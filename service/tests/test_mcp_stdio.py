"""The MCP stdio transport, actually spoken.

Every other MCP test inspects the tool table; none of them ever started a session, so the
transport glue carried ``# pragma: no cover`` and a client-visible break — a bad tool
schema, a serialization error — would have shipped green. This spawns the server as a
subprocess and talks real MCP to it: initialize, list tools, call one.

Skipped when the optional ``mcp`` extra is absent (the core stays dependency-free).
"""
import asyncio
import os
import sys

import pytest

mcp = pytest.importorskip("mcp", reason="needs the optional 'mcp' extra")

from mcp import ClientSession, StdioServerParameters  # noqa: E402
from mcp.client.stdio import stdio_client  # noqa: E402

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# A server whose call_route answers from a fixture: this test is about the transport, not
# about HTTP. Runs as its own process, exactly as an MCP client would launch it.
_SERVER = """
import asyncio, sys
sys.path.insert(0, {service!r})
from stepstitch_service.mcp_server import serve_stdio

async def call_route(method, path, params):
    return {{"status": "ok", "echo": {{"method": method, "path": path, "params": params}}}}

asyncio.run(serve_stdio(call_route))
"""


async def _session_roundtrip():
    params = StdioServerParameters(
        command=sys.executable,
        args=["-c", _SERVER.format(service=os.path.join(REPO, "service"))],
        env={**os.environ, "PYTHONUNBUFFERED": "1"},
    )
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = await session.list_tools()
            names = [t.name for t in tools.tools]
            assert names, "the server offered no tools"
            # Every advertised tool must carry a schema a client can render.
            for tool in tools.tools:
                assert tool.description, f"{tool.name} has no description"
                assert tool.inputSchema is not None, f"{tool.name} has no input schema"
            result = await session.call_tool(
                "get_agent_packet", {"trace_id": "t-1"})
            text = "".join(
                block.text for block in result.content if getattr(block, "type", "") == "text")
            assert "t-1" in text
            return names


def test_a_real_client_can_initialize_list_and_call():
    names = asyncio.run(asyncio.wait_for(_session_roundtrip(), timeout=60))
    # The surface a client sees must match the table the drift tests guard.
    from stepstitch_service.mcp_server import COPILOT_SAFE_OPERATIONS

    assert len(names) == len(COPILOT_SAFE_OPERATIONS)
