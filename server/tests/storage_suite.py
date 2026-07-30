"""Shared storage-seam suite: one behavior contract, two implementations.

The host consumes storage as three async callables — ``execute`` / ``fetchone`` /
``fetchall`` over generic ``?``-placeholder SQL (contracts/stepstitch.md). This module
holds the implementation-agnostic round-trip that both stores must pass:

- ``server/tests/test_localdb.py`` runs it against the SQLite local store (always);
- ``server/tests/test_pg_integration.py`` runs it against real Postgres (gated on
  ``STEPSTITCH_TEST_DATABASE_URL``).

Not a test module itself — pytest collects nothing here.
"""
import json
import uuid
from datetime import datetime, timedelta, timezone


async def storage_roundtrip(execute, fetchone, fetchall) -> None:
    """Insert/read traces, verifications, agents, config, audit; prove ordering and
    the retention timestamp comparison work through this store."""
    now = datetime.now(timezone.utc)
    tid = str(uuid.uuid4())
    footsteps = json.dumps([{"route": "/x", "type": "api_error"}])

    # Trace insert/read: '?' placeholders, TEXT-stored JSON body.
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

    # Agent row: hash-only credential storage, boolean revoked flag round-trips falsy.
    await execute(
        "INSERT INTO stepstitch_agents (id, name, token_hash, scope, revoked, "
        "created_at, created_by) VALUES (?, ?, ?, ?, ?, ?, ?)",
        ("agent-1", "repro-bot", "hash-1", "read", False, now, "admin"),
    )
    agent = await fetchone(
        "SELECT id, name, scope, revoked FROM stepstitch_agents WHERE token_hash = ?",
        ("hash-1",),
    )
    assert agent[0] == "agent-1" and not agent[3]

    # Config store: per-key JSON, upsert-by-key semantics live above this seam.
    await execute(
        "INSERT INTO stepstitch_config (key, value, updated_at, updated_by) "
        "VALUES (?, ?, ?, ?)",
        ("scrub_overrides", "{}", now, "admin"),
    )
    cfg = await fetchone(
        "SELECT value FROM stepstitch_config WHERE key = ?", ("scrub_overrides",)
    )
    assert cfg[0] == "{}"

    # Audit row round-trips (Reg S-P recordkeeping table).
    await execute(
        "INSERT INTO stepstitch_audit (id, action, actor, detail, created_at) "
        "VALUES (?, ?, ?, ?, ?)",
        (str(uuid.uuid4()), "stepstitch.verify", "admin", "{}", now),
    )
    audits = await fetchall("SELECT action, actor FROM stepstitch_audit", ())
    assert audits and audits[0][0] == "stepstitch.verify"

    # Ordering: a later trace lists first under ORDER BY created_at DESC — this is what
    # ISO-8601 TEXT timestamps must preserve in the local store.
    tid2 = str(uuid.uuid4())
    await execute(
        "INSERT INTO stepstitch_traces (id, app_id, project_id, user_id, explanation, "
        "footsteps, trace_metadata, consent_version, retention_expires_at, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (tid2, "demo", "proj-1", "ingest-client", None, footsteps, "{}", None, None,
         now + timedelta(seconds=5)),
    )
    listed = await fetchall(
        "SELECT id FROM stepstitch_traces ORDER BY created_at DESC LIMIT 2", ()
    )
    assert [r[0] for r in listed] == [tid2, tid]

    # Retention comparison: an expired body is selected by a datetime cutoff param.
    tid3 = str(uuid.uuid4())
    await execute(
        "INSERT INTO stepstitch_traces (id, app_id, project_id, user_id, explanation, "
        "footsteps, trace_metadata, consent_version, retention_expires_at, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (tid3, "demo", "proj-1", "ingest-client", None, footsteps, "{}", None,
         now - timedelta(days=1), now - timedelta(days=31)),
    )
    expired = await fetchall(
        "SELECT id FROM stepstitch_traces "
        "WHERE retention_expires_at IS NOT NULL AND retention_expires_at < ?",
        (now,),
    )
    assert [r[0] for r in expired] == [tid3]
