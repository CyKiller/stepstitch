"""The marketing site's MCP tool list must match the MCP server's.

This test exists because the site got it wrong in two places at once: the comparison table
advertised "8 read-only tools" while the agents section said "twelve", and the real number
was thirteen. Nobody noticed, because nothing connected the claim to the code.

`test_mcp_surface.py` already keeps the MCP server, the OpenAPI pack and the function specs
in step with each other. This extends that boundary one step further out, to the thing a
buyer actually reads. A published capability claim is part of the contract.
"""
import pathlib
import re

import pytest

from stepstitch_service.mcp_server import COPILOT_SAFE_OPERATIONS

_SITE_LIST = (
    pathlib.Path(__file__).resolve().parents[2] / "web" / "src" / "lib" / "mcp-tools.ts"
)


def _site_tools() -> list:
    """Tool names the website advertises, read straight out of the TS source."""
    source = _SITE_LIST.read_text()
    body = source.split("export const MCP_TOOLS = [", 1)[1].split("]", 1)[0]
    return re.findall(r'"([a-z_]+)"', body)


def _server_tools() -> list:
    return [op.tool_name for op in COPILOT_SAFE_OPERATIONS]


@pytest.mark.skipif(not _SITE_LIST.exists(), reason="web/ not present in this checkout")
def test_the_site_advertises_exactly_the_tools_the_server_exposes():
    site, server = _site_tools(), _server_tools()
    assert sorted(site) == sorted(server), (
        "web/src/lib/mcp-tools.ts is out of step with mcp_server.py.\n"
        f"  only on the site:   {sorted(set(site) - set(server))}\n"
        f"  only in the server: {sorted(set(server) - set(site))}"
    )


@pytest.mark.skipif(not _SITE_LIST.exists(), reason="web/ not present in this checkout")
def test_the_advertised_count_is_derived_not_typed():
    """Both places that quote a number must compute it, or they will drift again."""
    source = _SITE_LIST.read_text()
    assert "MCP_TOOLS.length" in source, "the count must be derived from the list"

    components = (_SITE_LIST.parents[1] / "components")
    for name in ("comparison.tsx", "agentic.tsx"):
        text = (components / name).read_text()
        assert "MCP_TOOL_COUNT" in text, f"{name} must read the count, not hardcode it"
        # The old wrong literals, in the exact shapes they appeared.
        assert "8 read-only tools" not in text
        assert "Twelve Copilot-safe tools" not in text
