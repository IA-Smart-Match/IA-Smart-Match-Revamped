"""The results routes: a team's refresh, its policy and refresh all (§12–§14).

Split by topic from ``tests/unit/test_exercise_results_router.py``; see
``test_exercise_results_rules.py`` for what the split files pin, in order.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime

import pytest
from fastapi.testclient import TestClient
from smartmatch_api.routers import (
    exercise_instructor_refresh,
)
from smartmatch_api.routers.exercise_matching_models import (
    event_evidence,
    rankable_set,
)
from smartmatch_api.routers.exercise_results_refresh import (
    invited_without_a_card,
    refresh_plan,
)
from smartmatch_domain.exercise.asking import (
    AskingChoice,
)
from smartmatch_domain.exercise.simulation import (
    SimulationCoefficients,
)
from smartmatch_domain.student_factors import career_goal_fit

from tests.unit.exercise_results_router.support import (
    _ASKING,
    _BASE,
    _DATASET_ID,
    _EVENTS,
    _FINAL_BODY,
    _HEADER,
    _PAST,
    _PROFILES,
    _REFRESH,
    _REFRESH_ALL,
    _REFRESH_SOURCE,
    _RESULTS,
    _RESULTS_TWO,
    _ROUND_ONE,
    _ROUND_TWO,
    _ROWS,
    _entered,
    _exercise_app,
    _Fakes,
    _instructor,
    _prepare_refresh,
    _Row,
    _run_round_one,
    _seed_choice,
)

# ---------------------------------------------------------------------------
# The refresh (design spec §13)
# ---------------------------------------------------------------------------


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
    _seed_choice(fakes, 1)

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
# Making the refresh visible (Oct-2 checklist §6)
# ---------------------------------------------------------------------------

_MARKER_KEYS = {"major_only", "major_plus_events", "completed_card"}
_LEGACY_COUNT_KEYS = ("cards_completed", "non_responding", "topics_added")


def test_the_choice_is_refused_before_round_one_has_results(
    fakes: _Fakes, client: TestClient
) -> None:
    """Checklist: "The choice appears only after the team has its round-one results"."""
    before = client.get(_ASKING).json()

    response = client.post(_ASKING, json={"choice": "required"}, headers=_HEADER)

    assert before["first_round_results"] is False
    assert response.status_code == 409
    assert response.json()["error"] == {
        "code": "exercise_no_first_round_results",
        "message": "Run the first round's results before asking.",
    }
    assert fakes.results.choices == {}, "a refused choice must store nothing"


def test_an_unknown_choice_is_still_answered_before_the_round_one_gate(
    client: TestClient,
) -> None:
    response = client.post(_ASKING, json={"choice": "bribery"}, headers=_HEADER)

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "exercise_asking_choice_unknown"


def test_the_asking_route_says_when_round_one_has_results_and_names_the_event(
    fakes: _Fakes, client: TestClient, confirmed: SimulationCoefficients
) -> None:
    assert client.get(_ASKING).json()["first_round_event_name"] == _ROUND_ONE.name

    _run_round_one(fakes, client)
    after = client.get(_ASKING).json()

    assert after["first_round_results"] is True
    assert after["first_round_event_name"] == _ROUND_ONE.name
    assert after["refreshed_at"] is None
    assert client.post(_ASKING, json={"choice": "required"}, headers=_HEADER).status_code == 200


def test_a_refresh_reports_when_it_happened_and_what_it_changed(
    fakes: _Fakes, client: TestClient, confirmed: SimulationCoefficients
) -> None:
    """Every fact the checklist's summary sentence and before/after line need."""
    first = _prepare_refresh(fakes, client)
    workspace = fakes.workspaces.rows[(_DATASET_ID, 1)]
    invited = first["team"]["invited_profile_nos"]

    body = client.post(_REFRESH, json={}, headers=_HEADER).json()

    stored = fakes.results.refreshed[workspace.id]
    assert datetime.fromisoformat(body["refreshed_at"]) == stored
    counts = body["refresh_counts"]
    assert {key: counts[key] for key in _LEGACY_COUNT_KEYS} == {
        key: body[key] for key in _LEGACY_COUNT_KEYS
    }
    assert counts["invited_without_card"] == len(invited_without_a_card(_PROFILES, invited))
    assert counts["invited_without_card"] >= counts["cards_completed"] >= 1
    before, after = counts["marker_counts_before"], counts["marker_counts_after"]
    assert set(before) == set(after) == _MARKER_KEYS
    assert sum(before.values()) == sum(after.values()) == len(_PROFILES), "every row is counted"
    assert before == {"major_only": 7, "major_plus_events": 3, "completed_card": 2}
    assert after["completed_card"] == before["completed_card"] + counts["cards_completed"]


def test_a_reload_reads_the_same_time_and_the_same_counts(
    fakes: _Fakes, client: TestClient, confirmed: SimulationCoefficients
) -> None:
    _prepare_refresh(fakes, client)
    posted = client.post(_REFRESH, json={}, headers=_HEADER).json()

    read = client.get(_ASKING).json()

    assert read["refreshed"] is True
    assert read["refreshed_at"] == posted["refreshed_at"]
    assert read["refresh_counts"] == posted["refresh_counts"]


def test_a_second_refresh_changes_nothing_and_the_time_stands(
    fakes: _Fakes, client: TestClient, confirmed: SimulationCoefficients
) -> None:
    """Checklist: a second press "does nothing"; the screen says when the first was."""
    _prepare_refresh(fakes, client)
    first = client.post(_REFRESH, json={}, headers=_HEADER).json()
    overlays = dict(fakes.team_view.overlays)

    second = client.post(_REFRESH, json={}, headers=_HEADER)

    assert second.status_code == 409
    assert second.json()["error"]["code"] == "exercise_already_refreshed"
    assert fakes.team_view.overlays == overlays
    assert client.get(_ASKING).json()["refreshed_at"] == first["refreshed_at"]


def test_the_list_marks_the_profiles_the_refresh_changed(
    fakes: _Fakes, client: TestClient, confirmed: SimulationCoefficients
) -> None:
    """Checklist: "The changed profiles are marked in the list"."""
    before = client.get(f"{_BASE}/events/round-one/list").json()
    assert all(entry["refresh_marks"] == [] for entry in before["entries"])
    assert before["first_round_event_name"] == _ROUND_ONE.name

    _prepare_refresh(fakes, client)
    client.post(_REFRESH, json={}, headers=_HEADER)
    after = client.get(f"{_BASE}/events/round-one/list").json()

    workspace = fakes.workspaces.rows[(_DATASET_ID, 1)]
    marks = {entry["profile_no"]: entry["refresh_marks"] for entry in after["entries"]}
    checked = 0
    for (workspace_id, profile_no), row in fakes.team_view.overlays.items():
        assert workspace_id == workspace.id
        if profile_no not in marks:
            continue
        expected = [
            mark
            for mark, applies in (
                ("new_card", row.overlay_card_interests is not None),
                ("new_event", bool(row.overlay_added_event_topics)),
                ("stopped_responding", row.non_responding),
            )
            if applies
        ]
        assert marks[profile_no] == expected
        checked += 1
    assert checked >= 1, "no changed profile is on the list, so nothing was checked"
    untouched = set(marks) - {profile_no for _, profile_no in fakes.team_view.overlays}
    assert all(marks[profile_no] == [] for profile_no in untouched)


def test_one_teams_marks_never_reach_another_teams_list(
    fakes: _Fakes, confirmed: SimulationCoefficients
) -> None:
    """Checklist: "One team's refresh changes nothing for any other team"."""
    with _entered(fakes, 1) as first, _entered(fakes, 2) as second:
        _prepare_refresh(fakes, first)
        assert first.post(_REFRESH, json={}, headers=_HEADER).status_code == 200

        own = first.get(f"{_BASE}/events/round-one/list").json()
        other = second.get(f"{_BASE}/events/round-one/list").json()
        other_asking = second.get(_ASKING).json()

    assert any(entry["refresh_marks"] for entry in own["entries"])
    assert all(entry["refresh_marks"] == [] for entry in other["entries"])
    assert other_asking["refreshed"] is False
    assert other_asking["refreshed_at"] is None
    assert other_asking["refresh_counts"] is None


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


def test_a_refresh_writes_the_hidden_goal_onto_every_copied_card(
    fakes: _Fakes, client: TestClient, confirmed: SimulationCoefficients
) -> None:
    """Ann's data file, 2026-09-24, through the route (OQ-CE-13).

    A new card copies the hidden columns: every overlay row this refresh gave a card to
    carries its file row's **hidden true** career goal, and ``None`` exactly
    where the file has none. Asserted against ``_ROWS`` rather than a written-out
    list, so a fixture row that gains a goal cannot quietly stop being checked.
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
        assert row.overlay_card_career_goal == _ROWS[profile_no - 1].hidden_true_career_goal
    assert any(row.overlay_card_career_goal is not None for row in given_a_card.values()), (
        "no copied card carried a hidden goal, so the new reading was never exercised"
    )


def test_an_overlay_card_with_no_goal_of_its_own_reads_the_base_rows() -> None:
    """How ``_profile_evidence`` resolves a copied card: overlay over base.

    A copied card whose ``card_career_goal`` is ``NULL`` — a file row with no
    hidden goal — finds the base row's goal through the overlay. The card
    exists, because the overlay recorded interests, so a :class:`ProfileCard`
    is built and ``career_goal_fit`` can earn on it.
    """
    base = _Row(4, "Devi Rao", career_goal="analytics").team_row()
    copied = replace(base, overlay_card_interests=("brand",), overlay_card_career_goal=None)

    rankable = rankable_set((copied,), _EVENTS)

    assert len(rankable.profiles) == 1
    card = rankable.profiles[0].evidence.card
    assert card is not None, "the copied interests are a card"
    assert card.career_goal == "analytics", "the base row's goal is read through the overlay"
    fit = career_goal_fit(rankable.profiles[0].evidence, event_evidence(_ROUND_ONE))
    assert fit.value == 1.0


def test_a_copied_hidden_goal_is_read_as_the_topic_it_points_at() -> None:
    """The copied goal is one of Ann's labels; the ranker compares its topic."""
    base = _Row(4, "Devi Rao").team_row()
    copied = replace(
        base,
        overlay_card_interests=("Consulting",),
        overlay_card_career_goal="Data, analytics or IT role",
    )
    northline = replace(_ROUND_ONE, topic_tags=("Technology / information systems",))

    rankable = rankable_set((copied,), (_PAST, northline, _ROUND_TWO))

    card = rankable.profiles[0].evidence.card
    assert card is not None
    assert card.career_goal == "Technology / information systems"
    assert career_goal_fit(rankable.profiles[0].evidence, event_evidence(northline)).value == 1.0


def test_the_two_draws_are_independent() -> None:
    """One salt for both would make ``required``'s cost fall on the people it helped."""
    no_card = tuple(range(1, 21))

    plan = refresh_plan(
        choice=AskingChoice.REQUIRED,
        seed=42,
        attended_profile_nos=(1, 2),
        no_card_profile_nos=no_card,
    )

    assert set(plan.card_completers).isdisjoint(plan.non_responding)
    # 80 percent and 15 percent of twenty: 16 and 3, no half to round.
    assert len(plan.card_completers) == 16
    assert len(plan.non_responding) == 3


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
    with _entered(fakes, 1) as one, _entered(fakes, 2):
        one.post(_RESULTS, json=_FINAL_BODY, headers=_HEADER)
        one.post(_ASKING, json={"choice": "required"}, headers=_HEADER)
        _seed_choice(fakes, 2)

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


def test_refresh_all_reports_every_team_and_why_it_was_skipped(
    fakes: _Fakes, confirmed: SimulationCoefficients
) -> None:
    """Ann, 2026-10-02: "which teams were refreshed and which were skipped and why"."""
    fakes.unlock("round-one")
    with (
        _entered(fakes, 1) as one,
        _entered(fakes, 2) as two,
        _entered(fakes, 3),
        _entered(fakes, 4),
    ):
        for client in (one, two):
            client.post(_RESULTS, json=_FINAL_BODY, headers=_HEADER)
            client.post(_ASKING, json={"choice": "required"}, headers=_HEADER)
        earlier = two.post(_REFRESH, json={}, headers=_HEADER).json()
        # team three never chooses; team four has a choice and no round one
        _seed_choice(fakes, 4)

        with _instructor(fakes) as instructor:
            body = instructor.post(_REFRESH_ALL, headers=_HEADER).json()
        own = one.get(_ASKING).json()

    assert [team["team_number"] for team in body["teams"]] == [1, 2, 3, 4]
    assert [(team["outcome"], team["reason_code"]) for team in body["teams"]] == [
        ("refreshed", None),
        ("skipped", "already_refreshed"),
        ("skipped", "no_asking_choice"),
        ("skipped", "no_round_one_run"),
    ]
    refreshed, already, unchosen, behind = body["teams"]
    # The refreshed team's line is the same summary that team now reads itself.
    assert refreshed["refresh_counts"] == own["refresh_counts"]
    assert refreshed["refreshed_at"] == own["refreshed_at"]
    assert refreshed["first_round_event_name"] == _ROUND_ONE.name
    assert refreshed["refresh_counts"]["cards_completed"] >= 1
    # A team that refreshed itself earlier keeps its own time and is not re-counted.
    assert already["refreshed_at"] == earlier["refreshed_at"]
    assert already["refresh_counts"] is None
    for skipped in (unchosen, behind):
        assert skipped["refreshed_at"] is None
        assert skipped["refresh_counts"] is None
    assert {team["dataset_label"] for team in body["teams"]} == {"Made-up student body (sample)"}
    # The three fields the route has always sent keep their meaning.
    assert body["refreshed_team_numbers"] == [1]
    assert body["refreshed"] == 1
    assert body["skipped"] == 1, "only the chosen team that could not be refreshed"


def test_refresh_all_reports_nothing_for_a_classroom_nobody_entered(fakes: _Fakes) -> None:
    with _instructor(fakes) as instructor:
        body = instructor.post(_REFRESH_ALL, headers=_HEADER).json()

    assert body == {"refreshed_team_numbers": [], "refreshed": 0, "skipped": 0, "teams": []}


def test_refresh_all_does_not_blame_round_one_for_a_team_cleared_mid_request(
    fakes: _Fakes, confirmed: SimulationCoefficients, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A lost claim is read back and named for what the row now says."""
    fakes.unlock("round-one")
    with _entered(fakes, 1) as one:
        one.post(_RESULTS, json=_FINAL_BODY, headers=_HEADER)
        one.post(_ASKING, json={"choice": "required"}, headers=_HEADER)
        workspace = fakes.workspaces.rows[(_DATASET_ID, 1)]

        def cleared_first(*_args: object, **_kwargs: object) -> None:
            """The team's choice goes away between the listing and the claim."""
            del fakes.results.choices[workspace.id]

        monkeypatch.setattr(fakes.results, "apply_refresh", cleared_first)
        with _instructor(fakes) as instructor:
            body = instructor.post(_REFRESH_ALL, headers=_HEADER).json()

    assert [(team["outcome"], team["reason_code"]) for team in body["teams"]] == [
        ("skipped", "no_asking_choice")
    ]
    assert body["refreshed"] == 0
    assert fakes.team_view.overlays == {}


def test_refresh_all_is_answered_by_the_new_router() -> None:
    declared = {
        (method, route.path)
        for route in exercise_instructor_refresh.router.routes
        for method in getattr(route, "methods", ())
    }

    assert ("POST", _REFRESH_ALL) in declared
