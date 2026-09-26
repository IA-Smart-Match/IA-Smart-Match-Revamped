"""What the matching routes return, and the arithmetic that has no HTTP in it.

Split out of ``exercise_matching.py`` so the router is routes: this module holds
the response contract, and the one place a repository row becomes a domain
value. Nothing here imports
FastAPI and nothing here declares a route.

It does hold **one** refusal, :func:`event_or_refusal`, moved here in review
round 1 (F8) from the router: both exercise tracks resolve an event key and
both must answer an unknown one with the same sentence, so the function belongs
beside the other two that turn a stored row into something the domain reads. It
raises :class:`~smartmatch_api.exercise_errors.ExerciseError`, which imports
nothing but the standard library, and takes its status from
:class:`http.HTTPStatus` — so "no web framework here" still holds.

Design spec §8's download is ``exercise_matching_csv``, split off in review
round 2 (F4) when this file passed the 800-line ceiling.

ADR-0025 D6 — the withheld column
=================================
No model below has a field for ``hidden_true_interests``, no docstring in this
module names a value of it, and the rows these functions read arrive through
``exercise_profile_public_columns()``, which does not select it.
``tests/unit/test_exercise_matching_router.py`` walks every model here and every
schema of the exercise-scope OpenAPI document to say so — including the
handlers' docstrings, which FastAPI publishes as operation descriptions.

ADR-0025 D8 — no numeric score
==============================
``rank`` is an integer position and the counts are integers. Neither is a score,
a share or a confidence, and nothing else numeric appears: no value, no
percentage, no normalized weight. The **one** number a team is shown is the
weighting it set itself (or the OQ-CE-02 defaults it has not changed), which
D8 permits by name — and it is echoed back *as the team stated it*, never as
``normalize_weights`` resolved it, because a normalized weight is derived from
the composition and reads as an output.

Ann's data file — the class-year order and the career-goal table
================================================================
Design spec §4.4's tie-break reads a ``year_rank`` mapping, "seniors first".
Ann's file (2026-09-24) names the four years and the owner ruled the order:
:data:`~smartmatch_domain.exercise.vocabulary.EXERCISE_CLASS_YEAR_RANK`,
seniors first and first-years last, which every ranked set carries. The
year now settles ties, and Ann's "Tied on major; ordered by year." appears.

A card's career goal is one of Ann's sixteen labels; "career goal fits this
event" compares the **topic** that label points at, through
:func:`~smartmatch_domain.exercise.vocabulary.goal_topic_for_matching` — the
one place that mapping is applied for the ranker. The stored and displayed
goal stays Ann's label. An ``Undecided`` goal names no topic but is flagged
(:func:`~smartmatch_domain.exercise.vocabulary.goal_is_undecided`), and the
event carries ``is_exploratory``, so the factor gives it half a fit on a broad
exploratory event (OQ-CE-14, decided 2026-09-25).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from http import HTTPStatus
from typing import Final

from pydantic import BaseModel, ConfigDict, Field, model_validator
from smartmatch_domain.exercise.markers import (
    GroupCounts,
    InformationMarker,
    ListComposition,
    derive_marker,
    list_composition,
)
from smartmatch_domain.exercise.matching import ExerciseList, ExerciseProfile
from smartmatch_domain.exercise.registry import EXERCISE_FACTOR_LABELS
from smartmatch_domain.exercise.vocabulary import (
    EXERCISE_CLASS_YEAR_RANK,
    goal_is_undecided,
    goal_topic_for_matching,
)
from smartmatch_domain.exercise_list_coverage import ListCoverage
from smartmatch_domain.student_factors import EventEvidence, ProfileCard, ProfileEvidence

from smartmatch_api.exercise_dependencies import (
    ExerciseEventRow,
    SavedSetting,
    TeamProfileRow,
)
from smartmatch_api.exercise_errors import ExerciseError

__all__ = [
    "MAX_WEIGHT_KEYS",
    "MAX_WEIGHT_KEY_CHARACTERS",
    "MAX_WEIGHT_REFUSAL_CHARACTERS",
    "CompareView",
    "EventView",
    "EventsView",
    "GroupCountsView",
    "ListCompositionView",
    "ListCoverageView",
    "ListEntryView",
    "ProfileFacts",
    "RankableSet",
    "RankedListView",
    "SaveSettingRequest",
    "SavedSettingView",
    "SavedSettingsView",
    "event_evidence",
    "event_or_refusal",
    "rankable_set",
    "ranked_list_view",
    "saved_setting_view",
]


# ---------------------------------------------------------------------------
# The repository row -> domain value step
# ---------------------------------------------------------------------------


def _text(value: str | None) -> str | None:
    """A stored text cell as a value, with blank read as absent.

    ``exercise_profile.major``, ``class_year`` and ``career_goal`` are ``TEXT``
    with no ``CHECK`` — deliberately: the vocabularies are closed in code at
    ingest, and a vocabulary written as DDL costs a migration to change. So a
    cell can be present and empty, and the domain's evidence types refuse a
    blank outright
    (``ProfileEvidence`` and ``ProfileCard`` both raise on one). Collapsing the
    two here is the *only* place the distinction is dropped, and it is dropped
    towards "not on file", which is ADR-0011's reading of an empty statement.
    """
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


@dataclass(frozen=True, slots=True)
class ProfileFacts:
    """What a screen shows about one profile beside its rank.

    Attributes:
        display_name: The made-up name. Every row is fictional.
        major: The major. Present, because a profile without one is not ranked.
        class_year: The year, as the data file spells it.
        marker: Which of design spec §7's three groups the profile is in, under
            *this team's* overlay.
    """

    display_name: str
    major: str
    class_year: str
    marker: InformationMarker


@dataclass(frozen=True, slots=True)
class RankableSet:
    """The dataset as one team's ranker sees it.

    Attributes:
        profiles: One :class:`ExerciseProfile` per rankable profile, in data
            file order.
        facts: ``{profile_no: ProfileFacts}`` for the same set.
        year_rank: ``vocabulary.EXERCISE_CLASS_YEAR_RANK`` — seniors first.
        unrankable_profile_count: How many profiles were left out because the
            data file records no major or no year for them. A count, not a
            score: it tells a team that the list is drawn from fewer than the
            whole file, which is a fact it would otherwise have to infer.
    """

    profiles: tuple[ExerciseProfile, ...]
    facts: Mapping[int, ProfileFacts]
    year_rank: Mapping[str, int]
    unrankable_profile_count: int


def event_or_refusal(events: Sequence[ExerciseEventRow], event_key: str) -> ExerciseEventRow:
    """The named event from this team's own data file, or one plain sentence.

    Looked up in the list already read for the topic lookup rather than by a
    second query, so an event key belonging to another data file cannot resolve:
    the only events in scope are this workspace's.

    **One copy, here, for both tracks** (review round 1, F8). Every exercise
    route addressed by an event key must answer an unknown one identically —
    PR #188's review item 6 is the record of what happens when one of them does
    not — and two copies of one sentence is the shape that divergence takes.

    It sat on ``exercise_matching`` and was imported from there by the results
    track, which made a router import a router for one helper. It belongs
    beside :func:`event_evidence` and :func:`rankable_set`, which are the other
    two functions that turn a stored row into something the domain can read.
    ``exercise_matching`` re-exports the same object, so nothing that imported
    it from there moved.

    The status comes from :class:`http.HTTPStatus` rather than from FastAPI's
    ``status`` module, so this module still imports no web framework — which is
    the property its docstring claims and the one that keeps it testable
    without an app.
    """
    for event in events:
        if event.event_key == event_key:
            return event
    raise ExerciseError(
        status_code=HTTPStatus.NOT_FOUND,
        code="exercise_event_unknown",
        message="That event is not in your team's data file.",
    )


def event_evidence(event: ExerciseEventRow) -> EventEvidence:
    """One stored event as the four factors may read it."""
    return EventEvidence(
        event_key=event.event_key,
        topic_tags=event.topic_tags,
        target_majors=event.target_majors,
        exploratory=event.is_exploratory,
    )


def _profile_evidence(
    profile: TeamProfileRow, *, topics_by_event_key: Mapping[str, tuple[str, ...]]
) -> tuple[ProfileEvidence, str] | None:
    """This team's view of one profile, or ``None`` when it cannot be ranked.

    **The overlay wins where it says anything** (design spec §2, §13). A card
    this team was given replaces the base row's card; a career goal it was given
    replaces the base row's. Where the overlay says nothing — ``NULL``, which is
    not the same as an empty card — the base row stands.

    A card exists when *either* side recorded interests. ``card_career_goal``
    alone does not conjure one: design spec §13's refresh copies a card, and a
    career goal with no card behind it is a state nothing writes.

    ``attended_event_topics`` is always a tuple and never ``None``, because
    ``exercise_profile.past_event_keys`` is ``NOT NULL`` with an empty-array
    default: the column cannot express "no attendance record", only "the record
    is empty". Both read as unknown for ``past_event_topic_overlap`` and both
    derive the ``major only`` marker, so nothing downstream is misled.

    Returns ``None`` when the stored row has no major or no year. Ingest now
    refuses such a file, so only a dataset stored before the vocabularies
    closed can hold one — but ``same_major`` is the one factor every profile can earn and
    the tie-break reads the year, so a profile missing either cannot take a
    place on a ranked list. They are counted instead. The year is returned
    beside the evidence rather than read a second time by the caller, so that
    "this profile is rankable" is decided exactly once.
    """
    major = _text(profile.major)
    class_year = _text(profile.class_year)
    if major is None or class_year is None:
        return None

    interests = (
        profile.overlay_card_interests
        if profile.overlay_card_interests is not None
        else profile.stated_interests
    )
    career_goal = _text(
        profile.overlay_card_career_goal
        if profile.overlay_card_career_goal is not None
        else profile.career_goal
    )
    card = (
        ProfileCard(
            stated_interests=interests,
            career_goal=goal_topic_for_matching(career_goal),
            career_goal_undecided=goal_is_undecided(career_goal),
        )
        if interests is not None
        else None
    )

    attended = [topics_by_event_key.get(key, ()) for key in profile.past_event_keys]
    if profile.overlay_added_event_topics:
        attended.append(profile.overlay_added_event_topics)

    evidence = ProfileEvidence(
        profile_id=str(profile.profile_no),
        major=major,
        card=card,
        attended_event_topics=tuple(attended),
    )
    return evidence, class_year


def rankable_set(
    profiles: Sequence[TeamProfileRow], events: Sequence[ExerciseEventRow]
) -> RankableSet:
    """Turn one team's stored rows into everything the ranker and the table need.

    The past-event topic lookup is built from the dataset's own events, so a
    ``past_event_keys`` entry naming an event the file does not carry
    contributes no topics rather than raising — the ingest counts what a file
    holds and the matching screen is not the place to refuse a file that was
    already accepted.
    """
    topics_by_event_key = {event.event_key: event.topic_tags for event in events}
    ranked: list[ExerciseProfile] = []
    facts: dict[int, ProfileFacts] = {}
    unrankable = 0
    for profile in profiles:
        resolved = _profile_evidence(profile, topics_by_event_key=topics_by_event_key)
        if resolved is None:
            unrankable += 1
            continue
        evidence, class_year = resolved
        ranked.append(
            ExerciseProfile(
                profile_no=profile.profile_no,
                class_year=class_year,
                evidence=evidence,
                tiebreak_order=profile.tiebreak_order,
            )
        )
        facts[profile.profile_no] = ProfileFacts(
            display_name=profile.display_name,
            major=evidence.major,
            class_year=class_year,
            marker=derive_marker(evidence),
        )
    return RankableSet(
        profiles=tuple(ranked),
        facts=facts,
        year_rank=EXERCISE_CLASS_YEAR_RANK,
        unrankable_profile_count=unrankable,
    )


def _profile_no_of(entry_profile_id: str) -> int:
    """The profile number a ranked entry's ``subject_id`` holds.

    ``ProfileEvidence.profile_id`` is a string because ADR-0025 D4 puts the
    subject's identifier in ``StageBScore.subject_id``, which every scope shares.
    This module put the number in; this function takes it back out, in one place,
    so the round trip has a name rather than being an ``int(...)`` in three
    handlers.
    """
    return int(entry_profile_id)


# ---------------------------------------------------------------------------
# The response contract
# ---------------------------------------------------------------------------


class EventView(BaseModel):
    """One event a team may build a list for."""

    model_config = ConfigDict(extra="forbid")

    event_key: str = Field(description="The event's identifier in the data file.")
    name: str = Field(description="The event's label, as the data file spells it.")
    topic_tags: list[str] = Field(description="The event's topics, as the data file spells them.")
    target_majors: list[str] = Field(description="The majors this event is aimed at.")
    is_exercise_event: bool = Field(
        description=(
            "True for the two events the teams run — round one and round two — "
            "and false for the past events a profile may have attended."
        ),
    )
    sequence: int = Field(description="The event's position in the data file, from 1.")


class EventsView(BaseModel):
    """Every event in this team's data file, in file order."""

    model_config = ConfigDict(extra="forbid")

    events: list[EventView] = Field(description="Ten past events, then the two rounds.")


class ListEntryView(BaseModel):
    """One name on the list, as a class participant sees it (ADR-0025 D8)."""

    model_config = ConfigDict(extra="forbid")

    rank: int = Field(description="Position on the list, from 1. Not a score.")
    profile_no: int = Field(description="The profile's number in the data file.")
    display_name: str = Field(description="The made-up name. Every row is fictional.")
    major: str = Field(description="The profile's major.")
    class_year: str = Field(description="The profile's year, as the data file spells it.")
    marker: str = Field(
        description=(
            "How much is on file about this profile under your team's view: "
            "`major_only`, `major_plus_events` or `completed_card`."
        ),
    )
    reason: str = Field(
        description="One sentence saying why this name is here, in the course's own words."
    )
    contributing_factor_keys: list[str] = Field(
        description=(
            "The factors that counted for this name, in rulebook order. Keys, "
            "not numbers — render them through `factor_labels`."
        ),
    )
    undecided_goal_half: bool = Field(
        description=(
            "True when the career goal counted only as an undecided goal's half "
            "on a broad exploratory event. A flag, not a number."
        ),
    )


class GroupCountsView(BaseModel):
    """One dimension of design spec §7's table: the list beside the whole file."""

    model_config = ConfigDict(extra="forbid")

    dimension: str = Field(description="What is being counted by: `major`, `class_year`, `marker`.")
    on_list: dict[str, int] = Field(description="How many of each label are on the current list.")
    all_profiles: dict[str, int] = Field(
        description="How many of each label there are across the whole data file."
    )


class ListCoverageView(BaseModel):
    """The one-line notice behind the table: groups with nobody on the list."""

    model_config = ConfigDict(extra="forbid")

    missing_majors: list[str] = Field(
        description="Majors some profile carries and no name on the list does."
    )
    missing_class_years: list[str] = Field(description="The same, for class years.")
    has_uncovered_group: bool = Field(
        description="Whether there is anything at all for the notice to say."
    )


class ListCompositionView(BaseModel):
    """Design spec §7's "who is on the list" table, and its notice."""

    model_config = ConfigDict(extra="forbid")

    by_major: GroupCountsView = Field(description="Counts by major.")
    by_class_year: GroupCountsView = Field(description="Counts by class year.")
    by_marker: GroupCountsView = Field(
        description="Counts by how much is on file. All three groups always appear."
    )
    coverage: ListCoverageView = Field(description="Which groups have nobody on the list.")


class RankedListView(BaseModel):
    """A ranked list for one event, with the table that describes it."""

    model_config = ConfigDict(extra="forbid")

    event_key: str = Field(description="The event this list was built for.")
    event_name: str = Field(description="That event's label.")
    invite_limit: int = Field(description="The cap the list was cut at, from the data file.")
    setting_name: str | None = Field(
        default=None,
        description="The saved setting the weights came from, or null when they did not.",
    )
    weights: dict[str, float] = Field(
        description=(
            "The four weights this list was built with, exactly as your team "
            "stated them — or the placeholder defaults while nobody has changed "
            "them. The only number here that is not a rank or a count."
        ),
    )
    factor_labels: dict[str, str] = Field(
        description="The plain words for each factor key, for a screen to render."
    )
    entries: list[ListEntryView] = Field(description="The names, in order.")
    composition: ListCompositionView = Field(description='The "who is on the list" table.')
    unlisted_class_years: list[str] = Field(
        description=(
            "Class years carried by a profile that the ordering did not name. "
            "Reported rather than guessed at while the year vocabulary is open."
        ),
    )
    unrankable_profile_count: int = Field(
        description=(
            "How many profiles the data file records no major or no year for. "
            "They take no place on a list; the count says the list was drawn "
            "from fewer than the whole file."
        ),
    )


class CompareView(BaseModel):
    """Design spec §6's side by side: two lists and the names on both."""

    model_config = ConfigDict(extra="forbid")

    a: RankedListView = Field(description="The first setting's list.")
    b: RankedListView = Field(description="The second setting's list.")
    on_both_profile_nos: list[int] = Field(
        description="The profile numbers that appear on both lists, in the first list's order."
    )


class SavedSettingView(BaseModel):
    """One weighting a team saved, as it saved it."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(description="What your team called it.")
    weights: dict[str, float] = Field(description="The four weights, as your team stated them.")
    created_at: datetime = Field(description="When the name was first saved.")


class SavedSettingsView(BaseModel):
    """Every weighting this team saved for one event."""

    model_config = ConfigDict(extra="forbid")

    event_key: str = Field(description="The event these settings belong to.")
    settings: list[SavedSettingView] = Field(description="Oldest first.")
    max_settings: int = Field(description="How many names your team may keep for one event.")


#: How many weights one request may propose.
#:
#: The rulebook names four. Eight leaves room for a client that sends a key the
#: registry has since dropped without turning a typo into a refusal nobody can
#: read — and, far more importantly, it is what stops the refusal from being an
#: amplifier: see :data:`MAX_WEIGHT_REFUSAL_CHARACTERS`.
MAX_WEIGHT_KEYS: Final[int] = 8

#: How long one proposed weight's key may be. Generous against the longest key
#: the rulebook actually has, and short enough that a key cannot be a payload.
MAX_WEIGHT_KEY_CHARACTERS: Final[int] = 64

#: How much of a refusal about weights may be returned.
#:
#: **This is a bound on amplification, not tidiness.** These routes take no
#: login; the weight validator names every offending field at once and quotes
#: each rejected key verbatim, at about 190 bytes per key. Unbounded, a body of
#: a few thousand short unknown keys turns a request into a multi-megabyte
#: response and reflects the caller's own text back onto a classroom projector.
#: The key count and key length above bound the input; this bounds the output
#: even if a future validator grows more to say per key.
MAX_WEIGHT_REFUSAL_CHARACTERS: Final[int] = 400


class SaveSettingRequest(BaseModel):
    """The body of a save: four weights and nothing else."""

    model_config = ConfigDict(extra="forbid")

    weights: dict[str, float] = Field(
        max_length=MAX_WEIGHT_KEYS,
        description=(
            "The weights, keyed by factor key. A key the rulebook does not name, "
            "a value that is not a finite number, and a negative value are each "
            "refused rather than repaired. At most "
            f"{MAX_WEIGHT_KEYS} keys, each at most {MAX_WEIGHT_KEY_CHARACTERS} "
            "characters."
        ),
    )

    @model_validator(mode="before")
    @classmethod
    def _refuse_oversized_keys(cls, data: object) -> object:
        """Bound the keys **before** pydantic can quote one back (review 2, F2).

        ``max_length`` on the field above bounds the key *count* and nothing
        else, and the handler's own bound runs after validation — so a body like
        ``{"weights": {"<a megabyte>": "x"}}`` failed inside pydantic first, and
        ``smartmatch_api.errors._describe_validation_error`` builds ``field``
        by joining the error's ``loc``, which for a dict entry **is** the
        caller's key. Up to eight unbounded keys came back in one 422.

        ``mode="before"`` is what makes the bound early enough: it sees the raw
        mapping, so it can refuse the shape before per-entry validation has any
        key to put in a ``loc``. The refusal names no key and quotes no length
        the caller chose — a refusal about a payload being too large is the last
        place to echo the payload — and it is deliberately the same sentence for
        "too many" and "too long", so the response distinguishes nothing about
        what was sent.

        The handler's :func:`_within_bounds_or_refusal` is not redundant with
        this: it is what covers weights that never pass through this model at
        all, which is every weight arriving on a query string.
        """
        if not isinstance(data, dict):
            return data
        weights = data.get("weights")
        if not isinstance(weights, dict):
            return data
        if len(weights) > MAX_WEIGHT_KEYS or any(
            isinstance(key, str) and len(key) > MAX_WEIGHT_KEY_CHARACTERS for key in weights
        ):
            raise ValueError("weights: too many, or named too long, to be factor keys")
        return data


# ---------------------------------------------------------------------------
# Building the views
# ---------------------------------------------------------------------------


def _counts_view(counts: GroupCounts) -> GroupCountsView:
    return GroupCountsView(
        dimension=counts.dimension,
        on_list=dict(counts.on_list),
        all_profiles=dict(counts.all_profiles),
    )


def _coverage_view(coverage: ListCoverage) -> ListCoverageView:
    return ListCoverageView(
        missing_majors=list(coverage.missing_majors),
        missing_class_years=list(coverage.missing_class_years),
        has_uncovered_group=coverage.has_uncovered_group,
    )


def _composition_view(composition: ListComposition) -> ListCompositionView:
    return ListCompositionView(
        by_major=_counts_view(composition.by_major),
        by_class_year=_counts_view(composition.by_class_year),
        by_marker=_counts_view(composition.by_marker),
        coverage=_coverage_view(composition.coverage),
    )


def _composition_for(ranked: ExerciseList, rankable: RankableSet) -> ListComposition:
    """Design spec §7's table, **composed** from the domain rather than re-derived.

    ``list_composition`` already counts by major, by year and by marker and
    already calls ``find_uncovered_groups`` for the notice. Counting here as
    well would be a second answer to one question, and the failure mode of two
    answers is that a screen shows a count and a notice that disagree.

    The whole-file side is the *rankable* set, not every row: a profile with no
    major on file could never appear on any list, so counting it as a group with
    nobody on the list would produce a notice nothing a team does can ever
    satisfy. ``unrankable_profile_count`` is where those rows are reported.
    """
    listed = [
        (facts.major, facts.class_year, facts.marker)
        for facts in (rankable.facts[_profile_no_of(entry.profile_id)] for entry in ranked.entries)
    ]
    everyone = [(facts.major, facts.class_year, facts.marker) for facts in rankable.facts.values()]
    return list_composition(listed, everyone)


def ranked_list_view(
    ranked: ExerciseList,
    rankable: RankableSet,
    *,
    event: ExerciseEventRow,
    weights: Mapping[str, float],
    setting_name: str | None,
) -> RankedListView:
    """One ranked list, its table and its notice, as one response."""
    entries: list[ListEntryView] = []
    for entry in ranked.entries:
        profile_no = _profile_no_of(entry.profile_id)
        facts = rankable.facts[profile_no]
        entries.append(
            ListEntryView(
                rank=entry.rank,
                profile_no=profile_no,
                display_name=facts.display_name,
                major=facts.major,
                class_year=facts.class_year,
                marker=str(entry.marker),
                reason=entry.reason,
                contributing_factor_keys=list(entry.contributing_factor_keys),
                undecided_goal_half=entry.undecided_goal_half,
            )
        )
    return RankedListView(
        event_key=event.event_key,
        event_name=event.name,
        invite_limit=ranked.invite_limit,
        setting_name=setting_name,
        weights=dict(weights),
        factor_labels=dict(EXERCISE_FACTOR_LABELS),
        entries=entries,
        composition=_composition_view(_composition_for(ranked, rankable)),
        unlisted_class_years=list(ranked.unlisted_class_years),
        unrankable_profile_count=rankable.unrankable_profile_count,
    )


def saved_setting_view(setting: SavedSetting) -> SavedSettingView:
    """One stored setting as a response."""
    return SavedSettingView(
        name=setting.name,
        weights=dict(setting.weights),
        created_at=setting.created_at,
    )
