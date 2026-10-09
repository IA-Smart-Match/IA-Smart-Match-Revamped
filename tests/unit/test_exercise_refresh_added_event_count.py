"""How a refresh-added event counts toward "went to similar events before".

Ann's revisions of 2026-10-02 made that factor a count of related past events:
none earns 0, one earns 0.5, two or more earn 1. A team's refresh (design spec
§13) adds the topics of the event the profile just attended to that team's
overlay, and ``rankable_set`` hands them to the factor as one more attended
event (``exercise_matching_models._profile_evidence``).

So the overlay counts as **one event**, not as extra topics on an existing one.
The decision record leaves this as is ("Not decided here",
``docs/decisions/class-exercise-factor-revisions-2026-10-02.md``). This file
pins what the code does, through the same row-to-input step the route uses, so
a change to it is a deliberate edit here rather than a side effect.
"""

from __future__ import annotations

from smartmatch_api.exercise_dependencies import ExerciseEventRow, TeamProfileRow
from smartmatch_api.routers.exercise_matching_models import event_evidence, rankable_set
from smartmatch_domain.factors import FactorScore
from smartmatch_domain.student_factors import past_event_topic_overlap

_RELATED_TOPICS = ("Data analytics",)

_PAST_RELATED = ExerciseEventRow(
    event_key="E08",
    name="A past event on the same topic",
    topic_tags=_RELATED_TOPICS,
    target_majors=("Marketing",),
    is_exercise_event=False,
    sequence=8,
)
_PAST_UNRELATED = ExerciseEventRow(
    event_key="E05",
    name="A past event on another topic",
    topic_tags=("Marketing",),
    target_majors=("Marketing",),
    is_exercise_event=False,
    sequence=5,
)
_RANKED = ExerciseEventRow(
    event_key="E11",
    name="The event being ranked",
    topic_tags=_RELATED_TOPICS,
    target_majors=("Marketing",),
    is_exercise_event=True,
    sequence=11,
)
_EVENTS = (_PAST_UNRELATED, _PAST_RELATED, _RANKED)


def _score(*, past_event_keys: tuple[str, ...], overlay: tuple[str, ...]) -> FactorScore:
    """The factor for one stored row, built the way the list route builds it."""
    row = TeamProfileRow(
        profile_no=1,
        display_name="A made-up name",
        major="Marketing",
        class_year="Senior",
        past_event_keys=past_event_keys,
        stated_interests=None,
        career_goal=None,
        overlay_added_event_topics=overlay,
        overlay_card_interests=None,
        overlay_card_career_goal=None,
        non_responding=False,
        tiebreak_order=1,
    )
    (profile,) = rankable_set((row,), _EVENTS).profiles
    return past_event_topic_overlap(profile.evidence, event_evidence(_RANKED))


def test_one_related_past_event_alone_earns_half() -> None:
    assert _score(past_event_keys=("E08",), overlay=()).value == 0.5


def test_one_related_past_event_plus_a_related_overlay_earns_the_whole_factor() -> None:
    """The overlay is counted as a second related event: 1 + 1 = 2 or more."""
    score = _score(past_event_keys=("E08",), overlay=_RELATED_TOPICS)

    assert score.value == 1.0
    assert score.basis == "2 of 2 past events attended share a topic with this event"


def test_a_related_overlay_alone_earns_half() -> None:
    """With no past event on file the overlay is the one related event."""
    assert _score(past_event_keys=(), overlay=_RELATED_TOPICS).value == 0.5


def test_an_unrelated_past_event_plus_a_related_overlay_earns_half() -> None:
    score = _score(past_event_keys=("E05",), overlay=_RELATED_TOPICS)

    assert score.value == 0.5
    assert score.basis == "1 of 2 past events attended share a topic with this event"


def test_an_overlay_with_no_shared_topic_adds_an_event_but_no_related_one() -> None:
    score = _score(past_event_keys=("E08",), overlay=("Marketing",))

    assert score.value == 0.5
    assert score.basis == "1 of 2 past events attended share a topic with this event"
