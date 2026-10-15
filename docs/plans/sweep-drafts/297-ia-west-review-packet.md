> DRAFT — needs IA West review + owner (BrooklynD23) approval. Nothing here is decided.

# #297 — Registry 3.0.0 flip: IA West review packet

Refs #297. Parked behind this: #288 (factor_registry split, B26 card 12).

## 1. The D2 ELI rule in plain words

Source: ADR-0027 "Decision" items 1–5 (`docs/architecture/decisions/ADR-0027-registry-3-engagement-load.md`), code in `python/smartmatch_domain/smartmatch_domain/factor_registry.py`.

1. Each professional gets a **load band** from their confirmed, not-cancelled bookings over the last 90 days divided by the capacity they declared (ELI 2.0.0).
2. Cut points (Q7 = A, owner decision 22 Sep 2026): Light below 50% utilization, Moderate from 50%, Heavy from 80%, Full above 100%.
3. **Full** professionals are removed before matching and listed as `load_full` in the run's excluded list. No override exists.
4. Everyone else keeps their normal score, then it is **multiplied once**: Light 1.00, Moderate 0.90, Heavy 0.70 (`factor_registry.py:794-805`, `ENGAGEMENT_LOAD_SPEC`).
5. **Unknown** load (no declared capacity, or unknown hours) is neutral: multiplier 1.00, labelled Unknown, never treated as zero (ADR-0011).
6. The four weights do not change. The penalty has weight 0 and sits outside the weighted sum (`factor_registry.py:809-813`).
7. Screens show a band word only; hours, capacity and utilization stay in the stored payload (owner ruling R-A, 2026-09-24).

## 2. What changes for coordinators when 3.0.0 is current

1. New match runs are pinned `3.0.0-approved-b26-eli`; old 1.1.1 and 2.0.0 runs still read at their own pin, unchanged.
2. Professionals at Full capacity disappear from new runs' candidate lists and show under "excluded" with a band.
3. Heavy and Moderate professionals rank lower than before for the same fit (x0.70, x0.90).
4. 3.x scores are not comparable with 2.x scores. Do not average, rank or chart them together.
5. A professional with no declared capacity is not penalized and shows load "Unknown".
6. A new run costs one extra query (the engagement read).

## 3. Factor keys and weights

| Factor key | Kind | 2.0.0 physical | 2.0.0 virtual | 3.0.0 physical | 3.0.0 virtual |
|---|---|---|---|---|---|
| `industry_match` | suitability | 0.30 | 0.4286 | 0.30 | 0.4286 |
| `role_match` | suitability | 0.25 | 0.3571 | 0.25 | 0.3571 |
| `cba_semantic_topic` | suitability | 0.15 | 0.2143 | 0.15 | 0.2143 |
| `proximity` | suitability | 0.30 | excluded | 0.30 | excluded |
| `engagement_load` | penalty | not declared | not declared | weight 0, multiplier 1.00 / 0.90 / 0.70 | same |
| `availability` | eligibility | filter, weight 0 | filter | filter, weight 0 | filter |

Declared weights at `factor_registry.py:343-388`; virtual weights are renormalized over the three survivors by `normalize_weights`. Retired G1 pair (`topic_relevance`, `travel_burden`) stays in 2.0.0 only.

## 4. Review questions for IA West

1. Are the cut points right: Light < 50%, Moderate >= 50%, Heavy >= 80%, Full > 100% utilization?
2. Are the multipliers right: Moderate 0.90, Heavy 0.70?
3. Should a Full professional be removed outright, with no coordinator override?
4. Is a 90-day window the right look-back for "load"?
5. Is neutral treatment of Unknown load (multiplier 1.00) acceptable, or should it be flagged to the coordinator?
6. Is showing a band word only (no hours or percentages) right for coordinators?
7. Do you accept that 3.x scores are not comparable with 2.x scores in any report?

## 5. Rollback

Revert one constant in `factor_registry.py`: `CURRENT_CBA_REGISTRY = CBA_REGISTRY` (was `CBA_REGISTRY_3`). New runs return to 2.0.0; stored 3.0.0 runs still read at their own pin. Revert the `CBA_REGISTRY_3` status too to return the gate to `proposed`.

## Open questions

1. `approver="BrooklynD23"` and `approved_on="2026-10-09"` in `CBA_REGISTRY_3` are placeholders. Confirm approver and set the real date at merge.
2. `LoadBandOwnership.review_status` is still `PENDING_OWNER_REVIEW`. ADR-0027 says it becomes `REVIEWED` once IA West reviews. Left unchanged here: it must not be claimed before the review.
3. Weights above are those in `factor_registry.py` on main (0.30/0.25/0.15/0.30). A 3/3/2/2 default-weights ruling exists (#352, 2026-10-06); confirm the review should use the table above and that no reweighting rides this flip.
4. DB-backed suites (`tests/contract`, `tests/integration`, `tests/e2e`) are pinned to 2.0.0 by an autouse fixture so this draft stays reviewable. Does the owner want them migrated to 3.0.0 when the flip merges?
5. Does the flip change the OpenAPI contract? Not checked by regen; `registry_version` is a free string on the wire, so likely no. CI to confirm.
