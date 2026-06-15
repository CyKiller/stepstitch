"""StepStitch ingest host proof — auth gating + DB wiring, with in-memory fakes.

No live Postgres needed: ``build_app`` takes the DB callables directly, so we pass the
same in-memory fake the service tests use and exercise the real auth + router wiring.
"""
from fastapi import FastAPI
from fastapi.testclient import TestClient

from server.auth import build_auth
from server.db import translate_placeholders
from server.host import build_app

ADMIN = "admin-secret"
INGEST = "ingest-secret"
_PFX = "/api/stepstitch/v1"


def test_translate_placeholders_to_asyncpg():
    assert translate_placeholders("WHERE a = ? AND b = ?") == "WHERE a = $1 AND b = $2"
    assert translate_placeholders("SELECT 1") == "SELECT 1"


def test_build_auth_requires_both_tokens():
    import pytest
    with pytest.raises(ValueError):
        build_auth("", INGEST)
    with pytest.raises(ValueError):
        build_auth(ADMIN, "")


class QueryAwareDB:
    def __init__(self):
        self.rows = {}

    async def execute(self, query, params=()):
        if query.strip().upper().startswith("INSERT"):
            self.rows[params[0]] = {
                "app_id": params[1], "project_id": params[2], "user_id": params[3],
                "explanation": params[4], "footsteps": params[5],
                "trace_metadata": params[6],
            }

    async def fetchone(self, query, params=()):
        row = self.rows.get(params[0])
        if not row:
            return None
        q = " ".join(query.split())
        if q.startswith("SELECT footsteps, project_id"):
            return (row["footsteps"], row["project_id"])
        if q.startswith("SELECT trace_metadata"):
            return (row["trace_metadata"],)
        if q.startswith("SELECT footsteps FROM"):
            return (row["footsteps"],)
        return (row["footsteps"], row["explanation"], row["user_id"],
                row["project_id"], None)

    async def fetchall(self, query, params=()):
        return []


def _client():
    db = QueryAwareDB()
    get_user_id, require_admin = build_auth(ADMIN, INGEST)
    app: FastAPI = build_app(
        get_user_id=get_user_id, require_admin=require_admin,
        execute=db.execute, fetchone=db.fetchone, fetchall=db.fetchall,
    )
    return TestClient(app), db


_PAYLOAD = {
    "app_id": "demo",
    "footsteps": [
        {"timestamp": "t", "type": "api_error", "route": "/accounts/:id",
         "label": "[masked]", "metadata": {"status": 500}},
    ],
    "metadata": {"sdk_version": "0.4.0"},
}


def test_healthz_open():
    client, _ = _client()
    assert client.get("/healthz").json() == {"status": "ok"}


def test_dashboard_served_readonly():
    client, _ = _client()
    r = client.get("/dashboard")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/html")
    body = r.text
    # It is the operator UI and targets the read-only API base; no embedded data/secrets.
    assert "StepStitch" in body and "/api/stepstitch/v1" in body
    assert "read-only operator view" in body


def test_ingest_requires_bearer():
    client, _ = _client()
    assert client.post(f"{_PFX}/session", json=_PAYLOAD).status_code == 401
    ok = client.post(f"{_PFX}/session", json=_PAYLOAD,
                     headers={"Authorization": f"Bearer {INGEST}"})
    assert ok.status_code == 200
    assert ok.json()["scrub"]["scrub_status"] in {"clean", "scrubbed"}


def test_operator_read_requires_admin_not_ingest():
    client, _ = _client()
    tid = client.post(f"{_PFX}/session", json=_PAYLOAD,
                      headers={"Authorization": f"Bearer {INGEST}"}).json()["trace_id"]
    # Ingest token cannot read the operator surface.
    assert client.get(f"{_PFX}/session/{tid}/summary",
                      headers={"Authorization": f"Bearer {INGEST}"}).status_code == 401
    # Admin token can.
    r = client.get(f"{_PFX}/session/{tid}/summary",
                   headers={"Authorization": f"Bearer {ADMIN}"})
    assert r.status_code == 200
    assert r.json()["summary"]["failing_status"] == 500


def test_build_app_accepts_github_bridge():
    from server.host import build_app
    get_user_id, require_admin = build_auth(ADMIN, INGEST)

    class _DB:
        async def execute(self, q, p=()):
            return None
        async def fetchone(self, q, p=()):
            return None
        async def fetchall(self, q, p=()):
            return []

    db = _DB()
    sentinel = object()
    app = build_app(
        get_user_id=get_user_id, require_admin=require_admin,
        execute=db.execute, fetchone=db.fetchone, fetchall=db.fetchall,
        github_bridge=sentinel,
    )
    assert app is not None
