"""GET /admin/session/{id}/execution — the "did anyone actually run this?" read.

Proves the endpoint composes the honest picture from data that already exists: the
execution state, the NAMED blockers (not a boolean), whether red and green really
ran, the per-trace privacy stamps, and the replayability score WITH its reasons.
Also covers the enriched /admin/status the setup panel reads.
"""
import json

from fastapi import FastAPI
from fastapi.testclient import TestClient

from server.auth import build_auth
from server.host import build_app

ADMIN = "admin-secret"
INGEST = "ingest-secret"

FOOTSTEPS = [
    {"timestamp": "t", "type": "navigation", "route": "/accounts/:id", "label": "[masked]"},
    {"timestamp": "t", "type": "click", "route": "/accounts/:id",
     "target": '[data-testid="pay"]', "label": "[masked]"},
    {"timestamp": "t", "type": "api_error", "route": "/accounts/:id", "label": "[masked]",
     "metadata": {"status": 500, "endpoint": "/api/pay"}},
]


class FakeDB:
    """In-memory stand-in with just the tables this endpoint reads."""

    def __init__(self, *, frozen=None, verifications=(), config=None):
        self.frozen = frozen
        self.verifications = list(verifications)
        self.config = dict(config or {})

    async def execute(self, query, params=()):
        s = " ".join(query.split()).upper()
        if s.startswith("DELETE FROM STEPSTITCH_CONFIG"):
            self.config.pop(params[0], None)
        elif s.startswith("INSERT INTO STEPSTITCH_CONFIG"):
            self.config[params[0]] = params[1]

    async def fetchone(self, query, params=()):
        s = " ".join(query.split())
        # Count queries first: "SELECT count(*) FROM stepstitch_traces" also matches the
        # table checks below, and it carries no params to key on.
        if "count(*)" in s:
            return (0,)
        if "FROM stepstitch_config" in s:
            v = self.config.get(params[0])
            return (v,) if v is not None else None
        if "FROM stepstitch_frozen_repros" in s:
            if not self.frozen:
                return None
            return (self.frozen["red_verdict"], self.frozen.get("sha256", "x" * 64),
                    self.frozen.get("frozen_at", "2026-08-04T00:00:00Z"))
        if "FROM stepstitch_traces" in s:
            if params[0] != "trc-1":
                return None
            return (json.dumps(FOOTSTEPS),
                    json.dumps({"_scrub": {"scrub_status": "scrubbed",
                                           "schema_status": "strict_schema_passed"}}))
        return None

    async def fetchall(self, query, params=()):
        s = " ".join(query.split())
        if "FROM stepstitch_verifications" in s:
            return [(v["pre_passed"], v["post_passed"], v["verdict"],
                     v["evidence_grade"], "2026-08-04T00:00:00Z")
                    for v in self.verifications]
        return []


def _client(db, profile="financial-services-enterprise", base_url=None):
    get_user_id, require_admin = build_auth(ADMIN, INGEST)
    app = build_app(
        get_user_id=get_user_id, require_admin=require_admin,
        execute=db.execute, fetchone=db.fetchone, fetchall=db.fetchall,
        admin_token=ADMIN, ingest_token=INGEST, profile=profile,
        base_url=base_url, local_mode=True,
    )
    outer = FastAPI()
    outer.mount("", app)
    return TestClient(app)


def _get(client, path):
    return client.get(path, headers={"Authorization": f"Bearer {ADMIN}"})


def test_draft_names_the_missing_setting_rather_than_a_boolean():
    # The trace's route is templated (/accounts/:id) and no fixture id is configured, so
    # the reproduction compiles but running it would test the configuration, not the bug.
    client = _client(FakeDB())
    body = _get(client, "/admin/session/trc-1/execution").json()
    assert body["execution_state"] == "draft"
    assert body["red_ran"] is False and body["green_ran"] is False
    blocker_ids = {b["id"] for b in body["blockers"]}
    assert "route_params" in blocker_ids
    for blocker in body["blockers"]:
        assert blocker["detail"], "a blocker with no detail is not actionable"
        assert ":id" in blocker["detail"] or "set " in blocker["detail"], (
            "the blocker must name the setting to change, not just the problem"
        )
    # The advisory auth item is reported in `readiness` but is NOT a blocker: running
    # unauthenticated is a limitation, not a reason the verdict would be meaningless.
    assert "auth" not in blocker_ids
    assert "auth" in {item["id"] for item in body["readiness"]}


def test_measured_red_then_green_reports_confirmed_fixed_with_its_grade():
    db = FakeDB(
        frozen={"red_verdict": "reproduced"},
        verifications=[{"pre_passed": False, "post_passed": True,
                        "verdict": "confirmed_fixed", "evidence_grade": "measured"}],
    )
    client = _client(db, base_url="https://staging.example.test")
    body = _get(client, "/admin/session/trc-1/execution").json()
    assert body["execution_state"] == "confirmed_fixed"
    assert body["red_ran"] is True and body["green_ran"] is True
    assert body["frozen_red_verdict"] == "reproduced"
    assert body["evidence_grade"] == "measured"


def test_sqlite_style_integer_booleans_do_not_become_a_false_green():
    # SQLite hands back 0/1; a naive read would turn "nobody ran the green half"
    # (None) into False and, worse, could read 0 as truthy in the wrong place.
    db = FakeDB(verifications=[{"pre_passed": 0, "post_passed": None,
                                "verdict": "reproduced_unfixed",
                                "evidence_grade": "asserted"}])
    client = _client(db, base_url="https://staging.example.test")
    body = _get(client, "/admin/session/trc-1/execution").json()
    assert body["execution_state"] == "reproduced"
    assert body["red_ran"] is True
    assert body["green_ran"] is False
    assert body["verifications"][0]["pre_passed"] is False
    assert body["verifications"][0]["post_passed"] is None


def test_the_evidence_panel_carries_the_honest_per_trace_stamps():
    client = _client(FakeDB(), base_url="https://staging.example.test")
    body = _get(client, "/admin/session/trc-1/execution").json()
    assert body["schema_status"] == "strict_schema_passed"
    assert body["scrub_status"] == "scrubbed"
    # Never claimed as verified: the app under test is operator-configured.
    assert body["customer_data_status"] == "not_verified"
    # A grade with no reasons is a number an operator cannot act on.
    assert "score" in body["replayability"] and "grade" in body["replayability"]
    assert "warnings" in body["replayability"]


def test_unknown_trace_is_404():
    client = _client(FakeDB())
    assert _get(client, "/admin/session/nope/execution").status_code == 404


def test_admin_status_names_each_missing_prerequisite():
    client = _client(FakeDB())
    body = _get(client, "/admin/status").json()
    ids = {item["id"] for item in body["readiness"]}
    # Per-item detail, not one boolean: the panel can name base URL and auth fixture
    # separately instead of saying "reproduction config: not ready".
    assert {"base_url", "auth"} <= ids
    assert "browser_available" in body
    assert body["strict_schema"] is False
    # Not a strict profile → the allowlist question does not apply.
    assert body["strict_allowlists_configured"] is None


def test_execution_is_available_on_a_deployed_host_not_only_local_mode():
    """Regression: the endpoint was registered inside the `if local_mode:` block next to
    freeze/verify-fix/reproduce. Those are gated because they spawn browsers and reach
    the network; this one is a pure read. The effect was that every deployed tenant —
    the audience this release targets — silently lost the Execution panel entirely."""
    db = FakeDB(frozen={"red_verdict": "reproduced"})
    get_user_id, require_admin = build_auth(ADMIN, INGEST)
    app = build_app(
        get_user_id=get_user_id, require_admin=require_admin,
        execute=db.execute, fetchone=db.fetchone, fetchall=db.fetchall,
        admin_token=ADMIN, ingest_token=INGEST,
        base_url="https://staging.example.test",
        local_mode=False,          # a DEPLOYED host
    )
    res = TestClient(app).get("/admin/session/trc-1/execution",
                              headers={"Authorization": f"Bearer {ADMIN}"})
    assert res.status_code == 200, "the execution read must exist on a deployed host"
    assert res.json()["execution_state"] == "reproduced"

    # …while the browser-spawning routes stay local-only, which is why the block exists.
    routes = {getattr(r, "path", "") for r in app.routes}
    assert "/admin/session/{trace_id}/execution" in routes
    for gated in ("reproduce", "freeze", "verify-fix"):
        assert f"/admin/session/{{trace_id}}/{gated}" not in routes, (
            f"{gated} spawns processes and must remain local-mode only"
        )


def test_half_configured_strict_allowlists_are_not_reported_as_configured():
    """Regression: this was computed as bool(approved_testids) alone. The strict profile
    also gates ROUTES, so approving testids while leaving route_templates empty still
    422s every single ingest — and the operator was told they were configured."""
    client = _client(FakeDB(), profile="financial-services-strict")
    hdr = {"Authorization": f"Bearer {ADMIN}"}

    # testids only — the exact half-configured trap.
    assert client.put("/admin/config/scrub", headers=hdr, json={
        "extra_redactions": [], "extra_forbidden_keys": [],
        "approved_testids": ["pay"], "route_templates": [],
    }).status_code == 200
    body = _get(client, "/admin/status").json()
    assert body["strict_allowlists_configured"] is False, (
        "testids without route templates must NOT report configured"
    )

    # routes only — the mirror image.
    client.put("/admin/config/scrub", headers=hdr, json={
        "extra_redactions": [], "extra_forbidden_keys": [],
        "approved_testids": [], "route_templates": ["/accounts/:id"],
    })
    assert _get(client, "/admin/status").json()["strict_allowlists_configured"] is False

    # both — genuinely usable.
    client.put("/admin/config/scrub", headers=hdr, json={
        "extra_redactions": [], "extra_forbidden_keys": [],
        "approved_testids": ["pay"], "route_templates": ["/accounts/:id"],
    })
    assert _get(client, "/admin/status").json()["strict_allowlists_configured"] is True


def test_an_unknown_browser_probe_result_is_cached_not_re_run_every_poll():
    """Regression: the cache keyed on `cached is not None`, so an UNKNOWN answer was
    never stored and every /admin/status poll respawned a 30s-timeout subprocess —
    the cost the async move was made to remove."""
    import stepstitch_service.host.host as host_mod

    host_mod._reset_browser_cache()
    calls = {"n": 0}

    def probe():
        calls["n"] += 1
        return None                      # the probe genuinely cannot tell

    original = host_mod._browser_present_blocking
    host_mod._browser_present_blocking = probe
    try:
        client = _client(FakeDB())
        for _ in range(3):
            assert _get(client, "/admin/status").json()["browser_available"] is None
        assert calls["n"] == 1, f"probed {calls['n']}x for 3 polls; unknown must cache"
    finally:
        host_mod._browser_present_blocking = original
        host_mod._reset_browser_cache()


def test_admin_status_warns_when_a_strict_profile_has_no_allowlists():
    # Deny-by-default with nothing approved refuses every semantic selector. Correct,
    # and silently catastrophic if the operator is never told.
    client = _client(FakeDB(), profile="financial-services-strict")
    body = _get(client, "/admin/status").json()
    assert body["strict_schema"] is True
    assert body["strict_allowlists_configured"] is False

    saved = client.put(
        "/admin/config/scrub",
        headers={"Authorization": f"Bearer {ADMIN}"},
        json={"extra_redactions": [], "extra_forbidden_keys": [],
              "approved_testids": ["pay"], "route_templates": ["/accounts/:id"]},
    )
    assert saved.status_code == 200
    body = _get(client, "/admin/status").json()
    assert body["strict_allowlists_configured"] is True
