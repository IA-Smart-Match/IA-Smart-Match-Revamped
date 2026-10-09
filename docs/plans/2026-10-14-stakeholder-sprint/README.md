# Oct-14 stakeholder sprint — plans

**Date:** 2026-10-06 · **Scope:** class exercise only · **Source:** Ann Wang's
progress check and user test checklist of 2026-10-02
(`docs/10-2-2026/extracted/`), mapped to issues in
`docs/10-2-2026/issue-briefs/INDEX.md`.

Dates: milestone board 2026-10-14 · Ann's run-through 2026-10-16 · fix-up window
to 2026-10-30.

One plan per issue. Each has: current behavior, ordered change list with
file:line seams, test plan, acceptance (the checklist lines it satisfies),
decision status, and an "As built" section where the implementation diverged.
A plan is a point-in-time record; the PR and the code are the authority.

## Plans

| Plan | Issue | Lane PR | Status 2026-10-07 |
|---|---|---|---|
| [001](001-upload-refusal-cell-cap.md) | #325 upload refusal | #339 | **Merged** |
| [002](002-event-descriptions.md) | #318 event descriptions | #339 | **Merged** |
| [003](003-lock-results-again.md) | #326 close results again | #345 | **Merged** |
| [004](004-results-lock-visibility.md) | #328 team-side lock visibility | #345 | **Merged** |
| [005](005-instructor-team-detail.md) | #319 instructor team detail | #345 | **Merged** |
| [006](006-run-snapshot-invited-names.md) | #271 run snapshot | #345 | **Merged** |
| [007](007-refresh-visibility.md) | #329 refresh visibility | #340 | PR open, mergeable |
| [008](008-refresh-all-report.md) | #330 refresh-all report | #340 | PR open, mergeable |
| [009](009-download-plain-labels.md) | #335 download labels | #338 | **Merged** |
| [010](010-status-band-and-feedback.md) | #321 status band and feedback | #346 | PR open, mergeable; merge after #340 |
| [011](011-seed-preserved-on-reset.md) | #331 seed kept on clear | #344 | PR open, mergeable; merge first |
| [012](012-email-everyone-baseline-seed.md) | #295 baseline seed | — | Deferred to Ann |
| [013](013-license-line.md) | #273 license line | — | Deferred to owner |
| [014](014-oct16-ops-runbook.md) | #323 Oct-16 clean-up | — | Runbook written; nothing run |

## Merge order

Done: #339 (`0044`), #345 (`0045`, `0046`), #338. Migration head on `main` is `0046_exercise_result_run_snapshot`. These plans and the runbook are PR #347.

Left, in order:

1. #344 (#331) — the Oct-16 runbook needs it on every path.
2. #340 (#329, #330).
3. #346 (#321) — stacked on #340; update from `main` once #340 is in.
4. #347 (this folder).

Expect small text conflicts between lanes in `docs/design/class-exercise/DESIGN.md`
§11.1, `docs/decisions/class-exercise-decisions-2026-09-25.md`,
`docs/operations/exercise-hosting.md` and `exerciseClient.ts`; each lane's rows
are adjacent additions.

Migration head after all lanes: `0046_exercise_run_snapshot`, linear from
`0043_exercise_event_exploratory`. Revision ids are capped at 32 characters by
`alembic_version.version_num`, so 0045 and 0046 are shorter than their file names.

## Related PRs outside the lanes

- #337 (Chau) — matching-rule changes; #342 removes its migration
  `0044_drop_event_exploratory` so it no longer collides with #339's 0044.
- #343 — CI check that a release only adds to the schema (expand/contract), and
  a deploy rollback that tolerates a schema that is ahead.

## Deploy steps the PRs cannot do

1. `GRANT UPDATE ON exercise_result_unlock` to the exercise role before #345
   ships (`docs/operations/exercise-hosting.md`).
2. Deploy #344 before the Oct-16 clean-up, or cleared teams get a new chance
   draw and checklist §8 fails.
3. Rebuild the `.accdb` fixture from the Oct-2 workbook (needs Microsoft Access
   on Windows; `tests/fixtures/exercise/README.md`).
4. Run the clean-up from `docs/operations/exercise-oct16-cleanup-runbook.md`
   after the owner picks a path.

## Decisions

Deferred questions and every default a lane took:
[`../open-questions/oct14-deferred.md`](../open-questions/oct14-deferred.md).
Dated amendments (D1, D4, D7, D16) are in
`docs/decisions/class-exercise-decisions-2026-09-25.md` on the lane branches.

## Audit, 2026-10-07

Four read-only Codex audits compared every plan here with the code (static; no tests run). What they found and what was done:

- **Plans 001–006 and 009 are historical.** Their `ec471ba2` baseline and many `file:line` seams predate the merges; read the merged code, not the line numbers. Some tests landed under other names: plan 004's `test_exercise_teacher_flow.py` pin is in `exercise_results_router/test_exercise_results_rules.py`; plan 007's wording scan is `tests/unit/exercise_results_router/test_exercise_results_asking_wording.py` and its Vitest file is `refreshWording.test.tsx`; plan 010's `InstructorUnlock.refreshAllConfirm.test.tsx` is covered by `InstructorFeedback.test.tsx` and `InstructorUnlock.guard.test.tsx`. Plan 008's "as built" note calls `first_round_event_name` a divergence; it is in the change list.
- **Fixed in this change:** the runbook's backup now fails closed and is checked with `gzip -t`; the four clears are sent one at a time, not in a loop; the go-ahead names a release SHA; stale "open" lines for #326/#339; "since #331" wording that read as if #344 had merged; OQ-OCT14-05's account of why a new file gives new results.
- **Fixed on #346:** the status line's region name added to `DESIGN.md` §11.1.
- **`dataset_id` on instructor response models** is a standing, tested exemption (`test_exercise_results_contract.py:260-271`), not a sprint regression.
- **Left open, owner or stakeholder to rule:**
  - #330: each team's line in the every-team report shows one before → after count (completed cards), not all three. Ann asked for "the same kind of summary for each team".
  - #321: the instructor's unlock-list "Check again" says nothing when nothing changed.
  - #269 (not in this sprint): the team's invited names follow profile number, not rank. The snapshot now holds rank, so it is a few lines in `ResultPanels.tsx`.
  - Runs stored before `0046` show the saved setting's weights as they stood at migration time. The Oct-16 clean-up clears those runs.
  - The exercise-only restore in the runbook has not been rehearsed on a developer database.
