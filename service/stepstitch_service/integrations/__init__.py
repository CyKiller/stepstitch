"""StepStitch outbound integrations — sanitized, flat, DRAFT-only.

Every adapter turns a :class:`TraceSummary` (derived from an already-scrubbed trace)
into a flat record draft for a system of record. Adapters never make live API calls in
this layer — they build the payload a host can preview, approve, and send. Direct
writes stay behind an explicit host-side governance flag.

Core never imports a vendor SDK; these are pure dict builders.
"""
from .base import (
    DraftAdapter,
    TraceSummary,
    assert_flat,
    build_trace_summary,
    export_preview,
)
from .genesys import GenesysAdapter, build_genesys_context_draft
from .salesforce import SalesforceAdapter, build_case_draft
from .servicenow import ServiceNowAdapter, build_incident_draft

__all__ = [
    "TraceSummary",
    "DraftAdapter",
    "build_trace_summary",
    "assert_flat",
    "export_preview",
    "ServiceNowAdapter",
    "build_incident_draft",
    "SalesforceAdapter",
    "build_case_draft",
    "GenesysAdapter",
    "build_genesys_context_draft",
]
