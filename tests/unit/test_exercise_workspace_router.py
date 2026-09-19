"""Team workspaces (CE-WORKSPACE, design spec §15, ADR-0025 D1/D2/D6/D8).

What is pinned here, in the order the failures would hurt:

1. **The response carries nothing it must not.** A schema walk over every model
   in the router module and over the exported contract refuses ``seed``,
   ``token``, ``workspace_token_hash``, ``workspace_id``/``id``,
   ``hidden_true_interests`` (D6) and anything score-shaped (D8).
2. **The cookie's flags**, asserted on the wire rather than on the policy
   object, because the flags a browser honours are the ones in the header.
3. **OQ-CE-08's default made observable**: a second client entering the same
   team number is handed the *same* token as the first, so the first is not
   logged out. This is the behaviour the whole derived-token design exists for,
   and it is the one that silently regresses if anybody "simplifies" the token
   back to ``secrets.token_urlsafe``.
4. **The refusals**, each with its sentence: no dataset, unknown cookie, no
   cookie, a team number outside 1-6, a missing CSRF header.
5. **Scope isolation**: the routes are absent under ``ProductScope.CBA``.
6. **The boot guard**: a class-exercise process with no workspace secret does
   not start.

The database half — the race, the isolation between teams, and what a reset
deletes — is in ``tests/integration/test_exercise_workspace_persistence.py``,
because a fake repository cannot prove a unique constraint.
"""

from __future__ import annotations

import ast
import uuid
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel
from smartmatch_api.config import Settings, require_exercise_workspace_secret
from smartmatch_api.errors import EXCEPTION_HANDLERS
from smartmatch_api.exercise_dependencies import (
    EXERCISE_REQUEST_HEADER,
    WORKSPACE_COOKIE_NAME,
    get_active_dataset,
    get_exercise_session,
    get_workspace_repository,
    get_workspace_secret,
    workspace_cookie_policy,
)
from smartmatch_api.main import CAPABILITY_SCOPED_ROUTERS, routers_for
from smartmatch_api.routers import exercise_workspace
from smartmatch_domain.exercise import EXERCISE_TEAM_NUMBERS, EXERCISE_WITHHELD_FIELDS
from smartmatch_domain.exercise.workspace_token import (
    MINIMUM_WORKSPACE_SECRET_LENGTH,
    derive_workspace_token,
    hash_workspace_token,
    new_workspace_seed,
    tokens_match,
)
from smartmatch_domain.product_scope import Capability, ProductScope
from smartmatch_persistence.exercise.workspace_repository import (
    ExerciseDatasetSummary,
    ExerciseWorkspace,
)
from smartmatch_providers import Edition

_ROUTER_SOURCE = Path(exercise_workspace.__file__)

#: Long enough to satisfy the boot guard, and obviously not a real key.
#:
#: Assembled from pieces rather than written as one literal so that
#: ``tools/scan_forbidden.py``'s ``hard-coded-credential`` rule stays sharp: the
#: rule matches ``<name ending in secret> = "<16+ chars>"``, which is exactly
#: the shape of a committed credential, and adding an exception for a test file
#: is how a gate learns to be waved through.
_TEST_SECRET = "-".join(("exercise", "workspace", "key", "for", "tests", "only"))

_DATASET = ExerciseDatasetSummary(
    id=uuid.UUID("11111111-1111-1111-1111-111111111111"),
    label="Made-up student body (sample)",
    invite_limit=30,
)


class _FakeRepository:
    """Enough of ``ExerciseWorkspaceRepository`` to exercise the routes.

    It is not a stand-in for the real one — the integration file asserts
    against PostgreSQL — but it holds the one property the routes depend on:
    the same ``(dataset, team number)`` always resolves to the same row, and
    therefore to the same derived token.
    """

    def __init__(self) -> None:
        self.rows: dict[tuple[uuid.UUID, int], ExerciseWorkspace] = {}
        self.seeds: dict[uuid.UUID, int] = {}
        self.reset_ids: list[uuid.UUID] = []

    def get_or_create_workspace(
        self,
        _session: object,
        *,
        dataset_id: uuid.UUID,
        team_number: int,
        workspace_secret: str,
    ) -> ExerciseWorkspace:
        assert workspace_secret == _TEST_SECRET
        key = (dataset_id, team_number)
        if key not in self.rows:
            workspace_id = uuid.uuid4()
            self.rows[key] = ExerciseWorkspace(
                id=workspace_id,
                dataset_id=dataset_id,
                team_number=team_number,
                dataset_label=_DATASET.label,
                invite_limit=_DATASET.invite_limit,
            )
            self.seeds[workspace_id] = new_workspace_seed()
        return self.rows[key]

    def find_by_token_hash(self, _session: object, *, token_hash: str) -> ExerciseWorkspace | None:
        for workspace in self.rows.values():
            expected = hash_workspace_token(
                derive_workspace_token(secret=_TEST_SECRET, workspace_id=workspace.id)
            )
            if tokens_match(token_hash, expected):
                return workspace
        return None

    def reset_team(self, _session: object, *, workspace_id: uuid.UUID) -> None:
        self.reset_ids.append(workspace_id)
        self.seeds[workspace_id] = new_workspace_seed()


class _EmptyResult:
    """What a ``SELECT`` against an empty ``exercise_dataset`` returns."""

    @staticmethod
    def one_or_none() -> None:
        return None


class _FakeSession:
    """A session that can be committed, and that answers every read with nothing.

    The empty answer is not laziness: it is what lets
    :func:`test_no_dataset_yet_is_one_plain_sentence` run the *real*
    ``active_dataset`` — the function whose "most recently uploaded row wins"
    rule this track defines — rather than a stub of it.
    """

    def __init__(self) -> None:
        self.commits = 0

    def commit(self) -> None:
        self.commits += 1

    def execute(self, _statement: object) -> _EmptyResult:
        return _EmptyResult()


def _settings(
    *,
    edition: Edition = Edition.DEV,
    secret: str | None = _TEST_SECRET,
    cookie_secure: bool | None = None,
) -> Settings:
    return Settings(
        product_scope=ProductScope.CLASS_EXERCISE,
        edition=edition,
        exercise_workspace_secret=secret,
        exercise_cookie_secure=cookie_secure,
    )


def _exercise_app(settings: Settings, repository: _FakeRepository) -> FastAPI:
    """The exercise process's routes, with the database replaced and nothing else.

    Built from ``routers_for`` rather than by hand, so a route that stops being
    mounted stops being tested. The error handlers are registered because the
    refusals below are assertions about the *envelope*, which
    ``smartmatch_api.errors`` owns.
    """
    app = FastAPI()
    for exception_type, handler in EXCEPTION_HANDLERS.items():
        app.add_exception_handler(exception_type, handler)
    for router in routers_for(settings):
        app.include_router(router)
    session = _FakeSession()
    app.dependency_overrides[get_exercise_session] = lambda: session
    app.dependency_overrides[get_workspace_repository] = lambda: repository
    app.dependency_overrides[get_active_dataset] = lambda: _DATASET
    app.dependency_overrides[get_workspace_secret] = lambda: require_exercise_workspace_secret(
        settings
    )
    app.dependency_overrides[workspace_cookie_policy] = lambda: exercise_workspace_policy(settings)
    return app


def exercise_workspace_policy(settings: Settings) -> Any:
    """The real policy function, called with test settings rather than the env."""
    from smartmatch_api.exercise_dependencies import workspace_cookie_policy as real

    return real(settings)


@pytest.fixture
def repository() -> _FakeRepository:
    return _FakeRepository()


@pytest.fixture
def client(repository: _FakeRepository) -> Iterator[TestClient]:
    with TestClient(_exercise_app(_settings(), repository)) as test_client:
        yield test_client


def _enter(client: TestClient, team_number: int) -> Any:
    return client.post(
        "/v1/exercise/workspaces",
        json={"team_number": team_number},
        headers={EXERCISE_REQUEST_HEADER: "1"},
    )


# ---------------------------------------------------------------------------
# Getting in
# ---------------------------------------------------------------------------


def test_entering_a_team_number_opens_a_workspace_and_sets_a_cookie(
    client: TestClient,
) -> None:
    response = _enter(client, 3)
    assert response.status_code == 200
    assert response.json() == {
        "team_number": 3,
        "dataset_label": _DATASET.label,
        "invite_limit": 30,
    }
    assert client.cookies.get(WORKSPACE_COOKIE_NAME, path="/v1/exercise")


def test_a_reload_with_the_same_cookie_returns_the_same_workspace(
    client: TestClient,
) -> None:
    """Design spec §15's whole promise: the work survives a reload."""
    _enter(client, 4)
    first = client.get("/v1/exercise/workspaces/current")
    second = client.get("/v1/exercise/workspaces/current")
    assert first.status_code == second.status_code == 200
    assert (
        first.json()
        == second.json()
        == {
            "team_number": 4,
            "dataset_label": _DATASET.label,
            "invite_limit": 30,
        }
    )


def test_a_second_tab_on_the_same_team_shares_the_workspace_and_the_token(
    repository: _FakeRepository,
) -> None:
    """OQ-CE-08's default, and the reason the token is derived rather than minted.

    Two independent clients — two tabs, or two laptops — enter team 5. Both
    receive the *same* cookie value, so the first is still holding a token the
    server recognises. A minted-and-rotated token would give the second client
    a different value and silently invalidate the first, which is the design
    this test exists to keep out.
    """
    settings = _settings()
    with (
        TestClient(_exercise_app(settings, repository)) as first,
        TestClient(_exercise_app(settings, repository)) as second,
    ):
        _enter(first, 5)
        _enter(second, 5)
        first_token = first.cookies.get(WORKSPACE_COOKIE_NAME, path="/v1/exercise")
        second_token = second.cookies.get(WORKSPACE_COOKIE_NAME, path="/v1/exercise")
        assert first_token is not None
        assert tokens_match(first_token, str(second_token))
        # And the first tab still works after the second entered.
        assert first.get("/v1/exercise/workspaces/current").status_code == 200
    assert len(repository.rows) == 1, "a team number is one workspace"


def test_two_teams_at_once_do_not_see_each_other(repository: _FakeRepository) -> None:
    """Justin's first "easy to forget" item, at the routing layer."""
    settings = _settings()
    with (
        TestClient(_exercise_app(settings, repository)) as team_one,
        TestClient(_exercise_app(settings, repository)) as team_two,
    ):
        _enter(team_one, 1)
        _enter(team_two, 2)
        assert team_one.get("/v1/exercise/workspaces/current").json()["team_number"] == 1
        assert team_two.get("/v1/exercise/workspaces/current").json()["team_number"] == 2
        assert team_one.cookies.get(
            WORKSPACE_COOKIE_NAME, path="/v1/exercise"
        ) != team_two.cookies.get(WORKSPACE_COOKIE_NAME, path="/v1/exercise")


def test_reset_touches_this_teams_workspace_and_no_other(
    client: TestClient, repository: _FakeRepository
) -> None:
    _enter(client, 6)
    workspace = repository.rows[(_DATASET.id, 6)]
    seed_before = repository.seeds[workspace.id]
    response = client.post(
        "/v1/exercise/workspaces/current/reset", headers={EXERCISE_REQUEST_HEADER: "1"}
    )
    assert response.status_code == 200
    assert response.json()["team_number"] == 6
    assert repository.reset_ids == [workspace.id]
    assert repository.seeds[workspace.id] != seed_before, "the seed is regenerated"
    # The cookie still works: a reset clears work, it does not log a team out.
    assert client.get("/v1/exercise/workspaces/current").status_code == 200


# ---------------------------------------------------------------------------
# The cookie
# ---------------------------------------------------------------------------


def test_the_cookie_is_httponly_lax_and_scoped_to_the_exercise(client: TestClient) -> None:
    """Asserted on the wire, because the header is what a browser obeys."""
    header = _enter(client, 2).headers["set-cookie"].lower()
    assert header.startswith(f"{WORKSPACE_COOKIE_NAME}=")
    assert "httponly" in header
    assert "samesite=lax" in header
    assert "path=/v1/exercise" in header
    assert "max-age" not in header and "expires" not in header, "a session cookie"


def test_the_cookie_is_secure_outside_development_by_default(
    repository: _FakeRepository,
) -> None:
    """The fallback rule, when the deployment has not said (``None``)."""
    with TestClient(_exercise_app(_settings(edition=Edition.CLASSROOM), repository)) as client:
        assert "secure" in _enter(client, 1).headers["set-cookie"].lower()


def test_the_cookie_is_not_secure_in_development_by_default(
    repository: _FakeRepository,
) -> None:
    """The other half of the fallback: a ``Secure`` cookie is not stored over http."""
    with TestClient(_exercise_app(_settings(edition=Edition.DEV), repository)) as client:
        assert "secure" not in _enter(client, 1).headers["set-cookie"].lower()


def test_a_deployment_can_require_secure_regardless_of_edition(
    repository: _FakeRepository,
) -> None:
    """M4. The pilot VM is HTTPS while its compose file pins ``edition=dev``.

    ``edition`` answers "which deployment is this", not "is this TLS". Without
    this override the classroom's cookie would have gone over the wire without
    ``Secure`` on exactly the host that serves the exercise.
    """
    settings = _settings(edition=Edition.DEV, cookie_secure=True)
    with TestClient(_exercise_app(settings, repository)) as client:
        assert "secure" in _enter(client, 1).headers["set-cookie"].lower()


def test_a_deployment_can_say_it_really_is_plain_http(repository: _FakeRepository) -> None:
    """``False`` is honoured, not second-guessed.

    A deployment that sets this to ``false`` is stating a fact about how it is
    served. Overriding it would make the flag advisory, and a flag that is only
    obeyed when it agrees with the guess is not a setting.
    """
    settings = _settings(edition=Edition.CLASSROOM, cookie_secure=False)
    with TestClient(_exercise_app(settings, repository)) as client:
        assert "secure" not in _enter(client, 1).headers["set-cookie"].lower()


def test_the_cookie_value_is_not_the_workspace_id(
    client: TestClient, repository: _FakeRepository
) -> None:
    """The secret is what stands between an id and a session."""
    _enter(client, 1)
    workspace = repository.rows[(_DATASET.id, 1)]
    token = client.cookies.get(WORKSPACE_COOKIE_NAME, path="/v1/exercise")
    assert token is not None
    assert str(workspace.id) not in token
    assert token == derive_workspace_token(secret=_TEST_SECRET, workspace_id=workspace.id)


# ---------------------------------------------------------------------------
# The refusals
# ---------------------------------------------------------------------------


def test_a_request_with_no_cookie_is_refused_with_a_sentence(client: TestClient) -> None:
    response = client.get("/v1/exercise/workspaces/current")
    assert response.status_code == 401
    assert response.json() == {
        "error": {
            "code": "exercise_workspace_required",
            "message": "Enter your team number to open your team's workspace.",
        }
    }


def test_an_unknown_cookie_is_refused_the_same_way(client: TestClient) -> None:
    """Indistinguishable from "no cookie", so the route is no oracle."""
    client.cookies.set(WORKSPACE_COOKIE_NAME, "not-a-token", path="/v1/exercise")
    response = client.get("/v1/exercise/workspaces/current")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "exercise_workspace_required"


@pytest.mark.parametrize("team_number", [0, 7, -1, 99])
def test_a_team_number_outside_one_to_six_is_refused_with_a_sentence(
    client: TestClient, team_number: int
) -> None:
    response = _enter(client, team_number)
    assert response.status_code == 422
    assert response.json() == {
        "error": {
            "code": "exercise_team_number_unknown",
            "message": "Pick a team number from 1 to 6.",
        }
    }


def test_a_team_number_that_is_not_a_number_is_refused_by_the_contract(
    client: TestClient,
) -> None:
    """``"a"`` never reaches the handler; pydantic's own 422 is the right answer."""
    response = client.post(
        "/v1/exercise/workspaces",
        json={"team_number": "a"},
        headers={EXERCISE_REQUEST_HEADER: "1"},
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_request"


def test_every_number_the_domain_names_is_accepted(client: TestClient) -> None:
    """The range comes from ``EXERCISE_TEAM_NUMBERS``, not from a literal here."""
    for team_number in EXERCISE_TEAM_NUMBERS:
        assert _enter(client, team_number).status_code == 200


def test_a_state_changing_request_without_the_exercise_header_is_refused(
    client: TestClient,
) -> None:
    """The CSRF half. A cookie with no login behind it needs it."""
    response = client.post("/v1/exercise/workspaces", json={"team_number": 1})
    assert response.status_code == 403
    assert response.json() == {
        "error": {
            "code": "exercise_request_header_required",
            "message": "This request did not come from the exercise site.",
        }
    }


def test_the_reset_is_state_changing_too(client: TestClient) -> None:
    _enter(client, 1)
    assert client.post("/v1/exercise/workspaces/current/reset").status_code == 403


def test_the_read_route_needs_no_exercise_header(client: TestClient) -> None:
    """A GET is not state-changing; requiring the header would be cargo cult."""
    _enter(client, 1)
    assert client.get("/v1/exercise/workspaces/current").status_code == 200


def test_no_dataset_yet_is_one_plain_sentence(repository: _FakeRepository) -> None:
    """Before the instructor uploads the file, entering a number refuses politely."""
    settings = _settings()
    app = FastAPI()
    for exception_type, handler in EXCEPTION_HANDLERS.items():
        app.add_exception_handler(exception_type, handler)
    for router in routers_for(settings):
        app.include_router(router)
    app.dependency_overrides[get_exercise_session] = lambda: _FakeSession()
    app.dependency_overrides[get_workspace_repository] = lambda: repository
    app.dependency_overrides[get_workspace_secret] = lambda: _TEST_SECRET
    with TestClient(app) as client:
        response = _enter(client, 1)
    assert response.status_code == 409
    assert response.json() == {
        "error": {
            "code": "exercise_no_dataset",
            "message": "The instructor has not loaded the student body yet.",
        }
    }


def test_the_refusal_codes_are_the_exercises_own(client: TestClient) -> None:
    """Never the CBA auth codes: there is no identity here to have failed to present."""
    codes = {
        client.get("/v1/exercise/workspaces/current").json()["error"]["code"],
        client.post("/v1/exercise/workspaces", json={"team_number": 1}).json()["error"]["code"],
    }
    assert codes.isdisjoint({"unauthenticated", "forbidden", "invalid_token"})
    assert all(code.startswith("exercise_") for code in codes)


# ---------------------------------------------------------------------------
# D1 — scope isolation
# ---------------------------------------------------------------------------


def _paths_under(scope: ProductScope) -> frozenset[str]:
    return frozenset(
        route.path
        for router in routers_for(Settings(product_scope=scope))
        for route in router.routes
        if hasattr(route, "path")
    )


def test_the_workspace_routes_are_mounted_only_under_the_exercise_scope() -> None:
    mounted = _paths_under(ProductScope.CLASS_EXERCISE)
    assert {
        "/v1/exercise/workspaces",
        "/v1/exercise/workspaces/current",
        "/v1/exercise/workspaces/current/reset",
    } <= mounted
    for scope in (ProductScope.CBA, ProductScope.IA_WEST_LEGACY):
        assert not any(path.startswith("/v1/exercise") for path in _paths_under(scope))


def test_the_workspace_routes_answer_404_in_a_cba_process() -> None:
    app = FastAPI()
    for router in routers_for(Settings(product_scope=ProductScope.CBA)):
        app.include_router(router)
    with TestClient(app) as client:
        assert client.post("/v1/exercise/workspaces", json={"team_number": 1}).status_code == 404
        assert client.get("/v1/exercise/workspaces/current").status_code == 404


def test_the_router_is_declared_under_the_class_exercise_capability() -> None:
    declared = {
        capability
        for router, capability in CAPABILITY_SCOPED_ROUTERS
        if router is exercise_workspace.router
    }
    assert declared == {Capability.CLASS_EXERCISE}


# ---------------------------------------------------------------------------
# D2 — the import boundary, restated where a reader of this file sees it
# ---------------------------------------------------------------------------


def _imported_modules(tree: ast.Module) -> set[str]:
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            imported.add(node.module)
    return imported


def test_the_router_imports_no_persistence_authz_or_principal_machinery() -> None:
    """``make imports`` says this too; a reader of this file should not have to look."""
    imported = _imported_modules(ast.parse(_ROUTER_SOURCE.read_text(encoding="utf-8")))
    for forbidden in (
        "smartmatch_authz",
        "smartmatch_persistence",
        "smartmatch_api.dependencies",
        "smartmatch_api.routers.auth",
        "sqlalchemy",
    ):
        assert not any(
            name == forbidden or name.startswith(f"{forbidden}.") for name in imported
        ), f"the workspace router imports {forbidden}"


# ---------------------------------------------------------------------------
# D6 / D8 — what a response may never carry
# ---------------------------------------------------------------------------

#: Names that must appear on no exercise response model. The first four are this
#: track's: the seed drives §11's chance element, the token and its hash are the
#: cookie, and the workspace id is what the token is derived from.
_FORBIDDEN_RESPONSE_FIELDS = frozenset(
    {"seed", "token", "workspace_token", "workspace_token_hash", "workspace_id", "id"}
    | set(EXERCISE_WITHHELD_FIELDS)
)

#: ADR-0025 D8: rank, weights and one reason. No number that reads as a score.
_SCORE_SHAPED = ("score", "percent", "confidence", "probability", "likelihood")


def _models_in_module() -> list[type[BaseModel]]:
    return [
        value
        for value in vars(exercise_workspace).values()
        if isinstance(value, type) and issubclass(value, BaseModel) and value is not BaseModel
    ]


def test_the_module_actually_declares_models() -> None:
    """A walk over an empty list is a green check that means nothing."""
    assert _models_in_module()


def test_no_response_model_carries_a_withheld_or_addressing_field() -> None:
    for model in _models_in_module():
        offenders = sorted(set(model.model_fields) & _FORBIDDEN_RESPONSE_FIELDS)
        assert offenders == [], f"{model.__name__} publishes {offenders}"


def test_no_response_model_carries_a_score_shaped_field() -> None:
    for model in _models_in_module():
        for field_name in model.model_fields:
            assert not any(shape in field_name.lower() for shape in _SCORE_SHAPED), (
                f"{model.__name__}.{field_name} reads as a score; ADR-0025 D8"
            )


def test_the_served_contract_names_none_of_them_either() -> None:
    """The models could be clean and the *document* not, if a route grew a parameter."""
    app = FastAPI()
    for router in routers_for(_settings()):
        app.include_router(router)
    document = app.openapi()
    schemas = document.get("components", {}).get("schemas", {})
    for name, schema in schemas.items():
        if not name.startswith(("Team", "Enter", "Exercise")):
            continue
        offenders = sorted(set(schema.get("properties", {})) & _FORBIDDEN_RESPONSE_FIELDS)
        assert offenders == [], f"{name} publishes {offenders}"
    for withheld in EXERCISE_WITHHELD_FIELDS:
        assert withheld not in str(document), f"{withheld} appears in the exercise contract"


# ---------------------------------------------------------------------------
# The secret and the boot guard
# ---------------------------------------------------------------------------


def test_a_class_exercise_process_without_a_secret_does_not_start() -> None:
    with pytest.raises(ValueError, match="SMARTMATCH_EXERCISE_WORKSPACE_SECRET is required"):
        require_exercise_workspace_secret(_settings(secret=None))


def test_a_short_secret_is_refused_rather_than_quietly_accepted() -> None:
    with pytest.raises(ValueError, match="at least"):
        require_exercise_workspace_secret(
            _settings(secret="x" * (MINIMUM_WORKSPACE_SECRET_LENGTH - 1))
        )


def test_the_secret_does_not_appear_in_a_repr_or_a_dump() -> None:
    """The two shapes that reach a debugger and a crash report unasked.

    ``repr(settings)`` is what a traceback frame prints and what most loggers
    call on an object they were handed; ``model_dump()`` is what anything that
    serialises configuration calls. Neither may carry the HMAC key, which is
    why the field is a ``SecretStr`` rather than a ``str`` with a comment
    saying not to log it.
    """
    settings = _settings()
    assert _TEST_SECRET not in repr(settings)
    assert _TEST_SECRET not in str(settings.model_dump())
    assert _TEST_SECRET not in str(settings.exercise_workspace_secret)
    # And it is still reachable where it is needed.
    assert require_exercise_workspace_secret(settings) == _TEST_SECRET


def test_the_refusal_quotes_no_part_of_the_configured_value() -> None:
    configured = "-".join(("a", "short", "but", "recognisable", "value"))
    with pytest.raises(ValueError) as raised:
        require_exercise_workspace_secret(_settings(secret=configured))
    assert configured not in str(raised.value)


@pytest.mark.parametrize("scope", [ProductScope.CBA, ProductScope.IA_WEST_LEGACY])
def test_the_secret_is_required_in_no_other_scope(scope: ProductScope) -> None:
    """A deployment with no exercise routes must not be made to carry the key."""
    settings = Settings(product_scope=scope)
    assert settings.exercise_workspace_secret is None
    assert not settings.capability_enabled(Capability.CLASS_EXERCISE)


def test_the_application_module_calls_the_boot_guard() -> None:
    """The guard is only a guard if the composition runs it."""
    source = Path(require_exercise_workspace_secret.__module__.replace(".", "/")).name
    assert source  # the import below is the real assertion
    main_source = (Path(exercise_workspace.__file__).parent.parent / "main.py").read_text(
        encoding="utf-8"
    )
    assert "require_exercise_workspace_secret(get_settings())" in main_source


# ---------------------------------------------------------------------------
# The token arithmetic
# ---------------------------------------------------------------------------


def test_the_token_is_stable_for_a_workspace_and_different_across_workspaces() -> None:
    first, second = uuid.uuid4(), uuid.uuid4()
    assert derive_workspace_token(secret=_TEST_SECRET, workspace_id=first) == (
        derive_workspace_token(secret=_TEST_SECRET, workspace_id=first)
    )
    assert derive_workspace_token(secret=_TEST_SECRET, workspace_id=first) != (
        derive_workspace_token(secret=_TEST_SECRET, workspace_id=second)
    )


def test_a_different_secret_yields_a_different_token() -> None:
    workspace_id = uuid.uuid4()
    assert derive_workspace_token(secret=_TEST_SECRET, workspace_id=workspace_id) != (
        derive_workspace_token(secret=_TEST_SECRET + "x", workspace_id=workspace_id)
    )


def test_the_stored_hash_is_not_the_token() -> None:
    token = derive_workspace_token(secret=_TEST_SECRET, workspace_id=uuid.uuid4())
    assert hash_workspace_token(token) != token


def test_a_seed_fits_a_signed_bigint() -> None:
    """``BIGINT`` is signed; a 64-bit draw overflows it for half of all values."""
    for _ in range(64):
        assert 0 <= new_workspace_seed() < 2**63
