"""The six attacks from the FixProof trust audit, as permanent acceptance tests.

The audit's finding, kept verbatim so the point survives refactors: *the hash detects
changes made after a document was created — it does not establish who created the
document.* A verifier that only checks internal consistency certifies forgeries. Each
test below is one of the audit's named attacks run against the HARDENED merge-gate
policy; every one of them must be refused, and refusing them is the product claim
("no trust in the PR author"), not an implementation detail.

The trust chain these tests pin: policy names public keys it trusts → the signature is
cryptographically verified (Ed25519 over the canonical statement bytes) against exactly
those keys → therefore every self-declared field inside the statement (grade, results,
verifier identity) is only as good as the key that vouched for it — which is the policy
holder's own host key, never the PR author.
"""
from __future__ import annotations

import hashlib
import json

import pytest

from stepstitch_service import _ed25519
from stepstitch_service.fixproof import (
    MANDATORY_BINDINGS,
    build_fixproof_statement,
    sign_statement,
    statement_sha256,
    verify_fixproof,
    wrap,
)

FIXED = "b" * 40
OTHER_COMMIT = "f" * 40

# Deterministic test keys: the "tenant host" key the policy trusts, and the attacker's
# own key (a real Ed25519 key — the attack is not a malformed signature, it is a VALID
# signature by the wrong signer).
TRUSTED_SEED = hashlib.sha256(b"stepstitch adversarial-suite trusted host key").digest()
TRUSTED_PUB = "ed25519:" + _ed25519.public_key(TRUSTED_SEED).hex()
ATTACKER_SEED = hashlib.sha256(b"stepstitch adversarial-suite attacker key").digest()

HARDENED_POLICY = {
    "require_grade": "measured",
    "require_pre_red": True,
    "require_post_green": True,
    "require_signature": True,
    "trusted_keys": {"tenant-host": TRUSTED_PUB},
    "require_bindings": True,
    "allowed_verifier_kinds": ["measured-by-host"],
    "allowed_verifier_identities": ["admin"],
    "require_privacy": {},
    "expected_head_sha": None,
}


def _statement(**overrides):
    params = dict(
        trace_id="trc_adversarial_1",
        subject_name="acme/payments-portal",
        fixed_commit=FIXED,
        base_commit="a" * 40,
        fingerprint={"route": "/transfer", "exception_type": "TypeError"},
        red_signature="Error: no server error from /api/accounts/:id/transfer",
        red_verdict="reproduced",
        frozen_test_sha256="c" * 64,
        frozen_at="2026-08-08T12:00:00+00:00",
        frozen_by="admin",
        envelope_sha256="d" * 64,
        envelope_schema_version=3,
        pre_passed=False,
        post_passed=True,
        verdict="confirmed_fixed",
        fix_ref="PR#42",
        fix_mechanism=None,
        policy="financial-services-strict",
        policy_sha256="sha256:" + "e" * 64,
        scrub_status="clean",
        schema_status="strict_schema_passed",
        verifier_identity="admin",
        evidence_grade="measured",
        issued_at="2026-08-08T12:34:56+00:00",
        sdk_build="abc123",
    )
    params.update(overrides)
    return build_fixproof_statement(**params)


def _signed_document(statement=None, seed=TRUSTED_SEED, key_id="tenant-host"):
    statement = statement if statement is not None else _statement()
    return wrap(statement, sign_statement(statement, seed=seed, key_id=key_id))


def _failed(outcome, check):
    return [c for c in outcome.checks if c["check"] == check and not c["passed"]]


def test_the_honestly_signed_baseline_passes_the_hardened_policy():
    """The control: a host-measured, host-signed proof with every binding satisfies the
    full hardened policy — the attacks below fail because they are attacks, not because
    the policy is unsatisfiable."""
    outcome = verify_fixproof(_signed_document(), HARDENED_POLICY, head_sha=FIXED)
    assert outcome.ok, [c for c in outcome.checks if not c["passed"]]


# --- attack 1: fabricate the entire proof and recompute its hash --------------------------


def test_attack_1_a_fabricated_proof_with_a_recomputed_hash_is_refused():
    """The audit's exact exploit: invent every field (self-declared measured grade,
    invented results, invented verifier), recompute statement_sha256 so the document is
    internally consistent, present no signature. Internal consistency must no longer
    be enough."""
    fabricated = {
        "_type": "https://in-toto.io/Statement/v1",
        "subject": [{"name": "victim/app", "digest": {"gitCommit": FIXED}}],
        "predicateType": "https://stepstitch.dev/attestation/fixproof/v2",
        "predicate": {
            "trace_id": "trc_made_up",
            "base_commit": {"gitCommit": "a" * 40},
            "failure": {"fingerprint": {"route": "/x"}, "red_signature": "made up",
                        "red_verdict": "reproduced"},
            "frozen_test": {"sha256": "sha256:" + "1" * 64, "frozen_at": None,
                            "frozen_by": None},
            "execution_envelope": {"sha256": "sha256:" + "2" * 64,
                                   "schema_version": 3},
            "results": {"pre_passed": False, "post_passed": True,
                        "verdict": "confirmed_fixed", "fix_ref": None,
                        "fix_mechanism": None},
            "privacy": {"policy": "financial-services-strict",
                        "policy_sha256": "sha256:" + "3" * 64,
                        "scrub_status": "clean",
                        "schema_status": "strict_schema_passed",
                        "structural_result": "structural_only"},
            "verifier": {"identity": "admin", "kind": "measured-by-host",
                         "evidence_grade": "measured"},
            "issued_at": "2026-08-09T00:00:00+00:00",
            "sdk_build": None,
            "scope": "fabricated",
        },
    }
    document = {
        "schema": "stepstitch.fixproof/v2",
        "statement": fabricated,
        "statement_sha256": statement_sha256(fabricated),  # attacker CAN do this
        "signature": None,
    }
    outcome = verify_fixproof(document, HARDENED_POLICY, head_sha=FIXED)
    assert not outcome.ok
    assert _failed(outcome, "require_signature"), (
        "a fabricated-but-internally-consistent document passed the signature "
        "requirement — the audit's exploit is back"
    )


def test_attack_1b_the_fabricator_signing_with_their_own_key_is_refused():
    """A fabricator can make a REAL Ed25519 signature — with a key the policy never
    trusted. The check is 'signed by whom', not 'signed at all'."""
    doc = _signed_document(seed=ATTACKER_SEED, key_id="tenant-host")
    outcome = verify_fixproof(doc, HARDENED_POLICY, head_sha=FIXED)
    assert not outcome.ok
    assert _failed(outcome, "require_signature")


# --- attack 2: a fake signature string ----------------------------------------------------


def test_attack_2_a_nonempty_signature_string_is_refused():
    """The v2 gap: `require_signature` accepted any truthy value. An opaque string
    cannot be cryptographically verified offline, so it must not count as a signature."""
    statement = _statement()
    for fake in ("looks-signed", "MEUCIQDx" + "A" * 60, "ed25519:deadbeef"):
        document = wrap(statement, fake)
        outcome = verify_fixproof(document, HARDENED_POLICY, head_sha=FIXED)
        assert not outcome.ok, f"fake signature string {fake!r} was accepted"
        assert _failed(outcome, "require_signature")


def test_attack_2b_a_forged_signature_object_is_refused():
    """The right shape with invented bytes — structurally perfect, cryptographically
    nothing."""
    statement = _statement()
    document = wrap(statement, {
        "algorithm": "ed25519", "key_id": "tenant-host", "signature": "ab" * 64,
    })
    outcome = verify_fixproof(document, HARDENED_POLICY, head_sha=FIXED)
    assert not outcome.ok
    assert _failed(outcome, "require_signature")


def test_attack_2c_a_trusted_signature_over_a_different_statement_is_refused():
    """Splice a genuine signature (made by the trusted key over statement A) onto
    statement B. The signature must bind THESE canonical bytes."""
    genuine = sign_statement(_statement(), seed=TRUSTED_SEED, key_id="tenant-host")
    other = _statement(trace_id="trc_other")
    document = wrap(other, genuine)
    outcome = verify_fixproof(document, HARDENED_POLICY, head_sha=FIXED)
    assert not outcome.ok
    assert _failed(outcome, "require_signature")


# --- attack 3: remove a mandatory binding -------------------------------------------------


@pytest.mark.parametrize("binding,overrides", [
    ("base_commit", {"base_commit": None}),
    ("failure.fingerprint", {"fingerprint": None}),
    ("failure.red_signature", {"red_signature": ""}),
    ("execution_envelope.sha256", {"envelope_sha256": None}),
    ("privacy.policy_sha256", {"policy_sha256": None}),
])
def test_attack_3_a_proof_missing_a_mandatory_binding_is_refused(binding, overrides):
    """A proof that omits a load-bearing binding — even one honestly signed by the
    trusted key — is not the artifact the gate promised to require."""
    doc = _signed_document(_statement(**overrides))
    outcome = verify_fixproof(doc, HARDENED_POLICY, head_sha=FIXED)
    assert not outcome.ok, f"a proof without {binding} passed require_bindings"
    failed = _failed(outcome, "require_bindings")
    assert failed and binding in failed[0]["detail"]


def test_attack_3b_the_mandatory_binding_list_is_the_named_set():
    """The floor under the parametrization above: the bindings the policy enforces are
    exactly the audit's list, so a refactor cannot quietly shrink it."""
    assert set(MANDATORY_BINDINGS) == {
        "subject.gitCommit",
        "base_commit",
        "failure.fingerprint",
        "failure.red_signature",
        "frozen_test.sha256",
        "execution_envelope.sha256",
        "privacy.policy_sha256",
        "privacy.structural_result",
    }


def test_attack_3c_a_subset_bindings_policy_must_name_real_bindings():
    """The list form exists for the committed demo (whose byte-stable measurement cannot
    carry an environment-dependent envelope digest) — but a typo'd binding name must be
    refused as unusable, never silently skipped."""
    policy = dict(HARDENED_POLICY, require_bindings=["base_commit", "frozen_test_sha"])
    with pytest.raises(ValueError, match="frozen_test_sha"):
        verify_fixproof(_signed_document(), policy, head_sha=FIXED)


# --- attack 4: change the policy inside the PR --------------------------------------------


def test_attack_4_the_gate_loads_its_policy_from_the_protected_base_branch():
    """A PR that weakens proof-policy.json in the same diff must be verifying against
    the BASE branch's policy, not its own. The workflow template is the enforcement
    point: it must read the policy out of the protected base commit and pass THAT file
    to the verifier."""
    from stepstitch_service.github_bridge import STEPSTITCH_FIXPROOF_GATE_WORKFLOW as wf
    assert "github.event.pull_request.base.sha" in wf, (
        "the gate never references the protected base commit"
    )
    assert "git show" in wf and "proof-policy.json" in wf
    # The verifier must be pointed at the base-branch copy, never the checkout's.
    verify_line = next(line for line in wf.splitlines() if "--policy" in line)
    assert "trusted-proof-policy.json" in verify_line, (
        f"the verify command reads the PR's own policy file: {verify_line!r}"
    )


def test_attack_4b_an_unknown_policy_key_is_refused_not_skipped():
    policy = dict(HARDENED_POLICY, require_signatures=True)  # plausible typo
    with pytest.raises(ValueError, match="require_signatures"):
        verify_fixproof(_signed_document(), policy, head_sha=FIXED)


# --- attack 5: reuse a valid proof for another commit -------------------------------------


def test_attack_5_a_genuine_proof_replayed_against_another_commit_is_refused():
    """The proof is real, trusted-signed, complete — for commit A. Presenting it while
    merging commit B must fail on the subject binding."""
    doc = _signed_document()
    outcome = verify_fixproof(doc, HARDENED_POLICY, head_sha=OTHER_COMMIT)
    assert not outcome.ok
    assert _failed(outcome, "expected_head_sha")


# --- attack 6: an unauthorized verifier identity ------------------------------------------


def test_attack_6_a_verifier_identity_the_policy_never_authorized_is_refused():
    doc = _signed_document(_statement(verifier_identity="attacker-ci-bot"))
    outcome = verify_fixproof(doc, HARDENED_POLICY, head_sha=FIXED)
    assert not outcome.ok
    assert _failed(outcome, "allowed_verifier_identities")


# --- the policy itself must be un-footgunnable --------------------------------------------


def test_require_signature_without_trusted_keys_is_an_unusable_policy():
    """'Require a signature' with nobody to trust is a check that verifies nothing —
    refuse the policy (exit 2 territory), never evaluate it."""
    for keys in (None, {}, ):
        policy = dict(HARDENED_POLICY)
        policy["trusted_keys"] = keys
        with pytest.raises(ValueError, match="trusted_keys"):
            verify_fixproof(_signed_document(), policy, head_sha=FIXED)


def test_a_placeholder_public_key_is_an_unusable_policy():
    """The shipped customer template carries REPLACE-WITH placeholders on purpose: a
    policy that was never configured must refuse to run, not quietly pass."""
    policy = dict(HARDENED_POLICY,
                  trusted_keys={"my-host": "ed25519:REPLACE_WITH_YOUR_PUBLIC_KEY"})
    with pytest.raises(ValueError, match="not a usable ed25519 public key"):
        verify_fixproof(_signed_document(), policy, head_sha=FIXED)


def test_the_shipped_customer_template_policy_refuses_to_run_unconfigured():
    """examples/proof/proof-policy.json as shipped (placeholder key, nothing filled in)
    must be refused as unusable — the failure mode of forgetting to configure the gate
    is a hard error, never a green check."""
    from pathlib import Path

    policy = json.loads(
        (Path(__file__).resolve().parents[2] / "examples" / "proof" /
         "proof-policy.json").read_text(encoding="utf-8"))
    assert policy["require_signature"] is True
    assert policy["require_bindings"] is True
    with pytest.raises(ValueError):
        verify_fixproof(_signed_document(), policy, head_sha=FIXED)
