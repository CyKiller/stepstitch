"""StepStitch adapter framework — the public extension seam (Apache-2.0).

The **base framework** (`TraceSummary`, `DraftAdapter`, `build_trace_summary`,
`assert_flat`, `export_preview`) and the **concrete vendor adapters** (ServiceNow /
Salesforce / Genesys, in ``integrations.bundle``) are all Apache-2.0. The base module is
the single, public seam anyone can extend with their own adapter. A host injects adapters
via ``create_stepstitch_router(draft_adapters=...)``.

A **layering** rule is enforced by ``tests/test_open_core_boundary.py`` and
``.importlinter``: no core module imports a concrete adapter, and adapters only ever see the
sanitized ``TraceSummary`` — keeping the privacy boundary intact and the adapter set cleanly
swappable.
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
