"""The results routes: CSRF, the cookie, D6/D8 and the wiring.

Split by topic from ``tests/unit/test_exercise_results_router.py``; see
``test_exercise_results_rules.py`` for what the split files pin, in order.
"""

from __future__ import annotations

import ast
import uuid
from collections.abc import Mapping
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel
from smartmatch_api.config import Settings
from smartmatch_api.exercise_dependencies import (
    RefreshCandidate,
    TeamResultsState,
)
from smartmatch_api.main import CAPABILITY_SCOPED_ROUTERS, routers_for
from smartmatch_api.routers import (
    exercise_instructor_refresh,
    exercise_results,
)
from smartmatch_domain.exercise import EXERCISE_WITHHELD_FIELDS
from smartmatch_domain.exercise.simulation import (
    SimulationCoefficients,
    SimulationProfile,
)
from smartmatch_domain.product_scope import Capability, ProductScope

from tests.unit.exercise_results_router.support import (
    _ASKING,
    _BASE,
    _DATASET_ID,
    _FINAL_BODY,
    _HEADER,
    _INSTRUCTOR_SOURCE,
    _REFRESH,
    _REFRESH_ALL,
    _RESULTS,
    _ROUTER_SOURCE,
    _ROWS,
    _RUN_SOURCE,
    _TRACK_MODULES,
    _TRACK_SOURCES,
    _exercise_app,
    _Fakes,
    _settings,
)

# ---------------------------------------------------------------------------
# CSRF and the cookie
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("path", [_RESULTS, _ASKING, _REFRESH])
def test_a_state_changing_request_without_the_exercise_header_is_refused(
    client: TestClient, path: str
) -> None:
    response = client.post(path, json={})

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "exercise_request_header_required"


def test_the_read_routes_need_no_exercise_header(client: TestClient) -> None:
    assert client.get(_ASKING).status_code == 200


def test_without_a_cookie_every_route_asks_for_a_team_number(fakes: _Fakes) -> None:
    with TestClient(_exercise_app(fakes)) as anonymous:
        for method, path in (
            ("post", _RESULTS),
            ("get", f"{_BASE}/events/round-one/results"),
            ("get", _ASKING),
            ("post", _ASKING),
            ("post", _REFRESH),
        ):
            response = getattr(anonymous, method)(path, headers=_HEADER)
            assert response.status_code == 401, f"{method} {path}"
            assert response.json()["error"]["code"] == "exercise_workspace_required"


def test_every_refusal_code_is_the_exercises_own(
    fakes: _Fakes, client: TestClient, confirmed: SimulationCoefficients
) -> None:
    """A no-login product answering ``unauthenticated`` would be naming a login."""
    refusals = [
        client.post(_RESULTS, json={}, headers=_HEADER),
        client.post(f"{_BASE}/events/nope/results", json={}, headers=_HEADER),
        client.post(_ASKING, json={"choice": "nope"}, headers=_HEADER),
        client.post(_REFRESH, json={}, headers=_HEADER),
        client.get(f"{_BASE}/events/nope/results"),
    ]

    for response in refusals:
        assert response.status_code >= 400
        code = response.json()["error"]["code"]
        assert code.startswith("exercise_"), code


# ---------------------------------------------------------------------------
# D6 / D8 — what a response may never carry
# ---------------------------------------------------------------------------

#: Names that must appear on no response model here. The addressing four are the
#: workspace router's, restated because these routes are reached with the same
#: cookie.
_FORBIDDEN_RESPONSE_FIELDS = frozenset(
    {"seed", "token", "workspace_token", "workspace_token_hash", "workspace_id", "dataset_id"}
    | set(EXERCISE_WITHHELD_FIELDS)
)

#: ADR-0025 D8: counts of people and of chairs. No number that reads as a score.
_SCORE_SHAPED = ("score", "percent", "confidence", "probability", "likelihood", "share")

#: How the OpenAPI document spells a reference to a component schema.
_SCHEMA_PREFIX = "#/components/schemas/"


def _models_in_modules() -> list[type[BaseModel]]:
    found: list[type[BaseModel]] = []
    for module in _TRACK_MODULES:
        found.extend(
            value
            for value in vars(module).values()
            if isinstance(value, type) and issubclass(value, BaseModel) and value is not BaseModel
        )
    return found


def test_the_modules_actually_declare_models() -> None:
    """A walk over an empty list is a green check that means nothing."""
    assert len(_models_in_modules()) >= 7


def test_no_response_model_carries_a_withheld_or_addressing_field() -> None:
    for model in _models_in_modules():
        offenders = sorted(set(model.model_fields) & _FORBIDDEN_RESPONSE_FIELDS)
        assert offenders == [], f"{model.__name__} publishes {offenders}"


def test_no_response_model_carries_a_score_shaped_field() -> None:
    for model in _models_in_modules():
        for field_name in model.model_fields:
            assert not any(shape in field_name.lower() for shape in _SCORE_SHAPED), (
                f"{model.__name__}.{field_name} reads as a score; ADR-0025 D8"
            )


def test_the_model_walk_reads_every_module_the_source_walks_read() -> None:
    """The two lists are one list, and this is what keeps them one (round 1, (a))."""
    assert {Path(module.__file__ or "") for module in _TRACK_MODULES} == set(_TRACK_SOURCES)
    assert len(_TRACK_SOURCES) == 5


def test_no_handler_docstring_names_the_withheld_column() -> None:
    """FastAPI publishes a docstring as an operation description (ADR-0025 D6)."""
    docstrings: list[str] = []
    for source_file in (_ROUTER_SOURCE, _INSTRUCTOR_SOURCE):
        tree = ast.parse(source_file.read_text(encoding="utf-8"))
        docstrings.extend(
            ast.get_docstring(node) or ""
            for node in ast.walk(tree)
            if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)
        )
    assert docstrings, "the walk found no handlers"
    for withheld in EXERCISE_WITHHELD_FIELDS:
        offenders = [text for text in docstrings if withheld in text]
        assert offenders == [], f"a handler docstring names {withheld}"


def _schema_names_in(node: object) -> set[str]:
    """Every ``#/components/schemas/<name>`` reference anywhere under ``node``."""
    found: set[str] = set()
    if isinstance(node, dict):
        reference = node.get("$ref")
        if isinstance(reference, str) and reference.startswith(_SCHEMA_PREFIX):
            found.add(reference.removeprefix(_SCHEMA_PREFIX))
        for value in node.values():
            found |= _schema_names_in(value)
    elif isinstance(node, list):
        for item in node:
            found |= _schema_names_in(item)
    return found


def _schemas_reachable_from_exercise_paths(document: Mapping[str, object]) -> set[str]:
    """Every schema an exercise route can actually publish, transitively.

    Review round 1, F9. The earlier walk filtered on the models *this file's
    modules declare*, which is the set it is easiest to keep clean and the set
    least likely to be the problem: a nested model declared elsewhere, a shared
    envelope, or a model pulled in by a ``$ref`` two levels down would have been
    skipped in silence. What a client sees is the transitive closure from the
    exercise paths, so that is what is checked.

    Followed to a fixed point rather than one level deep, because a response
    model's field can be a model whose field is a model.
    """
    paths = document.get("paths", {})
    assert isinstance(paths, dict)
    reachable = set()
    for path, operations in paths.items():
        if isinstance(path, str) and path.startswith("/v1/exercise"):
            reachable |= _schema_names_in(operations)

    schemas = document.get("components", {})
    assert isinstance(schemas, dict)
    declared = schemas.get("schemas", {})
    assert isinstance(declared, dict)
    while True:
        grown = set(reachable)
        for name in reachable:
            grown |= _schema_names_in(declared.get(name, {}))
        if grown == reachable:
            return reachable & set(declared)
        reachable = grown


def test_the_served_exercise_contract_names_neither_either() -> None:
    """The models could be clean and the document not, if a route grew a parameter.

    Widened in review round 1 (F9) from "the models this file's modules declare"
    to **every schema an exercise path can reach**, transitively. The narrow
    version could not see a nested model, a shared envelope, or anything a
    ``$ref`` pulled in from another track's module — and those are the ones
    nobody is looking at.
    """
    app = FastAPI()
    for router in routers_for(_settings()):
        app.include_router(router)
    document = app.openapi()
    for withheld in EXERCISE_WITHHELD_FIELDS:
        assert withheld not in str(document), f"{withheld} appears in the exercise contract"

    reachable = _schemas_reachable_from_exercise_paths(document)
    ours = {model.__name__ for model in _models_in_modules()}
    schemas = document["components"]["schemas"]  # type: ignore[index]

    assert ours & reachable, "none of this track's models reached the contract"
    assert len(reachable) >= len(ours), (
        "the reachable set must be at least this track's own models; "
        "a walk that shrank below them has stopped following references"
    )

    # **D8 is walked over everything reachable**, because "no number that ranks
    # a person" is a property of the whole exercise surface: the instructor's
    # screen is on the same projector as the teams'.
    for name in sorted(reachable):
        for field_name in schemas[name].get("properties", {}):
            assert not any(shape in field_name.lower() for shape in _SCORE_SHAPED), (
                f"{name}.{field_name} reads as a score; ADR-0025 D8"
            )

    # **The addressing fields are walked over this track's own models only**,
    # and that is a real exemption rather than a narrower net. Two instructor
    # models legitimately publish `dataset_id` — `DatasetView` and
    # `TeamSummaryView`, both of them the instructor's own screen, and she is
    # the person who uploaded the file and the person who can already see which
    # file each team is in. Asserting the team routes' rule over them would be
    # this file deciding another track's contract. The withheld columns are
    # still checked over the **whole** document, by the `str(document)` walk
    # above.
    for name in sorted(reachable & ours):
        offenders = sorted(set(schemas[name].get("properties", {})) & _FORBIDDEN_RESPONSE_FIELDS)
        assert offenders == [], f"{name} publishes {offenders}"


def test_the_reachability_walk_finds_more_than_this_tracks_own_models() -> None:
    """A closure that returned only what it started from would prove nothing."""
    app = FastAPI()
    for router in routers_for(_settings()):
        app.include_router(router)

    reachable = _schemas_reachable_from_exercise_paths(app.openapi())
    ours = {model.__name__ for model in _models_in_modules()}

    assert reachable - ours, (
        "the walk found only this track's own models, so it is not following "
        "references into the other exercise tracks' schemas"
    )


def test_a_response_body_carries_no_withheld_value(
    fakes: _Fakes, client: TestClient, confirmed: SimulationCoefficients
) -> None:
    """The walks above read declarations; this reads what actually went out."""
    fakes.unlock("round-one")
    client.post(_RESULTS, json=_FINAL_BODY, headers=_HEADER)
    client.post(_ASKING, json={"choice": "required"}, headers=_HEADER)

    bodies = "".join(
        response.text
        for response in (
            client.get(f"{_BASE}/events/round-one/results"),
            client.get(_ASKING),
            client.post(_REFRESH, json={}, headers=_HEADER),
        )
    )

    for row in _ROWS:
        for term in row.hidden_true_interests:
            if term in {"analytics", "brand", "outreach"} and term in (row.stated_interests or ()):
                continue  # a term the row also states is not withheld
            assert f'"{term}"' not in bodies, f"{term} left the server"


def test_a_team_seed_never_reaches_a_printed_form() -> None:
    """Review round 1, F4: a ``repr`` is what a log line and an assertion print.

    A seed is not a credential — it forges nothing, and the workspace token is
    derived from the id under a separate secret. What it *is* is the whole of
    what makes one team's results that team's: two teams handed the same seed
    see the same answers, which this file's own
    ``test_the_same_request_twice_gives_the_same_panels`` relies on. So a seed
    in a shared log or on a projector is an invitation to compare notes with a
    number instead of with a screen.

    ``RefreshCandidate`` matters more sharply than ``TeamResultsState``:
    "refresh all" builds a list of them, so one ``repr`` of that list would
    print every team's seed at once.
    """
    seed = 123_456_789
    state = TeamResultsState(seed=seed, asking_choice="required", refreshed_at=None)
    candidate = RefreshCandidate(
        workspace_id=uuid.uuid4(),
        dataset_id=_DATASET_ID,
        team_number=4,
        asking_choice="required",
        seed=seed,
    )

    assert str(seed) not in repr(state)
    assert str(seed) not in repr([candidate])
    assert state.seed == seed, "the value is still there to be read deliberately"
    assert candidate.seed == seed


def test_a_simulation_profile_never_prints_its_true_interests() -> None:
    """A ``repr`` is what a log line and an assertion message publish."""
    profile = SimulationProfile(
        profile_no=1, major="Alpha", true_interests=frozenset({"a-withheld-term"})
    )

    assert "a-withheld-term" not in repr(profile)


def test_no_module_in_this_track_logs_anything(
    fakes: _Fakes, caplog: pytest.LogCaptureFixture, client: TestClient
) -> None:
    """The one log line on these paths is the repository's, and it names a constraint."""
    for source_file in _TRACK_SOURCES:
        source = source_file.read_text(encoding="utf-8")
        assert "getLogger" not in source, f"{source_file.name} logs; D6 covers log lines"


def _mounted_exercise_paths() -> frozenset[str]:
    """Every exercise path this scope actually serves, read off the contract.

    **Not ``app.routes``**, and that is a correction rather than a preference.
    On this FastAPI version ``include_router`` leaves an ``_IncludedRouter``
    wrapper in ``app.routes`` whose ``path`` is ``None``, so a walk that filtered
    on ``route.path.startswith(...)`` matched **nothing** and passed over an
    empty set — a guard that cannot fail. The OpenAPI document's ``paths`` is the
    published surface and is what a client can actually address, so it is what
    the addressing rule is checked against.
    """
    app = FastAPI()
    for router in routers_for(_settings()):
        app.include_router(router)
    return frozenset(app.openapi().get("paths", {}))


def test_the_exercise_paths_carry_no_workspace_identifier() -> None:
    """The cookie is the whole of the addressing: no id is accepted anywhere."""
    team_paths = {
        path
        for path in _mounted_exercise_paths()
        if path.startswith("/v1/exercise/workspaces/current")
    }

    assert len(team_paths) >= 3, "the walk found none of this track's paths"
    for path in sorted(team_paths):
        for forbidden in ("{workspace_id}", "{token}", "{team_number}", "{dataset_id}"):
            assert forbidden not in path, f"{path} accepts an identifier from the client"


def test_this_tracks_own_paths_are_all_present_and_cookie_addressed() -> None:
    """Named, so a route that quietly moved is a failure rather than a surprise."""
    assert _mounted_exercise_paths() >= {
        "/v1/exercise/workspaces/current/events/{event_key}/results",
        "/v1/exercise/workspaces/current/asking-choice",
        "/v1/exercise/workspaces/current/refresh",
        "/v1/exercise/instructor/refresh-all",
    }


# ---------------------------------------------------------------------------
# Wiring
# ---------------------------------------------------------------------------


def test_both_routers_are_declared_under_the_class_exercise_capability() -> None:
    for module in (exercise_results, exercise_instructor_refresh):
        declared = {
            capability
            for router, capability in CAPABILITY_SCOPED_ROUTERS
            if router is module.router
        }
        assert declared == {Capability.CLASS_EXERCISE}, module.__name__


def test_the_routes_answer_404_in_a_cba_process() -> None:
    app = FastAPI()
    for router in routers_for(Settings(product_scope=ProductScope.CBA)):
        app.include_router(router)
    with TestClient(app) as cba:
        assert cba.post(_RESULTS, json={}).status_code == 404
        assert cba.post(_REFRESH_ALL).status_code == 404


def test_the_routers_import_no_persistence_authz_or_principal_machinery() -> None:
    """``make imports`` says this too; a reader of this file should not have to look."""
    for source_file in _TRACK_SOURCES:
        tree = ast.parse(source_file.read_text(encoding="utf-8"))
        imported: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module is not None:
                imported.add(node.module)
        for forbidden in (
            "smartmatch_authz",
            "smartmatch_persistence",
            "smartmatch_api.dependencies",
            "smartmatch_api.routers.auth",
            "sqlalchemy",
            "pandas",
        ):
            assert not any(
                name == forbidden or name.startswith(f"{forbidden}.") for name in imported
            ), f"{source_file.name} imports {forbidden}"


def test_only_the_models_module_reaches_the_simulation_loader() -> None:
    """The withheld column has one door on the router side, and it is named.

    ``exercise_results_run.run_the_rule`` calls ``load_simulation_profiles`` to
    hand rows to design spec §11's rule; nothing else in this track does, and the
    instructor half does not touch it at all — its card copy happens inside the
    repository.
    """
    callers = [
        source_file.name
        for source_file in _TRACK_SOURCES
        if "load_simulation_profiles(" in source_file.read_text(encoding="utf-8")
    ]

    assert callers == [_RUN_SOURCE.name]


def test_the_instructor_half_is_a_module_of_its_own_and_both_stay_under_the_ceiling() -> None:
    """Review carry-over from PR #188: ``exercise_instructor.py`` may not grow."""
    for source_file in _TRACK_SOURCES:
        lines = len(source_file.read_text(encoding="utf-8").splitlines())
        assert lines <= 800, f"{source_file.name} is {lines} lines"
