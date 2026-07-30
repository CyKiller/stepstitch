"""evidence grade on verifications (asserted / measured / signed)

Revision ID: 0007
Revises: 0006
Create Date: 2026-07-30

Records **how** a verification outcome was obtained, not just what it was.

Until now every verification looked alike in the console and in the attestation, whether
StepStitch had run the reproduction itself or a CI job had simply posted
``pre_passed``/``post_passed`` and been believed. Those are very different claims, and
presenting them in the same words overstated the weaker one.

Existing rows backfill to ``asserted`` — which is accurate, not pessimistic: they were all
reported by a caller, because measuring locally did not exist when they were written. The
column is deliberately NOT NULL with that default so no row can sit in an unknown state
and get read as if it were measured.
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "0007"
down_revision: Union[str, None] = "0006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE stepstitch_verifications "
        "ADD COLUMN IF NOT EXISTS evidence_grade TEXT NOT NULL DEFAULT 'asserted'"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_stepstitch_verif_grade "
        "ON stepstitch_verifications (evidence_grade)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_stepstitch_verif_grade")
    op.execute("ALTER TABLE stepstitch_verifications DROP COLUMN IF EXISTS evidence_grade")
