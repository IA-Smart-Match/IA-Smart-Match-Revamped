"""Authorization policy evaluation.

Architecture v1.1 §2.1 combination semantics, implemented exactly as specified:

    Access is allowed if **either** an inherited unit-path grant covers the
    resource's owning unit **or** an explicit resource grant exists — but an
    explicit **deny** on the resource wins over inheritance, and property-level
    filters apply after either path. Administrative suspension fails local
    authorization immediately, independent of IdP token revocation.

Five rules follow from that, in evaluation order:

1. **Suspension is checked first.** A suspended account is denied locally and
   immediately. Waiting for the identity provider to revoke a token is defense
   in depth, not the control (v1.1 Appendix A, diagram 23).
2. **Tenant mismatch is denied before anything else is considered.** Tenant
   isolation is structural, and a cross-tenant request is never a policy
   question.
3. **An explicit deny beats inheritance.** A resource-level deny is how an
   administrator carves an exception out of a broad unit grant.
4. **Otherwise, either path suffices** — inherited unit-path prefix match, or an
   explicit allow grant on the resource.
5. **``require_membership`` withdraws the explicit-grant path as a substitute
   for membership.** Some operations are correctly expressed with no finite
   ``required_roles`` set at all — the ratified metrics-authorization decision's
   aggregate read is the first: any active unit membership with a role
   suffices, but a bare ``resource_grant`` is denied. ``membership.role`` is
   free text, so there is no finite role set to enumerate, and an *empty*
   ``required_roles`` already means "any role suffices" on the
   inherited-membership path (Path 1) — that part needs no new keyword. What
   an empty ``required_roles`` cannot express on its own is "and a resource
   grant with no covering membership at all must still be refused"; by
   default Path 2 would allow it, which is the loosening this rule exists to
   prevent. Passing ``require_membership=True`` says exactly that: Path 2 (the
   explicit-grant path) denies with the distinct reason code
   ``resource_grant_lacks_membership`` instead of allowing, even when
   ``required_roles`` is empty. Suspension, tenant mismatch, and explicit deny
   keep their precedence ahead of both grant paths regardless of this flag.

Deny-by-default throughout: :func:`evaluate` returns a denial for any case not
positively allowed, including unknown roles and malformed paths.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Self

__all__ = [
    "AccessDecision",
    "AuthorizationError",
    "Effect",
    "Membership",
    "OrgPath",
    "Principal",
    "Resource",
    "ResourceGrant",
    "assert_allowed",
    "evaluate",
]


class Effect(StrEnum):
    """The effect of an explicit resource grant."""

    ALLOW = "allow"
    DENY = "deny"


@dataclass(frozen=True, slots=True)
class OrgPath:
    """A path in the durable organizational tree.

    Mirrors the PostgreSQL ``ltree`` column in ``org_unit.path`` (v1.1 §2.2).
    Represented here as a tuple of labels so prefix containment is exact tuple
    comparison rather than string matching — ``"cpp.eng"`` must not be treated
    as a prefix of ``"cpp.english"``, which is precisely the bug a naive
    ``startswith`` introduces.

    Only durable organizational units live in the tree. Terms, courses,
    sections, and events are resources *owned by* a unit, not tree nodes
    (v1.1 §2.1) — which is what keeps the tree stable across terms.
    """

    labels: tuple[str, ...]

    @classmethod
    def parse(cls, raw: str) -> Self:
        """Parse a dotted ltree-style path.

        Args:
            raw: e.g. ``"iawest.cpp.engineering.ie"``.

        Returns:
            The parsed path.

        Raises:
            ValueError: on an empty path or an empty label, either of which
                would otherwise produce a path that matches unintended subtrees.
        """
        if not raw or not raw.strip():
            raise ValueError("org path must not be empty")
        labels = tuple(part.strip() for part in raw.split("."))
        if any(not label for label in labels):
            raise ValueError(f"org path {raw!r} contains an empty label")
        return cls(labels=labels)

    def contains(self, other: OrgPath) -> bool:
        """Whether this path covers ``other``'s subtree, inclusive.

        Label-wise prefix comparison, so ``cpp.eng`` covers ``cpp.eng.ie`` but
        not ``cpp.english``.
        """
        if len(self.labels) > len(other.labels):
            return False
        return other.labels[: len(self.labels)] == self.labels

    def __str__(self) -> str:
        return ".".join(self.labels)


@dataclass(frozen=True, slots=True)
class Membership:
    """A role granted at a point in the org tree, valid over a time window.

    Attributes:
        granted_path: The subtree this membership covers.
        role: The role held. Roles are not interpreted here beyond their
            presence in ``required_roles``; the role-to-permission mapping is a
            separate concern and an open policy-matrix workstream.
        valid_from: Inclusive start. ``None`` means no lower bound.
        valid_until: Exclusive end. ``None`` means no upper bound. An expired
            membership grants nothing — checked, not assumed.
    """

    granted_path: OrgPath
    role: str
    valid_from: datetime | None = None
    valid_until: datetime | None = None

    def is_active_at(self, moment: datetime) -> bool:
        """Whether this membership is in force at ``moment``."""
        if self.valid_from is not None and moment < self.valid_from:
            return False
        return not (self.valid_until is not None and moment >= self.valid_until)


@dataclass(frozen=True, slots=True)
class ResourceGrant:
    """An explicit allow or deny on one specific resource."""

    resource_type: str
    resource_id: str
    effect: Effect


@dataclass(frozen=True, slots=True)
class Principal:
    """The authenticated actor.

    ``tenant_id`` is derived server-side from the verified token, never taken
    from the request body — the legacy's caller-selected identity is exactly
    what this type exists to prevent.
    """

    user_id: str
    tenant_id: str
    memberships: tuple[Membership, ...] = ()
    resource_grants: tuple[ResourceGrant, ...] = ()
    suspended: bool = False


@dataclass(frozen=True, slots=True)
class Resource:
    """The thing being accessed.

    Attributes:
        resource_type: e.g. ``"event"``, ``"match_run"``, ``"professional"``.
        resource_id: Stable identifier.
        tenant_id: Owning tenant.
        owning_unit_path: The org unit that owns this resource. Inherited grants
            are tested against this path.
    """

    resource_type: str
    resource_id: str
    tenant_id: str
    owning_unit_path: OrgPath


@dataclass(frozen=True, slots=True)
class AccessDecision:
    """The result of a policy evaluation.

    Attributes:
        allowed: Whether access is permitted.
        reason: A stable, machine-readable code. Safe to log and to include in
            an audit record; deliberately does not leak whether a resource
            exists.
        matched_path: The membership path that granted access, when the
            inherited path was the reason.
    """

    allowed: bool
    reason: str
    matched_path: OrgPath | None = None


class AuthorizationError(PermissionError):
    """Raised by :func:`assert_allowed` when access is denied."""

    def __init__(self, decision: AccessDecision) -> None:
        super().__init__(decision.reason)
        self.decision = decision


def evaluate(
    principal: Principal,
    resource: Resource,
    *,
    at: datetime,
    required_roles: frozenset[str] = frozenset(),
    require_membership: bool = False,
) -> AccessDecision:
    """Evaluate whether ``principal`` may access ``resource``.

    Args:
        principal: The authenticated actor, with tenant derived server-side.
        resource: The target resource.
        at: The instant to evaluate membership validity against. Passed in
            rather than read from the clock so expiry is testable.
        required_roles: Roles that satisfy this operation. An empty set means
            any active membership covering the path suffices.
        require_membership: When ``True``, an explicit ``resource_grant`` alone
            does not satisfy this operation — an active membership must cover
            the resource's owning unit path. See module docstring rule 5. Has
            no effect on Path 1 (inherited membership), which already applies
            an empty ``required_roles`` as "any role"; it only withdraws Path 2
            (the explicit-grant path) as a substitute for holding no
            membership at all.

    Returns:
        An :class:`AccessDecision`. Deny-by-default: every path that does not
        positively allow returns a denial with a specific reason code.
    """
    if principal.suspended:
        return AccessDecision(allowed=False, reason="principal_suspended")

    if principal.tenant_id != resource.tenant_id:
        return AccessDecision(allowed=False, reason="tenant_mismatch")

    # An explicit deny on the resource beats any inherited grant.
    for grant in principal.resource_grants:
        if (
            grant.resource_type == resource.resource_type
            and grant.resource_id == resource.resource_id
            and grant.effect is Effect.DENY
        ):
            return AccessDecision(allowed=False, reason="explicit_resource_deny")

    # Path 1: inherited grant via an active membership covering the owning unit.
    for membership in principal.memberships:
        if not membership.is_active_at(at):
            continue
        if required_roles and membership.role not in required_roles:
            continue
        if membership.granted_path.contains(resource.owning_unit_path):
            return AccessDecision(
                allowed=True,
                reason="inherited_unit_grant",
                matched_path=membership.granted_path,
            )

    # Path 2: explicit allow on this specific resource.
    #
    # A resource grant conveys *access to a resource*, not *authority to perform
    # any operation on it*. When an operation names required_roles and the
    # principal reached here — meaning no membership carried a required role —
    # the grant alone must not satisfy it, or a guest reviewer holding a single
    # event grant could submit imports.
    #
    # ResourceGrant carries no role, so the fail-closed reading is that a bare
    # grant cannot satisfy a role-gated operation. Which roles a grant *should*
    # convey is open policy-matrix work (v1.1 §2.1); until that is decided,
    # denying is the safe answer and the distinct reason code keeps the gap
    # visible in the audit trail rather than silent.
    #
    # require_membership is the second, independent way this path can be
    # withdrawn: an operation that names no required_roles at all (so the
    # branch above never fires) may still want membership itself, not just
    # reach, to be the thing that satisfies it. That case gets its own reason
    # code rather than reusing resource_grant_lacks_required_role, because the
    # two populations are different — one held a grant but the wrong role,
    # the other held a grant and no role requirement existed to lack.
    for grant in principal.resource_grants:
        if (
            grant.resource_type == resource.resource_type
            and grant.resource_id == resource.resource_id
            and grant.effect is Effect.ALLOW
        ):
            if required_roles:
                return AccessDecision(allowed=False, reason="resource_grant_lacks_required_role")
            if require_membership:
                return AccessDecision(allowed=False, reason="resource_grant_lacks_membership")
            return AccessDecision(allowed=True, reason="explicit_resource_allow")

    return AccessDecision(allowed=False, reason="no_grant")


def assert_allowed(
    principal: Principal,
    resource: Resource,
    *,
    at: datetime,
    required_roles: frozenset[str] = frozenset(),
    require_membership: bool = False,
) -> AccessDecision:
    """Evaluate policy and raise on denial.

    Args:
        principal: The authenticated actor, with tenant derived server-side.
        resource: The target resource.
        at: The instant to evaluate membership validity against.
        required_roles: Roles that satisfy this operation. See :func:`evaluate`.
        require_membership: See :func:`evaluate` rule 5 (module docstring).

    Returns:
        The allowing decision, so callers can record which path granted access.

    Raises:
        AuthorizationError: when access is denied.
    """
    decision = evaluate(
        principal,
        resource,
        at=at,
        required_roles=required_roles,
        require_membership=require_membership,
    )
    if not decision.allowed:
        raise AuthorizationError(decision)
    return decision
