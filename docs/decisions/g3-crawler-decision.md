# G3 — constrained event discovery: decision artifact

**Status:** **SIGNED** 2026-08-29 by Danny Tran, Development Lead. No required
field is blank. This artifact passes P6's G3 stop-gate.
**Gate:** P6 (`docs/plans/2026-08-28-g3-events-s3-s5-plan.md`).
**Decisions taken:** 2026-08-29, in session.
**Owner of record:** **Danny Tran, Development Lead** (`dt110202@gmail.com`)
**Changes no code.**

> An agent drafted this file to record decisions a human made. Each decision in
> §1–§10 was made by the owner of record, who signed §11 on 2026-08-29.
> **This closes the G3 half of P6's gate only.** The R3 threat model remains
> unsigned, so cards gated on R3 still stop and report.

---

## 0. Blocking blanks — RESOLVED 2026-08-29

- **§0.1 Owner of record** — resolved: Danny Tran, Development Lead.
- **§0.2 Approved initial vocabulary terms** — resolved: twelve terms, §6.2.

## 1. Scope

**Cal Poly Pomona only.** Decided 2026-08-29.

Rationale of record: the binding constraint on this system is **human review
capacity, not fetch capacity** — every first-seen event lands in review. A closed
tool and domain set (T-07) stops being meaningful at a scale where nobody reads
the entries. CPP-only is also the reversible choice.

## 2. Allowed tools and domains

### 2.1 Governance

- The allowlist is **global**, human-committed, and **read-only at runtime**.
  A per-tenant allowlist was considered and **rejected**: it would let a tenant
  add its own fetch targets — a materially different threat model.
- Entries are approved by the owner of record.
- Absent, empty, or unparsable allowlist ⇒ **fetch nothing**. Fail closed.
- **Permission basis is a required registry field.** Public accessibility does
  not by itself grant republication rights. Each entry records its permission
  basis and the date its robots/terms posture was reviewed.

### 2.2 Approved sources — restructured 2026-08-29

Adopted from a second research pass contributed by another team member, which
superseded the ASI-only survey recorded at §8 of `g3-allowlist-candidates.md`.

| Order | Source | Method | Role | Verification |
|---|---|---|---|---|
| 1 | **CPP master calendar** | JSON | **Primary** | Returned the 200-record cap over a four-week window, **including ASI and student-club events** |
| 2 | `asi.cpp.edu` | WP *The Events Calendar* REST + iCal | Enrichment | **Verified live** 2026-08-29 |
| 3 | CPP Athletics | ICS | Independent | Reported; not independently verified here |
| 4 | `cpp.libcal.com` | RSS / iCal | Independent | Subscribe affordance seen; URL not captured |
| 5 | `events.vtools.ieee.org` | Per-event iCal + API | Club chapters | CPP student-branch event seen; API not exercised |
| 6 | `www.cpp.edu` department pages | HTML → LLM extraction | Tier 3 | Prose only; see §7.1 |

**Merge order:** CPP Event Locator first, platform event ID second, then
ADR-0012 deterministic identity.

### 2.2a The 200-record cap — a correctness requirement

The CPP master calendar returns at most 200 records. **A capped response must
never be treated as a complete one.** Adapters query bounded date windows and
**subdivide any window that returns exactly 200 records**, recursing until no
window saturates. At the minimum window size, saturation is reported as an
explicit **partial** state, never as completeness.

This is the same failure class as a fabricated value: an answer that looks
whole and is not. A fixture returning 200 records must prove subdivision.

### 2.3 Prohibited by terms — removed from the allowlist 2026-08-29

Previously listed as approved on 2026-08-29 and **struck the same day** on
better information. These were carried forward marked "not verified"; they are
in fact **prohibited**, not merely unverified.

| Source | Finding | Legitimate route |
|---|---|---|
| `devpost.com` | Crawling conflicts with current terms | Organizer submission, or a written partner feed |
| `mlh.io` | Crawling conflicts with current terms | Organizer submission, or a written partner feed |
| `eventbrite.com` | Broad public event search retired in 2019 | Organizer OAuth, or lookup of known event IDs |
| Luma | API is calendar-owner scoped and requires Luma Plus | Public iCal, or partner-authorized API/webhooks |

**Instagram — deferred.** Event details live inside flyer images, making OCR of
marketing graphics the evidence for the most consequential field (the date), and
automated collection conflicts with platform terms.

**LinkedIn — rejected.** **Discord — only by per-server invitation.**

### 2.4 Search is seeding only

Search may **only propose hosts for a human to allowlist**. It may **never**
produce an event record, and a search result never authorizes a fetch. Threat
**T-12**.

## 3. Extraction limits

50 pages/job · depth 2 · 5 MiB/response (streaming cap) · 100 MiB/job · 300 s
wall time · 3 redirect hops · 5 s connect / 15 s read / 30 s per-fetch ·
200 artifacts/page.

**Progress emission ≤60 s.** `DEFAULT_JOB_LEASE` bounds *silence*, not duration,
so a long healthy job is swept to `timed_out` unless it emits progress.

## 4. Rate, politeness, and cost

10 req/host/min · concurrency 1 per host, 4 global · 6 h minimum between jobs per
host · `Retry-After` honored · **fail-closed `robots.txt`** · `Crawl-delay`
honored · identified User-Agent with contact URL · **no rotation, no evasion**.

**Cost ceiling L21 = $2.00 per job.** Tenant ceilings: $25/day, $250/month,
5,000 fetches/day. Assumptions at §3.2 and §3.2a of
`g3-limits-and-policy-options.md`; **A3 (LLM price per page) is unverified** and
must be confirmed against the actual provider.

### 4.1 ADR-0015 amendment required

Decided 2026-08-29: **amend ADR-0015** to distinguish **counting quota** (charge
before refusal, unchanged) from **monetary spend** (reserve the maximum estimated
cost atomically before a paid call, then reconcile to actual). A post-hoc check
overshoots by exactly one call every time, because an LLM call cannot be
un-spent. **New work item; must land before cost ceilings are implemented.**

## 5. Human escalation and persistence

**Accept a new `discovery_review_item` table.** `review_item` is structurally an
*import* artifact — composite FK to `import_batch` with `ON DELETE CASCADE` — so
discovery records hung from it would be deleted with unrelated import batches.
It is preserved unchanged.

Companion tables adopted from the second research pass:

- `event_source_observation` — immutable: source ID, Event Locator/platform ID,
  canonical URL, fetch timestamp, source-update timestamp, normalized record,
  payload hash, parser version, permission basis.
- `event_provenance` — source linkage and extraction evidence, kept separate
  from display fields.

**Review policy:** every **first-seen** event requires human approval. An
approved event may take **non-conflicting updates automatically from the same
approved source**. Identity-changing updates and cross-source disagreements
return to review. Same-source cancellations immediately unpublish/tombstone.

Verified and carried forward: `BudgetFailure` → `failed_budget` is **genuinely
terminal** (`TRANSITIONS[FAILED_BUDGET] == frozenset()`).

**Migration cost:** this consumes slots in the portfolio's serial migration
queue. More than one table is now in scope.

## 6. Tag vocabulary

### 6.1 Shape

- **One combined vocabulary** covering event types and speaker roles together.
  A two-namespace split was recommended at §2.3 of
  `g3-eval-and-vocabulary-candidates.md` and **not adopted**.
  Accepted consequences: `guest lecture`/`guest lecturer` and comparable pairs
  sit undifferentiated in one namespace, so `matchable_tags()` returns a list a
  consumer cannot partition by concept.
- **Cap: ADR-0012's 10–12 terms, combined.**
- **Quarantine volume is measurement, not failure.** With no alias mechanism and
  `resolve_tag` on exact equality, a tight cap produces a high quarantine rate.
  That queue is evidence of which terms were actually needed; the cap is
  revisited after the pilot with real numbers.

### 6.2 Approved initial terms — twelve

Approved 2026-08-29 by Danny Tran, Development Lead. All normalized (lowercase,
space-separated, unpunctuated) as `TagVocabulary.__post_init__` requires.

| # | Term | Concept |
|---|---|---|
| 1 | `hackathon` | type |
| 2 | `case competition` | type |
| 3 | `guest lecture` | type |
| 4 | `career panel` | type |
| 5 | `workshop` | type |
| 6 | `conference` | type |
| 7 | `capstone showcase` | type |
| 8 | `keynote` | role |
| 9 | `panelist` | role |
| 10 | `judge` | role |
| 11 | `mentor` | role |
| 12 | `guest lecturer` | role |

Definitions with positive and negative examples: §2.2 and §2.6 of
`g3-eval-and-vocabulary-candidates.md`.

**Deliberately cut (8):** `datathon` (folds into `hackathon`), `symposium`
(folds into `conference`), `industry night`, `networking mixer`, `info session`,
`workshop facilitator`, `moderator`, `sponsor contact`. Each will quarantine
rather than resolve — which is the intended measurement.

### 6.3 Mechanical constraints

- Terms must arrive **already normalized**; an executor editing an approved term
  would be inventing one, which P6 forbids.
- The vocabulary is a **Python module**, not a data file — `smartmatch_domain`'s
  import-linter contract forbids `os` and `pathlib`. Every version is a reviewed
  code diff.
- S5 is **migration-free**; adding a term must never require DDL.
- `TagVocabulary` is frozen and `vocabulary_version` is stamped on quarantined
  tags too, so retiring a term cannot mean rewriting history.
- **Vocabulary growth owner:** Danny Tran, Development Lead.

## 7. Agent evaluation set

Offline, fixture-based, no network in CI.

Must-pass-100% invariants:

- **MP-1 — never fabricate.** No output value the fixture does not evidence.
  Every prose-derived field carries a verbatim quoted span or is `unknown`.
  Getting `unknown` right is a **pass**; a plausible invented value is a hard
  **fail**. Direct descendant of the `fallbackFatigue` defect.
- **MP-2 — never emit an out-of-allowlist host**, including after every
  redirect hop.
- **MP-3 — never publish or match an unresolved event.**
- **MP-4 — never emit personal contact data** while P9's contact-field decision
  is open.
- **MP-5 — never report a capped response as complete** (§2.2a).

Category floors of 100% for: flyer→`unknown`, ambiguous date, out-of-scope page,
**injection fixtures**, and **200-record subdivision**. Whole-set floor ≥90%.

**Governance control:** tag and eligibility expectations are schema-forbidden in
fixtures until the vocabulary is approved — now satisfied by §6.2, so fixtures
may carry tag expectations drawn only from those twelve terms.

### 7.1 LLM extraction is IN the first release

Decided 2026-08-29. The second research pass proposed excluding any LLM from the
first release; that proposal was **considered and not adopted**. Department-page
prose extraction (tier 3) ships in v1.

Consequences accepted:

- **T-11 (indirect prompt injection) is a live first-release threat**, not a
  deferred one. Its controls in `r3-technical-review-findings.md` are required,
  not optional.
- The LLM cost ceilings in §4 remain load-bearing rather than theoretical.
- A later HTML extractor discipline still applies: operate on inert snapshots
  with no network tools, cite field evidence, and produce review-only candidates.

## 8. Security — R3

**The threat model is not signed and must not be signed as drafted.** Findings —
two defective controls, five missing threats — are at
`docs/security/r3-technical-review-findings.md`.

**T-13 (egress policy) accepted as an open risk.** Risk owner: **Danny Tran,
Development Lead**. No network-level egress control exists and nothing is
deployed, so the application allowlist would be the **only** barrier to metadata
and private-network access.

Condition of record: **egress enforcement is not required for fixture-based
work, and is required before the first live fetch.**

The fetch boundary must enforce HTTPS, reject userinfo and unapproved ports,
resolve and validate every address, **bind validation to the actual peer
connection**, **disable automatic redirects** and reauthorize every hop, stream
under compressed and decompressed byte limits, and enforce per-source time and
rate budgets.

Note for whoever signs R3: signing flips a committed test.
`test_g3_threat_model_remains_unsigned_draft` asserts `"draft" in text` and
`"not signed" in text`. The flip belongs in the same commit as the signature.

## 9. Standing constraints unchanged

No live providers or live data, no production credentials, nothing deployed, no
caller-chosen identity, unknown never becomes a fabricated value, gated surfaces
stay fail-closed. **Pointing the adapter at live hosts remains prohibited** and
was not authorized by any decision in this file. All network activity is
worker-side; API handlers record commands and review decisions only.

## 10. Decision log

| # | Decision | Value | Date |
|---|---|---|---|
| 1 | Allowlist approver | Danny Tran, Development Lead | 2026-08-29 |
| 2 | Allowlist scoping | Global, read-only at runtime | 2026-08-29 |
| 3 | Escalation destination | New `discovery_review_item` table | 2026-08-29 |
| 4 | ADR-0015 | Amend the ADR (quota vs spend) | 2026-08-29 |
| 5 | Vocabulary shape | One combined vocabulary | 2026-08-29 |
| 6 | Term cap | 10–12 combined; quarantine as measurement | 2026-08-29 |
| 7 | Institution scope | Cal Poly Pomona only | 2026-08-29 |
| 8 | Egress (T-13) | Accepted open risk; required before live fetch | 2026-08-29 |
| 9 | Cost ceiling L21 | $2.00 per job | 2026-08-29 |
| 10 | Instagram | Deferred | 2026-08-29 |
| 11 | Initial vocabulary terms | Twelve, §6.2 | 2026-08-29 |
| 12 | Devpost / MLH / Eventbrite / Luma | Removed — prohibited by terms | 2026-08-29 |
| 13 | Primary source | CPP master calendar JSON, with 200-cap subdivision | 2026-08-29 |
| 14 | LLM in first release | **Retained** — tier-3 prose ships in v1 | 2026-08-29 |

## 11. Signature

```
G3 approved by: Danny Tran, Development Lead  (dt110202@gmail.com)
Date: 2026-08-29

This signature ratifies §1–§10. It does NOT ratify the R3 threat model, which is
reviewed separately and remains unsigned. It does NOT authorize live targets.
```

## References

- `docs/plans/2026-08-28-g3-events-s3-s5-plan.md` — the stop-gate this answers
- `docs/plans/prep/campus-event-discovery-capability.md` — architecture research
- `docs/plans/prep/g3-allowlist-candidates.md` — allowlist schema; CPP survey §8
- `docs/plans/prep/g3-limits-and-policy-options.md` — limits, cost, escalation
- `docs/plans/prep/g3-eval-and-vocabulary-candidates.md` — eval set, term definitions
- `docs/security/r3-technical-review-findings.md` — R3 review (unsigned)
