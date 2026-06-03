"""ServiceNow incident DRAFT adapter (flat, sanitized).

Mirrors the ServiceNow connector's Create Record shape (Incident table). Produces a
draft only — the host decides whether to send it, and direct create stays behind a
governance flag. Carries a `correlation_id` so a later real incident can be reconciled.
"""
from __future__ import annotations

from typing import Any, Dict

from .base import DraftAdapter, TraceSummary, assert_flat

__all__ = ["ServiceNowAdapter", "build_incident_draft"]


def build_incident_draft(
    summary: TraceSummary,
    *,
    category: str = "software",
    subcategory: str = "portal",
    impact: str = "3",
    urgency: str = "3",
) -> Dict[str, Any]:
    """Build a flat ServiceNow incident draft from a sanitized summary."""
    work_notes = (
        f"Replayability score: {summary.replayability_score:.2f} "
        f"(grade {summary.replayability_grade}). "
        "Playwright repro available internally. "
        f"Privacy: {summary.privacy_status}."
    )
    draft = {
        "short_description": summary.headline,
        "description": (
            f"{summary.headline}. Sanitized StepStitch summary only — no screens, "
            f"field values, raw URLs, or page text. Route template: {summary.route}. "
            f"Steps captured: {summary.step_count}."
        ),
        "category": category,
        "subcategory": subcategory,
        "impact": impact,
        "urgency": urgency,
        "correlation_id": f"stepstitch:{summary.trace_id}",
        "work_notes": work_notes,
    }
    return assert_flat(draft)


class ServiceNowAdapter(DraftAdapter):
    name = "servicenow"

    def __init__(
        self,
        *,
        category: str = "software",
        subcategory: str = "portal",
        impact: str = "3",
        urgency: str = "3",
    ) -> None:
        self.category = category
        self.subcategory = subcategory
        self.impact = impact
        self.urgency = urgency

    def build_draft(self, summary: TraceSummary) -> Dict[str, Any]:
        return build_incident_draft(
            summary,
            category=self.category,
            subcategory=self.subcategory,
            impact=self.impact,
            urgency=self.urgency,
        )
