"""Operator scrub overrides — the dashboard scrub editor's safety contract.

The dashboard lets an operator ADD custom redaction patterns + forbidden keys. The single
invariant that must hold: overrides can only **tighten** — they add redaction/drops and can
never remove a built-in rule. These tests prove that property at the scrubber level.
"""
import re

from stepstitch_service.scrubber import (
    FINANCIAL_SERVICES_ENTERPRISE as BASE,
    compile_extra_redactions,
    derive_policy,
    redact_text,
    scrub_trace_payload,
)


def test_extra_pattern_redacts_what_builtins_miss():
    # "EMP-12345" is not caught by the built-ins (only 5 digits; no email/ssn/card shape).
    extra = compile_extra_redactions(derive_policy(extra_redactions=(("empid", r"EMP-\d+"),)))
    plain, kinds = redact_text("ticket EMP-12345 filed", ())
    assert "EMP-12345" in plain and kinds == []           # built-ins alone: untouched
    redacted, kinds = redact_text("ticket EMP-12345 filed", extra)
    assert "EMP-12345" not in redacted and "[redacted:custom:empid]" in redacted
    assert kinds == ["custom:empid"]


def test_overrides_only_add_never_remove_builtins():
    # A value the BASE redacts must stay redacted once extras are added (monotonic).
    text = "SSN 123-45-6789 and EMP-7"
    extra = compile_extra_redactions(derive_policy(extra_redactions=(("empid", r"EMP-\d+"),)))
    out, _ = redact_text(text, extra)
    assert "[redacted:ssn]" in out                          # built-in still fires
    assert "[redacted:custom:empid]" in out                 # extra also fires
    assert "123-45-6789" not in out and "EMP-7" not in out


def test_all_forbidden_keys_is_a_superset_of_builtins():
    policy = derive_policy(extra_forbidden_keys=frozenset({"user_agent"}))
    assert BASE.forbidden_keys <= policy.all_forbidden_keys   # built-ins never removed
    assert "user_agent" in policy.all_forbidden_keys


def test_extra_forbidden_key_drops_an_otherwise_allowed_field():
    # user_agent is normally allow-listed and kept; adding it as a forbidden key drops it.
    payload = {"explanation": "x", "footsteps": [],
               "metadata": {"sdk_version": "0.4.0", "user_agent": "Mozilla/5.0"}}
    kept, _ = scrub_trace_payload(payload, BASE)
    assert kept["metadata"].get("user_agent") == "Mozilla/5.0"

    tightened = derive_policy(extra_forbidden_keys=frozenset({"user_agent"}))
    dropped, report = scrub_trace_payload(payload, tightened)
    assert "user_agent" not in dropped["metadata"]
    assert "metadata.user_agent" in report["scrubbed_fields"]


def test_custom_pattern_applies_to_a_stored_trace_label():
    policy = derive_policy(extra_redactions=(("empid", r"EMP-\d+"),))
    payload = {
        "explanation": "see EMP-99 in the flow",
        "footsteps": [{"timestamp": "t", "type": "click", "route": "/x",
                       "label": "row for EMP-99"}],
        "metadata": {"sdk_version": "0.4.0"},
    }
    scrubbed, report = scrub_trace_payload(payload, policy)
    assert "EMP-99" not in scrubbed["explanation"]
    assert "EMP-99" not in scrubbed["footsteps"][0]["label"]
    assert report["scrub_status"] == "scrubbed"


def test_invalid_pattern_is_skipped_not_fatal():
    # A bad stored regex must never break ingestion — it is simply ignored.
    extra = compile_extra_redactions(derive_policy(extra_redactions=(("bad", r"([unclosed"),)))
    assert extra == ()
    out, _ = redact_text("anything", extra)
    assert out == "anything"
