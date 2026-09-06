"""Remove the unauthorized ledger reversal-target prototype.

Revision ID: 0015_remove_ledger_reversal
Revises: 0014_ledger_reversal_target
Create Date: 2026-09-03

Migration 0014 remains in history because developer databases may already have
applied it. This compensating revision restores the authorized 0009 ledger
shape. Its downgrade recreates exactly the column and constraints added by
0014, permitting development migration round trips without rewriting history.

This is a narrow rolling-deploy exception to ADR-0009. ``CONTRIBUTING.md``
records that nothing in this repository is deployed, so no deployed release or
older running process ever included the ``c075817`` rewards repository or
migration 0014; no runtime can depend on this column. Revision 0015 exists only
for local developer database continuity. If 0014 had deployed, contract removal
would require a later release after older processes stopped depending on it.
This exception applies only to the approved compensating migration, not to
other schema contract removals.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0015_remove_ledger_reversal"
down_revision = "0014_ledger_reversal_target"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Restore the authorized pre-0014 point-ledger structure."""
    op.drop_constraint(
        "fk_point_ledger_entry_reverses_entry",
        "point_ledger_entry",
        type_="foreignkey",
    )
    op.drop_column("point_ledger_entry", "reverses_entry_id")
    op.drop_constraint(
        "uq_point_ledger_entry_tenant_id",
        "point_ledger_entry",
        type_="unique",
    )


def downgrade() -> None:
    """Recreate exactly the structure introduced by migration 0014."""
    op.create_unique_constraint(
        "uq_point_ledger_entry_tenant_id",
        "point_ledger_entry",
        ["tenant_id", "id"],
    )
    op.add_column(
        "point_ledger_entry",
        sa.Column("reverses_entry_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_point_ledger_entry_reverses_entry",
        "point_ledger_entry",
        "point_ledger_entry",
        ["tenant_id", "reverses_entry_id"],
        ["tenant_id", "id"],
        ondelete="RESTRICT",
    )
