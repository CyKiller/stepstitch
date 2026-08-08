"""Server-side scrubber proof.

The thesis: even a HOSTILE direct POST (no SDK, hand-rolled curl) cannot persist NPI.
These tests assert against the scrubber directly and against the router's stored row.
"""
import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from stepstitch_service import (
    FINANCIAL_SERVICES_ENTERPRISE,
    ScrubPolicy,
    create_stepstitch_router,
    generate_playwright_test,
    scrub_trace_payload,
)
from stepstitch_service.scrubber import (
    ScrubRejection,
    derive_policy,
    redact_text,
    route_template,
)

# --- redact_text: each PII category ------------------------------------------


@pytest.mark.parametrize(
    "text,kind,marker",
    [
        ("My SSN is 123-45-6789 ok", "ssn", "[redacted:ssn]"),
        ("card 4111 1111 1111 1111 here", "card", "[redacted:card]"),
        # 13 digits but an invalid Luhn checksum: still redacted, labeled as the
        # generic identifier it is — Luhn narrows the label, never the coverage.
        ("acct 1234567890123 done", "number", "[redacted:number]"),
        ("call me at (555) 123-4567", "phone", "[redacted:phone]"),
        ("email jane.doe@example.com please", "email", "[redacted:email]"),
        ("born 04/12/1980 fyi", "date", "[redacted:date]"),
        ("ref number 987654 here", "number", "[redacted:number]"),
        ("see https://portal.bank.com/accounts/55?ssn=1", "url", "[redacted:url]"),
    ],
)
def test_redact_text_each_category(text, kind, marker):
    out, kinds = redact_text(text)
    assert kind in kinds
    assert marker in out
    # The raw sensitive token must be gone.
    for raw in ("123-45-6789", "4111 1111 1111 1111", "jane.doe@example.com"):
        if raw in text:
            assert raw not in out


def test_redact_text_clean_passthrough():
    out, kinds = redact_text("Submit button did nothing on the distributions page")
    assert kinds == []
    assert out == "Submit button did nothing on the distributions page"


def test_redact_text_none():
    assert redact_text(None) == (None, [])


# --- route_template: strips raw URLs + query, templates ids -------------------


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("https://portal.bank.com/accounts/8675309/distributions?ssn=1",
         "/accounts/:id/distributions"),
        ("/accounts/123?token=abc#frag", "/accounts/:id"),
        ("/dashboard", "/dashboard"),
        ("/users/550e8400-e29b-41d4-a716-446655440000/edit", "/users/:id/edit"),
        ("", "/"),
    ],
)
def test_route_template(raw, expected):
    assert route_template(raw) == expected


# --- scrub_trace_payload: the hostile payload ---------------------------------


def _hostile_payload():
    return {
        "explanation": "I'm John, SSN 123-45-6789, acct 1234567890123, "
                       "email john@bank.com, call 555-123-4567",
        "footsteps": [
            {
                "timestamp": "t",
                "type": "navigation",
                # raw URL with query string smuggling NPI
                "route": "https://portal.bank.com/accounts/8675309?ssn=123456789",
                "target": "#submit",
                "label": "Balance: 9876543210",
                "metadata": {
                    "status": 500,
                    "method": "POST",
                    "endpoint": "https://portal.bank.com/api/accounts/8675309?ssn=1",
                    "error_type": "TypeError",
                    "source_path": "https://portal.bank.com/static/app-123456.js?token=abc",
                    "line": 42,
                    "column": 9,
                    "message": "raw user message SSN 123-45-6789",
                    "stack": "stack with SECRETSTACK",
                    "response_body": "SECRETBODY9999",
                },
            }
        ],
        "metadata": {
            "sdk_version": "0.2.0",
            "user_agent": "Mozilla contact ops@bank.com",
            "request_body": "ssn=123-45-6789",
            "cookies": "session=SECRETCOOKIE",
        },
    }


def test_scrub_blocks_all_npi_in_explanation():
    scrubbed, report = scrub_trace_payload(_hostile_payload())
    exp = scrubbed["explanation"]
    assert "123-45-6789" not in exp
    assert "1234567890123" not in exp
    assert "john@bank.com" not in exp
    assert "555-123-4567" not in exp
    assert report["scrub_status"] == "scrubbed"
    assert "explanation" in report["scrubbed_fields"]
    assert report["policy"] == "financial-services-enterprise"


def test_scrub_templates_route_and_drops_forbidden_footstep_meta():
    scrubbed, _ = scrub_trace_payload(_hostile_payload())
    step = scrubbed["footsteps"][0]
    assert step["route"] == "/accounts/:id"
    assert "8675309" not in step["route"]
    # response_body is forbidden → dropped; status (allowlisted) survives.
    assert "response_body" not in step["metadata"]
    assert "message" not in step["metadata"]
    assert "stack" not in step["metadata"]
    assert step["metadata"]["status"] == 500
    assert step["metadata"]["method"] == "POST"
    assert step["metadata"]["endpoint"] == "/api/accounts/:id"
    assert step["metadata"]["source_path"] == "/static/:id"
    assert step["metadata"]["error_type"] == "TypeError"
    assert step["metadata"]["line"] == 42
    assert step["metadata"]["column"] == 9
    # unmasked label carried a long number → redacted.
    assert "9876543210" not in step["label"]


def test_scrub_drops_forbidden_top_level_metadata():
    scrubbed, report = scrub_trace_payload(_hostile_payload())
    meta = scrubbed["metadata"]
    assert "request_body" not in meta
    assert "cookies" not in meta
    assert meta["sdk_version"] == "0.2.0"
    # allowlisted user_agent kept, but its embedded email is redacted.
    assert "ops@bank.com" not in meta["user_agent"]
    assert "metadata.request_body" in report["scrubbed_fields"]


def test_clean_payload_reports_clean():
    clean = {
        "explanation": "Submit did nothing",
        "footsteps": [
            {"timestamp": "t", "type": "click", "route": "/dashboard",
             "target": "#go", "label": "[masked]", "metadata": {"status": 200}}
        ],
        "metadata": {"sdk_version": "0.2.0"},
    }
    scrubbed, report = scrub_trace_payload(clean)
    assert report["scrub_status"] == "clean"
    assert report["scrubbed_fields"] == []
    assert scrubbed["footsteps"][0]["target"] == "#go"


def test_free_text_disabled_drops_explanation():
    policy = derive_policy(free_text="disabled")
    scrubbed, report = scrub_trace_payload({"explanation": "anything", "footsteps": []}, policy)
    assert scrubbed["explanation"] is None
    assert "explanation" in report["scrubbed_fields"]


def test_reject_on_forbidden_raises():
    policy = derive_policy(reject_on_forbidden=True)
    with pytest.raises(ScrubRejection) as ei:
        scrub_trace_payload(_hostile_payload(), policy)
    assert any("request_body" in f for f in ei.value.fields)


def test_default_policy_is_strict_financial_services():
    assert FINANCIAL_SERVICES_ENTERPRISE.name == "financial-services-enterprise"
    assert FINANCIAL_SERVICES_ENTERPRISE.free_text == "scrub"
    assert isinstance(FINANCIAL_SERVICES_ENTERPRISE, ScrubPolicy)


# --- Router integration: nothing hostile reaches the stored row ---------------


class CapturingDB:
    """Captures the exact column values handed to the INSERT."""

    def __init__(self):
        self.inserted = None
        self.audits = []

    async def execute(self, query, params=()):
        if query.strip().upper().startswith("INSERT"):
            self.inserted = {
                "explanation": params[4],
                "footsteps": params[5],
                "trace_metadata": params[6],
            }

    async def fetchone(self, query, params=()):
        return None

    async def fetchall(self, query, params=()):
        return []


def _build(scrub_policy=FINANCIAL_SERVICES_ENTERPRISE):
    db = CapturingDB()

    async def audit(action, actor, detail):
        db.audits.append((action, actor, detail))

    router = create_stepstitch_router(
        get_user_id=lambda: "user-42",
        require_admin=lambda: {"user_id": "admin-1"},
        execute=db.execute,
        fetchone=db.fetchone,
        fetchall=db.fetchall,
        audit=audit,
        generate_playwright_test=generate_playwright_test,
        scrub_policy=scrub_policy,
    )
    app = FastAPI()
    app.include_router(router, prefix="/api")
    return TestClient(app), db


def test_router_never_stores_npi_from_hostile_post():
    client, db = _build()
    r = client.post("/api/stepstitch/v1/session", json=_hostile_payload())
    assert r.status_code == 200
    assert r.json()["scrub"]["scrub_status"] == "scrubbed"

    # The stored row is the real proof — no sensitive VALUE survives in any column.
    # (Dropped key NAMES legitimately appear in the _scrub audit report; we assert on
    # the data values, which are what would actually be NPI.)
    blob = json.dumps(db.inserted)
    for raw in (
        "123-45-6789",
        "1234567890123",
        "john@bank.com",
        "ops@bank.com",
        "8675309",
        "9876543210",
        "SECRETBODY9999",
        "SECRETSTACK",
        "SECRETCOOKIE",
        "session=SECRETCOOKIE",
    ):
        assert raw not in blob, f"leaked {raw!r} into storage"

    # Forbidden keys are not live keys on the stored metadata (only named in the report).
    meta = json.loads(db.inserted["trace_metadata"])
    for forbidden in ("response_body", "request_body", "cookies", "url"):
        assert forbidden not in meta, f"forbidden key {forbidden!r} stored as live data"
    step_meta = json.loads(db.inserted["footsteps"])[0].get("metadata", {})
    assert "response_body" not in step_meta
    assert step_meta.get("status") == 500

    # Scrub report persisted with the trace for compliance review.
    assert meta["_scrub"]["scrub_status"] == "scrubbed"
    assert meta["_scrub"]["policy"] == "financial-services-enterprise"


def test_router_rejects_with_422_under_strict_policy():
    client, db = _build(scrub_policy=derive_policy(reject_on_forbidden=True))
    r = client.post("/api/stepstitch/v1/session", json=_hostile_payload())
    assert r.status_code == 422
    assert db.inserted is None  # nothing was stored
    assert any(a[0] == "stepstitch.scrub_reject" for a in db.audits)
