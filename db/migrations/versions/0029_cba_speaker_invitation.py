"""Speaker invitations: a batch a Connector composed, and what each Speaker said.

Customer §6 steps 7-8 ("send invitations, including batch invitations where
supported" / "track speaker responses/acceptances"), §13, and §14. Two tables,
and every constraint in them exists to stop one specific confusion.

The confusion this revision is mostly about
=============================================
**A mail provider accepting bytes is not a person agreeing to speak.** Those two
facts already had a home for the first — ``outreach_send.disposition``, whose
``accepted`` means a provider took custody — and no home at all for the second.
The obvious cheap thing would have been a status column that carried both, and
it is the one thing this revision must not do: an Event Host who reads a
delivery receipt as an acceptance books a room for nobody.

So the two facts live in two tables and never in one column, and
``ck_cba_invitation_response_status`` enumerates the only three words a Speaker's
answer may take. All three name the invitation — ``accepted_invitation``,
``declined_invitation``, ``awaiting_response`` — so none of them can be spelled
like a disposition or a delivery event.
``smartmatch_domain.cba_invitations.assert_response_vocabulary_is_disjoint_from_delivery``
holds the same property in code, over both enums, which is where it can notice a
value added to either.

Why every named recipient gets a row, including the ones nobody wrote to
=========================================================================
``cba_invitation.status`` has a ``skipped`` value and ``skip_reason`` is required
with it. A batch of twelve names that produced nine invitations stores twelve
rows, not nine, because the three are the ones a Connector has to do something
about — a suppressed address, a contact nobody activated, a person the §13 form
recorded with no channel at all (OQ-CBA-011's ordinary case).

That is also what makes a replayed batch honest. The batch's idempotency key is
unique per unit, so re-submitting one returns the *stored* outcomes rather than
recomputing them, and a recipient who was skipped the first time is still
reported, with the same reason, rather than quietly disappearing from a shorter
list.

Why ``professional_id`` carries no foreign key
================================================
Because ``not_on_roster`` is a storable outcome. A Connector who pastes an id
that names nobody on this unit's §13 roster gets a row saying exactly that, and a
foreign key to ``speaker_profile`` would make the one skip reason that is about
a *mistake* the one skip reason that cannot be recorded. The scoped lookup
happens in the route, which is where a 404 can be worded.

Every other reference is a real composite foreign key on ``(tenant_id, …)``:
``org_unit``, ``match_run``, ``contact_channel``, ``outreach_draft``, ``job``,
``user_account``. All ``RESTRICT``, for 0027's reason — reorganizing a unit or
deleting an account must not silently erase who was invited or who recorded an
answer.

What is deliberately *not* stored
===================================
* **No delivery status.** The invitation holds ``outreach_send_job_id`` and
  nothing else about delivery; ``disposition`` is read from ``outreach_send``
  through that job. A copy here would be a second place the answer lives, and
  the disagreement between two such places always resolves toward the more
  flattering one.
* **No consent snapshot.** Eligibility is recomputed from ``contact_channel``
  and ``suppression_record`` every time it is asked, exactly as 0021 requires,
  so a suppression recorded between the batch and the dispatch is seen by the
  dispatch.
* **No response token.** Only its SHA-256, in ``response_token_hash``, globally
  unique for ``outreach_send.unsubscribe_token_hash``'s reason: possession of
  this database must not confer the ability to answer on somebody's behalf.

Expand-only
=============
Two new tables. Nothing is dropped, renamed, backfilled or widened, and no
existing table is touched — safe under a rolling deploy per v1.1 §4.2: the old
release does not know these tables exist.

Open questions this revision leaves open
==========================================
* **OQ-CBA-040** — whether a Speaker's decline should feed back into matching, so
  a declined candidate is ranked lower next time. Nothing here records it as a
  matching signal, and inventing one would be a scoring change made in DDL.
* **OQ-CBA-041** — whether an invitation should expire. There is no deadline
  column: an unanswered invitation stays ``awaiting_response`` forever, which is
  honest and unhelpful, and what the timeout should be is a product decision.
* **OQ-CBA-044** — whether a Speaker may change an answer they already gave. The
  fail-closed reading is implemented (the first answer stands); no column here
  presumes the other outcome.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0029_cba_speaker_invitation"
down_revision = "0028_classification_provenance"
branch_labels = None
depends_on = None


#: The three states a named recipient can be in. `skipped` is a real outcome
#: rather than an absence — see the module docstring.
_STATUS_IS_KNOWN = "status IN ('pending', 'dispatched', 'skipped')"

#: A skip says why, and only a skip does. Written as an equivalence rather than
#: two implications so neither half can be relaxed without the other.
_SKIP_REASON_IFF_SKIPPED = "(status = 'skipped') = (skip_reason IS NOT NULL)"

#: A recipient who was written to has a channel, a snapshotted address and the
#: draft that was composed for them; one who was skipped has none of the three.
#: The address is snapshotted for `outreach_send.recipient_address`'s reason: a
#: later correction to the channel must not rewrite what an invitation said.
_ADDRESSED_IFF_NOT_SKIPPED = (
    "(status = 'skipped') = "
    "(contact_channel_id IS NULL AND recipient_address IS NULL AND outreach_draft_id IS NULL)"
)

#: Dispatched means a send command exists and when it was submitted is recorded.
#: Note what this does *not* say: nothing about whether a message was delivered.
#: That is `outreach_send.disposition`, reached through the job.
_DISPATCHED_IFF_SUBMITTED = (
    "(status = 'dispatched') = (outreach_send_job_id IS NOT NULL AND dispatched_at IS NOT NULL)"
)

#: The Speaker's own three words. Every one of them names the invitation, so
#: none can collide with a provider disposition ('accepted', 'blocked',
#: 'failed') or a delivery event. This is the load-bearing constraint of the
#: revision; see the module docstring.
_RESPONSE_STATUS_IS_KNOWN = (
    "response_status IN ('awaiting_response', 'accepted_invitation', 'declined_invitation')"
)

#: An answered invitation records when the answer came and how it arrived; an
#: unanswered one records neither. `awaiting_response` is a state, not a missing
#: value, and this is what keeps it from being written as a half-answer.
_ANSWERED_IFF_DATED = (
    "(response_status = 'awaiting_response') = "
    "(response_recorded_at IS NULL AND response_channel IS NULL)"
)

#: How the answer reached us, and it matters: a Connector typing what they were
#: told on the phone is a different evidentiary claim from a Speaker following
#: the link in their own invitation, and a surface that showed them alike would
#: be asserting a directness nobody has.
_RESPONSE_CHANNEL_IS_KNOWN = (
    "response_channel IS NULL OR response_channel IN ('speaker_link', 'connector_recorded')"
)

#: Exactly the connector-recorded answers name the coordinator who recorded them.
#: A `speaker_link` answer has no account behind it — the Speaker is a contact,
#: not a user — and attributing one to whoever happened to be nearby would be
#: inventing a witness.
_ACTOR_IFF_CONNECTOR_RECORDED = (
    "(response_channel = 'connector_recorded') = (response_recorded_by_user_id IS NOT NULL)"
)

#: Nobody was written to, so nobody can have answered. Without this a skipped
#: recipient could carry an acceptance, which would be an answer to a message
#: that was never sent.
_SKIPPED_IS_UNANSWERABLE = (
    "status <> 'skipped' OR "
    "(response_status = 'awaiting_response' AND response_token_hash IS NULL)"
)


def upgrade() -> None:
    """Create the batch table and the invitation table."""
    op.create_table(
        "cba_invitation_batch",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        # A5-shaped: the unit whose Speaker Connector composed this batch and is
        # accountable for every message in it.
        sa.Column("owning_unit_id", postgresql.UUID(as_uuid=True), nullable=False),
        # The caller's Idempotency-Key. Unique per unit, which is what makes a
        # re-submitted batch return the first submission's outcomes instead of
        # inviting everybody a second time.
        sa.Column("idempotency_key", sa.Text, nullable=False),
        # The shortlist this batch came from, when it came from one. Nullable
        # because a Connector may invite people they picked by hand, and a
        # required run id would make the honest case unrepresentable.
        sa.Column("match_run_id", postgresql.UUID(as_uuid=True), nullable=True),
        # Which entry of the closed template registry composed the messages.
        # Stored so a batch stays readable after the registry gains a v2.
        sa.Column("template_id", sa.Text, nullable=False),
        # What the invitation said the event was. `event_date` is Text and is
        # never parsed: it is the date as the Connector wrote it, and it appears
        # in the message verbatim. Storing a timestamp would mean guessing a
        # timezone and a format for a string whose only job is to be read by a
        # human — the ADR-0010 posture on unresolved dates.
        sa.Column("event_name", sa.Text, nullable=False),
        sa.Column("event_date", sa.Text, nullable=False),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("id", name="cba_invitation_batch_pkey"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_cba_invitation_batch_tenant_id"),
        sa.UniqueConstraint(
            "tenant_id",
            "owning_unit_id",
            "idempotency_key",
            name="uq_cba_invitation_batch_key",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "owning_unit_id"],
            ["org_unit.tenant_id", "org_unit.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "match_run_id"],
            ["match_run.tenant_id", "match_run.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "created_by_user_id"],
            ["user_account.tenant_id", "user_account.id"],
            ondelete="RESTRICT",
        ),
    )

    op.create_table(
        "cba_invitation",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("owning_unit_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("batch_id", postgresql.UUID(as_uuid=True), nullable=False),
        # No foreign key, deliberately: `not_on_roster` is a storable outcome and
        # a reference would make the one skip reason about a mistake the one skip
        # reason that cannot be recorded. See the module docstring.
        sa.Column("professional_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.Text, nullable=False),
        sa.Column("skip_reason", sa.Text, nullable=True),
        sa.Column("contact_channel_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("recipient_address", sa.Text, nullable=True),
        sa.Column("outreach_draft_id", postgresql.UUID(as_uuid=True), nullable=True),
        # The send command, not the send. A job exists as soon as the dispatch is
        # accepted; whether a message left is `outreach_send.disposition`, read
        # through this id, and is deliberately not copied here.
        sa.Column("outreach_send_job_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("dispatched_at", sa.DateTime(timezone=True), nullable=True),
        # The Speaker's own answer, in a vocabulary no delivery outcome shares.
        # No server default: an invitation's initial state is written by the
        # insert that creates it, so the value is a decision somebody made rather
        # than one the database supplied.
        sa.Column("response_status", sa.Text, nullable=False),
        sa.Column("response_recorded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("response_channel", sa.Text, nullable=True),
        sa.Column("response_recorded_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        # SHA-256 of the single-use token in the invitation's own link. The token
        # itself is never stored, so a reader of this database cannot answer on
        # anybody's behalf. Globally unique, like `outreach_send`'s, because the
        # public respond route has no tenant to scope by.
        sa.Column("response_token_hash", sa.Text, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("id", name="cba_invitation_pkey"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_cba_invitation_tenant_id"),
        # One outcome per named recipient per batch. This is also the batch's
        # replay guarantee at the row level: a second insert for the same person
        # in the same batch cannot land, so a re-submitted batch cannot double-
        # invite even if a route forgot to check.
        sa.UniqueConstraint(
            "tenant_id",
            "batch_id",
            "professional_id",
            name="uq_cba_invitation_batch_recipient",
        ),
        # One invitation per send command, so a job cannot be claimed by two
        # invitations. PostgreSQL treats NULLs as distinct, so the many
        # un-dispatched rows do not collide.
        sa.UniqueConstraint(
            "tenant_id",
            "outreach_send_job_id",
            name="uq_cba_invitation_send_job",
        ),
        sa.UniqueConstraint("response_token_hash", name="uq_cba_invitation_response_token"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "owning_unit_id"],
            ["org_unit.tenant_id", "org_unit.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "batch_id"],
            ["cba_invitation_batch.tenant_id", "cba_invitation_batch.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "contact_channel_id"],
            ["contact_channel.tenant_id", "contact_channel.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "outreach_draft_id"],
            ["outreach_draft.tenant_id", "outreach_draft.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "outreach_send_job_id"],
            ["job.tenant_id", "job.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "response_recorded_by_user_id"],
            ["user_account.tenant_id", "user_account.id"],
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(_STATUS_IS_KNOWN, name="ck_cba_invitation_status"),
        sa.CheckConstraint(_SKIP_REASON_IFF_SKIPPED, name="ck_cba_invitation_skip_reason"),
        sa.CheckConstraint(_ADDRESSED_IFF_NOT_SKIPPED, name="ck_cba_invitation_addressed"),
        sa.CheckConstraint(_DISPATCHED_IFF_SUBMITTED, name="ck_cba_invitation_dispatched"),
        sa.CheckConstraint(_RESPONSE_STATUS_IS_KNOWN, name="ck_cba_invitation_response_status"),
        sa.CheckConstraint(_ANSWERED_IFF_DATED, name="ck_cba_invitation_response_dated"),
        sa.CheckConstraint(_RESPONSE_CHANNEL_IS_KNOWN, name="ck_cba_invitation_response_channel"),
        sa.CheckConstraint(_ACTOR_IFF_CONNECTOR_RECORDED, name="ck_cba_invitation_response_actor"),
        sa.CheckConstraint(_SKIPPED_IS_UNANSWERABLE, name="ck_cba_invitation_skipped_unanswered"),
    )

    # The read a Connector's tracking screen makes: one batch's invitations,
    # in a stable order. Without it the listing is a scan of every invitation
    # the tenant ever composed.
    op.create_index(
        "ix_cba_invitation_batch",
        "cba_invitation",
        ["tenant_id", "batch_id", "professional_id"],
    )
    # The batch listing's own read: one unit's batches, newest first.
    op.create_index(
        "ix_cba_invitation_batch_unit",
        "cba_invitation_batch",
        ["tenant_id", "owning_unit_id", "created_at"],
    )


def downgrade() -> None:
    """Drop both tables, child first.

    A development tool, not a production rollback path (v1.1 §4.2). Dropping
    these discards every record of who was invited and who agreed to come, and
    the ``outreach_draft`` and ``outreach_send`` rows the invitations pointed at
    survive without them — so the messages remain auditable and the reason they
    were sent does not.
    """
    op.drop_index("ix_cba_invitation_batch_unit", table_name="cba_invitation_batch")
    op.drop_index("ix_cba_invitation_batch", table_name="cba_invitation")
    op.drop_table("cba_invitation")
    op.drop_table("cba_invitation_batch")
