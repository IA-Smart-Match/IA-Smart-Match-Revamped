"""The Event Host's own organization: reads, one upsert, and one stamp.

Migration ``0036``. Two tables — ``host_organization`` and
``host_organization_member`` — plus the single ``UPDATE`` that records which
organization a newly filed Speaker Request was filed under.

Read this before building on it
================================
**None of this authorizes anything.** ``smartmatch_authz`` reads ``membership``
and ``resource_grant``, and nothing here writes either. Whose Speaker Requests
a caller may read is still decided by ``event.filed_by_user_id`` (migration
``0033``) and by nothing else. An organization is a description a host typed
about themselves; a *permit* is a thing a coordinator grants, and the day one
of these rows conveys reach, that will be a deliberate change to a route's
predicate rather than a consequence of this module existing.

``granted_by_user_id`` is where that future lives. Every row this module
writes carries ``NULL`` there, which means **self-asserted**: the host said so,
nobody checked. When a coordinator can grant membership, a granted row will
name them, and the two will be distinguishable — which they would not be if
the column were added later and the existing rows backfilled (ADR-0011 rule 1).

One organization per host
=========================
``uq_host_organization_member_user`` makes ``UNIQUE (user_id)`` true, so "the
caller's organization" is one row or none, never a list. That is what lets
:meth:`HostOrganizationRepository.membership_for_user` return a single value
rather than a collection the caller would have to disambiguate — and the
disambiguation is precisely where a bug would hide, because every reasonable
tie-break (newest, first, the one in this unit) is a guess.

The consequence for a unit-scoped route is real and is the caller's to handle:
a host whose one organization sits in another department has no organization
*in this unit*, and this module says so by returning the membership with its
own ``unit_id`` attached rather than by silently filtering it away. A filter
here would make "no organization" and "an organization somewhere else" the
same answer, and they are different things to tell a person.

Trimming, and why it happens here
=================================
The four text fields are stored ``strip``ped, and a field that strips to
nothing is stored as ``NULL`` rather than as ``""``. Both are one decision:
``ck_host_organization_name_shape`` and its three siblings refuse a blank, so
a form that posted ``"  "`` would otherwise be a 500 from a constraint rather
than an honest empty field. A host who cleared a box has cleared it, and
``NULL`` is what "they did not say" is spelled as everywhere else in this
schema.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.orm import Session

from smartmatch_persistence import schema


class HostOrganizationUnitConflictError(Exception):
    """Raised when a host's one organization belongs to a different unit.

    Not an integrity error the database would have raised on its own: the
    write this refuses is one the schema would happily accept, because
    ``uq_host_organization_member_user`` is satisfied by *updating* the
    existing member row. Silently re-homing a host's organization into
    whichever department they happened to post from is the behaviour this
    exists to refuse — it would move every other member of that organization
    with them, and none of them asked.
    """

    def __init__(self, *, organization_id: uuid.UUID, unit_id: uuid.UUID) -> None:
        super().__init__(
            f"This account already belongs to organization {organization_id}, "
            f"which files into unit {unit_id}."
        )
        self.organization_id = organization_id
        self.unit_id = unit_id


@dataclass(frozen=True, slots=True)
class HostOrganizationRow:
    """One organization, as both the host and the Connector read it.

    Carries no member list and no request list. A Connector reading a unit's
    organizations learns that they exist and what they say about themselves;
    who belongs to one is a second question with a second answer, and a row
    type that carried the members would make every reader of this one a reader
    of that.

    Attributes:
        organization_id: The organization.
        unit_id: The institution's org unit it files into — ``event``'s
            ``host_org_unit_id``, never the organization itself.
        name: What the host called it. Stored trimmed, never blank.
        department: The department inside the organization, or ``None``.
        default_location: Where their events usually happen, or ``None``.
        logistics_contact: Free text about who to reach on the day. **Not** a
            ``contact_channel``: no outreach path reads it, nothing treats it
            as an address, and it grants no consent.
        member_count: How many accounts belong to it. A count rather than the
            accounts, for the reason above.
        created_at: When the organization was first recorded.
        updated_at: When it was last written.
    """

    organization_id: uuid.UUID
    unit_id: uuid.UUID
    name: str
    department: str | None
    default_location: str | None
    logistics_contact: str | None
    member_count: int
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class HostOrganizationMembershipRow:
    """One account's place in one organization.

    Attributes:
        organization: The organization itself.
        user_id: The member.
        granted_by_user_id: ``None`` when the member asserted their own place
            in the organization, which is every row this release writes. A
            value names the coordinator who granted it.
        member_since: When the member row was written.
    """

    organization: HostOrganizationRow
    user_id: uuid.UUID
    granted_by_user_id: uuid.UUID | None
    member_since: datetime

    @property
    def self_asserted(self) -> bool:
        """``True`` when nobody granted this membership.

        A property rather than a stored column, so the two can never disagree.
        """
        return self.granted_by_user_id is None


@dataclass(frozen=True, slots=True)
class HostOrganizationWriteResult:
    """What one upsert did.

    Attributes:
        membership: The caller's membership after the write.
        created: ``True`` when this call created the organization (and the
            member row with it), ``False`` when it updated one the caller
            already belonged to. The route turns this into ``201`` or ``200``,
            which is how a caller learns which happened.
    """

    membership: HostOrganizationMembershipRow
    created: bool


def _clean(value: str | None) -> str | None:
    """Trim, and read an all-whitespace field as the absence it is."""
    if value is None:
        return None
    trimmed = value.strip()
    return trimmed or None


class HostOrganizationRepository:
    """Reads and writes ``host_organization`` and its member rows.

    Takes a session per call and commits nothing, like every other repository
    in this package.
    """

    # -----------------------------------------------------------------------
    # Reads
    # -----------------------------------------------------------------------

    def membership_for_user(
        self, session: Session, *, tenant_id: uuid.UUID, user_id: uuid.UUID
    ) -> HostOrganizationMembershipRow | None:
        """The caller's one organization, or ``None`` when they have none.

        Singular by construction: ``uq_host_organization_member_user`` allows
        one member row per account, so there is nothing here to disambiguate.

        **Not** filtered by unit. The membership carries its organization's own
        ``unit_id`` and the caller compares: "no organization" and "an
        organization in another department" are different things to tell a
        person, and a filter here would collapse them into one.
        """
        member = schema.host_organization_member
        rows = self._membership_rows(
            session,
            tenant_id=tenant_id,
            extra=(member.c.user_id == user_id,),
            limit=1,
        )
        return rows[0] if rows else None

    def get(
        self,
        session: Session,
        *,
        tenant_id: uuid.UUID,
        unit_id: uuid.UUID,
        organization_id: uuid.UUID,
    ) -> HostOrganizationRow | None:
        """One organization in one unit, or ``None``.

        Scoped by ``tenant_id`` **and** ``unit_id`` in the query rather than
        filtered afterwards: an organization in a department the caller was not
        authorized against must be indistinguishable from one that does not
        exist, which is the rule ``load_unit_or_404`` states for units.
        """
        organization = schema.host_organization
        rows = self._organization_rows(
            session,
            tenant_id=tenant_id,
            extra=(
                organization.c.unit_id == unit_id,
                organization.c.id == organization_id,
            ),
            limit=1,
        )
        return rows[0] if rows else None

    def list_for_unit(
        self, session: Session, *, tenant_id: uuid.UUID, unit_id: uuid.UUID, limit: int
    ) -> tuple[HostOrganizationRow, ...]:
        """This unit's organizations, by folded name then id, capped at ``limit``.

        Name order because a Connector reading a directory is looking one up,
        and ``id`` breaks ties so two organizations never swap places between
        two identical reads — which is also what makes a truncation cut at a
        stable point.

        The caller passes ``limit`` and decides what to do about a full page;
        this method says nothing about whether more exist, because a repository
        inventing a "truncated" flag would be a second opinion beside the
        route's own cap.
        """
        organization = schema.host_organization
        return self._organization_rows(
            session,
            tenant_id=tenant_id,
            extra=(organization.c.unit_id == unit_id,),
            limit=limit,
        )

    # -----------------------------------------------------------------------
    # Writes
    # -----------------------------------------------------------------------

    def upsert_for_user(
        self,
        session: Session,
        *,
        tenant_id: uuid.UUID,
        unit_id: uuid.UUID,
        user_id: uuid.UUID,
        name: str,
        department: str | None = None,
        default_location: str | None = None,
        logistics_contact: str | None = None,
    ) -> HostOrganizationWriteResult:
        """Create the caller's organization, or update the one they belong to.

        Two paths, and which one runs is decided by whether this account
        already has a member row — never by anything in the request:

        * **No member row.** One ``INSERT`` into ``host_organization`` and one
          into ``host_organization_member`` with ``granted_by_user_id = NULL``:
          the host asserted their own place in an organization they just
          described. If the unit already holds an organization with this
          folded name, ``uq_host_organization_unit_name`` refuses the insert
          and the ``IntegrityError`` reaches the route, which answers ``409``.
          That is deliberate: joining somebody else's organization is a
          membership grant, and nothing in this release can grant one.
        * **A member row in this unit.** One ``UPDATE`` of the organization's
          four descriptive fields. The member row is untouched — re-describing
          your club is not re-joining it, and rewriting ``created_at`` or
          ``granted_by_user_id`` here would erase the distinction the column
          exists to preserve.

        A member row in **another** unit raises
        :class:`HostOrganizationUnitConflictError` rather than re-homing the
        organization; see that class for why.

        Args:
            session: The caller's session. Not committed here.
            tenant_id: From the authenticated principal, never from a body.
            unit_id: The unit the router already authorized against.
            user_id: The account whose organization this is, from the verified
                principal. There is deliberately no parameter naming somebody
                else's: an id a caller supplies is caller-selected identity
                (MM-A01).
            name: Required and stored trimmed.
            department: Optional; an all-whitespace value is stored ``NULL``.
            default_location: Likewise.
            logistics_contact: Likewise.

        Returns:
            A :class:`HostOrganizationWriteResult`.

        Raises:
            HostOrganizationUnitConflictError: when the caller's organization
                files into a different unit.
        """
        existing = self.membership_for_user(session, tenant_id=tenant_id, user_id=user_id)
        fields: dict[str, str | None] = {
            "name": name.strip(),
            "department": _clean(department),
            "default_location": _clean(default_location),
            "logistics_contact": _clean(logistics_contact),
        }

        if existing is not None:
            if existing.organization.unit_id != unit_id:
                raise HostOrganizationUnitConflictError(
                    organization_id=existing.organization.organization_id,
                    unit_id=existing.organization.unit_id,
                )
            session.execute(
                sa.update(schema.host_organization)
                .where(
                    schema.host_organization.c.tenant_id == tenant_id,
                    schema.host_organization.c.id == existing.organization.organization_id,
                )
                .values(**fields, updated_at=sa.func.now())
            )
            refreshed = self.membership_for_user(session, tenant_id=tenant_id, user_id=user_id)
            if refreshed is None:  # pragma: no cover - written in this transaction
                raise RuntimeError("the organization was updated but could not be read back")
            return HostOrganizationWriteResult(membership=refreshed, created=False)

        organization_id = uuid.uuid4()
        session.execute(
            sa.insert(schema.host_organization).values(
                id=organization_id,
                tenant_id=tenant_id,
                unit_id=unit_id,
                **fields,
            )
        )
        session.execute(
            sa.insert(schema.host_organization_member).values(
                organization_id=organization_id,
                user_id=user_id,
                tenant_id=tenant_id,
                unit_id=unit_id,
                # Self-asserted. Not a default this call could be talked out
                # of: there is no parameter for a granter, because nothing in
                # this release is entitled to be one.
                granted_by_user_id=None,
            )
        )
        created = self.membership_for_user(session, tenant_id=tenant_id, user_id=user_id)
        if created is None:  # pragma: no cover - written in this transaction
            raise RuntimeError("the organization was created but could not be read back")
        return HostOrganizationWriteResult(membership=created, created=True)

    def stamp_event(
        self,
        session: Session,
        *,
        tenant_id: uuid.UUID,
        event_id: uuid.UUID,
        organization_id: uuid.UUID,
    ) -> None:
        """Record which organization a request was filed under.

        One ``UPDATE``, and the ``WHERE`` clause carries
        ``host_organization_id IS NULL`` so this can only ever write the fact
        for the first time. A stamp that overwrote an existing one would let a
        resubmission move a request from the organization it was filed under to
        the filer's organization today — the same reconstruction ``0033``
        declined to make about filers, and the reason the route only calls this
        for a request its own call **created**. OQ-CBA-065 (a resubmission by a
        different host under ADR-0012's identity key) is out of scope here and
        this write does not resolve it.

        The caller commits.
        """
        session.execute(
            sa.update(schema.event)
            .where(
                schema.event.c.tenant_id == tenant_id,
                schema.event.c.id == event_id,
                schema.event.c.host_organization_id.is_(None),
            )
            .values(host_organization_id=organization_id)
        )

    # -----------------------------------------------------------------------
    # Internals
    # -----------------------------------------------------------------------

    @staticmethod
    def _member_count_subquery() -> sa.ScalarSelect[int]:
        """How many accounts belong to the organization in the outer query.

        A correlated scalar subquery rather than a ``GROUP BY`` join: the
        listing's ``LIMIT`` applies to organizations, and a join that
        multiplied each organization by its members would make the limit count
        the wrong thing.
        """
        member = schema.host_organization_member
        return (
            sa.select(sa.func.count())
            .select_from(member)
            .where(
                member.c.tenant_id == schema.host_organization.c.tenant_id,
                member.c.organization_id == schema.host_organization.c.id,
            )
            .scalar_subquery()
        )

    def _organization_rows(
        self,
        session: Session,
        *,
        tenant_id: uuid.UUID,
        extra: tuple[sa.ColumnElement[bool], ...],
        limit: int,
    ) -> tuple[HostOrganizationRow, ...]:
        """Organizations matching ``extra``, in folded-name order."""
        organization = schema.host_organization
        rows = session.execute(
            sa.select(
                organization.c.id,
                organization.c.unit_id,
                organization.c.name,
                organization.c.department,
                organization.c.default_location,
                organization.c.logistics_contact,
                organization.c.created_at,
                organization.c.updated_at,
                self._member_count_subquery().label("member_count"),
            )
            .where(organization.c.tenant_id == tenant_id, *extra)
            .order_by(sa.func.lower(organization.c.name), organization.c.id)
            .limit(limit)
        ).all()
        return tuple(
            HostOrganizationRow(
                organization_id=row.id,
                unit_id=row.unit_id,
                name=row.name,
                department=row.department,
                default_location=row.default_location,
                logistics_contact=row.logistics_contact,
                member_count=int(row.member_count),
                created_at=row.created_at,
                updated_at=row.updated_at,
            )
            for row in rows
        )

    def _membership_rows(
        self,
        session: Session,
        *,
        tenant_id: uuid.UUID,
        extra: tuple[sa.ColumnElement[bool], ...],
        limit: int,
    ) -> tuple[HostOrganizationMembershipRow, ...]:
        """Memberships matching ``extra``, each with its organization.

        The join is on ``(tenant_id, organization_id)`` and cannot multiply
        rows: ``host_organization``'s primary key is ``id`` and
        ``uq_host_organization_tenant_id`` makes the pair unique, so each
        member row contributes exactly one.
        """
        organization = schema.host_organization
        member = schema.host_organization_member
        rows = session.execute(
            sa.select(
                organization.c.id,
                organization.c.unit_id,
                organization.c.name,
                organization.c.department,
                organization.c.default_location,
                organization.c.logistics_contact,
                organization.c.created_at,
                organization.c.updated_at,
                member.c.user_id,
                member.c.granted_by_user_id,
                member.c.created_at.label("member_since"),
                self._member_count_subquery().label("member_count"),
            )
            .select_from(
                member.join(
                    organization,
                    sa.and_(
                        organization.c.tenant_id == member.c.tenant_id,
                        organization.c.id == member.c.organization_id,
                    ),
                )
            )
            .where(member.c.tenant_id == tenant_id, *extra)
            .order_by(member.c.created_at, organization.c.id)
            .limit(limit)
        ).all()
        return tuple(
            HostOrganizationMembershipRow(
                organization=HostOrganizationRow(
                    organization_id=row.id,
                    unit_id=row.unit_id,
                    name=row.name,
                    department=row.department,
                    default_location=row.default_location,
                    logistics_contact=row.logistics_contact,
                    member_count=int(row.member_count),
                    created_at=row.created_at,
                    updated_at=row.updated_at,
                ),
                user_id=row.user_id,
                granted_by_user_id=row.granted_by_user_id,
                member_since=row.member_since,
            )
            for row in rows
        )
