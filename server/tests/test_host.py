"""StepStitch ingest host proof — auth gating + DB wiring, with in-memory fakes.

No live Postgres needed: ``build_app`` takes the DB callables directly, so we pass the
same in-memory fake the service tests use and exercise the real auth + router wiring.
"""
import shutil

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from server.auth import build_auth
from server.db import translate_placeholders
from server.host import build_app

ADMIN = "admin-secret"
INGEST = "ingest-secret"
_PFX = "/api/stepstitch/v1"


def test_translate_placeholders_to_asyncpg():
    assert translate_placeholders("WHERE a = ? AND b = ?") == "WHERE a = $1 AND b = $2"
    assert translate_placeholders("SELECT 1") == "SELECT 1"


def test_build_auth_requires_both_tokens():
    import pytest
    with pytest.raises(ValueError):
        build_auth("", INGEST)
    with pytest.raises(ValueError):
        build_auth(ADMIN, "")


class QueryAwareDB:
    def __init__(self):
        self.rows = {}

    async def execute(self, query, params=()):
        if query.strip().upper().startswith("INSERT"):
            self.rows[params[0]] = {
                "app_id": params[1], "project_id": params[2], "user_id": params[3],
                "explanation": params[4], "footsteps": params[5],
                "trace_metadata": params[6],
            }

    async def fetchone(self, query, params=()):
        row = self.rows.get(params[0])
        if not row:
            return None
        q = " ".join(query.split())
        if q.startswith("SELECT footsteps, project_id"):
            return (row["footsteps"], row["project_id"])
        if q.startswith("SELECT trace_metadata"):
            return (row["trace_metadata"],)
        if q.startswith("SELECT footsteps FROM"):
            return (row["footsteps"],)
        return (row["footsteps"], row["explanation"], row["user_id"],
                row["project_id"], None)

    async def fetchall(self, query, params=()):
        return []


def _client():
    db = QueryAwareDB()
    get_user_id, require_admin = build_auth(ADMIN, INGEST)
    app: FastAPI = build_app(
        get_user_id=get_user_id, require_admin=require_admin,
        execute=db.execute, fetchone=db.fetchone, fetchall=db.fetchall,
    )
    return TestClient(app), db


_PAYLOAD = {
    "app_id": "demo",
    "footsteps": [
        {"timestamp": "t", "type": "api_error", "route": "/accounts/:id",
         "label": "[masked]", "metadata": {"status": 500}},
    ],
    "metadata": {"sdk_version": "0.4.0"},
}


def test_healthz_open():
    client, _ = _client()
    # Outside a deployment there is no commit env; the endpoint says so instead of lying.
    assert client.get("/healthz").json() == {"status": "ok", "revision": "unknown"}


def test_healthz_reports_the_deployed_revision(monkeypatch):
    # The post-deploy verifier matches this against the pushed SHA, so a stale deploy
    # (Railway serving an old build) fails verification instead of passing on a bare 200.
    monkeypatch.setenv("RAILWAY_GIT_COMMIT_SHA", "cafe1234")
    client, _ = _client()
    assert client.get("/healthz").json()["revision"] == "cafe1234"


def test_dashboard_served_readonly():
    client, _ = _client()
    r = client.get("/dashboard")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/html")
    body = r.text
    # It is the operator UI and targets the read-only API base; no embedded data/secrets.
    assert "StepStitch" in body and "/api/stepstitch/v1" in body
    assert "operator console" in body
    # Keep the self-contained console from making a noisy /favicon.ico request.
    assert '<link rel="icon" href="data:image/svg+xml,' in body


def test_dashboard_sets_csp_with_per_request_nonce_and_security_headers():
    import re

    client, _ = _client()
    r = client.get("/dashboard")
    csp = r.headers.get("content-security-policy", "")
    assert "default-src 'none'" in csp
    m = re.search(r"script-src 'nonce-([^']+)'", csp)
    assert m, "CSP must pin the inline script to a nonce"
    # The served HTML carries that exact nonce on its single <script>, and the
    # placeholder is fully substituted.
    assert 'nonce="' + m.group(1) + '"' in r.text
    assert "__CSP_NONCE__" not in r.text
    # Baseline hardening headers are present on the response.
    assert r.headers.get("x-content-type-options") == "nosniff"
    assert r.headers.get("x-frame-options") == "DENY"
    assert r.headers.get("referrer-policy") == "no-referrer"
    # Nonce is per-request (not a fixed constant).
    r2 = client.get("/dashboard")
    assert r2.headers["content-security-policy"] != csp


def test_security_headers_on_non_dashboard_response():
    client, _ = _client()
    r = client.get("/healthz")
    assert r.headers.get("x-content-type-options") == "nosniff"
    assert r.headers.get("x-frame-options") == "DENY"


def test_dashboard_links_scheme_gated_and_no_inline_onclick():
    # Defense-in-depth for the operator UI: links are scheme-gated + attribute-escaped,
    # and no trace_id is interpolated into inline onclick markup.
    client, _ = _client()
    body = client.get("/dashboard").text
    assert "safeUrl(" in body and "escAttr(runUrl)" in body
    # Old sinks must stay gone: unescaped run_url href + trace_id in inline onclick.
    assert "esc(v.run_url)" not in body
    assert 'onclick="ssRepro' not in body


def test_dashboard_is_non_destructive_and_carries_audit_labels():
    # The operator console exposes reads, dry-run drafts, and GOVERNED config (agent
    # connections) — but never a destructive verb against evidence (delete, purge, retention,
    # or a non-dry-run deliver). It must explain its guarantees explicitly.
    client, _ = _client()
    body = client.get("/dashboard").text
    # Flow narrative + audit footer make the product legible and the guardrails explicit.
    for stage in ("Customer bug", "privacy scrub", "replayability score",
                  "Playwright repro", "draft ticket/PR", "verified fix"):
        assert stage in body, f"flow banner missing stage: {stage}"
    assert "every read and config change is audited" in body
    assert "drafts are previews, nothing is sent" in body
    assert "evidence is never edited or deleted here" in body
    # Privacy proof surfaces the scrub report as a plain-language narrative (not raw JSON),
    # backed by the same scrubbed-field data.
    assert "scrubbed_fields" in body and "Privacy proof" in body
    assert "never captures, ever" in body
    # No destructive operation is wired into the UI.
    assert "/maintenance/purge" not in body
    assert "/by-user/" not in body
    assert 'method: "DELETE"' not in body
    # Any deliver/PR action the UI exposes is dry-run only.
    assert "/deliver?dry_run=true" in body
    assert "/github/pr?dry_run=true" in body


def test_dashboard_is_organised_around_failure_shapes():
    # The console's primary object is the failure SHAPE, not the trace: it reads /shapes and
    # lays the pipeline out in the columns derived from the verdict state machine.
    client, _ = _client()
    body = client.get("/dashboard").text
    assert 'api("/shapes")' in body, "the board must read the clustered shapes endpoint"
    for stage in ("untriaged", "known_shape", "repro_invalid", "reproduced", "fix_failed",
                  "fixed"):
        assert f'"{stage}"' in body, f"board missing stage column: {stage}"
    # Four destinations, not a row of equal-weight buttons. "Board" became "Failures" when the
    # metrics Overview took the landing slot — the queue is no longer the front door.
    for dest in ("Overview", "Failures", "Agents", "Governance"):
        assert f'label: "{dest}"' in body


def test_dashboard_leads_with_metrics_not_a_queue():
    # The landing screen answers "how are things?" before "what should I work on?" — every
    # figure derived from /shapes + /admin/status, with the maths mirrored in metrics.py.
    client, _ = _client()
    body = client.get("/dashboard").text
    assert 'var current = "overview"' in body
    # Boot goes through the hash router, which falls back to the overview for an empty or
    # unknown fragment — so the console still opens on metrics, and a deep link still works.
    assert "routeFromHash();" in body, "the console must boot through the hash router"
    assert 'go(known ? known.id : "overview"' in body, "the fallback route is the overview"
    for metric in ("Open failures", "People affected", "Proven fixed", "Repeat rate"):
        assert metric in body, f"overview missing metric tile: {metric}"
    assert "function overviewMetrics" in body and "function areaChart" in body
    assert "function donut" in body


def test_dashboard_builds_dom_instead_of_concatenating_markup():
    # Every node goes through el(), which sets textContent / setAttribute. Nothing may reach
    # innerHTML — that is the structural version of the XSS guarantee the tests above grep for.
    client, _ = _client()
    body = client.get("/dashboard").text
    script = body.split("<script", 1)[1]
    assert "innerHTML" not in script, "console markup must be built via el(), never innerHTML"
    assert "function el(tag, attrs, kids)" in script


def test_dashboard_has_no_popout_and_closes_the_ci_loop():
    # Sections render in place; nothing is injected above what the operator is reading.
    client, _ = _client()
    body = client.get("/dashboard").text
    assert "insertBefore" not in body, "sections must render in place, not as injected popouts"
    assert "window.open" not in body
    # The console must hand the operator the snippet that reports a repro outcome back to
    # /verify — without it the corpus never fills and Fix Memory has nothing to match.
    assert "/verify" in body and "pre_passed" in body and "post_passed" in body


def test_ci_snippet_uses_the_verify_scoped_token_never_admin():
    # The "Report from CI" snippet is copy-pasted into pipelines, so it must carry the
    # narrow verify-scoped bearer (fetch repro + post verdict, nothing else). Handing CI
    # the admin token would contradict the console's own promise that no agent ever
    # receives that credential. Scoped to the Bearer header on purpose: the operator
    # gate legitimately names STEPSTITCH_ADMIN_TOKEN when asking the operator to log in.
    client, _ = _client()
    body = client.get("/dashboard").text
    start = body.index("report the repro outcome")
    snippet = body[start : start + 900]
    assert "/verify" in snippet
    assert "Bearer $STEPSTITCH_VERIFY_TOKEN" in snippet
    assert "Bearer $STEPSTITCH_ADMIN_TOKEN" not in body, (
        "no snippet anywhere may tell a machine to authenticate with the admin bearer"
    )
    # The verdict payload is intact — both measured outcomes plus provenance fields.
    for field in ("pre_passed", "post_passed", "fix_ref", "run_url"):
        assert field in snippet, f"CI snippet lost {field}"
    # And it says where the token comes from.
    assert "Agents tab" in snippet
    # Operator login is untouched: the gate still names the admin env var.
    assert "STEPSTITCH_ADMIN_TOKEN" in body


def test_dashboard_reads_plainly_by_default():
    # The console has to be usable by the support lead who took the customer's call, not only by
    # the engineer who will fix it. Plain wording ships alongside the technical wording, and the
    # technical-detail toggle chooses between them.
    client, _ = _client()
    body = client.get("/dashboard").text
    for plain in ("Waiting for a test run", "Seen before", "Test needs fixing",
                  "Confirmed broken", "Still broken", "Fixed and proven"):
        assert plain in body, f"missing plain column label: {plain}"
    # Plain tab names, and the plain rendering of the pipeline banner.
    for plain in ("What happened", "The test", "Proof it's fixed", "What an AI sees",
                  "Someone reports a bug", "the fix is proven"):
        assert plain in body, f"missing plain wording: {plain}"
    # The toggle exists, is persisted, and defaults OFF — an operator who needs plain language
    # is exactly the one who would not think to go looking for a switch.
    assert 'id="techtoggle"' in body
    assert 'var tech = pref("tech", false)' in body


def test_dashboard_onboards_without_a_shell_command():
    # An empty install used to be told to run `node scripts/seed-demo-trace.mjs`. A terminal
    # command is not an onboarding experience for a non-developer.
    client, _ = _client()
    body = client.get("/dashboard").text
    assert "seed-demo-trace" not in body, "onboarding must not hand the operator a shell command"
    assert "Send a sample report" in body
    for step in ("Connect to your host", "Receive your first report", "Let CI report results",
                 "Connect an AI agent"):
        assert step in body, f"setup checklist missing step: {step}"
    # Each step is DETECTED, never ticked by hand, so the checklist cannot claim something false.
    assert "(s.traces || 0) > 0" in body
    assert "(s.verifications || 0) > 0" in body


def test_dashboard_is_keyboard_navigable_and_announces_updates():
    # There were no focus styles at all — keyboard users got no indication of position.
    client, _ = _client()
    body = client.get("/dashboard").text
    assert ":focus-visible" in body, "every interactive element needs a visible focus ring"
    assert 'aria-live="polite"' in body, "async regions must announce themselves"
    # The tab roles are applied by el() at runtime rather than written as markup, so assert on
    # how they are authored. The rendered attributes are checked in the browser.
    assert 'role: "tablist"' in body and '"aria-controls": "tabpanel"' in body


def test_dashboard_can_be_searched():
    # /shapes returns up to 200; without a filter the board stops working on a real deployment.
    client, _ = _client()
    body = client.get("/dashboard").text
    assert 'id="search"' in body
    assert "function matchesQuery" in body
    assert "Showing " in body


def test_dashboard_states_the_privacy_boundary_ambiently():
    # The claim is permanent chrome, not a card you have to scroll to.
    client, _ = _client()
    body = client.get("/dashboard").text
    header_region = body.split('<main class="view"', 1)[0]
    assert "never captures, ever" in header_region
    assert 'class="privacy"' in header_region


def test_ingest_requires_bearer():
    client, _ = _client()
    assert client.post(f"{_PFX}/session", json=_PAYLOAD).status_code == 401
    ok = client.post(f"{_PFX}/session", json=_PAYLOAD,
                     headers={"Authorization": f"Bearer {INGEST}"})
    assert ok.status_code == 200
    assert ok.json()["scrub"]["scrub_status"] in {"clean", "scrubbed"}


def test_operator_read_requires_admin_not_ingest():
    client, _ = _client()
    tid = client.post(f"{_PFX}/session", json=_PAYLOAD,
                      headers={"Authorization": f"Bearer {INGEST}"}).json()["trace_id"]
    # Ingest token cannot read the operator surface.
    assert client.get(f"{_PFX}/session/{tid}/summary",
                      headers={"Authorization": f"Bearer {INGEST}"}).status_code == 401
    # Admin token can.
    r = client.get(f"{_PFX}/session/{tid}/summary",
                   headers={"Authorization": f"Bearer {ADMIN}"})
    assert r.status_code == 200
    assert r.json()["summary"]["failing_status"] == 500


def test_build_app_accepts_github_bridge():
    from server.host import build_app
    get_user_id, require_admin = build_auth(ADMIN, INGEST)

    class _DB:
        async def execute(self, q, p=()):
            return None
        async def fetchone(self, q, p=()):
            return None
        async def fetchall(self, q, p=()):
            return []

    db = _DB()
    sentinel = object()
    app = build_app(
        get_user_id=get_user_id, require_admin=require_admin,
        execute=db.execute, fetchone=db.fetchone, fetchall=db.fetchall,
        github_bridge=sentinel,
    )
    assert app is not None


# --- the console's inline script -----------------------------------------------------------
# Everything else in this file asserts against the served HTML as a STRING. That catches a
# missing feature but not a broken one: a syntax error anywhere in the ~85 KB inline script
# would leave every string assertion green and the console blank in the browser.

def _inline_script() -> str:
    import re

    from server.dashboard import DASHBOARD_HTML
    match = re.search(r'<script nonce="__CSP_NONCE__">(.*?)</script>', DASHBOARD_HTML, re.S)
    assert match, "the console must ship exactly one nonce-gated inline script"
    return match.group(1)


@pytest.mark.skipif(shutil.which("node") is None, reason="needs node to parse the console JS")
def test_dashboard_script_is_syntactically_valid():
    import pathlib
    import subprocess
    import tempfile

    path = pathlib.Path(tempfile.mkdtemp()) / "dashboard.js"
    path.write_text(_inline_script(), encoding="utf-8")
    result = subprocess.run(
        ["node", "--check", str(path)], capture_output=True, text=True)
    assert result.returncode == 0, f"console JS does not parse:\n{result.stderr}"


def test_running_or_exporting_the_repro_is_the_primary_action():
    """A reproduction that never leaves the browser proves nothing. Export used to be a
    Copy button buried inside the Repro tab; it is now the headline action on a failure."""
    client, _ = _client()
    page = client.get("/dashboard").text
    assert "primary-actions" in page
    assert "Run or export the reproduction" in page
    assert "Download .spec.ts" in page
    assert "/playwright/download" in page
    assert "/attestation/download" in page
    # And the plain-language register is served too.
    assert "Take the test to your code" in page


def test_dashboard_offers_the_safe_agent_packet():
    # The endpoint existed since 0.7 and nothing surfaced it.
    client, _ = _client()
    page = client.get("/dashboard").text
    assert "/agent-packet" in page
    assert "Copy safe agent packet" in page


def test_downloads_are_fetched_with_auth_not_linked():
    """The download routes are admin-gated, so a bare <a href> would 401. The console must
    fetch with the bearer header and save the blob."""
    client, _ = _client()
    page = client.get("/dashboard").text
    assert "function downloadBtn(" in page
    assert "URL.createObjectURL" in page
    assert "headers: hdr()" in page


def test_the_unified_workflow_stripe_is_the_dominant_status():
    """Phase 4: one state, one next action, one explanation — rendered above every
    tab from execution.py's vocabulary, never a fifth invention of the console."""
    client, _ = _client()
    page = client.get("/dashboard").text
    assert "workflow-stripe" in page
    assert "Execution progress" in page          # the aria-label
    assert "next_action" in page                 # the endpoint's own field name
    assert "workflowStripe(trace.execution)" in page
    # Both registers, and an honest fallback when the projection is unavailable.
    assert "Next: " in page
    assert "not available in this view" in page
