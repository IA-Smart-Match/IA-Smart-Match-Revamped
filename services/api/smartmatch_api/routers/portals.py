"""The authenticated account-to-portal mapping: ``GET /v1/me/portals``.

The portal shells in ``apps/web/legacy-frontend`` needed one thing this API
did not provide, and said so in the UI: "The coordinator portal is unavailable
until the API provides an authenticated account-to-portal mapping"
(``lib/api.ts``'s ``PortalSubjectUnavailableError``). This route is that
mapping.

## Why it hangs off ``/v1/me`` and takes no parameter

Because the answer is *about the caller*, and a route that took a portal id
would be back to the archived defect. ``bdce024:src/api/routers/portals.py:435``
let a browser name the subject whose portal it wanted; MM-A01 archived it, and
``lib/principal.ts`` refused to reopen it from the client side by returning
``null`` rather than passing ``me.user_id`` off as a legacy portal record id.
The fix for that is not a better id to pass — it is a route with nothing to
pass. ``GET /v1/me/portals`` has no path parameter, no query parameter, and no
body, so there is nothing on the request for a handler to read instead of the
verified principal.

There is deliberately **no** ``/api/portals/{id}``, and this route is not a
step toward one.

## The mapping is over roles the server assigned, and only active ones

Every entry below is derived from ``principal.principal.memberships`` — the
``membership`` rows :class:`~smartmatch_persistence.principals.PrincipalRepository`
loaded for the caller's own subject — filtered to those in force at the
instant of the response. A membership that has expired grants nothing, and a
portal listed for an expired membership would be a door the rest of the API
would then refuse to open, which is worse than not listing it.

Blank roles are skipped for the reason ``smartmatch_authz.policy``'s rule 6
gives: ``membership.role`` is ``NOT NULL`` free text with no non-blank CHECK,
so a blank-role row is storable out of band, and "a membership with a blank
role is not a membership *with a role*".

## Listing a portal is not authorization

Nothing here widens what the caller may do. Every ``/v1`` operation still runs
its own :func:`smartmatch_authz.assert_allowed` against the resource it
loaded, and the policy matrix still holds each of those to a role set. This
route reports which shells are worth *rendering*; deny-by-default decides what
they can then fetch. A caller who edited the response to add a portal would
get a shell whose every request is refused — which is the correct failure
mode, and the reason this route needs no authorization of its own.

## Resolved unit ids, not just a path

A portal is not usable without one more thing, and its absence was a real gap:
``GET /v1/me`` reports a membership's ``granted_path``, an ``ltree``, while
every unit-scoped route — ``/v1/units/{unit_id}/metrics``, ``/imports``,
``/events``, ``/match-runs``, ``/rewards`` — takes a ``unit_id``. Nothing in
this API joined the two, so a signed-in coordinator could reach a portal and
still have no way to name the unit whose metrics they are entitled to read
without going outside the API for the id.

So each descriptor carries ``units``: the ``org_unit`` rows at or below the
granting membership's path, resolved server-side by
:func:`~smartmatch_api.units.units_in_subtree`, shallowest first, plus a
``default_unit_id`` naming the first of them. The browser therefore never
constructs, guesses, or supplies a unit id — it is handed the ones its own
memberships already authorize, which is the same reason the portal itself is
reported rather than derived.

``units`` may legitimately be **empty**, and ``default_unit_id`` ``null`` with
it: a membership can be granted over a path that no ``org_unit`` row occupies.
That is reported as the absence it is. Inventing a unit to fill the field
would hand a portal an id that every authorized route would then refuse.

## What an unmapped role does, and why nothing is invented for it

:data:`_PORTAL_FOR_ROLE` maps exactly the four roles this pilot seeds. A
membership carrying any other role contributes **no** portal — it is not
guessed into the nearest one and not dropped into a default. The account then
receives an empty ``portals`` list and a null ``default_portal``, and the
frontend says plainly that no portal is mapped to the roles the server
assigned. An invented portal would be a fabricated capability (ADR-0011's
shape applied to access rather than to numbers), and a default would be the
worst version of it, because the wrong portal is indistinguishable from the
right one until something inside it is refused.
"""

from __future__ import annotations

import uuid
from typing import Final

from fastapi import APIRouter
from pydantic import BaseModel, Field
from smartmatch_authz import Membership
from sqlalchemy.orm import Session

from smartmatch_api.dependencies import CurrentPrincipal, DbSession
from smartmatch_api.units import units_in_subtree
from smartmatch_api.utils import utc_now

router = APIRouter(prefix="/v1/me/portals", tags=["identity"])


class PortalUnit(BaseModel):
    """One org unit the granting membership covers, with the id routes need."""

    unit_id: uuid.UUID = Field(
        description=(
            "The `unit_id` every `/v1/units/{unit_id}/...` route takes. Resolved by "
            "the server from the granting membership's path; a client never "
            "constructs or supplies one."
        )
    )
    path: str = Field(description="The unit's own ltree path.")
    unit_type: str = Field(description="The unit's type, e.g. `program`.")
    display_name: str = Field(description="The unit's human-readable name.")


class PortalDescriptor(BaseModel):
    """One portal the caller's server-assigned roles actually open."""

    portal: str = Field(
        description="Stable portal identifier: `student`, `coordinator`, `volunteer`, or `admin`."
    )
    display_name: str = Field(description="Human-readable name for the portal.")
    home_path: str = Field(
        description=(
            "The frontend route this portal's shell is mounted at. Reported by the "
            "server so the browser navigates to a portal it was actually granted, "
            "rather than deriving a path from a role it read for itself."
        )
    )
    role: str = Field(
        description=(
            "The `membership.role` that opened this portal — the row an administrator "
            "wrote, echoed back so the UI can name it truthfully. It is never a value "
            "the caller supplied."
        )
    )
    org_unit_path: str = Field(
        description="The org-unit subtree the granting membership covers, as an ltree path."
    )
    units: list[PortalUnit] = Field(
        description=(
            "Every org unit at or below `org_unit_path`, shallowest first — the units "
            "this membership authorizes the caller over. Empty when the granted path "
            "contains no unit row, which is reported rather than filled in."
        )
    )
    default_unit_id: uuid.UUID | None = Field(
        description=(
            "The `unit_id` of the first entry in `units`, or null when there are none. "
            "A suggestion about which unit a portal should open with; it always names a "
            "unit already in `units`."
        )
    )


class MyPortalsResponse(BaseModel):
    """Every portal the caller may enter, and which one to open first.

    An empty list is a real, honest answer — the account holds no active
    membership whose role maps to a portal — and is not softened into a
    default.
    """

    portals: list[PortalDescriptor] = Field(
        description=(
            "One entry per active, role-bearing membership whose role maps to a portal. "
            "Empty when the caller holds none."
        )
    )
    default_portal: str | None = Field(
        description=(
            "The `portal` of the first entry, or null when there are none. A "
            "suggestion about where to land, never a grant: it names a portal that "
            "is already in `portals`."
        )
    )


#: The four roles this pilot seeds, and the shell each one opens. Enumerated
#: rather than inferred: there is no rule here that turns an unknown role into
#: a portal, which is what makes an unmapped role produce an empty list instead
#: of a plausible guess. Adding a role to this table is a deliberate act.
#:
#: ``admin`` maps to the IA-admin surface, which the frontend mounts on a
#: pathless layout route whose first page is ``/dashboard`` — hence a home path
#: that is not ``/admin-portal``. The path is reported by the server precisely
#: so that mismatch lives in one place rather than in every shell.
_PORTAL_FOR_ROLE: Final[dict[str, tuple[str, str, str]]] = {
    "student": ("student", "Student portal", "/student-portal"),
    "coordinator": ("coordinator", "Event coordinator portal", "/coordinator-portal"),
    "volunteer": ("volunteer", "Volunteer portal", "/volunteer-portal"),
    "admin": ("admin", "IA West admin", "/dashboard"),
}


def _descriptor_for(
    session: Session, *, tenant_id: uuid.UUID, membership: Membership
) -> PortalDescriptor | None:
    """The portal a single membership opens, or ``None`` when its role maps to none.

    Resolves the membership's path to real ``org_unit`` rows so the descriptor
    carries the ids unit-scoped routes require. The lookup is scoped to the
    caller's own tenant inside :func:`~smartmatch_api.units.units_in_subtree`,
    and the path comes from a ``membership`` row rather than from the request.
    """
    mapped = _PORTAL_FOR_ROLE.get(membership.role)
    if mapped is None:
        # Resolved only for a role that maps to a portal: an unmapped role
        # produces no descriptor, so querying units for it would be work whose
        # result nothing can read.
        return None

    portal, display_name, home_path = mapped
    granted_path = str(membership.granted_path)
    units = [
        PortalUnit(
            unit_id=unit.id,
            path=unit.path,
            unit_type=unit.unit_type,
            display_name=unit.display_name,
        )
        for unit in units_in_subtree(session, tenant_id=tenant_id, path=granted_path)
    ]

    return PortalDescriptor(
        portal=portal,
        display_name=display_name,
        home_path=home_path,
        role=membership.role,
        org_unit_path=granted_path,
        units=units,
        default_unit_id=units[0].unit_id if units else None,
    )


@router.get(
    "",
    response_model=MyPortalsResponse,
    summary="Get the portals the caller's server-assigned roles open",
)
def get_my_portals(principal: CurrentPrincipal, session: DbSession) -> MyPortalsResponse:
    """Return the caller's own account-to-portal mapping.

    Reads the memberships ``get_current_principal`` already resolved rather
    than re-reading them — the same reasoning ``routers/me.py`` gives: a second
    read of the *memberships* would open a window in which the two could
    disagree, leaving a caller authenticated as one principal and shown the
    portals of another.

    It does query ``org_unit``, which is a different thing and not that risk:
    the memberships are fixed for this request, and the unit rows are only
    being resolved *from* them. A unit added or removed mid-request changes
    which ids are reported, never whose portals they are.

    Quota is not charged, for ``routers/me.py``'s reason: this route answers
    from the resolution that authenticated the request, so a refusal here could
    impose no cost a caller has not already paid.
    """
    now = utc_now()

    descriptors: list[PortalDescriptor] = []
    seen: set[str] = set()
    for membership in principal.principal.memberships:
        if not membership.is_active_at(now):
            continue
        # policy rule 6: a blank role is not a role. Skipped here for the same
        # reason it is skipped there — a blank-role row is storable out of band,
        # and it must not open a door.
        if not membership.role.strip():
            continue
        descriptor = _descriptor_for(session, tenant_id=principal.tenant_id, membership=membership)
        # De-duplicated by portal, not by membership: two coordinator
        # memberships over different subtrees are two grants of the same shell,
        # and listing the shell twice would make the UI ask which one to open —
        # a question with no meaning, since the shell is the same either way.
        # The first is kept, so the reported `org_unit_path` is a real covering
        # grant rather than a merged fiction.
        if descriptor is None or descriptor.portal in seen:
            continue
        seen.add(descriptor.portal)
        descriptors.append(descriptor)

    return MyPortalsResponse(
        portals=descriptors,
        default_portal=descriptors[0].portal if descriptors else None,
    )
