# Oct 2 stakeholder review — conflicts with the current implementation, and action plan

**Prepared:** 2026-10-05
**Sources:** Ann Wang, *Smart Match: Progress Check and Revisions Due Oct 16* and *Smart Match — User Test Checklist*, both dated 2026-10-02
**Code baseline:** branch `chau-10-02-update-matching-algorithm` at `f27199e`. Its product code equals `main` at `ec471ba`: the branch's 4 commits touch only `docs/plans/2026-10-02-exercise-matching-factor-fix-handoff.md`.
**Sprint deadline:** 2026-10-14 (milestone "Oct-14 stakeholder board"). **Ann's run-through:** 2026-10-16.
**Companion documents:** the Oct 4 plan on `feat/oct-2-stakeholder-revisions` (draft PR #324), and this branch's factor-fix handoff.

This document answers three questions:

1. Which of Ann's requests **conflict** with what the code does on purpose (a decision, ADR, design rule or approved wording)? For each one it covers what she asked, how the current code works, how the change would work, the blast radius, and a recommendation.
2. Which requests are simply **not built yet**?
3. Which GitHub issue owns each item? Issues **#325–#336** were filed on 2026-10-05. Existing issues #289, #293, #318, #320–#323 received scope-gap comments.

---

## 0. Read this first

### 0.1 Two blockers that stop the run-through regardless of anything else

| # | Blocker | Why | Issue |
|---|---|---|---|
| B1 | **Ann's new workbook is refused at upload** | The Northline and Harbor `event_description` cells are 571 and 561 characters long. `MAX_CELL_CHARACTERS = 500` (`exercise/workbook.py:114`) applies to every cell that has a heading (`:450-456`), so the upload returns 422 `cell_too_long`. That blocks Danny's upload and switch task, the event descriptions (#318), and the no-SQL clean-up path. | #325 |
| B2 | **"Set both events back to results closed" cannot be done in the app** | There is no route to close results again, and the production DB role has no DELETE on `exercise_result_unlock` (`docs/operations/exercise-hosting.md:218`, `:368`). | #326; workaround noted in #323 |

### 0.2 What Ann saw is not necessarily `main`

Ann clicked through the deployed GCP site. The `deploy` branch tip is `19b110e` (PR #243, Sep 27), **30 commits behind `main`**. It lacks PRs #253–#256, including `da4aa82` ("once-only presses send once and stay shut on the server's word") and the weight-total screen.

Some of Ann's "not working" observations may therefore already be fixed on `main`, or only partly. The deployed SHA must be recorded first (#323). The "Status" columns below describe **source on `main`**, not the live site.

---

## 1. Conflicts with the current implementation

The table sorts conflicts by how hard they are to undo. A *hard* conflict reverses a recorded stakeholder or owner decision. A *design* conflict reverses a team design rule or engineering limit. A *soft* conflict touches only a code comment or doc wording.

| ID | Ann's request | What it conflicts with | Kind | Issue |
|---|---|---|---|---|
| C1 | 4b — remove the "undecided goal fits a broad event" credit (at least on Northline) | OQ-CE-14 / decision D2: **Ann's own 2026-09-25 ruling** | Hard | #322 |
| C2 | 4c — major-only rows say "same major; nothing else on file"; ties say "tied on major; ordered by year" | OQ-CE-12: approved tie sentences and the precedence `TIE_LINE_WINS_OVER_MAJOR_ONLY_LINE = True` | Hard | #320 |
| C3 | P004 with "said they are interested" at 0 does **not** rank above a plain Accounting major | Decision D9 / OQ-CE-15: "keep as built" (Chau, 2026-09-25), pinned by a golden test | Hard | #293 |
| C4 | Clearing a team and rerunning the same list gives the **same** result | Design spec §11: "reset … regenerates its seed" | Design | #331 |
| C5 | Results can be **closed again**, with the time shown | DESIGN.md §6.16 / unlock-panel prompt: opening is one-way; the DB grant has no DELETE | Design | #326 |
| C6 | Grey "Results not open yet" and grey "Results already run for this event" buttons | DESIGN.md §6.14: teams have no read of the lock; after a run the button is *gone* | Design | #328 |
| C7 | 4a — a matching interest (and, by her wording, a past event) counts **in full** | The branch handoff's 0 / 0.5 / 1 past-event bucket (Chau's refinement, not Ann's) | Design | #289 |
| C8 | Long event descriptions in the workbook | The 500-character cell limit (an engineering security limit, design spec §111) | Design | #325 |
| C9 | The instructor sees each team's weights, names and results | Code-comment rules: "Names only, never the weights"; "a run is described by how many, never by who" | Soft | #319 |
| C10 | Event descriptions shown in the app | Requirements doc `:97-98` places the descriptions in the pre-class reading pack | Soft | #318 |

### C1 — "Undecided" career goal on Northline (revision 4b)

**What Ann asks now:** "It is being counted as fitting a 'broad event.' That rule is not in the plan, and Northline is not a broad event. Please remove it." The checklist says: "Nobody gets credit for an 'undecided' career goal on Northline."

**What it reverses:** Ann's own answer of 2026-09-25 (OQ-CE-14, `docs/plans/open-questions/class-exercise-open-questions.md:32`; decision D2, `docs/decisions/class-exercise-decisions-2026-09-25.md:25, 94-120`): *"Undecided → should match broad exploratory events … at half credit … Treat both Northline and Harbor as exploratory, since they are company events. The results step should treat undecided students the same way."*

**How it works today:**

- At ingest, each event's `event_type` is looked up in `EXERCISE_EVENT_TYPES` (`exercise/vocabulary.py:151-170`). Ann's file spells the types `"Employer talk (exercise event 1)"` and `"…(exercise event 2)"`, and both map to `True`.
- The result is stored as `exercise_event.is_exploratory` (migration `0043`).
- `career_goal_fit` (`student_factors/factors.py:177-186`) returns `UNDECIDED_EXPLORATORY_GOAL_FIT = 0.5` for an `Undecided` card on an exploratory event, and 0 elsewhere.
- The results rule mirrors this in `exercise/simulation.py:539-540`, so hidden-goal "undecided" profiles also get half fit when attendance is simulated.
- The ranked list labels such a profile with `UNDECIDED_GOAL_HALF_LABEL` ("undecided goal suits a broad event", `registry.py:155`). It is carried over the API as `ListEntryView.undecided_goal_half` and rendered by `RankedList.tsx:279-303`.

**How the change would work:**

| Option | Mechanism | Diff size |
|---|---|---|
| **A. Northline only (recommended)** | Flip `"Employer talk (exercise event 1)"` to `False` in `vocabulary.py:166`, then re-upload the dataset so `is_exploratory` is recomputed (this happens anyway with the Oct 2 file). Harbor keeps 0.5. | About 1 line of code; goldens re-pinned |
| B. Remove everywhere | Delete the undecided branch in `career_goal_fit` and its mirror in `simulation.py`. The `undecided_goal_half` field is always false, or removed (an API contract change). `UNDECIDED_GOAL_HALF_LABEL` and the reason phrase become dead. | ~15 Python tests, 2 web test files, and possibly the API contract |

The handoff's D5(b) says a Northline-only change "needs a per-event override". **That is not correct:** the two events already have distinct type keys, and the import-time collision check (`vocabulary.py:179-184`) proves they do not fold together.

**Blast radius:**

- **Domain:** `factors.py`, `simulation.py` (listed in the handoff as MUST NOT CHANGE, so this needs an explicit override), `reasons.py`, `registry.py`, `vocabulary.py`.
- **Tests:**
  - `test_exercise_undecided_goal_flag.py` (7 tests), `test_exercise_undecided_label.py`, `test_exercise_reasons.py:245-264`;
  - Ann-dataset goldens `:297`, `:317` (**missed by the handoff**: `max(undecided) < min(graduate)` fails under option B) and `:331` (P197's rank-30 pin);
  - `test_exercise_results_rule_sample_golden.py` if the simulation changes.
- **Visible effect:** P197 (30th on Northline) drops off the list. P233 (5th) and P030 (25th) are on Harbor's list and stay there only under option A.

**Recommendation:** take option A, apply it to the results rule as well, and record a dated decision that supersedes OQ-CE-14 for Northline. Ask Ann in the same email whether Harbor should follow.

### C2 — One reason line, and Ann's two phrases (revision 4c)

**What Ann asks:** one short reason line per name; major-only rows say "same major; nothing else on file"; tied rows say "tied on major; ordered by year".

**How it works today:**

- `RankedList.tsx:253-270` renders the server's `reason` and then a **second** `<FactorNames>` line ("What counted: …"). Removing that second line conflicts with nothing: DESIGN.md §6.7 specifies one line.
- Ann's two phrases **already exist byte-for-byte** in `exercise/reasons.py:94, 97`. They almost never appear, because of an approved precedence rule:
  - `reasons.py:118` sets `TIE_LINE_WINS_OVER_MAJOR_ONLY_LINE = True` (applied at `:228-236`).
  - `matching.py:376-397` (`_tie_context`) picks the *finest* tie-break key that separates a row from either neighbour.
  - Major-only profiles of the same major and year tie on every key down to the fixed order, so they get "Tied; placed in a fixed order that never changes."
- **Measured on today's Northline default list:** 15 of 30 names are major-only, and **0** show Ann's line. 22 of 30 show the fixed-order sentence, and "tied on major; ordered by year" appears **0** times.

**What it conflicts with:** OQ-CE-12 (`class-exercise-open-questions.md:30`). It approved "every reason line as written", including the fixed-order sentence, and the precedence "the tie line wins when both fit". The branch handoff (`:243-244`) also forbids touching `reasons.py`.

**How the change would work:**

1. Remove `FactorNames` from `RankedList.tsx`.
2. Set `TIE_LINE_WINS_OVER_MAJOR_ONLY_LINE = False`, so major-only rows always say Ann's phrase.
3. Change the tie wording so that a tie *within the same major* reads "tied on major; ordered by year" whenever year actually separates the rows. Retire the fixed-order sentence from the visible line, or keep it only for exact ties within one year.

**Interaction with C7 / #289:** under the binary-interest and related-count rules, about 21 of the Northline top 30 get the fixed-order sentence and none gets "What counted". Without the second line, the screen would show *what counted* for nobody. So C2 must be decided together with #289, not after it.

**Blast radius:** `reasons.py`, the `matching.py` tie logic, `RankedList.tsx`; about 6 tests in `test_exercise_reasons.py`; Ann-dataset goldens `:217` and `:331`; `RankedList.test.tsx`, `RankedList.undecidedLabel.test.tsx`, `ExerciseMatching.test.tsx:200`. No API or DB change.

### C3 — P004 with "said they are interested" set to 0

**What Ann's checklist says:** "with 'said they are interested' turned up, he ranks above a plain Accounting major. With it set to zero, he does not."

**What it conflicts with:** decision D9 / OQ-CE-15 ("keep as built", Chau, 2026-09-25; "Ann may revisit"). It is pinned by `tests/golden/exercise/test_exercise_ann_dataset_golden.py:178` (`test_turned_off_p004_still_ranks_above_on_its_career_goal`), which asserts the **opposite** of Ann's line.

**Technical reason:**

- Northline's target major is CIS, so a plain Accounting major scores 0 on every factor.
- P004's career goal ("Data, analytics or IT role") still scores on `career_goal_fit` when the interest weight is 0.
- When values tie, design spec §4.4 puts more information on file first (Ann's own tie-break).
- On the full file, P004 is 6th with the interest weight off, both today and under #289. The plain Accounting majors P257 and P231 sit at 161st and 295th.

**Change options:** Ann accepts D9 and edits the checklist line (no code), or the goal→topic table or tie-break changes (D9 option B, which the team rejected).

**Recommendation:** send Ann the numbers before Oct 16. **#289 does not fix this.**

### C4 — Clearing a team keeps its chance draw (checklist §8)

**What Ann asks:** "After clearing, run the same list again for that team. The result is the same as before (the chance part is fixed per team)."

**How it works today:**

- Every chance draw is `SHA-256(seed, event_key, profile_no, purpose)` (`simulation.py:503-518`, `determinism.py:37-50`).
- The seed is a per-team random value made when the team first enters (`workspace_token.py:142-153`).
- `ExerciseWorkspaceRepository.reset_team` (`workspace_repository.py:480-550`) deletes the team's overlay, settings and runs, and **sets a new seed**, on purpose: *"A reset that kept the seed would hand the team the same 'chance' results it just cleared, which is the one thing a reset in a classroom is for."*
- The design spec (`2026-09-16-class-exercise-design.md:317-318`) and the ops runbook (`exercise-hosting.md:654-655`) say the same.
- Re-pointing to a new file also regenerates seeds (`instructor_repository.py:723`).

**How the change would work:** stop assigning `seed=new_workspace_seed()` in `reset_team` (one line). Optionally do the same in re-point. Flip `tests/integration/test_exercise_full_class_run.py:461-484`, and amend the design spec and runbook.

**Blast radius:** small in code. The semantic change is that a cleared team cannot "re-roll" chance. If that is ever wanted, add a separate "re-roll" action.

**Recommendation:** keep the seed (Ann's checklist is newer and matches the "same list → same result" lesson). Record the change as a dated decision (#331).

### C5 — Re-closing results, with timestamps

**What Ann asks:** "Opening or closing results for an event shows the time it was done, and results can be closed again." Her clean-up also needs both events closed before Oct 16.

**How it works today:**

- The lock is the *absence* of a row in `exercise_result_unlock(dataset_id, event_key, unlocked_at)` (`schema.py:446-462`).
- `POST /events/{key}/unlock` inserts with `ON CONFLICT DO NOTHING` (`instructor_repository.py:455-477`).
- The rule is one-way by design: `DESIGN.md:637` ("once open: … no button") and the unlock-panel prompt ("Opening is one-way for the session").
- The production grant is `SELECT, INSERT` only (`exercise-hosting.md:218`).
- `unlocked_at` is stored but never selected or returned.

**How the change would work (recommended):**

- Add a nullable `closed_at` column (new migration), an `UPDATE` grant on it, and a `POST …/events/{key}/lock` route with an authz ledger entry.
- Return `unlocked_at` and `closed_at` on `InstructorEventView`.
- The alternative, a `DELETE` grant, loses the history.
- Also check "already run" **before** "locked" in `exercise_results_run.py:387-396`, so a team that already ran sees the right sentence after a re-close.

**Blast radius:** migration plus grant docs, the instructor router and models, OpenAPI, `InstructorUnlock.tsx`, the authz policy matrix, and integration tests.

### C6 — Team-visible lock and "already run" buttons

**What Ann asks:** a grey "Results not open yet" before unlock; the confirm "Send this list? You get one results run for Northline"; a grey "Results already run for this event" afterwards; and a reason for every retry path.

**How it works today:**

- **The server already enforces one run** per team per event: UNIQUE `(workspace_id, event_key)` (`0037_exercise_tables.py:327-328`), an advisory lock in `record_run` (`results_repository.py:434-455`), and a 409 `exercise_results_already_run`. Concurrency tests exist. Ann's "not blocked" does not hold for the server, and may reflect the older deployed build.
- What she can't *see* is by design:
  - `DESIGN.md:534`: teams have **no read of the lock state**, so the run button is the only probe.
  - `DESIGN.md:536`: after a run the button is *removed*.
- A tab opened before the run still shows the button, and it does not re-read after the 409.

**How the change would work:**

- Add `results_open` and `results_run` booleans to `EventView`, reusing `results_unlocked()` (`results_repository.py:258-272`). Render the three button states with `desk/Button.tsx`'s accessible disabled style.
- Add an inline confirm before running.
- Re-read after a 409.
- Reword the server's locked sentence to name the event and say "Ask your instructor."
- Amend DESIGN.md §6.14.

**Blast radius:** the API model (an additive field), OpenAPI, the authz test for the new field, `ExerciseResults.tsx`, a byte-for-byte refusal-sentence test, and DESIGN.md.

### C7 — "Count in full": partial credit (revision 4a)

**What Ann asks:** "a matching interest should count in full". Of past events she writes "seem to work the same way".

**How it works today:**

- `stated_interest_overlap` returns `jaccard(card interests, event topics)` (`student_factors/factors.py:127-154`). For P004, with 3 interests and Northline's single topic, that is 1/3.
- `past_event_topic_overlap` returns `jaccard(union of attended events' topics, event topics)` (`:206-242`).
- The composite is Σ weight × value over the *known* factors; unknown factors add 0 and their weight is not re-spread (`exercise/matching.py:234-239`).

**What this branch plans** (`docs/plans/2026-10-02-exercise-matching-factor-fix-handoff.md`; issue #289):

- Interest: any match → 1.0, none → 0, no card → unknown. **This matches Ann.**
- Past events: count attended events that share at least one topic. 0 → 0, 1 → 0.5, 2 or more → 1. **The 0.5 bucket is Chau's refinement, not Ann's.**

**Where it diverges from Ann on her own data:**

- Northline relates only to past event E08 and Harbor only to E05. Nobody has 2 related events, so the factor tops out at 0.5.
- 7 profiles that attended only E05 (topics identical to Harbor's) score **1.0 under Jaccard today and drop to 0.5**. That reduces credit on Harbor, the opposite of "count in full".

**Recommendation:** confirm the bucket with Ann, or let one related event count 1.0 for the exercise. Decide C2's tie wording in the same change.

**Blast radius (from the handoff, confirmed):**

- **Domain:** `factors.py`, the `evidence.py` docstring, `registry.py` (bump to `exercise-0.2.0`), `matching.py` (formula version bump).
- **Tests:** `test_student_factors.py`, `test_exercise_matching.py`, `test_exercise_matching_golden.py` (G-CE-05/06, new 16/17), the registry pins, `test_exercise_ann_dataset_golden.py`, `exercise_class_driver.py`.
- **Docs:** design spec §4.2 and ADR-0025:80.
- **No change** to the API or DB, which store factor keys and not formulas.

### C8 — The 500-character cell limit vs event descriptions

See blocker B1. The limit is an engineering choice (design spec §111), not a stakeholder decision. Give `event_description` its own larger limit and keep 500 everywhere else (#325).

### C9 — The instructor sees "names only" (soft)

The repository and row types say so in code comments:

- `instructor_repository.py:335`: "Names only, never the weights"
- `instructor_rows.py:104-110, 123-124`: "a run is described by how many, never by who"

These are not ADR rules. ADR-0025 D8 forbids **scores**, not weights or names. #319 already specifies the change; update those comments when it lands.

### C10 — Event descriptions in the app (soft)

`docs/product/class-exercise-requirements.md:97-98` lists "both event descriptions" in the pre-class reading pack. Ann's Oct 2 request moves them into the app as well. Update the requirements doc with #318.

**Caution:** Ann's "why someone would come" notes quote counts that come from the **hidden** columns (e.g. "21 against 19 truly interested"). They must never be loaded into `event_description`.

---

## 2. Requirement status (source on `main`) and owning issue

Status key: ✅ done · 🟡 partial · ❌ missing · ⚠️ conflict (see §1).

### Revision area 1 / checklist §1 — every press shows that it worked (lead: Janice, with Danny)

| Requirement | Status | Current behaviour | Issue |
|---|---|---|---|
| A message next to the button after every press | 🟡 | `desk/Notice.tsx` exists, but notices sit at the page top. Team-side successes (save, delete, slider, run, choose) are silent. | #321 |
| The message stays until the next action | ✅ | No auto-dismiss anywhere; each new press resets the notice. | — |
| A no-op says why | 🟡 | Server refusals are shown verbatim. The locked sentence lacks Ann's "Ask your instructor." | #321, #328 |
| One-use buttons grey out and say so | 🟡 / ⚠️ C6 | Refresh is done. The asking choice uses "Your team chose this." The results button disappears instead of greying. | #328 |
| Always-visible status line | ❌ | No status region and no single backend read. | #321, #268 |
| Times on changes | 🟡 | Timestamps are stored, and some are in the API (`SavedSettingView.created_at`). None are shown; `refreshed_at` is not on the team API. | #321, #329 |
| "Are you sure?" on clear / refresh-all / switch file | 🟡 | Clear and switch have inline confirms. Refresh-all has none. | #321 |

### Revision area 2 / checklist §2 — instructor view (lead: Danny, with Janice)

| Requirement | Status | Current behaviour | Issue |
|---|---|---|---|
| Wrong passcode → "Wrong passcode" | 🟡 | One generic sentence, "That passcode was not recognised." | #321 |
| Upload says file name, "300 profiles, 12 events loaded" | 🟡 / blocked | The facts are shown as a grid; Ann's file is refused (B1). | #325 |
| Missing column → plain message, old file stays | ✅ / 🟡 | Works for required columns. Backticks show literally, and a stale success report can sit beside the refusal. | #325 |
| Which file every team uses | 🟡 | Shown per team row on the instructor page; not on team pages. | #321 |
| Limit 30 → 25 → "Limit set to 25" | 🟡 | Works, but shows no message. | #321 |
| "Results closed" at start; open shows the time; can close again | ⚠️ C5 | Opening is one-way, with no time shown. | #326 |
| "Open this team's work" shows weights, names, results, asking choice, refresh | 🟡 / C9 | Shows setting names and run counts only. | #319, #271 |
| Clear team asks first → "Team X cleared", others untouched | 🟡 | Asks first; no "cleared" message; isolation is tested. | #321 |
| Clean-up before Oct 16 | ❌ / B2 | Teams can only be cleared one at a time; there is no way to re-close results. | #323, #326 |

### Revision area 3 / checklist §5–§7 — Session 2 (leads: Chau for rules and numbers, Danny for lock and refresh, Janice for screens)

| Requirement | Status | Current behaviour | Issue |
|---|---|---|---|
| "Email everyone" four numbers always beside the team's | 🟡 | Computed and stored (minus seats empty); shown only in the chart and a collapsed table. | #327, #295 |
| Harbor three-way view | 🟡 | Wired into the chart only. | #327 |
| One run per team per event (button, reload, second tab) | ✅ server / ❌ screen ⚠️ C6 | Enforced by a UNIQUE constraint plus an advisory lock. The screen does not show it, and a stale tab does not re-read. | #328 |
| Confirm "Send this list? You get one results run…" | ❌ | Posts immediately. | #328 |
| Results deterministic, survive reload, visible to the instructor | ✅ / ⚠️ C4 | Yes, except that a reset re-rolls the seed. | #331 |
| Results come from hidden true interests | ✅ | `simulation_profiles` reads the hidden columns only for the rule. | — |
| Asking choice only after round-one results | ❌ | Neither the server nor the screen checks for a round-one run. | #329 |
| Three options, "You chose: …", clear whether it can change | 🟡 | Choice is fixed by design and the screen says so; no visible "You chose" next to the button. | #321 |
| Refresh summary, time, before→after, changed profiles, "Already refreshed at …" | ❌ | Only a three-number band; the per-profile overlay data exists on the server. | #329 |
| Shares ~30/55/80%, ~15% stop responding | ✅ | `exercise/asking.py:80-92`. | — |
| Stopped-responding profiles marked or excluded on Harbor | ❌ | Neither marked nor excluded. | #329 |
| Refresh-all label and per-team report | 🟡 | Skipped teams are a count only; teams that haven't chosen or already refreshed are not reported. | #330 |
| Harbor list uses refreshed profiles | ✅ | Team view = base file plus overlay. | — |
| "Small reward" / "required" visibly better in round two | ❌ untested | No test checks the spread; design risks noted. | #336 |

### Revision area 4 / checklist §4 — matching rules (lead: Chau; Janice for 4c–4e)

| Requirement | Status | Current behaviour | Issue |
|---|---|---|---|
| 4a — a matching interest counts in full | ❌ / ⚠️ C7 | Jaccard; the plan is on this branch. | #289 |
| 4b — no undecided credit on Northline | ⚠️ C1 | Gives 0.5 per OQ-CE-14. | #322 |
| 4c — one reason line and Ann's phrases | ❌ / ⚠️ C2 | Two lines today; the precedence hides her phrases. | #320 |
| 4d — years in class order | ❌ | The web sorts alphabetically. The Oct 4 plan's matrix row 10 says "implemented" — **that is incorrect**. A mislabelled row was also found. | #332 |
| 4e — browser tab title | ❌ | Static `index.html:7` title. | #267 |
| The list stops at 30 and says so | ✅ | "Cut at {invite_limit} names…" (small, muted text). | — |
| P004 test | ⚠️ C3 | — | #293 |
| A line names any major or year with nobody on the list | ✅ | `exercise_list_coverage.py:145-160`. | — |
| Compare view: highlight, on both / only one / major alone | 🟡 | Highlight and "on both" are done; the other two counts are missing. | #333 |
| Download columns; pink columns absent | 🟡 | Pink columns are safe. The `marker` column holds raw keys rather than "how much we know"; there is no negative byte test. | #335 |

### Revision area 5 / checklist §3a — event descriptions (lead: Janice)

| Requirement | Status | Issue |
|---|---|---|
| Description above the sliders and beside each event on the instructor page, read from the workbook | ❌ (and blocked by B1) | #318, #325 |

### Checklist §3 and §9 — entry, projector, title

| Requirement | Status | Issue |
|---|---|---|
| Opening screen sentence and license line | ✅ (Ann's D13 wording is already shown; confirm with Ann, since her checklist says "once Ann provides it") | #273 |
| "You are Team 3" on every page, and a visible way to switch | ❌ | #268, #321 |
| Visible "Round one / Round two"; Harbor "opens after round one" | ❌ (the word "Round" is screen-reader-only) | #334 |
| Load under 5 s; readable from the back row | Manual check | #299 |

---

## 3. Action plan to 2026-10-14

The plan has four tracks. Within a track, items are in dependency order. Owners follow the leads Ann named on Oct 2. Justin has no GitHub handle, so he is named in the issue bodies and not assigned.

### Track 0 — this week, before anything else (Danny)

1. **#325** — fix the 500-character cap so Ann's workbook uploads. It unblocks #318 and the clean-up.
2. **#323** — record the deployed SHA. Re-triage Ann's observations against it.
3. **Email Ann** with the decision questions in §4, which gate Track 1.

### Track 1 — rule decisions, then matching (Chau; Janice on wording)

| Order | Item | Issue | Depends on |
|---|---|---|---|
| 1 | Decide C1 (Northline-only recommended) and C7 (past-event bucket) together; record dated decisions | #322, #289 | Ann's reply |
| 2 | Decide C2 tie and major-only precedence (supersede OQ-CE-12's precedence line) | #320 | 1 (the tie rate depends on the factor rules) |
| 3 | Implement #289 plus the #322 rule plus the #320 server wording in **one PR** on this branch; bump the registry to `exercise-0.2.0`; re-pin goldens once | #289, #322, #320 | 1, 2 |
| 4 | Decide C3 (P004) and C4 (reset seed) | #293, #331 | Ann's reply |
| 5 | Check the round-two lift per asking choice; propose coefficients if it is flat | #336 | 3 |

### Track 2 — server additions (Danny)

| Order | Item | Issue |
|---|---|---|
| 1 | Re-closable results with timestamps (migration, grant, route) | #326 |
| 2 | `results_open` / `results_run` on `EventView`; locked-sentence wording | #328 |
| 3 | `refreshed_at`, summary counts, before→after counts, `refresh_change` on list entries; round-one gate on the asking choice | #329 |
| 4 | Per-team refresh-all report | #330 |
| 5 | Instructor detail: weights, names, results (with #271) | #319 |
| 6 | Event description column (migration `0044`, ingest, API) | #318 |
| 7 | CSV "how much we know" column and negative test | #335 |
| 8 | Prepare the Oct 16 reset runbook (needs #325 and #326, or the re-point workaround) | #323 |

### Track 3 — screens (Janice)

| Order | Item | Issue |
|---|---|---|
| 1 | Status line, team number, per-button messages next to buttons, refresh-all confirm | #321, #268 |
| 2 | Results buttons and confirm; email-everyone tiles; Harbor three-way | #328, #327 |
| 3 | Refresh summary and changed-profile chips; refresh-all report | #329, #330 |
| 4 | One reason line (after Track 1 step 3); year order and label fix | #320, #332 |
| 5 | Descriptions on event pages and the instructor page | #318 |
| 6 | Round labels and Harbor note; compare counts; tab titles | #334, #333, #267 |
| 7 | All new copy into DESIGN.md §11.1 for Ann's sign-off | (each issue) |

### Track 4 — acceptance (Justin; tracked in #299)

Run the checklist row by row against the **deployed** build, with two people as two teams. Attach failures to the owning issue numbers above. Justin's two write-ups (#299) can reuse #336's numbers.

---

## 4. Questions to send Ann (by email, per her request for a record)

1. **4b:** remove the undecided half-credit on **Northline only**, or on Harbor too? Does the results rule follow? (C1)
2. **4a:** should one related past event count in full (1.0), or half (0.5)? On your file nobody has two related events, so with half credit the most anyone can get is 0.5, and 7 Harbor profiles would go down. (C7)
3. **4c:** we will show "same major; nothing else on file" and "tied on major; ordered by year" by changing the tie rule you approved on Sept 25 (OQ-CE-12). Is that the intent? (C2)
4. **P004:** with the interest weight at 0, P004 still ranks above the Accounting majors because his career goal fits Northline (D9). Keep, or change? (C3)
5. **Clearing a team:** keep the same chance draw (your checklist §8), so clearing never "re-rolls"? (C4)
6. **License line:** your Sept wording (D13) is already on the opening screen. Is it final? (#273)
7. **Descriptions:** confirm the "why someone would come" notes stay off-screen. They quote counts from the hidden columns. (C10)

---

## 5. GitHub issue map

**Filed 2026-10-05:**

- **#325** — workbook upload cap
- **#326** — re-close results and timestamps
- **#327** — email-everyone tiles and Harbor three-way view
- **#328** — results lock and one-run on screen
- **#329** — refresh summary and changed profiles
- **#330** — refresh-all report
- **#331** — decision: reset seed
- **#332** — year order and mislabelled row
- **#333** — compare counts
- **#334** — round labels and Harbor note
- **#335** — CSV column and negative test
- **#336** — round-two lift check

**Existing issues reused** (scope-gap comments added 2026-10-05 where marked †):

- **Exercise UX and features:** #267 (tab title), #268 (team number), #269 (rank order), #271 (deleted setting), #273 (license line), #318† (descriptions), #319 (instructor detail), #320† (reason line), #321† (status and feedback).
- **Matching rules and decisions:** #289† (OQ-CE-17), #293† (P004), #295 (email-everyone seed), #322† (undecided).
- **Testing and ops:** #299 (Justin's write-ups), #323† (Oct 16 reset).
