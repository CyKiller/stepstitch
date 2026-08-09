#!/usr/bin/env python3
"""Prove migrations survive being replayed over a SCHEMA_SQL-bootstrapped database.

The regression this pins happened on this branch and reached CI three jobs wide: a fresh
deployment bootstraps its schema from ``db.py``'s ``SCHEMA_SQL`` (complete, current), and
alembic then replays history on top. Migration 0009's bare ``ADD COLUMN`` hit
DuplicateColumn and took the host down at startup. The empty-database CI step proves the
OTHER order — alembic onto an empty database — so it stayed green while the failing order
shipped. This script proves ``SCHEMA_SQL -> alembic``; the surrounding CI workflow, which
runs both steps, is what proves both orders. This script alone does not.

    create a UNIQUE disposable database -> apply current SCHEMA_SQL
    -> assert no alembic history -> alembic upgrade head
    -> assert head revision + frozen-envelope columns
    -> alembic upgrade head AGAIN (idempotency) -> drop the database it created

Safety, because this is documented as publicly runnable: the database name is freshly
generated per invocation (``stepstitch_replay_<hex>``), validated, and quoted with
``psycopg2.sql.Identifier``; nothing pre-existing is ever dropped — there is no
``DROP DATABASE IF EXISTS <fixed name>`` in this script, and cleanup removes only the
database this invocation created, on success and on every failure path alike. Credentials
and connection URLs are never printed.

Requires: a reachable Postgres (``DATABASE_URL`` or ``STEPSTITCH_TEST_DATABASE_URL``),
psycopg2, alembic, and an installed ``stepstitch_service`` (for SCHEMA_SQL). Exits
non-zero with the failing step named.

    python3 scripts/prove_migrations_replay.py
"""
from __future__ import annotations

import os
import re
import secrets
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

EXPECTED_HEAD = "0010"
ENVELOPE_COLUMNS = ("execution_envelope_sha256", "execution_envelope_json")
# 0010's FixProof bindings — asserted post-replay like the envelope columns, so the
# proof checks the migration DID something, not merely that the version stamp moved.
FIXPROOF_COLUMNS = ("base_commit", "fixed_commit", "verified_by")
REPO = Path(__file__).resolve().parent.parent

# Lowercase letters, digits, underscores; well under Postgres's 63-byte identifier limit.
_VALID_DB_NAME = re.compile(r"^[a-z][a-z0-9_]{0,62}$")


class ProofFailure(Exception):
    """A named, non-zero-exit failure. Raised (not sys.exit) so cleanup always runs."""


def _replay_db_name() -> str:
    """A unique, validated name per invocation — never a predictable drop target."""
    name = f"stepstitch_replay_{secrets.token_hex(6)}"
    if not _VALID_DB_NAME.match(name):
        raise ProofFailure(f"generated database name failed validation: {name!r}")
    return name


def _replay_url(base_url: str, db_name: str) -> str:
    """The base connection URL with only the database (path) swapped.

    A real URL parser, deliberately: ``rsplit("/", 1)`` mangles query strings
    (``?sslmode=require``) and any URL whose password or options contain a slash.
    Credentials, host, port and query parameters all pass through untouched.
    """
    parts = urlsplit(base_url)
    return urlunsplit((parts.scheme, parts.netloc, f"/{db_name}",
                       parts.query, parts.fragment))


def _drop_replay_db(admin_conn: object, db_name: str, created: bool) -> None:
    """Remove ONLY the database this invocation created. A no-op when it never was.

    ``IF EXISTS`` guards the race where creation half-failed, not a predictable name —
    ``db_name`` is this invocation's random identifier, quoted, never a constant.
    """
    if not created:
        return
    from psycopg2 import sql

    with admin_conn.cursor() as cur:
        cur.execute(sql.SQL("DROP DATABASE IF EXISTS {}").format(sql.Identifier(db_name)))


def run_with_cleanup(admin_conn: object, db_name: str, proof) -> None:
    """Create the replay database, run the proof, and ALWAYS drop what was created.

    ``finally`` covers success, assertion failure, alembic failure, timeouts and
    ``SystemExit`` alike; the caller closes any replay-database connection inside
    ``proof``'s own cleanup so the drop is not blocked by an open session.
    """
    from psycopg2 import sql

    created = False
    try:
        with admin_conn.cursor() as cur:
            cur.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(db_name)))
        created = True
        proof()
    finally:
        _drop_replay_db(admin_conn, db_name, created)


def main() -> None:
    import psycopg2

    base_url = os.environ.get("DATABASE_URL") or os.environ.get(
        "STEPSTITCH_TEST_DATABASE_URL")
    if not base_url:
        print("  FAIL connect: set DATABASE_URL (or STEPSTITCH_TEST_DATABASE_URL) to a "
              "reachable Postgres")
        sys.exit(1)
    base_url = base_url.replace("postgresql+psycopg2://", "postgresql://")

    db_name = _replay_db_name()
    print(f"\nProving SCHEMA_SQL-first -> alembic replay (database {db_name})\n")

    admin = psycopg2.connect(base_url)
    admin.autocommit = True   # CREATE/DROP DATABASE cannot run inside a transaction

    def proof() -> None:
        from stepstitch_service.host.db import SCHEMA_SQL

        replay_url = _replay_url(base_url, db_name)
        conn = psycopg2.connect(replay_url)
        conn.autocommit = True
        try:
            with conn.cursor() as cur:
                # Bootstrap from the CURRENT declared schema — the fresh-deployment path.
                cur.execute(SCHEMA_SQL)
                print("  ok   current SCHEMA_SQL applied first")

                # The precondition that makes this the failing order: no history yet.
                cur.execute("SELECT to_regclass('alembic_version')")
                if cur.fetchone()[0] is not None:
                    raise ProofFailure("alembic_version already exists — this would "
                                       "prove the wrong order")
                print("  ok   no alembic version history (bootstrap did not stamp)")

            def upgrade(round_name: str) -> None:
                proc = subprocess.run(
                    ["alembic", "upgrade", "head"], cwd=str(REPO / "server"),
                    env={**os.environ, "DATABASE_URL": replay_url},
                    capture_output=True, text=True, timeout=300)
                if proc.returncode != 0:
                    raise ProofFailure(
                        f"{round_name}: "
                        f"{(proc.stderr or proc.stdout or '').strip()[-800:]}")
                print(f"  ok   {round_name}")

            # Replay full history over the bootstrapped schema — where 0009 used to die.
            upgrade("alembic upgrade head over the bootstrapped schema")

            with conn.cursor() as cur:
                cur.execute("SELECT version_num FROM alembic_version")
                head = cur.fetchone()[0]
                if head != EXPECTED_HEAD:
                    raise ProofFailure(f"head revision: expected {EXPECTED_HEAD}, "
                                       f"found {head}")
                print(f"  ok   head revision {head}")

                cur.execute(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_name = 'stepstitch_frozen_repros'")
                columns = {row[0] for row in cur.fetchall()}
                missing = [c for c in ENVELOPE_COLUMNS if c not in columns]
                if missing:
                    raise ProofFailure(f"frozen-envelope columns missing: {missing}")
                print("  ok   both frozen-envelope columns present")

                cur.execute(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_name = 'stepstitch_verifications'")
                columns = {row[0] for row in cur.fetchall()}
                missing = [c for c in FIXPROOF_COLUMNS if c not in columns]
                if missing:
                    raise ProofFailure(f"fixproof binding columns missing: {missing}")
                print("  ok   all three fixproof binding columns present")

            # Replaying a second time must change nothing and break nothing.
            upgrade("alembic upgrade head a second time (idempotency)")

            with conn.cursor() as cur:
                cur.execute("SELECT version_num FROM alembic_version")
                if cur.fetchone()[0] != EXPECTED_HEAD:
                    raise ProofFailure("head revision moved on the second replay")
            print("  ok   second replay is a no-op")
        finally:
            # Closed BEFORE the drop in run_with_cleanup, or the drop would block on
            # this open session.
            conn.close()

    try:
        run_with_cleanup(admin, db_name, proof)
        print("  ok   disposable database dropped\n")
        print("SCHEMA_SQL -> alembic replay proven. (The CI workflow's separate "
              "empty-database step proves the other order; together they cover both.)")
    except ProofFailure as exc:
        print(f"  FAIL {exc}")
        sys.exit(1)
    finally:
        admin.close()


if __name__ == "__main__":
    main()
