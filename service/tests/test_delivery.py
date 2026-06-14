"""Governed direct-write proof.

Direct-write is off by default, human-approval-gated, dry-run by default, idempotent, sends
only the sanitized draft, and is never exposed on the MCP/Copilot agent surface.
"""
import json

from fastapi import FastAPI
from fastapi.testclient import TestClient

from stepstitch_service import create_stepstitch_router, generate_playwright_test
from stepstitch_service.delivery import SalesforceWriter, ServiceNowWriter
from stepstitch_service.integrations.bundle import default_draft_adapters
from stepstitch_service.mcp_server import COPILOT_SAFE_OPERATIONS, build_tool_definitions
from stepstitch_service.mcp_server import CopilotSafeOperation, ToolParam

_PFX = "/api/stepstitch/v1"


class _DB:
    def __init__(self):
        self.rows = {}

    async def execute(self, query, params=()):
        if query.strip().upper().startswith("INSERT"):
            self.rows[params[0]] = {"footsteps": params[5], "project_id": params[2]}

    async def fetchone(self, query, params=()):
        row = self.rows.get(params[0])
        if not row:
            return None
        return (row["footsteps"], row["project_id"])

    async def fetchall(self, query, params=()):
        return []


def _build(*, with_writers=True, with_adapters=True):
    db = _DB()
    calls = []

    async def sn_post(path, body):
        calls.append(("servicenow", path, body))
        return {"result": {"sys_id": "SN123", "number": "INC0012345"}}

    async def sf_post(path, body):
        calls.append(("salesforce", path, body))
        return {"id": "SF456", "success": True}

    writers = [ServiceNowWriter(sn_post), SalesforceWriter(sf_post)] if with_writers else None
    router = create_stepstitch_router(
        get_user_id=lambda: "user-42",
        require_admin=lambda: {"user_id": "admin-1"},
        execute=db.execute, fetchone=db.fetchone, fetchall=db.fetchall,
        generate_playwright_test=generate_playwright_test,
        draft_adapters=default_draft_adapters() if with_adapters else None,
        record_writers=writers,
    )
    app = FastAPI()
    app.include_router(router, prefix="/api")
    return TestClient(app), db, calls


def _ingest(client):
    r = client.post(f"{_PFX}/session", json={
        "app_id": "acme", "project_id": "p1",
        "explanation": "submit failed, SSN 123-45-6789",
        "footsteps": [
            {"timestamp": "t", "type": "api_error",
             "route": "/accounts/8675309/distributions", "label": "[masked]",
             "metadata": {"status": 500, "endpoint": "/api/accounts/8675309"}},
        ],
        "metadata": {"sdk_version": "0.4.0"},
    })
    assert r.status_code == 200
    return r.json()["trace_id"]


def _approve():
    return {"approved_by": "ops@acme.test", "idempotency_key": "k-1"}


def test_disabled_returns_404_without_writers():
    client, _, _ = _build(with_writers=False)
    tid = _ingest(client)
    r = client.post(f"{_PFX}/session/{tid}/deliver", json=_approve())
    assert r.status_code == 404


def test_dry_run_is_default_and_sends_nothing():
    client, _, calls = _build()
    tid = _ingest(client)
    # No dry_run param -> defaults to True.
    r = client.post(f"{_PFX}/session/{tid}/deliver", json=_approve())
    assert r.status_code == 200
    body = r.json()
    assert body["dry_run"] is True
    assert calls == []  # nothing sent
    # Parity: would_send equals the export-preview draft.
    preview = client.post(f"{_PFX}/session/{tid}/export-preview").json()["drafts"]
    assert body["results"]["servicenow"]["would_send"] == preview["servicenow"]
    assert body["results"]["salesforce"]["would_send"] == preview["salesforce"]


def test_real_write_sends_only_sanitized_draft():
    client, _, calls = _build()
    tid = _ingest(client)
    r = client.post(f"{_PFX}/session/{tid}/deliver?dry_run=false", json=_approve())
    assert r.status_code == 200
    results = r.json()["results"]
    assert results["servicenow"]["record_id"] == "SN123"
    assert results["servicenow"]["deduped"] is False
    assert results["salesforce"]["record_id"] == "SF456"
    # Exactly the two configured targets were posted, once each.
    assert sorted(t for t, _, _ in calls) == ["salesforce", "servicenow"]
    # No NPI in anything that left the building.
    blob = json.dumps(calls)
    assert "123-45-6789" not in blob
    assert "8675309" not in blob


def test_idempotency_key_dedupes():
    client, _, calls = _build()
    tid = _ingest(client)
    first = client.post(f"{_PFX}/session/{tid}/deliver?dry_run=false", json=_approve())
    second = client.post(f"{_PFX}/session/{tid}/deliver?dry_run=false", json=_approve())
    assert first.status_code == second.status_code == 200
    # Second call deduped -> no extra POSTs (still one per target).
    assert len(calls) == 2
    assert second.json()["results"]["servicenow"]["deduped"] is True


def test_requires_approver_and_idempotency_key():
    client, _, _ = _build()
    tid = _ingest(client)
    bad_approver = client.post(f"{_PFX}/session/{tid}/deliver",
                               json={"approved_by": "  ", "idempotency_key": "k"})
    assert bad_approver.status_code == 422
    bad_key = client.post(f"{_PFX}/session/{tid}/deliver",
                          json={"approved_by": "a", "idempotency_key": ""})
    assert bad_key.status_code == 422


def test_unknown_target_rejected():
    client, _, _ = _build()
    tid = _ingest(client)
    r = client.post(f"{_PFX}/session/{tid}/deliver?dry_run=false",
                    json={**_approve(), "targets": ["jira"]})
    assert r.status_code == 400


def test_deliver_is_never_an_agent_tool():
    names = {op.tool_name for op in COPILOT_SAFE_OPERATIONS}
    assert "deliver" not in names
    assert not any("deliver" in d["name"] for d in build_tool_definitions())
    # And the destructive guard would reject a deliver op if anyone tried to add one.
    sneaky = CopilotSafeOperation(
        operation_id="Deliver", tool_name="deliver", method="POST",
        path="/session/{trace_id}/deliver", description="x",
        params=(ToolParam("trace_id", "string", required=True),),
    )
    assert sneaky.is_destructive
