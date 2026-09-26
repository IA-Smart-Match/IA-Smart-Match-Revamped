"""The results routes: the panels and the asking choice (design spec §10–§12).

Split by topic from ``tests/unit/test_exercise_results_router.py``; see
``test_exercise_results_rules.py`` for what the split files pin, in order.
"""

from __future__ import annotations

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
from smartmatch_domain.exercise.simulation import (
    EVENT_SEATS,
    EXISTING_SIGNUPS,
    SimulationCoefficients,
)
from smartmatch_persistence.exercise.settings_repository import SavedSetting

from tests.unit.exercise_results_router.support import (
    _ASKING,
    _BASE,
    _FINAL_BODY,
    _HEADER,
    _INVITE_LIMIT,
    _RESULTS,
    _RESULTS_TWO,
    _WHEN,
    _entered,
    _Fakes,
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
