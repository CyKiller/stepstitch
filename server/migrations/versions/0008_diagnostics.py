"""deep diagnostics from the local reproduction

Revision ID: 0008
Revises: 0007
Create Date: 2026-07-30

Stores what a local reproduction revealed about a failure — the stack, the console errors,
the failed requests, the snapshot at the moment it broke.

This is the one place StepStitch keeps rich technical detail, and what makes that
defensible is where it comes from: StepStitch's own run on a developer's machine, driven
by a generated test — provably not the reported session — with every string scrubbed
before storage. What it does NOT establish is that the content is customer-free: the run
targets whatever application the operator configured, and a staging backend with real
records prints what it prints, so the customer-data status of a record is not verified.
(An earlier revision of this docstring claimed "no customer in it"; that was a fact about
the session actor presented as a fact about the content.) The user's own failure trail
stays as small and scrubbed as it has always been. Depth from the reproduction, not from
surveillance — hence the explicit ``source`` column: ``local_reproduction`` for records
written at diagnostics schema 2 or later, ``synthetic_reproduction`` in older rows.

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
