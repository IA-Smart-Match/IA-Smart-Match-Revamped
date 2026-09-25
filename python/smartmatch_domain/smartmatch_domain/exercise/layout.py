"""What the class exercise's data file looks like, and what reading one yields.

Split out of ``ingest.py`` so that the *shape* of the file and the *reading* of
it are two files: the parser is behaviour and changes when a rule changes, and
everything here is description. Nothing in this module reads a workbook, and
nothing in it does any work — it is types and one constant.

Ann's workbook (OQ-CE-01, closed 2026-09-24)
============================================
Ann's final file is an ``.xlsx`` with a ``Profiles`` sheet and an ``Events``
sheet (plus ``Read Me`` and, on the full file, ``Benchmark``, which are never
read). Her Read Me says "Column names are final", and :data:`EXERCISE_LAYOUT`
writes them down once. :class:`ExerciseFileLayout` is the whole of what the
parser knows about sheet names, column names, the list-cell separator, the
``P``-prefix of a profile id, and which cell texts read as yes and no; the
parser reads these names and contains none, and ``test_exercise_ingest.py``
proves it by parsing a workbook with renamed columns through a
``dataclasses.replace`` of the layout.

Columns the parser does not read — ``events_attended_count`` and
``info_level`` (Ann: "can also be computed by the app"), and ``event_date``
(nothing shows it) — are not on the layout, so a file without them is still
accepted. ``event_type`` **is** read, since OQ-CE-14 was decided on 2026-09-25:
it says whether an event is broad and exploratory, which an undecided career
goal half-fits (:mod:`smartmatch_domain.exercise.vocabulary`).

ADR-0025 D6
===========
``hidden_true_interests`` and ``hidden_true_career_goal`` are fields of
:class:`ParsedProfile` and of nothing else here, and both are declared
``field(repr=False)`` so that neither value can reach a log line, an assertion
message or a driver's ``[parameters: …]`` through the default dataclass
``repr`` — a leak through code nobody wrote. :class:`IngestReport` has no field
for either at all.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Final

__all__ = [
    "EXERCISE_LAYOUT",
    "ExerciseFileLayout",
    "IngestRefusal",
    "IngestReport",
    "MarkerDistribution",
    "ParsedDataset",
    "ParsedEvent",
    "ParsedProfile",
]


@dataclass(frozen=True, slots=True)
class ExerciseFileLayout:
    """What the data file looks like, as data.

    Attributes:
        profiles_sheet: The sheet holding "the 300".
        events_sheet: The sheet holding the twelve events.
        profile_id_column: ``P001``–``P300``; the digits are the profile number.
        profile_id_prefix: The letter every profile id starts with.
        first_name_column: The made-up first name. Every row is fictional.
        last_name_column: The made-up last name.
        major_column: One of the six majors. Always known.
        class_year_column: One of the four years.
        past_event_keys_column: A list cell of past event ids attended.
        card_completed_column: Yes or No — whether the profile has a card.
        stated_interests_column: A list cell of topics; blank without a card.
        career_goal_column: A career-goal label; blank without a card.
        tiebreak_order_column: Ann's fixed order for the last tie-break step.
        hidden_interests_column: ADR-0025 D6's withheld list cell.
        hidden_career_goal_column: ADR-0025 D6's withheld career goal.
        event_key_column: The event's identifier.
        event_name_column: The event's label.
        event_type_column: The kind of event; decides whether it is
            exploratory (OQ-CE-14).
        topic_tags_column: A list cell of the event's topics.
        target_majors_column: One major, or "All majors".
        is_exercise_event_column: Yes on the two rounds, No on the past events.
        seats_column: The seats of an exercise event.
        list_cell_separator: What separates entries inside a list cell.
        true_values: Cell texts read as yes, compared case-insensitively after
            trimming.
        false_values: Cell texts read as no. A cell that is neither is refused
            rather than guessed at.
    """

    profiles_sheet: str
    events_sheet: str
    profile_id_column: str
    profile_id_prefix: str
    first_name_column: str
    last_name_column: str
    major_column: str
    class_year_column: str
    past_event_keys_column: str
    card_completed_column: str
    stated_interests_column: str
    career_goal_column: str
    tiebreak_order_column: str
    hidden_interests_column: str
    hidden_career_goal_column: str
    event_key_column: str
    event_name_column: str
    event_type_column: str
    topic_tags_column: str
    target_majors_column: str
    is_exercise_event_column: str
    seats_column: str
    list_cell_separator: str
    true_values: tuple[str, ...]
    false_values: tuple[str, ...]

    @property
    def profile_columns(self) -> tuple[str, ...]:
        """Every column the ``Profiles`` sheet must carry, in the file's order."""
        return (
            self.profile_id_column,
            self.first_name_column,
            self.last_name_column,
            self.major_column,
            self.class_year_column,
            self.past_event_keys_column,
            self.card_completed_column,
            self.stated_interests_column,
            self.career_goal_column,
            self.tiebreak_order_column,
            self.hidden_interests_column,
            self.hidden_career_goal_column,
        )

    @property
    def event_columns(self) -> tuple[str, ...]:
        """Every column the ``Events`` sheet must carry, in the file's order."""
        return (
            self.event_key_column,
            self.event_name_column,
            self.event_type_column,
            self.topic_tags_column,
            self.target_majors_column,
            self.is_exercise_event_column,
            self.seats_column,
        )

    @property
    def withheld_columns(self) -> frozenset[str]:
        """The columns whose cells no refusal sentence may quote (ADR-0025 D6)."""
        return frozenset({self.hidden_interests_column, self.hidden_career_goal_column})


#: Ann's column names, from her Read Me of 2026-09-24 ("Column names are
#: final"). The only place a sheet or column name is written down.
EXERCISE_LAYOUT: Final[ExerciseFileLayout] = ExerciseFileLayout(
    profiles_sheet="Profiles",
    events_sheet="Events",
    profile_id_column="profile_id",
    profile_id_prefix="P",
    first_name_column="first_name",
    last_name_column="last_name",
    major_column="major",
    class_year_column="year",
    past_event_keys_column="events_attended",
    card_completed_column="card_completed",
    stated_interests_column="stated_interests",
    career_goal_column="stated_career_goal",
    tiebreak_order_column="tiebreak_order",
    hidden_interests_column="hidden_true_interests",
    hidden_career_goal_column="hidden_true_career_goal",
    event_key_column="event_id",
    event_name_column="event_name",
    event_type_column="event_type",
    topic_tags_column="event_topics",
    target_majors_column="target_major",
    is_exercise_event_column="exercise_event",
    seats_column="seats",
    list_cell_separator=";",
    true_values=("yes", "y", "true"),
    false_values=("no", "n", "false", ""),
)


@dataclass(frozen=True, slots=True)
class IngestRefusal:
    """Why the file was not accepted: one code and one sentence.

    The sentence is what an instructor reads; the code is what a test and a log
    line name, so that changing the wording of a sentence does not change what
    a test asserts. No refusal sentence names a cell of the withheld column —
    ``test_exercise_ingest.py`` walks a corpus of bad files to say so.
    """

    code: str
    message: str


@dataclass(frozen=True, slots=True)
class ParsedProfile:
    """One of "the 300", as the file described it. Every row is fictional.

    ``stated_interests`` is ``None`` for "no card on file" (``card_completed``
    is No) and a tuple for a card, which is design spec §7's distinction and
    ``exercise_profile``'s nullable column. Every term is one of the thirteen
    topics in Ann's own spelling, and ``career_goal`` is one of her sixteen
    labels (:mod:`smartmatch_domain.exercise.vocabulary`).

    ``hidden_true_interests`` and ``hidden_true_career_goal`` are ADR-0025 D6's
    withheld values: carried here so the repository can store them, named on no
    report, and **excluded from the ``repr``**. That exclusion is load-bearing
    rather than tidy. A dataclass's default ``repr`` is what a log line, an
    assertion message, a debugger transcript and a database driver's
    ``[parameters: …]`` all print, so a withheld field that is in the ``repr``
    leaves the server through code nobody wrote. The values are still there to
    be read deliberately.
    """

    profile_no: int
    display_name: str
    major: str
    class_year: str
    past_event_keys: tuple[str, ...]
    stated_interests: tuple[str, ...] | None
    career_goal: str | None
    tiebreak_order: int
    hidden_true_interests: tuple[str, ...] = field(repr=False)
    hidden_true_career_goal: str | None = field(default=None, repr=False)


@dataclass(frozen=True, slots=True)
class ParsedEvent:
    """One of the twelve events: ten past, then Northline and Harbor.

    ``sequence`` is the event's row position on the ``Events`` sheet, from 1.
    ``target_majors`` holds all six majors for an event whose file cell says
    "All majors", so "same major" is a plain membership test for every event.
    ``is_exploratory`` is read off the ``event_type`` cell through
    :func:`~smartmatch_domain.exercise.vocabulary.event_type_is_exploratory`;
    the type itself is not kept, because nothing shows it (OQ-CE-14).
    """

    event_key: str
    name: str
    topic_tags: tuple[str, ...]
    target_majors: tuple[str, ...]
    is_exercise_event: bool
    sequence: int
    is_exploratory: bool = False


@dataclass(frozen=True, slots=True)
class MarkerDistribution:
    """How much is known about the profiles, by the requirements' three groups.

    "Next to every profile, a simple marker: major only; major plus events
    attended; completed card." Counted at ingest so the instructor sees the
    shape of the file they uploaded — Ann's table asks for about a third with
    attendance and about seventy with a card, and this is how they check.
    """

    major_only: int
    major_plus_events: int
    completed_card: int


@dataclass(frozen=True, slots=True)
class IngestReport:
    """What the accepted file contained, in counts. Safe to show and to log.

    Carries no cell of either withheld column, in any field, in any form —
    including through :func:`repr`, which is why neither is a field here at
    all rather than a field that is usually empty.

    ``distinct_class_years`` is the one field that carries values rather than
    counts: which of the four years the file actually used.

    Attributes:
        profile_count: Profile rows accepted.
        event_count: Event rows accepted.
        exercise_event_count: How many of them are the rounds; always two.
        distinct_class_years: The years the file used, youngest first.
        profiles_without_card: Profiles with no card on file (§7's first
            state), which is not the same as a card with nothing on it.
        distinct_stated_interest_terms: Distinct topics across cards.
        distinct_topic_tag_terms: Distinct topics across events.
        events_without_topic_tags: Events whose topic cell was empty.
        markers: The three "how much we know" groups.
    """

    profile_count: int
    event_count: int
    exercise_event_count: int
    distinct_class_years: tuple[str, ...]
    profiles_without_card: int
    distinct_stated_interest_terms: int
    distinct_topic_tag_terms: int
    events_without_topic_tags: int
    markers: MarkerDistribution


@dataclass(frozen=True, slots=True)
class ParsedDataset:
    """An accepted file: what to store, plus the checksum of what arrived.

    ``checksum`` is the SHA-256 of the **exact uploaded bytes**, not of the
    parsed rows. It identifies the upload, and it seeds the fixed tie-break
    order for a dataset stored before ``tiebreak_order`` existed — so a
    re-upload of the same file must produce the same hex string, pinned by
    ``test_the_checksum_is_stable_for_the_same_bytes``.
    """

    profiles: tuple[ParsedProfile, ...]
    events: tuple[ParsedEvent, ...]
    checksum: str
    row_count: int
    report: IngestReport
