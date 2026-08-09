"""`stepstitch proof` — the exit-code contract and the offline guarantee.

export talks to a host through the injectable transport (the doctor pattern); verify
must work with NOTHING but two files — a proof and a policy — because the merge gate
that runs it has no host, no token, and no reason to trust either side.
"""
from __future__ import annotations

import json

from stepstitch_service.cli import _proof_command, build_parser, main
from stepstitch_service.fixproof import build_fixproof_statement, wrap

FIXED = "b" * 40

POLICY = {
    "require_grade": "measured",
    "require_pre_red": True,
    "require_post_green": True,
    "require_signature": False,
    "allowed_verifier_kinds": ["measured-by-host"],
    "require_privacy": {},
    "expected_head_sha": None,
}


def _document():
    return wrap(build_fixproof_statement(
        trace_id="trc_1", subject_name="app", fixed_commit=FIXED,
        frozen_test_sha256="c" * 64, pre_passed=False, post_passed=True,
        verdict="confirmed_fixed", policy="financial-services-strict",
        verifier_identity="admin", evidence_grade="measured",
        issued_at="2026-08-08T12:00:00+00:00",
    ))


def _write(tmp_path, name, payload):
    path = tmp_path / name
    path.write_text(json.dumps(payload), encoding="utf-8")
    return str(path)


# --- verify: offline, 0/1/2 ---------------------------------------------------------------


def test_a_good_proof_verifies_with_exit_0(tmp_path, capsys):
    proof = _write(tmp_path, "fixproof.json", _document())
    policy = _write(tmp_path, "policy.json", POLICY)
    assert main(["proof", "verify", proof, "--policy", policy]) == 0
    assert "proof verified" in capsys.readouterr().out


def test_a_tampered_proof_exits_1(tmp_path, capsys):
    doc = _document()
    doc["statement"]["predicate"]["results"]["pre_passed"] = True
    proof = _write(tmp_path, "fixproof.json", doc)
    policy = _write(tmp_path, "policy.json", POLICY)
    assert main(["proof", "verify", proof, "--policy", policy]) == 1
    assert "TAMPERED" in capsys.readouterr().out


def test_a_policy_rejection_exits_1_and_names_the_check(tmp_path, capsys):
    """An unsigned proof against a policy that requires a trusted signature: the proof
    is rejected (1), and the failing check is named. (require_signature WITHOUT any
    trusted key is a different outcome — an unusable policy, exit 2, tested below.)"""
    import hashlib

    from stepstitch_service import _ed25519

    proof = _write(tmp_path, "fixproof.json", _document())
    pub = "ed25519:" + _ed25519.public_key(
        hashlib.sha256(b"proof-cli test key").digest()).hex()
    policy = _write(tmp_path, "policy.json",
                    dict(POLICY, require_signature=True,
                         trusted_keys={"host": pub}))
    assert main(["proof", "verify", proof, "--policy", policy]) == 1
    out = capsys.readouterr().out
    assert "FAIL" in out and "require_signature" in out


def test_an_unconfigured_signature_requirement_is_unusable_not_a_rejection(
        tmp_path, capsys):
    """require_signature true with no trusted_keys = the gate was never configured.
    That must exit 2 (unusable), never 1 — and never 0."""
    proof = _write(tmp_path, "fixproof.json", _document())
    policy = _write(tmp_path, "policy.json", dict(POLICY, require_signature=True))
    assert main(["proof", "verify", proof, "--policy", policy]) == 2
    assert "trusted_keys" in capsys.readouterr().out


def test_a_head_sha_mismatch_exits_1(tmp_path):
    proof = _write(tmp_path, "fixproof.json", _document())
    policy = _write(tmp_path, "policy.json", POLICY)
    assert main(["proof", "verify", proof, "--policy", policy,
                 "--head-sha", "f" * 40]) == 1
    assert main(["proof", "verify", proof, "--policy", policy,
                 "--head-sha", FIXED]) == 0


def test_unusable_inputs_exit_2(tmp_path):
    good_proof = _write(tmp_path, "fixproof.json", _document())
    good_policy = _write(tmp_path, "policy.json", POLICY)
    bad_json = tmp_path / "broken.json"
    bad_json.write_text("{not json", encoding="utf-8")
    assert main(["proof", "verify", str(tmp_path / "missing.json"),
                 "--policy", good_policy]) == 2
    assert main(["proof", "verify", str(bad_json), "--policy", good_policy]) == 2
    assert main(["proof", "verify", good_proof,
                 "--policy", str(bad_json)]) == 2
    typo = _write(tmp_path, "typo.json", dict(POLICY, require_grde="measured"))
    assert main(["proof", "verify", good_proof, "--policy", typo]) == 2
    assert main(["proof"]) == 2  # missing subcommand → help, not a traceback


def test_json_output_is_machine_readable(tmp_path, capsys):
    proof = _write(tmp_path, "fixproof.json", _document())
    policy = _write(tmp_path, "policy.json", POLICY)
    assert main(["proof", "verify", proof, "--policy", policy, "--json"]) == 0
    parsed = json.loads(capsys.readouterr().out)
    assert parsed["ok"] is True
    assert all("check" in c and "passed" in c for c in parsed["checks"])


# --- export: transport-injected, never a traceback ----------------------------------------


def _run_export(tmp_path, transport, extra=None):
    parser = build_parser()
    args = parser.parse_args(["proof", "export", "trc_1",
                              "--out", str(tmp_path / "out.json")] + (extra or []))
    return _proof_command(args, parser, transport=transport)


def test_export_writes_the_document_the_host_returned(tmp_path, capsys):
    doc = _document()

    def transport(url, method, headers, body):
        assert url.endswith("/api/stepstitch/v1/session/trc_1/fixproof")
        assert method == "GET"
        return 200, {"status": "ok", "fixproof": doc,
                     "statement_sha256": doc["statement_sha256"], "signed": False}

    assert _run_export(tmp_path, transport) == 0
    written = json.loads((tmp_path / "out.json").read_text(encoding="utf-8"))
    assert written == doc
    assert "unsigned" in capsys.readouterr().out


def test_export_surfaces_the_hosts_refusal(tmp_path, capsys):
    def transport(url, method, headers, body):
        return 409, {"detail": "no verification for this trace names the fixed commit"}

    assert _run_export(tmp_path, transport) == 1
    assert "fixed commit" in capsys.readouterr().out


def test_export_reports_an_unreachable_host_as_a_finding(tmp_path, capsys):
    def transport(url, method, headers, body):
        return 0, None

    assert _run_export(tmp_path, transport) == 1
    assert "STEPSTITCH_ADMIN_TOKEN" in capsys.readouterr().out


# --- keygen: the trust anchor's origin story ----------------------------------------------


def test_keygen_writes_a_private_seed_and_prints_only_the_public_key(tmp_path, capsys):
    from stepstitch_service import _ed25519

    out = tmp_path / "signing.key"
    assert main(["proof", "keygen", "--out", str(out),
                 "--key-id", "acme-host"]) == 0
    seed_hex = out.read_text(encoding="utf-8").strip()
    assert len(seed_hex) == 64
    assert (out.stat().st_mode & 0o777) == 0o600
    printed = capsys.readouterr().out
    public = "ed25519:" + _ed25519.public_key(bytes.fromhex(seed_hex)).hex()
    assert public in printed, "the public key must be printed to paste into the policy"
    assert seed_hex not in printed, "the private seed must never reach the terminal"
    assert "acme-host" in printed and "trusted_keys" in printed


def test_keygen_refuses_to_overwrite_an_existing_key(tmp_path, capsys):
    out = tmp_path / "signing.key"
    out.write_text("do not clobber me", encoding="utf-8")
    assert main(["proof", "keygen", "--out", str(out)]) == 2
    assert out.read_text(encoding="utf-8") == "do not clobber me"
    assert "refusing" in capsys.readouterr().out


def test_the_keygen_key_signs_proofs_the_hardened_policy_accepts(tmp_path):
    """The whole customer path, end to end: keygen -> host signer loads the file ->
    signature object on the document -> offline verify against the printed public key."""
    from stepstitch_service import _ed25519
    from stepstitch_service.attestation import canonical_bytes
    from stepstitch_service.host.signing import (load_signing_seed,
                                                 make_ed25519_signer)

    out = tmp_path / "signing.key"
    assert main(["proof", "keygen", "--out", str(out)]) == 0
    seed = load_signing_seed(str(out))
    assert seed is not None

    doc = _document()
    doc["signature"] = make_ed25519_signer(seed, "kid")(
        canonical_bytes(doc["statement"]))
    proof = _write(tmp_path, "fixproof.json", doc)
    public = "ed25519:" + _ed25519.public_key(seed).hex()
    policy = _write(tmp_path, "policy.json",
                    dict(POLICY, require_signature=True,
                         trusted_keys={"kid": public}))
    assert main(["proof", "verify", proof, "--policy", policy]) == 0


def test_every_recommended_command_parses():
    """House rule: anything the tool suggests must itself parse."""
    parser = build_parser()
    parser.parse_args(["proof", "export", "trc_1"])
    parser.parse_args(["proof", "export", "trc_1", "--format", "in-toto"])
    parser.parse_args(["proof", "verify", "fixproof.json", "--policy", "p.json"])
    parser.parse_args(["proof", "verify", "fixproof.json", "--policy", "p.json",
                       "--head-sha", FIXED, "--json"])
    parser.parse_args(["proof", "keygen"])
    parser.parse_args(["proof", "keygen", "--out", "k.key", "--key-id", "host-1"])
