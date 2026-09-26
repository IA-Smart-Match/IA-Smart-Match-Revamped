# Class exercise: decisions D1–D16 (wave 2)

**Status:** Record of decisions already made. Every decision below was approved
by the person named in its row, on the date named. This file decides nothing
new; it writes the decisions down in one place.
**Recorded:** 2026-09-25, by the team, for Danny (owner) and Chau.
**Scope:** `ProductScope.CLASS_EXERCISE` only (Dr. Lin's Spring 2027 AI in
Marketing course).
**Code references:** `origin/main` at `9339d5a4` (PRs #227–#234 merged).
**Register:** [`class-exercise-open-questions.md`](../plans/open-questions/class-exercise-open-questions.md)
**Architecture:** [ADR-0025](../architecture/decisions/ADR-0025-class-exercise-scope-shares-the-matching-mechanism.md),
amended 25 September 2026 for D3 and D6 (see "Why this file, and the ADR
amendment" at the end).
**Design:** [`2026-09-16-class-exercise-design.md`](../superpowers/specs/2026-09-16-class-exercise-design.md)

---

# Part 1 — In plain words (for Chau and Ann)

## What was decided

| # | The question | The answer | Who decided, when |
|---|---|---|---|
| D1 | What file does the instructor upload? | Ann's `.xlsx`, exactly as she sends it. No converting to CSV first. | Danny (owner), 2026-09-24 |
| D2 | Which events does each career goal fit? | Each "<field> role" fits its field. "Start my own business" fits Entrepreneurship. "Graduate school" fits no event topic. "Undecided" gets **half credit** on broad events (career fairs, industry panels, employer info sessions, employer talks — Northline and Harbor included). The results step treats undecided students the same way. | Danny drafted 2026-09-24; Ann confirmed and added the half-credit rule 2026-09-25 |
| D3 | When two students tie all the way down, who comes first? | The fixed order in Ann's `tiebreak_order` column. | Danny (owner), 2026-09-24 |
| D4 | Are Ann's files kept in the code repository? | Yes, as test data. The Read Me and Benchmark tabs were removed. | Danny (owner), 2026-09-24 and 2026-09-25 |
| D5 | Can a team run results without choosing a final setting? | No. The team must pick one saved setting first. | Danny (owner), 2026-09-24, from Ann's flow |
| D6 | When the refresh gives a student a new card, what goes on it? | The student's hidden true interests **and** hidden true career goal. | Ann's Read Me, 2026-09-24 |
| D7 | What numbers drive the simulated results? | Start at 4 in 100. A lot = +40 (half interests, half goal). Some = +10 for anyone who went to at least one past event. A little = +4 for the right major. Chance = up to 10 either way. 75 in 100 of sign-ups attend. | The team translated Ann's words; **Chau approved** (Ann delegated the numbers to Chau), 2026-09-25 |
| D8 | How are empty seats shown? | Show both groups: "8 were already coming. Your invitations added 6. 46 seats are still open." | Team recommendation; **Chau approved**, 2026-09-25 |
| D9 | Ann's P004 test case: change anything? | No. Keep it as built. Ann may revisit. | Team recommendation; **Chau approved**, 2026-09-25 |
| D10 | How does a developer's empty database get Ann's data? | A seed command (`make exercise-seed`), plus an optional seed-on-start that runs only on a developer's machine. | Danny (owner), 2026-09-25 |
| D11 | Which file does the instructor's unlock panel list? | The file the teams are using, not the newest upload. | Implementer ruling in PR #232, accepted |
| D12 | "Asking for more" lands on a half (16.5 of 30). Round up or down? | Up. | Danny, 2026-09-25; Ann gave no view |
| D13 | What license line goes on the opening screen, and where does it live? | Ann's wording, fixed in the app: "For California State Polytechnic University, Pomona — College of Business Administration instructional use only. All student profiles are fictional." | Ann's wording, 2026-09-25; fixed in the app in PR #230 |
| D14 | What does the profile card ask? | Only interests and career goal. The student confirms the major on file. | Ann, 2026-09-25 |
| D15 | How do we describe the data? | "Fictional profiles shaped by overall survey percentages." If a count is ever needed: 1,370 surveys. Nothing about individual people or their answers. | Ann, 2026-09-25 |
| D16 | If a run is refused for several reasons, which reason does the team see first? | "Locked" and "already run" first, then "choose a final setting", then the rule's own check. | Implementer ruling in PR #227, accepted |

## What changes in the app

- **The results screen works.** The numbers in D7 are live. A change is one
  line in `simulation.py`.
- **Undecided students** now reach broad events at half strength, both in the
  ranked list and in the simulated results (D2).
- **Empty seats** will read as three short sentences (D8). This is being built
  now on branch `feat/ce-results-integration`.
- **Nothing else visible changes.** D3, D5, D6, D11, D12, D13, D14 and D16 are
  already in the app. D1, D4 and D10 are for the people running it.

## What is still open

Nothing is waiting on Ann or Chau. Ann receives the
[sample result](../plans/open-questions/oq-ce-03-sample-result.md) for
information. If she reacts to the numbers (D7) or to P004 (D9), each is a small
change. The only open register row is OQ-CE-06: the team still has to apply
the rate-limit rule at the proxy.

---

# Part 2 — Each decision in full (for the builders)

Every `file:line` below is on `origin/main` at `9339d5a4`. Paths are shortened:

- `domain/` = `python/smartmatch_domain/smartmatch_domain/`
- `api/` = `services/api/smartmatch_api/`
- `web/` = `apps/web/legacy-frontend/src/app/pages/exercise/`

## D1. Upload Ann's `.xlsx` directly

- **Question.** Is the data file CSV or XLSX, and does the instructor convert
  it before uploading? (OQ-CE-05)
- **Options.** (a) Keep the CSV reader; the instructor exports CSV on every
  upload. (b) Read `.xlsx` and keep CSV beside it. (c) Read `.xlsx` only.
- **Decision.** (c). openpyxl (`read_only`, `data_only`) with defusedxml. A
  zip-bomb guard reads the ZIP central directory before openpyxl opens the
  file. CSV and old `.xls` are refused with their own sentence. The body stays
  raw bytes (no multipart; ruling of 2026-09-21).
- **Approved.** Danny (owner), 2026-09-24. Closes OQ-CE-05.
- **Why.** Ann's file is a workbook. A convert step on every upload is friction
  for a non-technical instructor.
- **Affects.** The instructor's upload on the instructor page.
- **Code.** Shipped in PR #228.
  - `domain/exercise/workbook.py:93` `MAX_UPLOAD_BYTES` (2 MiB)
  - `:96` `MAX_ZIP_ENTRIES` (100)
  - `:102` `MAX_ENTRY_UNCOMPRESSED_BYTES` (1 MiB)
  - `:105` `MAX_TOTAL_UNCOMPRESSED_BYTES` (4 MiB)
  - `:175` `read_sheets`; `:191` refuses when openpyxl is not using defusedxml
  - `:286` the CSV refusal sentence; `:291` `_guard_zip`
  - `python/smartmatch_domain/pyproject.toml:9-10` pins `openpyxl` and
    `defusedxml`

## D2. Career goal → topic, and "Undecided" at half credit

- **Question.** Which event topic does each career-goal label fit? (OQ-CE-14)
- **Options.** For "Undecided": (a) no topic, a measured miss (the owner's
  draft of 2026-09-24); (b) half credit on broad exploratory events (Ann's
  amendment).
- **Decision.** Each "<field> role" → its field. "Start my own business" →
  Entrepreneurship / startups. "Graduate school" → no topic. "Undecided" → no
  topic, but **0.5** on "career goal fits this event" for an exploratory event.
  Exploratory = Career fair, Industry panel, Employer info session, Employer
  talk. Northline and Harbor are Employer talks, so both are exploratory. The
  simulated-results rule gives the same half.
- **Approved.** Danny drafted the table 2026-09-24. Ann confirmed it and added
  the half-credit rule, 2026-09-25. Closes OQ-CE-14.
- **Why.** In Ann's data each role label is the profile's first true interest.
  Ann wants undecided students to still reach broad events, but below students
  whose goal clearly fits.
- **Affects.** The ranked list, the reason lines, and the simulated results.
- **Code.** Table in PR #228; half credit and migration `0043` in PR #233.
  - `domain/exercise/vocabulary.py:127` `CAREER_GOAL_TOPICS` (`:142` Start my
    own business, `:144` Graduate school)
  - `:152` `UNDECIDED_CAREER_GOAL`; `:157` `EXERCISE_EVENT_TYPES`
  - `domain/student_factors/factors.py:81` `UNDECIDED_EXPLORATORY_GOAL_FIT =
    0.5`; `:157` `career_goal_fit`
  - `domain/exercise/simulation.py:536` the rule's half
  - `domain/exercise/ingest.py:367` reads `event_type` into `is_exploratory`
  - `db/migrations/versions/0043_exercise_event_exploratory.py`

## D3. The last tie-break step is Ann's `tiebreak_order`

- **Question.** When two profiles tie on the score, on information on file and
  on class year, what decides?
- **Options.** (a) A fixed shuffle seeded from the dataset checksum (ADR-0025
  D5 as first written). (b) Ann's `tiebreak_order` column ("Fixed random order
  1–300 … Never changes between runs.").
- **Decision.** (b). A dataset stored before revision `0042` has no
  `tiebreak_order` and keeps (a).
- **Approved.** Danny (owner), 2026-09-24.
- **Why.** Ranks then match Ann's spreadsheet exactly.
- **Affects.** Only exact ties at the bottom of the tie-break. Rank order
  otherwise unchanged.
- **Code.** Shipped in PR #228. `domain/exercise/matching.py:292`
  `_exercise_ranked`; `:428` `_fixed_order` (uses `tiebreak_order`, falls back
  to the checksum permutation at `:441`). Pinned by
  `tests/golden/exercise/test_exercise_ann_dataset_golden.py:233`.
- **ADR.** This changes ADR-0025 D5's last step, so ADR-0025 is amended (see
  the end of this file).

## D4. Ann's files are committed as test fixtures

- **Question.** Do Ann's workbooks live in this public repository?
- **Options.** (a) Keep them out; tests build their own rows. (b) Commit them
  as they arrived. (c) Commit them without the Read Me and Benchmark tabs.
- **Decision.** (c). Commit both files; strip the two tabs going forward. Git
  history keeps the earlier versions.
- **Approved.** Danny (owner), 2026-09-24 (commit) and 2026-09-25 (strip).
- **Why.** Tests run on the real layout and values. The repository is public,
  and Ann asked that the data never be described beyond D15's wording.
- **Affects.** Tests only. The instructor still uploads Ann's own file.
- **Code.** `tests/fixtures/exercise/SmartMatch_Student_Body_300.xlsx` and
  `tests/fixtures/exercise/SmartMatch_Student_Body_Sample_20.xlsx`, sheets
  `Profiles` and `Events` only. Stripped in commit `a2086ffd` (PR #231).

## D5. A results run needs a saved final setting

- **Question.** What does a results run use when the team has not chosen?
- **Options.** (a) Fall back to the course's starting weights. (b) Refuse until
  the team chooses one of its saved settings.
- **Decision.** (b). 422 `exercise_final_setting_required`: "Choose one of your
  saved settings as your final setting before running results."
- **Approved.** Danny (owner), 2026-09-24, from Ann's flow (Ann to Chau,
  Discord, 2026-09-24).
- **Why.** Ann's step 3 is "the team chooses one final setting".
- **Affects.** The results screen's run button.
- **Code.** Shipped in PR #227. `api/routers/exercise_results_run.py:137`
  `FINAL_SETTING_SENTENCE`; `:142` `final_setting_or_refusal`; `:163` the code.

## D6. A copied card carries the hidden true interests and career goal

- **Question.** When a refresh copies a card onto a profile, what career goal
  does it carry? (OQ-CE-13)
- **Options.** (a) None (PR #190). (b) The base row's stated goal (ruling of
  2026-09-21). (c) The hidden true goal.
- **Decision.** (c), together with the hidden true interests.
- **Approved.** Ann's data file Read Me, 2026-09-24: "a new card copies
  these". Closes OQ-CE-13.
- **Why.** Ann's own rule for her hidden columns.
- **Affects.** Round two: a refreshed profile can move on the list, because the
  card now shows what it truly wants.
- **Code.** Shipped in PR #228. `domain/exercise/asking.py:123`
  `COPIED_CARD_CAREER_GOAL = CopiedCardCareerGoal.HIDDEN_GOAL`.
- **ADR.** ADR-0025 D6 named one withheld column and one reader; both are now
  two. The amendment records it.

## D7. The results-rule numbers

- **Question.** What numbers turn Ann's words into the simulated-results rule?
  (OQ-CE-03)
- **Options.** (a) Leave the rule unset, so every run is refused. (b) Ship the
  team's translation for Chau to approve from a sample result.
- **Decision.** (b), approved as shipped:

  | Ann's word | Quantity | Value |
  |---|---|---|
  | (starting chance) | `base_signup_rate` | 0.04 |
  | a lot | `true_fit_lift` | 0.40 |
  | (a lot, split) | `true_interest_share_of_fit` | 0.5 — half interests, half goal |
  | some | `frequent_attender_lift` | 0.10 |
  | (some: how many past events) | `frequent_attender_events` | 1 |
  | a little | `same_major_lift` | 0.04 |
  | some randomness | `chance_spread` | 0.20 (±0.10) |
  | (show-up) | `attend_given_signup` | 0.75 |

- **Approved.** The team translated Ann's words (Ann delegated the numbers to
  Chau); **Chau approved**, 2026-09-25. Closes OQ-CE-03. Ann receives the
  sample result for information.
- **Why.** Keeps Ann's order a lot > some > a little. An equal-weights top-30
  list lands near Ann's example of about 8 sign-ups and 6 attendees
  (typical team: 9.5 / 7.1 at Northline, 7.5 / 5.6 at Harbor). If Ann reacts to
  the sample, the change is one line.
- **Affects.** Every results run and the "email everyone" panel.
- **Code.** Shipped in PR #233.
  - `domain/exercise/simulation.py:471` `EXERCISE_SIMULATION_COEFFICIENTS`
  - `:425-436` the constructor refuses any set where "a lot" is not above
    "some" and "a little"
  - `tests/unit/test_exercise_simulation.py:439` checks the shipped set is
    in the order a lot > some > a little
  - `tests/golden/exercise/test_exercise_results_rule_sample_golden.py` pins
    the sample result's tables
- **Follow-up (CODE-A, `feat/ce-results-integration`).** The comment at
  `simulation.py:465-470` still reads "PLACEHOLDER (OQ-CE-03 … Chau to
  confirm …)". CODE-A removes that marker and states the approval. No number
  changes.

## D8. Empty seats: show both groups

- **Question.** How does the results screen explain empty seats? (new row
  OQ-CE-16)
- **Options.** (A) Show both groups: the 8 already coming and the team's
  attendees, then what is left (46 in the example). (B) Show one number that
  leaves the 8 out (54 in the example).
- **Decision.** (A). Target copy: "8 were already coming. Your invitations
  added 6. 46 seats are still open."
- **Approved.** Team recommendation A; **Chau approved**, 2026-09-25.
- **Why.** The case has 60 seats and 8 existing sign-ups. Showing both makes
  clear what the team's list changed. The earlier "54 open" came from the
  team's own example text, not from Ann.
- **Affects.** The results screen's seat panel. The count itself does not
  change.
- **Code today.** The count already follows (A):
  - `domain/exercise/simulation.py:217` `EVENT_SEATS = 60`
  - `:221` `EXISTING_SIGNUPS = 8`
  - `:660` `seats_empty` = 60 − 8 − attended
  - `web/ResultPanels.tsx:73-76` shows three figures: seats in the room,
    already signed up, seats still empty
- **Intended end state (CODE-A, `feat/ce-results-integration`).** The panel
  adds the three sentences above, filled from the run's own numbers.

## D9. P004 test case: keep as built

- **Question.** Ann's Read Me says P004 should rank above a plain Accounting
  major for Northline with "said they are interested" turned up, and not with it
  turned off. Turned off, P004 still ranks above. Change her expectation, the
  goal table, or the tie-break? (OQ-CE-15)
- **Options.** (A) Keep as built. (B) Change the goal table or the tie-break so
  P004 falls below.
- **Decision.** (A). On the full 300-profile file, with the other three
  factors at 0.25, turning the interest factor off moves P004 from 4th to
  6th for Northline. The two plain Accounting majors the test uses (P231, P257)
  are 161st and 295th, so P004 stays above them. (On the 20-profile sample: 1st → 2nd.)
- **Approved.** Team recommendation A; **Chau approved**, 2026-09-25. Ann may
  revisit.
- **Why.** P004's career goal ("Data, analytics or IT role") still fits
  Northline. With that factor off too, "more information on file first" is
  Ann's own tie-break. Both teach the lesson that information matters.
- **Affects.** Nothing changes.
- **Code.** Pinned by PR #228:
  `tests/golden/exercise/test_exercise_ann_dataset_golden.py:161`
  (turned up), `:170` (factor stops counting), `:178` (still above on the goal),
  `:188` (information tie-break).

## D10. Seed the database instead of a live file fallback

- **Question.** How does an empty database get Ann's data?
- **Options.** (A) A seed command, plus a guarded dev-only seed on start. (B)
  The API reads the fixture file live whenever the database has no dataset.
- **Decision.** (A).
- **Approved.** Danny (owner), 2026-09-25 (option A).
- **Why.** The database is already the runtime source. A live fallback could
  serve fixture data in production and would make two sources of truth.
- **Affects.** Developers and operators only. `SMARTMATCH_EXERCISE_SEED_ON_START`
  is never set on the VM (`docs/operations/exercise-hosting.md` §2).
- **Code.** Shipped in PR #234.
  - `Makefile:185-186` `exercise-seed`
  - `api/exercise_seed.py:136` `seed_exercise_dataset`
  - `:186` `auto_seed_refusal`: six conditions, all of which must hold
  - `:244` `seed_on_start`; called from `api/main.py:260`

## D11. The unlock panel lists the teams' file

- **Question.** Which data file's events does the instructor's unlock panel
  list?
- **Options.** (a) The newest upload. (b) The file the teams are on.
- **Decision.** (b), resolved exactly as the unlock itself is.
- **Approved.** Implementer ruling in PR #232; accepted.
- **Why.** The button must unlock what the teams see.
- **Affects.** The instructor page's unlock panel.
- **Code.** `api/routers/exercise_instructor.py:370`
  `list_instructor_events`; `:405` `unlock_results`; `:609` `_teams_dataset`.

## D12. "Asking for more" rounds a half up

- **Question.** 55 percent of 30 is 16.5. Up or down? (part of OQ-CE-04)
- **Options.** Round half up; round half down; round half to even.
- **Decision.** Round half up, in `Decimal` arithmetic.
- **Approved.** Danny, per the owner-doc recommendation, 2026-09-25. Ann gave
  no view.
- **Why.** Predictable in a classroom; no floating-point error.
- **Affects.** How many invited profiles get a card in the refresh.
- **Code.** Shipped in PR #230. `domain/exercise/asking.py:191`
  `_half_up_count` (`ROUND_HALF_UP` at `:203`); `:206` `select_share`.

## D13. The license line is a constant on the opening screen

- **Question.** Where does the license line live? (OQ-CE-09)
- **Options.** (a) Per upload, in `exercise_dataset.license_line`. (b) A
  constant on the opening screen.
- **Decision.** (b), with Ann's wording (see Part 1).
- **Approved.** Ann's wording, 2026-09-25; the constant was chosen in PR #230.
- **Why.** The opening screen renders before any dataset exists.
- **Affects.** The opening screen.
- **Code.** `web/ExerciseEntry.tsx:50-51` `EXERCISE_LICENSE_LINE`.
- **Left over.** `exercise_dataset.license_line` is never filled
  (`python/smartmatch_persistence/smartmatch_persistence/exercise/schema.py:133`;
  surfaced as always-null in `api/routers/exercise_instructor_models.py:137`).
  Whether to retire it or define it as a per-file addendum is a row in
  [`docs/plans/backlog.md`](../plans/backlog.md).

## D14. The card asks two questions

- **Question.** What are the "five quick questions" on the profile card?
  (OQ-CE-11)
- **Options.** (a) Five questions, including major, year and past events. (b)
  Interests and career goal only; the student confirms the major on file.
- **Decision.** (b). Year and past events are not asked. The hidden true
  interests are never asked.
- **Approved.** Ann, 2026-09-25. Closes OQ-CE-11.
- **Why.** Major and year are on file; the app records past events.
- **Affects.** The profile-card mock-up.
- **Code.** Shipped in PR #230. `web/ProfileCardMockup.tsx:10-17` (Ann's
  words); `:80` `MajorConfirm`; `:133` `ProfileCardMockup`.

## D15. How the data is described

- **Question.** How do documents and screens describe where Ann's profiles come
  from?
- **Decision.** "Fictional profiles shaped by overall survey percentages." If a
  count is ever needed, the survey count is 1,370. Never describe the profiles
  as, or as drawn from, actual people or anyone's individual answers.
- **Approved.** Ann, 2026-09-25, as an explicit instruction.
- **Affects.** Every document and screen that describes the data.
- **Where.** The license line (D13) says "All student profiles are
  fictional." This PR brings `docs/` and `README.md` into line; its
  description lists every line changed.

## D16. The order of a run's refusals

- **Question.** Where does the D5 check sit among a run's other refusals?
- **Options.** (a) First, as a body check. (b) After "locked" and "already
  run", before the rule's coefficient check.
- **Decision.** (b). Order: unknown event (404) → not a round (409) → locked
  (409) → already run (409) → no final setting (422) → no coefficients (409)
  → setting not saved (404).
- **Approved.** Implementer ruling in PR #227; accepted.
- **Why.** Asking a team that already ran to choose a setting invites a second
  try. And the new check must stay reachable: the coefficient check used to
  refuse every run.
- **Affects.** Which one sentence a team sees.
- **Code.** `api/routers/exercise_results.py:236-241` (call order) and
  `:217-227` (the order in words); `api/routers/exercise_results_run.py:347`
  `runnable_or_refusal`, `:142`, `:116` `coefficients_or_refusal`, `:169`
  `weights_or_refusal`.

---

## Why this file, and the ADR amendment

**Why a decision record in `docs/decisions/`.** Most of D1–D16 are product
rulings, numbers and wording, not architecture. ADR-0025's own amendment
discipline says so: "Changing a coefficient, a percentage, or a default weight
is a register row in `class-exercise-open-questions.md`, not an amendment."
This folder is where the repository records rulings of that kind with who
approved them (for example `manual-events-and-feedback-qr-2026-09-07.md`,
`pilot-login-decision-2026-09-04.md`). The register rows link here.

**Why ADR-0025 is also amended.** The same discipline says: "A later change to
… the tie-break order … amends this ADR." D3 replaces the last tie-break step
that ADR-0025 D5 names. D6 widens ADR-0025 D6 from one withheld column and one
reader to two of each. Both refine the ADR rather than replace it, so they are
an amendment section, not a new superseding ADR. The amendment is dated 25
September 2026 and points back here.
