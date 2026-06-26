"""Reference direct-write HTTP clients: timeout/retry/backoff + durable idempotency."""
import asyncio

import httpx
import pytest

from stepstitch_service.delivery import DeliveryService, ServiceNowWriter
from stepstitch_service.delivery.base import DeliveryError
from stepstitch_service.delivery.clients import (
    http_post_client,
    salesforce_bearer,
    servicenow_bearer,
)


def run(coro):
    # Fresh loop per call → order-independent (asyncio.get_event_loop() raises on 3.12+
    # when no loop is current).
    return asyncio.run(coro)


def test_success_returns_json_once():
    calls = []

    def handler(request):
        calls.append(request.url.path)
        return httpx.Response(201, json={"result": {"sys_id": "S1"}})

    post = http_post_client("https://sn.example", transport=httpx.MockTransport(handler))
    out = run(post("/api/now/table/incident", {"x": 1}))
    assert out["result"]["sys_id"] == "S1"
    assert calls == ["/api/now/table/incident"]


def test_4xx_fails_fast():
    def handler(request):
        return httpx.Response(400, text="bad request")

    post = http_post_client("https://sn.example", transport=httpx.MockTransport(handler))
    with pytest.raises(DeliveryError):
        run(post("/x", {}))


def test_retries_transient_then_succeeds():
    state = {"n": 0}

    def handler(request):
        state["n"] += 1
        if state["n"] < 3:
            return httpx.Response(503)
        return httpx.Response(200, json={"ok": True})

    post = http_post_client(
        "https://sn.example", attempts=3, backoff=0.0,
        transport=httpx.MockTransport(handler),
    )
    assert run(post("/x", {})) == {"ok": True}
    assert state["n"] == 3


def test_gives_up_after_attempts():
    def handler(request):
        return httpx.Response(503)

    post = http_post_client(
        "https://sn.example", attempts=2, backoff=0.0,
        transport=httpx.MockTransport(handler),
    )
    with pytest.raises(DeliveryError):
        run(post("/x", {}))
    # 2 attempts, no more.


def test_auth_headers_are_sent():
    seen = {}

    def handler(request):
        seen["auth"] = request.headers.get("authorization")
        return httpx.Response(200, json={"ok": True})

    sn = servicenow_bearer("https://sn.example", "tok-sn",
                           transport=httpx.MockTransport(handler))
    run(sn("/x", {}))
    assert seen["auth"] == "Bearer tok-sn"

    sf = salesforce_bearer("https://sf.example", "tok-sf",
                           transport=httpx.MockTransport(handler))
    run(sf("/y", {}))
    assert seen["auth"] == "Bearer tok-sf"


def test_durable_idempotency_store_dedupes_across_instances():
    store = {}
    posts = {"n": 0}

    def handler(request):
        posts["n"] += 1
        return httpx.Response(201, json={"result": {"sys_id": "S9"}})

    post = http_post_client("https://sn.example", transport=httpx.MockTransport(handler))

    svc1 = DeliveryService([ServiceNowWriter(post)], idempotency_store=store)
    r1 = run(svc1.deliver("servicenow", {"short_description": "x"}, idempotency_key="k1"))
    assert r1.deduped is False and r1.record_id == "S9"

    # A fresh service sharing the durable store must not POST again.
    svc2 = DeliveryService([ServiceNowWriter(post)], idempotency_store=store)
    r2 = run(svc2.deliver("servicenow", {"short_description": "x"}, idempotency_key="k1"))
    assert r2.deduped is True and r2.record_id == "S9"
    assert posts["n"] == 1
