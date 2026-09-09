"""Add published speaker rosters, matching, and invitation tracking.

Revision ID: 0035_speaker_workflow
Revises: 0034_manual_events
Create Date: 2026-09-08
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0035_speaker_workflow"
down_revision = "0034_manual_events"
branch_labels = None
depends_on = None

_UUID = postgresql.UUID(as_uuid=True)
_TS = sa.DateTime(timezone=True)
_STATUSES = (
    "'not_emailed_yet', 'awaiting_response', 'declined', 'ready_for_handoff', "
    "'handed_off', 'awaiting_final_confirmation', 'confirmed', 'withdrawn', "
    "'attended', 'did_not_attend', 'event_cancelled'"
)


def upgrade() -> None:
    op.add_column(
        "managed_event",
        sa.Column("speaker_topics", postgresql.JSONB(), nullable=False, server_default="[]"),
    )
    op.add_column("managed_event", sa.Column("region", sa.Text(), nullable=True))
    op.add_column(
        "managed_event", sa.Column("version", sa.Integer(), nullable=False, server_default="1")
    )
    op.add_column("managed_event", sa.Column("attendance_closed_at", _TS, nullable=True))
    op.add_column("managed_event", sa.Column("attendance_closed_by", _UUID, nullable=True))
    op.add_column("managed_event", sa.Column("cancelled_at", _TS, nullable=True))
    op.add_column("managed_event", sa.Column("cancelled_by", _UUID, nullable=True))
    op.add_column("managed_event", sa.Column("cancellation_reason", sa.Text(), nullable=True))
    op.drop_constraint("ck_managed_event_status", "managed_event", type_="check")
    op.create_check_constraint(
        "ck_managed_event_status", "managed_event", "status IN ('draft', 'published', 'cancelled')"
    )
    op.drop_constraint("ck_managed_event_publishable", "managed_event", type_="check")
    op.create_check_constraint(
        "ck_managed_event_publishable",
        "managed_event",
        "status <> 'published' OR (time_precision <> 'unresolved' AND category IS NOT NULL "
        "AND description IS NOT NULL AND btrim(description) <> '' AND location IS NOT NULL "
        "AND btrim(location) <> '' AND capacity IS NOT NULL AND volunteer_openings IS NOT NULL "
        "AND volunteer_needs IS NOT NULL AND btrim(volunteer_needs) <> '' AND audience IS NOT NULL "
        "AND btrim(audience) <> '' AND contact_name IS NOT NULL AND btrim(contact_name) <> '' "
        "AND contact_email IS NOT NULL AND btrim(contact_email) <> '')",
    )
    op.create_foreign_key(
        "fk_managed_event_attendance_closed_by",
        "managed_event",
        "user_account",
        ["tenant_id", "attendance_closed_by"],
        ["tenant_id", "id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "fk_managed_event_cancelled_by",
        "managed_event",
        "user_account",
        ["tenant_id", "cancelled_by"],
        ["tenant_id", "id"],
        ondelete="RESTRICT",
    )

    op.create_table(
        "speaker",
        sa.Column("id", _UUID, nullable=False),
        sa.Column("tenant_id", _UUID, nullable=False),
        sa.Column("owning_unit_id", _UUID, nullable=False),
        sa.Column("created_by", _UUID, nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("title", sa.Text(), nullable=True),
        sa.Column("company", sa.Text(), nullable=True),
        sa.Column("board_role", sa.Text(), nullable=True),
        sa.Column("expertise_topics", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("home_region", sa.Text(), nullable=True),
        sa.Column("service_regions", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("contact_email", sa.Text(), nullable=True),
        sa.Column("contact_phone", sa.Text(), nullable=True),
        sa.Column("available", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", _TS, nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", _TS, nullable=False, server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("id", name="speaker_pkey"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_speaker_tenant_id"),
        sa.UniqueConstraint("tenant_id", "owning_unit_id", "id", name="uq_speaker_tenant_unit_id"),
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
        sa.CheckConstraint("btrim(name) <> ''", name="ck_speaker_name"),
    )

    op.create_table(
        "speaker_roster",
        sa.Column("tenant_id", _UUID, nullable=False),
        sa.Column("owning_unit_id", _UUID, nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("published_by", _UUID, nullable=True),
        sa.Column("published_at", _TS, nullable=True),
        sa.PrimaryKeyConstraint("tenant_id", "owning_unit_id", name="speaker_roster_pkey"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "owning_unit_id"],
            ["org_unit.tenant_id", "org_unit.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "published_by"],
            ["user_account.tenant_id", "user_account.id"],
            ondelete="RESTRICT",
        ),
    )
    op.create_table(
        "speaker_roster_entry",
        sa.Column("tenant_id", _UUID, nullable=False),
        sa.Column("owning_unit_id", _UUID, nullable=False),
        sa.Column("speaker_id", _UUID, nullable=False),
        sa.Column("roster_version", sa.Integer(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("title", sa.Text(), nullable=True),
        sa.Column("company", sa.Text(), nullable=True),
        sa.Column("board_role", sa.Text(), nullable=True),
        sa.Column("expertise_topics", postgresql.JSONB(), nullable=False),
        sa.Column("home_region", sa.Text(), nullable=True),
        sa.Column("service_regions", postgresql.JSONB(), nullable=False),
        sa.PrimaryKeyConstraint(
            "tenant_id", "owning_unit_id", "speaker_id", name="speaker_roster_entry_pkey"
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "owning_unit_id"],
            ["speaker_roster.tenant_id", "speaker_roster.owning_unit_id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "owning_unit_id", "speaker_id"],
            ["speaker.tenant_id", "speaker.owning_unit_id", "speaker.id"],
            ondelete="CASCADE",
        ),
    )

    op.create_table(
        "speaker_match_run",
        sa.Column("id", _UUID, nullable=False),
        sa.Column("tenant_id", _UUID, nullable=False),
        sa.Column("owning_unit_id", _UUID, nullable=False),
        sa.Column("event_id", _UUID, nullable=False),
        sa.Column("requested_by", _UUID, nullable=False),
        sa.Column("idempotency_key", sa.Text(), nullable=False),
        sa.Column("request_fingerprint", sa.Text(), nullable=False),
        sa.Column("roster_version", sa.Integer(), nullable=False),
        sa.Column("created_at", _TS, nullable=False, server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("id", name="speaker_match_run_pkey"),
        sa.UniqueConstraint("tenant_id", "owning_unit_id", "id", name="uq_speaker_match_run_scope"),
        sa.UniqueConstraint(
            "tenant_id",
            "owning_unit_id",
            "idempotency_key",
            name="uq_speaker_match_run_idempotency",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "owning_unit_id", "event_id"],
            ["managed_event.tenant_id", "managed_event.owning_unit_id", "managed_event.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "requested_by"],
            ["user_account.tenant_id", "user_account.id"],
            ondelete="RESTRICT",
        ),
    )
    op.create_table(
        "speaker_match_result",
        sa.Column("tenant_id", _UUID, nullable=False),
        sa.Column("owning_unit_id", _UUID, nullable=False),
        sa.Column("match_run_id", _UUID, nullable=False),
        sa.Column("speaker_id", _UUID, nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("speaker_name", sa.Text(), nullable=False),
        sa.Column("speaker_title", sa.Text(), nullable=True),
        sa.Column("speaker_company", sa.Text(), nullable=True),
        sa.Column("speaker_board_role", sa.Text(), nullable=True),
        sa.Column("expertise_topics", postgresql.JSONB(), nullable=False),
        sa.Column("home_region", sa.Text(), nullable=True),
        sa.Column("service_regions", postgresql.JSONB(), nullable=False),
        sa.Column("topic_score", sa.Numeric(6, 5), nullable=False),
        sa.Column("proximity_score", sa.Numeric(6, 5), nullable=False),
        sa.Column("total_score", sa.Numeric(6, 5), nullable=False),
        sa.Column("explanations", postgresql.JSONB(), nullable=False),
        sa.PrimaryKeyConstraint(
            "tenant_id",
            "owning_unit_id",
            "match_run_id",
            "speaker_id",
            name="speaker_match_result_pkey",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "owning_unit_id", "match_run_id"],
            [
                "speaker_match_run.tenant_id",
                "speaker_match_run.owning_unit_id",
                "speaker_match_run.id",
            ],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "owning_unit_id", "speaker_id"],
            ["speaker.tenant_id", "speaker.owning_unit_id", "speaker.id"],
            ondelete="RESTRICT",
        ),
    )

    op.create_table(
        "speaker_event",
        sa.Column("id", _UUID, nullable=False),
        sa.Column("tenant_id", _UUID, nullable=False),
        sa.Column("owning_unit_id", _UUID, nullable=False),
        sa.Column("event_id", _UUID, nullable=False),
        sa.Column("speaker_id", _UUID, nullable=False),
        sa.Column("assigned_host_id", _UUID, nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default="not_emailed_yet"),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", _TS, nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", _TS, nullable=False, server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("id", name="speaker_event_pkey"),
        sa.UniqueConstraint("tenant_id", "owning_unit_id", "id", name="uq_speaker_event_scope"),
        sa.UniqueConstraint(
            "tenant_id", "owning_unit_id", "event_id", "speaker_id", name="uq_speaker_event_pair"
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "owning_unit_id", "event_id"],
            ["managed_event.tenant_id", "managed_event.owning_unit_id", "managed_event.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "owning_unit_id", "speaker_id"],
            ["speaker.tenant_id", "speaker.owning_unit_id", "speaker.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "assigned_host_id"],
            ["user_account.tenant_id", "user_account.id"],
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(f"status IN ({_STATUSES})", name="ck_speaker_event_status"),
    )
    op.create_table(
        "speaker_shortlist_submission",
        sa.Column("id", _UUID, nullable=False),
        sa.Column("tenant_id", _UUID, nullable=False),
        sa.Column("owning_unit_id", _UUID, nullable=False),
        sa.Column("match_run_id", _UUID, nullable=False),
        sa.Column("idempotency_key", sa.Text(), nullable=False),
        sa.Column("request_fingerprint", sa.Text(), nullable=False),
        sa.Column("created_at", _TS, nullable=False, server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("id", name="speaker_shortlist_submission_pkey"),
        sa.UniqueConstraint(
            "tenant_id",
            "owning_unit_id",
            "idempotency_key",
            name="uq_speaker_shortlist_idempotency",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "owning_unit_id", "match_run_id"],
            [
                "speaker_match_run.tenant_id",
                "speaker_match_run.owning_unit_id",
                "speaker_match_run.id",
            ],
            ondelete="CASCADE",
        ),
    )
    op.create_table(
        "speaker_event_history",
        sa.Column("id", _UUID, nullable=False),
        sa.Column("tenant_id", _UUID, nullable=False),
        sa.Column("owning_unit_id", _UUID, nullable=False),
        sa.Column("speaker_event_id", _UUID, nullable=False),
        sa.Column("from_status", sa.Text(), nullable=True),
        sa.Column("to_status", sa.Text(), nullable=False),
        sa.Column("action_kind", sa.Text(), nullable=False),
        sa.Column("actor_id", _UUID, nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("correction_reason", sa.Text(), nullable=True),
        sa.Column("idempotency_key", sa.Text(), nullable=True),
        sa.Column("created_at", _TS, nullable=False, server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("id", name="speaker_event_history_pkey"),
        sa.UniqueConstraint(
            "tenant_id",
            "owning_unit_id",
            "idempotency_key",
            name="uq_speaker_event_history_idempotency",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "owning_unit_id", "speaker_event_id"],
            ["speaker_event.tenant_id", "speaker_event.owning_unit_id", "speaker_event.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "actor_id"],
            ["user_account.tenant_id", "user_account.id"],
            ondelete="RESTRICT",
        ),
    )
    op.create_table(
        "speaker_event_note",
        sa.Column("id", _UUID, nullable=False),
        sa.Column("tenant_id", _UUID, nullable=False),
        sa.Column("owning_unit_id", _UUID, nullable=False),
        sa.Column("speaker_event_id", _UUID, nullable=False),
        sa.Column("actor_id", _UUID, nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("created_at", _TS, nullable=False, server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("id", name="speaker_event_note_pkey"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "owning_unit_id", "speaker_event_id"],
            ["speaker_event.tenant_id", "speaker_event.owning_unit_id", "speaker_event.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "actor_id"],
            ["user_account.tenant_id", "user_account.id"],
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint("btrim(body) <> ''", name="ck_speaker_event_note_body"),
    )


def downgrade() -> None:
    for table in (
        "speaker_event_note",
        "speaker_event_history",
        "speaker_shortlist_submission",
        "speaker_event",
        "speaker_match_result",
        "speaker_match_run",
        "speaker_roster_entry",
        "speaker_roster",
        "speaker",
    ):
        op.drop_table(table)
    op.drop_constraint("ck_managed_event_status", "managed_event", type_="check")
    op.drop_constraint("fk_managed_event_cancelled_by", "managed_event", type_="foreignkey")
    op.drop_constraint("fk_managed_event_attendance_closed_by", "managed_event", type_="foreignkey")
    op.drop_constraint("ck_managed_event_publishable", "managed_event", type_="check")
    op.create_check_constraint(
        "ck_managed_event_status", "managed_event", "status IN ('draft', 'published')"
    )
    op.create_check_constraint(
        "ck_managed_event_publishable",
        "managed_event",
        "status = 'draft' OR (time_precision <> 'unresolved' AND category IS NOT NULL "
        "AND description IS NOT NULL AND btrim(description) <> '' AND location IS NOT NULL "
        "AND btrim(location) <> '' AND capacity IS NOT NULL AND volunteer_openings IS NOT NULL "
        "AND volunteer_needs IS NOT NULL AND btrim(volunteer_needs) <> '' AND audience IS NOT NULL "
        "AND btrim(audience) <> '' AND contact_name IS NOT NULL AND btrim(contact_name) <> '' "
        "AND contact_email IS NOT NULL AND btrim(contact_email) <> '')",
    )
    for column in (
        "cancellation_reason",
        "cancelled_by",
        "cancelled_at",
        "attendance_closed_by",
        "attendance_closed_at",
        "version",
        "region",
        "speaker_topics",
    ):
        op.drop_column("managed_event", column)
