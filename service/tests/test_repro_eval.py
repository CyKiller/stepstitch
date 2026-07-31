"""Reproduction-quality eval gate (docs/PRODUCT-PLAN.md P5).

The output a regulated buyer's model-risk team cares about is the *reproduction*. This
gate asserts the quality oracle holds and FAILS on a bad reproduction: a strong trace
must compile to runnable, well-graded Playwright; a weak trace must be honestly graded
low (never over-promised); templated routes must flag id substitution; and no compiled
repro or evidence summary may carry credentials or a forbidden field.

This is the "ongoing output-quality monitoring" evidence cited in COMPLIANCE-EVIDENCE.md.
"""
import json

from stepstitch_service import generate_playwright_test, score_trace
from stepstitch_service.integrations import build_trace_summary
from stepstitch_service.integrations.base import FORBIDDEN_DRAFT_KEYS

# A strong trace: navigation + a stable-selector click + a terminal api_error.
STRONG = [
    {"timestamp": "t", "type": "navigation", "route": "/accounts/:id/checkout",
     "label": "[masked]"},
    {"timestamp": "t", "type": "click", "route": "/accounts/:id/checkout",
     "target": '[data-testid="pay"]', "label": "[masked]"},
    {"timestamp": "t", "type": "api_error", "route": "/accounts/:id/checkout",
     "label": "[masked]", "metadata": {"status": 500, "endpoint": "/api/accounts/:id/checkout"}},
]

# A weak trace: a single navigation — no terminal action, no stable selector.
WEAK = [
    {"timestamp": "t", "type": "navigation", "route": "/dashboard", "label": "[masked]"},
]


def test_strong_trace_compiles_to_runnable_well_graded_repro():
    code = generate_playwright_test("t-strong", STRONG, "https://app.example.test")
    # Runnable Playwright structure.
    assert "import { test, expect } from '@playwright/test';" in code
    assert "test('StepStitch reproduction'" in code
    assert "await page.goto('https://app.example.test/accounts/:id/checkout');" in code
    assert "await page.locator('[data-testid=\"pay\"]').click();" in code
    assert code.rstrip().endswith("});")
    # Quality header is present and honest.
    assert "// Replayability:" in code
    grade = score_trace(STRONG)["grade"]
    assert grade in {"A", "B"}, f"strong trace mis-graded {grade}"


def test_missing_terminal_action_is_warned_and_graded_poor():
    # A navigation-only trace has nothing to assert on. The oracle: it must carry the
    # `no_terminal_action` warning and grade poorly (D/F) — never a "good" grade.
    score = score_trace(WEAK)
    codes = {w["code"] for w in score["warnings"]}
    assert "no_terminal_action" in codes, "missing-terminal trace must be flagged"
    assert score["grade"] in {"D", "F"}, (
        f"a trace with nothing to assert must grade poorly, got {score['grade']}"
    )
    # It still compiles (the provider never crashes on thin input).
    assert "test('StepStitch reproduction'" in generate_playwright_test("t-weak", WEAK)


def test_empty_trace_is_graded_F():
    score = score_trace([])
    assert score["grade"] == "F"
    assert any(w["code"] == "empty_trace" for w in score["warnings"])


def test_templated_route_flags_id_substitution():
    # Unconfigured, a templated route must still be flagged — and now it names the exact
    # setting that resolves it rather than leaving a bare TODO.
    code = generate_playwright_test("t", STRONG)
    assert "NEEDS-CONFIG: no value for 'id'" in code, "templated route must flag substitution"
    assert "set route_params" in code, "the flag must name the setting that fixes it"


def test_configured_route_params_remove_the_flag():
    from stepstitch_service.repro_config import ReproConfig

    code = generate_playwright_test(
        "t", STRONG, config=ReproConfig.from_dict({"route_params": {"id": "1001"}})
    )
    assert "NEEDS-CONFIG" not in code.split("test('StepStitch")[1]
    assert "/accounts/1001/" in code


def test_repro_embeds_no_credentials():
    code = generate_playwright_test("t", STRONG, "https://app.example.test").lower()
    for secret in ("password", "authorization", "bearer ", "secret", "api_key", "apikey",
                   "cookie", "set-cookie"):
        assert secret not in code, f"compiled repro leaked credential-ish token {secret!r}"


def test_evidence_summary_never_carries_forbidden_keys_or_selectors():
    summary = build_trace_summary("t", STRONG).as_dict()
    for forbidden in FORBIDDEN_DRAFT_KEYS:
        assert forbidden not in summary
    blob = json.dumps(summary)
    assert "data-testid" not in blob  # structural selectors never surface in the summary


def test_grade_monotonicity_strong_beats_weak():
    # A regression that inverted the score would flip this — the core quality invariant.
    assert score_trace(STRONG)["score"] > score_trace(WEAK)["score"]


def test_a_trace_with_an_unexecutable_step_never_grades_a():
    """The oracle-level statement of the FootstepType fix: a reproduction that silently
    cannot replay one of its steps is not an A reproduction, whatever else it does well.
    Found live as a 1.00/A script with no page.goto that hung until timeout."""
    tainted = [dict(STRONG[0], type="navigate")] + [dict(s) for s in STRONG[1:]]
    verdict = score_trace(tainted)
    assert verdict["grade"] != "A", f"unexecutable step graded {verdict['grade']}"
    assert any(w["code"] == "unknown_step_type" for w in verdict["warnings"])
