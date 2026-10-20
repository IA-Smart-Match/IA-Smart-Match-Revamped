"""The default ranked list is sixty names, not thirty.

Revision ID: 0047_exercise_invite_sixty
Revises: 0046_exercise_run_snapshot
Create Date: 2026-10-19

Ann Wang's decision of 2026-10-16: CBACH sends 60 tailored emails in round one
(Northline) and 60 in round two (Harbor); the 300-student mass email stays as
the comparison. Seats stay at 60.

``exercise_dataset.invite_limit``
    The column's server default moves from 30 to 60, and every data file still
    at the old default (30) moves with it. A file an instructor deliberately
    set to anything else is left alone. The downgrade reverses both; a file
    that was set to 60 by hand reads 30 again after it.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0047_exercise_invite_sixty"
down_revision = "0046_exercise_run_snapshot"
branch_labels = None
depends_on = None

_TABLE = "exercise_dataset"
_COLUMN = "invite_limit"


def _move(old: int, new: int) -> None:
    op.alter_column(_TABLE, _COLUMN, server_default=sa.text(str(new)))
    op.execute(f"UPDATE {_TABLE} SET {_COLUMN} = {new} WHERE {_COLUMN} = {old}")


def upgrade() -> None:
    """Default 60, and every file still at 30 follows."""
    _move(30, 60)


def downgrade() -> None:
    """Default 30 again, and every file at 60 follows."""
    _move(60, 30)
