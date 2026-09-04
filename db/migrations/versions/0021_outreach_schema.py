"""Outreach storage — contacts, drafts, sends, delivery events, suppressions (card L3).

Revision ID: 0021_outreach_schema
Revises: 0020_pilot_login_credentials
Create Date: 2026-09-04

Plan `docs/plans/2026-09-04-r4-outreach-g4-implementation-plan.md` card L3. Five
tables that between them let the platform answer four questions it currently
cannot answer at all: *who may we write to and on whose say-so*, *what exactly
did we intend to send*, *did a provider take custody of it*, and *who has told
us to stop*.

The through-line for every constraint below is that each of those four is a
claim about a **real person**, and a claim of that kind must be unstorable
unless the evidence for it is stored alongside it. That is why so much here is
a biconditional CHECK rather than two nullable columns and a convention.

Storage plus its writers
-------------------------
Unlike ``0018``, which shipped a table nothing could reach, this revision lands
with the code that writes it: ``smartmatch_persistence.outreach``,
``smartmatch_worker.handlers.handle_outreach_send``, and the routes in
``smartmatch_api.routers.outreach``. The gate that made ``0018`` storage-only
(G1 open at the time) is closed here for G4 — see the plan's authorization
basis — so shipping the table without its writer would have created exactly the
"handler added ahead of its gate" hazard ``default_registry``'s docstring warns
about, in reverse.

Why there is no ``suppressed`` column on ``contact_channel``
-------------------------------------------------------------
The obvious design is a boolean on the contact, set when someone unsubscribes.
It is not used here, because suppression would then live in two places — the
flag and ``suppression_record`` — and the two would be free to disagree. A
disagreement in that particular pair has a direction: the flag says *may send*
and the record says *do not*, and every system that has ever had this bug
resolves it by reading the flag, because the flag is the cheap read.

So there is one place. ``suppression_record`` is authoritative, the repository
joins against it, and a contact's send-eligibility is computed rather than
cached. The cost is a join on the send path, which is a cost worth paying
exactly once per outbound message.

Why ``outreach_send.job_id`` is ``NOT NULL``
----------------------------------------------
The same argument ``match_run.job_id`` makes, and it matters more here. A send
row that could exist without a job would be a send that some route performed
inline, and "the request path never performs a consequential action"
(v1.1 §1.6) would be a convention rather than a property. With the constraint,
a synchronous send is *unstorable*: there is no job to point at, because jobs
are created only by ``commands.submit_command``.

``uq_outreach_send_job`` then makes a re-drive safe — a second execution of the
same command finds the first row instead of writing a second, which is
``MatchRunRepository.record``'s pattern — and ``uq_outreach_send_idempotency``
is the caller-facing half of the same guarantee.

Why ``delivery_event`` is append-only, and enforced by a trigger
------------------------------------------------------------------
v1.1 §1.8: delivery status is a projection over this stream, never a flag. The
reason the stream must be append-only is that its entries are not monotonic. A
provider can report ``delivered`` and then ``complained`` an hour later, and a
status *column* would have to choose which fact to forget. A stream forgets
nothing, and a projection over it can answer both "was it delivered" and "did
they complain" without the two competing for one column.

``0018``'s argument for using a trigger rather than a rule or a REVOKE applies
here unchanged and is not repeated: a rule discards the UPDATE silently, which
is a fake success; a REVOKE binds to a role name this migration does not know.
As there, **DELETE is not blocked** — retention is a separate question, and the
tenant-teardown path in ``tests/integration/conftest.py`` needs it.

Why the unsubscribe token is stored only as a hash
----------------------------------------------------
``outreach_send.unsubscribe_token_hash`` holds SHA-256 of the token, never the
token. The table is therefore not a set of working unsubscribe links: a reader
with database access cannot unsubscribe anybody, and a leaked backup does not
become a way to silence a mailing list on someone else's behalf. The uniqueness
is **global**, not tenant-scoped, and that is deliberate — the unsubscribe POST
is unauthenticated by design (RFC 8058 one-click arrives with no session at
all), so it has no tenant to scope a lookup by and must resolve the token
across the whole table. A 256-bit random token makes that safe; a shorter one
would not, which is why minting is the application's job and not a default here.

Expand only
------------
Five new tables, four indexes, one trigger function and its trigger. Nothing is
dropped, renamed, or backfilled, so this revision is safe to run ahead of the
code that reads it (v1.1 §4.2, ADR-0009), and one transaction covers all of it.
On an empty database there is nothing to migrate; on a populated one there is no
existing row to violate a constraint that applies only to tables this revision
creates. **No seed data**: every row in ``contact_channel`` asserts that a named
person agreed to be contacted, and a migration is not in a position to make that
assertion (OQ-004).
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0021_outreach_schema"
down_revision = "0020_pilot_login_credentials"
branch_labels = None
depends_on = None


#: The contact-confidence lifecycle, transcribed from
#: ``smartmatch_domain.consent.ContactState``. Spelled out here rather than
#: imported: a migration must describe the database as of the moment it ran, and
#: importing an enum would let a later edit to the domain silently change what
#: this historical revision meant.
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

#: Every consent source the domain names, refusable ones included. A scraped
#: address's *provenance* is a fact worth recording — it is how a reviewer knows
#: why a contact exists. What it must never do is authorize a send, and
#: ``ck_contact_channel_sendable_consent`` below is where that is enforced.
_CONSENT_SOURCES = (
    "self_service",
    "authenticated",
    "in_person",
    "institutional_relationship",
    "scraped",
    "purchased",
    "inferred",
)

#: The four that may stand behind an ``active_candidate``. Mirrors
#: ``smartmatch_domain.consent.APPROVED_CONSENT_SOURCES``.
_APPROVED_CONSENT_SOURCES = (
    "self_service",
    "authenticated",
    "in_person",
    "institutional_relationship",
)

#: ``smartmatch_domain.outreach.DeliveryEventType``.
_DELIVERY_EVENT_TYPES = (
    "queued",
    "blocked",
    "accepted",
    "delivered",
    "bounced",
    "complained",
    "unsubscribed",
    "failed",
)


def _quoted(values: tuple[str, ...]) -> str:
    """Render a vocabulary as a SQL ``IN`` list."""
    return ", ".join(f"'{value}'" for value in values)


def upgrade() -> None:
    """Create the five outreach tables, their indexes, and the append-only trigger."""
    # -----------------------------------------------------------------------
    # contact_channel — one address, and the evidence that it may be used
    # -----------------------------------------------------------------------
    op.create_table(
        "contact_channel",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        # A5-shaped, as job.owning_unit_id (0006), event.host_org_unit_id
        # (0017) and match_run.owning_unit_id (0018) are. NOT NULL from the
        # moment it exists: a nullable authorization input is a fail-open shape
        # waiting to be written.
        sa.Column("owning_unit_id", postgresql.UUID(as_uuid=True), nullable=False),
        # No foreign key, for the reason professional_unit_relationship
        # (migration 0012) records at length: no professional table exists in
        # this schema yet. Whichever migration gives professionals a persisted
        # identity should add this constraint alongside that one's.
        sa.Column("professional_id", postgresql.UUID(as_uuid=True), nullable=False),
        # A one-value vocabulary today, and a column rather than an assumption
        # so that adding SMS or postal later is a CHECK change rather than a
        # table. The alternative — no column, "everything here is email" — is
        # the shape that makes the second channel a migration nobody scoped.
        sa.Column("channel_kind", sa.Text, nullable=False),
        sa.Column("address", sa.Text, nullable=False),
        sa.Column("contact_state", sa.Text, nullable=False),
        # Nullable, because most states legitimately have no consent behind
        # them: a `discovered` address is evidence and nothing more. What is
        # not legitimate is `active_candidate` without one, and that pairing is
        # a constraint below rather than a convention.
        sa.Column("consent_source", sa.Text, nullable=True),
        sa.Column("consent_recorded_at", sa.DateTime(timezone=True), nullable=True),
        # Free text naming *how* consent was captured — a form submission id, a
        # coordinator's note, the institutional agreement's reference. Nullable
        # with the source; an auditor asking "show me the evidence" needs
        # somewhere for the answer to live that is not a comment on a ticket.
        sa.Column("consent_evidence", sa.Text, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        # Carried, unlike match_run's deliberate omission: a contact's state
        # genuinely moves through the lifecycle, so mutation is expected here
        # and saying so structurally is honest (pipeline_record's stage columns
        # make the same call for the same reason).
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("id", name="contact_channel_pkey"),
        # What outreach_draft's composite foreign key references.
        sa.UniqueConstraint("tenant_id", "id", name="uq_contact_channel_tenant_id"),
        # One channel per address per tenant. Two rows for one address would be
        # two independent consent states for one person, and a send path
        # reading either would be correct half the time.
        sa.UniqueConstraint(
            "tenant_id", "channel_kind", "address", name="uq_contact_channel_address"
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "owning_unit_id"],
            ["org_unit.tenant_id", "org_unit.id"],
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint("channel_kind IN ('email')", name="ck_contact_channel_kind"),
        sa.CheckConstraint(
            f"contact_state IN ({_quoted(_CONTACT_STATES)})",
            name="ck_contact_channel_state",
        ),
        sa.CheckConstraint(
            f"consent_source IS NULL OR consent_source IN ({_quoted(_CONSENT_SOURCES)})",
            name="ck_contact_channel_consent_source",
        ),
        # **The constraint this table exists for.** A contact in the one state
        # that authorizes a send must name an approved source for it. Research
        # evidence — scraped, purchased, inferred — can be recorded, reviewed,
        # and rejected; it can never arrive at `active_candidate`.
        #
        # This is the same rule as `consent.is_send_eligible`, deliberately
        # duplicated into the database. That is not the "one rule in two
        # places" problem the module docstring warns about elsewhere, because
        # these two enforce it against different threats: the domain check
        # stops application code, and this one stops a hand-written INSERT in a
        # psql session, which no amount of application discipline reaches.
        # `consent_source IS NOT NULL` is not redundant with the IN list, and
        # leaving it out was a real defect caught by
        # `tests/integration/test_outreach_persistence.py`. SQL's three-valued
        # logic makes `NULL IN (...)` evaluate to NULL, `FALSE OR NULL` to NULL,
        # and a CHECK constraint treats NULL as *satisfied* — so without this
        # clause a contact could reach `active_candidate` carrying no consent
        # source whatsoever, which is precisely the row this constraint exists
        # to forbid. The refusable sources were blocked correctly; the absent
        # one was not.
        sa.CheckConstraint(
            "contact_state <> 'active_candidate' "
            "OR (consent_source IS NOT NULL "
            f"AND consent_source IN ({_quoted(_APPROVED_CONSENT_SOURCES)}))",
            name="ck_contact_channel_sendable_consent",
        ),
        # A source without a time is a consent record nobody can date, and a
        # time without a source is a date for a permission nobody can name.
        sa.CheckConstraint(
            "(consent_source IS NULL) = (consent_recorded_at IS NULL)",
            name="ck_contact_channel_consent_dated",
        ),
        # NOT NULL accepts the empty string; an empty address is
        # indistinguishable from a writer that forgot (ADR-0011). The `@` check
        # is a shape assertion, not validation — deliverability is not decidable
        # here and pretending otherwise would be the fabricated-measurement
        # shape in a new place.
        sa.CheckConstraint(
            "length(btrim(address)) > 0 AND position('@' in address) > 1",
            name="ck_contact_channel_address_present",
        ),
    )

    # The access path the send handler and the coordinator list both take: one
    # unit's contacts within one tenant. Declared with the table rather than
    # left for a later card, as 0017 and 0018 both do.
    op.create_index(
        "ix_contact_channel_unit",
        "contact_channel",
        ["tenant_id", "owning_unit_id"],
    )

    # -----------------------------------------------------------------------
    # outreach_draft — the message, and who signed off on this exact text
    # -----------------------------------------------------------------------
    op.create_table(
        "outreach_draft",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("owning_unit_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("contact_channel_id", postgresql.UUID(as_uuid=True), nullable=False),
        # A key of smartmatch_domain.outreach.TEMPLATES. Text rather than a
        # foreign key to a template table: the registry is code, closed, and
        # reviewed in a diff — which is a stronger guarantee than a table an
        # operator can INSERT into, and the whole reason free-form body text is
        # not accepted anywhere in this feature.
        sa.Column("template_id", sa.Text, nullable=False),
        # Copied from the template at composition time, not looked up at send
        # time. A template's review status can change; what was composed did
        # not, and a draft that silently became live-sendable because someone
        # edited a registry entry is a change nobody approved.
        sa.Column("content_status", sa.Text, nullable=False),
        # The rendered text, stored. Not the placeholder values plus a template
        # id: re-rendering at send time would mean the approved text and the
        # sent text are two computations that merely usually agree, and the
        # entire value of pinning an approval to text is that they cannot
        # differ.
        sa.Column("subject", sa.Text, nullable=False),
        sa.Column("body", sa.Text, nullable=False),
        sa.Column("status", sa.Text, nullable=False),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("approved_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        # A correction names its replacement, exactly as match_run.supersedes
        # does in the other direction. Nullable: a draft can be superseded by
        # being abandoned as well as by being replaced.
        sa.Column("superseded_by_draft_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("id", name="outreach_draft_pkey"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_outreach_draft_tenant_id"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "owning_unit_id"],
            ["org_unit.tenant_id", "org_unit.id"],
            ondelete="RESTRICT",
        ),
        # RESTRICT: deleting the contact a draft addresses would leave a stored
        # message whose recipient's consent nothing can be checked against.
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
        # RESTRICT: an approval whose approver had been deleted would read as
        # an approved draft nobody approved.
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
            "status IN ('draft', 'approved', 'superseded')",
            name="ck_outreach_draft_status",
        ),
        sa.CheckConstraint(
            "content_status IN ('synthetic', 'reviewed')",
            name="ck_outreach_draft_content_status",
        ),
        # An approver and a time arrive together or not at all — same shape as
        # contact_channel's consent pairing, and for the same reason.
        sa.CheckConstraint(
            "(approved_by IS NULL) = (approved_at IS NULL)",
            name="ck_outreach_draft_approval_dated",
        ),
        # An `approved` draft names its approver. Stated one-directionally on
        # purpose: a *superseded* draft that was once approved keeps its
        # approval columns, because erasing them would destroy the record of
        # who signed off on text that may already have been sent.
        sa.CheckConstraint(
            "status <> 'approved' OR approved_by IS NOT NULL",
            name="ck_outreach_draft_approved_has_approver",
        ),
        # Only a superseded draft may name a successor, and it may not name
        # itself — the foreign key above is satisfied by a self-reference, and
        # a draft claiming to replace itself is a cycle of length one.
        sa.CheckConstraint(
            "superseded_by_draft_id IS NULL "
            "OR (status = 'superseded' AND superseded_by_draft_id <> id)",
            name="ck_outreach_draft_supersession",
        ),
        sa.CheckConstraint(
            "length(btrim(template_id)) > 0 "
            "AND length(btrim(subject)) > 0 "
            "AND length(btrim(body)) > 0",
            name="ck_outreach_draft_text_present",
        ),
    )

    op.create_index(
        "ix_outreach_draft_unit_created",
        "outreach_draft",
        ["tenant_id", "owning_unit_id", sa.text("created_at DESC")],
    )

    # -----------------------------------------------------------------------
    # outreach_send — one attempt, behind one durable command
    # -----------------------------------------------------------------------
    op.create_table(
        "outreach_send",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("owning_unit_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("draft_id", postgresql.UUID(as_uuid=True), nullable=False),
        # NOT NULL and constrained. See the module docstring: this is what makes
        # "no synchronous send" a property of the schema.
        sa.Column("job_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("idempotency_key", sa.Text, nullable=False),
        # Snapshots, taken at send time. The contact's address can be corrected
        # afterwards, and "who did we actually write to" must not change when it
        # is — an audit that answers with today's address is answering a
        # different question.
        sa.Column("recipient_address", sa.Text, nullable=False),
        sa.Column("from_address", sa.Text, nullable=False),
        # SHA-256 of the unsubscribe token. Never the token. See the module
        # docstring.
        sa.Column("unsubscribe_token_hash", sa.Text, nullable=False),
        # NULL until the attempt concludes. Not a default of 'failed' or
        # 'queued': an attempt in flight has no outcome, and ADR-0011's rule is
        # that unknown is never silently something else.
        sa.Column("disposition", sa.Text, nullable=True),
        sa.Column("provider", sa.Text, nullable=True),
        # NULL until a provider acknowledges. Never '' — an empty message id
        # would be indistinguishable from a writer that forgot, while satisfying
        # a NOT NULL column.
        sa.Column("provider_message_id", sa.Text, nullable=True),
        # Why a blocked or failed send stopped, in the words of the exception
        # that stopped it. Populated only for a non-accepted disposition.
        sa.Column("failure_reason", sa.Text, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("concluded_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name="outreach_send_pkey"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_outreach_send_tenant_id"),
        # The caller-facing idempotency guarantee: the same key never sends
        # twice. Named here because the repository passes it to
        # ON CONFLICT ON CONSTRAINT, which makes the name an interface.
        sa.UniqueConstraint("tenant_id", "idempotency_key", name="uq_outreach_send_idempotency"),
        # The re-drive guarantee. A handler can execute twice for one job — a
        # worker can die after its business write commits and before the
        # executor's terminal transition does — and without this a re-drive
        # would send the message a second time. This is the constraint that
        # makes "at least once delivery of the command" safe.
        sa.UniqueConstraint("tenant_id", "job_id", name="uq_outreach_send_job"),
        # **Globally** unique, not tenant-scoped: the unsubscribe POST is
        # unauthenticated and has no tenant to scope a lookup by. See the module
        # docstring.
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
        # RESTRICT: the job is this send's provenance, and a send whose job had
        # been deleted could not be traced back to the command that asked for it.
        sa.ForeignKeyConstraint(
            ["tenant_id", "job_id"],
            ["job.tenant_id", "job.id"],
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "disposition IS NULL OR disposition IN ('accepted', 'blocked', 'failed')",
            name="ck_outreach_send_disposition",
        ),
        # An outcome and the time it was reached arrive together.
        sa.CheckConstraint(
            "(disposition IS NULL) = (concluded_at IS NULL)",
            name="ck_outreach_send_concluded",
        ),
        # **A provider message id is only ever evidence of acceptance.** This is
        # the constraint that makes "no fake success" structural at the storage
        # layer: a blocked or failed send cannot carry an id that a reader — or
        # a UI — would take for a receipt.
        sa.CheckConstraint(
            "provider_message_id IS NULL OR disposition = 'accepted'",
            name="ck_outreach_send_message_id_means_accepted",
        ),
        # And an acceptance names both the provider and its id. An accepted send
        # with neither would be this system asserting a delivery it cannot
        # substantiate.
        sa.CheckConstraint(
            "disposition <> 'accepted' "
            "OR (provider IS NOT NULL AND provider_message_id IS NOT NULL)",
            name="ck_outreach_send_accepted_has_provider",
        ),
        # A refusal says why. A blocked send with no reason is a refusal nobody
        # can review, which is the state the delivery stream's `blocked` event
        # exists to prevent in the first place.
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

    op.create_index(
        "ix_outreach_send_draft",
        "outreach_send",
        ["tenant_id", "draft_id"],
    )

    # -----------------------------------------------------------------------
    # delivery_event — the append-only stream a status is projected from
    # -----------------------------------------------------------------------
    op.create_table(
        "delivery_event",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("send_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("event_type", sa.Text, nullable=False),
        # When the event *happened*, as the provider reports it, and when we
        # *learned* of it. Two columns because they genuinely differ — a bounce
        # webhook can arrive hours late — and collapsing them would make the
        # stream's ordering a claim about our own network rather than about the
        # message.
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "recorded_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        # The provider's own id for this event, when it has one. NULL for events
        # this platform wrote itself (`queued`, `blocked`), which is what the
        # uniqueness constraint below relies on: PostgreSQL treats NULLs as
        # distinct in a unique index, so our own events never collide while a
        # replayed provider webhook does.
        sa.Column("provider_event_id", sa.Text, nullable=True),
        # The event's own payload — a bounce code, a refusal reason. JSONB
        # rather than columns because the shape is the provider's, and inventing
        # columns for it would be this schema asserting a structure it does not
        # control.
        sa.Column("detail", postgresql.JSONB, nullable=True),
        sa.PrimaryKeyConstraint("id", name="delivery_event_pkey"),
        # A webhook delivered twice must not become two bounces. See the column
        # comment for why NULL provider ids do not collide under this.
        sa.UniqueConstraint(
            "tenant_id",
            "send_id",
            "provider_event_id",
            name="uq_delivery_event_provider_event",
        ),
        # RESTRICT: an event whose send had been deleted is a fact about
        # nothing.
        sa.ForeignKeyConstraint(
            ["tenant_id", "send_id"],
            ["outreach_send.tenant_id", "outreach_send.id"],
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            f"event_type IN ({_quoted(_DELIVERY_EVENT_TYPES)})",
            name="ck_delivery_event_type",
        ),
        sa.CheckConstraint(
            "detail IS NULL OR jsonb_typeof(detail) = 'object'",
            name="ck_delivery_event_detail_object",
        ),
    )

    # The projection's access path: one send's events, oldest first.
    op.create_index(
        "ix_delivery_event_send",
        "delivery_event",
        ["tenant_id", "send_id", "occurred_at"],
    )

    # -----------------------------------------------------------------------
    # suppression_record — the single authoritative "do not contact"
    # -----------------------------------------------------------------------
    op.create_table(
        "suppression_record",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("address", sa.Text, nullable=False),
        # By address rather than by contact_channel_id, deliberately. A person
        # who unsubscribes is telling us to stop writing to *them*, not to stop
        # using one row; if the same address were later re-added as a new
        # contact under a different unit, a channel-scoped suppression would
        # silently not apply to it. Suppression outlives the record that
        # provoked it.
        sa.Column("suppressed_at", sa.DateTime(timezone=True), nullable=False),
        # How we learned. A closed vocabulary because each member has different
        # consequences: a `complaint` is a deliverability event a provider will
        # also have recorded, while a `coordinator` entry is a human decision
        # with a name behind it.
        sa.Column("source", sa.Text, nullable=False),
        # Which send's unsubscribe link was used, when one was. NULL for a
        # coordinator entry or a bounce. No foreign key to outreach_send: a
        # suppression must survive the deletion of the message that caused it,
        # and a RESTRICT here would make that message undeletable instead.
        sa.Column("origin_send_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("id", name="suppression_record_pkey"),
        # One suppression per address per tenant. A second is not a second
        # instruction; it is the same instruction repeated, and the repository
        # relies on this constraint to make a repeated unsubscribe idempotent
        # rather than an error the recipient would see.
        sa.UniqueConstraint("tenant_id", "address", name="uq_suppression_record_address"),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenant.id"],
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "source IN ('unsubscribe_link', 'one_click', 'coordinator', 'bounce', 'complaint')",
            name="ck_suppression_record_source",
        ),
        sa.CheckConstraint(
            "length(btrim(address)) > 0",
            name="ck_suppression_record_address_present",
        ),
    )

    # -----------------------------------------------------------------------
    # Append-only enforcement for the delivery stream
    # -----------------------------------------------------------------------
    op.execute(
        """
        CREATE FUNCTION delivery_event_reject_mutation() RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION
                'delivery_event rows are append-only: a later fact about a '
                'message is a new event, never an UPDATE of an earlier one '
                '(migration 0021, plan card L3)'
                USING ERRCODE = 'restrict_violation';
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    op.execute(
        """
        CREATE TRIGGER delivery_event_is_append_only
        BEFORE UPDATE ON delivery_event
        FOR EACH ROW EXECUTE FUNCTION delivery_event_reject_mutation();
        """
    )


def downgrade() -> None:
    """Drop everything this revision created, in reverse dependency order.

    The trigger and its function go first, for the reason ``0018``'s downgrade
    records: dropping the table first takes the trigger with it and leaves the
    function behind, holding a name a later revision could not reuse without
    noticing. The tables then go child-first, because every foreign key here is
    ``RESTRICT`` and a parent dropped early would refuse.
    """
    op.execute("DROP TRIGGER IF EXISTS delivery_event_is_append_only ON delivery_event")
    op.execute("DROP FUNCTION IF EXISTS delivery_event_reject_mutation()")

    op.drop_table("suppression_record")
    op.drop_index("ix_delivery_event_send", table_name="delivery_event")
    op.drop_table("delivery_event")
    op.drop_index("ix_outreach_send_draft", table_name="outreach_send")
    op.drop_table("outreach_send")
    op.drop_index("ix_outreach_draft_unit_created", table_name="outreach_draft")
    op.drop_table("outreach_draft")
    op.drop_index("ix_contact_channel_unit", table_name="contact_channel")
    op.drop_table("contact_channel")
