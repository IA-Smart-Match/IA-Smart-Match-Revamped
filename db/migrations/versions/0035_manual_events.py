"""Add manually managed events and external-feedback QR redirects.

Revision ID: 0035_manual_events
Revises: 0034_cba_meeting
Create Date: 2026-09-07

This is the manual-entry path authorized independently of crawler work. It
does not add a discovery job, network fetch, or crawler persistence path.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0035_manual_events"
down_revision = "0034_cba_meeting"
branch_labels = None
depends_on = None

_CATEGORIES = "'hackathon', 'datathon', 'competition', 'guest lecturer event', 'school event'"


def upgrade() -> None:
    op.create_table(
        "managed_event",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("owning_unit_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("idempotency_key", sa.Text(), nullable=False),
        sa.Column("request_fingerprint", sa.Text(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("normalized_title", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("category", sa.Text(), nullable=True),
        sa.Column("time_precision", sa.Text(), nullable=False, server_default="unresolved"),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("on_date", sa.Date(), nullable=True),
        sa.Column("time_zone", sa.Text(), nullable=True),
        sa.Column("location", sa.Text(), nullable=True),
        sa.Column("capacity", sa.Integer(), nullable=True),
        sa.Column("volunteer_openings", sa.Integer(), nullable=True),
        sa.Column("volunteer_needs", sa.Text(), nullable=True),
        sa.Column("audience", sa.Text(), nullable=True),
        sa.Column("contact_name", sa.Text(), nullable=True),
        sa.Column("contact_email", sa.Text(), nullable=True),
        sa.Column("status", sa.Text(), nullable=False, server_default="draft"),
        sa.Column("source_kind", sa.Text(), nullable=False, server_default="manual"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("id", name="managed_event_pkey"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_managed_event_tenant_id"),
        sa.UniqueConstraint(
            "tenant_id", "owning_unit_id", "id", name="uq_managed_event_tenant_unit_id"
        ),
        sa.UniqueConstraint(
            "tenant_id", "owning_unit_id", "idempotency_key", name="uq_managed_event_idempotency"
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "owning_unit_id"],
            ["org_unit.tenant_id", "org_unit.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "created_by"],
            ["user_account.tenant_id", "user_account.id"],
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            f"category IS NULL OR category IN ({_CATEGORIES})", name="ck_managed_event_category"
        ),
        sa.CheckConstraint(
            "time_precision IN ('exact', 'date_only', 'unresolved')",
            name="ck_managed_event_time_precision",
        ),
        sa.CheckConstraint("status IN ('draft', 'published')", name="ck_managed_event_status"),
        sa.CheckConstraint("source_kind = 'manual'", name="ck_managed_event_source_kind"),
        sa.CheckConstraint("capacity IS NULL OR capacity >= 0", name="ck_managed_event_capacity"),
        sa.CheckConstraint(
            "volunteer_openings IS NULL OR volunteer_openings >= 0",
            name="ck_managed_event_openings_nonnegative",
        ),
        sa.CheckConstraint(
            "capacity IS NULL OR volunteer_openings IS NULL OR volunteer_openings <= capacity",
            name="ck_managed_event_openings_within_capacity",
        ),
        sa.CheckConstraint(
            "(time_precision = 'unresolved' AND starts_at IS NULL "
            "AND ends_at IS NULL AND on_date IS NULL) OR "
            "(time_precision = 'exact' AND starts_at IS NOT NULL "
            "AND on_date IS NULL AND time_zone IS NOT NULL) OR "
            "(time_precision = 'date_only' AND starts_at IS NULL "
            "AND ends_at IS NULL AND on_date IS NOT NULL "
            "AND time_zone IS NOT NULL)",
            name="ck_managed_event_temporal_shape",
        ),
        sa.CheckConstraint(
            "ends_at IS NULL OR ends_at > starts_at", name="ck_managed_event_end_after_start"
        ),
        sa.CheckConstraint(
            "status = 'draft' OR (time_precision <> 'unresolved' AND category IS NOT NULL "
            "AND description IS NOT NULL AND btrim(description) <> '' AND location IS NOT NULL "
            "AND btrim(location) <> '' AND capacity IS NOT NULL AND volunteer_openings IS NOT NULL "
            "AND volunteer_needs IS NOT NULL AND btrim(volunteer_needs) <> '' "
            "AND audience IS NOT NULL "
            "AND btrim(audience) <> '' AND contact_name IS NOT NULL AND btrim(contact_name) <> '' "
            "AND contact_email IS NOT NULL AND btrim(contact_email) <> '')",
            name="ck_managed_event_publishable",
        ),
    )
    op.create_index(
        "uq_managed_event_resolved_identity",
        "managed_event",
        [
            "tenant_id",
            "owning_unit_id",
            "normalized_title",
            sa.text("COALESCE(on_date, (starts_at AT TIME ZONE time_zone)::date)"),
        ],
        unique=True,
        postgresql_where=sa.text("time_precision <> 'unresolved'"),
    )

    op.create_table(
        "event_feedback_qr",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("owning_unit_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("event_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("public_token", sa.Text(), nullable=False),
        sa.Column("destination_url", sa.Text(), nullable=False),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("id", name="event_feedback_qr_pkey"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_event_feedback_qr_tenant_id"),
        sa.UniqueConstraint("tenant_id", "event_id", name="uq_event_feedback_qr_event"),
        sa.UniqueConstraint("public_token", name="uq_event_feedback_qr_public_token"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "owning_unit_id", "event_id"],
            ["managed_event.tenant_id", "managed_event.owning_unit_id", "managed_event.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "created_by"],
            ["user_account.tenant_id", "user_account.id"],
            ondelete="RESTRICT",
        ),
    )

    op.create_table(
        "event_feedback_qr_open",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("qr_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "opened_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")
        ),
        sa.PrimaryKeyConstraint("id", name="event_feedback_qr_open_pkey"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "qr_id"],
            ["event_feedback_qr.tenant_id", "event_feedback_qr.id"],
            ondelete="CASCADE",
        ),
    )
    op.create_index(
        "ix_event_feedback_qr_open_qr_time", "event_feedback_qr_open", ["qr_id", "opened_at"]
    )


def downgrade() -> None:
    op.drop_index("ix_event_feedback_qr_open_qr_time", table_name="event_feedback_qr_open")
    op.drop_table("event_feedback_qr_open")
    op.drop_table("event_feedback_qr")
    op.drop_index("uq_managed_event_resolved_identity", table_name="managed_event")
    op.drop_table("managed_event")
