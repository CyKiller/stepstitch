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
        _step("exception", metadata={"error_type": "TypeError"}),
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
    # No terminal action → nothing to assert → cannot be a "good" (A/B/C) grade.
    assert r["grade"] in {"D", "F"}, f"no-terminal trace mis-graded {r['grade']}"


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


def test_an_unknown_step_type_is_flagged_and_cannot_grade_well():
    """The second defensive layer, for legacy rows and direct Python callers that the
    ingest Literal cannot protect. The trace below is the live incident, verbatim in
    shape: a typo'd `navigate` followed by clean testid steps scored 1.00 grade A while
    the compiled script did nothing but hang — the scorer never asked whether a type was
    one the compiler can execute.
    """
    r = score_trace([
        _step("navigate", route="/index.html"),
        _step("input", target="[data-testid=amount]"),
        _step("click", target="[data-testid=submit]"),
        _step("exception"),
    ])
    assert any(w["code"] == "unknown_step_type" for w in r["warnings"])
    detail = next(w["detail"] for w in r["warnings"] if w["code"] == "unknown_step_type")
    assert "navigate" in detail, "the warning names the offending type"
    assert r["grade"] not in {"A", "B"}, (
        f"a reproduction with a silently unexecutable step graded {r['grade']}"
    )


def test_the_unknown_type_cap_is_exactly_the_advertised_060():
    """The cap is a specific number, so assert the number. `score_trace` promises in its
    own comment that such a trace is "at best a C", and the band assertion above enforces
    only that — it would still pass if the cap drifted to 0.69, which is why this one
    exists. Note what the control proves: the same trace with a canonical first step is a
    flawless 1.00, so the result is not 1.00 - 0.20 = 0.80 — the cap is what lands it.
    """
    clean = [
        _step("navigation", route="/index.html"),
        _step("input", target="[data-testid=amount]"),
        _step("click", target="[data-testid=submit]"),
        _step("exception"),
    ]
    assert score_trace(clean)["score"] == 1.0, (
        "the control must be flawless, or this test is measuring some other penalty"
    )

    capped = score_trace([_step("navigate", route="/index.html"), *clean[1:]])
    assert capped["score"] == 0.60, (
        f"one unexecutable step scored {capped['score']}, not the advertised 0.60 cap"
    )
    assert capped["grade"] == "C"


def test_each_unknown_step_costs_exactly_the_advertised_020():
    """The cap hides the per-step penalty whenever it binds, so measure the penalty where
    it cannot: a navigation-only trace already sits at 0.50, below the cap, and there each
    further unexecutable step must cost exactly 0.20. Differencing keeps this test honest
    if the unrelated no-terminal-action penalty is ever retuned.
    """
    def _score(unknowns):
        return score_trace(
            [_step("navigation", route="/a")]
            + [_step("navigate", route="/b") for _ in range(unknowns)]
        )["score"]

    none, one, two = _score(0), _score(1), _score(2)
    assert max(none, one, two) < 0.60, (
        "these traces must sit under the cap, or the cap — not the penalty — is what is "
        "being measured"
    )
    assert round(none - one, 4) == 0.20, f"first unknown step cost {round(none - one, 4)}"
    assert round(one - two, 4) == 0.20, f"second unknown step cost {round(one - two, 4)}"


def test_canonical_traces_gain_no_unknown_type_warning():
    r = score_trace([
        _step("navigation", route="/a"),
        _step("click", target="[data-testid=go]"),
        _step("api_error", metadata={"endpoint": "/api/x", "status": 500}),
    ])
    assert not any(w["code"] == "unknown_step_type" for w in r["warnings"])
