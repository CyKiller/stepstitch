"""The public demo console: credential-free, read-only, and the same UI as production.

Two things must both hold, and they pull in opposite directions: anyone can look at it
without a token, and nobody can change anything through it. The negative tests below are the
ones that matter — a public endpoint that turned out to be writable would be the worst
possible outcome of shipping a demo.
"""
import json
import pathlib

import pytest
from fastapi.testclient import TestClient
from stepstitch_service.shapes import STAGE_ORDER

from server.demo import DATASET_PATH, build_demo_app, load_dataset

_API = "/api/stepstitch/v1"


@pytest.fixture(scope="module")
def client():
    return TestClient(build_demo_app())


# --- credential-free reads ------------------------------------------------------------------

def test_the_console_is_served_without_a_token(client):
    r = client.get("/dashboard")
    assert r.status_code == 200
    assert "StepStitch" in r.text


def test_the_demo_console_addresses_its_own_api(client):
    page = client.get("/dashboard").text
    assert "var DEMO = true" in page
    # The API base is derived from the page's own path, so the same template works at the
    # root, under /demo, and behind the marketing site's proxy.
    assert 'location.pathname.replace' in page
    assert "__DEMO_MODE__" not in page  # the placeholder must never ship raw


def test_the_demo_console_keeps_the_production_content_security_policy(client):
    csp = client.get("/dashboard").headers["content-security-policy"]
    assert "default-src 'none'" in csp
    assert "connect-src 'self'" in csp
    assert "frame-ancestors 'none'" in csp


def test_reads_need_no_credential(client):
    for path in ("/shapes", "/sessions", "/corpus"):
        assert client.get(f"{_API}{path}").status_code == 200, path
    for path in ("/status", "/config/scrub", "/config/repro", "/agents"):
        assert client.get(f"/admin{path}").status_code == 200, path


# --- read-only (the part that must not be wrong) ---------------------------------------------

@pytest.mark.parametrize("method,path", [
    ("POST", f"{_API}/session"),
    ("POST", f"{_API}/session/trc_demo_transfer_fixed/verify"),
    ("POST", f"{_API}/session/trc_demo_transfer_fixed/deliver"),
    ("POST", f"{_API}/session/trc_demo_transfer_fixed/github/pr"),
    ("POST", f"{_API}/maintenance/purge-expired"),
    ("DELETE", f"{_API}/session/by-user/demo-user-1"),
    ("PUT", "/admin/config/scrub"),
    ("PUT", "/admin/config/repro"),
    ("POST", "/admin/agents"),
])
def test_every_mutation_is_refused(client, method, path):
    r = client.request(method, path, json={})
    assert r.status_code == 403, f"{method} {path} returned {r.status_code}"
    assert "read-only" in r.text


def test_the_store_itself_cannot_write():
    """Belt and braces: even if a route slipped past the middleware, there is no write path.

    ``_ReadOnlyStore.execute`` records the attempt and does nothing, so this asserts the
    dataset is identical after a full read sweep.
    """
    from server.demo import _ReadOnlyStore

    dataset = load_dataset()
    store = _ReadOnlyStore(dataset)
    before = json.dumps(dataset, sort_keys=True)
    app = build_demo_app(dataset)
    inner = TestClient(app)
    inner.get(f"{_API}/shapes")
    inner.post(f"{_API}/session", json={"app_id": "x", "footsteps": []})
    assert json.dumps(load_dataset(), sort_keys=True) == before
    assert store.writes_attempted == 0


def test_ingest_cannot_add_a_trace(client):
    before = len(client.get(f"{_API}/sessions").json()["sessions"])
    client.post(f"{_API}/session", json={
        "app_id": "attacker", "footsteps": [
            {"timestamp": "t", "type": "click", "route": "/", "target": "#x"}]})
    after = len(client.get(f"{_API}/sessions").json()["sessions"])
    assert after == before


# --- the dataset shows the whole lifecycle ---------------------------------------------------

def test_every_lifecycle_stage_is_represented(client):
    shapes = client.get(f"{_API}/shapes").json()["shapes"]
    assert {s["stage"] for s in shapes} == set(STAGE_ORDER), (
        "the demo exists to show the whole journey; a missing stage is a missing story"
    )


def test_the_fixed_shape_carries_a_measured_red_then_green(client):
    shapes = client.get(f"{_API}/shapes").json()["shapes"]
    fixed = next(s for s in shapes if s["stage"] == "fixed")
    trace = fixed["representative_trace_id"]
    rows = client.get(f"{_API}/session/{trace}/verifications").json()["verifications"]
    confirmed = [v for v in rows if v["verdict"] == "confirmed_fixed"]
    assert confirmed, "the fixed shape must have a confirmed_fixed verdict"
    assert confirmed[0]["pre_passed"] is False   # it really failed before the fix…
    assert confirmed[0]["post_passed"] is True   # …and really passed after it


def test_a_repeat_failure_is_matched_against_the_fix_corpus(client):
    shapes = client.get(f"{_API}/shapes").json()["shapes"]
    known = next(s for s in shapes if s["stage"] == "known_shape")
    assert known["prior_fixes"], "known_shape means Fix Memory matched a prior fix"
    assert known["prior_fixes"][0]["fix_ref"]


def test_the_demo_shows_scrubbing_actually_happening(client):
    posture = client.get(
        f"{_API}/session/trc_demo_transfer_fixed/privacy-posture").json()
    assert posture["scrub"]["scrub_status"] == "scrubbed"
    assert "explanation" in posture["scrub"]["scrubbed_fields"]


def test_no_fake_npi_survives_into_the_served_dataset(client):
    """The demo's explanations deliberately contain card/email/SSN patterns so the scrub can
    be SEEN working. None of it may survive into what the console serves."""
    served = json.dumps(client.get(f"{_API}/sessions").json())
    for value in ("4111 1111 1111 1234", "dana.holt@example.test", "000-00-0000",
                  "555-012-3456"):
        assert value not in served, f"demo dataset leaked {value}"


def test_the_demo_generates_a_runnable_reproduction(client):
    code = client.get(
        f"{_API}/session/trc_demo_transfer_fixed/playwright").json()["playwright_code"]
    assert "import { test, expect" in code
    assert "demo-bank.example.test" in code       # a fictional host, never a real one
    assert "/accounts/1001/transfer" in code      # route params resolved by project config
    assert "NEEDS-CONFIG" not in code


def test_the_demo_produces_an_attestation(client):
    bundle = client.get(f"{_API}/session/trc_demo_transfer_fixed/attestation").json()
    assert bundle["bundle_sha256"].startswith("sha256:")
    assert bundle["bundle"]["verification"]["verdict"] == "confirmed_fixed"


def test_admin_status_reports_it_is_a_demo(client):
    status = client.get("/admin/status").json()
    assert status["demo"] is True
    assert status["traces"] == len(load_dataset()["traces"])


def test_no_agent_token_is_ever_exposed(client):
    body = client.get("/admin/agents").text
    assert "ssa_" not in body and "token" not in body.lower().replace("tokens", "")


# --- the committed dataset ---------------------------------------------------------------

def test_the_committed_dataset_matches_its_generator():
    """Drift guard, mirroring test_demo_bundle.py: the demo must be what the pipeline
    produces today, not what it produced when someone last remembered to regenerate."""
    import importlib.util

    script = pathlib.Path(__file__).resolve().parents[2] / "scripts" / "build_demo_dataset.py"
    spec = importlib.util.spec_from_file_location("build_demo_dataset", script)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    fresh = module.build()
    committed = load_dataset()
    assert committed == fresh, (
        f"{DATASET_PATH.name} is stale — run "
        "`PYTHONPATH=service python3 scripts/build_demo_dataset.py`"
    )


def test_the_dataset_says_it_is_synthetic():
    dataset = load_dataset()
    assert "Synthetic" in dataset["note"]
    assert "No real user data" in dataset["note"]
