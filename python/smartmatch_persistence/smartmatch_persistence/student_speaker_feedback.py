"""The student speaker feedback write and read path (migration ``0031``).

Card ``CBA-STUDENT-FEEDBACK``, customer §§15-16, implementing OQ-CBA-003 as
decided on 6 September 2026. This module is the only writer of
``student_speaker_feedback``, and the rules it applies come from
:mod:`smartmatch_domain.student_speaker_feedback` rather than from statements
assembled here.

Idempotency is the natural key, not a header
==============================================
``uq_student_speaker_feedback_subject`` on
``(tenant_id, student_id, event_id, speaker_professional_id)`` is what makes a
second submission the same rating. This is
:mod:`smartmatch_persistence.event_registration`'s rule on a third surface: an
``Idempotency-Key`` header only recognises a repeat of the identical body, and a
student changing 4 to 5 is deliberately *not* a new rating — it is an edit of
their own, which is the whole of part 3 of the decision.

So there is one write for both submitting and editing.
:meth:`StudentSpeakerFeedbackRepository.submit` inserts when there is no row,
moves a withdrawn row back, rewrites a differing one, and writes nothing at all
when the rating and comment are already exactly what was asked for — because
``updated_at`` means "when this last moved" and a double-clicked Submit moved
nothing.

A withdrawal empties the row it keeps
=======================================
:meth:`StudentSpeakerFeedbackRepository.withdraw` sets ``status`` to
``withdrawn`` and nulls **both** the rating and the comment. The row survives
for migration ``0031``'s reason — de-duplication and abuse tracing are anchored
to it, and "withdrawn" must stay distinguishable from "never rated" — but the
opinion itself is gone, which is what a student retracting their words means.
``ck_student_speaker_feedback_rating_present`` and
``ck_student_speaker_feedback_withdrawn_is_silent`` refuse a half-honoured
retraction if this module ever stops doing both.

Eligibility is read, never assumed
====================================
:meth:`StudentSpeakerFeedbackRepository.eligibility` answers the three questions
a route has to ask before it accepts a rating, in one call: did this student
attend this event, is this speaker on this unit's roster, and what instant does
the edit window count from. The first is also a foreign key, so a route that
skipped the check would get an ``IntegrityError`` rather than a bad row — but an
``IntegrityError`` is a ``500``, and a student who did not attend deserves a
worded refusal.

The second is the weak one, and it is weak because of a gap in the schema rather
than in this module: **nothing in this database records which speaker appeared at
which event.** ``cba_invitation_batch`` names its event in free text, so it
cannot be joined. Roster membership is the nearest available evidence and it is
not the same claim. **OQ-CBA-051.**

What this module does not do
==============================
**No commit.** Transaction boundaries belong to the caller, like every other
repository here — and ``get_session`` rolls back unconditionally, so a route
that returns ``201`` without committing stores nothing while looking entirely
successful.

**No aggregation.** :meth:`StudentSpeakerFeedbackRepository.submitted_ratings`
returns the scores that count and stops there; the mean, the count and the n=3
suppression belong to
:func:`~smartmatch_domain.student_speaker_feedback.aggregate_speaker_feedback`,
so the rule has one implementation and a unit test rather than being a property
of a ``GROUP BY``. A ``HAVING count(*) >= 3`` here would suppress the same rows
and would put a privacy rule in a query plan.

**No authorization**, and **no student identifier leaves in an aggregate.**
Every method takes ``tenant_id`` and, on the student paths, ``student_id``, and
filters on both; who may supply them is the router's question, and the answer
there is that ``student_id`` comes from the verified principal and never from a
request field (MM-A01).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import sqlalchemy as sa
from smartmatch_domain.student_speaker_feedback import (
    FeedbackStatus,
    Rating,
    feedback_anchor,
)
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Session

from smartmatch_persistence import schema

__all__ = [
    "EligibilityFacts",
    "FeedbackRow",
    "FeedbackWriteResult",
    "StudentSpeakerFeedbackRepository",
]


@dataclass(frozen=True, slots=True)
class FeedbackRow:
    """One ``student_speaker_feedback`` row as its own author sees it.

    Returned only on the student's own paths. The Connector-facing read never
    builds one of these — it goes through
    :meth:`StudentSpeakerFeedbackRepository.submitted_ratings`, which returns
    bare integers and therefore has no field a ``student_id`` could travel in.

    Attributes:
        id: The rating's surrogate key.
        event_id: The event the rating is about.
        student_id: The author. Always the caller's own on every path this row
            is returned from.
        speaker_professional_id: The speaker, by opaque id.
        status: ``submitted`` or ``withdrawn``.
        rating: ``1..5``, or ``None`` on a withdrawn row.
        comment: The student's words, or ``None`` — both when they wrote none
            and after a withdrawal took them back.
        submitted_at: When the first submission landed. Does not move.
        updated_at: When the rating, comment or status last moved.
    """

    id: uuid.UUID
    event_id: uuid.UUID
    student_id: uuid.UUID
    speaker_professional_id: uuid.UUID
    status: str
    rating: int | None
    comment: str | None
    submitted_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class FeedbackWriteResult:
    """What one submit or withdraw did.

    Attributes:
        row: The rating as it stands after the call, read back out of the
            database rather than constructed here — ``submitted_at`` and
            ``updated_at`` are server-defaulted, so a locally built value would
            be this module's guess at what PostgreSQL wrote. ``None`` only from
            :meth:`StudentSpeakerFeedbackRepository.withdraw` on a student who
            never rated this speaker, which writes no row at all.
        created: ``True`` only when this call inserted a row. A re-submission
            that moved a withdrawn row back is not a creation — there is one row
            per student per speaker per event and it is still the same one.
        changed: ``True`` when something actually moved. ``False`` for a repeat
            of an identical submission and for a withdrawal with nothing to
            withdraw. This is the flag that keeps a response from claiming an
            edit that did not happen.
    """

    row: FeedbackRow | None
    created: bool
    changed: bool


@dataclass(frozen=True, slots=True)
class EligibilityFacts:
    """Whether this student may rate this speaker at this event, and until when.

    Attributes:
        event_exists: Whether the event exists in this tenant at all.
        attended: Whether an ``attendance_record`` exists for this student at
            this event. This is the evidence a rating rests on, and it is also
            the composite foreign key on the row — attendance rather than
            registration, because a student who signed up and stayed home heard
            nobody speak.
        speaker_on_roster: Whether the speaker is on this unit's §13 roster. The
            nearest available stand-in for "this speaker appeared at this
            event", which nothing in this schema records. **OQ-CBA-051.**
        anchor: The instant the edit window is measured from, or ``None`` when
            the event's date is unresolved (ADR-0010). Never invented.
    """

    event_exists: bool
    attended: bool
    speaker_on_roster: bool
    anchor: datetime | None


#: The columns :class:`FeedbackRow` is built from, in its own field order. One
#: tuple rather than a repeated ``select`` list, the discipline
#: ``event_registration._REGISTRATION_COLUMNS`` states: a column added to the
#: row type and forgotten in one of the readers is impossible by construction.
_FEEDBACK_COLUMNS = (
    schema.student_speaker_feedback.c.id,
    schema.student_speaker_feedback.c.event_id,
    schema.student_speaker_feedback.c.student_id,
    schema.student_speaker_feedback.c.speaker_professional_id,
    schema.student_speaker_feedback.c.status,
    schema.student_speaker_feedback.c.rating,
    schema.student_speaker_feedback.c.comment,
    schema.student_speaker_feedback.c.submitted_at,
    schema.student_speaker_feedback.c.updated_at,
)


def _row(record: sa.Row[Any]) -> FeedbackRow:
    """Build the read model from a row selected through :data:`_FEEDBACK_COLUMNS`."""
    return FeedbackRow(
        id=record.id,
        event_id=record.event_id,
        student_id=record.student_id,
        speaker_professional_id=record.speaker_professional_id,
        status=record.status,
        rating=record.rating,
        comment=record.comment,
        submitted_at=record.submitted_at,
        updated_at=record.updated_at,
    )


class StudentSpeakerFeedbackRepository:
    """Reads and writes ``student_speaker_feedback``.

    Takes a session per call and commits nothing, like every other repository in
    this package. Stateless; one instance serves all callers.
    """

    def get(
        self,
        session: Session,
        *,
        tenant_id: uuid.UUID,
        student_id: uuid.UUID,
        event_id: uuid.UUID,
        speaker_professional_id: uuid.UUID,
    ) -> FeedbackRow | None:
        """This student's rating of this speaker at this event, whatever its status.

        ``None`` means they have never rated — a different fact from a row
        reading ``withdrawn``, and keeping the two distinguishable is why
        migration ``0031`` refuses to model a withdrawal as a ``DELETE``.

        ``tenant_id`` is in the ``WHERE`` clause rather than applied afterwards,
        and the quadruple is ``uq_student_speaker_feedback_subject``, so this is
        a point lookup rather than a scan.
        """
        record = session.execute(
            sa.select(*_FEEDBACK_COLUMNS).where(
                schema.student_speaker_feedback.c.tenant_id == tenant_id,
                schema.student_speaker_feedback.c.student_id == student_id,
                schema.student_speaker_feedback.c.event_id == event_id,
                schema.student_speaker_feedback.c.speaker_professional_id
                == speaker_professional_id,
            )
        ).one_or_none()
        return None if record is None else _row(record)

    def list_for_student_event(
        self,
        session: Session,
        *,
        tenant_id: uuid.UUID,
        student_id: uuid.UUID,
        event_id: uuid.UUID,
    ) -> list[FeedbackRow]:
        """Everything this student has said about speakers at this one event.

        Every status is returned, including ``withdrawn``, and the caller
        narrows. ``EventRegistrationRepository.rows_for_events``'s reasoning
        applies here too: the form has to render "you withdrew this" differently
        from "you have not rated this speaker", so a reader that dropped
        withdrawn rows would force its one caller to issue a second query for
        the rows the first deliberately hid.
        """
        records = session.execute(
            sa.select(*_FEEDBACK_COLUMNS)
            .where(
                schema.student_speaker_feedback.c.tenant_id == tenant_id,
                schema.student_speaker_feedback.c.student_id == student_id,
                schema.student_speaker_feedback.c.event_id == event_id,
            )
            .order_by(schema.student_speaker_feedback.c.speaker_professional_id)
        ).all()
        return [_row(record) for record in records]

    def submitted_ratings(
        self,
        session: Session,
        *,
        tenant_id: uuid.UUID,
        owning_unit_id: uuid.UUID,
        speaker_professional_id: uuid.UUID,
    ) -> list[int]:
        """The scores that count for one speaker in one unit.

        **Bare integers, deliberately.** This is the only read behind the
        Connector-facing surface, and it selects one column: there is no
        ``student_id`` in the result set for a route to forget to strip, and no
        row type it could travel in. Part 1 of OQ-CBA-003 is a property of this
        signature rather than a discipline applied downstream.

        Withdrawn rows are excluded here, in the database, because they are not
        evidence any more — their rating is ``NULL``, and including them would
        make the caller filter ``None`` out of a list of scores. Filtering here
        also means a withdrawal correctly drops a speaker back below the n=3
        threshold, which is the case a stored or cached aggregate gets wrong.

        The aggregation itself is not done here. See the module docstring.
        """
        rows = session.execute(
            sa.select(schema.student_speaker_feedback.c.rating).where(
                schema.student_speaker_feedback.c.tenant_id == tenant_id,
                schema.student_speaker_feedback.c.owning_unit_id == owning_unit_id,
                schema.student_speaker_feedback.c.speaker_professional_id
                == speaker_professional_id,
                schema.student_speaker_feedback.c.status == FeedbackStatus.SUBMITTED.value,
            )
        ).all()
        return [row.rating for row in rows if row.rating is not None]

    def submitted_ratings_by_speaker(
        self,
        session: Session,
        *,
        tenant_id: uuid.UUID,
        owning_unit_id: uuid.UUID,
    ) -> dict[uuid.UUID, list[int]]:
        """The scores that count for a whole unit, grouped by the speaker.

        Two columns rather than :meth:`submitted_ratings`' one, and the second
        is a **speaker** id. That module claim -- "there is no ``student_id`` in
        the result set for a route to forget to strip" -- survives the widening
        intact: the grouping key is the professional the ratings are about, and
        there is still no row type a student identifier could travel in.

        The grouping exists because the unit aggregate is not a sum. Its
        suppression rule needs to know how many ratings each speaker has, so
        that a speaker whose own aggregate is already published can be
        subtracted out and the remainder checked -- see
        :func:`~smartmatch_domain.student_speaker_feedback.aggregate_unit_feedback`.
        A read that returned one flat list would make that rule uncomputable and
        the endpoint differenceable.

        Withdrawn rows are excluded here, in the database, for
        :meth:`submitted_ratings`' reasons, and ``rating IS NOT NULL`` is
        asserted alongside the status rather than trusted from it: the two are
        kept in step by ``ck_student_speaker_feedback_withdrawn_is_silent``, and
        a read that silently produced ``None`` in a list of scores would be a
        harder defect to find than a row that never arrives.

        Both scopes are in the query rather than applied to its result. A unit
        the caller does not name contributes nothing, and a tenant is not a
        filter applied afterwards.

        The aggregation, and every threshold in it, is the domain's. See the
        module docstring: no ``GROUP BY`` decides who may see a number.
        """
        rows = session.execute(
            sa.select(
                schema.student_speaker_feedback.c.speaker_professional_id,
                schema.student_speaker_feedback.c.rating,
            ).where(
                schema.student_speaker_feedback.c.tenant_id == tenant_id,
                schema.student_speaker_feedback.c.owning_unit_id == owning_unit_id,
                schema.student_speaker_feedback.c.status == FeedbackStatus.SUBMITTED.value,
                schema.student_speaker_feedback.c.rating.is_not(None),
            )
        ).all()

        by_speaker: dict[uuid.UUID, list[int]] = {}
        for row in rows:
            by_speaker.setdefault(row.speaker_professional_id, []).append(row.rating)
        return by_speaker

    def event_anchor(
        self,
        session: Session,
        *,
        tenant_id: uuid.UUID,
        event_id: uuid.UUID,
    ) -> tuple[bool, datetime | None]:
        """Whether the event exists here, and the instant its edit window runs from.

        Separate from :meth:`eligibility` because two callers need only this
        half: the listing route resolves one window for a whole page of ratings,
        and asking the fuller question would mean naming a speaker it is not
        asking about.

        Returns:
            ``(event_exists, anchor)``. ``anchor`` is ``None`` both when the
            event does not exist and when its date is unresolved (ADR-0010) —
            the two are told apart by the first element, and neither invents a
            date.
        """
        record = session.execute(
            sa.select(
                schema.event.c.time_precision,
                schema.event.c.starts_at,
                schema.event.c.ends_at,
                schema.event.c.on_date,
            ).where(
                schema.event.c.tenant_id == tenant_id,
                schema.event.c.id == event_id,
            )
        ).one_or_none()
        if record is None:
            return (False, None)
        return (
            True,
            feedback_anchor(
                time_precision=record.time_precision,
                starts_at=record.starts_at,
                ends_at=record.ends_at,
                on_date=record.on_date,
            ),
        )

    def speaker_on_roster(
        self,
        session: Session,
        *,
        tenant_id: uuid.UUID,
        owning_unit_id: uuid.UUID,
        speaker_professional_id: uuid.UUID,
    ) -> bool:
        """Whether this speaker is on this unit's §13 roster.

        The nearest available stand-in for "this speaker appeared at this event",
        which nothing in this schema records (**OQ-CBA-051**). Also what lets the
        Connector-facing summary answer ``404`` for an id that names nobody,
        rather than an empty aggregate that would let the route be used to
        enumerate ids.
        """
        return (
            session.execute(
                sa.select(sa.literal(1)).where(
                    schema.speaker_profile.c.tenant_id == tenant_id,
                    schema.speaker_profile.c.owning_unit_id == owning_unit_id,
                    schema.speaker_profile.c.professional_id == speaker_professional_id,
                )
            ).first()
            is not None
        )

    def eligibility(
        self,
        session: Session,
        *,
        tenant_id: uuid.UUID,
        owning_unit_id: uuid.UUID,
        student_id: uuid.UUID,
        event_id: uuid.UUID,
        speaker_professional_id: uuid.UUID,
    ) -> EligibilityFacts:
        """The three facts a route needs before it accepts a rating.

        Every predicate carries ``tenant_id``.

        The attendance check duplicates a foreign key on purpose. The constraint
        is what makes an ineligible row unstorable; this is what makes the
        refusal a worded ``403`` instead of an ``IntegrityError`` surfacing as a
        ``500``.

        Returns:
            :class:`EligibilityFacts`. ``anchor`` comes from
            :func:`~smartmatch_domain.student_speaker_feedback.feedback_anchor`
            over ADR-0010's stored triple, so an unresolved event date yields
            ``None`` here rather than a date this module chose.
        """
        event_exists, anchor = self.event_anchor(session, tenant_id=tenant_id, event_id=event_id)
        if not event_exists:
            return EligibilityFacts(
                event_exists=False, attended=False, speaker_on_roster=False, anchor=None
            )

        attended = (
            session.execute(
                sa.select(sa.literal(1)).where(
                    schema.attendance_record.c.tenant_id == tenant_id,
                    schema.attendance_record.c.subject_id == student_id,
                    schema.attendance_record.c.event_id == event_id,
                )
            ).first()
            is not None
        )

        return EligibilityFacts(
            event_exists=True,
            attended=attended,
            speaker_on_roster=self.speaker_on_roster(
                session,
                tenant_id=tenant_id,
                owning_unit_id=owning_unit_id,
                speaker_professional_id=speaker_professional_id,
            ),
            anchor=anchor,
        )

    def submit(
        self,
        session: Session,
        *,
        tenant_id: uuid.UUID,
        owning_unit_id: uuid.UUID,
        student_id: uuid.UUID,
        event_id: uuid.UUID,
        speaker_professional_id: uuid.UUID,
        rating: Rating,
    ) -> FeedbackWriteResult:
        """Record or amend this student's rating of this speaker, idempotently.

        Four cases, all of them successful:

        * no row — insert one at ``submitted``;
        * a ``withdrawn`` row — move it back and write the new rating, bumping
          ``updated_at`` and leaving ``submitted_at`` where it is;
        * a ``submitted`` row whose rating or comment differs — rewrite it and
          bump ``updated_at``. This is what "editable" means, and it is the same
          write as the first submission because it is the same row;
        * a ``submitted`` row that already says exactly this — write nothing at
          all, so ``updated_at`` keeps meaning "when this last moved" and a
          double-clicked Submit does not manufacture an edit.

        The caller is responsible for checking the edit window *before* calling
        this. That check needs the event's date and belongs with the worded
        refusal, and duplicating it here would give the rule two implementations
        that could disagree.

        The insert carries ``ON CONFLICT DO NOTHING`` on the natural key and the
        result is re-read. Two Submit clicks racing each other would otherwise be
        a unique violation surfacing as a ``500`` on the second click of an
        operation whose contract is that a second click is harmless.

        Args:
            session: The caller's session. **Not committed here** — and
                ``get_session`` rolls back unconditionally, so a route that
                forgets to commit stores nothing while returning a clean ``201``.
            tenant_id: The caller's tenant. In every predicate and on the row.
            owning_unit_id: The unit whose student surface this was written
                through, stored on the row (A5).
            student_id: The author, from the verified principal, never a request
                field.
            event_id: The event.
            speaker_professional_id: The speaker, by opaque id.
            rating: An already-validated :class:`Rating`. The scale is checked in
                the domain rather than here, so the bound has one home.

        Returns:
            The rating as it now stands, plus whether this call created it and
            whether it moved anything.
        """
        existing = self.get(
            session,
            tenant_id=tenant_id,
            student_id=student_id,
            event_id=event_id,
            speaker_professional_id=speaker_professional_id,
        )

        if existing is None:
            statement = (
                postgresql.insert(schema.student_speaker_feedback)
                .values(
                    id=uuid.uuid4(),
                    tenant_id=tenant_id,
                    owning_unit_id=owning_unit_id,
                    event_id=event_id,
                    student_id=student_id,
                    speaker_professional_id=speaker_professional_id,
                    status=FeedbackStatus.SUBMITTED.value,
                    rating=rating.value,
                    comment=rating.comment,
                )
                # DO NOTHING rather than DO UPDATE: under the race the other
                # transaction's row is a real submission, and the re-read below
                # reports whatever actually landed rather than overwriting it.
                .on_conflict_do_nothing(constraint="uq_student_speaker_feedback_subject")
                # RETURNING rather than `rowcount`: `ON CONFLICT DO NOTHING`
                # reports a suppressed insert through the absence of a returned
                # row, and `rowcount` is not a reliable discriminator here.
                .returning(schema.student_speaker_feedback.c.id)
            )
            inserted = session.execute(statement).first() is not None
            row = self.get(
                session,
                tenant_id=tenant_id,
                student_id=student_id,
                event_id=event_id,
                speaker_professional_id=speaker_professional_id,
            )
            return FeedbackWriteResult(row=row, created=inserted, changed=inserted)

        already_says_this = (
            existing.status == FeedbackStatus.SUBMITTED.value
            and existing.rating == rating.value
            and existing.comment == rating.comment
        )
        if already_says_this:
            return FeedbackWriteResult(row=existing, created=False, changed=False)

        session.execute(
            sa.update(schema.student_speaker_feedback)
            .where(
                schema.student_speaker_feedback.c.tenant_id == tenant_id,
                schema.student_speaker_feedback.c.student_id == student_id,
                schema.student_speaker_feedback.c.event_id == event_id,
                schema.student_speaker_feedback.c.speaker_professional_id
                == speaker_professional_id,
            )
            .values(
                status=FeedbackStatus.SUBMITTED.value,
                rating=rating.value,
                comment=rating.comment,
                updated_at=sa.func.now(),
            )
        )
        return FeedbackWriteResult(
            row=self.get(
                session,
                tenant_id=tenant_id,
                student_id=student_id,
                event_id=event_id,
                speaker_professional_id=speaker_professional_id,
            ),
            created=False,
            changed=True,
        )

    def withdraw(
        self,
        session: Session,
        *,
        tenant_id: uuid.UUID,
        student_id: uuid.UUID,
        event_id: uuid.UUID,
        speaker_professional_id: uuid.UUID,
    ) -> FeedbackWriteResult:
        """Take this student's rating back, idempotently.

        The row survives and its ``status`` moves — migration ``0031``'s central
        decision, inherited from OQ-CBA-018. Deleting would make "they withdrew"
        and "they never rated" the same absence, and would throw away the
        de-duplication key that stops the rating being cast again as a fresh one.

        **Both the rating and the comment are cleared.** A retraction that took
        back the number and left the words would be half-honoured, and the words
        are the half most likely to name somebody.

        A withdrawal with nothing to withdraw writes **no row**. Manufacturing a
        pre-withdrawn row would put one in the table for every stray click, and
        would assert that a student rated a speaker they never did.

        Note there is no ``owning_unit_id`` parameter: a withdrawal never
        inserts, so it needs no value for that column — and taking one would
        invite a caller to pass a different unit from the one on the row, which
        is a rewrite of the row's authorization scope disguised as an argument.

        Args:
            session: The caller's session. Not committed here.
            tenant_id: The caller's tenant.
            student_id: The author, from the verified principal.
            event_id: The event.
            speaker_professional_id: The speaker.

        Returns:
            The rating as it now stands — ``row=None`` when there was never one
            — plus whether this call moved anything.
        """
        existing = self.get(
            session,
            tenant_id=tenant_id,
            student_id=student_id,
            event_id=event_id,
            speaker_professional_id=speaker_professional_id,
        )

        if existing is None:
            return FeedbackWriteResult(row=None, created=False, changed=False)

        if existing.status == FeedbackStatus.WITHDRAWN.value:
            return FeedbackWriteResult(row=existing, created=False, changed=False)

        session.execute(
            sa.update(schema.student_speaker_feedback)
            .where(
                schema.student_speaker_feedback.c.tenant_id == tenant_id,
                schema.student_speaker_feedback.c.student_id == student_id,
                schema.student_speaker_feedback.c.event_id == event_id,
                schema.student_speaker_feedback.c.speaker_professional_id
                == speaker_professional_id,
            )
            .values(
                status=FeedbackStatus.WITHDRAWN.value,
                rating=None,
                comment=None,
                updated_at=sa.func.now(),
            )
        )
        return FeedbackWriteResult(
            row=self.get(
                session,
                tenant_id=tenant_id,
                student_id=student_id,
                event_id=event_id,
                speaker_professional_id=speaker_professional_id,
            ),
            created=False,
            changed=True,
        )
