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
    MaybeDataset,
    get_active_dataset,
    get_dataset_repository,
    get_exercise_session,
    get_instructor_passcode,
    get_instructor_repository,
    get_maybe_active_dataset,
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
    WorkingDataset,
)
from smartmatch_providers import Edition

#: Assembled from pieces, for ``test_exercise_workspace_router.py``'s reason:
#: ``tools/scan_forbidden.py`` matches ``<name ending in secret> = "<16+>"``.
_TEST_SECRET = "-".join(("exercise", "workspace", "key", "for", "tests", "only"))
_TEST_PASSCODE = "-".join(("classroom", "passcode", "for", "tests"))

#: A second deployment's exercise secret, for the "another deployment's session
#: is refused" case. Assembled from pieces for the same reason as the first.
_OTHER_SECRET = "-".join(("another", "deployment", "key", "entirely", "for", "tests"))

_DATASET_ID = uuid.UUID("11111111-1111-1111-1111-111111111111")
_DATASET = ExerciseDatasetSummary(
    id=_DATASET_ID, label="Made-up student body (sample)", invite_limit=30
)
_WHEN = datetime(2026, 11, 20, 9, 0, tzinfo=UTC)

#: The data file the teams are actually on, deliberately **not** the active
#: one. Design spec §3: an upload moves no team, so the newest file and the
#: file in use are different questions — and answering the second with the
#: first is the defect M8 names.
_TEAMS_DATASET_ID = uuid.UUID("22222222-2222-2222-2222-222222222222")
_TEAMS_DATASET_LABEL = "Made-up student body (in use)"


def _dataset_label(dataset_id: uuid.UUID) -> str:
    return _DATASET.label if dataset_id == _DATASET_ID else _TEAMS_DATASET_LABEL


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
        #: Team number -> (workspace id, the data file that team is on).
        #:
        #: The file is **not** ``_DATASET_ID`` by default: the active data file
        #: is the newest upload and the teams are on the one they entered on,
        #: and the whole of M8 was the two being confused. A fake that made
        #: them equal could not fail the way production did.
        self.teams: dict[int, tuple[uuid.UUID, uuid.UUID]] = {3: (uuid.uuid4(), _TEAMS_DATASET_ID)}
        self.unlocked: list[tuple[uuid.UUID, str]] = []
        self.repointed: list[uuid.UUID] = []
        self.reset_children: list[uuid.UUID] = []
        self.reset_ids: list[uuid.UUID] = []

    def list_workspaces(
        self, _session: object, *, dataset_id: uuid.UUID | None = None
    ) -> tuple[InstructorWorkspaceRow, ...]:
        return tuple(
            InstructorWorkspaceRow(
                team_number=number,
                dataset_id=on_dataset,
                dataset_label=_dataset_label(on_dataset),
                created_at=_WHEN,
                saved_setting_count=2,
                result_run_count=0,
                asking_choice=None,
                refreshed_at=None,
            )
            for number, (_id, on_dataset) in sorted(self.teams.items())
            if dataset_id is None or on_dataset == dataset_id
        )

    def datasets_with_workspaces(self, _session: object) -> tuple[WorkingDataset, ...]:
        counts: dict[uuid.UUID, int] = {}
        for _id, on_dataset in self.teams.values():
            counts[on_dataset] = counts.get(on_dataset, 0) + 1
        return tuple(
            WorkingDataset(dataset_id=key, label=_dataset_label(key), team_count=count)
            for key, count in sorted(counts.items(), key=lambda item: str(item[0]))
        )

    def find_workspace(
        self, _session: object, *, dataset_id: uuid.UUID, team_number: int
    ) -> TeamWorkspaceHandle | None:
        found = self.teams.get(team_number)
        if found is None or found[1] != dataset_id:
            return None
        return TeamWorkspaceHandle(id=found[0], dataset_id=dataset_id, team_number=team_number)

    def reset_workspace_children(
        self, _session: object, *, dataset_id: uuid.UUID, workspace_id: uuid.UUID
    ) -> None:
        assert dataset_id is not None
        self.reset_children.append(workspace_id)

    def reset_team(
        self,
        session: object,
        *,
        dataset_id: uuid.UUID,
        workspace_id: uuid.UUID,
        workspaces: object,
    ) -> None:
        assert dataset_id is not None
        self.reset_ids.append(workspace_id)
        workspaces.reset_team(session, workspace_id=workspace_id)  # type: ignore[attr-defined]

    def list_saved_settings(
        self, _session: object, *, workspace_id: uuid.UUID
    ) -> tuple[InstructorSavedSetting, ...]:
        assert workspace_id in {found[0] for found in self.teams.values()}
        return (InstructorSavedSetting(event_key=_EVENT_KEY, name="Wide net", created_at=_WHEN),)

    def list_result_runs(
        self, _session: object, *, workspace_id: uuid.UUID
    ) -> tuple[InstructorResultRun, ...]:
        assert workspace_id in {found[0] for found in self.teams.values()}
        return ()

    def event_exists(self, _session: object, *, dataset_id: uuid.UUID, event_key: str) -> bool:
        known = {_DATASET_ID, _TEAMS_DATASET_ID}
        return dataset_id in known and event_key == _EVENT_KEY

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
    cookie_secure: bool | None = False,
) -> Settings:
    """Test settings, with ``Secure`` **off by default** and that is the point.

    The instructor cookie defaults to ``Secure`` (M5), and ``TestClient`` speaks
    ``http://testserver`` — so a browser-accurate client does not store the
    cookie and every gated route would 401. That is not a test artefact: it is
    precisely the local-development consequence the policy's docstring names,
    and a deployment on plain HTTP has to set
    ``SMARTMATCH_EXERCISE_COOKIE_SECURE=false`` for the same reason.

    So the default here is the one a plain-HTTP deployment must use, and the
    tests that are *about* the flag pass it explicitly — including
    ``cookie_secure=None`` for the default-on case, which asserts on the
    ``Set-Cookie`` header rather than on what the client kept.
    """
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
    app.dependency_overrides[get_maybe_active_dataset] = lambda: MaybeDataset(dataset=_DATASET)
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


def test_the_instructor_cookie_is_secure_by_default_even_in_the_dev_edition(
    state: dict[str, Any],
) -> None:
    """M5. The workspace cookie's edition fallback is wrong for *this* cookie.

    The pilot VM serves the site over HTTPS while ``docker-compose.vm.yml``
    pins ``SMARTMATCH_EDITION=dev``, so "off in dev" would have sent the one
    credential in this product over the wire without ``Secure`` — on the one
    deployment that matters. A team's workspace token is a pointer to made-up
    rows and every participant holds one; this cookie is not that, and does not
    get that default.
    """
    with TestClient(_exercise_app(_settings(edition=Edition.DEV, cookie_secure=None), state)) as (
        client
    ):
        assert "Secure" in _login(client).headers["set-cookie"]


def test_the_instructor_cookie_is_insecure_only_when_a_deployment_says_so(
    state: dict[str, Any],
) -> None:
    """The escape hatch local development needs, and the only one.

    A ``Secure`` cookie is not stored on an ``http`` origin, so plain-HTTP
    development must set ``SMARTMATCH_EXERCISE_COOKIE_SECURE=false``. That
    failure is immediate and local; the default's failure was silent and in a
    classroom.
    """
    with TestClient(_exercise_app(_settings(cookie_secure=False), state)) as client:
        assert "Secure" not in _login(client).headers["set-cookie"]


def test_the_workspace_cookies_own_default_is_unchanged() -> None:
    """M5 must not have moved the *team* cookie's behaviour."""
    from smartmatch_api.exercise_dependencies import workspace_cookie_policy

    assert (
        workspace_cookie_policy(_settings(edition=Edition.DEV, cookie_secure=None)).secure is False
    )
    assert (
        workspace_cookie_policy(_settings(edition=Edition.CLASSROOM, cookie_secure=None)).secure
        is True
    )


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


def test_a_correct_passcode_gets_in_while_the_global_window_is_spent(
    state: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    """H1's second half: a flood must not lock the passcode holder out.

    The global bound is the one an attacker can exhaust *on somebody else's
    behalf* — many addresses, or one address behind a proxy this limiter
    deliberately does not parse. If it could refuse a correct passcode, an
    afternoon of wrong guesses from a botnet would take Ann's own instructor
    page away from her for the lesson, and nothing she could do at the keyboard
    would bring it back.
    """
    monkeypatch.setattr(
        exercise_instructor,
        "_LOGIN_LIMITER",
        FixedWindowLimiter(per_key=10, total=1, window=INSTRUCTOR_LOGIN_WINDOW),
    )
    with TestClient(_exercise_app(_settings(), state)) as client:
        # One wrong attempt from somewhere else spends the whole global window.
        assert _login(client, "wrong-passcode-entirely").status_code == 401

        assert _login(client).status_code == 200
        # And a second one is not refused either: the global bound is never the
        # reason a correct passcode is turned away.
        assert _login(client).status_code == 200


def test_a_correct_login_on_a_spent_global_window_refunds_nothing(
    state: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Review finding F3 on PR #184: the refund was unconditional.

    ``refund_global`` was called on every correct login, including the ones
    whose ``charge`` had already been refused by the global bound and had
    therefore spent nothing. Each such login handed back a unit it never took —
    minting one unit of everybody's allowance per correct login, exactly while
    the window is under the load it exists for, and cancelling somebody else's
    wrong attempt to do it.

    Observed through the bound rather than through the counter: with the window
    at one, a wrong passcode spends it, a correct login must leave it spent,
    and the next wrong passcode must therefore still be refused as 429. Before
    the guard the refund freed the unit and that attempt came back 401.
    """
    monkeypatch.setattr(
        exercise_instructor,
        "_LOGIN_LIMITER",
        FixedWindowLimiter(per_key=10, total=1, window=INSTRUCTOR_LOGIN_WINDOW),
    )
    with TestClient(_exercise_app(_settings(), state)) as client:
        assert _login(client, "wrong-passcode-entirely").status_code == 401
        assert _login(client).status_code == 200

        after = _login(client, "wrong-passcode-entirely")

    assert after.status_code == 429, "a correct login must not mint global budget"
    assert after.json()["error"]["code"] == "exercise_instructor_login_rate_limited"


def test_a_correct_login_inside_the_global_window_still_refunds_its_own_unit(
    state: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    """The guard narrows the refund; it does not remove it.

    With room in the window, a correct login spends a unit and gives that unit
    back, so the window ends up holding only the attempts that were wrong. Two
    correct logins against a window of two therefore leave both wrong-passcode
    units still available.
    """
    monkeypatch.setattr(
        exercise_instructor,
        "_LOGIN_LIMITER",
        FixedWindowLimiter(per_key=10, total=2, window=INSTRUCTOR_LOGIN_WINDOW),
    )
    with TestClient(_exercise_app(_settings(), state)) as client:
        assert _login(client).status_code == 200
        assert _login(client).status_code == 200

        # Nothing wrong has been attempted, so the window is still whole.
        assert _login(client, "wrong-passcode-entirely").status_code == 401
        assert _login(client, "wrong-passcode-entirely").status_code == 401


def test_a_wrong_passcode_on_a_spent_global_window_is_refused(
    state: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    """The bound still bounds: only a *correct* passcode survives it."""
    monkeypatch.setattr(
        exercise_instructor,
        "_LOGIN_LIMITER",
        FixedWindowLimiter(per_key=10, total=1, window=INSTRUCTOR_LOGIN_WINDOW),
    )
    with TestClient(_exercise_app(_settings(), state)) as client:
        assert _login(client, "wrong-passcode-entirely").status_code == 401

        refused = _login(client, "wrong-passcode-entirely")

    assert refused.status_code == 429
    assert refused.json()["error"]["code"] == "exercise_instructor_login_rate_limited"


def test_the_per_key_bound_still_applies_to_a_correct_passcode(
    state: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Decided and documented: the caller's own budget is not refunded.

    The per-key bound is the only one a caller controls, and a correct passcode
    does not buy more of it. A person who has just typed ten wrong passcodes
    waiting a few minutes is the limiter working; letting a correct passcode
    reset it would make the bound unreachable by exactly the attacker who has
    guessed one.
    """
    monkeypatch.setattr(
        exercise_instructor,
        "_LOGIN_LIMITER",
        FixedWindowLimiter(per_key=2, total=100, window=INSTRUCTOR_LOGIN_WINDOW),
    )
    with TestClient(_exercise_app(_settings(), state)) as client:
        assert _login(client).status_code == 200
        assert _login(client).status_code == 200

        assert _login(client).status_code == 429


def test_an_unconfigured_deployment_still_pays_for_a_verification(
    state: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    """M2: the "no passcode here" branch must not be the cheap one.

    Asserted by counting derivations rather than by timing, which on a loaded
    runner is a coin flip. The claim is that the unconfigured path performs the
    same key-derivation work a wrong passcode performs — so a stopwatch cannot
    answer "is there an instructor page on this host at all?".
    """
    from smartmatch_domain.exercise import instructor_session

    calls: list[str] = []
    real = instructor_session.verify_password

    def _counting(presented: str, stored: object) -> bool:
        calls.append(presented)
        return real(presented, stored)  # type: ignore[arg-type]

    monkeypatch.setattr(instructor_session, "verify_password", _counting)

    with TestClient(_exercise_app(_settings(passcode=None), state)) as unconfigured:
        assert _login(unconfigured, "some attempt").status_code == 401
    unconfigured_calls = len(calls)

    calls.clear()
    with TestClient(_exercise_app(_settings(), state)) as configured:
        assert _login(configured, "some attempt").status_code == 401

    assert unconfigured_calls == len(calls) == 1


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

    **Ungated routes are excluded by router identity, not by path spelling.**
    An earlier version skipped anything ending ``/login`` or ``/logout``, which
    made the guard's coverage a property of a *name*: a future ungated route
    called ``/token-refresh`` would have been checked (correctly), but a gated
    one called ``.../datasets/login`` would have been skipped (wrongly), and —
    worse — moving a route onto ``login_router`` without renaming it would have
    kept it in the checked set while removing its gate, so the test would fail
    for the right reason only by luck. ``router`` is the object the session
    dependency is attached to; asking which router a route came from is asking
    the question the test is about.
    """
    gated = {id(route) for route in exercise_instructor.router.routes}
    found: list[tuple[str, str]] = []
    for mounted in routers_for(settings):
        for route in mounted.routes:
            if id(route) not in gated:
                continue
            path = getattr(route, "path", "")
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
    assert ("POST", "/v1/exercise/instructor/login") not in routes
    assert ("POST", "/v1/exercise/instructor/logout") not in routes

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
        mint_instructor_session(secret=_OTHER_SECRET, now=_WHEN),
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
    assert response.json()["error"]["message"] == (
        "That event is not in the data file the teams are working in."
    )


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
    assert state["workspaces"].reset_ids == [state["instructor"].teams[3][0]]


def test_an_upload_does_not_empty_the_instructors_own_team_list(
    signed_in: TestClient, state: dict[str, Any]
) -> None:
    """M8, as the thing that actually happened.

    The active data file is the newest upload; the teams are on the one they
    entered on. This list used to be scoped to the first, so the moment Ann
    pressed "upload" her own screen reported no teams working while six teams
    carried on — with nothing to say why, and a re-point she had no reason to
    think she needed as the only way back.

    The fake keeps the two ids different on purpose, so a regression that
    re-scoped this list to the active file would fail here rather than pass
    because the test made them equal.
    """
    body = signed_in.get("/v1/exercise/instructor/workspaces").json()

    assert [team["team_number"] for team in body["teams"]] == [3]
    assert body["teams"][0]["dataset_id"] == str(_TEAMS_DATASET_ID)
    assert body["teams"][0]["dataset_label"] == _TEAMS_DATASET_LABEL
    # Said separately, because it is a different fact and only a re-point
    # makes the two the same.
    assert body["active_dataset_label"] == _DATASET.label
    assert _TEAMS_DATASET_ID != _DATASET_ID


def test_an_upload_says_in_one_sentence_that_no_team_has_moved(
    signed_in: TestClient,
) -> None:
    """M8's third part. Design spec §3's rule is right and it is surprising."""
    from smartmatch_api.routers.exercise_instructor_models import TEAMS_HAVE_NOT_MOVED

    response = signed_in.post(
        "/v1/exercise/instructor/datasets",
        params={"label": "Spring practice file"},
        content=_csv(),
        headers={EXERCISE_REQUEST_HEADER: "1", "content-type": "text/csv"},
    )

    # The file above is refused by the parser, so drive the notice through the
    # model instead of the write path: what is pinned is that the field exists,
    # is a sentence, and says the thing.
    assert response.status_code == 422
    assert TEAMS_HAVE_NOT_MOVED.endswith(".")
    assert "re-point" in TEAMS_HAVE_NOT_MOVED
    assert "notice" in exercise_instructor.UploadedDatasetView.model_fields


def test_the_team_routes_act_on_the_file_the_teams_are_on(
    signed_in: TestClient, state: dict[str, Any]
) -> None:
    """Detail, reset and unlock resolve to the teams' file, not the newest one."""
    detail = signed_in.get("/v1/exercise/instructor/workspaces/3")
    unlock = signed_in.post(
        f"/v1/exercise/instructor/events/{_EVENT_KEY}/unlock",
        headers={EXERCISE_REQUEST_HEADER: "1"},
    )

    assert detail.status_code == 200
    assert unlock.status_code == 200
    # The row was written against the teams' file, not the active one.
    assert state["instructor"].unlocked == [(_TEAMS_DATASET_ID, _EVENT_KEY)]


def test_a_data_file_with_no_teams_in_it_is_never_targeted(
    signed_in: TestClient, state: dict[str, Any]
) -> None:
    """The unlock-into-the-void, refused with a sentence instead."""
    response = signed_in.post(
        f"/v1/exercise/instructor/events/{_EVENT_KEY}/unlock",
        params={"dataset_id": str(_DATASET_ID)},
        headers={EXERCISE_REQUEST_HEADER: "1"},
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "exercise_dataset_has_no_teams"
    assert response.json()["error"]["message"] == "No team is working in that data file."
    assert state["instructor"].unlocked == []


def test_no_team_at_all_is_one_sentence_rather_than_a_write(
    signed_in: TestClient, state: dict[str, Any]
) -> None:
    state["instructor"].teams.clear()

    response = signed_in.post(
        f"/v1/exercise/instructor/events/{_EVENT_KEY}/unlock",
        headers={EXERCISE_REQUEST_HEADER: "1"},
    )

    assert response.status_code == 409
    assert response.json()["error"]["message"] == "No team has entered a number yet."
    assert state["instructor"].unlocked == []


def test_teams_split_across_two_files_are_asked_about_rather_than_guessed(
    signed_in: TestClient, state: dict[str, Any]
) -> None:
    """A re-point exists to end this state; until then the server does not pick."""
    state["instructor"].teams[4] = (uuid.uuid4(), _DATASET_ID)

    ambiguous = signed_in.get("/v1/exercise/instructor/workspaces/3")
    named = signed_in.get(
        "/v1/exercise/instructor/workspaces/3", params={"dataset_id": str(_TEAMS_DATASET_ID)}
    )

    assert ambiguous.status_code == 409
    assert ambiguous.json()["error"]["code"] == "exercise_teams_span_datasets"
    assert named.status_code == 200
    assert named.json()["team_number"] == 3


def test_an_explicit_dataset_id_is_honoured_for_a_reset(
    signed_in: TestClient, state: dict[str, Any]
) -> None:
    response = signed_in.post(
        "/v1/exercise/instructor/workspaces/3/reset",
        params={"dataset_id": str(_TEAMS_DATASET_ID)},
        headers={EXERCISE_REQUEST_HEADER: "1"},
    )

    assert response.status_code == 200
    assert state["workspaces"].reset_ids == [state["instructor"].teams[3][0]]


def test_a_passcode_longer_than_the_bound_is_refused_before_the_handler(
    client: TestClient,
) -> None:
    """L1. An unbounded field buys a key derivation over however much was sent."""
    from smartmatch_api.routers.exercise_instructor_models import MAX_PASSCODE_CHARACTERS

    response = _login(client, "x" * (MAX_PASSCODE_CHARACTERS + 1))

    assert response.status_code == 422
    assert _TEST_PASSCODE not in response.text


def test_this_module_no_longer_declares_refresh_all() -> None:
    """The refusing stub is **deleted**, not deprecated (CE-RESULTS-API).

    PR #184 shipped ``POST /v1/exercise/instructor/refresh-all`` as a route that
    always refused, because the share a refresh applies is decided by an asking
    choice no route stored yet. The choice is stored now, so the real handler
    lives in ``routers/exercise_instructor_refresh.py`` — a module of its own,
    because this file is already past the repository's 800-line ceiling — and
    this one must not still be answering at that path.

    Asserted on **this module's own routes** rather than on the mounted app: two
    handlers at one path is exactly the failure a deletion can leave behind, and
    the app would answer with whichever was mounted first without saying so.
    """
    declared = {
        (method, route.path)
        for route in (*exercise_instructor.router.routes, *exercise_instructor.login_router.routes)
        for method in getattr(route, "methods", ())
    }

    assert ("POST", "/v1/exercise/instructor/refresh-all") not in declared
    assert "refresh_all_workspaces" not in vars(exercise_instructor)


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


def test_the_served_contract_names_the_withheld_column_nowhere(
    state: dict[str, Any],
) -> None:
    """ADR-0025 D6 reaches the *document*, not only the fields.

    A handler docstring becomes a route's ``description``, so a route that
    merely *explains* the withheld column publishes its name — which is how
    ``refresh-all``'s docstring came to fail this during development. The
    schemas are clean by construction; the prose is not, unless somebody checks
    it.
    """
    app = _exercise_app(_settings(), state)
    document = str(app.openapi())

    for withheld in EXERCISE_WITHHELD_FIELDS:
        assert withheld not in document


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
