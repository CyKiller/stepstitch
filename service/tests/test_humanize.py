"""Plain-language rendering — the layer that makes the console readable by non-engineers.

The point of this module is that a support lead can read a bug without knowing what a route
template is. These tests assert that literally: the output of plain_summary must not contain the
structural vocabulary it was derived from.
"""
from __future__ import annotations

import pytest

from stepstitch_service.humanize import (
    STAGE_HELP,
    STAGE_LABELS,
    action_name,
    confidence_band,
    confidence_help,
    failure_phrase,
    page_name,
    plain_summary,
    stage_help,
    stage_label,
    warning_summary,
    warning_text,
)
from stepstitch_service.replayability import GRADE_THRESHOLDS
from stepstitch_service.shapes import STAGE_ORDER

TRANSFER = {
    "route": "/accounts/:id/transfer",
    "diagnostic_type": "api_error",
    "failing_status": 500,
    "exception_type": None,
    "diagnostic_endpoint": "/api/accounts/:id/transfers",
    "terminal_selector": "[data-testid=review-transfer]",
}


# ---- page names --------------------------------------------------------------------------

@pytest.mark.parametrize("route,expected", [
    ("/accounts/:id/transfer", "Transfer"),
    ("/checkout", "Checkout"),
    ("/settings/:section", "Settings"),
    ("/order-history", "Order history"),
    ("/user_profile", "User profile"),
    ("/", "Home"),
    ("", "Unknown page"),
    (None, "Unknown page"),
])
def test_page_name(route, expected):
    assert page_name(route) == expected


def test_page_name_skips_parameter_segments():
    # ":id" names nothing a person would recognise, so it must never be the page name.
    assert page_name("/accounts/:id") == "Accounts"
    assert page_name("/orders/{orderId}") == "Orders"
    assert page_name("/users/42") == "Users"


# ---- action names ------------------------------------------------------------------------

@pytest.mark.parametrize("selector,expected", [
    ("[data-testid=review-transfer]", "Review transfer"),
    ('[data-testid="apply-promo"]', "Apply promo"),
    ("#save-profile", "Save profile"),
    (None, ""),
    ("", ""),
])
def test_action_name(selector, expected):
    assert action_name(selector) == expected


def test_css_path_selectors_name_nothing():
    # A class chain describes styling, not an action. Inventing a name from it would be worse
    # than staying silent, so these degrade to "" and the summary drops the clause.
    assert action_name(".btn.btn-primary:nth-child(3)") == ""
    assert action_name("div > span") == ""


# ---- failure phrasing --------------------------------------------------------------------

@pytest.mark.parametrize("fp,expected", [
    ({"failing_status": 500}, "the server errored"),
    ({"failing_status": 503}, "the server errored"),
    ({"failing_status": 404}, "something could not be found"),
    ({"failing_status": 403}, "access was refused"),
    ({"failing_status": 422}, "the request was rejected"),
    ({"exception_type": "TypeError"}, "the page crashed"),
    ({"diagnostic_type": "exception"}, "the page crashed"),
    ({"diagnostic_type": "api_error"}, "a request failed"),
    ({}, "something went wrong"),
])
def test_failure_phrase(fp, expected):
    assert failure_phrase(fp) == expected


def test_a_crash_reads_as_a_crash_even_when_the_class_was_scrubbed():
    # The scrubber drops exception_type whenever it could carry a message, so most real crashes
    # arrive with only diagnostic_type set. Keying on the class alone would downgrade every one
    # of them to "something went wrong" — true, but useless to the person reading it.
    scrubbed_crash = {"diagnostic_type": "exception", "exception_type": None,
                      "failing_status": None}
    assert failure_phrase(scrubbed_crash) == "the page crashed"


def test_status_wins_over_exception():
    # An HTTP status is the more specific signal when both are present.
    assert failure_phrase({"failing_status": 500, "exception_type": "TypeError"}) \
        == "the server errored"


def test_non_numeric_status_does_not_crash():
    assert failure_phrase({"failing_status": "oops"}) == "something went wrong"


# ---- the whole sentence ------------------------------------------------------------------

def test_plain_summary_reads_as_a_sentence():
    assert plain_summary(TRANSFER) == "Transfer — the server errored after Review transfer"


def test_plain_summary_drops_the_clause_when_the_action_is_unnamed():
    fp = dict(TRANSFER, terminal_selector=".btn.btn-primary")
    assert plain_summary(fp) == "Transfer — the server errored"


def test_plain_summary_survives_an_empty_fingerprint():
    assert plain_summary({}) == "Unknown page — something went wrong"
    assert plain_summary(None) == "Unknown page — something went wrong"


def test_plain_summary_contains_no_structural_vocabulary():
    # The whole point: what a non-engineer reads must not leak the shape it came from.
    summary = plain_summary(TRANSFER)
    for leaked in ("/accounts", ":id", "500", "api_error", "data-testid", "HTTP"):
        assert leaked not in summary, f"plain summary leaked {leaked!r}: {summary}"


# ---- confidence --------------------------------------------------------------------------

@pytest.mark.parametrize("score,expected", [
    (0.95, "Reliably reproducible"),
    (0.85, "Reliably reproducible"),
    (0.76, "Likely reproducible"),
    (0.60, "Might be reproducible"),
    (0.45, "Hard to reproduce"),
    (0.10, "Very hard to reproduce"),
    (None, "Not yet assessed"),
])
def test_confidence_band(score, expected):
    assert confidence_band(score) == expected


def test_confidence_bands_align_with_the_grade_thresholds():
    # The bands must not drift from replayability.py's letter grades, or the plain view and the
    # technical view would disagree about the same trace.
    for _grade, threshold in GRADE_THRESHOLDS:
        assert confidence_band(threshold) != "Very hard to reproduce"
        assert confidence_band(threshold) == confidence_band(threshold + 0.01)


def test_every_band_has_help_text():
    for score in (0.95, 0.76, 0.60, 0.45, 0.10, None):
        assert confidence_help(score).endswith(".")


# ---- warnings ----------------------------------------------------------------------------

def test_warning_text_explains_the_consequence_not_the_code():
    text = warning_text("templated_route_needs_fixture")
    assert "real account" in text
    assert "templated" not in text


def test_unknown_warning_falls_back_to_its_detail():
    # A new code added to replayability.py must degrade to today's behaviour, never vanish.
    assert warning_text("brand_new_code", "Something specific happened.") \
        == "Something specific happened."
    assert warning_text("brand_new_code") == "brand new code"


def test_warning_summary_groups_by_count():
    assert warning_summary("unstable_selector", 1).startswith("1 step:")
    assert warning_summary("unstable_selector", 5).startswith("5 steps:")


# ---- stages ------------------------------------------------------------------------------

def test_every_stage_has_a_plain_label_and_help():
    for stage in STAGE_ORDER:
        assert stage in STAGE_LABELS, f"no plain label for stage {stage}"
        assert stage in STAGE_HELP, f"no help text for stage {stage}"
        assert stage_label(stage) != stage
        assert stage_help(stage).endswith(".")


def test_stage_labels_avoid_jargon():
    jargon = ("repro", "shape", "triage", "verdict", "fingerprint")
    for stage in STAGE_ORDER:
        label = stage_label(stage).lower()
        for term in jargon:
            assert term not in label, f"stage label {label!r} still uses {term!r}"


def test_unknown_stage_degrades_readably():
    assert stage_label("some_new_stage") == "some new stage"
