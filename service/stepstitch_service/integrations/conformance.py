"""Reusable conformance kit for StepStitch draft adapters.

Any connector — built-in or third-party — can import these helpers in its own test suite to
prove it respects the privacy seam: a draft must be flat, identity-safe, and deterministic.

    from stepstitch_service.integrations.conformance import assert_adapter_conformant
    def test_my_adapter():
        assert_adapter_conformant(MyAdapter())
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from .base import (
    FORBIDDEN_DRAFT_KEYS,
    DraftAdapter,
    TraceSummary,
    assert_flat,
    build_trace_summary,
)

# Tokens that must never appear in a draft (a raw id, an SSN, a selector).
_NPI_MARKERS = ("123-45-6789", "8675309", "data-testid")


def sample_trace_summary() -> TraceSummary:
    """A representative, already-sanitized summary for conformance checks."""
    footsteps: List[Dict[str, Any]] = [
        {"timestamp": "t", "type": "navigation",
         "route": "/accounts/:id/distributions", "label": "[masked]"},
        {"timestamp": "t", "type": "api_error",
         "route": "/accounts/:id/distributions", "label": "[masked]",
         "metadata": {"status": 500, "endpoint": "/api/accounts/:id"}},
    ]
    return build_trace_summary("trace-conformance", footsteps, project_id="proj")


def assert_adapter_conformant(
    adapter: DraftAdapter, summary: Optional[TraceSummary] = None
) -> None:
    """Raise AssertionError/ValueError unless ``adapter`` is a well-behaved draft adapter."""
    summary = summary or sample_trace_summary()

    assert isinstance(adapter.name, str) and adapter.name, \
        "adapter.name must be a non-empty string"

    draft = adapter.build_draft(summary)
    assert isinstance(draft, dict) and draft, "build_draft must return a non-empty dict"

    # Flat scalars + no forbidden keys (this also raises on nested/forbidden values).
    assert_flat(draft)
    leaked = set(draft) & FORBIDDEN_DRAFT_KEYS
    assert not leaked, f"draft carries forbidden keys: {sorted(leaked)}"

    # No NPI markers anywhere in the values.
    blob = " ".join(str(v) for v in draft.values())
    for marker in _NPI_MARKERS:
        assert marker not in blob, f"draft leaked NPI marker {marker!r}"

    # Deterministic: same summary in, same draft out.
    assert adapter.build_draft(summary) == draft, "build_draft must be deterministic"


def conformant_adapters(adapters: List[DraftAdapter]) -> List[str]:
    """Run conformance over a list; return the names that passed (raises on the first that
    does not)."""
    passed = []
    for a in adapters:
        assert_adapter_conformant(a)
        passed.append(a.name)
    return passed
