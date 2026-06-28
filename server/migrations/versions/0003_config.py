"""operator config store (scrub overrides)

Revision ID: 0003
Revises: 0002
Create Date: 2026-06-28

Adds ``stepstitch_config`` — the small per-key JSON store the dashboard scrub editor writes
to. Mirrors the ``stepstitch_config`` block in ``server.db.SCHEMA_SQL`` and uses
``IF NOT EXISTS`` so it stamps cleanly onto a DB already created via ``ensure_schema``.
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_CONFIG_SQL = """
CREATE TABLE IF NOT EXISTS stepstitch_config (
    key         TEXT PRIMARY KEY,
    value       TEXT NOT NULL,
    updated_at  TIMESTAMPTZ NOT NULL,
    updated_by  TEXT
);
"""


def upgrade() -> None:
    op.execute(_CONFIG_SQL)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS stepstitch_config CASCADE")
