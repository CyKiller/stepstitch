"""StepStitch ingestion + operator router (decoupled factory).

The package never imports a host application. The host calls
``create_stepstitch_router(...)`` and injects its own auth dependencies and async DB
callables. DB callables use ``?`` placeholders (the host adapts to its driver).

Contract: see contracts/stepstitch.md. Write = any authed user (bound to caller).
Operator reads = admin only, and every read emits an audit event.
"""
from __future__ import annotations

import inspect
import json
import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Awaitable, Callable, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from .retention import purge_expired_traces

logger = logging.getLogger("stepstitch")

# Injected callable signatures.
ExecuteFn = Callable[..., Awaitable[None]]
FetchOneFn = Callable[..., Awaitable[Optional[Any]]]
FetchAllFn = Callable[..., Awaitable[List[Any]]]
AuditFn = Callable[[str, str, Dict[str, Any]], Awaitable[None]]
# Org-wide kill switch. Returns truthy when capture is allowed. May be sync or async.
CaptureEnabledFn = Callable[[], Any]


class FootstepSchema(BaseModel):
    timestamp: str
    type: str
    route: str
    target: Optional[str] = None
    label: str = "[masked]"
    metadata: Optional[Dict[str, Any]] = None


class IngestTracePayload(BaseModel):
    app_id: str = "marvox"
    project_id: Optional[str] = None
    explanation: Optional[str] = None
    footsteps: List[FootstepSchema]
    consent_version: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


def _actor_id(actor: Any) -> str:
    if isinstance(actor, dict):
        return str(actor.get("user_id") or actor.get("id") or actor.get("sub") or "unknown")
    return str(actor)


def _loads(value: Any) -> Any:
    return json.loads(value) if isinstance(value, (str, bytes)) else value


def create_stepstitch_router(
    *,
    get_user_id: Callable[..., Any],
    require_admin: Callable[..., Any],
    execute: ExecuteFn,
    fetchone: FetchOneFn,
    fetchall: FetchAllFn,
    audit: Optional[AuditFn] = None,
    generate_playwright_test: Callable[..., str],
    base_url: str = "http://localhost:3000",
    retention_days: int = 30,
    capture_enabled: Optional[CaptureEnabledFn] = None,
) -> APIRouter:
    """Build the StepStitch router with host-injected auth + DB.

    ``get_user_id`` / ``require_admin`` are FastAPI dependency callables. ``execute`` /
    ``fetchone`` / ``fetchall`` are async DB functions using ``?`` placeholders.
    ``generate_playwright_test`` is the deterministic compiler.

    ``capture_enabled`` is the org-wide **kill switch** (Reg S-P incident-response, see
    INCIDENT-RESPONSE.md). When supplied and it returns falsy, ingestion is refused
    with 503 — the first action in an IR runbook, halting capture tenant-wide without a
    redeploy. Reads/deletes/purge stay available so operators can still respond.
    """
    router = APIRouter(prefix="/stepstitch/v1", tags=["StepStitch"])

    async def _audit(action: str, actor_id: str, detail: Dict[str, Any]) -> None:
        if audit is not None:
            try:
                await audit(action, actor_id, detail)
            except Exception:  # never let audit failure mask the request
                logger.exception("stepstitch audit failed action=%s", action)

    async def _capture_allowed() -> bool:
        if capture_enabled is None:
            return True
        try:
            result = capture_enabled()
            if inspect.isawaitable(result):
                result = await result
            return bool(result)
        except Exception:  # a broken flag must fail safe → capture OFF
            logger.exception("stepstitch capture_enabled check failed; refusing capture")
            return False

    @router.post("/session")
    async def save_session_trace(
        payload: IngestTracePayload,
        user_id: str = Depends(get_user_id),
    ) -> Dict[str, Any]:
        if not await _capture_allowed():
            raise HTTPException(status_code=503, detail="StepStitch capture is disabled")
        trace_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)
        expires = now + timedelta(days=retention_days)
        footsteps = [f.model_dump() for f in payload.footsteps]
        await execute(
            "INSERT INTO stepstitch_traces (id, app_id, project_id, user_id, "
            "explanation, footsteps, trace_metadata, consent_version, "
            "retention_expires_at, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                trace_id,
                payload.app_id,
                payload.project_id,
                str(user_id),
                payload.explanation,
                json.dumps(footsteps),
                json.dumps(payload.metadata),
                payload.consent_version,
                expires,
                now,
            ),
        )
        logger.info("stepstitch trace stored id=%s user=%s", trace_id, user_id)
        return {"status": "ok", "trace_id": trace_id}

    @router.get("/sessions")
    async def list_sessions(
        admin: Any = Depends(require_admin),
        user_id: Optional[str] = Query(None),
        project_id: Optional[str] = Query(None),
        limit: int = Query(50, ge=1, le=200),
    ) -> Dict[str, Any]:
        clauses: List[str] = []
        params: List[Any] = []
        if user_id:
            clauses.append("user_id = ?")
            params.append(user_id)
        if project_id:
            clauses.append("project_id = ?")
            params.append(project_id)
        where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
        params.append(limit)
        rows = await fetchall(
            "SELECT id, app_id, project_id, user_id, explanation, created_at "
            f"FROM stepstitch_traces{where} ORDER BY created_at DESC LIMIT ?",
            tuple(params),
        )
        await _audit("stepstitch.list", _actor_id(admin),
                     {"user_id": user_id, "project_id": project_id})
        items = [
            {
                "trace_id": r[0],
                "app_id": r[1],
                "project_id": r[2],
                "user_id": r[3],
                "explanation": r[4],
                "created_at": r[5].isoformat() if hasattr(r[5], "isoformat") else r[5],
            }
            for r in rows
        ]
        return {"status": "ok", "sessions": items}

    @router.get("/session/{trace_id}")
    async def get_session(
        trace_id: str,
        admin: Any = Depends(require_admin),
    ) -> Dict[str, Any]:
        row = await fetchone(
            "SELECT footsteps, explanation, user_id, project_id, created_at "
            "FROM stepstitch_traces WHERE id = ?",
            (trace_id,),
        )
        if not row:
            raise HTTPException(status_code=404, detail="Trace not found")
        await _audit("stepstitch.read", _actor_id(admin), {"trace_id": trace_id})
        return {
            "status": "ok",
            "trace_id": trace_id,
            "footsteps": _loads(row[0]),
            "explanation": row[1],
            "user_id": row[2],
            "project_id": row[3],
        }

    @router.get("/session/{trace_id}/playwright")
    async def get_compiled_repro(
        trace_id: str,
        admin: Any = Depends(require_admin),
    ) -> Dict[str, Any]:
        row = await fetchone(
            "SELECT footsteps FROM stepstitch_traces WHERE id = ?",
            (trace_id,),
        )
        if not row:
            raise HTTPException(status_code=404, detail="Trace not found")
        await _audit("stepstitch.compile", _actor_id(admin), {"trace_id": trace_id})
        footsteps = _loads(row[0])
        code = generate_playwright_test(trace_id, footsteps, base_url)
        return {"status": "ok", "trace_id": trace_id, "playwright_code": code}

    @router.delete("/session/by-user/{target_user_id}")
    async def delete_user_traces(
        target_user_id: str,
        admin: Any = Depends(require_admin),
    ) -> Dict[str, Any]:
        # Right-to-delete: remove trace bodies; the deletion itself is audit-logged.
        await execute("DELETE FROM stepstitch_traces WHERE user_id = ?", (target_user_id,))
        await _audit("stepstitch.delete_by_user", _actor_id(admin),
                     {"target_user_id": target_user_id})
        return {"status": "ok", "deleted_user_id": target_user_id}

    @router.post("/maintenance/purge-expired")
    async def purge_expired(
        admin: Any = Depends(require_admin),
    ) -> Dict[str, Any]:
        # Split-retention cleanup: purge trace BODIES past their window. The audit
        # record of this purge is retained on the separate 5-year clock.
        deleted = await purge_expired_traces(execute=execute, fetchone=fetchone)
        await _audit("stepstitch.retention_purge", _actor_id(admin),
                     {"deleted": deleted})
        return {"status": "ok", "deleted": deleted}

    return router
