"""The class-exercise public router (CE-ROUTERS, ADR-0025 D1/D2/D6/D8).

This track mounts the exercise API surface and nothing else: one route that
answers what a front end needs to know *before* anything exists — which scope
it is talking to, which team numbers the entry screen may offer, and that every
row it will ever see is made up. Every screen the design spec describes needs a
table this track deliberately does not depend on, so those routes belong to the
tracks that build them (CE-WORKSPACE, CE-SIMULATION, CE-INSTRUCTOR).

What is pinned here:

1. **D1 — the scope-absence pair.** The exercise route is mounted under
   ``ProductScope.CLASS_EXERCISE`` and under no other scope, and the composition
   that mounts it is the one the application is built from. A request for it in
   a CBA process is a ``404``, which is the honest shape of "this product does
   not have that route" — not a ``403``, which would confirm it exists.
2. **D2 — the import boundary as a property of the module**, asserted here in
   addition to ``make imports`` so a reader of this file sees the rule without
   opening ``pyproject.toml``: the router imports no authz, no principal
   dependency, and no tenant-scoped repository.
3. **D6 — the withheld field, guarded before any data model exists.** A
   schema walk over the router's own response models *and* over the exported
   OpenAPI document asserts the string ``hidden_true_interests`` appears in
   neither. Written now, while there is nothing to hide, because the guard is
   worth nothing if it arrives with the column it is guarding.
4. **D8 — no numeric score.** No field on any exercise response is named like
   a score, percentage, or confidence.
5. **The boot guard.** Under ``CLASS_EXERCISE`` startup constructs no token
   verifier: a process with no login has no token to verify, and building the
   principal machinery anyway would leave it one import away from a handler.
   Under both scopes that *do* have a login the startup sequence is unchanged.

This track closes no row in
``docs/plans/open-questions/class-exercise-open-questions.md`` and no row there
gates it. The team range 1–6 is not an open question: it is stated in
``docs/product/class-exercise-requirements.md`` ("Getting in").
"""

from __future__ import annotations

import ast
import asyncio
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel
from smartmatch_api.config import Settings
from smartmatch_api.main import CAPABILITY_SCOPED_ROUTERS, lifespan, routers_for
from smartmatch_api.routers import exercise_public
from smartmatch_domain.exercise import EXERCISE_TEAM_NUMBERS, EXERCISE_WITHHELD_FIELDS
from smartmatch_domain.product_scope import Capability, ProductScope

_ROUTER_SOURCE = Path(exercise_public.__file__)


def _app_for(scope: ProductScope) -> FastAPI:
    """A FastAPI application composed exactly as a process in ``scope`` would be.

    Built from ``routers_for`` rather than by importing ``main.app`` a second
    time: the module-level application is composed once, at import, from the
    settings the process booted with, and re-importing it under a different
    environment would not produce a second answer — it would produce the same
    one with a misleading name.
    """
    app = FastAPI()
    for router in routers_for(Settings(product_scope=scope)):
        app.include_router(router)
    return app


def _paths_under(scope: ProductScope) -> frozenset[str]:
    return frozenset(
        route.path
        for router in routers_for(Settings(product_scope=scope))
        for route in router.routes
        if hasattr(route, "path")
    )


# ---------------------------------------------------------------------------
# D1 — mounted under the exercise capability, and under nothing else
# ---------------------------------------------------------------------------


def test_the_router_is_declared_under_the_class_exercise_capability() -> None:
    """The declaration table is where the mounting decision is readable."""
    declared = {
        capability
        for router, capability in CAPABILITY_SCOPED_ROUTERS
        if router is exercise_public.router
    }
    assert declared == {Capability.CLASS_EXERCISE}


def test_no_other_router_rides_the_class_exercise_capability() -> None:
    """Nothing CBA-shaped may be smuggled in on the new flag.

    The exercise's own routers ride it, and each track adds one: CE-ROUTERS
    this module's, CE-WORKSPACE ``exercise_workspace``. The claim is that
    *every* rider is an exercise router — asserted by where the router lives
    rather than by a list of objects, so a track that adds one cannot make the
    check pass by editing the list it fails.
    """
    riders = [
        router
        for router, capability in CAPABILITY_SCOPED_ROUTERS
        if capability is Capability.CLASS_EXERCISE
    ]
    assert exercise_public.router in riders
    for router in riders:
        prefixes = {route.path for route in router.routes if hasattr(route, "path")}
        assert all(path.startswith("/v1/exercise") for path in prefixes), (
            f"a router serving {sorted(prefixes)} rides Capability.CLASS_EXERCISE"
        )


def test_the_exercise_route_is_mounted_only_under_the_exercise_scope() -> None:
    assert "/v1/exercise" in _paths_under(ProductScope.CLASS_EXERCISE)
    for scope in (ProductScope.CBA, ProductScope.IA_WEST_LEGACY):
        assert "/v1/exercise" not in _paths_under(scope), (
            f"the exercise route must not be mounted under {scope}"
        )


@pytest.mark.parametrize("scope", [ProductScope.CBA, ProductScope.IA_WEST_LEGACY])
def test_the_exercise_route_answers_404_in_a_cba_process(scope: ProductScope) -> None:
    """ADR-0025 D1's other half, now that there is a route to be absent.

    404 and not 403: a 403 would confirm the route exists and is merely
    forbidden. In a CBA process it does not exist.
    """
    with TestClient(_app_for(scope)) as client:
        assert client.get("/v1/exercise").status_code == 404


def test_the_exercise_scope_mounts_this_route_and_nothing_authenticated() -> None:
    """An equality over the whole exercise surface, extended by each track.

    CE-WORKSPACE added the team-workspace paths
    (``routers/exercise_workspace.py``; its third, the team-addressed reset,
    moved behind the instructor passcode by the owner ruling of 2026-09-19)
    and CE-INSTRUCTOR the instructor page
    (``routers/exercise_instructor.py``, two routers so the passcode session
    can gate one of them). CE-MATCHING-API added the six matching routes
    (``routers/exercise_matching.py``), every one of them under
    ``/v1/exercise/workspaces/current`` because every one of them is addressed
    by the workspace cookie rather than by an identifier a client supplies.
    They are listed here rather than the assertion being loosened to a
    containment, because what this test is for is catching a route that appears
    without anybody naming it.
    """
    assert _paths_under(ProductScope.CLASS_EXERCISE) == frozenset(
        {
            "/v1/exercise",
            "/v1/exercise/workspaces",
            "/v1/exercise/workspaces/current",
            "/v1/exercise/instructor/login",
            "/v1/exercise/instructor/logout",
            "/v1/exercise/instructor/datasets",
            "/v1/exercise/instructor/datasets/{dataset_id}",
            "/v1/exercise/instructor/datasets/{dataset_id}/repoint",
            "/v1/exercise/instructor/events/{event_key}/unlock",
            "/v1/exercise/instructor/workspaces",
            "/v1/exercise/instructor/workspaces/{team_number}",
            "/v1/exercise/instructor/workspaces/{team_number}/reset",
            "/v1/exercise/instructor/refresh-all",
            "/v1/exercise/workspaces/current/events",
            "/v1/exercise/workspaces/current/events/{event_key}/list",
            "/v1/exercise/workspaces/current/events/{event_key}/list.csv",
            "/v1/exercise/workspaces/current/events/{event_key}/settings",
            "/v1/exercise/workspaces/current/events/{event_key}/settings/compare",
            "/v1/exercise/workspaces/current/events/{event_key}/settings/{name}",
            # CE-RESULTS-API added the results lock and one-run route, the
            # asking choice and the one refresh (design spec §9-§13), under the
            # same prefix and for the same reason.
            "/v1/exercise/workspaces/current/events/{event_key}/results",
            "/v1/exercise/workspaces/current/asking-choice",
            "/v1/exercise/workspaces/current/refresh",
        }
    )


# ---------------------------------------------------------------------------
# The response
# ---------------------------------------------------------------------------


def test_the_route_answers_without_any_credential() -> None:
    with TestClient(_app_for(ProductScope.CLASS_EXERCISE)) as client:
        response = client.get("/v1/exercise")
    assert response.status_code == 200
    assert response.json() == {
        "scope": "class_exercise",
        "team_numbers": [1, 2, 3, 4, 5, 6],
        "synthetic_data": True,
    }


def test_the_team_numbers_are_the_requirements_range() -> None:
    """The requirements row "Getting in": *a team enters its team number (1–6)*."""
    assert EXERCISE_TEAM_NUMBERS == (1, 2, 3, 4, 5, 6)


def test_the_response_model_forbids_extra_fields() -> None:
    assert exercise_public.ExerciseScopeFacts.model_config.get("extra") == "forbid"


# ---------------------------------------------------------------------------
# D2 — the import boundary, as a property of the module's own source
# ---------------------------------------------------------------------------

#: What an exercise router may not import, and what each one would drag in.
_FORBIDDEN_IMPORTS = (
    "smartmatch_authz",
    "smartmatch_api.dependencies",
    "smartmatch_api.routers.auth",
    "smartmatch_api.units",
    "smartmatch_persistence",
)


def test_the_router_imports_nothing_principal_or_tenant_shaped() -> None:
    """ADR-0025 D2, read off the module rather than trusted to a config file."""
    tree = ast.parse(_ROUTER_SOURCE.read_text(encoding="utf-8"))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            imported.add(node.module)

    offenders = sorted(
        name
        for name in imported
        for forbidden in _FORBIDDEN_IMPORTS
        if name == forbidden or name.startswith(f"{forbidden}.")
    )
    assert offenders == [], f"exercise router imports a forbidden module: {offenders}"


def test_no_handler_takes_a_principal() -> None:
    """There is no principal to take: the exercise has no login (ADR-0025 D1)."""
    tree = ast.parse(_ROUTER_SOURCE.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            continue
        for arg in (*node.args.args, *node.args.kwonlyargs):
            annotation = arg.annotation
            name = annotation.id if isinstance(annotation, ast.Name) else None
            assert name != "CurrentPrincipal", f"{node.name} takes a principal"


# ---------------------------------------------------------------------------
# D6 — hidden true interests appear nowhere a client can see
# ---------------------------------------------------------------------------


def _schema_strings(schema: Any) -> list[str]:
    """Every string anywhere in a JSON-schema-shaped structure, keys included."""
    if isinstance(schema, dict):
        return [text for key, value in schema.items() for text in [key, *_schema_strings(value)]]
    if isinstance(schema, list):
        return [text for item in schema for text in _schema_strings(item)]
    if isinstance(schema, str):
        return [schema]
    return []


def _exercise_response_models() -> list[type[BaseModel]]:
    return [
        value
        for value in vars(exercise_public).values()
        if isinstance(value, type) and issubclass(value, BaseModel) and value is not BaseModel
    ]


def test_the_withheld_field_names_are_declared() -> None:
    assert "hidden_true_interests" in EXERCISE_WITHHELD_FIELDS


def test_no_withheld_field_appears_in_any_exercise_response_model() -> None:
    """ADR-0025 D6, written before the column it guards exists."""
    models = _exercise_response_models()
    assert models, "expected at least one response model to walk"
    for model in models:
        strings = _schema_strings(model.model_json_schema())
        for withheld in EXERCISE_WITHHELD_FIELDS:
            assert withheld not in strings, f"{model.__name__} exposes {withheld}"


def test_no_withheld_field_appears_in_the_exported_openapi_document() -> None:
    """The contract clients are generated from says nothing about it either."""
    document = Path("contracts/openapi/smartmatch.json").read_text(encoding="utf-8")
    for withheld in EXERCISE_WITHHELD_FIELDS:
        assert withheld not in document


def test_the_exercise_scope_openapi_document_withholds_it_too() -> None:
    """Belt and braces: the document a *class-exercise* process would serve.

    The committed contract is exported under the default scope, where the
    exercise routes are absent — so a walk over it alone would pass even if the
    field were on every exercise model. This walks the surface that actually
    carries them.
    """
    document = _app_for(ProductScope.CLASS_EXERCISE).openapi()
    strings = _schema_strings(document)
    for withheld in EXERCISE_WITHHELD_FIELDS:
        assert withheld not in strings


# ---------------------------------------------------------------------------
# D8 — no numeric score reaches a class participant
# ---------------------------------------------------------------------------

_SCORE_SHAPED = ("score", "percent", "confidence", "probability", "weight")


def test_no_exercise_response_field_is_named_like_a_score() -> None:
    for model in _exercise_response_models():
        for field_name in model.model_fields:
            lowered = field_name.lower()
            assert not any(word in lowered for word in _SCORE_SHAPED), (
                f"{model.__name__}.{field_name} is named like a score (ADR-0025 D8)"
            )


# ---------------------------------------------------------------------------
# The boot guard — a process with no login builds no token verifier
# ---------------------------------------------------------------------------


@pytest.fixture
def booted(monkeypatch: pytest.MonkeyPatch) -> Iterator[Callable[[str], FastAPI]]:
    """Run the real ``lifespan`` under a chosen scope and hand back its state.

    ``get_settings`` is cached process-wide on purpose — settings are read and
    validated once at startup — so the cache is cleared around each call rather
    than a second settings object being smuggled into ``lifespan``. The
    application under test is a bare :class:`FastAPI`, so nothing here mutates
    the module-level one the rest of the suite shares.
    """
    from smartmatch_api import config

    def boot(scope: str) -> FastAPI:
        monkeypatch.setenv("SMARTMATCH_PRODUCT_SCOPE", scope)
        config.get_settings.cache_clear()
        app = FastAPI()

        async def run() -> None:
            async with lifespan(app):
                pass

        asyncio.run(run())
        return app

    config.get_settings.cache_clear()
    yield boot
    config.get_settings.cache_clear()


def test_startup_under_class_exercise_builds_no_token_verifier(
    booted: Callable[[str], FastAPI],
) -> None:
    """A product with no login has nothing to verify a token for.

    The session factory is still built — the exercise will have its own tables —
    and nothing queries it here.
    """
    app = booted("class_exercise")
    assert getattr(app.state, "token_verifier", None) is None
    assert app.state.product_scope is ProductScope.CLASS_EXERCISE
    assert app.state.enabled_capabilities == frozenset({Capability.CLASS_EXERCISE})
    assert app.state.session_factory is not None


@pytest.mark.parametrize("scope", ["cba", "ia_west_legacy"])
def test_startup_under_a_login_scope_is_unchanged(
    booted: Callable[[str], FastAPI], scope: str
) -> None:
    app = booted(scope)
    assert app.state.token_verifier is not None
    assert app.state.session_factory is not None
