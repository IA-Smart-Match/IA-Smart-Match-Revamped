"""The instructor's unlock panel read: exercise events and their lock state.

Its own module because ``instructor_repository.py`` sits at this repository's
800-line ceiling and was already split once for crossing it (review round 2,
F4). :meth:`ExerciseInstructorRepository.list_exercise_events` delegates here.

Only ``exercise_`` tables, imported by object for the allow-list walk in
``tests/unit/test_exercise_persistence_tables.py`` (ADR-0025 D2). Nothing here
commits.
"""

from __future__ import annotations

import uuid

import sqlalchemy as sa
from sqlalchemy.orm import Session

from smartmatch_persistence.exercise.instructor_rows import InstructorEventRow
from smartmatch_persistence.exercise.schema import exercise_event, exercise_result_unlock

__all__ = ["select_exercise_events"]


def select_exercise_events(
    session: Session, *, dataset_id: uuid.UUID
) -> tuple[InstructorEventRow, ...]:
    """The events the teams run in one data file, in file order, with lock state.

    Only ``is_exercise_event`` rows: the past events are history a profile may
    have attended, and unlocking one opens nothing a team can run. ``unlocked``
    is an ``EXISTS`` on the ``exercise_result_unlock`` row that
    ``unlock_results`` writes, so a reload shows what the database holds.
    """
    is_unlocked = (
        sa.exists()
        .where(
            exercise_result_unlock.c.dataset_id == exercise_event.c.dataset_id,
            exercise_result_unlock.c.event_key == exercise_event.c.event_key,
        )
        .label("unlocked")
    )
    statement = (
        sa.select(
            exercise_event.c.event_key,
            exercise_event.c.name,
            exercise_event.c.sequence,
            is_unlocked,
        )
        .where(
            exercise_event.c.dataset_id == dataset_id,
            exercise_event.c.is_exercise_event.is_(True),
        )
        .order_by(exercise_event.c.sequence)
    )
    return tuple(
        InstructorEventRow(
            event_key=row.event_key,
            name=row.name,
            sequence=row.sequence,
            unlocked=bool(row.unlocked),
        )
        for row in session.execute(statement).all()
    )
