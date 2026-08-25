"""Loads an authorization principal from a verified identity.

This is the seam where a token becomes a set of permissions, and the reason it
is a database lookup rather than a token claim: **the token proves who you are,
the database decides what you may do.**

A token that carried its own tenant or roles would be caller-selected identity
in a better disguise — the exact pattern archived as MM-A01. Here the token
yields only a subject, and everything else is read from rows an administrator
controls.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

import sqlalchemy as sa
from smartmatch_authz import Effect, Membership, OrgPath, Principal, ResourceGrant
from sqlalchemy.orm import Session

from smartmatch_persistence import schema

__all__ = ["PrincipalRepository", "ResolvedPrincipal"]


@dataclass(frozen=True, slots=True)
class ResolvedPrincipal:
    """A principal plus the local account identifiers behind it.

    The :class:`~smartmatch_authz.Principal` is what policy evaluates. The
    surrounding fields are what the rest of the request needs — the actor id for
    audit records, the email for display.
    """

    principal: Principal
    user_id: uuid.UUID
    tenant_id: uuid.UUID
    email: str


class PrincipalRepository:
    """Resolves verified identities into authorization principals."""

    def load_by_subject(
        self, session: Session, *, external_subject: str
    ) -> ResolvedPrincipal | None:
        """Load the principal for an identity-provider subject.

        The query filters on ``external_subject`` and nothing else, deliberately:
        the tenant is what this lookup *resolves*, so it cannot also be an input.
        Returning at most one row is sound because the column is globally unique —
        ``uq_user_account_external_subject``, added by migration ``0003`` — and
        that constraint is the whole licence for the ``.one_or_none()`` below.

        Before it existed the only uniqueness was ``(tenant_id, external_subject)``,
        which promises one account per subject *per tenant* and says nothing about
        two. One subject with accounts in two tenants matched two rows, this call
        raised ``MultipleResultsFound``, and every authenticated request by that
        person returned a 500. The query was not changed to fix that; the schema
        was, and the same call became correct rather than merely defended.

        Returns:
            The resolved principal, or ``None`` when no local account matches.
            ``None`` is not an error: a person may authenticate with the identity
            provider and simply have no account here. The caller turns that into
            a denial, not a 500.

        Note:
            A suspended account is still returned, carrying ``suspended=True``.
            Policy denies it immediately (v1.1 Appendix A, diagram 23). Returning
            ``None`` instead would conflate "suspended" with "unknown" and lose
            the distinction the audit log needs.
        """
        account = session.execute(
            sa.select(
                schema.user_account.c.id,
                schema.user_account.c.tenant_id,
                schema.user_account.c.email,
                schema.user_account.c.suspended,
            ).where(schema.user_account.c.external_subject == external_subject)
        ).one_or_none()

        if account is None:
            return None

        memberships = self._load_memberships(
            session, tenant_id=account.tenant_id, user_id=account.id
        )
        grants = self._load_grants(session, tenant_id=account.tenant_id, user_id=account.id)

        return ResolvedPrincipal(
            principal=Principal(
                user_id=str(account.id),
                tenant_id=str(account.tenant_id),
                memberships=memberships,
                resource_grants=grants,
                suspended=account.suspended,
            ),
            user_id=account.id,
            tenant_id=account.tenant_id,
            email=account.email,
        )

    def _load_memberships(
        self, session: Session, *, tenant_id: uuid.UUID, user_id: uuid.UUID
    ) -> tuple[Membership, ...]:
        """Load every membership, including expired ones.

        Expiry is evaluated by the policy against an explicit instant, not
        filtered here. Filtering in SQL would mean the policy could not be tested
        for expiry without a database, and would put a second, silent copy of the
        validity rule in the query.
        """
        rows = session.execute(
            sa.select(
                sa.cast(schema.membership.c.granted_path, sa.Text).label("granted_path"),
                schema.membership.c.role,
                schema.membership.c.valid_from,
                schema.membership.c.valid_until,
            ).where(
                schema.membership.c.tenant_id == tenant_id,
                schema.membership.c.user_id == user_id,
            )
        ).all()

        return tuple(
            Membership(
                granted_path=OrgPath.parse(row.granted_path),
                role=row.role,
                valid_from=row.valid_from,
                valid_until=row.valid_until,
            )
            for row in rows
        )

    def _load_grants(
        self, session: Session, *, tenant_id: uuid.UUID, user_id: uuid.UUID
    ) -> tuple[ResourceGrant, ...]:
        """Load explicit per-resource allow and deny grants."""
        rows = session.execute(
            sa.select(
                schema.resource_grant.c.resource_type,
                schema.resource_grant.c.resource_id,
                schema.resource_grant.c.effect,
            ).where(
                schema.resource_grant.c.tenant_id == tenant_id,
                schema.resource_grant.c.user_id == user_id,
            )
        ).all()

        return tuple(
            ResourceGrant(
                resource_type=row.resource_type,
                resource_id=str(row.resource_id),
                effect=Effect(row.effect),
            )
            for row in rows
        )
