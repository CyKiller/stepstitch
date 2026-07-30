"""Did the fix work? The four answers, and the refusal to guess.

This is the half of the loop an agent does not get to answer, so the tests are mostly
about what StepStitch declines to conclude.
"""
from stepstitch_service.fixcheck import (
    DIFFERENT_FAILURE,
    FIXED,
    STILL_FAILING,
    UNABLE_TO_VERIFY,
    derive_fix_verdict,
    failure_signature,
)
from stepstitch_service.runner import (
    INCONCLUSIVE,
    NOT_REPRODUCED,
    REPRODUCED,
    ReproductionResult,
    RunAttempt,
)

RED_SIG = "Error: the reported TypeError must not reproduce"


def _after(verdict, *, transcript="", flaky=False, passed=None):
    if passed is None:
        passed = verdict == NOT_REPRODUCED
    return ReproductionResult(
        verdict=verdict, session_id="s", script_sha256="a" * 64, flaky=flaky,
        runs=[RunAttempt(index=0, exit_code=0 if passed else 1, passed=passed,
                         timed_out=False, duration_seconds=1.0, transcript=transcript)],
        detail="detail from the runner",
    )


def test_a_measured_red_then_green_is_fixed():
    v = derive_fix_verdict(red_verdict=REPRODUCED, red_signature=RED_SIG,
                           after=_after(NOT_REPRODUCED))
    assert v.verdict == FIXED
    assert "measured before the change" in v.detail


def test_without_a_red_run_a_passing_test_proves_nothing():
    """The whole point: a green test only means something against an observed failure."""
    v = derive_fix_verdict(red_verdict=None, red_signature="",
                           after=_after(NOT_REPRODUCED))
    assert v.verdict == UNABLE_TO_VERIFY
    assert "no measured red run" in v.detail


def test_a_red_run_that_did_not_reproduce_cannot_anchor_a_fix():
    v = derive_fix_verdict(red_verdict=NOT_REPRODUCED, red_signature="",
                           after=_after(NOT_REPRODUCED))
    assert v.verdict == UNABLE_TO_VERIFY


def test_the_same_failure_in_the_same_way_is_still_failing():
    v = derive_fix_verdict(
        red_verdict=REPRODUCED, red_signature=RED_SIG,
        after=_after(REPRODUCED, transcript="Error: the reported TypeError must not reproduce"))
    assert v.verdict == STILL_FAILING
    assert "same way" in v.detail


def test_a_failure_that_changed_shape_is_reported_as_different():
    """Calling this 'still failing' would hide the most useful thing anyone could say."""
    v = derive_fix_verdict(
        red_verdict=REPRODUCED, red_signature=RED_SIG,
        after=_after(REPRODUCED,
                     transcript="Error: locator('[data-testid=submit]') not found"))
    assert v.verdict == DIFFERENT_FAILURE
    assert "moved the problem" in v.detail
    assert "Before:" in v.detail and "Now:" in v.detail


def test_an_inconclusive_rerun_never_becomes_a_fix():
    v = derive_fix_verdict(red_verdict=REPRODUCED, red_signature=RED_SIG,
                           after=_after(INCONCLUSIVE, flaky=True, passed=False))
    assert v.verdict == UNABLE_TO_VERIFY
    assert v.flaky is True


def test_the_verdict_carries_both_signatures_for_the_reader():
    v = derive_fix_verdict(
        red_verdict=REPRODUCED, red_signature=RED_SIG,
        after=_after(REPRODUCED, transcript="Error: something else entirely"))
    payload = v.as_dict()
    assert payload["red_signature"] == RED_SIG
    assert "something else entirely" in payload["green_signature"]
    assert payload["script_sha256"] == "a" * 64


# --- the signature itself ---------------------------------------------------------------

def test_a_signature_survives_volatile_detail():
    """Two runs of the same failure must agree, or every rerun looks 'different'."""
    first = failure_signature(
        "  1) repro.spec.ts:12:3 › StepStitch reproduction\n"
        "    Error: expect(received).toBe(false) took 1234ms at a1b2c3d4e5f6\n")
    second = failure_signature(
        "  1) repro.spec.ts:14:9 › StepStitch reproduction\n"
        "    Error: expect(received).toBe(false) took 87ms at f6e5d4c3b2a1\n")
    assert first == second
    assert first


def test_two_genuinely_different_failures_do_not_collide():
    a = failure_signature("Error: the reported TypeError must not reproduce")
    b = failure_signature("Error: locator('#submit') resolved to 0 elements")
    assert a and b and a != b


def test_an_empty_transcript_has_no_signature():
    assert failure_signature("") == ""
