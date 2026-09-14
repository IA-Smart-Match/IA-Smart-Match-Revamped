# PR 157 Query-Cache Contract Tests Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make PR 157's Python source-contract tests validate the principal-scoped React Query implementation without weakening their error, tenancy, or feedback-privacy guarantees.

**Architecture:** Keep production TypeScript unchanged. Update the three failing Python contract modules so their assertions trace the new derived-state and shared-error-helper data flow instead of requiring removed React setters or matching an unrelated cache-key substring.

**Tech Stack:** Python 3.12/pytest source-contract tests, TypeScript/React 18, TanStack Query 5, PostgreSQL 16 for the full CI reproduction.

---

### Task 1: Follow dashboard refusal errors through the shared query helper

**Files:**
- Modify: `tests/unit/test_frontend_dashboard_stats_contract.py:43-47,766-779`
- Read: `apps/web/legacy-frontend/src/app/hooks/useScopedQuery.ts`
- Read: `apps/web/legacy-frontend/src/app/pages/coordinator/CoordinatorHome.tsx`

- [ ] **Step 1: Preserve the established RED result**

Run:

```bash
/tmp/ia-smart-match-pr157-venv/bin/pytest \
  tests/unit/test_frontend_dashboard_stats_contract.py::test_the_statistics_surface_renders_the_servers_refusal -q
```

Expected: FAIL because `CoordinatorHome.tsx` delegates error description to `useScopedQuery.ts` and no longer contains `cause.message` or `error.message` itself.

- [ ] **Step 2: Point the source contract at the shared helper and full render path**

Add the helper path beside `STATS_PAGE`:

```python
SCOPED_QUERY_HOOK = FRONTEND_SRC / "app" / "hooks" / "useScopedQuery.ts"
```

Replace the old implementation-token assertions with:

```python
page_code = _code_only(STATS_PAGE.read_text(encoding="utf-8"))
query_code = _code_only(SCOPED_QUERY_HOOK.read_text(encoding="utf-8"))

assert 'const feedback = queryToLoaded(feedbackQuery, "The unit feedback summary")' in page_code
assert "<StudentFeedbackPointer state={feedback} />" in page_code
assert "{state.error}" in page_code
assert "cause instanceof ApiRequestError" in query_code
assert "cause.message" in query_code, (
    "the shared query helper must preserve the server's own refusal text"
)
```

- [ ] **Step 3: Verify the dashboard refusal guard is GREEN**

Run the Step 1 command again.

Expected: PASS.

### Task 2: Assert derived missing-unit state in the migrated hooks

**Files:**
- Modify: `tests/unit/test_frontend_granted_unit_contract.py:157-196`
- Read: `apps/web/legacy-frontend/src/app/hooks/useOutreach.ts`
- Read: `apps/web/legacy-frontend/src/app/hooks/useRewards.ts`
- Read: `apps/web/legacy-frontend/src/app/hooks/useSpeakerInvitations.ts`

- [ ] **Step 1: Preserve the three established RED cases**

Run:

```bash
/tmp/ia-smart-match-pr157-venv/bin/pytest \
  tests/unit/test_frontend_granted_unit_contract.py::test_no_unit_is_its_own_state_and_carries_no_load_error -q
```

Expected: three FAIL results because the hooks now derive `status` and `loadError` directly instead of calling `setStatus` and `setLoadError`.

- [ ] **Step 2: Assert behavior-shaped derived state rather than removed setters**

Update the test docstring to describe a derived `"idle"` status and `null` load error. Replace the setter assertions with:

```python
assert re.search(r'const status(?::\s*\w+Status)?\s*=\s*unresolved\s*\?\s*"idle"', code), (
    f"{path.name} must derive idle status from a missing unit"
)
assert re.search(r"const loadError\s*=\s*unresolved\s*\?\s*null", code), (
    f"{path.name} must derive no load error from a state in which nothing was attempted"
)
```

- [ ] **Step 3: Verify all three missing-unit cases are GREEN**

Run the Step 1 command again.

Expected: three PASS results.

### Task 3: Make the Connector feedback guards distinguish cache keys from routes

**Files:**
- Modify: `tests/unit/test_frontend_student_feedback_contract.py:276-296,716-749`
- Read: `apps/web/legacy-frontend/src/app/pages/coordinator/CoordinatorSpeakerFeedback.tsx`

- [ ] **Step 1: Preserve the two established RED results**

Run:

```bash
/tmp/ia-smart-match-pr157-venv/bin/pytest \
  tests/unit/test_frontend_student_feedback_contract.py::test_the_connector_page_never_reads_a_students_own_feedback_route \
  tests/unit/test_frontend_student_feedback_contract.py::test_the_connector_page_still_reports_a_failed_summary_per_speaker -q
```

Expected: two FAIL results because `speaker-feedback-roster` contains an over-broad forbidden substring and the roster failure now derives from `rosterQuery.isError` rather than `setLoadError`.

- [ ] **Step 2: Forbid the actual student read surface**

Change the privacy loop to:

```python
for forbidden in (
    "fetchMySpeakerFeedback",
    "/student/events/",
    "submitSpeakerFeedback",
    "withdrawSpeakerFeedback",
):
    assert forbidden not in code, (
        f"the Connector page references {forbidden!r}; its only feedback read is the "
        "aggregate (OQ-CBA-003 part 1)"
    )

assert "fetchSpeakerFeedbackSummary" in code
```

- [ ] **Step 3: Assert the distinct roster-query failure path**

Replace the `setLoadError` assertion with:

```python
assert "const loadError = rosterQuery.isError" in code, (
    "the roster-level failure path must remain distinct from the per-speaker one"
)
assert "rosterQuery.error instanceof ApiRequestError" in code
assert "rosterQuery.error.message" in code
assert "{loadError}" in code
```

- [ ] **Step 4: Verify both feedback guards are GREEN**

Run the Step 1 command again.

Expected: two PASS results.

### Task 4: Run focused and complete verification

**Files:**
- Verify: `tests/unit/test_frontend_dashboard_stats_contract.py`
- Verify: `tests/unit/test_frontend_granted_unit_contract.py`
- Verify: `tests/unit/test_frontend_student_feedback_contract.py`
- Verify: `apps/web/legacy-frontend`

- [ ] **Step 1: Run the three affected Python modules**

```bash
/tmp/ia-smart-match-pr157-venv/bin/pytest \
  tests/unit/test_frontend_dashboard_stats_contract.py \
  tests/unit/test_frontend_granted_unit_contract.py \
  tests/unit/test_frontend_student_feedback_contract.py -q
```

Expected: PASS.

- [ ] **Step 2: Run Python format and lint checks**

```bash
/tmp/ia-smart-match-pr157-venv/bin/ruff format --check \
  tests/unit/test_frontend_dashboard_stats_contract.py \
  tests/unit/test_frontend_granted_unit_contract.py \
  tests/unit/test_frontend_student_feedback_contract.py
/tmp/ia-smart-match-pr157-venv/bin/ruff check \
  tests/unit/test_frontend_dashboard_stats_contract.py \
  tests/unit/test_frontend_granted_unit_contract.py \
  tests/unit/test_frontend_student_feedback_contract.py
```

Expected: both commands exit 0.

- [ ] **Step 3: Run frontend tests, type checking, and production build**

From `apps/web/legacy-frontend`:

```bash
npm test
npm run typecheck
npm run build
```

Expected: all commands exit 0; record and assess any build warning.

- [ ] **Step 4: Run the exact Python CI suite against PostgreSQL 16**

Start the temporary database, apply migrations, and run:

```bash
SMARTMATCH_DATABASE_URL='postgresql+psycopg://smartmatch:smartmatch@localhost:55432/smartmatch' \
  /tmp/ia-smart-match-pr157-venv/bin/pytest tests/ -m 'not e2e' \
  --cov=smartmatch_domain --cov=smartmatch_authz --cov=smartmatch_providers \
  --cov=smartmatch_persistence --cov-report=term-missing
```

Expected: 0 failures and the same two documented skips.

- [ ] **Step 5: Review and commit the repair**

```bash
git diff --check
git diff -- tests/unit/test_frontend_dashboard_stats_contract.py \
  tests/unit/test_frontend_granted_unit_contract.py \
  tests/unit/test_frontend_student_feedback_contract.py
git add tests/unit/test_frontend_dashboard_stats_contract.py \
  tests/unit/test_frontend_granted_unit_contract.py \
  tests/unit/test_frontend_student_feedback_contract.py \
  docs/superpowers/plans/2026-09-14-pr-157-query-cache-contract-tests.md
git commit -m "test: align frontend contracts with query cache"
```

Expected: one local implementation commit; no push.
