# OQ-SE-01 / OQ-SE-02 — student scoring registry and the wildcard contract

> **Decision packet — docs only. Authorizes no implementation. The register
> row(s) named here remain OPEN.**

## Decision needed

Whether to approve the distinct student scoring registry (OQ-SE-01) and the
declared wildcard/exploration contract (OQ-SE-02), which together gate every
student-facing ranked feed.

## Owner(s) of the decision

- **OQ-SE-01: Program owner + scoring registry owner** —
  [`../plans/open-questions/student-engagement-deferred.md`](../plans/open-questions/student-engagement-deferred.md).
  The scoring-registry owner is named elsewhere in the same register, at
  OQ-SE-20: "Scoring-registry owner (BrooklynD23, named 2026-09-16)". The
  program owner is named by role only in these two rows; the roster records
  **Danny Tran (@BrooklynD23)** as program owner
  ([`../decisions/owner-roster.md`](../decisions/owner-roster.md) row 2).
- **OQ-SE-02: Program owner + web/API owners** — same register. The web and API
  owners are not named as individuals in it.

## Current safe default in force

[`../plans/open-questions/student-engagement-deferred.md`](../plans/open-questions/student-engagement-deferred.md),
both rows **OPEN — tentative-development**.

**OQ-SE-01** — "Approve the distinct student scoring registry, factors, weights,
modes, version, golden cases, and promotion/rollback owner?" Safe default:

> `STUDENT_REGISTRY_VERSION` remains proposed and scoring fails closed.

**OQ-SE-02** — "Approve the wildcard contract — one declared draw in the first
feed plus student-initiated continuation draws (≤ `STUDENT_FEED_WILDCARD_BATCH`,
without replacement, ending at catalog exhaustion) — and whether any
operator/backend toggle exists?" Safe default:

> At most one separately labeled exploration item; no backend toggle.

[`../architecture/decisions/ADR-0024-staged-student-event-recommender.md`](../architecture/decisions/ADR-0024-staged-student-event-recommender.md)
D2 states the same gate from the architecture side:

> `STUDENT_REGISTRY` ships with `status = "proposed"` and fails closed until
> OQ-SE-01 closes. Its V1 contents are exactly W2 §4: `student_interest_overlap`
> (SUITABILITY, 1.00, Jaccard over the shared G3 vocabulary, six evidence rows),
> `student_modality_eligibility` (ELIGIBILITY, 0.0), and two declared-unbuilt
> factors at `proposed_weight = 0.0`.

D7 fixes the shape the wildcard would take if approved: "one draw in the first
feed, then student-initiated continuation draws of up to
`STUDENT_FEED_WILDCARD_BATCH` from the scorable pool outside the ranked list,
without replacement, `null`/empty when the pool is exhausted, so a student can
browse every scorable event without the feed ever padding". D8 binds the output
regardless of registry status: "No numeric score reaches a student surface, in
any version."

[`../architecture/decisions/ADR-0026-student-program-and-student-centric-classroom.md`](../architecture/decisions/ADR-0026-student-program-and-student-centric-classroom.md)
is **Proposed**, dated 17 September 2026, and its D3 states "Gates fail closed:
an unresolved gate means the slice stops at a plan, not code."

Note, as a verifiable fact rather than a decision: at this commit there is no
student-registry module under
`python/smartmatch_domain/smartmatch_domain/`; the CBA registry
(`factor_registry.py`) is a separate registry and is not this one.

**No conflict found** between the register, ADR-0024, and
[`../plans/README.md`](../plans/README.md), which lists the student→event
recommender as "gated on OQ-SC-02, OQ-SE-01, OQ-SE-02".

## Options

Neutral; each has consequences. This packet selects none, and proposes no
factor, weight, version string, or batch size.

**For OQ-SE-01:**

1. **Approve the registry as ADR-0024 D2 describes it.** *Consequence:*
   `STUDENT_REGISTRY_VERSION` can leave `proposed` once the closure evidence
   lands; ranking becomes buildable work (not authorized here); the
   promotion/rollback owner must be named in the same artifact.
2. **Approve a different factor/weight set.** *Consequence:* ADR-0024 D2's V1
   contents are stated as "exactly W2 §4", so a different set is an ADR
   amendment as well as a register closure, per that ADR's amendment
   discipline.
3. **Leave it proposed.** *Consequence:* student ranking stays fail-closed;
   OQ-SE-19/-20/-21/-22 (learned ranking, labels, collaborative signal,
   exploration logging) remain unreachable because they all depend on a ranker
   being served.

**For OQ-SE-02:**

1. **Approve the declared wildcard contract with no operator toggle**, matching
   the safe default's shape. *Consequence:* exploration is exactly what
   ADR-0024 D6 describes; no per-unit configuration surface exists.
2. **Approve it with an operator/backend toggle.** *Consequence:* the row
   requires "toggle authorization if approved" as closure evidence — an
   authorization decision about who may flip it, not just a flag.
3. **Approve a different contract shape** (for example a different number of
   declared draws, or with replacement). *Consequence:* ADR-0024 D7's ordered
   Stage C rules and its constants would need amendment; D7's guarantee that the
   feed "never pads" is the property at stake.
4. **Leave it open.** *Consequence:* "At most one separately labeled exploration
   item; no backend toggle" continues to bind.

## Evidence needed to close

From [`../plans/open-questions/student-engagement-deferred.md`](../plans/open-questions/student-engagement-deferred.md):

- **OQ-SE-01** — "Signed registry artifact/ADR, golden cases, promotion and
  rollback tests".
- **OQ-SE-02** — "Payload schema, selection golden cases, UI copy, toggle
  authorization if approved".

Register-wide closure discipline, from the same file:

> Closure requires an attributed, dated decision artifact plus the evidence
> named in the row.

> Do not reuse an OQ ID for a different decision. In particular, OQ-SC-09 does
> not approve `STUDENT_REGISTRY_VERSION`.

> Do not close a student row by implication from an OQ-CBA or OQ-E row. Record
> the cross-reference and the separate student-engagement disposition.

> Safe defaults remain active until closure evidence lands. A plan, prototype,
> feature flag, or unwired implementation is not closure evidence.

Note the register's related, separate gate: **OQ-SC-02** ("What may a student be
asked and what may be stored, including program of study?") carries the safe
default "No student profile persistence or personalized ranking" and blocks
"Interest profile, ranking, demand". Closing OQ-SE-01 and -02 does not close it.

## What stays blocked until closure

- **Student ranking** — OQ-SE-01's blocked slice.
- **Wildcard/exploration behavior** — OQ-SE-02's blocked slice.
- Per [`../plans/README.md`](../plans/README.md), the whole student→event
  recommender slice, listed as "gated on OQ-SC-02, OQ-SE-01, OQ-SE-02".
- Per [ADR-0024](../architecture/decisions/ADR-0024-staged-student-event-recommender.md)
  D4 condition 3, until **OQ-SE-19** closes a learned ranker "may be trained and
  evaluated **only** on authored gold sets and synthetic pilot data … and never
  promoted"; per D4 condition 4 and **OQ-SE-20**, promotion needs a signed
  artifact naming `model_artifact_hash` and a rollback owner.
- Per [ADR-0026](../architecture/decisions/ADR-0026-student-program-and-student-centric-classroom.md)
  D3: "an unresolved gate means the slice stops at a plan, not code."

## Source links

- [`../plans/open-questions/student-engagement-deferred.md`](../plans/open-questions/student-engagement-deferred.md) — OQ-SE-01, OQ-SE-02, OQ-SC-02, OQ-SE-19/-20, closure discipline
- [`../architecture/decisions/ADR-0024-staged-student-event-recommender.md`](../architecture/decisions/ADR-0024-staged-student-event-recommender.md) — D1–D8, amendment discipline
- [`../architecture/decisions/ADR-0026-student-program-and-student-centric-classroom.md`](../architecture/decisions/ADR-0026-student-program-and-student-centric-classroom.md) — D2, D3, D5 (Proposed)
- [`../architecture/decisions/ADR-0011-accountable-numbers.md`](../architecture/decisions/ADR-0011-accountable-numbers.md) — unknown is not zero
- [`../architecture/student-recommender-contracts.md`](../architecture/student-recommender-contracts.md) — feature registry and payload contracts
- [`../decisions/student-recommender-decision-record.md`](../decisions/student-recommender-decision-record.md) — decision record (draft)
- [`../plans/2026-09-13-w2-student-event-ranking-plan.md`](../plans/2026-09-13-w2-student-event-ranking-plan.md) — W2 ranking plan
- [`../plans/2026-09-14-student-engagement-program-plan.md`](../plans/2026-09-14-student-engagement-program-plan.md) — program plan
- [`../plans/README.md`](../plans/README.md) — recommender gating
- [`../decisions/owner-roster.md`](../decisions/owner-roster.md) — program owner
