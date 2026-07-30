"""Reference audit sinks for the ingest host.

Every operator read/action is audited by the StepStitch router via an injected callable.
This module provides two reference sinks:

- ``make_logging_audit`` — structured JSON to a logger (good for shipping to a SIEM).
- ``make_db_audit`` — durable rows in ``stepstitch_audit`` (queryable; keep on the separate
  ~5-year recordkeeping clock per Reg S-P — see contracts/stepstitch.md).

The audit detail is whatever the router passes (trace ids, correlation ids, target/approver
for deliveries) — never NPI.
"""
from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Dict, Optional

AuditFn = Callable[[str, str, Dict[str, Any]], Awaitable[None]]


def make_logging_audit(logger: Optional[logging.Logger] = None) -> AuditFn:
    log = logger or logging.getLogger("stepstitch.audit")

    async def audit(action: str, actor: str, detail: Dict[str, Any]) -> None:
        log.info(json.dumps(
            {"evt": "audit", "action": action, "actor": actor, "detail": detail},
            default=str,
        ))

    return audit


def make_db_audit(execute: Callable[..., Awaitable[Any]]) -> AuditFn:
    """Persist each audit event to ``stepstitch_audit`` via the host's ``execute`` callable
    (``?`` placeholders, adapted by the host's driver)."""

    async def audit(action: str, actor: str, detail: Dict[str, Any]) -> None:
        await execute(
            "INSERT INTO stepstitch_audit (id, action, actor, detail, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (
                str(uuid.uuid4()),
                action,
                actor,
                json.dumps(detail, default=str),
                datetime.now(timezone.utc),
            ),
        )

    return audit
