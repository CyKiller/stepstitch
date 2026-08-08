"""PCI account-data defense-in-depth: Luhn labeling + the advisory-detector seam.

The privacy boundary for CHD/SAD is the strict schema (proven by the fixture
pack in test_policy_verify.py — every PCI-shaped vector is refused with nothing
stored). This file pins the two supporting layers:

  1. Luhn is labeling precision, never a coverage decision — an invalid checksum
     reclassifies card -> number, and every 13-19 digit run stays redacted.
  2. Advisory detectors are host-injected code (never config), can only ADD
     redaction, are labeled advisory, and a broken one cannot break ingestion.

Also stated honestly: a bare 3-4 digit CVV in free text is NOT detected by any
regex here — which is exactly why the claim rests on schema refusal, not on
detection.
"""
import pytest

from stepstitch_service.scrubber import (
    clear_advisory_detectors,
    luhn_valid,
    redact_text,
    register_advisory_detector,
)


@pytest.fixture(autouse=True)
def _clean_registry():
    clear_advisory_detectors()
    yield
    clear_advisory_detectors()


# --- Luhn labeling ---------------------------------------------------------------


def test_luhn_valid_pan_is_labeled_card():
    out, kinds = redact_text("card 4111 1111 1111 1111 declined")
    assert "[redacted:card]" in out
    assert "4111" not in out
    assert "card" in kinds


def test_invalid_checksum_is_still_redacted_as_number():
    out, kinds = redact_text("card 4111 1111 1111 1112 declined")
    assert "4111" not in out, "an invalid checksum must never reduce redaction"
    assert "[redacted:number]" in out
    assert "card" not in kinds
    assert "number" in kinds


def test_every_13_to_19_digit_run_is_redacted_regardless_of_checksum():
    for run in ("5500 0000 0000 0004",      # Luhn-valid test number
                "1234567890123",            # 13 digits, invalid
                "999999999999999999"):      # 18 digits, invalid
        out, _ = redact_text(f"value {run} observed")
        digits = run.replace(" ", "")
        assert digits[:4] not in out and run not in out


def test_luhn_function_is_pinned():
    assert luhn_valid("4111111111111111")
    assert not luhn_valid("4111111111111112")
    assert not luhn_valid("123")            # too short to be a PAN
    assert not luhn_valid("not-digits")


def test_bare_cvv_is_not_detected_and_that_is_the_documented_boundary():
    """3-4 digits match no pattern — the honest limit of regex detection. The
    product's CHD/SAD claim therefore rests on strict-schema refusal (see the
    fixture pack), never on this scrubber finding a CVV."""
    out, kinds = redact_text("CVV 123")
    assert "123" in out
    assert kinds == []


# --- Advisory detectors ----------------------------------------------------------


def test_advisory_detector_adds_redaction_with_advisory_label():
    register_advisory_detector("fake-ner", lambda text: ["Jane Synthetic"])
    out, kinds = redact_text("customer Jane Synthetic reported the failure")
    assert "Jane Synthetic" not in out
    assert "[redacted:advisory:fake-ner]" in out
    assert "advisory:fake-ner" in kinds


def test_without_detectors_nothing_changes():
    out, kinds = redact_text("customer Jane Synthetic reported the failure")
    assert out == "customer Jane Synthetic reported the failure"
    assert kinds == []


def test_a_broken_detector_never_breaks_ingestion():
    def explodes(text):
        raise RuntimeError("model server down")

    register_advisory_detector("flaky", explodes)
    out, kinds = redact_text("SSN 000-00-0000 in text")
    # The built-in passes still ran; the broken detector was simply skipped.
    assert "[redacted:ssn]" in out
    assert kinds == ["ssn"]


def test_detectors_run_after_the_regex_passes_and_cannot_unredact():
    """A detector sees already-scrubbed text, so it can only add redaction — it
    is structurally incapable of restoring something the regexes removed."""
    seen = {}

    def spy(text):
        seen["text"] = text
        return []

    register_advisory_detector("spy", spy)
    redact_text("SSN 000-00-0000 and Jane")
    assert "[redacted:ssn]" in seen["text"]
    assert "000-00-0000" not in seen["text"]
