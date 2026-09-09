"""The student event surface: the published catalog, your own agenda, and registering.

Cards ``CBA-STUDENT-EVENTS`` and ``CBA-STUDENT-REGISTRATION``, customer §15
("Students should be able to browse events, register for events ... add events
to their calendar"). Four unit-scoped routes:

* ``GET /v1/units/{unit_id}/student/events`` — what the unit has published. See
  :func:`browse_student_events`.
* ``GET /v1/units/{unit_id}/student/agenda`` — the events *this* student is
  attached to, soonest first. See :func:`list_student_agenda`.
* ``POST /v1/units/{unit_id}/student/events/{event_id}/registration`` — take a
  place. See :func:`register_for_event`.
* ``DELETE`` on that same path — give it up. See :func:`cancel_registration`.

The two reads shipped first and the two writes could not: until migration
``0026`` there was no registration table, and the section below on why says what
the obvious substitute would have cost.

## Why a student surface rather than a wider role set on the catalog

``routers/events.py`` serves the same table and is gated to ``admin`` and
``coordinator``. Adding ``student`` to that role set would have been one line
and the wrong line: its response carries ``review_status``, ``source_url``,
``fetched_at`` and ``extractor_version`` — the extraction provenance ADR-0012
keeps for a reviewer — plus the two withheld counts a coordinator needs to
audit their pipeline. None of that is a student's to read, and a response model
is not an authorization boundary. So this is a second route with its own model
holding only what §15 asks for, and the coordinator catalog is untouched.

## What "browse" is allowed to contain

``publication_status = 'published'`` and nothing else. ``ck_event_publishable``
already makes that imply a resolved date and no quarantined tag, so the two
extra predicates in the query are redundant with the constraint — deliberately,
because a student-visible listing should not depend on a CHECK elsewhere
staying intact to stay correct, which is the discipline ``routers/review.py``
states for its own joins.

The count of what is *not* shown is reported rather than dropped (ADR-0011: an
unknown is never rendered as a zero, and the corollary this response applies is
that an omission is never rendered as an absence). An empty catalog with zero
withheld means the unit has scheduled nothing; an empty catalog with nine
withheld means the unit has nine events it has not published.

## "Add to calendar", answered per event rather than per page

G8 already ships the artifact: ``routers/calendar.py`` serves
``GET /v1/units/{unit_id}/events/{event_id}/invite.ics`` and refuses with a
``409`` naming the missing fact rather than inventing a slot (finding F-003).
What it needed was a page with an ``event_id`` to point at, which is what
``docs/plans/frontend-broken-buttons.md`` B07 records as the remaining half.

This module supplies that half **without** duplicating the refusal rules and
without letting a client discover them by trying. Every item carries a
:class:`StudentCalendarView` that either holds the download path or names the
reason there is none, evaluated against the same three facts the .ics route
checks — see :data:`_CALENDAR_UNAVAILABLE_REASONS`. So a "Download .ics" button
appears only where the download actually works, which is the difference between
this and B07's original toast: the button's presence is derived from the row,
not from the page having a button-shaped space.

The path is built from :data:`INVITE_PATH_TEMPLATE`, formatted with ids the
server already holds. No route is added here, no ICS byte is produced here, and
``smartmatch_domain.calendar_invite`` is not imported here — the one .ics
surface stays the one ``tests/unit/test_calendar_invite_wiring.py`` names.

## Registration is here now, in its own table

``CBA-STUDENT-EVENTS`` shipped these two reads and refused the write, because
the schema had nowhere to put a registration and the only table that *looked*
like it would serve — ``attendance_record`` — is attendance: ADR-0013 makes it
the sole input to points, so a row written when a student signed up would credit
them for an event they had not been to, indistinguishably from a check-in.

Migration ``0026`` ends that by giving a registration its own table, and this
module grew two writes onto the same surface:

* ``POST /v1/units/{unit_id}/student/events/{event_id}/registration`` — see
  :func:`register_for_event`.
* ``DELETE /v1/units/{unit_id}/student/events/{event_id}/registration`` — see
  :func:`cancel_registration`.

``attendance_record`` is untouched by both. Nothing here writes it, consults it
to decide a write, or admits a fourth ``method``; the two tables answer two
questions, and ``on_my_agenda`` is the one place they are deliberately folded
together — see :func:`_on_my_agenda_event_ids`.

### What "on my agenda" means now, and why the field kept its name

It means **either** the student holds an active registration for the event
**or** they are recorded at it. The union is the honest reading: a student who
registered for next week's talk and a student who was scanned into last week's
both have that event on their agenda, and a page showing only one of them would
be wrong for half its rows.

The field is still called ``on_my_agenda`` rather than ``registered``. Now that
registration exists the narrower name is finally *available*, and it would still
be wrong: it would exclude the attended-but-never-registered rows that were the
whole of the agenda before this card. :class:`StudentRegistrationView` on each
item is the field that says whether this student holds a place, and it is
``null`` where they have never registered — which is a different fact from a
registration reading ``cancelled``, exactly as migration ``0026`` keeps them
different in the table.

### The .ics consequence

``routers/calendar.py`` admits a student to an event's invite when they are
attached to it, and this card widened *attached* by the same union. So a newly
registered event stops reporting ``event_not_on_your_agenda`` and starts
carrying a download path the moment its times resolve — which is the point of
registering, and is why the verdict this module reports had to become correct
rather than merely present.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta
from typing import Annotated, Any, Final

import sqlalchemy as sa
from fastapi import APIRouter, Path, Response, status
from pydantic import BaseModel, Field
from smartmatch_authz import OrgPath, Resource, assert_allowed
from smartmatch_domain.event_registration import STATUS_REGISTERED
from smartmatch_persistence import schema
from smartmatch_persistence.event_registration import (
    EventRegistrationRepository,
    RegistrationRow,
)
from smartmatch_persistence.rate_limit import RateLimit
from sqlalchemy.orm import Session

from smartmatch_api.dependencies import CurrentPrincipal, DbSession, charge_quota
from smartmatch_api.errors import ApiError
from smartmatch_api.units import load_unit_or_404
from smartmatch_api.utils import utc_now

router = APIRouter(prefix="/v1/units", tags=["student-events"])

#: Who may read either student surface. ``student`` alone.
#:
#: Customer §15 names the Student and nobody else, and under deny-by-default the
#: absence of a permit is a denial rather than an invitation to guess.
#: ``admin`` and ``coordinator`` are deliberately **not** here: they already read
#: the same events through ``routers/events.py`` with the provenance and review
#: state this surface drops, and admitting them to a narrowed copy of a route
#: they already hold would add a second answer to a question already answered.
#:
#: A literal ``frozenset`` rather than an import of ``routers/calendar.py``'s
#: ``_STUDENT_ROLES``, for the reason ``tests/authz/test_route_roles.py`` gives
#: about its own ledger: two role sets agreeing today is not a reason a widening
#: of one should silently widen the other.
_STUDENT_EVENT_ROLES: Final[frozenset[str]] = frozenset({"student"})

#: Who may register or cancel. ``student`` alone, and equal to
#: :data:`_STUDENT_EVENT_ROLES` today.
#:
#: A second literal rather than an alias of the set above, for the reason
#: ``tests/authz/test_route_roles.py`` gives about its own ledger: two role sets
#: agreeing today is not a reason a widening of one should silently widen the
#: other. The widening actually on the table makes the point — OQ-CBA-019 asks
#: whether a Connector should be able to *preview* the student surface, and an
#: answer of "yes" must not also hand them the ability to register a student for
#: something. Reads and writes are different questions even when the answer
#: happens to match.
_STUDENT_REGISTRATION_ROLES: Final[frozenset[str]] = frozenset({"student"})

#: The per-caller quota on registration writes.
#:
#: Charged on both write routes and on neither read: the two ``GET``s shipped in
#: ``CBA-STUDENT-EVENTS`` with no quota and adding one here would be a behaviour
#: change to somebody else's route smuggled in beside a feature.
#:
#: 30 a minute is ``routers/cba_contacts.py``'s write allowance, reused rather
#: than a second number invented here. It is deliberately well above what a
#: person can click: this is a defence against a loop, not against a student
#: changing their mind twice — and because both writes are idempotent, a caller
#: who hits the limit has already achieved whatever their repeated request was
#: asking for.
STUDENT_REGISTRATION_RATE_LIMIT: Final[RateLimit] = RateLimit(
    operation="student_event.registration.write", max_requests=30, window=timedelta(minutes=1)
)

#: The one writer of ``event_registration``. Module-level and stateless, the
#: arrangement ``routers/cba_contacts.py`` and ``routers/speaker_requests.py``
#: use for their own repositories.
_registrations = EventRegistrationRepository()

#: The most rows either route returns. G3 §2.2a's 200-record cap, reused rather
#: than a second number invented here — ``routers/events.py::MAX_ROWS`` and
#: ``routers/speaker_requests.py::MAX_ROWS`` are the same number for the same
#: reason. Paging is deliberately not shipped: ``truncated`` is what keeps a
#: full page from reading as a complete one.
MAX_ROWS: Final[int] = 200

#: ``event.time_precision`` an invite can be written from — the value
#: ``routers/calendar.py::_EXACT`` also names. The other two carry no instant.
_EXACT: Final[str] = "exact"

#: ``event.time_precision`` for a row whose date was never resolved (ADR-0010
#: rule 2). Excluded from both surfaces, and counted on the agenda.
_UNRESOLVED: Final[str] = "unresolved"

#: The path ``routers/calendar.py`` serves, as a template this module formats
#: and never registers. Written out once so a client is handed a link built from
#: the same string the wiring test pins, rather than one assembled inline at two
#: call sites that could drift apart.
INVITE_PATH_TEMPLATE: Final[str] = "/v1/units/{unit_id}/events/{event_id}/invite.ics"

#: Why an event carries no .ics link, in the vocabulary ``routers/calendar.py``
#: already answers ``409`` with, plus the one reason that is about the *caller*
#: rather than the event.
#:
#: Stated as constants and reported on the item so a client never has to learn a
#: refusal by attempting the download — which is the difference between a page
#: that hides a broken button and one that never renders it.
_REASON_TIME_UNRESOLVED: Final[str] = "event_time_unresolved"
_REASON_END_UNKNOWN: Final[str] = "event_end_unknown"
_REASON_NOT_YOURS: Final[str] = "event_not_on_your_agenda"

#: The three, as one tuple, so a reader sees the whole vocabulary in one place
#: and a test can assert the set rather than three scattered literals.
_CALENDAR_UNAVAILABLE_REASONS: Final[tuple[str, ...]] = (
    _REASON_TIME_UNRESOLVED,
    _REASON_END_UNKNOWN,
    _REASON_NOT_YOURS,
)


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------


class StudentEventTimeView(BaseModel):
    """An event's time at whichever precision is actually known (ADR-0010).

    The same three-fields-plus-a-discriminator shape
    ``routers/events.py::EventTimeView`` and
    ``routers/speaker_requests.py::SpeakerRequestTimeView`` use — one event
    model, one temporal contract — written out here rather than imported for the
    same reason the role set is: a narrowing or widening of a student's view
    should be a diff on this file.

    ``precision`` is never ``unresolved`` on either surface: browse lists
    published rows and ``ck_event_publishable`` makes every published one
    resolved, and the agenda excludes and counts them. It *can* be ``date_only``,
    which is precisely when there is no instant and therefore no invite.
    """

    precision: str = Field(description="exact or date_only.")
    starts_at: datetime | None = Field(
        default=None, description="The instant, present only at exact precision."
    )
    ends_at: datetime | None = Field(
        default=None,
        description=(
            "The instant it finishes, present only when the source actually stated "
            "one. Null is not a duration of zero and not a default of an hour."
        ),
    )
    on_date: date | None = Field(
        default=None, description="The calendar date, present only at date_only precision."
    )
    time_zone: str | None = Field(
        default=None,
        description="The IANA zone the event happens in — never the viewer's or the server's.",
    )


class StudentCalendarView(BaseModel):
    """Whether this student can download this event's .ics, and where from.

    Exactly one of ``download_path`` and ``unavailable_reason`` is set. That
    invariant is what makes the field usable as a render condition: a client
    shows the link when there is a path and shows the reason when there is not,
    and there is no third state in which it has to decide for itself.
    """

    available: bool = Field(
        description="True when the download below will succeed for this caller, right now."
    )
    download_path: str | None = Field(
        default=None,
        description=(
            "The exact path to request, or null. Served by the one .ics route this "
            "deployment has; this response neither produces nor duplicates it."
        ),
    )
    unavailable_reason: str | None = Field(
        default=None,
        description=(
            "Why there is no download: 'event_time_unresolved' (no start instant), "
            "'event_end_unknown' (the source stated no end, and a duration is never "
            "guessed), or 'event_not_on_your_agenda' (the .ics route admits a "
            "student only for an event they are recorded at). Null when available."
        ),
    )


class StudentRegistrationView(BaseModel):
    """This student's registration for one event, or the absence of one.

    Rendered as ``null`` on an item where no registration row exists, and as an
    object reading ``cancelled`` where one does. Those are different facts and
    migration ``0026`` keeps them different on purpose: a ``DELETE`` on cancel
    would have made "they cancelled" and "they never registered" the same
    absence, and a client that could not tell them apart would have no way to
    show a student that their cancellation had registered at all.
    """

    status: str = Field(
        description=(
            "'registered' — you hold a place — or 'cancelled'. There is no "
            "'waitlisted': no capacity exists in this deployment for one to "
            "overflow from (OQ-CBA-029)."
        )
    )
    registered_at: datetime = Field(
        description=(
            "When the place was first taken. Does not move when you cancel and "
            "register again, so it stays able to say how late a cancellation was."
        )
    )
    updated_at: datetime = Field(
        description=(
            "When the status last moved. Equal to registered_at on a registration "
            "that has never changed — and a repeated Register does not advance it, "
            "because nothing moved."
        )
    )


class StudentEventSummary(BaseModel):
    """One event as a student sees it.

    Note what is absent beside ``routers/events.py::EventSummary``:
    ``review_status``, and the whole ``provenance`` object. Those describe how
    the pipeline came by the row, which is a coordinator's question. A student
    gets what the event *is* and whether they can put it in their calendar.
    """

    id: uuid.UUID
    title: str
    description: str | None = None
    time: StudentEventTimeView
    is_virtual: bool
    location_city: str | None = None
    location_postal_code: str | None = None
    tags: list[str] = Field(description="Mapped vocabulary terms. Never a quarantined value.")
    on_my_agenda: bool = Field(
        description=(
            "True when this caller holds an active registration for this event OR is "
            "recorded at it. Still named for what it is rather than 'registered': "
            "the narrower name would exclude the attended-but-never-registered rows "
            "that made up the whole agenda before registration existed. Use the "
            "`registration` field below to ask the narrower question."
        )
    )
    registration: StudentRegistrationView | None = Field(
        default=None,
        description=(
            "Your registration for this event, or null when you have never "
            "registered. A registration you cancelled is an object reading "
            "'cancelled', not a null — the two are different facts."
        ),
    )
    calendar: StudentCalendarView


class StudentRegistrationResponse(BaseModel):
    """What a register or cancel left behind, read back out of the database.

    Deliberately not an acknowledgement. Both write routes re-read the row they
    wrote and return *that*, so a client rendering this response is rendering
    server state rather than its own optimism — the "no toast-only success" rule
    ``docs/plans/frontend-broken-buttons.md`` states, applied to the two routes
    that would most easily break it.

    That the response carries the state rather than a message is also what makes
    the idempotent cases legible: a second Register returns the same object the
    first one did, with ``updated_at`` unmoved, which is a client-visible way of
    saying nothing happened because nothing needed to.
    """

    unit_id: uuid.UUID
    event_id: uuid.UUID
    registration: StudentRegistrationView | None = Field(
        default=None,
        description=(
            "Your registration after this call. Null only from a cancel by a "
            "student who had never registered — which writes no row, because a "
            "registration nobody made is not a thing to record the cancellation of."
        ),
    )


class StudentEventListResponse(BaseModel):
    """The unit's published events, and an honest count of what is not shown."""

    unit_id: uuid.UUID
    events: list[StudentEventSummary]
    withheld_unpublished: int = Field(
        description=(
            "Events this unit holds that are not published, and so are not a "
            "student's to see. Reported rather than dropped so an empty catalog and "
            "an unpublished one are distinguishable (ADR-0011)."
        )
    )
    truncated: bool = Field(
        description="True when more published events exist than the response cap returns."
    )


class StudentAgendaResponse(BaseModel):
    """The caller's own events, soonest first.

    Self-scoped in the query, not in the response: every row is selected by
    ``attendance_record.subject_id = principal.user_id``, so there is no filter a
    later edit could drop and no id a caller could substitute.
    """

    unit_id: uuid.UUID
    events: list[StudentEventSummary]
    withheld_unresolved_date: int = Field(
        description=(
            "Events you are recorded at whose date could not be resolved (ADR-0010 "
            "rule 2). They have no place on a time-ordered agenda and are counted "
            "rather than silently dropped."
        )
    )
    truncated: bool = Field(
        description="True when more of your events exist than the response cap returns."
    )


# ---------------------------------------------------------------------------
# Authorization
# ---------------------------------------------------------------------------


def _authorize_student_event_read(
    session: Session,
    principal: CurrentPrincipal,
    unit_id: uuid.UUID,
) -> None:
    """Load the unit and authorize a student's read against it.

    One authorizer for both routes, unlike ``routers/speaker_requests.py``'s
    deliberate pair. The contrast is the thing to read: those two are split
    because §12 admits the Event Host to the create and §13 admits only the
    Speaker Connector to the queue, so one cell of the rectangle differs between
    them. These two are one persona asking one question — may this student see
    this unit's student surface — and §15 names one role for both. Two identical
    helpers would be two answers to a question asked once, and the day the two
    surfaces do diverge, the split should have to be argued in a diff rather than
    already sitting there unused.

    That the two responses differ in *content* is not a second authorization
    question: the agenda's narrowing to the caller's own rows is done by the
    query's ``subject_id`` predicate, which is a scope the policy engine has no
    concept of and could not enforce for it.

    The unit is loaded first and authorization runs against *that row's* path,
    never against a path taken from the request. ``load_unit_or_404`` scopes the
    lookup by the caller's own tenant, so a unit in another tenant is a 404
    rather than a 403 that would confirm the id names something real.

    No ``require_membership`` — :data:`_STUDENT_EVENT_ROLES` is non-empty, so
    ``evaluate`` already refuses a bare ``resource_grant`` on the required-roles
    check (S-007). No ``tenant_wide_roles`` — the metrics decision's §4 is the
    only artifact that makes anything tenant-wide and it says so of aggregate
    reads; a student reading a sibling department's catalog is not that.
    """
    unit = load_unit_or_404(session, tenant_id=principal.tenant_id, unit_id=unit_id)
    assert_allowed(
        principal.principal,
        Resource(
            resource_type="org_unit",
            resource_id=str(unit_id),
            tenant_id=str(principal.tenant_id),
            owning_unit_path=OrgPath.parse(unit.path),
        ),
        at=utc_now(),
        required_roles=_STUDENT_EVENT_ROLES,
    )


def _authorize_student_registration_write(
    session: Session,
    principal: CurrentPrincipal,
    unit_id: uuid.UUID,
) -> None:
    """Load the unit and authorize a student's registration write against it.

    A separate function from :func:`_authorize_student_event_read`, and the
    separation is the point rather than an accident of drafting. That one is
    named for what it authorizes; routing a write through it would make
    ``tests/authz/test_policy_matrix.py``'s ``authorizer`` column say something
    false about these two routes, and the matrix reads that column out of the
    source precisely so it cannot.

    :data:`_STUDENT_REGISTRATION_ROLES` is likewise its own constant even though
    it equals the read set today — see the constant for the widening that makes
    the distinction matter.

    Everything else is the read authorizer's shape, deliberately: the unit is
    loaded first and authorization runs against *that row's* path rather than
    against anything from the request, ``load_unit_or_404`` scopes the lookup by
    the caller's own tenant so a foreign unit is a ``404`` rather than a ``403``
    that would confirm the id names something real, and no
    ``require_membership`` or ``tenant_wide_roles`` is passed.

    What this function does **not** do is check that the caller is registering
    *themselves*. It could not: the policy engine has no concept of a self-scope.
    That guarantee is structural instead — both routes take ``subject_id`` from
    ``principal.user_id`` and no route accepts one in a body or a path — which is
    why there is no request field for MM-A01's caller-selected identity to enter
    through.
    """
    unit = load_unit_or_404(session, tenant_id=principal.tenant_id, unit_id=unit_id)
    assert_allowed(
        principal.principal,
        Resource(
            resource_type="org_unit",
            resource_id=str(unit_id),
            tenant_id=str(principal.tenant_id),
            owning_unit_path=OrgPath.parse(unit.path),
        ),
        at=utc_now(),
        required_roles=_STUDENT_REGISTRATION_ROLES,
    )


# ---------------------------------------------------------------------------
# Shared row rendering
# ---------------------------------------------------------------------------


def _calendar_view(
    row: Any,
    *,
    unit_id: uuid.UUID,
    on_my_agenda: bool,
) -> StudentCalendarView:
    """Decide whether this caller gets a download link for this row, and say why not.

    The order of the three tests is the order ``routers/calendar.py`` reaches
    them, so the reason reported here is the code that route would answer with —
    except for :data:`_REASON_NOT_YOURS`, which that route expresses as a ``404``
    because distinguishing "not yours" from "no such event" there would be an
    existence oracle. Here the event is already listed, so its existence is not a
    secret this field could leak; what it withholds is the *bytes*, and saying
    which is a fact the caller already has.

    Quarantined events need no arm: browse lists published rows only and
    ``ck_event_publishable`` keeps a quarantined row unpublished, and the
    agenda's rows are events the student was actually recorded at.
    """
    if not on_my_agenda:
        return StudentCalendarView(available=False, unavailable_reason=_REASON_NOT_YOURS)
    if row.time_precision != _EXACT:
        return StudentCalendarView(available=False, unavailable_reason=_REASON_TIME_UNRESOLVED)
    if row.ends_at is None:
        return StudentCalendarView(available=False, unavailable_reason=_REASON_END_UNKNOWN)
    return StudentCalendarView(
        available=True,
        download_path=INVITE_PATH_TEMPLATE.format(unit_id=unit_id, event_id=row.id),
    )


def _registration_view(row: RegistrationRow | None) -> StudentRegistrationView | None:
    """Render a registration, or ``None`` where there has never been one.

    One function so the three places that report a registration — both listings
    and both write routes — cannot disagree about what a missing row renders as.
    ``None`` in, ``null`` out: the absence is passed through rather than
    substituted with a synthetic ``cancelled``, which would erase the distinction
    migration ``0026`` keeps the row alive to preserve.
    """
    if row is None:
        return None
    return StudentRegistrationView(
        status=row.status,
        registered_at=row.registered_at,
        updated_at=row.updated_at,
    )


def _summary(
    row: Any,
    *,
    unit_id: uuid.UUID,
    on_my_agenda: bool,
    tags: list[str],
    registration: RegistrationRow | None = None,
) -> StudentEventSummary:
    """Render one event row for a student. Shared so the two surfaces cannot drift."""
    return StudentEventSummary(
        id=row.id,
        title=row.title,
        description=row.description,
        time=StudentEventTimeView(
            precision=row.time_precision,
            starts_at=row.starts_at,
            ends_at=row.ends_at,
            on_date=row.on_date,
            time_zone=row.time_zone,
        ),
        is_virtual=row.is_virtual,
        location_city=row.location_city,
        location_postal_code=row.location_postal_code,
        tags=tags,
        on_my_agenda=on_my_agenda,
        registration=_registration_view(registration),
        calendar=_calendar_view(row, unit_id=unit_id, on_my_agenda=on_my_agenda),
    )


#: The event columns both surfaces render. One tuple, so the two SELECTs agree
#: by construction rather than by two lists happening to match today.
_EVENT_COLUMNS: Final[tuple[Any, ...]] = (
    schema.event.c.id,
    schema.event.c.title,
    schema.event.c.description,
    schema.event.c.starts_at,
    schema.event.c.ends_at,
    schema.event.c.on_date,
    schema.event.c.time_zone,
    schema.event.c.time_precision,
    schema.event.c.is_virtual,
    schema.event.c.location_city,
    schema.event.c.location_postal_code,
)


def _mapped_terms(
    session: Session, *, tenant_id: uuid.UUID, event_ids: list[uuid.UUID]
) -> dict[uuid.UUID, list[str]]:
    """The mapped vocabulary terms of each listed event, in one query.

    The same read ``routers/events.py::_mapped_terms`` performs, with the same
    ``resolution = 'mapped'`` filter ADR-0012 requires: a quarantined value has
    no ``term`` to carry, so a query that forgot the predicate would still
    surface none — the filter is belt to that braces rather than the only thing
    holding.
    """
    if not event_ids:
        return {}
    rows = session.execute(
        sa.select(schema.event_tag.c.event_id, schema.event_tag.c.term)
        .where(
            schema.event_tag.c.tenant_id == tenant_id,
            schema.event_tag.c.event_id.in_(event_ids),
            schema.event_tag.c.resolution == "mapped",
        )
        .order_by(schema.event_tag.c.event_id, schema.event_tag.c.term)
    ).all()
    terms: dict[uuid.UUID, list[str]] = {}
    for row in rows:
        if row.term is not None:
            terms.setdefault(row.event_id, []).append(str(row.term))
    return terms


def _attended_event_ids(
    session: Session, *, tenant_id: uuid.UUID, subject_id: uuid.UUID, event_ids: list[uuid.UUID]
) -> set[uuid.UUID]:
    """Which of these events the caller is recorded at, in one query.

    Restricted to the ids actually being returned, so a truncated listing does
    not read attendance it will not render, and keyed on ``subject_id`` from the
    verified principal — never from anything on the request.

    This is a **read** of ``attendance_record`` and the only one in this module.
    Nothing here writes it, and the registration routes below do not consult it:
    the two tables answer two questions and the one place they meet is
    :func:`_on_my_agenda_event_ids`.
    """
    if not event_ids:
        return set()
    rows = session.execute(
        sa.select(schema.attendance_record.c.event_id).where(
            schema.attendance_record.c.tenant_id == tenant_id,
            schema.attendance_record.c.subject_id == subject_id,
            schema.attendance_record.c.event_id.in_(event_ids),
        )
    ).all()
    return {row.event_id for row in rows}


def _on_my_agenda_event_ids(
    session: Session, *, tenant_id: uuid.UUID, subject_id: uuid.UUID, event_ids: list[uuid.UUID]
) -> set[uuid.UUID]:
    """Which of these events are on the caller's agenda: registered **or** attended.

    The union, and the one place in this codebase where the two tables are folded
    into a single answer. Both halves are needed and neither implies the other: a
    student can hold a place at an event that has not happened yet, and can be
    recorded at one they never registered for — a coordinator entry or an
    imported roster, which are the two ``attendance_record.method`` values that
    have nothing to do with a student clicking anything.

    Registered means *actively* registered. A cancelled registration is a row the
    table keeps (migration ``0026``) and a place the student does not hold, so it
    contributes nothing here — which is what makes cancelling actually remove an
    event from the agenda and withdraw its ``.ics`` link, rather than merely
    annotate it.
    """
    attended = _attended_event_ids(
        session, tenant_id=tenant_id, subject_id=subject_id, event_ids=event_ids
    )
    registered = _registrations.active_event_ids(
        session, tenant_id=tenant_id, subject_id=subject_id, event_ids=event_ids
    )
    return attended | registered


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.get(
    "/{unit_id}/student/events",
    response_model=StudentEventListResponse,
    summary="Browse a unit's published events as a student",
)
def browse_student_events(
    principal: CurrentPrincipal,
    session: DbSession,
    unit_id: Annotated[uuid.UUID, Path()],
) -> StudentEventListResponse:
    """Return the unit's published events, soonest first (customer §15).

    Published only. Everything else the unit holds — an event still in review, a
    date the pipeline could not resolve, a tag value awaiting a human — is not a
    student's to see, and is counted rather than dropped so an empty catalog
    stays meaningful (:class:`StudentEventListResponse`).

    Each item says whether this caller can download its .ics and, when they
    cannot, which fact is missing — see :func:`_calendar_view`. Nothing here
    produces a calendar document; the one route that does is
    ``routers/calendar.py``.

    Only ``student`` may read this (:func:`_authorize_student_event_read`), and
    authorization runs before any event row is read.
    """
    _authorize_student_event_read(session, principal, unit_id)

    owned_by_this_unit = (
        schema.event.c.tenant_id == principal.tenant_id,
        schema.event.c.host_org_unit_id == unit_id,
    )
    # One expression, used by the count and by the listing, so there is nothing
    # for a later edit to change in one place and not the other — the rule
    # `routers/events.py` states at length for its own pair of queries.
    published = schema.event.c.publication_status == "published"

    withheld = session.execute(
        sa.select(sa.func.count().filter(~published)).where(*owned_by_this_unit)
    ).scalar_one()

    listed = session.execute(
        sa.select(*_EVENT_COLUMNS)
        .where(
            *owned_by_this_unit,
            published,
            # Redundant with `ck_event_publishable`, and stated anyway: a
            # student-visible listing should not depend on a CHECK elsewhere
            # staying intact to stay correct.
            schema.event.c.time_precision != _UNRESOLVED,
            schema.event.c.quarantined_tag_count == 0,
        )
        # Deterministic across calls: `id` breaks ties so two events on one day
        # never swap places between two identical requests, which also makes the
        # truncation below cut at a stable point rather than an arbitrary one.
        .order_by(schema.event.c.resolved_date, schema.event.c.id)
        # One more than the cap, so "exactly MAX_ROWS" and "more than MAX_ROWS"
        # are distinguishable without a second query.
        .limit(MAX_ROWS + 1)
    ).all()

    truncated = len(listed) > MAX_ROWS
    listed = listed[:MAX_ROWS]
    event_ids = [row.id for row in listed]
    terms = _mapped_terms(session, tenant_id=principal.tenant_id, event_ids=event_ids)
    on_agenda = _on_my_agenda_event_ids(
        session,
        tenant_id=principal.tenant_id,
        subject_id=principal.user_id,
        event_ids=event_ids,
    )
    # Every status, not just the active ones: an item has to be able to render
    # "you cancelled this" differently from "you have never registered", and
    # `on_agenda` above has already answered the narrower question.
    registrations = _registrations.rows_for_events(
        session,
        tenant_id=principal.tenant_id,
        subject_id=principal.user_id,
        event_ids=event_ids,
    )

    return StudentEventListResponse(
        unit_id=unit_id,
        events=[
            _summary(
                row,
                unit_id=unit_id,
                on_my_agenda=row.id in on_agenda,
                tags=terms.get(row.id, []),
                registration=registrations.get(row.id),
            )
            for row in listed
        ],
        withheld_unpublished=withheld,
        truncated=truncated,
    )


@router.get(
    "/{unit_id}/student/agenda",
    response_model=StudentAgendaResponse,
    summary="List the events this student is recorded at, soonest first",
)
def list_student_agenda(
    principal: CurrentPrincipal,
    session: DbSession,
    unit_id: Annotated[uuid.UUID, Path()],
) -> StudentAgendaResponse:
    """Return the caller's own events in this unit (customer §15, fix #10).

    "Own" means either link: an active ``event_registration`` naming them and the
    event, or an ``attendance_record`` doing the same. Before migration ``0026``
    only the second existed, which is why this list was documented as "events you
    are recorded at" and why ``on_my_agenda`` is still not called ``registered``
    — the narrower name would drop every event a student attended without ever
    clicking anything, which a coordinator entry or an imported roster produces.

    The two links stay two tables. Registering writes no ``attendance_record``:
    ADR-0013 makes attendance the only input to points, so a row written when
    somebody signs up would credit them for an event they have not been to. That
    is the refusal ``CBA-STUDENT-EVENTS`` made and migration ``0026`` ended
    properly rather than cheaply.

    Self-scoping is in the query, and now in both halves of it. ``subject_id``
    comes from the verified principal and appears in the ``WHERE`` clause of the
    attendance select *and* of the registration select, so there is no request
    field naming a subject and no post-filter a later edit could drop — the
    caller-selected identity shape (MM-A01) has nowhere to enter.

    Unlike the browse route this does **not** filter on ``publication_status``:
    an event a student attended or holds a place at is theirs to see on their own
    agenda whether or not the unit still publishes it, and withholding it would
    make their own history disagree with itself. Unresolved-date rows are still
    excluded — they have no position on a time-ordered list — and counted.

    Only ``student`` may read this (:func:`_authorize_student_event_read`), and
    authorization runs before any row is read.
    """
    _authorize_student_event_read(session, principal, unit_id)

    # The two ways an event reaches this student's agenda, as one set of ids.
    #
    # A `UNION` of two id selects rather than the outer join this route used
    # before registration existed. The join was correct when `attendance_record`
    # was the only link; with two links an outer join against both would return
    # one event row per matching side and a student who registered for an event
    # *and* was then recorded at it would see it twice, which is the kind of
    # duplicate a `DISTINCT` hides rather than prevents. `UNION` deduplicates by
    # construction, and the event columns are then selected once from `event`.
    #
    # `tenant_id` is a predicate on both halves rather than reached through the
    # join, the discipline `routers/review.py` states: a read a student acts on
    # should not depend on a composite foreign key elsewhere staying intact to be
    # correct.
    attended_ids = sa.select(schema.attendance_record.c.event_id).where(
        schema.attendance_record.c.tenant_id == principal.tenant_id,
        schema.attendance_record.c.subject_id == principal.user_id,
    )
    registered_ids = sa.select(schema.event_registration.c.event_id).where(
        schema.event_registration.c.tenant_id == principal.tenant_id,
        schema.event_registration.c.subject_id == principal.user_id,
        # Active only. A cancelled registration is a row the table keeps and a
        # place the student does not hold, so cancelling actually removes the
        # event from this list rather than annotating it.
        schema.event_registration.c.status == STATUS_REGISTERED,
    )
    mine = (
        schema.event.c.tenant_id == principal.tenant_id,
        schema.event.c.host_org_unit_id == unit_id,
        schema.event.c.id.in_(attended_ids.union(registered_ids)),
    )
    unresolved = schema.event.c.time_precision == _UNRESOLVED

    withheld = session.execute(
        sa.select(sa.func.count().filter(unresolved)).select_from(schema.event).where(*mine)
    ).scalar_one()

    listed = session.execute(
        sa.select(*_EVENT_COLUMNS)
        .where(*mine, ~unresolved)
        .order_by(schema.event.c.resolved_date, schema.event.c.id)
        .limit(MAX_ROWS + 1)
    ).all()

    truncated = len(listed) > MAX_ROWS
    listed = listed[:MAX_ROWS]
    event_ids = [row.id for row in listed]
    terms = _mapped_terms(session, tenant_id=principal.tenant_id, event_ids=event_ids)
    # Every status. A row can be on this agenda through attendance while its
    # registration reads `cancelled` — a student who withdrew and went anyway —
    # and the item should say so rather than render as never registered.
    registrations = _registrations.rows_for_events(
        session,
        tenant_id=principal.tenant_id,
        subject_id=principal.user_id,
        event_ids=event_ids,
    )

    return StudentAgendaResponse(
        unit_id=unit_id,
        events=[
            # Every row here reached the list through the union above, so
            # `on_my_agenda` is true by construction rather than by a second
            # lookup that could disagree with the query.
            _summary(
                row,
                unit_id=unit_id,
                on_my_agenda=True,
                tags=terms.get(row.id, []),
                registration=registrations.get(row.id),
            )
            for row in listed
        ],
        withheld_unresolved_date=withheld,
        truncated=truncated,
    )


# ---------------------------------------------------------------------------
# Registration writes
# ---------------------------------------------------------------------------


def _published_event_or_404(
    session: Session,
    *,
    tenant_id: uuid.UUID,
    unit_id: uuid.UUID,
    event_id: uuid.UUID,
) -> None:
    """Require that this event is one this student could have seen listed.

    The write's target is checked against the *browse* surface rather than
    against ``event`` alone, and the three predicates are the browse query's own:
    the unit hosts it, it is published, and its date resolved. A student can only
    register for something they were shown, and a route that accepted any event
    id in the tenant would let a caller register for a unit's unpublished
    programme by guessing — a listing the ``withheld_unpublished`` count exists
    precisely to keep them out of.

    A ``404`` and not a ``403``, for ``routers/calendar.py``'s reason: a denial
    distinguished from an absence is an existence oracle, and here it would leak
    which of a unit's ids are real events awaiting publication.

    Raises:
        ApiError: 404 when no such event is visible to this caller in this unit.
    """
    found = session.execute(
        sa.select(schema.event.c.id).where(
            schema.event.c.tenant_id == tenant_id,
            schema.event.c.host_org_unit_id == unit_id,
            schema.event.c.id == event_id,
            schema.event.c.publication_status == "published",
            schema.event.c.time_precision != _UNRESOLVED,
        )
    ).one_or_none()
    if found is None:
        raise ApiError(
            status_code=status.HTTP_404_NOT_FOUND,
            code="event_not_found",
            message=(
                "No published event with that id is listed for this unit. A student "
                "registers for an event they were shown; an unpublished one is not "
                "one of those."
            ),
        )


@router.post(
    "/{unit_id}/student/events/{event_id}/registration",
    status_code=status.HTTP_201_CREATED,
    response_model=StudentRegistrationResponse,
    summary="Register this student for an event",
    responses={
        200: {
            "description": (
                "You were already registered, or were returning after cancelling. "
                "Uniqueness on (tenant, subject, event) makes a second Register the "
                "same registration rather than a second one."
            )
        },
        201: {"description": "A new registration was recorded."},
    },
)
def register_for_event(
    principal: CurrentPrincipal,
    session: DbSession,
    unit_id: Annotated[uuid.UUID, Path()],
    event_id: Annotated[uuid.UUID, Path()],
    response: Response,
) -> StudentRegistrationResponse:
    """Take this student's place at this event (customer §15).

    ``201``: this has completed when it returns. The row exists, it is committed,
    and the response is read back out of it rather than echoed. ``200``: the
    registration was already there, or a cancelled one was moved back — a second
    click is the same registration, not a conflict, and the status code is how a
    caller learns which happened.

    **No request body.** There is nothing to send: the event is in the path, and
    ``subject_id`` comes from the verified principal. That absence is the
    self-scope — with no field naming a subject, MM-A01's caller-selected
    identity has nowhere to enter, and no future edit can drop a filter that was
    never a filter.

    **No ``Idempotency-Key``.** Idempotency is
    ``uq_event_registration_subject_event``, the data's own identity, which is
    the rule ``routers/speaker_requests.py`` states: a header key recognises only
    a repeat of an identical body, and a body-less request has no identity to
    repeat. Two clicks are the same registration under any phrasing.

    **Nothing is written to ``attendance_record``.** ADR-0013 makes attendance
    the only input to points; a registration is a claim about the future, and
    crediting it would pay a student for an event they had not attended.

    Quota is charged first, before the unit is loaded and before authorization
    runs (ADR-0015).

    Raises:
        ApiError: 403 when the caller may not register into this unit; 404 when
            the unit is not this tenant's, or the event is not a published event
            of this unit; 429 when the minute's quota is spent.
    """
    charge_quota(session, principal, STUDENT_REGISTRATION_RATE_LIMIT)

    _authorize_student_registration_write(session, principal, unit_id)
    _published_event_or_404(
        session, tenant_id=principal.tenant_id, unit_id=unit_id, event_id=event_id
    )

    result = _registrations.register(
        session,
        tenant_id=principal.tenant_id,
        owning_unit_id=unit_id,
        subject_id=principal.user_id,
        event_id=event_id,
    )
    # `get_session` rolls back unconditionally, so without this the route returns
    # a clean 201 having stored nothing at all.
    session.commit()

    row = _registrations.get(
        session,
        tenant_id=principal.tenant_id,
        subject_id=principal.user_id,
        event_id=event_id,
    )
    if row is None:  # pragma: no cover - the row was committed in this transaction
        raise ApiError(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            code="registration_not_readable",
            message="The registration was written but could not be read back.",
        )

    if not result.created:
        # FastAPI stamped 201 from the decorator; this call did not create
        # anything, and saying "created" of a repeat would make a second click
        # indistinguishable from a first.
        response.status_code = status.HTTP_200_OK
    return StudentRegistrationResponse(
        unit_id=unit_id, event_id=event_id, registration=_registration_view(row)
    )


@router.delete(
    "/{unit_id}/student/events/{event_id}/registration",
    response_model=StudentRegistrationResponse,
    summary="Cancel this student's registration for an event",
    responses={
        200: {
            "description": (
                "You are not registered for this event. Returned whether this call "
                "cancelled an active registration, found one already cancelled, or "
                "found none at all — the outcome the caller asked for in each case."
            )
        }
    },
)
def cancel_registration(
    principal: CurrentPrincipal,
    session: DbSession,
    unit_id: Annotated[uuid.UUID, Path()],
    event_id: Annotated[uuid.UUID, Path()],
) -> StudentRegistrationResponse:
    """Give up this student's place at this event (customer §15).

    ``DELETE`` addresses the *registration* — the caller's claim on the event —
    and after this call they hold none, which is what the verb promises them.
    What the database does is narrower and deliberate: the row survives and its
    ``status`` moves to ``cancelled``. Migration ``0026`` argues that at length,
    and the short version is that deleting would make "they cancelled" and "they
    never registered" the same absence, and would discard the ``registered_at``
    that says how late the cancellation was. The response says so rather than
    hiding it: a cancelled registration comes back as an object, not as a null.

    Idempotent in both directions a caller can reach it. Cancelling an
    already-cancelled registration writes nothing and answers ``200``; cancelling
    one that never existed writes **no row at all** and answers ``200`` with a
    ``null`` registration. Neither is an error, because in both the caller ends up
    exactly where they were asking to be — and manufacturing a pre-cancelled row
    for the second would put a row in the table for every stray click.

    Self-scoped identically to the register route: no body, ``subject_id`` from
    the principal, so this can only ever cancel the caller's own registration.

    Raises:
        ApiError: 403 when the caller may not manage registrations in this unit;
            404 when the unit is not this tenant's, or the event is not a
            published event of this unit; 429 when the minute's quota is spent.
    """
    charge_quota(session, principal, STUDENT_REGISTRATION_RATE_LIMIT)

    _authorize_student_registration_write(session, principal, unit_id)
    _published_event_or_404(
        session, tenant_id=principal.tenant_id, unit_id=unit_id, event_id=event_id
    )

    _registrations.cancel(
        session,
        tenant_id=principal.tenant_id,
        subject_id=principal.user_id,
        event_id=event_id,
    )
    session.commit()

    # Re-read after the commit rather than trusting the write result, for the
    # same reason the register route does: what the caller renders is what the
    # database holds.
    row = _registrations.get(
        session,
        tenant_id=principal.tenant_id,
        subject_id=principal.user_id,
        event_id=event_id,
    )
    return StudentRegistrationResponse(
        unit_id=unit_id, event_id=event_id, registration=_registration_view(row)
    )
