"""Overview metrics — a dashboard that quietly computes the wrong number is worse than none."""
from __future__ import annotations

from stepstitch_service.metrics import (
    daily_series,
    open_shapes,
    people_affected,
    repeat_rate,
    stage_breakdown,
    summary,
    worst_hit_pages,
)
from stepstitch_service.shapes import STAGE_ORDER


def _shape(stage="untriaged", occurrences=1, first="2026-07-20T09:00:00+00:00",
           route="/checkout", prior=None):
    return {"stage": stage, "occurrences": occurrences, "first_seen": first,
            "fingerprint": {"route": route}, "prior_fixes": prior or []}


DAYS = ["2026-07-18", "2026-07-19", "2026-07-20", "2026-07-21"]


# ---- open / affected --------------------------------------------------------------------

def test_fixed_shapes_are_not_open():
    shapes = [_shape(), _shape(stage="fixed"), _shape(stage="reproduced")]
    assert len(open_shapes(shapes)) == 2


def test_people_affected_sums_occurrences():
    assert people_affected([_shape(occurrences=4), _shape(occurrences=7)]) == 11


def test_people_affected_survives_missing_counts():
    assert people_affected([{"occurrences": None}, {}, _shape(occurrences=3)]) == 3


# ---- repeat rate ------------------------------------------------------------------------

def test_repeat_rate_counts_shapes_matching_a_prior_fix():
    shapes = [_shape(prior=[{"fix_ref": "PR-1"}]), _shape(), _shape(), _shape()]
    assert repeat_rate(shapes) == 25.0


def test_repeat_rate_on_an_empty_deployment_is_zero_not_a_crash():
    assert repeat_rate([]) == 0.0


# ---- daily series -----------------------------------------------------------------------

def test_daily_series_buckets_by_day():
    shapes = [
        _shape(first="2026-07-19T01:00:00+00:00"),
        _shape(first="2026-07-19T23:00:00+00:00"),
        _shape(first="2026-07-21T12:00:00+00:00"),
    ]
    assert daily_series(shapes, DAYS) == [0, 2, 0, 1]


def test_quiet_days_render_as_zero_rather_than_vanishing():
    # If absent days were dropped the axis would compress and a quiet week would look busy.
    series = daily_series([_shape(first="2026-07-21T00:00:00+00:00")], DAYS)
    assert series == [0, 0, 0, 1]
    assert len(series) == len(DAYS)


def test_series_ignores_shapes_outside_the_window():
    shapes = [_shape(first="2020-01-01T00:00:00+00:00")]
    assert daily_series(shapes, DAYS) == [0, 0, 0, 0]


# ---- stage breakdown --------------------------------------------------------------------

def test_stage_breakdown_follows_the_canonical_order_and_skips_empties():
    shapes = [_shape(stage="reproduced"), _shape(stage="reproduced"), _shape(stage="untriaged")]
    out = stage_breakdown(shapes, STAGE_ORDER)
    assert [row["stage"] for row in out] == ["untriaged", "reproduced"]
    assert [row["count"] for row in out] == [1, 2]


# ---- worst-hit pages --------------------------------------------------------------------

def test_pages_rank_by_people_not_by_failure_count():
    # One bug costing 300 people outranks six bugs costing one each — ranking by failure
    # count would inverted this and point the team at the wrong page.
    shapes = [_shape(route="/transfer", occurrences=300)] + [
        _shape(route="/search", occurrences=1) for _ in range(6)
    ]
    out = worst_hit_pages(shapes)
    assert out[0] == {"route": "/transfer", "people": 300}
    assert out[1] == {"route": "/search", "people": 6}


def test_pages_are_capped_and_deterministic():
    shapes = [_shape(route=f"/p{i}", occurrences=5) for i in range(9)]
    once = worst_hit_pages(shapes, limit=5)
    twice = worst_hit_pages(list(reversed(shapes)), limit=5)
    assert len(once) == 5
    assert once == twice          # ties broken by route, so the order never shuffles


def test_pages_skip_shapes_with_no_route():
    shapes = [{"fingerprint": {}, "occurrences": 9}, _shape(route="/x", occurrences=2)]
    assert worst_hit_pages(shapes) == [{"route": "/x", "people": 2}]


# ---- summary ----------------------------------------------------------------------------

def test_summary_is_internally_consistent():
    shapes = [
        _shape(stage="reproduced", occurrences=4, route="/transfer"),
        _shape(stage="untriaged", occurrences=2, route="/checkout"),
        _shape(stage="fixed", occurrences=9, route="/transfer"),
        _shape(stage="known_shape", occurrences=1, prior=[{"fix_ref": "PR-7"}]),
    ]
    s = summary(shapes, DAYS, STAGE_ORDER)
    assert s["total"] == 4
    assert s["open"] == 3                                   # everything but the fixed one
    assert s["open"] == sum(r["count"] for r in s["stages"])  # stages must add up to open
    assert s["fixed"] == 1
    assert s["people_affected"] == 7                        # 4 + 2 + 1, excluding the fixed
    assert s["repeat_rate"] == 25.0
    assert len(s["series"]) == len(DAYS)


def test_summary_on_an_empty_deployment():
    s = summary([], DAYS, STAGE_ORDER)
    assert s == {"open": 0, "people_affected": 0, "fixed": 0, "repeat_rate": 0.0,
                 "series": [0, 0, 0, 0], "stages": [], "pages": [], "total": 0}
