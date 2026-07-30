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

# --- verdicts (the four honest answers) ---------------------------------------------------
REPRODUCED = "reproduced"
NEEDS_SETUP = "needs_setup"
NOT_REPRODUCED = "not_reproduced"
INCONCLUSIVE = "inconclusive"

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


def script_digest(script: str) -> str:
    """The freeze: sha256 over the exact bytes that will be executed."""
    return hashlib.sha256(script.encode("utf-8")).hexdigest()


def scrub_transcript(text: str) -> str:
    for pattern, replacement in _TRANSCRIPT_PATTERNS:
        text = pattern.sub(replacement, text)
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
_NEVER_RAN_MARKERS = (
    "Cannot find module",
    "Error: No tests found",
    "no tests found",
    "Playwright Test did not expect",
    "SyntaxError",
    "Cannot find package",
    "Requiring the config",
    "Error: Cannot find",
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


def _playwright_config(tests_dir: Path, base_url: str, timeout_ms: int,
                       screenshots: bool) -> str:
    """A minimal config. Values are JSON-encoded, never string-concatenated into code."""
    use: Dict[str, Any] = {"headless": True, "baseURL": base_url}
    if screenshots:
        # Only ever the synthetic run, stored locally beside the run record.
        use["screenshot"] = "only-on-failure"
    return (
        'import { defineConfig } from "@playwright/test"\n'
        "export default defineConfig({\n"
        f"  testDir: {json.dumps(str(tests_dir))},\n"
        f"  timeout: {int(timeout_ms)},\n"
        "  retries: 0,\n"
        "  workers: 1,\n"
        f"  use: {json.dumps(use)},\n"
        "})\n"
    )


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
    work_root: Optional[Path] = None,
    project_dir: Optional[Path] = None,
    should_cancel: Optional[Callable[[], bool]] = None,
    runner: Optional[Callable[..., subprocess.CompletedProcess]] = None,
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
    blockers = [item for item in readiness
                if not item.get("ready") and item.get("blocking", True)]
    if blockers:
        # Do not run a reproduction that is known to be unrunnable: the honest answer is
        # the exact missing prerequisite, not a failure the developer has to decode.
        return ReproductionResult(
            verdict=NEEDS_SETUP, session_id=session_id, script_sha256=digest,
            readiness=readiness,
            detail="; ".join(f"{b.get('title')}: {b.get('detail')}" for b in blockers),
        )

    check_address_allowed(base_url, list(allowed_addresses or [base_url]))

    run_count = max(1, min(int(runs), MAX_RUNS))
    timeout = max(1, min(int(timeout_seconds), MAX_TIMEOUT_SECONDS))
    execute = runner or subprocess.run

    # A fixed working directory the runner chooses; the reproduction cannot select paths.
    # It defaults to a scratch dir INSIDE the project, because Node resolves
    # `@playwright/test` by walking up from the config's location — a system temp dir has
    # no node_modules above it, and the resulting module error would otherwise be read as
    # a failing test.
    project = Path(project_dir or Path.cwd())
    default_root = project / ".stepstitch"
    default_root.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix="repro-",
                                 dir=str(work_root) if work_root else str(default_root)))
    tests_dir = work / "tests"
    tests_dir.mkdir(parents=True)
    spec_path = tests_dir / "repro.spec.ts"
    spec_path.write_text(script, encoding="utf-8")
    config_path = work / "repro.config.ts"
    config_path.write_text(
        _playwright_config(tests_dir, base_url, timeout * 1000, screenshots),
        encoding="utf-8",
    )

    env = child_env(extra={"STEPSTITCH_APP_BASE_URL": base_url})
    # Fixed argv — never a shell string, and no capsule text is interpolated into it.
    argv = ["npx", "--no-install", "playwright", "test",
            "--config", str(config_path), "--reporter=line"]
    # Playwright resolves @playwright/test by walking up from cwd; the project dir is the
    # runner's choice, never the capsule's.
    cwd = str(project)

    attempts: List[RunAttempt] = []
    cancelled = False
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
    finally:
        if not screenshots:
            shutil.rmtree(work, ignore_errors=True)

    verdict, flaky = derive_verdict(attempts)
    if cancelled:
        verdict, flaky = INCONCLUSIVE, flaky
    result = ReproductionResult(
        verdict=verdict, session_id=session_id, script_sha256=digest,
        runs=attempts, flaky=flaky, readiness=readiness, cancelled=cancelled,
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
