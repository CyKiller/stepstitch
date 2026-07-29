"""``stepstitch doctor`` — the first-run diagnostic.

The security-critical test here is ``test_no_secret_value_ever_appears_in_output``: doctor's
output is meant to be pasted into an issue or a support thread, so it must describe secrets
without disclosing them.

All checks run against a fake transport — no network, no host required.
"""
import json

from stepstitch_service.cli import (
    DEFAULT_HOST,
    FAIL,
    PASS,
    WARN,
    Check,
    main,
    mask,
    run_doctor,
)

ADMIN = "admin-token-supersecret-value"
INGEST = "ingest-token-supersecret-value"
DSN = "postgres://stepstitch:hunter2@db.internal:5432/stepstitch"

GOOD_ENV = {
    "DATABASE_URL": DSN,
    "STEPSTITCH_INGEST_TOKEN": INGEST,
    "STEPSTITCH_ADMIN_TOKEN": ADMIN,
    "STEPSTITCH_APP_BASE_URL": "https://staging.example.test",
}

ADMIN_STATUS = {
    "status": "ok", "profile": "financial-services-enterprise", "retention_days": 30,
    "traces": 3, "audit_events": 9, "agents_total": 1, "agents_active": 1,
    "verifications": 2, "base_url_configured": True, "repro_config_ready": True,
}


def fake_transport(overrides=None, calls=None):
    """A host that answers every doctor probe correctly unless told otherwise."""
    overrides = overrides or {}

    def send(url, method, headers, body):
        if calls is not None:
            calls.append((method, url, headers, body))
        for suffix, response in overrides.items():
            if url.endswith(suffix):
                return response
        if url.endswith("/healthz"):
            return 200, {"status": "ok"}
        if url.endswith("/dashboard"):
            return 200, "<html><title>StepStitch</title></html>"
        if url.endswith("/api/stepstitch/v1/session"):
            return 422, {"detail": "validation error"}
        if url.endswith("/admin/status"):
            return 200, dict(ADMIN_STATUS)
        if url.endswith("/admin/config/scrub"):
            return 200, {"status": "ok"}
        if url.endswith("/admin/config/repro"):
            return 200, {"status": "ok", "config": {}, "readiness": [
                {"id": "base_url", "ready": True, "title": "Application base URL",
                 "detail": "points at https://staging.example.test"},
                {"id": "auth", "ready": True, "title": "Authentication fixture",
                 "detail": "uses tests/auth.setup.ts"},
            ]}
        return 404, {}

    return send


def statuses(checks):
    return {c.name: c.status for c in checks}


# --- masking (the security property) ---------------------------------------------------------

def test_mask_describes_without_disclosing():
    out = mask("admin-token-supersecret-value")
    assert "supersecret" not in out
    assert "29 chars" in out and "sha256:" in out
    assert mask(None) == "not set"
    assert mask("") == "not set"


def test_mask_distinguishes_two_different_tokens():
    # The point of the digest: telling "the token I set" from "a different token".
    assert mask("token-a") != mask("token-b")
    assert mask("token-a") == mask("token-a")


def test_no_secret_value_ever_appears_in_output():
    checks = run_doctor(host=DEFAULT_HOST, env=GOOD_ENV, transport=fake_transport())
    rendered = json.dumps([c.as_dict() for c in checks])
    for secret in (ADMIN, INGEST, DSN, "hunter2", "supersecret"):
        assert secret not in rendered, f"doctor leaked {secret!r}"


def test_no_secret_leaks_even_when_everything_fails():
    transport = fake_transport({"/healthz": (0, "connection refused")})
    checks = run_doctor(host=DEFAULT_HOST, env=GOOD_ENV, transport=transport)
    rendered = json.dumps([c.as_dict() for c in checks])
    for secret in (ADMIN, INGEST, DSN, "hunter2"):
        assert secret not in rendered


# --- environment checks -------------------------------------------------------------------

def test_healthy_install_passes_everything():
    checks = run_doctor(host=DEFAULT_HOST, env=GOOD_ENV, transport=fake_transport())
    assert not [c for c in checks if c.status == FAIL]
    assert statuses(checks)["host reachable"] == PASS
    assert statuses(checks)["database reachable"] == PASS


def test_missing_env_is_reported_with_a_fix():
    checks = run_doctor(host=DEFAULT_HOST, env={}, transport=fake_transport())
    by_name = {c.name: c for c in checks}
    assert by_name["DATABASE_URL"].status == FAIL
    assert "Postgres DSN" in by_name["DATABASE_URL"].fix
    assert by_name["STEPSTITCH_INGEST_TOKEN"].status == FAIL


def test_oidc_replaces_the_admin_token_requirement():
    env = dict(GOOD_ENV)
    del env["STEPSTITCH_ADMIN_TOKEN"]
    env["STEPSTITCH_OIDC_ISSUER"] = "https://login.example.test/"
    names = {c.name for c in run_doctor(host=DEFAULT_HOST, env=env,
                                        transport=fake_transport())}
    assert "operator auth" in names
    assert "STEPSTITCH_ADMIN_TOKEN" not in names


def test_missing_app_base_url_warns_rather_than_fails():
    env = dict(GOOD_ENV)
    del env["STEPSTITCH_APP_BASE_URL"]
    by_name = {c.name: c for c in run_doctor(host=DEFAULT_HOST, env=env,
                                             transport=fake_transport())}
    check = by_name["STEPSTITCH_APP_BASE_URL"]
    assert check.status == WARN          # StepStitch still works…
    assert "cannot run in CI" in check.fix  # …but the repro is not usable


# --- host checks ----------------------------------------------------------------------------

def test_unreachable_host_fails_and_stops_rather_than_cascading():
    transport = fake_transport({"/healthz": (0, "Connection refused")})
    checks = run_doctor(host=DEFAULT_HOST, env=GOOD_ENV, transport=transport)
    by_name = {c.name: c for c in checks}
    assert by_name["host reachable"].status == FAIL
    assert "docker compose up" in by_name["host reachable"].fix
    # One clear failure beats eight consequential ones.
    assert "remaining checks" in by_name
    assert "admin authentication" not in by_name


def test_rejected_ingest_token_is_named_precisely():
    transport = fake_transport({"/api/stepstitch/v1/session": (401, {"detail": "no"})})
    by_name = {c.name: c for c in run_doctor(host=DEFAULT_HOST, env=GOOD_ENV,
                                             transport=transport)}
    check = by_name["ingest authentication"]
    assert check.status == FAIL
    assert "STEPSTITCH_INGEST_TOKEN" in check.fix


def test_ingest_probe_does_not_write_anything():
    """Doctor must be safe to run against production: the probe is an intentionally invalid
    payload, so a 422 proves the token works without storing a trace."""
    calls = []
    run_doctor(host=DEFAULT_HOST, env=GOOD_ENV, transport=fake_transport(calls=calls))
    posts = [c for c in calls if c[0] == "POST"]
    assert len(posts) == 1
    method, url, _headers, body = posts[0]
    assert url.endswith("/api/stepstitch/v1/session")
    assert body == b"{}", "the probe must be a payload the router rejects before storing"


def test_rejected_admin_token_is_named_precisely():
    transport = fake_transport({"/admin/status": (403, {"detail": "no"})})
    by_name = {c.name: c for c in run_doctor(host=DEFAULT_HOST, env=GOOD_ENV,
                                             transport=transport)}
    assert by_name["admin authentication"].status == FAIL
    assert "STEPSTITCH_ADMIN_TOKEN" in by_name["admin authentication"].fix


def test_no_ci_verdict_yet_is_a_warning_that_explains_the_consequence():
    status = dict(ADMIN_STATUS, verifications=0)
    by_name = {c.name: c for c in run_doctor(
        host=DEFAULT_HOST, env=GOOD_ENV,
        transport=fake_transport({"/admin/status": (200, status)}))}
    check = by_name["CI verification endpoint"]
    assert check.status == WARN
    assert "Fix Memory stays empty" in check.fix


def test_unconfigured_repro_settings_surface_as_a_warning():
    repro = (200, {"status": "ok", "config": {}, "readiness": [
        {"id": "base_url", "ready": False, "title": "Application base URL",
         "detail": "not set"},
    ]})
    by_name = {c.name: c for c in run_doctor(
        host=DEFAULT_HOST, env=GOOD_ENV,
        transport=fake_transport({"/admin/config/repro": repro}))}
    assert by_name["reproduction config"].status == WARN
    assert "Application base URL" in by_name["reproduction config"].detail


# --- CLI surface ------------------------------------------------------------------------------

def test_exit_code_is_zero_when_healthy(monkeypatch, capsys):
    monkeypatch.setattr("stepstitch_service.cli.run_doctor",
                        lambda **kw: [Check("all good", PASS, "fine")])
    assert main(["doctor"]) == 0
    assert "Everything checks out." in capsys.readouterr().out


def test_exit_code_is_one_when_anything_failed(monkeypatch, capsys):
    monkeypatch.setattr("stepstitch_service.cli.run_doctor",
                        lambda **kw: [Check("broken", FAIL, "nope", "do the thing")])
    assert main(["doctor"]) == 1
    out = capsys.readouterr().out
    assert "FAIL" in out and "do the thing" in out


def test_warnings_alone_do_not_fail_the_exit_code(monkeypatch, capsys):
    monkeypatch.setattr("stepstitch_service.cli.run_doctor",
                        lambda **kw: [Check("partial", WARN, "not wired yet")])
    assert main(["doctor"]) == 0
    assert "warning" in capsys.readouterr().out


def test_no_subcommand_prints_help_and_exits_two(capsys):
    assert main([]) == 2
    assert "doctor" in capsys.readouterr().out


def test_json_output_is_machine_readable(monkeypatch, capsys):
    monkeypatch.setattr("stepstitch_service.cli.run_doctor",
                        lambda **kw: [Check("a", PASS, "d", "f")])
    assert main(["doctor", "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["checks"] == [{"name": "a", "status": "pass", "detail": "d", "fix": "f"}]


def test_doctor_imports_without_fastapi_installed():
    """Doctor has to work in a minimal environment — that is the environment it diagnoses."""
    import stepstitch_service.cli as cli_module

    source = open(cli_module.__file__).read()
    assert "import fastapi" not in source
    assert "from fastapi" not in source
    assert "httpx" not in source
