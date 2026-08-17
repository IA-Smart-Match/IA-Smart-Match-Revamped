"""${message}

Revision ID: ${up_revision}
Revises: ${down_revision | comma,n}
Create Date: ${create_date}

Migrations follow expand → migrate → contract (architecture v1.1 §4.2).
A single revision must not both add and remove; the destructive contract step
runs only after the release is fully promoted and stable, so application
rollback never depends on reversing it.

Every tenant-owned table must carry `tenant_id`, a `(tenant_id, id)` unique
constraint, and composite foreign keys `(tenant_id, parent_id)` — tenant
isolation is structural, not a column convention (v1.1 §2.2).
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
${imports if imports else ""}

revision = ${repr(up_revision)}
down_revision = ${repr(down_revision)}
branch_labels = ${repr(branch_labels)}
depends_on = ${repr(depends_on)}


def upgrade() -> None:
    ${upgrades if upgrades else "pass"}


def downgrade() -> None:
    ${downgrades if downgrades else "pass"}
