"""Project reproduction config — host endpoints and effect on compiled repros.

The config is what turns a structural trace into a runnable regression test: base URL,
concrete route values, synthetic form values, auth fixture. These tests prove the round trip,
that invalid input produces an actionable 400 rather than a traceback, that the stored config
actually reaches the compiler, and that credentials are refused at the boundary.

In-memory fakes — no Postgres.
"""
import json

from fastapi import FastAPI
from fastapi.testclient import TestClient

from server.auth import build_auth
from server.host import build_app

ADMIN = "admin-secret"
INGEST = "ingest-secret"
_PFX = "/api/stepstitch/v1"

FOOTSTEPS = [
    {"timestamp": "2026-06-02T00:00:00Z", "type": "navigation",
     "route": "/accounts/:id/transfer", "label": "[masked]"},
    {"timestamp": "2026-06-02T00:00:01Z", "type": "input",
     "route": "/accounts/:id/transfer", "target": "[data-testid=contact-email]",
     "label": "[masked]"},
    {"timestamp": "2026-06-02T00:00:02Z", "type": "click",
     "route": "/accounts/:id/transfer", "target": "[data-testid=send]", "label": "[masked]"},
    {"timestamp": "2026-06-02T00:00:03Z", "type": "api_error",
     "route": "/accounts/:id/transfer",
     "metadata": {"status": 500, "endpoint": "/api/accounts/:id/transfers", "method": "POST"}},
]


class FakeDB:
    def __init__(self):
        self.traces = {}
        self.config = {}
        self.audits = []

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
        if "count(*)" in s:
            return (0,)
        row = self.traces.get(params[0])
        if not row:
            return None
        if s.startswith("SELECT footsteps, project_id, trace_metadata"):
            return (row["footsteps"], row["project_id"], row["trace_metadata"])
        if s.startswith("SELECT footsteps, project_id"):
            return (row["footsteps"], row["project_id"])
        if s.startswith("SELECT trace_metadata"):
            return (row["trace_metadata"],)
        if s.startswith("SELECT footsteps FROM"):
            return (row["footsteps"],)
        return (row["footsteps"], row["explanation"], row["user_id"], row["project_id"], None)

    async def fetchall(self, query, params=()):
        return []


def _client(base_url=None):
    db = FakeDB()
    get_user_id, require_admin = build_auth(ADMIN, INGEST)

    async def audit(action, actor, detail):
        db.audits.append((action, actor, detail))

    app: FastAPI = build_app(
        get_user_id=get_user_id, require_admin=require_admin,
        execute=db.execute, fetchone=db.fetchone, fetchall=db.fetchall,
        admin_token=ADMIN, ingest_token=INGEST, audit=audit, base_url=base_url,
    )
    return TestClient(app), db


def _h(tok):
    return {"Authorization": f"Bearer {tok}"}


def _ingest(client):
    r = client.post(f"{_PFX}/session", headers=_h(INGEST), json={
        "app_id": "demo", "project_id": "demo", "footsteps": FOOTSTEPS,
        "consent_version": "v1",
    })
    assert r.status_code == 200, r.text
    return r.json()["trace_id"]


def _repro(client, trace_id):
    r = client.get(f"{_PFX}/session/{trace_id}/playwright", headers=_h(ADMIN))
    assert r.status_code == 200, r.text
    return r.json()["playwright_code"]


# --- round trip ---------------------------------------------------------------------------

def test_config_round_trips_through_the_admin_api():
    client, db = _client()
    doc = {
        "base_url": "https://staging.example.test",
        "route_params": {"id": "1001"},
        "auth": {"fixture": "tests/auth.setup.ts", "env_vars": ["E2E_USER_EMAIL"]},
    }
    put = client.put("/admin/config/repro", headers=_h(ADMIN), json={"config": doc})
    assert put.status_code == 200, put.text

    got = client.get("/admin/config/repro", headers=_h(ADMIN)).json()
    assert got["config"]["base_url"] == "https://staging.example.test"
    assert got["config"]["route_params"] == {"id": "1001"}
    assert json.loads(db.config["repro_config"])["auth"]["fixture"] == "tests/auth.setup.ts"


def test_empty_config_is_the_default():
    client, _ = _client()
    got = client.get("/admin/config/repro", headers=_h(ADMIN)).json()
    assert got["status"] == "ok"
    assert got["config"] == {}
    assert got["default_base_url"] == "http://localhost:3000"


def test_readiness_is_reported_for_the_console_checklist():
    client, _ = _client()
    got = client.get("/admin/config/repro", headers=_h(ADMIN)).json()
    items = {i["id"]: i for i in got["readiness"]}
    assert items["base_url"]["ready"] is False
    client.put("/admin/config/repro", headers=_h(ADMIN),
               json={"config": {"base_url": "https://staging.example.test"}})
    items = {i["id"]: i
             for i in client.get("/admin/config/repro", headers=_h(ADMIN)).json()["readiness"]}
    assert items["base_url"]["ready"] is True


# --- validation ---------------------------------------------------------------------------

def test_invalid_config_is_a_400_with_an_actionable_message():
    client, db = _client()
    r = client.put("/admin/config/repro", headers=_h(ADMIN),
                   json={"config": {"base_url": "staging.example.test"}})
    assert r.status_code == 400
    assert "http://" in r.json()["detail"]
    assert "repro_config" not in db.config, "an invalid document must not be stored"


def test_credentials_are_refused_at_the_host_boundary():
    client, db = _client()
    r = client.put("/admin/config/repro", headers=_h(ADMIN),
                   json={"config": {"input_values": {"by_selector": {"#api_key": "sk-live-x"}}}})
    assert r.status_code == 400
    assert "never stores credentials" in r.json()["detail"]
    assert "repro_config" not in db.config


def test_config_writes_are_audited_by_shape_not_by_value():
    client, db = _client()
    client.put("/admin/config/repro", headers=_h(ADMIN),
               json={"config": {"base_url": "https://staging.example.test",
                                "route_params": {"id": "1001"}}})
    actions = [a for a in db.audits if a[0] == "stepstitch.repro_config_update"]
    assert actions, "a config change must be audited"
    detail = actions[0][2]
    assert detail["route_params"] == 1
    assert "1001" not in json.dumps(detail), "audit must record the shape, not the values"


def test_config_endpoints_require_admin():
    client, _ = _client()
    assert client.get("/admin/config/repro").status_code in (401, 403)
    assert client.get("/admin/config/repro", headers=_h(INGEST)).status_code in (401, 403)
    assert client.put("/admin/config/repro", headers=_h(INGEST),
                      json={"config": {}}).status_code in (401, 403)


# --- the config actually reaches the compiler ----------------------------------------------

def test_stored_config_reaches_the_generated_reproduction():
    client, _ = _client()
    trace_id = _ingest(client)
    assert "/accounts/:id/transfer" in _repro(client, trace_id)   # templated before config

    client.put("/admin/config/repro", headers=_h(ADMIN), json={"config": {
        "base_url": "https://staging.example.test",
        "route_params": {"id": "1001"},
    }})
    code = _repro(client, trace_id)
    assert "https://staging.example.test/accounts/1001/transfer" in code
    assert "NEEDS-CONFIG: no value for" not in code


def test_config_changes_apply_without_a_restart():
    client, _ = _client()
    trace_id = _ingest(client)
    client.put("/admin/config/repro", headers=_h(ADMIN),
               json={"config": {"route_params": {"id": "1001"}}})
    assert "/accounts/1001/transfer" in _repro(client, trace_id)
    client.put("/admin/config/repro", headers=_h(ADMIN),
               json={"config": {"route_params": {"id": "2002"}}})
    assert "/accounts/2002/transfer" in _repro(client, trace_id)


def test_env_base_url_is_used_when_no_project_override_is_stored():
    client, _ = _client(base_url="https://env.example.test")
    trace_id = _ingest(client)
    code = _repro(client, trace_id)
    assert "https://env.example.test/accounts/" in code
    assert "READY       Application base URL" in code


def test_project_config_overrides_the_env_base_url():
    client, _ = _client(base_url="https://env.example.test")
    trace_id = _ingest(client)
    client.put("/admin/config/repro", headers=_h(ADMIN),
               json={"config": {"base_url": "https://project.example.test"}})
    code = _repro(client, trace_id)
    assert "https://project.example.test/accounts/" in code
    assert "env.example.test" not in code


def test_a_corrupt_stored_config_does_not_break_repro_generation():
    # Repro generation must degrade to defaults, never 500.
    client, db = _client()
    trace_id = _ingest(client)
    db.config["repro_config"] = "{not json"
    code = _repro(client, trace_id)
    assert "test('StepStitch reproduction'" in code


def test_admin_status_reports_setup_readiness():
    client, _ = _client()
    status = client.get("/admin/status", headers=_h(ADMIN)).json()
    assert status["base_url_configured"] is False
    assert status["repro_config_ready"] is False
    client.put("/admin/config/repro", headers=_h(ADMIN), json={"config": {
        "base_url": "https://staging.example.test", "route_params": {"id": "1001"},
    }})
    status = client.get("/admin/status", headers=_h(ADMIN)).json()
    assert status["base_url_configured"] is True
    assert status["repro_config_ready"] is True


# --- downloads ------------------------------------------------------------------------------

def test_reproduction_downloads_as_a_spec_file():
    client, _ = _client()
    trace_id = _ingest(client)
    r = client.get(f"{_PFX}/session/{trace_id}/playwright/download", headers=_h(ADMIN))
    assert r.status_code == 200
    assert "attachment;" in r.headers["content-disposition"]
    assert r.headers["content-disposition"].endswith('-repro.spec.ts"')
    assert r.text.startswith("import { test, expect }")


def test_attestation_downloads_as_a_json_bundle():
    client, _ = _client()
    trace_id = _ingest(client)
    r = client.get(f"{_PFX}/session/{trace_id}/attestation/download", headers=_h(ADMIN))
    assert r.status_code == 200
    assert "attachment;" in r.headers["content-disposition"]
    body = r.json()
    assert body["bundle_sha256"].startswith("sha256:")
    assert body["bundle"]["trace_id"] == trace_id


def test_download_filenames_cannot_smuggle_a_path_or_header_break():
    client, _ = _client()
    r = client.get(f"{_PFX}/session/..%2f..%2fetc%2fpasswd/playwright/download",
                   headers=_h(ADMIN))
    # Either the trace does not exist (404) or the name was sanitized — never a raw path.
    if r.status_code == 200:
        disposition = r.headers["content-disposition"]
        assert "/" not in disposition.split("filename=")[1]
        assert "\n" not in disposition


def test_downloads_require_admin():
    client, _ = _client()
    trace_id = _ingest(client)
    for path in ("playwright/download", "attestation/download"):
        r = client.get(f"{_PFX}/session/{trace_id}/{path}", headers=_h(INGEST))
        assert r.status_code in (401, 403), path
