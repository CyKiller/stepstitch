"""Zendesk ticket DRAFT adapter (flat, sanitized) — bundled by default.

Built to the same bar as the ServiceNow/Salesforce/Genesys adapters (field caps, validated
enums, deterministic output). Kept in ``contrib/`` for import-path continuity and because it
doubles as the worked reference for `docs/connectors.md`'s "write your own adapter" guide.
"""
from __future__ import annotations

from typing import Any, Dict

from ..base import DraftAdapter, TraceSummary, assert_flat
from ..validation import (
    ZENDESK_PRIORITY,
    ZENDESK_SUBJECT_MAX,
    ZENDESK_TYPE,
    cap,
    validate_choice,
)

__all__ = ["ZendeskAdapter", "build_zendesk_ticket_draft"]


def _priority(summary: TraceSummary) -> str:
    if summary.failing_status is not None and summary.failing_status >= 500:
        return "urgent"
    if summary.exception_type is not None:
        return "high"
    return "normal"


def build_zendesk_ticket_draft(
    summary: TraceSummary,
    *,
    ticket_type: str = "problem",
) -> Dict[str, Any]:
    """Build a flat Zendesk ticket draft from a sanitized summary.

    ``type``/``priority`` are validated against the stock picklists and ``subject`` is
    capped, so the connector never has to silently reject or truncate the record.
    """
    validate_choice(ticket_type, ZENDESK_TYPE, field="type")
    subject, truncated = cap(summary.headline, ZENDESK_SUBJECT_MAX)
    priority = validate_choice(_priority(summary), ZENDESK_PRIORITY, field="priority")
    comment_body = (
        f"Sanitized StepStitch summary. Route: {summary.route}. "
        f"Replayability {summary.replayability_score:.2f} "
        f"(grade {summary.replayability_grade}). "
        f"Steps: {summary.step_count}. Privacy: {summary.privacy_status}."
    )
    if truncated:
        comment_body += f" (subject truncated to {ZENDESK_SUBJECT_MAX} chars.)"
    draft = {
        "subject": subject,
        "comment_body": comment_body,
        "priority": priority,
        "type": ticket_type,
        "tags": "stepstitch",
        "external_id": f"stepstitch:{summary.trace_id}",
    }
    return assert_flat(draft)


class ZendeskAdapter(DraftAdapter):
    name = "zendesk"

    def __init__(self, *, ticket_type: str = "problem") -> None:
        self.ticket_type = ticket_type

    def build_draft(self, summary: TraceSummary) -> Dict[str, Any]:
        return build_zendesk_ticket_draft(summary, ticket_type=self.ticket_type)
