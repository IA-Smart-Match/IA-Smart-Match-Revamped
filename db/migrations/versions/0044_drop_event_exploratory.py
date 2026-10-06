"""The class exercise no longer records which events are broad and exploratory.

Revision ID: 0044_drop_event_exploratory
Revises: 0043_exercise_event_exploratory
Create Date: 2026-10-05

Ann Wang's progress check and revisions of 2026-10-02 (item 4b) removed the
rule revision 0043 was added for: "It is being counted as fitting a 'broad
event.' That rule is not in the plan, and Northline is not a broad event.
Please remove it." An ``Undecided`` career goal now earns nothing from any
event, in matching and in the results step alike, so nothing reads the flag.

``exercise_event.is_exploratory``
    Dropped. No ``CHECK`` named it, so none is removed.

**This is a contract step shipped in the same release as the code that stops
reading the column.** ``script.py.mako`` asks for the destructive step to wait
until the release is promoted and stable; Chau decided on 2026-10-05 to drop
the column with the rule instead, before the class runs. The consequence: the
application as it stood at revision 0043 selects this column, so rolling the
application back needs ``alembic downgrade 0043_exercise_event_exploratory``
first.

The downgrade restores the column as 0043 created it, ``false`` for every
event. The flags a file once set are not recovered; re-uploading Ann's file
under the older application sets them again.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0044_drop_event_exploratory"
down_revision = "0043_exercise_event_exploratory"
branch_labels = None
depends_on = None

_TABLE = "exercise_event"
_COLUMN = "is_exploratory"


def upgrade() -> None:
    """Drop the flag. Nothing reads it."""
    op.drop_column(_TABLE, _COLUMN)


def downgrade() -> None:
    """Add it back as 0043 created it, false for every event stored."""
    op.add_column(
        _TABLE,
        sa.Column(_COLUMN, sa.Boolean, nullable=False, server_default=sa.text("false")),
    )
