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

| Plan | Issue | Lane PR | Status 2026-10-06 |
|---|---|---|---|
| [001](001-upload-refusal-cell-cap.md) | #325 upload refusal | #339 | PR open, reviewed |
| [002](002-event-descriptions.md) | #318 event descriptions | #339 | PR open, reviewed |
| [003](003-lock-results-again.md) | #326 close results again | #345 | PR open, reviewed |
| [004](004-results-lock-visibility.md) | #328 team-side lock visibility | #345 | PR open, reviewed |
| [005](005-instructor-team-detail.md) | #319 instructor team detail | #345 | PR open, reviewed |
| [006](006-run-snapshot-invited-names.md) | #271 run snapshot | #345 | PR open, reviewed |
| [007](007-refresh-visibility.md) | #329 refresh visibility | #340 | PR open, reviewed |
| [008](008-refresh-all-report.md) | #330 refresh-all report | #340 | PR open, reviewed |
| [009](009-download-plain-labels.md) | #335 download labels | #338 | PR open, reviewed |
| [010](010-status-band-and-feedback.md) | #321 status band and feedback | #346 | PR open, review fixes in progress |
| [011](011-seed-preserved-on-reset.md) | #331 seed kept on clear | #344 | PR open, reviewed |
| [012](012-email-everyone-baseline-seed.md) | #295 baseline seed | — | Deferred to Ann |
| [013](013-license-line.md) | #273 license line | — | Deferred to owner |
| [014](014-oct16-ops-runbook.md) | #323 Oct-16 clean-up | — | Runbook written; nothing run |

## Merge order

1. #339 (migration `0044_exercise_event_description`).
2. #345 (stacked on #339; `0045_exercise_unlock_closed_at`, `0046_exercise_run_snapshot`).
3. #340, #338, #344 — independent of each other and of 1–2.
4. #346 (#321) last — stacked on #345 and #340.

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
