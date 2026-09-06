"""``job.owning_unit_id``: the column that makes a job scopeable (A5).

Migration ``0006`` gives every job an owning organizational unit, referenced
through the **composite** key ``(tenant_id, owning_unit_id) -> (tenant_id, id)``.
That shape is the whole point and is asserted here rather than assumed: a
single-column reference to ``org_unit.id`` would look identical in a schema
diagram and would let a job in one tenant name a unit in another, which is the
class of bug v1.1 §2.2 makes impossible at the database layer.

Three groups of tests, answering three different questions:

* **What the database now refuses** — a cross-tenant owning unit, and the
  deletion of a unit that still owns work. Both are asserted by attempting the
  write, which proves the constraint does its job rather than that it is present.
* **What the migration does to rows that already exist** — run for real against a
  scratch database stopped at ``0005``, both when every row resolves and when one
  does not. The second is the more important of the two: a backfill that cannot
  resolve a row must stop and say which rows, not default them to something.
* **That a fresh database gets there too**, which is the case CI runs and the
  only one with no data to argue about.
"""

from __future__ import annotations

import uuid

import pytest

pytest.importorskip("sqlalchemy")

from migration_harness import alembic, applied_revision, connected, scratch_database
from smartmatch_persistence.engine import create_session_factory
from smartmatch_persistence.jobs import JobRepository
from sqlalchemy import Engine, text
from sqlalchemy.exc import IntegrityError

pytestmark = pytest.mark.integration

#: The revision immediately before the one under test. A scratch database is
#: brought to here, filled with the rows the backfill has to resolve, and only
#: then asked to continue.
REVISION_BEFORE = "0005_command_payload"

UNIT_PATH = "iawest.cpp.engineering.ie"


# ---------------------------------------------------------------------------
# Helpers that write the pre-migration shapes
# ---------------------------------------------------------------------------


def _insert_tenant(conn, tenant_id: uuid.UUID) -> None:
    conn.execute(
        text("INSERT INTO tenant (id, slug, display_name) VALUES (:id, :slug, :slug)"),
        {"id": tenant_id, "slug": f"scratch-{tenant_id.hex[:12]}"},
    )


def _insert_unit(conn, tenant_id: uuid.UUID, *, path: str = UNIT_PATH) -> uuid.UUID:
    unit_id = uuid.uuid4()
    conn.execute(
        text(
            "INSERT INTO org_unit (id, tenant_id, path, unit_type, display_name) "
            "VALUES (:id, :tid, CAST(:path AS ltree), 'department', 'Scratch')"
        ),
        {"id": unit_id, "tid": tenant_id, "path": path},
    )
    return unit_id


def _insert_pre_0006_job(
    conn,
    tenant_id: uuid.UUID,
    *,
    command_type: str = "import.create",
    payload: str | None = None,
) -> uuid.UUID:
    """Insert a job the way ``0005`` would have, with no owning unit column.

    ``payload`` is passed as JSON text rather than as a dict so a test can write
    the shapes the backfill has to cope with — an absent key, a value that is not
    a UUID — without a driver normalizing them on the way in.
    """
    job_id = uuid.uuid4()
    conn.execute(
        text(
            "INSERT INTO job (id, tenant_id, command_type, status, payload) "
            "VALUES (:id, :tid, :ct, 'queued', CAST(:payload AS jsonb))"
        ),
        {"id": job_id, "tid": tenant_id, "ct": command_type, "payload": payload},
    )
    return job_id


# ---------------------------------------------------------------------------
# What the database refuses, on the dev database at head
# ---------------------------------------------------------------------------


def test_a_job_cannot_name_an_owning_unit_in_another_tenant(engine: Engine, tenant_id: uuid.UUID):
    """The composite key, asserted as the write it refuses.

    This is what a single-column ``owning_unit_id -> org_unit.id`` would have
    permitted: a job in one tenant pointing at a unit in another, after which
    every authorization decision about that job would be made against a path in a
    tree the caller has no relationship to.
    """
    other_tenant = uuid.uuid4()
    with engine.begin() as conn:
        _insert_tenant(conn, other_tenant)
        foreign_unit = _insert_unit(conn, other_tenant, path="elsewhere.dept")

    try:
        with pytest.raises(IntegrityError) as raised, engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO job (id, tenant_id, command_type, status, owning_unit_id) "
                    "VALUES (:id, :tid, 'import.create', 'queued', :unit)"
                ),
                {"id": uuid.uuid4(), "tid": tenant_id, "unit": foreign_unit},
            )
        assert "foreign key" in str(raised.value).lower(), (
            f"the insert was refused by something other than the composite key: {raised.value}"
        )
    finally:
        with engine.begin() as conn:
            conn.execute(text("DELETE FROM job WHERE tenant_id = :t"), {"t": other_tenant})
            conn.execute(text("DELETE FROM org_unit WHERE tenant_id = :t"), {"t": other_tenant})
            conn.execute(text("DELETE FROM tenant WHERE id = :t"), {"t": other_tenant})


def test_deleting_a_unit_that_still_owns_a_job_is_refused(engine: Engine, tenant_id: uuid.UUID):
    """``ON DELETE RESTRICT``, for the same reason ``tenant`` uses it.

    A unit is reorganized far more often than a tenant is deleted, and a
    ``CASCADE`` here would silently delete the audit trail of every command ever
    submitted into that unit. ``RESTRICT`` makes the reorganization a decision
    someone has to take deliberately.
    """
    with engine.begin() as conn:
        unit_id = _insert_unit(conn, tenant_id)
        conn.execute(
            text(
                "INSERT INTO job (id, tenant_id, command_type, status, owning_unit_id) "
                "VALUES (:id, :tid, 'import.create', 'queued', :unit)"
            ),
            {"id": uuid.uuid4(), "tid": tenant_id, "unit": unit_id},
        )

    with pytest.raises(IntegrityError) as raised, engine.begin() as conn:
        conn.execute(text("DELETE FROM org_unit WHERE id = :id"), {"id": unit_id})

    assert "still referenced" in str(raised.value).lower(), (
        f"the delete was refused by something other than RESTRICT: {raised.value}"
    )


def test_owning_unit_id_is_not_nullable(engine: Engine):
    """A job with no owning unit is a job nothing can be scoped against.

    Asserted against the system catalog rather than by attempting a ``NULL``
    insert, because the insert would also be refused by the foreign key and the
    two failures are indistinguishable in the message.
    """
    with engine.connect() as conn:
        nullable = conn.execute(
            text(
                "SELECT is_nullable FROM information_schema.columns "
                "WHERE table_name = 'job' AND column_name = 'owning_unit_id'"
            )
        ).scalar_one()

    assert nullable == "NO"


def test_every_job_row_carries_an_owning_unit(engine: Engine):
    """No row anywhere escaped the backfill.

    Cheap, whole-table, and the only assertion that would catch a backfill that
    resolved the rows it looked at and never looked at some of them.
    """
    with engine.connect() as conn:
        unresolved = conn.execute(
            text("SELECT count(*) FROM job WHERE owning_unit_id IS NULL")
        ).scalar_one()

    assert unresolved == 0


def test_a_created_job_reports_the_unit_it_was_recorded_against(
    engine: Engine, tenant_id: uuid.UUID
):
    """The column the API writes is the column the authorizer reads.

    The full request path is exercised in ``test_command_path.py``; this is the
    narrower claim that ``JobRepository.get`` resolves the stored id back to the
    unit's ``ltree`` path, which is the form :mod:`smartmatch_api.job_authz`
    needs and the reason the read joins ``org_unit`` at all.
    """
    with engine.begin() as conn:
        unit_id = _insert_unit(conn, tenant_id)

    factory = create_session_factory(engine.url.render_as_string(hide_password=False))
    jobs = JobRepository()
    with factory() as session:
        created = jobs.create(
            session,
            tenant_id=tenant_id,
            command_type="import.create",
            owning_unit_id=unit_id,
        )
        session.commit()
        read_back = jobs.get(session, tenant_id=tenant_id, job_id=created.id)

    assert read_back is not None
    assert read_back.owning_unit_id == unit_id
    assert read_back.owning_unit_path == UNIT_PATH, (
        "the tenant-safe join did not return the unit's ltree path as text, which is "
        "what the authorizer needs"
    )


# ---------------------------------------------------------------------------
# The migration itself, run for real
# ---------------------------------------------------------------------------


def test_migrations_apply_cleanly_from_an_empty_database(engine: Engine):
    """The case CI runs, and the only one with no data to argue about.

    Asserts the shape of what ``0006`` built, not merely that Alembic exited
    zero: the column, its nullability, and — the part a single-column key would
    pass — that the foreign key carries ``tenant_id`` and refuses a delete.
    """
    with scratch_database(engine) as url:
        alembic(url, "head", expect_success=True)

        with connected(url) as scratch, scratch.connect() as conn:
            column = conn.execute(
                text(
                    "SELECT is_nullable FROM information_schema.columns "
                    "WHERE table_name = 'job' AND column_name = 'owning_unit_id'"
                )
            ).scalar_one()
            definition = conn.execute(
                text(
                    "SELECT pg_get_constraintdef(oid) FROM pg_constraint "
                    "WHERE conrelid = 'job'::regclass AND contype = 'f' "
                    "AND conname LIKE '%owning_unit%'"
                )
            ).scalar_one()

    assert column == "NO"
    assert "(tenant_id, owning_unit_id) REFERENCES org_unit(tenant_id, id)" in definition, (
        f"the reference is not the composite tenant-safe one: {definition}"
    )
    assert "ON DELETE RESTRICT" in definition, definition


def test_an_existing_0005_database_upgrades_through_0007(engine: Engine):
    """The upgrade path an operator actually takes, with rows in the table.

    Two import jobs in two different tenants, each naming a unit in its own
    tenant. The assertion is not only that they were backfilled but that they
    were backfilled to the *right* unit — a backfill joining on ``id`` alone
    would resolve both to whichever unit happened to match, and with two tenants
    holding one unit each, that is a difference a single-tenant fixture could not
    see.
    """
    first_tenant = uuid.uuid4()
    second_tenant = uuid.uuid4()

    with scratch_database(engine) as url:
        alembic(url, REVISION_BEFORE, expect_success=True)

        with connected(url) as scratch:
            with scratch.begin() as conn:
                _insert_tenant(conn, first_tenant)
                _insert_tenant(conn, second_tenant)
                first_unit = _insert_unit(conn, first_tenant, path="iawest.one")
                second_unit = _insert_unit(conn, second_tenant, path="iawest.two")
                first_job = _insert_pre_0006_job(
                    conn, first_tenant, payload=f'{{"unit_id": "{first_unit}"}}'
                )
                second_job = _insert_pre_0006_job(
                    conn, second_tenant, payload=f'{{"unit_id": "{second_unit}"}}'
                )

            alembic(url, "head", expect_success=True)

            with scratch.connect() as conn:
                owners = dict(conn.execute(text("SELECT id, owning_unit_id FROM job")).all())
                unresolved = conn.execute(
                    text("SELECT count(*) FROM job WHERE owning_unit_id IS NULL")
                ).scalar_one()

        assert unresolved == 0
        assert owners[first_job] == first_unit
        assert owners[second_job] == second_unit
        assert applied_revision(url) != REVISION_BEFORE


def test_the_backfill_refuses_to_run_when_a_row_cannot_be_resolved(engine: Engine):
    """Stop and name the rows, rather than defaulting them to something.

    Three unresolvable shapes at once, because each fails for a different reason
    and a migration that reported only the first would leave an operator
    discovering the other two one deploy at a time:

    * an ``import.create`` job whose ``payload.unit_id`` names a unit in *another*
      tenant — resolvable by id and correctly refused by tenancy;
    * an ``import.create`` job with no payload at all, which is every job written
      before ``0005``;
    * a command type that carries no unit to backfill from, which is what every
      future command resource looks like on the day it first ships.

    What is asserted is the refusal and the *evidence*: the total, and the rows
    named. A migration that raised a bare ``NotNullViolation`` would also refuse,
    and would tell an operator nothing about whether the fix is one row or nine
    hundred.
    """
    tenant = uuid.uuid4()
    other_tenant = uuid.uuid4()

    with scratch_database(engine) as url:
        alembic(url, REVISION_BEFORE, expect_success=True)

        with connected(url) as scratch:
            with scratch.begin() as conn:
                _insert_tenant(conn, tenant)
                _insert_tenant(conn, other_tenant)
                good_unit = _insert_unit(conn, tenant, path="iawest.good")
                foreign_unit = _insert_unit(conn, other_tenant, path="elsewhere.bad")

                resolvable = _insert_pre_0006_job(
                    conn, tenant, payload=f'{{"unit_id": "{good_unit}"}}'
                )
                cross_tenant = _insert_pre_0006_job(
                    conn, tenant, payload=f'{{"unit_id": "{foreign_unit}"}}'
                )
                no_payload = _insert_pre_0006_job(conn, tenant, payload=None)
                other_command = _insert_pre_0006_job(
                    conn, tenant, command_type="match-run.create", payload='{"scope": "all"}'
                )

            failure = alembic(url, "head", expect_success=False).stderr

            assert "3 job row(s)" in failure, failure
            for unresolved_job in (cross_tenant, no_payload, other_command):
                assert str(unresolved_job) in failure, (
                    f"job {unresolved_job} is not named in the failure: {failure}"
                )
            assert "match-run.create" in failure, failure
            assert str(resolvable) not in failure, (
                "a row the backfill resolved is reported as a problem"
            )

            with scratch.connect() as conn:
                surviving = conn.execute(text("SELECT count(*) FROM job")).scalar_one()
                columns = set(
                    conn.execute(
                        text(
                            "SELECT column_name FROM information_schema.columns "
                            "WHERE table_name = 'job'"
                        )
                    ).scalars()
                )

        assert surviving == 4, "the migration deleted rows instead of refusing to run"
        assert "owning_unit_id" not in columns, (
            "the failed migration left its column behind; the revision is transactional "
            "per ADR-0009, so a failure must roll the whole thing back"
        )
        assert applied_revision(url) == REVISION_BEFORE, (
            "the failed migration recorded itself as applied"
        )


def test_the_downgrade_removes_the_column(engine: Engine):
    """A development tool, and one that has to actually work.

    Production rollback never depends on it (v1.1 §4.2), but a downgrade nobody
    has run is a downgrade that does not work, and this is the cheapest place to
    find that out.
    """
    with scratch_database(engine) as url:
        alembic(url, "head", expect_success=True)
        alembic(url, REVISION_BEFORE, expect_success=True, command="downgrade")

        with connected(url) as scratch, scratch.connect() as conn:
            columns = set(
                conn.execute(
                    text(
                        "SELECT column_name FROM information_schema.columns "
                        "WHERE table_name = 'job'"
                    )
                ).scalars()
            )

        assert "owning_unit_id" not in columns
        assert applied_revision(url) == REVISION_BEFORE
