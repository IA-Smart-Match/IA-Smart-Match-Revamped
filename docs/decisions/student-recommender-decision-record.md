# Student→event recommender: product decision record (draft)

**Status:** **DRAFT — 2026-09-14. Closes nothing.** Every decision below is a
proposal put to a named owner; until the owner's dated, attributed decision lands
in the canonical register, the register's safe default stays in force.
**Gate:** Student-engagement program slice 6 ("Supporting interest profile and
event ranking", `docs/plans/2026-09-14-student-engagement-program-plan.md` §3),
entry gates OQ-SC-02, OQ-SE-01, OQ-SE-02.
**Formal deciders:** Student-engagement program owner (product choices);
scoring-registry owner (registry, factors, weights, golden cases); records/privacy
owner (any stored student datum: OQ-SC-02, OQ-SC-09, OQ-SC-11, OQ-SE-19, OQ-SE-21,
OQ-SE-22).
**Architecture:** [ADR-0018](../architecture/decisions/ADR-0018-staged-student-event-recommender.md) (Proposed).
**Contracts:** [`docs/architecture/student-recommender-contracts.md`](../architecture/student-recommender-contracts.md).
**Register:** [`docs/plans/open-questions/student-engagement-deferred.md`](../plans/open-questions/student-engagement-deferred.md).

This record does not build anything. It puts the *product* questions of the
student recommender to their owners in the D6 record's form — one decision per
section, the safe default stated, the closure evidence named — so that ADR-0018
can move from Proposed to Accepted on an owner's signature rather than on a
plan's momentum.

---

## 1. What the feed optimizes

**Proposal:** the student feed optimizes the stakeholder-named outcome —
*registrations per active student and registration→attendance conversion* — and
nothing attention-shaped. Time in feed, scroll depth, session count, and any
engagement proxy are not objectives, not tie-breaks, and not model labels.

- Source: `docs/plans/research/2026-09-13-engagement-feed-research.md` ("Not
  time in feed, not scroll depth, not sessions"); program plan §1 ("Interest-based
  recommendation supports that journey; it is not the program spine").
- Consequence for the five families (§2): a family is judged by whether it can
  rank toward *that* outcome from *permitted* data, not by benchmark accuracy.
- **Safe default until decided:** same as the proposal; nothing else is
  buildable without contradicting the register.
- **Owner:** program owner. **Closure evidence:** a dated line in the register
  naming the objective and the two metric names it maps to under OQ-SE-04.

## 2. Which recommender families, in what order

Five families were evaluated against the codebase (`factor_registry.py`,
`scoring.py`, `explanation.py`, `routers/student_events.py`, migrations
`0017`/`0026`/`0009`) and the register.

| Rank | Family | Verdict | Waits on |
|---|---|---|---|
| 1 | **Content-based ranking** — Jaccard between declared interests and mapped event tags over the shared G3 vocabulary (`VOCABULARY_VERSION = "g3-2026-08-29"`) | **Build first.** Works for a brand-new student with zero history; every input is already governed (ADR-0012 closed vocabulary); no behavioural datum touched | OQ-SC-02 (profile may exist), OQ-SE-01 (registry approved) |
| 2 | **Learning-to-rank** — LambdaMART via `xgboost` `rank:ndcg`, CPU | **Architect toward; do not ship first.** Replaces Stage B behind the same protocol; can be built and offline-evaluated on authored gold sets today; cannot be trained on real outcomes or promoted until labels are permitted | OQ-SE-19 (labels), OQ-SE-20 (promotion/rollback owner) |
| 3 | **Hybrid collaborative + metadata** — LightFM-style latent affinity | **Later, as one feature of #2.** Needs a student×event interaction matrix, which is a per-student behavioural record; pure CF is rejected for cold start and for D8 ("students like you") | OQ-SE-21 |
| 4 | **Multi-stakeholder constrained re-rank** — bounded feed, diversity cap, declared wildcard, governance counts, later capacity | **Always on.** Stage C wraps #1 and #2 from the first version; needs no behavioural data | OQ-SE-02 (wildcard contract) |
| 5 | **Contextual bandit** — LinUCB / VW `cb_explore_adf` | **Session-only now; learned policy much later.** In-session adaptation is caller-supplied exclusions with nothing stored; a learned exploration policy needs logged decisions with propensities | OQ-SC-09 (skip storage), OQ-SE-22 (decision logs) |

**Rejected outright:** extending the CBA registry or adding a second weight
system (W2 §1; matching-expansion brief "Option 1"); neural two-tower / deep
retrieval; popularity or time-ordered fallback presented as recommendations;
endless feed mechanics; inferring interests from registrations.

- **Owner:** program owner with the scoring-registry owner. **Closure evidence:**
  ADR-0018 moved to Accepted with this table's order confirmed or amended.

## 3. Resource envelope

No GPU at any phase. Recorded so procurement is not opened for it.

| Phase | API | Worker (training) | PostgreSQL | GPU |
|---|---|---|---|---|
| 1 — content + policy (families 1, 4) | 2 vCPU / 4 GB (existing) | none | existing + two small tables | none |
| 2 — learned ranker in shadow (family 2) | 2–4 vCPU / 4–8 GB | 4 vCPU / 8 GB, batch job | +50–100 GB SSD if labels are permitted | none |
| 3 — collaborative feature, bandit logs (families 3, 5) | 4 vCPU / 8 GB | 4–8 vCPU / 8–16 GB | 100–500 GB SSD, dominated by decision logs | still none |

The recommendation path adds no service, no vector store, no external provider.

## 4. Decisions put to owners (each is one register row)

### 4.1 OQ-SC-02 — may a student profile be stored? (existing row)

**Proposal:** yes, exactly W1's shape — `student_profile` (1:1 `user_account`,
`modality_preference` NOT NULL with no server default) and
`student_profile_interest` (closed vocabulary terms, `vocabulary_version`),
student-owned `GET`/`PUT`/`DELETE`, no coordinator/host/admin read of an
individual profile, no free text, no `program_of_study` column.
**Safe default:** no profile table, no ranking. **Owner:** program + records/privacy.

### 4.2 OQ-SE-01 — approve `STUDENT_REGISTRY` 0.1.0 (existing row)

**Proposal:** approve as W2 §4: `student_interest_overlap` (SUITABILITY, 1.00,
Jaccard), `student_modality_eligibility` (ELIGIBILITY, 0.0), two declared-unbuilt
factors at 0.0, mode `student-event-1`, formula `1.0.0`, and the golden case set
in `tests/golden/student/`. Promotion flips `STUDENT_REGISTRY_STATUS` to
`"approved"` and stamps approver and date, exactly as `REGISTRY_APPROVER` /
`REGISTRY_APPROVED_ON` do for CBA.
**Safe default:** `proposed`; the route refuses with a worded error.
**Owner:** program owner + scoring-registry owner.

### 4.3 OQ-SE-02 — wildcard contract (existing row)

**Proposal:** one wildcard, a separate named field, drawn only from scorable
events outside the ranked list, `null` when the pool is empty, selected by an
index derived from `inputs_hash`, seed returned; no backend toggle.
**Safe default:** identical. **Owner:** program + web/API owners.

### 4.4 OQ-SC-12 — untagged eligible events (existing row)

**Proposal:** keep `unknown`; report `withheld_untagged` in the payload; make tag
coverage a coordinator-visible number on the existing review surface so the
fix is tagging, not a neutral. **Safe default:** identical. **Owner:** program owner.

### 4.5 OQ-SC-09 and OQ-SC-11 — skips and exposure (existing rows)

**Proposal:** unchanged safe defaults. Session adaptation is implemented from a
caller-supplied `exclude_event_ids` parameter that the server never stores;
exposure is pinned *in the response* (`inputs_hash`, versions), not in a table.
**Owner:** program + records/privacy.

### 4.6 OQ-SE-19 — may a student's own registration/attendance become a *training label*? (new)

**Question:** ADR-0018 D4 distinguishes reading a behavioural datum at request
time (barred by `PROHIBITED_INPUTS` and OQ-CBA-053) from using it, after the
fact, as a label to fit a ranking model. Is the second use permitted, for which
rows (`event_registration.status = 'registered'`, `attendance_record`), with what
retention, what deletion semantics when a profile is deleted, and is the label
ever joined to anything beyond `(subject_id, event_id, feature vector at
exposure time)`?
**Safe default:** no. The learned ranker trains on authored gold sets and
synthetic pilot data only, and is never promoted.
**Owner:** records/privacy + program owner + scoring-registry owner.
**Closure evidence:** field classification, retention/deletion decision, a
`training_example` schema, and tests that a deleted profile's rows are purged.

### 4.7 OQ-SE-20 — who promotes a learned ranker, and how is it rolled back? (new)

**Question:** which owner signs a `formula_version = "ltr-x.y.z"` promotion, on
what evidence (offline NDCG@5 vs the gold set; shadow agreement rate vs
`content-1`; a golden-case run), and who owns rollback to `content-1`?
**Safe default:** no promotion; `LearnedRanker` may exist only in shadow and
only in tests.
**Owner:** scoring-registry owner + program owner.
**Closure evidence:** a signed promotion artifact naming `model_artifact_hash`,
the evaluation numbers, and the rollback test.

### 4.8 OQ-SE-21 — may a student×event interaction matrix exist? (new)

**Question:** collaborative affinity needs, per student, which events they
interacted with. Is that matrix permitted, from which signals (registration
only? attendance? never skips?), at what minimum density, and is it ever
readable outside the training job?
**Safe default:** no matrix; no collaborative feature.
**Owner:** records/privacy + program owner.

### 4.9 OQ-SE-22 — may recommendation decisions be logged with propensities? (new)

**Question:** a learned exploration policy needs `(context, actions, chosen,
propensity, reward, policy_version, timestamp)` rows — a per-student
behavioural record of what was shown and what happened. Is that log permitted,
with what retention, and is it the same decision as OQ-SC-11 or a stricter one?
**Safe default:** no log; exploration is the one declared wildcard.
**Owner:** records/privacy + program owner + security owner.

## 5. What this record does not decide

- It does not reorder the program plan: registration QR (slice 1) and host
  review (slices 2–3) still precede ranking (slice 6).
- It does not touch the CBA registry, ADR-0016's weights, or `match_run`.
- It does not license a migration number; schema-bearing slices use
  current-head-plus-one at merge readiness.
- It does not add `xgboost` or any ML dependency to `requirements/*.in`; that
  is a slice-6 phase-2 change that lands with the shadow evaluator, behind
  OQ-SE-20's safe default.
