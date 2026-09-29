"""Channels the ingest scrubber used to wave through, and what its report says.

The audit that prompted this file found fields that reached storage verbatim: a footstep
``timestamp`` is an arbitrary string, and ``app_id`` / ``project_id`` / ``consent_version``
were stored exactly as sent. Any of them could carry an email or an encoded blob past a
scrubber that only ever looked at the explanation, labels, selectors and metadata.
"""
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from stepstitch_service import (
    create_stepstitch_router,
    generate_playwright_test,
    scrub_trace_payload,
)
from stepstitch_service.scrubber import detector_set_sha256


def _payload(**step):
    base = {"timestamp": "2026-07-30T12:00:00Z", "type": "click", "route": "/transfer",
            "target": "#send", "label": "[masked]"}
    base.update(step)
    return {"explanation": None, "footsteps": [base], "metadata": {}}


@pytest.mark.parametrize("ts", ["2026-07-30T12:00:00Z", "2026-07-30T12:00:00.123+02:00",
                                "1727600000000", "t", "t1"])
def test_timestamp_shaped_values_pass(ts):
    scrubbed, report = scrub_trace_payload(_payload(timestamp=ts))
    assert scrubbed["footsteps"][0]["timestamp"] == ts
    assert "footsteps[0].timestamp" not in report["scrubbed_fields"]


@pytest.mark.parametrize("ts", ["jane.doe@example.com", "eyJhbGciOiJIUzI1NiJ9.eyJzdWIi.sig",
                                "Tuesday, Jane Synthetic called", "x" * 80])
def test_a_timestamp_that_is_not_a_timestamp_is_not_stored(ts):
    scrubbed, report = scrub_trace_payload(_payload(timestamp=ts))
    assert scrubbed["footsteps"][0]["timestamp"] == "[redacted:timestamp]"
    assert "footsteps[0].timestamp" in report["scrubbed_fields"]


def test_the_report_counts_what_fired_by_kind():
    payload = _payload(label="mail jane@example.com or joe@example.com")
    payload["explanation"] = "SSN 123-45-6789, reach me at dana@example.test"
    _, report = scrub_trace_payload(payload)
    assert report["kinds"] == {"email": 3, "ssn": 1}


def test_a_clean_payload_reports_no_kinds():
    _, report = scrub_trace_payload(_payload())
    assert report["kinds"] == {}
    assert report["scrub_status"] == "clean"


def test_the_report_pins_the_built_in_detector_set():
    _, report = scrub_trace_payload(_payload())
    assert report["detector_set_sha256"] == detector_set_sha256()
    assert report["detector_set_sha256"].startswith("sha256:")


def test_a_truncated_label_is_reported_even_when_no_pattern_fired():
    scrubbed, report = scrub_trace_payload(_payload(label="a" * 400))
    assert len(scrubbed["footsteps"][0]["label"]) == 280
    assert "footsteps[0].label" in report["scrubbed_fields"]


# --- identifiers the router stores verbatim ------------------------------------------


def _client():
    stored = {}

    async def execute(query, params=()):
        if "INSERT INTO stepstitch_traces" in query:
            stored["row"] = params

    async def fetchone(query, params=()):
        return None

    async def fetchall(query, params=()):
        return []

    app = FastAPI()
    app.include_router(create_stepstitch_router(
        execute=execute, fetchone=fetchone, fetchall=fetchall,
        get_user_id=lambda: "u1", require_admin=lambda: {"user_id": "admin"},
        generate_playwright_test=generate_playwright_test,
    ), prefix="/api")
    return TestClient(app), stored


def _ingest(client, **top):
    body = {"app_id": "tenant-app", "footsteps": [
        {"timestamp": "t", "type": "click", "route": "/x", "target": "#a"}]}
    body.update(top)
    return client.post("/api/stepstitch/v1/session", json=body)


@pytest.mark.parametrize("field,value", [
    ("app_id", "jane.doe@example.com"),
    ("project_id", "acct 4111 1111 1111 1111"),
    ("consent_version", "v1; name=Jane Synthetic"),
    ("app_id", "x" * 200),
])
def test_identifier_fields_refuse_free_text(field, value):
    client, stored = _client()
    r = _ingest(client, **{field: value})
    assert r.status_code == 422, r.text
    assert "row" not in stored


@pytest.mark.parametrize("field,value", [
    ("app_id", "tenant-app"), ("project_id", "proj-1"), ("consent_version", "v1"),
    ("project_id", "acme.web:prod_2"),
])
def test_identifier_fields_accept_identifiers(field, value):
    client, stored = _client()
    r = _ingest(client, **{field: value})
    assert r.status_code == 200, r.text
    assert "row" in stored
