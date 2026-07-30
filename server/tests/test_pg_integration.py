"""Real-Postgres integration proof for the ingest host's DB layer.

Skipped unless ``STEPSTITCH_TEST_DATABASE_URL`` is set (CI provides a Postgres service;
locally, point it at a throwaway database). The in-memory host/service tests inject fake
DB callables, so this is the only gate that exercises ``server/db.py`` for real —
``SCHEMA_SQL`` + ``ensure_schema``, the ``?`` -> ``$n`` ``translate_placeholders`` rewrite,
asyncpg ``Record`` tuple-indexing, and TEXT round-tripping of JSON bodies — end to end.

The round-trip body itself lives in ``storage_suite.py`` and is shared with the SQLite
local store's tests: one behavior contract, two implementations.
"""
import asyncio
import os

import pytest

from server.tests.storage_suite import storage_roundtrip

DB_URL = os.environ.get("STEPSTITCH_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(
    not DB_URL, reason="set STEPSTITCH_TEST_DATABASE_URL to run the real-Postgres gate"
)


async def _roundtrip() -> None:
    import asyncpg

    from server.db import build_db_callables, ensure_schema

    pool = await asyncpg.create_pool(DB_URL, min_size=1, max_size=2)
    try:
        await ensure_schema(pool)
        await pool.execute(
            "TRUNCATE stepstitch_traces, stepstitch_verifications, stepstitch_audit, "
            "stepstitch_agents, stepstitch_config"
        )
        execute, fetchone, fetchall = build_db_callables(pool)
        await storage_roundtrip(execute, fetchone, fetchall)
    finally:
        await pool.close()


def test_pg_roundtrip_traces_verifications_audit():
    asyncio.run(_roundtrip())
