"""Slack message DRAFT adapter (flat, sanitized).

Not a Slack API client. Builds a safe, flat message payload a host can post via its own
Slack app/webhook — the notification-oriented counterpart to the ticketing adapters, for
teams that triage a bug report in a channel before (or instead of) filing a ticket.
"""
from __future__ import annotations

from typing import Any, Dict

from .base import DraftAdapter, TraceSummary, assert_flat
from .validation import SLACK_TEXT_MAX, cap

__all__ = ["SlackAdapter", "build_slack_message_draft"]


def _severity_marker(summary: TraceSummary) -> str:
    if (summary.failing_status or 0) >= 500 or summary.exception_type is not None:
        return ":red_circle:"
    return ":large_yellow_circle:"


def build_slack_message_draft(
    summary: TraceSummary,
    *,
    channel: str = "#bugs",
) -> Dict[str, Any]:
    """Build a flat Slack message draft from a sanitized summary.

    ``text`` is capped to Slack's stock text-block limit so a long route template never
    silently truncates elsewhere in the pipeline.
    """
    text = (
        f"{_severity_marker(summary)} *{summary.headline}*\n"
        f"Route: `{summary.route}` · Replayability {summary.replayability_score:.2f} "
        f"(grade {summary.replayability_grade}) · Privacy: {summary.privacy_status}\n"
        f"Correlation: stepstitch:{summary.trace_id}"
    )
    text, _truncated = cap(text, SLACK_TEXT_MAX)
    draft = {
        "channel": channel,
        "text": text,
        "unfurl_links": False,
        "external_id": f"stepstitch:{summary.trace_id}",
    }
    return assert_flat(draft)


class SlackAdapter(DraftAdapter):
    name = "slack"

    def __init__(self, *, channel: str = "#bugs") -> None:
        self.channel = channel

    def build_draft(self, summary: TraceSummary) -> Dict[str, Any]:
        return build_slack_message_draft(summary, channel=self.channel)
