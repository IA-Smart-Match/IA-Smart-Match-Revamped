# ADR-0016 — CBA scoring policy: neutral Topic, proximity bands, and virtual redistribution

**Status:** Accepted
**Date:** Drafted 5 September 2026; accepted 5 September 2026
**Owner of record:** Danny Tran, Development Lead / program owner of record, with the matching-domain reviewer
**Decided:** 5 September 2026 — Danny Tran, Development Lead / program owner of record. All ten proposals approved as drafted, no amendments.
**Decides:** OQ-CBA-001, OQ-CBA-002, OQ-CBA-004 — all three closed by this acceptance
**Contract:** `docs/product/cba-smart-match-customer-requirements.md` §§5, 9, 10, 11, 26; ADR-0011
**Register:** `docs/plans/open-questions/cba-phase-deferred.md`

> **Accepted 5 September 2026 by Danny Tran, Development Lead / program owner of
> record.** All ten proposals below were put to the owner as numbered questions and
> approved as drafted, with no amendments. The values here are now the approved
> policy: engineering may implement them, and `REGISTRY_VERSION` moves to
> `2.0.0-approved-oq-cba-004` as Proposal 9 specifies. OQ-CBA-001, OQ-CBA-002 and
> OQ-CBA-004 are closed.
>
> What acceptance does **not** license: these values are approved because an owner
> chose them, not because they appear in a document. A later card that wants a
> different neutral value, a different band edge, or a different redistribution
> must amend this ADR and re-approve it — it may not adopt a new number because the
> old one proved inconvenient.

## Context

Three customer requirements and one platform rule meet in the same three lines
of code, and they appear to contradict each other.

**The customer's requirements.** §9: a speaker with no useful topic information
must not be scored zero; assign "a neutral/middle score" instead. §10:
proximity is scored in three distance bands — 0–25, 25–75, 75+ miles from the
CPP campus — with the exact sub-scores left unspecified. §11: for a virtual
event, ignore proximity and redistribute its 30% across Industry, Role and
Topic, with the formula left unspecified. §26 lists the last two as *known
unresolved items* and says in terms: "Do not silently invent permanent
behavior for these items."

**The platform rule.** ADR-0011 rule 1: "A value with no evidence is `unknown`
and renders as `unknown`. Never `0`, never `0%`." `scoring.py` implements the
aggregate form: an unknown factor makes the composite unknown, the factor is
never dropped, the remaining weights are never re-spread over the known subset.
`explanation.py` carries the distinction to the screen as a discriminator
(`ScoreState.MEASURED` / `ScoreState.UNKNOWN`) so a renderer cannot read an
absence as a measurement.

**Where they collide.** Read naively, §9 asks for exactly what ADR-0011
forbids: a number invented where there is no evidence. §11 asks for exactly
what `scoring.py` refuses: re-spreading weight when a factor does not
participate. An engineer who resolves this at the keyboard writes `0.5` into
`topic_relevance` and a proportional re-normalization into the virtual path,
and the repository acquires two permanent behaviours nobody approved. That is
the failure OQ-CBA-004 exists to prevent, and it is why this ADR must be
decided before the first Wave 3 registry PR.

**The reconciliation this ADR proposes.** The contradiction is only apparent,
and it dissolves on one distinction the current code does not make: *there are
two different reasons a Topic score can be absent, and only one of them is an
unknown.*

| The situation | What it is | ADR-0011 |
|---|---|---|
| The speaker record was reached, read, and carries **no usable topic evidence** — no topic text, no prior talk, no expertise field | An **observed absence**. The absence is itself the evidence, and the customer has a stated policy about what an observed absence is worth. | Rule 1 is about a value with *no evidence*. Here there is evidence: we looked, and there was nothing. |
| The speaker's topic evidence **could not be evaluated** — the record was not reached, the classification has not run, the comparison errored, the profile row is absent | A genuine **unknown**. | Rule 1 applies in full. `unknown is still not zero`, and it is not a neutral either. |

`neutral is not an unknown`, and it is not a measurement either. It is a third
thing: a *policy value* — a number the customer chose, applied to a situation
the system observed, carrying its own provenance so that no consumer can
mistake it for something the system measured. That is the shape of Proposals 1
and 2. Proposals 3–4 do the same job for proximity, Proposals 5–6 for virtual
events, and Proposals 7–9 make all of it serializable, labelled, and pinned so
a stored run can still be read a year later.

## Decision (accepted 5 September 2026)

Ten proposals, each separately approvable, rejectable, and amendable by the owner
of record. Approving a subset would have been a valid outcome; in the event the
owner approved every one as drafted, with no amendments, so all ten are in force
and OQ-CBA-001, OQ-CBA-002 and OQ-CBA-004 are closed. A later change to any single
proposal amends this ADR and needs its own approval — it does not follow from this
one.

### Proposal 1 — A neutral Topic score is a third evidence state, not an unknown and not a measurement

`smartmatch_domain.factors.FactorScore` gains a discriminator with three
values, and `smartmatch_domain.explanation.ScoreState` gains the matching third
member:

| State | Meaning | Value |
|---|---|---|
| `measured` | The semantic comparison ran against real topic evidence and produced a number. A `0.0` here is a measured zero and is displayed as such. | a float in `[0.0, 1.0]` |
| `policy_neutral` | The speaker record was read and carries **no usable topic evidence**. Customer §9 assigns a stated neutral value to that observed absence. | `CBA_NEUTRAL_TOPIC_VALUE` (Proposal 2) |
| `unknown` | The evidence **could not be evaluated**: the record was not reached, the classifier did not run, or the comparison failed. | `None`, always |

The rule that decides between `policy_neutral` and `unknown` is a property of
the *evidence-gathering step*, not of the score, and it must be decided there:
a speaker profile row that exists and has `topic_text IS NULL AND prior_talk IS
NULL` is `policy_neutral`; no speaker profile row at all, or an evaluation that
raised, is `unknown`. This is the separation OQ-CBA-004's decision-record
requirement 1 asks for, answered in both directions.

Consequence for the composite: `policy_neutral` **participates in scoring**
with its policy value and does not make the composite unknown. `unknown` keeps
today's behaviour exactly — the composite becomes `None`, weights are not
re-spread, ADR-0011 rule 1 is untouched. This ADR therefore *refines* ADR-0011
by naming a case it did not distinguish; it does not amend it, weaken it, or
supersede it. Rule 1 continues to say what it always said: `unknown is still
not zero`.

> **Owner must decide:** whether `policy_neutral` is the right shape at all, or
> whether the customer's §9 "neutral score" should instead be modelled as an
> `unknown` that the *ranking* layer treats separately (the alternative in
> "Alternatives considered", below).

### Proposal 2 — The neutral value is a named, versioned policy constant with its own provenance

Three new domain constants, in `smartmatch_domain` and nowhere else:

| Constant | Proposed value | What it is |
|---|---|---|
| `CBA_NEUTRAL_TOPIC_VALUE` | `0.50` | The score a `policy_neutral` Topic factor contributes. |
| `NEUTRAL_TOPIC_POLICY_ID` | `"cba-neutral-topic"` | The stable identifier of the policy, recorded on every score that used it. |
| `CBA_NEUTRAL_TOPIC_POLICY_VERSION` | `"1.0.0"` | Bumped whenever the value or the `policy_neutral` / `unknown` boundary rule changes, so an older stored run is never re-read under a newer policy. |

`0.50` is proposed, not assumed. It is the midpoint of the `[0.0, 1.0]` factor
scale, which is the plainest reading of §9's "neutral/middle score", and its
one operational property is stated so the owner can test it against intent: a
speaker with no topic evidence ranks **above** a speaker measured below 0.50
and **below** one measured above 0.50, on the Topic factor alone. Whether that
is the intended treatment of a thin record is precisely the owner's call, and
the alternatives are real:

| Option | Value | Effect on a thin record |
|---|---|---|
| 2a (proposed) | `0.50` | Neither rewarded nor penalised relative to a measured average. |
| 2b | `0.40` | Slightly disadvantaged against an average measured speaker, still far above zero. |
| 2c | the observed median measured Topic score for the run | Self-calibrating, but not reproducible across runs and therefore hostile to golden cases and to the run fingerprint. Recorded here as rejected for that reason, not as an option. |

Every score carrying this value also carries `neutral_topic_policy_id` and the
policy version, and its `basis` string reads, verbatim:
`"No usable topic evidence on file; customer §9 neutral policy applied
(cba-neutral-topic 1.0.0)."` A neutral score with no policy identifier attached
is indistinguishable from a measured 0.5, which would be ADR-0011's defect in a
new costume.

> **Owner must decide:** the value (2a or 2b or another), and confirm the
> `basis` wording that a Speaker Connector will read.

### Proposal 3 — The proximity band table, with exact sub-scores and explicit boundary ownership

Distance `d` is the great-circle distance in **miles** from the CPP campus to
the speaker's `location_city` / `location_postal_code` (migration `0024`). The
bands are a **step function**: every distance inside a band scores identically,
with no interpolation within or across bands. §10 specifies bands, and a band
that secretly interpolates is not the thing that was approved.

Boundaries are **lower-inclusive, upper-exclusive** throughout, so every
distance falls in exactly one band and no distance falls in two:

| Band | Interval | Proximity sub-score | `travel_burden` value (the registry's penalty scale, `1 − proximity`) |
|---|---|---:|---:|
| Near | `0 ≤ d < 25` | `1.00` | `0.00` |
| Mid | `25 ≤ d < 75` | `0.60` | `0.40` |
| Far | `75 ≤ d` | `0.20` | `0.80` |

Boundary ownership, stated in words because a table is read too quickly:
**exactly 25** miles is a **Mid** distance, not a Near one; **exactly 75** miles
is a **Far** distance, not a Mid one. Comparison is against the raw computed
float with no prior rounding — rounding `24.9996` to `25.0` before the
comparison would move a candidate between bands by a display convention.

Why the Far band is `0.20` and not `0.00`: a `0.00` proximity is a *measured
zero*, and under ADR-0011 a measured zero is a real claim — "this speaker is
maximally distant". A speaker 80 miles away and one 3,000 miles away are not
the same fact, and neither is maximally distant in any sense the system can
support. Reserving `0.00` keeps it available for a future band that means it,
and keeps an excellent far-away speaker rankable rather than flattened.

> **Owner must decide:** the three sub-scores (`1.00` / `0.60` / `0.20`), and
> both boundary rulings.

### Proposal 4 — An unknown distance is `unknown`, and `is not the far band`

A speaker with no `location_city` and no `location_postal_code` has an
**unknown** distance. Its `travel_burden` factor is `unknown` — `None`, state
`unknown` — and under Proposal 1 that makes the composite unknown, exactly as
today.

Stated as its own proposal because the tempting shortcut is to file a missing
location in the Far band on the grounds that it is "probably far". It is not:
that is a guess rendered as a measurement, it is the precise defect ADR-0011
was written for, and a Speaker Connector who then corrects the address would
see the score move for no visible reason. An unknown distance `is not the far
band`, and there is no distance-based policy-neutral state — unlike Topic,
where §9 states a policy, the customer has stated no policy for a missing
address.

> **Owner must decide:** confirm that a missing address yields an unscorable
> candidate rather than a Far-band one, accepting that such candidates rank
> last (`rank_candidates` already sorts unknowns last without treating them as
> `0.0`).

### Proposal 5 — Virtual events are an approved, pinned **scoring mode**, not a mutated registry

For an event with `is_virtual = true` (migration `0024`), Proximity /
`travel_burden` is excluded from the Stage B factor set for that run. The
exclusion is expressed as a named **scoring mode** — an input to the run,
recorded on the run — rather than as a second registry, a conditional
`PROPOSED_FACTORS`, or a weight override invented at the call site:

| Mode | Applies when | Surviving scoring factors |
|---|---|---|
| `cba-physical-1` | `is_virtual = false` | Industry, Role, Topic, Proximity |
| `cba-virtual-1` | `is_virtual = true` | Industry, Role, Topic |

A mode is a closed vocabulary with its own version, resolved from the event
before scoring and never inferred inside the scorer. The reason it is a mode
and not a conditional registry: `REGISTRY_VERSION` answers "which rulebook",
and two runs of the same rulebook that scored different factor sets must stay
distinguishable without minting a registry version per event shape. One
registry, two modes, both pinned (Proposal 9).

> **Owner must decide:** that virtual-event handling is a scoring mode, and the
> two mode names.

### Proposal 6 — The virtual redistribution formula

Under `cba-virtual-1`, the surviving factors' §5 default weights are
re-normalized over the surviving set — **proportional renormalization**, which
is exactly what `factor_registry.normalize_weights` already does when a factor
is not in the scoring set. No new arithmetic is introduced; the mode chooses
the set and the existing normalizer does the rest.

| Factor | Physical weight (§5) | Virtual weight (proposed) | Exact value |
|---|---:|---:|---:|
| Industry | 0.30 | 0.30 ÷ 0.70 | `0.428571` |
| Role | 0.25 | 0.25 ÷ 0.70 | `0.357143` |
| Topic | 0.15 | 0.15 ÷ 0.70 | `0.214286` |
| Proximity | 0.30 | excluded | — |

Weights are computed, never typed: the values above are what the division
yields, rounded to six decimal places for display and for
`weights_fingerprint` rendering only. They match §11's "approximately 42.86 /
35.71 / 21.43" because that is the same division, and §11 explicitly declines
to approve it — which is why this is Proposal 6 and not a default.

The alternative the owner may prefer is a **fixed table** the customer chooses
outright, for example Industry `0.40` / Role `0.35` / Topic `0.25`. It is a
legitimate answer: it is round, explainable to a Speaker Connector, and it lets
the customer say "Topic matters more when there is no room to matter about
travel" rather than inheriting a ratio from a formula. Its cost is a second set
of weights to govern and to keep summing to one.

| Option | Industry | Role | Topic |
|---|---:|---:|---:|
| 6a (proposed) proportional renormalization | `0.428571` | `0.357143` | `0.214286` |
| 6b fixed table | `0.40` | `0.35` | `0.25` |

> **Owner must decide:** 6a or 6b, or a different fixed table. Note that this
> is *not* the same question as re-spreading weight around an **unknown**
> factor, which `scoring.py` refuses and which stays refused: here the factor
> is *absent from the model by an approved rule*, known before any candidate is
> read, not missing evidence discovered per candidate.

### Proposal 7 — Serialization

The three states, the policy provenance, and the mode must survive the round
trip through `job.payload` that `explanation_to_payload` /
`explanation_from_payload` already guards. Proposed serialization:

* `ScoreState` serializes as `"measured"`, `"policy_neutral"`, or `"unknown"`.
  A reader that does not recognise a state **refuses the payload** — the
  existing behaviour — rather than coercing it to the nearest known one.
* A factor entry gains `policy_id` and `policy_version`, both `null` unless the
  state is `policy_neutral`, and both required when it is.
* The invariant `explanation.FactorExplanation.__post_init__` enforces widens
  from two states to three: `unknown` ⇔ `value is None`; `measured` and
  `policy_neutral` ⇔ `value is not None`; `policy_neutral` ⇔ `policy_id is not
  None`. A payload where these disagree is refused, not repaired.
* `CandidateExplanation` gains `policy_neutral_factor_keys` beside the existing
  `unknown_factor_keys`, in registry order, so "which factors were policy
  values rather than measurements" is answerable without scanning — the same
  reason `unknown_factor_keys` exists.
* The composite's own state is `unknown` when `unknown_factor_keys` is
  non-empty; otherwise `policy_neutral` when `policy_neutral_factor_keys` is
  non-empty; otherwise `measured`. Unknown dominates: a run with both an
  unknown factor and a policy-neutral one is unknown.
* The payload gains `scoring_mode` and `scoring_mode_version`, and a stored
  payload lacking them is read as a pre-ADR-0016 run rather than as
  `cba-physical-1`.

> **Owner must decide:** nothing product-facing here beyond confirming that a
> stored score must state which of its factors were policy values. The field
> names are the matching-domain reviewer's call.

### Proposal 8 — UI labels

The §6 rule stands unchanged: rank internally, no prominent overall percentage,
and the only provenance wording a score may travel under remains the existing
`heuristic score` constant. Nothing below multiplies a value by 100.

| Situation | Proposed UI label | Never |
|---|---|---|
| Topic, `policy_neutral` | **"Neutral — no topic information on file"**, with the §9 policy named on hover or in the detail row | "0", "0%", a blank cell, or a bar drawn from the origin |
| Topic, `measured` `0.0` | **"0 — measured"**, with its basis | an unqualified "0%" |
| Any factor, `unknown` | **"Unknown"** | any numeral |
| Proximity, band scored | the band name — **"Near"**, **"Mid"**, **"Far"** — beside the sub-score | a spurious precise mileage the band did not use |
| Proximity, unknown distance | **"Unknown — no location on file"** | "Far" |
| Composite, `policy_neutral` | the score plus the caption **"Includes a neutral default for missing topic information."** | the score alone |
| A virtual-event run | **"Virtual event — proximity not scored"** | a proximity row showing 0, or a silently absent row |

Every one of these is a UI label decision, not a rendering detail: each names
the exact wording a Speaker Connector reads, because "0%" on an AI event is the
literal symptom (Fix #8) that produced ADR-0011.

> **Owner must decide:** the seven strings, especially the Topic neutral label,
> which is the one a Speaker Connector will see most.

### Proposal 9 — `REGISTRY_VERSION` pin policy, and what a match run records

**Pin policy.** `REGISTRY_VERSION` is bumped in the same commit as any change
to: the declared factor set, any factor's weight, the neutral policy value or
its state boundary, or the proximity band table. Adopting Proposals 1–8 is such
a change and takes the registry from `1.1.1-approved-g1-m6j` to
`2.0.0-approved-oq-cba-004` — a **major** bump, because the CBA four-factor set
(Industry 30 / Role 25 / Topic 15 / Proximity 30) replaces the G1-approved
two-factor set (`topic_relevance` 0.70 / `travel_burden` 0.30) rather than
extending it, and a score is not comparable across that change. The version
string names the gate that approved it, as `1.1.1-approved-g1-m6j` names G1.

A scoring **mode** is never a registry version and a registry version is never
a mode: they are two independent pins, and conflating them would make
`cba-virtual-1` look like a different rulebook.

**What a run records.** `MatchRunPins` gains `scoring_mode` and
`scoring_mode_version`, alongside the existing `registry_version` and
`registry_hash`. `registry_hash` continues to be `weights_fingerprint` over
**the weights actually applied** — so a virtual run fingerprints the three
surviving weights, and a physical run the four. Two runs of the same registry
in different modes therefore carry the same `registry_version` and different
`registry_hash` values, which is the intended reading: same rulebook, different
model.

Runs already stored against `1.1.1-approved-g1-m6j` stay readable and stay
pinned to it. They are not re-scored, not re-labelled, and not compared against
`2.0.0-approved-oq-cba-004` runs in any aggregate, for the reason the registry
module already gives about the M6j bump: a consumer must never conflate two
rulebooks.

> **Owner must decide:** that this is a major bump; that stored 1.x runs are
> retained-but-not-comparable rather than re-scored; and the version string.

## Golden cases implied by these proposals

These are the cases the Wave 3 golden set must contain **once the owner
approves**. They are listed here so the owner can see what each decision
commits the system to, and so no golden case is written before the decision it
asserts. This ADR authorizes none of them to be implemented.

| ID | Case | Asserts |
|---|---|---|
| G-CBA-01 | Speaker profile exists, `topic_text` and `prior_talk` both null | Topic state `policy_neutral`, value `CBA_NEUTRAL_TOPIC_VALUE`, `policy_id` present, composite not unknown (Proposals 1, 2) |
| G-CBA-02 | No speaker profile row for the candidate | Topic state `unknown`, value `None`, composite `unknown`, weights not re-spread (Proposals 1, 4) |
| G-CBA-03 | Topic comparison runs and genuinely scores `0.0` | State `measured`, `zero_classification = "measured_zero"`, label "0 — measured", never "unknown" (Proposals 1, 8) |
| G-CBA-04 | `d = 24.9` miles | Near band, proximity `1.00`, burden `0.00` (Proposal 3) |
| G-CBA-05 | `d = 25.0` miles exactly | **Mid** band, proximity `0.60` — the boundary ruling (Proposal 3) |
| G-CBA-06 | `d = 74.9` and `d = 75.0` miles | Mid then **Far**; proximity `0.60` then `0.20` (Proposal 3) |
| G-CBA-07 | Speaker with no city and no postal code | Travel state `unknown`, composite unknown, candidate sorts last, never Far band (Proposal 4) |
| G-CBA-08 | `is_virtual = true` | Mode `cba-virtual-1`; no proximity factor in `factor_scores`; weights `0.428571` / `0.357143` / `0.214286` summing to 1.0 (Proposals 5, 6) |
| G-CBA-09 | Same candidate pool scored physical and virtual | Same `registry_version`, different `registry_hash`, different `scoring_mode` (Proposals 5, 9) |
| G-CBA-10 | Explanation with one `policy_neutral` factor round-tripped through `explanation_to_payload` / `explanation_from_payload` | State, value, `policy_id`, `policy_version`, and `policy_neutral_factor_keys` all survive; a payload with `policy_neutral` and a null `policy_id` is refused (Proposal 7) |
| G-CBA-11 | Candidate A: measured Topic `0.45`. Candidate B: `policy_neutral` Topic | B outranks A on the Topic factor — the ranking consequence of the neutral value, asserted rather than discovered (Proposal 2) |
| G-CBA-12 | A run stored under `1.1.1-approved-g1-m6j` read after the 2.x bump | Reads back at its own pin, is not re-scored, and is excluded from any aggregate spanning both registries (Proposal 9) |

## Consequences

- **OQ-CBA-001** (virtual redistribution) closes on Proposal 6, **OQ-CBA-002**
  (band values and boundaries) on Proposals 3 and 4, and **OQ-CBA-004**
  (the ADR-0011 relationship) on Proposals 1, 2, 7 and 9. Until then all three
  stay open and the register's safe planning defaults stay in force.
- `factor_registry.py`, `scoring.py`, `explanation.py` and `match_run.py` are
  **unchanged by this ADR**. Approval unblocks the Wave 3 registry PR that
  changes them; this document changes nothing.
- ADR-0011 is neither amended nor superseded. Rule 1 is unchanged; this ADR
  adds a state that rule 1 never covered, and reaffirms that an unevaluable
  factor remains an unknown.
- The golden cases above become required for the Wave 3 gate, in the same way
  MM-002's three symptoms became required for G1.
- `ALLOW_LIVE_PROVIDERS=false`, `ALLOW_LIVE_DATA=false` and
  `ALLOW_CLOUD_DEPLOY=false` are untouched. This is a documentation and test
  change with no runtime effect.

## Alternatives considered

**Model §9's neutral as an `unknown`, and handle it in ranking.** Keep
`topic_relevance` unknown for an evidence-free speaker, let the composite go
unknown, and have the ranking layer place unknown-Topic candidates in the
middle of the list rather than last. Attractive because it changes no types.
Rejected in this draft — but genuinely open for the owner — because it moves a
customer *policy* into a sorting heuristic, where it is invisible to the
explanation payload, absent from the run fingerprint, and impossible for a
Speaker Connector to see or a golden case to pin. It also cannot answer "why is
this speaker third" with anything a person can read.

**Write `0.5` into the Topic factor with a comment.** Rejected: a bare literal
with no policy identifier is indistinguishable in storage from a measured 0.5,
so the day someone asks "was that measured?" the answer is unrecoverable. The
policy id and version in Proposal 2 exist for exactly that question.

**A second registry for virtual events.** Rejected: two registries means two
versions to keep in step and an ambiguous answer to "which rulebook produced
this score". A mode is one rulebook, two models, both pinned.

**Re-spread weight around an unknown factor, mirroring the virtual rule.**
Rejected outright and not offered as an option. Proposal 6 re-normalizes over a
factor set that is *known before any candidate is read*; re-spreading around a
per-candidate unknown would let an evidence-free candidate outrank an evidenced
one, which is the aggregate form of the ADR-0011 defect and what `scoring.py`'s
unknown-propagation rule exists to prevent.

**Interpolate proximity continuously instead of banding.** Rejected: §10
specifies bands. A continuous curve would be a different decision, better than
this one in some respects, and not the one the customer made.
