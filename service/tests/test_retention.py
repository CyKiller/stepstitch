"""Unit tests for the split-retention body-purge path.

Uses ``asyncio.run`` rather than pytest-asyncio so the service test extras stay
dependency-light (httpx + pytest only).
"""
import asyncio
from datetime import datetime, timedelta, timezone

from stepstitch_service import purge_expired_traces


class FakeDB:
    def __init__(self, expired_count: int):
        self._expired = expired_count
        self.execute_calls = []
        self.deleted = False

    async def fetchone(self, query, params=()):
        assert "COUNT(*)" in query
        assert "retention_expires_at" in query
        return (self._expired,)

    async def execute(self, query, params=()):
        self.execute_calls.append((query, params))
        assert query.strip().upper().startswith("DELETE")
        assert "retention_expires_at" in query.lower()
        self.deleted = True


def test_purge_returns_precount_and_deletes():
    db = FakeDB(expired_count=3)
    deleted = asyncio.run(
        purge_expired_traces(execute=db.execute, fetchone=db.fetchone)
    )
    assert deleted == 3
    assert db.deleted is True


def test_purge_without_fetchone_returns_unknown_count():
    db = FakeDB(expired_count=0)
    deleted = asyncio.run(purge_expired_traces(execute=db.execute))
    assert deleted == -1  # count unknown, but the DELETE still ran
    assert db.deleted is True


def test_purge_uses_supplied_cutoff():
    captured = {}

    async def execute(query, params=()):
        captured["cutoff"] = params[0]

    fixed = datetime(2026, 1, 1, tzinfo=timezone.utc)
    asyncio.run(purge_expired_traces(execute=execute, now=fixed))
    assert captured["cutoff"] == fixed


def test_purge_defaults_to_now_utc():
    captured = {}

    async def execute(query, params=()):
        captured["cutoff"] = params[0]

    before = datetime.now(timezone.utc) - timedelta(seconds=5)
    asyncio.run(purge_expired_traces(execute=execute))
    after = datetime.now(timezone.utc) + timedelta(seconds=5)
    assert before <= captured["cutoff"] <= after
