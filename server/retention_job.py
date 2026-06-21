"""Scheduled retention purge — the periodic half of split-retention cleanup.

``stepstitch_service.retention.purge_expired_traces`` owns the body-purge SQL; the host
already exposes it as an admin-triggered endpoint (``POST /api/maintenance/purge-expired``).
This module adds the *automatic* counterpart: a background loop that runs the same purge on
a fixed interval so retention is enforced without manual calls.

Kept out of the lifespan closure (``server/app.py``) so it stays unit-testable: ``sleep`` and
``purge`` are injectable, letting tests drive iterations deterministically without real time.
"""
from __future__ import annotations

import asyncio
import logging
import os
from typing import Any, Awaitable, Callable

from stepstitch_service.retention import purge_expired_traces

logger = logging.getLogger("stepstitch.host")

ExecuteFn = Callable[..., Awaitable[Any]]
FetchOneFn = Callable[..., Awaitable[Any]]
SleepFn = Callable[[float], Awaitable[Any]]
PurgeFn = Callable[..., Awaitable[int]]

_DEFAULT_INTERVAL_SECONDS = 3600


def purge_interval_from_env() -> int:
    """Read the auto-purge interval (seconds) from the environment.

    ``0`` disables the loop entirely (see ``server/app.py``). Defaults to one hour.
    """
    return int(os.environ.get("RETENTION_PURGE_INTERVAL_SECONDS", str(_DEFAULT_INTERVAL_SECONDS)))


async def run_purge_loop(
    *,
    execute: ExecuteFn,
    fetchone: FetchOneFn,
    interval_seconds: float,
    sleep: SleepFn = asyncio.sleep,
    purge: PurgeFn = purge_expired_traces,
) -> None:
    """Periodically purge expired trace bodies until cancelled.

    Each pass is wrapped so a transient DB error logs and the loop survives (fail-safe,
    like the router's ``_audit`` helper). ``asyncio.CancelledError`` is re-raised so
    cancellation propagates cleanly and shutdown stays prompt.
    """
    while True:
        try:
            deleted = await purge(execute=execute, fetchone=fetchone)
            logger.info("stepstitch retention auto-purge deleted=%s", deleted)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("stepstitch retention auto-purge failed; loop continues")
        await sleep(interval_seconds)
