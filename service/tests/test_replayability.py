"""Replayability scoring proof — the score must track real reproducibility."""
from stepstitch_service import score_trace
from stepstitch_service.replayability import selector_stability


def _step(type_, route="/dashboard", target=None, metadata=None):
    s = {"timestamp": "t", "type": type_, "route": route, "label": "[masked]"}
    if target is not None:
        s["target"] = target
    if metadata is not None:
        s["metadata"] = metadata
    return s


def test_selector_stability_tiers():
    assert selector_stability('[data-testid="pay"]') == "testid"
    assert selector_stability("#submit") == "id"
    assert selector_stability("div > button:nth-of-type(2)") == "structural"
    assert selector_stability(None) == "none"
    assert selector_stability("") == "none"


def test_empty_trace_is_f():
    r = score_trace([])
    assert r["score"] == 0.0
    assert r["grade"] == "F"
    assert any(w["code"] == "empty_trace" for w in r["warnings"])


def test_clean_testid_trace_scores_high():
    steps = [
        _step("navigation", route="/dashboard"),
        _step("click", target='[data-testid="open"]'),
        _step("api_error", metadata={"status": 500}),
    ]
    r = score_trace(steps)
    assert r["grade"] == "A"
    assert r["score"] >= 0.85
    assert r["warnings"] == []
    assert r["signals"]["stable_selectors"] == 1


def test_structural_selector_warns_and_drops_grade():
    steps = [
        _step("navigation"),
        _step("click", target="div > button:nth-of-type(2)"),
        _step("exception", metadata={"name": "TypeError"}),
    ]
    r = score_trace(steps)
    assert any(w["code"] == "unstable_selector" for w in r["warnings"])
    assert r["score"] < 0.95


def test_missing_selector_penalised_more_than_structural():
    structural = score_trace([_step("click", target="div > button"), _step("click", target="#x")])
    missing = score_trace([_step("click", target=None), _step("click", target="#x")])
    assert missing["score"] < structural["score"]
    assert any(w["code"] == "missing_selector" for w in missing["warnings"])


def test_navigation_only_flags_no_terminal_action():
    r = score_trace([_step("navigation", route="/a"), _step("navigation", route="/b")])
    assert any(w["code"] == "no_terminal_action" for w in r["warnings"])
    assert r["score"] <= 0.75


def test_templated_route_flags_fixture():
    r = score_trace([
        _step("navigation", route="/accounts/:id/distributions"),
        _step("click", target='[data-testid="go"]'),
    ])
    assert any(w["code"] == "templated_route_needs_fixture" for w in r["warnings"])


def test_score_is_clamped_and_deterministic():
    steps = [_step("click", target=None) for _ in range(10)]
    r1 = score_trace(steps)
    r2 = score_trace(steps)
    assert 0.0 <= r1["score"] <= 1.0
    assert r1 == r2  # deterministic


def test_compiler_emits_replayability_header():
    from stepstitch_service import generate_playwright_test
    code = generate_playwright_test(
        "trace-1",
        [_step("click", target="div > button:nth-of-type(2)")],
        "https://app.example.test",
    )
    assert "Replayability:" in code
    assert "unstable_selector" in code
