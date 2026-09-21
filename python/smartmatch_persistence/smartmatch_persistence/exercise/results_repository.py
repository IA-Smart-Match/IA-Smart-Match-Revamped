"""Design spec §9–§13: the results lock, the one-run rule, the choice, the refresh.

Four questions, one table family, one advisory key:

* **Is this event unlocked?** ``exercise_result_unlock`` has a row for
  ``(dataset, event)``, or it does not. Absence is "locked" (design spec §9).
* **What did this team run?** ``exercise_result_run``, at most one row per
  ``(workspace, event)`` — the one-run rule, which is
  ``uq_exercise_result_run_workspace_event`` rather than a count in code.
* **How did this team choose to ask?** ``exercise_team_workspace.asking_choice``,
  set once (design spec §12).
* **What did the refresh change?** ``exercise_profile_overlay`` rows for this
  workspace, and ``refreshed_at`` on its workspace row (design spec §13).

ADR-0025 D2 in one sentence
===========================
Every statement here names a table beginning ``exercise_``. No ``tenant_id``, no
``owning_unit_id``, no join to ``user_account``, and no principal.
``tests/unit/test_exercise_persistence_tables.py`` walks this package and
refuses a table name without the prefix.

ADR-0025 D6 — the withheld column
=================================
Design spec §13's refresh copies a card **from** the withheld column, so this is
the one module in the exercise whose *purpose* touches it. It still does not read
it: :meth:`ExerciseResultsRepository.apply_refresh` calls
``results_cards.copied_cards``, which calls
``dataset_repository.load_simulation_profiles`` — still the single reader in this
package — and the values it hands back never leave this method: they are written
straight into ``exercise_profile_overlay.card_interests``, where they are an
ordinary card that the team was given and every later reader treats as one.

What the *same* copied card says about a career goal is a separate, **public**
question and follows a named policy — ``asking.COPIED_CARD_CAREER_GOAL``,
PLACEHOLDER (OQ-CE-13). See :meth:`ExerciseResultsRepository.apply_refresh`.

No caller of this module ever holds a withheld value. The router side passes
**profile numbers and a share** and gets **counts** back; there is no parameter
and no return field on any method here with a place to put an interest term.
Every write goes through the scrubber below, so a refused write carries no
``[parameters: …]``.

Transaction boundaries belong to the caller
===========================================
Every method takes a :class:`~sqlalchemy.orm.Session` and **commits nothing**,
like every other repository in this package. ``get_exercise_session`` rolls back
unconditionally, so a route that writes and forgets to commit stores nothing.

The seed, read here and nowhere else
====================================
``workspace_repository.ExerciseWorkspace`` deliberately carries no ``seed``, and
its docstring says a later track that needs it "adds a read that names it, at
which point the exception is visible at the call site". This is that track and
:meth:`ExerciseResultsRepository.team_state` is that read. The value is the
simulated-results rule's only per-team input; it reaches the router as an
``int`` on a value object that no response model is built from.
"""

from __future__ import annotations

import hashlib
import logging
import uuid
from collections.abc import Iterable, Mapping, Sequence
from datetime import datetime
from functools import partial
from typing import Final

import sqlalchemy as sa
from smartmatch_domain.exercise.asking import COPIED_CARD_CAREER_GOAL, CopiedCardCareerGoal
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from smartmatch_persistence.exercise.results_cards import copied_cards
from smartmatch_persistence.exercise.results_rows import (
    RefreshCandidate,
    RefreshCounts,
    ResultPanel,
    StoredResultRun,
    TeamResultsState,
)
from smartmatch_persistence.exercise.schema import (
    exercise_profile_overlay,
    exercise_result_run,
    exercise_result_unlock,
    exercise_team_workspace,
)

__all__ = [
    "ALREADY_RUN_SENTENCE",
    "RESULT_RUN_LOCK_KEY",
    "AlreadyRunError",
    "ExerciseResultsRepository",
    "ExerciseResultsWriteRefused",
    "RefreshCandidate",
    "RefreshCounts",
    "ResultPanel",
    "StoredResultRun",
    "TeamResultsState",
    "lock_result_runs",
]

_LOGGER = logging.getLogger(__name__)

#: Design spec §9, word for word: *"a second run hits the UNIQUE constraint and
#: is refused with 'This team has already run results for this event.'"* Stored
#: as a constant because the sentence is the specified behaviour and a test
#: compares it byte for byte — a handler that reworded it would be changing the
#: spec in a string literal.
ALREADY_RUN_SENTENCE: Final[str] = "This team has already run results for this event."

#: The advisory-lock key every statement that changes a team's **results state**
#: takes: a result run, an asking choice, a refresh, and the deletes that clear
#: them.
#:
#: **Derived, not chosen**, exactly as
#: :data:`~smartmatch_persistence.exercise.workspace_repository.WORKSPACE_MEMBERSHIP_LOCK_KEY`
#: and
#: :data:`~smartmatch_persistence.exercise.settings_repository.SAVED_SETTING_LOCK_KEY`
#: are: the first eight bytes of the SHA-256 of this table's own name, read as
#: PostgreSQL's signed ``bigint``. Deriving it from ``exercise_result_run``
#: rather than reusing the saved-settings key is the point — two subsystems on
#: one key serialise each other for no reason, and a key nobody can trace back
#: to a name is a number nobody can check.
#:
#: **Why a lock at all, when the one-run rule is a UNIQUE constraint.** The
#: constraint is enough for two concurrent runs and this module relies on it for
#: exactly that. The lock is for the *other* three writers, none of which the
#: constraint covers:
#:
#: * ``reset_team`` and ``reset_workspace_children`` DELETE this team's result
#:   runs and overlay rows. Without a shared key a run committing in the window
#:   between the delete and the reset's commit survives a reset that was meant to
#:   clear it — silently, under READ COMMITTED, which is review round 1's item 9
#:   with ``exercise_result_run`` in place of ``exercise_saved_setting``.
#: * ``repoint_workspaces`` deletes the same rows across every team.
#: * The refresh claims ``refreshed_at`` and then writes overlay rows; a reset
#:   interleaved between the two would clear an overlay whose ``refreshed_at``
#:   says it may never be written again.
#:
#: **Where it sits in the family's order.** See
#: :data:`~smartmatch_persistence.exercise.settings_repository.SAVED_SETTING_LOCK_KEY`,
#: whose docstring is the **single** per-path walk for all four repositories.
#: The order, in one line::
#:
#:     WORKSPACE_MEMBERSHIP_LOCK_KEY -> SAVED_SETTING_LOCK_KEY
#:         -> RESULT_RUN_LOCK_KEY -> row locks
#:
#: This key is third because the two paths that take more than one of them —
#: ``repoint_workspaces`` and ``reset_team`` — already take the earlier two, and
#: no path here takes either of the earlier keys at all. A cycle needs two paths
#: acquiring in opposite orders, and there is no second order.
#:
#: **Coarse, and deliberately**, for the saved-settings key's reason: one key
#: serialises results writes across every team rather than per workspace. Six
#: teams pressing "run results" in the same minute is not contention, the work
#: inside the key is a handful of short statements, and a per-workspace key
#: would be a second thing to get right for no measured gain.
RESULT_RUN_LOCK_KEY: Final[int] = int.from_bytes(
    hashlib.sha256(b"exercise_result_run").digest()[:8], "big", signed=True
)


def lock_result_runs(session: Session) -> None:
    """Take :data:`RESULT_RUN_LOCK_KEY` for the caller's transaction.

    ``pg_advisory_xact_lock`` rather than ``pg_advisory_lock``, for
    ``lock_workspace_membership``'s reason: the transaction form is released
    whichever way the transaction ends, so a caller that raises cannot wedge the
    classroom until the connection is recycled. Re-entrant within a transaction,
    which is what lets a path that already holds it call a method that takes it
    again for one round trip.
    """
    session.execute(sa.select(sa.func.pg_advisory_xact_lock(RESULT_RUN_LOCK_KEY)))


class ExerciseResultsWriteRefused(Exception):
    """The database refused a results write, with no driver text attached.

    ADR-0025 D6, the same door ``settings_repository.ExerciseSettingsWriteRefused``
    holds shut: SQLAlchemy renders a ``DBAPIError`` as the statement **plus**
    ``[parameters: …]``, and on this module's paths those parameters can be
    profile numbers and, on the refresh's card copy, interest terms out of the
    withheld column.

    What is logged instead is the **constraint name** and the **dataset id**:
    what an operator needs to act, and nothing that could be a row value. Raised
    from *outside* the ``except`` block that built it, so ``__context__`` is
    ``None`` rather than merely suppressed.
    """


class AlreadyRunError(Exception):
    """A second run for one ``(workspace, event)``. Not a database failure.

    Separate from :class:`ExerciseResultsWriteRefused` because it is a fact
    about what the team asked for rather than about what the database did, and
    the API answers the two with different statuses. It carries
    :data:`ALREADY_RUN_SENTENCE`, which design spec §9 writes out.
    """

    def __init__(self, message: str = ALREADY_RUN_SENTENCE) -> None:
        super().__init__(message)


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


def _ints(value: object) -> tuple[int, ...]:
    """A PostgreSQL integer array as a tuple. ``NULL`` reads as empty."""
    return tuple(int(item) for item in value) if isinstance(value, list) else ()


def _panel_from_json(value: object) -> ResultPanel:
    """``exercise_result_run.email_everyone`` as a :class:`ResultPanel`.

    Defensive about the stored shape rather than trusting it: the column is
    JSONB, so a row written by an older version of this module is data the
    current one is reading, and a missing key is read as "nobody" rather than as
    a crash on a screen.
    """
    stored = value if isinstance(value, Mapping) else {}
    return ResultPanel(
        invited_profile_nos=_ints(stored.get("invited")),
        signed_up_profile_nos=_ints(stored.get("signed_up")),
        attended_profile_nos=_ints(stored.get("attended")),
    )


def _panel_as_json(panel: ResultPanel) -> dict[str, list[int]]:
    """A :class:`ResultPanel` as the JSONB column stores it."""
    return {
        "invited": list(panel.invited_profile_nos),
        "signed_up": list(panel.signed_up_profile_nos),
        "attended": list(panel.attended_profile_nos),
    }


class ExerciseResultsRepository:
    """Design spec §9–§13's reads and writes. Commits nothing."""

    # -----------------------------------------------------------------------
    # Reads
    # -----------------------------------------------------------------------

    def results_unlocked(self, session: Session, *, dataset_id: uuid.UUID, event_key: str) -> bool:
        """Design spec §9's lock: whether the instructor has unlocked this event.

        The absence of a row is "locked", which is why this is an existence
        question and not a boolean column: a boolean would need a row per event
        written at ingest to mean anything, and a missing row would then be a
        third state nobody defined (``schema.py`` says the same).
        """
        found = session.execute(
            sa.select(exercise_result_unlock.c.event_key).where(
                exercise_result_unlock.c.dataset_id == dataset_id,
                exercise_result_unlock.c.event_key == event_key,
            )
        ).one_or_none()
        return found is not None

    def team_state(self, session: Session, *, workspace_id: uuid.UUID) -> TeamResultsState | None:
        """The seed, the asking choice and the refresh timestamp for one team.

        **The one read in the exercise that names ``seed``.** See this module's
        docstring: ``ExerciseWorkspace`` leaves it off so that reaching it is an
        explicit act, and this is the act.

        ``None`` for a workspace id that names no row, which a caller holding a
        resolved cookie cannot produce; it is still answered rather than raised,
        because a repository reporting "no row" is not a repository deciding what
        HTTP that is.
        """
        row = session.execute(
            sa.select(
                exercise_team_workspace.c.seed,
                exercise_team_workspace.c.asking_choice,
                exercise_team_workspace.c.refreshed_at,
            ).where(exercise_team_workspace.c.id == workspace_id)
        ).one_or_none()
        if row is None:
            return None
        return TeamResultsState(
            seed=int(row.seed),
            asking_choice=row.asking_choice,
            refreshed_at=row.refreshed_at,
        )

    def get_run(
        self, session: Session, *, workspace_id: uuid.UUID, event_key: str
    ) -> StoredResultRun | None:
        """This team's stored run for one event, or ``None``.

        Scoped to ``workspace_id`` in the statement rather than filtered
        afterwards: another team's run for the same event is not merely hidden,
        it is not selected.
        """
        return self._one(
            session,
            exercise_result_run.c.workspace_id == workspace_id,
            exercise_result_run.c.event_key == event_key,
        )

    def get_run_for_round(
        self, session: Session, *, workspace_id: uuid.UUID, round_number: int
    ) -> StoredResultRun | None:
        """This team's stored run for round one or round two, or ``None``.

        Design spec §10: *"for round two, the team's stored round-one result"*.
        Addressed by round rather than by event key because the round-two screen
        knows which round it is and does not know what the first round's event
        was called — and the round is on the row.
        """
        return self._one(
            session,
            exercise_result_run.c.workspace_id == workspace_id,
            exercise_result_run.c.round == round_number,
        )

    def workspaces_awaiting_refresh(self, session: Session) -> tuple[RefreshCandidate, ...]:
        """Every workspace design spec §13's "refresh all" applies to.

        *"every workspace that has chosen and not yet refreshed"*, as the
        statement's own predicate. A team that has not chosen has no share to
        apply, and a team that has refreshed has had its one refresh; neither is
        an error and neither is returned.

        Ordered by dataset and then team number so that "refresh all" visits the
        classroom in the order a person reads it, and so two runs of the same
        instruction touch the same rows in the same order.
        """
        rows = session.execute(
            sa.select(
                exercise_team_workspace.c.id,
                exercise_team_workspace.c.dataset_id,
                exercise_team_workspace.c.team_number,
                exercise_team_workspace.c.asking_choice,
                exercise_team_workspace.c.seed,
            )
            .where(
                exercise_team_workspace.c.asking_choice.is_not(None),
                exercise_team_workspace.c.refreshed_at.is_(None),
            )
            .order_by(
                exercise_team_workspace.c.dataset_id,
                exercise_team_workspace.c.team_number,
            )
        ).all()
        return tuple(
            RefreshCandidate(
                workspace_id=row.id,
                dataset_id=row.dataset_id,
                team_number=row.team_number,
                asking_choice=str(row.asking_choice),
                seed=int(row.seed),
            )
            for row in rows
        )

    # -----------------------------------------------------------------------
    # Writes
    # -----------------------------------------------------------------------

    def record_run(
        self,
        session: Session,
        *,
        dataset_id: uuid.UUID,
        workspace_id: uuid.UUID,
        event_key: str,
        round_number: int,
        setting_name: str | None,
        team: ResultPanel,
        email_everyone: ResultPanel,
        seats_empty: int,
    ) -> StoredResultRun:
        """Store one run, or refuse a second with design spec §9's sentence.

        The order of the three statements is the rule, not a style:

        1. :func:`lock_result_runs`, **first**, so a reset or a re-point cannot
           delete this team's runs between the check below and the insert. The
           one-run rule itself does not need the lock — that is the UNIQUE
           constraint's job — but the *clears* do; see
           :data:`RESULT_RUN_LOCK_KEY`.
        2. Read this team's run for this event, so the ordinary second press of
           a button is answered with a sentence rather than with a constraint
           violation nobody planned for.
        3. A plain ``INSERT``. It is still the constraint that decides: two
           requests that both passed step 2 are serialised by the key, the
           second one's insert conflicts, and
           :meth:`_refused_or_already_run` turns that one constraint name into
           the same sentence. The check is the courtesy; the constraint is the
           rule.

        Args:
            session: Not committed here. The lock is released by the caller's
                commit or rollback, so the check and the insert must be in one
                transaction — which they are, because they are in one method.
            dataset_id: The workspace's dataset. Written to the row because
                ``exercise_result_run``'s foreign keys are composite; a mismatch
                is unrepresentable rather than something to check.
            workspace_id: The team's workspace.
            event_key: The event the run is for.
            round_number: 1 or 2. Derived by the caller from the event's place
                among the data file's exercise events, never invented here.
            setting_name: The saved weighting the list came from, or ``None``.
            team: The team's own list through the rule.
            email_everyone: Design spec §10's second panel.
            seats_empty: ``60 - 8 - attended``, computed by the domain's
                :func:`~smartmatch_domain.exercise.simulation.seats_empty`.

        Returns:
            The stored run, read back so the caller reports what is in the table
            rather than what it sent.

        Raises:
            AlreadyRunError: For a second run on one ``(workspace, event)``.
            ExerciseResultsWriteRefused: If the database refuses the write for
                any other reason.
        """
        lock_result_runs(session)
        existing = self.get_run(session, workspace_id=workspace_id, event_key=event_key)
        if existing is not None:
            raise AlreadyRunError
        self._execute(
            session,
            sa.insert(exercise_result_run).values(
                id=uuid.uuid4(),
                workspace_id=workspace_id,
                dataset_id=dataset_id,
                event_key=event_key,
                round=round_number,
                setting_name=setting_name,
                invited_profile_nos=list(team.invited_profile_nos),
                signed_up_profile_nos=list(team.signed_up_profile_nos),
                attended_profile_nos=list(team.attended_profile_nos),
                email_everyone=_panel_as_json(email_everyone),
                seats_empty=seats_empty,
            ),
            dataset_id=dataset_id,
            refusal="Your results could not be stored.",
        )
        stored = self.get_run(session, workspace_id=workspace_id, event_key=event_key)
        if stored is None:  # pragma: no cover - requires a concurrent delete
            raise ExerciseResultsWriteRefused("Your results could not be stored.")
        return stored

    def choose_asking(self, session: Session, *, workspace_id: uuid.UUID, choice: str) -> bool:
        """Store design spec §12's asking choice, once. ``True`` when it was set.

        ``WHERE asking_choice IS NULL`` is the once-only rule, written as the
        statement's own predicate rather than as a read followed by a write: two
        requests arriving together would both read ``NULL`` and the second would
        quietly overwrite the first, changing which share the refresh applies
        after a team believed it had decided.

        ``False`` — rather than an exception — for a team that has already
        chosen, because "there is already a choice" is a fact about the row, and
        which HTTP status that is belongs to the route.

        The lock is taken first for :data:`RESULT_RUN_LOCK_KEY`'s reason: this
        ``UPDATE`` touches the same workspace row a reset updates, and a reset
        holds the earlier keys and this one before it gets there.
        """
        lock_result_runs(session)
        updated = self._execute(
            session,
            sa.update(exercise_team_workspace)
            .where(
                exercise_team_workspace.c.id == workspace_id,
                exercise_team_workspace.c.asking_choice.is_(None),
            )
            .values(asking_choice=choice)
            .returning(exercise_team_workspace.c.id),
            dataset_id=None,
            refusal="Your team's choice could not be stored.",
        )
        return bool(updated.all())

    def apply_refresh(
        self,
        session: Session,
        *,
        dataset_id: uuid.UUID,
        workspace_id: uuid.UUID,
        added_topics: Sequence[str],
        topic_gainers: Iterable[int],
        card_profile_nos: Iterable[int],
        non_responding_profile_nos: Iterable[int],
        now: datetime,
        career_goal_policy: CopiedCardCareerGoal = COPIED_CARD_CAREER_GOAL,
    ) -> RefreshCounts | None:
        """Design spec §13's refresh, for this team's overlay and nothing else.

        ``None`` — rather than an exception — when this team may not refresh:
        it has not chosen, or it has already refreshed. Which HTTP status that
        is belongs to the route, and the two cases are one answer here because
        the route asks :meth:`team_state` first and can tell them apart.

        **The claim comes before the work.** ``refreshed_at`` is written first,
        under ``WHERE refreshed_at IS NULL AND asking_choice IS NOT NULL``, so
        two refreshes arriving together cannot both write an overlay: the second
        updates no row, gets ``None``, and touches nothing. Doing the overlay
        first and the claim afterwards would apply one team's share twice.

        **The card copy, and the whole of ADR-0025 D6 on this path.** The cards
        come from ``load_simulation_profiles`` — the one reader of
        ``hidden_true_interests`` in this package — and go straight into
        ``exercise_profile_overlay.card_interests``. They are not returned, not
        logged, not held in a value this method hands back, and not visible to
        the caller, which passed profile *numbers* and gets *counts*. Once
        written they are an ordinary card the team was given, which is what
        design spec §13 describes and what every later reader treats them as.

        **``card_career_goal`` follows a named policy, not this method.** The
        owner ruled on 2026-09-21 that a copied card carries the base row's
        ``career_goal``, ``NULL`` only when the base has none;
        ``asking.copied_card_career_goal`` is where that is written and
        ``career_goal_policy`` is how it is switched. The base goal is a
        **public** column and is read off rows this method has already loaded for
        the card copy, so nothing new queries anything and
        ``load_simulation_profiles`` stays the one reader of the withheld column.

        Every statement is keyed on ``workspace_id``, so no other team's rows are
        reachable from here — the isolation is a key, not a discipline.

        Args:
            session: Not committed here.
            dataset_id: The workspace's dataset, written on every overlay row so
                the composite foreign keys hold.
            workspace_id: The team's workspace.
            added_topics: The round-one event's topics, which the round-one
                attended set gains.
            topic_gainers: Those attended profile numbers.
            card_profile_nos: The share of invited profiles with no card that
                complete one, chosen by the caller through
                ``smartmatch_domain.exercise.asking.select_share``.
            non_responding_profile_nos: Under ``required`` only, the further
                share that stops answering.
            now: The refresh timestamp, passed rather than read from the clock so
                that a caller refreshing six teams stamps them identically.
            career_goal_policy: PLACEHOLDER (OQ-CE-13) — which reading the copied
                card's career goal takes. Defaults to
                ``asking.COPIED_CARD_CAREER_GOAL``, so a caller never states it
                and Ann's answer is one constant in the domain.

        Returns:
            :class:`RefreshCounts`, or ``None`` when the team may not refresh.

        Raises:
            ExerciseResultsWriteRefused: If the database refuses a write.
        """
        lock_result_runs(session)
        claimed = self._execute(
            session,
            sa.update(exercise_team_workspace)
            .where(
                exercise_team_workspace.c.id == workspace_id,
                exercise_team_workspace.c.refreshed_at.is_(None),
                exercise_team_workspace.c.asking_choice.is_not(None),
            )
            .values(refreshed_at=now)
            .returning(exercise_team_workspace.c.id),
            dataset_id=dataset_id,
            refusal="That refresh could not be applied.",
        )
        if not claimed.all():
            return None

        gainers = sorted(set(topic_gainers))
        wants_card = sorted(set(card_profile_nos))
        silent = sorted(set(non_responding_profile_nos))

        write = partial(
            self._overlay_upsert, session, dataset_id=dataset_id, workspace_id=workspace_id
        )
        write(column="added_event_topics", values={no: list(added_topics) for no in gainers})
        # The read sits here, between the first and second write, exactly where
        # it sat before: it takes no lock, but the statement log is a pinned
        # property of this method and moving a statement is not a tidy-up.
        cards, goals = copied_cards(
            session,
            dataset_id=dataset_id,
            profile_nos=wants_card,
            career_goal_policy=career_goal_policy,
        )
        # The remaining three narrow upserts, in the order the sequence test
        # pins. Pairs rather than three more call blocks, so that a fifth column
        # is a pair and not another twelve lines.
        for column, values in (
            ("card_interests", cards),
            ("card_career_goal", goals),
            ("non_responding", dict.fromkeys(silent, True)),
        ):
            write(column=column, values=values)
        return RefreshCounts(
            cards_completed=len(cards),
            non_responding=len(silent),
            topics_added=len(gainers),
        )

    # -----------------------------------------------------------------------
    # Internals
    # -----------------------------------------------------------------------

    def _overlay_upsert(
        self,
        session: Session,
        *,
        dataset_id: uuid.UUID,
        workspace_id: uuid.UUID,
        column: str,
        values: Mapping[int, object],
    ) -> None:
        """Write one overlay column for a set of profiles, creating rows as needed.

        One statement per column rather than one per profile, and **four narrow
        upserts rather than one wide one**: the groups design spec §13 names
        overlap — a profile that attended round one may also be given a card, and
        a card carries both its interests and its career goal — and a single
        upsert would have to decide what to write for a column this group says
        nothing about. ``DO UPDATE SET <column> = EXCLUDED.<column>`` touches
        only the column this call is for, so the other three survive whatever
        order the four run in.

        A call with no values writes nothing at all, which is how a policy that
        yields no career goal leaves the statement sequence as it was.
        """
        if not values:
            return
        statement = pg_insert(exercise_profile_overlay)
        self._execute(
            session,
            statement.on_conflict_do_update(
                constraint="exercise_profile_overlay_pkey",
                set_={column: statement.excluded[column]},
            ),
            dataset_id=dataset_id,
            refusal="That refresh could not be applied.",
            parameters=[
                {
                    "workspace_id": workspace_id,
                    "dataset_id": dataset_id,
                    "profile_no": profile_no,
                    column: value,
                }
                for profile_no, value in sorted(values.items())
            ],
        )

    def _one(self, session: Session, *conditions: sa.ColumnElement[bool]) -> StoredResultRun | None:
        """The one read shape in this class, with every column named.

        ``sa.select(table)`` would carry ``id``, ``workspace_id`` and
        ``dataset_id`` into whatever a caller built from the row. Naming the
        columns is what makes that impossible rather than unlikely.
        """
        row = session.execute(
            sa.select(
                exercise_result_run.c.event_key,
                exercise_result_run.c.round,
                exercise_result_run.c.setting_name,
                exercise_result_run.c.invited_profile_nos,
                exercise_result_run.c.signed_up_profile_nos,
                exercise_result_run.c.attended_profile_nos,
                exercise_result_run.c.email_everyone,
                exercise_result_run.c.seats_empty,
                exercise_result_run.c.created_at,
            ).where(*conditions)
        ).one_or_none()
        if row is None:
            return None
        return StoredResultRun(
            event_key=row.event_key,
            round=int(row.round),
            setting_name=row.setting_name,
            team=ResultPanel(
                invited_profile_nos=_ints(row.invited_profile_nos),
                signed_up_profile_nos=_ints(row.signed_up_profile_nos),
                attended_profile_nos=_ints(row.attended_profile_nos),
            ),
            email_everyone=_panel_from_json(row.email_everyone),
            seats_empty=int(row.seats_empty),
            created_at=row.created_at,
        )

    def _failure_for(
        self, error: SQLAlchemyError, *, dataset_id: uuid.UUID | None, refusal: str
    ) -> Exception:
        """Log a refused write and build the exception to raise for it.

        **Builds, and deliberately does not raise**, so that the caller can raise
        it after its own ``except`` block has ended — which is the whole of what
        makes ``__context__`` ``None``. ``raise … from None`` would only set
        ``__suppress_context__``, leaving the driver error and its
        ``[parameters: …]`` reachable on the object (ADR-0025 D6).

        The one-run rule gets its own exception here rather than at the call
        site: ``uq_exercise_result_run_workspace_event`` is design spec §9's
        rule expressed as a constraint, so the constraint name is exactly where
        that sentence belongs.

        The line carries the constraint name and the dataset id and nothing that
        could be a row value: a constraint name is schema, and a dataset id names
        a file rather than a row in it.
        """
        constraint = _constraint_name(error)
        _LOGGER.warning(
            "exercise results write refused: constraint=%s dataset_id=%s error=%s",
            constraint,
            dataset_id,
            type(error).__name__,
        )
        if constraint == "uq_exercise_result_run_workspace_event":
            return AlreadyRunError()
        return ExerciseResultsWriteRefused(refusal)

    def _execute(
        self,
        session: Session,
        statement: sa.Executable,
        *,
        dataset_id: uuid.UUID | None,
        refusal: str,
        parameters: Sequence[Mapping[str, object]] | None = None,
    ) -> sa.CursorResult[sa.Row[tuple[object, ...]]]:
        """Run one statement, letting no driver text out of this module."""
        try:
            if parameters is None:
                return session.execute(statement)  # type: ignore[return-value]
            return session.execute(statement, list(parameters))  # type: ignore[return-value]
        except SQLAlchemyError as exc:
            failure = self._failure_for(exc, dataset_id=dataset_id, refusal=refusal)
        raise failure
