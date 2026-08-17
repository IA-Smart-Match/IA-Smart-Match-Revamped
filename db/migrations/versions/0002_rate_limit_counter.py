"""Rate-limit counters.

Revision ID: 0002_rate_limit
Revises: 0001_foundation
Create Date: 2026-08-17

Architecture v1.1 §3.4 layer 2: a PostgreSQL transactional limiter keyed on
tenant, subject, and operation. Layer 1 (Cloud Armor, edge) and layer 3 (budget
reservation) live elsewhere.

The counters must be **transactional in PostgreSQL**, not per-instance. Cloud Run
autoscales, so an in-process counter would let each instance independently permit
the full quota — a limit of 30/min silently becomes 30/min *per instance*. That
is the specific failure this table exists to prevent, and it is why Redis is not
required for correctness here (v1.1 §3.5).

Fixed windows rather than a sliding log: a sliding window needs one row per
request, and at pilot volume the storage and vacuum cost is not justified by the
precision. The tradeoff is documented in ``smartmatch_persistence.rate_limit``.

Expand-phase only, per v1.1 §4.2.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0002_rate_limit"
down_revision = "0001_foundation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create the rate-limit counter table."""
    op.create_table(
        "rate_limit_counter",
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        # The thing being limited: a user id, or an IP for unauthenticated
        # endpoints such as login. Text rather than UUID because those are not
        # the same shape, and forcing them into one type would mean encoding an
        # IP as a fake UUID.
        sa.Column("subject", sa.Text(), nullable=False),
        sa.Column("operation", sa.Text(), nullable=False),
        # Truncated window start. Together with the operation's window length
        # this identifies the bucket.
        sa.Column("window_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("count", sa.Integer(), nullable=False, server_default="0"),
        # The whole key is the primary key, so the atomic increment is a single
        # INSERT ... ON CONFLICT against a unique index — no separate lookup, and
        # no window in which two instances both decide there is room.
        sa.PrimaryKeyConstraint(
            "tenant_id", "subject", "operation", "window_start",
            name="pk_rate_limit_counter",
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"], ondelete="CASCADE"),
        sa.CheckConstraint("count >= 0", name="ck_rate_limit_count_non_negative"),
    )

    # Supports the periodic sweep of elapsed windows. Without it the sweep is a
    # sequential scan over a table that grows with every distinct subject.
    op.create_index(
        "ix_rate_limit_window_start", "rate_limit_counter", ["window_start"]
    )


def downgrade() -> None:
    """Drop the rate-limit counter table.

    Usable on a development database. Production rollback never depends on it:
    migrations follow expand → migrate → contract, and the destructive step runs
    only after a release is fully promoted (v1.1 §4.2).
    """
    op.drop_index("ix_rate_limit_window_start", table_name="rate_limit_counter")
    op.drop_table("rate_limit_counter")
