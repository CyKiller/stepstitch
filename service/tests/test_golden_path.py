"""Golden path — the single end-to-end acceptance test for StepStitch.

One hostile report flows through the WHOLE product in order:

  ingest (server-side scrub) → list → read (+replayability) → summary →
  privacy-posture → export-preview (drafts) → playwright compile

If this passes, the product works as a system, not just as isolated units. It is the
executable "definition of done" referenced by docs/STATUS.md.
"""
import json

from fastapi import FastAPI
from fastapi.testclient import TestClient

from stepstitch_service import create_stepstitch_router, generate_playwright_test
from stepstitch_service.integrations.bundle import default_draft_adapters

_PFX = "/api/stepstitch/v1"


class QueryAwareDB:
    """Stores the inserted row; answers each SELECT with the right column shape."""

    def __init__(self):
        self.rows = {}
        self.audits = []

    async def execute(self, query, params=()):
        q = query.strip().upper()
        if q.startswith("INSERT"):
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
        return [
            (tid, r["app_id"], r["project_id"], r["user_id"], r["explanation"], None)
            for tid, r in self.rows.items()
        ]


def _client():
    db = QueryAwareDB()

    async def audit(action, actor, detail):
        db.audits.append(action)

    router = create_stepstitch_router(
        get_user_id=lambda: "user-1",
        require_admin=lambda: {"user_id": "admin-1"},
        execute=db.execute, fetchone=db.fetchone, fetchall=db.fetchall,
        audit=audit, generate_playwright_test=generate_playwright_test,
        base_url="https://app.example.test",
        draft_adapters=default_draft_adapters(),
    )
    app = FastAPI()
    app.include_router(router, prefix="/api")
    return TestClient(app), db


def test_golden_path_end_to_end():
    client, db = _client()

    # 1. INGEST a hostile report — raw NPI in free text, raw id in route.
    ingest = client.post(f"{_PFX}/session", json={
        "app_id": "marvox",
        "project_id": "proj-1",
        "explanation": "checkout broke; my SSN 123-45-6789, email me@bank.com",
        "footsteps": [
            {"timestamp": "t", "type": "navigation",
             "route": "/accounts/8675309/checkout", "label": "[masked]"},
            {"timestamp": "t", "type": "click", "route": "/accounts/8675309/checkout",
             "target": '[data-testid="pay"]', "label": "[masked]"},
            {"timestamp": "t", "type": "api_error", "route": "/accounts/8675309/checkout",
             "label": "[masked]", "metadata": {
                 "status": 500,
                 "endpoint": "https://app.example.test/api/accounts/8675309?ssn=1",
                 "response_body": "SECRET",
                 "message": "raw message with email me@bank.com",
             }},
        ],
        "consent_version": "v1",
        "metadata": {"sdk_version": "0.3.0", "cookies": "session=SECRET"},
    })
    assert ingest.status_code == 200, ingest.text
    tid = ingest.json()["trace_id"]
    assert ingest.json()["scrub"]["scrub_status"] == "scrubbed"

    # The stored row carries no raw NPI and no forbidden values.
    stored = json.dumps(db.rows[tid])
    for raw in ("123-45-6789", "me@bank.com", "8675309", "SECRET", "session="):
        assert raw not in stored, f"leaked {raw!r}"

    # 2. LIST shows it.
    r = client.get(f"{_PFX}/sessions?limit=10")
    assert tid in [s["trace_id"] for s in r.json()["sessions"]]

    # 3. READ includes a replayability score.
    r = client.get(f"{_PFX}/session/{tid}")
    assert r.json()["replayability"]["grade"] in {"A", "B", "C", "D", "F"}
    assert r.json()["footsteps"][0]["route"] == "/accounts/:id/checkout"  # re-templated

    # 4. SUMMARY is sanitized + structure-derived.
    summary = client.get(f"{_PFX}/session/{tid}/summary").json()["summary"]
    assert summary["route"] == "/accounts/:id/checkout"
    assert summary["failing_status"] == 500
    assert summary["diagnostic_endpoint"] == "/api/accounts/:id"
    assert "8675309" not in json.dumps(summary)

    # 4b. DIAGNOSTIC SUMMARY is Copilot-safe and explains what never leaves.
    diagnostic = client.get(f"{_PFX}/session/{tid}/diagnostic-summary").json()["diagnostic"]
    assert diagnostic["summary"]["diagnostic_type"] == "api_error"
    assert "raw error messages" in diagnostic["never_included"]
    assert "me@bank.com" not in json.dumps(diagnostic)

    # 5. PRIVACY POSTURE reports the scrub + never-captured list.
    posture = client.get(f"{_PFX}/session/{tid}/privacy-posture").json()
    assert posture["scrub"]["scrub_status"] == "scrubbed"
    assert posture["never_captured"]

    # 6. EXPORT PREVIEW builds sanitized drafts (sends nothing).
    drafts = client.post(f"{_PFX}/session/{tid}/export-preview").json()["drafts"]
    assert set(drafts) == {"servicenow", "salesforce", "genesys"}
    assert drafts["servicenow"]["correlation_id"] == f"stepstitch:{tid}"
    assert drafts["genesys"]["trace_correlation_id"] == f"stepstitch:{tid}"
    assert "123-45-6789" not in json.dumps(drafts)

    fs_preview = client.post(
        f"{_PFX}/session/{tid}/financial-services-export-preview"
    ).json()
    assert fs_preview["target_pack"] == "financial-services-support"

    # 7. PLAYWRIGHT compiles to runnable code with the replayability header.
    code = client.get(f"{_PFX}/session/{tid}/playwright").json()["playwright_code"]
    assert "Replayability:" in code
    assert "await page.locator('[data-testid=\"pay\"]').click();" in code

    # Every operator action was audited.
    for action in ("stepstitch.list", "stepstitch.read", "stepstitch.summary",
                   "stepstitch.diagnostic_summary", "stepstitch.privacy_posture",
                   "stepstitch.export_preview",
                   "stepstitch.financial_services_export_preview", "stepstitch.compile"):
        assert action in db.audits
