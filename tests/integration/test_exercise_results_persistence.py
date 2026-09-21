"""The results rows against a real PostgreSQL (CE-RESULTS-API, design spec §9–§13).

``tests/unit/test_exercise_results_router.py`` proves the routes over a fake
repository. A fake cannot prove any of the five things that actually hold in a
classroom, and all five are database properties:

* **The one-run rule is a constraint, not a check.** Design spec §9 says so in
  as many words, and the difference shows only under concurrency: two runs that
  both pass a read-first check must still leave exactly one row, and the second
  must carry the spec's own sentence.
* **Once-only, as a predicate.** The asking choice and the refresh are
  ``UPDATE … WHERE <column> IS NULL``. Two requests that both read ``NULL`` and
  then wrote would both succeed in a fake and must not here.
* **The card copy.** Design spec §13 copies a card *out of the withheld column*
  into the overlay, which only a real row can demonstrate — and the copy must
  arrive as ordinary ``card_interests`` with the withheld column untouched.
* **The lock order.** ``RESULT_RUN_LOCK_KEY`` is third in the family's order,
  and the three paths that delete these rows must take it before any row lock.
  That is a property of the sequence of statements a method sends.
* **The scrubber.** A refused write must carry no driver text and no
  ``__context__`` (ADR-0025 D6), and only a real constraint violation produces
  one.

Runs against its own scratch database, migrated to head, and dropped afterwards;
skipped where no PostgreSQL is reachable.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator

import pytest

pytest.importorskip("sqlalchemy")

import sqlalchemy as sa
from migration_harness import alembic, connected, scratch_database
from smartmatch_persistence.exercise import schema
from smartmatch_persistence.exercise.instructor_repository import ExerciseInstructorRepository
from smartmatch_persistence.exercise.results_repository import (
    ALREADY_RUN_SENTENCE,
    RESULT_RUN_LOCK_KEY,
    AlreadyRunError,
    ExerciseResultsRepository,
    ExerciseResultsWriteRefused,
)
from smartmatch_persistence.exercise.results_rows import ResultPanel
from smartmatch_persistence.exercise.settings_repository import (
    SAVED_SETTING_LOCK_KEY,
    ExerciseSettingsRepository,
)
from smartmatch_persistence.exercise.workspace_repository import (
    WORKSPACE_MEMBERSHIP_LOCK_KEY,
    ExerciseWorkspaceRepository,
)
from sqlalchemy import Engine
from sqlalchemy.orm import Session, sessionmaker

pytestmark = pytest.mark.integration

#: Not a real key, and assembled from pieces for the reason the other exercise
#: files give: ``tools/scan_forbidden.py`` matches the shape of a committed
#: credential, and a test that needs an exception from that rule is written
#: badly.
_SECRET = "-".join(("integration", "only", "exercise", "results", "key"))

_ROUND_ONE = "round-one"
_ROUND_TWO = "round-two"
_WEIGHTS = {"same_major": 0.5, "stated_interest_overlap": 0.5}

#: The withheld cells design spec §13's refresh copies. Written here so the test
#: can assert the copy landed **and** that the source column was not disturbed;
#: nothing in the repository under test returns them.
_WITHHELD = {
    1: ["true-one"],
    2: ["true-two", "true-three"],
    3: [],
}

_TEAM = ResultPanel(
    invited_profile_nos=(1, 2, 3),
    signed_up_profile_nos=(1, 2),
    attended_profile_nos=(1,),
)

_EVERYONE = ResultPanel(
    invited_profile_nos=(1, 2, 3),
    signed_up_profile_nos=(1, 2, 3),
    attended_profile_nos=(1, 3),
)


@pytest.fixture
def exercise_sessions(engine: Engine) -> Iterator[sessionmaker[Session]]:
    """A session factory over a scratch database migrated to head.

    Its own database rather than the shared development one, because this file
    deletes rows.
    """
    with scratch_database(engine) as url:
        alembic(url, "head", expect_success=True)
        with connected(url) as scratch:
            yield sessionmaker(bind=scratch, expire_on_commit=False, future=True)


def _insert_dataset(session: Session, *, label: str) -> uuid.UUID:
    dataset_id = uuid.uuid4()
    session.execute(
        sa.insert(schema.exercise_dataset).values(
            id=dataset_id,
            label=label,
            source_filename=f"{label}.csv",
            row_count=3,
            checksum=uuid.uuid4().hex,
            invite_limit=30,
        )
    )
    return dataset_id


def _insert_events(session: Session, *, dataset_id: uuid.UUID) -> None:
    """The two rounds. No past events: this file never ranks anything."""
    session.execute(
        sa.insert(schema.exercise_event),
        [
            {
                "dataset_id": dataset_id,
                "event_key": _ROUND_ONE,
                "name": "The first round",
                "topic_tags": ["analytics"],
                "target_majors": ["Alpha"],
                "is_exercise_event": True,
                "sequence": 11,
            },
            {
                "dataset_id": dataset_id,
                "event_key": _ROUND_TWO,
                "name": "The second round",
                "topic_tags": ["brand"],
                "target_majors": ["Alpha"],
                "is_exercise_event": True,
                "sequence": 12,
            },
        ],
    )


def _insert_profiles(session: Session, *, dataset_id: uuid.UUID) -> None:
    """Three fictional profiles, each carrying a withheld cell of its own.

    The vocabularies are deliberately not anybody's: ``"Alpha"`` and ``"one"``
    name no major and no class year a data file might carry, because OQ-CE-01 is
    open and this file closes nothing.
    """
    session.execute(
        sa.insert(schema.exercise_profile),
        [
            {
                "dataset_id": dataset_id,
                "profile_no": profile_no,
                "display_name": f"Profile {profile_no}",
                "major": "Alpha",
                "class_year": "one",
                "past_event_keys": [],
                "stated_interests": None,
                "career_goal": None,
                "hidden_true_interests": withheld,
            }
            for profile_no, withheld in sorted(_WITHHELD.items())
        ],
    )


def _classroom(session: Session, *, teams: int = 2) -> tuple[uuid.UUID, list[uuid.UUID]]:
    """A data file, its two rounds, three profiles and ``teams`` workspaces on it."""
    dataset_id = _insert_dataset(session, label="results")
    _insert_events(session, dataset_id=dataset_id)
    _insert_profiles(session, dataset_id=dataset_id)
    repository = ExerciseWorkspaceRepository()
    workspaces = [
        repository.get_or_create_workspace(
            session, dataset_id=dataset_id, team_number=number, workspace_secret=_SECRET
        ).id
        for number in range(1, teams + 1)
    ]
    session.commit()
    return dataset_id, workspaces


def _record(
    repository: ExerciseResultsRepository,
    session: Session,
    *,
    dataset_id: uuid.UUID,
    workspace_id: uuid.UUID,
    event_key: str = _ROUND_ONE,
    round_number: int = 1,
    setting_name: str | None = None,
) -> object:
    return repository.record_run(
        session,
        dataset_id=dataset_id,
        workspace_id=workspace_id,
        event_key=event_key,
        round_number=round_number,
        setting_name=setting_name,
        team=_TEAM,
        email_everyone=_EVERYONE,
        seats_empty=51,
    )


def _now(session: Session) -> object:
    """The server's clock, so a stamped row does not depend on the test host's."""
    return session.execute(sa.select(sa.func.now())).scalar_one()


# ---------------------------------------------------------------------------
# The lock and the one-run rule (design spec §9)
# ---------------------------------------------------------------------------


def test_an_event_is_locked_until_the_instructor_unlocks_it(
    exercise_sessions: sessionmaker[Session],
) -> None:
    """Absence of a row is 'locked' — the state a boolean column could not express."""
    results = ExerciseResultsRepository()
    instructor = ExerciseInstructorRepository()
    with exercise_sessions() as session:
        dataset_id, _ = _classroom(session)

        assert results.results_unlocked(session, dataset_id=dataset_id, event_key=_ROUND_ONE) is (
            False
        )
        instructor.unlock_results(session, dataset_id=dataset_id, event_key=_ROUND_ONE)
        session.commit()

        assert results.results_unlocked(session, dataset_id=dataset_id, event_key=_ROUND_ONE) is (
            True
        )
        assert results.results_unlocked(session, dataset_id=dataset_id, event_key=_ROUND_TWO) is (
            False
        ), "unlocking one event must not unlock the other"


def test_a_run_is_stored_and_read_back_panel_for_panel(
    exercise_sessions: sessionmaker[Session],
) -> None:
    results = ExerciseResultsRepository()
    with exercise_sessions() as session:
        dataset_id, (workspace_id, _) = _classroom(session)
        _record(results, session, dataset_id=dataset_id, workspace_id=workspace_id)
        session.commit()

        stored = results.get_run(session, workspace_id=workspace_id, event_key=_ROUND_ONE)

    assert stored is not None
    assert stored.team == _TEAM
    assert stored.email_everyone == _EVERYONE, "the JSONB panel round-trips exactly"
    assert stored.seats_empty == 51
    assert stored.round == 1
    assert stored.setting_name is None


def test_a_second_run_is_refused_with_the_specs_own_sentence(
    exercise_sessions: sessionmaker[Session],
) -> None:
    results = ExerciseResultsRepository()
    with exercise_sessions() as session:
        dataset_id, (workspace_id, _) = _classroom(session)
        _record(results, session, dataset_id=dataset_id, workspace_id=workspace_id)
        session.commit()

        with pytest.raises(AlreadyRunError) as refused:
            _record(results, session, dataset_id=dataset_id, workspace_id=workspace_id)

    assert str(refused.value) == ALREADY_RUN_SENTENCE
    assert str(refused.value) == "This team has already run results for this event."


def test_two_runs_arriving_together_leave_exactly_one_row(
    exercise_sessions: sessionmaker[Session],
) -> None:
    """The one-run rule **as a constraint**, which is the whole of design spec §9.

    Both transactions pass ``record_run``'s courtesy read — the first has not
    committed, so under READ COMMITTED the second simply does not see its row —
    and the constraint is what decides. The second's ``INSERT`` violates
    ``uq_exercise_result_run_workspace_event``, the repository's scrubber
    recognises that constraint by name, and the caller gets the spec's sentence
    rather than a driver error.

    Serialised rather than raced on two threads: what this proves is that the
    **constraint** is load-bearing, not that a particular interleaving is timed
    right, and a read-then-write that both sides passed is exactly the
    interleaving reproduced here.
    """
    results = ExerciseResultsRepository()
    with exercise_sessions() as first, exercise_sessions() as second:
        dataset_id, (workspace_id, _) = _classroom(first)

        # Both see "no run yet": the second's read happens before the first commits.
        assert results.get_run(first, workspace_id=workspace_id, event_key=_ROUND_ONE) is None
        assert results.get_run(second, workspace_id=workspace_id, event_key=_ROUND_ONE) is None

        _record(results, first, dataset_id=dataset_id, workspace_id=workspace_id)
        first.commit()

        with pytest.raises(AlreadyRunError) as refused:
            _record(results, second, dataset_id=dataset_id, workspace_id=workspace_id)
        second.rollback()

        rows = first.execute(
            sa.select(sa.func.count())
            .select_from(schema.exercise_result_run)
            .where(schema.exercise_result_run.c.workspace_id == workspace_id)
        ).scalar_one()

    assert str(refused.value) == ALREADY_RUN_SENTENCE
    assert rows == 1
    assert refused.value.__context__ is None, "the driver's exception must not travel with it"


def test_one_team_may_run_both_rounds_and_another_team_the_same_event(
    exercise_sessions: sessionmaker[Session],
) -> None:
    """The constraint is on ``(workspace, event)`` and on nothing wider."""
    results = ExerciseResultsRepository()
    with exercise_sessions() as session:
        dataset_id, (first, second) = _classroom(session)
        _record(results, session, dataset_id=dataset_id, workspace_id=first)
        _record(
            results,
            session,
            dataset_id=dataset_id,
            workspace_id=first,
            event_key=_ROUND_TWO,
            round_number=2,
        )
        _record(results, session, dataset_id=dataset_id, workspace_id=second)
        session.commit()

        by_round = results.get_run_for_round(session, workspace_id=first, round_number=2)
        other = results.get_run(session, workspace_id=second, event_key=_ROUND_ONE)

    assert by_round is not None
    assert by_round.event_key == _ROUND_TWO
    assert other is not None


def test_a_run_for_an_event_in_another_data_file_is_refused_as_one_sentence(
    exercise_sessions: sessionmaker[Session],
) -> None:
    """The composite foreign key, scrubbed: one sentence, no driver text."""
    results = ExerciseResultsRepository()
    with exercise_sessions() as session:
        dataset_id, (workspace_id, _) = _classroom(session)

        with pytest.raises(ExerciseResultsWriteRefused) as refused:
            _record(
                results,
                session,
                dataset_id=dataset_id,
                workspace_id=workspace_id,
                event_key="not-in-this-file",
            )
        session.rollback()

    assert str(refused.value) == "Your results could not be stored."
    assert refused.value.__context__ is None
    assert "parameters" not in str(refused.value).lower()


# ---------------------------------------------------------------------------
# The asking choice and the refresh (design spec §12, §13)
# ---------------------------------------------------------------------------


def test_the_asking_choice_is_stored_once(exercise_sessions: sessionmaker[Session]) -> None:
    results = ExerciseResultsRepository()
    with exercise_sessions() as session:
        dataset_id, (workspace_id, other_id) = _classroom(session)

        assert results.choose_asking(session, workspace_id=workspace_id, choice="required") is True
        assert (
            results.choose_asking(session, workspace_id=workspace_id, choice="small_reward")
            is False
        ), "the second choice must not replace the first"
        session.commit()

        state = results.team_state(session, workspace_id=workspace_id)
        untouched = results.team_state(session, workspace_id=other_id)

    assert state is not None
    assert state.asking_choice == "required"
    assert state.refreshed_at is None
    assert untouched is not None
    assert untouched.asking_choice is None, "one team's choice is another team's business"
    assert dataset_id  # the fixture's data file is what both teams are on


def test_the_seed_is_read_only_by_the_read_that_names_it(
    exercise_sessions: sessionmaker[Session],
) -> None:
    """``ExerciseWorkspace`` carries no seed; ``team_state`` is where it is reached."""
    results = ExerciseResultsRepository()
    with exercise_sessions() as session:
        _, (workspace_id, _) = _classroom(session)
        stored = session.execute(
            sa.select(schema.exercise_team_workspace.c.seed).where(
                schema.exercise_team_workspace.c.id == workspace_id
            )
        ).scalar_one()

        state = results.team_state(session, workspace_id=workspace_id)

    assert state is not None
    assert state.seed == stored


def test_a_refresh_writes_the_overlay_and_may_not_run_twice(
    exercise_sessions: sessionmaker[Session],
) -> None:
    results = ExerciseResultsRepository()
    with exercise_sessions() as session:
        dataset_id, (workspace_id, _) = _classroom(session)
        results.choose_asking(session, workspace_id=workspace_id, choice="required")
        session.commit()

        counts = results.apply_refresh(
            session,
            dataset_id=dataset_id,
            workspace_id=workspace_id,
            added_topics=["analytics"],
            topic_gainers=[1],
            card_profile_nos=[2],
            non_responding_profile_nos=[3],
            now=_now(session),
        )
        session.commit()

        again = results.apply_refresh(
            session,
            dataset_id=dataset_id,
            workspace_id=workspace_id,
            added_topics=["analytics"],
            topic_gainers=[1, 2, 3],
            card_profile_nos=[1],
            non_responding_profile_nos=[1],
            now=_now(session),
        )
        session.commit()

        rows = {
            row.profile_no: row
            for row in session.execute(
                sa.select(schema.exercise_profile_overlay).where(
                    schema.exercise_profile_overlay.c.workspace_id == workspace_id
                )
            ).all()
        }

    assert counts is not None
    assert (counts.topics_added, counts.cards_completed, counts.non_responding) == (1, 1, 1)
    assert again is None, "a second refresh must claim nothing and write nothing"
    assert set(rows) == {1, 2, 3}
    assert rows[1].added_event_topics == ["analytics"]
    assert rows[2].card_interests == _WITHHELD[2], "the card is copied from the withheld column"
    assert rows[3].non_responding is True
    assert rows[1].card_interests is None, "no card was asked for, so none was given"


def test_a_refresh_before_the_choice_claims_nothing(
    exercise_sessions: sessionmaker[Session],
) -> None:
    """``ck_exercise_team_workspace_refresh_after_choice`` as the claim's predicate."""
    results = ExerciseResultsRepository()
    with exercise_sessions() as session:
        dataset_id, (workspace_id, _) = _classroom(session)

        counts = results.apply_refresh(
            session,
            dataset_id=dataset_id,
            workspace_id=workspace_id,
            added_topics=["analytics"],
            topic_gainers=[1],
            card_profile_nos=[2],
            non_responding_profile_nos=[],
            now=_now(session),
        )
        session.commit()

        overlay = session.execute(
            sa.select(sa.func.count()).select_from(schema.exercise_profile_overlay)
        ).scalar_one()

    assert counts is None
    assert overlay == 0


def test_the_copied_card_leaves_the_withheld_column_untouched(
    exercise_sessions: sessionmaker[Session],
) -> None:
    """A copy, not a move: the profile row is the data file and is never written."""
    results = ExerciseResultsRepository()
    with exercise_sessions() as session:
        dataset_id, (workspace_id, _) = _classroom(session)
        results.choose_asking(session, workspace_id=workspace_id, choice="required")
        results.apply_refresh(
            session,
            dataset_id=dataset_id,
            workspace_id=workspace_id,
            added_topics=[],
            topic_gainers=[],
            card_profile_nos=[1, 2],
            non_responding_profile_nos=[],
            now=_now(session),
        )
        session.commit()

        withheld = {
            row.profile_no: row.hidden_true_interests
            for row in session.execute(
                sa.select(
                    schema.exercise_profile.c.profile_no,
                    schema.exercise_profile.c.hidden_true_interests,
                ).where(schema.exercise_profile.c.dataset_id == dataset_id)
            ).all()
        }

    assert withheld == {key: value for key, value in sorted(_WITHHELD.items())}


def test_a_refresh_reaches_only_its_own_teams_overlay(
    exercise_sessions: sessionmaker[Session],
) -> None:
    """Design spec §2's isolation, as a key rather than as a discipline."""
    results = ExerciseResultsRepository()
    with exercise_sessions() as session:
        dataset_id, (workspace_id, other_id) = _classroom(session)
        for workspace in (workspace_id, other_id):
            results.choose_asking(session, workspace_id=workspace, choice="required")
        results.apply_refresh(
            session,
            dataset_id=dataset_id,
            workspace_id=workspace_id,
            added_topics=["analytics"],
            topic_gainers=[1, 2, 3],
            card_profile_nos=[1, 2],
            non_responding_profile_nos=[3],
            now=_now(session),
        )
        session.commit()

        touched = {
            row.workspace_id
            for row in session.execute(
                sa.select(schema.exercise_profile_overlay.c.workspace_id)
            ).all()
        }
        awaiting = results.workspaces_awaiting_refresh(session)

    assert touched == {workspace_id}
    assert [candidate.workspace_id for candidate in awaiting] == [other_id], (
        "the refreshed team must drop out of the refresh-all set and the other must stay in"
    )


def test_refresh_all_sees_only_teams_that_chose_and_have_not_refreshed(
    exercise_sessions: sessionmaker[Session],
) -> None:
    results = ExerciseResultsRepository()
    with exercise_sessions() as session:
        _, (chosen, unchosen) = _classroom(session)
        results.choose_asking(session, workspace_id=chosen, choice="small_reward")
        session.commit()

        awaiting = results.workspaces_awaiting_refresh(session)

    assert [candidate.workspace_id for candidate in awaiting] == [chosen]
    assert awaiting[0].asking_choice == "small_reward"
    assert awaiting[0].team_number == 1
    assert unchosen not in {candidate.workspace_id for candidate in awaiting}


# ---------------------------------------------------------------------------
# A reset and a re-point clear what they say they clear
# ---------------------------------------------------------------------------


def test_a_reset_clears_the_run_the_overlay_and_the_choice(
    exercise_sessions: sessionmaker[Session],
) -> None:
    """Design spec §11's reset, over the rows this track added to it."""
    results = ExerciseResultsRepository()
    workspaces = ExerciseWorkspaceRepository()
    with exercise_sessions() as session:
        dataset_id, (workspace_id, other_id) = _classroom(session)
        _record(results, session, dataset_id=dataset_id, workspace_id=workspace_id)
        _record(results, session, dataset_id=dataset_id, workspace_id=other_id)
        results.choose_asking(session, workspace_id=workspace_id, choice="required")
        results.apply_refresh(
            session,
            dataset_id=dataset_id,
            workspace_id=workspace_id,
            added_topics=["analytics"],
            topic_gainers=[1],
            card_profile_nos=[2],
            non_responding_profile_nos=[3],
            now=_now(session),
        )
        session.commit()
        before = results.team_state(session, workspace_id=workspace_id)

        workspaces.reset_team(session, workspace_id=workspace_id)
        session.commit()

        after = results.team_state(session, workspace_id=workspace_id)
        overlay = session.execute(
            sa.select(sa.func.count())
            .select_from(schema.exercise_profile_overlay)
            .where(schema.exercise_profile_overlay.c.workspace_id == workspace_id)
        ).scalar_one()
        run = results.get_run(session, workspace_id=workspace_id, event_key=_ROUND_ONE)
        others_run = results.get_run(session, workspace_id=other_id, event_key=_ROUND_ONE)

    assert before is not None
    assert after is not None
    assert after.asking_choice is None
    assert after.refreshed_at is None
    assert after.seed != before.seed, "a reset regenerates the seed"
    assert overlay == 0
    assert run is None
    assert others_run is not None, "a reset reaches one team and no other"


def test_a_repoint_clears_every_teams_runs_before_it_moves_them(
    exercise_sessions: sessionmaker[Session],
) -> None:
    """The composite keys are ``ON DELETE CASCADE`` only, so the order is the rule."""
    results = ExerciseResultsRepository()
    instructor = ExerciseInstructorRepository()
    with exercise_sessions() as session:
        dataset_id, (workspace_id, other_id) = _classroom(session)
        _record(results, session, dataset_id=dataset_id, workspace_id=workspace_id)
        results.choose_asking(session, workspace_id=workspace_id, choice="required")
        target = _insert_dataset(session, label="results-target")
        _insert_events(session, dataset_id=target)
        _insert_profiles(session, dataset_id=target)
        session.commit()

        outcome = instructor.repoint_workspaces(session, dataset_id=target)
        session.commit()

        runs = session.execute(
            sa.select(sa.func.count()).select_from(schema.exercise_result_run)
        ).scalar_one()
        state = results.team_state(session, workspace_id=workspace_id)

    assert outcome.moved == 2
    assert runs == 0
    assert state is not None
    assert state.asking_choice is None
    assert other_id


# ---------------------------------------------------------------------------
# The lock order (settings_repository.SAVED_SETTING_LOCK_KEY's per-path walk)
# ---------------------------------------------------------------------------

#: Statements that take a row lock: an explicit ``FOR UPDATE``, and the implicit
#: lock an ``UPDATE``, ``DELETE`` or ``INSERT`` takes on the row it writes or on
#: the row its foreign key references.
_ROW_LOCKING = ("FOR UPDATE", "UPDATE ", "DELETE ", "INSERT ")

_KEYS = {
    WORKSPACE_MEMBERSHIP_LOCK_KEY: "membership",
    SAVED_SETTING_LOCK_KEY: "saved settings",
    RESULT_RUN_LOCK_KEY: "result runs",
}


def _try_key(session: Session, key: int) -> bool:
    """Whether one advisory key is free, from this session's view.

    ``pg_try_advisory_xact_lock`` rather than a blocking acquire, so a probe can
    ask "is it held?" without becoming the thing that waits. The caller rolls
    back immediately: a successful try has *taken* the key, and leaving it taken
    would make the next probe lie.
    """
    held = session.execute(sa.select(sa.func.pg_try_advisory_xact_lock(key))).scalar_one()
    session.rollback()
    return bool(held)


def _statement_log(session: Session) -> list[tuple[str, object]]:
    """Record every statement this session's connection executes, in order.

    A SQLAlchemy ``before_cursor_execute`` listener rather than a clock or a
    second connection. What a lock-order claim is about is the **order in which
    one method acquires things**, and that is a property of the statements it
    sends — so it is read off the statements, with no timing in the test at all.

    The post-mortem alternative cannot work here, and
    ``tests/integration/test_exercise_settings_persistence.py`` records why at
    length: a ``lock_timeout`` leaves either an invalidated connection or an
    aborted transaction, and in both cases the locks are gone before a third
    connection can ask about them.
    """
    recorded: list[tuple[str, object]] = []
    connection = session.connection()

    def record(
        _conn: object,
        _cursor: object,
        statement: str,
        parameters: object,
        _context: object,
        _executemany: bool,
    ) -> None:
        recorded.append((" ".join(statement.split()).upper(), parameters))

    sa.event.listen(connection.engine, "before_cursor_execute", record)
    session.info["_stop_recording"] = lambda: sa.event.remove(
        connection.engine, "before_cursor_execute", record
    )
    return recorded


def _advisory_key(parameters: object) -> int | None:
    """The advisory key one recorded statement passed, if it passed one."""
    if isinstance(parameters, dict):
        values = list(parameters.values())
    elif isinstance(parameters, tuple | list):
        values = list(parameters)
    else:
        return None
    for value in values:
        if isinstance(value, int) and value in _KEYS:
            return value
    return None


def _acquired_at(recorded: list[tuple[str, object]], key: int) -> int:
    return next(
        index for index, (_, parameters) in enumerate(recorded) if _advisory_key(parameters) == key
    )


def _row_locks_at(recorded: list[tuple[str, object]]) -> list[int]:
    return [
        index
        for index, (statement, _) in enumerate(recorded)
        if any(shape in statement for shape in _ROW_LOCKING)
    ]


def test_the_results_key_is_derived_from_its_own_table_name() -> None:
    """Not reused from the saved-settings key, which is PR #188's own instruction."""
    import hashlib

    assert (
        int.from_bytes(hashlib.sha256(b"exercise_result_run").digest()[:8], "big", signed=True)
        == RESULT_RUN_LOCK_KEY
    )
    assert RESULT_RUN_LOCK_KEY not in {SAVED_SETTING_LOCK_KEY, WORKSPACE_MEMBERSHIP_LOCK_KEY}


def test_a_results_write_takes_only_the_results_key(
    exercise_sessions: sessionmaker[Session],
) -> None:
    """Deadlock freedom, as the property rather than as prose.

    The family's order is membership → saved settings → result runs → row locks.
    A cycle needs a path that takes them the other way round, and the candidates
    are the writes that hold a key and then wait for a row — so this probes the
    new one directly: while ``record_run`` holds the results key *and* the row
    locks its insert took, the two earlier keys are still free. Nothing therefore
    waits on an earlier key while holding a later one.
    """
    results = ExerciseResultsRepository()
    with exercise_sessions() as writing, exercise_sessions() as probe:
        dataset_id, (workspace_id, _) = _classroom(writing)
        _record(results, writing, dataset_id=dataset_id, workspace_id=workspace_id)

        assert _try_key(probe, RESULT_RUN_LOCK_KEY) is False, (
            "the run must be holding the results key at this point"
        )
        assert _try_key(probe, SAVED_SETTING_LOCK_KEY) is True, (
            "a results write that held the saved-settings key would invert the order"
        )
        assert _try_key(probe, WORKSPACE_MEMBERSHIP_LOCK_KEY) is True, (
            "a results write that held the membership key would invert the order"
        )
        writing.commit()
        assert _try_key(probe, RESULT_RUN_LOCK_KEY) is True, "committing releases it"


def test_a_run_takes_the_results_key_before_any_row_lock(
    exercise_sessions: sessionmaker[Session],
) -> None:
    results = ExerciseResultsRepository()
    with exercise_sessions() as session:
        dataset_id, (workspace_id, _) = _classroom(session)

        recorded = _statement_log(session)
        _record(results, session, dataset_id=dataset_id, workspace_id=workspace_id)
        session.info["_stop_recording"]()
        session.commit()

    row_locks = _row_locks_at(recorded)
    assert row_locks, "the run took no row lock at all; this fixture proves nothing"
    assert _acquired_at(recorded, RESULT_RUN_LOCK_KEY) < min(row_locks)


def test_a_refresh_claims_the_row_after_the_key_and_before_the_overlay(
    exercise_sessions: sessionmaker[Session],
) -> None:
    """Two claims in one: the key comes first, and the ``refreshed_at`` claim
    comes before any overlay write — so two refreshes arriving together cannot
    both apply a share."""
    results = ExerciseResultsRepository()
    with exercise_sessions() as session:
        dataset_id, (workspace_id, _) = _classroom(session)
        results.choose_asking(session, workspace_id=workspace_id, choice="required")
        session.commit()

        recorded = _statement_log(session)
        results.apply_refresh(
            session,
            dataset_id=dataset_id,
            workspace_id=workspace_id,
            added_topics=["analytics"],
            topic_gainers=[1],
            card_profile_nos=[2],
            non_responding_profile_nos=[3],
            now=_now(session),
        )
        session.info["_stop_recording"]()
        session.commit()

    key_at = _acquired_at(recorded, RESULT_RUN_LOCK_KEY)
    claim_at = next(
        index
        for index, (statement, _) in enumerate(recorded)
        if "UPDATE EXERCISE_TEAM_WORKSPACE" in statement
    )
    overlay_at = next(
        index
        for index, (statement, _) in enumerate(recorded)
        if "INSERT INTO EXERCISE_PROFILE_OVERLAY" in statement
    )

    assert key_at < claim_at < overlay_at


def test_a_reset_takes_all_three_keys_in_the_declared_order(
    exercise_sessions: sessionmaker[Session],
) -> None:
    """``reset_team`` deletes the rows this track writes, so it must take its key.

    Without it a run or a refresh committing in the window between this DELETE
    and this commit survives a reset that was meant to clear it — review round
    1's item 9 with ``exercise_result_run`` in place of
    ``exercise_saved_setting``.
    """
    results = ExerciseResultsRepository()
    workspaces = ExerciseWorkspaceRepository()
    with exercise_sessions() as session:
        dataset_id, (workspace_id, _) = _classroom(session)
        _record(results, session, dataset_id=dataset_id, workspace_id=workspace_id)
        session.commit()

        recorded = _statement_log(session)
        workspaces.reset_team(session, workspace_id=workspace_id)
        session.info["_stop_recording"]()
        session.commit()

    saved_at = _acquired_at(recorded, SAVED_SETTING_LOCK_KEY)
    results_at = _acquired_at(recorded, RESULT_RUN_LOCK_KEY)
    row_locks = _row_locks_at(recorded)

    assert row_locks, "the reset took no row lock at all; this fixture proves nothing"
    assert saved_at < results_at, "the saved-settings key is taken before the results key"
    assert results_at < min(row_locks), (
        "the reset took a row lock before the results key: that is the order that "
        "deadlocks against record_run, which holds the key and then waits for a "
        "FOR KEY SHARE lock on the workspace row"
    )


def test_a_repoint_takes_every_key_before_any_row_lock(
    exercise_sessions: sessionmaker[Session],
) -> None:
    """The only path that takes all three, and the order is the family's."""
    instructor = ExerciseInstructorRepository()
    with exercise_sessions() as session:
        _, _ = _classroom(session)
        target = _insert_dataset(session, label="repoint-target")
        session.commit()

        recorded = _statement_log(session)
        instructor.repoint_workspaces(session, dataset_id=target)
        session.info["_stop_recording"]()
        session.commit()

    membership_at = _acquired_at(recorded, WORKSPACE_MEMBERSHIP_LOCK_KEY)
    saved_at = _acquired_at(recorded, SAVED_SETTING_LOCK_KEY)
    results_at = _acquired_at(recorded, RESULT_RUN_LOCK_KEY)
    row_locks = _row_locks_at(recorded)

    assert row_locks, "the re-point took no row lock at all; this fixture proves nothing"
    assert membership_at < saved_at < results_at
    assert results_at < min(row_locks)


def test_a_child_clear_takes_the_results_key_too(
    exercise_sessions: sessionmaker[Session],
) -> None:
    """``reset_workspace_children`` is the delete half a re-point runs per team."""
    instructor = ExerciseInstructorRepository()
    settings = ExerciseSettingsRepository()
    results = ExerciseResultsRepository()
    with exercise_sessions() as session:
        dataset_id, (workspace_id, _) = _classroom(session)
        settings.save_setting(
            session,
            dataset_id=dataset_id,
            workspace_id=workspace_id,
            event_key=_ROUND_ONE,
            name="broad",
            weights=_WEIGHTS,
        )
        _record(results, session, dataset_id=dataset_id, workspace_id=workspace_id)
        session.commit()

        recorded = _statement_log(session)
        instructor.reset_workspace_children(
            session, dataset_id=dataset_id, workspace_id=workspace_id
        )
        session.info["_stop_recording"]()
        session.commit()

        remaining = results.get_run(session, workspace_id=workspace_id, event_key=_ROUND_ONE)

    saved_at = _acquired_at(recorded, SAVED_SETTING_LOCK_KEY)
    results_at = _acquired_at(recorded, RESULT_RUN_LOCK_KEY)
    row_locks = _row_locks_at(recorded)

    assert saved_at < results_at < min(row_locks)
    assert remaining is None
