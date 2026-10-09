# Oct-2 stakeholder issue briefs — index and dependency-ordered plan

Audience: the higher-reasoning planner (Claude/Opus pass) that turns each brief into an implementation plan. Generated 2026-10-06 by ten parallel repo-analysis agents against `main`, verified against the extracted Oct-2 stakeholder docs in `docs/10-2-2026/extracted/`.

Deadline model: **Oct-14 milestone board** (`#1 — Oct-14 stakeholder board`, due 2026-10-14) → **Oct-16 run-through** (deployment must be live + verified) → **Oct-30 fix-up** (post-run-through polish window).

## Files

| Brief file | Issues | Assignee-side theme |
|---|---|---|
| `issue-325-upload-refusal.md` | #325 | Upload pipeline — 500-char cell cap vs `event_description` |
| `issue-318-event-descriptions.md` | #318 | `event_description` end-to-end (layout→ingest→migration→API→UI) |
| `issue-319-271-instructor-detail-and-snapshot.md` | #319, #271 | Run snapshot + instructor per-team detail (one shared fix) |
| `issue-321-status-and-feedback.md` | #321 | Persistent team status band + every-press feedback + missing confirms |
| `issue-326-lock-again.md` | #326 | `exercise_result_unlock.closed_at` tri-state + lock route + D16 swap |
| `issue-328-results-lock-visibility.md` | #328 | Team-side read of lock/run state + three button states + confirm |
| `issue-329-refresh-visibility.md` | #329 | `refreshed_at`, before/after marker counts, `refresh_marks`, choice gate |
| `issue-330-refresh-all-report.md` | #330 | Refresh-all honest label + per-team refreshed/skipped reasons |
| `issue-331-273-323-decisions-and-ops.md` | #331, #273, #323 | Seed-on-reset decision, `license_line` decision, Oct-16 ops runbook |
| `issue-335-295-download-and-baseline-seed.md` | #335, #295 | CSV plain marker labels + pink-column negative test; email-everyone seed decision |

## Issue status at a glance

Sprint status column added 2026-10-06 (Oct-14 stakeholder sprint). "Landed" means merged to `main`. "PR open" means built, reviewed by an agent, not merged. Updated 2026-10-07; plans and this index are PR #347. Plans: `docs/plans/2026-10-14-stakeholder-sprint/`. Deferred questions and defaults taken: `docs/plans/open-questions/oct14-deferred.md`.

| Issue | State | Gate | Sprint status 2026-10-07 |
|---|---|---|---|
| #325 | Implementation-ready | Decide cap (recommend 2,000) + required-vs-optional column; coordinate scope split with #318 | **Landed** — merged #339 — plan 001; defaults taken: 2,000 cap, optional column |
| #318 | Implementation-ready, **hard-blocked by #325** | Column required vs optional; fixture commit (strip Read Me/Benchmark, force-add past `*.xlsx` ignore) | **Landed** — merged #339 — plan 002; migration `0044_exercise_event_description`; `.accdb` rebuild is a manual step |
| #319 + #271 | Implementation-ready | Snapshot contract shape; migration-number ordering | **Landed** — merged #345 — plans 005, 006; migration `0046_exercise_run_snapshot` |
| #321 | Ready w/ owner gates | Lock-read exposure (shared w/ #328), run/refresh confirm copy, band scope | **Planned, PR open** #346 — plan 010; stacked on #345 and #340; defaults taken: band on the four team pages, two-press team refresh |
| #326 | Ready w/ decision note | D16 supersession + `unlocked_at` semantics + zero-teams ordering vs #323 | **Landed** — merged #345 — plan 003; migration `0045_exercise_unlock_closed_at`; D16 amended 2026-10-06; needs `GRANT UPDATE ON exercise_result_unlock` at deploy |
| #328 | Ready w/ owner gates | Same lock-read gate as #321; copy pins; #326 interaction (run > open precedence) | **Landed** — merged #345 — plan 004; DESIGN.md §6.14 amended |
| #329 | Ready w/ Chau gates | Mark-vs-exclude non-responders; "refreshed" vs "asked" wording; shared counts shape | **Planned, PR open** #340 — plan 007; defaults taken: mark non-responders, Ann's "Refreshed at" wording |
| #330 | Ready w/ owner gates | Reason-code set; `dataset_label` in report; label copy | **Planned, PR open** #340 — plan 008 |
| #331 | **Decision-gated** — checklist §8 says preserve seed; code + tests + docs say regenerate | Ann/Chau decision; then docs+test inversion | **Planned, PR open** #344 — plan 011; implemented on checklist §8 (owner ruling); D7 amended 2026-10-06; re-point still draws a new seed (OQ-OCT14-05) |
| #273 | **Decision-gated** — retire `license_line` column vs per-file addendum | Owner decision; UI is a fixed constant either way | **Deferred** — plan 013; OQ-OCT14-02; issue comment posted |
| #323 | **Ops, deployment-gated** — destructive, needs live env verification | Verify deploy target/commit/dataset checksum first; depends on #326 (close) and #331 (seed) | **Deferred (runbook written, nothing run)** — plan 014; `docs/operations/exercise-oct16-cleanup-runbook.md`; OQ-OCT14-03; owner picks path A/B/C |
| #335 | Implementation-ready | None — plain labels + focused CSV negative test | **Landed** — merged #338 — plan 009 |
| #295 | **Decision-gated** — per-team vs class-wide email-everyone baseline | Ann decision; docs+tests either way | **Deferred** — plan 012; OQ-OCT14-01; issue comment posted |
| D2 undecided goal | Flagged in drafts | Dated decision superseding D2 | **Covered elsewhere** — issue #322 and PR #337 (its decision record supersedes D2); Harbor still needs Ann's written confirmation (OQ-OCT14-04) |

## Blocking decision gates (resolve before code)

1. **#325 cap value** — recommend `event_description`-scoped 2,000 chars (headings stay 500). Affects `workbook.py` signature + `layout.py` declared limits.
2. **#318 column policy** — recommend *optional* `event_description` (old files stay valid; NULL → not rendered). If *required*, the Sept fixture breaks and the Oct-2 workbook must be committed first.
3. **#319/#271 snapshot shape** — `invited_profiles` + `setting_weights` JSONB on `exercise_result_run`; SQL backfill leaves `rank`/`marker`/`reason` absent on old rows.
4. **#321/#328 shared team-side lock read** — both need `results_open`/`results_run` on `EventView` (or equivalent). Reverses DESIGN.md §6.14's deliberate "no team-side read" — needs dated design amendment in the same change.
5. **#326 D16 supersession** — already-run checked before locked; one-way unlock becomes tri-state; record a dated amendment in `docs/decisions/class-exercise-decisions-2026-09-25.md`.
6. **#329 gates** — mark (recommended) vs exclude non-responders; "refreshed" vs product voice "asked" for the shut-state line (wording scan `test_exercise_results_asking_wording.py` bans "refresh" server-side — compose client-side).
7. **#330 gates** — reason-code set (`no_asking_choice | no_round_one_run | already_refreshed`), whether never-entered teams appear, `dataset_label` for the two-file case (never `dataset_id`).
8. **#331** — checklist §8 says clearing a team keeps its chance seed; current code + tests + docs regenerate it. Surface to Ann; do not silently flip.
9. **#273** — retire `license_line` or keep as per-file addendum.
10. **#295** — email-everyone baseline: per-team seed (current) vs class-wide draw for cross-team comparability.
11. **Undecided-goal conflict (no assigned issue; flagged in drafts)** — Sept-25 D2 counts undecided half-credit on exploratory events *including Northline*; Oct-2 review says Northline is not broad. **Do not touch `simulation.py` until a dated decision supersedes D2.**

## Migration-head collision — assign before branching

Three briefs independently plan the next migration after head `0043_exercise_event_exploratory`:

- #318 → `exercise_event.description` (nullable TEXT)
- #326 → `exercise_result_unlock.closed_at` (nullable timestamptz)
- #319/#271 → `exercise_result_run.invited_profiles` + `setting_weights` (nullable JSONB ×2)

Assign 0044/0045/0046 in landing order (suggested: #318 first since it's on the Oct-16 critical path). Whoever lands second/third rebases `down_revision` + `tests/integration/test_exercise_schema_migration.py:72` `HEAD_REVISION`.

## Shared seams — implement once, consume twice+

| Seam | Consumers |
|---|---|
| `EventView.results_open`/`results_run` (`read_events` gains `ResultsRepository`) | #328 three button states; #321 status band |
| `AskingStateView.refreshed_at` + `RefreshView.refreshed_at` | #329 summary; #321 band timestamp |
| `RefreshCountsView` extension (denominator, `marker_counts_before`/`after`) | #329 team summary; #330 instructor report |
| `InvitedProfileView` + run snapshot columns | #271 team results names; #319 instructor detail |
| `invited_without_card` base-field denominator | #329 reported counts; #330 per-team summary |
| `first_round_results` fact on `AskingStateView` | #329 choice gating; #321 band |
| `exercise_result_unlock` tri-state read (`closed_at IS NULL`) | #326 lock/close; #328 `results_open`; #323 runbook |

## Dependency-ordered plan for the Oct-14 board

**Lane A — data file (critical path for Oct-16):**
1. Commit stripped Oct-2 workbook fixture (decision 2) → 2. **#325** cap + optional-column plumbing → 3. **#318** end-to-end description (migration 0044).

**Lane B — results integrity:**
4. **#326** close-again (migration 0045) + D16 amendment + ops-doc grants → 5. **#328** team-side lock/run read + buttons + confirm → 6. **#319/#271** snapshot columns (migration 0046) + instructor detail.

**Lane C — refresh visibility:**
7. **#329** `refreshed_at` + counts + `refresh_marks` + choice gate → 8. **#330** refresh-all report (reuses #329's counts shape).

**Lane D — polish:**
9. **#335** CSV labels + negative test (standalone, can go anytime) → 10. **#321** status band + RefreshAllPanel confirm (consumes every field landed above; last because it aggregates).

**Lane E — decisions (parallel, no code until answered):**
11. **#331** seed-on-reset → 12. **#295** baseline seed → 13. **#273** license line → 14. undecided-goal/Northline D2 conflict (new decision record; no issue yet — create one on the milestone if confirmed uncovered).

**Oct-16 ops:** **#323** runs only after #326 ships (close needs the lock route) and after #331 is decided (cleared teams' seed semantics); runbook order is **close results before clearing Teams 1–4** unless the zero-teams fallback lands. Verify `/api/health` release SHA before and after.

## Cross-cutting cautions

- **Contracts:** exercise routes are absent from `contracts/openapi/smartmatch.json` (CBA-scope export). Contract guard = hand-mirrored `exerciseClient.ts` + model-walk tests (`test_exercise_results_contract.py`, `test_exercise_matching_router.py`, `test_exercise_workspace_router.py`, `test_exercise_instructor_router.py`). `make openapi-check` is a no-op but cheap.
- **Forbidden fields:** `seed`, `token`, `workspace_id`, `dataset_id`, withheld columns, and `score|percent|confidence|probability|likelihood|share`-shaped names fail the walks. #319/#271 adds `weights` fields → replace the `"weight"` substring ban with a positive allowlist (see brief §5).
- **File ceilings:** `exercise_instructor.py` 698/800 lines; `exercise_instructor_refresh.py` 203/800. New modules must be added to `_TRACK_MODULES` + both pyproject import-linter lists.
- **Copy ledger:** every new sentence lands in `DESIGN.md` §11.1 in the same change; amend §6.14 (no-team-side-lock-read) when #328/#321 ship.
- **`.accdb` fixture** regeneration needs Microsoft Access on Windows (`tools/compute_event_major_fit.ps1`) — manual ops step for the workbook work.
- **Workbook verified:** `event_description` cells contain only the public text (E11/Northline 571 chars, E12/Harbor 561 chars); "why someone would come" notes are checklist-only prose, not workbook data — safe for participant-facing views.
- **Nothing here changes product code.** These are planning artifacts only.
