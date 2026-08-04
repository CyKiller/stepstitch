"""Execution state: how far a reproduction actually got, over every combination.

The question this answers is the one the four existing state machines could not: a
compiled draft missing its base URL looked identical to one measured red and fixed.
Pure derivation, so every combination is asserted directly rather than through a host.
"""
import pytest

from stepstitch_service.execution import (
    EXECUTION_STATES,
    STATE_CONFIRMED_FIXED,
    STATE_DRAFT,
    STATE_MEANING,
    STATE_READY,
    STATE_REPRODUCED,
    blocking_items,
    derive_execution_state,
    execution_summary,
)

BLOCKER = {"id": "base_url", "ready": False, "blocking": True,
           "title": "Application base URL", "detail": "not set"}
ADVISORY = {"id": "auth", "ready": False, "blocking": False,
            "title": "Authentication fixture", "detail": "not configured"}
READY_ITEM = {"id": "base_url", "ready": True, "blocking": True,
              "title": "Application base URL", "detail": "set"}

FROZEN_RED = {"red_verdict": "reproduced", "sha256": "a" * 64}
FROZEN_NEEDS_SETUP = {"red_verdict": "needs_setup"}
MEASURED_FIX = {"pre_passed": False, "post_passed": True,
                "verdict": "confirmed_fixed", "evidence_grade": "measured"}
REPORTED_RED = {"pre_passed": False, "post_passed": None,
                "verdict": "reproduced_unfixed", "evidence_grade": "asserted"}
INVALID_REPRO = {"pre_passed": True, "post_passed": None,
                 "verdict": "not_reproduced", "evidence_grade": "asserted"}


# --- the state, over every combination -------------------------------------------


@pytest.mark.parametrize(
    "readiness,frozen,verifications,expected",
    [
        # Nothing run: readiness alone decides.
        ([BLOCKER], None, [], STATE_DRAFT),
        ([BLOCKER, READY_ITEM], None, [], STATE_DRAFT),
        ([READY_ITEM], None, [], STATE_READY),
        ([], None, [], STATE_READY),
        (None, None, None, STATE_READY),
        # An advisory item is NOT a blocker — auth being unconfigured does not make a
        # reproduction wrong to run, only unauthenticated.
        ([ADVISORY], None, [], STATE_READY),
        # A measured red run.
        ([READY_ITEM], FROZEN_RED, [], STATE_REPRODUCED),
        # A freeze that refused to record a red is not evidence of one.
        ([READY_ITEM], FROZEN_NEEDS_SETUP, [], STATE_READY),
        # A CI-reported red half counts too (pre_passed False = the pre-fix run failed).
        ([READY_ITEM], None, [REPORTED_RED], STATE_REPRODUCED),
        # …but a pre-fix run that PASSED means the repro is invalid, not reproduced.
        ([READY_ITEM], None, [INVALID_REPRO], STATE_READY),
        # Red then green.
        ([READY_ITEM], FROZEN_RED, [MEASURED_FIX], STATE_CONFIRMED_FIXED),
        ([READY_ITEM], None, [MEASURED_FIX], STATE_CONFIRMED_FIXED),
    ],
)
def test_state_over_every_combination(readiness, frozen, verifications, expected):
    assert derive_execution_state(
        readiness, frozen=frozen, verifications=verifications) == expected


def test_measured_execution_outranks_a_later_config_change():
    # A trace that WAS reproduced stays reproduced even if config was edited afterwards.
    # Anything else would let an unrelated edit silently un-prove a real measurement.
    assert derive_execution_state(
        [BLOCKER], frozen=FROZEN_RED, verifications=[]) == STATE_REPRODUCED
    assert derive_execution_state(
        [BLOCKER], frozen=None, verifications=[MEASURED_FIX]) == STATE_CONFIRMED_FIXED


def test_blocking_items_ignores_ready_and_advisory():
    assert blocking_items([BLOCKER, ADVISORY, READY_ITEM]) == [BLOCKER]
    assert blocking_items(None) == []


def test_every_state_has_a_plain_meaning():
    # The console shows these verbatim; a state with no explanation is a label an
    # operator cannot act on.
    assert set(STATE_MEANING) == set(EXECUTION_STATES)
    for state, text in STATE_MEANING.items():
        assert len(text) > 40, f"{state} has no usable explanation"


# --- the summary: the evidence, not just the label --------------------------------


def test_summary_reports_what_actually_ran():
    summary = execution_summary([READY_ITEM], frozen=FROZEN_RED,
                                verifications=[MEASURED_FIX])
    assert summary["execution_state"] == STATE_CONFIRMED_FIXED
    assert summary["red_ran"] is True
    assert summary["green_ran"] is True
    assert summary["frozen"] is True
    assert summary["frozen_red_verdict"] == "reproduced"
    assert summary["evidence_grade"] == "measured"
    assert summary["blockers"] == []


def test_summary_never_claims_a_run_that_did_not_happen():
    summary = execution_summary([BLOCKER], frozen=None, verifications=[])
    assert summary["execution_state"] == STATE_DRAFT
    assert summary["red_ran"] is False
    assert summary["green_ran"] is False
    assert summary["frozen"] is False
    assert summary["evidence_grade"] is None
    # The blocker is named, with the setting to change — not just counted.
    assert summary["blockers"] == [
        {"id": "base_url", "title": "Application base URL", "detail": "not set"}]


def test_asserted_and_measured_grades_stay_distinguishable():
    asserted_only = execution_summary([READY_ITEM], verifications=[REPORTED_RED])
    assert asserted_only["evidence_grade"] == "asserted"
    assert asserted_only["red_ran"] is True      # CI reported a genuine failing run
    assert asserted_only["green_ran"] is False   # nobody has reported a passing one
    both = execution_summary([READY_ITEM], verifications=[REPORTED_RED, MEASURED_FIX])
    assert both["evidence_grade"] == "measured", "the strongest grade present wins"


def test_state_vocabulary_is_pinned():
    # A drift guard: the console, the docs and this module must agree on the names.
    assert EXECUTION_STATES == ("draft", "ready", "reproduced", "confirmed_fixed")
