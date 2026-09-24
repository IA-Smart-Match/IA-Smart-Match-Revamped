"""A Speaker booking can be cancelled: a transition on ``pipeline_record``, not a delete.

Revision ID: 0040_booking_cancellation
Revises: 0039_speaker_portal
Create Date: 2026-09-23

The revision id is shorter than the filename on purpose: ``alembic_version`` is
``varchar(32)``, and ``0040_speaker_booking_cancellation`` is 33 characters. The
precedent is ``0024_cba_classification_schema.py``, whose id is
``0024_cba_classification``.

B26 T8a (parent plan ``docs/plans/2026-09-22-b26-self-service-availability-plan.md``
§3.3; track plan ``docs/plans/b26-tracks/T8a-plan.md`` §2).

Why a transition
================
A Speaker booking is a ``pipeline_record`` row that reached Confirmed. Before this
revision nothing could cancel one: the only way to take a booking back was to
delete the journey, which would also delete the Matched and Contacted facts it
carries. The precedent this follows is ``event_registration.status`` — the row
is kept, the cancellation is recorded on it, and a repeat is a no-op.

The two columns
===============
``cancelled_at`` and ``cancelled_by_user_id`` — both nullable, **no default**.
Every row that exists when this runs keeps NULL in both: nobody cancelled it.
``cancelled_at`` comes from the server clock (owner ruling C5), and the actor is
the principal who pressed Cancel. They are set together or not at all
(``ck_pipeline_record_cancellation_actor``).

The four CHECKs
===============
* ``ck_pipeline_record_cancellation_actor`` — time and actor are one fact.
* ``ck_pipeline_record_cancellation_confirmed`` — only a confirmed journey is a
  booking, so only it can be cancelled.
* ``ck_pipeline_record_cancellation_order`` — a cancellation never precedes the
  confirmation it cancels (C4).
* ``ck_pipeline_record_cancellation_not_attended`` — attended and cancelled
  exclude each other (C2). Attendance is evidenced, so the talk happened; and
  ``completed`` is counted from ``attended_at`` alone, so a row that was both
  would not drop out of anything.

Every CHECK is partial on ``cancelled_at IS NULL``, so every existing row
satisfies it without being rewritten. ``ck_pipeline_record_stage_prefix`` and
``ck_pipeline_record_stage_order`` are unchanged.

The key and the index
=====================
``fk_pipeline_record_cancelled_by_user`` is composite, ``(tenant_id,
cancelled_by_user_id)`` → ``user_account (tenant_id, id)``, the shape every
account reference in this schema uses (``0033``'s ``fk_event_filed_by_user``).
``ON DELETE RESTRICT``: deleting an account that cancelled a booking is an error.

``ix_pipeline_record_cancelled_by`` is partial on ``cancelled_by_user_id IS NOT
NULL``. It supports the RESTRICT check when an account is deleted and carries
no uncancelled row.

Expand only
===========
Two nullable columns with no default, four partial CHECKs, one key, one partial
index. **No UPDATE and no DML of any kind** (ADR-0009). The previous release runs
unchanged against this schema: it neither reads nor writes these columns.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0040_booking_cancellation"
down_revision = "0039_speaker_portal"
branch_labels = None
depends_on = None

_TABLE = "pipeline_record"

#: ``(name, expression)`` in the order they are added; dropped in reverse.
_CHECKS = (
    (
        "ck_pipeline_record_cancellation_actor",
        "(cancelled_at IS NULL) = (cancelled_by_user_id IS NULL)",
    ),
    (
        "ck_pipeline_record_cancellation_confirmed",
        "cancelled_at IS NULL OR confirmed_at IS NOT NULL",
    ),
    (
        "ck_pipeline_record_cancellation_order",
        "cancelled_at IS NULL OR cancelled_at >= confirmed_at",
    ),
    (
        "ck_pipeline_record_cancellation_not_attended",
        "cancelled_at IS NULL OR attended_at IS NULL",
    ),
)


def upgrade() -> None:
    """Add the columns, the key, the CHECKs and the index. No row is written."""
    op.add_column(_TABLE, sa.Column("cancelled_at", sa.TIMESTAMP(timezone=True), nullable=True))
    op.add_column(
        _TABLE,
        sa.Column("cancelled_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
    )

    op.create_foreign_key(
        "fk_pipeline_record_cancelled_by_user",
        _TABLE,
        "user_account",
        ["tenant_id", "cancelled_by_user_id"],
        ["tenant_id", "id"],
        ondelete="RESTRICT",
    )

    for name, expression in _CHECKS:
        op.create_check_constraint(name, _TABLE, expression)

    op.create_index(
        "ix_pipeline_record_cancelled_by",
        _TABLE,
        ["tenant_id", "cancelled_by_user_id"],
        postgresql_where=sa.text("cancelled_by_user_id IS NOT NULL"),
    )


def downgrade() -> None:
    """Drop the index, the four CHECKs, the key, then both columns.

    A development tool, not a production rollback path (v1.1 §4.2), with the same
    caveat as ``0033``: it discards every recorded cancellation, and nothing else
    holds a copy. Every cancelled booking reads as a live booking again.
    """
    op.drop_index("ix_pipeline_record_cancelled_by", table_name=_TABLE)
    for name, _expression in reversed(_CHECKS):
        op.drop_constraint(name, _TABLE, type_="check")
    op.drop_constraint("fk_pipeline_record_cancelled_by_user", _TABLE, type_="foreignkey")
    op.drop_column(_TABLE, "cancelled_by_user_id")
    op.drop_column(_TABLE, "cancelled_at")
