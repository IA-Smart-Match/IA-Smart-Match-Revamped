"""The engagement schema: ``attendance_record``, ``point_ledger_entry``, ``reward_item``.

Revision ID: 0009_engagement_schema
Revises: 0008_import_review
Create Date: 2026-08-28

ADR-0013, backlog S6/S7/S8 (``docs/plans/remaining-foundation-r1-work.md``).
Three tables, not the five ``docs/architecture/engagement-model.md`` §1
describes — the same partial cut ``0008`` made of that document's earlier
five-table draft, and for the same reason: ``event``, ``redemption``, and
``disclosure_consent`` each depend on something this migration cannot settle
(the tag vocabulary gate G3, ADR-0012; D6/D7's shipped-catalog gate for
redemption; ADR-0014 for disclosure_consent). ``attendance_record``,
``point_ledger_entry``, and ``reward_item`` are the three S6/S7/S8 names, and
nothing gates *building* them — only *listing* a reward (D6) and *shipping* a
catalog (D6+D7) are gated, and both are applications of this schema, not
prerequisites to it.

Fix #9 and Fix #15, the two findings ADR-0013 answers
-------------------------------------------------------
The legacy ``getStudentTotalPoints`` computed a balance in the browser from two
summary counters, with no server-side record, no history, and — in its own
docstring — no claim to be more than a demo formula. ``point_ledger_entry``
replaces it: a balance is a fold over an append-only ledger, computed
server-side, never stored. **There is no balance column on this table, or on
any other table this migration touches.** A reversal is a new entry that names
what it reverses, never an ``UPDATE`` or a ``DELETE`` — the same append-only
shape ``job_event``, ``outbox_record``, and ``redrive_record`` already have
relative to their own histories.

The legacy catalog priced its cheapest item at 100 events of attendance and
named no one who would honour it. ADR-0013's answer is not a better price; it
is that ``reward_item.budget_owner_id`` and ``reward_item.funded`` are both
``NOT NULL``. D6 (``docs/decisions/pilot-decisions.md``) says explicitly that
the coordinator role administers reward *availability* but that no budget
holder is named and no budget exists — so this migration makes an unowned,
unfunded reward a row PostgreSQL refuses to hold, rather than a rule an
application layer could forget to check. D6 then blocks a *shipped* catalog
(nobody can insert a listable row yet) rather than blocking this schema.

``attendance_record`` is the evidence, and the only input to points
------------------------------------------------------------------------
QR check-in (``MM-F02``) is scheduled separately, for R2. This table is what it
will write to; nothing here builds the scanner. ``method`` records how a row
was produced — ``qr_scan``, ``coordinator_entry``, or ``import`` — as a CHECK
constraint over the three mechanisms the architecture names, the same
enumeration idiom ``ck_review_item_status`` (0008) and ``ck_outbox_status``
(0001) already use.

No ``event`` table exists yet (see above), so ``event_id`` is a bare
``UUID NOT NULL`` with **no foreign key**. This is not an oversight: a
constraint referencing a table that does not exist cannot be written, and
substituting a loosely-typed placeholder (text, or a nullable column) would
misstate the guarantee rather than simply omit it. The precedent for an
intentionally unconstrained id column already exists in this schema —
``job.actor_id`` — for the same reason: the identity is real and worth
recording, and the codebase is not yet in a position to enforce it refers to
anything. Whichever migration adds ``event`` should also add this foreign key.

``owning_unit_id`` is A5-shaped, exactly as ``job.owning_unit_id`` (0006) and
``import_batch.owning_unit_id`` (0008) are: the unit an attendance row is
scoped against for authorization, populated at write time rather than joined
back through ``event`` later — the same reasoning 0008 gives for
``import_batch`` carrying its own ``owning_unit_id`` rather than reaching it
through ``job``.

``subject_id`` is composite to ``user_account`` — the student who attended —
``ON DELETE RESTRICT`` for the reason ``import_batch.owning_unit_id -> org_unit``
gives: no route in this codebase deletes a ``user_account`` row, so the
practical difference from ``CASCADE`` is nil today, but attendance is evidence,
and evidence should not silently disappear if that ever changes.

``uq_attendance_record_tenant_id`` on ``(tenant_id, id)`` exists because
``point_ledger_entry.source_attendance_id`` below references it — the same
justification 0008 gives ``uq_import_batch_tenant_id``.

``uq_attendance_record_subject_event`` on ``(tenant_id, subject_id, event_id)``
is this migration's one constraint beyond the documented column list, and it
earns its place the same way ADR-0013 argues ``reward_item``'s ``NOT NULL``
pair does: attendance is the *only* input to points (ADR-0013, "Points derive
from recorded attendance and nothing else"), so a duplicate attendance row for
the same student at the same event is not a harmless re-scan — it is a second,
unearned credit the ledger has no way to tell apart from a real one. Refusing
the duplicate at the evidence layer is cheaper and more certain than trying to
detect double-crediting after the fact in the ledger it would otherwise
produce.

``point_ledger_entry`` — append-only, and that is enforced by what is absent
------------------------------------------------------------------------------
Columns are exactly ADR-0013's list: ``amount``, ``source_attendance_id``
(the "source" — the attendance record an entry derives from), ``reason``,
``actor``, ``occurred_at``. No ``status`` column, no ``updated_at``, no
``version`` — there is nothing here an application could legitimately
``UPDATE``, which is the same argument 0008 makes for why ``import_batch`` and
``review_item`` carry no ``version``: a column invites exactly the mutation its
absence forecloses. Appending a compensating entry (ADR-0013: "A reversal is a
compensating entry, never a delete") is the only way to change what the ledger
says, and that is an ``INSERT``, not an ``UPDATE``.

``amount`` is a signed ``INTEGER`` rather than an unsigned one precisely so a
reversal can be recorded as a negative entry naming the same
``source_attendance_id`` and a ``reason`` that says what it corrects, without
a sign-flag column alongside it.

``actor_id`` is nullable with no foreign key, deliberately mirroring
``job.actor_id``: an entry produced by automatic derivation from an attendance
record (the ordinary case — ADR-0013 says points have "no discretionary
grant") has no human actor to name, and forcing one would misstate the origin
of the row rather than describe it.

``source_attendance_id`` is composite to ``attendance_record``,
``ON DELETE RESTRICT``: an attendance row that a ledger entry derives from must
not disappear out from under the entry that cites it as its source — the
derivation rule (ADR-0013 §"Points derive from recorded attendance and nothing
else") would otherwise become unverifiable for exactly the rows it was written
to protect.

No ``uq_point_ledger_entry_tenant_id``: nothing below this table references it
in this migration (``redemption``, which might, is S9 and deferred — see
above), so per 0008's rule for ``review_item``, the constraint is not added on
spec.

``reward_item`` — the schema constraint ADR-0013 is chiefly about
----------------------------------------------------------------------
Columns are ADR-0013's and ``docs/architecture/engagement-model.md``'s list:
``name``, ``points_cost``, ``fulfilment_cost``, ``budget_owner_id``, ``funded``.

``budget_owner_id`` is composite to ``user_account``
(``(tenant_id, budget_owner_id) -> user_account (tenant_id, id)``), not a
single-column pointer to an id: a single-column key would accept an owner from
another tenant, and D6's "named human budget owner" reads emptily if the name
can belong to someone with no standing in this tenant at all.
``ON DELETE RESTRICT`` — the same choice ``job.owning_unit_id`` and
``import_batch.owning_unit_id`` make, and for the same reason: removing the
person who owns a reward's budget must not silently leave the reward's row
behind with a dangling owner. Both ``budget_owner_id`` and ``funded`` are
declared ``NOT NULL`` — every insert must supply both explicitly, which is what
makes this the structural form of D6's requirement rather than a policy
sentence about it. Softening either to nullable "for flexibility" would be
exactly the regression ADR-0013 exists to close: it would let an unowned,
unfunded reward be written, which is the legacy defect (Fix #15) reproduced at
the schema layer instead of the UI layer.

``funded`` carries ``server_default 'false'``, which is not in tension with the
paragraph above: ``NOT NULL`` is what refuses the *absent* case, and a default
only governs what a statement silent about the column receives. Defaulting to
unfunded is the fail-closed direction, matching ``tenant_budget.kill_switch``
and ``user_account.suspended`` elsewhere in this schema. ``budget_owner_id``
gets no such default — there is no safe value to fall back to for who owns a
budget — so every insert must still name one.

``ck_reward_item_points_cost_positive`` and
``ck_reward_item_fulfilment_cost_non_negative`` mirror
``ck_budget_ceiling_non_negative`` and ``ck_budget_non_negative``
(``tenant_budget``, 0001): a reward costing zero or negative points is not a
reward, and a negative fulfilment cost is not a real-world cost.

No ``uq_reward_item_tenant_id``: as with ``point_ledger_entry``, nothing in
this migration references ``reward_item`` by composite key — ``redemption``
(S9) is deferred, per the note at the top of this docstring.

Single transaction, no backfill
------------------------------------
All three tables are new. This is 0008's and 0001's shape, not 0006's: nothing
existing to lock or backfill, no reason to split expand from contract (v1.1
§4.2, ADR-0009). ``transaction_per_migration=True`` (``db/migrations/env.py``)
holds the whole thing in one transaction.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0009_engagement_schema"
down_revision = "0008_import_review"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create ``attendance_record``, ``point_ledger_entry``, ``reward_item``."""
    op.create_table(
        "attendance_record",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        # A5-shaped, same as job.owning_unit_id (0006) and
        # import_batch.owning_unit_id (0008): scoped at write time, not joined
        # back through event later.
        sa.Column("owning_unit_id", postgresql.UUID(as_uuid=True), nullable=False),
        # The student who attended.
        sa.Column("subject_id", postgresql.UUID(as_uuid=True), nullable=False),
        # No foreign key: no event table exists yet. See the module docstring.
        sa.Column("event_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("method", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("id"),
        # What point_ledger_entry's composite foreign key below references.
        sa.UniqueConstraint("tenant_id", "id", name="uq_attendance_record_tenant_id"),
        # Attendance is the only input to points (ADR-0013); a duplicate row
        # for the same student at the same event is an unearned second credit,
        # refused here rather than detected later in the ledger it would
        # otherwise produce.
        sa.UniqueConstraint(
            "tenant_id",
            "subject_id",
            "event_id",
            name="uq_attendance_record_subject_event",
        ),
        # RESTRICT: reorganizing a unit must not silently delete attendance
        # evidence recorded against it — the same intent job.owning_unit_id
        # and import_batch.owning_unit_id carry against org_unit.
        sa.ForeignKeyConstraint(
            ["tenant_id", "owning_unit_id"],
            ["org_unit.tenant_id", "org_unit.id"],
            ondelete="RESTRICT",
        ),
        # RESTRICT: no route deletes a user_account row today, but attendance
        # is evidence and should not silently vanish if that ever changes.
        sa.ForeignKeyConstraint(
            ["tenant_id", "subject_id"],
            ["user_account.tenant_id", "user_account.id"],
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "method IN ('qr_scan','coordinator_entry','import')",
            name="ck_attendance_record_method",
        ),
    )

    op.create_table(
        "point_ledger_entry",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        # Signed: a reversal is a negative entry naming the same source and a
        # reason that explains it, per ADR-0013 ("a reversal is a compensating
        # entry, never a delete"). No balance column exists anywhere in this
        # table, or in this migration.
        sa.Column("amount", sa.Integer(), nullable=False),
        # The attendance record this entry derives from — ADR-0013's "source".
        # Points derive from recorded attendance and nothing else; there is no
        # discretionary grant and no client-submitted entry.
        sa.Column("source_attendance_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        # Nullable, no foreign key: mirrors job.actor_id. Automatic derivation
        # from attendance — the ordinary case — has no human actor to name.
        sa.Column("actor_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "occurred_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("id"),
        # RESTRICT: the attendance record an entry derives from must not
        # disappear out from under the entry that cites it, or the derivation
        # rule becomes unverifiable for exactly the rows it protects.
        sa.ForeignKeyConstraint(
            ["tenant_id", "source_attendance_id"],
            ["attendance_record.tenant_id", "attendance_record.id"],
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint("amount <> 0", name="ck_point_ledger_entry_amount_nonzero"),
    )

    op.create_table(
        "reward_item",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("points_cost", sa.Integer(), nullable=False),
        sa.Column("fulfilment_cost", sa.Numeric(12, 4), nullable=False),
        # D6: "a named human budget owner. Without one, the rewards catalog is
        # not shippable." NOT NULL, no server default — every insert must name
        # a real owner in this tenant. Composite, not a bare id: a
        # single-column key would accept an owner from another tenant.
        sa.Column("budget_owner_id", postgresql.UUID(as_uuid=True), nullable=False),
        # NOT NULL alongside budget_owner_id — this pair is the structural
        # form of D6's requirement (ADR-0013). See the module docstring for why
        # the server_default below does not soften this.
        sa.Column("funded", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("id"),
        # RESTRICT: removing the person who owns a reward's budget must not
        # silently leave the reward behind with a dangling owner — the same
        # choice job.owning_unit_id and import_batch.owning_unit_id make.
        sa.ForeignKeyConstraint(
            ["tenant_id", "budget_owner_id"],
            ["user_account.tenant_id", "user_account.id"],
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint("points_cost > 0", name="ck_reward_item_points_cost_positive"),
        sa.CheckConstraint(
            "fulfilment_cost >= 0", name="ck_reward_item_fulfilment_cost_non_negative"
        ),
    )


def downgrade() -> None:
    """Drop all three tables.

    A development tool, not a production rollback path (v1.1 §4.2).
    ``point_ledger_entry`` is dropped before ``attendance_record`` because it is
    the dependent side of the foreign key between them; ``reward_item`` has no
    ordering dependency on either and is dropped last so the order still reads
    as deliberate rather than incidental.
    """
    op.drop_table("point_ledger_entry")
    op.drop_table("attendance_record")
    op.drop_table("reward_item")
