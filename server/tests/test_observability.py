"""Observability + audit: Prometheus /metrics, request metering, durable audit sink."""
import asyncio

from fastapi import FastAPI
from fastapi.testclient import TestClient

from server.audit import make_db_audit, make_logging_audit
from server.auth import build_auth
from server.db import SCHEMA_SQL
from server.host import build_app
from server.metrics import Metrics

ADMIN = "admin-secret"
INGEST = "ingest-secret"


def run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


class _DB:
    def __init__(self):
        self.calls = []

    async def execute(self, query, params=()):
        self.calls.append((query, params))

    async def fetchone(self, query, params=()):
        return None

    async def fetchall(self, query, params=()):
        return []


def _client():
    db = _DB()
    get_user_id, require_admin = build_auth(ADMIN, INGEST)
    app: FastAPI = build_app(
        get_user_id=get_user_id, require_admin=require_admin,
        execute=db.execute, fetchone=db.fetchone, fetchall=db.fetchall,
    )
    return TestClient(app), db


def test_metrics_endpoint_reports_requests():
    client, _ = _client()
    client.get("/healthz")
    body = client.get("/metrics").text
    assert "stepstitch_requests_total" in body
    assert "stepstitch_request_duration_seconds_count" in body
    # The /healthz request was metered by its route template.
    assert 'route="/healthz"' in body


def test_metrics_uses_route_template_not_concrete_path():
    m = Metrics()
    m.observe("GET", "/session/{trace_id}/summary", 200, 0.01)
    out = m.render()
    assert 'route="/session/{trace_id}/summary"' in out
    assert "stepstitch_requests_total" in out


def test_db_audit_inserts_row():
    db = _DB()
    audit = make_db_audit(db.execute)
    run(audit("stepstitch.summary", "admin", {"trace_id": "t1"}))
    assert len(db.calls) == 1
    sql, params = db.calls[0]
    assert "INSERT INTO stepstitch_audit" in sql
    assert "stepstitch.summary" in params and "admin" in params


def test_logging_audit_does_not_raise():
    audit = make_logging_audit()
    run(audit("stepstitch.deliver", "ops", {"target": "servicenow"}))


def test_schema_includes_audit_table():
    assert "stepstitch_audit" in SCHEMA_SQL
