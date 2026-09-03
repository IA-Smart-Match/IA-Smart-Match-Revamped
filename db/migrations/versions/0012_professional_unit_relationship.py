"""``professional_unit_relationship`` — board_role, relationship-scoped (P9 Gate A).

Revision ID: 0012_professional_unit_rel
Revises: 0011_pipeline_record
Create Date: 2026-09-02

**Revision id, not filename.** ``revision`` below is
``"0012_professional_unit_rel"`` (26 characters) rather than this file's own
stem: Alembic's ``alembic_version.version_num`` column is ``String(32)`` by
default (``alembic.ddl.impl``, ``Column("version_num", String(32), ...)``),
and the table name this migration creates is 35 characters. Widening that
column is explicitly not the fix — it is Alembic's own column, every other
revision in this repository fits it comfortably, and widening it to
accommodate one over-long identifier would be solving this migration's
problem in a place every other migration would then depend on. Shortening
the id is the same move ``0001_foundation_baseline.py`` (revision
``"0001_foundation"``) and ``0004_lease_and_generation_columns.py``
(revision ``"0004_lease_and_generation"``) already made: the filename may be
descriptive, the revision id stays short.

`docs/decisions/p9-gate-a-board-role-decision-draft.md`, CLOSED 2026-09-02.
§1 decides that ``board_role`` is relationship-scoped — it varies by
``(professional, unit)``, not as one intrinsic attribute on a person — and §2
answers the follow-on questions this migration's shape encodes. §4 records
that the program owner authorized this schema change for this slice (P9 pilot
columns V2); this file is that authorization exercised as source, not as an
applied migration — it is authored here for a later operator to apply, and
running ``alembic upgrade`` against a real pilot database is that operator's
action, not this change's.

One row per (professional, unit) relationship, not per professional
-------------------------------------------------------------------
The primary key is the composite natural key
``(tenant_id, professional_id, unit_id)`` — no surrogate ``id`` column, the
same choice ``spend_ceiling_bucket`` (migration 0010) and
``rate_limit_counter`` (migration 0002) already made for a row whose identity
is exactly what a caller already knows. That composite key is also how Gate A
§2's multiplicity answer is represented: **"multiple concurrent board_role
values per person across different unit relationships must be
representable"** falls directly out of the key shape, because the same
``professional_id`` may appear in as many rows as it has distinct
``unit_id`` relationships. No separate multiplicity column or array type is
needed, or added.

No ``effective_from`` / ``effective_to``, and that is the design, not an omission
-----------------------------------------------------------------------------------
Gate A §2 is explicit: **"pilot treats board_role as current-state only on
each relationship; no effective_from / effective_to columns for pilot."**
Adding history-tracking columns anyway — "for flexibility" — would answer a
question the gate deferred to a later decision rather than settling it now,
which is exactly the failure shape ADR-0013's "no discretionary grant" and
this repository's general distrust of speculative columns both already
argue against. Gate A §2's "correction semantics" — a coordinator's
correction **updates the current relationship record** rather than
superseding it with a dated new one — is what makes ``updated_at`` the
correct column to carry here instead of a history table: this row is
expected to be mutated, unlike an append-only ledger such as
``point_ledger_entry`` (migration 0009), which deliberately carries no
``updated_at`` for the opposite reason.

``professional_id`` has no foreign key, and that is the same situation as two existing columns
--------------------------------------------------------------------------------------------------
There is still no ``professional`` table in this schema. P9 pilot
professionals are import/review data today
(``docs/pilot-data/columns.yaml``, quarantined into ``review_item`` by
``smartmatch_worker.handlers``) — not a persisted entity with a stable id of
its own. ``attendance_record.event_id`` (migration 0009) and
``pipeline_record.opportunity_event_id`` (migration 0011) are already
exactly this situation for their own not-yet-built parent table (``event``,
owned by plan P6), and both migrations' docstrings give the same answer this
one gives: a constraint referencing a table that does not exist cannot be
written, and a loosely-typed placeholder would misstate the guarantee rather
than omit it. **Whichever migration gives professionals a persisted identity
should add this foreign key alongside it.**

``unit_id`` is composite and ``RESTRICT``, matching every other unit reference in this schema
--------------------------------------------------------------------------------------------------
``owning_unit_id`` on ``job`` (0006), ``import_batch`` (0008), and
``attendance_record`` (0009) all carry a composite
``(tenant_id, unit_id) -> org_unit(tenant_id, id)`` foreign key with
``ondelete="RESTRICT"``: a single-column key to ``org_unit.id`` would accept
a relationship in one tenant naming a unit that belongs to another (ADR-0004
v1.1 §2.2), and ``RESTRICT`` keeps a unit reorganization from silently
deleting the board-role relationships recorded against it. This migration's
foreign key is that same constraint, for the same reason, spelled the same
way.

No CHECK constraint on ``board_role``
--------------------------------------
Gate A did not ratify a closed vocabulary for board roles — the fixtures
(``docs/pilot-data/fixtures/professionals_clean.json``) carry free text such
as "Director", "Treasurer", "Secretary", "VP Programs", and "President", and
nothing in the gate record narrows that set. Unlike
``ck_attendance_record_method`` or ``ck_spend_ceiling_bucket_type``, which pin
a vocabulary an ADR actually specifies, inventing one here would be enforcing
an answer the gate never gave.

No index beyond the primary key
---------------------------------
The primary key already covers the only access pattern this slice needs — a
lookup by ``(tenant_id, professional_id, unit_id)`` — and, per this schema's
own stated practice (``schema.py``'s module docstring: "Index sets are not
compared because schema.py declares no indexes on purpose"), a speculative
index is not added ahead of a query that needs it.

**Applying this revision.** Per ADR-0009, this revision runs in its own
transaction (``transaction_per_migration=True`` in ``db/migrations/env.py``),
independently of every other pending revision. It creates one new table and
touches no existing one, so it needs no data backfill and is safe under a
rolling deploy per v1.1 §4.2's expand/migrate/contract discipline: the old
release simply does not know this table exists yet.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0012_professional_unit_rel"
down_revision = "0011_pipeline_record"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create ``professional_unit_relationship``."""
    op.create_table(
        "professional_unit_relationship",
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        # No foreign key: no professional table exists yet. See the module
        # docstring — the same situation attendance_record.event_id and
        # pipeline_record.opportunity_event_id are already in.
        sa.Column("professional_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("unit_id", postgresql.UUID(as_uuid=True), nullable=False),
        # NOT NULL: a relationship row with no role records nothing this
        # table exists to hold (the same reasoning reward_item.budget_owner_id,
        # D6, already applies to a column that would be meaningless if absent).
        sa.Column("board_role", sa.Text, nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        # A correction updates this row (Gate A §2), so — unlike
        # point_ledger_entry — mutation is expected here, and updated_at
        # says so structurally.
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        # The composite natural key IS the primary key. No effective_from /
        # effective_to columns — Gate A §2, current-state only for the pilot.
        sa.PrimaryKeyConstraint(
            "tenant_id",
            "professional_id",
            "unit_id",
            name="professional_unit_relationship_pkey",
        ),
        # RESTRICT: reorganizing a unit must not silently delete the
        # board-role relationships recorded against it. Composite, so a
        # relationship in one tenant cannot name a unit in another.
        sa.ForeignKeyConstraint(
            ["tenant_id", "unit_id"],
            ["org_unit.tenant_id", "org_unit.id"],
            ondelete="RESTRICT",
        ),
    )


def downgrade() -> None:
    """Drop the table.

    A development tool, not a production rollback path (v1.1 §4.2). Nothing
    in this schema references ``professional_unit_relationship``, so the drop
    is unconditional.
    """
    op.drop_table("professional_unit_relationship")
