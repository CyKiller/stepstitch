#!/usr/bin/env python3
"""Prove migrations survive being replayed over a SCHEMA_SQL-bootstrapped database.

The regression this pins happened on this branch and reached CI three jobs wide: a fresh
deployment bootstraps its schema from ``db.py``'s ``SCHEMA_SQL`` (complete, current), and
alembic then replays history on top. Migration 0009's bare ``ADD COLUMN`` hit
DuplicateColumn and took the host down at startup. The existing CI gate proves the OTHER
order — alembic onto an empty database — so it stayed green while the failing order
shipped. This gate proves the failing order, permanently:

    CREATE DATABASE (disposable) -> apply current SCHEMA_SQL -> assert no alembic history
    -> alembic upgrade head -> assert head revision + frozen-envelope columns
    -> alembic upgrade head AGAIN (idempotency) -> re-assert

Requires: a reachable Postgres (``DATABASE_URL`` or ``STEPSTITCH_TEST_DATABASE_URL``),
psycopg2, alembic, and an installed ``stepstitch_service`` (for SCHEMA_SQL). Exits
non-zero with the failing step named. The existing empty-database gate is untouched —
both orders stay proven.

    python3 scripts/prove_migrations_replay.py
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

REPLAY_DB = "stepstitch_bootstrap_replay"
EXPECTED_HEAD = "0009"
ENVELOPE_COLUMNS = ("execution_envelope_sha256", "execution_envelope_json")
REPO = Path(__file__).resolve().parent.parent


def fail(step: str, detail: str) -> None:
    print(f"  FAIL {step}: {detail}")
    sys.exit(1)


def main() -> None:
    import psycopg2  # comes in via server/requirements.txt, exactly like the host job

    base_url = os.environ.get("DATABASE_URL") or os.environ.get(
        "STEPSTITCH_TEST_DATABASE_URL")
    if not base_url:
        fail("connect", "set DATABASE_URL (or STEPSTITCH_TEST_DATABASE_URL) to a "
                        "reachable Postgres")
    base_url = base_url.replace("postgresql+psycopg2://", "postgresql://")

    print(f"\nProving SCHEMA_SQL-first -> alembic replay (database {REPLAY_DB})\n")

    # 1. A separate disposable database, so nothing here can touch the job's real one.
    admin = psycopg2.connect(base_url)
    admin.autocommit = True   # CREATE DATABASE cannot run inside a transaction
    with admin.cursor() as cur:
        cur.execute(f"DROP DATABASE IF EXISTS {REPLAY_DB}")
        cur.execute(f"CREATE DATABASE {REPLAY_DB}")
    admin.close()
    print("  ok   disposable database created")

    replay_url = base_url.rsplit("/", 1)[0] + f"/{REPLAY_DB}"

    # 2. Bootstrap from the CURRENT declared schema — the fresh-deployment path.
    from stepstitch_service.host.db import SCHEMA_SQL
    conn = psycopg2.connect(replay_url)
    conn.autocommit = True
    with conn.cursor() as cur:
        cur.execute(SCHEMA_SQL)
        print("  ok   current SCHEMA_SQL applied first")

        # 3. The precondition that makes this the failing order: no alembic history yet.
        cur.execute("SELECT to_regclass('alembic_version')")
        if cur.fetchone()[0] is not None:
            fail("precondition", "alembic_version already exists — this would prove the "
                                 "wrong order")
        print("  ok   no alembic version history (bootstrap did not stamp)")

    def upgrade(round_name: str) -> None:
        proc = subprocess.run(
            ["alembic", "upgrade", "head"], cwd=str(REPO / "server"),
            env={**os.environ, "DATABASE_URL": replay_url},
            capture_output=True, text=True, timeout=300)
        if proc.returncode != 0:
            fail(round_name, (proc.stderr or proc.stdout or "").strip()[-800:])
        print(f"  ok   {round_name}")

    # 4. Replay full history over the bootstrapped schema — where 0009 used to die.
    upgrade("alembic upgrade head over the bootstrapped schema")

    with conn.cursor() as cur:
        # 5. The head revision is recorded.
        cur.execute("SELECT version_num FROM alembic_version")
        head = cur.fetchone()[0]
        if head != EXPECTED_HEAD:
            fail("head revision", f"expected {EXPECTED_HEAD}, found {head}")
        print(f"  ok   head revision {head}")

        # 6. The columns 0009 exists to add are present.
        cur.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = 'stepstitch_frozen_repros'")
        columns = {row[0] for row in cur.fetchall()}
        missing = [c for c in ENVELOPE_COLUMNS if c not in columns]
        if missing:
            fail("frozen-envelope columns", f"missing: {missing}")
        print("  ok   both frozen-envelope columns present")

    # 7. Replaying a second time must change nothing and break nothing.
    upgrade("alembic upgrade head a second time (idempotency)")

    with conn.cursor() as cur:
        cur.execute("SELECT version_num FROM alembic_version")
        if cur.fetchone()[0] != EXPECTED_HEAD:
            fail("idempotency", "head revision moved on the second replay")
    conn.close()
    print("  ok   second replay is a no-op\n")
    print("Migrations replay cleanly over a bootstrapped schema, both directions proven.")


if __name__ == "__main__":
    main()
