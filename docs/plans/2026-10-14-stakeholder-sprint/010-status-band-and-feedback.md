# 010 — Team status line, every press says what it did, missing confirms (issue #321)

Branch `oct14/status-band`, stacked on `oct14/results-lock-snapshot` (#345, which holds #339) and `oct14/refresh-visibility` (#340). No migration. No server change.

## Current behavior (verified on the merged base, 2026-10-06)

| Area | Today | Gap |
|---|---|---|
| Team identity | Only `/exercise` says which team this browser is (`ExerciseEntry.tsx`). | No team page says "Team 3"; no status line. |
| `ExerciseScreen` | Header = logo, ribbon, `h1`, lead, optional `aside` (`ExerciseScreen.tsx:55-117`). | No slot for a status line. |
| Facts for a line | `GET workspaces/current` → `team_number`, `dataset_label`; `GET …/events` → `is_exercise_event`, `sequence`, `results_open`, `results_run` (#345); `GET …/asking-choice` → `choice`, `refreshed`, `refreshed_at` (#340). | All served. Nothing to add server-side. |
| Clock time | Two formatters after the merge: `exerciseTime.clockTime` (#345) and `refreshWording.formatClockTime` (#340). | Consolidate onto one. |
| Matching: save / delete / open / compare | Save and delete re-read the panel and say nothing. A refusal shows at the top of the page, far from the panel (`ExerciseMatching.tsx` `panelRefusal`). | No sentence beside the button. |
| Matching: slider let go | "Rebuilding the list…" while it runs, then nothing. | Checklist §4 wants "List updated". |
| Results: run | Three states and the inline question shipped in #345. Grey "Results already run for this event." | No time of the run. |
| Results: "Check again" | Re-reads the lock; if it is still closed nothing changes on screen. | A press that did nothing says nothing. |
| Asking: choice | Card turns "chosen"; the "Your team chose this" sentence is `sr-only`. | Checklist §6 wants a visible "You chose: …". |
| Team refresh ("Ask them now") | One press, once only, on Asking and on Results. | Brief gate 4: ask first. |
| Instructor: refresh every team | One press sends it (`InstructorUnlock.tsx` `RefreshAllPanel.send`). | **The named gap**: no "Are you sure?". |
| Instructor: clear a team | Asks first; afterwards says nothing. | Checklist §2 wants "Team X cleared." |
| Instructor: set the limit | Says nothing on success. | Checklist §2 wants "Limit set to 25." |
| Instructor: "Check the teams again" | Re-reads; if nothing changed, nothing shows. | Say when it was last read. |

### Buttons that already passed (no change)

| Button | Why it passes |
|---|---|
| Entry: team tile + "Enter" | Navigates; refusal sentence under the form. |
| Picker: round cards, past-events disclosure | Links; `aria-expanded` list opens in place. |
| Matching: "Save these weights" when blocked | Grey (`aria-disabled`) with the reason in `#exercise-save-note`. |
| Matching: delete confirm ("Delete X? It cannot be brought back.") | Already asks inline. |
| Matching: download link, disabled state | Grey link described by the not-current sentence. |
| Matching / Results / Asking: "Try again" | The notice it sits in is replaced by the loading state or the answer. |
| Results: "Results not open yet." / run question / "Results already run for this event." | #345. |
| Results + Asking: "Already refreshed at 10:42 AM" + summary | #340. |
| Asking: choice arm → confirm; refresh grey with its reasons | Existing. |
| Instructor: passcode sign-in, show/hide, sign out | Refusal sentence / form swaps. |
| Instructor: upload | "file — 300 profiles, 12 events loaded." (#325). |
| Instructor: open / close results | Ask inline; chip + "Opened at 10:42 AM." (#326). |
| Instructor: move every team to this file | Asks inline with scope; "Moved 4 teams to …, clearing the work of 2 of them." |
| Instructor: "Open this team's work" | The work opens under the row. |
| Instructor: refresh-every-team report | Headline + one line per team (#340). |

## Ordered change list

0. **Merge + ceiling.** Merge #340 into #345's branch (one commit). `results_repository.py` lands at 816 lines → move `_ints`, `_panel_from_json`, `_panel_as_json` to `results_rows.py` (as `int_tuple`, `panel_from_json`, `panel_as_json`; that module already holds `invited_as_json`/`weights_as_json`). No new module, so no `_TRACK_MODULES` / import-linter change. Separate commit.
1. **One clock.** `exerciseTime.clockTime` takes the `en-US` + plain-space implementation; `refreshWording.formatClockTime` is deleted and its four call sites use `clockTime`. Tests move with it.
2. **Wording module** `teamStatusWording.ts` (pure): `teamStatusFacts(workspace, events, asking, eventKey)` → the line's items. Round = index among `is_exercise_event` sorted by `sequence` (as the picker does). Refresh words composed here, client-side.
3. **Band** `TeamStatusBand.tsx`: reads `readCurrentWorkspace` + `readEvents` + `readAskingChoice` through `useExerciseResource`; props `eventKey?` and `revision` (a page bumps it through `useStatusRevision(reload)` after its own re-read lands). A refused read renders nothing (the page shows the refusal); an unreachable one says so. `role="status"`-free `dl` with an `aria-label`; one `sr-only` polite line announces a change.
4. **Shell slot.** `ExerciseScreen` gains `status?: React.ReactNode`, rendered between the header and the body.
5. **Wire four pages**: `ExerciseEventPicker`, `ExerciseMatching` (event), `ExerciseResults` (event, revision), `ExerciseAskingForMore` (revision). Entry and Instructor stay without it.
6. **Matching feedback.** `ExerciseMatching.guard` returns the outcome; a `panelNote {tone,text}` replaces `panelRefusal` and is rendered by `SavedSettingsPanel` beside its buttons (`feedback` prop). Sentences: saved (with slots left), deleted, opened, comparing, compare closed. "List updated." beside "The list" after a rebuild lands.
7. **Results feedback.** "Run at 10:42 AM." in the already-run line (`ResultsView.created_at`); "Checked at 10:43 AM. Results are still not open." after "Check again".
8. **Team refresh asks first.** New `AskOnceButton.tsx` (arm → press, `useConfirmWindow`), used on Asking and Results.
9. **Asking: visible choice sentence** "You chose: A small reward. A team picks once, so this is now fixed."
10. **Instructor.** `RefreshAllPanel`: inline two-button question in front of `send`. `InstructorTeams`: "Team 3 cleared at 10:42 AM. …" and "Last checked at 10:43 AM." `InstructorDatasets`: "Limit set to 25."
11. **DESIGN.md**: §6.1 (band), §6.14 (extend the 2026-10-06 note), §6.24 (refresh-all confirm; drop "not part of this panel yet"), §11.1 rows beside related ones.

## Test plan

- `teamStatusWording.test.tsx`: every item, null states, round derivation, refresh time.
- `TeamStatusBand.test.tsx`: renders from three reads; re-reads on `stamp`; refused read renders nothing; unreachable says so.
- `ExerciseScreen.test.tsx`: `status` slot sits between header and body.
- Per page: band present after load (`ExerciseEventPicker`, `ExerciseMatching`, `ExerciseResults`, `ExerciseAskingForMore`); band re-read after run / choice / refresh.
- `ExerciseMatching.test.tsx` / `SavedSettingsPanel`: saved / deleted / opened / comparing sentences; refused save shows beside the panel.
- `ExerciseResults.*.test.tsx`: run time; "Check again" sentence; refresh needs two presses.
- `ExerciseAskingForMore.test.tsx`: visible "You chose"; refresh needs two presses, Escape cancels.
- `InstructorUnlock.refreshAllConfirm.test.tsx`: first press sends nothing and shows the scope; "Refresh them now" sends once; "Not yet" / Escape send nothing.
- `ExerciseInstructor.teams.test.tsx` / datasets: "Team 3 cleared", "Limit set to 25."
- Backend: no code change beyond the helper move; targeted files only (results router dir, matching, instructor, workspace, reachability, schema, persistence tables).
- Commands: `make format-check lint typecheck imports scan VENV=…`; `tsc --noEmit`; `vitest run --pool=threads <files>` from an ext4 copy.

## Acceptance (Oct-2 checklist lines)

- §1 "After any press, a message appears right next to the button saying what just happened, in words." — items 6–10.
- §1 "The message stays on screen until the next action. It does not vanish after a second." — every new sentence is state cleared only by the next action.
- §1 "If the press did nothing (already done, not allowed yet, error), the message says why." — items 6, 7.
- §1 "A button that can only be used once turns grey after use and says so on the button itself." — shipped in #345/#340; kept, `aria-disabled`.
- §1 "Each team page has a status line at the top, always visible, showing: team number, which event, round one or round two, results used or not, way of asking chosen or not, refresh done or not." — items 2–5.
- §1 "Anything that changes saved work for a team shows the time it happened." — items 7, 10 (run, clear) plus #340's refresh time.
- §1 "Buttons that wipe or change work for everyone (clear a team, refresh every team at once, switch every team to a new file) ask “Are you sure?” first, and say exactly what will change." — clear and switch already did; item 10 adds refresh-every-team.
- §2 "Change the list limit from 30 to 25. You see “Limit set to 25.”" and "“Clear team X’s work” asks first, then shows “Team X cleared.”" — item 10.
- §4 "Move one slider and let go. A message says “List updated” and the list changes." / "Name a setting and save it. A message says “Saved” with the name and slots left." / "Delete a setting. It asks first, then says “Deleted.”" — item 6.
- §6 "After choosing, a message says “You chose: small reward,” and the status line shows it." — items 9, 3.
- §8 "Reload the page in the middle of each step. Nothing saved is lost, and the status line still shows where the team is." — the band is three server reads on mount; nothing is kept in the browser.

## Decision status

| Gate | Default taken | Recorded |
|---|---|---|
| Band scope | Four team pages; not Entry (it precedes a team), not Instructor. | F1 |
| Band's "which event" | Both rounds on every page, each with its results state; the page's own round is marked "(this page)". | F2 |
| Server field for the band | None: composed from three existing reads. | — |
| Band shows results open/closed | Yes, using #345's `results_open` (§6.14 note extended). | F3 |
| Team refresh confirm | Arm → press on the button, as the asking choice and the run. | F4 |
| Refresh-every-team confirm form | Two-button inline question in the panel (as open/close results, clear a team, move every team), not the 5-second window: the scope sentence is too long to read in five seconds. | F5 |
| "Refreshed" vs "Asked" | Not unified. Team screens and the every-team report say "Refreshed"; instructor team rows/detail keep "Asked". | F6 |
| "Wrong team?" link in the band | Included: "Not your team? Pick again" → `/exercise` (checklist §3). | F7 |
| Times with no server timestamp | "Team 3 cleared at …", "Checked at …" use the browser's clock at the moment the answer landed. | F8 |

## As built (2026-10-06) — where the implementation diverged

- **Band re-read trigger** is `revision` (a counter the page bumps after its own `reload()` lands), not `stamp`. A stamp of the page's data would have read the band twice on every first load.
- **Band lists both rounds on every page** (F2), instead of a separate "Event" pair on event pages. One rule, no guess about a "current" round.
- **Band also shows the data file** (checklist §8: "each team page says which file it uses").
- **Band checks the shape of its three answers** and treats a wrong shape as "could not be read". Found by the existing page tests, whose stubs answer other shapes.
- **Existing page tests** (`ExerciseAskingForMore`, `ExerciseEventPicker`, `ExerciseResults`) mock the band out and keep their exact request counts; the band has `TeamStatusBand.test.tsx` (component) and `TeamStatusBand.pages.test.tsx` (the four pages, real band).
- **Test files added**: `teamStatusWording.test.tsx`, `TeamStatusBand.test.tsx`, `TeamStatusBand.pages.test.tsx`, `ExerciseMatching.feedback.test.tsx`, `AskOnceButton.test.tsx`, `InstructorFeedback.test.tsx`. No test was removed; 12 refresh presses and 8 every-team presses now make the second press.
- **Merge**: six conflicted files, both sides kept. One unused import (`RefreshCounts` in `exercise_results_models.py`) dropped after the merge. No semantic incompatibility found between #345 and #340.
- **Ceiling**: `results_repository.py` 816 → 789 by moving three JSON helpers to `results_rows.py`. `exercise_matching_models.py` is exactly 800 after the merge (at the ceiling, not over; untouched). `ExerciseResults.tsx` is 785.
- **Not done**: no browser run. "Go back to this list's weights", the download link and the unlock list's "Check again" were audited and left (F10).
- **Extra OQ entries**: F9 (extra reads per page), F10 (presses left as they are).
