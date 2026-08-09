"""Evidence v1 at the seam: what gets recorded, what advises, what is refused.

The grade logic is unit-tested in service/tests/test_evidence.py. These tests pin the two
things that are easy to get quietly wrong in wiring: that a caller cannot talk their way
into a stronger grade, and that a local measurement really does earn one.
"""
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from stepstitch_service.evidence import ASSERTED, MEASURED, bundle_hash
from stepstitch_service.runner import ReproductionResult, RunAttempt

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


def _repro(verdict, *, transcript="", passed=None, sha="a" * 64):
    if passed is None:
        passed = verdict == "not_reproduced"
    return ReproductionResult(
        verdict=verdict, session_id="s", script_sha256=sha,
        runs=[RunAttempt(index=0, exit_code=0 if passed else 1, passed=passed,
                         timed_out=False, duration_seconds=1.0, transcript=transcript)],
        detail=f"runner said {verdict}")


RED = "  1) repro.spec.ts:12:3\n    Error: the reported TypeError must not reproduce\n"


# --- what a caller can and cannot claim -------------------------------------------------

def test_a_ci_reported_fix_is_recorded_as_asserted(tmp_path):
    client, conn, trace = _client(tmp_path)
    try:
        body = client.post(f"{_PFX}/session/{trace}/verify",
                           json={"pre_passed": False, "post_passed": True,
                                 "fix_ref": "PR#1"}, headers=_admin()).json()
        assert body["evidence_grade"] == ASSERTED
        assert "did not observe" in body["evidence_detail"]
        grade = conn.execute(
            "SELECT evidence_grade FROM stepstitch_verifications WHERE trace_id = ?",
            (trace,)).fetchone()[0]
        assert grade == ASSERTED
    finally:
        conn.close()


def test_a_caller_cannot_claim_a_stronger_grade(tmp_path):
    """There is no input that promotes evidence. Extra fields are simply not read."""
    client, conn, trace = _client(tmp_path)
    try:
        body = client.post(
            f"{_PFX}/session/{trace}/verify",
            json={"pre_passed": False, "post_passed": True,
                  "evidence_grade": "signed", "measured_by_stepstitch": True},
            headers=_admin()).json()
        assert body["evidence_grade"] == ASSERTED
        assert conn.execute(
            "SELECT evidence_grade FROM stepstitch_verifications WHERE trace_id = ?",
            (trace,)).fetchone()[0] == ASSERTED
    finally:
        conn.close()


# --- what a measurement earns -----------------------------------------------------------

def test_a_locally_measured_fix_is_recorded_as_measured(tmp_path):
    client, conn, trace = _client(tmp_path)
    try:
        with patch("stepstitch_service.runner.run_reproduction",
                   return_value=_repro("reproduced", transcript=RED)):
            sha = client.post(f"/admin/session/{trace}/freeze", json={},
                              headers=_admin()).json()["script_sha256"]
        with patch("stepstitch_service.runner.run_reproduction",
                   return_value=_repro("not_reproduced", sha=sha)):
            body = client.post(f"/admin/session/{trace}/verify-fix", json={},
                               headers=_admin()).json()
        assert body["verdict"] == "fixed"
        row = conn.execute(
            "SELECT verdict, evidence_grade FROM stepstitch_verifications "
            "WHERE trace_id = ?", (trace,)).fetchone()
        assert row == ("confirmed_fixed", MEASURED)
    finally:
        conn.close()


def test_a_failed_verification_does_not_enter_the_corpus(tmp_path):
    """Only a real red-to-green is a fix. Recording anything else would inflate the corpus
    with work that did not land."""
    client, conn, trace = _client(tmp_path)
    try:
        with patch("stepstitch_service.runner.run_reproduction",
                   return_value=_repro("reproduced", transcript=RED)):
            sha = client.post(f"/admin/session/{trace}/freeze", json={},
                              headers=_admin()).json()["script_sha256"]
        with patch("stepstitch_service.runner.run_reproduction",
                   return_value=_repro("reproduced", sha=sha, transcript=RED)):
            body = client.post(f"/admin/session/{trace}/verify-fix", json={},
                               headers=_admin()).json()
        assert body["verdict"] == "still_failing"
        assert conn.execute(
            "SELECT count(*) FROM stepstitch_verifications WHERE trace_id = ?",
            (trace,)).fetchone()[0] == 0
    finally:
        conn.close()


# --- the attestation carries it, and tampering is refused -------------------------------

def test_the_attestation_states_how_the_fix_was_established(tmp_path):
    client, conn, trace = _client(tmp_path)
    try:
        with patch("stepstitch_service.runner.run_reproduction",
                   return_value=_repro("reproduced", transcript=RED)):
            sha = client.post(f"/admin/session/{trace}/freeze", json={},
                              headers=_admin()).json()["script_sha256"]
        with patch("stepstitch_service.runner.run_reproduction",
                   return_value=_repro("not_reproduced", sha=sha)):
            client.post(f"/admin/session/{trace}/verify-fix", json={}, headers=_admin())

        att = client.get(f"{_PFX}/session/{trace}/attestation", headers=_admin()).json()
        assert att["bundle"]["verification"]["evidence_grade"] == MEASURED
    finally:
        conn.close()


def test_an_altered_bundle_is_refused_by_the_verify_endpoint(tmp_path):
    client, conn, trace = _client(tmp_path)
    try:
        att = client.get(f"{_PFX}/session/{trace}/attestation", headers=_admin()).json()
        good = {"bundle": att["bundle"], "bundle_sha256": att["bundle_sha256"]}
        assert client.post(f"{_PFX}/attestation/verify", json=good,
                           headers=_admin()).json()["verified"] is True

        tampered = dict(att["bundle"])
        tampered["trace_id"] = "someone-elses-trace"
        r = client.post(f"{_PFX}/attestation/verify",
                        json={"bundle": tampered,
                              "bundle_sha256": att["bundle_sha256"]}, headers=_admin())
        # A refusal, not a 200 with a flag a caller might forget to read.
        assert r.status_code == 422
        assert "altered" in r.json()["detail"]
    finally:
        conn.close()


def test_verification_does_not_consult_our_own_database(tmp_path):
    """An attestation must be checkable by someone who does not trust the issuer, so the
    check has to work on a bundle for a trace this host has never heard of."""
    client, conn, _ = _client(tmp_path)
    try:
        foreign = {"schema": "stepstitch/attestation@v1", "trace_id": "from-another-host",
                   "verification": {"verdict": "confirmed_fixed",
                                    "evidence_grade": MEASURED}}
        r = client.post(f"{_PFX}/attestation/verify",
                        json={"bundle": foreign, "bundle_sha256": bundle_hash(foreign)},
                        headers=_admin())
        assert r.status_code == 200 and r.json()["verified"] is True
        assert r.json()["evidence_grade"] == MEASURED
    finally:
        conn.close()


# --- FixProof bindings: which code, and who said so -------------------------------------

FIXED_SHA = "b" * 40
BASE_SHA = "a" * 40


def test_a_verification_records_which_code_and_who_reported_it(tmp_path):
    """The row must be able to answer "this verdict is about THAT commit, reported by
    THAT identity" — a FixProof subject cannot be built from free-text fix_ref."""
    client, conn, trace = _client(tmp_path)
    try:
        body = client.post(f"{_PFX}/session/{trace}/verify",
                           json={"pre_passed": False, "post_passed": True,
                                 "base_commit": BASE_SHA, "fixed_commit": FIXED_SHA},
                           headers=_admin()).json()
        assert body["base_commit"] == BASE_SHA
        assert body["fixed_commit"] == FIXED_SHA
        row = conn.execute(
            "SELECT base_commit, fixed_commit, verified_by "
            "FROM stepstitch_verifications WHERE trace_id = ?", (trace,)).fetchone()
        assert row == (BASE_SHA, FIXED_SHA, "admin")
    finally:
        conn.close()


def test_a_commit_that_is_not_a_full_sha_is_refused_not_coerced(tmp_path):
    """"main", an abbreviation, or a 39-hex near-miss names nothing verifiable — storing
    it would let a proof subject point at thin air."""
    client, conn, trace = _client(tmp_path)
    try:
        for bad in ("main", "abc123", "B" * 39, "g" * 40):
            r = client.post(f"{_PFX}/session/{trace}/verify",
                            json={"pre_passed": False, "post_passed": True,
                                  "fixed_commit": bad}, headers=_admin())
            assert r.status_code == 422, f"{bad!r} was accepted"
        assert conn.execute(
            "SELECT COUNT(*) FROM stepstitch_verifications WHERE trace_id = ?",
            (trace,)).fetchone()[0] == 0
    finally:
        conn.close()


def test_an_uppercase_full_sha_is_normalized_not_refused(tmp_path):
    """git prints lowercase but humans paste what they copied; case is not identity."""
    client, conn, trace = _client(tmp_path)
    try:
        r = client.post(f"{_PFX}/session/{trace}/verify",
                        json={"pre_passed": False, "post_passed": True,
                              "fixed_commit": FIXED_SHA.upper()}, headers=_admin())
        assert r.status_code == 200
        assert r.json()["fixed_commit"] == FIXED_SHA
    finally:
        conn.close()


def test_a_measured_verification_records_commits_and_verifier(tmp_path):
    client, conn, trace = _client(tmp_path)
    try:
        with patch("stepstitch_service.runner.run_reproduction",
                   return_value=_repro("reproduced", transcript=RED)):
            sha = client.post(f"/admin/session/{trace}/freeze", json={},
                              headers=_admin()).json()["script_sha256"]
        with patch("stepstitch_service.runner.run_reproduction",
                   return_value=_repro("not_reproduced", sha=sha)):
            body = client.post(f"/admin/session/{trace}/verify-fix",
                               json={"base_commit": BASE_SHA,
                                     "fixed_commit": FIXED_SHA},
                               headers=_admin()).json()
        assert body["verdict"] == "fixed"
        row = conn.execute(
            "SELECT base_commit, fixed_commit, verified_by, evidence_grade "
            "FROM stepstitch_verifications WHERE trace_id = ?", (trace,)).fetchone()
        assert row == (BASE_SHA, FIXED_SHA, "admin", MEASURED)
    finally:
        conn.close()
