# 31 August 2026 ratification and implementation report — R0

**Date:** 31 August 2026 · **Slice:** R0 (ratification and blocker report;
documentation only) · **Session approver:** Danny Tran (`dt110202@gmail.com`)
**Source design:**
`docs/superpowers/specs/2026-08-31-ratification-and-feature-delivery-design.md`
**Source handoff:** `docs/plans/prep/human-decisions-handoff-831.md`
(HANDOFF ONLY; committed unchanged in authority status alongside this
report)
**Ratification index:** `docs/decisions/2026-08-31-session-ratification.md`
**This report decides nothing new.** It reports what R0 formally recorded,
what remains blocked and why, and the ordered continuation plan. **No push,
pull request, merge, deployment, live-provider call, production credential,
or production-readiness claim is made or implied here.**

---

## 1. Review-friendly change summary

R0 is one documentation-only commit. It does not touch `python/`, `services/`,
`apps/`, `db/`, or `tests/`. What changed:

- **Committed** the previously-untracked
  `docs/plans/prep/human-decisions-handoff-831.md`, unchanged in authority
  status, with a forward link to the new ratification record added at its
  top.
- **Created** `docs/decisions/2026-08-31-session-ratification.md`, the dated
  index of every session decision, its status under the four-status model,
  and links to every formal artifact.
- **Ratified** ADR-0015 Amendment A1 as session policy — the only item
  promoted to a fully ratified technical implementation gate — in
  `docs/architecture/decisions/ADR-0015-charge-quota-before-refusal.md` and
  `docs/architecture/decisions/README.md`, in the same commit as this report,
  per `tests/unit/test_adr_index.py::test_an_amended_adr_is_marked_amended_in_the_index`.
  Live-provider estimate A3, credentials, and production ceilings are
  explicitly **not** ratified and remain external.
- **Updated** the P1, P2, P7, P8, and P9 (both gates) decision artifacts to
  the strongest status their explicit answers support, no stronger, and
  **created** two decision artifacts that did not previously exist
  (`docs/decisions/p8-opportunities-decision-draft.md` and
  `docs/decisions/p9-gate-a-board-role-decision-draft.md`). R3's status is
  recorded in the ratification index only — its own gate artifact
  (`docs/security/crawler-threat-model-draft.md`) is **not** edited, because
  its unsigned-draft signature block is a pinned test boundary that only a
  human signing pass may flip.
- **Synchronized** `docs/plans/2026-08-28-plan-portfolio-index.md`,
  `docs/plans/prep/blocked-work-register-830.md`, and
  `docs/plans/status-report-830.md` to point at the same authoritative
  blocker classification and owner recorded in the ratification index,
  without rewriting any of their historical, dated findings.
- **Marked** three existing plans (`2026-08-28-g3-events-s3-s5-plan.md`,
  `2026-08-28-d6-rewards-s8-s9-plan.md`, `2026-08-28-pilot-columns-plan.md`)
  explicitly amended/superseded for scope in their own headers, with the
  replacement relationship recorded here and in the ratification index.
- **This report**, the required implementation-report deliverable.

## 2. Formal updates — the complete list

| # | File | What changed |
|---|---|---|
| 1 | `docs/plans/prep/human-decisions-handoff-831.md` | Committed unchanged (except a forward-link line); newly tracked |
| 2 | `docs/decisions/2026-08-31-session-ratification.md` | Created — dated decision index |
| 3 | `docs/architecture/decisions/ADR-0015-charge-quota-before-refusal.md` | Amendment A1 marked ratified (session policy); A3/credentials/ceilings marked explicitly external |
| 4 | `docs/architecture/decisions/README.md` | ADR-0015 row's `Amended` column filled, dated 31 August 2026 |
| 5 | `docs/decisions/metrics-authorization-decision-draft.md` (P1) | §0 added: aggregate-visibility hierarchy recorded as direction; unanswered questions enumerated |
| 6 | `docs/decisions/a1b-idp-configuration-worksheet.md` (P2) | Marked EXTERNAL DEPENDENCY; "in scope; proceed" recorded; stop-gate requirement restated |
| 7 | `docs/decisions/p9-gate-b-contact-fields-worksheet.md` (P9 Gate B) | §0.5 added: collect-when-available working direction recorded; unresolved fields listed |
| 8 | `docs/decisions/p9-gate-a-board-role-decision-draft.md` (P9 Gate A) | Created — relationship-scoped direction recorded; unresolved fields listed |
| 9 | `docs/decisions/p8-opportunities-decision-draft.md` (P8) | Created — inclusive category set recorded; unresolved fields listed |
| 10 | `docs/decisions/pilot-decisions.md` (P7 D6, D9) | D6 section added recording the working direction; D6/D9 table rows annotated |
| 11 | `docs/plans/critical-path-legacy-pii.md` (CP-PII) | Ratification status section added: CANNOT CLOSE, non-blocking disposition recorded |
| 12 | `docs/plans/workshops/g1-factor-registry-workshop-packet.md` (P5) | Ratification status line added: CANNOT CLOSE |
| 13 | `docs/plans/2026-08-28-plan-portfolio-index.md` | Ratification-status banner added, pointing at the new index |
| 14 | `docs/plans/prep/blocked-work-register-830.md` | Ratification-status banner added |
| 15 | `docs/plans/status-report-830.md` | Superseded-as-current-status-report banner added |
| 16 | `docs/plans/2026-08-28-g3-events-s3-s5-plan.md` (P6) | Amended/superseded-for-scope notice added to header |
| 17 | `docs/plans/2026-08-28-d6-rewards-s8-s9-plan.md` (P7) | Amended/superseded-for-scope notice added to header |
| 18 | `docs/plans/2026-08-28-pilot-columns-plan.md` (P9) | Amended/superseded-for-scope notice added to header |
| 19 | `docs/plans/2026-08-31-ratification-and-implementation-report.md` | Created — this report |

**Not edited, deliberately:** `docs/security/crawler-threat-model-draft.md`
(R3's own artifact — unsigned draft, pinned test boundary, human-only
signing pass) and `docs/decisions/g3-crawler-decision.md` (already fully
signed 2026-08-29; nothing in this session changes its content).

## 3. Blocker-by-blocker report

Every blocked feature, using the design's §13 required fields.

### R3 (P6 security gate)

| Field | Content |
|---|---|
| **Decision** | Development Lead reviewer fact (Danny Tran is the named security reviewer unless a different authority is designated) plus T-07 (model-agnostic tooling; OpenRouter/Groq viable, all tools permitted in pilot scope), T-13 (project guardrail enforces egress at app runtime before outbound dispatch), T-19 (approver Danny Tran; proposers Danny, Chau / Starey Night (Janice), and their agents), T-23 (cheapest capable model by task/latency; retention terms not material to the pilot). Recorded in `docs/decisions/2026-08-31-session-ratification.md`. |
| **Implementability** | Partial (documentation only). |
| **Owner** | Development Lead / named security reviewer: Danny Tran (`dt110202@gmail.com`) for the reviewer fact; the R3 signature itself still requires a human signing pass. |
| **Work now** | None beyond this documentation record. No provider interface, adapter, model call, fetch, persistence, review action, or claim that R3 passed. |
| **Resumption** | Unresolved: R3 signature itself; T-19's conflict with signed G3 (single approver who also proposes vs. R3's required second approver — needs a G3 amendment); T-27 (observation scope), T-28 (reviewer identity/tenant/unit authority), T-29 (limits) remain CANNOT CLOSE by their own labelling; T-04's compressed-byte cap is unquantified. Affected modules: none yet (no provider interface exists). First concrete step: a human resolves the T-19/signed-G3 conflict (by G3 amendment or otherwise) and performs the R3 signing pass, flipping `test_g3_threat_model_remains_unsigned_draft` in the same commit. |

### P9 Gate A (`board_role`)

| Field | Content |
|---|---|
| **Decision** | `board_role` is relationship-scoped, contextual, and time-dependent rather than intrinsic. Recorded in `docs/decisions/p9-gate-a-board-role-decision-draft.md`. |
| **Implementability** | Partial (documentation and schema-shape analysis only). |
| **Owner** | Session approver: Danny Tran (`dt110202@gmail.com`); formal Gate A decider remains Dr. Wang. |
| **Work now** | Documentation and schema-shape analysis only. No flat rejection of `columns.yaml`'s current holding position, no new column-shape enforcement, no relationship-schema migration. |
| **Resumption** | Unresolved: multiplicity, effective dates, source semantics, correction semantics, and the formal Gate A signature. Affected modules: `docs/pilot-data/columns.yaml`, any future relationship-model migration. First concrete step: Dr. Wang signs a Gate A artifact answering the four unresolved fields. |

### P9 Gate B (published contact fields)

| Field | Content |
|---|---|
| **Decision** | Collect Public URL, Point(s) of Contact, and contact email/phone when available, for IA West Coordinator follow-up. Recorded in `docs/decisions/p9-gate-b-contact-fields-worksheet.md` §0.5. |
| **Implementability** | Partial. Only static HTTPS URL-shape validation (V2's four rules) may proceed; contact-field collection remains fully blocked. |
| **Owner** | Session approver: Danny Tran (`dt110202@gmail.com`); formal gate still requires Dr. Wang **plus** a named privacy owner, who does not yet exist anywhere in this repository. |
| **Work now** | Static URL-shape validation only (absolute URL, scheme exactly `https`, hostname present, no userinfo, no query/fragment, no IPv4/IPv6 literal host). Raw URL persistence remains blocked without an approved host/path projection. Contact data may not be collected, persisted, quarantined, copied into a finding, sent to a model, exported, or rendered. |
| **Resumption** | Unresolved: named privacy owner; purpose; minimization; retention; correction/deletion path; viewer/exporter roles; the three per-field collect/drop decisions; the §8 signature. Affected modules: the P9 pilot-columns ingestion path, `docs/pilot-data/columns.yaml`, R3's T-14 finding, G3's MP-4 control. First concrete step: name a privacy owner (a one-sentence act per the handoff), then Dr. Wang and that owner complete and sign the worksheet. |

### P1 metrics authorization

| Field | Content |
|---|---|
| **Decision** | Aggregate-visibility hierarchy: student sees their own class/unit summary; school coordinator sees their school summary; IA West Coordinator sees cross-unit portfolio metrics; raw rows stay restricted. Recorded in `docs/decisions/metrics-authorization-decision-draft.md` §0. |
| **Implementability** | Partial (direction recorded; no implementation authorized). |
| **Owner** | Session approver: Danny Tran (`dt110202@gmail.com`); formal policy still requires product and security together. |
| **Work now** | Record the hierarchy (done). Keep every **new** raw-row path fail-closed. No route, authorizer, policy-matrix, contract, or OpenAPI change. |
| **Resumption** | Unresolved: student exact-unit vs. subtree; school coordinator exact-unit vs. subtree; `admin` treatment; whether a bare `resource_grant` can read aggregates; named raw-row roles; metric-specific exceptions; formal product+security approval. Affected modules: `services/api/smartmatch_api/routers/metrics.py`, `tests/authz/test_policy_matrix.py::INTENTIONALLY_UNGATED_OPERATIONS`. The existing intentionally-ungated raw-row route remains an explicit unresolved exception — not an approved policy, not a pattern to copy. First concrete step: a product+security workshop answers the four bounded questions in `metrics-authorization-decision-draft.md` §1. |

### P8 opportunities

| Field | Content |
|---|---|
| **Decision** | Opportunity set includes hackathon, datathon, competition, guest lecturer event, and school event, recorded as an inclusive (non-exhaustive) set. Recorded in `docs/decisions/p8-opportunities-decision-draft.md`. |
| **Implementability** | Partial (category-shape fixtures only). |
| **Owner** | Session approver: Danny Tran (`dt110202@gmail.com`); formal gate still requires the product owner, who is not named anywhere in this repository. |
| **Work now** | Committed in-list and out-of-list-raw-example category-shape fixtures only, independent of P1/P9. No durable assignment, approval/rejection action, metric, or publication. |
| **Resumption** | Unresolved: whether the list is exhaustive; the canonical eligibility/count definition; the owning evidence source per registered name; T-28 identity/tenant/unit authority (for durable assignment); P6 owning persistence (for event-backed evidence); the formal product-owner signature. Affected modules: `python/smartmatch_domain/smartmatch_domain/metrics.py`, `docs/plans/2026-08-28-opportunities-s12-plan.md` card O1. First concrete step: name a product owner, then that owner ratifies the definition per the stop-gate's three required items. |

### P7 D6/D7 rewards

| Field | Content |
|---|---|
| **Decision** | Working direction: Danny Tran (`dt110202@gmail.com`) named for D6; IA West Coordinator is the intended operational administrator; $5,000 recorded as a placeholder ceiling. D7 remains tentative. Recorded in `docs/decisions/pilot-decisions.md` §D6. |
| **Implementability** | Partial (formal D6 record and existing-guarantee verification only). |
| **Owner** | Session approver: Danny Tran (`dt110202@gmail.com`) for the working direction; no institutional budget owner or funding source exists. |
| **Work now** | The formal D6 record (done) and verification of already-authorized existing-schema/append-only guarantees (e.g. `budget_owner_id NOT NULL`, `test_reward_item_rejects_a_null_budget_owner`). If a database append-only guard is found absent, report the gap rather than add it under this session. No new budget envelope, commitment, reservation, redemption, earning, catalog, route, or UI behavior. |
| **Resumption** | Unresolved: currency; institutional budget ownership; funded balance; budget lifecycle and effective versions; concurrency; release/refund semantics; overlap rules; item names/costs/content; earn policy and calibration N; fulfilment commitments; read/redemption roles. Affected modules: `docs/plans/2026-08-28-d6-rewards-s8-s9-plan.md` cards L1–L4/C1/R3/U1, `docs/pilot-data/rewards-catalog-worksheet.md`. First concrete step: name an institutional budget owner and confirm the funding model; the $5,000 figure and D7's numbers are not promoted until then. |

### P2 institutional sign-in

| Field | Content |
|---|---|
| **Decision** | In scope; proceed after the Google Cloud IdP tenant exists and the worksheet is complete. Recorded in `docs/decisions/a1b-idp-configuration-worksheet.md`. |
| **Implementability** | External dependency. |
| **Owner** | Whoever can provision the Google Cloud IdP tenant and record its final configuration — not named in this repository. |
| **Work now** | None on the identity path. Card A0 (audit + worksheet) is already landed. |
| **Resumption** | Unresolved: every field in worksheet Part 1 (provider/environment/tenant identifier; issuer, audience, JWKS retrieval/cache/refresh, accepted signing algorithms, key-rotation policy, clock-skew tolerance; client ID, public-client/PKCE decision, token-exchange model, authorization/token endpoints, redirect URIs, scopes, browser storage, refresh policy, session lifetime, logout endpoint, post-logout redirect; approving owner, approval date, administration location). A shortened subset does not pass the stop-gate. Affected modules: `docs/plans/2026-08-28-a1b-institutional-sign-in-plan.md` cards A1–A4, the legacy frontend's 16 fallback-identity files inventoried in the worksheet's Part 2. First concrete step: provision the IdP tenant and complete Part 1 in full. |

### P5 matching (D1/G1)

| Field | Content |
|---|---|
| **Decision** | No factor registry or golden case set is approved. No institutional program owner is named. |
| **Implementability** | Cannot close. |
| **Owner** | Not named — the longest-pole blocker in the portfolio. |
| **Work now** | Continue fail-closed behavior only (`assert_registry_approved()` raises `RegistryNotApprovedError`). |
| **Resumption** | Unresolved: named program owner, approved factors/weights, golden cases, `unknown`-vs-zero semantics for `historical_conversion`/`student_interest`, and weight-change governance. Affected modules: `python/smartmatch_domain/smartmatch_domain/factor_registry.py`, `tests/unit/test_factor_registry.py::test_registry_is_not_yet_approved`. First concrete step: name a program owner — the workshop packet (`docs/plans/workshops/g1-factor-registry-workshop-packet.md`) is already complete and can run the day one is named. |

### CP-PII / D9

| Field | Content |
|---|---|
| **Decision** | Keep the archive private and inaccessible; current private-repository engineering may continue. |
| **Implementability** | Cannot close. |
| **Owner** | Legacy-repository remediation owner unnamed; Development Lead directed the private/archive handling recorded here. |
| **Work now** | Nothing in this repository closes it and no work here reduces it. The archive stays read-only reference material, per `docs/decisions/pilot-decisions.md` Q1. |
| **Resumption** | Unresolved: legacy PII remediation owner and outcome (history rewrite vs. repository replacement vs. hybrid — see `docs/plans/critical-path-legacy-pii.md` §(c)); licensing/open-source approval (D9). Affected modules: none in this repository; `BrooklynD23/Nebiux-Team-IA-West-SmartMatch` (a different repository) and `LICENSE`/D9 in this one. **Explicitly non-blocking** for current private-repository engineering. First concrete step: name a remediation owner for `MM-A09.blocking_owner`. |

## 4. V1–V8 continuation order

Reproduced from the design §4, with entry conditions.

| Order | Slice | Entry condition |
|---|---|---|
| R0 | Ratification and blocker report | None — this is the first commit. **Complete as of this report.** |
| V1 | ADR-0015 A1 | Fully ratified (this report) — synthetic-provider implementation and verification may proceed. No paid call, no live credential. |
| V2 | P9 pilot columns | Static HTTPS URL-shape validation only; persistence and contact/`board_role` behavior remain blocked until their gates close. |
| V3 | P6 event discovery | Internal parsers, committed fixtures, and a contact-free public wrapper only; blocked past that boundary until the unsigned P6/R3 stop-gate passes. |
| V4 | P1 metrics authorization | Record the approved hierarchy (this report); implementation stays blocked on the remaining policy questions in §3 above. |
| V5 | P8 opportunities | Inclusive category-shape fixtures only; actions and metrics retain separate dependencies (T-28, P6, P1). |
| V6 | P7 rewards | Formal D6 recording (this report) and existing-schema/append-only verification only. |
| V7 | P2 institutional sign-in | Activates when the Google Cloud IdP worksheet is complete in full. |
| V8 | P5 matching | Activates when the D1/G1 registry and golden cases are approved by a named program owner. |

The order above is a reporting order, not whole-feature serialization —
tasks use the narrowest dependency that protects their own boundary, exactly
as design §4 states: P6 parser work does not wait for P9; P8's fixtures do
not wait for P1 or P6; P2 and P5 resume only when their own gate artifacts
are complete.

## 5. Remaining human-risk and human-action items

Ordered by decision cost, carried forward from
`docs/plans/prep/blocked-work-register-830.md` §3 and the handoff's own
ordering, and updated with what this session recorded:

1. **P9 Gate B signature** — the cheapest open gate. Three collect/drop
   choices plus a signature; a "drop all three" outcome needs no privacy
   owner and closes cleanly even though the session's working direction is
   "collect".
2. **Name the still-missing roles**: privacy owner (P9 Gate B), program
   owner (P5), rewards budget owner (P7 D6), product owner (P8), R3
   signature authority (if not the Development Lead). Each is a short,
   cheap act; none was named by this session, and none may be named by an
   agent.
3. **P1 workshop** — four bounded questions, now narrowed by the recorded
   hierarchy direction but not closed by it.
4. **P5 G1 registry** — start the day a program owner is named; the
   workshop packet is already complete.
5. **P9 Gate A**, **R3 signing pass** (including the T-19/signed-G3
   conflict), and **P7's institutional budget owner** as their respective
   owners become available.
6. **P2** — provision the Google Cloud IdP tenant; this is procurement, not
   a workshop.
7. **CP-PII remediation owner** — first human-assignment item, parallel with
   any of the above; non-blocking for current engineering but still gates
   D9 and `LICENSE`.

**Security/compliance gaps carried forward, not created by this session:**
R3 remains unsigned; T-27–T-29 remain CANNOT CLOSE by their own labelling;
egress enforcement (T-13) is accepted as an open risk until the first live
fetch, which remains unauthorized; no live-provider credential exists
anywhere in this repository.

## 6. Completed / partial / external / gap / human-action — the distinction

- **Completed behavior:** none. R0 is documentation only; no code path
  changed.
- **Partial foundations:** the documentation record itself — the
  ratification index, the updated decision artifacts, and the recorded
  working directions in §3 above — are complete as *records*, but every one
  of them stops short of authorizing an implementation past the boundary
  stated in its own row.
- **External dependencies:** P2 (Google Cloud IdP tenant); the live-provider
  price assumption A3 and production credentials/ceilings under ADR-0015
  A1; CP-PII (a different repository's remediation).
- **Security/compliance gaps:** R3 unsigned; T-27–T-29 CANNOT CLOSE; no
  egress control beyond the application allowlist; P9 Gate B's contact-field
  collection direction is recorded but not implementable without a named
  privacy owner and a completed worksheet.
- **Remaining human action:** every item in §5 above. None of it can be
  supplied by an agent, and this report supplies none of it.
