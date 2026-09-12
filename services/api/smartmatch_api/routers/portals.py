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

## One descriptor per portal, merged deterministically

Two stored roles may open the *same* shell: ``coordinator`` and ``admin`` are
one persona (``smartmatch_domain.role_presentation``), and since the CBA pivot
they land in one place. An account holding both therefore has two memberships
contributing to one portal, and the response carries **one** descriptor for it,
not two — a list with the same shell twice would make the UI ask which one to
open, a question with no meaning.

Merging is total and order-independent, because ``membership`` rows arrive in
no defined order (``smartmatch_persistence.principals`` issues no ``ORDER BY``)
and an answer that depended on which row the database handed back first would
be a different response for the same account on two consecutive requests. So:

* ``role`` is the highest the caller actually holds for that portal, by the
  fixed precedence in :data:`_ROLE_PRIORITY`. It is still a stored string off a
  real row, never a merged fiction.
* ``org_unit_path`` is that same winning row's ``granted_path``, so the role
  and the path a reader sees came from *one* membership rather than from two
  spliced together.
* ``units`` is the union over every contributing membership, de-duplicated by
  ``unit_id`` and sorted by ``(path, unit_id)`` — the caller is authorized over
  all of them, and dropping the ones that came from the losing row would report
  less access than the server will actually honour.
* ``portals`` is ordered by :data:`_PORTAL_ORDER`, and ``default_portal`` is
  the first of them.

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
from smartmatch_domain.role_presentation import KNOWN_ROLES, portal_display_name_for_role
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
    roles: list[str] = Field(
        description=(
            "The stored `membership.role`s the caller actually holds **over this "
            "unit** — the roles whose granted subtree contains it — highest reach "
            "first. Reported per unit rather than only per portal because the two "
            "genuinely differ: an account that is `coordinator` over one subtree and "
            "`admin` over another opens one shell, and a single portal-level role "
            "would label every unit in the union with the stronger of the two. A "
            "route asked about the weaker unit would then refuse something the UI "
            "had shown as permitted."
        )
    )


class PortalDescriptor(BaseModel):
    """One portal the caller's server-assigned roles actually open."""

    portal: str = Field(
        description=(
            "Stable portal identifier: `student`, `coordinator`, or `volunteer`. There is "
            "no separate `admin` portal: the stored `admin` role opens the connector "
            "shell, and holding it is read from `GET /v1/me`'s memberships."
        )
    )
    display_name: str = Field(
        description=(
            "Human-readable name for the portal, from the single CBA "
            "role-presentation map (`smartmatch_domain.role_presentation`). A "
            "label only: it names the shell and never widens what the caller may do."
        )
    )
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
            "the caller supplied. When several of the caller's memberships open this "
            "same portal, it is the highest of them by reach (`admin` > `coordinator` "
            "> `volunteer` > `student`), and `org_unit_path` is that same row's path."
        )
    )
    roles: list[str] = Field(
        description=(
            "Every stored `membership.role` the caller holds that opens this portal, "
            "highest reach first — `role` is simply the first of them. Present because "
            "one shell can now be opened by more than one role (`coordinator` and "
            "`admin` are one persona), and a reader that saw only the winner could not "
            "tell a connector who is also an administrator from one who is not."
        )
    )
    org_unit_path: str = Field(
        description=(
            "The org-unit subtree the granting membership covers, as an ltree path. One "
            "real membership's path — the same row `role` came from — never a merge of "
            "several. It is **not** a summary of everything this portal reaches: for "
            "that, read `units`, and read each unit's own `roles` for what is held "
            "over it."
        )
    )
    units: list[PortalUnit] = Field(
        description=(
            "Every org unit the memberships opening this portal authorize the caller "
            "over: the union of their subtrees, de-duplicated and ordered by path then "
            "id, so ancestors precede descendants and the order never varies between "
            "requests. Empty when no granted path contains a unit row, which is "
            "reported rather than filled in."
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
            "One entry per *portal* the caller's active, role-bearing memberships open "
            "— never two entries for one shell, however many memberships opened it. "
            "Ordered `coordinator`, `volunteer`, `student`. Empty when the caller holds "
            "no membership that opens a portal."
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
#: This table decides *routing* only — the stable portal id and the path its
#: shell is mounted at. What each portal is **called** is not here: it comes
#: from :mod:`smartmatch_domain.role_presentation`, the single CBA
#: role-presentation map the frontend's label helper mirrors. Splitting them
#: this way is what stops the wire from naming the same person one thing in a
#: portal header and another in a sidebar chip.
#:
#: ``admin`` and ``coordinator`` map to the **same** portal, because they are
#: the same persona (``smartmatch_domain.role_presentation``) and, since the
#: CBA pivot, the same shell: there is no separate administration surface to
#: land in, only an Administration section inside the connector shell that the
#: frontend shows when the caller holds ``admin``. Mapping ``admin`` to its own
#: portal at ``/dashboard`` is what split one person across two shells, and
#: what made an account holding both roles land in whichever membership the
#: database returned first.
#:
#: The table is therefore many-to-one over roles, and the merge in
#: :func:`get_my_portals` is what makes that safe. Two roles that share a portal
#: must agree about its home path — asserted at import below, so a future row
#: cannot introduce a portal with two homes.
#:
#: The keys are the **stored** ``membership.role`` strings, unchanged by the
#: CBA pivot. A permanent rename is a separate, deferred decision; presenting a
#: row as "Speaker Connector" while it still says ``coordinator`` is exactly
#: what the presentation map exists to do.
_PORTAL_FOR_ROLE: Final[dict[str, tuple[str, str]]] = {
    "student": ("student", "/student-portal"),
    "coordinator": ("coordinator", "/coordinator-portal"),
    "volunteer": ("volunteer", "/volunteer-portal"),
    # Not ``("admin", "/dashboard")``: see the note above. A held ``admin``
    # role is still visible to the frontend — it is on ``GET /v1/me``'s
    # ``memberships[].role`` — and that, not a second portal, is what reveals
    # the Administration section.
    "admin": ("coordinator", "/coordinator-portal"),
}

#: Stored roles in descending precedence, used when one portal is opened by
#: more than one of the caller's memberships. Highest wins the descriptor's
#: ``role`` and ``org_unit_path``.
#:
#: The order is by *reach*, which is the only ordering that does not lose
#: information: ``admin`` is tenant-wide where ``coordinator`` is subtree-scoped
#: (``smartmatch_authz.policy``), so reporting ``coordinator`` for an account
#: that also holds ``admin`` would understate a role the server did assign,
#: while the reverse never overstates one it did not — the descriptor only
#: echoes rows, and every route still authorizes for itself.
_ROLE_PRIORITY: Final[tuple[str, ...]] = ("admin", "coordinator", "volunteer", "student")

#: The order portals are listed in, and therefore which one ``default_portal``
#: names. Fixed here rather than left to membership order, because
#: ``smartmatch_persistence.principals`` loads memberships with no ``ORDER BY``:
#: an account holding two roles would otherwise land somewhere different on two
#: consecutive sign-ins, which is the landing bug in its purest form.
_PORTAL_ORDER: Final[tuple[str, ...]] = ("coordinator", "volunteer", "student")

if set(_ROLE_PRIORITY) != set(_PORTAL_FOR_ROLE):  # pragma: no cover - import-time assertion
    # A role with no precedence could not be merged deterministically, and a
    # precedence for a role that opens nothing is a rule nothing reads.
    raise RuntimeError(
        "role precedence and portal routing disagree about the stored roles: "
        f"{sorted(_ROLE_PRIORITY)} vs {sorted(_PORTAL_FOR_ROLE)}"
    )

if set(_PORTAL_ORDER) != {portal for portal, _home in _PORTAL_FOR_ROLE.values()}:
    # pragma: no cover - import-time assertion
    # A portal with no place in the order would be listed nondeterministically
    # (or not at all), which is exactly what the order exists to prevent.
    raise RuntimeError(
        "portal ordering and portal routing disagree about the portals: "
        f"{sorted(_PORTAL_ORDER)} vs "
        f"{sorted({portal for portal, _home in _PORTAL_FOR_ROLE.values()})}"
    )

_HOMES_PER_PORTAL: Final[dict[str, set[str]]] = {}
for _portal, _home in _PORTAL_FOR_ROLE.values():
    _HOMES_PER_PORTAL.setdefault(_portal, set()).add(_home)
if any(len(homes) != 1 for homes in _HOMES_PER_PORTAL.values()):  # pragma: no cover
    # Two roles sharing a portal but disagreeing about where it lives would
    # make the merged descriptor's `home_path` depend on which role won, i.e.
    # on data rather than on routing. Refused at import instead.
    raise RuntimeError(
        "one portal is mounted at two different home paths: "
        f"{ {portal: sorted(homes) for portal, homes in _HOMES_PER_PORTAL.items()} }"
    )

if set(_PORTAL_FOR_ROLE) != set(KNOWN_ROLES):  # pragma: no cover - import-time assertion
    # Routing and presentation must cover the same stored roles. A role with a
    # portal but no label would be listed with an empty name; a role with a
    # label but no portal would be a persona the product talks about and never
    # opens. Either is a silent half-decision, so it fails the import instead.
    raise RuntimeError(
        "portal routing and role presentation disagree about the stored roles: "
        f"{sorted(_PORTAL_FOR_ROLE)} vs {sorted(KNOWN_ROLES)}"
    )


def _winning_membership(memberships: list[Membership]) -> Membership:
    """The membership whose role and path the merged descriptor reports.

    Highest role by :data:`_ROLE_PRIORITY`, ties broken by the lowest
    ``granted_path``. The tie-break is not cosmetic: two ``coordinator``
    memberships over different subtrees are a real case, and without it the
    reported ``org_unit_path`` would be whichever row the database returned
    first.
    """
    return min(
        memberships,
        key=lambda membership: (
            _ROLE_PRIORITY.index(membership.role),
            str(membership.granted_path),
        ),
    )


def _ordered_roles(roles: set[str]) -> list[str]:
    """Stored roles in :data:`_ROLE_PRIORITY` order — highest reach first.

    A fixed order rather than the order rows arrived in, for the same reason
    the portal list has one: the same account must produce the same bytes on
    two consecutive requests.
    """
    return [role for role in _ROLE_PRIORITY if role in roles]


def _merged_units(
    session: Session, *, tenant_id: uuid.UUID, memberships: list[Membership]
) -> list[PortalUnit]:
    """Every unit the contributing memberships cover, once each, with its own roles.

    The union, not the winner's alone: the caller is authorized over all of
    them, and reporting only the units under the higher-precedence grant would
    hide access the routes will in fact honour — the mirror image of listing a
    portal that every route refuses.

    Each unit carries the roles **actually granted over it**, accumulated from
    every membership whose subtree contains it. That is the part a portal-level
    role cannot express: a caller who is ``coordinator`` over one subtree and
    ``admin`` over another holds one shell and two different reaches, and
    stamping the descriptor's winning role onto every unit would claim
    tenant-wide authority over units where only the subtree-scoped grant
    exists. The UI would then offer an action the route refuses, which is the
    fake-success shape applied to access.

    De-duplicated by ``unit_id`` because two granted paths may overlap, and
    ordered by ``(path, unit_id)`` so the same account gets the same list on
    every request. Ancestors still precede their descendants, since an ltree
    path sorts before any path it prefixes.
    """
    # Rows and roles are accumulated first and the descriptors built once,
    # rather than a model being constructed and then patched: a half-filled
    # `PortalUnit` that is correct only after a later loop is a shape a future
    # early return can ship.
    rows: dict[uuid.UUID, tuple[str, str, str]] = {}
    roles_by_unit: dict[uuid.UUID, set[str]] = {}
    for membership in memberships:
        for unit in units_in_subtree(
            session, tenant_id=tenant_id, path=str(membership.granted_path)
        ):
            rows.setdefault(unit.id, (unit.path, unit.unit_type, unit.display_name))
            roles_by_unit.setdefault(unit.id, set()).add(membership.role)

    return sorted(
        (
            PortalUnit(
                unit_id=unit_id,
                path=path,
                unit_type=unit_type,
                display_name=display_name,
                roles=_ordered_roles(roles_by_unit[unit_id]),
            )
            for unit_id, (path, unit_type, display_name) in rows.items()
        ),
        key=lambda unit: (unit.path, str(unit.unit_id)),
    )


def _descriptor_for(
    session: Session, *, tenant_id: uuid.UUID, portal: str, memberships: list[Membership]
) -> PortalDescriptor:
    """The single descriptor for one portal, merged over every membership opening it.

    Resolves the memberships' paths to real ``org_unit`` rows so the descriptor
    carries the ids unit-scoped routes require. The lookup is scoped to the
    caller's own tenant inside :func:`~smartmatch_api.units.units_in_subtree`,
    and every path comes from a ``membership`` row rather than from the request.
    """
    winner = _winning_membership(memberships)
    # Never ``None`` here: the import-time checks above pin routing,
    # precedence, and presentation to the same stored roles, and this line is
    # only reached for a role that mapped to ``portal``.
    display_name = portal_display_name_for_role(winner.role)
    if display_name is None:  # pragma: no cover - excluded by the import-time check
        # Unreachable while the tables agree, and raised rather than softened
        # to a placeholder if they somehow do not: a portal listed under an
        # invented name is the one failure mode this route refuses to produce.
        raise RuntimeError(f"no portal display name for stored role {winner.role!r}")

    units = _merged_units(session, tenant_id=tenant_id, memberships=memberships)

    return PortalDescriptor(
        portal=portal,
        display_name=display_name,
        home_path=_PORTAL_FOR_ROLE[winner.role][1],
        role=winner.role,
        roles=_ordered_roles({membership.role for membership in memberships}),
        org_unit_path=str(winner.granted_path),
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

    # Grouped by portal before anything is built, because the merge below is
    # over *all* of a portal's memberships at once. Collecting first and
    # deciding second is what makes the answer independent of the order the
    # rows arrived in.
    opening: dict[str, list[Membership]] = {}
    for membership in principal.principal.memberships:
        if not membership.is_active_at(now):
            continue
        # policy rule 6: a blank role is not a role. Skipped here for the same
        # reason it is skipped there — a blank-role row is storable out of band,
        # and it must not open a door.
        if not membership.role.strip():
            continue
        mapped = _PORTAL_FOR_ROLE.get(membership.role)
        if mapped is None:
            continue
        opening.setdefault(mapped[0], []).append(membership)

    descriptors = [
        _descriptor_for(
            session,
            tenant_id=principal.tenant_id,
            portal=portal,
            memberships=opening[portal],
        )
        for portal in _PORTAL_ORDER
        if portal in opening
    ]

    return MyPortalsResponse(
        portals=descriptors,
        default_portal=descriptors[0].portal if descriptors else None,
    )
