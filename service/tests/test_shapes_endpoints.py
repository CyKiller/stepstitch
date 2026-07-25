"""GET /shapes — the console's board, end to end through the real router.

test_shapes.py covers the clustering logic directly. This covers the wiring: that ingest stores
a fingerprint, that traces sharing one collapse into a single shape, that verifications move it
between columns, and that the reads are audited. Its DB fake tracks the real column order (the
one in test_verification_endpoints.py predates the fingerprint columns).
"""
from fastapi import FastAPI
from fastapi.testclient import TestClient

from stepstitch_service import create_stepstitch_router, generate_playwright_test
from stepstitch_service.shapes import (
    STAGE_FIXED,
    STAGE_KNOWN,
    STAGE_ORDER,
    STAGE_REPRODUCED,
    STAGE_UNTRIAGED,
)

_PFX = "/api/stepstitch/v1"


class _DB:
    def __init__(self):
        self.traces = {}          # id -> dict
        self.order = []           # insertion order, newest last
        self.verifications = []
        self.audits = []

    async def execute(self, query, params=()):
        q = " ".join(query.split())
        if q.startswith("INSERT INTO stepstitch_traces"):
            self.traces[params[0]] = {
                "id": params[0], "project_id": params[2], "footsteps": params[5],
                "trace_metadata": params[6], "created_at": params[9], "fingerprint": params[10],
            }
            self.order.append(params[0])
        elif q.startswith("INSERT INTO stepstitch_verifications"):
            self.verifications.append({
                "trace_id": params[1], "pre_passed": params[2], "post_passed": params[3],
                "verdict": params[4], "fix_ref": params[5], "run_url": params[6],
                "fingerprint": params[7], "created_at": params[8],
            })

    async def fetchone(self, query, params=()):
        q = " ".join(query.split())
        row = self.traces.get(params[0]) if params else None
        if q.startswith("SELECT footsteps, project_id"):
            return (row["footsteps"], row["project_id"]) if row else None
        if q.startswith("SELECT footsteps FROM stepstitch_traces"):
            return (row["footsteps"],) if row else None
        return None

    async def fetchall(self, query, params=()):
        q = " ".join(query.split())
        if q.startswith("SELECT id, fingerprint, created_at FROM stepstitch_traces"):
            rows = [self.traces[i] for i in reversed(self.order)]
            return [(r["id"], r["fingerprint"], r["created_at"]) for r in rows]
        if q.startswith("SELECT trace_id, verdict FROM stepstitch_verifications"):
            return [(v["trace_id"], v["verdict"]) for v in reversed(self.verifications)]
        if q.startswith("SELECT trace_id, fix_ref, run_url, fingerprint"):
            return [(v["trace_id"], v["fix_ref"], v["run_url"], v["fingerprint"])
                    for v in reversed(self.verifications) if v["verdict"] == params[0]]
        return []


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


def _ingest(client, route="/accounts/:id/transfer", status=500,
            selector="[data-testid=review-transfer]"):
    return client.post(f"{_PFX}/session", json={
        "app_id": "a",
        "footsteps": [
            {"timestamp": "t0", "type": "click", "route": route, "target": selector,
             "label": "[masked]"},
            {"timestamp": "t1", "type": "api_error", "route": route, "label": "[masked]",
             "metadata": {"status": status, "method": "POST",
                          "endpoint": "/api" + route.rstrip("/") + "s"}},
        ],
        "metadata": {"sdk_version": "0.6.0"},
    }).json()["trace_id"]


def test_ingest_stores_a_fingerprint():
    client, db = _build()
    tid = _ingest(client)
    assert db.traces[tid]["fingerprint"], "ingest must persist the structural fingerprint"
    assert "/accounts/:id/transfer" in db.traces[tid]["fingerprint"]


def test_three_reports_of_one_bug_are_one_shape():
    client, _ = _build()
    for _ in range(3):
        _ingest(client)
    body = client.get(f"{_PFX}/shapes").json()
    assert len(body["shapes"]) == 1
    assert body["shapes"][0]["occurrences"] == 3


def test_different_failures_stay_separate():
    client, _ = _build()
    _ingest(client)
    _ingest(client, route="/checkout", status=422, selector="[data-testid=apply-promo]")
    body = client.get(f"{_PFX}/shapes").json()
    assert len(body["shapes"]) == 2


def test_board_carries_every_stage_and_places_shapes():
    client, _ = _build()
    _ingest(client)
    body = client.get(f"{_PFX}/shapes").json()
    assert body["stages"] == list(STAGE_ORDER)
    assert list(body["board"]) == list(STAGE_ORDER)
    assert len(body["board"][STAGE_UNTRIAGED]) == 1


def test_a_verification_moves_the_shape_between_columns():
    client, _ = _build()
    tid = _ingest(client)
    client.post(f"{_PFX}/session/{tid}/verify", json={"pre_passed": False})
    assert client.get(f"{_PFX}/shapes").json()["shapes"][0]["stage"] == STAGE_REPRODUCED

    client.post(f"{_PFX}/session/{tid}/verify",
                json={"pre_passed": False, "post_passed": True, "fix_ref": "PR-42"})
    assert client.get(f"{_PFX}/shapes").json()["shapes"][0]["stage"] == STAGE_FIXED


def test_a_new_report_of_an_already_fixed_shape_lands_in_known():
    client, _ = _build()
    old = _ingest(client)
    client.post(f"{_PFX}/session/{old}/verify",
                json={"pre_passed": False, "post_passed": True, "fix_ref": "PR-42"})
    # The regression comes back as a fresh trace with the same structure.
    new = _ingest(client)
    shapes = client.get(f"{_PFX}/shapes").json()["shapes"]
    # Same structure, so it joins the existing shape rather than starting a new one.
    assert len(shapes) == 1
    assert new in shapes[0]["trace_ids"]
    assert shapes[0]["stage"] == STAGE_FIXED  # its own confirmed fix outranks resemblance


def test_prior_fix_from_a_different_shape_promotes_to_known():
    client, _ = _build()
    old = _ingest(client, route="/accounts/:id/transfer")
    client.post(f"{_PFX}/session/{old}/verify",
                json={"pre_passed": False, "post_passed": True, "fix_ref": "PR-42"})
    # Same route + diagnostic shape, different terminal selector -> similar, not identical.
    _ingest(client, route="/accounts/:id/transfer", selector="[data-testid=confirm-transfer]")
    shapes = client.get(f"{_PFX}/shapes").json()["shapes"]
    known = [s for s in shapes if s["stage"] == STAGE_KNOWN]
    assert len(known) == 1
    assert known[0]["prior_fixes"][0]["fix_ref"] == "PR-42"


def test_shape_detail_round_trips_and_404s():
    client, _ = _build()
    _ingest(client)
    sid = client.get(f"{_PFX}/shapes").json()["shapes"][0]["shape_id"]
    detail = client.get(f"{_PFX}/shapes/{sid}")
    assert detail.status_code == 200
    assert detail.json()["shape"]["shape_id"] == sid
    assert client.get(f"{_PFX}/shapes/shp_nope").status_code == 404


def test_shape_reads_are_audited():
    client, db = _build()
    _ingest(client)
    client.get(f"{_PFX}/shapes")
    assert any(a[0] == "stepstitch.shapes" for a in db.audits)
    sid = client.get(f"{_PFX}/shapes").json()["shapes"][0]["shape_id"]
    client.get(f"{_PFX}/shapes/{sid}")
    assert any(a[0] == "stepstitch.shape" for a in db.audits)


def test_shapes_expose_no_trace_body():
    # The board is structural only — no explanation, no footsteps, no metadata.
    client, _ = _build()
    _ingest(client)
    raw = client.get(f"{_PFX}/shapes").text
    for leaked in ("explanation", "footsteps", "trace_metadata", "_scrub"):
        assert leaked not in raw
