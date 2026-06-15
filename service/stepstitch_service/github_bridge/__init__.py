"""StepStitch Repair Loop — optional GitHub bridge (Apache-2.0, off by default).

Turns a reproduced trace into a labeled GitHub issue + a regression-test PR. Mirrors the
delivery/ pattern: credentials live in a host-injected closure, never in core; governed,
audited, human-merged; never on the agent/MCP surface. There is no merge capability.
"""
from .content import IssueContent, build_issue, branch_name, regression_test_path, repro_labels

__all__ = [
    "IssueContent",
    "build_issue",
    "branch_name",
    "regression_test_path",
    "repro_labels",
]
