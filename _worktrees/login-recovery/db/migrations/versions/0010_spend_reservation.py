"""``spend_ceiling_bucket`` and ``spend_reservation`` (ADR-0015 Amendment A1).

Revision ID: 0010_spend_reservation
Revises: 0009_engagement_schema
Create Date: 2026-08-31

A1: counting quota (``rate_limit_counter``, ADR-0015's own body) and monetary
spend are not the same control. A dollar paid to an external LLM provider is
an irreversible side effect this system cannot roll back, so A1's rule is
**reserve the maximum estimated cost atomically before the paid call, then
reconcile to the actual cost after it** — never the post-hoc
check-then-call shape ADR-0015's counting rule uses, which A1 shows overshoots
a ceiling by up to one call's cost, or ``N`` calls' cost under concurrency.

Two tables, matching A1's *Components*.

``spend_ceiling_bucket`` — three ceilings, three rows
------------------------------------------------------
A1's obligation 1 debits per-job, per-tenant-per-day, and per-tenant-per-month
ceilings **atomically, all-or-nothing**. A1 explicitly declines to choose
between "three sequential guarded writes", "one composite CTE", and "one
denormalized row" for the ledger's shape — the ADR's own words: *"This
amendment does not choose between them, and says so rather than implying the
choice is made... The choice must be recorded in the work item that builds the
ledger."* This migration records that choice: **three normalized rows, one per
ceiling kind, keyed by ``(tenant_id, bucket_type, bucket_key)``.**

That works only inside a single transaction that commits all three writes or
none — the alternative A1 names ("compensating release on partial failure")
reintroduces exactly the partial-debit state A1 warns against. The persistence
service (``smartmatch_persistence.spend``, not this migration) is what enforces
the transaction boundary and the **fixed lock order** A1 requires to avoid
deadlock between two concurrent reservations taking the same three rows in
different orders: it always locks ``job``, then ``tenant_day``, then
``tenant_month`` (``smartmatch_domain.spend.BUCKET_LOCK_ORDER``), never a
caller-chosen order.

``bucket_key`` is a normalized string the domain layer derives —
``job:<job_id>``, ``tenant-day:<tenant_id>:<date>``,
``tenant-month:<tenant_id>:<year>-<month>`` — rather than three differently
shaped columns per bucket kind, because day and month buckets roll over on
different clocks (A1: *"day and month buckets roll over on different clocks
and the per-job ceiling is scoped to a different entity"*) and a single string
key lets one table hold all three without three sets of nullable columns.

``ceiling`` is fixed at whichever value first creates a bucket row and is never
rewritten by a later reservation against the same key — a ceiling change from
policy takes effect on the *next* bucket (the next day, the next month, a
different job), not by mutating a bucket already in flight. ``reserved`` and
``spent`` mirror ``tenant_budget``'s columns and non-negativity check
(migration ``0001``); this table adds no ``kill_switch`` because a bucket has
no on/off switch of its own, only a ceiling.

**No CHECK bounding ``reserved + spent <= ceiling``.** A1 is explicit that an
overage must be *recorded*, never truncated: *"record the overage as actual
spend, never silently truncate it to the reservation."* A reconciliation that
posts a genuine overage can legitimately push ``spent`` past ``ceiling`` for one
bucket, once, and a CHECK enforcing the cap would refuse the very write A1
requires.

``spend_reservation`` — one row per reserved unit of work
-----------------------------------------------------------
Deterministic ``work_key`` (``smartmatch_domain.spend.derive_work_key``),
globally unique — mirrors ``uq_outbox_task_name``'s reasoning
(``outbox.py``/ADR-0007): a retried or redelivered attempt at the *same* unit
of work must find its own row rather than reserving a second time. The three
bucket keys a reservation debited are stored on the row (not re-derived at
settle time) so reconciliation, timeout, release, and the sweep credit exactly
the buckets that were exactly debited, even if a bucket's own definition
(rollover boundaries, job scoping) were ever to change.

``estimate`` and ``actual_cost`` are ``NUMERIC(12,4)``, matching
``tenant_budget``'s precision (migration ``0001``) — never ``FLOAT``, per A1's
repeated insistence that a dollar figure is either a recorded estimate or a
recorded actual and never a rounded approximation of either.
``actual_is_estimated`` distinguishes the two: A1's in-worker-timeout and
sweeper paths both write ``actual_cost = estimate`` but must never be mistaken
for a confirmed real cost — *"an estimated dollar amount must never be
recorded, displayed, or reported as an actual one."*

``lease_token`` is present exactly while the row is ``reserved`` and cleared
on every terminal transition, the same discipline J17 established for
``outbox_record`` — a terminal row must not keep a token a late writer could
present to satisfy a compare-and-set that should already be closed. The column
is therefore NULLABLE (as ``outbox_record.lease_token`` is), and the biconditional
``ck_spend_reservation_lease_token_iff_reserved`` is what enforces the
discipline: a ``NOT NULL`` column would make the clearing this docstring
requires impossible, and a merely nullable column with no check would let a
``reserved`` row exist with no token at all.

``state`` is the four values A1 names, ``reserved`` the only non-terminal one —
mirrors ``ck_job_status``'s enumeration idiom (migration ``0001``) and
``smartmatch_domain.spend.SpendReservationState``, which the drift test holds
this name to account against.

``review_flagged_at`` is the dedup marker for T-08's escalation requirement —
*"escalation row created once per failure class per window, not per
failure"*. This migration adds no ``discovery_review_item`` table (that table
does not exist in this schema yet, and creating one is outside this migration's
scope); ``review_flagged_at`` is the minimal, local mechanism that guarantees
at most one finding is ever emitted for a given reservation, via a guarded
``UPDATE ... WHERE review_flagged_at IS NULL``. A durable, tenant-window-rate-
limited escalation queue is future work once ``discovery_review_item`` lands.

Single transaction, no backfill
------------------------------------
Both tables are new. This is ``0009``'s and ``0008``'s shape, not ``0006``'s:
nothing existing to lock or backfill, no reason to split expand from contract
(v1.1 §4.2, ADR-0009). ``transaction_per_migration=True``
(``db/migrations/env.py``) holds the whole thing in one transaction.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0010_spend_reservation"
down_revision = "0009_engagement_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create ``spend_ceiling_bucket`` and ``spend_reservation``."""
    op.create_table(
        "spend_ceiling_bucket",
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        # 'job' | 'tenant_day' | 'tenant_month' — the three ceilings A1's
        # obligation 1 debits atomically. See the module docstring.
        sa.Column("bucket_type", sa.Text(), nullable=False),
        # A normalized key: job:<job_id>, tenant-day:<tenant_id>:<date>,
        # tenant-month:<tenant_id>:<year>-<month>. Derived by
        # smartmatch_domain.spend, never constructed here.
        sa.Column("bucket_key", sa.Text(), nullable=False),
        # Fixed at first write for this bucket; never rewritten by a later
        # reservation against the same key. See the module docstring.
        sa.Column("ceiling", sa.Numeric(12, 4), nullable=False),
        sa.Column("reserved", sa.Numeric(12, 4), nullable=False, server_default=sa.text("0")),
        sa.Column("spent", sa.Numeric(12, 4), nullable=False, server_default=sa.text("0")),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint(
            "tenant_id", "bucket_type", "bucket_key", name="pk_spend_ceiling_bucket"
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"], ondelete="RESTRICT"),
        sa.CheckConstraint(
            "bucket_type IN ('job','tenant_day','tenant_month')",
            name="ck_spend_ceiling_bucket_type",
        ),
        # Mirrors ck_budget_non_negative / ck_budget_ceiling_non_negative
        # (tenant_budget, migration 0001). Deliberately no
        # "reserved + spent <= ceiling" — see the module docstring for why an
        # overage must be allowed to post past the ceiling, once, recorded
        # rather than truncated.
        sa.CheckConstraint(
            "reserved >= 0 AND spent >= 0", name="ck_spend_ceiling_bucket_non_negative"
        ),
        sa.CheckConstraint("ceiling >= 0", name="ck_spend_ceiling_bucket_ceiling_non_negative"),
    )

    op.create_table(
        "spend_reservation",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        # Deterministic (smartmatch_domain.spend.derive_work_key), globally
        # unique so a retry or redelivery of the same unit of work finds this
        # row instead of reserving a second time.
        sa.Column("work_key", sa.Text(), nullable=False),
        sa.Column("job_bucket_key", sa.Text(), nullable=False),
        sa.Column("tenant_day_bucket_key", sa.Text(), nullable=False),
        sa.Column("tenant_month_bucket_key", sa.Text(), nullable=False),
        # The reserved maximum. NUMERIC(12,4), matching tenant_budget — never
        # FLOAT (A1).
        sa.Column("estimate", sa.Numeric(12, 4), nullable=False),
        # NULL until reconciled, timed out, or swept. See actual_is_estimated.
        sa.Column("actual_cost", sa.Numeric(12, 4), nullable=True),
        # True when actual_cost is the reserved maximum written by a timeout
        # or the sweep, not a real reported cost. A1: "an estimated dollar
        # amount must never be recorded, displayed, or reported as an actual
        # one."
        sa.Column(
            "actual_is_estimated", sa.Boolean(), nullable=False, server_default=sa.text("false")
        ),
        sa.Column("state", sa.Text(), nullable=False, server_default=sa.text("'reserved'")),
        # Present exactly while reserved; cleared on every terminal transition
        # — the same discipline J17 established for outbox_record.lease_token,
        # enforced below by ck_spend_reservation_lease_token_iff_reserved.
        sa.Column("lease_token", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=False),
        # T-08's dedup marker. See the module docstring — no
        # discovery_review_item table exists yet; this is the minimal local
        # mechanism guaranteeing at most one finding per reservation.
        sa.Column("review_flagged_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        # Set on any reserved -> {reconciled, expired_spent, released}
        # transition. NULL while reserved.
        sa.Column("settled_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name="spend_reservation_pkey"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("work_key", name="uq_spend_reservation_work_key"),
        sa.CheckConstraint("estimate >= 0", name="ck_spend_reservation_estimate_non_negative"),
        sa.CheckConstraint(
            "actual_cost IS NULL OR actual_cost >= 0",
            name="ck_spend_reservation_actual_non_negative",
        ),
        # Mirrors smartmatch_domain.spend.SpendReservationState. The drift
        # test holds this name to account.
        sa.CheckConstraint(
            "state IN ('reserved','reconciled','expired_spent','released')",
            name="ck_spend_reservation_state",
        ),
        # The lease-token discipline, as a biconditional rather than a
        # NOT NULL: a reserved row always carries the token its holder's
        # receipt is checked against, and a settled row never carries one a
        # late writer could present.
        sa.CheckConstraint(
            "(state = 'reserved') = (lease_token IS NOT NULL)",
            name="ck_spend_reservation_lease_token_iff_reserved",
        ),
    )


def downgrade() -> None:
    """Drop both tables.

    A development tool, not a production rollback path (v1.1 §4.2).
    ``spend_reservation`` has no foreign key to ``spend_ceiling_bucket`` — the
    relationship is by ``bucket_key`` string, not by a database constraint, so
    either order is safe; ``spend_reservation`` is dropped first so the order
    still reads as deliberate.
    """
    op.drop_table("spend_reservation")
    op.drop_table("spend_ceiling_bucket")
