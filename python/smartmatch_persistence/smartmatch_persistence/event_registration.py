"""The student registration write and read path (migration ``0026``).

Card ``CBA-STUDENT-REGISTRATION``, customer §15's "register for events". This
module is the only writer of ``event_registration``, and the rules it enforces
come from :mod:`smartmatch_domain.event_registration` rather than from
statements assembled here — so "a second Register click is the same
registration" is a fact with a unit test behind it, not an incidental property
of an ``ON CONFLICT`` clause.

Idempotency is the natural key, not a header
==============================================
``uq_event_registration_subject_event`` on ``(tenant_id, subject_id, event_id)``
is what makes a resubmission the same registration. This is
``routers/speaker_requests.py``'s rule applied to a second surface: an
``Idempotency-Key`` header only recognises a repeat of the *identical body*,
while uniqueness on the data's own identity makes a second click the same act
however the request was phrased. A student's second Register is not a new
registration under any phrasing, so the weaker notion is not offered.

Both writes are therefore total. :meth:`EventRegistrationRepository.register` on
an already-registered row is a no-op that reports success;
:meth:`EventRegistrationRepository.cancel` on a row that does not exist is the
same. Neither raises, and the reason is in the domain module: an API layer
answering ``409`` to a request whose outcome is the one the caller wanted is a
worse surface than one that says "yes, you are registered".

A no-op does not move ``updated_at``
======================================
Migration ``0026`` defines ``updated_at`` as "when the status last moved", so a
write that moves nothing must not touch it. ``RegistrationTransition.changed``
is what decides, and it is why this module reads the current status before
writing rather than issuing an unconditional upsert: an
``ON CONFLICT DO UPDATE SET updated_at = now()`` would stamp a transition on
every stray double-click, and a row would then claim a return-or-withdrawal it
never had.

``registered_at`` never moves at all, including across a
cancel-then-re-register. It says when the place was first taken, which is the
only thing in this table able to say how late a cancellation was.

What this module does not do
==============================
**No commit.** Transaction boundaries belong to the caller, like every other
repository here — and on this card that is load-bearing rather than stylistic:
``get_session`` rolls back unconditionally, so a route that returns ``201``
without committing stores nothing while looking entirely successful.

**No points, ever.** There is no import of
:mod:`smartmatch_persistence.attendance` here, no write to
``attendance_record``, and no read of ``point_ledger_entry``. ADR-0013 makes
attendance the only input to points; a registration is a statement about the
future, and the whole reason migration ``0026`` exists is that writing one into
the attendance table would credit a student for an event they had not been to.

**No authorization.** Every method takes ``tenant_id`` and ``subject_id`` as
arguments and filters on both; who may supply them is
``routers/student_events.py``'s question, and the answer there is that
``subject_id`` comes from the verified principal and never from a request.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime

import sqlalchemy as sa
from smartmatch_domain.event_registration import (
    STATUS_REGISTERED,
    cancelling,
    is_active,
    registering,
)
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Session

from smartmatch_persistence import schema

__all__ = [
    "EventRegistrationRepository",
    "RegistrationRow",
    "RegistrationWriteResult",
]


@dataclass(frozen=True, slots=True)
class RegistrationRow:
    """One ``event_registration`` row as a reader sees it.

    Attributes:
        id: The registration's surrogate key.
        event_id: The event a place was taken at.
        subject_id: The student. Always the caller's own on every path this
            repository is used from.
        status: ``registered`` or ``cancelled`` — never absent, because a row
            exists precisely when the student has said something about this
            event.
        registered_at: When the place was first taken. Does not move.
        updated_at: When ``status`` last moved. Equal to ``registered_at`` on a
            registration that has never changed.
    """

    id: uuid.UUID
    event_id: uuid.UUID
    subject_id: uuid.UUID
    status: str
    registered_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class RegistrationWriteResult:
    """What one register or cancel did.

    Attributes:
        row: The registration as it stands after the call, read back out of the
            database rather than constructed here — ``registered_at`` and
            ``updated_at`` are server-defaulted, so a locally built value would
            be this module's guess at what PostgreSQL wrote. ``None`` only from
            :meth:`EventRegistrationRepository.cancel` on a student who never
            registered, which writes no row at all.
        created: ``True`` only when this call inserted a row. A re-registration
            that moved a cancelled row back is not a creation: uniqueness on
            ``(tenant_id, subject_id, event_id)`` means there is one row per
            student per event and it is still the same one.
        changed: ``True`` when the status moved. ``False`` for a repeated
            register, a repeated cancel, and a cancel with nothing to cancel.
            This is the flag that keeps a response from claiming a transition
            that did not happen.
    """

    row: RegistrationRow | None
    created: bool
    changed: bool


#: The columns :class:`RegistrationRow` is built from, in its own field order.
#: One tuple rather than a repeated ``select`` list, the discipline
#: ``cba_contacts._PROFILE_COLUMNS`` states: a column added to the row type and
#: forgotten in one of the readers is impossible by construction.
_REGISTRATION_COLUMNS = (
    schema.event_registration.c.id,
    schema.event_registration.c.event_id,
    schema.event_registration.c.subject_id,
    schema.event_registration.c.status,
    schema.event_registration.c.registered_at,
    schema.event_registration.c.updated_at,
)


def _row(record: sa.Row) -> RegistrationRow:
    """Build the read model from a row selected through :data:`_REGISTRATION_COLUMNS`."""
    return RegistrationRow(
        id=record.id,
        event_id=record.event_id,
        subject_id=record.subject_id,
        status=record.status,
        registered_at=record.registered_at,
        updated_at=record.updated_at,
    )


class EventRegistrationRepository:
    """Reads and writes ``event_registration``.

    Takes a session per call and commits nothing, like every other repository in
    this package.
    """

    def get(
        self,
        session: Session,
        *,
        tenant_id: uuid.UUID,
        subject_id: uuid.UUID,
        event_id: uuid.UUID,
    ) -> RegistrationRow | None:
        """This student's registration for this event, whatever its status.

        ``None`` means they have never registered — which is a different fact
        from a row reading ``cancelled``, and keeping the two distinguishable is
        why migration ``0026`` refuses to model a cancellation as a ``DELETE``.

        ``tenant_id`` is in the ``WHERE`` clause rather than applied afterwards,
        the discipline ``routers/review.py`` states for its own joins, and the
        triple is ``uq_event_registration_subject_event`` — so this is a point
        lookup rather than a scan.
        """
        record = session.execute(
            sa.select(*_REGISTRATION_COLUMNS).where(
                schema.event_registration.c.tenant_id == tenant_id,
                schema.event_registration.c.subject_id == subject_id,
                schema.event_registration.c.event_id == event_id,
            )
        ).one_or_none()
        return None if record is None else _row(record)

    def rows_for_events(
        self,
        session: Session,
        *,
        tenant_id: uuid.UUID,
        subject_id: uuid.UUID,
        event_ids: list[uuid.UUID],
    ) -> dict[uuid.UUID, RegistrationRow]:
        """This student's registrations among these events, keyed by event, in one query.

        Restricted to the ids actually being rendered, so a truncated listing
        does not read registrations it will not show — the same narrowing
        ``routers/student_events.py``'s attendance lookup performs.

        **Every status is returned, including ``cancelled``**, and the caller
        narrows. That is the opposite of the obvious design and it is deliberate:
        a listing has to render "you cancelled this" differently from "you never
        registered", so a reader that dropped cancelled rows would force the one
        caller who needs the distinction to issue a second query for the rows the
        first one deliberately hid. :func:`is_active` is how a caller asks the
        narrower question, and it is one call rather than a second round trip.

        Keyed by ``event_id`` rather than returned as a list because
        ``uq_event_registration_subject_event`` makes that key unique for a fixed
        student — the mapping cannot lose a row, and building it here saves every
        caller writing the same fold.
        """
        if not event_ids:
            return {}
        records = session.execute(
            sa.select(*_REGISTRATION_COLUMNS).where(
                schema.event_registration.c.tenant_id == tenant_id,
                schema.event_registration.c.subject_id == subject_id,
                schema.event_registration.c.event_id.in_(event_ids),
            )
        ).all()
        return {record.event_id: _row(record) for record in records}

    def active_event_ids(
        self,
        session: Session,
        *,
        tenant_id: uuid.UUID,
        subject_id: uuid.UUID,
        event_ids: list[uuid.UUID],
    ) -> set[uuid.UUID]:
        """Which of these events the caller currently holds a place at.

        The narrowed form of :meth:`rows_for_events`, filtered in the database
        rather than in Python because a caller that only wants the set should not
        pay to transport the cancelled rows it is about to discard.
        """
        if not event_ids:
            return set()
        rows = session.execute(
            sa.select(schema.event_registration.c.event_id).where(
                schema.event_registration.c.tenant_id == tenant_id,
                schema.event_registration.c.subject_id == subject_id,
                schema.event_registration.c.event_id.in_(event_ids),
                schema.event_registration.c.status == STATUS_REGISTERED,
            )
        ).all()
        return {row.event_id for row in rows}

    def is_registered(
        self,
        session: Session,
        *,
        tenant_id: uuid.UUID,
        subject_id: uuid.UUID,
        event_id: uuid.UUID,
    ) -> bool:
        """Whether this student currently holds a place at this one event.

        The single-event form of :meth:`active_event_ids`, for the ``.ics``
        route, which is asked about one event and should not build a list to
        answer.
        """
        row = self.get(session, tenant_id=tenant_id, subject_id=subject_id, event_id=event_id)
        return is_active(None if row is None else row.status)

    def register(
        self,
        session: Session,
        *,
        tenant_id: uuid.UUID,
        owning_unit_id: uuid.UUID,
        subject_id: uuid.UUID,
        event_id: uuid.UUID,
    ) -> RegistrationWriteResult:
        """Take this student's place at this event, idempotently.

        Three cases, all of them successful, decided by
        :func:`smartmatch_domain.event_registration.registering` rather than by
        the shape of a statement here:

        * no row — insert one at ``registered``;
        * a ``cancelled`` row — move it back, bumping ``updated_at`` and leaving
          ``registered_at`` where it is;
        * a ``registered`` row — write nothing at all, so ``updated_at`` keeps
          saying when the status last actually moved.

        The insert carries ``ON CONFLICT DO NOTHING`` on the natural key and the
        result is re-read afterwards. That is not belt-and-braces: two Register
        clicks racing each other would otherwise be a unique-violation
        ``IntegrityError`` surfacing as a ``500`` on the *second* click of an
        operation whose entire contract is that a second click is harmless.

        Args:
            session: The caller's session. **Not committed here** — and
                ``get_session`` rolls back unconditionally, so a route that
                forgets to commit stores nothing while returning a clean ``201``.
            tenant_id: The caller's tenant. In every predicate and on the row.
            owning_unit_id: The unit whose student surface this was made
                through, stored on the row (A5) rather than joined back through
                ``event.host_org_unit_id`` later.
            subject_id: The student. From the verified principal, never a
                request field.
            event_id: The event.

        Returns:
            The registration as it now stands, plus whether this call created it
            and whether it moved anything.
        """
        existing = self.get(session, tenant_id=tenant_id, subject_id=subject_id, event_id=event_id)
        transition = registering(None if existing is None else existing.status)

        if existing is None:
            statement = (
                postgresql.insert(schema.event_registration)
                .values(
                    id=uuid.uuid4(),
                    tenant_id=tenant_id,
                    owning_unit_id=owning_unit_id,
                    subject_id=subject_id,
                    event_id=event_id,
                    status=transition.status,
                )
                # The race described above. DO NOTHING rather than DO UPDATE:
                # the row the other transaction inserted already says
                # `registered`, so there is nothing this call would change, and
                # an update would move `updated_at` for a transition that
                # happened once and is being reported twice.
                .on_conflict_do_nothing(constraint="uq_event_registration_subject_event")
            )
            inserted = session.execute(statement).rowcount == 1
            row = self.get(session, tenant_id=tenant_id, subject_id=subject_id, event_id=event_id)
            return RegistrationWriteResult(
                row=row,
                # `inserted` and not `transition.created`: under the race the
                # domain's answer was computed from a `None` that is no longer
                # true, and reporting a creation this call did not perform would
                # make one of the two concurrent clicks lie about what it did.
                created=inserted,
                changed=inserted,
            )

        if transition.changed:
            session.execute(
                sa.update(schema.event_registration)
                .where(
                    schema.event_registration.c.tenant_id == tenant_id,
                    schema.event_registration.c.subject_id == subject_id,
                    schema.event_registration.c.event_id == event_id,
                )
                .values(status=transition.status, updated_at=sa.func.now())
            )
            return RegistrationWriteResult(
                row=self.get(
                    session, tenant_id=tenant_id, subject_id=subject_id, event_id=event_id
                ),
                created=False,
                changed=True,
            )

        # Already registered. No statement is issued at all, which is the point:
        # `updated_at` must keep meaning "when the status last moved".
        return RegistrationWriteResult(row=existing, created=False, changed=False)

    def cancel(
        self,
        session: Session,
        *,
        tenant_id: uuid.UUID,
        subject_id: uuid.UUID,
        event_id: uuid.UUID,
    ) -> RegistrationWriteResult:
        """Give up this student's place, idempotently.

        The row survives and its ``status`` moves — migration ``0026``'s central
        decision. Deleting would make "they cancelled" and "they never
        registered" the same absence, and would throw away the ``registered_at``
        that says how late the cancellation was.

        A cancel with nothing to cancel writes **no row**. The domain's
        :func:`~smartmatch_domain.event_registration.cancelling` reports
        ``cancelled`` for that case because that is the state the caller should
        render, and ``created=False`` is the flag saying it must not be inserted:
        a student who never registered has no registration, and manufacturing a
        pre-cancelled row would put one in the table for every stray click.

        Note there is no ``owning_unit_id`` parameter. A cancel never inserts, so
        it never needs a value for that column — and taking one would invite a
        caller to pass a *different* unit from the one on the row, which is a
        rewrite of the row's authorization scope disguised as an argument.

        Args:
            session: The caller's session. Not committed here.
            tenant_id: The caller's tenant.
            subject_id: The student, from the verified principal.
            event_id: The event.

        Returns:
            The registration as it now stands — ``row=None`` when there was
            never one — plus whether this call moved anything.
        """
        existing = self.get(session, tenant_id=tenant_id, subject_id=subject_id, event_id=event_id)

        if existing is None:
            return RegistrationWriteResult(row=None, created=False, changed=False)

        transition = cancelling(existing.status)
        if not transition.changed:
            return RegistrationWriteResult(row=existing, created=False, changed=False)

        session.execute(
            sa.update(schema.event_registration)
            .where(
                schema.event_registration.c.tenant_id == tenant_id,
                schema.event_registration.c.subject_id == subject_id,
                schema.event_registration.c.event_id == event_id,
            )
            .values(status=transition.status, updated_at=sa.func.now())
        )
        return RegistrationWriteResult(
            row=self.get(session, tenant_id=tenant_id, subject_id=subject_id, event_id=event_id),
            created=False,
            changed=True,
        )
