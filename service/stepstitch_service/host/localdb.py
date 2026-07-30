"""SQLite wiring for StepStitch Local (single-developer, zero-config mode).

A deliberately *separate* storage implementation, not a dual-target rewrite: the
production asyncpg path in ``server/db.py`` is untouched, and a local database starts at
the current schema with no migration history to replay. Both implementations satisfy the
same three-callable storage seam the host consumes — ``execute`` / ``fetchone`` /
``fetchall`` taking generic SQL with ``?`` placeholders (contracts/stepstitch.md) — and
SQLite speaks ``?`` natively, so no placeholder translation is needed.

Schema: ``SCHEMA_SQL`` from ``server/db.py`` is reused verbatim. Every construct in it is
SQLite-legal (``TIMESTAMPTZ`` is accepted as a declared column type; ``BOOLEAN`` /
``FALSE`` literals are supported), so the two stores cannot drift apart.

Timestamps: writes pass timezone-aware UTC ``datetime`` objects; they are stored as ISO
8601 TEXT via a converter local to this connection. Aware-UTC ISO strings compare and
``ORDER BY`` correctly as text, and every reader in the router already tolerates string
timestamps (``r[n].isoformat() if hasattr(...) else r[n]``).

Concurrency: one connection, serialized by a lock, driven through ``asyncio.to_thread``
so the event loop never blocks on disk. A local store serves exactly one developer; a
connection pool would be complexity without a customer.
"""
from __future__ import annotations

import asyncio
import datetime as _dt
import sqlite3
import threading
from pathlib import Path
from typing import Any, Awaitable, Callable, Tuple

from .db import SCHEMA_SQL

LOCAL_DSN_PREFIX = "sqlite:///"


def local_path_from_dsn(dsn: str) -> Path:
    """``sqlite:///relative/or/absolute.db`` -> filesystem path."""
    if not dsn.startswith(LOCAL_DSN_PREFIX):
        raise ValueError(f"not a local sqlite DSN (expected {LOCAL_DSN_PREFIX}…)")
    return Path(dsn[len(LOCAL_DSN_PREFIX):])


def _adapt(value: Any) -> Any:
    if isinstance(value, _dt.datetime):
        return value.isoformat()
    if isinstance(value, bool):
        return int(value)
    return value


def connect_local(path: Path) -> sqlite3.Connection:
    """Open (creating if needed) a local store and bring it to the current schema."""
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), check_same_thread=False, isolation_level=None)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    conn.executescript(SCHEMA_SQL)
    return conn


def build_local_db_callables(conn: sqlite3.Connection) -> Tuple[
    Callable[..., Awaitable[Any]],
    Callable[..., Awaitable[Any]],
    Callable[..., Awaitable[Any]],
]:
    """Return ``(execute, fetchone, fetchall)`` bound to a local SQLite connection.

    Mirrors ``server.db.build_db_callables``: same signatures, same generic SQL in,
    same tuple-shaped rows out.
    """
    lock = threading.Lock()

    def _run(sql: str, params: Tuple[Any, ...], fetch: str) -> Any:
        with lock:
            cur = conn.execute(sql, tuple(_adapt(p) for p in params))
            if fetch == "one":
                return cur.fetchone()
            if fetch == "all":
                return cur.fetchall()
            return None

    async def execute(sql: str, params: Tuple[Any, ...] = ()) -> None:
        await asyncio.to_thread(_run, sql, params, "none")

    async def fetchone(sql: str, params: Tuple[Any, ...] = ()) -> Any:
        return await asyncio.to_thread(_run, sql, params, "one")

    async def fetchall(sql: str, params: Tuple[Any, ...] = ()) -> Any:
        return await asyncio.to_thread(_run, sql, params, "all")

    return execute, fetchone, fetchall
