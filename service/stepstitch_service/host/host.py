"""StepStitch ingest host — mounts create_stepstitch_router into a FastAPI app.

This is the thin host StepStitch's service library needs to run as a standalone product
(the library injects auth + DB; it ships no server of its own). ``build_app`` is pure and
testable (inject fakes); ``server.app`` wires it to asyncpg + env for deployment.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import re
import secrets
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, List, Optional

from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse
from pydantic import BaseModel

from stepstitch_service import create_stepstitch_router, generate_playwright_test
from stepstitch_service.compiler import DEFAULT_BASE_URL
from stepstitch_service.diagnostics import SOURCE_SYNTHETIC, EnvelopeMismatch
from stepstitch_service.profiles import load_profile
from stepstitch_service.repro_config import ReproConfig, ReproConfigError, readiness
from stepstitch_service.scrubber import (
    ScrubPolicy,
    compile_extra_redactions,
    derive_policy,
    redact_text,
)

from .agents import (
    list_agents,
    register_agent,
    resolve_agent,
    revoke_agent,
    scope_allows,
)
from .auth import _bearer
from .demo import dashboard_csp, render_dashboard
from .metrics import Metrics

_SERVICE_PREFIX = "/api/stepstitch/v1"


class AgentRegistration(BaseModel):
    name: str
    scope: str = "summaries"


class ScrubConfig(BaseModel):
    extra_redactions: list = []      # list of [label, regex] pairs
    extra_forbidden_keys: list = []  # list of metadata key names to additionally drop


class ScrubPreview(BaseModel):
    text: str = ""
    extra_redactions: Optional[list] = None  # preview candidate patterns (unsaved)


class ReproduceRequest(BaseModel):
    """Ask the local host to run a session's reproduction. Bounds are enforced again in
    the runner; these defaults keep a console click from tying up the machine."""

    runs: int = 1
    timeout_seconds: int = 120


class ReproConfigBody(BaseModel):
    """The reproduction-config document. Validated by ``ReproConfig.from_dict``, which is
    where the real rules live (including the refusal to store anything credential-shaped)."""

    config: dict = {}


def apply_scrub_overrides(base: ScrubPolicy, cfg: dict) -> ScrubPolicy:
    """Compose the base profile with operator overrides. Both fields only TIGHTEN: extra
    patterns add redaction, extra keys add drops. A malformed entry is dropped, never able
    to loosen the base. Pure + testable."""
    extra_red = tuple(
        (str(p[0]), str(p[1]))
        for p in (cfg.get("extra_redactions") or [])
        if isinstance(p, (list, tuple)) and len(p) == 2
    )
    extra_keys = frozenset(str(k) for k in (cfg.get("extra_forbidden_keys") or []))
    return derive_policy(base, extra_redactions=extra_red, extra_forbidden_keys=extra_keys)


def _actor_name(admin: Any) -> str:
    if isinstance(admin, dict):
        return str(admin.get("user_id") or admin.get("sub") or "admin")
    return str(admin)

logger = logging.getLogger("stepstitch.host")


def build_app(
    *,
    get_user_id: Callable[..., Any],
    require_admin: Callable[..., Any],
    require_destructive: Optional[Callable[..., Any]] = None,
    execute: Callable[..., Awaitable[Any]],
    fetchone: Callable[..., Awaitable[Any]],
    fetchall: Callable[..., Awaitable[Any]],
    profile: str = "financial-services-enterprise",
    retention_days: int = 30,
    draft_adapters: Optional[List[Any]] = None,
    record_writers: Optional[List[Any]] = None,
    github_bridge: Optional[Any] = None,
    audit: Optional[Callable[..., Awaitable[Any]]] = None,
    lifespan: Any = None,
    admin_token: Optional[str] = None,
    ingest_token: Optional[str] = None,
    sign_blob: Optional[Callable[..., Any]] = None,
    base_url: Optional[str] = None,
    local_mode: bool = False,
) -> FastAPI:
    """Build the ingest API. ``draft_adapters`` are the injected (Apache-2.0) adapters;
    ``record_writers`` enable the optional governed direct-write; ``audit`` is the audit
    sink (defaults to logging — a deployment should pass a durable store)."""

    if audit is None:
        async def audit(action: str, actor: str, detail: dict) -> None:
            # Default: audit to logs. PRODUCTION: pass a durable sink (server/audit.py)
            # on a separate 5-year clock (Reg S-P) — see contracts/stepstitch.md.
            logger.info("stepstitch.audit action=%s actor=%s detail=%s",
                        action, actor, detail)

    base_policy = load_profile(profile)

    async def _read_scrub_overrides() -> dict:
        row = await fetchone(
            "SELECT value FROM stepstitch_config WHERE key = ?", ("scrub_overrides",))
        if not row or not row[0]:
            return {}
        try:
            return json.loads(row[0]) or {}
        except Exception:
            return {}

    async def _scrub_policy_provider() -> ScrubPolicy:
        # The base profile, optionally TIGHTENED by stored operator overrides. Never weakens
        # the base; a read/parse failure falls back to the base policy.
        return apply_scrub_overrides(base_policy, await _read_scrub_overrides())

    # The application under test. Env-supplied (STEPSTITCH_BASE_URL) and overridable per
    # project by the stored repro config; without either, the compiler's localhost default.
    effective_base_url = (base_url or DEFAULT_BASE_URL).rstrip("/")

    async def _read_repro_config() -> ReproConfig:
        """Stored project reproduction settings. A missing or corrupt row is not fatal —
        repro generation must never break because config could not be read."""
        try:
            row = await fetchone(
                "SELECT value FROM stepstitch_config WHERE key = ?", ("repro_config",))
        except Exception:
            return ReproConfig()
        if not row or not row[0]:
            return ReproConfig()
        try:
            return ReproConfig.from_dict(json.loads(row[0]))
        except (ValueError, TypeError):
            logger.warning("stepstitch: stored repro_config is invalid; ignoring it")
            return ReproConfig()

    router = create_stepstitch_router(
        get_user_id=get_user_id,
        require_admin=require_admin,
        require_destructive=require_destructive,
        execute=execute,
        fetchone=fetchone,
        fetchall=fetchall,
        audit=audit,
        generate_playwright_test=generate_playwright_test,
        base_url=effective_base_url,
        retention_days=retention_days,
        scrub_policy=base_policy,
        scrub_policy_provider=_scrub_policy_provider,
        repro_config_provider=_read_repro_config,
        sign_blob=sign_blob,
        draft_adapters=draft_adapters,
        record_writers=record_writers,
        github_bridge=github_bridge,
    )

    app = FastAPI(title="StepStitch ingest API", lifespan=lifespan)
    app.include_router(router, prefix="/api")

    metrics = Metrics()

    @app.middleware("http")
    async def _observe(request, call_next):
        start = time.perf_counter()
        response = await call_next(request)
        elapsed = time.perf_counter() - start
        # Use the matched route TEMPLATE so trace ids never become label values. On an
        # unmatched path (404) record a constant sentinel rather than the raw URL, so junk
        # paths can't blow up metric label cardinality.
        route = request.scope.get("route")
        route_path = getattr(route, "path", None) or "<unmatched>"
        metrics.observe(request.method, route_path, response.status_code, elapsed)
        logger.info(json.dumps({
            "evt": "http", "method": request.method, "route": route_path,
            "status": response.status_code, "ms": round(elapsed * 1000, 2),
        }))
        # Baseline hardening on every response (a route may set stricter ones, e.g. the
        # dashboard's CSP). setdefault so a handler-supplied header is never clobbered.
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        response.headers.setdefault("X-Frame-Options", "DENY")
        return response

    @app.get("/healthz")
    async def healthz() -> dict:  # Railway healthcheck target
        # `revision` lets the post-deploy verifier confirm WHICH commit is serving, not
        # just that something answers. Railway injects RAILWAY_GIT_COMMIT_SHA; other
        # platforms can set STEPSTITCH_REVISION. Absent both, be honest about it.
        revision = (
            os.environ.get("RAILWAY_GIT_COMMIT_SHA")
            or os.environ.get("STEPSTITCH_REVISION")
            or "unknown"
        )
        return {"status": "ok", "revision": revision}

    @app.get("/metrics", response_class=PlainTextResponse)
    async def metrics_endpoint() -> str:
        return metrics.render()

    @app.get("/dashboard")
    async def dashboard() -> HTMLResponse:
        # Read-only operator UI; calls only the read/draft endpoints with the admin token
        # the operator supplies in the browser. No data is embedded server-side. A per-
        # request nonce gates the single inline <script>; default-src 'none' blocks every
        # other resource load, shrinking the blast radius of any markup-injection bug.
        # One template, two mount points (the demo console renders the same string against
        # its own read-only API) — see server/demo.py. The typeface is embedded, never
        # fetched, which is why font-src data: grants no network reach here.
        nonce = secrets.token_urlsafe(16)
        return HTMLResponse(
            content=render_dashboard(nonce, demo=False),
            headers={"Content-Security-Policy": dashboard_csp(nonce)},
        )

    @app.get("/admin/status")
    async def admin_status(admin: Any = Depends(require_admin)) -> dict:
        # Operator health strip: cheap counts + the active privacy posture. Admin-gated.
        async def _count(table: str) -> int:
            row = await fetchone(f"SELECT count(*) FROM {table}", ())
            return int(row[0]) if row else 0

        active = await fetchone(
            "SELECT count(*) FROM stepstitch_agents WHERE revoked = ?", (False,))
        repro_cfg = await _read_repro_config()
        return {
            "status": "ok",
            "profile": profile,
            "retention_days": retention_days,
            # Setup-checklist signals. Without a base URL every generated reproduction points
            # at localhost:3000 and cannot run in CI, so the console surfaces this directly.
            "base_url_configured": bool(
                repro_cfg.base_url or effective_base_url != DEFAULT_BASE_URL
            ),
            "repro_config_ready": bool(
                (repro_cfg.base_url or effective_base_url != DEFAULT_BASE_URL)
                and not repro_cfg.is_empty()
            ),
            "traces": await _count("stepstitch_traces"),
            "audit_events": await _count("stepstitch_audit"),
            "agents_total": await _count("stepstitch_agents"),
            "agents_active": int(active[0]) if active else 0,
            # Whether CI has ever reported a repro outcome. The console's setup checklist reads
            # this to know if the loop is closed — without it, the verified-fix corpus can never
            # fill and Fix Memory has nothing to match against.
            "verifications": await _count("stepstitch_verifications"),
            # StepStitch Local pairing. In local mode the credentials are generated, so the
            # console can hand the developer a ready-to-paste snippet instead of asking them
            # to copy a token out of a terminal. Gated three ways: local mode only, admin
            # only, and loopback-only binding — a deployed host never returns this.
            "local_mode": local_mode,
            "local_ingest_token": ingest_token if local_mode else None,
        }

    # --- Scrub-policy editor (operator config; only ever TIGHTENS the base profile) ---
    @app.get("/admin/config/scrub")
    async def get_scrub_config(admin: Any = Depends(require_admin)) -> dict:
        cfg = await _read_scrub_overrides()
        return {
            "status": "ok",
            "base_profile": base_policy.name,
            "extra_redactions": cfg.get("extra_redactions", []),
            "extra_forbidden_keys": cfg.get("extra_forbidden_keys", []),
        }

    @app.put("/admin/config/scrub")
    async def put_scrub_config(req: ScrubConfig, admin: Any = Depends(require_admin)) -> dict:
        patterns = []
        for item in req.extra_redactions:
            if not (isinstance(item, (list, tuple)) and len(item) == 2):
                raise HTTPException(status_code=400,
                                    detail="each redaction must be [label, regex]")
            label, raw = str(item[0]), str(item[1])
            try:
                re.compile(raw)  # reject the whole save on a bad pattern
            except re.error as exc:
                raise HTTPException(status_code=400,
                                    detail=f"invalid regex for '{label}': {exc}")
            patterns.append([label, raw])
        keys = [str(k) for k in req.extra_forbidden_keys]
        cfg = {"extra_redactions": patterns, "extra_forbidden_keys": keys}
        await execute("DELETE FROM stepstitch_config WHERE key = ?", ("scrub_overrides",))
        await execute(
            "INSERT INTO stepstitch_config (key, value, updated_at, updated_by) "
            "VALUES (?, ?, ?, ?)",
            ("scrub_overrides", json.dumps(cfg), datetime.now(timezone.utc),
             _actor_name(admin)),
        )
        await audit("stepstitch.scrub_config_update", _actor_name(admin),
                    {"patterns": len(patterns), "forbidden_keys": len(keys)})
        return {"status": "ok", **cfg}

    # --- Reproduction config (project settings the compiler needs; never credentials) ---
    @app.get("/admin/config/repro")
    async def get_repro_config(admin: Any = Depends(require_admin)) -> dict:
        cfg = await _read_repro_config()
        return {
            "status": "ok",
            "config": cfg.as_dict(),
            # The env-supplied fallback, so the console can show where repros point today
            # even when no project override is stored.
            "env_base_url": effective_base_url if effective_base_url != DEFAULT_BASE_URL else None,
            "default_base_url": DEFAULT_BASE_URL,
            # Trace-independent readiness (no footsteps → base URL + auth only).
            "readiness": readiness(
                cfg, [],
                fallback_base_url=(
                    effective_base_url if effective_base_url != DEFAULT_BASE_URL else None
                ),
            ),
        }

    @app.put("/admin/config/repro")
    async def put_repro_config(
        req: ReproConfigBody, admin: Any = Depends(require_admin)
    ) -> dict:
        # Validation lives in the service core so the rules (including the refusal to store
        # anything credential-shaped) are the same wherever config arrives from.
        try:
            cfg = ReproConfig.from_dict(req.config)
        except ReproConfigError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        doc = cfg.as_dict()
        await execute("DELETE FROM stepstitch_config WHERE key = ?", ("repro_config",))
        await execute(
            "INSERT INTO stepstitch_config (key, value, updated_at, updated_by) "
            "VALUES (?, ?, ?, ?)",
            ("repro_config", json.dumps(doc), datetime.now(timezone.utc),
             _actor_name(admin)),
        )
        # Audit the SHAPE of the change, never the values.
        await audit("stepstitch.repro_config_update", _actor_name(admin),
                    {"settings": sorted(doc.keys()),
                     "route_params": len(cfg.route_params),
                     "input_values": len(cfg.input_by_selector) + len(cfg.input_by_kind)})
        return {"status": "ok", "config": doc}

    @app.post("/admin/scrub/preview")
    async def scrub_preview(req: ScrubPreview, admin: Any = Depends(require_admin)) -> dict:
        # Preview UNSAVED candidate patterns when supplied; else the active saved policy.
        if req.extra_redactions is not None:
            policy = apply_scrub_overrides(base_policy,
                                           {"extra_redactions": req.extra_redactions})
        else:
            policy = await _scrub_policy_provider()
        redacted, kinds = redact_text(req.text or "", compile_extra_redactions(policy))
        return {"status": "ok", "input": req.text, "redacted": redacted, "kinds": kinds}

    # --- Reproduce locally (StepStitch Local only) --------------------------------------
    # Executing a browser test is a local-developer action, not something a deployed,
    # multi-tenant host should do on request: it spawns processes and reaches the network.
    # So the route exists ONLY in local mode, where the host is the developer's own machine
    # bound to loopback. A deployed host has no such endpoint at all.
    if local_mode:

        @app.post("/admin/session/{trace_id}/reproduce")
        async def reproduce_locally(trace_id: str, req: ReproduceRequest,
                                    admin: Any = Depends(require_admin)) -> dict:
            from ..runner import RunnerError, run_reproduction

            row = await fetchone(
                "SELECT footsteps FROM stepstitch_traces WHERE id = ?", (trace_id,))
            if not row:
                raise HTTPException(status_code=404, detail="Trace not found")
            footsteps = json.loads(row[0]) if isinstance(row[0], str) else row[0]
            cfg = await _read_repro_config()
            app_url = cfg.base_url or effective_base_url
            script = generate_playwright_test(trace_id, footsteps, app_url, config=cfg)
            items = readiness(cfg, footsteps, fallback_base_url=effective_base_url)

            await audit("stepstitch.reproduce", _actor_name(admin),
                        {"trace_id": trace_id, "runs": req.runs})
            try:
                result = await asyncio.to_thread(
                    run_reproduction,
                    session_id=trace_id, script=script, base_url=app_url,
                    readiness=items, runs=req.runs, timeout_seconds=req.timeout_seconds,
                )
            except (RunnerError, EnvelopeMismatch) as exc:
                # A refusal is an answer, not a server fault: say what and why.
                return {"status": "refused", "detail": str(exc)}
            payload = result.as_dict()
            payload["status"] = "ok"
            return payload

        async def _store_diagnostics(trace_id: str, result: Any) -> None:
            """Persist what the synthetic run revealed, if anything.

            The runner deletes its scratch directory when a run ends, so this is the only
            place the record survives. Diagnostics are the extra, never the product: a
            failure to store them must not disturb a verdict that was correctly measured.
            """
            record = getattr(result, "diagnostics", None)
            if not record:
                return
            try:
                await execute(
                    "INSERT INTO stepstitch_diagnostics (id, trace_id, run_id, source, "
                    "schema_version, script_sha256, execution_envelope_sha256, "
                    "diagnostics_json, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (str(uuid.uuid4()), trace_id, str(uuid.uuid4()),
                     record.get("source", SOURCE_SYNTHETIC),
                     int(record.get("schema_version", 1)),
                     result.script_sha256, result.execution_envelope_sha256,
                     json.dumps(record), datetime.now(timezone.utc)),
                )
            except Exception:
                logger.warning("stepstitch: could not store reproduction diagnostics",
                               exc_info=True)

        # --- The agent loop: freeze, hand off, then judge with the frozen bytes ---------
        @app.post("/admin/session/{trace_id}/freeze")
        async def freeze_reproduction(trace_id: str, req: ReproduceRequest,
                                      admin: Any = Depends(require_admin)) -> dict:
            """Record the exact reproduction that will judge a fix, and measure the red run.

            Called before handing a session to an agent. Without a measured red run there
            is nothing to prove a fix against, so this runs the reproduction first and
            stores what it observed — the verdict is never taken on trust later.
            """
            from ..fixcheck import failure_signature
            from ..runner import REPRODUCED, RunnerError, run_reproduction

            row = await fetchone(
                "SELECT footsteps FROM stepstitch_traces WHERE id = ?", (trace_id,))
            if not row:
                raise HTTPException(status_code=404, detail="Trace not found")
            footsteps = json.loads(row[0]) if isinstance(row[0], str) else row[0]
            cfg = await _read_repro_config()
            app_url = cfg.base_url or effective_base_url
            script = generate_playwright_test(trace_id, footsteps, app_url, config=cfg)
            items = readiness(cfg, footsteps, fallback_base_url=effective_base_url)

            try:
                red = await asyncio.to_thread(
                    run_reproduction,
                    session_id=trace_id, script=script, base_url=app_url,
                    readiness=items, runs=req.runs, timeout_seconds=req.timeout_seconds,
                    # The red run is where the failure is actually present, so it is the
                    # run worth inspecting deeply — a green run has nothing to diagnose.
                    diagnostics=True,
                )
            except (RunnerError, EnvelopeMismatch) as exc:
                return {"status": "refused", "detail": str(exc)}

            signature = ""
            for attempt in red.runs:
                if not attempt.passed and attempt.transcript:
                    signature = failure_signature(attempt.transcript)
                    if signature:
                        break

            await _store_diagnostics(trace_id, red)

            digest = hashlib.sha256(script.encode("utf-8")).hexdigest()
            now = datetime.now(timezone.utc)
            await execute("DELETE FROM stepstitch_frozen_repros WHERE trace_id = ?",
                          (trace_id,))
            await execute(
                "INSERT INTO stepstitch_frozen_repros (trace_id, script, sha256, "
                "red_verdict, red_signature, frozen_at, frozen_by) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (trace_id, script, digest, red.verdict, signature, now,
                 _actor_name(admin)),
            )
            await audit("stepstitch.freeze", _actor_name(admin),
                        {"trace_id": trace_id, "sha256": digest,
                         "red_verdict": red.verdict})
            return {
                "status": "ok", "trace_id": trace_id, "script_sha256": digest,
                "red": red.as_dict(),
                "ready_for_agent": red.verdict == REPRODUCED,
                "detail": (
                    "the failure was measured and the test is frozen — an agent may change "
                    "the application, not this test."
                    if red.verdict == REPRODUCED else
                    "the failure was NOT observed, so there is nothing to prove a fix "
                    f"against yet: {red.detail}"
                ),
            }

        @app.post("/admin/session/{trace_id}/verify-fix")
        async def verify_fix(trace_id: str, req: ReproduceRequest,
                             admin: Any = Depends(require_admin)) -> dict:
            """Rerun the frozen reproduction after a change and say what was observed."""
            from ..fixcheck import FIXED, UNABLE_TO_VERIFY, derive_fix_verdict
            from ..runner import RunnerError, run_reproduction

            frozen = await fetchone(
                "SELECT script, sha256, red_verdict, red_signature "
                "FROM stepstitch_frozen_repros WHERE trace_id = ?", (trace_id,))
            if not frozen:
                return {
                    "status": "ok", "verdict": UNABLE_TO_VERIFY,
                    "detail": "nothing is frozen for this session. Freeze the reproduction "
                              "first so the same test judges before and after the change.",
                }
            script, digest, red_verdict, red_signature = (
                frozen[0], frozen[1], frozen[2], frozen[3] or "")

            cfg = await _read_repro_config()
            app_url = cfg.base_url or effective_base_url
            try:
                after = await asyncio.to_thread(
                    run_reproduction,
                    session_id=trace_id, script=script, base_url=app_url,
                    # The freeze enforced: these bytes, or nothing.
                    expected_sha256=digest,
                    readiness=readiness(cfg, [], fallback_base_url=effective_base_url),
                    runs=req.runs, timeout_seconds=req.timeout_seconds,
                )
            except (RunnerError, EnvelopeMismatch) as exc:
                return {"status": "refused", "detail": str(exc)}

            verdict = derive_fix_verdict(red_verdict=red_verdict,
                                         red_signature=red_signature, after=after)

            # A fix StepStitch watched fail and then pass belongs in the corpus as MEASURED
            # evidence — the whole point of the local runner. Only a real red-to-green is
            # recorded: 'still failing', 'different failure' and 'unable to verify' are not
            # fixes, and writing them here would quietly inflate the corpus.
            if verdict.verdict == FIXED:
                from ..evidence import derive_grade
                from ..fix_memory import fingerprint as fix_fingerprint
                from ..integrations.base import build_trace_summary

                trace_row = await fetchone(
                    "SELECT footsteps, project_id FROM stepstitch_traces WHERE id = ?",
                    (trace_id,))
                fp_json = None
                if trace_row:
                    steps = (json.loads(trace_row[0])
                             if isinstance(trace_row[0], str) else trace_row[0])
                    summary = build_trace_summary(trace_id, steps,
                                                  project_id=trace_row[1])
                    fp_json = json.dumps(fix_fingerprint(summary.as_dict(), steps))
                await execute(
                    "INSERT INTO stepstitch_verifications (id, trace_id, pre_passed, "
                    "post_passed, verdict, fix_ref, run_url, fingerprint, evidence_grade, "
                    "created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (str(uuid.uuid4()), trace_id, False, True, "confirmed_fixed",
                     None, None, fp_json,
                     # measured_by_stepstitch=True: both runs happened here, under the
                     # frozen script, with no caller asked to vouch for either.
                     derive_grade(measured_by_stepstitch=True),
                     datetime.now(timezone.utc)),
                )

            await audit("stepstitch.verify_fix", _actor_name(admin),
                        {"trace_id": trace_id, "verdict": verdict.verdict,
                         "sha256": digest})
            payload = verdict.as_dict()
            payload["status"] = "ok"
            return payload

    # --- Agent connections (named, scoped tokens) -------------------------------------
    # Only available in shared-admin-token mode (the host must have an admin token to
    # translate an allowed agent request into). When enabled, a registered agent's token
    # is scope-checked here; allowed requests run as admin for that one call, disallowed
    # ones are refused 403 — the service router and its auth never change.
    if admin_token:

        @app.middleware("http")
        async def _enforce_agent_scope(request, call_next):
            path = request.url.path
            if path.startswith(_SERVICE_PREFIX):
                token = _bearer(request.headers.get("authorization"))
                if token and token != admin_token and token != ingest_token:
                    agent = await resolve_agent(fetchone, token)
                    if agent is not None:
                        if scope_allows(agent["scope"], request.method, path):
                            # Translate to admin access for this single request.
                            request.scope["headers"] = [
                                (k, v) for (k, v) in request.scope["headers"]
                                if k != b"authorization"
                            ] + [(b"authorization", f"Bearer {admin_token}".encode())]
                            await audit("stepstitch.agent_access", agent["name"], {
                                "agent_id": agent["id"], "scope": agent["scope"],
                                "method": request.method, "path": path,
                            })
                        else:
                            await audit("stepstitch.agent_denied", agent["name"], {
                                "agent_id": agent["id"], "scope": agent["scope"],
                                "method": request.method, "path": path,
                            })
                            return JSONResponse(
                                status_code=403,
                                content={"detail": (
                                    f"agent scope '{agent['scope']}' is not permitted to "
                                    f"access {request.method} {path}"
                                )},
                            )
            return await call_next(request)

        @app.post("/admin/agents")
        async def create_agent(req: AgentRegistration,
                               admin: Any = Depends(require_admin)) -> dict:
            try:
                agent_id, token = await register_agent(
                    execute, name=req.name, scope=req.scope, actor=_actor_name(admin),
                )
            except ValueError as exc:
                raise HTTPException(status_code=400, detail=str(exc))
            await audit("stepstitch.agent_register", _actor_name(admin),
                        {"agent_id": agent_id, "scope": req.scope})
            return {
                "status": "ok", "id": agent_id, "name": req.name.strip(),
                "scope": req.scope, "token": token,
                "note": "Copy this token now — it is shown only once and stored only as a hash.",
            }

        @app.get("/admin/agents")
        async def get_agents(admin: Any = Depends(require_admin)) -> dict:
            return {"status": "ok", "agents": await list_agents(fetchall)}

        @app.post("/admin/agents/{agent_id}/revoke")
        async def revoke(agent_id: str, admin: Any = Depends(require_admin)) -> dict:
            await revoke_agent(execute, agent_id)
            await audit("stepstitch.agent_revoke", _actor_name(admin), {"agent_id": agent_id})
            return {"status": "ok", "id": agent_id, "revoked": True}

    return app
