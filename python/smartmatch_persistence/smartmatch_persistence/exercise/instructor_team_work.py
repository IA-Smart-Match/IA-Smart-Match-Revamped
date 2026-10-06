"""What one team has saved and run, as the instructor's page reads it.

Its own module for ``instructor_events.py``'s reason: ``instructor_repository``
sits at this repository's 800-line ceiling.
:meth:`ExerciseInstructorRepository.list_saved_settings` and
:meth:`ExerciseInstructorRepository.list_result_runs` delegate here.

Only ``exercise_`` tables, imported by object for the allow-list walk in
``tests/unit/test_exercise_persistence_tables.py`` (ADR-0025 D2). Nothing here
commits, and every statement is keyed on one ``workspace_id``: another team's
rows are not filtered out afterwards, they are not selected.
"""

from __future__ import annotations

import uuid

import sqlalchemy as sa
from sqlalchemy.orm import Session

from smartmatch_persistence.exercise.instructor_rows import (
    InstructorResultRun,
    InstructorSavedSetting,
)
from smartmatch_persistence.exercise.schema import exercise_result_run, exercise_saved_setting

__all__ = ["select_result_runs", "select_saved_settings"]


def select_saved_settings(
    session: Session, *, workspace_id: uuid.UUID
) -> tuple[InstructorSavedSetting, ...]:
    """A team's saved settings, oldest first. Names only, never the weights."""
    statement = (
        sa.select(
            exercise_saved_setting.c.event_key,
            exercise_saved_setting.c.name,
            exercise_saved_setting.c.created_at,
        )
        .where(exercise_saved_setting.c.workspace_id == workspace_id)
        .order_by(exercise_saved_setting.c.created_at, exercise_saved_setting.c.name)
    )
    return tuple(
        InstructorSavedSetting(event_key=row.event_key, name=row.name, created_at=row.created_at)
        for row in session.execute(statement).all()
    )


def select_result_runs(
    session: Session, *, workspace_id: uuid.UUID
) -> tuple[InstructorResultRun, ...]:
    """A team's result runs, by round.

    Counted in SQL — ``cardinality`` over the three arrays — so the profile
    numbers themselves are never fetched into this process, let alone
    returned. That is cheaper and it is also the D8 boundary written as a
    query rather than as a promise about what the caller does next.
    """
    statement = (
        sa.select(
            exercise_result_run.c.event_key,
            exercise_result_run.c.round,
            exercise_result_run.c.setting_name,
            sa.func.cardinality(exercise_result_run.c.invited_profile_nos).label("invited"),
            sa.func.cardinality(exercise_result_run.c.signed_up_profile_nos).label("signed_up"),
            sa.func.cardinality(exercise_result_run.c.attended_profile_nos).label("attended"),
            exercise_result_run.c.seats_empty,
            exercise_result_run.c.created_at,
        )
        .where(exercise_result_run.c.workspace_id == workspace_id)
        .order_by(exercise_result_run.c.round, exercise_result_run.c.created_at)
    )
    return tuple(
        InstructorResultRun(
            event_key=row.event_key,
            round=row.round,
            setting_name=row.setting_name,
            invited_count=row.invited,
            signed_up_count=row.signed_up,
            attended_count=row.attended,
            seats_empty=row.seats_empty,
            created_at=row.created_at,
        )
        for row in session.execute(statement).all()
    )
