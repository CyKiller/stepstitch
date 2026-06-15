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
    assert not hasattr(GitHubClient, "merge")
    assert not hasattr(GitHubClient, "merge_pull_request")
