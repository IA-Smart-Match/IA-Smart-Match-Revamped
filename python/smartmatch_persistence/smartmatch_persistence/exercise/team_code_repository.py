"""The six teams' 4-digit entry codes (revision 0048, issue #413).

A team types its number and its code to open its work. The instructor page
lists all six codes, and resetting a team gives it a new one. The rows are
seeded by the migration; nothing here inserts one, so a team with no row can
never be entered, which is the safe way round.
"""

from __future__ import annotations

import secrets

import sqlalchemy as sa
from sqlalchemy.orm import Session

from smartmatch_persistence.exercise import schema

__all__ = ["ExerciseTeamCodeRepository", "new_team_code"]

_TABLE = schema.exercise_team_code


def new_team_code() -> str:
    """A random 4-digit code. Leading zeros allowed, so ``"0042"`` is valid."""
    return f"{secrets.randbelow(10_000):04d}"


class ExerciseTeamCodeRepository:
    """Read and rotate ``exercise_team_code`` rows."""

    def code_for(self, session: Session, *, team_number: int) -> str | None:
        """The team's current code, or ``None`` if the team has no row."""
        return session.execute(
            sa.select(_TABLE.c.code).where(_TABLE.c.team_number == team_number)
        ).scalar_one_or_none()

    def all_codes(self, session: Session) -> dict[int, str]:
        """Every team's code, by team number."""
        rows = session.execute(sa.select(_TABLE.c.team_number, _TABLE.c.code))
        return {team: code for team, code in rows}

    def rotate(self, session: Session, *, team_number: int) -> None:
        """Give the team a new code, in the caller's transaction."""
        session.execute(
            sa.update(_TABLE)
            .where(_TABLE.c.team_number == team_number)
            .values(code=new_team_code(), updated_at=sa.func.now())
        )
