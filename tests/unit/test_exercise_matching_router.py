"""The matching screen's routes (CE-MATCHING-API, design spec §4-§8).

What is pinned here, in the order the failures would hurt:

1. **The order is the domain ranker's**, name for name, against
   ``exercise_ranked_list`` called directly on the same inputs. A route that
   re-sorted, re-cut or re-worded would pass every other test in this file.
2. **Nothing a response may never carry**: a schema walk over every model in
   both modules, over the handlers' docstrings — FastAPI publishes those as
   operation descriptions — and over the whole exercise-scope OpenAPI document,
   refusing ``hidden_true_interests`` (ADR-0025 D6) and anything score-shaped
   (D8).
3. **The CSV**: design spec §8's six columns, and a cell that begins with a
   spreadsheet formula introducer neutralised. The names and majors come out of
   an uploaded file and the file is opened in a spreadsheet by definition.
4. **Isolation and durability**: two teams do not see each other's settings, and
   a reload — a new client with the same cookie — still has them.
5. **The refusals**, each with its sentence.

The database half — the at-most-three rule against a concurrent fourth, the
overlay join against real rows, and the two-teams claim as a property of the
statements rather than of a fake — is in
``tests/integration/test_exercise_settings_persistence.py``. A fake repository
cannot prove a lock.
"""

from __future__ import annotations

import ast
import uuid
from collections.abc import Iterator, Mapping
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel
from smartmatch_api.config import Settings
from smartmatch_api.errors import EXCEPTION_HANDLERS
from smartmatch_api.exercise_dependencies import (
    EXERCISE_REQUEST_HEADER,
    WORKSPACE_COOKIE_NAME,
    get_active_dataset,
    get_dataset_repository,
    get_exercise_session,
    get_settings_repository,
    get_team_view_repository,
    get_workspace_repository,
    get_workspace_secret,
)
from smartmatch_api.exercise_errors import ExerciseError
from smartmatch_api.main import CAPABILITY_SCOPED_ROUTERS, routers_for
from smartmatch_api.routers import (
    exercise_matching,
    exercise_matching_csv,
    exercise_matching_models,
    exercise_matching_weights,
)
from smartmatch_api.routers.exercise_matching_csv import (
    CSV_FORMULA_INTRODUCERS,
    CSV_LEADING_WHITESPACE,
    CSV_LIST_COLUMNS,
    csv_download_filename,
    neutralised_cell,
)
from smartmatch_api.routers.exercise_matching_models import (
    MAX_WEIGHT_KEY_CHARACTERS,
    MAX_WEIGHT_KEYS,
    MAX_WEIGHT_REFUSAL_CHARACTERS,
    PLACEHOLDER_CLASS_YEAR_RANK,
    event_evidence,
    rankable_set,
)
from smartmatch_domain.exercise import EXERCISE_WITHHELD_FIELDS
from smartmatch_domain.exercise.matching import exercise_ranked_list
from smartmatch_domain.exercise.reasons import ANN_TIED_ON_YEAR_PHRASE, phrase_as_sentence
from smartmatch_domain.exercise.registry import (
    EXERCISE_APPROVED_SCORING_KEYS,
    EXERCISE_DEFAULT_WEIGHTS,
)
from smartmatch_domain.exercise.workspace_token import (
    derive_workspace_token,
    hash_workspace_token,
)
from smartmatch_domain.product_scope import Capability, ProductScope
from smartmatch_persistence.exercise.dataset_repository import DatasetSummary, ExerciseEventRow
from smartmatch_persistence.exercise.settings_repository import (
    MAX_SAVED_SETTINGS_PER_EVENT,
    SavedSetting,
    TooManySavedSettingsError,
)
from smartmatch_persistence.exercise.team_view_repository import TeamProfileRow
from smartmatch_persistence.exercise.workspace_repository import (
    ExerciseDatasetSummary,
    ExerciseWorkspace,
)

_ROUTER_SOURCE = Path(exercise_matching.__file__)
_MODELS_SOURCE = Path(exercise_matching_models.__file__)
_CSV_SOURCE = Path(exercise_matching_csv.__file__)
_WEIGHTS_SOURCE = Path(exercise_matching_weights.__file__)

#: Every source file this track owns on the router side. The source walks below
#: read all of them, so a module split off in review round 2 is covered the day
#: it lands rather than the day somebody remembers it.
_TRACK_SOURCES = (_ROUTER_SOURCE, _MODELS_SOURCE, _CSV_SOURCE, _WEIGHTS_SOURCE)

#: Assembled from pieces rather than written as one literal, for the reason
#: ``test_exercise_workspace_router.py`` gives: ``tools/scan_forbidden.py``
#: matches the shape of a committed credential, and a gate with an exception for
#: a test file is a gate that has learned to be waved through.
_TEST_SECRET = "-".join(("exercise", "matching", "key", "for", "tests", "only"))

_DATASET_ID = uuid.UUID("33333333-3333-3333-3333-333333333333")
_CHECKSUM = "b" * 64
_INVITE_LIMIT = 4

_DATASET = ExerciseDatasetSummary(
    id=_DATASET_ID, label="Made-up student body (sample)", invite_limit=_INVITE_LIMIT
)

_SUMMARY = DatasetSummary(
    dataset_id=_DATASET_ID,
    label=_DATASET.label,
    source_filename="sample.csv",
    uploaded_at=datetime(2026, 9, 19, 12, 0, tzinfo=UTC),
    row_count=8,
    checksum=_CHECKSUM,
    invite_limit=_INVITE_LIMIT,
    license_line=None,
    event_count=2,
)

_NORTHLINE = ExerciseEventRow(
    event_key="northline",
    name="Northline round",
    topic_tags=("analytics", "brand"),
    target_majors=("Marketing",),
    is_exercise_event=True,
    sequence=11,
)

_PAST = ExerciseEventRow(
    event_key="past-analytics",
    name="An earlier analytics evening",
    topic_tags=("analytics",),
    target_majors=("Marketing",),
    is_exercise_event=False,
    sequence=1,
)

_EVENTS: tuple[ExerciseEventRow, ...] = (_PAST, _NORTHLINE)


def _profile(
    profile_no: int,
    *,
    display_name: str,
    major: str | None = "Marketing",
    class_year: str | None = "Senior",
    past_event_keys: tuple[str, ...] = (),
    stated_interests: tuple[str, ...] | None = None,
    career_goal: str | None = None,
) -> TeamProfileRow:
    """One base row with no overlay. Every value is made up."""
    return TeamProfileRow(
        profile_no=profile_no,
        display_name=display_name,
        major=major,
        class_year=class_year,
        past_event_keys=past_event_keys,
        stated_interests=stated_interests,
        career_goal=career_goal,
        overlay_added_event_topics=(),
        overlay_card_interests=None,
        overlay_card_career_goal=None,
        non_responding=False,
    )


#: Eight fictional profiles spanning every marker and both majors, plus one row
#: the data file records no major for — the case the ranked list cannot seat.
_PROFILES: tuple[TeamProfileRow, ...] = (
    _profile(
        1,
        display_name="Avery Brooks",
        stated_interests=("analytics", "brand"),
        career_goal="analytics",
    ),
    _profile(2, display_name="Bao Nguyen", past_event_keys=("past-analytics",)),
    _profile(3, display_name="Cam Ellis", class_year="Junior"),
    _profile(
        4,
        display_name="Devi Rao",
        major="Finance",
        class_year="Junior",
        stated_interests=("brand",),
    ),
    _profile(5, display_name="Emery Vale", class_year="Junior"),
    _profile(6, display_name="Fen Liu", major="Finance", past_event_keys=("past-analytics",)),
    _profile(7, display_name="Gita Shah", major="Finance", class_year="Sophomore"),
    _profile(8, display_name="Hal Ortiz", major=None, class_year=None),
)


class _FakeWorkspaceRepository:
    """Enough of ``ExerciseWorkspaceRepository`` to run the entry route."""

    def __init__(self) -> None:
        self.rows: dict[tuple[uuid.UUID, int], ExerciseWorkspace] = {}

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
            self.rows[key] = ExerciseWorkspace(
                id=uuid.uuid4(),
                dataset_id=dataset_id,
                team_number=team_number,
                dataset_label=_DATASET.label,
                invite_limit=_DATASET.invite_limit,
            )
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
    """The two reads the matching routes make of a dataset."""

    def list_events(
        self, _session: object, *, dataset_id: uuid.UUID
    ) -> tuple[ExerciseEventRow, ...]:
        return _EVENTS if dataset_id == _DATASET_ID else ()

    def get_dataset_summary(
        self, _session: object, *, dataset_id: uuid.UUID
    ) -> DatasetSummary | None:
        return _SUMMARY if dataset_id == _DATASET_ID else None


class _FakeTeamViewRepository:
    """Design spec §2's ``base row ⟕ overlay``, over a dict of overlays.

    The overlay is keyed on the workspace, like the real statement's join
    condition, so a test can give one team a card and assert the other team's
    view is unchanged.
    """

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
    """The saved-settings rules, minus the lock the database provides.

    The cap is re-implemented rather than stubbed out, because the routes'
    behaviour around it — which status, which sentence, and that an overwrite is
    always allowed — is what this file is for. That two concurrent saves cannot
    both pass the count is the integration file's.
    """

    def __init__(self) -> None:
        self.rows: dict[tuple[uuid.UUID, str, str], SavedSetting] = {}

    def list_settings(
        self, _session: object, *, workspace_id: uuid.UUID, event_key: str
    ) -> tuple[SavedSetting, ...]:
        return tuple(
            setting
            for (held_by, held_for, _), setting in self.rows.items()
            if held_by == workspace_id and held_for == event_key
        )

    def get_setting(
        self, _session: object, *, workspace_id: uuid.UUID, event_key: str, name: str
    ) -> SavedSetting | None:
        return self.rows.get((workspace_id, event_key, name))

    def save_setting(
        self,
        session: object,
        *,
        dataset_id: uuid.UUID,
        workspace_id: uuid.UUID,
        event_key: str,
        name: str,
        weights: Mapping[str, float],
    ) -> SavedSetting:
        assert dataset_id == _DATASET_ID
        existing = self.list_settings(session, workspace_id=workspace_id, event_key=event_key)
        if len(existing) >= MAX_SAVED_SETTINGS_PER_EVENT and not any(
            setting.name == name for setting in existing
        ):
            raise TooManySavedSettingsError(
                f"Your team can keep {MAX_SAVED_SETTINGS_PER_EVENT} saved settings for "
                "this event. Delete one before saving another."
            )
        stored = SavedSetting(
            event_key=event_key,
            name=name,
            weights=dict(weights),
            created_at=datetime(2026, 9, 19, 12, 0, tzinfo=UTC),
        )
        self.rows[(workspace_id, event_key, name)] = stored
        return stored

    def delete_setting(
        self,
        _session: object,
        *,
        dataset_id: uuid.UUID,
        workspace_id: uuid.UUID,
        event_key: str,
        name: str,
    ) -> bool:
        assert dataset_id == _DATASET_ID
        return self.rows.pop((workspace_id, event_key, name), None) is not None


class _FakeSession:
    """A session that can be committed and answers every read with nothing."""

    def __init__(self) -> None:
        self.commits = 0

    def commit(self) -> None:
        self.commits += 1

    def execute(self, _statement: object) -> object:
        raise AssertionError("a matching route issued a query of its own")


def _settings() -> Settings:
    return Settings(
        product_scope=ProductScope.CLASS_EXERCISE,
        exercise_workspace_secret=_TEST_SECRET,
        exercise_cookie_secure=False,
    )


class _Fakes:
    """Every fake one app is wired with, so a test can reach them by name."""

    def __init__(self) -> None:
        self.workspaces = _FakeWorkspaceRepository()
        self.datasets = _FakeDatasetRepository()
        self.team_view = _FakeTeamViewRepository()
        self.settings = _FakeSettingsRepository()


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
    app.dependency_overrides[get_active_dataset] = lambda: _DATASET
    app.dependency_overrides[get_workspace_secret] = lambda: _TEST_SECRET
    return app


@pytest.fixture
def fakes() -> _Fakes:
    return _Fakes()


def _entered(fakes: _Fakes, team_number: int) -> TestClient:
    """A client that has entered a team number and holds its cookie."""
    client = TestClient(_exercise_app(fakes))
    response = client.post(
        "/v1/exercise/workspaces",
        json={"team_number": team_number},
        headers={EXERCISE_REQUEST_HEADER: "1"},
    )
    assert response.status_code == 200, response.text
    return client


@pytest.fixture
def client(fakes: _Fakes) -> Iterator[TestClient]:
    with _entered(fakes, 1) as entered:
        yield entered


_BASE = "/v1/exercise/workspaces/current"
_LIST = f"{_BASE}/events/northline/list"
_SETTINGS = f"{_BASE}/events/northline/settings"
_HEADER = {EXERCISE_REQUEST_HEADER: "1"}
_WEIGHTS = {"same_major": 0.5, "stated_interest_overlap": 0.5}


# ---------------------------------------------------------------------------
# The event picker
# ---------------------------------------------------------------------------


def test_the_events_route_returns_this_teams_data_files_events(client: TestClient) -> None:
    body = client.get(f"{_BASE}/events").json()
    assert [event["event_key"] for event in body["events"]] == ["past-analytics", "northline"]
    northline = body["events"][1]
    assert northline["is_exercise_event"] is True
    assert northline["topic_tags"] == ["analytics", "brand"]
    assert northline["target_majors"] == ["Marketing"]
    assert northline["sequence"] == 11


# ---------------------------------------------------------------------------
# The ranked list is the domain ranker's list
# ---------------------------------------------------------------------------


def _expected_list(weights: Mapping[str, float] | None = None) -> Any:
    """The same call the route makes, made here, from the same inputs."""
    rankable = rankable_set(_PROFILES, _EVENTS)
    return exercise_ranked_list(
        event_evidence(_NORTHLINE),
        rankable.profiles,
        weights=weights,
        invite_limit=_INVITE_LIMIT,
        year_rank=rankable.year_rank,
        dataset_checksum=_CHECKSUM,
    )


def test_the_route_returns_the_domain_rankers_list_name_for_name(client: TestClient) -> None:
    """Golden: the route composes the ranker, it does not re-implement it.

    Compared against ``exercise_ranked_list`` called directly on the same rows,
    so a handler that re-sorted, re-cut or re-worded a reason fails here even
    though every field would still have the right shape.
    """
    body = client.get(_LIST).json()
    expected = _expected_list()
    assert [entry["profile_no"] for entry in body["entries"]] == [
        int(entry.profile_id) for entry in expected.entries
    ]
    assert [entry["rank"] for entry in body["entries"]] == [
        entry.rank for entry in expected.entries
    ]
    assert [entry["reason"] for entry in body["entries"]] == [
        entry.reason for entry in expected.entries
    ]
    assert [entry["marker"] for entry in body["entries"]] == [
        str(entry.marker) for entry in expected.entries
    ]
    assert [entry["contributing_factor_keys"] for entry in body["entries"]] == [
        list(entry.contributing_factor_keys) for entry in expected.entries
    ]


def test_the_list_is_cut_at_the_data_files_invite_limit(client: TestClient) -> None:
    body = client.get(_LIST).json()
    assert body["invite_limit"] == _INVITE_LIMIT
    assert len(body["entries"]) == _INVITE_LIMIT
    assert len(body["entries"]) < len(_PROFILES), "the cut has to bite for this to mean anything"


def test_the_same_request_twice_gives_the_same_order(client: TestClient) -> None:
    """Design spec §4.4: the fixed order never changes between runs."""
    assert client.get(_LIST).json()["entries"] == client.get(_LIST).json()["entries"]


def test_two_teams_are_given_the_same_order(fakes: _Fakes) -> None:
    """…and never between teams: the seed is the data file's checksum alone."""
    with _entered(fakes, 2) as team_two, _entered(fakes, 3) as team_three:
        assert team_two.get(_LIST).json()["entries"] == team_three.get(_LIST).json()["entries"]


def test_moving_a_weight_changes_the_list(client: TestClient) -> None:
    """The four factors are adjustable, which is the requirement being served."""
    default_order = [entry["profile_no"] for entry in client.get(_LIST).json()["entries"]]
    on_the_card = client.get(
        _LIST, params={"same_major": 0.0, "stated_interest_overlap": 1.0}
    ).json()
    assert on_the_card["weights"]["same_major"] == 0.0
    assert on_the_card["weights"]["stated_interest_overlap"] == 1.0
    assert [entry["profile_no"] for entry in on_the_card["entries"]] != default_order


def test_with_no_weights_the_placeholder_defaults_are_used_and_echoed(
    client: TestClient,
) -> None:
    """OQ-CE-02: equal weights, from the rulebook's named constants."""
    body = client.get(_LIST).json()
    assert body["weights"] == dict(EXERCISE_DEFAULT_WEIGHTS)
    assert body["setting_name"] is None


def test_a_profile_with_no_major_on_file_is_counted_and_not_seated(
    client: TestClient,
) -> None:
    body = client.get(_LIST).json()
    assert body["unrankable_profile_count"] == 1
    assert 8 not in [entry["profile_no"] for entry in body["entries"]]


# ---------------------------------------------------------------------------
# Who is on the list (design spec §7)
# ---------------------------------------------------------------------------


def test_the_response_carries_the_counts_beside_the_whole_file(client: TestClient) -> None:
    composition = client.get(_LIST).json()["composition"]
    assert composition["by_major"]["dimension"] == "major"
    assert sum(composition["by_major"]["on_list"].values()) == _INVITE_LIMIT
    # Seven rankable profiles; the eighth has no major on file and is counted
    # by `unrankable_profile_count` instead of being made into a group.
    assert sum(composition["by_major"]["all_profiles"].values()) == 7
    assert sum(composition["by_class_year"]["all_profiles"].values()) == 7
    assert set(composition["by_marker"]["all_profiles"]) == {
        "major_only",
        "major_plus_events",
        "completed_card",
    }


def test_the_table_and_the_unrankable_count_reconcile_to_the_whole_file(
    client: TestClient,
) -> None:
    """Declared deviation: §7's "whole file" side counts the rankable set.

    A profile the data file records no major or no year for can take no place on
    any list, so counting it as a group with nobody on the list would produce a
    notice nothing a team does could ever satisfy. It is reported as a count
    instead — and the count sits on the same response as the table, so a reader
    can add the two and get the file's own row count back. That reconciliation
    is the whole justification for the deviation, so it is asserted rather than
    described.
    """
    body = client.get(_LIST).json()
    composition = body["composition"]
    counted = sum(composition["by_major"]["all_profiles"].values())
    assert counted + body["unrankable_profile_count"] == len(_PROFILES)
    assert sum(composition["by_class_year"]["all_profiles"].values()) == counted
    assert sum(composition["by_marker"]["all_profiles"].values()) == counted
    assert body["unrankable_profile_count"] > 0, "the fixture must exercise the gap"


def test_the_coverage_notice_names_a_group_with_nobody_on_the_list(
    client: TestClient,
) -> None:
    """The #161 notice, composed from ``find_uncovered_groups`` rather than redone."""
    body = client.get(_LIST, params={"same_major": 1.0}).json()
    coverage = body["composition"]["coverage"]
    listed_majors = {entry["major"] for entry in body["entries"]}
    uncovered = {
        major for profile in _PROFILES if profile.major is not None for major in (profile.major,)
    } - listed_majors
    assert set(coverage["missing_majors"]) == uncovered
    assert coverage["has_uncovered_group"] is bool(uncovered)


def test_an_overlay_changes_only_that_teams_view(fakes: _Fakes) -> None:
    """Design spec §2: a team's view is base ⟕ overlay, and the overlay is keyed."""
    with _entered(fakes, 4) as team_four, _entered(fakes, 5) as team_five:
        workspace = fakes.workspaces.rows[(_DATASET_ID, 4)]
        base = _PROFILES[2]
        fakes.team_view.overlays[(workspace.id, base.profile_no)] = replace(
            base,
            overlay_card_interests=("analytics", "brand"),
            overlay_card_career_goal="analytics",
        )
        four = client_marker(team_four, base.profile_no)
        five = client_marker(team_five, base.profile_no)
    assert four == "completed_card"
    assert five == "major_only"


def client_marker(client: TestClient, profile_no: int) -> str | None:
    """The marker this client's list carries for one profile, if it is on it."""
    body = client.get(_LIST, params={"same_major": 1.0, "stated_interest_overlap": 1.0}).json()
    for entry in body["entries"]:
        if entry["profile_no"] == profile_no:
            return str(entry["marker"])
    return None


# ---------------------------------------------------------------------------
# Saved settings (design spec §6)
# ---------------------------------------------------------------------------


def _save(client: TestClient, name: str, weights: Mapping[str, float] | None = None) -> Any:
    return client.put(
        f"{_SETTINGS}/{name}",
        json={"weights": dict(weights if weights is not None else _WEIGHTS)},
        headers=_HEADER,
    )


def test_a_team_may_keep_three_names_and_a_fourth_is_refused(client: TestClient) -> None:
    for name in ("broad", "narrow", "balanced"):
        assert _save(client, name).status_code == 200
    fourth = _save(client, "one-more")
    assert fourth.status_code == 409
    assert fourth.json()["error"]["code"] == "exercise_too_many_settings"
    assert "Delete one before saving another." in fourth.json()["error"]["message"]
    assert len(client.get(_SETTINGS).json()["settings"]) == MAX_SAVED_SETTINGS_PER_EVENT


def test_saving_over_a_name_the_team_already_has_is_allowed(client: TestClient) -> None:
    """Three names is a cap on names, not on saves."""
    for name in ("broad", "narrow", "balanced"):
        _save(client, name)
    again = _save(client, "narrow", {"same_major": 0.9})
    assert again.status_code == 200
    stored = {setting["name"]: setting["weights"] for setting in again.json()["settings"]}
    assert stored["narrow"] == {"same_major": 0.9}
    assert len(stored) == MAX_SAVED_SETTINGS_PER_EVENT


def test_deleting_one_frees_a_slot(client: TestClient) -> None:
    for name in ("broad", "narrow", "balanced"):
        _save(client, name)
    removed = client.delete(f"{_SETTINGS}/narrow", headers=_HEADER)
    assert removed.status_code == 200
    assert [setting["name"] for setting in removed.json()["settings"]] == ["broad", "balanced"]
    assert _save(client, "one-more").status_code == 200


def test_a_reload_keeps_the_saved_settings(fakes: _Fakes) -> None:
    """Justin's second "easy to forget" item: a reload loses no work."""
    with _entered(fakes, 6) as first:
        _save(first, "broad")
        token = first.cookies.get(WORKSPACE_COOKIE_NAME, path="/v1/exercise")
    with TestClient(_exercise_app(fakes)) as reloaded:
        reloaded.cookies.set(WORKSPACE_COOKIE_NAME, str(token), path="/v1/exercise")
        body = reloaded.get(_SETTINGS).json()
    assert [setting["name"] for setting in body["settings"]] == ["broad"]


def test_two_teams_never_see_each_others_settings(fakes: _Fakes) -> None:
    """Justin's first "easy to forget" item, for saved settings."""
    with _entered(fakes, 1) as team_one, _entered(fakes, 2) as team_two:
        _save(team_one, "ours")
        assert [setting["name"] for setting in team_one.get(_SETTINGS).json()["settings"]] == [
            "ours"
        ]
        assert team_two.get(_SETTINGS).json()["settings"] == []
        # And team two cannot build a list from a name only team one saved.
        assert team_two.get(_LIST, params={"setting": "ours"}).status_code == 404


def test_a_list_can_be_built_from_a_saved_setting(client: TestClient) -> None:
    _save(client, "only-major", {"same_major": 1.0, "stated_interest_overlap": 0.0})
    body = client.get(_LIST, params={"setting": "only-major"}).json()
    assert body["setting_name"] == "only-major"
    assert body["weights"]["same_major"] == 1.0


def test_naming_a_setting_and_a_weight_at_once_is_refused(client: TestClient) -> None:
    _save(client, "broad")
    response = client.get(_LIST, params={"setting": "broad", "same_major": 1.0})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "exercise_weights_ambiguous"


# ---------------------------------------------------------------------------
# Compare (design spec §6)
# ---------------------------------------------------------------------------


def test_compare_returns_both_lists_and_the_names_on_both(client: TestClient) -> None:
    _save(client, "only-major", {"same_major": 1.0, "stated_interest_overlap": 0.0})
    _save(client, "only-card", {"same_major": 0.0, "stated_interest_overlap": 1.0})
    body = client.get(f"{_SETTINGS}/compare", params={"a": "only-major", "b": "only-card"}).json()
    assert body["a"]["setting_name"] == "only-major"
    assert body["b"]["setting_name"] == "only-card"
    on_a = [entry["profile_no"] for entry in body["a"]["entries"]]
    on_b = {entry["profile_no"] for entry in body["b"]["entries"]}
    assert body["on_both_profile_nos"] == [number for number in on_a if number in on_b]


def test_compare_refuses_a_name_this_team_has_not_saved(client: TestClient) -> None:
    _save(client, "only-major")
    response = client.get(f"{_SETTINGS}/compare", params={"a": "only-major", "b": "absent"})
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "exercise_setting_unknown"


def test_compare_is_not_readable_as_a_setting_name(client: TestClient) -> None:
    """The route is declared before the named routes; the name is refused too."""
    refused = _save(client, "compare")
    assert refused.status_code == 422
    assert refused.json()["error"]["code"] == "exercise_setting_name_reserved"


# ---------------------------------------------------------------------------
# The download (design spec §8)
# ---------------------------------------------------------------------------


def test_the_csv_carries_the_six_columns_and_the_lists_rows(client: TestClient) -> None:
    response = client.get(f"{_BASE}/events/northline/list.csv")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    assert response.headers["content-disposition"] == 'attachment; filename="northline-list.csv"'
    rows = response.text.strip().split("\r\n")
    assert rows[0] == ",".join(CSV_LIST_COLUMNS)
    assert len(rows) == _INVITE_LIMIT + 1
    listed = client.get(_LIST).json()["entries"]
    assert rows[1].split(",")[0] == str(listed[0]["rank"])
    assert listed[0]["display_name"] in rows[1]


def test_the_csv_matches_the_list_built_from_the_same_setting(client: TestClient) -> None:
    _save(client, "only-major", {"same_major": 1.0, "stated_interest_overlap": 0.0})
    listed = client.get(_LIST, params={"setting": "only-major"}).json()["entries"]
    rows = (
        client.get(f"{_BASE}/events/northline/list.csv", params={"setting": "only-major"})
        .text.strip()
        .split("\r\n")[1:]
    )
    assert len(rows) == len(listed)
    for row, entry in zip(rows, listed, strict=True):
        assert row.startswith(f"{entry['rank']},")


#: Cells that must be neutralised, listed here rather than derived from the
#: constant the guard reads (review round 1). A parametrisation that iterates
#: the implementation's own table is a test that agrees with whatever the table
#: says, including with a table that has lost an entry — which is exactly how
#: the leading space and the leading newline went missing.
_MUST_NEUTRALISE = [
    "=HYPERLINK",
    "+HYPERLINK",
    "-HYPERLINK",
    "@HYPERLINK",
    " =HYPERLINK",
    "   =HYPERLINK",
    "\t=HYPERLINK",
    "\r=HYPERLINK",
    "\n=HYPERLINK",
    " \t \n @HYPERLINK",
    "\t-2+3",
    "\tplain text after a tab",
    "\nplain text after a newline",
    # Review round 2, F3: the characters a value pasted out of a web page or
    # written by a Windows editor actually begins with, each invisible to
    # whoever looks at the file, each of which used to carry an `=` straight
    # through an ASCII-only whitespace set.
    "\xa0=HYPERLINK",  # NO-BREAK SPACE
    "\ufeff=HYPERLINK",  # BYTE ORDER MARK
    "\u200b=HYPERLINK",  # ZERO WIDTH SPACE
    "\u3000=HYPERLINK",  # IDEOGRAPHIC SPACE
    "\u202f+HYPERLINK",  # NARROW NO-BREAK SPACE
    "\xa0\ufeff \t@HYPERLINK",  # and mixed, in any order
]

#: Cells that must be left exactly as they are. A guard that neutralises
#: everything is a guard nobody can read the output of.
_MUST_LEAVE_ALONE = [
    "Avery Brooks",
    "Marketing",
    "one",
    "x=1",
    "3",
    "a - b",
    "Same major; nothing else on file.",
    # A no-break space in the *middle* is ordinary text and stays ordinary: the
    # guard looks at the front of the cell, not for a character anywhere in it.
    "Avery\xa0Brooks",
    "caf\xe9 society",
]


@pytest.mark.parametrize("cell", _MUST_NEUTRALISE)
def test_a_cell_that_would_start_a_formula_is_neutralised(cell: str) -> None:
    """The spreadsheet's rule: strip the leading whitespace, then look."""
    assert neutralised_cell(cell) == f"'{cell}"


@pytest.mark.parametrize("cell", _MUST_LEAVE_ALONE)
def test_an_ordinary_cell_is_left_alone(cell: str) -> None:
    assert neutralised_cell(cell) == cell


def test_an_integer_cell_is_rendered_and_left_alone() -> None:
    assert neutralised_cell(3) == "3"


def test_the_guard_covers_every_introducer_the_module_names() -> None:
    """The cases above are independent; this says they are not *narrower*.

    The list is written out so it cannot shrink with the implementation. This
    assertion is the other direction: an introducer added to the module must
    also appear in the cases, or the list has stopped being complete.
    """
    covered = {cell.lstrip(CSV_LEADING_WHITESPACE)[:1] for cell in _MUST_NEUTRALISE}
    assert set(CSV_FORMULA_INTRODUCERS) <= covered


def test_every_skipped_character_is_covered_by_a_written_out_case() -> None:
    """The other completeness direction, for the whitespace set (review 2, F3).

    The cases above are written out so they cannot shrink with the
    implementation. This says the written list has not fallen *behind* it: every
    character the guard agrees to skip appears in front of an introducer in at
    least one case, or in a case that is deliberately excused below.
    """
    seen = {
        character
        for cell in _MUST_NEUTRALISE
        for character in cell[: len(cell) - len(cell.lstrip(CSV_LEADING_WHITESPACE))]
    }
    # The Unicode spaces in the U+2000..U+200A run and their two neighbours are
    # skipped for completeness rather than because anybody has produced one;
    # writing twelve near-identical cases would be noise. One of the run is in
    # the cases (U+3000) and the three that actually arrive are all covered.
    excused = set("\u2000\u2001\u2002\u2003\u2004\u2005\u2006\u2007\u2008\u2009\u200a")
    excused |= set("\u200c\u200d\u2028\u2029\u205f\u1680\x85\v\f\r")
    assert set(CSV_LEADING_WHITESPACE) - seen <= excused


def test_a_display_name_with_a_no_break_space_cannot_start_a_formula(
    fakes: _Fakes,
) -> None:
    """F3 end to end: the invisible prefix reaches the download as text.

    A name out of an uploaded file, led by a no-break space and an equals sign —
    the shape a value pasted from a web page takes. It must arrive in the CSV
    quoted as text, and the cell must still carry what the file said.
    """
    with _entered(fakes, 1) as client:
        workspace = fakes.workspaces.rows[(_DATASET_ID, 1)]
        base = _PROFILES[0]
        fakes.team_view.overlays[(workspace.id, base.profile_no)] = replace(
            base, display_name='\xa0=HYPERLINK("http://x","click")'
        )
        text = client.get(f"{_BASE}/events/northline/list.csv").text
    assert "'\xa0=HYPERLINK" in text


def test_a_display_name_from_the_data_file_cannot_start_a_formula(fakes: _Fakes) -> None:
    """The case this guard exists for: the names come from an uploaded file."""
    with _entered(fakes, 1) as client:
        workspace = fakes.workspaces.rows[(_DATASET_ID, 1)]
        base = _PROFILES[0]
        fakes.team_view.overlays[(workspace.id, base.profile_no)] = replace(
            base, display_name='=HYPERLINK("http://x","click")'
        )
        text = client.get(f"{_BASE}/events/northline/list.csv").text
    assert "'=HYPERLINK" in text
    assert "\n=HYPERLINK" not in text
    assert ",=HYPERLINK" not in text


@pytest.mark.parametrize(
    ("event_key", "expected"),
    [
        ("northline", "northline-list.csv"),
        ('x" onload="alert(1)', "x--onload--alert-1-list.csv"),
        ("../../etc/passwd", "etc-passwd-list.csv"),
        ("...", "list-list.csv"),
    ],
)
def test_the_download_filename_is_an_allow_list_of_characters(
    event_key: str, expected: str
) -> None:
    """A header value a browser parses, built from an uploaded file's key."""
    built = csv_download_filename(event_key)
    assert built == expected
    assert '"' not in built and "\r" not in built and "\n" not in built and "/" not in built


# ---------------------------------------------------------------------------
# The refusals
# ---------------------------------------------------------------------------


def test_without_a_cookie_every_route_asks_for_a_team_number(fakes: _Fakes) -> None:
    with TestClient(_exercise_app(fakes)) as stranger:
        for response in (
            stranger.get(f"{_BASE}/events"),
            stranger.get(_LIST),
            stranger.get(_SETTINGS),
            stranger.get(f"{_BASE}/events/northline/list.csv"),
        ):
            assert response.status_code == 401
            assert response.json()["error"]["code"] == "exercise_workspace_required"


def test_an_event_from_another_data_file_is_not_found(client: TestClient) -> None:
    response = client.get(f"{_BASE}/events/harbor/list")
    assert response.status_code == 404
    assert response.json() == {
        "error": {
            "code": "exercise_event_unknown",
            "message": "That event is not in your team's data file.",
        }
    }


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("GET", f"{_BASE}/events/harbor/list"),
        ("GET", f"{_BASE}/events/harbor/list.csv"),
        ("GET", f"{_BASE}/events/harbor/settings"),
        ("PUT", f"{_BASE}/events/harbor/settings/broad"),
        ("DELETE", f"{_BASE}/events/harbor/settings/broad"),
        ("GET", f"{_BASE}/events/harbor/settings/compare?a=x&b=y"),
    ],
)
def test_every_route_resolves_its_event_against_this_teams_data_file(
    client: TestClient, method: str, path: str
) -> None:
    """Review round 1: the two settings reads used to echo an unchecked key.

    ``read_settings`` and ``delete_setting`` took ``event_key`` straight from
    the path, so a key from another data file — or from no file at all — came
    back on the response beside an empty list, and a screen could not tell "no
    settings yet" from "that event does not exist here". The save route always
    checked. Inconsistency between routes on one resource is how the unchecked
    one gets trusted, so all six now answer the same way.
    """
    response = client.request(method, path, json={"weights": dict(_WEIGHTS)}, headers=_HEADER)
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "exercise_event_unknown"


def test_an_unknown_event_costs_no_profile_read(fakes: _Fakes) -> None:
    """Review round 1: the event is resolved before the three-hundred-row join.

    An unknown event key is the cheapest thing a client can send at a route with
    no login in front of it. Reading the profiles first meant every one of those
    cost a join across the dataset and its overlay before the 404.
    """
    reads: list[uuid.UUID] = []
    original = fakes.team_view.list_team_profiles

    def counted(session: object, *, dataset_id: uuid.UUID, workspace_id: uuid.UUID) -> Any:
        reads.append(workspace_id)
        return original(session, dataset_id=dataset_id, workspace_id=workspace_id)

    with _entered(fakes, 1) as client:
        fakes.team_view.list_team_profiles = counted  # type: ignore[method-assign]
        assert client.get(f"{_BASE}/events/harbor/list").status_code == 404
        assert reads == [], "an unknown event key read the profiles"
        assert client.get(_LIST).status_code == 200
        assert len(reads) == 1, "a known event key must still read them"


@pytest.mark.parametrize(
    "path",
    [f"{_BASE}/events/harbor/list", f"{_BASE}/events/harbor/list.csv"],
)
def test_an_unknown_event_is_refused_before_a_saved_setting_is_looked_up(
    fakes: _Fakes, path: str
) -> None:
    """Review round 2 (F2): the list routes resolved the name before the event.

    Every other route in this module answers an unknown event key with
    ``exercise_event_unknown``. These two called ``_overrides_for`` first, so
    ``?setting=missing`` on a key from another data file came back as
    ``exercise_setting_unknown`` — a refusal that sends a reader looking for a
    setting when the real problem is the event, and a saved-setting lookup
    spent on a key that was never going to resolve.
    """
    lookups: list[str] = []
    profile_reads: list[uuid.UUID] = []
    original_get = fakes.settings.get_setting
    original_profiles = fakes.team_view.list_team_profiles

    def counted_lookup(
        session: object, *, workspace_id: uuid.UUID, event_key: str, name: str
    ) -> Any:
        lookups.append(name)
        return original_get(session, workspace_id=workspace_id, event_key=event_key, name=name)

    def counted_profiles(session: object, *, dataset_id: uuid.UUID, workspace_id: uuid.UUID) -> Any:
        profile_reads.append(workspace_id)
        return original_profiles(session, dataset_id=dataset_id, workspace_id=workspace_id)

    with _entered(fakes, 1) as client:
        fakes.settings.get_setting = counted_lookup  # type: ignore[method-assign]
        fakes.team_view.list_team_profiles = counted_profiles  # type: ignore[method-assign]
        response = client.get(path, params={"setting": "missing"})

    assert response.status_code == 404
    assert response.json() == {
        "error": {
            "code": "exercise_event_unknown",
            "message": "That event is not in your team's data file.",
        }
    }
    assert lookups == [], "an unknown event key looked a saved setting up"
    assert profile_reads == [], "an unknown event key read the profiles"


@pytest.mark.parametrize(
    "path",
    [_LIST, f"{_BASE}/events/northline/list.csv"],
)
def test_a_known_event_still_refuses_a_setting_this_team_has_not_saved(
    client: TestClient, path: str
) -> None:
    """The other half of F2: event-first must not swallow the setting refusal."""
    response = client.get(path, params={"setting": "missing"})
    assert response.status_code == 404
    assert response.json() == {
        "error": {
            "code": "exercise_setting_unknown",
            "message": "Your team has no saved settings with that name.",
        }
    }


def test_a_saved_setting_name_is_echoed_trimmed(client: TestClient) -> None:
    """Review round 1: the lookup trims, so the echo must trim too.

    Echoing the raw query value handed back a name that is not the name the row
    is stored under, so a client comparing the echo against its own saved list
    would see two different settings.
    """
    _save(client, "broad")
    body = client.get(_LIST, params={"setting": "  broad  "}).json()
    assert body["setting_name"] == "broad"
    csv_rows = client.get(f"{_BASE}/events/northline/list.csv", params={"setting": "  broad  "})
    assert csv_rows.status_code == 200


def test_a_weight_the_rulebook_refuses_is_refused_with_a_sentence(client: TestClient) -> None:
    response = client.put(
        f"{_SETTINGS}/broad",
        json={"weights": {"not_a_factor": 1.0}},
        headers=_HEADER,
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "exercise_weights_invalid"


def test_a_negative_weight_never_reaches_the_handler(client: TestClient) -> None:
    assert client.get(_LIST, params={"same_major": -1}).status_code == 422


# ---------------------------------------------------------------------------
# The refusal is bounded, because the route has no login in front of it
# ---------------------------------------------------------------------------


def test_a_body_of_many_unknown_weights_is_refused_without_describing_them(
    client: TestClient,
) -> None:
    """The amplification, closed at the door (review round 1).

    The rulebook's validator names every offending field at once and quotes each
    rejected key verbatim — about 190 bytes per key. Unbounded, a body of a few
    thousand short unknown keys is a request that returns megabytes and reflects
    the caller's own text onto a classroom projector. The refusal must therefore
    quote nothing and must be shorter than what was sent.
    """
    keys = {f"k{index}": 1.0 for index in range(MAX_WEIGHT_KEYS + 1)}
    response = client.put(f"{_SETTINGS}/broad", json={"weights": keys}, headers=_HEADER)
    assert response.status_code == 422
    body = response.json()
    assert body["error"]["code"] in {"exercise_weights_too_many", "invalid_request"}
    assert "k0" not in response.text, "the refusal quoted a key the caller sent"
    assert len(response.text) < 500


def test_a_very_long_weight_key_is_refused_without_echoing_it(client: TestClient) -> None:
    """The key bound now bites on the **model**, one step earlier (review 2, F2).

    Round 1 asserted the handler's own code here. Review round 2 moved the bound
    onto `SaveSettingRequest` so that it applies before pydantic can put the key
    in an error `loc`, so a body route's oversized key is refused by the
    contract rather than by the handler. The claim this test exists for — the
    key is not echoed — is unchanged and still asserted; the handler's code is
    asserted to be live below, on the path that has no model in front of it.
    """
    long_key = "z" * (MAX_WEIGHT_KEY_CHARACTERS + 1)
    response = client.put(f"{_SETTINGS}/broad", json={"weights": {long_key: 1.0}}, headers=_HEADER)
    assert response.status_code == 422
    assert long_key not in response.text
    assert response.json()["error"]["code"] == "invalid_request"


def test_the_handlers_own_key_bound_is_still_live_for_weights_with_no_model(
    client: TestClient,
) -> None:
    """The model bound does not make the handler's redundant: it covers a different door.

    Weights arriving on a query string pass through no pydantic model at all, so
    `within_bounds_or_refusal` is the only bound they meet. Asserted by calling
    it with a payload only a body could carry, which is also what keeps the code
    from becoming dead.
    """
    with pytest.raises(ExerciseError) as refused:
        exercise_matching_weights.validated({"z" * (MAX_WEIGHT_KEY_CHARACTERS + 1): 1.0})
    assert refused.value.code == "exercise_weights_key_too_long"
    assert refused.value.status_code == 422
    assert "z" not in refused.value.message


def test_an_oversized_key_with_an_invalid_value_never_reaches_the_response(
    client: TestClient,
) -> None:
    """Review round 2, F2: pydantic used to quote the key back.

    `max_length` on the field bounds the key *count*, and the handler's own
    bound runs after validation — so a body whose key is huge **and** whose
    value is not a number failed inside pydantic first, and
    `errors._describe_validation_error` builds `field` by joining the error's
    `loc`, which for a dict entry is the caller's key. Up to eight unbounded
    keys came back in one 422.

    The value here is deliberately invalid as well as the key oversized: that is
    the combination that reached pydantic's per-entry validation, and a test
    with a valid value would have been stopped by the handler and proved
    nothing.
    """
    long_key = "q" * (MAX_WEIGHT_KEY_CHARACTERS * 64)
    response = client.put(
        f"{_SETTINGS}/broad",
        json={"weights": {long_key: "not-a-number"}},
        headers=_HEADER,
    )
    assert response.status_code == 422
    assert long_key not in response.text
    assert "q" * (MAX_WEIGHT_KEY_CHARACTERS + 1) not in response.text
    assert len(response.text) < 500


def test_eight_oversized_keys_are_refused_in_one_short_response(
    client: TestClient,
) -> None:
    """The amplification the bound closes: the response cannot grow with the body."""
    keys = {f"{chr(97 + index)}" * 4096: "not-a-number" for index in range(MAX_WEIGHT_KEYS)}
    response = client.put(f"{_SETTINGS}/broad", json={"weights": keys}, headers=_HEADER)
    assert response.status_code == 422
    for key in keys:
        assert key not in response.text
    assert len(response.text) < 500


def test_a_body_at_the_bounds_still_reaches_the_handlers_own_sentence(
    client: TestClient,
) -> None:
    """The model bound must not swallow the refusal a team can act on.

    Eight keys of sixty-four characters is the largest body the bounds admit, so
    it passes the model and is refused by the rulebook with the exercise's own
    code — not by pydantic with a generic one.
    """
    keys = {
        f"{chr(97 + index)}" * MAX_WEIGHT_KEY_CHARACTERS: 1.0 for index in range(MAX_WEIGHT_KEYS)
    }
    response = client.put(f"{_SETTINGS}/broad", json={"weights": keys}, headers=_HEADER)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "exercise_weights_invalid"


def test_the_weight_refusal_is_capped_even_at_the_key_bound(client: TestClient) -> None:
    """The second line: the message is cut whatever the validator says.

    Eight keys of sixty-four characters is the largest input the bounds admit,
    and the response to it must still be a sentence rather than a page.
    """
    keys = {
        f"{chr(97 + index)}" * MAX_WEIGHT_KEY_CHARACTERS: 1.0 for index in range(MAX_WEIGHT_KEYS)
    }
    response = client.put(f"{_SETTINGS}/broad", json={"weights": keys}, headers=_HEADER)
    assert response.status_code == 422
    message = response.json()["error"]["message"]
    assert len(message) <= MAX_WEIGHT_REFUSAL_CHARACTERS + 40


def test_the_same_bounds_apply_to_weights_arriving_on_the_query_string(
    client: TestClient,
) -> None:
    """The list and CSV routes take weights too, and go through the same check.

    The four weight parameters are declared, so a count above the bound cannot
    arrive that way — which is the point: the bound lives in the one function
    both paths call, rather than on the body model alone, so it cannot be true
    of one route and not the other. Asserted by calling that function directly
    with a payload only a body could carry.
    """
    with pytest.raises(ExerciseError) as refused:
        exercise_matching_weights.validated(
            {f"k{index}": 1.0 for index in range(MAX_WEIGHT_KEYS + 1)}
        )
    assert refused.value.code == "exercise_weights_too_many"
    assert refused.value.status_code == 422
    # …and a well-formed query weighting still passes through it untouched.
    assert client.get(_LIST, params={"same_major": 1.0}).status_code == 200


def test_a_state_changing_request_without_the_exercise_header_is_refused(
    client: TestClient,
) -> None:
    saved = client.put(f"{_SETTINGS}/broad", json={"weights": dict(_WEIGHTS)})
    removed = client.delete(f"{_SETTINGS}/broad")
    for response in (saved, removed):
        assert response.status_code == 403
        assert response.json()["error"]["code"] == "exercise_request_header_required"


def test_the_read_routes_need_no_exercise_header(client: TestClient) -> None:
    assert client.get(_LIST).status_code == 200
    assert client.get(_SETTINGS).status_code == 200


def test_deleting_a_name_the_team_has_not_saved_is_not_found(client: TestClient) -> None:
    response = client.delete(f"{_SETTINGS}/absent", headers=_HEADER)
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "exercise_setting_unknown"


def test_an_empty_setting_name_is_refused_with_a_sentence(client: TestClient) -> None:
    response = _save(client, "%20")
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "exercise_setting_name_unusable"


def test_every_refusal_code_is_the_exercises_own(client: TestClient) -> None:
    codes = {
        client.get(f"{_BASE}/events/harbor/list").json()["error"]["code"],
        client.delete(f"{_SETTINGS}/absent", headers=_HEADER).json()["error"]["code"],
        client.put(f"{_SETTINGS}/broad", json={"weights": {}}).json()["error"]["code"],
    }
    assert codes.isdisjoint({"unauthenticated", "forbidden", "invalid_token"})
    assert all(code.startswith("exercise_") for code in codes)


# ---------------------------------------------------------------------------
# PLACEHOLDER (OQ-CE-01) — the class-year order closes nothing
# ---------------------------------------------------------------------------


def test_the_class_year_order_is_empty_while_ann_has_not_stated_one() -> None:
    """(d) The seam, and the fact that nothing is plugged into it yet.

    Review round 1 withdrew an order derived from the data file. It was
    deterministic, but file order is not seniority, so the list would print
    Ann's verbatim "Tied on major; ordered by year." about an order that is
    arbitrary — an untrue statement to a class participant, which is the class
    of defect review rejected on PR #180. Empty is what closes nothing.
    """
    assert PLACEHOLDER_CLASS_YEAR_RANK == {}
    assert rankable_set(_PROFILES, _EVENTS).year_rank == PLACEHOLDER_CLASS_YEAR_RANK


def test_the_year_sentences_are_never_emitted_by_the_api_today() -> None:
    """(a) Neither year line can reach a screen while the order is empty.

    Asserted over every name on every list the four weightings below produce,
    and against the domain's own constant rather than against a copy of the
    wording here — ``reasons.py`` owns the words (OQ-CE-12) and this file must
    not restate them.
    """
    forbidden = {
        phrase_as_sentence(ANN_TIED_ON_YEAR_PHRASE),
        phrase_as_sentence("tied on what counted; ordered by year"),
    }
    fakes = _Fakes()
    with _entered(fakes, 1) as client:
        for params in (
            {},
            {"same_major": 1.0, "stated_interest_overlap": 0.0},
            {"same_major": 0.0, "stated_interest_overlap": 1.0},
            {"career_goal_fit": 1.0},
        ):
            body = client.get(_LIST, params=params).json()
            reasons = {entry["reason"] for entry in body["entries"]}
            assert reasons.isdisjoint(forbidden), f"a year sentence reached the list for {params}"


def test_a_tie_the_year_would_have_settled_falls_to_the_fixed_order(
    client: TestClient,
) -> None:
    """(b) The honest sentence for a tie nothing in the data separates.

    Several profiles in the fixture share a major and a marker and have nothing
    else on file, and differ only in a column the order no longer reads. With a
    year order they would have been separated by it; with none, the fixed order
    seeded from the data file's checksum decides, and the line says so.
    """
    fixed_order_sentence = phrase_as_sentence("tied; placed in a fixed order that never changes")
    reasons = [entry["reason"] for entry in client.get(_LIST).json()["entries"]]
    assert fixed_order_sentence in reasons, (
        "no name was placed by the fixed order; this fixture no longer exercises the branch"
    )


def test_every_class_year_in_the_file_is_reported_as_unlisted(client: TestClient) -> None:
    """(c) The gap is visible on the response rather than silent.

    ``unlisted_class_years`` is the domain's own report of years the ordering
    does not name. With an empty ordering that is every year in the file, which
    is exactly the fact a screen should be able to show while OQ-CE-01 is open.
    """
    body = client.get(_LIST).json()
    expected: list[str] = []
    for profile in _PROFILES:
        year = profile.class_year
        if year is not None and profile.major is not None and year not in expected:
            expected.append(year)
    assert body["unlisted_class_years"] == expected
    assert expected, "the fixture must carry a class year for this to mean anything"


def test_the_placeholder_marker_is_literally_present_in_the_source() -> None:
    """A placeholder nobody can grep for is a decision that has quietly closed."""
    source = _MODELS_SOURCE.read_text(encoding="utf-8")
    assert "PLACEHOLDER (OQ-CE-01)" in source
    assert "OQ-CE-02" in source


def test_no_module_here_writes_down_a_class_year_or_a_major() -> None:
    """The vocabularies are Ann's; this track names none of them (OQ-CE-01)."""
    for source_file in _TRACK_SOURCES:
        source = source_file.read_text(encoding="utf-8")
        for guess in ("Senior", "Junior", "Sophomore", "Freshman", "Finance", "Marketing"):
            assert guess not in source, f"{source_file.name} writes down {guess!r}"


# ---------------------------------------------------------------------------
# D6 / D8 — what a response may never carry
# ---------------------------------------------------------------------------

#: Names that must appear on no exercise response model here. The addressing
#: four are the workspace router's, restated because these routes are reached
#: with the same cookie.
_FORBIDDEN_RESPONSE_FIELDS = frozenset(
    {"seed", "token", "workspace_token", "workspace_token_hash", "workspace_id", "dataset_id"}
    | set(EXERCISE_WITHHELD_FIELDS)
)

#: ADR-0025 D8: rank, counts, the team's own weights and one reason. No number
#: that reads as a score.
_SCORE_SHAPED = ("score", "percent", "confidence", "probability", "likelihood")


#: The same four modules ``_TRACK_SOURCES`` reads, as modules.
#:
#: Widened from ``(exercise_matching, exercise_matching_models)`` by
#: CE-RESULTS-API, carrying a LOW item from PR #188's re-review: review round 2's
#: F4 split the weights helpers and the CSV download into modules of their own
#: and widened the three **source** walks to cover them, but this **model** walk
#: kept reading two of the four. A response model declared in ``_csv`` or
#: ``_weights`` would have escaped the D6 and D8 field checks entirely — quietly,
#: because a walk that reads fewer modules still passes.
_TRACK_MODULES = (
    exercise_matching,
    exercise_matching_models,
    exercise_matching_csv,
    exercise_matching_weights,
)


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
    assert len(_models_in_modules()) >= 8


def test_the_model_walk_reads_every_module_the_source_walks_read() -> None:
    """The two lists must not drift apart again (PR #188 LOW item).

    A module added to ``_TRACK_SOURCES`` and forgotten here is a module whose
    response models never meet the D6 and D8 field checks.
    """
    assert {Path(module.__file__ or "") for module in _TRACK_MODULES} == set(_TRACK_SOURCES)


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


def test_no_handler_docstring_names_the_withheld_column() -> None:
    """FastAPI publishes a docstring as an operation description (ADR-0025 D6)."""
    tree = ast.parse(_ROUTER_SOURCE.read_text(encoding="utf-8"))
    docstrings = [
        ast.get_docstring(node) or ""
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)
    ]
    assert docstrings, "the walk found no handlers"
    for withheld in EXERCISE_WITHHELD_FIELDS:
        offenders = [text for text in docstrings if withheld in text]
        # The module docstring may name the rule; a *handler* docstring may not,
        # because that is the text the contract publishes.
        assert offenders == [], f"a handler docstring names {withheld}"


def test_the_served_exercise_contract_names_neither_either() -> None:
    """The models could be clean and the document not, if a route grew a parameter."""
    app = FastAPI()
    for router in routers_for(_settings()):
        app.include_router(router)
    document = app.openapi()
    for withheld in EXERCISE_WITHHELD_FIELDS:
        assert withheld not in str(document), f"{withheld} appears in the exercise contract"
    # Scoped to this track's own models. The instructor page's `DatasetView`
    # legitimately publishes a dataset id — it is the instructor's own screen —
    # and widening this walk to every exercise schema would assert that track's
    # decisions from this file rather than this track's.
    ours = {model.__name__ for model in _models_in_modules()}
    schemas = document.get("components", {}).get("schemas", {})
    assert ours & set(schemas), "none of this track's models reached the contract"
    for name, schema in schemas.items():
        if name not in ours:
            continue
        offenders = sorted(set(schema.get("properties", {})) & _FORBIDDEN_RESPONSE_FIELDS)
        assert offenders == [], f"{name} publishes {offenders}"
        for field_name in schema.get("properties", {}):
            assert not any(shape in field_name.lower() for shape in _SCORE_SHAPED), (
                f"{name}.{field_name} reads as a score; ADR-0025 D8"
            )


def test_the_exercise_paths_carry_no_workspace_identifier() -> None:
    """The cookie is the whole of the addressing: no id is accepted anywhere.

    **Read off the OpenAPI document, not ``app.routes``** (CE-RESULTS-API
    correction). On this FastAPI version ``include_router`` leaves an
    ``_IncludedRouter`` wrapper in ``app.routes`` whose ``path`` is ``None``, so
    the earlier walk's ``startswith`` matched nothing at all and this guard
    passed over an empty set. The count below is what stops that coming back:
    a walk with nothing in it now fails instead of passing.
    """
    app = FastAPI()
    for router in routers_for(_settings()):
        app.include_router(router)
    team_paths = {
        path
        for path in app.openapi().get("paths", {})
        if path.startswith("/v1/exercise/workspaces/current")
    }

    assert len(team_paths) >= 6, "the walk found none of this track's paths"
    for path in sorted(team_paths):
        for forbidden in ("{workspace_id}", "{token}", "{team_number}", "{dataset_id}"):
            assert forbidden not in path, f"{path} accepts an identifier from the client"


# ---------------------------------------------------------------------------
# Wiring
# ---------------------------------------------------------------------------


def test_the_weight_parameters_are_the_rulebooks_own_keys() -> None:
    """Four names in a signature, checked against the registry rather than a list."""
    assert exercise_matching.EXERCISE_WEIGHT_PARAMETER_KEYS == EXERCISE_APPROVED_SCORING_KEYS
    signature = ast.parse(_ROUTER_SOURCE.read_text(encoding="utf-8"))
    handlers = {
        node.name: {argument.arg for argument in node.args.args}
        for node in ast.walk(signature)
        if isinstance(node, ast.FunctionDef)
    }
    for handler in ("read_ranked_list", "download_ranked_list"):
        assert handlers[handler] >= EXERCISE_APPROVED_SCORING_KEYS


def test_the_router_is_declared_under_the_class_exercise_capability() -> None:
    declared = {
        capability
        for router, capability in CAPABILITY_SCOPED_ROUTERS
        if router is exercise_matching.router
    }
    assert declared == {Capability.CLASS_EXERCISE}


def test_the_routes_answer_404_in_a_cba_process() -> None:
    app = FastAPI()
    for router in routers_for(Settings(product_scope=ProductScope.CBA)):
        app.include_router(router)
    with TestClient(app) as cba:
        assert cba.get(_LIST).status_code == 404
        assert cba.get(f"{_BASE}/events").status_code == 404


def test_the_router_imports_no_persistence_authz_or_principal_machinery() -> None:
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


def test_the_download_is_written_with_the_standard_library() -> None:
    """Design spec §0: ``tools/scan_forbidden.py`` refuses the pandas writer by name."""
    source = _CSV_SOURCE.read_text(encoding="utf-8")
    assert "csv.writer" in source
    assert "io.StringIO" in source
    # Assembled rather than written out: ``tools/scan_forbidden.py`` matches the
    # call by name, and a test that spells it is a test that fails the gate it
    # is asserting.
    pandas_call = "to_" + "csv("
    assert pandas_call not in source
    assert "import pandas" not in source


def test_nothing_here_reaches_the_simulation_loader() -> None:
    """The sole reader of the withheld column is not reachable from these routes."""
    for source_file in _TRACK_SOURCES:
        assert "load_simulation_profiles(" not in source_file.read_text(encoding="utf-8")


def test_the_sequence_of_profiles_a_list_is_built_from_is_the_files_order() -> None:
    """Everything order-dependent downstream reads this sequence, so it is pinned."""
    rankable = rankable_set(_PROFILES, _EVENTS)
    assert [profile.profile_no for profile in rankable.profiles] == [1, 2, 3, 4, 5, 6, 7]
    assert rankable.unrankable_profile_count == 1
