"""Overview metrics — a dashboard that quietly computes the wrong number is worse than none."""
from __future__ import annotations

from stepstitch_service.metrics import (
    daily_series,
    open_shapes,
    people_affected,
    people_series,
    repeat_rate,
    stage_breakdown,
    summary,
    worst_hit_pages,
)
from stepstitch_service.shapes import STAGE_ORDER


def _shape(stage="untriaged", occurrences=1, first="2026-07-20T09:00:00+00:00",
           route="/checkout", prior=None, daily=None):
    return {"stage": stage, "occurrences": occurrences, "first_seen": first,
            "fingerprint": {"route": route}, "prior_fixes": prior or [],
            "daily": daily or {}}


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
                 "days": DAYS, "series": [0, 0, 0, 0], "new_shapes_series": [0, 0, 0, 0],
                 "stages": [], "pages": [], "total": 0}


def test_summary_charts_people_not_new_shapes():
    """The headline series must be people-per-day; new-shapes-per-day rides alongside it.

    These differ by an order of magnitude on real data — which is the entire reason the
    chart changed. Asserting both in one place stops a future edit quietly swapping them
    back and flattening the chart again.
    """
    shapes = [
        _shape(first="2026-07-18T00:00:00+00:00", occurrences=9,
               daily={"2026-07-18": 4, "2026-07-19": 5}),
        _shape(first="2026-07-20T00:00:00+00:00", occurrences=3,
               daily={"2026-07-20": 3}),
    ]
    s = summary(shapes, DAYS, STAGE_ORDER)
    assert s["series"] == [4, 5, 3, 0]              # people per day
    assert s["new_shapes_series"] == [1, 0, 1, 0]   # distinct failures first seen per day
    assert s["days"] == DAYS                        # the axis travels with the data


# ---- people series ----------------------------------------------------------------------

def test_people_series_sums_across_shapes_on_the_same_day():
    shapes = [_shape(daily={"2026-07-19": 2}), _shape(daily={"2026-07-19": 5})]
    assert people_series(shapes, DAYS) == [0, 7, 0, 0]


def test_people_series_zero_fills_quiet_days():
    """A day nobody reported is a zero, never a gap — otherwise a quiet week compresses
    the chart and makes a calm month look busy."""
    shapes = [_shape(daily={"2026-07-18": 1, "2026-07-21": 1})]
    assert people_series(shapes, DAYS) == [1, 0, 0, 1]


def test_people_series_ignores_days_outside_the_window():
    shapes = [_shape(daily={"2026-01-01": 99, "2026-07-20": 2})]
    assert people_series(shapes, DAYS) == [0, 0, 2, 0]


def test_people_series_survives_shapes_with_no_daily_tally():
    """Shapes predating the `daily` field, or with a null created_at, must not crash it."""
    assert people_series([{}, {"daily": None}, _shape(daily={"2026-07-20": 3})],
                         DAYS) == [0, 0, 3, 0]


def test_people_series_on_no_shapes_is_all_zeros():
    assert people_series([], DAYS) == [0, 0, 0, 0]
