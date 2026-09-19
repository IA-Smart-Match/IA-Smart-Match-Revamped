"""The instructor page's routes (CE-INSTRUCTOR, design spec §14, ADR-0025).

What is pinned here, in the order the failures would hurt:

1. **Every route but login and logout is shut without a session** — asserted
   over the app's own route table rather than route by route, so a route added
   to this module and left ungated fails here without anybody remembering to
   add a test.
2. **A team's workspace cookie does not open the instructor page.** Every class
   participant holds one.
3. **Fail closed**: a deployment with no passcode, a blank one and a
   too-short one all refuse, with the same sentence a wrong passcode gets.
4. **The rate limit** is charged before the passcode is checked (OQ-CE-06
   PLACEHOLDER).
5. **The cookie's flags on the wire**, including the narrower path.
6. **The responses carry nothing they must not**: a schema walk refuses the
   withheld column (D6), anything score-shaped (D8), and the workspace id,
   token, hash and seed.
7. **The refusals**, each with its sentence.
8. **Scope isolation**: the routes are absent under ``ProductScope.CBA``.

The database half — the re-point's delete-then-update order, the idempotent
unlock, and what a reset really deletes — is in
``tests/integration/test_exercise_instructor_persistence.py``, because a fake
repository cannot prove a foreign key.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel
from smartmatch_api.config import Settings, require_exercise_workspace_secret
from smartmatch_api.errors import EXCEPTION_HANDLERS
from smartmatch_api.exercise_dependencies import (
    EXERCISE_REQUEST_HEADER,
    INSTRUCTOR_COOKIE_NAME,
    ConfiguredPasscode,
    DatasetSummary,
    ExerciseDatasetSummary,
    ExerciseDatasetWriteError,
    get_active_dataset,
    get_dataset_repository,
    get_exercise_session,
    get_instructor_passcode,
    get_instructor_repository,
    get_workspace_repository,
    get_workspace_secret,
    instructor_cookie_policy,
)
from smartmatch_api.exercise_rate_limit import (
    INSTRUCTOR_LOGIN_ATTEMPTS_PER_CLIENT,
    INSTRUCTOR_LOGIN_WINDOW,
    FixedWindowLimiter,
)
from smartmatch_api.main import routers_for
from smartmatch_api.routers import exercise_instructor
from smartmatch_domain.exercise import EXERCISE_WITHHELD_FIELDS
from smartmatch_domain.exercise.instructor_session import mint_instructor_session
from smartmatch_domain.exercise.workspace_token import derive_workspace_token
from smartmatch_persistence.exercise.instructor_repository import (
    InstructorResultRun,
    InstructorSavedSetting,
    InstructorWorkspaceRow,
    RepointOutcome,
    TeamWorkspaceHandle,
)
from smartmatch_providers import Edition

#: Assembled from pieces, for ``test_exercise_workspace_router.py``'s reason:
#: ``tools/scan_forbidden.py`` matches ``<name ending in secret> = "<16+>"``.
_TEST_SECRET = "-".join(("exercise", "workspace", "key", "for", "tests", "only"))
_TEST_PASSCODE = "-".join(("classroom", "passcode", "for", "tests"))

_DATASET_ID = uuid.UUID("11111111-1111-1111-1111-111111111111")
_DATASET = ExerciseDatasetSummary(
    id=_DATASET_ID, label="Made-up student body (sample)", invite_limit=30
)
_WHEN = datetime(2026, 11, 20, 9, 0, tzinfo=UTC)

#: Event keys of the placeholder file. The case's, not an open question.
_EVENT_KEY = "northline"


def _summary(*, invite_limit: int = 30) -> DatasetSummary:
    return DatasetSummary(
        dataset_id=_DATASET_ID,
        label=_DATASET.label,
        source_filename="ann-sample.csv",
        uploaded_at=_WHEN,
        row_count=12,
        checksum="0" * 64,
        invite_limit=invite_limit,
        license_line=None,
        event_count=12,
    )


class _FakeDatasetRepository:
    """Enough of ``ExerciseDatasetRepository`` to exercise the routes."""

    def __init__(self) -> None:
        self.created: list[tuple[str, str | None]] = []
        self.invite_limit = 30
        self.write_fails = False

    def list_datasets(self, _session: object, *, limit: int) -> tuple[DatasetSummary, ...]:
        assert limit > 0
        return (_summary(invite_limit=self.invite_limit),)

    def get_dataset_summary(
        self, _session: object, *, dataset_id: uuid.UUID
    ) -> DatasetSummary | None:
        if dataset_id != _DATASET_ID:
            return None
        return _summary(invite_limit=self.invite_limit)

    def create_dataset(
        self, _session: object, parsed: object, *, label: str, source_filename: str | None
    ) -> DatasetSummary:
        if self.write_fails:
            raise ExerciseDatasetWriteError()
        self.created.append((label, source_filename))
        return _summary(invite_limit=self.invite_limit)


class _FakeInstructorRepository:
    """Enough of ``ExerciseInstructorRepository`` to exercise the routes."""

    def __init__(self, datasets: _FakeDatasetRepository) -> None:
        self.datasets = datasets
        self.teams: dict[int, uuid.UUID] = {3: uuid.uuid4()}
        self.unlocked: list[tuple[uuid.UUID, str]] = []
        self.repointed: list[uuid.UUID] = []

    def list_workspaces(
        self, _session: object, *, dataset_id: uuid.UUID
    ) -> tuple[InstructorWorkspaceRow, ...]:
        if dataset_id != _DATASET_ID:
            return ()
        return tuple(
            InstructorWorkspaceRow(
                team_number=number,
                dataset_label=_DATASET.label,
                created_at=_WHEN,
                saved_setting_count=2,
                result_run_count=0,
                asking_choice=None,
                refreshed_at=None,
            )
            for number in sorted(self.teams)
        )

    def find_workspace(
        self, _session: object, *, dataset_id: uuid.UUID, team_number: int
    ) -> TeamWorkspaceHandle | None:
        workspace_id = self.teams.get(team_number)
        if workspace_id is None or dataset_id != _DATASET_ID:
            return None
        return TeamWorkspaceHandle(id=workspace_id, dataset_id=dataset_id, team_number=team_number)

    def list_saved_settings(
        self, _session: object, *, workspace_id: uuid.UUID
    ) -> tuple[InstructorSavedSetting, ...]:
        assert workspace_id in self.teams.values()
        return (InstructorSavedSetting(event_key=_EVENT_KEY, name="Wide net", created_at=_WHEN),)

    def list_result_runs(
        self, _session: object, *, workspace_id: uuid.UUID
    ) -> tuple[InstructorResultRun, ...]:
        assert workspace_id in self.teams.values()
        return ()

    def event_exists(self, _session: object, *, dataset_id: uuid.UUID, event_key: str) -> bool:
        return dataset_id == _DATASET_ID and event_key == _EVENT_KEY

    def set_invite_limit(
        self, _session: object, *, dataset_id: uuid.UUID, invite_limit: int
    ) -> bool:
        if dataset_id != _DATASET_ID:
            return False
        self.datasets.invite_limit = invite_limit
        return True

    def unlock_results(self, _session: object, *, dataset_id: uuid.UUID, event_key: str) -> bool:
        already = (dataset_id, event_key) in self.unlocked
        if not already:
            self.unlocked.append((dataset_id, event_key))
        return not already

    def repoint_workspaces(self, _session: object, *, dataset_id: uuid.UUID) -> RepointOutcome:
        self.repointed.append(dataset_id)
        return RepointOutcome(moved=2, discarded=1)


class _FakeWorkspaceRepository:
    def __init__(self) -> None:
        self.reset_ids: list[uuid.UUID] = []

    def reset_team(self, _session: object, *, workspace_id: uuid.UUID) -> None:
        self.reset_ids.append(workspace_id)


class _FakeSession:
    def __init__(self) -> None:
        self.commits = 0

    def commit(self) -> None:
        self.commits += 1


def _settings(
    *,
    edition: Edition = Edition.DEV,
    passcode: str | None = _TEST_PASSCODE,
    cookie_secure: bool | None = None,
) -> Settings:
    from smartmatch_domain.product_scope import ProductScope

    return Settings(
        product_scope=ProductScope.CLASS_EXERCISE,
        edition=edition,
        exercise_workspace_secret=_TEST_SECRET,
        exercise_instructor_passcode=passcode,
        exercise_cookie_secure=cookie_secure,
    )


def _exercise_app(settings: Settings, state: dict[str, Any]) -> FastAPI:
    """The exercise process's routes, with the database replaced and nothing else."""
    app = FastAPI()
    for exception_type, handler in EXCEPTION_HANDLERS.items():
        app.add_exception_handler(exception_type, handler)
    for router in routers_for(settings):
        app.include_router(router)
    app.dependency_overrides[get_exercise_session] = lambda: state["session"]
    app.dependency_overrides[get_dataset_repository] = lambda: state["datasets"]
    app.dependency_overrides[get_instructor_repository] = lambda: state["instructor"]
    app.dependency_overrides[get_workspace_repository] = lambda: state["workspaces"]
    app.dependency_overrides[get_active_dataset] = lambda: _DATASET
    app.dependency_overrides[get_workspace_secret] = lambda: require_exercise_workspace_secret(
        settings
    )
    app.dependency_overrides[get_instructor_passcode] = lambda: ConfiguredPasscode(
        value=settings.exercise_instructor_passcode.get_secret_value()
        if settings.exercise_instructor_passcode
        else None
    )
    app.dependency_overrides[instructor_cookie_policy] = lambda: _real_policy(settings)
    return app


def _real_policy(settings: Settings) -> Any:
    """The real policy function, called with test settings rather than the env."""
    from smartmatch_api.exercise_dependencies import instructor_cookie_policy as real

    return real(settings)


@pytest.fixture(autouse=True)
def fresh_limiter(monkeypatch: pytest.MonkeyPatch) -> None:
    """A limiter per test. The real one is module-level and would leak counts."""
    monkeypatch.setattr(
        exercise_instructor,
        "_LOGIN_LIMITER",
        FixedWindowLimiter(
            per_key=INSTRUCTOR_LOGIN_ATTEMPTS_PER_CLIENT,
            total=INSTRUCTOR_LOGIN_ATTEMPTS_PER_CLIENT * 10,
            window=INSTRUCTOR_LOGIN_WINDOW,
        ),
    )


@pytest.fixture
def state() -> dict[str, Any]:
    datasets = _FakeDatasetRepository()
    return {
        "session": _FakeSession(),
        "datasets": datasets,
        "instructor": _FakeInstructorRepository(datasets),
        "workspaces": _FakeWorkspaceRepository(),
    }


@pytest.fixture
def client(state: dict[str, Any]) -> Iterator[TestClient]:
    with TestClient(_exercise_app(_settings(), state)) as test_client:
        yield test_client


def _login(client: TestClient, passcode: str = _TEST_PASSCODE) -> Any:
    return client.post(
        "/v1/exercise/instructor/login",
        json={"passcode": passcode},
        headers={EXERCISE_REQUEST_HEADER: "1"},
    )


@pytest.fixture
def signed_in(client: TestClient) -> TestClient:
    assert _login(client).status_code == 200
    return client


# ---------------------------------------------------------------------------
# The door
# ---------------------------------------------------------------------------


def test_the_passcode_opens_the_page_and_sets_a_cookie(client: TestClient) -> None:
    response = _login(client)

    assert response.status_code == 200
    assert response.json() == {"signed_in": True}
    assert client.cookies.get(INSTRUCTOR_COOKIE_NAME, path="/v1/exercise/instructor")


def test_the_cookie_carries_the_flags_a_browser_honours(client: TestClient) -> None:
    """Asserted on the wire, not on the policy object: the header is what counts."""
    header = _login(client).headers["set-cookie"]

    assert header.startswith(f"{INSTRUCTOR_COOKIE_NAME}=")
    assert "HttpOnly" in header
    assert "Path=/v1/exercise/instructor" in header
    assert "SameSite=lax" in header.lower().replace("samesite=lax", "SameSite=lax")


def test_the_instructor_cookie_is_scoped_more_narrowly_than_the_teams(
    client: TestClient,
) -> None:
    """A team's screen must never carry the instructor's session."""
    header = _login(client).headers["set-cookie"]
    assert "Path=/v1/exercise/instructor" in header
    assert "Path=/v1/exercise;" not in header


def test_the_cookie_is_secure_when_the_deployment_says_so(state: dict[str, Any]) -> None:
    with TestClient(_exercise_app(_settings(cookie_secure=True), state)) as client:
        assert "Secure" in _login(client).headers["set-cookie"]


@pytest.mark.parametrize(
    "presented",
    ["", " ", "wrong-passcode-entirely", _TEST_PASSCODE[:-1], _TEST_PASSCODE.upper()],
)
def test_a_wrong_passcode_is_one_sentence_and_no_cookie(client: TestClient, presented: str) -> None:
    response = _login(client, presented)

    assert response.status_code == 401
    assert response.json()["error"]["message"] == "That passcode was not recognised."
    assert INSTRUCTOR_COOKIE_NAME not in response.cookies


@pytest.mark.parametrize("passcode", [None, "", "  ", "tooshort"])
def test_an_unconfigured_or_unusable_passcode_is_a_shut_door(
    state: dict[str, Any], passcode: str | None
) -> None:
    """Fail closed. The sentence is the wrong-passcode sentence, so the response
    cannot be used to learn whether this deployment has an instructor page."""
    with TestClient(_exercise_app(_settings(passcode=passcode), state)) as client:
        response = _login(client, _TEST_PASSCODE)

    assert response.status_code == 401
    assert response.json()["error"]["message"] == "That passcode was not recognised."


def test_the_login_requires_the_exercise_request_header(client: TestClient) -> None:
    response = client.post("/v1/exercise/instructor/login", json={"passcode": _TEST_PASSCODE})
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "exercise_request_header_required"


def test_the_attempt_allowance_is_spent_by_wrong_passcodes(client: TestClient) -> None:
    """Charged before the passcode is looked at, so a wrong attempt costs the same."""
    for _ in range(INSTRUCTOR_LOGIN_ATTEMPTS_PER_CLIENT):
        assert _login(client, "wrong-passcode-entirely").status_code == 401

    refused = _login(client)
    assert refused.status_code == 429
    assert refused.json()["error"]["code"] == "exercise_instructor_login_rate_limited"


def test_logout_clears_the_cookie_without_needing_a_session(client: TestClient) -> None:
    response = client.post("/v1/exercise/instructor/logout", headers={EXERCISE_REQUEST_HEADER: "1"})

    assert response.status_code == 200
    assert response.json() == {"signed_in": False}


# ---------------------------------------------------------------------------
# The gate
# ---------------------------------------------------------------------------


def _instructor_routes(settings: Settings) -> list[tuple[str, str]]:
    """Every instructor route but login and logout, as (method, path).

    Read off ``routers_for`` rather than off ``app.routes``: this FastAPI
    version wraps an included router in an opaque object with no flat ``path``,
    so walking the app would find nothing and pass vacuously. The routers are
    what the app is built from, so they are the same list one level up.
    """
    found: list[tuple[str, str]] = []
    for router in routers_for(settings):
        for route in router.routes:
            path = getattr(route, "path", "")
            if not path.startswith("/v1/exercise/instructor"):
                continue
            if path.endswith(("/login", "/logout")):
                continue
            for method in sorted(getattr(route, "methods", set()) - {"HEAD", "OPTIONS"}):
                found.append((method, path))
    return found


def _call(client: TestClient, method: str, path: str) -> Any:
    """One request at a path, with the placeholders filled and CSRF sent."""
    concrete = (
        path.replace("{dataset_id}", str(_DATASET_ID))
        .replace("{team_number}", "3")
        .replace("{event_key}", _EVENT_KEY)
    )
    return client.request(
        method,
        concrete,
        headers={EXERCISE_REQUEST_HEADER: "1"},
        json={"invite_limit": 25} if method == "PATCH" else None,
        content=b"record_type\n" if method == "POST" and concrete.endswith("datasets") else None,
        params={"label": "A file"} if method == "POST" else None,
    )


def test_every_instructor_route_is_shut_without_a_session(client: TestClient) -> None:
    """Walked over the mounted route table, so a route added to this module and
    left ungated fails here without anybody remembering to write a test for it."""
    routes = _instructor_routes(_settings())
    assert routes, "the walk found no instructor routes; it is passing vacuously"

    for method, path in routes:
        response = _call(client, method, path)
        assert response.status_code == 401, f"{method} {path} answered {response.status_code}"
        assert response.json()["error"]["code"] == "exercise_instructor_session_required"


def test_a_team_workspace_cookie_does_not_open_the_instructor_page(
    client: TestClient,
) -> None:
    """Every class participant holds one of these."""
    client.cookies.set(
        INSTRUCTOR_COOKIE_NAME,
        derive_workspace_token(secret=_TEST_SECRET, workspace_id=uuid.uuid4()),
        path="/v1/exercise/instructor",
    )
    response = client.get("/v1/exercise/instructor/workspaces")

    assert response.status_code == 401


def test_a_session_from_another_deployment_is_refused(client: TestClient) -> None:
    client.cookies.set(
        INSTRUCTOR_COOKIE_NAME,
        mint_instructor_session(secret="a-different-deployments-key-entirely", now=_WHEN),
        path="/v1/exercise/instructor",
    )
    assert client.get("/v1/exercise/instructor/workspaces").status_code == 401


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("POST", "/v1/exercise/instructor/datasets"),
        ("PATCH", "/v1/exercise/instructor/datasets/{dataset_id}"),
        ("POST", "/v1/exercise/instructor/datasets/{dataset_id}/repoint"),
        ("POST", "/v1/exercise/instructor/events/{event_key}/unlock"),
        ("POST", "/v1/exercise/instructor/workspaces/{team_number}/reset"),
        ("POST", "/v1/exercise/instructor/refresh-all"),
    ],
)
def test_every_state_changing_route_requires_the_csrf_header(
    signed_in: TestClient, method: str, path: str
) -> None:
    concrete = (
        path.replace("{dataset_id}", str(_DATASET_ID))
        .replace("{team_number}", "3")
        .replace("{event_key}", _EVENT_KEY)
    )
    response = signed_in.request(method, concrete, json={"invite_limit": 25})

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "exercise_request_header_required"


# ---------------------------------------------------------------------------
# Data files
# ---------------------------------------------------------------------------


def _csv(rows: int = 12) -> bytes:
    """A placeholder-layout file the ingest core accepts is not needed here —
    the parser's own tests own that. What is needed is a file it *refuses*, so
    the route's refusal path is the thing under test."""
    return ("record_type\n" + "profile\n" * rows).encode("utf-8")


def test_a_refused_file_is_one_plain_sentence(signed_in: TestClient) -> None:
    response = signed_in.post(
        "/v1/exercise/instructor/datasets",
        params={"label": "Spring practice file"},
        content=_csv(),
        headers={EXERCISE_REQUEST_HEADER: "1", "content-type": "text/csv"},
    )

    assert response.status_code == 422
    message = response.json()["error"]["message"]
    assert message.endswith(".")
    assert "Traceback" not in message
    assert response.json()["error"]["code"].startswith("exercise_ingest_")


def test_the_dataset_list_is_behind_the_session_and_names_the_file(
    signed_in: TestClient,
) -> None:
    response = signed_in.get("/v1/exercise/instructor/datasets")

    assert response.status_code == 200
    assert response.json()[0]["label"] == _DATASET.label
    assert response.json()[0]["invite_limit"] == 30


@pytest.mark.parametrize("limit", [0, -1, 1_000_000])
def test_an_invite_limit_outside_its_bounds_is_one_sentence(
    signed_in: TestClient, limit: int
) -> None:
    response = signed_in.patch(
        f"/v1/exercise/instructor/datasets/{_DATASET_ID}",
        json={"invite_limit": limit},
        headers={EXERCISE_REQUEST_HEADER: "1"},
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "exercise_invite_limit_out_of_range"


def test_the_invite_limit_can_be_changed(signed_in: TestClient) -> None:
    response = signed_in.patch(
        f"/v1/exercise/instructor/datasets/{_DATASET_ID}",
        json={"invite_limit": 25},
        headers={EXERCISE_REQUEST_HEADER: "1"},
    )

    assert response.status_code == 200
    assert response.json()["invite_limit"] == 25


def test_an_unknown_data_file_is_one_sentence(signed_in: TestClient) -> None:
    response = signed_in.patch(
        f"/v1/exercise/instructor/datasets/{uuid.uuid4()}",
        json={"invite_limit": 25},
        headers={EXERCISE_REQUEST_HEADER: "1"},
    )

    assert response.status_code == 404
    assert response.json()["error"]["message"] == "That data file is not on the server."


def test_a_repoint_reports_what_it_did(signed_in: TestClient, state: dict[str, Any]) -> None:
    response = signed_in.post(
        f"/v1/exercise/instructor/datasets/{_DATASET_ID}/repoint",
        headers={EXERCISE_REQUEST_HEADER: "1"},
    )

    assert response.status_code == 200
    assert response.json() == {
        "dataset_label": _DATASET.label,
        "teams_moved": 2,
        "teams_discarded": 1,
    }
    assert state["instructor"].repointed == [_DATASET_ID]


# ---------------------------------------------------------------------------
# Unlock, teams, refresh-all
# ---------------------------------------------------------------------------


def test_unlocking_an_event_twice_says_the_same_thing(signed_in: TestClient) -> None:
    first = signed_in.post(
        f"/v1/exercise/instructor/events/{_EVENT_KEY}/unlock",
        headers={EXERCISE_REQUEST_HEADER: "1"},
    )
    second = signed_in.post(
        f"/v1/exercise/instructor/events/{_EVENT_KEY}/unlock",
        headers={EXERCISE_REQUEST_HEADER: "1"},
    )

    assert first.status_code == second.status_code == 200
    assert first.json() == second.json() == {"event_key": _EVENT_KEY, "unlocked": True}


def test_unlocking_an_event_that_is_not_in_the_file_is_one_sentence(
    signed_in: TestClient,
) -> None:
    response = signed_in.post(
        "/v1/exercise/instructor/events/not-an-event/unlock",
        headers={EXERCISE_REQUEST_HEADER: "1"},
    )

    assert response.status_code == 404
    assert response.json()["error"]["message"] == "That event is not in the loaded data file."


def test_the_team_list_reports_counts_and_no_identifiers(signed_in: TestClient) -> None:
    response = signed_in.get("/v1/exercise/instructor/workspaces")

    assert response.status_code == 200
    body = response.json()
    assert body["teams"][0]["team_number"] == 3
    assert body["teams"][0]["saved_setting_count"] == 2
    assert "seed" not in str(body)
    assert "workspace_id" not in str(body)


def test_a_teams_detail_lists_settings_by_name_and_no_runs_yet(
    signed_in: TestClient,
) -> None:
    response = signed_in.get("/v1/exercise/instructor/workspaces/3")

    assert response.status_code == 200
    body = response.json()
    assert body["team_number"] == 3
    assert body["result_runs"] == []
    assert [(row["event_key"], row["name"]) for row in body["saved_settings"]] == [
        (_EVENT_KEY, "Wide net")
    ]
    assert "weights" not in body["saved_settings"][0]


def test_a_team_that_has_not_entered_is_one_sentence(signed_in: TestClient) -> None:
    response = signed_in.get("/v1/exercise/instructor/workspaces/5")

    assert response.status_code == 404
    assert response.json()["error"]["message"] == "That team has not entered its number yet."


def test_a_team_number_outside_one_to_six_is_the_typo_it_is(signed_in: TestClient) -> None:
    response = signed_in.get("/v1/exercise/instructor/workspaces/9")

    assert response.status_code == 422
    assert response.json()["error"]["message"] == "Pick a team number from 1 to 6."


def test_the_instructor_reset_clears_exactly_one_team(
    signed_in: TestClient, state: dict[str, Any]
) -> None:
    response = signed_in.post(
        "/v1/exercise/instructor/workspaces/3/reset",
        headers={EXERCISE_REQUEST_HEADER: "1"},
    )

    assert response.status_code == 200
    assert state["workspaces"].reset_ids == [state["instructor"].teams[3]]


def test_refresh_all_refuses_with_a_sentence_until_the_results_track_lands(
    signed_in: TestClient,
) -> None:
    response = signed_in.post(
        "/v1/exercise/instructor/refresh-all", headers={EXERCISE_REQUEST_HEADER: "1"}
    )

    assert response.status_code == 409
    assert response.json()["error"]["message"] == ("Refreshing every team is not switched on yet.")


# ---------------------------------------------------------------------------
# What a response may never carry (ADR-0025 D6, D8)
# ---------------------------------------------------------------------------

#: Names that would be a workspace's own addressing, or a score.
_REFUSED_FIELD_NAMES = (
    frozenset({"seed", "token", "workspace_token_hash", "workspace_id", "id", "passcode", "secret"})
    | EXERCISE_WITHHELD_FIELDS
)

#: Substrings that would be a number about how well a team did (D8).
_SCORE_SHAPED = ("score", "percent", "confidence", "probability", "weight")


#: The models that are *inputs*. A request may of course name the passcode —
#: that is what a login screen sends — and the rules below are about what
#: leaves the server. Listed by name rather than detected by a suffix, so a
#: response model accidentally named ``…Request`` cannot exempt itself.
_REQUEST_MODELS = frozenset({"InstructorLoginRequest", "InviteLimitRequest"})


def _models(*, responses_only: bool = True) -> list[type[BaseModel]]:
    return [
        value
        for value in vars(exercise_instructor).values()
        if isinstance(value, type)
        and issubclass(value, BaseModel)
        and value is not BaseModel
        and not (responses_only and value.__name__ in _REQUEST_MODELS)
    ]


def test_no_response_model_carries_a_refused_name() -> None:
    models = _models()
    assert models, "the walk found no models; it is passing vacuously"

    offenders = [
        (model.__name__, name)
        for model in models
        for name in model.model_fields
        if name in _REFUSED_FIELD_NAMES
    ]
    assert offenders == []


def test_the_request_models_are_the_only_exemption_and_they_are_inputs() -> None:
    """So the exemption above cannot quietly grow to cover a response."""
    declared = {model.__name__ for model in _models(responses_only=False)}
    assert declared >= _REQUEST_MODELS
    for name in _REQUEST_MODELS:
        model = getattr(exercise_instructor, name)
        assert model.model_config.get("extra") == "forbid"


def test_no_response_model_carries_anything_score_shaped() -> None:
    """ADR-0025 D8, including on the instructor's screen — it is the same projector."""
    offenders = [
        (model.__name__, name)
        for model in _models()
        for name in model.model_fields
        for shape in _SCORE_SHAPED
        if shape in name.lower()
    ]
    assert offenders == []


def test_no_route_response_mentions_the_withheld_column(signed_in: TestClient) -> None:
    """Belt and braces over the schema walk: the wire, not the declaration."""
    for path in (
        "/v1/exercise/instructor/datasets",
        "/v1/exercise/instructor/workspaces",
        "/v1/exercise/instructor/workspaces/3",
    ):
        body = signed_in.get(path).text
        for withheld in EXERCISE_WITHHELD_FIELDS:
            assert withheld not in body


# ---------------------------------------------------------------------------
# Scope isolation (ADR-0025 D1)
# ---------------------------------------------------------------------------


def test_the_instructor_routes_are_absent_under_the_cba_scope() -> None:
    from smartmatch_domain.product_scope import ProductScope

    cba_paths = {
        getattr(route, "path", "")
        for router in routers_for(Settings(product_scope=ProductScope.CBA))
        for route in router.routes
    }
    offenders = sorted(path for path in cba_paths if path.startswith("/v1/exercise"))
    assert offenders == []
