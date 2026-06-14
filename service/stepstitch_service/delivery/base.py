"""Optional governed direct-write — deliver a sanitized draft to a system of record.

This capability is **off by default** and deliberately **not** part of the MCP/Copilot agent
surface. A write happens only when ALL of these hold:

1. The host injected a configured ``RecordWriter`` (carrying base URL + auth in a closure —
   StepStitch core stores no system-of-record credentials).
2. An admin called ``/deliver`` with an explicit human ``approved_by`` and an
   ``idempotency_key``.
3. It was not a dry run (dry run is the default).

The payload sent is *exactly* the ``assert_flat``-validated draft the export-preview
endpoints return — never anything more. That keeps the no-NPI guarantee intact: direct-write
changes only *where the draft goes*, never *what is in it*.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Dict, List, Optional

from ..integrations.base import assert_flat

# A host closure carrying base URL + auth: (path, json_body) -> response json.
# Keeping creds in the closure means StepStitch core never holds them.
HttpPostFn = Callable[[str, Dict[str, Any]], Awaitable[Dict[str, Any]]]


class DeliveryError(RuntimeError):
    """Raised when a system-of-record write cannot be confirmed."""


@dataclass(frozen=True)
class DeliveryResult:
    target: str
    record_id: str
    deduped: bool
    receipt: Dict[str, Any]

    def as_dict(self) -> Dict[str, Any]:
        return {
            "target": self.target,
            "record_id": self.record_id,
            "deduped": self.deduped,
            "receipt": self.receipt,
        }


class RecordWriter(ABC):
    """Writes a single sanitized draft to a system of record."""

    name: str = "writer"

    @abstractmethod
    async def _create(self, draft: Dict[str, Any]) -> DeliveryResult:
        """POST the draft to the system of record; return a confirmed result."""
        raise NotImplementedError

    async def deliver(self, draft: Dict[str, Any]) -> DeliveryResult:
        # Belt-and-suspenders: never send anything but a flat, sanitized draft.
        assert_flat(draft)
        return await self._create(draft)


class DeliveryService:
    """Wraps the configured writers; enforces idempotency and reports receipts.

    Idempotency here is in-process, keyed by ``(target, idempotency_key)`` — enough to make
    a retried ``/deliver`` safe within a running service. A host that needs durable
    idempotency across restarts should back it with its own store or the system of record's
    own correlation key (the draft carries ``correlation_id = stepstitch:<trace_id>``).
    """

    def __init__(
        self,
        writers: Optional[List[RecordWriter]] = None,
        *,
        idempotency_store: Optional[Dict[str, Dict[str, Any]]] = None,
    ) -> None:
        self._writers: Dict[str, RecordWriter] = {w.name: w for w in (writers or [])}
        # A dict-like store of {key: receipt_dict}. Default is in-process; a host can pass a
        # durable MutableMapping (Redis/DB-backed) so idempotency survives restarts and is
        # shared across replicas. Receipts are stored as plain dicts to be JSON-friendly.
        self._store: Dict[str, Dict[str, Any]] = (
            {} if idempotency_store is None else idempotency_store
        )

    @property
    def enabled(self) -> bool:
        return bool(self._writers)

    def targets(self) -> List[str]:
        return sorted(self._writers)

    def has(self, target: str) -> bool:
        return target in self._writers

    async def deliver(
        self, target: str, draft: Dict[str, Any], *, idempotency_key: str
    ) -> DeliveryResult:
        writer = self._writers.get(target)
        if writer is None:
            raise DeliveryError(f"no writer configured for target {target!r}")
        key = f"{target}:{idempotency_key}"
        cached = self._store.get(key)
        if cached is not None:
            # Already delivered with this key — do NOT POST again.
            return DeliveryResult(
                cached["target"], cached["record_id"], True, cached["receipt"]
            )
        result = await writer.deliver(draft)
        self._store[key] = result.as_dict()
        return result
