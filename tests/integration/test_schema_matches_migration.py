"""Assert the hand-written table definitions match the migrated database.

``smartmatch_persistence.schema`` is written by hand rather than reflected,
because the composite tenant-safe keys in v1.1 §2.2 are the point of the schema
and reflection would not reliably preserve them. The cost of writing them by
hand is that they can drift from the migrations that actually shape the
database.

This module is the guard. It compares the code's definitions against a live,
migrated database, so drift fails the build rather than surfacing later as a
confusing runtime error — a missing column shows up here, not as a
``ProgrammingError`` in a request handler.
"""

from __future__ import annotations

import pytest
from smartmatch_persistence import schema
from sqlalchemy import Engine, inspect

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def inspector(engine: Engine):
    return inspect(engine)


def test_every_defined_table_exists(inspector):
    """A table in code but not in the database means a migration is missing."""
    defined = set(schema.METADATA.tables)
    actual = set(inspector.get_table_names())

    missing = defined - actual
    assert not missing, f"defined in code but absent from the database: {sorted(missing)}"


def test_no_migrated_table_is_missing_from_code(inspector):
    """The reverse drift: a migration landed but the code never learned about it.

    ``alembic_version`` is Alembic's own bookkeeping and is deliberately not
    modelled.
    """
    defined = set(schema.METADATA.tables) | {"alembic_version"}
    actual = set(inspector.get_table_names())

    unmodelled = actual - defined
    assert not unmodelled, f"in the database but not defined in code: {sorted(unmodelled)}"


@pytest.mark.parametrize("table_name", sorted(schema.METADATA.tables))
def test_columns_match(inspector, table_name: str):
    """Every column defined in code exists in the database, and vice versa."""
    defined = {column.name for column in schema.METADATA.tables[table_name].columns}
    actual = {column["name"] for column in inspector.get_columns(table_name)}

    assert defined == actual, (
        f"{table_name}: only in code {sorted(defined - actual)}, "
        f"only in database {sorted(actual - defined)}"
    )


@pytest.mark.parametrize(
    "table_name",
    ["membership", "resource_grant", "job_event", "outbox_record", "redrive_record"],
)
def test_tenant_scoped_children_use_composite_foreign_keys(inspector, table_name: str):
    """The isolation guarantee, asserted structurally.

    Every foreign key from a tenant-owned child to a tenant-owned parent must be
    composite and include ``tenant_id``. A single-column key would let a row
    reference a parent in another tenant, which is exactly the class of bug
    v1.1 §2.2 makes impossible at the database layer.
    """
    foreign_keys = inspector.get_foreign_keys(table_name)
    assert foreign_keys, f"{table_name} has no foreign keys at all"

    composite = [fk for fk in foreign_keys if "tenant_id" in fk["constrained_columns"]]
    assert composite, (
        f"{table_name} has no foreign key including tenant_id; a cross-tenant "
        "reference would be accepted by the database"
    )

    for fk in composite:
        assert len(fk["constrained_columns"]) >= 2, (
            f"{table_name}: foreign key {fk['constrained_columns']} includes tenant_id "
            "but is not composite"
        )


def test_job_event_sequence_is_unique_per_job(inspector):
    """SSE reconnect correctness depends on this constraint existing."""
    constraints = {c["name"] for c in inspector.get_unique_constraints("job_event")}
    assert "uq_job_event_sequence" in constraints


def test_outbox_task_name_is_globally_unique(inspector):
    """Deterministic task names only deduplicate if the name is unique."""
    constraints = {c["name"] for c in inspector.get_unique_constraints("outbox_record")}
    assert "uq_outbox_task_name" in constraints


def test_idempotency_scope_constraint_exists(inspector):
    """v1.1 §1.11 requires a defined idempotency-key scope."""
    constraints = {c["name"] for c in inspector.get_unique_constraints("idempotency_record")}
    assert "uq_idempotency_scope" in constraints
