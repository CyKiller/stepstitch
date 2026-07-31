"""Deep evidence from the reproduction — never from the person who reported the bug.

This is the inversion the product rests on. Session-replay tools buy debugging depth by
recording the real user: their screen, their inputs, their page text. StepStitch takes
almost nothing from production, reproduces the failure in a local run on the developer's
own machine against the operator-configured application, and then inspects *that*
execution as deeply as it likes.

> **Minimal evidence from production. Maximum evidence from a controlled reproduction.**

What the architecture proves, every record states; what it cannot prove, no record claims.
Provable: nothing here came from the reported session (the runner replays a generated test,
it never reads the user's trail), and every string passed the scrubber. NOT provable: that
the application under test holds no customer data — ``STEPSTITCH_APP_BASE_URL`` points
wherever the operator configured, and a staging backend with real records will print what
it prints. The scrubber removes known PATTERNS; a name or a postal address is not a
pattern, and no regex reliably makes it one. An earlier version of this stamp said
``contains_customer_session_data: false``, which read as a promise about content and was
only ever a fact about the session actor; the posture below replaced it.

**How it is collected.** Playwright *tracing*, parsed after the run — not a reporter. A
reporter receives test results and attachments; it never gets the live ``Page``, so it
cannot see the DOM, the network, or the console. The trace can, and it is produced by the
byte-identical frozen script without that script knowing anything about it.

**The execution envelope.** Freezing the test alone is not enough to make two runs
comparable: *how* the test ran matters too. A different browser build, timeout or base URL
can turn the same bytes into a different outcome, and a referee that only pins the script
would be quietly comparing two different experiments. So the envelope is hashed as well,
and a verification run must match on both. (The diagnostics profile is deliberately NOT in
that hash — ``prove-diagnostics-are-inert.mjs`` is the standing proof that tracing changes
no outcome — so a profile difference is never a mismatch and no refusal may claim it is.)
"""
from __future__ import annotations

import hashlib
import json
import re
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

# Bump when the shape of a stored record changes. Stored beside every record so a reader
# (or a later migration) can tell what it is looking at without guessing. 2: the absolute
# `contains_customer_session_data` claim was replaced by the normalized posture below.
SCHEMA_VERSION = 2

# The only provenance this module ever emits. Deliberately not a parameter: there is no
# code path that produces a diagnostics record from production traffic, and offering one
# would make the guarantee a configuration option rather than a property.
SOURCE_LOCAL_REPRODUCTION = "local_reproduction"

# Bounds. A diagnostics record is meant to fit in an agent's context beside the rest of the
# packet; an unbounded one would defeat the whole size argument the product makes.
MAX_CONSOLE_ERRORS = 20
MAX_FAILED_REQUESTS = 20
MAX_STACK_FRAMES = 30
MAX_FIELD_CHARS = 2000


def provenance() -> Dict[str, Any]:
    """The stamp every agent-facing diagnostics field carries or inherits.

    Each field states one thing the architecture actually delivers, and the one thing it
    cannot deliver is stated as exactly that:

    - ``from_reported_session: false`` — provable. The runner replays a generated test; no
      code path feeds the reported trail into a diagnostics record.
    - ``content_scrubbed: true`` — every string passed the credential and PII scrubbers.
      A statement about processing, deliberately not about outcome.
    - ``environment_assurance: operator_configured`` — the application under test is
      whatever the operator pointed ``STEPSTITCH_APP_BASE_URL`` at. StepStitch does not
      enforce that it holds only synthetic records.
    - ``customer_data_status: not_verified`` — the honest consequence of the two above.
      Scrubbing removes known patterns; it cannot prove a name or an address absent.
    """
    return {
        "source": SOURCE_LOCAL_REPRODUCTION,
        "from_reported_session": False,
        "content_scrubbed": True,
        "environment_assurance": "operator_configured",
        "customer_data_status": "not_verified",
        "schema_version": SCHEMA_VERSION,
    }


# Bump when the MEANING of the envelope digest changes, so old digests are refused rather
# than silently compared against a hash computed a different way. Separate from
# SCHEMA_VERSION on purpose: that one stamps stored diagnostics records, whose shape is
# untouched by how the envelope happens to be hashed. 3: the diagnostics SCHEMA_VERSION
# was removed from the hashed payload — record-shape changes must not move run digests.
ENVELOPE_SCHEMA_VERSION = 3


@dataclass(frozen=True)
class ExecutionEnvelope:
    """*How* the frozen script ran — the other half of a reproducible verdict.

    Env vars appear by NAME only. The names are part of how a run was configured and are
    worth pinning; the values are exactly what must never be recorded.
    """

    config_canonical: str             # the config SPEC as canonical JSON, paths placeheld
    browser: str                      # e.g. "chromium 149.0.7827.55 (playwright build 1228)"
    base_url: str                     # identity of the app under test
    timeout_ms: int
    retries: int
    diagnostics_profile: str          # "off" | "four-signal"
    runner_version: str
    env_names: List[str] = field(default_factory=list)

    def as_dict(self) -> Dict[str, Any]:
        """The full record — everything about how the run was configured, for humans and
        for the refusal message. A superset of what is hashed."""
        return {
            "config_canonical": self.config_canonical,
            "browser": self.browser,
            "base_url": self.base_url,
            "timeout_ms": self.timeout_ms,
            "retries": self.retries,
            "diagnostics_profile": self.diagnostics_profile,
            "runner_version": self.runner_version,
            # Only the envelope's OWN version. The diagnostics SCHEMA_VERSION used to sit
            # here too, inside the hashed payload — coupling that would have moved every
            # envelope digest each time the record shape changed, refusing verification of
            # every session frozen before the bump. Found when SCHEMA_VERSION went to 2.
            "envelope_schema_version": ENVELOPE_SCHEMA_VERSION,
            "env_names": sorted(self.env_names),
        }

    def hashed_payload(self) -> Dict[str, Any]:
        """The subset that decides whether two runs are the same experiment.

        ``diagnostics_profile`` is deliberately EXCLUDED, and this is the one judgement
        call in the envelope worth defending. Including it would make the check
        unenforceable exactly where it matters: the freeze traces (that run is the one worth
        inspecting) and the verification does not (a green run has nothing to diagnose), so
        the two would differ by construction on every single fix that ever gets verified. A
        check that always refuses is indistinguishable from one that is never reached.

        The empirical basis for excluding it is not an assumption — it is a blocking CI
        gate. ``scripts/prove-diagnostics-are-inert.mjs`` runs every failure shape twice
        against real Chromium, tracing off and on, and asserts identical verdict, identical
        frozen hash and identical failure fingerprint. If that gate is ever deleted or
        weakened, this exclusion loses its justification and belongs back in the hash.
        ``screenshots`` and ``use.trace`` are the same class of observer and are stripped
        from ``config_canonical`` for the same reason.
        """
        record = self.as_dict()
        record.pop("diagnostics_profile", None)
        return record

    def sha256(self) -> str:
        """Canonical hash of the envelope, computed the way the attestation is."""
        payload = json.dumps(self.hashed_payload(), sort_keys=True,
                             separators=(",", ":")).encode("utf-8")
        return hashlib.sha256(payload).hexdigest()


class EnvelopeMismatch(Exception):
    """The run would not be comparable to the frozen one. A refusal, not a warning."""


def _record_may_explain(expected_sha256: str, expected_record: Any,
                        hashed_keys: List[str]) -> Optional[Dict[str, Any]]:
    """Decide whether the stored envelope record has earned the right to name fields.

    The rule the whole feature hangs on: **the digest decides whether the run is accepted;
    the JSON only explains a trusted mismatch.** The record is stored text — it can be
    corrupted, hand-edited, or written by an older schema whose hashing rules differed —
    and a diagnosis built from an untrusted record is a fabricated diagnosis. So before it
    may explain anything: extract exactly the current hashed keys, re-hash them with the
    same canonicalization ``sha256()`` uses, and require the result to equal the digest the
    freeze stored. A record that fails any step gets no say; digest enforcement and the
    generic refusal stand unchanged.
    """
    if not isinstance(expected_record, dict):
        return None
    if expected_record.get("envelope_schema_version") != ENVELOPE_SCHEMA_VERSION:
        # An older writer hashed by different rules; a diff across that boundary would
        # produce confident nonsense.
        return None
    if any(key not in expected_record for key in hashed_keys):
        return None
    extracted = {key: expected_record[key] for key in hashed_keys}
    digest = hashlib.sha256(json.dumps(extracted, sort_keys=True,
                                       separators=(",", ":")).encode("utf-8")).hexdigest()
    return extracted if digest == expected_sha256 else None


def check_envelope(expected_sha256: Optional[str], actual: ExecutionEnvelope,
                   expected_record: Any = None) -> None:
    """Refuse a verification whose execution envelope differs from the frozen one.

    Mirrors the script-hash refusal deliberately: a fix "proven" under a different browser,
    timeout or base URL was not proven against the same experiment, and saying so after the
    fact is worth much less than refusing up front.

    ``expected_record`` is the frozen row's stored envelope JSON, already parsed. When it
    validates against the stored digest (see ``_record_may_explain``), the refusal names
    the FIELDS that moved — names only, never values, because a stored ``base_url`` can
    carry userinfo and ``env_names`` exists precisely because values must not be recorded.
    When it does not validate, the refusal falls back to the digest prefixes.
    """
    if not expected_sha256:
        return
    actual_sha = actual.sha256()
    if actual_sha == expected_sha256:
        return

    actual_payload = actual.hashed_payload()
    trusted = _record_may_explain(expected_sha256, expected_record,
                                  sorted(actual_payload))
    if trusted is not None:
        moved = sorted(key for key in actual_payload
                       if trusted.get(key) != actual_payload.get(key))
        if moved:
            raise EnvelopeMismatch(
                "this run's execution envelope differs from the frozen one on: "
                f"{', '.join(moved)} (this run {actual_sha[:12]}…, frozen "
                f"{expected_sha256[:12]}…). A run under a different configuration is a "
                "different experiment, so the result would not be comparable."
            )
    # The generic refusal. Deliberately does NOT name the diagnostics profile: it is
    # excluded from the hashed payload (see hashed_payload), so a profile difference can
    # never be the cause of this refusal, and a message naming impossible causes sends
    # the developer hunting in the wrong place.
    raise EnvelopeMismatch(
        f"this run's execution envelope ({actual_sha[:12]}…) differs from the frozen "
        f"one ({expected_sha256[:12]}…). The same script under a different browser, "
        "timeout or base URL is a different experiment, so the result would not be "
        "comparable."
    )


def _clip(value: Any, limit: int = MAX_FIELD_CHARS) -> Any:
    if isinstance(value, str) and len(value) > limit:
        return value[:limit] + "…[truncated]"
    return value


@dataclass
class Diagnostics:
    """What the local reproduction run revealed. Bounded, scrubbed, and stamped with the
    posture from provenance() — including that the customer-data status of the
    operator-configured target is not verified."""

    failure_stack: List[str] = field(default_factory=list)
    console_errors: List[str] = field(default_factory=list)
    failed_requests: List[Dict[str, Any]] = field(default_factory=list)
    failure_snapshot: Optional[Dict[str, Any]] = None
    browser: str = ""
    stepstitch_version: str = ""
    app_build: Optional[Dict[str, Any]] = None

    def as_dict(self) -> Dict[str, Any]:
        return {
            **provenance(),
            "failure_stack": [_clip(f) for f in self.failure_stack[:MAX_STACK_FRAMES]],
            "console_errors": [_clip(e) for e in self.console_errors[:MAX_CONSOLE_ERRORS]],
            "failed_requests": self.failed_requests[:MAX_FAILED_REQUESTS],
            "failure_snapshot": self.failure_snapshot,
            "browser": self.browser,
            "stepstitch_version": self.stepstitch_version,
            "app_build": self.app_build,
        }


def scrub_diagnostics(record: Dict[str, Any], redact: Any) -> Dict[str, Any]:
    """Run every string in a diagnostics record through the caller's redactor.

    The reproduction is synthetic, so in principle nothing here is a customer's. In
    practice a developer's own app will happily print a real bearer token into its console
    against a staging database — so this is defence in depth, not a contradiction of the
    provenance stamp. ``redact`` is ``runner.scrub_transcript`` in production use; injected
    so this module stays free of the runner.
    """
    def walk(value: Any) -> Any:
        if isinstance(value, str):
            return redact(value)
        if isinstance(value, list):
            return [walk(v) for v in value]
        if isinstance(value, dict):
            return {k: walk(v) for k, v in value.items()}
        return value

    cleaned = walk(record)
    # Provenance is structural and must survive scrubbing unchanged.
    cleaned.update(provenance())
    return cleaned


# --- reading a Playwright trace -----------------------------------------------------------
# Shapes below were read off a real trace.zip produced by this runner, not from docs:
#   test.trace        -> {"type":"error","message":...,"stack":[{file,line,column}]}
#   0-trace.trace     -> JSONL; {"type":"console","messageType":"error","text":...,"location":…}
#   0-trace.network   -> JSONL; {"type":"resource-snapshot","snapshot":{request,response,time}}

_ANSI = re.compile(r"\x1b\[[0-9;]*m")


def _strip_ansi(text: str) -> str:
    """Playwright colours its failure messages. An agent reading escape codes is worse off."""
    return _ANSI.sub("", text or "")


def _templated(url: str) -> str:
    """Path only, with id-shaped segments templated — the same discipline as the compiler.

    A raw URL can carry an account number in a path segment and a session token in a query
    string. Neither belongs in evidence, and the path *shape* is what a developer needs.
    """
    try:
        parsed = urlparse(url)
    except ValueError:
        return "/"
    out = []
    for segment in (parsed.path or "/").split("/"):
        if not segment:
            continue
        if re.fullmatch(r"\d+", segment) or re.fullmatch(
            r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", segment, re.I
        ) or (len(segment) > 24 and not segment.count(".")):
            out.append(":id")
        else:
            out.append(segment)
    return "/" + "/".join(out)


def _jsonl(blob: bytes) -> List[Dict[str, Any]]:
    events = []
    for line in blob.decode("utf-8", "replace").splitlines():
        try:
            events.append(json.loads(line))
        except ValueError:
            continue
    return events


def parse_trace(trace_path: Path) -> Diagnostics:
    """Turn a Playwright trace into the four signals an agent can act on.

    Deliberately narrow. A trace holds far more than this — screencast frames, DOM
    snapshots, every API call — and shipping all of it would recreate the bloated,
    privacy-hostile artifact this product exists to avoid. Four signals, bounded, then stop.
    """
    diags = Diagnostics()
    with zipfile.ZipFile(trace_path) as archive:
        names = set(archive.namelist())

        # 1. The failure itself. Two very different things live in a trace and only one of
        # them is useful: `test.trace` holds the ASSERTION that failed ("the reported
        # TypeError must not reproduce") with a frame pointing at the generated spec, while
        # the browser's own `pageError` event holds the APPLICATION's exception with a
        # stack pointing into the app's source. Shipping the former as "the failure stack"
        # tells an agent only that a test failed — which it already knew. The real
        # exception is preferred, and the assertion kept as context after it.
        app_error: List[str] = []
        for name in sorted(n for n in names if n.endswith(".trace") and n != "test.trace"):
            for event in _jsonl(archive.read(name)):
                if event.get("type") != "event" or event.get("method") != "pageError":
                    continue
                error = ((event.get("params") or {}).get("error") or {}).get("error") or {}
                stack = _strip_ansi(str(error.get("stack") or ""))
                message = _strip_ansi(str(error.get("message") or ""))
                if stack:
                    app_error = [line.strip() for line in stack.splitlines() if line.strip()]
                elif message:
                    app_error = [message]
                if app_error:
                    break
            if app_error:
                break

        assertion: List[str] = []
        if "test.trace" in names:
            for event in _jsonl(archive.read("test.trace")):
                if event.get("type") != "error":
                    continue
                message = _strip_ansi(str(event.get("message", "")))
                frames = [
                    f"{f.get('file')}:{f.get('line')}:{f.get('column')}"
                    for f in (event.get("stack") or [])
                    if isinstance(f, dict)
                ]
                assertion = ([message] if message else []) + frames
                break

        diags.failure_stack = app_error + assertion

        for name in sorted(names):
            # 2. console ERRORS only — not every log line the app happens to print
            if name.endswith(".trace") and name != "test.trace":
                for event in _jsonl(archive.read(name)):
                    if event.get("type") == "console" and \
                            event.get("messageType") == "error":
                        text = _strip_ansi(str(event.get("text", ""))).strip()
                        if text:
                            diags.console_errors.append(text)
            # 3. failed requests: method, TEMPLATED path, status, duration
            elif name.endswith(".network"):
                for event in _jsonl(archive.read(name)):
                    snap = event.get("snapshot") or {}
                    status = (snap.get("response") or {}).get("status")
                    if not isinstance(status, int) or status < 400:
                        continue
                    diags.failed_requests.append({
                        "method": (snap.get("request") or {}).get("method", ""),
                        "path": _templated((snap.get("request") or {}).get("url", "")),
                        "status": status,
                        "duration_ms": round(float(snap.get("time") or 0.0), 1),
                    })

        # 4. the state at the moment it broke: the last action that touched the PAGE.
        # Deliberately not simply the last event: a trace ends with internal bookkeeping
        # (waitForTimeout, closes), and reporting "the failure happened during
        # waitForTimeout" tells a developer nothing. The last action carrying a selector is
        # the last thing the user's flow actually did.
        for name in sorted(n for n in names if n.endswith(".trace") and n != "test.trace"):
            last_interaction = None
            for event in _jsonl(archive.read(name)):
                if event.get("type") != "before":
                    continue
                selector = (event.get("params") or {}).get("selector", "")
                if event.get("method") and selector:
                    last_interaction = {
                        "action": event.get("method"),
                        "target": selector,
                        # Templated, and named `path` like the sibling structure above: a raw
                        # `url` here would carry the query string the failed-request branch
                        # already refuses to carry, and would put a key named `url` in a
                        # packet that promises it captures none.
                        "path": _templated((event.get("params") or {}).get("url", "")),
                    }
            if last_interaction:
                diags.failure_snapshot = last_interaction
                break

    return diags
