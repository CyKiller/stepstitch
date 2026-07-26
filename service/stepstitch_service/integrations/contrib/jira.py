"""Jira issue DRAFT adapter (flat, sanitized) — bundled by default.

Built to the same bar as the ServiceNow/Salesforce/Genesys adapters (field caps, validated
enums, deterministic output). Kept in ``contrib/`` for import-path continuity and because it
doubles as the worked reference for `docs/connectors.md`'s "write your own adapter" guide.
"""
from __future__ import annotations

from typing import Any, Dict

from ..base import DraftAdapter, TraceSummary, assert_flat
from ..validation import JIRA_ISSUE_TYPES, JIRA_SUMMARY_MAX, cap, validate_choice

__all__ = ["JiraAdapter", "build_jira_issue_draft"]


def build_jira_issue_draft(
    summary: TraceSummary,
    *,
    project_key: str = "SUP",
    issue_type: str = "Bug",
) -> Dict[str, Any]:
    """Build a flat Jira issue draft from a sanitized summary.

    ``issuetype`` is validated against the stock type set and ``summary`` is capped to
    Jira's field limit, so the connector never has to silently reject or truncate the
    record.
    """
    validate_choice(issue_type, JIRA_ISSUE_TYPES, field="issuetype")
    summary_text, truncated = cap(summary.headline, JIRA_SUMMARY_MAX)
    description = (
        f"Sanitized StepStitch summary. Route: {summary.route}. "
        f"Replayability {summary.replayability_score:.2f} "
        f"(grade {summary.replayability_grade}). "
        f"Steps: {summary.step_count}. Privacy: {summary.privacy_status}."
    )
    if truncated:
        description += f" (summary truncated to {JIRA_SUMMARY_MAX} chars.)"
    draft = {
        "project_key": project_key,
        "issuetype": issue_type,
        "summary": summary_text,
        "description": description,
        "labels": "stepstitch",
        "stepstitch_trace_id": summary.trace_id,
    }
    return assert_flat(draft)


class JiraAdapter(DraftAdapter):
    name = "jira"

    def __init__(self, *, project_key: str = "SUP", issue_type: str = "Bug") -> None:
        self.project_key = project_key
        self.issue_type = issue_type

    def build_draft(self, summary: TraceSummary) -> Dict[str, Any]:
        return build_jira_issue_draft(
            summary, project_key=self.project_key, issue_type=self.issue_type
        )
