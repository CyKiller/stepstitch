"""Verdict logic: red->green is the only 'confirmed_fixed'."""
from stepstitch_service.verification.verdict import (
    VERDICT_CONFIRMED_FIXED, VERDICT_NOT_FIXED, VERDICT_NOT_REPRODUCED,
    VERDICT_REPRODUCED_UNFIXED, VerificationResult, derive_verdict,
)


def test_pre_passed_means_not_reproduced():
    assert derive_verdict(pre_passed=True, post_passed=None) == VERDICT_NOT_REPRODUCED
    assert derive_verdict(pre_passed=True, post_passed=False) == VERDICT_NOT_REPRODUCED


def test_pre_failed_no_post_is_reproduced_unfixed():
    assert derive_verdict(pre_passed=False, post_passed=None) == VERDICT_REPRODUCED_UNFIXED


def test_red_then_green_is_confirmed_fixed():
    assert derive_verdict(pre_passed=False, post_passed=True) == VERDICT_CONFIRMED_FIXED


def test_red_then_red_is_not_fixed():
    assert derive_verdict(pre_passed=False, post_passed=False) == VERDICT_NOT_FIXED


def test_result_as_dict_roundtrips():
    r = VerificationResult(trace_id="t1", pre_passed=False, post_passed=True,
                           verdict=VERDICT_CONFIRMED_FIXED, fix_ref="PR#9", run_url="u")
    d = r.as_dict()
    assert d["trace_id"] == "t1" and d["verdict"] == "confirmed_fixed"
    assert d["pre_passed"] is False and d["post_passed"] is True
    assert d["fix_ref"] == "PR#9" and d["run_url"] == "u"
