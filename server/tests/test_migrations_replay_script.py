"""Safety of the publicly runnable migration-replay proof script.

The script's first version used one fixed database name and opened with
``DROP DATABASE IF EXISTS stepstitch_bootstrap_replay`` — a predictable, destructive
target on whatever server DATABASE_URL points at, and the "disposable" database was never
cleaned up. These tests pin the safe shape: unique validated names, Identifier quoting,
cleanup that runs on success and failure and touches only what this invocation created.
The real-Postgres CI step remains the behavioral integration proof.
"""
import importlib.util
from pathlib import Path

import pytest

_SPEC = importlib.util.spec_from_file_location(
    "prove_migrations_replay",
    Path(__file__).resolve().parents[2] / "scripts" / "prove_migrations_replay.py")
assert _SPEC is not None and _SPEC.loader is not None, "the script moved"
script = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(script)


class FakeCursor:
    def __init__(self, log):
        self.log = log

    def execute(self, statement, params=None):
        self.log.append(statement)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class FakeConn:
    def __init__(self):
        self.statements = []

    def cursor(self):
        return FakeCursor(self.statements)


def test_generated_names_are_unique_and_valid():
    names = {script._replay_db_name() for _ in range(50)}
    assert len(names) == 50, "one name per invocation, never a shared drop target"
    for name in names:
        assert script._VALID_DB_NAME.match(name)
        assert len(name) <= 63, "inside Postgres's identifier limit"
        assert name != "stepstitch_bootstrap_replay"


def test_replay_url_preserves_everything_but_the_database():
    url = script._replay_url(
        "postgresql://user:p%40ss@db.example.invalid:6432/postgres?sslmode=require",
        "stepstitch_replay_abc123")
    assert url == ("postgresql://user:p%40ss@db.example.invalid:6432/"
                   "stepstitch_replay_abc123?sslmode=require"), \
        "credentials, host, port and query parameters all pass through untouched"


def test_cleanup_targets_only_the_generated_database():
    conn = FakeConn()
    script._drop_replay_db(conn, "stepstitch_replay_deadbeef", created=True)
    assert len(conn.statements) == 1
    dropped = repr(conn.statements[0])
    assert "stepstitch_replay_deadbeef" in dropped
    assert "Identifier" in dropped, "quoted, never interpolated"
    assert "bootstrap_replay" not in dropped


def test_cleanup_is_a_noop_when_this_invocation_created_nothing():
    conn = FakeConn()
    script._drop_replay_db(conn, "stepstitch_replay_deadbeef", created=False)
    assert conn.statements == [], "never drop what someone else may own"


def test_cleanup_runs_after_success_and_after_every_failure_shape():
    for outcome in (None, script.ProofFailure("assertion"), RuntimeError("alembic"),
                    SystemExit(1)):
        conn = FakeConn()

        def proof():
            if outcome is not None:
                raise outcome

        if outcome is None:
            script.run_with_cleanup(conn, "stepstitch_replay_cafe01", proof)
        else:
            with pytest.raises(type(outcome)):
                script.run_with_cleanup(conn, "stepstitch_replay_cafe01", proof)
        created = repr(conn.statements[0])
        dropped = repr(conn.statements[-1])
        assert "CREATE DATABASE" in created and "cafe01" in created
        assert "DROP DATABASE" in dropped and "cafe01" in dropped, \
            f"cleanup must run even on {type(outcome).__name__}"


def test_no_predictable_destructive_target_remains():
    source = (Path(__file__).resolve().parents[2] / "scripts" /
              "prove_migrations_replay.py").read_text(encoding="utf-8")
    assert "DROP DATABASE IF EXISTS stepstitch_bootstrap_replay" not in source
    assert 'REPLAY_DB = "stepstitch_bootstrap_replay"' not in source
