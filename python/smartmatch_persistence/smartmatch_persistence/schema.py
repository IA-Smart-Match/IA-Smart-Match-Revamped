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
    "attendance_record",
    "concurrency_lease",
    "idempotency_record",
    "import_batch",
    "job",
    "job_event",
    "membership",
    "org_unit",
    "outbox_record",
    "point_ledger_entry",
    "professional_unit_relationship",
    "rate_limit_counter",
    "redrive_record",
    "resource_grant",
    "review_item",
    "reward_item",
    "spend_ceiling_bucket",
    "spend_reservation",
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
    # Globally unique, not merely unique per tenant. ``principals.py`` looks an
    # account up by subject alone — the token proves who you are, the database
    # decides which tenant you are in — so a subject held by accounts in two
    # tenants returned two rows and 500'd every request for that person. See
    # migration 0003.
    #
    # This is now the *only* subject constraint. `uq_user_account_tenant_subject`
    # on `(tenant_id, external_subject)` stood beside it until migration 0007
    # (F12) and was strictly implied by it: a subject appearing at most once in
    # the table appears at most once per tenant. 0003 kept it because dropping a
    # constraint is contract-phase work (v1.1 §4.2); 0007 is that phase. The
    # within-tenant rule it used to state is unchanged and is now enforced here.
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
    # A5 (migration 0006). The organizational unit this job belongs to, and the
    # thing every authorization decision about the job is scoped against. Before
    # it existed no job operation could be scoped to a subtree, so a coordinator
    # in one department could read, re-drive and abandon another department's
    # work. NOT NULL from the moment the column existed: a nullable
    # authorization input is a fail-open shape waiting to be written, and 0006
    # backfills rather than defaults precisely so this can be required.
    sa.Column("owning_unit_id", _UUID, nullable=False),
    sa.PrimaryKeyConstraint("id", name="job_pkey"),
    sa.UniqueConstraint("tenant_id", "id", name="uq_job_tenant_id"),
    # Composite, and that is the guarantee rather than a detail: a single-column
    # key to `org_unit.id` would accept a job in one tenant naming a unit in
    # another, after which the job would be authorized against a path in a tree
    # its tenant has no relationship to. RESTRICT because reorganizing a unit
    # must not silently delete the audit trail of every command submitted into
    # it — `job_event` and `redrive_record` cascade from `job`.
    sa.ForeignKeyConstraint(
        ["tenant_id", "owning_unit_id"],
        ["org_unit.tenant_id", "org_unit.id"],
        ondelete="RESTRICT",
    ),
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


# ADR-0013, backlog S6/S7/S8 (migration 0009). Three of the five tables
# docs/architecture/engagement-model.md §1 describes — event, redemption, and
# disclosure_consent are each deferred behind a gate this migration cannot
# settle. See 0009_engagement_schema.py's module docstring for the full
# rationale on every choice below; only what a reader of this mirror needs is
# repeated here.

attendance_record = sa.Table(
    "attendance_record",
    METADATA,
    sa.Column("id", _UUID, primary_key=True),
    sa.Column("tenant_id", _UUID, nullable=False),
    # A5-shaped, same as job.owning_unit_id and import_batch.owning_unit_id.
    sa.Column("owning_unit_id", _UUID, nullable=False),
    # The student who attended.
    sa.Column("subject_id", _UUID, nullable=False),
    # No foreign key: no event table exists yet in this schema. Whichever
    # migration adds one should also add this constraint.
    sa.Column("event_id", _UUID, nullable=False),
    sa.Column("method", sa.Text, nullable=False),
    sa.Column("created_at", _TS, nullable=False, server_default=sa.text("now()")),
    sa.PrimaryKeyConstraint("id", name="attendance_record_pkey"),
    # What point_ledger_entry's composite foreign key below references.
    sa.UniqueConstraint("tenant_id", "id", name="uq_attendance_record_tenant_id"),
    # Attendance is the only input to points (ADR-0013); a duplicate row for
    # the same student at the same event is an unearned second credit.
    sa.UniqueConstraint(
        "tenant_id", "subject_id", "event_id", name="uq_attendance_record_subject_event"
    ),
    sa.ForeignKeyConstraint(
        ["tenant_id", "owning_unit_id"],
        ["org_unit.tenant_id", "org_unit.id"],
        ondelete="RESTRICT",
    ),
    sa.ForeignKeyConstraint(
        ["tenant_id", "subject_id"],
        ["user_account.tenant_id", "user_account.id"],
        ondelete="RESTRICT",
    ),
    sa.CheckConstraint(
        "method IN ('qr_scan','coordinator_entry','import')",
        name="ck_attendance_record_method",
    ),
)


point_ledger_entry = sa.Table(
    "point_ledger_entry",
    METADATA,
    sa.Column("id", _UUID, primary_key=True),
    sa.Column("tenant_id", _UUID, nullable=False),
    # Signed: a reversal is a negative entry naming the same source and a
    # reason that explains it (ADR-0013: "a reversal is a compensating entry,
    # never a delete"). No balance column exists on this table, or anywhere
    # else in this schema — a balance is a fold over this ledger, computed
    # server-side, never stored.
    sa.Column("amount", sa.Integer, nullable=False),
    # The attendance record this entry derives from — ADR-0013's "source".
    sa.Column("source_attendance_id", _UUID, nullable=False),
    sa.Column("reason", sa.Text, nullable=False),
    # Nullable, no foreign key: mirrors job.actor_id. Automatic derivation
    # from attendance — the ordinary case — has no human actor to name.
    sa.Column("actor_id", _UUID, nullable=True),
    sa.Column("occurred_at", _TS, nullable=False, server_default=sa.text("now()")),
    sa.PrimaryKeyConstraint("id", name="point_ledger_entry_pkey"),
    # RESTRICT: the attendance record an entry derives from must not
    # disappear out from under the entry that cites it as its source.
    sa.ForeignKeyConstraint(
        ["tenant_id", "source_attendance_id"],
        ["attendance_record.tenant_id", "attendance_record.id"],
        ondelete="RESTRICT",
    ),
    sa.CheckConstraint("amount <> 0", name="ck_point_ledger_entry_amount_nonzero"),
)


reward_item = sa.Table(
    "reward_item",
    METADATA,
    sa.Column("id", _UUID, primary_key=True),
    sa.Column("tenant_id", _UUID, nullable=False),
    sa.Column("name", sa.Text, nullable=False),
    sa.Column("points_cost", sa.Integer, nullable=False),
    sa.Column("fulfilment_cost", sa.Numeric(12, 4), nullable=False),
    # D6 (docs/decisions/pilot-decisions.md): "a named human budget owner.
    # Without one, the rewards catalog is not shippable." NOT NULL, no server
    # default — every insert must name a real owner in this tenant. Composite,
    # not a bare id: a single-column key would accept an owner from another
    # tenant.
    sa.Column("budget_owner_id", _UUID, nullable=False),
    # NOT NULL alongside budget_owner_id — this pair is the structural form of
    # D6's requirement (ADR-0013), and neither is softened to nullable "for
    # flexibility": that would let an unowned, unfunded reward be written,
    # reproducing the legacy defect (Fix #15) at the schema layer.
    sa.Column("funded", sa.Boolean, nullable=False, server_default=sa.text("false")),
    sa.Column("created_at", _TS, nullable=False, server_default=sa.text("now()")),
    sa.PrimaryKeyConstraint("id", name="reward_item_pkey"),
    sa.ForeignKeyConstraint(
        ["tenant_id", "budget_owner_id"],
        ["user_account.tenant_id", "user_account.id"],
        ondelete="RESTRICT",
    ),
    sa.CheckConstraint("points_cost > 0", name="ck_reward_item_points_cost_positive"),
    sa.CheckConstraint("fulfilment_cost >= 0", name="ck_reward_item_fulfilment_cost_non_negative"),
)


pipeline_record = sa.Table(
    "pipeline_record",
    METADATA,
    sa.Column("id", _UUID, primary_key=True),
    sa.Column("tenant_id", _UUID, nullable=False),
    # A5-shaped, same as job.owning_unit_id, import_batch and
    # attendance_record. Also the axis the funnel metrics are read per.
    sa.Column("owning_unit_id", _UUID, nullable=False),
    # The student whose journey through the funnel this row is.
    sa.Column("subject_id", _UUID, nullable=False),
    # The opportunity. No foreign key: no event table exists yet in this
    # schema (P6 owns it). Whichever migration adds one should add this
    # constraint and attendance_record.event_id's together.
    sa.Column("opportunity_event_id", _UUID, nullable=False),
    # The five stages as the times they were reached, not as one status
    # column: the register counts records that "reached X or a later stage",
    # and a stalled journey has still reached the stages it passed. Only the
    # first is NOT NULL — a record exists because a match does.
    sa.Column("matched_at", _TS, nullable=False, server_default=sa.text("now()")),
    sa.Column("contacted_at", _TS, nullable=True),
    sa.Column("confirmed_at", _TS, nullable=True),
    sa.Column("attended_at", _TS, nullable=True),
    sa.Column("member_inquiry_at", _TS, nullable=True),
    # The attendance row the Attended stage cites (ADR-0013's evidence, one
    # table over). Biconditional with attended_at below.
    sa.Column("attended_attendance_id", _UUID, nullable=True),
    sa.Column("created_at", _TS, nullable=False, server_default=sa.text("now()")),
    # This row is updated when a stage is reached, unlike point_ledger_entry —
    # carrying updated_at says mutation is expected here.
    sa.Column("updated_at", _TS, nullable=False, server_default=sa.text("now()")),
    sa.PrimaryKeyConstraint("id", name="pipeline_record_pkey"),
    # A second row for the same student and opportunity is a second count in
    # every stage it has reached — inflating the aggregate and the drill-down
    # identically, so the two still agree (ADR-0011 rule 3) while both are
    # wrong.
    sa.UniqueConstraint(
        "tenant_id",
        "subject_id",
        "opportunity_event_id",
        name="uq_pipeline_record_subject_opportunity",
    ),
    sa.ForeignKeyConstraint(
        ["tenant_id", "owning_unit_id"],
        ["org_unit.tenant_id", "org_unit.id"],
        ondelete="RESTRICT",
    ),
    sa.ForeignKeyConstraint(
        ["tenant_id", "subject_id"],
        ["user_account.tenant_id", "user_account.id"],
        ondelete="RESTRICT",
    ),
    # RESTRICT: deleting the attendance a funnel row cites would leave a count
    # nothing could explain.
    sa.ForeignKeyConstraint(
        ["tenant_id", "attended_attendance_id"],
        ["attendance_record.tenant_id", "attendance_record.id"],
        ondelete="RESTRICT",
    ),
    # A funnel that is wider at the bottom than the top is a number no
    # drill-down can reconcile, because every individual row is reported
    # faithfully. These two constraints are what make that state unstorable.
    sa.CheckConstraint(
        "(contacted_at IS NULL OR matched_at IS NOT NULL) "
        "AND (confirmed_at IS NULL OR contacted_at IS NOT NULL) "
        "AND (attended_at IS NULL OR confirmed_at IS NOT NULL) "
        "AND (member_inquiry_at IS NULL OR attended_at IS NOT NULL)",
        name="ck_pipeline_record_stage_prefix",
    ),
    sa.CheckConstraint(
        "(contacted_at IS NULL OR contacted_at >= matched_at) "
        "AND (confirmed_at IS NULL OR confirmed_at >= contacted_at) "
        "AND (attended_at IS NULL OR attended_at >= confirmed_at) "
        "AND (member_inquiry_at IS NULL OR member_inquiry_at >= attended_at)",
        name="ck_pipeline_record_stage_order",
    ),
    # An attendance claim names its evidence; evidence is never carried
    # without the claim it supports.
    sa.CheckConstraint(
        "(attended_at IS NULL) = (attended_attendance_id IS NULL)",
        name="ck_pipeline_record_attendance_evidence",
    ),
)


import_batch = sa.Table(
    "import_batch",
    METADATA,
    sa.Column("id", _UUID, primary_key=True),
    sa.Column("tenant_id", _UUID, nullable=False),
    # A5-shaped (migration 0006): the unit this import landed in, the thing
    # every authorization decision about its review items is scoped against.
    # Composite FK below, not a bare id — see that constraint's comment.
    sa.Column("owning_unit_id", _UUID, nullable=False),
    # The durable command job that produced this batch (v1.1 §1.6).
    sa.Column("job_id", _UUID, nullable=False),
    sa.Column("dataset", sa.Text, nullable=False),
    sa.Column("row_count", sa.Integer, nullable=False),
    sa.Column("dry_run", sa.Boolean, nullable=False),
    sa.Column("created_at", _TS, nullable=False, server_default=sa.text("now()")),
    sa.PrimaryKeyConstraint("id", name="import_batch_pkey"),
    # What review_item's composite foreign key below references.
    sa.UniqueConstraint("tenant_id", "id", name="uq_import_batch_tenant_id"),
    # CASCADE: a batch is a thing a job's execution produced, the same
    # relationship job_event/outbox_record/redrive_record already have to job
    # — not an independent entity that happens to name one.
    sa.ForeignKeyConstraint(
        ["tenant_id", "job_id"], ["job.tenant_id", "job.id"], ondelete="CASCADE"
    ),
    # RESTRICT: reorganizing a unit must not silently delete the pending
    # review work submitted into it, the same intent job.owning_unit_id
    # carries against org_unit (migration 0006). A single-column key to
    # org_unit.id would accept a batch in one tenant naming a unit in
    # another, so the reference is composite.
    sa.ForeignKeyConstraint(
        ["tenant_id", "owning_unit_id"],
        ["org_unit.tenant_id", "org_unit.id"],
        ondelete="RESTRICT",
    ),
)


review_item = sa.Table(
    "review_item",
    METADATA,
    sa.Column("id", _UUID, primary_key=True),
    sa.Column("tenant_id", _UUID, nullable=False),
    sa.Column("import_batch_id", _UUID, nullable=False),
    # This row's position in the submitted batch, so a coordinator can find
    # it in their source file.
    sa.Column("row_index", sa.Integer, nullable=False),
    # The normalized row itself — validate_columns's per-row output, not the
    # raw submission.
    sa.Column("row_data", postgresql.JSONB, nullable=False),
    sa.Column("status", sa.Text, nullable=False, server_default="pending"),
    sa.Column("created_at", _TS, nullable=False, server_default=sa.text("now()")),
    sa.PrimaryKeyConstraint("id", name="review_item_pkey"),
    # CASCADE: a review item cannot outlive the batch that quarantined it.
    sa.ForeignKeyConstraint(
        ["tenant_id", "import_batch_id"],
        ["import_batch.tenant_id", "import_batch.id"],
        ondelete="CASCADE",
    ),
    # Mirrors uq_job_event_sequence: a monotonic position within one parent,
    # and the parent id alone is already globally unique, so no tenant_id is
    # needed alongside it here.
    sa.UniqueConstraint("import_batch_id", "row_index", name="uq_review_item_batch_row"),
    # v1.1 §1.5's quarantine-and-review vocabulary: a review item is
    # quarantined (pending) and a human resolves it one way or the other.
    sa.CheckConstraint(
        "status IN ('pending','accepted','rejected')",
        name="ck_review_item_status",
    ),
)


# ADR-0015 Amendment A1 (migration 0010). Reserve-before-paid-call monetary
# spend semantics — the counting-quota rule ADR-0015's own body states is
# structurally wrong for money, because a dollar paid to a provider is an
# external side effect no ROLLBACK reaches. Full rationale lives in the
# migration's module docstring; only what a reader of this mirror needs is
# repeated here.

spend_ceiling_bucket = sa.Table(
    "spend_ceiling_bucket",
    METADATA,
    sa.Column(
        "tenant_id", _UUID, sa.ForeignKey("tenant.id", ondelete="RESTRICT"), primary_key=True
    ),
    # 'job' | 'tenant_day' | 'tenant_month' — the three ceilings A1's
    # obligation 1 debits atomically, in that fixed order
    # (smartmatch_domain.spend.BUCKET_LOCK_ORDER).
    sa.Column("bucket_type", sa.Text, primary_key=True),
    # job:<job_id>, tenant-day:<tenant_id>:<date>,
    # tenant-month:<tenant_id>:<year>-<month> — derived by
    # smartmatch_domain.spend, never constructed here.
    sa.Column("bucket_key", sa.Text, primary_key=True),
    # Fixed at first write for this bucket; never rewritten by a later
    # reservation against the same key.
    sa.Column("ceiling", sa.Numeric(12, 4), nullable=False),
    sa.Column("reserved", sa.Numeric(12, 4), nullable=False, server_default="0"),
    sa.Column("spent", sa.Numeric(12, 4), nullable=False, server_default="0"),
    sa.Column("created_at", _TS, nullable=False, server_default=sa.text("now()")),
    # Named because smartmatch_persistence.spend passes this name to
    # ON CONFLICT DO UPDATE, the same reason pk_rate_limit_counter is named.
    sa.PrimaryKeyConstraint(
        "tenant_id", "bucket_type", "bucket_key", name="pk_spend_ceiling_bucket"
    ),
    sa.CheckConstraint(
        "bucket_type IN ('job','tenant_day','tenant_month')",
        name="ck_spend_ceiling_bucket_type",
    ),
    # Mirrors ck_budget_non_negative / ck_budget_ceiling_non_negative
    # (tenant_budget). Deliberately no "reserved + spent <= ceiling" — A1
    # requires a genuine overage be recorded, never truncated to fit the
    # ceiling, so a reconciliation can legitimately push spent past ceiling.
    sa.CheckConstraint("reserved >= 0 AND spent >= 0", name="ck_spend_ceiling_bucket_non_negative"),
    sa.CheckConstraint("ceiling >= 0", name="ck_spend_ceiling_bucket_ceiling_non_negative"),
)


spend_reservation = sa.Table(
    "spend_reservation",
    METADATA,
    sa.Column("id", _UUID, primary_key=True),
    sa.Column("tenant_id", _UUID, sa.ForeignKey("tenant.id", ondelete="RESTRICT"), nullable=False),
    # Deterministic (smartmatch_domain.spend.derive_work_key), globally
    # unique so a retry or redelivery of the same unit of work finds this row
    # instead of reserving a second time — mirrors uq_outbox_task_name.
    sa.Column("work_key", sa.Text, nullable=False),
    sa.Column("job_bucket_key", sa.Text, nullable=False),
    sa.Column("tenant_day_bucket_key", sa.Text, nullable=False),
    sa.Column("tenant_month_bucket_key", sa.Text, nullable=False),
    # The reserved maximum. NUMERIC(12,4) — never FLOAT (A1).
    sa.Column("estimate", sa.Numeric(12, 4), nullable=False),
    # NULL until reconciled, timed out, or swept.
    sa.Column("actual_cost", sa.Numeric(12, 4), nullable=True),
    # True when actual_cost is the reserved maximum written by a timeout or
    # the sweep, not a real reported cost. A1: "an estimated dollar amount
    # must never be recorded, displayed, or reported as an actual one."
    sa.Column("actual_is_estimated", sa.Boolean, nullable=False, server_default=sa.text("false")),
    sa.Column("state", sa.Text, nullable=False, server_default="reserved"),
    # Present exactly while reserved; cleared on every terminal transition —
    # the same discipline J17 established for outbox_record.lease_token, which
    # is likewise nullable. Enforced by the biconditional check below, not by
    # NOT NULL: a NOT NULL column could never be cleared.
    sa.Column("lease_token", _UUID, nullable=True),
    sa.Column("lease_expires_at", _TS, nullable=False),
    # T-08's dedup marker: at most one review finding is ever emitted for a
    # given reservation, guarded by "UPDATE ... WHERE review_flagged_at IS
    # NULL". No discovery_review_item table exists yet in this schema.
    sa.Column("review_flagged_at", _TS, nullable=True),
    sa.Column("created_at", _TS, nullable=False, server_default=sa.text("now()")),
    # Set on any reserved -> {reconciled, expired_spent, released} transition.
    sa.Column("settled_at", _TS, nullable=True),
    sa.PrimaryKeyConstraint("id", name="spend_reservation_pkey"),
    sa.UniqueConstraint("work_key", name="uq_spend_reservation_work_key"),
    sa.CheckConstraint("estimate >= 0", name="ck_spend_reservation_estimate_non_negative"),
    sa.CheckConstraint(
        "actual_cost IS NULL OR actual_cost >= 0",
        name="ck_spend_reservation_actual_non_negative",
    ),
    # Mirrors smartmatch_domain.spend.SpendReservationState.
    sa.CheckConstraint(
        "state IN ('reserved','reconciled','expired_spent','released')",
        name="ck_spend_reservation_state",
    ),
    sa.CheckConstraint(
        "(state = 'reserved') = (lease_token IS NOT NULL)",
        name="ck_spend_reservation_lease_token_iff_reserved",
    ),
)


# P9 Gate A (`docs/decisions/p9-gate-a-board-role-decision-draft.md`, CLOSED
# 2026-09-02) and migration 0012. board_role is relationship-scoped, not an
# intrinsic attribute of a professional: §1 of the gate record decides that
# question, and §2 answers the follow-on ones this table's shape encodes.

professional_unit_relationship = sa.Table(
    "professional_unit_relationship",
    METADATA,
    # Composite NATURAL key, no surrogate id -- mirrors spend_ceiling_bucket
    # and rate_limit_counter, the schema's other tables whose identity is
    # exactly what a caller already knows rather than a generated value. Here
    # that identity is "this professional's role at this unit", and it is
    # also the multiplicity rule Gate A §2 states: the same professional_id
    # may appear in many rows as long as unit_id differs, which is what lets
    # "multiple concurrent board_role values per person across different
    # units" (§2) be represented at the same instant -- by more than one row,
    # not by a wider column.
    sa.Column("tenant_id", _UUID, nullable=False),
    # No foreign key: no professional table exists yet in this schema.
    # Professionals are P9 pilot import/review data today
    # (docs/pilot-data/columns.yaml, quarantined into review_item), not a
    # persisted entity with a stable id of its own -- the same situation
    # attendance_record.event_id and pipeline_record.opportunity_event_id
    # are already in for their own not-yet-built parent tables. Whichever
    # migration gives professionals a persisted identity should add this
    # constraint alongside it.
    sa.Column("professional_id", _UUID, nullable=False),
    sa.Column("unit_id", _UUID, nullable=False),
    # The whole point of a row existing here. NOT NULL: a relationship row
    # carrying no role records nothing Gate A asked this table to hold, the
    # same reasoning reward_item.budget_owner_id (D6) already applies to a
    # column that would be meaningless if it could be absent.
    sa.Column("board_role", sa.Text, nullable=False),
    sa.Column("created_at", _TS, nullable=False, server_default=sa.text("now()")),
    # Gate A §2's "correction semantics": a coordinator's correction updates
    # the current relationship record rather than superseding it with a new
    # one, so — unlike point_ledger_entry's append-only design — mutation is
    # expected here, and carrying updated_at says so structurally
    # (pipeline_record's stage columns are the same argument for the same
    # reason).
    sa.Column(
        "updated_at",
        _TS,
        nullable=False,
        server_default=sa.text("now()"),
    ),
    # The composite natural key IS the primary key -- no separate
    # UniqueConstraint is needed alongside it, unlike attendance_record's
    # surrogate id + uq_attendance_record_subject_event pair, because there
    # is no surrogate id here to make redundant.
    sa.PrimaryKeyConstraint(
        "tenant_id",
        "professional_id",
        "unit_id",
        name="professional_unit_relationship_pkey",
    ),
    # Deliberately NO effective_from / effective_to columns. Gate A §2: "pilot
    # treats board_role as current-state only on each relationship; no
    # effective_from / effective_to columns for pilot." Post-pilot dating is
    # explicitly deferred, not merely unimplemented -- adding those columns
    # without a new gate decision would be inventing the answer this table's
    # shape is not authorized to give yet.
    #
    # RESTRICT: reorganizing a unit must not silently delete the board-role
    # relationships recorded against it -- the same intent
    # attendance_record.owning_unit_id and import_batch.owning_unit_id
    # already carry against org_unit. Composite, not a bare unit_id, so a
    # relationship in one tenant cannot name a unit in another (ADR-0004).
    sa.ForeignKeyConstraint(
        ["tenant_id", "unit_id"],
        ["org_unit.tenant_id", "org_unit.id"],
        ondelete="RESTRICT",
    ),
)
