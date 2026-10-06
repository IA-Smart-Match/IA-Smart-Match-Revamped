"""What migration ``0046`` adds so a run keeps its names, proved against PostgreSQL.

``exercise_result_run`` gains ``invited_profiles`` and ``setting_weights``, both
``JSONB NULL``. Runs stored before the revision are backfilled in SQL with what
can honestly be rebuilt:

* the invited names, majors and years, in the stored order — and **no**
  ``rank``, ``marker`` or ``reason``, which depended on the weights and the
  team's view at the moment of the run and cannot be reconstructed;
* the saved setting's weights where a setting of that name still exists for
  that team and event, and ``NULL`` where it was deleted.

No ``CHECK`` is added, which is why
``tests/integration/test_check_constraints.py`` declares nothing new. The
mirror's agreement is ``test_schema_matches_migration.py``'s.
"""

from __future__ import annotations

import json
import uuid

import pytest

pytest.importorskip("sqlalchemy")

from migration_harness import alembic, applied_revision, connected, scratch_database
from sqlalchemy import Connection, Engine, text

pytestmark = pytest.mark.integration

#: Read off the ``revision =`` line of ``0045_exercise_result_unlock_closed_at.py``.
REVISION_BEFORE = "0045_exercise_unlock_closed_at"

#: The revision under test. Read off the ``revision =`` line of
#: ``0046_exercise_result_run_snapshot.py``.
REVISION = "0046_exercise_run_snapshot"

_EVENT_KEY = "E11"
_COLUMNS = ("invited_profiles", "setting_weights")
_WEIGHTS = {"same_major": 0.5, "stated_interest_overlap": 0.5}


def _classroom(conn: Connection) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID]:
    """A data file with three profiles and one event, and two teams on it."""
    dataset_id = uuid.uuid4()
    conn.execute(
        text(
            "INSERT INTO exercise_dataset (id, label, source_filename, row_count, checksum) "
            "VALUES (:id, 'Scratch dataset', 'scratch.xlsx', 3, 'scratch-checksum')"
        ),
        {"id": dataset_id},
    )
    conn.execute(
        text(
            "INSERT INTO exercise_event (dataset_id, event_key, name, sequence, is_exercise_event) "
            "VALUES (:dataset, :key, 'Fictional event', 11, true)"
        ),
        {"dataset": dataset_id, "key": _EVENT_KEY},
    )
    for profile_no, name, major, year in (
        (1, "Avery Brooks", "Accounting", "Senior"),
        (2, "Bao Nguyen", None, None),
        (3, "Cam Ellis", "Finance", "Junior"),
    ):
        conn.execute(
            text(
                "INSERT INTO exercise_profile "
                "(dataset_id, profile_no, display_name, major, class_year, hidden_true_interests) "
                "VALUES (:dataset, :no, :name, :major, :year, ARRAY['withheld-topic'])"
            ),
            {"dataset": dataset_id, "no": profile_no, "name": name, "major": major, "year": year},
        )
    teams = []
    for team_number in (1, 2):
        workspace_id = uuid.uuid4()
        conn.execute(
            text(
                "INSERT INTO exercise_team_workspace "
                "(id, dataset_id, team_number, workspace_token_hash, seed) "
                "VALUES (:id, :dataset, :team, :hash, 7)"
            ),
            {
                "id": workspace_id,
                "dataset": dataset_id,
                "team": team_number,
                "hash": f"scratch-hash-{team_number}",
            },
        )
        teams.append(workspace_id)
    return dataset_id, teams[0], teams[1]


def _run(
    conn: Connection,
    dataset_id: uuid.UUID,
    workspace_id: uuid.UUID,
    *,
    invited: list[int],
    setting_name: str | None,
) -> None:
    conn.execute(
        text(
            "INSERT INTO exercise_result_run "
            "(id, workspace_id, dataset_id, event_key, round, setting_name, "
            " invited_profile_nos, email_everyone, seats_empty) "
            "VALUES (:id, :workspace, :dataset, :key, 1, :setting, :invited, '{}'::jsonb, 52)"
        ),
        {
            "id": uuid.uuid4(),
            "workspace": workspace_id,
            "dataset": dataset_id,
            "key": _EVENT_KEY,
            "setting": setting_name,
            "invited": invited,
        },
    )


def _saved_setting(
    conn: Connection, dataset_id: uuid.UUID, workspace_id: uuid.UUID, name: str
) -> None:
    conn.execute(
        text(
            "INSERT INTO exercise_saved_setting "
            "(id, workspace_id, dataset_id, event_key, name, weights) "
            "VALUES (:id, :workspace, :dataset, :key, :name, CAST(:weights AS jsonb))"
        ),
        {
            "id": uuid.uuid4(),
            "workspace": workspace_id,
            "dataset": dataset_id,
            "key": _EVENT_KEY,
            "name": name,
            "weights": json.dumps(_WEIGHTS),
        },
    )


def _columns(conn: Connection) -> dict[str, tuple[str, str]]:
    rows = conn.execute(
        text(
            "SELECT column_name, data_type, is_nullable FROM information_schema.columns "
            "WHERE table_schema = 'public' AND table_name = 'exercise_result_run' "
            "AND column_name = ANY(:names)"
        ),
        {"names": list(_COLUMNS)},
    ).all()
    return {row[0]: (row[1], row[2]) for row in rows}


def _snapshot(conn: Connection, workspace_id: uuid.UUID) -> tuple[object, object]:
    row = conn.execute(
        text(
            "SELECT invited_profiles, setting_weights FROM exercise_result_run "
            "WHERE workspace_id = :workspace"
        ),
        {"workspace": workspace_id},
    ).one()
    return row.invited_profiles, row.setting_weights


def test_the_upgrade_backfills_names_in_stored_order_and_invents_no_rank(engine: Engine) -> None:
    """The backfill writes what is on file about each invited profile, and stops there."""
    with scratch_database(engine) as url:
        alembic(url, REVISION_BEFORE, expect_success=True)
        with connected(url) as scratch:
            with scratch.begin() as conn:
                dataset_id, kept_team, deleted_team = _classroom(conn)
                # Stored out of number order on purpose: the order kept is the
                # array's own, whatever it is.
                _run(conn, dataset_id, kept_team, invited=[3, 1, 2], setting_name="Wide net")
                _saved_setting(conn, dataset_id, kept_team, "Wide net")
                _saved_setting(conn, dataset_id, kept_team, "Another one")
                # This team's setting was deleted before the upgrade.
                _run(conn, dataset_id, deleted_team, invited=[2], setting_name="Gone")

            alembic(url, REVISION, expect_success=True)
            assert applied_revision(url) == REVISION

            with scratch.connect() as conn:
                assert _columns(conn) == {name: ("jsonb", "YES") for name in _COLUMNS}
                names, weights = _snapshot(conn, kept_team)
                orphan_names, orphan_weights = _snapshot(conn, deleted_team)

    assert names == [
        {"profile_no": 3, "display_name": "Cam Ellis", "major": "Finance", "class_year": "Junior"},
        {
            "profile_no": 1,
            "display_name": "Avery Brooks",
            "major": "Accounting",
            "class_year": "Senior",
        },
        {"profile_no": 2, "display_name": "Bao Nguyen", "major": None, "class_year": None},
    ]
    for entry in (*names, *orphan_names):
        assert set(entry) == {"profile_no", "display_name", "major", "class_year"}, (
            "rank, marker and reason cannot be rebuilt and must stay absent"
        )
    assert "withheld-topic" not in json.dumps([names, orphan_names])
    assert weights == _WEIGHTS, "the setting of that name, where it survives"
    assert orphan_names == [
        {"profile_no": 2, "display_name": "Bao Nguyen", "major": None, "class_year": None}
    ]
    assert orphan_weights is None, "a deleted setting leaves the weights unrecorded"


def test_a_run_with_nobody_invited_is_left_without_a_snapshot(engine: Engine) -> None:
    """An empty array aggregates to no row at all, so the column stays ``NULL``."""
    with scratch_database(engine) as url:
        alembic(url, REVISION_BEFORE, expect_success=True)
        with connected(url) as scratch:
            with scratch.begin() as conn:
                dataset_id, team, _other = _classroom(conn)
                _run(conn, dataset_id, team, invited=[], setting_name=None)

            alembic(url, REVISION, expect_success=True)

            with scratch.connect() as conn:
                assert _snapshot(conn, team) == (None, None)


def test_the_downgrade_removes_both_columns_and_the_upgrade_returns_them(engine: Engine) -> None:
    with scratch_database(engine) as url:
        alembic(url, REVISION, expect_success=True)
        alembic(url, REVISION_BEFORE, expect_success=True, command="downgrade")
        assert applied_revision(url) == REVISION_BEFORE
        with connected(url) as scratch, scratch.connect() as conn:
            assert _columns(conn) == {}

        alembic(url, REVISION, expect_success=True)
        with connected(url) as scratch, scratch.connect() as conn:
            assert _columns(conn) == {name: ("jsonb", "YES") for name in _COLUMNS}
