"""StepStitch ingest host — mounts create_stepstitch_router into a FastAPI app.

This is the thin host StepStitch's service library needs to run as a standalone product
(the library injects auth + DB; it ships no server of its own). ``build_app`` is pure and
testable (inject fakes); ``server.app`` wires it to asyncpg + env for deployment.
"""
from __future__ import annotations

import logging
from typing import Any, Awaitable, Callable, List, Optional

from fastapi import FastAPI

from stepstitch_service import create_stepstitch_router, generate_playwright_test
from stepstitch_service.profiles import load_profile

logger = logging.getLogger("stepstitch.host")


def build_app(
    *,
    get_user_id: Callable[..., Any],
    require_admin: Callable[..., Any],
    execute: Callable[..., Awaitable[Any]],
    fetchone: Callable[..., Awaitable[Any]],
    fetchall: Callable[..., Awaitable[Any]],
    profile: str = "financial-services-enterprise",
    retention_days: int = 30,
    draft_adapters: Optional[List[Any]] = None,
    lifespan: Any = None,
) -> FastAPI:
    """Build the ingest API. ``draft_adapters`` is the optional commercial pack."""

    async def audit(action: str, actor: str, detail: dict) -> None:
        # Demo: audit to logs. PRODUCTION: persist to a separate 5-year store
        # (Reg S-P recordkeeping) — see contracts/stepstitch.md "Retention (split clocks)".
        logger.info("stepstitch.audit action=%s actor=%s detail=%s", action, actor, detail)

    router = create_stepstitch_router(
        get_user_id=get_user_id,
        require_admin=require_admin,
        execute=execute,
        fetchone=fetchone,
        fetchall=fetchall,
        audit=audit,
        generate_playwright_test=generate_playwright_test,
        retention_days=retention_days,
        scrub_policy=load_profile(profile),
        draft_adapters=draft_adapters,
    )

    app = FastAPI(title="StepStitch ingest API", lifespan=lifespan)
    app.include_router(router, prefix="/api")

    @app.get("/healthz")
    async def healthz() -> dict:  # Railway healthcheck target
        return {"status": "ok"}

    return app
