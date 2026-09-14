# ADR-0018 — A staged student→event recommender: eligibility, a swappable ranker, and a policy re-rank

**Status:** Proposed
**Date:** 14 September 2026
**Owner of record:** Student-engagement program owner, with the scoring-registry owner and the records/privacy owner
**Decides:** the *architecture* of the student→event recommender and the order in which recommender families may be admitted into it. It closes no register row. OQ-SC-02, OQ-SE-01 and OQ-SE-02 still need their named owners; this ADR adds OQ-SE-19 through OQ-SE-22 to the canonical register for the learned stages.
**Contract:** `docs/architecture/student-recommender-contracts.md`; `docs/decisions/student-recommender-decision-record.md`; ADR-0011; ADR-0012; ADR-0016
**Register:** `docs/plans/open-questions/student-engagement-deferred.md`
**Evidence:** `docs/plans/2026-09-13-w2-student-event-ranking-plan.md` (superseded, retained as ranking-design evidence); `docs/plans/research/2026-09-13-engagement-feed-research.md`; `docs/plans/research/2026-09-07-matching-expansion-options.md` §3.3 ("no outcome loop")

> **Proposed.** Nothing in this ADR licenses a route, a table, a model artifact,
> or a scoring path. What it fixes is the *shape* the student recommender must
> take so that the first version (content-based) and every later version
> (learned ranking, collaborative signal, session adaptation) are replacements
> of one stage behind one interface, never a second scoring system beside the
> first. The values a later version needs — labels, interaction rows, a stored
> skip — are register decisions, and the ADR names the row each one waits on.

## Context

**The speaker matcher is a fixed-weight rulebook, and that is correct for it.**
`smartmatch_domain.factor_registry` composes four factors at Industry 0.30 /
Role 0.25 / Topic 0.15 / Proximity 0.30 (`PROPOSED_FACTORS`, `factor_registry.py:280-332`),
approved by ADR-0016 and pinned to `REGISTRY_VERSION = "2.0.0-approved-oq-cba-004"`.
Those numbers are an owner's signed policy over a coordinator-facing, irreversible,
solver-backed decision (an invitation goes out). Re-tuning them from behaviour is
barred by OQ-CBA-059/060, and the registry's own `assert_scoring_ready()` makes
adding a fifth factor to it impossible without breaking every CBA call
(`factor_registry.py:585`; W2 plan §1).

**The student problem is a different recommendation problem.** The subject is a
student, the candidates are *events*, nothing irreversible follows from showing
one, there is no shared scarce resource coupling candidates, and the output is a
bounded feed rather than a shortlist for a solver. The success metric the
stakeholders named is *registrations per active student and
registration→attendance conversion*, not time in feed. Today there is no student
profile table, no student→event factor, and no student-facing recommendation
route; `routers/student_events.py` serves a time-ordered published catalog only.

**Five recommender families were evaluated** (`docs/decisions/student-recommender-decision-record.md` §2):

| # | Family | Needs at request time | Needs to build | Fit now |
|---|---|---|---|---|
| 1 | Content-based / knowledge-based ranking over the closed G3 vocabulary | declared interests + mapped event tags | nothing behavioural | **build first** |
| 2 | Learning-to-rank (LambdaMART / `xgboost` `rank:ndcg`) | a feature vector per (student, event) | labelled outcomes per (student, event) | evolution of Stage B once labels are permitted |
| 3 | Hybrid collaborative + metadata (LightFM) | latent vectors | a student×event interaction matrix | after interactions are permitted and dense enough |
| 4 | Multi-stakeholder constrained re-rank | ranked list + policy | nothing behavioural | **always on**, wraps 1 and 2 |
| 5 | Contextual bandit (LinUCB / VW `cb_explore_adf`) | session context | logged (context, action, propensity, reward) | session-only now; learned policy later |

**What the platform already rules out.** ADR-0011 rule 1: a value with no evidence
is `unknown`, never `0` and never a silent `0.5`. ADR-0016: a policy-neutral
value exists only where a customer has *stated* a policy for an observed absence;
nobody has stated one for an untagged event (OQ-SC-12). `PROHIBITED_INPUTS`
names `unrelated_student_feedback` and `llm_generated_assumption`
(`factor_registry.py:398`). OQ-CBA-053 is closed at "student ratings must not
influence matching". The canonical register's safe defaults are: no profile
persistence (OQ-SC-02), session-only skips (OQ-SC-09), no stored exposure rows
(OQ-SC-11), no neutral for untagged events (OQ-SC-12), student registry stays
`proposed` and fails closed (OQ-SE-01), at most one labelled wildcard and no
backend toggle (OQ-SE-02).

**The scarce resource is permissioned outcome data, not compute.** Every family
above serves on 1–2 vCPU and trains on 4–8 CPU cores; none needs a GPU at pilot
or campus scale (§ "Resources" below). Families 2, 3 and 5 differ from 1 and 4
only in *what they must be allowed to remember about a student*. That is why the
admission order below is a sequence of register decisions, not a sequence of
engineering milestones.

## Decision

### D1. Three stages with fixed interfaces; every version replaces one stage

```
StudentRankingRun (interests, modality, vocabulary version, feed window, unit)
        │
        ▼
Stage A  EligibilityFilter        published · dated inside window · modality-compatible
        │                         · no quarantined tag · not already registered
        │                         excluded events are COUNTED, never silently dropped
        ▼
Stage B  StudentRanker            V1 ContentRanker   (STUDENT_REGISTRY, Jaccard)
        │                         V2 LearnedRanker   (LambdaMART, same protocol, same StageBScore)
        │                         unknown stays unknown; unscorable sorts last
        ▼
Stage C  FeedPolicy               bounded top-N · one declared wildcard · diversity cap
        │                         · session exclusions supplied by the caller · governance
        ▼
StudentFeed (items, wildcard, withheld counts, provenance pins, inputs_hash)
```

The interfaces are the contract (`student-recommender-contracts.md` §3):

- `EligibilityFilter.apply(run, candidates) -> EligibilityResult` returns the
  eligible tuple **and** a `Mapping[str, int]` of exclusion reasons.
- `StudentRanker.rank(run, candidates) -> tuple[StageBScore, ...]` returns the
  existing `smartmatch_domain.scoring.StageBScore` unchanged in shape.
  `subject_id` holds the *event* id and is documented, not renamed (W2 §5).
- `FeedPolicy.select(run, ranked) -> StudentFeed`.

A new recommender family is admitted **only** as a new implementation of one of
these three, carrying its own `registry_version` / `formula_version` /
`model_artifact_hash` pin. A family that needs a fourth stage, or that needs
Stage B to return a different shape, is a new ADR.

### D2. The student registry is its own `FactorRegistry`, built by parameterising the CBA mechanism

W2a/W2b as designed: extract a frozen `FactorRegistry` value object
(`version`, `status`, `approver`, `approved_on`, `factors`,
`approved_scoring_keys`, `scoring_modes`) and thread it through
`assert_registry_approved`, `assert_scoring_ready`, `factor_keys`,
`implemented_scoring_keys`, `resolve_scoring_model`, `normalize_weights`, and
the two module-level lookups `scoring._FACTOR_KIND` and
`explanation._SPECS_BY_KEY`. `ScoringModel.__post_init__`'s closed-mode check
moves to the registry. Every existing constant stays exported and bound to
`CBA_REGISTRY`; every free function defaults to `CBA_REGISTRY`; and
`tests/unit/test_factor_registry.py` is not edited by one line. `PROHIBITED_INPUTS`
is **imported** by the student registry, never copied.

`STUDENT_REGISTRY` ships with `status = "proposed"` and fails closed until
OQ-SE-01 closes. Its V1 contents are exactly W2 §4: `student_interest_overlap`
(SUITABILITY, 1.00, Jaccard over the shared G3 vocabulary, six evidence rows),
`student_modality_eligibility` (ELIGIBILITY, 0.0), and two declared-unbuilt
factors at `proposed_weight = 0.0`.

### D3. V1 Stage B is content-based and lexical: Jaccard over the closed vocabulary

Not a percentage, not an LLM score, not a neutral for an untagged event.
`|I ∩ T| / |I ∪ T|` is chosen because it is symmetric and gaming-resistant
(declaring all twelve interests scores strictly worse than declaring two
accurately). Both sides arrive at the same `vocabulary_version`; a mismatch is
a caller bug and raises at construction. Absences are distinguishable
(`NO_PROFILE`, `NO_TAG_RECORDS`, none-mapped → `unknown`; disjoint sets →
measured `0.0`).

### D4. V2 Stage B is a learned ranker admitted as a *replacement* of D3, under four conditions

The target is LambdaMART (`xgboost.XGBRanker`, objective `rank:ndcg`, CPU),
because it learns an *ordering* against the metric the stakeholders named and
its trees are inspectable enough to keep `reason` honest. It is admitted only
when all four hold:

1. **Same protocol, same output.** It is a `StudentRanker`. It returns
   `StageBScore` with `formula_version = "ltr-<semver>"`, `scoring_mode =
   "student-event-ltr-1"`, and a `model_artifact_hash` in `applied_weights`'
   sibling provenance field on the run pin. The HTTP contract does not change.
2. **Features are registered, not improvised.** Every model input is a
   `FeatureSpec` in `STUDENT_FEATURE_REGISTRY` (`student-recommender-contracts.md` §4)
   with `key`, `source`, `required`, `evidence_states`, and the register row that
   admitted it. A feature whose `source` is in `PROHIBITED_INPUTS` cannot be
   constructed. `required=True` features that are `unknown` make the composite
   `unknown` (ADR-0011 unchanged); `required=False` features are encoded as
   *missing* to the trees, never imputed with a number.
3. **Labels are a register decision.** Training a ranker on a student's own
   registration or attendance is a *use of behavioural data about that student*.
   It is not the same act as reading it at request time (which
   `PROHIBITED_INPUTS` bars), but it is not free either. **OQ-SE-19** decides
   whether, on what retention, and with what deletion semantics outcome rows may
   become training labels. Because each example records an exposure, OQ-SC-11
   must close or be scoped by that decision as well. Until it closes, the
   learned ranker may be trained and evaluated **only** on authored gold sets
   and synthetic pilot data (`tests/golden/student/`,
   `docs/pilot-data/fixtures`), and never promoted.
4. **Promotion is shadow-first and owner-signed.** A learned model runs in shadow
   beside D3 on the same eligible set, its offline NDCG@5 against the gold set
   and its live agreement rate are reported to the owner, and **OQ-SE-20** names
   the owner who promotes it, the rollback owner, and the retirement of the
   previous `formula_version` (which stays readable for stored pins, ADR-0016
   Proposal 9's discipline).

A learned model is never the *first* ranker a unit sees: D3 is the fallback the
protocol guarantees, and a model artifact that fails to load makes the route
fall back to D3 with `ranker = "content-1"` stated in the payload, not to an
error and not silently.

### D5. Collaborative signal enters as a registered *feature*, never as a second ranker

When (and only when) **OQ-SE-21** permits a student×event interaction matrix,
LightFM-style latent affinity is admitted as one `FeatureSpec`
(`collaborative_affinity`, `required=False`) consumed by D4. Pure collaborative
filtering as a ranker is rejected: it has nothing to say to a new student or a
new event, which is the day-one state of every unit, and "students like you
attended" is a claim built from other named students' behaviour (D8's
question). Training runs on the worker (Dockerfile.worker) as an outbox job
with a deterministic task name (ADR-0005, ADR-0007); the artifact is
content-addressed and pinned by hash.

### D6. Session adaptation is a Stage C policy over caller-supplied context; a learned bandit policy is a later register decision

"Skip → the rest of the feed adapts" is implemented in Stage C from an
`exclude_event_ids` query parameter the client sends for the current session.
The server stores nothing (OQ-SC-09 safe default) and returns the same
`inputs_hash` discipline with the exclusions folded into the canonical tuple. A
*learned* exploration policy (LinUCB / VW) needs logged
`(context, actions, chosen, propensity, reward, policy_version)` rows, which are
per-student behavioural records; **OQ-SE-22** owns that. Until then exploration
is exactly the one declared wildcard OQ-SE-02 governs, selected by an index
derived from `inputs_hash` with the seed returned.

### D7. Stage C is a constrained re-rank, and it is always on

Stage C applies, in this order: (1) bounded window and size
(`STUDENT_FEED_WINDOW_DAYS = 7`, `STUDENT_FEED_MAX_ITEMS = 5`,
`STUDENT_FEED_WILDCARD_SLOTS = 1`, domain constants); (2) session exclusions;
(3) a **diversity cap** — no more than `STUDENT_FEED_MAX_PER_PRIMARY_TAG = 3`
ranked items sharing the same primary tag, stated as a constant, applied as a
stable re-order that never promotes an unscorable item; (4) the declared
wildcard from the scorable pool outside the ranked list, or `null`; (5)
governance: unscorable events counted under `withheld_unscorable`, events with
no mapped tag counted under `withheld_untagged` (OQ-SC-12 default), and a
worded refusal through the standard error envelope while the registry is
`proposed`. Capacity and host-side constraints are deliberately **not** in V1
(no capacity datum exists on `event`); they are the natural next Stage C rule
and need no ADR, only a constant and a golden case.

### D8. No numeric score reaches a student surface, in any version

`rank`, `matched_interests`, and a one-sentence `reason` are the account. A
schema-walking contract test rejects any number-typed property matching
`score|value|percent|match|fit|rating|confidence` on the student response
(`rank` allowed by name). This holds for D4 too: a learned model's margin is
no more a "match percentage" than Jaccard is.

### D9. Rejected

- **Extending the CBA registry** with student factors, or a second weight
  system beside it (W2 §1; matching-expansion brief §5 "Option 1").
- **A neural two-tower / deep retrieval model.** Needs GPU-class training,
  hundreds of GB of logs, and an outcome loop that does not exist; no benefit
  at hundreds of events per unit.
- **A popularity or time-ordered fallback** dressed as recommendations when the
  profile is absent or the catalog is untagged.
- **Endless feed, autoplay, variable-ratio reward, streak mechanics** (feed
  research "Refused" column).
- **Inferring interests from behaviour** ("registered for three hackathons ⇒
  `hackathon` interest"; W1 §"No inference").

## Resources

Stated so nobody sizes a GPU for this.

| Stage / version | Serve | Train | Storage |
|---|---|---|---|
| A + C (constraints, policy) | inside the API request, <1 vCPU-ms per event | — | none |
| B-V1 content (Jaccard) | tens of set operations per request | — | `student_profile`, `student_profile_interest`, existing `event_tag` |
| B-V2 LambdaMART | 1–2 vCPU, 2–4 GB, artifact 10–100 MB loaded once | worker job, 4–8 vCPU, 8–16 GB, CPU only | labelled rows (OQ-SE-19) ≫ model |
| Feature: collaborative affinity | vectors in the artifact | worker job, 4–8 vCPU, 8 GB | interaction matrix (OQ-SE-21), sparse |
| Bandit policy | 1–2 vCPU | incremental | decision logs (OQ-SE-22): the expensive part |

The recommendation path adds no service, no vector store, and no external
provider; `ALLOW_LIVE_PROVIDERS` is irrelevant to it.

## Consequences

**Good.** One response contract survives every version. A unit with a thin tag
catalog gets an honest, thin feed and a visible `withheld_untagged` count
rather than a fabricated one. The learned path can be *built and measured*
against gold sets before any student datum is stored, so the engineering risk
and the privacy decision are decoupled. Nothing in the CBA path moves.

**Bad, accepted.** V1 has one scored factor, so ties are common and the
tie-break (event id ascending) does real work; the diversity cap and the
wildcard are what keep the top five from being five near-identical events. V2
cannot be promoted on synthetic labels alone, so the calendar to a learned
ranker is bounded by OQ-SE-19/20, not by engineering. Parameterising the
registry touches three hot modules and must land as its own no-behaviour-change
PR with `test_factor_registry.py` untouched as the pin.

**Verification.** The tests in `student-recommender-contracts.md` §7 are the
acceptance criteria for this ADR: registry isolation, import-reachability of
prohibited sources, the six evidence rows, determinism (`inputs_hash` and order
identical across two calls), the numeric-score schema walk, wildcard honesty,
proposed-status refusal, and — for D4 — a `FeatureSpec` whose `source` is
prohibited failing at construction, and a `LearnedRanker` whose artifact is
missing falling back to `content-1` with the fallback named in the payload.

## Amendment discipline

A later version that wants a different bound, a different diversity constant,
a neutral for untagged events, or a fifth stage amends this ADR and re-approves
it. Adding a `FeatureSpec` is a registry version bump plus a register row, not
an ADR amendment. Promoting a learned model is an OQ-SE-20 artifact, not an
ADR amendment.
