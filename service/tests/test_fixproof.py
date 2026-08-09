"""FixProof v2: the proof core, adversarially.

The statement is only worth shipping if every protected field is provably bound: alter
any leaf and offline verification must refuse. These tests enumerate the mutation surface
FROM THE STATEMENT ITSELF (``_leaf_paths``) so a field added later is covered by
construction — a guard that samples fields rots the day the statement grows.
"""
from __future__ import annotations

import json

import pytest

from stepstitch_service.evidence import TamperError
from stepstitch_service.fixproof import (
    PREDICATE_TYPE,
    SCHEMA,
    STATEMENT_TYPE,
    build_fixproof_statement,
    statement_sha256,
    verify_fixproof,
    wrap,
)

FIXED = "b" * 40
BASE = "a" * 40


def _statement(**overrides):
    params = dict(
        trace_id="trc_test_1",
        subject_name="acme/payments-portal",
        fixed_commit=FIXED,
        base_commit=BASE,
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
        verifier_identity="agent:ci-verifier",
        evidence_grade="measured",
        issued_at="2026-08-08T12:34:56+00:00",
        sdk_build="abc123",
    )
    params.update(overrides)
    return build_fixproof_statement(**params)


def _document(**overrides):
    return wrap(_statement(**overrides))


BASE_POLICY = {
    "require_grade": "measured",
    "require_pre_red": True,
    "require_post_green": True,
    "require_signature": False,
    "allowed_verifier_kinds": ["measured-by-host"],
    "require_privacy": {"schema_status": "strict_schema_passed"},
    "expected_head_sha": None,
}


def _verify(doc, policy=None, head_sha=None):
    return verify_fixproof(doc, policy if policy is not None else dict(BASE_POLICY),
                           head_sha=head_sha)


# --- shape: the statement is the interoperable in-toto unit -------------------------------


def test_the_statement_is_an_in_toto_statement():
    s = _statement()
    assert s["_type"] == STATEMENT_TYPE == "https://in-toto.io/Statement/v1"
    assert s["predicateType"] == PREDICATE_TYPE
    assert s["subject"] == [
        {"name": "acme/payments-portal", "digest": {"gitCommit": FIXED}}
    ]


def test_the_wrapper_carries_schema_hash_and_signature_slot():
    doc = _document()
    assert doc["schema"] == SCHEMA == "stepstitch.fixproof/v2"
    assert doc["statement_sha256"] == statement_sha256(doc["statement"])
    assert doc["statement_sha256"].startswith("sha256:")
    assert doc["signature"] is None


def test_a_proof_without_a_fixed_commit_cannot_be_built():
    """No subject, no proof — a proof about unidentified code proves nothing."""
    for bad in (None, "", "main", "abc123", "B" * 39):
        with pytest.raises(ValueError):
            _statement(fixed_commit=bad)


def test_the_ten_bindings_are_all_present():
    """The floor: the DoD's ten proof components, named. If a refactor drops one, this
    fails before any mutation test has to."""
    s = _statement()
    p = s["predicate"]
    assert s["subject"][0]["digest"]["gitCommit"]          # fixed commit
    assert p["base_commit"] == {"gitCommit": BASE}          # base commit
    assert p["failure"]["fingerprint"]                      # failure fingerprint
    assert p["failure"]["red_signature"]
    assert p["frozen_test"]["sha256"].startswith("sha256:")  # frozen-test digest
    assert p["execution_envelope"]["sha256"].startswith("sha256:")  # envelope digest
    assert p["results"]["pre_passed"] is False              # explicit pre/post
    assert p["results"]["post_passed"] is True
    assert p["privacy"]["policy_sha256"].startswith("sha256:")  # privacy-policy digest
    assert p["privacy"]["structural_result"]                # structural privacy result
    assert p["verifier"]["identity"]                        # verifier identity
    assert p["verifier"]["kind"] == "measured-by-host"
    # signature is the wrapper's slot, exercised in the signature tests below.


def test_bare_hex_digests_are_normalized_to_prefixed_form():
    """The rows store bare hex (historical); the proof re-emits prefixed. Feeding bare
    hex must not produce a double prefix or an unprefixed digest."""
    s = _statement()
    assert s["predicate"]["frozen_test"]["sha256"] == "sha256:" + "c" * 64
    assert s["predicate"]["execution_envelope"]["sha256"] == "sha256:" + "d" * 64
    assert s["predicate"]["privacy"]["policy_sha256"] == "sha256:" + "e" * 64


# --- the mutation surface, enumerated from the statement itself ---------------------------


def _leaf_paths(obj, prefix=()):
    """Every (path, value) leaf in a nested dict/list structure."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield from _leaf_paths(v, prefix + (k,))
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            yield from _leaf_paths(v, prefix + (i,))
    else:
        yield prefix, obj


def _set_path(obj, path, value):
    node = obj
    for key in path[:-1]:
        node = node[key]
    node[path[-1]] = value


def _del_path(obj, path):
    node = obj
    for key in path[:-1]:
        node = node[key]
    del node[path[-1]]


def _mutated(value):
    if isinstance(value, bool):
        return not value
    if isinstance(value, (int, float)):
        return value + 1
    if isinstance(value, str):
        return value + "-tampered"
    if value is None:
        return "tampered"
    return "tampered"


ALL_LEAVES = sorted(
    (path for path, _ in _leaf_paths(_statement())), key=lambda p: tuple(map(str, p))
)


def test_the_enumerated_surface_covers_the_named_bindings():
    """If the walker or the statement shrinks, the mutation matrix silently shrinks with
    it — this floor makes that loud."""
    joined = {".".join(map(str, p)) for p in ALL_LEAVES}
    for needle in (
        "subject.0.digest.gitCommit",
        "predicate.base_commit.gitCommit",
        "predicate.failure.red_signature",
        "predicate.frozen_test.sha256",
        "predicate.execution_envelope.sha256",
        "predicate.results.pre_passed",
        "predicate.results.post_passed",
        "predicate.privacy.policy_sha256",
        "predicate.privacy.structural_result",
        "predicate.verifier.identity",
        "predicate.verifier.kind",
        "predicate.verifier.evidence_grade",
    ):
        assert needle in joined, f"binding {needle} missing from the mutation surface"
    assert len(ALL_LEAVES) >= 25


@pytest.mark.parametrize("path", ALL_LEAVES, ids=[".".join(map(str, p)) for p in ALL_LEAVES])
def test_altering_any_leaf_is_refused(path):
    doc = _document()
    _set_path(doc["statement"], path, _mutated(_get(doc["statement"], path)))
    with pytest.raises(TamperError):
        _verify(doc)


@pytest.mark.parametrize("path", ALL_LEAVES, ids=[".".join(map(str, p)) for p in ALL_LEAVES])
def test_deleting_any_leaf_is_refused(path):
    doc = _document()
    _del_path(doc["statement"], path)
    with pytest.raises(TamperError):
        _verify(doc)


def _get(obj, path):
    node = obj
    for key in path:
        node = node[key]
    return node


def test_inserting_an_extra_claim_is_refused():
    doc = _document()
    doc["statement"]["predicate"]["universally_correct"] = True
    with pytest.raises(TamperError):
        _verify(doc)


def test_a_missing_hash_is_refused_not_recomputed():
    doc = _document()
    del doc["statement_sha256"]
    with pytest.raises(TamperError):
        _verify(doc)


def test_reserialization_is_not_tampering():
    doc = json.loads(json.dumps(_document()))
    assert _verify(doc).ok


def test_a_bare_hex_statement_hash_still_verifies():
    """Prefix tolerance, the same as evidence.verify_bundle: a correct hash written
    without the sha256: prefix is correct, not tampered."""
    doc = _document()
    doc["statement_sha256"] = doc["statement_sha256"].removeprefix("sha256:")
    assert _verify(doc).ok


# --- policy checks ------------------------------------------------------------------------


def test_the_shipped_policy_passes_a_measured_proof():
    result = _verify(_document())
    assert result.ok
    assert all(c["passed"] for c in result.checks)


def test_an_asserted_proof_fails_a_measured_floor():
    doc = wrap(_statement(evidence_grade="asserted"))
    result = _verify(doc)
    assert not result.ok
    failed = {c["check"] for c in result.checks if not c["passed"]}
    assert "require_grade" in failed


def test_a_head_sha_mismatch_fails():
    result = _verify(_document(), head_sha="f" * 40)
    assert not result.ok
    assert any(c["check"] == "expected_head_sha" and not c["passed"]
               for c in result.checks)


def test_a_matching_head_sha_passes_case_insensitively():
    assert _verify(_document(), head_sha=FIXED.upper()).ok


def _signature_policy():
    """require_signature with a real trust anchor — the only shape it works in now."""
    import hashlib

    from stepstitch_service import _ed25519

    seed = hashlib.sha256(b"test_fixproof signature key").digest()
    policy = dict(BASE_POLICY, require_signature=True,
                  trusted_keys={"test-host":
                                "ed25519:" + _ed25519.public_key(seed).hex()})
    return seed, policy


def test_missing_signature_fails_only_when_required():
    doc = _document()
    assert _verify(doc).ok
    _, policy = _signature_policy()
    result = _verify(doc, policy)
    assert not result.ok
    assert any(c["check"] == "require_signature" and not c["passed"]
               for c in result.checks)


def test_a_signed_proof_passes_the_signature_requirement():
    """Signed means CRYPTOGRAPHICALLY signed by a policy-trusted key. The fake string
    this test used to accept is the trust-audit exploit; it must fail now, and the
    full attack matrix lives in test_fixproof_adversarial.py."""
    from stepstitch_service.fixproof import sign_statement

    seed, policy = _signature_policy()
    statement = _statement()
    signed = wrap(statement, sign_statement(statement, seed=seed, key_id="test-host"))
    assert _verify(signed, policy).ok

    faked = wrap(statement, "MEUCIQfakebase64signature==")
    result = _verify(faked, policy)
    assert not result.ok
    assert any(c["check"] == "require_signature" and not c["passed"]
               for c in result.checks)


def test_an_unlisted_verifier_kind_fails():
    doc = wrap(_statement(evidence_grade="asserted"))
    policy = dict(BASE_POLICY, require_grade="asserted")
    result = _verify(doc, policy)
    assert not result.ok
    assert any(c["check"] == "allowed_verifier_kinds" and not c["passed"]
               for c in result.checks)


def test_pre_red_and_post_green_are_required_individually():
    never_red = wrap(_statement(pre_passed=True, verdict="not_fixed"))
    result = _verify(never_red)
    assert not result.ok
    assert any(c["check"] == "require_pre_red" and not c["passed"]
               for c in result.checks)

    never_green = wrap(_statement(post_passed=False, verdict="not_fixed"))
    result = _verify(never_green)
    assert not result.ok
    assert any(c["check"] == "require_post_green" and not c["passed"]
               for c in result.checks)


def test_a_privacy_requirement_mismatch_fails():
    doc = wrap(_statement(schema_status=None))
    result = _verify(doc)
    assert not result.ok
    assert any(c["check"] == "require_privacy" and not c["passed"]
               for c in result.checks)


def test_an_unknown_policy_key_is_refused_as_unusable():
    """A typo'd policy must not silently verify nothing — refuse the file outright."""
    with pytest.raises(ValueError, match="unknown policy key"):
        _verify(_document(), dict(BASE_POLICY, require_grde="measured"))


def test_an_underscore_key_is_commentary_not_a_typo():
    """JSON has no comments; the shipped policy documents itself via `_comment`."""
    assert _verify(_document(), dict(BASE_POLICY, _comment="explains the policy")).ok


# --- no raw customer values ---------------------------------------------------------------

CANARIES = ("4111 1111 1111 1234", "250.00", "dana.holt@example.test",
            "FAKE-QUERY-SECRET-123", "8842")


def _hostile_trace_proof():
    """Build a proof from evidence that passed through the REAL scrub boundary after a
    hostile ingest — the proof may carry digests and statuses, never the values."""
    from stepstitch_service.scrubber import (
        scrub_trace_payload,
    )

    hostile = {
        "explanation": ("Card 4111 1111 1111 1234 charged 250.00, "
                        "email dana.holt@example.test token FAKE-QUERY-SECRET-123 acct 8842"),
        "footsteps": [{"timestamp": "t", "type": "navigation",
                       "route": "/transfer?card=4111 1111 1111 1234",
                       "target": "#send", "label": "Card 4111 1111 1111 1234",
                       "metadata": {"status": 500}}],
        "metadata": {"sdk_version": "0.2.0"},
    }
    _, report = scrub_trace_payload(hostile)
    return wrap(_statement(
        policy=report["policy"],
        policy_sha256=report["policy_sha256"],
        scrub_status=report["scrub_status"],
        schema_status=report.get("schema_status"),
    ))


def test_the_proof_carries_no_raw_customer_values():
    blob = json.dumps(_hostile_trace_proof())
    for canary in CANARIES:
        assert canary not in blob, f"proof leaked {canary!r}"


def test_the_leak_scan_itself_is_awake():
    """Scanner self-test (the copy-claims pattern): plant a canary, the scan must bite."""
    doc = _hostile_trace_proof()
    doc["statement"]["predicate"]["results"]["fix_ref"] = CANARIES[0]
    blob = json.dumps(doc)
    assert any(c in blob for c in CANARIES), "planted canary not even present"
