"""Results for an exercise event can be closed again.

Revision ID: 0045_exercise_unlock_closed_at
Revises: 0044_exercise_event_description
Create Date: 2026-10-06

Ann Wang's revisions of 2026-10-02, area 2: "Opening or closing results for an
event shows the time it was done, and results can be closed again." Until this
revision ``exercise_result_unlock`` could only gain rows: the absence of a row
was "locked", a row was "open", and nothing could take a row back.

``exercise_result_unlock.closed_at``
    ``TIMESTAMPTZ NULL``. The lock is now three states read off one row:

    * no row — results were never opened;
    * a row with ``closed_at IS NULL`` — results are open;
    * a row with ``closed_at`` set — results were opened and closed again.

    Opening a closed event clears ``closed_at`` and moves ``unlocked_at`` to
    the time of that opening, so each column answers "when was this last
    done". Recorded as the dated amendment under D16 in
    ``docs/decisions/class-exercise-decisions-2026-09-25.md``.

Existing rows get ``NULL`` and are therefore still open, exactly as they were:
no backfill is needed.

No ``CHECK`` is declared. A row is only ever created by an opening, so a close
with no opening before it cannot exist, and a reopening moves ``unlocked_at``
past the old ``closed_at`` before clearing it — the one ordering a constraint
could state is not an invariant of the row.

Deployment note: the exercise database role needs ``UPDATE`` on this table
from this revision on (``docs/operations/exercise-hosting.md``, the grant
block). Both the close and the reopening are refused without it.

The revision id is shorter than this file's name on purpose:
``alembic_version.version_num`` is ``VARCHAR(32)``, and the file's name is
longer than that. ``0040_speaker_booking_cancellation.py`` carries
``0040_booking_cancellation`` for the same reason.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0045_exercise_unlock_closed_at"
down_revision = "0044_exercise_event_description"
branch_labels = None
depends_on = None

_TABLE = "exercise_result_unlock"
_COLUMN = "closed_at"


def upgrade() -> None:
    """Add the column, empty for every row already stored: those stay open."""
    op.add_column(_TABLE, sa.Column(_COLUMN, sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    """Drop it again. An event that was closed reads as open after this."""
    op.drop_column(_TABLE, _COLUMN)
