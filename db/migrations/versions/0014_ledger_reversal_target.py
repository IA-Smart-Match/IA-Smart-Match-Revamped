"""A compensating ledger entry names the entry it reverses.

Revision ID: 0014_ledger_reversal_target
Revises: 0013_review_decision
Create Date: 2026-09-03

ADR-0013, backlog S7. Closes a defect in the reversal path added alongside
``smartmatch_persistence.rewards`` (task 8, this batch), found in review.

The defect
----------
ADR-0013 §"A reversal is a compensating entry, never a delete" says the
correction is "an offsetting ledger entry that **names what it reverses**"
(``docs/architecture/decisions/ADR-0013-attendance-derived-engagement.md``:69,
restated at ``docs/architecture/engagement-model.md``:99). Migration ``0009``
gave ``point_ledger_entry`` no column capable of doing that, and the repository
written against it carried the original's ``source_attendance_id`` forward as
the only link between the pair.

That is ambiguous exactly when it matters. Nothing constrains
``point_ledger_entry`` to one row per ``attendance_record`` — there is no unique
constraint on ``source_attendance_id``, and ADR-0013's "policies change"
argument for keeping points separate from attendance positively anticipates
several entries deriving from one attendance as the earn policy is revised. Once
two entries share a source, a negative row citing that source names *the
attendance* but not *the entry*, and an auditor asking "which credit was
withdrawn" cannot answer it from the ledger. The evidence plane stayed
append-only and stopped being self-describing, which is most of what the ledger
was for: ADR-0013's case against a counter is that a counter "cannot answer 'why
is my balance this'".

``reverses_entry_id`` — nullable, and that nullability is the rule
-------------------------------------------------------------------
``NULL`` on an ordinary earning entry, set on a compensating one. The column is
therefore not merely permitted to be null; **which of the two it is *defines*
what kind of entry the row is**, which is why it takes no server default in
either direction. There is no safe value to default to: a default of ``NULL``
would silently turn a miswritten reversal into an unexplained debit, and there
is obviously no non-null value to invent. ``smartmatch_domain.rewards``'s
``assert_reversal_target`` refuses both mistakes before a statement is issued —
a reversal with no target, and a non-reversal that names one.

This is additive and **not backfilled**. Every ``point_ledger_entry`` row
existing before this migration gets ``NULL``, which is the correct and honest
value: those rows are earning entries, and no reversal has ever been written by
any code path in this repository (the repository that would write one has no
production caller — ``smartmatch_persistence/rewards.py``'s docstring). Guessing
a target for a historical row would be the fabricated-evidence defect ADR-0011
exists to refuse, and there would be nothing to guess from in any case.

Why ``uq_point_ledger_entry_tenant_id`` arrives here
------------------------------------------------------
Migration ``0009`` deliberately left it out, and said why: "No
``uq_point_ledger_entry_tenant_id``: nothing below this table references it in
this migration … so per 0008's rule for ``review_item``, the constraint is not
added on spec" (``0009_engagement_schema.py``'s docstring). Something now does —
this migration's own foreign key — so the constraint is added by the migration
that creates the reference, which is exactly the rule ``0009`` was following
rather than an exception to it. ``uq_attendance_record_tenant_id`` exists in
``0009`` for the identical reason: ``point_ledger_entry.source_attendance_id``
referenced it.

Why the foreign key is composite
----------------------------------
``(tenant_id, reverses_entry_id) -> (tenant_id, id)``, not a single-column
pointer at ``id``. A single-column key would accept an entry from another
tenant, and a reversal that withdraws a credit belonging to a different
institution is a cross-tenant write in the one table whose whole purpose is to
be trustworthy. This is the same argument ``0009`` gives for
``reward_item.budget_owner_id`` being composite, applied to the same kind of
claim. Because both columns sit on this table, the pair is also literally the
same ``tenant_id`` on both sides of the reference, so the constraint reads as
"within this tenant" rather than merely "consistent with it".

``ON DELETE RESTRICT``, matching every other foreign key ``0009`` declared: a
reversal must not be able to outlive the entry it explains, and no route in this
codebase deletes a ledger row in any case — the table is append-only.

Not added here, deliberately
------------------------------
**No CHECK constraint.** A ``CHECK (id <> reverses_entry_id)`` — refusing a row
that reverses itself — would be correct, but every live CHECK constraint in this
schema must be declared in ``tests/integration/test_check_constraints.py``'s
``CHECK_CONSTRAINT_DEFINITIONS`` and ``BEHAVIOURAL_COVERAGE`` registries
(``test_no_undeclared_check_constraint`` fails otherwise), and that file belongs
to no single track in this batch. The self-reference is refused in application
code instead — and is close to unreachable in any case, since a row's own id
does not exist to be named until after its insert. The gap is recorded in this
batch's task 8 report rather than closed by editing a shared file.

**No index on ``reverses_entry_id``.** Nothing queries by it yet. Added when a
reader needs one, on ``0008``'s rule for constraints not added on spec.

**No ``UPDATE`` path, and no backfill.** The ledger is append-only (ADR-0013).
This migration adds a column to a table and writes no row.

**No database-level append-only guard.** Still absent, still card **L2**, still
reported rather than closed — see
``docs/decisions/d6-rewards-budget-decision-record.md`` §7 check 2. This
migration does not change that either way.

Single transaction, no backfill
---------------------------------
One new nullable column, one unique constraint, one foreign key, on a table that
is empty in every environment this has run against. Nothing to lock for long and
nothing to rewrite, so this is ``0013``'s shape rather than ``0006``'s: no
expand/contract split (v1.1 §4.2, ADR-0009). ``transaction_per_migration=True``
(``db/migrations/env.py``) holds the whole thing in one transaction.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0014_ledger_reversal_target"
down_revision = "0013_review_decision"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add ``reverses_entry_id`` and the composite self-reference it needs."""
    # Deferred by 0009 because nothing referenced it then. This migration's
    # foreign key below is what now does, so it is added by the migration
    # creating the reference — 0009's own stated rule, not an exception to it.
    op.create_unique_constraint(
        "uq_point_ledger_entry_tenant_id",
        "point_ledger_entry",
        ["tenant_id", "id"],
    )

    # Nullable with no server default in either direction: whether this column
    # is null is what makes a row an earning entry or a compensating one, so
    # there is no value that could be defaulted without misstating the row.
    # Existing rows take NULL, which is correct — they are all earning entries,
    # and nothing has ever written a reversal.
    op.add_column(
        "point_ledger_entry",
        sa.Column("reverses_entry_id", postgresql.UUID(as_uuid=True), nullable=True),
    )

    # Composite, so a reversal cannot reach an entry in another tenant — the
    # same argument reward_item.budget_owner_id's composite key makes. RESTRICT,
    # like every other foreign key in 0009: a reversal must not outlive the
    # entry it explains.
    op.create_foreign_key(
        "fk_point_ledger_entry_reverses_entry",
        "point_ledger_entry",
        "point_ledger_entry",
        ["tenant_id", "reverses_entry_id"],
        ["tenant_id", "id"],
        ondelete="RESTRICT",
    )


def downgrade() -> None:
    """Drop the foreign key, the column, and the unique constraint.

    A development tool, not a production rollback path (v1.1 §4.2). Reverse
    order of :func:`upgrade`: the foreign key depends on both the column it is
    declared on and the unique constraint it references, so it goes first, and
    ``uq_point_ledger_entry_tenant_id`` goes last.

    Dropping the column discards any reversal target recorded in it. That is the
    honest consequence of removing the only place that fact was stored, and it
    is why this is a development affordance rather than something to run against
    an environment whose ledger has corrections in it.
    """
    op.drop_constraint(
        "fk_point_ledger_entry_reverses_entry", "point_ledger_entry", type_="foreignkey"
    )
    op.drop_column("point_ledger_entry", "reverses_entry_id")
    op.drop_constraint("uq_point_ledger_entry_tenant_id", "point_ledger_entry", type_="unique")
