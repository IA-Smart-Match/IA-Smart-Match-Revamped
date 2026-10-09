# 001 — Upload refusal: cell cap vs `event_description` (#325)

Lane A, branch `oct14/event-descriptions`, one PR with #318. Seams verified against `origin/main` @ `ec471ba2` on 2026-10-06.

## Current behavior

1. `MAX_CELL_CHARACTERS = 500` (`python/smartmatch_domain/smartmatch_domain/exercise/workbook.py:114`) is applied to every headed body cell in `_collect_rows` (`workbook.py:450-456`) and to headings in `_header_map` (`:411`). It runs inside `read_sheets`, before ingest looks at a column name.
2. Ann's Oct-2 workbook has `Events.event_description` at 571 (E11 Northline) and 561 (E12 Harbor) characters, so the upload is refused with 422 `exercise_ingest_cell_too_long`.
3. `workbook.py` knows no column name (module docstring; AST test `tests/unit/test_exercise_ingest.py:618`), so the exception cannot be a literal there.
4. Refusal sentences quote sheet and column names in backticks; `ExerciseNotice` renders the sentence verbatim, so the backticks show on screen (`services/api/smartmatch_api/routers/exercise_instructor.py:221-226`).
5. `InstructorDatasets.run()` clears `refusal` and `done` but not `uploaded` (`apps/web/legacy-frontend/src/app/pages/exercise/InstructorDatasets.tsx:94-101`), so a refusal can sit beside the previous upload's success report.
6. A successful upload shows the server notice and a six-figure grid (`InstructorDatasets.tsx:151-167`), not the checklist's one sentence.
7. Refusal precedes `create_dataset`; no workspace row is touched (`exercise_instructor.py:221-248`). Already correct; pinned further by a test.

## Ordered change list

1. `layout.py` — new module constant `EVENT_DESCRIPTION_MAX_CHARACTERS = 2_000`; new layout fields `event_description_column`, `event_description_max_characters`; new properties `optional_event_columns` and `cell_character_limits` (sheet -> column -> limit). `event_columns` (the required list) is unchanged.
2. `workbook.py:175` — `read_sheets(raw, sheet_names, *, cell_limits=None)`; limits keyed by normalized sheet name then normalized heading, threaded through `_read_named` -> `_read_sheet` -> `_collect_rows`. Body cells only. Headings and every unlisted column keep 500. The `cell_too_long` sentence states the limit that applied.
3. `ingest.py:167` — pass `layout.cell_character_limits` into `read_sheets`. No column literal in a function.
4. `exercise_instructor.py:221-226` — the wire sentence of an ingest refusal drops the backticks (`plain_sentence` helper in `exercise_instructor_models.py`, because the router file is at 698/800 lines). Safe: `workbook.quote` already removes backticks from quoted file content, so every backtick in a refusal is a delimiter.
5. `InstructorDatasets.tsx` — an upload clears the previous upload report when it starts; any refusal clears it too. The success report leads with one composed sentence: `{file name} — {n} profiles, {m} events loaded.` The server notice ("teams have not moved") and the counts grid stay below it.
6. Fixture — `tests/fixtures/exercise/SmartMatch_Student_Body_300_10022026.xlsx`: an openpyxl copy of Ann's Oct-2 workbook with `Read Me` and `Benchmark` removed and document properties reset, exactly as the September fixture was cut (D4). Force-added past the `*.xlsx` ignore. The September file and its `.accdb` stay as the pre-Oct-2 pair.
7. Docs — `docs/design/class-exercise/DESIGN.md` §11.1 (upload sentence), `tests/fixtures/exercise/README.md`, design spec §3 cap note, decision record.

## Test plan

- `tests/unit/test_exercise_workbook.py` — a listed column at 571/2,000 accepted; 2,001 refused naming sheet, row, column and 2,000; another column at 501 still refused at 500; the limit is sheet-scoped; a heading over 500 is still `column_name_too_long`.
- `tests/unit/test_exercise_ingest.py` — Oct-2 fixture accepted (300 profiles, 12 events); a 2,001-character description refused; a 501-character `event_name` still refused; an ignored column at 501 still refused; layout contract test grows to required + optional.
- `tests/unit/test_exercise_instructor_router.py` — refused upload: 422, plain sentence with no backtick naming the missing column, `created == []`, zero commits.
- `ExerciseInstructor.test.tsx` — upload sentence; a refused second upload removes the first report.

## Acceptance

- Checklist §2: "Upload Ann's 300-row workbook. You see a message: file name, '300 profiles, 12 events loaded.'"
- Checklist §2: "Upload a workbook with one column removed. You see a plain message naming the missing column, and the old file stays in use."
- Revisions (file section): "Check that the upload works with the new column. Then remove a column on purpose and check that the app shows a plain error."

## Decision status

| Gate | Default taken | Status |
|---|---|---|
| Cap value and scope | 2,000 characters, `Events.event_description` only; headings and all other cells 500 | Default taken — confirm (OQ-A-01) |
| Column required or optional | Optional; an absent column and a blank cell both read as no description | Default taken — confirm (OQ-A-02) |
| Backticks in upload refusals | Dropped on the wire for ingest refusals only; domain sentences unchanged | Default taken — confirm (OQ-A-03) |
| Upload success sentence | Composed client-side from server fields; grid kept below | Default taken — confirm (OQ-A-04) |
| Fixture | New Oct-2 file added beside the September pair; `.accdb` not rebuilt | Manual step open (OQ-A-05) |

## As built (2026-10-06, PR #339, commit `2adeef21`)

Matches the plan, with three differences:

1. Frontend tests are in a new file, `InstructorDatasets.upload.test.tsx`, not in `ExerciseInstructor.test.tsx` (already 868 lines).
2. `layout.py` also gained `optional_event_columns`, and `test_every_layout_column_is_required_on_its_sheet` became `…_or_declared_optional`.
3. The `.accdb` was not rebuilt (needs Microsoft Access). Recorded in the fixture README and OQ-A-05.

OQ entries: `docs/plans/open-questions/oct14-deferred.md` (Lane A section) OQ-A-01 to OQ-A-05.
