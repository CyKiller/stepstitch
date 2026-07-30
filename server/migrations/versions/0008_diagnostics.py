"""deep diagnostics from the synthetic reproduction

Revision ID: 0008
Revises: 0007
Create Date: 2026-07-30

Stores what a local reproduction revealed about a failure — the stack, the console errors,
the failed requests, the snapshot at the moment it broke.

This is the one place StepStitch keeps rich technical detail, and it is safe precisely
because of where it comes from: a synthetic run on a developer's machine, driven by a
generated test, with no customer in it. The user's own failure trail stays as small and
scrubbed as it has always been. Depth from the reproduction, not from surveillance — hence
the explicit ``source`` column, which is always ``synthetic_reproduction``.

The runner deletes its scratch directory after each run, so a file beside the run would not
survive to populate an agent packet; the scrubbed record lives here instead. Raw Playwright
traces stay on local disk, are short-lived, and are never exposed over MCP.

Both digests are stored because a verdict is only comparable when the script *and* the way
it ran are the same experiment: ``script_sha256`` pins the bytes,
``execution_envelope_sha256`` pins the browser, timeouts, base URL and diagnostics profile.
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "0008"
down_revision: Union[str, None] = "0007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS stepstitch_diagnostics (
            id                        TEXT PRIMARY KEY,
            trace_id                  TEXT NOT NULL,
            run_id                    TEXT NOT NULL,
            source                    TEXT NOT NULL,
            schema_version            INTEGER NOT NULL,
            script_sha256             TEXT NOT NULL,
            execution_envelope_sha256 TEXT NOT NULL,
            diagnostics_json          TEXT NOT NULL,
            created_at                TIMESTAMPTZ NOT NULL
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_stepstitch_diag_trace "
        "ON stepstitch_diagnostics (trace_id, created_at DESC)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_stepstitch_diag_trace")
    op.execute("DROP TABLE IF EXISTS stepstitch_diagnostics")
