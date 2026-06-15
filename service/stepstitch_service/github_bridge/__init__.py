"""StepStitch Repair Loop — optional GitHub bridge (Apache-2.0, off by default).

Turns a reproduced trace into a labeled GitHub issue + a regression-test PR. Mirrors the
delivery/ pattern: credentials live in a host-injected closure, never in core; governed,
audited, human-merged; never on the agent/MCP surface. There is no merge capability.
"""
from .bridge import BridgeReceipt, GitHubBridge
from .client import BridgeError, GitHubClient, GitHubRequestFn
from .content import IssueContent, build_body, build_issue, branch_name, regression_test_path, repro_labels
from .workflow import STEPSTITCH_REPRO_WORKFLOW

# Reference HTTP client needs the optional [github] extra (httpx); import lazily.
try:  # pragma: no cover - exercised via the [github] extra
    from .client import github_token_request
except Exception:  # noqa: BLE001
    github_token_request = None  # type: ignore

__all__ = [
    "GitHubBridge",
    "BridgeReceipt",
    "GitHubClient",
    "GitHubRequestFn",
    "BridgeError",
    "github_token_request",
    "IssueContent",
    "build_body",
    "build_issue",
    "branch_name",
    "regression_test_path",
    "repro_labels",
    "STEPSTITCH_REPRO_WORKFLOW",
]
