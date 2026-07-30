"""StepStitch Local storage: the SQLite store satisfies the same seam as Postgres.

Two layers of proof, neither needing Postgres or any service running:

1. The shared storage round-trip (``storage_suite.py``) — the same behavior contract the
   real-Postgres gate runs — passes against ``server/localdb.py`` on a real on-disk file.
2. The full host runs over the local store: ingest over HTTP, operator reads, agent
   registration and scope enforcement, and the admin purge endpoint — the golden path a
   ``stepstitch start`` developer exercises.
"""
import asyncio

from fastapi import FastAPI
from fastapi.testclient import TestClient

from server.audit import make_db_audit
from server.auth import build_auth
from server.host import build_app
from server.localdb import build_local_db_callables, connect_local, local_path_from_dsn
from server.tests.storage_suite import storage_roundtrip

ADMIN = "admin-secret"
INGEST = "ingest-secret"
_PFX = "/api/stepstitch/v1"

_PAYLOAD = {
    "app_id": "demo",
    "footsteps": [{"timestamp": "t", "type": "api_error", "route": "/accounts/:id",
                   "label": "[masked]", "metadata": {"status": 500}}],
    "metadata": {"sdk_version": "0.4.0"},
}


def _bearer(tok):
    return {"Authorization": f"Bearer {tok}"}


def test_local_store_passes_the_shared_storage_suite(tmp_path):
    conn = connect_local(tmp_path / "local.db")
    try:
        execute, fetchone, fetchall = build_local_db_callables(conn)
        asyncio.run(storage_roundtrip(execute, fetchone, fetchall))
    finally:
        conn.close()


def test_dsn_parsing_accepts_only_sqlite():
    assert str(local_path_from_dsn("sqlite:///x/y.db")).endswith("x/y.db")
    try:
        local_path_from_dsn("postgres://u:p@db/x")
    except ValueError:
        pass
    else:  # pragma: no cover - the assertion is the point
        raise AssertionError("a non-sqlite DSN must be refused")


def test_host_golden_path_over_the_local_store(tmp_path):
    conn = connect_local(tmp_path / "local.db")
    get_user_id, require_admin = build_auth(ADMIN, INGEST)
    execute, fetchone, fetchall = build_local_db_callables(conn)
    app: FastAPI = build_app(
        get_user_id=get_user_id, require_admin=require_admin,
        execute=execute, fetchone=fetchone, fetchall=fetchall,
        audit=make_db_audit(execute),   # durable trail, like production wiring
        admin_token=ADMIN, ingest_token=INGEST,
    )
    client = TestClient(app)

    # Ingest over HTTP lands in SQLite; the operator can read it back.
    r = client.post(f"{_PFX}/session", json=_PAYLOAD, headers=_bearer(INGEST))
    assert r.status_code == 200, r.text
    tid = r.json()["trace_id"]
    assert client.get(f"{_PFX}/session/{tid}/summary",
                      headers=_bearer(ADMIN)).status_code == 200

    # Agent registration + scope enforcement work over the local store: a summaries-
    # scoped token reads summaries, and is refused outside its scope (admin surface).
    reg = client.post("/admin/agents", json={"name": "repro-bot", "scope": "summaries"},
                      headers=_bearer(ADMIN))
    assert reg.status_code == 200, reg.text
    agent_token = reg.json()["token"]
    assert client.get(f"{_PFX}/session/{tid}/summary",
                      headers=_bearer(agent_token)).status_code == 200
    assert client.get("/admin/agents", headers=_bearer(agent_token)).status_code in (401, 403)

    # The audit trail recorded the agent's read (durable, queryable).
    audit = client.get(f"{_PFX}/audit", headers=_bearer(ADMIN))
    assert audit.status_code == 200
    assert any(e["action"] == "stepstitch.agent_access" for e in audit.json()["entries"])

    # The admin retention purge endpoint runs its SQL against SQLite without error.
    purge = client.post(f"{_PFX}/maintenance/purge-expired", headers=_bearer(ADMIN))
    assert purge.status_code == 200

    conn.close()


def test_local_mode_app_creation_needs_no_postgres_and_no_tokens(tmp_path, monkeypatch):
    """``STEPSTITCH_MODE=local`` builds a working app from a bare environment."""
    monkeypatch.setenv("STEPSTITCH_MODE", "local")
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path}/local.db")
    monkeypatch.delenv("STEPSTITCH_INGEST_TOKEN", raising=False)
    monkeypatch.delenv("STEPSTITCH_ADMIN_TOKEN", raising=False)

    from server.app import create_app_from_env

    app = create_app_from_env()
    ingest = app.state.local_ingest_token
    admin = app.state.local_admin_token
    assert ingest and admin and ingest != admin

    with TestClient(app) as client:  # runs lifespan: purge loop start/stop, conn close
        r = client.post(f"{_PFX}/session", json=_PAYLOAD, headers=_bearer(ingest))
        assert r.status_code == 200, r.text
        tid = r.json()["trace_id"]
        assert client.get(f"{_PFX}/session/{tid}/summary",
                          headers=_bearer(admin)).status_code == 200
        # Generated credentials are real gates, not decoration.
        assert client.get(f"{_PFX}/session/{tid}/summary",
                          headers=_bearer("wrong")).status_code == 401
