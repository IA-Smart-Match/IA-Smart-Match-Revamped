"""The one calendar artifact gate G5 permits: an .ics file, served synchronously.

The synthetic pilot development authorization (2026-09-03, §3) leaves **G5
(Calendar API)** deferred to public-release planning and permits exactly one
thing meanwhile — *ICS artifacts*. This module is that permission spent, and
nothing beyond it: one ``GET`` that hands the caller bytes.

``GET /v1/units/{unit_id}/events/{event_id}/invite.ics``

## Why a synchronous GET rather than a job

Every network action in this system is worker-side and asynchronous (G3 §9),
and the shape those take is ``POST`` a command, ``202``, poll a job. This route
is neither of those and does not want to be. It makes no network call, holds no
session past the request, and produces its whole output from a few columns of
one row that has already been read — ``smartmatch_domain.calendar_invite``
reads no clock of its own and reaches nothing outside
``smartmatch_domain.ics``. A job id, a poll loop and an artifact store to hand
back a document the request already had in hand would be machinery whose only
function is to look like the routes around it.

## No Google Calendar, and nothing that could become it

There is no client here, no OAuth scope, no credential, and no environment
variable that a later edit could point at Google. The deferral of G5 is about
the *API*: writing into somebody's calendar on their behalf. Handing a person a
file they choose to open is the thing the authorization already permits, and
the difference between the two is the difference between this module and a
dependency it does not have. See
``docs/plans/open-questions/calendar-deferred.md``.

## Three refusals, each naming what is actually missing

An event is only downloadable when the row says enough for RFC 5545 to be
written without anything being made up. Where it does not, the response is a
``409`` with a distinct code, never a plausible-looking invite:

* ``event_time_unresolved`` — ``time_precision`` is not ``exact``. ADR-0010
  rule 2 keeps such an event out of every matchable and publishable state, and
  finding **F-003** is what happens when a generator ignores that: the legacy
  turned the unparsed recurrence string "Every Tuesday" into a confident invite
  thirty days out. A ``date_only`` event is refused by the same clause and for
  the same reason — a date with no clock time becomes an instant only by
  someone choosing midnight, in some zone, on the event's behalf.
* ``event_not_presentable`` — the event carries a quarantined tag value
  (ADR-0012). ``ck_event_publishable`` refuses to publish such a row and
  ``routers/events.py`` refuses to list it; an .ics is a document handed to a
  person, which is the same act under a different name.
* ``event_end_unknown`` — ``ends_at`` is NULL, meaning the source stated no end
  (migration ``0022``). ``generate_ics`` would supply one hour;
  ``calendar_invite.build_invite_ics`` refuses to let it, because "a guessed
  duration is still a guess", and this route reports that refusal rather than
  routing around it.

The first and the last are checked here *and* enforced again inside the facade,
which raises :class:`~smartmatch_domain.ics.UnschedulableEventError` on a
``None`` endpoint. That duplication is deliberate: the check here exists to
produce a specific code for a specific caller, and the check there exists so no
caller can skip it. Neither is load-bearing alone.

## Who may download, and for which events

``admin`` and ``coordinator`` may download any presentable event in the unit —
the same role set and the same unit-scoped question ``routers/events.py``
already answers for the catalog these ids come from.

A ``student`` may download **only an event they are actually attached to**: a
row in ``attendance_record`` naming them and it. Holding a student membership
over the unit is not by itself a licence to enumerate its calendar. An event
with no such row is a ``404`` rather than a ``403`` — the same reasoning
``load_unit_or_404`` gives for a cross-tenant unit, that a denial distinguished
from an absence is an existence oracle.

``attendance_record`` is the only link between a student and an event that this
schema has; there is no registration table, so "their own events" today means
"events they attended". That is a real limitation of the read, not of the
authorization, and it is recorded as an open question rather than papered over
by widening the student's reach to the whole unit catalog.
"""

from __future__ import annotations

import uuid
from typing import Annotated, Final

import sqlalchemy as sa
from fastapi import APIRouter, Path, Response, status
from smartmatch_authz import OrgPath, Resource, assert_allowed, evaluate
from smartmatch_domain.calendar_invite import ICS_CONTENT_TYPE, build_invite_ics
from smartmatch_persistence import schema
from sqlalchemy.orm import Session

from smartmatch_api.dependencies import CurrentPrincipal, DbSession
from smartmatch_api.errors import ApiError
from smartmatch_api.units import load_unit_or_404
from smartmatch_api.utils import utc_now

router = APIRouter(prefix="/v1/units", tags=["calendar"])

#: Roles that may download any presentable event in the unit. Identical to
#: ``routers/events.py::_EVENT_ROLES`` and written out rather than imported,
#: for the reason that module gives about its own ledger: several role sets
#: agreeing today is not a reason a widening of one should silently widen the
#: others.
_COORDINATOR_ROLES: Final[frozenset[str]] = frozenset({"admin", "coordinator"})

#: The role that may download only its own events. Separate from
#: :data:`_COORDINATOR_ROLES` because the two authorize different questions:
#: this one passes the role check and then still has to prove attendance.
_STUDENT_ROLES: Final[frozenset[str]] = frozenset({"student"})

#: Every role the route admits at all. The union is stated once so the role
#: check and the two branches below cannot drift into a state where a role
#: passes the gate and then matches neither branch.
_INVITE_ROLES: Final[frozenset[str]] = _COORDINATOR_ROLES | _STUDENT_ROLES

#: The one ``event.time_precision`` an invite can be written from. The other
#: two values carry no instant — see the module docstring.
_EXACT: Final[str] = "exact"

#: UID namespace for the invites this route issues. Not a routable hostname:
#: RFC 5545 only requires global uniqueness, and ``.invalid`` (RFC 2606) cannot
#: be mistaken for a mailbox SmartMatch does not have. Distinct from the
#: domain's own default namespace because the UID below is keyed on something
#: the domain package cannot see — the database row id.
_UID_NAMESPACE: Final[str] = "events.smartmatch.invalid"


def _invite_uid(event_id: uuid.UUID) -> str:
    """The stable UID for an event's invite, keyed on the row rather than the text.

    ``generate_ics`` would otherwise derive a UID by hashing the title with the
    start instant, which is stable only while both are. Correcting a typo in a
    title would then issue a *different* UID for the same event, and every
    recipient who had already imported it would get a second entry beside the
    first rather than an update to it. The row id is the identity that survives
    a correction, so it is what the UID is built from.
    """
    return f"{event_id}@{_UID_NAMESPACE}"


def _unit_resource(principal: CurrentPrincipal, unit_id: uuid.UUID, unit_path: str) -> Resource:
    """The org-unit resource both authorization questions are asked against.

    Built from the *loaded row's* path, never from a path taken off the
    request. The two calls below have to agree about what they are
    authorizing, and the only way to guarantee that is for them to be handed
    the same value.
    """
    return Resource(
        resource_type="org_unit",
        resource_id=str(unit_id),
        tenant_id=str(principal.tenant_id),
        owning_unit_path=OrgPath.parse(unit_path),
    )


def _authorize_invite_read(
    session: Session, principal: CurrentPrincipal, unit_id: uuid.UUID
) -> bool:
    """Authorize the download, and report whether the caller reads the whole unit.

    ``evaluate`` for the second question rather than ``assert_allowed``: a
    negative answer there is not a denial, it is the branch that goes on to
    require attendance. The denial for a caller who holds no admitted role at
    all comes from the ``assert_allowed`` above it, so there is no path where
    a "no" from the second call is the only thing between the caller and the
    bytes.

    Returns:
        ``True`` when the caller may download any presentable event in the
        unit, ``False`` when they are a student who must still prove
        attendance. Returned rather than recomputed by the handler so the role
        decision is made exactly once.

    Raises:
        ApiError: 404 when the unit is not in the caller's tenant.
        AuthorizationError: 403 when the caller holds none of
            :data:`_INVITE_ROLES` over the unit.
    """
    unit = load_unit_or_404(session, tenant_id=principal.tenant_id, unit_id=unit_id)
    resource = _unit_resource(principal, unit_id, unit.path)
    at = utc_now()
    assert_allowed(principal.principal, resource, at=at, required_roles=_INVITE_ROLES)
    return evaluate(principal.principal, resource, at=at, required_roles=_COORDINATOR_ROLES).allowed


def _student_attended(
    session: Session, *, tenant_id: uuid.UUID, subject_id: uuid.UUID, event_id: uuid.UUID
) -> bool:
    """Whether an ``attendance_record`` ties this student to this event.

    ``uq_attendance_record_subject_event`` makes the triple unique, so this is
    a point lookup rather than a count, and ``tenant_id`` is in the query
    itself rather than applied afterwards — the discipline
    ``routers/review.py`` states for its own joins.
    """
    return (
        session.execute(
            sa.select(schema.attendance_record.c.id).where(
                schema.attendance_record.c.tenant_id == tenant_id,
                schema.attendance_record.c.subject_id == subject_id,
                schema.attendance_record.c.event_id == event_id,
            )
        ).first()
        is not None
    )


def _event_not_found() -> ApiError:
    """The single 404 that both "no such event" and "not your event" resolve to.

    One function so the two call sites cannot drift into two distinguishable
    responses, which is the whole point: a student who was never at an event
    learns nothing about whether it exists.
    """
    return ApiError(
        status_code=status.HTTP_404_NOT_FOUND,
        code="event_not_found",
        message="No such event in this unit.",
    )


@router.get(
    "/{unit_id}/events/{event_id}/invite.ics",
    summary="Download one event's calendar invite (.ics)",
    response_class=Response,
    responses={
        200: {
            "description": "The RFC 5545 calendar document, as UTF-8 octets.",
            "content": {"text/calendar": {"schema": {"type": "string", "format": "binary"}}},
        },
        409: {
            "description": (
                "The event states no usable time slot: an unresolved or date-only "
                "start, an unstated end, or a tag value still awaiting review. No "
                "invite is issued and nothing is inferred (finding F-003)."
            )
        },
    },
)
def download_event_invite(
    principal: CurrentPrincipal,
    session: DbSession,
    unit_id: Annotated[uuid.UUID, Path()],
    event_id: Annotated[uuid.UUID, Path()],
) -> Response:
    """Return one event's .ics bytes, or refuse and name the fact that is missing.

    Authorization runs before any event row is read, and the student branch
    runs before any of the event's content reaches a response — so a caller
    with no claim on the event learns nothing from it, including whether it
    would have been downloadable.

    The bytes come from
    :func:`smartmatch_domain.calendar_invite.build_invite_ics` and are not
    assembled here. Every RFC 5545 rule — escaping, 75-octet folding, UTC
    conversion, the deliberate absence of ``METHOD`` — lives in
    ``smartmatch_domain.ics``, and this route's whole contribution is deciding
    whether the row may be handed to it.
    """
    reads_whole_unit = _authorize_invite_read(session, principal, unit_id)

    row = session.execute(
        sa.select(
            schema.event.c.id,
            schema.event.c.title,
            schema.event.c.description,
            schema.event.c.starts_at,
            schema.event.c.ends_at,
            schema.event.c.time_precision,
            schema.event.c.quarantined_tag_count,
        ).where(
            schema.event.c.tenant_id == principal.tenant_id,
            schema.event.c.host_org_unit_id == unit_id,
            schema.event.c.id == event_id,
        )
    ).one_or_none()

    if row is None:
        raise _event_not_found()

    if not reads_whole_unit and not _student_attended(
        session,
        tenant_id=principal.tenant_id,
        subject_id=principal.user_id,
        event_id=event_id,
    ):
        raise _event_not_found()

    if row.time_precision != _EXACT:
        raise ApiError(
            status_code=status.HTTP_409_CONFLICT,
            code="event_time_unresolved",
            message=(
                "This event has no resolved start instant, so no calendar entry can "
                "be issued for it. SmartMatch does not infer a time slot."
            ),
            details={"time_precision": str(row.time_precision)},
        )

    if row.quarantined_tag_count > 0:
        raise ApiError(
            status_code=status.HTTP_409_CONFLICT,
            code="event_not_presentable",
            message=(
                "This event carries a tag value still awaiting human review, so it "
                "is not published and no calendar entry is issued for it."
            ),
        )

    if row.ends_at is None:
        raise ApiError(
            status_code=status.HTTP_409_CONFLICT,
            code="event_end_unknown",
            message=(
                "This event's source stated no end time. A calendar entry needs one, "
                "and SmartMatch does not guess a duration."
            ),
        )

    document = build_invite_ics(
        title=row.title,
        starts_at=row.starts_at,
        ends_at=row.ends_at,
        generated_at=utc_now(),
        description=row.description,
        uid=_invite_uid(row.id),
    )

    return Response(
        content=document,
        media_type=ICS_CONTENT_TYPE,
        headers={
            # The row id, never the title. A filename built from user-supplied
            # text is a header-injection and path-traversal surface, and this
            # one needs no escaping rules because there is nothing in a UUID to
            # escape.
            "Content-Disposition": f'attachment; filename="smartmatch-event-{row.id}.ics"',
            # A calendar document is derived from a row a coordinator may
            # correct at any time; a cached copy would be a stale invite that
            # looks current.
            "Cache-Control": "no-store",
        },
    )
