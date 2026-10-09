"""``test_data/event_interest_fit.csv`` still agrees with Ann's workbook.

The CSV is Chau's derived interest-fit table for the two exercise events,
E11 and E12, written by ``tools/compute_event_interest_fit.ps1``. Her rule:
a profile fits an event when any ``;``-separated stated interest is one of
the event's ``;``-separated topics.

Since Ann's revisions of 2026-10-02 that is also the app's rule: for a profile
with a card, ``stated_interest_overlap`` is ``1.0`` exactly where this table
says ``1`` and ``0.0`` where it says ``0``. The one difference is a profile
with no card. The table writes ``0`` for it; the factor is unknown (``None``),
never ``0`` (ADR-0011).

The first test recomputes Chau's rule from the committed xlsx through the real
parser rather than calling the factor, and fails if either file drifts. The
second holds the table against the factor itself.
"""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Final

from smartmatch_domain.exercise.layout import ParsedDataset
from smartmatch_domain.student_factors import (
    EventEvidence,
    ProfileCard,
    ProfileEvidence,
    stated_interest_overlap,
)

_CSV: Final[Path] = Path(__file__).resolve().parents[2] / "test_data" / "event_interest_fit.csv"
_EVENTS: Final[tuple[str, ...]] = ("E11", "E12")
_HEADER: Final[list[str]] = [
    "profile_id",
    "first_name",
    "last_name",
    "stated_interests",
    *(f"{key}_interest_fit" for key in _EVENTS),
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
        interests = profile.stated_interests or ()
        row = {
            "profile_id": f"P{profile.profile_no:03d}",
            "first_name": first,
            "last_name": last,
            "stated_interests": ";".join(interests),
        }
        for key in _EVENTS:
            row[f"{key}_interest_fit"] = str(
                int(any(interest in events[key].topic_tags for interest in interests))
            )
        rows.append(row)
    return rows


def test_csv_has_the_expected_columns() -> None:
    header, _ = _read_csv()
    assert header == _HEADER


def test_csv_matches_interest_fit_recomputed_from_the_xlsx(ann_full_dataset: ParsedDataset) -> None:
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


def test_csv_is_the_apps_interest_factor_for_every_profile_with_a_card(
    ann_full_dataset: ParsedDataset,
) -> None:
    _, rows = _read_csv()
    by_id = {row["profile_id"]: row for row in rows}
    events = {
        event.event_key: EventEvidence(event_key=event.event_key, topic_tags=event.topic_tags)
        for event in ann_full_dataset.events
    }
    carded = 0
    for profile in ann_full_dataset.profiles:
        row = by_id[f"P{profile.profile_no:03d}"]
        card = (
            ProfileCard(stated_interests=profile.stated_interests)
            if profile.stated_interests is not None
            else None
        )
        evidence = ProfileEvidence(str(profile.profile_no), profile.major, card=card)
        for key in _EVENTS:
            value = stated_interest_overlap(evidence, events[key]).value
            if card is None:
                assert value is None, (profile.profile_no, key)
                assert row[f"{key}_interest_fit"] == "0"
            else:
                assert value == float(row[f"{key}_interest_fit"]), (profile.profile_no, key)
        carded += card is not None
    assert carded == 70, "300 profiles, 230 without a card"
