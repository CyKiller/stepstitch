"""MCP surface proof (docs/PRODUCT-PLAN.md P0 + P1).

P0 (parity): the MCP tool set, the OpenAPI pack, and the live router routes are the
SAME Copilot-safe operation set — none may drift from the others.
P1 (safety + E2E): the MCP surface exposes no destructive operation, and dispatching a
tool actually drives the real service (audited, sanitized, no NPI).
"""
import json
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from stepstitch_service import (
    COPILOT_SAFE_OPERATIONS,
    assert_no_destructive_operation,
    build_function_tool_specs,
    build_tool_definitions,
    create_stepstitch_router,
    dispatch_tool,
    generate_playwright_test,
)
from stepstitch_service.integrations.bundle import default_draft_adapters
from stepstitch_service.mcp_server import SERVICE_PREFIX

_REPO_ROOT = Path(__file__).resolve().parents[2]
_OPENAPI = _REPO_ROOT / "copilot" / "openapi-v2.json"
_PFX = "/api/stepstitch/v1"


# --- shared in-memory service harness (mirrors test_copilot_surface) ------------------

class QueryAwareDB:
    def __init__(self):
        self.rows = {}
        self.audits = []

    async def execute(self, query, params=()):
        if query.strip().upper().startswith("INSERT"):
            self.rows[params[0]] = {
                "app_id": params[1], "project_id": params[2], "user_id": params[3],
                "explanation": params[4], "footsteps": params[5],
                "trace_metadata": params[6],
            }

    async def fetchone(self, query, params=()):
        row = self.rows.get(params[0])
        if not row:
            return None
        q = " ".join(query.split())
        if q.startswith("SELECT footsteps, project_id"):
            return (row["footsteps"], row["project_id"])
        if q.startswith("SELECT trace_metadata"):
            return (row["trace_metadata"],)
        if q.startswith("SELECT footsteps FROM"):
            return (row["footsteps"],)
        return (row["footsteps"], row["explanation"], row["user_id"],
                row["project_id"], None)

    async def fetchall(self, query, params=()):
        return []


def _build():
    db = QueryAwareDB()

    async def audit(action, actor, detail):
        db.audits.append((action, actor, detail))

    router = create_stepstitch_router(
        get_user_id=lambda: "user-42",
        require_admin=lambda: {"user_id": "admin-1"},
        execute=db.execute,
        fetchone=db.fetchone,
        fetchall=db.fetchall,
        audit=audit,
        generate_playwright_test=generate_playwright_test,
        draft_adapters=default_draft_adapters(),
    )
    app = FastAPI()
    app.include_router(router, prefix="/api")
    return TestClient(app), db


def _ingest(client):
    payload = {
        "app_id": "marvox",
        "project_id": "proj-1",
        "explanation": "Submit failed, my SSN 123-45-6789",
        "footsteps": [
            {"timestamp": "t", "type": "navigation",
             "route": "/accounts/8675309/distributions", "label": "[masked]"},
            {"timestamp": "t", "type": "click",
             "route": "/accounts/8675309/distributions",
             "target": '[data-testid="submit"]', "label": "[masked]"},
            {"timestamp": "t", "type": "api_error",
             "route": "/accounts/8675309/distributions", "label": "[masked]",
             "metadata": {"status": 500,
                          "endpoint": "https://portal.example.test/api/accounts/8675309",
                          "message": "raw message with SSN 123-45-6789"}},
        ],
        "metadata": {"sdk_version": "0.4.0"},
    }
    r = client.post(f"{_PFX}/session", json=payload)
    assert r.status_code == 200
    return r.json()["trace_id"]


def _make_call_route(client):
    async def call_route(method, path, params):
        url = f"{_PFX}{path}"
        resp = client.get(url, params=params) if method == "GET" \
            else client.post(url, params=params)
        resp.raise_for_status()
        return resp.json()
    return call_route


# --- P1: safety -----------------------------------------------------------------------

def test_no_destructive_mcp_tool():
    # Module self-check (also runs at import) plus an explicit per-op assertion.
    assert_no_destructive_operation()
    for op in COPILOT_SAFE_OPERATIONS:
        assert not op.is_destructive, f"destructive tool exposed: {op.tool_name}"
        assert op.method.upper() in {"GET", "POST"}
    names = {op.tool_name for op in COPILOT_SAFE_OPERATIONS}
    # Tools that must NEVER exist on the MCP surface.
    for forbidden in ("delete_user_traces", "purge_expired", "get_session", "set_capture"):
        assert forbidden not in names


def test_tool_definitions_have_schemas():
    defs = build_tool_definitions()
    assert len(defs) == len(COPILOT_SAFE_OPERATIONS)
    for d in defs:
        assert d["name"] and d["description"]
        assert d["inputSchema"]["type"] == "object"
    # Per-trace tools require trace_id; the list tool does not.
    by_name = {d["name"]: d for d in defs}
    assert by_name["get_trace_summary"]["inputSchema"]["required"] == ["trace_id"]
    assert "required" not in by_name["list_recent_traces"]["inputSchema"]


def test_function_tool_specs_match_mcp_tools_exactly():
    # The OpenAI/JSON-Schema function projection (for non-MCP models like Hermes) is drawn
    # from the same SSOT and must not drift from the MCP tool definitions.
    mcp = {d["name"]: d["inputSchema"] for d in build_tool_definitions()}
    specs = build_function_tool_specs()
    assert len(specs) == len(COPILOT_SAFE_OPERATIONS)
    fn = {}
    for s in specs:
        assert s["type"] == "function"
        f = s["function"]
        fn[f["name"]] = f["parameters"]
        assert f["description"]
    assert fn == mcp, "function-tool projection drifted from the MCP tool set"


# --- P0: three-way parity (MCP <-> OpenAPI <-> live routes) ---------------------------

def test_mcp_matches_openapi_exactly():
    spec = json.loads(_OPENAPI.read_text())
    spec_ops = {}
    for path, ops in spec["paths"].items():
        for method, body in ops.items():
            spec_ops[body["operationId"]] = (method.upper(), path)
    mcp_ops = {op.operation_id: (op.method.upper(), op.path)
               for op in COPILOT_SAFE_OPERATIONS}
    assert mcp_ops == spec_ops, "MCP tools and openapi-v2.json have drifted apart"


def test_mcp_paths_are_real_routes():
    client, _ = _build()
    live = set()
    for route in client.app.routes:
        path = getattr(route, "path", "")
        if path.startswith(_PFX):
            live.add(path.replace(_PFX, "", 1))
    for op in COPILOT_SAFE_OPERATIONS:
        assert op.path in live, f"MCP tool {op.tool_name} path {op.path} has no live route"
    assert SERVICE_PREFIX == "/stepstitch/v1"


# --- P1: end-to-end — dispatching a tool drives the real, audited service -------------

def test_dispatch_drives_service_sanitized_and_audited():
    client, db = _build()
    tid = _ingest(client)
    call = _make_call_route(client)

    summary = run(dispatch_tool("get_trace_summary", {"trace_id": tid}, call))
    assert summary["summary"]["route"] == "/accounts/:id/distributions"
    assert "8675309" not in json.dumps(summary)
    assert "123-45-6789" not in json.dumps(summary)

    repl = run(dispatch_tool("get_replayability_score", {"trace_id": tid}, call))
    assert repl["replayability"]["grade"] in {"A", "B", "C", "D", "F"}

    repro = run(dispatch_tool("generate_playwright_repro", {"trace_id": tid}, call))
    assert "test(" in repro["playwright_code"] or "import" in repro["playwright_code"]

    fs = run(dispatch_tool("create_fs_export_preview", {"trace_id": tid}, call))
    assert fs["target_pack"] == "financial-services-support"
    assert "123-45-6789" not in json.dumps(fs)

    # Every read went through the service's audit path.
    actions = {a[0] for a in db.audits}
    assert {"stepstitch.summary", "stepstitch.replayability", "stepstitch.compile",
            "stepstitch.financial_services_export_preview"} <= actions


def test_dispatch_rejects_unknown_tool_and_missing_arg():
    client, _ = _build()
    call = _make_call_route(client)
    try:
        run(dispatch_tool("rm_rf", {}, call))
        raise AssertionError("expected KeyError")
    except KeyError:
        pass
    try:
        run(dispatch_tool("get_trace_summary", {}, call))
        raise AssertionError("expected ValueError")
    except ValueError:
        pass


def run(coro):
    import asyncio
    return asyncio.get_event_loop().run_until_complete(coro)
