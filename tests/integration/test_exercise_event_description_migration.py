"""What migration ``0044`` adds for #318, proved against PostgreSQL.

``exercise_event`` gains ``description``: nullable ``TEXT`` with no default. An
event stored before the revision reads ``NULL``, so a dataset uploaded before
it shows no description. No ``CHECK`` is added, which is why
``tests/integration/test_check_constraints.py`` declares nothing new. The
mirror's agreement is ``test_schema_matches_migration.py``'s.
"""

from __future__ import annotations

import uuid

import pytest

pytest.importorskip("sqlalchemy")

from migration_harness import alembic, applied_revision, connected, scratch_database
from sqlalchemy import Engine, text

pytestmark = pytest.mark.integration

#: Read off the ``revision =`` line of ``0043_exercise_event_exploratory.py``.
REVISION_BEFORE = "0043_exercise_event_exploratory"

#: The revision under test. Read off the ``revision =`` line of
#: ``0044_exercise_event_description.py``.
REVISION = "0044_exercise_event_description"

#: Longer than the 500 characters any other cell of the file may hold.
LONG_TEXT = "A fictional sixty-minute talk. " * 40


def _dataset(conn) -> uuid.UUID:
    dataset_id = uuid.uuid4()
    conn.execute(
        text(
            "INSERT INTO exercise_dataset (id, label, source_filename, row_count, checksum) "
            "VALUES (:id, 'Scratch dataset', 'scratch.xlsx', 0, 'scratch-checksum')"
        ),
        {"id": dataset_id},
    )
    return dataset_id


def _event(conn, dataset_id: uuid.UUID, sequence: int, **extra: object) -> None:
    columns = ", ".join(("dataset_id", "event_key", "name", "sequence", *extra))
    values = ", ".join((":dataset", ":key", ":name", ":sequence", *(f":{key}" for key in extra)))
    conn.execute(
        text(f"INSERT INTO exercise_event ({columns}) VALUES ({values})"),
        {
            "dataset": dataset_id,
            "key": f"E{sequence:02d}",
            "name": f"Fictional event {sequence}",
            "sequence": sequence,
            **extra,
        },
    )


def _columns(conn) -> set[str]:
    return {
        row[0]
        for row in conn.execute(
            text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_schema = 'public' AND table_name = 'exercise_event'"
            )
        )
    }


def _descriptions(conn, dataset_id: uuid.UUID) -> list[tuple[str, str | None]]:
    rows = conn.execute(
        text(
            "SELECT event_key, description FROM exercise_event "
            "WHERE dataset_id = :dataset ORDER BY sequence"
        ),
        {"dataset": dataset_id},
    ).all()
    return [(row[0], row[1]) for row in rows]


def test_the_upgrade_adds_the_column_null_for_every_event_already_stored(engine: Engine) -> None:
    with scratch_database(engine) as url:
        alembic(url, REVISION_BEFORE, expect_success=True)
        with connected(url) as scratch:
            with scratch.begin() as conn:
                dataset_id = _dataset(conn)
                _event(conn, dataset_id, 1)
                _event(conn, dataset_id, 2)

            alembic(url, REVISION, expect_success=True)
            assert applied_revision(url) == REVISION

            with scratch.connect() as conn:
                assert "description" in _columns(conn)
                assert _descriptions(conn, dataset_id) == [("E01", None), ("E02", None)]


def test_a_new_event_may_carry_a_long_description_or_none(engine: Engine) -> None:
    with scratch_database(engine) as url:
        alembic(url, REVISION, expect_success=True)
        with connected(url) as scratch:
            with scratch.begin() as conn:
                dataset_id = _dataset(conn)
                _event(conn, dataset_id, 1, description=LONG_TEXT)
                _event(conn, dataset_id, 2, description=None)
                _event(conn, dataset_id, 3)
            with scratch.connect() as conn:
                assert _descriptions(conn, dataset_id) == [
                    ("E01", LONG_TEXT),
                    ("E02", None),
                    ("E03", None),
                ]


def test_the_downgrade_removes_the_column_and_the_upgrade_returns_it(engine: Engine) -> None:
    with scratch_database(engine) as url:
        alembic(url, REVISION, expect_success=True)
        alembic(url, REVISION_BEFORE, expect_success=True, command="downgrade")
        assert applied_revision(url) == REVISION_BEFORE
        with connected(url) as scratch, scratch.connect() as conn:
            assert "description" not in _columns(conn)

        alembic(url, REVISION, expect_success=True)
        with connected(url) as scratch, scratch.connect() as conn:
            assert "description" in _columns(conn)
