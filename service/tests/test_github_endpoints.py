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


def test_pr_disabled_returns_404():
    client = _build(with_bridge=False)
    tid = _ingest(client)
    assert client.post(f"{_PFX}/session/{tid}/github/pr",
                       json={"approved_by": "ops", "idempotency_key": "k"}).status_code == 404


def test_pr_requires_approver_and_key():
    client = _build()
    tid = _ingest(client)
    assert client.post(f"{_PFX}/session/{tid}/github/pr",
                       json={"approved_by": "  ", "idempotency_key": "k"}).status_code == 422
    assert client.post(f"{_PFX}/session/{tid}/github/pr",
                       json={"approved_by": "ops", "idempotency_key": ""}).status_code == 422
