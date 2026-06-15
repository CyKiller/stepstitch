"""GitHub REST client for the optional Repair Loop bridge.

Uses an injected async request fn so the core never imports httpx or holds credentials.
Exposes the MINIMUM operations to label an issue and open a regression-test PR. There is
deliberately NO merge method — StepStitch never merges.
"""
from __future__ import annotations

import asyncio
import base64
from typing import Any, Awaitable, Callable, Dict, List, Optional

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
            if exc.status != 422:
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
