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


# --- templated routes are a per-TRACE configuration gap -------------------------------
# Found on real data: a 50-step trace on /projects/:id/... was charged 49 times (-1.96)
# for ONE missing fixture id and scored 0.00 — with 44 of its 50 selectors stable. The
# charge made the grade a function of trace LENGTH rather than of how faithfully the trace
# replays, which is the one thing the grade is supposed to mean.


def _templated(n, route="/projects/:id/manuscript"):
    return [_step("click", route=route, target='[data-testid="x"]') for _ in range(n)]


def test_templated_route_is_charged_once_not_once_per_step():
    short = score_trace(_templated(2))
    long_ = score_trace(_templated(40))
    assert short["score"] == long_["score"], (
        "trace length must not change the templating charge — one fixture id resolves "
        "every occurrence at once"
    )
    codes = [w["code"] for w in long_["warnings"]]
    assert codes.count("templated_route_needs_fixture") == 1


def test_a_long_clean_templated_trace_still_grades_well():
    """The regression in one assertion: 40 clean steps must not be floored to F."""
    result = score_trace(_templated(40))
    assert result["score"] >= 0.85
    assert result["grade"] == "A"


def test_distinct_parameters_are_charged_separately():
    # Two different fixture values are two things the operator must supply.
    steps = [_step("click", route="/orgs/:org/projects/:id", target='[data-testid="x"]')]
    result = score_trace(steps)
    codes = [w["code"] for w in result["warnings"]]
    assert codes.count("templated_route_needs_fixture") == 2
    assert result["score"] == 0.92  # 1.00 - 2 x 0.04


def test_supplying_route_params_removes_the_charge():
    """The warning's own remedy, honoured: a supplied value is not a gap."""
    from stepstitch_service.repro_config import ReproConfig

    steps = _templated(10)
    unconfigured = score_trace(steps)
    configured = score_trace(steps, ReproConfig.from_dict({"route_params": {"id": "1001"}}))

    assert unconfigured["score"] < configured["score"]
    assert configured["score"] == 1.0
    assert not [
        w for w in configured["warnings"] if w["code"] == "templated_route_needs_fixture"
    ]


def test_a_partially_configured_trace_is_charged_only_for_what_is_missing():
    from stepstitch_service.repro_config import ReproConfig

    steps = [_step("click", route="/orgs/:org/projects/:id", target='[data-testid="x"]')]
    result = score_trace(steps, ReproConfig.from_dict({"route_params": {"id": "1001"}}))
    warnings = [w for w in result["warnings"] if w["code"] == "templated_route_needs_fixture"]
    assert len(warnings) == 1
    assert ":org" in warnings[0]["detail"]
    assert result["score"] == 0.96


def test_the_warning_names_the_parameter_and_its_reach():
    result = score_trace(_templated(7))
    warning = next(
        w for w in result["warnings"] if w["code"] == "templated_route_needs_fixture"
    )
    assert ":id" in warning["detail"]
    assert "7 steps" in warning["detail"], "say how many steps the one value unblocks"
    assert "route_params" in warning["detail"], "name the exact setting to change"
    assert warning["step_index"] == 0  # first occurrence, for consumers that locate it


def test_an_untemplated_trace_is_never_charged():
    result = score_trace([_step("click", route="/dashboard", target='[data-testid="x"]')])
    assert result["score"] == 1.0
    assert not [
        w for w in result["warnings"] if w["code"] == "templated_route_needs_fixture"
    ]
