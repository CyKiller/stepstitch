"""Reference entrypoint to run the StepStitch MCP server over stdio.

This is the host-wiring half of ``mcp_server.serve_stdio``: it builds a ``call_route``
that performs authenticated requests against a deployed StepStitch service, then serves
the Copilot-safe tools over stdio for any MCP client (Copilot Studio, OpenAI, Vertex,
LangGraph, Bedrock, Claude). Config via env:

    STEPSTITCH_BASE_URL   base URL of the service mount, incl. prefix
                          (e.g. https://stepstitch.internal/api/stepstitch/v1)
    STEPSTITCH_TOKEN      operator bearer token (admin; reads are audited server-side)

Run:  pip install 'stepstitch-service[mcp]'
      STEPSTITCH_BASE_URL=... STEPSTITCH_TOKEN=... python -m stepstitch_service.mcp_cli

Kept out of the dependency-free core: ``httpx`` and ``mcp`` are imported lazily here.
"""
from __future__ import annotations

import os
from typing import Any, Dict

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


def main() -> None:  # pragma: no cover - process entrypoint
    import asyncio

    base_url = os.environ.get("STEPSTITCH_BASE_URL")
    if not base_url:
        raise SystemExit("STEPSTITCH_BASE_URL is required (the service mount incl. prefix)")
    token = os.environ.get("STEPSTITCH_TOKEN", "")
    call_route = _build_http_call_route(base_url, token)
    asyncio.run(serve_stdio(call_route))


if __name__ == "__main__":  # pragma: no cover
    main()
