"""The Reproduce-locally endpoint: local-only, admin-only, and honest about what it saw.

The runner itself is covered in service/tests/test_runner.py; these tests cover the seam
the console clicks — that the route exists only where executing a browser is appropriate,
that it is gated, and that the verdict reaches the caller unchanged.
"""
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from stepstitch_service.runner import ReproductionResult, RunAttempt, RunnerError

from server.audit import make_db_audit
from server.auth import build_auth
from server.host import build_app
from server.localdb import build_local_db_callables, connect_local

ADMIN = "admin-secret"
INGEST = "ingest-secret"
_PFX = "/api/stepstitch/v1"

_PAYLOAD = {
    "app_id": "tiny-transfer",
    "footsteps": [
        {"timestamp": "2026-07-30T12:00:00Z", "type": "navigation", "route": "/transfer",
         "label": "[masked]"},
        {"timestamp": "2026-07-30T12:00:02Z", "type": "exception", "route": "/transfer",
         "label": "[masked]", "metadata": {"error_type": "TypeError"}},
    ],
    "metadata": {"sdk_version": "0.8.0"},
}


def _client(tmp_path, *, local_mode=True):
    conn = connect_local(tmp_path / "local.db")
    get_user_id, require_admin = build_auth(ADMIN, INGEST)
    execute, fetchone, fetchall = build_local_db_callables(conn)
    app: FastAPI = build_app(
        get_user_id=get_user_id, require_admin=require_admin,
        execute=execute, fetchone=fetchone, fetchall=fetchall,
        audit=make_db_audit(execute),   # durable trail, like production wiring
        admin_token=ADMIN, ingest_token=INGEST, local_mode=local_mode,
        base_url="http://127.0.0.1:4321",
    )
    client = TestClient(app)
    trace = client.post(f"{_PFX}/session", json=_PAYLOAD,
                        headers={"Authorization": f"Bearer {INGEST}"}).json()["trace_id"]
    return client, conn, trace


def _admin():
    return {"Authorization": f"Bearer {ADMIN}"}


def _result(verdict="reproduced", **kwargs):
    return ReproductionResult(
        verdict=verdict, session_id="s", script_sha256="a" * 64,
        runs=[RunAttempt(index=0, exit_code=1, passed=False, timed_out=False,
                         duration_seconds=1.0)],
        detail="the failure happened again in 1 of 1 run.", **kwargs)


def test_a_deployed_host_has_no_reproduce_endpoint_at_all(tmp_path):
    """Executing a browser is a local-developer action. A deployed, multi-tenant host must
    not offer it — not gated, not present."""
    client, conn, trace = _client(tmp_path, local_mode=False)
    try:
        r = client.post(f"/admin/session/{trace}/reproduce", json={}, headers=_admin())
        assert r.status_code == 404
    finally:
        conn.close()


def test_the_endpoint_is_admin_gated(tmp_path):
    client, conn, trace = _client(tmp_path)
    try:
        assert client.post(f"/admin/session/{trace}/reproduce", json={}).status_code == 401
        assert client.post(f"/admin/session/{trace}/reproduce", json={},
                           headers={"Authorization": f"Bearer {INGEST}"}).status_code == 401
    finally:
        conn.close()


def test_an_unknown_session_is_a_404_not_a_run(tmp_path):
    client, conn, _ = _client(tmp_path)
    try:
        with patch("stepstitch_service.runner.run_reproduction") as run:
            r = client.post("/admin/session/does-not-exist/reproduce", json={},
                            headers=_admin())
            assert r.status_code == 404
            run.assert_not_called()
    finally:
        conn.close()


def test_the_verdict_reaches_the_caller_unchanged(tmp_path):
    client, conn, trace = _client(tmp_path)
    try:
        with patch("stepstitch_service.runner.run_reproduction",
                   return_value=_result()) as run:
            body = client.post(f"/admin/session/{trace}/reproduce",
                               json={"runs": 2, "timeout_seconds": 30},
                               headers=_admin()).json()
        assert body["status"] == "ok"
        assert body["verdict"] == "reproduced"
        assert body["script_sha256"] == "a" * 64
        # The request's bounds are honored, and the app under test is the configured one.
        kwargs = run.call_args.kwargs
        assert kwargs["runs"] == 2 and kwargs["timeout_seconds"] == 30
        assert kwargs["base_url"] == "http://127.0.0.1:4321"
        assert kwargs["session_id"] == trace
    finally:
        conn.close()


def test_a_refusal_is_reported_as_an_answer_not_a_server_error(tmp_path):
    client, conn, trace = _client(tmp_path)
    try:
        with patch("stepstitch_service.runner.run_reproduction",
                   side_effect=RunnerError("this is not the frozen reproduction")):
            r = client.post(f"/admin/session/{trace}/reproduce", json={}, headers=_admin())
        assert r.status_code == 200
        assert r.json()["status"] == "refused"
        assert "frozen" in r.json()["detail"]
    finally:
        conn.close()


def test_running_a_reproduction_is_audited(tmp_path):
    client, conn, trace = _client(tmp_path)
    try:
        with patch("stepstitch_service.runner.run_reproduction", return_value=_result()):
            client.post(f"/admin/session/{trace}/reproduce", json={}, headers=_admin())
        events = client.get(f"{_PFX}/audit", headers=_admin()).json()["entries"]
        assert any(e["action"] == "stepstitch.reproduce" for e in events)
    finally:
        conn.close()
