"""Connector enablement-pack guards (docs/PRODUCT-PLAN.md P2).

The connector docs in copilot/ must not drift from the operation SSOT. (The
declarative/paste-a-trace agent is a separate competition artifact, not the StepStitch
product, so it is intentionally not part of this repo's surface.)
"""
import re
from pathlib import Path

from stepstitch_service import COPILOT_SAFE_OPERATIONS

_COPILOT = Path(__file__).resolve().parents[2] / "copilot"


def test_mcp_setup_doc_lists_every_tool_and_no_extras():
    md = (_COPILOT / "MCP-SETUP.md").read_text()
    documented = set(re.findall(r"`([a-z_]+)`", md))
    tool_names = {op.tool_name for op in COPILOT_SAFE_OPERATIONS}
    missing = tool_names - documented
    assert not missing, f"MCP-SETUP.md does not document tools: {sorted(missing)}"
    # Any snake_case backticked token shaped like a tool but not in the SSOT is drift.
    toolish = {t for t in documented if t.startswith(("get_", "list_", "create_", "generate_"))}
    extras = toolish - tool_names
    assert not extras, f"MCP-SETUP.md references unknown tools: {sorted(extras)}"


def test_setup_links_the_mcp_connector_path():
    setup = (_COPILOT / "SETUP.md").read_text()
    assert "MCP-SETUP.md" in setup, "SETUP.md should link the MCP (universal connector) path"
