"""GitHub issue/PR CONTENT (pure, privacy-safe).

Derived only from the sanitized ``TraceSummary`` — never raw footsteps, the explanation, or
the user id. Same privacy seam as the draft adapters.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List

from ..integrations.base import TraceSummary

LABEL_BASE = "stepstitch"
LABEL_PRIVACY = "privacy-safe"
LABEL_REPRO_READY = "stepstitch:repro-ready"
LABEL_NEEDS_DATA = "stepstitch:needs-data"
LABEL_NEEDS_FIX = "stepstitch:needs-fix"
LABEL_FIX_CANDIDATE = "stepstitch:fix-candidate"
# Vocabulary applied by the customer's CI workflow / review process, NOT by the bridge
# itself (the bridge applies the labels above). Defined here as the single source of the
# label names so the workflow template and docs stay in sync.
LABEL_CONFIRMED = "stepstitch:confirmed-repro"
LABEL_REGRESSION_ADDED = "stepstitch:regression-added"
LABEL_READY_FOR_REVIEW = "stepstitch:ready-for-review"


def repro_labels(summary: TraceSummary) -> List[str]:
    """Labels for a freshly bridged trace, gated on the replayability grade."""
    labels = [LABEL_BASE, LABEL_PRIVACY, LABEL_NEEDS_FIX]
    if summary.replayability_grade in ("A", "B"):
        labels.append(LABEL_REPRO_READY)
    else:
        labels.append(LABEL_NEEDS_DATA)
    return labels


def branch_name(trace_id: str) -> str:
    return f"stepstitch/trace-{trace_id}"


def regression_test_path(trace_id: str) -> str:
    return f"tests/stepstitch/repro_{trace_id}.spec.ts"


@dataclass(frozen=True)
class IssueContent:
    title: str
    body: str
    labels: List[str]


def build_body(summary: TraceSummary) -> str:
    """The privacy-safe issue/PR body text, derived only from the sanitized summary."""
    return (
        "Reported issue reproduced by StepStitch (privacy-safe; no NPI captured).\n\n"
        f"- **Route:** `{summary.route}`\n"
        f"- **Replayability:** {summary.replayability_score:.2f} "
        f"(grade {summary.replayability_grade})\n"
        f"- **Steps:** {summary.step_count}\n"
        f"- **Privacy:** {summary.privacy_status}\n"
        f"- **Trace correlation id:** `stepstitch:{summary.trace_id}`\n\n"
        "A deterministic Playwright reproduction is available from StepStitch and can be "
        "committed as a regression test. StepStitch never merges — a human reviews and merges."
    )


def build_issue(summary: TraceSummary) -> IssueContent:
    return IssueContent(
        title=f"[StepStitch] {summary.headline}",
        body=build_body(summary),
        labels=repro_labels(summary),
    )
