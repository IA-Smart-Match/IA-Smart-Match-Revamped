"""Table definitions, mirroring ``db/migrations``.

SQLAlchemy Core rather than the ORM, and hand-written rather than reflected. The
composite tenant-safe keys in architecture v1.1 §2.2 are the point of this
schema, and neither autogeneration nor reflection reproduces them reliably — a
silently simplified foreign key would remove the isolation guarantee without
anyone noticing.

Because these definitions are hand-written, they can drift from the migrations
that actually shape the database. ``tests/integration/test_schema_matches_migration.py``
compares them against a freshly migrated database, so drift fails the build
rather than surfacing as a confusing runtime error.
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

__all__ = [
    "METADATA",
    "concurrency_lease",
    "idempotency_record",
    "job",
    "job_event",
    "membership",
    "org_unit",
    "outbox_record",
    "rate_limit_counter",
    "redrive_record",
    "resource_grant",
    "tenant",
    "tenant_budget",
    "user_account",
]

METADATA = sa.MetaData()


class LTree(sa.types.UserDefinedType):  # type: ignore[type-arg]
    """The PostgreSQL ``ltree`` type.

    SQLAlchemy ships no ``ltree`` type. Substituting ``TEXT`` would cost the
    subtree operators and the GiST index that make the organizational tree
    queryable, so the real type is declared here.
    """

    cache_ok = True

    def get_col_spec(self, **kw: object) -> str:
        return "ltree"


_UUID = postgresql.UUID(as_uuid=True)
_TS = sa.DateTime(timezone=True)


tenant = sa.Table(
    "tenant",
    METADATA,
    sa.Column("id", _UUID, primary_key=True),
    sa.Column("slug", sa.Text, nullable=False, unique=True),
    sa.Column("display_name", sa.Text, nullable=False),
    sa.Column("created_at", _TS, nullable=False, server_default=sa.text("now()")),
)


org_unit = sa.Table(
    "org_unit",
    METADATA,
    sa.Column("id", _UUID, primary_key=True),
    sa.Column("tenant_id", _UUID, sa.ForeignKey("tenant.id"), nullable=False),
    sa.Column("path", LTree(), nullable=False),
    sa.Column("unit_type", sa.Text, nullable=False),
    sa.Column("display_name", sa.Text, nullable=False),
    sa.Column("created_at", _TS, nullable=False, server_default=sa.text("now()")),
    sa.Column("version", sa.Integer, nullable=False, server_default="1"),
    sa.UniqueConstraint("tenant_id", "id", name="uq_org_unit_tenant_id"),
    sa.UniqueConstraint("tenant_id", "path", name="uq_org_unit_tenant_path"),
)


user_account = sa.Table(
    "user_account",
    METADATA,
    sa.Column("id", _UUID, primary_key=True),
    sa.Column("tenant_id", _UUID, sa.ForeignKey("tenant.id"), nullable=False),
    sa.Column("external_subject", sa.Text, nullable=False),
    sa.Column("email", sa.Text, nullable=False),
    sa.Column("suspended", sa.Boolean, nullable=False, server_default=sa.text("false")),
    sa.Column("created_at", _TS, nullable=False, server_default=sa.text("now()")),
    sa.Column("version", sa.Integer, nullable=False, server_default="1"),
    sa.UniqueConstraint("tenant_id", "id", name="uq_user_account_tenant_id"),
    sa.UniqueConstraint("tenant_id", "external_subject", name="uq_user_account_tenant_subject"),
)


membership = sa.Table(
    "membership",
    METADATA,
    sa.Column("id", _UUID, primary_key=True),
    sa.Column("tenant_id", _UUID, nullable=False),
    sa.Column("user_id", _UUID, nullable=False),
    sa.Column("granted_path", LTree(), nullable=False),
    sa.Column("role", sa.Text, nullable=False),
    sa.Column("valid_from", _TS, nullable=True),
    sa.Column("valid_until", _TS, nullable=True),
    sa.Column("created_at", _TS, nullable=False, server_default=sa.text("now()")),
    # Composite: a membership cannot reference a user in another tenant.
    sa.ForeignKeyConstraint(
        ["tenant_id", "user_id"],
        ["user_account.tenant_id", "user_account.id"],
        ondelete="CASCADE",
    ),
)


resource_grant = sa.Table(
    "resource_grant",
    METADATA,
    sa.Column("id", _UUID, primary_key=True),
    sa.Column("tenant_id", _UUID, nullable=False),
    sa.Column("user_id", _UUID, nullable=False),
    sa.Column("resource_type", sa.Text, nullable=False),
    sa.Column("resource_id", _UUID, nullable=False),
    sa.Column("effect", sa.Text, nullable=False),
    sa.Column("created_at", _TS, nullable=False, server_default=sa.text("now()")),
    sa.ForeignKeyConstraint(
        ["tenant_id", "user_id"],
        ["user_account.tenant_id", "user_account.id"],
        ondelete="CASCADE",
    ),
    sa.UniqueConstraint(
        "tenant_id",
        "user_id",
        "resource_type",
        "resource_id",
        name="uq_resource_grant_unique_decision",
    ),
)


job = sa.Table(
    "job",
    METADATA,
    sa.Column("id", _UUID, primary_key=True),
    sa.Column("tenant_id", _UUID, sa.ForeignKey("tenant.id"), nullable=False),
    sa.Column("command_type", sa.Text, nullable=False),
    sa.Column("status", sa.Text, nullable=False),
    sa.Column("actor_id", _UUID, nullable=True),
    sa.Column("deadline", _TS, nullable=True),
    sa.Column("created_at", _TS, nullable=False, server_default=sa.text("now()")),
    sa.Column("updated_at", _TS, nullable=False, server_default=sa.text("now()")),
    sa.Column("version", sa.Integer, nullable=False, server_default="1"),
    sa.UniqueConstraint("tenant_id", "id", name="uq_job_tenant_id"),
)


job_event = sa.Table(
    "job_event",
    METADATA,
    sa.Column("id", _UUID, primary_key=True),
    sa.Column("tenant_id", _UUID, nullable=False),
    sa.Column("job_id", _UUID, nullable=False),
    # Monotonic per job. SSE event IDs use it and Last-Event-ID reconnects from
    # it, which is why Redis is not required for reconnect correctness.
    sa.Column("sequence", sa.BigInteger, nullable=False),
    sa.Column("payload", postgresql.JSONB, nullable=False),
    sa.Column("created_at", _TS, nullable=False, server_default=sa.text("now()")),
    sa.ForeignKeyConstraint(
        ["tenant_id", "job_id"], ["job.tenant_id", "job.id"], ondelete="CASCADE"
    ),
    sa.UniqueConstraint("job_id", "sequence", name="uq_job_event_sequence"),
)


outbox_record = sa.Table(
    "outbox_record",
    METADATA,
    sa.Column("id", _UUID, primary_key=True),
    sa.Column("tenant_id", _UUID, nullable=False),
    sa.Column("job_id", _UUID, nullable=False),
    sa.Column("task_name", sa.Text, nullable=False),
    sa.Column("status", sa.Text, nullable=False, server_default="pending"),
    sa.Column("lease_expires_at", _TS, nullable=True),
    sa.Column("dispatch_attempts", sa.Integer, nullable=False, server_default="0"),
    sa.Column("last_error", sa.Text, nullable=True),
    sa.Column("created_at", _TS, nullable=False, server_default=sa.text("now()")),
    sa.ForeignKeyConstraint(
        ["tenant_id", "job_id"], ["job.tenant_id", "job.id"], ondelete="CASCADE"
    ),
    sa.UniqueConstraint("task_name", name="uq_outbox_task_name"),
)


idempotency_record = sa.Table(
    "idempotency_record",
    METADATA,
    sa.Column("id", _UUID, primary_key=True),
    sa.Column("tenant_id", _UUID, sa.ForeignKey("tenant.id"), nullable=False),
    sa.Column("idempotency_key", sa.Text, nullable=False),
    sa.Column("command_type", sa.Text, nullable=False),
    sa.Column("request_fingerprint", sa.Text, nullable=False),
    sa.Column("job_id", _UUID, nullable=True),
    sa.Column("created_at", _TS, nullable=False, server_default=sa.text("now()")),
    sa.UniqueConstraint(
        "tenant_id", "command_type", "idempotency_key", name="uq_idempotency_scope"
    ),
)


redrive_record = sa.Table(
    "redrive_record",
    METADATA,
    sa.Column("id", _UUID, primary_key=True),
    sa.Column("tenant_id", _UUID, nullable=False),
    sa.Column("job_id", _UUID, nullable=False),
    sa.Column("attempt_history", postgresql.JSONB, nullable=False),
    sa.Column("parked_at", _TS, nullable=False, server_default=sa.text("now()")),
    sa.Column("redriven_at", _TS, nullable=True),
    sa.Column("redriven_by", _UUID, nullable=True),
    sa.Column("redrive_reason", sa.Text, nullable=True),
    sa.ForeignKeyConstraint(
        ["tenant_id", "job_id"], ["job.tenant_id", "job.id"], ondelete="CASCADE"
    ),
)


tenant_budget = sa.Table(
    "tenant_budget",
    METADATA,
    sa.Column("tenant_id", _UUID, sa.ForeignKey("tenant.id"), primary_key=True),
    sa.Column("provider", sa.Text, primary_key=True),
    sa.Column("reserved", sa.Numeric(12, 4), nullable=False, server_default="0"),
    sa.Column("spent", sa.Numeric(12, 4), nullable=False, server_default="0"),
    sa.Column("ceiling", sa.Numeric(12, 4), nullable=False),
    sa.Column("kill_switch", sa.Boolean, nullable=False, server_default=sa.text("false")),
)


rate_limit_counter = sa.Table(
    "rate_limit_counter",
    METADATA,
    sa.Column("tenant_id", _UUID, sa.ForeignKey("tenant.id"), primary_key=True),
    # Text, not UUID: the subject is a user id for authenticated operations and
    # an IP for unauthenticated ones, and forcing an IP into a UUID column would
    # mean encoding it as a fake identifier.
    sa.Column("subject", sa.Text, primary_key=True),
    sa.Column("operation", sa.Text, primary_key=True),
    sa.Column("window_start", _TS, primary_key=True),
    sa.Column("count", sa.Integer, nullable=False, server_default="0"),
)


concurrency_lease = sa.Table(
    "concurrency_lease",
    METADATA,
    sa.Column("id", _UUID, primary_key=True),
    sa.Column("tenant_id", _UUID, sa.ForeignKey("tenant.id"), nullable=False),
    sa.Column("operation", sa.Text, nullable=False),
    sa.Column("holder", sa.Text, nullable=False),
    sa.Column("expires_at", _TS, nullable=False),
)
