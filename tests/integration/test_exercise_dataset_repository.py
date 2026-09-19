"""Storing one accepted data file, against a real PostgreSQL.

``tests/unit/test_exercise_ingest.py`` decides what a file may contain; this
file decides what happens to it afterwards, and the three claims it exists for
are all claims a mock would have agreed with while the database disagreed:

* the dataset, its profiles and its events are **one** write — a failure part
  way through leaves nothing behind, counted in all three tables;
* uploading a file **touches no workspace**, which is design spec §3's
  "existing workspaces keep pointing at their old dataset";
* ``hidden_true_interests`` comes back from ``load_simulation_profiles`` and
  from no other read (ADR-0025 D6), because the projection is what enforces
  that and a projection is a database fact.

Every profile here is fictional and obviously so.

Requires a live database; skipped otherwise.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator

import pytest

pytest.importorskip("sqlalchemy")

import sqlalchemy as sa
from smartmatch_domain.exercise.ingest import (
    IngestReport,
    MarkerDistribution,
    ParsedDataset,
    ParsedEvent,
    ParsedProfile,
)
from smartmatch_persistence.exercise.dataset_repository import (
    MAX_SOURCE_FILENAME_CHARACTERS,
    ExerciseDatasetRepository,
    sanitise_source_filename,
)
from smartmatch_persistence.exercise.schema import (
    exercise_dataset,
    exercise_event,
    exercise_profile,
    exercise_team_workspace,
)
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session, sessionmaker

pytestmark = pytest.mark.integration

REPOSITORY = ExerciseDatasetRepository()


def _profile(number: int, **overrides: object) -> ParsedProfile:
    """One fictional profile. The withheld cell carries a distinctive marker."""
    values: dict[str, object] = {
        "profile_no": number,
        "display_name": f"Fictional Profile {number:03d}",
        "major": "Marketing",
        "class_year": "Junior",
        "past_event_keys": ("past-01",),
        "stated_interests": ("data analytics",),
        "career_goal": "Brand manager",
        "hidden_true_interests": (f"secret-interest-{number:03d}",),
    }
    values.update(overrides)
    return ParsedProfile(**values)  # type: ignore[arg-type]


def _events() -> tuple[ParsedEvent, ...]:
    past = tuple(
        ParsedEvent(
            event_key=f"past-{index:02d}",
            name=f"Fictional Event {index:02d}",
            topic_tags=("data analytics",),
            target_majors=("Marketing",),
            is_exercise_event=False,
            sequence=index,
        )
        for index in range(1, 11)
    )
    rounds = tuple(
        ParsedEvent(
            event_key=key,
            name=name,
            topic_tags=("brand strategy",),
            target_majors=("Marketing",),
            is_exercise_event=True,
            sequence=11 + index,
        )
        for index, (key, name) in enumerate(
            (("northline", "Northline Analytics"), ("harbor", "Harbor Consumer Brands"))
        )
    )
    return past + rounds


def _dataset(profiles: tuple[ParsedProfile, ...] | None = None) -> ParsedDataset:
    rows = profiles if profiles is not None else tuple(_profile(n) for n in range(1, 13))
    return ParsedDataset(
        profiles=rows,
        events=_events(),
        checksum="0" * 64,
        row_count=len(rows),
        report=IngestReport(
            profile_count=len(rows),
            event_count=12,
            exercise_event_count=2,
            distinct_class_years=("Junior",),
            profiles_missing_major=0,
            profiles_missing_class_year=0,
            profiles_without_card=0,
            distinct_stated_interest_terms=1,
            distinct_topic_tag_terms=2,
            events_without_topic_tags=0,
            markers=MarkerDistribution(major_only=0, major_plus_events=0, completed_card=len(rows)),
        ),
    )


@pytest.fixture
def session(session_factory: sessionmaker[Session]) -> Iterator[Session]:
    """A session whose exercise rows are removed afterwards, whatever happened.

    Cleanup deletes ``exercise_dataset`` only: every other table in the family
    is ``ON DELETE CASCADE`` from it, which is the same claim
    ``test_exercise_schema_migration.py`` makes about the downgrade.
    """
    with session_factory() as active:
        try:
            yield active
        finally:
            active.rollback()
            active.execute(sa.delete(exercise_dataset))
            active.commit()


def _counts(session: Session) -> tuple[int, int, int]:
    """Rows in the three tables a dataset writes."""
    return tuple(  # type: ignore[return-value]
        session.execute(sa.select(sa.func.count()).select_from(table)).scalar_one()
        for table in (exercise_dataset, exercise_profile, exercise_event)
    )


# ---------------------------------------------------------------------------
# One write
# ---------------------------------------------------------------------------


def test_one_upload_becomes_a_dataset_its_profiles_and_its_events(session: Session) -> None:
    summary = REPOSITORY.create_dataset(
        session, _dataset(), label="Spring practice file", source_filename="ann-sample.csv"
    )
    session.commit()

    assert _counts(session) == (1, 12, 12)
    assert summary.row_count == 12
    assert summary.event_count == 12
    assert summary.checksum == "0" * 64
    assert summary.invite_limit == 30
    assert summary.license_line is None


def test_a_refused_write_leaves_no_row_behind(session: Session) -> None:
    """``ck_exercise_dataset_label_shape`` refuses a 300-character label."""
    with pytest.raises(DBAPIError):
        REPOSITORY.create_dataset(
            session, _dataset(), label="x" * 300, source_filename="ann-sample.csv"
        )
    session.rollback()

    assert _counts(session) == (0, 0, 0)


def test_a_duplicate_profile_number_refuses_the_whole_upload(session: Session) -> None:
    """The parser refuses this first; the primary key is the second line."""
    duplicated = (_profile(1), _profile(1), _profile(2))

    with pytest.raises(DBAPIError):
        REPOSITORY.create_dataset(
            session, _dataset(duplicated), label="Duplicated", source_filename="x.csv"
        )
    session.rollback()

    assert _counts(session) == (0, 0, 0)


def test_creating_a_dataset_leaves_every_workspace_alone(session: Session) -> None:
    """Design spec §3: workspaces keep pointing at their old dataset."""
    first = REPOSITORY.create_dataset(
        session, _dataset(), label="First file", source_filename="first.csv"
    )
    workspace_id = uuid.uuid4()
    session.execute(
        sa.insert(exercise_team_workspace).values(
            id=workspace_id,
            dataset_id=first.dataset_id,
            team_number=3,
            workspace_token_hash=uuid.uuid4().hex,
            seed=12345,
        )
    )
    session.commit()

    REPOSITORY.create_dataset(
        session, _dataset(), label="Replacement file", source_filename="second.csv"
    )
    session.commit()

    workspaces = session.execute(
        sa.select(exercise_team_workspace.c.id, exercise_team_workspace.c.dataset_id)
    ).all()
    assert [(row.id, row.dataset_id) for row in workspaces] == [(workspace_id, first.dataset_id)]


# ---------------------------------------------------------------------------
# Reads
# ---------------------------------------------------------------------------


def test_list_datasets_is_newest_first(session: Session) -> None:
    older = REPOSITORY.create_dataset(session, _dataset(), label="Older", source_filename="a.csv")
    session.commit()
    session.execute(
        sa.update(exercise_dataset)
        .where(exercise_dataset.c.id == older.dataset_id)
        .values(uploaded_at=sa.text("now() - interval '1 day'"))
    )
    newer = REPOSITORY.create_dataset(session, _dataset(), label="Newer", source_filename="b.csv")
    session.commit()

    listed = REPOSITORY.list_datasets(session, limit=10)

    assert [row.dataset_id for row in listed] == [newer.dataset_id, older.dataset_id]


def test_a_summary_read_back_matches_what_was_written(session: Session) -> None:
    summary = REPOSITORY.create_dataset(
        session, _dataset(), label="Round trip", source_filename="c.csv"
    )
    session.commit()

    assert REPOSITORY.get_dataset_summary(session, dataset_id=summary.dataset_id) == summary
    assert REPOSITORY.get_dataset_summary(session, dataset_id=uuid.uuid4()) is None


def test_the_events_come_back_in_file_order(session: Session) -> None:
    summary = REPOSITORY.create_dataset(
        session, _dataset(), label="Events", source_filename="d.csv"
    )
    session.commit()

    events = REPOSITORY.list_events(session, dataset_id=summary.dataset_id)

    assert [event.sequence for event in events] == list(range(1, 13))
    assert [event.event_key for event in events][-2:] == ["northline", "harbor"]
    assert sum(1 for event in events if event.is_exercise_event) == 2


def test_no_card_on_file_stays_different_from_an_empty_card(session: Session) -> None:
    """Design spec §7's three states survive the round trip."""
    profiles = (
        _profile(1, stated_interests=None),
        _profile(2, stated_interests=()),
        _profile(3),
    )
    summary = REPOSITORY.create_dataset(
        session, _dataset(profiles), label="Cards", source_filename="e.csv"
    )
    session.commit()

    stored = REPOSITORY.list_profiles(session, dataset_id=summary.dataset_id, limit=10)

    assert [row.stated_interests for row in stored] == [None, (), ("data analytics",)]


# ---------------------------------------------------------------------------
# ADR-0025 D6
# ---------------------------------------------------------------------------


def test_the_public_profile_read_cannot_carry_the_withheld_column(session: Session) -> None:
    summary = REPOSITORY.create_dataset(
        session, _dataset(), label="Withheld", source_filename="f.csv"
    )
    session.commit()

    rows = REPOSITORY.list_profiles(session, dataset_id=summary.dataset_id, limit=500)

    assert len(rows) == 12
    assert all(not hasattr(row, "hidden_true_interests") for row in rows)
    assert "secret-interest" not in repr(rows)
    assert "secret-interest" not in repr(summary)


def test_the_simulation_loader_is_the_one_read_that_sees_it(session: Session) -> None:
    summary = REPOSITORY.create_dataset(
        session, _dataset(), label="Simulation", source_filename="g.csv"
    )
    session.commit()

    rows = REPOSITORY.load_simulation_profiles(session, dataset_id=summary.dataset_id)

    assert [row.profile_no for row in rows] == list(range(1, 13))
    assert rows[0].hidden_true_interests == ("secret-interest-001",)


def test_the_withheld_column_is_stored_even_though_no_screen_reads_it(session: Session) -> None:
    summary = REPOSITORY.create_dataset(
        session, _dataset(), label="Stored", source_filename="h.csv"
    )
    session.commit()

    stored = session.execute(
        sa.select(exercise_profile.c.hidden_true_interests)
        .where(exercise_profile.c.dataset_id == summary.dataset_id)
        .order_by(exercise_profile.c.profile_no)
        .limit(1)
    ).scalar_one()

    assert stored == ["secret-interest-001"]


# ---------------------------------------------------------------------------
# The uploaded file's name
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("given", "expected"),
    [
        ("ann-sample.csv", "ann-sample.csv"),
        ("/etc/passwd", "passwd"),
        (r"C:\Users\Ann\Desktop\data.csv", "data.csv"),
        ("../../secrets.csv", "secrets.csv"),
        ("..", "(unnamed upload)"),
        ("", "(unnamed upload)"),
        (None, "(unnamed upload)"),
        ("x" * 400, "x" * MAX_SOURCE_FILENAME_CHARACTERS),
    ],
)
def test_an_uploaded_name_is_reduced_to_a_bounded_basename(
    given: str | None, expected: str
) -> None:
    assert sanitise_source_filename(given) == expected


def test_the_stored_filename_is_the_sanitised_one(session: Session) -> None:
    summary = REPOSITORY.create_dataset(
        session, _dataset(), label="Path", source_filename="../../../etc/ann.csv"
    )
    session.commit()

    assert summary.source_filename == "ann.csv"
