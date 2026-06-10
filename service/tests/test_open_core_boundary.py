"""Open-core boundary proof (docs/PRODUCT-PLAN.md P3).

The open core (privacy/repro engine + MCP connector) must not import the COMMERCIAL
adapters (ServiceNow / Salesforce / Genesys, and the `bundle` factory). The boundary is
enforced here by static AST analysis — no import-linter install required — so the
commercial pack stays cleanly extractable into its own distribution. `.importlinter`
carries the same contract for teams that run `lint-imports` in CI.
"""
import ast
from pathlib import Path

_PKG = Path(__file__).resolve().parents[1] / "stepstitch_service"

# Filenames (module stems) that constitute the COMMERCIAL adapter pack.
_COMMERCIAL_STEMS = {"servicenow", "salesforce", "genesys", "bundle"}

# Core = every package module EXCEPT the commercial adapter modules themselves.
def _core_files():
    for path in _PKG.rglob("*.py"):
        if path.parent.name == "integrations" and path.stem in _COMMERCIAL_STEMS:
            continue
        yield path


def _referenced_tokens(tree: ast.AST):
    """All dotted-path segments + imported names referenced by import statements."""
    tokens = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                tokens.update(alias.name.split("."))
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                tokens.update(node.module.split("."))
            for alias in node.names:  # catches `from . import servicenow`
                tokens.add(alias.name)
    return tokens


def test_core_modules_do_not_import_commercial_adapters():
    violations = []
    for path in _core_files():
        tree = ast.parse(path.read_text(), filename=str(path))
        hits = _referenced_tokens(tree) & _COMMERCIAL_STEMS
        if hits:
            violations.append(f"{path.relative_to(_PKG)} imports commercial: {sorted(hits)}")
    assert not violations, "open-core boundary violated:\n" + "\n".join(violations)


def test_router_serves_reads_with_zero_adapters():
    """The open core must work with NO commercial adapters: reads succeed; export
    previews simply return an empty draft set rather than failing."""
    import json

    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from stepstitch_service import create_stepstitch_router, generate_playwright_test

    rows = {}

    async def execute(query, params=()):
        if query.strip().upper().startswith("INSERT"):
            rows[params[0]] = {"footsteps": params[5], "project_id": params[2]}

    async def fetchone(query, params=()):
        row = rows.get(params[0])
        if not row:
            return None
        q = " ".join(query.split())
        if q.startswith("SELECT footsteps, project_id"):
            return (row["footsteps"], row["project_id"])
        return (row["footsteps"],)

    async def fetchall(query, params=()):
        return []

    router = create_stepstitch_router(
        get_user_id=lambda: "u1",
        require_admin=lambda: {"user_id": "admin"},
        execute=execute, fetchone=fetchone, fetchall=fetchall,
        generate_playwright_test=generate_playwright_test,
        # NOTE: no draft_adapters — pure open core.
    )
    app = FastAPI()
    app.include_router(router, prefix="/api")
    client = TestClient(app)

    pfx = "/api/stepstitch/v1"
    tid = client.post(f"{pfx}/session", json={
        "app_id": "x", "footsteps": [
            {"timestamp": "t", "type": "api_error", "route": "/a/:id",
             "label": "[masked]", "metadata": {"status": 500}}],
        "metadata": {"sdk_version": "0.4.0"},
    }).json()["trace_id"]

    # Read-only surface works with no adapters.
    assert client.get(f"{pfx}/session/{tid}/summary").status_code == 200
    assert client.get(f"{pfx}/session/{tid}/playwright").status_code == 200
    # Export preview succeeds but yields no drafts (no commercial adapters configured).
    drafts = client.post(f"{pfx}/session/{tid}/export-preview").json()["drafts"]
    assert drafts == {}, f"expected empty drafts without adapters, got {json.dumps(drafts)}"
