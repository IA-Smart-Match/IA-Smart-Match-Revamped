# Factor registry supersession record — 1.1.1-approved-g1-m6j → 2.0.0-approved-oq-cba-004

**Status:** Active
**Date:** 5 September 2026
**Approver of record:** Danny Tran, Development Lead / program owner of record
**Decision:** [`ADR-0016 — CBA scoring policy`](decisions/ADR-0016-cba-scoring-policy.md) (Accepted)
**Implemented by:** `CBA-MATCH-REGISTRY` (Wave 3)
**Code of record:** `python/smartmatch_domain/smartmatch_domain/factor_registry.py`
**Register:** [`docs/plans/open-questions/cba-phase-deferred.md`](../plans/open-questions/cba-phase-deferred.md)

ADR-0016 is the *decision*, and says of itself that it "changes nothing". This
document is the *record of the change* — what moved, what was kept, and what a
person reading a stored match run a year from now must not do with it.

## The bump

`REGISTRY_VERSION` moved from `1.1.1-approved-g1-m6j` to
`2.0.0-approved-oq-cba-004`. **Major**, because the CBA four-factor set
*replaces* the G1 two-factor set rather than extending it.

| | Superseded (`1.1.1-approved-g1-m6j`) | Current (`2.0.0-approved-oq-cba-004`) |
|---|---|---|
| Approved by | Gate G1, 3 September 2026 | ADR-0016, 5 September 2026 |
| Scoring factors | `topic_relevance` 0.70, `travel_burden` 0.30 | `industry_match` 0.30, `role_match` 0.25, `cba_semantic_topic` 0.15, `proximity` 0.30 |
| Evidence states | `measured`, `unknown` | `measured`, `policy_neutral`, `unknown` |
| Scoring modes | none | `cba-physical-1`, `cba-virtual-1` |
| Composition version | `STAGE_B_FORMULA_VERSION` `1.0.0` | `CBA_STAGE_B_FORMULA_VERSION` `2.0.0-cba` |
| Entry point | `scoring.score_candidate` | `scoring.score_cba_candidate` |
| Model constant | `SUPERSEDED_G1_MODEL` | `CBA_PHYSICAL_MODEL`, `CBA_VIRTUAL_MODEL` |

## The rule a consumer must obey

**A 1.x score and a 2.x score are not comparable.** They must never be averaged,
ranked against each other, charted together, or folded into one aggregate. They
do not measure the same thing: `topic_relevance` is lexical tag overlap and
`cba_semantic_topic` is a description-to-profile comparison; `travel_burden` is a
continuous kilometre penalty and `proximity` is a three-band step function on
miles. A number from each is a number about a different question.

The registry version string is the **only** thing keeping them apart, which is
why every stored score carries it and why nothing defaults it.

## What was kept, and why

`topic_relevance` and `travel_burden` are **retired, not deleted** — the owner's
OQ-CBA-025 decision is *coexist*. Both remain declared in `PROPOSED_FACTORS`,
remain `implemented=True`, and keep the weights they were approved with. What
they lose is *active* weight: `FactorSpec.retired_in_version` takes them out of
the current model's numerator **and denominator together**.

Together is the load-bearing word. Removing a factor from the sum while leaving
it in the normalization denominator is the legacy Nebiux defect exactly — nine
declared weights, seven computed, every score silently capped at 0.90 — and
doing it in the other direction is the same defect wearing new clothes.
`tests/unit/test_factor_registry.py` asserts a retired factor contributes
`active_weight == 0.0`, and that an override naming one cannot inject weight
mass back into the current model.

The practical consequence: a run stored under `1.1.1-approved-g1-m6j` is still
**reproducible**, not merely readable.
`tests/unit/test_matching_approved_golden.py` re-scores three of the G1 golden
cases after the bump and asserts they still produce their approved numbers, over
exactly the two-factor set, with weights still summing to one. Had retirement
meant deletion, every run a coordinator has already seen would have become
unreproducible on the day the CBA factors landed.

## Two pins, not one

`registry_version` answers **which rulebook**. `scoring_mode` answers **which of
its models**. They are independent, and conflating them would make
`cba-virtual-1` look like a different rulebook and mint a registry version per
event shape.

| Mode | Applies when | Factors | Weights |
|---|---|---|---|
| `cba-physical-1` | physical event | Industry, Role, Topic, Proximity | 0.30 / 0.25 / 0.15 / 0.30 |
| `cba-virtual-1` | virtual event (§11) | Industry, Role, Topic | 0.428571 / 0.357143 / 0.214286 |
| *(none)* | pre-ADR-0016 run | `topic_relevance`, `travel_burden` | 0.70 / 0.30 |

Two runs of one registry in different modes carry the **same**
`registry_version` and **different** `registry_hash` values — `registry_hash` is
`weights_fingerprint` over the weights actually applied, so a virtual run
fingerprints three and a physical run four. Same rulebook, different model.
Golden case `G-CBA-09` pins this.

The virtual weights are **computed, never typed**: `CBA_VIRTUAL_MODEL` names
three factors instead of four and the existing proportional normalizer does the
rest, so `0.30/0.70`, `0.25/0.70` and `0.15/0.70` fall out of the same arithmetic
that produces the physical weights. The six-place values above appear as literals
in exactly one place in the repository — the assertion in
`tests/unit/test_factor_registry.py` that checks them against `display_weights` —
and a test greps the whole domain package to prove no runtime module types them.

**An absent mode is not `cba-physical-1`.** A stored payload with no
`scoring_mode` is a pre-ADR-0016 run and reads as one;
`resolve_scoring_model(None)` returns `SUPERSEDED_G1_MODEL`. Reading it as
physical would claim a proximity factor was scored under a rulebook that had no
modes at all.

## The third evidence state

ADR-0016 Proposal 1 adds `policy_neutral` beside `measured` and `unknown`. It
**refines** ADR-0011 rather than amending it: rule 1 still says an unevaluable
value is `unknown` and never `0`. What the third state names is a case rule 1
never covered — a record that *was read* and carries no usable evidence, which
customer §9 has a stated policy about.

* Only `unknown` makes a composite unscorable. A `policy_neutral` factor
  participates with its policy value.
* **Unknown dominates.** A candidate with both an unknown factor and a
  policy-neutral one is unknown.
* Weights are **never re-spread per candidate**, in any state. The virtual
  redistribution is a different thing: that factor set is chosen before any
  candidate is read.
* A `policy_neutral` score without its `policy_id` and `policy_version` is
  refused — at construction, and again on the way back out of storage. An
  unlabelled `0.5` is indistinguishable from a measured `0.5`, and the day
  somebody asks "was that measured?" the answer would be unrecoverable.

## What is *not* superseded

* **ADR-0011** is neither amended nor superseded. Rule 1 is unchanged.
* **The §6 presentation rules** are unchanged: rank internally, no prominent
  overall percentage, a 2–3 candidate shortlist, and `"heuristic score"` remains
  the only provenance label a score may travel under.
* **The proximity band formula** is untouched by the OQ-CBA-023 campus-origin
  ratification. The origin carries its own version precisely so the point can
  move without that being a change to the bands.
* **The HTTP match-run surface** has not migrated. It still scores with the
  superseded composition and still produces `1.1.1-approved-g1-m6j` runs — see
  OQ-CBA-029. That is deliberate and recorded rather than papered over: the
  route writes `scoring_mode: null`, so a stored run's weights are always the
  ones that touched its numbers.

## Open questions this record leaves

| ID | What is unresolved |
|---|---|
| OQ-CBA-024 | How a city/ZIP becomes a coordinate. Owner steer is a static offline ZIP-centroid table; not built, because the goldens supply distances directly. Blocks OQ-CBA-029. |
| OQ-CBA-025 | *Deletion* of the retired factors. Coexist is implemented; retirement still waits on no pinned run referencing them. |
| OQ-CBA-028 | `scoring_mode` as a `match_run` column. Recoverable from the payload today, but not queryable. Needs DDL. |
| OQ-CBA-029 | Migrating the HTTP surface to CBA evidence. A request-schema change, dependent on OQ-CBA-024. |

## Where the guarantees are asserted

| Guarantee | Asserted in |
|---|---|
| The four weights, and the exact virtual redistribution | `tests/unit/test_factor_registry.py` |
| No weight literal outside the registry | `tests/unit/test_factor_registry.py` (greps the domain package) |
| Retired factors carry zero active weight | `tests/unit/test_factor_registry.py`, `tests/unit/test_travel_burden.py` |
| 1.x runs still reproduce at their own pin | `tests/unit/test_matching_approved_golden.py` |
| The twelve approved CBA behaviours | `tests/unit/test_cba_matching_golden.py`, `tests/golden/matching/cba/` |
| Policy provenance survives storage | `tests/unit/test_cba_matching_golden.py` (G-CBA-10) |
| The mode pin, and refusal of an unknown mode | `tests/unit/test_match_run_pins.py` |
