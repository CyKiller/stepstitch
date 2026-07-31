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

One asterisk on "no migration history to replay": ``CREATE TABLE IF NOT EXISTS`` creates
tables but never ALTERs them, so an existing local store keeps yesterday's columns forever
and the first INSERT naming a new one fails. ``_ensure_columns`` closes that gap by adding
any column the current schema declares and the store lacks — column ADDITION only, which is
the only schema change a local store needs to survive an upgrade. This is not the
production alembic path and does not want to be; Postgres keeps its real migrations.

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
import re
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


# "CREATE TABLE <name> ( <columns> );" — parsed from SCHEMA_SQL so the ensure step can
# never drift from the declared schema: whatever db.py says, this reads.
_TABLE_RE = re.compile(
    r"CREATE TABLE IF NOT EXISTS\s+(\w+)\s*\((.*?)\);", re.DOTALL | re.IGNORECASE)


def _declared_columns(create_body: str) -> "list[Tuple[str, str]]":
    """(name, declaration) per column in a CREATE TABLE body.

    Comments are stripped BEFORE splitting on commas — a comma inside a comment would
    otherwise shear the body into fragments whose first word is prose, and the ALTER built
    from one of those is a syntax error at connect time.
    """
    no_comments = "\n".join(line.split("--", 1)[0] for line in create_body.splitlines())
    columns = []
    for raw in no_comments.split(","):
        line = " ".join(raw.split()).strip()
        if not line or line.upper().startswith(("PRIMARY ", "FOREIGN ", "UNIQUE", "CHECK")):
            continue
        columns.append((line.split()[0], line))
    return columns


def _ensure_columns(conn: sqlite3.Connection) -> None:
    """Add any column the current schema declares and this store lacks.

    ``executescript(SCHEMA_SQL)`` creates missing TABLES but never alters existing ones —
    an upgraded install crashed with "no such column" on its first insert, and the failure
    was invisible to CI because every CI run starts from an empty store. Addition only, and
    NOT NULL defaults are stripped for added columns because SQLite cannot add a
    NOT-NULL-without-default column to a populated table; existing rows carry NULL, which
    readers already tolerate (they predate the column existing at all).

    This runs BEFORE ``executescript``, not after: SCHEMA_SQL also declares indexes, and a
    ``CREATE INDEX`` on a column the stale table lacks fails inside the script itself.
    Tables that do not exist yet are skipped here (empty PRAGMA) and created complete by
    the script a moment later.
    """
    for table, body in _TABLE_RE.findall(SCHEMA_SQL):
        existing = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
        if not existing:
            continue    # not created yet — executescript will build it complete
        for name, declaration in _declared_columns(body):
            if name in existing:
                continue
            if "PRIMARY KEY" in declaration.upper() or "REFERENCES" in declaration.upper():
                # A table missing its PRIMARY KEY is not an older version of this table —
                # it is a different table, and "adding" the key column without the key
                # would be silent corruption. Leave it; the next insert fails loudly and
                # names the column, which is a diagnosis rather than a mangling.
                continue
            addable = declaration.replace("NOT NULL", "").strip()
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {addable}")


def connect_local(path: Path) -> sqlite3.Connection:
    """Open (creating if needed) a local store and bring it to the current schema."""
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), check_same_thread=False, isolation_level=None)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    _ensure_columns(conn)
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
