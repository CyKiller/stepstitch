"""The egress guard: the last check on anything that leaves toward an AI agent.

Ingest scrubbing decides what is stored; this decides what is *sent*. It exists because
storage is not the only source of what an agent reads — reproduction output, compiled code,
signatures and summaries are all assembled after ingest, and a scrubber that runs once, at
the door, cannot vouch for text that was written later.

Two properties are pinned here, and they pull in opposite directions:

1. **Catches** — a secret or known PII shape anywhere in an outbound document is redacted
   and counted, wherever it hides.
2. **Doesn't vandalise** — the evidence an agent needs (digests, signatures, Playwright code
   with its URLs and timeouts, commands, timestamps) passes through byte-for-byte. A guard
   that mangles the reproduction is a guard someone turns off.
"""
import json

from stepstitch_service.agent_packet import build_packet
from stepstitch_service.compiler import generate_playwright_test
from stepstitch_service.egress import guard_outbound

_JWT = "eyJhbGciOiJIUzI1NiJ9" + "." + "eyJzdWIiOiIxMjM0NTY3ODkwIn0" + "." + "c2lnbmF0dXJlMTIzNDU2"
_DIGEST = "3f1c9a0b7e2d4c6a8b0f1e3d5c7a9b1d2e4f6a8c0b2d4e6f8a0c2e4b6d8f0a1c"
_SIGNATURE = "k3Jq9Xw2Vb7Lm1Pz8Rt4Yc6Hn0Ds5Fg2Ke7Wq1Ua9Mx3Bo6Ni8Ct4Zp0Gy5Hr2Lj7Sv1Qe9Tf3Uk6Wd8Xa0Ab=="


def test_a_secret_anywhere_in_the_document_is_redacted_and_counted():
    doc = {"summary": {"headline": f"session {_JWT} expired"},
           "diagnostics": {"console_errors": ["mail jane@example.invalid"]}}
    out, report = guard_outbound(doc)
    blob = json.dumps(out)
    assert _JWT not in blob and "jane@example.invalid" not in blob
    assert report["kinds"] == {"jwt": 1, "email": 1}
    assert report["fields"] == ["summary.headline", "diagnostics.console_errors[0]"]
    assert report["mode"] == "redact"


def test_the_input_document_is_not_mutated():
    doc = {"a": f"x {_JWT}"}
    guard_outbound(doc)
    assert doc == {"a": f"x {_JWT}"}


def test_digests_signatures_and_ids_pass_untouched():
    doc = {
        "reproduction": {"script_sha256": _DIGEST, "execution_envelope_sha256": _DIGEST},
        "privacy_posture": {"scrub": {"policy_sha256": f"sha256:{_DIGEST}"}},
        "bundle": {"signature": _SIGNATURE, "public_key": _SIGNATURE[:44], "key_id": "k1"},
        "fix_ref": "a" * 40,
        "trace_id": "550e8400-e29b-41d4-a716-446655440000",
        "created_at": "2026-09-29T12:42:28.047916+00:00",
        "note": f"digest sha256:{_DIGEST} recorded",
    }
    out, report = guard_outbound(doc)
    assert out == doc
    assert report["kinds"] == {}


def test_a_playwright_reproduction_survives_byte_for_byte():
    code = generate_playwright_test("t-1", [
        {"timestamp": "t", "type": "navigation", "route": "/accounts/:id/transfer",
         "label": "[masked]"},
        {"timestamp": "t", "type": "click", "route": "/accounts/:id/transfer",
         "target": '[data-testid="transfer-submit"]', "label": "[masked]"},
        {"timestamp": "t", "type": "api_error", "route": "/accounts/:id/transfer",
         "label": "[masked]",
         "metadata": {"status": 500, "method": "POST", "endpoint": "/api/accounts/:id/pay"}},
    ])
    out, report = guard_outbound({"playwright_code": code})
    assert out["playwright_code"] == code
    assert report["kinds"] == {}


def test_a_clean_agent_packet_needs_no_redaction():
    """The allowlist is correct only if the guard finds NOTHING in a packet that holds no
    customer data. A redaction here is a false positive that would vandalise evidence."""
    packet = build_packet(
        trace_id="550e8400-e29b-41d4-a716-446655440000",
        summary={"route": "/transfer", "headline": "Transfer failed with a 500",
                 "step_count": 3},
        replayability={"score": 0.92, "grade": "A", "warnings": []},
        policy_name="financial-services-enterprise",
        scrub={"scrub_status": "clean", "policy_sha256": f"sha256:{_DIGEST}",
               "detector_set_sha256": f"sha256:{_DIGEST}", "kinds": {}},
        recommended_next_step="Route to frontend engineering.",
        playwright_code=generate_playwright_test("t-1", [
            {"timestamp": "t", "type": "navigation", "route": "/transfer",
             "label": "[masked]"}]),
        diagnostics={
            "source": "local_reproduction", "customer_data_status": "not_verified",
            "failure_stack": ["TypeError: form.amount.toFixed is not a function",
                              "at submitTransfer (http://127.0.0.1:4711/transfer.js:9:27)"],
            "console_errors": ["pay failed with 500"],
            "failed_requests": [{"method": "POST", "path": "/api/accounts/:id/pay",
                                 "status": 500, "duration_ms": 120000}],
        },
        frozen={"script_sha256": _DIGEST, "execution_envelope_sha256": _DIGEST},
    )
    out, report = guard_outbound(packet)
    assert report["kinds"] == {}, report
    assert out == packet


def test_a_luhn_valid_card_is_redacted_but_an_epoch_timestamp_is_not():
    out, report = guard_outbound({"a": "card 4111 1111 1111 1111", "b": "at 1727600000000"})
    assert out["a"] == "card [redacted:card]"
    assert out["b"] == "at 1727600000000"
    assert report["kinds"] == {"card": 1}


def test_scan_mode_reports_without_touching_a_signed_document():
    """A signed artifact cannot be edited without breaking its signature, so the guard
    reports what it would have removed and leaves the bytes alone."""
    doc = {"statement": {"detail": f"token={_JWT}"}, "signature": _SIGNATURE}
    out, report = guard_outbound(doc, mode="scan")
    assert out == doc
    assert report["mode"] == "scan"
    assert report["kinds"] == {"jwt": 1}
    assert report["fields"] == ["statement.detail"]


def test_keys_are_guarded_as_well_as_values():
    out, report = guard_outbound({"by_user": {"jane@example.invalid": 3}})
    assert "jane@example.invalid" not in json.dumps(out)
    assert report["kinds"] == {"email": 1}


# --- the MCP server applies it to every tool result --------------------------------------

import asyncio  # noqa: E402

from stepstitch_service.mcp_server import dispatch_tool  # noqa: E402


def _route_returning(doc):
    async def call_route(method, path, query):
        return json.loads(json.dumps(doc))
    return call_route


def test_every_mcp_tool_result_is_guarded():
    """Whatever token the MCP server holds, its reader is a model. So the guard runs on the
    MCP path unconditionally — not only when the host saw an agent token."""
    result = asyncio.run(dispatch_tool(
        "get_trace_summary", {"trace_id": "t-1"},
        _route_returning({"headline": f"session {_JWT} expired"})))
    assert _JWT not in json.dumps(result)
    assert result["_egress"]["kinds"] == {"jwt": 1}


def test_an_mcp_signed_artifact_is_scanned_not_edited():
    doc = {"bundle": {"detail": f"token={_JWT}"}, "signature": _SIGNATURE}
    result = asyncio.run(dispatch_tool(
        "get_attestation", {"trace_id": "t-1"}, _route_returning(doc)))
    assert result == doc


def test_a_host_report_is_kept_when_the_mcp_pass_finds_nothing_new():
    already = {"headline": "session [redacted:jwt] expired",
               "_egress": {"mode": "redact", "kinds": {"jwt": 1}, "fields": ["headline"]}}
    result = asyncio.run(dispatch_tool(
        "get_trace_summary", {"trace_id": "t-1"}, _route_returning(already)))
    assert result["_egress"]["kinds"] == {"jwt": 1}


# --- deliveries to systems of record, and the packet's own description -------------------

from stepstitch_service.agent_packet import privacy_posture  # noqa: E402
from stepstitch_service.delivery.base import DeliveryResult, RecordWriter  # noqa: E402


class _Capture(RecordWriter):
    name = "capture"

    def __init__(self):
        self.sent = None

    async def _create(self, draft):
        self.sent = draft
        return DeliveryResult(target=self.name, record_id="r-1", deduped=False, receipt={})


def test_a_delivered_draft_passes_the_guard_before_it_leaves():
    writer = _Capture()
    asyncio.run(writer.deliver({"short_description": f"session {_JWT} expired",
                                "correlation_id": "stepstitch:t-1"}))
    assert _JWT not in json.dumps(writer.sent)
    assert writer.sent["correlation_id"] == "stepstitch:t-1"


def test_the_packet_says_where_the_egress_guard_runs_and_what_it_is_not():
    posture = privacy_posture("financial-services-enterprise", {"scrub_status": "clean"}, False)
    guard = posture["egress_guard"]
    assert "_egress" in guard["detail"]
    assert guard["scope"] == ["agent-token responses", "MCP tool results", "record deliveries"]
    assert "not proof" in guard["limits"]
