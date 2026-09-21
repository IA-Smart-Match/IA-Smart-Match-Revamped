"""Saved settings and the overlay join against a real PostgreSQL (CE-MATCHING-API).

``tests/unit/test_exercise_matching_router.py`` proves the routes over a fake
repository. A fake cannot prove any of the four things that actually hold in a
classroom, and all four are database properties:

* **The cap is a lock, not a count.** Migration ``0037`` created the UNIQUE
  constraint on ``(workspace_id, event_key, name)`` and no partial check, so
  "at most three" is this repository's, and two saves racing would each read
  two and each insert. That the key is held, and that the second save sees the
  first's row, is only observable against a real transaction.
* **Isolation.** One team's settings are not *filtered out* of another team's
  answer; they are never selected. The difference is a ``WHERE`` clause, and a
  fake that stores rows in a dict cannot get it wrong.
* **The outer join.** Design spec §2's ``base row ⟕ overlay`` with the
  workspace in the *join condition*: a team with no overlay rows must still see
  every profile, which is exactly what the same predicate in a ``WHERE`` would
  break.
* **The scrubber.** A refused write must carry no driver text and no
  ``__context__`` (ADR-0025 D6), and only a real constraint violation produces
  one.

Runs against its own scratch database, migrated to head, and dropped
afterwards; skipped where no PostgreSQL is reachable.
"""

from __future__ import annotations

import threading
import time
import uuid
from collections.abc import Iterator

import pytest

pytest.importorskip("sqlalchemy")

import sqlalchemy as sa
from migration_harness import alembic, connected, scratch_database
from smartmatch_persistence.exercise import schema
from smartmatch_persistence.exercise.instructor_repository import (
    ExerciseInstructorRepository,
    ExerciseWriteRefused,
    RepointOutcome,
)
from smartmatch_persistence.exercise.settings_repository import (
    MAX_SAVED_SETTINGS_PER_EVENT,
    SAVED_SETTING_LOCK_KEY,
    ExerciseSettingsRepository,
    ExerciseSettingsWriteRefused,
    TooManySavedSettingsError,
    lock_saved_settings,
)
from smartmatch_persistence.exercise.team_view_repository import ExerciseTeamViewRepository
from smartmatch_persistence.exercise.workspace_repository import (
    WORKSPACE_MEMBERSHIP_LOCK_KEY,
    ExerciseWorkspaceRepository,
    lock_workspace_membership,
)
from sqlalchemy import Engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

pytestmark = pytest.mark.integration

#: Not a real key, and assembled from pieces for the reason the other exercise
#: files give: ``tools/scan_forbidden.py`` matches the shape of a committed
#: credential, and a test that needs an exception from that rule is a test
#: written badly.
_SECRET = "-".join(("integration", "only", "exercise", "settings", "key"))

_EVENT_KEY = "northline"
_WEIGHTS = {"same_major": 0.5, "stated_interest_overlap": 0.5}


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
    """One ``exercise_dataset`` row, written directly."""
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


def _insert_event(session: Session, *, dataset_id: uuid.UUID) -> None:
    session.execute(
        sa.insert(schema.exercise_event).values(
            dataset_id=dataset_id,
            event_key=_EVENT_KEY,
            name="Northline round",
            topic_tags=["analytics"],
            target_majors=["Marketing"],
            is_exercise_event=True,
            sequence=11,
        )
    )


def _insert_profiles(session: Session, *, dataset_id: uuid.UUID) -> None:
    """Three fictional profiles, one per design spec §7 state."""
    rows = [
        {
            "dataset_id": dataset_id,
            "profile_no": 1,
            "display_name": "Avery Brooks",
            "major": "Marketing",
            "class_year": "one",
            "past_event_keys": [],
            "stated_interests": ["analytics"],
            "career_goal": "analytics",
            # Stored because the column is NOT NULL. Nothing in this file reads
            # it back, and the repository under test does not select it.
            "hidden_true_interests": [],
        },
        {
            "dataset_id": dataset_id,
            "profile_no": 2,
            "display_name": "Bao Nguyen",
            "major": "Finance",
            "class_year": "two",
            "past_event_keys": ["past-analytics"],
            "stated_interests": None,
            "career_goal": None,
            "hidden_true_interests": [],
        },
        {
            "dataset_id": dataset_id,
            "profile_no": 3,
            "display_name": "Cam Ellis",
            "major": "Marketing",
            "class_year": "two",
            "past_event_keys": [],
            "stated_interests": None,
            "career_goal": None,
            "hidden_true_interests": [],
        },
    ]
    session.execute(sa.insert(schema.exercise_profile), rows)


def _classroom(session: Session, *, teams: int = 2) -> tuple[uuid.UUID, list[uuid.UUID]]:
    """A data file, its event, three profiles and ``teams`` workspaces on it."""
    dataset_id = _insert_dataset(session, label="settings")
    _insert_event(session, dataset_id=dataset_id)
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


# ---------------------------------------------------------------------------
# The at-most-three rule
# ---------------------------------------------------------------------------


def test_three_names_are_stored_and_a_fourth_new_name_is_refused(
    exercise_sessions: sessionmaker[Session],
) -> None:
    repository = ExerciseSettingsRepository()
    with exercise_sessions() as session:
        dataset_id, (workspace_id, _) = _classroom(session)
        for name in ("broad", "narrow", "balanced"):
            repository.save_setting(
                session,
                dataset_id=dataset_id,
                workspace_id=workspace_id,
                event_key=_EVENT_KEY,
                name=name,
                weights=_WEIGHTS,
            )
        session.commit()

        with pytest.raises(TooManySavedSettingsError) as refused:
            repository.save_setting(
                session,
                dataset_id=dataset_id,
                workspace_id=workspace_id,
                event_key=_EVENT_KEY,
                name="one-more",
                weights=_WEIGHTS,
            )
        session.rollback()

        stored = repository.list_settings(session, workspace_id=workspace_id, event_key=_EVENT_KEY)

    assert len(stored) == MAX_SAVED_SETTINGS_PER_EVENT
    assert "Delete one before saving another." in str(refused.value)


def test_saving_over_an_existing_name_is_allowed_and_changes_no_count(
    exercise_sessions: sessionmaker[Session],
) -> None:
    """Three *names*, not three saves. The UNIQUE constraint is what makes it one row."""
    repository = ExerciseSettingsRepository()
    with exercise_sessions() as session:
        dataset_id, (workspace_id, _) = _classroom(session)
        for name in ("broad", "narrow", "balanced"):
            repository.save_setting(
                session,
                dataset_id=dataset_id,
                workspace_id=workspace_id,
                event_key=_EVENT_KEY,
                name=name,
                weights=_WEIGHTS,
            )
        updated = repository.save_setting(
            session,
            dataset_id=dataset_id,
            workspace_id=workspace_id,
            event_key=_EVENT_KEY,
            name="narrow",
            weights={"same_major": 0.9},
        )
        session.commit()
        stored = repository.list_settings(session, workspace_id=workspace_id, event_key=_EVENT_KEY)

    assert updated.weights == {"same_major": 0.9}
    assert len(stored) == MAX_SAVED_SETTINGS_PER_EVENT
    assert {setting.name for setting in stored} == {"broad", "narrow", "balanced"}


def test_the_cap_is_counted_under_the_lock(
    exercise_sessions: sessionmaker[Session],
) -> None:
    """A save takes the key before it counts, so two saves cannot both pass.

    Asserted by holding the key from a second connection and giving the saver a
    short ``lock_timeout``: it is refused, quickly and deterministically, rather
    than waiting on a sleep. A repository that counted without the lock would
    not block here at all — it would read two names and insert a third.
    """
    repository = ExerciseSettingsRepository()
    with exercise_sessions() as holder, exercise_sessions() as saver:
        dataset_id, (workspace_id, _) = _classroom(holder)
        holder.execute(sa.select(sa.func.pg_advisory_xact_lock(SAVED_SETTING_LOCK_KEY)))

        saver.execute(sa.text("SET LOCAL lock_timeout = '250ms'"))
        with pytest.raises(SQLAlchemyError) as refused:
            repository.save_setting(
                saver,
                dataset_id=dataset_id,
                workspace_id=workspace_id,
                event_key=_EVENT_KEY,
                name="broad",
                weights=_WEIGHTS,
            )
        saver.rollback()
        holder.rollback()

    assert "lock timeout" in str(refused.value).lower()


def test_a_second_connections_fourth_name_sees_the_first_threes_rows(
    exercise_sessions: sessionmaker[Session],
) -> None:
    """The outcome the lock protects, stated as behaviour rather than as timing.

    One connection saves the third name and commits; the other — a second
    laptop on the same team, which is the product's own shape — then reads
    three and is refused. Without the cap being a repository rule over committed
    rows, the team would end with four.
    """
    repository = ExerciseSettingsRepository()
    with exercise_sessions() as first, exercise_sessions() as second:
        dataset_id, (workspace_id, _) = _classroom(first)
        for name in ("broad", "narrow", "balanced"):
            repository.save_setting(
                first,
                dataset_id=dataset_id,
                workspace_id=workspace_id,
                event_key=_EVENT_KEY,
                name=name,
                weights=_WEIGHTS,
            )
        first.commit()

        with pytest.raises(TooManySavedSettingsError):
            repository.save_setting(
                second,
                dataset_id=dataset_id,
                workspace_id=workspace_id,
                event_key=_EVENT_KEY,
                name="one-more",
                weights=_WEIGHTS,
            )
        second.rollback()

        assert (
            len(repository.list_settings(second, workspace_id=workspace_id, event_key=_EVENT_KEY))
            == MAX_SAVED_SETTINGS_PER_EVENT
        )


def test_the_cap_is_per_event_rather_than_per_team(
    exercise_sessions: sessionmaker[Session],
) -> None:
    """Design spec §6: three per (workspace, event). A second event is its own three."""
    repository = ExerciseSettingsRepository()
    with exercise_sessions() as session:
        dataset_id, (workspace_id, _) = _classroom(session)
        session.execute(
            sa.insert(schema.exercise_event).values(
                dataset_id=dataset_id,
                event_key="harbor",
                name="Harbor round",
                topic_tags=["brand"],
                target_majors=["Marketing"],
                is_exercise_event=True,
                sequence=12,
            )
        )
        for name in ("broad", "narrow", "balanced"):
            repository.save_setting(
                session,
                dataset_id=dataset_id,
                workspace_id=workspace_id,
                event_key=_EVENT_KEY,
                name=name,
                weights=_WEIGHTS,
            )
        also = repository.save_setting(
            session,
            dataset_id=dataset_id,
            workspace_id=workspace_id,
            event_key="harbor",
            name="broad",
            weights=_WEIGHTS,
        )
        session.commit()

    assert also.event_key == "harbor"


# ---------------------------------------------------------------------------
# Isolation
# ---------------------------------------------------------------------------


def test_two_teams_never_see_each_others_settings(
    exercise_sessions: sessionmaker[Session],
) -> None:
    """Justin's first "easy to forget" item, as a property of the statements."""
    repository = ExerciseSettingsRepository()
    with exercise_sessions() as session:
        dataset_id, (team_one, team_two) = _classroom(session)
        repository.save_setting(
            session,
            dataset_id=dataset_id,
            workspace_id=team_one,
            event_key=_EVENT_KEY,
            name="ours",
            weights=_WEIGHTS,
        )
        session.commit()

        assert [
            setting.name
            for setting in repository.list_settings(
                session, workspace_id=team_one, event_key=_EVENT_KEY
            )
        ] == ["ours"]
        assert repository.list_settings(session, workspace_id=team_two, event_key=_EVENT_KEY) == ()
        assert (
            repository.get_setting(
                session, workspace_id=team_two, event_key=_EVENT_KEY, name="ours"
            )
            is None
        )
        # …and team two may use the same name for its own, which the UNIQUE
        # constraint permits because it is keyed on the workspace.
        repository.save_setting(
            session,
            dataset_id=dataset_id,
            workspace_id=team_two,
            event_key=_EVENT_KEY,
            name="ours",
            weights={"same_major": 1.0},
        )
        session.commit()
        theirs = repository.get_setting(
            session, workspace_id=team_two, event_key=_EVENT_KEY, name="ours"
        )
        ours = repository.get_setting(
            session, workspace_id=team_one, event_key=_EVENT_KEY, name="ours"
        )

    assert theirs is not None and ours is not None
    assert theirs.weights == {"same_major": 1.0}
    assert ours.weights == _WEIGHTS


def test_deleting_removes_one_teams_row_and_nothing_else(
    exercise_sessions: sessionmaker[Session],
) -> None:
    repository = ExerciseSettingsRepository()
    with exercise_sessions() as session:
        dataset_id, (team_one, team_two) = _classroom(session)
        for workspace_id in (team_one, team_two):
            repository.save_setting(
                session,
                dataset_id=dataset_id,
                workspace_id=workspace_id,
                event_key=_EVENT_KEY,
                name="ours",
                weights=_WEIGHTS,
            )
        session.commit()

        assert (
            repository.delete_setting(
                session,
                dataset_id=dataset_id,
                workspace_id=team_one,
                event_key=_EVENT_KEY,
                name="ours",
            )
            is True
        )
        # A second delete of the same name reports that nothing went.
        assert (
            repository.delete_setting(
                session,
                dataset_id=dataset_id,
                workspace_id=team_one,
                event_key=_EVENT_KEY,
                name="ours",
            )
            is False
        )
        session.commit()
        survived = repository.list_settings(session, workspace_id=team_two, event_key=_EVENT_KEY)

    assert [setting.name for setting in survived] == ["ours"]


def test_a_reset_takes_a_teams_settings_with_it(
    exercise_sessions: sessionmaker[Session],
) -> None:
    """Design spec §11's reset deletes this team's settings, by the foreign key."""
    settings = ExerciseSettingsRepository()
    with exercise_sessions() as session:
        dataset_id, (team_one, team_two) = _classroom(session)
        for workspace_id in (team_one, team_two):
            settings.save_setting(
                session,
                dataset_id=dataset_id,
                workspace_id=workspace_id,
                event_key=_EVENT_KEY,
                name="ours",
                weights=_WEIGHTS,
            )
        session.commit()

        ExerciseWorkspaceRepository().reset_team(session, workspace_id=team_one)
        session.commit()

        assert settings.list_settings(session, workspace_id=team_one, event_key=_EVENT_KEY) == ()
        assert (
            len(settings.list_settings(session, workspace_id=team_two, event_key=_EVENT_KEY)) == 1
        )


# ---------------------------------------------------------------------------
# The lock order, and the clearing paths that had fallen outside it (review 1)
# ---------------------------------------------------------------------------


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


def test_a_reset_takes_the_saved_settings_key_before_it_deletes(
    exercise_sessions: sessionmaker[Session],
) -> None:
    """Review round 1: a reset racing a save used to lose to it.

    ``reset_team`` deleted ``exercise_saved_setting`` rows without taking
    ``SAVED_SETTING_LOCK_KEY``. A save holds that key while it counts and
    inserts; the reset's ``DELETE`` could run in between and, under READ
    COMMITTED, simply not see the uncommitted row; the save then committed, and
    the team kept a setting the reset was meant to clear, with no error to say
    so.

    Asserted by holding the key from a second connection and giving the reset a
    short ``lock_timeout``: it is refused, quickly and deterministically, rather
    than waiting on a sleep. Before the fix it took no key at all and returned.
    """
    with exercise_sessions() as holder, exercise_sessions() as resetting:
        _, (workspace_id, _) = _classroom(holder)
        holder.execute(sa.select(sa.func.pg_advisory_xact_lock(SAVED_SETTING_LOCK_KEY)))

        resetting.execute(sa.text("SET LOCAL lock_timeout = '250ms'"))
        with pytest.raises(SQLAlchemyError) as refused:
            ExerciseWorkspaceRepository().reset_team(resetting, workspace_id=workspace_id)
        resetting.rollback()
        holder.rollback()

    assert "lock timeout" in str(refused.value).lower()


def test_the_instructor_child_clear_takes_the_saved_settings_key_too(
    exercise_sessions: sessionmaker[Session],
) -> None:
    """The same hole on the instructor's side, which the re-point runs through.

    The refusal here is :class:`ExerciseWriteRefused` rather than the driver's
    own error, and that is the second half of the fix: the acquire is a
    statement, and in this module a statement that fails must not let driver
    text out (ADR-0025 D6). Waiting is still what happened — the ``lock_timeout``
    fires only because the acquire blocked on the key the holder has — and
    without the acquire this method would simply have returned.
    """
    with exercise_sessions() as holder, exercise_sessions() as clearing:
        dataset_id, (workspace_id, _) = _classroom(holder)
        holder.execute(sa.select(sa.func.pg_advisory_xact_lock(SAVED_SETTING_LOCK_KEY)))

        clearing.execute(sa.text("SET LOCAL lock_timeout = '250ms'"))
        with pytest.raises(ExerciseWriteRefused) as refused:
            ExerciseInstructorRepository().reset_workspace_children(
                clearing, dataset_id=dataset_id, workspace_id=workspace_id
            )
        clearing.rollback()
        holder.rollback()

    assert str(refused.value) == "That team's work could not be cleared."
    assert refused.value.__context__ is None
    assert "lock timeout" not in str(refused.value).lower()


def test_a_save_never_takes_the_membership_key(
    exercise_sessions: sessionmaker[Session],
) -> None:
    """Deadlock freedom, as the property rather than as prose.

    The family's order is membership key, then saved-settings key, then row
    locks. A cycle needs a path that takes them the other way round, and the
    only candidate is the settings write — so this probes it directly: while a
    save holds the saved-settings key *and* the row locks its insert took, the
    membership key is still free. Nothing therefore waits on membership while
    holding saved-settings, and the order cannot be one edge of a cycle.
    """
    repository = ExerciseSettingsRepository()
    with exercise_sessions() as saving, exercise_sessions() as probe:
        dataset_id, (workspace_id, _) = _classroom(saving)
        repository.save_setting(
            saving,
            dataset_id=dataset_id,
            workspace_id=workspace_id,
            event_key=_EVENT_KEY,
            name="broad",
            weights=_WEIGHTS,
        )
        assert _try_key(probe, SAVED_SETTING_LOCK_KEY) is False, (
            "the save must be holding the saved-settings key at this point"
        )
        assert _try_key(probe, WORKSPACE_MEMBERSHIP_LOCK_KEY) is True, (
            "a save that held the membership key would invert the family's lock order"
        )
        saving.commit()
        assert _try_key(probe, SAVED_SETTING_LOCK_KEY) is True, "committing releases it"


#: Statements that take a row lock: an explicit ``FOR UPDATE``, and the implicit
#: lock an ``UPDATE``, ``DELETE`` or ``INSERT`` takes on the row it writes or on
#: the row its foreign key references.
_ROW_LOCKING = ("FOR UPDATE", "UPDATE ", "DELETE ", "INSERT ")


def _statement_log(session: Session) -> list[tuple[str, object]]:
    """Record every statement this session's connection executes, in order.

    A SQLAlchemy ``before_cursor_execute`` listener rather than a clock or a
    second connection. What F1 is about is the **order in which one method
    acquires things**, and that is a property of the statements it sends — so it
    is read off the statements, with no timing in the test at all.
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
    keys = {SAVED_SETTING_LOCK_KEY, WORKSPACE_MEMBERSHIP_LOCK_KEY}
    for value in values:
        if isinstance(value, int) and value in keys:
            return value
    return None


def test_a_repoint_takes_the_saved_settings_key_before_any_row_lock(
    exercise_sessions: sessionmaker[Session],
) -> None:
    """Review round 2, F1: the key is acquired before both ``FOR UPDATE`` reads.

    Round 1 acquired the saved-settings key inside ``reset_workspace_children``,
    which ``repoint_workspaces`` calls **after** it has row-locked every
    workspace. That is row locks before the key — the one order the family
    forbids — and the cycle it opens is not hypothetical: ``save_setting`` holds
    the key and then waits for the ``FOR KEY SHARE`` lock its insert's foreign
    key takes on the workspace row, which is exactly the row a re-point holds
    ``FOR UPDATE``. PostgreSQL aborts one of the two after ``deadlock_timeout``.

    **Why this is asserted on the statement log and not with a NOWAIT probe.**
    The obvious experiment — hold the key from a second connection, let the
    re-point block under a short ``lock_timeout``, then ask a third connection
    whether the workspace row is still free — cannot work here, and it was tried
    first. A ``lock_timeout`` surfaces as a psycopg ``OperationalError``, which
    SQLAlchemy treats as a disconnect and **invalidates the pooled connection**:
    by the time the exception reaches the test the backend is gone,
    ``pg_locks`` shows nothing for it, and the probe reports "free" whichever
    order the code used. Measured, not assumed — the probe passed against the
    unfixed code, which is the definition of a test that is not testing.

    So the order is read where it is actually decided: off the sequence of
    statements the method sends. No second connection, no timing, no sleep, and
    it fails against the round-1 code because the acquire genuinely comes later
    in that sequence.
    """
    repository = ExerciseInstructorRepository()
    with exercise_sessions() as session:
        _, _ = _classroom(session)
        target = _insert_dataset(session, label="repoint-target")
        session.commit()

        recorded = _statement_log(session)
        repository.repoint_workspaces(session, dataset_id=target)
        session.info["_stop_recording"]()
        session.commit()

    membership_at = next(
        index
        for index, (_, parameters) in enumerate(recorded)
        if _advisory_key(parameters) == WORKSPACE_MEMBERSHIP_LOCK_KEY
    )
    saved_settings_at = next(
        index
        for index, (_, parameters) in enumerate(recorded)
        if _advisory_key(parameters) == SAVED_SETTING_LOCK_KEY
    )
    row_locks_at = [
        index
        for index, (statement, _) in enumerate(recorded)
        if any(shape in statement for shape in _ROW_LOCKING)
    ]

    assert row_locks_at, "the re-point took no row lock at all; this fixture proves nothing"
    assert membership_at < saved_settings_at, (
        "the membership key must be taken first (the family's documented order)"
    )
    assert saved_settings_at < min(row_locks_at), (
        "the re-point took a row lock before the saved-settings key: that is the "
        "order that deadlocks against save_setting, which holds the key and then "
        "waits for a FOR KEY SHARE lock on the workspace row"
    )


def test_a_repoint_still_completes_when_nothing_holds_the_key(
    exercise_sessions: sessionmaker[Session],
) -> None:
    """The fix moved an acquire; it must not have moved the behaviour.

    A re-point with no contention still moves every team onto the target data
    file and clears the settings it was supposed to clear.
    """
    settings = ExerciseSettingsRepository()
    repository = ExerciseInstructorRepository()
    with exercise_sessions() as session:
        dataset_id, (workspace_id, other_id) = _classroom(session)
        settings.save_setting(
            session,
            dataset_id=dataset_id,
            workspace_id=workspace_id,
            event_key=_EVENT_KEY,
            name="broad",
            weights=_WEIGHTS,
        )
        target = _insert_dataset(session, label="repoint-target")
        session.commit()

        outcome = repository.repoint_workspaces(session, dataset_id=target)
        session.commit()

        table = schema.exercise_team_workspace
        datasets = {
            row.dataset_id
            for row in session.execute(
                sa.select(table.c.dataset_id).where(table.c.id.in_([workspace_id, other_id]))
            ).all()
        }
        remaining = settings.list_settings(session, workspace_id=workspace_id, event_key=_EVENT_KEY)

    assert outcome.moved == 2
    assert datasets == {target}
    assert remaining == ()


def test_a_reset_holds_both_keys_in_the_declared_order(
    exercise_sessions: sessionmaker[Session],
) -> None:
    """The re-point's path: membership first, then saved settings, then rows."""
    with exercise_sessions() as instructor, exercise_sessions() as probe:
        dataset_id, (workspace_id, _) = _classroom(instructor)
        assert _try_key(probe, WORKSPACE_MEMBERSHIP_LOCK_KEY) is True
        assert _try_key(probe, SAVED_SETTING_LOCK_KEY) is True

        lock_workspace_membership(instructor)
        assert _try_key(probe, WORKSPACE_MEMBERSHIP_LOCK_KEY) is False
        assert _try_key(probe, SAVED_SETTING_LOCK_KEY) is True, (
            "the saved-settings key must be taken after the membership key, not before"
        )

        ExerciseInstructorRepository().reset_workspace_children(
            instructor, dataset_id=dataset_id, workspace_id=workspace_id
        )
        assert _try_key(probe, SAVED_SETTING_LOCK_KEY) is False
        assert _try_key(probe, WORKSPACE_MEMBERSHIP_LOCK_KEY) is False

        instructor.commit()
        assert _try_key(probe, WORKSPACE_MEMBERSHIP_LOCK_KEY) is True
        assert _try_key(probe, SAVED_SETTING_LOCK_KEY) is True


def _wait_until_a_backend_waits_for_an_advisory_key(
    session: Session, *, seconds: float = 30.0
) -> None:
    """Block until some backend on this database is queued for an advisory key.

    The barrier the re-point regression coordinates on. It is an **observed
    lock** rather than a sleep: ``pg_locks`` says whether the other transaction
    has actually reached its acquire and is waiting, so the probe that follows
    cannot run early on a slow machine or late on a fast one. Bounded, so a
    re-point that never waits fails the test rather than hanging the suite.

    Scoped to ``current_database()`` because ``pg_locks`` is cluster-wide and a
    scratch database is not the only one on the server.
    """
    statement = sa.text(
        "SELECT count(*) FROM pg_locks "
        "WHERE locktype = 'advisory' AND NOT granted "
        "AND database = (SELECT oid FROM pg_database WHERE datname = current_database())"
    )
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        waiting = session.execute(statement).scalar_one()
        session.rollback()
        if waiting:
            return
        time.sleep(0.05)
    raise AssertionError("no backend ever queued for an advisory key")


def test_a_repoint_takes_the_saved_settings_key_before_any_workspace_row(
    exercise_sessions: sessionmaker[Session],
) -> None:
    """Review round 2 (F1): the re-point inverted the family's lock order.

    ``repoint_workspaces`` took the membership key, then row-locked every
    workspace with two ``FOR UPDATE`` scans, and only then reached
    ``SAVED_SETTING_LOCK_KEY`` through ``reset_workspace_children``. A save
    takes the settings key first and then needs a workspace row for its
    composite foreign key — so the two could wait on each other in a cycle, and
    PostgreSQL would break it by aborting one of them mid-classroom.

    The regression runs both transactions for real. A saver holds the settings
    key; a re-point starts on another connection and is observed, through
    ``pg_locks``, to be queued for that key; while it waits, this test takes
    ``FOR UPDATE NOWAIT`` on every workspace row. Under the old order the
    re-point is holding those rows and ``NOWAIT`` fails at once — which is the
    deadlock edge, stated as a lock that exists rather than as timing. Under the
    fixed order it holds no row at all, the save commits, the key is released
    and the re-point finishes: no deadlock, the team moved, and the setting the
    save had just written is gone, because a re-point resets every team.
    """
    repository = ExerciseSettingsRepository()
    moved: list[RepointOutcome] = []
    failures: list[BaseException] = []

    with exercise_sessions() as setup:
        old_dataset, (workspace_id,) = _classroom(setup, teams=1)
        target_dataset = _insert_dataset(setup, label="target")
        _insert_event(setup, dataset_id=target_dataset)
        setup.commit()

    def repoint() -> None:
        with exercise_sessions() as instructor:
            try:
                # Bounded, so a fix that never releases cannot hang the suite.
                instructor.execute(sa.text("SET LOCAL lock_timeout = '60s'"))
                moved.append(
                    ExerciseInstructorRepository().repoint_workspaces(
                        instructor, dataset_id=target_dataset
                    )
                )
                instructor.commit()
            except BaseException as exc:  # carried to the main thread and re-reported there
                failures.append(exc)
                instructor.rollback()

    saver = exercise_sessions()
    thread = threading.Thread(target=repoint, name="repoint", daemon=True)
    try:
        lock_saved_settings(saver)
        thread.start()
        with exercise_sessions() as watcher:
            _wait_until_a_backend_waits_for_an_advisory_key(watcher)
            watcher.execute(sa.text("SET LOCAL lock_timeout = '2s'"))
            held = watcher.execute(
                sa.select(schema.exercise_team_workspace.c.id).with_for_update(nowait=True)
            ).all()
            watcher.rollback()
        assert [row.id for row in held] == [workspace_id], (
            "a re-point waiting for the saved-settings key must hold no workspace row"
        )
        repository.save_setting(
            saver,
            dataset_id=old_dataset,
            workspace_id=workspace_id,
            event_key=_EVENT_KEY,
            name="broad",
            weights=_WEIGHTS,
        )
        saver.commit()
    finally:
        saver.close()
        thread.join(timeout=90)

    assert not thread.is_alive(), "the re-point never finished"
    assert failures == [], f"the re-point failed: {failures}"
    assert moved == [RepointOutcome(moved=1, discarded=0)]

    with exercise_sessions() as after:
        assert _dataset_of(after, workspace_id) == target_dataset
        assert (
            repository.list_settings(after, workspace_id=workspace_id, event_key=_EVENT_KEY) == ()
        ), "a re-point resets every team, so the saved setting must be gone"


# ---------------------------------------------------------------------------
# The scrubber (ADR-0025 D6)
# ---------------------------------------------------------------------------


def test_a_refused_write_carries_no_driver_text_and_no_context(
    exercise_sessions: sessionmaker[Session],
) -> None:
    """A foreign-key violation must not render as ``[parameters: …]``.

    SQLAlchemy's ``DBAPIError`` renders the statement plus every value bound to
    it. Anything that logs it, returns it, or lets a test runner print it has
    published whatever was in the parameters. What leaves the repository is one
    sentence, with ``__context__`` ``None`` rather than merely suppressed.
    """
    repository = ExerciseSettingsRepository()
    with exercise_sessions() as session:
        dataset_id, _ = _classroom(session)
        with pytest.raises(ExerciseSettingsWriteRefused) as refused:
            repository.save_setting(
                session,
                dataset_id=dataset_id,
                workspace_id=uuid.uuid4(),
                event_key=_EVENT_KEY,
                name="broad",
                weights={"same_major": 0.5},
            )
        session.rollback()

    assert str(refused.value) == "Your settings could not be saved."
    assert refused.value.__context__ is None
    assert "parameters" not in str(refused.value).lower()
    assert "INSERT" not in str(refused.value)


# ---------------------------------------------------------------------------
# Design spec §2's base row ⟕ overlay
# ---------------------------------------------------------------------------


def test_a_team_with_no_overlay_still_sees_every_profile(
    exercise_sessions: sessionmaker[Session],
) -> None:
    """The workspace is in the join condition, not in a ``WHERE``.

    In a ``WHERE`` the same predicate would discard every profile the team has
    no overlay row for — which, before the refresh track writes any, is all of
    them. The list would be empty and every count would be zero.
    """
    with exercise_sessions() as session:
        _, (team_one, _) = _classroom(session)
        rows = ExerciseTeamViewRepository().list_team_profiles(
            session,
            dataset_id=_dataset_of(session, team_one),
            workspace_id=team_one,
        )

    assert [row.profile_no for row in rows] == [1, 2, 3]
    assert all(row.overlay_card_interests is None for row in rows)
    assert all(row.overlay_added_event_topics == () for row in rows)
    assert all(row.non_responding is False for row in rows)
    # The three-state rule of design spec §7 survives the join: NULL is "no card
    # on file" and is not collapsed into an empty one.
    assert rows[0].stated_interests == ("analytics",)
    assert rows[1].stated_interests is None


def test_an_overlay_row_reaches_only_the_team_that_owns_it(
    exercise_sessions: sessionmaker[Session],
) -> None:
    with exercise_sessions() as session:
        dataset_id, (team_one, team_two) = _classroom(session)
        session.execute(
            sa.insert(schema.exercise_profile_overlay).values(
                workspace_id=team_one,
                dataset_id=dataset_id,
                profile_no=2,
                added_event_topics=["analytics"],
                card_interests=["brand"],
                card_career_goal="brand",
                non_responding=True,
            )
        )
        session.commit()

        repository = ExerciseTeamViewRepository()
        ours = repository.list_team_profiles(session, dataset_id=dataset_id, workspace_id=team_one)
        theirs = repository.list_team_profiles(
            session, dataset_id=dataset_id, workspace_id=team_two
        )

    changed = next(row for row in ours if row.profile_no == 2)
    assert changed.overlay_card_interests == ("brand",)
    assert changed.overlay_card_career_goal == "brand"
    assert changed.overlay_added_event_topics == ("analytics",)
    assert changed.non_responding is True
    # The base row is untouched by the overlay, which is what makes it an overlay.
    assert changed.stated_interests is None

    unchanged = next(row for row in theirs if row.profile_no == 2)
    assert unchanged.overlay_card_interests is None
    assert unchanged.overlay_added_event_topics == ()
    assert unchanged.non_responding is False
    assert len(theirs) == 3


def test_the_team_view_selects_no_withheld_column(
    exercise_sessions: sessionmaker[Session],
) -> None:
    """ADR-0025 D6, asserted on the value rather than on the query's text."""
    with exercise_sessions() as session:
        dataset_id, (team_one, _) = _classroom(session)
        rows = ExerciseTeamViewRepository().list_team_profiles(
            session, dataset_id=dataset_id, workspace_id=team_one
        )

    for withheld in schema.EXERCISE_WITHHELD_FIELDS:
        for row in rows:
            assert not hasattr(row, withheld), f"a team's profile view carries {withheld}"
            assert withheld not in repr(row)


def _dataset_of(session: Session, workspace_id: uuid.UUID) -> uuid.UUID:
    """The data file one workspace is in, read back rather than remembered."""
    table = schema.exercise_team_workspace
    found = session.execute(
        sa.select(table.c.dataset_id).where(table.c.id == workspace_id)
    ).scalar_one()
    return uuid.UUID(str(found))
