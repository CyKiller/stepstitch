"""StepStitch Local: the one-command, single-developer mode behind ``stepstitch start``.

SQLite storage, loopback-only bind, generated credentials, no Postgres/Alembic/Docker —
the same host (``build_app``) production runs, wired for one developer's machine. The
storage seam is identical to production (three async callables, ``?`` placeholders);
only the implementation behind it changes (``localdb.py``).

Pairing: the dashboard normally asks the operator to paste the admin bearer. Locally the
credentials are generated, so ``start`` opens ``/dashboard#ss=<admin-token>`` — the page
adopts the token into sessionStorage and strips the fragment. The fragment never leaves
the machine (loopback bind) and never reaches server logs (fragments aren't sent in
requests).
"""
from __future__ import annotations

import asyncio
import os
import secrets
import threading
import urllib.request
import webbrowser
from contextlib import asynccontextmanager

from .audit import make_db_audit
from .auth import build_auth
from .host import build_app
from .localdb import build_local_db_callables, connect_local, local_path_from_dsn
from .retention_job import purge_interval_from_env, run_purge_loop

DEFAULT_LOCAL_DSN = "sqlite:///.stepstitch/local.db"
# Deliberately not 3000/8000/8080: `start` runs NEXT TO the developer's own app and the
# common dev-server ports must stay free for it.
DEFAULT_LOCAL_PORT = 8321


def create_local_app_from_env():
    """Build the local app from the environment (``STEPSTITCH_MODE=local``).

    Tokens may be pre-set (CI does this to make runs reproducible) or are generated so a
    bare local app never starts unauthenticated. Generated values are exposed on
    ``app.state`` for ``start`` to surface — never logged.
    """
    dsn = os.environ.get("DATABASE_URL", DEFAULT_LOCAL_DSN)
    db_path = local_path_from_dsn(dsn)
    ingest_token = os.environ.get("STEPSTITCH_INGEST_TOKEN") or secrets.token_urlsafe(24)
    admin_token = os.environ.get("STEPSTITCH_ADMIN_TOKEN") or secrets.token_urlsafe(24)
    profile = os.environ.get("STEPSTITCH_PROFILE", "open-source-default")
    base_url = os.environ.get("STEPSTITCH_APP_BASE_URL")
    retention_days = int(os.environ.get("RETENTION_DAYS", "30"))

    conn = connect_local(db_path)
    execute, fetchone, fetchall = build_local_db_callables(conn)
    get_user_id, require_admin = build_auth(admin_token, ingest_token)
    audit = make_db_audit(execute)
    purge_interval = purge_interval_from_env()

    @asynccontextmanager
    async def lifespan(app):
        purge_task = None
        if purge_interval > 0:
            purge_task = asyncio.create_task(
                run_purge_loop(execute=execute, fetchone=fetchone,
                               interval_seconds=purge_interval)
            )
        try:
            yield
        finally:
            if purge_task is not None:
                purge_task.cancel()
                try:
                    await purge_task
                except asyncio.CancelledError:
                    pass
            conn.close()

    app = build_app(
        get_user_id=get_user_id,
        require_admin=require_admin,
        execute=execute,
        fetchone=fetchone,
        fetchall=fetchall,
        profile=profile,
        retention_days=retention_days,
        audit=audit,
        lifespan=lifespan,
        admin_token=admin_token,
        ingest_token=ingest_token,
        base_url=base_url,
        local_mode=True,
    )
    # For `stepstitch start` to surface — not logged.
    app.state.local_admin_token = admin_token
    app.state.local_ingest_token = ingest_token
    app.state.local_db_path = str(db_path)
    return app


def _open_when_ready(url: str, health_url: str, timeout_s: float = 20.0) -> None:
    """Poll ``/healthz`` from a daemon thread, then open the browser once."""

    def _poll() -> None:
        import time

        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            try:
                with urllib.request.urlopen(health_url, timeout=1):
                    webbrowser.open(url)
                    return
            except OSError:
                time.sleep(0.25)

    threading.Thread(target=_poll, daemon=True).start()


def _connect_when_ready(agent: str, port: int, admin: str,
                        timeout_s: float = 20.0) -> None:
    """Register a coding agent from a daemon thread once ``/healthz`` answers.

    This is the flag the docs and the connect error message promise: one process starts
    the host, issues the scoped token, registers the agent, verifies the connection, and
    keeps serving. It has to wait for readiness because registration is an HTTP call to
    the very server this process is about to start — and it must be a daemon thread so a
    hung probe can never keep the host alive after Ctrl+C.
    """

    def _poll() -> None:
        import time

        health_url = f"http://127.0.0.1:{port}/healthz"
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            try:
                with urllib.request.urlopen(health_url, timeout=1):
                    break
            except OSError:
                time.sleep(0.25)
        else:
            print(f"\nCould not connect {agent}: the host did not answer /healthz "
                  f"within {int(timeout_s)}s.", flush=True)
            return
        import sys

        from stepstitch_service.cli import connect_agent

        print(f"\nConnecting {agent}…", flush=True)
        rc = connect_agent(f"http://127.0.0.1:{port}", admin, agent)
        if rc == 0:
            print("The host keeps running; the agent is ready to use.", flush=True)
        # connect_agent's own progress lines do not pass flush=True, and stdout is
        # block-buffered when it is not a tty — piped or nohup'd, they would otherwise sit
        # invisible until the server EXITS, which is when they stop being useful. The same
        # trap the pairing block above already documents for itself.
        sys.stdout.flush()

    threading.Thread(target=_poll, daemon=True).start()


def run_local(*, port: int = DEFAULT_LOCAL_PORT, db: str | None = None,
              open_browser: bool = True, connect: str | None = None) -> int:
    """Run StepStitch Local: build the app, print the pairing block, serve on loopback."""
    try:
        import uvicorn
    except ImportError:
        print(
            "stepstitch start needs uvicorn, which ships in the [local] extra:\n"
            "  pip install 'stepstitch-service[local]'\n"
            "(or: uvx --from 'stepstitch-service[local]' stepstitch start)"
        )
        return 2

    os.environ["STEPSTITCH_MODE"] = "local"
    if db:
        os.environ["DATABASE_URL"] = f"sqlite:///{db}"

    app = create_local_app_from_env()
    admin = app.state.local_admin_token
    ingest = app.state.local_ingest_token
    dashboard_url = f"http://127.0.0.1:{port}/dashboard#ss={admin}"

    # The one place the generated credentials are shown. Loopback-only, this terminal.
    # flush=True because stdout is block-buffered when it is not a tty: piped through
    # `tee`, or captured by CI, the dashboard link would otherwise not appear until the
    # server exits — which is exactly when it stops being useful.
    print(
        "StepStitch Local\n"
        f"  Dashboard:     {dashboard_url}\n"
        f"  Ingest token:  {ingest}\n"
        f"  Local store:   {app.state.local_db_path}\n"
        "  Bound to 127.0.0.1 only. Ctrl+C stops it; the store persists.",
        flush=True,
    )

    if open_browser:
        _open_when_ready(dashboard_url, f"http://127.0.0.1:{port}/healthz")
    if connect:
        _connect_when_ready(connect, port, admin)

    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")
    return 0
