"""The report endpoint's key ships in the page, so its cost must be bounded by the server.

Anyone can read the ingest token out of a customer's JavaScript and post "reports". Without
limits that is two of the most common complaints about the tools StepStitch replaces — a
noisy inbox and a self-hosted bill that grows overnight — handed to whoever wants them.

Pinned here, without a network or a database:

- the limiter: per-client and global budgets, refill over time, a Retry-After that is true,
  and memory that stays bounded when an attacker sprays addresses;
- the configuration: env parsing, ``0`` disables a limit, and a typo fails loudly instead of
  silently running unlimited;
- the guard: a real ASGI app behind it rejects with 429 / 413 before the body reaches the
  handler, and leaves every other route alone.
"""
import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from stepstitch_service.ingest_limits import IngestGuard, IngestLimits, RateLimiter


class Clock:
    def __init__(self) -> None:
        self.t = 1000.0

    def __call__(self) -> float:
        return self.t


# --- the limiter -------------------------------------------------------------------------

def test_a_client_gets_its_budget_then_a_true_retry_after():
    clock = Clock()
    lim = RateLimiter(per_client_per_minute=3, global_per_minute=0, clock=clock)
    assert [lim.check("a") for _ in range(3)] == [None, None, None]
    retry = lim.check("a")
    assert retry is not None and 0 < retry <= 20.0
    clock.t += retry
    assert lim.check("a") is None, "waiting the advertised Retry-After must be enough"


def test_one_noisy_client_does_not_spend_another_clients_budget():
    lim = RateLimiter(per_client_per_minute=2, global_per_minute=0, clock=Clock())
    lim.check("a"), lim.check("a")
    assert lim.check("a") is not None
    assert lim.check("b") is None


def test_the_global_ceiling_holds_when_every_request_comes_from_a_new_address():
    """Behind a proxy that is not trusted, or under an address spray, per-client limits see
    no repeat offender. The global ceiling is what still bounds the disk."""
    lim = RateLimiter(per_client_per_minute=100, global_per_minute=5, clock=Clock())
    results = [lim.check(f"10.0.0.{i}") for i in range(10)]
    assert results[:5] == [None] * 5
    assert all(r is not None for r in results[5:])


def test_a_denied_request_does_not_spend_the_global_budget():
    lim = RateLimiter(per_client_per_minute=1, global_per_minute=3, clock=Clock())
    lim.check("a")
    for _ in range(10):
        assert lim.check("a") is not None
    assert lim.check("b") is None and lim.check("c") is None


def test_memory_stays_bounded_under_an_address_spray():
    lim = RateLimiter(per_client_per_minute=5, global_per_minute=0, clock=Clock(),
                      max_clients=100)
    for i in range(10_000):
        lim.check(f"spray-{i}")
    assert lim.tracked_clients() <= 100


def test_zero_disables_a_limit():
    lim = RateLimiter(per_client_per_minute=0, global_per_minute=0, clock=Clock())
    assert all(lim.check("a") is None for _ in range(10_000))


# --- configuration -----------------------------------------------------------------------

def test_defaults_are_bounded():
    limits = IngestLimits.from_env({})
    assert limits.max_body_bytes > 0
    assert limits.per_client_per_minute > 0
    assert limits.global_per_minute >= limits.per_client_per_minute


def test_env_overrides_and_zero_disables():
    limits = IngestLimits.from_env({
        "STEPSTITCH_INGEST_MAX_BYTES": "1024",
        "STEPSTITCH_INGEST_RATE_PER_MINUTE": "0",
        "STEPSTITCH_INGEST_GLOBAL_RATE_PER_MINUTE": "50",
    })
    assert (limits.max_body_bytes, limits.per_client_per_minute,
            limits.global_per_minute) == (1024, 0, 50)


@pytest.mark.parametrize("value", ["ten", "-1", "1.5", "1e3"])
def test_a_typo_fails_loudly_rather_than_running_unlimited(value):
    with pytest.raises(ValueError, match="STEPSTITCH_INGEST_RATE_PER_MINUTE"):
        IngestLimits.from_env({"STEPSTITCH_INGEST_RATE_PER_MINUTE": value})


# --- the guard in front of a real ASGI app -------------------------------------------------

PATH = "/api/stepstitch/v1/session"


def _app(limits: IngestLimits, clock=None):
    app = FastAPI()
    seen = []

    @app.post(PATH)
    async def ingest(request: Request):
        body = await request.body()
        seen.append(len(body))
        return {"ok": True, "bytes": len(body)}

    @app.post("/admin/other")
    async def other(request: Request):
        await request.body()
        return {"ok": True}

    app.add_middleware(IngestGuard, path=PATH, limits=limits, clock=clock or Clock())
    return TestClient(app), seen


def test_an_oversized_report_is_413_and_never_reaches_the_handler():
    client, seen = _app(IngestLimits(max_body_bytes=100, per_client_per_minute=0,
                                     global_per_minute=0))
    r = client.post(PATH, content=b"x" * 101, headers={"content-type": "application/json"})
    assert r.status_code == 413
    assert seen == []


def test_a_chunked_body_without_content_length_is_still_measured():
    client, seen = _app(IngestLimits(max_body_bytes=100, per_client_per_minute=0,
                                     global_per_minute=0))

    def chunks():
        for _ in range(5):
            yield b"x" * 40

    r = client.post(PATH, content=chunks(), headers={"content-type": "application/json"})
    assert r.status_code == 413
    assert seen == []


def test_a_report_within_the_cap_arrives_intact():
    client, seen = _app(IngestLimits(max_body_bytes=100, per_client_per_minute=0,
                                     global_per_minute=0))
    r = client.post(PATH, content=b"y" * 100, headers={"content-type": "application/json"})
    assert r.status_code == 200 and r.json()["bytes"] == 100
    assert seen == [100]


def test_the_rate_limit_answers_429_with_retry_after():
    client, seen = _app(IngestLimits(max_body_bytes=0, per_client_per_minute=2,
                                     global_per_minute=0))
    codes = [client.post(PATH, content=b"{}").status_code for _ in range(3)]
    assert codes == [200, 200, 429]
    r = client.post(PATH, content=b"{}")
    assert r.status_code == 429
    assert int(r.headers["retry-after"]) >= 1
    assert len(seen) == 2


def test_other_routes_are_not_limited():
    client, _ = _app(IngestLimits(max_body_bytes=10, per_client_per_minute=1,
                                  global_per_minute=1))
    for _ in range(5):
        assert client.post("/admin/other", content=b"z" * 1000).status_code == 200
