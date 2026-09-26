# PR #188 review and implementation plan

Status: review complete; fixes planned, not implemented.

PR: https://github.com/IA-Smart-Match/IA-Smart-Match-Revamped/pull/188

Reviewed head: `f7c91be7c77a31da60bc5dad5c02928221d29991`.
Comparison: `git diff 291b7c35a9ce26b3e7a068c1f41403cc461ae392...f7c91be7c77a31da60bc5dad5c02928221d29991`.
The diff contains 16 files, 4,553 additions and 27 deletions.

Exploration: GPT-5.6 Sol standards and specification reviewers. Parent orchestrator challenged the initial findings, inspected the relevant call paths, and owns this plan. An initial full-history reviewer launch was stopped and replaced with an explicit Sol launch before accepting findings.

Implementation worktree: `.claude/worktrees/agent-a02d657dade9ec6e3`, branch `feat/exercise-matching-api`. This worktree was clean at review. The main checkout contains unrelated user edits; preserve them. Before implementing, recheck HEAD and status and adapt to any concurrent changes.

## Standards review

### F1 — HIGH: re-point and save can deadlock

Evidence at the reviewed head:

- `python/smartmatch_persistence/smartmatch_persistence/exercise/instructor_repository.py:722-738`: re-point takes the membership advisory lock, then workspace row locks through two `FOR UPDATE` scans.
- The call at `:746` reaches `reset_workspace_children`, which first takes the settings advisory lock at `:606-611`.
- `python/smartmatch_persistence/smartmatch_persistence/exercise/settings_repository.py:281-305`: saving takes the settings advisory lock before inserting. The composite parent foreign key is declared in `exercise/schema.py:364-369`.
- This contradicts the explicitly documented order at `settings_repository.py:95-118`: membership, settings, then row locks.

Failing interleaving: re-point owns the workspace row lock; save owns the settings lock; save's foreign-key check waits for the workspace row; re-point waits for the settings lock. PostgreSQL must abort one transaction to break the cycle. This is source-confirmed lock-cycle analysis, not a newly executed PostgreSQL reproduction.

No cosmetic smell or speculative abstraction changes are proposed.

## Specification review

### F2 — MEDIUM: list and CSV resolve saved settings before the event

`services/api/smartmatch_api/routers/exercise_matching.py:512-524` and `:573-585` call `_overrides_for` before `_build_list`. With `?setting=missing`, `_overrides_for` performs the setting lookup at `:403-412`; event validation happens later at `:346-347`.

Consequently, an unknown event plus an unknown setting reports `exercise_setting_unknown`, while the other event routes report `exercise_event_unknown`. This contradicts the PR's declared event-first behavior and the route contract represented by `tests/unit/test_exercise_matching_router.py:864-889`; that test currently omits a setting query. This is a PR-contract inconsistency, not an invented stakeholder requirement about error precedence.

## Implementation sequence

One Sol implementer owns the following files, sequentially. Other agents must remain read-only during implementation. Do not revert concurrent edits. Parent owns this plan and final acceptance.

### 1. Fix F1 and prove lock ordering — 25–40 minutes

Ownership:

- `python/smartmatch_persistence/smartmatch_persistence/exercise/instructor_repository.py`
- `tests/integration/test_exercise_settings_persistence.py`
- `tests/integration/test_exercise_instructor_persistence.py` only if the existing fixture/test placement makes this necessary

Acquire the saved-settings transaction advisory lock immediately after the membership lock and before either workspace `FOR UPDATE` scan. Use the instructor repository's existing scrubbed execution path and its re-point refusal sentence. Keep child-reset locking: transaction advisory locks can be acquired again by the owning transaction. Keep the declared membership → settings → row order and update stale method prose accordingly.

Regression must coordinate actual database transactions with explicit barriers or observed locks and bounded timeouts, not sleep-based timing. Have a saver hold the settings key, start re-point, and verify re-point cannot acquire a workspace row lock while waiting for that key. Allow the save to insert/commit, then let re-point finish. Assert no deadlock, successful re-point, and removal of the old saved setting. The old code must fail the regression. A local fake or an assertion that only checks call order is not sufficient evidence for this defect.

Use an explicitly disposable PostgreSQL test database. Do not run destructive fixture cleanup against a shared developer database. If no safe database is available, record the integration gate as blocked rather than passed.

### 2. Fix F2 and extend route tests — 10–20 minutes

Ownership:

- `services/api/smartmatch_api/routers/exercise_matching.py`
- `tests/unit/test_exercise_matching_router.py`

Resolve the dataset's event before looking up a named weighting in both list and CSV handlers. Prefer passing the already resolved events/event into the existing rendering path so the fix does not add repeated database reads; keep this a small local helper change. Preserve valid-event behavior, weight validation, ambiguity refusals, ranking, reason text, CSV bytes, and response schemas.

Add parameterized HTTP tests for list and CSV with an unknown event plus `?setting=missing`: 404 `exercise_event_unknown`, zero saved-setting lookups and zero profile reads. Retain the valid-event/missing-setting behavior: 404 `exercise_setting_unknown`. Run existing golden ranking and CSV comparisons to detect output drift.

### 3. Verify and independently review — 10–15 minutes

Run targeted matching/workspace unit tests and the exercise settings/workspace/instructor PostgreSQL suites with the worktree's package paths. Run the affected golden, scope/reachability and authorization checks. Run repository format, lint, types, import-boundary, forbidden-behavior and OpenAPI checks. The parent reviews the final diff against F1/F2, then has the Sol reviewer independently check the fixes and tests. Report passed, skipped, blocked and unrun checks distinctly.

Acceptance: both regressions fail before their fixes and pass afterward; the PostgreSQL race is exercised; existing route/domain behavior remains intact; no new migration, API shape change or governance decision is introduced. Publishing or merging is outside this plan.

## Reviewed items excluded from this fix dispatch

| Item | Disposition |
|---|---|
| Senior-first tie-break | Existing readiness gate. OQ-CE-01 remains OPEN; the empty class-year map avoids inventing Ann's vocabulary. Do not claim classroom acceptance is complete or manufacture a year order in this fix. |
| Historical events in the event response | Returning metadata with `is_exercise_event` is explicitly intentional. No binding prohibition was found. Whether matching endpoints should reject historical targets is a separate specification decision; no filter is authorized by this plan. |
| Compare reads profiles twice | Record for refresh/results integration. No current ordinary-workflow acceptance failure was demonstrated. Future mutable-overlay integration should compare both weightings against one captured team view. |
| Raw failure from settings advisory-lock acquisition | Existing integration tests deliberately expect a SQLAlchemy error. No withheld-data leak was demonstrated from the lock statement. Do not expand this patch into generic error handling. |
| Stale workspace during re-point | Composite foreign keys prevent cross-dataset persistence; a sanitized conflict is possible. No corruption demonstrated. |

## Verification at review time

- GitHub reported all 10 checks successful for the reviewed PR head; this does not prove coverage of F1/F2.
- Matching and workspace router unit suites: **139 tests passed**, exit 0, using the parent virtualenv and worktree imports outside the sandbox. The initial sandboxed run stalled and was interrupted; it is not counted as a pass.
- F2 independently reproduced with the PR's in-memory HTTP fixtures: both `/events/unknown/list?setting=missing` and `/events/unknown/list.csv?setting=missing` returned 404 with `exercise_setting_unknown`.
- PR worktree `git diff --check` passed and working tree was clean.
- New PostgreSQL concurrency reproduction: **not run** during this review. It is required before accepting F1's implementation.

Standards: one HIGH finding. Specification/PR behavior: one MEDIUM finding.
Dispatch verdict: **safe to implement this bounded plan; PR needs changes before merge.**
