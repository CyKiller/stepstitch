"""FixProof bindings on verifications (base commit, fixed commit, verifier)

Revision ID: 0010
Revises: 0009
Create Date: 2026-08-08

A verification row said WHAT happened (pre red, post green) and HOW it was obtained
(evidence_grade), but not WHICH CODE it happened to or WHO reported it. That left a
FixProof — the in-toto statement binding a fix to its evidence — with nothing to put in
its subject: ``fix_ref`` is caller-supplied free text (NULL on the measured path), and no
actor was ever recorded on the row itself, only in the time-correlated audit table.

Three nullable columns, nullable on purpose: a commit SHA that was never captured cannot
be invented after the fact, so old rows stay NULL and the fixproof endpoint REFUSES to
build a proof from them rather than fabricating a subject. New writes carry the bindings
when the caller provides them (validated as 40-hex upstream) and always carry the actor.
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "0010"
down_revision: Union[str, None] = "0009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE stepstitch_verifications ADD COLUMN IF NOT EXISTS base_commit TEXT"
    )
    op.execute(
        "ALTER TABLE stepstitch_verifications ADD COLUMN IF NOT EXISTS fixed_commit TEXT"
    )
    op.execute(
        "ALTER TABLE stepstitch_verifications ADD COLUMN IF NOT EXISTS verified_by TEXT"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE stepstitch_verifications DROP COLUMN IF EXISTS verified_by")
    op.execute("ALTER TABLE stepstitch_verifications DROP COLUMN IF EXISTS fixed_commit")
    op.execute("ALTER TABLE stepstitch_verifications DROP COLUMN IF EXISTS base_commit")
