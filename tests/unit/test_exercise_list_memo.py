"""Class-load memo for the ranked list (Ann #413, lane L4).

Every page load asks for the same list; it is ranked once and kept. The key
carries this team's overlay digest, so a team's list after a refresh (Harbor
after asking) is ranked again, never served stale, and one team never gets
another team's list.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Any

import pytest
from smartmatch_api.routers import exercise_matching

from tests.unit.test_exercise_matching_router import (  # noqa: F401 - pytest fixtures
    _DATASET_ID,
    _LIST,
    _PROFILES,
    _entered,
    _Fakes,
    client_marker,
    fakes,
)


def _count_rankings(monkeypatch: pytest.MonkeyPatch) -> list[int]:
    calls = [0]
    real = exercise_matching.exercise_ranked_list

    def counted(*args: Any, **kwargs: Any) -> Any:
        calls[0] += 1
        return real(*args, **kwargs)

    monkeypatch.setattr(exercise_matching, "exercise_ranked_list", counted)
    return calls


def test_the_same_list_is_ranked_once(fakes: _Fakes, monkeypatch: pytest.MonkeyPatch) -> None:  # noqa: F811
    calls = _count_rankings(monkeypatch)
    with _entered(fakes, 1) as team:
        first = team.get(_LIST).json()
        second = team.get(_LIST).json()
        team.get(_LIST, params={"same_major": 3})
    assert first == second
    assert calls[0] == 2  # default once, the moved slider once


def test_a_refresh_ranks_again_and_shows_the_new_overlay(
    fakes: _Fakes,  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Fable's risk: Harbor after asking must not be served the pre-refresh list."""
    calls = _count_rankings(monkeypatch)
    with _entered(fakes, 4) as team_four:
        base = _PROFILES[1]
        before = client_marker(team_four, base.profile_no)
        workspace = fakes.workspaces.rows[(_DATASET_ID, 4)]
        fakes.team_view.overlays[(workspace.id, base.profile_no)] = replace(
            base,
            overlay_card_interests=("analytics", "brand"),
            overlay_card_career_goal="analytics",
        )
        after = client_marker(team_four, base.profile_no)
    assert (before, after) == ("major_plus_events", "completed_card")
    assert calls[0] == 2


def test_one_teams_kept_list_is_never_another_teams(
    fakes: _Fakes,  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = _count_rankings(monkeypatch)
    with _entered(fakes, 4) as team_four, _entered(fakes, 5) as team_five:
        base = _PROFILES[1]
        workspace = fakes.workspaces.rows[(_DATASET_ID, 4)]
        fakes.team_view.overlays[(workspace.id, base.profile_no)] = replace(
            base,
            overlay_card_interests=("analytics", "brand"),
            overlay_card_career_goal="analytics",
        )
        four = client_marker(team_four, base.profile_no)
        five = client_marker(team_five, base.profile_no)
        assert client_marker(team_five, base.profile_no) == five
    assert (four, five) == ("completed_card", "major_plus_events")
    assert calls[0] == 2  # one per team; team five's re-read was kept


def test_a_refresh_landing_mid_build_is_not_kept_under_the_old_digest(
    fakes: _Fakes,  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Review H1: digest read, refresh commits, profiles read; a reset must not get that list."""
    base = _PROFILES[1]
    with _entered(fakes, 4) as team_four:
        workspace = fakes.workspaces.rows[(_DATASET_ID, 4)]
        carded = replace(
            base,
            overlay_card_interests=("analytics", "brand"),
            overlay_card_career_goal="analytics",
        )
        real_read = fakes.team_view.list_team_profiles

        def refresh_lands_now(*args: Any, **kwargs: Any) -> Any:
            fakes.team_view.overlays[(workspace.id, base.profile_no)] = carded
            return real_read(*args, **kwargs)

        monkeypatch.setattr(fakes.team_view, "list_team_profiles", refresh_lands_now)
        assert client_marker(team_four, base.profile_no) == "completed_card"
        monkeypatch.setattr(fakes.team_view, "list_team_profiles", real_read)
        del fakes.team_view.overlays[(workspace.id, base.profile_no)]  # instructor reset
        assert client_marker(team_four, base.profile_no) == "major_plus_events"
