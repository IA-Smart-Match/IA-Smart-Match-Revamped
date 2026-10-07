# Oct-14 stakeholder sprint — open questions deferred to a person

**Date:** 2026-10-06 · **Slice:** Oct-14 stakeholder sprint, Lane E (decisions and ops) · **Scope:** `ProductScope.CLASS_EXERCISE` only

Ann Wang's progress check and test checklist of 2026-10-02 raised five things
engineering cannot settle alone. Each needs an answer from a named person.
None of them stopped the sprint: each has a **safe default that is what the
app does today**, so an unanswered question changes nothing on screen.

Nothing in this file changes behavior. Plans for each are in
`docs/plans/2026-10-14-stakeholder-sprint/`.

Dates: milestone board 2026-10-14 · Ann's run-through 2026-10-16 · fix-up
window ends 2026-10-30.

---

## Summary

| OQ | Question | Blocks | Safe default, in force | Who decides | Needed by |
|---|---|---|---|---|---|
| **OQ-OCT14-01** | "Email everyone" baseline: each team's own chance draw, or one draw for the whole class? (#295) | Nothing | Each team's own draw (as built) | Ann; Chau for the seed source | 2026-10-16 to be seen in the run-through, else 2026-10-30 |
| **OQ-OCT14-02** | The unused `license_line` column: retire it, or use it for wording per data file? (#273) | Nothing | Column stays, empty; the opening screen shows Ann's fixed line | Ann (one question); Danny (the migration) | 2026-10-30 |
| **OQ-OCT14-03** | Oct-16 clean-up: which path, which build, and the go-ahead (#323) | Ann's run-through starting from a clean site | Nothing is run without a written go-ahead | Danny (owner) | 2026-10-13, to run on 2026-10-14 |
| **OQ-OCT14-04** | Undecided career goal: is the Sept-25 D2 half credit superseded, and does that cover Harbor? | Merging #337; checklist §4 | **Answered 2026-10-07 (Ann): option A, every event, Harbor included.** `main` still gives the half credit until #337 merges | Answered; Danny merges #337 | 2026-10-14 |
| **OQ-OCT14-05** | When every team is switched to a new data file, does each team keep its chance seed? | Nothing | A switch still draws a new seed (as built) | Ann; Danny | 2026-10-30 |

---

## OQ-OCT14-01 — the "email everyone" baseline (#295)

**Question.** The results screen shows "email everyone (all 300)" next to the
team's own result. Today that panel uses the team's own chance draw, so two
teams can show two different "email all 300" numbers for the same event.
Should it be one number for the whole class?

**Options.**

- **A. Keep each team's own draw (as built).** A profile on the team's list has
  the same outcome in both panels, so the comparison is only "who was asked".
  Cost: six projectors can show six slightly different baselines.
- **B-ii. One class-wide baseline.** The baseline uses a draw fixed by the data
  file, and ignores each team's "stopped responding" list. Every team sees the
  same baseline. Cost: a profile on the team's list can sign up in one panel
  and not the other; under "required" the baseline no longer pays the team's
  asking cost.
- **B-i. Shared draw only.** Round-one baselines match; round-two baselines can
  still differ. Half a fix.

**Recommended default.** A. It needs no change before Oct 16, the checklist
asks only that the baseline sit beside the team's numbers, and once #331
(PR #344, open on 2026-10-07) is merged a cleared team's baseline no longer
changes. If Ann wants one number on every
projector, choose B-ii, not B-i.

**Who answers.** Ann. If B: Chau confirms the draw is fixed by the data file's
checksum.

**The exact answer needed.** "Should 'email everyone' show the same numbers
for every team, or may it differ a little from team to team the way team
results do?"

**What changes in code.**

- A: nothing. Close the backlog row with a dated line.
- B-ii: `exercise_results_run.py:263-283` (a baseline seed from
  `determinism.stable_digest` over the dataset checksum; a second `everybody`
  with no silenced set); the `ResultsView.email_everyone` description; the
  `run_email_everyone` docstring in `simulation.py` (after #337 merges); three
  tests invert (`test_exercise_results_panels.py:81`,
  `test_exercise_results_refresh.py:164`, the class-run recompute helper);
  design spec §10. No migration. Stored runs are not recomputed.
- B-i: the seed half of B-ii only.

**Blocks.** Nothing. To be visible on 2026-10-16 the answer is needed by
2026-10-13; otherwise it lands by 2026-10-30.

**Plan.** `docs/plans/2026-10-14-stakeholder-sprint/012-email-everyone-baseline-seed.md`

---

## OQ-OCT14-02 — `exercise_dataset.license_line` (#273)

**Question.** Checklist §9 says "The opening screen shows the license line
once Ann provides it." Ann provided it on 2026-09-25 and it is on the opening
screen as a fixed line (decision D13). A per-file column for it exists and has
never been filled. Retire the column, or use it?

**Options.**

- **A. Retire the column, after the run-through.** One migration and about ten
  small edits. Cost: a schema change on the shared database, so it ships in its
  own release.
- **B. Per-file addendum.** The instructor types extra wording with each
  upload; it shows on the instructor page. Cost: Ann must define the wording
  rule; it reopens D13, which rejected this.
- **C. Leave it.** Zero cost; a dead column stays.

**Recommended default.** A, scheduled after 2026-10-16. Until then C is in
force. B only if Ann asks for wording per file.

**Who answers.** Ann: one question. Danny: whether and when to drop the column.

**The exact answer needed.** From Ann: "Is the fixed line on the opening
screen what you meant in §9, or do you want different wording for each
uploaded file?" From Danny: "OK to drop the column in a release after Oct 16?"

**What changes in code.**

- A: a migration (next free revision; 0044–0046 are taken); `schema.py:133`;
  `dataset_repository.py:198-214,577,593`; `exercise_instructor_models.py:137-143,355`;
  `exerciseClient.ts:251`; `InstructorDatasets.tsx:362-363`; eight test
  fixtures; a dated line under D13; the backlog row. The exercise routes are
  not in `contracts/openapi/smartmatch.json`, so that file does not change.
- B: an upload field, one write in `dataset_repository.py`, one form field,
  new wording in DESIGN.md §11.1, a dated line under D13 reversing option (a).
- C: a dated line under D13 only.

**Blocks.** Nothing before 2026-10-16. Checklist §9 is checked live in the
clean-up runbook (step 3.7). Target 2026-10-30.

**Plan.** `docs/plans/2026-10-14-stakeholder-sprint/013-license-line.md`

---

## OQ-OCT14-03 — the Oct-16 clean-up (#323)

**Question.** Ann asked: "clear all test work under Teams 1 to 4, and set both
events back to 'results closed'." How is that done on the deployed site, on
which build, and who says go?

**What the owner must do or confirm.**

1. **Choose the path.**
   - **A. Close route, then four clears.** Teams 5–6 untouched. Needs #326
     deployed, and its grant change run as the database owner.
   - **B. Switch every team to Ann's Oct-2 file.** The switch clears all six
     teams and the new file starts with both events closed. Needs #339
     deployed. Teams 5–6 are cleared too.
   - **C. SQL fallback.** Path A, but the close is a `DELETE` run as the
     database owner. A recorded exception to the least-privilege grant. Only if
     #326 is not deployed by 2026-10-13.
2. **Name the build.** The commit to deploy before the clean-up. It must
   contain #331, or a cleared team gets a new chance draw and checklist §8
   fails. Record the `/api/health` release before and after.
3. **Give the go-ahead in writing** — date, operator, path. The runbook
   authorizes nothing.
4. **Say whether Teams 5–6 may be cleared.** Issue #323 says leave them
   untouched; path B cannot.
5. **Confirm the environment** — `exercise.plated.blog`, `synthetic_data:
   true`, and the data file's checksum equals Ann's file.

**Recommended default.** Path B if the Oct-2 file is switched in before Oct 16
(Ann asked for that switch; a switch after a path-A clean-up would redo it and
clear Teams 5–6 anyway). Otherwise path A. In A and C, close results **before**
clearing teams.

**Who answers.** Danny (owner).

**What changes in code.** Nothing under any path. The runbook is
`docs/operations/exercise-oct16-cleanup-runbook.md`. After the run, a docs PR
records the evidence table and corrects the "nothing here has been run" lines
in `exercise-hosting.md` §9 and §9b.

**Blocks.** Ann's run-through on 2026-10-16. Answers by 2026-10-13; run on
2026-10-14.

**Depends on.** #326 (close route), #331 (seed kept on a clear), #339 (Oct-2
workbook), #299 (Justin's evidence).

**Plan.** `docs/plans/2026-10-14-stakeholder-sprint/014-oct16-ops-runbook.md`

---

## OQ-OCT14-04 — the undecided career goal (Sept-25 D2 against the Oct-2 review)

> **Answered 2026-10-07 — option A.** Ann Wang, by email to Danny: "yes. An
> undecided career goal earns 0 on the career-goal factor for Harbor too, same
> as Northline. Neither of the two test events is a broad event: Northline is
> technology/information systems, and Harbor is retail/consumer goods and
> supply chain. Please remove the 'undecided fits a broad event' rule so it
> doesn't apply to any event, and check that the results rule treats undecided
> the same way (no career-goal lift). Undecided students can still make the
> list through major, stated interest, or past events."
>
> What this settles: D2's half credit is superseded on every event, in matching
> and in the results rule. "Harbor" under "Still undecided" below is closed.
> Checked on #337 with #342 (`origin/fix/pr337-audit-findings`): the results
> rule lifts only when the goal's topic is one of the event's topics
> (`exercise/simulation.py:509`), "Undecided" maps to no topic
> (`exercise/vocabulary.py:133`), and
> `test_undecided_earns_nothing_from_any_of_the_twelve_events` pins it. No new
> code is needed for this answer; #337 still has to be rebased past the `0044`
> migration collision before it can merge. Nothing on `main` changes until then.

**The conflict.** D2 (2026-09-25, Ann): an "Undecided" career goal earns half
credit on broad events, "Northline and Harbor included", in matching and in
results. Ann's review of 2026-10-02, item 4b: "It is being counted as fitting
a 'broad event.' That rule is not in the plan, and Northline is not a broad
event. Please remove it." Checklist §4: "Nobody gets credit for an 'undecided'
career goal on Northline."

**Where it stands on 2026-10-06.**

- **Open PR #337 (Chau) already carries the superseding decision.** It adds
  `docs/decisions/class-exercise-factor-revisions-2026-10-02.md`, whose header
  reads "Supersedes: D2's 'Undecided at half credit'". It puts a "Superseded
  in part, 2026-10-02" note directly under the D2 heading, marks D2's table row
  and the "What changes" bullet, updates `docs/decisions/INDEX.md`, and
  annotates the OQ-CE-14 row. So **yes: once #337 merges, D2's half credit is
  formally superseded, and no further note is needed.**
- **Its scope is wider than Ann's sentence.** Chau ruled on 2026-10-05 that
  the rule is removed on **every** event, in matching and in results, and the
  `is_exploratory` column is dropped. Ann's text names only Northline.
- **Until #337 merges, `main` still follows D2.** Checklist §4 fails on `main`.
- **A tracking issue exists: #322** ("decision: supersede OQ-CE-14 for
  Northline undecided-goal fit", assigned to Chau, on the Oct-14 milestone).
  No new issue is needed.

**Still undecided.**

1. **Harbor.** Ann has not confirmed in writing that the half credit goes on
   Harbor too. #337's own conflict analysis recommended "Northline only; ask
   Ann about Harbor". Chau's ruling stands unless Ann says otherwise.
2. **Two records to close when #337 merges.** Issue #322 still lists its three
   options as open. Open PR #324 adds a register row **OQ-CE-18** marked
   "OPEN — owner decision required" for this same question; it will be stale
   the moment #337 merges.
3. **Migration number.** #337 adds `0044_drop_event_exploratory`. This sprint's
   other lanes were also assigned 0044–0046. Whichever merges second must
   renumber.

**Options.**

- **A. Merge #337 as ruled (all events).** D2's half credit is gone everywhere.
- **B. Northline only.** Harbor keeps the half credit. A one-line change in
  `EXERCISE_EVENT_TYPES` instead; `is_exploratory` stays; #337 is reworked.
- **C. Hold.** `main` keeps D2; checklist §4 fails on 2026-10-16.

**Recommended default.** A. It is Chau's recorded ruling, it satisfies
checklist §4, and D2 itself bound matching and results together. Ask Ann the
Harbor question in the same email as the others; B stays a small follow-up if
she wants it.

**Who answers.** Chau has ruled. Ann confirms Harbor. Danny merges.

**The exact answer needed.** From Ann: "Your note removes the 'undecided'
half credit for Northline. We removed it for Harbor too. Is that right?"

**What changes in code.** Nothing from this lane. All of it is in #337
(`student_factors/factors.py`, `exercise/simulation.py`, `vocabulary.py`,
migration, goldens). Under B, #337 changes shape and the goldens are re-pinned.

**Blocks.** Checklist §4 on 2026-10-16. Decide by 2026-10-14.

**Drafted superseding note — use only if #337 does not merge first.** Place it
directly under the `## D2.` heading in
`docs/decisions/class-exercise-decisions-2026-09-25.md`:

> **Superseded in part, 2026-10-02.** Ann Wang's progress check and revisions
> of 2026-10-02, item 4b: "It is being counted as fitting a 'broad event.'
> That rule is not in the plan, and Northline is not a broad event. Please
> remove it." Chau ruled on 2026-10-05 that the half credit for "Undecided"
> is removed on every event, in matching and in the results step. The
> role→topic table below stands. The code change is PR #337; until it merges
> the app still gives the half credit. Ann has not yet confirmed that Harbor
> is included — see OQ-OCT14-04 in
> `docs/plans/open-questions/oct14-deferred.md`. The text below is left as it
> was recorded on 2026-09-25.

If #337 merges first, its own note replaces this one. Then add only one line
under it: "Harbor: Ann's confirmation pending — OQ-OCT14-04."

---

## OQ-OCT14-05 — the chance seed when every team is switched to a new file

**Question.** Since #331 a per-team clear keeps the team's chance seed
(checklist §8). A switch of every team to a new data file still draws each
team a new seed. Should the switch keep it too?

**Options.**

- **A. Leave it (as built).** A new file gets a new draw, because the switch
  gives each team a new seed. The draw is keyed on the seed, the event, the
  profile number and the purpose — not on the file — so the new seed is the
  only reason results differ where those others match.
- **B. Keep the seed across a switch.** Re-uploading the *same* file and
  switching to it would then give the same results as before.

**Recommended default.** A. Checklist §8 speaks only about clearing one team,
and the owner's ruling of 2026-10-06 covers only that.

**Who answers.** Ann, with Danny.

**What changes in code.** A: nothing. B: one line in
`instructor_repository.py` `repoint_workspaces` (drop `seed=` from the
update), one test inverts
(`test_exercise_instructor_persistence.py` `test_a_repoint_regenerates_the_seed_because_it_resets_every_team`),
the spec §11 correction note and the D7 amendment gain a clause.

**Blocks.** Nothing. 2026-10-30.

**Plan.** `docs/plans/2026-10-14-stakeholder-sprint/011-seed-preserved-on-reset.md`

---

# Part 2 — defaults taken in the shipped lanes (confirm or overrule)

Part 1 above lists what was deferred with no behavior change. This part lists
every choice a lane made in order to ship, so none of them is silent. Each is in
force on its PR branch, not on `main`, until that PR merges. Overruling one is a
small follow-up on the named PR.

## Orchestrator entries (found during review, 2026-10-06)

| OQ | Question | In force | Who decides |
|---|---|---|---|
| **OQ-OCT14-06** | CSV download: add a UTF-8 byte-order mark so Excel reads non-ASCII names? (#335, PR #338) | No mark added; data is ASCII today. A non-ASCII name would show garbled in Excel until a one-line `utf-8-sig` change. | Danny |
| **OQ-OCT14-07** | `dataset_id` is on three instructor response models on `main` (`exercise_instructor_models.py:129,209,309`). The sprint rules ban it on response models. Intended instructor-only exception, or remove? | Untouched by every sprint PR. | Danny |
| **OQ-OCT14-08** | Ann's Oct-2 workbook is committed as a test fixture with both hidden-truth columns (PR #339), as the September fixture already is. Ann asked that the file not reach class participants. | Acceptable only while the repository is private to the team. | Danny |
| **OQ-OCT14-09** | `event_description` is optional, so removing that column from an upload is accepted without a message. Ann's "remove a column on purpose" check shows the plain error only for a required column such as `seats`. | Optional (old files stay valid). | Ann |
| **OQ-OCT14-10** | Deploy rollback (PR #343): after a tolerated rollback past a newer schema, a VM reboot runs a plain `up -d` and the old `migrate` step fails again. Follow-up before merge, or accept the gap? | Documented as a known gap in `docs/operations/deploy-runbook.md`. Not exercised on a real VM. | Danny |
| **OQ-OCT14-11** | Two words for one act: team screens say "Refreshed at 10:42 AM" (Ann's wording, PR #340); instructor rows say "Has already asked." / "Asked at 10:42 AM." (PR #345). Unify? | Both kept. | Ann |
| **OQ-OCT14-12** | The VM's `/opt/smartmatch/exercise-setup.sh` is outside the repository. If it re-applies the old `SELECT, INSERT` grants, every open/close press fails after #345 deploys. | Unverified — check on the VM (runbook step). | Danny |


---

## Lane A open questions — #325, #318 (PR #339)

Each entry: question, options, default taken, what changes if the answer differs. All defaults are live on branch `oct14/event-descriptions`.

### OQ-A-01 — How long may an event description be?

- **Question.** Ann's two descriptions are 571 and 561 characters; the cell cap is 500. What is the new limit, and for which cells?
- **Options.** (a) 2,000 characters for `Events.event_description` only; headings and every other cell stay at 500. (b) Raise the cap for every cell. (c) A different number.
- **Default taken.** (a).
- **If the answer differs.** (c) is one constant: `EVENT_DESCRIPTION_MAX_CHARACTERS` in `python/smartmatch_domain/smartmatch_domain/exercise/layout.py`, plus the `2000` in three test sentences and one DESIGN.md §11.1 row. (b) is `MAX_CELL_CHARACTERS` in `workbook.py` and removes the need for `cell_limits`.

### OQ-A-02 — Is `event_description` a required column?

- **Question.** Must every uploaded file carry the column?
- **Options.** (a) Optional: a file without it uploads and shows no descriptions. (b) Required: a file without it is refused with "The Events sheet is missing the column event_description."
- **Default taken.** (a).
- **Consequence to confirm with Ann.** Her checklist says "upload a workbook with one column removed … a plain message naming the missing column". Under (a), removing `event_description` itself is accepted silently, exactly like `event_date`, `info_level` and `events_attended_count`. Removing any of the 19 required columns (for example `seats` or `event_topics`) gives the plain refusal. The run-through should remove a required column.
- **If the answer differs.** (b): move `event_description_column` from `optional_event_columns` into `event_columns` in `layout.py`; the September fixture then becomes a refusal case, `good_workbook()` and `EVENT_HEADINGS` in `tests/unit/exercise_workbooks.py` gain the column, and `ANN_FULL_FILE` must point at the October file (golden tests follow).

### OQ-A-03 — Backticks in upload refusals

- **Question.** The parser quotes names in backticks and the page prints them literally. Ann asked for "a plain message".
- **Options.** (a) The upload route drops the backticks from the sentence it sends. (b) The page renders backticked names as code. (c) Rewrite every parser sentence without them. (d) Leave as is.
- **Default taken.** (a). One line at the route (`plain_sentence` in `exercise_instructor_models.py`); the parser's ~50 sentences and their tests are untouched.
- **If the answer differs.** (d): remove the `plain_sentence` call and restore backticks in two router tests and two DESIGN.md §11.1 rows. (b): same removal, plus a small renderer in `InstructorDatasets.tsx`.

### OQ-A-04 — The upload success message

- **Question.** Checklist §2 asks for: file name, "300 profiles, 12 events loaded."
- **Options.** (a) One sentence composed on the page from the server's file name and counts, above the existing "teams have not moved" notice and the counts grid. (b) Same sentence, and remove the grid. (c) A server-authored sentence field.
- **Default taken.** (a): `SmartMatch_Student_Body_300.xlsx — 300 profiles, 12 events loaded.`
- **If the answer differs.** (b) deletes the `<dl>` in `InstructorDatasets.tsx`. (c) adds a field to `UploadedDatasetView` and its hand-mirrored client type.

### OQ-A-05 — The Oct-2 fixture and the `.accdb` (manual step open)

- **Question.** How is Ann's Oct-2 workbook committed, and what happens to the Access copy?
- **Options.** (a) Add it as a second file beside the September one, cut the same way (Profiles + Events, properties reset), and leave the `.accdb` mirroring September. (b) Replace the September file in place.
- **Default taken.** (a): `tests/fixtures/exercise/SmartMatch_Student_Body_300_10022026.xlsx`, force-added. Built with openpyxl from `docs/10-2-2026/SmartMatch_Student_Body_300_10022026.xlsx` (source not edited); verified cell-for-cell equal to the source on both sheets, and equal to the September fixture on every shared column. `lastModifiedBy` ("Ann Wang") was removed with the other document properties, as the September fixture has none.
- **Not done — needs a person.** The `.accdb` has no `event_description`. Rebuilding it needs Microsoft Access on Windows. `tests/fixtures/exercise/README.md` says so under "Open manual step". `test_data/event_major_fit.csv` is unaffected (profiles and the other event columns are identical).
- **If the answer differs.** (b): delete the September file, rename the October one over it, and rebuild the `.accdb` first (README rule 1).

### OQ-A-06 — Description on the picker card

- **Question.** Ann named two places: the top of the Northline and Harbor pages, and the instructor page. Issue #318 also lists the round card on the event picker.
- **Default taken.** Shown in all three. On the card the link is named by "Round N" and the event name and described by the rest, so a 571-character paragraph does not become the link's name.
- **If the answer differs.** Remove one `<EventDescription>` line and the `aria-*` ids from `RoundCard` in `ExerciseEventPicker.tsx`.

### OQ-A-07 — Migration number collision with PR #337 (for the owner, not Ann)

- This PR adds `0044_exercise_event_description`. PR #337 adds `0044_drop_event_exploratory`. Both chain to `0043`. Whichever merges second must set its `down_revision` to the other's revision, renumber if wanted, and move the six pinned heads (`tests/integration/test_cba_contact_schema.py`, `test_cba_weight_settings_persistence.py`, `test_event_filed_by_migration.py`, `test_exercise_schema_migration.py`, `test_host_organization_migration.py`, `test_speaker_availability_migration.py`) plus the chain list in `test_cba_contact_schema.py`.
- Shared files both PRs edit: `layout.py`, `ingest.py`, `schema.py`, `dataset_repository.py`, `exerciseClient.ts`. This PR's edits there are additive (one field, one column, one property).

---

## Lane B open questions — defaults taken (PR #345)

Issues #326, #328, #319, #271. Branch `oct14/results-lock-snapshot`. Written 2026-10-06.

Each entry: the question, the options, the default taken, and what changes if the answer differs. B-0 is not a default; it is a deviation from the assignment that someone must know about.

### B-0. Revision ids could not be the assigned ones (deviation, not a default)

- **What happened.** `alembic_version.version_num` is `VARCHAR(32)`. The assigned ids are 37 and 33 characters. PostgreSQL refused the first: `value too long for type character varying(32)`.
- **What shipped.** File names as assigned; revision ids shortened, as `0040_speaker_booking_cancellation.py` → `0040_booking_cancellation` already does.

  | File | Revision id | Down revision |
  |---|---|---|
  | `0045_exercise_result_unlock_closed_at.py` | `0045_exercise_unlock_closed_at` | `0044_exercise_event_description` |
  | `0046_exercise_result_run_snapshot.py` | `0046_exercise_run_snapshot` | `0045_exercise_unlock_closed_at` |

- **Who is affected.** Any lane that chains a migration after Lane B must use `down_revision = "0046_exercise_run_snapshot"`, and must bump the six `HEAD_REVISION` pins and README from that id.

### B-1. May "already run" be checked before "locked"? (#326)

- **Options.** (a) Keep D16's order: locked, then already run. (b) Already run first.
- **Default taken.** (b). Recorded as the D16 amendment of 2026-10-06 in `docs/decisions/class-exercise-decisions-2026-09-25.md`.
- **Why.** Results can now be closed again. A team that ran, then presses again after the close, has had its one run; "not open yet" would tell it to wait for a second one.
- **If the answer is (a).** Swap two `if` blocks back in `runnable_or_refusal` (`exercise_results_run.py`) and one test. The screen still shows "already run" from the read, so only the POST's sentence changes.

### B-2. What does `unlocked_at` mean after results are opened a second time? (#326)

- **Options.** (a) First-ever opening, never overwritten. (b) Most recent opening.
- **Default taken.** (b). A reopening sets `unlocked_at = now()` and clears `closed_at`.
- **Why.** Ann asked that the page show "the time it was done". One row cannot keep every cycle either way.
- **If the answer is (a).** Add a column for the first opening (new migration); the page keeps showing the latest.

### B-3. Should the instructor's events list work before any team has entered? (#326, #323)

- **Options.** (a) No change: "No team has entered a number yet." (b) Read-only fallback to the newest data file when zero teams exist. (c) Let open/close also fall back.
- **Default taken.** (a). No behavior changed.
- **Why it is safe for Oct 16.** Clearing a team keeps its workspace row (`reset_team` deletes the team's work and regenerates the seed only). So clearing Teams 1–4 does not empty the list, and "close both events" works before or after. The runbook now says close first anyway.
- **What it does not cover.** A brand-new site with no team ever entered shows that sentence instead of two events reading "Results closed". Checklist §2 line "Both events show “Results closed” at the start" is met only once a team row exists.
- **If the answer is (b).** One fallback in `_teams_dataset` for GET only (`exercise_instructor.py`); its docstring argues against it today, so it needs the owner's say.

### B-4. Where does the team-side lock read live? (#328)

- **Options.** (a) Two fields on `EventView`, filled by `read_events`. (b) A new `GET …/events/{event_key}/results-state` route.
- **Default taken.** (a), as the issue plan and the shared-seams table say. #321 reuses the same fields.
- **If the answer is (b).** Move two reads to a new route; the screen's `eventResultsState()` changes one call.

### B-5. How is the event named in the team's sentences? (#328)

- **Options.** (a) The file's full `name`: "Northline Analytics: Behind the Business". (b) A short name: "Northline", as in Ann's examples.
- **Default taken.** (a). The data file has no short name; inventing one in code would break when Ann changes the file.
- **Result on screen.** "Results for Northline Analytics: Behind the Business are not open yet. Ask your instructor." and "Send this list? You get one results run for Northline Analytics: Behind the Business".
- **If the answer is (b).** Needs a short-name column in the workbook (Lane A's layout) or a rule for shortening; then two sentence builders change.

### B-6. How fresh must the team's button be? (#328)

- **Options.** (a) Read on load, re-read after a refused press, plus a "Check again" button. (b) Poll, as the instructor's Teams panel does.
- **Default taken.** (a). Checklist §5 allows "after a page reload at most".
- **Kept as it was.** The live button's own label stays "Run results for this event"; only the armed question is Ann's "Send this list? …".
- **If the answer is (b).** Add a timer and a `visibilitychange` listener to `ExerciseResults.tsx`; #321's status band may want the same.

### B-7. Shape of the run snapshot (#319, #271)

- **Default taken (the brief's).** Two nullable JSONB columns on `exercise_result_run`:
  - `invited_profiles`: list of `{rank, profile_no, display_name, major, class_year, marker, reason}` in rank order;
  - `setting_weights`: the four stated weights.
- **Old rows.** Backfilled in SQL with `profile_no`, `display_name`, `major`, `class_year` only, in stored (profile-number) order. `rank`, `marker`, `reason` are **not** written; the API serves them as `null`.
- **If a different shape is wanted.** The stored shape is parsed in one place (`results_rows.invited_from_json`); the wire shape is `InvitedProfileView`.

### B-8. Who decides that a run's setting "was deleted"? (#319)

- **Options.** (a) Server bool `setting_deleted`. (b) The page works it out.
- **Default taken.** (a): true when the team has no saved setting of that name for that event now.
- **Known limit.** A setting deleted and saved again under the same name reads as not deleted. `setting_weights` on the run still shows what the run actually used.

### B-9. "Email everyone" counts on the instructor's view of a run (#319)

- **Options.** (a) Leave them off. (b) Add the three counts.
- **Default taken.** (a). The brief marks it a scope check; Ann's list of what the instructor sees does not include it.
- **If the answer is (b).** Select `email_everyone` in `instructor_team_work.select_result_runs`, three count fields on `ResultRunView`, one line on the page.

### B-10. "Refreshed" or "asked" on the instructor's team view? (#319; shared with #329)

- **Options.** (a) The page's existing words: "Has not asked yet." / "Asked at 10:42 AM." (b) Ann's word: "Refreshed at 10:42 AM."
- **Default taken.** (a), to match the Teams row above it. Composed on the page, so the server's no-"refresh" rule is not involved.
- **If the answer is (b).** One function, `askingSentence` in `InstructorTeamDetail.tsx`, and its three tests. Whatever #329 decides for the team side should be applied here too.

### B-11. May old runs' weights be backfilled from the saved setting as it is today? (#319, #271)

- **Options.** (a) Yes, where a setting of that name still exists. (b) Leave `setting_weights` NULL on every old run.
- **Default taken.** (a), the brief's.
- **Risk.** A setting re-saved under the same name since the run shows its newer numbers on that old run. The Oct-16 clean-up clears Teams 1–4, so no old run should survive to the run-through.
- **If the answer is (b).** Remove one `UPDATE` from migration 0046 before it is applied anywhere; after that, a one-line data fix.

### B-12. Chip wording differs between the two sides (#326, #328)

- **What shipped.** Instructor page: "Results open" / "Results closed" (checklist §2, word for word). Team lock panel: "Results are closed" (unchanged).
- **Why.** The checklist gives wording only for the instructor's labels and the team's buttons. The team's chip was approved on 2026-09-26 and nothing asks to change it.
- **If one wording is wanted.** One string in `ResultsLockPanel.tsx` and two test lines.

---

## Lane C open questions — refresh visibility (#329, #330)

PR #340, branch `oct14/refresh-visibility`. Every entry is a brief-recommended default that was taken to ship. Confirm or overrule; "if different" says what changes.

### C1 — Profiles that "stopped responding": mark or leave off the list? (Chau)

- Options: (a) mark them on the list; (b) leave them off every list.
- Default taken: **(a) mark**. Chip "Stopped responding" beside the name. They still never sign up in round two.
- Source: checklist §7 allows either; brief #329 §5.1 recommends mark.
- If different: `rankable_set` would drop `non_responding` rows. That shrinks every list, moves the "who is on the list" counts and round two's invitable pool. Not a copy change.

### C2 — "Refreshed" or the product's word "asked"? (Chau / Ann)

- Options: (a) Ann's Oct-2 words for the outcome ("Refresh done at…", "Already refreshed at…"); (b) keep the product voice ("Your team asked at…").
- Default taken: **(a)**, composed in the browser (`refreshWording.ts`). The button that starts it still reads "Ask them now"; server refusals still say "asking".
- Known seam: one screen now uses both words (button "Ask them now" → shut label "Already refreshed at 10:42 AM"). The instructor Teams rows still read "Has already asked." / "Has not asked yet."
- If different: edit strings in `refreshWording.ts` and DESIGN.md §11.1 only. No contract change.

### C3 — Refusal code for a choice made before round one (Danny)

- Options: (a) reuse `exercise_no_first_round_results`; (b) a new code.
- Default taken: **(a)**, sentence "Run the first round's results before asking."
- If different: one new code + one sentence in `exercise_results.py`; the screen does not branch on it.

### C4 — Before round one: hide the three choice cards, or show them greyed? (Ann)

- Checklist: "The choice appears only after the team has its round-one results."
- Default taken: **hide**. One line stands in their place: "Your team picks a way of asking after it has its results for Northline."
- If different: render the cards with a disabled state (the card component has none today).

### C5 — Where the "went to Northline" name comes from (Danny)

- Default taken: server fields `AskingStateView.first_round_event_name` and `RankedListView.first_round_event_name` (the first exercise event by sequence). No extra request on the matching screen.
- If different: drop the two fields and read `GET …/events` on each list screen.

### C6 — Server gate on the choice makes one state unreachable (Danny)

- Fact: the API now refuses a choice before round one, so "chosen, no round-one run" cannot be produced through the routes. The refresh-all reason `no_round_one_run` and the team refusal for it remain, and are tested with a directly seeded choice.
- It can still occur for rows written before this change (e.g. live Teams 1–4 until they are cleared).
- If different (gate only in the UI): remove four lines in `choose_asking` and revert three test setups.

### C7 — Reason codes for skipped teams (Danny)

- Default taken: `no_asking_choice | no_round_one_run | already_refreshed`. A claim lost mid-request is re-read and named `already_refreshed` or `no_asking_choice`, never `no_round_one_run`.
- If different: the set is a `Literal` on `RefreshAllTeamView.reason_code`; the client renders an unknown code as "Skipped."

### C8 — Do never-entered teams appear in the report? (Ann)

- Options: (a) only teams that exist; (b) always six lines, with "has not entered".
- Default taken: **(a)**, as the Teams panel does.
- If different: add outcome/reason `not_entered` synthesised over team numbers 1–6 per data file.

### C9 — Two data files in one class (Danny)

- Default taken: every entry carries `dataset_label`; the screen shows it ("Team 3 (October file):") only when the report spans more than one file. `dataset_id` is never sent.

### C10 — Every-team button copy (Ann)

- Default taken: title "Refresh every team at once"; button "Refresh every team that has chosen how to ask"; in progress "Refreshing every team…". Full list in DESIGN.md §11.1.
- #321's "Are you sure?" confirm is not added here; `RefreshAllPanel.send` is the single place the request is made.

### C11 — Clock format (Ann)

- Default taken: browser local time, `en-US`, "10:42 AM".
- If different: one `Intl.DateTimeFormat` line in `refreshWording.ts`.

---

## Lane D — open questions and defaults taken (#335, branch `oct14/download-labels`)

No owner gate blocks #335. Three small choices were open in the brief (§5). Each took the conservative option.

### D-1 — Byte-order mark on the downloaded CSV

- **Question:** should `list.csv` start with a UTF-8 byte-order mark so Excel always reads it as UTF-8?
- **Options:** (a) no BOM — bytes unchanged from today; (b) encode the body as `utf-8-sig` in `download_ranked_list`.
- **Default taken:** (a), not added. The brief recommended (b); the lane prompt says to take the conservative option.
- **Why:** the checklist does not ask for it; names, majors, years, marker phrases and reason sentences are ASCII in Ann's current file, so Excel opens it correctly today; a BOM changes the response bytes for every consumer.
- **If the answer differs:** one line in `services/api/smartmatch_api/routers/exercise_matching.py` (`content=ranked_list_csv(view).encode("utf-8-sig")`) plus one test. Needed the day a data file carries a non-ASCII name (e.g. "José") — without it Excel shows such a name garbled.

### D-2 — Where the server's marker words live

- **Question:** the lane prompt says reuse the existing label source, no second copy. The only existing source is `apps/web/legacy-frontend/src/app/pages/exercise/markers.ts` (`MARKER_LABELS`), which Python cannot import.
- **Options:** (a) one server map (`MARKER_WORDS` in `smartmatch_domain/exercise/markers.py`) pinned to `markers.ts` by a test that reads the TypeScript file; (b) build the CSV in the browser from the JSON list using `markerLabel`; (c) send the words on the API and delete `MARKER_LABELS`.
- **Default taken:** (a).
- **Why:** (b) moves the download out of the server route and its formula-neutralising guard; (c) changes the `ListEntryView` contract and the chip's icon keys. Both are bigger than the issue. With (a) `markers.ts` stays the wording source and `test_the_csv_words_are_the_words_the_screen_file_holds` fails if either side is reworded alone.
- **If the answer differs:** choosing (c) later removes `MARKER_LABELS` and that parity test; the CSV writer keeps calling `marker_words`.

### D-3 — Header spelling

- **Question:** `how much we know` (checklist, and `dimensionLabel("marker")`) or `How much we know` (the on-screen table header in `RankedList.tsx`)?
- **Default taken:** lowercase, matching the other five lowercase headers and the checklist verbatim. `reason` stays `reason` (not "the reason").
- **If the answer differs:** one string in `CSV_LIST_COLUMNS` and the literal in `_CSV_HEADER` in the test.

### Not done on purpose

- No mark / refresh-mark column, no seventh column of any kind (pinned by literal in two tests).
- #295 (email-everyone baseline seed): untouched, no plan written — other agent's.
- `docs/superpowers/specs/2026-09-16-class-exercise-design.md:243-244` still says "marker" for the fifth column; it is a dated spec and was left as written.

---

## Lane F open questions — team status line and feedback (#321)

Branch `oct14/status-band`, stacked on #339 → #345 and on #340. Every entry is a default taken to ship. Confirm or overrule; "if different" says what changes. None needs a migration or a server change.

### F1 — Which pages carry the status line? (Ann / Danny)

- Options: (a) the four team pages; (b) also the opening screen; (c) also the instructor page.
- Default taken: **(a)** event picker, matching, results, asking. Not the opening screen (no team yet; it already says "This browser is already in team N"). Not the instructor page (it lists every team itself).
- Also taken: the line is at the top of each page and is **not pinned** while the page scrolls. The matching page already has a sticky weights panel and a sticky phone bar.
- If different: (b)/(c) is one prop on that page's `ExerciseScreen`. Pinning is a CSS change plus a check against the two sticky elements on matching.

### F2 — What "which event, round one or round two" shows (Ann)

- Options: (a) both rounds always, each with its results state, the page's own round marked "(this page)"; (b) only the page's event on event pages and nothing on the picker and asking pages; (c) one "current round" guessed from progress.
- Default taken: **(a)**. Example: "Round 1 · Northline…: Results used · Round 2 · Harbor…: Results not used yet (not open yet)". No guess about which round a team "is in".
- If different: `teamStatusItems` in `teamStatusWording.ts` and its test. (c) needs a rule from Ann for what "current" means.

### F3 — The line says whether results are open, not only whether they are used (Ann / Danny)

- Fact: #345 gave teams a read of the lock (`EventView.results_open`). The line reuses it: "Results not used yet (open now)" / "(not open yet)".
- Default taken: **show it**. DESIGN.md §6.14's 2026-10-06 note is extended, not duplicated.
- If different: drop the bracket in `resultsWords`; two values remain ("Results used" / "Results not used yet").

### F4 — Does the team's own refresh ask first? (Ann)

- Checklist §6 says "After pressing it, a summary appears"; it asks for a confirm only on class-wide buttons. Brief #321 gate 4 recommends matching the choice and the run, which both ask.
- Default taken: **ask**. First press: "Ask them now? Your team can ask only once" + "Press again to ask. Your team cannot ask a second time, and it cannot be undone." Second press inside 5 s sends. Same on Asking and Results (`AskOnceButton.tsx`).
- This changes existing behavior (one press → two). It is the only such change in the lane.
- If different: render the plain `Button` again in two places and revert 12 test presses. No contract change.

### F5 — Form of the refresh-every-team confirm (Danny)

- Options: (a) two-button inline question in the panel, as open/close results, clear a team and move every team use; (b) the 5-second arm-and-press window on the button.
- Default taken: **(a)**. The scope sentence is 36 words; it cannot be read against a 5-second timer, and the three sibling confirms on that page are all (a).
- Copy: "Refresh every team that has chosen how to ask? Each of those teams is refreshed once, and that cannot be undone or done again. Teams that have not chosen, and teams already refreshed, are not changed." / "Refresh them now" / "Not yet".
- If different: swap the well for `useConfirmWindow` in `RefreshAllPanel`; the sentence would have to shrink to fit a button.

### F6 — "Refreshed" and "Asked" are both in use for the same act (Ann / Chau)

- Where each is used now:
  - "Refreshed": team screens ("Already refreshed at 10:42 AM", "Refresh done at…"), the status line ("Refresh: Done at 10:42 AM"), the instructor's every-team panel and report.
  - "Asked": instructor Teams rows ("Has already asked." / "Has not asked yet."), instructor team detail ("Asked at 10:42 AM."), the button that starts it ("Ask them now"), every server sentence.
- Default taken: **not unified.** Each string left as its lane shipped it. New strings follow their screen: the status line says "Refresh" (Ann's status-line word), the new confirm on the team button says "Ask" (the button's word).
- Recommended wording if Ann wants one word: **"refreshed"** for the outcome everywhere a person reads it — instructor rows "Refreshed at 10:42 AM." / "Not refreshed yet.", detail "Way of asking: A small reward. Refreshed at 10:42 AM." — and keep "Ask them now" for the button, because it says what the team does. Server sentences stay "asking" (the wording scan forbids "refresh" there).
- If different: strings in `InstructorTeams.tsx`, `InstructorTeamDetail.tsx`, their tests and DESIGN.md §11.1. No contract change.

### F7 — "Not your team? Pick again" in the status line (Danny)

- Checklist §3: "There is a visible way to switch team number if someone picked the wrong one." It overlaps #268.
- Default taken: **included**, as a link to `/exercise`. It only navigates; the opening screen's existing rules decide what entering again does.
- If different: remove one `<Link>` in `TeamStatusBand.tsx`.

### F8 — Times that have no server timestamp (Danny)

- "Team 3 cleared at 10:42 AM.", "Checked at 10:43 AM. Results are still not open." and "Teams last read at 10:43 AM." use the browser's clock when the answer landed. The reset route returns no time, and a read has none.
- "Run at 10:42 AM." and every refresh time are the server's (`ResultsView.created_at`, `refreshed_at`).
- Default taken: **browser clock for those three**, stated in DESIGN.md §6.24.
- If different: a `cleared_at` on the reset response (additive field, mirrored in `exerciseClient.ts`); the other two have nothing to store.

### F9 — Extra reads per page (Danny)

- The status line makes three GETs of its own on each team page (workspace, events, asking). Results and Asking already read two of them, so those are read twice per load.
- Default taken: **accept it** — one self-contained component, no page hands data to it, and no rate limit applies to these routes (only the instructor login is limited).
- If different: a `GET …/workspaces/current/status` aggregate (brief gate 1), or pages passing their data in. Both are larger changes.

### F10 — Presses audited and left as they are

- The download link (the browser's own download bar is the sign), "Try again" (the notice is replaced by the answer), the instructor's "Check again" on the unlock list when no file resolves (shows the server's sentence again), and "Go back to this list's weights" (the boxes and the list change in place).
- If Ann fails any of these on Oct 16, each is a one-sentence addition in the pattern used here.
