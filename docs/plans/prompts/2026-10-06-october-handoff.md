# Handoff — October stakeholder work on Smart Match (written 2026-10-06)

Paste everything below the line into a fresh agent session opened in the
repository. It is written for an agent that has none of the prior context.

---

You are picking up the October stakeholder work on
`IA-Smart-Match/IA-Smart-Match-Revamped` for the owner (Danny; GitHub
`BrooklynD23`, `gh` is authenticated as that account). A previous agent session
did a large amount of work on 2026-10-06. Your job has two parts, in this order:

1. **Check that work against what Dr. Ann Wang has actually asked for since
   October began.** Treat every claim in this document as a claim to verify, not
   a fact. Report what holds, what does not, and what was missed.
2. **Then carry the open pull requests and the GitHub issues assigned to
   `BrooklynD23` to completion**, within the rules below.

Report findings from part 1 to the owner before starting anything in part 2 that
changes behavior.

## Dates that drive everything

| Date | What |
|---|---|
| Thu 2026-10-08 | CBACH advisory board presentation. Two presenters (Chau and one other), 30-minute slot between 1:00 and 4:30 pm: about 15 minutes of FRONT-END demo, then Q&A. The board is non-technical |
| Wed 2026-10-14 | GitHub milestone "#1 — Oct-14 stakeholder board" |
| Fri 2026-10-16 | Dr. Wang's run-through of the class exercise, both sessions, using her test checklist. The deployed site must be live, clean and verified |
| Fri 2026-10-30 | Problems from the run-through fixed; the teaching module is "finished". The CPP platform build starts only after this, and only with the college's go-ahead |

## What Dr. Wang has asked for since October 1 — read the sources yourself

1. **2026-10-02 — progress check and user test checklist.** Five areas to
   revise before Oct 16: (1) every press shows what it did, plus a status line
   on each team page; (2) a full instructor view of each team, and results can
   be closed again; (3) Session 2 gaps — "email everyone" comparison, one results
   run per team, a visible refresh; (4) matching-rule corrections — a matching
   interest counts in full, remove the "undecided" career-goal credit, one reason
   line, year order, browser tab name; (5) event descriptions from a new
   `event_description` workbook column. Also: a new workbook to upload, and a
   clean-up of the site (clear Teams 1–4, both events closed).
   Sources: `docs/10-2-2026/extracted/*.txt` and
   `docs/10-2-2026/issue-briefs/INDEX.md` (on branch `oct14/sprint-plans`, PR
   #347; also untracked in the owner's main checkout).
2. **2026-10-06 — the results rule** (who signs up, who attends): notice 75% for
   the team's 30 and 15% for "email everyone"; sign-up starts at 5% and adds +35
   true interest, +15 true career goal, +5 for 1–2 past events or +10 for 3 or
   more, +5 same major; a flat 70% attend; a small element of luck fixed per
   team; hidden columns decide outcomes for all 300. Justin adds a plain-words
   description to the one-page write-up. Verbatim text and analysis: PR #348
   (`docs/decisions/class-exercise-results-rule-2026-10-06.md`,
   `docs/plans/2026-10-06-results-rule-impact-analysis.md`).
3. **2026-10-06 — default weights are 3 / 3 / 2 / 2** (same major, stated
   interest, career goal, past events) for both the class module and the
   platform. The owner then ruled the display scale: whole numbers 0–10. PR #349
   (`docs/decisions/class-exercise-default-weights-2026-10-06.md`).
4. **2026-10-06 — a clickable CPP front-end prototype** for the board, with
   "Feel free to use it and modify it from your end." Her files:
   `docs/design/cpp-prototype/source/` on branch `demo/cbach-advisory-2026-10-08`.
   Her README's rules: present it as the design for the next phase; say out loud
   that the interview and the assistant are scripted, not live AI; never real
   student data; every screen keeps its working / planned label.

Earlier decisions still in force: `docs/decisions/class-exercise-decisions-2026-09-25.md`
(D1–D16, with amendments dated 2026-10-06 on main and on open branches) and
`docs/decisions/stakeholder-correspondence-2026-09.md`.

## What was done on 2026-10-06 (verify each line)

`main` was at `783a1244` when this was written.

| PR | Issues | State when written | What it claims |
|---|---|---|---|
| #339 | #325, #318 | **merged** | Accepts her Oct-2 workbook (2,000-char cap on `event_description` only); shows event descriptions; migration `0044_exercise_event_description` |
| #345 | #326, #328, #319, #271 | **merged** | Results can be closed again; teams see lock and one-run state; run snapshot of invited names and weights; instructor team detail; migrations `0045_exercise_unlock_closed_at`, `0046_exercise_run_snapshot` |
| #341 | — | **merged** | `source-map-js` bump for the web audit gate |
| #340 | #329, #330 | open, green, reviewed | Refresh summary, time, before/after counts, marks; refresh-every-team report |
| #338 | #335 | open, green, reviewed | CSV download with plain "how much we know" labels; six columns pinned; negative tests |
| #344 | #331 | open, green, reviewed | Clearing one team keeps its chance seed (checklist §8); D7 amended |
| #346 | #321 | open, green; review fixes applied but **not re-reviewed** | Team status line, a sentence after every press, confirm on refresh-every-team. Contains #340's commits — merge after #340 |
| #343 | — | open, green | CI check that migrations only add (expand/contract), and a deploy rollback that tolerates a schema that is ahead. **Never exercised on a real VM** |
| #347 | all | open, docs | Sprint plans (14), `oct14-deferred.md` open questions, Oct-16 clean-up runbook, the issue briefs |
| #348 | — | open, docs | Results-rule record, impact analysis, OQ-CE-19 to 31 |
| #349 | — | open, docs | Default weights 3/3/2/2 on 0–10; OQ-CE-32 to 34 |
| #342 | — | open, targets Chau's branch | Fixes for audit findings on #337 (removes its migration `0044_drop_event_exploratory`) |
| #337 | #322 | open, Chau's, **conflicts with main** | Matching-rule corrections from Oct-2 area 4 |
| branch `demo/cbach-advisory-2026-10-08` | — | pushed, **no PR yet** | Her prototype, `docs/design/cpp-prototype/DESIGN.md`, three mockups (A Blueprint, B Workbench, C Walkthrough), this handoff. An independent UI audit was running; look for `docs/design/cpp-prototype/audit/AUDIT.md` (it may be uncommitted in the worktree `.claude/worktrees/demo-cbach`) |

Deferred, with an issue comment and a plan each: #295 (baseline seed), #273
(`license_line`), #323 (Oct-16 clean-up; runbook written, nothing run).

## Part 1 — what to check

Work read-only until you have reported. Use independent reviewers where a second
read matters; give them the code, not this document's conclusions.

1. **Coverage against her requests.** Build a table: every line of the Oct-2
   progress check and every checklist box, plus the three Oct-6 items → the PR or
   issue that covers it → status (on main / open PR / planned / not covered).
   Flag anything not covered. Known candidates for "not covered by BrooklynD23's
   issues": Oct-2 area 4 (Chau, #337), the "email everyone" comparison and
   Harbor three-way panel, year order, browser tab name, reason lines, the
   license line on the opening screen.
2. **Merged code does what it says.** For #339 and #345 on main: read the diffs,
   confirm CI on main is green, and confirm the invariants below still hold.
3. **Open PRs are still correct against current main** — #340, #338, #344, #346,
   #343: mergeable, CI green, no stale claims in the PR body. #346's review
   fixes (key-repeat guard on inline confirms, "Check again" honesty, the
   "Opened" note) have had no second review; give it one.
4. **Contradictions between her rulings and what is built or documented:**
   - Defaults are 0.25 each in code (`python/smartmatch_domain/smartmatch_domain/exercise/registry.py`) against the 3/3/2/2 ruling.
   - The results rule in `simulation.py` against her Oct-6 rule (no notice step; "email everyone" shares the team's rule and seed).
   - Under her numbers the analysis found "email everyone" draws about as many sign-ups as a typical list of 30 (OQ-CE-31). Re-derive this independently before anyone relies on it; it decides whether her rule shows the lesson.
   - Her Oct-2 line "P004 ranks 5th with the starting settings" will move under 3/3/2/2.
5. **Unverified claims carried forward.** No screen was checked in a real
   browser by a person; the rollback fix has not run on a VM; the `.accdb`
   fixture still mirrors the September workbook (needs Microsoft Access on
   Windows); three worktrees under `/home/danny/worktrees/` (`ia-319-…`,
   `ia-271-…`, `ia-321-…`) hold branches for issues already built here — find
   out whether they are abandoned.

Report: the coverage table; what failed verification; decisions the owner or Dr.
Wang must make, each with a recommended default.

## Part 2 — continue to completion

In rough priority order. Re-plan after part 1.

1. **Board demo (Oct 8).** Apply the UI audit's BLOCKER and HIGH findings to the
   three mockups, correct the contradictions it lists in
   `docs/design/cpp-prototype/DESIGN.md`, open the PR for
   `demo/cbach-advisory-2026-10-08`, and check the chosen mockup opens by
   double-click on the presenting laptop's browser. Recommended lead: A.
2. **Land the reviewed PRs** (the owner merges; you keep them mergeable and
   green): #344, #340, #338, then #346, then #343; docs PRs #347, #348, #349 any
   time. Expect small keep-both conflicts in `DESIGN.md` §11.1, the decisions
   file, `docs/decisions/INDEX.md` and `docs/operations/exercise-hosting.md`.
3. **Close out assigned issues as their PRs merge**, and move each card on the
   project board "SmartMatch - Deliverable 10/14/2026" (In review → Done). Open
   and assigned when written: #335, #331, #330, #329, #321 (built, PRs open);
   #323, #295, #273 (waiting on decisions).
4. **Default weights 3/3/2/2 on 0–10** — implement once the owner says whether
   the class module switches before or after Oct 16 (OQ-CE-34). Do it after
   Chau's #337 merges so golden files are regenerated once.
5. **Dr. Wang's results rule** — do not implement until she answers at least
   OQ-CE-24, 26 and 31 (PR #348). The impact analysis has an 11-step change list
   (about 27 hours), built on top of #337.
6. **Oct-16 clean-up (#323)** — the owner picks path A, B or C in the runbook and
   gives a written go-ahead. You run nothing against the VM without it. Before it:
   `GRANT UPDATE ON exercise_result_unlock` to the exercise role, #344 deployed,
   and a check of `/opt/smartmatch/exercise-setup.sh` on the VM (it is outside
   the repository and may re-apply old grants).
7. **Chau's #337** — it needs main merged in and #342 merged into it. That is
   Chau's branch: do not push to it; tell the owner what Chau needs to do.

## Decisions still open with the owner

1. Two-press confirm on the team's own refresh in #346 — keep or revert.
2. Switch the class module to 3/3/2/2 before or after Oct 16.
3. CSV byte-order mark (none today).
4. `dataset_id` on three instructor response models on main — intended, or fix.
5. Is the repository private to the team (the Oct-2 workbook fixture and the
   mockup data carry hidden-truth columns of made-up profiles).
6. Reboot gap in the #343 rollback fix — follow up or accept.
7. Which mockup leads on Thursday.
8. #323 clean-up path; #295 and #273 (see `oct14-deferred.md`).

## Rules that are not negotiable

- Branch and pull request only. Never merge, never push to `main`, never deploy,
  never run anything against a live environment or live data. Never push to
  another person's branch.
- No change to `simulation.py`, coefficients or mappings without a dated
  decision that supersedes the current one.
- Exercise response models never expose `hidden_true_*` fields, seeds, tokens,
  `workspace_id`, `dataset_id`, or names shaped like
  score / percent / confidence / probability / likelihood / share. The model-walk
  contract tests stay green.
- The word "refresh" never appears in a server-sent sentence; compose it
  client-side.
- Every new user-facing sentence goes in `docs/design/class-exercise/DESIGN.md`
  §11.1 in the same change.
- No modals, no `window.confirm`; inline confirms. `aria-disabled`, not `disabled`.
- Determinism is the SHA-256 stable digest only. The workspace is
  cookie-addressed; no ids in URL paths.
- Routers reach persistence only through `exercise_dependencies`. New modules join
  `_TRACK_MODULES` and both import-linter lists in `pyproject.toml`. Source files
  stay under 800 lines (`exercise_matching_models.py` is at exactly 800).
- Migrations only add (nullable columns, new tables). Revision ids are at most 32
  characters. Head when written: `0046_exercise_run_snapshot`.
- `exerciseClient.ts` is hand-mirrored from the server models; exercise routes
  are not in `contracts/openapi/smartmatch.json`.
- Dated amendments go directly under the decision they amend. Never rewrite a
  stakeholder's source file (`docs/10-2-2026/`, `docs/design/cpp-prototype/source/`).
- No commit or PR attribution lines; conventional commit prefixes. Write reports,
  PR bodies and comments result-first, numbered, short (the owner's
  `~/.claude/rules/common/subagent-output.md`); pass that rule to every subagent.
- Do not claim something works without the command output that shows it.

## Environment facts that cost time before

- The owner's notes for this repository:
  `/home/danny/.claude/projects/-mnt-c-Users-DangT-Documents-GitHub-IA-Smart-Match-Revamped/memory/MEMORY.md`. Read it first.
- Source tree is `python/`, `services/`, `apps/web/legacy-frontend`,
  `db/migrations/versions`, `tests/`. There is no `src/`.
- Run parallel agents in separate git worktrees; they share no checkout. A
  worktree has no virtualenv — use the parent's:
  `make <target> VENV=/mnt/c/Users/DangT/Documents/GitHub/IA-Smart-Match-Revamped/.venv`.
- Never run the whole pytest suite locally (it wedges on `/mnt/c`). Run the cheap
  gates (`make format-check lint typecheck imports scan`) and targeted test files,
  one pytest process at a time; CI proves the full suite. `ruff format` also
  formats Python code fences inside Markdown under `docs/`.
- Integration tests on the shared local PostgreSQL drop each other's scratch
  databases (`database "smartmatch_scratch_…" does not exist`). Use a privately
  named database through `SMARTMATCH_DATABASE_URL`.
- Vitest: run from a copy on ext4 with `--pool=threads` on specific files; it
  collects only `*.test.tsx`; under local Node 26, `ExerciseEntry*.test.tsx` and
  `ExerciseInstructor.passcode.test.tsx` fail on an undefined `localStorage`
  (CI passes them).
- `gh pr edit` fails silently here; change a PR body with
  `gh api -X PATCH repos/IA-Smart-Match/IA-Smart-Match-Revamped/pulls/N -F body=@file`.
- A re-run of a failed CI job reuses the old merge commit; to pick up a newer
  `main`, merge `main` into the branch and push.
- Headless browser: playwright-cli with `--browser=chromium`; `file://` is
  blocked there, so serve the folder on a local port.

## What "done" looks like

1. A verification report the owner has read, with the coverage table.
2. Every reviewed PR merged by the owner or mergeable and green with nothing
   stale in its body; every built issue closed and in Done on the board.
3. The demo branch has a PR, the audit's serious findings are fixed, and the lead
   mockup has been opened on the presenting laptop.
4. Each gated item (#295, #273, #323, the results rule, the weights switch) either
   has its decision recorded and is implemented, or has a named person and date
   it is waiting on.
5. A short note of what could not ship by Oct 16 and why.
