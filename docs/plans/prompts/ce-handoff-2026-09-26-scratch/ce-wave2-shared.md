# CE wave 2 — shared brief (read fully before starting)

Output style: follow ~/.claude/rules/common/subagent-output.md (i-have-adhd)

## State
- Repo: parent checkout /mnt/c/Users/DangT/Documents/GitHub/IA-Smart-Match-Revamped. Public GitHub repo IA-Smart-Match/IA-Smart-Match-Revamped.
- origin/main @9339d5a4 contains everything below (PRs #227–#234 merged).
- Migration head: 0043_exercise_event_exploratory.
- The results screen works now: `EXERCISE_SIMULATION_COEFFICIENTS` is set in
  `python/smartmatch_domain/smartmatch_domain/exercise/simulation.py:471`, still marked "Chau to confirm".

## Decisions the owner approved (source of truth — do not re-ask)
Chau reviewed the team's recommendations and approved proceeding. Ann's answers come from her email reply of 2026-09-25.

| # | Decision | Who / when | Reasoning |
|---|---|---|---|
| D1 | Upload Ann's .xlsx directly (openpyxl + defusedxml, zip-bomb guard); CSV path removed | Owner (Danny) 2026-09-24; closes OQ-CE-05 | Ann's file is xlsx; a converter step every upload is friction for a non-technical instructor |
| D2 | Career goal → topic table; "Start my own business" → Entrepreneurship; Graduate school → none; **Undecided → half credit on exploratory events** (Career fair, Industry panel, Employer info session, Employer talk; Northline + Harbor exploratory), same in the results rule | Owner draft 2026-09-24, Ann confirmed + amended 2026-09-25; OQ-CE-14 | Data shows each role label = the profile's first true interest; Ann wants undecided students to still reach broad events, below students whose goal clearly fits |
| D3 | The last tie-break step uses Ann's `tiebreak_order` column | Owner 2026-09-24 | Ranks match Ann's spreadsheet exactly |
| D4 | Ann's files are committed as fixtures; Read Me and Benchmark tabs were stripped going forward (history kept) | Owner 2026-09-24 / 2026-09-25 | Tests run on the real data. The repo is public, and Ann asked that no real-survey or respondent wording appear anywhere |
| D5 | A results run requires a saved final setting (422 `exercise_final_setting_required`) | Owner 2026-09-24, from Ann's flow (Discord to Chau, 2026-09-24) | Ann's step 3 is "the team chooses one final setting" |
| D6 | A refresh-copied card carries the hidden true interests AND the hidden true goal | Ann's Read Me 2026-09-24; closes OQ-CE-13 | Ann: "a new card copies these" |
| D7 | Results-rule numbers: start 0.04; true fit +0.40 ("a lot"), split half interests / half goal; past attendance +0.10 ("some", ≥1 event); same major +0.04 ("a little"); chance ±0.10 ("some randomness", spread 0.20); attend given sign-up 0.75 | Team translation of Ann's words (Ann delegated the numbers to Chau); **Chau approved**; closes OQ-CE-03 | Keeps Ann's order a lot > some > a little, which the code enforces. A top-30 equal-weights list lands near Ann's "about 8 sign up, 6 attend". Numbers are a one-line change if Ann reacts to the sample |
| D8 | Empty seats: **show both groups**, e.g. "8 were already coming. Your invitations added 6. 46 seats are still open." | Team recommendation A, **Chau approved** (new row OQ-CE-16) | The class case has 60 seats and 8 existing sign-ups. Showing both makes clear what the team's list actually changed. The earlier "54 open" came from our own example text, not from Ann |
| D9 | P004 test case: keep as built. With "said they are interested" off, P004 drops (4th → 6th) but stays above a plain Accounting major | Team recommendation A, **Chau approved**; OQ-CE-15 decided, Ann may revisit | The career goal still fits Northline, and "more information on file first" is Ann's own tie-break. That matches the lesson that information matters |
| D10 | Seed instead of a live file fallback: `make exercise-seed`, plus a guarded dev-only seed-on-start | Owner 2026-09-25 (option A) | The DB is already the runtime source. A live fallback could serve fixture data in production and creates 2 sources of truth |
| D11 | The instructor unlock panel lists the file the **teams** use, not the newest upload | Implementer ruling in #232, accepted | The button must unlock what teams see |
| D12 | "Asking for more" rounds x.5 up (Decimal) | Danny per owner-doc recommendation; Ann gave no view | Predictable for a classroom; no float error |
| D13 | License line is a constant on the opening screen: "For California State Polytechnic University, Pomona — College of Business Administration instructional use only. All student profiles are fictional." | Ann 2026-09-25 wording; constant chosen in #230 | The screen renders before any dataset exists. `exercise_dataset.license_line` is now unused → backlog |
| D14 | Card asks only interests + career goal; the student confirms the major on file | Ann 2026-09-25; OQ-CE-11 | Major and year are on file; the app records past events |
| D15 | Data wording: "fictional profiles shaped by overall survey percentages"; survey count 1,370 if a count is ever needed; never mention real students, respondents or individual responses | Ann 2026-09-25 | Her explicit instruction |
| D16 | Final-setting refusal order: after locked / already-run, before coefficients | #227 implementer, accepted | Don't invite a second run. Keep the new check reachable |

## Standing rules (each came from a failure)
1. Branch from origin/main. Commit and push at every milestone. Never rebase or force-push; merge main in if needed.
2. TDD. Run targeted test files only, one pytest at a time; full runs wedge on /mnt/c. CI proves the suite.
   - Use the parent venv: `/mnt/c/Users/DangT/Documents/GitHub/IA-Smart-Match-Revamped/.venv`.
3. Vitest: symlinking node_modules from another /mnt/c worktree times out.
   - Use the Linux-fs copy at `/tmp/claude-1000/-mnt-c-Users-DangT-Documents-GitHub-IA-Smart-Match-Revamped/65424d04-37cd-4ac7-8159-f9980f92eff9/scratchpad/fe/node_modules` (symlink it, then remove the symlink after).
   - Run `vitest run --pool=threads <file>`.
4. `ruff format` also checks python blocks in .md files.
5. A new migration must update the head pins AND `_REVISIONS_BETWEEN_HEAD_AND_THIS_CARD` in `tests/integration/test_cba_contact_schema.py`. Declare new CHECK constraints in `tests/integration/test_check_constraints.py`.
6. The local dev DB has 3 pilot-tenant `cba_invitation_batch` rows that make integration conftest setup fail. Use a throwaway DB, then drop it.
7. Hidden columns (`hidden_true_*`) must never reach a response, log, repr or CSV. No `OQ-CE-` register IDs in user-facing strings; guard tests enforce this.
8. Write PR bodies to a UNIQUELY named scratch file (include your track name). A shared `pr_body.md` got cross-posted once. Edit with `gh api -X PATCH repos/IA-Smart-Match/IA-Smart-Match-Revamped/pulls/N -F body=@<file>`. `gh pr edit` fails silently here.
9. `gh pr checks N` takes no `--json`.
10. Any subagent you spawn: `model: "opus"`, worktree isolation, and the output-style line above in its prompt.
11. Do not merge. Do not deploy to the VM.
12. Keep files ≤ 800 lines. `tests/unit/test_exercise_results_router.py` is already 1,995 lines; put new tests in NEW files.

## File ownership (parallel tracks — do not touch another track's files)
- **DOCS** (`docs/ce-wave2-decisions`): everything under `docs/` (register, spec, ADRs, the decision record, exercise-hosting.md) plus `README.md`.
- **CODE-A** (`feat/ce-results-integration`): `python/**/exercise/*`, `services/api/**/exercise_*`, `ResultPanels.tsx`, `ExerciseResults.tsx`, new test files.
- **CODE-B** (`fix/ce-ui-polish`): every other `apps/web/legacy-frontend/src/app/pages/exercise/*` file and `src/lib/exerciseClient.ts` (coordinate: if you need a new client field, add only that).
- **Monitors M1 and M2**: read-only on the repo. Scratch output only. They report bugs; they do not fix them.
