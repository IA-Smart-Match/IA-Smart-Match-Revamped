# 003 — Results can be closed again, and the instructor sees when (#326)

Lane B, branch `oct14/results-lock-snapshot`, stacked on Lane A (`oct14/event-descriptions`).
Seams are `file:line` on `origin/main` @ `ec471ba2` (2026-10-06); Lane A shifts a few by a line or two.

Paths are shortened: `persistence/` = `python/smartmatch_persistence/smartmatch_persistence/exercise/`,
`routers/` = `services/api/smartmatch_api/routers/`, `web/` = `apps/web/legacy-frontend/src/`.

## Current behavior

- `exercise_result_unlock` is keyed `(dataset_id, event_key)` with `unlocked_at`. No row = locked. A row can never be removed or closed (`persistence/schema.py:446-462`).
- `unlock_results` is `INSERT … ON CONFLICT DO NOTHING` (`persistence/instructor_repository.py:455-477`). There is no lock write anywhere.
- Two reads answer "is it open?": the team's `results_unlocked` (`persistence/results_repository.py:258-272`) and the instructor's `EXISTS` (`persistence/instructor_events.py:35-42`). Both test row existence only.
- The instructor panel shows a chip "Results are open" / "Results are closed" and an "Open results" button that disappears for good once pressed (`web/app/pages/exercise/InstructorUnlock.tsx:224-333`). No time is shown.
- A run's refusals check **locked before already-run** (`routers/exercise_results_run.py:387-396`, decision D16).

## Ordered change list

1. **Decision note first.** `docs/decisions/class-exercise-decisions-2026-09-25.md`, directly under D16 (`:364-380`): "D16 amendment, 2026-10-06". States: unlock is tri-state; already-run is checked before locked; `unlocked_at` means the most recent open; closing deletes no run. Cites Ann's Oct-2 revisions §2.
2. **Migration** `db/migrations/versions/0045_exercise_result_unlock_closed_at.py`: `revision = "0045_exercise_result_unlock_closed_at"`, `down_revision = "0044_exercise_event_description"`. `op.add_column("exercise_result_unlock", sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True))`; downgrade drops it. No backfill: existing rows read `closed_at IS NULL` = still open. No CHECK (rows are only created by an open, so close-before-open cannot exist).
3. **Schema mirror** `persistence/schema.py:446-462`: add `closed_at`; rewrite the comment at `:452-454` to the three states (no row = never opened; row + `closed_at IS NULL` = open; row + `closed_at` set = closed).
4. **Head pins**: bump every test constant that names the Alembic head to `0045_…` (`tests/integration/test_exercise_schema_migration.py`, `test_cba_contact_schema.py:174`, `test_cba_weight_settings_persistence.py:211`, plus the "revisions between" lists they keep).
5. **Team-side read** `persistence/results_repository.py:258-272`: `results_unlocked` adds `closed_at IS NULL`. This is the single lock predicate team routes consult (seam for #328 and #323).
6. **Instructor read** `persistence/instructor_events.py:35-64` + `persistence/instructor_rows.py:85-99`: LEFT JOIN the unlock row; `InstructorEventRow` gains `unlocked_at: datetime | None`, `closed_at: datetime | None`; `unlocked` = row exists and `closed_at IS NULL`.
7. **Writes** `persistence/instructor_repository.py:455-477`:
   - `unlock_results`: `ON CONFLICT (pkey) DO UPDATE SET unlocked_at = now(), closed_at = NULL WHERE closed_at IS NOT NULL`. Pressing open on an already-open event still changes nothing.
   - new `lock_results`: `UPDATE … SET closed_at = now() WHERE dataset_id, event_key, closed_at IS NULL RETURNING event_key`, through `_execute` (`:769-786`). Never opened or already closed = no-op, returns `False`, not an error.
   - The file is 786/800 lines: move the bodies of `list_saved_settings` / `list_result_runs` (`:332-388`) to a new `persistence/instructor_team_work.py` (same cut as `instructor_events.py`). #319 needs that module anyway.
8. **Models** `routers/exercise_instructor_models.py:288-320`: `InstructorEventView` gains `unlocked_at`, `closed_at`; `UnlockView` gains `unlocked_at`; new `LockView {event_key, unlocked: false, closed_at}`. `event_view()` (`:392-393`) maps the two new fields.
9. **Route** `routers/exercise_instructor.py:399-449`: `POST /v1/exercise/instructor/events/{event_key}/lock`, `dependencies=_STATE_CHANGING`, same `_teams_dataset` → `event_exists` → write → commit → re-read flow as unlock; refusal code `exercise_lock_write_refused`. Both routes answer with the row's timestamps read back from `list_exercise_events`. To keep this file from growing, the team-detail route moves out to the new `routers/exercise_instructor_detail.py` (#319, plan 005).
10. **Refusal order** `routers/exercise_results_run.py:387-396`: `get_run` check moves above `results_unlocked`. Rewrite the docstring at `:354-373` and the order-in-words in `run_results` (`routers/exercise_results.py:218-235`, served as the route description).
11. **Route ledgers**: add the lock route to `_EXPECTED_INSTRUCTOR_ROUTES` (`tests/unit/test_exercise_instructor_router.py:1380-1519`), the policy ledger (`tests/authz/test_policy_matrix.py:687`), and the two path lists (`tests/unit/test_class_exercise_scope.py:361`, `tests/unit/test_exercise_public_router.py:167`).
12. **Client** `web/lib/exerciseClient.ts:315-331, 586-591`: `InstructorEventView.unlocked_at/closed_at` (ISO strings or null), `UnlockView.unlocked_at`, `LockView`, `lockResults(eventKey, datasetId)`.
13. **Panel** `web/app/pages/exercise/InstructorUnlock.tsx:64-345`: chip "Results open" / "Results closed" (Ann's words); a time line "Opened at 10:42 AM." / "Closed at 10:50 AM."; open events get "Close results" with an inline confirm well ("Close results now" / "Keep them open"). `confirming` carries the action (`open|close`) inside the existing file+event key. Focus-restore effect (`:247-263`) extended for the close transition.
14. **Docs**: `DESIGN.md` §6.24 unlock-row states + §11.1 new sentences (inserted beside the existing "Instructor, unlock confirm" rows); `docs/operations/exercise-hosting.md` grant line `:218` → `SELECT, INSERT, UPDATE`, the `ON CONFLICT` paragraph `:235-237`, the statement inventory `:247-270`, the verification table `:361-370`, and the runbook step at `:636-639` gains the lock route.

## Test plan

| File | Adds |
|---|---|
| `tests/unit/test_exercise_instructor_router.py` | lock route: closes an open event, idempotent on closed/never-opened, 404 unknown event, 409 refusals, needs header + session; events list carries `unlocked_at`/`closed_at`; reopen after close; route table row |
| `tests/unit/exercise_results_router/test_exercise_results_rules.py` + `support.py` | `fakes.lock()`; closed-again event refuses a new run with the locked sentence; a team that already ran gets `exercise_results_already_run` on a closed event (order swap); stored results still readable after close |
| `tests/integration/test_exercise_instructor_persistence.py` | open → close → reopen on real PostgreSQL: `closed_at` set then cleared, `unlocked_at` moves on reopen only, second open press moves nothing, lock on a missing row is a no-op |
| `tests/integration/test_exercise_result_unlock_closed_at_migration.py` (new) | upgrade adds a nullable column and leaves existing rows open; downgrade drops it |
| `tests/integration/test_exercise_results_persistence.py` | `results_unlocked` is false for a closed row |
| `web/…/InstructorUnlock.lifecycle.test.tsx`, `InstructorUnlock.confirm.test.tsx` | chip words, time line, close confirm sends `POST …/lock` only on "Close results now", "Keep them open"/Escape send nothing, focus is not dropped |

Commands (one pytest process at a time, parent venv):

```
PARENT/.venv/bin/python -m pytest tests/unit/test_exercise_instructor_router.py -q
PARENT/.venv/bin/python -m pytest tests/unit/exercise_results_router -q
PARENT/.venv/bin/python -m pytest tests/integration/test_exercise_instructor_persistence.py -q
make format-check lint typecheck imports scan VENV=PARENT/.venv
npx vitest run --pool=threads src/app/pages/exercise/InstructorUnlock.lifecycle.test.tsx src/app/pages/exercise/InstructorUnlock.confirm.test.tsx
```

## Acceptance (Oct-2 lines this satisfies)

- Revisions §2: "Opening or closing results for an event shows the time it was done, and results can be closed again."
- Checklist §2: "Both events show “Results closed” at the start, with a button to open each."
- Checklist §2: "Open results for Northline. The label changes to “Results open” and the time is shown. There is also a way to close it again."
- Checklist §2 / clean-up: "Before the Oct 16 run-through, every test team is cleared and both events are closed." (#323 needs this route.)

## Decision status

| Gate | Default taken | Record |
|---|---|---|
| D16 supersession | Already-run is checked before locked; unlock is tri-state | D16 amendment 2026-10-06 in the decisions file; OQ `lane-b.md` B-1 |
| `unlocked_at` on reopen | **Most recent open** (overwritten on reopen), so the time shown is the time it was done. One row cannot hold every cycle either way | same amendment; OQ B-2 |
| Zero-teams ordering | **No fallback added.** `GET/POST …/events` keep refusing with "No team has entered a number yet." Clearing a team keeps its workspace row, so clearing Teams 1–4 does not empty the list; the runbook still says close before clear | OQ B-3 |
| Closing deletes runs? | No. Stored runs stay readable; only new runs are refused | amendment text |
| CHECK `closed_at >= unlocked_at` | None (reopen moves `unlocked_at` past the old `closed_at` and clears it) | plan only |

Operational note for the PR body: the deployed database role needs `GRANT UPDATE ON exercise_result_unlock` **before** this ships, or both open-again and close fail every time.

## As built (2026-10-06, PR #345, commit `98e52381`)

Where the implementation differs from the plan above:

1. **Revision id.** The file is `0045_exercise_result_unlock_closed_at.py`, but the revision id is `0045_exercise_unlock_closed_at`. `alembic_version.version_num` is `VARCHAR(32)` and the planned id is 37 characters; PostgreSQL refused it. Read every `0045_exercise_result_unlock_closed_at` above as the file name only.
2. **Head pins.** Six test files pin the head, not three: add `test_event_filed_by_migration.py`, `test_host_organization_migration.py`, `test_speaker_availability_migration.py`. `README.md:35` also states the count and the head.
3. **Step 9, where the lock route lives.** It stayed in `exercise_instructor.py`, beside unlock, sharing one helper (`_change_lock`). The file is 718 lines after the team-detail route moved out (plan 005); it was 698.
4. **Step 8.** `UnlockView` and `LockView` are separate models; `LockView.closed_at` is null when there was nothing open to close.
5. **Step 13, focus.** After a state change focus goes to the event's name even when it was resting on the row's own button, because that button now offers the opposite action.
6. **Extra file.** `apps/web/legacy-frontend/src/app/pages/exercise/exerciseTime.ts` (`clockTime`), shared with plan 005.
7. **Extra tests.** `InstructorUnlock.close.test.tsx` (new, 9 tests). The persistence test for closed rows lives in `test_exercise_instructor_persistence.py`, which calls `results_unlocked` too.
8. **Docs.** The design spec §9 got a five-line "as amended" pointer; one server sentence was added to DESIGN.md §11.1 ("The results for that event could not be closed.").
