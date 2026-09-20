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

import uuid
from collections.abc import Iterator

import pytest

pytest.importorskip("sqlalchemy")

import sqlalchemy as sa
from migration_harness import alembic, connected, scratch_database
from smartmatch_persistence.exercise import schema
from smartmatch_persistence.exercise.settings_repository import (
    MAX_SAVED_SETTINGS_PER_EVENT,
    SAVED_SETTING_LOCK_KEY,
    ExerciseSettingsRepository,
    ExerciseSettingsWriteRefused,
    TooManySavedSettingsError,
)
from smartmatch_persistence.exercise.team_view_repository import ExerciseTeamViewRepository
from smartmatch_persistence.exercise.workspace_repository import ExerciseWorkspaceRepository
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
