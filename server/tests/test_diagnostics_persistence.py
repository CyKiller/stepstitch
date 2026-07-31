"""The diagnostics record must survive the runner's cleanup and be readable afterwards."""
from unittest.mock import patch

from fastapi.testclient import TestClient
from stepstitch_service.runner import ReproductionResult, RunAttempt

from server.audit import make_db_audit
from server.auth import build_auth
from server.host import build_app
from server.localdb import build_local_db_callables, connect_local

ADMIN, INGEST = "a", "i"
_PFX = "/api/stepstitch/v1"
PAYLOAD = {"app_id": "x", "footsteps": [
    {"timestamp": "t", "type": "exception", "route": "/x", "label": "[masked]",
     "metadata": {"error_type": "TypeError"}}], "metadata": {}}


def _client(tmp_path):
    conn = connect_local(tmp_path / "l.db")
    g, a = build_auth(ADMIN, INGEST)
    e, f1, fa = build_local_db_callables(conn)
    app = build_app(get_user_id=g, require_admin=a, execute=e, fetchone=f1, fetchall=fa,
                    audit=make_db_audit(e), admin_token=ADMIN, ingest_token=INGEST,
                    local_mode=True, base_url="http://127.0.0.1:4321")
    c = TestClient(app)
    t = c.post(f"{_PFX}/session", json=PAYLOAD,
               headers={"Authorization": f"Bearer {INGEST}"}).json()["trace_id"]
    return c, conn, t


def _result(diagnostics):
    return ReproductionResult(
        verdict="reproduced", session_id="s", script_sha256="a" * 64,
        execution_envelope_sha256="b" * 64, diagnostics=diagnostics,
        runs=[RunAttempt(index=0, exit_code=1, passed=False, timed_out=False,
                         duration_seconds=1.0, transcript="Error: boom")],
        detail="d")


DIAG = {"source": "synthetic_reproduction", "contains_customer_session_data": False,
        "schema_version": 1, "console_errors": ["pay failed"],
        "failed_requests": [{"method": "POST", "path": "/api/pay", "status": 500}]}


def test_diagnostics_survive_the_runners_cleanup(tmp_path):
    client, conn, trace = _client(tmp_path)
    try:
        with patch("stepstitch_service.runner.run_reproduction",
                   return_value=_result(DIAG)):
            client.post(f"/admin/session/{trace}/freeze", json={},
                        headers={"Authorization": f"Bearer {ADMIN}"})
        row = conn.execute(
            "SELECT source, schema_version, script_sha256, execution_envelope_sha256, "
            "diagnostics_json FROM stepstitch_diagnostics WHERE trace_id = ?",
            (trace,)).fetchone()
        assert row is not None, "the record did not survive"
        assert row[0] == "synthetic_reproduction"
        assert row[3] == "b" * 64, "the envelope digest must be stored with the record"
        assert "pay failed" in row[4]
    finally:
        conn.close()


def test_a_run_without_diagnostics_stores_nothing(tmp_path):
    client, conn, trace = _client(tmp_path)
    try:
        with patch("stepstitch_service.runner.run_reproduction",
                   return_value=_result(None)):
            client.post(f"/admin/session/{trace}/freeze", json={},
                        headers={"Authorization": f"Bearer {ADMIN}"})
        assert conn.execute("SELECT count(*) FROM stepstitch_diagnostics").fetchone()[0] == 0
    finally:
        conn.close()


def test_a_storage_failure_never_costs_us_the_verdict(tmp_path):
    """Diagnostics are the extra; the verdict is the product."""
    client, conn, trace = _client(tmp_path)
    try:
        with patch("stepstitch_service.runner.run_reproduction",
                   return_value=_result({"source": "synthetic_reproduction",
                                          "schema_version": "not-an-int"})):
            body = client.post(f"/admin/session/{trace}/freeze", json={},
                               headers={"Authorization": f"Bearer {ADMIN}"}).json()
        assert body["status"] == "ok"
        assert body["ready_for_agent"] is True
    finally:
        conn.close()

def test_refreezing_replaces_the_record_instead_of_stacking_another(tmp_path):
    """Only the newest record is ever read, so every appended row was unreachable dead
    weight — in the one table that also had no retention clock. Same discipline as the
    freeze row four lines below it: replace, never append."""
    client, conn, trace = _client(tmp_path)
    try:
        for text in ("first run", "second run"):
            diag = dict(DIAG, console_errors=[text])
            with patch("stepstitch_service.runner.run_reproduction",
                       return_value=_result(diag)):
                client.post(f"/admin/session/{trace}/freeze", json={},
                            headers={"Authorization": f"Bearer {ADMIN}"})
        rows = conn.execute("SELECT diagnostics_json FROM stepstitch_diagnostics "
                            "WHERE trace_id = ?", (trace,)).fetchall()
        assert len(rows) == 1, "re-freezing must replace, not accumulate"
        assert "second run" in rows[0][0]
    finally:
        conn.close()


def test_diagnostics_are_deleted_when_the_user_exercises_right_to_delete(tmp_path):
    """The sharpest finding of the review this fixes: the right-to-delete endpoint
    audit-logged a deletion, returned ok, and left the richest per-trace record in the
    store — orphaned, unreachable by any read path, and holding exactly the console/stack
    text with the strongest claim to deletion. Not deleted, only lost."""
    client, conn, trace = _client(tmp_path)
    try:
        with patch("stepstitch_service.runner.run_reproduction",
                   return_value=_result(DIAG)):
            client.post(f"/admin/session/{trace}/freeze", json={},
                        headers={"Authorization": f"Bearer {ADMIN}"})
        user = conn.execute("SELECT user_id FROM stepstitch_traces WHERE id = ?",
                            (trace,)).fetchone()[0]
        body = client.delete(f"{_PFX}/session/by-user/{user}",
                             headers={"Authorization": f"Bearer {ADMIN}"}).json()
        assert body["status"] == "ok"
        left = conn.execute("SELECT count(*) FROM stepstitch_diagnostics "
                            "WHERE trace_id = ?", (trace,)).fetchone()
        assert left == (0,), "deleted means deleted, diagnostics included"
    finally:
        conn.close()
