# 013 — `exercise_dataset.license_line`: retire or keep as a per-file addendum (#273)

**Deferred. No code in this sprint.** Open question: `docs/plans/open-questions/oct14-deferred.md` → OQ-OCT14-02. Seams verified against `origin/main` on 2026-10-06.

## Current behavior

- The opening screen shows a fixed line, Ann's approved wording (D13): `apps/web/legacy-frontend/src/app/pages/exercise/ExerciseEntry.tsx` `EXERCISE_LICENSE_LINE`. It renders before any data file exists.
- The column exists and is never written: `schema.py:133`, created in `db/migrations/versions/0037_exercise_tables.py:126`.
- It is read and always `null`: `dataset_repository.py:214` (`DatasetSummary`), `:577`, `:593`; `exercise_instructor_models.py:137` (`DatasetView.license_line`), `:355`; `exerciseClient.ts:251`.
- The instructor page shows it only when non-null: `InstructorDatasets.tsx:362-363`. So it is already "addendum-ready" and shows nothing today.
- Fixtures that carry `license_line=None`/`null`: `tests/unit/test_exercise_instructor_router.py:123`, `tests/unit/test_exercise_matching_router.py:132`, `tests/unit/exercise_results_router/support.py:122`, `tests/integration/test_exercise_dataset_repository.py:212`, `ExerciseInstructor.test.tsx:396,458,499`, `ExerciseInstructor.signout.test.tsx:74`.
- Correction to the brief: the exercise routes are not in `contracts/openapi/smartmatch.json`, so there is no OpenAPI field to remove.
- Checklist §9 ("The opening screen shows the license line once Ann provides it") is already met by the constant. It needs a live check, not code — folded into the #323 runbook pre-flight.

## Ordered change list — conditional on the answer

**Option A — retire the column (recommended, after 2026-10-16).**
1. Migration: next free revision at that time (0044–0046 are taken by this sprint; #337 also claims a 0044). `op.drop_column("exercise_dataset", "license_line")`; downgrade re-adds it nullable. Update `tests/integration/test_exercise_schema_migration.py` `HEAD_REVISION`.
2. `schema.py:133` — remove the column.
3. `dataset_repository.py:198-214,577,593` — remove the field and the two reads.
4. `exercise_instructor_models.py:137-143,355` — remove the field.
5. `exerciseClient.ts:251`; `InstructorDatasets.tsx:29,362-363`; `ExerciseEntry.tsx:27` comment.
6. The eight fixtures listed above.
7. Docs: dated amendment under D13 ("Left over" is closed: column retired); OQ-CE-09 row; `docs/plans/backlog.md:16` row removed; `docs/operations/exercise-hosting.md` §10.
8. Deploy note: a column drop on the shared database. Ship it in a release of its own, not with a run-through deploy.

**Option B — per-file addendum.**
1. Ann supplies the wording rule (what an addendum may say, per file).
2. Upload route (`exercise_instructor.py` is 698 of 800 lines — the new field's handling goes in a new module) takes the addendum as a header or query value; the body stays raw bytes (ruling of 2026-09-21).
3. `dataset_repository.py` `create_dataset` / `_write_rows` (`:400-407`) writes it.
4. Instructor upload form gains one text field; new sentence(s) go into DESIGN.md §11.1.
5. Decide whether teams see it (the opening screen cannot — no data file yet).
6. Dated amendment under D13 reversing its option (a) rejection.

**Option C — leave it.** Docs only: dated line under D13 saying the column stays unused on purpose; close #273.

## Test plan

- A: `tests/integration/test_exercise_schema_migration.py`, `tests/integration/test_exercise_dataset_repository.py`, `tests/unit/test_exercise_instructor_router.py` (model walk), `vitest run --pool=threads` on the two `ExerciseInstructor*.test.tsx` files. Then `grep -rn license_line python services apps/web/legacy-frontend/src tests` returns only the migration files.
- B: one integration test uploading with an addendum; one component test rendering it.
- C: none.

## Acceptance

- Checklist §3: "The opening screen says what the exercise is in one or two sentences, plus the license line once Ann provides it."
- Checklist §9: "The opening screen shows the license line once Ann provides it."
- Both are met today by the constant; the option chosen changes only what happens to the unused column.

## Decision status

- **Deferred.** Ann answers one question (fixed wording vs wording per file). The owner (Danny) answers whether to drop the column and when.
- **Default while unanswered: C in effect** (nothing changes). Recommended once answered: A, after the run-through.
- **Needed by:** nothing before 2026-10-16. Target the 2026-10-30 fix-up.
