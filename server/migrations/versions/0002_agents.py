"""agent connections (named, scoped bearer tokens)

Revision ID: 0002
Revises: 0001
Create Date: 2026-06-28

Adds ``stepstitch_agents`` so AI/MCP consumers can be registered and scoped per agent
(see server/agents.py). The DDL mirrors the ``stepstitch_agents`` block in
``server.db.SCHEMA_SQL`` and uses ``IF NOT EXISTS`` so it stamps cleanly onto a DB that
already created the table via ``ensure_schema``.
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_AGENTS_SQL = """
CREATE TABLE IF NOT EXISTS stepstitch_agents (
    id          TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    token_hash  TEXT NOT NULL UNIQUE,
    scope       TEXT NOT NULL,
    revoked     BOOLEAN NOT NULL DEFAULT FALSE,
    created_at  TIMESTAMPTZ NOT NULL,
    created_by  TEXT
);
CREATE INDEX IF NOT EXISTS ix_stepstitch_agents_token ON stepstitch_agents (token_hash);
"""


def upgrade() -> None:
    op.execute(_AGENTS_SQL)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS stepstitch_agents CASCADE")
