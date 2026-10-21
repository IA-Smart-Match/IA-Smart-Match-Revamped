"""Each class-exercise team gets a 4-digit entry code.

Revision ID: 0048_exercise_team_code
Revises: 0047_exercise_invite_sixty
Create Date: 2026-10-21

Issue #413 (Oct 23 class testing). The exercise is public, and until now a
team number alone opened that team's work. A team now also types its 4-digit
code; the instructor page shows all six.

``exercise_team_code``
    One row per team number 1-6, keyed by the number rather than by a
    workspace, because the instructor reads the codes out *before* any team has
    entered (and so before any workspace exists). The code is stored as text so
    a leading zero survives. It is stored in the clear on purpose: the
    instructor page has to show it. It is a classroom code over made-up
    profiles, not a credential to anything else.

Backfill
    The six rows are inserted here with codes from :mod:`secrets`. A rerun of
    the downgrade and upgrade issues new codes.

Grants
    The runtime role (docs/operations/exercise-hosting.md §3) is not the role
    migrations run as. Every role that can already update
    ``exercise_team_workspace`` is granted ``SELECT, UPDATE`` on the new table,
    so a deployment with a dedicated exercise role keeps working without a
    manual grant. A deployment without one grants nothing.
"""

from __future__ import annotations

import secrets

import sqlalchemy as sa
from alembic import op

revision = "0048_exercise_team_code"
down_revision = "0047_exercise_invite_sixty"
branch_labels = None
depends_on = None

_TABLE = "exercise_team_code"

#: Fixed by the requirements' "Getting in" row; restated because a migration
#: must not import application code that may change after it is written.
_TEAMS = range(1, 7)


def upgrade() -> None:
    """Create the table, give every team a code, and mirror the runtime grant."""
    table = op.create_table(
        _TABLE,
        sa.Column("team_number", sa.Integer, nullable=False, autoincrement=False),
        sa.Column("code", sa.Text, nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("team_number", name="exercise_team_code_pkey"),
        sa.CheckConstraint("team_number BETWEEN 1 AND 6", name="ck_exercise_team_code_team_number"),
        sa.CheckConstraint("code ~ '^[0-9]{4}$'", name="ck_exercise_team_code_shape"),
    )
    op.bulk_insert(
        table,
        [{"team_number": team, "code": f"{secrets.randbelow(10_000):04d}"} for team in _TEAMS],
    )
    op.execute(
        """
        DO $$
        DECLARE grantee_name text;
        BEGIN
          FOR grantee_name IN
            SELECT DISTINCT grantee FROM information_schema.role_table_grants
            WHERE table_name = 'exercise_team_workspace'
              AND table_schema = current_schema()
              AND privilege_type = 'UPDATE'
              AND grantee <> current_user
              AND grantee <> 'PUBLIC'
          LOOP
            EXECUTE format('GRANT SELECT, UPDATE ON exercise_team_code TO %I', grantee_name);
          END LOOP;
        END $$;
        """
    )


def downgrade() -> None:
    """Drop the table; teams go back to entering a number alone."""
    op.drop_table(_TABLE)
