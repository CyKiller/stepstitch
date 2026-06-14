"""Connector platform proof — public seam, conformance kit, discovery, reference adapters."""
import pytest

from stepstitch_service.integrations.base import DraftAdapter
from stepstitch_service.integrations.bundle import (
    all_draft_adapters,
    default_draft_adapters,
    discovered_draft_adapters,
)
from stepstitch_service.integrations.conformance import (
    assert_adapter_conformant,
    conformant_adapters,
)
from stepstitch_service.integrations.contrib import JiraAdapter, ZendeskAdapter


def test_reference_adapters_are_conformant():
    assert conformant_adapters([JiraAdapter(), ZendeskAdapter()]) == ["jira", "zendesk"]


def test_builtin_adapters_are_conformant():
    # The shipped pack must itself pass the kit it advertises.
    assert set(conformant_adapters(default_draft_adapters())) == \
        {"servicenow", "salesforce", "genesys"}


def test_conformance_rejects_non_flat_adapter():
    class Bad(DraftAdapter):
        name = "bad"

        def build_draft(self, summary):
            return {"nested": {"x": 1}}

    with pytest.raises(ValueError):
        assert_adapter_conformant(Bad())


def test_conformance_rejects_forbidden_key_adapter():
    class Leaky(DraftAdapter):
        name = "leaky"

        def build_draft(self, summary):
            return {"footsteps": "oops"}

    with pytest.raises(ValueError):
        assert_adapter_conformant(Leaky())


def test_conformance_rejects_nondeterministic_adapter():
    class Flaky(DraftAdapter):
        name = "flaky"
        _n = 0

        def build_draft(self, summary):
            Flaky._n += 1
            return {"subject": summary.headline, "nonce": Flaky._n}

    with pytest.raises(AssertionError):
        assert_adapter_conformant(Flaky())


def test_discovery_returns_list_without_plugins():
    # No third-party plugins installed in CI -> empty list, never an error.
    assert isinstance(discovered_draft_adapters(), list)


def test_all_adapters_includes_builtins():
    names = {a.name for a in all_draft_adapters()}
    assert {"servicenow", "salesforce", "genesys"} <= names
