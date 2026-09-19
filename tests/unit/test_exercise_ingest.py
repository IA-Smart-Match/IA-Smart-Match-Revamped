"""The class-exercise data-file parser: what it accepts, and what it says.

Every row built here is **fictional and obviously so** — names read
``Fictional Profile 007`` and events read ``past-03``. The requirements are
explicit that no real student data appears in this product, "even with names
changed", and a test fixture is not an exemption from that.

The file under test is ``smartmatch_domain/exercise/ingest.py``. These tests
assert three kinds of thing:

* that each check of design spec §3 happens, in the spec's order, and produces
  one sentence an instructor can act on;
* that ADR-0025 D6's withheld column reaches :class:`ParsedProfile` and reaches
  nothing else — asserted by walking a corpus of bad files as well as a good
  one, because a leak through an error message is the leak nobody looks for;
* that the checksum is a checksum of the uploaded bytes and does not move.
"""

from __future__ import annotations

import csv
import dataclasses
import hashlib
import io
import logging
from collections.abc import Mapping, Sequence

import pytest
from smartmatch_domain.exercise.ingest import (
    EXERCISE_EVENT_ROW_COUNT,
    MAX_CELL_CHARACTERS,
    MAX_UPLOAD_BYTES,
    MIN_PROFILE_ROW_COUNT,
    PLACEHOLDER_LAYOUT,
    ExerciseFileLayout,
    IngestRefusal,
    ParsedDataset,
    parse_exercise_file,
)

LAYOUT = PLACEHOLDER_LAYOUT

#: A made-up interest vocabulary. PLACEHOLDER (OQ-CE-01): the real one is
#: Ann's, and no test here treats this list as the vocabulary — it is only
#: text to put in a cell.
FICTIONAL_INTERESTS = ("data analytics", "brand strategy", "sports marketing")

#: The ten past events and the two rounds, by key. Names are the case's.
PAST_EVENT_KEYS = tuple(f"past-{index:02d}" for index in range(1, 11))
ROUND_EVENT_KEYS = ("northline", "harbor")


def _profile_row(number: int, **overrides: str) -> dict[str, str]:
    """One fictional profile row, in the placeholder layout."""
    row = {
        LAYOUT.record_type_column: LAYOUT.profile_record_value,
        LAYOUT.profile_no_column: str(number),
        LAYOUT.display_name_column: f"Fictional Profile {number:03d}",
        LAYOUT.major_column: "Marketing",
        LAYOUT.class_year_column: "Junior",
        LAYOUT.past_event_keys_column: PAST_EVENT_KEYS[number % 10] if number % 3 == 0 else "",
        LAYOUT.stated_interests_column: (
            LAYOUT.list_cell_separator.join(FICTIONAL_INTERESTS[:2]) if number % 5 == 0 else ""
        ),
        LAYOUT.career_goal_column: "Brand manager" if number % 5 == 0 else "",
        LAYOUT.hidden_interests_column: f"secret-interest-{number:03d}",
    }
    row.update(overrides)
    return row


def _event_row(
    key: str, sequence: int, *, is_exercise: bool = False, **overrides: str
) -> dict[str, str]:
    """One fictional event row, in the placeholder layout."""
    row = {
        LAYOUT.record_type_column: LAYOUT.event_record_value,
        LAYOUT.event_key_column: key,
        LAYOUT.event_name_column: f"Fictional Event {key}",
        LAYOUT.topic_tags_column: LAYOUT.list_cell_separator.join(FICTIONAL_INTERESTS[:2]),
        LAYOUT.target_majors_column: "Marketing",
        LAYOUT.is_exercise_event_column: "true" if is_exercise else "false",
        LAYOUT.sequence_column: str(sequence),
    }
    row.update(overrides)
    return row


def _event_rows() -> list[dict[str, str]]:
    """Ten past events, then Northline (round one) and Harbor (round two)."""
    rows = [_event_row(key, index + 1) for index, key in enumerate(PAST_EVENT_KEYS)]
    rows += [
        _event_row(key, 11 + index, is_exercise=True) for index, key in enumerate(ROUND_EVENT_KEYS)
    ]
    return rows


def _build_file(
    rows: Sequence[Mapping[str, str]],
    *,
    columns: Sequence[str] | None = None,
    prefix: str = "",
) -> bytes:
    """Render rows as CSV bytes, the way a browser would upload them."""
    header = list(columns if columns is not None else LAYOUT.required_columns)
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=header, extrasaction="ignore")
    writer.writeheader()
    for row in rows:
        writer.writerow({column: row.get(column, "") for column in header})
    return (prefix + buffer.getvalue()).encode("utf-8")


def _good_rows(profile_count: int = MIN_PROFILE_ROW_COUNT + 10) -> list[dict[str, str]]:
    """A file that passes every check: profiles first, then the twelve events."""
    return [_profile_row(number) for number in range(1, profile_count + 1)] + _event_rows()


def _good_file(profile_count: int = MIN_PROFILE_ROW_COUNT + 10) -> bytes:
    return _build_file(_good_rows(profile_count))


def _accepted(content: bytes) -> ParsedDataset:
    """Parse, and fail the test with the sentence if the file was refused."""
    result = parse_exercise_file(content, filename="placeholder.csv")
    assert isinstance(result, ParsedDataset), getattr(result, "message", result)
    return result


def _refusal(content: bytes, *, filename: str = "placeholder.csv") -> IngestRefusal:
    result = parse_exercise_file(content, filename=filename)
    assert isinstance(result, IngestRefusal), "expected a refusal"
    return result


# ---------------------------------------------------------------------------
# The happy path
# ---------------------------------------------------------------------------


def test_a_well_formed_file_is_parsed_into_profiles_and_events() -> None:
    dataset = _accepted(_good_file())

    assert dataset.row_count == MIN_PROFILE_ROW_COUNT + 10
    assert len(dataset.profiles) == MIN_PROFILE_ROW_COUNT + 10
    assert len(dataset.events) == 12
    assert dataset.report.exercise_event_count == EXERCISE_EVENT_ROW_COUNT
    assert dataset.profiles[0].display_name == "Fictional Profile 001"


def test_an_empty_interest_cell_is_no_card_rather_than_an_empty_card() -> None:
    """Design spec §7's three states, as the two the file can express."""
    dataset = _accepted(_good_file())

    without_card = [p for p in dataset.profiles if p.profile_no % 5 != 0]
    with_card = [p for p in dataset.profiles if p.profile_no % 5 == 0]
    assert all(profile.stated_interests is None for profile in without_card)
    assert all(
        profile.stated_interests == ("data analytics", "brand strategy") for profile in with_card
    )


def test_the_report_counts_the_three_how_much_we_know_markers() -> None:
    dataset = _accepted(_good_file())
    markers = dataset.report.markers

    assert markers.completed_card == dataset.report.profile_count - sum(
        (markers.major_only, markers.major_plus_events)
    )
    assert markers.completed_card == sum(
        1 for profile in dataset.profiles if profile.stated_interests is not None
    )


def test_the_report_names_the_class_year_values_instead_of_a_vocabulary() -> None:
    """PLACEHOLDER (OQ-CE-01): no vocabulary is closed here, so it is reported."""
    rows = _good_rows()
    rows[0][LAYOUT.class_year_column] = "Senior"
    rows[1][LAYOUT.class_year_column] = ""

    dataset = _accepted(_build_file(rows))

    assert dataset.report.distinct_class_years == ("Junior", "Senior")
    assert dataset.report.profiles_missing_class_year == 1


def test_interest_terms_are_counted_and_never_dropped() -> None:
    """ADR-0011: counted, never silently dropped. Nothing is mapped to G3."""
    rows = _good_rows()
    rows[4][LAYOUT.stated_interests_column] = "Esports Marketing; data analytics"

    dataset = _accepted(_build_file(rows))

    assert dataset.report.distinct_stated_interest_terms >= 3
    assert len(dataset.profiles) == len(rows) - 12
    assert dataset.profiles[4].stated_interests == ("esports marketing", "data analytics")


def test_a_byte_order_mark_is_tolerated() -> None:
    dataset = _accepted("﻿".encode() + _good_file())

    assert dataset.profiles[0].profile_no == 1


def test_header_spelling_is_presentation_rather_than_identity() -> None:
    renamed = [column.replace("_", " ").title() for column in LAYOUT.required_columns]
    rows = [
        {
            renamed[index]: row.get(column, "")
            for index, column in enumerate(LAYOUT.required_columns)
        }
        for row in _good_rows()
    ]

    dataset = _accepted(_build_file(rows, columns=renamed))

    assert dataset.report.profile_count == MIN_PROFILE_ROW_COUNT + 10


# ---------------------------------------------------------------------------
# The refusals, in design spec §3's order
# ---------------------------------------------------------------------------


def test_a_missing_column_is_reported_in_the_specs_own_sentence() -> None:
    columns = [c for c in LAYOUT.required_columns if c != LAYOUT.major_column]

    refusal = _refusal(_build_file(_good_rows(), columns=columns))

    assert refusal.code == "missing_columns"
    assert refusal.message == "The file is missing the column `major`."


def test_every_missing_column_is_named_in_one_sentence() -> None:
    dropped = {LAYOUT.major_column, LAYOUT.class_year_column}
    columns = [c for c in LAYOUT.required_columns if c not in dropped]

    refusal = _refusal(_build_file(_good_rows(), columns=columns))

    assert refusal.code == "missing_columns"
    assert "`major`" in refusal.message
    assert "`class_year`" in refusal.message


@pytest.mark.parametrize("profile_count", [MIN_PROFILE_ROW_COUNT - 1, 0])
def test_a_file_outside_the_row_count_range_is_refused(profile_count: int) -> None:
    refusal = _refusal(_build_file(_good_rows(profile_count) if profile_count else _event_rows()))

    assert refusal.code == "row_count_out_of_range"
    assert str(MIN_PROFILE_ROW_COUNT) in refusal.message


def test_a_file_with_more_than_a_thousand_profiles_is_refused() -> None:
    refusal = _refusal(_build_file(_good_rows(1_001)))

    assert refusal.code == "row_count_out_of_range"
    assert "1000" in refusal.message


@pytest.mark.parametrize("flagged", [1, 3])
def test_exactly_two_rows_must_be_flagged_as_exercise_events(flagged: int) -> None:
    rows = _good_rows()
    for index, row in enumerate(rows):
        if row[LAYOUT.record_type_column] == LAYOUT.event_record_value:
            row[LAYOUT.is_exercise_event_column] = "true" if index % 2 == 0 else "false"
    events = [r for r in rows if r[LAYOUT.record_type_column] == LAYOUT.event_record_value]
    for index, row in enumerate(events):
        row[LAYOUT.is_exercise_event_column] = "true" if index < flagged else "false"

    refusal = _refusal(_build_file(rows))

    assert refusal.code == "wrong_exercise_event_count"
    assert str(flagged) in refusal.message


def test_a_duplicate_profile_number_is_named() -> None:
    rows = _good_rows()
    rows[3][LAYOUT.profile_no_column] = rows[2][LAYOUT.profile_no_column]

    refusal = _refusal(_build_file(rows))

    assert refusal.code == "duplicate_profile_no"
    assert f"`{rows[2][LAYOUT.profile_no_column]}`" in refusal.message


def test_a_duplicate_event_key_is_named() -> None:
    rows = _good_rows()
    events = [r for r in rows if r[LAYOUT.record_type_column] == LAYOUT.event_record_value]
    events[1][LAYOUT.event_key_column] = events[0][LAYOUT.event_key_column]

    refusal = _refusal(_build_file(rows))

    assert refusal.code == "duplicate_event_key"
    assert "`past-01`" in refusal.message


def test_two_events_may_not_claim_the_same_position() -> None:
    rows = _good_rows()
    events = [r for r in rows if r[LAYOUT.record_type_column] == LAYOUT.event_record_value]
    events[1][LAYOUT.sequence_column] = events[0][LAYOUT.sequence_column]

    refusal = _refusal(_build_file(rows))

    assert refusal.code == "duplicate_event_sequence"


def test_an_attended_event_that_is_not_in_the_file_is_refused_not_dropped() -> None:
    """ADR-0011: never silently dropped, so the whole file is refused."""
    rows = _good_rows()
    rows[2][LAYOUT.past_event_keys_column] = "career-fair-2019"
    rows[5][LAYOUT.past_event_keys_column] = "career-fair-2019"

    refusal = _refusal(_build_file(rows))

    assert refusal.code == "unknown_past_event_key"
    assert "`career-fair-2019` (2 rows)" in refusal.message


def test_a_row_that_says_it_is_neither_kind_is_refused() -> None:
    rows = _good_rows()
    rows[7][LAYOUT.record_type_column] = "teacher"

    refusal = _refusal(_build_file(rows))

    assert refusal.code == "unknown_record_type"
    assert "Row 9" in refusal.message


def test_a_profile_with_no_name_is_refused_as_the_database_would() -> None:
    rows = _good_rows()
    rows[0][LAYOUT.display_name_column] = "   "

    refusal = _refusal(_build_file(rows))

    assert refusal.code == "missing_display_name"


def test_a_profile_number_that_is_not_a_whole_number_is_refused() -> None:
    rows = _good_rows()
    rows[0][LAYOUT.profile_no_column] = "one"

    refusal = _refusal(_build_file(rows))

    assert refusal.code == "bad_profile_no"


def test_an_unreadable_exercise_event_flag_is_refused_rather_than_guessed() -> None:
    rows = _good_rows()
    events = [r for r in rows if r[LAYOUT.record_type_column] == LAYOUT.event_record_value]
    events[0][LAYOUT.is_exercise_event_column] = "maybe"

    refusal = _refusal(_build_file(rows))

    assert refusal.code == "bad_event_flag"


# ---------------------------------------------------------------------------
# Untrusted input
# ---------------------------------------------------------------------------


def test_an_xlsx_upload_asks_for_a_csv_export() -> None:
    """PLACEHOLDER (OQ-CE-05): openpyxl is not a dependency and is not used."""
    refusal = _refusal(b"PK\x03\x04" + b"\x00" * 64, filename="ann-data.xlsx")

    assert refusal.code == "spreadsheet_not_csv"
    assert "CSV" in refusal.message


def test_a_workbook_renamed_to_csv_is_still_recognised_by_its_bytes() -> None:
    refusal = _refusal(b"PK\x03\x04" + b"rest of a workbook", filename="ann-data.csv")

    assert refusal.code == "spreadsheet_not_csv"


def test_a_file_over_the_byte_cap_is_refused_before_it_is_decoded() -> None:
    refusal = _refusal(b"a" * (MAX_UPLOAD_BYTES + 1))

    assert refusal.code == "file_too_large"


def test_a_file_containing_nul_bytes_is_refused() -> None:
    refusal = _refusal(_good_file().replace(b"Marketing", b"Mark\x00ting", 1))

    assert refusal.code == "binary_content"


def test_an_overlong_cell_is_refused() -> None:
    rows = _good_rows()
    rows[0][LAYOUT.career_goal_column] = "x" * (MAX_CELL_CHARACTERS + 1)

    refusal = _refusal(_build_file(rows))

    assert refusal.code == "cell_too_long"


def test_undecodable_bytes_are_refused_with_a_sentence() -> None:
    refusal = _refusal(b"record_type,profile_no\n\xff\xfe\xfa,1\n")

    assert refusal.code == "undecodable_text"


def test_an_empty_upload_is_refused() -> None:
    assert _refusal(b"   \n").code == "file_empty"


def test_a_leading_equals_sign_is_data_and_is_never_evaluated() -> None:
    """CSV injection is the download track's problem (§8), not this one's."""
    rows = _good_rows()
    rows[0][LAYOUT.career_goal_column] = "=2+2"

    dataset = _accepted(_build_file(rows))

    assert dataset.profiles[0].career_goal == "=2+2"


def test_the_csv_field_size_limit_is_restored() -> None:
    before = csv.field_size_limit()

    parse_exercise_file(_good_file())
    parse_exercise_file(b"PK\x03\x04")

    assert csv.field_size_limit() == before


# ---------------------------------------------------------------------------
# ADR-0025 D6 — the withheld column
# ---------------------------------------------------------------------------

#: The marker every fictional row puts in the withheld cell. Distinctive on
#: purpose: a substring search for it is the whole test.
_WITHHELD_MARKER = "secret-interest-"


def test_the_withheld_column_reaches_the_profile_and_nothing_else() -> None:
    dataset = _accepted(_good_file())

    assert dataset.profiles[0].hidden_true_interests == ("secret interest 001",)
    assert _WITHHELD_MARKER not in repr(dataset.report)
    assert "hidden" not in repr(dataset.report)
    assert not any("hidden" in field.name for field in dataclasses.fields(dataset.report))


def _corpus_of_bad_files() -> list[bytes]:
    """One file per refusal path, each carrying the withheld marker."""
    variants: list[list[dict[str, str]]] = []
    for mutate in (
        lambda rows: rows[0].update({LAYOUT.display_name_column: ""}),
        lambda rows: rows[0].update({LAYOUT.profile_no_column: "zero"}),
        lambda rows: rows[3].update({LAYOUT.profile_no_column: rows[2][LAYOUT.profile_no_column]}),
        lambda rows: rows[2].update({LAYOUT.past_event_keys_column: "not-an-event"}),
        lambda rows: rows[7].update({LAYOUT.record_type_column: "something-else"}),
        lambda rows: rows[0].update({LAYOUT.career_goal_column: "y" * 900}),
    ):
        rows = _good_rows()
        mutate(rows)
        variants.append(rows)
    files = [_build_file(rows) for rows in variants]
    files.append(_build_file(_good_rows(3)))
    files.append(
        _build_file(
            _good_rows(),
            columns=[c for c in LAYOUT.required_columns if c != LAYOUT.major_column],
        )
    )
    return files


def test_no_refusal_sentence_ever_quotes_the_withheld_column() -> None:
    for content in _corpus_of_bad_files():
        refusal = _refusal(content)
        assert _WITHHELD_MARKER not in refusal.message, refusal
        assert LAYOUT.hidden_interests_column not in refusal.message, refusal


def test_the_log_records_counts_and_no_content(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.INFO, logger="smartmatch_domain.exercise.ingest"):
        _accepted(_good_file())
        _refusal(_build_file(_good_rows(3)))

    logged = "\n".join(record.getMessage() for record in caplog.records)
    assert "profiles=60" in logged
    assert "row_count_out_of_range" in logged
    assert _WITHHELD_MARKER not in logged
    assert "Fictional Profile" not in logged


# ---------------------------------------------------------------------------
# The checksum
# ---------------------------------------------------------------------------


def test_the_checksum_is_stable_for_the_same_bytes() -> None:
    content = _good_file()

    first = _accepted(content)
    second = _accepted(content)

    assert first.checksum == second.checksum
    assert len(first.checksum) == 64
    assert first.checksum == hashlib.sha256(content).hexdigest()


def test_the_checksum_is_of_the_uploaded_bytes_not_the_parsed_rows() -> None:
    content = _good_file()
    with_trailing_newline = content + b"\n"

    assert _accepted(content).checksum != _accepted(with_trailing_newline).checksum


def test_text_and_bytes_of_the_same_file_agree() -> None:
    content = _good_file()

    assert _accepted(content).checksum == _accepted(content.decode("utf-8").encode()).checksum


# ---------------------------------------------------------------------------
# The layout is the placeholder, and it is replaceable
# ---------------------------------------------------------------------------


def test_the_placeholder_marker_is_literally_present() -> None:
    """OQ-CE-01 is open; the module must say so where a reader will look."""
    from smartmatch_domain.exercise import ingest

    assert "PLACEHOLDER (OQ-CE-01)" in (ingest.__doc__ or "")
    assert "PLACEHOLDER (OQ-CE-05)" in (ingest.__doc__ or "")
    assert "PLACEHOLDER (OQ-CE-01)" in (ExerciseFileLayout.__doc__ or "")


def test_closing_the_open_question_is_one_object_and_no_parser_edit() -> None:
    """Ann's column names arrive as a different layout, not a different parser."""
    renamed = dataclasses.replace(
        LAYOUT,
        major_column="Field of Study",
        class_year_column="Year in School",
        list_cell_separator="|",
    )
    rows = _good_rows()
    for row in rows:
        if LAYOUT.major_column in row:
            row["Field of Study"] = row.pop(LAYOUT.major_column)
            row["Year in School"] = row.pop(LAYOUT.class_year_column)
            row[LAYOUT.stated_interests_column] = row[LAYOUT.stated_interests_column].replace(
                ";", "|"
            )
            row[LAYOUT.past_event_keys_column] = row[LAYOUT.past_event_keys_column].replace(
                ";", "|"
            )
        else:
            row["Field of Study"] = ""
            row["Year in School"] = ""
            row[LAYOUT.topic_tags_column] = row[LAYOUT.topic_tags_column].replace(";", "|")

    result = parse_exercise_file(
        _build_file(rows, columns=renamed.required_columns), layout=renamed
    )

    assert isinstance(result, ParsedDataset), getattr(result, "message", result)
    assert result.report.distinct_class_years == ("Junior",)


def test_no_function_in_the_parser_writes_a_column_name_down() -> None:
    """Every name lives on the layout, which is what makes OQ-CE-01 cheap.

    Walked with :mod:`ast` rather than searched as text, so that the module's
    own prose — which necessarily quotes ``class_year`` to explain why it has
    no vocabulary — is not mistaken for a parser that hard-codes it. Docstrings
    are skipped; every other string literal inside a function is checked.
    """
    import ast
    from pathlib import Path

    from smartmatch_domain.exercise import ingest

    names = {
        getattr(LAYOUT, field.name)
        for field in dataclasses.fields(LAYOUT)
        if field.name.endswith("_column")
    }
    tree = ast.parse(Path(ingest.__file__).read_text(encoding="utf-8"))
    offenders = [
        (node.name, literal.value)
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef)
        for statement in (node.body[1:] if ast.get_docstring(node) else node.body)
        for literal in ast.walk(statement)
        if isinstance(literal, ast.Constant)
        and isinstance(literal.value, str)
        and literal.value in names
    ]

    assert offenders == []
