"""Split-retention cleanup for StepStitch trace bodies.

Reg S-P reconciliation (the "two clocks" rule from contracts/stepstitch.md):

* Trace **bodies** (``footsteps`` / ``explanation``) are minimized — purged once their
  ``retention_expires_at`` window elapses. This shrinks the standing NPI surface.
* Access / audit **records** live in the host's audit store on a *separate* 5-year
  clock. Purging a body therefore never destroys the record of who touched it.

This module owns only the body-purge half. The host wires it into its existing
job-cleanup precedent (a periodic background loop and/or an admin-triggered endpoint).
It is intentionally driver-agnostic: ``execute`` / ``fetchone`` use ``?`` placeholders
and the host adapts them to its DB driver.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Optional

logger = logging.getLogger("stepstitch")

ExecuteFn = Callable[..., Awaitable[Any]]
FetchOneFn = Callable[..., Awaitable[Optional[Any]]]

_COUNT_SQL = (
    "SELECT COUNT(*) FROM stepstitch_traces "
    "WHERE retention_expires_at IS NOT NULL AND retention_expires_at < ?"
)
_DELETE_SQL = (
    "DELETE FROM stepstitch_traces "
    "WHERE retention_expires_at IS NOT NULL AND retention_expires_at < ?"
)


async def purge_expired_traces(
    *,
    execute: ExecuteFn,
    fetchone: Optional[FetchOneFn] = None,
    now: Optional[datetime] = None,
) -> int:
    """Delete trace bodies whose retention window has elapsed.

    Returns the number of rows purged when ``fetchone`` is supplied (a pre-count, since
    many async drivers — e.g. asyncpg — do not surface a rowcount on ``execute``);
    otherwise returns ``-1`` to mean "purged, count unknown". Never raises on an empty
    table.
    """
    cutoff = now or datetime.now(timezone.utc)

    count = -1
    if fetchone is not None:
        row = await fetchone(_COUNT_SQL, (cutoff,))
        if row is not None:
            try:
                count = int(row[0])
            except (TypeError, ValueError, IndexError):
                count = -1

    await execute(_DELETE_SQL, (cutoff,))
    logger.info(
        "stepstitch retention purge cutoff=%s deleted=%s", cutoff.isoformat(), count
    )
    return count
