"""What migration ``0045`` adds so results can be closed again, on PostgreSQL.

``exercise_result_unlock`` gains ``closed_at``: ``TIMESTAMPTZ NULL``. A row
stored before the revision reads ``NULL``, which is "still open", so an event
the instructor had opened stays open across the upgrade. No ``CHECK`` is added,
which is why ``tests/integration/test_check_constraints.py`` declares nothing
new. The mirror's agreement is ``test_schema_matches_migration.py``'s.
"""

from __future__ import annotations

import uuid

import pytest

pytest.importorskip("sqlalchemy")

from migration_harness import alembic, applied_revision, connected, scratch_database
from sqlalchemy import Connection, Engine, text

pytestmark = pytest.mark.integration

#: Read off the ``revision =`` line of ``0044_exercise_event_description.py``.
REVISION_BEFORE = "0044_exercise_event_description"

#: The revision under test. Read off the ``revision =`` line of
#: ``0045_exercise_result_unlock_closed_at.py``.
REVISION = "0045_exercise_unlock_closed_at"

_EVENT_KEY = "E11"


def _opened_event(conn: Connection) -> uuid.UUID:
    """One data file, one event, and results opened for it."""
    dataset_id = uuid.uuid4()
    conn.execute(
        text(
            "INSERT INTO exercise_dataset (id, label, source_filename, row_count, checksum) "
            "VALUES (:id, 'Scratch dataset', 'scratch.xlsx', 0, 'scratch-checksum')"
        ),
        {"id": dataset_id},
    )
    conn.execute(
        text(
            "INSERT INTO exercise_event (dataset_id, event_key, name, sequence) "
            "VALUES (:dataset, :key, 'Fictional event', 11)"
        ),
        {"dataset": dataset_id, "key": _EVENT_KEY},
    )
    conn.execute(
        text("INSERT INTO exercise_result_unlock (dataset_id, event_key) VALUES (:dataset, :key)"),
        {"dataset": dataset_id, "key": _EVENT_KEY},
    )
    return dataset_id


def _column(conn: Connection) -> tuple[str, str] | None:
    row = conn.execute(
        text(
            "SELECT data_type, is_nullable FROM information_schema.columns "
            "WHERE table_schema = 'public' AND table_name = 'exercise_result_unlock' "
            "AND column_name = 'closed_at'"
        )
    ).one_or_none()
    return None if row is None else (row[0], row[1])


def test_the_upgrade_adds_an_empty_closed_at_so_an_open_event_stays_open(engine: Engine) -> None:
    with scratch_database(engine) as url:
        alembic(url, REVISION_BEFORE, expect_success=True)
        with connected(url) as scratch:
            with scratch.begin() as conn:
                dataset_id = _opened_event(conn)

            alembic(url, REVISION, expect_success=True)
            assert applied_revision(url) == REVISION

            with scratch.connect() as conn:
                assert _column(conn) == ("timestamp with time zone", "YES")
                stored = conn.execute(
                    text(
                        "SELECT unlocked_at, closed_at FROM exercise_result_unlock "
                        "WHERE dataset_id = :dataset AND event_key = :key"
                    ),
                    {"dataset": dataset_id, "key": _EVENT_KEY},
                ).one()
                assert stored.unlocked_at is not None
                assert stored.closed_at is None


def test_an_event_can_be_closed_and_reopened_on_the_one_row(engine: Engine) -> None:
    with scratch_database(engine) as url:
        alembic(url, REVISION, expect_success=True)
        with connected(url) as scratch:
            with scratch.begin() as conn:
                dataset_id = _opened_event(conn)
                conn.execute(
                    text("UPDATE exercise_result_unlock SET closed_at = now()"),
                )
            with scratch.begin() as conn:
                conn.execute(text("UPDATE exercise_result_unlock SET closed_at = NULL"))
            with scratch.connect() as conn:
                rows = conn.execute(
                    text(
                        "SELECT count(*) FROM exercise_result_unlock "
                        "WHERE dataset_id = :dataset AND closed_at IS NULL"
                    ),
                    {"dataset": dataset_id},
                ).scalar_one()
                assert rows == 1


def test_the_downgrade_removes_the_column_and_the_upgrade_returns_it(engine: Engine) -> None:
    with scratch_database(engine) as url:
        alembic(url, REVISION, expect_success=True)
        alembic(url, REVISION_BEFORE, expect_success=True, command="downgrade")
        assert applied_revision(url) == REVISION_BEFORE
        with connected(url) as scratch, scratch.connect() as conn:
            assert _column(conn) is None

        alembic(url, REVISION, expect_success=True)
        with connected(url) as scratch, scratch.connect() as conn:
            assert _column(conn) == ("timestamp with time zone", "YES")
