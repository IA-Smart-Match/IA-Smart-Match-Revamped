"""What migration ``0042`` adds for Ann's data file, proved against PostgreSQL.

``exercise_profile`` gains ``tiebreak_order`` (positive, unique within a
dataset, nullable for a dataset stored before this revision) and the withheld
``hidden_true_career_goal``. The claims below are the refusals and the
round trip; the mirror's agreement is ``test_schema_matches_migration.py``'s.
"""

from __future__ import annotations

import uuid

import pytest

pytest.importorskip("sqlalchemy")

from migration_harness import alembic, applied_revision, connected, scratch_database
from sqlalchemy import Engine, text
from sqlalchemy.exc import IntegrityError

pytestmark = pytest.mark.integration

#: Read off the ``revision =`` line of ``0041_invitation_batch_speaker_request.py``.
REVISION_BEFORE = "0041_batch_speaker_request"

#: The revision under test. Read off the ``revision =`` line of
#: ``0042_exercise_ann_dataset.py``.
REVISION = "0042_exercise_ann_dataset"

_CHECK = "ck_exercise_profile_tiebreak_order"
_UNIQUE = "uq_exercise_profile_tiebreak_order"


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


def _profile(conn, dataset_id: uuid.UUID, number: int, **extra: object) -> None:
    columns = ", ".join(("dataset_id", "profile_no", "display_name", *extra))
    values = ", ".join((":dataset", ":number", ":name", *(f":{key}" for key in extra)))
    conn.execute(
        text(f"INSERT INTO exercise_profile ({columns}) VALUES ({values})"),
        {"dataset": dataset_id, "number": number, "name": f"Fictional {number}", **extra},
    )


def _columns(conn) -> set[str]:
    return {
        row[0]
        for row in conn.execute(
            text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_schema = 'public' AND table_name = 'exercise_profile'"
            )
        )
    }


def _constraints(conn) -> set[str]:
    return {
        row[0]
        for row in conn.execute(
            text("SELECT conname FROM pg_constraint WHERE conrelid = 'exercise_profile'::regclass")
        )
    }


def test_the_upgrade_adds_both_columns_and_keeps_existing_rows(engine: Engine) -> None:
    """A dataset stored before 0042 survives it, with both new columns NULL."""
    with scratch_database(engine) as url:
        alembic(url, REVISION_BEFORE, expect_success=True)
        with connected(url) as scratch:
            with scratch.begin() as conn:
                dataset_id = _dataset(conn)
                _profile(conn, dataset_id, 1)
                _profile(conn, dataset_id, 2)

            alembic(url, REVISION, expect_success=True)
            assert applied_revision(url) == REVISION

            with scratch.connect() as conn:
                assert {"tiebreak_order", "hidden_true_career_goal"} <= _columns(conn)
                assert {_CHECK, _UNIQUE} <= _constraints(conn)
                rows = conn.execute(
                    text(
                        "SELECT tiebreak_order, hidden_true_career_goal FROM exercise_profile "
                        "WHERE dataset_id = :dataset"
                    ),
                    {"dataset": dataset_id},
                ).all()
    assert [tuple(row) for row in rows] == [(None, None), (None, None)]


def test_a_place_in_the_fixed_order_is_positive(engine: Engine) -> None:
    with scratch_database(engine) as url:
        alembic(url, REVISION, expect_success=True)
        with connected(url) as scratch:
            with scratch.begin() as conn:
                dataset_id = _dataset(conn)
            with pytest.raises(IntegrityError, match=_CHECK), scratch.begin() as conn:
                _profile(conn, dataset_id, 1, tiebreak_order=0)


def test_two_profiles_of_one_dataset_may_not_share_a_place(engine: Engine) -> None:
    with scratch_database(engine) as url:
        alembic(url, REVISION, expect_success=True)
        with connected(url) as scratch:
            with scratch.begin() as conn:
                dataset_id = _dataset(conn)
                _profile(conn, dataset_id, 1, tiebreak_order=7)
            with pytest.raises(IntegrityError, match=_UNIQUE), scratch.begin() as conn:
                _profile(conn, dataset_id, 2, tiebreak_order=7)


def test_two_datasets_each_have_their_own_order(engine: Engine) -> None:
    with scratch_database(engine) as url:
        alembic(url, REVISION, expect_success=True)
        with connected(url) as scratch, scratch.begin() as conn:
            first, second = _dataset(conn), _dataset(conn)
            _profile(conn, first, 1, tiebreak_order=1)
            _profile(conn, second, 1, tiebreak_order=1)
            _profile(conn, first, 2)
            _profile(conn, first, 3)


def test_the_downgrade_removes_both_and_the_upgrade_returns_them(engine: Engine) -> None:
    with scratch_database(engine) as url:
        alembic(url, REVISION, expect_success=True)
        alembic(url, REVISION_BEFORE, expect_success=True, command="downgrade")
        assert applied_revision(url) == REVISION_BEFORE
        with connected(url) as scratch, scratch.connect() as conn:
            assert not {"tiebreak_order", "hidden_true_career_goal"} & _columns(conn)
            assert not {_CHECK, _UNIQUE} & _constraints(conn)

        alembic(url, REVISION, expect_success=True)
        assert applied_revision(url) == REVISION
