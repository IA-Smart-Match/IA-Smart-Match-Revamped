"""Organizational-unit lookup shared by command resources.

Every unit-scoped command authorizes against the unit's ``ltree`` path, so every
one of them needs to load the unit first. That lookup is here rather than
repeated, mainly so the 404-versus-403 decision is made once and made the same
way everywhere.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Final

import sqlalchemy as sa
from fastapi import status
from smartmatch_persistence import schema
from sqlalchemy.orm import Session

from smartmatch_api.errors import ApiError

__all__ = ["MAX_SUBTREE_UNITS", "OrgUnitRow", "load_unit_or_404", "units_in_subtree"]

#: Most units one membership's subtree may report through
#: :func:`units_in_subtree`. A membership rooted near the top of a large tree
#: covers a lot of units, and the caller of this function is a *mapping* route
#: whose job is to hand a portal something to act on — not to page through an
#: org chart. The bound is applied in SQL, and a caller that hits it gets a
#: shorter list from a route that says how many it asked for, rather than a
#: silently truncated one.
MAX_SUBTREE_UNITS: Final[int] = 50


@dataclass(frozen=True, slots=True)
class OrgUnitRow:
    """The parts of an org unit a command handler needs."""

    id: uuid.UUID
    path: str
    unit_type: str
    display_name: str


def load_unit_or_404(session: Session, *, tenant_id: uuid.UUID, unit_id: uuid.UUID) -> OrgUnitRow:
    """Load a unit within the caller's tenant, or raise 404.

    Scoped by ``tenant_id`` in the query itself, not filtered afterwards. A unit
    belonging to another tenant is indistinguishable from one that does not
    exist — returning 403 for the former would confirm its existence to a caller
    with no right to know.

    Raises:
        ApiError: 404 when no such unit exists in this tenant.
    """
    row = session.execute(
        sa.select(
            schema.org_unit.c.id,
            sa.cast(schema.org_unit.c.path, sa.Text).label("path"),
            schema.org_unit.c.unit_type,
            schema.org_unit.c.display_name,
        ).where(
            schema.org_unit.c.tenant_id == tenant_id,
            schema.org_unit.c.id == unit_id,
        )
    ).one_or_none()

    if row is None:
        raise ApiError(
            status_code=status.HTTP_404_NOT_FOUND,
            code="unit_not_found",
            message="No such organizational unit.",
        )

    return OrgUnitRow(
        id=row.id,
        path=row.path,
        unit_type=row.unit_type,
        display_name=row.display_name,
    )


def units_in_subtree(
    session: Session, *, tenant_id: uuid.UUID, path: str, limit: int = MAX_SUBTREE_UNITS
) -> list[OrgUnitRow]:
    """Every unit at or below ``path``, within one tenant, shallowest first.

    This is the resolution step that was missing between "who am I" and "which
    unit do I read". ``GET /v1/me`` reports a membership's ``granted_path``
    (an ``ltree``), and every unit-scoped route — metrics, imports, events,
    match runs, rewards — takes a ``unit_id`` (a UUID). Nothing joined the two,
    so a signed-in coordinator could not get from their own identity to a unit
    they may act on without reading the database directly. That gap is why
    ``GET /v1/me/portals`` returns resolved ids rather than a path: a browser
    that had to turn a path into an id would be constructing an identifier the
    server should be supplying, which is the caller-supplied-subject shape in
    a new place.

    Containment is the ``ltree`` ``<@`` operator, which is the same
    label-wise, inclusive rule :meth:`smartmatch_authz.OrgPath.contains`
    applies in policy — deliberately, so the units this reports are exactly the
    units that membership will actually authorize. String prefix matching
    would not be: ``'cpp.eng'`` is a text prefix of ``'cpp.english'`` and is
    not an ancestor of it, and the GiST index (v1.1 §2.2) exists to make the
    real operator cheap.

    Scoped by ``tenant_id`` in the query itself, as ``load_unit_or_404`` is.

    Args:
        session: The request session.
        tenant_id: The caller's own tenant, resolved server-side.
        path: The membership's ``granted_path``. Bound as a parameter and cast
            to ``ltree`` by PostgreSQL — never interpolated, so a path that
            arrived from a database row cannot become SQL.
        limit: At most this many units. See :data:`MAX_SUBTREE_UNITS`.

    Returns:
        The units, ordered by path length then path, so the shallowest — the
        one a portal should default to — is first. Empty when the membership's
        subtree contains no unit row at all, which is a real answer: a
        membership may be granted over a path that no ``org_unit`` occupies,
        and inventing a unit for it would be worse than reporting none.
    """
    rows = session.execute(
        sa.select(
            schema.org_unit.c.id,
            sa.cast(schema.org_unit.c.path, sa.Text).label("path"),
            schema.org_unit.c.unit_type,
            schema.org_unit.c.display_name,
        )
        .where(
            schema.org_unit.c.tenant_id == tenant_id,
            # `<@` is "is contained by", inclusive of the root itself.
            schema.org_unit.c.path.op("<@")(sa.cast(sa.literal(path), schema.LTree())),
        )
        .order_by(
            sa.func.nlevel(schema.org_unit.c.path),
            sa.cast(schema.org_unit.c.path, sa.Text),
        )
        .limit(limit)
    ).all()

    return [
        OrgUnitRow(
            id=row.id,
            path=row.path,
            unit_type=row.unit_type,
            display_name=row.display_name,
        )
        for row in rows
    ]
