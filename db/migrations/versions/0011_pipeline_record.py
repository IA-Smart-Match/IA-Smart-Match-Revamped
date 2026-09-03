"""``pipeline_record`` — the S12 funnel's evidence (P8 card O2).

Revision ID: 0011_pipeline_record
Revises: 0010_spend_reservation
Create Date: 2026-09-02

ADR-0011, backlog S12, plan `docs/plans/2026-08-28-opportunities-s12-plan.md`
card O2. The five Pipeline metrics in ``smartmatch_domain.metrics`` have
carried ``PIPELINE_UNKNOWN_REASON`` — "No evidence source yet: S12 Pipeline
persistence is not started" — since the register was written. This table is
that evidence source. **It does not by itself change any metric**: binding the
owning query ``pipeline_funnel_rows_v1`` to these rows is card O3, in
``services/api/smartmatch_api/routers/metrics.py``, and until that lands every
Pipeline metric still answers unknown, which stays the truthful answer.

One row per (student, opportunity) journey
-------------------------------------------
``uq_pipeline_record_subject_opportunity`` on
``(tenant_id, subject_id, opportunity_event_id)`` is the same argument
``uq_attendance_record_subject_event`` (0009) makes one table over: a second
row for the same student and the same opportunity is not a harmless
re-recording, it is a second count in *every* funnel stage that row has
reached. ADR-0011 rule 3 requires the drill-down to equal the aggregate, and
both would be inflated identically and consistently — a wrong number that
audits as correct, which is worse than one that does not.

Stages are timestamps, not a status column, and that is the design decision
--------------------------------------------------------------------------
The register's wording is "records that have reached the Matched stage **or a
later stage**". A single ``status`` column answers *where a record is now*, and
those are different questions the moment a journey stalls: a student who was
confirmed and then did not attend has still reached Confirmed, and a funnel
built on the current status alone would silently un-count them when they
stopped progressing. So each stage carries its own nullable
``<stage>_at``, "reached" is ``IS NOT NULL``, and the current stage is derived
as the latest one set rather than stored twice.

``matched_at`` is ``NOT NULL``: a record enters this table because a match
exists, so a row with no ``matched_at`` would be a pipeline record for a
pipeline that never started.

Two CHECKs, because a funnel that widens is an incoherent number
----------------------------------------------------------------
``ck_pipeline_record_stage_prefix`` requires each stage's timestamp to be
accompanied by the one before it. Without it the database will hold a row that
was contacted but never matched, and the Pipeline surface then shows Contacted
greater than Matched — a funnel wider at the bottom than the top. ADR-0011
exists to stop exactly the numbers a viewer cannot reconcile, and this one
cannot be reconciled by any amount of drill-down, because each individual row
is faithfully reported.

Its first clause — Contacted requires Matched — cannot fire while
``matched_at`` is ``NOT NULL``, and is kept anyway: it states the rule
completely, and it is what would still hold the line if a later migration ever
relaxed that column. The test file names it as unreachable rather than
pretending to cover it.

``ck_pipeline_record_stage_order`` requires the timestamps to be
non-decreasing. The prefix rule alone admits a row confirmed before it was
matched, which is the same incoherence expressed in time rather than in
presence, and it becomes visible the moment anything reports on *when* a stage
was reached rather than only how many rows reached it.

Attendance is cited, never asserted
------------------------------------
``attended_attendance_id`` is a composite foreign key to ``attendance_record``,
``ON DELETE RESTRICT``, and ``ck_pipeline_record_attendance_evidence`` makes it
a biconditional with ``attended_at`` — the idiom
``ck_redrive_authorship_complete`` (0001) and
``ck_spend_reservation_lease_token_iff_reserved`` (0010) already use.

ADR-0013 says attendance is recorded evidence and the only input to points; the
Attended stage of this funnel is a claim about the same fact, and a claim that
cites nothing is the fabricated-field defect (Fix #15, H21) reproduced one
table over. So this schema cannot hold a record that says it attended without
naming the attendance row that says so, and cannot hold one that names an
attendance row without claiming the stage. RESTRICT keeps the citation
readable: deleting the evidence out from under the claim would leave a funnel
count nothing could explain.

``opportunity_event_id`` has no foreign key, and P6 is why
-----------------------------------------------------------
There is still no ``event`` table (0009 gives the full reasoning for
``attendance_record.event_id``, and it is unchanged here): the events plan P6
owns it. A constraint referencing a table that does not exist cannot be
written, and a loosely-typed placeholder would misstate the guarantee rather
than omit it. **Whichever migration adds ``event`` should add this foreign key
and ``attendance_record``'s together.**

The dependency this leaves is recorded rather than worked around. The P8
definition (`docs/decisions/p8-opportunities-decision-draft.md` §3, closed
2026-09-02) counts import-origin opportunities now and crawler-origin ones only
once P6's persistence lands; nothing in this table distinguishes the two, and
nothing here should — the origin is a property of the event row, and inventing
a column for it before the table exists would be this migration guessing at
P6's schema.

No ``uq_pipeline_record_tenant_id``
------------------------------------
Nothing in this migration references this table, so per 0008's rule for
``review_item`` the anchoring unique constraint is not added on spec. Whichever
migration first needs to point at a pipeline record adds it then.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0011_pipeline_record"
down_revision = "0010_spend_reservation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create ``pipeline_record`` and the index its owning query reads."""
    op.create_table(
        "pipeline_record",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        # A5-shaped, as job.owning_unit_id (0006), import_batch (0008) and
        # attendance_record (0009) are: the unit every authorization decision
        # about this row is scoped against, and the unit the metric is read
        # per. Written here rather than joined back through the event later,
        # which is 0008's reasoning and applies unchanged.
        sa.Column("owning_unit_id", postgresql.UUID(as_uuid=True), nullable=False),
        # The student whose journey this is.
        sa.Column("subject_id", postgresql.UUID(as_uuid=True), nullable=False),
        # The opportunity. No foreign key: no event table exists yet (P6).
        sa.Column("opportunity_event_id", postgresql.UUID(as_uuid=True), nullable=False),
        # The five stages, as the times they were reached. NOT NULL only for
        # the first: a record exists because a match does.
        sa.Column(
            "matched_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("contacted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("attended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("member_inquiry_at", sa.DateTime(timezone=True), nullable=True),
        # The attendance row the Attended stage cites. Biconditional with
        # attended_at below.
        sa.Column("attended_attendance_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        # This row does change — a stage is reached by an UPDATE writing its
        # timestamp — so unlike point_ledger_entry (0009) it carries an
        # updated_at, and carrying one is a statement that mutation is
        # expected here rather than an oversight.
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("id", name="pipeline_record_pkey"),
        sa.UniqueConstraint(
            "tenant_id",
            "subject_id",
            "opportunity_event_id",
            name="uq_pipeline_record_subject_opportunity",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "owning_unit_id"],
            ["org_unit.tenant_id", "org_unit.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "subject_id"],
            ["user_account.tenant_id", "user_account.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "attended_attendance_id"],
            ["attendance_record.tenant_id", "attendance_record.id"],
            ondelete="RESTRICT",
        ),
        # A stage is reached only if the stage before it was.
        sa.CheckConstraint(
            "(contacted_at IS NULL OR matched_at IS NOT NULL) "
            "AND (confirmed_at IS NULL OR contacted_at IS NOT NULL) "
            "AND (attended_at IS NULL OR confirmed_at IS NOT NULL) "
            "AND (member_inquiry_at IS NULL OR attended_at IS NOT NULL)",
            name="ck_pipeline_record_stage_prefix",
        ),
        # And not before it.
        sa.CheckConstraint(
            "(contacted_at IS NULL OR contacted_at >= matched_at) "
            "AND (confirmed_at IS NULL OR confirmed_at >= contacted_at) "
            "AND (attended_at IS NULL OR attended_at >= confirmed_at) "
            "AND (member_inquiry_at IS NULL OR member_inquiry_at >= attended_at)",
            name="ck_pipeline_record_stage_order",
        ),
        # An attendance claim names its evidence, and evidence is never
        # carried without the claim it supports.
        sa.CheckConstraint(
            "(attended_at IS NULL) = (attended_attendance_id IS NULL)",
            name="ck_pipeline_record_attendance_evidence",
        ),
    )

    # The owning query reads one unit's records within one tenant, which is
    # every funnel stage's filter (ADR-0011: one query serves the aggregate and
    # the drill-down, so there is one access path to index for).
    op.create_index(
        "ix_pipeline_record_unit",
        "pipeline_record",
        ["tenant_id", "owning_unit_id"],
    )


def downgrade() -> None:
    """Drop the table.

    A development tool, not a production rollback path (v1.1 §4.2). Nothing
    references ``pipeline_record``, so the drop is unconditional; the index
    goes with the table.
    """
    op.drop_table("pipeline_record")
