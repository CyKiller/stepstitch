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
import re
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Awaitable, Callable, Dict, List, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse, PlainTextResponse
from pydantic import BaseModel, ConfigDict, Field, field_validator

from .agent_packet import (
    NEVER_FROM_PRODUCTION,
    NEVER_FROM_REPORTED_SESSION,
)
from .agent_packet import build_packet as build_agent_packet
from .attestation import (
    build_attestation,
    bundle_sha256,
    canonical_bytes,
    verify_recipe,
)
from .delivery.base import DeliveryError, DeliveryService, RecordWriter
from .evidence import ASSERTED, GRADE_MEANING, MEASURED, SIGNED, TamperError, derive_grade
from .evidence import verify_bundle as verify_evidence_bundle
from .fix_memory import fingerprint as fix_fingerprint
from .fix_memory import match as fix_match
from .fragility import compute_fragility_map, minimal_repro
from .github_bridge.content import branch_name, regression_test_path
from .integrations.base import DraftAdapter, build_trace_summary, export_preview
from .metrics import summary as overview_summary
from .replayability import score_trace
from .retention import purge_expired_traces
from .scrubber import (
    FINANCIAL_SERVICES_ENTERPRISE,
    ScrubPolicy,
    ScrubRejection,
    scrub_trace_payload,
)
from .shapes import STAGE_ORDER
from .shapes import board as shape_board
from .shapes import cluster as cluster_shapes
from .verification.verdict import (
    ALL_VERDICTS,
    VERDICT_CONFIRMED_FIXED,
    derive_verdict,
)

logger = logging.getLogger("stepstitch")

# Injected callable signatures.
ExecuteFn = Callable[..., Awaitable[None]]
FetchOneFn = Callable[..., Awaitable[Optional[Any]]]
FetchAllFn = Callable[..., Awaitable[List[Any]]]
AuditFn = Callable[[str, str, Dict[str, Any]], Awaitable[None]]
# Org-wide kill switch. Returns truthy when capture is allowed. May be sync or async.
CaptureEnabledFn = Callable[[], Any]


class FootstepSchema(BaseModel):
    # extra="forbid": an unknown key on a footstep (screenshot, value, html, ...) is
    # refused with 422 at the door. Without this, pydantic silently discards unknown
    # keys — they never reach the scrubber, so they could never be rejected or even
    # counted, and a hostile client's probe would look like a clean ingest.
    model_config = ConfigDict(extra="forbid")

    timestamp: str
    # Spelled out rather than built from replayability.SUPPORTED_STEP_TYPES because mypy
    # needs Literal args at type-check time; the parity test in test_compiler.py is what
    # keeps this, the tuple, and the SDK's TypeScript union from drifting apart. A type
    # outside this set is refused with 422 at the door — the compiler would silently skip
    # it, the scorer would once have graded the wreckage A, and a hand-typed `navigate`
    # did exactly that live.
    type: Literal["navigation", "click", "input", "api_error", "exception"]
    route: str
    target: Optional[str] = None
    label: str = "[masked]"
    metadata: Optional[Dict[str, Any]] = None


class IngestTracePayload(BaseModel):
    # Same boundary as FootstepSchema: a hostile top-level key ({"cookies": ...})
    # must 422, not vanish before the scrubber can see it.
    model_config = ConfigDict(extra="forbid")

    # Neutral default for hand-rolled clients that omit it; the SDK always sets its own.
    app_id: str = "unknown"
    project_id: Optional[str] = None
    explanation: Optional[str] = None
    footsteps: List[FootstepSchema]
    consent_version: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class DeliverPayload(BaseModel):
    # Governance: a write requires a named human approver and an idempotency key.
    approved_by: str
    idempotency_key: str
    targets: Optional[List[str]] = None


class GitHubIssuePayload(BaseModel):
    approved_by: str


class GitHubPrPayload(BaseModel):
    approved_by: str
    idempotency_key: str


class AttestationCheck(BaseModel):
    """A bundle handed back for checking. ``bundle`` may be the whole issued document, or
    just the payload with the hash and signature supplied alongside it."""

    bundle: dict = {}
    bundle_sha256: Optional[str] = None
    signature: Optional[str] = None


class VerifyPayload(BaseModel):
    pre_passed: bool
    post_passed: Optional[bool] = None
    fix_ref: Optional[str] = None
    run_url: Optional[str] = None

    @field_validator("run_url")
    @classmethod
    def _http_url_only(cls, v: Optional[str]) -> Optional[str]:
        # run_url is rendered as a link in the operator dashboard; only http(s) is
        # storable so a javascript:/data: scheme can never reach the DOM (trust boundary B2).
        if v is None:
            return v
        v = v.strip()
        if not v:
            return None
        if not re.match(r"^https?://", v, re.IGNORECASE):
            raise ValueError("run_url must be an http(s) URL")
        return v


def _actor_id(actor: Any) -> str:
    if isinstance(actor, dict):
        return str(actor.get("user_id") or actor.get("id") or actor.get("sub") or "unknown")
    return str(actor)


def _loads(value: Any) -> Any:
    return json.loads(value) if isinstance(value, (str, bytes)) else value


def _safe_filename(trace_id: str, suffix: str) -> str:
    """A download filename that cannot smuggle a path or a header break out of a trace id."""
    stem = re.sub(r"[^A-Za-z0-9_-]", "_", trace_id)[:64] or "trace"
    return f"stepstitch-{stem}{suffix}"


def create_stepstitch_router(
    *,
    get_user_id: Callable[..., Any],
    require_admin: Callable[..., Any],
    require_destructive: Optional[Callable[..., Any]] = None,
    execute: ExecuteFn,
    fetchone: FetchOneFn,
    fetchall: FetchAllFn,
    audit: Optional[AuditFn] = None,
    generate_playwright_test: Callable[..., str],
    base_url: str = "http://localhost:3000",
    retention_days: int = 30,
    capture_enabled: Optional[CaptureEnabledFn] = None,
    scrub_policy: ScrubPolicy = FINANCIAL_SERVICES_ENTERPRISE,
    scrub_policy_provider: Optional[Callable[[], Any]] = None,
    repro_config_provider: Optional[Callable[[], Any]] = None,
    sign_blob: Optional[Callable[[bytes], Any]] = None,
    draft_adapters: Optional[List[DraftAdapter]] = None,
    record_writers: Optional[List[RecordWriter]] = None,
    github_bridge: Optional[Any] = None,
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

    ``draft_adapters`` are the system-of-record exporters (the built-in pack — see
    ``integrations.bundle.default_draft_adapters``). The core never imports concrete
    adapters; a host injects them (a layering rule). When none are supplied, the
    export-preview endpoints return an empty draft set (the core still serves all read-only
    operations).

    ``record_writers`` enable the OPTIONAL governed direct-write (``delivery/``). Off unless
    the host injects configured writers (which carry the system-of-record credentials in a
    closure — core stores none). When enabled, ``POST /session/{id}/deliver`` requires a
    named human approver + idempotency key, defaults to a dry run, and sends only the
    sanitized export-preview draft. It is intentionally NOT part of the MCP/Copilot agent
    surface. When no writers are injected, ``/deliver`` returns 404.
    """
    router = APIRouter(prefix="/stepstitch/v1", tags=["StepStitch"])
    adapters: List[DraftAdapter] = list(draft_adapters or [])
    # Optional governed direct-write. Disabled unless the host injects writers.
    delivery = DeliveryService(record_writers)
    # Destructive ops (deliver / delete-by-user / purge) may require a stricter gate than
    # the read surface (least privilege). A host injects require_destructive — e.g. an
    # admin-role check — and it falls back to require_admin (unchanged single-tier behavior).
    require_destructive = require_destructive or require_admin

    async def _audit(action: str, actor_id: str, detail: Dict[str, Any]) -> None:
        if audit is not None:
            try:
                await audit(action, actor_id, detail)
            except Exception:  # never let audit failure mask the request
                logger.exception("stepstitch audit failed action=%s", action)

    async def _repro_config() -> Any:
        """The project's reproduction settings, re-read per request so an operator's change
        applies without a restart. A provider failure falls back to defaults — the compiler
        degrades to a NEEDS-CONFIG checklist rather than failing to produce a test."""
        if repro_config_provider is None:
            return None
        try:
            result = repro_config_provider()
            if inspect.isawaitable(result):
                result = await result
            return result
        except Exception:
            logger.exception("stepstitch repro config unavailable; using defaults")
            return None

    async def _compile(trace_id: str, footsteps: List[Dict[str, Any]]) -> str:
        """Every compiled reproduction goes through here so project config is never skipped."""
        cfg = await _repro_config()
        return generate_playwright_test(trace_id, footsteps, base_url, config=cfg)

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
        # Resolve the active policy per-ingest: the base profile, optionally TIGHTENED by
        # operator overrides (dashboard scrub editor). A broken provider falls back to the
        # base policy so the trust boundary never weakens or fails open.
        policy = scrub_policy
        if scrub_policy_provider is not None:
            try:
                policy = await scrub_policy_provider()
            except Exception:
                logger.exception("stepstitch scrub_policy_provider failed; using base policy")
                policy = scrub_policy
        try:
            scrubbed, scrub_report = scrub_trace_payload(raw, policy)
        except ScrubRejection as exc:
            await _audit("stepstitch.scrub_reject", str(user_id),
                         {"fields": exc.fields, "policy": policy.name})
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
        # Failure Shapes: compute the structural fingerprint at ingest so the console can cluster
        # with a query rather than parsing every footsteps blob per board load. Derived purely
        # from post-scrub structural fields (templated routes, structural selectors) — no NPI —
        # and stored outside the body so the shape survives retention purge.
        ingest_summary = build_trace_summary(
            trace_id, scrubbed["footsteps"], project_id=payload.project_id)
        fp_json = json.dumps(
            fix_fingerprint(ingest_summary.as_dict(), scrubbed["footsteps"]))
        await execute(
            "INSERT INTO stepstitch_traces (id, app_id, project_id, user_id, "
            "explanation, footsteps, trace_metadata, consent_version, "
            "retention_expires_at, created_at, fingerprint) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
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
                fp_json,
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

    @router.get("/audit")
    async def list_audit(
        admin: Any = Depends(require_admin),
        action: Optional[str] = Query(None),
        trace_id: Optional[str] = Query(None),
        limit: int = Query(100, ge=1, le=500),
    ) -> Dict[str, Any]:
        # Operator-only governance read of the durable audit trail. NOT an MCP/Copilot tool —
        # the audit log is for humans proving who/what accessed evidence, never for agents.
        # The detail column carries only structural ids (trace/correlation), never NPI.
        clauses: List[str] = []
        params: List[Any] = []
        if action:
            clauses.append("action = ?")
            params.append(action)
        where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
        params.append(limit)
        rows = await fetchall(
            "SELECT id, action, actor, detail, created_at "
            f"FROM stepstitch_audit{where} ORDER BY created_at DESC LIMIT ?",
            tuple(params),
        )
        entries = []
        for r in rows:
            detail = _loads(r[3]) if r[3] else None
            # Optional client-side-style filter by trace_id without a JSON query dependency.
            if trace_id and not (isinstance(detail, dict) and detail.get("trace_id") == trace_id):
                continue
            entries.append({
                "id": r[0],
                "action": r[1],
                "actor": r[2],
                "detail": detail,
                "created_at": r[4].isoformat() if hasattr(r[4], "isoformat") else r[4],
            })
        # Reading the audit log is itself an audited admin action.
        await _audit("stepstitch.audit_read", _actor_id(admin),
                     {"action_filter": action, "trace_id": trace_id, "returned": len(entries)})
        return {"status": "ok", "entries": entries}

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

    @router.get("/correlation/{correlation_id}/summary")
    async def get_summary_by_correlation(
        correlation_id: str,
        admin: Any = Depends(require_admin),
    ) -> Dict[str, Any]:
        # Reverse lookup: a real ServiceNow incident / Salesforce case carries
        # correlation_id = "stepstitch:<trace_id>", so an operator who has the ticket can
        # resolve it back to the sanitized trace summary. Read-only and audited.
        prefix = "stepstitch:"
        if not correlation_id.startswith(prefix) or not correlation_id[len(prefix):]:
            raise HTTPException(
                status_code=400,
                detail="correlation_id must be 'stepstitch:<trace_id>'",
            )
        trace_id = correlation_id[len(prefix):]
        row = await fetchone(
            "SELECT footsteps, project_id FROM stepstitch_traces WHERE id = ?",
            (trace_id,),
        )
        if not row:
            raise HTTPException(status_code=404, detail="Trace not found")
        await _audit("stepstitch.by_correlation", _actor_id(admin),
                     {"correlation_id": correlation_id, "trace_id": trace_id})
        summary = build_trace_summary(trace_id, _loads(row[0]), project_id=row[1])
        return {
            "status": "ok",
            "trace_id": trace_id,
            "correlation_id": correlation_id,
            "summary": summary.as_dict(),
        }

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
                # One constant, shared with the agent packet, so a privacy claim cannot
                # drift between two places that both assert it.
                "never_included": list(NEVER_FROM_REPORTED_SESSION),
                "never_included_scope": (
                    "from the reported session. Evidence from the operator-configured "
                    "local reproduction is listed separately in the agent packet under "
                    "privacy_posture.from_reproduction."
                ),
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
            "never_captured": list(NEVER_FROM_PRODUCTION),
            # Present only when a strict-schema profile checked this trace: says which
            # checks ran and passed ("strict_schema_passed"), never "no NPI proven".
            "schema_status": (scrub or {}).get("schema_status"),
        }

    @router.get("/session/{trace_id}/agent-packet")
    async def get_agent_packet(
        trace_id: str,
        admin: Any = Depends(require_admin),
    ) -> Dict[str, Any]:
        # The Safe Agent Packet: one call composing the same five already-agent-safe reads
        # (summary, replayability, privacy posture, diagnostic, Playwright repro) instead of
        # five round-trips. No new capability — every field here is already individually
        # exposed as its own MCP tool; this only removes the round-trips.
        row = await fetchone(
            "SELECT footsteps, project_id, trace_metadata FROM stepstitch_traces WHERE id = ?",
            (trace_id,),
        )
        if not row:
            raise HTTPException(status_code=404, detail="Trace not found")
        await _audit("stepstitch.agent_packet", _actor_id(admin), {"trace_id": trace_id})
        footsteps = _loads(row[0])
        summary = build_trace_summary(trace_id, footsteps, project_id=row[1])
        meta = _loads(row[2]) or {}
        scrub = meta.get("_scrub") if isinstance(meta, dict) else None
        # What the LOCAL reproduction revealed, if one has been run. Read from the
        # store rather than recomputed: the runner deletes its scratch dir, so this is the
        # only copy, and it was scrubbed on the way in.
        diagnostics = None
        try:
            diag_row = await fetchone(
                "SELECT diagnostics_json FROM stepstitch_diagnostics WHERE trace_id = ? "
                "ORDER BY created_at DESC LIMIT 1", (trace_id,))
            if diag_row and diag_row[0]:
                loaded = _loads(diag_row[0])
                # Only a dict is a diagnostics record. Anything else is a legacy row or a
                # store that answered a different question, and is not worth a 500.
                diagnostics = loaded if isinstance(loaded, dict) else None
        except Exception:
            # A deployed host predating migration 0008 has no such table. Missing
            # diagnostics must never cost a caller the rest of the packet.
            logger.debug("stepstitch: no diagnostics store available", exc_info=True)

        frozen: Dict[str, Any] = {}
        try:
            # The envelope digest comes from the FREEZE ROW, not from the latest
            # diagnostics record. The old latest-diagnostics heuristic served whatever run
            # wrote last — after a re-freeze or a stray diagnostics run, that is not the
            # frozen envelope, and the packet's promise to the agent ("verification reruns
            # these bytes under the same execution envelope") was false exactly when a
            # mismatch existed to detect.
            try:
                frozen_row = await fetchone(
                    "SELECT sha256, execution_envelope_sha256 "
                    "FROM stepstitch_frozen_repros WHERE trace_id = ?", (trace_id,))
            except Exception:
                # Pre-migration host: four-column table. The packet still works.
                frozen_row = await fetchone(
                    "SELECT sha256 FROM stepstitch_frozen_repros WHERE trace_id = ?",
                    (trace_id,))
            if frozen_row:
                frozen["script_sha256"] = frozen_row[0]
                if len(frozen_row) > 1 and frozen_row[1]:
                    frozen["execution_envelope_sha256"] = frozen_row[1]
        except Exception:
            logger.debug("stepstitch: no frozen-repro store available", exc_info=True)
        if diagnostics and "execution_envelope_sha256" not in frozen:
            # Fallback for stores frozen before the envelope lived on the freeze row.
            try:
                env_row = await fetchone(
                    "SELECT execution_envelope_sha256 FROM stepstitch_diagnostics "
                    "WHERE trace_id = ? ORDER BY created_at DESC LIMIT 1", (trace_id,))
                if env_row:
                    frozen["execution_envelope_sha256"] = env_row[0]
            except Exception:
                pass

        return {
            "status": "ok",
            "trace_id": trace_id,
            "agent_packet": build_agent_packet(
                trace_id=trace_id,
                summary=summary.as_dict(),
                replayability=score_trace(footsteps),
                policy_name=scrub_policy.name,
                scrub=scrub,
                recommended_next_step=_recommended_next_step(summary),
                playwright_code=await _compile(trace_id, footsteps),
                diagnostics=diagnostics,
                frozen=frozen,
            ),
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

    @router.post("/session/{trace_id}/deliver")
    async def post_deliver(
        trace_id: str,
        payload: DeliverPayload,
        admin: Any = Depends(require_destructive),
        dry_run: bool = Query(True),
    ) -> Dict[str, Any]:
        # OPTIONAL governed direct-write. NOT an agent tool. Sends only the sanitized
        # export-preview draft, and only when explicitly approved + not a dry run.
        if not delivery.enabled:
            raise HTTPException(status_code=404, detail="direct-write is not enabled")
        if not payload.approved_by.strip():
            raise HTTPException(status_code=422, detail="approved_by is required")
        if not payload.idempotency_key.strip():
            raise HTTPException(status_code=422, detail="idempotency_key is required")

        row = await fetchone(
            "SELECT footsteps, project_id FROM stepstitch_traces WHERE id = ?",
            (trace_id,),
        )
        if not row:
            raise HTTPException(status_code=404, detail="Trace not found")
        summary = build_trace_summary(trace_id, _loads(row[0]), project_id=row[1])
        drafts = export_preview(summary, adapters)

        # Default to every target that has BOTH a draft and a configured writer.
        requested = payload.targets or [t for t in delivery.targets() if t in drafts]
        results: Dict[str, Any] = {}
        for target in requested:
            if target not in drafts:
                raise HTTPException(
                    status_code=400,
                    detail=f"no draft adapter configured for target '{target}'",
                )
            if not delivery.has(target):
                raise HTTPException(
                    status_code=400,
                    detail=f"direct-write not configured for target '{target}'",
                )
            if dry_run:
                # Exactly what would be sent — same payload as export-preview.
                results[target] = {"would_send": drafts[target]}
            else:
                try:
                    res = await delivery.deliver(
                        target, drafts[target],
                        idempotency_key=payload.idempotency_key,
                    )
                except DeliveryError as exc:
                    raise HTTPException(status_code=502, detail=str(exc)) from exc
                results[target] = res.as_dict()

        await _audit("stepstitch.deliver", _actor_id(admin), {
            "trace_id": trace_id, "targets": requested,
            "approved_by": payload.approved_by, "dry_run": dry_run,
            "idempotency_key": payload.idempotency_key,
        })
        return {"status": "ok", "trace_id": trace_id, "dry_run": dry_run, "results": results}

    @router.post("/session/{trace_id}/github/issue")
    async def post_github_issue(
        trace_id: str,
        payload: GitHubIssuePayload,
        admin: Any = Depends(require_admin),
    ) -> Dict[str, Any]:
        # Repair Loop (optional). NOT an agent tool. Creates/labels a GitHub issue from the
        # sanitized summary. Off unless a github_bridge is injected.
        if github_bridge is None:
            raise HTTPException(status_code=404, detail="github bridge is not enabled")
        if not payload.approved_by.strip():
            raise HTTPException(status_code=422, detail="approved_by is required")
        row = await fetchone(
            "SELECT footsteps, project_id FROM stepstitch_traces WHERE id = ?",
            (trace_id,),
        )
        if not row:
            raise HTTPException(status_code=404, detail="Trace not found")
        summary = build_trace_summary(trace_id, _loads(row[0]), project_id=row[1])
        receipt = await github_bridge.create_issue(summary)
        await _audit("stepstitch.github_issue", _actor_id(admin), {
            "trace_id": trace_id, "approved_by": payload.approved_by,
            "issue_number": receipt.issue_number,
        })
        return {"status": "ok", "trace_id": trace_id, "issue": receipt.as_dict()}

    @router.post("/session/{trace_id}/github/pr")
    async def post_github_pr(
        trace_id: str,
        payload: GitHubPrPayload,
        admin: Any = Depends(require_admin),
        dry_run: bool = Query(True),
    ) -> Dict[str, Any]:
        # Opens a regression-test PR (branch + committed Playwright test). Dry-run by
        # default; admin + approved_by + idempotency_key required. NEVER merges.
        if github_bridge is None:
            raise HTTPException(status_code=404, detail="github bridge is not enabled")
        if not payload.approved_by.strip():
            raise HTTPException(status_code=422, detail="approved_by is required")
        if not payload.idempotency_key.strip():
            raise HTTPException(status_code=422, detail="idempotency_key is required")
        row = await fetchone(
            "SELECT footsteps, project_id FROM stepstitch_traces WHERE id = ?",
            (trace_id,),
        )
        if not row:
            raise HTTPException(status_code=404, detail="Trace not found")
        footsteps = _loads(row[0])
        summary = build_trace_summary(trace_id, footsteps, project_id=row[1])
        repro_code = await _compile(trace_id, footsteps)
        if dry_run:
            await _audit("stepstitch.github_pr", _actor_id(admin),
                         {"trace_id": trace_id, "dry_run": True,
                          "approved_by": payload.approved_by,
                          "idempotency_key": payload.idempotency_key})
            return {
                "status": "ok", "trace_id": trace_id, "dry_run": True,
                "would_open": {
                    "branch": branch_name(trace_id),
                    "test_path": regression_test_path(trace_id),
                    "title": f"[StepStitch] regression + repro for {summary.route}",
                },
            }
        receipt = await github_bridge.open_regression_pr(
            summary, repro_code, idempotency_key=payload.idempotency_key
        )
        await _audit("stepstitch.github_pr", _actor_id(admin), {
            "trace_id": trace_id, "dry_run": False,
            "pr_number": receipt.pr_number, "approved_by": payload.approved_by,
            "idempotency_key": payload.idempotency_key,
        })
        return {"status": "ok", "trace_id": trace_id, "dry_run": False,
                "pr": receipt.as_dict()}

    @router.post("/session/{trace_id}/verify")
    async def post_verify(
        trace_id: str,
        payload: VerifyPayload,
        admin: Any = Depends(require_admin),
    ) -> Dict[str, Any]:
        # CI reports the repro outcome; StepStitch derives + stores the verdict. Nothing
        # here was observed by StepStitch, so the evidence grade is ASSERTED — the caller
        # is being trusted. (A local host that ran the frozen reproduction itself records a
        # MEASURED verification instead; see host.verify_fix.) The grade is derived, never
        # read from the payload: a caller claiming "signed" still lands here as asserted.
        row = await fetchone(
            "SELECT footsteps, project_id FROM stepstitch_traces WHERE id = ?",
            (trace_id,),
        )
        if not row:
            raise HTTPException(status_code=404, detail="Trace not found")
        verdict = derive_verdict(payload.pre_passed, payload.post_passed)
        # Fix Memory: persist the trace's structural fingerprint now, while the body still
        # exists, so a confirmed fix stays matchable after the body is purged. NPI-free.
        footsteps = _loads(row[0])
        summary = build_trace_summary(trace_id, footsteps, project_id=row[1])
        fp_json = json.dumps(fix_fingerprint(summary.as_dict(), footsteps))
        await execute(
            "INSERT INTO stepstitch_verifications (id, trace_id, pre_passed, post_passed, "
            "verdict, fix_ref, run_url, fingerprint, evidence_grade, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                str(uuid.uuid4()), trace_id, payload.pre_passed, payload.post_passed,
                verdict, payload.fix_ref, payload.run_url, fp_json,
                derive_grade(measured_by_stepstitch=False),
                datetime.now(timezone.utc),
            ),
        )
        await _audit("stepstitch.verify", _actor_id(admin), {
            "trace_id": trace_id, "verdict": verdict, "fix_ref": payload.fix_ref,
        })
        return {
            "status": "ok", "trace_id": trace_id, "verdict": verdict,
            "pre_passed": payload.pre_passed, "post_passed": payload.post_passed,
            "fix_ref": payload.fix_ref,
            "evidence_grade": derive_grade(measured_by_stepstitch=False),
            "evidence_detail": GRADE_MEANING[ASSERTED],
        }

    @router.get("/session/{trace_id}/verifications")
    async def get_verifications(
        trace_id: str,
        admin: Any = Depends(require_admin),
    ) -> Dict[str, Any]:
        exists = await fetchone(
            "SELECT footsteps FROM stepstitch_traces WHERE id = ?", (trace_id,)
        )
        if not exists:
            raise HTTPException(status_code=404, detail="Trace not found")
        rows = await fetchall(
            "SELECT trace_id, pre_passed, post_passed, verdict, fix_ref, run_url, "
            "created_at FROM stepstitch_verifications WHERE trace_id = ? "
            "ORDER BY created_at DESC",
            (trace_id,),
        )
        await _audit("stepstitch.verifications", _actor_id(admin), {"trace_id": trace_id})
        return {"status": "ok", "trace_id": trace_id,
                "verifications": [_verification_row(r) for r in rows]}

    @router.get("/session/{trace_id}/similar-fixes")
    async def get_similar_fixes(
        trace_id: str,
        admin: Any = Depends(require_admin),
        limit: int = Query(5, ge=1, le=50),
    ) -> Dict[str, Any]:
        # Fix Memory: match this trace's structural fingerprint against the verified-fix corpus
        # ("you've fixed this shape before"). Read-only, audited. Fingerprints are NPI-free
        # (templated routes + structural selectors), so this is safe on the agent surface.
        row = await fetchone(
            "SELECT footsteps, project_id FROM stepstitch_traces WHERE id = ?", (trace_id,))
        if not row:
            raise HTTPException(status_code=404, detail="Trace not found")
        footsteps = _loads(row[0])
        summary = build_trace_summary(trace_id, footsteps, project_id=row[1])
        new_fp = fix_fingerprint(summary.as_dict(), footsteps)
        # MEASURED evidence only. "You have fixed this shape before" is worth acting on
        # exactly to the degree the earlier fix was actually observed to work — a corpus
        # padded with fixes somebody merely reported would make this feature confidently
        # wrong, which is worse than not having it. Asserted rows stay in the table (they
        # are real history) but they do not get to advise anyone.
        rows = await fetchall(
            "SELECT trace_id, fix_ref, run_url, fingerprint, evidence_grade "
            "FROM stepstitch_verifications "
            "WHERE verdict = ? AND fingerprint IS NOT NULL AND evidence_grade IN (?, ?) "
            "ORDER BY created_at DESC LIMIT ?",
            ("confirmed_fixed", MEASURED, SIGNED, 500),
        )
        candidates: List[Dict[str, Any]] = []
        for r in rows:
            try:
                fp = _loads(r[3])
            except Exception:
                continue
            candidates.append(
                {"trace_id": r[0], "fix_ref": r[1], "run_url": r[2], "fingerprint": fp,
                 "evidence_grade": r[4]})
        matches = fix_match(new_fp, candidates, top_k=limit, exclude_trace_id=trace_id)
        await _audit("stepstitch.similar_fixes", _actor_id(admin),
                     {"trace_id": trace_id, "matches": len(matches)})
        return {"status": "ok", "trace_id": trace_id, "fingerprint": new_fp,
                "similar_fixes": matches,
                # Say what the corpus is, so nobody reads an empty result as "no such bug
                # has ever been fixed here" when it may mean "none were measured".
                "corpus": "measured evidence only (asserted verifications are excluded)"}

    async def _attestation_payload(trace_id: str, admin: Any) -> Dict[str, Any]:
        # Evidence Attestation: a canonical, tamper-evident bundle (scrub report + replayability
        # + verdict + sdk build) anyone can verify INDEPENDENTLY (recompute the hash; if signed,
        # cosign verify-blob with the tenant's key). Optionally signed by a host-injected signer
        # bound to the tenant's key — the service never holds a key. Read-only, audited, NPI-free.
        row = await fetchone(
            "SELECT footsteps, project_id, trace_metadata FROM stepstitch_traces WHERE id = ?",
            (trace_id,))
        if not row:
            raise HTTPException(status_code=404, detail="Trace not found")
        footsteps = _loads(row[0])
        summary = build_trace_summary(trace_id, footsteps, project_id=row[1])
        meta = _loads(row[2]) or {}
        scrub = meta.get("_scrub") if isinstance(meta, dict) else None
        sdk_build = meta.get("sdk_build") if isinstance(meta, dict) else None
        vrow = await fetchone(
            "SELECT verdict, fix_ref, run_url, evidence_grade FROM stepstitch_verifications "
            "WHERE trace_id = ? ORDER BY created_at DESC LIMIT 1", (trace_id,))
        latest = ({"verdict": vrow[0], "fix_ref": vrow[1], "run_url": vrow[2],
                   "evidence_grade": (vrow[3] if len(vrow) > 3 else ASSERTED)}
                  if vrow else None)
        bundle = build_attestation(
            trace_id,
            summary=summary.as_dict(),
            replayability=score_trace(footsteps),
            scrub=scrub,
            never_captured=[
                "screenshots", "video", "input values", "raw URLs", "page text",
                "request/response bodies", "console messages", "network headers",
            ],
            sdk_build=sdk_build,
            latest_verification=latest,
        )
        digest = bundle_sha256(bundle)
        signature = None
        if sign_blob is not None:
            try:
                result = sign_blob(canonical_bytes(bundle))
                signature = await result if inspect.isawaitable(result) else result
            except Exception:
                logger.exception("stepstitch attestation signing failed")
                signature = None
        await _audit("stepstitch.attestation", _actor_id(admin),
                     {"trace_id": trace_id, "signed": signature is not None})
        return {
            "status": "ok", "trace_id": trace_id, "bundle": bundle,
            "bundle_sha256": digest, "signature": signature,
            "signed": signature is not None, "verify_recipe": verify_recipe(trace_id),
        }

    @router.get("/session/{trace_id}/attestation")
    async def get_attestation(
        trace_id: str,
        admin: Any = Depends(require_admin),
    ) -> Dict[str, Any]:
        return await _attestation_payload(trace_id, admin)

    @router.post("/attestation/verify")
    async def verify_attestation(
        payload: AttestationCheck,
        admin: Any = Depends(require_admin),
    ) -> Dict[str, Any]:
        """Check a bundle someone hands back, and REFUSE it if it has been altered.

        Deliberately takes the document as input and consults nothing stored: the point of
        an attestation is that it can be checked without trusting the issuer, and a check
        that quietly re-derived the answer from our own database would prove nothing about
        the copy in the caller's hand. It re-canonicalises and rehashes exactly what it was
        given.

        A mismatch is a 422 with a plain statement, not a field on a 200 — a caller that
        forgets to read a boolean must not sail past a forged bundle.
        """
        document = dict(payload.bundle or {})
        if payload.bundle_sha256 and "bundle_sha256" not in document:
            document["bundle_sha256"] = payload.bundle_sha256
        if payload.signature and "signature" not in document:
            document["signature"] = payload.signature
        try:
            result = verify_evidence_bundle(document)
        except TamperError as exc:
            await _audit("stepstitch.attestation_verify", _actor_id(admin),
                         {"verified": False})
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        await _audit("stepstitch.attestation_verify", _actor_id(admin),
                     {"verified": True, "grade": result["evidence_grade"]})
        return {"status": "ok", **result}

    @router.get("/session/{trace_id}/attestation/download")
    async def download_attestation(
        trace_id: str,
        admin: Any = Depends(require_admin),
    ) -> JSONResponse:
        """The same evidence bundle as a file. An attestation is only useful if it can leave
        the console — attached to a ticket, checked into a repo, handed to an auditor."""
        payload = await _attestation_payload(trace_id, admin)
        filename = _safe_filename(trace_id, "-attestation.json")
        return JSONResponse(
            content=payload,
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    @router.get("/session/{trace_id}/fragility")
    async def get_fragility(
        trace_id: str,
        admin: Any = Depends(require_admin),
    ) -> Dict[str, Any]:
        # Fragility Radar: which steps are most likely to break (selector brittleness +
        # templated routes), ranked worst-first. Read-only, audited, NPI-free.
        row = await fetchone(
            "SELECT footsteps FROM stepstitch_traces WHERE id = ?", (trace_id,))
        if not row:
            raise HTTPException(status_code=404, detail="Trace not found")
        await _audit("stepstitch.fragility", _actor_id(admin), {"trace_id": trace_id})
        return {"status": "ok", "trace_id": trace_id, **compute_fragility_map(_loads(row[0]))}

    @router.get("/session/{trace_id}/minimal-repro")
    async def get_minimal_repro(
        trace_id: str,
        admin: Any = Depends(require_admin),
    ) -> Dict[str, Any]:
        # The smallest failing path (drops unrelated-route detours), compiled to Playwright.
        row = await fetchone(
            "SELECT footsteps FROM stepstitch_traces WHERE id = ?", (trace_id,))
        if not row:
            raise HTTPException(status_code=404, detail="Trace not found")
        mr = minimal_repro(_loads(row[0]))
        code = await _compile(trace_id, mr["footsteps"])
        await _audit("stepstitch.minimal_repro", _actor_id(admin),
                     {"trace_id": trace_id, "reduced_steps": mr["reduced_steps"]})
        return {
            "status": "ok", "trace_id": trace_id,
            "original_steps": mr["original_steps"], "reduced_steps": mr["reduced_steps"],
            "reduction_ratio": mr["reduction_ratio"], "playwright_code": code,
        }

    @router.get("/corpus")
    async def get_corpus(
        admin: Any = Depends(require_admin),
        verdict: str = Query("confirmed_fixed"),
        limit: int = Query(50, ge=1, le=500),
    ) -> Dict[str, Any]:
        # The regression corpus: every reproduced failure with the given verdict.
        if verdict not in ALL_VERDICTS:
            raise HTTPException(
                status_code=422, detail=f"unknown verdict '{verdict}'"
            )
        rows = await fetchall(
            "SELECT trace_id, pre_passed, post_passed, verdict, fix_ref, run_url, "
            "created_at FROM stepstitch_verifications WHERE verdict = ? "
            "ORDER BY created_at DESC LIMIT ?",
            (verdict, limit),
        )
        await _audit("stepstitch.corpus", _actor_id(admin), {"verdict": verdict})
        return {"status": "ok", "verdict": verdict,
                "entries": [_verification_row(r) for r in rows]}

    async def _load_shapes(limit: int) -> List[Dict[str, Any]]:
        """Read traces + their verdicts + the corpus, and cluster into failure shapes.

        All three reads are structural only — fingerprints, verdicts, fix refs — so nothing here
        can surface a trace body. The clustering itself lives in the pure `shapes` module.
        """
        trace_rows = await fetchall(
            "SELECT id, fingerprint, created_at FROM stepstitch_traces "
            "WHERE fingerprint IS NOT NULL ORDER BY created_at DESC LIMIT ?",
            (limit,),
        )
        verdict_rows = await fetchall(
            "SELECT trace_id, verdict FROM stepstitch_verifications "
            "ORDER BY created_at DESC LIMIT ?",
            (limit * 10,),
        )
        verdicts_by_trace: Dict[str, List[str]] = {}
        for row in verdict_rows:
            verdicts_by_trace.setdefault(row[0], []).append(row[1])

        corpus_rows = await fetchall(
            "SELECT trace_id, fix_ref, run_url, fingerprint FROM stepstitch_verifications "
            "WHERE verdict = ? AND fingerprint IS NOT NULL ORDER BY created_at DESC LIMIT ?",
            (VERDICT_CONFIRMED_FIXED, 500),
        )
        corpus: List[Dict[str, Any]] = []
        for row in corpus_rows:
            try:
                fp = _loads(row[3])
            except Exception:
                continue
            corpus.append({"trace_id": row[0], "fix_ref": row[1], "run_url": row[2],
                           "fingerprint": fp})

        traces: List[Dict[str, Any]] = []
        for row in trace_rows:
            try:
                fp = _loads(row[1])
            except Exception:
                continue
            created = row[2]
            traces.append({
                "trace_id": row[0],
                "fingerprint": fp,
                "created_at": created.isoformat() if hasattr(created, "isoformat") else created,
                "verdicts": verdicts_by_trace.get(row[0], []),
            })
        # Default match weights, same as /similar-fixes — one notion of "similar" everywhere.
        return cluster_shapes(traces, corpus=corpus)

    def _recent_days(span: int = 30) -> List[str]:
        """The chart's x-axis: `span` dates ending today, oldest first.

        Built here rather than inferred from the data so a day on which nothing broke is
        still a zero on the chart. Inferring the axis from the traces themselves would
        silently drop quiet days and make a bad week look like a busy one.
        """
        today = datetime.now(timezone.utc).date()
        return [(today - timedelta(days=n)).isoformat() for n in range(span - 1, -1, -1)]

    @router.get("/shapes")
    async def list_shapes(
        admin: Any = Depends(require_admin),
        limit: int = Query(200, ge=1, le=1000),
    ) -> Dict[str, Any]:
        # Failure Shapes: traces grouped by what actually broke, arranged into the pipeline
        # columns derived from the verdict state machine. Forty reports of one bug is one shape.
        shapes = await _load_shapes(limit)
        await _audit("stepstitch.shapes", _actor_id(admin), {"shapes": len(shapes)})
        return {"status": "ok", "stages": list(STAGE_ORDER), "shapes": shapes,
                "board": shape_board(shapes),
                # The overview's arithmetic is computed here, by the tested `metrics` module,
                # rather than re-derived by whichever client is drawing it. A dashboard that
                # quietly computes the wrong number is worse than no dashboard, and the only
                # way that stays true is if the code under test is the code that runs.
                "overview": overview_summary(shapes, _recent_days(), STAGE_ORDER)}

    @router.get("/shapes/{shape_id}")
    async def get_shape(
        shape_id: str,
        admin: Any = Depends(require_admin),
        limit: int = Query(200, ge=1, le=1000),
    ) -> Dict[str, Any]:
        shapes = await _load_shapes(limit)
        for shape in shapes:
            if shape["shape_id"] == shape_id:
                await _audit("stepstitch.shape", _actor_id(admin), {"shape_id": shape_id})
                return {"status": "ok", "shape": shape}
        raise HTTPException(status_code=404, detail="Shape not found")

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
        code = await _compile(trace_id, footsteps)
        return {"status": "ok", "trace_id": trace_id, "playwright_code": code}

    @router.get("/session/{trace_id}/playwright/download")
    async def download_compiled_repro(
        trace_id: str,
        admin: Any = Depends(require_admin),
    ) -> PlainTextResponse:
        """The reproduction as a ready-to-commit ``.spec.ts``. StepStitch does not run it —
        the engineer or CI does, which is why getting it out of the console matters."""
        row = await fetchone(
            "SELECT footsteps FROM stepstitch_traces WHERE id = ?", (trace_id,))
        if not row:
            raise HTTPException(status_code=404, detail="Trace not found")
        await _audit("stepstitch.compile_download", _actor_id(admin), {"trace_id": trace_id})
        code = await _compile(trace_id, _loads(row[0]))
        filename = _safe_filename(trace_id, "-repro.spec.ts")
        return PlainTextResponse(
            content=code,
            media_type="text/plain; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    @router.delete("/session/by-user/{target_user_id}")
    async def delete_user_traces(
        target_user_id: str,
        admin: Any = Depends(require_destructive),
    ) -> Dict[str, Any]:
        # Right-to-delete: remove trace bodies AND their diagnostics. The diagnostics are
        # keyed by trace_id with no foreign key, so without the explicit cascade this
        # endpoint audit-logged a deletion, returned ok, and left the single richest
        # per-trace record in the store — orphaned and unreachable by any code path, which
        # is not deleted, only lost. Diagnostics go first, while the trace rows still
        # exist to resolve the join.
        try:
            await execute(
                "DELETE FROM stepstitch_diagnostics WHERE trace_id IN ("
                "SELECT id FROM stepstitch_traces WHERE user_id = ?)", (target_user_id,))
        except Exception:
            logger.debug("stepstitch: no diagnostics table to purge", exc_info=True)
        await execute("DELETE FROM stepstitch_traces WHERE user_id = ?", (target_user_id,))
        await _audit("stepstitch.delete_by_user", _actor_id(admin),
                     {"target_user_id": target_user_id})
        return {"status": "ok", "deleted_user_id": target_user_id}

    @router.post("/maintenance/purge-expired")
    async def purge_expired(
        admin: Any = Depends(require_destructive),
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


def _verification_row(r: Any) -> Dict[str, Any]:
    return {
        "trace_id": r[0],
        "pre_passed": r[1],
        "post_passed": r[2],
        "verdict": r[3],
        "fix_ref": r[4],
        "run_url": r[5],
        "created_at": r[6].isoformat() if hasattr(r[6], "isoformat") else r[6],
    }
