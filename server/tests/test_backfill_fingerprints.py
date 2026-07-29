"""The fingerprint backfill (scripts/backfill_fingerprints.py).

A trace with a NULL fingerprint never clusters into a failure shape, so it is invisible on
the board — and invisibly so. These tests use an in-memory fake connection (asyncpg-shaped,
``$1`` placeholders) so they run without Postgres.
"""
import asyncio
import importlib.util
import json
import pathlib

import pytest
from stepstitch_service.fix_memory import fingerprint as fix_fingerprint
from stepstitch_service.integrations.base import build_trace_summary

_SCRIPT = pathlib.Path(__file__).resolve().parents[2] / "scripts" / "backfill_fingerprints.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("backfill_fingerprints", _SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


backfill_mod = _load_module()

FOOTSTEPS = [
    {"type": "navigation", "route": "/accounts/:id/transfer", "label": "[masked]"},
    {"type": "click", "route": "/accounts/:id/transfer", "target": "[data-testid=send]",
     "label": "[masked]"},
    {"type": "api_error", "route": "/accounts/:id/transfer",
     "metadata": {"status": 500, "endpoint": "/api/accounts/:id/transfers", "method": "POST"}},
]


class FakeConn:
    """Just enough asyncpg surface for the script: fetch / execute / fetchval."""

    def __init__(self, rows):
        self.rows = rows          # list of dicts: id, project_id, footsteps, fingerprint
        self.updates = []

    async def fetch(self, _sql, limit):
        pending = [r for r in self.rows if r["fingerprint"] is None]
        return pending[:limit]

    async def execute(self, _sql, fingerprint, trace_id):
        self.updates.append((trace_id, fingerprint))
        for row in self.rows:
            if row["id"] == trace_id:
                row["fingerprint"] = fingerprint

    async def fetchval(self, _sql):
        return len([r for r in self.rows if r["fingerprint"] is None])


def _row(trace_id, footsteps=FOOTSTEPS, fingerprint=None):
    return {
        "id": trace_id,
        "project_id": "demo",
        "footsteps": json.dumps(footsteps) if footsteps is not None else None,
        "fingerprint": fingerprint,
    }


def run(coro):
    return asyncio.run(coro)


def test_null_fingerprints_are_populated():
    conn = FakeConn([_row("trc_1"), _row("trc_2")])
    result = run(backfill_mod.backfill(conn, batch=500, dry_run=False))
    assert result == {"scanned": 2, "updated": 2, "skipped": 0}
    assert all(r["fingerprint"] is not None for r in conn.rows)


def test_backfilled_value_matches_what_ingest_would_have_written():
    """A backfilled row must be indistinguishable from a freshly ingested one, or the
    backfilled traces would cluster into their own separate shapes."""
    conn = FakeConn([_row("trc_1")])
    run(backfill_mod.backfill(conn, batch=500, dry_run=False))
    summary = build_trace_summary("trc_1", FOOTSTEPS, project_id="demo")
    expected = json.dumps(fix_fingerprint(summary.as_dict(), FOOTSTEPS))
    assert conn.rows[0]["fingerprint"] == expected


def test_already_fingerprinted_rows_are_left_alone():
    conn = FakeConn([_row("trc_1", fingerprint='{"route": "/x"}')])
    result = run(backfill_mod.backfill(conn, batch=500, dry_run=False))
    assert result == {"scanned": 0, "updated": 0, "skipped": 0}
    assert conn.updates == []


def test_running_twice_changes_nothing_the_second_time():
    conn = FakeConn([_row("trc_1"), _row("trc_2")])
    run(backfill_mod.backfill(conn, batch=500, dry_run=False))
    first = list(conn.updates)
    second = run(backfill_mod.backfill(conn, batch=500, dry_run=False))
    assert second == {"scanned": 0, "updated": 0, "skipped": 0}
    assert conn.updates == first


def test_dry_run_writes_nothing():
    conn = FakeConn([_row("trc_1"), _row("trc_2")])
    result = run(backfill_mod.backfill(conn, batch=500, dry_run=True))
    assert result["updated"] == 2          # reports what it would do…
    assert conn.updates == []              # …but touches nothing
    assert all(r["fingerprint"] is None for r in conn.rows)


def test_purged_bodies_are_skipped_not_guessed():
    # Retention purges the body; there is nothing structural left to derive from, and
    # inventing a fingerprint would put the trace in the wrong shape.
    conn = FakeConn([_row("trc_purged", footsteps=[]), _row("trc_ok")])
    result = run(backfill_mod.backfill(conn, batch=500, dry_run=False))
    assert result == {"scanned": 2, "updated": 1, "skipped": 1}


@pytest.mark.parametrize("batch", [1, 2, 500])
def test_batching_covers_every_row(batch):
    conn = FakeConn([_row(f"trc_{i}") for i in range(5)])
    while True:
        result = run(backfill_mod.backfill(conn, batch=batch, dry_run=False))
        if result["updated"] == 0:
            break
    assert all(r["fingerprint"] is not None for r in conn.rows)
