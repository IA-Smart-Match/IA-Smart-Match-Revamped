"""Authorization negative tests.

Architecture v1.1 §2.1 requires the combination semantics be covered by negative
tests, and the verification matrix names the specific cases: anonymous, wrong
role, wrong tenant, wrong resource, expired membership, and suspended account.

Every test here asserts a *denial*. Positive cases live in
``test_policy_grants.py``; keeping them apart makes it obvious at a glance that
the deny paths are covered, which is the property that actually matters.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from smartmatch_authz import (
    AuthorizationError,
    Effect,
    Membership,
    OrgPath,
    Principal,
    Resource,
    ResourceGrant,
    assert_allowed,
    evaluate,
)

NOW = datetime(2026, 8, 17, 12, 0, tzinfo=UTC)

TENANT = "tenant-iawest"
OTHER_TENANT = "tenant-someone-else"


def _resource(
    *,
    tenant_id: str = TENANT,
    path: str = "iawest.cpp.engineering.ie",
    resource_id: str = "event-1",
) -> Resource:
    return Resource(
        resource_type="event",
        resource_id=resource_id,
        tenant_id=tenant_id,
        owning_unit_path=OrgPath.parse(path),
    )


def _member(path: str, role: str = "coordinator", **kw: object) -> Membership:
    return Membership(granted_path=OrgPath.parse(path), role=role, **kw)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# The six named negative cases
# ---------------------------------------------------------------------------


def test_anonymous_principal_is_denied():
    """No memberships and no grants means no access. Deny-by-default."""
    principal = Principal(user_id="anon", tenant_id=TENANT)
    decision = evaluate(principal, _resource(), at=NOW)

    assert not decision.allowed
    assert decision.reason == "no_grant"


def test_wrong_role_is_denied():
    """A membership covering the path does not help if the role is insufficient."""
    principal = Principal(
        user_id="u1",
        tenant_id=TENANT,
        memberships=(_member("iawest.cpp", role="student"),),
    )
    decision = evaluate(
        principal, _resource(), at=NOW, required_roles=frozenset({"coordinator", "admin"})
    )

    assert not decision.allowed
    assert decision.reason == "no_grant"


def test_wrong_tenant_is_denied_even_with_a_covering_membership():
    """Tenant isolation is structural and is checked before any grant."""
    principal = Principal(
        user_id="u1",
        tenant_id=TENANT,
        memberships=(_member("iawest.cpp"),),
    )
    decision = evaluate(principal, _resource(tenant_id=OTHER_TENANT), at=NOW)

    assert not decision.allowed
    assert decision.reason == "tenant_mismatch"


def test_wrong_tenant_is_denied_even_with_an_explicit_resource_grant():
    """A cross-tenant resource grant is never honoured."""
    principal = Principal(
        user_id="u1",
        tenant_id=TENANT,
        resource_grants=(ResourceGrant("event", "event-1", Effect.ALLOW),),
    )
    decision = evaluate(principal, _resource(tenant_id=OTHER_TENANT), at=NOW)

    assert not decision.allowed
    assert decision.reason == "tenant_mismatch"


def test_wrong_resource_grant_does_not_transfer():
    """A grant on one resource says nothing about another."""
    principal = Principal(
        user_id="u1",
        tenant_id=TENANT,
        resource_grants=(ResourceGrant("event", "event-99", Effect.ALLOW),),
    )
    decision = evaluate(principal, _resource(resource_id="event-1"), at=NOW)

    assert not decision.allowed
    assert decision.reason == "no_grant"


def test_grant_on_a_different_resource_type_does_not_transfer():
    """Type is part of resource identity; ids are not globally unique."""
    principal = Principal(
        user_id="u1",
        tenant_id=TENANT,
        resource_grants=(ResourceGrant("match_run", "event-1", Effect.ALLOW),),
    )
    decision = evaluate(principal, _resource(resource_id="event-1"), at=NOW)

    assert not decision.allowed


def test_expired_membership_is_denied():
    """An expired membership grants nothing — checked, not assumed."""
    principal = Principal(
        user_id="u1",
        tenant_id=TENANT,
        memberships=(_member("iawest.cpp", valid_until=NOW - timedelta(days=1)),),
    )
    decision = evaluate(principal, _resource(), at=NOW)

    assert not decision.allowed
    assert decision.reason == "no_grant"


def test_not_yet_valid_membership_is_denied():
    """A future-dated membership is not yet in force."""
    principal = Principal(
        user_id="u1",
        tenant_id=TENANT,
        memberships=(_member("iawest.cpp", valid_from=NOW + timedelta(days=1)),),
    )
    assert not evaluate(principal, _resource(), at=NOW).allowed


def test_membership_validity_window_is_half_open():
    """``valid_until`` is exclusive, so it does not grant access at the boundary."""
    expires = NOW
    principal = Principal(
        user_id="u1",
        tenant_id=TENANT,
        memberships=(_member("iawest.cpp", valid_until=expires),),
    )
    assert not evaluate(principal, _resource(), at=expires).allowed
    assert evaluate(principal, _resource(), at=expires - timedelta(seconds=1)).allowed


def test_suspended_account_is_denied_immediately():
    """Suspension fails local authorization independent of IdP token revocation.

    The principal here holds a membership that would otherwise grant access, so
    the test proves suspension short-circuits rather than merely coinciding with
    a denial.
    """
    principal = Principal(
        user_id="u1",
        tenant_id=TENANT,
        memberships=(_member("iawest"),),
        resource_grants=(ResourceGrant("event", "event-1", Effect.ALLOW),),
        suspended=True,
    )
    decision = evaluate(principal, _resource(), at=NOW)

    assert not decision.allowed
    assert decision.reason == "principal_suspended"


# ---------------------------------------------------------------------------
# Combination semantics: explicit deny beats inheritance
# ---------------------------------------------------------------------------


def test_explicit_resource_deny_overrides_inherited_unit_grant():
    """v1.1 §2.1: an explicit deny on the resource wins over inheritance."""
    principal = Principal(
        user_id="u1",
        tenant_id=TENANT,
        memberships=(_member("iawest"),),  # covers the whole org
        resource_grants=(ResourceGrant("event", "event-1", Effect.DENY),),
    )
    decision = evaluate(principal, _resource(resource_id="event-1"), at=NOW)

    assert not decision.allowed
    assert decision.reason == "explicit_resource_deny"


def test_explicit_deny_beats_an_explicit_allow_on_the_same_resource():
    """Deny is evaluated first, so a conflicting pair fails closed."""
    principal = Principal(
        user_id="u1",
        tenant_id=TENANT,
        resource_grants=(
            ResourceGrant("event", "event-1", Effect.ALLOW),
            ResourceGrant("event", "event-1", Effect.DENY),
        ),
    )
    decision = evaluate(principal, _resource(), at=NOW)

    assert not decision.allowed
    assert decision.reason == "explicit_resource_deny"


# ---------------------------------------------------------------------------
# Path containment: the label-boundary bug a naive prefix match introduces
# ---------------------------------------------------------------------------


def test_sibling_subtree_is_not_covered():
    """A grant on one department does not reach its sibling."""
    principal = Principal(
        user_id="u1",
        tenant_id=TENANT,
        memberships=(_member("iawest.cpp.engineering.ie"),),
    )
    decision = evaluate(principal, _resource(path="iawest.cpp.engineering.cs"), at=NOW)

    assert not decision.allowed


def test_parent_resource_is_not_covered_by_a_child_grant():
    """Grants flow down the tree, never up."""
    principal = Principal(
        user_id="u1",
        tenant_id=TENANT,
        memberships=(_member("iawest.cpp.engineering.ie"),),
    )
    assert not evaluate(principal, _resource(path="iawest.cpp"), at=NOW).allowed


def test_label_prefix_does_not_imply_subtree_containment():
    """``eng`` must not be treated as a prefix of ``english``.

    A string ``startswith`` implementation grants access here. Label-wise
    comparison does not, which is why :class:`OrgPath` stores a tuple.
    """
    principal = Principal(
        user_id="u1",
        tenant_id=TENANT,
        memberships=(_member("iawest.cpp.eng"),),
    )
    decision = evaluate(principal, _resource(path="iawest.cpp.english"), at=NOW)

    assert not decision.allowed


# ---------------------------------------------------------------------------
# Malformed input
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("raw", ["", "   ", "iawest..cpp", ".cpp", "cpp."])
def test_malformed_org_paths_are_rejected(raw: str):
    """An empty label would silently widen the subtree a grant covers."""
    with pytest.raises(ValueError):
        OrgPath.parse(raw)


def test_assert_allowed_raises_on_denial():
    principal = Principal(user_id="anon", tenant_id=TENANT)
    with pytest.raises(AuthorizationError) as excinfo:
        assert_allowed(principal, _resource(), at=NOW)

    assert excinfo.value.decision.reason == "no_grant"


# ---------------------------------------------------------------------------
# Role gating applies to BOTH grant paths
# ---------------------------------------------------------------------------


def test_explicit_resource_grant_does_not_satisfy_a_role_gated_operation():
    """An access grant is not authority to perform any operation on the resource.

    A resource grant says "you may reach this event". An operation's
    ``required_roles`` says "this action needs a coordinator". Treating the
    first as satisfying the second lets a guest reviewer submit imports, because
    the explicit-allow path returned before any role was consulted.

    ``ResourceGrant`` carries no role, so the fail-closed reading is that a bare
    grant cannot satisfy a role-gated operation.

    **A4 settled this rather than leaving it open (S-007): the behaviour stays.**
    The type has a resource type, a resource id, and an effect, and nothing that
    could name a role — so there is no mapping to derive, only one to invent, and
    inventing one is the only change on this surface that turns a denial into a
    permit. Conveying a role means the *grant* carrying one, which is a
    ``resource_grant`` schema change and a product decision about what a guest
    reviewer may do. ``tests/authz/test_policy_matrix.py`` pins the rule on every
    operation and fails the day ``ResourceGrant`` grows a field that could answer
    the question.
    """
    principal = Principal(
        user_id="guest",
        tenant_id=TENANT,
        resource_grants=(ResourceGrant("event", "event-1", Effect.ALLOW),),
    )
    decision = evaluate(
        principal,
        _resource(),
        at=NOW,
        required_roles=frozenset({"admin", "coordinator"}),
    )

    assert not decision.allowed
    assert decision.reason == "resource_grant_lacks_required_role"


def test_explicit_resource_grant_still_works_for_ungated_operations():
    """The guest-reviewer case must keep working where no role is demanded."""
    principal = Principal(
        user_id="guest",
        tenant_id=TENANT,
        resource_grants=(ResourceGrant("event", "event-1", Effect.ALLOW),),
    )
    decision = evaluate(principal, _resource(), at=NOW)

    assert decision.allowed
    assert decision.reason == "explicit_resource_allow"


def test_resource_grant_plus_qualifying_membership_is_allowed():
    """A grant does not block someone who independently holds the role."""
    principal = Principal(
        user_id="u1",
        tenant_id=TENANT,
        memberships=(_member("iawest", role="coordinator"),),
        resource_grants=(ResourceGrant("event", "event-1", Effect.ALLOW),),
    )
    decision = evaluate(principal, _resource(), at=NOW, required_roles=frozenset({"coordinator"}))

    assert decision.allowed
    assert decision.reason == "inherited_unit_grant"
