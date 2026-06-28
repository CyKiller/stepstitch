"""Agent-scope enforcement in the host (named scoped tokens).

A registered agent's token is scope-checked at the host: an allowed request runs as admin
for that one call; a disallowed one is refused 403. The service router never changes. The
admin-management routes themselves require the real admin token (an agent token can't reach
them). Uses in-memory fakes — no live Postgres.
"""
from fastapi import FastAPI
from fastapi.testclient import TestClient

from server.auth import build_auth
from server.host import build_app

ADMIN = "admin-secret"
INGEST = "ingest-secret"
_PFX = "/api/stepstitch/v1"


class FakeDB:
    def __init__(self):
        self.traces = {}
        self.agents = {}

    async def execute(self, query, params=()):
        q = " ".join(query.split()).upper()
        if q.startswith("INSERT INTO STEPSTITCH_TRACES"):
            self.traces[params[0]] = {
                "project_id": params[2], "user_id": params[3], "explanation": params[4],
                "footsteps": params[5], "trace_metadata": params[6],
            }
        elif q.startswith("INSERT INTO STEPSTITCH_AGENTS"):
            self.agents[params[0]] = {
                "id": params[0], "name": params[1], "token_hash": params[2],
                "scope": params[3], "revoked": params[4], "created_at": params[5],
                "created_by": params[6],
            }
        elif q.startswith("UPDATE STEPSTITCH_AGENTS SET REVOKED"):
            self.agents[params[1]]["revoked"] = params[0]
        # stepstitch_audit INSERTs are ignored (audit defaults to logging here).

    async def fetchone(self, query, params=()):
        q = " ".join(query.split())
        if "FROM stepstitch_agents" in q:
            for a in self.agents.values():
                if a["token_hash"] == params[0]:
                    return (a["id"], a["name"], a["scope"], a["revoked"])
            return None
        row = self.traces.get(params[0])
        if not row:
            return None
        if q.startswith("SELECT footsteps, project_id"):
            return (row["footsteps"], row["project_id"])
        if q.startswith("SELECT trace_metadata"):
            return (row["trace_metadata"],)
        if q.startswith("SELECT footsteps FROM"):
            return (row["footsteps"],)
        return (row["footsteps"], row["explanation"], row["user_id"], row["project_id"], None)

    async def fetchall(self, query, params=()):
        if "FROM stepstitch_agents" in " ".join(query.split()):
            return [
                (a["id"], a["name"], a["scope"], a["revoked"], a["created_at"], a["created_by"])
                for a in self.agents.values()
            ]
        return []


def _client():
    db = FakeDB()
    get_user_id, require_admin = build_auth(ADMIN, INGEST)
    app: FastAPI = build_app(
        get_user_id=get_user_id, require_admin=require_admin,
        execute=db.execute, fetchone=db.fetchone, fetchall=db.fetchall,
        admin_token=ADMIN, ingest_token=INGEST,
    )
    return TestClient(app), db


def _bearer(tok):
    return {"Authorization": f"Bearer {tok}"}


def _ingest(client):
    r = client.post(f"{_PFX}/session", headers=_bearer(INGEST), json={
        "app_id": "demo",
        "footsteps": [{"timestamp": "t", "type": "api_error", "route": "/accounts/:id",
                       "label": "[masked]", "metadata": {"status": 500}}],
        "metadata": {"sdk_version": "0.4.0"},
    })
    assert r.status_code == 200, r.text
    return r.json()["trace_id"]


def _register(client, name, scope):
    r = client.post("/admin/agents", headers=_bearer(ADMIN), json={"name": name, "scope": scope})
    assert r.status_code == 200, r.text
    return r.json()


def test_scoped_token_gates_reads_by_tier():
    client, _ = _client()
    tid = _ingest(client)

    summaries = _register(client, "Copilot summaries", "summaries")["token"]
    repros = _register(client, "Claude repros", "repros")["token"]

    # summaries tier: summary OK, playwright denied.
    ok = client.get(f"{_PFX}/session/{tid}/summary", headers=_bearer(summaries))
    assert ok.status_code == 200
    denied = client.get(f"{_PFX}/session/{tid}/playwright", headers=_bearer(summaries))
    assert denied.status_code == 403

    # repros tier: playwright OK.
    allowed = client.get(f"{_PFX}/session/{tid}/playwright", headers=_bearer(repros))
    assert allowed.status_code == 200

    # No agent tier reaches the raw trace or the audit log.
    assert client.get(f"{_PFX}/session/{tid}", headers=_bearer(repros)).status_code == 403
    assert client.get(f"{_PFX}/audit", headers=_bearer(repros)).status_code == 403


def test_agent_token_cannot_manage_agents_and_listing_hides_secrets():
    client, _ = _client()
    agent = _register(client, "scoped", "summaries")

    # An agent token cannot reach the admin-management routes (require_admin rejects).
    assert client.get("/admin/agents", headers=_bearer(agent["token"])).status_code == 401
    assert client.post("/admin/agents", headers=_bearer(agent["token"]),
                       json={"name": "x", "scope": "drafts"}).status_code == 401

    # The admin listing never returns the token or its hash.
    listing = client.get("/admin/agents", headers=_bearer(ADMIN)).json()["agents"]
    assert listing and all("token" not in a and "token_hash" not in a for a in listing)


def test_revoked_token_stops_working():
    client, _ = _client()
    tid = _ingest(client)
    agent = _register(client, "temp", "summaries")
    tok = agent["token"]

    assert client.get(f"{_PFX}/session/{tid}/summary", headers=_bearer(tok)).status_code == 200
    rev = client.post(f"/admin/agents/{agent['id']}/revoke", headers=_bearer(ADMIN))
    assert rev.status_code == 200
    # Revoked → no longer resolves as an agent → normal auth rejects it.
    assert client.get(f"{_PFX}/session/{tid}/summary", headers=_bearer(tok)).status_code == 401


def test_invalid_scope_rejected_at_registration():
    client, _ = _client()
    r = client.post("/admin/agents", headers=_bearer(ADMIN), json={"name": "x", "scope": "root"})
    assert r.status_code == 400
