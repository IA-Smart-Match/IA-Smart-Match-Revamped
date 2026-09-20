"""Saved weight settings, and a team's own view of the profiles (design spec §2, §6).

Two reads and three writes, for CE-MATCHING-API. They share a module because
they share a caller and a door: the matching routes take one repository handle
each through ``smartmatch_api.exercise_dependencies``, and every ``ignore_imports``
edge that door needs is one line per *module* in ``pyproject.toml``.

ADR-0025 D2 in one sentence
===========================
Every statement here names a table beginning ``exercise_``. No ``tenant_id``, no
``owning_unit_id``, no join to ``user_account``, and no principal.
``tests/unit/test_exercise_persistence_tables.py`` walks this package and
refuses a table name without the prefix.

ADR-0025 D6 — the withheld column
=================================
:meth:`ExerciseTeamViewRepository.list_team_profiles` projects through
``exercise_profile_public_columns()``, so ``hidden_true_interests`` is absent
from the ``SELECT`` by construction rather than dropped afterwards. Nothing in
this module names that column, and nothing here calls
``dataset_repository.load_simulation_profiles``, which is its one reader.

Transaction boundaries belong to the caller
===========================================
Every method takes a :class:`~sqlalchemy.orm.Session` and **commits nothing**,
like every other repository in this package. ``get_exercise_session`` rolls back
unconditionally, so a route that writes and forgets to commit stores nothing.

A team's view of a profile is base ⟕ overlay
============================================
Design spec §2: *"Per-team mutations only. A team's view of a profile is base
row ⟕ overlay."* The overlay table is empty until the refresh track (design spec
§13) writes to it, and the join is still written and tested now — because a join
added later, under a deadline, against a table that has rows in it, is a join
that gets written wrong once and discovered in a classroom.

The at-most-three rule, and why it is a lock
============================================
Design spec §2 on ``exercise_saved_setting``: *"UNIQUE (workspace_id, event_key,
name); at most three per (workspace, event), enforced in the repository and by a
partial check."* Migration ``0037`` created the UNIQUE constraint and **no**
partial check — a count is not a uniqueness and expressing it in DDL would take
a trigger, which ``schema.py`` says in as many words. So the cap is this
module's, and a count read outside a lock is a count that two concurrent saves
both pass: each sees three, each inserts a fourth, and the team ends with five.
:data:`SAVED_SETTING_LOCK_KEY` is what makes the two take turns.
"""

from __future__ import annotations

import hashlib
import logging
import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Final

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from smartmatch_persistence.exercise.schema import (
    exercise_profile,
    exercise_profile_overlay,
    exercise_profile_public_columns,
    exercise_saved_setting,
)

__all__ = [
    "MAX_SAVED_SETTINGS_PER_EVENT",
    "SAVED_SETTING_LOCK_KEY",
    "ExerciseSettingsRepository",
    "ExerciseSettingsWriteRefused",
    "ExerciseTeamViewRepository",
    "SavedSetting",
    "TeamProfileRow",
    "TooManySavedSettingsError",
    "lock_saved_settings",
]

_LOGGER = logging.getLogger(__name__)

#: Design spec §6: *"a fourth name is refused with a sentence"*. Three, as a
#: named constant rather than a literal in a comparison, because the number is
#: the rule and the sentence the instructor's teams read quotes it.
MAX_SAVED_SETTINGS_PER_EVENT: Final[int] = 3

#: The advisory-lock key every statement that changes *how many* saved settings a
#: team has takes first.
#:
#: **Why a lock at all.** The cap is a count, and migration ``0037`` has no
#: constraint that can express one. Two saves racing on the same (workspace,
#: event) would each read two existing names and each insert a third and a
#: fourth. The UNIQUE constraint does not catch it: the two names differ.
#:
#: **Derived, not chosen**, exactly as
#: :data:`~smartmatch_persistence.exercise.workspace_repository.WORKSPACE_MEMBERSHIP_LOCK_KEY`
#: is: the first eight bytes of the SHA-256 of the table's own name, read as
#: PostgreSQL's signed ``bigint``. It cannot silently collide with that key
#: unless two different table names hash alike.
#:
#: **Coarse, and deliberately.** One key serialises saved-setting writes across
#: every team rather than per workspace. Six teams saving a named weighting
#: between two clicks is not contention, the work inside the lock is two short
#: statements, and a per-workspace key would be a second thing to get right for
#: no measured gain. Nothing else is locked on these paths, so this key is never
#: one edge of a cycle.
SAVED_SETTING_LOCK_KEY: Final[int] = int.from_bytes(
    hashlib.sha256(b"exercise_saved_setting").digest()[:8], "big", signed=True
)


def lock_saved_settings(session: Session) -> None:
    """Take :data:`SAVED_SETTING_LOCK_KEY` for the caller's transaction.

    ``pg_advisory_xact_lock`` rather than ``pg_advisory_lock``, for
    ``lock_workspace_membership``'s reason: the transaction form is released
    whichever way the transaction ends, so a caller that raises cannot wedge the
    classroom until the connection is recycled.
    """
    session.execute(sa.select(sa.func.pg_advisory_xact_lock(SAVED_SETTING_LOCK_KEY)))


class ExerciseSettingsWriteRefused(Exception):
    """The database refused a saved-settings write, with no driver text attached.

    ADR-0025 D6, the door ``instructor_repository.ExerciseWriteRefused`` and
    ``dataset_repository.ExerciseDatasetWriteError`` hold shut, held shut again
    here and for the same reason: SQLAlchemy's ``DBAPIError`` renders the
    statement **plus** ``[parameters: …]``, and anything that logs it, returns
    it, or lets a test runner print it has published whatever was in the
    parameters.

    What is logged instead is the **constraint name** and the **dataset id**:
    what an operator needs to act, and nothing that could be a row value. Raised
    from *outside* the ``except`` block that built it, so ``__context__`` is
    ``None`` rather than merely suppressed.
    """


class TooManySavedSettingsError(Exception):
    """A fourth *new* name on one (workspace, event). Not a database failure.

    Separate from :class:`ExerciseSettingsWriteRefused` because it is a fact
    about what the team asked for rather than about what the database did, and
    the API answers the two with different statuses. It carries a plain sentence
    a class participant reads on a projector, naming no table and no identifier.
    """


def _tuple(value: object) -> tuple[str, ...]:
    """A PostgreSQL text array as a tuple. ``NULL`` reads as empty."""
    return tuple(str(item) for item in value) if isinstance(value, list) else ()


def _optional_tuple(value: object) -> tuple[str, ...] | None:
    """The same, keeping ``NULL`` distinct from ``{}`` (design spec §7)."""
    return None if value is None else _tuple(value)


def _constraint_name(error: SQLAlchemyError) -> str:
    """The constraint a driver error names, or ``"unknown"``.

    Read from ``psycopg``'s structured diagnostics rather than from the
    exception's rendered text: the text is the leak, the diagnostic field is a
    schema identifier.
    """
    original = getattr(error, "orig", None)
    diagnostic = getattr(original, "diag", None)
    name = getattr(diagnostic, "constraint_name", None)
    return str(name) if name else "unknown"


@dataclass(frozen=True, slots=True)
class SavedSetting:
    """One named weighting a team saved for one event (design spec §6).

    Carries no ``id`` and no ``workspace_id``: a team addresses its own settings
    by name, through its own cookie, and an identifier on this value is an
    identifier one ``model_dump()`` away from a response.

    Attributes:
        event_key: The event the weighting was saved against.
        name: What the team called it.
        weights: The four weights, as the team saved them. Echoed back to the
            team that set them and to nobody else (ADR-0025 D8 permits exactly
            this and no other number).
        created_at: When the row was first written.
    """

    event_key: str
    name: str
    weights: Mapping[str, float]
    created_at: datetime


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

        Ordered by ``profile_no``, which is the data file's own order. Every
        caller that derives anything order-dependent from this read — the
        placeholder class-year ranking, for one — gets the same sequence for the
        same dataset in every process.

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
            )
            for row in session.execute(statement).all()
        )


class ExerciseSettingsRepository:
    """Design spec §6's saved settings: list, read, save, delete. Commits nothing."""

    def list_settings(
        self, session: Session, *, workspace_id: uuid.UUID, event_key: str
    ) -> tuple[SavedSetting, ...]:
        """This team's saved weightings for one event, oldest first.

        Oldest first so that the order a screen shows is the order the team
        created them in, and so a truncation — which cannot happen under a cap of
        three, but could if the cap ever moved — would cut at a stable point.
        """
        return self._select(
            session,
            exercise_saved_setting.c.workspace_id == workspace_id,
            exercise_saved_setting.c.event_key == event_key,
        )

    def get_setting(
        self, session: Session, *, workspace_id: uuid.UUID, event_key: str, name: str
    ) -> SavedSetting | None:
        """One saved weighting by name, or ``None`` when this team has no such name.

        Scoped to ``workspace_id`` in the statement rather than filtered
        afterwards: another team's setting of the same name is not merely hidden,
        it is not selected.
        """
        found = self._select(
            session,
            exercise_saved_setting.c.workspace_id == workspace_id,
            exercise_saved_setting.c.event_key == event_key,
            exercise_saved_setting.c.name == name,
        )
        return found[0] if found else None

    def save_setting(
        self,
        session: Session,
        *,
        dataset_id: uuid.UUID,
        workspace_id: uuid.UUID,
        event_key: str,
        name: str,
        weights: Mapping[str, float],
    ) -> SavedSetting:
        """Store four weights under a name, or refuse a fourth new name.

        The order of the three statements is the rule, not a style:

        1. :func:`lock_saved_settings`, **first**, so the count below cannot be
           read by two transactions that then both insert.
        2. Count this team's names for this event, and whether ``name`` is
           already one of them. Overwriting an existing name is always allowed —
           it changes no count — and is what a team does when it adjusts a
           weighting it has already saved.
        3. ``INSERT … ON CONFLICT (workspace_id, event_key, name) DO UPDATE``,
           so the overwrite is one statement and cannot lose a race with a
           delete.

        Args:
            session: Not committed here. The lock is released by the caller's
                commit or rollback, so the count and the insert must be in one
                transaction — which they are, because they are in one method.
            dataset_id: The workspace's dataset. Written to the row because
                ``exercise_saved_setting``'s foreign keys are composite; a
                mismatch is unrepresentable rather than something to check.
            workspace_id: The team's workspace.
            event_key: The event the weighting is for.
            name: What the team called it. Already trimmed and bounded by the
                caller; ``ck_exercise_saved_setting_name_shape`` is the backstop.
            weights: The validated weights. Validation belongs to
                ``smartmatch_domain.exercise.registry.validate_exercise_weight_overrides``
                and has already happened; this method stores what it is given.

        Returns:
            The stored setting, read back so the caller reports what is in the
            table rather than what it sent.

        Raises:
            TooManySavedSettingsError: for a fourth *new* name, with the
                sentence a class participant reads.
            ExerciseSettingsWriteRefused: if the database refuses the write.
        """
        lock_saved_settings(session)
        existing = self.list_settings(session, workspace_id=workspace_id, event_key=event_key)
        if len(existing) >= MAX_SAVED_SETTINGS_PER_EVENT and not any(
            setting.name == name for setting in existing
        ):
            raise TooManySavedSettingsError(
                f"Your team can keep {MAX_SAVED_SETTINGS_PER_EVENT} saved settings for "
                "this event. Delete one before saving another."
            )
        statement = (
            pg_insert(exercise_saved_setting)
            .values(
                id=uuid.uuid4(),
                workspace_id=workspace_id,
                dataset_id=dataset_id,
                event_key=event_key,
                name=name,
                weights=dict(weights),
            )
            .on_conflict_do_update(
                constraint="uq_exercise_saved_setting_name",
                set_={"weights": dict(weights)},
            )
        )
        self._execute(
            session,
            statement,
            dataset_id=dataset_id,
            refusal="Your settings could not be saved.",
        )
        stored = self.get_setting(
            session, workspace_id=workspace_id, event_key=event_key, name=name
        )
        if stored is None:  # pragma: no cover - requires a concurrent delete
            raise ExerciseSettingsWriteRefused("Your settings could not be saved.")
        return stored

    def delete_setting(
        self,
        session: Session,
        *,
        dataset_id: uuid.UUID,
        workspace_id: uuid.UUID,
        event_key: str,
        name: str,
    ) -> bool:
        """Remove one named weighting. ``True`` when a row went.

        Takes the same lock as :meth:`save_setting`, so a delete and a save
        cannot interleave between the cap's count and its insert — without it a
        team that deleted one name and saved another at the same moment could
        end with four.

        ``False`` rather than an exception for a name this team does not have:
        deleting something that is not there has the outcome the team asked for,
        and the API answers a name it cannot find with its own sentence.
        """
        lock_saved_settings(session)
        removed = self._execute(
            session,
            sa.delete(exercise_saved_setting)
            .where(
                exercise_saved_setting.c.workspace_id == workspace_id,
                exercise_saved_setting.c.event_key == event_key,
                exercise_saved_setting.c.name == name,
            )
            .returning(exercise_saved_setting.c.id),
            dataset_id=dataset_id,
            refusal="That setting could not be deleted.",
        )
        return bool(removed.all())

    # -----------------------------------------------------------------------
    # Internals
    # -----------------------------------------------------------------------

    @staticmethod
    def _select(session: Session, *conditions: sa.ColumnElement[bool]) -> tuple[SavedSetting, ...]:
        """The one read shape in this class, with every column named.

        ``sa.select(table)`` would carry ``id``, ``workspace_id`` and
        ``dataset_id`` into whatever a caller built from the row. Naming the four
        columns is what makes that impossible rather than unlikely.
        """
        statement = (
            sa.select(
                exercise_saved_setting.c.event_key,
                exercise_saved_setting.c.name,
                exercise_saved_setting.c.weights,
                exercise_saved_setting.c.created_at,
            )
            .where(*conditions)
            .order_by(
                exercise_saved_setting.c.created_at,
                exercise_saved_setting.c.name,
            )
        )
        return tuple(
            SavedSetting(
                event_key=row.event_key,
                name=row.name,
                weights={str(key): float(value) for key, value in dict(row.weights).items()},
                created_at=row.created_at,
            )
            for row in session.execute(statement).all()
        )

    def _failure_for(
        self, error: SQLAlchemyError, *, dataset_id: uuid.UUID, refusal: str
    ) -> ExerciseSettingsWriteRefused:
        """Log a refused write and build the exception to raise for it.

        **Builds, and deliberately does not raise**, so that the caller can raise
        it after its own ``except`` block has ended — which is the whole of what
        makes ``__context__`` ``None``. ``raise … from None`` would only set
        ``__suppress_context__``, leaving the driver error and its
        ``[parameters: …]`` reachable on the object (ADR-0025 D6).

        The line carries the constraint name and the dataset id and nothing that
        could be a row value: a constraint name is schema, and a dataset id names
        a file rather than a row in it.
        """
        _LOGGER.warning(
            "exercise saved-setting write refused: constraint=%s dataset_id=%s error=%s",
            _constraint_name(error),
            dataset_id,
            type(error).__name__,
        )
        return ExerciseSettingsWriteRefused(refusal)

    def _execute(
        self,
        session: Session,
        statement: sa.Executable,
        *,
        dataset_id: uuid.UUID,
        refusal: str,
    ) -> sa.CursorResult[sa.Row[tuple[object, ...]]]:
        """Run one statement, letting no driver text out of this module."""
        try:
            return session.execute(statement)  # type: ignore[return-value]
        except SQLAlchemyError as exc:
            failure = self._failure_for(exc, dataset_id=dataset_id, refusal=refusal)
        raise failure
