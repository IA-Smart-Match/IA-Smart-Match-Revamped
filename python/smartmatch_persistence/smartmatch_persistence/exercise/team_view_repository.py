"""A team's own view of the profiles: base row ⟕ overlay (design spec §2).

Split out of ``settings_repository.py`` (review round 1). A saved weighting and
a profile read are two questions, and a module that answers both is a module the
results track would import for the second while inheriting the first — so the
seam is cut here, before anything depends on the wrong name. Each module gets
its own ``ignore_imports`` edge from ``smartmatch_api.exercise_dependencies``,
which is what keeps that door's edge list a description of what is actually
reached rather than a list of modules that happen to share a file.

ADR-0025 D2 in one sentence
===========================
Every statement here names a table beginning ``exercise_``. No ``tenant_id``, no
``owning_unit_id``, no join to ``user_account``, and no principal.
``tests/unit/test_exercise_persistence_tables.py`` walks this package and
refuses a table name without the prefix.

ADR-0025 D6 — the withheld column
=================================
The read projects through ``exercise_profile_public_columns()``, so
``hidden_true_interests`` is absent from the ``SELECT`` by construction rather
than dropped afterwards. Nothing in this module names that column, and nothing
here calls ``dataset_repository.load_simulation_profiles``, which is its one
reader.

Transaction boundaries belong to the caller
===========================================
The one method takes a :class:`~sqlalchemy.orm.Session` and **commits nothing**,
like every other repository in this package. It writes nothing at all, so it
takes no lock and appears nowhere in this family's lock order.

Why the join is written now
===========================
Design spec §2: *"Per-team mutations only. A team's view of a profile is base
row ⟕ overlay."* The overlay table is empty until the refresh track (design spec
§13) writes to it, and the join is still written and tested now — because a join
added later, under a deadline, against a table that has rows in it, is a join
that gets written wrong once and discovered in a classroom.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

import sqlalchemy as sa
from sqlalchemy.orm import Session

from smartmatch_persistence.exercise.schema import (
    exercise_profile,
    exercise_profile_overlay,
    exercise_profile_public_columns,
)

__all__ = [
    "ExerciseTeamViewRepository",
    "TeamProfileRow",
]


def _tuple(value: object) -> tuple[str, ...]:
    """A PostgreSQL text array as a tuple. ``NULL`` reads as empty."""
    return tuple(str(item) for item in value) if isinstance(value, list) else ()


def _optional_tuple(value: object) -> tuple[str, ...] | None:
    """The same, keeping ``NULL`` distinct from ``{}`` (design spec §7)."""
    return None if value is None else _tuple(value)


@dataclass(frozen=True, slots=True)
class TeamProfileRow:
    """One profile as *this team* sees it: the base row joined to its overlay.

    Built from ``exercise_profile_public_columns()`` plus the overlay's own
    columns, so ``hidden_true_interests`` is absent by construction.

    The three-state rule of design spec §7 is preserved on both sides:
    ``stated_interests`` is ``None`` for "no card on file" and a tuple — possibly
    empty — for "a card with nothing on it". The overlay's ``card_interests`` is
    ``None`` for "this team has not been given a card for this profile", which is
    a different fact again, and the two are resolved by the caller rather than
    here: the repository reports what is stored.

    Attributes:
        profile_no: The profile's number in the data file.
        display_name: The made-up name. Every row is fictional.
        major: The major, or ``None`` when the file recorded none.
        class_year: The year, as the data file spells it, or ``None``.
        past_event_keys: The events attended, by key.
        stated_interests: The base row's card, or ``None`` for no card.
        career_goal: The base row's career goal, or ``None``.
        overlay_added_event_topics: Topics this team's refresh added (design
            spec §13). Empty when there is no overlay row.
        overlay_card_interests: A card this team was given, or ``None``.
        overlay_card_career_goal: That card's career goal, or ``None``.
        non_responding: Whether this team's refresh marked the profile as asked
            and not answering. False when there is no overlay row.
        tiebreak_order: Ann's fixed order for the last tie-break step, or
            ``None`` for a dataset stored before revision 0042.
    """

    profile_no: int
    display_name: str
    major: str | None
    class_year: str | None
    past_event_keys: tuple[str, ...]
    stated_interests: tuple[str, ...] | None
    career_goal: str | None
    overlay_added_event_topics: tuple[str, ...]
    overlay_card_interests: tuple[str, ...] | None
    overlay_card_career_goal: str | None
    non_responding: bool
    tiebreak_order: int | None = None


class ExerciseTeamViewRepository:
    """Reads the profiles of one dataset as one workspace sees them."""

    def list_team_profiles(
        self, session: Session, *, dataset_id: uuid.UUID, workspace_id: uuid.UUID
    ) -> tuple[TeamProfileRow, ...]:
        """Design spec §2's ``base row ⟕ overlay``, for one team.

        A LEFT OUTER JOIN rather than two reads and a merge in Python: the
        overlay's primary key is ``(workspace_id, profile_no)``, so the join is
        one row to at most one row, and doing it in the database is what keeps
        "this team's overlay" a key rather than a filter somebody has to
        remember to apply.

        **The workspace is part of the join condition, not of a ``WHERE``.** On
        an outer join the difference is the whole isolation property: in a
        ``WHERE`` the predicate would discard every profile this team has no
        overlay row for, silently shortening the dataset to whatever the team
        had already been given.

        Ordered by ``profile_no``, which is the data file's own order.

        Args:
            session: Not committed here. Reads only.
            dataset_id: The workspace's dataset. Passed rather than looked up so
                that the composite foreign keys' own shape is mirrored in the
                query, and so a caller cannot ask for one dataset's profiles
                through another dataset's workspace and get rows.
            workspace_id: The team's workspace.

        Returns:
            One :class:`TeamProfileRow` per profile in the dataset, in file
            order, **without** the withheld column.
        """
        overlay = exercise_profile_overlay
        statement = (
            sa.select(
                *exercise_profile_public_columns(),
                overlay.c.added_event_topics,
                overlay.c.card_interests,
                overlay.c.card_career_goal,
                overlay.c.non_responding,
            )
            .select_from(
                exercise_profile.outerjoin(
                    overlay,
                    sa.and_(
                        overlay.c.dataset_id == exercise_profile.c.dataset_id,
                        overlay.c.profile_no == exercise_profile.c.profile_no,
                        overlay.c.workspace_id == workspace_id,
                    ),
                )
            )
            .where(exercise_profile.c.dataset_id == dataset_id)
            .order_by(exercise_profile.c.profile_no)
        )
        return tuple(
            TeamProfileRow(
                profile_no=row.profile_no,
                display_name=row.display_name,
                major=row.major,
                class_year=row.class_year,
                past_event_keys=_tuple(row.past_event_keys),
                stated_interests=_optional_tuple(row.stated_interests),
                career_goal=row.career_goal,
                overlay_added_event_topics=_tuple(row.added_event_topics),
                overlay_card_interests=_optional_tuple(row.card_interests),
                overlay_card_career_goal=row.card_career_goal,
                non_responding=bool(row.non_responding),
                tiebreak_order=row.tiebreak_order,
            )
            for row in session.execute(statement).all()
        )
