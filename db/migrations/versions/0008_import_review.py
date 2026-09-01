"""The quarantine-and-review path: ``import_batch`` and ``review_item``.

Revision ID: 0008_import_review
Revises: 0007_drop_tenant_subject
Create Date: 2026-08-28

Architecture v1.1 §1.5: a validated import produces review items, not verified
records. ``handle_import_create`` (``services/worker/smartmatch_worker/handlers.py``)
already refuses every live import for exactly this reason — it names the
missing ``review_item`` table in its own ``PolicyFailure`` message, as
``import_content_unavailable``. This migration is what lets that refusal go
away for the storage half of the problem; the object-storage adapter that reads
``source_reference`` is separate, unbuilt work.

Two tables only, not the five the plan once called for
----------------------------------------------------------
An earlier draft of this migration also carried ``event``, ``event_tag`` and
``engagement_stage_entry``. All three are deferred, on record rather than
forgotten:

* ``docs/architecture/engagement-model.md`` states its own tables land in
  **R2**, and depend on open decisions D6 (rewards budget owner), D7 (economy
  calibration), D8 (disclosure-consent policy) — none of which are settled.
* The tag vocabulary an ``event_tag`` row would validate against sits behind
  gate **G3** (ADR-0012, backlog S5): unmapped values are meant to be
  quarantined against a *closed* vocabulary that does not exist yet.

Building those three now would be building tables application code is
forbidden from writing to until decisions this migration cannot make are made
elsewhere. ``import_batch`` and ``review_item`` are different: nothing gates
them. ``smartmatch_domain.ingest.validate_columns`` is already written and
already imported by the worker; the only thing missing is somewhere for its
output to land.

The shape: a batch, and the rows quarantined under it
-------------------------------------------------------
``import_batch`` is one submitted import — the record of *what was submitted*,
written once when ``import.create`` executes. ``review_item`` is one row from
that submission awaiting a human decision, carrying the row's position (so a
coordinator can find it in their source file) and its normalized values as
JSONB. A usable dataset (``DatasetQuality.is_usable``) produces one
``review_item`` per row; nothing here decides what happens to a dataset that
is not usable — that stays the caller's problem, exactly as
``handle_import_create``'s docstring says the worker's job stops at validating
the command, not the caller's data.

Ownership, not just tenancy
----------------------------
``import_batch`` carries ``owning_unit_id`` the same way ``job`` does
(migration ``0006``, backlog A5): a composite foreign key to
``org_unit (tenant_id, id)``, never a bare id, because the single-column form
would accept a batch in one tenant naming a unit in another and every
authorization decision about its review items would then be made against a
path in a tree their tenant has no relationship to. It is **not** copied from
``job.owning_unit_id`` at read time; it is its own column, populated from the
same ``unit_id`` the submission authorized against, so that a review-item
listing scoped to a unit is a query against ``import_batch`` directly and never
has to join back through ``job`` to find out what it may show.

Two composite foreign keys, two delete actions, both deliberate
------------------------------------------------------------------
``import_batch`` has two tenant-owned parents, and they get different
``ondelete`` actions for different reasons:

* ``(tenant_id, job_id) -> job (tenant_id, id)`` is ``ON DELETE CASCADE``. This
  is the same relationship ``job_event``, ``outbox_record`` and
  ``redrive_record`` already have to ``job``, and it is the same shape:
  ``import_batch`` is a thing a job's execution produced, not an independent
  entity that happens to name a job. Nothing in this codebase deletes a job —
  no route exists — so the practical difference from ``RESTRICT`` is nil today;
  the convention is followed anyway because these four tables should not read
  as three that agree and one that doesn't.
* ``(tenant_id, owning_unit_id) -> org_unit (tenant_id, id)`` is
  ``ON DELETE RESTRICT``, for the reason ``0006`` gives ``job.owning_unit_id``
  the same action: a unit is reorganized far more often than a tenant is
  deleted, and ``CASCADE`` would make a routine reorganization silently delete
  the record of every import ever submitted into that unit, along with every
  review item still awaiting a decision. ``RESTRICT`` makes the reorganization
  refuse until a person has decided where that pending review work goes.

``review_item`` has one tenant-owned parent, ``import_batch``, referenced the
same composite way and ``ON DELETE CASCADE``: a review item cannot outlive the
batch that quarantined it, and — because ``import_batch`` itself cascades from
``job`` — deleting a job's row (were that ever to happen) correctly takes its
batches and every item in them with it, in one statement, without either table
needing to know about the other's existence.

Neither table gets a direct single-column foreign key to ``tenant``. That is
not an omission: every table in this schema that is scoped to a tenant only
*through* another tenant-owned table (``job_event``, ``outbox_record``,
``redrive_record``, ``membership``, ``resource_grant``) carries only the
composite key to that parent, never a redundant direct pointer to ``tenant``
as well — ``job`` is the one exception, and it is a historical one:
``job.tenant_id -> tenant.id`` predates ``owning_unit_id`` by five revisions
(``0001`` versus ``0006``). ``import_batch`` and ``review_item`` are designed
fresh with both their tenant-owned parents already in hand, so they follow the
plain rule rather than repeat the accident.
``tests/integration/test_schema_matches_migration.py::test_every_tenant_scoped_table_is_anchored_by_a_composite_key``
requires only *one* qualifying foreign key per table, and each of these has
one.

``uq_import_batch_tenant_id`` on ``(tenant_id, id)`` exists for the reason
every such constraint in this schema exists: it is what ``review_item``'s
composite foreign key references, per ADR-0004. ``review_item`` needs no
equivalent — nothing below it references it.

No ``version`` column, on either table
----------------------------------------
The instruction from the architecture is to carry one "if the surrounding
tables carry one" or "if consistent with neighbours," so the neighbours are
what settles it. ``version`` in this schema marks a durable, independently
addressed entity — ``org_unit``, ``user_account``, ``job`` — not a row reached
only through another tenant-owned table's composite key. ``job_event``,
``outbox_record`` and ``redrive_record`` are the tables actually shaped like
these two — reached from ``job`` by composite foreign key — and despite two of
them (``outbox_record.status``, ``redrive_record.redriven_at``/``redriven_by``)
being mutated after their initial insert, none of the three carries a
``version``. ``import_batch`` and ``review_item`` are reached the same way, so
they follow that convention rather than ``job``'s: a future reviewer UI that
needs a stale-write guard on ``review_item.status`` can build a conditional
``UPDATE ... WHERE status = 'pending'``, the same shape ``JobRepository.claim``
already uses against ``job.status``, without a counter column to keep in step.

``uq_review_item_batch_row`` on ``(import_batch_id, row_index)``
--------------------------------------------------------------------
Mirrors ``uq_job_event_sequence`` on ``(job_id, sequence)`` (migration
``0001``) exactly, and for the same reason: ``row_index`` is a monotonic
position within one parent, ``import_batch_id`` is already globally unique (it
references a primary key), so the pair needs no ``tenant_id`` alongside it to
be a sound uniqueness key. It guarantees a coordinator's source-file position
maps to at most one review item, the property that makes "find row 41 in your
file" a query rather than a hope.

``ck_review_item_status`` — ``pending`` / ``accepted`` / ``rejected``
--------------------------------------------------------------------------
Named per this schema's convention (ADR-0004's mirror docstring: CHECK
constraints carry their database name so the drift test can catch one added to
a migration and never mirrored). The three-value vocabulary is the one v1.1
§1.5 describes: a review item is quarantined (``pending``), and a human
resolves it one way or the other. Nothing broader is added on spec —
``duplicate`` or ``superseded`` are plausible future outcomes of a review
workflow that does not exist yet, and this migration adds exactly the two
tables asked for and nothing a later gate has not settled.

What this migration deliberately does not add
--------------------------------------------------
No index beyond what the constraints above require. Nothing queries
``review_item`` yet — the endpoint that would (list pending items for a batch,
or for a unit) is exactly the follow-on work this migration exists to unblock,
and its access pattern is not this migration's to guess at. ``job.owning_unit_id``
(migration ``0006``) makes the same call for the same reason: an index added to
serve a query nobody issues costs every future write and serves nothing until
one does.

No ``row_count`` non-negativity check. Every other numeric CHECK in this schema
(``ck_budget_non_negative``, ``ck_rate_limit_count_non_negative``) guards a
column something *decrements* — a balance, a quota — where a negative value is
a specific, reachable bug. ``row_count`` is written once, from ``len(rows)`` at
validation time (``smartmatch_domain.ingest.validate_columns``), and nothing
in this codebase ever subtracts from it. Adding a constraint with no failure
mode to guard against would be decoration, not a guarantee.

Single transaction, no backfill
------------------------------------
Both tables are new; no existing row needs a value written into a column it
did not have. This is `0001`'s shape, not `0006`'s: nothing to lock, nothing to
guard with a live-connection precondition, no reason to split expand from
contract (v1.1 §4.2, ADR-0009). ``transaction_per_migration=True``
(``db/migrations/env.py``) holds the whole thing in one transaction, and at an
empty table that transaction is momentary.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0008_import_review"
down_revision = "0007_drop_tenant_subject"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create ``import_batch`` and ``review_item``. Nothing else."""
    op.create_table(
        "import_batch",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        # A5-shaped: the unit this import landed in, the thing every
        # authorization decision about its review items is scoped against.
        sa.Column("owning_unit_id", postgresql.UUID(as_uuid=True), nullable=False),
        # The durable command job that produced this batch (v1.1 §1.6).
        sa.Column("job_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("dataset", sa.Text(), nullable=False),
        sa.Column("row_count", sa.Integer(), nullable=False),
        sa.Column("dry_run", sa.Boolean(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("id"),
        # What review_item's composite foreign key below references.
        sa.UniqueConstraint("tenant_id", "id", name="uq_import_batch_tenant_id"),
        # CASCADE: a batch is a thing a job's execution produced, the same
        # relationship job_event/outbox_record/redrive_record already have to
        # job. See the module docstring for why this differs from the next FK.
        sa.ForeignKeyConstraint(
            ["tenant_id", "job_id"], ["job.tenant_id", "job.id"], ondelete="CASCADE"
        ),
        # RESTRICT: reorganizing a unit must not silently delete the pending
        # review work submitted into it, the same intent job.owning_unit_id
        # carries against org_unit (migration 0006).
        sa.ForeignKeyConstraint(
            ["tenant_id", "owning_unit_id"],
            ["org_unit.tenant_id", "org_unit.id"],
            ondelete="RESTRICT",
        ),
    )

    op.create_table(
        "review_item",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("import_batch_id", postgresql.UUID(as_uuid=True), nullable=False),
        # This row's position in the submitted batch, so a coordinator can find
        # it in their source file. 0-based, matching len(rows) indexing in
        # smartmatch_domain.ingest.
        sa.Column("row_index", sa.Integer(), nullable=False),
        # The normalized row itself — validate_columns's per-row output, not
        # the raw submission. Structure is the caller's, not this schema's, to
        # constrain: import contracts vary by dataset.
        sa.Column("row_data", postgresql.JSONB(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default="pending"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("id"),
        # CASCADE: a review item cannot outlive the batch that quarantined it.
        sa.ForeignKeyConstraint(
            ["tenant_id", "import_batch_id"],
            ["import_batch.tenant_id", "import_batch.id"],
            ondelete="CASCADE",
        ),
        # Mirrors uq_job_event_sequence: a monotonic position within one
        # parent, and the parent id alone is already globally unique.
        sa.UniqueConstraint(
            "import_batch_id", "row_index", name="uq_review_item_batch_row"
        ),
        sa.CheckConstraint(
            "status IN ('pending','accepted','rejected')",
            name="ck_review_item_status",
        ),
    )


def downgrade() -> None:
    """Drop both tables.

    A development tool, not a production rollback path (v1.1 §4.2): this
    migration is expand-only and destructive rollback is never how a release is
    reversed. ``review_item`` is dropped first because it is the dependent side
    of the one foreign key between these two tables; PostgreSQL would enforce
    the same order via CASCADE if it were dropped implicitly, but an explicit
    order is what a reader of this function should be able to rely on without
    checking.
    """
    op.drop_table("review_item")
    op.drop_table("import_batch")
