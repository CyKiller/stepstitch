"""Genesys support-context DRAFT adapter (flat, sanitized).

This is not a Genesys API client. It builds a safe context packet a Copilot/Power
Platform flow can map into a contact-center support process, queue handoff, or case note.
"""
from __future__ import annotations

from typing import Any, Dict

from .base import DraftAdapter, TraceSummary, assert_flat

__all__ = ["GenesysAdapter", "build_genesys_context_draft"]


def _suggested_queue(summary: TraceSummary) -> str:
    if summary.failing_status is not None and summary.failing_status >= 500:
        return "digital-platform-escalation"
    if summary.exception_type is not None:
        return "web-experience-support"
    return "digital-service-support"


def build_genesys_context_draft(summary: TraceSummary) -> Dict[str, Any]:
    """Build a flat Genesys support-context draft from a sanitized summary."""
    draft = {
        "origin": "StepStitch",
        "trace_correlation_id": f"stepstitch:{summary.trace_id}",
        "issue_headline": summary.headline,
        "route_template": summary.route,
        "diagnostic_type": summary.diagnostic_type or "user_report",
        "diagnostic_endpoint": summary.diagnostic_endpoint or "",
        "failing_status": summary.failing_status,
        "exception_type": summary.exception_type or "",
        "replayability_score": summary.replayability_score,
        "replayability_grade": summary.replayability_grade,
        "suggested_queue": _suggested_queue(summary),
        "privacy_status": summary.privacy_status,
        "playwright_repro": "internal-link-only",
    }
    return assert_flat(draft)


class GenesysAdapter(DraftAdapter):
    name = "genesys"

    def build_draft(self, summary: TraceSummary) -> Dict[str, Any]:
        return build_genesys_context_draft(summary)
