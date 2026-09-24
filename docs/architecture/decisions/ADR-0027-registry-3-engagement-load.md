# ADR-0027 — Registry 3.0.0: engagement load as a Stage A cap and a Stage B multiplier

**Status:** Proposed
**Date:** 23 September 2026
**Owner of record:** Danny Tran, Development Lead / program owner of record
**Decides:** how registry `3.0.0-approved-b26-eli` applies the Engagement Load Index (ELI 2.0.0): the Q7 band table and who owns it, a multiplier on the CBA composite, removal of a Full pair before the solve, what `registry_hash` covers for a 3.x run, and the one-line procedure that later makes 3.0.0 current.
**Plan:** `docs/plans/2026-09-22-b26-self-service-availability-plan.md` §5.2 (registry items 1–7), §9 Q7; `docs/plans/b26-tracks/T8c-plan.md`
**Relates to:** ADR-0011 (unknown is not zero), ADR-0016 (CBA scoring policy). **Amends ADR-0016 for 3.x runs only:** its "`registry_hash` continues to be `weights_fingerprint`" holds for 1.1.1 and 2.0.0 runs and does not hold for 3.x.

> **Proposed, and not current.** B26 T8c *declares* registry 3.0.0 with status
> `proposed`. `REGISTRY_VERSION` stays `2.0.0-approved-oq-cba-004`,
> `CURRENT_CBA_REGISTRY` stays `CBA_REGISTRY`, and every new run still scores
> under 2.0.0. The approval gate refuses 3.0.0 until its status is `approved`.

## Context

ELI 2.0.0 (B26 T8b, `smartmatch_domain/eli.py`) computes a load band per
professional from confirmed, not-cancelled bookings over a 90-day window and a
declared capacity. The owner decided Q7 = A on 22 September 2026: Light below
0.50 utilization, Moderate from 0.50, Heavy from 0.80, Full above 1.00, with
multipliers Light 1.00, Moderate 0.90, Heavy 0.70 and Unknown 1.00.

A penalty makes a score incomparable with a 2.x score, for the reason ADR-0016
gave for its own major bump. So the penalty ships as a new rulebook, not as an
edit to 2.0.0.

## Decision

1. **Factor.** `engagement_load` is a `PENALTY` factor with weight 0 in the
   weighted sum and in no scoring model's `scoring_keys`. The four CBA weights
   and `normalize_weights` are unchanged, so 3.0.0 and 2.0.0 apply the same
   weights value for value.
2. **Band table and ownership.** The registry holds `RegisteredLoadBands`: T8b's
   `Q7_LOAD_BAND_TABLE` unedited, the ELI formula version it was declared
   against, and a `LoadBandOwnership` record (who decided, when, which
   decision, IA West review state). The edge semantics (`>=` for Moderate and
   Heavy, `>` for Full) stay code in `eli.py`.
3. **Stage A.** A Full pair is removed before the solve and reported in the
   run's `excluded` list as `load_full`, with its load block. It is never
   scored and never explained. No override exists (plan §5.2 item 7).
4. **Stage B.** In `_compose_cba`, the unrounded weighted composite is
   multiplied by the band's multiplier, then rounded once. Light and Unknown
   multiply by 1.0, so they equal the 2.x value bit for bit. An unknown factor
   still makes the composite unknown (ADR-0011); the load is still recorded.
   The composition version for 3.x is `3.0.0-cba-load`.
5. **Unknown load is neutral and labelled.** No stated capacity, or unknown
   hours in the window, gives band Unknown with multiplier 1.0. It is never a
   default capacity and never zero hours (ADR-0011).
6. **`registry_hash`.** Keyed on whether the registry carries a band table,
   never on parsing the version string:

   | Registry | `registry_hash` |
   |---|---|
   | 1.1.1, 2.0.0 (no band table) | `weights_fingerprint(weights)`, byte for byte as before |
   | 3.0.0 (band table) | SHA-256 over `{"weights": …, "load_bands": canonical_load_bands(…)}` |

   The canonical band table holds the cut points, the multipliers and the ELI
   formula version, each `Decimal` normalised so `0.5` and `0.50` hash equal.
   Ownership and review status are **not** hashed: approval must not move a
   hash.
7. **Explanation `load` block.** A 3.x explanation always carries `load`
   (band, reason, hours, capacity, unrounded utilization, multiplier,
   pre-load composite, `as_of`, ELI formula version); a 1.x or 2.x payload
   never does. The reader decides presence from the pinned registry and refuses
   a mismatch rather than repairing it. `unknown_hours_refs` stays in the
   stored payload and never reaches the API wire. Nor do the load numbers:
   the hours, the capacity and the utilization stay in the stored payload
   for audit, and a wire load block carries the band, the reason,
   `measurable`, `as_of` and the ELI formula version (owner ruling R-A,
   2026-09-24).
8. **Current, superseded, proposed.** `CURRENT_CBA_REGISTRY` names the
   registry new runs score under. `SUPERSEDED_REGISTRY_VERSIONS` and
   `proposed_registry_versions()` are derived from it over the CBA lineage
   (1.1.1 → 2.0.0 → 3.0.0). `REGISTRY_VERSION` keeps naming 2.0.0: retargeting
   it would re-label every stored 2.0.0 run.
9. **Pins.** Only the create route reads the current registry. The worker
   scores under the payload's `registry_version` pin and refuses a pin its mode
   does not resolve to. The read route gates on the run's own pin, so flipping
   current never blocks reading a stored run.

## The flip (not done by this ADR)

1. **Approve.** `CBA_REGISTRY_3`: `status="approved"`, `approver`,
   `approved_on`; `ownership.review_status=REVIEWED` once IA West reviews. This
   ADR moves to Accepted.
2. **Make current**, in `factor_registry.py`:

   ```python
   CURRENT_CBA_REGISTRY: Final[FactorRegistry] = CBA_REGISTRY_3  # was: = CBA_REGISTRY
   ```

3. In the same PR, update the tests that assert the current registry and the
   derived sets (`tests/unit/test_factor_registry.py` tests 3 and 4) and the
   create-path rows that assert a new run carries `REGISTRY_VERSION`.

Step 2 without step 1 fails closed: the create route answers
`503 registry_not_ready`.

## Consequences

- A 3.x score and a 2.x score are not comparable and must not be averaged,
  ranked or charted together; the `registry_version` pin separates them.
- A 3.x run costs one more query on create (the engagement read). A 2.x run
  costs none.
- The load read is tenant-wide: load is the person's, not the unit's. Numbers
  stay in the stored payload; screens show a band word only (T8d).

## Rejected

- **Retargeting `REGISTRY_VERSION` to 3.0.0.** Every stored 2.0.0 run would be
  re-labelled.
- **Turning `SUPERSEDED_REGISTRY_VERSION` into a set.** It pins
  `SUPERSEDED_G1_MODEL` and 43 references read it as a string; a derived plural
  set sits beside it instead.
- **A non-zero weight for the penalty.** It would re-normalise the four approved
  weights and move every 2.x-equivalent score.
- **An override of Full.** Not built (plan §5.2 item 7).
