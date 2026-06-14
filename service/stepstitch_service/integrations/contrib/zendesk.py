"""Reference Zendesk ticket DRAFT adapter (Apache-2.0).

A worked example of the connector SDK. Register via the ``stepstitch.adapters`` entry point
or inject explicitly.
"""
from __future__ import annotations

from typing import Any, Dict

from ..base import DraftAdapter, TraceSummary, assert_flat
from ..validation import cap

_SUBJECT_MAX = 150
_PRIORITY = frozenset({"low", "normal", "high", "urgent"})


class ZendeskAdapter(DraftAdapter):
    name = "zendesk"

    def build_draft(self, summary: TraceSummary) -> Dict[str, Any]:
        subject, _ = cap(summary.headline, _SUBJECT_MAX)
        urgent = (summary.failing_status or 0) >= 500 or summary.exception_type is not None
        priority = "urgent" if urgent else "normal"
        assert priority in _PRIORITY  # invariant: stays in the stock picklist
        draft = {
            "subject": subject,
            "comment_body": (
                f"Sanitized StepStitch summary. Route: {summary.route}. "
                f"Replayability {summary.replayability_score:.2f} "
                f"(grade {summary.replayability_grade}). Privacy: {summary.privacy_status}."
            ),
            "priority": priority,
            "tags": "stepstitch",
            "external_id": f"stepstitch:{summary.trace_id}",
        }
        return assert_flat(draft)
