"""The caller's own identity, tenant, and server-assigned memberships.

This route closes the observable half of stakeholder Fix #7 — "no real login:
the user picks their own role". The legacy frontend read a role out of the
browser (``bdce024:src/api/routers/portals.py:435``, archived as MM-A01), which
made "who am I" whatever the caller claimed. Here it is the opposite: role
comes from a :class:`~smartmatch_authz.Membership` row an administrator wrote,
resolved server-side from the verified bearer token by
:func:`~smartmatch_api.dependencies.get_current_principal` onto a
:class:`~smartmatch_persistence.principals.ResolvedPrincipal` *before this
handler ever runs*. This route's entire job is to hand that resolution back to
the caller instead of leaving the frontend to guess it.

## Why there is no authorization call here

Every other route in this package loads a resource and calls
``assert_allowed`` or an ``authorize_*`` helper against it — see
``routers/jobs.py`` and ``routers/imports.py``. This route has no resource to
authorize against: there is no path parameter naming a tenant, a unit, or
another account, and every field in the response is keyed by the caller's own
verified subject. "May this principal read this principal's own identity" is
not a policy question — :func:`smartmatch_authz.evaluate` decides whether a
principal may reach a *resource*, and there is no ``Resource`` to construct
here that would not just be a roundabout restatement of "are you you".
Authentication is the entire gate: any principal ``get_current_principal``
resolves — suspended accounts included, per its own docstring — may read their
own identity back. That is deliberate, not an oversight: a suspended caller
needs to be able to tell it is suspended, not receive a second, differently
shaped 401 for asking.

## What must never appear here (MM-A01)

``user_id``, ``tenant_id``, ``email`` and every membership come from the
verified token's subject and the database rows that subject resolves to via
:class:`~smartmatch_persistence.principals.PrincipalRepository` — never from a
request header, a query parameter, or a body. There being no route parameters
at all is what makes that easy to keep true: there is nothing on the request
for a handler to be tempted to read instead.

## Why nothing here is fetched twice

``get_current_principal`` already ran the one query this route needs —
``PrincipalRepository.load_by_subject`` loads the account row and every
membership row in the same resolution that produced the ``CurrentPrincipal``
dependency. Querying again here would be re-deriving a value the dependency
already computed, and would open a window in which the two reads could
disagree (a membership revoked between the two queries would leave the caller
authenticated as one principal and shown another). The handler below reads
``principal.principal.memberships`` — the tuple ``PrincipalRepository`` already
built — rather than issuing anything of its own.

## Quota

Not charged. ADR-0015 governs *command* routes, where charging before a
refusal matters because the refusal still cost something to attempt. This
route answers from the principal ``get_current_principal`` already resolved to
authenticate the request at all, so there is no additional cost a refusal
could impose. ``routers/jobs.py``'s two read routes set the same precedent:
neither ``GET /v1/jobs/{job_id}`` nor its event stream charges quota.

## What is deliberately not returned

Explicit ``resource_grant`` rows are not included. The task names this route
as returning "identity, tenant, and server-assigned memberships"
specifically — a resource grant is a narrower, per-resource exception an
administrator carved out, not part of the caller's standing identity, and
surfacing it here would give this route a second shape the day someone wants
to show a caller their grants deliberately, rather than as a side effect of
this one. Nothing about *other* accounts, *other* tenants, or internal opaque
ids beyond the caller's own is exposed either: every field below is a value
the caller already necessarily knows they hold (their own account id, their
own tenant, their own email) or a row recorded because it grants *them*
something.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter
from pydantic import BaseModel, Field

from smartmatch_api.dependencies import CurrentPrincipal
from smartmatch_api.utils import utc_now

router = APIRouter(prefix="/v1/me", tags=["identity"])


class MembershipResponse(BaseModel):
    """One server-assigned membership, exactly as ``membership`` recorded it."""

    org_unit_path: str = Field(
        description=(
            "Dotted path in the org tree this membership covers, e.g. 'iawest.cpp.engineering'"
        )
    )
    role: str = Field(description="The role held over that subtree")
    valid_from: str | None = Field(
        default=None,
        description="ISO-8601 inclusive start of the validity window, or null for no lower bound",
    )
    valid_until: str | None = Field(
        default=None,
        description="ISO-8601 exclusive end of the validity window, or null for no upper bound",
    )
    #: Computed against the request's own clock rather than left for the client
    #: to derive: the client would otherwise have to reimplement
    #: `Membership.is_active_at` (inclusive start, exclusive end) to answer "is
    #: this the caller's role right now", which is precisely the guesswork this
    #: route exists to remove.
    is_active: bool = Field(description="Whether this membership is in force as of this response")


class MeResponse(BaseModel):
    """The caller's own identity, tenant, and server-assigned memberships.

    Nothing here is caller-supplied (MM-A01): every field is either the
    verified subject itself or a database row keyed by that subject.
    """

    user_id: uuid.UUID = Field(description="This account's local id")
    tenant_id: uuid.UUID = Field(description="The tenant this account belongs to")
    email: str = Field(description="This account's own email address")
    memberships: list[MembershipResponse] = Field(
        description=(
            "Every membership row granted to this account, active or not — "
            "filtering by validity is the client's choice, so `is_active` is "
            "reported rather than the row being silently dropped"
        )
    )


@router.get("", response_model=MeResponse, summary="Get the caller's own identity")
def get_me(principal: CurrentPrincipal) -> MeResponse:
    """Return the caller's own identity, tenant, and server-assigned memberships.

    No path parameter, no query parameter, no body — there is nothing here for
    a caller to supply, and therefore nothing here for MM-A01 to reopen. Every
    field is read off the ``ResolvedPrincipal`` that authenticated this request.
    """
    now = utc_now()
    memberships = [
        MembershipResponse(
            org_unit_path=str(membership.granted_path),
            role=membership.role,
            valid_from=membership.valid_from.isoformat() if membership.valid_from else None,
            valid_until=membership.valid_until.isoformat() if membership.valid_until else None,
            is_active=membership.is_active_at(now),
        )
        for membership in principal.principal.memberships
    ]

    return MeResponse(
        user_id=principal.user_id,
        tenant_id=principal.tenant_id,
        email=principal.email,
        memberships=memberships,
    )
