"""Copilot-safe surface proof — summary / privacy-posture / export-preview endpoints
return only sanitized data, are audited, and never expose raw NPI."""
import json
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from stepstitch_service import create_stepstitch_router, generate_playwright_test

_REPO_ROOT = Path(__file__).resolve().parents[2]
_OPENAPI = _REPO_ROOT / "copilot" / "openapi-v2.json"


class QueryAwareDB:
    """Stores the full inserted row and answers each SELECT with the right columns."""

    def __init__(self):
        self.rows = {}
        self.audits = []

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
        q = " ".join(query.split())  # normalize whitespace
        if q.startswith("SELECT footsteps, project_id"):
            return (row["footsteps"], row["project_id"])
        if q.startswith("SELECT trace_metadata"):
            return (row["trace_metadata"],)
        if q.startswith("SELECT footsteps FROM"):
            return (row["footsteps"],)
        # default: get_session 5-col shape
        return (row["footsteps"], row["explanation"], row["user_id"],
                row["project_id"], None)

    async def fetchall(self, query, params=()):
        return []


def _build():
    db = QueryAwareDB()

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
    )
    app = FastAPI()
    app.include_router(router, prefix="/api")
    return TestClient(app), db


_PFX = "/api/stepstitch/v1"


def _ingest(client):
    payload = {
        "app_id": "marvox",
        "project_id": "proj-1",
        "explanation": "Submit failed, my SSN 123-45-6789",
        "footsteps": [
            {"timestamp": "t", "type": "navigation",
             "route": "/accounts/8675309/distributions", "label": "[masked]"},
            {"timestamp": "t", "type": "click", "route": "/accounts/8675309/distributions",
             "target": '[data-testid="submit"]', "label": "[masked]"},
            {"timestamp": "t", "type": "api_error",
             "route": "/accounts/8675309/distributions", "label": "[masked]",
             "metadata": {
                 "status": 500,
                 "endpoint": "https://portal.example.test/api/accounts/8675309?ssn=1",
                 "message": "raw message with SSN 123-45-6789",
             }},
        ],
        "metadata": {"sdk_version": "0.2.0"},
    }
    r = client.post(f"{_PFX}/session", json=payload)
    assert r.status_code == 200
    return r.json()["trace_id"]


def test_summary_is_sanitized_and_audited():
    client, db = _build()
    tid = _ingest(client)
    r = client.get(f"{_PFX}/session/{tid}/summary")
    assert r.status_code == 200
    summary = r.json()["summary"]
    # route was re-templated at ingestion; raw id gone.
    assert summary["route"] == "/accounts/:id/distributions"
    assert "8675309" not in json.dumps(summary)
    assert summary["failing_status"] == 500
    assert summary["privacy_status"] == "Scrubbed / No NPI"
    assert any(a[0] == "stepstitch.summary" for a in db.audits)


def test_privacy_posture_reports_scrub_and_never_captured():
    client, db = _build()
    tid = _ingest(client)
    r = client.get(f"{_PFX}/session/{tid}/privacy-posture")
    assert r.status_code == 200
    body = r.json()
    assert body["policy"] == "financial-services-enterprise"
    assert body["scrub"]["scrub_status"] == "scrubbed"  # SSN in explanation was scrubbed
    assert "input values" in body["never_captured"]
    assert any(a[0] == "stepstitch.privacy_posture" for a in db.audits)


def test_export_preview_builds_drafts_without_npi():
    client, db = _build()
    tid = _ingest(client)
    r = client.post(f"{_PFX}/session/{tid}/export-preview")
    assert r.status_code == 200
    drafts = r.json()["drafts"]
    assert set(drafts.keys()) == {"servicenow", "salesforce", "genesys"}
    assert drafts["servicenow"]["correlation_id"] == f"stepstitch:{tid}"
    assert drafts["genesys"]["diagnostic_endpoint"] == "/api/accounts/:id"
    blob = json.dumps(drafts)
    assert "123-45-6789" not in blob
    assert "8675309" not in blob
    assert any(a[0] == "stepstitch.export_preview" for a in db.audits)


def test_diagnostic_summary_is_copilot_safe_and_audited():
    client, db = _build()
    tid = _ingest(client)
    r = client.get(f"{_PFX}/session/{tid}/diagnostic-summary")
    assert r.status_code == 200
    body = r.json()["diagnostic"]
    assert body["summary"]["diagnostic_type"] == "api_error"
    assert body["summary"]["diagnostic_endpoint"] == "/api/accounts/:id"
    assert "raw console logs" in body["never_included"]
    assert "123-45-6789" not in json.dumps(body)
    assert any(a[0] == "stepstitch.diagnostic_summary" for a in db.audits)


def test_financial_services_export_preview_is_named_and_audited():
    client, db = _build()
    tid = _ingest(client)
    r = client.post(f"{_PFX}/session/{tid}/financial-services-export-preview")
    assert r.status_code == 200
    body = r.json()
    assert body["target_pack"] == "financial-services-support"
    assert set(body["drafts"]) == {"servicenow", "salesforce", "genesys"}
    assert any(
        a[0] == "stepstitch.financial_services_export_preview" for a in db.audits
    )


def test_summary_404_on_missing():
    client, _ = _build()
    r = client.get(f"{_PFX}/session/nope/summary")
    assert r.status_code == 404


def test_openapi_exposes_no_destructive_operation():
    spec = json.loads(_OPENAPI.read_text())
    # No DELETE anywhere, and no purge/delete/kill paths.
    for path, ops in spec["paths"].items():
        assert "delete" not in ops, f"DELETE exposed on {path}"
        assert "purge" not in path and "by-user" not in path
    # The full raw read (carries explanation) must not be a tool.
    assert "/session/{trace_id}" not in spec["paths"]


def test_openapi_paths_are_real_routes():
    client, _ = _build()
    spec = json.loads(_OPENAPI.read_text())
    live = set()
    for route in client.app.routes:
        path = getattr(route, "path", "")
        if path.startswith("/api/stepstitch/v1"):
            live.add(path.replace("/api/stepstitch/v1", "", 1))
    for spec_path in spec["paths"]:
        assert spec_path in live, f"OpenAPI path {spec_path} has no live route"
