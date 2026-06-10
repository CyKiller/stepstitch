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

from .integrations.base import DraftAdapter, build_trace_summary, export_preview
from .replayability import score_trace
from .retention import purge_expired_traces
from .scrubber import FINANCIAL_SERVICES_ENTERPRISE, ScrubPolicy, ScrubRejection, scrub_trace_payload

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
    scrub_policy: ScrubPolicy = FINANCIAL_SERVICES_ENTERPRISE,
    draft_adapters: Optional[List[DraftAdapter]] = None,
) -> APIRouter:
    """Build the StepStitch router with host-injected auth + DB.

    ``get_user_id`` / ``require_admin`` are FastAPI dependency callables. ``execute`` /
    ``fetchone`` / ``fetchall`` are async DB functions using ``?`` placeholders.
    ``generate_playwright_test`` is the deterministic compiler.

    ``capture_enabled`` is the org-wide **kill switch** (Reg S-P incident-response, see
    INCIDENT-RESPONSE.md). When supplied and it returns falsy, ingestion is refused
    with 503 — the first action in an IR runbook, halting capture tenant-wide without a
    redeploy. Reads/deletes/purge stay available so operators can still respond.

    ``scrub_policy`` is the server-side **trust boundary** (see scrubber.py). Every
    payload is scrubbed before storage, independent of the SDK, so a hand-rolled or
    hostile POST cannot persist NPI (SSNs, account numbers, raw URLs, request/response
    bodies, unexpected metadata). The default is the strict financial-services posture.

    ``draft_adapters`` are the system-of-record exporters (the commercial pack — see
    ``integrations.bundle.default_draft_adapters``). The open core never imports concrete
    adapters; a host injects them. When none are supplied, the export-preview endpoints
    return an empty draft set (the core still serves all read-only operations).
    """
    router = APIRouter(prefix="/stepstitch/v1", tags=["StepStitch"])
    adapters: List[DraftAdapter] = list(draft_adapters or [])

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

        # Server-side trust boundary: scrub BEFORE anything touches storage. The SDK
        # redacts in the browser, but the server never trusts the client.
        raw = {
            "explanation": payload.explanation,
            "footsteps": [f.model_dump() for f in payload.footsteps],
            "metadata": dict(payload.metadata),
        }
        try:
            scrubbed, scrub_report = scrub_trace_payload(raw, scrub_policy)
        except ScrubRejection as exc:
            await _audit("stepstitch.scrub_reject", str(user_id),
                         {"fields": exc.fields, "policy": scrub_policy.name})
            raise HTTPException(
                status_code=422,
                detail={"error": "payload rejected by scrub policy", "fields": exc.fields},
            ) from exc

        if scrub_report["scrub_status"] != "clean":
            logger.info(
                "stepstitch scrubbed fields=%s policy=%s",
                scrub_report["scrubbed_fields"], scrub_report["policy"],
            )

        trace_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)
        expires = now + timedelta(days=retention_days)
        # Persist the scrub report alongside structural metadata so an operator (and a
        # compliance reviewer) can see exactly what the server stripped at ingestion.
        stored_metadata = dict(scrubbed["metadata"])
        stored_metadata["_scrub"] = scrub_report
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
                scrubbed["explanation"],
                json.dumps(scrubbed["footsteps"]),
                json.dumps(stored_metadata),
                payload.consent_version,
                expires,
                now,
            ),
        )
        logger.info("stepstitch trace stored id=%s user=%s scrub=%s",
                    trace_id, user_id, scrub_report["scrub_status"])
        return {"status": "ok", "trace_id": trace_id, "scrub": scrub_report}

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
        footsteps = _loads(row[0])
        return {
            "status": "ok",
            "trace_id": trace_id,
            "footsteps": footsteps,
            "explanation": row[1],
            "user_id": row[2],
            "project_id": row[3],
            "replayability": score_trace(footsteps),
        }

    @router.get("/session/{trace_id}/replayability")
    async def get_replayability(
        trace_id: str,
        admin: Any = Depends(require_admin),
    ) -> Dict[str, Any]:
        row = await fetchone(
            "SELECT footsteps FROM stepstitch_traces WHERE id = ?",
            (trace_id,),
        )
        if not row:
            raise HTTPException(status_code=404, detail="Trace not found")
        await _audit("stepstitch.replayability", _actor_id(admin), {"trace_id": trace_id})
        return {
            "status": "ok",
            "trace_id": trace_id,
            "replayability": score_trace(_loads(row[0])),
        }

    # --- Copilot-safe surface (read-only / draft; no delete, no SoR writes) ----

    @router.get("/session/{trace_id}/summary")
    async def get_summary(
        trace_id: str,
        admin: Any = Depends(require_admin),
    ) -> Dict[str, Any]:
        row = await fetchone(
            "SELECT footsteps, project_id FROM stepstitch_traces WHERE id = ?",
            (trace_id,),
        )
        if not row:
            raise HTTPException(status_code=404, detail="Trace not found")
        await _audit("stepstitch.summary", _actor_id(admin), {"trace_id": trace_id})
        summary = build_trace_summary(trace_id, _loads(row[0]), project_id=row[1])
        return {"status": "ok", "summary": summary.as_dict()}

    @router.get("/session/{trace_id}/diagnostic-summary")
    async def get_diagnostic_summary(
        trace_id: str,
        admin: Any = Depends(require_admin),
    ) -> Dict[str, Any]:
        row = await fetchone(
            "SELECT footsteps, project_id FROM stepstitch_traces WHERE id = ?",
            (trace_id,),
        )
        if not row:
            raise HTTPException(status_code=404, detail="Trace not found")
        await _audit("stepstitch.diagnostic_summary", _actor_id(admin),
                     {"trace_id": trace_id})
        summary = build_trace_summary(trace_id, _loads(row[0]), project_id=row[1])
        return {
            "status": "ok",
            "trace_id": trace_id,
            "diagnostic": {
                "summary": summary.as_dict(),
                "recommended_next_step": _recommended_next_step(summary),
                "never_included": [
                    "raw console logs", "raw error messages", "stack traces",
                    "request/response bodies", "headers", "cookies",
                    "input values", "screenshots", "full URLs",
                ],
            },
        }

    @router.get("/session/{trace_id}/privacy-posture")
    async def get_privacy_posture(
        trace_id: str,
        admin: Any = Depends(require_admin),
    ) -> Dict[str, Any]:
        row = await fetchone(
            "SELECT trace_metadata FROM stepstitch_traces WHERE id = ?",
            (trace_id,),
        )
        if not row:
            raise HTTPException(status_code=404, detail="Trace not found")
        await _audit("stepstitch.privacy_posture", _actor_id(admin), {"trace_id": trace_id})
        meta = _loads(row[0]) or {}
        scrub = meta.get("_scrub") if isinstance(meta, dict) else None
        return {
            "status": "ok",
            "trace_id": trace_id,
            "policy": scrub_policy.name,
            "scrub": scrub,
            "never_captured": [
                "screenshots", "video", "input values", "raw URLs", "page text",
                "request/response bodies", "console messages", "network headers",
            ],
        }

    @router.post("/session/{trace_id}/export-preview")
    async def post_export_preview(
        trace_id: str,
        admin: Any = Depends(require_admin),
    ) -> Dict[str, Any]:
        # Draft-only: builds financial-services support drafts. Sends nothing.
        row = await fetchone(
            "SELECT footsteps, project_id FROM stepstitch_traces WHERE id = ?",
            (trace_id,),
        )
        if not row:
            raise HTTPException(status_code=404, detail="Trace not found")
        await _audit("stepstitch.export_preview", _actor_id(admin), {"trace_id": trace_id})
        summary = build_trace_summary(trace_id, _loads(row[0]), project_id=row[1])
        drafts = export_preview(summary, adapters)
        return {"status": "ok", "trace_id": trace_id, "drafts": drafts}

    @router.post("/session/{trace_id}/financial-services-export-preview")
    async def post_financial_services_export_preview(
        trace_id: str,
        admin: Any = Depends(require_admin),
    ) -> Dict[str, Any]:
        row = await fetchone(
            "SELECT footsteps, project_id FROM stepstitch_traces WHERE id = ?",
            (trace_id,),
        )
        if not row:
            raise HTTPException(status_code=404, detail="Trace not found")
        await _audit("stepstitch.financial_services_export_preview", _actor_id(admin),
                     {"trace_id": trace_id})
        summary = build_trace_summary(trace_id, _loads(row[0]), project_id=row[1])
        drafts = export_preview(summary, adapters)
        return {
            "status": "ok",
            "trace_id": trace_id,
            "target_pack": "financial-services-support",
            "drafts": drafts,
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


def _recommended_next_step(summary: Any) -> str:
    if summary.failing_status is not None and summary.failing_status >= 500:
        return "Route to platform engineering with the generated Playwright repro."
    if summary.exception_type:
        return "Route to frontend engineering with the sanitized exception type and repro."
    if summary.replayability_grade in {"A", "B"}:
        return "Attach the repro to the support case and prioritize by affected workflow."
    return "Ask support to gather one more consented reproduction path before escalation."
