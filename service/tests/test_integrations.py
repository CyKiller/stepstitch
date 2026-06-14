"""Draft adapter proof — drafts are flat, sanitized, and identity-safe."""
import pytest

from stepstitch_service.integrations import (
    assert_flat,
    build_trace_summary,
    export_preview,
)
from stepstitch_service.integrations.base import _FLAT_SCALARS
from stepstitch_service.integrations.bundle import (
    GenesysAdapter,
    SalesforceAdapter,
    ServiceNowAdapter,
    build_case_draft,
    build_genesys_context_draft,
    build_incident_draft,
)


def _footsteps():
    return [
        {"timestamp": "t", "type": "navigation", "route": "/accounts/:id/distributions",
         "label": "[masked]"},
        {"timestamp": "t", "type": "click", "route": "/accounts/:id/distributions",
         "target": '[data-testid="submit"]', "label": "[masked]"},
        {"timestamp": "t", "type": "api_error", "route": "/accounts/:id/distributions",
         "label": "[masked]", "metadata": {
             "status": 500, "endpoint": "/api/accounts/:id/distributions"}},
    ]


def test_summary_is_flat_and_derived_from_structure_only():
    s = build_trace_summary("trace_123", _footsteps(), project_id="proj-1")
    assert s.trace_id == "trace_123"
    assert s.route == "/accounts/:id/distributions"
    assert s.failing_status == 500
    assert s.diagnostic_type == "api_error"
    assert s.diagnostic_endpoint == "/api/accounts/:id/distributions"
    assert "500" in s.headline
    assert s.privacy_status == "Scrubbed / No NPI"
    # summary dict is flat
    for v in s.as_dict().values():
        assert isinstance(v, _FLAT_SCALARS)


def test_servicenow_draft_flat_and_correlated():
    s = build_trace_summary("trace_123", _footsteps())
    draft = build_incident_draft(s)
    assert draft["correlation_id"] == "stepstitch:trace_123"
    assert draft["category"] == "software"
    assert "Sanitized StepStitch summary only" in draft["description"]
    assert_flat(draft)  # raises if nested / forbidden


def test_salesforce_draft_flat_high_priority_on_500():
    s = build_trace_summary("trace_123", _footsteps())
    draft = build_case_draft(s)
    assert draft["Origin"] == "StepStitch"
    assert draft["StepStitchTraceId__c"] == "trace_123"
    assert draft["RouteTemplate__c"] == "/accounts/:id/distributions"
    assert draft["Priority"] == "High"  # 500 -> High
    assert draft["PlaywrightReproLink__c"] == "internal-link-only"
    assert_flat(draft)


def test_genesys_context_draft_flat_and_queue_oriented():
    s = build_trace_summary("trace_123", _footsteps())
    draft = build_genesys_context_draft(s)
    assert draft["origin"] == "StepStitch"
    assert draft["trace_correlation_id"] == "stepstitch:trace_123"
    assert draft["diagnostic_type"] == "api_error"
    assert draft["diagnostic_endpoint"] == "/api/accounts/:id/distributions"
    assert draft["suggested_queue"] == "digital-platform-escalation"
    assert draft["playwright_repro"] == "internal-link-only"
    assert_flat(draft)


def test_drafts_never_carry_raw_trace_internals():
    s = build_trace_summary("trace_123", _footsteps())
    for draft in (build_incident_draft(s), build_case_draft(s),
                  build_genesys_context_draft(s)):
        keys = set(draft.keys())
        for forbidden in ("footsteps", "explanation", "user_id", "target", "raw_url"):
            assert forbidden not in keys
        # no selector / page-text leaks in any value
        blob = " ".join(str(v) for v in draft.values())
        assert "data-testid" not in blob


def test_assert_flat_rejects_nested():
    with pytest.raises(ValueError):
        assert_flat({"Subject": "ok", "nested": {"a": 1}})


def test_assert_flat_rejects_forbidden_key():
    with pytest.raises(ValueError):
        assert_flat({"footsteps": "anything"})


def test_export_preview_builds_financial_services_pack():
    s = build_trace_summary("trace_123", _footsteps())
    preview = export_preview(s, [ServiceNowAdapter(), SalesforceAdapter(), GenesysAdapter()])
    assert set(preview.keys()) == {"servicenow", "salesforce", "genesys"}
    assert preview["servicenow"]["correlation_id"] == "stepstitch:trace_123"
    assert preview["salesforce"]["StepStitchTraceId__c"] == "trace_123"
    assert preview["genesys"]["trace_correlation_id"] == "stepstitch:trace_123"


def _long_route_footsteps():
    long_route = "/accounts/:id/" + "segment/" * 30  # > 200 chars
    return [
        {"timestamp": "t", "type": "api_error", "route": long_route, "label": "[masked]",
         "metadata": {"status": 500, "endpoint": "/api/x"}},
    ]


def test_servicenow_rejects_out_of_range_impact():
    s = build_trace_summary("trace_123", _footsteps())
    with pytest.raises(ValueError):
        build_incident_draft(s, impact="9")
    with pytest.raises(ValueError):
        build_incident_draft(s, urgency="critical")


def test_servicenow_caps_short_description_explicitly():
    s = build_trace_summary("trace_123", _long_route_footsteps())
    draft = build_incident_draft(s)
    assert len(draft["short_description"]) <= 160
    assert draft["short_description"].endswith("…")  # visible, not silent
    assert "truncated to 160" in draft["work_notes"]
    assert_flat(draft)


def test_salesforce_caps_subject_and_priority_in_picklist():
    long = build_trace_summary("trace_123", _long_route_footsteps())
    draft = build_case_draft(long)
    assert len(draft["Subject"]) <= 255
    # Priority for every kind of trace must be a stock picklist value.
    from stepstitch_service.integrations.validation import SALESFORCE_PRIORITY
    for s in (build_trace_summary("a", _footsteps()),
              build_trace_summary("b", _long_route_footsteps()),
              build_trace_summary("c", [{"timestamp": "t", "type": "navigation",
                                         "route": "/d", "label": "[masked]"}])):
        assert build_case_draft(s)["Priority"] in SALESFORCE_PRIORITY


def test_summary_handles_navigation_only_trace():
    nav = [{"timestamp": "t", "type": "navigation", "route": "/dashboard",
            "label": "[masked]"}]
    s = build_trace_summary("t1", nav)
    assert s.failing_status is None
    assert s.exception_type is None
    assert "/dashboard" in s.headline
    assert build_case_draft(s)["Priority"] == "Medium"
