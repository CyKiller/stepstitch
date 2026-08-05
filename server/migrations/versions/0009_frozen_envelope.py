"""the execution envelope lives with the freeze it belongs to

Revision ID: 0009
Revises: 0008
Create Date: 2026-07-31

The envelope digest existed before this migration — on ``stepstitch_diagnostics``, found
back by ``ORDER BY created_at DESC LIMIT 1``. That is the *latest* diagnostics row, which
after a re-freeze or a stray diagnostics run is not the frozen envelope at all. Since the
agent packet tells the fixing agent "verification reruns these exact bytes under the same
execution envelope", the heuristic made that sentence false in exactly the case where it
mattered. The digest now lives on the freeze row itself, 1:1 with the script it pins.

Both columns are nullable, and NULL is load-bearing: it is the honest marker for "frozen
before enforcement existed". Verification degrades for those rows (script hash still
enforced, envelope not, reported as ``envelope_enforced: false``) rather than refusing —
a refusal would force a re-freeze, and re-freezing after the agent has already edited the
application destroys the red baseline, the one artefact that cannot be recreated.

``execution_envelope_json`` is not decoration. A refusal whose message is two hex prefixes
is undiagnosable, and developers work around checks they cannot read; storing the frozen
record lets the refusal say *which field moved*. It carries no raw values — config settings, a
browser version, and environment variable NAMES, never values.
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "0009"
down_revision: Union[str, None] = "0008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# IF NOT EXISTS on both statements, because this migration is not the only writer of the
# schema: the host CI job (and any fresh deployment) bootstraps from db.py's SCHEMA_SQL,
# which already declares these columns, and alembic then replays history on top. Every
# earlier migration is idempotent against that pattern via CREATE TABLE IF NOT EXISTS;
# an ALTER without the guard was the one statement in nine migrations that could not be
# replayed — found by CI, not by the local suite, because SQLite tests never run alembic.
def upgrade() -> None:
    op.execute("ALTER TABLE stepstitch_frozen_repros "
               "ADD COLUMN IF NOT EXISTS execution_envelope_sha256 TEXT")
    op.execute("ALTER TABLE stepstitch_frozen_repros "
               "ADD COLUMN IF NOT EXISTS execution_envelope_json TEXT")


def downgrade() -> None:
    op.execute("ALTER TABLE stepstitch_frozen_repros "
               "DROP COLUMN IF EXISTS execution_envelope_sha256")
    op.execute("ALTER TABLE stepstitch_frozen_repros "
               "DROP COLUMN IF EXISTS execution_envelope_json")
