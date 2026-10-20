"""What one refresh changed, as the facts a screen builds its summary from.

Oct-2 checklist §6: the summary's "12 of the 22 invited people with no card",
and the "how much we know" counts "for all 300 … before and after". Both are
derived from one team's view — nothing is stored for them — so the same numbers
come back from the press and from every later reload.

Uses the rows from ``exercise_results_router/support.py``: twelve profiles, two
with a card, three with past events only, and one the file records no major for.
"""

from __future__ import annotations

from dataclasses import replace

from smartmatch_api.routers.exercise_results_refresh import (
    marker_counts,
    profiles_without_a_card,
    refresh_report,
)

from tests.unit.exercise_results_router.support import _PROFILES


def test_before_counts_follow_the_upload_reports_rule_over_every_row() -> None:
    """Every row is counted, including the one no list can rank."""
    counts = marker_counts(_PROFILES, with_overlay=False)

    assert counts == {"major_only": 7, "major_plus_events": 3, "completed_card": 2}
    assert sum(counts.values()) == len(_PROFILES)


def test_the_three_groups_are_always_named_even_when_empty() -> None:
    assert marker_counts((), with_overlay=True) == {
        "major_only": 0,
        "major_plus_events": 0,
        "completed_card": 0,
    }


def test_a_view_nobody_refreshed_reads_the_same_before_and_after() -> None:
    report = refresh_report(_PROFILES)

    assert report.marker_counts_before == report.marker_counts_after
    assert (report.counts.cards_completed, report.counts.non_responding) == (0, 0)


def test_a_new_card_moves_one_profile_into_completed_card() -> None:
    given = replace(_PROFILES[3], overlay_card_interests=("brand",))
    view = (*_PROFILES[:3], given, *_PROFILES[4:])

    report = refresh_report(view)

    assert report.marker_counts_before == {
        "major_only": 7,
        "major_plus_events": 3,
        "completed_card": 2,
    }
    assert report.marker_counts_after == {
        "major_only": 6,
        "major_plus_events": 3,
        "completed_card": 3,
    }


def test_an_empty_new_card_is_still_a_card() -> None:
    given = replace(_PROFILES[3], overlay_card_interests=())
    view = (*_PROFILES[:3], given, *_PROFILES[4:])

    assert marker_counts(view, with_overlay=True)["completed_card"] == 3


def test_added_topics_move_a_major_only_profile_to_major_plus_events() -> None:
    gained = replace(_PROFILES[6], overlay_added_event_topics=("analytics",))
    view = (*_PROFILES[:6], gained, *_PROFILES[7:])

    report = refresh_report(view)

    assert report.marker_counts_after["major_plus_events"] == 4
    assert report.marker_counts_after["major_only"] == 6
    assert report.counts.topics_added == 1


def test_stopped_responding_moves_no_marker() -> None:
    """It marks who answers, not how much is on file."""
    silent = replace(_PROFILES[7], non_responding=True)
    view = (*_PROFILES[:7], silent, *_PROFILES[8:])

    report = refresh_report(view)

    assert report.marker_counts_before == report.marker_counts_after
    assert report.counts.non_responding == 1


def test_the_asked_group_is_every_profile_without_a_card_invited_or_not() -> None:
    report = refresh_report(_PROFILES)

    assert report.asked_without_card == 10
    assert report.asked_without_card == len(profiles_without_a_card(_PROFILES))


def test_the_asked_count_does_not_shrink_once_new_cards_land() -> None:
    """Read from the base row, so a reload after the refresh says the same number."""
    given = replace(_PROFILES[3], overlay_card_interests=("brand",))
    view = (*_PROFILES[:3], given, *_PROFILES[4:])

    report = refresh_report(view)

    assert report.asked_without_card == 10
    assert report.counts.cards_completed == 1


def test_anns_300_file_asks_230_students_without_a_card() -> None:
    """Ann, 2026-10-18: the ask goes to all 230 without a card, not only invitees."""
    from smartmatch_persistence.exercise.team_view_repository import TeamProfileRow

    from tests.unit.exercise_workbooks import ann_full_parsed

    rows = tuple(
        TeamProfileRow(
            profile_no=p.profile_no,
            display_name=p.display_name,
            major=p.major,
            class_year=p.class_year,
            past_event_keys=p.past_event_keys,
            stated_interests=p.stated_interests,
            career_goal=p.career_goal,
            overlay_added_event_topics=(),
            overlay_card_interests=None,
            overlay_card_career_goal=None,
            non_responding=False,
            tiebreak_order=p.tiebreak_order,
        )
        for p in ann_full_parsed().profiles
    )

    assert len(rows) == 300
    assert refresh_report(rows).asked_without_card == 230
