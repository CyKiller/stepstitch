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

import re
from dataclasses import dataclass, replace
from typing import Any, Dict, List, Optional, Tuple

# --- Route templating (Python mirror of redaction.ts routeTemplate) ----------

_UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.I
)
_LONG_HEX_RE = re.compile(r"^[0-9a-f]{16,}$", re.I)


def _is_id_like_segment(seg: str) -> bool:
    if seg == "":
        return False
    if seg.isdigit():
        return True
    if _UUID_RE.match(seg):
        return True
    if _LONG_HEX_RE.match(seg):
        return True
    if len(seg) >= 6 and any(c.isdigit() for c in seg):
        return True
    return False


def route_template(value: str) -> str:
    """Reduce a path (or a leaked raw URL) to a route TEMPLATE.

    Strips scheme/host/query/hash entirely (query strings are a common NPI carrier)
    and replaces ID-like segments with ``:id``. Idempotent on an already-clean
    template, so a well-behaved SDK payload passes through unchanged.
    """
    if not value:
        return "/"
    # Drop scheme://host if a raw URL leaked through.
    stripped = re.sub(r"^[a-z][a-z0-9+.-]*://[^/]*", "", value, flags=re.I)
    path = stripped.split("?", 1)[0].split("#", 1)[0]
    if not path:
        return "/"
    segments = [":id" if _is_id_like_segment(seg) else seg for seg in path.split("/")]
    joined = "/".join(segments)
    return joined or "/"


# --- Free-text PII redaction --------------------------------------------------
#
# Applied in priority order: most specific first so a card number is not chewed
# up by the generic long-digit pass, and structured tokens (url/email) are removed
# before the numeric passes touch their internals.

_PII_PATTERNS: Tuple[Tuple[str, "re.Pattern[str]"], ...] = (
    ("url", re.compile(r"\b[a-z][a-z0-9+.-]*://\S+", re.I)),
    ("email", re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b")),
    ("ssn", re.compile(r"\b\d{3}-\d{2}-\d{4}\b")),
    # 13–19 digits, optionally separated by spaces/hyphens (cards, account numbers).
    ("card", re.compile(r"\b(?:\d[ -]?){13,19}\b")),
    (
        "phone",
        re.compile(r"\b(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b"),
    ),
    ("date", re.compile(r"\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b")),
    # Any remaining long digit run is treated as an identifier (account no., etc.).
    ("number", re.compile(r"\b\d{6,}\b")),
)


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
    if text is None:
        return None, []
    kinds: List[str] = []
    out = text
    for kind, pattern in _PII_PATTERNS:
        if pattern.search(out):
            out = pattern.sub(f"[redacted:{kind}]", out)
            kinds.append(kind)
    for kind, pattern in extra:
        if pattern.search(out):
            out = pattern.sub(f"[redacted:{kind}]", out)
            kinds.append(kind)
    return out, kinds


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


# --- Policy -------------------------------------------------------------------

# Structural, NPI-free metadata the server is willing to store. Anything else is
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
            redacted, kinds = redact_text(value, extra)
            if redacted is not None and len(redacted) > policy.max_text_len:
                redacted = redacted[: policy.max_text_len]
            if kinds or redacted != value:
                scrubbed.append(field_path)
            clean[key] = redacted
        elif isinstance(value, (int, float, bool)) or value is None:
            clean[key] = value
        else:
            # Nested structures are not part of the structural contract → drop.
            scrubbed.append(field_path)
    return clean


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
        redacted, kinds = redact_text(explanation, extra)
        if redacted is not None and len(redacted) > policy.max_text_len:
            redacted = redacted[: policy.max_text_len]
            if "explanation" not in scrubbed_fields:
                scrubbed_fields.append("explanation")
        if kinds:
            scrubbed_fields.append("explanation")
        result["explanation"] = redacted

    # 2. Footsteps — re-template routes, redact labels/targets, narrow metadata.
    footsteps = result.get("footsteps") or []
    clean_steps: List[Dict[str, Any]] = []
    for i, step in enumerate(footsteps):
        if not isinstance(step, dict):
            continue
        step = dict(step)
        route = step.get("route", "/")
        templated = route_template(route if isinstance(route, str) else "/")
        if templated != route:
            scrubbed_fields.append(f"footsteps[{i}].route")
        step["route"] = templated

        for text_key in ("label", "target"):
            val = step.get(text_key)
            if isinstance(val, str):
                redacted, kinds = redact_text(val, extra)
                if redacted is not None and len(redacted) > policy.max_text_len:
                    redacted = redacted[: policy.max_text_len]
                if kinds or (redacted != val):
                    if kinds:
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
    }
    return result, report


# Re-export ``replace`` for callers building policy variants without importing dataclasses.
def derive_policy(base: ScrubPolicy = FINANCIAL_SERVICES_ENTERPRISE, **changes: Any) -> ScrubPolicy:
    """Return a copy of ``base`` with the given fields overridden."""
    return replace(base, **changes)


__all__ = [
    "ScrubPolicy",
    "ScrubRejection",
    "FINANCIAL_SERVICES_ENTERPRISE",
    "scrub_trace_payload",
    "redact_text",
    "route_template",
    "derive_policy",
    "compile_extra_redactions",
]
