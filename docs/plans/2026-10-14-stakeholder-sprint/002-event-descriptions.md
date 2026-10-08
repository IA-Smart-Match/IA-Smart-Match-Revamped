# 002 — Event descriptions end to end (#318)

Lane A, branch `oct14/event-descriptions`, one PR with #325. Seams verified against `origin/main` @ `ec471ba2` on 2026-10-06.

## Current behavior

1. `event_description` exists nowhere: not on `ExerciseFileLayout` / `ParsedEvent` (`python/smartmatch_domain/smartmatch_domain/exercise/layout.py:54-149`, `:229-247`), not read by `_parse_event` (`ingest.py:332-368`), not on `exercise_event` (`python/smartmatch_persistence/smartmatch_persistence/exercise/schema.py:189-223`).
2. `ExerciseEventRow`, `_event_values`, `list_events` (`dataset_repository.py`) and `InstructorEventRow` / `select_exercise_events` (`instructor_rows.py`, `instructor_events.py`) project no description.
3. `EventView`, `RankedListView` (`services/api/smartmatch_api/routers/exercise_matching_models.py:351-366`, `:449-490`) and `InstructorEventView` (`exercise_instructor_models.py:288-297`) carry no description.
4. Team pages show name, topics and "Aimed at" only: `RoundCard` (`ExerciseEventPicker.tsx:112-153`), `ExerciseMatching.tsx` (title from `RankedListView.event_name`), and `UnlockRow` (`InstructorUnlock.tsx:265-330`) shows the name and a lock chip.
5. `_Cells.text` (`ingest.py:236-237`) raises `KeyError` for a column the sheet does not have.

## Ordered change list

1. Migration `0044_exercise_event_description` (down `0043_exercise_event_exploratory`): nullable `TEXT` `exercise_event.description`; schema mirror; six pinned heads moved. **First commit, pushed alone** (Lane B chains on it).
2. `layout.py` — `ParsedEvent.description: str | None = None` (defaulted last). Layout field and `optional_event_columns` come from plan 001.
3. `ingest.py` — `_Cells.optional_text` (blank when the sheet has no such column); `_parse_event` stores the cell or `None`. Free text, no vocabulary check, not in `withheld_columns`.
4. `dataset_repository.py` — `ExerciseEventRow.description`, `_event_values`, `list_events` select and row builder.
5. `instructor_rows.py` / `instructor_events.py` — `InstructorEventRow.description`, selected in `select_exercise_events`.
6. API — `EventView.description`, `RankedListView.event_description`, `InstructorEventView.description`; builders in `exercise_matching.py:323-335`, `ranked_list_view`, `event_view`. All `str | None`, default `None`.
7. `exerciseClient.ts` — the three interfaces gain the field.
8. UI — one shared `EventDescription` component at body size (`ce-type-body`, the ranked list's own size): under the name in `RoundCard`; above the weights grid in `ExerciseMatching.tsx`; under the name in `UnlockRow`. `null` renders nothing. No description literal in the frontend.
9. Docs — DESIGN.md §6.5, §6.24, §7.4; decision record amendment; ops docs head revision.

## Test plan

- `tests/integration/test_exercise_event_description_migration.py` (new): NULL backfill, long text and NULL accepted, downgrade and re-upgrade.
- `tests/unit/test_exercise_ingest.py`: Oct-2 fixture gives 571/561-character descriptions on E11/E12 and `None` on E01–E10; September fixture gives `None` everywhere and otherwise parses to the same events and profiles; blank cell -> `None`; absent column accepted.
- `tests/unit/test_exercise_schema.py`: `description` on `exercise_event`, nullable.
- `tests/integration/test_exercise_dataset_repository.py`: round trip through `create_dataset` -> `list_events`.
- `tests/integration/test_exercise_instructor_persistence.py`: `list_exercise_events` carries it.
- `tests/unit/test_exercise_matching_router.py`, `test_exercise_instructor_router.py`: `/events`, `/list` and `/instructor/events` carry it; model walks stay green.
- Vitest: `ExerciseEventPicker.test.tsx`, `ExerciseMatching.test.tsx`, `InstructorUnlock.lifecycle.test.tsx` — shown when present, absent when `null`, above the weights controls.

## Acceptance

- Revisions §5: "Show a short description at the top of the Northline and Harbor pages, above the sliders, and next to each event on the instructor page. The text is in the new event_description column of the attached Excel file. Take it from the file, so I can change it later by uploading a new file."
- Checklist §3a: "Northline and Harbor each show the description below at the top of the event page, above the sliders." / "The same description appears on the instructor page next to each event." / "The text is readable on the projector (no smaller than the list text)."
- Checklist §3a: "The 'why someone would come' notes are for the instructor and the team only. Teams see just the description." — those notes are checklist prose, not workbook data; no field carries them.

## Decision status

| Gate | Default taken | Status |
|---|---|---|
| Column required or optional | Optional | Default taken — confirm (OQ-A-02) |
| Where the text lives | Same public paragraph on `EventView`, `InstructorEventView` and `RankedListView.event_description`; no instructor-only field | Default taken (brief §5.2) |
| Old datasets | `NULL` end to end, nothing rendered | Default taken (brief §5.3) |
| Migration number | `0044_exercise_event_description`, as assigned; collides with PR #337's `0044_drop_event_exploratory` — whoever merges second rebases | Stated in the PR body |

## As built (2026-10-06, PR #339, commits `a7895be6` and `7ac5d957`)

Matches the plan, with four differences:

1. The six pinned Alembic heads moved, not one: `test_cba_contact_schema.py` (plus its chain list), `test_cba_weight_settings_persistence.py`, `test_event_filed_by_migration.py`, `test_exercise_schema_migration.py`, `test_host_organization_migration.py`, `test_speaker_availability_migration.py`.
2. Frontend tests are in one new file, `EventDescription.surfaces.test.tsx`, covering all three screens.
3. The round card's link is named by the seal and the event name (`aria-labelledby`) and described by the rest (`aria-describedby`), so the paragraph is not the link's name. Existing name-prefix tests still pass.
4. Head-revision mentions in `README.md`, `docs/operations/exercise-hosting.md`, `supabase-setup.md`, `supabase-maintenance.md` and `docs/agents/feature-implementation-template.md` moved to `0044`.

OQ entries: `docs/plans/open-questions/oct14-deferred.md` (Lane A section) OQ-A-02, OQ-A-06, OQ-A-07.
