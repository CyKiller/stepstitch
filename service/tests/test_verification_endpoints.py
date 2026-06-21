"""Verify endpoint computes the verdict; corpus lists confirmed fixes; all audited."""
from fastapi import FastAPI
from fastapi.testclient import TestClient

from stepstitch_service import create_stepstitch_router, generate_playwright_test

_PFX = "/api/stepstitch/v1"


class _DB:
    def __init__(self):
        self.traces = {}
        self.verifications = []
        self.audits = []

    async def execute(self, query, params=()):
        q = " ".join(query.split())
        if q.startswith("INSERT INTO stepstitch_traces"):
            self.traces[params[0]] = {"footsteps": params[5], "project_id": params[2]}
        elif q.startswith("INSERT INTO stepstitch_verifications"):
            self.verifications.append({
                "trace_id": params[1], "pre_passed": params[2], "post_passed": params[3],
                "verdict": params[4], "fix_ref": params[5], "run_url": params[6],
                "created_at": params[7],
            })

    async def fetchone(self, query, params=()):
        q = " ".join(query.split())
        if q.startswith("SELECT footsteps, project_id"):
            row = self.traces.get(params[0])
            return (row["footsteps"], row["project_id"]) if row else None
        if q.startswith("SELECT footsteps FROM stepstitch_traces"):
            row = self.traces.get(params[0])
            return (row["footsteps"],) if row else None
        return None

    async def fetchall(self, query, params=()):
        q = " ".join(query.split())
        if "FROM stepstitch_verifications WHERE trace_id" in q:
            rows = [v for v in self.verifications if v["trace_id"] == params[0]]
        elif "FROM stepstitch_verifications WHERE verdict" in q:
            rows = [v for v in self.verifications if v["verdict"] == params[0]]
        else:
            return []
        return [(v["trace_id"], v["pre_passed"], v["post_passed"], v["verdict"],
                 v["fix_ref"], v["run_url"], v["created_at"]) for v in rows]


def _build():
    db = _DB()

    async def audit(action, actor, detail):
        db.audits.append((action, detail))

    router = create_stepstitch_router(
        get_user_id=lambda: "u", require_admin=lambda: {"user_id": "admin"},
        execute=db.execute, fetchone=db.fetchone, fetchall=db.fetchall,
        audit=audit, generate_playwright_test=generate_playwright_test,
    )
    app = FastAPI()
    app.include_router(router, prefix="/api")
    return TestClient(app), db


def _ingest(client):
    return client.post(f"{_PFX}/session", json={
        "app_id": "a", "footsteps": [
            {"timestamp": "t", "type": "api_error", "route": "/x",
             "label": "[masked]", "metadata": {"status": 500}}],
        "metadata": {"sdk_version": "0.4.0"},
    }).json()["trace_id"]


def test_verify_missing_trace_404():
    client, _ = _build()
    assert client.post(f"{_PFX}/session/nope/verify",
                       json={"pre_passed": False}).status_code == 404


def test_verify_red_then_green_is_confirmed_and_audited():
    client, db = _build()
    tid = _ingest(client)
    r = client.post(f"{_PFX}/session/{tid}/verify",
                    json={"pre_passed": False, "post_passed": True, "fix_ref": "PR#9"})
    assert r.status_code == 200
    assert r.json()["verdict"] == "confirmed_fixed"
    assert any(a[0] == "stepstitch.verify" for a in db.audits)


def test_verify_pre_only_is_reproduced_unfixed():
    client, _ = _build()
    tid = _ingest(client)
    r = client.post(f"{_PFX}/session/{tid}/verify", json={"pre_passed": False})
    assert r.json()["verdict"] == "reproduced_unfixed"


def test_verifications_list_for_trace():
    client, _ = _build()
    tid = _ingest(client)
    client.post(f"{_PFX}/session/{tid}/verify",
                json={"pre_passed": False, "post_passed": True})
    r = client.get(f"{_PFX}/session/{tid}/verifications")
    assert r.status_code == 200
    items = r.json()["verifications"]
    assert len(items) == 1 and items[0]["verdict"] == "confirmed_fixed"


def test_corpus_lists_only_confirmed_fixed_by_default():
    client, _ = _build()
    tid = _ingest(client)
    client.post(f"{_PFX}/session/{tid}/verify",
                json={"pre_passed": False, "post_passed": True})
    client.post(f"{_PFX}/session/{tid}/verify",
                json={"pre_passed": False, "post_passed": False})
    r = client.get(f"{_PFX}/corpus")
    entries = r.json()["entries"]
    assert all(e["verdict"] == "confirmed_fixed" for e in entries)
    assert len(entries) == 1


def test_verifications_missing_trace_404():
    client, _ = _build()
    assert client.get(f"{_PFX}/session/nope/verifications").status_code == 404


def test_corpus_rejects_unknown_verdict():
    client, _ = _build()
    assert client.get(f"{_PFX}/corpus?verdict=garbage").status_code == 422


def test_verify_pre_passed_is_not_reproduced():
    client, _ = _build()
    tid = _ingest(client)
    r = client.post(f"{_PFX}/session/{tid}/verify", json={"pre_passed": True})
    assert r.json()["verdict"] == "not_reproduced"


def test_verify_red_then_red_is_not_fixed():
    client, _ = _build()
    tid = _ingest(client)
    r = client.post(f"{_PFX}/session/{tid}/verify",
                    json={"pre_passed": False, "post_passed": False})
    assert r.json()["verdict"] == "not_fixed"


def test_verify_rejects_non_http_run_url():
    # Dashboard renders run_url as a link; a javascript: scheme must never be storable.
    client, _ = _build()
    tid = _ingest(client)
    r = client.post(f"{_PFX}/session/{tid}/verify",
                    json={"pre_passed": False, "post_passed": True,
                          "run_url": "javascript:alert(document.cookie)"})
    assert r.status_code == 422


def test_verify_accepts_https_run_url():
    client, db = _build()
    tid = _ingest(client)
    r = client.post(f"{_PFX}/session/{tid}/verify",
                    json={"pre_passed": False, "post_passed": True,
                          "run_url": "https://ci.example.com/run/42"})
    assert r.status_code == 200
    assert db.verifications[-1]["run_url"] == "https://ci.example.com/run/42"
