"""Deployment entrypoint: ``uvicorn server.app:app`` (the StepStitch ingest API).

Reads configuration from the environment (see docs/DEPLOY.md), opens an asyncpg pool on
startup, ensures the schema, and mounts the StepStitch router. Importing this module
requires the env to be set, so tests import ``server.host`` / ``server.db`` / ``server.auth``
directly instead.
"""
from __future__ import annotations

import asyncio
import os
import pathlib
from contextlib import asynccontextmanager

from .audit import make_db_audit
from .auth import build_auth
from .db import build_db_callables
from .host import build_app
from .oidc import oidc_auth_from_env
from .retention_job import logger as retention_logger
from .retention_job import purge_interval_from_env, run_purge_loop

_ALEMBIC_INI = pathlib.Path(__file__).resolve().parent / "alembic.ini"


def _run_migrations() -> None:
    """Apply Alembic ``upgrade head`` over the sync psycopg2 engine.

    env.py reads DATABASE_URL from the environment, so this stays decoupled from the
    asyncpg runtime pool. Run inside an executor so the sync work never blocks the loop.
    """
    from alembic import command
    from alembic.config import Config

    cfg = Config(str(_ALEMBIC_INI))
    command.upgrade(cfg, "head")


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
    ingest_token = os.environ["STEPSTITCH_INGEST_TOKEN"]
    profile = os.environ.get("STEPSTITCH_PROFILE", "financial-services-enterprise")
    retention_days = int(os.environ.get("RETENTION_DAYS", "30"))
    enable_adapters = os.environ.get("STEPSTITCH_ENABLE_ADAPTERS", "1").lower() in (
        "1", "true", "yes",
    )

    proxy = _PoolProxy()
    # FI-grade deployments set STEPSTITCH_OIDC_ISSUER -> per-operator SSO (any standards-
    # compliant OIDC issuer); otherwise fall back to the demo shared-bearer admin token.
    require_destructive = None
    if os.environ.get("STEPSTITCH_OIDC_ISSUER"):
        get_user_id, require_admin, require_destructive = oidc_auth_from_env(ingest_token)
    else:
        get_user_id, require_admin = build_auth(
            os.environ["STEPSTITCH_ADMIN_TOKEN"], ingest_token)
    execute, fetchone, fetchall = build_db_callables(proxy)
    audit = make_db_audit(execute)  # durable audit trail (stepstitch_audit table)

    draft_adapters = None
    if enable_adapters:  # the built-in adapters (Apache-2.0); the core never imports them
        from stepstitch_service.integrations.bundle import default_draft_adapters
        draft_adapters = default_draft_adapters()

    purge_interval = purge_interval_from_env()

    @asynccontextmanager
    async def lifespan(app):
        import asyncpg

        proxy.pool = await asyncpg.create_pool(dsn=database_url, min_size=1, max_size=10)
        # Bring the schema to head before serving traffic. Migrations run on a sync
        # psycopg2 engine (env.py reads DATABASE_URL), driven in a thread so the sync
        # work doesn't block the event loop.
        await asyncio.get_running_loop().run_in_executor(None, _run_migrations)
        # Automatic retention enforcement: spawn the periodic body-purge loop after the
        # schema is at head. RETENTION_PURGE_INTERVAL_SECONDS=0 disables it (operators
        # who prefer the admin-triggered endpoint only).
        purge_task = None
        if purge_interval > 0:
            purge_task = asyncio.create_task(
                run_purge_loop(
                    execute=execute,
                    fetchone=fetchone,
                    interval_seconds=purge_interval,
                )
            )
        else:
            retention_logger.info(
                "stepstitch retention auto-purge disabled "
                "(RETENTION_PURGE_INTERVAL_SECONDS=0)"
            )
        try:
            yield
        finally:
            # Cancel/await the purge task BEFORE closing the pool so an in-flight purge
            # isn't cut off mid-query by a closed pool. The loop re-raises CancelledError,
            # which we swallow here so shutdown stays clean.
            if purge_task is not None:
                purge_task.cancel()
                try:
                    await purge_task
                except asyncio.CancelledError:
                    pass
            await proxy.pool.close()

    return build_app(
        get_user_id=get_user_id,
        require_admin=require_admin,
        require_destructive=require_destructive,
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
