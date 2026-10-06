"""Shared fakes, rows and helpers for the results-router tests.

Moved out of ``tests/unit/test_exercise_results_router.py`` when that file was
split by topic (it was past the 800-line cap). The fixtures that use these live
in this directory's ``conftest.py``. See ``test_exercise_results_rules.py`` for
what the split files pin, in order.
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient
from smartmatch_api.config import Settings
from smartmatch_api.errors import EXCEPTION_HANDLERS
from smartmatch_api.exercise_dependencies import (
    EXERCISE_REQUEST_HEADER,
    INSTRUCTOR_COOKIE_NAME,
    InvitedProfile,
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
from smartmatch_api.main import routers_for
from smartmatch_api.routers import (
    exercise_instructor_refresh,
    exercise_results,
    exercise_results_models,
    exercise_results_refresh,
    exercise_results_run,
)
from smartmatch_domain.exercise.asking import (
    COPIED_CARD_CAREER_GOAL,
    CopiedCardCareerGoal,
    copied_card_career_goal,
)
from smartmatch_domain.exercise.instructor_session import mint_instructor_session
from smartmatch_domain.exercise.registry import EXERCISE_DEFAULT_WEIGHTS
from smartmatch_domain.exercise.simulation import (
    SimulationCoefficients,
)
from smartmatch_domain.exercise.workspace_token import (
    derive_workspace_token,
    hash_workspace_token,
)
from smartmatch_domain.product_scope import ProductScope
from smartmatch_persistence.exercise.dataset_repository import (
    DatasetSummary,
    ExerciseEventRow,
    SimulationProfileRow,
)
from smartmatch_persistence.exercise.results_repository import (
    AlreadyRunError,
    ResultsLockedError,
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

#: **Test-only coefficients.** Not a proposal, not a default, and never read
#: from source. They keep this file's pinned outcomes independent of the
#: shipped set, which Chau approved (D7) and which stays a one-line change if
#: Ann reacts to the sample result. Every test that
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
    than Ann's vocabulary: the route's arithmetic is under test here, not the
    list of majors, and a stored row from before the vocabularies closed is
    still read.
    """

    profile_no: int
    display_name: str
    major: str | None = "Alpha"
    class_year: str | None = "One"
    past_event_keys: tuple[str, ...] = ()
    stated_interests: tuple[str, ...] | None = None
    career_goal: str | None = None
    hidden_true_interests: tuple[str, ...] = ()
    hidden_true_career_goal: str | None = None

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
            hidden_true_career_goal=self.hidden_true_career_goal,
        )


#: Twelve fictional rows: eleven that can take a place on a list and one the data
#: file records no major for. Only two carry a card, so at least four of any six
#: invited have none — which is what makes design spec §13's two shares land on
#: somebody in every run of these tests.
_ROWS: tuple[_Row, ...] = (
    _Row(1, "Avery Brooks", stated_interests=("analytics",), hidden_true_interests=("analytics",)),
    _Row(2, "Bao Nguyen", stated_interests=("brand",), hidden_true_interests=("brand",)),
    _Row(
        3,
        "Cam Ellis",
        past_event_keys=("past-analytics",),
        hidden_true_interests=("analytics",),
        hidden_true_career_goal="analytics",
    ),
    _Row(4, "Devi Rao", hidden_true_interests=("brand",), career_goal="analytics"),
    _Row(5, "Emery Vale", past_event_keys=("past-analytics",), hidden_true_interests=("outreach",)),
    _Row(
        6, "Fen Liu", hidden_true_interests=("analytics", "brand"), hidden_true_career_goal="brand"
    ),
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
        invited: Sequence[InvitedProfile] = (),
        setting_weights: Mapping[str, float] | None = None,
    ) -> StoredResultRun:
        assert dataset_id == _DATASET_ID
        if (workspace_id, event_key) in self.runs:
            raise AlreadyRunError
        # Read again at the write, as the real repository does under its key.
        if (dataset_id, event_key) not in self.unlocked:
            raise ResultsLockedError
        stored = StoredResultRun(
            event_key=event_key,
            round=round_number,
            setting_name=setting_name,
            team=team,
            email_everyone=email_everyone,
            seats_empty=seats_empty,
            created_at=_WHEN,
            # Copied, as the real row is: what the run keeps is its own record
            # and not a reference to anything a later request could change.
            invited=tuple(invited),
            setting_weights=None if setting_weights is None else dict(setting_weights),
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
            if (
                goal := copied_card_career_goal(
                    row.career_goal,
                    career_goal_policy,
                    hidden_true_career_goal=row.hidden_true_career_goal,
                )
            )
            is not None
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

    def lock(self, *event_keys: str) -> None:
        """Close results again, as the instructor's lock route does."""
        for event_key in event_keys:
            self.results.unlocked.discard((_DATASET_ID, event_key))


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


def _prepare_refresh(
    fakes: _Fakes, client: TestClient, choice: str = "required"
) -> Mapping[str, object]:
    """Run round one and choose, which is what a refresh needs behind it."""
    fakes.unlock("round-one", "round-two")
    first = client.post(_RESULTS, json=_FINAL_BODY, headers=_HEADER).json()
    assert client.post(_ASKING, json={"choice": choice}, headers=_HEADER).status_code == 200
    return first


def _instructor(fakes: _Fakes) -> TestClient:
    """A client holding a live instructor session cookie."""
    client = TestClient(_exercise_app(fakes))
    client.cookies.set(
        INSTRUCTOR_COOKIE_NAME,
        mint_instructor_session(secret=_TEST_SECRET, now=datetime.now(tz=UTC)),
        path="/v1/exercise/instructor",
    )
    return client
