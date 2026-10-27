"""Every ranked list holds sixty names, and nothing can change that.

Revision ID: 0049_exercise_invite_fixed
Revises: 0048_exercise_team_code
Create Date: 2026-10-27

Ann Wang's answer (b) on #413, 2026-10-22: "List size: 60, fixed for this
class. No instructor setting needed." The instructor route that changed it is
gone, so every data file moves to 60 and ``ck_exercise_dataset_invite_limit``
narrows from ``>= 1`` to ``= 60``. The downgrade widens the check again; it
cannot know what a file held before, so every file stays at 60.
"""

from __future__ import annotations

from alembic import op

revision = "0049_exercise_invite_fixed"
down_revision = "0048_exercise_team_code"
branch_labels = None
depends_on = None

_TABLE = "exercise_dataset"
_CHECK = "ck_exercise_dataset_invite_limit"


def upgrade() -> None:
    """Move every file to 60, then allow only 60."""
    op.execute(f"UPDATE {_TABLE} SET invite_limit = 60 WHERE invite_limit <> 60")
    op.drop_constraint(_CHECK, _TABLE, type_="check")
    op.create_check_constraint(_CHECK, _TABLE, "invite_limit = 60")


def downgrade() -> None:
    """Allow any positive limit again."""
    op.drop_constraint(_CHECK, _TABLE, type_="check")
    op.create_check_constraint(_CHECK, _TABLE, "invite_limit >= 1")
