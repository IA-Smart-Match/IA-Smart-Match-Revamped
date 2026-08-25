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

Primary keys, unique constraints, and CHECK constraints carry their database
names here, including the ones PostgreSQL would have generated on its own. Two
reasons. The drift test compares those names in both directions, which is what
catches a constraint added to a migration and never mirrored — the failure mode
that has no column to notice. And a name a query passes to ``ON CONFLICT`` is an
interface: ``idempotency.py`` names ``uq_idempotency_scope`` and
``rate_limit.py`` names ``pk_rate_limit_counter``, so both belong in the mirror
rather than only in a migration.

**Foreign keys are deliberately left unnamed**, and the drift test deliberately
omits their names from its comparison. Nothing in the codebase refers to a
foreign key by name — no query, no ``ON CONFLICT`` — so a name here would be a
value to keep in step with no reader depending on it. Their columns, targets, and
delete actions are mirrored and compared, which is the part that carries meaning.

``ondelete`` is likewise part of the mirror. ``METADATA`` never creates a
database, so a missing ``ondelete`` changes no behaviour — but this file is what
people read to learn the schema, and it should be able to say which parents
refuse to be deleted (``RESTRICT``) and which take their children with them
(``CASCADE``).
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
    sa.Column("slug", sa.Text, nullable=False),
    sa.Column("display_name", sa.Text, nullable=False),
    sa.Column("created_at", _TS, nullable=False, server_default=sa.text("now()")),
    sa.PrimaryKeyConstraint("id", name="tenant_pkey"),
    sa.UniqueConstraint("slug", name="tenant_slug_key"),
)


org_unit = sa.Table(
    "org_unit",
    METADATA,
    sa.Column("id", _UUID, primary_key=True),
    # RESTRICT: a tenant with live data must not vanish because a row was
    # removed. The same intent holds for every tenant-owned table below except
    # rate_limit_counter, whose counters are disposable.
    sa.Column("tenant_id", _UUID, sa.ForeignKey("tenant.id", ondelete="RESTRICT"), nullable=False),
    sa.Column("path", LTree(), nullable=False),
    sa.Column("unit_type", sa.Text, nullable=False),
    sa.Column("display_name", sa.Text, nullable=False),
    sa.Column("created_at", _TS, nullable=False, server_default=sa.text("now()")),
    sa.Column("version", sa.Integer, nullable=False, server_default="1"),
    sa.PrimaryKeyConstraint("id", name="org_unit_pkey"),
    sa.UniqueConstraint("tenant_id", "id", name="uq_org_unit_tenant_id"),
    sa.UniqueConstraint("tenant_id", "path", name="uq_org_unit_tenant_path"),
)


user_account = sa.Table(
    "user_account",
    METADATA,
    sa.Column("id", _UUID, primary_key=True),
    sa.Column("tenant_id", _UUID, sa.ForeignKey("tenant.id", ondelete="RESTRICT"), nullable=False),
    sa.Column("external_subject", sa.Text, nullable=False),
    sa.Column("email", sa.Text, nullable=False),
    sa.Column("suspended", sa.Boolean, nullable=False, server_default=sa.text("false")),
    sa.Column("created_at", _TS, nullable=False, server_default=sa.text("now()")),
    sa.Column("version", sa.Integer, nullable=False, server_default="1"),
    sa.PrimaryKeyConstraint("id", name="user_account_pkey"),
    sa.UniqueConstraint("tenant_id", "id", name="uq_user_account_tenant_id"),
    sa.UniqueConstraint("tenant_id", "external_subject", name="uq_user_account_tenant_subject"),
    # Globally unique, not merely unique per tenant. ``principals.py`` looks an
    # account up by subject alone — the token proves who you are, the database
    # decides which tenant you are in — so a subject held by accounts in two
    # tenants returned two rows and 500'd every request for that person. See
    # migration 0003. This constraint implies the one above, which is kept
    # because dropping it is a contract-phase action (v1.1 §4.2).
    sa.UniqueConstraint("external_subject", name="uq_user_account_external_subject"),
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
    sa.PrimaryKeyConstraint("id", name="membership_pkey"),
    # Composite: a membership cannot reference a user in another tenant.
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
    sa.PrimaryKeyConstraint("id", name="resource_grant_pkey"),
    sa.ForeignKeyConstraint(
        ["tenant_id", "user_id"],
        ["user_account.tenant_id", "user_account.id"],
        ondelete="CASCADE",
    ),
    sa.CheckConstraint("effect IN ('allow', 'deny')", name="ck_resource_grant_effect"),
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
    sa.Column("tenant_id", _UUID, sa.ForeignKey("tenant.id", ondelete="RESTRICT"), nullable=False),
    sa.Column("command_type", sa.Text, nullable=False),
    sa.Column("status", sa.Text, nullable=False),
    sa.Column("actor_id", _UUID, nullable=True),
    sa.Column("deadline", _TS, nullable=True),
    sa.Column("created_at", _TS, nullable=False, server_default=sa.text("now()")),
    sa.Column("updated_at", _TS, nullable=False, server_default=sa.text("now()")),
    sa.Column("version", sa.Integer, nullable=False, server_default="1"),
    # J9 (migration 0004). When a worker taking `dispatched -> running` expects
    # to be finished by. NULL means no deadline, and the sweep leaves the row
    # alone — the fail-safe direction, since a missing deadline must not be
    # grounds for terminating a job that may still be running.
    sa.Column("lease_expires_at", _TS, nullable=True),
    # J10 (migration 0005). The command's parameters, written in the same INSERT
    # as the job row so they commit with the intent to dispatch and can never
    # lag behind it. NULL means the row was written by code that did not persist
    # a payload, and the parameters are unrecoverable — the fingerprint on
    # `idempotency_record` is a one-way hash. That is a different fact from
    # `{}`, which is a command that genuinely carried nothing, and 0005
    # deliberately declines a `DEFAULT '{}'::jsonb` that would merge the two.
    sa.Column("payload", postgresql.JSONB, nullable=True),
    sa.PrimaryKeyConstraint("id", name="job_pkey"),
    sa.UniqueConstraint("tenant_id", "id", name="uq_job_tenant_id"),
    # Mirrors smartmatch_domain.jobs.JobState. The set of states lives in the
    # migration; this name is what the drift test holds to account.
    sa.CheckConstraint(
        "status IN ('queued','dispatched','running','succeeded','partial',"
        "'failed_provider','failed_budget','failed_policy','cancelled',"
        "'timed_out','redrive_pending','abandoned')",
        name="ck_job_status",
    ),
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
    sa.PrimaryKeyConstraint("id", name="job_event_pkey"),
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
    # J17 (migration 0004). Minted per claim, so `mark_dispatched` and
    # `mark_failed` can prove *this* caller holds the row rather than that
    # someone does. NULL is **not** "no dispatcher holds this": a dispatcher on
    # pre-J17 code claims without writing a token and holds the row anyway.
    # J17's guarantee needs every dispatcher on the new code — see 0004.
    sa.Column("lease_token", _UUID, nullable=True),
    sa.Column("created_at", _TS, nullable=False, server_default=sa.text("now()")),
    sa.PrimaryKeyConstraint("id", name="outbox_record_pkey"),
    sa.ForeignKeyConstraint(
        ["tenant_id", "job_id"], ["job.tenant_id", "job.id"], ondelete="CASCADE"
    ),
    sa.UniqueConstraint("task_name", name="uq_outbox_task_name"),
    sa.CheckConstraint(
        "status IN ('pending','leased','dispatched','failed')",
        name="ck_outbox_status",
    ),
)


idempotency_record = sa.Table(
    "idempotency_record",
    METADATA,
    sa.Column("id", _UUID, primary_key=True),
    sa.Column("tenant_id", _UUID, sa.ForeignKey("tenant.id", ondelete="RESTRICT"), nullable=False),
    sa.Column("idempotency_key", sa.Text, nullable=False),
    sa.Column("command_type", sa.Text, nullable=False),
    sa.Column("request_fingerprint", sa.Text, nullable=False),
    sa.Column("job_id", _UUID, nullable=True),
    # J14 (migration 0004). The generation *this key's* command produced,
    # written after it succeeds rather than at reserve time — the generation is
    # the command's result, so it does not exist when the key is reserved. NULL
    # means the reservation predates 0004, or its command never completed.
    sa.Column("result_generation", sa.Integer, nullable=True),
    sa.Column("created_at", _TS, nullable=False, server_default=sa.text("now()")),
    sa.PrimaryKeyConstraint("id", name="idempotency_record_pkey"),
    # Named because idempotency.py passes this name to ON CONFLICT.
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
    sa.PrimaryKeyConstraint("id", name="redrive_record_pkey"),
    sa.ForeignKeyConstraint(
        ["tenant_id", "job_id"], ["job.tenant_id", "job.id"], ondelete="CASCADE"
    ),
    sa.CheckConstraint(
        "(redriven_at IS NULL) = (redriven_by IS NULL)",
        name="ck_redrive_authorship_complete",
    ),
)


tenant_budget = sa.Table(
    "tenant_budget",
    METADATA,
    sa.Column(
        "tenant_id",
        _UUID,
        sa.ForeignKey("tenant.id", ondelete="RESTRICT"),
        primary_key=True,
    ),
    sa.Column("provider", sa.Text, primary_key=True),
    sa.Column("reserved", sa.Numeric(12, 4), nullable=False, server_default="0"),
    sa.Column("spent", sa.Numeric(12, 4), nullable=False, server_default="0"),
    sa.Column("ceiling", sa.Numeric(12, 4), nullable=False),
    sa.Column("kill_switch", sa.Boolean, nullable=False, server_default=sa.text("false")),
    sa.PrimaryKeyConstraint("tenant_id", "provider", name="tenant_budget_pkey"),
    sa.CheckConstraint("spent >= 0 AND reserved >= 0", name="ck_budget_non_negative"),
    sa.CheckConstraint("ceiling >= 0", name="ck_budget_ceiling_non_negative"),
)


rate_limit_counter = sa.Table(
    "rate_limit_counter",
    METADATA,
    # CASCADE, unlike every other tenant-owned table: counters are derived data
    # with no audit value, so they go with the tenant rather than blocking it.
    sa.Column(
        "tenant_id",
        _UUID,
        sa.ForeignKey("tenant.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    # Text, not UUID: the subject is a user id for authenticated operations and
    # an IP for unauthenticated ones, and forcing an IP into a UUID column would
    # mean encoding it as a fake identifier.
    sa.Column("subject", sa.Text, primary_key=True),
    sa.Column("operation", sa.Text, primary_key=True),
    sa.Column("window_start", _TS, primary_key=True),
    sa.Column("count", sa.Integer, nullable=False, server_default="0"),
    # Named because rate_limit.py passes this name to ON CONFLICT DO UPDATE.
    sa.PrimaryKeyConstraint(
        "tenant_id", "subject", "operation", "window_start", name="pk_rate_limit_counter"
    ),
    sa.CheckConstraint("count >= 0", name="ck_rate_limit_count_non_negative"),
)


concurrency_lease = sa.Table(
    "concurrency_lease",
    METADATA,
    sa.Column("id", _UUID, primary_key=True),
    sa.Column("tenant_id", _UUID, sa.ForeignKey("tenant.id", ondelete="RESTRICT"), nullable=False),
    sa.Column("operation", sa.Text, nullable=False),
    sa.Column("holder", sa.Text, nullable=False),
    sa.Column("expires_at", _TS, nullable=False),
    sa.PrimaryKeyConstraint("id", name="concurrency_lease_pkey"),
)
