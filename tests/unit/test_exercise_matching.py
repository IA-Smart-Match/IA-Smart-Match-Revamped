"""The exercise composition, tie-break, cap and public list (design spec §4.3–§4.6).

The load-bearing claim here is the one a plausible implementation gets wrong:
**an unknown factor contributes nothing and its weight is not re-spread**
(ADR-0016). A profile with only a major on file must get exactly the major
factor's contribution — not that contribution scaled up to fill the other
three factors' share, which would let a profile nobody knows anything about
outrank one whose card genuinely matches.
"""

from __future__ import annotations

import ast
import pathlib
from types import ModuleType

import pytest
from smartmatch_domain.exercise.markers import InformationMarker
from smartmatch_domain.exercise.matching import (
    EXERCISE_STAGE_B_FORMULA_VERSION,
    ExerciseProfile,
    exercise_ranked_list,
    rank_profiles_for_event,
    score_exercise_pair,
    unlisted_class_years,
)
from smartmatch_domain.exercise.registry import (
    EXERCISE_REGISTRY_VERSION,
    EXERCISE_SCORING_MODE,
    SAME_MAJOR_DEFAULT_WEIGHT,
)
from smartmatch_domain.student_factors import ProfileCard, ProfileEvidence
from smartmatch_domain.student_factors.evidence import EventEvidence

EVENT = EventEvidence(
    event_key="northline",
    topic_tags=("analytics", "careers"),
    target_majors=("Marketing",),
)

# Test-only. The ranker takes the caller's mapping; production passes
# ``vocabulary.EXERCISE_CLASS_YEAR_RANK``. A smaller one keeps these tests about
# the ranker rather than about Ann's four years.
TEST_ONLY_YEAR_RANK = {"Senior": 3, "Junior": 2, "Sophomore": 1}

CHECKSUM = "sha256:testonly0001"


def _major_only(profile_id: str, major: str = "Marketing") -> ProfileEvidence:
    return ProfileEvidence(profile_id, major)


def _full_card(profile_id: str) -> ProfileEvidence:
    return ProfileEvidence(
        profile_id,
        "Marketing",
        card=ProfileCard(("analytics", "careers"), career_goal="analytics"),
        attended_event_topics=(("analytics", "careers"),),
    )


# ---------------------------------------------------------------------------
# The composition
# ---------------------------------------------------------------------------


def test_a_major_only_profile_gets_exactly_the_major_contribution() -> None:
    score = score_exercise_pair(_major_only("p1"), EVENT)
    assert score.value == pytest.approx(SAME_MAJOR_DEFAULT_WEIGHT, abs=1e-9)
    assert score.unknown_factor_keys == (
        "stated_interest_overlap",
        "career_goal_fit",
        "past_event_topic_overlap",
    )


def test_the_unknown_factors_weight_is_not_re_spread() -> None:
    """The ADR-0016 rule, stated as the inequality it protects."""
    nothing_known = score_exercise_pair(_major_only("p1"), EVENT)
    everything_known = score_exercise_pair(_full_card("p2"), EVENT)
    assert nothing_known.value is not None
    assert everything_known.value is not None
    assert nothing_known.value < everything_known.value
    # If the missing three weights had been re-spread, the major-only profile
    # would have composed to a perfect 1.0 and tied the fully evidenced one.
    assert nothing_known.value != pytest.approx(1.0)
    assert everything_known.value == pytest.approx(1.0, abs=1e-9)


def test_an_unknown_factor_is_listed_and_never_coerced_to_zero() -> None:
    score = score_exercise_pair(_major_only("p1"), EVENT)
    by_key = {factor.factor_key: factor for factor in score.factor_scores}
    assert by_key["career_goal_fit"].value is None
    assert by_key["same_major"].value == 1.0


def test_an_empty_card_scores_where_no_card_is_unknown() -> None:
    empty = ProfileEvidence("p1", "Marketing", card=ProfileCard())
    score = score_exercise_pair(empty, EVENT)
    assert score.unknown_factor_keys == ("past_event_topic_overlap",)
    assert score.value == pytest.approx(SAME_MAJOR_DEFAULT_WEIGHT, abs=1e-9)


def test_the_score_is_pinned_to_the_exercise_rulebook_and_mode() -> None:
    score = score_exercise_pair(_major_only("p1"), EVENT)
    assert score.registry_version == EXERCISE_REGISTRY_VERSION
    assert score.scoring_mode == EXERCISE_SCORING_MODE
    assert score.formula_version == EXERCISE_STAGE_B_FORMULA_VERSION
    assert score.subject_id == "p1"


def test_team_weights_change_the_composition() -> None:
    heavy_major = score_exercise_pair(_major_only("p1"), EVENT, weights={"same_major": 4.0})
    assert heavy_major.value is not None
    assert heavy_major.value > SAME_MAJOR_DEFAULT_WEIGHT


# ---------------------------------------------------------------------------
# The tie-break, branch by branch
# ---------------------------------------------------------------------------


def _ranked_ids(profiles: list[ExerciseProfile], *, limit: int = 10) -> list[str]:
    return [
        score.subject_id
        for score in rank_profiles_for_event(
            EVENT,
            profiles,
            invite_limit=limit,
            year_rank=TEST_ONLY_YEAR_RANK,
            dataset_checksum=CHECKSUM,
        )
    ]


def test_a_higher_composite_outranks_a_lower_one() -> None:
    profiles = [
        ExerciseProfile(1, "Junior", _major_only("low", major="History")),
        ExerciseProfile(2, "Junior", _full_card("high")),
    ]
    assert _ranked_ids(profiles) == ["high", "low"]


def test_more_information_on_file_breaks_a_tie_on_value() -> None:
    """Both compose to the major weight alone; the marker separates them."""
    thin = ProfileEvidence("thin", "Marketing")
    thick = ProfileEvidence("thick", "Marketing", attended_event_topics=(("sports",),))
    profiles = [ExerciseProfile(1, "Junior", thin), ExerciseProfile(2, "Junior", thick)]
    assert _ranked_ids(profiles) == ["thick", "thin"]


def test_the_year_breaks_a_tie_on_value_and_information() -> None:
    profiles = [
        ExerciseProfile(1, "Sophomore", _major_only("younger")),
        ExerciseProfile(2, "Senior", _major_only("older")),
    ]
    assert _ranked_ids(profiles) == ["older", "younger"]


def test_the_fixed_order_breaks_a_tie_on_everything_else() -> None:
    profiles = [
        ExerciseProfile(number, "Senior", _major_only(f"p{number}")) for number in range(1, 6)
    ]
    order = _ranked_ids(profiles)
    assert sorted(order) == sorted(f"p{number}" for number in range(1, 6))
    # Not input order, and not profile-number order: a real shuffle.
    assert order == _ranked_ids(list(reversed(profiles)))


def test_an_unlisted_class_year_ranks_last_and_is_reported() -> None:
    profiles = [
        ExerciseProfile(1, "Visitor", _major_only("unlisted")),
        ExerciseProfile(2, "Sophomore", _major_only("lowest_listed")),
    ]
    assert _ranked_ids(profiles) == ["lowest_listed", "unlisted"]
    assert unlisted_class_years(profiles, TEST_ONLY_YEAR_RANK) == ("Visitor",)
    listing = exercise_ranked_list(
        EVENT,
        profiles,
        invite_limit=10,
        year_rank=TEST_ONLY_YEAR_RANK,
        dataset_checksum=CHECKSUM,
    )
    assert listing.unlisted_class_years == ("Visitor",)


def test_an_unlisted_year_still_ranks_last_when_the_listed_ranks_are_negative() -> None:
    profiles = [
        ExerciseProfile(1, "Visitor", _major_only("unlisted")),
        ExerciseProfile(2, "Sophomore", _major_only("listed")),
    ]
    ranked = rank_profiles_for_event(
        EVENT,
        profiles,
        invite_limit=10,
        year_rank={"Sophomore": -5},
        dataset_checksum=CHECKSUM,
    )
    assert [score.subject_id for score in ranked] == ["listed", "unlisted"]


# ---------------------------------------------------------------------------
# The cap, and refusals
# ---------------------------------------------------------------------------


def test_the_list_is_cut_at_the_invite_limit() -> None:
    profiles = [
        ExerciseProfile(number, "Senior", _major_only(f"p{number}")) for number in range(1, 40)
    ]
    assert len(_ranked_ids(profiles, limit=30)) == 30


def test_a_non_positive_invite_limit_is_refused() -> None:
    with pytest.raises(ValueError, match="invite_limit"):
        rank_profiles_for_event(
            EVENT,
            [],
            invite_limit=0,
            year_rank=TEST_ONLY_YEAR_RANK,
            dataset_checksum=CHECKSUM,
        )


def test_a_blank_dataset_checksum_is_refused() -> None:
    with pytest.raises(ValueError, match="dataset_checksum"):
        rank_profiles_for_event(
            EVENT,
            [ExerciseProfile(1, "Senior", _major_only("p1"))],
            invite_limit=30,
            year_rank=TEST_ONLY_YEAR_RANK,
            dataset_checksum="  ",
        )


def test_a_duplicate_profile_number_is_refused() -> None:
    profiles = [
        ExerciseProfile(1, "Senior", _major_only("a")),
        ExerciseProfile(1, "Senior", _major_only("b")),
    ]
    with pytest.raises(ValueError, match="profile_no"):
        _ranked_ids(profiles)


# ---------------------------------------------------------------------------
# The list a screen renders
# ---------------------------------------------------------------------------


def test_the_list_carries_rank_reason_marker_and_contributing_keys() -> None:
    profiles = [
        ExerciseProfile(1, "Senior", _full_card("rich")),
        ExerciseProfile(2, "Junior", _major_only("thin")),
    ]
    listing = exercise_ranked_list(
        EVENT,
        profiles,
        invite_limit=30,
        year_rank=TEST_ONLY_YEAR_RANK,
        dataset_checksum=CHECKSUM,
    )
    first, second = listing.entries
    assert (first.rank, first.profile_id) == (1, "rich")
    assert first.marker is InformationMarker.COMPLETED_CARD
    assert first.contributing_factor_keys == (
        "same_major",
        "stated_interest_overlap",
        "career_goal_fit",
        "past_event_topic_overlap",
    )
    assert (second.rank, second.profile_id) == (2, "thin")
    assert second.reason == "Same major; nothing else on file."


def test_a_measured_zero_factor_is_not_named_as_contributing() -> None:
    missed = ProfileEvidence(
        "missed", "Marketing", card=ProfileCard(("sports",), career_goal="law")
    )
    listing = exercise_ranked_list(
        EVENT,
        [ExerciseProfile(1, "Senior", missed)],
        invite_limit=30,
        year_rank=TEST_ONLY_YEAR_RANK,
        dataset_checksum=CHECKSUM,
    )
    assert listing.entries[0].contributing_factor_keys == ("same_major",)


def _reasons(profiles: list[ExerciseProfile]) -> list[str]:
    listing = exercise_ranked_list(
        EVENT,
        profiles,
        invite_limit=30,
        year_rank=TEST_ONLY_YEAR_RANK,
        dataset_checksum=CHECKSUM,
    )
    return [entry.reason for entry in listing.entries]


def test_a_year_resolved_tie_on_major_alone_gets_anns_sentence_on_the_list() -> None:
    profiles = [
        ExerciseProfile(1, "Sophomore", _major_only("younger")),
        ExerciseProfile(2, "Senior", _major_only("older")),
    ]
    assert _reasons(profiles) == [
        "Tied on major; ordered by year.",
        "Tied on major; ordered by year.",
    ]


def test_two_zero_scoring_names_are_never_told_they_share_a_major() -> None:
    """MEDIUM 1, end to end: neither profile's major is a target major."""
    profiles = [
        ExerciseProfile(1, "Sophomore", _major_only("younger", major="History")),
        ExerciseProfile(2, "Senior", _major_only("older", major="Physics")),
    ]
    assert _reasons(profiles) == [
        "Tied on what counted; ordered by year.",
        "Tied on what counted; ordered by year.",
    ]


def test_two_identical_full_cards_are_not_told_they_tied_on_major() -> None:
    """They tied on all four factors; the major is not what separated them."""
    profiles = [
        ExerciseProfile(1, "Sophomore", _full_card("younger")),
        ExerciseProfile(2, "Senior", _full_card("older")),
    ]
    assert _reasons(profiles) == [
        "Tied on what counted; ordered by year.",
        "Tied on what counted; ordered by year.",
    ]


def test_an_information_resolved_tie_names_the_information_key() -> None:
    thin = ProfileEvidence("thin", "Marketing")
    thick = ProfileEvidence("thick", "Marketing", attended_event_topics=(("sports",),))
    profiles = [ExerciseProfile(1, "Senior", thin), ExerciseProfile(2, "Senior", thick)]
    assert _reasons(profiles) == [
        "Tied; more information on file first.",
        "Tied; more information on file first.",
    ]


def test_a_permutation_resolved_tie_names_the_fixed_order() -> None:
    profiles = [
        ExerciseProfile(number, "Senior", _major_only(f"p{number}")) for number in range(1, 4)
    ]
    assert _reasons(profiles) == ["Tied; placed in a fixed order that never changes."] * 3


def test_no_reason_on_any_list_claims_a_major_tie_that_was_not_one() -> None:
    """One sweep over mixed evidence: the sentence never overstates the tie."""
    profiles = [
        ExerciseProfile(1, "Senior", _major_only("major_only")),
        ExerciseProfile(2, "Junior", _major_only("wrong_major", major="History")),
        ExerciseProfile(3, "Senior", _full_card("full")),
        ExerciseProfile(
            4,
            "Junior",
            ProfileEvidence("partial", "Marketing", card=ProfileCard(("analytics",))),
        ),
    ]
    listing = exercise_ranked_list(
        EVENT,
        profiles,
        invite_limit=30,
        year_rank=TEST_ONLY_YEAR_RANK,
        dataset_checksum=CHECKSUM,
    )
    for entry in listing.entries:
        if "Tied on major" in entry.reason:
            assert entry.contributing_factor_keys == ("same_major",)


def test_the_tie_break_reason_is_read_from_the_whole_set_not_the_cut() -> None:
    """The last name on the list says what it would have said one place down."""
    profiles = [
        ExerciseProfile(number, "Senior", _major_only(f"p{number}")) for number in range(1, 6)
    ]
    cut = exercise_ranked_list(
        EVENT,
        profiles,
        invite_limit=2,
        year_rank=TEST_ONLY_YEAR_RANK,
        dataset_checksum=CHECKSUM,
    )
    whole = exercise_ranked_list(
        EVENT,
        profiles,
        invite_limit=5,
        year_rank=TEST_ONLY_YEAR_RANK,
        dataset_checksum=CHECKSUM,
    )
    assert [entry.reason for entry in cut.entries] == [entry.reason for entry in whole.entries[:2]]


def _imported_names(module: ModuleType) -> set[tuple[str, str]]:
    """Every ``(module, name)`` pair one module imports, read from its source."""
    tree = ast.parse(pathlib.Path(module.__file__ or "").read_text())
    pairs: set[tuple[str, str]] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module is not None:
            pairs.update((node.module, alias.name) for alias in node.names)
        elif isinstance(node, ast.Import):
            pairs.update(("", alias.name) for alias in node.names)
    return pairs


def test_neither_ranker_imports_the_other() -> None:
    """ADR-0025 D5, read from the source rather than from attribute presence.

    ``scoring._ranked`` is the ratified CBA tie-break and is untouched. This
    module is allowed exactly one thing from :mod:`smartmatch_domain.scoring` —
    the ``StageBScore`` shape its results take (ADR-0025 D4) — and the CBA
    scorer is allowed nothing at all from the exercise package.
    """
    import smartmatch_domain.exercise.matching as matching_module
    import smartmatch_domain.scoring as scoring_module

    from_scoring = {
        name for module, name in _imported_names(matching_module) if module.endswith("scoring")
    }
    assert from_scoring == {"StageBScore"}

    exercise_imports = {
        (module, name)
        for module, name in _imported_names(scoring_module)
        if "exercise" in module or "exercise" in name
    }
    assert exercise_imports == set()


# ---------------------------------------------------------------------------
# Ann's tiebreak_order (owner ruling 3, 2026-09-24)
# ---------------------------------------------------------------------------


def _tied(orders: list[int | None]) -> list[ExerciseProfile]:
    return [
        ExerciseProfile(number, "Senior", _major_only(f"p{number}"), tiebreak_order=order)
        for number, order in enumerate(orders, start=1)
    ]


def test_anns_tiebreak_order_settles_the_last_tie() -> None:
    assert _ranked_ids(_tied([3, 1, 2])) == ["p2", "p3", "p1"]
    assert _reasons(_tied([3, 1, 2]))[0] == "Tied; placed in a fixed order that never changes."


def test_the_tiebreak_order_does_not_depend_on_the_checksum() -> None:
    profiles = _tied([5, 4, 3, 2, 1])
    other = [
        score.subject_id
        for score in rank_profiles_for_event(
            EVENT,
            profiles,
            invite_limit=10,
            year_rank=TEST_ONLY_YEAR_RANK,
            dataset_checksum="sha256:another-upload",
        )
    ]
    assert other == _ranked_ids(profiles) == ["p5", "p4", "p3", "p2", "p1"]


def test_the_tiebreak_order_is_the_last_key_not_the_first() -> None:
    profiles = [
        ExerciseProfile(1, "Junior", _major_only("junior-first-in-order"), tiebreak_order=1),
        ExerciseProfile(2, "Senior", _major_only("senior"), tiebreak_order=2),
    ]
    assert _ranked_ids(profiles) == ["senior", "junior-first-in-order"]


def test_a_dataset_without_tiebreak_order_keeps_the_checksum_order() -> None:
    from smartmatch_domain.exercise.determinism import exercise_permutation

    permutation = exercise_permutation(CHECKSUM, range(1, 6))
    expected = [f"p{number}" for number in sorted(range(1, 6), key=permutation.__getitem__)]
    assert _ranked_ids(_tied([None] * 5)) == expected


def test_a_tiebreak_order_on_only_some_profiles_is_refused() -> None:
    with pytest.raises(ValueError, match="some profiles carry one"):
        _ranked_ids(_tied([1, None, 2]))


def test_a_shared_tiebreak_order_is_refused() -> None:
    with pytest.raises(ValueError, match="share one place"):
        _ranked_ids(_tied([1, 1, 2]))


def test_a_non_positive_tiebreak_order_is_refused() -> None:
    with pytest.raises(ValueError, match="tiebreak_order"):
        ExerciseProfile(1, "Senior", _major_only("p1"), tiebreak_order=0)


def test_anns_year_order_wakes_the_year_sentence() -> None:
    """Owner ruling 4: seniors first, and the dormant year rung speaks."""
    from smartmatch_domain.exercise.vocabulary import EXERCISE_CLASS_YEAR_RANK

    profiles = [
        ExerciseProfile(1, "Freshman", _major_only("freshman"), tiebreak_order=1),
        ExerciseProfile(2, "Senior", _major_only("senior"), tiebreak_order=2),
        ExerciseProfile(3, "Junior", _major_only("junior"), tiebreak_order=3),
        ExerciseProfile(4, "Sophomore", _major_only("sophomore"), tiebreak_order=4),
    ]
    listing = exercise_ranked_list(
        EVENT,
        profiles,
        invite_limit=30,
        year_rank=EXERCISE_CLASS_YEAR_RANK,
        dataset_checksum=CHECKSUM,
    )
    assert [entry.profile_id for entry in listing.entries] == [
        "senior",
        "junior",
        "sophomore",
        "freshman",
    ]
    assert {entry.reason for entry in listing.entries} == {"Tied on major; ordered by year."}
    assert listing.unlisted_class_years == ()
