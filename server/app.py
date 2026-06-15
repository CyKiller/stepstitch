"""Deployment entrypoint: ``uvicorn server.app:app`` (the StepStitch ingest API).

Reads configuration from the environment (see docs/DEPLOY.md), opens an asyncpg pool on
startup, ensures the schema, and mounts the StepStitch router. Importing this module
requires the env to be set, so tests import ``server.host`` / ``server.db`` / ``server.auth``
directly instead.
"""
from __future__ import annotations

import os
from contextlib import asynccontextmanager

from .audit import make_db_audit
from .auth import build_auth
from .db import build_db_callables, ensure_schema
from .host import build_app


class _PoolProxy:
    """Forwards execute/fetchrow/fetch to a pool created at app startup (lifespan)."""

    pool = None

    async def execute(self, *a, **k):
        return await self.pool.execute(*a, **k)

    async def fetchrow(self, *a, **k):
        return await self.pool.fetchrow(*a, **k)

    async def fetch(self, *a, **k):
        return await self.pool.fetch(*a, **k)


def create_app_from_env():
    database_url = os.environ["DATABASE_URL"]
    admin_token = os.environ["STEPSTITCH_ADMIN_TOKEN"]
    ingest_token = os.environ["STEPSTITCH_INGEST_TOKEN"]
    profile = os.environ.get("STEPSTITCH_PROFILE", "financial-services-enterprise")
    retention_days = int(os.environ.get("RETENTION_DAYS", "30"))
    enable_adapters = os.environ.get("STEPSTITCH_ENABLE_ADAPTERS", "1").lower() in (
        "1", "true", "yes",
    )

    proxy = _PoolProxy()
    get_user_id, require_admin = build_auth(admin_token, ingest_token)
    execute, fetchone, fetchall = build_db_callables(proxy)
    audit = make_db_audit(execute)  # durable audit trail (stepstitch_audit table)

    draft_adapters = None
    if enable_adapters:  # the built-in adapters (Apache-2.0); the core never imports them
        from stepstitch_service.integrations.bundle import default_draft_adapters
        draft_adapters = default_draft_adapters()

    @asynccontextmanager
    async def lifespan(app):
        import asyncpg

        proxy.pool = await asyncpg.create_pool(dsn=database_url, min_size=1, max_size=10)
        await ensure_schema(proxy.pool)
        try:
            yield
        finally:
            await proxy.pool.close()

    return build_app(
        get_user_id=get_user_id,
        require_admin=require_admin,
        execute=execute,
        fetchone=fetchone,
        fetchall=fetchall,
        profile=profile,
        retention_days=retention_days,
        draft_adapters=draft_adapters,
        audit=audit,
        lifespan=lifespan,
    )


app = create_app_from_env()
