"""Golden cases on Ann's own data file (2026-09-24), through the production path.

Ann's file is parsed by the real ingest, projected into the same row types the
repositories return, turned into ranker input by the API's own
``rankable_set`` (career-goal table, class-year order, ``tiebreak_order``), and
ranked by the domain. Nothing here builds evidence by hand, so a regression in
any of those steps moves a pinned name.

Ann's test case (Ann's data file, 2026-09-24)
=============================================
    P004 is an Accounting major whose card names Technology / information
    systems as an interest. For the Northline event (E11), with "said they are
    interested" turned up, P004 should rank above a plain Accounting major;
    with that factor turned off, it should not.

The 20-row sample is refused on upload by design spec §3's 50-profile floor,
so the case runs on the full file restricted to the sample's 20 ids. The
sample's rows are the full file's rows with the same ids and values (Ann's
data file, 2026-09-24), which ``test_exercise_ingest`` asserts.

**The first half holds.** Turned up, P004 ranks above every plain Accounting
major, and "said they are interested" is one of the factors that counted.

**The second half does not hold as worded, and this file pins why rather than
coding around it.** Turned off, "said they are interested" no longer counts for
P004 — but P004 *still* ranks above the plain Accounting majors, for two
reasons that are rulings rather than bugs:

1. P004's card goal, "Data, analytics or IT role", fits Northline through the
   role→topic table (owner ruling 2 of 2026-09-24), so "career goal fits this
   event" still lifts it.
2. With that factor turned off as well, P004 and the plain majors tie on the
   composite, and design spec §4.4's tie-break puts **more information on file
   first** — P004 has a completed card, they do not.

So "should not rank above" is true of the *interest factor's contribution*,
which is what the test below pins, and not of the position. Reported to the
owner as a question for Ann on 2026-09-24.
"""

from __future__ import annotations

from collections.abc import Mapping

import pytest
from smartmatch_api.exercise_dependencies import ExerciseEventRow, TeamProfileRow
from smartmatch_api.routers.exercise_matching_models import event_evidence, rankable_set
from smartmatch_domain.exercise.ingest import ParsedDataset
from smartmatch_domain.exercise.matching import ExerciseList, exercise_ranked_list
from smartmatch_domain.exercise.reasons import phrase_as_sentence

from tests.unit.exercise_workbooks import ann_full_parsed

#: The 20 profile numbers of Ann's sample file.
SAMPLE_PROFILE_NOS = frozenset(
    {4, 38, 43, 57, 63, 85, 149, 168, 178, 220, 231, 234, 247, 256, 257, 264, 269, 284, 292, 295}
)

#: Accounting majors in the sample with no card and no past events.
PLAIN_ACCOUNTING_MAJORS = (231, 257)

_TURNED_UP = {
    "same_major": 0.25,
    "stated_interest_overlap": 1.0,
    "career_goal_fit": 0.25,
    "past_event_topic_overlap": 0.25,
}
_TURNED_OFF = {**_TURNED_UP, "stated_interest_overlap": 0.0}
_INTEREST_AND_GOAL_OFF = {**_TURNED_OFF, "career_goal_fit": 0.0}


def _dataset() -> ParsedDataset:
    """Ann's file, parsed once per session — the object ``ann_full_dataset`` serves."""
    return ann_full_parsed()


def _rows(profile_nos: frozenset[int] | None = None) -> tuple[TeamProfileRow, ...]:
    return tuple(
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
        for p in _dataset().profiles
        if profile_nos is None or p.profile_no in profile_nos
    )


def _events() -> tuple[ExerciseEventRow, ...]:
    return tuple(
        ExerciseEventRow(
            event_key=e.event_key,
            name=e.name,
            topic_tags=e.topic_tags,
            target_majors=e.target_majors,
            is_exercise_event=e.is_exercise_event,
            sequence=e.sequence,
        )
        for e in _dataset().events
    )


def _ranked(
    event_key: str,
    weights: Mapping[str, float] | None,
    *,
    profile_nos: frozenset[int] | None = None,
    invite_limit: int = 30,
) -> ExerciseList:
    events = _events()
    rankable = rankable_set(_rows(profile_nos), events)
    event = next(e for e in events if e.event_key == event_key)
    return exercise_ranked_list(
        event_evidence(event),
        rankable.profiles,
        weights=weights,
        invite_limit=invite_limit,
        year_rank=rankable.year_rank,
        dataset_checksum=_dataset().checksum,
    )


def _positions(listing: ExerciseList) -> dict[int, int]:
    return {int(entry.profile_id): entry.rank for entry in listing.entries}


def _entry(listing: ExerciseList, profile_no: int) -> object:
    return next(entry for entry in listing.entries if entry.profile_id == str(profile_no))


# ---------------------------------------------------------------------------
# Ann's test case (Ann's data file, 2026-09-24)
# ---------------------------------------------------------------------------


@pytest.mark.golden
def test_the_plain_accounting_majors_are_what_anns_test_case_describes() -> None:
    by_no = {p.profile_no: p for p in _dataset().profiles}
    for number in PLAIN_ACCOUNTING_MAJORS:
        profile = by_no[number]
        assert profile.major == "Accounting"
        assert profile.stated_interests is None
        assert profile.past_event_keys == ()
    assert by_no[4].major == "Accounting"
    assert by_no[4].stated_interests is not None
    assert "Technology / information systems" in by_no[4].stated_interests


@pytest.mark.golden
def test_turned_up_p004_ranks_above_every_plain_accounting_major() -> None:
    listing = _ranked("E11", _TURNED_UP, profile_nos=SAMPLE_PROFILE_NOS)
    at = _positions(listing)

    assert all(at[4] < at[number] for number in PLAIN_ACCOUNTING_MAJORS)
    assert "stated_interest_overlap" in _entry(listing, 4).contributing_factor_keys  # type: ignore[attr-defined]


@pytest.mark.golden
def test_turned_off_the_interest_no_longer_counts_for_p004() -> None:
    """The half of "it should not" that the ranker can honour: the factor stops counting."""
    listing = _ranked("E11", _TURNED_OFF, profile_nos=SAMPLE_PROFILE_NOS)

    assert "stated_interest_overlap" not in _entry(listing, 4).contributing_factor_keys  # type: ignore[attr-defined]


@pytest.mark.golden
def test_turned_off_p004_still_ranks_above_on_its_career_goal() -> None:
    """Reason 1 in the module docstring: the role→topic table (owner ruling 2)."""
    listing = _ranked("E11", _TURNED_OFF, profile_nos=SAMPLE_PROFILE_NOS)
    at = _positions(listing)

    assert _entry(listing, 4).contributing_factor_keys == ("career_goal_fit",)  # type: ignore[attr-defined]
    assert all(at[4] < at[number] for number in PLAIN_ACCOUNTING_MAJORS)


@pytest.mark.golden
def test_with_the_goal_off_too_only_the_information_tie_break_separates_them() -> None:
    """Reason 2: equal composites, and design spec §4.4 puts the completed card first."""
    listing = _ranked("E11", _INTEREST_AND_GOAL_OFF, profile_nos=SAMPLE_PROFILE_NOS)
    at = _positions(listing)
    p004 = _entry(listing, 4)

    assert p004.contributing_factor_keys == ()  # type: ignore[attr-defined]
    for number in PLAIN_ACCOUNTING_MAJORS:
        assert _entry(listing, number).contributing_factor_keys == ()  # type: ignore[attr-defined]
        assert at[4] < at[number]


# ---------------------------------------------------------------------------
# The whole file, as the class will see it
# ---------------------------------------------------------------------------


@pytest.mark.golden
@pytest.mark.parametrize("event_key", ["E11", "E12"])
def test_the_default_list_is_thirty_names_in_a_fixed_order(event_key: str) -> None:
    first = _ranked(event_key, None)
    second = _ranked(event_key, None)

    assert len(first.entries) == 30
    assert [e.profile_id for e in first.entries] == [e.profile_id for e in second.entries]
    assert first.unlisted_class_years == ()


@pytest.mark.golden
def test_the_year_rung_speaks_on_anns_file() -> None:
    """Owner ruling 4 woke the year rung; on the real file some name is placed by it."""
    year_sentences = {
        phrase_as_sentence("tied on major; ordered by year"),
        phrase_as_sentence("tied on what counted; ordered by year"),
    }
    reasons = {
        entry.reason
        for event_key in ("E11", "E12")
        for entry in _ranked(event_key, None, invite_limit=300).entries
    }

    assert reasons & year_sentences


@pytest.mark.golden
def test_the_fixed_order_is_anns_tiebreak_order_not_the_checksum() -> None:
    """Major-only profiles of one major and one year tie on everything the data
    says, so ``tiebreak_order`` alone orders them."""
    by_no = {p.profile_no: p for p in _dataset().profiles}
    listing = _ranked("E11", None, invite_limit=300)
    groups: dict[tuple[str, str], list[int]] = {}
    for entry in listing.entries:
        profile = by_no[int(entry.profile_id)]
        if profile.stated_interests is None and not profile.past_event_keys:
            groups.setdefault((profile.major, profile.class_year), []).append(profile.profile_no)

    assert max(len(members) for members in groups.values()) >= 2
    for members in groups.values():
        orders = [by_no[number].tiebreak_order for number in members]
        assert orders == sorted(orders)
