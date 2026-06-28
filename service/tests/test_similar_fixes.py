"""Fix Memory end-to-end: ingest -> verify (stores fingerprint) -> match a new trace.

A confirmed red->green fix becomes a structural fingerprint; a new trace of the same shape
surfaces it via GET /session/{id}/similar-fixes. Read-only, audited, NPI-free. In-memory fake.
"""
from fastapi import FastAPI
from fastapi.testclient import TestClient

from stepstitch_service import create_stepstitch_router, generate_playwright_test

_PFX = "/api/stepstitch/v1"


class CorpusDB:
    def __init__(self):
        self.traces = {}
        self.verifs = []
        self.audits = []

    async def execute(self, query, params=()):
        s = " ".join(query.split()).upper()
        if s.startswith("INSERT INTO STEPSTITCH_TRACES"):
            self.traces[params[0]] = {
                "project_id": params[2], "explanation": params[4], "footsteps": params[5],
            }
        elif s.startswith("INSERT INTO STEPSTITCH_VERIFICATIONS"):
            # id, trace_id, pre, post, verdict, fix_ref, run_url, fingerprint, created_at
            self.verifs.append({
                "trace_id": params[1], "verdict": params[4], "fix_ref": params[5],
                "run_url": params[6], "fingerprint": params[7],
            })

    async def fetchone(self, query, params=()):
        s = " ".join(query.split())
        row = self.traces.get(params[0]) if params else None
        if not row:
            return None
        if s.startswith("SELECT footsteps, project_id"):
            return (row["footsteps"], row["project_id"])
        if s.startswith("SELECT footsteps FROM"):
            return (row["footsteps"],)
        if s.startswith("SELECT trace_metadata"):
            return ("{}",)
        return (row["footsteps"], row["explanation"], "u", row["project_id"], None)

    async def fetchall(self, query, params=()):
        s = " ".join(query.split())
        if "FROM stepstitch_verifications" in s and "verdict = ?" in s:
            want = params[0]
            return [
                (v["trace_id"], v["fix_ref"], v["run_url"], v["fingerprint"])
                for v in self.verifs
                if v["verdict"] == want and v["fingerprint"] is not None
            ]
        return []


def _client():
    db = CorpusDB()

    async def audit(action, actor, detail):
        db.audits.append(action)

    router = create_stepstitch_router(
        get_user_id=lambda: "user-1",
        require_admin=lambda: {"user_id": "admin-1"},
        execute=db.execute, fetchone=db.fetchone, fetchall=db.fetchall,
        audit=audit, generate_playwright_test=generate_playwright_test,
    )
    app = FastAPI()
    app.include_router(router, prefix="/api")
    return TestClient(app), db


def _ingest(client, route="/accounts/8675309/transfer"):
    r = client.post(f"{_PFX}/session", json={
        "app_id": "demo", "project_id": "p1",
        "footsteps": [
            {"timestamp": "t", "type": "click", "route": route,
             "target": '[data-testid="pay"]', "label": "[masked]"},
            {"timestamp": "t", "type": "api_error", "route": route,
             "target": '[data-testid="pay"]', "label": "[masked]",
             "metadata": {"status": 500, "endpoint": "/api/accounts/8675309/transfers"}},
        ],
        "metadata": {"sdk_version": "0.5.0"},
    })
    assert r.status_code == 200, r.text
    return r.json()["trace_id"]


def test_confirmed_fix_is_matched_by_a_new_trace_of_the_same_shape():
    client, _ = _client()
    a = _ingest(client)
    # Confirm a red->green fix on trace A (stores its fingerprint).
    v = client.post(f"{_PFX}/session/{a}/verify",
                    json={"pre_passed": False, "post_passed": True, "fix_ref": "PR#1"})
    assert v.status_code == 200 and v.json()["verdict"] == "confirmed_fixed"

    # A new trace of the same shape surfaces the prior fix.
    b = _ingest(client, route="/accounts/42/transfer")  # different id, same template
    out = client.get(f"{_PFX}/session/{b}/similar-fixes").json()
    assert out["similar_fixes"], "expected a structural match to the prior fix"
    top = out["similar_fixes"][0]
    assert top["trace_id"] == a and top["fix_ref"] == "PR#1"
    assert top["similarity"] >= 0.9 and "same route" in top["reasons"]
    # The returned fingerprint is structural only — no raw ids leak.
    assert "8675309" not in str(out)


def test_self_is_excluded_and_unrelated_trace_has_no_match():
    client, _ = _client()
    a = _ingest(client)
    client.post(f"{_PFX}/session/{a}/verify",
                json={"pre_passed": False, "post_passed": True, "fix_ref": "PR#1"})
    # Querying the same trace excludes itself.
    assert client.get(f"{_PFX}/session/{a}/similar-fixes").json()["similar_fixes"] == []

    # An unrelated trace (different route, exception not api_error) matches nothing.
    other = client.post(f"{_PFX}/session", json={
        "app_id": "demo", "project_id": "p1",
        "footsteps": [{"timestamp": "t", "type": "exception", "route": "/login",
                       "label": "[masked]", "metadata": {"error_type": "TypeError"}}],
        "metadata": {"sdk_version": "0.5.0"},
    }).json()["trace_id"]
    assert client.get(f"{_PFX}/session/{other}/similar-fixes").json()["similar_fixes"] == []


def test_similar_fixes_requires_admin_and_is_audited():
    client, db = _client()
    b = _ingest(client)
    client.get(f"{_PFX}/session/{b}/similar-fixes")
    assert "stepstitch.similar_fixes" in db.audits
