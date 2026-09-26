"""One sentence per name, in Ann's words (requirements; design spec §4.5).

Three things that can silently decay here: Ann's exact wording, the
one-sentence contract, and — the one a review caught — whether the sentence is
**true**. "Tied on major" must not be printed beside two names that share no
major at all, so every tie sentence below is asserted against the tie it
actually describes.
"""

from __future__ import annotations

import pytest
from smartmatch_domain.exercise.markers import InformationMarker
from smartmatch_domain.exercise.reasons import (
    ANN_MAJOR_ONLY_PHRASE,
    ANN_TIED_ON_YEAR_PHRASE,
    TIE_LINE_WINS_OVER_MAJOR_ONLY_LINE,
    TieBreakKey,
    exercise_reason,
    phrase_as_sentence,
)
from smartmatch_domain.one_sentence import OneSentenceRationaleError, assert_one_sentence

ALL_MARKERS = tuple(InformationMarker)
ALL_TIE_KEYS = tuple(TieBreakKey)

#: The four evidence shapes a tie sentence has to stay true for.
CONTRIBUTION_SHAPES = {
    "major only": ("same_major",),
    "zero score": (),
    "partial": ("same_major", "stated_interest_overlap"),
    "full card": (
        "same_major",
        "stated_interest_overlap",
        "career_goal_fit",
        "past_event_topic_overlap",
    ),
}


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


# ---------------------------------------------------------------------------
# The major-only line
# ---------------------------------------------------------------------------


def test_a_major_only_profile_gets_anns_sentence() -> None:
    reason = exercise_reason(marker=InformationMarker.MAJOR_ONLY, contributing_keys=())
    assert reason == "Same major; nothing else on file."


def test_a_major_only_profile_whose_major_misses_still_gets_anns_sentence() -> None:
    """What is on file, not whether it matched — the trigger is the marker."""
    reason = exercise_reason(marker=InformationMarker.MAJOR_ONLY, contributing_keys=())
    assert reason == "Same major; nothing else on file."


# ---------------------------------------------------------------------------
# The year tie: Ann's line only when the tie really is on major
# ---------------------------------------------------------------------------


def test_a_year_tie_genuinely_on_major_gets_anns_sentence() -> None:
    reason = exercise_reason(
        marker=InformationMarker.MAJOR_ONLY,
        contributing_keys=("same_major",),
        tie_break_key=TieBreakKey.YEAR,
        tied_on_major=True,
    )
    assert reason == "Tied on major; ordered by year."


@pytest.mark.parametrize(
    "contributing_keys",
    [CONTRIBUTION_SHAPES["zero score"], CONTRIBUTION_SHAPES["full card"]],
    ids=["two zero scores share no major", "two identical full cards"],
)
def test_a_year_tie_that_is_not_on_major_never_claims_it_is(
    contributing_keys: tuple[str, ...],
) -> None:
    """The review's MEDIUM 1: the sentence must describe the tie it names."""
    reason = exercise_reason(
        marker=InformationMarker.COMPLETED_CARD,
        contributing_keys=contributing_keys,
        tie_break_key=TieBreakKey.YEAR,
        tied_on_major=False,
    )
    assert reason == "Tied on what counted; ordered by year."
    assert "on major" not in reason


def test_a_zero_scoring_pair_is_never_told_they_share_a_major() -> None:
    reason = exercise_reason(
        marker=InformationMarker.MAJOR_ONLY,
        contributing_keys=(),
        tie_break_key=TieBreakKey.YEAR,
        tied_on_major=False,
    )
    assert reason == "Tied on what counted; ordered by year."


# ---------------------------------------------------------------------------
# The other two tie keys describe the key that actually decided
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("tied_on_major", [True, False])
def test_an_information_tie_says_information_decided(tied_on_major: bool) -> None:
    reason = exercise_reason(
        marker=InformationMarker.COMPLETED_CARD,
        contributing_keys=("same_major",),
        tie_break_key=TieBreakKey.INFORMATION,
        tied_on_major=tied_on_major,
    )
    assert reason == "Tied; more information on file first."


@pytest.mark.parametrize("tied_on_major", [True, False])
def test_a_fixed_order_tie_says_the_fixed_order_decided(tied_on_major: bool) -> None:
    reason = exercise_reason(
        marker=InformationMarker.COMPLETED_CARD,
        contributing_keys=("same_major",),
        tie_break_key=TieBreakKey.FIXED_ORDER,
        tied_on_major=tied_on_major,
    )
    assert reason == "Tied; placed in a fixed order that never changes."


# ---------------------------------------------------------------------------
# Precedence, as one flag
# ---------------------------------------------------------------------------


def test_the_tie_line_wins_over_the_major_only_line_and_says_so_in_one_place() -> None:
    """A question for Ann; flipping it is a one-line change to the flag."""
    assert TIE_LINE_WINS_OVER_MAJOR_ONLY_LINE is True
    reason = exercise_reason(
        marker=InformationMarker.MAJOR_ONLY,
        contributing_keys=("same_major",),
        tie_break_key=TieBreakKey.YEAR,
        tied_on_major=True,
    )
    assert reason == "Tied on major; ordered by year."


# ---------------------------------------------------------------------------
# The contributing-factor line, and the catch-all
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Every branch, over every evidence shape
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("marker", ALL_MARKERS)
@pytest.mark.parametrize("tie_break_key", ALL_TIE_KEYS)
@pytest.mark.parametrize("shape", sorted(CONTRIBUTION_SHAPES), ids=sorted(CONTRIBUTION_SHAPES))
@pytest.mark.parametrize("tied_on_major", [True, False])
def test_every_branch_is_one_sentence_with_no_number(
    marker: InformationMarker,
    tie_break_key: TieBreakKey,
    shape: str,
    tied_on_major: bool,
) -> None:
    reason = exercise_reason(
        marker=marker,
        contributing_keys=CONTRIBUTION_SHAPES[shape],
        tie_break_key=tie_break_key,
        tied_on_major=tied_on_major,
    )
    assert_one_sentence(reason, field="reason")
    assert not any(character.isdigit() for character in reason)
    assert "%" not in reason


@pytest.mark.parametrize("marker", ALL_MARKERS)
@pytest.mark.parametrize("tie_break_key", ALL_TIE_KEYS)
@pytest.mark.parametrize("shape", sorted(CONTRIBUTION_SHAPES), ids=sorted(CONTRIBUTION_SHAPES))
def test_no_branch_claims_a_major_tie_that_was_not_one(
    marker: InformationMarker, tie_break_key: TieBreakKey, shape: str
) -> None:
    """The invariant behind MEDIUM 1, stated once over the whole matrix."""
    reason = exercise_reason(
        marker=marker,
        contributing_keys=CONTRIBUTION_SHAPES[shape],
        tie_break_key=tie_break_key,
        tied_on_major=False,
    )
    assert "Tied on major" not in reason


# ---------------------------------------------------------------------------
# OQ-CE-14: an undecided goal's half fit is not told that its goal "fits"
# ---------------------------------------------------------------------------


def test_an_undecided_half_fit_is_named_as_such_and_never_as_a_fit() -> None:
    reason = exercise_reason(
        marker=InformationMarker.COMPLETED_CARD,
        contributing_keys=("career_goal_fit", "past_event_topic_overlap"),
        undecided_goal=True,
    )
    assert reason == (
        "What counted: undecided goal suits a broad event and went to similar events before."
    )
    assert "fits" not in reason


def test_a_goal_that_fits_still_says_it_fits() -> None:
    reason = exercise_reason(
        marker=InformationMarker.COMPLETED_CARD, contributing_keys=("career_goal_fit",)
    )
    assert reason == "What counted: career goal fits this event."


def test_the_undecided_flag_changes_nothing_when_the_goal_did_not_count() -> None:
    reason = exercise_reason(
        marker=InformationMarker.COMPLETED_CARD,
        contributing_keys=("same_major",),
        undecided_goal=True,
    )
    assert reason == "What counted: same major."


# --- OQ-CE-12 closed 2026-09-25 ------------------------------------------------


def test_the_approved_wording_is_no_longer_marked_pending():
    """Ann's answers approved every line as written; a marker left would be untrue."""
    from pathlib import Path

    from smartmatch_domain.exercise import reasons

    source = Path(reasons.__file__).read_text(encoding="utf-8")
    assert "PLACEHOLDER" not in source
    assert "wording pending Ann" not in source
    assert "OQ-CE-12 closed" in source


@pytest.mark.parametrize(
    ("tie_break_key", "contributing", "tied_on_major", "expected"),
    [
        (
            TieBreakKey.YEAR,
            ("same_major", "stated_interest_overlap"),
            False,
            "Tied on what counted; ordered by year.",
        ),
        (
            TieBreakKey.INFORMATION,
            ("stated_interest_overlap",),
            False,
            "Tied; more information on file first.",
        ),
        (
            TieBreakKey.FIXED_ORDER,
            ("stated_interest_overlap",),
            False,
            "Tied; placed in a fixed order that never changes.",
        ),
    ],
)
def test_the_three_approved_tie_sentences_render_exactly(
    tie_break_key: TieBreakKey,
    contributing: tuple[str, ...],
    tied_on_major: bool,
    expected: str,
):
    assert (
        exercise_reason(
            marker=InformationMarker.COMPLETED_CARD,
            contributing_keys=contributing,
            tie_break_key=tie_break_key,
            tied_on_major=tied_on_major,
        )
        == expected
    )


def test_the_approved_renderings_of_anns_phrases():
    assert phrase_as_sentence(ANN_MAJOR_ONLY_PHRASE) == "Same major; nothing else on file."
    assert phrase_as_sentence(ANN_TIED_ON_YEAR_PHRASE) == "Tied on major; ordered by year."


def test_the_approved_single_factor_rendering():
    assert (
        exercise_reason(
            marker=InformationMarker.COMPLETED_CARD,
            contributing_keys=("same_major",),
        )
        == "What counted: same major."
    )


def test_the_tie_line_still_wins_over_the_major_only_line():
    """Approved as built: the tie line wins when both lines fit."""
    assert TIE_LINE_WINS_OVER_MAJOR_ONLY_LINE is True
