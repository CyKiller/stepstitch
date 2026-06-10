"""StepStitch adapter framework — open-core boundary.

The **base framework** (`TraceSummary`, `DraftAdapter`, `build_trace_summary`,
`assert_flat`, `export_preview`) is open-core (Apache-2.0). The **concrete vendor
adapters** (ServiceNow / Salesforce / Genesys) are the COMMERCIAL pack and live in
``integrations.bundle`` — the open core never imports them. A host injects them via
``create_stepstitch_router(draft_adapters=...)``.

This separation is enforced by ``tests/test_open_core_boundary.py`` and ``.importlinter``:
no core module may import a concrete adapter, which keeps the commercial pack cleanly
extractable into its own distribution.
"""
from .base import (
    DraftAdapter,
    TraceSummary,
    assert_flat,
    build_trace_summary,
    export_preview,
)

__all__ = [
    "TraceSummary",
    "DraftAdapter",
    "build_trace_summary",
    "assert_flat",
    "export_preview",
]
