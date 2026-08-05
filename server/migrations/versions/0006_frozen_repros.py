"""frozen reproductions (the referee property)

Revision ID: 0006
Revises: 0005
Create Date: 2026-07-30

Stores the exact reproduction bytes that judge a fix, plus the measured red run that proved
the failure was present before an agent touched anything.

Verification reruns the script recorded here; a script whose sha256 differs is refused rather
than run. That is what makes StepStitch a referee instead of a scorekeeper: an agent may
change the application, but it can never weaken, replace or regenerate the test that judges
its own fix.

Contents are structural only — a compiled Playwright spec derived from footsteps the ingest
scrubber has already cleared — so this stores only structural fields and moves no
privacy boundary. It sits
outside the trace body deliberately: a frozen reproduction and its verdict must stay valid
after retention purges the body it came from.
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "0006"
down_revision: Union[str, None] = "0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS stepstitch_frozen_repros (
            trace_id      TEXT PRIMARY KEY,
            script        TEXT NOT NULL,
            sha256        TEXT NOT NULL,
            red_verdict   TEXT,
            red_signature TEXT,
            frozen_at     TIMESTAMPTZ NOT NULL,
            frozen_by     TEXT
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_stepstitch_frozen_sha "
        "ON stepstitch_frozen_repros (sha256)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_stepstitch_frozen_sha")
    op.execute("DROP TABLE IF EXISTS stepstitch_frozen_repros")
