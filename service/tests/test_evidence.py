"""Evidence grades and tamper rejection.

The grade answers "how do we know", so the tests are mostly about what cannot be claimed
and what cannot be quietly altered.
"""
import pytest
from stepstitch_service.evidence import (
    ASSERTED,
    MEASURED,
    SIGNED,
    TamperError,
    bundle_hash,
    canonical_bytes,
    derive_grade,
    grade_at_least,
    verify_bundle,
)

BUNDLE = {
    "trace_id": "t-1",
    "verdict": "confirmed_fixed",
    "evidence_grade": MEASURED,
    "scrub": {"redacted": ["email"], "policy": "financial-services-enterprise"},
    "replayability": {"score": 1.0, "grade": "A"},
}


def _document(bundle=None, signature=None):
    body = dict(bundle or BUNDLE)
    doc = dict(body, bundle_sha256=bundle_hash(body))
    if signature:
        doc["signature"] = signature
    return doc


# --- the ladder -------------------------------------------------------------------------

def test_an_outcome_stepstitch_did_not_observe_is_only_asserted():
    assert derive_grade(measured_by_stepstitch=False) == ASSERTED


def test_stepstitch_running_it_earns_measured():
    assert derive_grade(measured_by_stepstitch=True) == MEASURED


def test_signing_a_measurement_earns_signed():
    assert derive_grade(measured_by_stepstitch=True, signature="sig") == SIGNED


def test_signing_something_nobody_measured_is_still_only_asserted():
    """A signed assertion is a signed rumour — the signature attests to authorship, not
    to the fix having been observed."""
    assert derive_grade(measured_by_stepstitch=False, signature="sig") == ASSERTED


def test_the_ladder_orders_correctly():
    assert grade_at_least(SIGNED, MEASURED)
    assert grade_at_least(MEASURED, MEASURED)
    assert not grade_at_least(ASSERTED, MEASURED)
    # An unknown or missing grade is the weakest thing there is, never a pass.
    assert not grade_at_least(None, MEASURED)
    assert not grade_at_least("platinum", MEASURED)


# --- canonicalisation -------------------------------------------------------------------

def test_key_order_and_whitespace_do_not_change_the_hash():
    """Attestations round-trip through many hands; re-serialisation must not look like
    tampering, or the check would cry wolf and get ignored."""
    reordered = dict(reversed(list(BUNDLE.items())))
    assert bundle_hash(reordered) == bundle_hash(BUNDLE)
    assert b" " not in canonical_bytes(BUNDLE)


def test_any_content_change_moves_the_hash():
    altered = dict(BUNDLE, verdict="still_failing")
    assert bundle_hash(altered) != bundle_hash(BUNDLE)


# --- tamper rejection -------------------------------------------------------------------

def test_an_untouched_bundle_verifies():
    result = verify_bundle(_document())
    assert result["verified"] is True
    assert result["evidence_grade"] == MEASURED


def test_a_flipped_verdict_is_refused():
    doc = _document()
    doc["verdict"] = "confirmed_fixed" if doc["verdict"] != "confirmed_fixed" else "broken"
    with pytest.raises(TamperError, match="does not match its own hash"):
        verify_bundle(doc)


def test_an_upgraded_grade_is_refused():
    """The most tempting edit: quietly promote asserted evidence to signed."""
    doc = _document()
    doc["evidence_grade"] = SIGNED
    with pytest.raises(TamperError):
        verify_bundle(doc)


def test_a_removed_redaction_is_refused():
    doc = _document()
    doc["scrub"] = {"redacted": [], "policy": "financial-services-enterprise"}
    with pytest.raises(TamperError):
        verify_bundle(doc)


def test_a_bundle_with_no_hash_cannot_be_trusted():
    with pytest.raises(TamperError, match="carries no bundle_sha256"):
        verify_bundle({"trace_id": "t-1", "verdict": "confirmed_fixed"})


def test_a_signature_is_reported_but_is_not_what_makes_it_verifiable():
    """The hash is tamper-evidence on its own; the signature adds attributable authorship.
    Both are reported separately so a reader can tell which assurance they actually have."""
    assert verify_bundle(_document())["signed"] is False
    assert verify_bundle(_document(signature="MEUCIQ..."))["signed"] is True


def test_reserialising_a_verified_document_still_verifies():
    import json

    doc = json.loads(json.dumps(_document(signature="sig")))
    assert verify_bundle(doc)["verified"] is True
