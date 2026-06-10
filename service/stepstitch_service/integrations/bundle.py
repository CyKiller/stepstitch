"""Bundled system-of-record draft adapters — COMMERCIAL pack (not open-core).

The concrete ServiceNow / Salesforce / Genesys draft builders are the commercial layer.
The open core never imports this module; a host wires the adapters into the router:

    from stepstitch_service import create_stepstitch_router
    from stepstitch_service.integrations.bundle import default_draft_adapters
    router = create_stepstitch_router(..., draft_adapters=default_draft_adapters())

Keeping this isolated (enforced by tests/test_open_core_boundary.py + .importlinter) means
the open-core service runs with zero adapters by default, and the commercial pack can be
shipped as a separate distribution without touching core code.
"""
from typing import List

from .base import DraftAdapter
from .genesys import GenesysAdapter, build_genesys_context_draft
from .salesforce import SalesforceAdapter, build_case_draft
from .servicenow import ServiceNowAdapter, build_incident_draft

__all__ = [
    "ServiceNowAdapter",
    "SalesforceAdapter",
    "GenesysAdapter",
    "build_incident_draft",
    "build_case_draft",
    "build_genesys_context_draft",
    "default_draft_adapters",
]


def default_draft_adapters() -> List[DraftAdapter]:
    """The bundled financial-services support adapters, in canonical order."""
    return [ServiceNowAdapter(), SalesforceAdapter(), GenesysAdapter()]
