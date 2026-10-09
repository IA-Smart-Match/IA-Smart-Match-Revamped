# 011 — Clearing one team's work preserves that team's chance seed (#331)

Branch `oct14/seed-preserve-reset` → PR against `main`. No migration. Seams verified against `origin/main` on 2026-10-06.

## Current behavior

- `python/smartmatch_persistence/smartmatch_persistence/exercise/workspace_repository.py:480-550` `reset_team` deletes the workspace's overlay, saved settings and result runs, then updates the workspace row with `seed=new_workspace_seed()` (`:546`), `asking_choice=None`, `refreshed_at=None`. The docstring (`:481-493`) argues regeneration is "the one thing a reset in a classroom is for".
- One application caller: `ExerciseInstructorRepository.reset_team` (`instructor_repository.py:549-590`), reached from `POST /v1/exercise/instructor/workspaces/{n}/reset` (`services/api/smartmatch_api/routers/exercise_instructor.py`, docstring `:555` says "and a new seed").
- Four tests pin a new seed after a reset (the brief listed three; `test_exercise_results_persistence.py:835` was missed):
  1. `tests/integration/test_exercise_workspace_persistence.py:521` (`!=`), module docstring `:13`, test docstring `:495-497`.
  2. `tests/integration/test_exercise_results_persistence.py:835` (`after.seed != before.seed, "a reset regenerates the seed"`).
  3. `tests/integration/test_exercise_full_class_run.py:461-469` (`test_the_reset_cleared_team_3_and_gave_it_a_new_seed`).
  4. The class-run driver `_reset_and_repeat` (`test_exercise_full_class_run.py:232-271`) satisfies checklist §8 only by writing the old seed back with `set_seed` (`:253`).
- Docs that state regeneration: design spec `docs/superpowers/specs/2026-09-16-class-exercise-design.md:317-318`; `docs/operations/exercise-hosting.md:268` (grant table row) and `:655` (day-of-class step 5).
- A re-point (`instructor_repository.py:592-732`, seed at `:723`) also regenerates. Not in this change — see Decision status.

## Ordered change list

1. **Tests first (RED).**
   - `tests/integration/test_exercise_workspace_persistence.py:521` → `==`; rewrite docstring `:13` and `:495-497`.
   - `tests/integration/test_exercise_results_persistence.py:835` → `==`, message "a reset keeps the seed".
   - `tests/integration/test_exercise_full_class_run.py`: rename `:461` to `..._and_kept_its_seed`, assert `==`; in `_reset_and_repeat` delete the `set_seed(sessions, old.id, old.seed)` restore (`:253`) so the rerun proves the route alone gives the same result; compute the "seed matters" comparison with a deliberately different seed (`old.seed + 1`, wrapped below 2**63) so `test_the_seed_changes_the_result` (`:413-416`) keeps its meaning; update the module docstring (`:16`, `:20-22`) and the `_ClassRun` field names.
2. **Persistence (GREEN).** `workspace_repository.py:546`: drop `seed=new_workspace_seed()` from the `UPDATE`; rewrite docstring `:481-493` (checklist §8, 2026-10-06 amendment). `new_workspace_seed` import stays — creation at `:280` still uses it.
3. **Docstrings only.** `instructor_repository.py:484-488` (`reset_workspace_children` "without the seed regeneration"); `exercise_instructor.py:555` ("and a new seed").
4. **Docs.**
   - Spec `:317-318`: fix both stale clauses (the `random.Random(seed ^ hash)` text → the shipped SHA-256 stable digest; "regenerates its seed" → keeps).
   - `exercise-hosting.md:268` and `:655` (and the line refs in those two rows, which had drifted).
   - `docs/decisions/class-exercise-decisions-2026-09-25.md`: dated amendment 2026-10-06 directly under **D7** (the chance element is D7's `chance_spread`; no D-row covers seed lifetime), citing checklist §8.
5. **Not touched.** `simulation.py`, coefficients, any response model, `repoint_workspaces`, migrations, frontend (`InstructorTeams.tsx` confirm copy names settings and runs only — still true).

## Test plan

- RED then GREEN, one pytest process at a time, `PARENT/.venv/bin/python -m pytest`:
  - `tests/integration/test_exercise_workspace_persistence.py`
  - `tests/integration/test_exercise_results_persistence.py`
  - `tests/integration/test_exercise_full_class_run.py`
  - `tests/integration/test_exercise_instructor_persistence.py` (unchanged; proves the re-point path still behaves as documented)
  - `tests/unit/test_exercise_instructor_router.py` (model walk stays green; no seed on any response model)
- Gates: `make format-check lint typecheck imports VENV=PARENT/.venv`.
- Full suite: CI on the PR.

## Acceptance

- Checklist §8: "Clear one team from the instructor page. That team goes back to the start; the others don't change."
- Checklist §8: "After clearing, run the same list again for that team. The result is the same as before (the chance part is fixed per team)."
- Checklist §5: "Each team's result is fixed and repeatable, but the two teams can differ a little because of chance."
- Determinism stays the SHA-256 stable digest; the seed is on no response model.

## Decision status

- **Decided — owner ruling, 2026-10-06:** the explicit Oct-2 checklist §8 text is implemented. Clearing one team's work preserves that team's seed. This flips documented behavior (spec §11, `reset_team` docstring, hosting runbook step 5).
- **What would revert it:** a written change from Ann to checklist §8 saying a cleared team should get a fresh chance draw. The revert is one line (`seed=new_workspace_seed()` back in the `UPDATE`) plus the four test assertions and the same docs.
- **Left as is, recorded as an open question (not flipped on inference):** a **re-point** to a new data file still regenerates every moved team's seed. Checklist §8 speaks only about clearing one team. Entry: `oct14-deferred.md` → OQ-OCT14-05.

## Divergence from this plan

Shipped as PR #344, commit `82994300`. Three small differences from the list above:

1. **Spec §11 was corrected with a dated note, not by rewriting the formula.** `simulation.py`'s docstring says "Design spec §11 writes the chance draw as `random.Random(...)`", and `simulation.py` is frozen this sprint. Rewriting the spec's formula would have made that docstring false. The reset clause was changed in place; the formula is kept and a "Correction, 6 October 2026" note under it states the shipped SHA-256 digest.
2. **`_ClassRun.reset_seed_everyone` was renamed `other_seed_everyone`**, and three rerun tests lost "same_seed" from their names (the seed is now simply the team's). A helper `_another_seed` keeps the comparison seed inside the signed 64-bit range.
3. **`exercise-hosting.md`'s neighbouring line reference** (`workspace_repository.py:535-540`, the three deletes) was updated to `:543-548` because this change moved it.

Local test database: the shared local PostgreSQL could not be used — other lanes' runs sweep "leaked" scratch databases (`tests/integration/migration_harness.py` `_drop_leaked_scratch_databases`) and were dropping this lane's between create and connect. A private throwaway cluster on port 55439 was used instead. Worth knowing for any future wave that runs integration tests in parallel.
