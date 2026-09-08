"""The Event Host's Speaker Request intake, and the Speaker Connector's queue.

Card ``CBA-EVENT-REQUEST``. Three unit-scoped routes over migration ``0024``'s
``event`` + ``speaker_request_classification`` shape, plus ``0033``'s
``event.filed_by_user_id``:

* ``POST /v1/units/{unit_id}/speaker-requests`` — customer §12, an Event Host
  files a request. See :func:`create_speaker_request`.
* ``GET /v1/units/{unit_id}/speaker-requests`` — customer §13, a Speaker
  Connector reads the incoming queue. See :func:`list_speaker_requests`.
* ``GET /v1/units/{unit_id}/host/speaker-requests`` — **OQ-CBA-014**, closed 7
  September 2026: an Event Host reads back the requests *they* filed. See
  :func:`list_own_speaker_requests`.

The second and third are two operations rather than one read with two audiences,
and their role sets are **disjoint**: ``{admin, coordinator}`` against
``{volunteer}``. The queue carries every host's request text for the unit, so a
host reading it would learn what the other hosts asked for; the host list carries
only the rows whose recorded filer is the caller, so a coordinator reading it
would learn nothing the queue does not already tell them. Neither is a subset of
the other, which is why neither is expressible as a role added to a set.

## Why this is a transactional create and not a command

``smartmatch_api.commands.submit_command`` exists for work the request path must
not do: a provider call, an extraction, a solve — anything durable, slow, or
paid, where "accepted" is the only honest answer and a job id is the handle.
Filing a Speaker Request is none of those. It is one ``INSERT ... ON CONFLICT``
plus its child rows, it touches no network and no provider, and it is *complete*
when the response is written. Answering ``202 Accepted`` with a job id would
report that something had been queued when the row already exists — the mirror
image of the defect v1.1 §3.6 N2 forbids, and the same species: a status code
that does not describe what happened.

What keeps this honest is that the route does exactly what its status code
claims. It commits, then reads the row back through the same repository the list
route uses, and returns that. Nothing is echoed from the request body.

## Idempotency without an ``Idempotency-Key``

ADR-0012 already gives an event a deterministic identity — host org unit, folded
title, resolved date — and says in as many words that manual entry is not exempt
from it. So a resubmitted request updates the request it names rather than
filing a second one, and the caller is told which happened by the status code:
``201`` when this call created the row, ``200`` when it updated one that already
existed. That is a stronger guarantee than a header key, which only recognises a
repeat of the *identical body*: a host who fixes a typo and resubmits gets one
request either way here, and would have got two with a header key.

There is deliberately no ``Idempotency-Key`` parameter. Accepting one would
publish a second notion of sameness beside the one the data already has, and the
first time the two disagreed a caller would have no way to know which applied.

## Host power is server-side

The unit comes from the path, is loaded with ``load_unit_or_404`` inside the
caller's tenant, and is authorized against *that row's* path — never against
anything in the body. The tenant comes from the verified principal. There is no
``host_org_unit_id``, ``tenant_id`` or ``actor`` field on the request model and
there must never be one: a body naming its own scope is the caller-selected
identity pattern (MM-A01), and here it would let a host file a request into a
department they cannot reach.

The three authorizers are separate functions with separate role constants,
because customer §12, customer §13 and OQ-CBA-014's closure answer three
different questions — see :data:`_SPEAKER_REQUEST_CREATE_ROLES`,
:data:`_SPEAKER_REQUEST_READ_ROLES` and
:data:`_SPEAKER_REQUEST_OWN_READ_ROLES`.

The host list adds a fourth statement of the same rule, one level down from the
principal: a permit says which *unit* a caller may ask about, and the row filter
``filed_by_user_id == principal.user_id`` says whose requests they get. No route
here accepts a filer in a path, a query parameter or a body, and none may.

## No fetch, no URL, no crawl

Nothing here accepts a URL, opens a socket, or consults ``ALLOW_LIVE_PROVIDERS``.
A filed request is written with ``origin = 'coordinator_entry'`` and no
provenance at all, which ``ck_event_provenance_evidence`` requires of a row a
person typed — customer §20's out-of-scope external discovery refused as a
constraint rather than as a policy somebody has to remember.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta
from typing import Annotated, Final

from fastapi import APIRouter, Path, Response, status
from pydantic import BaseModel, Field
from smartmatch_authz import OrgPath, Resource, assert_allowed
from smartmatch_domain.cba_role_categories import (
    UnknownCbaRoleCategory,
    role_category_for_code,
)
from smartmatch_domain.events import DateOnlyTime, EventTime, ExactTime
from smartmatch_domain.naics_sectors import UnknownNaicsSector, sector_for_code
from smartmatch_domain.speaker_requests import (
    KIND_INDUSTRY,
    KIND_ROLE,
    SpeakerRequestDraft,
    SpeakerRequestError,
)
from smartmatch_persistence.rate_limit import RateLimit
from smartmatch_persistence.speaker_requests import SpeakerRequestRepository, SpeakerRequestRow
from sqlalchemy.orm import Session

from smartmatch_api.dependencies import CurrentPrincipal, DbSession, charge_quota
from smartmatch_api.errors import ApiError
from smartmatch_api.units import load_unit_or_404
from smartmatch_api.utils import utc_now

router = APIRouter(prefix="/v1/units", tags=["speaker-requests"])

_requests: Final[SpeakerRequestRepository] = SpeakerRequestRepository()

#: Who may file a Speaker Request. Customer §12 gives the capability to the
#: **Event Host**, which ``smartmatch_domain.role_presentation`` maps onto the
#: stored ``volunteer`` role following customer §4 ("Volunteer — Event Host when
#: referring to the event-requesting role"). ``admin`` and ``coordinator`` are
#: the Speaker Connector persona, which already owns every other write to an
#: ``event`` row in the same unit — ``review.py`` decides it, ``pipeline.py``
#: moves it, ``match_runs.py`` runs against it — so refusing them the creation
#: of one would be an inconsistency rather than a narrower policy, and §13 makes
#: them the recipients of these requests in the first place.
#:
#: A literal ``frozenset`` rather than an import of another module's role set,
#: for the reason ``tests/authz/test_route_roles.py`` gives about its own
#: ledger: several role sets agreeing today is not a reason a widening of one
#: should silently widen the others.
_SPEAKER_REQUEST_CREATE_ROLES: Final[frozenset[str]] = frozenset(
    {"admin", "coordinator", "volunteer"}
)

#: Who may read the queue. Customer §13 gives "view incoming Speaker Requests"
#: to the **Speaker Connector** and names nobody else, so this set is narrower
#: than the one above by exactly ``volunteer``: the queue holds every host's
#: request text for the unit, and handing one host the others' requests is a
#: widening no committed artifact supports. Under deny-by-default the absence of
#: a permit is a denial rather than an invitation to guess. A host does not need
#: it to see their own work — :func:`create_speaker_request` returns the filed
#: request, a resubmission returns it again, and since **OQ-CBA-014** was closed
#: (7 September 2026, Danny Tran, program owner of record) a host reads their own
#: filings back through :data:`_SPEAKER_REQUEST_OWN_READ_ROLES` below. That
#: closure took nothing out of this set and put nothing into it: it added a
#: second route with a narrower query, which is what the register asked for in as
#: many words — "a host-scoped read is a different query, not a wider permit".
_SPEAKER_REQUEST_READ_ROLES: Final[frozenset[str]] = frozenset({"admin", "coordinator"})

#: Who may read back **their own** filed Speaker Requests. **OQ-CBA-014**, closed
#: 7 September 2026 by Danny Tran, program owner of record.
#:
#: ``volunteer`` and nothing else, and the two absences are the decision rather
#: than an oversight. ``admin`` and ``coordinator`` already hold the queue above,
#: which is strictly wider: a coordinator who filed a request sees it there
#: alongside every other, so this route would tell them only which of the unit's
#: requests they personally typed. A second door onto rows already reachable is a
#: second thing to narrow the day the first one narrows, and until then it is a
#: permit nobody needs.
#:
#: A third literal beside the two above rather than a fourth member of either, for
#: the reason ``tests/authz/test_route_roles.py`` gives about its own ledger:
#: several role sets agreeing today is not a reason a widening of one should
#: silently widen the others. Here the sets do not even agree — this one is
#: *disjoint* from the queue's, which is the shape of the decision.
_SPEAKER_REQUEST_OWN_READ_ROLES: Final[frozenset[str]] = frozenset({"volunteer"})

#: The write is the consequential one and carries the tighter limit, the same
#: relationship ``pipeline.py`` draws between its two. Thirty filings a minute is
#: already faster than a department can plan events; the read is a queue a person
#: refreshes.
SPEAKER_REQUEST_WRITE_RATE_LIMIT: Final[RateLimit] = RateLimit(
    operation="speaker_request.create", max_requests=30, window=timedelta(minutes=1)
)
SPEAKER_REQUEST_READ_RATE_LIMIT: Final[RateLimit] = RateLimit(
    operation="speaker_request.read", max_requests=120, window=timedelta(minutes=1)
)

#: The most requests one response returns. G3 §2.2a's 200-record cap, reused
#: rather than a second number invented here — ``routers/events.py::MAX_ROWS``
#: and ``routers/match_runs.py::MAX_CANDIDATES`` are the same number for the
#: same reason. Paging is deliberately not shipped: a cursor nobody has asked
#: for is a contract to maintain, and ``truncated`` is what keeps a full page
#: from reading as a complete one.
MAX_ROWS: Final[int] = 200


# ---------------------------------------------------------------------------
# Request and response models
# ---------------------------------------------------------------------------


class SpeakerRequestCreate(BaseModel):
    """One Speaker Request, as an Event Host fills it in (customer §12).

    Note what is **not** here: no tenant, no host org unit, no actor, no source
    URL, no publication status. The first three come from the verified principal
    and the path; the fourth does not exist for a request a person typed; the
    fifth is not a host's to set.

    The temporal fields are ADR-0010's, not a single nullable timestamp. A host
    who knows the date but not yet the hour sends ``on_date`` and gets a
    ``date_only`` request, which is the honest description of what they said —
    rather than midnight in some zone, which is the fabrication ADR-0010 exists
    to stop. ``time_zone`` is required at both precisions and is the event's own
    zone, never the browser's.
    """

    title: str = Field(min_length=1, description="What the event is called.")
    time_zone: str = Field(
        min_length=1,
        description=(
            "The IANA zone the event happens in, e.g. 'America/Los_Angeles'. "
            "Resolved against the real tz database; a UTC offset is not accepted "
            "in its place (ADR-0010 rule 1)."
        ),
    )
    industry_codes: list[str] = Field(
        min_length=1,
        description=(
            "One or more NAICS sector codes from the released CBA taxonomy "
            "(customer §7). Multi-select: a request is not restricted to one."
        ),
    )
    role_codes: list[str] = Field(
        min_length=1,
        description=(
            "One or more CBA career role-category codes from the released "
            "taxonomy (customer §8). Multi-select, for the same reason."
        ),
    )
    is_virtual: bool = Field(
        default=False,
        description=(
            "Customer §12's physical/virtual switch. A virtual request must "
            "carry no location: §11 ignores Proximity entirely for one."
        ),
    )
    starts_at: datetime | None = Field(
        default=None,
        description=(
            "The instant the event starts, timezone-aware. Send this or "
            "'on_date', never both and never neither."
        ),
    )
    ends_at: datetime | None = Field(
        default=None,
        description=(
            "The instant it finishes, when the host states one. Never derived "
            "from 'starts_at' — an unstated end stays unstated. Valid only "
            "alongside 'starts_at'."
        ),
    )
    on_date: date | None = Field(
        default=None,
        description="The calendar date, when the hour is not yet known.",
    )
    description: str | None = Field(
        default=None,
        description=(
            "Customer §12's event topic/description, and the text §9 compares "
            "semantically against a speaker's topic information. Omit it rather "
            "than sending an empty string."
        ),
    )
    location_city: str | None = Field(
        default=None, description="Customer §10's city. Physical requests only."
    )
    location_postal_code: str | None = Field(
        default=None, description="Customer §10's ZIP. Physical requests only."
    )


class ClassificationView(BaseModel):
    """One target of a request, with the name a person reads beside the stored code.

    ``code`` is what a row holds and what a matcher compares; ``display_name`` is
    §7's or §8's own wording, read from the released taxonomy module rather than
    restated here, so a display rename cannot drift from the storage key.
    ``taxonomy_version`` says which released table evaluated the code, which is
    what keeps it interpretable after the next revision.
    """

    code: str
    display_name: str
    taxonomy_version: str


class SpeakerRequestTimeView(BaseModel):
    """The request's time at whichever precision the host actually stated.

    The same shape ``routers/events.py::EventTimeView`` uses, and deliberately so
    — one event model, one temporal contract. ``precision`` is never
    ``unresolved`` on this surface: a request that could not resolve a date is
    refused at intake rather than filed.
    """

    precision: str = Field(description="exact or date_only.")
    starts_at: datetime | None = None
    ends_at: datetime | None = None
    on_date: date | None = None
    time_zone: str | None = None


class SpeakerRequestResponse(BaseModel):
    """One filed Speaker Request, read back from the row that was written.

    Never assembled from the request body. What a caller reads here is what the
    database holds — which is the difference between a create that reports what
    it did and one that repeats what it was told.
    """

    unit_id: uuid.UUID
    request_id: uuid.UUID = Field(
        description="The event id holding this request. Stable across resubmissions."
    )
    title: str
    description: str | None = None
    time: SpeakerRequestTimeView
    is_virtual: bool
    location_city: str | None = None
    location_postal_code: str | None = None
    industries: list[ClassificationView] = Field(
        description="Customer §7's targets, in code order."
    )
    roles: list[ClassificationView] = Field(description="Customer §8's targets, in code order.")
    publication_status: str = Field(
        description=(
            "The event's own status. A filed request is 'unpublished': filing "
            "records what a host asked for, it does not publish an event."
        )
    )
    review_status: str
    created_at: datetime
    updated_at: datetime


class SpeakerRequestListResponse(BaseModel):
    """The unit's incoming Speaker Requests (customer §13)."""

    unit_id: uuid.UUID
    requests: list[SpeakerRequestResponse]
    truncated: bool = Field(
        description="True when more requests exist than the response cap returns."
    )


# ---------------------------------------------------------------------------
# Authorization
# ---------------------------------------------------------------------------


def _authorize_speaker_request_create(
    session: Session,
    principal: CurrentPrincipal,
    unit_id: uuid.UUID,
) -> uuid.UUID:
    """Load the unit and authorize an Event Host's filing against it.

    The unit is loaded first and authorization runs against *that row's* path,
    never against a path taken from the request. ``load_unit_or_404`` scopes the
    lookup by the caller's own tenant, so a unit in another tenant is a 404
    rather than a 403 that would confirm the id names something real.

    No ``require_membership`` — :data:`_SPEAKER_REQUEST_CREATE_ROLES` is
    non-empty, so ``evaluate`` already refuses a bare ``resource_grant`` on the
    required-roles check (S-007). No ``tenant_wide_roles`` — the metrics
    decision's §4 is the only artifact that makes anything tenant-wide and it
    says so of aggregate reads, not of writing a row into a department.

    Returns:
        The authorized unit id, which is what the write is filed under.
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
        required_roles=_SPEAKER_REQUEST_CREATE_ROLES,
    )
    return unit_id


def _authorize_speaker_request_read(
    session: Session,
    principal: CurrentPrincipal,
    unit_id: uuid.UUID,
) -> uuid.UUID:
    """Load the unit and authorize a Speaker Connector's read of its queue.

    Its own function rather than a share of the one above, even though the two
    load the same row the same way: they gate on two different customer sections,
    and one helper taking the role set as an argument would make a single call
    site the place both could be widened from.
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
        required_roles=_SPEAKER_REQUEST_READ_ROLES,
    )
    return unit_id


def _authorize_speaker_request_own_read(
    session: Session,
    principal: CurrentPrincipal,
    unit_id: uuid.UUID,
) -> uuid.UUID:
    """Load the unit and authorize an Event Host's read of their own filings.

    A **third** function rather than a role-set parameter on either of the two
    above, for the reason :func:`_authorize_speaker_request_read` states about the
    first pair and which applies with more force here: this one and the queue's
    gate on *disjoint* role sets, and a single call site taking the set as an
    argument would be the one place all three could be widened from.

    Note what this function does **not** decide. A permit here says this principal
    may call the route against this unit; it says nothing about whose requests
    come back, and it cannot — ``evaluate`` reasons about principals and paths,
    not about rows. The self-scoping is
    :func:`list_own_speaker_requests`'s own predicate, which is why that function
    passes ``principal.user_id`` and why nothing in the request can name a filer.

    Returns:
        The authorized unit id, which is the unit the listing is scoped to.
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
        required_roles=_SPEAKER_REQUEST_OWN_READ_ROLES,
    )
    return unit_id


# ---------------------------------------------------------------------------
# Body to domain
# ---------------------------------------------------------------------------


def _event_time(body: SpeakerRequestCreate) -> EventTime:
    """Build ADR-0010's temporal value, or refuse to invent one.

    Exactly one of ``starts_at`` and ``on_date``. Neither is refused rather than
    filed as ``UnresolvedTime``: a request with no date has no identity key
    (ADR-0012) and can reach no matchable state (ADR-0010 rule 2), so filing one
    would produce a row that is neither deduplicable nor usable, and the deferral
    policy for this phase is that an unresolved field fails closed. Both is
    refused because they are two answers to one question, and silently taking the
    more precise one would discard whichever the host actually meant.
    """
    if body.starts_at is not None and body.on_date is not None:
        raise ApiError(
            status_code=status.HTTP_400_BAD_REQUEST,
            code="speaker_request_time_ambiguous",
            message=(
                "Send 'starts_at' or 'on_date', not both. They are two answers to one "
                "question, and choosing between them here would discard the one you meant."
            ),
        )
    if body.starts_at is None and body.on_date is None:
        raise ApiError(
            status_code=status.HTTP_400_BAD_REQUEST,
            code="speaker_request_time_required",
            message=(
                "A Speaker Request needs a date: send 'starts_at' for a known time or "
                "'on_date' when the hour is not settled. An undated request has no "
                "identity key (ADR-0012) and cannot reach a matchable state "
                "(ADR-0010 rule 2), so it is refused rather than filed as unresolved."
            ),
        )
    if body.on_date is not None:
        if body.ends_at is not None:
            raise ApiError(
                status_code=status.HTTP_400_BAD_REQUEST,
                code="speaker_request_end_without_start",
                message=(
                    "'ends_at' needs a 'starts_at'. An end instant on a date-only request "
                    "would be a clock time on an event that has none."
                ),
            )
        return DateOnlyTime(on_date=body.on_date, time_zone=body.time_zone)
    # Narrowed by the two checks above: `starts_at` is set and `on_date` is not.
    starts_at = body.starts_at
    if starts_at is None:  # pragma: no cover - unreachable, stated for the type checker
        raise ApiError(
            status_code=status.HTTP_400_BAD_REQUEST,
            code="speaker_request_time_required",
            message="A Speaker Request needs a date.",
        )
    return ExactTime(starts_at=starts_at, time_zone=body.time_zone, ends_at=body.ends_at)


def _draft(body: SpeakerRequestCreate) -> SpeakerRequestDraft:
    """Validate the body into a domain draft, or answer 400 naming the rule.

    Every rule is the domain's — see ``smartmatch_domain.speaker_requests``. This
    function only decides which HTTP answer each refusal gets, so a rule cannot
    be enforced differently by the route than by the writer.

    ``ValueError`` from the temporal types (a naive ``starts_at``, an unknown
    zone, an ``ends_at`` at or before the start) is caught in the same net for
    the same reason: those are also statements about the submitted body, and
    letting one become a 500 would report a server fault for a client mistake.
    """
    try:
        event_time = _event_time(body)
        return SpeakerRequestDraft(
            title=body.title,
            event_time=event_time,
            is_virtual=body.is_virtual,
            industry_codes=tuple(body.industry_codes),
            role_codes=tuple(body.role_codes),
            description=body.description,
            location_city=body.location_city,
            location_postal_code=body.location_postal_code,
        )
    except UnknownNaicsSector as exc:
        raise ApiError(
            status_code=status.HTTP_400_BAD_REQUEST,
            code="speaker_request_unknown_industry",
            message=str(exc),
        ) from exc
    except UnknownCbaRoleCategory as exc:
        raise ApiError(
            status_code=status.HTTP_400_BAD_REQUEST,
            code="speaker_request_unknown_role",
            message=str(exc),
        ) from exc
    except SpeakerRequestError as exc:
        raise ApiError(
            status_code=status.HTTP_400_BAD_REQUEST,
            code="speaker_request_invalid",
            message=str(exc),
        ) from exc
    except ValueError as exc:
        # The temporal types' own refusals (ADR-0010): a naive instant, a zone
        # the IANA database does not contain, an end at or before the start.
        raise ApiError(
            status_code=status.HTTP_400_BAD_REQUEST,
            code="speaker_request_invalid_time",
            message=str(exc),
        ) from exc


def _view(unit_id: uuid.UUID, row: SpeakerRequestRow) -> SpeakerRequestResponse:
    """Render one stored request.

    The display names come from the released taxonomy modules, which are the only
    copies of customer §7's and §8's wording. Reading them here rather than
    storing them beside the codes is what keeps a rename a one-file change:
    ``0024`` stores keys, ``naics_sectors`` and ``cba_role_categories`` say what
    a key means.
    """
    industries = [
        ClassificationView(
            code=item.code,
            display_name=sector_for_code(item.code).name,
            taxonomy_version=item.taxonomy_version,
        )
        for item in row.classifications
        if item.kind == KIND_INDUSTRY
    ]
    roles = [
        ClassificationView(
            code=item.code,
            display_name=role_category_for_code(item.code).name,
            taxonomy_version=item.taxonomy_version,
        )
        for item in row.classifications
        if item.kind == KIND_ROLE
    ]
    return SpeakerRequestResponse(
        unit_id=unit_id,
        request_id=row.event_id,
        title=row.title,
        description=row.description,
        time=SpeakerRequestTimeView(
            precision=row.time_precision,
            starts_at=row.starts_at,
            ends_at=row.ends_at,
            on_date=row.on_date,
            time_zone=row.time_zone,
        ),
        is_virtual=row.is_virtual,
        location_city=row.location_city,
        location_postal_code=row.location_postal_code,
        industries=industries,
        roles=roles,
        publication_status=row.publication_status,
        review_status=row.review_status,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.post(
    "/{unit_id}/speaker-requests",
    status_code=status.HTTP_201_CREATED,
    response_model=SpeakerRequestResponse,
    summary="File a Speaker Request",
    responses={
        200: {
            "description": (
                "This request already existed under ADR-0012's identity key — same "
                "host unit, same folded title, same date — and was updated rather "
                "than duplicated."
            )
        },
        201: {"description": "A new Speaker Request was filed."},
    },
)
def create_speaker_request(
    principal: CurrentPrincipal,
    session: DbSession,
    body: SpeakerRequestCreate,
    unit_id: Annotated[uuid.UUID, Path()],
    response: Response,
) -> SpeakerRequestResponse:
    """Record what an Event Host is asking for (customer §12).

    ``201``: this has completed when it returns. The row exists, its industry and
    role targets exist, and the response is read back out of them rather than
    echoed from the body.

    ``200``: ADR-0012's identity key resolved this onto a request already filed,
    so this call updated it. A resubmission is the same request, and the status
    code is how a caller learns which of the two happened — see the module
    docstring on idempotency. A resubmission also *replaces* the targets: an
    industry the new body does not name is one the host removed.

    Quota is charged first, before the unit is loaded and before authorization
    runs (ADR-0015).

    Raises:
        ApiError: 400 when the body describes a request that cannot be filed — an
            undated or doubly-dated one, an unreleased taxonomy code, a virtual
            request carrying a location, a physical one carrying none, or a
            repeated selection; 403 when the caller may not file into this unit;
            404 when the unit is not this tenant's; 429 when the minute's quota
            is spent.
    """
    charge_quota(session, principal, SPEAKER_REQUEST_WRITE_RATE_LIMIT)

    host_org_unit_id = _authorize_speaker_request_create(session, principal, unit_id)
    draft = _draft(body)

    result = _requests.file(
        session,
        tenant_id=principal.tenant_id,
        host_org_unit_id=host_org_unit_id,
        draft=draft,
        # The verified principal, never a body field — exactly what
        # `SpeakerRequestCreate`'s docstring already promises about every actor
        # on this surface. A coordinator filing a request is recorded as its
        # filer too; that is the truth about who typed it, and the alternative
        # would be a column that means "the filer, unless it was a coordinator".
        filed_by_user_id=principal.user_id,
    )
    session.commit()

    row = _requests.get(session, tenant_id=principal.tenant_id, event_id=result.event_id)
    if row is None:  # pragma: no cover - the row was committed in this transaction
        raise ApiError(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            code="speaker_request_not_readable",
            message="The Speaker Request was written but could not be read back.",
        )

    if not result.created:
        # FastAPI stamped 201 from the decorator; this call updated a request
        # that was already there, and saying "created" of it would make a
        # resubmission indistinguishable from a first filing.
        response.status_code = status.HTTP_200_OK
    return _view(unit_id, row)


@router.get(
    "/{unit_id}/speaker-requests",
    response_model=SpeakerRequestListResponse,
    summary="List a unit's incoming Speaker Requests",
)
def list_speaker_requests(
    principal: CurrentPrincipal,
    session: DbSession,
    unit_id: Annotated[uuid.UUID, Path()],
) -> SpeakerRequestListResponse:
    """Return the requests filed under this unit, soonest event first (§13).

    Only requests: the query is restricted to ``origin = 'coordinator_entry'`` in
    the repository, so an extracted event never appears here. That is not a
    tidiness rule — an extracted row carries source provenance, and a queue that
    promises "what hosts asked for" must not answer with something a crawler
    produced.

    Reads at most :data:`MAX_ROWS` + 1 rows so ``truncated`` is answered by the
    same query rather than by a second count whose filters could drift from this
    one's.

    Only ``admin`` and ``coordinator`` may read this
    (:func:`_authorize_speaker_request_read`), and authorization runs before any
    request row is read.
    """
    charge_quota(session, principal, SPEAKER_REQUEST_READ_RATE_LIMIT)
    _authorize_speaker_request_read(session, principal, unit_id)

    rows = _requests.list_for_unit(
        session,
        tenant_id=principal.tenant_id,
        host_org_unit_id=unit_id,
        limit=MAX_ROWS + 1,
    )
    return SpeakerRequestListResponse(
        unit_id=unit_id,
        requests=[_view(unit_id, row) for row in rows[:MAX_ROWS]],
        truncated=len(rows) > MAX_ROWS,
    )


@router.get(
    "/{unit_id}/host/speaker-requests",
    response_model=SpeakerRequestListResponse,
    summary="List the Speaker Requests this Event Host filed",
)
def list_own_speaker_requests(
    principal: CurrentPrincipal,
    session: DbSession,
    unit_id: Annotated[uuid.UUID, Path()],
) -> SpeakerRequestListResponse:
    """Return the requests **this caller** filed under this unit, soonest first.

    **OQ-CBA-014**, closed 7 September 2026 by Danny Tran, program owner of
    record. The register asked whether an Event Host may list back the requests
    they filed and pre-refused the shortcut in its own words: "do not widen the
    list role set as a shortcut; a host-scoped read is a different query, not a
    wider permit". This is that different query. The queue —
    :func:`list_speaker_requests` — is untouched and still ``{admin,
    coordinator}``; it holds every host's request text for the unit, and handing
    one host the others' filings is what the narrower reading exists to prevent.

    The only predicate on identity is ``filed_by_user_id == principal.user_id``.
    There is deliberately no ``?host_id=`` parameter and no body: an id a caller
    supplies is caller-selected identity (MM-A01), and it would be convenient in
    exactly the way that defect always is. Nothing in the request selects whose
    rows come back.

    **A request filed before migration ``0033`` is listed by nobody**, including
    the host who filed it. Its ``filed_by_user_id`` is NULL, NULL means the filer
    is unknown, and unknown is not this caller — reading it as the caller, or
    falling back to the host unit when the filer is unknown, would republish the
    whole queue through this route. Nothing was backfilled, for the reason
    ``0033``'s docstring gives: an inferred filer is indistinguishable from a
    recorded one (ADR-0011 rule 1).

    **Nothing here reflects an invitation.** OQ-CBA-042 decided that an Event
    Host does not learn who declined, by any route, and that decision binds this
    one. The enforcement is structural rather than a filter somebody has to
    remember: this renders ``SpeakerRequestRow`` through the same :func:`_view`
    the queue uses, and that row carries no invitation, batch, count or response
    field to withhold in the first place. A wider row type is the change that
    would break it.

    What a host reads here is what :func:`create_speaker_request` already handed
    them when they filed: title, description, time, virtual flag, location,
    industries, roles, ``publication_status``, ``review_status`` and the two
    timestamps. No field is new. What is new is the *list* — that these requests
    are theirs — which is the whole of what this route discloses.

    Charges :data:`SPEAKER_REQUEST_READ_RATE_LIMIT`: a read is a read, and a
    second counter would be a number nobody asked for. Quota first, then
    authorization, then any row (ADR-0015). Reads ``MAX_ROWS + 1`` so
    ``truncated`` is answered by the same query rather than by a second count
    whose filters could drift from this one's.

    Raises:
        ApiError: 403 when the caller is not an Event Host in this unit — a
            coordinator included, since they hold the wider queue; 404 when the
            unit is not this tenant's; 429 when the minute's quota is spent.
    """
    charge_quota(session, principal, SPEAKER_REQUEST_READ_RATE_LIMIT)
    _authorize_speaker_request_own_read(session, principal, unit_id)

    rows = _requests.list_filed_by(
        session,
        tenant_id=principal.tenant_id,
        host_org_unit_id=unit_id,
        filed_by_user_id=principal.user_id,
        limit=MAX_ROWS + 1,
    )
    return SpeakerRequestListResponse(
        unit_id=unit_id,
        requests=[_view(unit_id, row) for row in rows[:MAX_ROWS]],
        truncated=len(rows) > MAX_ROWS,
    )
