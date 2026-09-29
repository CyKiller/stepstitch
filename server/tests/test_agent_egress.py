"""What an AI agent can read back out of the host.

The ingest scrubber decides what is stored. This file is about the other direction: what
leaves toward an agent holding an ``ssa_`` token. An operator reading their own dashboard
may see the (scrubbed) words a customer typed; an agent is a third party to that customer
and gets structure. Runs against the real local SQLite store, not a fake.
"""
from fastapi import FastAPI
from fastapi.testclient import TestClient

from server.audit import make_db_audit
from server.auth import build_auth
from server.host import build_app
from server.localdb import build_local_db_callables, connect_local

ADMIN = "admin-secret"
INGEST = "ingest-secret"
_PFX = "/api/stepstitch/v1"


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


def _ingest(client, explanation="Transfer failed after I pressed send twice"):
    r = client.post(f"{_PFX}/session", headers=_bearer(INGEST), json={
        "app_id": "tiny-transfer",
        "explanation": explanation,
        "footsteps": [
            {"timestamp": "2026-07-30T12:00:00Z", "type": "navigation",
             "route": "/transfer", "label": "[masked]"},
            {"timestamp": "2026-07-30T12:00:02Z", "type": "exception",
             "route": "/transfer", "label": "[masked]",
             "metadata": {"error_type": "TypeError"}},
        ],
        "metadata": {"sdk_version": "0.8.0"},
    })
    assert r.status_code == 200, r.text
    return r.json()["trace_id"]


def _agent(client, scope):
    r = client.post("/admin/agents", headers=_bearer(ADMIN),
                    json={"name": f"test-{scope}", "scope": scope})
    assert r.status_code == 200, r.text
    return r.json()["token"]


def test_an_agent_listing_sessions_gets_structure_not_the_customers_words(tmp_path):
    client, _ = _client(tmp_path)
    tid = _ingest(client)
    token = _agent(client, "summaries")

    r = client.get(f"{_PFX}/sessions", headers=_bearer(token))
    assert r.status_code == 200, r.text
    rows = r.json()["sessions"]
    assert [row["trace_id"] for row in rows] == [tid]
    row = rows[0]
    assert "explanation" not in row
    assert "user_id" not in row
    assert row["has_explanation"] is True
    assert "Transfer failed" not in r.text


def test_the_operator_listing_still_shows_the_explanation(tmp_path):
    client, _ = _client(tmp_path)
    _ingest(client)
    r = client.get(f"{_PFX}/sessions", headers=_bearer(ADMIN))
    assert r.status_code == 200, r.text
    assert r.json()["sessions"][0]["explanation"].startswith("Transfer failed")


def test_an_agent_cannot_ask_whether_a_given_person_filed_a_report(tmp_path):
    client, _ = _client(tmp_path)
    _ingest(client)
    token = _agent(client, "summaries")
    r = client.get(f"{_PFX}/sessions", params={"user_id": "someone"},
                   headers=_bearer(token))
    assert r.status_code == 403


# --- the egress guard on the agent path ------------------------------------------------

import json  # noqa: E402

_JWT = "eyJhbGciOiJIUzI1NiJ9" + "." + "eyJzdWIiOiIxMjM0NTY3ODkwIn0" + "." + "c2lnbmF0dXJlMTIzNDU2"


def _legacy_row_with_a_secret(conn, trace_id):
    """A row stored before the current detector set existed — or by any path that skipped
    ingest. Egress must not depend on every stored byte having been scrubbed by today's
    rules."""
    footsteps = [
        {"timestamp": "t", "type": "navigation", "route": "/transfer", "label": "[masked]"},
        {"timestamp": "t", "type": "click", "route": "/transfer", "target": "#send",
         "label": f"Send with session {_JWT}"},
    ]
    conn.execute("UPDATE stepstitch_traces SET footsteps = ? WHERE id = ?",
                 (json.dumps(footsteps), trace_id))


def test_a_secret_in_a_stored_row_never_reaches_an_agent(tmp_path):
    client, conn = _client(tmp_path)
    tid = _ingest(client)
    _legacy_row_with_a_secret(conn, tid)
    token = _agent(client, "repros")

    r = client.get(f"{_PFX}/session/{tid}/playwright", headers=_bearer(token))
    assert r.status_code == 200, r.text
    assert _JWT not in r.text
    body = r.json()
    assert body["_egress"]["kinds"] == {"jwt": 1}
    assert body["_egress"]["mode"] == "redact"

    audited = conn.execute(
        "SELECT detail FROM stepstitch_audit WHERE action = 'stepstitch.egress_redaction'"
    ).fetchall()
    assert len(audited) == 1
    assert _JWT not in audited[0][0], "the audit trail records kinds, never the value"


def test_the_agent_packet_is_guarded_and_says_so(tmp_path):
    client, conn = _client(tmp_path)
    tid = _ingest(client)
    _legacy_row_with_a_secret(conn, tid)
    token = _agent(client, "repros")

    r = client.get(f"{_PFX}/session/{tid}/agent-packet", headers=_bearer(token))
    assert r.status_code == 200, r.text
    assert _JWT not in r.text
    assert r.json()["_egress"]["kinds"] == {"jwt": 1}


def test_a_clean_response_carries_an_empty_report(tmp_path):
    client, _ = _client(tmp_path)
    tid = _ingest(client)
    token = _agent(client, "summaries")
    r = client.get(f"{_PFX}/session/{tid}/summary", headers=_bearer(token))
    assert r.status_code == 200, r.text
    assert r.json()["_egress"] == {"mode": "redact", "kinds": {}, "fields": []}


def test_the_operator_reading_their_own_data_is_not_filtered(tmp_path):
    client, conn = _client(tmp_path)
    tid = _ingest(client)
    _legacy_row_with_a_secret(conn, tid)
    r = client.get(f"{_PFX}/session/{tid}/playwright", headers=_bearer(ADMIN))
    assert r.status_code == 200
    assert "_egress" not in r.json()


def test_a_signed_artifact_is_scanned_and_sent_byte_for_byte(tmp_path):
    client, _ = _client(tmp_path)
    tid = _ingest(client)
    token = _agent(client, "summaries")
    as_agent = client.get(f"{_PFX}/session/{tid}/attestation", headers=_bearer(token))
    as_admin = client.get(f"{_PFX}/session/{tid}/attestation", headers=_bearer(ADMIN))
    assert as_agent.status_code == as_admin.status_code == 200, as_agent.text
    assert as_agent.headers["X-StepStitch-Egress"] == "scan; clean"
    assert "_egress" not in as_agent.json()
    body = as_agent.json()
    assert body.get("bundle_sha256") == as_admin.json().get("bundle_sha256")
