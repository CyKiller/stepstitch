"""Alembic environment for the StepStitch ingest host.

Migrations run over a **sync** SQLAlchemy/psycopg2 engine at deploy/startup only —
entirely separate from the asyncpg pool the runtime trace path uses. The DB URL is
resolved here from the environment (NOT from alembic.ini): we prefer ``DATABASE_URL``
and fall back to ``STEPSTITCH_TEST_DATABASE_URL``, then normalise the scheme to
``postgresql+psycopg2://`` so SQLAlchemy uses the sync psycopg2 driver.
"""
from __future__ import annotations

import os
import pathlib
import sys

from alembic import context
from sqlalchemy import engine_from_config, pool

# Repo root on sys.path so ``import server.db`` works (mirrors server/tests/conftest.py).
_ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

config = context.config

# Hand-written migrations — no autogenerate, so no metadata to diff against.
target_metadata = None


def _resolve_url() -> str:
    """Read the DB URL from the environment and normalise it for psycopg2."""
    url = os.environ.get("DATABASE_URL") or os.environ.get(
        "STEPSTITCH_TEST_DATABASE_URL"
    )
    if not url:
        raise RuntimeError(
            "DATABASE_URL (or STEPSTITCH_TEST_DATABASE_URL) must be set to run migrations"
        )
    # Strip any async driver suffix (e.g. postgresql+asyncpg://) and force psycopg2.
    if "+" in url.split("://", 1)[0]:
        scheme, rest = url.split("://", 1)
        url = scheme.split("+", 1)[0] + "://" + rest
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://"):]
    if url.startswith("postgresql://"):
        url = "postgresql+psycopg2://" + url[len("postgresql://"):]
    return url


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode (emit SQL without a live connection)."""
    context.configure(
        url=_resolve_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode against a live sync engine."""
    section = config.get_section(config.config_ini_section) or {}
    section["sqlalchemy.url"] = _resolve_url()
    connectable = engine_from_config(
        section,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
