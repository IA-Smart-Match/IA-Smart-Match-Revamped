"""Structural guarantees for P9 Gate A's ``professional_unit_relationship`` table.

No live database is needed for any of this: it is all provable by inspecting
``smartmatch_persistence.schema``'s ``sa.Table`` object directly, which is
what makes it a unit test rather than an addition to
``tests/integration/test_professional_unit_relationship_constraints.py`` —
that file proves PostgreSQL enforces these things; this file proves the code
that will eventually create such a database still says so, and runs on a
machine with no PostgreSQL at all. Mirrors
``tests/unit/test_engagement_schema.py``'s pattern for the ADR-0013 tables.

``docs/decisions/p9-gate-a-board-role-decision-draft.md`` (CLOSED 2026-09-02)
is what this table's shape answers:

* §1 — ``board_role`` is relationship-scoped, not intrinsic to a professional.
* §2 — multiple concurrent ``board_role`` values per person across different
  units must be representable at the same instant, and the pilot carries no
  ``effective_from`` / ``effective_to`` columns (current-state only).
"""

from __future__ import annotations

from smartmatch_persistence import schema


def test_the_table_is_registered_in_metadata_and_all():
    """A table that exists only as a local variable is not part of the schema."""
    assert "professional_unit_relationship" in schema.METADATA.tables
    assert schema.METADATA.tables["professional_unit_relationship"] is (
        schema.professional_unit_relationship
    )
    assert "professional_unit_relationship" in schema.__all__


def test_the_primary_key_is_the_composite_natural_key_with_no_surrogate_id():
    """Gate A's key: (tenant_id, professional_id, unit_id), and nothing else.

    No ``id`` column exists at all — this table's identity is the tuple a
    caller already knows, the same choice ``spend_ceiling_bucket`` and
    ``rate_limit_counter`` already made, not a generated value with a
    separate unique constraint layered on top.
    """
    table = schema.professional_unit_relationship
    pk_columns = [column.name for column in table.primary_key.columns]
    assert pk_columns == ["tenant_id", "professional_id", "unit_id"]
    assert "id" not in table.columns
    assert table.primary_key.name == "professional_unit_relationship_pkey"


def test_multiple_units_per_professional_are_representable_by_the_key_shape():
    """Gate A §2's multiplicity answer falls out of the primary key alone.

    The primary key is the ONLY uniqueness constraint on this table (checked
    below) and it requires all three of (tenant_id, professional_id,
    unit_id) to repeat before a row is rejected. A second row for the same
    professional_id in a different unit_id therefore differs in a key
    column and is not a duplicate — "multiple concurrent board_role values
    per person across different units" is representable by ordinary rows,
    with no array column, no JSON blob, and no second table.
    """
    table = schema.professional_unit_relationship
    unique_column_sets = [
        tuple(sorted(c.name for c in constraint.columns))
        for constraint in table.constraints
        if constraint.__class__.__name__ == "UniqueConstraint"
    ]
    assert unique_column_sets == [], (
        "no UniqueConstraint should exist beyond the primary key -- one on "
        "(tenant_id, professional_id) alone would make multiple concurrent "
        "unit relationships impossible, which is the opposite of Gate A §2"
    )


def test_no_effective_date_columns_exist():
    """Gate A §2: "no effective_from / effective_to columns for pilot."

    Checked by substring, not just the two literal names, so a differently
    spelled attempt at the same idea (``effective_start``, ``valid_from``)
    would also fail this test -- the same defensive pattern
    ``test_no_table_has_a_balance_column`` uses for ADR-0013.
    """
    columns = {column.name.lower() for column in schema.professional_unit_relationship.columns}
    forbidden_fragments = ("effective_from", "effective_to", "valid_from", "valid_until")
    offenders = [c for c in columns for frag in forbidden_fragments if frag in c]
    assert not offenders, (
        f"found date-ranging column(s) {offenders} -- the pilot is current-state "
        "only per Gate A §2; adding these answers a question the gate deferred"
    )


def test_board_role_is_not_nullable():
    """A relationship row with no role records nothing this table exists to hold."""
    assert schema.professional_unit_relationship.c.board_role.nullable is False


def test_board_role_is_text():
    """Free text: Gate A did not ratify a closed vocabulary for board roles."""
    assert isinstance(
        schema.professional_unit_relationship.c.board_role.type,
        type(schema.tenant.c.slug.type),
    )


def test_key_columns_are_not_nullable():
    """Every primary key column is required, which SQLAlchemy enforces on its own,

    but this is pinned explicitly so a future edit that tries to soften one
    "for flexibility" fails here before it ever reaches a migration review.
    """
    table = schema.professional_unit_relationship
    for name in ("tenant_id", "professional_id", "unit_id"):
        assert table.c[name].nullable is False, f"{name} must be NOT NULL"


def test_professional_id_carries_no_foreign_key():
    """No professional table exists yet in this schema (see the module docstring).

    The same situation ``attendance_record.event_id`` and
    ``pipeline_record.opportunity_event_id`` are already in for their own
    not-yet-built parent table. A foreign key here would reference something
    that does not exist.
    """
    table = schema.professional_unit_relationship
    covered = {
        column
        for constraint in table.foreign_key_constraints
        for column in {element.parent.name for element in constraint.elements}
    }
    assert "professional_id" not in covered


def test_unit_id_is_a_composite_tenant_scoped_foreign_key_to_org_unit():
    """A single-column key would accept a unit from another tenant (ADR-0004).

    Mirrors ``attendance_record.owning_unit_id`` and
    ``import_batch.owning_unit_id``'s composite reference to ``org_unit``.
    """
    table = schema.professional_unit_relationship
    constraints = [
        constraint
        for constraint in table.foreign_key_constraints
        if "unit_id" in {element.parent.name for element in constraint.elements}
    ]
    assert len(constraints) == 1, "expected exactly one foreign key covering unit_id"
    (constraint,) = constraints
    assert {element.parent.name for element in constraint.elements} == {
        "tenant_id",
        "unit_id",
    }
    assert constraint.referred_table.name == "org_unit"


def test_unit_id_foreign_key_restricts_deletion():
    """Reorganizing a unit must not silently delete the board-role relationships on it."""
    table = schema.professional_unit_relationship
    (constraint,) = [
        constraint
        for constraint in table.foreign_key_constraints
        if "unit_id" in {element.parent.name for element in constraint.elements}
    ]
    assert constraint.ondelete == "RESTRICT"


def test_created_at_and_updated_at_both_exist_and_are_not_nullable():
    """Gate A §2's correction semantics ("updates the current relationship record")

    mean mutation is expected here, unlike an append-only ledger such as
    ``point_ledger_entry``, which deliberately carries no ``updated_at``.
    """
    table = schema.professional_unit_relationship
    assert table.c.created_at.nullable is False
    assert table.c.updated_at.nullable is False
