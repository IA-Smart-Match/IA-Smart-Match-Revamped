"""Speaker self-service availability: the statement and its unavailable windows.

B26 (``docs/plans/2026-09-22-b26-self-service-availability-plan.md`` §3.1,
track plan ``docs/plans/b26-tracks/T2-plan.md`` §2). Two tables and one index;
no row is written.

``speaker_availability``
    One row per speaker who has **said something** about their availability.
    The absence of a row is itself the answer "said nothing" (``UNKNOWN`` in
    ``smartmatch_domain.speaker_availability``), so this revision seeds none: a
    row per existing speaker would turn "said nothing" into "stated, nothing
    blocked" for everyone at once. ``declared_capacity_hours_per_90_days`` has
    no default for the same reason — ``NULL`` is "not stated".

    ``version`` is the optimistic-concurrency token. Two writers exist (the
    speaker and a Speaker Connector), so the repository always checks it; the
    CHECK keeps it from ever reaching ``0``.

``speaker_availability_window``
    The inclusive date ranges a speaker cannot speak on. Each carries its own
    ``created_source`` and ``created_by_user_id``: a range kept across an edit
    keeps its original author. ``uq_speaker_availability_window_range`` is a
    constraint rather than a unique index so the drift test compares it.
    Overlapping but distinct ranges are allowed; merging them is the caller's
    choice, not the schema's.

Tenant isolation is structural: every foreign key is composite on
``tenant_id``. Deleting a ``speaker_profile`` takes its statement and windows
with it (CASCADE); deleting an account that authored either is refused
(RESTRICT), so authorship is never silently erased.

Expand-only: two CREATE TABLEs and one CREATE INDEX. No existing table is
altered and no existing row is read — safe under a rolling deploy per v1.1
§4.2. Transaction handling belongs to ``env.py`` (ADR-0009).
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0038_speaker_availability"
down_revision = "0037_exercise_tables"
branch_labels = None
depends_on = None

_UUID = postgresql.UUID(as_uuid=True)
_TS = sa.DateTime(timezone=True)


def upgrade() -> None:
    """Create ``speaker_availability``, its window table, and the window index."""
    op.create_table(
        "speaker_availability",
        sa.Column("tenant_id", _UUID, nullable=False),
        sa.Column("professional_id", _UUID, nullable=False),
        sa.Column("invitations_paused_until", sa.Date, nullable=True),
        sa.Column("declared_capacity_hours_per_90_days", sa.Numeric(5, 1), nullable=True),
        sa.Column("version", sa.Integer, nullable=False, server_default=sa.text("1")),
        sa.Column("updated_source", sa.Text, nullable=False),
        sa.Column("updated_by_user_id", _UUID, nullable=False),
        sa.Column("created_at", _TS, nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", _TS, nullable=False, server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint(
            "tenant_id", "professional_id", name="speaker_availability_pkey"
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "professional_id"],
            ["speaker_profile.tenant_id", "speaker_profile.professional_id"],
            ondelete="CASCADE",
            name="fk_speaker_availability_profile",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "updated_by_user_id"],
            ["user_account.tenant_id", "user_account.id"],
            ondelete="RESTRICT",
            name="fk_speaker_availability_updated_by",
        ),
        sa.CheckConstraint(
            "updated_source IN ('speaker', 'connector')",
            name="ck_speaker_availability_source",
        ),
        sa.CheckConstraint(
            "declared_capacity_hours_per_90_days IS NULL OR "
            "(declared_capacity_hours_per_90_days > 0 "
            "AND declared_capacity_hours_per_90_days <= 720)",
            name="ck_speaker_availability_capacity",
        ),
        sa.CheckConstraint("version >= 1", name="ck_speaker_availability_version"),
    )

    op.create_table(
        "speaker_availability_window",
        sa.Column("id", _UUID, nullable=False),
        sa.Column("tenant_id", _UUID, nullable=False),
        sa.Column("professional_id", _UUID, nullable=False),
        sa.Column("starts_on", sa.Date, nullable=False),
        sa.Column("ends_on", sa.Date, nullable=False),
        sa.Column("created_source", sa.Text, nullable=False),
        sa.Column("created_by_user_id", _UUID, nullable=False),
        sa.Column("created_at", _TS, nullable=False, server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("id", name="speaker_availability_window_pkey"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "professional_id"],
            ["speaker_availability.tenant_id", "speaker_availability.professional_id"],
            ondelete="CASCADE",
            name="fk_speaker_availability_window_statement",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "created_by_user_id"],
            ["user_account.tenant_id", "user_account.id"],
            ondelete="RESTRICT",
            name="fk_speaker_availability_window_created_by",
        ),
        sa.CheckConstraint("ends_on >= starts_on", name="ck_speaker_availability_window_order"),
        # date - date is an integer number of days; 366 matches
        # smartmatch_domain.speaker_availability.WINDOW_MAX_SPAN_DAYS.
        sa.CheckConstraint(
            "ends_on - starts_on <= 366", name="ck_speaker_availability_window_span"
        ),
        sa.CheckConstraint(
            "created_source IN ('speaker', 'connector')",
            name="ck_speaker_availability_window_source",
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "professional_id",
            "starts_on",
            "ends_on",
            name="uq_speaker_availability_window_range",
        ),
    )

    op.create_index(
        "ix_speaker_availability_window_ends",
        "speaker_availability_window",
        ["tenant_id", "professional_id", "ends_on"],
    )


def downgrade() -> None:
    """Drop the index and both tables; nothing else is touched."""
    op.drop_index(
        "ix_speaker_availability_window_ends", table_name="speaker_availability_window"
    )
    op.drop_table("speaker_availability_window")
    op.drop_table("speaker_availability")
