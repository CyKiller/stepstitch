"""initial StepStitch host schema (traces, audit, verifications)

Revision ID: 0001
Revises: None
Create Date: 2026-06-21

Single source of truth: ``upgrade()`` applies ``server.db.SCHEMA_SQL`` verbatim so the
migrated schema is byte-identical to what ``ensure_schema`` produces at runtime. Because
SCHEMA_SQL uses ``CREATE TABLE IF NOT EXISTS``, this also stamps cleanly onto a DB that
already has the tables.
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    from server.db import SCHEMA_SQL

    op.execute(SCHEMA_SQL)


def downgrade() -> None:
    op.execute(
        "DROP TABLE IF EXISTS "
        "stepstitch_verifications, stepstitch_audit, stepstitch_traces CASCADE"
    )
