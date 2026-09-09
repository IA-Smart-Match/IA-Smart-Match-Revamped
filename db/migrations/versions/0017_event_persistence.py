"""``event``, ``event_tag``, ``discovery_review_item`` — the P6 event model (cards S3–S5f).

Revision ID: 0017_event_persistence
Revises: 0016_pipeline_provenance
Create Date: 2026-09-03

ADR-0010 (an event carries an instant, an IANA zone, and a precision),
ADR-0012 (deterministic identity, structured provenance, closed tag
vocabulary), plan `docs/plans/2026-08-28-g3-events-s3-s5-plan.md` cards S3,
S4, S5 and S5f, and the signed G3 decision
`docs/decisions/g3-crawler-decision.md`.

`smartmatch_domain.events` has held the pure half of both ADRs since R2 —
`resolve_identity_key` returns `None` for `UnresolvedTime`, `resolve_tag`
quarantines an unmapped value, `QuarantinedTag` has no `term` field to reach.
Its own docstring says the tables "are not implemented here; they are deferred
to R2 behind open decisions D6-D8 ... This module is the contract those land
against." This migration is the landing.

**Storage only.** No route reads these tables, no crawler writes them, and
nothing in this repository fetches a URL. The event list surface, the crawl
adapter, and `CrawlerFeed` are later cards and are deliberately absent.

Three tables, and why each is separate
---------------------------------------
``event`` carries display fields, the ADR-0010 temporal triple, the ADR-0012
identity components, and structured provenance — as columns, per card S3's own
wording ("structured provenance columns (source URL, fetch time, extractor
version) separate from display fields"). The richer pair the R3 record asks
for (``event_source_observation`` and a standalone ``event_provenance``,
`r3-signing-decisions-2026-09-03.md` T-27) is a superset of this and is left
to the card that needs a second observation of the same event; nothing here
forecloses it, because provenance already lives in its own named columns
rather than inside a display string.

``event_tag`` is one row per resolved tag, and it stores the *resolution*, not
the raw text plus a flag. ``smartmatch_domain.events`` makes an unmapped value
unconstructible as a matchable one — ``QuarantinedTag`` has no ``term``
attribute at all — and ``ck_event_tag_resolution_shape`` is that same property
expressed in the database: a quarantined row has no ``term`` column value for
a query to ``SELECT`` by accident, so "never rendered and never matched on"
survives a caller who forgets to filter.

``discovery_review_item`` is a **new table**, and G3 §5 decides it explicitly
("Accept a new ``discovery_review_item`` table"). ``review_item`` was the
alternative and is structurally wrong for this: it hangs off ``import_batch``
by a composite foreign key with ``ON DELETE CASCADE`` (migration ``0008``), so
a discovery finding parked there would be deleted along with an unrelated
coordinator's import batch — a review queue that silently loses entries when
somebody tidies up an import. ``review_item`` is left exactly as it is.

Unpublished means unresolved dates, or quarantined tags
--------------------------------------------------------
``ck_event_publishable`` is the ADR-0010 rule 2 constraint — "an event at
``unresolved`` cannot reach a matchable or publishable state ... a
state-machine constraint, not a validation warning" — plus ADR-0012's
quarantine rule, in one predicate:

    publication_status = 'unpublished'
    OR (time_precision <> 'unresolved' AND quarantined_tag_count = 0)

The tag half needs a number on this row, because a CHECK cannot see another
table. ``quarantined_tag_count`` is that number, maintained by
``smartmatch_persistence.events`` alongside every ``event_tag`` write, and
``ck_event_quarantined_tag_count_non_negative`` keeps it from going negative
if a future writer ever gets its arithmetic wrong. A denormalised counter is a
real cost — it can drift from the rows it counts — and it is paid deliberately:
the alternative is a trigger, and a trigger is a second place where the
publish rule lives with no test naming it.

Unresolved events stay unkeyed, and PostgreSQL's NULL rules are what does it
-----------------------------------------------------------------------------
ADR-0012: "An event at ``unresolved`` precision **has no identity key** and
cannot be resolved against anything." ``uq_event_identity`` spans
``(tenant_id, host_org_unit_id, normalized_title, resolved_date)``, and
``resolved_date`` is NULL exactly when the precision is ``unresolved``
(``ck_event_identity_iff_resolved``). A UNIQUE constraint in PostgreSQL treats
NULLs as distinct, so two unresolved events with the identical host and title
do **not** collide — they insert as two rows, distinct, unmatchable, and
visible to review, which is the honest state the ADR names. No partial index
and no application branch is needed to get that; it falls out of the key
itself. A resolved event, by contrast, collides on its second extraction and
the writer's ``ON CONFLICT ON CONSTRAINT uq_event_identity DO UPDATE`` updates
rather than inserting.

``origin`` and the provenance biconditional
--------------------------------------------
ADR-0012 closes with "Manual event entry uses the same key and the same
vocabulary. A coordinator typing an event is not exempt, or the duplicate class
reopens through a second door." A coordinator-entered event has no source URL,
no fetch time, and no extractor version, so those three columns are nullable —
and ``ck_event_provenance_evidence`` makes them a biconditional with ``origin``
so that nullable does not degrade into optional. The idiom is
``ck_pipeline_record_attendance_evidence`` (0011) and
``ck_review_item_decision_evidence`` (0013): a claim names its evidence, and
evidence is never carried without the claim it supports. An extraction that
cannot say where it came from is not storable, which is the fabricated-field
defect (Fix #15, H21) closed one table over.

``attendance_record.event_id`` gets its foreign key (card S5f)
---------------------------------------------------------------
Migration ``0009`` left that column unconstrained with the comment "No foreign
key: no event table exists yet in this schema. Whichever migration adds one
should also add this constraint." This is that migration, and the constraint is
composite — ``(tenant_id, event_id)`` against ``uq_event_tenant_id`` — for the
same reason every other foreign key in this schema is: a single-column key to
``event.id`` would let one tenant's attendance row cite another tenant's event
and the isolation guarantee in v1.1 §2.2 would be gone without anybody
noticing. ``ON DELETE RESTRICT``: attendance is the only input to points
(ADR-0013), and deleting the event out from under a credited attendance would
leave a ledger entry nothing could explain.

``pipeline_record.opportunity_event_id`` is **deliberately not** given the same
treatment here, although ``0011``'s docstring asks for both together. That
column belongs to the S12 opportunities surface, its rows are written by
``smartmatch_persistence.pipeline``, and constraining it is a change to what
that writer must produce — a different card's decision, made against a table
this one only just created. ``test_pipeline_record_constraints.py``'s standing
assertion about that column's foreign keys is unchanged by this migration and
still passes; it is the test that will tell the next card to act.

Expand only
-----------
Every statement here is additive: three new tables and one new constraint on an
existing column. Nothing is dropped, renamed, or backfilled, so this revision is
safe to run ahead of the code that reads it (v1.1 §4.2, ADR-0009).

The one precondition is that ``attendance_record`` holds no row whose
``event_id`` refers to nothing — which is every row it holds today, since no
event table existed to refer to. On an empty database (CI, and the
``migrate-check`` gate) there is nothing to fail. On a developer database
carrying leftover synthetic attendance rows, the foreign key will refuse, and
the fix is to delete those rows: they cite an event that never existed, which
is precisely the state this constraint exists to make unrepresentable. That is
stated rather than automated — a migration that silently deleted rows to make
its own constraint apply would be doing the deciding for an operator.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0017_event_persistence"
down_revision = "0016_pipeline_provenance"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create the three event tables and constrain ``attendance_record.event_id``."""
    op.create_table(
        "event",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        # ADR-0012: "the org_unit the event belongs to, not the page it was
        # found on". A5-shaped, as job.owning_unit_id (0006) and
        # attendance_record.owning_unit_id (0009) are: the unit every
        # authorization decision about this row is scoped against.
        sa.Column("host_org_unit_id", postgresql.UUID(as_uuid=True), nullable=False),
        # The display title, exactly as a human would read it. ADR-0012's
        # "titles carrying their source" defect is closed structurally: the
        # provenance columns below are where a source name goes, and no code
        # path in smartmatch_domain.events can produce a string combining the
        # two.
        sa.Column("title", sa.Text, nullable=False),
        # normalize_title()'s output — case-folded, whitespace-collapsed,
        # punctuation-stripped. Stored rather than computed in the index so the
        # exact value the writer keyed on is readable, and so a change to the
        # folding rule is a visible data difference rather than a silent
        # re-partitioning of the identity space.
        sa.Column("normalized_title", sa.Text, nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        # --- ADR-0010's temporal triple -----------------------------------
        # The instant, in UTC. Present only at 'exact'.
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=True),
        # The calendar date, with no clock time. Present only at 'date_only' —
        # DateOnlyTime deliberately has no starts_at field, because collapsing
        # a date-only event to midnight is the fabrication that produced the
        # 3 AM / 7 AM listings (stakeholder log, Fix #6).
        sa.Column("on_date", sa.Date, nullable=True),
        # An IANA zone name — the zone the event happens in, never the
        # viewer's and never the server's (ADR-0010 rule 1). NULL only when
        # there is no time at all to place in a zone.
        sa.Column("time_zone", sa.Text, nullable=True),
        # The precision enum itself, mirroring
        # smartmatch_domain.events.TimePrecision. Stored, not inferred:
        # ADR-0010 rejects deriving date_only from a midnight timestamp
        # because that heuristic mislabels events that genuinely start at
        # midnight.
        sa.Column("time_precision", sa.Text, nullable=False),
        # --- ADR-0012's identity ------------------------------------------
        # The key's date component: resolved_date(event_time). NULL exactly
        # when the precision is 'unresolved', which is what leaves such an
        # event out of uq_event_identity entirely.
        sa.Column("resolved_date", sa.Date, nullable=True),
        # --- state --------------------------------------------------------
        sa.Column("publication_status", sa.Text, nullable=False, server_default="unpublished"),
        # G3 §5: "every first-seen event requires human approval". Recorded
        # here; deliberately *not* folded into ck_event_publishable, which
        # states only the two ADR-pinned reasons an event cannot publish. A
        # review policy is a product decision that will change; the ADR
        # invariants are not, and mixing them into one predicate would make a
        # policy change look like an ADR change.
        sa.Column("review_status", sa.Text, nullable=False, server_default="pending"),
        # How many quarantined tags this event carries. See the module
        # docstring: a CHECK cannot see another table, and this is what lets
        # the publish rule name ADR-0012's quarantine half at all.
        sa.Column("quarantined_tag_count", sa.Integer, nullable=False, server_default="0"),
        # --- ADR-0012's structured provenance -----------------------------
        # Mirrors smartmatch_domain.events.EventProvenance field for field.
        # All three are NULL together for a coordinator-entered event; see
        # ck_event_provenance_evidence.
        sa.Column("origin", sa.Text, nullable=False),
        sa.Column("source_url", sa.Text, nullable=True),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("extractor_version", sa.Text, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        # This row does change — a second extraction of the same event updates
        # it (ADR-0012) — so it carries updated_at, and carrying one is a
        # statement that mutation is expected here (0011's reasoning).
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("id", name="event_pkey"),
        # What attendance_record's composite foreign key below references, and
        # event_tag's and discovery_review_item's.
        sa.UniqueConstraint("tenant_id", "id", name="uq_event_tenant_id"),
        # ADR-0012's deterministic key. tenant_id is part of it because an
        # org_unit id is only unique within a tenant here, and two tenants
        # describing the same public event are not describing the same row.
        sa.UniqueConstraint(
            "tenant_id",
            "host_org_unit_id",
            "normalized_title",
            "resolved_date",
            name="uq_event_identity",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "host_org_unit_id"],
            ["org_unit.tenant_id", "org_unit.id"],
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "time_precision IN ('exact','date_only','unresolved')",
            name="ck_event_time_precision",
        ),
        # Each precision admits exactly one shape of the other three columns.
        # Without this the table would hold an 'unresolved' row carrying a
        # starts_at — a fabricated instant wearing an honest label, which is
        # the defect ADR-0010 exists to close rather than a lesser form of it.
        sa.CheckConstraint(
            "(time_precision = 'exact' AND starts_at IS NOT NULL "
            "AND on_date IS NULL AND time_zone IS NOT NULL) "
            "OR (time_precision = 'date_only' AND starts_at IS NULL "
            "AND on_date IS NOT NULL AND time_zone IS NOT NULL) "
            "OR (time_precision = 'unresolved' AND starts_at IS NULL "
            "AND on_date IS NULL AND time_zone IS NULL)",
            name="ck_event_temporal_shape",
        ),
        # An event has an identity key if and only if its date resolved.
        sa.CheckConstraint(
            "(time_precision = 'unresolved') = (resolved_date IS NULL)",
            name="ck_event_identity_iff_resolved",
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
        # ADR-0010 rule 2 and ADR-0012's quarantine rule, as one state-machine
        # constraint. See the module docstring.
        sa.CheckConstraint(
            "publication_status = 'unpublished' "
            "OR (time_precision <> 'unresolved' AND quarantined_tag_count = 0)",
            name="ck_event_publishable",
        ),
        sa.CheckConstraint(
            "origin IN ('coordinator_entry','extraction')",
            name="ck_event_origin",
        ),
        # Three independent biconditionals, ANDed rather than chained — 0013's
        # docstring explains why a chained three-way `=` would not say what it
        # looks like it says.
        sa.CheckConstraint(
            "(origin = 'extraction') = (source_url IS NOT NULL) "
            "AND (source_url IS NULL) = (fetched_at IS NULL) "
            "AND (fetched_at IS NULL) = (extractor_version IS NULL)",
            name="ck_event_provenance_evidence",
        ),
    )

    # The listing access path a coordinator surface will read: one unit's
    # events within one tenant. Declared now, with the table, rather than left
    # for the card that adds the route — an index is cheap and a sequential
    # scan discovered later is not.
    op.create_index("ix_event_host_unit", "event", ["tenant_id", "host_org_unit_id"])

    op.create_table(
        "event_tag",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("event_id", postgresql.UUID(as_uuid=True), nullable=False),
        # 'mapped' or 'quarantined' — the two arms of
        # smartmatch_domain.events.TagResolution.
        sa.Column("resolution", sa.Text, nullable=False),
        # MappedTag.term. NULL for a quarantined row, which is the point: a
        # query selecting terms cannot pick up a quarantined value by
        # forgetting a filter, because there is no value in the column.
        sa.Column("term", sa.Text, nullable=True),
        # QuarantinedTag.raw_value — "the extracted text exactly as received,
        # unnormalized", because a reviewer deciding whether to add this to the
        # vocabulary needs to see what was on the page, casing and all.
        sa.Column("raw_value", sa.Text, nullable=True),
        # Stamped on both arms. TagVocabulary is frozen and every version is a
        # reviewed code diff (G3 §6.3), so a stored tag stays interpretable
        # against the vocabulary that actually evaluated it — retiring a term
        # never means rewriting history.
        sa.Column("vocabulary_version", sa.Text, nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("id", name="event_tag_pkey"),
        # CASCADE: a tag cannot outlive the event it describes, the same
        # relationship review_item has to import_batch (0008).
        sa.ForeignKeyConstraint(
            ["tenant_id", "event_id"],
            ["event.tenant_id", "event.id"],
            ondelete="CASCADE",
        ),
        # Two natural keys rather than one, because the two arms key on
        # different columns and PostgreSQL's NULLs-are-distinct rule keeps each
        # from constraining the other: a quarantined row has term IS NULL and
        # never collides in the first, a mapped row has raw_value IS NULL and
        # never collides in the second. Both exist so that re-resolving the
        # same extraction is idempotent under ON CONFLICT rather than a
        # duplicate row or a raised error.
        sa.UniqueConstraint("event_id", "term", name="uq_event_tag_term"),
        sa.UniqueConstraint("event_id", "raw_value", name="uq_event_tag_raw_value"),
        sa.CheckConstraint(
            "resolution IN ('mapped','quarantined')",
            name="ck_event_tag_resolution",
        ),
        # The database half of "QuarantinedTag has no term field".
        sa.CheckConstraint(
            "(resolution = 'mapped') = (term IS NOT NULL) "
            "AND (resolution = 'quarantined') = (raw_value IS NOT NULL)",
            name="ck_event_tag_resolution_shape",
        ),
    )

    op.create_table(
        "discovery_review_item",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        # A5-shaped, so a review queue can be read per unit the way every
        # other coordinator surface is scoped.
        sa.Column("owning_unit_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("event_id", postgresql.UUID(as_uuid=True), nullable=False),
        # Why this entry is in the queue. 'unmapped_tag' is ADR-0012's
        # quarantine; 'unresolved_time' is ADR-0010's; 'first_seen_event' is
        # G3 §5's "every first-seen event requires human approval".
        sa.Column("kind", sa.Text, nullable=False),
        # The quarantined tag text, for an 'unmapped_tag' entry only.
        sa.Column("raw_value", sa.Text, nullable=True),
        sa.Column("vocabulary_version", sa.Text, nullable=True),
        sa.Column("status", sa.Text, nullable=False, server_default="pending"),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("decided_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("id", name="discovery_review_item_pkey"),
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
        # RESTRICT, as review_item.decided_by is (0013): deleting the account
        # behind a recorded decision must not silently turn a cited decision
        # back into an uncited one.
        sa.ForeignKeyConstraint(
            ["tenant_id", "decided_by"],
            ["user_account.tenant_id", "user_account.id"],
            ondelete="RESTRICT",
        ),
        # One queue entry per (event, quarantined value), so escalating the
        # same unmapped tag twice is idempotent. NULLs-are-distinct means the
        # non-tag kinds are not constrained by this.
        sa.UniqueConstraint("event_id", "raw_value", name="uq_discovery_review_item_event_value"),
        sa.CheckConstraint(
            "kind IN ('unmapped_tag','unresolved_time','first_seen_event')",
            name="ck_discovery_review_item_kind",
        ),
        sa.CheckConstraint(
            "status IN ('pending','accepted','rejected')",
            name="ck_discovery_review_item_status",
        ),
        # review_item's own decision biconditional (0013), unchanged: a
        # decision that names nobody and no time is the fabricated-field
        # defect.
        sa.CheckConstraint(
            "(status = 'pending') = (decided_at IS NULL) "
            "AND (decided_at IS NULL) = (decided_by IS NULL)",
            name="ck_discovery_review_item_decision_evidence",
        ),
        # A tag entry carries the value and the vocabulary version it failed
        # against; a non-tag entry carries neither.
        sa.CheckConstraint(
            "(kind = 'unmapped_tag') = (raw_value IS NOT NULL) "
            "AND (raw_value IS NULL) = (vocabulary_version IS NULL)",
            name="ck_discovery_review_item_tag_evidence",
        ),
    )

    op.create_index(
        "ix_discovery_review_item_pending",
        "discovery_review_item",
        ["tenant_id", "owning_unit_id", "status"],
    )

    # Card S5f. Unnamed, as every foreign key in this schema is — nothing in
    # the codebase refers to one by name, so PostgreSQL's generated
    # attendance_record_tenant_id_event_id_fkey is the name.
    op.create_foreign_key(
        None,
        "attendance_record",
        "event",
        ["tenant_id", "event_id"],
        ["tenant_id", "id"],
        ondelete="RESTRICT",
    )


def downgrade() -> None:
    """Drop the foreign key, then the three tables.

    A development tool, not a production rollback path (v1.1 §4.2). The
    foreign key goes first because ``attendance_record`` outlives ``event``;
    the two child tables go before their parent, and their indexes go with
    them.
    """
    op.drop_constraint(
        "attendance_record_tenant_id_event_id_fkey",
        "attendance_record",
        type_="foreignkey",
    )
    op.drop_table("discovery_review_item")
    op.drop_table("event_tag")
    op.drop_table("event")
