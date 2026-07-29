"""StepStitch ingest host — mounts create_stepstitch_router into a FastAPI app.

This is the thin host StepStitch's service library needs to run as a standalone product
(the library injects auth + DB; it ships no server of its own). ``build_app`` is pure and
testable (inject fakes); ``server.app`` wires it to asyncpg + env for deployment.
"""
from __future__ import annotations

import json
import logging
import re
import secrets
import time
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, List, Optional

from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse
from pydantic import BaseModel
from stepstitch_service import create_stepstitch_router, generate_playwright_test
from stepstitch_service.compiler import DEFAULT_BASE_URL
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
from .dashboard import DASHBOARD_HTML
from .fonts import GEIST_SANS_WOFF2_B64
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
        return {"status": "ok"}

    @app.get("/metrics", response_class=PlainTextResponse)
    async def metrics_endpoint() -> str:
        return metrics.render()

    @app.get("/dashboard")
    async def dashboard() -> HTMLResponse:
        # Read-only operator UI; calls only the read/draft endpoints with the admin token
        # the operator supplies in the browser. No data is embedded server-side. A per-
        # request nonce gates the single inline <script>; default-src 'none' blocks every
        # other resource load, shrinking the blast radius of any markup-injection bug.
        nonce = secrets.token_urlsafe(16)
        html = (
            DASHBOARD_HTML
            .replace("__CSP_NONCE__", nonce)
            # The typeface is embedded, not fetched — see server/fonts.py and the font-src
            # directive below.
            .replace("__FONT_SANS_B64__", GEIST_SANS_WOFF2_B64)
        )
        csp = (
            "default-src 'none'; "
            f"script-src 'nonce-{nonce}'; "
            "style-src 'unsafe-inline'; "
            "connect-src 'self'; "
            "img-src 'self' data:; "
            # The typeface is embedded in the page as a data: URI, never fetched. This
            # directive grants no network reach — `default-src 'none'` still blocks every
            # origin — it only permits the bytes already inside the document to be used.
            "font-src data:; "
            "base-uri 'none'; "
            "frame-ancestors 'none'; "
            "form-action 'none'"
        )
        return HTMLResponse(content=html, headers={"Content-Security-Policy": csp})

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
