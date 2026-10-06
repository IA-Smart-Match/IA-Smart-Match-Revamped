# 005 — "Open this team's work" shows the whole team (#319)

Lane B, branch `oct14/results-lock-snapshot`. Shares one fix with plan 006 (#271): the run-time snapshot on `exercise_result_run`. This file stands on its own; 006 holds the migration and the write path in full.
Seams are `file:line` on `origin/main` @ `ec471ba2`.

Paths: `persistence/` = `python/smartmatch_persistence/smartmatch_persistence/exercise/`, `routers/` = `services/api/smartmatch_api/routers/`, `web/` = `apps/web/legacy-frontend/src/`.

## Current behavior

- `GET /v1/exercise/instructor/workspaces/{team_number}` returns `TeamDetailView {team_number, saved_settings, result_runs}` (`routers/exercise_instructor.py:491-529`, models `routers/exercise_instructor_models.py:248-285`).
- A saved setting is `{event_key, name, created_at}` — no weights, by a rule written into the row type (`persistence/instructor_rows.py:102-114`) and the query (`persistence/instructor_repository.py:332-350`).
- A run is counts only; the three arrays are counted in SQL and never fetched (`persistence/instructor_repository.py:352-388`).
- The screen prints "{name} — for {event_key}" and "Round {n} for {event_key}: invited …" (`web/app/pages/exercise/InstructorTeams.tsx:330-366`). No four numbers, no names, no event names, no way of asking, no refresh state in the opened view.

## Ordered change list

1. **Shared wire model** `routers/exercise_results_models.py` — `InvitedProfileView` (defined once; plan 006 uses it for the team's results):
   `rank: int | None`, `profile_no: int`, `display_name: str`, `major: str | None`, `class_year: str | None`, `marker: str | None`, `reason: str | None`. `rank`/`marker`/`reason` are null only on runs stored before migration 0046.
2. **Row types** `persistence/instructor_rows.py:102-134`:
   - `InstructorSavedSetting` gains `weights: Mapping[str, float]` (docstring rewritten: this is the "later track that opens a setting").
   - `InstructorResultRun` gains `invited: tuple[InvitedProfile, ...]`, `signed_up_profile_nos`, `attended_profile_nos`, `setting_weights: Mapping[str, float] | None`. Still no id, seed or token.
3. **Reads** — new `persistence/instructor_team_work.py` holding the two selects moved out of `instructor_repository.py:332-388` (that file is 786/800). Settings select adds `weights`; runs select adds `invited_profiles`, `setting_weights` and the two arrays. `ExerciseInstructorRepository.list_saved_settings/list_result_runs` delegate. No new import-linter edge: routers reach the row types through `exercise_dependencies` → `instructor_rows` (edge exists).
4. **Response models** `routers/exercise_instructor_models.py:248-285`:
   - `SavedSettingView` += `event_name: str`, `round: int | None`, `weights: dict[str, float]` (the four stated weights via `effective_weights`, never normalized), `invited: tuple[InvitedProfileView, ...]` in rank order.
   - `ResultRunView` += `event_name: str`, `invited`, `signed_up`, `attended` (each `tuple[InvitedProfileView, ...]`), `setting_weights: dict[str, float] | None`, `setting_deleted: bool`.
   - `TeamDetailView` += `factor_labels: dict[str, str]` (Ann's words for the four keys), `asking_choice: str | None`, `refreshed_at: datetime | None`.
   - Builders stay field by field (`:396-410`).
5. **Route** — moves to a new module `routers/exercise_instructor_detail.py` (router-level `require_instructor_session`, same prefix literal), because `exercise_instructor.py` is 698/800 and gains the lock route in plan 003. It injects `DatasetRepository` + `TeamViewRepository` beside `InstructorRepository`. Composition, in `_build_list`'s read order (`routers/exercise_matching.py:182-246`):
   1. `_teams_dataset` → `_require_team` (imported from `exercise_instructor`).
   2. `datasets.list_events` + `get_dataset_summary` (events before the 300-row join).
   3. `team_view.list_team_profiles(dataset_id, workspace_id)` once → `rankable_set` once.
   4. Per saved setting: `exercise_ranked_list(event_evidence(event), rankable.profiles, weights=validated(dict(row.weights)), invite_limit=summary.invite_limit, year_rank=rankable.year_rank, dataset_checksum=summary.checksum)`. Composed, never re-derived. **Live** for settings (current state); **snapshot** for runs (history).
   5. Per run: names from the row's snapshot; `signed_up`/`attended` resolved by `profile_no` against it.
   6. Way of asking + refresh time from `instructor.list_workspaces(dataset_id=…)` (the summary row already carries both).
6. **Registration** — `main.py:650-682` router list; `pyproject.toml` both import-linter `source_modules` lists (`:312-336`, `:398-…`); `_TRACK_MODULES` (`tests/unit/test_exercise_instructor_router.py:1263`) so the ceiling test and the model walks cover it; `_EXPECTED_INSTRUCTOR_ROUTES` row gains `get_dataset_repository`, `get_team_view_repository`; policy ledger text (`tests/authz/test_policy_matrix.py:707-718`) rewritten — it currently promises "listed by name without their weights".
7. **Guardrail, replaced on purpose** `tests/unit/test_exercise_instructor_router.py:1247` — drop `"weight"` from `_SCORE_SHAPED`; add a positive allowlist test: across every model in the instructor router modules **and** `exercise_instructor_models`, the fields whose name contains `weight` are exactly `SavedSettingView.weights` and `ResultRunView.setting_weights`. A new weight-shaped field still fails. `score|percent|confidence|probability` and `_REFUSED_FIELD_NAMES` are untouched. Do not import `RankedListView`/`ListEntryView` into an instructor module.
8. **Persistence guard, inverted** `tests/integration/test_exercise_instructor_persistence.py:452-470` — the `not hasattr(run, 'invited_profile_nos')` / `not hasattr(setting, 'weights')` assertions become positive assertions for the new fields plus negatives for `hidden_true_*`, ids, seeds.
9. **Client** `web/lib/exerciseClient.ts:291-312` — mirror the three views; export `InvitedProfileView`.
10. **Screen** — `TeamDetail` moves to a new `web/app/pages/exercise/InstructorTeamDetail.tsx`:
    - a line for the way of asking and whether it has asked, with the time;
    - per saved setting: name, event name, the four numbers under Ann's labels (the `SettingCard` pattern, `ExerciseResults.tsx:395-451`), its list of names in rank order with the "how much we know" words;
    - per run: "Round {n} · {event name}", the setting it was built from (and that it was deleted since, when so), the four numbers used, invited / signed-up / attended names, the existing seats sentence.
    - Real lists and `dl`s, no colour-only marking, readable at projector size; a live region announces the loaded detail.
11. **Docs** — DESIGN.md §6.24 team row, §7.11, §11.1 (every new sentence beside the existing instructor rows); `docs/operations/exercise-hosting.md:75` router table gains the new module.

## Test plan

| File | Adds |
|---|---|
| `tests/unit/test_exercise_instructor_router.py` | detail returns the four weights, event names, rounds, ranked invited names per setting, per-run names from the snapshot, `setting_weights`, `setting_deleted`, way of asking, refresh time, `factor_labels`; legacy run with no snapshot answers empty lists, not a crash; allowlist test; route-table row; withheld-column wire scan (`:1312-1321`) unchanged and green |
| `tests/integration/test_exercise_instructor_persistence.py` | real DB: setting weights and run snapshot read back; team isolation on both |
| `tests/unit/exercise_results_router/test_exercise_results_contract.py` | unchanged — proves the new fields leaked nothing across `/v1/exercise` |
| `web/…/ExerciseInstructor.teams.test.tsx` (+ new `InstructorTeamDetail.test.tsx`) | four numbers in Ann's words, names per setting and per run, deleted-setting wording, way of asking + time, empty states |

Commands:

```
PARENT/.venv/bin/python -m pytest tests/unit/test_exercise_instructor_router.py -q
PARENT/.venv/bin/python -m pytest tests/authz/test_policy_matrix.py -q
PARENT/.venv/bin/python -m pytest tests/integration/test_exercise_instructor_persistence.py -q
make format-check lint typecheck imports scan VENV=PARENT/.venv
npx vitest run --pool=threads src/app/pages/exercise/InstructorTeamDetail.test.tsx src/app/pages/exercise/ExerciseInstructor.teams.test.tsx
```

## Acceptance (Oct-2 lines this satisfies)

- Revisions §2: "For each team, show: its saved settings with the four numbers, its list of names, its results for each event, the way of asking it chose, and whether it has refreshed."
- Checklist §2: "“Open this team’s work” shows, for each team: its saved settings with the four numbers, its list of names, its results for each round, its way of asking, and whether it has refreshed."
- Checklist §5: "Results stay on screen after a reload, and the instructor can see them."
- Checklist §10 row 10: "Instructor sees only the names of a team’s settings, not its lists or results."

## Decision status

| Gate | Default taken | Record |
|---|---|---|
| Snapshot contract shape | `InvitedProfileView` as above; `invited_profiles` + `setting_weights` JSONB on the run (plan 006) | OQ `lane-b.md` B-7 |
| Run row shape for the builder | arrays + snapshot on the row; one join in the view builder | plan only |
| "Setting deleted" | server bool `setting_deleted` (name not among the team's current settings for that event). A same-name re-save is indistinguishable; `setting_weights` shows what was actually used | OQ B-8 |
| `email_everyone` counts on the instructor run | **Not added** (the brief marks it a scope check) | OQ B-9 |
| New module vs in place | new `exercise_instructor_detail.py` | this plan |
| Wording for "refreshed" | the page's existing voice — "Has already asked" — with the time added; #329 owns the refreshed/asked wording gate | OQ B-10 |

Cross-reference: plan 006 (`006-run-snapshot-invited-names.md`) — migration `0046_exercise_result_run_snapshot`, the write path, and the team-side names.

## As built (2026-10-06, PR #345, commit `0d88b3a0`)

Where the implementation differs from the plan above:

1. **Step 3.** `instructor_team_work.py` was created in the #326 commit (it freed room for the lock write) and extended here.
2. **Step 5, helpers.** `exercise_instructor_detail.py` imports `_teams_dataset`, `_require_team` and `_DatasetChoice` from `exercise_instructor` under their private names. Renaming them would have touched every route in that file.
3. **Step 5, shared builder.** `invited_snapshot(ranked, rankable)` in `exercise_results_run.py` builds the entries for both the run's stored snapshot and a saved setting's live list.
4. **Step 7, the walk.** `_models()` reads the router modules' namespaces only, so `SavedSettingView` and `ResultRunView` (nested in `TeamDetailView`) were never walked. The new allowlist test walks `exercise_instructor_models` as well, and a second new test applies the refused-name and score-shaped checks to those nested models.
5. **Step 10.** Each list of names is a native `<details>`, open by default. A run's missing names read "Names were not kept for this run."
6. **Not done.** No end-to-end unit test "team runs, instructor reads the same names" through one fake app; the seam is covered by `tests/integration/test_exercise_full_class_run.py` (828 passed locally with the schema files) and by the two halves separately.
7. **Revision id.** See plan 006: `0046_exercise_run_snapshot`.
