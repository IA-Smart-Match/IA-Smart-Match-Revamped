"""CBA classification storage — one primary per speaker, many per Speaker Request.

Revision ID: 0024_cba_classification
Revises: 0023_contact_transition
Create Date: 2026-09-05

``CBA-TAXONOMY`` (PR #51) released the two closed vocabularies customer §§7–8
supply: twenty NAICS sector groups and ten CBA career role categories. It
deliberately enforced no cardinality — ``docs/product/cba-taxonomies.md`` says
so in as many words: "§7 and §8 give the speaker side one primary value and the
Speaker Request side many. Nothing here blocks either, and nothing here
enforces either — the constraint is ``CBA-DATA-SCHEMA``'s column work." This
revision is that column work.

Two cardinalities, held apart by shape rather than by a rule
-------------------------------------------------------------
Customer §7: "each speaker should have **one primary industry sector**"; §8:
"each speaker should normally have **one primary role category**"; and both
sections' event-side paragraphs: "a Speaker Request may target **multiple**
… Do not restrict an event request to one."

So the speaker side gets **two columns on a table keyed by
``(tenant_id, professional_id)``** and the request side gets **a child table**.
The asymmetry is the point. A second primary industry for a speaker is not
refused by a CHECK somebody could later write an exception into; it has
nowhere to be written, because the key admits one row per professional and the
row holds one code. And a request targeting three industries needs no wider
column, for the reason ``professional_unit_relationship``'s docstring already
gives about ``board_role``: multiplicity is represented by more than one row,
not by an array.

**No array columns**, and that is a decision rather than an omission. An array
of sector codes could not carry a foreign key, could not be constrained per
element without a hand-written ``CHECK`` over ``unnest``, could not be indexed
for the "which requests target Finance" query the matcher will ask, and could
not hold the version token each stored value needs. The card's own
anti-pattern list names arrays without constraints; the honest reading is that
a constrained array here would be a child table with worse ergonomics.

Why the taxonomy codes are transcribed into CHECK constraints
---------------------------------------------------------------
``docs/product/cba-taxonomies.md`` says the domain module is the only copy and
names "a migration literal" among the places a second copy must not appear.
That instruction and this constraint cannot both be satisfied literally: a
``CHECK`` cannot import Python, and a column with no ``CHECK`` is a free-text
column, which the card forbids outright ("classification values must be
constrained to the merged taxonomy modules, not free text").

The resolution is the one migration ``0023`` already applies to
``smartmatch_domain.consent``'s states, for the reason it states: "a migration
describes the database as of the moment it ran, and an import would let a later
edit to the domain silently change what this historical revision meant." The
codes below are therefore transcribed, deliberately, **and the divergence that
transcription risks is caught behaviourally rather than left to discipline**:
``tests/integration/test_cba_classification_schema.py`` parametrizes over
``SECTOR_CODES`` and ``ROLE_CATEGORY_CODES`` *from the domain modules* and
requires every released code to be storable. A twenty-first sector added to the
taxonomy without a migration fails there, at the point it is added, rather than
in a Speaker Connector's correction screen months later.

What the meaning-carrying half is: the sector **names** are not copied here.
The database stores codes; ``naics_sectors`` alone says what ``31-33`` means.
That is the duplication the taxonomy document is actually guarding against.

CBA roles are not ADR-0012 event tags
---------------------------------------
``event_tag`` holds ADR-0012's twelve terms — what kind of event this is
(``hackathon``, ``career panel``) and what function a speaker performs at it
(``panelist``, ``judge``). Nothing in this revision touches that table, extends
that vocabulary, or reuses it. ``speaker_request_classification`` is a separate
table with its own ``taxonomy_version`` column precisely so a stored row names
which of the three vocabularies evaluated it, and the ``CHECK`` on ``code``
refuses all twelve ADR-0012 terms under both kinds. The tests assert that
directly rather than trusting the lists not to overlap by accident.

Event identity is untouched
-----------------------------
``uq_event_identity`` is still ``(tenant_id, host_org_unit_id,
normalized_title, resolved_date)``. Location is added *beside* the key and
never inside it: two Speaker Requests differing only in city are the same
event, and widening the key would silently un-deduplicate the discovery path
ADR-0012 exists to make deterministic.

``is_virtual`` is ``NOT NULL DEFAULT false``, so no backfill decision is
needed and none is invented. Every event that existed before this revision was
entered or extracted with a place attached; ``false`` is the true statement
about them, and a nullable column would create a third "nobody said" state
that §11's redistribution rule has no branch for.

``speaker_profile.professional_id`` **does** carry a foreign key
-----------------------------------------------------------------
``professional_unit_relationship`` (0012) and ``contact_channel`` (0021) both
leave their own ``professional_id`` unconstrained, each saying the same thing:
"no professional table exists yet … whichever migration gives professionals a
persisted identity should add this foreign key alongside it." Since 0012 was
written, one has: the synthetic pilot authorization's **Choice A** —
"import creates or links ``user_account`` per professional" — makes
``user_account`` the persisted professional identity, ``professionals.py`` is
its writer, and ``pipeline_record.subject_id`` already references it under
``RESTRICT``.

So this table does what 0012 asked a later migration to do, for its own
column: a composite ``(tenant_id, professional_id) -> user_account(tenant_id,
id)`` key under ``ON DELETE RESTRICT``. Composite, so a profile in one tenant
cannot classify a person in another; ``RESTRICT``, because a classification
that outlived its subject would be an assertion about nobody, and one that
vanished with them would delete a Speaker Connector's reviewed judgment as a
side effect. **The two older columns are deliberately left alone** — retrofitting
their foreign keys is a data-bearing change to tables that already hold rows,
which is its own migration and its own backfill decision, not a rider on this
one. See OQ-CBA-009.

Expand only
-------------
Two new tables and three new nullable-or-defaulted columns on ``event``.
Nothing is dropped, renamed, or backfilled, so this is safe under a rolling
deploy per v1.1 §4.2: the old release does not know the tables exist and writes
``event`` rows that the new defaults fill in. Per ADR-0009 it runs in its own
transaction (``transaction_per_migration=True`` in ``db/migrations/env.py``).

Open questions this revision deliberately does not answer
-----------------------------------------------------------
Recorded here because the card requires a missing audit requirement to become
an OQ *before* DDL rather than a guessed column after it.

* **OQ-CBA-008 — classification provenance and correction history.** §19's
  flow infers a classification and then has a Speaker Connector correct it, and
  §7/§8 both require the correction to be possible. This revision stores the
  *current* value only, the same current-state-only treatment P9 Gate A §2
  gives ``board_role``. Whether the pilot must also record who classified a
  speaker, whether the value was inferred or human-assigned, and what the
  previous value was, is unanswered — nobody has stated an audit requirement
  for it. Inventing an ``industry_source`` vocabulary here would be settling
  that question by writing a column, which ``0012``'s refusal to invent a
  ``board_role`` vocabulary is the local precedent against. If the answer turns
  out to be yes, the shape is ``contact_channel_transition``'s and it is a
  later revision.
* **OQ-CBA-009 — retrofitting the two older ``professional_id`` columns.**
  See above.
* **OQ-CBA-010 — where a *quarantined* classification lives.** Both taxonomy
  modules return a ``Quarantined…`` value carrying the reviewer's original text
  for a code they do not recognize, and this schema has nowhere to put one: the
  columns store released codes and refuse everything else. Import quarantine is
  ``review_item``'s and ``discovery_review_item``'s job today, and whether a CBA
  classification quarantine belongs there or beside the profile is
  ``CBA-IMPORT-CLASSIFY``'s question, not this card's.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0024_cba_classification"
down_revision = "0023_contact_transition"
branch_labels = None
depends_on = None


#: Transcribed from ``smartmatch_domain.naics_sectors.SECTOR_CODES``
#: (taxonomy version ``cba-naics-2026-09-04``), spelled out here rather than
#: imported for ``0023``'s reason — see the module docstring. The three
#: hyphenated ranges are customer §7's own and are why the column is ``TEXT``.
#: ``tests/integration/test_cba_classification_schema.py`` binds this list back
#: to the domain module behaviourally.
_SECTOR_CODES = (
    "11",
    "21",
    "22",
    "23",
    "31-33",
    "42",
    "44-45",
    "48-49",
    "51",
    "52",
    "53",
    "54",
    "55",
    "56",
    "61",
    "62",
    "71",
    "72",
    "81",
    "92",
)

#: Transcribed from ``smartmatch_domain.cba_role_categories.ROLE_CATEGORY_CODES``
#: (taxonomy version ``cba-roles-2026-09-04``). Storage keys, not §8's display
#: names: ``Management & Strategy`` is what a person reads and
#: ``management_strategy`` is what a row holds, so a display rename does not
#: renumber stored rows.
_ROLE_CATEGORY_CODES = (
    "accounting",
    "finance",
    "marketing",
    "management_strategy",
    "human_resources",
    "operations_supply_chain",
    "information_systems_analytics",
    "international_business",
    "entrepreneurship_founder",
    "sales_business_development",
)

#: The two axes customer §§7–8 name. No third is approved, and ``kind`` is what
#: decides which vocabulary a ``speaker_request_classification`` row is held to.
_CLASSIFICATION_KINDS = ("industry", "role")


def _quoted(values: tuple[str, ...]) -> str:
    """Render a vocabulary as a SQL ``IN`` list. ``0023``'s helper, same job."""
    return ", ".join(f"'{value}'" for value in values)


def upgrade() -> None:
    """Add the speaker profile, the request classifications, and event location."""
    op.create_table(
        "speaker_profile",
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        # The professional this profile classifies. See the module docstring
        # for why this column, unlike its two older namesakes, carries a
        # foreign key.
        sa.Column("professional_id", postgresql.UUID(as_uuid=True), nullable=False),
        # A5-shaped, as `contact_channel.owning_unit_id` and
        # `match_run.owning_unit_id` are: the unit whose Speaker Connector is
        # accountable for this classification.
        sa.Column("owning_unit_id", postgresql.UUID(as_uuid=True), nullable=False),
        # Customer §7, one column and not a set. NULL is a real state and not a
        # placeholder: §19 imports a contact first and classifies it after, so
        # an unclassified speaker must be storable — the same argument ADR-0010
        # makes for an unresolved event date.
        sa.Column("primary_industry_code", sa.Text, nullable=True),
        # Which released taxonomy the code above was resolved against. The
        # taxonomy modules stamp this onto every `ClassifiedSector` for the
        # reason it is stored here: a code stays interpretable after a revision
        # only if the row says which table evaluated it.
        sa.Column("industry_taxonomy_version", sa.Text, nullable=True),
        # Customer §8, the same shape for the same reason.
        sa.Column("primary_role_code", sa.Text, nullable=True),
        sa.Column("role_taxonomy_version", sa.Text, nullable=True),
        # §18's "Topic/interests/expertise text" and "optional prior talk
        # information", stored as the free text they are. §9 compares them
        # semantically against an event description; nothing here parses them.
        sa.Column("topic_text", sa.Text, nullable=True),
        sa.Column("prior_talk", sa.Text, nullable=True),
        # §10: "City or ZIP code is sufficient for this phase." Two independent
        # nullable columns, because "or" is what the requirement says — neither
        # is derived from the other and neither is required.
        sa.Column("location_city", sa.Text, nullable=True),
        sa.Column("location_postal_code", sa.Text, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        # §§7-8 require a Speaker Connector to be able to correct an assigned
        # classification, and a correction updates this row rather than
        # superseding it — P9 Gate A §2's current-state treatment of
        # `board_role`, and the reason `updated_at` belongs here while
        # `point_ledger_entry` deliberately has none.
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        # THE cardinality constraint. Customer §7's "one primary industry
        # sector" per speaker is this key: one row per professional, one code
        # in it, and a second primary value with nowhere to go.
        sa.PrimaryKeyConstraint(
            "tenant_id",
            "professional_id",
            name="speaker_profile_pkey",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "professional_id"],
            ["user_account.tenant_id", "user_account.id"],
            ondelete="RESTRICT",
        ),
        # RESTRICT: reorganizing a unit must not silently delete the
        # classifications recorded under it, the same intent every other
        # `owning_unit_id` in this schema carries.
        sa.ForeignKeyConstraint(
            ["tenant_id", "owning_unit_id"],
            ["org_unit.tenant_id", "org_unit.id"],
            ondelete="RESTRICT",
        ),
        # The closed vocabulary, in the database and not only in Python. The
        # `IS NULL` arm is what makes the classification optional; without the
        # explicit test the column would still accept NULL (a CHECK treats an
        # unknown as satisfied), but stating it keeps the two readings from
        # depending on three-valued logic that 0021 and 0023 both had to
        # explain at length.
        sa.CheckConstraint(
            f"primary_industry_code IS NULL OR primary_industry_code IN ({_quoted(_SECTOR_CODES)})",
            name="ck_speaker_profile_industry_code",
        ),
        # A code and its version travel together in both directions. A code
        # with no version is uninterpretable after the next revision; a version
        # with no code is a claim about nothing.
        sa.CheckConstraint(
            "(primary_industry_code IS NULL) = (industry_taxonomy_version IS NULL)",
            name="ck_speaker_profile_industry_versioned",
        ),
        sa.CheckConstraint(
            f"primary_role_code IS NULL OR primary_role_code IN ({_quoted(_ROLE_CATEGORY_CODES)})",
            name="ck_speaker_profile_role_code",
        ),
        sa.CheckConstraint(
            "(primary_role_code IS NULL) = (role_taxonomy_version IS NULL)",
            name="ck_speaker_profile_role_versioned",
        ),
        # ADR-0011: absent is a value, blank is a writer that forgot. §9 scores
        # a speaker with no topic information *neutrally* rather than at zero,
        # which is a decision about NULL — an empty string would reach it as
        # text and be scored as though it said something.
        sa.CheckConstraint(
            "(topic_text IS NULL OR length(btrim(topic_text)) > 0) "
            "AND (prior_talk IS NULL OR length(btrim(prior_talk)) > 0) "
            "AND (location_city IS NULL OR length(btrim(location_city)) > 0) "
            "AND (location_postal_code IS NULL OR length(btrim(location_postal_code)) > 0)",
            name="ck_speaker_profile_text_present",
        ),
    )

    # The access path a Speaker Connector's review queue takes: this unit's
    # speakers, and among them the ones still unclassified. Declared with the
    # table rather than left for a later card, as 0017, 0021 and 0023 all do.
    op.create_index(
        "ix_speaker_profile_unit",
        "speaker_profile",
        ["tenant_id", "owning_unit_id"],
    )

    # -----------------------------------------------------------------------
    # The Speaker Request side. A Speaker Request is persisted as an `event`
    # row: customer §4 renames "Volunteer opportunity" to "Speaker Request",
    # and `docs/product/cba-terminology.md` maps that page onto the existing
    # opportunity/event surface. So these columns and this child table hang off
    # `event` rather than creating a parallel entity beside it.
    # -----------------------------------------------------------------------

    # §12: an Event Host must be able to "specify physical vs. virtual".
    # NOT NULL with a server default, so existing rows need no backfill and no
    # fabricated value — see the module docstring.
    op.add_column(
        "event",
        sa.Column(
            "is_virtual",
            sa.Boolean,
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    # §12: "specify event location"; §10: "city or ZIP code is sufficient".
    op.add_column("event", sa.Column("location_city", sa.Text, nullable=True))
    op.add_column("event", sa.Column("location_postal_code", sa.Text, nullable=True))

    # §11: "for virtual events — ignore Proximity entirely". A location stored
    # on a virtual event is a value the scoring rule is required to ignore,
    # which is precisely the shape of a field that gets read by accident two
    # cards later. Refusing it makes "entirely" structural rather than a line
    # in a factor implementation.
    op.create_check_constraint(
        "ck_event_virtual_has_no_location",
        "event",
        "NOT is_virtual OR (location_city IS NULL AND location_postal_code IS NULL)",
    )
    # ADR-0011 again, and load-bearing rather than tidy: a `location_city` of
    # `''` satisfies the NULL test above while the row still claims a place.
    op.create_check_constraint(
        "ck_event_location_present",
        "event",
        "(location_city IS NULL OR length(btrim(location_city)) > 0) "
        "AND (location_postal_code IS NULL OR length(btrim(location_postal_code)) > 0)",
    )

    op.create_table(
        "speaker_request_classification",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("event_id", postgresql.UUID(as_uuid=True), nullable=False),
        # Which of customer §§7-8's two axes this row targets, and therefore
        # which closed vocabulary `code` is held to.
        sa.Column("kind", sa.Text, nullable=False),
        # The stored code. NOT NULL: a targeted classification naming nothing
        # is not a target, and there is no quarantine arm here — a Speaker
        # Request's industries are chosen from a list by a host, not resolved
        # out of a spreadsheet cell. See OQ-CBA-010.
        sa.Column("code", sa.Text, nullable=False),
        # Unconditionally NOT NULL, unlike `speaker_profile`'s pair, because
        # `code` is NOT NULL too: there is no absent case for it to mirror.
        # `event_tag.vocabulary_version` is NOT NULL for the same reason.
        sa.Column("taxonomy_version", sa.Text, nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("id", name="speaker_request_classification_pkey"),
        # CASCADE, as `event_tag`'s reference to the same parent is: a target
        # cannot outlive the request that states it.
        sa.ForeignKeyConstraint(
            ["tenant_id", "event_id"],
            ["event.tenant_id", "event.id"],
            ondelete="CASCADE",
        ),
        # Multi-select is a set, not a bag. A repeated target is a weight
        # counted twice by a matcher with nothing on screen to explain it —
        # `uq_event_tag_term` guards the same thing for the same reason.
        sa.UniqueConstraint(
            "tenant_id",
            "event_id",
            "kind",
            "code",
            name="uq_speaker_request_classification",
        ),
        sa.CheckConstraint(
            f"kind IN ({_quoted(_CLASSIFICATION_KINDS)})",
            name="ck_speaker_request_classification_kind",
        ),
        # `kind` decides which vocabulary applies. Without this conditional,
        # `kind` would be a label the row carries rather than a statement the
        # database holds it to, and an industry target reading 'finance' could
        # sit beside a role target reading '52'. Both branches are exhaustive
        # over `ck_..._kind`'s two values, so no row escapes a vocabulary.
        sa.CheckConstraint(
            f"(kind = 'industry' AND code IN ({_quoted(_SECTOR_CODES)})) "
            f"OR (kind = 'role' AND code IN ({_quoted(_ROLE_CATEGORY_CODES)}))",
            name="ck_speaker_request_classification_code",
        ),
    )

    # The matcher's access path: this request's targets, and a host's read of
    # its own request. `kind` is in the key because every reader wants one axis
    # at a time.
    op.create_index(
        "ix_speaker_request_classification_event",
        "speaker_request_classification",
        ["tenant_id", "event_id", "kind"],
    )


def downgrade() -> None:
    """Drop everything this revision added, children before parents.

    A development tool, not a production rollback path (v1.1 §4.2). The two
    ``event`` CHECK constraints are dropped before their columns for ``0018``'s
    and ``0023``'s reason: dropping the column first takes the constraint with
    it and leaves a name a later revision could not reuse without noticing why.
    Nothing outside this revision references either new table, so both drops
    are unconditional.
    """
    op.drop_index(
        "ix_speaker_request_classification_event",
        table_name="speaker_request_classification",
    )
    op.drop_table("speaker_request_classification")

    op.drop_constraint("ck_event_location_present", "event", type_="check")
    op.drop_constraint("ck_event_virtual_has_no_location", "event", type_="check")
    op.drop_column("event", "location_postal_code")
    op.drop_column("event", "location_city")
    op.drop_column("event", "is_virtual")

    op.drop_index("ix_speaker_profile_unit", table_name="speaker_profile")
    op.drop_table("speaker_profile")
