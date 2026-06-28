"""fix-memory fingerprint on verifications

Revision ID: 0004
Revises: 0003
Create Date: 2026-06-28

Adds the privacy-safe structural ``fingerprint`` column to ``stepstitch_verifications`` so a
confirmed fix stays matchable even after the trace body is purged (Fix Memory, 0.6.0). Mirrors
the column in ``server.db.SCHEMA_SQL`` and is idempotent (``ADD COLUMN IF NOT EXISTS``).
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "0004"
down_revision: Union[str, None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE stepstitch_verifications ADD COLUMN IF NOT EXISTS fingerprint TEXT"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE stepstitch_verifications DROP COLUMN IF EXISTS fingerprint")
