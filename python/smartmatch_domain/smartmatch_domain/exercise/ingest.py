"""Read and validate the class exercise's data file (design spec §3).

Bytes in, a :class:`ParsedDataset` or one plain sentence out. Nothing here
opens a file, touches a path, imports ``sqlalchemy``, or writes anything down:
the route hands over the uploaded bytes and this module answers. That is the
separation ``smartmatch_domain/ingest.py`` states for the CBA import path —
file handling belongs to an adapter, validation to the domain — applied to an
upload that has no adapter because it has no pipeline (§3: the instructor
needs an answer on the spot).

Every refusal is one sentence a non-programmer can act on, in §3's order, and
the first failure is the whole answer. A missing sheet names the sheet and a
missing column names the sheet and the column: *The `Profiles` sheet is missing
the column `tiebreak_order`.*

Ann's workbook (OQ-CE-01 and OQ-CE-05, closed 2026-09-24)
=========================================================
The file is Ann's ``.xlsx`` as she sent it, read by
:mod:`smartmatch_domain.exercise.workbook` (which owns every guard on the
bytes, the ZIP and the XML) and described by
:data:`~smartmatch_domain.exercise.layout.EXERCISE_LAYOUT`; no function below
contains a column name. Only the ``Profiles`` and ``Events`` sheets are read.

Every value is checked against the closed vocabularies of
:mod:`smartmatch_domain.exercise.vocabulary` — six majors, four years, thirteen
topics, sixteen career goals — and stored in Ann's spelling. A value outside
them is refused, which is the owner's ruling of 2026-09-24.

What the file says, and what is decided here
============================================
* ``profile_id`` ``P004`` is profile number 4; anything but ``P`` and digits
  is refused. ``display_name`` is first name, a space, last name.
* ``card_completed`` says whether a card exists. ``No`` beside a stated
  interest or a stated goal is a contradiction and is refused.
* ``tiebreak_order`` is a whole number, unique across the file: the last step
  of the tie-break (owner ruling 3).
* An event's ``target_major`` of ``All majors`` is stored as all six majors.
* An event's ``sequence`` is its row position on the ``Events`` sheet.
* An event's ``event_type`` is one of Ann's event types and decides whether
  the event is exploratory (OQ-CE-14); the type itself is not stored.
* ``seats`` is read on the two exercise events and must be
  :data:`~smartmatch_domain.exercise.simulation.EVENT_SEATS`: the simulated
  results run with that many seats, and a file saying otherwise is refused
  rather than ignored.
* A past event a profile attended must be one of the file's past events.

ADR-0025 D6 — the withheld columns
==================================
``hidden_true_interests`` and ``hidden_true_career_goal`` are parsed onto
:class:`ParsedProfile` so the repository can store them and the results rule
and the refresh can read them. A refusal about one of them names the column
and never quotes the cell; they appear on :class:`IngestReport` in no form, in
no ``repr`` and in no log line. The log records counts only.
"""

from __future__ import annotations

import hashlib
import logging
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Final

from smartmatch_domain.exercise.layout import (
    EXERCISE_LAYOUT,
    ExerciseFileLayout,
    IngestRefusal,
    IngestReport,
    MarkerDistribution,
    ParsedDataset,
    ParsedEvent,
    ParsedProfile,
)
from smartmatch_domain.exercise.simulation import EVENT_SEATS
from smartmatch_domain.exercise.vocabulary import (
    EXERCISE_CAREER_GOALS,
    EXERCISE_CLASS_YEARS,
    EXERCISE_EVENT_TYPES,
    EXERCISE_MAJORS,
    EXERCISE_TOPICS,
    canonical_career_goal,
    canonical_class_year,
    canonical_event_type,
    canonical_major,
    canonical_topic,
    is_all_majors,
)
from smartmatch_domain.exercise.workbook import (
    MAX_UPLOAD_BYTES,
    SheetRows,
    quote,
    read_sheets,
)
from smartmatch_domain.ingest import normalize_header

# The layout types are re-exported so a caller needs one import to parse a file
# and read the answer; ``layout.py`` holds their definitions.
__all__ = [
    "EXERCISE_EVENT_ROW_COUNT",
    "EXERCISE_LAYOUT",
    "MAX_COLUMN_INTEGER",
    "MAX_PROFILE_ROW_COUNT",
    "MAX_UPLOAD_BYTES",
    "MIN_PROFILE_ROW_COUNT",
    "ExerciseFileLayout",
    "IngestRefusal",
    "IngestReport",
    "MarkerDistribution",
    "ParsedDataset",
    "ParsedEvent",
    "ParsedProfile",
    "parse_exercise_file",
]

_LOGGER = logging.getLogger(__name__)

#: Design spec §3: "row count within 50–1000", counted over profile rows.
MIN_PROFILE_ROW_COUNT: Final[int] = 50
MAX_PROFILE_ROW_COUNT: Final[int] = 1_000

#: Design spec §3: "exactly two rows flagged as exercise events".
EXERCISE_EVENT_ROW_COUNT: Final[int] = 2

#: How many offending values a refusal sentence names before it stops.
_MAX_NAMED_VALUES: Final[int] = 5

#: The largest value an ``integer`` column holds (``profile_no``,
#: ``tiebreak_order``, ``sequence``). Python's ``int`` has no ceiling, so
#: without this a long digit string parses here and a driver refuses it later.
MAX_COLUMN_INTEGER: Final[int] = 2_147_483_647

#: The most digits a number cell may carry before it is refused unread.
_MAX_NUMBER_DIGITS: Final[int] = 10

_Row = tuple[int, Mapping[str, str]]


def parse_exercise_file(
    content: bytes, *, layout: ExerciseFileLayout = EXERCISE_LAYOUT
) -> ParsedDataset | IngestRefusal:
    """Read an uploaded workbook, or say in one sentence why it was refused.

    Args:
        content: The uploaded bytes.
        layout: Where the file keeps each value. Defaults to Ann's.

    Returns:
        A :class:`ParsedDataset` when every check of design spec §3 passed, or
        the first :class:`IngestRefusal` otherwise.
    """
    raw = bytes(content)
    dataset = _parse(raw, layout)
    if isinstance(dataset, IngestRefusal):
        _LOGGER.info("exercise data file refused: code=%s", dataset.code)
        return dataset
    _LOGGER.info(
        "exercise data file accepted: profiles=%d events=%d exercise_events=%d",
        dataset.report.profile_count,
        dataset.report.event_count,
        dataset.report.exercise_event_count,
    )
    return dataset


def _parse(raw: bytes, layout: ExerciseFileLayout) -> ParsedDataset | IngestRefusal:
    """The whole of §3, in order. The first refusal is the answer."""
    sheets = read_sheets(raw, (layout.profiles_sheet, layout.events_sheet))
    if isinstance(sheets, IngestRefusal):
        return sheets
    profile_sheet, event_sheet = sheets
    missing = _missing_columns(profile_sheet, layout.profile_columns) or _missing_columns(
        event_sheet, layout.event_columns
    )
    if missing is not None:
        return missing
    count = len(profile_sheet.rows)
    if count < MIN_PROFILE_ROW_COUNT or count > MAX_PROFILE_ROW_COUNT:
        return IngestRefusal(
            "row_count_out_of_range",
            f"The `{profile_sheet.title}` sheet has {count} profiles; it needs between "
            f"{MIN_PROFILE_ROW_COUNT} and {MAX_PROFILE_ROW_COUNT}.",
        )
    events = _parse_events(event_sheet, layout)
    if isinstance(events, IngestRefusal):
        return events
    profiles = _parse_profiles(profile_sheet, layout)
    if isinstance(profiles, IngestRefusal):
        return profiles
    cross = _check_across_rows(profile_sheet.title, profiles, events, layout)
    if cross is not None:
        return cross
    return ParsedDataset(
        profiles=profiles,
        events=events,
        checksum=hashlib.sha256(raw).hexdigest(),
        row_count=count,
        report=_build_report(profiles, events),
    )


def _missing_columns(sheet: SheetRows, required: Sequence[str]) -> IngestRefusal | None:
    """Every missing column of one sheet, named with the sheet, in one sentence."""
    missing = [column for column in required if normalize_header(column) not in sheet.headers]
    if not missing:
        return None
    if len(missing) == 1:
        sentence = f"The `{sheet.title}` sheet is missing the column `{missing[0]}`."
    else:
        listed = ", ".join(f"`{column}`" for column in missing)
        sentence = f"The `{sheet.title}` sheet is missing these columns: {listed}."
    return IngestRefusal("missing_columns", sentence)


# ---------------------------------------------------------------------------
# One cell at a time
# ---------------------------------------------------------------------------


class _Cells:
    """One row of one sheet, read by layout column name, with its refusals.

    Every sentence says the row number Excel shows and the sheet's name, so an
    instructor can find the cell. A cell of a withheld column is never quoted.
    """

    __slots__ = ("_layout", "_line", "_row", "_sheet")

    def __init__(
        self, sheet: SheetRows, line: int, row: Mapping[str, str], layout: ExerciseFileLayout
    ) -> None:
        self._sheet = sheet
        self._line = line
        self._row = row
        self._layout = layout

    def text(self, column: str) -> str:
        return self._row.get(self._sheet.headers[normalize_header(column)], "")

    def refuse(self, code: str, detail: str) -> IngestRefusal:
        return IngestRefusal(code, f"Row {self._line} of the `{self._sheet.title}` sheet {detail}")

    def required(self, column: str) -> str | IngestRefusal:
        value = self.text(column)
        return value or self.refuse("missing_value", f"has nothing in the column `{column}`.")

    def whole_number(self, column: str) -> int | IngestRefusal:
        value = _positive_int(self.text(column))
        if value is None:
            return self.refuse("bad_number", f"has no whole number in the column `{column}`.")
        return value

    def yes_no(self, column: str) -> bool | IngestRefusal:
        folded = self.text(column).casefold()
        if folded in {value.casefold() for value in self._layout.true_values}:
            return True
        if folded in {value.casefold() for value in self._layout.false_values}:
            return False
        return self.refuse(
            "bad_yes_no", f"has a value in the column `{column}` that is neither Yes nor No."
        )

    def term(
        self, column: str, lookup: Callable[[str], str | None], what: str
    ) -> str | IngestRefusal | None:
        """One vocabulary term, blank read as ``None``."""
        text = self.text(column)
        if not text:
            return None
        found = lookup(text)
        return found if found is not None else self.unknown(column, text, what)

    def required_term(
        self, column: str, lookup: Callable[[str], str | None], what: str
    ) -> str | IngestRefusal:
        """One vocabulary term that must be there."""
        found = self.term(column, lookup, what)
        if found is None:
            return self.refuse("missing_value", f"has nothing in the column `{column}`.")
        return found

    def terms(
        self, column: str, lookup: Callable[[str], str | None], what: str
    ) -> tuple[str, ...] | IngestRefusal:
        """A list cell of vocabulary terms, in file order, each once."""
        seen: dict[str, None] = {}
        for entry in _split_cell(self.text(column), self._layout):
            found = lookup(entry)
            if found is None:
                return self.unknown(column, entry, what)
            seen.setdefault(found, None)
        return tuple(seen)

    def unknown(self, column: str, text: str, what: str) -> IngestRefusal:
        if column in self._layout.withheld_columns:
            return self.refuse(
                "unknown_value", f"has a value in the column `{column}` that is not {what}."
            )
        return self.refuse(
            "unknown_value", f"has `{quote(text)}` in the column `{column}`, which is not {what}."
        )


_A_MAJOR: Final[str] = f"one of the {len(EXERCISE_MAJORS)} majors"
_A_YEAR: Final[str] = ", ".join(EXERCISE_CLASS_YEARS[:-1]) + f" or {EXERCISE_CLASS_YEARS[-1]}"
_A_TOPIC: Final[str] = f"one of the {len(EXERCISE_TOPICS)} topics"
_A_GOAL: Final[str] = f"one of the {len(EXERCISE_CAREER_GOALS)} career goals"
_AN_EVENT_TYPE: Final[str] = f"one of the {len(EXERCISE_EVENT_TYPES)} event types"


# ---------------------------------------------------------------------------
# Events
# ---------------------------------------------------------------------------


def _parse_events(
    sheet: SheetRows, layout: ExerciseFileLayout
) -> tuple[ParsedEvent, ...] | IngestRefusal:
    """One event per row, its position on the sheet as its sequence."""
    parsed: list[ParsedEvent] = []
    for position, (line, row) in enumerate(sheet.rows, start=1):
        event = _parse_event(_Cells(sheet, line, row, layout), layout, position)
        if isinstance(event, IngestRefusal):
            return event
        parsed.append(event)
    return tuple(parsed)


def _parse_event(
    cells: _Cells, layout: ExerciseFileLayout, position: int
) -> ParsedEvent | IngestRefusal:
    key = cells.required(layout.event_key_column)
    if isinstance(key, IngestRefusal):
        return key
    name = cells.required(layout.event_name_column)
    if isinstance(name, IngestRefusal):
        return name
    event_type = cells.required_term(layout.event_type_column, canonical_event_type, _AN_EVENT_TYPE)
    if isinstance(event_type, IngestRefusal):
        return event_type
    flag = cells.yes_no(layout.is_exercise_event_column)
    if isinstance(flag, IngestRefusal):
        return flag
    topics = cells.terms(layout.topic_tags_column, canonical_topic, _A_TOPIC)
    if isinstance(topics, IngestRefusal):
        return topics
    majors = _target_majors(cells, layout)
    if isinstance(majors, IngestRefusal):
        return majors
    if flag and _positive_int(cells.text(layout.seats_column)) != EVENT_SEATS:
        return cells.refuse(
            "bad_seats",
            f"gives `{quote(cells.text(layout.seats_column))}` in the column "
            f"`{layout.seats_column}` for an exercise event; this exercise runs with "
            f"{EVENT_SEATS} seats per event.",
        )
    return ParsedEvent(
        event_key=key,
        name=name,
        topic_tags=topics,
        target_majors=majors,
        is_exercise_event=flag,
        sequence=position,
        is_exploratory=EXERCISE_EVENT_TYPES[event_type],
    )


def _target_majors(cells: _Cells, layout: ExerciseFileLayout) -> tuple[str, ...] | IngestRefusal:
    """The event's majors; "All majors" is every one of the six.

    Every entry is checked before "All majors" expands, so a cell that says
    "All majors" beside something that is not a major is still refused.
    """
    column = layout.target_majors_column
    for entry in _split_cell(cells.text(column), layout):
        if not is_all_majors(entry) and canonical_major(entry) is None:
            return cells.unknown(column, entry, _A_MAJOR + ' or "All majors"')
    entries = _split_cell(cells.text(column), layout)
    if any(is_all_majors(entry) for entry in entries):
        return EXERCISE_MAJORS
    return cells.terms(column, canonical_major, _A_MAJOR)


# ---------------------------------------------------------------------------
# Profiles
# ---------------------------------------------------------------------------


def _parse_profiles(
    sheet: SheetRows, layout: ExerciseFileLayout
) -> tuple[ParsedProfile, ...] | IngestRefusal:
    """One profile per row, refusing anything the vocabulary or the table would."""
    parsed: list[ParsedProfile] = []
    for line, row in sheet.rows:
        profile = _parse_profile(_Cells(sheet, line, row, layout), layout)
        if isinstance(profile, IngestRefusal):
            return profile
        parsed.append(profile)
    return tuple(parsed)


def _parse_profile(cells: _Cells, layout: ExerciseFileLayout) -> ParsedProfile | IngestRefusal:
    number = _profile_no(cells.text(layout.profile_id_column), layout)
    if number is None:
        return cells.refuse(
            "bad_profile_id",
            f"has `{quote(cells.text(layout.profile_id_column))}` in the column "
            f"`{layout.profile_id_column}`; a profile id is {layout.profile_id_prefix} "
            f"followed by a number, such as {layout.profile_id_prefix}004.",
        )
    first = cells.required(layout.first_name_column)
    if isinstance(first, IngestRefusal):
        return first
    last = cells.required(layout.last_name_column)
    if isinstance(last, IngestRefusal):
        return last
    major = cells.required_term(layout.major_column, canonical_major, _A_MAJOR)
    if isinstance(major, IngestRefusal):
        return major
    year = cells.required_term(layout.class_year_column, canonical_class_year, _A_YEAR)
    if isinstance(year, IngestRefusal):
        return year
    card = _card(cells, layout)
    if isinstance(card, IngestRefusal):
        return card
    tiebreak = cells.whole_number(layout.tiebreak_order_column)
    if isinstance(tiebreak, IngestRefusal):
        return tiebreak
    hidden_interests = cells.terms(layout.hidden_interests_column, canonical_topic, _A_TOPIC)
    if isinstance(hidden_interests, IngestRefusal):
        return hidden_interests
    hidden_goal = cells.term(layout.hidden_career_goal_column, canonical_career_goal, _A_GOAL)
    if isinstance(hidden_goal, IngestRefusal):
        return hidden_goal
    return ParsedProfile(
        profile_no=number,
        display_name=f"{first} {last}",
        major=major,
        class_year=year,
        # Each attended event once: ``E01;E01`` is one attendance, not two, or
        # the results rule would count a frequent attender who is not one.
        past_event_keys=tuple(
            dict.fromkeys(_split_cell(cells.text(layout.past_event_keys_column), layout))
        ),
        stated_interests=card.interests,
        career_goal=card.career_goal,
        tiebreak_order=tiebreak,
        hidden_true_interests=hidden_interests,
        hidden_true_career_goal=hidden_goal,
    )


@dataclass(frozen=True, slots=True)
class _Card:
    """What a row says about its card: ``interests is None`` means no card."""

    interests: tuple[str, ...] | None
    career_goal: str | None


def _card(cells: _Cells, layout: ExerciseFileLayout) -> _Card | IngestRefusal:
    """``card_completed`` decides whether a card exists; the row must agree."""
    completed = cells.yes_no(layout.card_completed_column)
    if isinstance(completed, IngestRefusal):
        return completed
    interests = cells.terms(layout.stated_interests_column, canonical_topic, _A_TOPIC)
    if isinstance(interests, IngestRefusal):
        return interests
    goal = cells.term(layout.career_goal_column, canonical_career_goal, _A_GOAL)
    if isinstance(goal, IngestRefusal):
        return goal
    if completed:
        return _Card(interests=interests, career_goal=goal)
    for column in (layout.stated_interests_column, layout.career_goal_column):
        if cells.text(column):
            return cells.refuse(
                "card_contradiction",
                f"says No in the column `{layout.card_completed_column}` but has a value "
                f"in the column `{column}`; a profile without a card has no stated "
                "interests and no stated career goal.",
            )
    return _Card(interests=None, career_goal=None)


def _profile_no(text: str, layout: ExerciseFileLayout) -> int | None:
    """``P004`` as ``4``, or ``None`` for anything that is not the prefix and digits."""
    prefix = layout.profile_id_prefix
    if text[: len(prefix)].casefold() != prefix.casefold():
        return None
    digits = text[len(prefix) :]
    if not digits.isascii() or not digits.isdigit():
        return None
    return _positive_int(digits)


def _positive_int(text: str) -> int | None:
    """A whole number an ``integer`` column can hold, or ``None``.

    The digit count is checked before ``int()``, because converting a very long
    digit string is itself work an uploaded file should not be able to ask for.
    """
    if not text or len(text) > _MAX_NUMBER_DIGITS or not text.isascii() or not text.isdigit():
        return None
    value = int(text)
    return value if 1 <= value <= MAX_COLUMN_INTEGER else None


def _split_cell(text: str, layout: ExerciseFileLayout) -> tuple[str, ...]:
    """A list cell into its entries, trimmed, blanks dropped, order kept."""
    if not text:
        return ()
    return tuple(part.strip() for part in text.split(layout.list_cell_separator) if part.strip())


# ---------------------------------------------------------------------------
# Checks that need every row
# ---------------------------------------------------------------------------


def _check_across_rows(
    profile_sheet: str,
    profiles: Sequence[ParsedProfile],
    events: Sequence[ParsedEvent],
    layout: ExerciseFileLayout,
) -> IngestRefusal | None:
    """Design spec §3's remaining checks, in the order the spec lists them."""
    flagged = sum(1 for event in events if event.is_exercise_event)
    if flagged != EXERCISE_EVENT_ROW_COUNT:
        return IngestRefusal(
            "wrong_exercise_event_count",
            f"The file flags {flagged} events as exercise events; it needs exactly "
            f"{EXERCISE_EVENT_ROW_COUNT}, one for each round.",
        )
    prefix = layout.profile_id_prefix
    duplicates = _duplicates([f"{prefix}{profile.profile_no:03d}" for profile in profiles])
    if duplicates:
        return IngestRefusal(
            "duplicate_profile_id",
            f"Two or more profiles share the same id: {_listed(duplicates)}.",
        )
    duplicate_keys = _duplicates([event.event_key for event in events])
    if duplicate_keys:
        return IngestRefusal(
            "duplicate_event_key",
            f"Two or more events share the same id: {_listed(duplicate_keys)}.",
        )
    duplicate_orders = _duplicates([str(profile.tiebreak_order) for profile in profiles])
    if duplicate_orders:
        return IngestRefusal(
            "duplicate_tiebreak_order",
            f"Two or more profiles on the `{profile_sheet}` sheet share the same "
            f"`{layout.tiebreak_order_column}`: {_listed(duplicate_orders)}; each "
            "profile needs its own place in the fixed order.",
        )
    return _check_past_event_keys(profiles, events)


def _check_past_event_keys(
    profiles: Sequence[ParsedProfile], events: Sequence[ParsedEvent]
) -> IngestRefusal | None:
    """Every attended event must be one of the file's *past* events.

    Refused rather than trimmed: quietly discarding an attendance would change
    who "went to similar events before" without telling anybody (ADR-0011). An
    exercise event cannot have been attended yet, so naming one is refused too.
    """
    known = {event.event_key for event in events if not event.is_exercise_event}
    counts: dict[str, int] = {}
    for profile in profiles:
        for key in profile.past_event_keys:
            if key not in known:
                counts[key] = counts.get(key, 0) + 1
    if not counts:
        return None
    named = sorted(counts.items(), key=lambda item: (-item[1], item[0]))[:_MAX_NAMED_VALUES]
    listed = ", ".join(f"`{quote(key)}` ({used} rows)" for key, used in named)
    more = f" and {len(counts) - len(named)} more" if len(counts) > len(named) else ""
    return IngestRefusal(
        "unknown_past_event_key",
        f"Some profiles list attended events that are not past events in the file: {listed}{more}.",
    )


def _duplicates(values: Sequence[str]) -> tuple[str, ...]:
    """The values that appear more than once, in first-seen order."""
    seen: set[str] = set()
    repeated: dict[str, None] = {}
    for value in values:
        if value in seen:
            repeated.setdefault(value, None)
        seen.add(value)
    return tuple(repeated)


def _listed(values: Sequence[str]) -> str:
    """A few values in backticks, quoted from the file, with a count of the rest."""
    shown = ", ".join(f"`{quote(value)}`" for value in values[:_MAX_NAMED_VALUES])
    remaining = len(values) - _MAX_NAMED_VALUES
    return f"{shown} and {remaining} more" if remaining > 0 else shown


def _build_report(profiles: Sequence[ParsedProfile], events: Sequence[ParsedEvent]) -> IngestReport:
    """Counts only. Nothing here reads a withheld field (ADR-0025 D6)."""
    used = {profile.class_year for profile in profiles}
    interests = {term for p in profiles for term in (p.stated_interests or ())}
    topics = {term for event in events for term in event.topic_tags}
    return IngestReport(
        profile_count=len(profiles),
        event_count=len(events),
        exercise_event_count=sum(1 for event in events if event.is_exercise_event),
        distinct_class_years=tuple(year for year in EXERCISE_CLASS_YEARS if year in used),
        profiles_without_card=sum(1 for p in profiles if p.stated_interests is None),
        distinct_stated_interest_terms=len(interests),
        distinct_topic_tag_terms=len(topics),
        events_without_topic_tags=sum(1 for event in events if not event.topic_tags),
        markers=_markers(profiles),
    )


def _markers(profiles: Sequence[ParsedProfile]) -> MarkerDistribution:
    """The requirements' three "how much we know" groups, counted."""
    card = sum(1 for p in profiles if p.stated_interests is not None)
    with_events = sum(1 for p in profiles if p.stated_interests is None and p.past_event_keys)
    return MarkerDistribution(
        major_only=len(profiles) - card - with_events,
        major_plus_events=with_events,
        completed_card=card,
    )
