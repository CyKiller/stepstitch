"""Every MCP tool must be reachable by some scope — or be an explicit, documented exclusion.

This test exists because the gap it guards was real and invisible. ``scope_allows`` is
default-deny and ``_RULES`` simply had no entry for five of the thirteen advertised tools,
including ``get_agent_packet`` — the one a coding agent is meant to call. Nothing failed:
the MCP surface advertised the tool, the route existed, and the only credential that could
actually reach it was the **admin** token. So the shipped ``.mcp.json`` handed agents admin
rights, and "least-privilege agent connection" was impossible in practice while appearing
to be a solved problem.

Advertising a tool no scoped token can call is worse than not shipping it: it pushes every
operator toward the one credential that works.
"""
import pytest
from stepstitch_service.mcp_server import COPILOT_SAFE_OPERATIONS

from server.agents import SCOPES, scope_allows

_PFX = "/api/stepstitch/v1"

# Tools deliberately unreachable by scoped tokens, with the reason. Empty today — every
# advertised tool is reachable. An entry here is a claim that a tool is admin-only ON
# PURPOSE, and it must be justified in the string.
DOCUMENTED_EXCLUSIONS: dict = {}

# The scope a coding agent is issued by `stepstitch connect`. It must be able to do the
# whole job — understand the failure and read the reproduction — and nothing more.
CODING_AGENT_SCOPE = "repros"


def _path(operation) -> str:
    return _PFX + operation.path.replace("{trace_id}", "trace-1").replace(
        "{correlation_id}", "corr-1")


@pytest.mark.parametrize("operation", COPILOT_SAFE_OPERATIONS,
                         ids=lambda o: o.tool_name)
def test_every_mcp_tool_is_reachable_by_some_scope(operation):
    reachable = [s for s in SCOPES
                 if s != "none" and scope_allows(s, operation.method, _path(operation))]
    if operation.tool_name in DOCUMENTED_EXCLUSIONS:
        assert not reachable, (
            f"{operation.tool_name} is listed as a documented exclusion but IS reachable — "
            "remove it from DOCUMENTED_EXCLUSIONS.")
        return
    assert reachable, (
        f"{operation.tool_name} is advertised on the MCP surface but no scoped token can "
        f"call it, so operators must use the admin token instead. Add a rule to "
        f"server/agents.py _RULES, or record it in DOCUMENTED_EXCLUSIONS with a reason."
    )


def test_a_coding_agent_can_do_its_whole_job(the_packet="get_agent_packet"):
    """The connect flow issues `repros`. If the flagship tool needed more than that, every
    operator would quietly fall back to admin."""
    packet = [o for o in COPILOT_SAFE_OPERATIONS if o.tool_name == the_packet][0]
    assert scope_allows(CODING_AGENT_SCOPE, packet.method, _path(packet))
    repro = [o for o in COPILOT_SAFE_OPERATIONS
             if o.tool_name == "generate_playwright_repro"][0]
    assert scope_allows(CODING_AGENT_SCOPE, repro.method, _path(repro))


def test_a_coding_agent_cannot_record_a_verdict():
    """The load-bearing separation: an agent that fixes code must never be able to write
    the evidence that says its fix worked. That is what `verify` alone may do."""
    assert not scope_allows(CODING_AGENT_SCOPE, "POST", f"{_PFX}/session/t/verify")
    assert scope_allows("verify", "POST", f"{_PFX}/session/t/verify")


def test_a_coding_agent_cannot_draft_tickets():
    """`repros` is not a superset of `drafts`. Reading a reproduction is not permission to
    write into a system of record."""
    assert not scope_allows(CODING_AGENT_SCOPE, "POST", f"{_PFX}/session/t/export-preview")


def test_summaries_cannot_read_reproduction_code_through_the_packet():
    """The packet CONTAINS the compiled reproduction. If it sat at summary tier, a
    summaries-only agent would read repro code through the side door."""
    packet = [o for o in COPILOT_SAFE_OPERATIONS if o.tool_name == "get_agent_packet"][0]
    assert not scope_allows("summaries", packet.method, _path(packet))


def test_ci_gets_the_reproduction_but_not_a_shorter_one():
    """`verify` runs the frozen script it was handed. Fetching a different, minimised test
    is not part of that job."""
    assert scope_allows("verify", "GET", f"{_PFX}/session/t/playwright")
    assert not scope_allows("verify", "GET", f"{_PFX}/session/t/minimal-repro")


def test_an_unknown_route_is_denied_by_default():
    for scope in SCOPES:
        assert not scope_allows(scope, "GET", f"{_PFX}/session/t/whatever-comes-next")
        assert not scope_allows(scope, "DELETE", f"{_PFX}/session/t")
