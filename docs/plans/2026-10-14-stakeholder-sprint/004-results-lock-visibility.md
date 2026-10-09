# 004 — Teams can see the results lock and the one-run rule (#328)

Lane B, branch `oct14/results-lock-snapshot`. Builds on plan 003 (#326): it reads the tri-state lock through the same predicate.
Seams are `file:line` on `origin/main` @ `ec471ba2`.

Paths: `persistence/` = `python/smartmatch_persistence/smartmatch_persistence/exercise/`, `routers/` = `services/api/smartmatch_api/routers/`, `web/` = `apps/web/legacy-frontend/src/`.

## Current behavior

- The server already enforces both rules: locked → 409 `exercise_results_locked`; second run → 409 `exercise_results_already_run`, backed by `uq_exercise_result_run_workspace_event` (`routers/exercise_results_run.py:354-397`, `persistence/results_repository.py:376-459`).
- The team has **no read** of either state. `EventView` has no results fields (`routers/exercise_matching_models.py:83-123`); `read_events` does not ask (`routers/exercise_matching.py:303-335`). DESIGN.md §6.14 says this is deliberate.
- So the run button is live before the instructor opens results, the lock shows only after a refused press (`web/app/pages/exercise/ExerciseResults.tsx:256,267`), nothing asks before the one run (`:236-253`), and after the run the button is simply gone (`:262-293`).
- A stale tab that gets a 409 keeps its live button: only `exercise_setting_unknown` and success re-read the screen (`:236-253`).

## Ordered change list

1. **Contract** `routers/exercise_matching_models.py:83-123` — `EventView` gains two required fields:
   - `results_open: bool` — the instructor has opened results for this event and has not closed them.
   - `results_run: bool` — this team has already run results for this event.
   Both are `false` for a past event (not a round).
2. **Read** `routers/exercise_matching.py:303-335` — `read_events` takes `results: ResultsRepository` (already exported by `exercise_dependencies`; import list at `:69-81`). For each `is_exercise_event` row: `results.results_unlocked(session, dataset_id=workspace.dataset_id, event_key=…)` and `results.get_run(session, workspace_id=workspace.id, event_key=…) is not None`. Two rounds × two single-row reads; past events cost nothing. Addressed by the cookie only.
3. **Locked sentence** `routers/exercise_results_run.py:390-393` — becomes `"Results for {event.name} are not open yet. Ask your instructor."` (Ann's example sentence, event name substituted). `ALREADY_RUN_SENTENCE` is unchanged. Pins to update after checking the real files: `tests/unit/exercise_results_router/test_exercise_results_rules.py:186`, `tests/unit/test_exercise_teacher_flow.py:182`, `web/…/desk/primitives.test.tsx:74`, `web/…/ExerciseScreen.test.tsx:70`.
4. **Client mirror** `web/lib/exerciseClient.ts:50-57` — `EventView.results_open`, `results_run`.
5. **Screen read** `web/app/pages/exercise/ExerciseResults.tsx:99-117` — `load` adds `readEvents(signal)` to its `Promise.all`; `ResultsData` gains the event (`name`, `results_open`, `results_run`). An event the read does not list is treated as open-and-not-run, so the server stays the judge.
6. **Three button states** `ExerciseResults.tsx:194-293`. Run takes precedence over open:
   | State | Button | Reason (wired with `describedBy`) |
   |---|---|---|
   | not open, not run | grey, `aria-disabled`: "Results not open yet." | lock panel: "Results for {event} are not open yet. Ask your instructor." + quiet "Check again" (re-reads; it is a read now, not the one-time run) |
   | open, not run | live: "Run results for this event" (grey until a final setting is chosen, as today) | existing final-setting hint |
   | run | grey, `aria-disabled`: "Results already run for this event." above the stored panels | "A team runs results once per event." |
7. **Inline confirm** — `useConfirmWindow` (`web/…/desk/confirmWindow.tsx`), the asking card's pattern (`ExerciseAskingChoiceCard.tsx:119-155`): first press arms and the button reads "Send this list? You get one results run for {event}"; a second press inside 5 s sends the POST; Escape or the window lapsing puts it back and sends nothing. A held Enter never confirms. No pop-up, no `window.confirm`.
8. **Second run says why, and the tab catches up** — in `act()` (`:205-234`) a 409 `exercise_results_locked` or `exercise_results_already_run` shows the server sentence **and** calls `onChanged()`, so a stale tab re-reads events + results and lands on the right grey state. Covers: second press, reload (grey from the read), second tab (409 → sentence → resync).
9. **Lock panel** `web/…/ResultsLockPanel.tsx` — shown from the read, not from a refusal; takes the sentence `id` and an `action` slot; docstring rewritten (the "no team-side read" rationale is retired).
10. **Design** `docs/design/class-exercise/DESIGN.md` §6.14 (`:530-536`) — dated amendment 2026-10-06 reversing "teams have no read of the lock state", new state table; §7.8 line "Before a run"; §11.1 gains every new sentence next to the existing "Results, lock chips" row.
11. **Route description** — `run_results` docstring already updated in plan 003 step 10; `read_events` docstring says what the two fields mean.

## Test plan

| File | Adds |
|---|---|
| `tests/unit/test_exercise_matching_router.py` | fake results repository + `get_results_repository` override in `_exercise_app` (`:383-398`); state matrix: closed/unrun, open/unrun, open/run, closed-again/run, past events both false; two teams — one team's run does not set the other's `results_run`; the model walks (`:113-119, 1441-1452`) stay green |
| `tests/unit/exercise_results_router/test_exercise_results_rules.py` | new locked sentence byte for byte, naming the event; already-run sentence unchanged |
| `tests/unit/test_exercise_teacher_flow.py` | substring pin for the new sentence |
| `web/…/ExerciseResults.test.tsx`, `ExerciseResults.desk.test.tsx` | every fixture gains a `GET …/events` stub; grey "Results not open yet." with no POST possible; first press arms and sends nothing; second press sends once; Escape cancels; after run the grey "Results already run for this event." is present; 409 already-run → sentence + re-read → grey; `aria-disabled` + `aria-describedby` assertions; "Check again" re-reads |
| `web/…/desk/primitives.test.tsx`, `ExerciseScreen.test.tsx` | sentence fixtures |

Second-tab and reload are proven at the HTTP level by the existing `tests/integration/test_exercise_full_class_run.py:331-353` and the persistence concurrency tests; nothing there changes except the locked sentence.

Commands:

```
PARENT/.venv/bin/python -m pytest tests/unit/test_exercise_matching_router.py -q
PARENT/.venv/bin/python -m pytest tests/unit/exercise_results_router -q
PARENT/.venv/bin/python -m pytest tests/unit/test_exercise_teacher_flow.py -q
npx vitest run --pool=threads src/app/pages/exercise/ExerciseResults.test.tsx src/app/pages/exercise/ExerciseResults.desk.test.tsx
```

## Acceptance (Oct-2 checklist §5 "Results lock and one run per team")

- "Before the instructor opens results, the results button is grey and says “Results not open yet.”"
- "After the instructor opens results, the button becomes active on the team page (after a page reload at most)."
- "The team chooses which saved setting to send. The screen asks “Send this list? You get one results run for Northline” before running."
- "After the run, the button turns grey and reads “Results already run for this event.”"
- "Try to run again: by pressing the button, by reloading the page, and from a second browser tab as the same team. Each time, no second run happens and a message says why."
- Checklist §1: "If the press did nothing (already done, not allowed yet, error), the message says why. Example: “Results for Harbor are not open yet. Ask your instructor.”"
- Checklist §7: "Results for Harbor stay locked until the instructor opens them, with one run per team, as in round one."

## Decision status

| Gate | Default taken | Record |
|---|---|---|
| A — where the state lives | `EventView` fields via `read_events` (the issue's plan; #321 reuses them) | OQ `lane-b.md` B-4 |
| B — closed again after a run | `results_run` wins over `results_open` on screen; the POST answers already-run first (plan 003) | D16 amendment |
| C — copy | Checklist wording used exactly where it gives it. Event shown by its full `name` ("Northline Analytics: Behind the Business"), not the short "Northline" of Ann's example — the file has no short name. The live button keeps "Run results for this event" | OQ B-5; DESIGN.md §11.1 |
| D — freshness | Read on load, resync on 409, and a "Check again" button on the closed state. No polling | OQ B-6 |
| §6.14 reversal | Amended in the same change with a dated note | DESIGN.md §6.14 |

Seams for later lanes: `EventView.results_open: bool`, `EventView.results_run: bool` (server `exercise_matching_models.py`, client `exerciseClient.ts`).

## As built (2026-10-06, PR #345, commit `beda9c0f`)

Where the implementation differs from the plan above:

1. **Step 3 pins.** `tests/unit/test_exercise_teacher_flow.py` does not exist. The old sentence was pinned in `test_exercise_results_rules.py` and as sample text in two frontend tests (`ExerciseScreen.test.tsx`, `desk/primitives.test.tsx`); all three were updated.
2. **Step 5, a failed events read.** `eventResultsState()` answers `null` when the read fails or does not list the event, and the button is then live, as before this change. Losing access (401/403) still replaces the screen.
3. **Step 6, the "not open" state from a refusal.** When the events read could not say and the run is refused as locked, the lock panel shows the server's sentence, as it did before.
4. **Step 7.** The button also carries a visible, spoken hint while armed: "Press again to send this list. Your team cannot run this event a second time." Two presses in one tick only arm the button (the 300 ms double-click guard).
5. **Existing tests.** Every test that ran results now presses twice through a `pressRun()` helper; "sends one run for two presses in the same tick" became two tests.
6. **New test file.** `ExerciseResults.lock.test.tsx` (12 tests) instead of growing the two existing files.
7. **Merge with Lane A.** `EventView` carries `description` (Lane A) before `results_open` / `results_run`.
