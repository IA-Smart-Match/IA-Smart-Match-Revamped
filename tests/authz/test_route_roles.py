"""The role-set ledger: which mounted routes require which roles, as data.

The plan flags a route's ``required_roles`` set as a decision a human must
own, not one a test should merely infer from whatever the code happens to say
today. So this file is a ledger rather than a derivation: a literal table,
readable without following any machinery, naming every mounted route this
track is responsible for and the exact role set it gates on — or ``None``,
stated explicitly, for a route that requires nothing beyond authentication.
Widening or narrowing a role set in the code changes what this table
disagrees with, and the disagreement is the point: a role-set change should
fail a test and force whoever made it to update this ledger on purpose,
rather than shipping as a silent diff in ``job_authz.py`` or ``imports.py``.

## Relationship to ``tests/authz/test_policy_matrix.py``

That file is the authority on *behavior*: for every route x principal shape,
it runs the real authorizer and asserts permit/deny and the exact reason
code, and it derives the route table from source so a brand-new operation
with no coverage at all fails loudly. This file does not attempt any of that
— it would only be a second, weaker copy of it. What this file adds is a
single place a reviewer can read top to bottom and answer "what role can call
this route, right now" without following AST-derivation code, and it pins the
role sets as **literal** values rather than references to the constants
themselves, so that a change to ``JOB_OVERSIGHT_ROLES`` or ``_IMPORT_ROLES``
is a genuine comparison this file can fail on — not a reference that quietly
moved together with the code it was supposed to be checking.

## Why ``GET /v1/me`` has no role set

``routers/me.py`` authorizes nothing beyond authentication: there is no path
parameter naming a tenant, unit, or other account for a role check to be
scoped against, and every field in its response is keyed by the caller's own
verified subject (see that module's docstring). ``None`` in the ledger below
records that decision explicitly, the same way ``UNAUTHENTICATED_ROUTES`` in
``test_policy_matrix.py`` explicitly records why a route needs no principal
at all, rather than leaving either kind of route to look like an oversight.
"""

from __future__ import annotations

import ast
import inspect

import pytest
from smartmatch_api import job_authz
from smartmatch_api.routers import imports as imports_router
from smartmatch_api.routers import me as me_router
from smartmatch_api.routers import review as review_router

#: The three role sets every gated route in this ledger currently reads from,
#: written as literals rather than as ``job_authz.JOB_OVERSIGHT_ROLES`` /
#: ``imports_router._IMPORT_ROLES`` / ``review_router._REVIEW_ROLES``. A
#: literal is what makes :func:`test_job_oversight_roles_matches_the_live_constant`,
#: :func:`test_import_roles_matches_the_live_constant`, and
#: :func:`test_review_roles_matches_the_live_constant` real comparisons: an
#: alias to the constant would still be equal to itself after the constant
#: changed underneath it, and the drift this ledger exists to catch would pass
#: silently.
_JOB_OVERSIGHT = frozenset({"admin", "coordinator"})
_IMPORT = frozenset({"admin", "coordinator"})
_REVIEW = frozenset({"admin", "coordinator"})

#: method, path -> the role set that route requires, or ``None`` when the
#: route requires only authentication and nothing further. Every route this
#: track (T5) is responsible for is listed, whether it was authored by this
#: track (``GET /v1/me``) or already existed (the four job operations and
#: the import command) — a ledger that only named the new route would not be
#: able to tell "this route's roles are unchanged" from "nobody looked".
ROUTE_ROLE_LEDGER: dict[tuple[str, str], frozenset[str] | None] = {
    ("GET", "/v1/jobs/{job_id}"): _JOB_OVERSIGHT,
    ("GET", "/v1/jobs/{job_id}/events"): _JOB_OVERSIGHT,
    ("POST", "/v1/jobs/{job_id}/redrive"): _JOB_OVERSIGHT,
    ("POST", "/v1/jobs/{job_id}/abandon"): _JOB_OVERSIGHT,
    ("POST", "/v1/units/{unit_id}/imports"): _IMPORT,
    ("POST", "/v1/review-items/{review_item_id}/decision"): _REVIEW,
    ("GET", "/v1/me"): None,
}


def test_job_oversight_roles_matches_the_live_constant() -> None:
    """A widened or narrowed ``JOB_OVERSIGHT_ROLES`` must fail here.

    Covers all four job operations at once: they share one constant by
    construction (``job_authz.py``'s own docstring), so one comparison is
    enough — and is the whole point of that sharing.
    """
    assert job_authz.JOB_OVERSIGHT_ROLES == _JOB_OVERSIGHT, (
        f"job_authz.JOB_OVERSIGHT_ROLES is now {sorted(job_authz.JOB_OVERSIGHT_ROLES)}; "
        f"this ledger still expects {sorted(_JOB_OVERSIGHT)} for the four job "
        f"operations. A role-set change is a decision a human must own — update "
        f"ROUTE_ROLE_LEDGER and _JOB_OVERSIGHT deliberately if the change is intended."
    )


def test_import_roles_matches_the_live_constant() -> None:
    """A widened or narrowed ``_IMPORT_ROLES`` must fail here."""
    assert imports_router._IMPORT_ROLES == _IMPORT, (
        f"imports.py's _IMPORT_ROLES is now {sorted(imports_router._IMPORT_ROLES)}; "
        f"this ledger still expects {sorted(_IMPORT)} for POST "
        f"/v1/units/{{unit_id}}/imports. Update ROUTE_ROLE_LEDGER and _IMPORT "
        f"deliberately if the change is intended."
    )


def test_review_roles_matches_the_live_constant() -> None:
    """A widened or narrowed ``_REVIEW_ROLES`` must fail here."""
    assert review_router._REVIEW_ROLES == _REVIEW, (
        f"review.py's _REVIEW_ROLES is now {sorted(review_router._REVIEW_ROLES)}; "
        f"this ledger still expects {sorted(_REVIEW)} for POST "
        f"/v1/review-items/{{review_item_id}}/decision. Update ROUTE_ROLE_LEDGER "
        f"and _REVIEW deliberately if the change is intended."
    )


def test_every_job_route_shares_the_same_role_set_in_the_ledger() -> None:
    """The ledger itself records the four job operations as one set, not four.

    A ledger that let one of the four drift to its own literal frozenset would
    stop reflecting ``job_authz``'s "one set for all four operations" design
    without any test noticing — this pins that the ledger's own rows agree
    with each other, on top of agreeing with the code.

    Compared by identity (``is``), not value: ``_IMPORT`` currently holds the
    same two roles as ``_JOB_OVERSIGHT`` and ``==`` would conflate the two
    sets, which would let ``POST /v1/units/{unit_id}/imports`` masquerade as a
    fifth job route the day this test is read quickly rather than run.
    """
    job_routes = {
        ("GET", "/v1/jobs/{job_id}"),
        ("GET", "/v1/jobs/{job_id}/events"),
        ("POST", "/v1/jobs/{job_id}/redrive"),
        ("POST", "/v1/jobs/{job_id}/abandon"),
    }
    assert {
        key for key, roles in ROUTE_ROLE_LEDGER.items() if roles is _JOB_OVERSIGHT
    } == job_routes


@pytest.mark.parametrize(
    ("method", "path"),
    sorted(key for key, roles in ROUTE_ROLE_LEDGER.items() if roles is None),
)
def test_an_auth_only_route_calls_no_authorizer(method: str, path: str) -> None:
    """``None`` in the ledger is a claim about the code, checked against it.

    Only ``GET /v1/me`` is auth-only today, so this runs once — but it is
    written to cover every ``None`` row the ledger ever grows, rather than
    hard-coding the one route that happens to qualify now. A call to
    ``assert_allowed``, ``evaluate``, or an ``authorize_*``/``_authorize*``
    helper appearing in the handler later means a role gate was added without
    the ledger's ``None`` being revisited — the same silent-widening this file
    exists to catch, in the direction of a route *gaining* a gate rather than
    changing one it already had.
    """
    assert (method, path) == ("GET", "/v1/me"), (
        f"an auth-only route was added to the ledger ({method} {path}) that this "
        f"test does not know how to locate the handler for; extend the lookup "
        f"below rather than skip the check"
    )

    source = inspect.getsource(me_router)
    tree = ast.parse(source)
    handler = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == "get_me"
    )
    calls = {
        child.func.id
        for child in ast.walk(handler)
        if isinstance(child, ast.Call) and isinstance(child.func, ast.Name)
    }
    authorizer_calls = {
        name
        for name in calls
        if name in {"assert_allowed", "evaluate"} or name.startswith(("authorize_", "_authorize"))
    }
    assert not authorizer_calls, (
        f"{method} {path}'s handler now calls {sorted(authorizer_calls)}, but "
        f"ROUTE_ROLE_LEDGER records it as auth-only (None). Either state the "
        f"required roles in this ledger, or remove the call if it was added by "
        f"mistake."
    )


def test_the_ledger_covers_exactly_the_routes_this_track_owns() -> None:
    """A row silently dropped, or one nobody meant to add, both fail here."""
    assert set(ROUTE_ROLE_LEDGER) == {
        ("GET", "/v1/jobs/{job_id}"),
        ("GET", "/v1/jobs/{job_id}/events"),
        ("POST", "/v1/jobs/{job_id}/redrive"),
        ("POST", "/v1/jobs/{job_id}/abandon"),
        ("POST", "/v1/units/{unit_id}/imports"),
        ("POST", "/v1/review-items/{review_item_id}/decision"),
        ("GET", "/v1/me"),
    }
