"""StepStitch MCP server — the universal agentic connector.

StepStitch is a capability *provider*, not an agent *orchestrator*. This module exposes
the **Copilot-safe** operation set (read-only / draft-only, already proven non-destructive
by ``test_copilot_surface.py``) over the Model Context Protocol, so any MCP client —
Microsoft Copilot Studio, OpenAI, Google Vertex/Gemini, LangGraph, AWS Bedrock, Claude —
can consume the same surface without a bespoke adapter. See docs/PRODUCT-PLAN.md (P1).

Design (mirrors ``router.create_stepstitch_router``): this module never imports a host,
an HTTP client, or the MCP SDK at import time. The host injects ``call_route`` — an async
callable that performs the actual authenticated request against the deployed StepStitch
service. That keeps the trust boundary (server-side scrubber), the admin auth, and the
``stepstitch.*`` read-audit centralized in the service; the MCP server is pure protocol
adaptation over the *same* routes the OpenAPI pack advertises.

``COPILOT_SAFE_OPERATIONS`` is the single source of truth shared by three surfaces:
the OpenAPI pack (``copilot/openapi-v2.json``), the live router routes, and these MCP
tools. ``test_mcp_surface.py`` fails if any of the three drift apart or if a destructive
operation ever appears here.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Dict, Optional, Tuple

# The service's own router prefix (the host prepends its mount path, e.g. ``/api``).
SERVICE_PREFIX = "/stepstitch/v1"

# A callable the host injects to perform an authenticated request against the deployed
# StepStitch service: (method, path_under_service_prefix, query_params) -> parsed JSON.
CallRouteFn = Callable[[str, str, Dict[str, Any]], Awaitable[Dict[str, Any]]]


@dataclass(frozen=True)
class ToolParam:
    name: str
    json_type: str
    required: bool = False
    description: str = ""
    # path = substituted into the route template; query = appended as a query parameter.
    location: str = "path"
    default: Any = None
    maximum: Optional[int] = None


@dataclass(frozen=True)
class CopilotSafeOperation:
    """One read-only / draft-only operation, shared across OpenAPI, routes, and MCP."""

    operation_id: str  # must equal the OpenAPI operationId
    tool_name: str  # MCP tool name (snake_case)
    method: str  # "GET" | "POST"
    path: str  # route under SERVICE_PREFIX, e.g. "/session/{trace_id}/summary"
    description: str
    params: Tuple[ToolParam, ...] = field(default_factory=tuple)

    @property
    def is_destructive(self) -> bool:
        # A tool is destructive if it deletes, purges, targets a user's bodies, toggles
        # capture/retention, or reads the raw trace (which carries the free-text
        # ``explanation``). None of those may ever be an MCP tool.
        method = self.method.upper()
        if method in {"DELETE", "PUT", "PATCH"}:
            return True
        lowered = self.path.lower()
        if any(token in lowered for token in (
            "purge", "by-user", "delete", "maintenance", "retention", "deliver",
            "github", "merge",
        )):
            # "deliver"/"github"/"merge" = governed write loops; never agent tools.
            return True
        # The raw single-trace read endpoint is exactly "/session/{trace_id}".
        if self.path == "/session/{trace_id}":
            return True
        return False

    def input_schema(self) -> Dict[str, Any]:
        props: Dict[str, Any] = {}
        required = []
        for p in self.params:
            schema: Dict[str, Any] = {"type": p.json_type}
            if p.description:
                schema["description"] = p.description
            if p.default is not None:
                schema["default"] = p.default
            if p.maximum is not None:
                schema["maximum"] = p.maximum
            props[p.name] = schema
            if p.required:
                required.append(p.name)
        out: Dict[str, Any] = {"type": "object", "properties": props}
        if required:
            out["required"] = required
        return out


_TRACE_ID = ToolParam(
    "trace_id", "string", required=True, location="path",
    description="The StepStitch trace id.",
)

# ---- Single source of truth: the Copilot-safe operation set (mirrors openapi-v2.json) ----
COPILOT_SAFE_OPERATIONS: Tuple[CopilotSafeOperation, ...] = (
    CopilotSafeOperation(
        operation_id="ListRecentTraces",
        tool_name="list_recent_traces",
        method="GET",
        path="/sessions",
        description="List recent traces (admin, audited). Returns no trace bodies.",
        params=(
            ToolParam("project_id", "string", location="query",
                      description="Optional project filter."),
            ToolParam("limit", "integer", location="query", default=50, maximum=200,
                      description="Max traces to return (<=200)."),
        ),
    ),
    CopilotSafeOperation(
        operation_id="GetTraceSummary",
        tool_name="get_trace_summary",
        method="GET",
        path="/session/{trace_id}/summary",
        description="Sanitized, structure-derived summary of a trace (no NPI).",
        params=(_TRACE_ID,),
    ),
    CopilotSafeOperation(
        operation_id="GetReplayabilityScore",
        tool_name="get_replayability_score",
        method="GET",
        path="/session/{trace_id}/replayability",
        description="Reproducibility score, grade (A-F), and warnings.",
        params=(_TRACE_ID,),
    ),
    CopilotSafeOperation(
        operation_id="GetPrivacyPosture",
        tool_name="get_privacy_posture",
        method="GET",
        path="/session/{trace_id}/privacy-posture",
        description="Per-trace scrub report and the never-captured list.",
        params=(_TRACE_ID,),
    ),
    CopilotSafeOperation(
        operation_id="GetDiagnosticSummary",
        tool_name="get_diagnostic_summary",
        method="GET",
        path="/session/{trace_id}/diagnostic-summary",
        description="Sanitized frontend/API diagnostic summary and recommended next step.",
        params=(_TRACE_ID,),
    ),
    CopilotSafeOperation(
        operation_id="GeneratePlaywrightRepro",
        tool_name="generate_playwright_repro",
        method="GET",
        path="/session/{trace_id}/playwright",
        description="Deterministic Playwright reproduction code (text only; never run "
                    "against production).",
        params=(_TRACE_ID,),
    ),
    CopilotSafeOperation(
        operation_id="MatchVerifiedFixes",
        tool_name="match_verified_fixes",
        method="GET",
        path="/session/{trace_id}/similar-fixes",
        description="Match this trace against the verified-fix corpus by structure — surfaces "
                    "'you've fixed this shape before' with the prior fix ref. Structural, no NPI.",
        params=(_TRACE_ID,),
    ),
    CopilotSafeOperation(
        operation_id="GetAttestation",
        tool_name="get_attestation",
        method="GET",
        path="/session/{trace_id}/attestation",
        description="Signed, independently-verifiable evidence bundle (scrub report + "
                    "replayability + verdict + SDK build) with a tamper-evident hash. No NPI.",
        params=(_TRACE_ID,),
    ),
    CopilotSafeOperation(
        operation_id="GetFragilityMap",
        tool_name="get_fragility_map",
        method="GET",
        path="/session/{trace_id}/fragility",
        description="Per-step fragility ranking (selector brittleness + templated routes), "
                    "worst-first — predicts what will break. No NPI.",
        params=(_TRACE_ID,),
    ),
    CopilotSafeOperation(
        operation_id="GenerateMinimalRepro",
        tool_name="generate_minimal_repro",
        method="GET",
        path="/session/{trace_id}/minimal-repro",
        description="The smallest failing path compiled to Playwright (drops unrelated-route "
                    "detours). No NPI.",
        params=(_TRACE_ID,),
    ),
    CopilotSafeOperation(
        operation_id="CreateExportPreview",
        tool_name="create_export_preview",
        method="POST",
        path="/session/{trace_id}/export-preview",
        description="Build sanitized ServiceNow + Salesforce + Genesys DRAFTS. Sends nothing.",
        params=(_TRACE_ID,),
    ),
    CopilotSafeOperation(
        operation_id="CreateFinancialServicesExportPreview",
        tool_name="create_fs_export_preview",
        method="POST",
        path="/session/{trace_id}/financial-services-export-preview",
        description="Build the named financial-services support DRAFT pack. Sends nothing.",
        params=(_TRACE_ID,),
    ),
)

_BY_TOOL = {op.tool_name: op for op in COPILOT_SAFE_OPERATIONS}


def assert_no_destructive_operation() -> None:
    """Self-check: the MCP surface must expose no destructive operation. Raises on drift."""
    bad = [op.tool_name for op in COPILOT_SAFE_OPERATIONS if op.is_destructive]
    if bad:
        raise AssertionError(f"destructive MCP operations are forbidden: {bad}")


# Fail fast at import: a destructive tool can never ship.
assert_no_destructive_operation()


def build_tool_definitions() -> list[Dict[str, Any]]:
    """MCP tool descriptors (name / description / inputSchema) for ``list_tools``."""
    return [
        {
            "name": op.tool_name,
            "description": op.description,
            "inputSchema": op.input_schema(),
        }
        for op in COPILOT_SAFE_OPERATIONS
    ]


def build_function_tool_specs() -> list[Dict[str, Any]]:
    """The SAME Copilot-safe operations projected into the OpenAI/JSON-Schema *function
    tool* format, for function-calling models that don't speak MCP (e.g. Hermes, the OpenAI
    tools API, Gemini function calling).

    Drawn from the same ``COPILOT_SAFE_OPERATIONS`` source of truth as the MCP tools and the
    OpenAPI pack — so the three surfaces cannot drift (see ``test_mcp_surface.py``). Still
    read-only / draft-only: a destructive op can never appear here.
    """
    return [
        {
            "type": "function",
            "function": {
                "name": op.tool_name,
                "description": op.description,
                "parameters": op.input_schema(),
            },
        }
        for op in COPILOT_SAFE_OPERATIONS
    ]


async def dispatch_tool(
    tool_name: str,
    arguments: Dict[str, Any],
    call_route: CallRouteFn,
) -> Dict[str, Any]:
    """Translate an MCP tool call into a request against the StepStitch service.

    Path params are substituted into the route template; query params are passed
    through. The actual auth + audit + scrub all happen in the service behind
    ``call_route``. Raises ``KeyError`` for an unknown tool and ``ValueError`` for a
    missing required argument.
    """
    op = _BY_TOOL.get(tool_name)
    if op is None:
        raise KeyError(f"unknown StepStitch tool: {tool_name}")

    arguments = arguments or {}
    path = op.path
    query: Dict[str, Any] = {}
    for p in op.params:
        value = arguments.get(p.name, p.default)
        if p.required and value is None:
            raise ValueError(f"{tool_name}: missing required argument '{p.name}'")
        if value is None:
            continue
        if p.location == "path":
            path = path.replace("{" + p.name + "}", str(value))
        else:
            query[p.name] = value

    return await call_route(op.method, path, query)


def serve_stdio(call_route: CallRouteFn, *, server_name: str = "stepstitch") -> Any:
    """Run the MCP server over stdio, binding the Copilot-safe tools to ``call_route``.

    The MCP SDK is imported lazily so the core service package stays dependency-free
    (install the ``mcp`` extra: ``pip install 'stepstitch-service[mcp]'``). Returns the
    coroutine to await, so a thin CLI entrypoint can ``asyncio.run(serve_stdio(...))``.
    """
    try:
        import mcp.types as types
        from mcp.server import Server
        from mcp.server.stdio import stdio_server
    except ImportError as exc:  # pragma: no cover - exercised only without the extra
        raise ImportError(
            "The MCP server needs the optional 'mcp' dependency. "
            "Install it with: pip install 'stepstitch-service[mcp]'"
        ) from exc

    server: Any = Server(server_name)

    @server.list_tools()
    async def _list_tools():  # pragma: no cover - thin SDK glue
        return [
            types.Tool(
                name=d["name"],
                description=d["description"],
                inputSchema=d["inputSchema"],
            )
            for d in build_tool_definitions()
        ]

    @server.call_tool()
    async def _call_tool(name: str, arguments: Dict[str, Any]):  # pragma: no cover
        import json

        result = await dispatch_tool(name, arguments or {}, call_route)
        return [types.TextContent(type="text", text=json.dumps(result, default=str))]

    async def _run():  # pragma: no cover - thin SDK glue
        async with stdio_server() as (read, write):
            await server.run(read, write, server.create_initialization_options())

    return _run()
