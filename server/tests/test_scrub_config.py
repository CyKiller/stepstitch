"""Scrub-policy editor — host endpoints + per-ingest tightening.

The dashboard can ADD custom redaction patterns; the host resolves the active policy per
ingest as (base profile + overrides). Overrides can only tighten — built-in PII redaction
always still fires. Uses in-memory fakes.
"""

from fastapi import FastAPI
from fastapi.testclient import TestClient
from stepstitch_service.scrubber import FINANCIAL_SERVICES_ENTERPRISE as BASE

from server.auth import build_auth
from server.host import apply_scrub_overrides, build_app

ADMIN = "admin-secret"
INGEST = "ingest-secret"
_PFX = "/api/stepstitch/v1"


class FakeDB:
    def __init__(self):
        self.traces = {}
        self.config = {}

    async def execute(self, query, params=()):
        s = " ".join(query.split()).upper()
        if s.startswith("INSERT INTO STEPSTITCH_TRACES"):
            self.traces[params[0]] = {
                "project_id": params[2], "user_id": params[3], "explanation": params[4],
                "footsteps": params[5], "trace_metadata": params[6],
            }
        elif s.startswith("DELETE FROM STEPSTITCH_CONFIG"):
            self.config.pop(params[0], None)
        elif s.startswith("INSERT INTO STEPSTITCH_CONFIG"):
            self.config[params[0]] = params[1]

    async def fetchone(self, query, params=()):
        s = " ".join(query.split())
        if "FROM stepstitch_config" in s:
            v = self.config.get(params[0])
            return (v,) if v is not None else None
        row = self.traces.get(params[0])
        if not row:
            return None
        if s.startswith("SELECT footsteps, project_id"):
            return (row["footsteps"], row["project_id"])
        if s.startswith("SELECT trace_metadata"):
            return (row["trace_metadata"],)
        if s.startswith("SELECT footsteps FROM"):
            return (row["footsteps"],)
        return (row["footsteps"], row["explanation"], row["user_id"], row["project_id"], None)

    async def fetchall(self, query, params=()):
        return []


def _client():
    db = FakeDB()
    get_user_id, require_admin = build_auth(ADMIN, INGEST)
    app: FastAPI = build_app(
        get_user_id=get_user_id, require_admin=require_admin,
        execute=db.execute, fetchone=db.fetchone, fetchall=db.fetchall,
        admin_token=ADMIN, ingest_token=INGEST,
    )
    return TestClient(app), db


def _h(tok):
    return {"Authorization": f"Bearer {tok}"}


def _put(client, patterns=(), keys=()):
    return client.put("/admin/config/scrub", headers=_h(ADMIN),
                      json={"extra_redactions": list(patterns),
                            "extra_forbidden_keys": list(keys)})


def _ingest(client, explanation):
    return client.post(f"{_PFX}/session", headers=_h(INGEST), json={
        "app_id": "demo", "explanation": explanation,
        "footsteps": [{"timestamp": "t", "type": "click", "route": "/x", "label": "ok"}],
        "metadata": {"sdk_version": "0.4.0"},
    })


def test_apply_overrides_is_pure_and_only_tightens():
    p = apply_scrub_overrides(BASE, {"extra_redactions": [["id", r"X\d+"]],
                                     "extra_forbidden_keys": ["user_agent"]})
    assert p.extra_redactions == (("id", r"X\d+"),)
    assert BASE.forbidden_keys <= p.all_forbidden_keys and "user_agent" in p.all_forbidden_keys


def test_put_then_get_roundtrips_and_validates_regex():
    client, _ = _client()
    assert _put(client, patterns=[["empid", r"EMP-\d+"]]).status_code == 200
    got = client.get("/admin/config/scrub", headers=_h(ADMIN)).json()
    assert got["base_profile"] == BASE.name
    assert got["extra_redactions"] == [["empid", r"EMP-\d+"]]
    # A bad regex rejects the whole save.
    assert _put(client, patterns=[["bad", r"([unclosed"]]).status_code == 400


def test_custom_pattern_redacts_at_ingest():
    client, db = _client()
    _put(client, patterns=[["empid", r"EMP-\d+"]])
    r = _ingest(client, "user hit a wall at EMP-42 on checkout")
    assert r.status_code == 200, r.text
    tid = r.json()["trace_id"]
    stored = db.traces[tid]["explanation"]
    assert "EMP-42" not in stored and "[redacted:custom:empid]" in stored


def test_builtins_still_fire_with_overrides_active():
    # Tightening with a custom pattern must NOT disable the built-in PII redaction.
    client, db = _client()
    _put(client, patterns=[["empid", r"EMP-\d+"]])
    tid = _ingest(client, "SSN 123-45-6789 plus EMP-9").json()["trace_id"]
    stored = db.traces[tid]["explanation"]
    assert "123-45-6789" not in stored and "[redacted:ssn]" in stored
    assert "EMP-9" not in stored


def test_preview_uses_candidate_patterns():
    client, _ = _client()
    resp = client.post("/admin/scrub/preview", headers=_h(ADMIN),
                       json={"text": "ref EMP-7",
                             "extra_redactions": [["empid", r"EMP-\d+"]]})
    out = resp.json()
    assert "EMP-7" not in out["redacted"] and "custom:empid" in out["kinds"]
