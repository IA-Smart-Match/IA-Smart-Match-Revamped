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
from typing import Final

import sqlalchemy as sa
from smartmatch_domain.exercise.workspace_token import new_workspace_seed
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from smartmatch_persistence.exercise.instructor_rows import (
    InstructorResultRun,
    InstructorSavedSetting,
    InstructorWorkspaceRow,
    RepointOutcome,
    TeamWorkspaceHandle,
    WorkingDataset,
)
from smartmatch_persistence.exercise.schema import (
    exercise_dataset,
    exercise_event,
    exercise_profile_overlay,
    exercise_result_run,
    exercise_result_unlock,
    exercise_saved_setting,
    exercise_team_workspace,
)
from smartmatch_persistence.exercise.settings_repository import SAVED_SETTING_LOCK_KEY
from smartmatch_persistence.exercise.workspace_repository import (
    ExerciseWorkspaceRepository,
    lock_workspace_membership,
)

__all__ = [
    "MAX_INVITE_LIMIT",
    "MAX_WORKSPACE_LIST_ROWS",
    "MIN_INVITE_LIMIT",
    "ExerciseInstructorRepository",
    "ExerciseWriteRefused",
    "InstructorResultRun",
    "InstructorSavedSetting",
    "InstructorWorkspaceRow",
    "RepointOutcome",
    "TeamWorkspaceHandle",
    "WorkingDataset",
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

#: How many team rows :meth:`ExerciseInstructorRepository.list_workspaces`
#: returns (review finding F4 on PR #184).
#:
#: ``list_datasets`` is capped and this read was not, which is the asymmetry
#: the finding names. It is not a number of Ann's and it is not a product rule:
#: six teams per data file is the product (``EXERCISE_TEAM_NUMBERS``, and the
#: table's ``CHECK (team_number BETWEEN 1 AND 6)``), so this is one screen's
#: worth of *every* data file's teams and a classroom can never approach it.
#: What it bounds is the pathological case a cap exists for — a server that has
#: run many lessons without its old data files being cleared — where an
#: unbounded read builds a list nobody scrolls out of rows nobody wants.
#:
#: A truncation cuts at a stable point because the ordering is total: upload
#: time, then data file id, then team number.
MAX_WORKSPACE_LIST_ROWS: Final[int] = 300


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

    Since 2026-09-19 the shared engine is additionally built with
    ``hide_parameters=True`` (``smartmatch_persistence.engine``), so
    ``[parameters: …]`` is suppressed repository-wide. This class is not
    redundant because of it: the engine flag governs SQLAlchemy's rendering
    only, and neither nulls ``__context__`` nor removes PostgreSQL's own
    ``DETAIL: Failing row contains (…)``. Not letting the driver's exception
    out is still the only complete answer.
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


class ExerciseInstructorRepository:
    """The instructor page's reads and writes. Commits nothing."""

    # -----------------------------------------------------------------------
    # Reads
    # -----------------------------------------------------------------------

    def list_workspaces(
        self,
        session: Session,
        *,
        dataset_id: uuid.UUID | None = None,
        limit: int = MAX_WORKSPACE_LIST_ROWS,
    ) -> tuple[InstructorWorkspaceRow, ...]:
        """Every team that exists, each with the data file it is actually on.

        **``dataset_id`` defaults to "all of them", and that default is the
        fix for a real defect.** This read used to be scoped to the *active*
        data file — the most recently uploaded row — and design spec §3 is
        explicit that uploading a file moves no team. So the instant the
        instructor uploaded, her own list of teams went empty: six teams still
        working, the screen reporting none, and the only way back a re-point she
        had no reason to think she needed.

        A team is a row in this table. The instructor's question is "what are
        my teams doing", and the honest answer names each team's file rather
        than filtering by a file chosen for it.

        Ordered by data file and then team number, so a classroom that has
        somehow split across two files reads as two groups rather than as
        interleaved duplicates of team 3. The data file's ``id`` breaks a tie on
        its upload time, which is what makes the ordering total and therefore
        the truncation below stable between two identical reads.

        **Capped** at :data:`MAX_WORKSPACE_LIST_ROWS` — review finding F4 on PR
        #184: ``list_datasets`` was bounded and this read was not. A classroom
        cannot reach the cap; a server that has run many lessons can.

        Args:
            session: Not committed here.
            dataset_id: One data file, or ``None`` for all of them.
            limit: How many rows to return. Refused if it is not positive, so a
                caller that computes one cannot turn the cap into ``LIMIT 0``.

        Raises:
            ValueError: if ``limit`` is less than one.
        """
        if limit < 1:
            raise ValueError(f"limit must be at least 1, not {limit}")
        settings = self._child_count(exercise_saved_setting).label("saved_setting_count")
        runs = self._child_count(exercise_result_run).label("result_run_count")
        statement = (
            sa.select(
                exercise_team_workspace.c.team_number,
                exercise_team_workspace.c.dataset_id,
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
            .order_by(
                exercise_dataset.c.uploaded_at,
                exercise_dataset.c.id,
                exercise_team_workspace.c.team_number,
            )
            .limit(limit)
        )
        if dataset_id is not None:
            statement = statement.where(exercise_team_workspace.c.dataset_id == dataset_id)
        return tuple(
            InstructorWorkspaceRow(
                team_number=row.team_number,
                dataset_id=row.dataset_id,
                dataset_label=row.label,
                created_at=row.created_at,
                saved_setting_count=row.saved_setting_count,
                result_run_count=row.result_run_count,
                asking_choice=row.asking_choice,
                refreshed_at=row.refreshed_at,
            )
            for row in session.execute(statement).all()
        )

    def datasets_with_workspaces(self, session: Session) -> tuple[WorkingDataset, ...]:
        """The data files teams are actually working in, oldest upload first.

        The read behind "which data file does an instructor action apply to".
        Design spec §3's separation of *uploaded* from *in use* is what makes it
        necessary: the newest file is the one a team entering now would join,
        and it is emphatically not the one the teams already in the room are on.

        Empty when nobody has entered a number yet — a real answer, and the one
        that stops an unlock from writing a row against a file no team can see.
        """
        statement = (
            sa.select(
                exercise_dataset.c.id,
                exercise_dataset.c.label,
                sa.func.count().label("team_count"),
            )
            .select_from(
                exercise_team_workspace.join(
                    exercise_dataset,
                    exercise_team_workspace.c.dataset_id == exercise_dataset.c.id,
                )
            )
            .group_by(
                exercise_dataset.c.id, exercise_dataset.c.label, exercise_dataset.c.uploaded_at
            )
            .order_by(exercise_dataset.c.uploaded_at, exercise_dataset.c.id)
        )
        return tuple(
            WorkingDataset(dataset_id=row.id, label=row.label, team_count=row.team_count)
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

    def reset_workspace_children(
        self, session: Session, *, dataset_id: uuid.UUID, workspace_id: uuid.UUID
    ) -> None:
        """Delete one workspace's overlay, saved settings and result runs.

        The delete half of a reset, without the seed regeneration
        ``workspace_repository.reset_team`` does — because a re-point needs the
        rows gone *before* it may update ``dataset_id`` (see the module
        docstring), and regenerating a seed mid-move would be a second thing
        happening in a statement about a dataset.

        Every statement is keyed on ``workspace_id`` and therefore cannot reach
        another team's rows: the isolation is a key, not a discipline.

        **Run through the scrubber**, like every other write here. These three
        deletes used a bare ``session.execute``, which quietly contradicted this
        module's own "the driver's exception never escapes" contract: a delete
        that failed — a lock timeout, a statement timeout, a connection lost
        mid-transaction — would have raised a ``DBAPIError`` whose rendering
        carries ``[parameters: …]``, out of the one module that promises it
        does not do that. The engine's ``hide_parameters=True`` (2026-09-19)
        would now blunt that particular escape, which is exactly why it is
        worth saying that it does not excuse one: see
        :class:`ExerciseWriteRefused`.

        **Takes the saved-settings key first** (review round 1). The delete of
        ``exercise_saved_setting`` below races a team's save otherwise: the save
        holds
        :data:`~smartmatch_persistence.exercise.settings_repository.SAVED_SETTING_LOCK_KEY`
        while it counts and inserts, this delete runs in between and under READ
        COMMITTED does not see the uncommitted row, and the save then commits —
        so a team keeps a setting a reset or a re-point was meant to clear.

        The order is the family's, stated on that constant: membership key, then
        saved-settings key, then row locks. :meth:`repoint_workspaces` already
        holds the membership key when it calls this, which is exactly that order;
        an advisory lock is re-entrant within a transaction, so a caller that
        already holds this key pays one round trip.

        **The acquire runs through the scrubber too**, rather than calling
        ``settings_repository.lock_saved_settings`` directly. It is a statement,
        and in a transaction PostgreSQL has already poisoned it is the *first*
        statement — so an unwrapped acquire would be the one driver exception
        that escapes this module, out of the method whose own test exists to
        prove none does. ``test_a_failing_child_delete_is_scrubbed_like_every_other_write``
        caught exactly that when the lock was added.

        Args:
            dataset_id: Not used in any statement's ``WHERE``; carried so a
                refusal can be logged against the data file it happened in.
            workspace_id: The one workspace whose rows are deleted.
        """
        self._execute(
            session,
            sa.select(sa.func.pg_advisory_xact_lock(SAVED_SETTING_LOCK_KEY)),
            dataset_id=dataset_id,
            refusal="That team's work could not be cleared.",
        )
        for child in (exercise_profile_overlay, exercise_saved_setting, exercise_result_run):
            self._execute(
                session,
                sa.delete(child).where(child.c.workspace_id == workspace_id),
                dataset_id=dataset_id,
                refusal="That team's work could not be cleared.",
            )

    def reset_team(
        self,
        session: Session,
        *,
        dataset_id: uuid.UUID,
        workspace_id: uuid.UUID,
        workspaces: ExerciseWorkspaceRepository,
    ) -> None:
        """Design spec §11's per-team reset, run through this module's scrubber.

        Delegates to ``ExerciseWorkspaceRepository.reset_team`` rather than
        reimplementing it, so "what a reset deletes" keeps one answer.

        There is no *team's* reset to keep it in step with any more, and this
        docstring used to say there was. The owner ruled on 2026-09-19 that the
        per-team reset moves behind the instructor passcode, and PR #186 removed
        ``POST /v1/exercise/workspaces/current/reset`` rather than deprecating
        it — so ``ExerciseWorkspaceRepository.reset_team`` is reached from this
        wrapper and from nowhere else in the application.

        What this wrapper adds is the refusal contract: the workspace
        repository is CE-WORKSPACE's module and raises the driver's exception as
        it finds it, which is correct there — its caller is a team route with
        its own error envelope. An instructor route reaching it through *this*
        module would otherwise be the one path out of here that could render
        ``[parameters: …]``. (Since 2026-09-19 the engine hides those values
        anyway — but the server's own ``DETAIL`` line is outside that flag's
        reach, so this wrapper still earns its place.)

        Raises:
            ExerciseWriteRefused: if the database refuses any of the four
                statements. The driver's exception never escapes.
        """
        try:
            workspaces.reset_team(session, workspace_id=workspace_id)
            return
        except SQLAlchemyError as exc:
            failure = self._failure_for(
                exc, dataset_id=dataset_id, refusal="That team's work could not be cleared."
            )
        # Outside the ``except`` block, for :meth:`_failure_for`'s reason.
        raise failure

    def repoint_workspaces(self, session: Session, *, dataset_id: uuid.UUID) -> RepointOutcome:
        """Design spec §3: point every team at ``dataset_id``, resetting them all.

        The order the schema comment requires, in the caller's one transaction:
        each moving workspace's children are deleted, then its ``dataset_id`` is
        updated and its seed regenerated. A workspace already on the target is
        left entirely alone — it is not "moved", so it is not reset either.

        **The collision, and how it is resolved.** A team can hold two
        workspaces at once: an old one on the previous dataset and a new one on
        the target. Entry no longer creates that state — owner ruling,
        2026-09-19, implemented in
        ``workspace_repository.entry_dataset_for``: a team that has a workspace
        re-enters *that* one — but rows written before the ruling can still be
        in it, and this method is what ends it. Moving the old one would
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

        **Serialised against a team entering at the same moment.** A classroom
        is exactly where that happens — the instructor presses "re-point" while
        six laptops are typing their numbers — and the window has two bad ends:

        * a team whose ``enter`` committed *after* the scan and *before* the
          update stayed on the old data file, silently, and the instructor's
          screen said every team had moved; or
        * that same insert landed on the target file for a team this method had
          already decided to move, and the update tripped
          ``uq_exercise_team_workspace_dataset_team`` — failing the **whole**
          re-point, after some teams had already been reset.

        Three locks, in the order
        :data:`~smartmatch_persistence.exercise.settings_repository.SAVED_SETTING_LOCK_KEY`
        documents for the whole family, and none of them redundant (review
        finding F2 on PR #184; the third added in review round 2 of PR #188):

        * :func:`~smartmatch_persistence.exercise.workspace_repository.lock_workspace_membership`
          is taken **first**, before any row is read. It is what closes the
          second end. ``FOR UPDATE`` alone could not: it locks the rows it
          finds, and the row that breaks a re-point is a **new** one a
          concurrent ``get_or_create_workspace`` inserts for a pair this scan
          returned nothing for. ``get_or_create_workspace`` takes the same
          advisory lock before its insert, so the two take turns; an earlier
          version of this docstring claimed the row lock covered it, which was
          not true.
        * ``FOR UPDATE`` on both reads then holds every existing row this
          statement will touch, which is what closes the first end and what
          stops a second re-point, or a reset, from interleaving with this one.

        * The **saved-settings key** is taken between them, and that position is
          the whole of review round 2's F1. It has to be held before the row
          locks, not after: ``save_setting`` holds it and then waits for a
          ``FOR KEY SHARE`` lock on the workspace row its insert references, so
          a re-point that held that row and then waited for the key would close
          a wait-for cycle and be aborted by ``deadlock_timeout``. Taking it
          first means the two wait for each other in one direction only.

        The ordering — membership key, then saved-settings key, then row locks,
        on every path that takes more than one — is what keeps the three
        deadlock-free.

        Returns:
            How many workspaces moved and how many stale ones were discarded.

        Raises:
            ExerciseWriteRefused: if the database refuses any statement. The
                driver's exception never escapes.
        """
        lock_workspace_membership(session)
        # Second, and **before either FOR UPDATE below** (review round 2, F1).
        # Round 1 put this acquire inside `reset_workspace_children`, which runs
        # after the two row-locking selects — so this method took row locks and
        # *then* waited for the key, while `save_setting` takes the key and then
        # waits for a row (its insert's FK takes FOR KEY SHARE on the workspace
        # row this method holds FOR UPDATE). That is a wait-for cycle, and
        # PostgreSQL resolves it by aborting one of them after
        # `deadlock_timeout` — an instructor's re-point failing because a team
        # pressed save. Taking the key here restores the order the constant
        # documents. `reset_workspace_children`'s own acquire stays and costs
        # one round trip: an advisory lock is re-entrant within a transaction.
        self._execute(
            session,
            sa.select(sa.func.pg_advisory_xact_lock(SAVED_SETTING_LOCK_KEY)),
            dataset_id=dataset_id,
            refusal="The teams could not be moved to that data file.",
        )
        target_team_numbers = {
            row.team_number
            for row in session.execute(
                sa.select(exercise_team_workspace.c.team_number)
                .where(exercise_team_workspace.c.dataset_id == dataset_id)
                .with_for_update()
            ).all()
        }
        moving = session.execute(
            sa.select(
                exercise_team_workspace.c.id,
                exercise_team_workspace.c.team_number,
            )
            .where(exercise_team_workspace.c.dataset_id != dataset_id)
            .with_for_update()
        ).all()

        moved = 0
        discarded = 0
        for row in moving:
            # Children first, always — see the module docstring. Both branches
            # need it: a discard relies on CASCADE, but doing it explicitly
            # keeps one order in this method rather than two.
            self.reset_workspace_children(session, dataset_id=dataset_id, workspace_id=row.id)
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

    def _failure_for(
        self, error: SQLAlchemyError, *, dataset_id: uuid.UUID, refusal: str
    ) -> ExerciseWriteRefused:
        """Log a refused write and build the exception to raise for it.

        **Builds, and deliberately does not raise.** Every caller raises the
        returned value *after* its own ``except`` block has ended, which is the
        whole of what makes ``__context__`` ``None`` — see
        :class:`ExerciseWriteRefused`.

        A context manager was tried here and reverted: when a ``@contextmanager``
        is resumed through ``gen.throw()``, the driver's exception is still the
        one being handled inside the generator frame, so a ``raise`` anywhere in
        it chains — and the chained ``DBAPIError`` renders as
        ``[parameters: …]``, every value of every row (ADR-0025 D6). The
        existing ``__context__ is None`` test caught it; four duplicated lines
        at two call sites are cheaper than the property being conditional on an
        interpreter detail.

        What is logged is the review follow-up: the **constraint name** and the
        **dataset id**, and nothing that could be a row value. A constraint name
        is schema; a dataset id names a file, not a row in it.
        """
        _LOGGER.warning(
            "exercise instructor write refused: constraint=%s dataset_id=%s error=%s",
            _constraint_name(error),
            dataset_id,
            type(error).__name__,
        )
        return ExerciseWriteRefused(refusal)

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
        # Raised outside the ``except`` block, so the new exception carries no
        # ``__context__``. ``raise ... from None`` would only set
        # ``__suppress_context__``, leaving the original — and its parameters —
        # reachable on the object.
        raise failure
