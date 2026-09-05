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
   passing quietly. A route that authenticates but authorizes nothing has no
   honest row to write — a row must name an authorizer the route really calls —
   so it is declared in :data:`AUTHENTICATED_ONLY_ROUTES` instead, and held to
   that claim: gaining an authorizer moves it back into the matrix.
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

**Decision: keep the current fail-closed behaviour and pin it, for every
*role-gated* operation.** A :class:`~smartmatch_authz.ResourceGrant` carries a
resource type, a resource id, and an effect. It carries no role, so there is
no engineering answer to "which roles does it convey" — any mapping would be
invented here rather than derived from anything, and inventing one is the
single change on this surface that turns a denial into a permit. Conveying a
role would need the *grant* to name one, which is a ``resource_grant`` schema
change and a product decision about what a guest reviewer's access lets them
do — not a decision this file can make.

So the rule is stated as a rule and tested as one, on every role-gated
operation (:func:`test_a_bare_resource_grant_never_satisfies_a_role_gated_operation`),
and :func:`test_resource_grant_carries_no_role_field` fails the day someone
adds a role-carrying field to the type — which is the moment the product
decision has to be made deliberately rather than arriving as a side effect of
a new column.

That decision has a second half, first *hypothesised* rather than reached when
``metrics.read``/``metrics.drill_down`` had no ratified policy to implement:
an operation that names *no* required roles at all asks nothing of a grant
that its plain "you may address this resource" does not already answer, so
``evaluate`` would permit it. :data:`INTENTIONALLY_UNGATED_OPERATIONS` and
:func:`test_a_bare_resource_grant_satisfies_an_intentionally_ungated_operation`
are that half — kept, empty, exactly as :data:`GAPS` is kept after being
emptied, because no operation in this codebase has needed the loosening once
one was actually characterised end to end.

**The metrics-authorization decision (CLOSED 2026-09-02,
`docs/decisions/metrics-authorization-decision-draft.md`) answered the
hypothesis differently.** ``metrics.read`` (aggregates) really does need no
finite role set — ``membership.role`` is free text, so there is no role set to
enumerate for "any active membership with a role" — but the decision's §4 is
explicit that a bare ``resource_grant`` is **denied**, not admitted, for
aggregates. That is neither of the two shapes S-007 had drawn: not
role-gated (no ``roles_constant`` to name), and not the ungated case either
(a grant alone must not suffice). It is a third, honest category —
:data:`MEMBERSHIP_ONLY_OPERATIONS` — checked with the same rigour as the
other two: both directions of membership in
:func:`test_every_membership_only_operation_is_declared`, and the negative
pinned directly in
:func:`test_a_bare_resource_grant_never_satisfies_a_membership_only_operation`
(the inverse of the ungated test that used to cover this operation). The
mechanism behind the category is ``smartmatch_authz.evaluate``'s
``require_membership`` keyword (policy module docstring, rule 5): it
withdraws the explicit-grant path as a substitute for membership without
requiring a role. ``metrics.drill_down`` did not need a third category — the
decision role-gates it outright (``admin``, ``coordinator`` only), so it is
an ordinary row naming :data:`_DRILL_DOWN_ROLES`, and both metrics operations
have left :data:`INTENTIONALLY_UNGATED_OPERATIONS` for good.

## The one sanctioned way past unit scoping

The same §4 carries a *scope* rule as well as role rules: "**``admin``:**
unrestricted within tenant for aggregates". Ordinary subtree containment
cannot express that, because nothing in the schema roots an ``admin``
membership at the tenant root — ``membership.granted_path`` is an ordinary
``ltree`` — so an admin attached below it was refused a sibling unit's
aggregates, a wrongful denial rather than a leak.
:data:`TENANT_WIDE_ROLE_OPERATIONS` is the third and last category, and it is
fenced harder than the other two because it is the only one that *widens*
anything: the mechanism is enumerated (``tenant_wide_roles``, policy module
docstring rule 7 — a role reaches tenant-wide only because an operation named
it), the ``admin_at_sibling_unit`` shape makes it visible as a full column,
and :func:`test_no_operation_is_reachable_from_a_sibling_department` now
asserts the exception as an *equality* against that table rather than leaving
"if an operation is genuinely tenant-wide, say so here" as advice. It applies
to aggregates only: ``metrics.drill_down`` passes no ``tenant_wide_roles``, so
the same admin reads a sibling unit's totals and not its ``row_data``.
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
    AccessDecision,
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


def _is_authorizer_name(name: str) -> bool:
    """Whether ``name`` is one of the policy's own entry points or an ``_authorize*`` helper."""
    return name in _POLICY_ENTRY_POINTS or name.startswith(_AUTHORIZER_PREFIXES)


def _referenced_name(expr: ast.expr) -> str | None:
    """The bare or attribute name an expression names, or ``None`` for anything else.

    ``assert_allowed`` (imported by name) and ``authz.assert_allowed`` (imported
    by module, then called through it) name the same function two different
    ways in the AST — the first is an :class:`ast.Name`, the second an
    :class:`ast.Attribute` whose ``.attr`` is what matters, not the module it
    hangs off of. Matching only the first is what let a route that imported its
    authorizer's module rather than the function itself pass this file as
    exempt while calling no authorizer at all.
    """
    if isinstance(expr, ast.Name):
        return expr.id
    if isinstance(expr, ast.Attribute):
        return expr.attr
    return None


def _authorizer_calls(node: ast.AST) -> set[str]:
    """Names of authorization calls made anywhere inside a function.

    Two shapes count as "calls this authorizer": calling it directly —
    ``assert_allowed(...)`` or ``authz.assert_allowed(...)``, the bare-name and
    attribute forms :func:`_referenced_name` normalises — and naming it as a
    FastAPI dependency — ``Depends(assert_allowed)`` or
    ``Depends(authz.assert_allowed)``. The dependency form is not a call to the
    authorizer *in the handler's own body*; FastAPI calls it during dependency
    resolution before the handler runs. Missing it would let a route wrap its
    authorization in ``Depends(...)`` and pass this file as exempt while
    genuinely authorizing nothing the matrix ever executes.
    """
    found: set[str] = set()
    for child in ast.walk(node):
        if not isinstance(child, ast.Call):
            continue
        name = _referenced_name(child.func)
        if name is not None and _is_authorizer_name(name):
            found.add(name)
            continue
        if isinstance(child.func, ast.Name) and child.func.id == "Depends":
            for arg in child.args:
                arg_name = _referenced_name(arg)
                if arg_name is not None and _is_authorizer_name(arg_name):
                    found.add(arg_name)
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
    ("POST", "/v1/unsubscribe"): (
        "The mutating half of the pair whose read half is ``GET /u/{token}``, "
        "and public for the same reason plus a stronger one. The person using "
        "it has by definition no account, and RFC 8058 one-click unsubscribe is "
        "issued by their *mail provider* with no session at all — so requiring "
        "a principal would make the endpoint unreachable by the mechanism it "
        "exists to serve. The signed token is the entire authorization: 256 "
        "bits derived by HMAC in the worker and stored only as a SHA-256 hash, "
        "so possession of the database confers no ability to unsubscribe "
        "anybody. Note that the response is identical for a real and an "
        "invented token, which is what stops the route being an oracle for "
        "whether an address is on our list."
    ),
    ("POST", "/v1/auth/login"): (
        "The pilot sign-in exchange, and necessarily public: it is what a "
        "caller uses to *obtain* a principal, so requiring one would make it "
        "unreachable. Owner-authorized and pilot-scoped "
        "(docs/decisions/pilot-login-decision-2026-09-04.md); it is not A1b "
        "and does not unblock it. "
        "Being public is the whole reason it is fenced elsewhere, and none of "
        "that fencing is authorization: LoginRequest forbids extra fields, so "
        "a body naming a role, tenant, or unit is rejected with a 422 rather "
        "than ignored — this route resolves an external_subject and nothing "
        "more, and every role still comes from `membership` on the next "
        "request. Quota is charged against the client address as the handler's "
        "first statement and committed immediately (ADR-0015), so an "
        "unauthenticated caller cannot use it as a free credential oracle. "
        "Every failure that is not a suspension returns one code and one "
        "message, so it cannot be used to discover which addresses exist. "
        "This is emphatically not the archived caller-selected identity endpoint "
        "(MM-A01), which was public *and* let the caller choose an identity. "
        "Here the caller must present a secret only the account holder has."
    ),
}


#: Routes that authenticate and then authorize *nothing*, and why that is
#: correct. This is a third category, not a loophole. ``OPERATIONS`` rows are
#: required to name an authorizer the route really calls
#: (:func:`test_the_route_calls_the_authorizer_the_matrix_names`), so a route
#: with no authorization has no honest row to write — and before this table
#: existed the only ways to land it were to invent an authorizer it does not
#: call, or to drop its ``CurrentPrincipal`` and declare it public. Both are
#: worse than saying plainly that authentication is the whole gate.
#:
#: The entry is held to that claim in both directions by
#: :func:`test_authentication_only_routes_really_authorize_nothing`: the route
#: must exist, must take a principal, and must call no authorizer. Adding an
#: authorization call to one of these routes therefore fails this file until
#: the route is moved into ``OPERATIONS`` and characterised properly.
AUTHENTICATED_ONLY_ROUTES: dict[tuple[str, str], str] = {
    ("GET", "/v1/me"): (
        "Identity echo. Every field is keyed by the caller's own verified "
        "subject, so there is no resource to authorize against that is not a "
        "roundabout 'are you you' — the token already settled that. It reports "
        "the memberships the server assigned; it never accepts a role from the "
        "caller, which is the defect Fix #7 named. A suspended account is "
        "deliberately still allowed to read it, so a suspended caller can see "
        "that it is suspended rather than receive a second flavour of 401."
    ),
    ("GET", "/v1/me/portals"): (
        "The account-to-portal mapping, and the same shape as GET /v1/me for "
        "the same reason: it has no path parameter, no query parameter and no "
        "body, so there is no resource to authorize against that is not a "
        "roundabout 'are you you'. Every entry is derived from the caller's "
        "own membership rows and the org units those rows already cover. "
        "Listing a portal is deliberately NOT a grant — the shells it feeds "
        "still reach /v1 routes that each run their own assert_allowed against "
        "the resource they load, so a portal reported in error is a shell "
        "whose every request is refused rather than an access someone gained. "
        "That is exactly why it needs no authorizer of its own, and why adding "
        "one here would be the wrong fix for anything: the authority is the "
        "operation being attempted, not the menu. The resolved unit_ids it "
        "returns are likewise not permissions — they are the ids that make the "
        "caller's *existing* memberships addressable, closing the gap between "
        "membership.granted_path (an ltree) and the unit_id every "
        "/v1/units/{unit_id}/... route takes, so a browser never has to "
        "construct one."
    ),
    ("POST", "/v1/auth/logout"): (
        "Ends the caller's own pilot session. Authentication is the entire "
        "gate, and it is load-bearing rather than decorative: the row revoked "
        "is looked up by the hash of the very token that authenticated the "
        "request, so a caller cannot name somebody else's session — the only "
        "token they can send is their own. There is no resource parameter to "
        "authorize, and 'may this principal end this principal's own session' "
        "is not a policy question. A caller holding a dev fixture token "
        "reaches it and is told `ended: false`, which is true: that credential "
        "has no row to revoke."
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
    #: The module-level constant the authorizer reads its role set from, or
    #: ``None`` when the operation names no required roles at all, so there is
    #: no constant to name either. ``None`` is only honest when
    #: :data:`required_roles` is empty and the operation's key appears in
    #: :data:`INTENTIONALLY_UNGATED_OPERATIONS` (a bare grant suffices) *or*
    #: :data:`MEMBERSHIP_ONLY_OPERATIONS` (a bare grant does not — an active
    #: membership is still required); both are checked, not merely declared
    #: (see the tests this field changes).
    roles_constant: str | None
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
    #: Whether the real authorizer passes ``require_membership=True`` to
    #: ``assert_allowed``/``evaluate`` (policy module docstring, rule 5).
    #: ``False`` for every operation except the two metrics ones: it is what
    #: lets ``metrics.read`` name no ``required_roles`` at all while still
    #: refusing a bare ``resource_grant`` — see :data:`MEMBERSHIP_ONLY_OPERATIONS`.
    #: Held against the source in both directions by
    #: :func:`test_the_authorizer_passes_require_membership_exactly_when_the_matrix_says_so`,
    #: because :func:`_authorize` builds its policy call *from this field* —
    #: so without that check the field would be a declaration compared with
    #: itself, and deleting the keyword from the real authorizer would leave
    #: this whole file green while a bare grant walked through §4's denial.
    require_membership: bool = False
    #: The module-level constant the authorizer passes as ``tenant_wide_roles``
    #: (policy module docstring, rule 7), or ``None`` when it passes none — the
    #: ordinary case, and the default, because tenant-wide reach is an
    #: exception a decision record has to name. ``metrics.read`` is the only
    #: member: the ratified metrics-authorization decision's §4 scope rules say
    #: "``admin``: unrestricted within tenant for aggregates", which subtree
    #: containment cannot express for an admin attached below the tenant root.
    #: Held against the source *and* against the live object by
    #: :func:`test_the_authorizer_passes_the_tenant_wide_roles_the_matrix_names`,
    #: in both directions and by name — :func:`_authorize` builds its policy
    #: call from :data:`tenant_wide_roles` below, so without that check this
    #: pair would be compared only with itself and deleting the keyword from
    #: ``_authorize_aggregate_read`` would leave ``tests/authz`` green while
    #: §4's tenant-wide admin permit silently disappeared.
    tenant_wide_roles_constant: str | None = None
    #: What that constant contains, or empty when there is none. Checked
    #: against the live object, so widening the tenant-wide set in the code
    #: without recording it here fails.
    tenant_wide_roles: frozenset[str] = frozenset()

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
    # Same shape as `import.create` in every respect that matters here: loads
    # a unit (off the review item's own import batch rather than off a path
    # parameter — see `routers/review.py`'s module docstring for why the unit
    # is derived, not named), then calls `assert_allowed` against an
    # `org_unit` Resource built from it, with the same two roles. No
    # `require_membership`, no `tenant_wide_roles` — deciding a review item
    # never widens past ordinary subtree containment.
    Operation(
        key="review.decide",
        method="POST",
        path="/v1/review-items/{review_item_id}/decision",
        module="smartmatch_api.routers.review",
        authorizer="assert_allowed",
        roles_constant="_REVIEW_ROLES",
        authorizer_module=None,
        required_roles=frozenset({"admin", "coordinator"}),
        resource_type="org_unit",
        unit_scoped=True,
    ),
    # ``metrics.read`` and ``metrics.drill_down`` now name two different
    # authorizers in ``routers/metrics.py``, per the ratified metrics
    # authorization decision (Option B, CLOSED 2026-09-02) — they no longer
    # share one call and one outcome the way the four job operations share
    # ``job_authz``. Both still mirror ``import.create``'s shape: load the
    # unit, then call ``smartmatch_authz.assert_allowed`` against an
    # ``org_unit`` Resource built from it.
    #
    # ``metrics.read`` (``_authorize_aggregate_read``) passes no
    # ``required_roles`` at all — there is no finite role set for "any active
    # unit membership with a role" — but does pass ``require_membership=True``,
    # which is what keeps a bare ``resource_grant`` from satisfying it despite
    # the empty role set. That combination is neither the role-gated shape nor
    # the fully ungated one S-007 originally drew, so it gets its own category,
    # :data:`MEMBERSHIP_ONLY_OPERATIONS`, rather than
    # :data:`INTENTIONALLY_UNGATED_OPERATIONS`. ``roles_constant=None`` follows
    # from the empty ``required_roles``, exactly as it did for the ungated
    # case — there is still no module-level roles constant to name.
    #
    # ``metrics.read`` also carries the one *scope* exception in this file:
    # ``tenant_wide_roles=_TENANT_WIDE_AGGREGATE_ROLES``. §4's scope rules say
    # "``admin``: unrestricted within tenant for aggregates", and subtree
    # containment cannot say that for an admin whose membership hangs below the
    # tenant root — nothing in the schema requires it to be rooted there. The
    # ``admin_at_sibling_unit`` shape is what makes the difference observable,
    # and it is the only cell in this whole matrix where a principal reaches a
    # unit no membership of theirs covers.
    #
    # ``metrics.drill_down`` (``_authorize_drill_down_read``) is role-gated
    # outright — ``admin``/``coordinator`` only, :data:`_DRILL_DOWN_ROLES` — so
    # it is an ordinary row, the same shape as every job operation above, and
    # is read off the source the same way (see the two checks below). It gets
    # **no** ``tenant_wide_roles``: §4 sends drill-down "per row above", which
    # is a role rule and not a scope one, so row-level access to ``row_data``
    # (§3: **High** sensitivity) keeps ordinary containment.
    Operation(
        key="metrics.read",
        method="GET",
        path="/v1/units/{unit_id}/metrics",
        module="smartmatch_api.routers.metrics",
        authorizer="_authorize_aggregate_read",
        roles_constant=None,
        authorizer_module=None,
        required_roles=frozenset(),
        resource_type="org_unit",
        unit_scoped=True,
        require_membership=True,
        tenant_wide_roles_constant="_TENANT_WIDE_AGGREGATE_ROLES",
        tenant_wide_roles=frozenset({"admin"}),
    ),
    Operation(
        key="metrics.drill_down",
        method="GET",
        path="/v1/units/{unit_id}/metrics/{metric_name}/drill-down",
        module="smartmatch_api.routers.metrics",
        authorizer="_authorize_drill_down_read",
        roles_constant="_DRILL_DOWN_ROLES",
        authorizer_module=None,
        required_roles=frozenset({"admin", "coordinator"}),
        resource_type="org_unit",
        unit_scoped=True,
        require_membership=True,
    ),
    # The two event reads share one authorizer, ``_authorize_event_read`` in
    # ``routers/events.py``, the way the four job operations share
    # ``job_authz``: both ask the identical question against the identical
    # resource — may this caller see this unit's discovery output — so a
    # widening applies to both or to neither and cannot reach one by accident.
    # That is why they name the same ``authorizer`` and the same
    # ``roles_constant`` rather than getting a private helper each.
    #
    # Otherwise these are the plainest rows in this file, identical in shape to
    # ``review.decide``: load the unit, call ``assert_allowed`` against an
    # ``org_unit`` Resource built from that row's own path, with
    # ``admin``/``coordinator`` required. No ``require_membership`` —
    # ``_EVENT_ROLES`` is non-empty, so ``evaluate``'s required-roles check
    # already refuses a bare ``resource_grant`` before the membership question
    # is reached, and passing the keyword would be a claim these rows would
    # then have to carry for no observable effect. No ``tenant_wide_roles`` —
    # the metrics decision's §4 is the only artifact in this repository that
    # makes anything tenant-wide, it says so of aggregate reads specifically,
    # and no committed artifact says it of an event catalog or a review queue.
    # Under deny-by-default the narrower reading is the only one available.
    Operation(
        key="events.read",
        method="GET",
        path="/v1/units/{unit_id}/events",
        module="smartmatch_api.routers.events",
        authorizer="_authorize_event_read",
        roles_constant="_EVENT_ROLES",
        authorizer_module=None,
        required_roles=frozenset({"admin", "coordinator"}),
        resource_type="org_unit",
        unit_scoped=True,
    ),
    Operation(
        key="events.tag_quarantine.read",
        method="GET",
        path="/v1/units/{unit_id}/tag-quarantine",
        module="smartmatch_api.routers.events",
        authorizer="_authorize_event_read",
        roles_constant="_EVENT_ROLES",
        authorizer_module=None,
        required_roles=frozenset({"admin", "coordinator"}),
        resource_type="org_unit",
        unit_scoped=True,
    ),
    # The .ics download is the one operation in this file whose role set is
    # deliberately *wider* than the read it hangs off. ``events.read`` refuses a
    # student because the catalog carries extraction provenance and source
    # references; an invite carries a title, a description and two instants for
    # one event, which is the thing a student is meant to have.
    #
    # So ``_INVITE_ROLES`` is ``admin``/``coordinator``/``student``, and this row
    # records the permit for ``student_at_owning_unit`` that ``events.read``
    # denies. That is not the whole rule the route enforces, and it matters that
    # it is not: a student who clears this check still has to produce an
    # ``attendance_record`` for the specific event before any bytes are written,
    # and an event they have no row for is a 404. That second gate is not policy
    # — it is a fact about one row, which ``evaluate`` has no way to see and this
    # matrix has no way to state — so it is asserted over HTTP in
    # ``tests/contract/test_calendar_ics.py`` instead. What this row is
    # responsible for is the half that *is* policy: nobody outside these three
    # roles reaches the handler at all, and the unit scoping is ordinary
    # containment.
    #
    # No ``require_membership`` — ``_INVITE_ROLES`` is non-empty, so ``evaluate``
    # refuses a bare ``resource_grant`` on the required-roles check before the
    # membership question is reached (S-007). No ``tenant_wide_roles`` — the
    # metrics decision's §4 is the only artifact in this repository that makes
    # anything tenant-wide, it says so of aggregate reads specifically, and an
    # .ics for one event is the narrowest read in the file.
    Operation(
        key="calendar.invite.download",
        method="GET",
        path="/v1/units/{unit_id}/events/{event_id}/invite.ics",
        module="smartmatch_api.routers.calendar",
        authorizer="_authorize_invite_read",
        roles_constant="_INVITE_ROLES",
        authorizer_module=None,
        required_roles=frozenset({"admin", "coordinator", "student"}),
        resource_type="org_unit",
        unit_scoped=True,
    ),
    # The two match-run operations share one authorizer,
    # ``_authorize_match_run`` in ``routers/match_runs.py``, for the reason the
    # two event reads share theirs: both ask the identical question — may this
    # caller work with this unit's match runs — against the identical
    # ``org_unit`` resource, so a widening applies to both or to neither and
    # cannot reach one by accident.
    #
    # ``admin``/``coordinator``, and no third role. The G1 worksheet's program
    # direction makes the shortlist a coordinator instrument ("coordinator
    # batch-invites; return 2-3 speakers") and names nobody else; under
    # deny-by-default the absence of a permit is a denial rather than an
    # invitation to guess. In particular a ``student`` is refused both: the
    # response carries every candidate professional's expertise evidence, the
    # weights in force, and the reasons some candidates could not be scored at
    # all, which is coordinator-and-above material.
    #
    # No ``require_membership`` — ``_MATCH_RUN_ROLES`` is non-empty, so
    # ``evaluate`` refuses a bare ``resource_grant`` on the required-roles
    # check before the membership question is reached. No ``tenant_wide_roles``
    # — the metrics decision's §4 is the only artifact in this repository that
    # makes anything tenant-wide, it says so of aggregate reads specifically,
    # and no committed artifact says it of a match run.
    Operation(
        key="match_run.create",
        method="POST",
        path="/v1/units/{unit_id}/match-runs",
        module="smartmatch_api.routers.match_runs",
        authorizer="_authorize_match_run",
        roles_constant="_MATCH_RUN_ROLES",
        authorizer_module=None,
        required_roles=frozenset({"admin", "coordinator"}),
        resource_type="org_unit",
        unit_scoped=True,
    ),
    Operation(
        key="match_run.read",
        method="GET",
        path="/v1/units/{unit_id}/match-runs/{match_run_id}",
        module="smartmatch_api.routers.match_runs",
        authorizer="_authorize_match_run",
        roles_constant="_MATCH_RUN_ROLES",
        authorizer_module=None,
        required_roles=frozenset({"admin", "coordinator"}),
        resource_type="org_unit",
        unit_scoped=True,
    ),
    # The four outreach operations share one authorizer,
    # ``_authorize_outreach`` in ``routers/outreach.py``, for the reason the two
    # match-run operations share theirs: all four ask the identical question —
    # may this caller work with this unit's outreach — against the identical
    # ``org_unit`` resource, so a widening applies to all of them or to none and
    # cannot reach one by accident.
    #
    # ``admin`` and ``coordinator``. Deliberately not ``student``: outreach is
    # correspondence sent on the institution's behalf, and the roles that may
    # compose it are the roles accountable for what it says.
    #
    # No ``require_membership`` and no ``tenant_wide_roles``, for the reasons
    # the match-run rows above give — ``_OUTREACH_ROLES`` is non-empty, so
    # ``evaluate`` refuses a bare ``resource_grant`` on the required-roles check
    # first, and no committed artifact makes anything about outreach tenant-wide.
    #
    # The fifth outreach operation, ``POST /v1/unsubscribe``, is in
    # ``UNAUTHENTICATED_ROUTES`` rather than here. That is not a gap in this
    # table: it is the one outreach route with no principal to authorize, and
    # the entry there says why.
    Operation(
        key="outreach.draft.create",
        method="POST",
        path="/v1/units/{unit_id}/outreach/drafts",
        module="smartmatch_api.routers.outreach",
        authorizer="_authorize_outreach",
        roles_constant="_OUTREACH_ROLES",
        authorizer_module=None,
        required_roles=frozenset({"admin", "coordinator"}),
        resource_type="org_unit",
        unit_scoped=True,
    ),
    Operation(
        key="outreach.draft.list",
        method="GET",
        path="/v1/units/{unit_id}/outreach/drafts",
        module="smartmatch_api.routers.outreach",
        authorizer="_authorize_outreach",
        roles_constant="_OUTREACH_ROLES",
        authorizer_module=None,
        required_roles=frozenset({"admin", "coordinator"}),
        resource_type="org_unit",
        unit_scoped=True,
    ),
    Operation(
        key="outreach.send.submit",
        method="POST",
        path="/v1/units/{unit_id}/outreach/drafts/{draft_id}/send",
        module="smartmatch_api.routers.outreach",
        authorizer="_authorize_outreach",
        roles_constant="_OUTREACH_ROLES",
        authorizer_module=None,
        required_roles=frozenset({"admin", "coordinator"}),
        resource_type="org_unit",
        unit_scoped=True,
    ),
    Operation(
        key="outreach.send.read",
        method="GET",
        path="/v1/units/{unit_id}/outreach/sends/{send_id}",
        module="smartmatch_api.routers.outreach",
        authorizer="_authorize_outreach",
        roles_constant="_OUTREACH_ROLES",
        authorizer_module=None,
        required_roles=frozenset({"admin", "coordinator"}),
        resource_type="org_unit",
        unit_scoped=True,
    ),
    # The send listing joined the four above rather than getting a table of
    # its own: it asks the same question of the same resource, and a listing
    # readable by somebody who cannot read the sends in it would be exactly
    # the widening this shared-authorizer arrangement exists to prevent.
    Operation(
        key="outreach.send.list",
        method="GET",
        path="/v1/units/{unit_id}/outreach/sends",
        module="smartmatch_api.routers.outreach",
        authorizer="_authorize_outreach",
        roles_constant="_OUTREACH_ROLES",
        authorizer_module=None,
        required_roles=frozenset({"admin", "coordinator"}),
        resource_type="org_unit",
        unit_scoped=True,
    ),
    # The five contact-channel operations live in
    # ``routers/outreach_contacts.py`` and authorize through *this same*
    # ``_authorize_outreach``, which is why their rows name it and set
    # ``authorizer_module`` to the module it is defined in — the arrangement
    # the four job operations already use for ``smartmatch_api.job_authz``. A
    # second helper in the new module would have been a second answer to one
    # question, and the first place a widening could reach the surface that
    # decides who may be written to at all.
    #
    # Same role set, for the same reason, and it matters most here: a row in
    # ``contact_channel`` asserts that a named person agreed to be contacted,
    # so the roles that may create one are the roles accountable for that
    # assertion.
    Operation(
        key="outreach.contact.list",
        method="GET",
        path="/v1/units/{unit_id}/outreach/contacts",
        module="smartmatch_api.routers.outreach_contacts",
        authorizer="_authorize_outreach",
        roles_constant="_OUTREACH_ROLES",
        authorizer_module="smartmatch_api.routers.outreach",
        required_roles=frozenset({"admin", "coordinator"}),
        resource_type="org_unit",
        unit_scoped=True,
    ),
    Operation(
        key="outreach.contact.read",
        method="GET",
        path="/v1/units/{unit_id}/outreach/contacts/{contact_channel_id}",
        module="smartmatch_api.routers.outreach_contacts",
        authorizer="_authorize_outreach",
        roles_constant="_OUTREACH_ROLES",
        authorizer_module="smartmatch_api.routers.outreach",
        required_roles=frozenset({"admin", "coordinator"}),
        resource_type="org_unit",
        unit_scoped=True,
    ),
    Operation(
        key="outreach.contact.create",
        method="POST",
        path="/v1/units/{unit_id}/outreach/contacts",
        module="smartmatch_api.routers.outreach_contacts",
        authorizer="_authorize_outreach",
        roles_constant="_OUTREACH_ROLES",
        authorizer_module="smartmatch_api.routers.outreach",
        required_roles=frozenset({"admin", "coordinator"}),
        resource_type="org_unit",
        unit_scoped=True,
    ),
    Operation(
        key="outreach.contact.update",
        method="PATCH",
        path="/v1/units/{unit_id}/outreach/contacts/{contact_channel_id}",
        module="smartmatch_api.routers.outreach_contacts",
        authorizer="_authorize_outreach",
        roles_constant="_OUTREACH_ROLES",
        authorizer_module="smartmatch_api.routers.outreach",
        required_roles=frozenset({"admin", "coordinator"}),
        resource_type="org_unit",
        unit_scoped=True,
    ),
    Operation(
        key="outreach.contact.transition",
        method="POST",
        path="/v1/units/{unit_id}/outreach/contacts/{contact_channel_id}/transitions",
        module="smartmatch_api.routers.outreach_contacts",
        authorizer="_authorize_outreach",
        roles_constant="_OUTREACH_ROLES",
        authorizer_module="smartmatch_api.routers.outreach",
        required_roles=frozenset({"admin", "coordinator"}),
        resource_type="org_unit",
        unit_scoped=True,
    ),
    # The two S12 funnel operations share one authorizer, ``_authorize_pipeline``,
    # for the reason ``_authorize_outreach`` is shared across its four: they ask
    # the identical question against the identical resource, so a widening
    # applies to both or to neither. The read is not given a looser role set than
    # the write — a journey is a named student's engagement record, and reading
    # one is not less consequential than advancing it.
    Operation(
        key="pipeline.record.read",
        method="GET",
        path="/v1/units/{unit_id}/pipeline-records/{record_id}",
        module="smartmatch_api.routers.pipeline",
        authorizer="_authorize_pipeline",
        roles_constant="_PIPELINE_ROLES",
        authorizer_module=None,
        required_roles=frozenset({"admin", "coordinator"}),
        resource_type="org_unit",
        unit_scoped=True,
    ),
    Operation(
        key="pipeline.stage.advance",
        method="POST",
        path="/v1/units/{unit_id}/pipeline-records/{record_id}/stages",
        module="smartmatch_api.routers.pipeline",
        authorizer="_authorize_pipeline",
        roles_constant="_PIPELINE_ROLES",
        authorizer_module=None,
        required_roles=frozenset({"admin", "coordinator"}),
        resource_type="org_unit",
        unit_scoped=True,
    ),
    # The three student rewards operations share one authorizer,
    # ``_authorize_student_rewards`` in ``routers/rewards.py``, for the reason
    # the two event reads and the two match-run operations share theirs: all
    # three ask the identical question — may this caller act on this unit's
    # rewards as a student — against the identical ``org_unit`` resource, so a
    # widening applies to all of them or to none.
    #
    # ``student``, and no second role. These are the first operations in this
    # file whose role set is not ``{admin, coordinator}``, and that is what card
    # P-REWARDS-API authorizes: "students see a server catalog and request
    # redemption". ``docs/decisions/d6-rewards-budget-decision-record.md`` §5
    # still lists "Read/redemption roles" among the fields no artifact resolves,
    # so a wider set would be the router inventing a decision; under
    # deny-by-default the absence of a permit is a denial. A coordinator is
    # therefore refused all three — including the catalog read, which they have
    # no need of: the catalog they administer is seeded, not browsed, and the
    # ticket list is a self-read that would show them only their own.
    #
    # This is also why ``test_every_operation_denies_a_principal_without_its_role``
    # now *chooses* its wrong-role shape rather than hard-coding
    # ``student_at_owning_unit``: for these three, ``student`` is the *right*
    # role, and ``coordinator_at_owning_unit`` is the active covering membership
    # carrying the wrong one.
    Operation(
        key="rewards.catalog.read",
        method="GET",
        path="/v1/units/{unit_id}/rewards",
        module="smartmatch_api.routers.rewards",
        authorizer="_authorize_student_rewards",
        roles_constant="_REWARDS_STUDENT_ROLES",
        authorizer_module=None,
        required_roles=frozenset({"student"}),
        resource_type="org_unit",
        unit_scoped=True,
    ),
    Operation(
        key="redemption.create",
        method="POST",
        path="/v1/units/{unit_id}/redemptions",
        module="smartmatch_api.routers.rewards",
        authorizer="_authorize_student_rewards",
        roles_constant="_REWARDS_STUDENT_ROLES",
        authorizer_module=None,
        required_roles=frozenset({"student"}),
        resource_type="org_unit",
        unit_scoped=True,
    ),
    Operation(
        key="redemption.read",
        method="GET",
        path="/v1/units/{unit_id}/redemptions",
        module="smartmatch_api.routers.rewards",
        authorizer="_authorize_student_rewards",
        roles_constant="_REWARDS_STUDENT_ROLES",
        authorizer_module=None,
        required_roles=frozenset({"student"}),
        resource_type="org_unit",
        unit_scoped=True,
    ),
    # The coordinator half, and a *different* authorizer on purpose:
    # ``_authorize_redemption_decision`` reads a role set of its own, so widening
    # the student surface cannot widen the surface that spends the budget, and
    # vice versa. ``admin``/``coordinator`` matches ``review.py::_REVIEW_ROLES``
    # — approving, denying or fulfilling a reward is the same kind of
    # consequential act on a student's record that deciding a review item is —
    # and ``d6-rewards-budget-decision-record.md`` §2 puts operational
    # administration of the rewards program with the IA West Coordinator by name.
    Operation(
        key="redemption.decide",
        method="POST",
        path="/v1/units/{unit_id}/redemptions/{redemption_id}/decision",
        module="smartmatch_api.routers.rewards",
        authorizer="_authorize_redemption_decision",
        roles_constant="_REDEMPTION_DECISION_ROLES",
        authorizer_module=None,
        required_roles=frozenset({"admin", "coordinator"}),
        resource_type="org_unit",
        unit_scoped=True,
    ),
    # The R2 engagement read. `{admin, coordinator}` and its own authorizer,
    # `_authorize_engagement_read`, rather than a share of `events.py`'s: the
    # two role sets agree today and a widening of one is not a reason to widen
    # the other.
    #
    # No `tenant_wide_roles`, which is the cell `admin_at_sibling_unit` below
    # measures. This *is* an aggregate, and the ratified metrics decision's §4
    # makes aggregate reads tenant-wide for an admin — but it makes them
    # tenant-wide for the metrics surface it names, and stretching a decision
    # over a route it does not mention is how scope widens without anybody
    # deciding to widen it.
    Operation(
        key="engagement.attendance_summary.read",
        method="GET",
        path="/v1/units/{unit_id}/engagement/attendance-summary",
        module="smartmatch_api.routers.engagement",
        authorizer="_authorize_engagement_read",
        roles_constant="_ENGAGEMENT_READ_ROLES",
        authorizer_module=None,
        required_roles=frozenset({"admin", "coordinator"}),
        resource_type="org_unit",
        unit_scoped=True,
    ),
    # The two Speaker Request operations (card ``CBA-EVENT-REQUEST``). They do
    # **not** share one authorizer, unlike the two event reads above, and the
    # split is the decision rather than an accident of layout.
    #
    # ``speaker_request.create`` is customer §12: "Event Hosts should be able
    # to create a new event / Speaker Request". The Event Host is the stored
    # ``volunteer`` role — ``smartmatch_domain.role_presentation`` maps it
    # there, following customer §4's "Volunteer — **Event Host** when
    # referring to the event-requesting role" — so ``volunteer`` is in this
    # role set and in no other role set in this file. ``admin`` and
    # ``coordinator`` are the Speaker Connector persona, which already owns
    # every other write to an ``event`` row in the same unit
    # (``review.decide`` decides it, ``pipeline.stage.advance`` moves it,
    # ``match_run.create`` runs against it); refusing them the creation of one
    # would not be a narrower policy, it would be an inconsistent one, and §13
    # makes them the recipients of these requests.
    #
    # ``speaker_request.list`` is customer §13: "Speaker Connectors should be
    # able to view incoming Speaker Requests", and §13 names nobody else. Under
    # deny-by-default the absence of a permit is a denial rather than an
    # invitation to guess, so ``volunteer`` is **not** in the read set even
    # though it is in the write set: no committed artifact says an Event Host
    # may read the other hosts' requests filed under the same unit, and the
    # create response hands a host back its own request without needing the
    # queue (OQ-CBA-014). That asymmetry is exactly why the two operations do
    # not share an authorizer — one helper taking the role set as an argument
    # would make one call site the place both are widened from, which is the
    # rule ``tests/authz/test_route_roles.py`` states in its own words.
    #
    # No ``require_membership`` on either: both role sets are non-empty, so
    # ``evaluate`` refuses a bare ``resource_grant`` on the required-roles
    # check before the membership question is reached (S-007). No
    # ``tenant_wide_roles`` on either — the metrics decision's §4 is the only
    # artifact in this repository that makes anything tenant-wide, it says so
    # of aggregate reads specifically, and a Speaker Request is a row in one
    # unit's own catalog.
    Operation(
        key="speaker_request.create",
        method="POST",
        path="/v1/units/{unit_id}/speaker-requests",
        module="smartmatch_api.routers.speaker_requests",
        authorizer="_authorize_speaker_request_create",
        roles_constant="_SPEAKER_REQUEST_CREATE_ROLES",
        authorizer_module=None,
        required_roles=frozenset({"admin", "coordinator", "volunteer"}),
        resource_type="org_unit",
        unit_scoped=True,
    ),
    Operation(
        key="speaker_request.list",
        method="GET",
        path="/v1/units/{unit_id}/speaker-requests",
        module="smartmatch_api.routers.speaker_requests",
        authorizer="_authorize_speaker_request_read",
        roles_constant="_SPEAKER_REQUEST_READ_ROLES",
        authorizer_module=None,
        required_roles=frozenset({"admin", "coordinator"}),
        resource_type="org_unit",
        unit_scoped=True,
    ),
    # The two student event reads (card ``CBA-STUDENT-EVENTS``, customer §15).
    # ``{student}`` and nothing else, which makes them the only rows in this file
    # whose role set contains ``student`` — everywhere else in this matrix
    # ``student`` is the shape used to *demonstrate* a denial.
    #
    # That is the decision, not an oversight. §15 gives browsing events and
    # adding them to a calendar to the Student and names nobody else, and under
    # deny-by-default the absence of a permit is a denial rather than an
    # invitation to guess. ``admin`` and ``coordinator`` are deliberately absent:
    # they read the same table through ``events.list``, whose response carries
    # the review status and extraction provenance this narrowed surface drops,
    # so admitting them here would add a second answer to a question already
    # answered rather than widen anything real. Compare ``invite.download``,
    # which admits all three — it hands out one representation of one event, so
    # there is only one route to admit anybody to.
    #
    # Both rows name **one** authorizer, and the contrast with the two
    # ``speaker_request.*`` rows above is the thing to read: those are split
    # because §12 admits the Event Host to the create and §13 admits only the
    # Speaker Connector to the queue, so the ``volunteer`` cell differs between
    # them. These two are one persona asking one question — may this student see
    # this unit's student surface — and every cell agrees. They therefore follow
    # the arrangement the five ``speaker_contact.*`` operations already use.
    #
    # What the matrix cannot see, and what is therefore not encoded here: the
    # agenda route additionally narrows its rows to the caller's own
    # ``attendance_record`` by a ``subject_id`` predicate in the query. That is a
    # self-scope the policy engine has no concept of; it is asserted over HTTP in
    # ``tests/contract/test_student_events_api.py`` instead, which is the same
    # division of labour ``invite.download``'s student branch already uses.
    #
    # No ``require_membership`` on either — the role set is non-empty, so
    # ``evaluate`` refuses a bare ``resource_grant`` on the required-roles check
    # before the membership question is reached (S-007). No ``tenant_wide_roles``
    # — the metrics decision's §4 is the only artifact that makes anything
    # tenant-wide, it says so of aggregate reads, and a student reading a sibling
    # department's catalog is not that.
    Operation(
        key="student_event.browse",
        method="GET",
        path="/v1/units/{unit_id}/student/events",
        module="smartmatch_api.routers.student_events",
        authorizer="_authorize_student_event_read",
        roles_constant="_STUDENT_EVENT_ROLES",
        authorizer_module=None,
        required_roles=frozenset({"student"}),
        resource_type="org_unit",
        unit_scoped=True,
    ),
    Operation(
        key="student_agenda.list",
        method="GET",
        path="/v1/units/{unit_id}/student/agenda",
        module="smartmatch_api.routers.student_events",
        authorizer="_authorize_student_event_read",
        roles_constant="_STUDENT_EVENT_ROLES",
        authorizer_module=None,
        required_roles=frozenset({"student"}),
        resource_type="org_unit",
        unit_scoped=True,
    ),
    # The five contact-management operations (card ``CBA-CONTACT-MANAGEMENT``,
    # customer §13). They share **one** authorizer, and the contrast with the
    # two Speaker Request rows directly above is the thing to read, because a
    # reviewer arriving here will ask why this card did not split its
    # authorizers the way that one just did.
    #
    # Those two are split because they are two personas: §12 admits the Event
    # Host to the create and §13 admits only the Speaker Connector to the
    # queue, so the ``volunteer`` cell differs between them, and a shared
    # helper taking the role set as an argument would make one call site the
    # place both are widened from.
    #
    # These five are one persona. Every one of them is the Speaker Connector
    # managing the contacts their own unit owns — adding one, listing them,
    # reading one, editing one, correcting the classification on one. No
    # committed artifact distinguishes among them and §13 names one role for
    # the whole surface, so the ``volunteer`` cell is a deny on all five and
    # every other cell agrees too. They therefore follow the arrangement the
    # five ``outreach.contact.*`` operations already use for
    # ``_authorize_outreach``: one helper, one role set, one place a widening
    # can happen and one place a reviewer has to look for it. Five identical
    # helpers would be five answers to a question asked once, and the day §13
    # does split, the split should have to be argued in a diff rather than
    # already sitting there unused.
    #
    # ``authorizer_module`` is ``None`` on all five because the helper lives in
    # the same module as the routes — unlike the ``outreach.contact.*`` rows,
    # whose helper lives over in ``routers/outreach.py``.
    #
    # The role set is ``{admin, coordinator}`` and **not**
    # ``speaker_request.create``'s ``{admin, coordinator, volunteer}``. That one
    # cell is the whole difference between the two cards: an Event Host asks
    # for a speaker, and managing the roster of professionals a unit may draw
    # on is not part of asking.
    #
    # No ``require_membership`` on any of them — the role set is non-empty, so
    # ``evaluate`` refuses a bare ``resource_grant`` on the required-roles
    # check before the membership question is reached (S-007). No
    # ``tenant_wide_roles`` — a contact is a row in one unit's own roster, and
    # the metrics decision's §4 is the only artifact in this repository that
    # makes anything tenant-wide.
    Operation(
        key="speaker_contact.create",
        method="POST",
        path="/v1/units/{unit_id}/speaker-contacts",
        module="smartmatch_api.routers.cba_contacts",
        authorizer="_authorize_speaker_contacts",
        roles_constant="_SPEAKER_CONTACT_ROLES",
        authorizer_module=None,
        required_roles=frozenset({"admin", "coordinator"}),
        resource_type="org_unit",
        unit_scoped=True,
    ),
    Operation(
        key="speaker_contact.list",
        method="GET",
        path="/v1/units/{unit_id}/speaker-contacts",
        module="smartmatch_api.routers.cba_contacts",
        authorizer="_authorize_speaker_contacts",
        roles_constant="_SPEAKER_CONTACT_ROLES",
        authorizer_module=None,
        required_roles=frozenset({"admin", "coordinator"}),
        resource_type="org_unit",
        unit_scoped=True,
    ),
    Operation(
        key="speaker_contact.read",
        method="GET",
        path="/v1/units/{unit_id}/speaker-contacts/{professional_id}",
        module="smartmatch_api.routers.cba_contacts",
        authorizer="_authorize_speaker_contacts",
        roles_constant="_SPEAKER_CONTACT_ROLES",
        authorizer_module=None,
        required_roles=frozenset({"admin", "coordinator"}),
        resource_type="org_unit",
        unit_scoped=True,
    ),
    Operation(
        key="speaker_contact.update",
        method="PATCH",
        path="/v1/units/{unit_id}/speaker-contacts/{professional_id}",
        module="smartmatch_api.routers.cba_contacts",
        authorizer="_authorize_speaker_contacts",
        roles_constant="_SPEAKER_CONTACT_ROLES",
        authorizer_module=None,
        required_roles=frozenset({"admin", "coordinator"}),
        resource_type="org_unit",
        unit_scoped=True,
    ),
    Operation(
        key="speaker_contact.correct_classification",
        method="POST",
        path="/v1/units/{unit_id}/speaker-contacts/{professional_id}/classification",
        module="smartmatch_api.routers.cba_contacts",
        authorizer="_authorize_speaker_contacts",
        roles_constant="_SPEAKER_CONTACT_ROLES",
        authorizer_module=None,
        required_roles=frozenset({"admin", "coordinator"}),
        resource_type="org_unit",
        unit_scoped=True,
    ),
)

#: Operations that intentionally reach the policy's ungated grant path — S-007
#: answered "yes": an operation names no required roles at all, and a bare
#: ``resource_grant`` is enough to satisfy it anyway, because it asks for
#: nothing beyond "you may address this resource".
#:
#: **Empty, and kept** — the same posture :data:`GAPS` takes after being
#: emptied. This constant used to name ``metrics.read`` and
#: ``metrics.drill_down`` as a working hypothesis, before either operation had
#: a ratified policy behind it. The metrics authorization decision (CLOSED
#: 2026-09-02) answered differently: ``metrics.drill_down`` is role-gated
#: outright, and ``metrics.read`` needs membership even though it needs no
#: role — see :data:`MEMBERSHIP_ONLY_OPERATIONS`. Neither is the shape this
#: table exists for. It stays, rather than being deleted along with its last
#: members, because the next operation that genuinely asks for nothing beyond
#: resource reach should land here on purpose, checked in both directions by
#: :func:`test_every_ungated_operation_is_declared_intentional` exactly as it
#: was for these two.
INTENTIONALLY_UNGATED_OPERATIONS: frozenset[str] = frozenset()

#: Operations that name no ``required_roles`` yet still refuse a bare
#: ``resource_grant`` — the category :data:`INTENTIONALLY_UNGATED_OPERATIONS`
#: does not cover. Mechanically: ``require_membership=True`` on the real
#: authorizer's call to ``assert_allowed``/``evaluate`` (policy module
#: docstring, rule 5). ``metrics.read`` is the first and, so far, only member:
#: the decision's §4 gives it no finite role set to enumerate ("any active
#: unit membership with a role" — ``membership.role`` is free text) while
#: explicitly denying a bare grant, which is a policy shape neither
#: :data:`INTENTIONALLY_UNGATED_OPERATIONS` nor an ordinary ``roles_constant``
#: row could express.
#:
#: Checked with the same rigour S-007's table always has, in both directions —
#: :func:`test_every_membership_only_operation_is_declared` — and pinned as a
#: negative just as explicitly as the ungated table's positive is:
#: :func:`test_a_bare_resource_grant_never_satisfies_a_membership_only_operation`
#: is the direct inverse of
#: :func:`test_a_bare_resource_grant_satisfies_an_intentionally_ungated_operation`,
#: proving the same shape of grant is refused here where it used to be admitted.
MEMBERSHIP_ONLY_OPERATIONS: frozenset[str] = frozenset({"metrics.read"})

#: Operations that permit a role *outside* the resource's own subtree — the one
#: deliberate exception to the unit scoping
#: :func:`test_no_operation_is_reachable_from_a_sibling_department` otherwise
#: enforces without exception. Mechanically: a non-empty
#: ``tenant_wide_roles`` on the real authorizer's policy call (policy module
#: docstring, rule 7).
#:
#: ``metrics.read`` is the only member, and the ratified metrics-authorization
#: decision's §4 is the whole of its authority: "**``admin``:** unrestricted
#: within tenant for aggregates". Note what it is *not*: not
#: ``metrics.drill_down`` (§4 sends that "per row above", a role rule that says
#: nothing about scope, and §3 rates its ``row_data`` **High**), and not any
#: role but ``admin``.
#:
#: Checked in both directions by
#: :func:`test_every_tenant_wide_operation_is_declared`, exactly as the other
#: two tables are, so an operation cannot gain tenant-wide reach in the code
#: without landing here, and this table cannot claim reach the code does not
#: give. The permit itself is exercised by
#: :func:`test_a_tenant_wide_role_reaches_a_unit_its_own_path_does_not_cover`
#: and its precedence limits by
#: :func:`test_a_tenant_wide_role_never_outranks_suspension_tenant_or_an_explicit_deny`.
TENANT_WIDE_ROLE_OPERATIONS: frozenset[str] = frozenset({"metrics.read"})

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
        name="admin_at_sibling_unit",
        description=(
            "admin membership in a different department of the same tenant — "
            "an admin the org tree does not root at the tenant root"
        ),
        memberships=(_member(SIBLING_UNIT, "admin"),),
    ),
    Shape(
        name="student_at_owning_unit",
        description=(
            "an active membership at the right unit carrying the `student` role "
            "— the wrong role for eleven of the fifteen operations, and the "
            "right one for the three the rewards card gates on `student`"
        ),
        memberships=(_member(OWNING_UNIT, "student"),),
    ),
    Shape(
        name="volunteer_at_owning_unit",
        description=(
            "an active membership at the right unit carrying the `volunteer` "
            "role — the wrong role for every operation in this file, which is "
            "exactly why it exists. `calendar.invite.download` admits "
            "`admin`, `coordinator` *and* `student`, so before this shape there "
            "was no covering membership left that its row could refuse for a "
            "role reason, and `_wrong_role_shape_for` said so rather than "
            "quietly skipping the assertion"
        ),
        memberships=(_member(OWNING_UNIT, "volunteer"),),
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
        "admin_at_sibling_unit": deny(
            "no_grant",
            why=(
                "admin is a required role here and the membership is active, so "
                "the only thing refusing this principal is the path: a sibling "
                "department does not contain the owning unit. Being an admin "
                "somewhere is not authority everywhere — `metrics.read` is the "
                "single operation the ratified decision makes tenant-wide, and "
                "it is tenant-wide for *aggregates* only."
            ),
        ),
        "student_at_owning_unit": deny(
            "no_grant",
            why="importing records into a unit is role-gated, not membership-gated",
        ),
        "volunteer_at_owning_unit": deny(
            "no_grant",
            why=(
                "`volunteer` is not in this operation's role set, and the "
                "membership is active at exactly the owning unit — so the "
                "role is the only thing left that can refuse it"
            ),
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
        "admin_at_sibling_unit": deny(
            "no_grant",
            why="the role is right and the department is not; jobs are scoped by their own unit",
        ),
        "student_at_owning_unit": deny(
            "no_grant",
            why="a job's command type and event payloads carry operational detail",
        ),
        "volunteer_at_owning_unit": deny(
            "no_grant",
            why=(
                "`volunteer` is not in this operation's role set, and the "
                "membership is active at exactly the owning unit — so the "
                "role is the only thing left that can refuse it"
            ),
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
        "admin_at_sibling_unit": deny(
            "no_grant",
            why="same as job.read — one authorizer, one answer",
        ),
        "student_at_owning_unit": deny("no_grant"),
        "volunteer_at_owning_unit": deny(
            "no_grant",
            why=(
                "`volunteer` is not in this operation's role set, and the "
                "membership is active at exactly the owning unit — so the "
                "role is the only thing left that can refuse it"
            ),
        ),
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
        "admin_at_sibling_unit": deny(
            "no_grant",
            why="a command on another department's job is refused on the path, admin or not",
        ),
        "student_at_owning_unit": deny(
            "no_grant",
            why=(
                "re-running failed work can repeat effects that already reached "
                "people outside the system"
            ),
        ),
        "volunteer_at_owning_unit": deny(
            "no_grant",
            why=(
                "`volunteer` is not in this operation's role set, and the "
                "membership is active at exactly the owning unit — so the "
                "role is the only thing left that can refuse it"
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
        "admin_at_sibling_unit": deny(
            "no_grant",
            why="abandon shares `authorize_job_command` with re-drive, at the same tightness",
        ),
        "student_at_owning_unit": deny(
            "no_grant",
            why="closing work permanently removes it from everyone else's view",
        ),
        "volunteer_at_owning_unit": deny(
            "no_grant",
            why=(
                "`volunteer` is not in this operation's role set, and the "
                "membership is active at exactly the owning unit — so the "
                "role is the only thing left that can refuse it"
            ),
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
    # Same shape as `import.create`'s own row, cell for cell: both operations
    # authorize an `org_unit` resource through the same `assert_allowed` call
    # with the same two required roles, no `require_membership`, no
    # `tenant_wide_roles`. The only thing that differs between the two routes
    # is *how* the unit is found — a path parameter for `import.create`, a
    # join through the review item's own batch for `review.decide` — and
    # `_authorize` never exercises that difference: both reach `evaluate`
    # through an identically-shaped `Resource`.
    "review.decide": {
        "admin_at_org_root": permit(
            why="an admin grant at the root covers every unit beneath it",
        ),
        "coordinator_at_owning_unit": permit(
            why="containment is inclusive, so a path covers itself",
        ),
        "coordinator_at_sibling_unit": deny(
            "no_grant",
            why=(
                "unit scoping works here exactly as it does for import.create: "
                "a review item names the unit its batch was imported into, and "
                "a sibling department's coordinator does not cover it"
            ),
        ),
        "admin_at_sibling_unit": deny(
            "no_grant",
            why=(
                "admin is a required role here and the membership is active, so "
                "the only thing refusing this principal is the path: a sibling "
                "department does not contain the owning unit. `review.decide` "
                "passes no `tenant_wide_roles` — deciding a review item is not "
                "the aggregate-reads exception `metrics.read` carries."
            ),
        ),
        "student_at_owning_unit": deny(
            "no_grant",
            why="deciding a submitted record is role-gated, not membership-gated",
        ),
        "volunteer_at_owning_unit": deny(
            "no_grant",
            why=(
                "`volunteer` is not in this operation's role set, and the "
                "membership is active at exactly the owning unit — so the "
                "role is the only thing left that can refuse it"
            ),
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
                "a review decision has no actor path — the shape degenerates to "
                "a role-less member, and that is correct: this operation is not "
                "reachable through job submission at all"
            ),
        ),
        "job_actor_with_explicit_deny": deny(
            "explicit_resource_deny",
            why=(
                "the actor half of the shape is inert here for the reason above; "
                "what is left is a deny on the unit, which beats inheritance"
            ),
        ),
    },
    # The two metrics rows no longer share an outcome on every shape, because
    # they no longer share a policy: `metrics.read` is membership-only
    # (`_authorize_aggregate_read`, MEMBERSHIP_ONLY_OPERATIONS) and
    # `metrics.drill_down` is role-gated to `_DRILL_DOWN_ROLES`
    # (`_authorize_drill_down_read`) — the ratified metrics authorization
    # decision's Option B split (CLOSED 2026-09-02, decision record §4). They
    # still agree on every cell that is purely about unit scoping, suspension,
    # tenant isolation, or an explicit deny, because both routes still load the
    # same unit and reach `evaluate` through it; they diverge exactly on the
    # cells that ask "which role" — `student_at_owning_unit` and
    # `resource_grant_only`.
    "metrics.read": {
        "admin_at_org_root": permit(
            why="an admin grant at the root covers every unit beneath it",
        ),
        "coordinator_at_owning_unit": permit(
            why="containment is inclusive, so a path covers itself",
        ),
        "coordinator_at_sibling_unit": deny(
            "no_grant",
            why=(
                "unit scoping is a path question, not a role question — it still "
                "applies with no required_roles at all, exactly as it does on "
                "every gated operation above"
            ),
        ),
        "admin_at_sibling_unit": permit(
            why=(
                "the decision's §4 scope rule, made real, and the only cell in "
                "this matrix where a principal reaches a unit no membership of "
                "theirs covers: '**admin:** unrestricted within tenant for "
                "aggregates'. Nothing in the schema roots an admin membership "
                "at the tenant root — `membership.granted_path` is an ordinary "
                "`ltree` — so an admin attached to a sibling department was "
                "getting a 403 on this unit's aggregates, which §4 does not "
                "say. `_authorize_aggregate_read` passes "
                "`tenant_wide_roles=_TENANT_WIDE_AGGREGATE_ROLES`, and "
                "`evaluate`'s Path 1b (policy module docstring, rule 7) allows "
                "with `tenant_wide_role_grant` — a distinct code, so this "
                "population stays countable rather than blending into "
                "`inherited_unit_grant`. Compare `coordinator_at_sibling_unit` "
                "immediately above, which still denies: the widening is by "
                "enumerated role, not by 'sibling units are fine now'."
            ),
        ),
        "student_at_owning_unit": permit(
            why=(
                "the cell that would deny on every role-gated operation above "
                "and does not here: `required_roles` is empty, so `evaluate`'s "
                "role filter (`if required_roles and membership.role not in "
                "required_roles`) never triggers — an active membership at the "
                "right unit is enough on its own, whichever role it carries. "
                "This is the decision's §4 aggregate rule: 'any active unit "
                "membership with a role'."
            ),
        ),
        "volunteer_at_owning_unit": permit(
            why=(
                "the same reason `student_at_owning_unit` is permitted "
                "here and denied everywhere else: `required_roles` is "
                "empty, so `evaluate`'s role filter never triggers and an "
                "active membership at the right unit is enough on its own, "
                "whichever role it carries"
            ),
        ),
        "member_with_no_memberships": deny(
            "no_grant",
            why=(
                "membership-only is not unauthenticated — some membership or "
                "grant on the unit is still required"
            ),
        ),
        "resource_grant_only": deny(
            "resource_grant_lacks_membership",
            why=(
                "the decision's §4 negative, made real: `require_membership=True` "
                "on `_authorize_aggregate_read`'s call means `evaluate`'s Path 2 "
                "(`if require_membership: return ...lacks_membership`) refuses a "
                "bare explicit grant even though `required_roles` is empty — the "
                "distinct reason code is what tells this population apart from a "
                "role-gated operation's `resource_grant_lacks_required_role` in "
                "the audit trail. This is the cell that used to permit under the "
                "S-007 hypothesis and is the one this task's negative coverage "
                "exists to flip: `resource_grant` alone reads aggregates? No — "
                "role required (decision record §1)."
            ),
        ),
        "admin_with_explicit_deny": deny(
            "explicit_resource_deny",
            why="checked before either grant path runs, regardless of required_roles",
        ),
        "expired_coordinator_at_owning_unit": deny(
            "no_grant",
            why="`is_active_at` is applied before the role filter is ever reached",
        ),
        "suspended_admin": deny(
            "principal_suspended",
            why="the first check in `evaluate`, ahead of required_roles being empty or not",
        ),
        "cross_tenant_coordinator": deny(
            "tenant_mismatch",
            why="tenant isolation is structural and precedes every grant question",
        ),
        "job_actor_without_role": deny(
            "no_grant",
            why=(
                "a metric read has no actor path — the shape degenerates to a "
                "role-less member, and a role-less member still needs a "
                "membership or grant on the unit even when no role is required"
            ),
        ),
        "job_actor_with_explicit_deny": deny(
            "explicit_resource_deny",
            why="the actor half of the shape is inert here; the deny on the unit beats inheritance",
        ),
    },
    "metrics.drill_down": {
        "admin_at_org_root": permit(
            why="an admin grant at the root covers every unit; admin is a drill-down role",
        ),
        "coordinator_at_owning_unit": permit(
            why="containment is inclusive, and coordinator is a drill-down role",
        ),
        "coordinator_at_sibling_unit": deny(
            "no_grant",
            why="unit scoping is a path question, not a role question — see metrics.read",
        ),
        "admin_at_sibling_unit": deny(
            "no_grant",
            why=(
                "the split that keeps §4's tenant-wide rule where §4 put it. "
                "The same principal reads this unit's *aggregates* one row "
                "above, and is refused its rows here: §4's scope bullet says "
                "'unrestricted within tenant **for aggregates**; drill-down per "
                "row above', and the row above is a role rule "
                "(`admin`/`coordinator`) that says nothing about widening "
                "scope. `row_data` is §3's **High** sensitivity — the full "
                "imported row payload, contact fields included (P9 Gate B) — "
                "so under deny-by-default the narrower reading is the only one "
                "available: `_authorize_drill_down_read` passes no "
                "`tenant_wide_roles` and ordinary containment refuses."
            ),
        ),
        "student_at_owning_unit": deny(
            "no_grant",
            why=(
                "the split from metrics.read: row-level drill-down carries "
                "`row_data` — the full imported row payload, which may include "
                "contact fields (P9 Gate B) — so the decision's §4 restricts it "
                "to `admin`/`coordinator` (`_DRILL_DOWN_ROLES`) and a student "
                "membership, however active and however well it covers the unit, "
                "is refused for holding the wrong role"
            ),
        ),
        "volunteer_at_owning_unit": deny(
            "no_grant",
            why=(
                "`volunteer` is not in this operation's role set, and the "
                "membership is active at exactly the owning unit — so the "
                "role is the only thing left that can refuse it"
            ),
        ),
        "member_with_no_memberships": deny("no_grant"),
        "resource_grant_only": deny(
            "resource_grant_lacks_required_role",
            why=(
                "role-gated like every other row-scoped operation above: "
                "`required_roles` is non-empty, so `evaluate`'s Path 2 refuses "
                "the bare grant on that check before `require_membership` is "
                "ever consulted — the same reason code `import.create` and the "
                "four job operations answer for this shape"
            ),
        ),
        "admin_with_explicit_deny": deny("explicit_resource_deny"),
        "expired_coordinator_at_owning_unit": deny("no_grant"),
        "suspended_admin": deny("principal_suspended"),
        "cross_tenant_coordinator": deny("tenant_mismatch"),
        "job_actor_without_role": deny("no_grant"),
        "job_actor_with_explicit_deny": deny("explicit_resource_deny"),
    },
    # `events.read` and `events.tag_quarantine.read` share one authorizer and
    # therefore share every outcome, which is why the two rows below are
    # identical cell for cell. That is not duplication to be factored out: the
    # rectangle is the artifact a reviewer reads, and two operations that
    # happen to agree today must each state their own answer so that the day
    # one of them diverges the diff shows which one.
    "calendar.invite.download": {
        "admin_at_org_root": permit(
            why="an admin grant at the root covers every unit beneath it",
        ),
        "coordinator_at_owning_unit": permit(
            why="containment is inclusive, so a path covers itself",
        ),
        "coordinator_at_sibling_unit": deny(
            "no_grant",
            why=(
                "an event names the unit that hosts it "
                "(`event.host_org_unit_id`), and a sibling department's "
                "coordinator does not cover it — the same scoping "
                "`events.read` applies to the catalog these ids come from"
            ),
        ),
        "admin_at_sibling_unit": deny(
            "no_grant",
            why=(
                "admin is a required role here and the membership is active, "
                "so the only thing refusing this principal is the path. No "
                "committed artifact makes a calendar artifact tenant-wide, so "
                "`_authorize_invite_read` passes no `tenant_wide_roles`"
            ),
        ),
        "student_at_owning_unit": permit(
            why=(
                "the one cell where this operation is deliberately wider than "
                "`events.read` below. The catalog is refused to a student "
                "because it carries extraction provenance and source "
                "references; an invite carries a title, a description and two "
                "instants for a single event, which is the artifact the "
                "student portal exists to hand over. The permit is not the "
                "whole rule: the handler then requires an `attendance_record` "
                "naming this student and this event, and answers 404 without "
                "one. That gate is a fact about a row rather than about a "
                "principal, so `evaluate` cannot express it and "
                "`tests/contract/test_calendar_ics.py` asserts it instead"
            ),
        ),
        "volunteer_at_owning_unit": deny(
            "no_grant",
            why=(
                "`volunteer` is not in this operation's role set, and the "
                "membership is active at exactly the owning unit — so the "
                "role is the only thing left that can refuse it"
            ),
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
                "downloading an invite has no actor path — the shape "
                "degenerates to a role-less member, which is correct: this "
                "operation is not reachable through job submission at all"
            ),
        ),
        "job_actor_with_explicit_deny": deny(
            "explicit_resource_deny",
            why=(
                "the actor half of the shape is inert here for the reason "
                "above; what is left is a deny on the unit, which beats "
                "inheritance"
            ),
        ),
    },
    "events.read": {
        "admin_at_org_root": permit(
            why="an admin grant at the root covers every unit beneath it",
        ),
        "coordinator_at_owning_unit": permit(
            why="containment is inclusive, so a path covers itself",
        ),
        "coordinator_at_sibling_unit": deny(
            "no_grant",
            why=(
                "unit scoping works here as it does for import.create: an "
                "event names the unit that hosts it (`event.host_org_unit_id`, "
                "which is also ADR-0012's identity-key host component), and a "
                "sibling department's coordinator does not cover it"
            ),
        ),
        "admin_at_sibling_unit": deny(
            "no_grant",
            why=(
                "admin is a required role here and the membership is active, so "
                "the only thing refusing this principal is the path. Compare "
                "`metrics.read` immediately above, which permits this shape: "
                "that is the ratified metrics decision's §4 aggregate rule and "
                "nothing else. No committed artifact makes an event catalog "
                "tenant-wide, so `_authorize_event_read` passes no "
                "`tenant_wide_roles` and ordinary containment refuses."
            ),
        ),
        "student_at_owning_unit": deny(
            "no_grant",
            why=(
                "reading a unit's event catalog is role-gated, not "
                "membership-gated. The catalog carries extraction provenance "
                "and source references, which is coordinator-and-above "
                "material rather than something every active membership sees"
            ),
        ),
        "volunteer_at_owning_unit": deny(
            "no_grant",
            why=(
                "`volunteer` is not in this operation's role set, and the "
                "membership is active at exactly the owning unit — so the "
                "role is the only thing left that can refuse it"
            ),
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
                "an event read has no actor path — the shape degenerates to a "
                "role-less member, and that is correct: this operation is not "
                "reachable through job submission at all"
            ),
        ),
        "job_actor_with_explicit_deny": deny(
            "explicit_resource_deny",
            why=(
                "the actor half of the shape is inert here for the reason above; "
                "what is left is a deny on the unit, which beats inheritance"
            ),
        ),
    },
    "events.tag_quarantine.read": {
        "admin_at_org_root": permit(
            why="an admin grant at the root covers every unit beneath it",
        ),
        "coordinator_at_owning_unit": permit(
            why="containment is inclusive, so a path covers itself",
        ),
        "coordinator_at_sibling_unit": deny(
            "no_grant",
            why=(
                "`discovery_review_item.owning_unit_id` is what this queue is "
                "scoped by, and a sibling department's coordinator does not "
                "cover it — the same path question as the row above"
            ),
        ),
        "admin_at_sibling_unit": deny(
            "no_grant",
            why=(
                "the role is right and the department is not. If anything this "
                "is the harder of the two to widen: the queue carries "
                "`raw_value`, unnormalized source text a human has not yet "
                "vetted, so under deny-by-default it keeps ordinary "
                "containment for the same reason `metrics.drill_down` does"
            ),
        ),
        "student_at_owning_unit": deny(
            "no_grant",
            why=(
                "reviewing quarantined tag values is role-gated: the queue "
                "exists so a coordinator decides what a term means, and an "
                "active membership carrying another role is not that person"
            ),
        ),
        "volunteer_at_owning_unit": deny(
            "no_grant",
            why=(
                "`volunteer` is not in this operation's role set, and the "
                "membership is active at exactly the owning unit — so the "
                "role is the only thing left that can refuse it"
            ),
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
                "a review-queue read has no actor path — the shape degenerates "
                "to a role-less member, and this operation is not reachable "
                "through job submission at all"
            ),
        ),
        "job_actor_with_explicit_deny": deny(
            "explicit_resource_deny",
            why=(
                "the actor half of the shape is inert here for the reason above; "
                "what is left is a deny on the unit, which beats inheritance"
            ),
        ),
    },
    # `match_run.create` and `match_run.read` share one authorizer, so — like
    # the two event rows above — they agree cell for cell today and each still
    # states its own answer, so the day one diverges the diff shows which.
    # The two student surfaces, and the two columns worth reading first are
    # `admin_at_org_root` and `coordinator_at_owning_unit`: both **deny**. These
    # are the only operations in this file an admin at the tenant root cannot
    # perform, and that is the role set doing exactly what it says rather than an
    # omission — see the `Operation` rows for why `{student}` is the whole of it.
    # An admin who wants these events reads `events.read`, which shows them more.
    "student_event.browse": {
        "admin_at_org_root": deny(
            "no_grant",
            why=(
                "`admin` is not in this operation's role set. The root grant "
                "covers the unit, so path containment is satisfied and the role "
                "is the only thing refusing — which is the shape a widening of "
                "`_STUDENT_EVENT_ROLES` would flip, and is therefore worth "
                "having a cell for. An admin is not shut out of the data: "
                "`events.read` serves the same rows with the review status and "
                "provenance this surface drops."
            ),
        ),
        "coordinator_at_owning_unit": deny(
            "no_grant",
            why=(
                "same reason as the admin above, at the unit that owns the "
                "resource: containment is inclusive and satisfied, and "
                "`coordinator` is simply not the role §15 names"
            ),
        ),
        "coordinator_at_sibling_unit": deny(
            "no_grant",
            why=(
                "refused twice over — wrong role and, independently, a sibling "
                "department does not contain the owning unit. The role check is "
                "what `evaluate` reaches first, so `no_grant` is the code either "
                "way"
            ),
        ),
        "admin_at_sibling_unit": deny(
            "no_grant",
            why=(
                "the column this file keeps to make `tenant_wide_roles` visible. "
                "`_authorize_student_event_read` passes none — the metrics "
                "decision's §4 is the only artifact making anything tenant-wide "
                "and it says so of aggregate reads — and the role is wrong here "
                "besides"
            ),
        ),
        "student_at_owning_unit": permit(
            why=(
                "customer §15: the Student browses the events their unit has "
                "published. Containment is inclusive, so a membership at exactly "
                "the owning unit covers it. This is the permit the whole card "
                "rests on, and it is narrower than it looks — the response "
                "carries published events only, and the .ics link on each item "
                "appears only where the student is recorded at the event, which "
                "is a fact about a row that `evaluate` cannot express (see "
                "`tests/contract/test_student_events_api.py`)"
            ),
        ),
        "volunteer_at_owning_unit": deny(
            "no_grant",
            why=(
                "`volunteer` is the Event Host (customer §4), who files Speaker "
                "Requests. §15 is about the Student, and an active membership at "
                "exactly the owning unit leaves the role as the only thing that "
                "can refuse it"
            ),
        ),
        "member_with_no_memberships": deny("no_grant"),
        "resource_grant_only": deny(
            "resource_grant_lacks_required_role",
            why="S-007. A grant conveys reach, not authority. See the module docstring.",
        ),
        "admin_with_explicit_deny": deny(
            "explicit_resource_deny",
            why=(
                "v1.1 §2.1: an explicit deny on the resource beats inheritance. "
                "Note this principal would have been denied anyway for the role — "
                "the cell asserts the *code*, and the deny is what wins, which is "
                "how a precedence regression stays visible even on a row whose "
                "role set would refuse the principal regardless"
            ),
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
                "browsing events has no actor path — the shape degenerates to a "
                "role-less member, which is correct: this operation is not "
                "reachable through job submission at all"
            ),
        ),
        "job_actor_with_explicit_deny": deny(
            "explicit_resource_deny",
            why=(
                "the actor half of the shape is inert here for the reason above; "
                "what is left is a deny on the unit, which beats inheritance"
            ),
        ),
    },
    # Identical to the row above, cell for cell, and deliberately written out
    # rather than aliased: the two routes share one authorizer *today* because
    # they ask one question, and a copy is what makes the day they stop agreeing
    # a visible diff on this file rather than a silent consequence of an alias.
    #
    # The agenda's extra narrowing — to the caller's own `attendance_record` — is
    # not in this rectangle at all. It is a `subject_id` predicate in the query,
    # which is a self-scope the policy engine has no concept of, and it is
    # asserted over HTTP in `tests/contract/test_student_events_api.py`.
    "student_agenda.list": {
        "admin_at_org_root": deny(
            "no_grant",
            why="`admin` is not in this operation's role set; see `student_event.browse`",
        ),
        "coordinator_at_owning_unit": deny(
            "no_grant",
            why=(
                "`coordinator` is not the role §15 names, and an agenda is one "
                "student's own list — a coordinator who needs to know who "
                "attended reads `engagement.attendance_summary.read`, which is "
                "an aggregate carrying no subject ids at all"
            ),
        ),
        "coordinator_at_sibling_unit": deny(
            "no_grant",
            why="wrong role, and a sibling department does not contain the owning unit",
        ),
        "admin_at_sibling_unit": deny(
            "no_grant",
            why=(
                "no `tenant_wide_roles` is passed, and the role is wrong besides "
                "— see `student_event.browse`"
            ),
        ),
        "student_at_owning_unit": permit(
            why=(
                "customer §15. The permit is to the *route*; which rows come "
                "back is decided by `attendance_record.subject_id = "
                "principal.user_id` in the query, so a student admitted here "
                "still sees only their own events and there is no request field "
                "that could name somebody else's (MM-A01)"
            ),
        ),
        "volunteer_at_owning_unit": deny(
            "no_grant",
            why="`volunteer` is the Event Host; the role is the only thing left to refuse it",
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
                "reading an agenda has no actor path — the shape degenerates to a role-less member"
            ),
        ),
        "job_actor_with_explicit_deny": deny(
            "explicit_resource_deny",
            why=(
                "the actor half of the shape is inert here; what is left is a "
                "deny on the unit, which beats inheritance"
            ),
        ),
    },
    "match_run.create": {
        "admin_at_org_root": permit(
            why="an admin grant at the root covers every unit beneath it",
        ),
        "coordinator_at_owning_unit": permit(
            why=(
                "containment is inclusive, and this is the shape the ratified "
                "program direction is written for: the coordinator who runs "
                "the unit asks for its shortlist and batch-invites from it"
            ),
        ),
        "coordinator_at_sibling_unit": deny(
            "no_grant",
            why=(
                "unit scoping works here as it does for import.create: the run "
                "is filed under `job.owning_unit_id`, taken from the loaded "
                "unit rather than the body, and a sibling department's "
                "coordinator does not cover it"
            ),
        ),
        "admin_at_sibling_unit": deny(
            "no_grant",
            why=(
                "the role is required and the membership is active, so the "
                "only thing refusing this principal is the path. No committed "
                "artifact makes match runs tenant-wide the way the metrics "
                "decision's §4 makes aggregates tenant-wide, so "
                "`_authorize_match_run` passes no `tenant_wide_roles` and "
                "ordinary containment refuses"
            ),
        ),
        "student_at_owning_unit": deny(
            "no_grant",
            why=(
                "submitting a run is role-gated, not membership-gated: it "
                "queues durable work and its body carries every candidate "
                "professional's expertise evidence"
            ),
        ),
        "volunteer_at_owning_unit": deny(
            "no_grant",
            why=(
                "`volunteer` is not in this operation's role set, and the "
                "membership is active at exactly the owning unit — so the "
                "role is the only thing left that can refuse it"
            ),
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
                "there is no job yet when this operation is authorized — it is "
                "the request that creates one — so the actor half of the shape "
                "is inert and what remains is a role-less member"
            ),
        ),
        "job_actor_with_explicit_deny": deny(
            "explicit_resource_deny",
            why=(
                "the actor half is inert here for the reason above; what is "
                "left is a deny on the unit, which beats inheritance"
            ),
        ),
    },
    "outreach.draft.create": {
        "admin_at_org_root": permit(
            why="an admin grant at the root covers every unit beneath it",
        ),
        "coordinator_at_owning_unit": permit(
            why=(
                "composing is the coordinator's own job: they are the named actor recorded as the "
                "draft's author, and as its approver when they approve it in the same call"
            ),
        ),
        "coordinator_at_sibling_unit": deny(
            "no_grant",
            why=(
                "outreach is scoped by the loaded unit's own path, never by "
                "anything in the request, so a sibling department's coordinator "
                "does not cover it — the same containment rule import.create and "
                "match_run.create are held to"
            ),
        ),
        "admin_at_sibling_unit": deny(
            "no_grant",
            why=(
                "the role is required and the membership is active, so the only "
                "thing refusing this principal is the path. No committed artifact "
                "makes outreach tenant-wide the way the metrics decision's §4 "
                "makes aggregates tenant-wide, so `_authorize_outreach` passes no "
                "`tenant_wide_roles` and ordinary containment refuses"
            ),
        ),
        "student_at_owning_unit": deny(
            "no_grant",
            why=(
                "outreach is correspondence sent on the institution's behalf. "
                "The roles that may touch it are the roles accountable for what "
                "it says, and a student membership is not one of them — this is "
                "the one operation family where the wrong answer reaches a real "
                "person outside the institution"
            ),
        ),
        "volunteer_at_owning_unit": deny(
            "no_grant",
            why=(
                "`volunteer` is not in this operation's role set, and the "
                "membership is active at exactly the owning unit — so the "
                "role is the only thing left that can refuse it"
            ),
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
                "there is no job at all in this operation — composing writes a row directly and "
                "queues nothing — so the actor half of the shape is inert and what remains is a "
                "role-less member"
            ),
        ),
        "job_actor_with_explicit_deny": deny(
            "explicit_resource_deny",
            why=(
                "the actor half is inert here for the reason above; what is left "
                "is a deny on the unit, which beats inheritance"
            ),
        ),
    },
    "outreach.draft.list": {
        "admin_at_org_root": permit(
            why="an admin grant at the root covers every unit beneath it",
        ),
        "coordinator_at_owning_unit": permit(
            why=(
                "a coordinator reading their own unit's drafts, which carry the rendered text and "
                "the recipient's address"
            ),
        ),
        "coordinator_at_sibling_unit": deny(
            "no_grant",
            why=(
                "outreach is scoped by the loaded unit's own path, never by "
                "anything in the request, so a sibling department's coordinator "
                "does not cover it — the same containment rule import.create and "
                "match_run.create are held to"
            ),
        ),
        "admin_at_sibling_unit": deny(
            "no_grant",
            why=(
                "the role is required and the membership is active, so the only "
                "thing refusing this principal is the path. No committed artifact "
                "makes outreach tenant-wide the way the metrics decision's §4 "
                "makes aggregates tenant-wide, so `_authorize_outreach` passes no "
                "`tenant_wide_roles` and ordinary containment refuses"
            ),
        ),
        "student_at_owning_unit": deny(
            "no_grant",
            why=(
                "outreach is correspondence sent on the institution's behalf. "
                "The roles that may touch it are the roles accountable for what "
                "it says, and a student membership is not one of them — this is "
                "the one operation family where the wrong answer reaches a real "
                "person outside the institution"
            ),
        ),
        "volunteer_at_owning_unit": deny(
            "no_grant",
            why=(
                "`volunteer` is not in this operation's role set, and the "
                "membership is active at exactly the owning unit — so the "
                "role is the only thing left that can refuse it"
            ),
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
                "this is a read of stored drafts and creates no job, so the "
                "actor half of the shape is inert and what remains is a "
                "role-less member"
            ),
        ),
        "job_actor_with_explicit_deny": deny(
            "explicit_resource_deny",
            why=(
                "the actor half is inert here for the reason above; what is left "
                "is a deny on the unit, which beats inheritance"
            ),
        ),
    },
    "outreach.send.submit": {
        "admin_at_org_root": permit(
            why="an admin grant at the root covers every unit beneath it",
        ),
        "coordinator_at_owning_unit": permit(
            why=(
                "the coordinator who composed and approved the message is the one who sends it. "
                "This is the only operation in this family that can cause a message to leave the "
                "building, so its cell is the one worth reading twice"
            ),
        ),
        "coordinator_at_sibling_unit": deny(
            "no_grant",
            why=(
                "outreach is scoped by the loaded unit's own path, never by "
                "anything in the request, so a sibling department's coordinator "
                "does not cover it — the same containment rule import.create and "
                "match_run.create are held to"
            ),
        ),
        "admin_at_sibling_unit": deny(
            "no_grant",
            why=(
                "the role is required and the membership is active, so the only "
                "thing refusing this principal is the path. No committed artifact "
                "makes outreach tenant-wide the way the metrics decision's §4 "
                "makes aggregates tenant-wide, so `_authorize_outreach` passes no "
                "`tenant_wide_roles` and ordinary containment refuses"
            ),
        ),
        "student_at_owning_unit": deny(
            "no_grant",
            why=(
                "outreach is correspondence sent on the institution's behalf. "
                "The roles that may touch it are the roles accountable for what "
                "it says, and a student membership is not one of them — this is "
                "the one operation family where the wrong answer reaches a real "
                "person outside the institution"
            ),
        ),
        "volunteer_at_owning_unit": deny(
            "no_grant",
            why=(
                "`volunteer` is not in this operation's role set, and the "
                "membership is active at exactly the owning unit — so the "
                "role is the only thing left that can refuse it"
            ),
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
                "there is no job yet when this operation is authorized — it is the request that "
                "creates one — so the actor half of the shape is inert and what remains is a role- "
                "less member"
            ),
        ),
        "job_actor_with_explicit_deny": deny(
            "explicit_resource_deny",
            why=(
                "the actor half is inert here for the reason above; what is left "
                "is a deny on the unit, which beats inheritance"
            ),
        ),
    },
    "outreach.send.read": {
        "admin_at_org_root": permit(
            why="an admin grant at the root covers every unit beneath it",
        ),
        "coordinator_at_owning_unit": permit(
            why=(
                "reading what happened to a message their unit sent, including the recipient's "
                "address and any refusal reason"
            ),
        ),
        "coordinator_at_sibling_unit": deny(
            "no_grant",
            why=(
                "outreach is scoped by the loaded unit's own path, never by "
                "anything in the request, so a sibling department's coordinator "
                "does not cover it — the same containment rule import.create and "
                "match_run.create are held to"
            ),
        ),
        "admin_at_sibling_unit": deny(
            "no_grant",
            why=(
                "the role is required and the membership is active, so the only "
                "thing refusing this principal is the path. No committed artifact "
                "makes outreach tenant-wide the way the metrics decision's §4 "
                "makes aggregates tenant-wide, so `_authorize_outreach` passes no "
                "`tenant_wide_roles` and ordinary containment refuses"
            ),
        ),
        "student_at_owning_unit": deny(
            "no_grant",
            why=(
                "outreach is correspondence sent on the institution's behalf. "
                "The roles that may touch it are the roles accountable for what "
                "it says, and a student membership is not one of them — this is "
                "the one operation family where the wrong answer reaches a real "
                "person outside the institution"
            ),
        ),
        "volunteer_at_owning_unit": deny(
            "no_grant",
            why=(
                "`volunteer` is not in this operation's role set, and the "
                "membership is active at exactly the owning unit — so the "
                "role is the only thing left that can refuse it"
            ),
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
                "the send's job exists by now, but this operation authorizes against the unit "
                "rather than against the job, so the actor half of the shape is inert and what "
                "remains is a role-less member"
            ),
        ),
        "job_actor_with_explicit_deny": deny(
            "explicit_resource_deny",
            why=(
                "the actor half is inert here for the reason above; what is left "
                "is a deny on the unit, which beats inheritance"
            ),
        ),
    },
    "match_run.read": {
        "admin_at_org_root": permit(
            why="an admin grant at the root covers every unit beneath it",
        ),
        "coordinator_at_owning_unit": permit(
            why="containment is inclusive, so a path covers itself",
        ),
        "coordinator_at_sibling_unit": deny(
            "no_grant",
            why=(
                "`match_run.owning_unit_id` is what a run is scoped by — "
                "written by the worker from the job row, never from a payload "
                "— and a sibling department's coordinator does not cover it. "
                "The route additionally requires the run to belong to the unit "
                "in the path, so an authorized caller cannot reach another "
                "unit's run through their own"
            ),
        ),
        "admin_at_sibling_unit": deny(
            "no_grant",
            why="the role is right and the department is not; see the row above",
        ),
        "student_at_owning_unit": deny(
            "no_grant",
            why=(
                "reading a run is role-gated: it returns per-factor "
                "explanations naming which candidates had no evidence on file, "
                "which is a statement about individual professionals' records"
            ),
        ),
        "volunteer_at_owning_unit": deny(
            "no_grant",
            why=(
                "`volunteer` is not in this operation's role set, and the "
                "membership is active at exactly the owning unit — so the "
                "role is the only thing left that can refuse it"
            ),
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
                "a match-run read authorizes against the unit, not against the "
                "job that produced the run, so submitting that job conveys "
                "nothing here — the shape degenerates to a role-less member"
            ),
        ),
        "job_actor_with_explicit_deny": deny(
            "explicit_resource_deny",
            why=(
                "the actor half of the shape is inert here for the reason "
                "above; what is left is a deny on the unit"
            ),
        ),
    },
    # The three student rewards operations share `_authorize_student_rewards`,
    # so — like the event and match-run pairs above — they agree cell for cell
    # today and each still states its own answer, so the day one diverges the
    # diff shows which.
    #
    # These are the first rows in this file where `student_at_owning_unit`
    # *permits* and `coordinator_at_owning_unit` denies. That inversion is the
    # whole point of the operations: the person whose points are at stake is the
    # person the surface is for. Everything else about the row is unchanged —
    # tenant isolation, suspension, the explicit deny, the validity window and
    # subtree containment all refuse exactly as they do everywhere else, which is
    # what shows the permit is a role decision and not a hole.
    "rewards.catalog.read": {
        "admin_at_org_root": deny(
            "no_grant",
            why=(
                "`_REWARDS_STUDENT_ROLES` is `{student}` and an admin does not "
                "hold it. Being an administrator is not being the student whose "
                "balance this is: the response is one caller's own folded ledger "
                "and the catalog measured against it. An admin reading another "
                "person's standing is a different operation, gated on the "
                "read-role decision D6 §5 still leaves open"
            ),
        ),
        "coordinator_at_owning_unit": deny(
            "no_grant",
            why=(
                "the wrong-role cell for this operation — an active membership at "
                "exactly the owning unit, refused for its role and nothing else. "
                "A coordinator administers the catalog; they do not browse it as "
                "a student, and this route would answer with the coordinator's "
                "own balance if they did"
            ),
        ),
        "coordinator_at_sibling_unit": deny(
            "no_grant",
            why=(
                "wrong role and wrong department; either alone refuses. Unit "
                "scoping applies here as it does everywhere else, even though "
                "`reward_item` is tenant-scoped: the unit in the path is the "
                "authorization scope, which is exactly what this cell measures"
            ),
        ),
        "admin_at_sibling_unit": deny(
            "no_grant",
            why=(
                "no committed artifact makes a rewards read tenant-wide the way "
                "the metrics decision's §4 makes aggregates tenant-wide, so "
                "`_authorize_student_rewards` passes no `tenant_wide_roles` — and "
                "the role is wrong here in any case"
            ),
        ),
        "student_at_owning_unit": permit(
            why=(
                "the shape this operation exists for. Containment is inclusive, "
                "so the membership's own path covers the unit, and `student` is "
                "the required role"
            ),
        ),
        "volunteer_at_owning_unit": deny(
            "no_grant",
            why=(
                "`volunteer` is not in this operation's role set, and the "
                "membership is active at exactly the owning unit — so the "
                "role is the only thing left that can refuse it"
            ),
        ),
        "member_with_no_memberships": deny("no_grant"),
        "resource_grant_only": deny(
            "resource_grant_lacks_required_role",
            why="S-007. A grant conveys reach, not authority. See the module docstring.",
        ),
        "admin_with_explicit_deny": deny(
            "explicit_resource_deny",
            why=(
                "v1.1 §2.1: an explicit deny on the resource beats inheritance, "
                "and it is evaluated *before* the required-role check — so this "
                "principal is refused for the deny rather than for holding no "
                "`student` role. Worth stating rather than assuming: the "
                "precedence is what makes a carved-out deny binding on a surface "
                "the principal was never going to reach on role grounds either, "
                "which is the case an admin at the org root (one cell up, refused "
                "with `no_grant`) shows by contrast"
            ),
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
                "a rewards read authorizes against the unit and has no job in it "
                "at all, so the actor half of the shape is inert and what remains "
                "is a role-less member"
            ),
        ),
        "job_actor_with_explicit_deny": deny(
            "explicit_resource_deny",
            why=(
                "the actor half is inert here for the reason above; unlike "
                "`admin_with_explicit_deny` this principal holds no membership, "
                "so the grant path is where it is refused and the deny on the "
                "unit is what answers"
            ),
        ),
    },
    "redemption.create": {
        "admin_at_org_root": deny(
            "no_grant",
            why=(
                "a redemption is opened *for the caller* — `subject_id` is "
                "`principal.user_id` and there is no field that could name "
                "anyone else — so an admin reaching this route could only spend "
                "their own points. Role-gated to the students it is for"
            ),
        ),
        "coordinator_at_owning_unit": deny(
            "no_grant",
            why="the wrong-role cell: a coordinator decides redemptions, they do not open them",
        ),
        "coordinator_at_sibling_unit": deny("no_grant", why="wrong role and wrong department"),
        "admin_at_sibling_unit": deny(
            "no_grant",
            why="wrong role, wrong department, and no tenant-wide reach is passed",
        ),
        "student_at_owning_unit": permit(
            why="the shape this operation exists for; containment is inclusive",
        ),
        "volunteer_at_owning_unit": deny(
            "no_grant",
            why=(
                "`volunteer` is not in this operation's role set, and the "
                "membership is active at exactly the owning unit — so the "
                "role is the only thing left that can refuse it"
            ),
        ),
        "member_with_no_memberships": deny("no_grant"),
        "resource_grant_only": deny(
            "resource_grant_lacks_required_role",
            why="S-007. A grant conveys reach, not authority.",
        ),
        "admin_with_explicit_deny": deny(
            "explicit_resource_deny",
            why="the deny is evaluated ahead of the role check; see `rewards.catalog.read`",
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
            why="there is no job on this path; the shape degenerates to a role-less member",
        ),
        "job_actor_with_explicit_deny": deny(
            "explicit_resource_deny",
            why="the actor half is inert; what is left is a deny on the unit",
        ),
    },
    "redemption.read": {
        "admin_at_org_root": deny(
            "no_grant",
            why=(
                "this route returns the *caller's own* tickets, scoped to "
                "`principal.user_id` in the query. An admin admitted here would "
                "see their own and nobody else's, so admitting them would buy "
                "nothing and would widen a surface a coordinator queue should "
                "later occupy deliberately"
            ),
        ),
        "coordinator_at_owning_unit": deny(
            "no_grant",
            why="the wrong-role cell; see `redemption.decide` for what a coordinator may do",
        ),
        "coordinator_at_sibling_unit": deny("no_grant", why="wrong role and wrong department"),
        "admin_at_sibling_unit": deny(
            "no_grant",
            why="wrong role, wrong department, and no tenant-wide reach is passed",
        ),
        "student_at_owning_unit": permit(
            why="the shape this operation exists for; containment is inclusive",
        ),
        "volunteer_at_owning_unit": deny(
            "no_grant",
            why=(
                "`volunteer` is not in this operation's role set, and the "
                "membership is active at exactly the owning unit — so the "
                "role is the only thing left that can refuse it"
            ),
        ),
        "member_with_no_memberships": deny("no_grant"),
        "resource_grant_only": deny(
            "resource_grant_lacks_required_role",
            why="S-007. A grant conveys reach, not authority.",
        ),
        "admin_with_explicit_deny": deny(
            "explicit_resource_deny",
            why="the deny is evaluated ahead of the role check; see `rewards.catalog.read`",
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
            why="there is no job on this path; the shape degenerates to a role-less member",
        ),
        "job_actor_with_explicit_deny": deny(
            "explicit_resource_deny",
            why="the actor half is inert; what is left is a deny on the unit",
        ),
    },
    # The coordinator half, authorized by `_authorize_redemption_decision` and
    # therefore shaped like every other `{admin, coordinator}` row in this file —
    # which is the point of it being a separate authorizer: the student rows
    # above and this one cannot be widened together by one edit.
    "redemption.decide": {
        "admin_at_org_root": permit(
            why="an admin grant at the root covers every unit beneath it",
        ),
        "coordinator_at_owning_unit": permit(
            why=(
                "containment is inclusive, and this is the shape the decision is "
                "written for: the coordinator who administers the unit's rewards "
                "program approves, denies, or hands the reward over"
            ),
        ),
        "coordinator_at_sibling_unit": deny(
            "no_grant",
            why=(
                "fulfilment debits a student's ledger, so it is scoped like every "
                "other consequential write: a sibling department's coordinator "
                "does not cover this unit"
            ),
        ),
        "admin_at_sibling_unit": deny(
            "no_grant",
            why="the role is right and the department is not; no tenant-wide reach is passed",
        ),
        "student_at_owning_unit": deny(
            "no_grant",
            why=(
                "the wrong-role cell for this operation, and the one that matters "
                "most on this surface: a student approving their own redemption "
                "would delete ADR-0013's approval step, and fulfilling it would "
                "let them hand themselves the reward and take the debit"
            ),
        ),
        "volunteer_at_owning_unit": deny(
            "no_grant",
            why=(
                "`volunteer` is not in this operation's role set, and the "
                "membership is active at exactly the owning unit — so the "
                "role is the only thing left that can refuse it"
            ),
        ),
        "member_with_no_memberships": deny("no_grant"),
        "resource_grant_only": deny(
            "resource_grant_lacks_required_role",
            why="S-007. A grant conveys reach, not authority.",
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
            why="there is no job on this path; the shape degenerates to a role-less member",
        ),
        "job_actor_with_explicit_deny": deny(
            "explicit_resource_deny",
            why="the actor half is inert; what is left is a deny on the unit",
        ),
    },
    # Both S12 funnel operations run the same authorizer over the same resource,
    # so their rectangles are identical by construction rather than by
    # coincidence. They are still written out twice: `_missing_rows` keys on the
    # operation, and a shared dict object would make widening one of them widen
    # the other silently — which is the failure mode this whole file exists to
    # make impossible.
    "pipeline.record.read": {
        "admin_at_org_root": permit(
            why="an admin grant at the root covers every unit beneath it",
        ),
        "coordinator_at_owning_unit": permit(
            why="containment is inclusive; this is the coordinator whose unit owns the journey",
        ),
        "coordinator_at_sibling_unit": deny(
            "no_grant",
            why=(
                "a pipeline record is one named student's engagement record. A "
                "sibling department's coordinator has no business reading it, and "
                "the route turns this refusal into a 404 rather than a 403 so the "
                "id is not confirmed to name anything"
            ),
        ),
        "admin_at_sibling_unit": deny(
            "no_grant",
            why="the role is right and the department is not; no tenant-wide reach is passed",
        ),
        "student_at_owning_unit": deny(
            "no_grant",
            why=(
                "the wrong-role cell. There is no self-read shape here: unlike "
                "`redemption.list.own`, this route takes a record id rather than "
                "scoping to the caller, so admitting students would admit reading "
                "other students' journeys"
            ),
        ),
        "volunteer_at_owning_unit": deny(
            "no_grant",
            why=(
                "`volunteer` is not in this operation's role set, and the "
                "membership is active at exactly the owning unit — so the "
                "refusal is the role alone. A volunteer neither reads nor moves "
                "another student's funnel record"
            ),
        ),
        "member_with_no_memberships": deny("no_grant"),
        "resource_grant_only": deny(
            "resource_grant_lacks_required_role",
            why="S-007. A grant conveys reach, not authority.",
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
            why="there is no job on this path; the shape degenerates to a role-less member",
        ),
        "job_actor_with_explicit_deny": deny(
            "explicit_resource_deny",
            why="the actor half is inert; what is left is a deny on the unit",
        ),
    },
    "pipeline.stage.advance": {
        "admin_at_org_root": permit(
            why="an admin grant at the root covers every unit beneath it",
        ),
        "coordinator_at_owning_unit": permit(
            why=(
                "the shape this operation exists for: the coordinator who runs the "
                "program records that a journey reached Confirmed, Attended, or "
                "Member Inquiry. Nothing else in this repository can move those "
                "three stages, so this cell is the one the funnel depends on"
            ),
        ),
        "coordinator_at_sibling_unit": deny(
            "no_grant",
            why=(
                "an advance writes a number a stakeholder reads. Scoped like every "
                "other consequential write: a sibling department does not contain "
                "this unit, so its coordinator cannot move this unit's funnel"
            ),
        ),
        "admin_at_sibling_unit": deny(
            "no_grant",
            why="the role is right and the department is not; no tenant-wide reach is passed",
        ),
        "student_at_owning_unit": deny(
            "no_grant",
            why=(
                "the wrong-role cell, and the one that matters most here: a student "
                "recording their own Attended would mint the attendance claim the "
                "rewards ledger reads, and asserting their own Member Inquiry would "
                "write the program's headline conversion number"
            ),
        ),
        "volunteer_at_owning_unit": deny(
            "no_grant",
            why=(
                "`volunteer` is not in this operation's role set, and the "
                "membership is active at exactly the owning unit — so the "
                "refusal is the role alone. A volunteer neither reads nor moves "
                "another student's funnel record"
            ),
        ),
        "member_with_no_memberships": deny("no_grant"),
        "resource_grant_only": deny(
            "resource_grant_lacks_required_role",
            why="S-007. A grant conveys reach, not authority.",
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
            why="there is no job on this path; the shape degenerates to a role-less member",
        ),
        "job_actor_with_explicit_deny": deny(
            "explicit_resource_deny",
            why="the actor half is inert; what is left is a deny on the unit",
        ),
    },
    # The R2 engagement read. Shaped like `events.read` rather than like the
    # rewards rows: the surface is a coordinator's account of their own unit's
    # record-keeping, so the roles are `{admin, coordinator}` and the student
    # cell denies.
    "engagement.attendance_summary.read": {
        "admin_at_org_root": permit(
            why="an admin grant at the root covers every unit beneath it",
        ),
        "coordinator_at_owning_unit": permit(
            why=(
                "the shape this operation exists for: the coordinator "
                "accountable for whether check-in is actually being used in this "
                "unit. Containment is inclusive, so the membership's own path "
                "covers the unit"
            ),
        ),
        "coordinator_at_sibling_unit": deny(
            "no_grant",
            why=(
                "the cross-unit denial this card is measured on. An "
                "`attendance_record` carries its own `owning_unit_id` (A5, "
                "migration `0009`), so a summary is a statement about one "
                "department's evidence and a sibling department's coordinator "
                "does not cover it — exactly as `events.read` refuses the same "
                "shape"
            ),
        ),
        "admin_at_sibling_unit": deny(
            "no_grant",
            why=(
                "admin is a required role here and the membership is active, so "
                "only the path refuses this principal. This response *is* an "
                "aggregate, which makes the contrast with `metrics.read` the "
                "cell worth reading: that operation permits this shape on the "
                "ratified metrics decision's §4 and nothing else, and §4 names "
                "the metrics surface rather than every aggregate anyone later "
                "builds. `_authorize_engagement_read` therefore passes no "
                "`tenant_wide_roles` and ordinary containment refuses"
            ),
        ),
        "student_at_owning_unit": deny(
            "no_grant",
            why=(
                "the wrong-role cell. A student reading this would learn how "
                "much attendance *other people* in their unit have on file — a "
                "cohort fact, not their own standing, which "
                "`rewards.catalog.read` already gives them. D8 (disclosure "
                "consent) is the decision that would have to authorize a "
                "student view of anyone else's engagement, and it is open"
            ),
        ),
        "volunteer_at_owning_unit": deny(
            "no_grant",
            why=(
                "`volunteer` is not in this operation's role set, and the "
                "membership is active at exactly the owning unit — so the "
                "role is the only thing left that can refuse it"
            ),
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
                "an attendance summary has no job on its path, so the actor half "
                "of the shape is inert and what remains is a role-less member"
            ),
        ),
        "job_actor_with_explicit_deny": deny(
            "explicit_resource_deny",
            why="the actor half is inert; what is left is a deny on the unit",
        ),
    },
    "outreach.send.list": {
        "admin_at_org_root": permit(
            why="an admin grant at the root covers every unit beneath it",
        ),
        "coordinator_at_owning_unit": permit(
            why=(
                "a coordinator reading what their own unit has attempted to send, which carries "
                "recipient addresses and delivery outcomes"
            ),
        ),
        "coordinator_at_sibling_unit": deny(
            "no_grant",
            why=(
                "outreach is scoped by the loaded unit's own path, never by "
                "anything in the request, so a sibling department's coordinator "
                "does not cover it"
            ),
        ),
        "admin_at_sibling_unit": deny(
            "no_grant",
            why=(
                "the role is required and the membership is active, so the only "
                "thing refusing this principal is the path. No committed artifact "
                "makes outreach tenant-wide, so `_authorize_outreach` passes no "
                "`tenant_wide_roles` and ordinary containment refuses"
            ),
        ),
        "student_at_owning_unit": deny(
            "no_grant",
            why=(
                "outreach is correspondence sent on the institution's behalf, and "
                "the roles that may touch it are the roles accountable for what it "
                "says — this is the operation family where the wrong answer reaches "
                "a real person outside the institution"
            ),
        ),
        "volunteer_at_owning_unit": deny(
            "no_grant",
            why=(
                "`volunteer` is not in this operation's role set, and the "
                "membership is active at exactly the owning unit — so the "
                "role is the only thing left that can refuse it"
            ),
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
                "there is no job on this path — it writes rows directly and queues "
                "nothing — so the actor half of the shape is inert and what remains "
                "is a role-less member"
            ),
        ),
        "job_actor_with_explicit_deny": deny(
            "explicit_resource_deny",
            why=(
                "the actor half is inert here for the reason above; what is left "
                "is a deny on the unit, which beats inheritance"
            ),
        ),
    },
    "outreach.contact.list": {
        "admin_at_org_root": permit(
            why="an admin grant at the root covers every unit beneath it",
        ),
        "coordinator_at_owning_unit": permit(
            why=(
                "a coordinator reading their own unit's contacts, which carry addresses, consent "
                "sources, and whether each may be written to"
            ),
        ),
        "coordinator_at_sibling_unit": deny(
            "no_grant",
            why=(
                "outreach is scoped by the loaded unit's own path, never by "
                "anything in the request, so a sibling department's coordinator "
                "does not cover it"
            ),
        ),
        "admin_at_sibling_unit": deny(
            "no_grant",
            why=(
                "the role is required and the membership is active, so the only "
                "thing refusing this principal is the path. No committed artifact "
                "makes outreach tenant-wide, so `_authorize_outreach` passes no "
                "`tenant_wide_roles` and ordinary containment refuses"
            ),
        ),
        "student_at_owning_unit": deny(
            "no_grant",
            why=(
                "outreach is correspondence sent on the institution's behalf, and "
                "the roles that may touch it are the roles accountable for what it "
                "says — this is the operation family where the wrong answer reaches "
                "a real person outside the institution"
            ),
        ),
        "volunteer_at_owning_unit": deny(
            "no_grant",
            why=(
                "`volunteer` is not in this operation's role set, and the "
                "membership is active at exactly the owning unit — so the "
                "role is the only thing left that can refuse it"
            ),
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
                "there is no job on this path — it writes rows directly and queues "
                "nothing — so the actor half of the shape is inert and what remains "
                "is a role-less member"
            ),
        ),
        "job_actor_with_explicit_deny": deny(
            "explicit_resource_deny",
            why=(
                "the actor half is inert here for the reason above; what is left "
                "is a deny on the unit, which beats inheritance"
            ),
        ),
    },
    "outreach.contact.read": {
        "admin_at_org_root": permit(
            why="an admin grant at the root covers every unit beneath it",
        ),
        "coordinator_at_owning_unit": permit(
            why=(
                "a coordinator reading one contact and its consent history — the trail of who "
                "recorded what, which is the record their own entries appear in"
            ),
        ),
        "coordinator_at_sibling_unit": deny(
            "no_grant",
            why=(
                "outreach is scoped by the loaded unit's own path, never by "
                "anything in the request, so a sibling department's coordinator "
                "does not cover it"
            ),
        ),
        "admin_at_sibling_unit": deny(
            "no_grant",
            why=(
                "the role is required and the membership is active, so the only "
                "thing refusing this principal is the path. No committed artifact "
                "makes outreach tenant-wide, so `_authorize_outreach` passes no "
                "`tenant_wide_roles` and ordinary containment refuses"
            ),
        ),
        "student_at_owning_unit": deny(
            "no_grant",
            why=(
                "outreach is correspondence sent on the institution's behalf, and "
                "the roles that may touch it are the roles accountable for what it "
                "says — this is the operation family where the wrong answer reaches "
                "a real person outside the institution"
            ),
        ),
        "volunteer_at_owning_unit": deny(
            "no_grant",
            why=(
                "`volunteer` is not in this operation's role set, and the "
                "membership is active at exactly the owning unit — so the "
                "role is the only thing left that can refuse it"
            ),
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
                "there is no job on this path — it writes rows directly and queues "
                "nothing — so the actor half of the shape is inert and what remains "
                "is a role-less member"
            ),
        ),
        "job_actor_with_explicit_deny": deny(
            "explicit_resource_deny",
            why=(
                "the actor half is inert here for the reason above; what is left "
                "is a deny on the unit, which beats inheritance"
            ),
        ),
    },
    "outreach.contact.create": {
        "admin_at_org_root": permit(
            why="an admin grant at the root covers every unit beneath it",
        ),
        "coordinator_at_owning_unit": permit(
            why=(
                "registering a contact is the coordinator's own act: they are the named actor "
                "recorded on the registration entry of its audit trail, and the person the "
                "assertion 'this address consented' belongs to"
            ),
        ),
        "coordinator_at_sibling_unit": deny(
            "no_grant",
            why=(
                "outreach is scoped by the loaded unit's own path, never by "
                "anything in the request, so a sibling department's coordinator "
                "does not cover it"
            ),
        ),
        "admin_at_sibling_unit": deny(
            "no_grant",
            why=(
                "the role is required and the membership is active, so the only "
                "thing refusing this principal is the path. No committed artifact "
                "makes outreach tenant-wide, so `_authorize_outreach` passes no "
                "`tenant_wide_roles` and ordinary containment refuses"
            ),
        ),
        "student_at_owning_unit": deny(
            "no_grant",
            why=(
                "outreach is correspondence sent on the institution's behalf, and "
                "the roles that may touch it are the roles accountable for what it "
                "says — this is the operation family where the wrong answer reaches "
                "a real person outside the institution"
            ),
        ),
        "volunteer_at_owning_unit": deny(
            "no_grant",
            why=(
                "`volunteer` is not in this operation's role set, and the "
                "membership is active at exactly the owning unit — so the role "
                "is the only thing left that can refuse it. A contact row asserts "
                "that a named person agreed to be written to, and a volunteer is "
                "not accountable for that assertion"
            ),
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
                "there is no job on this path — it writes rows directly and queues "
                "nothing — so the actor half of the shape is inert and what remains "
                "is a role-less member"
            ),
        ),
        "job_actor_with_explicit_deny": deny(
            "explicit_resource_deny",
            why=(
                "the actor half is inert here for the reason above; what is left "
                "is a deny on the unit, which beats inheritance"
            ),
        ),
    },
    "outreach.contact.update": {
        "admin_at_org_root": permit(
            why="an admin grant at the root covers every unit beneath it",
        ),
        "coordinator_at_owning_unit": permit(
            why=(
                "correcting the evidence behind a consent record, and suppressing an address, are "
                "both the coordinator's own work on their own unit's contacts"
            ),
        ),
        "coordinator_at_sibling_unit": deny(
            "no_grant",
            why=(
                "outreach is scoped by the loaded unit's own path, never by "
                "anything in the request, so a sibling department's coordinator "
                "does not cover it"
            ),
        ),
        "admin_at_sibling_unit": deny(
            "no_grant",
            why=(
                "the role is required and the membership is active, so the only "
                "thing refusing this principal is the path. No committed artifact "
                "makes outreach tenant-wide, so `_authorize_outreach` passes no "
                "`tenant_wide_roles` and ordinary containment refuses"
            ),
        ),
        "student_at_owning_unit": deny(
            "no_grant",
            why=(
                "outreach is correspondence sent on the institution's behalf, and "
                "the roles that may touch it are the roles accountable for what it "
                "says — this is the operation family where the wrong answer reaches "
                "a real person outside the institution"
            ),
        ),
        "volunteer_at_owning_unit": deny(
            "no_grant",
            why=(
                "`volunteer` is not in this operation's role set, and the "
                "membership is active at exactly the owning unit — so the role "
                "is the only thing left that can refuse it. A contact row asserts "
                "that a named person agreed to be written to, and a volunteer is "
                "not accountable for that assertion"
            ),
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
                "there is no job on this path — it writes rows directly and queues "
                "nothing — so the actor half of the shape is inert and what remains "
                "is a role-less member"
            ),
        ),
        "job_actor_with_explicit_deny": deny(
            "explicit_resource_deny",
            why=(
                "the actor half is inert here for the reason above; what is left "
                "is a deny on the unit, which beats inheritance"
            ),
        ),
    },
    "outreach.contact.transition": {
        "admin_at_org_root": permit(
            why="an admin grant at the root covers every unit beneath it",
        ),
        "coordinator_at_owning_unit": permit(
            why=(
                "moving a contact through the consent lifecycle is the coordinator's own act, "
                "recorded against their name on the trail — including the move to 'consented', "
                "which is the moment a person becomes writable to"
            ),
        ),
        "coordinator_at_sibling_unit": deny(
            "no_grant",
            why=(
                "outreach is scoped by the loaded unit's own path, never by "
                "anything in the request, so a sibling department's coordinator "
                "does not cover it"
            ),
        ),
        "admin_at_sibling_unit": deny(
            "no_grant",
            why=(
                "the role is required and the membership is active, so the only "
                "thing refusing this principal is the path. No committed artifact "
                "makes outreach tenant-wide, so `_authorize_outreach` passes no "
                "`tenant_wide_roles` and ordinary containment refuses"
            ),
        ),
        "student_at_owning_unit": deny(
            "no_grant",
            why=(
                "outreach is correspondence sent on the institution's behalf, and "
                "the roles that may touch it are the roles accountable for what it "
                "says — this is the operation family where the wrong answer reaches "
                "a real person outside the institution"
            ),
        ),
        "volunteer_at_owning_unit": deny(
            "no_grant",
            why=(
                "`volunteer` is not in this operation's role set, and the "
                "membership is active at exactly the owning unit — so the role "
                "is the only thing left that can refuse it. A contact row asserts "
                "that a named person agreed to be written to, and a volunteer is "
                "not accountable for that assertion"
            ),
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
                "there is no job on this path — it writes rows directly and queues "
                "nothing — so the actor half of the shape is inert and what remains "
                "is a role-less member"
            ),
        ),
        "job_actor_with_explicit_deny": deny(
            "explicit_resource_deny",
            why=(
                "the actor half is inert here for the reason above; what is left "
                "is a deny on the unit, which beats inheritance"
            ),
        ),
    },
    # The two Speaker Request rows. They differ in exactly one cell —
    # ``volunteer_at_owning_unit`` — and that cell is the whole of customer
    # §12 against customer §13. Written out in full rather than derived from
    # each other for the reason the two ``events`` rows are: the rectangle is
    # the artifact a reviewer reads, and the day one of them diverges further
    # the diff has to show which one.
    "speaker_request.create": {
        "admin_at_org_root": permit(
            why="an admin grant at the root covers every unit beneath it",
        ),
        "coordinator_at_owning_unit": permit(
            why=(
                "containment is inclusive, and `coordinator` is in this role "
                "set: the Speaker Connector persona already decides, publishes "
                "and matches on the same `event` row"
            ),
        ),
        "coordinator_at_sibling_unit": deny(
            "no_grant",
            why=(
                "a Speaker Request is filed under the unit that hosts it "
                "(`event.host_org_unit_id`), and a sibling department's "
                "coordinator does not cover it — the same scoping "
                "`events.read` applies to the catalog it lands in"
            ),
        ),
        "admin_at_sibling_unit": deny(
            "no_grant",
            why=(
                "`admin` is a required role here and the membership is active, "
                "so the only thing refusing this principal is the path. No "
                "committed artifact makes a Speaker Request tenant-wide, so "
                "`_authorize_speaker_request_create` passes no "
                "`tenant_wide_roles`"
            ),
        ),
        "student_at_owning_unit": deny(
            "no_grant",
            why=(
                "customer §15 gives a Student browsing, registration, calendar "
                "and feedback — not the asking. §12 gives creation to the Event "
                "Host, and the membership here is active at exactly the owning "
                "unit, so the role is the only thing left that can refuse it"
            ),
        ),
        "volunteer_at_owning_unit": permit(
            why=(
                "the cell this whole card exists for, and the only permit any "
                "`volunteer` shape has in this file. Customer §4 maps the "
                "stored `volunteer` role onto the **Event Host** persona and "
                "§12 makes the Event Host the person who creates a Speaker "
                "Request. The permit is not the whole rule the route enforces: "
                "the body is still held to the two closed taxonomies, to a "
                "resolved date (ADR-0010 rule 2) and to the virtual/location "
                "exclusion, and those are facts about a payload rather than "
                "about a principal, so `evaluate` cannot express them and "
                "`tests/contract/test_speaker_requests_api.py` asserts them"
            ),
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
                "creating a Speaker Request queues no job — it writes the row "
                "in the request's own transaction — so the actor half of the "
                "shape is inert and what remains is a role-less member"
            ),
        ),
        "job_actor_with_explicit_deny": deny(
            "explicit_resource_deny",
            why=(
                "the actor half is inert here for the reason above; what is "
                "left is a deny on the unit, which beats inheritance"
            ),
        ),
    },
    "speaker_request.list": {
        "admin_at_org_root": permit(
            why="an admin grant at the root covers every unit beneath it",
        ),
        "coordinator_at_owning_unit": permit(
            why=(
                "containment is inclusive, and customer §13 makes viewing "
                "incoming Speaker Requests a Speaker Connector capability"
            ),
        ),
        "coordinator_at_sibling_unit": deny(
            "no_grant",
            why="unit scoping is a path question, not a role question",
        ),
        "admin_at_sibling_unit": deny(
            "no_grant",
            why=(
                "active membership, required role, wrong path — and no "
                "`tenant_wide_roles`, for the reason the create row gives"
            ),
        ),
        "student_at_owning_unit": deny(
            "no_grant",
            why=(
                "the queue carries every host's request text for the unit, "
                "which §13 puts in front of a Speaker Connector and nobody "
                "else; the membership is active at the owning unit, so the "
                "role is the only thing refusing it"
            ),
        ),
        "volunteer_at_owning_unit": deny(
            "no_grant",
            why=(
                "the one cell where this operation is deliberately narrower "
                "than the create above it. §12 lets an Event Host file a "
                "request; §13 names only the Speaker Connector as the reader "
                "of the queue, and reading it would hand one host every other "
                "host's request under the same unit. Under deny-by-default the "
                "narrower reading is the only one available — OQ-CBA-014 is "
                "where the question of a host reading back their own requests "
                "is recorded rather than answered here"
            ),
        ),
        "member_with_no_memberships": deny("no_grant"),
        "resource_grant_only": deny(
            "resource_grant_lacks_required_role",
            why="S-007. A grant conveys reach, not authority.",
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
            why="a read queues nothing, so the actor half of the shape is inert",
        ),
        "job_actor_with_explicit_deny": deny(
            "explicit_resource_deny",
            why="the actor half is inert; a deny on the unit beats inheritance",
        ),
    },
    # The five contact-management rows (customer §13). They are identical to
    # each other, cell for cell, and that is the finding rather than a
    # shortcut: all five are the Speaker Connector acting on their own unit's
    # roster, so there is no principal any one of them admits that another
    # refuses.
    #
    # Written out five times anyway, rather than generated from a template.
    # The rectangle is the artifact a reviewer reads, and a generated one
    # cannot be read: it says "these are the same" without ever saying what
    # they are, and it makes the day one of them legitimately diverges — a
    # correction restricted more tightly than a read, say — a change to a
    # generator rather than a diff that shows which cell moved and why. The
    # two ``events`` rows and the two ``speaker_request`` rows above are spelled
    # out on the same principle and for the same reason.
    #
    # The cell to compare against ``speaker_request.create`` is
    # ``volunteer_at_owning_unit``, and it is the only one that differs from
    # that operation's rectangle.
    "speaker_contact.create": {
        "admin_at_org_root": permit(
            why="an admin grant at the root covers every unit beneath it",
        ),
        "coordinator_at_owning_unit": permit(
            why=(
                "customer §13's own sentence: a Speaker Connector adds a "
                "professional contact to the unit they are accountable for. "
                "Containment is inclusive, so a grant at the owning unit "
                "covers it"
            ),
        ),
        "coordinator_at_sibling_unit": deny(
            "no_grant",
            why=(
                "a contact is filed under the unit whose Connector vouches for "
                "it (`speaker_profile.owning_unit_id`), and a sibling "
                "department's coordinator does not cover that path — the same "
                "scoping every other `owning_unit_id` in this schema carries"
            ),
        ),
        "admin_at_sibling_unit": deny(
            "no_grant",
            why=(
                "`admin` is a required role here and the membership is active, "
                "so the only thing refusing this principal is the path. No "
                "committed artifact makes a unit's contact roster tenant-wide, "
                "so `_authorize_speaker_contacts` passes no `tenant_wide_roles`"
            ),
        ),
        "student_at_owning_unit": deny(
            "no_grant",
            why=(
                "customer §15 gives a Student browsing, registration, calendar "
                "and feedback. A contact record names a real person outside "
                "the institution and asserts a unit stands behind that record; "
                "the membership here is active at exactly the owning unit, so "
                "the role is the only thing left that can refuse it"
            ),
        ),
        "volunteer_at_owning_unit": deny(
            "no_grant",
            why=(
                "**the cell that distinguishes this card from CBA-EVENT-REQUEST.** "
                "`speaker_request.create` permits this exact shape, because "
                "customer §4 maps the stored `volunteer` role onto the Event "
                "Host persona and §12 makes the Event Host the person who files "
                "a Speaker Request. §13 gives the contact roster to the Speaker "
                "Connector and names nobody else, and asking for a speaker is "
                "not the same authority as deciding who is on the list of "
                "people who may be asked. Under deny-by-default the absence of "
                "a permit is a denial rather than an invitation to guess. The "
                "membership is active at exactly the owning unit, so the role "
                "is the only thing refusing this"
            ),
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
                "there is no job on this path — a create writes `user_account`, "
                "`professional_unit_relationship` and `speaker_profile` in the "
                "request's own transaction and queues nothing — so the actor "
                "half of the shape is inert and what remains is a role-less "
                "member"
            ),
        ),
        "job_actor_with_explicit_deny": deny(
            "explicit_resource_deny",
            why=(
                "the actor half is inert here for the reason above; what is "
                "left is a deny on the unit, which beats inheritance"
            ),
        ),
    },
    "speaker_contact.list": {
        "admin_at_org_root": permit(
            why="an admin grant at the root covers every unit beneath it",
        ),
        "coordinator_at_owning_unit": permit(
            why=(
                "a Speaker Connector reading the roster their own unit owns, "
                "which is the §13 surface the other four operations act on"
            ),
        ),
        "coordinator_at_sibling_unit": deny(
            "no_grant",
            why=(
                "the listing is scoped by the loaded unit's own path, never by "
                "anything in the request, so a sibling department's "
                "coordinator does not cover it"
            ),
        ),
        "admin_at_sibling_unit": deny(
            "no_grant",
            why=(
                "active membership, required role, wrong path — and no "
                "`tenant_wide_roles`, for the reason the create row gives"
            ),
        ),
        "student_at_owning_unit": deny(
            "no_grant",
            why=(
                "the roster carries named professionals, their employers and "
                "their titles; §13 puts it in front of a Speaker Connector and "
                "nobody else, and the membership here is active at the owning "
                "unit, so the role is the only thing refusing it"
            ),
        ),
        "volunteer_at_owning_unit": deny(
            "no_grant",
            why=(
                "`volunteer` is the Event Host persona, which §12 admits to "
                "filing a Speaker Request and §13 does not admit to the roster. "
                "Reading it would hand a host the unit's whole list of "
                "professionals — a wider read than the queue of requests "
                "`speaker_request.list` already refuses them"
            ),
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
            why="a read queues nothing, so the actor half of the shape is inert",
        ),
        "job_actor_with_explicit_deny": deny(
            "explicit_resource_deny",
            why="the actor half is inert; a deny on the unit beats inheritance",
        ),
    },
    "speaker_contact.read": {
        "admin_at_org_root": permit(
            why="an admin grant at the root covers every unit beneath it",
        ),
        "coordinator_at_owning_unit": permit(
            why=(
                "one contact out of the same roster the listing returns. Read "
                "and list are not given different role sets: a record readable "
                "one at a time by somebody who cannot read the list is a "
                "distinction with no artifact behind it"
            ),
        ),
        "coordinator_at_sibling_unit": deny(
            "no_grant",
            why=(
                "the contact is loaded by `(tenant_id, professional_id)` within "
                "the unit named in the path, so a sibling department's "
                "coordinator does not cover it"
            ),
        ),
        "admin_at_sibling_unit": deny(
            "no_grant",
            why=(
                "active membership, required role, wrong path — and no "
                "`tenant_wide_roles`, for the reason the create row gives"
            ),
        ),
        "student_at_owning_unit": deny(
            "no_grant",
            why=(
                "a single contact is the same named professional the listing "
                "holds; §13 gives neither to a Student, and the membership is "
                "active at the owning unit, so the role is what refuses it"
            ),
        ),
        "volunteer_at_owning_unit": deny(
            "no_grant",
            why=(
                "`volunteer` is not in this operation's role set, for the "
                "reason the create row states at length: §12's Event Host asks "
                "for a speaker and §13's Speaker Connector keeps the roster"
            ),
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
            why="a read queues nothing, so the actor half of the shape is inert",
        ),
        "job_actor_with_explicit_deny": deny(
            "explicit_resource_deny",
            why="the actor half is inert; a deny on the unit beats inheritance",
        ),
    },
    "speaker_contact.update": {
        "admin_at_org_root": permit(
            why="an admin grant at the root covers every unit beneath it",
        ),
        "coordinator_at_owning_unit": permit(
            why=(
                "customer §13 requires a Speaker Connector to be able to edit a "
                "contact they added. The edit is a current-value UPDATE that "
                "bumps `updated_at` — OQ-CBA-008's interim ruling — so what this "
                "cell permits is the replacement of a stored value, not the "
                "appending of one"
            ),
        ),
        "coordinator_at_sibling_unit": deny(
            "no_grant",
            why=(
                "editing another department's contact is the widening this "
                "`owning_unit_id` scoping exists to refuse"
            ),
        ),
        "admin_at_sibling_unit": deny(
            "no_grant",
            why=(
                "active membership, required role, wrong path — and no "
                "`tenant_wide_roles`, for the reason the create row gives"
            ),
        ),
        "student_at_owning_unit": deny(
            "no_grant",
            why=(
                "§15 gives a Student no write anywhere near a professional's "
                "record; the membership is active at the owning unit, so the "
                "role is the only thing refusing it"
            ),
        ),
        "volunteer_at_owning_unit": deny(
            "no_grant",
            why=(
                "an Event Host may state what they want in a Speaker Request "
                "(§12) and may not restate who a professional is (§13). The "
                "membership is active at exactly the owning unit, so the role "
                "is the only thing left that can refuse it"
            ),
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
                "an edit writes the row in the request's own transaction and "
                "queues nothing, so the actor half of the shape is inert and "
                "what remains is a role-less member"
            ),
        ),
        "job_actor_with_explicit_deny": deny(
            "explicit_resource_deny",
            why=(
                "the actor half is inert here for the reason above; what is "
                "left is a deny on the unit, which beats inheritance"
            ),
        ),
    },
    "speaker_contact.correct_classification": {
        "admin_at_org_root": permit(
            why="an admin grant at the root covers every unit beneath it",
        ),
        "coordinator_at_owning_unit": permit(
            why=(
                "customer §§7-8 both require a Speaker Connector to be able to "
                "correct a classification the pipeline assigned, and §19's flow "
                "is exactly that: infer, then let a Connector fix it. The "
                "correction is a current-value UPDATE and stores no history — "
                "OQ-CBA-008's interim ruling — so this cell is not also a "
                "permit to read who classified the speaker before"
            ),
        ),
        "coordinator_at_sibling_unit": deny(
            "no_grant",
            why=(
                "a correction is a judgment the owning unit's Connector is "
                "accountable for, which is why `speaker_profile.owning_unit_id` "
                "is on the row at all; a sibling department does not cover it"
            ),
        ),
        "admin_at_sibling_unit": deny(
            "no_grant",
            why=(
                "active membership, required role, wrong path — and no "
                "`tenant_wide_roles`, for the reason the create row gives"
            ),
        ),
        "student_at_owning_unit": deny(
            "no_grant",
            why=(
                "§§7-8 name the Speaker Connector as the corrector and nobody "
                "else; a stored classification feeds §9's matching, so writing "
                "one is a decision about who gets recommended to whom"
            ),
        ),
        "volunteer_at_owning_unit": deny(
            "no_grant",
            why=(
                "the sharpest reading of the difference between the two cards. "
                "§12's Event Host names the industries and roles their own "
                "Speaker Request targets — that is `speaker_request.create`, "
                "which this shape is permitted — and §§7-8 give the correction "
                "of a *speaker's* classification to the Speaker Connector. "
                "Letting a host restate what a professional is would let one "
                "side of the match edit the other side's record"
            ),
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
                "a correction updates the profile row directly and queues no "
                "rescore, so the actor half of the shape is inert and what "
                "remains is a role-less member"
            ),
        ),
        "job_actor_with_explicit_deny": deny(
            "explicit_resource_deny",
            why=(
                "the actor half is inert here for the reason above; what is "
                "left is a deny on the unit, which beats inheritance"
            ),
        ),
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

    # `import.create`'s handler calls `assert_allowed` directly; `metrics.py`'s
    # two routes each call it through their own private helper —
    # `_authorize_aggregate_read` for `metrics.read`,
    # `_authorize_drill_down_read` for `metrics.drill_down` — which first
    # loads the unit from the database and then makes exactly this same call
    # against it (`routers/metrics.py`, around those two definitions). The DB
    # load is plumbing that produces `unit.path`, not a second policy
    # decision, so all three names dispatch here rather than each getting its
    # own near-identical branch: the load is out of scope for this
    # no-database file the same way it already is for `import.create` (see
    # the comment on `owning_unit_path` below). `required_roles` and
    # `require_membership` are what actually vary between the operations that
    # reach this branch — `metrics.read` passes `required_roles=frozenset()`
    # and `require_membership=True` (the row's `MEMBERSHIP_ONLY_OPERATIONS`
    # membership), `metrics.drill_down` passes both `_DRILL_DOWN_ROLES` and
    # `require_membership=True` (ordinary role-gated, plus the same keyword
    # for consistency — see `_authorize_drill_down_read`'s own docstring).
    #
    # `_authorize_event_read` (`routers/events.py`) joins them on the same
    # terms and for the same reason: it loads the unit, then makes exactly this
    # call against it with `_EVENT_ROLES`. It is one name rather than two
    # because both event operations share it — see their rows in `OPERATIONS`.
    #
    # `_authorize_match_run` (`routers/match_runs.py`) is the fifth name on the
    # same terms: load the unit, then make exactly this call against that row's
    # path with `_MATCH_RUN_ROLES`. It is one name for two operations for the
    # same reason `_authorize_event_read` is — the submission and the read ask
    # the identical question of the identical resource.
    #
    # `_authorize_student_rewards` and `_authorize_redemption_decision`
    # (`routers/rewards.py`) are the sixth and seventh names, on the same terms
    # again: load the unit, then make exactly this call against that row's path.
    # They are two names rather than one because they are two decisions — one
    # admits the student whose points are at stake (`_REWARDS_STUDENT_ROLES`),
    # the other the person who spends the budget on their behalf
    # (`_REDEMPTION_DECISION_ROLES`) — and a single helper taking the role set as
    # an argument would make one call site the place both are widened from.
    # `_authorize_outreach` (`routers/outreach.py`) is the eighth name, on the
    # same terms as the rest: load the unit, then make exactly this call against
    # that row's path with `_OUTREACH_ROLES`. One name for four operations for
    # the reason `_authorize_event_read` is one for two — composing, listing,
    # sending, and reading all ask the identical question of the identical
    # `org_unit` resource, so a widening applies to all four or to none. The
    # fifth outreach route, `POST /v1/unsubscribe`, does not appear here at all:
    # it has no principal, and its entry is in `UNAUTHENTICATED_ROUTES`.
    # `_authorize_engagement_read` (`routers/engagement.py`) is the ninth name,
    # on the same terms as every one before it: load the unit, then make exactly
    # this call against that row's path with `_ENGAGEMENT_READ_ROLES`. Its own
    # name rather than a share of `_authorize_event_read`'s even though the two
    # role sets agree today — `tests/authz/test_route_roles.py`'s rule, that two
    # sets agreeing is not a reason a widening of one should widen the other.
    #
    # `_authorize_invite_read` (`routers/calendar.py`) is the tenth name, and
    # the only one that does something after the call this stub reproduces: it
    # goes on to `evaluate` the same resource against `_COORDINATOR_ROLES` to
    # learn whether the caller reads the whole unit or is a student who must
    # still produce an `attendance_record`. That second call decides nothing —
    # `assert_allowed` has already raised for anyone outside `_INVITE_ROLES`,
    # and a `False` from it leads to a stricter path rather than a laxer one —
    # so reproducing only the first call here is not a simplification of the
    # authorizer, it is all of the authorizer that is a policy decision. The
    # row-level half is asserted over HTTP in
    # `tests/contract/test_calendar_ics.py`, which is where a fact about one
    # `attendance_record` can actually be stated.
    if operation.authorizer in (
        "assert_allowed",
        "_authorize_aggregate_read",
        "_authorize_drill_down_read",
        "_authorize_event_read",
        "_authorize_engagement_read",
        "_authorize_match_run",
        "_authorize_student_rewards",
        "_authorize_redemption_decision",
        "_authorize_outreach",
        "_authorize_pipeline",
        "_authorize_invite_read",
        # The eleventh and twelfth names (`routers/speaker_requests.py`), on
        # the same terms as every one before them: load the unit, then make
        # exactly this call against that row's path. Two names rather than one
        # because they are two decisions — customer §12 admits the Event Host
        # to the create, §13 admits only the Speaker Connector to the queue —
        # and a shared helper taking the role set as an argument would make one
        # call site the place both are widened from.
        "_authorize_speaker_request_create",
        "_authorize_speaker_request_read",
        # The thirteenth (`routers/cba_contacts.py`), on the same terms. One
        # name for five operations, which is the `_authorize_outreach`
        # arrangement rather than the two-name split directly above it: all
        # five contact-management operations are customer §13's single Speaker
        # Connector persona, so there is one decision and it is made here.
        "_authorize_speaker_contacts",
        # The fourteenth (`routers/student_events.py`), on the same terms: load
        # the unit, then make exactly this call against that row's path with
        # `_STUDENT_EVENT_ROLES`. One name for two operations, the
        # `_authorize_event_read` arrangement — customer §15 names one persona
        # and both routes ask it the identical question. The agenda route then
        # narrows its *rows* by `attendance_record.subject_id`, which is not a
        # second policy decision and could not be one: `evaluate` has no concept
        # of a self-scope. That half is asserted over HTTP in
        # `tests/contract/test_student_events_api.py`, the same division of
        # labour `_authorize_invite_read` already uses.
        "_authorize_student_event_read",
    ):
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
            require_membership=operation.require_membership,
            tenant_wide_roles=operation.tenant_wide_roles,
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
    covered |= set(AUTHENTICATED_ONLY_ROUTES)
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


def test_authentication_only_routes_really_authorize_nothing() -> None:
    """The claim in :data:`AUTHENTICATED_ONLY_ROUTES` is checked, not trusted.

    Exempting a route from the matrix is exactly the shape of change that could
    hide a missing authorization, so the exemption is only honoured while the
    route still matches what the table says about it: it exists, it takes a
    principal, and it calls no authorizer at all. The last clause is the one
    that matters. The moment someone adds an ``assert_allowed`` to one of these
    handlers, the route has a policy worth characterising and belongs in
    ``OPERATIONS`` with a row describing it — so this fails until it is moved,
    rather than leaving it exempt with authorization nobody ever exercised.
    """
    routes = _declared_routes()

    missing = sorted(key for key in AUTHENTICATED_ONLY_ROUTES if key not in routes)
    assert not missing, "AUTHENTICATED_ONLY_ROUTES lists routes that do not exist: " + ", ".join(
        f"{method} {path}" for method, path in missing
    )

    unauthenticated = sorted(
        key for key in AUTHENTICATED_ONLY_ROUTES if not routes[key].authenticated
    )
    assert not unauthenticated, (
        "AUTHENTICATED_ONLY_ROUTES lists routes that take no principal; they are "
        "public, and belong in UNAUTHENTICATED_ROUTES: "
        + ", ".join(f"{method} {path}" for method, path in unauthenticated)
    )

    now_authorizing = sorted(
        (key, routes[key].authorizers)
        for key in AUTHENTICATED_ONLY_ROUTES
        if routes[key].authorizers
    )
    assert not now_authorizing, (
        "these routes are declared as authenticating and authorizing nothing, but "
        "now call an authorizer; give each a row in OPERATIONS instead: "
        + ", ".join(
            f"{method} {path} calls {', '.join(names)}" for (method, path), names in now_authorizing
        )
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

    ``roles_constant is None`` covers two categories, both empty of a finite
    role set: :data:`INTENTIONALLY_UNGATED_OPERATIONS` (a bare grant suffices)
    and :data:`MEMBERSHIP_ONLY_OPERATIONS` (a bare grant does not — see
    ``require_membership``). There is no constant to read for either, so what
    is checked instead is that the row is honest about *belonging to one of
    them* — empty ``required_roles`` and membership in exactly one table, both
    directions, so an operation cannot claim an exemption without also being
    declared, or vice versa.
    """
    if operation.roles_constant is None:
        assert operation.required_roles == frozenset(), (
            f"{operation.key} names no roles_constant, which only makes sense "
            f"for an intentionally ungated or membership-only operation; "
            f"MATRIX states required_roles={sorted(operation.required_roles)}"
        )
        assert (
            operation.key in INTENTIONALLY_UNGATED_OPERATIONS
            or operation.key in MEMBERSHIP_ONLY_OPERATIONS
        ), (
            f"{operation.key} names no roles_constant but is not listed in "
            f"INTENTIONALLY_UNGATED_OPERATIONS or MEMBERSHIP_ONLY_OPERATIONS — "
            f"add it to one with a reason, or give it a real roles_constant"
        )
        assert not (
            operation.key in INTENTIONALLY_UNGATED_OPERATIONS
            and operation.key in MEMBERSHIP_ONLY_OPERATIONS
        ), (
            f"{operation.key} is listed in both INTENTIONALLY_UNGATED_OPERATIONS "
            f"and MEMBERSHIP_ONLY_OPERATIONS — a resource grant cannot both "
            f"satisfy this operation and be refused by it; pick one"
        )
        return

    assert operation.key not in INTENTIONALLY_UNGATED_OPERATIONS, (
        f"{operation.key} is listed in INTENTIONALLY_UNGATED_OPERATIONS but "
        f"names a real roles_constant ({operation.roles_constant!r}); remove "
        f"it from that table"
    )
    assert operation.key not in MEMBERSHIP_ONLY_OPERATIONS, (
        f"{operation.key} is listed in MEMBERSHIP_ONLY_OPERATIONS but names a "
        f"real roles_constant ({operation.roles_constant!r}); remove it from "
        f"that table — a role-gated operation already refuses a bare grant "
        f"via resource_grant_lacks_required_role"
    )
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


def _authorizer_function_node(operation: Operation) -> ast.FunctionDef | ast.AsyncFunctionDef:
    """The function whose body should carry the role decision this operation names.

    When the operation names a dedicated authorizer, that function is where the
    role set has to be read; when it calls the policy directly, the handler is.
    ``authz_module`` is where to look for the former, which for the four job
    operations is the shared module rather than their own router.
    """
    route = _declared_routes()[(operation.method, operation.path)]
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
    return functions[0]


def _passes_required_roles_keyword(function_node: ast.AST) -> bool:
    """Whether a call to a policy entry point inside ``function_node`` names ``required_roles``.

    Used only for the intentionally-ungated case: the row claims the code
    passes no ``required_roles`` at all (rather than an empty constant), and
    this is what checks that claim against the source instead of trusting it.
    """
    for child in ast.walk(function_node):
        if not isinstance(child, ast.Call):
            continue
        name = _referenced_name(child.func)
        if name not in _POLICY_ENTRY_POINTS:
            continue
        if any(keyword.arg == "required_roles" for keyword in child.keywords):
            return True
    return False


@pytest.mark.parametrize("operation", OPERATIONS, ids=lambda op: op.key)
def test_the_authorizer_reads_the_role_constant_the_matrix_names(operation: Operation) -> None:
    """The constant must be the one this operation's decision actually reads.

    Without this, ``JOB_OVERSIGHT_ROLES`` could keep its value while the authorizer
    started reading a different, wider set, and the check above would still pass
    against a constant nothing uses.

    For an intentionally-ungated operation (``roles_constant is None``) there is
    no constant to find, so what is checked instead is the other direction of
    the same drift: that the authorizing function still passes no
    ``required_roles`` to ``assert_allowed``/``evaluate`` at all. If it started
    passing one, the row's claim of "ungated" would be stale — this is what
    catches that instead of leaving :data:`INTENTIONALLY_UNGATED_OPERATIONS`
    to go silently wrong.
    """
    function_node = _authorizer_function_node(operation)

    if operation.roles_constant is None:
        assert not _passes_required_roles_keyword(function_node), (
            f"{operation.authz_module} now passes required_roles to its policy "
            f"call, but MATRIX records {operation.key} as intentionally ungated "
            f"(roles_constant=None); give it a real roles_constant and remove it "
            f"from INTENTIONALLY_UNGATED_OPERATIONS"
        )
        return

    names = {node.id for node in ast.walk(function_node) if isinstance(node, ast.Name)}
    assert operation.roles_constant in names, (
        f"{operation.authz_module} does not reference {operation.roles_constant}, "
        f"which MATRIX says is where {operation.key} gets its role set"
    )


def _passes_require_membership_keyword(function_node: ast.AST) -> bool:
    """Whether a policy call inside ``function_node`` passes ``require_membership=True``.

    A *literal* ``True`` only. A name, an attribute or a call in that position
    is an expression this file cannot evaluate, and reading an unevaluatable
    expression as "yes" is how a source check like this quietly stops catching
    anything. If an authorizer ever needs to compute the flag, this returning
    ``False`` is the correct, loud outcome: the matrix row and the code have
    stopped being comparable by reading, and that is worth a failure.
    """
    for child in ast.walk(function_node):
        if not isinstance(child, ast.Call):
            continue
        if _referenced_name(child.func) not in _POLICY_ENTRY_POINTS:
            continue
        for keyword in child.keywords:
            if keyword.arg != "require_membership":
                continue
            if isinstance(keyword.value, ast.Constant) and keyword.value.value is True:
                return True
    return False


@pytest.mark.parametrize("operation", OPERATIONS, ids=lambda op: op.key)
def test_the_authorizer_passes_require_membership_exactly_when_the_matrix_says_so(
    operation: Operation,
) -> None:
    """``Operation.require_membership`` must describe the code, not itself.

    Every other field on a row is held against the source or against the live
    object: :func:`test_the_route_calls_the_authorizer_the_matrix_names`
    catches the two metrics authorizers being swapped, and
    :func:`test_the_authorizer_reads_the_role_constant_the_matrix_names`
    catches ``_DRILL_DOWN_ROLES`` being dropped. ``require_membership`` had no
    such check: :func:`_authorize` reconstructs the ``assert_allowed`` call
    from the row's own field, so the row was being compared with itself, and
    deleting ``require_membership=True`` from ``_authorize_aggregate_read``
    left the whole of ``tests/authz`` green.

    What that mutation costs is the §4 denial itself: a principal holding only
    an ``allow`` ``resource_grant`` on the unit, with no membership anywhere,
    reaches Path 2, gets ``explicit_resource_allow``, and reads the unit's
    aggregates — the exact permit the ratified decision refuses. The only
    other test that would notice is in ``tests/contract/test_metrics.py``,
    which is ``pytest.mark.integration`` and cannot run without PostgreSQL.

    Checked in **both** directions, like every other membership check in this
    file: an operation the matrix marks ``require_membership=True`` must pass
    the keyword, and one it marks ``False`` must not — so quietly hardening a
    route without recording it fails here too, rather than leaving the row
    stale in the loose direction.
    """
    function_node = _authorizer_function_node(operation)
    passes = _passes_require_membership_keyword(function_node)

    if operation.require_membership:
        assert passes, (
            f"MATRIX records {operation.key} as require_membership=True, but "
            f"{operation.authz_module}.{operation.authorizer} does not pass "
            f"require_membership=True to assert_allowed/evaluate. Without that "
            f"keyword a bare resource_grant with no covering membership is "
            f"permitted via explicit_resource_allow, which the ratified metrics "
            f"authorization decision (§4) denies. Restore the keyword, or — if "
            f"the policy really changed — change the row and the decision record."
        )
    else:
        assert not passes, (
            f"{operation.authz_module}.{operation.authorizer} now passes "
            f"require_membership=True, but MATRIX records {operation.key} as "
            f"require_membership=False; set the field on the row so the matrix "
            f"describes the code"
        )


def _tenant_wide_roles_argument(function_node: ast.AST) -> str | None:
    """The name a policy call inside ``function_node`` passes as ``tenant_wide_roles``.

    Returns the referenced constant's name, or ``None`` when no policy call in
    the function passes the keyword at all. Only a plain name (or a dotted
    attribute, whose ``.attr`` is what matters) is recognised — the same
    deliberate narrowness :func:`_passes_require_membership_keyword` takes, and
    for the same reason: an inline set literal or a computed expression in that
    position is something this file cannot compare against a live object, and
    reading an uncomparable expression as "fine" is how a source check stops
    catching anything. If an authorizer ever needs to build the set inline,
    this returning ``None`` and failing loudly is the correct outcome.
    """
    for child in ast.walk(function_node):
        if not isinstance(child, ast.Call):
            continue
        if _referenced_name(child.func) not in _POLICY_ENTRY_POINTS:
            continue
        for keyword in child.keywords:
            if keyword.arg == "tenant_wide_roles":
                return _referenced_name(keyword.value)
    return None


@pytest.mark.parametrize("operation", OPERATIONS, ids=lambda op: op.key)
def test_the_authorizer_passes_the_tenant_wide_roles_the_matrix_names(
    operation: Operation,
) -> None:
    """``tenant_wide_roles`` must describe the code, in both directions and by name.

    The exact counterpart of
    :func:`test_the_authorizer_passes_require_membership_exactly_when_the_matrix_says_so`,
    and it exists for the same structural reason: :func:`_authorize` builds its
    ``assert_allowed`` call *from the row's own field*, so without a source
    check the row would be compared with itself and deleting
    ``tenant_wide_roles=_TENANT_WIDE_AGGREGATE_ROLES`` from
    ``_authorize_aggregate_read`` would leave the whole of ``tests/authz``
    green.

    What that mutation costs is §4's tenant-wide admin rule: an active
    ``admin`` membership attached below the tenant root — which nothing in the
    schema forbids — goes back to a 403 on a sibling unit's aggregates, the
    wrongful denial this keyword exists to fix. Only
    ``tests/contract/test_metrics.py`` would otherwise notice, and only with a
    live PostgreSQL.

    Three things are asserted, not one: that the keyword is passed exactly for
    the operations the matrix marks tenant-wide (so quietly widening
    ``metrics.drill_down`` fails here too), that the constant passed is the one
    the row names (so swapping in a wider set fails), and that the constant's
    *live value* matches what the row records (so editing
    ``_TENANT_WIDE_AGGREGATE_ROLES`` to add ``coordinator`` fails).
    """
    function_node = _authorizer_function_node(operation)
    passed = _tenant_wide_roles_argument(function_node)

    if operation.tenant_wide_roles_constant is None:
        assert operation.tenant_wide_roles == frozenset(), (
            f"{operation.key} names no tenant_wide_roles_constant but records "
            f"tenant_wide_roles={sorted(operation.tenant_wide_roles)}"
        )
        assert passed is None, (
            f"{operation.authz_module}.{operation.authorizer} now passes "
            f"tenant_wide_roles={passed!r}, but MATRIX records {operation.key} "
            f"as ordinarily unit-scoped. A tenant-wide role reaches units no "
            f"membership of the caller's covers — the one thing "
            f"test_no_operation_is_reachable_from_a_sibling_department "
            f"otherwise forbids — so it has to be recorded on the row and "
            f"declared in TENANT_WIDE_ROLE_OPERATIONS with the decision that "
            f"authorizes it."
        )
        return

    assert passed == operation.tenant_wide_roles_constant, (
        f"MATRIX says {operation.key} passes "
        f"{operation.tenant_wide_roles_constant!r} as tenant_wide_roles, but "
        f"{operation.authz_module}.{operation.authorizer} passes {passed!r}. "
        f"Without that argument an admin whose membership hangs below the "
        f"tenant root is refused a sibling unit's aggregates, which the "
        f"ratified metrics authorization decision (§4, 'admin: unrestricted "
        f"within tenant for aggregates') does not say. Restore it, or — if "
        f"the policy really changed — change the row and the decision record."
    )
    module = importlib.import_module(operation.authz_module)
    declared = getattr(module, operation.tenant_wide_roles_constant, None)
    assert declared is not None, (
        f"{operation.authz_module} has no {operation.tenant_wide_roles_constant}"
    )
    assert declared == operation.tenant_wide_roles, (
        f"{operation.key}: MATRIX states tenant-wide roles "
        f"{sorted(operation.tenant_wide_roles)} but "
        f"{operation.authz_module}.{operation.tenant_wide_roles_constant} is "
        f"{sorted(declared)}"
    )


def test_every_tenant_wide_operation_is_declared() -> None:
    """Both directions, exactly as the other two category tables are checked.

    Tenant-wide reach is the only sanctioned way past unit scoping in this
    codebase, so an operation must not acquire it without landing in
    :data:`TENANT_WIDE_ROLE_OPERATIONS`, and the table must not claim it for
    an operation the code does not give it.
    """
    tenant_wide = {operation.key for operation in OPERATIONS if operation.tenant_wide_roles}
    undeclared = tenant_wide - TENANT_WIDE_ROLE_OPERATIONS
    assert not undeclared, (
        f"these operations now permit a role outside the resource's own "
        f"subtree and are not recorded in TENANT_WIDE_ROLE_OPERATIONS: "
        f"{sorted(undeclared)}. Name the decision that authorizes it."
    )
    stale = TENANT_WIDE_ROLE_OPERATIONS - tenant_wide
    assert not stale, (
        f"TENANT_WIDE_ROLE_OPERATIONS names operations the code does not "
        f"actually give tenant-wide reach: {sorted(stale)}. Remove them, or "
        f"restore the tenant_wide_roles argument on their authorizer."
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


#: Shapes carrying an active membership at exactly the owning unit, in the
#: order :func:`_wrong_role_shape_for` prefers them. Every one of them differs
#: from the others in nothing but its role, which is what makes a denial
#: attributable to the role rather than to the path, the clock, or the tenant.
_ACTIVE_OWNING_UNIT_SHAPES: tuple[str, ...] = (
    "student_at_owning_unit",
    "coordinator_at_owning_unit",
    # Last, so the nineteen operations that already had a wrong-role shape keep
    # the one they were written against and this addition changes what nothing
    # else asserts. It is reached only by an operation that admits both of the
    # shapes above — today that is `calendar.invite.download` alone.
    "volunteer_at_owning_unit",
)


def _wrong_role_shape_for(operation: Operation) -> str:
    """The shape that holds a covering membership carrying the *wrong* role here.

    ``student_at_owning_unit`` for every operation that does not name
    ``student``, which was the hard-coded answer before card P-REWARDS-API and
    is still the answer for eleven of the fifteen operations. The four rewards
    operations broke that assumption honestly rather than by accident: three of
    them gate on ``student`` precisely, so for those the student shape is the
    *right* role and asserting its denial would assert the opposite of the
    intended behaviour.

    Chosen rather than declared per operation, so a new operation cannot arrive
    with a hand-picked shape that happens to deny for some other reason. The
    returned shape is guaranteed to hold an active membership at exactly the
    owning unit, so the only thing that can refuse it is the role.

    Raises:
        AssertionError: the operation requires every role any of these shapes
            carries, so there is no wrong-role case left to test with. That is a
            real hole, not a technicality — an operation nothing can be refused
            from for role reasons needs a new shape, not a skipped assertion.
    """
    for shape_name in _ACTIVE_OWNING_UNIT_SHAPES:
        role = SHAPES_BY_NAME[shape_name].memberships[0].role
        if role not in operation.required_roles:
            return shape_name
    raise AssertionError(
        f"{operation.key} requires every role the owning-unit shapes carry "
        f"({sorted(operation.required_roles)}), so no cell in its row refuses a "
        f"covering membership for its role. Add a shape rather than skip this."
    )


@pytest.mark.parametrize("operation", OPERATIONS, ids=lambda op: op.key)
def test_every_operation_denies_a_principal_without_its_role(operation: Operation) -> None:
    """A4's core requirement: a negative test per operation.

    Deny-by-default means the interesting assertion is the denial, so this is
    stated as a property of the matrix rather than left to the reader to spot:
    every operation has at least one cell where a principal holding an active,
    covering membership is refused for holding the wrong role, and at least one
    where a principal holding nothing is refused.

    The "wrong role" half is skipped for :data:`INTENTIONALLY_UNGATED_OPERATIONS`
    and :data:`MEMBERSHIP_ONLY_OPERATIONS` alike — there is no wrong role to
    hold when the operation names none, by design (S-007);
    :func:`test_an_intentionally_ungated_operation_admits_any_active_membership`
    and :func:`test_a_membership_only_operation_admits_any_active_membership`
    are that property's positive counterpart for each category, asserted
    rather than merely unassert-ed here. "Holding nothing is refused" still
    applies to every operation without exception: neither category is
    unauthenticated.
    """
    row = MATRIX[operation.key]
    if operation.key not in INTENTIONALLY_UNGATED_OPERATIONS | MEMBERSHIP_ONLY_OPERATIONS:
        shape_name = _wrong_role_shape_for(operation)
        wrong_role = row[shape_name]
        assert not wrong_role.permit and wrong_role.reason == "no_grant", (
            f"{operation.key} admits {shape_name}, an active membership at the "
            f"owning unit carrying none of {sorted(operation.required_roles)}"
        )
    nothing = row["member_with_no_memberships"]
    assert not nothing.permit, f"{operation.key} admits a principal holding nothing"


@pytest.mark.parametrize(
    "operation",
    [op for op in OPERATIONS if op.key in INTENTIONALLY_UNGATED_OPERATIONS],
    ids=lambda op: op.key,
)
def test_an_intentionally_ungated_operation_admits_any_active_membership(
    operation: Operation,
) -> None:
    """The positive half of ungating: *any* role at the unit is enough, not none.

    Ungating an operation is not "no check at all" — unit scoping (path
    containment), tenant isolation, and suspension all still apply, as the
    other cells in the same row prove. What specifically falls away is the
    role filter: :func:`smartmatch_authz.evaluate` skips it entirely when
    ``required_roles`` is empty, so an active membership holding a role this
    operation never named — ``student``, in the shape below — is exactly as
    good as any other for reaching a resource it already covers. Asserted
    against the real authorizer, not only against the recorded cell, so a
    regression here fails on the code rather than only on the matrix agreeing
    with itself.
    """
    cell = MATRIX[operation.key]["student_at_owning_unit"]
    assert cell.permit, (
        f"{operation.key} is recorded in INTENTIONALLY_UNGATED_OPERATIONS but "
        f"denies an active membership at the owning unit anyway; if it is now "
        f"role-gated, remove it from that table and give it real required_roles"
    )
    observed = _observe(operation, SHAPES_BY_NAME["student_at_owning_unit"])
    assert observed.permit


@pytest.mark.parametrize(
    "operation",
    [op for op in OPERATIONS if op.key in MEMBERSHIP_ONLY_OPERATIONS],
    ids=lambda op: op.key,
)
def test_a_membership_only_operation_admits_any_active_membership(
    operation: Operation,
) -> None:
    """The positive half of membership-only, mirroring the ungated one exactly.

    Same mechanism as :func:`test_an_intentionally_ungated_operation_admits_any_active_membership`
    — an empty ``required_roles`` means ``evaluate``'s role filter never
    triggers on Path 1 (inherited membership), so a ``student`` membership at
    the owning unit is exactly as good as any other role there. What
    distinguishes this category is Path 2, checked separately by
    :func:`test_a_bare_resource_grant_never_satisfies_a_membership_only_operation`
    — membership-only means membership, specifically, is what has to be held;
    this test is the "membership is still enough regardless of role" half of
    that, not the "a grant alone is not" half.
    """
    cell = MATRIX[operation.key]["student_at_owning_unit"]
    assert cell.permit, (
        f"{operation.key} is recorded in MEMBERSHIP_ONLY_OPERATIONS but denies "
        f"an active membership at the owning unit anyway; if it is now "
        f"role-gated, remove it from that table and give it real required_roles"
    )
    observed = _observe(operation, SHAPES_BY_NAME["student_at_owning_unit"])
    assert observed.permit


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


def test_every_ungated_operation_is_declared_intentional() -> None:
    """Every operation that reaches the policy's ungated grant path says so on purpose.

    :func:`smartmatch_authz.evaluate` allows a bare resource grant when an
    operation names no roles *and* does not require membership either — the
    guest-reviewer case the policy is designed for. Scoped away from
    ``require_membership=True`` operations deliberately:
    :data:`MEMBERSHIP_ONLY_OPERATIONS` also names no required roles, but a
    bare grant does *not* suffice for it, which is exactly what
    :func:`test_every_membership_only_operation_is_declared` checks in its own
    right rather than here. Folding the two together would let a genuinely
    ungated operation hide behind a membership-only one's empty role set, or
    the reverse.

    This checks both directions: an operation cannot be ungated in the code
    without being declared here (an *undeclared* new hole still fails, which
    is what keeps this from being a weakening), and the table cannot name an
    operation that is not actually ungated in the code.
    """
    ungated = {
        operation.key
        for operation in OPERATIONS
        if not operation.required_roles and not operation.require_membership
    }
    undeclared = ungated - INTENTIONALLY_UNGATED_OPERATIONS
    assert not undeclared, (
        f"these operations name no required roles and no require_membership, so "
        f"a bare resource grant now suffices for them, and they are not "
        f"recorded in INTENTIONALLY_UNGATED_OPERATIONS: {sorted(undeclared)}. "
        f"Confirm that is intended (S-007) and add them there with a reason."
    )
    stale = INTENTIONALLY_UNGATED_OPERATIONS - ungated
    assert not stale, (
        f"INTENTIONALLY_UNGATED_OPERATIONS names operations that are actually "
        f"role-gated or membership-only in the code: {sorted(stale)}. Remove "
        f"them from the table."
    )


def test_every_membership_only_operation_is_declared() -> None:
    """The membership-only counterpart of the ungated check above, same rigour.

    An operation lands in :data:`MEMBERSHIP_ONLY_OPERATIONS` exactly when it
    names no ``required_roles`` (nothing to enumerate) but does pass
    ``require_membership=True`` (a bare grant is still refused) — the shape
    the ratified metrics authorization decision's aggregate rule needs and
    S-007's original two categories could not express. Checked both
    directions, the same way :func:`test_every_ungated_operation_is_declared_intentional`
    is: an operation cannot gain this shape in the code without being declared
    here, and the table cannot name an operation the code does not actually
    give this shape.
    """
    membership_only = {
        operation.key
        for operation in OPERATIONS
        if not operation.required_roles and operation.require_membership
    }
    undeclared = membership_only - MEMBERSHIP_ONLY_OPERATIONS
    assert not undeclared, (
        f"these operations name no required roles but do require membership, "
        f"and are not recorded in MEMBERSHIP_ONLY_OPERATIONS: "
        f"{sorted(undeclared)}. Add them there with a reason."
    )
    stale = MEMBERSHIP_ONLY_OPERATIONS - membership_only
    assert not stale, (
        f"MEMBERSHIP_ONLY_OPERATIONS names operations the code does not "
        f"actually give that shape: {sorted(stale)}. Remove them from the "
        f"table, or restore require_membership=True on their authorizer."
    )


# ---------------------------------------------------------------------------
# S-007 — the decision, stated as a rule
# ---------------------------------------------------------------------------


#: Operations that are neither intentionally ungated nor membership-only —
#: i.e. a bare ``resource_grant`` must be refused via the ordinary
#: ``required_roles`` check (``resource_grant_lacks_required_role``), not via
#: ``require_membership``. Excludes both tables, not just the ungated one:
#: before the metrics authorization decision this repository had only two
#: categories, and ``INTENTIONALLY_UNGATED_OPERATIONS`` was the only one to
#: subtract; now there are three, and a membership-only operation is no more
#: "role-gated" than an ungated one is — it just fails a different way.
_ROLE_GATED_OPERATIONS = tuple(
    operation
    for operation in OPERATIONS
    if operation.key not in INTENTIONALLY_UNGATED_OPERATIONS
    and operation.key not in MEMBERSHIP_ONLY_OPERATIONS
)


@pytest.mark.parametrize("operation", _ROLE_GATED_OPERATIONS, ids=lambda op: op.key)
def test_a_bare_resource_grant_never_satisfies_a_role_gated_operation(
    operation: Operation,
) -> None:
    """The S-007 rule, pinned on every *role-gated* operation rather than on one.

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

    Scoped to :data:`_ROLE_GATED_OPERATIONS` rather than every operation: for
    an *intentionally* ungated one there is no required role for the grant to
    lack, so ``evaluate`` correctly permits it — that is the rule answered the
    other way on purpose, not this rule broken. See
    :func:`test_a_bare_resource_grant_satisfies_an_intentionally_ungated_operation`
    for that side, asserted just as explicitly.
    """
    cell = MATRIX[operation.key]["resource_grant_only"]
    assert not cell.permit, (
        f"{operation.key} admits a principal whose only claim is a resource "
        f"grant. That is the S-007 loosening; it needs a product decision, not a "
        f"patch."
    )
    observed = _observe(operation, SHAPES_BY_NAME["resource_grant_only"])
    assert not observed.permit


@pytest.mark.parametrize(
    "operation",
    [op for op in OPERATIONS if op.key in INTENTIONALLY_UNGATED_OPERATIONS],
    ids=lambda op: op.key,
)
def test_a_bare_resource_grant_satisfies_an_intentionally_ungated_operation(
    operation: Operation,
) -> None:
    """S-007 answered "yes", the other direction: this is the case the rule exists for.

    A resource grant conveys reach, not authority — but when an operation asks
    for no authority beyond reach (no ``required_roles`` at all), reach is
    exactly enough. This is the guest-reviewer shape the policy's ungated path
    was designed for, landing on a real operation for the first time, and the
    reason code (``explicit_resource_allow``, not the gated operations'
    ``resource_grant_lacks_required_role``) is what the audit trail uses to
    tell the two populations apart.
    """
    cell = MATRIX[operation.key]["resource_grant_only"]
    assert cell.permit, (
        f"{operation.key} is recorded in INTENTIONALLY_UNGATED_OPERATIONS but "
        f"denies a bare resource grant anyway; if it is now role-gated, remove "
        f"it from that table and give it real required_roles"
    )
    observed = _observe(operation, SHAPES_BY_NAME["resource_grant_only"])
    assert observed.permit

    # `_observe` records a reason only for denials (permit cells carry
    # `reason=None` by construction — see `Cell`), so the specific allow
    # reason is checked directly against `evaluate`, the same function
    # `assert_allowed` wraps, rather than through that shortcut.
    resolved = _resolved(operation, SHAPES_BY_NAME["resource_grant_only"])
    decision = evaluate(
        resolved.principal,
        Resource(
            resource_type=operation.resource_type,
            resource_id=operation.resource_id,
            tenant_id=str(resolved.tenant_id),
            owning_unit_path=OrgPath.parse(OWNING_UNIT),
        ),
        at=NOW,
        required_roles=operation.required_roles,
    )
    assert decision.allowed and decision.reason == "explicit_resource_allow"


@pytest.mark.parametrize(
    "operation",
    [op for op in OPERATIONS if op.key in MEMBERSHIP_ONLY_OPERATIONS],
    ids=lambda op: op.key,
)
def test_a_bare_resource_grant_never_satisfies_a_membership_only_operation(
    operation: Operation,
) -> None:
    """The direct inverse of the ungated test above — pinned on ``metrics.read``.

    This is the test the task brief asked for by name: before the metrics
    authorization decision was ratified, ``metrics.read`` sat in
    :data:`INTENTIONALLY_UNGATED_OPERATIONS` and this exact shape —
    ``resource_grant_only`` — *permitted*. The decision's §4 answers "bare
    resource_grant reads aggregates?" with **No — role required**, which this
    codebase expresses not as a role requirement (there is none to enumerate)
    but as membership required (``require_membership=True``). The reason code,
    ``resource_grant_lacks_membership``, is what tells this population apart
    from a role-gated operation's ``resource_grant_lacks_required_role`` in
    the audit trail — the same distinction
    :func:`test_the_distinct_denial_reason_survives` draws for
    :data:`_ROLE_GATED_OPERATIONS`, drawn here for this table instead.
    """
    cell = MATRIX[operation.key]["resource_grant_only"]
    assert not cell.permit and cell.reason == "resource_grant_lacks_membership", (
        f"{operation.key} is recorded in MEMBERSHIP_ONLY_OPERATIONS but admits "
        f"a bare resource grant anyway; if that is now intended, move it to "
        f"INTENTIONALLY_UNGATED_OPERATIONS instead"
    )
    observed = _observe(operation, SHAPES_BY_NAME["resource_grant_only"])
    assert not observed.permit and observed.reason == "resource_grant_lacks_membership"

    # Same shortcut as the ungated test above: `_observe` only records a
    # reason for denials, which is exactly what this branch is, so the
    # decision is available through it directly — no need for the second,
    # direct `evaluate` call the allow-side test needs to see past `_observe`
    # recording no reason for a permit.


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
    """The reason code is the audit trail's record that S-007 is still open — for gated operations.

    ``resource_grant_lacks_required_role`` is not interchangeable with
    ``no_grant``: it says the principal held a grant that conveyed nothing,
    which is the population that would be affected the day the rule changes.
    Collapsing it into ``no_grant`` would make that population unmeasurable.

    Every *role-gated* operation, not the three that used to manage it.
    ``job.read`` and ``job.events.read`` answered ``no_grant`` here because the
    old read path consulted no grants at all — a refusal in the right
    direction that recorded the wrong thing, so a grant-holder and a stranger
    were indistinguishable in the audit trail. Listing all of
    :data:`_ROLE_GATED_OPERATIONS` is what stops the exception coming back.
    Scoped away from :data:`INTENTIONALLY_UNGATED_OPERATIONS`: those answer
    ``explicit_resource_allow`` instead, which is S-007 decided the other way
    on purpose — see
    :func:`test_a_bare_resource_grant_satisfies_an_intentionally_ungated_operation`.
    """
    for operation in _ROLE_GATED_OPERATIONS:
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

    # The sibling shape above holds a *coordinator*, so it cannot see the one
    # sanctioned way past unit scoping: `admin_at_sibling_unit`, whose role the
    # ratified metrics-authorization decision makes tenant-wide for aggregates.
    # Left unchecked, "if an operation is genuinely tenant-wide, say so here
    # deliberately" would be advice rather than a control — a second operation
    # could quietly start admitting a sibling department's admin and no
    # assertion in this file would move. So the exception is enumerated too:
    # only the operations declared in TENANT_WIDE_ROLE_OPERATIONS may permit
    # it, and every one of them must.
    tenant_wide_leaking = {
        operation.key
        for operation in OPERATIONS
        if MATRIX[operation.key]["admin_at_sibling_unit"].permit
    }
    assert tenant_wide_leaking == TENANT_WIDE_ROLE_OPERATIONS, (
        f"operations admitting an admin from a different department are "
        f"{sorted(tenant_wide_leaking)}, but TENANT_WIDE_ROLE_OPERATIONS "
        f"declares {sorted(TENANT_WIDE_ROLE_OPERATIONS)}. Tenant-wide reach is "
        f"the decision record's exception (§4, aggregates only) and has to be "
        f"declared where it is taken."
    )


def _decision_for(
    shape: Shape,
    *,
    operation_key: str = "metrics.read",
    tenant_wide_roles: frozenset[str] | None = None,
) -> AccessDecision:
    """Evaluate one shape against ``metrics.read``'s resource, directly.

    Goes to :func:`evaluate` rather than through :func:`_observe` because these
    tests need the *allow* reason code, which :class:`Cell` does not carry (a
    permit cell has ``reason=None`` by construction) — the same shortcut
    :func:`test_a_bare_resource_grant_satisfies_an_intentionally_ungated_operation`
    takes. ``tenant_wide_roles`` overrides the row's own value so a single
    shape can be run with the mechanism on and off.
    """
    operation = OPERATIONS_BY_KEY[operation_key]
    resolved = _resolved(operation, shape)
    return evaluate(
        resolved.principal,
        Resource(
            resource_type=operation.resource_type,
            resource_id=operation.resource_id,
            tenant_id=str(resolved.tenant_id),
            owning_unit_path=OrgPath.parse(OWNING_UNIT),
        ),
        at=NOW,
        required_roles=operation.required_roles,
        require_membership=operation.require_membership,
        tenant_wide_roles=(
            operation.tenant_wide_roles if tenant_wide_roles is None else tenant_wide_roles
        ),
    )


def test_a_tenant_wide_role_reaches_a_unit_its_own_path_does_not_cover() -> None:
    """§4's admin rule, run in both directions so the permit is attributable.

    A denial or a permit on its own proves little here — the admin shape could
    be permitted for some unrelated reason, or refused because the whole role
    check broke. So the *same* principal and the *same* resource are evaluated
    twice, varying only ``tenant_wide_roles``: refused ``no_grant`` without it
    (which is the bug — a wrongful 403 on a sibling unit's aggregates for an
    admin the org tree does not root at the tenant root), allowed with it, and
    allowed specifically because of it, which the distinct reason code
    ``tenant_wide_role_grant`` is what records.
    """
    shape = SHAPES_BY_NAME["admin_at_sibling_unit"]

    without = _decision_for(shape, tenant_wide_roles=frozenset())
    assert not without.allowed and without.reason == "no_grant", (
        "the sibling admin is reachable without the tenant-wide keyword, so "
        "the permit below proves nothing about the keyword"
    )

    with_it = _decision_for(shape)
    assert with_it.allowed and with_it.reason == "tenant_wide_role_grant"
    assert with_it.matched_path == OrgPath.parse(SIBLING_UNIT)


def test_a_tenant_wide_role_does_not_relabel_an_ordinary_containment_permit() -> None:
    """An admin whose membership *does* cover the unit still reports the old reason.

    The keyword is checked after Path 1, deliberately (policy module docstring,
    rule 7), so ``tenant_wide_role_grant`` means exactly one thing in the audit
    trail: this permit existed only because the role reaches tenant-wide. If
    the check moved ahead of Path 1 every admin permit would start carrying it
    and the population would stop being countable.
    """
    decision = _decision_for(SHAPES_BY_NAME["admin_at_org_root"])
    assert decision.allowed and decision.reason == "inherited_unit_grant"


def test_a_tenant_wide_role_never_outranks_suspension_tenant_or_an_explicit_deny() -> None:
    """The three controls that must survive the widening, asserted rather than assumed.

    Every one of these shapes holds an ``admin`` membership, so each would be
    permitted by Path 1b on the role alone if the new check had been placed
    ahead of the earlier rules instead of after them. That is precisely the
    defect a widening like this invites — a role that reaches everywhere
    quietly reaching *past* suspension, tenant isolation, or an administrator's
    explicit carve-out — so it is pinned per control, with the reason code, not
    left to the reading of the source.
    """
    suspended = _decision_for(SHAPES_BY_NAME["suspended_admin"])
    assert not suspended.allowed and suspended.reason == "principal_suspended"

    denied = _decision_for(SHAPES_BY_NAME["admin_with_explicit_deny"])
    assert not denied.allowed and denied.reason == "explicit_resource_deny"

    # The cross-tenant shape carries a coordinator, so the tenant check is put
    # to a real admin here: the same tenant-wide role, in the wrong tenant.
    cross_tenant_admin = Shape(
        name="cross_tenant_admin",
        description="an admin whose authorization tenant is another tenant entirely",
        memberships=(_member(SIBLING_UNIT, "admin"),),
        cross_tenant=True,
    )
    crossed = _decision_for(cross_tenant_admin)
    assert not crossed.allowed and crossed.reason == "tenant_mismatch"

    expired_admin = Shape(
        name="expired_admin_at_sibling_unit",
        description="a tenant-wide admin membership whose validity window closed yesterday",
        memberships=(_member(SIBLING_UNIT, "admin", valid_until=NOW - timedelta(days=1)),),
    )
    expired = _decision_for(expired_admin)
    assert not expired.allowed and expired.reason == "no_grant", (
        "an expired membership grants nothing, tenant-wide role or not"
    )


def test_a_blank_role_gains_nothing_from_the_tenant_wide_path() -> None:
    """Rule 6 holds on Path 1b too, and is reachable there only through a caller mistake.

    ``membership.role`` is ``sa.Text NOT NULL`` with no non-blank ``CHECK``, so
    a blank-role row is storable out-of-band. On this path it can only match if
    a blank string is also placed in ``tenant_wide_roles`` — a caller mistake
    rather than a data one, and exactly the kind that turns a blank column into
    tenant-wide authority. The guard makes it inert; this is what would notice
    if it were removed as redundant.
    """
    blank_role_admin = Shape(
        name="blank_role_at_sibling_unit",
        description="an active membership whose role column is whitespace-only",
        memberships=(_member(SIBLING_UNIT, "   "),),
    )
    decision = _decision_for(blank_role_admin, tenant_wide_roles=frozenset({"   ", "admin"}))
    assert not decision.allowed and decision.reason == "no_grant"


def test_a_tenant_wide_role_is_not_a_grant_of_membership_to_everyone() -> None:
    """Only the enumerated role widens; every other shape is refused as before.

    The risk in a keyword like this is not the role it names but the ones it
    might drag along — a check written as "has any membership and the operation
    is tenant-wide" would permit the coordinator and the student too. So the
    shapes that must *not* move are asserted against the real evaluation with
    the keyword live, rather than inferred from the matrix agreeing with itself.
    """
    for shape_name in ("coordinator_at_sibling_unit", "member_with_no_memberships"):
        decision = _decision_for(SHAPES_BY_NAME[shape_name])
        assert not decision.allowed and decision.reason == "no_grant", (
            f"{shape_name} was admitted by the tenant-wide path; only the roles "
            f"in _TENANT_WIDE_AGGREGATE_ROLES may reach outside their subtree"
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
#:
#: The synthetic path was ``/v1/units/{unit_id}/match-runs`` until card
#: P-MATCH-API landed that route for real, at which point this stopped being a
#: route "nobody added to the matrix" and the completeness check found nothing
#: missing — a control passing because its own probe had become real. The path
#: is therefore one that does not and should not exist. Any future card landing
#: a ``synthetic-commands`` resource has to rename it again, for the same
#: reason.
_SYNTHETIC_ROUTER = '''
from fastapi import APIRouter

router = APIRouter(prefix="/v1/units", tags=["synthetic"])


@router.post("/{unit_id}/synthetic-commands")
def create_synthetic_command(principal: CurrentPrincipal, session: DbSession) -> None:
    """A new command resource that nobody added to the matrix."""
    unit = load_unit_or_404(session, tenant_id=principal.tenant_id, unit_id=unit_id)
    assert_allowed(principal.principal, unit, at=utc_now(), required_roles=_SOME_ROLES)


@router.get("/public-thing")
def public_thing() -> None:
    """A route that takes no principal at all."""
    return None
'''


def test_the_derivation_finds_routes_and_their_authorizers() -> None:
    """The parser reports the method, the prefixed path, and what authorizes it."""
    routes = {route.key: route for route in _routes_in_source(_SYNTHETIC_ROUTER, "synthetic")}

    command = routes[("POST", "/v1/units/{unit_id}/synthetic-commands")]
    assert command.authenticated
    assert command.authorizers == ("assert_allowed",)
    assert command.handler == "create_synthetic_command"

    public = routes[("GET", "/v1/units/public-thing")]
    assert not public.authenticated
    assert public.authorizers == ()


#: A router that authorizes two routes without ever writing a bare
#: ``assert_allowed(...)`` call — the two escape hatches this file's
#: ``_authorize_calls`` used to miss entirely, each isolated on its own route
#: so a regression in either detector fails on a specific, named path rather
#: than on "some cell somewhere".
_SYNTHETIC_ROUTER_INDIRECT_AUTHZ = '''
from fastapi import APIRouter, Depends
import smartmatch_authz as authz

router = APIRouter(prefix="/v1/units", tags=["synthetic"])


@router.post("/{unit_id}/attribute-call")
def create_via_attribute(principal: CurrentPrincipal, session: DbSession) -> None:
    """Authorizes through the module, not the bare imported name."""
    unit = load_unit_or_404(session, tenant_id=principal.tenant_id, unit_id=unit_id)
    authz.assert_allowed(principal.principal, unit, at=utc_now(), required_roles=_ROLES)


@router.post("/{unit_id}/depends-call")
def create_via_depends(
    principal: CurrentPrincipal,
    _authorized: None = Depends(assert_allowed),
) -> None:
    """Authorizes by naming the authorizer as a FastAPI dependency."""
    return None
'''


def test_the_derivation_recognises_an_attribute_call_as_authorizing() -> None:
    """``authz.assert_allowed(...)`` is not invisible just because it is qualified.

    Before ``_authorizer_calls`` also walked :class:`ast.Attribute` calls, a
    route that imported its authorizer's *module* rather than the bare
    name — entirely ordinary Python — authorized every request it handled and
    still reported no authorizer here, which is indistinguishable from a route
    that genuinely authorizes nothing.
    """
    routes = {
        route.key: route
        for route in _routes_in_source(_SYNTHETIC_ROUTER_INDIRECT_AUTHZ, "synthetic")
    }
    route = routes[("POST", "/v1/units/{unit_id}/attribute-call")]
    assert route.authorizers == ("assert_allowed",)


def test_the_derivation_recognises_an_authorizer_named_via_depends() -> None:
    """``Depends(assert_allowed)`` authorizes the request; it must not look exempt.

    FastAPI calls a ``Depends(...)`` argument during dependency resolution,
    before the handler body ever runs — so an authorizer named this way is
    never a direct call inside the handler's own AST. This is the second
    escape hatch named in the finding this file's fix closes.
    """
    routes = {
        route.key: route
        for route in _routes_in_source(_SYNTHETIC_ROUTER_INDIRECT_AUTHZ, "synthetic")
    }
    route = routes[("POST", "/v1/units/{unit_id}/depends-call")]
    assert route.authorizers == ("assert_allowed",)


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
    assert missing == [("POST", "/v1/units/{unit_id}/synthetic-commands")], (
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
        "assert_allowed(principal.principal, unit, at=utc_now(), required_roles=_SOME_ROLES)",
        "pass",
    )
    routes = {route.key: route for route in _routes_in_source(source, "synthetic")}
    unprotected = routes[("POST", "/v1/units/{unit_id}/synthetic-commands")]
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
