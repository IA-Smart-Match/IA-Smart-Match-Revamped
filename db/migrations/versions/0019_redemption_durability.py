"""``redemption``, a representable redemption debit, and the ledger's append-only guard.

Revision ID: 0019_redemption_durability
Revises: 0018_match_run_snapshot
Create Date: 2026-09-04

Plan ``docs/plans/2026-08-28-d6-rewards-s8-s9-plan.md`` cards **L2** (a
database-level append-only guard on ``point_ledger_entry``) and **L4** (the S9
redemption command: ``requested -> approved -> fulfilled | denied | expired``,
with the balance check and the ledger debit atomic server-side). D6 is closed
for pilot scope (``docs/decisions/pilot-decisions.md`` §D6, 2026-09-02, Danny
Tran named as institutional budget owner), which is what makes these two cards
implementable rather than merely reportable; D7 stays **tentative** and this
revision seeds no catalog, prices nothing, and moves no money.

Three gaps are closed here, all three of which the rewards domain and its
repository were landed *without* and reported in their own docstrings.

1. There is no ``redemption`` table
------------------------------------
Migration ``0009`` deferred it explicitly ("``event``, ``redemption``, and
``disclosure_consent`` each depend on something this migration cannot settle
… D6/D7's shipped-catalog gate for redemption"). ``0017`` settled ``event``;
D6's closure settles this one. Until now the whole
``requested -> approved -> fulfilled | denied | expired`` machine lived in
memory in :mod:`smartmatch_domain.rewards`, which means a redemption did not
survive a process restart — a student's approved reward could evaporate
between the approval and the handover, and nothing would be able to say it had
ever existed.

The columns are exactly what :class:`smartmatch_domain.rewards.Redemption`
carries, plus the audit trail a state machine needs to be readable after the
fact:

``item_name_snapshot`` and ``points_cost_snapshot`` are D7's two "consequences
that must survive into any implementation" — "existing redemptions retain their
point-cost snapshot" and "a deactivated reward blocks new requests but stays
visible on existing tickets". They are columns on this table rather than a join
back to ``reward_item`` for exactly that reason: a join returns today's price
and today's name, which is the defect, not the fix.

``approved_at``/``approved_by`` and ``closed_at``/``closed_by`` are the two
transitions that actually happen to a redemption, recorded as evidence rather
than inferred from ``state``. The pair shape is ``review_item``'s
(``ck_review_item_decision_evidence``, migration ``0008``) applied to a machine
with one more hop: a decision that recorded no time and no author is a decision
nobody can audit, and ``state`` alone cannot say *when* or *by whom*.

``closed_by`` is nullable where ``approved_by`` is not, and that asymmetry is
the vocabulary's: ``approved`` and ``denied`` are things a coordinator does,
while ``expired`` is something time does. Forcing an author onto an expiry
would name a human for a row no human touched — the fabricated-field defect
(Fix #15) arriving through a ``NOT NULL``.

**No ``owning_unit_id``**, and that is deliberate rather than an oversight.
Every other A5-shaped table here (``job``, ``attendance_record``, ``event``,
``match_run``) carries the unit its authorization is scoped against because
something already knows which unit that is. Nothing does for a redemption:
``reward_item`` has no unit, D6 records "read/redemption roles" as a field it
does *not* resolve, and card R3 — which is what would authorize against such a
column — cannot land until those roles are decided. A column filled with a
guess would be worse than its absence, because a later authorization decision
would inherit the guess. The unit is added by the card that decides what it
means.

**No trigger on this table.** ``0018``'s ``match_run`` is immutable because a
correction there is a new row. A redemption is the opposite: its whole purpose
is to move through states, and each move is an ``UPDATE`` of ``state`` and one
evidence pair. What keeps that honest is not immutability but
``ck_redemption_approval_evidence`` and ``ck_redemption_closure_evidence``,
which hold on an ``UPDATE`` exactly as they do on an ``INSERT`` — so a row
cannot be moved into ``fulfilled`` without an approval behind it, whichever
statement moves it.

``uq_redemption_open_per_item`` is a **partial** unique index over
``(tenant_id, subject_id, item_id) WHERE state IN ('requested','approved')``.
Card L4 asks that "concurrent duplicate requests resolve to one redemption",
and this is that rule where a race can reach it: a second request for an item
this student already has in flight conflicts, and
``RewardsRepository.open_redemption`` reads the in-flight one back instead of
opening a twin. It is partial because a *terminal* redemption must not block a
later one — a reward fulfilled in October is not a reason to refuse the same
reward in March, and a unique constraint over the whole table would say it was.

2. A redemption debit had no representable row
------------------------------------------------
``point_ledger_entry.source_attendance_id`` was ``NOT NULL`` (``0009``), so
every ledger row had to name an attendance it derived from. A debit taken when
a student redeems a reward derives from a *redemption*. Card L4's "balance
check and ledger debit are atomic" therefore could not be implemented honestly
at all: the only ways to write the debit were to borrow an unrelated
attendance id — evidence fabricated to satisfy a constraint, which is the
precise defect ADR-0011 exists to refuse — or to store the balance somewhere
else, which is Fix #9 restored.

So ``source_attendance_id`` becomes nullable and ``source_redemption_id``
arrives beside it. **Nullability alone would be a hole**, and
``ck_point_ledger_entry_kind`` is what closes it: every row is exactly one of

* ``attendance_credit`` — an attendance, no redemption, ``amount > 0``
* ``reversal`` — an attendance, no redemption, ``amount < 0``
* ``redemption_debit`` — a redemption, no attendance, ``amount < 0``

and each carries the fields its kind requires. The constraint is written as a
disjunction of three fully-specified shapes rather than as a vocabulary check
plus a shape check, because the disjunction *is* the vocabulary: a row with a
``kind`` outside the three satisfies none of the disjuncts and is refused by
the same expression that refuses a well-named row with the wrong fields. There
is no combination of nulls that passes.

``kind`` is derivable from the sign and from which source is set, and that is
the argument *for* the column rather than against it. The repository's
double-credit check previously read ``amount > 0`` as a proxy for "this is a
credit", which is a semantic encoded in arithmetic and invisible to a reader of
the table; ``uq_point_ledger_entry_attendance_credit`` below cannot be written
against a proxy at all. The CHECK ties the column to the derivation exactly, so
the two cannot drift.

Existing rows are backfilled ``CASE WHEN amount > 0 THEN 'attendance_credit'
ELSE 'reversal' END``. That is not a guess: before this revision those were the
only two kinds of row the schema could hold, and the sign is what told them
apart — the backfill states the existing semantics rather than inventing a new
one. The column then takes ``NOT NULL`` with **no server default**: every
writer must say which kind it is writing (ADR-0011).

**``reverses_entry_id`` is deliberately not reintroduced.** Migration ``0015``
removed it, and its stated reason was authorization — the ``c075817``
prototype's gates were closed — not that the column was wrong. This revision is
not that authorization: nothing in D6's closure or in cards L2/L4 speaks to
which *entry* a reversal names, and bringing back a dropped contract on the
side of a change about something else is how a removal quietly becomes
reversible. The ambiguity ``0014`` described — where two entries share a
source, a reversal names the attendance but not the entry — therefore stands,
reported here and in :mod:`smartmatch_persistence.rewards`, unchanged by this
revision. ``uq_point_ledger_entry_tenant_id``, which ``0015`` removed with it,
is likewise not restored: nothing references ``point_ledger_entry`` by
composite key, and ``0008``'s rule is that such a constraint is added by the
migration that creates the reference. The reference here runs the other way —
the debit names the redemption.

``uq_reward_item_tenant_id`` *is* added, by exactly that rule:
``redemption.item_id`` is the reference that now needs it, and ``0009`` said
"nothing in this migration references ``reward_item`` by composite key" as its
reason for leaving it out.

3. Earning idempotency had no constraint, and the ledger no DB guard
----------------------------------------------------------------------
``uq_point_ledger_entry_attendance_credit`` is a partial unique index over
``(tenant_id, source_attendance_id) WHERE kind = 'attendance_credit'``: one
credit per attendance, enforced by PostgreSQL for every writer rather than by a
``SELECT ... FOR UPDATE`` that holds only for callers who come through one
method. It is partial because the general constraint would be wrong —
ADR-0013 positively anticipates several entries deriving from one attendance
as the earn policy is revised, and a reversal is one of them. What must not
happen twice is the *credit*.

Creating it will fail loudly on a database that already holds two credits for
one attendance. That is the correct outcome: such a pair is the unearned second
credit the constraint exists to refuse, and it should be looked at by a human
rather than deduplicated by a migration guessing which row was real.

``point_ledger_entry_reject_mutation()`` is card **L2**, and it follows
``0018``'s pattern deliberately rather than inventing a second mechanism —
same ``BEFORE UPDATE`` trigger, same ``restrict_violation``, and the same
reasoning ``0018``'s docstring gives for why a trigger and not a ``CHECK`` (a
CHECK sees only the new row and cannot know one existed before it), not a
``RULE ... DO INSTEAD NOTHING`` (which discards the write silently, a fake
success), and not ``REVOKE`` (which binds to a role name a migration does not
know and is undone by any later ``GRANT``).

**DELETE is not blocked, and card L2's wording asked for both.** This is a
deviation, stated rather than glossed. ``0018`` made the same call for
``match_run`` and gave the reasons that apply here unchanged: retention is a
question neither card decides, the tenant-teardown path in
``tests/integration/conftest.py`` and the engagement test modules' own fixtures
need it, and a table nothing may delete from makes its tenant undeletable by
way of a table nobody can authorize deleting from. The half that matters for
the ledger's integrity is the one blocked: D7's "no silent balance editing"
rule is about a balance being *changed*, and an ``UPDATE`` is how that is done.
A ``DELETE`` of a whole tenant's rows is a retention operation, not a silent
edit, and it is visible as an absence in a way an amended amount is not.

Expand only, one transaction
------------------------------
One new table, one new column pair on an existing one, one relaxed ``NOT
NULL``, one CHECK, three indexes, and a trigger. Nothing is dropped or renamed;
the one nullability change is a *widening*, so code written before this
revision — which always supplies ``source_attendance_id`` — keeps working
against the new shape, which is what makes it safe to run ahead of its readers
(v1.1 §4.2, ADR-0009). The backfill touches a table that is empty in every
environment this has run against. ``transaction_per_migration=True``
(``db/migrations/env.py``) holds the whole thing in one transaction.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0019_redemption_durability"
down_revision = "0018_match_run_snapshot"
branch_labels = None
depends_on = None

#: The three kinds a ``point_ledger_entry`` row may be, each spelled out with
#: the fields it requires. Held as one string so the migration and the schema
#: mirror cannot render it differently by accident.
_LEDGER_KIND_CHECK = (
    "(kind = 'attendance_credit' AND source_attendance_id IS NOT NULL "
    "AND source_redemption_id IS NULL AND amount > 0) "
    "OR (kind = 'reversal' AND source_attendance_id IS NOT NULL "
    "AND source_redemption_id IS NULL AND amount < 0) "
    "OR (kind = 'redemption_debit' AND source_attendance_id IS NULL "
    "AND source_redemption_id IS NOT NULL AND amount < 0)"
)


def upgrade() -> None:
    """Create ``redemption``, make the debit representable, and guard the ledger."""
    # 0009 left this out because nothing referenced reward_item by composite
    # key. redemption.item_id below now does, so it is added by the migration
    # that creates the reference — 0008's rule, and 0009's own stated reason.
    op.create_unique_constraint(
        "uq_reward_item_tenant_id",
        "reward_item",
        ["tenant_id", "id"],
    )

    op.create_table(
        "redemption",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        # The student redeeming. Composite to user_account, as every identity
        # reference in this schema is.
        sa.Column("subject_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("item_id", postgresql.UUID(as_uuid=True), nullable=False),
        # D7's two "consequences that must survive into any implementation".
        # Snapshots, not a join: a join returns today's price and today's name.
        sa.Column("item_name_snapshot", sa.Text(), nullable=False),
        sa.Column("points_cost_snapshot", sa.Integer(), nullable=False),
        sa.Column("state", sa.Text(), nullable=False),
        sa.Column(
            "requested_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        # The approval hop. Both null until a coordinator approves; both set
        # together afterwards, and never unset — the transitions out of
        # `approved` are `fulfilled` and `expired`, neither of which unapproves
        # anything.
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("approved_by", postgresql.UUID(as_uuid=True), nullable=True),
        # The terminal hop. `closed_by` stays null for an expiry: time is not a
        # person. See the module docstring.
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("closed_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name="redemption_pkey"),
        # What point_ledger_entry.source_redemption_id below references.
        sa.UniqueConstraint("tenant_id", "id", name="uq_redemption_tenant_id"),
        # RESTRICT throughout, matching every foreign key 0009 declared: a
        # redemption is a promise made to a named student against a named
        # reward, and neither may vanish out from under it.
        sa.ForeignKeyConstraint(
            ["tenant_id", "subject_id"],
            ["user_account.tenant_id", "user_account.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "item_id"],
            ["reward_item.tenant_id", "reward_item.id"],
            ondelete="RESTRICT",
        ),
        # The actors are constrained, unlike point_ledger_entry.actor_id: a
        # ledger credit is derived and usually has no human author, but an
        # approval and a denial are things a person did, and an approver who is
        # not an account in this tenant is not an approver.
        sa.ForeignKeyConstraint(
            ["tenant_id", "approved_by"],
            ["user_account.tenant_id", "user_account.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "closed_by"],
            ["user_account.tenant_id", "user_account.id"],
            ondelete="RESTRICT",
        ),
        # ADR-0013's vocabulary, verbatim, and the same StrEnum spelling
        # smartmatch_domain.rewards.RedemptionState carries.
        sa.CheckConstraint(
            "state IN ('requested','approved','fulfilled','denied','expired')",
            name="ck_redemption_state",
        ),
        # The approval evidence, and the one structural statement of "fulfilled
        # is reachable only from approved": a fulfilled row with no approval
        # behind it cannot be written or updated into existence. `requested`
        # implies no approval yet, which is what stops an approval being
        # recorded and then walked back to `requested`.
        sa.CheckConstraint(
            "(approved_at IS NULL) = (approved_by IS NULL) "
            "AND (state <> 'fulfilled' OR approved_at IS NOT NULL) "
            "AND (state <> 'requested' OR approved_at IS NULL)",
            name="ck_redemption_approval_evidence",
        ),
        # A terminal state has a close time; a live one does not. `closed_by`
        # may be null on a closed row (expiry), but never set on an open one.
        sa.CheckConstraint(
            "(state IN ('fulfilled','denied','expired')) = (closed_at IS NOT NULL) "
            "AND (closed_by IS NULL OR closed_at IS NOT NULL)",
            name="ck_redemption_closure_evidence",
        ),
        # A snapshot that says nothing is not a snapshot. NOT NULL alone
        # accepts the empty string and a zero cost; a ticket showing a nameless
        # reward at no cost is the fabricated-field shape, not a record.
        sa.CheckConstraint(
            "points_cost_snapshot > 0 AND length(btrim(item_name_snapshot)) > 0",
            name="ck_redemption_snapshot_present",
        ),
    )

    # One in-flight redemption per student per item; a terminal one never
    # blocks a later request. See the module docstring.
    op.create_index(
        "uq_redemption_open_per_item",
        "redemption",
        ["tenant_id", "subject_id", "item_id"],
        unique=True,
        postgresql_where=sa.text("state IN ('requested','approved')"),
    )

    # The access path a student's ticket list reads: one subject's redemptions
    # within one tenant, newest first. Declared with the table for the reason
    # 0017 and 0018 give — an index is cheap and a sequential scan discovered
    # later is not.
    op.create_index(
        "ix_redemption_subject_requested",
        "redemption",
        ["tenant_id", "subject_id", sa.text("requested_at DESC")],
    )

    # --- the representable debit -----------------------------------------
    # A widening. Code written before this revision always supplies the column
    # and keeps working; what changes is that a debit no longer has to invent
    # an attendance to satisfy a NOT NULL.
    op.alter_column("point_ledger_entry", "source_attendance_id", nullable=True)

    op.add_column(
        "point_ledger_entry",
        sa.Column("source_redemption_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_point_ledger_entry_source_redemption",
        "point_ledger_entry",
        "redemption",
        ["tenant_id", "source_redemption_id"],
        ["tenant_id", "id"],
        ondelete="RESTRICT",
    )

    # Added nullable, backfilled from the semantics the sign already carried,
    # then made NOT NULL with no default. See the module docstring for why the
    # backfill is a statement of the existing rule rather than a guess.
    op.add_column("point_ledger_entry", sa.Column("kind", sa.Text(), nullable=True))
    op.execute(
        "UPDATE point_ledger_entry SET kind = "
        "CASE WHEN amount > 0 THEN 'attendance_credit' ELSE 'reversal' END"
    )
    op.alter_column("point_ledger_entry", "kind", nullable=False)

    op.create_check_constraint(
        "ck_point_ledger_entry_kind",
        "point_ledger_entry",
        _LEDGER_KIND_CHECK,
    )

    # Earning idempotency, as a constraint rather than as a row lock one
    # method happens to take. Partial: several entries may derive from one
    # attendance (a reversal is one), but only one may *credit* it.
    op.create_index(
        "uq_point_ledger_entry_attendance_credit",
        "point_ledger_entry",
        ["tenant_id", "source_attendance_id"],
        unique=True,
        postgresql_where=sa.text("kind = 'attendance_credit'"),
    )

    # --- card L2: append-only, structurally -------------------------------
    # 0018's pattern, reused rather than reinvented. UPDATE only; see the
    # module docstring for why DELETE stays permitted and why that is a stated
    # deviation from card L2's wording rather than an oversight.
    op.execute(
        """
        CREATE FUNCTION point_ledger_entry_reject_mutation() RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION
                'point_ledger_entry is append-only: a correction is a new '
                'compensating entry, never an UPDATE of an existing one '
                '(ADR-0013, migration 0019, plan card L2)'
                USING ERRCODE = 'restrict_violation';
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    op.execute(
        """
        CREATE TRIGGER point_ledger_entry_is_append_only
        BEFORE UPDATE ON point_ledger_entry
        FOR EACH ROW EXECUTE FUNCTION point_ledger_entry_reject_mutation();
        """
    )


def downgrade() -> None:
    """Undo the above, in reverse creation order.

    A development tool, not a production rollback path (v1.1 §4.2).

    It **refuses** rather than proceeding when the ledger holds a redemption
    debit. Restoring ``source_attendance_id NOT NULL`` over such a row is
    impossible without either deleting the row — destroying a ledger entry, in
    a table whose entire design says corrections are appended and never removed
    — or inventing an attendance for it, which is the fabrication this revision
    exists to make unnecessary. Refusing names the situation and leaves the
    operator to decide; a downgrade that quietly deleted evidence would be the
    worse of the two by a distance.
    """
    debits = (
        op.get_bind()
        .execute(
            sa.text("SELECT count(*) FROM point_ledger_entry WHERE kind = 'redemption_debit'")
        )
        .scalar_one()
    )
    if debits:
        raise RuntimeError(
            f"cannot downgrade 0019: {debits} redemption debit(s) exist in "
            "point_ledger_entry, and restoring source_attendance_id NOT NULL would "
            "require deleting ledger rows or fabricating an attendance for each. "
            "Decide what should happen to those entries first."
        )

    op.execute("DROP TRIGGER IF EXISTS point_ledger_entry_is_append_only ON point_ledger_entry")
    op.execute("DROP FUNCTION IF EXISTS point_ledger_entry_reject_mutation()")
    op.drop_index("uq_point_ledger_entry_attendance_credit", table_name="point_ledger_entry")
    op.drop_constraint("ck_point_ledger_entry_kind", "point_ledger_entry", type_="check")
    op.drop_column("point_ledger_entry", "kind")
    op.drop_constraint(
        "fk_point_ledger_entry_source_redemption", "point_ledger_entry", type_="foreignkey"
    )
    op.drop_column("point_ledger_entry", "source_redemption_id")
    op.alter_column("point_ledger_entry", "source_attendance_id", nullable=False)

    op.drop_index("ix_redemption_subject_requested", table_name="redemption")
    op.drop_index("uq_redemption_open_per_item", table_name="redemption")
    op.drop_table("redemption")
    op.drop_constraint("uq_reward_item_tenant_id", "reward_item", type_="unique")
