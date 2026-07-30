"""Local onboarding: pairing data, its production gate, and the connect pane's contract.

The console can hand a developer a ready-to-paste snippet only because local mode returns
the generated ingest credential to an admin. That is a deliberate, narrow exception, so
these tests pin both halves: it works locally, and it can never leak from a deployed host.
"""
from fastapi import FastAPI
from fastapi.testclient import TestClient
from stepstitch_service.host.dashboard import DASHBOARD_HTML

from server.auth import build_auth
from server.host import build_app
from server.localdb import build_local_db_callables, connect_local

ADMIN = "admin-secret"
INGEST = "ingest-secret"
_PFX = "/api/stepstitch/v1"

_PAYLOAD = {
    "app_id": "my-app",
    "footsteps": [{"timestamp": "t", "type": "api_error", "route": "/transfer",
                   "label": "[masked]", "metadata": {"status": 500}}],
    "metadata": {"sdk_version": "0.8.0"},
}


def _client(tmp_path, *, local_mode):
    conn = connect_local(tmp_path / "local.db")
    get_user_id, require_admin = build_auth(ADMIN, INGEST)
    execute, fetchone, fetchall = build_local_db_callables(conn)
    app: FastAPI = build_app(
        get_user_id=get_user_id, require_admin=require_admin,
        execute=execute, fetchone=fetchone, fetchall=fetchall,
        admin_token=ADMIN, ingest_token=INGEST, local_mode=local_mode,
    )
    return TestClient(app), conn


def _bearer(tok):
    return {"Authorization": f"Bearer {tok}"}


def test_local_mode_hands_the_ingest_token_to_the_operator(tmp_path):
    client, conn = _client(tmp_path, local_mode=True)
    try:
        status = client.get("/admin/status", headers=_bearer(ADMIN)).json()
        assert status["local_mode"] is True
        assert status["local_ingest_token"] == INGEST
    finally:
        conn.close()


def test_a_deployed_host_never_returns_the_ingest_token(tmp_path):
    # The same endpoint, same admin, without local mode: the credential is simply absent.
    client, conn = _client(tmp_path, local_mode=False)
    try:
        status = client.get("/admin/status", headers=_bearer(ADMIN)).json()
        assert status["local_mode"] is False
        assert status["local_ingest_token"] is None
    finally:
        conn.close()


def test_the_pairing_data_is_admin_gated(tmp_path):
    client, conn = _client(tmp_path, local_mode=True)
    try:
        # The ingest token cannot read the status that would reveal it.
        assert client.get("/admin/status", headers=_bearer(INGEST)).status_code == 401
        assert client.get("/admin/status").status_code == 401
    finally:
        conn.close()


def test_the_connection_check_separates_a_real_app_from_the_console_sample(tmp_path):
    """The check's whole value is answering 'is MY app wired up?', so it must not be
    satisfied by the console's own sample button."""
    client, conn = _client(tmp_path, local_mode=True)
    try:
        client.post(f"{_PFX}/session",
                    json=dict(_PAYLOAD, app_id="console-sample"), headers=_bearer(INGEST))
        listed = client.get(f"{_PFX}/sessions?limit=50", headers=_bearer(ADMIN)).json()
        real = [s for s in listed["sessions"] if s["app_id"] != "console-sample"]
        assert real == []          # sample alone -> still "not connected"

        client.post(f"{_PFX}/session", json=_PAYLOAD, headers=_bearer(INGEST))
        listed = client.get(f"{_PFX}/sessions?limit=50", headers=_bearer(ADMIN)).json()
        real = [s for s in listed["sessions"] if s["app_id"] != "console-sample"]
        assert [s["app_id"] for s in real] == ["my-app"]
    finally:
        conn.close()


def test_the_connect_pane_ships_three_kits_and_keeps_the_token_server_side():
    html = DASHBOARD_HTML
    for label in ('"Next.js"', '"Express"', '"Browser only"'):
        assert label in html
    # The framework kits proxy through the developer's own server: the browser bundle
    # never carries the credential. Only the explicitly-labelled local-only kit inlines it.
    assert "process.env.STEPSTITCH_INGEST_TOKEN" in html
    assert "Local evaluation only" in html
    # The check exists and knows what does not count as a connection.
    assert "Check my connection" in html
    assert "console-sample" in html
