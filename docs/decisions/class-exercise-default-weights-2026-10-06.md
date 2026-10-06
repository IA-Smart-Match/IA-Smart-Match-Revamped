# Default weights are 3 / 3 / 2 / 2 — class module and Smart Match platform

**Date recorded:** 2026-10-06 · **Decided by:** Dr. Ann Wang · **Relayed by:** the
owner (Danny) on 2026-10-06 · **Scope:** the class exercise (`ProductScope.CLASS_EXERCISE`)
and the Smart Match CPP platform design · **Status:** recorded, **not yet implemented**; display scale decided the same day (whole numbers 0–10)

## The ruling

The owner relayed Dr. Wang's answer on 2026-10-06:

> Default weights should be 3/3/2/2 — that is the answer from Dr. Wang for the
> class module and the Smart Match platform.

It is corroborated in writing by the prototype she sent the same day
(`docs/design/cpp-prototype/source/`, on branch `demo/cbach-advisory-2026-10-08`).
Her README says the page's code holds "the same four factors and default weights
3/3/2/2", and the page's starting state is
`w:{major:3,interest:3,goal:2,past:2}`.

| Factor | Default weight |
|---|---|
| Same major | 3 |
| Said they are interested (stated interest) | 3 |
| Career goal fit | 2 |
| Past events | 2 |

Her own send date and exact words for this answer were not given to the
repository; only the owner's relay and the prototype are on record.

## Display scale — whole numbers 0 to 10 (decided 2026-10-06)

**Decided by the owner (Danny), 2026-10-06:** weights are shown and set as whole
numbers from 0 to 10, as in Dr. Wang's prototype (sliders `min 0`, `max 10`),
starting at 3 / 3 / 2 / 2. This closes OQ-CE-32. The alternative — keeping the
0-to-1 scale and starting at 0.30 / 0.30 / 0.20 / 0.20 — was not chosen.

What this changes from the screens as built:

| As built (0-to-1 scale) | Ruled (0-to-10 scale) |
|---|---|
| Sliders 0.00–1.00, arrow step 0.05 | Sliders 0–10, step 1 |
| Start at 0.25 each | Start at 3 / 3 / 2 / 2 |
| "Total 1.00" line and the weight-total work from PR #256 | No fixed total; the numbers need not add up to anything |
| "a factor set to 0.50 counts twice as much as one set to 0.25." | The same idea in whole numbers, e.g. a factor set to 4 counts twice as much as one set to 2 — exact sentence to be pinned in DESIGN.md §11.1 with the implementing change |
| 390-wide bar "Weights 0.40 · 0.25 · 0.25 · 0.10 · Total 1.00" | Four whole numbers, no total |

What it does not change: the ranking depends only on how the weights compare, so
3 / 3 / 2 / 2 orders profiles exactly as 0.30 / 0.30 / 0.20 / 0.20 would. All
four at 0 is still the "every weight is 0" case and needs its existing message.

Carried into implementation, not decided here: how saved settings and run
snapshots already stored on the 0-to-1 scale are shown beside new whole-number
ones (convert for display, or show as stored), and whether the API stores whole
numbers or keeps fractions and converts at the edge.

## What it supersedes

- **OQ-CE-02** (`docs/plans/open-questions/class-exercise-open-questions.md`),
  decided 2026-09-25 by Dr. Wang: "Equal is fine. Teams should decide for
  themselves which factors matter most." — equal weights, 0.25 each. Superseded
  for the default values. The second sentence stands: teams still set the
  weights themselves.
- Her 2026-10-02 progress check listed "All start at 0.25" under *What is
  working*. That observation described the site as built and is overtaken by
  this ruling.

## What it leaves standing

- The four factors, their order, the tie-break and the invite limit.
- That teams may change every weight and save up to three settings per event.
- Results, refresh and hidden-column rules — none depend on the starting weights.

## What the code does today (unchanged by this record)

| Seam | Today |
|---|---|
| `python/smartmatch_domain/smartmatch_domain/exercise/registry.py:133-136` | four `*_DEFAULT_WEIGHT` constants, each `0.25` |
| `registry.py:164-170` `EXERCISE_DEFAULT_WEIGHTS` | built from those constants |
| `services/api/smartmatch_api/routers/exercise_matching_weights.py:204` | effective weights start from `EXERCISE_DEFAULT_WEIGHTS` |
| `apps/web/legacy-frontend/src/app/pages/exercise/WeightsControls.tsx:50` | "a factor set to 0.50 counts twice as much as one set to 0.25." |
| `docs/design/class-exercise/DESIGN.md` §6 and §11.1 | slider steps of 0.05, "Total 1.00", the 0.25 examples |
| `docs/product/class-exercise-requirements.md:212, 412` | "Default weights are 0.25 each" |

## Areas an implementation will touch

1. The four default constants and anything pinned to them: golden rankings, the
   sample result, and "P004 ranks 5th with the starting settings" (checklist §4
   and Dr. Wang's 2026-10-02 note) — the starting order changes when same major
   and stated interest outweigh the other two.
2. The weights screen: sliders become 0–10 in steps of 1, the running total and
   its copy go away, and the sentence explaining how weights compare and the
   390-wide summary bar are reworded (see "Display scale" above).
3. Saved settings already stored by teams. They hold the team's own stated
   weights and should not be rewritten.
4. Run snapshots (`exercise_result_run.setting_weights`) keep what the run used.
5. The Smart Match platform default — the CBA-scope default-weight seam has not
   been located for this record; find it before changing anything.
6. Requirements, DESIGN.md §11.1 copy and the decision cross-references.

## Open questions (not answered by the ruling — do not guess)

| OQ | Question | Options | Recommended default | Who |
|---|---|---|---|---|
| **OQ-CE-32** | On what scale are 3/3/2/2 shown and stored? | — | **Closed 2026-10-06 (owner): whole numbers 0–10.** See "Display scale" above. | — |
| **OQ-CE-33** | Does "P004 ranks 5th with the starting settings" still have to hold? | Re-state the expected rank under 3/3/2/2, or drop the pinned rank. | Recompute and send her the new rank for confirmation. | Dr. Wang; Chau for the number |
| **OQ-CE-34** | When does the class module switch? | Before the 2026-10-16 run-through, or after it. | Before, so her run-through sees the ruled defaults. | Owner |

## Related

- `class-exercise-decisions-2026-09-25.md` — a dated cross-reference under the
  weights decision is added with the implementing change, not by this record.
- PR #337 (matching-rule changes) and the results-rule ruling of 2026-10-06 are
  separate decisions; neither sets the default weights.

Open-question numbers 32–34 are used here because OQ-CE-19 to 31 are taken by the
results-rule record of the same date (PR #348).
