"""Reference Jira issue DRAFT adapter (Apache-2.0).

A worked example of the connector SDK: build a flat, sanitized draft from a TraceSummary.
Not wired in by default — register it via the ``stepstitch.adapters`` entry point or inject
it explicitly with ``create_stepstitch_router(draft_adapters=[..., JiraAdapter()])``.
"""
from __future__ import annotations

from typing import Any, Dict

from ..base import DraftAdapter, TraceSummary, assert_flat
from ..validation import cap

_SUMMARY_MAX = 255


class JiraAdapter(DraftAdapter):
    name = "jira"

    def __init__(self, *, project_key: str = "SUP", issue_type: str = "Bug") -> None:
        self.project_key = project_key
        self.issue_type = issue_type

    def build_draft(self, summary: TraceSummary) -> Dict[str, Any]:
        summary_text, _ = cap(summary.headline, _SUMMARY_MAX)
        draft = {
            "project_key": self.project_key,
            "issuetype": self.issue_type,
            "summary": summary_text,
            "description": (
                f"Sanitized StepStitch summary. Route: {summary.route}. "
                f"Replayability {summary.replayability_score:.2f} "
                f"(grade {summary.replayability_grade}). "
                f"Steps: {summary.step_count}. Privacy: {summary.privacy_status}."
            ),
            "labels": "stepstitch",
            "stepstitch_trace_id": summary.trace_id,
        }
        return assert_flat(draft)
