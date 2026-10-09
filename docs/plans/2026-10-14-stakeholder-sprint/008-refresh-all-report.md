# 008 — Instructor every-team refresh: honest label + per-team report (#330)

Lane C, branch `oct14/refresh-visibility`, PR #340. Builds on 007. No migration.

## Current behavior (verified against the worktree, 2026-10-06)

- `refresh_all_workspaces` (`services/api/smartmatch_api/routers/exercise_instructor_refresh.py:96-146`) loops `results.workspaces_awaiting_refresh` — chosen ∧ not refreshed only. Never-chosen and already-refreshed teams are not visited and not reported.
- `_refresh_candidate` (`:149-203`) returns a bool. `False` conflates "no round-one run" with "claim lost". Counts from `refresh_one_team` are dropped.
- `RefreshAllView` (`exercise_results_models.py`) = `refreshed_team_numbers`, `refreshed`, `skipped` (count only, one implied reason).
- One `now`, one `session.commit()` after the loop: all or nothing.
- Client `RefreshAllPanel` (`InstructorUnlock.tsx:357-424`): button "Ask for every team"; one sentence that hard-codes the only skip reason.

## Ordered change list

1. `python/smartmatch_persistence/smartmatch_persistence/exercise/results_rows.py` — new `WorkspaceRefreshStatus` (`workspace_id`, `dataset_id`, `dataset_label`, `team_number`, `asking_choice`, `refreshed_at`, `seed` with `repr=False`).
2. `results_repository.py` — new read `workspaces_refresh_status(session)`: every workspace, joined to its data file for the label, ordered `uploaded_at, dataset id, team_number` (the Teams panel's order). `workspaces_awaiting_refresh` is left in place.
3. `services/api/smartmatch_api/exercise_dependencies.py` — re-export `WorkspaceRefreshStatus`.
4. `exercise_results_models.py` — new `RefreshAllTeamView` (`team_number`, `dataset_label`, `outcome`, `reason_code`, `refreshed_at`, `refresh_counts: RefreshCountsView | None`, `first_round_event_name`); `RefreshAllView` += `teams: list[RefreshAllTeamView]`. `refreshed_team_numbers`, `refreshed`, `skipped` keep their meaning.
5. `exercise_instructor_refresh.py` — classify every workspace: `no_asking_choice` → skipped; already has `refreshed_at` → skipped `already_refreshed` (carries the stored time); else attempt. No round-one run → `no_round_one_run`. Claim lost → re-read `team_state` and classify by what it says. Refreshed → `refresh_report` from the re-read view (007's shape). Same single `now`, same single commit, no per-team transaction.
6. `apps/web/legacy-frontend/src/lib/exerciseClient.ts` — mirror.
7. `refreshWording.ts` — `refreshAllHeadline`, `refreshAllTeamLine` (reason code → words, client-side).
8. `InstructorUnlock.tsx` — button label "Refresh every team that has chosen how to ask"; panel title, explainer and pending label to match; result = done notice + one line per team. No confirm step added (belongs to #321); the button's `onClick` stays one function so a confirm can wrap it.
9. `docs/design/class-exercise/DESIGN.md` — §6.24, §7.11, §11.1 rows beside the instructor rows.
10. `tests/unit/exercise_results_router/support.py` — fake gains the new read.

## Test plan

- `tests/unit/exercise_results_router/test_exercise_results_refresh.py`: existing refresh-all tests stay green; new: report lists every team with each of the three reasons; refreshed entry carries counts + time + event name equal to what that team's own GET then reads; already-refreshed entry carries its stored time; legacy `skipped` unchanged; a team reset between enumeration and claim is not mislabeled.
- `tests/unit/exercise_results_router/test_exercise_results_contract.py`: new model walked automatically.
- `tests/integration/test_exercise_results_persistence.py`: `workspaces_refresh_status` membership, label and order (PostgreSQL).
- Vitest: `ExerciseInstructor.teams.test.tsx`, `ExerciseInstructor.signout.test.tsx`, `ExerciseInstructor.test.tsx`, `refreshWording.test.tsx`.
- Gates: `make format-check lint typecheck imports scan VENV=<parent>/.venv`.

## Acceptance (Oct-2)

- Checklist §6: "The instructor's button that refreshes every team at once (now labeled 'Ask for every team') says, after running, which teams were refreshed and which were skipped and why."
- Revisions §3: "…should give the same kind of summary for each team, and its label should say what it does."

## Decision status

| # | Question | Default taken | Source |
|---|---|---|---|
| C8 | Reason-code set | `no_asking_choice`, `no_round_one_run`, `already_refreshed` | brief §5.6 |
| C9 | Never-entered teams | Not listed: only teams that exist | brief §5.2 |
| C10 | Two-file case | `dataset_label` on every entry; shown only when the report spans more than one file. Never `dataset_id` | brief §5.4 |
| C11 | Counts on skipped teams | `null`; `already_refreshed` carries its stored time | brief §5.5 |
| C12 | Button label | "Refresh every team that has chosen how to ask" | brief §5.7 |
| C13 | Additive vs replace | Additive `teams`; legacy three fields unchanged | lane constraint |

OQ entries: `docs/plans/open-questions/oct14-deferred.md` (Lane C section).

## As built (2026-10-06, commit 026bbe19 on `oct14/refresh-visibility`)

Divergences from the list above:

- `_refresh_candidate` is replaced by `_refresh_team` + `_skipped` + `_claim_lost`; the route no longer calls `workspaces_awaiting_refresh` (kept in the repository; its integration tests still pass).
- `RefreshAllTeamView` also carries `first_round_event_name`, so a refreshed team's line can name the event.
- A refreshed team's line ends with the completed-card count before and after, not the full three-line strip.
- `tests/authz/test_policy_matrix.py` prose was left unchanged (optional in the brief).
