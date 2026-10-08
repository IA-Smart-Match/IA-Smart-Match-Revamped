# 009 — List download: plain "how much we know" column + pink-column negative test (#335)

Branch `oct14/download-labels` (base `origin/main` @ ec471ba2). One PR against `main`. No migration. Frontend untouched.

## Current behavior

- `GET /exercise/.../events/{event_key}/list.csv` (`services/api/smartmatch_api/routers/exercise_matching.py:422-490`) renders the same `RankedListView` as the JSON list through `ranked_list_csv`.
- `services/api/smartmatch_api/routers/exercise_matching_csv.py:47-54` — `CSV_LIST_COLUMNS = ("rank","name","major","year","marker","reason")`. Header says `marker`.
- `exercise_matching_csv.py:152-163` writes `entry.marker` as-is: the wire key `major_only` / `major_plus_events` / `completed_card` (`python/smartmatch_domain/smartmatch_domain/exercise/markers.py:60-68`).
- The plain words exist only in the frontend: `apps/web/legacy-frontend/src/app/pages/exercise/markers.ts:22-26` (`MARKER_LABELS`), column label `"how much we know"` at `markers.ts:44-45`. No server-side constant holds them (grep of `python/` and `services/` finds the phrases in docstrings only).
- Pink columns are absent by construction (`TeamProfileRow` has no such field; writer iterates a fixed 6-tuple). Name-level coverage exists (`tests/integration/test_exercise_full_class_run.py:493-500`). No test reads the CSV bytes against distinctive hidden *values*, and `tests/unit/test_exercise_matching_router.py:738` derives the expected header from the constant itself, so it cannot catch a wrong header.

## Ordered change list

1. **Tests first (RED)** — `tests/unit/test_exercise_matching_router.py`, "The download" section (`:727`):
   - literal header pin `rank,name,major,year,how much we know,reason` and `CSV_LIST_COLUMNS` equal to the literal six-tuple;
   - marker cells are the three plain phrases, never an underscore key; unknown marker renders as itself;
   - words pinned to the screen's source: parse `markers.ts` `MARKER_LABELS` + `dimensionLabel("marker")` and assert equality with the server map and header;
   - negative test (route): fakes carry sentinel hidden values (`load_simulation_profiles` stub on the dataset fake + team rows that carry `hidden_true_*` attributes); assert response bytes hold neither withheld name nor any sentinel, and every row has exactly six cells;
   - negative test (writer): a view whose entries carry extra withheld attributes still yields six cells and no sentinel.
   - `tests/unit/test_exercise_markers.py`: `MARKER_WORDS` covers every `InformationMarker`; `marker_words` falls back to the raw string.
2. **Domain** — `python/smartmatch_domain/smartmatch_domain/exercise/markers.py` after `INFORMATION_RANK` (`:71-81`): `MARKER_WORDS: Final[Mapping[InformationMarker, str]]` and `marker_words(marker: str) -> str` (raw-value fallback, mirroring `markers.ts:30`). Export both in `__all__`.
3. **Writer** — `exercise_matching_csv.py:47-54`: `"marker"` → `"how much we know"`; `:152-163`: marker cell through `marker_words`. Docstrings updated. Route docstring `exercise_matching.py:444` reworded to match.
4. **Frontend comment only** — `markers.ts` doc comment cross-references the server map (no behaviour change, no string change).
5. **Copy ledger** — `docs/design/class-exercise/DESIGN.md` §6.8 one line (download uses the chip's words) and §11.1 one row beside the Matching entries.

## Test plan

- `PARENT/.venv/bin/python -m pytest tests/unit/test_exercise_markers.py`
- `PARENT/.venv/bin/python -m pytest tests/unit/test_exercise_matching_router.py`
- `PARENT/.venv/bin/python -m pytest tests/unit/test_exercise_undecided_goal_flag.py` (pins `len(CSV_LIST_COLUMNS) == 6`)
- `make format-check lint typecheck imports scan VENV=PARENT/.venv`
- Integration (`test_exercise_full_class_run.py`) needs PostgreSQL — CI only.
- No vitest: no frontend behaviour or string changes.

## Acceptance

- Checklist §4 Download: "Download the list. The file opens in Excel with rank, name, major, year, how much we know, and the reason for each name. The two pink columns from the data file do not appear."
- Revisions, "The attached Excel file": "Danny: the list participants download from the app must leave out the two pink columns. Justin: please check this."
- Header is exactly `rank,name,major,year,how much we know,reason`; six columns, pinned by literal.
- Marker cells read "major only" / "major plus events attended" / "completed card".
- The negative tests fail if a withheld name or value reaches the bytes, or if a seventh column appears.

## Decision status

No owner gate blocks #335. Three small choices the brief lists, conservative option taken, recorded in `docs/plans/open-questions/oct14-deferred.md` (Lane D section):

1. Header spelling: lowercase `how much we know` (checklist verbatim; identical to `dimensionLabel("marker")`).
2. Label source: the server cannot import `markers.ts`, so one server map in the domain module, pinned by a test that reads `markers.ts` — the frontend file stays the wording source and drift fails the build.
3. Byte-order mark: not added. Not required by the checklist, data and reasons are ASCII today, and it would change the response bytes for every consumer.
