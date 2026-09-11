"""Move managed events to Event Hosts and support showcase-linked records.

Revision ID: 0037_host_events_showcase
Revises: 0036_speaker_workflow
Create Date: 2026-09-10
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0037_host_events_showcase"
down_revision = "0036_speaker_workflow"
branch_labels = None
depends_on = None

_UUID = postgresql.UUID(as_uuid=True)


def upgrade() -> None:
    op.add_column("managed_event", sa.Column("catalog_event_id", _UUID, nullable=True))
    op.create_unique_constraint(
        "uq_managed_event_catalog_event", "managed_event", ["tenant_id", "catalog_event_id"]
    )
    op.create_foreign_key(
        "fk_managed_event_catalog_event",
        "managed_event",
        "event",
        ["tenant_id", "catalog_event_id"],
        ["tenant_id", "id"],
        ondelete="RESTRICT",
    )

    op.add_column("speaker", sa.Column("account_id", _UUID, nullable=True))
    op.create_unique_constraint(
        "uq_speaker_unit_account",
        "speaker",
        ["tenant_id", "owning_unit_id", "account_id"],
    )
    op.create_foreign_key(
        "fk_speaker_account",
        "speaker",
        "user_account",
        ["tenant_id", "account_id"],
        ["tenant_id", "id"],
        ondelete="RESTRICT",
    )

    op.drop_constraint("ck_managed_event_source_kind", "managed_event", type_="check")
    op.create_check_constraint(
        "ck_managed_event_source_kind",
        "managed_event",
        "source_kind IN ('manual', 'synthetic')",
    )
    op.drop_constraint("ck_managed_event_publishable", "managed_event", type_="check")
    op.create_check_constraint(
        "ck_managed_event_publishable",
        "managed_event",
        "status <> 'published' OR (time_precision <> 'unresolved' "
        "AND location IS NOT NULL AND btrim(location) <> '' "
        "AND volunteer_openings BETWEEN 1 AND 3 "
        "AND jsonb_typeof(speaker_topics) = 'array' "
        "AND jsonb_array_length(speaker_topics) > 0)",
    )


def downgrade() -> None:
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
    op.drop_constraint("ck_managed_event_source_kind", "managed_event", type_="check")
    op.create_check_constraint("ck_managed_event_source_kind", "managed_event", "source_kind = 'manual'")
    op.drop_constraint("fk_speaker_account", "speaker", type_="foreignkey")
    op.drop_constraint("uq_speaker_unit_account", "speaker", type_="unique")
    op.drop_column("speaker", "account_id")
    op.drop_constraint("fk_managed_event_catalog_event", "managed_event", type_="foreignkey")
    op.drop_constraint("uq_managed_event_catalog_event", "managed_event", type_="unique")
    op.drop_column("managed_event", "catalog_event_id")
