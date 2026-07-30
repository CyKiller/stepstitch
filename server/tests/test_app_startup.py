"""Startup validation: a misconfigured host must say what is wrong, not raise KeyError.

``server/app.py`` is the deployment entrypoint. Importing it used to fail with a bare
``KeyError: 'DATABASE_URL'`` and a container that exited instantly — which tells an operator
nothing about the other variables they also forgot. The validator lives in its own module
precisely so it can be tested without a full environment.
"""
import pytest

from server.envcheck import require_env

GOOD = {
    "DATABASE_URL": "postgres://u:p@db:5432/stepstitch",
    "STEPSTITCH_INGEST_TOKEN": "ingest-token",
    "STEPSTITCH_ADMIN_TOKEN": "admin-token",
}


def test_a_complete_environment_passes():
    require_env(dict(GOOD))          # does not raise


def test_every_problem_is_reported_at_once():
    # Not one per redeploy.
    with pytest.raises(SystemExit) as exc:
        require_env({})
    message = str(exc.value)
    assert "DATABASE_URL" in message
    assert "STEPSTITCH_INGEST_TOKEN" in message
    assert "STEPSTITCH_ADMIN_TOKEN" in message


def test_the_message_names_the_fix_and_the_tool():
    with pytest.raises(SystemExit) as exc:
        require_env({})
    message = str(exc.value)
    assert "cannot start" in message
    assert "openssl rand" in message          # how to make a token
    assert "stepstitch doctor" in message     # what checks the rest
    assert "docs/DEPLOY.md" in message


def test_production_mode_rejects_a_non_postgres_dsn_with_the_reason():
    # Production (the default mode) still requires Postgres; sqlite is the LOCAL mode's
    # store, never a silent production fallback.
    with pytest.raises(SystemExit) as exc:
        require_env(dict(GOOD, DATABASE_URL="sqlite:///local.db"))
    assert "must start with" in str(exc.value)


def test_local_mode_accepts_a_sqlite_dsn_and_needs_no_tokens():
    require_env({"STEPSTITCH_MODE": "local",
                 "DATABASE_URL": "sqlite:///.stepstitch/local.db"})   # does not raise
    require_env({"STEPSTITCH_MODE": "local"})   # unset DSN -> default local file


def test_local_mode_refuses_a_postgres_dsn_rather_than_half_honoring_it():
    with pytest.raises(SystemExit) as exc:
        require_env({"STEPSTITCH_MODE": "local",
                     "DATABASE_URL": "postgres://u:hunter2@db:5432/x"})
    message = str(exc.value)
    assert "STEPSTITCH_MODE=local" in message
    assert "hunter2" not in message   # never echo credentials


def test_oidc_removes_the_admin_token_requirement():
    env = dict(GOOD)
    del env["STEPSTITCH_ADMIN_TOKEN"]
    env["STEPSTITCH_OIDC_ISSUER"] = "https://login.example.test/"
    require_env(env)                 # SSO deployments have no shared admin token


def test_an_empty_string_counts_as_unset():
    with pytest.raises(SystemExit):
        require_env(dict(GOOD, STEPSTITCH_INGEST_TOKEN=""))


def test_the_error_does_not_echo_secret_values():
    with pytest.raises(SystemExit) as exc:
        require_env({"DATABASE_URL": "mysql://user:hunter2@db/x"})
    assert "hunter2" not in str(exc.value)
