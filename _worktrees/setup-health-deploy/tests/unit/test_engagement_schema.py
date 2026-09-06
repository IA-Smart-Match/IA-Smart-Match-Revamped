"""Structural guarantees for ADR-0013's engagement schema (backlog S6/S7/S8).

No live database is needed for any of this: it is all provable by inspecting
``smartmatch_persistence.schema``'s ``sa.Table`` objects directly, which is
what makes it a unit test rather than an addition to
``tests/integration/test_engagement_schema_constraints.py`` — that file proves
PostgreSQL enforces these things; this file proves the code that will
eventually create such a database still says so, and runs on a machine with no
PostgreSQL at all.

Fix #9 (ADR-0013) is that the legacy points balance was a browser formula with
no server-side record. The fix is that a balance is a fold over
``point_ledger_entry``, computed on request, and never stored as a column — on
that table or on any other. ``test_no_table_has_a_balance_column`` is the
guard that keeps that true as the schema grows: it does not name
``point_ledger_entry`` specifically, so a balance column added to some other
table later — the same regression at a different name — fails it too.

Fix #15 is that the legacy rewards catalog named no one who would honour it.
ADR-0013's structural answer is that ``reward_item.budget_owner_id`` and
``reward_item.funded`` are both ``NOT NULL``, so an unowned or unfunded reward
is a row the database refuses rather than a rule a caller could forget to
check. The two tests below pin that in code, independent of whatever
``0009_engagement_schema.py`` actually applies against a live database — so a
future edit that quietly relaxes either column to nullable "for flexibility"
fails here before it ever reaches a migration review.
"""

from __future__ import annotations

from smartmatch_persistence import schema


def test_no_table_has_a_balance_column():
    """ADR-0013: a balance is a fold over the ledger, never a stored column.

    Checked against every table in the schema, not just ``point_ledger_entry``
    — the defect ADR-0013 closes is a *stored balance* existing anywhere, and a
    column named ``balance`` on some unrelated table would be the same defect
    under a different name. Matched case-insensitively and as a substring
    (``student_balance``, ``pointsBalance``) for the same reason.
    """
    offenders = [
        f"{table_name}.{column.name}"
        for table_name, table in schema.METADATA.tables.items()
        for column in table.columns
        if "balance" in column.name.lower()
    ]
    assert not offenders, (
        f"a stored balance column exists: {offenders}. ADR-0013 requires a balance to "
        "be a server-side fold over point_ledger_entry, never a stored counter."
    )


def test_point_ledger_entry_carries_no_mutable_bookkeeping_column():
    """Nothing on this table is a column an application could legitimately ``UPDATE``.

    ADR-0013: "A reversal is a compensating entry, never a delete." The only
    way this table's meaning can change is a new row. ``status``, ``version``,
    and ``updated_at`` are the columns other tables in this schema carry
    specifically to support a later mutation (``review_item.status``,
    ``org_unit.version``, ``job.updated_at``) — their absence here is what
    makes the table's append-only claim structural rather than a comment.
    """
    columns = set(schema.point_ledger_entry.columns.keys())
    mutable_bookkeeping = {"status", "version", "updated_at", "balance"}
    present = columns & mutable_bookkeeping
    assert not present, (
        f"point_ledger_entry carries {sorted(present)}, which invites the mutation "
        "its append-only design is supposed to foreclose"
    )


def test_reward_item_budget_owner_id_is_not_nullable():
    """D6: "a named human budget owner. Without one, the rewards catalog is not shippable."

    ``NOT NULL`` is the structural form of that requirement (ADR-0013's own
    framing) — a schema constraint the database enforces rather than a policy
    a caller could forget. Softening this to nullable "for flexibility" would
    reopen exactly the defect (Fix #15) ADR-0013 closes.
    """
    assert schema.reward_item.c.budget_owner_id.nullable is False


def test_reward_item_funded_is_not_nullable():
    """The other half of D6's structural pair. See the module and migration docstrings."""
    assert schema.reward_item.c.funded.nullable is False


def test_reward_item_budget_owner_is_composite_and_tenant_scoped():
    """A single-column key would accept an owner from another tenant.

    D6's "named human budget owner" only means something if that owner has
    standing in *this* tenant — a composite ``(tenant_id, budget_owner_id)``
    foreign key is what makes a cross-tenant owner impossible to write, the
    same guarantee every other tenant-owned reference in this schema carries
    (ADR-0004).
    """
    constraints = [
        constraint
        for constraint in schema.reward_item.foreign_key_constraints
        if "budget_owner_id" in {element.parent.name for element in constraint.elements}
    ]
    assert len(constraints) == 1, "expected exactly one foreign key covering budget_owner_id"
    (constraint,) = constraints
    assert {element.parent.name for element in constraint.elements} == {
        "tenant_id",
        "budget_owner_id",
    }
    assert constraint.referred_table.name == "user_account"
