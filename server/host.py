"""StepStitch ingest host — mounts create_stepstitch_router into a FastAPI app.

This is the thin host StepStitch's service library needs to run as a standalone product
(the library injects auth + DB; it ships no server of its own). ``build_app`` is pure and
testable (inject fakes); ``server.app`` wires it to asyncpg + env for deployment.
"""
from __future__ import annotations

import json
import logging
import secrets
import time
from typing import Any, Awaitable, Callable, List, Optional

from fastapi import FastAPI
from fastapi.responses import HTMLResponse, PlainTextResponse

from stepstitch_service import create_stepstitch_router, generate_playwright_test
from stepstitch_service.profiles import load_profile

from .dashboard import DASHBOARD_HTML
from .metrics import Metrics

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

    router = create_stepstitch_router(
        get_user_id=get_user_id,
        require_admin=require_admin,
        require_destructive=require_destructive,
        execute=execute,
        fetchone=fetchone,
        fetchall=fetchall,
        audit=audit,
        generate_playwright_test=generate_playwright_test,
        retention_days=retention_days,
        scrub_policy=load_profile(profile),
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
        html = DASHBOARD_HTML.replace("__CSP_NONCE__", nonce)
        csp = (
            "default-src 'none'; "
            f"script-src 'nonce-{nonce}'; "
            "style-src 'unsafe-inline'; "
            "connect-src 'self'; "
            "img-src 'self' data:; "
            "base-uri 'none'; "
            "frame-ancestors 'none'; "
            "form-action 'none'"
        )
        return HTMLResponse(content=html, headers={"Content-Security-Policy": csp})

    return app
