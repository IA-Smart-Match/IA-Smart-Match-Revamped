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

import logging
import os
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
    MAX_LIST_LIMIT,
    MAX_SOURCE_FILENAME_CHARACTERS,
    ExerciseDatasetLabelError,
    ExerciseDatasetRepository,
    ExerciseDatasetWriteError,
    sanitise_source_filename,
)
from smartmatch_persistence.exercise.schema import (
    exercise_dataset,
    exercise_event,
    exercise_profile,
    exercise_team_workspace,
)
from sqlalchemy import Engine
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
            discarded_list_entries=0,
            markers=MarkerDistribution(major_only=0, major_plus_events=0, completed_card=len(rows)),
        ),
    )


#: A database whose name starts with this is one these tests own outright.
#: ``make test-integration`` against a personal database would otherwise hand
#: this file a ``DELETE FROM exercise_dataset`` with no ``WHERE``.
SCRATCH_DATABASE_PREFIX = "smartmatch_scratch"


def _require_a_database_this_file_may_clear(engine: Engine) -> None:
    """Skip unless every ``exercise_dataset`` row here is ours to delete.

    The cleanup below is an unqualified ``DELETE``, which is safe only because
    the exercise family has no tenant column to scope it by — ADR-0025 D2 is
    what removed the scoping every other integration file uses, so the scoping
    has to happen one level up, at the database.

    Two gates rather than one, and the second is not laziness. CI's database
    is named ``smartmatch`` — the *same* name a developer's local database
    carries (``verify.yml``: ``POSTGRES_DB: smartmatch``) — so a prefix check
    alone would silently skip this file on every CI run, which is the failure
    mode that leaves a green tick over tests nobody executed.

    **The second gate is the exact variable, with its exact value.** It was
    ``os.getenv("CI")``, which is truthy for *any* non-empty value of a name
    half the tooling in the world sets: ``CI=1`` in a personal shell profile,
    a Makefile, a container image, or a git hook is enough to turn an
    unqualified ``DELETE`` loose on a developer's own database. That is the
    review follow-up this line carries. ``GITHUB_ACTIONS`` is set to the
    literal ``"true"`` by the one runner that actually owns a throwaway
    database, and comparing the value rather than testing truthiness means an
    empty or accidental setting does not open the gate either.
    """
    name = engine.url.database or ""
    if name.startswith(SCRATCH_DATABASE_PREFIX) or os.environ.get("GITHUB_ACTIONS") == "true":
        return
    pytest.skip(
        f"this file deletes every exercise_dataset row, and {name!r} is neither a "
        f"scratch database (a name starting {SCRATCH_DATABASE_PREFIX!r}) nor a "
        "GitHub Actions runner. Point SMARTMATCH_DATABASE_URL at a database "
        "these tests own."
    )


@pytest.fixture
def session(engine: Engine, session_factory: sessionmaker[Session]) -> Iterator[Session]:
    """A session whose exercise rows are removed afterwards, whatever happened.

    Cleanup deletes ``exercise_dataset`` only: every other table in the family
    is ``ON DELETE CASCADE`` from it, which is the same claim
    ``test_exercise_schema_migration.py`` makes about the downgrade.
    """
    _require_a_database_this_file_may_clear(engine)
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


def test_a_label_the_database_would_refuse_is_refused_before_any_write(
    session: Session,
) -> None:
    """M5: ``ck_exercise_dataset_label_shape`` restated at the boundary.

    Checked in Python *before* the insert, so the instructor gets a sentence
    about the label rather than a write failure about a constraint — and so a
    300-character label never reaches the database at all.
    """
    with pytest.raises(ExerciseDatasetLabelError) as caught:
        REPOSITORY.create_dataset(
            session, _dataset(), label="x" * 300, source_filename="ann-sample.csv"
        )
    session.rollback()

    assert "200" in str(caught.value)
    assert _counts(session) == (0, 0, 0)


@pytest.mark.parametrize("label", ["", "   ", "\t\n"])
def test_a_blank_label_is_refused_with_a_sentence(session: Session, label: str) -> None:
    with pytest.raises(ExerciseDatasetLabelError):
        REPOSITORY.create_dataset(session, _dataset(), label=label, source_filename="a.csv")
    session.rollback()

    assert _counts(session) == (0, 0, 0)


def test_a_duplicate_profile_number_refuses_the_whole_upload(session: Session) -> None:
    """The parser refuses this first; the primary key is the second line."""
    duplicated = (_profile(1), _profile(1), _profile(2))

    with pytest.raises(ExerciseDatasetWriteError):
        REPOSITORY.create_dataset(
            session, _dataset(duplicated), label="Duplicated", source_filename="x.csv"
        )
    session.rollback()

    assert _counts(session) == (0, 0, 0)


def test_a_write_failure_never_carries_the_withheld_column_out_of_the_driver(
    session: Session,
) -> None:
    """H1 — ADR-0025 D6 through the one door nobody writes a line for.

    A ``DBAPIError``'s text embeds ``[parameters: …]``, which for a failed
    profile insert is every value of every row — ``hidden_true_interests``
    included. Re-raising it, logging it, or letting pytest print it would
    publish the withheld column without a single line of code naming it. So
    the driver's exception is swallowed at the repository boundary and
    replaced with one sentence, and this test walks ``str``, ``repr`` and the
    formatted traceback of what comes out.
    """
    import traceback

    duplicated = (_profile(1), _profile(1), _profile(2))

    with pytest.raises(ExerciseDatasetWriteError) as caught:
        REPOSITORY.create_dataset(
            session, _dataset(duplicated), label="Duplicated", source_filename="x.csv"
        )
    session.rollback()

    error = caught.value
    rendered = "".join(traceback.format_exception(error))
    assert error.__context__ is None
    assert error.__cause__ is None
    for text in (str(error), repr(error), rendered):
        assert "secret-interest" not in text
        assert "hidden_true_interests" not in text
    assert _counts(session) == (0, 0, 0)


def test_a_write_failure_logs_only_the_exception_type(
    session: Session, caplog: pytest.LogCaptureFixture
) -> None:
    """The log line that replaces the driver's carries no parameters either."""
    duplicated = (_profile(1), _profile(1))

    logger = "smartmatch_persistence.exercise.dataset_repository"
    with caplog.at_level(logging.WARNING, logger=logger), pytest.raises(ExerciseDatasetWriteError):
        REPOSITORY.create_dataset(
            session, _dataset(duplicated), label="Duplicated", source_filename="x.csv"
        )
    session.rollback()

    logged = "\n".join(record.getMessage() for record in caplog.records)
    assert "IntegrityError" in logged
    assert "secret-interest" not in logged
    assert "Fictional Profile" not in logged


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


@pytest.mark.parametrize("limit", [0, -1, MAX_LIST_LIMIT + 1])
def test_a_read_refuses_a_limit_that_is_not_a_bounded_row_count(
    session: Session, limit: int
) -> None:
    """An unbounded or nonsensical ``LIMIT`` is a caller bug, not a page."""
    with pytest.raises(ValueError, match="limit must be between"):
        REPOSITORY.list_datasets(session, limit=limit)
    with pytest.raises(ValueError, match="limit must be between"):
        REPOSITORY.list_profiles(session, dataset_id=uuid.uuid4(), limit=limit)


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


def test_the_simulation_row_keeps_the_withheld_column_out_of_its_repr(
    session: Session,
) -> None:
    """H2 — the default dataclass ``repr`` is a leak nobody writes a line for.

    ``SimulationProfileRow`` is the one type that carries the withheld column,
    so it is the one type whose ``repr`` would publish it — into a log line, a
    pytest assertion message, or a debugger transcript. The field is excluded
    from the ``repr``; the value is still there to be read deliberately.
    """
    summary = REPOSITORY.create_dataset(session, _dataset(), label="Repr", source_filename="i.csv")
    session.commit()

    rows = REPOSITORY.load_simulation_profiles(session, dataset_id=summary.dataset_id)

    assert rows[0].hidden_true_interests == ("secret-interest-001",)
    assert "secret-interest" not in repr(rows[0])
    assert "secret-interest" not in repr(rows)
    assert "Fictional Profile 001" in repr(rows[0])


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
