"""Organizational-unit lookup shared by command resources.

Every unit-scoped command authorizes against the unit's ``ltree`` path, so every
one of them needs to load the unit first. That lookup is here rather than
repeated, mainly so the 404-versus-403 decision is made once and made the same
way everywhere.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

import sqlalchemy as sa
from fastapi import status
from smartmatch_persistence import schema
from sqlalchemy.orm import Session

from smartmatch_api.errors import ApiError

__all__ = ["OrgUnitRow", "load_unit_or_404"]


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
