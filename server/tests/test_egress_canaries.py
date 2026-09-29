"""End-to-end canary proof: planted values never reach an AI agent, by any tool.

Every canary below is planted in a place a real one could arrive — the customer's words, a
label, metadata, a timestamp, a route, and the local reproduction's console, stack and
network — and then the whole MCP tool surface is called, with a real scoped agent token,
through the real host and its real SQLite store. No canary may appear in any result.

Planted twice, on purpose:

- **through ingest** — the normal path; the scrubber should stop them at the door;
- **directly into storage** — a row written before today's detectors existed, or by a path
  that skipped ingest. The egress guard must stop these on the way out on its own, so a
  regression at either boundary fails this file by name.

The second half of the file is the no-false-positive proof: the same surface over a clean
trace must need no redaction at all, or the guard is vandalising evidence.

Credential-shaped literals are assembled at runtime; none is, or ever was, real.
"""
import asyncio
import json
import uuid
from datetime import datetime, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from stepstitch_service.mcp_server import COPILOT_SAFE_OPERATIONS, dispatch_tool

from server.audit import make_db_audit
from server.auth import build_auth
from server.host import build_app
from server.localdb import build_local_db_callables, connect_local

ADMIN = "admin-secret"
INGEST = "ingest-secret"
_PFX = "/api/stepstitch/v1"

CANARIES = {
    "jwt": "eyJhbGciOiJIUzI1NiJ9" + "." + "eyJjYW5hcnkiOiIxMjM0In0" + "." + "Y2FuYXJ5c2lnMTIz",
    "api_key": "sk-" + "proj-" + "Canary12Canary34Canary56",
    "blob": "Q2FuYXJ5QmxvYjEyMzQ1Njc4OTBhYmNkZWZnaGlqa2xtbm9w",
    "short_link": "bit.ly/Canary9Zq",
    "iban": "DE89370400440532013000",
    "ip": "10.66.77.88",
    "email": "canary.person@example.invalid",
    "ssn": "123-45-6789",
}


def _client(tmp_path):
    conn = connect_local(tmp_path / "local.db")
    get_user_id, require_admin = build_auth(ADMIN, INGEST)
    execute, fetchone, fetchall = build_local_db_callables(conn)
    app: FastAPI = build_app(
        get_user_id=get_user_id, require_admin=require_admin,
        execute=execute, fetchone=fetchone, fetchall=fetchall,
        audit=make_db_audit(execute),
        admin_token=ADMIN, ingest_token=INGEST, local_mode=True,
        base_url="http://127.0.0.1:4321",
    )
    return TestClient(app), conn


def _bearer(tok):
    return {"Authorization": f"Bearer {tok}"}


def _agent(client, scope="drafts"):
    r = client.post("/admin/agents", headers=_bearer(ADMIN),
                    json={"name": f"canary-{scope}", "scope": scope})
    assert r.status_code == 200, r.text
    return r.json()["token"]


def _all(sep=" "):
    return sep.join(CANARIES.values())


def _hostile_footsteps():
    return [
        {"timestamp": "2026-07-30T12:00:00Z", "type": "navigation",
         "route": f"/share/{CANARIES['email']}", "label": "[masked]"},
        {"timestamp": "2026-07-30T12:00:01Z", "type": "click", "route": "/transfer",
         "target": '[data-testid="transfer-submit"]', "label": f"Send {_all()}"},
        {"timestamp": "2026-07-30T12:00:02Z", "type": "api_error", "route": "/transfer",
         "label": "[masked]",
         "metadata": {"status": 500, "method": "POST",
                      "endpoint": f"/api/pay/{CANARIES['api_key']}"}},
    ]


def _plant_diagnostics(conn, trace_id, console, stack, request_path):
    record = {
        "source": "local_reproduction", "customer_data_status": "not_verified",
        "content_scrubbed": True, "schema_version": 2,
        "failure_stack": [stack, "/app/src/pay.ts:9:27"],
        "console_errors": [console],
        "failed_requests": [{"method": "POST", "path": request_path, "status": 500}],
        "failure_snapshot": {"type": "click", "target": "#send"},
    }
    conn.execute(
        "INSERT INTO stepstitch_diagnostics (id, trace_id, run_id, source, schema_version, "
        "script_sha256, execution_envelope_sha256, diagnostics_json, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (str(uuid.uuid4()), trace_id, "run-1", "local_reproduction", 2, "a" * 64, "b" * 64,
         json.dumps(record), datetime.now(timezone.utc).isoformat()))


def _call_every_tool(client, token, trace_id):
    """Every MCP tool, through the real MCP dispatcher, against the real host."""
    async def call_route(method, path, params):
        r = client.request(method, f"{_PFX}{path}", params=params or None,
                           headers=_bearer(token))
        return {"_status": r.status_code, "_body": r.text} if r.status_code >= 400 \
            else r.json()

    results = {}
    for op in COPILOT_SAFE_OPERATIONS:
        args = {p.name: trace_id for p in op.params if p.name == "trace_id"}
        results[op.tool_name] = asyncio.run(dispatch_tool(op.tool_name, args, call_route))
    return results


def _assert_no_canary(results):
    blob = json.dumps(results)
    leaked = {name: value for name, value in CANARIES.items() if value in blob}
    assert not leaked, f"canaries reached an agent: {sorted(leaked)}"


def test_canaries_planted_through_ingest_never_reach_an_agent(tmp_path):
    client, conn = _client(tmp_path)
    r = client.post(f"{_PFX}/session", headers=_bearer(INGEST), json={
        "app_id": "tiny-transfer",
        "explanation": f"It broke. {_all()}",
        "footsteps": _hostile_footsteps(),
        "metadata": {"sdk_version": "0.8.0", "user_agent": f"Mozilla/5.0 {CANARIES['jwt']}"},
    })
    assert r.status_code == 200, r.text
    tid = r.json()["trace_id"]
    _plant_diagnostics(conn, tid, console=f"upstream said {_all()}",
                       stack=f"Error: pay failed for {_all()}",
                       request_path=f"/api/users/{CANARIES['email']}/pay")

    results = _call_every_tool(client, _agent(client), tid)
    assert all("_status" not in v or v["_status"] < 500 for v in results.values()), results
    _assert_no_canary(results)


def test_canaries_already_in_storage_are_stopped_on_the_way_out(tmp_path):
    client, conn = _client(tmp_path)
    r = client.post(f"{_PFX}/session", headers=_bearer(INGEST), json={
        "app_id": "tiny-transfer", "explanation": "It broke.",
        "footsteps": [{"timestamp": "t", "type": "navigation", "route": "/transfer",
                       "label": "[masked]"}],
    })
    tid = r.json()["trace_id"]
    # Bypass ingest entirely: this is what a pre-upgrade row looks like.
    conn.execute("UPDATE stepstitch_traces SET footsteps = ?, explanation = ? WHERE id = ?",
                 (json.dumps(_hostile_footsteps()), f"It broke. {_all()}", tid))
    _plant_diagnostics(conn, tid, console=f"upstream said {_all()}",
                       stack=f"Error: pay failed for {_all()}",
                       request_path=f"/api/users/{CANARIES['email']}/pay")

    results = _call_every_tool(client, _agent(client), tid)
    _assert_no_canary(results)
    audited = conn.execute("SELECT count(*) FROM stepstitch_audit "
                           "WHERE action = 'stepstitch.egress_redaction'").fetchone()[0]
    assert audited > 0, "every egress redaction is audited"


def test_a_clean_trace_needs_no_egress_redaction_on_any_tool(tmp_path):
    client, conn = _client(tmp_path)
    r = client.post(f"{_PFX}/session", headers=_bearer(INGEST), json={
        "app_id": "tiny-transfer", "explanation": "Pressing send did nothing",
        "footsteps": [
            {"timestamp": "2026-07-30T12:00:00Z", "type": "navigation",
             "route": "/accounts/:id/transfer", "label": "[masked]"},
            {"timestamp": "2026-07-30T12:00:01Z", "type": "click",
             "route": "/accounts/:id/transfer", "target": '[data-testid="transfer-submit"]',
             "label": "[masked]"},
            {"timestamp": "2026-07-30T12:00:02Z", "type": "api_error",
             "route": "/accounts/:id/transfer", "label": "[masked]",
             "metadata": {"status": 500, "method": "POST",
                          "endpoint": "/api/accounts/:id/pay"}},
        ],
        "metadata": {"sdk_version": "0.8.0", "user_agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")},
    })
    tid = r.json()["trace_id"]
    _plant_diagnostics(conn, tid, console="pay failed with 500",
                       stack="TypeError: form.amount.toFixed is not a function",
                       request_path="/api/accounts/:id/pay")

    results = _call_every_tool(client, _agent(client), tid)
    for tool, result in results.items():
        if isinstance(result, dict) and "_egress" in result:
            assert result["_egress"]["kinds"] == {}, (tool, result["_egress"])


@pytest.mark.parametrize("scope", ["summaries", "repros"])
def test_lower_tiers_are_guarded_too(tmp_path, scope):
    client, conn = _client(tmp_path)
    r = client.post(f"{_PFX}/session", headers=_bearer(INGEST), json={
        "app_id": "tiny-transfer",
        "footsteps": [{"timestamp": "t", "type": "navigation", "route": "/transfer",
                       "label": "[masked]"}],
    })
    tid = r.json()["trace_id"]
    conn.execute("UPDATE stepstitch_traces SET footsteps = ? WHERE id = ?",
                 (json.dumps(_hostile_footsteps()), tid))
    _assert_no_canary(_call_every_tool(client, _agent(client, scope), tid))
