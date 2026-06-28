"""Fix Memory matching — pure, deterministic, explainable (fix_memory.py)."""
from stepstitch_service.fix_memory import DEFAULT_WEIGHTS, fingerprint, match


def _summary(**over):
    base = {
        "route": "/accounts/:id/transfer",
        "diagnostic_type": "api_error",
        "failing_status": 500,
        "exception_type": None,
        "diagnostic_endpoint": "/api/accounts/:id/transfers",
    }
    base.update(over)
    return base


def test_fingerprint_extracts_structural_fields_and_terminal_selector():
    footsteps = [
        {"type": "navigation", "route": "/accounts/:id/transfer"},
        {"type": "click", "route": "/accounts/:id/transfer", "target": '[data-testid="pay"]'},
        {"type": "api_error", "route": "/accounts/:id/transfer", "target": '[data-testid="pay"]'},
    ]
    fp = fingerprint(_summary(), footsteps)
    assert fp["route"] == "/accounts/:id/transfer"
    assert fp["failing_status"] == 500
    assert fp["terminal_selector"] == '[data-testid="pay"]'  # last interactive step


def test_identical_fingerprints_score_1_and_self_excluded():
    fp = fingerprint(_summary(), [])
    cands = [
        {"trace_id": "self", "fix_ref": "PR#1", "fingerprint": fp},
        {"trace_id": "twin", "fix_ref": "PR#2", "fingerprint": dict(fp)},
    ]
    out = match(fp, cands, exclude_trace_id="self")
    assert [m["trace_id"] for m in out] == ["twin"]
    assert out[0]["similarity"] == 1.0
    assert "same route" in out[0]["reasons"]


def test_unrelated_fingerprint_is_filtered_out():
    a = fingerprint(_summary(), [])
    b = fingerprint(_summary(route="/login", diagnostic_type="exception", failing_status=None,
                             exception_type="TypeError", diagnostic_endpoint=None), [])
    out = match(a, [{"trace_id": "x", "fingerprint": b}], min_similarity=0.4)
    assert out == []  # nothing shared above threshold


def test_partial_match_scores_between_and_reports_reasons():
    a = fingerprint(_summary(), [])
    # same route + diagnostic_type, different status/endpoint
    b = fingerprint(_summary(failing_status=503, diagnostic_endpoint="/api/other"), [])
    out = match(a, [{"trace_id": "x", "fix_ref": "PR#9", "fingerprint": b}], min_similarity=0.1)
    assert out and 0.0 < out[0]["similarity"] < 1.0
    assert "same route" in out[0]["reasons"]
    assert "same diagnostic_type" in out[0]["reasons"]
    assert "same failing_status" not in out[0]["reasons"]


def test_weights_are_configurable_and_change_ranking():
    a = fingerprint(_summary(), [])
    only_route = fingerprint(_summary(diagnostic_type=None, failing_status=None,
                                      exception_type=None, diagnostic_endpoint=None), [])
    only_status = fingerprint(_summary(route="/zzz", diagnostic_type=None,
                                       exception_type=None, diagnostic_endpoint=None), [])
    cands = [
        {"trace_id": "route_match", "fingerprint": only_route},
        {"trace_id": "status_match", "fingerprint": only_status},
    ]
    # Default weights: route (0.35) outranks status (0.15).
    assert match(a, cands, min_similarity=0.01)[0]["trace_id"] == "route_match"
    # Flip the weights → status wins.
    flipped = dict(DEFAULT_WEIGHTS, route=0.1, failing_status=0.6)
    assert match(a, cands, weights=flipped, min_similarity=0.01)[0]["trace_id"] == "status_match"


def test_ranking_is_deterministic_with_stable_tiebreak():
    a = fingerprint(_summary(), [])
    twin = dict(a)
    cands = [
        {"trace_id": "b", "fingerprint": dict(twin)},
        {"trace_id": "a", "fingerprint": dict(twin)},
    ]
    out = match(a, cands)
    assert [m["trace_id"] for m in out] == ["a", "b"]  # equal score → trace_id asc
