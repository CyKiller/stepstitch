"""Server-side scrubber — the enterprise trust boundary.

The SDK redacts in the browser (``src/redaction.ts``), but the server must not
*trust* the client: a hand-rolled ``curl`` POST, a buggy integration, or a
compromised page can send anything. This module is **defense-in-depth** — it runs
on every ingestion, independent of the SDK, so the stored trace is safe even when
the producer is hostile.

Design mirrors ``redaction.ts``: pure functions, no I/O and no service state, so the
proof suite can assert them directly. The scrubber never raises on dirty input under
the default policy — it redacts free text, drops disallowed/forbidden keys, and
re-templates routes, then reports exactly what it touched. Set
``reject_on_forbidden`` to turn a leak signal into a hard 422 instead.

Contract: see ``contracts/stepstitch.md`` (Ingestion API → server-side scrubber).
"""
from __future__ import annotations

import hashlib
import ipaddress
import json
import math
import re
from dataclasses import dataclass, replace
from dataclasses import fields as dataclass_fields
from typing import Any, Callable, Dict, List, Optional, Tuple
from urllib.parse import unquote

# --- Route templating (Python mirror of redaction.ts routeTemplate) ----------

_UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.I
)
_LONG_HEX_RE = re.compile(r"^[0-9a-f]{16,}$", re.I)


def _is_id_like_segment(seg: str) -> bool:
    if seg == "":
        return False
    if seg.startswith(":"):
        # Already a template parameter — idempotence on a clean template.
        return False
    if seg.isdigit():
        return True
    if _UUID_RE.match(seg):
        return True
    if _LONG_HEX_RE.match(seg):
        return True
    if len(seg) >= 6 and any(c.isdigit() for c in seg):
        return True
    if "@" in seg:
        # An email (or any addressed identity) used as a slug.
        return True
    # A segment that reads as a secret, an encoded blob or PII is an identifier by
    # construction, whatever its digit count.
    _, kinds = redact_text(seg)
    return bool(kinds)


def route_template(value: str) -> str:
    """Reduce a path (or a leaked raw URL) to a route TEMPLATE.

    Strips scheme/host/query/hash entirely (query strings are a common NPI carrier)
    and replaces ID-like segments with ``:id``. Idempotent on an already-clean
    template, so a well-behaved SDK payload passes through unchanged. Percent-encoding
    is decoded first — the SDK's ``routeTemplate`` does the same — so an encoded slug is
    judged by what it says, not by how it was spelled.
    """
    if not value:
        return "/"
    # Drop scheme://host if a raw URL leaked through.
    stripped = re.sub(r"^[a-z][a-z0-9+.-]*://[^/]*", "", value, flags=re.I)
    path = stripped.split("?", 1)[0].split("#", 1)[0]
    if not path:
        return "/"
    segments = [":id" if _is_id_like_segment(unquote(seg)) else seg
                for seg in path.split("/")]
    joined = "/".join(segments)
    return joined or "/"


# --- Secrets and encoded payloads ---------------------------------------------
#
# Applied BEFORE the PII passes. A credential or an encoded blob is one unit: left to
# the digit rules, a JWT or an API key either survives whole (``\b`` never fires inside
# a word) or is chewed into fragments that still carry most of the secret. These are
# also the shapes an exfiltrating agent uses — encoded fragments packed into short links
# and blobs — so catching them is what keeps a scrubbed trace from being a carrier.

# ``secret_assignment`` keeps the name and drops the value: "password=[redacted]" tells an
# engineer what went wrong without telling anyone the password.
_SECRET_NAME = r"[A-Za-z0-9_]*(?:token|secret|password|passwd|api[_-]?key|credential)[A-Za-z0-9_]*"

_SECRET_PATTERNS: Tuple[Tuple[str, "re.Pattern[str]"], ...] = (
    ("private_key", re.compile(
        r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?(?:-----END [A-Z ]*PRIVATE KEY-----|\Z)",
        re.S)),
    ("bearer", re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]{8,}")),
    ("jwt", re.compile(r"\bey[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{4,}\.[A-Za-z0-9_-]*")),
    ("api_key", re.compile(
        r"\b(?:sk-(?:proj-|ant-|live-|test-)?[A-Za-z0-9_-]{16,}"
        r"|gh[pousr]_[A-Za-z0-9]{16,}"
        r"|github_pat_[A-Za-z0-9_]{20,}"
        r"|A(?:KIA|SIA)[0-9A-Z]{16}"
        r"|xox[abprs]-[A-Za-z0-9-]{10,}"
        r"|AIza[0-9A-Za-z_-]{35}"
        r"|ss[ai]_[A-Za-z0-9_-]{8,})")),
    ("data_uri", re.compile(r"(?i)\bdata:[\w.+-]+/[\w.+-]+(?:;[\w=.+-]+)*,[^\s\"'<>)]+")),
    ("short_link", re.compile(
        r"(?i)\b(?:bit\.ly|t\.co|tinyurl\.com|goo\.gl|ow\.ly|is\.gd|buff\.ly|rebrand\.ly"
        r"|cutt\.ly|shorturl\.at|tiny\.cc)/[A-Za-z0-9_-]+")),
    ("percent_encoded", re.compile(r"(?:%[0-9A-Fa-f]{2}){4,}")),
)
# A secret-named word, then either an explicit separator and any value, or whitespace
# and a value that is credential-shaped (has a digit, 6+ chars) — so "the token expired"
# stays readable while "token FAKE-SECRET-123" does not.
_SECRET_ASSIGNMENT = re.compile(
    rf"(?i)\b({_SECRET_NAME})(\s*[=:]\s*[^\s,;]+|\s+(?=[^\s,;]*\d)[^\s,;]{{6,}})")

# High-entropy tokens: a whole whitespace/punctuation-delimited run of base64/base64url
# or hex characters. A token touching a '.' is never a candidate — that is how file
# paths, versions and hostnames stay out.
_ENTROPY_CANDIDATE = re.compile(
    r"(?<![A-Za-z0-9+/=_.\-])[A-Za-z0-9+/_\-]{24,}={0,2}(?![A-Za-z0-9+/=_.\-])")
_HEX_RUN = re.compile(r"^[0-9a-fA-F]{24,}$")


def _shannon_bits(value: str) -> float:
    counts: Dict[str, int] = {}
    for ch in value:
        counts[ch] = counts.get(ch, 0) + 1
    n = len(value)
    return -sum((c / n) * math.log2(c / n) for c in counts.values())


def _is_high_entropy(token: str) -> bool:
    has_digit = any(c.isdigit() for c in token)
    has_alpha = any(c.isalpha() for c in token)
    if not (has_digit and has_alpha):
        return False
    if _HEX_RUN.match(token):
        return True
    has_upper = any(c.isupper() for c in token)
    has_lower = any(c.islower() for c in token)
    return has_upper and has_lower and _shannon_bits(token) >= 4.0


# --- Free-text PII redaction --------------------------------------------------
#
# Applied in priority order: most specific first so a card number is not chewed
# up by the generic long-digit pass, and structured tokens (url/email) are removed
# before the numeric passes touch their internals. Filesystem paths run straight after
# URLs, so the email, IP and number passes never see a path's insides.

# Where a pasted filesystem path starts: a drive (``C:\``, ``c:/``, ``\\?\C:\``), a UNC
# share, an environment variable, or a POSIX home/system root (case-sensitive, so the
# web route ``/home`` on its own stays a route).
_PATH_ROOT = (
    r"(?:\\\\\?\\)?(?<![\w])[A-Za-z]:[\\/]"
    r"|\\\\\?\\UNC\\[^\s\\/]+\\[^\s\\/]+"
    r"|\\\\[^\s\\/?]+\\[^\s\\/]+"
    r"|%[A-Za-z_][A-Za-z0-9_]*%[\\/]"
    r"|(?<![\w./~])(?:~|/(?:Users|home|Volumes|private|tmp|var/folders))(?=/)"
)
# An unquoted path stops at whitespace and never ends on trailing punctuation.
_PATH_BODY = r"[^\s\"'<>|]*[^\s\"'<>|.,;:!?)]"
# A relative segment, or what an earlier pass left of one (a high-entropy or encoded
# segment is already a ``[redacted:<kind>]`` token by the time this pass runs).
_PATH_SEGMENT = r"(?:[\w.-]{2,}|\[redacted:[a-z_:]+\])"
_PATH = re.compile(
    rf"([\"'])(?:{_PATH_ROOT})[^\"'\r\n]*\1"           # quoted: spaces allowed
    rf"|(?:{_PATH_ROOT}){_PATH_BODY}"                  # unquoted
    # Relative Windows path. A match only starts at the head of a run, never inside a
    # '.'/'-' run, so a long punctuation run costs linear time, not quadratic.
    rf"|(?<![\w.\-\\:%\]]){_PATH_SEGMENT}(?:\\{_PATH_SEGMENT})+"
)

_PII_PATTERNS: Tuple[Tuple[str, "re.Pattern[str]"], ...] = (
    ("url", re.compile(r"\b[a-z][a-z0-9+.-]*://\S+", re.I)),
    # The whole path, leaf included: a home folder carries the user's name.
    ("path", _PATH),
    ("email", re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b")),
    # Country code, check digits, then 4-char groups (spaced or compact). Redacted only
    # when the mod-97 checksum passes — an unchecked shape would eat every error code.
    ("iban", re.compile(r"\b[A-Z]{2}\d{2}(?: ?[A-Z0-9]{4}){2,7}(?: ?[A-Z0-9]{1,3})?\b")),
    ("mac", re.compile(r"\b[0-9A-Fa-f]{2}(?:([:-])[0-9A-Fa-f]{2})(?:\1[0-9A-Fa-f]{2}){4}\b")),
    # IPv4, but never inside a version string ("Chrome/120.0.0.0", "v1.2.3.4").
    ("ip", re.compile(
        r"(?<![\w./:])(?:(?:25[0-5]|2[0-4]\d|1?\d?\d)\.){3}(?:25[0-5]|2[0-4]\d|1?\d?\d)"
        r"(?![\w.])")),
    # IPv6 candidates; confirmed by the stdlib parser before anything is redacted.
    ("ipv6", re.compile(r"(?<![\w:.])[0-9A-Fa-f]{0,4}(?::[0-9A-Fa-f]{0,4}){2,7}(?![\w:])")),
    ("ssn", re.compile(r"\b\d{3}([- ])\d{2}\1\d{4}\b")),
    # 13–19 digits, optionally separated by spaces/hyphens (cards, account numbers).
    ("card", re.compile(r"\b(?:\d[ -]?){13,19}\b")),
    ("phone_intl", re.compile(r"(?<![\w+])\+(?!1\b)\d{1,3}(?:[\s.-]?\(?\d{1,4}\)?){2,5}(?!\w)")),
    (
        "phone",
        re.compile(r"\b(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b"),
    ),
    ("date", re.compile(r"\b(?:\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|(?:19|20)\d{2}-\d{2}-\d{2})\b")),
    # Any remaining long digit run is treated as an identifier (account no., etc.).
    ("number", re.compile(r"\b\d{6,}\b")),
)


def iban_valid(value: str) -> bool:
    """ISO 13616 mod-97 check. Decides whether an IBAN-shaped run is redacted at all."""
    compact = re.sub(r"\s", "", value).upper()
    if not (15 <= len(compact) <= 34):
        return False
    rearranged = compact[4:] + compact[:4]
    try:
        digits = "".join(str(int(ch, 36)) for ch in rearranged)
    except ValueError:
        return False
    return int(digits) % 97 == 1


def _ipv6_valid(value: str) -> bool:
    if value.count(":") < 2 or len([g for g in value.split(":") if g]) < 3:
        return False
    try:
        return isinstance(ipaddress.ip_address(value), ipaddress.IPv6Address)
    except ValueError:
        return False


# Labelers for the patterns whose match is a CANDIDATE, not a verdict. Each returns the
# label to redact under, or None to leave the text alone.
_LABELERS: Dict[str, Callable[[str], Optional[str]]] = {
    "iban": lambda m: "iban" if iban_valid(m) else None,
    "ipv6": lambda m: "ip" if _ipv6_valid(m) else None,
    "phone_intl": lambda m: "phone" if len(re.sub(r"\D", "", m)) >= 8 else None,
    # Luhn is labeling precision, not a coverage decision: a 13-19 digit run that fails
    # the checksum is still redacted, as a generic number.
    "card": lambda m: "card" if luhn_valid(re.sub(r"\D", "", m)) else "number",
}


# Candidate patterns whose confirmed matches are reported under another kind.
_REPORTED_AS = {"ipv6": "ip", "phone_intl": "phone"}


def built_in_detector_kinds() -> List[str]:
    """Every kind the built-in detectors can report, in the order they run."""
    kinds = [k for k, _ in _SECRET_PATTERNS] + ["secret_assignment", "high_entropy"]
    for kind, _ in _PII_PATTERNS:
        reported = _REPORTED_AS.get(kind, kind)
        if reported not in kinds:
            kinds.append(reported)
    if "number" not in kinds:  # the card labeler's fallback label
        kinds.append("number")
    return kinds


def detector_set_sha256() -> str:
    """Digest of the BUILT-IN detector set — the part ``policy_sha256`` cannot see.

    ``policy_sha256`` hashes the operator-visible policy; the patterns every policy shares
    live here, in code. When they change, evidence scrubbed before and after the change
    must be distinguishable, so the scrub report carries both digests.
    """
    material = {
        "secret": [[k, p.pattern] for k, p in _SECRET_PATTERNS],
        "secret_assignment": _SECRET_ASSIGNMENT.pattern,
        "entropy": [_ENTROPY_CANDIDATE.pattern, _HEX_RUN.pattern, 4.0],
        "pii": [[k, p.pattern] for k, p in _PII_PATTERNS],
        "labelers": sorted(_LABELERS),
    }
    payload = json.dumps(material, sort_keys=True, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()


def luhn_valid(digits: str) -> bool:
    """Luhn checksum over a digit string. Labeling only — an invalid checksum
    never reduces redaction, it only reclassifies card -> number."""
    if not digits.isdigit() or len(digits) < 13:
        return False
    total = 0
    for index, char in enumerate(reversed(digits)):
        value = int(char)
        if index % 2 == 1:
            value *= 2
            if value > 9:
                value -= 9
        total += value
    return total % 10 == 0


# --- Advisory detectors (host-injected; defense-in-depth, never proof) -----------
#
# A detector is code the HOST registers at build time (like sign_blob or the draft
# adapters) — never something operator config can carry, because config must stay
# data. Each detector takes the (already regex-scrubbed) text and returns literal
# substrings it believes are sensitive; every returned literal is redacted and the
# scrub report labels the kind ``advisory:<name>``. By construction a detector can
# only ADD redaction. This is the seam a Presidio/NER adapter plugs into; its
# output is detection — advisory signal — never proof of absence, and the strict
# schema remains the privacy boundary.
_ADVISORY_DETECTORS: List[Tuple[str, Any]] = []


def register_advisory_detector(name: str, detector: Any) -> None:
    """Register a host-injected detector: ``detector(text) -> iterable of literals``."""
    _ADVISORY_DETECTORS.append((str(name), detector))


def clear_advisory_detectors() -> None:
    """Test seam — the registry is process-global."""
    _ADVISORY_DETECTORS.clear()


def redact_secrets(text: str, fired: Optional[Callable[[str], None]] = None) -> str:
    """Redact credentials and encoded payloads only — the first pass of ``redact_text``.

    Exposed on its own for machine output (run transcripts) where the PII digit rules
    would destroy line numbers and timings but a leaked token must still never survive.
    """
    def _note(kind: str) -> None:
        if fired is not None:
            fired(kind)

    out = text
    for kind, pattern in _SECRET_PATTERNS:
        out, n = pattern.subn(f"[redacted:{kind}]", out)
        for _ in range(n):
            _note(kind)

    def _assignment(match: "re.Match[str]") -> str:
        tail = match.group(2)
        sep = tail[: len(tail) - len(tail.lstrip(" \t\r\n=:"))]
        if match.group(2)[len(sep):].startswith("[redacted"):
            # Already scrubbed upstream — a second pass must be a no-op, not a new finding.
            return match.group(0)
        _note("secret_assignment")
        return f"{match.group(1)}{sep}[redacted:secret_assignment]"

    out = _SECRET_ASSIGNMENT.sub(_assignment, out)

    def _entropy(match: "re.Match[str]") -> str:
        token = match.group(0)
        if not _is_high_entropy(token):
            return token
        _note("high_entropy")
        return "[redacted:high_entropy]"

    return _ENTROPY_CANDIDATE.sub(_entropy, out)


def redact_text(
    text: Optional[str],
    extra: Tuple[Tuple[str, "re.Pattern[str]"], ...] = (),
) -> Tuple[Optional[str], List[str]]:
    """Redact PII from a free-text string.

    Returns ``(scrubbed_text, kinds)`` where ``kinds`` lists the distinct PII
    categories that fired (e.g. ``["ssn", "email"]``). ``None`` passes through.

    ``extra`` is an optional tuple of ``(label, compiled-pattern)`` applied AFTER the
    built-in passes — operator-configured additions that can only ADD redaction.
    """
    out, counts = redact_text_counted(text, extra)
    return out, list(counts)


def redact_text_counted(
    text: Optional[str],
    extra: Tuple[Tuple[str, "re.Pattern[str]"], ...] = (),
    skip: frozenset = frozenset(),
) -> Tuple[Optional[str], Dict[str, int]]:
    """``redact_text`` with occurrence counts: ``(scrubbed_text, {kind: count})``.

    The dict preserves first-fired order, so ``list(counts)`` is exactly the ``kinds`` list
    ``redact_text`` has always returned. ``skip`` names built-in PII passes to leave out —
    used only by the reproduction redactor, which replaces the ``url`` pass with a
    query-string strip so a stack frame keeps its file and line.
    """
    if text is None:
        return None, {}
    counts: Dict[str, int] = {}

    def _fired(kind: str, n: int = 1) -> None:
        counts[kind] = counts.get(kind, 0) + n

    out = redact_secrets(text, _fired)
    for kind, pattern in _PII_PATTERNS:
        if kind in skip:
            continue
        labeler = _LABELERS.get(kind)
        if labeler is not None:
            def _labeled(match: "re.Match[str]", labeler=labeler) -> str:
                label = labeler(match.group(0))
                if label is None:
                    return match.group(0)
                _fired(label)
                return f"[redacted:{label}]"

            out = pattern.sub(_labeled, out)
            continue
        out, n = pattern.subn(f"[redacted:{kind}]", out)
        if n:
            _fired(kind, n)
    for kind, pattern in extra:
        out, n = pattern.subn(f"[redacted:{kind}]", out)
        if n:
            _fired(kind, n)
    for name, detector in _ADVISORY_DETECTORS:
        try:
            literals = [str(v) for v in (detector(out) or []) if str(v)]
        except Exception:
            # A broken detector must never break ingestion — advisory means advisory.
            continue
        for literal in literals:
            n = out.count(literal)
            if n:
                out = out.replace(literal, f"[redacted:advisory:{name}]")
                _fired(f"advisory:{name}", n)
    return out, counts


def compile_extra_redactions(
    policy: "ScrubPolicy",
) -> Tuple[Tuple[str, "re.Pattern[str]"], ...]:
    """Compile a policy's operator-supplied ``extra_redactions`` to ``(label, pattern)``.

    An un-compilable pattern is skipped (it is validated/rejected at config-save time, but
    we never let a bad stored pattern break ingestion)."""
    compiled: List[Tuple[str, "re.Pattern[str]"]] = []
    for item in policy.extra_redactions:
        try:
            label, raw = item[0], item[1]
            compiled.append((f"custom:{label}", re.compile(raw)))
        except (re.error, IndexError, TypeError):
            continue
    return tuple(compiled)


# --- Strict-schema primitives ---------------------------------------------------
#
# Under the strict financial posture, semantic content is not scrubbed — it is
# refused. A selector is acceptable only when it provably carries no author- or
# customer-authored string: an operator-approved static ``data-testid`` value, or a
# purely structural path (tag names and :nth-of-type positions). Routes must match
# an operator-declared template. Everything else is a rejected field.

# The label constant the SDK stores for masked elements (src/types.ts MASKED).
MASKED_LABEL = "[masked]"

# One segment of a structural path as built by ``buildSelector`` (redaction.ts):
# a lowercase tag name, optionally positioned. Tag names are static application
# code, never per-customer data, so they cannot carry NPI.
_STRUCTURAL_SEGMENT_RE = re.compile(r"^[a-z][a-z0-9-]*(?::nth-of-type\(\d+\))?$")
# A data-testid segment, exactly as the SDK emits it: [data-testid="..."] with
# CSS-escaped contents.
_TESTID_SEGMENT_RE = re.compile(r'^\[data-testid="((?:[^"\\]|\\.)*)"\]$')


def _unescape_css(value: str) -> str:
    return re.sub(r"\\(.)", r"\1", value)


def selector_allowed(target: str, approved_testids: frozenset) -> bool:
    """True when every segment of ``target`` is structural or an approved testid.

    Mirrors the SDK's ``buildSelector`` grammar: segments joined by `` > ``, each a
    tag (optionally ``:nth-of-type(n)``) or a ``[data-testid="..."]`` anchor. ``#id``
    segments and anything else are NOT allowed — ids are author strings the operator
    has not vouched for.
    """
    if not target:
        return True
    for segment in target.split(" > "):
        if _STRUCTURAL_SEGMENT_RE.match(segment):
            continue
        m = _TESTID_SEGMENT_RE.match(segment)
        if m and _unescape_css(m.group(1)) in approved_testids:
            continue
        return False
    return True


def route_matches_templates(route: str, templates: Tuple[str, ...]) -> bool:
    """True when ``route`` (already templated) matches one operator template.

    Segment-wise: a template segment starting with ``:`` matches any segment
    (including the scrubber's generic ``:id``); a literal segment must be equal.
    """
    route_segs = route.split("/")
    for template in templates:
        tmpl_segs = template.split("/")
        if len(tmpl_segs) != len(route_segs):
            continue
        if all(
            t.startswith(":") or t == r
            for t, r in zip(tmpl_segs, route_segs)
        ):
            return True
    return False


# --- Policy -------------------------------------------------------------------

# Structural, structural metadata the server is willing to store. Anything else is
# dropped (strict allowlist) — values are still PII-scrubbed before storage.
_DEFAULT_METADATA_ALLOWLIST = frozenset(
    {
        "sdk_version",
        "sdk_build",
        "viewport",
        "user_agent",
        "consent_version",
        "locale",
        "release",
        "environment",
        "sentry_release",
        "sentry_environment",
    }
)
# Footstep metadata is even narrower: only structural diagnostics.
_DEFAULT_FOOTSTEP_METADATA_ALLOWLIST = frozenset(
    {
        "status",
        "error_type",
        "method",
        "endpoint",
        "source_path",
        "line",
        "column",
        "interacted",
    }
)
# Keys whose mere presence is a leak signal — raw bodies, headers, console, cookies.
_DEFAULT_FORBIDDEN_KEYS = frozenset(
    {
        "request_body",
        "request_bodies",
        "response_body",
        "response_bodies",
        "body",
        "console",
        "console_messages",
        "network_headers",
        "headers",
        "cookies",
        "cookie",
        "url",
        "raw_url",
        "query",
        "query_string",
        "screenshot",
        "screenshots",
        "dom",
        "dom_text",
        "html",
        "message",
        "messages",
        "stack",
        "stacktrace",
        "log",
        "logs",
        "console_log",
    }
)


@dataclass(frozen=True)
class ScrubPolicy:
    """Server-side scrub policy. Defaults = strict financial-services posture."""

    name: str = "financial-services-enterprise"
    free_text: str = "scrub"  # "scrub" → redact PII; "disabled" → drop explanation
    max_text_len: int = 280
    metadata_allowlist: frozenset = _DEFAULT_METADATA_ALLOWLIST
    footstep_metadata_allowlist: frozenset = _DEFAULT_FOOTSTEP_METADATA_ALLOWLIST
    forbidden_keys: frozenset = _DEFAULT_FORBIDDEN_KEYS
    # When True, a forbidden key (or disallowed free text under "disabled") makes
    # the whole payload invalid → router returns 422 instead of silently dropping.
    reject_on_forbidden: bool = False
    # Operator additions from the dashboard scrub editor. Both can only TIGHTEN: extra
    # patterns add redaction, extra keys add drops. Neither can remove a built-in rule, so
    # the floor (``_PII_PATTERNS`` + ``_DEFAULT_FORBIDDEN_KEYS``) always holds regardless of
    # config. ``extra_redactions`` is a tuple of ``(label, regex-string)``.
    extra_redactions: Tuple[Tuple[str, str], ...] = ()
    extra_forbidden_keys: frozenset = frozenset()
    # Strict-schema knobs (financial-services-strict). Defaults are the permissive
    # values, so every existing profile behaves exactly as before.
    #   selector_policy "approved_testids": a footstep target must be an operator-
    #   approved static data-testid or a purely structural path; anything else is a
    #   rejected field. Deny-by-default: an empty allowlist rejects every semantic
    #   selector, and operator config can only name specific static values — it can
    #   never turn the check off.
    selector_policy: str = "any"  # "any" | "approved_testids"
    approved_testids: frozenset = frozenset()
    #   route_policy "operator_templates": a footstep route (post-templating) must
    #   match one operator-declared template; unknown semantic routes are rejected.
    route_policy: str = "any"  # "any" | "operator_templates"
    route_templates: Tuple[str, ...] = ()
    #   enforce_masked_labels: any label other than "[masked]" is re-masked before
    #   storage — the SDK's unmask attribute has no effect on what this tenant stores.
    enforce_masked_labels: bool = False

    @property
    def strict_schema_active(self) -> bool:
        """True when any strict-schema knob is on (drives the schema_status report)."""
        return (
            self.selector_policy != "any"
            or self.route_policy != "any"
            or self.enforce_masked_labels
        )

    @property
    def all_forbidden_keys(self) -> frozenset:
        """Built-in forbidden keys UNION operator additions — never fewer than the built-ins."""
        return self.forbidden_keys | self.extra_forbidden_keys


FINANCIAL_SERVICES_ENTERPRISE = ScrubPolicy()


class ScrubRejection(Exception):
    """Raised when ``reject_on_forbidden`` is set and a forbidden field is present."""

    def __init__(self, fields: List[str]) -> None:
        self.fields = fields
        super().__init__(f"payload rejected by scrubber: {', '.join(fields)}")


# --- Metadata scrubbing -------------------------------------------------------


def _scrub_metadata(
    meta: Any,
    allowlist: frozenset,
    policy: ScrubPolicy,
    prefix: str,
    scrubbed: List[str],
    rejected: List[str],
    extra: Tuple[Tuple[str, "re.Pattern[str]"], ...] = (),
    kinds: Optional[Dict[str, int]] = None,
) -> Dict[str, Any]:
    """Drop forbidden + non-allowlisted keys; PII-scrub remaining string values."""
    if not isinstance(meta, dict):
        return {}
    clean: Dict[str, Any] = {}
    for key, value in meta.items():
        field_path = f"{prefix}.{key}"
        if key in policy.all_forbidden_keys:
            scrubbed.append(field_path)
            rejected.append(field_path)
            continue
        if key not in allowlist:
            # Unexpected key → drop. Strict allowlist prevents silent NPI smuggling.
            scrubbed.append(field_path)
            continue
        if isinstance(value, str):
            if key in {"endpoint", "source_path"}:
                templated = route_template(value)
                if templated != value:
                    scrubbed.append(field_path)
                clean[key] = templated[: policy.max_text_len]
                continue
            redacted, counts = redact_text_counted(value, extra)
            _merge_counts(kinds, counts)
            if redacted is not None and len(redacted) > policy.max_text_len:
                redacted = redacted[: policy.max_text_len]
            if counts or redacted != value:
                scrubbed.append(field_path)
            clean[key] = redacted
        elif isinstance(value, (int, float, bool)) or value is None:
            clean[key] = value
        else:
            # Nested structures are not part of the structural contract → drop.
            scrubbed.append(field_path)
    return clean


def _merge_counts(into: Optional[Dict[str, int]], counts: Dict[str, int]) -> None:
    if into is None:
        return
    for kind, n in counts.items():
        into[kind] = into.get(kind, 0) + n


# A footstep timestamp is stored verbatim, so it may only LOOK like a timestamp: ISO-8601,
# epoch digits, or the short ordinal tokens hand-rolled clients use ("t", "t1"). Anything
# else is a free-text channel and is replaced, never stored.
_TIMESTAMP_SHAPE = re.compile(r"^(?:[0-9TZtz:.+\- ]{1,40}|t\d{0,6})$")
REDACTED_TIMESTAMP = "[redacted:timestamp]"


# Identifier fields (``app_id``, ``project_id``, ``consent_version``) are stored verbatim
# because they key tenancy and consent, so they must BE identifiers: no spaces, no '@',
# nothing long enough to carry a sentence or a blob. The router's schema and the offline
# policy classifier both enforce this one pattern.
IDENTIFIER_PATTERN = r"^[A-Za-z0-9._:-]{1,128}$"
IDENTIFIER_FIELDS = ("app_id", "project_id", "consent_version")


# --- Public entry point -------------------------------------------------------


def scrub_trace_payload(
    payload: Dict[str, Any],
    policy: ScrubPolicy = FINANCIAL_SERVICES_ENTERPRISE,
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """Scrub an ingestion payload in place-of-trust.

    Accepts the raw dict (``explanation``, ``footsteps``, ``metadata``, ...) and
    returns ``(scrubbed_payload, report)``. ``report`` is::

        {"scrub_status": "clean" | "scrubbed", "scrubbed_fields": [...], "policy": "..."}

    Raises :class:`ScrubRejection` when ``policy.reject_on_forbidden`` is set and a
    forbidden field is present.
    """
    scrubbed_fields: List[str] = []
    rejected_fields: List[str] = []
    kind_counts: Dict[str, int] = {}
    result = dict(payload)
    extra = compile_extra_redactions(policy)  # operator additions; () for the base policy

    # 1. Free-text explanation — the single biggest NPI carrier.
    explanation = result.get("explanation")
    if policy.free_text == "disabled":
        if explanation:
            scrubbed_fields.append("explanation")
            rejected_fields.append("explanation")
        result["explanation"] = None
    else:
        redacted, counts = redact_text_counted(explanation, extra)
        _merge_counts(kind_counts, counts)
        if redacted is not None and len(redacted) > policy.max_text_len:
            redacted = redacted[: policy.max_text_len]
            if "explanation" not in scrubbed_fields:
                scrubbed_fields.append("explanation")
        if counts:
            scrubbed_fields.append("explanation")
        result["explanation"] = redacted

    # 2. Footsteps — re-template routes, redact labels/targets, narrow metadata.
    footsteps = result.get("footsteps") or []
    clean_steps: List[Dict[str, Any]] = []
    for i, step in enumerate(footsteps):
        if not isinstance(step, dict):
            continue
        step = dict(step)
        stamp = step.get("timestamp")
        if isinstance(stamp, str) and not _TIMESTAMP_SHAPE.match(stamp):
            scrubbed_fields.append(f"footsteps[{i}].timestamp")
            _merge_counts(kind_counts, {"timestamp": 1})
            step["timestamp"] = REDACTED_TIMESTAMP
        route = step.get("route", "/")
        templated = route_template(route if isinstance(route, str) else "/")
        if templated != route:
            scrubbed_fields.append(f"footsteps[{i}].route")
        step["route"] = templated

        if policy.route_policy == "operator_templates" and not route_matches_templates(
            templated, policy.route_templates
        ):
            # Unknown semantic route: refused, never stored. Under reject_on_forbidden
            # this becomes a 422; otherwise the route is reduced to "/" so the unknown
            # slug cannot persist either way.
            scrubbed_fields.append(f"footsteps[{i}].route")
            rejected_fields.append(f"footsteps[{i}].route")
            step["route"] = "/"

        if policy.enforce_masked_labels:
            label = step.get("label")
            if isinstance(label, str) and label != MASKED_LABEL:
                # Re-mask, don't reject: masking is loss-free for privacy, and it is
                # what makes the SDK's unmask attribute inert for this tenant.
                scrubbed_fields.append(f"footsteps[{i}].label")
                step["label"] = MASKED_LABEL

        if policy.selector_policy == "approved_testids":
            target = step.get("target")
            if isinstance(target, str) and not selector_allowed(
                target, policy.approved_testids
            ):
                scrubbed_fields.append(f"footsteps[{i}].target")
                rejected_fields.append(f"footsteps[{i}].target")
                step["target"] = None

        for text_key in ("label", "target"):
            if text_key == "target" and policy.selector_policy == "approved_testids":
                # Already checked against the selector allowlist above — the value is
                # an operator-approved static testid or a purely structural path (or
                # None). That check is strictly stronger than the free-text regexes,
                # which would otherwise mangle an approved testid containing digits.
                continue
            if text_key == "label" and policy.enforce_masked_labels:
                # The label is exactly "[masked]" after enforcement above; the generic
                # pass would truncate it to max_text_len (1 under disabled free text).
                continue
            val = step.get(text_key)
            if isinstance(val, str):
                # A selector is CSS, where a backslash is an escape ("checkout\.submit"),
                # never a path separator.
                skip = frozenset({"path"}) if text_key == "target" else frozenset()
                redacted, counts = redact_text_counted(val, extra, skip=skip)
                _merge_counts(kind_counts, counts)
                if redacted is not None and len(redacted) > policy.max_text_len:
                    redacted = redacted[: policy.max_text_len]
                if counts or redacted != val:
                    # A truncation is a change to what is stored, so it is reported too.
                    scrubbed_fields.append(f"footsteps[{i}].{text_key}")
                step[text_key] = redacted

        if "metadata" in step and step["metadata"] is not None:
            step["metadata"] = _scrub_metadata(
                step["metadata"],
                policy.footstep_metadata_allowlist,
                policy,
                f"footsteps[{i}].metadata",
                scrubbed_fields,
                rejected_fields,
                extra,
                kind_counts,
            )
        clean_steps.append(step)
    result["footsteps"] = clean_steps

    # 3. Top-level metadata — strict allowlist + value scrub.
    if "metadata" in result and result["metadata"] is not None:
        result["metadata"] = _scrub_metadata(
            result["metadata"],
            policy.metadata_allowlist,
            policy,
            "metadata",
            scrubbed_fields,
            rejected_fields,
            extra,
            kind_counts,
        )

    if policy.reject_on_forbidden and rejected_fields:
        raise ScrubRejection(sorted(set(rejected_fields)))

    # De-dupe while preserving first-seen order.
    seen: Dict[str, None] = {}
    for f in scrubbed_fields:
        seen.setdefault(f, None)
    ordered = list(seen.keys())

    report = {
        "scrub_status": "scrubbed" if ordered else "clean",
        "scrubbed_fields": ordered,
        "policy": policy.name,
        # The policy a name cannot pin down: two tenants can both run a profile called
        # "financial-services-strict" with different operator allowlists. The digest is
        # the policy's actual configuration, so a FixProof (or an auditor) can say "this
        # evidence was scrubbed under EXACTLY these rules" — not "under a rule set that
        # shared a label with these rules".
        "policy_sha256": policy_sha256(policy),
        # The built-in detectors every policy shares — what policy_sha256 cannot see.
        "detector_set_sha256": detector_set_sha256(),
        # What fired, by kind and occurrence. Counts only — never the values.
        "kinds": kind_counts,
    }
    if policy.strict_schema_active:
        # An explicit, honest status: the strict schema checks ran and the stored
        # payload satisfies them. Never phrased as "no NPI proven" — the checks are
        # what is proven. (A rejected payload raises above and stores nothing; the
        # dropped-violations wording only appears under a non-rejecting variant.)
        report["schema_status"] = (
            "strict_schema_passed" if not rejected_fields
            else "strict_schema_violations_dropped"
        )
    return result, report


# Re-export ``replace`` for callers building policy variants without importing dataclasses.
def derive_policy(base: ScrubPolicy = FINANCIAL_SERVICES_ENTERPRISE, **changes: Any) -> ScrubPolicy:
    """Return a copy of ``base`` with the given fields overridden."""
    return replace(base, **changes)


def policy_sha256(policy: ScrubPolicy) -> str:
    """A content digest of the policy's full configuration, ``sha256:``-prefixed.

    Every dataclass field participates — enumerated via ``dataclasses.fields`` so a knob
    added later is hashed by construction, never silently outside the digest (the guard
    test parametrizes over the same enumeration). Unordered collections are sorted and
    tuples-of-tuples listified so the digest depends on the policy's CONTENT, not on the
    construction order of a frozenset or the JSON quirks of a tuple.
    """
    canonical: Dict[str, Any] = {}
    for f in dataclass_fields(policy):
        value = getattr(policy, f.name)
        if isinstance(value, frozenset):
            canonical[f.name] = sorted(value)
        elif isinstance(value, tuple):
            canonical[f.name] = [list(v) if isinstance(v, tuple) else v for v in value]
        else:
            canonical[f.name] = value
    payload = json.dumps(canonical, sort_keys=True, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()


def apply_scrub_overrides(base: ScrubPolicy, cfg: Dict[str, Any]) -> ScrubPolicy:
    """Compose the base profile with operator overrides. Every field only TIGHTENS or
    scopes an already-strict check: extra patterns add redaction, extra keys add drops,
    and the strict allowlists (approved testids / route templates) name the specific
    static values a deny-by-default profile will accept. Overrides can never flip a
    strict knob off, remove a built-in rule, or re-enable free text. A malformed entry
    is dropped, never able to loosen the base. Pure + testable, stdlib-only — the host
    and the ``stepstitch policy verify`` CLI both use exactly this function, so a
    fixture run and a live ingest can never disagree about what a config means."""
    extra_red = tuple(
        (str(p[0]), str(p[1]))
        for p in (cfg.get("extra_redactions") or [])
        if isinstance(p, (list, tuple)) and len(p) == 2
    )
    extra_keys = frozenset(str(k) for k in (cfg.get("extra_forbidden_keys") or []))
    changes: Dict[str, Any] = {
        "extra_redactions": extra_red, "extra_forbidden_keys": extra_keys}
    # The strict allowlists are inert unless the base profile turned the matching
    # policy on (selector_policy / route_policy are profile-owned, never override-
    # settable), so on a permissive profile these keys change nothing.
    testids = cfg.get("approved_testids")
    if isinstance(testids, (list, tuple)):
        changes["approved_testids"] = frozenset(str(t) for t in testids)
    templates = cfg.get("route_templates")
    if isinstance(templates, (list, tuple)):
        changes["route_templates"] = tuple(str(t) for t in templates)
    return derive_policy(base, **changes)


__all__ = [
    "ScrubPolicy",
    "ScrubRejection",
    "FINANCIAL_SERVICES_ENTERPRISE",
    "MASKED_LABEL",
    "scrub_trace_payload",
    "redact_text",
    "redact_text_counted",
    "redact_secrets",
    "detector_set_sha256",
    "route_template",
    "derive_policy",
    "apply_scrub_overrides",
    "compile_extra_redactions",
    "selector_allowed",
    "route_matches_templates",
]
