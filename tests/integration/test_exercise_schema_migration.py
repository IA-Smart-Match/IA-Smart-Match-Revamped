"""What migration ``0037`` builds, proved against a real PostgreSQL.

``tests/unit/test_exercise_schema.py`` holds the *mirror* to ADR-0025 D2 and
D6 without a database, and ``test_schema_matches_migration.py`` proves the
mirror and the migration agree. Neither proves what the database actually
refuses. The three rules the class exercise turns on are refusals:

* **The one-run rule** (§9). A second results run for the same team and event
  is refused by ``uq_exercise_result_run_workspace_event``, not by an ``if``
  in a handler — so it holds whichever path reaches the table, including a
  retry that arrives twice.
* **Six teams** (§2). ``team_number`` 7 is not a workspace nobody visits; it
  is a row the database will not hold.
* **Tenancy is absent, structurally.** Every foreign key stays inside the
  ``exercise_`` family. Asserted here against the migrated catalogue rather
  than only against the mirror, for the reason
  ``test_every_tenant_scoped_table_is_anchored_by_a_composite_key`` gives
  about its own enumeration: a claim derived from ``schema.py`` disappears
  when ``schema.py`` is the thing that drifted.

And the downgrade: it removes all eight tables, so a developer who runs it
lands on exactly the ``0036`` schema rather than on one with half the exercise
still in it.

Requires a live database and the privilege to create one; skipped otherwise.
"""

from __future__ import annotations

import uuid

import pytest

pytest.importorskip("sqlalchemy")

from migration_harness import alembic, applied_revision, connected, scratch_database
from sqlalchemy import Engine, text
from sqlalchemy.exc import DBAPIError

pytestmark = pytest.mark.integration

#: The revision immediately before the one under test. Read off the
#: ``revision =`` line of ``0036_host_organization.py``, not off a filename:
#: Alembic revision ids are not filenames, and this repository carries the
#: standing proof — ``0024_cba_classification_schema.py`` declares
#: ``revision = "0024_cba_classification"``.
REVISION_BEFORE = "0036_host_organization"

#: The revision under test.
REVISION = "0037_exercise_tables"

#: The current head. ``0038_speaker_availability`` (B26 T2) chains to
#: :data:`REVISION` and creates two ``speaker_availability`` tables; it
#: touches no ``exercise_`` table, so every claim below holds through it.
#: Moved again by B26 T6b-1: ``0039_speaker_portal`` chains to
#: ``0038_speaker_availability``; it touches no ``exercise_`` table either.
#: Moved again by B26 T8a: ``0040_booking_cancellation`` chains to
#: ``0039_speaker_portal`` and is the head. It adds two nullable
#: ``pipeline_record`` columns and writes no rows; it touches no ``exercise_`` table.
#: Moved again by B26 T4: ``0041_batch_speaker_request`` chains to
#: ``0040_booking_cancellation`` and is the head. It adds one nullable
#: ``cba_invitation_batch`` column and backfills only that column, so this
#: file's claims still hold through it.
#: Moved again by CE-DATASET: ``0042_exercise_ann_dataset`` chains to
#: ``0041_batch_speaker_request`` and is the head. It adds two nullable
#: ``exercise_profile`` columns and writes no rows, so this file's claims still
#: hold through it.
#: Moved again by CE-RESULTS-RULE: ``0043_exercise_event_exploratory`` chains to
#: ``0042_exercise_ann_dataset`` and is the head. It adds one boolean
#: ``exercise_event`` column defaulting to false and writes no rows, so this
#: file's claims still hold through it.
HEAD_REVISION = "0043_exercise_event_exploratory"

#: Design spec §2's eight tables.
EXERCISE_TABLES = (
    "exercise_dataset",
    "exercise_profile",
    "exercise_event",
    "exercise_team_workspace",
    "exercise_profile_overlay",
    "exercise_saved_setting",
    "exercise_result_run",
    "exercise_result_unlock",
)


def _insert_dataset(conn, dataset_id: uuid.UUID) -> None:
    conn.execute(
        text(
            "INSERT INTO exercise_dataset (id, label, source_filename, row_count, checksum) "
            "VALUES (:id, 'Scratch dataset', 'scratch.xlsx', 0, 'scratch-checksum')"
        ),
        {"id": dataset_id},
    )


def _insert_event(conn, dataset_id: uuid.UUID, event_key: str, sequence: int) -> None:
    conn.execute(
        text(
            "INSERT INTO exercise_event "
            "(dataset_id, event_key, name, is_exercise_event, sequence) "
            "VALUES (:dataset, :key, :key, true, :sequence)"
        ),
        {"dataset": dataset_id, "key": event_key, "sequence": sequence},
    )


def _insert_workspace(conn, dataset_id: uuid.UUID, team_number: int) -> uuid.UUID:
    workspace_id = uuid.uuid4()
    conn.execute(
        text(
            "INSERT INTO exercise_team_workspace "
            "(id, dataset_id, team_number, workspace_token_hash, seed) "
            "VALUES (:id, :dataset, :team, :hash, 1234567890)"
        ),
        {
            "id": workspace_id,
            "dataset": dataset_id,
            "team": team_number,
            "hash": f"scratch-hash-{workspace_id.hex}",
        },
    )
    return workspace_id


def _result_run_insert() -> str:
    return (
        "INSERT INTO exercise_result_run "
        "(id, workspace_id, dataset_id, event_key, round, email_everyone, seats_empty) "
        "VALUES (:id, :workspace, :dataset, :key, 1, '{}'::jsonb, 52)"
    )


def test_the_upgrade_creates_all_eight_tables(engine: Engine):
    with scratch_database(engine) as url:
        alembic(url, "head", expect_success=True)

        with connected(url) as scratch, scratch.connect() as conn:
            present = {
                row[0]
                for row in conn.execute(
                    text(
                        "SELECT table_name FROM information_schema.tables "
                        "WHERE table_schema = 'public' AND table_name LIKE 'exercise\\_%'"
                    )
                )
            }

        assert present == set(EXERCISE_TABLES)
        assert applied_revision(url) == HEAD_REVISION


def test_no_exercise_table_carries_a_tenancy_column(engine: Engine):
    """ADR-0025 D2, read off the catalogue the migration actually produced."""
    with scratch_database(engine) as url:
        alembic(url, "head", expect_success=True)

        with connected(url) as scratch, scratch.connect() as conn:
            found = conn.execute(
                text(
                    "SELECT table_name, column_name FROM information_schema.columns "
                    "WHERE table_schema = 'public' AND table_name LIKE 'exercise\\_%' "
                    "  AND column_name IN ('tenant_id', 'owning_unit_id', 'user_id')"
                )
            ).all()

    assert not found, f"tenancy columns on exercise tables: {found}"


def test_every_exercise_foreign_key_stays_inside_the_family(engine: Engine):
    """Synthetic rows are never one join from real ones — both directions.

    The second half of the query is the one that matters most and is easiest
    to leave out: a *CBA* table given a key into an exercise table is the same
    failure read from the other end, and nothing about the exercise tables'
    own definitions would catch it.
    """
    query = text(
        "SELECT c.conrelid::regclass::text AS child, c.confrelid::regclass::text AS parent "
        "FROM pg_constraint c "
        "WHERE c.contype = 'f' "
        "  AND (c.conrelid::regclass::text LIKE 'exercise\\_%' "
        "    OR c.confrelid::regclass::text LIKE 'exercise\\_%')"
    )
    with scratch_database(engine) as url:
        alembic(url, "head", expect_success=True)

        with connected(url) as scratch, scratch.connect() as conn:
            pairs = [(row.child, row.parent) for row in conn.execute(query)]

    assert pairs, "no foreign keys found at all — the query is wrong, not the schema"
    strays = [
        pair
        for pair in pairs
        if not (pair[0].startswith("exercise_") and pair[1].startswith("exercise_"))
    ]
    assert not strays, f"foreign keys crossing the exercise boundary: {strays}"


def test_a_second_results_run_for_the_same_team_and_event_is_refused(engine: Engine):
    """§9's one-run rule, as the database enforces it.

    The refusal is what the screen turns into "This team has already run
    results for this event." Enforcing it in the handler alone would leave the
    rule true only for requests that took the path somebody remembered.
    """
    with scratch_database(engine) as url:
        alembic(url, "head", expect_success=True)

        with connected(url) as scratch:
            dataset_id = uuid.uuid4()
            with scratch.begin() as conn:
                _insert_dataset(conn, dataset_id)
                _insert_event(conn, dataset_id, "northline", 11)
                workspace_id = _insert_workspace(conn, dataset_id, 3)
                conn.execute(
                    text(_result_run_insert()),
                    {
                        "id": uuid.uuid4(),
                        "workspace": workspace_id,
                        "dataset": dataset_id,
                        "key": "northline",
                    },
                )

            with pytest.raises(DBAPIError) as raised, scratch.begin() as conn:
                conn.execute(
                    text(_result_run_insert()),
                    {
                        "id": uuid.uuid4(),
                        "workspace": workspace_id,
                        "dataset": dataset_id,
                        "key": "northline",
                    },
                )

        assert applied_revision(url) == HEAD_REVISION

    assert "uq_exercise_result_run_workspace_event" in str(raised.value)


def test_a_seventh_team_is_refused(engine: Engine):
    """§2: teams 1-6. A seventh is a row the database will not hold."""
    with scratch_database(engine) as url:
        alembic(url, "head", expect_success=True)

        with connected(url) as scratch:
            dataset_id = uuid.uuid4()
            with scratch.begin() as conn:
                _insert_dataset(conn, dataset_id)

            with pytest.raises(DBAPIError) as raised, scratch.begin() as conn:
                _insert_workspace(conn, dataset_id, 7)

        assert applied_revision(url) == HEAD_REVISION

    assert "ck_exercise_team_workspace_team_number" in str(raised.value)


def test_two_workspaces_for_one_team_are_refused(engine: Engine):
    """§15 and OQ-CE-08's shared-per-team reading, as a constraint.

    A second tab entering team 3 finds the same workspace because a second
    workspace for team 3 cannot exist.
    """
    with scratch_database(engine) as url:
        alembic(url, "head", expect_success=True)

        with connected(url) as scratch:
            dataset_id = uuid.uuid4()
            with scratch.begin() as conn:
                _insert_dataset(conn, dataset_id)
                _insert_workspace(conn, dataset_id, 3)

            with pytest.raises(DBAPIError) as raised, scratch.begin() as conn:
                _insert_workspace(conn, dataset_id, 3)

        assert applied_revision(url) == HEAD_REVISION

    assert "uq_exercise_team_workspace_dataset_team" in str(raised.value)


def test_the_invite_limit_defaults_to_thirty(engine: Engine):
    """§5, read back from a row nobody gave a limit to."""
    with scratch_database(engine) as url:
        alembic(url, "head", expect_success=True)

        with connected(url) as scratch:
            dataset_id = uuid.uuid4()
            with scratch.begin() as conn:
                _insert_dataset(conn, dataset_id)

            with scratch.connect() as conn:
                limit = conn.execute(
                    text("SELECT invite_limit FROM exercise_dataset WHERE id = :id"),
                    {"id": dataset_id},
                ).scalar_one()

    assert limit == 30


def test_class_year_and_career_goal_carry_no_check(engine: Engine):
    """The vocabularies stay out of DDL, asserted against the catalogue.

    The owner closed them in code (2026-09-24). The unit test reads the mirror;
    this reads ``pg_constraint``, so a vocabulary that reached the database
    through a migration the mirror never learned about would still fail here.
    """
    with scratch_database(engine) as url:
        alembic(url, "head", expect_success=True)

        with connected(url) as scratch, scratch.connect() as conn:
            expressions = [
                row[0]
                for row in conn.execute(
                    text(
                        "SELECT pg_get_constraintdef(c.oid) FROM pg_constraint c "
                        "WHERE c.contype = 'c' "
                        "  AND c.conrelid = 'exercise_profile'::regclass"
                    )
                )
            ]

    for expression in expressions:
        assert "class_year" not in expression, expression
        assert "career_goal" not in expression, expression


def test_the_downgrade_removes_every_exercise_table(engine: Engine):
    """A development tool, and it has to leave the ``0036`` schema behind.

    Half a downgrade is worse than none: a leftover ``exercise_dataset`` would
    make the next upgrade fail on a table that already exists, and the error
    would name the table rather than the rollback that left it.
    """
    with scratch_database(engine) as url:
        alembic(url, "head", expect_success=True)
        alembic(url, REVISION_BEFORE, expect_success=True, command="downgrade")

        with connected(url) as scratch, scratch.connect() as conn:
            remaining = [
                row[0]
                for row in conn.execute(
                    text(
                        "SELECT table_name FROM information_schema.tables "
                        "WHERE table_schema = 'public' AND table_name LIKE 'exercise\\_%'"
                    )
                )
            ]

        assert remaining == []
        assert applied_revision(url) == REVISION_BEFORE

        # And the schema it lands on still upgrades, which is the claim a
        # downgrade is actually used for.
        alembic(url, "head", expect_success=True)
        assert applied_revision(url) == HEAD_REVISION
