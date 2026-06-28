"""Fragility Radar — fragility map + minimal repro (fragility.py). Pure + deterministic."""
from stepstitch_service.fragility import compute_fragility_map, minimal_repro


def test_fragility_ranks_worst_selector_first():
    steps = [
        {"type": "click", "route": "/a", "target": '[data-testid="ok"]'},   # testid -> low
        {"type": "click", "route": "/a", "target": "div > span:nth-of-type(2)"},  # structural
        {"type": "input", "route": "/a"},                                    # none -> highest
    ]
    fm = compute_fragility_map(steps)
    order = [f["stability"] for f in fm["fragility"]]
    assert order == ["none", "structural", "testid"]      # worst-first
    assert fm["most_fragile"]["stability"] == "none"
    assert fm["interactive_steps"] == 3
    # testid is least fragile.
    assert fm["fragility"][-1]["risk"] < fm["fragility"][0]["risk"]


def test_templated_route_increases_risk():
    plain = compute_fragility_map([{"type": "click", "route": "/a", "target": "#x"}])
    templ = compute_fragility_map([{"type": "click", "route": "/a/:id", "target": "#x"}])
    assert templ["fragility"][0]["risk"] > plain["fragility"][0]["risk"]


def test_non_interactive_steps_are_ignored():
    fm = compute_fragility_map([{"type": "navigation", "route": "/a"},
                                {"type": "api_error", "route": "/a"}])
    assert fm["fragility"] == [] and fm["most_fragile"] is None


def test_minimal_repro_keeps_failing_route_drops_detours():
    steps = [
        {"type": "navigation", "route": "/home"},
        {"type": "click", "route": "/home", "target": "#menu"},     # detour route
        {"type": "navigation", "route": "/checkout"},
        {"type": "click", "route": "/checkout", "target": '[data-testid="pay"]'},
        {"type": "api_error", "route": "/checkout"},                 # terminal failure here
    ]
    mr = minimal_repro(steps)
    assert mr["original_steps"] == 5
    assert mr["reduced_steps"] == 3                                  # only /checkout steps
    assert all(s["route"] == "/checkout" for s in mr["footsteps"])
    assert 0.0 < mr["reduction_ratio"] < 1.0


def test_minimal_repro_handles_empty_and_no_terminal():
    assert minimal_repro([])["reduced_steps"] == 0
    nav_only = [{"type": "navigation", "route": "/a"}]
    out = minimal_repro(nav_only)
    assert out["reduced_steps"] == 1 and out["reduction_ratio"] == 1.0  # nothing to assert -> whole
