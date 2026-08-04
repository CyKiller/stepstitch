"""The console's JS must speak the host's actual wire contract.

The scrub editor shipped broken for two releases: the page POSTed (via jsonPost) to a
route registered as PUT, sent ``{patterns, forbidden_keys}`` where ``ScrubConfig``
expects ``{extra_redactions, extra_forbidden_keys}``, and previewed with
``{text, overrides}`` where ``ScrubPreview`` expects ``{text, extra_redactions}``.
Every unit test passed because none of them read the embedded JS, and the browser
suite ran against the demo console's read-only stub. These tests are the cheap layer
that would have caught it: they assert the JS source uses the right method and field
tokens for each admin endpoint. The real proof is the governance-editor browser spec
(tests/e2e/governance-editor.spec.ts) driving a live host.
"""
from __future__ import annotations

import re

from stepstitch_service.host.dashboard import DASHBOARD_HTML
from stepstitch_service.host.host import ScrubConfig, ScrubPreview


def _js_call_sites(endpoint: str) -> list[str]:
    """Every adminApi/api call touching the endpoint, with its wrapped body text."""
    pattern = re.compile(
        r"(?:adminApi|api)\(\s*\"" + re.escape(endpoint) + r"\"[^;]*;", re.S
    )
    sites = pattern.findall(DASHBOARD_HTML)
    assert sites, f"the console never calls {endpoint} — did the page lose the feature?"
    return sites


def test_scrub_save_is_a_put_of_the_scrubconfig_fields():
    sites = _js_call_sites("/config/scrub")
    writes = [s for s in sites if "jsonPut(" in s or "jsonPost(" in s]
    assert writes, "the console never saves the scrub config"
    for site in writes:
        assert "jsonPut(" in site, (
            "the scrub-config save must be a PUT (the route is @app.put); "
            f"found: {site!r}"
        )
    # The pending document the page builds must carry exactly the model's fields.
    model_fields = set(ScrubConfig.model_fields)
    for field_name in model_fields:
        assert f"{field_name}:" in DASHBOARD_HTML or f'"{field_name}"' in DASHBOARD_HTML, (
            f"the console never mentions ScrubConfig field {field_name!r}"
        )
    # And the old invented shape must be gone.
    assert "overrides.patterns" not in DASHBOARD_HTML
    assert "pending.patterns" not in DASHBOARD_HTML
    assert "forbidden_keys: keys.slice()" not in DASHBOARD_HTML


def test_scrub_preview_sends_the_scrubpreview_fields():
    sites = _js_call_sites("/scrub/preview")
    assert any("jsonPost(" in s for s in sites)
    for site in sites:
        for field_name in ScrubPreview.model_fields:
            assert field_name in site, (
                f"preview call is missing ScrubPreview field {field_name!r}: {site!r}"
            )
        assert "overrides:" not in site, "preview must not send the old invented shape"


def test_redaction_pairs_are_pairs_not_objects():
    # ScrubConfig.extra_redactions is a list of [label, regex] PAIRS; the old page
    # pushed {label, regex} objects, which the host's pair validation rejected.
    assert "push([label.value.trim(), regex.value.trim()])" in DASHBOARD_HTML
    assert "{ label: label.value.trim(), regex: regex.value.trim() }" not in DASHBOARD_HTML


def test_strict_allowlist_editors_exist_and_are_flag_gated():
    # The strict editors render only when the host says the profile enforces the
    # strict schema — from the response flag, never inferred from the profile name.
    assert "cfg.strict_schema" in DASHBOARD_HTML
    assert "approved_testids" in DASHBOARD_HTML
    assert "route_templates" in DASHBOARD_HTML
