"""An internal record of a meeting a unit holds with the CBA team.

The coordinator portal's Meetings page has, until now, rendered a
``PortalDatasetUnavailable`` placeholder naming the legacy
``/api/portals/event-coordinators/{id}/meetings`` dataset. That backend is not in
this repository, so the page has never had a request that could succeed. This
revision gives it one table to read, and **only** a table.

What this is not: a calendar integration
==========================================
Gate **G5 (Calendar API)** stays deferred under the ratified
``docs/decisions/synthetic-pilot-development-authorization-2026-09-03.md`` §3,
and ``services/api/smartmatch_api/routers/calendar.py``'s docstring draws the
boundary this revision stays inside: "There is no client here, no OAuth scope, no
credential, and no environment variable that a later edit could point at Google."
The same is true of the table below and of the routes that write it. A row here
is a note the unit made about a meeting *its own people* arranged; it is not a
booking, it does not reserve anybody's time, and **nothing in this system tells
an external participant that it exists**. Confusing the two would make the row a
promise the system cannot keep.

Because the record is internal, what a "meeting with the CBA team" is
*contractually* — who may book one, whether an external participant is a
``user_account`` or free text, and whether a booking ever leaves the system — is
**not settled here**. It is registered as **OQ-CBA-066**. This table ships the
internal record; the register carries the question. There is deliberately no
participant table, no invitee column, and no external-identity column, because
each of those would be an answer to OQ-CBA-066 written in DDL.

The invariant: an unresolved time is refused, never defaulted
===============================================================
``scheduled_at`` is ``NOT NULL`` **and carries no server default.** That pairing
is the whole point and it is not an oversight: there is nothing for the database
to supply, so an insert that names no instant *fails* rather than quietly
receiving one.

This is ADR-0010 rule 2 — an event with no resolved time stays out of every state
that would present it as scheduled — and it is migration finding **F-003**
written into a constraint. F-003 is what happens when a writer ignores the rule:
the legacy code turned an unparsed date into "thirty days from now" and produced
a confident meeting slot **nobody chose**. ``smartmatch_domain.ics`` was ported
specifically to end that class of defect, and
:class:`~smartmatch_domain.ics.UnschedulableEventError` exists so a caller with no
instant gets an error instead of an invention.

So the refusal is written twice, deliberately, in the two places a wrong answer
could enter:

* **Here**, as ``NOT NULL`` with no default, which is what holds when a second
  writer is added later by somebody who did not read this docstring.
* **In the route** (``smartmatch_api.routers.meetings``), as a worded ``422``
  naming the missing field, because an ``IntegrityError`` is a ``500`` and a
  coordinator who forgot the time deserves a sentence rather than a stack trace.

Neither is load-bearing alone, and neither may be relaxed into a default. A
``server_default=now()`` would mean "a meeting created at this instant is
happening at this instant", which is F-003 with a shorter offset.

``time_zone`` is stored beside the instant rather than in place of it.
``scheduled_at`` is ``timestamptz`` — an unambiguous instant — and ``time_zone``
is the IANA zone the people in the room agreed the time *in*, which is the part a
UTC instant cannot recover and which a rendering has to say out loud. It is
``NOT NULL`` for the same reason ``scheduled_at`` is: "some zone, probably ours"
is a guess, and this schema does not store guesses.

A cancellation is a transition
================================
``status`` is ``'scheduled'`` or ``'cancelled'``, and ``ck_cba_meeting_status``
is the vocabulary. A cancellation never ``DELETE``\\ s — OQ-CBA-018 settled that
shape for ``event_registration`` and the reasons carry unchanged: "cancelled" and
"never arranged" are different facts, and a unit looking at its own history needs
them to stay different.

Expand-only
=============
One new table. Nothing is dropped, renamed, backfilled or widened, and no
existing table is altered — safe under a rolling deploy per v1.1 §4.2, because
the previous release does not know this table exists.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0034_cba_meeting"
down_revision = "0033_event_filed_by"
branch_labels = None
depends_on = None


#: The two states a meeting record can be in. There is no third: a meeting that
#: was never arranged has no row, which is a different fact from one that was
#: arranged and called off.
_STATUS_IS_KNOWN = "status IN ('scheduled', 'cancelled')"

#: A title is present or the row should not exist. ``''`` is refused because an
#: empty string is a third state — "somebody opened the form and tabbed past the
#: field" — that no surface distinguishes from a missing title and no reader
#: would render differently. The upper bound is here as well as in the request
#: model because a request model is not the last line of defence for a text
#: column.
_TITLE_SHAPE_IS_HONEST = "length(btrim(title)) > 0 AND length(title) <= 200"

#: The zone the time was agreed in, non-blank. See the module docstring: this is
#: the half of a wall-clock appointment that a ``timestamptz`` cannot recover,
#: and a blank one would leave a rendering to pick a zone on the unit's behalf —
#: the same fabrication ``scheduled_at``'s missing default refuses.
_TIME_ZONE_IS_NAMED = "length(btrim(time_zone)) > 0 AND length(time_zone) <= 64"

#: Where, or how to join. Genuinely optional — a meeting whose location is still
#: being settled is a real thing to have recorded — but optional in the honest
#: sense: NULL means nobody has said, and ``''`` is refused so a blank string
#: cannot become a second way of saying it.
_LOCATION_SHAPE_IS_HONEST = (
    "location_or_link IS NULL OR "
    "(length(btrim(location_or_link)) > 0 AND length(location_or_link) <= 500)"
)


def upgrade() -> None:
    """Create the internal CBA meeting record table."""
    op.create_table(
        "cba_meeting",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        # A5-shaped, as attendance_record.owning_unit_id is: the unit whose
        # coordinator surface the meeting was recorded through, and the unit the
        # read of it is authorized against. Stored at write time rather than
        # derived later from the recorder's memberships, which can change.
        sa.Column("owning_unit_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("title", sa.Text, nullable=False),
        # THE INVARIANT. NOT NULL and **no server default**: a meeting with no
        # resolved time is refused, never defaulted. ADR-0010 rule 2 and
        # migration finding F-003 — the legacy turned an unparsed date into
        # "thirty days from now" and fabricated a slot nobody chose. There is
        # nothing here for the database to supply, so an insert that names no
        # instant fails. Do not add a default to this column. The route refuses
        # first, with a worded 422; this is what holds when the next writer
        # does not.
        sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=False),
        # The IANA zone the instant above was agreed in. NOT NULL for
        # scheduled_at's reason: "some zone, probably ours" is a guess.
        sa.Column("time_zone", sa.Text, nullable=False),
        # Where, or how to join. Free text on purpose: a room number, a building,
        # and a conference URL are the same field to the person reading the list,
        # and modelling them apart would be a product decision OQ-CBA-066 has not
        # made. Nullable — see _LOCATION_SHAPE_IS_HONEST.
        sa.Column("location_or_link", sa.Text, nullable=True),
        # No server default: a row's initial state is a decision the insert
        # makes, not one the database supplies (migration 0031's rule).
        sa.Column("status", sa.Text, nullable=False),
        # Who recorded it. Provenance, and the only person-shaped column on the
        # table: OQ-CBA-008 (provenance, no history) is why there is no revision
        # table beside it, and OQ-CBA-066 is why there is no participant column
        # beside it either.
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        # When the record last moved. Distinct from created_at and from
        # scheduled_at, all three of which answer different questions: when the
        # note was made, when it last changed, and when the meeting is.
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("id", name="cba_meeting_pkey"),
        # What a later table's composite foreign key would reference. Present
        # from the start for the reason attendance_record carries its own: adding
        # it later means a migration that has to prove the pair is already
        # unique.
        sa.UniqueConstraint("tenant_id", "id", name="uq_cba_meeting_tenant_id"),
        # Composite and tenant-safe, as every foreign key in this schema is
        # (architecture v1.1 §2.2). A single-column key to org_unit.id would
        # accept a unit from another tenant, which is the isolation guarantee
        # this shape exists to make structural rather than remembered.
        sa.ForeignKeyConstraint(
            ["tenant_id", "owning_unit_id"],
            ["org_unit.tenant_id", "org_unit.id"],
            ondelete="RESTRICT",
        ),
        # RESTRICT, for attendance_record's reason: deleting the recorder out
        # from under the record would leave a note nobody can be asked about.
        sa.ForeignKeyConstraint(
            ["tenant_id", "created_by_user_id"],
            ["user_account.tenant_id", "user_account.id"],
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(_STATUS_IS_KNOWN, name="ck_cba_meeting_status"),
        sa.CheckConstraint(_TITLE_SHAPE_IS_HONEST, name="ck_cba_meeting_title_shape"),
        sa.CheckConstraint(_TIME_ZONE_IS_NAMED, name="ck_cba_meeting_time_zone"),
        sa.CheckConstraint(_LOCATION_SHAPE_IS_HONEST, name="ck_cba_meeting_location_shape"),
    )

    # The unit's own list, in the order the page renders it. `scheduled_at` is
    # in the key rather than only in the ORDER BY so the listing is an index
    # scan rather than a sort over the unit's whole history.
    op.create_index(
        "ix_cba_meeting_unit_schedule",
        "cba_meeting",
        ["tenant_id", "owning_unit_id", "scheduled_at"],
    )


def downgrade() -> None:
    """Drop the table.

    A development tool, not a production rollback path (v1.1 §4.2). Dropping this
    discards every meeting a unit recorded, and there is no second copy anywhere:
    the record is internal by construction, so nothing outside this database ever
    received one.
    """
    op.drop_index("ix_cba_meeting_unit_schedule", table_name="cba_meeting")
    op.drop_table("cba_meeting")
