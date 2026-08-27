"""The authorization policy matrix, and the control that keeps it complete.

Architecture v1.1 §2.1 names an authorization matrix with negative tests per
operation as a workstream (backlog **A4**). Before this file one operation was
covered and the matrix was not, so deny-by-default was asserted for a single
case and assumed everywhere else.

## What an "operation" is here

Not an idea about the product — a route that takes an authenticated principal.
Every such route in ``services/api/smartmatch_api`` is an operation the policy
is asked to authorize, and every one of them needs a row. The list is derived
from the source by :func:`_declared_routes` rather than written down, because a
list written down is a list that goes stale the first time someone adds a route.

## Why the matrix is executable rather than a docstring

The standing lesson in this repository is that **documentation is not a
control**. A matrix in a comment that nobody checks is worth nothing: the
failure it exists to catch — a new operation shipped with no authorization, or
with authorization nobody characterised — is exactly the failure a comment
cannot see. So three things are checked mechanically, in the same shape
``tests/unit/test_adr_index.py`` uses to hold the ADR index against the ADR
files:

1. **Both directions of membership.** Every authenticated route has a row, and
   every row names a route that exists. A route that is *not* authenticated must
   be declared in :data:`UNAUTHENTICATED_ROUTES` with a reason, so a handler that
   silently loses its ``CurrentPrincipal`` parameter fails here rather than
   passing quietly.
2. **The row describes the code.** The authorizer the row names is the one the
   route actually calls, and the role set the row states is the constant the
   authorizer actually reads — compared against the live object, so widening
   ``JOB_OVERSIGHT_ROLES`` to admit a student breaks this file.
3. **Every cell is executed.** Each cell is run through the *real* authorizer,
   not through a re-implementation of it. That distinction mattered more before
   A5 than it does now: three of the five operations did not call
   :func:`smartmatch_authz.evaluate` at all, because ``job`` had no owning unit
   and the two job routers restated the policy's rules in Python instead. All
   five reach ``evaluate`` today — the job ones through
   :mod:`smartmatch_api.job_authz` — and the cells are still run through the
   call sites rather than through the policy, because what a route *does* is the
   thing that can drift.

## Known holes, recorded rather than left blank

A blank cell is indistinguishable from an untested one, so a hole is a cell with
a ``gap`` marker naming the item that closes it (:data:`GAPS`). There are none
at present. There were three — A5, and two consequences of the job-read path
consulting no ``resource_grant`` — and :data:`GAPS` records what closing each of
them changed rather than being deleted along with them, because the practice is
the part worth keeping.

## S-007 — which roles a bare ``resource_grant`` conveys

**Decision: keep the current fail-closed behaviour and pin it.** A
:class:`~smartmatch_authz.ResourceGrant` carries a resource type, a resource id,
and an effect. It carries no role, so there is no engineering answer to "which
roles does it convey" — any mapping would be invented here rather than derived
from anything, and inventing one is the single change on this surface that turns
a denial into a permit. Conveying a role would need the *grant* to name one,
which is a ``resource_grant`` schema change and a product decision about what a
guest reviewer's access lets them do — not a decision this file can make.

So the rule is stated as a rule and tested as one, on every operation
(:func:`test_a_bare_resource_grant_never_satisfies_a_role_gated_operation`), and
:func:`test_resource_grant_carries_no_role_field` fails the day someone adds a
role-carrying field to the type — which is the moment the product decision has to
be made deliberately rather than arriving as a side effect of a new column.
"""

from __future__ import annotations

import ast
import dataclasses
import importlib
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from smartmatch_api import job_authz
from smartmatch_api.errors import ApiError
from smartmatch_authz import (
    AuthorizationError,
    Effect,
    Membership,
    OrgPath,
    Principal,
    Resource,
    ResourceGrant,
    assert_allowed,
)
from smartmatch_persistence.principals import ResolvedPrincipal

REPO_ROOT = Path(__file__).resolve().parents[2]
API_PACKAGE = REPO_ROOT / "services" / "api" / "smartmatch_api"

NOW = datetime(2026, 8, 17, 12, 0, tzinfo=UTC)

TENANT_ID = uuid.UUID("11111111-1111-4111-8111-111111111111")
OTHER_TENANT_ID = uuid.UUID("22222222-2222-4222-8222-222222222222")
USER_ID = uuid.UUID("33333333-3333-4333-8333-333333333333")
SOMEONE_ELSE_ID = uuid.UUID("44444444-4444-4444-8444-444444444444")
UNIT_ID = uuid.UUID("55555555-5555-4555-8555-555555555555")
JOB_ID = uuid.UUID("66666666-6666-4666-8666-666666666666")

#: The unit that owns the resource under test, and its sibling department. The
#: sibling is what makes unit scoping observable: a grant on one department must
#: not reach the other. Every job operation permitted it until A5 landed, which
#: is why the sibling shape has a row of its own rather than being folded into
#: "some other member".
OWNING_UNIT = "iawest.cpp.engineering.ie"
SIBLING_UNIT = "iawest.cpp.engineering.cs"
ORG_ROOT = "iawest"


# ---------------------------------------------------------------------------
# Deriving the operations from the code
# ---------------------------------------------------------------------------

_HTTP_METHODS = frozenset({"get", "post", "put", "patch", "delete", "head", "options"})

#: Calls that constitute authorizing a request. ``assert_allowed`` and
#: ``evaluate`` are the policy's own entry points; ``authorize_*`` is the naming
#: convention for a shared authorizer that wraps them for one resource type, as
#: :mod:`smartmatch_api.job_authz` does for the four job operations.
#:
#: ``_authorize*`` is still recognised, and nothing uses it now — the two
#: handler-local job authorizers it named were replaced by that shared module. It
#: stays because the convention it encodes is "a private authorizer inside a
#: router", which is a perfectly reasonable thing for the next command resource
#: to write; dropping it would make such a route silently look *unauthorized* to
#: :func:`test_the_route_calls_the_authorizer_the_matrix_names`, which is the
#: failure this file exists to catch and not one to introduce into it.
_POLICY_ENTRY_POINTS = frozenset({"assert_allowed", "evaluate"})
_AUTHORIZER_PREFIXES = ("authorize_", "_authorize")

#: The annotation that marks a handler parameter as the authenticated caller.
#: Its *absence* is what makes a route public, so this string is the discriminant
#: between "needs a matrix row" and "must be declared unauthenticated".
_PRINCIPAL_ANNOTATION = "CurrentPrincipal"


@dataclass(frozen=True, slots=True)
class Route:
    """One route as the source declares it."""

    method: str
    path: str
    module: str
    handler: str
    authenticated: bool
    authorizers: tuple[str, ...]

    @property
    def key(self) -> tuple[str, str]:
        return (self.method, self.path)


def _router_prefixes(tree: ast.Module) -> dict[str, str]:
    """Map each route-registering object in a module to its path prefix.

    ``app`` carries no prefix; an ``APIRouter`` carries whatever ``prefix=``
    says. Read from the assignment rather than from the imported object so the
    parser works on source alone — which is what lets
    :func:`test_the_completeness_check_reports_an_operation_with_no_row` feed it
    a synthetic module.
    """
    prefixes = {"app": ""}
    for node in tree.body:
        if not isinstance(node, ast.Assign) or len(node.targets) != 1:
            continue
        target = node.targets[0]
        value = node.value
        if not isinstance(target, ast.Name):
            continue
        if not (isinstance(value, ast.Call) and isinstance(value.func, ast.Name)):
            continue
        if value.func.id != "APIRouter":
            continue
        prefix = ""
        for keyword in value.keywords:
            if keyword.arg == "prefix" and isinstance(keyword.value, ast.Constant):
                prefix = str(keyword.value.value)
        prefixes[target.id] = prefix
    return prefixes


def _routes_in_source(source: str, module: str) -> list[Route]:
    """Every route a module declares, with what authorizes it.

    Operates on text, not on the imported module, for two reasons. Importing
    would report the routes FastAPI ended up with but not *which call in the
    handler authorizes them*, and that is the half that matters: a route is
    registered whether or not anybody checked permissions on it.
    """
    tree = ast.parse(source)
    prefixes = _router_prefixes(tree)
    routes: list[Route] = []

    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            continue
        for decorator in node.decorator_list:
            if not isinstance(decorator, ast.Call):
                continue
            func = decorator.func
            if not (isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name)):
                continue
            if func.value.id not in prefixes or func.attr not in _HTTP_METHODS:
                continue
            assert decorator.args and isinstance(decorator.args[0], ast.Constant), (
                f"{module}.{node.name} registers a route with a non-literal path; "
                f"the matrix cannot key on it"
            )
            path = prefixes[func.value.id] + str(decorator.args[0].value)
            authenticated = any(
                isinstance(arg.annotation, ast.Name) and arg.annotation.id == _PRINCIPAL_ANNOTATION
                for arg in (*node.args.args, *node.args.kwonlyargs)
            )
            routes.append(
                Route(
                    method=func.attr.upper(),
                    path=path,
                    module=module,
                    handler=node.name,
                    authenticated=authenticated,
                    authorizers=tuple(sorted(_authorizer_calls(node))),
                )
            )
    return routes


def _authorizer_calls(node: ast.AST) -> set[str]:
    """Names of authorization calls made anywhere inside a function."""
    found: set[str] = set()
    for child in ast.walk(node):
        if not (isinstance(child, ast.Call) and isinstance(child.func, ast.Name)):
            continue
        name = child.func.id
        if name in _POLICY_ENTRY_POINTS or name.startswith(_AUTHORIZER_PREFIXES):
            found.add(name)
    return found


def _source_files(package_dir: Path) -> list[Path]:
    """The modules that may register routes: the app module and every router."""
    files = [package_dir / "main.py"]
    files.extend(sorted(p for p in (package_dir / "routers").glob("*.py")))
    return [p for p in files if p.is_file() and p.name != "__init__.py"]


def _module_name(package_dir: Path, path: Path) -> str:
    if path.parent == package_dir:
        return f"smartmatch_api.{path.stem}"
    return f"smartmatch_api.{path.parent.name}.{path.stem}"


def _declared_routes(package_dir: Path = API_PACKAGE) -> dict[tuple[str, str], Route]:
    """Every route the API declares, keyed by method and full path.

    ``package_dir`` is a parameter so the machinery can be pointed at a scratch
    copy of the package. That is not a convenience: it is how the completeness
    check is shown to actually fail, without editing a file another agent owns.
    """
    routes: dict[tuple[str, str], Route] = {}
    for path in _source_files(package_dir):
        module = _module_name(package_dir, path)
        for route in _routes_in_source(path.read_text(encoding="utf-8"), module):
            assert route.key not in routes, (
                f"{route.method} {route.path} is declared twice: "
                f"{routes[route.key].module}.{routes[route.key].handler} and "
                f"{route.module}.{route.handler}"
            )
            routes[route.key] = route
    return routes


#: Routes that take no authenticated principal, and why that is correct. A route
#: absent from both this table and the matrix fails
#: :func:`test_every_route_is_either_authenticated_or_declared_public`, so
#: "forgot to authenticate it" cannot pass as "meant to be public".
UNAUTHENTICATED_ROUTES: dict[tuple[str, str], str] = {
    ("GET", "/api/health"): (
        "Liveness probe. Reports that the process is serving and nothing else — "
        "no dependency, topology, or version detail an unauthenticated caller "
        "could use (v1.1 §1.11). Requiring a token would make the probe depend "
        "on the identity provider being up."
    ),
    ("GET", "/u/{token}"): (
        "Public unsubscribe confirmation page. Reached from a link in an email "
        "by someone who by definition has no account, so the bearer token is "
        "the signed token in the path. It never changes state — the actual "
        "unsubscribe is the signed POST (v1.1 §1.10)."
    ),
}


# ---------------------------------------------------------------------------
# The operations
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Operation:
    """One authorized operation, as the matrix names it."""

    key: str
    method: str
    path: str
    module: str
    #: The call in the code that decides this operation. Checked against the
    #: source, so swapping a strict authorizer for a weaker one fails.
    authorizer: str
    #: The module-level constant the authorizer reads its role set from.
    roles_constant: str
    #: Where :data:`authorizer` and :data:`roles_constant` are *defined*, when
    #: that is not the module the route lives in. The four job operations are
    #: authorized by :mod:`smartmatch_api.job_authz` rather than by a helper in
    #: their own router, and this field is what lets the two checks below look
    #: for the function and the constant where they actually are — without
    #: loosening them into "somewhere in the package", which would stop them
    #: noticing a route that authorizes against a different set entirely.
    authorizer_module: str | None
    #: What that constant contains. Checked against the live object, so widening
    #: the role set in the code without updating the matrix fails.
    required_roles: frozenset[str]
    #: The ``resource_grant.resource_type`` an explicit grant on this operation's
    #: target would carry.
    resource_type: str
    #: Whether authorization can be scoped to the resource's owning org unit.
    #: ``False`` for every ``job`` operation until A5 landed; ``True`` for all
    #: five now. Kept as a field rather than deleted as always-true: it is the
    #: thing a new operation has to state about itself, and
    #: :func:`test_no_operation_is_reachable_from_a_sibling_department` requires
    #: it to be true, so a route that cannot scope has to say so and fail.
    unit_scoped: bool

    @property
    def resource_id(self) -> str:
        return str(UNIT_ID if self.resource_type == "org_unit" else JOB_ID)

    @property
    def authz_module(self) -> str:
        """Where the authorizer and its role constant live."""
        return self.authorizer_module or self.module


OPERATIONS: tuple[Operation, ...] = (
    Operation(
        key="import.create",
        method="POST",
        path="/v1/units/{unit_id}/imports",
        module="smartmatch_api.routers.imports",
        authorizer="assert_allowed",
        roles_constant="_IMPORT_ROLES",
        authorizer_module=None,
        required_roles=frozenset({"admin", "coordinator"}),
        resource_type="org_unit",
        unit_scoped=True,
    ),
    Operation(
        key="job.read",
        method="GET",
        path="/v1/jobs/{job_id}",
        module="smartmatch_api.routers.jobs",
        authorizer="authorize_job_read",
        roles_constant="JOB_OVERSIGHT_ROLES",
        authorizer_module="smartmatch_api.job_authz",
        required_roles=frozenset({"admin", "coordinator"}),
        resource_type="job",
        unit_scoped=True,
    ),
    Operation(
        key="job.events.read",
        method="GET",
        path="/v1/jobs/{job_id}/events",
        module="smartmatch_api.routers.jobs",
        authorizer="authorize_job_read",
        roles_constant="JOB_OVERSIGHT_ROLES",
        authorizer_module="smartmatch_api.job_authz",
        required_roles=frozenset({"admin", "coordinator"}),
        resource_type="job",
        unit_scoped=True,
    ),
    Operation(
        key="job.redrive",
        method="POST",
        path="/v1/jobs/{job_id}/redrive",
        module="smartmatch_api.routers.redrive",
        authorizer="authorize_job_command",
        roles_constant="JOB_OVERSIGHT_ROLES",
        authorizer_module="smartmatch_api.job_authz",
        required_roles=frozenset({"admin", "coordinator"}),
        resource_type="job",
        unit_scoped=True,
    ),
    Operation(
        key="job.abandon",
        method="POST",
        path="/v1/jobs/{job_id}/abandon",
        module="smartmatch_api.routers.redrive",
        authorizer="authorize_job_command",
        roles_constant="JOB_OVERSIGHT_ROLES",
        authorizer_module="smartmatch_api.job_authz",
        required_roles=frozenset({"admin", "coordinator"}),
        resource_type="job",
        unit_scoped=True,
    ),
)

OPERATIONS_BY_KEY = {operation.key: operation for operation in OPERATIONS}


# ---------------------------------------------------------------------------
# The principal shapes
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Shape:
    """A principal, described by what makes it interesting.

    The shapes are the matrix's columns. Each is a *reason a request might be
    allowed or refused* — a role, a place in the tree, a grant, a clock, a
    tenant — rather than a persona, so a cell always has a mechanical answer.
    """

    name: str
    description: str
    memberships: tuple[Membership, ...] = ()
    #: An explicit grant on this operation's own target resource, if any.
    grant: Effect | None = None
    suspended: bool = False
    #: The authorization tenant disagrees with the tenant the request was
    #: scoped by. Structurally unreachable today — ``PrincipalRepository``
    #: builds both from one row — which is exactly why it is asserted rather
    #: than assumed.
    cross_tenant: bool = False
    #: This principal submitted the job being acted on.
    is_job_actor: bool = False


def _member(path: str, role: str, **window: datetime) -> Membership:
    return Membership(granted_path=OrgPath.parse(path), role=role, **window)


SHAPES: tuple[Shape, ...] = (
    Shape(
        name="admin_at_org_root",
        description="admin membership at the root of the tenant's org tree",
        memberships=(_member(ORG_ROOT, "admin"),),
    ),
    Shape(
        name="coordinator_at_owning_unit",
        description="coordinator at exactly the unit that owns the resource",
        memberships=(_member(OWNING_UNIT, "coordinator"),),
    ),
    Shape(
        name="coordinator_at_sibling_unit",
        description="coordinator in a different department of the same tenant",
        memberships=(_member(SIBLING_UNIT, "coordinator"),),
    ),
    Shape(
        name="student_at_owning_unit",
        description="an active membership at the right unit carrying the wrong role",
        memberships=(_member(OWNING_UNIT, "student"),),
    ),
    Shape(
        name="member_with_no_memberships",
        description="authenticated, in the right tenant, holding nothing at all",
    ),
    Shape(
        name="resource_grant_only",
        description="an explicit allow grant on this resource and no membership (S-007)",
        grant=Effect.ALLOW,
    ),
    Shape(
        name="admin_with_explicit_deny",
        description="admin at the org root, with an explicit deny carved out on this resource",
        memberships=(_member(ORG_ROOT, "admin"),),
        grant=Effect.DENY,
    ),
    Shape(
        name="expired_coordinator_at_owning_unit",
        description="a coordinator membership whose validity window closed yesterday",
        memberships=(_member(OWNING_UNIT, "coordinator", valid_until=NOW - timedelta(days=1)),),
    ),
    Shape(
        name="suspended_admin",
        description="an administratively suspended account that otherwise holds everything",
        memberships=(_member(ORG_ROOT, "admin"),),
        grant=Effect.ALLOW,
        suspended=True,
    ),
    Shape(
        name="cross_tenant_coordinator",
        description="a covering coordinator whose authorization tenant is another tenant",
        memberships=(_member(OWNING_UNIT, "coordinator"),),
        cross_tenant=True,
    ),
    Shape(
        name="job_actor_without_role",
        description="the person who submitted the job, holding no role anywhere",
        is_job_actor=True,
    ),
    Shape(
        name="job_actor_with_explicit_deny",
        description="the person who submitted the job, explicitly denied on it",
        grant=Effect.DENY,
        is_job_actor=True,
    ),
)

SHAPES_BY_NAME = {shape.name: shape for shape in SHAPES}


# ---------------------------------------------------------------------------
# The matrix
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Cell:
    """The expected outcome of one operation for one principal shape."""

    permit: bool
    #: The stable reason code the denial must carry. Asserting the code and not
    #: merely the refusal is what stops a denial for the wrong reason — a
    #: suspension read as a missing role — from passing as coverage.
    reason: str | None = None
    #: The item that closes this cell, when the cell records a hole rather than
    #: the intended behaviour. Keys of :data:`GAPS`.
    gap: str | None = None
    why: str = ""


def permit(*, gap: str | None = None, why: str = "") -> Cell:
    return Cell(permit=True, gap=gap, why=why)


def deny(reason: str, *, gap: str | None = None, why: str = "") -> Cell:
    return Cell(permit=False, reason=reason, gap=gap, why=why)


#: Holes the matrix records rather than leaves blank. A cell carrying one of
#: these keys is asserting *current* behaviour that is known to be wrong or
#: incomplete, so closing the item is expected to break that cell — which is the
#: point: the test names what has to change.
#:
#: **Empty, and kept.** It held three entries, and closing them is what this
#: revision of the matrix records:
#:
#: * ``A5`` — the ``job`` table had no owning org unit, so no job operation could
#:   be scoped to a subtree. Migration ``0006`` adds ``job.owning_unit_id``,
#:   ``JobRepository.get`` joins the path in, and the four
#:   ``coordinator_at_sibling_unit`` cells that used to permit now deny.
#: * ``JOB-READ-IGNORES-GRANTS`` — the job-read path consulted no
#:   ``resource_grant``, so an explicit deny stopped ``/redrive`` and not the read
#:   of the same job. Both read routes now go through the policy, so the deny is
#:   obeyed everywhere and a grant-only principal gets the distinct reason code.
#: * ``JOB-READ-NO-TENANT-ASSERT`` — the tenant comparison was made on two of the
#:   four job routes. All four share one authorizer now, so it is made on all of
#:   them or on none.
#:
#: The machinery stays because the *practice* is the valuable part: the next
#: known-wrong cell should be recorded here rather than written as a green
#: assertion of behaviour nobody defends.
GAPS: dict[str, str] = {}


#: operation × principal shape → permit/deny.
#:
#: Read a row as "who may do this", a column as "what this kind of principal may
#: do". Every cell is executed against the real authorizer by
#: :func:`test_the_matrix_describes_what_the_code_does`; none of them is a claim
#: about intent that nothing checks.
MATRIX: dict[str, dict[str, Cell]] = {
    "import.create": {
        "admin_at_org_root": permit(
            why="an admin grant at the root covers every unit beneath it",
        ),
        "coordinator_at_owning_unit": permit(
            why="containment is inclusive, so a path covers itself",
        ),
        "coordinator_at_sibling_unit": deny(
            "no_grant",
            why=(
                "unit scoping works here, because an import names the unit it "
                "imports into. This was the cell the job operations could not "
                "have until A5 gave a job a unit of its own; they have it now."
            ),
        ),
        "student_at_owning_unit": deny(
            "no_grant",
            why="importing records into a unit is role-gated, not membership-gated",
        ),
        "member_with_no_memberships": deny("no_grant"),
        "resource_grant_only": deny(
            "resource_grant_lacks_required_role",
            why="S-007. A grant conveys reach, not authority. See the module docstring.",
        ),
        "admin_with_explicit_deny": deny(
            "explicit_resource_deny",
            why="v1.1 §2.1: an explicit deny on the resource beats inheritance",
        ),
        "expired_coordinator_at_owning_unit": deny("no_grant"),
        "suspended_admin": deny(
            "principal_suspended",
            why="suspension is checked first and does not wait for the IdP to revoke a token",
        ),
        "cross_tenant_coordinator": deny(
            "tenant_mismatch",
            why="tenant isolation is structural and precedes every grant question",
        ),
        "job_actor_without_role": deny(
            "no_grant",
            why=(
                "an import has no actor path — the shape degenerates to a "
                "role-less member, and that is correct: having submitted work is "
                "not authority to submit more."
            ),
        ),
        "job_actor_with_explicit_deny": deny(
            "explicit_resource_deny",
            why=(
                "the actor half of the shape is inert here for the reason above; "
                "what is left is a deny on the unit, which beats inheritance."
            ),
        ),
    },
    "job.read": {
        "admin_at_org_root": permit(why="an admin grant at the root covers every unit beneath it"),
        "coordinator_at_owning_unit": permit(
            why="containment is inclusive, so a path covers itself",
        ),
        "coordinator_at_sibling_unit": deny(
            "no_grant",
            why=(
                "A5, closed. This cell used to permit and to carry a gap marker: "
                "the role was checked and the unit was not, because there was no "
                "unit on a job to check against. `job.owning_unit_id` (migration "
                "0006) is that unit, and the policy's inherited-grant path now "
                "does the scoping the router used to skip."
            ),
        ),
        "student_at_owning_unit": deny(
            "no_grant",
            why="a job's command type and event payloads carry operational detail",
        ),
        "member_with_no_memberships": deny("no_grant"),
        "resource_grant_only": deny(
            "resource_grant_lacks_required_role",
            why=(
                "S-007. Denied before and denied now — what changed is the reason "
                "code: the old read path consulted no grants at all and answered "
                "`no_grant`, so the audit trail could not tell a caller who held a "
                "grant that conveyed nothing from one who held nothing."
            ),
        ),
        "admin_with_explicit_deny": deny(
            "explicit_resource_deny",
            why=(
                "the serious half of that omission, closed: an explicit deny on "
                "this job used to stop `/redrive` and *not* stop the read of the "
                "same job. v1.1 §2.1 rule 3 now applies on all four routes."
            ),
        ),
        "expired_coordinator_at_owning_unit": deny(
            "no_grant",
            why="`is_active_at` is applied by the policy, not assumed",
        ),
        "suspended_admin": deny(
            "principal_suspended",
            why=(
                "the check these routes previously lacked entirely: before A2 a "
                "suspended account kept full read access, because the policy was "
                "never invoked."
            ),
        ),
        "cross_tenant_coordinator": deny(
            "tenant_mismatch",
            why=(
                "still not reachable — the job load is tenant-scoped in its query "
                "— and now asserted on all four job routes rather than on two."
            ),
        ),
        "job_actor_without_role": permit(
            why=(
                "the actor path, and the reason job reads are not purely "
                "role-gated: whoever submitted the work can follow it without "
                "being given oversight of everyone else's."
            ),
        ),
        "job_actor_with_explicit_deny": deny(
            "explicit_resource_deny",
            why=(
                "the ordering that makes the actor path safe. The exception is "
                "ranked *below* the deny, so an administrator carving one job out "
                "of a grant is obeyed even against the person who submitted it — "
                "which is the one principal who would otherwise walk straight "
                "through the hole the deny exists to make."
            ),
        ),
    },
    "job.events.read": {
        "admin_at_org_root": permit(),
        "coordinator_at_owning_unit": permit(),
        "coordinator_at_sibling_unit": deny("no_grant"),
        "student_at_owning_unit": deny("no_grant"),
        "member_with_no_memberships": deny("no_grant"),
        "resource_grant_only": deny("resource_grant_lacks_required_role"),
        "admin_with_explicit_deny": deny("explicit_resource_deny"),
        "expired_coordinator_at_owning_unit": deny("no_grant"),
        "suspended_admin": deny("principal_suspended"),
        "cross_tenant_coordinator": deny("tenant_mismatch"),
        "job_actor_without_role": permit(
            why=(
                "the stream and the polling view answer to the same authorizer, "
                "which is what stops one being a way around the other. Since A5 "
                "that is literally the same function object, not two functions "
                "that agree."
            ),
        ),
        "job_actor_with_explicit_deny": deny("explicit_resource_deny"),
    },
    "job.redrive": {
        "admin_at_org_root": permit(),
        "coordinator_at_owning_unit": permit(),
        "coordinator_at_sibling_unit": deny(
            "no_grant",
            why="another department's failed work is no longer re-drivable from outside it",
        ),
        "student_at_owning_unit": deny(
            "no_grant",
            why=(
                "re-running failed work can repeat effects that already reached "
                "people outside the system"
            ),
        ),
        "member_with_no_memberships": deny("no_grant"),
        "resource_grant_only": deny(
            "resource_grant_lacks_required_role",
            why="S-007, and the reason code that keeps the gap visible in the audit trail",
        ),
        "admin_with_explicit_deny": deny("explicit_resource_deny"),
        "expired_coordinator_at_owning_unit": deny("no_grant"),
        "suspended_admin": deny("principal_suspended"),
        "cross_tenant_coordinator": deny("tenant_mismatch"),
        "job_actor_without_role": deny(
            "no_grant",
            why=(
                "the negative that matters most on this route: submitting a job "
                "does not entitle you to re-run it. Re-drive is oversight, not "
                "ownership — the actor path that opens `job.read` is deliberately "
                "absent here, which is the whole difference between "
                "`authorize_job_read` and `authorize_job_command`."
            ),
        ),
        "job_actor_with_explicit_deny": deny(
            "explicit_resource_deny",
            why=(
                "denied twice over, and the reason code says which one fired "
                "first — the deny outranks the absent actor path, so this reads "
                "the same here as on `job.read` even though the two routes treat "
                "the actor differently."
            ),
        ),
    },
    "job.abandon": {
        "admin_at_org_root": permit(),
        "coordinator_at_owning_unit": permit(),
        "coordinator_at_sibling_unit": deny("no_grant"),
        "student_at_owning_unit": deny(
            "no_grant",
            why="closing work permanently removes it from everyone else's view",
        ),
        "member_with_no_memberships": deny("no_grant"),
        "resource_grant_only": deny("resource_grant_lacks_required_role"),
        "admin_with_explicit_deny": deny("explicit_resource_deny"),
        "expired_coordinator_at_owning_unit": deny("no_grant"),
        "suspended_admin": deny("principal_suspended"),
        "cross_tenant_coordinator": deny("tenant_mismatch"),
        "job_actor_without_role": deny(
            "no_grant",
            why="abandon shares `authorize_job_command` with re-drive, at the same tightness",
        ),
        "job_actor_with_explicit_deny": deny("explicit_resource_deny"),
    },
}

CELLS = [(operation.key, shape.name) for operation in OPERATIONS for shape in SHAPES]


# ---------------------------------------------------------------------------
# Running a cell against the real authorizer
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class _JobStub:
    """The four fields the job authorizers read off a job row.

    A stub rather than a real ``JobRecord`` because the matrix is about
    principals, not about rows: every cell uses the same job, owned by
    :data:`OWNING_UNIT`, and varies only who is asking. The one row-shaped
    variation that matters — an absent ``owning_unit_path`` — is exercised in
    ``tests/authz/test_job_authz.py``, where it belongs.
    """

    actor_id: uuid.UUID | None
    id: uuid.UUID = JOB_ID
    tenant_id: uuid.UUID = TENANT_ID
    owning_unit_path: str = OWNING_UNIT


def _resolved(operation: Operation, shape: Shape) -> ResolvedPrincipal:
    """Build the principal a request in this shape would arrive carrying."""
    grants: tuple[ResourceGrant, ...] = ()
    if shape.grant is not None:
        grants = (ResourceGrant(operation.resource_type, operation.resource_id, shape.grant),)
    authorization_tenant = OTHER_TENANT_ID if shape.cross_tenant else TENANT_ID
    return ResolvedPrincipal(
        principal=Principal(
            user_id=str(USER_ID),
            tenant_id=str(authorization_tenant),
            memberships=shape.memberships,
            resource_grants=grants,
            suspended=shape.suspended,
        ),
        user_id=USER_ID,
        tenant_id=TENANT_ID,
        email="matrix@example.test",
    )


def _authorize(operation: Operation, shape: Shape) -> None:
    """Invoke the operation's real authorizer. Raises exactly what it raises.

    The dispatch is on the authorizer the matrix names, and the ``else`` is
    load-bearing: an operation authorized by something with no runner here fails
    rather than silently going unexercised.
    """
    resolved = _resolved(operation, shape)

    if operation.authorizer == "assert_allowed":
        assert_allowed(
            resolved.principal,
            Resource(
                resource_type=operation.resource_type,
                resource_id=operation.resource_id,
                # The handler builds this from the principal's own tenant, so a
                # mismatch is expressed on the principal, not here.
                tenant_id=str(resolved.tenant_id),
                owning_unit_path=OrgPath.parse(OWNING_UNIT),
            ),
            at=NOW,
            required_roles=operation.required_roles,
        )
        return

    # Both job entry points take the same arguments and differ only in whether
    # the actor exception applies, so the stub is built once and the dispatch is
    # a lookup rather than two near-identical branches.
    job_authorizers = {
        "authorize_job_read": job_authz.authorize_job_read,
        "authorize_job_command": job_authz.authorize_job_command,
    }
    if operation.authorizer in job_authorizers:
        actor_id = USER_ID if shape.is_job_actor else SOMEONE_ELSE_ID
        job_authorizers[operation.authorizer](resolved, _JobStub(actor_id=actor_id), at=NOW)
        return

    raise AssertionError(
        f"{operation.key} is authorized by {operation.authorizer!r}, which this "
        f"file has no runner for. Add one — an operation the matrix cannot "
        f"execute is an operation the matrix does not cover."
    )


def _observe(operation: Operation, shape: Shape) -> Cell:
    """Run a cell and report what the code decided, in the matrix's own terms."""
    try:
        _authorize(operation, shape)
    except AuthorizationError as exc:
        return Cell(permit=False, reason=exc.decision.reason)
    except ApiError as exc:
        assert exc.status_code == 403, (
            f"{operation.key} refused {shape.name} with {exc.status_code}, which is "
            f"not an authorization decision"
        )
        details = exc.details or {}
        return Cell(permit=False, reason=str(details.get("reason")))
    return Cell(permit=True)


# ---------------------------------------------------------------------------
# Completeness: the matrix is a statement about the code, not about intent
# ---------------------------------------------------------------------------


def _missing_rows(routes: dict[tuple[str, str], Route]) -> list[tuple[str, str]]:
    """Authenticated routes with no matrix row. The failure this file exists for."""
    covered = {(operation.method, operation.path) for operation in OPERATIONS}
    return sorted(
        key for key, route in routes.items() if route.authenticated and key not in covered
    )


def test_the_routes_parse_and_there_are_some() -> None:
    """A parser that finds nothing would make every check below vacuously pass."""
    routes = _declared_routes()
    assert routes, "no routes were found in smartmatch_api — did the router shape change?"
    assert any(route.authenticated for route in routes.values())


def test_every_authenticated_route_has_a_matrix_row() -> None:
    """A new operation with no row is a hole, and must be visible as one."""
    missing = _missing_rows(_declared_routes())
    assert not missing, (
        "these authenticated routes have no row in MATRIX, so nothing asserts who "
        "may call them: " + ", ".join(f"{method} {path}" for method, path in missing)
    )


def test_every_matrix_row_names_a_real_route() -> None:
    """The other direction: a row for a route that was renamed or removed."""
    routes = _declared_routes()
    extra = sorted(
        (operation.method, operation.path)
        for operation in OPERATIONS
        if (operation.method, operation.path) not in routes
    )
    assert not extra, "MATRIX has rows for routes that do not exist: " + ", ".join(
        f"{method} {path}" for method, path in extra
    )


def test_every_route_is_either_authenticated_or_declared_public() -> None:
    """A handler that loses its ``CurrentPrincipal`` must not pass as public."""
    routes = _declared_routes()
    undeclared = sorted(
        key
        for key, route in routes.items()
        if not route.authenticated and key not in UNAUTHENTICATED_ROUTES
    )
    assert not undeclared, (
        "these routes take no authenticated principal and are not declared in "
        "UNAUTHENTICATED_ROUTES: " + ", ".join(f"{method} {path}" for method, path in undeclared)
    )

    stale = sorted(
        key for key in UNAUTHENTICATED_ROUTES if key not in routes or routes[key].authenticated
    )
    assert not stale, (
        "UNAUTHENTICATED_ROUTES lists routes that no longer exist or that now "
        "take a principal: " + ", ".join(f"{method} {path}" for method, path in stale)
    )


@pytest.mark.parametrize("operation", OPERATIONS, ids=lambda op: op.key)
def test_the_route_calls_the_authorizer_the_matrix_names(operation: Operation) -> None:
    """A row that names a strict authorizer the route no longer calls is a lie."""
    route = _declared_routes()[(operation.method, operation.path)]
    assert route.authorizers, (
        f"{operation.method} {operation.path} authenticates its caller and then "
        f"authorizes nothing — no call to assert_allowed, evaluate, or an "
        f"_authorize* helper appears in {route.module}.{route.handler}"
    )
    assert operation.authorizer in route.authorizers, (
        f"MATRIX says {operation.key} is authorized by {operation.authorizer!r}, "
        f"but {route.module}.{route.handler} calls {list(route.authorizers)}"
    )
    assert route.module == operation.module, (
        f"MATRIX places {operation.key} in {operation.module}, "
        f"but the route is declared in {route.module}"
    )


@pytest.mark.parametrize("operation", OPERATIONS, ids=lambda op: op.key)
def test_the_required_roles_match_the_constant_in_the_code(operation: Operation) -> None:
    """Widening a role set in the code without saying so here must fail.

    The comparison is against the live object, so this is not a text match on a
    docstring: adding ``"student"`` to ``JOB_OVERSIGHT_ROLES`` breaks it.
    """
    module = importlib.import_module(operation.authz_module)
    declared = getattr(module, operation.roles_constant, None)
    assert declared is not None, (
        f"{operation.authz_module} has no {operation.roles_constant}; MATRIX names it "
        f"as where {operation.key} reads its role set from"
    )
    assert declared == operation.required_roles, (
        f"{operation.key}: MATRIX states {sorted(operation.required_roles)} but "
        f"{operation.authz_module}.{operation.roles_constant} is {sorted(declared)}"
    )


@pytest.mark.parametrize("operation", OPERATIONS, ids=lambda op: op.key)
def test_the_authorizer_reads_the_role_constant_the_matrix_names(operation: Operation) -> None:
    """The constant must be the one this operation's decision actually reads.

    Without this, ``JOB_OVERSIGHT_ROLES`` could keep its value while the authorizer
    started reading a different, wider set, and the check above would still pass
    against a constant nothing uses.
    """
    route = _declared_routes()[(operation.method, operation.path)]
    # When the operation names a dedicated authorizer, that function is where the
    # role set has to be read; when it calls the policy directly, the handler is.
    # ``authz_module`` is where to look for the former, which for the four job
    # operations is the shared module rather than their own router.
    target = (
        operation.authorizer
        if operation.authorizer.startswith(_AUTHORIZER_PREFIXES)
        else route.handler
    )
    source_path = REPO_ROOT / "services" / "api" / f"{operation.authz_module.replace('.', '/')}.py"
    assert source_path.is_file(), f"cannot find the source of {operation.authz_module}"
    tree = ast.parse(source_path.read_text(encoding="utf-8"))
    functions = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef) and node.name == target
    ]
    assert len(functions) == 1, f"expected exactly one {target} in {operation.authz_module}"
    names = {node.id for node in ast.walk(functions[0]) if isinstance(node, ast.Name)}
    assert operation.roles_constant in names, (
        f"{operation.authz_module}.{target} does not reference {operation.roles_constant}, "
        f"which MATRIX says is where {operation.key} gets its role set"
    )


def test_the_matrix_is_a_full_rectangle() -> None:
    """Every operation × every shape. A blank cell reads as an untested one.

    This is why the shapes are not chosen per operation: a shape that does not
    apply still has an answer, and writing it down is how "we did not think
    about that one" stops looking like "that one cannot happen".
    """
    assert set(MATRIX) == {operation.key for operation in OPERATIONS}, (
        f"MATRIX keys {sorted(MATRIX)} do not match the operations "
        f"{sorted(operation.key for operation in OPERATIONS)}"
    )
    expected = {shape.name for shape in SHAPES}
    for key, row in MATRIX.items():
        assert set(row) == expected, (
            f"{key} is missing cells for {sorted(expected - set(row))} and has "
            f"unknown cells for {sorted(set(row) - expected)}"
        )


def test_every_denial_cell_states_a_reason_code() -> None:
    """ "Denied" is not coverage; denied *for the right reason* is.

    A cell that only asserted refusal would pass when a suspension check
    accidentally became a missing-role check, or when a tenant mismatch started
    reading as an absent grant — and the reason code is what the audit trail
    carries, so a wrong one is a wrong record of why someone was refused.
    """
    for key, row in MATRIX.items():
        for shape_name, cell in row.items():
            if cell.permit:
                assert cell.reason is None, f"{key}/{shape_name}: a permit cell has a reason code"
            else:
                assert cell.reason, f"{key}/{shape_name}: a denial cell states no reason code"


def test_every_gap_marker_is_described_and_every_description_is_used() -> None:
    """A gap key with no entry says nothing; an entry with no cell is stale."""
    used = {cell.gap for row in MATRIX.values() for cell in row.values() if cell.gap}
    assert used <= set(GAPS), f"cells name gaps with no entry in GAPS: {sorted(used - set(GAPS))}"
    assert set(GAPS) <= used, (
        f"GAPS describes holes no cell records any more: {sorted(set(GAPS) - used)}"
    )


# ---------------------------------------------------------------------------
# The matrix, executed
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(("operation_key", "shape_name"), CELLS, ids=lambda part: str(part))
def test_the_matrix_describes_what_the_code_does(operation_key: str, shape_name: str) -> None:
    """Run one cell through the operation's real authorizer.

    Every cell, not only the interesting ones. A matrix whose permits are
    asserted and whose denials are assumed is the arrangement A4 exists to
    replace.
    """
    operation = OPERATIONS_BY_KEY[operation_key]
    shape = SHAPES_BY_NAME[shape_name]
    expected = MATRIX[operation_key][shape_name]
    observed = _observe(operation, shape)

    assert observed.permit == expected.permit, (
        f"{operation_key} × {shape_name}: matrix says "
        f"{'permit' if expected.permit else 'deny'}, code says "
        f"{'permit' if observed.permit else 'deny'} "
        f"({observed.reason or 'allowed'}). {shape.description}."
    )
    if not expected.permit:
        assert observed.reason == expected.reason, (
            f"{operation_key} × {shape_name}: matrix expects the denial reason "
            f"{expected.reason!r}, code gave {observed.reason!r}"
        )


@pytest.mark.parametrize("operation", OPERATIONS, ids=lambda op: op.key)
def test_every_operation_denies_a_principal_without_its_role(operation: Operation) -> None:
    """A4's core requirement: a negative test per operation.

    Deny-by-default means the interesting assertion is the denial, so this is
    stated as a property of the matrix rather than left to the reader to spot:
    every operation has at least one cell where a principal holding an active,
    covering membership is refused for holding the wrong role, and at least one
    where a principal holding nothing is refused.
    """
    row = MATRIX[operation.key]
    wrong_role = row["student_at_owning_unit"]
    assert not wrong_role.permit and wrong_role.reason == "no_grant", (
        f"{operation.key} admits an active membership carrying no required role"
    )
    nothing = row["member_with_no_memberships"]
    assert not nothing.permit, f"{operation.key} admits a principal holding nothing"


@pytest.mark.parametrize("operation", OPERATIONS, ids=lambda op: op.key)
def test_every_operation_denies_a_suspended_principal(operation: Operation) -> None:
    """Suspension is the one control that must not be reachable around.

    The suspended shape holds an admin membership at the org root *and* an
    explicit allow grant, so the denial proves a short-circuit rather than
    coinciding with an absence of permission.
    """
    cell = MATRIX[operation.key]["suspended_admin"]
    assert not cell.permit and cell.reason == "principal_suspended"
    observed = _observe(operation, SHAPES_BY_NAME["suspended_admin"])
    assert not observed.permit and observed.reason == "principal_suspended"


def test_every_operation_is_role_gated_today() -> None:
    """No operation currently reaches the policy's ungated grant path.

    :func:`smartmatch_authz.evaluate` allows a bare resource grant when an
    operation names no roles — the guest-reviewer case the policy is designed
    for. No route uses it yet. That matters for S-007: the fail-closed rule
    below costs nothing today because nothing depends on the path it closes.

    When the first ungated operation lands this fails, which is the right moment
    to confirm deliberately that a grant alone is meant to be enough for it.
    """
    ungated = [operation.key for operation in OPERATIONS if not operation.required_roles]
    assert not ungated, (
        f"these operations name no required roles, so a bare resource grant now "
        f"suffices for them: {ungated}. Confirm that is intended (S-007) and "
        f"update this test and the matrix together."
    )


# ---------------------------------------------------------------------------
# S-007 — the decision, stated as a rule
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("operation", OPERATIONS, ids=lambda op: op.key)
def test_a_bare_resource_grant_never_satisfies_a_role_gated_operation(
    operation: Operation,
) -> None:
    """The S-007 rule, pinned on every operation rather than on one.

    **A resource grant conveys reach, not authority.** It says "you may address
    this resource"; ``required_roles`` says "this action needs a coordinator".
    Reading the first as satisfying the second is what lets a guest reviewer
    holding one event grant submit imports and re-drive jobs.

    Kept as-is rather than loosened, and the reasoning is not "fail-closed is
    always right": ``ResourceGrant`` has a resource type, a resource id, and an
    effect, and *nothing that could name a role*. There is no correct mapping to
    derive, only one to invent. Conveying a role would mean the grant carrying
    one — a ``resource_grant`` schema change and a product decision about what a
    guest reviewer may do — so this is pinned, not decided, and the pin is what
    makes the next person decide it on purpose.
    """
    cell = MATRIX[operation.key]["resource_grant_only"]
    assert not cell.permit, (
        f"{operation.key} admits a principal whose only claim is a resource "
        f"grant. That is the S-007 loosening; it needs a product decision, not a "
        f"patch."
    )
    observed = _observe(operation, SHAPES_BY_NAME["resource_grant_only"])
    assert not observed.permit


def test_resource_grant_carries_no_role_field() -> None:
    """The reason S-007 has no engineering answer, asserted rather than asserted-in-prose.

    If someone adds a role or permission field to ``ResourceGrant``, the premise
    of the decision above changes and this fails — forcing the question to be
    reopened at the moment the type could answer it, instead of a bare grant
    quietly starting to convey something.
    """
    fields = {field.name for field in dataclasses.fields(ResourceGrant)}
    assert fields == {"resource_type", "resource_id", "effect"}, (
        f"ResourceGrant's fields are now {sorted(fields)}. If one of them names a "
        f"role or a permission, S-007 can finally be answered — reopen it "
        f"deliberately and update the matrix, rather than letting a bare grant "
        f"start conveying authority."
    )


def test_the_distinct_denial_reason_survives() -> None:
    """The reason code is the audit trail's record that S-007 is still open.

    ``resource_grant_lacks_required_role`` is not interchangeable with
    ``no_grant``: it says the principal held a grant that conveyed nothing,
    which is the population that would be affected the day the rule changes.
    Collapsing it into ``no_grant`` would make that population unmeasurable.

    Every operation, not the three that used to manage it. ``job.read`` and
    ``job.events.read`` answered ``no_grant`` here because the old read path
    consulted no grants at all — a refusal in the right direction that recorded
    the wrong thing, so a grant-holder and a stranger were indistinguishable in
    the audit trail. Listing all five is what stops the exception coming back.
    """
    for operation in OPERATIONS:
        cell = MATRIX[operation.key]["resource_grant_only"]
        assert cell.reason == "resource_grant_lacks_required_role", (
            f"{operation.key} no longer distinguishes a conveying-nothing grant "
            f"from no grant; it answers {cell.reason!r}"
        )


# ---------------------------------------------------------------------------
# A5, closed — measured rather than described
# ---------------------------------------------------------------------------


def test_no_operation_is_reachable_from_a_sibling_department() -> None:
    """Every operation, job ones included, is scoped to the resource's own unit.

    This test is the inverse of the one it replaces. That one asserted the hole
    as an equality — "exactly the four job operations admit a sibling
    department's coordinator" — so that the day ``job.owning_unit_id`` landed it
    would fail and point at the matrix rather than let four green cells go on
    asserting the old behaviour. It did, and this is the other side of it.

    Kept as a property over :data:`OPERATIONS` rather than as five cell lookups,
    because the thing worth pinning is *no exceptions*: a sixth operation added
    without unit scoping fails here, and does so with a message naming it.
    """
    leaking = {
        operation.key
        for operation in OPERATIONS
        if MATRIX[operation.key]["coordinator_at_sibling_unit"].permit
    }
    assert not leaking, (
        f"these operations admit a coordinator from a different department: "
        f"{sorted(leaking)}. Unit scoping is the control A5 exists to provide; if "
        f"an operation is genuinely tenant-wide, say so here deliberately."
    )

    unscoped = [operation.key for operation in OPERATIONS if not operation.unit_scoped]
    assert not unscoped, (
        f"these operations are marked as not unit-scoped: {unscoped}. Every "
        f"resource the API authorizes now carries an owning unit — org_unit is its "
        f"own, and job has one as of migration 0006."
    )


def test_the_owning_unit_is_what_decides_a_job_operation() -> None:
    """The same principal, the same job, a different owning unit — opposite answers.

    The denial above could be produced by a coordinator role that had simply
    stopped working, which would pass the test and fail the users. So the control
    is run in both directions against the real authorizer: the sibling-department
    coordinator is refused a job owned by :data:`OWNING_UNIT` and *allowed* the
    same job owned by :data:`SIBLING_UNIT`. What separates the two is the column
    A5 added and nothing else.
    """
    shape = SHAPES_BY_NAME["coordinator_at_sibling_unit"]
    resolved = _resolved(OPERATIONS_BY_KEY["job.redrive"], shape)

    with pytest.raises(AuthorizationError) as excinfo:
        job_authz.authorize_job_command(
            resolved, _JobStub(actor_id=SOMEONE_ELSE_ID, owning_unit_path=OWNING_UNIT), at=NOW
        )
    assert excinfo.value.decision.reason == "no_grant"

    allowed = job_authz.authorize_job_command(
        resolved, _JobStub(actor_id=SOMEONE_ELSE_ID, owning_unit_path=SIBLING_UNIT), at=NOW
    )
    assert allowed.allowed, (
        "the sibling-department coordinator cannot act on a job in their *own* "
        "department either, so the denial above is a broken role check rather "
        "than unit scoping"
    )


def test_the_four_job_operations_share_one_authorizer() -> None:
    """Two entry points over one decision, not four implementations that agree.

    The defect A5 sat next to was not only the missing column: the read routes
    and the command routes applied *different subsets* of the policy to the same
    resource, so an explicit deny stopped a re-drive and not a read. Asserting
    that the four operations name two functions from one module is what stops
    that arrangement growing back one route at a time.
    """
    modules = {
        operation.authz_module for operation in OPERATIONS if operation.resource_type == "job"
    }
    assert modules == {"smartmatch_api.job_authz"}, (
        f"job operations are authorized from {sorted(modules)}; a job decision made "
        f"in more than one module is the arrangement that let a deny be obeyed on "
        f"two routes and ignored on the other two"
    )

    authorizers = {
        operation.key: operation.authorizer
        for operation in OPERATIONS
        if operation.resource_type == "job"
    }
    assert authorizers == {
        "job.read": "authorize_job_read",
        "job.events.read": "authorize_job_read",
        "job.redrive": "authorize_job_command",
        "job.abandon": "authorize_job_command",
    }, (
        f"the read/command split changed: {authorizers}. The split is the actor "
        f"exception and nothing else — reads have it, commands do not."
    )


def test_a_job_with_no_recorded_actor_is_not_readable_by_a_role_less_member() -> None:
    """The actor path must not degrade into "nobody owns it, so anybody may read it".

    ``job.actor_id`` is nullable — system-initiated work records none — and the
    guard is ``is not None and ==``. Dropping the null check would make every
    such job readable by any authenticated member of the tenant, and no cell in
    the matrix would notice, because every cell uses a job that has an actor.
    """
    operation = OPERATIONS_BY_KEY["job.read"]
    resolved = _resolved(operation, SHAPES_BY_NAME["member_with_no_memberships"])
    with pytest.raises(AuthorizationError) as excinfo:
        job_authz.authorize_job_read(resolved, _JobStub(actor_id=None), at=NOW)
    assert excinfo.value.decision.reason == "no_grant"


# ---------------------------------------------------------------------------
# The completeness check, checked
# ---------------------------------------------------------------------------

#: A router module that declares one authenticated route. Used to prove the
#: derivation and the completeness check actually fire, rather than trusting
#: that they would.
_SYNTHETIC_ROUTER = '''
from fastapi import APIRouter

router = APIRouter(prefix="/v1/units", tags=["synthetic"])


@router.post("/{unit_id}/match-runs")
def create_match_run(principal: CurrentPrincipal, session: DbSession) -> None:
    """A new command resource that nobody added to the matrix."""
    unit = load_unit_or_404(session, tenant_id=principal.tenant_id, unit_id=unit_id)
    assert_allowed(principal.principal, unit, at=utc_now(), required_roles=_MATCH_ROLES)


@router.get("/public-thing")
def public_thing() -> None:
    """A route that takes no principal at all."""
    return None
'''


def test_the_derivation_finds_routes_and_their_authorizers() -> None:
    """The parser reports the method, the prefixed path, and what authorizes it."""
    routes = {route.key: route for route in _routes_in_source(_SYNTHETIC_ROUTER, "synthetic")}

    command = routes[("POST", "/v1/units/{unit_id}/match-runs")]
    assert command.authenticated
    assert command.authorizers == ("assert_allowed",)
    assert command.handler == "create_match_run"

    public = routes[("GET", "/v1/units/public-thing")]
    assert not public.authenticated
    assert public.authorizers == ()


def test_the_completeness_check_reports_an_operation_with_no_row() -> None:
    """The evidence that the control works: a new operation is a failure, not a shrug.

    :func:`_missing_rows` is the function
    :func:`test_every_authenticated_route_has_a_matrix_row` asserts on, run here
    against the real route set plus one route nobody wrote a row for. Without
    this, the completeness test would be indistinguishable from one that passes
    because it never looks at anything.
    """
    routes = dict(_declared_routes())
    assert not _missing_rows(routes)

    synthetic = _routes_in_source(_SYNTHETIC_ROUTER, "smartmatch_api.routers.synthetic")
    for route in synthetic:
        routes[route.key] = route

    missing = _missing_rows(routes)
    assert missing == [("POST", "/v1/units/{unit_id}/match-runs")], (
        f"adding an authenticated route with no matrix row was not reported as a "
        f"hole; _missing_rows returned {missing}"
    )


def test_an_unprotected_route_is_visible_as_unprotected() -> None:
    """A route that authenticates and then authorizes nothing has no authorizers.

    That emptiness is what
    :func:`test_the_route_calls_the_authorizer_the_matrix_names` asserts against,
    so this pins the signal it depends on.
    """
    source = _SYNTHETIC_ROUTER.replace(
        "assert_allowed(principal.principal, unit, at=utc_now(), required_roles=_MATCH_ROLES)",
        "pass",
    )
    routes = {route.key: route for route in _routes_in_source(source, "synthetic")}
    unprotected = routes[("POST", "/v1/units/{unit_id}/match-runs")]
    assert unprotected.authenticated
    assert unprotected.authorizers == ()


def test_a_public_route_dropped_into_the_package_is_reported() -> None:
    """The public-route half of the same control, on a scratch copy of the package.

    ``_declared_routes`` takes a directory so this can be shown rather than
    argued: a route with no ``CurrentPrincipal`` and no entry in
    ``UNAUTHENTICATED_ROUTES`` is undeclared, and the assertion in
    :func:`test_every_route_is_either_authenticated_or_declared_public` fires.
    """
    routes = {route.key: route for route in _routes_in_source(_SYNTHETIC_ROUTER, "synthetic")}
    undeclared = sorted(
        key
        for key, route in routes.items()
        if not route.authenticated and key not in UNAUTHENTICATED_ROUTES
    )
    assert undeclared == [("GET", "/v1/units/public-thing")]
