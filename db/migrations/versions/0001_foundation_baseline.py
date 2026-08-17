"""Foundation baseline schema.

Revision ID: 0001_foundation
Revises:
Create Date: 2026-08-17

Architecture v1.1 §2.2. Establishes the organizational tree, the job/outbox
coordination tables, and the tenant-isolation mechanism the whole schema depends
on.

The central decision, and the reason this migration is worth reading: **tenant
isolation is structural, not a column convention.** Every tenant-owned table
carries a composite unique key ``(tenant_id, id)``, and every foreign key
between tenant-owned tables is composite ``(tenant_id, parent_id)`` referencing
that key. A cross-tenant reference is therefore rejected by the database, not by
application code that might forget the ``WHERE tenant_id = ?`` clause. That is
what closes audit finding C-02.

Only durable organizational units are ``ltree`` nodes. Terms, courses, sections,
and events are resources owned by a unit (v1.1 §2.1), which keeps the tree
stable instead of churning every term.

This migration is **expand-phase only**, per v1.1 §4.2. It creates; it drops
nothing. Application rollback never depends on reversing a destructive step.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0001_foundation"
down_revision = None
branch_labels = None
depends_on = None


class LTree(sa.types.UserDefinedType):  # type: ignore[type-arg]
    """The PostgreSQL ``ltree`` type.

    SQLAlchemy does not ship an ``ltree`` type, and substituting ``TEXT`` would
    quietly cost the subtree operators and the GiST index that make the
    organizational tree queryable at all. Declaring it explicitly keeps the
    column's real type in the schema.
    """

    cache_ok = True

    def get_col_spec(self, **kw: object) -> str:
        return "ltree"


def upgrade() -> None:
    """Create the Foundation schema."""
    op.execute("CREATE EXTENSION IF NOT EXISTS ltree")
    op.execute('CREATE EXTENSION IF NOT EXISTS "uuid-ossp"')

    # ------------------------------------------------------------------
    # Tenancy root
    # ------------------------------------------------------------------
    op.create_table(
        "tenant",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("slug", sa.Text(), nullable=False, unique=True),
        sa.Column("display_name", sa.Text(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False,
            server_default=sa.text("now()"),
        ),
    )

    # ------------------------------------------------------------------
    # Durable organizational tree
    # ------------------------------------------------------------------
    op.create_table(
        "org_unit",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("path", LTree(), nullable=False),
        sa.Column("unit_type", sa.Text(), nullable=False),
        sa.Column("display_name", sa.Text(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"], ondelete="RESTRICT"),
        # The composite key every tenant-owned child references.
        sa.UniqueConstraint("tenant_id", "id", name="uq_org_unit_tenant_id"),
        # A path is unique within a tenant, never globally.
        sa.UniqueConstraint("tenant_id", "path", name="uq_org_unit_tenant_path"),
    )
    op.create_index(
        "ix_org_unit_path_gist", "org_unit", ["path"], postgresql_using="gist"
    )

    # ------------------------------------------------------------------
    # Identity and access
    # ------------------------------------------------------------------
    op.create_table(
        "user_account",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("external_subject", sa.Text(), nullable=False),
        sa.Column("email", sa.Text(), nullable=False),
        sa.Column(
            "suspended", sa.Boolean(), nullable=False, server_default=sa.text("false")
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_user_account_tenant_id"),
        # An IdP subject maps to at most one account per tenant.
        sa.UniqueConstraint(
            "tenant_id", "external_subject", name="uq_user_account_tenant_subject"
        ),
    )

    op.create_table(
        "membership",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("granted_path", LTree(), nullable=False),
        sa.Column("role", sa.Text(), nullable=False),
        sa.Column("valid_from", sa.DateTime(timezone=True), nullable=True),
        sa.Column("valid_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("id"),
        # Composite FK: a membership cannot reference a user in another tenant.
        sa.ForeignKeyConstraint(
            ["tenant_id", "user_id"],
            ["user_account.tenant_id", "user_account.id"],
            ondelete="CASCADE",
        ),
        sa.CheckConstraint(
            "valid_until IS NULL OR valid_from IS NULL OR valid_until > valid_from",
            name="ck_membership_valid_window",
        ),
    )
    op.create_index("ix_membership_user", "membership", ["tenant_id", "user_id"])
    op.create_index(
        "ix_membership_path_gist", "membership", ["granted_path"], postgresql_using="gist"
    )

    op.create_table(
        "resource_grant",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("resource_type", sa.Text(), nullable=False),
        sa.Column("resource_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("effect", sa.Text(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "user_id"],
            ["user_account.tenant_id", "user_account.id"],
            ondelete="CASCADE",
        ),
        sa.CheckConstraint("effect IN ('allow', 'deny')", name="ck_resource_grant_effect"),
        # One decision per (user, resource). A conflicting pair is a data bug;
        # the policy resolves deny-wins, but the schema prevents the ambiguity.
        sa.UniqueConstraint(
            "tenant_id", "user_id", "resource_type", "resource_id",
            name="uq_resource_grant_unique_decision",
        ),
    )

    # ------------------------------------------------------------------
    # Durable jobs, outbox, and coordination (v1.1 §2.4)
    # ------------------------------------------------------------------
    op.create_table(
        "job",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("command_type", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("actor_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("deadline", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_job_tenant_id"),
        # Mirrors smartmatch_domain.jobs.JobState. Kept in sync by
        # tests/integration/test_job_states_match_domain.py.
        sa.CheckConstraint(
            "status IN ('queued','dispatched','running','succeeded','partial',"
            "'failed_provider','failed_budget','failed_policy','cancelled',"
            "'timed_out','redrive_pending','abandoned')",
            name="ck_job_status",
        ),
    )
    op.create_index("ix_job_tenant_status", "job", ["tenant_id", "status"])

    op.create_table(
        "job_event",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("job_id", postgresql.UUID(as_uuid=True), nullable=False),
        # Monotonic per job. SSE event IDs use it, Last-Event-ID reconnects from
        # it, and polling reads the same rows — which is why Redis is not
        # required for reconnect correctness (v1.1 §1.6).
        sa.Column("sequence", sa.BigInteger(), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "job_id"], ["job.tenant_id", "job.id"], ondelete="CASCADE"
        ),
        sa.UniqueConstraint("job_id", "sequence", name="uq_job_event_sequence"),
    )
    op.create_index(
        "ix_job_event_stream", "job_event", ["tenant_id", "job_id", "sequence"]
    )

    op.create_table(
        "outbox_record",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("job_id", postgresql.UUID(as_uuid=True), nullable=False),
        # Deterministic, so a duplicate dispatch creates the same Cloud Tasks
        # task name and is deduplicated by the queue rather than executed twice.
        sa.Column("task_name", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default="pending"),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("dispatch_attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "job_id"], ["job.tenant_id", "job.id"], ondelete="CASCADE"
        ),
        sa.UniqueConstraint("task_name", name="uq_outbox_task_name"),
        sa.CheckConstraint(
            "status IN ('pending','leased','dispatched','failed')",
            name="ck_outbox_status",
        ),
    )
    # Partial index: the dispatcher polls only claimable rows, so the index stays
    # small even as dispatched history accumulates.
    op.create_index(
        "ix_outbox_claimable",
        "outbox_record",
        ["status", "lease_expires_at"],
        postgresql_where=sa.text("status IN ('pending','leased')"),
    )

    op.create_table(
        "idempotency_record",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("idempotency_key", sa.Text(), nullable=False),
        sa.Column("command_type", sa.Text(), nullable=False),
        sa.Column("request_fingerprint", sa.Text(), nullable=False),
        sa.Column("job_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"], ondelete="RESTRICT"),
        # Idempotency keys are scoped per tenant and command type — a key reused
        # across command types is a different operation, not a replay.
        sa.UniqueConstraint(
            "tenant_id", "command_type", "idempotency_key", name="uq_idempotency_scope"
        ),
    )

    op.create_table(
        "redrive_record",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("job_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("attempt_history", postgresql.JSONB(), nullable=False),
        sa.Column("parked_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("redriven_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("redriven_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("redrive_reason", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "job_id"], ["job.tenant_id", "job.id"], ondelete="CASCADE"
        ),
        # Cloud Tasks has no native DLQ, so terminal failures park here and
        # re-drive is an authorized, audited command (v1.1 §1.6).
        sa.CheckConstraint(
            "(redriven_at IS NULL) = (redriven_by IS NULL)",
            name="ck_redrive_authorship_complete",
        ),
    )

    op.create_table(
        "tenant_budget",
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("provider", sa.Text(), nullable=False),
        sa.Column("reserved", sa.Numeric(12, 4), nullable=False, server_default="0"),
        sa.Column("spent", sa.Numeric(12, 4), nullable=False, server_default="0"),
        sa.Column("ceiling", sa.Numeric(12, 4), nullable=False),
        sa.Column(
            "kill_switch", sa.Boolean(), nullable=False, server_default=sa.text("false")
        ),
        sa.PrimaryKeyConstraint("tenant_id", "provider"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"], ondelete="RESTRICT"),
        # Enforced transactionally by `UPDATE ... WHERE spent + x <= ceiling`;
        # this constraint is the backstop that makes an accounting bug loud.
        sa.CheckConstraint("spent >= 0 AND reserved >= 0", name="ck_budget_non_negative"),
        sa.CheckConstraint("ceiling >= 0", name="ck_budget_ceiling_non_negative"),
    )

    op.create_table(
        "concurrency_lease",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("operation", sa.Text(), nullable=False),
        sa.Column("holder", sa.Text(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"], ondelete="RESTRICT"),
    )
    # Leases expire, so a worker crash self-heals without operator action.
    op.create_index(
        "ix_concurrency_lease_active", "concurrency_lease",
        ["tenant_id", "operation", "expires_at"],
    )


def downgrade() -> None:
    """Drop the Foundation schema.

    Present because Alembic expects it, and usable on a development database.
    Production rollback never depends on this: migrations follow expand →
    migrate → contract, and the destructive contract phase runs only after a
    release is fully promoted and stable (v1.1 §4.2).
    """
    for table in (
        "concurrency_lease",
        "tenant_budget",
        "redrive_record",
        "idempotency_record",
        "outbox_record",
        "job_event",
        "job",
        "resource_grant",
        "membership",
        "user_account",
        "org_unit",
        "tenant",
    ):
        op.drop_table(table)
