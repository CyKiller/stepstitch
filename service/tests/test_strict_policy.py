"""Strict-schema scrub proof — the financial deny-by-default primitives.

The thesis: under the strict knobs, semantic content is not merely scrubbed — it is
refused. Selectors must be operator-approved static testids or purely structural
paths; routes must match operator-declared templates; labels are permanently masked;
unknown payload keys 422 at the door for EVERY profile. Every assertion here is
measured (a real POST, a real 422, the captured stored row) — never asserted.
"""
import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from stepstitch_service import (
    FINANCIAL_SERVICES_ENTERPRISE,
    create_stepstitch_router,
    generate_playwright_test,
    scrub_trace_payload,
)
from stepstitch_service.host.host import apply_scrub_overrides
from stepstitch_service.scrubber import (
    MASKED_LABEL,
    ScrubRejection,
    derive_policy,
    route_matches_templates,
    selector_allowed,
)

APPROVED = frozenset({"amount-input", "recipient-select", "transfer-submit", "acct-1234"})
TEMPLATES = ("/", "/transfer", "/accounts/:id")


def _strict_policy(**overrides):
    base = dict(
        free_text="disabled",
        max_text_len=1,
        reject_on_forbidden=True,
        selector_policy="approved_testids",
        approved_testids=APPROVED,
        route_policy="operator_templates",
        route_templates=TEMPLATES,
        enforce_masked_labels=True,
    )
    base.update(overrides)
    return derive_policy(**base)


def _step(**kw):
    step = {"timestamp": "t", "type": "click", "route": "/transfer",
            "target": '[data-testid="transfer-submit"]', "label": MASKED_LABEL}
    step.update(kw)
    return step


# --- selector_allowed: the grammar ---------------------------------------------


@pytest.mark.parametrize(
    "target,allowed",
    [
        ('[data-testid="transfer-submit"]', True),
        ('[data-testid="acct-1234"]', True),          # approved, even with digits
        ('[data-testid="customer-ssn-field"]', False),  # semantic, not approved
        ("main > form > button:nth-of-type(2)", True),  # purely structural
        ("button", True),
        ("custom-widget:nth-of-type(3)", True),
        ('[data-testid="amount-input"] > span:nth-of-type(1)', True),  # approved anchor
        ('[data-testid="customer-row"] > td:nth-of-type(2)', False),   # unapproved anchor
        ("#submit", False),                             # ids are not vouched for
        ("div > #inner", False),
        ('a[href="https://bank.example.test"]', False),  # attribute selectors never
        ("", True),                                      # nothing to leak
    ],
)
def test_selector_allowed_grammar(target, allowed):
    assert selector_allowed(target, APPROVED) is allowed


def test_empty_allowlist_rejects_every_testid_but_not_structural():
    # Deny-by-default: with no approved values, no semantic selector passes.
    assert selector_allowed('[data-testid="anything"]', frozenset()) is False
    assert selector_allowed("main > button", frozenset()) is True


# --- route_matches_templates ----------------------------------------------------


@pytest.mark.parametrize(
    "route,matches",
    [
        ("/", True),
        ("/transfer", True),
        ("/accounts/:id", True),        # the scrubber's generic :id under a :param
        ("/customers/jane-doe-smith", False),  # unknown semantic slug
        ("/transfer/extra", False),     # segment-count mismatch
        ("/admin", False),
    ],
)
def test_route_matches_templates(route, matches):
    assert route_matches_templates(route, TEMPLATES) is matches


# --- scrub_trace_payload under the strict knobs ----------------------------------


def test_approved_testid_survives_verbatim():
    payload = {"footsteps": [_step(target='[data-testid="acct-1234"]')]}
    scrubbed, report = scrub_trace_payload(payload, _strict_policy())
    # The free-text digit regexes must NOT mangle an operator-approved value.
    assert scrubbed["footsteps"][0]["target"] == '[data-testid="acct-1234"]'
    assert report["schema_status"] == "strict_schema_passed"


def test_unapproved_semantic_selector_rejects():
    payload = {"footsteps": [_step(target='[data-testid="customer-ssn-field"]')]}
    with pytest.raises(ScrubRejection) as ei:
        scrub_trace_payload(payload, _strict_policy())
    assert "footsteps[0].target" in ei.value.fields


def test_id_selector_rejects():
    payload = {"footsteps": [_step(target="#submit")]}
    with pytest.raises(ScrubRejection):
        scrub_trace_payload(payload, _strict_policy())


def test_unknown_semantic_route_rejects():
    payload = {"footsteps": [_step(route="/customers/jane-doe-smith")]}
    with pytest.raises(ScrubRejection) as ei:
        scrub_trace_payload(payload, _strict_policy())
    assert "footsteps[0].route" in ei.value.fields


def test_free_text_rejects_under_strict():
    payload = {"explanation": "customer SSN 000-00-0000", "footsteps": [_step()]}
    with pytest.raises(ScrubRejection) as ei:
        scrub_trace_payload(payload, _strict_policy())
    assert "explanation" in ei.value.fields


def test_unmasked_label_is_remasked_not_rejected():
    # Masking is loss-free for privacy, so an unmask attempt is corrected, not 422'd —
    # this is exactly what makes the SDK's data-stepstitch-unmask attribute inert here.
    payload = {"footsteps": [_step(label="Jane Doe — Account 8842")]}
    scrubbed, report = scrub_trace_payload(payload, _strict_policy())
    assert scrubbed["footsteps"][0]["label"] == MASKED_LABEL
    assert "footsteps[0].label" in report["scrubbed_fields"]
    assert report["schema_status"] == "strict_schema_passed"


def test_nonrejecting_variant_never_stores_the_violation():
    # Even when a policy combines the strict checks with reject_on_forbidden=False,
    # the semantic value must not persist: target → None, route → "/".
    policy = _strict_policy(reject_on_forbidden=False, free_text="scrub", max_text_len=280)
    payload = {"footsteps": [
        _step(target='[data-testid="customer-ssn-field"]', route="/customers/jane-doe-smith"),
    ]}
    scrubbed, report = scrub_trace_payload(payload, policy)
    step = scrubbed["footsteps"][0]
    assert step["target"] is None
    assert step["route"] == "/"
    assert report["schema_status"] == "strict_schema_violations_dropped"


def test_permissive_policies_report_no_schema_status():
    _, report = scrub_trace_payload({"footsteps": [_step(target="#submit")]},
                                    FINANCIAL_SERVICES_ENTERPRISE)
    assert "schema_status" not in report
    assert not FINANCIAL_SERVICES_ENTERPRISE.strict_schema_active


# --- Router: unknown keys 422 at the door for EVERY profile ----------------------


class CapturingDB:
    def __init__(self):
        self.inserted = None
        self.audits = []

    async def execute(self, query, params=()):
        if query.strip().upper().startswith("INSERT"):
            self.inserted = params

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


def _clean_ingest_body(**extra_top):
    body = {
        "app_id": "app",
        "footsteps": [_step()],
        "metadata": {"sdk_version": "0.2.0"},
    }
    body.update(extra_top)
    return body


def test_hostile_top_level_key_is_422_not_silently_ignored():
    # The old behavior: pydantic discarded unknown top-level keys, so a hostile
    # {"screenshot": ...} never reached the scrubber and looked like a clean ingest.
    client, db = _build()
    r = client.post("/api/stepstitch/v1/session",
                    json=_clean_ingest_body(screenshot="fake-png-bytes",
                                            cookies="session=SECRETCOOKIE"))
    assert r.status_code == 422
    assert db.inserted is None
    blob = json.dumps(r.json())
    assert "screenshot" in blob  # the refusal names the offending field
    assert "SECRETCOOKIE" not in json.dumps(db.audits)


def test_hostile_footstep_key_is_422():
    body = _clean_ingest_body()
    body["footsteps"][0]["value"] = "hunter2"
    client, db = _build()
    r = client.post("/api/stepstitch/v1/session", json=body)
    assert r.status_code == 422
    assert db.inserted is None


def test_sdk_shaped_payload_still_ingests_after_forbid():
    # The forbid boundary must not break the SDK's own wire shape.
    body = {
        "app_id": "app",
        "project_id": "proj",
        "explanation": None,
        "footsteps": [_step()],
        "consent_version": "1",
        "metadata": {"sdk_version": "0.2.0", "viewport": "800x600",
                     "user_agent": "test"},
    }
    client, db = _build()
    r = client.post("/api/stepstitch/v1/session", json=body)
    assert r.status_code == 200
    assert db.inserted is not None


def test_router_rejects_semantic_payload_and_stores_nothing_under_strict():
    client, db = _build(scrub_policy=_strict_policy())
    body = _clean_ingest_body()
    body["footsteps"][0]["target"] = '[data-testid="customer-ssn-field"]'
    body["footsteps"][0]["route"] = "/customers/jane-doe-smith"
    r = client.post("/api/stepstitch/v1/session", json=body)
    assert r.status_code == 422
    assert db.inserted is None
    assert any(a[0] == "stepstitch.scrub_reject" for a in db.audits)
    fields = r.json()["detail"]["fields"]
    assert "footsteps[0].target" in fields
    assert "footsteps[0].route" in fields


def test_router_stores_strict_schema_passed_on_clean_strict_ingest():
    client, db = _build(scrub_policy=_strict_policy())
    r = client.post("/api/stepstitch/v1/session", json=_clean_ingest_body())
    assert r.status_code == 200
    assert r.json()["scrub"]["schema_status"] == "strict_schema_passed"
    stored_meta = json.loads(db.inserted[6])
    assert stored_meta["_scrub"]["schema_status"] == "strict_schema_passed"


# --- Overrides: allowlists scope, never loosen ------------------------------------


def test_overrides_supply_the_strict_allowlists():
    policy = apply_scrub_overrides(
        _strict_policy(approved_testids=frozenset(), route_templates=()),
        {"approved_testids": ["amount-input"], "route_templates": ["/transfer"]},
    )
    assert policy.approved_testids == frozenset({"amount-input"})
    assert policy.route_templates == ("/transfer",)


def test_overrides_cannot_flip_a_strict_knob_off():
    # A hostile or buggy stored document naming the policy fields is ignored: the
    # strict knobs are profile-owned, never override-settable.
    strict = _strict_policy()
    loosened = apply_scrub_overrides(strict, {
        "selector_policy": "any",
        "route_policy": "any",
        "enforce_masked_labels": False,
        "reject_on_forbidden": False,
        "free_text": "scrub",
        "forbidden_keys": [],
    })
    assert loosened.selector_policy == "approved_testids"
    assert loosened.route_policy == "operator_templates"
    assert loosened.enforce_masked_labels is True
    assert loosened.reject_on_forbidden is True
    assert loosened.free_text == "disabled"
    assert loosened.forbidden_keys == strict.forbidden_keys


def test_allowlist_overrides_are_inert_on_a_permissive_profile():
    policy = apply_scrub_overrides(
        FINANCIAL_SERVICES_ENTERPRISE,
        {"approved_testids": ["anything"], "route_templates": ["/x"]},
    )
    # The values are carried but change nothing while the policy modes stay "any".
    assert policy.selector_policy == "any"
    assert policy.route_policy == "any"
    _, report = scrub_trace_payload({"footsteps": [_step(target="#submit")]}, policy)
    assert "schema_status" not in report


def test_malformed_override_entries_are_dropped():
    policy = apply_scrub_overrides(
        _strict_policy(),
        {"approved_testids": "not-a-list", "route_templates": {"nor": "this"}},
    )
    assert policy.approved_testids == APPROVED
    assert policy.route_templates == TEMPLATES
