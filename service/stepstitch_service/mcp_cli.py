"""Reference entrypoint to run the StepStitch MCP server over stdio.

This is the host-wiring half of ``mcp_server.serve_stdio``: it builds a ``call_route``
that performs authenticated requests against a deployed StepStitch service, then serves
the Copilot-safe tools over stdio for any MCP client (Copilot Studio, OpenAI, Vertex,
LangGraph, Bedrock, Claude). Config via env:

    STEPSTITCH_BASE_URL   base URL of the service mount, incl. prefix
                          (e.g. https://stepstitch.internal/api/stepstitch/v1)
    STEPSTITCH_TOKEN_FILE path to a file containing the agent token (preferred)
    STEPSTITCH_TOKEN      the token itself (fallback; see the warning below)

``STEPSTITCH_TOKEN_FILE`` is preferred and is what ``stepstitch connect`` writes. An agent
client's config file is read by editors, synced by dotfile managers and pasted into bug
reports; a token sitting in it leaks by ordinary accident. A path leaks nothing, the file
is owner-only, and revoking it is deleting one file. The literal token is still accepted
because CI and container setups legitimately inject env vars.

Run:  pip install 'stepstitch-service[mcp]'
      STEPSTITCH_BASE_URL=... STEPSTITCH_TOKEN=... python -m stepstitch_service.mcp_cli

Kept out of the dependency-free core: ``httpx`` and ``mcp`` are imported lazily here.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, Optional

from .mcp_server import serve_stdio


def _build_http_call_route(base_url: str, token: str):
    import httpx

    headers = {"Authorization": f"Bearer {token}"} if token else {}
    client = httpx.AsyncClient(base_url=base_url.rstrip("/"), headers=headers, timeout=30.0)

    async def call_route(method: str, path: str, params: Dict[str, Any]) -> Dict[str, Any]:
        resp = await client.request(method, path, params=params or None)
        resp.raise_for_status()
        return resp.json()

    return call_route


def read_token(env: Optional[Dict[str, str]] = None) -> str:
    """The agent token: from a file if one is named, else straight from the environment.

    Pure and injectable so the precedence is testable — this decides what credential an
    agent presents, which is not something to leave to a manual check.
    """
    source = dict(os.environ if env is None else env)
    path = source.get("STEPSTITCH_TOKEN_FILE")
    if path:
        try:
            return Path(path).expanduser().read_text(encoding="utf-8").strip()
        except OSError as exc:
            raise SystemExit(
                f"STEPSTITCH_TOKEN_FILE points at {path}, which could not be read ({exc}). "
                "Re-run `stepstitch connect <agent>` to reissue it."
            ) from exc
    return source.get("STEPSTITCH_TOKEN", "")


def main() -> None:  # pragma: no cover - process entrypoint
    import asyncio

    base_url = os.environ.get("STEPSTITCH_BASE_URL")
    if not base_url:
        raise SystemExit("STEPSTITCH_BASE_URL is required (the service mount incl. prefix)")
    call_route = _build_http_call_route(base_url, read_token())
    asyncio.run(serve_stdio(call_route))


if __name__ == "__main__":  # pragma: no cover
    main()
