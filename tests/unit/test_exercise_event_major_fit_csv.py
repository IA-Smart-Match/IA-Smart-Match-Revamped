"""``test_data/event_major_fit.csv`` still agrees with Ann's workbook.

The CSV is Chau's derived major-fit table for the two exercise events, E11 and
E12, written by ``tools/compute_event_major_fit.ps1``. Her rule: an event whose
``target_major`` is "All majors" fits everyone; otherwise a profile fits when
its major equals the event's target major, ignoring case. The app's rule
(``ParsedEvent.target_majors``) is membership of the profile's canonical major
in the event's majors, with "All majors" expanded to all six. For single-major
targets such as E11 and E12 the two rules give the same answer, so this test
recomputes the fit from the committed xlsx through the real parser and fails
if either file drifts.
"""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Final

from smartmatch_domain.exercise.layout import ParsedDataset

_CSV: Final[Path] = Path(__file__).resolve().parents[2] / "test_data" / "event_major_fit.csv"
_EVENTS: Final[tuple[str, ...]] = ("E11", "E12")
_HEADER: Final[list[str]] = [
    "profile_id",
    "first_name",
    "last_name",
    "major",
    *(f"{key}_major_fit" for key in _EVENTS),
]


def _read_csv() -> tuple[list[str], list[dict[str, str]]]:
    # Export-Csv -Encoding UTF8 on Windows PowerShell writes a byte-order mark.
    with _CSV.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        return list(reader.fieldnames or []), list(reader)


def _expected_rows(dataset: ParsedDataset) -> list[dict[str, str]]:
    events = {event.event_key: event for event in dataset.events}
    rows = []
    for profile in sorted(dataset.profiles, key=lambda p: p.profile_no):
        first, _, last = profile.display_name.partition(" ")
        row = {
            "profile_id": f"P{profile.profile_no:03d}",
            "first_name": first,
            "last_name": last,
            "major": profile.major,
        }
        for key in _EVENTS:
            row[f"{key}_major_fit"] = str(int(profile.major in events[key].target_majors))
        rows.append(row)
    return rows


def test_csv_has_the_expected_columns() -> None:
    header, _ = _read_csv()
    assert header == _HEADER


def test_csv_matches_major_fit_recomputed_from_the_xlsx(ann_full_dataset: ParsedDataset) -> None:
    _, actual = _read_csv()
    expected = _expected_rows(ann_full_dataset)
    assert len(actual) == len(expected) == 300
    mismatches = [
        (want["profile_id"], column, got.get(column), want[column])
        for got, want in zip(actual, expected, strict=True)
        for column in _HEADER
        if got.get(column) != want[column]
    ]
    assert mismatches == []
