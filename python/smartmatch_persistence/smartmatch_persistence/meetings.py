"""The internal CBA meeting record's write and read path (migration ``0034``).

This module is the only writer of ``cba_meeting``. A row is one unit's note that
a meeting with the CBA team is happening: a title, an instant, the zone that
instant was agreed in, optionally where, and who recorded it.

An unresolved time is refused here too, and that is not redundant
====================================================================
:meth:`MeetingRepository.create` takes ``scheduled_at`` as a required,
timezone-**aware** ``datetime`` and raises :class:`UnresolvedMeetingTimeError` on
a naive one before any statement is built.

The column is already ``NOT NULL`` with no server default (migration ``0034``),
so the database would refuse the row regardless. The check is here anyway for the
reason ``routers/calendar.py`` gives about its own duplicated refusal: the two
exist for different callers. The database's refusal is what holds when a writer
skips this module; this one exists so the failure is a named exception a route
can turn into a worded ``422`` rather than an ``IntegrityError`` that surfaces as
a ``500``.

The naive-datetime arm is the one that earns its place. A ``NOT NULL`` column
cannot see the difference between ``2026-09-15 17:00+00:00`` and
``2026-09-15 17:00`` — it stores both — and PostgreSQL resolves the second using
the *session's* ``TimeZone`` setting, so the instant a meeting is recorded at
would depend on which connection wrote it. That is migration finding **F-003**'s
shape: an instant nobody chose, arrived at by a default nobody stated. ADR-0010
rule 2 is the rule, and :mod:`smartmatch_domain.ics` already refuses naive
datetimes for exactly this reason (``_require_aware``); this module refuses them
at the boundary so the refusal happens before the row exists rather than after.

**Nothing in this module supplies a time.** There is no fallback, no
``now() + timedelta``, and no parameter default on ``scheduled_at``. A caller
without an instant gets an exception.

What this module does not do
==============================
**No commit.** Transaction boundaries belong to the caller, like every other
repository here — and ``get_session`` rolls back unconditionally, so a route that
returns ``201`` without committing stores nothing while looking entirely
successful.

**No authorization.** Every method takes ``tenant_id`` and ``owning_unit_id`` and
filters on both; who may supply them is the router's question.

**No calendar, and nothing that could become one.** This module writes a row and
reads rows back. It sends nothing, invites nobody, and imports no client. G5
(Calendar API) stays deferred under the ratified synthetic-pilot development
authorization, and ``routers/calendar.py``'s docstring draws the boundary: "There
is no client here, no OAuth scope, no credential, and no environment variable
that a later edit could point at Google." The same is true here.

**No participants.** There is no participant column, no invitee list, and no
external-identity field, because what a "meeting with the CBA team" is
contractually — who may book one, whether an external participant is a
``user_account`` or free text, and whether a booking ever leaves the system — is
**OQ-CBA-066**, open. Each of those columns would be an answer to it. The
register carries the question; this module carries the internal record.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Final

import sqlalchemy as sa
from sqlalchemy.orm import Session

from smartmatch_persistence import schema

__all__ = [
    "MEETING_STATUSES",
    "MEETING_STATUS_CANCELLED",
    "MEETING_STATUS_SCHEDULED",
    "MeetingRepository",
    "MeetingRow",
    "UnresolvedMeetingTimeError",
]

#: A meeting that is on. The only status :meth:`MeetingRepository.create` writes.
MEETING_STATUS_SCHEDULED: Final[str] = "scheduled"

#: A meeting that was arranged and called off. Reachable only as a transition,
#: never as an initial state and never as a ``DELETE`` — OQ-CBA-018 settled that
#: shape for ``event_registration`` and the reasons carry: "cancelled" and "never
#: arranged" are different facts about a unit's own history.
MEETING_STATUS_CANCELLED: Final[str] = "cancelled"

#: The whole vocabulary, mirroring ``ck_cba_meeting_status``. Stated here so a
#: caller can validate before writing and get a worded refusal, rather than an
#: ``IntegrityError`` the database raised for the same reason.
MEETING_STATUSES: Final[frozenset[str]] = frozenset(
    {MEETING_STATUS_SCHEDULED, MEETING_STATUS_CANCELLED}
)


class UnresolvedMeetingTimeError(ValueError):
    """Raised when a meeting is offered without an unambiguously resolved instant.

    The module docstring carries the argument. In short: ADR-0010 rule 2 and
    migration finding F-003. A meeting with no resolved time is refused, never
    defaulted — the legacy fabricated "thirty days from now" out of an unparsed
    date and produced a slot nobody chose.

    Callers must surface this as an explicit refusal naming the missing field.
    **Do not handle it by substituting a time**, which is the defect it exists to
    report. :class:`smartmatch_domain.ics.UnschedulableEventError` is the same
    rule stated one layer down, for the same reason.
    """


@dataclass(frozen=True, slots=True)
class MeetingRow:
    """One ``cba_meeting`` row as a unit's own coordinator sees it.

    Attributes:
        id: The meeting's surrogate key.
        owning_unit_id: The unit whose surface recorded it, and the unit a read
            of it is authorized against. Carried so a caller holding a row does
            not have to remember which unit it asked about.
        title: What the meeting is. Never blank — ``ck_cba_meeting_title_shape``
            refuses ``''``, so this is a real string or the row does not exist.
        scheduled_at: When the meeting is. Always present and always aware:
            ``timestamptz``, ``NOT NULL``, no server default. There is no state
            of this dataclass in which the time is unknown, which is the whole
            point — a reader never has to decide what to render for a meeting
            with no time, because such a row cannot be stored.
        time_zone: The IANA zone the instant above was agreed in. Not derivable
            from ``scheduled_at``, which is why it is a column: a rendering that
            wants to say "5pm" needs to know 5pm *where*.
        location_or_link: A room, a building, or a URL. ``None`` means nobody has
            said yet — a real state, distinct from ``''``, which the database
            refuses.
        status: ``scheduled`` or ``cancelled``.
        created_by_user_id: Who recorded it. Provenance; OQ-CBA-008 (provenance,
            no history) is why there is no revision trail beside it.
        created_at: When the note was made.
        updated_at: When the note last moved. Three distinct instants live on
            this row — when it was recorded, when it last changed, and when the
            meeting is — and collapsing any two would lose a question somebody
            asks.
    """

    id: uuid.UUID
    owning_unit_id: uuid.UUID
    title: str
    scheduled_at: datetime
    time_zone: str
    location_or_link: str | None
    status: str
    created_by_user_id: uuid.UUID
    created_at: datetime
    updated_at: datetime


#: The columns :class:`MeetingRow` is built from, in its own field order. One
#: tuple rather than a repeated ``select`` list, the discipline
#: ``event_registration._REGISTRATION_COLUMNS`` states: a column added to the row
#: type and forgotten in one of the readers is impossible by construction.
_MEETING_COLUMNS = (
    schema.cba_meeting.c.id,
    schema.cba_meeting.c.owning_unit_id,
    schema.cba_meeting.c.title,
    schema.cba_meeting.c.scheduled_at,
    schema.cba_meeting.c.time_zone,
    schema.cba_meeting.c.location_or_link,
    schema.cba_meeting.c.status,
    schema.cba_meeting.c.created_by_user_id,
    schema.cba_meeting.c.created_at,
    schema.cba_meeting.c.updated_at,
)


def _row(record: sa.Row[Any]) -> MeetingRow:
    """Build the read model from a row selected through :data:`_MEETING_COLUMNS`."""
    return MeetingRow(
        id=record.id,
        owning_unit_id=record.owning_unit_id,
        title=record.title,
        scheduled_at=record.scheduled_at,
        time_zone=record.time_zone,
        location_or_link=record.location_or_link,
        status=record.status,
        created_by_user_id=record.created_by_user_id,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


def _require_resolved(scheduled_at: datetime | None) -> datetime:
    """Return the instant, or refuse — the one place this module inspects a time.

    Two arms, and both are the same rule:

    * ``None`` — the caller has no time. There is no branch below that supplies
      one.
    * naive — the caller has a wall-clock reading and no zone, which is not an
      instant. PostgreSQL would resolve it against the session's ``TimeZone``,
      making the stored instant depend on which connection did the writing.

    Raises:
        UnresolvedMeetingTimeError: in both cases, naming which one it was.
    """
    if scheduled_at is None:
        raise UnresolvedMeetingTimeError(
            "A meeting must name the instant it happens at. There is no default: "
            "ADR-0010 rule 2 and finding F-003."
        )
    if scheduled_at.tzinfo is None or scheduled_at.tzinfo.utcoffset(scheduled_at) is None:
        raise UnresolvedMeetingTimeError(
            "scheduled_at must be timezone-aware. A naive datetime is a wall-clock "
            "reading, not an instant, and resolving one would pick a zone on the "
            "unit's behalf."
        )
    return scheduled_at


class MeetingRepository:
    """Reads and writes ``cba_meeting``.

    Takes a session per call and commits nothing, like every other repository in
    this package.
    """

    def create(
        self,
        session: Session,
        *,
        tenant_id: uuid.UUID,
        owning_unit_id: uuid.UUID,
        title: str,
        scheduled_at: datetime | None,
        time_zone: str,
        location_or_link: str | None,
        created_by_user_id: uuid.UUID,
    ) -> MeetingRow:
        """Record one meeting, and read it back.

        Every meeting starts ``scheduled``. There is no ``status`` parameter: a
        record created as ``cancelled`` would be a meeting that was never
        arranged, which is the state migration ``0034`` keeps distinguishable
        from one that was.

        ``scheduled_at`` is declared ``datetime | None`` rather than ``datetime``
        **on purpose**, and it has no default. The ``None`` is admitted into the
        signature so :func:`_require_resolved` can refuse it *by name*, in this
        module, with an exception a route turns into a worded ``422``. Typing it
        as non-optional would push a caller's missing time into a type error at
        one call site and an unchecked ``None`` at the next, and would leave the
        naive-datetime arm — the one a type annotation cannot express at all —
        with nowhere to live.

        Args:
            tenant_id: The caller's own tenant, from the verified principal.
            owning_unit_id: The unit recording the meeting.
            title: What the meeting is. Non-blank; the database refuses ``''``.
            scheduled_at: When it is. Required and timezone-aware.
            time_zone: The IANA zone the instant was agreed in. Non-blank.
            location_or_link: A room or a URL, or ``None`` when nobody has said.
            created_by_user_id: Who recorded it, from the verified principal.

        Returns:
            The meeting as stored, read back rather than constructed here —
            ``created_at`` and ``updated_at`` are server-defaulted, so a locally
            built value would be this module's guess at what PostgreSQL wrote.

        Raises:
            UnresolvedMeetingTimeError: when ``scheduled_at`` is absent or naive.
                **Do not handle this by supplying a time.**
        """
        resolved_at = _require_resolved(scheduled_at)
        meeting_id = uuid.uuid4()

        session.execute(
            sa.insert(schema.cba_meeting).values(
                id=meeting_id,
                tenant_id=tenant_id,
                owning_unit_id=owning_unit_id,
                title=title,
                scheduled_at=resolved_at,
                time_zone=time_zone,
                location_or_link=location_or_link,
                status=MEETING_STATUS_SCHEDULED,
                created_by_user_id=created_by_user_id,
            )
        )

        stored = self.get(session, tenant_id=tenant_id, meeting_id=meeting_id)
        if stored is None:  # pragma: no cover - the insert above just succeeded
            raise RuntimeError("the meeting could not be read back after writing")
        return stored

    def get(
        self,
        session: Session,
        *,
        tenant_id: uuid.UUID,
        meeting_id: uuid.UUID,
    ) -> MeetingRow | None:
        """One meeting by id, scoped to the tenant.

        ``tenant_id`` is in the ``WHERE`` clause rather than applied afterwards —
        the discipline ``routers/review.py`` states for its own joins — so a
        meeting belonging to another tenant is *absent* here rather than fetched
        and then discarded by a caller who might forget to.

        The unit is deliberately **not** a parameter. A caller that has already
        authorized against a unit narrows with :meth:`for_unit`; this method
        answers "does this tenant hold this row", and a caller comparing
        :attr:`MeetingRow.owning_unit_id` afterwards can tell a wrong-unit id
        from an absent one, which a combined lookup could not.
        """
        record = session.execute(
            sa.select(*_MEETING_COLUMNS).where(
                schema.cba_meeting.c.tenant_id == tenant_id,
                schema.cba_meeting.c.id == meeting_id,
            )
        ).one_or_none()
        return None if record is None else _row(record)

    def for_unit(
        self,
        session: Session,
        *,
        tenant_id: uuid.UUID,
        owning_unit_id: uuid.UUID,
        limit: int,
    ) -> list[MeetingRow]:
        """This unit's meetings, soonest first, bounded by ``limit``.

        **Every status is returned, including ``cancelled``**, and the caller
        narrows. That is the opposite of the obvious design and it is deliberate,
        for ``event_registration.rows_for_events``'s reason: a listing has to
        render "this was called off" differently from "this was never arranged",
        so a reader that dropped cancelled rows would force the one caller who
        needs the distinction to issue a second query for rows the first
        deliberately hid.

        ``limit`` is required rather than defaulted. A default here would be this
        module's opinion about how much a page should render, applied to every
        caller that forgot to say — and the caller that forgot is exactly the one
        that would then read a unit's entire history into memory. The ordering
        matches ``ix_cba_meeting_unit_schedule``, so this is an index scan rather
        than a sort over that history.

        Args:
            tenant_id: The caller's own tenant, from the verified principal.
            owning_unit_id: The unit whose meetings these are.
            limit: The most rows to return. Must be positive.

        Raises:
            ValueError: when ``limit`` is not positive. A ``limit`` of zero would
                return an empty list indistinguishable from "this unit has no
                meetings", which is a different and false statement.
        """
        if limit <= 0:
            raise ValueError("limit must be positive")
        records = session.execute(
            sa.select(*_MEETING_COLUMNS)
            .where(
                schema.cba_meeting.c.tenant_id == tenant_id,
                schema.cba_meeting.c.owning_unit_id == owning_unit_id,
            )
            .order_by(
                schema.cba_meeting.c.scheduled_at.asc(),
                # A deterministic tie-break. Two meetings at the same instant are
                # ordinary — a unit can hold two calls at 5pm — and without this
                # the pair's order would be whatever the scan returned, so two
                # identical requests could render them differently.
                schema.cba_meeting.c.id.asc(),
            )
            .limit(limit)
        ).all()
        return [_row(record) for record in records]

    def count_for_unit(
        self,
        session: Session,
        *,
        tenant_id: uuid.UUID,
        owning_unit_id: uuid.UUID,
    ) -> int:
        """How many meetings this unit holds, all statuses.

        Exists so a bounded listing can say whether it is showing everything.
        Without it, a caller rendering :meth:`for_unit`'s ``limit`` rows cannot
        tell a unit with exactly that many meetings from one with more, and would
        have to either claim a total it did not measure or say nothing —
        ADR-0011 rule 1's distinction between a measured number and an unknown
        one, on a much smaller question.
        """
        return int(
            session.execute(
                sa.select(sa.func.count())
                .select_from(schema.cba_meeting)
                .where(
                    schema.cba_meeting.c.tenant_id == tenant_id,
                    schema.cba_meeting.c.owning_unit_id == owning_unit_id,
                )
            ).scalar_one()
        )
