"""The local runner: every MUST in contracts/stepstitch.md "Local runner security".

The contract was written in Phase 0, before the runner existed, precisely so these could
be tests rather than intentions. Playwright is never actually launched here — a fake
subprocess runner stands in — so the security properties are provable on any machine.
"""
import subprocess

import pytest

from stepstitch_service.runner import (
    INCONCLUSIVE,
    MAX_RUNS,
    NEEDS_SETUP,
    NOT_REPRODUCED,
    REPRODUCED,
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


def _run(**overrides):
    params = dict(session_id="s-1", script=SCRIPT, base_url=BASE, readiness=READY,
                  runner=fake_runner([0]))
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


def test_an_errored_run_is_never_called_flaky():
    def cannot_resolve(argv, **kwargs):
        return subprocess.CompletedProcess(
            argv, 1, stdout="", stderr="Error: Cannot find module '@playwright/test'")

    result = _run(runs=3, runner=cannot_resolve)
    assert result.verdict == INCONCLUSIVE
    assert result.flaky is False    # nothing ran; there is no flakiness to report
