"""The two student-facing event reads: the published catalog, and your own agenda.

Card ``CBA-STUDENT-EVENTS``, customer §15 ("Students should be able to browse
events ... add events to their calendar"). Two unit-scoped ``GET`` routes over
the ``event`` and ``attendance_record`` tables that already exist:

* ``GET /v1/units/{unit_id}/student/events`` — what the unit has published. See
  :func:`browse_student_events`.
* ``GET /v1/units/{unit_id}/student/agenda`` — the events *this* student is
  attached to, soonest first. See :func:`list_student_agenda`.

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

## Registration is *not* here, and the agenda says why

§15 also asks that students be able to *register* for events. There is no
registration in this schema: ``attendance_record`` is attendance — ADR-0013
makes it the only input to points, and ``uq_attendance_record_subject_event``
plus the ledger's ``attendance_credit`` shape mean a row written at
registration time would credit a student for an event they had not been to.
Writing one anyway to make a button work is the exact defect this repository
treats as worse than a missing feature.

So this card ships no registration route rather than a plausible one, the
agenda is documented as "events you are recorded as attending" rather than
labelled "registered", and the missing table is **OQ-CBA-018**. ``B06``'s
standing instruction — "New command resource; until then relabel" — is what the
UI does with that.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Annotated, Any, Final

import sqlalchemy as sa
from fastapi import APIRouter, Path
from pydantic import BaseModel, Field
from smartmatch_authz import OrgPath, Resource, assert_allowed
from smartmatch_persistence import schema
from sqlalchemy.orm import Session

from smartmatch_api.dependencies import CurrentPrincipal, DbSession
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
            "True when an attendance record ties this caller to this event. Named for "
            "what it is rather than 'registered': this deployment has no registration "
            "(OQ-CBA-018), and a field called 'registered' would claim one."
        )
    )
    calendar: StudentCalendarView


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


def _summary(
    row: Any,
    *,
    unit_id: uuid.UUID,
    on_my_agenda: bool,
    tags: list[str],
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
    attended = _attended_event_ids(
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
                on_my_agenda=row.id in attended,
                tags=terms.get(row.id, []),
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

    "Own" means ``attendance_record`` names them and the event, because that is
    the only link between a student and an event this schema has. It is
    deliberately not called *registered*: there is no registration table, and
    writing an attendance row when somebody registers would credit them under
    ADR-0013 for an event they have not been to. The gap is **OQ-CBA-018**, and
    :class:`StudentEventSummary`'s ``on_my_agenda`` is named for what the data
    supports rather than for the button a page would like to draw.

    Self-scoping is in the query. ``subject_id`` comes from the verified
    principal and appears in the ``WHERE`` clause, so there is no request field
    naming a subject and no post-filter a later edit could drop — the
    caller-selected identity shape (MM-A01) has nowhere to enter.

    Unlike the browse route this does **not** filter on ``publication_status``:
    an event a student actually attended is theirs to see on their own agenda
    whether or not the unit still publishes it, and withholding it would make
    their own history disagree with itself. Unresolved-date rows are still
    excluded — they have no position on a time-ordered list — and counted.

    Only ``student`` may read this (:func:`_authorize_student_event_read`), and
    authorization runs before any row is read.
    """
    _authorize_student_event_read(session, principal, unit_id)

    mine = (
        schema.attendance_record.c.tenant_id == principal.tenant_id,
        schema.attendance_record.c.subject_id == principal.user_id,
        schema.event.c.host_org_unit_id == unit_id,
    )
    # Composite on `tenant_id` as well as the id: the discipline
    # `routers/review.py` states for its own joins. A join on the surrogate id
    # alone would return the same rows today only because the composite foreign
    # key already forbids a cross-tenant pairing, and a read a student acts on
    # should not depend on a constraint elsewhere staying intact to be correct.
    joined = sa.join(
        schema.attendance_record,
        schema.event,
        sa.and_(
            schema.event.c.tenant_id == schema.attendance_record.c.tenant_id,
            schema.event.c.id == schema.attendance_record.c.event_id,
        ),
    )
    unresolved = schema.event.c.time_precision == _UNRESOLVED

    withheld = session.execute(
        sa.select(sa.func.count().filter(unresolved)).select_from(joined).where(*mine)
    ).scalar_one()

    listed = session.execute(
        sa.select(*_EVENT_COLUMNS)
        .select_from(joined)
        .where(*mine, ~unresolved)
        .order_by(schema.event.c.resolved_date, schema.event.c.id)
        .limit(MAX_ROWS + 1)
    ).all()

    truncated = len(listed) > MAX_ROWS
    listed = listed[:MAX_ROWS]
    terms = _mapped_terms(
        session, tenant_id=principal.tenant_id, event_ids=[row.id for row in listed]
    )

    return StudentAgendaResponse(
        unit_id=unit_id,
        events=[
            # Every row here is one the caller is recorded at — that is what the
            # join selected on — so `on_my_agenda` is true by construction rather
            # than by a second lookup that could disagree with the join.
            _summary(row, unit_id=unit_id, on_my_agenda=True, tags=terms.get(row.id, []))
            for row in listed
        ],
        withheld_unresolved_date=withheld,
        truncated=truncated,
    )
