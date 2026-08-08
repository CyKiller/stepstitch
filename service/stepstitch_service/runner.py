"""Execute a compiled reproduction locally, under the frozen security contract.

The contract this satisfies was written before this file existed — see "Local runner
security" in contracts/stepstitch.md. Every MUST there maps to code here and to a test in
``service/tests/test_runner.py``.

Two properties matter most:

**The script is frozen.** A reproduction is compiled once, its bytes hashed, and every
later run must present the byte-identical script. An agent may change application code; it
can never weaken, replace or regenerate the test that judges its fix. A hash mismatch is a
refusal, not a warning.

**StepStitch decides, not the runner's caller.** The verdict is derived here from observed
exit status across N runs. Disagreement between runs is reported as ``inconclusive`` with a
flake flag rather than resolved into a confident answer.

Kept free of FastAPI and of the service router: the CLI must be able to run a reproduction
in an environment that has Node and Playwright but no web stack.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import shutil
import subprocess
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence
from urllib.parse import urlparse

from .diagnostics import (
    Diagnostics,
    ExecutionEnvelope,
    check_envelope,
    parse_trace,
    scrub_diagnostics,
)

logger = logging.getLogger("stepstitch.runner")

# --- verdicts (the four honest answers) ---------------------------------------------------
REPRODUCED = "reproduced"
NEEDS_SETUP = "needs_setup"
NOT_REPRODUCED = "not_reproduced"
INCONCLUSIVE = "inconclusive"

# Pinned into the execution envelope: a runner change can alter how a test behaves, so two
# runs are only comparable when they came from the same runner.
RUNNER_VERSION = "1"

# --- limits -------------------------------------------------------------------------------
DEFAULT_TIMEOUT_SECONDS = 120
MAX_TIMEOUT_SECONDS = 600
MAX_RUNS = 10

# The child process environment is built from this allowlist — never inherited wholesale.
# PATH and the platform's loader variables are required to launch node at all; the rest is
# what Playwright itself reads. Nothing matching a credential shape can appear here.
_ENV_ALLOWLIST = frozenset({
    "PATH", "HOME", "TMPDIR", "TEMP", "TMP",
    "SystemRoot", "COMSPEC", "PATHEXT", "USERPROFILE", "APPDATA", "LOCALAPPDATA",
    "LANG", "LC_ALL", "TZ",
    "NODE_PATH", "npm_config_cache",
    "PLAYWRIGHT_BROWSERS_PATH", "PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD",
    "CI",
})

# Redaction applied to transcripts before they are stored or shown. The scrubber owns the
# ingest boundary; a run transcript is machine output, so this is a narrower, targeted
# sweep for the shapes that leak from a test runner: bearer tokens, URL credentials, and
# anything that looks like an assignment to a secret-ish name.
_TRANSCRIPT_PATTERNS: Sequence[tuple[re.Pattern[str], str]] = (
    (re.compile(r"(?i)\b(bearer)\s+[A-Za-z0-9._\-]{8,}"), r"\1 [redacted]"),
    (re.compile(r"(?i)\b([A-Za-z0-9_]*(?:token|secret|password|passwd|api[_-]?key|"
                r"credential)[A-Za-z0-9_]*)\s*[=:]\s*\S+"), r"\1=[redacted]"),
    (re.compile(r"://[^/\s:@]+:[^/\s@]+@"), "://[redacted]@"),
    (re.compile(r"\bssa_[A-Za-z0-9._\-]{8,}"), "[redacted:agent-token]"),
)


class RunnerError(Exception):
    """A refusal: the run must not proceed as asked."""


@dataclass(frozen=True)
class BrowserIdentity:
    """What browser this machine would actually launch, and whether it is there.

    ``present`` is a TRI-STATE on purpose. ``None`` means "could not ask" — an unusual
    layout (pnpm, Yarn PnP), no Node, a probe that would not parse. Collapsing that into
    ``False`` would refuse runs on machines that work fine, which is a worse failure than
    the one this guards.
    """
    build: str = "unknown"
    install_location: str = ""
    present: Optional[bool] = None


# "Chrome Headless Shell 149.0.7827.55 (playwright chromium-headless-shell v1228)"
_BROWSER_ENTRY = re.compile(
    r"^(?P<title>.+?)\s+(?P<version>\d[\d.]*)\s+"
    r"\(playwright\s+(?P<name>chromium(?:-headless-shell)?)\s+v(?P<rev>\d+)\)\s*$")


def _browser_identity(headless: bool = True) -> BrowserIdentity:
    """The browser identity that goes in the envelope, asked of Playwright itself.

    This used to run ``playwright --version``, which reports the **npm package** version
    ("Version 1.61.0") — not the browser. That made the envelope's browser field a lie in
    both directions: ``npx playwright install chromium`` pulling a new Chromium left the
    string unchanged, and the string stayed healthy when the browser was absent entirely.
    ``install --dry-run`` costs the same (~0.8s, no network) and answers honestly.

    ``headless`` picks WHICH entry to believe, and it matters more than it looks. With
    ``headless: true`` Playwright ≥1.49 launches the **headless shell**, a separate download
    from full Chromium. A machine can legitimately have the shell for the pinned revision
    and not the full browser — that is the state of the machine this was written on — so
    checking the full-Chromium path would declare a working install broken and refuse every
    run. Keyed off the config spec rather than a constant, so it follows if that changes.

    Never raises. A failure to answer is "unknown" with ``present=None``: refusing to run
    because a version string would not parse is worse than the risk it guards.
    """
    try:
        proc = subprocess.run(
            ["npx", "--no-install", "playwright", "install", "chromium", "--dry-run"],
            capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.SubprocessError):
        return BrowserIdentity()
    if proc.returncode != 0:
        return BrowserIdentity()

    wanted = "chromium-headless-shell" if headless else "chromium"
    entry: Optional[re.Match[str]] = None
    location = ""
    for line in (proc.stdout or "").splitlines():
        matched = _BROWSER_ENTRY.match(line.strip())
        if matched:
            entry = matched if matched.group("name") == wanted else None
            continue
        if entry and line.strip().startswith("Install location:"):
            location = line.split(":", 1)[1].strip()
            break
    if entry is None or not location:
        return BrowserIdentity()

    build = f"chromium {entry.group('version')} (playwright build {entry.group('rev')})"
    try:
        present = Path(location).exists()
    except OSError:
        present = None
    return BrowserIdentity(build=build[:60], install_location=location, present=present)


def _collect_diagnostics(artifacts_dir: Path) -> Optional["Diagnostics"]:
    """Find the trace Playwright kept and read the four signals out of it.

    Returns None rather than raising when there is nothing to read: a passing run keeps no
    trace (``retain-on-failure``), and a diagnostics failure must never turn a good verdict
    into an error. The verdict is the product; diagnostics are the extra.
    """
    try:
        traces = sorted(artifacts_dir.rglob("trace.zip"))
    except OSError:
        return None
    if not traces:
        return None
    try:
        return parse_trace(traces[0])
    except Exception:
        logger.warning("stepstitch: could not read the reproduction trace", exc_info=True)
        return None


def script_digest(script: str) -> str:
    """The freeze: sha256 over the exact bytes that will be executed."""
    return hashlib.sha256(script.encode("utf-8")).hexdigest()


def scrub_transcript(text: str) -> str:
    for pattern, replacement in _TRANSCRIPT_PATTERNS:
        text = pattern.sub(replacement, text)
    return text


# A URL's PII is its query string; its path is the evidence. The full scrubber's `url`
# rule deletes the whole thing, which in a stack frame is the file and line — the exact
# detail that lets an agent open the right file without searching. Strip the query, keep
# the location.
_QUERY_STRING = re.compile(r"(\b[a-z][a-z0-9+.-]*://[^\s?#]+)\?\S*", re.I)


def _diagnostics_redactor(text: str) -> str:
    """The redactor a diagnostics record actually deserves: credentials AND free-text PII.

    ``scrub_transcript`` alone was the whole story here for one release, and it is a
    credentials scrubber — bearer tokens, secret-shaped assignments, URL userinfo, agent
    tokens. No raw values patterns. But ``console_errors`` and ``failure_stack`` carry whatever
    the application printed, and an app run against a staging backend will happily
    ``console.error`` a real email, phone number or card. So every string gets the
    server-side scrubber's PII rules too — email, ssn, card, phone, dates, long digit
    runs — the same bar the ingest path holds production traffic to.

    What this buys is ``content_scrubbed: true`` in the provenance stamp, and nothing
    stronger. Patterns cannot prove a name or a postal address absent, which is why the
    stamp says ``customer_data_status: not_verified`` instead of the absolute claim an
    earlier version made. Scrubbing here is defence in depth, not a guarantee.

    One deliberate difference from the ingest scrubber: its ``url`` rule is replaced by a
    query-string strip. Deleting whole URLs from a stack frame deletes the file and line —
    ``transfer.js:9`` is precisely what an agent needs and is not PII — while the query
    string (``?session=…``, ``?email=…``) is where a URL actually leaks and is removed.
    """
    from .scrubber import _PII_PATTERNS

    text = scrub_transcript(text)
    text = _QUERY_STRING.sub(r"\1?[redacted:query]", text)
    for label, pattern in _PII_PATTERNS:
        if label == "url":
            continue
        text = pattern.sub(f"[redacted:{label}]", text)
    return text


def child_env(base: Optional[Dict[str, str]] = None,
              extra: Optional[Dict[str, str]] = None) -> Dict[str, str]:
    """Build the child environment from the allowlist, plus explicit extras.

    ``extra`` is for values the runner itself decides (the app base URL, Playwright's
    browser path). Caller-supplied secrets have no route into this dictionary.
    """
    source = os.environ if base is None else base
    env = {k: v for k, v in source.items() if k in _ENV_ALLOWLIST}
    env.update(extra or {})
    return env


def check_address_allowed(url: str, allowed: Sequence[str]) -> None:
    """Refuse a reproduction pointed anywhere the operator did not name.

    Compares scheme+host+port, so a path or query cannot smuggle a different destination.
    """
    if not allowed:
        raise RunnerError(
            "no application address is configured, so there is nowhere safe to run this "
            "reproduction. Set STEPSTITCH_APP_BASE_URL (or a per-project base_url)."
        )
    target = urlparse(url)
    for candidate in allowed:
        permitted = urlparse(candidate)
        if (target.scheme, target.hostname, target.port) == (
            permitted.scheme, permitted.hostname, permitted.port
        ):
            return
    raise RunnerError(
        f"reproduction targets {target.scheme}://{target.netloc}, which is not an "
        f"allowed address ({', '.join(allowed)})."
    )


@dataclass
class RunAttempt:
    """One execution of the frozen script.

    ``errored`` separates "the reproduction ran and the app misbehaved" from "the
    reproduction never ran". Both exit non-zero, and conflating them would let a broken
    toolchain masquerade as a reproduced bug — the exact dishonesty this product exists to
    prevent.
    """
    index: int
    exit_code: Optional[int]
    passed: bool
    timed_out: bool
    duration_seconds: float
    transcript: str = ""
    errored: bool = False
    error_detail: str = ""


@dataclass
class ReproductionResult:
    """What StepStitch observed — never what a caller asserted."""
    verdict: str
    session_id: str
    script_sha256: str
    runs: List[RunAttempt] = field(default_factory=list)
    flaky: bool = False
    readiness: List[Dict[str, Any]] = field(default_factory=list)
    detail: str = ""
    cancelled: bool = False
    execution_envelope_sha256: str = ""
    # The full envelope record (ExecutionEnvelope.as_dict), so the freeze can store it and
    # a later refusal can say WHICH field moved instead of quoting two hex prefixes.
    # `config_canonical` inside it is a JSON *string*, deliberately: this dict crosses HTTP
    # verbatim, and a nested spec would put keys like `use.screenshot` in payloads that
    # key-walking privacy gates (scripts/demo_agent_loop.py) reject by name.
    execution_envelope: Optional[Dict[str, Any]] = None
    diagnostics: Optional[Dict[str, Any]] = None

    @property
    def blockers(self) -> List[Dict[str, Any]]:
        """Unready items that prevent a correct run (not merely unconfigured ones)."""
        return [item for item in self.readiness
                if not item.get("ready") and item.get("blocking", True)]

    @property
    def advisories(self) -> List[Dict[str, Any]]:
        """Unready but non-blocking — worth saying, never worth refusing over."""
        return [item for item in self.readiness
                if not item.get("ready") and not item.get("blocking", True)]

    def as_dict(self) -> Dict[str, Any]:
        return {
            "verdict": self.verdict,
            "session_id": self.session_id,
            "script_sha256": self.script_sha256,
            "flaky": self.flaky,
            "cancelled": self.cancelled,
            "detail": self.detail,
            "execution_envelope_sha256": self.execution_envelope_sha256,
            "execution_envelope": self.execution_envelope,
            "diagnostics": self.diagnostics,
            "advisories": self.advisories,
            "runs": [
                {
                    "index": r.index, "exit_code": r.exit_code, "passed": r.passed,
                    "timed_out": r.timed_out, "errored": r.errored,
                    "error_detail": r.error_detail,
                    "duration_seconds": round(r.duration_seconds, 3),
                }
                for r in self.runs
            ],
            "blockers": self.blockers,
        }


def derive_verdict(attempts: Sequence[RunAttempt]) -> tuple[str, bool]:
    """Map observed outcomes onto the four answers. Returns ``(verdict, flaky)``.

    A reproduction *fails* when the bug is present: the generated test asserts the working
    behavior, so a failing test means the failure reproduced. Mixed results across runs
    are never resolved into a confident answer.
    """
    if not attempts:
        return INCONCLUSIVE, False
    if any(a.errored for a in attempts):
        # The test never ran. That is a fact about the toolchain, not about the app.
        return INCONCLUSIVE, False
    if any(a.timed_out for a in attempts):
        # A timeout is not evidence of either outcome.
        return INCONCLUSIVE, len({a.passed for a in attempts}) > 1
    outcomes = {a.passed for a in attempts}
    if len(outcomes) > 1:
        return INCONCLUSIVE, True
    # passed == the app behaved correctly == the failure did NOT reproduce.
    return (NOT_REPRODUCED if outcomes.pop() else REPRODUCED), False


# Markers that mean the test never ran. Playwright exits 1 both when a test fails and
# when the config or its imports blow up, so the exit code alone cannot tell the two
# apart — and treating the second as "the bug reproduced" would be a lie.
#
# The second group is the browser itself. It was missing for a long time, and the omission
# was expensive: a purged or never-installed Chromium prints its launch error AND a "1
# failed" summary, so the summary regex below matched, `errored` stayed False, and a broken
# toolchain was reported as a reproduced application bug. Worse on the freeze path, where it
# would record a red baseline whose signature is `Error: browserType.launch: …` — a referee
# that never refereed. `fixcheck` has always reserved `unable_to_verify` for "a broken
# toolchain"; until these markers existed, that branch was unreachable for the single most
# common toolchain break there is.
_NEVER_RAN_MARKERS = (
    "Cannot find module",
    "Error: No tests found",
    "no tests found",
    "Playwright Test did not expect",
    "SyntaxError",
    "Cannot find package",
    "Requiring the config",
    "Error: Cannot find",
    # The browser. `browserType.launch:` is deliberately broad — it also covers missing
    # system libraries and a corrupt profile, all of which mean the test never ran. Matching
    # is a substring over the whole transcript, so a test whose NAME contained one of these
    # would trip it; that is the accepted cost of not calling a dead toolchain a bug.
    "Executable doesn't exist at",
    "browserType.launch:",
    "Looks like Playwright Test or Playwright was just installed or updated",
    "npx playwright install",
    "Host system is missing dependencies",
)


def classify_run(exit_code: Optional[int], output: str) -> tuple[bool, bool, str]:
    """Return ``(passed, errored, error_detail)`` for one execution.

    Evidence that a test actually ran is required before an exit code is read as a
    statement about the application: Playwright prints a run summary ("1 passed",
    "1 failed") only when it got that far.
    """
    text = output or ""
    if exit_code == 0:
        return True, False, ""
    for marker in _NEVER_RAN_MARKERS:
        if marker in text:
            line = next((ln.strip() for ln in text.splitlines()
                         if marker in ln), marker)
            return False, True, line[:200]
    ran = re.search(r"\b\d+\s+(passed|failed|flaky|did not run|skipped)\b", text)
    if not ran:
        first = next((ln.strip() for ln in text.splitlines() if ln.strip()), "")
        return False, True, (first[:200] or
                             f"the reproduction produced no test results (exit {exit_code})")
    return False, False, ""


# The scratch paths, as they appear in the CANONICAL spec. Real absolute paths are
# substituted only when the file is rendered. See _config_spec.
_TESTS_PLACEHOLDER = "<scratch>/tests"
_OUT_PLACEHOLDER = "<scratch>/artifacts"


def _config_spec(base_url: str, timeout_ms: int, screenshots: bool,
                 diagnostics: bool = False) -> Dict[str, Any]:
    """The reproduction's configuration as DATA, with paths as fixed placeholders.

    This exists because the execution envelope has to hash something stable. It used to hash
    the rendered config text, which embeds the ``mkdtemp`` scratch directory — so the digest
    changed on every single run and was a run nonce wearing a fingerprint's name. Nothing
    could ever match it, which is why the envelope check was dead code in production.

    Hashing the spec rather than a hand-listed set of scalars is deliberate: a hand-listed
    set silently stops covering the config the day someone adds a knob here and forgets to
    add it there. This is fail-closed — a new key enters the hash automatically, and a path
    can never leak back in because the spec never holds one.

    ``diagnostics`` turns on Playwright TRACING, which is how deep evidence is collected:
    the trace carries actions, DOM snapshots, console output, network activity and timings,
    and it is produced without the frozen script knowing anything about it. That matters —
    instrumenting the test itself would move its hash and silently kill the referee
    property. Everything here lives in the config, so the script stays byte-identical.
    """
    use: Dict[str, Any] = {"headless": True, "baseURL": base_url}
    if screenshots:
        # Only ever StepStitch's own local reproduction run — never the reported
        # session — stored locally beside the run record, and off by default. What the
        # screenshot shows is the operator-configured application's own rendering.
        use["screenshot"] = "only-on-failure"
    if diagnostics:
        # Retained on failure only: a passing run has nothing to diagnose, and traces are
        # large. The file stays local and short-lived; it is never exposed over MCP.
        use["trace"] = "retain-on-failure"
    return {
        # Artifacts belong in the runner's own scratch dir. Playwright's default outputDir
        # is relative to the config's rootDir, and because the runner must run from the
        # project (so Node can resolve @playwright/test), that default writes trace.zip and
        # screenshots into the DEVELOPER'S repository — surprising, and outside the
        # lifecycle the runner manages.
        "testDir": _TESTS_PLACEHOLDER,
        "outputDir": _OUT_PLACEHOLDER,
        "timeout": int(timeout_ms),
        "retries": 0,
        "workers": 1,
        "use": use,
    }


def canonical_spec(spec: Dict[str, Any]) -> str:
    """The spec as the bytes that get hashed: sorted keys, no incidental whitespace."""
    return json.dumps(spec, sort_keys=True, separators=(",", ":"))


def _render_config(spec: Dict[str, Any], tests_dir: Path, output_dir: Path) -> str:
    """Substitute the real scratch paths and emit the file. Values are JSON-encoded,
    never string-concatenated into code."""
    rendered = dict(spec)
    rendered["testDir"] = str(tests_dir)
    rendered["outputDir"] = str(output_dir)
    body = "".join(f"  {key}: {json.dumps(value)},\n" for key, value in rendered.items())
    return ('import { defineConfig } from "@playwright/test"\n'
            "export default defineConfig({\n" + body + "})\n")


def run_reproduction(
    *,
    session_id: str,
    script: str,
    base_url: str,
    allowed_addresses: Optional[Sequence[str]] = None,
    expected_sha256: Optional[str] = None,
    readiness: Optional[List[Dict[str, Any]]] = None,
    runs: int = 1,
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
    screenshots: bool = False,
    diagnostics: bool = False,
    expected_envelope_sha256: Optional[str] = None,
    # The frozen row's stored envelope record, parsed. Purely explanatory: check_envelope
    # validates it against the digest before letting it name fields, and the digest alone
    # decides acceptance. None (legacy row, malformed JSON) degrades to the prefix message.
    expected_envelope_record: Optional[Dict[str, Any]] = None,
    work_root: Optional[Path] = None,
    project_dir: Optional[Path] = None,
    should_cancel: Optional[Callable[[], bool]] = None,
    runner: Optional[Callable[..., subprocess.CompletedProcess]] = None,
    # Same kind of seam as `runner`, and for the same reason. The browser probe shells out
    # to the real machine, so without a seam every test that fakes execution still depends
    # on whether THIS machine happens to have Chromium installed — and a machine with npx
    # but no browser (npm install run, `npx playwright install` not) sent 21 fake-execution
    # tests into the NEEDS_SETUP return below, never reaching the code they exist to test.
    browser_probe: Optional[Callable[..., BrowserIdentity]] = None,
) -> ReproductionResult:
    """Execute ``script`` up to ``runs`` times and report what was observed.

    ``expected_sha256`` enforces the freeze: a mismatch refuses the run outright.
    ``should_cancel`` is polled between runs so a surface can abort in flight.
    """
    digest = script_digest(script)
    if expected_sha256 and expected_sha256 != digest:
        raise RunnerError(
            "this is not the frozen reproduction for this session (script hash "
            f"{digest[:12]}… does not match the recorded {expected_sha256[:12]}…). "
            "Verification runs the byte-identical script that was frozen, so the test "
            "cannot be regenerated or edited between runs."
        )

    readiness = list(readiness or [])
    # Only items that make the run *wrong* stop it. An unconfigured auth fixture is not one
    # of those — plenty of flows need no session, and refusing them would be a false
    # blocker that makes "needs setup" meaningless. repro_config declares which is which.
    run_count = max(1, min(int(runs), MAX_RUNS))
    timeout = max(1, min(int(timeout_seconds), MAX_TIMEOUT_SECONDS))
    execute = runner or subprocess.run

    # The envelope is built BEFORE anything touches the filesystem, which is possible only
    # because the spec no longer needs the scratch paths. Two bugs fall out of that ordering
    # for free: a mismatch now refuses without having created a scratch directory it would
    # then leak (check_envelope used to fire after mkdtemp and outside the try/finally), and
    # nothing is spawned on a machine that cannot spawn it.
    spec = _config_spec(base_url, timeout * 1000, screenshots, diagnostics=diagnostics)
    probe = browser_probe or _browser_identity
    identity = probe(headless=bool(spec["use"].get("headless", True)))

    # The observers are stripped from what gets hashed, for the reason argued at length in
    # ExecutionEnvelope.hashed_payload: red traces, green does not, and hashing that
    # difference would refuse every verification that ever runs.
    hashable = dict(spec)
    hashable["use"] = {k: v for k, v in spec["use"].items()
                       if k not in ("trace", "screenshot")}
    envelope = ExecutionEnvelope(
        config_canonical=canonical_spec(hashable),
        browser=identity.build,
        base_url=base_url,
        timeout_ms=timeout * 1000,
        retries=0,
        diagnostics_profile="four-signal" if diagnostics else "off",
        runner_version=RUNNER_VERSION,
        env_names=sorted(_ENV_ALLOWLIST),
    )
    check_envelope(expected_envelope_sha256, envelope,
                   expected_record=expected_envelope_record)

    # An absent browser is a prerequisite, and it is knowable BEFORE running — so it is
    # NEEDS_SETUP with the exact fix, not an INCONCLUSIVE the developer has to decode after
    # a run that was doomed. Strictly `is False`: `None` means the probe could not answer,
    # and refusing runs over an unanswerable question would break working machines (pnpm,
    # Yarn PnP) to guard broken ones. This lives here, not in repro_config.readiness() —
    # that function is pure, and a dashboard GET must not shell out.
    readiness = list(readiness)
    if identity.present is False:
        readiness.append({
            "id": "browser", "ready": False, "blocking": True,
            "title": "Playwright browser",
            "detail": (f"{identity.build} is not installed"
                       f" (expected at {identity.install_location})."
                       " Run: npx playwright install chromium"),
        })

    blockers = [item for item in readiness
                if not item.get("ready") and item.get("blocking", True)]
    if blockers:
        # Do not run a reproduction that is known to be unrunnable: the honest answer is
        # the exact missing prerequisite, not a failure the developer has to decode.
        # No envelope digest on purpose: a digest for a run that never happened is noise.
        return ReproductionResult(
            verdict=NEEDS_SETUP, session_id=session_id, script_sha256=digest,
            readiness=readiness,
            detail="; ".join(f"{b.get('title')}: {b.get('detail')}" for b in blockers),
        )

    check_address_allowed(base_url, list(allowed_addresses or [base_url]))

    # A fixed working directory the runner chooses; the reproduction cannot select paths.
    # It defaults to a scratch dir INSIDE the project, because Node resolves
    # `@playwright/test` by walking up from the config's location — a system temp dir has
    # no node_modules above it, and the resulting module error would otherwise be read as
    # a failing test.
    # `.absolute()`, because the config records testDir as text and Playwright resolves a
    # relative testDir against the CONFIG's directory, not the cwd — so a relative project
    # dir yields a doubled path and "No tests found", which the runner then correctly but
    # unhelpfully reports as `inconclusive`. Python 3.12's tempfile.mkdtemp absolutises its
    # return value and 3.11's does not, so this failed only on the older interpreter: CI.
    # Left as `.absolute()` rather than `.resolve()` deliberately — resolving symlinks would
    # rewrite /tmp to /private/tmp on macOS and move the envelope hash for existing callers.
    project = Path(project_dir or Path.cwd()).absolute()
    default_root = project / ".stepstitch"
    default_root.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix="repro-",
                                 dir=str(work_root) if work_root else str(default_root)))
    tests_dir = work / "tests"
    tests_dir.mkdir(parents=True)
    spec_path = tests_dir / "repro.spec.ts"
    spec_path.write_text(script, encoding="utf-8")
    config_path = work / "repro.config.ts"
    artifacts_dir = work / "artifacts"
    config_path.write_text(_render_config(spec, tests_dir, artifacts_dir), encoding="utf-8")

    env = child_env(extra={"STEPSTITCH_APP_BASE_URL": base_url})
    # Fixed argv — never a shell string, and no capsule text is interpolated into it.
    argv = ["npx", "--no-install", "playwright", "test",
            "--config", str(config_path), "--reporter=line"]
    # Playwright resolves @playwright/test by walking up from cwd; the project dir is the
    # runner's choice, never the capsule's.
    cwd = str(project)

    attempts: List[RunAttempt] = []
    cancelled = False
    diagnostics_record: Optional[Dict[str, Any]] = None
    try:
        for index in range(run_count):
            if should_cancel and should_cancel():
                cancelled = True
                break
            started = time.monotonic()
            timed_out = False
            exit_code: Optional[int] = None
            output = ""
            try:
                completed = execute(
                    argv, cwd=cwd, env=env, capture_output=True, text=True,
                    timeout=timeout, shell=False,
                )
                exit_code = completed.returncode
                output = (completed.stdout or "") + (completed.stderr or "")
            except subprocess.TimeoutExpired as exc:
                # subprocess.run kills the child on timeout; record it as neither outcome.
                timed_out = True
                output = _decode(exc.stdout) + _decode(exc.stderr) + "\n[timed out]"
            except FileNotFoundError as exc:
                raise RunnerError(
                    "could not launch Playwright (npx not found). Install Node 18+ and "
                    "`npm i -D @playwright/test`, or run `stepstitch doctor`."
                ) from exc
            if timed_out:
                passed, errored, error_detail = False, False, ""
            else:
                passed, errored, error_detail = classify_run(exit_code, output)
            attempts.append(RunAttempt(
                index=index,
                exit_code=exit_code,
                passed=passed,
                timed_out=timed_out,
                duration_seconds=time.monotonic() - started,
                transcript=scrub_transcript(output),
                errored=errored,
                error_detail=scrub_transcript(error_detail),
            ))
        # Read the trace BEFORE the scratch dir goes away. The record is scrubbed here
        # and persisted by the caller; the raw trace never outlives this block, and is
        # never exposed over MCP.
        if diagnostics:
            collected = _collect_diagnostics(artifacts_dir)
            if collected is not None:
                collected.browser = envelope.browser
                collected.stepstitch_version = RUNNER_VERSION
                diagnostics_record = scrub_diagnostics(collected.as_dict(),
                                                       _diagnostics_redactor)
    finally:
        if not screenshots:
            shutil.rmtree(work, ignore_errors=True)

    verdict, flaky = derive_verdict(attempts)
    envelope_sha = envelope.sha256()
    if cancelled:
        verdict, flaky = INCONCLUSIVE, flaky
    result = ReproductionResult(
        verdict=verdict, session_id=session_id, script_sha256=digest,
        runs=attempts, flaky=flaky, readiness=readiness, cancelled=cancelled,
        execution_envelope_sha256=envelope_sha, execution_envelope=envelope.as_dict(),
        diagnostics=diagnostics_record,
    )
    result.detail = _explain(result)
    return result


def _decode(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", "replace")
    return str(value)


def _explain(result: ReproductionResult) -> str:
    n = len(result.runs)
    plural = "" if n == 1 else "s"
    if result.cancelled:
        return f"cancelled after {n} run{plural}; no verdict was reached."
    if result.verdict == REPRODUCED:
        return f"the failure happened again in {n} of {n} run{plural}."
    if result.verdict == NOT_REPRODUCED:
        return (f"the application behaved correctly in {n} of {n} run{plural} — this "
                "evidence does not reproduce the failure here.")
    if result.verdict == INCONCLUSIVE:
        errored = next((r for r in result.runs if r.errored), None)
        if errored is not None:
            return ("the reproduction never ran, so nothing was learned about the "
                    f"application: {errored.error_detail}")
        if any(r.timed_out for r in result.runs):
            return "a run exceeded the time limit, so neither outcome was observed."
        failed = sum(1 for r in result.runs if not r.passed)
        return (f"the failure happened in {failed} of {n} runs — that is a flaky "
                "reproduction, not a reliable one.")
    return ""
