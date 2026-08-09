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
    proof = _write(tmp_path, "fixproof.json", _document())
    policy = _write(tmp_path, "policy.json", dict(POLICY, require_signature=True))
    assert main(["proof", "verify", proof, "--policy", policy]) == 1
    out = capsys.readouterr().out
    assert "FAIL" in out and "require_signature" in out


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


def test_every_recommended_command_parses():
    """House rule: anything the tool suggests must itself parse."""
    parser = build_parser()
    parser.parse_args(["proof", "export", "trc_1"])
    parser.parse_args(["proof", "export", "trc_1", "--format", "in-toto"])
    parser.parse_args(["proof", "verify", "fixproof.json", "--policy", "p.json"])
    parser.parse_args(["proof", "verify", "fixproof.json", "--policy", "p.json",
                       "--head-sha", FIXED, "--json"])
