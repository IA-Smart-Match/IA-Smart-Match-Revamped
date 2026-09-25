"""The results screen's routes (CE-RESULTS-API, design spec §9–§13).

What is pinned here, in the order the failures would hurt:

1. **The three rules.** A locked event refuses; a second run is refused with the
   sentence design spec §9 writes out, byte for byte; a refresh needs the choice
   and is allowed once.
2. **OQ-CE-03 stays open.** With no confirmed coefficients the run route refuses
   with the domain's own sentence — which is this route *working*. Every test
   that needs a result injects a clearly-labelled test-only coefficient set
   through ``monkeypatch``; no value is written into any source file.
3. **Determinism and the shared seed.** The same inputs and the same seed give
   the same panels, and "email everyone" agrees with the team's own list on
   every profile they share — which is what makes them a comparison.
4. **Isolation.** One team's refresh changes one team's overlay.
5. **Nothing a response may never carry**: a schema walk over every model in
   both modules, over the handlers' docstrings — FastAPI publishes those as
   operation descriptions — and over the whole exercise-scope OpenAPI document,
   refusing ``hidden_true_interests`` (ADR-0025 D6) and anything score-shaped
   (D8).

The database half — the one-run rule as a UNIQUE constraint against two
concurrent runs, the lock order, and a reset clearing the rows it says it clears
— is in ``tests/integration/test_exercise_results_persistence.py``. A fake
repository cannot prove a constraint.
"""

from __future__ import annotations

import ast
import uuid
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel
from smartmatch_api.config import Settings
from smartmatch_api.errors import EXCEPTION_HANDLERS
from smartmatch_api.exercise_dependencies import (
    EXERCISE_REQUEST_HEADER,
    INSTRUCTOR_COOKIE_NAME,
    RefreshCandidate,
    RefreshCounts,
    ResultPanel,
    StoredResultRun,
    TeamResultsState,
    get_active_dataset,
    get_dataset_repository,
    get_exercise_session,
    get_results_repository,
    get_settings_repository,
    get_team_view_repository,
    get_workspace_repository,
    get_workspace_secret,
)
from smartmatch_api.main import CAPABILITY_SCOPED_ROUTERS, routers_for
from smartmatch_api.routers import (
    exercise_instructor_refresh,
    exercise_results,
    exercise_results_models,
    exercise_results_refresh,
    exercise_results_run,
)
from smartmatch_api.routers.exercise_matching_models import (
    event_evidence,
    rankable_set,
)
from smartmatch_api.routers.exercise_results_models import (
    EXERCISE_ROUNDS,
    FIRST_ROUND,
    MAX_ASKING_CHOICE_CHARACTERS,
    round_of,
)
from smartmatch_api.routers.exercise_results_refresh import (
    invited_without_a_card,
    refresh_plan,
)
from smartmatch_domain.exercise import EXERCISE_WITHHELD_FIELDS
from smartmatch_domain.exercise.asking import (
    CARD_COMPLETION_SHARE,
    COPIED_CARD_CAREER_GOAL,
    REQUIRED_NON_RESPONDING_SHARE,
    AskingChoice,
    CopiedCardCareerGoal,
    copied_card_career_goal,
)
from smartmatch_domain.exercise.instructor_session import mint_instructor_session
from smartmatch_domain.exercise.registry import EXERCISE_DEFAULT_WEIGHTS
from smartmatch_domain.exercise.simulation import (
    EVENT_SEATS,
    EXISTING_SIGNUPS,
    SimulationCoefficients,
    SimulationProfile,
)
from smartmatch_domain.exercise.workspace_token import (
    derive_workspace_token,
    hash_workspace_token,
)
from smartmatch_domain.product_scope import Capability, ProductScope
from smartmatch_domain.student_factors import career_goal_fit
from smartmatch_persistence.exercise.dataset_repository import (
    DatasetSummary,
    ExerciseEventRow,
    SimulationProfileRow,
)
from smartmatch_persistence.exercise.results_repository import (
    ALREADY_RUN_SENTENCE,
    AlreadyRunError,
)
from smartmatch_persistence.exercise.settings_repository import SavedSetting
from smartmatch_persistence.exercise.team_view_repository import TeamProfileRow
from smartmatch_persistence.exercise.workspace_repository import (
    ExerciseDatasetSummary,
    ExerciseWorkspace,
)

_ROUTER_SOURCE = Path(exercise_results.__file__)
_MODELS_SOURCE = Path(exercise_results_models.__file__)
_REFRESH_SOURCE = Path(exercise_results_refresh.__file__)
_RUN_SOURCE = Path(exercise_results_run.__file__)
_INSTRUCTOR_SOURCE = Path(exercise_instructor_refresh.__file__)

#: Every module this track owns on the router side, and the files they live in.
#:
#: **One** list, derived twice, because review round 1's carry-over item (a) was
#: exactly the drift between two such lists on the matching track: its model walk
#: read two of four modules while its source walks read all four, so a response
#: model declared in either of the other two met no D6 or D8 check.
#: ``test_the_model_walk_reads_every_module_the_source_walks_read`` is the guard.
_TRACK_MODULES = (
    exercise_results,
    exercise_results_models,
    exercise_results_refresh,
    exercise_results_run,
    exercise_instructor_refresh,
)
_TRACK_SOURCES = tuple(Path(module.__file__ or "") for module in _TRACK_MODULES)

#: Assembled from pieces rather than written as one literal, for the reason the
#: other exercise test files give: ``tools/scan_forbidden.py`` matches the shape
#: of a committed credential, and a gate with an exception for a test file is a
#: gate that has learned to be waved through.
_TEST_SECRET = "-".join(("exercise", "results", "key", "for", "tests", "only"))
_TEST_PASSCODE = "-".join(("exercise", "results", "passcode", "for", "tests"))

_DATASET_ID = uuid.UUID("44444444-4444-4444-4444-444444444444")
_CHECKSUM = "c" * 64
_INVITE_LIMIT = 6
_WHEN = datetime(2026, 9, 20, 9, 0, tzinfo=UTC)

_DATASET = ExerciseDatasetSummary(
    id=_DATASET_ID, label="Made-up student body (sample)", invite_limit=_INVITE_LIMIT
)

_SUMMARY = DatasetSummary(
    dataset_id=_DATASET_ID,
    label=_DATASET.label,
    source_filename="sample.csv",
    uploaded_at=_WHEN,
    row_count=12,
    checksum=_CHECKSUM,
    invite_limit=_INVITE_LIMIT,
    license_line=None,
    event_count=3,
)

#: **Test-only coefficients (OQ-CE-03 is OPEN).** Not a proposal, not a default,
#: and never read from source: the exercise ships ``None`` and
#: ``require_coefficients`` refuses, which is the behaviour
#: ``test_a_run_refuses_while_the_rule_has_no_confirmed_coefficients`` pins.
#: These exist so the *rest* of the path can be exercised, and every test that
#: uses them injects them through ``monkeypatch`` onto the domain module.
#:
#: The values are chosen to make the rule produce a mixture rather than all or
#: nothing, and they satisfy the ordering the domain enforces: the true-fit lift
#: exceeds both the frequent-attender lift and the same-major lift.
_TEST_ONLY_COEFFICIENTS = SimulationCoefficients(
    base_signup_rate=0.40,
    true_fit_lift=0.45,
    frequent_attender_lift=0.10,
    same_major_lift=0.05,
    chance_spread=0.10,
    attend_given_signup=0.90,
    frequent_attender_events=1,
    true_interest_share_of_fit=0.60,
)

_PAST = ExerciseEventRow(
    event_key="past-analytics",
    name="An earlier analytics evening",
    topic_tags=("analytics",),
    target_majors=("Alpha",),
    is_exercise_event=False,
    sequence=1,
)

_ROUND_ONE = ExerciseEventRow(
    event_key="round-one",
    name="The first round",
    topic_tags=("analytics", "brand"),
    target_majors=("Alpha",),
    is_exercise_event=True,
    sequence=11,
)

_ROUND_TWO = ExerciseEventRow(
    event_key="round-two",
    name="The second round",
    topic_tags=("brand", "outreach"),
    target_majors=("Alpha",),
    is_exercise_event=True,
    sequence=12,
)

_EVENTS: tuple[ExerciseEventRow, ...] = (_PAST, _ROUND_ONE, _ROUND_TWO)


@dataclass(frozen=True, slots=True)
class _Row:
    """One made-up profile, in both the shapes the two repositories return.

    Written once and projected twice so the team's view and the simulation's
    view cannot drift apart in the fixture — which is exactly the drift the real
    schema prevents by storing one row and projecting it two ways.

    ``major`` and ``class_year`` are deliberately ``"Alpha"``/``"One"`` rather
    than any real vocabulary: OQ-CE-01 is open and this file names no year and no
    major a data file might actually carry.
    """

    profile_no: int
    display_name: str
    major: str | None = "Alpha"
    class_year: str | None = "One"
    past_event_keys: tuple[str, ...] = ()
    stated_interests: tuple[str, ...] | None = None
    career_goal: str | None = None
    hidden_true_interests: tuple[str, ...] = ()

    def team_row(self) -> TeamProfileRow:
        return TeamProfileRow(
            profile_no=self.profile_no,
            display_name=self.display_name,
            major=self.major,
            class_year=self.class_year,
            past_event_keys=self.past_event_keys,
            stated_interests=self.stated_interests,
            career_goal=self.career_goal,
            overlay_added_event_topics=(),
            overlay_card_interests=None,
            overlay_card_career_goal=None,
            non_responding=False,
        )

    def simulation_row(self) -> SimulationProfileRow:
        return SimulationProfileRow(
            profile_no=self.profile_no,
            display_name=self.display_name,
            major=self.major,
            class_year=self.class_year,
            past_event_keys=self.past_event_keys,
            stated_interests=self.stated_interests,
            career_goal=self.career_goal,
            hidden_true_interests=self.hidden_true_interests,
        )


#: Twelve fictional rows: eleven that can take a place on a list and one the data
#: file records no major for. Only two carry a card, so at least four of any six
#: invited have none — which is what makes design spec §13's two shares land on
#: somebody in every run of these tests.
_ROWS: tuple[_Row, ...] = (
    _Row(1, "Avery Brooks", stated_interests=("analytics",), hidden_true_interests=("analytics",)),
    _Row(2, "Bao Nguyen", stated_interests=("brand",), hidden_true_interests=("brand",)),
    _Row(3, "Cam Ellis", past_event_keys=("past-analytics",), hidden_true_interests=("analytics",)),
    _Row(4, "Devi Rao", hidden_true_interests=("brand",), career_goal="analytics"),
    _Row(5, "Emery Vale", past_event_keys=("past-analytics",), hidden_true_interests=("outreach",)),
    _Row(6, "Fen Liu", hidden_true_interests=("analytics", "brand")),
    _Row(7, "Gita Shah", hidden_true_interests=()),
    _Row(8, "Hal Ortiz", hidden_true_interests=("brand",)),
    _Row(9, "Ivy Chen", past_event_keys=("past-analytics",), hidden_true_interests=("analytics",)),
    _Row(10, "Jo Park", hidden_true_interests=("outreach",)),
    _Row(11, "Kit Alvarez", hidden_true_interests=("brand",), career_goal="brand"),
    _Row(12, "Lee Osei", major=None, class_year=None),
)

_PROFILES: tuple[TeamProfileRow, ...] = tuple(row.team_row() for row in _ROWS)
_SIMULATION_ROWS: tuple[SimulationProfileRow, ...] = tuple(row.simulation_row() for row in _ROWS)


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


class _FakeWorkspaceRepository:
    """Enough of ``ExerciseWorkspaceRepository`` to run the entry route."""

    def __init__(self) -> None:
        self.rows: dict[tuple[uuid.UUID, int], ExerciseWorkspace] = {}
        self.seeds: dict[uuid.UUID, int] = {}
        #: The seed every team is given unless a test says otherwise. One value
        #: for every team so that "two teams with one seed agree" is a test this
        #: file can write without reaching into the database.
        self.seed_for_every_team = 987_654_321

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
            workspace = ExerciseWorkspace(
                id=uuid.uuid4(),
                dataset_id=dataset_id,
                team_number=team_number,
                dataset_label=_DATASET.label,
                invite_limit=_DATASET.invite_limit,
            )
            self.rows[key] = workspace
            self.seeds[workspace.id] = self.seed_for_every_team
        return self.rows[key]

    def entry_dataset_for(self, _session: object, *, team_number: int) -> uuid.UUID | None:
        own = [key for key in self.rows if key[1] == team_number]
        if own:
            return own[-1][0]
        every = list(self.rows)
        return every[-1][0] if every else _DATASET.id

    def find_by_token_hash(self, _session: object, *, token_hash: str) -> ExerciseWorkspace | None:
        for workspace in self.rows.values():
            expected = hash_workspace_token(
                derive_workspace_token(secret=_TEST_SECRET, workspace_id=workspace.id)
            )
            if token_hash == expected:
                return workspace
        return None


class _FakeDatasetRepository:
    """The three reads the results routes make of a data file."""

    def __init__(self) -> None:
        self.simulation_loads = 0

    def list_events(
        self, _session: object, *, dataset_id: uuid.UUID
    ) -> tuple[ExerciseEventRow, ...]:
        return _EVENTS if dataset_id == _DATASET_ID else ()

    def get_dataset_summary(
        self, _session: object, *, dataset_id: uuid.UUID
    ) -> DatasetSummary | None:
        return _SUMMARY if dataset_id == _DATASET_ID else None

    def load_simulation_profiles(
        self, _session: object, *, dataset_id: uuid.UUID
    ) -> tuple[SimulationProfileRow, ...]:
        self.simulation_loads += 1
        return _SIMULATION_ROWS if dataset_id == _DATASET_ID else ()


class _FakeTeamViewRepository:
    """Design spec §2's ``base row ⟕ overlay``, over a dict keyed on the workspace."""

    def __init__(self) -> None:
        self.overlays: dict[tuple[uuid.UUID, int], TeamProfileRow] = {}

    def list_team_profiles(
        self, _session: object, *, dataset_id: uuid.UUID, workspace_id: uuid.UUID
    ) -> tuple[TeamProfileRow, ...]:
        assert dataset_id == _DATASET_ID
        return tuple(
            self.overlays.get((workspace_id, profile.profile_no), profile) for profile in _PROFILES
        )


class _FakeSettingsRepository:
    """Only the one read the results route makes: a saved weighting by name."""

    def __init__(self) -> None:
        self.rows: dict[tuple[uuid.UUID, str, str], SavedSetting] = {}

    def get_setting(
        self, _session: object, *, workspace_id: uuid.UUID, event_key: str, name: str
    ) -> SavedSetting | None:
        return self.rows.get((workspace_id, event_key, name))


class _FakeResultsRepository:
    """The results repository's behaviour, minus the lock the database provides.

    The one-run rule, the once-only choice and the once-only refresh are
    re-implemented rather than stubbed out, because the routes' behaviour around
    them — which status, which sentence, and what a second press gets — is what
    this file is for. That two concurrent runs cannot both pass is the
    integration file's, where there is a real constraint.
    """

    def __init__(
        self,
        workspaces: _FakeWorkspaceRepository,
        datasets: _FakeDatasetRepository,
        team_view: _FakeTeamViewRepository,
    ) -> None:
        self.workspaces = workspaces
        self.datasets = datasets
        self.team_view = team_view
        self.unlocked: set[tuple[uuid.UUID, str]] = set()
        self.runs: dict[tuple[uuid.UUID, str], StoredResultRun] = {}
        self.choices: dict[uuid.UUID, str] = {}
        self.refreshed: dict[uuid.UUID, datetime] = {}

    # -- reads --------------------------------------------------------------

    def results_unlocked(self, _session: object, *, dataset_id: uuid.UUID, event_key: str) -> bool:
        return (dataset_id, event_key) in self.unlocked

    def team_state(self, _session: object, *, workspace_id: uuid.UUID) -> TeamResultsState | None:
        if workspace_id not in self.workspaces.seeds:
            return None
        return TeamResultsState(
            seed=self.workspaces.seeds[workspace_id],
            asking_choice=self.choices.get(workspace_id),
            refreshed_at=self.refreshed.get(workspace_id),
        )

    def get_run(
        self, _session: object, *, workspace_id: uuid.UUID, event_key: str
    ) -> StoredResultRun | None:
        return self.runs.get((workspace_id, event_key))

    def get_run_for_round(
        self, _session: object, *, workspace_id: uuid.UUID, round_number: int
    ) -> StoredResultRun | None:
        for (held_by, _), run in self.runs.items():
            if held_by == workspace_id and run.round == round_number:
                return run
        return None

    def workspaces_awaiting_refresh(self, _session: object) -> tuple[RefreshCandidate, ...]:
        return tuple(
            RefreshCandidate(
                workspace_id=workspace.id,
                dataset_id=workspace.dataset_id,
                team_number=workspace.team_number,
                asking_choice=self.choices[workspace.id],
                seed=self.workspaces.seeds[workspace.id],
            )
            for workspace in sorted(self.workspaces.rows.values(), key=lambda row: row.team_number)
            if workspace.id in self.choices and workspace.id not in self.refreshed
        )

    # -- writes -------------------------------------------------------------

    def record_run(
        self,
        _session: object,
        *,
        dataset_id: uuid.UUID,
        workspace_id: uuid.UUID,
        event_key: str,
        round_number: int,
        setting_name: str | None,
        team: ResultPanel,
        email_everyone: ResultPanel,
        seats_empty: int,
    ) -> StoredResultRun:
        assert dataset_id == _DATASET_ID
        if (workspace_id, event_key) in self.runs:
            raise AlreadyRunError
        stored = StoredResultRun(
            event_key=event_key,
            round=round_number,
            setting_name=setting_name,
            team=team,
            email_everyone=email_everyone,
            seats_empty=seats_empty,
            created_at=_WHEN,
        )
        self.runs[(workspace_id, event_key)] = stored
        return stored

    def choose_asking(self, _session: object, *, workspace_id: uuid.UUID, choice: str) -> bool:
        if workspace_id in self.choices:
            return False
        self.choices[workspace_id] = choice
        return True

    def apply_refresh(
        self,
        _session: object,
        *,
        dataset_id: uuid.UUID,
        workspace_id: uuid.UUID,
        added_topics: Sequence[str],
        topic_gainers: Sequence[int],
        card_profile_nos: Sequence[int],
        non_responding_profile_nos: Sequence[int],
        now: datetime,
        career_goal_policy: CopiedCardCareerGoal = COPIED_CARD_CAREER_GOAL,
    ) -> RefreshCounts | None:
        assert dataset_id == _DATASET_ID
        if workspace_id not in self.choices or workspace_id in self.refreshed:
            return None
        self.refreshed[workspace_id] = now
        chosen = [
            row
            for row in self.datasets.load_simulation_profiles(None, dataset_id=dataset_id)
            if row.profile_no in set(card_profile_nos)
        ]
        cards = {row.profile_no: row.hidden_true_interests for row in chosen}
        #: OQ-CE-13, mirrored from ``results_cards.copied_cards`` so the fake and
        #: the real one cannot disagree about what a copied card says — including
        #: the ``None`` entries being **dropped** rather than written, which is
        #: what makes "a policy that says nothing writes no statement" true on
        #: this side too.
        goals = {
            row.profile_no: goal
            for row in chosen
            if (goal := copied_card_career_goal(row.career_goal, career_goal_policy)) is not None
        }
        for profile_no in sorted(set(topic_gainers)):
            self._patch(workspace_id, profile_no, overlay_added_event_topics=tuple(added_topics))
        for profile_no, interests in sorted(cards.items()):
            self._patch(workspace_id, profile_no, overlay_card_interests=interests)
        for profile_no, goal in sorted(goals.items()):
            self._patch(workspace_id, profile_no, overlay_card_career_goal=goal)
        for profile_no in sorted(set(non_responding_profile_nos)):
            self._patch(workspace_id, profile_no, non_responding=True)
        return RefreshCounts(
            cards_completed=len(cards),
            non_responding=len(set(non_responding_profile_nos)),
            topics_added=len(set(topic_gainers)),
        )

    def _patch(self, workspace_id: uuid.UUID, profile_no: int, **changes: object) -> None:
        """Merge one overlay change, the way three narrow upserts do."""
        key = (workspace_id, profile_no)
        current = self.team_view.overlays.get(key, _PROFILES[profile_no - 1])
        self.team_view.overlays[key] = replace(current, **changes)  # type: ignore[arg-type]


class _FakeSession:
    """A session that can be committed and answers every read with nothing."""

    def __init__(self) -> None:
        self.commits = 0

    def commit(self) -> None:
        self.commits += 1

    def execute(self, _statement: object) -> object:
        raise AssertionError("a results route issued a query of its own")


class _Fakes:
    """Every fake one app is wired with, so a test can reach them by name."""

    def __init__(self) -> None:
        self.workspaces = _FakeWorkspaceRepository()
        self.datasets = _FakeDatasetRepository()
        self.team_view = _FakeTeamViewRepository()
        self.settings = _FakeSettingsRepository()
        self.results = _FakeResultsRepository(self.workspaces, self.datasets, self.team_view)

    def unlock(self, *event_keys: str) -> None:
        for event_key in event_keys:
            self.results.unlocked.add((_DATASET_ID, event_key))


def _settings() -> Settings:
    return Settings(
        product_scope=ProductScope.CLASS_EXERCISE,
        exercise_workspace_secret=_TEST_SECRET,
        exercise_instructor_passcode=_TEST_PASSCODE,
        exercise_cookie_secure=False,
    )


def _exercise_app(fakes: _Fakes) -> FastAPI:
    """The exercise process's routes, with the database replaced and nothing else."""
    app = FastAPI()
    for exception_type, handler in EXCEPTION_HANDLERS.items():
        app.add_exception_handler(exception_type, handler)
    for router in routers_for(_settings()):
        app.include_router(router)
    session = _FakeSession()
    app.dependency_overrides[get_exercise_session] = lambda: session
    app.dependency_overrides[get_workspace_repository] = lambda: fakes.workspaces
    app.dependency_overrides[get_dataset_repository] = lambda: fakes.datasets
    app.dependency_overrides[get_team_view_repository] = lambda: fakes.team_view
    app.dependency_overrides[get_settings_repository] = lambda: fakes.settings
    app.dependency_overrides[get_results_repository] = lambda: fakes.results
    app.dependency_overrides[get_active_dataset] = lambda: _DATASET
    app.dependency_overrides[get_workspace_secret] = lambda: _TEST_SECRET
    return app


@pytest.fixture
def fakes() -> _Fakes:
    return _Fakes()


@pytest.fixture
def confirmed(monkeypatch: pytest.MonkeyPatch) -> SimulationCoefficients:
    """Inject **test-only** coefficients, because OQ-CE-03 has no answer.

    Patched onto the domain module rather than written into it: the shipped
    value is ``None`` and must stay ``None`` until Ann confirms, which
    ``test_the_exercise_still_ships_no_coefficients`` asserts on the source.
    """
    monkeypatch.setattr(
        "smartmatch_domain.exercise.simulation.EXERCISE_SIMULATION_COEFFICIENTS",
        _TEST_ONLY_COEFFICIENTS,
    )
    return _TEST_ONLY_COEFFICIENTS


def _entered(fakes: _Fakes, team_number: int) -> TestClient:
    """A client that has entered a team number, holds its cookie, and has a final setting.

    The final setting is saved for both rounds **with the course's starting
    values**, so every run below names one (Ann to Chau, Discord, 2026-09-24:
    the team chooses one final setting before it runs) and the list it builds
    is the list the default route shows — which keeps each comparison against
    ``…/list`` a comparison of like with like.
    """
    client = TestClient(_exercise_app(fakes))
    response = client.post(
        "/v1/exercise/workspaces",
        json={"team_number": team_number},
        headers=_HEADER,
    )
    assert response.status_code == 200, response.text
    workspace = fakes.workspaces.rows[(_DATASET_ID, team_number)]
    for event_key in ("round-one", "round-two"):
        fakes.settings.rows[(workspace.id, event_key, _FINAL)] = SavedSetting(
            event_key=event_key,
            name=_FINAL,
            weights=dict(EXERCISE_DEFAULT_WEIGHTS),
            created_at=_WHEN,
        )
    return client


@pytest.fixture
def client(fakes: _Fakes) -> Iterator[TestClient]:
    with _entered(fakes, 1) as entered:
        yield entered


_BASE = "/v1/exercise/workspaces/current"
_RESULTS = f"{_BASE}/events/round-one/results"
_RESULTS_TWO = f"{_BASE}/events/round-two/results"
_ASKING = f"{_BASE}/asking-choice"
_REFRESH = f"{_BASE}/refresh"
_REFRESH_ALL = "/v1/exercise/instructor/refresh-all"
_HEADER = {EXERCISE_REQUEST_HEADER: "1"}

#: The saved setting every entered team holds for both rounds (see ``_entered``).
_FINAL = "final"
_FINAL_BODY = {"setting_name": _FINAL}

#: The sentence a run without a final setting is refused with. Written out here
#: because it is the owner's rule in a team's words, compared byte for byte.
_FINAL_SETTING_SENTENCE = (
    "Choose one of your saved settings as your final setting before running results."
)


def _run(client: TestClient, path: str = _RESULTS, **body: object) -> object:
    return client.post(path, json=body or {}, headers=_HEADER)


# ---------------------------------------------------------------------------
# OQ-CE-03 — the coefficients are not decided, and that is the behaviour
# ---------------------------------------------------------------------------


def test_a_run_refuses_while_the_rule_has_no_confirmed_coefficients(
    fakes: _Fakes, client: TestClient
) -> None:
    """No ``confirmed`` fixture here, deliberately: this is what ships today."""
    fakes.unlock("round-one")

    response = client.post(_RESULTS, json=_FINAL_BODY, headers=_HEADER)

    assert response.status_code == 409
    body = response.json()["error"]
    assert body["code"] == "exercise_results_rule_not_confirmed"
    assert body["message"] == "The results rule has no confirmed coefficients yet (OQ-CE-03)."
    assert fakes.results.runs == {}, "a refused run must store nothing"


def test_the_exercise_still_ships_no_coefficients() -> None:
    """A placeholder nobody can grep for is a decision that has quietly closed."""
    from smartmatch_domain.exercise import simulation

    assert simulation.EXERCISE_SIMULATION_COEFFICIENTS is None
    source = Path(simulation.__file__).read_text(encoding="utf-8")
    assert "PLACEHOLDER (OQ-CE-03)" in source


def test_no_module_in_this_track_writes_down_a_coefficient_or_a_share() -> None:
    """The eight coefficients and the three shares are Ann's, not this track's."""
    for source_file in _TRACK_SOURCES:
        source = source_file.read_text(encoding="utf-8")
        for guess in ("0.30", "0.55", "0.80", "0.15", "= 0.5", "base_signup_rate ="):
            assert guess not in source, f"{source_file.name} writes down {guess!r}"


def test_no_module_in_this_track_writes_down_a_class_year_or_a_major() -> None:
    """The vocabularies are Ann's; this track names none of them (OQ-CE-01)."""
    for source_file in _TRACK_SOURCES:
        source = source_file.read_text(encoding="utf-8")
        for guess in ("Senior", "Junior", "Sophomore", "Freshman", "Finance", "Marketing"):
            assert guess not in source, f"{source_file.name} writes down {guess!r}"


def test_the_placeholder_markers_are_literally_present_in_the_source() -> None:
    assert "PLACEHOLDER (OQ-CE-03)" in _MODELS_SOURCE.read_text(encoding="utf-8")
    assert "PLACEHOLDER (OQ-CE-04)" in _REFRESH_SOURCE.read_text(encoding="utf-8")
    assert "OQ-CE-03" in _ROUTER_SOURCE.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# The lock and the one-run rule (design spec §9)
# ---------------------------------------------------------------------------


def test_a_locked_event_is_refused_with_a_sentence(
    fakes: _Fakes, client: TestClient, confirmed: SimulationCoefficients
) -> None:
    response = client.post(_RESULTS, json={}, headers=_HEADER)

    assert response.status_code == 409
    body = response.json()["error"]
    assert body["code"] == "exercise_results_locked"
    assert body["message"] == "The instructor has not opened results for this event yet."
    assert fakes.results.runs == {}


def test_an_unlocked_event_runs_and_stores_the_three_panels(
    fakes: _Fakes, client: TestClient, confirmed: SimulationCoefficients
) -> None:
    fakes.unlock("round-one")

    response = client.post(_RESULTS, json=_FINAL_BODY, headers=_HEADER)

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["event_key"] == "round-one"
    assert body["round"] == FIRST_ROUND
    assert body["setting_name"] == _FINAL
    assert body["team"]["invited_count"] == _INVITE_LIMIT
    assert body["email_everyone"]["invited_count"] == len(_ROWS)
    assert body["round_one"] is None, "round one has no earlier round to compare with"
    assert len(fakes.results.runs) == 1


def test_a_second_run_is_refused_with_the_specs_own_sentence(
    fakes: _Fakes, client: TestClient, confirmed: SimulationCoefficients
) -> None:
    """Design spec §9 writes this sentence out; it is compared byte for byte."""
    fakes.unlock("round-one")
    assert client.post(_RESULTS, json=_FINAL_BODY, headers=_HEADER).status_code == 201

    response = client.post(_RESULTS, json={}, headers=_HEADER)

    assert response.status_code == 409
    body = response.json()["error"]
    assert body["code"] == "exercise_results_already_run"
    assert body["message"] == "This team has already run results for this event."
    assert body["message"] == ALREADY_RUN_SENTENCE


def test_the_sentence_is_the_repositorys_and_is_not_restated_in_the_router() -> None:
    """One copy of the words, so a reword cannot change the spec in one place."""
    assert "already run results" not in _ROUTER_SOURCE.read_text(encoding="utf-8")


def test_a_past_event_is_not_one_of_the_rounds(
    fakes: _Fakes, client: TestClient, confirmed: SimulationCoefficients
) -> None:
    """``exercise_result_run.round`` admits 1 and 2, so a past event has nothing
    to store — and that is a sentence rather than a constraint violation."""
    fakes.unlock("past-analytics")

    response = client.post(f"{_BASE}/events/past-analytics/results", json={}, headers=_HEADER)

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "exercise_event_is_not_a_round"


def test_an_event_from_another_data_file_is_not_found(
    client: TestClient, confirmed: SimulationCoefficients
) -> None:
    response = client.post(f"{_BASE}/events/not-in-this-file/results", json={}, headers=_HEADER)

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "exercise_event_unknown"


def test_the_round_is_read_off_the_data_file_rather_than_from_a_name() -> None:
    """Round one is the first exercise event by sequence; no name is written down."""
    assert round_of(_EVENTS, "round-one") == 1
    assert round_of(_EVENTS, "round-two") == EXERCISE_ROUNDS
    assert round_of(_EVENTS, "past-analytics") is None
    # Shuffled input, same answer: the order comes from `sequence`, not from the
    # order the repository happened to return.
    assert round_of(tuple(reversed(_EVENTS)), "round-one") == 1


# ---------------------------------------------------------------------------
# The final setting (Ann to Chau, Discord, 2026-09-24)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "body",
    [{}, {"setting_name": None}, {"setting_name": ""}, {"setting_name": "   "}],
    ids=["left-out", "null", "empty", "blank"],
)
def test_a_run_without_a_final_setting_is_refused_with_a_sentence(
    fakes: _Fakes,
    client: TestClient,
    confirmed: SimulationCoefficients,
    body: Mapping[str, object],
) -> None:
    """Step three of the owner's flow: the team chooses one final setting.

    There is no longer a run on the course's starting values. A team that wants
    them saves them under a name, which is the same act as choosing any other
    final setting.
    """
    fakes.unlock("round-one")

    response = client.post(_RESULTS, json=body, headers=_HEADER)

    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "exercise_final_setting_required"
    assert error["message"] == _FINAL_SETTING_SENTENCE
    assert fakes.results.runs == {}, "a refused run must store nothing"


def test_a_run_with_no_body_at_all_is_refused_with_the_same_sentence(
    fakes: _Fakes, client: TestClient, confirmed: SimulationCoefficients
) -> None:
    fakes.unlock("round-one")

    response = client.post(_RESULTS, headers=_HEADER)

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "exercise_final_setting_required"
    assert fakes.results.runs == {}


def test_the_final_setting_is_trimmed_before_it_is_looked_up_and_stored(
    fakes: _Fakes, client: TestClient, confirmed: SimulationCoefficients
) -> None:
    fakes.unlock("round-one")

    response = client.post(_RESULTS, json={"setting_name": f"  {_FINAL} "}, headers=_HEADER)

    assert response.status_code == 201, response.text
    assert response.json()["setting_name"] == _FINAL


# -- the order of the refusals ------------------------------------------------
#
# The event's own state is answered first, whatever the body says: a sentence
# about the body is only useful once the event can actually be run. The body is
# answered before OQ-CE-03, which is the owner's to close and refuses every run
# on this deployment today — after it, the team's own step would be unreachable.


def test_an_unknown_event_is_answered_before_a_missing_final_setting(
    client: TestClient, confirmed: SimulationCoefficients
) -> None:
    response = client.post(f"{_BASE}/events/not-in-this-file/results", json={}, headers=_HEADER)

    assert response.json()["error"]["code"] == "exercise_event_unknown"


def test_a_past_event_is_answered_before_a_missing_final_setting(
    fakes: _Fakes, client: TestClient, confirmed: SimulationCoefficients
) -> None:
    fakes.unlock("past-analytics")

    response = client.post(f"{_BASE}/events/past-analytics/results", json={}, headers=_HEADER)

    assert response.json()["error"]["code"] == "exercise_event_is_not_a_round"


def test_a_locked_event_is_answered_before_a_missing_final_setting(
    fakes: _Fakes, client: TestClient, confirmed: SimulationCoefficients
) -> None:
    """Choosing a setting would not open the event; the lock is the true answer."""
    response = client.post(_RESULTS, json={}, headers=_HEADER)

    assert response.json()["error"]["code"] == "exercise_results_locked"


def test_an_event_already_run_is_answered_before_a_missing_final_setting(
    fakes: _Fakes, client: TestClient, confirmed: SimulationCoefficients
) -> None:
    """Asking a team that has run to choose a setting would invite a second try."""
    fakes.unlock("round-one")
    assert client.post(_RESULTS, json=_FINAL_BODY, headers=_HEADER).status_code == 201

    response = client.post(_RESULTS, json={}, headers=_HEADER)

    assert response.json()["error"]["code"] == "exercise_results_already_run"


def test_a_missing_final_setting_is_answered_before_the_unconfirmed_rule(
    fakes: _Fakes, client: TestClient
) -> None:
    """No ``confirmed`` fixture: this is the order a team meets on this deployment."""
    fakes.unlock("round-one")

    response = client.post(_RESULTS, json={}, headers=_HEADER)

    assert response.json()["error"]["code"] == "exercise_final_setting_required"


def test_the_published_request_names_the_final_setting_as_required() -> None:
    """The contract a client is generated from says what the route enforces."""
    app = FastAPI()
    for router in routers_for(_settings()):
        app.include_router(router)
    document = app.openapi()
    schema = document["components"]["schemas"]["RunResultsRequest"]
    operation = document["paths"]["/v1/exercise/workspaces/current/events/{event_key}/results"][
        "post"
    ]

    assert operation["requestBody"]["required"] is True
    assert operation["requestBody"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/RunResultsRequest"
    }
    assert schema["required"] == ["setting_name"]
    assert schema["properties"]["setting_name"]["type"] == "string"
    assert schema["properties"]["setting_name"]["minLength"] == 1
    assert "starting values" not in schema["properties"]["setting_name"]["description"]


# ---------------------------------------------------------------------------
# The panels (design spec §10, §11)
# ---------------------------------------------------------------------------


def test_the_same_request_twice_gives_the_same_panels(
    fakes: _Fakes, confirmed: SimulationCoefficients
) -> None:
    """Two teams on one seed, because one team may only run once.

    The rule reads exactly one per-team value — the seed — so two teams holding
    the same seed must produce the same answer for the same list. That is
    design spec §11's behaviour (4) expressed through the route rather than
    through the domain's own unit test.
    """
    fakes.unlock("round-one")
    with _entered(fakes, 1) as first, _entered(fakes, 2) as second:
        one = first.post(_RESULTS, json=_FINAL_BODY, headers=_HEADER).json()
        two = second.post(_RESULTS, json=_FINAL_BODY, headers=_HEADER).json()

    assert one["team"] == two["team"]
    assert one["email_everyone"] == two["email_everyone"]
    assert one["seats_empty"] == two["seats_empty"]


def test_two_teams_with_different_seeds_are_free_to_differ(
    fakes: _Fakes, confirmed: SimulationCoefficients
) -> None:
    """The seed is per team, so a shared answer must not be shared *state*."""
    fakes.unlock("round-one")
    with _entered(fakes, 1) as first:
        one = first.post(_RESULTS, json=_FINAL_BODY, headers=_HEADER).json()
    fakes.workspaces.seed_for_every_team = 13
    with _entered(fakes, 2) as second:
        two = second.post(_RESULTS, json=_FINAL_BODY, headers=_HEADER).json()

    assert one["team"]["invited_profile_nos"] == two["team"]["invited_profile_nos"], (
        "the invited list is the ranked list and does not read the seed"
    )
    assert one["team"] != two["team"], "a different seed must be able to change the outcome"


def test_email_everyone_uses_the_same_seed_as_the_teams_own_list(
    fakes: _Fakes, client: TestClient, confirmed: SimulationCoefficients
) -> None:
    """The whole point of the comparison: a shared profile has one outcome.

    If the two panels were run on different seeds a team would read the
    difference between *two simulations* rather than the difference between
    *who was asked*, which is the lesson design spec §10 is built to teach.
    """
    fakes.unlock("round-one")

    body = client.post(_RESULTS, json=_FINAL_BODY, headers=_HEADER).json()

    invited = set(body["team"]["invited_profile_nos"])
    for panel in ("signed_up_profile_nos", "attended_profile_nos"):
        team = set(body["team"][panel])
        everyone = set(body["email_everyone"][panel])
        assert team == everyone & invited, f"{panel} disagrees between the panels"


def test_seats_empty_is_the_cases_own_arithmetic(
    fakes: _Fakes, client: TestClient, confirmed: SimulationCoefficients
) -> None:
    """``60 - 8 - attended``, from the two named constants and not from a literal."""
    fakes.unlock("round-one")

    body = client.post(_RESULTS, json=_FINAL_BODY, headers=_HEADER).json()

    assert body["event_seats"] == EVENT_SEATS
    assert body["existing_signups"] == EXISTING_SIGNUPS
    assert body["seats_empty"] == max(
        0, EVENT_SEATS - EXISTING_SIGNUPS - body["team"]["attended_count"]
    )


def test_the_panels_nest_the_way_the_rule_promises(
    fakes: _Fakes, client: TestClient, confirmed: SimulationCoefficients
) -> None:
    fakes.unlock("round-one")

    body = client.post(_RESULTS, json=_FINAL_BODY, headers=_HEADER).json()

    for panel in (body["team"], body["email_everyone"]):
        invited = set(panel["invited_profile_nos"])
        signed_up = set(panel["signed_up_profile_nos"])
        attended = set(panel["attended_profile_nos"])
        assert attended <= signed_up <= invited
        assert panel["invited_count"] == len(invited)
        assert panel["signed_up_count"] == len(signed_up)
        assert panel["attended_count"] == len(attended)


def test_the_invited_set_is_the_ranked_list_cut_at_the_invite_limit(
    fakes: _Fakes, client: TestClient, confirmed: SimulationCoefficients
) -> None:
    """Composed from the matching track's ranker, never re-derived here."""
    fakes.unlock("round-one")

    body = client.post(_RESULTS, json=_FINAL_BODY, headers=_HEADER).json()
    listed = client.get(f"{_BASE}/events/round-one/list").json()

    assert body["team"]["invited_profile_nos"] == sorted(
        entry["profile_no"] for entry in listed["entries"]
    )
    assert len(listed["entries"]) == _INVITE_LIMIT


def test_a_saved_setting_moves_the_invited_list_and_is_stored_on_the_run(
    fakes: _Fakes, client: TestClient, confirmed: SimulationCoefficients
) -> None:
    fakes.unlock("round-one")
    workspace = next(iter(fakes.workspaces.rows.values()))
    fakes.settings.rows[(workspace.id, "round-one", "broad")] = SavedSetting(
        event_key="round-one",
        name="broad",
        weights={"past_event_topic_overlap": 1.0},
        created_at=_WHEN,
    )

    body = client.post(_RESULTS, json={"setting_name": "broad"}, headers=_HEADER).json()

    assert body["setting_name"] == "broad"
    # The invited set is the list *that weighting* produces, not the default
    # one: compared against the matching route asked for the same setting, so
    # the two screens a team sees cannot disagree about who was invited.
    with_setting = client.get(f"{_BASE}/events/round-one/list?setting=broad").json()
    assert body["team"]["invited_profile_nos"] == sorted(
        entry["profile_no"] for entry in with_setting["entries"]
    )


def test_a_setting_this_team_has_not_saved_is_not_found(
    fakes: _Fakes, client: TestClient, confirmed: SimulationCoefficients
) -> None:
    fakes.unlock("round-one")

    response = client.post(_RESULTS, json={"setting_name": "nope"}, headers=_HEADER)

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "exercise_setting_unknown"


def test_reading_the_run_back_gives_the_stored_panels(
    fakes: _Fakes, client: TestClient, confirmed: SimulationCoefficients
) -> None:
    fakes.unlock("round-one")
    written = client.post(_RESULTS, json=_FINAL_BODY, headers=_HEADER).json()

    read_back = client.get(f"{_BASE}/events/round-one/results").json()

    assert read_back == written


def test_reading_a_run_this_team_has_not_made_is_not_found(client: TestClient) -> None:
    response = client.get(f"{_BASE}/events/round-one/results")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "exercise_results_not_run"


def test_round_two_carries_the_stored_round_one_panel(
    fakes: _Fakes, client: TestClient, confirmed: SimulationCoefficients
) -> None:
    fakes.unlock("round-one", "round-two")
    first = client.post(_RESULTS, json=_FINAL_BODY, headers=_HEADER).json()

    second = client.post(_RESULTS_TWO, json=_FINAL_BODY, headers=_HEADER).json()

    assert second["round"] == EXERCISE_ROUNDS
    assert second["round_one"] is not None
    assert second["round_one"]["event_key"] == "round-one"
    assert second["round_one"]["round"] == FIRST_ROUND
    assert second["round_one"]["team"] == first["team"]
    assert second["round_one"]["seats_empty"] == first["seats_empty"]


# ---------------------------------------------------------------------------
# The asking choice (design spec §12)
# ---------------------------------------------------------------------------


def test_the_three_choices_come_from_the_domain(client: TestClient) -> None:
    body = client.get(_ASKING).json()

    assert body["choice"] is None
    assert body["refreshed"] is False
    assert body["choices"] == [member.value for member in AskingChoice]


@pytest.mark.parametrize("choice", [member.value for member in AskingChoice])
def test_each_of_the_three_choices_is_accepted_and_stored(
    fakes: _Fakes, client: TestClient, choice: str
) -> None:
    response = client.post(_ASKING, json={"choice": choice}, headers=_HEADER)

    assert response.status_code == 200, response.text
    assert response.json()["choice"] == choice
    assert list(fakes.results.choices.values()) == [choice]


def test_a_second_choice_is_refused_rather_than_replacing_the_first(
    fakes: _Fakes, client: TestClient
) -> None:
    assert client.post(_ASKING, json={"choice": "small_reward"}, headers=_HEADER).status_code == 200

    response = client.post(_ASKING, json={"choice": "required"}, headers=_HEADER)

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "exercise_asking_already_chosen"
    assert list(fakes.results.choices.values()) == ["small_reward"]


def test_a_choice_that_is_not_one_of_the_three_is_refused(client: TestClient) -> None:
    response = client.post(_ASKING, json={"choice": "bribery"}, headers=_HEADER)

    assert response.status_code == 422
    body = response.json()["error"]
    assert body["code"] == "exercise_asking_choice_unknown"
    assert "bribery" not in response.text, "a refusal must not echo what the caller sent"


def test_an_oversized_choice_never_reaches_the_response(client: TestClient) -> None:
    """Review round 2's F2 on PR #188, applied to the one string this track takes."""
    payload = "z" * (MAX_ASKING_CHOICE_CHARACTERS + 1)

    response = client.post(_ASKING, json={"choice": payload}, headers=_HEADER)

    assert response.status_code == 422
    assert payload not in response.text
    assert len(response.text) < 1_000


def test_a_body_naming_anything_else_is_refused(client: TestClient) -> None:
    response = client.post(_ASKING, json={"choice": "required", "team_number": 4}, headers=_HEADER)

    assert response.status_code == 422


# ---------------------------------------------------------------------------
# The refresh (design spec §13)
# ---------------------------------------------------------------------------


def _prepare_refresh(
    fakes: _Fakes, client: TestClient, choice: str = "required"
) -> Mapping[str, object]:
    """Run round one and choose, which is what a refresh needs behind it."""
    fakes.unlock("round-one", "round-two")
    first = client.post(_RESULTS, json=_FINAL_BODY, headers=_HEADER).json()
    assert client.post(_ASKING, json={"choice": choice}, headers=_HEADER).status_code == 200
    return first


def test_a_refresh_before_the_choice_is_refused(
    fakes: _Fakes, client: TestClient, confirmed: SimulationCoefficients
) -> None:
    fakes.unlock("round-one")
    client.post(_RESULTS, json=_FINAL_BODY, headers=_HEADER)

    response = client.post(_REFRESH, json={}, headers=_HEADER)

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "exercise_asking_not_chosen"
    assert fakes.team_view.overlays == {}, "a refused refresh must write no overlay"


def test_a_refresh_before_the_first_round_is_refused(fakes: _Fakes, client: TestClient) -> None:
    assert client.post(_ASKING, json={"choice": "required"}, headers=_HEADER).status_code == 200

    response = client.post(_REFRESH, json={}, headers=_HEADER)

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "exercise_no_first_round_results"
    assert fakes.team_view.overlays == {}


def test_a_refresh_applies_the_three_effects_and_reports_them_as_counts(
    fakes: _Fakes, client: TestClient, confirmed: SimulationCoefficients
) -> None:
    first = _prepare_refresh(fakes, client)

    response = client.post(_REFRESH, json={}, headers=_HEADER)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["choice"] == "required"
    assert body["topics_added"] == first["team"]["attended_count"]
    assert body["cards_completed"] >= 1
    assert body["non_responding"] >= 1, (
        "the fixture must put at least four card-less profiles on the list "
        "for the required share to land on anybody"
    )


def test_a_second_refresh_is_refused(
    fakes: _Fakes, client: TestClient, confirmed: SimulationCoefficients
) -> None:
    _prepare_refresh(fakes, client)
    assert client.post(_REFRESH, json={}, headers=_HEADER).status_code == 200

    response = client.post(_REFRESH, json={}, headers=_HEADER)

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "exercise_already_refreshed"


def test_a_refresh_touches_only_this_teams_overlay(
    fakes: _Fakes, confirmed: SimulationCoefficients
) -> None:
    """Design spec §2's isolation claim, through the route that writes overlays."""
    fakes.unlock("round-one")
    with _entered(fakes, 1) as first, _entered(fakes, 2) as second:
        second_before = second.get(f"{_BASE}/events/round-one/list").json()
        first.post(_RESULTS, json=_FINAL_BODY, headers=_HEADER)
        first.post(_ASKING, json={"choice": "required"}, headers=_HEADER)
        assert first.post(_REFRESH, json={}, headers=_HEADER).status_code == 200

        first_after = first.get(f"{_BASE}/events/round-one/list").json()
        second_after = second.get(f"{_BASE}/events/round-one/list").json()

    workspaces = {workspace.id for workspace in fakes.workspaces.rows.values()}
    touched = {workspace_id for workspace_id, _ in fakes.team_view.overlays}
    assert len(touched) == 1, "a refresh reached more than one team's overlay"
    assert touched < workspaces
    assert second_after == second_before, "the other team's view changed"
    assert first_after != second_after, "this team's view did not change"


def test_the_refreshed_state_is_visible_on_the_asking_route(
    fakes: _Fakes, client: TestClient, confirmed: SimulationCoefficients
) -> None:
    _prepare_refresh(fakes, client)
    assert client.get(_ASKING).json()["refreshed"] is False

    client.post(_REFRESH, json={}, headers=_HEADER)

    assert client.get(_ASKING).json()["refreshed"] is True


def test_the_non_responding_never_sign_up_in_round_two(
    fakes: _Fakes, client: TestClient, confirmed: SimulationCoefficients
) -> None:
    """Design spec §13's cost under ``required``, at the end of the path."""
    _prepare_refresh(fakes, client)
    refreshed = client.post(_REFRESH, json={}, headers=_HEADER).json()
    assert refreshed["non_responding"] >= 1

    silent = {
        profile_no
        for (_, profile_no), row in fakes.team_view.overlays.items()
        if row.non_responding
    }
    body = client.post(_RESULTS_TWO, json=_FINAL_BODY, headers=_HEADER).json()

    assert silent
    assert silent.isdisjoint(body["team"]["signed_up_profile_nos"])
    assert silent.isdisjoint(body["email_everyone"]["signed_up_profile_nos"])


def test_the_other_two_ways_of_asking_cost_nobody(
    fakes: _Fakes, client: TestClient, confirmed: SimulationCoefficients
) -> None:
    _prepare_refresh(fakes, client, choice="better_recommendations")

    body = client.post(_REFRESH, json={}, headers=_HEADER).json()

    assert body["non_responding"] == 0
    assert body["cards_completed"] >= 1


def test_a_refresh_copies_a_card_that_then_reads_as_an_ordinary_card(
    fakes: _Fakes, client: TestClient, confirmed: SimulationCoefficients
) -> None:
    """Design spec §13: the copied card lives in the overlay as ``card_interests``.

    Asserted as a *marker* moving on the team's own list rather than by reading
    the overlay's values, because the value is what D6 keeps off a response: a
    class participant learns that somebody now has a card, never what was on it
    before they filled one in.
    """
    before = {
        entry["profile_no"]: entry["marker"]
        for entry in client.get(f"{_BASE}/events/round-one/list").json()["entries"]
    }
    _prepare_refresh(fakes, client)
    client.post(_REFRESH, json={}, headers=_HEADER)

    after = {
        entry["profile_no"]: entry["marker"]
        for entry in client.get(f"{_BASE}/events/round-one/list").json()["entries"]
    }

    moved = [key for key, marker in after.items() if before.get(key) != marker]
    assert moved, "no marker moved, so the refresh changed nothing this team can see"
    # Some markers move because of the added topics (`major_only` becomes
    # `major_plus_events`), which is the refresh's other effect. What this test
    # is for is the card: at least one profile must have reached the third state.
    completed = [key for key in moved if after[key] == "completed_card"]
    assert completed, "no profile reached `completed_card`, so no card was copied"


# ---------------------------------------------------------------------------
# The refresh policy, on its own (design spec §12, §13)
# ---------------------------------------------------------------------------


def test_a_card_exists_when_either_side_recorded_interests() -> None:
    """Read exactly as ``exercise_matching_models._profile_evidence`` reads it."""
    invited = [row.profile_no for row in _ROWS]

    without = invited_without_a_card(_PROFILES, invited)

    assert 1 not in without, "a base-row card is a card"
    assert 3 in without
    given = replace(_PROFILES[2], overlay_card_interests=())
    assert 3 not in invited_without_a_card((given,), invited)


def test_a_refresh_writes_the_base_goal_onto_every_copied_card(
    fakes: _Fakes, client: TestClient, confirmed: SimulationCoefficients
) -> None:
    """The ruling of 2026-09-21, through the route (OQ-CE-13).

    Every overlay row this refresh gave a card to carries its **base row's**
    ``career_goal``, and carries ``None`` exactly where the base row has none.
    Asserted against ``_ROWS`` rather than against a written-out list, so a
    fixture row that gains a goal cannot quietly stop being checked.
    """
    _prepare_refresh(fakes, client)
    client.post(_REFRESH, json={}, headers=_HEADER)

    given_a_card = {
        profile_no: row
        for (_, profile_no), row in fakes.team_view.overlays.items()
        if row.overlay_card_interests is not None
    }
    assert given_a_card, "no card was copied, so the policy was never exercised"
    for profile_no, row in given_a_card.items():
        assert row.overlay_card_career_goal == _ROWS[profile_no - 1].career_goal


def test_a_copied_card_already_reads_the_base_rows_career_goal() -> None:
    """**The step-1 characterisation.** What a team sees *today*, before OQ-CE-13.

    A profile whose base row carries a career goal and whose overlay now carries
    a copied card, with ``card_career_goal`` left ``NULL`` as PR #190 shipped it:
    ``_profile_evidence`` resolves the overlay **over** the base, so the goal it
    finds is the base row's. The card exists — the overlay recorded interests —
    so a :class:`ProfileCard` is built, and ``career_goal_fit`` can already earn
    on it.

    So writing the goal onto the copied row **changes no ranking**: it makes an
    implicit resolution explicit at the row. If this test ever goes red, the two
    readings have stopped agreeing and OQ-CE-13 has become a behaviour change.
    """
    base = _Row(4, "Devi Rao", career_goal="analytics").team_row()
    copied = replace(base, overlay_card_interests=("brand",), overlay_card_career_goal=None)

    rankable = rankable_set((copied,), _EVENTS)

    assert len(rankable.profiles) == 1
    card = rankable.profiles[0].evidence.card
    assert card is not None, "the copied interests are a card"
    assert card.career_goal == "analytics", "the base row's goal is read through the overlay"
    fit = career_goal_fit(rankable.profiles[0].evidence, event_evidence(_ROUND_ONE))
    assert fit.value == 1.0, "the factor already earns on a goal the copied row does not carry"


def test_writing_the_base_goal_onto_the_copied_card_reads_the_same() -> None:
    """The ruling's row and today's row resolve identically (OQ-CE-13)."""
    base = _Row(4, "Devi Rao", career_goal="analytics").team_row()
    today = replace(base, overlay_card_interests=("brand",), overlay_card_career_goal=None)
    ruled = replace(today, overlay_card_career_goal="analytics")

    assert rankable_set((today,), _EVENTS).profiles == rankable_set((ruled,), _EVENTS).profiles


def test_the_two_draws_are_independent() -> None:
    """One salt for both would make ``required``'s cost fall on the people it helped."""
    no_card = tuple(range(1, 21))

    plan = refresh_plan(
        choice=AskingChoice.REQUIRED,
        seed=42,
        attended_profile_nos=(1, 2),
        no_card_profile_nos=no_card,
    )

    assert set(plan.card_completers) != set(plan.non_responding)
    assert len(plan.card_completers) == round(
        CARD_COMPLETION_SHARE[AskingChoice.REQUIRED] * len(no_card)
    )
    assert len(plan.non_responding) == round(REQUIRED_NON_RESPONDING_SHARE * len(no_card))


def test_the_plan_does_not_depend_on_the_order_it_was_given() -> None:
    forwards = refresh_plan(
        choice=AskingChoice.SMALL_REWARD,
        seed=7,
        attended_profile_nos=(3, 1, 2),
        no_card_profile_nos=(5, 4, 6, 7),
    )
    backwards = refresh_plan(
        choice=AskingChoice.SMALL_REWARD,
        seed=7,
        attended_profile_nos=(2, 3, 1),
        no_card_profile_nos=(7, 6, 4, 5),
    )

    assert forwards == backwards


def test_the_shares_are_the_domains_and_are_not_restated() -> None:
    """The refresh reads Ann's numbers; it does not carry a copy of them."""
    source = _REFRESH_SOURCE.read_text(encoding="utf-8")
    assert "CARD_COMPLETION_SHARE" in source
    assert "REQUIRED_NON_RESPONDING_SHARE" in source
    assert "OQ-CE-04" in source


# ---------------------------------------------------------------------------
# Refresh all (design spec §14)
# ---------------------------------------------------------------------------


def _instructor(fakes: _Fakes) -> TestClient:
    """A client holding a live instructor session cookie."""
    client = TestClient(_exercise_app(fakes))
    client.cookies.set(
        INSTRUCTOR_COOKIE_NAME,
        mint_instructor_session(secret=_TEST_SECRET, now=datetime.now(tz=UTC)),
        path="/v1/exercise/instructor",
    )
    return client


def test_refresh_all_needs_the_instructor_session(fakes: _Fakes) -> None:
    with TestClient(_exercise_app(fakes)) as anonymous:
        response = anonymous.post(_REFRESH_ALL, headers=_HEADER)

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "exercise_instructor_session_required"


def test_refresh_all_needs_the_exercise_header(fakes: _Fakes) -> None:
    with _instructor(fakes) as instructor:
        response = instructor.post(_REFRESH_ALL)

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "exercise_request_header_required"


def test_refresh_all_covers_exactly_the_teams_that_have_chosen(
    fakes: _Fakes, confirmed: SimulationCoefficients
) -> None:
    """Chosen and not yet refreshed — three teams in three different states."""
    fakes.unlock("round-one")
    with _entered(fakes, 1) as one, _entered(fakes, 2) as two, _entered(fakes, 3) as three:
        for client in (one, two, three):
            client.post(_RESULTS, json=_FINAL_BODY, headers=_HEADER)
        one.post(_ASKING, json={"choice": "required"}, headers=_HEADER)
        two.post(_ASKING, json={"choice": "small_reward"}, headers=_HEADER)
        two.post(_REFRESH, json={}, headers=_HEADER)
        # team three never chooses

        with _instructor(fakes) as instructor:
            body = instructor.post(_REFRESH_ALL, headers=_HEADER).json()

    assert body["refreshed_team_numbers"] == [1]
    assert body["refreshed"] == 1
    assert body["skipped"] == 0
    assert set(fakes.results.refreshed) == {
        fakes.workspaces.rows[(_DATASET_ID, 1)].id,
        fakes.workspaces.rows[(_DATASET_ID, 2)].id,
    }


def test_refresh_all_skips_and_counts_a_team_with_no_first_round(
    fakes: _Fakes, confirmed: SimulationCoefficients
) -> None:
    fakes.unlock("round-one")
    with _entered(fakes, 1) as one, _entered(fakes, 2) as two:
        one.post(_RESULTS, json=_FINAL_BODY, headers=_HEADER)
        one.post(_ASKING, json={"choice": "required"}, headers=_HEADER)
        two.post(_ASKING, json={"choice": "required"}, headers=_HEADER)

        with _instructor(fakes) as instructor:
            body = instructor.post(_REFRESH_ALL, headers=_HEADER).json()

    assert body["refreshed_team_numbers"] == [1]
    assert body["skipped"] == 1


def test_refresh_all_produces_what_the_teams_own_buttons_would_have(
    fakes: _Fakes, confirmed: SimulationCoefficients
) -> None:
    """One policy, two routes: the instructor's button is not a second refresh."""
    fakes.unlock("round-one")
    with _entered(fakes, 1) as one, _entered(fakes, 2) as two:
        for client in (one, two):
            client.post(_RESULTS, json=_FINAL_BODY, headers=_HEADER)
            client.post(_ASKING, json={"choice": "required"}, headers=_HEADER)
        by_hand = one.post(_REFRESH, json={}, headers=_HEADER).json()
        with _instructor(fakes) as instructor:
            instructor.post(_REFRESH_ALL, headers=_HEADER)

        first = one.get(f"{_BASE}/events/round-one/list").json()
        second = two.get(f"{_BASE}/events/round-one/list").json()

    assert by_hand["cards_completed"] >= 1
    assert [entry["marker"] for entry in first["entries"]] == [
        entry["marker"] for entry in second["entries"]
    ]


def test_refresh_all_is_answered_by_the_new_router() -> None:
    declared = {
        (method, route.path)
        for route in exercise_instructor_refresh.router.routes
        for method in getattr(route, "methods", ())
    }

    assert ("POST", _REFRESH_ALL) in declared


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
        client.get(f"{_BASE}/events/round-one/results"),
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
