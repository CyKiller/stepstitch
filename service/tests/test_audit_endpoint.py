"""The operator audit read endpoint (``GET /audit``).

Governance proof: every operator read is recorded to ``stepstitch_audit`` and an operator
can read that trail back — admin-gated, and reading it is itself audited. This is NOT an
MCP/Copilot tool (agents never see the audit log); ``test_mcp_surface.py`` guards that the
agent surface stays the eight read/draft tools only.
"""
import json
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from stepstitch_service import create_stepstitch_router, generate_playwright_test

_PFX = "/api/stepstitch/v1"


class AuditDB:
    """Persists audit rows (mirroring the host's make_db_audit) and answers the audit SELECT."""

    def __init__(self):
        self.audit_rows = []  # (id, action, actor, detail_json, created_at)

    async def execute(self, query, params=()):
        q = " ".join(query.split()).upper()
        if q.startswith("INSERT INTO STEPSTITCH_AUDIT"):
            self.audit_rows.append(tuple(params))

    async def fetchone(self, query, params=()):
        return None

    async def fetchall(self, query, params=()):
        q = " ".join(query.split())
        if "FROM stepstitch_audit" in q:
            rows = sorted(self.audit_rows, key=lambda r: r[4], reverse=True)
            if "WHERE action = ?" in q:
                rows = [r for r in rows if r[1] == params[0]]
            return rows[: params[-1]]  # honor LIMIT (last param)
        return []


def _client(require_admin=None):
    db = AuditDB()

    async def audit(action, actor, detail):
        await db.execute(
            "INSERT INTO stepstitch_audit (id, action, actor, detail, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (str(uuid.uuid4()), action, actor, json.dumps(detail),
             datetime.now(timezone.utc)),
        )

    router = create_stepstitch_router(
        get_user_id=lambda: "user-1",
        require_admin=require_admin or (lambda: {"user_id": "admin-1"}),
        execute=db.execute, fetchone=db.fetchone, fetchall=db.fetchall,
        audit=audit, generate_playwright_test=generate_playwright_test,
    )
    app = FastAPI()
    app.include_router(router, prefix="/api")
    return TestClient(app), db


def test_audit_read_returns_recorded_actions_and_is_itself_audited():
    client, db = _client()

    # A normal operator read records an audit row.
    assert client.get(f"{_PFX}/sessions?limit=5").status_code == 200

    out = client.get(f"{_PFX}/audit").json()
    actions = [e["action"] for e in out["entries"]]
    assert "stepstitch.list" in actions

    # detail round-trips as structured JSON (never a raw string blob).
    listed = next(e for e in out["entries"] if e["action"] == "stepstitch.list")
    assert isinstance(listed["detail"], dict)

    # Reading the audit log is itself audited.
    out2 = client.get(f"{_PFX}/audit").json()
    assert "stepstitch.audit_read" in [e["action"] for e in out2["entries"]]


def test_audit_action_filter():
    client, _ = _client()
    client.get(f"{_PFX}/sessions")
    client.get(f"{_PFX}/audit")  # records stepstitch.audit_read
    filtered = client.get(f"{_PFX}/audit?action=stepstitch.list").json()["entries"]
    assert filtered and all(e["action"] == "stepstitch.list" for e in filtered)


def test_audit_is_admin_gated():
    def deny():
        raise HTTPException(status_code=401, detail="admin required")

    client, _ = _client(require_admin=deny)
    assert client.get(f"{_PFX}/audit").status_code == 401
