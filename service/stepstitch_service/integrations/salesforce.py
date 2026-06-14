"""Salesforce Case DRAFT adapter (flat, sanitized).

The Salesforce connector rejects nested complex objects and prefers flat structures, so
this draft is deliberately flat scalars only. It carries the trace id, route template,
replayability score, and privacy status as custom fields — never raw footsteps, the
explanation, the user id, page text, or bodies. The repro link is internal-only.
"""
from __future__ import annotations

from typing import Any, Dict

from .base import DraftAdapter, TraceSummary, assert_flat
from .validation import (
    SALESFORCE_PRIORITY,
    SALESFORCE_SUBJECT_MAX,
    cap,
    validate_choice,
)

__all__ = ["SalesforceAdapter", "build_case_draft"]


def _priority(summary: TraceSummary) -> str:
    if summary.failing_status is not None and summary.failing_status >= 500:
        return "High"
    if summary.exception_type is not None:
        return "High"
    return "Medium"


def build_case_draft(summary: TraceSummary) -> Dict[str, Any]:
    """Build a flat Salesforce Case draft from a sanitized summary.

    ``Priority`` is validated against the stock picklist and ``Subject`` is capped to
    Salesforce's 255-char limit, so the connector never silently rejects or truncates.
    """
    subject, _ = cap(summary.headline, SALESFORCE_SUBJECT_MAX)
    draft = {
        "Subject": subject,
        "Origin": "StepStitch",
        "Status": "New",
        "Priority": validate_choice(
            _priority(summary), SALESFORCE_PRIORITY, field="Priority"
        ),
        "StepStitchTraceId__c": summary.trace_id,
        "RouteTemplate__c": summary.route,
        "ReplayabilityScore__c": summary.replayability_score,
        "ReplayabilityGrade__c": summary.replayability_grade,
        "PrivacyStatus__c": summary.privacy_status,
        "PlaywrightReproLink__c": "internal-link-only",
    }
    return assert_flat(draft)


class SalesforceAdapter(DraftAdapter):
    name = "salesforce"

    def build_draft(self, summary: TraceSummary) -> Dict[str, Any]:
        return build_case_draft(summary)
