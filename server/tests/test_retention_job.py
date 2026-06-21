"""Deterministic proof for the scheduled retention purge loop (``server/retention_job.py``).

No real time passes: ``sleep`` and ``purge`` are injected, so the loop is driven a fixed
number of iterations by having the fake ``sleep`` raise ``CancelledError`` once the desired
passes have run. Mirrors the repo's ``asyncio.run(...)`` test style (no pytest-asyncio).
"""
import asyncio

import pytest

from server.retention_job import purge_interval_from_env, run_purge_loop


class _FakeExecute:
    """Sentinel callable; the loop only forwards it to purge, never invokes it here."""

    async def __call__(self, *a, **k):  # pragma: no cover - never called by these tests
        return None


def test_purge_interval_from_env_default(monkeypatch):
    monkeypatch.delenv("RETENTION_PURGE_INTERVAL_SECONDS", raising=False)
    assert purge_interval_from_env() == 3600


def test_purge_interval_from_env_override(monkeypatch):
    monkeypatch.setenv("RETENTION_PURGE_INTERVAL_SECONDS", "0")
    assert purge_interval_from_env() == 0
    monkeypatch.setenv("RETENTION_PURGE_INTERVAL_SECONDS", "120")
    assert purge_interval_from_env() == 120


def test_loop_calls_purge_with_injected_callables():
    """One pass, then the fake sleep cancels; purge got the injected execute/fetchone."""
    execute = _FakeExecute()
    fetchone = object()
    purge_calls = []
    sleep_calls = []

    async def fake_purge(*, execute, fetchone):
        purge_calls.append({"execute": execute, "fetchone": fetchone})
        return 7

    async def fake_sleep(seconds):
        sleep_calls.append(seconds)
        raise asyncio.CancelledError

    async def _run():
        with pytest.raises(asyncio.CancelledError):
            await run_purge_loop(
                execute=execute,
                fetchone=fetchone,
                interval_seconds=99,
                sleep=fake_sleep,
                purge=fake_purge,
            )

    asyncio.run(_run())

    assert len(purge_calls) == 1
    assert purge_calls[0]["execute"] is execute
    assert purge_calls[0]["fetchone"] is fetchone
    # purge happens before sleep, and sleep got the configured interval.
    assert sleep_calls == [99]


def test_loop_survives_transient_purge_error():
    """First purge raises; the loop logs and continues to a successful second pass."""
    execute = _FakeExecute()
    fetchone = object()
    purge_calls = []

    async def fake_purge(*, execute, fetchone):
        purge_calls.append(1)
        if len(purge_calls) == 1:
            raise RuntimeError("transient DB blip")
        return 3

    sleep_count = {"n": 0}

    async def fake_sleep(seconds):
        # Allow exactly two purge passes, then cancel to end the loop.
        sleep_count["n"] += 1
        if sleep_count["n"] >= 2:
            raise asyncio.CancelledError

    async def _run():
        with pytest.raises(asyncio.CancelledError):
            await run_purge_loop(
                execute=execute,
                fetchone=fetchone,
                interval_seconds=1,
                sleep=fake_sleep,
                purge=fake_purge,
            )

    asyncio.run(_run())

    # The RuntimeError on pass 1 did NOT kill the loop — it reached pass 2.
    assert len(purge_calls) == 2


def test_loop_cancellation_propagates_and_does_not_hang():
    """Cancelling the loop task raises CancelledError out of it (re-raised, not swallowed)."""
    execute = _FakeExecute()
    fetchone = object()

    async def fake_purge(*, execute, fetchone):
        return 0

    # Real asyncio.sleep so the task parks on the await and external cancel hits it.
    async def _run():
        task = asyncio.create_task(
            run_purge_loop(
                execute=execute,
                fetchone=fetchone,
                interval_seconds=3600,
                purge=fake_purge,
            )
        )
        # Let the loop reach its first sleep, then cancel from the outside.
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert task.cancelled()

    asyncio.run(asyncio.wait_for(_run(), timeout=5))
