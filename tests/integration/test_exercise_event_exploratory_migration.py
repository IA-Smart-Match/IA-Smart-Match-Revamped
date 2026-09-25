"""What migration ``0043`` adds for OQ-CE-14, proved against PostgreSQL.

``exercise_event`` gains ``is_exploratory``: ``BOOLEAN NOT NULL DEFAULT false``.
An event stored before the revision reads ``false``, so a dataset uploaded
before it ranks and simulates exactly as it did. No ``CHECK`` is added, which
is why ``tests/integration/test_check_constraints.py`` declares nothing new.
The mirror's agreement is ``test_schema_matches_migration.py``'s.
"""

from __future__ import annotations

import uuid

import pytest

pytest.importorskip("sqlalchemy")

from migration_harness import alembic, applied_revision, connected, scratch_database
from sqlalchemy import Engine, text
from sqlalchemy.exc import IntegrityError

pytestmark = pytest.mark.integration

#: Read off the ``revision =`` line of ``0042_exercise_ann_dataset.py``.
REVISION_BEFORE = "0042_exercise_ann_dataset"

#: The revision under test. Read off the ``revision =`` line of
#: ``0043_exercise_event_exploratory.py``.
REVISION = "0043_exercise_event_exploratory"


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


def _flags(conn, dataset_id: uuid.UUID) -> list[tuple[str, bool]]:
    rows = conn.execute(
        text(
            "SELECT event_key, is_exploratory FROM exercise_event "
            "WHERE dataset_id = :dataset ORDER BY sequence"
        ),
        {"dataset": dataset_id},
    ).all()
    return [(row[0], row[1]) for row in rows]


def test_the_upgrade_adds_the_flag_false_for_every_event_already_stored(engine: Engine) -> None:
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
                assert "is_exploratory" in _columns(conn)
                assert _flags(conn, dataset_id) == [("E01", False), ("E02", False)]


def test_a_new_event_may_say_it_is_exploratory(engine: Engine) -> None:
    with scratch_database(engine) as url:
        alembic(url, REVISION, expect_success=True)
        with connected(url) as scratch:
            with scratch.begin() as conn:
                dataset_id = _dataset(conn)
                _event(conn, dataset_id, 1, is_exploratory=True)
                _event(conn, dataset_id, 2)
            with scratch.connect() as conn:
                assert _flags(conn, dataset_id) == [("E01", True), ("E02", False)]


def test_the_flag_is_never_null(engine: Engine) -> None:
    with scratch_database(engine) as url:
        alembic(url, REVISION, expect_success=True)
        with connected(url) as scratch:
            with scratch.begin() as conn:
                dataset_id = _dataset(conn)
            with pytest.raises(IntegrityError, match="is_exploratory"), scratch.begin() as conn:
                _event(conn, dataset_id, 1, is_exploratory=None)


def test_the_downgrade_removes_the_flag_and_the_upgrade_returns_it(engine: Engine) -> None:
    with scratch_database(engine) as url:
        alembic(url, REVISION, expect_success=True)
        alembic(url, REVISION_BEFORE, expect_success=True, command="downgrade")
        assert applied_revision(url) == REVISION_BEFORE
        with connected(url) as scratch, scratch.connect() as conn:
            assert "is_exploratory" not in _columns(conn)

        alembic(url, REVISION, expect_success=True)
        with connected(url) as scratch, scratch.connect() as conn:
            assert "is_exploratory" in _columns(conn)
