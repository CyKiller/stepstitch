"""Evidence Attestation endpoint — composes existing reads into a signed, verifiable bundle.

In-memory fake. A host-injected ``sign_blob`` proves the tenant-controlled signing path without
needing cosign installed. The bundle hash is always present and deterministic.
"""
import json

from fastapi import FastAPI
from fastapi.testclient import TestClient

from stepstitch_service import create_stepstitch_router, generate_playwright_test
from stepstitch_service.attestation import bundle_sha256

_PFX = "/api/stepstitch/v1"


class AttDB:
    def __init__(self):
        self.traces = {}
        self.audits = []

    async def execute(self, query, params=()):
        if " ".join(query.split()).upper().startswith("INSERT INTO STEPSTITCH_TRACES"):
            self.traces[params[0]] = {
                "project_id": params[2], "footsteps": params[5], "trace_metadata": params[6],
            }

    async def fetchone(self, query, params=()):
        s = " ".join(query.split())
        if s.startswith("SELECT verdict, fix_ref, run_url"):
            return None  # no verification recorded
        row = self.traces.get(params[0]) if params else None
        if not row:
            return None
        if s.startswith("SELECT footsteps, project_id, trace_metadata"):
            return (row["footsteps"], row["project_id"], row["trace_metadata"])
        if s.startswith("SELECT footsteps, project_id"):
            return (row["footsteps"], row["project_id"])
        return (row["footsteps"],)

    async def fetchall(self, query, params=()):
        return []


def _client(sign_blob=None):
    db = AttDB()

    async def audit(action, actor, detail):
        db.audits.append(action)

    router = create_stepstitch_router(
        get_user_id=lambda: "u", require_admin=lambda: {"user_id": "admin"},
        execute=db.execute, fetchone=db.fetchone, fetchall=db.fetchall,
        audit=audit, generate_playwright_test=generate_playwright_test,
        sign_blob=sign_blob,
    )
    app = FastAPI()
    app.include_router(router, prefix="/api")
    return TestClient(app), db


def _ingest(client):
    r = client.post(f"{_PFX}/session", json={
        "app_id": "demo", "project_id": "p1",
        "footsteps": [{"timestamp": "t", "type": "api_error", "route": "/accounts/:id",
                       "label": "[masked]", "metadata": {"status": 500}}],
        "metadata": {"sdk_version": "0.5.0", "sdk_build": "5c2ea11"},
    })
    assert r.status_code == 200, r.text
    return r.json()["trace_id"]


def test_unsigned_attestation_has_deterministic_tamper_evident_hash():
    client, _ = _client(sign_blob=None)
    tid = _ingest(client)
    out = client.get(f"{_PFX}/session/{tid}/attestation").json()
    assert out["signed"] is False and out["signature"] is None
    assert out["bundle"]["schema"] == "stepstitch.attestation/v1"
    assert out["bundle"]["sdk_build"] == "5c2ea11"
    # The hash recomputes to the same value from the returned bundle (independent verification).
    assert bundle_sha256(out["bundle"]) == out["bundle_sha256"]
    assert "verify_recipe" in out


async def _fake_signer(blob: bytes) -> str:
    return "FAKESIG:" + str(len(blob))


def test_injected_signer_signs_the_bundle():
    client, db = _client(sign_blob=_fake_signer)
    tid = _ingest(client)
    out = client.get(f"{_PFX}/session/{tid}/attestation").json()
    assert out["signed"] is True and out["signature"].startswith("FAKESIG:")
    assert "stepstitch.attestation" in db.audits


def test_bundle_is_npi_free():
    client, _ = _client()
    tid = _ingest(client)
    out = client.get(f"{_PFX}/session/{tid}/attestation").json()
    blob = json.dumps(out["bundle"])
    assert "input values" in str(out["bundle"]["privacy"]["never_captured"])  # the proof list
    for raw in ("password", "ssn", "Bearer "):
        assert raw not in blob
