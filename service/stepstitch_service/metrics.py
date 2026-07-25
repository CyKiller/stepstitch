"""Overview metrics — the numbers the console's landing screen is built from.

Everything here is derived from data the API already returns (``GET /shapes`` plus the counts on
``/admin/status``). No new endpoint, no new column: a shape already carries its stage, how many
people hit it, when it first and last appeared, and whether it matches a fix you shipped before.

The point of putting it here rather than in the page's JavaScript is that a dashboard which
quietly computes the wrong number is worse than no dashboard. These are pure functions over
plain dicts, so every figure on screen is covered by a test instead of by eyeballing a chart.
"""
from __future__ import annotations

from collections import Counter
from typing import Any, Dict, Iterable, List, Optional, Sequence

FIXED = "fixed"


def _day(iso: Optional[str]) -> str:
    """The date part of an ISO timestamp. Bucketing by day is the honest resolution here —
    finer than that and the line is noise, coarser and a spike disappears."""
    return str(iso or "")[:10]


def open_shapes(shapes: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [s for s in shapes if s.get("stage") != FIXED]


def people_affected(shapes: Iterable[Dict[str, Any]]) -> int:
    """Occurrences are traces, and each trace is one person's report."""
    return sum(int(s.get("occurrences") or 0) for s in shapes)


def repeat_rate(shapes: Sequence[Dict[str, Any]]) -> float:
    """Share of failures that match something already fixed — "how often are we re-breaking
    the same thing?". Returns 0.0 rather than dividing by zero on an empty deployment."""
    if not shapes:
        return 0.0
    repeats = sum(1 for s in shapes if s.get("prior_fixes"))
    return round(repeats / len(shapes) * 100, 1)


def daily_series(shapes: Sequence[Dict[str, Any]], days: Sequence[str]) -> List[int]:
    """New failures per day, over an explicit list of dates.

    The caller supplies the date axis so a day on which nothing broke still renders as a zero —
    if we only counted days that appear in the data, a quiet week would silently compress the
    chart and make things look busier than they were.
    """
    counts = Counter(_day(s.get("first_seen")) for s in shapes)
    return [counts.get(d, 0) for d in days]


def stage_breakdown(
    shapes: Sequence[Dict[str, Any]], order: Sequence[str]
) -> List[Dict[str, Any]]:
    """Count per stage, in the given order, skipping stages with nothing in them."""
    counts = Counter(s.get("stage") for s in shapes)
    return [{"stage": st, "count": counts[st]} for st in order if counts.get(st)]


def worst_hit_pages(
    shapes: Sequence[Dict[str, Any]], limit: int = 5
) -> List[Dict[str, Any]]:
    """Routes ranked by how many people they cost, not by how many distinct failures they have.

    One page with a single bug that hit 300 people matters more than a page with six bugs that
    hit one person each, and ranking by failure count would invert that.
    """
    totals: Counter = Counter()
    for s in shapes:
        route = (s.get("fingerprint") or {}).get("route")
        if route:
            totals[route] += int(s.get("occurrences") or 0)
    # Ties broken by route so the order never shuffles between identical requests.
    ranked = sorted(totals.items(), key=lambda kv: (-kv[1], kv[0]))
    return [{"route": r, "people": n} for r, n in ranked[:limit]]


def summary(
    shapes: Sequence[Dict[str, Any]], days: Sequence[str], stage_order: Sequence[str]
) -> Dict[str, Any]:
    """Everything the overview needs, in one pass."""
    opened = open_shapes(shapes)
    return {
        "open": len(opened),
        "people_affected": people_affected(opened),
        "fixed": sum(1 for s in shapes if s.get("stage") == FIXED),
        "repeat_rate": repeat_rate(shapes),
        "series": daily_series(shapes, days),
        "stages": stage_breakdown(opened, stage_order),
        "pages": worst_hit_pages(opened),
        "total": len(shapes),
    }


__all__ = [
    "open_shapes", "people_affected", "repeat_rate", "daily_series",
    "stage_breakdown", "worst_hit_pages", "summary",
]
