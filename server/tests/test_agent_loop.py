"""The agent loop's seam: freeze, hand off, judge with the frozen bytes.

The verdict logic is covered in service/tests/test_fixcheck.py. These tests cover what the
host stores and refuses — above all, that the frozen script is what verification reruns,
so a fixing agent can never grade its own homework.
"""
import json
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from stepstitch_service.diagnostics import EnvelopeMismatch
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


def _result(verdict, *, transcript="", passed=None, sha="a" * 64, envelope_sha="e" * 64):
    if passed is None:
        passed = verdict == "not_reproduced"
    return ReproductionResult(
        verdict=verdict, session_id="s", script_sha256=sha,
        runs=[RunAttempt(index=0, exit_code=0 if passed else 1, passed=passed,
                         timed_out=False, duration_seconds=1.0, transcript=transcript)],
        detail=f"runner said {verdict}",
        execution_envelope_sha256=envelope_sha,
        execution_envelope={"browser": "chromium 149.0 (build 1228)",
                            "base_url": "http://127.0.0.1:4321"},
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


def test_the_freeze_records_the_envelope_it_measured_under(tmp_path):
    """The digest lives on the freeze row, 1:1 with the script it pins — not found back by
    a latest-diagnostics heuristic that a re-freeze or stray run makes wrong."""
    client, conn, trace = _client(tmp_path)
    try:
        with patch("stepstitch_service.runner.run_reproduction",
                   return_value=_result("reproduced", transcript=RED_TRANSCRIPT)):
            client.post(f"/admin/session/{trace}/freeze", json={}, headers=_admin())
        row = conn.execute(
            "SELECT execution_envelope_sha256, execution_envelope_json "
            "FROM stepstitch_frozen_repros WHERE trace_id = ?", (trace,)).fetchone()
        assert row[0] == "e" * 64
        assert "chromium" in row[1], "the record, so a refusal can say which field moved"
    finally:
        conn.close()


def test_verify_fix_passes_the_frozen_envelope_to_the_runner(tmp_path):
    """Repo-wide, `expected_envelope_sha256` used to appear only in the runner's own unit
    tests. Nothing exercised the production call path, which is how the packet came to
    promise enforcement that never happened."""
    client, conn, trace = _client(tmp_path)
    try:
        with patch("stepstitch_service.runner.run_reproduction",
                   return_value=_result("reproduced", transcript=RED_TRANSCRIPT)):
            client.post(f"/admin/session/{trace}/freeze", json={}, headers=_admin())
        with patch("stepstitch_service.runner.run_reproduction",
                   return_value=_result("not_reproduced")) as run:
            body = client.post(f"/admin/session/{trace}/verify-fix", json={},
                               headers=_admin()).json()
        assert run.call_args.kwargs["expected_envelope_sha256"] == "e" * 64
        assert body["verdict"] == "fixed"
        assert body["envelope_enforced"] is True
    finally:
        conn.close()


def test_a_session_frozen_before_the_envelope_column_still_verifies(tmp_path):
    """Legacy rows degrade, they do not refuse. A refusal would force a re-freeze, and
    re-freezing after the agent has edited the app destroys the red baseline — the one
    artefact that cannot be recreated. The reduction is REPORTED, not silent."""
    client, conn, trace = _client(tmp_path)
    try:
        with patch("stepstitch_service.runner.run_reproduction",
                   return_value=_result("reproduced", transcript=RED_TRANSCRIPT)):
            client.post(f"/admin/session/{trace}/freeze", json={}, headers=_admin())
        conn.execute("UPDATE stepstitch_frozen_repros SET execution_envelope_sha256 = NULL, "
                     "execution_envelope_json = NULL WHERE trace_id = ?", (trace,))
        with patch("stepstitch_service.runner.run_reproduction",
                   return_value=_result("not_reproduced")) as run:
            body = client.post(f"/admin/session/{trace}/verify-fix", json={},
                               headers=_admin()).json()
        assert run.call_args.kwargs["expected_envelope_sha256"] is None
        assert body["verdict"] == "fixed"
        assert body["envelope_enforced"] is False, "weaker evidence, said out loud"
    finally:
        conn.close()


def test_the_packet_serves_the_frozen_envelope_not_the_latest_diagnostics(tmp_path):
    """The old source was `stepstitch_diagnostics ORDER BY created_at DESC LIMIT 1` — the
    latest row, which is not the frozen one after any subsequent run. The packet's sentence
    to the agent is about the FROZEN envelope, so it must come from the freeze row."""
    client, conn, trace = _client(tmp_path)
    try:
        with patch("stepstitch_service.runner.run_reproduction",
                   return_value=_result("reproduced", transcript=RED_TRANSCRIPT)):
            client.post(f"/admin/session/{trace}/freeze", json={}, headers=_admin())
        # A later diagnostics row with a DIFFERENT envelope — the heuristic would serve it.
        conn.execute(
            "INSERT INTO stepstitch_diagnostics (id, trace_id, run_id, source, "
            "schema_version, script_sha256, execution_envelope_sha256, diagnostics_json, "
            "created_at) VALUES ('x', ?, 'r', 'local_reproduction', 1, 's', ?, '{}', "
            "'2099-01-01T00:00:00+00:00')", (trace, "f" * 64))
        body = client.get(f"{_PFX}/session/{trace}/agent-packet",
                          headers=_admin()).json()
        packet = json.dumps(body)
        assert ("e" * 64) in packet, "the frozen envelope"
        assert ("f" * 64) not in packet, "the stray later run must not displace it"
    finally:
        conn.close()


def test_a_reproduction_that_could_not_launch_is_not_frozen(tmp_path):
    """Freezing a run that never ran records a referee that never refereed.

    The worst case this guards: browser purged, freeze called, a "red baseline" written
    whose signature is the launch error. The session then reads ready-for-agent, and the
    moment the browser comes back the agent is asked to fix a bug that does not exist.
    """
    client, conn, trace = _client(tmp_path)
    try:
        needs_setup = ReproductionResult(
            verdict="needs_setup", session_id="s", script_sha256="a" * 64,
            detail="Playwright browser: chromium is not installed. "
                   "Run: npx playwright install chromium")
        with patch("stepstitch_service.runner.run_reproduction",
                   return_value=needs_setup):
            body = client.post(f"/admin/session/{trace}/freeze", json={},
                               headers=_admin()).json()
        assert body["ready_for_agent"] is False
        assert "cannot run the reproduction" in body["detail"]
        row = conn.execute("SELECT count(*) FROM stepstitch_frozen_repros "
                           "WHERE trace_id = ?", (trace,)).fetchone()
        assert row == (0,), "nothing ran, so nothing may be frozen"
    finally:
        conn.close()


def test_an_envelope_mismatch_is_refused_not_a_server_error(tmp_path):
    """A refusal is an answer. Presented as a 500 it reads as "StepStitch is broken".

    `EnvelopeMismatch` is not a `RunnerError` and cannot become one — diagnostics.py is
    deliberately runner-free — so every place that catches a refusal has to name it. Until
    it did, the first genuine mismatch would have escaped as an unhandled exception on the
    product's central path, and the bug would only appear once envelope enforcement was
    switched on: a trap laid for the commit that fixes something else.
    """
    client, conn, trace = _client(tmp_path)
    try:
        with patch("stepstitch_service.runner.run_reproduction",
                   return_value=_result("reproduced", transcript=RED_TRANSCRIPT)):
            client.post(f"/admin/session/{trace}/freeze", json={}, headers=_admin())
        with patch("stepstitch_service.runner.run_reproduction",
                   side_effect=EnvelopeMismatch(
                       "this run is not the experiment that was frozen")):
            response = client.post(f"/admin/session/{trace}/verify-fix", json={},
                                   headers=_admin())
        assert response.status_code == 200, "a refusal is not a server fault"
        body = response.json()
        assert body["status"] == "refused"
        assert "experiment" in body["detail"]
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
