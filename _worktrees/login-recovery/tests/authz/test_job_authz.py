"""The one authorizer the four job operations share, exercised directly.

``services/api/smartmatch_api/job_authz.py`` replaces two hand-rolled
authorizers — ``routers/jobs.py::_authorize_job_read`` and
``routers/redrive.py::_authorize_redrive`` — that applied *different* subsets of
the same policy to the same resource. Reading a job obeyed no ``resource_grant``
at all, so an explicit deny carved out by an administrator stopped a re-drive and
did not stop the read of the very same job; re-drive restated the four policy
rules in Python rather than calling the policy. Neither could scope to an org
unit, because ``job`` had no owning unit to scope to (backlog **A5**).

The tests here are about the *ordering*, because ordering is the whole content of
an authorization decision that has more than one reason to refuse. Every case
below asserts the stable reason code as well as the outcome: "denied" is not
coverage, and a suspension that reads as a missing role is a wrong record of why
someone was refused.

:mod:`tests.authz.test_policy_matrix` runs the same authorizer over the full
operation × principal-shape rectangle. This file is the narrower one: it pins the
half-dozen orderings that would still be individually satisfiable by a matrix
that happened to agree, and the two fail-closed paths a matrix cell cannot reach
because they are about a malformed *row* rather than about a principal.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import pytest
from smartmatch_api import job_authz
from smartmatch_authz import (
    AuthorizationError,
    Effect,
    Membership,
    OrgPath,
    Principal,
    ResourceGrant,
)
from smartmatch_persistence.principals import ResolvedPrincipal

NOW = datetime(2026, 8, 26, 12, 0, tzinfo=UTC)

TENANT_ID = uuid.UUID("11111111-1111-4111-8111-111111111111")
OTHER_TENANT_ID = uuid.UUID("22222222-2222-4222-8222-222222222222")
ACTOR_ID = uuid.UUID("33333333-3333-4333-8333-333333333333")
BYSTANDER_ID = uuid.UUID("44444444-4444-4444-8444-444444444444")
JOB_ID = uuid.UUID("66666666-6666-4666-8666-666666666666")

OWNING_UNIT = "iawest.cpp.engineering.ie"
SIBLING_UNIT = "iawest.cpp.engineering.cs"
ORG_ROOT = "iawest"

#: The four operations, as the pair of entry points that serve them. Both job
#: reads share one function and both job commands share the other, which is the
#: property that makes "the stream is a way around the status endpoint"
#: unrepresentable rather than merely untrue today.
READS = pytest.mark.parametrize("authorize", [job_authz.authorize_job_read], ids=["read"])
COMMANDS = pytest.mark.parametrize("authorize", [job_authz.authorize_job_command], ids=["command"])
BOTH = pytest.mark.parametrize(
    "authorize",
    [job_authz.authorize_job_read, job_authz.authorize_job_command],
    ids=["read", "command"],
)


@dataclass(frozen=True, slots=True)
class _JobRow:
    """The four fields authorizing a job operation reads off the job.

    Deliberately not a :class:`~smartmatch_persistence.jobs.JobRecord`: this file
    must be able to build a row whose ``owning_unit_path`` is absent or malformed,
    which a record produced by a tenant-scoped read never is.
    """

    id: uuid.UUID = JOB_ID
    tenant_id: uuid.UUID = TENANT_ID
    actor_id: uuid.UUID | None = ACTOR_ID
    owning_unit_path: str | None = OWNING_UNIT


def _principal(
    *,
    user_id: uuid.UUID = BYSTANDER_ID,
    tenant_id: uuid.UUID = TENANT_ID,
    memberships: tuple[Membership, ...] = (),
    grants: tuple[ResourceGrant, ...] = (),
    suspended: bool = False,
) -> ResolvedPrincipal:
    return ResolvedPrincipal(
        principal=Principal(
            user_id=str(user_id),
            tenant_id=str(tenant_id),
            memberships=memberships,
            resource_grants=grants,
            suspended=suspended,
        ),
        user_id=user_id,
        tenant_id=TENANT_ID,
        email="authz@example.test",
    )


def _member(path: str, role: str, **window: datetime) -> Membership:
    return Membership(granted_path=OrgPath.parse(path), role=role, **window)


def _grant(effect: Effect) -> ResourceGrant:
    return ResourceGrant(resource_type="job", resource_id=str(JOB_ID), effect=effect)


def _denial(authorize, principal: ResolvedPrincipal, job: _JobRow) -> str:
    """Run an authorizer that must refuse, and report the reason it gave."""
    with pytest.raises(AuthorizationError) as raised:
        authorize(principal, job, at=NOW)
    return raised.value.decision.reason


# ---------------------------------------------------------------------------
# The permits
# ---------------------------------------------------------------------------


@BOTH
def test_a_coordinator_at_the_owning_unit_is_allowed(authorize):
    """Containment is inclusive, so the owning unit's own coordinator qualifies."""
    decision = authorize(
        _principal(memberships=(_member(OWNING_UNIT, "coordinator"),)),
        _JobRow(),
        at=NOW,
    )
    assert decision.allowed


@BOTH
def test_an_administrator_at_the_org_root_is_allowed(authorize):
    """An inherited grant at the root of the tree covers every unit beneath it."""
    decision = authorize(
        _principal(memberships=(_member(ORG_ROOT, "admin"),)),
        _JobRow(),
        at=NOW,
    )
    assert decision.allowed


# ---------------------------------------------------------------------------
# A5 — the owning unit is now the thing that scopes a job operation
# ---------------------------------------------------------------------------


@BOTH
def test_a_sibling_unit_coordinator_is_denied_every_job_operation(authorize):
    """The A5 hole, closed and asserted as a denial rather than described.

    Before ``job.owning_unit_id`` existed, all four operations checked the role
    and nothing else, so a coordinator in one department could read, re-drive and
    abandon another department's work. The role is unchanged; what changed is
    that there is now a unit to test it against.
    """
    principal = _principal(memberships=(_member(SIBLING_UNIT, "coordinator"),))
    assert _denial(authorize, principal, _JobRow()) == "no_grant"


@BOTH
def test_an_expired_membership_grants_nothing(authorize):
    """Validity is evaluated against the instant passed in, not assumed."""
    principal = _principal(
        memberships=(_member(OWNING_UNIT, "coordinator", valid_until=NOW - timedelta(days=1)),)
    )
    assert _denial(authorize, principal, _JobRow()) == "no_grant"


@BOTH
def test_a_membership_carrying_the_wrong_role_is_denied(authorize):
    """Job operations are role-gated, not membership-gated."""
    principal = _principal(memberships=(_member(OWNING_UNIT, "student"),))
    assert _denial(authorize, principal, _JobRow()) == "no_grant"


# ---------------------------------------------------------------------------
# The actor exception, and its exact boundary
# ---------------------------------------------------------------------------


@READS
def test_the_actor_may_read_their_own_job_without_an_oversight_role(authorize):
    """Whoever submitted the work can follow it.

    This is the one permission a job operation grants outside the org tree, and
    it is deliberately narrow: it is *following your own work*, which is why it
    exists on the two read routes and on neither command route.
    """
    decision = authorize(_principal(user_id=ACTOR_ID), _JobRow(), at=NOW)
    assert decision.allowed


@COMMANDS
def test_the_actor_may_not_redrive_or_abandon_their_own_job(authorize):
    """Submitting a job is not authority to re-run or close it.

    Re-driving repeats effects that may already have reached people outside the
    system, and abandoning removes the item from everyone else's view. Both are
    oversight, not ownership.
    """
    assert _denial(authorize, _principal(user_id=ACTOR_ID), _JobRow()) == "no_grant"


@BOTH
def test_a_job_with_no_recorded_actor_is_not_readable_by_a_role_less_member(authorize):
    """The actor path must not degrade into "nobody owns it, so anybody may".

    ``job.actor_id`` is nullable — system-initiated work records none — and a
    guard written as ``job.actor_id == principal.user_id`` without the null check
    would make every such job readable by any member of the tenant.
    """
    principal = _principal(user_id=BYSTANDER_ID)
    assert _denial(authorize, principal, _JobRow(actor_id=None)) == "no_grant"


# ---------------------------------------------------------------------------
# Ordering: what outranks the actor exception
# ---------------------------------------------------------------------------


@BOTH
def test_an_explicit_deny_blocks_the_jobs_own_actor(authorize):
    """Rule 3 of the policy, applied on the read path for the first time.

    An administrator carving one job out of a broad grant was obeyed by
    ``/redrive`` and ``/abandon`` and ignored by ``GET /v1/jobs/{job_id}``, which
    is the half of that omission that actually granted access. The deny is now
    evaluated before the actor exception, so it stops the actor's own read too —
    which is the case that would otherwise reopen the hole through the back door.
    """
    principal = _principal(user_id=ACTOR_ID, grants=(_grant(Effect.DENY),))
    assert _denial(authorize, principal, _JobRow()) == "explicit_resource_deny"


@BOTH
def test_an_explicit_deny_beats_an_administrator_at_the_root(authorize):
    """The deny is what an exception to a broad inherited grant is made of."""
    principal = _principal(
        memberships=(_member(ORG_ROOT, "admin"),),
        grants=(_grant(Effect.DENY),),
    )
    assert _denial(authorize, principal, _JobRow()) == "explicit_resource_deny"


@BOTH
def test_suspension_is_checked_before_everything_including_the_actor(authorize):
    """The one control that must not be reachable around.

    The principal here is the job's own actor *and* an administrator at the root
    *and* holds an explicit allow — so the denial proves a short-circuit rather
    than coinciding with an absence of permission.
    """
    principal = _principal(
        user_id=ACTOR_ID,
        memberships=(_member(ORG_ROOT, "admin"),),
        grants=(_grant(Effect.ALLOW),),
        suspended=True,
    )
    assert _denial(authorize, principal, _JobRow()) == "principal_suspended"


@BOTH
def test_a_tenant_mismatch_is_denied_before_the_actor_exception(authorize):
    """Tenant isolation is structural and precedes every grant question.

    Unreachable through the routes — the job load is tenant-scoped in its query —
    which is exactly why it is asserted rather than assumed. The principal is the
    job's actor, so an actor exception evaluated before this check would let a
    cross-tenant read through.
    """
    principal = _principal(user_id=ACTOR_ID, tenant_id=OTHER_TENANT_ID)
    assert _denial(authorize, principal, _JobRow()) == "tenant_mismatch"


# ---------------------------------------------------------------------------
# S-007 — a bare resource grant conveys reach, not authority
# ---------------------------------------------------------------------------


@BOTH
def test_a_bare_resource_allow_does_not_confer_an_oversight_role(authorize):
    """A grant says "you may address this resource"; the role says "you may act".

    Denied on every job operation, and denied with the *distinct* reason, which
    is what keeps the population affected by S-007 measurable in the audit trail.
    Job reads previously answered ``no_grant`` here because they consulted no
    grant at all.
    """
    principal = _principal(grants=(_grant(Effect.ALLOW),))
    reason = _denial(authorize, principal, _JobRow())
    assert reason == "resource_grant_lacks_required_role"


# ---------------------------------------------------------------------------
# Fail-closed on a row the routes cannot produce
# ---------------------------------------------------------------------------


@BOTH
def test_a_job_with_no_owning_unit_path_is_denied(authorize):
    """A record that did not come from a tenant-scoped read authorizes nothing.

    ``job.owning_unit_id`` is ``NOT NULL`` and ``JobRepository.get`` joins the
    unit in, so the four routes cannot reach this. It is asserted because the
    alternative to a denial is an exception — a 500 on an authorization path — and
    because the fail-*open* version of this branch would be a one-line mistake
    that no route-level test could see.
    """
    principal = _principal(user_id=ACTOR_ID, memberships=(_member(ORG_ROOT, "admin"),))
    assert _denial(authorize, principal, _JobRow(owning_unit_path=None)) == "no_grant"


@BOTH
def test_a_malformed_owning_unit_path_is_denied(authorize):
    """A path the tree cannot parse must refuse, not raise."""
    principal = _principal(memberships=(_member(ORG_ROOT, "admin"),))
    assert _denial(authorize, principal, _JobRow(owning_unit_path="iawest..ie")) == "no_grant"


# ---------------------------------------------------------------------------
# The role set is one set, in one place
# ---------------------------------------------------------------------------


def test_both_entry_points_gate_on_the_same_oversight_roles():
    """The four operations share a role set because they share a module.

    Before this module there were two constants — ``_JOB_OVERSIGHT_ROLES`` and
    ``_REDRIVE_ROLES`` — holding equal values in two files, which is the
    arrangement in which they quietly stop being equal.
    """
    assert frozenset({"admin", "coordinator"}) == job_authz.JOB_OVERSIGHT_ROLES


def test_the_resource_type_matches_what_a_grant_would_carry():
    """An explicit grant on a job names this string in ``resource_grant``."""
    assert job_authz.JOB_RESOURCE_TYPE == "job"


# ---------------------------------------------------------------------------
# The one guard the ordering design was missing
# ---------------------------------------------------------------------------


def _denial_reasons_evaluate_can_emit() -> frozenset[str]:
    """Every ``reason`` the policy returns on a denial, read out of its source.

    Read by AST rather than listed here, because a list here would be the second
    copy of the vocabulary and would agree with the first until the day it
    mattered. Walking the module finds the reasons whatever order they appear in
    and whichever branch returns them.
    """
    import ast
    import inspect as _inspect

    from smartmatch_authz import policy as policy_module

    tree = ast.parse(_inspect.getsource(policy_module))
    reasons: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if getattr(node.func, "id", None) != "AccessDecision":
            continue
        keywords = {kw.arg: kw.value for kw in node.keywords}
        allowed = keywords.get("allowed")
        reason = keywords.get("reason")
        if not isinstance(allowed, ast.Constant) or allowed.value is not False:
            continue
        if isinstance(reason, ast.Constant) and isinstance(reason.value, str):
            reasons.add(reason.value)
    assert reasons, "no denial reasons could be read out of the policy module"
    return frozenset(reasons)


def test_the_denial_vocabulary_is_exactly_the_five_documented_reasons():
    """The six stable reason codes, pinned as a *set* rather than one at a time.

    Each is already asserted individually by a test above (or, for the newest
    one, by the metrics authorization matrix), which catches one being
    renamed. None of them catches one being *added* — and an added reason is
    the case that matters, because
    :func:`test_a_new_denial_reason_must_choose_a_side` is what decides
    whether the new one is overridable by the actor exception.

    ``resource_grant_lacks_membership`` is the newest: the ratified metrics
    authorization decision's ``require_membership`` keyword
    (``smartmatch_authz.policy`` module docstring rule 5) added it to what
    ``evaluate`` can emit. No job route passes ``require_membership`` — job
    operations are role-gated, so that branch is unreachable from here — but
    this test scans the policy's full source, not any one call site, so the
    vocabulary grows the moment the policy can emit it, whether or not this
    module happens to trigger it today.

    These strings are a contract beyond this repository: they are emitted as
    ``details.reason`` on a 403 and are safe to log and to audit against.
    """
    assert _denial_reasons_evaluate_can_emit() == frozenset(
        {
            "principal_suspended",
            "tenant_mismatch",
            "explicit_resource_deny",
            "resource_grant_lacks_required_role",
            "resource_grant_lacks_membership",
            "no_grant",
        }
    )


def test_a_new_denial_reason_must_choose_a_side():
    """``_STRUCTURAL_DENIALS`` is an allowlist, and an allowlist fails open.

    ``_decide`` raises immediately for a reason *in* that set and lets the actor
    exception override any reason *not* in it. So a denial added to the policy
    later — ``tenant_suspended``, say — would land silently on the
    **overridable** side, and the job's own actor would read straight past it.
    Nothing else in the codebase relates the two sets: the constant is
    referenced only inside ``job_authz`` itself.

    This test is the relation. It fails the moment the policy grows a reason,
    and the fix is not to edit the expected set below — it is to decide,
    deliberately, whether the new reason is structural, and to put it in
    ``_STRUCTURAL_DENIALS`` if it is.

    The halves below are separate assertions because they fail for different
    causes: a reason that is structural but unlisted is a fail-open hole, while
    a listed reason the policy cannot emit is dead configuration.
    """
    vocabulary = _denial_reasons_evaluate_can_emit()

    assert vocabulary >= job_authz._STRUCTURAL_DENIALS, (
        "_STRUCTURAL_DENIALS names reasons the policy cannot emit: "
        f"{sorted(job_authz._STRUCTURAL_DENIALS - vocabulary)}"
    )

    # The reasons that are about the caller or the request rather than about
    # which grants they hold. No relationship to the job can answer these, so
    # the actor exception must never reach them.
    assert (
        frozenset({"principal_suspended", "tenant_mismatch", "explicit_resource_deny"})
        == job_authz._STRUCTURAL_DENIALS
    )

    # Stated the other way round, so a failure names the hole rather than a set
    # difference: everything else is deliberately overridable.
    #
    # resource_grant_lacks_membership joins this side, not _STRUCTURAL_DENIALS:
    # it is a statement about which grants and memberships the principal
    # holds (the same population as resource_grant_lacks_required_role), not
    # about the caller or the request in the way suspension, tenant mismatch,
    # and an explicit deny are. No job route can reach it today — none passes
    # require_membership — but the classification is decided here regardless,
    # exactly as this test's docstring requires for every reason the policy
    # can emit.
    assert vocabulary - job_authz._STRUCTURAL_DENIALS == frozenset(
        {"resource_grant_lacks_required_role", "resource_grant_lacks_membership", "no_grant"}
    ), "a denial reason became overridable by the actor exception without anyone deciding it"
