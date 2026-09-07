"""The coordinator's attendance write — the one route that creates evidence.

One operation:

* ``POST /v1/units/{unit_id}/events/{event_id}/attendance`` — record that one
  account was present at one of this unit's events, and credit the points
  ADR-0013 derives from that. See :func:`record_attendance`.

## The prohibition this route reverses, and on whose authority

``smartmatch_persistence/attendance.py`` used to close its own docstring with
"no route imports this repository, and none may", and
``docs/plans/open-questions/pipeline-stage-writers-deferred.md`` carried the
reason as **OQ-102**: ``attendance_record`` is the only input to points, so
whatever writes it is also what mints student rewards, and the tolerance for a
wrong row is a program decision rather than a technical one. That decision was
taken on **7 September 2026 by Danny Tran, program owner of record**: the
coordinator is the writer, through this route. The register carries the closure;
the repository's docstring was rewritten in the same commit rather than left to
contradict the code that now imports it.

The scanner and the roster-upload writers that question also named remain
unbuilt. This is the narrowest of its three candidates, not the first of them.

## Not the check-in flow, and structurally not

B08's QR check-in is still behind S11 and D8. Nothing here issues or verifies a
token, no scanner or device reaches this module, and the path contains none of
``tests/unit/test_checkin_wiring.py``'s markers — that file also holds the API
composition root away from :mod:`smartmatch_domain.checkin` by import
reachability, so a helper module could not smuggle the capability in either. The
mechanism recorded is
:data:`~smartmatch_domain.attendance.COORDINATOR_ENTRY_METHOD`, which is what
actually happened: a named coordinator asserted that somebody was present.

## Its own module, and not a ``POST`` on ``routers/engagement.py``

That router is pinned read-only by ``tests/unit/test_matching_fail_closed.py``
and bounded to its single path. A write there would need both pins loosened, and
it would attach the consequential act in this product to the router that exists
to demonstrate D8 is still open. Two routers, two questions.

## Which capability mounts it

``Capability.DISCOVERY_METRICS``, beside ``routers/pipeline.py``. That row exists
to make the funnel's Attended stage reachable, and this route is what makes it
reachable at all: a journey cannot reach Attended without an ``attendance_record``
to cite, and until now nothing under ``/v1`` wrote one. ``EVENT_READS`` (feedback
eligibility) and ``REWARDS_LEDGER`` (points) also depend on the row, so a reviewer
may move this — but it is one capability, stated here, rather than a route
mounted under whichever flag is convenient.

## What the subject may be

Any ``user_account`` in the tenant, and deliberately not "any student". The CBA
hand-off cites a row whose ``subject_id`` is the *speaker's* professional id, so
a route restricted to students would leave the CBA funnel's Attended stage
unreachable through the API. A speaker's attendance therefore also mints a
ledger entry that speaker cannot spend — the catalog is student-gated. That row
is inert, and it is written down here because an inert row is still a row.

## What it deliberately does not carry

**No balance.** ``GET /v1/units/{unit_id}/rewards`` folds the ledger and is the
only surface that knows how to answer ``unknown``; a second computation here
would be free to disagree with it. **No score, no roster, no list.** The response
describes the one row this request wrote and nothing about anybody else.

## Correcting a wrong row

An ``attendance_record`` cannot be deleted — every foreign key to it is
``RESTRICT`` — and the credit deriving from it is in an append-only ledger. A
coordinator who marks the wrong person present is corrected by
:meth:`~smartmatch_persistence.rewards.RewardsRepository.record_reversal`, which
writes a withdrawing entry carrying its own ``actor_id`` and reason. That is the
compensating control OQ-102's closure rests on, and it is a reversal rather than
an erasure on purpose.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from typing import Annotated, Final

import sqlalchemy as sa
from fastapi import APIRouter, Path, Response, status
from pydantic import BaseModel, ConfigDict, Field
from smartmatch_authz import OrgPath, Resource, assert_allowed
from smartmatch_domain.attendance import COORDINATOR_ENTRY_METHOD
from smartmatch_domain.rewards import LedgerEntryKind
from smartmatch_persistence import schema
from smartmatch_persistence.attendance import AttendanceRepository, ConflictingOwningUnitError
from smartmatch_persistence.rate_limit import RateLimit
from smartmatch_persistence.rewards import AlreadyCreditedError, RewardsRepository
from sqlalchemy.orm import Session

from smartmatch_api.dependencies import CurrentPrincipal, DbSession, charge_quota
from smartmatch_api.errors import ApiError
from smartmatch_api.units import load_unit_or_404
from smartmatch_api.utils import utc_now

router = APIRouter(prefix="/v1/units", tags=["attendance"])

#: The repositories, built once. Both are stateless — every method takes its
#: session — so one module-level instance is the same object every request would
#: construct. ``routers/rewards.py`` and ``routers/engagement.py`` hold theirs
#: the same way.
_attendance: Final[AttendanceRepository] = AttendanceRepository()
_rewards: Final[RewardsRepository] = RewardsRepository()

#: Roles permitted to record a unit's attendance. ``{admin, coordinator}`` —
#: OQ-102's closure names the coordinator as the writer of record, on the
#: argument ``routers/engagement.py`` makes for the matching read: this is unit
#: record-keeping a coordinator is accountable for, not a student's own standing.
#: A student is refused here for a sharper reason than they are refused the
#: summary — attendance is the only input to points, so a student who could write
#: one could mint their own.
#:
#: A literal ``frozenset`` rather than an import of the engagement read's set,
#: for the reason ``tests/authz/test_route_roles.py`` gives: two role sets
#: agreeing today is not a reason a widening of one should silently widen the
#: other, and this one carries a consequence the read does not.
_ATTENDANCE_WRITE_ROLES: Final[frozenset[str]] = frozenset({"admin", "coordinator"})

#: Looser than the 30-a-minute a filing or a stage advance gets, and the reason
#: is the act rather than its weight: a coordinator marking a room of students
#: present at the end of an event does thirty of these in well under a minute,
#: and a limit that refused the back half of the room would be read as the room
#: being wrong.
ATTENDANCE_WRITE_RATE_LIMIT: Final[RateLimit] = RateLimit(
    operation="attendance.record", max_requests=120, window=timedelta(minutes=1)
)


# ---------------------------------------------------------------------------
# Wire shapes
# ---------------------------------------------------------------------------


class AttendanceRecordRequest(BaseModel):
    """Who was present. Nothing else, and the absences are the design.

    **No** ``method``. The route *is* a coordinator's entry, so the mechanism is
    a fact about which route was called rather than a parameter: a caller-chosen
    ``qr_scan`` would claim a scanner nobody used and an ``import`` would claim a
    batch that never ran, and ``GET .../engagement/attendance-summary`` then
    republishes that claim as a breakdown by mechanism.

    **No** ``recorded_at``. ``attendance_record.created_at`` is the server
    default and the Attended funnel stage reads exactly that column as its own
    timestamp, so a caller-supplied instant would let a journey be walked into
    the past.

    ``extra="forbid"`` is what makes both refusals visible. A field accepted and
    quietly dropped is indistinguishable, to the client that sent it, from one
    that worked — ``routers/auth.py`` forbids extras for the same reason.
    """

    model_config = ConfigDict(extra="forbid")

    subject_id: uuid.UUID = Field(
        description=(
            "The account that was present. Any `user_account` in this tenant: a "
            "student, or the speaker whose attendance the CBA hand-off cites. Must "
            "already exist — this route creates no accounts."
        )
    )


class AttendanceRecordResponse(BaseModel):
    """The one row this request wrote, and what derived from it.

    Carries no balance and no score. The balance has one honest home —
    `GET /v1/units/{unit_id}/rewards` — which is also the only surface that knows
    how to report it as `unknown`.
    """

    attendance_id: uuid.UUID = Field(
        description="The `attendance_record` row. The same id on a replay as on the first call."
    )
    unit_id: uuid.UUID = Field(
        description=(
            "The unit that owns this evidence, which is also the unit the request "
            "was authorized against. Taken from the loaded row, never from the body."
        )
    )
    event_id: uuid.UUID = Field(description="The event attended, hosted by this unit.")
    subject_id: uuid.UUID = Field(description="The account recorded as present.")
    method: str = Field(
        description=(
            "Always `coordinator_entry`. Fixed server-side; the request has no field "
            "for it. See the request model."
        )
    )
    recorded_at: datetime = Field(
        description=(
            "`attendance_record.created_at` — the server's own instant, read back "
            "from the stored row. Timezone-aware (ADR-0010)."
        )
    )
    points_credited: bool = Field(
        description=(
            "Whether *this request* appended the earning entry. False on a replay, "
            "where the entry already existed — which is not the same claim as 'no "
            "points derive from this attendance'. `ledger_entry_id` says which."
        )
    )
    ledger_entry_id: uuid.UUID | None = Field(
        description=(
            "The `point_ledger_entry` deriving from this attendance, whether this "
            "request wrote it or found it. Null only when no entry exists at all."
        )
    )


# ---------------------------------------------------------------------------
# Authorization and lookups
# ---------------------------------------------------------------------------


def _authorize_attendance_write(
    session: Session,
    principal: CurrentPrincipal,
    unit_id: uuid.UUID,
) -> uuid.UUID:
    """Load the unit and authorize a coordinator's attendance write against it.

    The unit is loaded first and authorization runs against *that row's* path,
    never a path taken from the request. ``load_unit_or_404`` scopes the lookup
    by the caller's own tenant, so a unit in another tenant is a 404 rather than
    a 403 that would confirm the id names something real.

    No ``require_membership`` and no ``tenant_wide_roles``.
    :data:`_ATTENDANCE_WRITE_ROLES` is non-empty, so ``evaluate`` refuses a bare
    ``resource_grant`` on the required-roles check before membership is reached
    (S-007). The ratified metrics decision's §4 widens *aggregate reads* for an
    admin, and this is neither an aggregate nor a read, so ordinary subtree
    containment applies and a sibling department's admin is refused.

    Returns:
        The loaded unit's own id — the ``owning_unit_id`` the row is written
        under, so it comes from the authorized row and never from a body.
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
        required_roles=_ATTENDANCE_WRITE_ROLES,
    )
    return unit.id


def _require_event_hosted_by(
    session: Session, *, tenant_id: uuid.UUID, unit_id: uuid.UUID, event_id: uuid.UUID
) -> None:
    """Refuse an event that is not this unit's, in words.

    ``attendance_record``'s composite foreign key checks that the event is in the
    tenant; it says nothing about which unit hosts it. An attendance owned by
    unit A at an event hosted by unit B stores perfectly well and is a row
    nobody's drill-down can explain, so the host is checked here — the same
    scoping the CBA hand-off applies to its own event.
    """
    hosted = session.execute(
        sa.select(schema.event.c.id).where(
            schema.event.c.tenant_id == tenant_id,
            schema.event.c.id == event_id,
            schema.event.c.host_org_unit_id == unit_id,
        )
    ).one_or_none()
    if hosted is None:
        raise ApiError(
            status_code=status.HTTP_404_NOT_FOUND,
            code="event_not_found",
            message="No such event hosted by this unit.",
        )


def _require_subject_in_tenant(
    session: Session, *, tenant_id: uuid.UUID, subject_id: uuid.UUID
) -> None:
    """Refuse an unknown subject as a worded 404 rather than an ``IntegrityError``.

    The composite foreign key to ``user_account`` would refuse it too, but as a
    500 naming a constraint — which tells a coordinator who mistyped an id
    nothing they can act on.
    """
    known = session.execute(
        sa.select(schema.user_account.c.id).where(
            schema.user_account.c.tenant_id == tenant_id,
            schema.user_account.c.id == subject_id,
        )
    ).one_or_none()
    if known is None:
        raise ApiError(
            status_code=status.HTTP_404_NOT_FOUND,
            code="attendance_subject_not_found",
            message="No such account in this tenant.",
        )


def _recorded_at(session: Session, *, attendance_id: uuid.UUID) -> datetime:
    """Read the stored row's own ``created_at``.

    Read back rather than stamped from a clock in this handler: the column
    carries a database default, and a second instant computed beside it would let
    the response disagree with the row the funnel reads.
    """
    value = session.execute(
        sa.select(schema.attendance_record.c.created_at).where(
            schema.attendance_record.c.id == attendance_id
        )
    ).scalar_one()
    if not isinstance(value, datetime):
        raise TypeError(
            f"attendance_record.created_at read back as {type(value).__name__}, not datetime"
        )
    return value


def _existing_credit(
    session: Session, *, tenant_id: uuid.UUID, attendance_id: uuid.UUID
) -> uuid.UUID | None:
    """The attendance credit already deriving from this row, if there is one.

    Read only on the replay path, where
    :meth:`~smartmatch_persistence.rewards.RewardsRepository.credit_attendance`
    has just refused a second credit. Reporting ``null`` there would say
    something false — the points exist — and the id is what lets a client tell
    "already credited" from "not credited at all".
    """
    return session.execute(
        sa.select(schema.point_ledger_entry.c.id).where(
            schema.point_ledger_entry.c.tenant_id == tenant_id,
            schema.point_ledger_entry.c.source_attendance_id == attendance_id,
            schema.point_ledger_entry.c.kind == LedgerEntryKind.ATTENDANCE_CREDIT.value,
        )
    ).scalar_one_or_none()


# ---------------------------------------------------------------------------
# Route
# ---------------------------------------------------------------------------


@router.post(
    "/{unit_id}/events/{event_id}/attendance",
    status_code=status.HTTP_201_CREATED,
    response_model=AttendanceRecordResponse,
    summary="Record that an account was present at one of this unit's events",
    responses={
        200: {
            "description": (
                "This attendance was already on file for the same subject and event, "
                "so nothing was written and the existing row is returned."
            )
        },
        201: {"description": "The attendance was recorded and its points credited."},
    },
)
def record_attendance(
    principal: CurrentPrincipal,
    session: DbSession,
    body: AttendanceRecordRequest,
    unit_id: Annotated[uuid.UUID, Path()],
    event_id: Annotated[uuid.UUID, Path()],
    response: Response,
) -> AttendanceRecordResponse:
    """Record one attendance, and credit the points that derive from it.

    ``201``: this call wrote the row. ``200``: a row for this subject and event
    was already there, so nothing was written — the distinction
    ``routers/speaker_requests.py`` draws on ADR-0012's identity key, applied
    here to ``uq_attendance_record_subject_event``. Either way the response
    describes the row that exists, so a coordinator who clicks twice is not told
    they created two.

    The points are credited in the **same transaction** as the row, because
    ADR-0013 makes the derivation automatic — "points derive from recorded
    attendance and nothing else" — and a separate credit route would turn one
    derivation into a second human step somebody could forget, leaving every
    balance ``unknown``. ``actor_id`` is the caller: this is the case
    :meth:`~smartmatch_persistence.rewards.RewardsRepository.credit_attendance`'s
    own docstring names, "where a coordinator's action is what caused the
    derivation to be run". ``AlreadyCreditedError`` is caught, so a replay does
    not double-credit; ``UnknownAttendanceError`` is **not** caught, because the
    row was written two statements ago and its absence would be a defect here
    rather than a caller's mistake.

    No registration is required first. An attendance row is evidence that
    somebody was present, and demanding an ``event_registration`` would refuse
    the walk-in the coordinator is looking at.

    Quota is charged first, before the unit is loaded and before authorization
    runs (ADR-0015): a caller producing 404s against invented ids spends what a
    caller recording real attendance spends.

    Raises:
        ApiError: 403 when the caller may not write into this unit; 404 when the
            unit is not this tenant's, the event is not hosted by this unit, or
            the subject is not an account in this tenant; 409 when an attendance
            for this subject and event is already filed under a different unit;
            429 when the minute's quota is spent.
    """
    charge_quota(session, principal, ATTENDANCE_WRITE_RATE_LIMIT)

    owning_unit_id = _authorize_attendance_write(session, principal, unit_id)
    _require_event_hosted_by(
        session, tenant_id=principal.tenant_id, unit_id=owning_unit_id, event_id=event_id
    )
    _require_subject_in_tenant(session, tenant_id=principal.tenant_id, subject_id=body.subject_id)

    try:
        written = _attendance.record_attendance(
            session,
            tenant_id=principal.tenant_id,
            owning_unit_id=owning_unit_id,
            subject_id=body.subject_id,
            event_id=event_id,
            method=COORDINATOR_ENTRY_METHOD,
        )
    except ConflictingOwningUnitError as exc:
        raise ApiError(
            status_code=status.HTTP_409_CONFLICT,
            code="attendance_owned_by_another_unit",
            message=str(exc),
        ) from exc

    ledger_entry_id: uuid.UUID | None
    try:
        ledger_entry_id = _rewards.credit_attendance(
            session,
            tenant_id=principal.tenant_id,
            attendance_id=written.attendance_id,
            actor_id=principal.user_id,
        )
        points_credited = True
    except AlreadyCreditedError:
        # The replay path, and the only failure this catches. The credit is
        # there; what this request did not do is write it.
        points_credited = False
        ledger_entry_id = _existing_credit(
            session, tenant_id=principal.tenant_id, attendance_id=written.attendance_id
        )

    recorded_at = _recorded_at(session, attendance_id=written.attendance_id)
    # The commit `get_session` will not do for us: it rolls back unconditionally,
    # so without this the route returns a cheerful 201 and stores nothing.
    session.commit()

    if not written.created:
        # FastAPI stamped 201 from the decorator; this call inserted nothing,
        # and saying "created" of it would make a replay indistinguishable from
        # a first recording.
        response.status_code = status.HTTP_200_OK

    return AttendanceRecordResponse(
        attendance_id=written.attendance_id,
        unit_id=owning_unit_id,
        event_id=event_id,
        subject_id=body.subject_id,
        method=COORDINATOR_ENTRY_METHOD,
        recorded_at=recorded_at,
        points_credited=points_credited,
        ledger_entry_id=ledger_entry_id,
    )
