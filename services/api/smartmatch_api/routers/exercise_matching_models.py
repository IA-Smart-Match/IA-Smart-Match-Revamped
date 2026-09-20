"""What the matching routes return, and the arithmetic that has no HTTP in it.

Split out of ``exercise_matching.py`` so the router is routes: this module holds
the response contract, the one place a repository row becomes a domain value,
the placeholder class-year ordering (OQ-CE-01), and the CSV writer of design
spec §8. Nothing here imports FastAPI, and nothing here decides a status code.

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
weighting it set itself (or the OQ-CE-02 placeholder it has not changed), which
D8 permits by name — and it is echoed back *as the team stated it*, never as
``normalize_weights`` resolved it, because a normalized weight is derived from
the composition and reads as an output.

PLACEHOLDER (OQ-CE-01) — the class-year order
=============================================
Design spec §4.4's tie-break reads a ``year_rank`` mapping, "seniors first". No
such vocabulary exists: OQ-CE-01 is open, Ann's sample has not arrived, and
``smartmatch_domain.exercise.matching`` deliberately declares no default. This
module supplies an **empty** one — :data:`PLACEHOLDER_CLASS_YEAR_RANK`, which is
the seam Ann's order plugs into — so that the year settles no tie and no reason
line claims it did. The constant's own comment says why an order derived from
file order was withdrawn.
"""

from __future__ import annotations

import csv
import io
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from types import MappingProxyType
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
from smartmatch_domain.exercise_list_coverage import ListCoverage
from smartmatch_domain.student_factors import EventEvidence, ProfileCard, ProfileEvidence

from smartmatch_api.exercise_dependencies import (
    ExerciseEventRow,
    SavedSetting,
    TeamProfileRow,
)

__all__ = [
    "CSV_FORMULA_INTRODUCERS",
    "CSV_LEADING_CONTROL",
    "CSV_LEADING_WHITESPACE",
    "CSV_LIST_COLUMNS",
    "MAX_WEIGHT_KEYS",
    "MAX_WEIGHT_KEY_CHARACTERS",
    "MAX_WEIGHT_REFUSAL_CHARACTERS",
    "PLACEHOLDER_CLASS_YEAR_RANK",
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
    "csv_download_filename",
    "event_evidence",
    "neutralised_cell",
    "rankable_set",
    "ranked_list_csv",
    "ranked_list_view",
    "saved_setting_view",
]


# ---------------------------------------------------------------------------
# The repository row -> domain value step
# ---------------------------------------------------------------------------


def _text(value: str | None) -> str | None:
    """A stored text cell as a value, with blank read as absent.

    ``exercise_profile.major``, ``class_year`` and ``career_goal`` are ``TEXT``
    with no ``CHECK`` — deliberately, because OQ-CE-01 is open and a vocabulary
    written as DDL costs a migration to change. So a cell can be present and
    empty, and the domain's evidence types refuse a blank outright
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
        year_rank: :data:`PLACEHOLDER_CLASS_YEAR_RANK` — empty while OQ-CE-01
            is open, so the year never settles a tie and no sentence claims it
            did.
        unrankable_profile_count: How many profiles were left out because the
            data file records no major or no year for them. A count, not a
            score: it tells a team that the list is drawn from fewer than the
            whole file, which is a fact it would otherwise have to infer.
    """

    profiles: tuple[ExerciseProfile, ...]
    facts: Mapping[int, ProfileFacts]
    year_rank: Mapping[str, int]
    unrankable_profile_count: int


#: **PLACEHOLDER (OQ-CE-01) — the seam where Ann's class-year order plugs in.**
#:
#: Design spec §4.4's tie-break reads a ``year_rank`` mapping and wants "seniors
#: first". **Nobody has said which years exist or which of them is senior.**
#: OQ-CE-01 is open, Ann's sample has not arrived, and the owner's standing
#: ruling is to close no vocabulary in code and to invent nothing.
#:
#: So this is **empty**, and empty is a decision rather than an omission. Three
#: shapes were available:
#:
#: * *A written-down list of year names, ranked.* The one the spec sketches and
#:   the one this track may not write: it answers OQ-CE-01 in code, in a file a
#:   later reader would take for a settled decision.
#: * *An order derived from the data file* — years ranked by first appearance.
#:   This shipped first and was **withdrawn in review round 1**, and the reason
#:   is worth keeping: it is deterministic, but file order is not seniority, so
#:   the list would print Ann's verbatim sentence *"Tied on major; ordered by
#:   year."* about an order that is arbitrary. Telling a class participant that
#:   the year decided, when what decided was which row the spreadsheet happened
#:   to list first, is an untrue statement to the reader — the same class of
#:   defect review rejected on PR #180.
#: * *No order at all*, which is this.
#:
#: What the merged domain does with an empty mapping, with no edit to it:
#: ``matching._unlisted_year_rank`` gives every year the same rank, so the year
#: column of the key never separates two names; ``matching._key_against``
#: therefore never returns :attr:`~smartmatch_domain.exercise.reasons.TieBreakKey.YEAR`,
#: so **neither year sentence can be emitted at all**; a tie that the year would
#: have settled falls through to the fixed order, which has its own honest
#: sentence; and ``matching.unlisted_class_years`` reports every year present in
#: the file, which this module surfaces on the response as
#: ``unlisted_class_years`` so the gap is visible rather than silent.
#:
#: Closing OQ-CE-01 is replacing this one object with Ann's order. Nothing else
#: in this track changes, and the sentences start appearing on their own.
PLACEHOLDER_CLASS_YEAR_RANK: Final[Mapping[str, int]] = MappingProxyType({})


def event_evidence(event: ExerciseEventRow) -> EventEvidence:
    """One stored event as the four factors may read it."""
    return EventEvidence(
        event_key=event.event_key,
        topic_tags=event.topic_tags,
        target_majors=event.target_majors,
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

    Returns ``None`` when the data file recorded no major or no year. Neither is
    a failure of the file — both columns are nullable on purpose while OQ-CE-01
    is open — but ``same_major`` is the one factor every profile can earn and
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
        ProfileCard(stated_interests=interests, career_goal=career_goal)
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
        year_rank=PLACEHOLDER_CLASS_YEAR_RANK,
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


# ---------------------------------------------------------------------------
# The download (design spec §8)
# ---------------------------------------------------------------------------

#: Design spec §8's columns, in order. Named here rather than written into the
#: writer, so the header row and the value row cannot drift.
CSV_LIST_COLUMNS: Final[tuple[str, ...]] = (
    "rank",
    "name",
    "major",
    "year",
    "marker",
    "reason",
)

#: The four characters Excel and LibreOffice read as the start of a formula.
#:
#: This matters for this product specifically: a display name, a major and a
#: class year all come from a file an instructor uploaded, and the download is
#: opened in a spreadsheet by definition.
CSV_FORMULA_INTRODUCERS: Final[tuple[str, ...]] = ("=", "+", "-", "@")

#: Whitespace a spreadsheet strips from the front of a cell **before** deciding
#: whether the cell is a formula.
#:
#: Review round 1: the first version of this guard compared the cell's first
#: character against the introducers plus tab and carriage return, which its own
#: docstring already said was not the rule — ``" =cmd|…"`` and ``"\n=cmd|…"``
#: both walked straight through it. The check below looks past *all* of these
#: instead of listing two of them.
CSV_LEADING_WHITESPACE: Final[str] = " \t\r\n\v\f"

#: Leading characters that make a cell worth neutralising on their own, whatever
#: follows them: a tab, a carriage return or a newline at the front of a cell is
#: never data anybody typed, and it is how a cell smuggles a row break past a
#: careless reader.
CSV_LEADING_CONTROL: Final[tuple[str, ...]] = ("\t", "\r", "\n")

#: What a neutralised cell is prefixed with. A single quote is what a spreadsheet
#: reads as "this cell is text", and it is what the cell shows if the file is
#: opened by anything else — visible, rather than silently executed.
CSV_TEXT_PREFIX: Final[str] = "'"


def neutralised_cell(value: object) -> str:
    """One cell, with a formula introducer defused.

    The rule is the spreadsheet's own: **strip the leading whitespace first, and
    then look at the character that is left.** Checking the raw first character
    is the version that ships with a docstring describing this rule and does not
    implement it, which is what review round 1 found — ``" =cmd|…"`` and
    ``"\n=cmd|…"`` are the same attack wearing a space.

    A leading tab, carriage return or newline is neutralised even when nothing
    dangerous follows: it is never data, and a cell that begins with a row break
    is a cell worth showing rather than obeying.

    Applied to **every** cell rather than to the ones that look risky: ``rank``
    is an integer today and a rule that exempts a column is a rule that stops
    holding when the column changes.
    """
    text = str(value)
    if text[:1] in CSV_LEADING_CONTROL:
        return f"{CSV_TEXT_PREFIX}{text}"
    if text.lstrip(CSV_LEADING_WHITESPACE)[:1] in CSV_FORMULA_INTRODUCERS:
        return f"{CSV_TEXT_PREFIX}{text}"
    return text


def ranked_list_csv(view: RankedListView) -> str:
    """Design spec §8's download, as text.

    ``csv.writer`` into a :class:`io.StringIO`. Never pandas, never ``to_csv``
    — ``tools/scan_forbidden.py`` refuses both by name — and never a file on
    disk: the whole document is at most an invite limit's worth of rows, and a
    temporary file is a thing to clean up and a thing to leak.

    ``lineterminator="\\r\\n"`` is stated rather than left to the platform, so
    the bytes a classroom downloads do not depend on which machine served them.
    """
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\r\n")
    writer.writerow(CSV_LIST_COLUMNS)
    for entry in view.entries:
        writer.writerow(
            neutralised_cell(cell)
            for cell in (
                entry.rank,
                entry.display_name,
                entry.major,
                entry.class_year,
                entry.marker,
                entry.reason,
            )
        )
    return buffer.getvalue()


#: What a download is called when the event key survives sanitising as nothing.
_UNNAMED_LIST: Final[str] = "list"

#: How much of an event key is kept in a filename.
_MAX_FILENAME_STEM: Final[int] = 60


def csv_download_filename(event_key: str) -> str:
    """A ``Content-Disposition`` filename built from the event key alone.

    The key is data from an uploaded file, and a header value is parsed by the
    browser, so the alphabet is an allow-list rather than a list of characters to
    strip: letters, digits, hyphen and underscore survive and **everything else
    becomes a hyphen**, which cannot close a quoted string, start a second header
    line, or name a directory.

    Nothing else reaches the name — not the team number, not the dataset label,
    not a profile's name — because a filename is the one part of this response
    that a person forwards without reading.
    """
    stem = "".join(
        character if character.isascii() and (character.isalnum() or character in "-_") else "-"
        for character in event_key
    ).strip("-")[:_MAX_FILENAME_STEM]
    return f"{stem or _UNNAMED_LIST}-list.csv"
