"""Design spec §6's saved weight settings: list, read, save, delete.

A team's own view of the profiles used to live here too, and no longer does
(review round 1): a saved weighting and a profile read are two questions, and
the module that answered both would be imported by the results track for the
second while inheriting the first. It is
``smartmatch_persistence.exercise.team_view_repository``, with its own
``ignore_imports`` edge from the one door.

ADR-0025 D2 in one sentence
===========================
Every statement here names a table beginning ``exercise_``. No ``tenant_id``, no
``owning_unit_id``, no join to ``user_account``, and no principal.
``tests/unit/test_exercise_persistence_tables.py`` walks this package and
refuses a table name without the prefix.

ADR-0025 D6 — the withheld column
=================================
Nothing here selects from ``exercise_profile`` at all, so the withheld column is
not reachable from this module by any statement it contains. Every write goes
through the scrubber below, so a refused write carries no ``[parameters: …]``.

Transaction boundaries belong to the caller
===========================================
Every method takes a :class:`~sqlalchemy.orm.Session` and **commits nothing**,
like every other repository in this package. ``get_exercise_session`` rolls back
unconditionally, so a route that writes and forgets to commit stores nothing.

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

from smartmatch_persistence.exercise.schema import exercise_saved_setting

__all__ = [
    "MAX_SAVED_SETTINGS_PER_EVENT",
    "SAVED_SETTING_LOCK_KEY",
    "ExerciseSettingsRepository",
    "ExerciseSettingsWriteRefused",
    "SavedSetting",
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
#: no measured gain.
#:
#: The lock order for this family, stated once, here (review round 1)
#: ------------------------------------------------------------------
#: Three kinds of lock exist in the ``exercise_`` tables, and **every path that
#: takes more than one takes them in this order**::
#:
#:     WORKSPACE_MEMBERSHIP_LOCK_KEY  ->  SAVED_SETTING_LOCK_KEY  ->  row locks
#:
#: * ``save_setting`` / ``delete_setting`` take this key, then row-lock what they
#:   write. They never take the membership key.
#: * ``workspace_repository.reset_team`` and
#:   ``instructor_repository.reset_workspace_children`` take this key before they
#:   delete a team's settings — which is what review round 1 added, and why: a
#:   reset that deleted outside the key could run its ``DELETE`` between a
#:   concurrent save's count and its commit, and under READ COMMITTED the delete
#:   simply does not see the uncommitted row. The save then commits, and the team
#:   is left holding a setting the reset was meant to clear.
#: * ``instructor_repository.repoint_workspaces`` takes the membership key,
#:   then this key directly — before either of its ``FOR UPDATE`` scans — then
#:   row locks. That is the full order and it is the only path that takes all
#:   three. Review round 2 (F1) moved the acquire up front: the earlier shape
#:   reached this key inside ``reset_workspace_children``, *after* the row
#:   locks, which is this order read backwards — a concurrent ``save_setting``
#:   holds this key and then needs a workspace row for
#:   ``exercise_saved_setting``'s composite foreign key, and each waited on
#:   what the other held. The loop's own acquire still runs, but a transaction
#:   advisory lock is re-entrant, so it costs one round trip.
#:
#: Because the order is total and no path ever takes the membership key *after*
#: this one, neither key can be an edge of a wait-for cycle. The integration
#: file probes both directions of that claim with
#: ``pg_try_advisory_xact_lock`` rather than asserting it here in prose.
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
