"""A unit records that it is meeting the CBA team, and reads back what it recorded.

Migration ``0034``. Two routes, both unit-scoped:

* ``POST /v1/units/{unit_id}/meetings`` — record one meeting.
* ``GET  /v1/units/{unit_id}/meetings`` — this unit's meetings, bounded.

The coordinator portal's Meetings page has rendered a placeholder naming the
legacy ``/api/portals/event-coordinators/{id}/meetings`` dataset since the port,
because that backend is not in this repository. These two routes are what the
page reads instead. They are the whole of the surface.

An internal record, and nothing that sends anything
=====================================================
**There is no Google Calendar client here, no OAuth scope, no credential, and no
environment variable a later edit could point at one.** ``routers/calendar.py``
draws that boundary and this module stays inside it. G5 (Calendar API) is
deferred under the ratified
``docs/decisions/synthetic-pilot-development-authorization-2026-09-03.md`` §3,
and the deferral is about *writing into somebody's calendar on their behalf* —
which is exactly what a meeting "booking" would be if this row were one.

It is not one. A row here is a note a unit made about a meeting its own people
arranged. Nothing in this system tells an external participant that the row
exists; no message is composed, queued, or sent, and no address is read. The
difference between this module and a booking system is the dependency it does
not have.

**Why there is no per-meeting ``.ics`` download**, although the domain could
render one. ``tests/unit/test_matching_fail_closed.py`` puts ``ics``, ``invite``
and ``invite.ics`` in ``_G5_FORBIDDEN_SEGMENTS`` and admits exactly one path
through ``G5_AUTHORIZED_CALENDAR_PATHS`` —
``/v1/units/{unit_id}/events/{event_id}/invite.ics``, the single permission G5
leaves spendable. A second ``.ics`` path would require widening that allowlist,
and widening a G5 allowlist is a decision the ratified authorization reserves;
this track does not hold it. Spelling the path to slip past an exact-segment
match would be the same widening with the audit removed. So the route is not
built, and the reason is recorded here and in **OQ-CBA-066** rather than in a
silence. A coordinator who wants this meeting in their own calendar types it in,
which is what they do today.

No participants, because nobody has decided what one is
=========================================================
There is no participant field on either model below, no invitee list, and no
external-identity column behind them. What a "meeting with the CBA team" is
contractually — **who may book one, whether an external participant is a
``user_account`` or free text, and whether a booking ever leaves the system** —
is **OQ-CBA-066**, open. Each of those fields would be an answer to it shipped as
an API. The table ships the internal record; the register carries the question.

The refusal this module exists to make
========================================
A meeting with no resolved time is **refused, never defaulted**. ADR-0010 rule 2,
and migration finding **F-003**: the legacy turned an unparsed date into "thirty
days from now" and produced a confident slot nobody chose. The refusal is written
three times, at three layers, and none of them is redundant:

1. :class:`MeetingSubmission` makes ``scheduled_at`` a required field, so an
   omitted time is a ``422`` from FastAPI before any code here runs.
2. :class:`~smartmatch_persistence.meetings.MeetingRepository` raises
   :class:`~smartmatch_persistence.meetings.UnresolvedMeetingTimeError` on an
   absent or *naive* datetime — the arm nothing else covers, because a naive
   value is not null and PostgreSQL would resolve it against the session's own
   ``TimeZone``. This route catches it and answers ``422
   meeting_time_unresolved`` rather than letting it become a ``500``.
3. ``cba_meeting.scheduled_at`` is ``NOT NULL`` with no server default, which is
   what holds when a writer skips both layers above.

**No branch in this module supplies a time.** There is no fallback and no
"assume today"; the ``422`` is the whole of the handling.

Mounted under one capability: ``SPEAKER_CONTACT_MANAGEMENT``
=============================================================
Stated here because a router must ride exactly one flag and a reader is entitled
to know which, and why.

``SPEAKER_CONTACT_MANAGEMENT`` is the capability for *a Speaker Connector
maintaining their unit's own records by hand* (customer §13) — records typed in
by a person about people their institution already knows, with no network call
and nothing sent. A meeting note is that same persona doing that same kind of
by-hand record-keeping on the same portal, and a deployment that has turned the
Connector surface off has no page these routes could be opened from. That is the
argument ``main.py`` makes for mounting the student feedback routes on
``EVENT_READS``.

The two it is deliberately **not**:

* **``CONSENTED_OUTREACH``** — that flag gates putting something in somebody's
  inbox. This module sends nothing and reads no address, and mounting it there
  would make a deployment's outreach switch govern a table that cannot reach
  anybody.
* **``EVENT_READS``** — a meeting is not an ``event`` row. It is in no catalog,
  no match run, and no student agenda, and pretending otherwise would attach it
  to the funnel it deliberately stands outside of.

A reviewer may move this; it must stay one flag, and the replacement must be
stated here.

Who may call these
====================
``_MEETING_ROLES`` is ``{admin, coordinator}``, a literal. Customer §13 makes the
Connector the accountable actor for their unit's own record-keeping, and under
deny-by-default the absence of a permit is a denial rather than an invitation to
guess. ``student`` and ``volunteer`` are absent, and not merely by omission: a
unit's internal meeting schedule is operational detail about the people running
the program, and neither persona has business in it. Both routes authorize
against the *loaded unit row*, so a unit in another tenant is a ``404`` rather
than a ``403`` that would confirm the id names something real.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from typing import Annotated, Final

from fastapi import APIRouter, Path, Query, status
from pydantic import BaseModel, Field
from smartmatch_authz import OrgPath, Resource, assert_allowed
from smartmatch_persistence.meetings import (
    MeetingRepository,
    MeetingRow,
    UnresolvedMeetingTimeError,
)
from smartmatch_persistence.rate_limit import RateLimit
from sqlalchemy.orm import Session

from smartmatch_api.dependencies import CurrentPrincipal, DbSession, charge_quota
from smartmatch_api.errors import ApiError
from smartmatch_api.units import load_unit_or_404
from smartmatch_api.utils import utc_now

router = APIRouter(prefix="/v1/units", tags=["meetings"])

#: The only writer and reader of ``cba_meeting``. Module-level and stateless, the
#: arrangement ``routers/student_speaker_feedback.py`` uses for its own
#: repository.
_meetings = MeetingRepository()

#: Who may record a meeting and read the unit's list.
#:
#: A literal ``frozenset`` rather than an import of another router's, for the
#: reason ``tests/authz/test_route_roles.py`` gives about its own ledger: two role
#: sets agreeing today is not a reason a widening of one should silently widen
#: the other.
#:
#: One set for both routes, unlike the read/write split
#: ``routers/student_speaker_feedback.py`` makes — and the two authorizers below
#: are still separate. Recording a meeting and reading the unit's list are one
#: persona asking one question ("may this coordinator keep this unit's meeting
#: records"), and every cell of the authorization rectangle agrees; that is the
#: arrangement the ``cba_handoff`` pair uses. The authorizers stay distinct so
#: ``tests/authz/test_policy_matrix.py``'s ``authorizer`` column says something
#: true about each route, which is the reason that file reads it out of the
#: source.
_MEETING_ROLES: Final[frozenset[str]] = frozenset({"admin", "coordinator"})

#: The per-caller quota on meeting writes. 30 a minute is
#: ``routers/student_events.py``'s write allowance reused rather than a second
#: number invented here — far above what a person recording meetings can type,
#: which is what makes it a defence against a loop rather than against a busy
#: coordinator.
MEETING_WRITE_RATE_LIMIT: Final[RateLimit] = RateLimit(
    operation="meeting.record", max_requests=30, window=timedelta(minutes=1)
)

#: The most meetings one listing returns, and the ceiling a caller may ask for.
#:
#: A bound rather than a page cursor, deliberately: a unit holds meetings in the
#: tens, and a cursor protocol would be machinery with nothing to page through.
#: The response carries a measured ``total`` beside the rows, so a caller can
#: always tell a full page from a truncated one — ADR-0011 rule 1's distinction
#: between a measured number and an unknown one, on a small question.
MAX_MEETINGS_PER_PAGE: Final[int] = 100

#: Longest title accepted. Mirrors ``ck_cba_meeting_title_shape``; stated in both
#: places because a request model is not the last line of defence for a text
#: column.
MAX_TITLE_LENGTH: Final[int] = 200

#: Longest location or link accepted. Mirrors ``ck_cba_meeting_location_shape``.
MAX_LOCATION_LENGTH: Final[int] = 500

#: Longest IANA zone name accepted. Mirrors ``ck_cba_meeting_time_zone``.
MAX_TIME_ZONE_LENGTH: Final[int] = 64


# ---------------------------------------------------------------------------
# Request and response models
# ---------------------------------------------------------------------------


class MeetingSubmission(BaseModel):
    """What a coordinator says about one meeting.

    Four fields, and the absent ones are the design. There is no ``status``: a
    meeting recorded as already cancelled is a meeting that was never arranged,
    and migration ``0034`` keeps those two distinguishable. There is no
    ``created_by``: that comes from the verified principal, and no route here
    accepts one, so there is no request field for MM-A01's caller-selected
    identity to enter through. And there are no participants — **OQ-CBA-066**.
    """

    title: str = Field(
        min_length=1,
        max_length=MAX_TITLE_LENGTH,
        description="What the meeting is. Required and non-blank.",
    )
    scheduled_at: datetime = Field(
        description=(
            "When the meeting is, ISO-8601 **with an offset**. Required, and there "
            "is no default: a meeting with no resolved time is refused rather than "
            "given one (ADR-0010 rule 2, finding F-003). A value with no offset is "
            "a wall-clock reading rather than an instant and is refused for the "
            "same reason."
        )
    )
    time_zone: str = Field(
        min_length=1,
        max_length=MAX_TIME_ZONE_LENGTH,
        description=(
            "The IANA zone the time was agreed in, e.g. 'America/Los_Angeles'. "
            "Required, because it is the half of a wall-clock appointment the "
            "instant above cannot recover — a surface that wants to say '5pm' has "
            "to know 5pm where, and guessing is the defect one column over."
        ),
    )
    location_or_link: str | None = Field(
        default=None,
        max_length=MAX_LOCATION_LENGTH,
        description=(
            "A room, a building, or a join URL. Optional in the honest sense: "
            "absent means nobody has said yet, and a blank or whitespace-only "
            "value is normalized to absent rather than stored, so there is no "
            "third state between 'no location' and 'a location'."
        ),
    )


class MeetingView(BaseModel):
    """One meeting as its own unit sees it.

    Carries no participant field of any kind, for the module docstring's reason.
    A model with no such field cannot grow one by a later copy-paste onto a
    surface that should not have it.
    """

    id: uuid.UUID
    unit_id: uuid.UUID
    title: str
    scheduled_at: str = Field(
        description=(
            "When the meeting is, ISO-8601 with an offset. Never null and never "
            "inferred — a meeting with no time cannot be stored."
        )
    )
    time_zone: str = Field(description="The IANA zone the time was agreed in.")
    location_or_link: str | None = Field(
        default=None,
        description="Where, or how to join. Null when nobody has said yet.",
    )
    status: str = Field(
        description=(
            "'scheduled' or 'cancelled'. A cancelled meeting is listed rather than "
            "hidden: 'called off' and 'never arranged' are different facts."
        )
    )
    recorded_at: str = Field(description="When this note was made, ISO-8601.")
    updated_at: str = Field(description="When this note last moved, ISO-8601.")


class MeetingListResponse(BaseModel):
    """This unit's meetings, bounded, with a measured total beside them."""

    unit_id: uuid.UUID
    meetings: list[MeetingView]
    total: int = Field(
        description=(
            "How many meetings this unit holds, all statuses — counted in the "
            "database, not folded from the rows above. A caller comparing it to "
            "the length of `meetings` can tell a full page from a truncated one, "
            "which is the question a bounded listing otherwise leaves a client to "
            "guess at."
        )
    )
    limit: int = Field(description="The bound this listing was taken under.")


# ---------------------------------------------------------------------------
# Authorization
# ---------------------------------------------------------------------------


def _authorize_meeting_write(
    session: Session,
    principal: CurrentPrincipal,
    unit_id: uuid.UUID,
) -> None:
    """Load the unit and authorize a coordinator recording a meeting against it.

    The unit is loaded first and authorization runs against *that row's* path
    rather than anything from the request; ``load_unit_or_404`` scopes the lookup
    by the caller's own tenant, so a foreign unit is a ``404`` rather than a
    ``403`` that would confirm the id names something real.
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
        required_roles=_MEETING_ROLES,
    )


def _authorize_meeting_read(
    session: Session,
    principal: CurrentPrincipal,
    unit_id: uuid.UUID,
) -> None:
    """Load the unit and authorize a coordinator reading its meetings.

    A separate function from :func:`_authorize_meeting_write` although the role
    set is the same one, and the separation is the point rather than an accident
    of drafting: routing a read through the write authorizer would make
    ``tests/authz/test_policy_matrix.py``'s ``authorizer`` column say something
    false about this route, and the matrix reads that column out of the source
    precisely so it cannot.
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
        required_roles=_MEETING_ROLES,
    )


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _view(row: MeetingRow) -> MeetingView:
    """Render one stored meeting.

    ``scheduled_at`` is always present here, and that is a property of the table
    rather than of this function: a row with no time cannot exist, so there is no
    branch deciding what to show when it is missing. That absent branch is the
    whole benefit of refusing the write.
    """
    return MeetingView(
        id=row.id,
        unit_id=row.owning_unit_id,
        title=row.title,
        scheduled_at=row.scheduled_at.isoformat(),
        time_zone=row.time_zone,
        location_or_link=row.location_or_link,
        status=row.status,
        recorded_at=row.created_at.isoformat(),
        updated_at=row.updated_at.isoformat(),
    )


def _normalized(value: str | None) -> str | None:
    """Trim, and treat a blank as absent rather than storing it.

    ``ck_cba_meeting_location_shape`` refuses ``''`` outright, so without this a
    caller who submitted a whitespace-only location would get a ``500`` from an
    ``IntegrityError``. Normalizing to ``None`` answers what they meant — they
    did not give a location — instead of refusing a request that carried no
    actual error.
    """
    if value is None:
        return None
    trimmed = value.strip()
    return trimmed or None


def _time_unresolved(error: UnresolvedMeetingTimeError) -> ApiError:
    """The ``422`` a repository refusal becomes.

    Never a fallback. This is the whole of the handling for an unresolved time:
    the caller is told which fact is missing, and no time is supplied on their
    behalf. Substituting one here is finding F-003 reintroduced at the layer that
    was built to report it.
    """
    return ApiError(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        code="meeting_time_unresolved",
        message=str(error),
    )


# ---------------------------------------------------------------------------
# Record a meeting
# ---------------------------------------------------------------------------


@router.post(
    "/{unit_id}/meetings",
    response_model=MeetingView,
    status_code=status.HTTP_201_CREATED,
    summary="Record a meeting this unit is holding with the CBA team",
    responses={
        422: {
            "description": (
                "The request states no usable meeting time: an absent "
                "`scheduled_at`, or one carrying no UTC offset. No meeting is "
                "recorded and no time is inferred (finding F-003)."
            )
        },
    },
)
def record_meeting(
    principal: CurrentPrincipal,
    session: DbSession,
    body: MeetingSubmission,
    unit_id: Annotated[uuid.UUID, Path()],
) -> MeetingView:
    """Store one meeting note for this unit, and return it as stored.

    Every meeting is recorded as ``scheduled``; the body cannot choose a status,
    for :class:`MeetingSubmission`'s reason. ``created_by_user_id`` comes from the
    verified principal and never from the request.

    Nothing is sent. This route writes a row and returns it — no invitation, no
    message, no calendar entry anywhere but this database.

    Raises:
        403: ``forbidden`` for a caller who is not an admin or coordinator over
            this unit.
        404: ``unit_not_found`` for a unit outside the caller's tenant.
        422: ``invalid_request`` for a missing or malformed field;
            ``meeting_time_unresolved`` when the time carries no offset.
        429: over the write quota.
    """
    charge_quota(session, principal, MEETING_WRITE_RATE_LIMIT)
    _authorize_meeting_write(session, principal, unit_id)

    try:
        stored = _meetings.create(
            session,
            tenant_id=principal.tenant_id,
            owning_unit_id=unit_id,
            title=body.title.strip(),
            scheduled_at=body.scheduled_at,
            time_zone=body.time_zone.strip(),
            location_or_link=_normalized(body.location_or_link),
            # From the verified principal, never from the body. There is no
            # request field a caller could put somebody else's id in.
            created_by_user_id=principal.user_id,
        )
    except UnresolvedMeetingTimeError as error:
        raise _time_unresolved(error) from error

    # The one commit. Without it `get_session`'s unconditional rollback discards
    # the meeting and this route returns a clean 201 having stored nothing.
    session.commit()
    return _view(stored)


# ---------------------------------------------------------------------------
# Read this unit's meetings
# ---------------------------------------------------------------------------


@router.get(
    "/{unit_id}/meetings",
    response_model=MeetingListResponse,
    summary="List the meetings this unit has recorded",
)
def list_meetings(
    principal: CurrentPrincipal,
    session: DbSession,
    unit_id: Annotated[uuid.UUID, Path()],
    limit: Annotated[int, Query(ge=1, le=MAX_MEETINGS_PER_PAGE)] = MAX_MEETINGS_PER_PAGE,
) -> MeetingListResponse:
    """This unit's meetings, soonest first, with a measured total.

    Cancelled meetings are **listed, not hidden**. A surface has to render "this
    was called off" differently from "this was never arranged", and a route that
    dropped the cancelled rows would take that distinction away from the only
    caller who needs it.

    ``total`` is counted in the database rather than folded from the rows
    returned, so a client can tell a full page from a truncated one instead of
    inferring a number nobody measured.

    Raises:
        403: ``forbidden`` for a caller who is not an admin or coordinator over
            this unit.
        404: ``unit_not_found`` for a unit outside the caller's tenant.
    """
    _authorize_meeting_read(session, principal, unit_id)

    rows = _meetings.for_unit(
        session,
        tenant_id=principal.tenant_id,
        owning_unit_id=unit_id,
        limit=limit,
    )
    total = _meetings.count_for_unit(session, tenant_id=principal.tenant_id, owning_unit_id=unit_id)
    return MeetingListResponse(
        unit_id=unit_id,
        meetings=[_view(row) for row in rows],
        total=total,
        limit=limit,
    )
