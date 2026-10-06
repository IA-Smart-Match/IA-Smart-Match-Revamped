# 012 — "Email everyone" baseline: per-team seed or one class-wide draw (#295)

**Deferred. No code in this sprint.** Open question: `docs/plans/open-questions/oct14-deferred.md` → OQ-OCT14-01. Seams verified against `origin/main` on 2026-10-06.

## Current behavior

- One seed drives both panels. `services/api/smartmatch_api/routers/exercise_results_run.py:273` passes `seed=seed` to the team's run and `:283` passes the same `seed` to `run_email_everyone`.
- The baseline's inputs are per-team too. `exercise_results_run.py:264-265` builds `everybody` with this team's "stopped responding" set, so two teams' round-two baselines can differ even on one seed.
- The contract says so on purpose: `ResultsView.email_everyone` in `exercise_results_models.py` ("the same rule with the same seed"), `run_email_everyone` docstring (`simulation.py:657`), design spec §10 (`docs/superpowers/specs/2026-09-16-class-exercise-design.md:287-288`).
- Pinned by `tests/unit/exercise_results_router/test_exercise_results_panels.py:81` `test_email_everyone_uses_the_same_seed_as_the_teams_own_list` and `test_exercise_results_refresh.py:164` (a silenced profile signs up in neither panel).
- Stored, not recomputed: `exercise_result_run.email_everyone` is written once. A change affects future runs only. No migration under any option.
- Since #331 (plan 011) a cleared team keeps its seed, so its baseline no longer changes after a clear. That removes one cost of the status quo.

## Ordered change list — conditional on the answer

**Option A — keep the per-team seed (recommended default). No code.**
1. Move the `docs/plans/backlog.md:20` row out with a dated decision line (owner PR).
2. Add checklist-§5 wording to the run-through notes: "the two baselines can differ a little, like the two teams".

**Option B-ii — one class-wide baseline (seed and inputs both team-independent).**
1. `simulation.py` is frozen for this sprint (PR #337 owns it). Do the work after #337 merges.
2. `exercise_results_run.py:263-283`: derive a baseline seed from the dataset checksum with `determinism.stable_digest` (SHA-256; same source the fixed order uses), build a second `everybody` with no silenced set, pass both to `run_email_everyone`.
3. Reword `ResultsView.email_everyone` (`exercise_results_models.py`) and the `run_email_everyone` docstring (`simulation.py:647-661`) — the "same seed" sentence becomes false.
4. Tests: invert `test_exercise_results_panels.py:81` to "the baseline is identical for two teams"; invert `test_exercise_results_refresh.py:164`; give `tests/integration/exercise_class_driver.py:280-302` `recompute` a baseline-seed path.
5. Docs: spec §10 `:287-288`; backlog row; dated amendment under D7.
6. The seed stays off every response model. No new field.

**Option B-i — shared seed only.** Steps 2 (seed half), 3, 4 (first test only), 5. Round-one baselines match; round-two baselines can still differ under "required". Half a fix — not recommended.

## Test plan

- A: none.
- B-ii: the three test edits above, then `tests/unit/exercise_results_router/` (two files), `tests/integration/test_exercise_full_class_run.py`, `tests/golden/exercise/test_exercise_simulation_golden.py` (must stay green unchanged — it tests the rule as a pure function of a seed). One pytest process at a time.

## Acceptance

- Checklist §5: "Next to them, always: the result of emailing all 300, with the same four numbers."
- Checklist §5: "Run the same list for two different teams. Each team's result is fixed and repeatable, but the two teams can differ a little because of chance."
- Under B-ii only: all six teams' `email_everyone` panels for one event on one data file are identical, and a test pins it.

## Decision status

- **Deferred to Ann** (Chau for the seed source if B). Not asked before; this sprint posts the question on #295.
- **Default while unanswered: A.** Nothing changes; the Oct-16 run-through sees per-team baselines.
- **Needed by:** 2026-10-16 to be seen in the run-through; otherwise it lands in the 2026-10-30 fix-up.
- This differs from the brief, which recommends sending B-ii. Reason: A needs no code before Oct 16, the checklist does not ask for identical baselines, and #331 removed the reset side-effect. B-ii stays the answer if Ann wants one number on every projector.
