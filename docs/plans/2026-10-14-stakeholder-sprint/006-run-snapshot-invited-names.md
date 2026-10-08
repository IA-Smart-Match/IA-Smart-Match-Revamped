# 006 — A run keeps the names it invited (#271)

Lane B, branch `oct14/results-lock-snapshot`. Shares one fix with plan 005 (#319): this file holds the migration, the write path and the team-side read; 005 holds the instructor view that also reads the snapshot. Each stands on its own.
Seams are `file:line` on `origin/main` @ `ec471ba2`.

Paths: `persistence/` = `python/smartmatch_persistence/smartmatch_persistence/exercise/`, `routers/` = `services/api/smartmatch_api/routers/`, `web/` = `apps/web/legacy-frontend/src/`.

## Current behavior

- A run stores profile **numbers** and a `setting_name` label; no names, no weights (`persistence/schema.py:397-443`).
- The results screen gets names by asking the ranked-list route for the run's setting (`web/app/pages/exercise/ExerciseResults.tsx:110-114, 161-183`).
- Delete that setting and the list route answers 404 `exercise_setting_unknown`; the catch returns an empty map; every chip reads "Profile 17" (`web/…/ResultPanels.tsx:230-231`).
- Re-save the setting under the same name and the names shown are a different list from the one the run invited. Same after a refresh changes the team's view.
- The full ranked entries are in hand at run time and thrown away down to ints (`routers/exercise_results_run.py:200-238`).

## Ordered change list

1. **Migration** `db/migrations/versions/0046_exercise_result_run_snapshot.py`: `revision = "0046_exercise_result_run_snapshot"`, `down_revision = "0045_exercise_result_unlock_closed_at"`. Adds to `exercise_result_run`:
   - `invited_profiles JSONB NULL` — list of `{rank, profile_no, display_name, major, class_year, marker, reason}` in rank order.
   - `setting_weights JSONB NULL` — the four stated weights the list was built with.
   **SQL-only backfill**, no domain import:
   - `invited_profiles` ← `jsonb_agg(jsonb_build_object('profile_no', …, 'display_name', …, 'major', …, 'class_year', …) ORDER BY ord)` over `unnest(invited_profile_nos) WITH ORDINALITY` joined to `exercise_profile` on `(dataset_id, profile_no)`. **No `rank`, `marker` or `reason` key is written**: they depended on the weights and the team's view at run time and cannot be rebuilt.
   - `setting_weights` ← `exercise_saved_setting.weights` on `(workspace_id, event_key, name = setting_name)` where that row still exists; otherwise stays NULL.
   Downgrade drops both columns.
2. **Schema mirror** `persistence/schema.py:397-443` + head pins bumped to `0046_…` (same files as plan 003 step 4).
3. **Value type** `persistence/results_rows.py` — frozen `InvitedProfile(rank: int | None, profile_no: int, display_name: str, major: str | None, class_year: str | None, marker: str | None, reason: str | None)` and the two JSON conversions (defensive on read: a missing key is `None`, a non-list is empty). `StoredResultRun` gains `invited: tuple[InvitedProfile, ...] = ()` and `setting_weights: Mapping[str, float] | None = None`. Re-exported through `exercise_dependencies` (`:139-145`, `__all__` `:167-235`).
4. **Write/read** `persistence/results_repository.py:376-459, 675-712` — `record_run` gains `invited: Sequence[InvitedProfile]` and `setting_weights`; writes both columns. `_one` selects them. Nothing else about the three statements or the lock changes.
5. **Run path** `routers/exercise_results_run.py:200-238, 298-332, 400-441`:
   - `_invited_profile_nos` → `_invited_entries`, returning `InvitedProfile` values built from `ranked.entries` and `rankable.facts` (the same facts `ranked_list_view` reads, `routers/exercise_matching_models.py:659-679`).
   - `invited_list` returns the entries and the weights beside the profiles and the setting name.
   - `store` passes `invited=` and `setting_weights=effective_weights(weights)` (`routers/exercise_matching_weights.py:195-206`).
   - `run_results` (`routers/exercise_results.py:236-263`) threads them through; `run_the_rule` still receives plain numbers.
6. **Team response** `routers/exercise_results_models.py:340-377, 481-506` — `InvitedProfileView` (the shared model, see plan 005) and `ResultsView.invited_profiles: list[InvitedProfileView]`, top level. **Not** on `ResultPanelView`: "email everyone" shares that model and stays counts-only. `PreviousRoundView` unchanged.
7. **Delete flow** — nothing changes on `DELETE …/settings/{name}`. That is the point.
8. **Client** `web/lib/exerciseClient.ts` — `InvitedProfileView`; `ResultsView.invited_profiles`.
9. **Screen** `web/…/ExerciseResults.tsx:99-117, 161-183` — once there is a run, `names` is built from `results.invited_profiles`; the ranked list is read only for `factor_labels` (default weighting, constant labels) and never for the run's setting. `ResultPanels.tsx` keeps "Profile N" only for a number the snapshot does not name; its docstring is updated.
10. **Docs** — spec note in `ResultPanels.tsx`/`ExerciseResults.tsx` docstrings (the "names joined from the ranked list" owner decision of 2026-09-21 is replaced by the stored snapshot); `docs/plans/backlog.md:17` entry marked done if it is still listed.

## Test plan

| File | Adds |
|---|---|
| `tests/integration/test_exercise_result_run_snapshot_migration.py` (new) | upgrade adds two nullable JSONB columns; a pre-existing run is backfilled with names in stored order and **without** `rank`/`marker`/`reason` keys; weights backfilled only where the setting survives; downgrade drops both |
| `tests/integration/test_exercise_results_persistence.py` | record a run, delete the setting row, `get_run` still returns the snapshot and weights; JSONB round-trip; a NULL legacy row reads `invited == ()`, `setting_weights is None` |
| `tests/unit/exercise_results_router/test_exercise_results_rules.py` + `support.py` | a run stores the ranked snapshot (rank order, marker, reason) and the four weights; **run → DELETE setting → GET results still names everyone**; re-saving the name does not change the stored names |
| `tests/unit/exercise_results_router/test_exercise_results_panels.py` | `invited_profiles` on the response; a backfilled-shape row (no rank/marker/reason) serializes with nulls |
| `tests/unit/exercise_results_router/test_exercise_results_contract.py` | unchanged and green: no forbidden or score-shaped name reachable |
| `web/…/ExerciseResults.test.tsx` | names come from the snapshot; no `…/list?setting=` request after a run; deleted-setting case still shows names |
| `web/…/ResultPanels.test.tsx` | "Profile N" only for an unknown number |

Commands:

```
PARENT/.venv/bin/python -m pytest tests/unit/exercise_results_router -q
PARENT/.venv/bin/python -m pytest tests/integration/test_exercise_results_persistence.py -q
PARENT/.venv/bin/python -m pytest tests/integration/test_exercise_result_run_snapshot_migration.py -q
npx vitest run --pool=threads src/app/pages/exercise/ExerciseResults.test.tsx src/app/pages/exercise/ResultPanels.test.tsx
```

## Acceptance (Oct-2 lines this satisfies)

- Checklist §5: "Changing the sliders after the run does not change the results already shown."
- Checklist §5: "Results stay on screen after a reload, and the instructor can see them."
- Checklist §4: "Delete a setting. It asks first, then says “Deleted.”" — and the run's names survive it (issue #271).
- Revisions §2: "its list of names, its results for each event" (the instructor view in plan 005 reads this snapshot).

## Decision status

| Gate | Default taken | Record |
|---|---|---|
| Snapshot contract shape | two nullable JSONB columns on `exercise_result_run`; seven-field entry; rank order | OQ `lane-b.md` B-7 |
| Old rows | names/major/year backfilled in SQL; `rank`/`marker`/`reason` left absent, served as null | OQ B-7 |
| Old rows' weights | backfilled from the saved setting **as it stands at migration time**; a setting re-saved since the run would show its newer numbers. NULL when deleted | OQ B-11 |
| Where names sit on the team response | `ResultsView.invited_profiles`, not on the panel model | this plan |
| Migration numbering | `0046`, after Lane B's `0045` and Lane A's `0044`. PR #337 also numbers a migration `0044`; numbering here stays as assigned | PR body |

Cross-reference: plan 005 (`005-instructor-team-detail.md`) — the instructor's per-team view, the `weight` guardrail change and the new instructor module.

## As built (2026-10-06, PR #345, commit `0d88b3a0`)

Where the implementation differs from the plan above:

1. **Revision id.** The file is `0046_exercise_result_run_snapshot.py`; the revision id is `0046_exercise_run_snapshot` and its down revision is `0045_exercise_unlock_closed_at`. The planned ids are longer than `alembic_version.version_num` (`VARCHAR(32)`) allows.
2. **Step 3.** `InvitedProfile` puts `profile_no` and `display_name` first and defaults the other five to `None`, so a backfilled row is constructed without naming what it lacks.
3. **Step 5.** `invited_list` returns four values: profiles, entries, setting name, weights. `run_the_rule` receives `[entry.profile_no for entry in invited]`.
4. **Step 6.** `ResultsView.invited_profiles` defaults to an empty list; the client type marks it optional so older fixtures type-check.
5. **Step 9.** `ResultPanels` reads the names from the run itself (`namesFromRun`) when no `names` prop is given; the screen no longer passes one. Before a run the ranked list is read once with the default weighting, for the factor words only.
6. **A zero-invite run** is left with `invited_profiles` NULL by the backfill (an empty array aggregates to no row); covered by a migration test.
7. **Step 10.** The backlog row "Results names are lost when the run's saved setting is deleted afterwards" was removed. The neighbouring row "The invited-names list is not in rank order" is **not** fixed: the team's chips still follow `invited_profile_nos`. The snapshot now holds the rank order, so that fix is a few lines in `ResultPanels.tsx`.
