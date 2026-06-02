"""Router factory smoke + behavior test using injected fakes and FastAPI TestClient."""
import json

from fastapi import FastAPI
from fastapi.testclient import TestClient

from stepstitch_service import create_stepstitch_router, generate_playwright_test


class FakeDB:
    def __init__(self):
        self.rows = {}
        self.audits = []

    async def execute(self, query, params=()):
        q = query.strip().upper()
        if q.startswith("INSERT"):
            self.rows[params[0]] = {"footsteps": params[5], "user_id": params[3]}
        elif q.startswith("DELETE"):
            uid = params[0]
            self.rows = {k: v for k, v in self.rows.items() if v["user_id"] != uid}

    async def fetchone(self, query, params=()):
        row = self.rows.get(params[0])
        if not row:
            return None
        return (row["footsteps"], None, row["user_id"], None, None)

    async def fetchall(self, query, params=()):
        return []


def _build():
    db = FakeDB()

    async def audit(action, actor, detail):
        db.audits.append((action, actor, detail))

    router = create_stepstitch_router(
        get_user_id=lambda: "user-42",
        require_admin=lambda: {"user_id": "admin-1"},
        execute=db.execute,
        fetchone=db.fetchone,
        fetchall=db.fetchall,
        audit=audit,
        generate_playwright_test=generate_playwright_test,
        base_url="https://app.example.test",
    )
    app = FastAPI()
    app.include_router(router, prefix="/api")
    return app, db


def test_write_then_compile_roundtrip():
    app, db = _build()
    client = TestClient(app)

    payload = {
        "app_id": "marvox",
        "footsteps": [
            {"timestamp": "2026-06-02T00:00:00Z", "type": "click",
             "route": "/dashboard", "target": "#go", "label": "[masked]"}
        ],
        "consent_version": "v1",
        "metadata": {"sdk_version": "0.1.0"},
    }
    r = client.post("/api/stepstitch/v1/session", json=payload)
    assert r.status_code == 200
    trace_id = r.json()["trace_id"]
    assert trace_id

    # stored footsteps were JSON-serialized (string), not a raw list
    assert isinstance(db.rows[trace_id]["footsteps"], str)
    assert json.loads(db.rows[trace_id]["footsteps"])[0]["target"] == "#go"

    r2 = client.get(f"/api/stepstitch/v1/session/{trace_id}/playwright")
    assert r2.status_code == 200
    assert "await page.locator('#go').click();" in r2.json()["playwright_code"]
    # operator read emitted an audit event
    assert any(a[0] == "stepstitch.compile" for a in db.audits)


def test_compile_missing_trace_404():
    app, _ = _build()
    client = TestClient(app)
    r = client.get("/api/stepstitch/v1/session/nope/playwright")
    assert r.status_code == 404


def test_delete_by_user_audited():
    app, db = _build()
    client = TestClient(app)
    client.post("/api/stepstitch/v1/session", json={
        "footsteps": [{"timestamp": "t", "type": "navigation", "route": "/", "label": "[masked]"}],
    })
    r = client.delete("/api/stepstitch/v1/session/by-user/user-42")
    assert r.status_code == 200
    assert any(a[0] == "stepstitch.delete_by_user" for a in db.audits)
    assert db.rows == {}
