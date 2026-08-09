"""The proof-only-commit protocol, proven in real git repositories.

The second trust audit found the documented flow impossible: committing fixproof.json
into the fix PR moves the head the proof was supposed to name — forever. The protocol
that resolves it, permanently pinned here:

    A = the exact tested code commit           (the proof's subject)
    B = a child commit adding ONLY fixproof.json   (the PR head)

``stepstitch proof gate <head>`` enforces all of it: exactly one parent, HEAD^..HEAD
touches nothing but fixproof.json, and the signed proof passes the policy with the
subject bound to HEAD^. Every test below builds a real temporary git repository and
runs the exact command the generated workflow runs — this file IS the customer-flow
acceptance test the audit required.
"""
from __future__ import annotations

import hashlib
import json
import subprocess

import pytest

from stepstitch_service import _ed25519
from stepstitch_service.cli import build_parser, main
from stepstitch_service.fixproof import (
    build_fixproof_statement,
    sign_statement,
    wrap,
)

SEED = hashlib.sha256(b"proof-gate host key").digest()
PUBLIC = "ed25519:" + _ed25519.public_key(SEED).hex()
STRANGER_SEED = hashlib.sha256(b"proof-gate stranger key").digest()

POLICY = {
    "require_grade": "measured",
    "require_pre_red": True,
    "require_post_green": True,
    "require_signature": True,
    "trusted_keys": {"host": PUBLIC},
    "require_bindings": True,
    "allowed_verifier_kinds": ["measured-by-host"],
    "allowed_verifier_identities": ["admin"],
    "require_privacy": {},
    "expected_head_sha": None,
}


def _git(repo, *argv) -> str:
    proc = subprocess.run(
        ["git", "-C", str(repo), "-c", "user.name=gate-test",
         "-c", "user.email=gate-test@example.test", "-c", "commit.gpgsign=false",
         *argv],
        capture_output=True, text=True, timeout=60, check=True,
    )
    return proc.stdout.strip()


@pytest.fixture()
def repo(tmp_path):
    """A real repository holding commit A — the tested code."""
    path = tmp_path / "customer-repo"
    path.mkdir()
    _git(path, "init", "-q")
    (path / "app.py").write_text("def handler():\n    return 'fixed'\n",
                                 encoding="utf-8")
    _git(path, "add", "app.py")
    _git(path, "commit", "-q", "-m", "the fix (commit A)")
    return path


def _code_commit(repo) -> str:
    return _git(repo, "rev-parse", "HEAD")


def _proof_for(commit_sha, *, seed=SEED, key_id="host", identity="admin"):
    statement = build_fixproof_statement(
        trace_id="trc_gate_1",
        subject_name="customer/app",
        fixed_commit=commit_sha,
        base_commit="a" * 40,
        fingerprint={"route": "/x", "exception_type": "TypeError"},
        red_signature="TypeError: boom",
        red_verdict="reproduced",
        frozen_test_sha256="c" * 64,
        frozen_at="2026-08-09T12:00:00+00:00",
        frozen_by="admin",
        envelope_sha256="d" * 64,
        envelope_schema_version=3,
        pre_passed=False,
        post_passed=True,
        verdict="confirmed_fixed",
        fix_ref="PR#7",
        fix_mechanism=None,
        policy="financial-services-strict",
        policy_sha256="sha256:" + "e" * 64,
        scrub_status="clean",
        schema_status="strict_schema_passed",
        verifier_identity=identity,
        evidence_grade="measured",
        issued_at="2026-08-09T12:00:00+00:00",
        sdk_build=None,
    )
    return wrap(statement, sign_statement(statement, seed=seed, key_id=key_id))


def _commit_proof(repo, document, message="fixproof for HEAD^ (commit B)") -> str:
    (repo / "fixproof.json").write_text(json.dumps(document, indent=2),
                                        encoding="utf-8")
    _git(repo, "add", "fixproof.json")
    _git(repo, "commit", "-q", "-m", message)
    return _git(repo, "rev-parse", "HEAD")


def _policy_file(tmp_path, policy=None) -> str:
    path = tmp_path / "proof-policy.json"
    path.write_text(json.dumps(policy or POLICY), encoding="utf-8")
    return str(path)


def _gate(repo, head, policy_path) -> int:
    return main(["proof", "gate", head, "--policy", policy_path,
                 "--repo", str(repo)])


# --- the protocol works: the documented customer flow is executable ----------------------


def test_the_documented_flow_succeeds_end_to_end(repo, tmp_path, capsys):
    """Commit A (code) -> signed proof naming A -> commit B (proof only) -> gate
    accepts B. The loop the audit proved impossible is now a straight line."""
    code = _code_commit(repo)
    head = _commit_proof(repo, _proof_for(code))
    assert head != code
    assert _gate(repo, head, _policy_file(tmp_path)) == 0
    out = capsys.readouterr().out
    assert "proof verified" in out


def test_the_gate_names_the_protocol_in_its_output(repo, tmp_path, capsys):
    code = _code_commit(repo)
    head = _commit_proof(repo, _proof_for(code))
    _gate(repo, head, _policy_file(tmp_path))
    out = capsys.readouterr().out
    assert code[:12] in out  # the tested code commit is named, so a reviewer can look


# --- the audit's required refusals -------------------------------------------------------


def test_code_committed_after_the_proof_is_refused(repo, tmp_path, capsys):
    """The proof must be the LAST word: any code on top of it is untested code riding
    a stale proof."""
    code = _code_commit(repo)
    _commit_proof(repo, _proof_for(code))
    (repo / "app.py").write_text("def handler():\n    return 'sneaky change'\n",
                                 encoding="utf-8")
    _git(repo, "add", "app.py")
    _git(repo, "commit", "-q", "-m", "code after the proof")
    head = _git(repo, "rev-parse", "HEAD")
    assert _gate(repo, head, _policy_file(tmp_path)) == 1
    assert "only fixproof.json" in capsys.readouterr().out


def test_an_extra_file_in_the_proof_commit_is_refused(repo, tmp_path, capsys):
    code = _code_commit(repo)
    (repo / "fixproof.json").write_text(json.dumps(_proof_for(code)),
                                        encoding="utf-8")
    (repo / "helper.py").write_text("# smuggled\n", encoding="utf-8")
    _git(repo, "add", "fixproof.json", "helper.py")
    _git(repo, "commit", "-q", "-m", "proof plus a stowaway")
    head = _git(repo, "rev-parse", "HEAD")
    assert _gate(repo, head, _policy_file(tmp_path)) == 1
    assert "helper.py" in capsys.readouterr().out


def test_a_proof_naming_the_head_instead_of_the_parent_is_refused(repo, tmp_path):
    """The old impossible loop, now an attack: a proof claiming to be about the
    commit that CONTAINS it cannot be about tested code."""
    code = _code_commit(repo)
    # Predict nothing: build the proof-only commit first, then re-point the proof at
    # that head and amend — the classic self-referential shape.
    head = _commit_proof(repo, _proof_for(code))
    (repo / "fixproof.json").write_text(json.dumps(_proof_for(head)),
                                        encoding="utf-8")
    _git(repo, "add", "fixproof.json")
    _git(repo, "commit", "-q", "--amend", "--no-edit")
    amended = _git(repo, "rev-parse", "HEAD")
    assert _gate(repo, amended, _policy_file(tmp_path)) == 1


def test_a_merge_commit_head_is_refused(repo, tmp_path, capsys):
    code = _code_commit(repo)
    _git(repo, "checkout", "-q", "-b", "side")
    _commit_proof(repo, _proof_for(code))
    _git(repo, "checkout", "-q", "-")
    (repo / "other.py").write_text("x = 1\n", encoding="utf-8")
    _git(repo, "add", "other.py")
    _git(repo, "commit", "-q", "-m", "mainline moved")
    _git(repo, "merge", "-q", "--no-ff", "--no-edit", "side")
    head = _git(repo, "rev-parse", "HEAD")
    assert _gate(repo, head, _policy_file(tmp_path)) == 1
    assert "exactly one parent" in capsys.readouterr().out


def test_an_untrusted_signer_is_refused_by_the_gate(repo, tmp_path):
    code = _code_commit(repo)
    head = _commit_proof(repo, _proof_for(code, seed=STRANGER_SEED))
    assert _gate(repo, head, _policy_file(tmp_path)) == 1


def test_a_head_without_a_proof_file_is_refused(repo, tmp_path, capsys):
    (repo / "notes.md").write_text("no proof here\n", encoding="utf-8")
    _git(repo, "add", "notes.md")
    _git(repo, "commit", "-q", "-m", "just code")
    head = _git(repo, "rev-parse", "HEAD")
    assert _gate(repo, head, _policy_file(tmp_path)) == 1


def test_invalid_proof_json_in_the_commit_is_refused(repo, tmp_path):
    (repo / "fixproof.json").write_text("{not json", encoding="utf-8")
    _git(repo, "add", "fixproof.json")
    _git(repo, "commit", "-q", "-m", "corrupt proof")
    head = _git(repo, "rev-parse", "HEAD")
    assert _gate(repo, head, _policy_file(tmp_path)) == 1


# --- unusable inputs stay exit 2 ---------------------------------------------------------


def test_an_unresolvable_head_is_unusable_input(repo, tmp_path):
    assert _gate(repo, "f" * 40, _policy_file(tmp_path)) == 2


def test_a_directory_that_is_not_a_repo_is_unusable_input(tmp_path):
    empty = tmp_path / "not-a-repo"
    empty.mkdir()
    assert _gate(empty, "f" * 40, _policy_file(tmp_path)) == 2


def test_an_unconfigured_policy_is_unusable_through_the_gate(repo, tmp_path):
    code = _code_commit(repo)
    head = _commit_proof(repo, _proof_for(code))
    broken = dict(POLICY, trusted_keys={"host": "ed25519:REPLACE_ME"})
    assert _gate(repo, head, _policy_file(tmp_path, broken)) == 2


def test_the_gate_command_parses_under_the_cli():
    parser = build_parser()
    parser.parse_args(["proof", "gate", "a" * 40, "--policy", "proof-policy.json"])
    parser.parse_args(["proof", "gate", "a" * 40, "--policy", "p.json",
                       "--repo", "."])
