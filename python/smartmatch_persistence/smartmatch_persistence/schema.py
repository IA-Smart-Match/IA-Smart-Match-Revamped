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
    "contact_channel",
    "contact_channel_transition",
    "delivery_event",
    "discovery_review_item",
    "event",
    "event_tag",
    "idempotency_record",
    "import_batch",
    "job",
    "job_event",
    "match_run",
    "membership",
    "org_unit",
    "outbox_record",
    "outreach_draft",
    "outreach_send",
    "pilot_credential",
    "pilot_login_attempt",
    "pilot_session",
    "point_ledger_entry",
    "professional_unit_relationship",
    "rate_limit_counter",
    "redemption",
    "redrive_record",
    "resource_grant",
    "review_item",
    "reward_item",
    "speaker_profile",
    "speaker_request_classification",
    "spend_ceiling_bucket",
    "spend_reservation",
    "suppression_record",
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
    # The event attended. Composite foreign key below, added by migration
    # 0017 (card S5f) alongside the event table itself -- the constraint 0009
    # asked "whichever migration adds one" to write.
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
    # RESTRICT (migration 0017): attendance is the only input to points
    # (ADR-0013), so deleting the event out from under a credited attendance
    # would leave a ledger entry nothing could explain.
    sa.ForeignKeyConstraint(
        ["tenant_id", "event_id"],
        ["event.tenant_id", "event.id"],
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
    # Which of the three shapes this row is: an attendance credit, a
    # compensating reversal, or a redemption debit. NOT NULL with no server
    # default — every writer names the kind it is writing (migration 0019).
    # Derivable from the sign and the source, and tied to that derivation by
    # ck_point_ledger_entry_kind below, so the two cannot drift.
    sa.Column("kind", sa.Text, nullable=False),
    # The attendance record this entry derives from — ADR-0013's "source".
    # Nullable since migration 0019: a redemption debit derives from a
    # redemption, not from an attendance, and borrowing an unrelated
    # attendance id to satisfy a NOT NULL would be fabricated evidence.
    sa.Column("source_attendance_id", _UUID, nullable=True),
    # The redemption this entry debits for. Set on exactly the rows where
    # source_attendance_id is null, and null on every other row.
    sa.Column("source_redemption_id", _UUID, nullable=True),
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
    # RESTRICT: the redemption a debit was taken for must not disappear out
    # from under the entry that cites it, or the debit becomes unexplainable.
    sa.ForeignKeyConstraint(
        ["tenant_id", "source_redemption_id"],
        ["redemption.tenant_id", "redemption.id"],
        ondelete="RESTRICT",
    ),
    sa.CheckConstraint("amount <> 0", name="ck_point_ledger_entry_amount_nonzero"),
    # Exactly one of three shapes, each carrying the fields its kind requires
    # (migration 0019). This is what keeps source_attendance_id's nullability
    # from being a hole: a row naming neither source, or both, or a kind
    # outside the three, satisfies none of the disjuncts.
    sa.CheckConstraint(
        "(kind = 'attendance_credit' AND source_attendance_id IS NOT NULL "
        "AND source_redemption_id IS NULL AND amount > 0) "
        "OR (kind = 'reversal' AND source_attendance_id IS NOT NULL "
        "AND source_redemption_id IS NULL AND amount < 0) "
        "OR (kind = 'redemption_debit' AND source_attendance_id IS NULL "
        "AND source_redemption_id IS NOT NULL AND amount < 0)",
        name="ck_point_ledger_entry_kind",
    ),
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
    # What redemption.item_id references (migration 0019). Deferred by 0009,
    # which said "nothing in this migration references reward_item by
    # composite key" -- something now does, so it is added by the migration
    # that creates the reference.
    sa.UniqueConstraint("tenant_id", "id", name="uq_reward_item_tenant_id"),
    sa.ForeignKeyConstraint(
        ["tenant_id", "budget_owner_id"],
        ["user_account.tenant_id", "user_account.id"],
        ondelete="RESTRICT",
    ),
    sa.CheckConstraint("points_cost > 0", name="ck_reward_item_points_cost_positive"),
    sa.CheckConstraint("fulfilment_cost >= 0", name="ck_reward_item_fulfilment_cost_non_negative"),
)


# ---------------------------------------------------------------------------
# redemption (migration 0019, plan cards L2/L4). One of the two tables
# docs/architecture/engagement-model.md §1 describes that migration 0009
# deferred and 0017 did not settle -- disclosure_consent, gated on ADR-0014, is
# the other. 0009 deferred this one behind D6's shipped-catalog gate, which
# closed for pilot scope on 2026-09-02.
#
# Deliberately mutable, unlike point_ledger_entry and match_run: a redemption's
# purpose is to move through requested -> approved -> fulfilled | denied |
# expired, and each move is an UPDATE. What keeps that honest is the pair of
# evidence CHECKs below, which hold on an UPDATE exactly as on an INSERT.
#
# The two partial unique / access indexes have no representation in SQLAlchemy
# Core and so are absent from this mirror, as every other index is;
# tests/integration/test_redemption_durability.py is what holds them to
# account. So is the append-only trigger 0019 puts on point_ledger_entry.
# ---------------------------------------------------------------------------

redemption = sa.Table(
    "redemption",
    METADATA,
    sa.Column("id", _UUID, primary_key=True),
    sa.Column("tenant_id", _UUID, nullable=False),
    # The student redeeming.
    sa.Column("subject_id", _UUID, nullable=False),
    sa.Column("item_id", _UUID, nullable=False),
    # D7's two "consequences that must survive into any implementation":
    # existing redemptions retain their point-cost snapshot, and a deactivated
    # reward stays visible on existing tickets. Columns, not a join back to
    # reward_item -- a join returns today's price and today's name.
    sa.Column("item_name_snapshot", sa.Text, nullable=False),
    sa.Column("points_cost_snapshot", sa.Integer, nullable=False),
    sa.Column("state", sa.Text, nullable=False),
    sa.Column("requested_at", _TS, nullable=False, server_default=sa.text("now()")),
    # The approval hop, recorded as evidence rather than inferred from state.
    sa.Column("approved_at", _TS, nullable=True),
    sa.Column("approved_by", _UUID, nullable=True),
    # The terminal hop. closed_by stays null for an expiry: time is not a
    # person, and naming one would be a fabricated field.
    sa.Column("closed_at", _TS, nullable=True),
    sa.Column("closed_by", _UUID, nullable=True),
    sa.PrimaryKeyConstraint("id", name="redemption_pkey"),
    # What point_ledger_entry.source_redemption_id references.
    sa.UniqueConstraint("tenant_id", "id", name="uq_redemption_tenant_id"),
    # RESTRICT throughout: a redemption is a promise made to a named student
    # against a named reward, and neither may vanish out from under it.
    sa.ForeignKeyConstraint(
        ["tenant_id", "subject_id"],
        ["user_account.tenant_id", "user_account.id"],
        ondelete="RESTRICT",
    ),
    sa.ForeignKeyConstraint(
        ["tenant_id", "item_id"],
        ["reward_item.tenant_id", "reward_item.id"],
        ondelete="RESTRICT",
    ),
    # Constrained, unlike point_ledger_entry.actor_id: a credit is derived and
    # usually has no human author, but an approval is something a person did.
    sa.ForeignKeyConstraint(
        ["tenant_id", "approved_by"],
        ["user_account.tenant_id", "user_account.id"],
        ondelete="RESTRICT",
    ),
    sa.ForeignKeyConstraint(
        ["tenant_id", "closed_by"],
        ["user_account.tenant_id", "user_account.id"],
        ondelete="RESTRICT",
    ),
    # ADR-0013's vocabulary, and the spelling
    # smartmatch_domain.rewards.RedemptionState carries.
    sa.CheckConstraint(
        "state IN ('requested','approved','fulfilled','denied','expired')",
        name="ck_redemption_state",
    ),
    # The structural statement of "fulfilled is reachable only from approved":
    # a fulfilled row with no approval behind it cannot be written or updated
    # into existence.
    sa.CheckConstraint(
        "(approved_at IS NULL) = (approved_by IS NULL) "
        "AND (state <> 'fulfilled' OR approved_at IS NOT NULL) "
        "AND (state <> 'requested' OR approved_at IS NULL)",
        name="ck_redemption_approval_evidence",
    ),
    # A terminal state has a close time; a live one does not.
    sa.CheckConstraint(
        "(state IN ('fulfilled','denied','expired')) = (closed_at IS NOT NULL) "
        "AND (closed_by IS NULL OR closed_at IS NOT NULL)",
        name="ck_redemption_closure_evidence",
    ),
    # A snapshot that says nothing is not a snapshot.
    sa.CheckConstraint(
        "points_cost_snapshot > 0 AND length(btrim(item_name_snapshot)) > 0",
        name="ck_redemption_snapshot_present",
    ),
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
    # Where the match came from. NOT NULL, no server default (migration
    # 0016): a default would let a caller omit provenance and still write a
    # row, which is exactly what this column exists to make impossible. Full
    # rationale — why the vocabulary is closed to exactly these two members,
    # why the first is spelled with a space and a slash, why a third member is
    # always a new revision — lives in that migration's module docstring;
    # only what a reader of this mirror needs is repeated here.
    sa.Column("matched_provenance", sa.Text, nullable=False),
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
    # The provenance vocabulary is closed to exactly these two members; full
    # rationale lives in migration 0016's module docstring, only what a
    # reader of this mirror needs is repeated here.
    sa.CheckConstraint(
        "matched_provenance IN ('synthetic / coordinator-accepted', 'match-engine')",
        name="ck_pipeline_record_matched_provenance",
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
    # migration 0013. NULL while pending, set once by the one conditional
    # UPDATE ... WHERE status = 'pending' this schema allows to leave that
    # state (ReviewRepository.decide). Biconditional with both status and
    # decided_by below — see ck_review_item_decision_evidence.
    sa.Column("decided_at", _TS, nullable=True),
    sa.Column("decided_by", _UUID, nullable=True),
    sa.PrimaryKeyConstraint("id", name="review_item_pkey"),
    # CASCADE: a review item cannot outlive the batch that quarantined it.
    sa.ForeignKeyConstraint(
        ["tenant_id", "import_batch_id"],
        ["import_batch.tenant_id", "import_batch.id"],
        ondelete="CASCADE",
    ),
    # RESTRICT: deleting the user_account behind a recorded decision must not
    # silently turn a cited decision back into an uncited one — the same
    # fabricated-field state ck_review_item_decision_evidence exists to make
    # unstorable in the first place (migration 0013).
    sa.ForeignKeyConstraint(
        ["tenant_id", "decided_by"],
        ["user_account.tenant_id", "user_account.id"],
        ondelete="RESTRICT",
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
    # A decision that names nobody and no time is the fabricated-field defect
    # (Fix #15, H21) one table over from pipeline_record's own attendance
    # evidence (migration 0011). Two independent biconditionals, ANDed rather
    # than chained — see migration 0013's docstring for why a chained
    # three-way `=` would not say what it looks like it says.
    sa.CheckConstraint(
        "(status = 'pending') = (decided_at IS NULL) "
        "AND (decided_at IS NULL) = (decided_by IS NULL)",
        name="ck_review_item_decision_evidence",
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


# ---------------------------------------------------------------------------
# The P6 event model (migration 0017): ADR-0010's temporal triple, ADR-0012's
# deterministic identity and closed tag vocabulary, and the G3 §5 discovery
# review queue. See the migration's docstring for the reasoning behind every
# constraint mirrored below; it is not repeated here.
# ---------------------------------------------------------------------------

event = sa.Table(
    "event",
    METADATA,
    sa.Column("id", _UUID, primary_key=True),
    sa.Column("tenant_id", _UUID, nullable=False),
    # ADR-0012: the org unit the event belongs to, not the page it was found on.
    sa.Column("host_org_unit_id", _UUID, nullable=False),
    sa.Column("title", sa.Text, nullable=False),
    # smartmatch_domain.events.normalize_title()'s output.
    sa.Column("normalized_title", sa.Text, nullable=False),
    sa.Column("description", sa.Text, nullable=True),
    # ADR-0010's temporal triple. starts_at is present only at 'exact',
    # on_date only at 'date_only', and time_zone at both but never at
    # 'unresolved' -- ck_event_temporal_shape below is the enforcement.
    sa.Column("starts_at", _TS, nullable=True),
    # Migration 0022. Not part of ADR-0010's triple and deliberately outside
    # time_precision's remit: precision describes how much of the *start* is
    # known, and an event whose source stated no end is exactly as resolved as
    # one that did. NULL means "the source stated no end" -- never a duration
    # nobody wrote down, which is what an .ics download is refused for rather
    # than served with. See ck_event_end_after_start below.
    sa.Column("ends_at", _TS, nullable=True),
    sa.Column("on_date", sa.Date, nullable=True),
    sa.Column("time_zone", sa.Text, nullable=True),
    sa.Column("time_precision", sa.Text, nullable=False),
    # The identity key's date component. NULL exactly when unresolved, which
    # is what keeps an unresolved event out of uq_event_identity.
    sa.Column("resolved_date", sa.Date, nullable=True),
    sa.Column("publication_status", sa.Text, nullable=False, server_default="unpublished"),
    sa.Column("review_status", sa.Text, nullable=False, server_default="pending"),
    # Denormalised, maintained by smartmatch_persistence.events: a CHECK
    # cannot see event_tag, and ck_event_publishable has to name the
    # quarantine half of ADR-0012 somehow.
    sa.Column("quarantined_tag_count", sa.Integer, nullable=False, server_default="0"),
    # ADR-0012's structured provenance -- EventProvenance field for field,
    # never folded into title or description.
    sa.Column("origin", sa.Text, nullable=False),
    sa.Column("source_url", sa.Text, nullable=True),
    sa.Column("fetched_at", _TS, nullable=True),
    sa.Column("extractor_version", sa.Text, nullable=True),
    # Migration 0024. Customer §12: an Event Host must be able to "specify
    # physical vs. virtual" and "specify event location". NOT NULL with a
    # server default so 0024 needed no backfill: every event that existed
    # before it was entered or extracted with a place attached, and a nullable
    # column would have created a third "nobody said" state that §11's
    # proximity-redistribution rule has no branch for.
    sa.Column("is_virtual", sa.Boolean, nullable=False, server_default=sa.text("false")),
    # §10: "City or ZIP code is sufficient for this phase." Two independent
    # nullable columns, because "or" is what the requirement says. Deliberately
    # NOT part of uq_event_identity below — two requests differing only in city
    # are the same event, and widening ADR-0012's key would un-deduplicate the
    # discovery path it exists to make deterministic.
    sa.Column("location_city", sa.Text, nullable=True),
    sa.Column("location_postal_code", sa.Text, nullable=True),
    sa.Column("created_at", _TS, nullable=False, server_default=sa.text("now()")),
    sa.Column("updated_at", _TS, nullable=False, server_default=sa.text("now()")),
    sa.PrimaryKeyConstraint("id", name="event_pkey"),
    # What attendance_record, event_tag, and discovery_review_item reference.
    sa.UniqueConstraint("tenant_id", "id", name="uq_event_tenant_id"),
    # ADR-0012's deterministic key. Named here rather than only in the
    # migration because events.py passes it to ON CONFLICT ON CONSTRAINT,
    # which makes the name an interface.
    sa.UniqueConstraint(
        "tenant_id",
        "host_org_unit_id",
        "normalized_title",
        "resolved_date",
        name="uq_event_identity",
    ),
    # RESTRICT: reorganizing a unit must not silently delete its events.
    sa.ForeignKeyConstraint(
        ["tenant_id", "host_org_unit_id"],
        ["org_unit.tenant_id", "org_unit.id"],
        ondelete="RESTRICT",
    ),
    sa.CheckConstraint(
        "time_precision IN ('exact','date_only','unresolved')",
        name="ck_event_time_precision",
    ),
    sa.CheckConstraint(
        "(time_precision = 'exact' AND starts_at IS NOT NULL "
        "AND on_date IS NULL AND time_zone IS NOT NULL) "
        "OR (time_precision = 'date_only' AND starts_at IS NULL "
        "AND on_date IS NOT NULL AND time_zone IS NOT NULL) "
        "OR (time_precision = 'unresolved' AND starts_at IS NULL "
        "AND on_date IS NULL AND time_zone IS NULL)",
        name="ck_event_temporal_shape",
    ),
    sa.CheckConstraint(
        "(time_precision = 'unresolved') = (resolved_date IS NULL)",
        name="ck_event_identity_iff_resolved",
    ),
    # Migration 0022. An end may exist only where a start does, and must come
    # after it. Without the time_precision clause a row could hold an end and
    # no start -- ck_event_temporal_shape keeps starts_at NULL at the other two
    # precisions -- and every other constraint would still pass. Strictly `>`
    # because a zero-length event is what an adapter writes when it copies
    # starts_at across, not something a source states; ExactTime refuses the
    # same value in Python.
    sa.CheckConstraint(
        "ends_at IS NULL OR (time_precision = 'exact' AND ends_at > starts_at)",
        name="ck_event_end_after_start",
    ),
    sa.CheckConstraint(
        "publication_status IN ('unpublished','published')",
        name="ck_event_publication_status",
    ),
    sa.CheckConstraint(
        "review_status IN ('pending','approved','rejected')",
        name="ck_event_review_status",
    ),
    sa.CheckConstraint(
        "quarantined_tag_count >= 0",
        name="ck_event_quarantined_tag_count_non_negative",
    ),
    # Unpublished means: unresolved dates, or quarantined tags.
    sa.CheckConstraint(
        "publication_status = 'unpublished' "
        "OR (time_precision <> 'unresolved' AND quarantined_tag_count = 0)",
        name="ck_event_publishable",
    ),
    sa.CheckConstraint(
        "origin IN ('coordinator_entry','extraction')",
        name="ck_event_origin",
    ),
    sa.CheckConstraint(
        "(origin = 'extraction') = (source_url IS NOT NULL) "
        "AND (source_url IS NULL) = (fetched_at IS NULL) "
        "AND (fetched_at IS NULL) = (extractor_version IS NULL)",
        name="ck_event_provenance_evidence",
    ),
    # Migration 0024. Customer §11: "for virtual events — ignore Proximity
    # entirely". A location stored on a virtual event is a value the scoring
    # rule is required to ignore, which is the shape of a field that gets read
    # by accident later; refusing it makes "entirely" structural.
    sa.CheckConstraint(
        "NOT is_virtual OR (location_city IS NULL AND location_postal_code IS NULL)",
        name="ck_event_virtual_has_no_location",
    ),
    # ADR-0011, and load-bearing rather than tidy: a location_city of '' passes
    # the NULL test above while the row still claims a place.
    sa.CheckConstraint(
        "(location_city IS NULL OR length(btrim(location_city)) > 0) "
        "AND (location_postal_code IS NULL OR length(btrim(location_postal_code)) > 0)",
        name="ck_event_location_present",
    ),
)


event_tag = sa.Table(
    "event_tag",
    METADATA,
    sa.Column("id", _UUID, primary_key=True),
    sa.Column("tenant_id", _UUID, nullable=False),
    sa.Column("event_id", _UUID, nullable=False),
    # The two arms of smartmatch_domain.events.TagResolution.
    sa.Column("resolution", sa.Text, nullable=False),
    # MappedTag.term -- NULL on a quarantined row, so a query selecting terms
    # cannot pick a quarantined value up by forgetting a filter.
    sa.Column("term", sa.Text, nullable=True),
    # QuarantinedTag.raw_value, exactly as received.
    sa.Column("raw_value", sa.Text, nullable=True),
    sa.Column("vocabulary_version", sa.Text, nullable=False),
    sa.Column("created_at", _TS, nullable=False, server_default=sa.text("now()")),
    sa.PrimaryKeyConstraint("id", name="event_tag_pkey"),
    # CASCADE: a tag cannot outlive the event it describes.
    sa.ForeignKeyConstraint(
        ["tenant_id", "event_id"],
        ["event.tenant_id", "event.id"],
        ondelete="CASCADE",
    ),
    # Both are named in ON CONFLICT by events.py.
    sa.UniqueConstraint("event_id", "term", name="uq_event_tag_term"),
    sa.UniqueConstraint("event_id", "raw_value", name="uq_event_tag_raw_value"),
    sa.CheckConstraint(
        "resolution IN ('mapped','quarantined')",
        name="ck_event_tag_resolution",
    ),
    sa.CheckConstraint(
        "(resolution = 'mapped') = (term IS NOT NULL) "
        "AND (resolution = 'quarantined') = (raw_value IS NOT NULL)",
        name="ck_event_tag_resolution_shape",
    ),
)


discovery_review_item = sa.Table(
    "discovery_review_item",
    METADATA,
    sa.Column("id", _UUID, primary_key=True),
    sa.Column("tenant_id", _UUID, nullable=False),
    sa.Column("owning_unit_id", _UUID, nullable=False),
    sa.Column("event_id", _UUID, nullable=False),
    sa.Column("kind", sa.Text, nullable=False),
    sa.Column("raw_value", sa.Text, nullable=True),
    sa.Column("vocabulary_version", sa.Text, nullable=True),
    sa.Column("status", sa.Text, nullable=False, server_default="pending"),
    sa.Column("decided_at", _TS, nullable=True),
    sa.Column("decided_by", _UUID, nullable=True),
    sa.Column("created_at", _TS, nullable=False, server_default=sa.text("now()")),
    sa.PrimaryKeyConstraint("id", name="discovery_review_item_pkey"),
    # CASCADE: a queue entry about an event cannot outlive it. This is the
    # relationship that made review_item the wrong home -- its own CASCADE is
    # to import_batch, which has nothing to do with discovery (G3 §5).
    sa.ForeignKeyConstraint(
        ["tenant_id", "event_id"],
        ["event.tenant_id", "event.id"],
        ondelete="CASCADE",
    ),
    sa.ForeignKeyConstraint(
        ["tenant_id", "owning_unit_id"],
        ["org_unit.tenant_id", "org_unit.id"],
        ondelete="RESTRICT",
    ),
    sa.ForeignKeyConstraint(
        ["tenant_id", "decided_by"],
        ["user_account.tenant_id", "user_account.id"],
        ondelete="RESTRICT",
    ),
    sa.UniqueConstraint("event_id", "raw_value", name="uq_discovery_review_item_event_value"),
    sa.CheckConstraint(
        "kind IN ('unmapped_tag','unresolved_time','first_seen_event')",
        name="ck_discovery_review_item_kind",
    ),
    sa.CheckConstraint(
        "status IN ('pending','accepted','rejected')",
        name="ck_discovery_review_item_status",
    ),
    sa.CheckConstraint(
        "(status = 'pending') = (decided_at IS NULL) "
        "AND (decided_at IS NULL) = (decided_by IS NULL)",
        name="ck_discovery_review_item_decision_evidence",
    ),
    sa.CheckConstraint(
        "(kind = 'unmapped_tag') = (raw_value IS NOT NULL) "
        "AND (raw_value IS NULL) = (vocabulary_version IS NULL)",
        name="ck_discovery_review_item_tag_evidence",
    ),
)


# ---------------------------------------------------------------------------
# The G1 match-run snapshot (migration 0018, plan card M8a). Immutable: the
# migration installs a BEFORE UPDATE trigger that refuses every UPDATE, and a
# correction is a new row naming the one it supersedes. See the migration's
# docstring for the reasoning behind every constraint mirrored below; it is not
# repeated here.
#
# The trigger has no representation in SQLAlchemy Core and so is absent from
# this mirror, as indexes are. `test_match_run_snapshot.py` is what holds it to
# account, by attempting the UPDATE and requiring the refusal.
# ---------------------------------------------------------------------------

match_run = sa.Table(
    "match_run",
    METADATA,
    sa.Column("id", _UUID, primary_key=True),
    sa.Column("tenant_id", _UUID, nullable=False),
    # A5-shaped: the unit every authorization decision about this run is scoped
    # against, as job.owning_unit_id and event.host_org_unit_id are.
    sa.Column("owning_unit_id", _UUID, nullable=False),
    # The durable command that produced this run. Constrained, which is what
    # makes "written on the command path, never by a route" a property of the
    # schema rather than a convention.
    sa.Column("job_id", _UUID, nullable=False),
    # PortfolioRequest.event_need_id. Text, not a foreign key -- the need
    # belongs to card S12's surface.
    sa.Column("event_need_id", sa.Text, nullable=False),
    # smartmatch_domain.match_run.inputs_fingerprint over the candidate pool,
    # the requested size, the seed, and the weights.
    sa.Column("inputs_hash", sa.Text, nullable=False),
    sa.Column("portfolio_size", sa.Integer, nullable=False),
    sa.Column("random_seed", sa.BigInteger, nullable=False),
    sa.Column("registry_version", sa.Text, nullable=False),
    sa.Column("registry_hash", sa.Text, nullable=False),
    # The readable copy of what registry_hash fingerprints: a digest is one-way,
    # and "which weights were in force in March" is not answerable from a hash.
    sa.Column("weights", postgresql.JSONB, nullable=False),
    sa.Column("optimizer_model_version", sa.Text, nullable=False),
    sa.Column("solver_name", sa.Text, nullable=False),
    sa.Column("solver_version", sa.Text, nullable=False),
    sa.Column("route_estimate_source", sa.Text, nullable=False),
    sa.Column("route_estimate_version", sa.Text, nullable=False),
    # Mirrors smartmatch_domain.optimizer.PortfolioStatus: 'infeasible' is a
    # claim about the model, 'unknown' one about the search stopping early, and
    # the two are never conflated.
    sa.Column("portfolio_status", sa.Text, nullable=False),
    # A correction is a new run naming the one it replaces.
    sa.Column("supersedes_run_id", _UUID, nullable=True),
    sa.Column("created_at", _TS, nullable=False, server_default=sa.text("now()")),
    # No updated_at, deliberately: carrying one would be a statement that
    # mutation is expected here, and the trigger forbids it.
    sa.PrimaryKeyConstraint("id", name="match_run_pkey"),
    sa.UniqueConstraint("tenant_id", "id", name="uq_match_run_tenant_id"),
    # One snapshot per command, so a re-driven job cannot write a second row for
    # the same run. Named here because match_runs.py passes it to
    # ON CONFLICT ON CONSTRAINT, which makes the name an interface.
    sa.UniqueConstraint("tenant_id", "job_id", name="uq_match_run_job"),
    # RESTRICT: reorganizing a unit must not silently delete the record of what
    # was recommended under it.
    sa.ForeignKeyConstraint(
        ["tenant_id", "owning_unit_id"],
        ["org_unit.tenant_id", "org_unit.id"],
        ondelete="RESTRICT",
    ),
    # RESTRICT: the job is this run's provenance.
    sa.ForeignKeyConstraint(
        ["tenant_id", "job_id"],
        ["job.tenant_id", "job.id"],
        ondelete="RESTRICT",
    ),
    sa.ForeignKeyConstraint(
        ["tenant_id", "supersedes_run_id"],
        ["match_run.tenant_id", "match_run.id"],
        ondelete="RESTRICT",
    ),
    sa.CheckConstraint(
        "supersedes_run_id IS NULL OR supersedes_run_id <> id",
        name="ck_match_run_supersedes_is_not_self",
    ),
    sa.CheckConstraint(
        "length(btrim(event_need_id)) > 0 "
        "AND length(btrim(inputs_hash)) > 0 "
        "AND length(btrim(registry_version)) > 0 "
        "AND length(btrim(registry_hash)) > 0 "
        "AND length(btrim(optimizer_model_version)) > 0 "
        "AND length(btrim(solver_name)) > 0 "
        "AND length(btrim(solver_version)) > 0 "
        "AND length(btrim(route_estimate_version)) > 0",
        name="ck_match_run_pins_present",
    ),
    sa.CheckConstraint(
        "jsonb_typeof(weights) = 'object' AND weights <> '{}'::jsonb",
        name="ck_match_run_weights_object",
    ),
    sa.CheckConstraint("portfolio_size >= 1", name="ck_match_run_portfolio_size"),
    sa.CheckConstraint("random_seed >= 0", name="ck_match_run_random_seed"),
    sa.CheckConstraint(
        "route_estimate_source IN ('straight_line','route_matrix')",
        name="ck_match_run_route_estimate_source",
    ),
    sa.CheckConstraint(
        "portfolio_status IN ('optimal','feasible','infeasible','unknown')",
        name="ck_match_run_portfolio_status",
    ),
)


# ---------------------------------------------------------------------------
# Pilot login (migration 0020)
#
# The storage behind the owner-authorized, pilot-scoped substitute for
# institutional sign-in — see ``docs/decisions/pilot-login-decision-2026-09-04.md``
# and the migration's own docstring, which carries the reasoning these mirrors
# deliberately do not restate.
#
# Note what is absent from all three tables: any column naming a **role**, a
# tenant the caller chose, or a unit. A credential resolves *who*; ``membership``
# above decides *what*, and it is written by an administrator rather than by
# anyone signing in.
# ---------------------------------------------------------------------------


pilot_credential = sa.Table(
    "pilot_credential",
    METADATA,
    sa.Column("id", _UUID, primary_key=True),
    sa.Column("tenant_id", _UUID, nullable=False),
    sa.Column("user_id", _UUID, nullable=False),
    # Stored, not assumed: verify_password compares this against the one
    # identifier it knows and refuses anything else rather than re-deriving an
    # unfamiliar row under today's defaults.
    sa.Column("algorithm", sa.Text, nullable=False),
    sa.Column("iterations", sa.Integer, nullable=False),
    sa.Column("salt", sa.LargeBinary, nullable=False),
    sa.Column("password_hash", sa.LargeBinary, nullable=False),
    sa.Column("created_at", _TS, nullable=False, server_default=sa.text("now()")),
    sa.Column("updated_at", _TS, nullable=False, server_default=sa.text("now()")),
    sa.PrimaryKeyConstraint("id", name="pilot_credential_pkey"),
    # CASCADE: a digest for a deleted account is a secret nobody owns.
    sa.ForeignKeyConstraint(
        ["tenant_id", "user_id"],
        ["user_account.tenant_id", "user_account.id"],
        ondelete="CASCADE",
    ),
    # Named because pilot_auth.py passes it to ON CONFLICT DO UPDATE when the
    # seed rewrites an existing credential.
    sa.UniqueConstraint("tenant_id", "user_id", name="uq_pilot_credential_account"),
    sa.CheckConstraint("algorithm = 'pbkdf2_hmac_sha256'", name="ck_pilot_credential_algorithm"),
    sa.CheckConstraint(
        "octet_length(salt) >= 16 AND octet_length(password_hash) = 32 AND iterations >= 100000",
        name="ck_pilot_credential_material",
    ),
)


pilot_session = sa.Table(
    "pilot_session",
    METADATA,
    sa.Column("id", _UUID, primary_key=True),
    sa.Column("tenant_id", _UUID, nullable=False),
    sa.Column("user_id", _UUID, nullable=False),
    # The SHA-256 of the token the browser holds; the token itself is stored
    # nowhere, so this column cannot be replayed as a credential.
    sa.Column("token_hash", sa.LargeBinary, nullable=False),
    sa.Column("issued_at", _TS, nullable=False, server_default=sa.text("now()")),
    sa.Column("expires_at", _TS, nullable=False),
    # Log-out sets this rather than deleting the row: "ended deliberately" is a
    # fact, and an absent row cannot state it.
    sa.Column("revoked_at", _TS, nullable=True),
    sa.PrimaryKeyConstraint("id", name="pilot_session_pkey"),
    sa.ForeignKeyConstraint(
        ["tenant_id", "user_id"],
        ["user_account.tenant_id", "user_account.id"],
        ondelete="CASCADE",
    ),
    # Named because every authenticated request resolves through this column,
    # and its uniqueness is what makes ``.one_or_none()`` sound there.
    sa.UniqueConstraint("token_hash", name="uq_pilot_session_token_hash"),
    sa.CheckConstraint(
        "expires_at > issued_at AND (revoked_at IS NULL OR revoked_at >= issued_at)",
        name="ck_pilot_session_window",
    ),
    sa.CheckConstraint("octet_length(token_hash) = 32", name="ck_pilot_session_token_hash"),
)


pilot_login_attempt = sa.Table(
    "pilot_login_attempt",
    METADATA,
    # Text and tenant-less, because a caller who has not authenticated has
    # neither a tenant nor a user id. See migration 0020 for why this is a
    # separate table rather than a relaxation of rate_limit_counter.
    sa.Column("caller_key", sa.Text, primary_key=True),
    sa.Column("window_start", _TS, primary_key=True),
    sa.Column("count", sa.Integer, nullable=False, server_default="0"),
    # Named because pilot_auth.py passes this name to ON CONFLICT DO UPDATE.
    sa.PrimaryKeyConstraint("caller_key", "window_start", name="pk_pilot_login_attempt"),
    sa.CheckConstraint("count >= 0", name="ck_pilot_login_attempt_count"),
)


# ---------------------------------------------------------------------------
# Outreach (migration 0021)
#
# Contacts and their consent evidence, drafts and their approvals, sends and
# their delivery streams, and the one authoritative suppression list. Every
# constraint's reasoning lives in that migration's module docstring and is not
# repeated here; what is repeated is only what a reader of this mirror needs in
# order to use the tables correctly.
#
# The one thing worth restating, because its absence is easy to read as an
# oversight: there is **no `suppressed` column** on `contact_channel`.
# Suppression lives only in `suppression_record`, so the two can never disagree
# — see `OutreachRepository.load_recipient`, which computes eligibility by
# joining rather than by reading a cached flag.
# ---------------------------------------------------------------------------


contact_channel = sa.Table(
    "contact_channel",
    METADATA,
    sa.Column("id", _UUID, primary_key=True),
    sa.Column("tenant_id", _UUID, nullable=False),
    # A5-shaped, as job.owning_unit_id and match_run.owning_unit_id are.
    sa.Column("owning_unit_id", _UUID, nullable=False),
    # No foreign key: no professional table exists in this schema yet, the same
    # situation professional_unit_relationship.professional_id is already in.
    sa.Column("professional_id", _UUID, nullable=False),
    sa.Column("channel_kind", sa.Text, nullable=False),
    sa.Column("address", sa.Text, nullable=False),
    sa.Column("contact_state", sa.Text, nullable=False),
    # Nullable because most lifecycle states legitimately have no consent
    # behind them. What is not legitimate is 'active_candidate' without an
    # approved one, which ck_contact_channel_sendable_consent forbids.
    sa.Column("consent_source", sa.Text, nullable=True),
    sa.Column("consent_recorded_at", _TS, nullable=True),
    sa.Column("consent_evidence", sa.Text, nullable=True),
    sa.Column("created_at", _TS, nullable=False, server_default=sa.text("now()")),
    # Carried, unlike match_run's deliberate omission: a contact's state moves
    # through the lifecycle, so mutation is expected here.
    sa.Column("updated_at", _TS, nullable=False, server_default=sa.text("now()")),
    sa.PrimaryKeyConstraint("id", name="contact_channel_pkey"),
    sa.UniqueConstraint("tenant_id", "id", name="uq_contact_channel_tenant_id"),
    sa.UniqueConstraint("tenant_id", "channel_kind", "address", name="uq_contact_channel_address"),
    sa.ForeignKeyConstraint(
        ["tenant_id", "owning_unit_id"],
        ["org_unit.tenant_id", "org_unit.id"],
        ondelete="RESTRICT",
    ),
    sa.CheckConstraint("channel_kind IN ('email')", name="ck_contact_channel_kind"),
    sa.CheckConstraint(
        "contact_state IN ('discovered', 'corroborated', 'reviewed', "
        "'relationship_recorded', 'rejected', 'consented', 'active_candidate', 'stale')",
        name="ck_contact_channel_state",
    ),
    sa.CheckConstraint(
        "consent_source IS NULL OR consent_source IN ('self_service', 'authenticated', "
        "'in_person', 'institutional_relationship', 'scraped', 'purchased', 'inferred')",
        name="ck_contact_channel_consent_source",
    ),
    # The constraint this table exists for: the one state that authorizes a
    # send must name an approved source for it. Research evidence can be
    # recorded and reviewed; it can never reach 'active_candidate'.
    sa.CheckConstraint(
        "contact_state <> 'active_candidate' OR (consent_source IS NOT NULL "
        "AND consent_source IN ('self_service', 'authenticated', 'in_person', "
        "'institutional_relationship'))",
        name="ck_contact_channel_sendable_consent",
    ),
    sa.CheckConstraint(
        "(consent_source IS NULL) = (consent_recorded_at IS NULL)",
        name="ck_contact_channel_consent_dated",
    ),
    sa.CheckConstraint(
        "length(btrim(address)) > 0 AND position('@' in address) > 1",
        name="ck_contact_channel_address_present",
    ),
)


# ---------------------------------------------------------------------------
# The consent audit trail (migration 0022)
#
# `contact_channel.contact_state` says where a contact is now; this table says
# how it got there, who moved it, and on what evidence. Append-only, enforced
# by a trigger the same way `delivery_event` is — an audit trail whose rows can
# be edited is a second mutable copy of the current state, not a trail.
#
# The legal edges are *not* mirrored here. They live in
# `smartmatch_domain.consent.STATE_TRANSITIONS` and nowhere else; this table
# records the moves that were made, and the domain decides which moves are
# legal. See migration 0022's docstring for why that separation is deliberate.
# ---------------------------------------------------------------------------


contact_channel_transition = sa.Table(
    "contact_channel_transition",
    METADATA,
    sa.Column("id", _UUID, primary_key=True),
    sa.Column("tenant_id", _UUID, nullable=False),
    sa.Column("contact_channel_id", _UUID, nullable=False),
    # NULL only for the registration row: a contact's first appearance is a
    # move from nothing to its initial state, recorded rather than implied.
    sa.Column("from_state", sa.Text, nullable=True),
    sa.Column("to_state", sa.Text, nullable=False),
    # Snapshotted, not referenced: a later correction to the contact must not
    # rewrite what an earlier transition was made on.
    sa.Column("consent_source", sa.Text, nullable=True),
    sa.Column("consent_evidence", sa.Text, nullable=True),
    sa.Column("reason", sa.Text, nullable=True),
    # NOT NULL: there is no lifecycle move nobody made.
    sa.Column("actor_user_id", _UUID, nullable=False),
    sa.Column("occurred_at", _TS, nullable=False),
    sa.Column("recorded_at", _TS, nullable=False, server_default=sa.text("now()")),
    sa.PrimaryKeyConstraint("id", name="contact_channel_transition_pkey"),
    sa.ForeignKeyConstraint(
        ["tenant_id", "contact_channel_id"],
        ["contact_channel.tenant_id", "contact_channel.id"],
        ondelete="RESTRICT",
    ),
    sa.ForeignKeyConstraint(
        ["tenant_id", "actor_user_id"],
        ["user_account.tenant_id", "user_account.id"],
        ondelete="RESTRICT",
    ),
    sa.CheckConstraint(
        "from_state IS NULL OR from_state IN ('discovered', 'corroborated', 'reviewed', "
        "'relationship_recorded', 'rejected', 'consented', 'active_candidate', 'stale')",
        name="ck_contact_channel_transition_from_state",
    ),
    sa.CheckConstraint(
        "to_state IN ('discovered', 'corroborated', 'reviewed', 'relationship_recorded', "
        "'rejected', 'consented', 'active_candidate', 'stale')",
        name="ck_contact_channel_transition_to_state",
    ),
    sa.CheckConstraint(
        "from_state IS NULL OR from_state <> to_state",
        name="ck_contact_channel_transition_moves",
    ),
    sa.CheckConstraint(
        "consent_source IS NULL OR consent_source IN ('self_service', 'authenticated', "
        "'in_person', 'institutional_relationship', 'scraped', 'purchased', 'inferred')",
        name="ck_contact_channel_transition_consent_source",
    ),
    # The same rule as ck_contact_channel_sendable_consent, stated about the
    # move rather than about the resulting row.
    sa.CheckConstraint(
        "to_state NOT IN ('consented', 'active_candidate') OR (consent_source IS NOT NULL "
        "AND consent_source IN ('self_service', 'authenticated', 'in_person', "
        "'institutional_relationship'))",
        name="ck_contact_channel_transition_consented_source",
    ),
    sa.CheckConstraint(
        "(reason IS NULL OR length(btrim(reason)) > 0) "
        "AND (consent_evidence IS NULL OR length(btrim(consent_evidence)) > 0)",
        name="ck_contact_channel_transition_text_present",
    ),
)

outreach_draft = sa.Table(
    "outreach_draft",
    METADATA,
    sa.Column("id", _UUID, primary_key=True),
    sa.Column("tenant_id", _UUID, nullable=False),
    sa.Column("owning_unit_id", _UUID, nullable=False),
    sa.Column("contact_channel_id", _UUID, nullable=False),
    # A key of smartmatch_domain.outreach.TEMPLATES. Text, not a foreign key:
    # the registry is code, closed, and reviewed in a diff.
    sa.Column("template_id", sa.Text, nullable=False),
    # Copied from the template at composition time. A template's status can
    # change; what was composed did not.
    sa.Column("content_status", sa.Text, nullable=False),
    # The rendered text, stored — not re-rendered at send time, so the approved
    # text and the sent text cannot differ.
    sa.Column("subject", sa.Text, nullable=False),
    sa.Column("body", sa.Text, nullable=False),
    sa.Column("status", sa.Text, nullable=False),
    # Which revision a coordinator approved. Stored rather than assumed because
    # SendRequest.approved_draft_version is a required field of the provider
    # interface, and a constant there would be a plausible number nobody
    # measured.
    sa.Column("version", sa.Integer, nullable=False, server_default=sa.text("1")),
    sa.Column("created_by", _UUID, nullable=False),
    sa.Column("created_at", _TS, nullable=False, server_default=sa.text("now()")),
    sa.Column("approved_by", _UUID, nullable=True),
    sa.Column("approved_at", _TS, nullable=True),
    sa.Column("superseded_by_draft_id", _UUID, nullable=True),
    sa.Column("updated_at", _TS, nullable=False, server_default=sa.text("now()")),
    sa.PrimaryKeyConstraint("id", name="outreach_draft_pkey"),
    sa.UniqueConstraint("tenant_id", "id", name="uq_outreach_draft_tenant_id"),
    sa.ForeignKeyConstraint(
        ["tenant_id", "owning_unit_id"],
        ["org_unit.tenant_id", "org_unit.id"],
        ondelete="RESTRICT",
    ),
    sa.ForeignKeyConstraint(
        ["tenant_id", "contact_channel_id"],
        ["contact_channel.tenant_id", "contact_channel.id"],
        ondelete="RESTRICT",
    ),
    sa.ForeignKeyConstraint(
        ["tenant_id", "created_by"],
        ["user_account.tenant_id", "user_account.id"],
        ondelete="RESTRICT",
    ),
    sa.ForeignKeyConstraint(
        ["tenant_id", "approved_by"],
        ["user_account.tenant_id", "user_account.id"],
        ondelete="RESTRICT",
    ),
    sa.ForeignKeyConstraint(
        ["tenant_id", "superseded_by_draft_id"],
        ["outreach_draft.tenant_id", "outreach_draft.id"],
        ondelete="RESTRICT",
    ),
    sa.CheckConstraint(
        "status IN ('draft', 'approved', 'superseded')", name="ck_outreach_draft_status"
    ),
    sa.CheckConstraint(
        "content_status IN ('synthetic', 'reviewed')",
        name="ck_outreach_draft_content_status",
    ),
    sa.CheckConstraint(
        "(approved_by IS NULL) = (approved_at IS NULL)",
        name="ck_outreach_draft_approval_dated",
    ),
    # One-directional on purpose: a superseded draft that was once approved
    # keeps its approval columns, because erasing them would destroy the record
    # of who signed off on text that may already have been sent.
    sa.CheckConstraint(
        "status <> 'approved' OR approved_by IS NOT NULL",
        name="ck_outreach_draft_approved_has_approver",
    ),
    sa.CheckConstraint(
        "superseded_by_draft_id IS NULL "
        "OR (status = 'superseded' AND superseded_by_draft_id <> id)",
        name="ck_outreach_draft_supersession",
    ),
    sa.CheckConstraint(
        "length(btrim(template_id)) > 0 AND length(btrim(subject)) > 0 AND length(btrim(body)) > 0",
        name="ck_outreach_draft_text_present",
    ),
    sa.CheckConstraint("version >= 1", name="ck_outreach_draft_version"),
)


outreach_send = sa.Table(
    "outreach_send",
    METADATA,
    sa.Column("id", _UUID, primary_key=True),
    sa.Column("tenant_id", _UUID, nullable=False),
    sa.Column("owning_unit_id", _UUID, nullable=False),
    sa.Column("draft_id", _UUID, nullable=False),
    # NOT NULL and constrained, which is what makes "no synchronous send" a
    # property of the schema: jobs are created only by commands.submit_command.
    sa.Column("job_id", _UUID, nullable=False),
    sa.Column("idempotency_key", sa.Text, nullable=False),
    # Snapshots taken at send time. "Who did we actually write to" must not
    # change when the contact's address is later corrected.
    sa.Column("recipient_address", sa.Text, nullable=False),
    sa.Column("from_address", sa.Text, nullable=False),
    # SHA-256 of the unsubscribe token, never the token itself.
    sa.Column("unsubscribe_token_hash", sa.Text, nullable=False),
    # NULL until the attempt concludes — an attempt in flight has no outcome,
    # and ADR-0011's rule is that unknown is never silently something else.
    sa.Column("disposition", sa.Text, nullable=True),
    sa.Column("provider", sa.Text, nullable=True),
    sa.Column("provider_message_id", sa.Text, nullable=True),
    sa.Column("failure_reason", sa.Text, nullable=True),
    sa.Column("created_at", _TS, nullable=False, server_default=sa.text("now()")),
    sa.Column("concluded_at", _TS, nullable=True),
    sa.PrimaryKeyConstraint("id", name="outreach_send_pkey"),
    sa.UniqueConstraint("tenant_id", "id", name="uq_outreach_send_tenant_id"),
    # Named here because outreach.py passes both to ON CONFLICT ON CONSTRAINT,
    # which makes the names an interface.
    sa.UniqueConstraint("tenant_id", "idempotency_key", name="uq_outreach_send_idempotency"),
    sa.UniqueConstraint("tenant_id", "job_id", name="uq_outreach_send_job"),
    # Globally unique, not tenant-scoped: the unsubscribe POST is
    # unauthenticated and has no tenant to scope a lookup by.
    sa.UniqueConstraint("unsubscribe_token_hash", name="uq_outreach_send_unsubscribe_token"),
    sa.ForeignKeyConstraint(
        ["tenant_id", "owning_unit_id"],
        ["org_unit.tenant_id", "org_unit.id"],
        ondelete="RESTRICT",
    ),
    sa.ForeignKeyConstraint(
        ["tenant_id", "draft_id"],
        ["outreach_draft.tenant_id", "outreach_draft.id"],
        ondelete="RESTRICT",
    ),
    sa.ForeignKeyConstraint(
        ["tenant_id", "job_id"],
        ["job.tenant_id", "job.id"],
        ondelete="RESTRICT",
    ),
    sa.CheckConstraint(
        "disposition IS NULL OR disposition IN ('accepted', 'blocked', 'failed')",
        name="ck_outreach_send_disposition",
    ),
    sa.CheckConstraint(
        "(disposition IS NULL) = (concluded_at IS NULL)",
        name="ck_outreach_send_concluded",
    ),
    # No fake success, structurally: a blocked or failed send cannot carry an
    # id a reader — or a UI — would take for a receipt.
    sa.CheckConstraint(
        "provider_message_id IS NULL OR disposition = 'accepted'",
        name="ck_outreach_send_message_id_means_accepted",
    ),
    sa.CheckConstraint(
        "disposition <> 'accepted' OR (provider IS NOT NULL AND provider_message_id IS NOT NULL)",
        name="ck_outreach_send_accepted_has_provider",
    ),
    sa.CheckConstraint(
        "disposition IS NULL "
        "OR (disposition IN ('blocked', 'failed')) = (failure_reason IS NOT NULL)",
        name="ck_outreach_send_failure_reason",
    ),
    sa.CheckConstraint(
        "length(btrim(idempotency_key)) > 0 "
        "AND length(btrim(recipient_address)) > 0 "
        "AND length(btrim(from_address)) > 0 "
        "AND length(btrim(unsubscribe_token_hash)) > 0",
        name="ck_outreach_send_fields_present",
    ),
)


delivery_event = sa.Table(
    "delivery_event",
    METADATA,
    sa.Column("id", _UUID, primary_key=True),
    sa.Column("tenant_id", _UUID, nullable=False),
    sa.Column("send_id", _UUID, nullable=False),
    sa.Column("event_type", sa.Text, nullable=False),
    # Two columns because they genuinely differ: a bounce webhook can arrive
    # hours after the bounce. Collapsing them would make the stream's ordering
    # a claim about our network rather than about the message.
    sa.Column("occurred_at", _TS, nullable=False),
    sa.Column("recorded_at", _TS, nullable=False, server_default=sa.text("now()")),
    # NULL for events this platform wrote itself. PostgreSQL treats NULLs as
    # distinct in a unique index, so our own events never collide while a
    # replayed provider webhook does.
    sa.Column("provider_event_id", sa.Text, nullable=True),
    sa.Column("detail", postgresql.JSONB, nullable=True),
    sa.PrimaryKeyConstraint("id", name="delivery_event_pkey"),
    sa.UniqueConstraint(
        "tenant_id", "send_id", "provider_event_id", name="uq_delivery_event_provider_event"
    ),
    sa.ForeignKeyConstraint(
        ["tenant_id", "send_id"],
        ["outreach_send.tenant_id", "outreach_send.id"],
        ondelete="RESTRICT",
    ),
    sa.CheckConstraint(
        "event_type IN ('queued', 'blocked', 'accepted', 'delivered', 'bounced', "
        "'complained', 'unsubscribed', 'failed')",
        name="ck_delivery_event_type",
    ),
    sa.CheckConstraint(
        "detail IS NULL OR jsonb_typeof(detail) = 'object'",
        name="ck_delivery_event_detail_object",
    ),
)


suppression_record = sa.Table(
    "suppression_record",
    METADATA,
    sa.Column("id", _UUID, primary_key=True),
    sa.Column("tenant_id", _UUID, nullable=False),
    # By address rather than by contact_channel_id: a person who unsubscribes
    # is telling us to stop writing to *them*, and a suppression must outlive
    # the record that provoked it.
    sa.Column("address", sa.Text, nullable=False),
    sa.Column("suppressed_at", _TS, nullable=False),
    sa.Column("source", sa.Text, nullable=False),
    # No foreign key to outreach_send: a suppression must survive the deletion
    # of the message that caused it, and a RESTRICT here would instead make
    # that message undeletable.
    sa.Column("origin_send_id", _UUID, nullable=True),
    sa.Column("created_at", _TS, nullable=False, server_default=sa.text("now()")),
    sa.PrimaryKeyConstraint("id", name="suppression_record_pkey"),
    # A repeated unsubscribe is the same instruction, not a second one. The
    # repository relies on this to make it idempotent rather than an error the
    # recipient would see.
    sa.UniqueConstraint("tenant_id", "address", name="uq_suppression_record_address"),
    sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"], ondelete="RESTRICT"),
    sa.CheckConstraint(
        "source IN ('unsubscribe_link', 'one_click', 'coordinator', 'bounce', 'complaint')",
        name="ck_suppression_record_source",
    ),
    sa.CheckConstraint("length(btrim(address)) > 0", name="ck_suppression_record_address_present"),
)


# ---------------------------------------------------------------------------
# The CBA classification model (migration 0024): customer §§7-8's two closed
# taxonomies, stored at two different cardinalities.
#
# A speaker has zero or one primary industry and zero or one primary role; a
# Speaker Request may target many of each. That asymmetry is why one side is
# columns on a table keyed by (tenant_id, professional_id) and the other is a
# child table — see the migration's docstring, which is not repeated here.
#
# Neither is `event_tag`. ADR-0012's twelve terms describe what kind of event
# this is and what function a speaker performs at it; these describe the
# industry a person works in and the career discipline they work within. The
# word "role" appears in both vocabularies and means unrelated things
# (`docs/product/cba-taxonomies.md`), which is exactly why the storage is
# separate and each row names the taxonomy version that evaluated it.
# ---------------------------------------------------------------------------


speaker_profile = sa.Table(
    "speaker_profile",
    METADATA,
    # Composite NATURAL key, no surrogate id — and unlike
    # professional_unit_relationship, which uses the same shape to *permit*
    # many rows per professional, this one uses it to forbid them. Customer
    # §7's "one primary industry sector" per speaker is this key: a second
    # primary value has no row to live in.
    sa.Column("tenant_id", _UUID, nullable=False),
    # This professional_id *does* carry a foreign key, unlike its two older
    # namesakes on professional_unit_relationship and contact_channel. Both of
    # those say "whichever migration gives professionals a persisted identity
    # should add this foreign key alongside it", and one has since: Choice A of
    # the synthetic pilot authorization makes `user_account` the persisted
    # professional identity, and pipeline_record.subject_id already references
    # it. Retrofitting the two older columns is its own migration
    # (OQ-CBA-009).
    sa.Column("professional_id", _UUID, nullable=False),
    # A5-shaped, as contact_channel.owning_unit_id and match_run.owning_unit_id
    # are: the unit whose Speaker Connector is accountable for this record.
    sa.Column("owning_unit_id", _UUID, nullable=False),
    # Customer §13's three identity fields, added by migration 0025. Before it
    # nothing in the schema held a person's name: the only `title` was
    # `event.title`, and `user_account.external_subject` is an identity key
    # whose `.invalid` placeholder must not be overloaded as a display field.
    #
    # NOT NULL, because a contact with no name is a row a Speaker Connector
    # cannot act on and §13's list surface would render blank. No server
    # default: a placeholder name outlives the uncertainty that produced it.
    sa.Column("full_name", sa.Text, nullable=False),
    # Optional, and genuinely so — a retired professional, an independent
    # consultant, or a contact met before the Connector learned where they
    # work. NULL says "nobody told us"; see the blank-text CHECK below for why
    # that is different from ''.
    sa.Column("company", sa.Text, nullable=True),
    sa.Column("title", sa.Text, nullable=True),
    # Customer §7. Nullable because §19 imports a contact first and classifies
    # it after — an unclassified speaker is a storable state, the same argument
    # ADR-0010 makes for an unresolved event date.
    sa.Column("primary_industry_code", sa.Text, nullable=True),
    # Which released taxonomy the code was resolved against. Both taxonomy
    # modules stamp one onto every `Classified…` value for the reason it is
    # stored: a code stays interpretable after a revision only if the row says
    # which table evaluated it.
    sa.Column("industry_taxonomy_version", sa.Text, nullable=True),
    # Customer §8, same shape for the same reason.
    sa.Column("primary_role_code", sa.Text, nullable=True),
    sa.Column("role_taxonomy_version", sa.Text, nullable=True),
    # §18's "Topic/interests/expertise text" and "optional prior talk
    # information". §9 compares them semantically against an event description;
    # nothing in persistence parses them.
    sa.Column("topic_text", sa.Text, nullable=True),
    sa.Column("prior_talk", sa.Text, nullable=True),
    # §10: city or ZIP is sufficient, so neither is derived from the other and
    # neither is required.
    sa.Column("location_city", sa.Text, nullable=True),
    sa.Column("location_postal_code", sa.Text, nullable=True),
    sa.Column("created_at", _TS, nullable=False, server_default=sa.text("now()")),
    # §§7-8 require a Speaker Connector to correct an assigned classification,
    # and a correction updates this row rather than superseding it — P9 Gate A
    # §2's current-state treatment of board_role. Whether the previous value is
    # retained anywhere is OQ-CBA-008, open when 0024 landed.
    sa.Column("updated_at", _TS, nullable=False, server_default=sa.text("now()")),
    sa.PrimaryKeyConstraint("tenant_id", "professional_id", name="speaker_profile_pkey"),
    # RESTRICT: a classification that outlived its subject would be an
    # assertion about nobody, and one that vanished with them would delete a
    # Speaker Connector's reviewed judgment as a side effect.
    sa.ForeignKeyConstraint(
        ["tenant_id", "professional_id"],
        ["user_account.tenant_id", "user_account.id"],
        ondelete="RESTRICT",
    ),
    sa.ForeignKeyConstraint(
        ["tenant_id", "owning_unit_id"],
        ["org_unit.tenant_id", "org_unit.id"],
        ondelete="RESTRICT",
    ),
    # The closed vocabularies, transcribed into the migration and mirrored here
    # for the same reason every other CHECK in this file is. The behavioural
    # binding back to smartmatch_domain lives in
    # tests/integration/test_cba_classification_schema.py, which parametrizes
    # over SECTOR_CODES and ROLE_CATEGORY_CODES from the domain modules, so a
    # taxonomy revision that never reached a migration fails there.
    sa.CheckConstraint(
        "primary_industry_code IS NULL OR primary_industry_code IN "
        "('11','21','22','23','31-33','42','44-45','48-49','51','52','53','54','55','56',"
        "'61','62','71','72','81','92')",
        name="ck_speaker_profile_industry_code",
    ),
    sa.CheckConstraint(
        "(primary_industry_code IS NULL) = (industry_taxonomy_version IS NULL)",
        name="ck_speaker_profile_industry_versioned",
    ),
    sa.CheckConstraint(
        "primary_role_code IS NULL OR primary_role_code IN "
        "('accounting','finance','marketing','management_strategy','human_resources',"
        "'operations_supply_chain','information_systems_analytics','international_business',"
        "'entrepreneurship_founder','sales_business_development')",
        name="ck_speaker_profile_role_code",
    ),
    sa.CheckConstraint(
        "(primary_role_code IS NULL) = (role_taxonomy_version IS NULL)",
        name="ck_speaker_profile_role_versioned",
    ),
    # ADR-0011: absent is a value, blank is a writer that forgot. §9 scores a
    # speaker with no topic information neutrally rather than at zero, which is
    # a decision about NULL — an empty string would reach it as text.
    #
    # Widened by migration 0025 to cover §13's two new nullable identity
    # columns, and to refuse a whitespace-only `full_name` — NOT NULL rejects
    # the absence and says nothing about '   ', which is a name-shaped value
    # that renders as nothing. One constraint rather than two, so there is a
    # single answer to "which text columns refuse blanks".
    sa.CheckConstraint(
        "length(btrim(full_name)) > 0 "
        "AND (topic_text IS NULL OR length(btrim(topic_text)) > 0) "
        "AND (prior_talk IS NULL OR length(btrim(prior_talk)) > 0) "
        "AND (location_city IS NULL OR length(btrim(location_city)) > 0) "
        "AND (location_postal_code IS NULL OR length(btrim(location_postal_code)) > 0) "
        "AND (company IS NULL OR length(btrim(company)) > 0) "
        "AND (title IS NULL OR length(btrim(title)) > 0)",
        name="ck_speaker_profile_text_present",
    ),
)


speaker_request_classification = sa.Table(
    "speaker_request_classification",
    METADATA,
    sa.Column("id", _UUID, primary_key=True),
    sa.Column("tenant_id", _UUID, nullable=False),
    # A Speaker Request is persisted as an `event` row: customer §4 renames
    # "Volunteer opportunity" to "Speaker Request", and the terminology
    # document maps that page onto the existing opportunity/event surface.
    sa.Column("event_id", _UUID, nullable=False),
    # Which of §§7-8's two axes this row targets, and therefore which closed
    # vocabulary `code` is held to.
    sa.Column("kind", sa.Text, nullable=False),
    # NOT NULL: a target naming nothing is not a target. There is no quarantine
    # arm here — a host picks from a list rather than resolving a spreadsheet
    # cell (OQ-CBA-010).
    sa.Column("code", sa.Text, nullable=False),
    # Unconditionally NOT NULL, unlike speaker_profile's pair, because `code`
    # is NOT NULL too: there is no absent case for it to mirror.
    sa.Column("taxonomy_version", sa.Text, nullable=False),
    sa.Column("created_at", _TS, nullable=False, server_default=sa.text("now()")),
    sa.PrimaryKeyConstraint("id", name="speaker_request_classification_pkey"),
    # CASCADE, as event_tag's reference to the same parent is: a target cannot
    # outlive the request stating it.
    sa.ForeignKeyConstraint(
        ["tenant_id", "event_id"],
        ["event.tenant_id", "event.id"],
        ondelete="CASCADE",
    ),
    # Multi-select is a set, not a bag: a repeated target is a weight counted
    # twice by a matcher with nothing on screen to explain it. Named here
    # because it is also pinned absolutely by
    # tests/integration/test_schema_matches_migration.py.
    sa.UniqueConstraint(
        "tenant_id",
        "event_id",
        "kind",
        "code",
        name="uq_speaker_request_classification",
    ),
    sa.CheckConstraint(
        "kind IN ('industry', 'role')",
        name="ck_speaker_request_classification_kind",
    ),
    # `kind` decides which vocabulary applies. Without this conditional, `kind`
    # would be a label the row carries rather than a statement the database
    # holds it to, and an industry target reading 'finance' could sit beside a
    # role target reading '52'.
    sa.CheckConstraint(
        "(kind = 'industry' AND code IN "
        "('11','21','22','23','31-33','42','44-45','48-49','51','52','53','54','55','56',"
        "'61','62','71','72','81','92')) "
        "OR (kind = 'role' AND code IN "
        "('accounting','finance','marketing','management_strategy','human_resources',"
        "'operations_supply_chain','information_systems_analytics','international_business',"
        "'entrepreneurship_founder','sales_business_development'))",
        name="ck_speaker_request_classification_code",
    ),
)
