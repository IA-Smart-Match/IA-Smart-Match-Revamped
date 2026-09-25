"""Build class-exercise workbooks in memory, shaped like Ann's, for tests.

Every row built here is **fictional and obviously so** — names read
``Fictional`` / ``Profile 007`` and event names read ``Past event 03``. The
requirements are explicit that no real student data appears in this product,
"even with names changed", and a test fixture is not an exemption from that.

Values come from the closed vocabularies, because the parser refuses anything
else. One topic and one career goal are reserved for the withheld columns —
:data:`WITHHELD_TOPIC` and :data:`WITHHELD_GOAL` appear in no other cell of a
workbook built here — so a test can search any output for them and a hit can
only be a leak.

Ann's own two files are committed beside this module's callers under
``tests/fixtures/exercise/`` and are what the golden tests read.
"""

from __future__ import annotations

import io
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Final

from openpyxl import Workbook
from smartmatch_domain.exercise.layout import EXERCISE_LAYOUT as LAYOUT

__all__ = [
    "ANN_FULL_FILE",
    "ANN_SAMPLE_FILE",
    "EVENT_HEADINGS",
    "LAYOUT",
    "PROFILE_HEADINGS",
    "WITHHELD_GOAL",
    "WITHHELD_TOPIC",
    "event_rows",
    "good_profile_rows",
    "good_workbook",
    "profile_row",
    "workbook_bytes",
]

_FIXTURES: Final[Path] = Path(__file__).resolve().parents[1] / "fixtures" / "exercise"

#: Ann's full file and her 20-row sample, as she sent them on 2026-09-24.
ANN_FULL_FILE: Final[Path] = _FIXTURES / "SmartMatch_Student_Body_300.xlsx"
ANN_SAMPLE_FILE: Final[Path] = _FIXTURES / "SmartMatch_Student_Body_Sample_20.xlsx"

#: Reserved for the withheld columns; in no other cell of a built workbook.
WITHHELD_TOPIC: Final[str] = "Healthcare administration"
WITHHELD_GOAL: Final[str] = "Healthcare administration role"

#: Ann's Profiles headings, including the two the parser does not read.
PROFILE_HEADINGS: Final[tuple[str, ...]] = (
    *LAYOUT.profile_columns[:6],
    "events_attended_count",
    *LAYOUT.profile_columns[6:9],
    "info_level",
    *LAYOUT.profile_columns[9:],
)

#: Ann's Events headings, including the two the parser does not read.
EVENT_HEADINGS: Final[tuple[str, ...]] = (
    LAYOUT.event_key_column,
    LAYOUT.event_name_column,
    "event_type",
    "event_date",
    LAYOUT.topic_tags_column,
    LAYOUT.target_majors_column,
    LAYOUT.is_exercise_event_column,
    LAYOUT.seats_column,
)

_MAJORS: Final[tuple[str, ...]] = (
    "Accounting",
    "Computer Information Systems",
    "Finance, Real Estate & Law",
    "International Business & Marketing",
    "Management & Human Resources",
    "Technology & Operations Management",
)
_YEARS: Final[tuple[str, ...]] = ("Freshman", "Sophomore", "Junior", "Senior")
_CARD_TOPICS: Final[tuple[str, ...]] = (
    "Technology / information systems",
    "Retail / consumer goods",
    "Sales / business development",
)


def workbook_bytes(
    profiles: Sequence[Mapping[str, object]],
    events: Sequence[Mapping[str, object]],
    *,
    profile_headings: Sequence[str] = PROFILE_HEADINGS,
    event_headings: Sequence[str] = EVENT_HEADINGS,
    sheet_names: tuple[str, str] = (LAYOUT.profiles_sheet, LAYOUT.events_sheet),
) -> bytes:
    """An ``.xlsx`` with a Read Me sheet and the two data sheets."""
    workbook = Workbook()
    readme = workbook.active
    assert readme is not None
    readme.title = "Read Me"
    readme.append(("Fictional test workbook. Every row is made up.",))
    for title, headings, rows in (
        (sheet_names[0], profile_headings, profiles),
        (sheet_names[1], event_headings, events),
    ):
        sheet = workbook.create_sheet(title)
        sheet.append(list(headings))
        for row in rows:
            sheet.append([row.get(heading) for heading in headings])
    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


def profile_row(number: int, *, count: int = 60, **overrides: object) -> dict[str, object]:
    """One fictional profile. Every third has a card; every fourth went to events."""
    card = number % 3 == 0
    attended = ("E01", "E03") if number % 4 == 0 else ()
    row: dict[str, object] = {
        LAYOUT.profile_id_column: f"P{number:03d}",
        LAYOUT.first_name_column: "Fictional",
        LAYOUT.last_name_column: f"Profile {number:03d}",
        LAYOUT.major_column: _MAJORS[number % len(_MAJORS)],
        LAYOUT.class_year_column: _YEARS[number % len(_YEARS)],
        LAYOUT.past_event_keys_column: ";".join(attended) or None,
        "events_attended_count": len(attended),
        LAYOUT.card_completed_column: "Yes" if card else "No",
        LAYOUT.stated_interests_column: ";".join(_CARD_TOPICS[:2]) if card else None,
        LAYOUT.career_goal_column: "Data, analytics or IT role" if card else None,
        "info_level": "not read",
        LAYOUT.tiebreak_order_column: count - number + 1,
        LAYOUT.hidden_interests_column: f"{WITHHELD_TOPIC};Consulting",
        LAYOUT.hidden_career_goal_column: WITHHELD_GOAL,
    }
    row.update(overrides)
    return row


def good_profile_rows(count: int = 60) -> list[dict[str, object]]:
    """``count`` fictional profiles, P001 upwards."""
    return [profile_row(number, count=count) for number in range(1, count + 1)]


def event_rows() -> list[dict[str, object]]:
    """Ten past events (E01–E10) and the two rounds (E11 Northline, E12 Harbor)."""
    rows: list[dict[str, object]] = []
    for index in range(1, 11):
        rows.append(
            {
                LAYOUT.event_key_column: f"E{index:02d}",
                LAYOUT.event_name_column: f"Past event {index:02d}",
                "event_type": "Workshop",
                "event_date": "2025-10-02",
                LAYOUT.topic_tags_column: "Sales / business development;Consulting",
                LAYOUT.target_majors_column: "All majors" if index % 2 else _MAJORS[0],
                LAYOUT.is_exercise_event_column: "No",
                LAYOUT.seats_column: None,
            }
        )
    for index, (name, topics, major) in enumerate(
        (
            ("Northline (fictional)", "Technology / information systems", _MAJORS[1]),
            ("Harbor (fictional)", "Retail / consumer goods", _MAJORS[3]),
        ),
        start=11,
    ):
        rows.append(
            {
                LAYOUT.event_key_column: f"E{index:02d}",
                LAYOUT.event_name_column: name,
                "event_type": "Employer talk",
                "event_date": "2027-03-04",
                LAYOUT.topic_tags_column: topics,
                LAYOUT.target_majors_column: major,
                LAYOUT.is_exercise_event_column: "Yes",
                LAYOUT.seats_column: 60,
            }
        )
    return rows


def good_workbook(count: int = 60) -> bytes:
    """A workbook the parser accepts: ``count`` profiles and twelve events."""
    return workbook_bytes(good_profile_rows(count), event_rows())
