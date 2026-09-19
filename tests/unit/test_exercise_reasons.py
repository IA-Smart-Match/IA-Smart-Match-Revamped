"""One sentence per name, in Ann's words (requirements; design spec §4.5).

The two things that can silently decay here: Ann's exact wording, and the
one-sentence contract. Both are asserted, and so is the join between them —
the rendered line is her phrase capitalised and full-stopped and nothing else,
so a reword of either half fails.
"""

from __future__ import annotations

import pytest
from smartmatch_domain.exercise.markers import InformationMarker
from smartmatch_domain.exercise.reasons import (
    ANN_MAJOR_ONLY_PHRASE,
    ANN_TIED_ON_YEAR_PHRASE,
    TieBreakKey,
    exercise_reason,
    phrase_as_sentence,
)
from smartmatch_domain.one_sentence import OneSentenceRationaleError, assert_one_sentence

ALL_MARKERS = tuple(InformationMarker)
ALL_TIE_KEYS = tuple(TieBreakKey)


def test_anns_two_phrases_are_kept_verbatim() -> None:
    assert ANN_MAJOR_ONLY_PHRASE == "same major; nothing else on file"
    assert ANN_TIED_ON_YEAR_PHRASE == "tied on major; ordered by year"


def test_a_rendered_line_is_the_phrase_capitalised_and_full_stopped() -> None:
    """The only liberty taken with her wording, and it is mechanical."""
    for phrase in (ANN_MAJOR_ONLY_PHRASE, ANN_TIED_ON_YEAR_PHRASE):
        sentence = phrase_as_sentence(phrase)
        assert sentence == f"{phrase[0].upper()}{phrase[1:]}."
        assert sentence.lower().rstrip(".") == phrase.lower()


def test_anns_phrases_as_written_would_not_pass_the_sentence_rule() -> None:
    """Why the rendering exists at all, rather than as an unexplained habit."""
    with pytest.raises(OneSentenceRationaleError):
        assert_one_sentence(ANN_MAJOR_ONLY_PHRASE, field="reason")


def test_a_major_only_profile_gets_anns_sentence() -> None:
    reason = exercise_reason(marker=InformationMarker.MAJOR_ONLY, contributing_keys=())
    assert reason == "Same major; nothing else on file."


def test_a_major_only_profile_whose_major_misses_still_gets_anns_sentence() -> None:
    """ "For everyone else the reason line says so" is about what is on file."""
    reason = exercise_reason(marker=InformationMarker.MAJOR_ONLY, contributing_keys=())
    assert reason == "Same major; nothing else on file."


def test_the_year_tie_break_gets_anns_other_sentence() -> None:
    reason = exercise_reason(
        marker=InformationMarker.COMPLETED_CARD,
        contributing_keys=("same_major",),
        tie_break_key=TieBreakKey.YEAR,
    )
    assert reason == "Tied on major; ordered by year."


def test_the_year_sentence_wins_over_the_major_only_sentence() -> None:
    reason = exercise_reason(
        marker=InformationMarker.MAJOR_ONLY,
        contributing_keys=(),
        tie_break_key=TieBreakKey.YEAR,
    )
    assert reason == "Tied on major; ordered by year."


def test_the_other_two_tie_break_keys_read_as_the_same_family() -> None:
    information = exercise_reason(
        marker=InformationMarker.COMPLETED_CARD,
        contributing_keys=("same_major",),
        tie_break_key=TieBreakKey.INFORMATION,
    )
    fixed = exercise_reason(
        marker=InformationMarker.COMPLETED_CARD,
        contributing_keys=("same_major",),
        tie_break_key=TieBreakKey.FIXED_ORDER,
    )
    assert information == "Tied on major; ordered by how much is on file."
    assert fixed == "Tied on major; ordered by the fixed order."


def test_contributing_factors_are_named_in_anns_words() -> None:
    one = exercise_reason(
        marker=InformationMarker.MAJOR_PLUS_EVENTS,
        contributing_keys=("past_event_topic_overlap",),
    )
    two = exercise_reason(
        marker=InformationMarker.COMPLETED_CARD,
        contributing_keys=("same_major", "stated_interest_overlap"),
    )
    three = exercise_reason(
        marker=InformationMarker.COMPLETED_CARD,
        contributing_keys=("same_major", "stated_interest_overlap", "career_goal_fit"),
    )
    assert one == "What counted: went to similar events before."
    assert two == "What counted: same major and said they are interested in this topic."
    assert three == (
        "What counted: same major, said they are interested in this topic, and "
        "career goal fits this event."
    )


def test_a_profile_with_information_and_no_contribution_is_said_plainly() -> None:
    reason = exercise_reason(
        marker=InformationMarker.COMPLETED_CARD,
        contributing_keys=(),
    )
    assert reason == "Nothing on file matches this event."


@pytest.mark.parametrize("marker", ALL_MARKERS)
@pytest.mark.parametrize("tie_break_key", ALL_TIE_KEYS)
def test_every_branch_produces_exactly_one_sentence_with_no_number(
    marker: InformationMarker, tie_break_key: TieBreakKey
) -> None:
    for keys in ((), ("same_major",), ("same_major", "career_goal_fit")):
        reason = exercise_reason(marker=marker, contributing_keys=keys, tie_break_key=tie_break_key)
        assert_one_sentence(reason, field="reason")
        assert not any(character.isdigit() for character in reason)
        assert "%" not in reason
