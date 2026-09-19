"""What the class exercise's data file looks like, and what reading one yields.

Split out of ``ingest.py`` so that the *shape* of the file and the *reading* of
it are two files: the parser is behaviour and changes when a rule changes, and
everything here is description and changes when Ann's sample arrives. Nothing
in this module imports ``csv``, and nothing in it does any work — it is types
and one constant.

PLACEHOLDER (OQ-CE-01)
======================
:class:`ExerciseFileLayout` is the whole of what the parser knows about column
names, the list-cell separator, how a row says what it is, and which cell texts
read as yes and no. :data:`PLACEHOLDER_LAYOUT` is this branch's guess at Ann's
20-row sample, which has not arrived; the owner ruled on 2026-09-18 to build to
the placeholder columns now. Closing OQ-CE-01 is replacing that one object, and
``test_exercise_ingest.py`` proves it by parsing a file with different column
names and a different separator through a ``dataclasses.replace`` of it.

ADR-0025 D6
===========
``hidden_true_interests`` is a field of :class:`ParsedProfile` and of nothing
else here, and it is declared ``field(repr=False)`` so that the value cannot
reach a log line, an assertion message or a driver's ``[parameters: …]``
through the default dataclass ``repr`` — a leak through code nobody wrote.
:class:`IngestReport` has no field for it at all.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Final

__all__ = [
    "PLACEHOLDER_LAYOUT",
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
    """PLACEHOLDER (OQ-CE-01) — what the data file looks like, as data.

    Every column name the parser knows is a field here, so that Ann's sample
    closes OQ-CE-01 by replacing one object. The parser reads these names; it
    does not contain any.

    Attributes:
        record_type_column: The column that says what a row describes.
        profile_record_value: Its value on a profile row, compared
            case-insensitively.
        event_record_value: Its value on an event row.
        profile_no_column: The profile's number within the dataset ("the 300").
        display_name_column: The made-up name. Every row is fictional.
        major_column: The major.
        class_year_column: The year. **No vocabulary** — the parser reports the
            values it found rather than checking them against a list.
        past_event_keys_column: A list cell of event keys the profile attended.
        stated_interests_column: A list cell. Empty means *no card on file*,
            which is design spec §7's first state and is stored as ``None``
            rather than as an empty list. Whether Ann's file can express "a
            card with nothing on it" is on the question list.
        career_goal_column: Free text; no vocabulary.
        hidden_interests_column: ADR-0025 D6's withheld list cell.
        event_key_column: The event's identifier.
        event_name_column: The event's label.
        topic_tags_column: A list cell of the event's topics.
        target_majors_column: A list cell of majors the event aims at.
        is_exercise_event_column: True on the two rounds, false on the ten past
            events.
        sequence_column: The event's position, 1-based and unique.
        list_cell_separator: What separates entries inside a list cell.
        true_values: Cell texts read as true, compared case-insensitively after
            trimming.
        false_values: Cell texts read as false. A cell that is neither is
            refused rather than guessed at.
    """

    record_type_column: str
    profile_record_value: str
    event_record_value: str
    profile_no_column: str
    display_name_column: str
    major_column: str
    class_year_column: str
    past_event_keys_column: str
    stated_interests_column: str
    career_goal_column: str
    hidden_interests_column: str
    event_key_column: str
    event_name_column: str
    topic_tags_column: str
    target_majors_column: str
    is_exercise_event_column: str
    sequence_column: str
    list_cell_separator: str
    true_values: tuple[str, ...]
    false_values: tuple[str, ...]

    @property
    def profile_columns(self) -> tuple[str, ...]:
        """The columns a profile row is read from, in the order they are named."""
        return (
            self.profile_no_column,
            self.display_name_column,
            self.major_column,
            self.class_year_column,
            self.past_event_keys_column,
            self.stated_interests_column,
            self.career_goal_column,
            self.hidden_interests_column,
        )

    @property
    def event_columns(self) -> tuple[str, ...]:
        """The columns an event row is read from."""
        return (
            self.event_key_column,
            self.event_name_column,
            self.topic_tags_column,
            self.target_majors_column,
            self.is_exercise_event_column,
            self.sequence_column,
        )

    @property
    def required_columns(self) -> tuple[str, ...]:
        """Every column the header must carry, discriminator first.

        Derived from :attr:`profile_columns` and :attr:`event_columns`, which
        are themselves derived from this object's fields — so a column added to
        the layout is required without anyone editing a second list.
        ``test_the_required_columns_are_derived_from_the_layouts_own_fields``
        walks the dataclass fields to say so.

        One header serves both kinds of row, so a profile row leaves the event
        columns empty and the other way round. "Required" is about the header,
        never about a cell: ``major`` is nullable on ``exercise_profile`` and a
        profile with no major recorded is a fact, not a broken file.
        """
        return (self.record_type_column, *self.profile_columns, *self.event_columns)


#: PLACEHOLDER (OQ-CE-01). This module's guess at Ann's file, and the only
#: place a column name is written down.
PLACEHOLDER_LAYOUT: Final[ExerciseFileLayout] = ExerciseFileLayout(
    record_type_column="record_type",
    profile_record_value="profile",
    event_record_value="event",
    profile_no_column="profile_no",
    display_name_column="display_name",
    major_column="major",
    class_year_column="class_year",
    past_event_keys_column="past_event_keys",
    stated_interests_column="stated_interests",
    career_goal_column="career_goal",
    hidden_interests_column="hidden_true_interests",
    event_key_column="event_key",
    event_name_column="event_name",
    topic_tags_column="topic_tags",
    target_majors_column="target_majors",
    is_exercise_event_column="is_exercise_event",
    sequence_column="sequence",
    list_cell_separator=";",
    true_values=("true", "yes", "y", "1"),
    false_values=("false", "no", "n", "0", ""),
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

    ``stated_interests`` is ``None`` for "no card on file" and a tuple for a
    card, which is design spec §7's distinction and ``exercise_profile``'s
    nullable column.

    ``hidden_true_interests`` is ADR-0025 D6's withheld list: carried here so
    the repository can store it, named on no report, and **excluded from the
    ``repr``**. That exclusion is load-bearing rather than tidy. A dataclass's
    default ``repr`` is what a log line, an assertion message, a debugger
    transcript and a database driver's ``[parameters: …]`` all print, so a
    withheld field that is in the ``repr`` leaves the server through code
    nobody wrote. The value is still there to be read deliberately.
    """

    profile_no: int
    display_name: str
    major: str | None
    class_year: str | None
    past_event_keys: tuple[str, ...]
    stated_interests: tuple[str, ...] | None
    career_goal: str | None
    hidden_true_interests: tuple[str, ...] = field(repr=False)


@dataclass(frozen=True, slots=True)
class ParsedEvent:
    """One of the twelve events: ten past, then Northline and Harbor."""

    event_key: str
    name: str
    topic_tags: tuple[str, ...]
    target_majors: tuple[str, ...]
    is_exercise_event: bool
    sequence: int


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

    Carries no cell of ``hidden_true_interests``, in any field, in any form —
    including through :func:`repr`, which is why the withheld list is not a
    field here at all rather than a field that is usually empty.

    ``distinct_class_years`` is the one field that carries values rather than
    counts, and deliberately: PLACEHOLDER (OQ-CE-01), the ``class_year``
    vocabulary is undecided, so the parser refuses to invent one and reports
    what the file actually used instead.

    The term counts are ADR-0011's "counted, never silently dropped" under a
    mapping that does not exist yet: no term is mapped to G3, so every distinct
    term is reported as-is and every row is kept.

    Attributes:
        profile_count: Profile rows accepted.
        event_count: Event rows accepted.
        exercise_event_count: How many of them are the rounds; always two.
        distinct_class_years: The year values the file used, sorted.
        profiles_missing_major: Profiles with no major recorded.
        profiles_missing_class_year: Profiles with no year recorded.
        profiles_without_card: Profiles with no card on file (§7's first
            state), which is not the same as a card with nothing on it.
        distinct_stated_interest_terms: Distinct interest terms across cards.
        distinct_topic_tag_terms: Distinct topic terms across events.
        events_without_topic_tags: Events whose topic cell was empty.
        markers: The three "how much we know" groups.
    """

    profile_count: int
    event_count: int
    exercise_event_count: int
    distinct_class_years: tuple[str, ...]
    profiles_missing_major: int
    profiles_missing_class_year: int
    profiles_without_card: int
    distinct_stated_interest_terms: int
    distinct_topic_tag_terms: int
    events_without_topic_tags: int
    markers: MarkerDistribution


@dataclass(frozen=True, slots=True)
class ParsedDataset:
    """An accepted file: what to store, plus the checksum of what arrived.

    ``checksum`` is the SHA-256 of the **exact uploaded bytes**, not of the
    decoded text and not of the parsed rows. It later seeds the fixed
    tie-break permutation of the requirements' "fixed random order that never
    changes", so a re-upload of the same file must produce the same hex string
    — pinned by ``test_the_checksum_is_stable_for_the_same_bytes``.
    """

    profiles: tuple[ParsedProfile, ...]
    events: tuple[ParsedEvent, ...]
    checksum: str
    row_count: int
    report: IngestReport
