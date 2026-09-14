"""The Event Host's own organization, and the Connector's directory of them.

PR #154 close-out, PLAN v2 finding 10, owner decision 4. Three unit-scoped
routes over migration ``0036``:

* ``GET /v1/units/{unit_id}/host/organization`` — an Event Host reads their
  own organization. See :func:`read_own_organization`.
* ``PUT /v1/units/{unit_id}/host/organization`` — an Event Host creates or
  updates it. See :func:`upsert_own_organization`.
* ``GET /v1/units/{unit_id}/host-organizations`` — a Speaker Connector reads
  the unit's directory. See :func:`list_host_organizations`.

The role sets are **disjoint**: ``{volunteer}`` against ``{admin,
coordinator}``, the same shape ``routers/speaker_requests.py`` draws between a
host's own filings and the Connector's queue, and for the same reason. The
directory carries every host's organization in the unit, so a host reading it
would learn which other groups are asking; the host routes carry exactly one
organization — the caller's — so a Connector reading them would learn nothing
the directory does not already say. Neither is a subset of the other, which is
why neither is expressible as a role added to a set.

An organization is a description, not a permit
===============================================
This is the sentence to read twice. Nothing here writes ``membership`` or
``resource_grant``, and no route anywhere consults these tables to decide what
a caller may see. Whose Speaker Requests a host reads is still
``event.filed_by_user_id == principal.user_id`` (migration ``0033``), exactly
as it was before this module existed. Two hosts in one organization do **not**
see each other's requests.

That is owner decision 4 in as many words — "organization modelled now,
enforcement per-user" — and it is enforced structurally rather than
remembered: ``smartmatch_persistence.host_organizations`` has no method that
returns another account's rows, and the host detail route in
``routers/speaker_requests.py`` filters on the principal's own id with no
organization arm.

Self-asserted, and the column that says so
===========================================
A host types their organization and nobody approves it. The member row
records that with ``granted_by_user_id = NULL``, which means *self-asserted* —
never "granted by nobody in particular". Nothing in this release can write a
non-NULL value, because nothing in this release can grant a membership; when a
coordinator can, a granted row will name them and the two states will be
distinguishable, which they would not be if the distinction were introduced
afterwards (ADR-0011 rule 1).

The consequence a caller has to handle: ``PUT`` refuses to add the caller to
an organization somebody else already created under the same name in the same
unit (``409 host_organization_name_taken``). Joining is a grant, and there is
nothing here entitled to make one.

Host power is server-side
=========================
The unit comes from the path, is loaded with ``load_unit_or_404`` inside the
caller's tenant, and is authorized against *that row's* path. The account is
``principal.user_id``. There is no ``user_id``, ``tenant_id`` or
``organization_id`` field on the request model and there must never be one: a
body naming its own subject is the caller-selected identity pattern (MM-A01),
and here it would let a host rewrite another host's organization.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from typing import Annotated, Final

from fastapi import APIRouter, Path, Response, status
from pydantic import BaseModel, Field, field_validator
from smartmatch_authz import OrgPath, Resource, assert_allowed
from smartmatch_persistence.host_organizations import (
    HostOrganizationMembershipRow,
    HostOrganizationRepository,
    HostOrganizationRow,
    HostOrganizationUnitConflictError,
)
from smartmatch_persistence.rate_limit import RateLimit
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from smartmatch_api.dependencies import CurrentPrincipal, DbSession, charge_quota
from smartmatch_api.errors import ApiError
from smartmatch_api.units import load_unit_or_404
from smartmatch_api.utils import utc_now

router = APIRouter(prefix="/v1/units", tags=["host-organizations"])

_organizations: Final[HostOrganizationRepository] = HostOrganizationRepository()

#: Who may read their own organization. ``volunteer`` — the stored role
#: ``smartmatch_domain.role_presentation`` maps onto the **Event Host**
#: persona, following customer §4 — and nobody else.
#:
#: ``admin`` and ``coordinator`` are deliberately absent, for the reason
#: ``_SPEAKER_REQUEST_OWN_READ_ROLES`` gives about its own absences: they hold
#: the directory below, which is strictly wider, so this route would tell them
#: only which of the unit's organizations they personally typed. A second door
#: onto rows already reachable is a second thing to narrow the day the first
#: one narrows.
_HOST_ORGANIZATION_READ_OWN_ROLES: Final[frozenset[str]] = frozenset({"volunteer"})

#: Who may write their own organization. The same membership as the read, and
#: a **separate constant** rather than a share of it.
#:
#: Separate because a read and a write are two decisions, and one constant
#: would make a widening of either a widening of both. They agree today; the
#: rule ``tests/authz/test_route_roles.py`` states about its own ledger is that
#: several role sets agreeing today is not a reason to fuse them.
_HOST_ORGANIZATION_WRITE_OWN_ROLES: Final[frozenset[str]] = frozenset({"volunteer"})

#: Who may read the unit's directory of organizations. The Speaker Connector
#: persona, matching ``_SPEAKER_REQUEST_READ_ROLES``: a Connector reading an
#: incoming request needs to know who is asking, and the two reads answer one
#: workflow. ``volunteer`` is absent for the reason it is absent from the
#: request queue — the directory is every host's record, and handing one host
#: the others' is a widening no committed artifact supports.
_HOST_ORGANIZATION_LIST_ROLES: Final[frozenset[str]] = frozenset({"admin", "coordinator"})

#: The write carries the tighter limit, the relationship ``pipeline.py`` and
#: ``speaker_requests.py`` both draw between their pairs. Its own operation
#: name rather than a share of ``speaker_request.*``: a counter shared between
#: two operations makes one spend the other's budget.
HOST_ORGANIZATION_WRITE_RATE_LIMIT: Final[RateLimit] = RateLimit(
    operation="host_organization.write", max_requests=30, window=timedelta(minutes=1)
)
HOST_ORGANIZATION_READ_RATE_LIMIT: Final[RateLimit] = RateLimit(
    operation="host_organization.read", max_requests=120, window=timedelta(minutes=1)
)

#: The most organizations one directory response returns. G3 §2.2a's
#: 200-record cap, reused rather than a second number invented here —
#: ``routers/speaker_requests.py::MAX_ROWS`` is the same number for the same
#: reason.
MAX_ROWS: Final[int] = 200


# ---------------------------------------------------------------------------
# Request and response models
# ---------------------------------------------------------------------------


class HostOrganizationUpsert(BaseModel):
    """One organization, as an Event Host describes it.

    Note what is **not** here: no tenant, no unit, no user, no organization
    id, and no member list. The first three come from the verified principal
    and the path; the fourth is decided by whether this account already has an
    organization; the fifth is a membership grant and nothing in this release
    can make one.
    """

    name: str = Field(
        min_length=1,
        max_length=200,
        description=(
            "What the organization is called. Stored trimmed. Must be unique "
            "within the unit, case-insensitively: two rows for one club would "
            "split its requests with nothing to say they belong together."
        ),
    )
    department: str | None = Field(
        default=None,
        max_length=200,
        description=(
            "The department inside the organization, when there is one. Omit "
            "it, or send an empty string to clear it — either is stored as "
            "'they did not say' rather than as a blank."
        ),
    )
    default_location: str | None = Field(
        default=None,
        max_length=500,
        description="Where this organization's events usually happen. Free text.",
    )
    logistics_contact: str | None = Field(
        default=None,
        max_length=500,
        description=(
            "Who to reach about logistics on the day. Free text, and "
            "deliberately not a contact channel: nothing sends to it, nothing "
            "treats it as an address, and it grants no consent."
        ),
    )

    @field_validator("name")
    @classmethod
    def name_is_not_blank(cls, value: str) -> str:
        """Refuse a name that is only whitespace, as ``min_length`` cannot.

        ``"   "`` is three characters and passes ``min_length=1``; the
        repository then trims it to ``""``, which
        ``ck_host_organization_name_shape`` refuses — and the ``IntegrityError``
        would surface as ``409 host_organization_name_taken``, an answer that
        claims another host holds a name nobody holds. A blank name is a
        malformed request, so it is refused here as a 422 like every other
        field-level failure. The value is returned untrimmed: the repository
        owns storage trimming.
        """
        if not value.strip():
            raise ValueError("name must not be blank")
        return value


class HostOrganizationView(BaseModel):
    """One organization, read back from the row that was written."""

    unit_id: uuid.UUID
    organization_id: uuid.UUID
    name: str
    department: str | None = None
    default_location: str | None = None
    logistics_contact: str | None = None
    member_count: int = Field(
        description=(
            "How many accounts belong to this organization. A count, never "
            "the accounts: who belongs to an organization is a second question "
            "and neither of these surfaces answers it."
        )
    )
    created_at: datetime
    updated_at: datetime


class HostOwnOrganizationResponse(BaseModel):
    """The caller's organization, plus what this caller's own place in it is."""

    organization: HostOrganizationView
    self_asserted: bool = Field(
        description=(
            "True when this membership was asserted by the member rather than "
            "granted by a coordinator. Every membership is self-asserted in "
            "this release; nothing can grant one yet."
        )
    )
    member_since: datetime = Field(description="When this account joined the organization.")


class HostOrganizationListResponse(BaseModel):
    """The unit's organizations, as a Speaker Connector reads them."""

    unit_id: uuid.UUID
    organizations: list[HostOrganizationView]
    truncated: bool = Field(
        description="True when more organizations exist than the response cap returns."
    )


# ---------------------------------------------------------------------------
# Authorization
# ---------------------------------------------------------------------------


def _authorize_host_organization_read_own(
    session: Session,
    principal: CurrentPrincipal,
    unit_id: uuid.UUID,
) -> uuid.UUID:
    """Load the unit and authorize an Event Host's read of their own organization.

    The unit is loaded first and authorization runs against *that row's* path,
    never against anything in the request. ``load_unit_or_404`` scopes the
    lookup by the caller's own tenant, so a unit in another tenant is a 404
    rather than a 403 that would confirm the id names something real.

    No ``require_membership`` — the role set is non-empty, so ``evaluate``
    already refuses a bare ``resource_grant`` on the required-roles check
    (S-007). No ``tenant_wide_roles``: an organization is a record in one
    unit's own directory.

    Note what this does **not** decide. A permit here says this principal may
    call the route against this unit; it says nothing about *whose*
    organization comes back, and it cannot — ``evaluate`` reasons about
    principals and paths, not about rows. The self-scoping is
    :func:`read_own_organization`'s own predicate, which is why that function
    passes ``principal.user_id`` and why nothing in the request can name an
    account.
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
        required_roles=_HOST_ORGANIZATION_READ_OWN_ROLES,
    )
    return unit_id


def _authorize_host_organization_write_own(
    session: Session,
    principal: CurrentPrincipal,
    unit_id: uuid.UUID,
) -> uuid.UUID:
    """Load the unit and authorize an Event Host's write of their own organization.

    Its own function rather than a share of the read's, even though the two
    load the same row the same way and name role sets that agree today: one
    helper taking the role set as an argument would make a single call site the
    place both could be widened from, which is the rule
    ``tests/authz/test_route_roles.py`` states about its own ledger.
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
        required_roles=_HOST_ORGANIZATION_WRITE_OWN_ROLES,
    )
    return unit_id


def _authorize_host_organization_list(
    session: Session,
    principal: CurrentPrincipal,
    unit_id: uuid.UUID,
) -> uuid.UUID:
    """Load the unit and authorize a Speaker Connector's read of the directory.

    A third function beside the two above, and here the sets do not even agree
    — this one is *disjoint* from theirs, which is the shape of the decision
    rather than an accident of layout.
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
        required_roles=_HOST_ORGANIZATION_LIST_ROLES,
    )
    return unit_id


# ---------------------------------------------------------------------------
# Views
# ---------------------------------------------------------------------------


def _view(row: HostOrganizationRow) -> HostOrganizationView:
    """Render one stored organization. Never assembled from a request body."""
    return HostOrganizationView(
        unit_id=row.unit_id,
        organization_id=row.organization_id,
        name=row.name,
        department=row.department,
        default_location=row.default_location,
        logistics_contact=row.logistics_contact,
        member_count=row.member_count,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _own_view(membership: HostOrganizationMembershipRow) -> HostOwnOrganizationResponse:
    """Render the caller's membership and the organization behind it."""
    return HostOwnOrganizationResponse(
        organization=_view(membership.organization),
        self_asserted=membership.self_asserted,
        member_since=membership.member_since,
    )


def _no_organization_yet() -> ApiError:
    """The 404 a host gets before they have described an organization.

    A 404 with a body rather than a 200 with ``null``: "you have no
    organization" is the absence of the resource this URL names, and a 200
    would make every client's "did it load?" and "do they have one?" the same
    question. The code is stable and the message is the one a person reads.
    """
    return ApiError(
        status_code=status.HTTP_404_NOT_FOUND,
        code="host_organization_not_found",
        message=(
            "You have not described an organization for this department yet. "
            "PUT this URL to create one."
        ),
    )


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.get(
    "/{unit_id}/host/organization",
    response_model=HostOwnOrganizationResponse,
    summary="Read this Event Host's organization",
    responses={
        404: {
            "description": (
                "This account has no organization in this unit — either none at "
                "all, or one that files into a different department. Both answer "
                "`host_organization_not_found`."
            )
        }
    },
)
def read_own_organization(
    principal: CurrentPrincipal,
    session: DbSession,
    unit_id: Annotated[uuid.UUID, Path()],
) -> HostOwnOrganizationResponse:
    """Return the organization **this caller** belongs to in this unit.

    The only predicate on identity is ``principal.user_id``. There is
    deliberately no ``?user_id=`` parameter: an id a caller supplies is
    caller-selected identity (MM-A01), and it would be convenient in exactly
    the way that defect always is.

    A host whose organization files into a **different** unit gets the same
    404 as a host with no organization at all. That is not a lost distinction
    — it is the honest answer to the question this URL asks, which is "what is
    my organization *in this department*". Publishing "you have one, but
    elsewhere" from a route the caller was authorized against one unit for
    would report the existence of a row in a department nobody authorized them
    against.

    Charges :data:`HOST_ORGANIZATION_READ_RATE_LIMIT`. Quota first, then
    authorization, then any row (ADR-0015).

    Raises:
        ApiError: 403 when the caller is not an Event Host in this unit — a
            coordinator included, since they hold the wider directory; 404
            when the unit is not this tenant's, or when this caller has no
            organization here; 429 when the minute's quota is spent.
    """
    charge_quota(session, principal, HOST_ORGANIZATION_READ_RATE_LIMIT)
    _authorize_host_organization_read_own(session, principal, unit_id)

    membership = _organizations.membership_for_user(
        session, tenant_id=principal.tenant_id, user_id=principal.user_id
    )
    if membership is None or membership.organization.unit_id != unit_id:
        raise _no_organization_yet()
    return _own_view(membership)


@router.put(
    "/{unit_id}/host/organization",
    status_code=status.HTTP_201_CREATED,
    response_model=HostOwnOrganizationResponse,
    summary="Create or update this Event Host's organization",
    responses={
        200: {"description": "The caller's existing organization was updated."},
        201: {"description": "A new organization was created and the caller joined it."},
        409: {
            "description": (
                "Either this unit already holds an organization with this name "
                "(`host_organization_name_taken`), or the caller's one "
                "organization files into a different unit "
                "(`host_organization_unit_conflict`)."
            )
        },
    },
)
def upsert_own_organization(
    principal: CurrentPrincipal,
    session: DbSession,
    body: HostOrganizationUpsert,
    unit_id: Annotated[uuid.UUID, Path()],
    response: Response,
) -> HostOwnOrganizationResponse:
    """Describe the organization this Event Host is asking on behalf of.

    ``201``: this call created the organization and wrote the caller's member
    row with ``granted_by_user_id = NULL`` — self-asserted, because nothing in
    this release can grant a membership.

    ``200``: the caller already belonged to an organization in this unit and
    this call updated its description. The member row is untouched:
    re-describing your club is not re-joining it.

    A ``PUT`` rather than a ``POST`` because the URL names one resource — *the
    caller's organization in this unit* — and this replaces its description.
    It is idempotent in the way that matters: sending the same body twice
    leaves one organization with those values, and the status code says which
    of the two calls created it.

    ``409`` in two distinguishable shapes, and neither is a case this route
    should guess its way through:

    * ``host_organization_name_taken`` — another host already created an
      organization with this folded name in this unit. Adding the caller to it
      would be granting a membership, which nothing in this release is
      entitled to do.
    * ``host_organization_unit_conflict`` — the caller's one organization
      files into a different department. Moving it would move every other
      member with it, and none of them asked.

    Quota is charged first, before the unit is loaded and before authorization
    runs (ADR-0015).

    Raises:
        ApiError: 403 when the caller is not an Event Host in this unit; 404
            when the unit is not this tenant's; 409 in the two shapes above;
            429 when the minute's quota is spent.
    """
    charge_quota(session, principal, HOST_ORGANIZATION_WRITE_RATE_LIMIT)
    _authorize_host_organization_write_own(session, principal, unit_id)

    try:
        result = _organizations.upsert_for_user(
            session,
            tenant_id=principal.tenant_id,
            unit_id=unit_id,
            # The verified principal, never a body field.
            user_id=principal.user_id,
            name=body.name,
            department=body.department,
            default_location=body.default_location,
            logistics_contact=body.logistics_contact,
        )
        session.commit()
    except HostOrganizationUnitConflictError as exc:
        session.rollback()
        raise ApiError(
            status_code=status.HTTP_409_CONFLICT,
            code="host_organization_unit_conflict",
            message=(
                "This account already belongs to an organization that files into a "
                "different department. An organization belongs to the department it "
                "was created in; moving it would move every other member with it."
            ),
        ) from exc
    except IntegrityError as exc:
        # `uq_host_organization_unit_name`. Caught rather than pre-checked with
        # a SELECT: a check-then-insert is a race, and the constraint is the
        # only place the answer is authoritative.
        session.rollback()
        raise ApiError(
            status_code=status.HTTP_409_CONFLICT,
            code="host_organization_name_taken",
            message=(
                "This department already has an organization with that name. Joining "
                "it is a membership a coordinator grants, and nothing can grant one "
                "yet — use a name that distinguishes your group, or ask the Speaker "
                "Connector."
            ),
        ) from exc

    if not result.created:
        # FastAPI stamped 201 from the decorator; this call updated an
        # organization that was already there, and saying "created" of it would
        # make an edit indistinguishable from a first description.
        response.status_code = status.HTTP_200_OK
    return _own_view(result.membership)


@router.get(
    "/{unit_id}/host-organizations",
    response_model=HostOrganizationListResponse,
    summary="List the organizations that file Speaker Requests into this unit",
)
def list_host_organizations(
    principal: CurrentPrincipal,
    session: DbSession,
    unit_id: Annotated[uuid.UUID, Path()],
) -> HostOrganizationListResponse:
    """Return this unit's host organizations, by folded name (Speaker Connector).

    What this discloses is what a host typed about their own group: its name,
    its department, where they usually meet, who to ask about logistics, and
    how many accounts belong to it. What it does **not** disclose is *which*
    accounts — no member list, no email, no name of a person. A Connector who
    needs to reach a host reaches them through the request they filed.

    Reads :data:`MAX_ROWS` + 1 rows so ``truncated`` is answered by the same
    query rather than by a second count whose filters could drift from this
    one's.

    Raises:
        ApiError: 403 when the caller is not a Speaker Connector in this unit
            — an Event Host included, since the directory is every host's
            record; 404 when the unit is not this tenant's; 429 when the
            minute's quota is spent.
    """
    charge_quota(session, principal, HOST_ORGANIZATION_READ_RATE_LIMIT)
    _authorize_host_organization_list(session, principal, unit_id)

    rows = _organizations.list_for_unit(
        session,
        tenant_id=principal.tenant_id,
        unit_id=unit_id,
        limit=MAX_ROWS + 1,
    )
    return HostOrganizationListResponse(
        unit_id=unit_id,
        organizations=[_view(row) for row in rows[:MAX_ROWS]],
        truncated=len(rows) > MAX_ROWS,
    )
