"""The class-exercise data-file parser: the ``event_description`` column.

Split out of ``test_exercise_ingest.py`` to keep that file under the size
ceiling. Two things are asserted here: the description column's own length
limit (#325), and how the description is read (#318).
"""

from __future__ import annotations

from smartmatch_domain.exercise.ingest import IngestRefusal, ParsedDataset, parse_exercise_file
from smartmatch_domain.exercise.layout import EVENT_DESCRIPTION_MAX_CHARACTERS
from smartmatch_domain.exercise.workbook import MAX_CELL_CHARACTERS

from tests.unit.exercise_workbooks import (
    EVENT_HEADINGS,
    EVENT_HEADINGS_WITH_DESCRIPTION,
    LAYOUT,
    PROFILE_HEADINGS,
    event_rows,
    good_profile_rows,
    good_workbook,
    workbook_bytes,
)


def _accepted(content: bytes) -> ParsedDataset:
    result = parse_exercise_file(content, layout=LAYOUT)
    assert isinstance(result, ParsedDataset), result
    return result


def _refusal(content: bytes) -> IngestRefusal:
    result = parse_exercise_file(content)
    assert isinstance(result, IngestRefusal), result
    return result


def _with_event(index: int, **overrides: object) -> bytes:
    events = event_rows()
    events[index].update(overrides)
    return workbook_bytes(good_profile_rows(), events)


def _with_described_event(index: int, **overrides: object) -> bytes:
    """As :func:`_with_event`, on a sheet that carries the description column."""
    events = event_rows()
    events[index].update(overrides)
    return workbook_bytes(
        good_profile_rows(), events, event_headings=EVENT_HEADINGS_WITH_DESCRIPTION
    )


# ---------------------------------------------------------------------------
# The description column's own length limit (#325)
# ---------------------------------------------------------------------------


def test_a_description_may_be_as_long_as_its_own_limit() -> None:
    text = "d" * EVENT_DESCRIPTION_MAX_CHARACTERS

    _accepted(_with_described_event(10, **{LAYOUT.event_description_column: text}))


def test_a_description_past_its_limit_is_refused_and_the_sentence_says_the_limit() -> None:
    text = "d" * (EVENT_DESCRIPTION_MAX_CHARACTERS + 1)

    refusal = _refusal(_with_described_event(10, **{LAYOUT.event_description_column: text}))

    assert refusal.code == "cell_too_long"
    assert refusal.message == (
        "Row 12 of the `Events` sheet has more than 2000 characters in the column "
        "`event_description`; please shorten it and upload again."
    )


def test_a_long_cell_in_any_other_events_column_is_still_refused() -> None:
    name = "n" * (MAX_CELL_CHARACTERS + 1)

    refusal = _refusal(_with_described_event(10, **{LAYOUT.event_name_column: name}))

    assert refusal.code == "cell_too_long"
    assert "more than 500 characters in the column `event_name`" in refusal.message


def test_a_long_cell_in_a_column_the_parser_does_not_read_is_still_refused() -> None:
    refusal = _refusal(_with_event(0, event_date="9" * (MAX_CELL_CHARACTERS + 1)))

    assert refusal.code == "cell_too_long"
    assert "more than 500 characters in the column `event_date`" in refusal.message


def test_the_longer_limit_does_not_reach_a_profiles_column_of_the_same_name() -> None:
    headings = (*PROFILE_HEADINGS, LAYOUT.event_description_column)
    rows = good_profile_rows()
    rows[0][LAYOUT.event_description_column] = "d" * (MAX_CELL_CHARACTERS + 1)

    refusal = _refusal(workbook_bytes(rows, event_rows(), profile_headings=headings))

    assert refusal.code == "cell_too_long"
    assert "`Profiles` sheet has more than 500 characters" in refusal.message


# ---------------------------------------------------------------------------
# Reading the description (#318)
# ---------------------------------------------------------------------------

_BLURB = "A fictional sixty-minute talk about a made-up company. Snacks provided."


def test_an_events_description_is_read_as_the_file_wrote_it() -> None:
    dataset = _accepted(_with_described_event(10, **{LAYOUT.event_description_column: _BLURB}))

    assert dataset.events[10].description == _BLURB


def test_a_blank_description_is_no_description() -> None:
    dataset = _accepted(_with_described_event(10, **{LAYOUT.event_description_column: "   "}))

    assert [event.description for event in dataset.events] == [None] * 12


def test_a_file_without_the_description_column_is_accepted_with_no_descriptions() -> None:
    """The column is optional: every file Ann sent before 2026-10-02 lacks it."""
    assert LAYOUT.event_description_column not in EVENT_HEADINGS

    dataset = _accepted(good_workbook())

    assert [event.description for event in dataset.events] == [None] * 12


def test_a_description_is_free_text_and_is_not_checked_against_a_vocabulary() -> None:
    text = "Basket weaving; `quoted`; =SUM(A1); 100% made up."

    dataset = _accepted(_with_described_event(11, **{LAYOUT.event_description_column: text}))

    assert dataset.events[11].description == text


def test_the_description_is_not_a_withheld_column() -> None:
    """It is the public paragraph, shown to teams; only the two pink columns are withheld."""
    assert LAYOUT.event_description_column not in LAYOUT.withheld_columns
