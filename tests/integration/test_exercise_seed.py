"""The exercise seed against a real PostgreSQL (CE-SEED, owner design "A", 2026-09-25).

The database comes first; Ann's fixture file is the fallback that fills an
empty one. Every claim below is a claim about rows, so a mock would have agreed
with all of them while the database disagreed:

* an empty database is seeded, and the seeded file is the active one;
* a second run is a no-op — one dataset, not two;
* a dataset the instructor uploaded is left exactly as it was;
* ``--force`` adds a dataset and deletes none;
* a file the parser refuses stores nothing;
* the command prints counts, never a withheld column (ADR-0025 D6);
* the start-up hook, allowed by its guard, seeds the same way.

Runs against its own scratch database, migrated to head once for the module and
dropped afterwards, because every test here starts from an empty
``exercise_dataset`` table and a developer's own database is not empty.
Skipped where no PostgreSQL is reachable.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest

pytest.importorskip("sqlalchemy")

import sqlalchemy as sa
from migration_harness import alembic, connected, scratch_database
from smartmatch_api.config import Settings
from smartmatch_api.exercise_seed import main, seed_exercise_dataset, seed_on_start
from smartmatch_domain.exercise import EXERCISE_WITHHELD_FIELDS
from smartmatch_domain.exercise.ingest import ParsedDataset
from smartmatch_persistence.exercise import schema
from smartmatch_persistence.exercise.dataset_repository import ExerciseDatasetRepository
from smartmatch_persistence.exercise.workspace_repository import active_dataset
from sqlalchemy import Engine
from sqlalchemy.orm import Session, sessionmaker

from tests.unit.exercise_workbooks import ANN_FULL_FILE, ANN_SAMPLE_FILE

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def scratch_url(engine: Engine) -> Iterator[sa.engine.URL]:
    """One scratch database for the module, migrated to head once."""
    with scratch_database(engine) as url:
        alembic(url, "head", expect_success=True)
        yield url


@pytest.fixture
def sessions(scratch_url: sa.engine.URL) -> Iterator[sessionmaker[Session]]:
    """A session factory over the scratch database, emptied before each test."""
    with connected(scratch_url) as scratch:
        factory = sessionmaker(bind=scratch, expire_on_commit=False, future=True)
        with factory() as session:
            session.execute(sa.delete(schema.exercise_dataset))
            session.commit()
        yield factory


def _dataset_labels(sessions: sessionmaker[Session]) -> list[str]:
    with sessions() as session:
        return list(
            session.execute(
                sa.select(schema.exercise_dataset.c.label).order_by(
                    schema.exercise_dataset.c.uploaded_at, schema.exercise_dataset.c.id
                )
            ).scalars()
        )


def _count(sessions: sessionmaker[Session], table: sa.Table) -> int:
    with sessions() as session:
        return int(session.execute(sa.select(sa.func.count()).select_from(table)).scalar_one())


def _seed(sessions: sessionmaker[Session], *, force: bool = False) -> object:
    with sessions() as session:
        return seed_exercise_dataset(
            session,
            ANN_FULL_FILE.read_bytes(),
            source_filename=ANN_FULL_FILE.name,
            force=force,
        )


def test_an_empty_database_is_seeded_and_the_seed_is_active(
    sessions: sessionmaker[Session], ann_full_dataset: ParsedDataset
) -> None:
    outcome = _seed(sessions)

    assert getattr(outcome, "seeded", None) is True
    assert _count(sessions, schema.exercise_dataset) == 1
    assert _count(sessions, schema.exercise_profile) == len(ann_full_dataset.profiles)
    assert _count(sessions, schema.exercise_event) == len(ann_full_dataset.events)
    with sessions() as session:
        active = active_dataset(session)
    assert active is not None
    assert _dataset_labels(sessions) == [active.label]


def test_a_second_run_is_a_no_op(sessions: sessionmaker[Session]) -> None:
    _seed(sessions)

    outcome = _seed(sessions)

    assert getattr(outcome, "seeded", None) is False
    assert _count(sessions, schema.exercise_dataset) == 1


def test_an_instructor_upload_is_left_untouched(
    sessions: sessionmaker[Session], ann_full_dataset: ParsedDataset
) -> None:
    with sessions() as session:
        uploaded = ExerciseDatasetRepository().create_dataset(
            session, ann_full_dataset, label="Monday's class", source_filename="monday.xlsx"
        )
        session.commit()

    outcome = _seed(sessions)

    assert getattr(outcome, "seeded", None) is False
    assert _dataset_labels(sessions) == ["Monday's class"]
    with sessions() as session:
        active = active_dataset(session)
    assert active is not None
    assert active.id == uploaded.id


def test_force_adds_a_dataset_and_deletes_none(sessions: sessionmaker[Session]) -> None:
    _seed(sessions)

    outcome = _seed(sessions, force=True)

    assert getattr(outcome, "seeded", None) is True
    labels = _dataset_labels(sessions)
    assert len(labels) == 2
    with sessions() as session:
        active = active_dataset(session)
    assert active is not None
    assert active.label == labels[-1]


# ---------------------------------------------------------------------------
# The command
# ---------------------------------------------------------------------------


def _url(scratch_url: sa.engine.URL) -> str:
    return scratch_url.render_as_string(hide_password=False)


def _withheld_values(dataset: ParsedDataset) -> set[str]:
    """Every value of every withheld cell in Ann's file."""
    values: set[str] = set()
    for profile in dataset.profiles:
        values.update(profile.hidden_true_interests or ())
        if profile.hidden_true_career_goal:
            values.add(profile.hidden_true_career_goal)
    return values


def test_the_command_seeds_then_says_so_in_counts_only(
    sessions: sessionmaker[Session],
    scratch_url: sa.engine.URL,
    ann_full_dataset: ParsedDataset,
    capsys: pytest.CaptureFixture[str],
) -> None:
    first = main([], database_url=_url(scratch_url))
    second = main([], database_url=_url(scratch_url))
    out, err = capsys.readouterr()

    assert (first, second) == (0, 0)
    assert _count(sessions, schema.exercise_dataset) == 1
    lines = out.strip().splitlines()
    assert len(lines) == 2
    assert f"{len(ann_full_dataset.profiles)} profiles" in lines[0]
    assert "nothing seeded" in lines[1]
    printed = out + err
    for field in EXERCISE_WITHHELD_FIELDS:
        assert field not in printed
    for value in _withheld_values(ann_full_dataset):
        assert value not in printed


def test_the_command_force_flag_adds_a_dataset(
    sessions: sessionmaker[Session], scratch_url: sa.engine.URL
) -> None:
    assert main([], database_url=_url(scratch_url)) == 0
    assert main(["--force"], database_url=_url(scratch_url)) == 0

    assert _count(sessions, schema.exercise_dataset) == 2


def test_the_command_file_flag_reads_another_file_and_a_refusal_stores_nothing(
    sessions: sessionmaker[Session],
    scratch_url: sa.engine.URL,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Ann's 20-row sample is below design spec §3's 50-profile floor."""
    code = main(["--file", str(ANN_SAMPLE_FILE)], database_url=_url(scratch_url))
    _, err = capsys.readouterr()

    assert code == 1
    assert "profiles" in err
    assert _count(sessions, schema.exercise_dataset) == 0


def test_the_command_refuses_a_missing_file(
    sessions: sessionmaker[Session],
    scratch_url: sa.engine.URL,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    code = main(["--file", str(tmp_path / "absent.xlsx")], database_url=_url(scratch_url))
    _, err = capsys.readouterr()

    assert code == 1
    assert "absent.xlsx" in err
    assert _count(sessions, schema.exercise_dataset) == 0


# ---------------------------------------------------------------------------
# On start
# ---------------------------------------------------------------------------


def test_the_start_up_hook_seeds_an_empty_database_once(
    sessions: sessionmaker[Session],
) -> None:
    allowed = Settings(
        edition="dev",  # type: ignore[arg-type]
        product_scope="class_exercise",  # type: ignore[arg-type]
        exercise_seed_on_start=True,
        exercise_cookie_secure=None,
        release="dev",
        database_url="postgresql+psycopg://smartmatch:smartmatch@localhost:5432/smartmatch",
        use_fixture_providers=True,
        email_api_key=None,
        routes_api_key=None,
        dev_principals={},
    )

    seed_on_start(allowed, sessions)
    seed_on_start(allowed, sessions)

    assert _count(sessions, schema.exercise_dataset) == 1
