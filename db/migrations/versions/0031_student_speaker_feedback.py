"""One student's rating of one speaker at one event they actually attended.

Customer §15 ("provide feedback/ratings on speakers"), §16 ("Speaker
Connectors/admin users must be able to view the feedback"), and §26 item 3,
which recorded that the scale, the fields, and the aggregation behaviour were
**not specified**. They are now: OQ-CBA-003 was decided on 6 September 2026 by
Danny Tran, program owner of record, and this revision implements that decision
and nothing beyond it.

One table. Every column and every constraint below traces to one of the four
parts of that decision.

Stored attributed, shown aggregate-only
=========================================
``student_id`` is a real, NOT NULL, foreign-keyed column. **Anonymity here is an
API display rule, not an absence in the data**, and that distinction is the
whole design:

* **Retraction** needs to know whose row to withdraw. A student who changes
  their mind has to be able to point at their own rating, and an unattributed
  row cannot be pointed at.
* **De-duplication** needs it too — ``uq_student_speaker_feedback_subject``
  below is what stops one student rating one speaker at one event five times,
  and a table with no student column has no key to enforce it on.
* **Abuse tracing** needs it last: a coordinator investigating a coordinated
  pile-on has to be able to ask *how many distinct people* wrote these rows.

Dropping ``student_id`` would look like a privacy improvement and would break
all three at once. What actually protects the student is that no
Connector-facing read ever returns this column beside a rating — enforced in
``smartmatch_api.routers.student_speaker_feedback`` and proved in
``tests/contract/test_student_feedback_api.py``, not here.

One dimension, and it is required
===================================
``rating`` is a single overall 1-5 integer;
``ck_student_speaker_feedback_rating_range`` is the bound. There are no
sub-criteria columns, because the decision names one dimension and §16's "do
not over-design this requirement" makes inventing a second a product change
made in DDL. ``comment`` is the optional free-text half, and it is optional in
the honest sense: NULL means the student wrote nothing, and
``ck_student_speaker_feedback_comment_shape`` refuses ``''`` so a blank string
cannot become a third state nobody defined.

Eligibility is a foreign key, not a route check
=================================================
The composite foreign key on ``(tenant_id, student_id, event_id)`` targets
``attendance_record``'s ``uq_attendance_record_subject_event``. **A student who
did not attend the event cannot have a row in this table** — not "is refused by
the route", but has nowhere to be stored. The route refuses first, with a
worded 403; the constraint is what holds when a second writer is added later by
someone who did not read this docstring.

``attendance_record`` rather than ``event_registration``, deliberately.
Registration is an intent to attend — 0026's docstring makes that separation
the reason that table exists at all — and a student who signed up and stayed
home heard nobody speak. Attendance is the evidence a rating claims to rest on,
so it is the evidence the schema requires.

The speaker side is a plain foreign key to ``speaker_profile`` on
``(tenant_id, professional_id)`` — **by id only**. Nothing here derives a
speaker from a name, which is what keeps this table correct across
``0030_cba_opaque_speaker_identity``'s re-key of that column.

What the schema cannot check is which speaker appeared at which event: no table
in this database records an appearance. The route binds the two through the
event's host unit roster, and **OQ-CBA-051** records that as unfinished rather
than pretending the join exists.

Withdrawal is a transition, and it empties the row
====================================================
``status`` is ``'submitted'`` or ``'withdrawn'``. A withdrawal never DELETEs —
OQ-CBA-018 settled that shape for ``event_registration`` and the reasons carry:
"withdrawn" and "never rated" must stay distinguishable, and the row is what
de-duplication and abuse tracing are anchored to.

But a withdrawal does *mean* something, so
``ck_student_speaker_feedback_rating_present`` writes it as an equivalence —
exactly the submitted rows carry a rating — and
``ck_student_speaker_feedback_withdrawn_is_silent`` takes the words back with
it. A retracted opinion is gone from the database; the fact that this student
rated this speaker once is not. That is the narrowest reading of "withdrawable"
that still leaves the three properties above working.

Re-submitting after a withdrawal is an idempotent flip on the same row, for
0026's reason.

Where the seven-day cutoff is *not*
=====================================
There is no ``locked_at`` column and no cutoff expression in any CHECK. The
cutoff is ``FEEDBACK_EDIT_WINDOW_DAYS`` in
``smartmatch_domain.student_speaker_feedback``, evaluated against the event's
date at the moment an edit is attempted. A CHECK cannot see ``event.starts_at``,
and a stored ``locked_at`` would be a denormalised copy of a derived fact that
goes wrong the moment an event is rescheduled.

``event.time_precision`` has an ``'unresolved'`` state (ADR-0010), and an event
with no date has no anchor a deadline can be measured from. The domain returns
"the window's close is unknown" for that case rather than fabricating one in
either direction; **OQ-CBA-052** records that nobody has ruled on it.

Where the n=3 suppression is *not*
====================================
Also not here. Aggregation is a read, suppression is a property of that read,
and a CHECK constrains writes. ``aggregate_speaker_feedback`` returns no mean
and no count below ``MIN_RESPONSES_FOR_AGGREGATE``, per ADR-0011 rule 1 —
unknown is not zero, and in a class of thirty an average over two students is
both meaningless and re-identifying.

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

revision = "0031_student_speaker_feedback"
down_revision = "0030_cba_opaque_speaker_identity"
branch_labels = None
depends_on = None


#: The two states a rating can be in. There is no third: a rating that was never
#: written has no row, which is a different fact from a rating that was written
#: and taken back, and this vocabulary keeps the two apart.
_STATUS_IS_KNOWN = "status IN ('submitted', 'withdrawn')"

#: OQ-CBA-003 part 2: **one** required overall 1-5 rating. Written as an
#: explicit pair of bounds rather than a ``BETWEEN``, so widening either end is a
#: visible edit here and in ``test_check_constraints.py``'s pinned expression.
#: ``IS NULL`` is admitted because a withdrawn row carries no rating; *which*
#: rows may be NULL is the next constraint's job, not this one's.
_RATING_IS_IN_RANGE = "rating IS NULL OR (rating >= 1 AND rating <= 5)"

#: Exactly the submitted rows carry a rating. An equivalence rather than two
#: implications, so neither half can be relaxed without the other: a submitted
#: row with no rating would be a feedback record that says nothing, and a
#: withdrawn row still carrying one would be a retraction that retracted
#: nothing.
_RATING_IFF_SUBMITTED = "(status = 'submitted') = (rating IS NOT NULL)"

#: A comment is absent or it is real. ``''`` is refused because an empty string
#: is a third state — "the student opened the box and wrote nothing" — that no
#: surface distinguishes from NULL and no reader would render differently. The
#: upper bound mirrors ``MAX_COMMENT_LENGTH`` in the domain; it is here as well
#: because a request model is not the last line of defence for a text column.
_COMMENT_SHAPE_IS_HONEST = (
    "comment IS NULL OR (length(btrim(comment)) > 0 AND length(comment) <= 2000)"
)

#: A withdrawal takes the words back too. Without this the rating would vanish
#: on retraction and the free text would survive it, which is the half a student
#: is most likely to have meant.
_WITHDRAWN_IS_SILENT = "status <> 'withdrawn' OR comment IS NULL"


def upgrade() -> None:
    """Create the student speaker feedback table."""
    op.create_table(
        "student_speaker_feedback",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        # A5-shaped, as attendance_record.owning_unit_id is: the unit whose
        # student surface the rating was written through, and the unit a
        # Connector's authorization to read the aggregate is scoped against.
        # Stored at write time rather than joined back through
        # event.host_org_unit_id later.
        sa.Column("owning_unit_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("event_id", postgresql.UUID(as_uuid=True), nullable=False),
        # The student. Stored, never displayed beside a rating — see the module
        # docstring. Every read of this column filters on it from the verified
        # principal, never from a request field (MM-A01).
        sa.Column("student_id", postgresql.UUID(as_uuid=True), nullable=False),
        # The speaker, by opaque id. Nothing derives this from a name.
        sa.Column("speaker_professional_id", postgresql.UUID(as_uuid=True), nullable=False),
        # No server default: a row's initial state is a decision the insert
        # makes, not one the database supplies.
        sa.Column("status", sa.Text, nullable=False),
        # The one dimension. Nullable only so a withdrawal can empty it;
        # _RATING_IFF_SUBMITTED is what stops that nullability meaning anything
        # else.
        sa.Column("rating", sa.Integer, nullable=True),
        sa.Column("comment", sa.Text, nullable=True),
        # When the first submission landed. Never moves across a
        # withdraw-then-resubmit, so it stays able to say how promptly a student
        # responded — the same reason event_registration.registered_at does not
        # move.
        sa.Column(
            "submitted_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        # When the rating, the comment, or the status last moved. This is what
        # an edit is visible as; OQ-CBA-008 (provenance, no history) is why
        # there is no revision table beside it.
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("id", name="student_speaker_feedback_pkey"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_student_speaker_feedback_tenant_id"),
        # De-duplication, and the reason `student_id` is stored at all: one
        # rating per student per speaker per event, whatever its status. A
        # second submission is the same row flipped, not a second vote.
        sa.UniqueConstraint(
            "tenant_id",
            "student_id",
            "event_id",
            "speaker_professional_id",
            name="uq_student_speaker_feedback_subject",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "owning_unit_id"],
            ["org_unit.tenant_id", "org_unit.id"],
            ondelete="RESTRICT",
        ),
        # Eligibility, as a database fact rather than a route's promise. Targets
        # `uq_attendance_record_subject_event`. A student who did not attend
        # this event has nowhere to store a rating of it.
        sa.ForeignKeyConstraint(
            ["tenant_id", "student_id", "event_id"],
            [
                "attendance_record.tenant_id",
                "attendance_record.subject_id",
                "attendance_record.event_id",
            ],
            ondelete="RESTRICT",
        ),
        # RESTRICT, for attendance_record's own reason: removing the speaker out
        # from under a rating would leave feedback about nobody.
        sa.ForeignKeyConstraint(
            ["tenant_id", "speaker_professional_id"],
            ["speaker_profile.tenant_id", "speaker_profile.professional_id"],
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(_STATUS_IS_KNOWN, name="ck_student_speaker_feedback_status"),
        sa.CheckConstraint(_RATING_IS_IN_RANGE, name="ck_student_speaker_feedback_rating_range"),
        sa.CheckConstraint(
            _RATING_IFF_SUBMITTED, name="ck_student_speaker_feedback_rating_present"
        ),
        sa.CheckConstraint(
            _COMMENT_SHAPE_IS_HONEST, name="ck_student_speaker_feedback_comment_shape"
        ),
        sa.CheckConstraint(
            _WITHDRAWN_IS_SILENT, name="ck_student_speaker_feedback_withdrawn_is_silent"
        ),
    )

    # The Connector's aggregate read: every rating of one speaker, in one unit.
    # `status` is in the key because the aggregate counts submitted rows only,
    # and without it the index would hand back withdrawn rows for the query to
    # discard.
    op.create_index(
        "ix_student_speaker_feedback_speaker",
        "student_speaker_feedback",
        ["tenant_id", "owning_unit_id", "speaker_professional_id", "status"],
    )
    # The student's own list — "what have I already rated?" — which is the read
    # the submission form makes before it offers to submit anything.
    op.create_index(
        "ix_student_speaker_feedback_student",
        "student_speaker_feedback",
        ["tenant_id", "student_id", "event_id"],
    )


def downgrade() -> None:
    """Drop the table.

    A development tool, not a production rollback path (v1.1 §4.2). Dropping
    this discards every rating students wrote, and there is no second copy
    anywhere — the aggregate is computed on read and stored nowhere.
    """
    op.drop_index("ix_student_speaker_feedback_student", table_name="student_speaker_feedback")
    op.drop_index("ix_student_speaker_feedback_speaker", table_name="student_speaker_feedback")
    op.drop_table("student_speaker_feedback")
