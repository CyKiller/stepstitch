"""The local runner: every MUST in contracts/stepstitch.md "Local runner security".

The contract was written in Phase 0, before the runner existed, precisely so these could
be tests rather than intentions. Playwright is never actually launched here — a fake
subprocess runner stands in — so the security properties are provable on any machine.
"""
import json
import os
import re
import subprocess
from pathlib import Path

import pytest

from stepstitch_service.diagnostics import EnvelopeMismatch
from stepstitch_service.runner import (
    INCONCLUSIVE,
    MAX_RUNS,
    NEEDS_SETUP,
    NOT_REPRODUCED,
    REPRODUCED,
    BrowserIdentity,
    RunnerError,
    check_address_allowed,
    child_env,
    run_reproduction,
    script_digest,
    scrub_transcript,
)

SCRIPT = 'import { test } from "@playwright/test"\ntest("repro", async () => {})\n'
BASE = "http://127.0.0.1:3000"
READY = [{"id": "base_url", "ready": True, "title": "Application base URL",
          "detail": "points at http://127.0.0.1:3000"}]


def fake_runner(exit_codes, calls=None, raises=None):
    """Stands in for subprocess.run: returns the given exit code per call.

    Emits a real Playwright run summary, because the runner requires evidence that a test
    actually ran before reading an exit code as a statement about the application.
    """
    codes = list(exit_codes)

    def run(argv, **kwargs):
        if calls is not None:
            calls.append((argv, kwargs))
        if raises:
            raise raises
        code = codes.pop(0) if codes else 0
        summary = "  1 passed (1.2s)\n" if code == 0 else "  1 failed\n"
        return subprocess.CompletedProcess(argv, code, stdout=summary, stderr="")

    return run


def fake_browser(present=True, build="chromium 151.0.7922.34 (playwright build 1234)",
                 location="/fake-cache/ms-playwright/chromium_headless_shell-1234"):
    """Stands in for the browser probe, which otherwise shells out to the real machine.

    Without this the promise in this module's docstring — provable on ANY machine — is
    false. The probe runs `npx playwright install --dry-run`, so on a machine that has npx
    but no Chromium (npm install done, `npx playwright install` not: a normal developer
    state, and the state of a clean CI container) every test below refused at the readiness
    gate with NEEDS_SETUP and never reached the fake runner it exists to exercise.

    Tests that are ABOUT the probe pass their own instead of relying on this default.
    """
    def probe(headless=True):
        return BrowserIdentity(build=build, install_location=location, present=present)

    return probe


def _run(**overrides):
    params = dict(session_id="s-1", script=SCRIPT, base_url=BASE, readiness=READY,
                  runner=fake_runner([0]), browser_probe=fake_browser())
    params.update(overrides)
    return run_reproduction(**params)


# --- the four honest answers ---------------------------------------------------------------

def test_a_failing_test_means_the_failure_reproduced():
    # The generated test asserts the WORKING behavior, so non-zero == bug is present.
    result = _run(runner=fake_runner([1]))
    assert result.verdict == REPRODUCED
    assert "happened again" in result.detail


def test_a_passing_test_means_it_did_not_reproduce_here():
    result = _run(runner=fake_runner([0]))
    assert result.verdict == NOT_REPRODUCED
    assert "behaved correctly" in result.detail


def test_disagreement_across_runs_is_inconclusive_and_flagged_flaky():
    result = _run(runs=4, runner=fake_runner([1, 0, 1, 1]))
    assert result.verdict == INCONCLUSIVE
    assert result.flaky is True
    assert "flaky" in result.detail
    assert "1 of 4" not in result.detail    # it reports 3 of 4, the real count
    assert "3 of 4" in result.detail


def test_a_timeout_is_neither_outcome():
    def timing_out(argv, **kwargs):
        raise subprocess.TimeoutExpired(argv, kwargs.get("timeout", 1))

    result = _run(runner=timing_out)
    assert result.verdict == INCONCLUSIVE
    assert result.runs[0].timed_out is True
    assert "time limit" in result.detail


def test_missing_prerequisites_are_named_instead_of_run():
    calls = []
    result = _run(
        readiness=[{"id": "base_url", "ready": False, "title": "Application base URL",
                    "detail": "set STEPSTITCH_APP_BASE_URL"}],
        runner=fake_runner([1], calls),
    )
    assert result.verdict == NEEDS_SETUP
    assert "set STEPSTITCH_APP_BASE_URL" in result.detail
    assert calls == []          # nothing was executed — the answer was already known
    assert result.blockers and result.blockers[0]["id"] == "base_url"


# --- the freeze (the referee property) -----------------------------------------------------

def test_a_modified_script_is_refused_not_warned_about():
    frozen = script_digest(SCRIPT)
    edited = SCRIPT.replace("async () => {}", "async () => { /* weakened */ }")
    with pytest.raises(RunnerError) as exc:
        _run(script=edited, expected_sha256=frozen)
    message = str(exc.value)
    assert "not the frozen reproduction" in message
    assert "byte-identical" in message


def test_the_frozen_script_runs_and_reports_its_digest():
    result = _run(expected_sha256=script_digest(SCRIPT))
    assert result.script_sha256 == script_digest(SCRIPT)


def test_the_digest_covers_every_byte():
    assert script_digest("a") != script_digest("a ")


# --- isolation ------------------------------------------------------------------------------

def test_the_child_environment_is_an_allowlist_not_an_inheritance():
    env = child_env(base={
        "PATH": "/usr/bin",
        "AWS_SECRET_ACCESS_KEY": "very-secret",
        "STEPSTITCH_ADMIN_TOKEN": "admin-secret",
        "GITHUB_TOKEN": "gh-secret",
        "MY_API_KEY": "key-secret",
    })
    assert env["PATH"] == "/usr/bin"
    for leaked in ("AWS_SECRET_ACCESS_KEY", "STEPSTITCH_ADMIN_TOKEN", "GITHUB_TOKEN",
                   "MY_API_KEY"):
        assert leaked not in env
    assert not any("secret" in v for v in env.values())


def test_the_runner_never_builds_a_shell_command():
    calls = []
    _run(runner=fake_runner([1], calls))
    argv, kwargs = calls[0]
    assert isinstance(argv, list)                 # fixed argv, not a string
    assert kwargs["shell"] is False
    assert all(isinstance(part, str) for part in argv)


def test_the_working_directory_is_the_runners_choice(tmp_path):
    calls = []
    _run(project_dir=tmp_path, runner=fake_runner([1], calls))
    assert calls[0][1]["cwd"] == str(tmp_path)


def test_an_unlisted_address_is_refused():
    with pytest.raises(RunnerError) as exc:
        _run(base_url="http://evil.example.com", allowed_addresses=[BASE])
    assert "not an allowed address" in str(exc.value)


def test_no_configured_address_is_a_refusal_with_the_fix():
    with pytest.raises(RunnerError) as exc:
        check_address_allowed(BASE, [])
    assert "STEPSTITCH_APP_BASE_URL" in str(exc.value)


def test_a_path_cannot_smuggle_a_different_destination():
    # Same origin, different path: allowed. Different host: not, whatever the path says.
    check_address_allowed("http://127.0.0.1:3000/deep/link", [BASE])
    with pytest.raises(RunnerError):
        check_address_allowed("http://127.0.0.1:9999/", [BASE])


# --- limits ---------------------------------------------------------------------------------

def test_the_run_count_is_capped():
    calls = []
    _run(runs=1000, runner=fake_runner([1] * 100, calls))
    assert len(calls) == MAX_RUNS


def test_the_timeout_is_passed_to_the_child_and_capped():
    calls = []
    _run(timeout_seconds=99999, runner=fake_runner([1], calls))
    assert calls[0][1]["timeout"] <= 600


def test_cancelling_stops_between_runs_and_reaches_no_verdict():
    calls = []
    state = {"n": 0}

    def cancel_after_two():
        state["n"] += 1
        return state["n"] > 2

    result = _run(runs=6, should_cancel=cancel_after_two, runner=fake_runner([1] * 6, calls))
    assert result.cancelled is True
    assert result.verdict == INCONCLUSIVE
    assert len(calls) == 2
    assert "cancelled" in result.detail


# --- evidence hygiene ------------------------------------------------------------------------

def test_transcripts_are_scrubbed_of_credential_shapes():
    dirty = (
        "Authorization: Bearer abcdefghijklmnop\n"
        "STEPSTITCH_ADMIN_TOKEN=hunter2supersecret\n"
        "connecting to postgres://user:hunter2@db.internal:5432/x\n"
        "agent ssa_AbCdEf123456789 denied\n"
    )
    clean = scrub_transcript(dirty)
    for secret in ("abcdefghijklmnop", "hunter2supersecret", "hunter2",
                   "ssa_AbCdEf123456789"):
        assert secret not in clean
    assert "[redacted]" in clean


def test_the_stored_transcript_is_the_scrubbed_one():
    def leaky(argv, **kwargs):
        return subprocess.CompletedProcess(
            argv, 1, stdout="Bearer leaked-token-value-here\n", stderr="")

    result = _run(runner=leaky)
    assert "leaked-token-value-here" not in result.runs[0].transcript
    assert "[redacted]" in result.runs[0].transcript


# --- shape of the result ---------------------------------------------------------------------

def test_the_result_serializes_without_transcripts():
    # Transcripts can be long and are held separately; the summary stays small and safe.
    payload = _run(runner=fake_runner([1])).as_dict()
    assert payload["verdict"] == REPRODUCED
    assert payload["runs"][0]["exit_code"] == 1
    assert "transcript" not in payload["runs"][0]


def test_a_missing_playwright_names_the_install_instead_of_crashing():
    with pytest.raises(RunnerError) as exc:
        _run(runner=fake_runner([], raises=FileNotFoundError("npx")))
    assert "stepstitch doctor" in str(exc.value)


# --- a broken toolchain must never masquerade as a reproduced bug ---------------------------
# Found while proving the runner against real Playwright: the config lived outside the
# project, `@playwright/test` did not resolve, the process exited 1, and the runner called
# that "reproduced". Playwright exits 1 for a failing test AND for a config that will not
# load, so the exit code alone cannot tell them apart.

def test_a_module_resolution_failure_is_not_a_reproduced_bug():
    def cannot_resolve(argv, **kwargs):
        return subprocess.CompletedProcess(
            argv, 1, stdout="",
            stderr="Error: Cannot find module '@playwright/test'\n  at Module._load")

    result = _run(runner=cannot_resolve)
    assert result.verdict == INCONCLUSIVE
    assert result.runs[0].errored is True
    assert "never ran" in result.detail
    assert "Cannot find module" in result.detail


def test_output_without_test_results_is_treated_as_never_having_run():
    def garbage(argv, **kwargs):
        return subprocess.CompletedProcess(argv, 1, stdout="", stderr="Segmentation fault")

    result = _run(runner=garbage)
    assert result.verdict == INCONCLUSIVE
    assert result.runs[0].errored is True


def test_a_genuinely_failing_test_still_reads_as_reproduced():
    # The guard must not swallow the real signal: Playwright printed a run summary.
    def real_failure(argv, **kwargs):
        return subprocess.CompletedProcess(
            argv, 1,
            stdout="  1) repro.spec.ts:3:1 the button updates the page\n\n  1 failed\n",
            stderr="")

    result = _run(runner=real_failure)
    assert result.verdict == REPRODUCED
    assert result.runs[0].errored is False


def test_a_missing_browser_is_not_a_reproduced_bug():
    """A purged Chromium is a fact about this machine, never about the application.

    This is the transcript Playwright actually emits, and the reason it was misread for so
    long is the last line: a missing browser prints a **run summary** as well as its launch
    error. The summary regex matched, `errored` stayed False, and the verdict came back
    `reproduced` — StepStitch telling a developer their app was broken when what was broken
    was the browser. On the verify path that surfaced as `different_failure` (the two error
    strings differ), which reads like the four-verdict system working and is not.
    """
    def no_browser(argv, **kwargs):
        return subprocess.CompletedProcess(
            argv, 1,
            stdout="  1) repro.spec.ts:24:1 › StepStitch reproduction\n\n  1 failed\n",
            stderr="Error: browserType.launch: Executable doesn't exist at "
                   "/Users/x/Library/Caches/ms-playwright/chromium_headless_shell-1228/"
                   "chrome-headless-shell-mac-arm64/chrome-headless-shell\n"
                   "╔════════════════════════════════════════╗\n"
                   "║ Looks like Playwright Test or Playwright was just installed "
                   "or updated. ║\n"
                   "║ Please run the following command to download new browsers:  ║\n"
                   "║                                                             ║\n"
                   "║     npx playwright install                                  ║\n"
                   "╚════════════════════════════════════════╝\n")

    result = _run(runner=no_browser)
    assert result.verdict == INCONCLUSIVE, "a dead toolchain is not a reproduced bug"
    assert result.runs[0].errored is True
    assert "never ran" in result.detail


def test_classify_run_separates_the_three_outcomes():
    from stepstitch_service.runner import classify_run

    assert classify_run(0, "1 passed") == (True, False, "")
    passed, errored, _ = classify_run(1, "1 failed")
    assert (passed, errored) == (False, False)
    passed, errored, detail = classify_run(1, "Cannot find module '@playwright/test'")
    assert (passed, errored) == (False, True)
    assert "Cannot find module" in detail


def test_the_work_directory_sits_inside_the_project_so_node_can_resolve(tmp_path):
    # The failure that started this: a temp dir has no node_modules above it.
    seen = {}

    def capture(argv, **kwargs):
        config = argv[argv.index("--config") + 1]
        seen["config"] = config
        return subprocess.CompletedProcess(argv, 1, stdout="1 failed\n", stderr="")

    _run(project_dir=tmp_path, runner=capture)
    assert str(tmp_path) in seen["config"]


def test_a_relative_project_dir_still_yields_an_absolute_testdir(tmp_path, monkeypatch):
    """Playwright resolves a relative ``testDir`` against the CONFIG's directory, not the
    cwd, so a relative project dir produces a doubled path and "No tests found" — reported
    as ``inconclusive``, which reads like a fact about the app and is a fact about us.

    ``mkdtemp`` hid this: 3.12 absolutises its return value, 3.11 does not, so it passed on
    a laptop and failed on CI. The patch below forces the 3.11 behaviour so the guarantee is
    checked on every interpreter rather than on whichever one happens to be installed.
    """
    import tempfile as _tempfile

    real_mkdtemp = _tempfile.mkdtemp

    def mkdtemp_311(**kw):
        """3.11 returned ``os.path.join(dir, name)``; 3.12 wraps that in ``abspath``.

        So the result is relative exactly when ``dir`` is — which is why absolutising the
        project dir is the fix, and why faking an unconditionally relative return would
        test something that never happens.
        """
        return os.path.join(kw.get("dir", ""), os.path.basename(real_mkdtemp(**kw)))

    monkeypatch.setattr(_tempfile, "mkdtemp", mkdtemp_311)
    monkeypatch.chdir(tmp_path)

    seen = {}

    def capture(argv, **kwargs):
        config_path = argv[argv.index("--config") + 1]
        seen["text"] = Path(config_path).read_text(encoding="utf-8")
        return subprocess.CompletedProcess(argv, 1, stdout="1 failed\n", stderr="")

    _run(project_dir=Path("."), runner=capture)
    test_dir = json.loads(re.search(r"testDir:\s*(\".*?\")", seen["text"]).group(1))
    assert Path(test_dir).is_absolute(), f"relative testDir would not be found: {test_dir}"


def test_an_errored_run_is_never_called_flaky():
    def cannot_resolve(argv, **kwargs):
        return subprocess.CompletedProcess(
            argv, 1, stdout="", stderr="Error: Cannot find module '@playwright/test'")

    result = _run(runs=3, runner=cannot_resolve)
    assert result.verdict == INCONCLUSIVE
    assert result.flaky is False    # nothing ran; there is no flakiness to report


# --- the execution envelope: freezing HOW it ran, not only WHAT ran -----------------------

def test_diagnostics_do_not_change_the_frozen_script(tmp_path):
    """The whole design rests on this: instrumentation lives in the config, so the bytes
    that judge a fix are identical whether or not we are collecting evidence. If turning
    diagnostics on moved the hash, the referee property would die silently."""
    off = _run(diagnostics=False, work_root=tmp_path)
    on = _run(diagnostics=True, work_root=tmp_path)
    assert off.script_sha256 == on.script_sha256 == script_digest(SCRIPT)


def test_diagnostics_do_not_change_the_verdict(tmp_path):
    """A measurement that alters what it measures is not a measurement."""
    red_off = _run(diagnostics=False, runner=fake_runner([1]), work_root=tmp_path)
    red_on = _run(diagnostics=True, runner=fake_runner([1]), work_root=tmp_path)
    green_off = _run(diagnostics=False, runner=fake_runner([0]), work_root=tmp_path)
    green_on = _run(diagnostics=True, runner=fake_runner([0]), work_root=tmp_path)
    assert red_off.verdict == red_on.verdict == REPRODUCED
    assert green_off.verdict == green_on.verdict == NOT_REPRODUCED


def _capturing_runner(exit_code, sink):
    """Read the generated config *during* the run.

    It cannot be read afterwards: the runner deletes its scratch directory when the run
    ends, which is the very reason diagnostics are persisted to the store rather than left
    beside the run.
    """
    inner = fake_runner([exit_code])

    def run(argv, **kwargs):
        sink.append(Path(argv[argv.index("--config") + 1]).read_text())
        return inner(argv, **kwargs)

    return run


def test_tracing_is_requested_only_when_diagnostics_are_on(tmp_path):
    """Traces are large; a run nobody asked to diagnose should not pay for one."""
    on: list = []
    _run(diagnostics=True, runner=_capturing_runner(1, on), work_root=tmp_path)
    assert '"trace"' in on[0] and "retain-on-failure" in on[0]

    off: list = []
    _run(diagnostics=False, runner=_capturing_runner(1, off), work_root=tmp_path)
    assert '"trace"' not in off[0]


def test_a_run_under_a_different_envelope_is_refused(tmp_path):
    """Same script, different experiment. A fix 'proven' under another browser or timeout
    was not proven against the run that was frozen."""
    with pytest.raises(EnvelopeMismatch, match="different experiment"):
        _run(expected_envelope_sha256="0" * 64, work_root=tmp_path)


def test_a_session_frozen_before_envelopes_existed_still_verifies(tmp_path):
    # No recorded envelope means there is nothing to enforce — not a refusal.
    assert _run(expected_envelope_sha256=None, work_root=tmp_path).verdict


# --- browser identity -------------------------------------------------------------------

_DRY_RUN = """\
Chrome for Testing 149.0.7827.55 (playwright chromium v1228)
  Install location:    /cache/ms-playwright/chromium-1228
  Download url:        https://example.invalid/chrome.zip

FFmpeg (playwright ffmpeg v1011)
  Install location:    /cache/ms-playwright/ffmpeg-1011

Chrome Headless Shell 149.0.7827.55 (playwright chromium-headless-shell v1228)
  Install location:    /cache/ms-playwright/chromium_headless_shell-1228
"""


def _fake_probe(monkeypatch, stdout=_DRY_RUN, returncode=0, raises=None):
    def fake_run(argv, **kwargs):
        if raises:
            raise raises
        return subprocess.CompletedProcess(argv, returncode, stdout=stdout, stderr="")

    monkeypatch.setattr("stepstitch_service.runner.subprocess.run", fake_run)


def test_the_browser_identity_is_the_chromium_build_not_the_package_version(monkeypatch):
    """It used to report `playwright --version` — the npm package, not the browser.

    That made the field wrong in both directions: installing a new Chromium left the string
    unchanged, and the string stayed healthy with the browser deleted entirely.
    """
    from stepstitch_service.runner import _browser_identity

    _fake_probe(monkeypatch)
    monkeypatch.setattr("stepstitch_service.runner.Path.exists", lambda self: True)
    identity = _browser_identity(headless=True)
    assert identity.build == "chromium 149.0.7827.55 (playwright build 1228)"
    assert "Version 1." not in identity.build, "that is the npm package, not the browser"


def test_the_probe_believes_the_headless_shell_because_that_is_what_launches(monkeypatch):
    """The trap that would turn this fix into a worse bug.

    With `headless: true` Playwright launches the headless SHELL, a separate download from
    full Chromium. A machine can legitimately have the shell for the pinned revision and not
    the full browser — that is the machine this was written on. Checking the full-Chromium
    path would declare a working install broken and refuse every run.
    """
    from stepstitch_service.runner import _browser_identity

    _fake_probe(monkeypatch)
    # Exactly the real cache state: the shell is there for v1228, full chromium is not.
    monkeypatch.setattr("stepstitch_service.runner.Path.exists",
                        lambda self: "headless_shell" in str(self))
    assert _browser_identity(headless=True).present is True
    assert _browser_identity(headless=False).present is False


def test_an_unreadable_browser_probe_reports_unknown_rather_than_absent(monkeypatch):
    """Tri-state on purpose. "Could not ask" is not "it is missing".

    Collapsing them would refuse runs on unusual but working layouts (pnpm, Yarn PnP), which
    is a worse failure than the one this guards.
    """
    from stepstitch_service.runner import _browser_identity

    _fake_probe(monkeypatch, raises=OSError("npx not found"))
    absent = _browser_identity()
    assert absent.present is None and absent.build == "unknown"

    _fake_probe(monkeypatch, stdout="something unparseable")
    assert _browser_identity().present is None


# --- the envelope is a fingerprint, not a run id ------------------------------------------

def _root(tmp_path, name):
    """A scratch root that exists — mkdtemp will not create its parent."""
    d = tmp_path / name
    d.mkdir(parents=True, exist_ok=True)
    return d

def test_two_comparable_runs_produce_the_same_envelope_digest(tmp_path, monkeypatch):
    """The assertion whose absence let a run nonce ship as a fingerprint.

    The envelope used to hash the rendered config text, which embeds the mkdtemp scratch
    directory — so the digest changed on every run and could never match. The one test that
    existed passed "0"*64 and asserted a refusal, which succeeds even if the digest is pure
    noise. Nothing checked the direction that actually matters: two runs of the same
    experiment must agree.
    """
    _fake_probe(monkeypatch)
    monkeypatch.setattr("stepstitch_service.runner.Path.exists", lambda self: True)
    first = _run(work_root=_root(tmp_path, "a"), project_dir=_root(tmp_path, "a"),
                 runner=fake_runner([1]))
    second = _run(work_root=_root(tmp_path, "b"), project_dir=_root(tmp_path, "b"),
                  runner=fake_runner([0]))
    assert first.execution_envelope_sha256 == second.execution_envelope_sha256


def test_a_run_with_diagnostics_on_matches_the_envelope_frozen_with_them_off(
        tmp_path, monkeypatch):
    """The exact production pairing: freeze traces, verify does not.

    While diagnostics_profile was hashed, this pair could never agree, so enforcing the
    envelope would have refused every verification StepStitch ever performed.
    """
    _fake_probe(monkeypatch)
    monkeypatch.setattr("stepstitch_service.runner.Path.exists", lambda self: True)
    red = _run(work_root=_root(tmp_path, "red"), diagnostics=True, runner=fake_runner([1]))
    green = _run(work_root=_root(tmp_path, "green"), diagnostics=False, runner=fake_runner([0]))
    assert red.execution_envelope_sha256 == green.execution_envelope_sha256
    # And the frozen SCRIPT hash: tracing must not move either digest.
    assert red.script_sha256 == green.script_sha256


@pytest.mark.parametrize("change", [
    {"base_url": "http://127.0.0.1:9999"},
    {"timeout_seconds": 7},
])
def test_a_genuinely_different_experiment_still_moves_the_digest(change, tmp_path,
                                                                 monkeypatch):
    """Stops the fix degenerating into "hash a constant", which a same-digest test alone
    invites. Two runs must agree; two DIFFERENT runs must not."""
    _fake_probe(monkeypatch)
    monkeypatch.setattr("stepstitch_service.runner.Path.exists", lambda self: True)
    base = _run(work_root=_root(tmp_path, "base"), runner=fake_runner([1]))
    other = _run(work_root=_root(tmp_path, "other"), runner=fake_runner([1]),
                 allowed_addresses=[BASE, "http://127.0.0.1:9999"], **change)
    assert base.execution_envelope_sha256 != other.execution_envelope_sha256


def test_the_browser_build_is_part_of_the_experiment(tmp_path):
    # The reason the browser is pinned at all: an upgrade genuinely can change an outcome.
    # (Stated through the probe seam; how a build string is PARSED out of the dry-run
    # output is `_browser_identity`'s own concern, covered by its unit tests above.)
    before = _run(work_root=_root(tmp_path, "1"), runner=fake_runner([1]),
                  browser_probe=fake_browser(
                      build="chromium 149.0.7827.55 (playwright build 1228)"))
    after = _run(work_root=_root(tmp_path, "2"), runner=fake_runner([1]),
                 browser_probe=fake_browser(
                     build="chromium 150.0.9000.1 (playwright build 1228)"))
    assert before.execution_envelope_sha256 != after.execution_envelope_sha256


def test_the_scratch_directory_is_not_left_behind_when_the_envelope_is_refused(tmp_path):
    """check_envelope used to fire after mkdtemp and outside the try/finally, so every
    refusal leaked a scratch directory. It is now checked before anything is created."""
    before = set(tmp_path.iterdir()) if tmp_path.exists() else set()
    with pytest.raises(EnvelopeMismatch):
        _run(expected_envelope_sha256="0" * 64, work_root=tmp_path)
    assert set(tmp_path.iterdir()) == before, "a refused run created a directory"


def test_a_missing_browser_is_refused_before_anything_is_launched():
    """Pre-flight, not post-mortem. The condition is knowable before running, so the
    answer is NEEDS_SETUP with the exact fix — and the proof of "pre" is that the fake
    runner was never called.

    Passes its own probe rather than monkeypatching the module global: this test is ABOUT
    the absent-browser branch, so the absence has to be stated here, not arranged at a
    distance where `_run`'s default would silently overrule it.
    """
    calls = []
    result = _run(runner=fake_runner([1], calls),
                  browser_probe=fake_browser(
                      present=False,
                      build="chromium 149.0.7827.55 (playwright build 1228)",
                      location="/cache/chromium_headless_shell-1228"))
    assert result.verdict == NEEDS_SETUP
    assert calls == [], "nothing may be spawned on a machine that cannot spawn it"
    blocker = next(b for b in result.blockers if b["id"] == "browser")
    assert "npx playwright install chromium" in blocker["detail"]
    assert result.execution_envelope_sha256 == "", \
        "a digest for a run that never happened is noise"


def test_an_unreadable_browser_probe_does_not_refuse_the_run():
    """`None` is "could not ask", and it must never harden into "absent" — refusing runs
    on unusual but working layouts is a worse failure than the one being guarded.

    States its own unanswerable probe for the reason given in the test above.
    """
    calls = []
    result = _run(runner=fake_runner([1], calls),
                  browser_probe=lambda headless=True: BrowserIdentity())
    assert result.verdict == REPRODUCED
    assert len(calls) == 1, "the run must proceed"


def test_no_test_in_this_file_depends_on_a_browser_being_installed():
    """The guard for the defect this seam exists to close.

    This module's docstring promises its properties are "provable on any machine". That was
    false for 21 tests: the browser probe shelled out to the real machine, so a host with
    npx but no Chromium refused every run at the readiness gate before the fake runner was
    reached. The suite passed anyway wherever a developer happened to have Chromium, which
    is precisely how it survived to a release candidate.

    Asserting the seam is wired is not enough — a future test calling `run_reproduction`
    directly would reintroduce the dependence — so this enumerates the real surface: every
    call into the runner from this file must route through `_run`, which supplies the probe.
    Paired with the browser-free CI job, which runs this suite with Chromium absent.
    """
    import ast

    tree = ast.parse(Path(__file__).read_text())
    run_fn = next(node for node in tree.body
                  if isinstance(node, ast.FunctionDef) and node.name == "_run")
    # AST, not grep: comments, docstrings and this test's own error message all mention
    # the function name, and matching those would make the guard fail over prose.
    calls = [node.lineno for node in ast.walk(tree)
             if isinstance(node, ast.Call)
             and getattr(node.func, "id", "") == "run_reproduction"]
    strays = [ln for ln in calls if not run_fn.lineno <= ln <= run_fn.end_lineno]
    assert calls and not strays, (
        "a test calls run_reproduction() outside the _run() helper, so it will probe the "
        f"real machine for a browser and fail wherever Chromium is absent: lines {strays}")
