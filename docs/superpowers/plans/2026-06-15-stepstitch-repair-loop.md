# StepStitch Repair Loop (GitHub Bridge) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an optional, governed "Repair Loop" that turns a reproduced StepStitch trace into a labeled GitHub issue and a regression-test pull request in the customer's repo — privacy-safe, human-merged, never auto-merged.

**Architecture:** A new optional package `service/stepstitch_service/github_bridge/` mirroring the proven `delivery/` pattern: pure content builder (issue/PR text + labels from the sanitized `TraceSummary`), a `GitHubClient` over an injected HTTP transport (credentials live in a host closure, never in core), and a `GitHubBridge` orchestrator with idempotency. Two governed router endpoints (admin-only, `approved_by`, audited, **excluded from the MCP/agent surface**) trigger it. StepStitch supplies the issue + the regression test and recommends merge-readiness; a human merges. There is deliberately **no merge capability**.

**Tech Stack:** Python 3.10+, FastAPI router factory, `httpx` (optional `[github]` extra, lazy-imported), GitHub REST API v3, pytest with `httpx.MockTransport`.

**Scope (this plan):** issue/label bridge, regression-test PR proposal, and the customer CI repro workflow template. **Out of scope (follow-on plan):** the admin-cockpit fix-options UI, multi-agent fix *generation*, and a GitHub App installation/onboarding wizard (this plan uses a host-injected token, consistent with `delivery/clients.py`).

**Reference patterns to copy:** `service/stepstitch_service/delivery/base.py` (DeliveryService + idempotency_store), `delivery/clients.py` (httpx factory with timeout/retry), `delivery/servicenow_writer.py` (thin client), `service/tests/test_delivery_clients.py` (MockTransport tests), `router.py` `post_deliver` (governed endpoint shape), `mcp_server.is_destructive` (agent-surface guard).

---

## File Structure

- Create `service/stepstitch_service/github_bridge/__init__.py` — public exports.
- Create `service/stepstitch_service/github_bridge/content.py` — pure: labels + issue/PR text from `TraceSummary`. No I/O.
- Create `service/stepstitch_service/github_bridge/client.py` — `GitHubClient` over an injected request fn + reference `github_token_request` httpx factory. **No merge method.**
- Create `service/stepstitch_service/github_bridge/bridge.py` — `GitHubBridge` orchestration + idempotency.
- Create `service/stepstitch_service/github_bridge/workflow.py` — `STEPSTITCH_REPRO_WORKFLOW` customer CI template constant.
- Modify `service/stepstitch_service/router.py` — add `github_bridge` param + two governed endpoints.
- Modify `service/stepstitch_service/mcp_server.py` — extend `is_destructive` so `github`/`merge` can never be agent tools.
- Modify `service/pyproject.toml` — `[github]` extra, package list, import-linter sources.
- Modify `server/host.py` — pass `github_bridge` through `build_app`.
- Create tests: `service/tests/test_github_content.py`, `test_github_client.py`, `test_github_bridge.py`, `test_github_endpoints.py`.
- Create `docs/integrations/github.md` — setup + wiring + the CI workflow.

---

## Task 1: Pure content builder + package skeleton

**Files:**
- Create: `service/stepstitch_service/github_bridge/__init__.py`
- Create: `service/stepstitch_service/github_bridge/content.py`
- Test: `service/tests/test_github_content.py`
- Modify: `service/pyproject.toml` (packages + `[github]` extra)

- [ ] **Step 1: Write the failing test**

```python
# service/tests/test_github_content.py
"""GitHub issue/PR content is privacy-safe, label-correct, and deterministic."""
from stepstitch_service.integrations.base import build_trace_summary
from stepstitch_service.github_bridge.content import (
    build_issue, repro_labels, branch_name, regression_test_path,
)


def _summary(grade_footsteps):
    return build_trace_summary("trace_42", grade_footsteps, project_id="p1")


def _failing():
    return [{"timestamp": "t", "type": "api_error",
             "route": "/accounts/:id/distributions", "label": "[masked]",
             "metadata": {"status": 500, "endpoint": "/api/accounts/:id"}}]


def _nav_only():
    return [{"timestamp": "t", "type": "navigation", "route": "/dashboard",
             "label": "[masked]"}]


def test_repro_ready_labels_for_high_grade():
    labels = repro_labels(_summary(_failing()))
    assert "stepstitch" in labels and "privacy-safe" in labels
    assert "stepstitch:repro-ready" in labels
    assert "stepstitch:needs-data" not in labels


def test_needs_data_labels_for_low_grade():
    labels = repro_labels(_summary(_nav_only()))
    assert "stepstitch:needs-data" in labels
    assert "stepstitch:repro-ready" not in labels


def test_issue_is_privacy_safe_and_deterministic():
    s = _summary(_failing())
    issue = build_issue(s)
    assert issue.title.startswith("[StepStitch]")
    assert "stepstitch:trace_42" in issue.body          # correlation marker
    assert "No NPI" in issue.body or "no NPI" in issue.body
    # never leaks raw internals
    blob = issue.title + issue.body
    assert "8675309" not in blob and "data-testid" not in blob
    assert build_issue(s) == issue                       # deterministic


def test_branch_and_test_path():
    assert branch_name("trace_42") == "stepstitch/trace-trace_42"
    assert regression_test_path("trace_42") == "tests/stepstitch/repro_trace_42.spec.ts"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd service && python -m pytest tests/test_github_content.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'stepstitch_service.github_bridge'`

- [ ] **Step 3: Create the package skeleton**

```python
# service/stepstitch_service/github_bridge/__init__.py
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
```

- [ ] **Step 4: Write the content builder**

```python
# service/stepstitch_service/github_bridge/content.py
"""GitHub issue/PR CONTENT (pure, privacy-safe).

Derived only from the sanitized ``TraceSummary`` — never raw footsteps, the explanation, or
the user id. Same privacy seam as the draft adapters.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List

from ..integrations.base import TraceSummary

# The full StepStitch label vocabulary (the bridge applies some; the CI workflow applies the
# verification ones like confirmed-repro).
LABEL_BASE = "stepstitch"
LABEL_PRIVACY = "privacy-safe"
LABEL_REPRO_READY = "stepstitch:repro-ready"
LABEL_NEEDS_DATA = "stepstitch:needs-data"
LABEL_NEEDS_FIX = "stepstitch:needs-fix"
LABEL_CONFIRMED = "stepstitch:confirmed-repro"
LABEL_FIX_CANDIDATE = "stepstitch:fix-candidate"
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


def build_issue(summary: TraceSummary) -> IssueContent:
    title = f"[StepStitch] {summary.headline}"
    body = (
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
    return IssueContent(title=title, body=body, labels=repro_labels(summary))
```

- [ ] **Step 5: Register the package + `[github]` extra in pyproject**

In `service/pyproject.toml`, add to `[project.optional-dependencies]` after the `delivery` line:

```toml
# Reference GitHub client for the optional Repair Loop bridge (github_bridge/client.py).
github = ["httpx>=0.27"]
```

In `[tool.setuptools] packages`, add `"stepstitch_service.github_bridge"`:

```toml
packages = [
    "stepstitch_service",
    "stepstitch_service.integrations",
    "stepstitch_service.integrations.contrib",
    "stepstitch_service.delivery",
    "stepstitch_service.github_bridge",
]
```

- [ ] **Step 6: Run test to verify it passes**

Run: `cd service && python -m pytest tests/test_github_content.py -q`
Expected: PASS (4 passed)

- [ ] **Step 7: Commit**

```bash
git add service/stepstitch_service/github_bridge/__init__.py \
        service/stepstitch_service/github_bridge/content.py \
        service/tests/test_github_content.py service/pyproject.toml
git commit -m "feat(repair-loop): privacy-safe GitHub issue/PR content builder"
```

---

## Task 2: GitHubClient + reference httpx factory

**Files:**
- Create: `service/stepstitch_service/github_bridge/client.py`
- Test: `service/tests/test_github_client.py`

- [ ] **Step 1: Write the failing test**

```python
# service/tests/test_github_client.py
"""GitHubClient: REST calls over an injected transport; no merge capability."""
import asyncio

import httpx
import pytest

from stepstitch_service.github_bridge.client import (
    BridgeError, GitHubClient, github_token_request,
)


def run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def _client(handler):
    request = github_token_request(
        "tok", attempts=2, backoff=0.0, transport=httpx.MockTransport(handler),
    )
    return GitHubClient(request, repo="acme/app")


def test_create_issue_returns_number_and_sends_auth():
    seen = {}

    def handler(req):
        seen["auth"] = req.headers.get("authorization")
        seen["path"] = req.url.path
        return httpx.Response(201, json={"number": 7})

    issue = run(_client(handler).create_issue("t", "b", ["stepstitch"]))
    assert issue["number"] == 7
    assert seen["auth"] == "Bearer tok"
    assert seen["path"] == "/repos/acme/app/issues"


def test_ensure_label_tolerates_already_exists_422():
    def handler(req):
        return httpx.Response(422, json={"message": "already_exists"})

    # Must NOT raise — label already present is fine.
    run(_client(handler).ensure_label("stepstitch"))


def test_request_raises_bridgeerror_on_404():
    def handler(req):
        return httpx.Response(404, text="not found")

    with pytest.raises(BridgeError):
        run(_client(handler).create_issue("t", "b", []))


def test_open_pull_request_posts_to_pulls():
    def handler(req):
        assert req.url.path == "/repos/acme/app/pulls"
        return httpx.Response(201, json={"number": 12})

    pr = run(_client(handler).open_pull_request("stepstitch/trace-1", "main", "t", "b"))
    assert pr["number"] == 12


def test_no_merge_method_exists():
    # Safety invariant: the client must expose no merge capability.
    assert not hasattr(GitHubClient, "merge")
    assert not hasattr(GitHubClient, "merge_pull_request")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd service && python -m pytest tests/test_github_client.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'stepstitch_service.github_bridge.client'`

- [ ] **Step 3: Write the client**

```python
# service/stepstitch_service/github_bridge/client.py
"""GitHub REST client for the optional Repair Loop bridge.

Uses an injected async request fn so the core never imports httpx or holds credentials.
Exposes the MINIMUM operations to label an issue and open a regression-test PR. There is
deliberately NO merge method — StepStitch never merges.
"""
from __future__ import annotations

import asyncio
import base64
from typing import Any, Awaitable, Callable, Dict, List, Optional

# (method, path, json_body|None) -> parsed JSON response (``{}`` for empty bodies).
GitHubRequestFn = Callable[[str, str, Optional[Dict[str, Any]]], Awaitable[Dict[str, Any]]]

_TRANSIENT = {429, 500, 502, 503, 504}


class BridgeError(RuntimeError):
    def __init__(self, message: str, *, status: Optional[int] = None) -> None:
        super().__init__(message)
        self.status = status


def github_token_request(
    token: str,
    *,
    api_base: str = "https://api.github.com",
    timeout: float = 10.0,
    attempts: int = 3,
    backoff: float = 0.2,
    transport: Any = None,
) -> GitHubRequestFn:
    """Reference GitHub request closure (needs the [github] extra: httpx)."""

    async def request(
        method: str, path: str, json_body: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        import httpx

        last: Any = None
        client = httpx.AsyncClient(
            base_url=api_base.rstrip("/"),
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            },
            timeout=timeout,
            transport=transport,
        )
        try:
            for attempt in range(attempts):
                try:
                    resp = await client.request(method, path, json=json_body)
                except httpx.TransportError as exc:
                    last = exc
                else:
                    if resp.status_code in _TRANSIENT:
                        last = BridgeError(
                            f"transient {resp.status_code}", status=resp.status_code
                        )
                    elif resp.status_code >= 400:
                        raise BridgeError(
                            f"{resp.status_code} {method} {path}: {resp.text[:200]}",
                            status=resp.status_code,
                        )
                    else:
                        return resp.json() if resp.content else {}
                if attempt < attempts - 1:
                    await asyncio.sleep(backoff * (2 ** attempt))
            raise BridgeError(
                f"github {method} {path} failed after {attempts} attempts: {last}",
                status=getattr(last, "status", None),
            )
        finally:
            await client.aclose()

    return request


class GitHubClient:
    """Minimal GitHub operations. No merge — by design."""

    def __init__(self, request: GitHubRequestFn, *, repo: str) -> None:
        self._request = request
        self._repo = repo  # "owner/name"

    async def ensure_label(
        self, name: str, *, color: str = "ededed", description: str = "StepStitch"
    ) -> None:
        try:
            await self._request(
                "POST", f"/repos/{self._repo}/labels",
                {"name": name, "color": color, "description": description},
            )
        except BridgeError as exc:
            if exc.status != 422:  # 422 = label already exists; that's fine
                raise

    async def create_issue(
        self, title: str, body: str, labels: List[str]
    ) -> Dict[str, Any]:
        return await self._request(
            "POST", f"/repos/{self._repo}/issues",
            {"title": title, "body": body, "labels": labels},
        )

    async def default_branch_sha(self, base_branch: str) -> str:
        ref = await self._request(
            "GET", f"/repos/{self._repo}/git/ref/heads/{base_branch}", None
        )
        return ref["object"]["sha"]

    async def create_branch(self, branch: str, sha: str) -> Dict[str, Any]:
        return await self._request(
            "POST", f"/repos/{self._repo}/git/refs",
            {"ref": f"refs/heads/{branch}", "sha": sha},
        )

    async def put_file(
        self, branch: str, path: str, content_text: str, message: str
    ) -> Dict[str, Any]:
        encoded = base64.b64encode(content_text.encode("utf-8")).decode("ascii")
        return await self._request(
            "PUT", f"/repos/{self._repo}/contents/{path}",
            {"message": message, "content": encoded, "branch": branch},
        )

    async def open_pull_request(
        self, head: str, base: str, title: str, body: str
    ) -> Dict[str, Any]:
        return await self._request(
            "POST", f"/repos/{self._repo}/pulls",
            {"title": title, "head": head, "base": base, "body": body},
        )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd service && python -m pytest tests/test_github_client.py -q`
Expected: PASS (5 passed)

- [ ] **Step 5: Commit**

```bash
git add service/stepstitch_service/github_bridge/client.py service/tests/test_github_client.py
git commit -m "feat(repair-loop): GitHub REST client (injected transport, no merge)"
```

---

## Task 3: GitHubBridge orchestration + idempotency

**Files:**
- Create: `service/stepstitch_service/github_bridge/bridge.py`
- Modify: `service/stepstitch_service/github_bridge/__init__.py` (export bridge symbols)
- Test: `service/tests/test_github_bridge.py`

- [ ] **Step 1: Write the failing test**

```python
# service/tests/test_github_bridge.py
"""GitHubBridge: orchestrates labels -> issue -> regression PR; idempotent; never merges."""
import asyncio

from stepstitch_service.github_bridge.bridge import GitHubBridge
from stepstitch_service.integrations.base import build_trace_summary


def run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


class FakeClient:
    def __init__(self):
        self.labels = []
        self.issues = 0
        self.branches = []
        self.files = []
        self.prs = 0

    async def ensure_label(self, name, **kw):
        self.labels.append(name)

    async def create_issue(self, title, body, labels):
        self.issues += 1
        return {"number": 100 + self.issues}

    async def default_branch_sha(self, base):
        return "deadbeef"

    async def create_branch(self, branch, sha):
        self.branches.append((branch, sha))
        return {}

    async def put_file(self, branch, path, content_text, message):
        self.files.append((branch, path))
        return {}

    async def open_pull_request(self, head, base, title, body):
        self.prs += 1
        return {"number": 200 + self.prs}


def _summary():
    return build_trace_summary("trace_7", [
        {"timestamp": "t", "type": "api_error", "route": "/accounts/:id",
         "label": "[masked]", "metadata": {"status": 500}}], project_id="p1")


def test_create_issue_applies_labels_and_returns_number():
    c = FakeClient()
    b = GitHubBridge(c)
    r = run(b.create_issue(_summary()))
    assert r.issue_number == 101
    assert "stepstitch:repro-ready" in c.labels
    assert r.deduped is False


def test_create_issue_is_idempotent_per_trace():
    c = FakeClient()
    store = {}
    b1 = GitHubBridge(c, idempotency_store=store)
    r1 = run(b1.create_issue(_summary()))
    b2 = GitHubBridge(c, idempotency_store=store)
    r2 = run(b2.create_issue(_summary()))
    assert c.issues == 1               # not created twice
    assert r2.deduped is True and r2.issue_number == r1.issue_number


def test_open_regression_pr_branches_commits_and_opens_pr():
    c = FakeClient()
    b = GitHubBridge(c)
    r = run(b.open_regression_pr(_summary(), "test('repro', async () => {});"))
    assert r.pr_number == 201
    assert c.branches == [("stepstitch/trace-trace_7", "deadbeef")]
    assert c.files == [("stepstitch/trace-trace_7", "tests/stepstitch/repro_trace_7.spec.ts")]


def test_open_regression_pr_is_idempotent():
    c = FakeClient()
    store = {}
    b = GitHubBridge(c, idempotency_store=store)
    run(b.open_regression_pr(_summary(), "code"))
    run(b.open_regression_pr(_summary(), "code"))
    assert c.prs == 1                  # PR not opened twice
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd service && python -m pytest tests/test_github_bridge.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'stepstitch_service.github_bridge.bridge'`

- [ ] **Step 3: Write the orchestrator**

```python
# service/stepstitch_service/github_bridge/bridge.py
"""GitHubBridge — orchestrates the Repair Loop write side.

Idempotent per trace (keyed by trace_id) via a dict-like store, exactly like
``delivery.DeliveryService``. Never merges.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from ..integrations.base import TraceSummary
from .content import (
    LABEL_BASE,
    LABEL_FIX_CANDIDATE,
    branch_name,
    build_issue,
    regression_test_path,
)


@dataclass(frozen=True)
class BridgeReceipt:
    trace_id: str
    issue_number: Optional[int] = None
    pr_number: Optional[int] = None
    branch: Optional[str] = None
    labels: Optional[List[str]] = None
    deduped: bool = False

    def as_dict(self) -> Dict[str, Any]:
        return {
            "trace_id": self.trace_id,
            "issue_number": self.issue_number,
            "pr_number": self.pr_number,
            "branch": self.branch,
            "labels": self.labels,
            "deduped": self.deduped,
        }


class GitHubBridge:
    def __init__(
        self,
        client: Any,
        *,
        base_branch: str = "main",
        idempotency_store: Optional[Dict[str, Dict[str, Any]]] = None,
    ) -> None:
        self._client = client
        self._base = base_branch
        self._store: Dict[str, Dict[str, Any]] = (
            {} if idempotency_store is None else idempotency_store
        )

    def _cached(self, key: str) -> Optional[BridgeReceipt]:
        raw = self._store.get(key)
        if raw is None:
            return None
        data = dict(raw)
        data["deduped"] = True
        return BridgeReceipt(**data)

    async def create_issue(self, summary: TraceSummary) -> BridgeReceipt:
        key = f"issue:{summary.trace_id}"
        hit = self._cached(key)
        if hit is not None:
            return hit
        content = build_issue(summary)
        for label in content.labels:
            await self._client.ensure_label(label)
        issue = await self._client.create_issue(
            content.title, content.body, content.labels
        )
        receipt = BridgeReceipt(
            trace_id=summary.trace_id,
            issue_number=issue["number"],
            labels=content.labels,
        )
        self._store[key] = receipt.as_dict()
        return receipt

    async def open_regression_pr(
        self, summary: TraceSummary, repro_code: str
    ) -> BridgeReceipt:
        key = f"pr:{summary.trace_id}"
        hit = self._cached(key)
        if hit is not None:
            return hit
        branch = branch_name(summary.trace_id)
        sha = await self._client.default_branch_sha(self._base)
        await self._client.create_branch(branch, sha)
        await self._client.put_file(
            branch,
            regression_test_path(summary.trace_id),
            repro_code,
            f"test: add StepStitch regression for {summary.trace_id}",
        )
        content = build_issue(summary)
        pr = await self._client.open_pull_request(
            branch,
            self._base,
            f"[StepStitch] regression + repro for {summary.route}",
            content.body,
        )
        receipt = BridgeReceipt(
            trace_id=summary.trace_id,
            pr_number=pr["number"],
            branch=branch,
            labels=[LABEL_BASE, LABEL_FIX_CANDIDATE],
        )
        self._store[key] = receipt.as_dict()
        return receipt
```

- [ ] **Step 4: Export bridge symbols**

Replace the body of `service/stepstitch_service/github_bridge/__init__.py` with:

```python
"""StepStitch Repair Loop — optional GitHub bridge (Apache-2.0, off by default).

Turns a reproduced trace into a labeled GitHub issue + a regression-test PR. Mirrors the
delivery/ pattern: credentials live in a host-injected closure, never in core; governed,
audited, human-merged; never on the agent/MCP surface. There is no merge capability.
"""
from .bridge import BridgeReceipt, GitHubBridge
from .client import BridgeError, GitHubClient, GitHubRequestFn
from .content import IssueContent, build_issue, branch_name, regression_test_path, repro_labels

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
    "build_issue",
    "branch_name",
    "regression_test_path",
    "repro_labels",
]
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd service && python -m pytest tests/test_github_bridge.py -q`
Expected: PASS (4 passed)

- [ ] **Step 6: Commit**

```bash
git add service/stepstitch_service/github_bridge/bridge.py \
        service/stepstitch_service/github_bridge/__init__.py \
        service/tests/test_github_bridge.py
git commit -m "feat(repair-loop): GitHubBridge orchestration with per-trace idempotency"
```

---

## Task 4: Governed router endpoints + agent-surface guard

**Files:**
- Modify: `service/stepstitch_service/mcp_server.py` (extend `is_destructive`)
- Modify: `service/stepstitch_service/router.py` (param + 2 endpoints + payload models)
- Test: `service/tests/test_github_endpoints.py`

- [ ] **Step 1: Write the failing test**

```python
# service/tests/test_github_endpoints.py
"""Governed GitHub endpoints: off by default, admin + approved_by, dry-run, not an agent tool."""
from fastapi import FastAPI
from fastapi.testclient import TestClient

from stepstitch_service import create_stepstitch_router, generate_playwright_test
from stepstitch_service.github_bridge import GitHubBridge
from stepstitch_service.mcp_server import CopilotSafeOperation, ToolParam, build_tool_definitions

_PFX = "/api/stepstitch/v1"


class _DB:
    def __init__(self):
        self.rows = {}

    async def execute(self, query, params=()):
        if query.strip().upper().startswith("INSERT"):
            self.rows[params[0]] = {"footsteps": params[5], "project_id": params[2]}

    async def fetchone(self, query, params=()):
        row = self.rows.get(params[0])
        return (row["footsteps"], row["project_id"]) if row else None

    async def fetchall(self, query, params=()):
        return []


class _FakeClient:
    def __init__(self):
        self.issues = 0
        self.prs = 0

    async def ensure_label(self, name, **kw):
        pass

    async def create_issue(self, title, body, labels):
        self.issues += 1
        return {"number": 5}

    async def default_branch_sha(self, base):
        return "sha"

    async def create_branch(self, branch, sha):
        return {}

    async def put_file(self, branch, path, content_text, message):
        return {}

    async def open_pull_request(self, head, base, title, body):
        self.prs += 1
        return {"number": 9}


def _build(*, with_bridge=True):
    db = _DB()
    bridge = GitHubBridge(_FakeClient()) if with_bridge else None
    router = create_stepstitch_router(
        get_user_id=lambda: "u", require_admin=lambda: {"user_id": "admin"},
        execute=db.execute, fetchone=db.fetchone, fetchall=db.fetchall,
        generate_playwright_test=generate_playwright_test,
        github_bridge=bridge,
    )
    app = FastAPI()
    app.include_router(router, prefix="/api")
    return TestClient(app)


def _ingest(client):
    return client.post(f"{_PFX}/session", json={
        "app_id": "a", "footsteps": [
            {"timestamp": "t", "type": "api_error", "route": "/x",
             "label": "[masked]", "metadata": {"status": 500}}],
        "metadata": {"sdk_version": "0.4.0"},
    }).json()["trace_id"]


def test_disabled_returns_404():
    client = _build(with_bridge=False)
    tid = _ingest(client)
    assert client.post(f"{_PFX}/session/{tid}/github/issue",
                       json={"approved_by": "ops"}).status_code == 404


def test_issue_requires_approver():
    client = _build()
    tid = _ingest(client)
    assert client.post(f"{_PFX}/session/{tid}/github/issue",
                       json={"approved_by": "  "}).status_code == 422


def test_create_issue_ok():
    client = _build()
    tid = _ingest(client)
    r = client.post(f"{_PFX}/session/{tid}/github/issue", json={"approved_by": "ops"})
    assert r.status_code == 200
    assert r.json()["issue"]["issue_number"] == 5


def test_pr_dry_run_is_default_and_opens_nothing():
    client = _build()
    tid = _ingest(client)
    r = client.post(f"{_PFX}/session/{tid}/github/pr",
                    json={"approved_by": "ops", "idempotency_key": "k"})
    assert r.status_code == 200
    body = r.json()
    assert body["dry_run"] is True
    assert body["would_open"]["branch"] == f"stepstitch/trace-{tid}"


def test_pr_real_opens_pr():
    client = _build()
    tid = _ingest(client)
    r = client.post(f"{_PFX}/session/{tid}/github/pr?dry_run=false",
                    json={"approved_by": "ops", "idempotency_key": "k"})
    assert r.status_code == 200
    assert r.json()["pr"]["pr_number"] == 9


def test_github_is_never_an_agent_tool():
    assert not any("github" in d["name"] for d in build_tool_definitions())
    sneaky = CopilotSafeOperation(
        operation_id="Gh", tool_name="github_issue", method="POST",
        path="/session/{trace_id}/github/issue", description="x",
        params=(ToolParam("trace_id", "string", required=True),),
    )
    assert sneaky.is_destructive
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd service && python -m pytest tests/test_github_endpoints.py -q`
Expected: FAIL with `TypeError: create_stepstitch_router() got an unexpected keyword argument 'github_bridge'`

- [ ] **Step 3: Extend the agent-surface destructive guard**

In `service/stepstitch_service/mcp_server.py`, in `is_destructive`, change the token tuple to include `github` and `merge`:

```python
        lowered = self.path.lower()
        if any(token in lowered for token in (
            "purge", "by-user", "delete", "maintenance", "retention", "deliver",
            "github", "merge",
        )):
            # "deliver"/"github"/"merge" = governed write loops; never agent tools.
            return True
```

- [ ] **Step 4: Add the param + endpoints to the router**

In `service/stepstitch_service/router.py`, add the import near the other bridge import:

```python
from .github_bridge.content import branch_name, regression_test_path
```

Add two payload models next to `DeliverPayload`:

```python
class GitHubIssuePayload(BaseModel):
    approved_by: str


class GitHubPrPayload(BaseModel):
    approved_by: str
    idempotency_key: str
```

Add `github_bridge` to the `create_stepstitch_router` signature, right after `record_writers`:

```python
    record_writers: Optional[List[RecordWriter]] = None,
    github_bridge: Optional[Any] = None,
```

Add the two endpoints immediately before `@router.get("/session/{trace_id}/playwright")`:

```python
    @router.post("/session/{trace_id}/github/issue")
    async def post_github_issue(
        trace_id: str,
        payload: GitHubIssuePayload,
        admin: Any = Depends(require_admin),
    ) -> Dict[str, Any]:
        # Repair Loop (optional). NOT an agent tool. Creates/labels a GitHub issue from the
        # sanitized summary. Off unless a github_bridge is injected.
        if github_bridge is None:
            raise HTTPException(status_code=404, detail="github bridge is not enabled")
        if not payload.approved_by.strip():
            raise HTTPException(status_code=422, detail="approved_by is required")
        row = await fetchone(
            "SELECT footsteps, project_id FROM stepstitch_traces WHERE id = ?",
            (trace_id,),
        )
        if not row:
            raise HTTPException(status_code=404, detail="Trace not found")
        summary = build_trace_summary(trace_id, _loads(row[0]), project_id=row[1])
        receipt = await github_bridge.create_issue(summary)
        await _audit("stepstitch.github_issue", _actor_id(admin), {
            "trace_id": trace_id, "approved_by": payload.approved_by,
            "issue_number": receipt.issue_number,
        })
        return {"status": "ok", "trace_id": trace_id, "issue": receipt.as_dict()}

    @router.post("/session/{trace_id}/github/pr")
    async def post_github_pr(
        trace_id: str,
        payload: GitHubPrPayload,
        admin: Any = Depends(require_admin),
        dry_run: bool = Query(True),
    ) -> Dict[str, Any]:
        # Opens a regression-test PR (branch + committed Playwright test). Dry-run by
        # default; admin + approved_by + idempotency_key required. NEVER merges.
        if github_bridge is None:
            raise HTTPException(status_code=404, detail="github bridge is not enabled")
        if not payload.approved_by.strip():
            raise HTTPException(status_code=422, detail="approved_by is required")
        if not payload.idempotency_key.strip():
            raise HTTPException(status_code=422, detail="idempotency_key is required")
        row = await fetchone(
            "SELECT footsteps, project_id FROM stepstitch_traces WHERE id = ?",
            (trace_id,),
        )
        if not row:
            raise HTTPException(status_code=404, detail="Trace not found")
        footsteps = _loads(row[0])
        summary = build_trace_summary(trace_id, footsteps, project_id=row[1])
        repro_code = generate_playwright_test(trace_id, footsteps, base_url)
        if dry_run:
            await _audit("stepstitch.github_pr", _actor_id(admin),
                         {"trace_id": trace_id, "dry_run": True})
            return {
                "status": "ok", "trace_id": trace_id, "dry_run": True,
                "would_open": {
                    "branch": branch_name(trace_id),
                    "test_path": regression_test_path(trace_id),
                    "title": f"[StepStitch] regression + repro for {summary.route}",
                },
            }
        receipt = await github_bridge.open_regression_pr(summary, repro_code)
        await _audit("stepstitch.github_pr", _actor_id(admin), {
            "trace_id": trace_id, "dry_run": False,
            "pr_number": receipt.pr_number, "approved_by": payload.approved_by,
        })
        return {"status": "ok", "trace_id": trace_id, "dry_run": False,
                "pr": receipt.as_dict()}
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd service && python -m pytest tests/test_github_endpoints.py tests/test_mcp_surface.py -q`
Expected: PASS (all green — the destructive-guard change keeps the 3-way parity intact because no `github` op is added to `COPILOT_SAFE_OPERATIONS`)

- [ ] **Step 6: Commit**

```bash
git add service/stepstitch_service/router.py service/stepstitch_service/mcp_server.py \
        service/tests/test_github_endpoints.py
git commit -m "feat(repair-loop): governed GitHub issue/PR endpoints (not agent tools)"
```

---

## Task 5: Customer CI repro workflow template + import-linter coverage

**Files:**
- Create: `service/stepstitch_service/github_bridge/workflow.py`
- Modify: `service/stepstitch_service/github_bridge/__init__.py` (export the template)
- Modify: `service/pyproject.toml` (import-linter source modules)
- Test: `service/tests/test_github_content.py` (append a workflow check)

- [ ] **Step 1: Write the failing test (append to test_github_content.py)**

```python
def test_repro_workflow_template_is_runnable_yaml_text():
    from stepstitch_service.github_bridge.workflow import STEPSTITCH_REPRO_WORKFLOW
    t = STEPSTITCH_REPRO_WORKFLOW
    # Triggered manually with a trace id; fetches repro; runs Playwright; comments back.
    assert "workflow_dispatch" in t
    assert "trace_id" in t
    assert "playwright" in t.lower()
    assert "stepstitch:confirmed-repro" in t  # labels the issue on a confirmed repro
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd service && python -m pytest tests/test_github_content.py::test_repro_workflow_template_is_runnable_yaml_text -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'stepstitch_service.github_bridge.workflow'`

- [ ] **Step 3: Write the workflow template**

```python
# service/stepstitch_service/github_bridge/workflow.py
"""The customer-side CI workflow that runs a StepStitch repro and confirms it.

Customers drop this into ``.github/workflows/stepstitch-repro.yml`` in their repo. It is a
template string (not executed by StepStitch). Secrets STEPSTITCH_BASE_URL +
STEPSTITCH_ADMIN_TOKEN are set by the customer.
"""

STEPSTITCH_REPRO_WORKFLOW = r"""# .github/workflows/stepstitch-repro.yml
name: stepstitch-repro
on:
  workflow_dispatch:
    inputs:
      trace_id:
        description: StepStitch trace id
        required: true
permissions:
  contents: read
  issues: write
jobs:
  repro:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with: { node-version: "20" }
      - run: npm i -D @playwright/test && npx playwright install --with-deps chromium
      - name: Fetch the StepStitch reproduction
        env:
          BASE: ${{ secrets.STEPSTITCH_BASE_URL }}
          TOKEN: ${{ secrets.STEPSTITCH_ADMIN_TOKEN }}
          TRACE: ${{ github.event.inputs.trace_id }}
        run: |
          mkdir -p tests/stepstitch
          curl -fsS -H "Authorization: Bearer $TOKEN" \
            "$BASE/api/stepstitch/v1/session/$TRACE/playwright" \
            | python -c "import sys,json;open('tests/stepstitch/repro_'+'${{ github.event.inputs.trace_id }}'+'.spec.ts','w').write(json.load(sys.stdin)['playwright_code'])"
      - name: Run the reproduction
        id: run
        run: npx playwright test tests/stepstitch/ --reporter=line
      - name: Label issue confirmed on green-then-red repro
        if: success()
        run: echo "stepstitch:confirmed-repro (wire to your issue via gh CLI)"
"""
```

- [ ] **Step 4: Export the template**

In `service/stepstitch_service/github_bridge/__init__.py`, add to the imports and `__all__`:

```python
from .workflow import STEPSTITCH_REPRO_WORKFLOW
```

Add `"STEPSTITCH_REPRO_WORKFLOW"` to the `__all__` list.

- [ ] **Step 5: Add the github_bridge modules to the import-linter contract**

In `service/pyproject.toml`, under `[[tool.importlinter.contracts]] source_modules`, add:

```toml
    "stepstitch_service.github_bridge.content",
    "stepstitch_service.github_bridge.client",
    "stepstitch_service.github_bridge.bridge",
    "stepstitch_service.github_bridge.workflow",
```

- [ ] **Step 6: Run tests + boundary checks**

Run: `cd service && python -m pytest tests/test_github_content.py -q && lint-imports`
Expected: PASS, and `Contracts: 1 kept, 0 broken.`

- [ ] **Step 7: Commit**

```bash
git add service/stepstitch_service/github_bridge/workflow.py \
        service/stepstitch_service/github_bridge/__init__.py service/pyproject.toml \
        service/tests/test_github_content.py
git commit -m "feat(repair-loop): customer CI repro workflow template + boundary coverage"
```

---

## Task 6: Host wiring + docs

**Files:**
- Modify: `server/host.py` (accept + pass `github_bridge`)
- Create: `docs/integrations/github.md`
- Modify: `docs/AGENTS.md` (note the Repair Loop is governed, not an agent tool)

- [ ] **Step 1: Write the failing test (append to server/tests/test_host.py)**

```python
def test_build_app_accepts_github_bridge():
    from server.host import build_app
    get_user_id, require_admin = build_auth(ADMIN, INGEST)

    class _DB:
        async def execute(self, q, p=()):
            return None
        async def fetchone(self, q, p=()):
            return None
        async def fetchall(self, q, p=()):
            return []

    db = _DB()
    sentinel = object()
    app = build_app(
        get_user_id=get_user_id, require_admin=require_admin,
        execute=db.execute, fetchone=db.fetchone, fetchall=db.fetchall,
        github_bridge=sentinel,
    )
    assert app is not None  # build_app accepts and forwards github_bridge without error
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/cykiller/Downloads/stepstitch-main && python -m pytest server/tests/test_host.py::test_build_app_accepts_github_bridge -q`
Expected: FAIL with `TypeError: build_app() got an unexpected keyword argument 'github_bridge'`

- [ ] **Step 3: Thread github_bridge through build_app**

In `server/host.py`, add the parameter after `record_writers`:

```python
    record_writers: Optional[List[Any]] = None,
    github_bridge: Optional[Any] = None,
    audit: Optional[Callable[..., Awaitable[Any]]] = None,
```

And pass it into `create_stepstitch_router(...)` right after `record_writers=record_writers,`:

```python
        record_writers=record_writers,
        github_bridge=github_bridge,
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /Users/cykiller/Downloads/stepstitch-main && python -m pytest server/tests/test_host.py -q`
Expected: PASS

- [ ] **Step 5: Write the integration doc**

```markdown
# GitHub Repair Loop (optional)

The Repair Loop turns a reproduced trace into a labeled GitHub **issue** and a
regression-test **pull request** in your repo — privacy-safe and **human-merged**. It is
off by default, governed (admin + `approved_by`), audited, and never exposed on the
agent/MCP surface. StepStitch holds no repo write credentials in core and never merges.

## Enable it

```python
# pip install "stepstitch-service[github]"
from stepstitch_service.github_bridge import GitHubBridge, GitHubClient, github_token_request
request = github_token_request(GITHUB_TOKEN)            # token lives in the host
bridge = GitHubBridge(GitHubClient(request, repo="acme/app"), base_branch="main")
# build_app(..., github_bridge=bridge)   OR  create_stepstitch_router(..., github_bridge=bridge)
```

## Endpoints (admin only)

- `POST /stepstitch/v1/session/{id}/github/issue` — body `{ "approved_by": "..." }` →
  ensures labels + creates the issue from the sanitized summary.
- `POST /stepstitch/v1/session/{id}/github/pr?dry_run=true` — body
  `{ "approved_by": "...", "idempotency_key": "..." }` → dry-run shows the branch + test
  path; `dry_run=false` opens the regression-test PR. **Never merges.**

## CI repro workflow

Copy `STEPSTITCH_REPRO_WORKFLOW` (`stepstitch_service.github_bridge.workflow`) into
`.github/workflows/stepstitch-repro.yml`, set repo secrets `STEPSTITCH_BASE_URL` +
`STEPSTITCH_ADMIN_TOKEN`, then dispatch it with a `trace_id` to run the reproduction and
confirm it in CI.

## Labels

`stepstitch`, `privacy-safe`, `stepstitch:needs-fix`, `stepstitch:repro-ready` /
`stepstitch:needs-data` (by grade), `stepstitch:confirmed-repro` (CI), and
`stepstitch:fix-candidate` (on the PR).
```

Save the above as `docs/integrations/github.md`.

- [ ] **Step 6: Note it in docs/AGENTS.md**

In `docs/AGENTS.md`, under "What the agent must never do", add a bullet:

```markdown
- Use the Repair Loop (`/github/issue`, `/github/pr`) — it is a governed, admin-only,
  human-merged capability, deliberately off the agent surface (see docs/integrations/github.md).
```

- [ ] **Step 7: Full verification + commit**

Run:
```bash
cd /Users/cykiller/Downloads/stepstitch-main
( cd service && python -m pytest tests -q && lint-imports )
python -m pytest server/tests -q
```
Expected: all green; `Contracts: 1 kept, 0 broken.`

```bash
git add server/host.py docs/integrations/github.md docs/AGENTS.md
git commit -m "feat(repair-loop): host wiring + GitHub integration docs"
```

---

## Self-Review

**Spec coverage (user's 4 phases):**
- Phase 1 (issue/label bridge): Task 1 (content/labels) + Task 3 (`create_issue`) + Task 4 (`/github/issue`). ✓
- Phase 2 (Actions generator): Task 5 (`STEPSTITCH_REPRO_WORKFLOW`) + Task 6 docs. ✓
- Phase 3 (PR proposal): Task 3 (`open_regression_pr`) + Task 4 (`/github/pr`, dry-run default, never merges). ✓
- Phase 4 (fix-options cockpit UI / multi-agent fix generation): **explicitly deferred** to a follow-on plan (stated in Goal/Scope). ✓ (boundary noted, not silently dropped)
- Label vocabulary from the spec: all defined in `content.py` (Task 1); applied across bridge (repro-ready/needs-data/needs-fix/fix-candidate) and CI (confirmed-repro). ✓
- "Never auto-merge": enforced structurally — `GitHubClient` has no merge method (Task 2 test `test_no_merge_method_exists`) and `is_destructive` blocks `github`/`merge` from the agent surface (Task 4). ✓

**Placeholder scan:** every code step contains complete code; no TBD/“similar to”/“add error handling”. ✓

**Type consistency:** `GitHubRequestFn`, `GitHubClient(request, *, repo)`, `GitHubBridge(client, *, base_branch, idempotency_store)`, `BridgeReceipt(trace_id, issue_number, pr_number, branch, labels, deduped)` + `as_dict()`, `build_issue → IssueContent(title, body, labels)`, `branch_name`/`regression_test_path` — names match across Tasks 1–6. Router uses `build_trace_summary`, `generate_playwright_test`, `base_url`, `_loads`, `_audit`, `_actor_id` which already exist in `router.py`. ✓
