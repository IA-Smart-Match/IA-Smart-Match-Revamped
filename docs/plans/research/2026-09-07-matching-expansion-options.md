# Expanding the matching engine after the pilot — options, blockers, and one decision the owner may not know he already made

**Status:** research report. Nothing here is adopted, and nothing here closes an
open question. Every recommendation is a proposal for the program owner.

**Date:** 2026-09-07
**Scope:** the CBA four-factor engine at registry `2.0.0-approved-oq-cba-004`.

This report answers four questions the owner asked, in the order he asked them:
what the engine we have actually does and where it is weak; how it compares to
the backend of an open-source game recommender he wants us to look at; what
specifically stops us building a hybrid-RAG-style recommender here; and whether
we should put a prominent "Job Fit Score 89%" card in front of a Connector.

The short version, so the rest reads as evidence rather than suspense. The
engine's central weakness is **resolution, not retrieval** — a physical
candidate today can take exactly **twelve** distinct composite values, and only
twelve, because three of the four factors are step functions and the fourth
cannot produce a number at all outside a recorded fixture. What blocks a learned
or tuned recommender is not the model, the vector store, or the budget: it is
that **no relevance signal exists anywhere in this system**, by four separate
ratified decisions plus one schema gap. And the score card in Part 4 is already
decided against in the register, for reasons that get *stronger*, not weaker,
once Part 1's arithmetic is on the table.

---

## Part 1 — The current engine

### 1.1 What it is

Four weighted factors, composed once, pinned to a version. The set and the
weights are declared in one place and nowhere else — `PROPOSED_FACTORS` at
`python/smartmatch_domain/smartmatch_domain/factor_registry.py:280-377`:

| Factor | Key | Weight | Kind | Spec |
|---|---|---|---|---|
| Industry Match | `industry_match` | 0.30 | suitability | `factor_registry.py:281-292` |
| Role Match | `role_match` | 0.25 | suitability | `factor_registry.py:293-303` |
| Topic Fit | `cba_semantic_topic` | 0.15 | suitability | `factor_registry.py:304-318` |
| Proximity | `proximity` | 0.30 | suitability | `factor_registry.py:319-332` |

Two more factors — `topic_relevance` (0.70) and `travel_burden` (0.30) — remain
declared and implemented but carry `retired_in_version=REGISTRY_VERSION`
(`factor_registry.py:346`, `:361`), which takes them out of the numerator and the
denominator together (`FactorSpec.active_weight`, `factor_registry.py:258-269`).
They exist so a run stored under `1.1.1-approved-g1-m6j` stays reproducible;
OQ-CBA-025 decided *coexist*, not delete.

Composition is `_compose_cba` at `scoring.py:544-627`. It normalizes the model's
weights (`:553`), computes every factor the model admits (`_cba_factor_scores`,
`:503-541`), and sums `weight × value` for suitability factors — the penalty
branch at `:612` is kept for the rule, not for today's set, since all four
current factors are SUITABILITY. The result is rounded to six places (`:614`).

Ranking is `_ranked` at `scoring.py:377-390`, a single sort key:
`(value is None, -value, subject_id)`. Known scores first, then descending
value, then ascending subject id. `rank_cba_candidates` (`:630-671`) is that sort
over a scored pool.

### 1.2 How each factor scores

**Industry Match** (`factors/industry_match.py:199-270`) is a set-membership
test. The speaker has *one* primary NAICS sector (§7); the request may name
several. The score is `1.0` if the speaker's sector code is in the requested set
(`:260`, `:265`) and a measured `0.0` if it was read and is not. Four separate
branches return `None` instead: no sector on file (`:222-229`), quarantined
sector (`:231-239`), request names no sectors (`:241-246`), request names sectors
but none resolved (`:249-258`). The module is explicit about why it is binary —
"inventing a graded score where the data supports only a yes/no would be a
precision the evidence does not carry" (`:7-9`). That reasoning is sound *for the
factor*. Section 1.3 is about what happens when four such factors are composed.

**Role Match** (`factors/role_match.py:206-277`) is structurally identical: one
primary CBA role category tested for membership in the request's set, `1.0` /
measured `0.0` / four unknown branches. Its one distinctive guard is that it
refuses the ADR-0012 event-function vocabulary (`panelist`, `judge`, `keynote`,
`mentor`) by type — those quarantine and score unknown (`role_match.py:9-23`).

**Proximity** (`factors/proximity.py:624-697`) is a three-band step function on
straight-line miles from a fixed CPP campus origin. Bands are lower-inclusive,
upper-exclusive: `< 25` Near, `< 75` Mid, else Far (`band_for_miles`,
`:518-544`), scoring `1.00` / `0.60` / `0.20` (`:194`, `:197`, `:203`). It does
not interpolate and does not round before banding (`:13-19`). `0.20` rather than
`0.00` for Far is deliberate — "a speaker 80 miles away is not the same fact as
one 3,000 miles away" (`:199-203`). Under `cba-virtual-1` the factor is not
scored at all: `score_proximity` raises rather than returning a number
(`:643-649`), and `_cba_factor_scores` branches around it
(`scoring.py:530-539`).

**Topic Fit** (`factors/cba_semantic_topic.py:410-494`) is the only continuous
factor, and it carries a subtlety worth the whole module. It has three states,
not two:

- `measured` — a provider comparison ran and returned a number, rounded to
  `TOPIC_SCORE_PRECISION = 4` (`:130`, `:486`). A measured `0.0` is a real claim.
- `policy_neutral` — the speaker profile row **was read** and holds no usable
  topic text. That is an *observed absence*, and customer §9 states a policy for
  it: score `CBA_NEUTRAL_TOPIC_VALUE = 0.50` (`:97`), tagged with
  `NEUTRAL_TOPIC_POLICY_ID` and a policy version so it can never be mistaken for
  a measured 0.5 (`:442-451`).
- `unknown` — no profile row was reached (`:436-440`), the request carries no
  description (`:453-460`), or the provider raised (`:469-481`). Value `None`.

The decision order matters and is deliberate: the two states needing no
comparison are settled *before* the provider is consulted, so a thin record never
reaches an adapter at all (`:417-421`).

### 1.3 The discreteness problem — the central weakness, quantified

`industry_match` and `role_match` are binary. Between them they carry **0.55** of
the weight. `proximity` is a three-valued step function carrying **0.30**. Only
`cba_semantic_topic`, at **0.15**, is continuous.

So the composite has a *backbone* of `0.30·I + 0.25·R + 0.30·P` over
`I,R ∈ {0,1}` and `P ∈ {1.0, 0.6, 0.2}` — 2 × 2 × 3 = **12 backbone values**, all
distinct, computed against the shipped `normalize_weights`:

```
0.06, 0.18, 0.30, 0.31, 0.36, 0.43, 0.48, 0.55, 0.60, 0.61, 0.73, 0.85
```

Adjacent gaps run `0.12, 0.12, 0.01, 0.05, 0.07, 0.05, 0.07, 0.05, 0.01, 0.12,
0.12`. **The minimum gap is 0.01 and the topic term's full swing is 0.15.** So
Topic is not merely a tiebreaker — it can move a candidate across several
backbone tiers. That is worth saying because the naive criticism ("the small
continuous factor only breaks ties") is *not* the right criticism here. The right
criticism is sharper, and it comes from the provider.

**How many distinct values can a physical candidate actually take?** Three
answers, and the gap between them is the finding.

*Theoretical ceiling.* If Topic could emit anything on its 4-decimal grid:
12 × 10,001 = **120,012**. Under `cba-virtual-1`, whose backbone is 4 values
(`0`, `0.357143`, `0.428571`, `0.785714`) and whose topic swing is `0.214286`:
4 × 10,001 = **40,004**.

*What ships today.* The only implementation behind the provider seam is
`FixtureSemanticTopicProvider`
(`python/smartmatch_providers/smartmatch_providers/topic_semantics.py:124-201`).
It **computes nothing**. It replays comparisons a caller recorded (`:183-200`)
and *raises* `TopicComparisonUnavailable` for any pair it was not given
(`:194-200`) — deliberately, because "a provider that answered '0.5, probably'
would be storing an assumption as a fact" (`:40-43`).
`build_semantic_topic_provider` refuses a live client under **every** edition,
not only the classroom one (`topic_semantics.py:7-22`).

The consequence is the single most important operational fact in this report, and
it is easy to miss: **for any real speaker who has topic text on file, the
provider raises, the factor returns `unknown`, and the composite is `None`**
(`cba_semantic_topic.py:469-481` → `scoring.py:592-598`). A candidate can only
receive a *number* today if their Topic factor is `policy_neutral` — that is, if
their profile was read and they have **no** topic evidence at all.

*So the real count, on the deployed engine, is:*

| Model | Distinct composite values reachable outside a recorded fixture |
|---|---|
| `cba-physical-1` | **12** |
| `cba-virtual-1` | **4** |

Physical: `0.135, 0.255, 0.375, 0.385, 0.435, 0.505, 0.555, 0.625, 0.675, 0.685,
0.805, 0.925`. Virtual: `0.107143, 0.464286, 0.535714, 0.892857`.

(Verified by evaluating the shipped `normalize_weights` over the enumerated
factor ranges. The physical figures reproduce the golden cases — G-CBA-11's
neutral candidate scores `0.925`, the top of that twelve-value list.)

Twelve. That is the resolution of the engine as deployed. Two speakers in the
same sector, the same role, and the same mile band are, to this engine,
**indistinguishable** — not close, identical. In a pool of tens drawn from one
CBA roster, where sector and role are the *reason* the coordinator assembled the
pool, that collision is the normal case rather than the edge case. Hold this
number; Part 4 turns on it.

### 1.4 Unknown propagation (ADR-0011)

`_compose_cba` at `scoring.py:591-598`: if any factor is unknown, the composite is
`None`. Not dropped, not substituted with `0.0`, and the remaining weights are
**not** re-spread over the known subset. This implements ADR-0011 rule 1 — "A
value with no evidence is `unknown` and renders as `unknown`. Never `0`, never
`0%`, never `—` styled to look like a measurement"
(`docs/architecture/decisions/ADR-0011-accountable-numbers.md:51-55`).

**Pros.** It is honest, and honest at the type level rather than by convention —
`explanation.py` carries a `ScoreState` discriminator *beside* the value
(`explanation.py:11-18`, `:133-166`) precisely because `value is None` is easy to
lose to a `?? 0` in a TypeScript client. `explanation_from_payload` refuses a
stored row where state and score disagree (`explanation.py:48-52`), so a
truncated or hand-edited row cannot resurrect the collapse. Golden case G-CBA-07
pins the behaviour: a speaker with no location gets `composite_state: "unknown"`,
`heuristic_score: null`, `is_shortlistable: false`, and sorts last — *never* filed
into the Far band.

**Cons, stated as sharply.** It is brittle in exactly the regime we are in. One
missing postal code destroys a candidate's entire *scorability*, not merely their
proximity — and `is_shortlistable: false` removes them from the shortlist
altogether. With four factors and any single one unknown, the other three's
evidence is discarded. In a small pool with patchy profile data, unknown
propagation can empty a shortlist faster than any scoring disagreement. Note also
that today, because the fixture raises on unrecorded pairs, *having topic text is
what makes a speaker unscorable* — a perverse incentive the provider seam creates
and that the domain code is not at fault for.

There is a defensible alternative the ADRs did not take: score the known subset
and report coverage ("scored on 3 of 4 factors"). It was not taken because
re-spreading weight around a per-candidate absence is precisely what ADR-0016
Proposal 6 refuses, and because a coverage-weighted score is comparable across
candidates only by accident. That reasoning holds. But the cost is real and should
be named rather than treated as free.

### 1.5 `policy_neutral` at 0.50 in the composite

A `policy_neutral` Topic factor **participates** in the composite with its policy
value (`scoring.py:456-461`, `:587-589`). The composite state becomes
`POLICY_NEUTRAL` and the surface must show `COMPOSITE_NEUTRAL_CAPTION` —
"Includes a neutral default for missing topic information." (`explanation.py:117`,
`:401-406`) — shown *with* the composite, never instead of it.

The operational property is stated in the constant's own docstring
(`cba_semantic_topic.py:92-97`) and pinned by golden case G-CBA-11: a speaker with
**no** topic evidence scores `0.925` and **outranks** a speaker whose topic fit was
measured at `0.45` and who scores `0.9175`. That is the intended behaviour of the
§9 policy, correctly implemented — and it is also, plainly, a system in which
having less evidence on file can rank you higher. The caption exists to make that
legible. It is a defensible reading of §9; it is not a *neutral* one, and it will
deserve re-examination the first time a Connector asks why the speaker with a
documented prior talk lost to the speaker with a blank profile.

Note the arithmetic: `0.925 − 0.9175 = 0.0075`. Part 4 returns to it.

### 1.6 The readiness guard, and why a factor change is a major bump

`assert_scoring_ready` (`factor_registry.py:585-620`) fails closed unless the
implemented scoring set **equals** `APPROVED_SCORING_KEYS` exactly — neither a
missing implementation nor an extra one passes (`:604-611`) — and unless both
current models' normalized weights sum to 1.0 within `1e-9` (`:613-620`). Both
models are checked, because a deflated virtual model would reproduce the legacy
defect on a path a physical-only check never touches. `_compose_cba` carries the
same guard again at composition time (`scoring.py:576-584`), comparing the
computed factor keys against the weighted keys.

This is the correct fix for a real historical defect: the legacy engine declared
nine factors, computed seven, normalized over nine, and therefore capped every
score at 0.90 (`factor_registry.py:13-26`). The guard makes that unrepeatable.

**What it costs any expansion.** Adding a factor is not an increment. ADR-0016
Proposal 9 (`docs/architecture/decisions/ADR-0016-cba-scoring-policy.md:319-350`)
requires `REGISTRY_VERSION` to bump on any change to the declared factor set, any
factor's weight, the neutral policy value or its state boundary, or the proximity
band table — and a factor-set change is a **major** bump because the new set
*replaces* rather than extends the old one: "a score is not comparable across that
change." Runs stored under the old pin "are not re-scored, not re-labelled, and
not compared against `2.0.0-approved-oq-cba-004` runs in any aggregate."

So any embedding factor, any BM25 factor, any ELI penalty is a `3.0.0` and a hard
discontinuity in every stored score. That is not an argument against doing it. It
is an argument for doing it **once**, deliberately, with the owner's signature —
and for preferring changes that fit *inside* an existing factor over changes that
add one. Part 3 leans on this.

### 1.7 Edge cases

**Ties.** `_ranked` (`scoring.py:377-390`) breaks ties by ascending `subject_id` —
lexicographic, on a UUID. With only twelve reachable composite values (§1.3), ties
are not rare; they are the expected outcome for any two candidates sharing sector,
role, and band. The final tie-break is therefore effectively arbitrary with
respect to fit. G-CBA-11 was deliberately constructed so lexicographic order would
put the *wrong* candidate first, forcing value ordering to do the work — which
tells you the authors knew the id tie-break is not a fit signal.

**Unknown sorting.** Unknowns sort last via `result.value is None` as the first
sort-key element; `-(result.value or 0.0)` is reached only for known scores, so an
unknown is never treated as `0.0`.

**Virtual renormalization.** `CBA_VIRTUAL_MODEL` (`factor_registry.py:478-484`)
names three factors; `normalize_weights` re-normalizes over that set and nothing
else (`:640-694`). The weights `0.428571 / 0.357143 / 0.214286` are **computed,
never typed** (`:67-76`; `display_weights` at `:704-722`). The distinction from
per-candidate re-spreading is that the exclusion is known before any candidate is
read. Consequence for us: the virtual model has a **four**-value backbone, so
virtual runs discriminate *less* than physical ones, not more.

**Unresolvable ZIPs.** `services/api/smartmatch_api/zip_proximity.py` resolves a
postal code against a static offline ZCTA centroid table (OQ-CBA-024: US Census
2023 Gazetteer, California only; `normalize_zcta` at `:124`,
`resolve_distance_from_campus` at `:166`). An absent or invalid ZIP resolves to
nothing, `distance_miles` is `None`, and `score_proximity` returns unknown with
the explicit basis that "no address-lookup provider is called here (OQ-CBA-024),
and an unresolved address is not the Far band" (`proximity.py:658-664`). Correct,
and expensive: an out-of-state or malformed ZIP makes the whole candidate
unscorable.

**Quarantined classifications.** A quarantined sector or role is unknown, not zero
(`industry_match.py:231-239`, `role_match.py:238-246`) — "a later taxonomy version
may well classify `"Tech"` into `Information`". Separately, an unreviewed or
wrongly-provenanced classification never reaches a factor at all: the pool
assembler calls `match_ineligibility_reason` *before* assembling evidence and
excludes the candidate (`match_run_evidence.py:398-411`), so a proposal cannot
leak into a ranking.

**`MIN_RESPONSES_FOR_AGGREGATE`.** `= 3`
(`student_speaker_feedback.py:92`). Below it, `aggregate_speaker_feedback`
publishes no mean and no count and reads `"not enough responses yet"`
(`:331-333`): "zero is not the average of nothing, and a speaker nobody rated must
not appear beside a speaker rated 0.0." This is ADR-0011 rule 1 applied to
feedback — and it is also, as Part 3 argues, a floor that would bite hard on any
attempt to use feedback as a training signal even if the register permitted it,
which it does not.

### 1.8 `eli.py` is implemented, tested, and orphaned

`python/smartmatch_domain/smartmatch_domain/eli.py` is 322 lines implementing the
Engagement Load Index from Architecture v1.1 §1.3: `compute_eli` (`:226`),
`evaluate_cap` (`:287`) returning `WITHIN_CAP` / `OVER_CAP` / `BLACKED_OUT`
(`:303-306`), pinned at `ELI_FORMULA_VERSION = "1.1.0"` (`:62`). It is covered by
`tests/unit/test_eli.py`, 339 lines. Its docstring is careful about what it
rejects from the legacy "volunteer fatigue" factor — the health framing, the "Rest
Recommended" labels, the invented days-since-last-assignment — and it records a
port-review correction (F-4) that the docstring once claimed an event-cadence
input the module does not have (`eli.py:12-19`).

**And nothing imports it.** A repo-wide grep for `smartmatch_domain.eli` returns
`tests/unit/test_eli.py:9` and nothing else. There is no `FactorSpec` with an ELI
key in `PROPOSED_FACTORS`; the only `ELIGIBILITY` spec is `availability`, which
points at `smartmatch_domain.eligibility`, a different module
(`factor_registry.py:363-376`). The registry's `FactorKind` docstring names ELI as
the motivating example of a factor that is both Stage A and Stage B
(`factor_registry.py:169-173`) — the concept is in the registry's *prose* and
absent from its *data*.

**What wiring it would cost.** v1.1 §1.3 applies it twice, so it is two changes,
not one.

*Stage A (hard cap).* The cheaper path, and **not a registry change**.
`evaluate_cap` returning `OVER_CAP` or `BLACKED_OUT` becomes an exclusion reason
in `assemble_cba_pool` alongside the existing ones
(`match_run_evidence.py:391-417`; exclusion constants at `:147-165`). It needs: a
persisted source of `EngagementRecord`s — assignments per professional over a
window — that does not exist today; a new exclusion reason constant and its
surface copy; the authorized, expiring override §1.3 requires, which is an authz
and audit design rather than a scoring one; and an open question for the cap value
and the override authority. `REGISTRY_VERSION` does **not** move: a `FactorSpec`
with `kind=ELIGIBILITY` carries `proposed_weight=0.0` by construction
(`factor_registry.py:238-241`) and contributes nothing to Stage B.

*Stage B (soft penalty).* The expensive half. A `PENALTY` spec with non-zero
weight changes the declared factor set and every weight in it, because weights
renormalize. Under ADR-0016 Proposal 9 that is a **major** bump to `3.0.0`, and
every stored `2.x` score becomes non-comparable. It also needs an owner decision
on the weight — which is a re-weighting of all five factors, not an addition to
four — a fifth column in every explanation surface, and golden-case coverage for
the new arithmetic. `_compose_cba` already handles the penalty complement
(`scoring.py:606-613`), so the *composition* is free; nothing else is.

Honest assessment: Stage A is a contained piece of work gated on a data source and
two owner decisions. Stage B should not happen as a side effect of anything — if
the registry is going to `3.0.0`, that bump should be planned once and carry
everything the owner wants at the same time.

---
