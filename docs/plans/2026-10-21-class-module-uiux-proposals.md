# Class module UI/UX proposals (2026-10-21)

**These are proposals only.** Nothing here is merged, deployed or changed in app code. Scope is the class exercise (https://exercise.smartmatch.cloud/exercise). The main platform is deferred.

Dr. Wang's class testing runs Oct 23–26 and the VM is frozen. Every item needs the owner's go-ahead. Items that add or change words also need Dr. Wang's OK.

## Verdict

1. Safe before Oct 23 (all S effort, no new student wording):
   - fix 2 real bugs (S1, S2);
   - make the Round 1 → Round 2 handoff a single next step and re-check results on its own timer (S3, S4);
   - apply 4 one-line correctness fixes (S5);
   - fix L1 (stat tiles merge into "1270" at 360 px), and check L2 (seat-map vs chart counts) by hand before class.
2. After testing:
   - turn the Harbor before/after table into the visual lesson it is meant to be (A1);
   - make the build-save-compare loop fit on one screen (A2).
3. Copy gate on origin/main 7de1fda4:
   - `--verbatim` finds 18 of 18;
   - `--banned` finds 0 FAIL in 280 strings;
   - the gate has a blind spot (G1), so 2 banned-phrase strings go unchecked.

## How this was made

| Lane (Opus, own worktree) | Skills | Output |
|---|---|---|
| 1 | local stack + `jury` | 45 states × 3 widths, jury score, 10 observed problems (see "Lane 1") |
| 2 | `impeccable` critique/audit | 12 findings |
| 3 | `design-taste-frontend-v1`, `ui-ux-pro-max` | 11 findings (engagement, visual) |
| 4 | `web-design-guidelines`, `design:accessibility-review` | 2 bugs + 12 findings (a11y, 360 → projector) |
| 5 | `design:design-critique` | flow inventory, minutes per step, 12 findings |
| 6 | `exercise-copy-audit` (repo skill), `design:ux-copy` | 15 copy findings, gate run on every proposed sentence |
| 7 | `impeccable` harden + critique | instructor page, error/lock/empty states: 5 bugs + 5 polish |

There are no other UI/UX skills under `.claude/skills/` besides `exercise-copy-audit`.

Paths below are under `apps/web/legacy-frontend/src/app/pages/exercise/` unless they start with `services/`, `python/` or `.claude/`.

## Time budget (lane 5, from code)

A first-time team needs about **62–88 min** for both rounds, against a 75-min class.

| Step | Minutes |
|---|---|
| Entry, picker, read Northline | 3–4 |
| Northline: sliders, 2–3 saves, 1 compare | 18–25 |
| Round 1 results: pick, **wait for instructor**, run, read | 8–18 |
| Asking: choose, ask, read what changed | 5–8 |
| Harbor list: re-save settings from scratch | 12–16 |
| Harbor results: **wait**, run, read before/after | 6–15 |

The two instructor waits and the scrolling on the event page drive the overrun. Most proposals below target those three steps.

## Screen and state inventory

| Screen | States | File |
|---|---|---|
| Entry | loading, refused, unreachable + Try again, ready, "already open as Team N", enter refused | `ExerciseEntry.tsx` |
| Event picker | loading, refused, unreachable, no events, R1 card + R2 card (locked line), past events | `ExerciseEventPicker.tsx` |
| Event page (R1/R2) | loading, rebuilding, stale ("does not match the slider numbers yet"), updated, empty list, coverage line, filled-list line | `ExerciseMatching.tsx`, `RankedList.tsx`, `FilledListNote.tsx` |
| Saved settings | empty, 1, 3 at cap, same-as warning, save blocked while stale | `SavedSettingsPanel.tsx` |
| Compare | side by side (desktop), tabs (phone) | `MatchingCompareView.tsx` |
| R2 gate | locked before R1 results; "ask first" gate; asked + New-card marks | `RoundTwoAskingStep.tsx` |
| Results | not open + Check again; no saved setting; pick → "You will send" → two-press send; refused (ask first, locked, already run, unknown setting); revealed; already run | `ExerciseResults.tsx`, `ResultsLockPanel.tsx`, `ResultsCheckAgain.tsx`, `ResultsReveal.tsx`, `ResultPanels.tsx` |
| Asking | not yet; 3 choice cards + two-press; Ask now (two-press); summary + before→after table | `ExerciseAskingForMore.tsx`, `AskOnceButton.tsx` |
| Harbor results | as Results, plus before/after rows, Round 1 hatched bar and recap | `HarborBeforeAfter.tsx`, `ResultPanels.tsx` |
| Done | **none**: no end-of-exercise state | `teamStatusWording.ts:149-151` |
| Instructor | passcode, teams grid (15 s poll), team detail, open/close results, refresh all, data files + upload | `ExerciseInstructor.tsx`, `InstructorTeams.tsx`, `InstructorUnlock.tsx`, `InstructorDatasets.tsx` |

Ann's 3 UI pain points from her Oct 16 feedback, and where they stand on HEAD:

| Pain point | Status |
|---|---|
| Round confusion | Mostly fixed: banner on every page, numbered rounds, Harbor list gated |
| Two-press confirm button moves or expires | Fixed: 10 s window, fixed width, double-click guard (`desk/motion.ts:39`, `desk/confirmWindow.tsx:42-48`) |
| "Nobody on this list is a … major" line too small | Fixed: gold-tint line directly above the list |

## Top 5

### Safe before Oct 23

| # | Proposal | Screen | Current | Change | Why it helps a student in a 75-min class | Effort | Freeze risk | Ann-frozen |
|---|---|---|---|---|---|---|---|---|
| S1+S2 | **Fix 2 bugs that stall the class** | Instructor teams grid; Harbor results | **S1:** `InstructorTeams.tsx:109` (also `InstructorUnlock.tsx:91`) does not pass `keepDataOnError`. One Wi-Fi blip blanks all 6 team rows and **stops the 15 s poll**. **S2:** `ExerciseResults.tsx:437-439` checks only `event.open`. A team without Round 1 results is told to wait for the instructor, or presses Run and gets a `round_two_locked` refusal. | **S1:** pass `keepDataOnError: (e) => e instanceof ExerciseUnreachable`, the same pattern already used at `TeamStatusBand.tsx:106` and `ExerciseResults.tsx:188`. **S2:** read `workspace.round_two_open` (already used at `RoundTwoAskingStep.tsx:45`). If it is false, grey out Run and show the server's own sentence "Round 2 opens after your team has its Round 1 results." | Ann keeps the projector grid live. Teams stop waiting on the instructor when they are really blocked by Round 1. | S, 2–3 h | low: S1 copies a shipped pattern; S2 mirrors a gate the server already enforces | S1 adds no words. S2 reuses an existing server sentence: **needs Ann OK** (it is not in ann-verbatim) |
| S3+S4 | **One next step at the round boundary, plus a timed re-check of results** (Mockup 3) | Round 1 results, picker, asking, results lock | The frozen "Round 1 done…" line shows twice, with 2 links to 2 places (`RoundBanner.tsx:40-49`, `ExerciseResults.tsx:516-522`). The grey "Results already run" button sits above the outcome. After choosing a way to ask, nothing moves the team on to "Ask students now". Results unlock only when someone presses Check again. | Keep one copy of the frozen line, with a primary "Go to Round 2" button to `/exercise/asking`. Move the grey button below the outcome. After the choice is confirmed, move focus and scroll to Ask. Re-read the lock every 15 s while results are closed (`ResultsCheckAgain.tsx:46`). | Removes a 2–5 min stall at the round boundary and up to 2 wait-stalls per team. | S, 4–6 h | low: layout and focus changes; existing order tests need updating | No new words. Frozen line and lock sentence are unchanged. |
| S5 | **4 one-line correctness fixes** | Results confirm, phone list, tab title, asking refusal | (a) The armed label says "for Northline Analytics: Behind the Business"; Ann's text is "for Northline." (`ExerciseResults.tsx:132`). (b) The marker chip spills 11 px past its card at 360 px (`RankedList.tsx:163`). (c) The tab shows "SmartMatch Platform" while screens load (`index.html:7`, `ExerciseScreen.tsx:96-97`). (d) The server says "already asked the people it invited", which is false since the redesign (`services/api/smartmatch_api/routers/exercise_results.py:625`). | (a) `shortEventName()`. (b) `self-start whitespace-normal`. (c) Set the exercise title before render when on `/exercise`, and drop the restore. (d) "Your team has already asked students for more information. A team asks once." | (a) matches Ann's words. (b) stops sideways scroll on small phones. (c) meets Ann's tab rule. (d) stops a false statement. | S, 2 h | low | (a) brings the label back to Ann's text. (c) tab wording **needs Ann OK**. (d) **needs Ann OK** (passes gate). |

### After testing

| # | Proposal | Screen | Current | Change | Why it helps | Effort | Freeze risk | Ann-frozen |
|---|---|---|---|---|---|---|---|---|
| A1 | **Harbor before/after as the visual lesson** (Mockup 1) | Harbor results | `HarborBeforeAfter.tsx` is a plain 4-column table, third in the stack (`ResultPanels.tsx:146-175`). Ann's debrief line is plain body text. The Harbor chart adds a Round-1 bar from a different event, which is the comparison Ann warned against. | Put it straight under the seat reveal. Show paired bars per row on one shared axis: mass email alone vs with your list, with a `+N (M came)` chip. Highlight the team's after-asking row and set Major first apart. Show the debrief line as a gold-rule pull quote. Fold the table into "See the numbers" (DOM kept for tests and screen readers). | Ann expects a gap of only 2–3 sign-ups between before and after. That is invisible in a table but obvious as two bar ends, and it reads on the projector at debrief. | M, 4–6 h | med: new visual in a tested block | Debrief sentence frozen and unchanged. "See the numbers" and the reorder **need Ann OK**. Optional freeze-safe slice: the reorder alone (S, 0.5 h). |
| A2 | **Build-save-compare on one screen** (Mockup 2) | Event page, both rounds | Saving means scrolling past 60 rows and the composition table, 6+ times a round. The status band is pinned and 3–4 lines tall at 1280 (about 8 at 360), and it covers the pinned slider card (`TeamStatusBand.tsx:92`, `ExerciseMatching.tsx:360`). | At 900 px and up, move the save card into the pinned left column under the sliders. Show the first 15 rows plus "Show all 60". Fold the composition table. Shrink the band to one line on desktop and unpin it on phones. Give Round 1 and Round 2 their own banner colours. | Saves about 30 s per save/compare trip, 120–200 px of screen, and several minutes per round. This is the biggest time sink. | M, 6–10 h | med: layout tests (`*.desk.test`, `TeamStatusBand*.test`) | Frozen panel strings move but are unchanged. "Show all 60" and short band labels **need Ann OK**. |

## Other proposals (ranked, after testing unless noted)

| id | Screen | Proposal | Source lane | Effort | Risk | Ann-frozen |
|---|---|---|---|---|---|---|
| B1 | Picker | Status chips "Done / Up next / Locked until Round 1 results". The current round gets the strong seal. The Round 2 link goes to asking until the team has asked. (Mockup 3C) | 2, 3, 5 | M 2–3 h | low-med | chips need Ann OK |
| B2 | Event page | After a slider release, show rank deltas (▲3 / ▼2) for 4 s and the line "List updated: 5 names joined, 5 left." | 3 | M 3 h | med | needs Ann OK |
| B3 | Weights card | Live ratio line while dragging: "Right now same major counts 2× as much as …" (Ann's own framing, no %) | 3 | S-M 2 h | low | needs Ann OK |
| B4 | Harbor saved settings | One button: "Use our Northline settings" | 5 | M 3 h | med | needs Ann OK |
| B5 | After Harbor | A finish state, e.g. "Both rounds done. Stay on this screen for the debrief." | 5 | S 1 h | low | needs Ann OK |
| B6 | Compare view, 1280 and projector | Each half is about 516 px but the table needs 640 px, so the Year and "how much we know" columns scroll off-screen. Use `layout="cards"`. | 4 | S 0.5 h | low-med | conflicts with Ann's "each table scrolls in its own box": needs Ann OK |
| B7 | Results chart, tablet and projector | Scale the fixed 880×460 chart with CSS. Above 1600 px, raise body and meta type and the content width. Make the seat grid wider on xl. Make the mass-email bar stroke darker. | 4 | M 3 h | med (results is the big moment) | no copy |
| B8 | Fonts, all screens | `proxima-sera` and `usual` never load (no Typekit link), so headings fall back to Georgia, DejaVu or Noto, depending on the device. Map the serif token to the loaded display/body stack. | 3 | S 1 h | low-med (global) | no copy |
| B9 | Instructor | Compact 6-row progress table: Northline results / Asked / Harbor results. "3 of 6 teams have Northline results." in the Open-results confirm. Name the data file in use after upload, with an "In use by N teams" chip. Put the confirm well under its row header. Fix plurals. | 7 | M 5–6 h | low | new labels need Ann OK |
| B10 | Instructor confirms | Clear team / Move every team: focus moves to the confirm, reuse `useInlineConfirmGuard`, and say how many teams lose work | 7 | S 1.5 h | low | count sentence needs Ann OK |
| B11 | Upload | Refuse Excel error cells (`#VALUE!`, `#REF!`, …) with a sentence naming sheet, row and column. Ann's "#VALUE!" most likely came from the team's checklist sheet. The app already names missing columns. | 7 | M 2–3 h | med | needs Ann OK |
| B12 | Status band offline | Replace "Reload the page…" with a "Try again" re-read, because a reload while offline loses the team's place | 7 | S 1 h | low | needs Ann OK |
| B13 | Results reveal | "Play again" ghost button so Ann can replay a team's seat fill at debrief | 3 | S 1 h | low | needs Ann OK |
| B14 | Round 2 asking | Bars for "how much we know", before vs after | 3 | M 2.5 h | low | no copy |
| B15 | Entry | Hide the duplicate "Fictional data" ribbon on the entry page only, since the license box says the same. Label the button "Open Team 3's work". | 2, 6 | S 1 h | low | needs Ann OK |

## Wording proposals (lane 6; all pass the gate)

The gate was run on 26 proposed strings added to a scratch copy:
- `--banned`: exit 0, 0 FAIL in 306 strings;
- `--verbatim`: exit 0, 18 of 18.

| id | file:line | Current | Proposed | Ann-frozen |
|---|---|---|---|---|
| W1 | `askingChoices.ts:51` | Students must fill in a card to hear about events. Some will stop responding. | Students must fill in a card to hear about events. Some will stop opening our messages and will not sign up for anything. | needs Ann OK |
| W2 | `services/.../exercise_results.py:625` | Your team has already asked the people it invited. | Your team has already asked students for more information. A team asks once. | needs Ann OK (false today) |
| W3 | `HarborBeforeAfter.tsx:24, :44` | "Your list added" / "3 (2 came)"; "…same chance draws…" | "Extra sign-ups from your list" / "3 (2 of them came)"; "…same luck as your run. They do not use up your one results run." | needs Ann OK |
| W4 | `ExerciseResults.tsx:590, :578, :597` | Run results for this event / Running… / …cannot run this event a second time. | Send this list and see results / Sending your list… / Press again to send this list. You get one results run for this event. | needs Ann OK |
| W5 | `ResultsLockPanel.tsx:51` | Results are closed | Results not open yet | needs Ann OK |
| W6 | `python/.../results_repository.py:122`, `ExerciseResults.tsx:460` | 3 different wordings of the one-run rule | "You get one results run for this event." (Ann's phrase) everywhere | needs Ann OK |
| W7 | `ExerciseEntry.tsx:228` | This computer is already open as Team {n}. | …Press Open this team's work to go back to it, or pick a different team. | needs Ann OK |
| W8 | `ExerciseAskingForMore.tsx:444, :522` | "…picks up its topics" / "Picked up the first event's topics" | "…also counts as having gone to a similar event" / "Now count as having gone to a similar event" | needs Ann OK |
| W9 | `RoundTwoAskingStep.tsx:102` | Ask first. The list comes after, so it can use what the students tell us. | Ask first. Your Harbor list comes after, so it can use the new cards students fill in. | needs Ann OK |
| W10 | `ExerciseMatching.tsx:479` | Go back to this list's weights | Set the sliders back to this list's numbers | needs Ann OK |
| W11 | `ResultPanels.tsx:261` | …with {n} invited. …the name limit… | …with {n} students on your list. …the list size… | needs Ann OK |
| W12 | `ResultPanels.tsx:182` | Your team's first round | Your team in Round 1 | needs Ann OK |
| W13 | `exercise_matching.py:246`, `exercise_results_run.py:255`, `ExerciseEventPicker.tsx:191` | "…student body…", "…data file…" | Each gets a next action, and "data file" is dropped (full text in the lane 6 notes) | needs Ann OK |
| W14 | `exercise_matching_weights.py:140, :143, :198`, `desk/weightValue.ts:34` | "weight" in slider errors | "slider number" | needs Ann OK |

None of these touch a string in `ann-verbatim.md`.

**G1 (tooling):** `.claude/skills/exercise-copy-audit/extract-copy.mjs:27` (`SKIP_LINE`) skips every line that contains `className=`. That hides 2 banned-phrase strings:
- `ExerciseEventPicker.tsx:191` "This data file carries no past events.";
- `teamStatusWording.ts:120` "Data file".

Fix the regex before the next copy change. It is tooling, not app code, so it is safe any time.

## Mockups

Static HTML in `docs/plans/class-module-uiux/mockups/`. Screenshots at 1280 and 360 px are in `docs/plans/class-module-uiux/shots/`. Colours come from `desk/tokens.ts`. The fonts are system fallbacks. Numbers are illustrative.

| Mockup | Covers | Files |
|---|---|---|
| 1 | A1 Harbor before/after | `mock-1-harbor-before-after.html`, `shots/mock-1-*.png` |
| 2 | A2 event page, one-screen loop | `mock-2-event-page-layout.html`, `shots/mock-2-*.png` |
| 3 | S3+S4 round handoff, auto re-check, B1 picker chips, focus to Ask | `mock-3-round-handoff.html`, `shots/mock-3-*.png` |

Live entry page (read-only, no team opened): `shots/live-entry-360.png`, `shots/live-entry-1280.png`.

## Lane 1 (local stack + jury)

**Setup.** Local API and Vite ran against a private database (since dropped), seeded with `make exercise-seed` (300 profiles, 12 events). The VM was not touched. Team 3 was walked through both rounds, and the instructor page through unlock and refresh.

**Screenshots.** 45 states were captured at 360, 768 and 1280.
- The 360 set is in this PR: `docs/plans/class-module-uiux/shots/local/*-360.png`.
- The full 135-file set (43 MB) is on the local, unpushed branch `uiux/lane1-shots` @ 83101257. Push it if wanted.
- Not captured: dataset upload and "Clear team's work" (both destructive). The asking confirm also reset on resize, so it shows unconfirmed.

**Jury** (blind critic, local production build, 9 pages):
- Critic score 5.9, jury estimate about 7.0.
- Weakest areas, all at 4/10: Responsive, Semantics, Animations and Markup.
- Mobile CLS is above 0.2 on 4 pages: Harbor 0.32, Northline 0.30, events 0.24, asking 0.24.
- Mobile LCP is 2.4–2.8 s.
- No page-level horizontal scroll at any width.

Lane 1 findings not already covered above:

| id | Screen / width | Finding | Proposal | Effort | Risk | Ann-frozen |
|---|---|---|---|---|---|---|
| L1 | Asking, 360 (`30-asking-after-summary-360`) | **Bug:** the stats "127" and "0" run together and read as "1270" | Stack the count tiles below 480 px | S 0.5 h | low | no copy. **Safe before Oct 23.** |
| L2 | Results, Northline and Harbor | **Verify before Oct 23:** the critic reports that the seat-map counts differ from the chart (Northline seats 13+10=23 vs chart 16 attended). Possibly two different measures (already coming + list vs attended), not a bug. | Check one run by hand. If it is two measures, label both (rule R3). | S 1 h check | — | any new label needs Ann OK |
| L3 | Status band and compact slider bar, 360 | The band is sticky and about 360 px tall (46 % of a 780 px screen). The fixed slider bar (z-30) covers it and wraps to 5 lines. Headings scroll under it at every width. | Same fix as A2: one-line band, unpinned on phones, compact bar placed under the band (`TeamStatusBand.tsx:92`, `WeightsCompactBar.tsx:69-75`) | S-M 2 h | low-med | short labels need Ann OK |
| L4 | Harbor event page before Round 1 results (`04-harbor-reachable-before-r1`) | The list is correctly hidden, but the banner says "Build your Harbor list with what you now know…" and the card heading says "Round 2 starts here", above "Round 2 opens after your Northline results." | While Round 2 is locked, show only the lock line in the banner | S 1 h | low | reuses existing text |
| L5 | `/exercise/<unknown>` | The exercise 404 falls through to the platform 404 ("Back to the Smart Match home page", title "SmartMatch Platform") | Add an exercise catch-all route linking to `/exercise` | S 1 h | low | new sentence needs Ann OK |
| L6 | Harbor and Northline results with exactly 1 saved setting | Run stays grey until the team ticks its only setting | Pre-select it when there is exactly one | S 0.5 h | low | no copy |
| L7 | Instructor teams | "Clear team 3's work" is a green link beside the primary button | Use the danger style and move it apart | S 0.5 h | low | no copy |
| L8 | Every page, mobile | CLS above 0.2 | Reserve height for the status band and list skeletons | M 2 h | low | no copy |

## Open questions for Dr. Wang

1. Can Northline results be opened at the start of class, so teams pace themselves? The server keeps Harbor locked until each team has Round 1 results. This removes up to 10 min of waiting per round.
2. On Harbor results, should the Round-1 hatched bar and recap stay, or should only the before/after rows show (A1)?
3. "Use our Northline settings" shortcut for Harbor (B4), or should teams rebuild their settings as part of the lesson?
4. What should the finish line say after Harbor results (B5)?
5. Approve or reword W1–W14 and the new labels: picker chips, "Show all 60", short band labels, "See the numbers", tab title, the S2 Round-2 lock sentence, and the compare view showing cards instead of a scrolling table.
