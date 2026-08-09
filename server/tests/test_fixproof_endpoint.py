"""The FixProof endpoints at the seam: built only from recorded evidence, refused
otherwise, and verifiable offline by someone who does not trust this host.

The proof core is unit-tested adversarially in service/tests/test_fixproof.py; these
tests pin the wiring — that the endpoint's output is exactly what the offline verifier
accepts, and that every missing prerequisite is a refusal instead of a fabrication.
"""
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from stepstitch_service.fixproof import verify_fixproof
from stepstitch_service.host.agents import scope_allows
from stepstitch_service.runner import ReproductionResult, RunAttempt

from server.audit import make_db_audit
from server.auth import build_auth
from server.host import build_app
from server.localdb import build_local_db_callables, connect_local

ADMIN = "admin-secret"
INGEST = "ingest-secret"
_PFX = "/api/stepstitch/v1"

FIXED_SHA = "b" * 40
BASE_SHA = "a" * 40

_PAYLOAD = {
    "app_id": "tiny-transfer",
    "footsteps": [
        {"timestamp": "2026-08-08T12:00:00Z", "type": "navigation", "route": "/transfer",
         "label": "[masked]"},
        {"timestamp": "2026-08-08T12:00:02Z", "type": "exception", "route": "/transfer",
         "label": "[masked]", "metadata": {"error_type": "TypeError"}},
    ],
    "metadata": {"sdk_version": "0.8.0"},
}

POLICY = {
    "require_grade": "measured",
    "require_pre_red": True,
    "require_post_green": True,
    "require_signature": False,
    "allowed_verifier_kinds": ["measured-by-host"],
    "require_privacy": {},
    "expected_head_sha": None,
}

RED = "  1) repro.spec.ts:12:3\n    Error: the reported TypeError must not reproduce\n"


def _client(tmp_path, *, sign_blob=None):
    conn = connect_local(tmp_path / "local.db")
    get_user_id, require_admin = build_auth(ADMIN, INGEST)
    execute, fetchone, fetchall = build_local_db_callables(conn)
    app: FastAPI = build_app(
        get_user_id=get_user_id, require_admin=require_admin,
        execute=execute, fetchone=fetchone, fetchall=fetchall,
        audit=make_db_audit(execute),
        admin_token=ADMIN, ingest_token=INGEST, local_mode=True,
        base_url="http://127.0.0.1:4321", sign_blob=sign_blob,
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
        detail=f"runner said {verdict}",
        # A real freeze records the run's execution envelope; the fake must too, or
        # the exported proof lacks the envelope binding a hardened policy requires.
        execution_envelope_sha256="e" * 64)


def _measure_fix(client, trace, *, fixed_commit=FIXED_SHA, base_commit=BASE_SHA):
    """Freeze red, then verify-fix green with commit bindings — the measured path."""
    with patch("stepstitch_service.runner.run_reproduction",
               return_value=_repro("reproduced", transcript=RED)):
        sha = client.post(f"/admin/session/{trace}/freeze", json={},
                          headers=_admin()).json()["script_sha256"]
    with patch("stepstitch_service.runner.run_reproduction",
               return_value=_repro("not_reproduced", sha=sha)):
        body = client.post(f"/admin/session/{trace}/verify-fix",
                           json={"base_commit": base_commit,
                                 "fixed_commit": fixed_commit},
                           headers=_admin()).json()
    assert body["verdict"] == "fixed"


def test_a_measured_fix_yields_a_proof_the_offline_verifier_accepts(tmp_path):
    client, conn, trace = _client(tmp_path)
    try:
        _measure_fix(client, trace)
        body = client.get(f"{_PFX}/session/{trace}/fixproof", headers=_admin()).json()
        doc = body["fixproof"]
        assert doc["schema"] == "stepstitch.fixproof/v2"
        s = doc["statement"]
        assert s["subject"][0]["digest"]["gitCommit"] == FIXED_SHA
        assert s["predicate"]["base_commit"] == {"gitCommit": BASE_SHA}
        assert s["predicate"]["verifier"]["kind"] == "measured-by-host"
        assert s["predicate"]["verifier"]["identity"] == "admin"
        assert s["predicate"]["frozen_test"]["sha256"].startswith("sha256:")
        assert s["predicate"]["privacy"]["policy_sha256"].startswith("sha256:")
        # The point of the whole feature: independent acceptance, no host consulted.
        assert verify_fixproof(doc, dict(POLICY), head_sha=FIXED_SHA).ok
    finally:
        conn.close()


def test_an_altered_export_is_refused_by_the_offline_verifier(tmp_path):
    client, conn, trace = _client(tmp_path)
    try:
        _measure_fix(client, trace)
        doc = client.get(f"{_PFX}/session/{trace}/fixproof",
                         headers=_admin()).json()["fixproof"]
        doc["statement"]["predicate"]["results"]["pre_passed"] = True
        import pytest
        from stepstitch_service.evidence import TamperError
        with pytest.raises(TamperError):
            verify_fixproof(doc, dict(POLICY))
    finally:
        conn.close()


def test_without_a_fixed_commit_the_proof_is_refused_not_fabricated(tmp_path):
    """A verification exists, but nothing names the code — 409, never a made-up subject."""
    client, conn, trace = _client(tmp_path)
    try:
        r = client.post(f"{_PFX}/session/{trace}/verify",
                        json={"pre_passed": False, "post_passed": True},
                        headers=_admin())
        assert r.status_code == 200
        r = client.get(f"{_PFX}/session/{trace}/fixproof", headers=_admin())
        assert r.status_code == 409
        assert "fixed_commit" in r.json()["detail"]
    finally:
        conn.close()


def test_without_a_freeze_the_proof_is_refused(tmp_path):
    """A commit-bearing asserted verification alone is not enough: no frozen bytes, no
    frozen-test digest to bind."""
    client, conn, trace = _client(tmp_path)
    try:
        client.post(f"{_PFX}/session/{trace}/verify",
                    json={"pre_passed": False, "post_passed": True,
                          "fixed_commit": FIXED_SHA}, headers=_admin())
        r = client.get(f"{_PFX}/session/{trace}/fixproof", headers=_admin())
        assert r.status_code == 409
        assert "frozen" in r.json()["detail"].lower()
    finally:
        conn.close()


def test_an_unknown_trace_is_404(tmp_path):
    client, conn, _ = _client(tmp_path)
    try:
        assert client.get(f"{_PFX}/session/nope/fixproof",
                          headers=_admin()).status_code == 404
    finally:
        conn.close()


def test_the_download_is_the_bare_document_with_a_safe_filename(tmp_path):
    client, conn, trace = _client(tmp_path)
    try:
        _measure_fix(client, trace)
        r = client.get(f"{_PFX}/session/{trace}/fixproof/download", headers=_admin())
        assert r.status_code == 200
        assert "attachment" in r.headers["content-disposition"]
        assert "-fixproof.json" in r.headers["content-disposition"]
        # The file IS the verifiable document — not the endpoint envelope around it.
        assert verify_fixproof(r.json(), dict(POLICY), head_sha=FIXED_SHA).ok
    finally:
        conn.close()


def test_a_signed_export_verifies_cryptographically_and_a_fake_string_does_not(
        tmp_path):
    """The host signs with a REAL ed25519 key through the same seam production uses,
    and the offline verifier accepts it only against that key's public half. The fake
    string this test used to inject is the trust-audit exploit: it must now fail the
    signature requirement."""
    import hashlib

    from stepstitch_service import _ed25519
    from stepstitch_service.host.signing import make_ed25519_signer

    seed = hashlib.sha256(b"fixproof endpoint test key").digest()
    signer = make_ed25519_signer(seed, "test-host")
    client, conn, trace = _client(tmp_path, sign_blob=signer)
    try:
        _measure_fix(client, trace)
        body = client.get(f"{_PFX}/session/{trace}/fixproof", headers=_admin()).json()
        assert body["signed"] is True
        signature = body["fixproof"]["signature"]
        assert signature["algorithm"] == "ed25519"
        assert signature["key_id"] == "test-host"
        trusting = dict(POLICY, require_signature=True,
                        trusted_keys={"test-host":
                                      "ed25519:" + _ed25519.public_key(seed).hex()})
        assert verify_fixproof(body["fixproof"], trusting).ok

        # The wrong trust anchor refuses the same intact document.
        stranger = hashlib.sha256(b"some other key").digest()
        distrusting = dict(trusting,
                           trusted_keys={"test-host":
                                         "ed25519:"
                                         + _ed25519.public_key(stranger).hex()})
        rejected = verify_fixproof(body["fixproof"], distrusting)
        assert not rejected.ok

        # And an opaque string — what this test used to call "signed" — never passes.
        faked = dict(body["fixproof"], signature="fake-signature-over-statement")
        result = verify_fixproof(faked, trusting)
        assert not result.ok
        assert any(c["check"] == "require_signature" and not c["passed"]
                   for c in result.checks)
    finally:
        conn.close()


def test_an_asserted_verification_with_commit_exports_but_fails_a_measured_floor(tmp_path):
    """The proof honestly says asserted-by-caller; the shipped policy then rejects it.
    Export never upgrades evidence — the gate does the refusing."""
    client, conn, trace = _client(tmp_path)
    try:
        # Freeze (red) so the frozen-test digest exists, but let CI *assert* the outcome.
        with patch("stepstitch_service.runner.run_reproduction",
                   return_value=_repro("reproduced", transcript=RED)):
            client.post(f"/admin/session/{trace}/freeze", json={}, headers=_admin())
        client.post(f"{_PFX}/session/{trace}/verify",
                    json={"pre_passed": False, "post_passed": True,
                          "fixed_commit": FIXED_SHA}, headers=_admin())
        doc = client.get(f"{_PFX}/session/{trace}/fixproof",
                         headers=_admin()).json()["fixproof"]
        assert doc["statement"]["predicate"]["verifier"]["kind"] == "asserted-by-caller"
        result = verify_fixproof(doc, dict(POLICY))
        assert not result.ok
        failed = {c["check"] for c in result.checks if not c["passed"]}
        assert {"require_grade", "allowed_verifier_kinds"} <= failed
    finally:
        conn.close()


def test_agent_scopes_cover_fixproof_like_the_attestation():
    """summaries reads it (no repro code inside), verify exports the proof it earned,
    and nothing below summaries sees it."""
    for path in (f"{_PFX}/session/t1/fixproof", f"{_PFX}/session/t1/fixproof/download"):
        assert scope_allows("summaries", "GET", path)
        assert scope_allows("repros", "GET", path)
        assert scope_allows("verify", "GET", path)
        assert not scope_allows("none", "GET", path)
    assert not scope_allows("summaries", "POST", f"{_PFX}/session/t1/fixproof")


def test_the_full_customer_chain_from_measured_export_through_the_merge_gate(tmp_path):
    """The second audit's definitive requirement, in one test: a real git repository,
    a host-MEASURED verification bound to that repository's actual code commit, the
    host-SIGNED export, a proof-only commit on top, and the exact `proof gate` command
    the generated workflow runs — accepted. Then the two protocol attacks — code after
    the proof, a stowaway file — refused against the very same repository."""
    import hashlib
    import json
    import subprocess

    from stepstitch_service import _ed25519
    from stepstitch_service.cli import main
    from stepstitch_service.host.signing import make_ed25519_signer

    def git(*argv):
        return subprocess.run(
            ["git", "-C", str(repo), "-c", "user.name=chain",
             "-c", "user.email=chain@example.test", "-c", "commit.gpgsign=false",
             *argv],
            capture_output=True, text=True, timeout=60, check=True,
        ).stdout.strip()

    repo = tmp_path / "customer-repo"
    repo.mkdir()
    git("init", "-q")
    (repo / "app.py").write_text("def handler():\n    return 'fixed'\n",
                                 encoding="utf-8")
    git("add", "app.py")
    git("commit", "-q", "-m", "the fix (commit A)")
    code_commit = git("rev-parse", "HEAD")

    seed = hashlib.sha256(b"full-chain host key").digest()
    client, conn, trace = _client(tmp_path,
                                  sign_blob=make_ed25519_signer(seed, "host"))
    try:
        _measure_fix(client, trace, fixed_commit=code_commit)
        document = client.get(f"{_PFX}/session/{trace}/fixproof",
                              headers=_admin()).json()["fixproof"]
    finally:
        conn.close()

    (repo / "fixproof.json").write_text(json.dumps(document, indent=2),
                                        encoding="utf-8")
    git("add", "fixproof.json")
    git("commit", "-q", "-m", f"fixproof for {code_commit} (commit B)")
    head = git("rev-parse", "HEAD")

    policy_path = tmp_path / "proof-policy.json"
    policy_path.write_text(json.dumps({
        "require_grade": "measured",
        "require_pre_red": True,
        "require_post_green": True,
        "require_signature": True,
        "trusted_keys": {"host": "ed25519:" + _ed25519.public_key(seed).hex()},
        "require_bindings": True,
        "allowed_verifier_kinds": ["measured-by-host"],
        "allowed_verifier_identities": ["admin"],
        "require_privacy": {},
        "expected_head_sha": None,
    }), encoding="utf-8")

    assert main(["proof", "gate", head, "--policy", str(policy_path),
                 "--repo", str(repo)]) == 0

    # Attack: code pushed after the proof rides a stale proof — refused.
    (repo / "app.py").write_text("def handler():\n    return 'untested'\n",
                                 encoding="utf-8")
    git("add", "app.py")
    git("commit", "-q", "-m", "code after the proof")
    assert main(["proof", "gate", git("rev-parse", "HEAD"),
                 "--policy", str(policy_path), "--repo", str(repo)]) == 1
