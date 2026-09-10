"""Manual event detail and per-event external feedback QR.

Ratified by ``docs/decisions/manual-events-and-feedback-qr-2026-09-07.md``:
"Administrators may create, edit, and publish events directly in Smart Match
for an authorized organizational unit." and "Each event may have one feedback
QR code."

Manual events are rows in the canonical ``event`` table (migration ``0017``),
written through ``smartmatch_persistence.events.EventRepository`` with
``origin='coordinator_entry'`` and ``filed_by_user_id`` set — that origin value
and that column already exist (migrations ``0017``/``0033``) and are unchanged
here. This revision adds no column to ``event`` and adds no new origin value:
"a coordinator typed this event in" is exactly what ``coordinator_entry``
already means, so main's own catalog reads (``GET /v1/units/{unit_id}/events``)
list a manually created event with provenance for free.

What ``event`` genuinely lacks for a manually filed event — category, a
free-text location, capacity, volunteer openings/needs, audience, contact
details, speaker topics, region — goes in the new 1:1 side table
``event_manual_detail`` below, keyed on ``event.id``. This is the plan-gate
review's finding 2 (PORT_PLAN.md §0.5): a separate ``managed_event`` table
would be invisible to main's catalog and would duplicate the identity/
temporal/provenance machinery ``event`` already has; a side table for the
event-only extras is not.

The feedback QR pair, ``event_feedback_qr`` and ``event_feedback_qr_open``,
mirrors PR #125's design exactly (down to constraint names, so
``tests/unit/test_manual_events.py`` can hold the repository to them):

* ``event_feedback_qr`` — one row per event (``uq_event_feedback_qr_event``),
  a stable opaque ``public_token`` used by the public redirect
  (``GET /q/{public_token}``), and the destination URL an administrator
  supplies. Changing the destination never rotates the token, so a printed QR
  code keeps working.
* ``event_feedback_qr_open`` — records only ``qr_id`` and ``opened_at``. No
  IP address, user agent, referrer, or cookie column exists on this table by
  construction (decision doc: "no cookie, IP address, user agent, referrer,
  or other visitor identifier").

Expand-only
=============
Three new tables. Nothing on ``event`` or any other existing table is
altered, dropped, renamed, or backfilled — safe under a rolling deploy per
v1.1 §4.2.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0035_manual_event_detail"
down_revision = "0034_cba_meeting"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create ``event_manual_detail``, ``event_feedback_qr``, ``event_feedback_qr_open``."""
    op.create_table(
        "event_manual_detail",
        sa.Column("event_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("owning_unit_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("category", sa.Text, nullable=True),
        sa.Column("location", sa.Text, nullable=True),
        sa.Column("capacity", sa.Integer, nullable=True),
        sa.Column("volunteer_openings", sa.Integer, nullable=True),
        sa.Column("volunteer_needs", sa.Text, nullable=True),
        sa.Column("audience", sa.Text, nullable=True),
        sa.Column("contact_name", sa.Text, nullable=True),
        sa.Column("contact_email", sa.Text, nullable=True),
        sa.Column(
            "speaker_topics",
            postgresql.JSONB,
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("region", sa.Text, nullable=True),
        sa.Column("idempotency_key", sa.Text, nullable=True),
        sa.Column("request_fingerprint", sa.Text, nullable=True),
        sa.Column("version", sa.Integer, nullable=False, server_default="1"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")
        ),
        sa.PrimaryKeyConstraint("event_id", name="event_manual_detail_pkey"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "event_id"],
            ["event.tenant_id", "event.id"],
            ondelete="CASCADE",
            name="fk_event_manual_detail_event",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "owning_unit_id"],
            ["org_unit.tenant_id", "org_unit.id"],
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "owning_unit_id",
            "idempotency_key",
            name="uq_event_manual_detail_idempotency",
        ),
        sa.CheckConstraint(
            "capacity IS NULL OR capacity >= 0", name="ck_event_manual_detail_capacity"
        ),
        sa.CheckConstraint(
            "volunteer_openings IS NULL OR volunteer_openings >= 0",
            name="ck_event_manual_detail_volunteer_openings",
        ),
        sa.CheckConstraint("version >= 1", name="ck_event_manual_detail_version"),
    )
    op.create_index(
        "ix_event_manual_detail_unit",
        "event_manual_detail",
        ["tenant_id", "owning_unit_id"],
    )

    op.create_table(
        "event_feedback_qr",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("owning_unit_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("event_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("public_token", sa.Text, nullable=False),
        sa.Column("destination_url", sa.Text, nullable=False),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")
        ),
        sa.PrimaryKeyConstraint("id", name="event_feedback_qr_pkey"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "event_id"],
            ["event.tenant_id", "event.id"],
            ondelete="CASCADE",
            name="fk_event_feedback_qr_event",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "owning_unit_id"],
            ["org_unit.tenant_id", "org_unit.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "created_by"],
            ["user_account.tenant_id", "user_account.id"],
            ondelete="RESTRICT",
            name="fk_event_feedback_qr_created_by",
        ),
        sa.UniqueConstraint("tenant_id", "event_id", name="uq_event_feedback_qr_event"),
        sa.UniqueConstraint("public_token", name="uq_event_feedback_qr_public_token"),
        sa.CheckConstraint(
            "length(btrim(public_token)) >= 20 AND length(public_token) <= 100",
            name="ck_event_feedback_qr_token_shape",
        ),
        sa.CheckConstraint(
            "length(btrim(destination_url)) > 0 AND length(destination_url) <= 2048",
            name="ck_event_feedback_qr_destination_shape",
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
            name="fk_event_feedback_qr_open_qr",
        ),
    )
    op.create_index(
        "ix_event_feedback_qr_open_qr",
        "event_feedback_qr_open",
        ["tenant_id", "qr_id", "opened_at"],
    )


def downgrade() -> None:
    """Drop all three tables, in dependency order.

    A development tool, not a production rollback path (v1.1 §4.2).
    """
    op.drop_index("ix_event_feedback_qr_open_qr", table_name="event_feedback_qr_open")
    op.drop_table("event_feedback_qr_open")
    op.drop_table("event_feedback_qr")
    op.drop_index("ix_event_manual_detail_unit", table_name="event_manual_detail")
    op.drop_table("event_manual_detail")
