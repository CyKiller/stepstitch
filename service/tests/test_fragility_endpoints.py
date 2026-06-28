"""Fragility Radar endpoints — /fragility + /minimal-repro (audited, NPI-free)."""
from fastapi import FastAPI
from fastapi.testclient import TestClient

from stepstitch_service import create_stepstitch_router, generate_playwright_test

_PFX = "/api/stepstitch/v1"


class DB:
    def __init__(self):
        self.traces = {}
        self.audits = []

    async def execute(self, query, params=()):
        if " ".join(query.split()).upper().startswith("INSERT INTO STEPSTITCH_TRACES"):
            self.traces[params[0]] = params[5]  # footsteps json

    async def fetchone(self, query, params=()):
        return (self.traces.get(params[0]),) if params and params[0] in self.traces else None

    async def fetchall(self, query, params=()):
        return []


def _client():
    db = DB()

    async def audit(a, actor, detail):
        db.audits.append(a)

    router = create_stepstitch_router(
        get_user_id=lambda: "u", require_admin=lambda: {"user_id": "admin"},
        execute=db.execute, fetchone=db.fetchone, fetchall=db.fetchall,
        audit=audit, generate_playwright_test=generate_playwright_test,
    )
    app = FastAPI()
    app.include_router(router, prefix="/api")
    return TestClient(app), db


def _ingest(client):
    r = client.post(f"{_PFX}/session", json={
        "app_id": "demo",
        "footsteps": [
            {"timestamp": "t", "type": "click", "route": "/home", "target": "#menu",
             "label": "[masked]"},
            {"timestamp": "t", "type": "click", "route": "/checkout",
             "target": "div > span:nth-of-type(2)", "label": "[masked]"},
            {"timestamp": "t", "type": "api_error", "route": "/checkout",
             "label": "[masked]", "metadata": {"status": 500}},
        ],
        "metadata": {"sdk_version": "0.5.0"},
    })
    assert r.status_code == 200, r.text
    return r.json()["trace_id"]


def test_fragility_endpoint_ranks_and_audits():
    client, db = _client()
    tid = _ingest(client)
    out = client.get(f"{_PFX}/session/{tid}/fragility").json()
    assert out["interactive_steps"] == 2
    assert out["fragility"][0]["stability"] == "structural"   # brittle one ranked first
    assert "stepstitch.fragility" in db.audits


def test_minimal_repro_endpoint_reduces_and_compiles():
    client, db = _client()
    tid = _ingest(client)
    out = client.get(f"{_PFX}/session/{tid}/minimal-repro").json()
    assert out["original_steps"] == 3 and out["reduced_steps"] == 2   # only /checkout steps
    assert "import { test" in out["playwright_code"]
    assert "stepstitch.minimal_repro" in db.audits
