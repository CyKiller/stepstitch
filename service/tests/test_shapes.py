"""Failure Shapes — clustering, stage derivation, and shape ids.

These guard the console's primary object. The module is pure, so everything here is exercised
directly with plain dicts; no DB, no app, no fixtures.
"""
from __future__ import annotations

from stepstitch_service.fix_memory import fingerprint
from stepstitch_service.shapes import (
    FP_KEYS,
    STAGE_FIX_FAILED,
    STAGE_FIXED,
    STAGE_KNOWN,
    STAGE_ORDER,
    STAGE_REPRO_INVALID,
    STAGE_REPRODUCED,
    STAGE_UNTRIAGED,
    board,
    canonical_fingerprint,
    cluster,
    derive_stage,
    shape_id,
)
from stepstitch_service.verification.verdict import (
    VERDICT_CONFIRMED_FIXED,
    VERDICT_NOT_FIXED,
    VERDICT_NOT_REPRODUCED,
    VERDICT_REPRODUCED_UNFIXED,
)

TRANSFER = {
    "route": "/accounts/:id/transfer",
    "diagnostic_type": "api_error",
    "failing_status": 500,
    "exception_type": None,
    "diagnostic_endpoint": "/api/accounts/:id/transfers",
    "terminal_selector": "[data-testid=review-transfer]",
}
CHECKOUT = dict(TRANSFER, route="/checkout", failing_status=422,
                diagnostic_endpoint="/api/checkout/promo")


def _trace(tid, fp, created="2026-07-01T00:00:00+00:00", verdicts=None):
    return {"trace_id": tid, "fingerprint": fp, "created_at": created,
            "verdicts": verdicts or []}


# ---- shape_id ---------------------------------------------------------------------------

def test_shape_id_is_stable_and_order_independent():
    reordered = {k: TRANSFER[k] for k in reversed(list(TRANSFER))}
    assert shape_id(TRANSFER) == shape_id(reordered)
    # Stable across calls — it must not be Python's salted hash().
    assert shape_id(TRANSFER) == shape_id(dict(TRANSFER))


def test_shape_id_separates_different_shapes():
    assert shape_id(TRANSFER) != shape_id(CHECKOUT)


def test_shape_id_ignores_keys_outside_the_fingerprint():
    noisy = dict(TRANSFER, user_id="u_123", explanation="please help")
    assert shape_id(noisy) == shape_id(TRANSFER)


def test_canonical_fingerprint_fills_every_key():
    assert set(canonical_fingerprint({"route": "/x"})) == set(FP_KEYS)


def test_fingerprint_from_a_real_summary_clusters():
    # The id must be computable straight off fix_memory.fingerprint's output.
    summary = {
        "route": "/accounts/:id/transfer", "diagnostic_type": "api_error",
        "failing_status": 500, "exception_type": None,
        "diagnostic_endpoint": "/api/accounts/:id/transfers",
    }
    footsteps = [{"type": "click", "target": "[data-testid=review-transfer]"}]
    assert shape_id(fingerprint(summary, footsteps)) == shape_id(TRANSFER)


# ---- stage derivation -------------------------------------------------------------------

def test_untriaged_when_nothing_reported():
    assert derive_stage([]) == STAGE_UNTRIAGED


def test_prior_fix_promotes_untriaged_to_known():
    assert derive_stage([], has_prior_fix=True) == STAGE_KNOWN


def test_each_verdict_maps_to_its_column():
    assert derive_stage([VERDICT_NOT_REPRODUCED]) == STAGE_REPRO_INVALID
    assert derive_stage([VERDICT_REPRODUCED_UNFIXED]) == STAGE_REPRODUCED
    assert derive_stage([VERDICT_NOT_FIXED]) == STAGE_FIX_FAILED
    assert derive_stage([VERDICT_CONFIRMED_FIXED]) == STAGE_FIXED


def test_most_advanced_verdict_wins():
    verdicts = [VERDICT_REPRODUCED_UNFIXED, VERDICT_CONFIRMED_FIXED, VERDICT_NOT_FIXED]
    assert derive_stage(verdicts) == STAGE_FIXED


def test_own_verification_outranks_resemblance_to_an_older_fix():
    # A shape whose CI has reported must not sit in "known shape" — its own reality wins.
    assert derive_stage([VERDICT_REPRODUCED_UNFIXED], has_prior_fix=True) == STAGE_REPRODUCED


# ---- clustering -------------------------------------------------------------------------

def test_traces_with_the_same_shape_collapse_to_one():
    shapes = cluster([_trace("t1", TRANSFER), _trace("t2", TRANSFER), _trace("t3", TRANSFER)])
    assert len(shapes) == 1
    assert shapes[0]["occurrences"] == 3
    assert set(shapes[0]["trace_ids"]) == {"t1", "t2", "t3"}


def test_different_shapes_stay_separate():
    shapes = cluster([_trace("t1", TRANSFER), _trace("t2", CHECKOUT)])
    assert len(shapes) == 2
    assert {s["shape_id"] for s in shapes} == {shape_id(TRANSFER), shape_id(CHECKOUT)}


def test_first_and_last_seen_span_the_cluster():
    shapes = cluster([
        _trace("t1", TRANSFER, created="2026-07-01T00:00:00+00:00"),
        _trace("t2", TRANSFER, created="2026-07-09T00:00:00+00:00"),
        _trace("t3", TRANSFER, created="2026-07-05T00:00:00+00:00"),
    ])
    assert shapes[0]["first_seen"] == "2026-07-01T00:00:00+00:00"
    assert shapes[0]["last_seen"] == "2026-07-09T00:00:00+00:00"


def test_empty_fingerprints_are_skipped_not_merged():
    # Otherwise every unparseable trace collapses into one meaningless mega-shape.
    shapes = cluster([_trace("t1", {}), _trace("t2", None), _trace("t3", TRANSFER)])
    assert len(shapes) == 1
    assert shapes[0]["trace_ids"] == ["t3"]


def test_verdicts_aggregate_across_the_cluster():
    shapes = cluster([
        _trace("t1", TRANSFER, verdicts=[VERDICT_REPRODUCED_UNFIXED]),
        _trace("t2", TRANSFER, verdicts=[VERDICT_CONFIRMED_FIXED]),
    ])
    assert shapes[0]["stage"] == STAGE_FIXED
    assert shapes[0]["verdicts"] == sorted({VERDICT_REPRODUCED_UNFIXED, VERDICT_CONFIRMED_FIXED})


def test_ordering_is_deterministic_newest_active_first():
    traces = [
        _trace("t1", TRANSFER, created="2026-07-01T00:00:00+00:00"),
        _trace("t2", CHECKOUT, created="2026-07-09T00:00:00+00:00"),
    ]
    once = cluster(traces)
    twice = cluster(list(reversed(traces)))
    assert [s["shape_id"] for s in once] == [shape_id(CHECKOUT), shape_id(TRANSFER)]
    assert [s["shape_id"] for s in once] == [s["shape_id"] for s in twice]


# ---- fix memory integration -------------------------------------------------------------

def test_matching_corpus_entry_puts_an_untriaged_shape_in_known():
    corpus = [{"trace_id": "old", "fix_ref": "PR-42", "run_url": None, "fingerprint": TRANSFER}]
    shapes = cluster([_trace("t1", TRANSFER)], corpus=corpus)
    assert shapes[0]["stage"] == STAGE_KNOWN
    assert shapes[0]["prior_fixes"][0]["fix_ref"] == "PR-42"
    assert shapes[0]["prior_fixes"][0]["similarity"] == 1.0


def test_a_shape_never_cites_its_own_member_as_precedent():
    # t1 is both the trace being clustered and the corpus entry; it is not "seen before".
    corpus = [{"trace_id": "t1", "fix_ref": "PR-1", "run_url": None, "fingerprint": TRANSFER}]
    shapes = cluster([_trace("t1", TRANSFER, verdicts=[VERDICT_CONFIRMED_FIXED])], corpus=corpus)
    assert shapes[0]["prior_fixes"] == []
    assert shapes[0]["stage"] == STAGE_FIXED


def test_unrelated_corpus_entry_does_not_match():
    corpus = [{"trace_id": "old", "fix_ref": "PR-9", "run_url": None, "fingerprint": CHECKOUT}]
    shapes = cluster([_trace("t1", TRANSFER)], corpus=corpus)
    assert shapes[0]["prior_fixes"] == []
    assert shapes[0]["stage"] == STAGE_UNTRIAGED


# ---- board ------------------------------------------------------------------------------

def test_board_has_every_column_even_when_empty():
    columns = board(cluster([_trace("t1", TRANSFER)]))
    assert list(columns) == list(STAGE_ORDER)
    assert columns[STAGE_UNTRIAGED][0]["shape_id"] == shape_id(TRANSFER)
    assert columns[STAGE_FIXED] == []


def test_board_places_each_shape_in_exactly_one_column():
    shapes = cluster([
        _trace("t1", TRANSFER, verdicts=[VERDICT_CONFIRMED_FIXED]),
        _trace("t2", CHECKOUT),
    ])
    columns = board(shapes)
    assert sum(len(v) for v in columns.values()) == len(shapes) == 2
    assert columns[STAGE_FIXED][0]["fingerprint"]["route"] == "/accounts/:id/transfer"
    assert columns[STAGE_UNTRIAGED][0]["fingerprint"]["route"] == "/checkout"
