"""The agent loop's seam: freeze, hand off, judge with the frozen bytes.

The verdict logic is covered in service/tests/test_fixcheck.py. These tests cover what the
host stores and refuses — above all, that the frozen script is what verification reruns,
so a fixing agent can never grade its own homework.
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
        audit=make_db_audit(execute),
        admin_token=ADMIN, ingest_token=INGEST, local_mode=local_mode,
        base_url="http://127.0.0.1:4321",
    )
    client = TestClient(app)
    trace = client.post(f"{_PFX}/session", json=_PAYLOAD,
                        headers={"Authorization": f"Bearer {INGEST}"}).json()["trace_id"]
    return client, conn, trace


def _admin():
    return {"Authorization": f"Bearer {ADMIN}"}


def _result(verdict, *, transcript="", passed=None, sha="a" * 64):
    if passed is None:
        passed = verdict == "not_reproduced"
    return ReproductionResult(
        verdict=verdict, session_id="s", script_sha256=sha,
        runs=[RunAttempt(index=0, exit_code=0 if passed else 1, passed=passed,
                         timed_out=False, duration_seconds=1.0, transcript=transcript)],
        detail=f"runner said {verdict}",
    )


RED_TRANSCRIPT = "  1) repro.spec.ts:12:3\n    Error: the reported TypeError must not reproduce\n"


def test_freezing_records_the_script_and_the_measured_red_run(tmp_path):
    client, conn, trace = _client(tmp_path)
    try:
        with patch("stepstitch_service.runner.run_reproduction",
                   return_value=_result("reproduced", transcript=RED_TRANSCRIPT)):
            body = client.post(f"/admin/session/{trace}/freeze", json={},
                               headers=_admin()).json()
        assert body["status"] == "ok"
        assert body["ready_for_agent"] is True
        assert len(body["script_sha256"]) == 64
        assert "an agent may change the application, not this test" in body["detail"]

        row = conn.execute(
            "SELECT sha256, red_verdict, red_signature FROM stepstitch_frozen_repros "
            "WHERE trace_id = ?", (trace,)).fetchone()
        assert row[0] == body["script_sha256"]
        assert row[1] == "reproduced"
        assert "TypeError" in row[2]        # how it failed, for comparison later
    finally:
        conn.close()


def test_freezing_says_so_when_the_failure_was_not_observed(tmp_path):
    """Handing an agent a session whose failure never happened wastes everyone's time."""
    client, conn, trace = _client(tmp_path)
    try:
        with patch("stepstitch_service.runner.run_reproduction",
                   return_value=_result("not_reproduced")):
            body = client.post(f"/admin/session/{trace}/freeze", json={},
                               headers=_admin()).json()
        assert body["ready_for_agent"] is False
        assert "nothing to prove a fix against" in body["detail"]
    finally:
        conn.close()


def test_verification_reruns_the_frozen_bytes_not_a_fresh_compile(tmp_path):
    """The referee property, at the seam: whatever the app looks like now, the test that
    judges the fix is the one recorded at freeze time."""
    client, conn, trace = _client(tmp_path)
    try:
        with patch("stepstitch_service.runner.run_reproduction",
                   return_value=_result("reproduced", transcript=RED_TRANSCRIPT)):
            frozen_sha = client.post(f"/admin/session/{trace}/freeze", json={},
                                     headers=_admin()).json()["script_sha256"]
        stored_script = conn.execute(
            "SELECT script FROM stepstitch_frozen_repros WHERE trace_id = ?",
            (trace,)).fetchone()[0]

        with patch("stepstitch_service.runner.run_reproduction",
                   return_value=_result("not_reproduced", sha=frozen_sha)) as run:
            body = client.post(f"/admin/session/{trace}/verify-fix", json={},
                               headers=_admin()).json()
        kwargs = run.call_args.kwargs
        assert kwargs["script"] == stored_script
        assert kwargs["expected_sha256"] == frozen_sha   # the runner enforces it again
        assert body["verdict"] == "fixed"
    finally:
        conn.close()


def test_a_tampered_script_is_refused_at_verification(tmp_path):
    client, conn, trace = _client(tmp_path)
    try:
        with patch("stepstitch_service.runner.run_reproduction",
                   return_value=_result("reproduced", transcript=RED_TRANSCRIPT)):
            client.post(f"/admin/session/{trace}/freeze", json={}, headers=_admin())
        with patch("stepstitch_service.runner.run_reproduction",
                   side_effect=RunnerError("this is not the frozen reproduction")):
            body = client.post(f"/admin/session/{trace}/verify-fix", json={},
                               headers=_admin()).json()
        assert body["status"] == "refused"
        assert "frozen" in body["detail"]
    finally:
        conn.close()


def test_verifying_without_freezing_first_is_unable_to_verify(tmp_path):
    client, conn, trace = _client(tmp_path)
    try:
        with patch("stepstitch_service.runner.run_reproduction") as run:
            body = client.post(f"/admin/session/{trace}/verify-fix", json={},
                               headers=_admin()).json()
        assert body["verdict"] == "unable_to_verify"
        assert "Freeze the reproduction first" in body["detail"]
        run.assert_not_called()          # nothing to run against
    finally:
        conn.close()


def test_a_changed_failure_is_reported_as_different_not_still_failing(tmp_path):
    client, conn, trace = _client(tmp_path)
    try:
        with patch("stepstitch_service.runner.run_reproduction",
                   return_value=_result("reproduced", transcript=RED_TRANSCRIPT)):
            sha = client.post(f"/admin/session/{trace}/freeze", json={},
                              headers=_admin()).json()["script_sha256"]
        with patch("stepstitch_service.runner.run_reproduction",
                   return_value=_result(
                       "reproduced", sha=sha,
                       transcript="Error: locator('#submit') resolved to 0 elements")):
            body = client.post(f"/admin/session/{trace}/verify-fix", json={},
                               headers=_admin()).json()
        assert body["verdict"] == "different_failure"
        assert "moved the problem" in body["detail"]
    finally:
        conn.close()


def test_refreezing_replaces_rather_than_accumulates(tmp_path):
    client, conn, trace = _client(tmp_path)
    try:
        for _ in range(2):
            with patch("stepstitch_service.runner.run_reproduction",
                       return_value=_result("reproduced", transcript=RED_TRANSCRIPT)):
                client.post(f"/admin/session/{trace}/freeze", json={}, headers=_admin())
        count = conn.execute(
            "SELECT count(*) FROM stepstitch_frozen_repros WHERE trace_id = ?",
            (trace,)).fetchone()[0]
        assert count == 1
    finally:
        conn.close()


def test_both_halves_of_the_loop_are_audited(tmp_path):
    client, conn, trace = _client(tmp_path)
    try:
        with patch("stepstitch_service.runner.run_reproduction",
                   return_value=_result("reproduced", transcript=RED_TRANSCRIPT)):
            sha = client.post(f"/admin/session/{trace}/freeze", json={},
                              headers=_admin()).json()["script_sha256"]
        with patch("stepstitch_service.runner.run_reproduction",
                   return_value=_result("not_reproduced", sha=sha)):
            client.post(f"/admin/session/{trace}/verify-fix", json={}, headers=_admin())
        actions = {e["action"] for e in
                   client.get(f"{_PFX}/audit", headers=_admin()).json()["entries"]}
        assert "stepstitch.freeze" in actions
        assert "stepstitch.verify_fix" in actions
    finally:
        conn.close()


def test_a_deployed_host_offers_neither_endpoint(tmp_path):
    client, conn, trace = _client(tmp_path, local_mode=False)
    try:
        assert client.post(f"/admin/session/{trace}/freeze", json={},
                           headers=_admin()).status_code == 404
        assert client.post(f"/admin/session/{trace}/verify-fix", json={},
                           headers=_admin()).status_code == 404
    finally:
        conn.close()
