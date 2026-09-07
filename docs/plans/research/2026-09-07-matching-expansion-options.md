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

## Part 2 — BakedSoups/NextSteamGame, and how far the analogy carries

### 2.1 What I was able to verify, and how

I fetched the repository landing page, its `README.md`, the `backend/` directory
listing, and the raw sources of `backend/retrieval.py` and
`backend/recommender.py`. Those fetches succeeded and what follows is drawn from
them.

One caveat stated plainly rather than buried: these fetches return the page
rendered and summarised, not a byte-exact checkout. I am therefore confident about
the *architecture* — the stores queried, the pipeline stages, the shape of the
scoring formula, the named constants — and I am **not** offering line numbers, and
I have not read `pg_store.py`, `api_models.py`, `coercion.py`, the `db_creation/`
pipeline sources, or the test suite. Where I state a specific numeric constant
below, it came back from the raw-source fetch and I believe it; where I would be
guessing, I say so instead.

The `backend/` directory contains `__init__.py`, `api_models.py`, `coercion.py`,
`pg_store.py`, `recommender.py`, `retrieval.py`, with the listing indicating
further files not shown.

### 2.2 What it actually does

**Offline pipeline.** Five stages. Metadata and reviews are collected from the
Steam APIs and SteamSpy — up to 2,000 reviews per game across roughly 80,000 games
— and filtered for quality (regex spam removal, review-quality scoring,
word-diversity scoring, insightful-phrase detection). An extraction stage produces
four *focus vectors* per game (mechanics, narrative, vibe, structure_loop) plus
identity metadata (signature tags, niche anchors, identity tags, music tags,
micro-tags), using ModernBERT classification over the reviews. A canonicalisation
stage collapses tags that describe the same concept in different words — "Fast
Action" / "Quick Action" / "High-Speed Combat" — using heuristics, fuzzy matching,
embedding similarity and vector search. A final stage precomputes candidate
relationships offline, because "computing similarity between every game at runtime
would be expensive."

**Retrieval.** Two parallel sources: a Chroma vector index, and a "prescreen"
store used when non-default parameters are set. The Chroma query uses stored
embeddings under default settings and a dynamically built query text otherwise.
Candidate lists are merged **round-robin** with deduplication rather than by a
blended relevance score. The limits are `chroma_limit = 300`,
`prescreen_limit = 450`, `merged_limit = 300`.

**Ranking.** This is the part worth the owner's attention, and it is not what the
phrase "hybrid RAG" suggests. The re-ranker is a **hand-weighted linear composite
of static constants**:

```
total_score = vector(0.54) + genre(0.18) + appeal(0.14) + music(0.14)
```

with per-context multipliers inside the vector term (mechanics 1.22, narrative
0.46, vibe 0.62, structure_loop 1.12), branch weights inside the genre term
(primary 0.8, sub 0.9, sub_sub 0.95), a two-signal blend inside appeal
(`raw_appeal * 0.62 + metadata_signal * 0.38`), identity-tag boosts (signature
2.15, niche anchor 1.55, micro-tag 0.65), zero-overlap genre penalties
(0.90/0.93/0.96), anchor-match boosts (1.08–1.12), and finally a confidence
multiplier derived from review count, owner estimates, positive-review ratio and
Metacritic, clamped to `[0.55, 1.20]`.

**There is no learned model, no feedback loop, and no trained re-ranker.** Every
multiplier is a static constant. The README's own framing is that the project
deliberately avoids player-overlap collaborative filtering ("Players who liked X
also liked Y") because it fails on niche preferences, and instead operates on
semantic identity so a user can see *why* a game was recommended and adjust the
weights themselves.

### 2.3 Where the analogy holds

More than one might expect, and in the direction that flatters SmartMatch rather
than the comparison.

- **The ranking philosophy is the one we already implement.** A transparent,
  hand-weighted linear composite over interpretable components, with the weights
  exposed rather than learned, chosen specifically so the system can explain itself
  and so a human can adjust it. That is `factor_registry.py` and
  `weight_settings.py`. The owner is, without knowing it, pointing at a project
  that validates the architecture we already have.
- **The cold-start motivation is shared.** NextSteamGame rejects collaborative
  filtering because behavioural overlap fails on the long tail. We have no
  behavioural data at all, so we are in that regime permanently, not temporarily.
- **Explainability as a first-class product goal.** Their "understand *why*" is our
  `basis` strings and `CandidateExplanation`.
- **Offline precomputation to keep the request path cheap and deterministic.**
  Directly transferable if we ever do embed text: embed on write, not on match.
- **Canonicalising synonymous tags** is a real, borrowable idea. Our
  `naics_sectors` and `cba_role_categories` modules explicitly defer alias and
  fuzzy matching as "inference rules learned from pilot data and a later versioned
  decision" (`industry_match.py:54-60`). Their Stage 4 is one worked answer to that
  deferral, and it is the single most directly applicable thing in the repository.

### 2.4 Where it breaks

- **Corpus size and provenance.** They mine ~80,000 items × up to 2,000 free-text
  reviews each — millions of documents of third-party opinion. Our per-speaker
  corpus is `topic_text` and `prior_talk`: two nullable `Text` columns (migration
  `0024_cba_classification_schema.py:247-248`), self-declared, often one sentence,
  often absent. There is no review corpus and there never will be. Their semantic
  richness comes from the reviews, not from the algorithm.
- **Candidate pool size.** Their retrieval narrows ~80,000 to 300. `POST
  /match-runs` accepts a pool of at most `MAX_CANDIDATES = 200`
  (`routers/match_runs.py:236`), supplied by the coordinator as
  `candidate_subject_ids` (`:286-296`). We do not have a retrieval problem; see
  §3.4.
- **Consequence asymmetry.** A bad game recommendation costs a user a click. A bad
  speaker match costs a named professional an unwanted approach, a classroom a
  wasted session, and the program a relationship. That asymmetry is why our engine
  refuses rather than guesses in the many branches catalogued in Part 1.
- **Consented contact.** Games do not consent to being recommended. Our candidates
  are named people whose contact is gated by consent state and whose profile text
  OQ-CBA-026 will not let us send to a third party without a named privacy owner's
  decision. "Just embed the corpus" runs into a person, not a dataset.
- **Behavioural telemetry.** They have review counts, owner estimates, positive
  ratios and Metacritic feeding a confidence multiplier. We have none of these and
  — per Part 3 — are forbidden from building the closest equivalents.
- **What "unknown" means.** Their confidence multiplier *degrades* a thin-data game
  to `0.55×` and keeps ranking it. Ours refuses to produce a number at all. Theirs
  is the right call for games; ours is the right call for people. This is the
  deepest structural difference and it is not reconcilable by tuning.
- **Interactive weight adjustment.** Their users retune weights per query and
  re-rank live. Ours are unit-scoped, validated, refused-not-repaired
  (`weight_settings.py:31-39`), and pinned onto every stored run — a
  regulatory-style constraint their product has no reason to carry.

### 2.5 The honest conclusion of the comparison

The most useful finding is a deflationary one. **Strip away the offline pipeline
and NextSteamGame's ranker is the same species of thing as ours** — a weighted
linear composite of interpretable features with hand-set constants. What it has
that we lack is not a smarter algorithm; it is *dozens of graded features derived
from a large text corpus*, where we have three binary-or-banded features and one
that cannot fire. The lesson to take is about **feature richness and gradation**,
not about vector databases.

---

## Part 3 — What stops a hybrid-RAG-style recommender here

The owner's question: "what is stopping us from doing something similar to a
Hybrid RAG type of recommendation system — wouldn't our situation apply?"

Direct answer: **four things, of very unequal size.** One is a decision that could
be taken next week. One is a modest build. One is a design constraint that is
solvable. And one is a wall that no amount of engineering gets over, because it is
about evidence that does not exist and that this system has repeatedly decided not
to collect.

### 3.1 Blocker 1 — there is no semantic provider, and the seam is deliberately shut

`cba_semantic_topic`'s provider is a `Protocol` seam
(`factors/cba_semantic_topic.py:182-202`). The only implementation is a playback
fixture reporting `is_semantic_model = False` (`topic_semantics.py:146`, `:178`).
`build_semantic_topic_provider` refuses a live client under **every** edition, not
merely the classroom one, and `ALLOW_LIVE_PROVIDERS=false` is the standing
environment default — explicitly "necessary but not sufficient here — flipping it
reaches an adapter that still does not exist" (`topic_semantics.py:20-22`).

OQ-CBA-026 records why, and it is not a technical shortfall. The open question is
"which semantic model performs customer §9's Topic comparison, on whose
credentials, under which vendor terms, and at what per-run cost… may a speaker's
`topic_text` and `prior_talk` be sent to a third party at all, and under what
retention?" It requires "CBA product owner with a named privacy owner." And it
closes one door in advance:

> Do **not** answer this by adding a token-overlap scorer and calling it semantic —
> a lexical comparison shipped under a semantic name puts an untrue claim about how
> every stored match was produced into the data permanently, which is why the
> fixture reports `is_semantic_model = False`.

**What clearing it takes.** An owner decision plus a named privacy owner, an
ADR-0014 field set, a vendor and terms, a per-run cost ceiling, and then an
adapter. It is a governance item first and an engineering item second. It is **not**
a step to be taken casually, and this report does not propose enabling live
providers.

Note the corollary from §1.3: this blocker is *currently the binding constraint on
the engine's usefulness*, not only on its future. A speaker with topic text on file
is unscorable today. Whatever else the owner decides, that is worth surfacing on
its own.

### 3.2 Blocker 2 — there is no store, no index, and barely a corpus

There is no embedding store, no vector index, no corpus, and no ingestion job. On
"what would we even embed", the honest inventory is three nullable text columns:

| Field | Table | Type | Source |
|---|---|---|---|
| `topic_text` | `speaker_profile` | `Text`, nullable | migration `0024_cba_classification_schema.py:247` |
| `prior_talk` | `speaker_profile` | `Text`, nullable | migration `0024:248` |
| `description` | `event` (the Speaker Request) | `Text`, nullable | migration `0017_event_persistence.py:174` |

`ck_speaker_profile_text_present` (migration `0024:322`) forbids blank strings, so
a value that exists has content. The domain joins `topic_text` and `prior_talk`
rather than ranking them (`cba_semantic_topic.py:263-277`), and the request
description is the query side (`score_cba_candidate(request_description=…)`,
`scoring.py:448`).

That is the entire corpus: one short self-declared paragraph per speaker, matched
against one coordinator-written description per request. It is not nothing — it is
exactly the input §9 asks about — but it will not support the representation
learning NextSteamGame gets from two thousand reviews a title. An embedding of a
one-line self-description is a paraphrase detector, and it should be sold as one.

**What clearing it takes.** A pgvector column or a sidecar index; an embed-on-write
job with a pinned model id; a backfill; re-embedding on every profile edit. Modest
work, and entirely downstream of 3.1 — you cannot embed text you are not permitted
to send anywhere, and a local model is still a model choice OQ-CBA-026 covers.

### 3.3 Blocker 3 — no outcome loop at all. This is the wall.

Everything above is buildable. This is not, and it is why the honest answer to the
owner's question is "the model is the easy part."

A recommender that is *tuned* — never mind trained — needs relevance judgements:
some record of which past matches were good. This system has **none**, and not by
oversight. Four decisions and one schema gap each remove one candidate source.

**No appearance relation (OQ-CBA-051).** "What persisted evidence proves that a
particular speaker appeared at a particular event? … the current schema has no
speaker-to-event appearance relation; `cba_invitation_batch.event_name` is free
text and cannot supply one." The decision: "Require the speaker to be on the
feedback unit's roster, and state the limitation. Do not claim roster membership
proves an appearance and do not derive the speaker from a name." So the schema
cannot express the fact "this match resulted in this speaker actually speaking."

**Nothing writes the attendance table either.** `attendance_record` exists —
`db/migrations/versions/0009_engagement_schema.py:184-235`, with columns `id`,
`tenant_id`, `owning_unit_id`, `subject_id`, `event_id`, `method`, `created_at` —
and **no `/v1` route creates one.** `routers/student_events.py` states outright
that "Nothing is written to `attendance_record`"; `routers/cba_handoff.py` and
`routers/pipeline.py` *cite* an `attendance_record` for the Attended stage but do
not create one. Every write path found is outside the `/v1` API. So even the weaker
proxy — "somebody attended this event" — has no API-driven writer.

**Declines are recorded and never scored (OQ-CBA-040).**
"`cba_invitation.response_status` is not a scoring input, and no factor in the
registry knows the table exists." Decision: "Recorded, never scored. A decline is
one data point about one event on one date, and the reasons for it — a diary clash,
a topic mismatch, a bad month — are invisible to this system. Treating it as a
standing signal would quietly demote somebody for being busy in June, and it would
do so through a factor nobody approved."

**Ratings are barred (OQ-CBA-053).** "Should a student's rating of a speaker
influence later matching? … **No.** Student speaker feedback is an event outcome
and remains separate from coordinator match-outcome feedback; no rating is a
scoring input and no factor reads this table." And even if reopened, aggregates
below three responses publish nothing at all (`student_speaker_feedback.py:92`,
`:331-333`) — so a per-speaker signal would be suppressed for exactly the long-tail
speakers a recommender most needs to learn about.

**And the one loop that does exist is orphaned and mis-wired.**
`smartmatch_domain/feedback.py` implements precisely the mechanism a tuner would
want: coordinator accept/decline decisions aggregated into bounded weight-delta
proposals, `min(MAX_FACTOR_DELTA, PER_REASON_BUMP × count)` with
`MAX_FACTOR_DELTA = 0.08` (`:64`), `PER_REASON_BUMP = 0.03` (`:68`),
`MIN_DECLINES_PER_FACTOR = 5` (`:78`), held deliberately shadow-mode: "it proposes
weight deltas, and a human approves them. Generative AI never chooses ranking
weights" (`:31-34`). Two problems. First, **nothing imports it** — a repo-wide grep
for `smartmatch_domain.feedback` returns only `tests/unit/test_feedback.py:8` and a
disambiguating docstring reference at `student_speaker_feedback.py:8`. Second, its
`REASON_TO_FACTOR` map (`:108-119`) targets `topic_relevance`, `role_fit`,
`travel_burden`, `availability`, `engagement_load`, `repeat_penalty` — of which
`topic_relevance` and `travel_burden` are **retired**, and `role_fit`,
`engagement_load` and `repeat_penalty` **do not exist in `PROPOSED_FACTORS` at
all**. The one tuning loop in the codebase is wired to a factor set the CBA pivot
replaced.

**And the pilot cannot supply the missing signal.** The pilot runs entirely on
synthetic data on a VM with pre-loaded logins, demonstrating that a Connector can
see events needing matching, produce a match, and that a dashboard renders
statistics. That is a functional demonstration and a good one. It is *not* a source
of relevance judgements, and the distinction is absolute rather than a matter of
volume: synthetic accept/decline decisions are made by people testing a workflow,
and they measure whether the button works, not whether the match was good. **No
quantity of synthetic pilot data produces a single true label.** A model tuned on it
would be fitted to the fixture generator. This is worth stating because "we will
have data after the pilot" is the natural assumption and it is false.

**What clearing it takes.** In order: an owner decision to reopen OQ-CBA-051 and
design a speaker-appearance relation; a `/v1` writer for whatever that relation is,
and separately for `attendance_record`; a decision on whether coordinator
accept/decline may become a *learning* signal rather than only a shadow proposal,
which is OQ-CBA-040 territory; re-pointing `feedback.py`'s reason map at the CBA
factor set; and then **real matches, made by real Connectors, over real events, for
long enough to accumulate labels**. That last item is measured in program cycles,
not sprints, and nothing in engineering shortens it.

Until then, any "learned" component would be fitted to constants somebody chose —
which is what we already have, minus the auditability.

### 3.4 Is retrieval even the bottleneck? No.

It is not, and this is the most actionable finding in Part 3.

`POST /match-runs` takes `candidate_subject_ids` from the caller, capped at
`MAX_CANDIDATES = 200` (`routers/match_runs.py:236`, `:286-296`). The pool
assembler reads exactly those rows in one query and decides per subject
(`match_run_evidence.py:353-419`). There is no retrieval stage in this engine at
all — the coordinator names the pool. Compare NextSteamGame narrowing 80,000 to
300: they need retrieval because the corpus is four orders of magnitude larger.
Scanning 200 rows of a CBA roster is a query, not an information-retrieval problem,
and a vector index over 200 documents buys nothing an in-memory scan does not.

The real problem is **scoring resolution**: those 200 candidates collapse onto 12
distinct composite values (§1.3), and in practice onto far fewer, because a pool
assembled for one sector and one role shares its two heaviest factors by
construction. The engine cannot tell its candidates apart. That is a *feature
gradation* problem, and it is exactly the problem NextSteamGame solves with dozens
of graded features — not with Chroma.

So: the owner's instinct that something is missing is correct. The diagnosis "we
need retrieval / RAG" is the wrong one. **We need more graded factors, or finer
ones, over the pool we already have.**

### 3.5 Determinism, and what an embedding model does to it

Every stored run pins `registry_version`, `formula_version` and `applied_weights`
(`StageBScore`, `scoring.py:165-174`; `MatchRunPins` per ADR-0016 Proposal 9, which
adds `scoring_mode` and `scoring_mode_version` and keeps `registry_hash` as the
fingerprint over the weights actually applied). The submission API takes an explicit
solver `seed` and documents the contract: "the same pool, size and seed always
produce the same selection" (`routers/match_runs.py:280-285`). The golden suite
pins exact composites — G-CBA-11 asserts `0.9175` and `0.925`, not "A ranks above
B."

A live embedding model breaks this in four distinct ways, worth separating because
they have different fixes:

1. **Model drift.** A hosted endpoint silently re-versioned changes every score.
   *Fix:* pin an immutable model id and refuse to score if the served id differs.
   `TopicComparison` already carries `model_id` (`cba_semantic_topic.py:166-167`);
   the field exists precisely for this.
2. **Nondeterministic inference.** Batching, GPU non-associativity and
   floating-point ordering perturb embeddings run to run. *Fix:* embed once on
   write, store the vector, and score from the stored vector — never embed at match
   time. This also makes the request path cheap, and it is the one NextSteamGame
   lesson that transfers cleanly.
3. **Reproducibility of a stored run.** Re-scoring a run a year later must reproduce
   it. *Fix:* treat the vector as evidence rather than as model state — store it and
   the resulting comparison alongside the run, the way `basis` already stores the
   provenance of every factor value.
4. **Provenance honesty.** `is_semantic_model`, `provider` and `model_id` must
   travel onto the stored score, or a future reader cannot tell a fixture from a
   model. The seam already requires this (`cba_semantic_topic.py:483-494`).

Conclusion: determinism is a **solvable** constraint, and the codebase has already
put most of the fields in place. It costs a versioning discipline —
`CBA_SEMANTIC_TOPIC_FACTOR_VERSION` (`:117`) would have to move with the model —
not a redesign. It is not the reason to say no.

### 3.6 A staged path, if the owner wants one

Ordered by cost, each stage independently abandonable. These are **proposals**, not
decisions.

**Stage 0 — surface the fixture problem (no decision needed, no registry change).**
Report how often, on realistic data, a candidate with topic text is rendered
unscorable by `TopicComparisonUnavailable`. My reading of
`topic_semantics.py:194-200` says: always, outside a recorded pair. If that is
right, the Topic factor is effectively inert in any non-fixture run, and the owner
is choosing between the 12-value engine and something else — not between a good
engine and a better one. *Buys:* the owner learns what he actually has. *Costs:* an
afternoon.

**Stage 1 — fix the resolution problem inside the existing factors (registry change,
but a small and well-understood one).** The gradation deficit is in Industry, Role
and Proximity, and it is fixable without any model. Graded industry match — exact
sector 1.0, related sector within a shared NAICS parent 0.6, unrelated 0.0 — is the
alias/fuzzy work `industry_match.py:54-60` already defers, and it is
NextSteamGame's Stage 4 idea applied to a taxonomy we control. Finer proximity
bands, or interpolation within a band, do the same for the 0.30 that is currently
three-valued. *Buys:* an order of magnitude more distinct composite values, from
data we already hold, with no provider, no vendor and no privacy question. *Costs:*
a `3.0.0` registry bump, an owner decision per change, new golden cases, and stored
`2.x` runs becoming non-comparable. **This is the highest value-per-risk option in
this report, and it does not appear anywhere in the owner's original question.**

**Stage 2 — lexical/BM25 blending inside the existing Topic factor (no registry
change — but read the caveat).** Mechanically this is attractive: BM25 over
`topic_text || prior_talk` against the request `description` is deterministic,
local, cheap, needs no vendor and no privacy decision, and would be a *provider
behind the existing seam*, so `APPROVED_SCORING_KEYS` is untouched and
`assert_scoring_ready` still passes. **But OQ-CBA-026 forbids the obvious form of
it**: shipping a lexical scorer under the `cba_semantic_topic` name is precisely
what the decision names and refuses. There are two honest ways round it and both
need the owner. Either a new adapter that reports `is_semantic_model = False`, is
labelled lexical in every `basis` string it writes, and is admitted by an explicit
amendment to OQ-CBA-026 recording that a labelled lexical provider is acceptable in
the Topic slot; or a genuinely separate lexical factor, which is a registry change
and lands in Stage 1's bump. *Buys:* a continuous Topic signal without a vendor.
*Costs:* an OQ amendment; a real risk of the naming confusion the ADR authors were
right to fear; and BM25 over one self-written sentence is a weak signal that will
look more precise than it is.

**Stage 3 — embeddings.** Only after 3.1 is answered by the owner and a named
privacy owner, with an embed-on-write store per §3.5. *Buys:* real paraphrase
tolerance on Topic. *Costs:* the governance work of OQ-CBA-026, a store, a backfill,
a pinned model id, and a versioning discipline.

**Stage 4 — anything learned.** Blocked on §3.3 and not schedulable. Revisit when an
appearance relation exists and has accumulated real outcomes over real program
cycles.

**Also worth doing independently of all four:** re-point `feedback.py`'s
`REASON_TO_FACTOR` at the CBA factor set, or delete the module. Leaving a
shadow-mode weight tuner wired to three factor keys that do not exist is a trap for
whoever wires it up next.

---
