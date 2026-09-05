"""Give a student's event registration a table of its own.

Revision ID: 0026_event_registration
Revises: 0025_cba_contact_identity

Customer §15 asks that a student be able to *register* for an event. Card
``CBA-STUDENT-EVENTS`` shipped the reads and refused the write, because the
schema had nowhere to put one; this revision is the table that ends the refusal,
and **OQ-CBA-018** is the open question it answers.

Why this is a new table and not a fourth ``attendance_record.method``
=======================================================================
That was the change that would have taken one line, and it is the one thing this
revision must not do.

``attendance_record`` already ties a ``subject_id`` to an ``event_id`` inside a
tenant, and ``uq_attendance_record_subject_event`` already makes that triple
unique — so a ``POST .../register`` writing one would have worked on the first
try. It would also have been a fabrication with a paper trail. ADR-0013 makes
attendance the **only** input to points; ``ck_point_ledger_entry_kind`` (0019)
requires every ``attendance_credit`` to name a ``source_attendance_id``; and
``0009``'s own docstring says the quiet part outright — "attendance is the only
input to points ... a duplicate attendance row for the same student at the same
event is not a harmless re-scan". A row written when somebody signs up is
therefore, by construction, a row points can be computed from. A student who
registered and never went would be credited for attending, and no later code
could separate the two, because by then the evidence would say they were the
same kind of thing.

So ``ck_attendance_record_method`` is untouched. Its three values —
``qr_scan``, ``coordinator_entry``, ``import`` — each describe a person who was
*there*, and this revision adds no fourth. Intending to go is a different fact
about a different moment, and it gets a different table.

**There is no path from ``event_registration`` to ``point_ledger_entry``**, and
there must not be one. No ``source_registration_id`` column on the ledger, no
foreign key in either direction, no shared unique constraint a later join could
be built on. The ledger's only source is an attendance row (ADR-0013), and the
separation is what makes "registered but did not attend" answerable by a query
instead of by archaeology. A comment on the table below says the same thing to
anyone reading the DDL rather than this docstring.

The ``status`` vocabulary is two values, and ``waitlisted`` is deliberately not one
=====================================================================================
``ck_event_registration_status`` admits ``registered`` and ``cancelled``. Both
are reachable today: the first is what a sign-up writes, the second is what a
cancellation writes, and every row is in one of them at every instant.

``waitlisted`` is the value a reader will expect and it is absent on purpose.
A waitlist is overflow from a capacity, and this schema has no capacity:
``event`` carries no seat count, no ``max_attendees``, and nothing anywhere
states how many students an event can hold. Admitting a third value now would
put a state in the constraint that no writer could ever legitimately produce — a
vocabulary invented by DDL ahead of the decision that would give it meaning,
which is precisely what ``0012`` refused to do for ``board_role`` and what
``0024``'s docstring cites that refusal for. When a capacity is ratified,
widening this CHECK is a two-line revision and the diff will say which card
decided it.

The enumeration is a CHECK over ``text`` rather than a PostgreSQL ``ENUM`` type,
following ``ck_attendance_record_method`` (0009), ``ck_review_item_status``
(0008) and ``ck_outbox_status`` (0001). Every enumeration in this schema is
already shaped that way, and a native enum type would make the widening above an
``ALTER TYPE`` in a schema where nothing else needs one.

Cancellation is a transition, not a ``DELETE``
================================================
A cancelled registration keeps its row and moves its ``status``. The alternative
— deleting on cancel — makes "they cancelled" and "they never registered" the
same absence, and those are different facts a coordinator will want told apart:
one is a student who changed their mind, the other is a student the event never
reached. Deleting also throws away the ``registered_at`` that says *when* they
had intended to come, which is the only signal in this table about how late a
cancellation was.

That choice is what makes ``updated_at`` load-bearing rather than decorative.
``registered_at`` is when the place was taken and never moves; ``updated_at`` is
when the status last did, so a cancellation has a time. Both are ``NOT NULL``
with a ``now()`` server default, the same shape ``attendance_record.created_at``
carries.

It also decides what re-registering means. Uniqueness on
``(tenant_id, subject_id, event_id)`` holds whether the row is registered or
cancelled, so a student who cancels and signs up again does **not** get a second
row — they get the first one moved back to ``registered`` with a new
``updated_at``. That is the honest reading of a table with one row per student
per event, and it is why this revision adds no ``cancelled_at``: a column
recording one cancellation would quietly become wrong the moment there were two.
A full history of every transition is ``contact_channel_transition``'s shape
(0023) and is deliberately **not** built here — see the open questions below.

Idempotency is the uniqueness, not a header
=============================================
``uq_event_registration_subject_event`` on ``(tenant_id, subject_id, event_id)``
is the same triple ``uq_attendance_record_subject_event`` uses, and it is what
makes a second click the same registration however the request was phrased. This
is ``0024``/``routers/speaker_requests.py``'s rule applied again: a header
``Idempotency-Key`` only recognises a repeat of the *identical body*, while a
natural key makes a resubmission the same object even when the request differs.
Two notions of sameness beside each other would disagree the first time they
were asked, so this table has only the stronger one.

Foreign keys, and why all three are ``RESTRICT``
==================================================
All three are composite on ``tenant_id``, per architecture v1.1 §2.2, so a
registration cannot name an event, a student, or a unit belonging to another
tenant — isolation held by the key rather than by a predicate somebody has to
remember to write.

* ``(tenant_id, event_id) -> event(tenant_id, id)``, ``ON DELETE RESTRICT``. An
  event must not be deleted out from under a student holding a place at it. The
  contrast worth reading is ``speaker_request_classification`` (0024), whose
  reference to the same parent is ``CASCADE``: a classification is *part of* the
  request and cannot outlive it, while a registration is a second party's
  statement about the event and its disappearance is a fact that party should be
  told about rather than have silently erased. ``attendance_record`` references
  ``event`` with ``RESTRICT`` for the neighbouring reason (0017), and a
  registration is at least as much a claim as an attendance is.
* ``(tenant_id, subject_id) -> user_account(tenant_id, id)``, ``ON DELETE
  RESTRICT``, exactly as ``attendance_record.subject_id`` is: no route in this
  codebase deletes a ``user_account``, so the practical difference from
  ``CASCADE`` is nil today, and the day it stops being nil is the day the choice
  matters.
* ``(tenant_id, owning_unit_id) -> org_unit(tenant_id, id)``, ``ON DELETE
  RESTRICT``, as ``attendance_record``, ``job`` and ``import_batch`` all are:
  reorganizing a unit must not silently delete the rows scoped against it.

``owning_unit_id`` is A5-shaped and populated at write time
=============================================================
It is the unit whose student surface the registration was made through, stored
on the row rather than reached through ``event.host_org_unit_id`` at read time —
the same argument ``0008`` gives for ``import_batch`` carrying its own
``owning_unit_id`` rather than joining back through ``job``. Every authorizer in
this codebase resolves an ``org_unit`` and compares paths, so a table with no
unit column would force the one route that writes it to authorize against
something no other surface authorizes against.

No index beyond the constraints, and that is a decision
=========================================================
The read this table serves is "the events *this* student registered for in this
unit", which filters on ``(tenant_id, subject_id)``. That is the leading pair of
``uq_event_registration_subject_event``, whose backing unique index already
serves it — so an explicit index would be a second copy of one PostgreSQL has
already built. ``0017``'s ``ix_event_host_unit`` exists because no constraint
covered ``(tenant_id, host_org_unit_id)``; here one does.

Expand-only
=============
One new table. Nothing is dropped, renamed, backfilled, or widened, and no
existing constraint is touched — so this is safe under a rolling deploy per v1.1
§4.2 without qualification: the old release does not know the table exists, and
an empty new table has nothing for it to misread.

Open questions this revision leaves open
==========================================
* **OQ-CBA-018** is answered by this revision and its status is amended
  accordingly: the table is ``event_registration``, and the column list is the
  one below.
* **OQ-CBA-021** — capacity and the waitlist. No seat count exists anywhere in
  the schema, so ``waitlisted`` is not in the CHECK. Adding a capacity is a
  product decision about what happens at the boundary, not a column.
* **OQ-CBA-022** — whether a registration needs a *history* of its transitions
  rather than the current status plus one ``updated_at``. This revision stores
  the current value only, the same treatment ``0024`` gives a classification
  under OQ-CBA-008; if the answer is yes, the shape is
  ``contact_channel_transition``'s and it is a later revision.
* **OQ-CBA-020** — the month grid's interactivity. Unblocked by this revision
  rather than answered by it: a day cell now has an action it could offer, which
  was the reason that question was parked.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0026_event_registration"
down_revision = "0025_cba_contact_identity"
branch_labels = None
depends_on = None


#: ``event_registration.status``. Two values, both reachable today; see the
#: module docstring on why ``waitlisted`` is not a third.
STATUS_REGISTERED = "registered"
STATUS_CANCELLED = "cancelled"

#: The CHECK's condition, built from the two constants so the constraint and any
#: reader of them cannot drift into disagreeing about the vocabulary.
_STATUS_CONDITION = f"status IN ('{STATUS_REGISTERED}','{STATUS_CANCELLED}')"


def upgrade() -> None:
    """Create ``event_registration``."""
    op.create_table(
        "event_registration",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        # A5-shaped, as attendance_record.owning_unit_id (0009) and
        # import_batch.owning_unit_id (0008) are: the unit whose student
        # surface this registration was made through, scoped at write time
        # rather than joined back through event later.
        sa.Column("owning_unit_id", postgresql.UUID(as_uuid=True), nullable=False),
        # The event a place was taken at.
        sa.Column("event_id", postgresql.UUID(as_uuid=True), nullable=False),
        # The student. Self-scoped reads filter on this column, and it is never
        # taken from a request body — see routers/student_events.py.
        sa.Column("subject_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        # When the place was taken. Never moves, including across a
        # cancel-then-re-register: it is what says how late a cancellation was.
        sa.Column(
            "registered_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        # When `status` last moved, so a cancellation has a time. This is the
        # column that makes cancellation-as-a-transition legible; without it a
        # cancelled row would say only that it is cancelled.
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("id"),
        # The natural key, and the whole of this table's idempotency. One row
        # per student per event whatever its status, so a re-registration after
        # a cancellation moves the first row rather than inserting a second.
        #
        # Deliberately NOT accompanied by a uq_event_registration_tenant_id on
        # (tenant_id, id): nothing references this table, and per 0008's rule
        # the constraint is added by whichever revision first needs it. The one
        # thing that must never need it is point_ledger_entry — a registration
        # is not attendance, and ADR-0013 makes attendance the only input to
        # points. See the module docstring.
        sa.UniqueConstraint(
            "tenant_id",
            "subject_id",
            "event_id",
            name="uq_event_registration_subject_event",
        ),
        # RESTRICT: an event must not be deleted out from under a student
        # holding a place at it. Contrast speaker_request_classification's
        # CASCADE onto the same parent — that is part of the event, this is a
        # second party's statement about it.
        sa.ForeignKeyConstraint(
            ["tenant_id", "event_id"],
            ["event.tenant_id", "event.id"],
            ondelete="RESTRICT",
        ),
        # RESTRICT, as attendance_record.subject_id is.
        sa.ForeignKeyConstraint(
            ["tenant_id", "subject_id"],
            ["user_account.tenant_id", "user_account.id"],
            ondelete="RESTRICT",
        ),
        # RESTRICT: reorganizing a unit must not silently delete the
        # registrations scoped against it.
        sa.ForeignKeyConstraint(
            ["tenant_id", "owning_unit_id"],
            ["org_unit.tenant_id", "org_unit.id"],
            ondelete="RESTRICT",
        ),
        # Two values, both reachable. `waitlisted` is absent because no capacity
        # exists for it to overflow from (OQ-CBA-021).
        sa.CheckConstraint(_STATUS_CONDITION, name="ck_event_registration_status"),
    )


def downgrade() -> None:
    """Drop the table.

    A development tool, not a production rollback path (v1.1 §4.2). Dropping
    this table destroys every registration in it, which is the reason the
    upgrade refuses to model a cancellation as a delete: the same information
    loss, applied to everything at once.
    """
    op.drop_table("event_registration")
