"""Drive the class exercise through its real routes against a real PostgreSQL.

The helpers ``test_exercise_full_class_run.py`` uses to walk six teams through
a whole class. Nothing here is faked: the app is the exercise process's own
routers and error handlers over a session factory bound to a scratch
database, and the only dependency replaced is ``get_settings`` — so the
workspace secret, the instructor passcode and plain-HTTP cookies are the
test's own rather than whatever the environment holds.

Every request any client here sends is recorded (:class:`Exchange`), so the
test can check *every* response body of the class — not a sample — for the
withheld columns (ADR-0025 D6) and for register IDs.

Not a test module (no ``test_`` prefix), so pytest does not collect it; it is
imported the way ``migration_harness`` is.
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Final

import sqlalchemy as sa
from fastapi import FastAPI
from fastapi.testclient import TestClient
from httpx import Response
from pydantic import SecretStr
from smartmatch_api.config import Settings, get_settings
from smartmatch_api.errors import EXCEPTION_HANDLERS
from smartmatch_api.exercise_dependencies import EXERCISE_REQUEST_HEADER
from smartmatch_api.main import routers_for
from smartmatch_api.routers.exercise_results_models import simulation_event, simulation_profiles
from smartmatch_domain.exercise.asking import AskingChoice
from smartmatch_domain.exercise.simulation import (
    SimulationProfile,
    SimulationResult,
    require_coefficients,
    run_email_everyone,
    simulate_results,
)
from smartmatch_domain.product_scope import ProductScope
from smartmatch_domain.student_factors.factors import (
    CAREER_GOAL_FIT_FACTOR_KEY,
    PAST_EVENT_TOPIC_OVERLAP_FACTOR_KEY,
    SAME_MAJOR_FACTOR_KEY,
    STATED_INTEREST_OVERLAP_FACTOR_KEY,
)
from smartmatch_persistence.exercise import schema
from smartmatch_persistence.exercise.dataset_repository import ExerciseDatasetRepository
from smartmatch_persistence.exercise.team_view_repository import ExerciseTeamViewRepository
from sqlalchemy.orm import Session, sessionmaker

#: Not real keys, and assembled from pieces for the reason the other exercise
#: files give: ``tools/scan_forbidden.py`` matches the shape of a committed
#: credential.
_SECRET: Final[str] = "-".join(("integration", "only", "full", "class", "run", "key"))
_PASSCODE: Final[str] = "-".join(("integration", "only", "class", "passcode"))

HEADER: Final[dict[str, str]] = {EXERCISE_REQUEST_HEADER: "1"}
TEAM_BASE: Final[str] = "/v1/exercise/workspaces/current"
INSTRUCTOR_BASE: Final[str] = "/v1/exercise/instructor"

#: Northline and Harbor in Ann's 300-row file: the two exercise events, in
#: file order. ``test_the_fixture_has_the_two_rounds_this_file_names`` checks
#: the file still says so.
ROUND_ONE: Final[str] = "E11"
ROUND_TWO: Final[str] = "E12"


@dataclass(frozen=True, slots=True)
class Exchange:
    """One request any client sent, and the response it got."""

    method: str
    path: str
    status: int
    text: str


class RecordingClient(TestClient):
    """A ``TestClient`` that appends every exchange to a shared log.

    ``httpx.Client.get``/``post``/``put`` all end in :meth:`request`, so
    overriding it here records every call without wrapping each verb.
    """

    def __init__(self, app: FastAPI, log: list[Exchange]) -> None:
        super().__init__(app)
        self._log = log

    def request(self, method: str, url: Any, *args: Any, **kwargs: Any) -> Response:  # type: ignore[override]
        response = super().request(method, url, *args, **kwargs)
        self._log.append(Exchange(method, str(url), response.status_code, response.text))
        return response


def exercise_settings() -> Settings:
    """The class-exercise process's settings, with the test's own keys."""
    return Settings(
        product_scope=ProductScope.CLASS_EXERCISE,
        exercise_workspace_secret=SecretStr(_SECRET),
        exercise_instructor_passcode=SecretStr(_PASSCODE),
        exercise_cookie_secure=False,
    )


def build_app(session_factory: sessionmaker[Session]) -> FastAPI:
    """The exercise process's routes over a real session factory."""
    settings = exercise_settings()
    app = FastAPI()
    for exception_type, handler in EXCEPTION_HANDLERS.items():
        app.add_exception_handler(exception_type, handler)
    for router in routers_for(settings):
        app.include_router(router)
    app.state.session_factory = session_factory
    app.dependency_overrides[get_settings] = lambda: settings
    return app


def instructor(app: FastAPI, log: list[Exchange]) -> RecordingClient:
    """A client holding a live instructor session."""
    client = RecordingClient(app, log)
    response = client.post(f"{INSTRUCTOR_BASE}/login", json={"passcode": _PASSCODE}, headers=HEADER)
    assert response.status_code == 200, response.text
    return client


def enter(app: FastAPI, log: list[Exchange], team_number: int) -> RecordingClient:
    """A client that has entered ``team_number`` and holds its cookie."""
    client = RecordingClient(app, log)
    response = client.post(
        "/v1/exercise/workspaces", json={"team_number": team_number}, headers=HEADER
    )
    assert response.status_code == 200, response.text
    return client


def weightings(team_number: int) -> dict[str, dict[str, float]]:
    """Three named weightings a team saves, different for every team.

    Each team leans on one factor by its own amount, so six teams build six
    different lists rather than six copies of one.
    """
    lean = float(team_number)
    return {
        "balanced": {
            SAME_MAJOR_FACTOR_KEY: 1.0,
            STATED_INTEREST_OVERLAP_FACTOR_KEY: 1.0,
            CAREER_GOAL_FIT_FACTOR_KEY: 1.0,
            PAST_EVENT_TOPIC_OVERLAP_FACTOR_KEY: 1.0,
        },
        "interests first": {
            SAME_MAJOR_FACTOR_KEY: 1.0,
            STATED_INTEREST_OVERLAP_FACTOR_KEY: 1.0 + lean,
            CAREER_GOAL_FIT_FACTOR_KEY: 2.0,
            PAST_EVENT_TOPIC_OVERLAP_FACTOR_KEY: 0.5,
        },
        "majors first": {
            SAME_MAJOR_FACTOR_KEY: 1.0 + lean,
            STATED_INTEREST_OVERLAP_FACTOR_KEY: 0.5,
            CAREER_GOAL_FIT_FACTOR_KEY: 1.0,
            PAST_EVENT_TOPIC_OVERLAP_FACTOR_KEY: 1.0,
        },
    }


def final_setting(team_number: int) -> str:
    """The setting a team picks as final; two teams per setting."""
    names = sorted(weightings(team_number))
    return names[(team_number - 1) % len(names)]


def asking_choice(team_number: int) -> AskingChoice:
    """The way a team asks for more; two teams per choice."""
    choices = list(AskingChoice)
    return choices[(team_number - 1) % len(choices)]


def prepare_round(client: RecordingClient, event_key: str, team_number: int) -> list[int]:
    """Set weights, save three settings, compare two, and read the final list.

    Returns the profile numbers the final setting's list shows, in order — the
    people the team is about to invite.
    """
    named = weightings(team_number)
    first = client.get(f"{TEAM_BASE}/events/{event_key}/list", params=named["balanced"])
    assert first.status_code == 200, first.text
    for name, weights in named.items():
        saved = client.put(
            f"{TEAM_BASE}/events/{event_key}/settings/{name}",
            json={"weights": weights},
            headers=HEADER,
        )
        assert saved.status_code == 200, saved.text
    compared = client.get(
        f"{TEAM_BASE}/events/{event_key}/settings/compare",
        params={"a": "balanced", "b": final_setting(team_number)},
    )
    assert compared.status_code == 200, compared.text
    final = client.get(
        f"{TEAM_BASE}/events/{event_key}/list", params={"setting": final_setting(team_number)}
    )
    assert final.status_code == 200, final.text
    return [int(entry["profile_no"]) for entry in final.json()["entries"]]


def run(client: RecordingClient, event_key: str, team_number: int) -> Response:
    """Run results for one event on the team's final setting."""
    return client.post(
        f"{TEAM_BASE}/events/{event_key}/results",
        json={"setting_name": final_setting(team_number)},
        headers=HEADER,
    )


def unlock(client: RecordingClient, event_key: str) -> None:
    response = client.post(f"{INSTRUCTOR_BASE}/events/{event_key}/unlock", headers=HEADER)
    assert response.status_code == 200, response.text


@dataclass(frozen=True, slots=True)
class WorkspaceRow:
    id: uuid.UUID
    dataset_id: uuid.UUID
    seed: int


def workspace_row(sessions: sessionmaker[Session], team_number: int) -> WorkspaceRow:
    """The one team workspace for ``team_number`` (one data file in this test)."""
    table = schema.exercise_team_workspace
    with sessions() as session:
        row = session.execute(
            sa.select(table.c.id, table.c.dataset_id, table.c.seed).where(
                table.c.team_number == team_number
            )
        ).one()
    return WorkspaceRow(id=row.id, dataset_id=row.dataset_id, seed=int(row.seed))


def set_seed(sessions: sessionmaker[Session], workspace_id: uuid.UUID, seed: int) -> None:
    """Put a chosen seed on one team, the way a reset puts a random one."""
    table = schema.exercise_team_workspace
    with sessions() as session:
        session.execute(sa.update(table).where(table.c.id == workspace_id).values(seed=seed))
        session.commit()


def rule_inputs(
    sessions: sessionmaker[Session], team_number: int
) -> tuple[tuple[SimulationProfile, ...], WorkspaceRow]:
    """Everybody as the rule reads them for this team, from the stored rows.

    The same two reads the run route makes — the withheld-column load and this
    team's view for who stopped answering — so a result recomputed from these
    is the rule applied to what the database holds, not to a copy.
    """
    workspace = workspace_row(sessions, team_number)
    with sessions() as session:
        rows = ExerciseDatasetRepository().load_simulation_profiles(
            session, dataset_id=workspace.dataset_id
        )
        view = ExerciseTeamViewRepository().list_team_profiles(
            session, dataset_id=workspace.dataset_id, workspace_id=workspace.id
        )
    silent = frozenset(profile.profile_no for profile in view if profile.non_responding)
    return simulation_profiles(rows, non_responding_profile_nos=silent), workspace


def rule_event(sessions: sessionmaker[Session], event_key: str) -> Any:
    """One stored event as the rule reads it."""
    with sessions() as session:
        dataset_id = session.execute(sa.select(schema.exercise_dataset.c.id)).scalar_one()
        events = ExerciseDatasetRepository().list_events(session, dataset_id=dataset_id)
    (event,) = [row for row in events if row.event_key == event_key]
    return simulation_event(event)


def recompute(
    sessions: sessionmaker[Session],
    team_number: int,
    event_key: str,
    invited: list[int],
    *,
    seed: int | None = None,
) -> tuple[SimulationResult, SimulationResult]:
    """The rule on this team's seed and list, outside the route."""
    everybody, workspace = rule_inputs(sessions, team_number)
    event = rule_event(sessions, event_key)
    wanted = set(invited)
    use_seed = workspace.seed if seed is None else seed
    coefficients = require_coefficients()
    team = simulate_results(
        tuple(profile for profile in everybody if profile.profile_no in wanted),
        event,
        seed=use_seed,
        coefficients=coefficients,
        invite_limit=len(wanted),
    )
    everyone = run_email_everyone(everybody, event, seed=use_seed, coefficients=coefficients)
    return team, everyone


def panel_of(result: SimulationResult) -> dict[str, list[int]]:
    """A domain result in the response's panel shape (profile numbers only)."""
    return {
        "invited_profile_nos": list(result.invited),
        "signed_up_profile_nos": list(result.signed_up),
        "attended_profile_nos": list(result.attended),
    }


def numbers_of(panel: Mapping[str, Any]) -> dict[str, list[int]]:
    """A response panel without its counts, for comparing with :func:`panel_of`."""
    return {key: list(panel[key]) for key in panel_of(SimulationResult((), (), ()))}


def team_snapshot(
    team: RecordingClient, teacher: RecordingClient, team_number: int
) -> dict[str, tuple[int, Any]]:
    """Everything a team or the instructor can read about one team."""
    paths = {
        "workspace": (team, "/v1/exercise/workspaces/current"),
        "asking": (team, f"{TEAM_BASE}/asking-choice"),
        "detail": (teacher, f"{INSTRUCTOR_BASE}/workspaces/{team_number}"),
    }
    for event_key in (ROUND_ONE, ROUND_TWO):
        paths[f"results {event_key}"] = (team, f"{TEAM_BASE}/events/{event_key}/results")
        paths[f"settings {event_key}"] = (team, f"{TEAM_BASE}/events/{event_key}/settings")
        paths[f"list {event_key}"] = (team, f"{TEAM_BASE}/events/{event_key}/list")
    snapshot: dict[str, tuple[int, Any]] = {}
    for label, (client, path) in paths.items():
        response = client.get(path)
        snapshot[label] = (response.status_code, response.json())
        if label.startswith("list "):
            csv = client.get(f"{path}.csv")
            snapshot[f"{label}.csv"] = (csv.status_code, csv.text)
    overview = teacher.get(f"{INSTRUCTOR_BASE}/workspaces")
    rows = [row for row in overview.json()["teams"] if row["team_number"] == team_number]
    snapshot["overview row"] = (overview.status_code, rows)
    return snapshot


#: Read-only routes a class's screens call that the walk above does not
#: otherwise reach. Fetched once each so the whole-class leak scan covers them,
#: along with the published OpenAPI description (FastAPI publishes handler
#: docstrings and field descriptions there).
TEAM_READS: Final[tuple[str, ...]] = (
    f"{TEAM_BASE}/events",
    f"{TEAM_BASE}/events/{ROUND_ONE}/list.csv",
    f"{TEAM_BASE}/events/{ROUND_TWO}/list.csv",
)
INSTRUCTOR_READS: Final[tuple[str, ...]] = (
    f"{INSTRUCTOR_BASE}/workspaces",
    f"{INSTRUCTOR_BASE}/events",
    f"{INSTRUCTOR_BASE}/datasets",
    "/openapi.json",
)


def read_everything(team: RecordingClient, teacher: RecordingClient) -> None:
    """GET every read-only route in :data:`TEAM_READS` and :data:`INSTRUCTOR_READS`."""
    for path in TEAM_READS:
        response = team.get(path)
        assert response.status_code == 200, (path, response.text)
    for path in INSTRUCTOR_READS:
        response = teacher.get(path)
        assert response.status_code == 200, (path, response.text)
