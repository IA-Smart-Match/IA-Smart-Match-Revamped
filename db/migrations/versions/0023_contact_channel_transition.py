"""``contact_channel_transition`` — the audit trail behind every consent move (OQ-004).

Revision ID: 0022_contact_transition
Revises: 0021_outreach_schema
Create Date: 2026-09-04

Migration ``0021`` gave ``contact_channel`` a ``contact_state`` column and the
constraint that keeps an unapproved source out of ``active_candidate``. What it
did not give it is a **history**: the column says where a contact is now, and
nothing said how it got there, who moved it, or on what evidence.

That gap is the operational half of OQ-004. A row in ``contact_channel``
asserts that a named person agreed to be contacted; an assertion of that kind
is worth exactly as much as the record of who made it. "Show me the evidence
that this address consented" is a question an auditor, a data-protection
officer, or a complaining recipient will ask, and a mutable state column cannot
answer it — by the time anyone asks, the column holds the answer to a different
question.

So every lifecycle move writes a row here, including the first one: registering
a contact is a transition from nothing to its initial state, recorded with
``from_state IS NULL`` rather than left implicit. A trail with a hole at the
beginning is a trail that cannot say where a contact started.

Why the trail is append-only, enforced by a trigger
----------------------------------------------------
``0021``'s argument for ``delivery_event`` applies here unchanged and is the
reason the same shape is used: an audit trail whose rows can be edited is not
an audit trail, it is a second mutable copy of the current state. The trigger
refuses ``UPDATE`` outright and says why. **DELETE is not blocked**, for
``0021``'s reason exactly: retention is a separate decision, and a table
nothing can delete from makes its tenant undeletable — which the teardown path
in ``tests/integration/conftest.py`` depends on.

Why the constraints are duplicated from ``consent.py``
-------------------------------------------------------
``ck_contact_channel_transition_consented_source`` restates the rule
``smartmatch_domain.consent.assert_transition`` enforces: a move to
``consented`` must name an approved source. That is the same deliberate
duplication ``ck_contact_channel_sendable_consent`` already makes, for the same
reason — the domain check stops application code and this one stops a
hand-written INSERT in a psql session. What is **not** duplicated is the
transition graph itself: the legal edges live in ``STATE_TRANSITIONS`` and
nowhere else, because a graph transcribed into SQL is a graph that can disagree
with the one the application reads, and the disagreement would be invisible
until a legal move started failing in production.

The trail therefore records the moves that happened; it does not decide which
moves are legal. That decision has one home.

Why ``actor_user_id`` is ``NOT NULL``
---------------------------------------
There is no such thing as a lifecycle move nobody made. Every transition
reaches this table from a route that ran under an authenticated principal, and
a nullable actor column would be a place for a future background job to record
a consent decision with no name behind it — which is precisely the assertion
OQ-004 says a machine is not in a position to make.

Expand only
------------
One new table, one index, one trigger function and its trigger. Nothing is
dropped, renamed, or backfilled. **No backfill of existing contacts**, and the
absence is deliberate: a synthesised "transitioned to its current state at some
point, by nobody" row would be a fabricated audit entry, which is worse than an
empty history that is honestly empty. Contacts registered before this revision
have no trail, and that is the true statement about them.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0022_contact_transition"
down_revision = "0021_outreach_schema"
branch_labels = None
depends_on = None


#: Transcribed from ``smartmatch_domain.consent.ContactState``, spelled out
#: here rather than imported for ``0021``'s reason: a migration describes the
#: database as of the moment it ran, and an import would let a later edit to
#: the domain silently change what this historical revision meant.
_CONTACT_STATES = (
    "discovered",
    "corroborated",
    "reviewed",
    "relationship_recorded",
    "rejected",
    "consented",
    "active_candidate",
    "stale",
)

_CONSENT_SOURCES = (
    "self_service",
    "authenticated",
    "in_person",
    "institutional_relationship",
    "scraped",
    "purchased",
    "inferred",
)

_APPROVED_CONSENT_SOURCES = (
    "self_service",
    "authenticated",
    "in_person",
    "institutional_relationship",
)


def _quoted(values: tuple[str, ...]) -> str:
    """Render a vocabulary as a SQL ``IN`` list."""
    return ", ".join(f"'{value}'" for value in values)


def upgrade() -> None:
    """Create the transition trail, its index, and the append-only trigger."""
    op.create_table(
        "contact_channel_transition",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("contact_channel_id", postgresql.UUID(as_uuid=True), nullable=False),
        # NULL only for the registration row. A contact's first appearance is a
        # move from nothing to its initial state, and recording it as a real
        # row is what makes the trail complete rather than complete-after-the-
        # first-edit.
        sa.Column("from_state", sa.Text, nullable=True),
        sa.Column("to_state", sa.Text, nullable=False),
        # The source in force *after* this move, copied from the contact rather
        # than referenced, so a later correction to the contact does not rewrite
        # what an earlier transition was made on.
        sa.Column("consent_source", sa.Text, nullable=True),
        # Free text naming how the consent was captured at this moment — a form
        # submission id, a coordinator's note, the institutional agreement's
        # reference. The same field as `contact_channel.consent_evidence`, and
        # snapshotted here for the reason the source above is.
        sa.Column("consent_evidence", sa.Text, nullable=True),
        # Why the move was made, in the actor's own words. Nullable: most moves
        # need no explanation beyond the states they name, and a required field
        # nobody has anything to put in becomes a field everybody types "n/a"
        # into, which is a fabricated record with extra steps.
        sa.Column("reason", sa.Text, nullable=True),
        # NOT NULL. See the module docstring: there is no lifecycle move nobody
        # made, and a nullable actor is where an unattributed consent decision
        # would eventually be written.
        sa.Column("actor_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "recorded_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("id", name="contact_channel_transition_pkey"),
        # RESTRICT, as `outreach_draft`'s reference to the same table is:
        # deleting a contact out from under its consent history would leave the
        # history unreadable and the deletion unexplained.
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
            f"from_state IS NULL OR from_state IN ({_quoted(_CONTACT_STATES)})",
            name="ck_contact_channel_transition_from_state",
        ),
        sa.CheckConstraint(
            f"to_state IN ({_quoted(_CONTACT_STATES)})",
            name="ck_contact_channel_transition_to_state",
        ),
        # A move to itself is not a move. Recording one would put a row in the
        # trail that describes no change, which is the audit-trail equivalent of
        # a log line that says "something happened".
        sa.CheckConstraint(
            "from_state IS NULL OR from_state <> to_state",
            name="ck_contact_channel_transition_moves",
        ),
        sa.CheckConstraint(
            f"consent_source IS NULL OR consent_source IN ({_quoted(_CONSENT_SOURCES)})",
            name="ck_contact_channel_transition_consent_source",
        ),
        # The rule this table shares with `ck_contact_channel_sendable_consent`,
        # stated about the *move* rather than about the resulting row: arriving
        # at `consented` requires naming an approved source for it. Research
        # evidence — scraped, purchased, inferred — can be recorded and reviewed
        # and rejected; it can never be the thing a consent transition rests on.
        #
        # `consent_source IS NOT NULL` is not redundant with the IN list, for
        # the three-valued-logic reason 0021 records at length: `NULL IN (...)`
        # is NULL, and a CHECK treats NULL as satisfied, so without the explicit
        # null test a consent transition carrying no source at all would pass.
        sa.CheckConstraint(
            "to_state NOT IN ('consented', 'active_candidate') "
            "OR (consent_source IS NOT NULL "
            f"AND consent_source IN ({_quoted(_APPROVED_CONSENT_SOURCES)}))",
            name="ck_contact_channel_transition_consented_source",
        ),
        # NOT NULL accepts the empty string, and an empty reason or evidence
        # string is indistinguishable from a writer that forgot (ADR-0011).
        # Absent is a value here; blank is not.
        sa.CheckConstraint(
            "(reason IS NULL OR length(btrim(reason)) > 0) "
            "AND (consent_evidence IS NULL OR length(btrim(consent_evidence)) > 0)",
            name="ck_contact_channel_transition_text_present",
        ),
    )

    # The access path every reader takes: one contact's history, oldest first.
    # Declared with the table rather than left for a later card, as 0017, 0018
    # and 0021 all do.
    op.create_index(
        "ix_contact_channel_transition_channel",
        "contact_channel_transition",
        ["tenant_id", "contact_channel_id", "occurred_at"],
    )

    op.execute(
        """
        CREATE FUNCTION contact_channel_transition_reject_mutation() RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION
                'contact_channel_transition rows are append-only: a correction '
                'to a contact''s lifecycle is a new transition, never an UPDATE '
                'of the record of an earlier one (migration 0022, OQ-004)'
                USING ERRCODE = 'restrict_violation';
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    op.execute(
        """
        CREATE TRIGGER contact_channel_transition_is_append_only
        BEFORE UPDATE ON contact_channel_transition
        FOR EACH ROW EXECUTE FUNCTION contact_channel_transition_reject_mutation();
        """
    )


def downgrade() -> None:
    """Drop the trigger, its function, and the table, in that order.

    The trigger and the function go first for ``0018``'s and ``0021``'s reason:
    dropping the table first takes the trigger with it and leaves the function
    behind holding a name a later revision could not reuse without noticing.
    """
    op.execute(
        "DROP TRIGGER IF EXISTS contact_channel_transition_is_append_only "
        "ON contact_channel_transition"
    )
    op.execute("DROP FUNCTION IF EXISTS contact_channel_transition_reject_mutation()")
    op.drop_table("contact_channel_transition")
