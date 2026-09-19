"""The rows the instructor page reads and writes (design spec §5, §9, §13, §14).

A repository of its own rather than more methods on the two that exist, for the
reason ``workspace_repository``'s docstring gives about read shapes: every
statement here is an *instructor* statement — it spans teams, it changes a
dataset-wide setting, or it moves workspaces — and none of them is something a
team's own route may run. Keeping them apart means the question "what can a
class participant's request reach" is answered by reading one file rather than
by checking which methods a router happens to call.

Nothing outside the ``exercise_`` family is referenced (ADR-0025 D2), the
tables are imported by object so the allow-list walk in
``tests/unit/test_exercise_persistence_tables.py`` can see them, and nothing
here commits: the caller's transaction is what makes the multi-statement
operations below atomic.

ADR-0025 D6 and D8
==================
No read here selects ``hidden_true_interests`` — the only reader of that column
in this package is ``dataset_repository.load_simulation_profiles`` and this
module does not call it. No row returned carries a score, a percentage or a
confidence: a result run is summarised by **counts**, which is what the
instructor's screen shows, and the profile numbers behind them stay in the
table. The sentence "no numeric score reaches a class participant" is not
weakened by "unless they are the instructor", because the instructor's screen
is on the same projector.

The re-point, and why its order is not optional
===============================================
``exercise/schema.py`` states it at length and this module is the half that
obeys it: the composite foreign keys from the overlay, the saved settings and
the result runs reference ``(dataset_id, id)`` on the workspace and are
``ON DELETE CASCADE`` only — not ``ON UPDATE CASCADE``. So an UPDATE of
``dataset_id`` is refused while a child row exists, and were it to succeed it
would leave a team's work pointing at profiles from a dataset it no longer
uses. :meth:`ExerciseInstructorRepository.repoint_workspaces` therefore deletes
each workspace's children **before** updating its ``dataset_id``, in the
caller's one transaction. That is design spec §3's own semantics rather than a
workaround: *a re-point resets every team*.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Final

import sqlalchemy as sa
from smartmatch_domain.exercise.workspace_token import new_workspace_seed
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from smartmatch_persistence.exercise.schema import (
    exercise_dataset,
    exercise_event,
    exercise_profile_overlay,
    exercise_result_run,
    exercise_result_unlock,
    exercise_saved_setting,
    exercise_team_workspace,
)

__all__ = [
    "MAX_INVITE_LIMIT",
    "MIN_INVITE_LIMIT",
    "ExerciseInstructorRepository",
    "ExerciseWriteRefused",
    "InstructorResultRun",
    "InstructorSavedSetting",
    "InstructorWorkspaceRow",
    "RepointOutcome",
    "TeamWorkspaceHandle",
]

_LOGGER = logging.getLogger(__name__)

#: The bounds design spec §5's invite limit is accepted within.
#:
#: The floor is ``ck_exercise_dataset_invite_limit`` (``invite_limit >= 1``),
#: restated so the refusal can be a sentence rather than a write failure. The
#: ceiling is this module's own and is **not** a number of Ann's: it is the
#: largest dataset the ingest path will accept
#: (``ingest.MAX_PROFILE_ROW_COUNT``), because a limit above the number of
#: profiles that can exist caps nothing. Ann's stated default, 30, lives in the
#: column's server default and is not repeated here.
MIN_INVITE_LIMIT: Final[int] = 1
MAX_INVITE_LIMIT: Final[int] = 1_000


class ExerciseWriteRefused(Exception):
    """The database refused an instructor write, with no driver text attached.

    ADR-0025 D6, the same door ``dataset_repository.ExerciseDatasetWriteError``
    holds shut and for the same reason: SQLAlchemy's ``DBAPIError`` renders the
    statement **plus** ``[parameters: …]``, and anything that logs it, returns
    it, or lets a test runner print it has published whatever was in the
    parameters.

    What is logged instead is the review follow-up this track carries: the
    **constraint name** and the **dataset id**, which is what an operator needs
    to act, and nothing else. A constraint name is schema, not data; a dataset
    id names a file, not a row in it. No cell value, no column value, and never
    the withheld column, appear in the line.

    Raised from *outside* the ``except`` block that built it, so ``__context__``
    is ``None`` rather than merely suppressed — ``raise ... from None`` sets
    ``__suppress_context__``, which hides the driver error from a printed
    traceback while leaving it, and its parameters, reachable on the object.
    """

    def __init__(self, message: str) -> None:
        super().__init__(message)


def _constraint_name(error: SQLAlchemyError) -> str:
    """The constraint a driver error names, or ``"unknown"``.

    Read from ``psycopg``'s structured diagnostics rather than from the
    exception's rendered text: the text is the leak, the diagnostic field is a
    schema identifier. ``"unknown"`` when the driver offers none, which is a
    real answer — a write can fail for reasons no constraint names.
    """
    original = getattr(error, "orig", None)
    diagnostic = getattr(original, "diag", None)
    name = getattr(diagnostic, "constraint_name", None)
    return str(name) if name else "unknown"


@dataclass(frozen=True, slots=True)
class TeamWorkspaceHandle:
    """Enough of a workspace for an instructor route to act on it.

    Carries no ``seed`` and no ``workspace_token_hash``, for
    ``workspace_repository.ExerciseWorkspace``'s reason: a value a handler
    already holds is a value one ``model_dump()`` away from a response.
    """

    id: uuid.UUID
    dataset_id: uuid.UUID
    team_number: int


@dataclass(frozen=True, slots=True)
class InstructorWorkspaceRow:
    """One team, as the instructor's list of teams shows it.

    Counts rather than contents: the list answers "which teams are working and
    how far have they got", and a list that carried each team's saved weights
    would put six teams' work on one screen for no one's benefit.
    """

    team_number: int
    dataset_label: str
    created_at: datetime
    saved_setting_count: int
    result_run_count: int
    asking_choice: str | None
    refreshed_at: datetime | None


@dataclass(frozen=True, slots=True)
class InstructorSavedSetting:
    """One of a team's saved settings (design spec §6), without its weights.

    The weights are the team's work and the instructor's screen lists what
    exists rather than reproducing it; a later track that needs to *open* a
    setting adds a read that names the column, at which point the exception is
    visible at the call site.
    """

    event_key: str
    name: str
    created_at: datetime


@dataclass(frozen=True, slots=True)
class InstructorResultRun:
    """One of a team's result runs (design spec §9/§10), summarised by counts.

    ``seats_empty`` is stored on the row rather than derived, so what is
    reported here is what the team was shown. No score, no percentage, no
    confidence (ADR-0025 D8), and no profile number — a run is described by how
    many, never by who.
    """

    event_key: str
    round: int
    setting_name: str | None
    invited_count: int
    signed_up_count: int
    attended_count: int
    seats_empty: int
    created_at: datetime


@dataclass(frozen=True, slots=True)
class RepointOutcome:
    """What a re-point did, in the two numbers the instructor's sentence needs."""

    moved: int
    discarded: int


class ExerciseInstructorRepository:
    """The instructor page's reads and writes. Commits nothing."""

    # -----------------------------------------------------------------------
    # Reads
    # -----------------------------------------------------------------------

    def list_workspaces(
        self, session: Session, *, dataset_id: uuid.UUID
    ) -> tuple[InstructorWorkspaceRow, ...]:
        """Every team working in ``dataset_id``, by team number.

        Scoped to one dataset rather than listing every workspace ever created:
        the instructor's question is "what are my six teams doing", and a team
        whose workspace belongs to a replaced file is not one of them until it
        is re-pointed.
        """
        settings = self._child_count(exercise_saved_setting).label("saved_setting_count")
        runs = self._child_count(exercise_result_run).label("result_run_count")
        statement = (
            sa.select(
                exercise_team_workspace.c.team_number,
                exercise_dataset.c.label,
                exercise_team_workspace.c.created_at,
                exercise_team_workspace.c.asking_choice,
                exercise_team_workspace.c.refreshed_at,
                settings,
                runs,
            )
            .select_from(
                exercise_team_workspace.join(
                    exercise_dataset,
                    exercise_team_workspace.c.dataset_id == exercise_dataset.c.id,
                )
            )
            .where(exercise_team_workspace.c.dataset_id == dataset_id)
            .order_by(exercise_team_workspace.c.team_number)
        )
        return tuple(
            InstructorWorkspaceRow(
                team_number=row.team_number,
                dataset_label=row.label,
                created_at=row.created_at,
                saved_setting_count=row.saved_setting_count,
                result_run_count=row.result_run_count,
                asking_choice=row.asking_choice,
                refreshed_at=row.refreshed_at,
            )
            for row in session.execute(statement).all()
        )

    @staticmethod
    def _child_count(table: sa.Table) -> sa.ScalarSelect[int]:
        """How many rows of ``table`` belong to the workspace being selected."""
        return (
            sa.select(sa.func.count())
            .select_from(table)
            .where(table.c.workspace_id == exercise_team_workspace.c.id)
            .scalar_subquery()
        )

    def find_workspace(
        self, session: Session, *, dataset_id: uuid.UUID, team_number: int
    ) -> TeamWorkspaceHandle | None:
        """The workspace for ``(dataset_id, team_number)``, or ``None``.

        ``None`` rather than a refusal, because "team 5 has not entered yet" is
        a real state of a classroom and not an error the repository can judge.
        """
        row = session.execute(
            sa.select(
                exercise_team_workspace.c.id,
                exercise_team_workspace.c.dataset_id,
                exercise_team_workspace.c.team_number,
            ).where(
                exercise_team_workspace.c.dataset_id == dataset_id,
                exercise_team_workspace.c.team_number == team_number,
            )
        ).one_or_none()
        if row is None:
            return None
        return TeamWorkspaceHandle(
            id=row.id, dataset_id=row.dataset_id, team_number=row.team_number
        )

    def list_saved_settings(
        self, session: Session, *, workspace_id: uuid.UUID
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
            InstructorSavedSetting(
                event_key=row.event_key, name=row.name, created_at=row.created_at
            )
            for row in session.execute(statement).all()
        )

    def list_result_runs(
        self, session: Session, *, workspace_id: uuid.UUID
    ) -> tuple[InstructorResultRun, ...]:
        """A team's result runs, by round. Empty until the results track lands.

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

    def event_exists(self, session: Session, *, dataset_id: uuid.UUID, event_key: str) -> bool:
        """Whether ``event_key`` is one of this dataset's events.

        Checked before an unlock so that a mistyped key is one sentence rather
        than a foreign-key violation, which would arrive as
        :class:`ExerciseWriteRefused` and tell the instructor nothing they can
        act on.
        """
        found = session.execute(
            sa.select(exercise_event.c.event_key).where(
                exercise_event.c.dataset_id == dataset_id,
                exercise_event.c.event_key == event_key,
            )
        ).one_or_none()
        return found is not None

    # -----------------------------------------------------------------------
    # Writes
    # -----------------------------------------------------------------------

    def set_invite_limit(
        self, session: Session, *, dataset_id: uuid.UUID, invite_limit: int
    ) -> bool:
        """Design spec §5: change how many names a ranked list may hold.

        Args:
            session: Not committed here.
            dataset_id: The dataset to change.
            invite_limit: Already checked against :data:`MIN_INVITE_LIMIT` and
                :data:`MAX_INVITE_LIMIT` by the caller, which is where the
                sentence lives. ``ck_exercise_dataset_invite_limit`` is the
                backstop, not the validation.

        Returns:
            Whether a row was changed. ``False`` means no such dataset — not
            "the value was already that", because the statement writes
            unconditionally.

        Raises:
            ValueError: if ``invite_limit`` is outside the bounds. Raised rather
                than written, so a caller that skipped its own check still
                cannot store a value the column would refuse.
        """
        if not MIN_INVITE_LIMIT <= invite_limit <= MAX_INVITE_LIMIT:
            raise ValueError(
                f"invite_limit must be between {MIN_INVITE_LIMIT} and "
                f"{MAX_INVITE_LIMIT}, not {invite_limit}"
            )
        changed = self._execute(
            session,
            sa.update(exercise_dataset)
            .where(exercise_dataset.c.id == dataset_id)
            .values(invite_limit=invite_limit)
            .returning(exercise_dataset.c.id),
            dataset_id=dataset_id,
            refusal="The invite limit could not be changed.",
        )
        return bool(changed.all())

    def unlock_results(self, session: Session, *, dataset_id: uuid.UUID, event_key: str) -> bool:
        """Design spec §9: let the teams run results for one event.

        Idempotent by the primary key rather than by a read first: a second
        press of the same button inserts nothing, changes no ``unlocked_at``,
        and is not an error. An instructor pressing "unlock" twice in a
        classroom is the expected case, not the exceptional one.

        Returns:
            ``True`` when this call is what unlocked the event, ``False`` when
            it was already unlocked. The route says the same sentence either
            way; the distinction is for the log line and the test.
        """
        inserted = self._execute(
            session,
            pg_insert(exercise_result_unlock)
            .values(dataset_id=dataset_id, event_key=event_key)
            .on_conflict_do_nothing(constraint="exercise_result_unlock_pkey")
            .returning(exercise_result_unlock.c.event_key),
            dataset_id=dataset_id,
            refusal="The results for that event could not be unlocked.",
        )
        return bool(inserted.all())

    def reset_workspace_children(self, session: Session, *, workspace_id: uuid.UUID) -> None:
        """Delete one workspace's overlay, saved settings and result runs.

        The delete half of a reset, without the seed regeneration
        ``workspace_repository.reset_team`` does — because a re-point needs the
        rows gone *before* it may update ``dataset_id`` (see the module
        docstring), and regenerating a seed mid-move would be a second thing
        happening in a statement about a dataset.

        Every statement is keyed on ``workspace_id`` and therefore cannot reach
        another team's rows: the isolation is a key, not a discipline.
        """
        for child in (exercise_profile_overlay, exercise_saved_setting, exercise_result_run):
            session.execute(sa.delete(child).where(child.c.workspace_id == workspace_id))

    def repoint_workspaces(self, session: Session, *, dataset_id: uuid.UUID) -> RepointOutcome:
        """Design spec §3: point every team at ``dataset_id``, resetting them all.

        The order the schema comment requires, in the caller's one transaction:
        each moving workspace's children are deleted, then its ``dataset_id`` is
        updated and its seed regenerated. A workspace already on the target is
        left entirely alone — it is not "moved", so it is not reset either.

        **The collision, and how it is resolved.** A team can hold two
        workspaces at once: an old one on the previous dataset and a new one on
        the target, because entry lands on the newest dataset (see
        ``workspace_repository.active_dataset``). Moving the old one would
        violate ``uq_exercise_team_workspace_dataset_team``, so it is
        **discarded** instead — deleted, with its children cascading — and the
        team's workspace on the target dataset wins. That is the direction that
        loses nothing a team is currently looking at: the row being dropped is
        the one whose cookie the team has already stopped using.

        A moved workspace keeps its id, and therefore its token and its cookie,
        because the token is derived from the id rather than the dataset. A team
        whose *stale* workspace was discarded is holding a cookie that now
        resolves to nothing and re-enters its number to get its current one — no
        work is lost, because the work was on the row that was discarded and a
        re-point resets every team in any case.

        Returns:
            How many workspaces moved and how many stale ones were discarded.

        Raises:
            ExerciseWriteRefused: if the database refuses any statement. The
                driver's exception never escapes.
        """
        target_team_numbers = {
            row.team_number
            for row in session.execute(
                sa.select(exercise_team_workspace.c.team_number).where(
                    exercise_team_workspace.c.dataset_id == dataset_id
                )
            ).all()
        }
        moving = session.execute(
            sa.select(
                exercise_team_workspace.c.id,
                exercise_team_workspace.c.team_number,
            ).where(exercise_team_workspace.c.dataset_id != dataset_id)
        ).all()

        moved = 0
        discarded = 0
        for row in moving:
            # Children first, always — see the module docstring. Both branches
            # need it: a discard relies on CASCADE, but doing it explicitly
            # keeps one order in this method rather than two.
            self.reset_workspace_children(session, workspace_id=row.id)
            if row.team_number in target_team_numbers:
                self._execute(
                    session,
                    sa.delete(exercise_team_workspace).where(
                        exercise_team_workspace.c.id == row.id
                    ),
                    dataset_id=dataset_id,
                    refusal="The teams could not be moved to that data file.",
                )
                discarded += 1
                continue
            self._execute(
                session,
                sa.update(exercise_team_workspace)
                .where(exercise_team_workspace.c.id == row.id)
                .values(
                    dataset_id=dataset_id,
                    seed=new_workspace_seed(),
                    asking_choice=None,
                    refreshed_at=None,
                ),
                dataset_id=dataset_id,
                refusal="The teams could not be moved to that data file.",
            )
            moved += 1
        _LOGGER.info("exercise workspaces re-pointed: moved=%d discarded=%d", moved, discarded)
        return RepointOutcome(moved=moved, discarded=discarded)

    # -----------------------------------------------------------------------
    # Internals
    # -----------------------------------------------------------------------

    def _execute(
        self,
        session: Session,
        statement: sa.Executable,
        *,
        dataset_id: uuid.UUID,
        refusal: str,
    ) -> sa.CursorResult[sa.Row[tuple[object, ...]]]:
        """Run one statement, letting no driver text out of this module.

        The one place an instructor write can fail, so the log line the review
        follow-up asks for is written once: the **constraint name** and the
        **dataset id**, and nothing that could be a row value.
        """
        try:
            return session.execute(statement)  # type: ignore[return-value]
        except SQLAlchemyError as exc:
            _LOGGER.warning(
                "exercise instructor write refused: constraint=%s dataset_id=%s error=%s",
                _constraint_name(exc),
                dataset_id,
                type(exc).__name__,
            )
            failure = ExerciseWriteRefused(refusal)
        # Raised outside the ``except`` block, so the new exception carries no
        # ``__context__`` — and therefore none of the driver's ``[parameters: …]``
        # (ADR-0025 D6).
        raise failure
