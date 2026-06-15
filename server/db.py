"""Postgres wiring for the StepStitch ingest host (asyncpg).

StepStitch's router/retention emit ``?`` placeholders and adapt to the host's driver
(see contracts/stepstitch.md). asyncpg uses ``$1, $2, …`` positional placeholders, so we
translate ``?`` -> ``$n`` and pass params positionally. Bodies (``footsteps`` /
``trace_metadata``) are stored as TEXT — the router JSON-encodes on write and
``json.loads`` on read — which avoids any JSONB codec surprises.
"""
from __future__ import annotations

from typing import Any, Awaitable, Callable, Tuple

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS stepstitch_traces (
    id                   TEXT PRIMARY KEY,
    app_id               TEXT NOT NULL,
    project_id           TEXT,
    user_id              TEXT NOT NULL,
    explanation          TEXT,
    footsteps            TEXT NOT NULL,
    trace_metadata       TEXT NOT NULL,
    consent_version      TEXT,
    retention_expires_at TIMESTAMPTZ,
    created_at           TIMESTAMPTZ NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_stepstitch_created_at  ON stepstitch_traces (created_at DESC);
CREATE INDEX IF NOT EXISTS ix_stepstitch_user_id     ON stepstitch_traces (user_id);
CREATE INDEX IF NOT EXISTS ix_stepstitch_retention   ON stepstitch_traces (retention_expires_at);

-- Audit trail (Reg S-P recordkeeping). Kept on a separate, longer retention clock than
-- trace bodies; never carries NPI (actions + ids only).
CREATE TABLE IF NOT EXISTS stepstitch_audit (
    id          TEXT PRIMARY KEY,
    action      TEXT NOT NULL,
    actor       TEXT NOT NULL,
    detail      TEXT,
    created_at  TIMESTAMPTZ NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_stepstitch_audit_created_at ON stepstitch_audit (created_at DESC);
CREATE INDEX IF NOT EXISTS ix_stepstitch_audit_action     ON stepstitch_audit (action);

-- Verified-Fix corpus: each reproduced failure + its certified fix (red->green).
-- Carries trace ids, pass/fail booleans, and a fix reference only — never NPI.
CREATE TABLE IF NOT EXISTS stepstitch_verifications (
    id           TEXT PRIMARY KEY,
    trace_id     TEXT NOT NULL,
    pre_passed   BOOLEAN NOT NULL,
    post_passed  BOOLEAN,
    verdict      TEXT NOT NULL,
    fix_ref      TEXT,
    run_url      TEXT,
    created_at   TIMESTAMPTZ NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_stepstitch_verif_trace   ON stepstitch_verifications (trace_id);
CREATE INDEX IF NOT EXISTS ix_stepstitch_verif_verdict ON stepstitch_verifications (verdict, created_at DESC);
"""


def translate_placeholders(sql: str) -> str:
    """Rewrite ``?`` placeholders to asyncpg's ``$1, $2, …`` (left to right)."""
    out = []
    n = 0
    for ch in sql:
        if ch == "?":
            n += 1
            out.append(f"${n}")
        else:
            out.append(ch)
    return "".join(out)


def build_db_callables(pool: Any) -> Tuple[
    Callable[..., Awaitable[Any]],
    Callable[..., Awaitable[Any]],
    Callable[..., Awaitable[Any]],
]:
    """Return ``(execute, fetchone, fetchall)`` bound to an asyncpg pool."""

    async def execute(sql: str, params: Tuple[Any, ...] = ()) -> None:
        await pool.execute(translate_placeholders(sql), *params)

    async def fetchone(sql: str, params: Tuple[Any, ...] = ()) -> Any:
        return await pool.fetchrow(translate_placeholders(sql), *params)

    async def fetchall(sql: str, params: Tuple[Any, ...] = ()) -> Any:
        return await pool.fetch(translate_placeholders(sql), *params)

    return execute, fetchone, fetchall


async def ensure_schema(pool: Any) -> None:
    """Create the traces table + indexes if absent (demo-grade migration)."""
    await pool.execute(SCHEMA_SQL)
