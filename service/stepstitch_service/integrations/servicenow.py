"""ServiceNow incident DRAFT adapter (flat, sanitized).

Mirrors the ServiceNow connector's Create Record shape (Incident table). Produces a
draft only — the host decides whether to send it, and direct create stays behind a
governance flag. Carries a `correlation_id` so a later real incident can be reconciled.
"""
from __future__ import annotations

from typing import Any, Dict

from .base import DraftAdapter, TraceSummary, assert_flat
from .validation import (
    SERVICENOW_IMPACT_URGENCY,
    SERVICENOW_SHORT_DESCRIPTION_MAX,
    cap,
    validate_choice,
)

__all__ = ["ServiceNowAdapter", "build_incident_draft"]


def build_incident_draft(
    summary: TraceSummary,
    *,
    category: str = "software",
    subcategory: str = "portal",
    impact: str = "3",
    urgency: str = "3",
) -> Dict[str, Any]:
    """Build a flat ServiceNow incident draft from a sanitized summary.

    ``impact``/``urgency`` are validated against the allowed scale and
    ``short_description`` is capped to ServiceNow's stock limit, so the connector never has
    to silently reject or truncate the record.
    """
    validate_choice(impact, SERVICENOW_IMPACT_URGENCY, field="impact")
    validate_choice(urgency, SERVICENOW_IMPACT_URGENCY, field="urgency")
    short_description, sd_truncated = cap(
        summary.headline, SERVICENOW_SHORT_DESCRIPTION_MAX
    )
    work_notes = (
        f"Replayability score: {summary.replayability_score:.2f} "
        f"(grade {summary.replayability_grade}). "
        "Playwright repro available internally. "
        f"Privacy: {summary.privacy_status}."
    )
    if sd_truncated:
        work_notes += (
            f" (short_description truncated to {SERVICENOW_SHORT_DESCRIPTION_MAX} chars.)"
        )
    draft = {
        "short_description": short_description,
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
