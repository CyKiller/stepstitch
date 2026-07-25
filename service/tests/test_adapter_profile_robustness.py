"""Adapter × deployment-profile robustness proof.

Adapters only ever see a ``TraceSummary`` derived from *already-scrubbed* footsteps — by
architecture they cannot see which deployment profile produced that summary. This test
proves that invariant holds in practice: every bundled adapter's draft stays flat and
NPI-free no matter which of the four drift-guarded profiles (`profiles.py`) scrubbed the
underlying trace, closing the "does this still hold for every posture" gap named in the
product-strengthening plan (broadening the existing enterprise adapters).
"""
from stepstitch_service.integrations import assert_flat, build_trace_summary, export_preview
from stepstitch_service.integrations.base import FORBIDDEN_DRAFT_KEYS
from stepstitch_service.integrations.bundle import default_draft_adapters
from stepstitch_service.profiles import available_profiles, get_profile, policy_from_profile
from stepstitch_service.scrubber import ScrubRejection, scrub_trace_payload

# Same NPI markers the conformance kit checks for (integrations/conformance.py).
_NPI_MARKERS = ("123-45-6789", "8675309", "data-testid")


def _hostile_payload(*, with_explanation: bool = True):
    payload = {
        "app_id": "demo-app",
        "footsteps": [
            {"timestamp": "t", "type": "navigation",
             "route": "/accounts/123456/distributions", "label": "click here"},
            {"timestamp": "t", "type": "click",
             "route": "/accounts/123456/distributions",
             "target": '[data-testid="submit"]', "label": "Submit"},
            {"timestamp": "t", "type": "api_error",
             "route": "/accounts/123456/distributions", "label": "error",
             "metadata": {"status": 500, "endpoint": "/api/accounts/123456/distributions"}},
        ],
        "metadata": {"sdk_version": "0.6.0"},
    }
    if with_explanation:
        payload["explanation"] = (
            "Card 4111 1111 1111 1111, SSN 123-45-6789, call 555-867-5309"
        )
    return payload


def test_every_profile_produces_npi_free_flat_drafts_for_every_adapter():
    assert available_profiles() == sorted(
        ["financial-services-enterprise", "healthcare-strict",
         "internal-enterprise", "open-source-default"]
    )

    for profile_name in available_profiles():
        policy = policy_from_profile(get_profile(profile_name))
        try:
            scrubbed, report = scrub_trace_payload(_hostile_payload(), policy)
        except ScrubRejection:
            # healthcare-strict disables free text *and* hard-rejects it (422 at the
            # router) rather than silently dropping it — that IS the tightened
            # boundary working. A real host simply never sends `explanation` under
            # this profile; footsteps-only ingestion still must scrub cleanly.
            scrubbed, report = scrub_trace_payload(
                _hostile_payload(with_explanation=False), policy
            )
        assert report["scrub_status"] in ("clean", "scrubbed")

        summary = build_trace_summary(
            f"trace-{profile_name}", scrubbed["footsteps"], project_id="proj-1"
        )
        preview = export_preview(summary, default_draft_adapters())

        assert set(preview.keys()) == {
            "servicenow", "salesforce", "genesys", "jira", "zendesk",
            "github_issues", "linear", "slack",
        }
        for adapter_name, draft in preview.items():
            assert_flat(draft), f"{adapter_name} draft not flat under {profile_name}"
            leaked = set(draft) & FORBIDDEN_DRAFT_KEYS
            assert not leaked, f"{adapter_name} leaked {leaked} under {profile_name}"
            blob = " ".join(str(v) for v in draft.values())
            for marker in _NPI_MARKERS:
                assert marker not in blob, (
                    f"{adapter_name} leaked NPI marker {marker!r} under {profile_name}"
                )
