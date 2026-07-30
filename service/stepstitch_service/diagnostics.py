"""Deep evidence from the reproduction — never from the person who reported the bug.

This is the inversion the product rests on. Session-replay tools buy debugging depth by
recording the real user: their screen, their inputs, their page text. StepStitch takes
almost nothing from production, reproduces the failure in a synthetic run on the
developer's own machine, and then inspects *that* execution as deeply as it likes.

> **Minimal evidence from production. Maximum evidence from a controlled reproduction.**

Nothing collected here ever touched a customer. That is a structural fact about where the
data comes from, not a promise about filtering, which is why every record carries
``source: synthetic_reproduction`` and ``contains_customer_session_data: false`` — a reader
should not have to take our word for the distinction, or work out which half of the packet
they are looking at.

**How it is collected.** Playwright *tracing*, parsed after the run — not a reporter. A
reporter receives test results and attachments; it never gets the live ``Page``, so it
cannot see the DOM, the network, or the console. The trace can, and it is produced by the
byte-identical frozen script without that script knowing anything about it.

**The execution envelope.** Freezing the test alone is not enough to make two runs
comparable: *how* the test ran matters too. A different browser build, timeout, base URL or
diagnostics profile can turn the same bytes into a different outcome, and a referee that
only pins the script would be quietly comparing two different experiments. So the envelope
is hashed as well, and a verification run must match on both.
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
# (or a later migration) can tell what it is looking at without guessing.
SCHEMA_VERSION = 1

# The only provenance this module ever emits. Deliberately not a parameter: there is no
# code path that produces a diagnostics record from production traffic, and offering one
# would make the guarantee a configuration option rather than a property.
SOURCE_SYNTHETIC = "synthetic_reproduction"

# Bounds. A diagnostics record is meant to fit in an agent's context beside the rest of the
# packet; an unbounded one would defeat the whole size argument the product makes.
MAX_CONSOLE_ERRORS = 20
MAX_FAILED_REQUESTS = 20
MAX_STACK_FRAMES = 30
MAX_FIELD_CHARS = 2000


def provenance() -> Dict[str, Any]:
    """The stamp every agent-facing diagnostics field carries or inherits."""
    return {
        "source": SOURCE_SYNTHETIC,
        "contains_customer_session_data": False,
        "schema_version": SCHEMA_VERSION,
    }


@dataclass(frozen=True)
class ExecutionEnvelope:
    """*How* the frozen script ran — the other half of a reproducible verdict.

    Env vars appear by NAME only. The names are part of how a run was configured and are
    worth pinning; the values are exactly what must never be recorded.
    """

    config: str                       # the generated repro.config.ts, verbatim
    browser: str                      # e.g. "chromium 141.0.7390.37"
    base_url: str                     # identity of the app under test
    timeout_ms: int
    retries: int
    diagnostics_profile: str          # "off" | "four-signal"
    runner_version: str
    env_names: List[str] = field(default_factory=list)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "config": self.config,
            "browser": self.browser,
            "base_url": self.base_url,
            "timeout_ms": self.timeout_ms,
            "retries": self.retries,
            "diagnostics_profile": self.diagnostics_profile,
            "runner_version": self.runner_version,
            "schema_version": SCHEMA_VERSION,
            "env_names": sorted(self.env_names),
        }

    def sha256(self) -> str:
        """Canonical hash of the envelope, computed the way the attestation is."""
        payload = json.dumps(self.as_dict(), sort_keys=True,
                             separators=(",", ":")).encode("utf-8")
        return hashlib.sha256(payload).hexdigest()


class EnvelopeMismatch(Exception):
    """The run would not be comparable to the frozen one. A refusal, not a warning."""


def check_envelope(expected_sha256: Optional[str], actual: ExecutionEnvelope) -> None:
    """Refuse a verification whose execution envelope differs from the frozen one.

    Mirrors the script-hash refusal deliberately: a fix "proven" under a different browser,
    timeout or base URL was not proven against the same experiment, and saying so after the
    fact is worth much less than refusing up front.
    """
    if not expected_sha256:
        return
    actual_sha = actual.sha256()
    if actual_sha != expected_sha256:
        raise EnvelopeMismatch(
            f"this run's execution envelope ({actual_sha[:12]}…) differs from the frozen "
            f"one ({expected_sha256[:12]}…). The same script under a different browser, "
            "timeout, base URL or diagnostics profile is a different experiment, so the "
            "result would not be comparable."
        )


def _clip(value: Any, limit: int = MAX_FIELD_CHARS) -> Any:
    if isinstance(value, str) and len(value) > limit:
        return value[:limit] + "…[truncated]"
    return value


@dataclass
class Diagnostics:
    """What the synthetic run revealed. Bounded, scrubbed, and stamped with its origin."""

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
                        "url": (event.get("params") or {}).get("url", ""),
                    }
            if last_interaction:
                diags.failure_snapshot = last_interaction
                break

    return diags
