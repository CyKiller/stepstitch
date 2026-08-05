"""structural fingerprint on traces (Failure Shapes)

Revision ID: 0005
Revises: 0004
Create Date: 2026-07-24

Adds the privacy-safe structural ``fingerprint`` column to ``stepstitch_traces`` so the console
can cluster traces into **failure shapes** with a query instead of parsing every footsteps blob
on every board load. Mirrors 0004, which added the same column to ``stepstitch_verifications``.

The fingerprint is derived entirely from fields the ingest scrubber has already cleared —
templated routes and structural selectors — so this stores only structural fields and
moves no privacy boundary.
Because it lives outside the trace body, a shape and its fix stay matchable after retention
purges the body.

Backfill is deliberately omitted: the fingerprint needs the footsteps blob parsed and summarised
through the service layer, which Alembic has no business importing. Existing rows keep a NULL
fingerprint and are skipped by the board until re-ingested; ``scripts/backfill_fingerprints.py``
fills them in for a deployment that wants its history clustered.
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "0005"
down_revision: Union[str, None] = "0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE stepstitch_traces ADD COLUMN IF NOT EXISTS fingerprint TEXT")
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_stepstitch_traces_fingerprint "
        "ON stepstitch_traces (fingerprint)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_stepstitch_traces_fingerprint")
    op.execute("ALTER TABLE stepstitch_traces DROP COLUMN IF EXISTS fingerprint")
