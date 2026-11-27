"""Ingest limits on the real host, against the real local store.

The ingest token is public by design, so the host — not the SDK — bounds what a report can
cost: how big one may be, how many fields it may carry, and how often anyone may send one.
A real SDK report must still pass untouched.
"""
from fastapi.testclient import TestClient

from server.audit import make_db_audit
from server.auth import build_auth
from server.host import build_app
from server.localdb import build_local_db_callables, connect_local
from stepstitch_service.ingest_limits import IngestLimits

ADMIN = "admin-secret"
INGEST = "ingest-secret"
_PFX = "/api/stepstitch/v1"


def _client(tmp_path, limits=None):
    conn = connect_local(tmp_path / "local.db")
    get_user_id, require_admin = build_auth(ADMIN, INGEST)
    execute, fetchone, fetchall = build_local_db_callables(conn)
    app = build_app(
        get_user_id=get_user_id, require_admin=require_admin,
        execute=execute, fetchone=fetchone, fetchall=fetchall,
        audit=make_db_audit(execute), admin_token=ADMIN, ingest_token=INGEST,
        local_mode=True, base_url="http://127.0.0.1:4321", ingest_limits=limits,
    )
    return TestClient(app), conn


def _report(steps=2, **overrides):
    footsteps = [{"timestamp": f"t{i}", "type": "click", "route": "/transfer",
                  "target": "#send", "label": "[masked]"} for i in range(steps)]
    body = {"app_id": "tiny-transfer", "explanation": "send failed",
            "footsteps": footsteps, "metadata": {"sdk_version": "0.12.0"}}
    body.update(overrides)
    return body


def _post(client, body):
    return client.post(f"{_PFX}/session", json=body,
                       headers={"Authorization": f"Bearer {INGEST}"})


def _traces(conn):
    return conn.execute("SELECT COUNT(*) FROM stepstitch_traces").fetchone()[0]


def test_a_real_sdk_sized_report_still_lands(tmp_path):
    client, conn = _client(tmp_path)
    r = _post(client, _report(steps=50))  # the SDK's default buffer
    assert r.status_code == 200, r.text
    assert _traces(conn) == 1


def test_the_host_applies_limits_by_default(tmp_path):
    """No ingest_limits argument means the env defaults — never unlimited."""
    client, conn = _client(tmp_path)
    r = _post(client, _report(explanation="x" * 400_000))
    assert r.status_code == 413
    assert _traces(conn) == 0


def test_a_flood_from_one_client_is_429_and_stores_nothing_more(tmp_path):
    client, conn = _client(tmp_path, IngestLimits(per_client_per_minute=3,
                                                  global_per_minute=0))
    codes = [_post(client, _report()).status_code for _ in range(5)]
    assert codes == [200, 200, 200, 429, 429]
    assert _traces(conn) == 3


def test_too_many_footsteps_is_refused_at_the_door(tmp_path):
    client, conn = _client(tmp_path, IngestLimits(max_body_bytes=0,
                                                  per_client_per_minute=0,
                                                  global_per_minute=0))
    r = _post(client, _report(steps=501))
    assert r.status_code == 422
    assert _traces(conn) == 0


def test_an_overlong_route_or_selector_is_refused(tmp_path):
    client, conn = _client(tmp_path, IngestLimits(max_body_bytes=0,
                                                  per_client_per_minute=0,
                                                  global_per_minute=0))
    long_route = _report()
    long_route["footsteps"][0]["route"] = "/" + "a" * 5000
    long_target = _report()
    long_target["footsteps"][0]["target"] = "#" + "b" * 5000
    assert _post(client, long_route).status_code == 422
    assert _post(client, long_target).status_code == 422
    assert _traces(conn) == 0


def test_metadata_with_too_many_keys_is_refused(tmp_path):
    client, conn = _client(tmp_path, IngestLimits(max_body_bytes=0,
                                                  per_client_per_minute=0,
                                                  global_per_minute=0))
    r = _post(client, _report(metadata={f"k{i}": i for i in range(200)}))
    assert r.status_code == 422
    assert _traces(conn) == 0


def test_operator_routes_are_not_rate_limited(tmp_path):
    client, _ = _client(tmp_path, IngestLimits(per_client_per_minute=1,
                                               global_per_minute=1))
    _post(client, _report())
    for _ in range(5):
        r = client.get(f"{_PFX}/sessions", headers={"Authorization": f"Bearer {ADMIN}"})
        assert r.status_code == 200, r.text
