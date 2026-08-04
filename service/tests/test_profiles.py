"""Enterprise profile proof — each profile maps to the right ScrubPolicy, and the
committed JSON artifacts never drift from the canonical Python definitions."""
import json
from pathlib import Path

import pytest

from stepstitch_service import (
    available_profiles,
    load_profile,
    policy_from_profile,
)
from stepstitch_service.profiles import DEFAULT_PROFILE, PROFILES, get_profile

_REPO_ROOT = Path(__file__).resolve().parents[2]
_PROFILES_DIR = _REPO_ROOT / "profiles"


def test_default_profile_is_financial_services():
    assert DEFAULT_PROFILE == "financial-services-enterprise"
    policy = load_profile()
    assert policy.name == "financial-services-enterprise"
    assert policy.free_text == "scrub"
    assert policy.reject_on_forbidden is False


def test_all_profiles_load_to_a_policy():
    for name in available_profiles():
        policy = load_profile(name)
        assert policy.name == name


def test_healthcare_strict_is_hardest():
    policy = load_profile("healthcare-strict")
    assert policy.free_text == "disabled"
    assert policy.reject_on_forbidden is True


def test_financial_services_strict_is_deny_by_default():
    policy = load_profile("financial-services-strict")
    assert policy.free_text == "disabled"
    assert policy.reject_on_forbidden is True
    assert policy.selector_policy == "approved_testids"
    assert policy.route_policy == "operator_templates"
    assert policy.enforce_masked_labels is True
    assert policy.strict_schema_active
    # The allowlists ship EMPTY: until an operator names static values, every
    # semantic selector and route is rejected. Config scopes; it never disables.
    assert policy.approved_testids == frozenset()
    assert policy.route_templates == ()


def test_permissive_profiles_do_not_grow_strict_knobs():
    for name in ("financial-services-enterprise", "healthcare-strict",
                 "internal-enterprise", "open-source-default"):
        policy = load_profile(name)
        assert not policy.strict_schema_active, f"{name} must stay behaviorally unchanged"


def test_internal_enterprise_allows_longer_notes():
    policy = load_profile("internal-enterprise")
    assert policy.free_text == "scrub"
    assert policy.max_text_len == 1000


def test_unknown_profile_raises():
    with pytest.raises(KeyError):
        get_profile("does-not-exist")


def test_profile_cannot_weaken_allowlist():
    # A profile only tunes free-text/rejection; allowlists stay the hardened defaults.
    base = policy_from_profile(get_profile("open-source-default"))
    fin = load_profile("financial-services-enterprise")
    assert base.forbidden_keys == fin.forbidden_keys
    assert base.metadata_allowlist == fin.metadata_allowlist


def test_json_artifacts_match_canonical_definitions():
    # Drift guard: the committed profiles/*.json must equal the Python source of truth.
    assert _PROFILES_DIR.is_dir(), f"missing {_PROFILES_DIR}"
    on_disk = {p.stem for p in _PROFILES_DIR.glob("*.json")}
    assert on_disk == set(PROFILES.keys())
    for name, prof in PROFILES.items():
        disk = json.loads((_PROFILES_DIR / f"{name}.json").read_text())
        assert disk == prof, f"profiles/{name}.json drifted from PROFILES[{name!r}]"
