"""The class exercise records which events are broad and exploratory.

Revision ID: 0043_exercise_event_exploratory
Revises: 0042_exercise_ann_dataset
Create Date: 2026-09-25

OQ-CE-14 was decided on 2026-09-25 (Ann Wang, email reply to the team's
question list): an ``Undecided`` career goal "should match broad exploratory
events (company talks, industry panels, career fairs), at half credit", and
"the results step should treat undecided students the same way". Whether an
event is exploratory is a property of the event, and Ann's file says it in the
``event_type`` column — which revision 0042 deliberately did not store,
because nothing read it then.

``exercise_event.is_exploratory``
    ``BOOLEAN NOT NULL DEFAULT false``. Derived at ingest from ``event_type``
    through ``smartmatch_domain.exercise.vocabulary.EXERCISE_EVENT_TYPES``.

Why a derived boolean rather than the ``event_type`` text: the flag is the only
thing any reader needs, and storing the text would put a vocabulary either in a
``CHECK`` (the owner ruled vocabularies closed *in code*, where a change is an
edit rather than a migration) or nowhere (free text compared at read time). A
boolean needs no ``CHECK`` at all, so no constraint is declared in
``tests/integration/test_check_constraints.py``.

Existing rows get ``false``: a dataset stored before this revision ranks and
simulates exactly as it did, with an undecided goal earning nothing.
Re-uploading Ann's file sets the flag, and Northline and Harbor come out
exploratory.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0043_exercise_event_exploratory"
down_revision = "0042_exercise_ann_dataset"
branch_labels = None
depends_on = None

_TABLE = "exercise_event"
_COLUMN = "is_exploratory"


def upgrade() -> None:
    """Add the flag, false for every event already stored."""
    op.add_column(
        _TABLE,
        sa.Column(_COLUMN, sa.Boolean, nullable=False, server_default=sa.text("false")),
    )


def downgrade() -> None:
    """Drop it again. The flag is lost; re-upload the file after upgrading."""
    op.drop_column(_TABLE, _COLUMN)
