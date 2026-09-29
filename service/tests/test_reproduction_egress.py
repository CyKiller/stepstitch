"""Reproduction-side evidence goes through the same detection engine as ingest.

Before this file, three reproduction paths each had their own, weaker redaction:
``_diagnostics_redactor`` walked the ingest PII regexes by hand (so advisory detectors and
every new secret shape skipped it), dict keys were never scrubbed, and the ``red_signature``
a summaries-tier agent reads through FixProof was cut from a transcript that only the
credential rules had touched. One engine now, and these tests keep it that way.
"""
import json

import pytest

from stepstitch_service.agent_packet import likely_files
from stepstitch_service.diagnostics import scrub_diagnostics
from stepstitch_service.fixcheck import failure_signature
from stepstitch_service.runner import _diagnostics_redactor
from stepstitch_service.scrubber import clear_advisory_detectors, register_advisory_detector

_JWT = "eyJhbGciOiJIUzI1NiJ9" + "." + "eyJzdWIiOiIxMjM0NTY3ODkwIn0" + "." + "c2lnbmF0dXJlMTIzNDU2"
_KEY = "sk-" + "proj-" + "Ab12Cd34Ef56Gh78Ij90Kl12"
_BLOB = "U2FsdGVkX1+vupppZksvRf5pq5g5XjFRlipRkwB0K1Y96Qsv2Lm+31cmzaAILwyt"


@pytest.mark.parametrize("secret", [_JWT, _KEY, _BLOB, "DE89370400440532013000",
                                    "bit.ly/3xYzAbC", "10.20.30.40"])
def test_the_diagnostics_redactor_uses_the_full_detector_set(secret):
    out = _diagnostics_redactor(f"console.error: upstream said {secret} then died")
    assert secret not in out, out


def test_advisory_detectors_reach_reproduction_evidence_too():
    register_advisory_detector("names", lambda text: ["Jane Synthetic"] if "Jane" in text else [])
    try:
        out = _diagnostics_redactor("could not load profile for Jane Synthetic")
    finally:
        clear_advisory_detectors()
    assert "Jane Synthetic" not in out
    assert "[redacted:advisory:names]" in out


def test_the_file_and_line_still_survive():
    frame = "at submitTransfer (http://127.0.0.1:4711/transfer.js:9:27)"
    assert "transfer.js:9:27" in _diagnostics_redactor(frame)


def test_dict_keys_are_scrubbed_not_only_values():
    record = {"failure_snapshot": {"jane.doe@example.invalid": "clicked"}}
    blob = json.dumps(scrub_diagnostics(record, _diagnostics_redactor))
    assert "jane.doe@example.invalid" not in blob


def test_the_red_signature_carries_no_customer_values():
    transcript = ("Error: expect(received).toBe(expected) for jane.doe@example.invalid "
                  f"with token={_KEY}")
    sig = failure_signature(transcript)
    assert sig, "a failure still has a signature"
    assert "jane.doe@example.invalid" not in sig
    assert _KEY not in sig


def test_two_runs_of_the_same_failure_still_agree_after_redaction():
    a = failure_signature("Error: balance for jane@example.invalid was 12ms late")
    b = failure_signature("Error: balance for jane@example.invalid was 48ms late")
    assert a == b


@pytest.mark.parametrize("frame,expected", [
    ("at f (C:\\Users\\dana.holt\\work\\app\\src\\pay.ts:9:1)", "~\\work\\app\\src\\pay.ts"),
    ("at f (/home/dana/work/app/src/pay.ts:9:1)", "~/work/app/src/pay.ts"),
    ("at f (/Users/dana/work/app/src/pay.ts:9:1)", "~/work/app/src/pay.ts"),
    ("at f (/srv/app/src/pay.ts:9:1)", "/srv/app/src/pay.ts"),
])
def test_likely_files_never_name_the_developer_account(frame, expected):
    paths = [f["path"] for f in likely_files({"failure_stack": [frame]})]
    assert paths == [expected]
