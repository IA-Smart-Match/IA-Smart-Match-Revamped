"""The list download (CE-MATCHING-API, design spec §8; Oct-2 checklist §4).

Split out of ``test_exercise_matching_router.py``, which was already past this
repository's 800-line ceiling: the tests issue #335 added live here rather than
growing that file. The fakes, the app wiring and the eight made-up profiles are
that module's and are imported, not copied, so the two files cannot disagree
about what a team's data looks like.

What is pinned here:

1. **The six columns**, written out, and the fifth headed and filled with the
   words the screen uses rather than the API's keys.
2. **One wording, two languages**: the server's marker words and column label
   against the TypeScript files that hold the screen's.
3. **The two pink columns**: neither withheld column's name nor a value from
   one reaches the bytes of the download.

The formula guard and the filename allow-list stay in the router module's own
file, where they were before this one existed.
"""

from __future__ import annotations

import csv
import io
import re
import uuid
from collections.abc import Iterator
from dataclasses import field, make_dataclass, replace
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest
from fastapi.testclient import TestClient
from smartmatch_api.routers.exercise_matching_csv import CSV_LIST_COLUMNS, ranked_list_csv
from smartmatch_domain.exercise import EXERCISE_WITHHELD_FIELDS
from smartmatch_domain.exercise.markers import MARKER_WORDS, InformationMarker
from smartmatch_persistence.exercise.dataset_repository import SimulationProfileRow
from smartmatch_persistence.exercise.team_view_repository import TeamProfileRow

from tests.unit.test_exercise_matching_router import (
    _BASE,
    _DATASET_ID,
    _INVITE_LIMIT,
    _LIST,
    _PROFILES,
    _entered,
    _FakeDatasetRepository,
    _Fakes,
    _FakeTeamViewRepository,
)


@pytest.fixture
def fakes() -> _Fakes:
    return _Fakes()


@pytest.fixture
def client(fakes: _Fakes) -> Iterator[TestClient]:
    with _entered(fakes, 1) as entered:
        yield entered


#: The header a participant sees when the file opens, written out (Oct-2
#: checklist §4, "Download"). Not derived from ``CSV_LIST_COLUMNS``: the six-
#: column test in ``test_exercise_matching_router.py`` compares the header with
#: that constant, so it agrees with whatever the constant says.
_CSV_HEADER = ("rank", "name", "major", "year", "how much we know", "reason")

#: The three phrases the screen shows, written out for the same reason.
_PLAIN_MARKERS = frozenset({"major only", "major plus events attended", "completed card"})

#: Where the screen keeps the same words. The server cannot import a TypeScript
#: module, so the two are held together by reading this file in a test.
_SCREEN_MARKERS_SOURCE = (
    Path(__file__).resolve().parents[2]
    / "apps/web/legacy-frontend/src/app/pages/exercise/markers.ts"
)

#: Where the screen heads the same column over the ranked list. That heading is
#: its own literal in the component, not a call into ``markers.ts``, so it is
#: read here too: capitalised on screen, the same words otherwise.
_SCREEN_LIST_SOURCE = _SCREEN_MARKERS_SOURCE.with_name("RankedList.tsx")


def _csv_rows(response: Any) -> list[list[str]]:
    return list(csv.reader(io.StringIO(response.text)))


def test_the_csv_has_exactly_the_six_columns_the_checklist_names(client: TestClient) -> None:
    rows = _csv_rows(client.get(f"{_BASE}/events/northline/list.csv"))
    assert CSV_LIST_COLUMNS == _CSV_HEADER
    assert tuple(rows[0]) == _CSV_HEADER
    assert len(rows) == _INVITE_LIMIT + 1
    assert {len(row) for row in rows} == {len(_CSV_HEADER)}


def test_the_csv_says_how_much_we_know_in_the_words_on_screen(client: TestClient) -> None:
    """The screen's marker words, never the keys the API carries."""
    weights = {"same_major": 1.0, "stated_interest_overlap": 1.0}
    listed = client.get(_LIST, params=weights).json()["entries"]
    rows = _csv_rows(client.get(f"{_BASE}/events/northline/list.csv", params=weights))[1:]
    column = _CSV_HEADER.index("how much we know")
    cells = [row[column] for row in rows]
    assert cells == [MARKER_WORDS[InformationMarker(entry["marker"])] for entry in listed]
    assert set(cells) <= _PLAIN_MARKERS
    assert len(set(cells)) > 1, "the sample list should span more than one marker"
    assert not any("_" in cell for cell in cells)


def test_an_unrecognised_marker_reaches_the_csv_as_itself() -> None:
    """Design spec §7: a fourth marker is shown, not folded into one of the three."""
    view = SimpleNamespace(entries=[_entry(1, marker="something_new")])
    rows = list(csv.reader(io.StringIO(ranked_list_csv(cast(Any, view)))))
    assert rows[1][_CSV_HEADER.index("how much we know")] == "something_new"


def test_the_csv_words_are_the_words_the_screen_file_holds() -> None:
    """One wording, two languages: a change to either side alone fails here."""
    source = _SCREEN_MARKERS_SOURCE.read_text(encoding="utf-8")
    table = re.search(r"const MARKER_LABELS[^=]*=\s*\{(.*?)\};", source, re.DOTALL)
    assert table is not None, "markers.ts no longer declares MARKER_LABELS"
    on_screen = dict(re.findall(r'(\w+):\s*"([^"]+)"', table.group(1)))
    assert on_screen == {str(marker): words for marker, words in MARKER_WORDS.items()}
    column = re.search(r'dimension === "marker"\)\s*\{\s*return "([^"]+)"', source)
    assert column is not None, "markers.ts no longer labels the marker dimension"
    assert column.group(1) == "how much we know"
    assert column.group(1) in CSV_LIST_COLUMNS
    listed = _SCREEN_LIST_SOURCE.read_text(encoding="utf-8")
    heads = re.findall(r'<th scope="col"[^>]*>\s*([^<>{}]+?)\s*</th>', listed)
    assert len(heads) == len(_CSV_HEADER) - 1, "RankedList.tsx no longer has five headings"
    on_list = heads[_CSV_HEADER.index("how much we know")]
    assert on_list.casefold() == column.group(1).casefold()
    assert on_list.casefold() in CSV_LIST_COLUMNS


# -- The two pink columns (Oct-2 revisions, "The attached Excel file") -------

#: A distinctive value per withheld column, so a leak is findable in the bytes.
#: Ann's real file cannot play this part: its hidden values are ordinary topic
#: words that also appear in the public columns.
_WITHHELD_SENTINELS: dict[str, str] = {
    name: f"zz-withheld-{index:03d}-only-in-a-pink-column"
    for index, name in enumerate(sorted(EXERCISE_WITHHELD_FIELDS), start=1)
}

#: A team row that carries both withheld columns, which the real one never
#: does. Built from ``EXERCISE_WITHHELD_FIELDS`` so the names are not respelt.
_RowWithPinkColumns = make_dataclass(
    "_RowWithPinkColumns",
    [(name, str, field(default="")) for name in sorted(EXERCISE_WITHHELD_FIELDS)],
    bases=(TeamProfileRow,),
    frozen=True,
)


def _with_pink_columns(row: TeamProfileRow) -> TeamProfileRow:
    fields = {name: getattr(row, name) for name in TeamProfileRow.__dataclass_fields__}
    return cast(TeamProfileRow, _RowWithPinkColumns(**fields, **_WITHHELD_SENTINELS))


class _PinkTeamViewRepository(_FakeTeamViewRepository):
    """Every profile handed to the route carries both withheld values."""

    def list_team_profiles(
        self, _session: object, *, dataset_id: uuid.UUID, workspace_id: uuid.UUID
    ) -> tuple[TeamProfileRow, ...]:
        rows = super().list_team_profiles(
            _session, dataset_id=dataset_id, workspace_id=workspace_id
        )
        return tuple(_with_pink_columns(row) for row in rows)


class _PinkDatasetRepository(_FakeDatasetRepository):
    """The dataset fake, with the one reader of the withheld columns attached."""

    def __init__(self) -> None:
        self.simulation_reads = 0

    def load_simulation_profiles(
        self, _session: object, *, dataset_id: uuid.UUID
    ) -> tuple[SimulationProfileRow, ...]:
        self.simulation_reads += 1
        hidden: dict[str, Any] = {
            name: (value,) if name.endswith("interests") else value
            for name, value in _WITHHELD_SENTINELS.items()
        }
        return tuple(
            SimulationProfileRow(
                profile_no=row.profile_no,
                display_name=row.display_name,
                major=row.major,
                class_year=row.class_year,
                past_event_keys=row.past_event_keys,
                stated_interests=row.stated_interests,
                career_goal=row.career_goal,
                **hidden,
            )
            for row in _PROFILES
        )


def _assert_no_pink_column(body: bytes) -> None:
    text = body.decode("utf-8").lower()
    for withheld in EXERCISE_WITHHELD_FIELDS:
        assert withheld not in text, f"the download names {withheld}"
    assert "hidden" not in text
    for sentinel in _WITHHELD_SENTINELS.values():
        assert sentinel not in text, "a value from a pink column reached the download"


@pytest.mark.parametrize(
    "params",
    [{}, {"same_major": 0.0, "stated_interest_overlap": 1.0, "career_goal_fit": 1.0}],
)
def test_the_csv_never_carries_a_pink_column_or_a_value_from_one(
    fakes: _Fakes, params: dict[str, float]
) -> None:
    """Ann: "the list participants download … must leave out the two pink columns."

    The data behind this download holds both columns for every profile, on the
    rows the route reads and behind the one loader it must never call. Neither
    column's name nor either value may be anywhere in the bytes, and the file
    stays six cells wide.
    """
    fakes.team_view = _PinkTeamViewRepository()
    pink_datasets = _PinkDatasetRepository()
    fakes.datasets = pink_datasets
    served = fakes.team_view.list_team_profiles(
        None, dataset_id=_DATASET_ID, workspace_id=uuid.uuid4()
    )
    for name, sentinel in _WITHHELD_SENTINELS.items():
        assert {getattr(row, name) for row in served} == {sentinel}, "the fake is not pink"

    with _entered(fakes, 1) as entered:
        response = entered.get(f"{_BASE}/events/northline/list.csv", params=params)

    assert response.status_code == 200, response.text
    rows = _csv_rows(response)
    assert tuple(rows[0]) == _CSV_HEADER
    assert len(rows) == _INVITE_LIMIT + 1
    assert {len(row) for row in rows} == {6}
    _assert_no_pink_column(response.content)
    assert pink_datasets.simulation_reads == 0


def _entry(rank: int, **extra: object) -> SimpleNamespace:
    """One list entry as the writer reads it, plus whatever a test adds."""
    values: dict[str, object] = {
        "rank": rank,
        "display_name": f"Made-up Name {rank}",
        "major": "Marketing",
        "class_year": "Senior",
        "marker": "completed_card",
        "reason": "Same major as the event is aimed at.",
    }
    return SimpleNamespace(**{**values, **extra})


def test_the_writer_cannot_grow_a_column_from_what_an_entry_carries() -> None:
    """If a view ever gained a withheld field, the file still would not.

    The six cells are named in the writer, not read off the entry, so an entry
    carrying both pink columns produces the same six-cell row as one without.
    """
    plain = SimpleNamespace(entries=[_entry(1), _entry(2)])
    pink = SimpleNamespace(
        entries=[_entry(1, **_WITHHELD_SENTINELS), _entry(2, **_WITHHELD_SENTINELS)]
    )
    written = ranked_list_csv(cast(Any, pink))
    assert written == ranked_list_csv(cast(Any, plain))
    assert {len(row) for row in csv.reader(io.StringIO(written))} == {6}
    _assert_no_pink_column(written.encode("utf-8"))


def test_a_copied_card_on_the_overlay_never_reaches_the_csv(fakes: _Fakes) -> None:
    """After a refresh the team's own overlay holds values out of the pink columns.

    ``results_cards.py`` copies ``hidden_true_interests`` and, under the copied-
    card policy, ``hidden_true_career_goal`` onto the new card, and the card is
    stored on the overlay the list route reads. So the pink *values* are on the
    row behind this download even though the pink *columns* are not. The row is
    on the list, it is marked as a completed card, and neither value nor either
    column's name is anywhere in the bytes.
    """
    interest = _WITHHELD_SENTINELS["hidden_true_interests"]
    goal = _WITHHELD_SENTINELS["hidden_true_career_goal"]
    base = _PROFILES[2]
    weights = {"same_major": 1.0, "stated_interest_overlap": 1.0, "career_goal_fit": 1.0}

    with _entered(fakes, 1) as entered:
        workspace = fakes.workspaces.rows[(_DATASET_ID, 1)]
        fakes.team_view.overlays[(workspace.id, base.profile_no)] = replace(
            base,
            overlay_card_interests=(interest, "analytics"),
            overlay_card_career_goal=goal,
        )
        listed = entered.get(_LIST, params=weights).json()["entries"]
        response = entered.get(f"{_BASE}/events/northline/list.csv", params=weights)

    assert response.status_code == 200, response.text
    rows = _csv_rows(response)
    on_list = {entry["profile_no"]: entry for entry in listed}
    assert base.profile_no in on_list, "the copied card is not on the list being downloaded"
    assert on_list[base.profile_no]["marker"] == "completed_card"
    row = rows[on_list[base.profile_no]["rank"]]
    assert row[_CSV_HEADER.index("name")] == base.display_name
    assert row[_CSV_HEADER.index("how much we know")] == "completed card"
    assert {len(row) for row in rows} == {6}
    _assert_no_pink_column(response.content)


def test_no_download_column_is_a_withheld_one() -> None:
    assert not set(CSV_LIST_COLUMNS) & EXERCISE_WITHHELD_FIELDS
    assert not any("hidden" in column for column in CSV_LIST_COLUMNS)
