"""Evidence Attestation — canonical bundle + tamper-evident hash (attestation.py)."""
from stepstitch_service.attestation import (
    SCHEMA,
    build_attestation,
    bundle_sha256,
    canonical_bytes,
)


def _bundle():
    return build_attestation(
        "trc-1",
        summary={"route": "/accounts/:id/transfer", "headline": "HTTP 500",
                 "diagnostic_type": "api_error", "failing_status": 500,
                 "exception_type": None, "diagnostic_endpoint": "/api/x", "step_count": 6},
        replayability={"score": 0.76, "grade": "B", "warnings": ["..."]},
        scrub={"policy": "financial-services-enterprise", "scrub_status": "scrubbed",
               "scrubbed_fields": ["explanation"]},
        never_captured=["screenshots", "input values"],
        sdk_build="5c2ea11",
        latest_verification={"verdict": "confirmed_fixed", "fix_ref": "PR#42",
                             "run_url": "https://ci/9"},
    )


def test_bundle_composes_expected_fields():
    b = _bundle()
    assert b["schema"] == SCHEMA and b["trace_id"] == "trc-1" and b["sdk_build"] == "5c2ea11"
    assert b["replayability"] == {"score": 0.76, "grade": "B"}  # warnings dropped
    assert b["privacy"]["scrubbed_fields"] == ["explanation"]
    assert b["verification"]["verdict"] == "confirmed_fixed"


def test_canonical_bytes_are_deterministic_regardless_of_key_order():
    b1 = _bundle()
    b2 = dict(reversed(list(_bundle().items())))  # same content, different insertion order
    assert canonical_bytes(b1) == canonical_bytes(b2)
    assert bundle_sha256(b1) == bundle_sha256(b2)


def test_hash_is_tamper_evident():
    b = _bundle()
    h = bundle_sha256(b)
    b["verification"]["verdict"] = "not_fixed"  # flip one field
    assert bundle_sha256(b) != h


def test_bundle_is_structural_only_no_raw_data():
    # Only sanitized reads go in; a raw id/secret never appears.
    b = _bundle()
    blob = canonical_bytes(b).decode()
    for raw in ("8675309", "ssn", "password", "Bearer "):
        assert raw not in blob
