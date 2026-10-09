"""The results routes: the panels and the asking choice (design spec §10–§12).

Split by topic from ``tests/unit/test_exercise_results_router.py``; see
``test_exercise_results_rules.py`` for what the split files pin, in order.
"""

from __future__ import annotations

from dataclasses import replace

import pytest
from fastapi.testclient import TestClient
from smartmatch_api.routers.exercise_results_models import (
    EXERCISE_ROUNDS,
    FIRST_ROUND,
    MAX_ASKING_CHOICE_CHARACTERS,
)
from smartmatch_domain.exercise.asking import (
    AskingChoice,
)
from smartmatch_domain.exercise.registry import EXERCISE_DEFAULT_WEIGHTS
from smartmatch_domain.exercise.simulation import (
    EVENT_SEATS,
    EXISTING_SIGNUPS,
    SimulationCoefficients,
)
from smartmatch_persistence.exercise.results_rows import InvitedProfile
from smartmatch_persistence.exercise.settings_repository import SavedSetting

from tests.unit.exercise_results_router.support import (
    _ASKING,
    _BASE,
    _DATASET_ID,
    _FINAL,
    _FINAL_BODY,
    _HEADER,
    _INVITE_LIMIT,
    _RESULTS,
    _RESULTS_TWO,
    _WHEN,
    _entered,
    _Fakes,
    _run_round_one,
)

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
    fakes: _Fakes, client: TestClient, confirmed: SimulationCoefficients, choice: str
) -> None:
    _run_round_one(fakes, client)

    response = client.post(_ASKING, json={"choice": choice}, headers=_HEADER)

    assert response.status_code == 200, response.text
    assert response.json()["choice"] == choice
    assert list(fakes.results.choices.values()) == [choice]


def test_a_second_choice_is_refused_rather_than_replacing_the_first(
    fakes: _Fakes, client: TestClient, confirmed: SimulationCoefficients
) -> None:
    _run_round_one(fakes, client)
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
# A run keeps the names it invited (issue #271)
# ---------------------------------------------------------------------------


def _ranked_entries(client: TestClient) -> list[dict[str, object]]:
    """The team's own list for the final setting, as its screen shows it."""
    listed = client.get(f"{_BASE}/events/round-one/list", params={"setting": _FINAL})
    assert listed.status_code == 200, listed.text
    return list(listed.json()["entries"])


_SNAPSHOT_FIELDS = (
    "rank",
    "profile_no",
    "display_name",
    "major",
    "class_year",
    "marker",
    "reason",
)


def test_a_run_answers_with_the_names_its_list_showed_in_list_order(
    fakes: _Fakes, client: TestClient, confirmed: SimulationCoefficients
) -> None:
    """The names are the ranked list's own seven fields, and nothing else."""
    fakes.unlock("round-one")
    listed = _ranked_entries(client)

    body = client.post(_RESULTS, json=_FINAL_BODY, headers=_HEADER).json()

    invited = body["invited_profiles"]
    assert len(invited) == _INVITE_LIMIT
    assert [set(entry) for entry in invited] == [set(_SNAPSHOT_FIELDS)] * _INVITE_LIMIT
    assert invited == [{name: entry[name] for name in _SNAPSHOT_FIELDS} for entry in listed]
    assert [entry["rank"] for entry in invited] == list(range(1, _INVITE_LIMIT + 1))
    assert sorted(entry["profile_no"] for entry in invited) == body["team"]["invited_profile_nos"]


def test_the_stored_run_keeps_the_names_and_the_four_stated_weights(
    fakes: _Fakes, client: TestClient, confirmed: SimulationCoefficients
) -> None:
    fakes.unlock("round-one")
    listed = _ranked_entries(client)

    assert client.post(_RESULTS, json=_FINAL_BODY, headers=_HEADER).status_code == 201

    (stored,) = fakes.results.runs.values()
    assert [entry.display_name for entry in stored.invited] == [
        entry["display_name"] for entry in listed
    ]
    assert [entry.reason for entry in stored.invited] == [entry["reason"] for entry in listed]
    assert stored.setting_weights == dict(EXERCISE_DEFAULT_WEIGHTS)


def test_deleting_the_saved_setting_does_not_take_the_runs_names_with_it(
    fakes: _Fakes, client: TestClient, confirmed: SimulationCoefficients
) -> None:
    """Issue #271, end to end: run, delete the setting, read the results again.

    The list route now refuses that setting — which is what used to turn every
    name on the results screen into "Profile 17" — and the results still name
    everybody, because they never ask it.
    """
    fakes.unlock("round-one")
    ran = client.post(_RESULTS, json=_FINAL_BODY, headers=_HEADER).json()
    workspace = fakes.workspaces.rows[(_DATASET_ID, 1)]

    del fakes.settings.rows[(workspace.id, "round-one", _FINAL)]

    gone = client.get(f"{_BASE}/events/round-one/list", params={"setting": _FINAL})
    again = client.get(_RESULTS)
    assert gone.status_code == 404
    assert gone.json()["error"]["code"] == "exercise_setting_unknown"
    assert again.status_code == 200
    assert again.json()["invited_profiles"] == ran["invited_profiles"]
    assert all(entry["display_name"] for entry in again.json()["invited_profiles"])
    assert again.json()["setting_name"] == _FINAL


def test_saving_the_setting_again_with_other_weights_does_not_change_the_runs_names(
    fakes: _Fakes, client: TestClient, confirmed: SimulationCoefficients
) -> None:
    """The same name over different weights is a different list — but not this run's."""
    fakes.unlock("round-one")
    ran = client.post(_RESULTS, json=_FINAL_BODY, headers=_HEADER).json()
    workspace = fakes.workspaces.rows[(_DATASET_ID, 1)]
    major_only = {**dict.fromkeys(EXERCISE_DEFAULT_WEIGHTS, 0.0), "past_event_topic_overlap": 1.0}

    fakes.settings.rows[(workspace.id, "round-one", _FINAL)] = SavedSetting(
        event_key="round-one", name=_FINAL, weights=major_only, created_at=_WHEN
    )

    now = _ranked_entries(client)
    again = client.get(_RESULTS).json()
    assert [entry["profile_no"] for entry in now] != [
        entry["profile_no"] for entry in ran["invited_profiles"]
    ], "the re-saved setting builds a different list, or this test proves nothing"
    assert again["invited_profiles"] == ran["invited_profiles"]


def test_a_run_stored_before_names_were_kept_reads_back_without_inventing_any(
    fakes: _Fakes, client: TestClient, confirmed: SimulationCoefficients
) -> None:
    """A backfilled row: names, and no rank, marker or reason. An older one: nothing."""
    fakes.unlock("round-one")
    assert client.post(_RESULTS, json=_FINAL_BODY, headers=_HEADER).status_code == 201
    ((key, stored),) = fakes.results.runs.items()

    fakes.results.runs[key] = replace(
        stored,
        invited=tuple(
            InvitedProfile(profile_no=entry.profile_no, display_name=entry.display_name)
            for entry in stored.invited
        ),
        setting_weights=None,
    )
    backfilled = client.get(_RESULTS).json()["invited_profiles"]
    fakes.results.runs[key] = replace(stored, invited=(), setting_weights=None)
    older = client.get(_RESULTS)

    assert [entry["display_name"] for entry in backfilled] == [
        entry.display_name for entry in stored.invited
    ]
    assert {(entry["rank"], entry["marker"], entry["reason"]) for entry in backfilled} == {
        (None, None, None)
    }
    assert older.status_code == 200
    assert older.json()["invited_profiles"] == []
    assert older.json()["team"]["invited_count"] == _INVITE_LIMIT, "the counts still stand"


def test_everybody_in_the_file_stays_counts_only(
    fakes: _Fakes, client: TestClient, confirmed: SimulationCoefficients
) -> None:
    """The names sit on the response, never on a panel: the 300 stay a number."""
    fakes.unlock("round-one")

    body = client.post(_RESULTS, json=_FINAL_BODY, headers=_HEADER).json()

    for panel in (body["team"], body["email_everyone"]):
        assert "invited_profiles" not in panel
        assert "display_name" not in str(panel)


def test_a_results_run_from_an_old_fractional_setting_still_works(
    fakes: _Fakes, client: TestClient, confirmed: SimulationCoefficients
) -> None:
    fakes.unlock("round-one")
    workspace = fakes.workspaces.rows[(_DATASET_ID, 1)]
    fakes.settings.rows[(workspace.id, "round-one", _FINAL)] = SavedSetting(
        event_key="round-one",
        name=_FINAL,
        weights={"same_major": 0.5, "stated_interest_overlap": 0.25},
        created_at=_WHEN,
    )
    assert client.post(_RESULTS, json=_FINAL_BODY, headers=_HEADER).status_code == 201
