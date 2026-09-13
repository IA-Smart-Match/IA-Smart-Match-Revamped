# W2 — student → event ranking (2026-09-13)

**Status:** planning only. No source file changes, no route, no migration.

**Parent:** [`2026-09-13-student-recommendation-program-plan.md`](2026-09-13-student-recommendation-program-plan.md).
**Depends on:** the vocabulary module from W1 §2 (not the table — this wave
consumes evidence dataclasses, not rows).
**Migration:** none, by construction.

---

## 1. Its own registry. Not an extension of the CBA one.

Four arguments, in descending force.

**1. `assert_scoring_ready()` makes extension impossible without collateral
damage.** It asserts `implemented_scoring_keys() == APPROVED_SCORING_KEYS`
*exactly*, and it is called at the top of `score_candidate` and
`score_cba_candidate` — including on the reproduce-a-stored-run path. Registering
a student factor with `implemented=True` breaks **every CBA scoring call** the
moment it merges, until `APPROVED_SCORING_KEYS` is widened. Widening it puts the
key into `CBA_PHYSICAL_MODEL.scoring_keys` (built by
`_keys_in_registry_order(APPROVED_SCORING_KEYS)`), so a *speaker* would be scored
on a student's interests — and `_compose_cba`'s deflation guard would then fire
because `_cba_factor_scores` never computes it. Registering it `implemented=False`
means it can never be used. There is no third position.

**2. The 1.0 invariant re-opens a signed decision for no product reason.** A fifth
weight forces re-approval of Industry 30 / Role 25 / Topic 15 / Proximity 30 —
ADR-0016's owner-signed numbers, accepted 2026-09-05 — plus a major
`REGISTRY_VERSION` bump, new `SUPERSEDED_*` machinery, and a re-derivation of
`CBA_VIRTUAL_MODEL`'s computed 0.428571 / 0.357143 / 0.214286.

**3. A registry version identifies a rulebook, and `match_run` cannot
disambiguate two.** It has no subject-kind column and `event_need_id` is `Text`
with no FK. Two subject kinds sharing one version string makes every stored pin
ambiguous about what was being scored.

**4. A second `ScoringModel` under the same registry is the wrong seam.**
`implemented_scoring_keys()` ranges over `PROPOSED_FACTORS` globally, not per
model, so the exact-set assertion still fails. The split has to be at the
registry.

**This is not a second scorer.** The mechanism is shared; only the data splits.

## 2. W2a — parameterise `factor_registry`, do not copy it

Extract a value object and thread it through, in its own PR with no student
artifact in it:

```
@dataclass(frozen=True, slots=True)
class FactorRegistry:
    version: str
    status: str                                  # "approved" | "proposed"
    approver: str | None
    approved_on: str | None
    factors: tuple[FactorSpec, ...]
    approved_scoring_keys: frozenset[str]
    scoring_modes: Mapping[str, ScoringModel]    # this registry's closed mode vocabulary
```

then `assert_registry_approved(registry=CBA_REGISTRY)`,
`assert_scoring_ready(registry=...)`, `factor_keys(registry=...)`,
`implemented_scoring_keys(registry=...)`, `resolve_scoring_model(mode, registry=...)`.

**Three of these are real code changes, not plumbing, and each blocks the wave:**

- **`ScoringModel.__post_init__` validates `scoring_mode not in CBA_SCORING_MODES`.**
  That check must move to the registry — each registry declares its own closed
  mode vocabulary — or a student model cannot be constructed at all. This is the
  single blocking edit.
- **`explanation.py::_SPECS_BY_KEY` is built from `PROPOSED_FACTORS`.**
  `explain_candidate` must resolve the spec table from the score's own
  `registry_version` via a `registry_for_version()` lookup, or a student score
  raises `KeyError`. This is *also* the correct fix in general: the file's own
  comment already says weights must come from the score rather than from today's
  registry, and the spec table should follow the same rule.
- **`scoring.py::_FACTOR_KIND`** is likewise a module-level dict over
  `PROPOSED_FACTORS`; make it a registry lookup.

Every existing module-level constant stays exported, bound to `CBA_REGISTRY`'s
fields, and every free function keeps a default argument of `CBA_REGISTRY`.

**The pin on this PR is that `tests/unit/test_factor_registry.py` is not edited by
a single line.** If the parameterisation changed CBA behaviour, that file fails.

Do **not** copy the mechanism into a parallel module. Two copies of
`normalize_weights` is the second source of truth `display_weights`' own docstring
forbids, and duplication is how the legacy deflation defect recurs.

## 3. W2b — the student registry, shipped with the gate shut

```
STUDENT_REGISTRY_VERSION        = "0.1.0-proposed-oq-sc-09"
STUDENT_REGISTRY_STATUS         = "proposed"          # <-- the gate
STUDENT_SCORING_MODE            = "student-event-1"
STUDENT_SCORING_MODE_VERSION    = "1.0.0"
STUDENT_STAGE_B_FORMULA_VERSION = "1.0.0"
APPROVED_STUDENT_SCORING_KEYS   = frozenset({"student_interest_overlap"})
```

`status = "proposed"` means `assert_registry_approved(STUDENT_REGISTRY)`
**raises**, so the whole student scoring path fails closed until a named human
approves it — the mechanism gate G1 used. That is what lets W2 and W3 merge
*before* the owner decision, with the gate visible in a test rather than in a
checklist.

`PROHIBITED_INPUTS` is **imported, not copied.** It already names
`unrelated_student_feedback` and `llm_generated_assumption`; both bind here.

## 4. The factors — one scored, one eligibility, two declared unbuilt

**Only one student→event factor can be built honestly today.** Saying so, in the
registry's own idiom, is better than inventing two more.

### `student_interest_overlap` — SUITABILITY, weight **1.00**, `implemented=True`

Set overlap between declared interests and an event's mapped tags, both at the
same vocabulary version. Both sides arrive **already resolved** — the caller who
read the row is the one who says which absence it is (ADR-0016 Proposal 1):

```
StudentInterestEvidence:  DECLARED | NO_PROFILE      + terms, vocabulary_version
EventTagEvidence:         TAGGED  | NO_TAG_RECORDS   + mapped_terms, quarantined_count, vocabulary_version
```

`__post_init__` raises `ValueError` — a caller bug, not missing evidence, which is
`industry_match._validate`'s exact distinction — when the two versions disagree or
either names a version other than the student binding's.

**The boundary, stated once: a set that was read and does not overlap is a
measured zero; a set that could not be established is unknown.**

| Evidence | State | Value |
|---|---|---|
| No profile row | UNKNOWN | `None` — "no interest profile on file for this student (g3-2026-08-29)" |
| Profile exists, zero interests | UNKNOWN | `None`. The `PUT` refuses this, so it should be unreachable; the branch exists because a factor may not assume its writer's discipline |
| Event has no `event_tag` rows | UNKNOWN | `None` — "this event carries no vocabulary tags; not evaluable" |
| Event has tags, **none mapped** | UNKNOWN | `None` — `industry_match`'s "none of them resolved" branch verbatim: a student cannot miss a target set that was never established |
| Both read, intersection empty | **MEASURED `0.0`**, `zero_classification = "measured_zero"` | a real claim about two real sets |
| Both read, intersection non-empty | MEASURED | Jaccard, rounded to `FACTOR_SCORE_PRECISION` |

**Is a policy-neutral value legitimate here? No, for either absence.** ADR-0016's
neutral exists only because customer §9 *states* a policy for a speaker with no
topic evidence; §7 states none for industry, which is why `industry_match`
"deliberately does not reach for the neutral machinery". Nobody has stated what an
untagged event is worth to a student. Inventing 0.5 would be the invention
ADR-0016 forbids.

**Consequence, and it is the biggest product risk in this design.** Every event
with no mapped tag is unscorable and sorts last. That is honest, and it makes tag
coverage *visible* rather than hidden — but a thinly tagged pilot catalog means a
thin feed. Registered as **OQ-SC-12 — "is an untagged event worth a stated
neutral, and what value?"** Owner: program owner with Ann. Safe default: no
neutral, UNKNOWN, and the feed reports the count. Answering it later is a value
plus a `policy_id` plus a formula-version bump, not a redesign.

**Formula: Jaccard, `|I ∩ T| / |I ∪ T|`**, argued rather than defaulted.
`|I ∩ T| / |I|` rewards declaring one interest; `/ |T|` punishes a richly tagged
event; Jaccard is symmetric so neither side is privileged, and — decisively — it
makes "tick all twelve" strictly *worse* than declaring accurately: twelve
interests against a two-tag event scores 2/12, where two accurate interests score
1.0. A gaming-resistant formula is worth more here than a marginally better
ranking.

`basis` is written by the factor and validated with `assert_one_sentence` at
construction (`cba_semantic_topic`'s pattern): *"Your interests hackathon and
workshop match two of this event's three tags (g3-2026-08-29)."* The version
token's dots survive the sentence-boundary regex because they are followed by
`)`.

### `student_modality_eligibility` — ELIGIBILITY, weight `0.0`, `implemented=True`

**A Stage A filter, not a scored factor — and that choice is the whole reason the
field is admissible.** As a scored factor, `no_preference` would need an invented
value that no policy states. As eligibility it needs none: `in_person` excludes
virtual events, `virtual` excludes the converse, `no_preference` excludes nothing.
`FactorSpec.__post_init__` already enforces that an ELIGIBILITY factor carries
zero Stage B weight, and `implemented_scoring_keys()` filters on `is_scoring`
before `implemented`, so it is correctly invisible to
`APPROVED_STUDENT_SCORING_KEYS`. Excluded events are **counted and reported**,
never silently dropped.

### Declared, `implemented=False`, `proposed_weight = 0.0`

The registry's designed way to record an intended shape without deflating
anything — `active_weight` returns 0.0 and `normalize_weights` excludes it from
the denominator.

- **`student_availability_fit`** — rationale names OQ-SC-02: no availability datum
  may be stored, and no event field would compare to one.
- **`student_program_affinity`** — rationale names OQ-SC-02 *and* that
  `event_manual_detail.audience` is unvalidated free text, so **both** sides are
  missing.

Weights are `0.0` rather than a guessed non-zero: a proposed weight is a number a
human proposed, and no human has.

**Explicitly rejected, not even declared: `student_region_fit`.** Two independent
blockers — no closed region vocabulary on the event side (free text ≤200 chars),
and no admitted student location datum. Declaring a factor whose input is missing
on *both* sides is a proposal nobody made.

**Explicitly rejected: any factor over `attendance_record`, `event_registration`,
or `student_speaker_feedback`.** `PROHIBITED_INPUTS` names
`unrelated_student_feedback`; OQ-CBA-053 is closed at "student ratings must not
influence matching"; and the owner's decision this session refuses
demand-weighting. §7 makes this executable rather than documentary.

## 5. Composition

In `scoring.py`, beside `rank_cba_candidates`, reusing every invariant —
`StageBScore` verbatim, `_ranked` (unscorables last), the deflation guard, the
`applied_total != 1.0` refusal, the unknown-dominates rule.

`StageBScore.subject_id` now holds an **event** id. **Do not rename the field:**
renaming churns `explanation.py`, `explanation_from_payload`, and every
stored-payload reader for a cosmetic gain. Document that it means "the thing being
ranked" and pin it.

The student's evidence is a property of the **run**, not of a candidate —
`CbaCandidateEvidence`'s stated rule that a per-candidate description "would let
two candidates in one pool be scored against different requests and still look
comparable". So the interest evidence is passed **once** to the ranking function
and folded in there, never copied onto every candidate by the caller.

**No semantic provider.** Set overlap over a closed vocabulary is lexical and
deterministic, so `ALLOW_LIVE_PROVIDERS` is irrelevant to this path and no
`topic_provider` argument exists. That is also why W3 can be synchronous.

**Weights are not per-unit configurable.** `CONFIGURABLE_FACTOR_KEYS` stays
CBA-only; one factor at 1.00 has nothing to tune and a settings surface would
imply otherwise. Pinned.

## 6. Delivery — a synchronous read, and how it stays accountable

**`GET /v1/units/{unit_id}/student/recommendations`**, roles `{student}`, its own
module `routers/student_recommendations.py`, one route.

The speaker path is durable because of what it *is*: a CP-SAT portfolio
optimization over a shared scarce resource (candidates are coupled), it is acted
upon irreversibly (invitations get sent), and it is slow and external (a solver
plus a provider). A student feed has none of those — per-candidate score then
sort, nothing irreversible follows, no solver, no provider. Writing one immutable
row per page view converts an accountability artifact into a request log and
degrades `match_run`'s meaning for the CBA path that depends on it.

**Pin in the response, not in a table.** A run is reproducible when
`(inputs, rulebook) → output` is deterministic and both are recoverable, so return
both: `registry_version`, `registry_hash`, `scoring_mode`, `scoring_mode_version`,
`formula_version`, `applied_weights`, `interest_vocabulary_version`,
`profile_version` (the input pin), `feed_window`, and an `inputs_hash` computed by
reusing `match_run.inputs_fingerprint` over the canonical tuple. Nothing is
written; accountability travels in the artifact the caller holds.

Determinism obligations: final tie-break is event id ascending, and the wildcard
is selected by an index derived from `inputs_hash` — no RNG state — with the seed
returned.

Storing "what did we show student X on 3 October" is a per-student behavioural
record and a D8 question. **OQ-SC-11. Safe default: do not store.**

### No numeric score anywhere in the response

Not even a `0.0–1.0` float. ADR-0016 Proposal 8 forbids a prominent overall
percentage and multiplying by 100; the strictest honest reading for a *student*
surface is to omit the number entirely, because a float in a payload is one
`Math.round(x*100)` away from the forbidden percentage in a client the backend
does not control. `rank` is the ordering, `matched_interests` is the evidence,
`reason` is the account. Pinned by a schema-walking contract test. This is a
deliberate narrowing relative to the coordinator match-run surface, which does
expose the composite.

### Bounded feed, and the wildcard declared rather than hidden

Domain constants in `smartmatch_domain/student_feed.py`, not the router:
`STUDENT_FEED_WINDOW_DAYS = 7`, `STUDENT_FEED_MAX_ITEMS = 5`,
`STUDENT_FEED_WILDCARD_SLOTS = 1`. The window is explicit in the payload
(closed-open, tz-aware) so "this week" is a stated interval, not an implication.
`time_precision = 'unresolved'` events are counted in `withheld_unresolved_date`,
never placed in a dated window. `truncated` uses the word
`StudentEventListResponse` already uses for the same fact.

The wildcard is a **named separate field**, never mixed into `items`, carrying
`selection_basis`, `pool_size` and `seed`. Three honesty requirements: it says in
the *payload* that it is a wildcard, so a client cannot quietly present it as a
recommendation; it is drawn **only from scorable events** outside the ranked list,
because promoting an unscorable event would launder an unknown into a
recommendation; and it is `null` — never a duplicate of a ranked item — when the
outside pool is empty.

### Absences, each distinguishable

- **Unscorable events** are counted with a worded caption, not listed and not
  dropped — `withheld_unpublished`'s discipline. They stay fully visible on
  `GET .../student/events`, which is the time-ordered catalog; a *ranking* has no
  honest place for an unrankable item, and the student already has a route showing
  it.
- **A student with no profile** gets `profile_state: "absent"`, `items: []`, and a
  worded caption. Never a fallback ranking, never a time-ordered list dressed as
  recommendations, never a popularity fallback — that would be a different
  measurement wearing this one's label.
- **While the registry status is `"proposed"`**, the route returns a worded
  refusal through the standard error envelope, **not** `200` with an empty list. A
  closed gate must never be indistinguishable from "nothing matched".

This is the only student read whose work is proportional to the catalog, so unlike
the others it carries a `RateLimit`.

## 7. Tests

| Level | Asserts |
|---|---|
| unit `test_factor_registry.py` | **Unchanged, zero lines edited.** That is W2a's entire pin |
| unit `test_student_factor_registry.py` | Weights sum to 1.0 ± 1e-9; keys match exactly; the eligibility factor carries zero Stage B weight and is absent from the scoring keys; the two unimplemented factors touch neither numerator nor denominator; and **`assert_registry_approved(STUDENT_REGISTRY)` raises** — the closed gate pinned as a positive assertion |
| unit `test_scoring_registry_isolation.py` | The two key sets are disjoint; no student key in either CBA model; `resolve_scoring_model("student-event-1", registry=CBA_REGISTRY)` raises; `PROHIBITED_INPUTS` is one shared frozenset still naming `unrelated_student_feedback` |
| unit `test_student_scoring_inputs_wiring.py` | **Import reachability** (`test_checkin_wiring.py`'s idiom): no student factor and no student scoring path imports `student_speaker_feedback`, `attendance`, or `event_registration`. OQ-CBA-053 as an executable control |
| unit `test_student_interest_overlap.py` | All six rows of §4's table — `value`, `zero_classification`, `state`, and `basis` passing `assert_one_sentence`; cross-version input raises at **construction**; the exact Jaccard values; and the anti-gaming property |
| unit `test_student_scoring.py` | Unknown dominates; weights never re-spread; deflation guard fires; unscorables sort last; identical inputs give identical order |
| golden | `tests/golden/` per mode, mirroring `test_cba_matching_golden.py`. **These are the artifact the owner reviews to flip the gate** |
| structural | `test_matching_fail_closed.py` flipped **in the commit that lands the route**: widen the forbidden-segment list (`recommendation`, `recommendations`, `ranking`, `suggest`) and add one exact literal path to a new allowlist, so a second recommendation path fails whether or not anyone regenerated the contract |
| contract | No numeric score: walk the response JSON schema and fail on any number/integer property matching `score|value|percent|match|fit|rating|confidence` (`rank` allowed by name). Every `reason` passes `assert_one_sentence`. Wildcard distinct, never duplicated, never unscorable. Two calls over an unchanged catalog give the same `inputs_hash` and order. Proposed status → worded refusal, not `200` |

## 8. What W2 does not do

- No speaker name on any card — OQ-CBA-064 and OQ-CBA-051; see the parent plan's
  W5 row.
- No collaborative filtering. "Students like you also attended" is a claim built
  from other named students' behaviour and is squarely D8's.
- No stored skip — **OQ-SC-09**, safe default session-only.
- No popularity fallback for an unrankable feed.
