"""The instructor page against a real PostgreSQL (CE-INSTRUCTOR, design spec §3, §5, §9).

``tests/unit/test_exercise_instructor_router.py`` proves the routes over a fake
repository. A fake repository cannot prove any of the things below, and every
one of them is a database property:

* **The re-point's order.** The composite foreign keys from the overlay, the
  saved settings and the result runs are ``ON DELETE CASCADE`` and **not**
  ``ON UPDATE CASCADE``, so an ``UPDATE`` of ``dataset_id`` is *refused* while
  a child row exists. A repository that updated first would fail against
  PostgreSQL and pass against a mock. This is the first review follow-up this
  track carries.
* **The collision.** A team can hold a workspace on both the old and the new
  data file, and ``uq_exercise_team_workspace_dataset_team`` admits one per
  file.
* **The idempotent unlock**, which is a primary key rather than a check in
  code.
* **The scrubbed write failure**, which needs a real constraint to violate —
  the second follow-up: the log line names the constraint and the dataset id,
  and the raised exception carries no driver text and no ``__context__``.

Runs against its own scratch database, migrated to head, and dropped
afterwards; skipped where no PostgreSQL is reachable.
"""

from __future__ import annotations

import hashlib
import logging
import uuid
from collections.abc import Iterator

import pytest

pytest.importorskip("sqlalchemy")

import sqlalchemy as sa
from migration_harness import alembic, connected, scratch_database
from smartmatch_domain.exercise import EXERCISE_TEAM_NUMBERS
from smartmatch_persistence.exercise import schema
from smartmatch_persistence.exercise.instructor_repository import (
    MAX_WORKSPACE_LIST_ROWS,
    ExerciseInstructorRepository,
    ExerciseWriteRefused,
)
from smartmatch_persistence.exercise.workspace_repository import (
    WORKSPACE_MEMBERSHIP_LOCK_KEY,
    ExerciseWorkspaceRepository,
)
from sqlalchemy import Engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

pytestmark = pytest.mark.integration

#: Not a real key, assembled from pieces for ``tools/scan_forbidden.py``'s sake.
_SECRET = "-".join(("integration", "only", "exercise", "workspace", "key"))

_EVENT_KEY = "northline"

REPOSITORY = ExerciseInstructorRepository()
WORKSPACES = ExerciseWorkspaceRepository()


@pytest.fixture
def exercise_sessions(engine: Engine) -> Iterator[sessionmaker[Session]]:
    """A session factory over a scratch database migrated to head.

    Its own database rather than the shared development one, because this file
    deletes rows and moves workspaces between data files.
    """
    with scratch_database(engine) as url:
        alembic(url, "head", expect_success=True)
        with connected(url) as scratch:
            yield sessionmaker(bind=scratch, expire_on_commit=False, future=True)


def _insert_dataset(session: Session, *, label: str) -> uuid.UUID:
    """One data file with one profile and one event to hang work off."""
    dataset_id = uuid.uuid4()
    session.execute(
        sa.insert(schema.exercise_dataset).values(
            id=dataset_id,
            label=label,
            source_filename=f"{label}.csv",
            row_count=300,
            checksum=uuid.uuid4().hex,
        )
    )
    session.execute(
        sa.insert(schema.exercise_profile).values(
            dataset_id=dataset_id, profile_no=1, display_name="A made-up person"
        )
    )
    session.execute(
        sa.insert(schema.exercise_event).values(
            dataset_id=dataset_id,
            event_key=_EVENT_KEY,
            name="Northline Analytics",
            sequence=1,
            is_exercise_event=True,
        )
    )
    session.commit()
    return dataset_id


def _give_the_team_some_work(
    session: Session, *, dataset_id: uuid.UUID, workspace_id: uuid.UUID
) -> None:
    """One overlay row, one saved setting and one result run for a workspace.

    All three carry composite foreign keys into the workspace's data file,
    which is what makes the re-point's order observable.
    """
    session.execute(
        sa.insert(schema.exercise_profile_overlay).values(
            workspace_id=workspace_id, dataset_id=dataset_id, profile_no=1
        )
    )
    session.execute(
        sa.insert(schema.exercise_saved_setting).values(
            id=uuid.uuid4(),
            workspace_id=workspace_id,
            dataset_id=dataset_id,
            event_key=_EVENT_KEY,
            name="Wide net",
            weights={"same_major": 0.25},
        )
    )
    session.execute(
        sa.insert(schema.exercise_result_run).values(
            id=uuid.uuid4(),
            workspace_id=workspace_id,
            dataset_id=dataset_id,
            event_key=_EVENT_KEY,
            round=1,
            invited_profile_nos=[1],
            signed_up_profile_nos=[1],
            attended_profile_nos=[],
            email_everyone={},
            seats_empty=52,
        )
    )
    session.commit()


def _enter(session: Session, *, dataset_id: uuid.UUID, team_number: int) -> uuid.UUID:
    workspace = WORKSPACES.get_or_create_workspace(
        session, dataset_id=dataset_id, team_number=team_number, workspace_secret=_SECRET
    )
    session.commit()
    return workspace.id


def _child_counts(session: Session, workspace_id: uuid.UUID) -> tuple[int, int, int]:
    return tuple(  # type: ignore[return-value]
        session.execute(
            sa.select(sa.func.count())
            .select_from(table)
            .where(table.c.workspace_id == workspace_id)
        ).scalar_one()
        for table in (
            schema.exercise_profile_overlay,
            schema.exercise_saved_setting,
            schema.exercise_result_run,
        )
    )


def _dataset_of(session: Session, workspace_id: uuid.UUID) -> uuid.UUID:
    table = schema.exercise_team_workspace
    return uuid.UUID(
        str(
            session.execute(
                sa.select(table.c.dataset_id).where(table.c.id == workspace_id)
            ).scalar_one()
        )
    )


# ---------------------------------------------------------------------------
# The re-point (review follow-up (a))
# ---------------------------------------------------------------------------


def test_a_repoint_moves_a_team_and_deletes_its_work_first(
    exercise_sessions: sessionmaker[Session],
) -> None:
    """The order the schema comment requires, proved rather than trusted.

    If ``dataset_id`` were updated before the children were deleted,
    ``fk_exercise_profile_overlay_workspace`` would refuse the statement and
    this test would raise rather than assert.
    """
    with exercise_sessions() as session:
        old = _insert_dataset(session, label="old-file")
        new = _insert_dataset(session, label="new-file")
        workspace_id = _enter(session, dataset_id=old, team_number=3)
        _give_the_team_some_work(session, dataset_id=old, workspace_id=workspace_id)
        assert _child_counts(session, workspace_id) == (1, 1, 1)

        outcome = REPOSITORY.repoint_workspaces(session, dataset_id=new)
        session.commit()

        assert outcome.moved == 1
        assert outcome.discarded == 0
        assert _dataset_of(session, workspace_id) == new
        assert _child_counts(session, workspace_id) == (0, 0, 0)


def test_a_moved_workspace_keeps_its_id_and_therefore_its_cookie(
    exercise_sessions: sessionmaker[Session],
) -> None:
    """The token is derived from the row's id, so a re-point does not log a team out."""
    table = schema.exercise_team_workspace
    with exercise_sessions() as session:
        old = _insert_dataset(session, label="old-file")
        new = _insert_dataset(session, label="new-file")
        workspace_id = _enter(session, dataset_id=old, team_number=3)
        before = session.execute(
            sa.select(table.c.workspace_token_hash).where(table.c.id == workspace_id)
        ).scalar_one()

        REPOSITORY.repoint_workspaces(session, dataset_id=new)
        session.commit()

        after = session.execute(
            sa.select(table.c.workspace_token_hash).where(table.c.id == workspace_id)
        ).scalar_one()
    assert before == after


def test_a_repoint_regenerates_the_seed_because_it_resets_every_team(
    exercise_sessions: sessionmaker[Session],
) -> None:
    table = schema.exercise_team_workspace
    with exercise_sessions() as session:
        old = _insert_dataset(session, label="old-file")
        new = _insert_dataset(session, label="new-file")
        workspace_id = _enter(session, dataset_id=old, team_number=3)
        before = session.execute(
            sa.select(table.c.seed).where(table.c.id == workspace_id)
        ).scalar_one()

        REPOSITORY.repoint_workspaces(session, dataset_id=new)
        session.commit()

        after = session.execute(
            sa.select(table.c.seed).where(table.c.id == workspace_id)
        ).scalar_one()
    assert before != after


def test_a_stale_workspace_is_discarded_when_the_team_already_entered_on_the_target(
    exercise_sessions: sessionmaker[Session],
) -> None:
    """``uq_exercise_team_workspace_dataset_team`` admits one row per team per file.

    The team's workspace on the *target* file wins, because it is the one whose
    cookie the team is currently holding.
    """
    table = schema.exercise_team_workspace
    with exercise_sessions() as session:
        old = _insert_dataset(session, label="old-file")
        new = _insert_dataset(session, label="new-file")
        stale_id = _enter(session, dataset_id=old, team_number=3)
        current_id = _enter(session, dataset_id=new, team_number=3)
        _give_the_team_some_work(session, dataset_id=old, workspace_id=stale_id)

        outcome = REPOSITORY.repoint_workspaces(session, dataset_id=new)
        session.commit()

        remaining = (
            session.execute(sa.select(table.c.id).where(table.c.team_number == 3)).scalars().all()
        )

    assert outcome.moved == 0
    assert outcome.discarded == 1
    assert [str(row) for row in remaining] == [str(current_id)]
    assert str(stale_id) not in [str(row) for row in remaining]


def test_a_workspace_already_on_the_target_is_left_entirely_alone(
    exercise_sessions: sessionmaker[Session],
) -> None:
    """It is not moved, so it is not reset — a team mid-exercise keeps its work."""
    with exercise_sessions() as session:
        new = _insert_dataset(session, label="new-file")
        workspace_id = _enter(session, dataset_id=new, team_number=4)
        _give_the_team_some_work(session, dataset_id=new, workspace_id=workspace_id)

        outcome = REPOSITORY.repoint_workspaces(session, dataset_id=new)
        session.commit()

        assert outcome == type(outcome)(moved=0, discarded=0)
        assert _child_counts(session, workspace_id) == (1, 1, 1)


def test_a_repoint_resets_every_team_and_not_only_one(
    exercise_sessions: sessionmaker[Session],
) -> None:
    with exercise_sessions() as session:
        old = _insert_dataset(session, label="old-file")
        new = _insert_dataset(session, label="new-file")
        workspaces = [_enter(session, dataset_id=old, team_number=number) for number in (1, 2, 5)]
        for workspace_id in workspaces:
            _give_the_team_some_work(session, dataset_id=old, workspace_id=workspace_id)

        outcome = REPOSITORY.repoint_workspaces(session, dataset_id=new)
        session.commit()

        assert outcome.moved == 3
        for workspace_id in workspaces:
            assert _dataset_of(session, workspace_id) == new
            assert _child_counts(session, workspace_id) == (0, 0, 0)


# ---------------------------------------------------------------------------
# The unlock, the invite limit, the reads
# ---------------------------------------------------------------------------


def test_unlocking_twice_writes_one_row_and_moves_no_timestamp(
    exercise_sessions: sessionmaker[Session],
) -> None:
    table = schema.exercise_result_unlock
    with exercise_sessions() as session:
        dataset_id = _insert_dataset(session, label="unlocking")

        first = REPOSITORY.unlock_results(session, dataset_id=dataset_id, event_key=_EVENT_KEY)
        session.commit()
        stamp = session.execute(sa.select(table.c.unlocked_at)).scalar_one()
        second = REPOSITORY.unlock_results(session, dataset_id=dataset_id, event_key=_EVENT_KEY)
        session.commit()

        rows = session.execute(sa.select(sa.func.count()).select_from(table)).scalar_one()
        after = session.execute(sa.select(table.c.unlocked_at)).scalar_one()

    assert (first, second) == (True, False)
    assert rows == 1
    assert stamp == after


def test_the_event_list_carries_the_unlock_row_and_only_exercise_events(
    exercise_sessions: sessionmaker[Session],
) -> None:
    """CE-INSTRUCTOR-UNLOCK: the panel's state after a reload is this read."""
    with exercise_sessions() as session:
        dataset_id = _insert_dataset(session, label="event-list")
        other_id = _insert_dataset(session, label="event-list-other")
        session.execute(
            sa.insert(schema.exercise_event).values(
                dataset_id=dataset_id,
                event_key="past-one",
                name="A past event",
                sequence=0,
                is_exercise_event=False,
            )
        )
        session.commit()

        before = REPOSITORY.list_exercise_events(session, dataset_id=dataset_id)
        REPOSITORY.unlock_results(session, dataset_id=other_id, event_key=_EVENT_KEY)
        session.commit()
        other_file_only = REPOSITORY.list_exercise_events(session, dataset_id=dataset_id)
        REPOSITORY.unlock_results(session, dataset_id=dataset_id, event_key=_EVENT_KEY)
        session.commit()
        after = REPOSITORY.list_exercise_events(session, dataset_id=dataset_id)

    assert [(row.event_key, row.unlocked) for row in before] == [(_EVENT_KEY, False)]
    assert [row.unlocked for row in other_file_only] == [False]
    assert [(row.event_key, row.name, row.unlocked) for row in after] == [
        (_EVENT_KEY, "Northline Analytics", True)
    ]


def test_an_event_that_is_not_in_the_file_is_recognised_before_the_write(
    exercise_sessions: sessionmaker[Session],
) -> None:
    with exercise_sessions() as session:
        dataset_id = _insert_dataset(session, label="unknown-event")

        assert REPOSITORY.event_exists(session, dataset_id=dataset_id, event_key=_EVENT_KEY)
        assert not REPOSITORY.event_exists(session, dataset_id=dataset_id, event_key="not-an-event")


def test_the_invite_limit_is_written_and_read_back(
    exercise_sessions: sessionmaker[Session],
) -> None:
    table = schema.exercise_dataset
    with exercise_sessions() as session:
        dataset_id = _insert_dataset(session, label="invite-limit")

        assert REPOSITORY.set_invite_limit(session, dataset_id=dataset_id, invite_limit=42)
        session.commit()

        stored = session.execute(
            sa.select(table.c.invite_limit).where(table.c.id == dataset_id)
        ).scalar_one()
    assert stored == 42


def test_an_invite_limit_the_column_would_refuse_is_refused_before_the_write(
    exercise_sessions: sessionmaker[Session],
) -> None:
    with exercise_sessions() as session:
        dataset_id = _insert_dataset(session, label="bad-limit")
        with pytest.raises(ValueError, match="invite_limit must be between"):
            REPOSITORY.set_invite_limit(session, dataset_id=dataset_id, invite_limit=0)


def test_setting_the_limit_on_a_file_that_is_not_there_changes_nothing(
    exercise_sessions: sessionmaker[Session],
) -> None:
    with exercise_sessions() as session:
        _insert_dataset(session, label="present")
        assert not REPOSITORY.set_invite_limit(session, dataset_id=uuid.uuid4(), invite_limit=25)


def test_the_team_list_counts_a_teams_work_without_reading_it(
    exercise_sessions: sessionmaker[Session],
) -> None:
    with exercise_sessions() as session:
        dataset_id = _insert_dataset(session, label="listing")
        workspace_id = _enter(session, dataset_id=dataset_id, team_number=2)
        _give_the_team_some_work(session, dataset_id=dataset_id, workspace_id=workspace_id)

        rows = REPOSITORY.list_workspaces(session, dataset_id=dataset_id)

    assert [row.team_number for row in rows] == [2]
    assert rows[0].saved_setting_count == 1
    assert rows[0].result_run_count == 1
    assert rows[0].dataset_label == "listing"
    assert rows[0].asking_choice is None


def test_a_result_run_is_read_back_as_counts_and_never_as_profile_numbers(
    exercise_sessions: sessionmaker[Session],
) -> None:
    """ADR-0025 D8 as a query: the arrays are counted in SQL, not fetched."""
    with exercise_sessions() as session:
        dataset_id = _insert_dataset(session, label="runs")
        workspace_id = _enter(session, dataset_id=dataset_id, team_number=6)
        _give_the_team_some_work(session, dataset_id=dataset_id, workspace_id=workspace_id)

        runs = REPOSITORY.list_result_runs(session, workspace_id=workspace_id)
        settings = REPOSITORY.list_saved_settings(session, workspace_id=workspace_id)

    assert [(run.invited_count, run.signed_up_count, run.attended_count) for run in runs] == [
        (1, 1, 0)
    ]
    assert runs[0].seats_empty == 52
    assert [setting.name for setting in settings] == ["Wide net"]
    assert not hasattr(runs[0], "invited_profile_nos")
    assert not hasattr(settings[0], "weights")


# ---------------------------------------------------------------------------
# A refused write (review follow-up (b))
# ---------------------------------------------------------------------------


def test_a_failing_child_delete_is_scrubbed_like_every_other_write(
    exercise_sessions: sessionmaker[Session],
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Review follow-up M7: these three deletes used a bare ``session.execute``.

    That quietly contradicted this module's own "the driver's exception never
    escapes" contract — a delete that failed would have raised a ``DBAPIError``
    whose rendering carries ``[parameters: …]``, out of the one module that
    promises it does not do that.

    The failure is produced deterministically by poisoning the transaction
    first: after a statement against a table that does not exist, PostgreSQL
    refuses everything until rollback, so the next delete fails for a reason
    that has nothing to do with this test's timing.
    """
    with exercise_sessions() as session:
        dataset_id = _insert_dataset(session, label="scrubbed-delete")
        workspace_id = _enter(session, dataset_id=dataset_id, team_number=3)

        with pytest.raises(SQLAlchemyError):
            session.execute(sa.text("SELECT 1 FROM a_table_that_does_not_exist"))

        with (
            caplog.at_level(logging.WARNING),
            pytest.raises(ExerciseWriteRefused) as raised,
        ):
            REPOSITORY.reset_workspace_children(
                session, dataset_id=dataset_id, workspace_id=workspace_id
            )
        session.rollback()

    assert str(raised.value) == "That team's work could not be cleared."
    assert "parameters" not in str(raised.value).lower()
    assert raised.value.__context__ is None
    logged = "\n".join(record.getMessage() for record in caplog.records)
    assert str(dataset_id) in logged
    assert "parameters" not in logged.lower()


def test_a_failing_team_reset_is_scrubbed_too(
    exercise_sessions: sessionmaker[Session],
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Review follow-up L4, and the reason the scrubber is a context manager.

    The per-team reset is four statements inside *another* module —
    ``ExerciseWorkspaceRepository.reset_team``, which raises the driver's
    exception as it finds it because its own caller is a team route. An
    instructor route reaching it would otherwise be the one path out of this
    repository that could render ``[parameters: …]``.
    """
    with exercise_sessions() as session:
        dataset_id = _insert_dataset(session, label="scrubbed-reset")
        workspace_id = _enter(session, dataset_id=dataset_id, team_number=3)

        with pytest.raises(SQLAlchemyError):
            session.execute(sa.text("SELECT 1 FROM a_table_that_does_not_exist"))

        with (
            caplog.at_level(logging.WARNING),
            pytest.raises(ExerciseWriteRefused) as raised,
        ):
            REPOSITORY.reset_team(
                session,
                dataset_id=dataset_id,
                workspace_id=workspace_id,
                workspaces=WORKSPACES,
            )
        session.rollback()

    assert raised.value.__context__ is None
    assert "parameters" not in str(raised.value).lower()


def test_a_repoint_holds_a_row_lock_against_a_team_entering_at_the_same_moment(
    exercise_sessions: sessionmaker[Session],
) -> None:
    """Review follow-up M6, proved by a second connection rather than by timing.

    The re-point scans the workspaces it is about to move and the ones already
    on the target file. Without ``FOR UPDATE`` that scan had a window with two
    bad ends, and a classroom is where they happen — the instructor presses
    "re-point" while six laptops are typing their numbers:

    * a team whose ``enter`` committed after the scan and before the update
      stayed on the old file, silently, while the screen said it had moved; or
    * that insert landed on the target for a team already being moved, and the
      update tripped ``uq_exercise_team_workspace_dataset_team``, failing the
      **whole** re-point after some teams had been reset.

    Asserted with ``FOR UPDATE NOWAIT`` from a second connection: it fails
    immediately rather than waiting, so the test is deterministic and cannot
    hang a suite. A lock error is the lock existing; no error would mean the
    re-point had left the rows unprotected.

    **The row it locks is one the re-point only reads** (review finding F1 on
    PR #184). The first version pointed ``NOWAIT`` at the workspace being
    *moved* — a row the re-point ``UPDATE``s, which PostgreSQL locks on its own
    account — so the assertion held whether or not the scan said ``FOR UPDATE``
    and the test passed against the bug it was written for. Team 5's workspace
    is already on the target file: the re-point reads it, to discover that team
    5 is taken, and writes it never. A lock on it is the ``FOR UPDATE`` on the
    target scan and can be nothing else.
    """
    table = schema.exercise_team_workspace
    with exercise_sessions() as writer, exercise_sessions() as other:
        old = _insert_dataset(writer, label="old-file")
        new = _insert_dataset(writer, label="new-file")
        _enter(writer, dataset_id=old, team_number=3)
        read_only_id = _enter(writer, dataset_id=new, team_number=5)

        # Uncommitted on purpose: this is the window the lock has to cover.
        REPOSITORY.repoint_workspaces(writer, dataset_id=new)

        with pytest.raises(SQLAlchemyError) as blocked:
            other.execute(
                sa.select(table.c.id).where(table.c.id == read_only_id).with_for_update(nowait=True)
            )
        other.rollback()
        writer.rollback()

    assert "could not obtain lock" in str(blocked.value).lower()


def test_the_repoint_and_an_entry_take_the_same_advisory_lock(
    exercise_sessions: sessionmaker[Session],
) -> None:
    """Review finding F2 on PR #184: ``FOR UPDATE`` takes no predicate lock.

    The row that breaks a re-point is one that does not exist when the scan
    runs — a team entering at that moment inserts a **new** ``(target file,
    team N)`` row, which no row lock the scan holds can cover, and the
    re-point's own ``UPDATE`` into that pair then trips
    ``uq_exercise_team_workspace_dataset_team`` and aborts the whole
    transaction after teams have already been reset.

    So both sides take one transaction-level advisory lock, and this is that
    claim: while a re-point is open, the key is held, and a second connection
    asking for it without waiting is told no. ``pg_try_advisory_xact_lock``
    rather than a real entry, so the test states the mechanism rather than a
    timing, and cannot hang.
    """
    with exercise_sessions() as writer, exercise_sessions() as other:
        old = _insert_dataset(writer, label="lock-old")
        new = _insert_dataset(writer, label="lock-new")
        _enter(writer, dataset_id=old, team_number=2)

        free_before = other.execute(
            sa.select(sa.func.pg_try_advisory_xact_lock(WORKSPACE_MEMBERSHIP_LOCK_KEY))
        ).scalar_one()
        other.rollback()
        assert free_before is True, "nothing else may be holding the key"

        REPOSITORY.repoint_workspaces(writer, dataset_id=new)

        held = other.execute(
            sa.select(sa.func.pg_try_advisory_xact_lock(WORKSPACE_MEMBERSHIP_LOCK_KEY))
        ).scalar_one()
        other.rollback()
        writer.rollback()

    assert held is False, "a re-point must hold the workspace-membership lock"


def test_an_entry_takes_the_advisory_lock_before_it_inserts(
    exercise_sessions: sessionmaker[Session],
) -> None:
    """The other half of F2: the lock is pointless unless both sides take it."""
    with exercise_sessions() as writer, exercise_sessions() as other:
        dataset_id = _insert_dataset(writer, label="entry-lock")

        WORKSPACES.get_or_create_workspace(
            writer, dataset_id=dataset_id, team_number=4, workspace_secret=_SECRET
        )

        held = other.execute(
            sa.select(sa.func.pg_try_advisory_xact_lock(WORKSPACE_MEMBERSHIP_LOCK_KEY))
        ).scalar_one()
        other.rollback()
        writer.rollback()

    assert held is False, "get_or_create_workspace must hold the lock while it inserts"


def test_the_lock_is_released_by_the_transaction_ending(
    exercise_sessions: sessionmaker[Session],
) -> None:
    """``pg_advisory_xact_lock``: nothing unlocks it, and nothing has to.

    A session-scoped lock left behind by a handler that raised would wedge the
    entry path for every team until the connection was recycled.
    """
    with exercise_sessions() as writer, exercise_sessions() as other:
        dataset_id = _insert_dataset(writer, label="lock-release")
        WORKSPACES.get_or_create_workspace(
            writer, dataset_id=dataset_id, team_number=1, workspace_secret=_SECRET
        )
        writer.rollback()

        free_again = other.execute(
            sa.select(sa.func.pg_try_advisory_xact_lock(WORKSPACE_MEMBERSHIP_LOCK_KEY))
        ).scalar_one()
        other.rollback()

    assert free_again is True


def test_the_lock_key_is_a_stable_signed_bigint() -> None:
    """Derived from the table's name, so it is checkable rather than magic."""
    expected = int.from_bytes(
        hashlib.sha256(b"exercise_team_workspace").digest()[:8], "big", signed=True
    )
    assert expected == WORKSPACE_MEMBERSHIP_LOCK_KEY
    assert -(2**63) <= WORKSPACE_MEMBERSHIP_LOCK_KEY < 2**63


def test_the_team_list_is_capped_and_cuts_at_a_stable_point(
    exercise_sessions: sessionmaker[Session],
) -> None:
    """Review finding F4 on PR #184: ``list_datasets`` was bounded and this was not.

    Asserted with an explicit ``limit`` rather than by writing
    ``MAX_WORKSPACE_LIST_ROWS`` rows, which would be three hundred rows to
    prove an argument reaches a ``LIMIT``. What is checked is that the cap is
    applied, that it cuts at the *front* of the declared order rather than
    wherever the planner happened to stop, and that two reads agree.
    """
    with exercise_sessions() as session:
        dataset_id = _insert_dataset(session, label="capped")
        for team_number in (1, 2, 3, 4):
            _enter(session, dataset_id=dataset_id, team_number=team_number)

        assert len(REPOSITORY.list_workspaces(session)) == 4
        first_two = REPOSITORY.list_workspaces(session, limit=2)
        assert [row.team_number for row in first_two] == [1, 2]
        assert REPOSITORY.list_workspaces(session, limit=2) == first_two

        with pytest.raises(ValueError, match="at least 1"):
            REPOSITORY.list_workspaces(session, limit=0)


def test_the_default_cap_is_the_named_constant(
    exercise_sessions: sessionmaker[Session],
) -> None:
    """The bound is the constant, not a number repeated at a call site."""
    with exercise_sessions() as session:
        dataset_id = _insert_dataset(session, label="default-cap")
        _enter(session, dataset_id=dataset_id, team_number=1)
        assert REPOSITORY.list_workspaces(session) == REPOSITORY.list_workspaces(
            session, limit=MAX_WORKSPACE_LIST_ROWS
        )
    assert len(EXERCISE_TEAM_NUMBERS) <= MAX_WORKSPACE_LIST_ROWS


def test_a_refused_write_logs_the_constraint_and_the_dataset_id_and_nothing_else(
    exercise_sessions: sessionmaker[Session],
    caplog: pytest.LogCaptureFixture,
) -> None:
    """The second review follow-up, and ADR-0025 D6's door in the same breath.

    A real constraint is violated — ``exercise_result_unlock`` names an event
    that is not in the file, so ``fk_exercise_result_unlock_event`` refuses it.
    What must come back is one plain sentence with no driver text; what must be
    logged is the constraint's *name* and the dataset id, both schema rather
    than data; and what must not exist is a ``__context__``, because the
    chained ``DBAPIError`` renders as ``[parameters: …]``.
    """
    with exercise_sessions() as session:
        dataset_id = _insert_dataset(session, label="refused-write")

        with (
            caplog.at_level(logging.WARNING),
            pytest.raises(ExerciseWriteRefused) as raised,
        ):
            REPOSITORY.unlock_results(session, dataset_id=dataset_id, event_key="not-an-event")
        session.rollback()

    message = str(raised.value)
    assert message == "The results for that event could not be unlocked."
    assert "parameters" not in message.lower()
    assert raised.value.__context__ is None

    logged = "\n".join(record.getMessage() for record in caplog.records)
    assert "fk_exercise_result_unlock_event" in logged
    assert str(dataset_id) in logged
    assert "parameters" not in logged.lower()
    assert "not-an-event" not in logged
