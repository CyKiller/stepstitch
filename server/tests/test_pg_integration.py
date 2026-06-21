"""Real-Postgres integration proof for the ingest host's DB layer.

Skipped unless ``STEPSTITCH_TEST_DATABASE_URL`` is set (CI provides a Postgres service;
locally, point it at a throwaway database). The in-memory host/service tests inject fake
DB callables, so this is the only gate that exercises ``server/db.py`` for real —
``SCHEMA_SQL`` + ``ensure_schema``, the ``?`` -> ``$n`` ``translate_placeholders`` rewrite,
asyncpg ``Record`` tuple-indexing, and TEXT round-tripping of JSON bodies — end to end.
"""
import asyncio
import json
import os
import uuid
from datetime import datetime, timezone

import pytest

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
            "TRUNCATE stepstitch_traces, stepstitch_verifications, stepstitch_audit"
        )
        execute, fetchone, fetchall = build_db_callables(pool)
        now = datetime.now(timezone.utc)
        tid = str(uuid.uuid4())
        footsteps = json.dumps([{"route": "/x", "type": "api_error"}])

        # Trace insert/read drives '?' placeholders through translate_placeholders -> $n
        # and stores the footsteps body as TEXT (router JSON-encodes on write).
        await execute(
            "INSERT INTO stepstitch_traces (id, app_id, project_id, user_id, explanation, "
            "footsteps, trace_metadata, consent_version, retention_expires_at, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (tid, "demo", "proj-1", "ingest-client", None, footsteps, "{}", None, None, now),
        )
        row = await fetchone(
            "SELECT footsteps, project_id FROM stepstitch_traces WHERE id = ?", (tid,)
        )
        assert json.loads(row[0]) == [{"route": "/x", "type": "api_error"}]
        assert row[1] == "proj-1"

        # Verification round-trip — the run_url column the operator dashboard renders.
        await execute(
            "INSERT INTO stepstitch_verifications (id, trace_id, pre_passed, post_passed, "
            "verdict, fix_ref, run_url, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (str(uuid.uuid4()), tid, False, True, "confirmed_fixed", "PR#9",
             "https://ci.example.com/run/42", now),
        )
        corpus = await fetchall(
            "SELECT trace_id, verdict, run_url FROM stepstitch_verifications "
            "WHERE verdict = ? ORDER BY created_at DESC",
            ("confirmed_fixed",),
        )
        assert len(corpus) == 1
        assert corpus[0][0] == tid
        assert corpus[0][2] == "https://ci.example.com/run/42"

        # Audit row round-trips (Reg S-P recordkeeping table).
        await execute(
            "INSERT INTO stepstitch_audit (id, action, actor, detail, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (str(uuid.uuid4()), "stepstitch.verify", "admin", "{}", now),
        )
        audits = await fetchall("SELECT action, actor FROM stepstitch_audit", ())
        assert audits and audits[0][0] == "stepstitch.verify"
    finally:
        await pool.close()


def test_pg_roundtrip_traces_verifications_audit():
    asyncio.run(_roundtrip())
