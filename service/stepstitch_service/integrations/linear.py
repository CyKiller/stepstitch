"""Linear issue DRAFT adapter (flat, sanitized).

Linear is one of the most common issue trackers for indie/OSS teams — this fills the gap
left by StepStitch's previously enterprise-only (ServiceNow/Salesforce/Genesys) adapter set.
"""
from __future__ import annotations

from typing import Any, Dict

from .base import DraftAdapter, TraceSummary, assert_flat
from .validation import LINEAR_PRIORITY, LINEAR_TITLE_MAX, cap, validate_choice

__all__ = ["LinearAdapter", "build_linear_issue_draft"]


def _priority(summary: TraceSummary) -> str:
    # Linear's numeric scale: 1=Urgent, 2=High, 3=Normal, 4=Low, 0=No priority.
    if summary.failing_status is not None and summary.failing_status >= 500:
        return "1"
    if summary.exception_type is not None:
        return "2"
    return "3"


def build_linear_issue_draft(
    summary: TraceSummary,
    *,
    team_key: str = "SUP",
) -> Dict[str, Any]:
    """Build a flat Linear issue draft from a sanitized summary.

    ``priority`` is validated against Linear's stock numeric scale and ``title`` is capped,
    so the connector never has to silently reject or truncate the record.
    """
    title, truncated = cap(summary.headline, LINEAR_TITLE_MAX)
    priority = validate_choice(_priority(summary), LINEAR_PRIORITY, field="priority")
    description = (
        f"Sanitized StepStitch summary. Route: {summary.route}. "
        f"Replayability {summary.replayability_score:.2f} "
        f"(grade {summary.replayability_grade}). "
        f"Steps: {summary.step_count}. Privacy: {summary.privacy_status}."
    )
    if truncated:
        description += f" (title truncated to {LINEAR_TITLE_MAX} chars.)"
    draft = {
        "team_key": team_key,
        "title": title,
        "description": description,
        "priority": priority,
        "labels": "stepstitch",
        "external_id": f"stepstitch:{summary.trace_id}",
    }
    return assert_flat(draft)


class LinearAdapter(DraftAdapter):
    name = "linear"

    def __init__(self, *, team_key: str = "SUP") -> None:
        self.team_key = team_key

    def build_draft(self, summary: TraceSummary) -> Dict[str, Any]:
        return build_linear_issue_draft(summary, team_key=self.team_key)
