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
    assert c.issues == 1
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
    assert c.prs == 1
