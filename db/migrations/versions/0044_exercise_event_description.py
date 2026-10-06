"""The class exercise stores the short description an event's file row carries.

Revision ID: 0044_exercise_event_description
Revises: 0043_exercise_event_exploratory
Create Date: 2026-10-06

Ann Wang's 2026-10-02 revisions (§5, "Event descriptions") ask for a short
description at the top of the Northline and Harbor pages and next to each event
on the instructor page: "The text is in the new ``event_description`` column of
the attached Excel file. Take it from the file, so I can change it later by
uploading a new file." (#318.)

``exercise_event.description``
    ``TEXT``, nullable, no server default. The text of the file's
    ``event_description`` cell, or ``NULL`` when the cell is blank (the ten
    past events) or the file has no such column (every file before
    2026-10-02).

Why nullable with no default: ``NULL`` is the honest reading of "this file said
nothing", and a reader renders no description for it. Existing rows therefore
need no backfill — a dataset stored before this revision shows no description
until the new file is uploaded and the teams are moved to it.

Why no ``CHECK``: the text is free prose bounded at ingest
(``smartmatch_domain.exercise.layout``), the one place a value enters, so no
constraint is declared in ``tests/integration/test_check_constraints.py``.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0044_exercise_event_description"
down_revision = "0043_exercise_event_exploratory"
branch_labels = None
depends_on = None

_TABLE = "exercise_event"
_COLUMN = "description"


def upgrade() -> None:
    """Add the column, NULL for every event already stored."""
    op.add_column(_TABLE, sa.Column(_COLUMN, sa.Text, nullable=True))


def downgrade() -> None:
    """Drop it again. The text is lost; re-upload the file after upgrading."""
    op.drop_column(_TABLE, _COLUMN)
