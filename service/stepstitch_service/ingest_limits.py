"""Ingest limits — the report endpoint's key ships in the page, so the server bounds its cost.

The SDK posts reports with a bearer token that every visitor's browser can read. That is by
design (there is no other way for a page to report), and it means anyone can send a report.
The scrubber decides what a report may *contain*; this module decides what one may *cost*:

- **Size.** A report larger than ``max_body_bytes`` is answered 413 before the body reaches
  the handler. The body is measured as it arrives, so a chunked upload without a
  Content-Length is measured too. (Field-level caps — footsteps, lengths, metadata keys —
  live on the ingest schema in ``router.py``, so a host that embeds the router gets them.)
- **Rate.** Each client may send ``per_client_per_minute`` reports, refilled continuously;
  everyone together may send ``global_per_minute``. A refusal is 429 with a Retry-After that
  is true: waiting that long is enough.

Client identity is the connection's peer address as the ASGI server reports it. Behind a
reverse proxy that address is the proxy's unless the server is told to trust it (uvicorn:
``--forwarded-allow-ips`` / ``FORWARDED_ALLOW_IPS``). Untrusted, every client shares one
budget — coarser, never unlimited — and the global ceiling bounds the total either way.
X-Forwarded-For is deliberately not read here: a forger sets it to anything.

Limits are per process. Several replicas each enforce their own budgets.
"""
from __future__ import annotations

import json
import logging
import math
import time
from collections import OrderedDict
from dataclasses import dataclass
from typing import Any, Callable, Dict, Mapping, Optional, Tuple

logger = logging.getLogger("stepstitch.ingest_limits")

ENV_MAX_BYTES = "STEPSTITCH_INGEST_MAX_BYTES"
ENV_RATE = "STEPSTITCH_INGEST_RATE_PER_MINUTE"
ENV_GLOBAL_RATE = "STEPSTITCH_INGEST_GLOBAL_RATE_PER_MINUTE"

# A default SDK report (50 footsteps, masked labels) is a few kilobytes. 256 KiB leaves room
# for a long free-text note and a configured larger buffer while keeping a flood expensive
# for the sender rather than the host.
DEFAULT_MAX_BODY_BYTES = 256 * 1024
# One person reports a bug once, not sixty times a minute; a corporate NAT puts many people
# behind one address, so the per-client budget is generous and the global one is the wall.
DEFAULT_PER_CLIENT_PER_MINUTE = 60
DEFAULT_GLOBAL_PER_MINUTE = 600


def _env_int(env: Mapping[str, str], name: str, default: int) -> int:
    raw = (env.get(name) or "").strip()
    if not raw:
        return default
    if not raw.isdigit():
        # A typo must not quietly mean "unlimited". 0 is the explicit way to disable.
        raise ValueError(f"{name} must be a whole number >= 0 (0 disables it); got {raw!r}")
    return int(raw)


@dataclass(frozen=True)
class IngestLimits:
    max_body_bytes: int = DEFAULT_MAX_BODY_BYTES
    per_client_per_minute: int = DEFAULT_PER_CLIENT_PER_MINUTE
    global_per_minute: int = DEFAULT_GLOBAL_PER_MINUTE

    @classmethod
    def from_env(cls, env: Optional[Mapping[str, str]] = None) -> "IngestLimits":
        import os

        env = os.environ if env is None else env
        return cls(
            max_body_bytes=_env_int(env, ENV_MAX_BYTES, DEFAULT_MAX_BODY_BYTES),
            per_client_per_minute=_env_int(env, ENV_RATE, DEFAULT_PER_CLIENT_PER_MINUTE),
            global_per_minute=_env_int(env, ENV_GLOBAL_RATE, DEFAULT_GLOBAL_PER_MINUTE),
        )


class _Bucket:
    """A token bucket: ``capacity`` tokens, refilled at ``capacity`` per minute."""

    __slots__ = ("capacity", "tokens", "stamp")

    def __init__(self, capacity: int, now: float) -> None:
        self.capacity = float(capacity)
        self.tokens = float(capacity)
        self.stamp = now

    def refill(self, now: float) -> None:
        elapsed = max(0.0, now - self.stamp)
        self.tokens = min(self.capacity, self.tokens + elapsed * self.capacity / 60.0)
        self.stamp = now

    def wait(self) -> float:
        """Seconds until one token is available (0 if one is now)."""
        if self.tokens >= 1.0:
            return 0.0
        return (1.0 - self.tokens) * 60.0 / self.capacity


class RateLimiter:
    """Per-client and global token buckets. ``check`` returns None (allowed, and spent) or
    the seconds to wait. A refused request spends nothing, so a client hammering after its
    own refusal cannot drain everyone else's global budget."""

    def __init__(self, *, per_client_per_minute: int, global_per_minute: int,
                 clock: Callable[[], float] = time.monotonic,
                 max_clients: int = 10_000) -> None:
        self._per_client = per_client_per_minute
        self._clock = clock
        self._max_clients = max_clients
        self._clients: "OrderedDict[str, _Bucket]" = OrderedDict()
        self._global = (_Bucket(global_per_minute, clock())
                        if global_per_minute > 0 else None)

    def tracked_clients(self) -> int:
        return len(self._clients)

    def _client_bucket(self, key: str, now: float) -> _Bucket:
        bucket = self._clients.get(key)
        if bucket is None:
            bucket = _Bucket(self._per_client, now)
            self._clients[key] = bucket
            # An address spray must not grow memory without bound. Evict the least
            # recently seen; an evicted client comes back with a full bucket, which costs
            # at most one budget per eviction while the global ceiling still holds.
            while len(self._clients) > self._max_clients:
                self._clients.popitem(last=False)
        else:
            self._clients.move_to_end(key)
        bucket.refill(now)
        return bucket

    def check(self, key: str) -> Optional[float]:
        now = self._clock()
        waits = []
        client = None
        if self._per_client > 0:
            client = self._client_bucket(key, now)
            waits.append(client.wait())
        if self._global is not None:
            self._global.refill(now)
            waits.append(self._global.wait())
        wait = max(waits, default=0.0)
        if wait > 0:
            return wait
        if client is not None:
            client.tokens -= 1.0
        if self._global is not None:
            self._global.tokens -= 1.0
        return None


Scope = Dict[str, Any]


class IngestGuard:
    """ASGI middleware enforcing :class:`IngestLimits` on ``POST <path>`` only.

    The rate check runs before the body is read; the body is then buffered up to the cap
    and replayed to the app, so an oversized report never reaches the handler."""

    def __init__(self, app: Any, *, path: str, limits: IngestLimits,
                 clock: Callable[[], float] = time.monotonic) -> None:
        self.app = app
        self.path = path
        self.limits = limits
        self.clock = clock
        self.limiter = RateLimiter(per_client_per_minute=limits.per_client_per_minute,
                                   global_per_minute=limits.global_per_minute, clock=clock)
        self._refused: Dict[str, int] = {}
        self._window_start = clock()

    async def __call__(self, scope: Scope, receive: Any, send: Any) -> None:
        if (scope.get("type") != "http" or scope.get("method") != "POST"
                or scope.get("path") != self.path):
            await self.app(scope, receive, send)
            return

        client = scope.get("client")
        key = client[0] if client else "unknown"
        wait = self.limiter.check(key)
        if wait is not None:
            self._note("rate")
            await _reply(send, 429, "too many reports; retry later",
                         [(b"retry-after", str(max(1, math.ceil(wait))).encode())])
            return

        cap = self.limits.max_body_bytes
        if cap <= 0:
            await self.app(scope, receive, send)
            return
        declared = _content_length(scope)
        if declared is not None and declared > cap:
            self._note("size")
            await _reply(send, 413, f"report larger than {cap} bytes")
            return

        body = bytearray()
        more = True
        while more:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            body.extend(message.get("body", b""))
            more = message.get("more_body", False)
            if len(body) > cap:
                self._note("size")
                await _reply(send, 413, f"report larger than {cap} bytes")
                return

        replayed = False

        async def replay() -> Dict[str, Any]:
            nonlocal replayed
            if not replayed:
                replayed = True
                return {"type": "http.request", "body": bytes(body), "more_body": False}
            return await receive()

        await self.app(scope, replay, send)

    def _note(self, reason: str) -> None:
        """Count refusals and log a summary at most once a minute — a flood of refusals
        must not become a flood of log lines (or audit rows) on the host it targets."""
        self._refused[reason] = self._refused.get(reason, 0) + 1
        now = self.clock()
        if now - self._window_start >= 60.0:
            logger.warning("stepstitch ingest refused reports in the last %.0fs: %s",
                           now - self._window_start, dict(self._refused))
            self._refused.clear()
            self._window_start = now


def _content_length(scope: Scope) -> Optional[int]:
    for name, value in scope.get("headers") or []:
        if name.lower() == b"content-length":
            try:
                return int(value)
            except ValueError:
                return None
    return None


async def _reply(send: Any, status: int, detail: str,
                 extra: Tuple[Tuple[bytes, bytes], ...] | list = ()) -> None:
    payload = json.dumps({"detail": detail}).encode()
    headers = [(b"content-type", b"application/json"),
               (b"content-length", str(len(payload)).encode()), *extra]
    await send({"type": "http.response.start", "status": status, "headers": headers})
    await send({"type": "http.response.body", "body": payload})


__all__ = ["IngestGuard", "IngestLimits", "RateLimiter", "ENV_MAX_BYTES", "ENV_RATE",
           "ENV_GLOBAL_RATE"]
