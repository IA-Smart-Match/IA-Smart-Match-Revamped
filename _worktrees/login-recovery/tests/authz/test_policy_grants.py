"""Authorization positive tests — the two grant paths and their combination."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from smartmatch_authz import (
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


def _resource(path: str = "iawest.cpp.engineering.ie") -> Resource:
    return Resource(
        resource_type="event",
        resource_id="event-1",
        tenant_id=TENANT,
        owning_unit_path=OrgPath.parse(path),
    )


def test_inherited_grant_covers_the_whole_subtree():
    """A membership at a unit path covers every resource owned below it."""
    principal = Principal(
        user_id="u1",
        tenant_id=TENANT,
        memberships=(Membership(OrgPath.parse("iawest.cpp"), "coordinator"),),
    )
    decision = evaluate(principal, _resource(), at=NOW)

    assert decision.allowed
    assert decision.reason == "inherited_unit_grant"
    assert str(decision.matched_path) == "iawest.cpp"


def test_membership_at_the_exact_owning_unit_grants_access():
    """Containment is inclusive: a path covers itself."""
    principal = Principal(
        user_id="u1",
        tenant_id=TENANT,
        memberships=(Membership(OrgPath.parse("iawest.cpp.engineering.ie"), "coordinator"),),
    )
    assert evaluate(principal, _resource(), at=NOW).allowed


def test_explicit_resource_grant_works_without_any_membership():
    """The second path: a resource grant alone suffices.

    This is how a guest reviewer gets access to exactly one event without being
    given a role anywhere in the org tree.

    Note what this covers and what it does not: the operation here names no
    required roles, and **no route does that today** — every operation in
    ``tests/authz/test_policy_matrix.py`` is role-gated, so this permit path is
    reachable from the policy and not yet from the API. That is asserted there
    (``test_every_operation_is_role_gated_today``) so the first ungated operation
    has to confirm deliberately that a bare grant is meant to be enough for it.
    """
    principal = Principal(
        user_id="guest",
        tenant_id=TENANT,
        resource_grants=(ResourceGrant("event", "event-1", Effect.ALLOW),),
    )
    decision = evaluate(principal, _resource(), at=NOW)

    assert decision.allowed
    assert decision.reason == "explicit_resource_allow"


def test_required_roles_are_satisfied_by_a_matching_membership():
    principal = Principal(
        user_id="u1",
        tenant_id=TENANT,
        memberships=(Membership(OrgPath.parse("iawest"), "admin"),),
    )
    decision = evaluate(principal, _resource(), at=NOW, required_roles=frozenset({"admin"}))
    assert decision.allowed


def test_empty_required_roles_accepts_any_active_membership():
    """An operation with no role requirement needs only coverage."""
    principal = Principal(
        user_id="u1",
        tenant_id=TENANT,
        memberships=(Membership(OrgPath.parse("iawest"), "anything"),),
    )
    assert evaluate(principal, _resource(), at=NOW).allowed


def test_membership_within_its_validity_window_is_honoured():
    principal = Principal(
        user_id="u1",
        tenant_id=TENANT,
        memberships=(
            Membership(
                OrgPath.parse("iawest"),
                "coordinator",
                valid_from=NOW - timedelta(days=30),
                valid_until=NOW + timedelta(days=30),
            ),
        ),
    )
    assert evaluate(principal, _resource(), at=NOW).allowed


def test_one_expired_membership_does_not_shadow_an_active_one():
    """Evaluation continues past an inactive membership."""
    principal = Principal(
        user_id="u1",
        tenant_id=TENANT,
        memberships=(
            Membership(
                OrgPath.parse("iawest"),
                "coordinator",
                valid_until=NOW - timedelta(days=1),
            ),
            Membership(OrgPath.parse("iawest.cpp"), "coordinator"),
        ),
    )
    decision = evaluate(principal, _resource(), at=NOW)

    assert decision.allowed
    assert str(decision.matched_path) == "iawest.cpp"


def test_assert_allowed_returns_the_granting_decision():
    """Callers record which path granted access, for the audit trail."""
    principal = Principal(
        user_id="u1",
        tenant_id=TENANT,
        memberships=(Membership(OrgPath.parse("iawest"), "coordinator"),),
    )
    decision = assert_allowed(principal, _resource(), at=NOW)

    assert decision.allowed
    assert decision.reason == "inherited_unit_grant"
