"""Read and validate the class exercise's data file (design spec §3).

Bytes in, a :class:`ParsedDataset` or a single plain sentence out. Nothing here
opens a file, touches a path, imports ``sqlalchemy``, or writes anything down:
the route hands over the uploaded bytes and this module answers. That is the
same separation ``smartmatch_domain/ingest.py`` states for the CBA import path
— file handling belongs to an adapter, validation belongs to the domain —
applied to an upload that has no adapter because it has no pipeline (§3: the
instructor needs an answer on the spot, so the job and review path behind
``routers/imports.py`` is not used).

One sentence, aimed at an instructor
====================================
Every refusal is one sentence a non-programmer can act on, in the order §3
names, and the first failure is the whole answer. The spec's own example is
carried verbatim by :func:`_missing_columns_sentence`: *The file is missing the
column ``major``.* The requirements ask Danny for "data-file loading with a
plain error when a column is missing", and a stack trace, a field path, or a
list of twelve problems are all worse answers to that than the first one.

PLACEHOLDER (OQ-CE-01) — the layout, and why it is one object
=============================================================
Ann's 20-row sample with the final column names has not arrived, and the owner
ruled on 2026-09-18 to build to the placeholder columns now. So **every column
name, the list-cell separator, and the way a row declares what it is** are
fields of :class:`ExerciseFileLayout`, and :data:`PLACEHOLDER_LAYOUT` is this
module's guess at them. Closing OQ-CE-01 is editing that one object; no
function below contains a column name.

Design spec §3 says "multipart, one file" while §2 needs about 300 profiles
*and* 12 events. The format is undecided, so the placeholder picks the layout
that keeps both facts true: **one CSV with a ``record_type`` column** whose
value says whether the row describes a profile or an event. The alternatives
considered, and why they lost, are on this track's pull request and in the
question list for Ann. None of them is refused forever — each is a different
``ExerciseFileLayout``, and the discriminator lives in that object precisely so
that "two files" or "profiles only" is a layout change rather than a parser
rewrite.

PLACEHOLDER (OQ-CE-05) — CSV, and what happens to an XLSX
=========================================================
``csv.DictReader`` from the standard library, as §3 and the register row both
say. ``openpyxl`` is not imported, is not a dependency, and is not a fallback
here: an XLSX upload is **refused with a sentence asking for a CSV export**,
detected by the ZIP magic bytes as well as by the file name, because a
spreadsheet renamed ``.csv`` is still a spreadsheet and the byte-level check is
the one a rename cannot get past.

No vocabulary is closed here
============================
§3 asks for "every ``class_year`` in the vocabulary" and for interest terms
"mapped to G3". Both vocabularies are OQ-CE-01, and the G3 mapping is a gated
area besides. Inventing either would answer an open question in code, so this
module does neither. It validates ``class_year`` only for the things the
database would refuse anyway, and **reports the distinct values it found** so
the instructor — and Ann — can read the vocabulary off the file instead of off
a guess. Terms are normalized and counted, never mapped and never dropped:
ADR-0011's "counted, never silently dropped", with the counting on
:class:`IngestReport`.

ADR-0025 D6 — the withheld column
=================================
``hidden_true_interests`` is parsed and carried on :class:`ParsedProfile`, so
that the repository can store it and the simulated-results rule can read it.
It appears in **no** refusal sentence, on :class:`IngestReport` in no form, and
in no log line. The log records counts only — never a cell, never a name.

Untrusted input
===============
This parses a file a browser uploaded. The byte cap, the cell cap, the column
cap and the row cap below are all checked *before* any per-row work, NUL bytes
are refused outright, and ``csv.field_size_limit`` is set to a bounded value
and restored. No cell is ever evaluated: a leading ``=``, ``+`` or ``@`` is
data here and nothing reads it as a formula. The CSV-injection risk of those
prefixes belongs to the **download** track of §8, which writes cells rather
than reading them; it is noted here and acted on there.
"""

from __future__ import annotations

import csv
import hashlib
import io
import logging
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Final

from smartmatch_domain.events import normalize_tag_value
from smartmatch_domain.exercise.layout import (
    PLACEHOLDER_LAYOUT,
    ExerciseFileLayout,
    IngestRefusal,
    IngestReport,
    MarkerDistribution,
    ParsedDataset,
    ParsedEvent,
    ParsedProfile,
)
from smartmatch_domain.ingest import normalize_header

# Re-exported so that a caller needs one import to parse a file and read the
# answer. ``layout.py`` holds the definitions — the shape of the file is
# description and changes when Ann's sample arrives, and this module is
# behaviour and changes when a rule does.
__all__ = [
    "EXERCISE_EVENT_ROW_COUNT",
    "MAX_CELL_CHARACTERS",
    "MAX_COLUMN_COUNT",
    "MAX_DATA_ROW_COUNT",
    "MAX_PROFILE_ROW_COUNT",
    "MAX_UPLOAD_BYTES",
    "MIN_PROFILE_ROW_COUNT",
    "PLACEHOLDER_LAYOUT",
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

#: The largest upload this will look at, in bytes. About three hundred profiles
#: and twelve events is well under a hundred kilobytes; two mebibytes leaves an
#: instructor room to paste in a wider export without leaving room for a file
#: that is not a class roster at all. Checked before anything is decoded.
MAX_UPLOAD_BYTES: Final[int] = 2 * 1024 * 1024

#: The longest a single cell may be. Long enough for a sentence of interests,
#: short enough that a million-character field is refused rather than parsed.
MAX_CELL_CHARACTERS: Final[int] = 500

#: The most columns a header may carry. The placeholder layout needs thirteen.
MAX_COLUMN_COUNT: Final[int] = 64

#: The most data rows that will be read. Design spec §2's file is about 312
#: rows; this bound exists so a file that is not one stops early.
MAX_DATA_ROW_COUNT: Final[int] = 4_000

#: Design spec §3: "row count within 50–1000". Counted over profile rows, which
#: are "the 300" the sentence is about, and aligned with
#: ``ck_exercise_dataset_row_count`` (``row_count >= 0``) — this pair is the
#: narrower of the two, so what this accepts the database accepts.
MIN_PROFILE_ROW_COUNT: Final[int] = 50
MAX_PROFILE_ROW_COUNT: Final[int] = 1_000

#: Design spec §3: "exactly two rows flagged as exercise events". Northline is
#: round one and Harbor is round two; that is the case, not an open question.
EXERCISE_EVENT_ROW_COUNT: Final[int] = 2

#: How many offending values a refusal sentence names before it stops counting
#: them out. A sentence that lists three hundred duplicates is not a sentence.
_MAX_NAMED_VALUES: Final[int] = 5

#: Where ``csv.DictReader`` puts cells past the end of the header.
_OVERFLOW_KEY: Final[str] = "__extra_cells__"


def parse_exercise_file(
    content: bytes | str,
    *,
    filename: str | None = None,
    layout: ExerciseFileLayout = PLACEHOLDER_LAYOUT,
) -> ParsedDataset | IngestRefusal:
    """Read an uploaded data file, or say in one sentence why it was refused.

    Args:
        content: The uploaded bytes. A ``str`` is accepted for callers that
            already hold text and is encoded as UTF-8 before anything else, so
            that the checksum is a checksum of bytes either way.
        filename: What the browser called the file, used only to recognise an
            XLSX by name. Never opened, never joined to a path.
        layout: PLACEHOLDER (OQ-CE-01). Defaults to :data:`PLACEHOLDER_LAYOUT`.

    Returns:
        A :class:`ParsedDataset` when every check of design spec §3 passed, or
        the first :class:`IngestRefusal` otherwise.
    """
    raw = content.encode("utf-8") if isinstance(content, str) else bytes(content)
    guard = _guard_upload(raw, filename=filename)
    if guard is not None:
        return guard
    decoded = _decode(raw)
    if isinstance(decoded, IngestRefusal):
        return decoded
    rows = _read_rows(decoded, layout)
    if isinstance(rows, IngestRefusal):
        return rows
    dataset = _build_dataset(rows, layout=layout, checksum=hashlib.sha256(raw).hexdigest())
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


# ---------------------------------------------------------------------------
# Guards that run before a single row is parsed
# ---------------------------------------------------------------------------

#: The first four bytes of every ZIP container, which is what an XLSX is.
_ZIP_MAGIC: Final[bytes] = b"PK\x03\x04"


def _guard_upload(raw: bytes, *, filename: str | None) -> IngestRefusal | None:
    """Size, format and NUL checks, in that order. ``None`` means "carry on"."""
    if len(raw) > MAX_UPLOAD_BYTES:
        return IngestRefusal(
            "file_too_large",
            f"The file is larger than {MAX_UPLOAD_BYTES // (1024 * 1024)} MB, "
            "which is much larger than a class data file; please check you "
            "picked the right file.",
        )
    if not raw.strip():
        return IngestRefusal("file_empty", "The file is empty.")
    name = (filename or "").strip().lower()
    if raw.startswith(_ZIP_MAGIC) or name.endswith((".xlsx", ".xlsm")):
        return IngestRefusal(
            "spreadsheet_not_csv",
            "This looks like an Excel workbook. Please save it as CSV "
            "(File, Save As, CSV UTF-8) and upload that file instead.",
        )
    if b"\x00" in raw:
        return IngestRefusal(
            "binary_content",
            "The file does not look like a CSV file; please upload the CSV "
            "export of the data file.",
        )
    return None


def _decode(raw: bytes) -> str | IngestRefusal:
    """UTF-8 with a tolerated byte-order mark, or a sentence about the encoding."""
    try:
        return raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        return IngestRefusal(
            "undecodable_text",
            "The file could not be read as text; please re-save it as CSV UTF-8 "
            "and upload it again.",
        )


# ---------------------------------------------------------------------------
# Reading the rows
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class _Sheet:
    """The header map and the data rows, once the CSV itself has been read."""

    #: Normalized header name to the spelling the file actually used.
    headers: Mapping[str, str]
    #: Each data row as the file gave it, paired with its line number.
    rows: tuple[tuple[int, Mapping[str, str]], ...]


def _read_rows(text: str, layout: ExerciseFileLayout) -> _Sheet | IngestRefusal:
    """Parse the CSV with a bounded field size, restoring the global limit.

    ``csv.field_size_limit`` is process-global: it is not a parser setting but
    a module one, so raising it for this call would raise it for every other
    caller in the process. It is therefore set defensively to a bounded value
    and restored in a ``finally``, and
    ``test_the_csv_field_size_limit_is_restored`` pins that.
    """
    previous = csv.field_size_limit()
    try:
        csv.field_size_limit(MAX_CELL_CHARACTERS * 8)
        reader = csv.DictReader(io.StringIO(text), restkey=_OVERFLOW_KEY, restval="")
        try:
            fieldnames = reader.fieldnames
            body = list(reader)
        except csv.Error:
            return IngestRefusal(
                "unreadable_csv",
                "The file could not be read as a CSV table; please check it "
                "opens as a spreadsheet and re-export it.",
            )
    finally:
        csv.field_size_limit(previous)
    headers = _header_map(fieldnames)
    if isinstance(headers, IngestRefusal):
        return headers
    missing = _missing_columns(headers, layout)
    if missing is not None:
        return missing
    return _collect_rows(headers, body)


def _header_map(fieldnames: Sequence[str] | None) -> Mapping[str, str] | IngestRefusal:
    """Normalized column name to the file's own spelling.

    Headers are compared through ``normalize_header``, so ``"Class Year"``,
    ``"class_year"`` and ``" CLASS-YEAR "`` are the same column — header text
    is presentation and never an identity, which is the rule the CBA import
    path already follows.
    """
    if not fieldnames:
        return IngestRefusal("no_header_row", "The file has no header row naming its columns.")
    if len(fieldnames) > MAX_COLUMN_COUNT:
        return IngestRefusal(
            "too_many_columns",
            f"The file has {len(fieldnames)} columns, which is more than this "
            f"page reads ({MAX_COLUMN_COUNT}).",
        )
    mapped: dict[str, str] = {}
    for name in fieldnames:
        key = normalize_header(name or "")
        if key and key in mapped:
            return IngestRefusal(
                "duplicate_column",
                f"The file has two columns named `{name.strip()}`; please leave "
                "one of them and upload it again.",
            )
        if key:
            mapped[key] = name
    return mapped


def _missing_columns(
    headers: Mapping[str, str], layout: ExerciseFileLayout
) -> IngestRefusal | None:
    """Design spec §3's first check, reporting every missing column at once.

    All of them in one sentence rather than one at a time: an instructor fixing
    a file five minutes before class should learn everything that is wrong with
    its header in one upload, and the spec's example sentence composes into a
    list without becoming a list of sentences.
    """
    missing = [
        column for column in layout.required_columns if normalize_header(column) not in headers
    ]
    if not missing:
        return None
    return IngestRefusal("missing_columns", _missing_columns_sentence(missing))


def _missing_columns_sentence(missing: Sequence[str]) -> str:
    """Design spec §3's example, verbatim for one column and extended for more."""
    if len(missing) == 1:
        return f"The file is missing the column `{missing[0]}`."
    listed = ", ".join(f"`{column}`" for column in missing)
    return f"The file is missing these columns: {listed}."


def _collect_rows(
    headers: Mapping[str, str], body: Sequence[Mapping[str, object]]
) -> _Sheet | IngestRefusal:
    """Bound the row count and every cell, and drop rows that are entirely blank."""
    if len(body) > MAX_DATA_ROW_COUNT:
        return IngestRefusal(
            "too_many_rows",
            f"The file has {len(body)} rows, which is more than this page reads "
            f"({MAX_DATA_ROW_COUNT}).",
        )
    kept: list[tuple[int, Mapping[str, str]]] = []
    for index, row in enumerate(body):
        line = index + 2
        if row.get(_OVERFLOW_KEY):
            return IngestRefusal(
                "ragged_row",
                f"Row {line} has more cells than the header has columns; please "
                "check the file for a stray comma and upload it again.",
            )
        cells = {key: _cell_text(value) for key, value in row.items() if key != _OVERFLOW_KEY}
        too_long = next((k for k, v in cells.items() if len(v) > MAX_CELL_CHARACTERS), None)
        if too_long is not None:
            return IngestRefusal(
                "cell_too_long",
                f"Row {line} has more than {MAX_CELL_CHARACTERS} characters in "
                f"the column `{too_long}`; please shorten it and upload again.",
            )
        if any(cells.values()):
            kept.append((line, cells))
    return _Sheet(headers=headers, rows=tuple(kept))


def _cell_text(value: object) -> str:
    """One cell as trimmed text. A missing cell and a blank one are both blank."""
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    return str(value).strip()


# ---------------------------------------------------------------------------
# Turning rows into profiles and events
# ---------------------------------------------------------------------------


def _get(sheet: _Sheet, row: Mapping[str, str], column: str) -> str:
    """One layout column out of one row, found through the normalized header."""
    return row.get(sheet.headers[normalize_header(column)], "")


def _build_dataset(
    sheet: _Sheet, *, layout: ExerciseFileLayout, checksum: str
) -> ParsedDataset | IngestRefusal:
    """Split the rows by kind, parse each, then run the cross-row checks."""
    split = _split_by_kind(sheet, layout)
    if isinstance(split, IngestRefusal):
        return split
    profile_rows, event_rows = split
    count = len(profile_rows)
    if count < MIN_PROFILE_ROW_COUNT or count > MAX_PROFILE_ROW_COUNT:
        return IngestRefusal(
            "row_count_out_of_range",
            f"The file has {count} profile rows; it needs between "
            f"{MIN_PROFILE_ROW_COUNT} and {MAX_PROFILE_ROW_COUNT}.",
        )
    profiles = _parse_profiles(sheet, profile_rows, layout)
    if isinstance(profiles, IngestRefusal):
        return profiles
    events = _parse_events(sheet, event_rows, layout)
    if isinstance(events, IngestRefusal):
        return events
    cross = _check_across_rows(profiles, events)
    if cross is not None:
        return cross
    return ParsedDataset(
        profiles=profiles,
        events=events,
        checksum=checksum,
        row_count=count,
        report=_build_report(profiles, events),
    )


def _split_by_kind(
    sheet: _Sheet, layout: ExerciseFileLayout
) -> (
    tuple[list[tuple[int, Mapping[str, str]]], list[tuple[int, Mapping[str, str]]]] | IngestRefusal
):
    """PLACEHOLDER (OQ-CE-01): one file, one discriminator column, two kinds."""
    profiles: list[tuple[int, Mapping[str, str]]] = []
    events: list[tuple[int, Mapping[str, str]]] = []
    for line, row in sheet.rows:
        kind = _get(sheet, row, layout.record_type_column).casefold()
        if kind == layout.profile_record_value.casefold():
            profiles.append((line, row))
        elif kind == layout.event_record_value.casefold():
            events.append((line, row))
        else:
            return IngestRefusal(
                "unknown_record_type",
                f"Row {line} has `{layout.record_type_column}` set to "
                f"`{kind or '(blank)'}`; every row must say either "
                f"`{layout.profile_record_value}` or `{layout.event_record_value}`.",
            )
    return profiles, events


def _parse_profiles(
    sheet: _Sheet, rows: Sequence[tuple[int, Mapping[str, str]]], layout: ExerciseFileLayout
) -> tuple[ParsedProfile, ...] | IngestRefusal:
    """One profile per row, refusing anything ``exercise_profile`` would refuse."""
    parsed: list[ParsedProfile] = []
    for line, row in rows:
        number = _positive_int(_get(sheet, row, layout.profile_no_column))
        if number is None:
            return IngestRefusal(
                "bad_profile_no",
                f"Row {line} has no whole number in the column `{layout.profile_no_column}`.",
            )
        name = _get(sheet, row, layout.display_name_column)
        if not name:
            return IngestRefusal(
                "missing_display_name",
                f"Row {line} has nothing in the column `{layout.display_name_column}`.",
            )
        card = _get(sheet, row, layout.stated_interests_column)
        parsed.append(
            ParsedProfile(
                profile_no=number,
                display_name=name,
                major=_get(sheet, row, layout.major_column) or None,
                class_year=_get(sheet, row, layout.class_year_column) or None,
                past_event_keys=_split_cell(
                    _get(sheet, row, layout.past_event_keys_column), layout
                ),
                stated_interests=_terms(card, layout) if card else None,
                career_goal=_get(sheet, row, layout.career_goal_column) or None,
                hidden_true_interests=_terms(
                    _get(sheet, row, layout.hidden_interests_column), layout
                ),
            )
        )
    return tuple(parsed)


def _parse_events(
    sheet: _Sheet, rows: Sequence[tuple[int, Mapping[str, str]]], layout: ExerciseFileLayout
) -> tuple[ParsedEvent, ...] | IngestRefusal:
    """One event per row, refusing anything ``exercise_event`` would refuse."""
    parsed: list[ParsedEvent] = []
    for line, row in rows:
        key = _get(sheet, row, layout.event_key_column)
        name = _get(sheet, row, layout.event_name_column)
        sequence = _positive_int(_get(sheet, row, layout.sequence_column))
        flag = _boolean(_get(sheet, row, layout.is_exercise_event_column), layout)
        blank = _first_blank({layout.event_key_column: key, layout.event_name_column: name})
        if blank is not None:
            return IngestRefusal(
                "missing_event_field",
                f"Row {line} has nothing in the column `{blank}`.",
            )
        if sequence is None:
            return IngestRefusal(
                "bad_event_sequence",
                f"Row {line} has no whole number in the column `{layout.sequence_column}`.",
            )
        if flag is None:
            return IngestRefusal(
                "bad_event_flag",
                f"Row {line} has a value in the column "
                f"`{layout.is_exercise_event_column}` that is neither yes nor no.",
            )
        parsed.append(
            ParsedEvent(
                event_key=key,
                name=name,
                topic_tags=_terms(_get(sheet, row, layout.topic_tags_column), layout),
                # Split, not folded: a major is stored as written on
                # ``exercise_profile.major`` too, and folding one side of a
                # comparison but not the other is how "Data Science" stops
                # matching "data science" later.
                target_majors=_split_cell(_get(sheet, row, layout.target_majors_column), layout),
                is_exercise_event=flag,
                sequence=sequence,
            )
        )
    return tuple(parsed)


def _first_blank(fields: Mapping[str, str]) -> str | None:
    """The first named field that is empty, or ``None`` when all are filled."""
    return next((column for column, value in fields.items() if not value), None)


def _positive_int(text: str) -> int | None:
    """A whole number of at least one, or ``None`` for anything else."""
    try:
        value = int(text)
    except ValueError:
        return None
    return value if value >= 1 else None


def _boolean(text: str, layout: ExerciseFileLayout) -> bool | None:
    """A yes or a no out of a cell, or ``None`` when it is neither.

    ``None`` rather than a default: a cell nobody can read as yes or no is not
    evidence that the answer is no, and guessing here would silently decide
    which two events the teams run.
    """
    folded = text.casefold()
    if folded in {value.casefold() for value in layout.true_values}:
        return True
    if folded in {value.casefold() for value in layout.false_values}:
        return False
    return None


def _split_cell(text: str, layout: ExerciseFileLayout) -> tuple[str, ...]:
    """A list cell into its entries, trimmed, blanks dropped, order kept."""
    if not text:
        return ()
    return tuple(part.strip() for part in text.split(layout.list_cell_separator) if part.strip())


def _terms(text: str, layout: ExerciseFileLayout) -> tuple[str, ...]:
    """A list cell as normalized terms — folded for comparison, never mapped.

    ``normalize_tag_value`` is the repository's existing fold (case, whitespace
    and punctuation), reused rather than restated so that an exercise term and
    a CBA tag compare the same way. No term is looked up in a vocabulary and no
    term is dropped: the G3 mapping design spec §3 mentions is OQ-CE-01 and a
    gated area, so this module counts instead (ADR-0011).
    """
    seen: dict[str, None] = {}
    for entry in _split_cell(text, layout):
        seen.setdefault(normalize_tag_value(entry), None)
    return tuple(seen)


# ---------------------------------------------------------------------------
# Checks that need every row
# ---------------------------------------------------------------------------


def _check_across_rows(
    profiles: Sequence[ParsedProfile], events: Sequence[ParsedEvent]
) -> IngestRefusal | None:
    """Design spec §3's remaining checks, in the order the spec lists them."""
    flagged = sum(1 for event in events if event.is_exercise_event)
    if flagged != EXERCISE_EVENT_ROW_COUNT:
        return IngestRefusal(
            "wrong_exercise_event_count",
            f"The file flags {flagged} rows as exercise events; it needs exactly "
            f"{EXERCISE_EVENT_ROW_COUNT}, one for each round.",
        )
    duplicates = _duplicates([str(profile.profile_no) for profile in profiles])
    if duplicates:
        return IngestRefusal(
            "duplicate_profile_no",
            f"Two or more profiles share the same number: {_listed(duplicates)}.",
        )
    duplicate_keys = _duplicates([event.event_key for event in events])
    if duplicate_keys:
        return IngestRefusal(
            "duplicate_event_key",
            f"Two or more events share the same key: {_listed(duplicate_keys)}.",
        )
    duplicate_sequences = _duplicates([str(event.sequence) for event in events])
    if duplicate_sequences:
        return IngestRefusal(
            "duplicate_event_sequence",
            f"Two or more events share the same position: {_listed(duplicate_sequences)}.",
        )
    return _check_past_event_keys(profiles, events)


def _check_past_event_keys(
    profiles: Sequence[ParsedProfile], events: Sequence[ParsedEvent]
) -> IngestRefusal | None:
    """Every attended event must be an event in the file.

    Refused rather than trimmed. ADR-0011's rule is that nothing is silently
    dropped, and quietly discarding an attendance would change who "went to
    similar events before" without telling anybody — a wrong ranked list that
    looks right. The sentence names the keys and how many rows used them.
    """
    known = {event.event_key for event in events}
    counts: dict[str, int] = {}
    for profile in profiles:
        for key in profile.past_event_keys:
            if key not in known:
                counts[key] = counts.get(key, 0) + 1
    if not counts:
        return None
    named = sorted(counts.items(), key=lambda item: (-item[1], item[0]))[:_MAX_NAMED_VALUES]
    listed = ", ".join(f"`{key}` ({used} rows)" for key, used in named)
    return IngestRefusal(
        "unknown_past_event_key",
        f"Some profiles list past events that are not in the file: {listed}."
        + (f" and {len(counts) - len(named)} more." if len(counts) > len(named) else ""),
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
    """A few values in backticks, with a count of whatever did not fit."""
    shown = ", ".join(f"`{value}`" for value in values[:_MAX_NAMED_VALUES])
    remaining = len(values) - _MAX_NAMED_VALUES
    return f"{shown} and {remaining} more" if remaining > 0 else shown


def _build_report(profiles: Sequence[ParsedProfile], events: Sequence[ParsedEvent]) -> IngestReport:
    """Counts only. Nothing here reads ``hidden_true_interests`` (ADR-0025 D6)."""
    years = sorted({profile.class_year for profile in profiles if profile.class_year})
    interests = {term for p in profiles for term in (p.stated_interests or ())}
    topics = {term for event in events for term in event.topic_tags}
    return IngestReport(
        profile_count=len(profiles),
        event_count=len(events),
        exercise_event_count=sum(1 for event in events if event.is_exercise_event),
        distinct_class_years=tuple(years),
        profiles_missing_major=sum(1 for p in profiles if p.major is None),
        profiles_missing_class_year=sum(1 for p in profiles if p.class_year is None),
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
