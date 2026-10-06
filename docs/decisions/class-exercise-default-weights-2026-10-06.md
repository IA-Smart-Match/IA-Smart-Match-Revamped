# Default weights are 3 / 3 / 2 / 2 — class module and Smart Match platform

**Date recorded:** 2026-10-06 · **Decided by:** Dr. Ann Wang · **Relayed by:** the
owner (Danny) on 2026-10-06 · **Scope:** the class exercise (`ProductScope.CLASS_EXERCISE`)
and the Smart Match CPP platform design · **Status:** recorded, **not yet implemented**

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
2. The weights screen: slider range and step, the running total, the sentence
   explaining how weights compare, and the 390-wide summary bar.
3. Saved settings already stored by teams. They hold the team's own stated
   weights and should not be rewritten.
4. Run snapshots (`exercise_result_run.setting_weights`) keep what the run used.
5. The Smart Match platform default — the CBA-scope default-weight seam has not
   been located for this record; find it before changing anything.
6. Requirements, DESIGN.md §11.1 copy and the decision cross-references.

## Open questions (not answered by the ruling — do not guess)

| OQ | Question | Options | Recommended default | Who |
|---|---|---|---|---|
| **OQ-CE-19** | On what scale are 3/3/2/2 shown and stored? | **A.** Whole numbers 0–10 as in her prototype (sliders `min 0`, `max 10`), no "total". **B.** Keep the 0–1 scale and start at 0.30 / 0.30 / 0.20 / 0.20 (same ratios, total 1.00). | **A** for the platform design; ask before changing the class screens, because B needs no new copy and keeps the weight-total work from PR #256. Rankings are identical under both — only the display differs. | Dr. Wang |
| **OQ-CE-20** | Does "P004 ranks 5th with the starting settings" still have to hold? | Re-state the expected rank under 3/3/2/2, or drop the pinned rank. | Recompute and send her the new rank for confirmation. | Dr. Wang; Chau for the number |
| **OQ-CE-21** | When does the class module switch? | Before the 2026-10-16 run-through, or after it. | Before, so her run-through sees the ruled defaults — but only once OQ-CE-19 is answered. | Owner |

## Related

- `class-exercise-decisions-2026-09-25.md` — a dated cross-reference under the
  weights decision is added with the implementing change, not by this record.
- PR #337 (matching-rule changes) and the results-rule ruling of 2026-10-06 are
  separate decisions; neither sets the default weights.
