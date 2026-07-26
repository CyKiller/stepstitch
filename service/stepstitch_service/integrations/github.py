"""GitHub Issues DRAFT adapter (flat, sanitized).

Builds a draft GitHub issue from a sanitized trace summary — the general-purpose
"file a ticket in GitHub" connector for any team already living there, distinct from the
human-gated Repair Loop (``github_bridge/``), which opens issues about StepStitch's own
findings against this repo. Same draft-only, no-agent-write posture as every other adapter.
"""
from __future__ import annotations

from typing import Any, Dict

from .base import DraftAdapter, TraceSummary, assert_flat
from .validation import GITHUB_TITLE_MAX, cap

__all__ = ["GitHubIssuesAdapter", "build_github_issue_draft"]


def build_github_issue_draft(
    summary: TraceSummary,
    *,
    labels: str = "stepstitch,bug",
) -> Dict[str, Any]:
    """Build a flat GitHub issue draft from a sanitized summary.

    ``title`` is capped so a long route template never silently truncates elsewhere in
    the pipeline; the cut is marked in ``body``, never silent.
    """
    title, truncated = cap(summary.headline, GITHUB_TITLE_MAX)
    body = (
        "**Sanitized StepStitch summary** — no screens, field values, raw URLs, or page "
        "text.\n\n"
        f"- Route template: `{summary.route}`\n"
        f"- Replayability: {summary.replayability_score:.2f} "
        f"(grade {summary.replayability_grade})\n"
        f"- Steps captured: {summary.step_count}\n"
        f"- Privacy: {summary.privacy_status}\n\n"
        f"_Correlation: stepstitch:{summary.trace_id}_"
    )
    if truncated:
        body += f"\n\n_(title truncated to {GITHUB_TITLE_MAX} chars)_"
    draft = {
        "title": title,
        "body": body,
        "labels": labels,
        "external_id": f"stepstitch:{summary.trace_id}",
    }
    return assert_flat(draft)


class GitHubIssuesAdapter(DraftAdapter):
    # Not "github" — the demo bundle and any host that also wires in the Repair Loop
    # (`github_bridge/`, contracts/stepstitch.md's `/github/issue` + `/github/pr`) already
    # uses that key for its dry-run issue/PR preview. This adapter is a distinct,
    # general-purpose "file a ticket in GitHub" draft, so it gets a distinct name.
    name = "github_issues"

    def __init__(self, *, labels: str = "stepstitch,bug") -> None:
        self.labels = labels

    def build_draft(self, summary: TraceSummary) -> Dict[str, Any]:
        return build_github_issue_draft(summary, labels=self.labels)
