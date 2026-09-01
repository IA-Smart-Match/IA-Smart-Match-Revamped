# 31 August 2026 session ratification — dated index of decisions

**Date:** 31 August 2026
**Approver (session):** Danny Tran (`dt110202@gmail.com`)
**Authority boundary (verbatim from the design header):** Human-decision
ratification and implementation design; **not** blanket approval of
production code, deployment, procurement, credentials, or unresolved
organizational policy.
**Source design:**
`docs/superpowers/specs/2026-08-31-ratification-and-feature-delivery-design.md`
(§§3, 4, 8, 10, 13, 16).
**Source handoff (HANDOFF ONLY, not a decision artifact itself):**
`docs/plans/prep/human-decisions-handoff-831.md`, committed unchanged in
authority status alongside this record.
**Commit boundary:** this record and the other R0 formal-artifact updates it
indexes land as **one documentation-only commit**, separate from any behavior
change. No push, pull request, merge, deployment, live-provider call,
production credential, or production-readiness claim is authorized by this
record.

---

## 1. Purpose

This is the dated, authoritative index of every explicit decision made in the
31 August 2026 session, its status under the four-status model below, and the
formal repository artifact each decision is recorded in or authorizes. It
supersedes no evidence — the handoff and every prior dated artifact remain in
the repository as the record of what was said and when — and it fills no
blank that the source materials leave blank. Where a field is unknown, this
record says so and names who must supply it, per the source design's own
rule.

## 2. The four statuses

| Status | Meaning |
|---|---|
| **RATIFIED — SESSION POLICY** | Explicitly approved on 31 August 2026 by Danny Tran and available to guide implementation. |
| **RECORDED — GATE INCOMPLETE** | The direction is approved, but a required owner, policy field, or technical value is absent. |
| **EXTERNAL DEPENDENCY** | Policy is sufficient; infrastructure, procurement, credentials, or funding must arrive. |
| **CANNOT CLOSE** | Deliberately unresolved and prohibited from being represented as approved. |

A direction can be explicit and still be non-implementable when its required
gate authority or policy fields are missing. Reaching a status in this table
never means a gate passed, never means production readiness, and never fills
an unassigned gate-specific authority (owner, budget holder, privacy owner,
program owner, security reviewer) that no source document names.

## 3. Per-decision authority matrix

Reproduced from the design's §3.3, in substance and in full. This is the
controlling table for R0.

| Decision | Approver role/person | Exact explicit decision | Status | Unresolved fields | Permitted implementation boundary |
|---|---|---|---|---|---|
| **ADR-0015 A1** | Session approver: Danny Tran (`dt110202@gmail.com`) | Ratify reserve-before-paid-call monetary spend semantics separately from quota counting. | **RATIFIED — SESSION POLICY** | Live-provider estimate A3, credentials, and production ceilings remain external. | Synthetic-provider reservation implementation and verification only; no paid call. |
| **R3 T-07/T-13/T-19/T-23 and reviewer fact** | Development Lead / named security reviewer: Danny Tran (`dt110202@gmail.com`) | OpenRouter and Groq remain viable and all tools are permitted within pilot scope; the project guardrail runs before outbound calls; approver is Danny and proposers are Danny, Chau / Starey Night (Janice), and their relevant agents; choose the cheapest capable model by task/latency; provider-retention terms are recorded as not material to the pilot. | **RECORDED — GATE INCOMPLETE** | R3 signature; T-19 conflict; T-27 observation scope; T-28 reviewer identity/tenant/unit authority; T-29 limits; T-04 compressed-byte cap. | Documentation only. No provider interface, adapter, model call, fetch, persistence, review action, or claim that R3 passed. |
| **P9 Gate B** | Session approver: Danny Tran (`dt110202@gmail.com`); formal gate still requires Dr. Wang plus a named privacy owner | Collect Public URL, contact name, and email/phone when available for IA West Coordinator follow-up. | **RECORDED — GATE INCOMPLETE** | Named privacy owner; purpose; minimization; retention; correction/deletion; viewer/exporter roles; per-field decisions; signatures. | Static HTTPS URL-shape validation only; persistence requires an approved host/path projection. Contact data may not be collected, persisted, or quarantined. |
| **P9 Gate A** | Session approver: Danny Tran (`dt110202@gmail.com`); formal Gate A decider remains Dr. Wang | `board_role` is relationship-scoped, contextual, and time-dependent rather than intrinsic. | **RECORDED — GATE INCOMPLETE** | Multiplicity, effective dates, source semantics, correction semantics, and formal gate record. | Documentation and schema-shape analysis only; no flat rejection, column enforcement, or relationship migration. |
| **P1 metrics authorization** | Session approver: Danny Tran (`dt110202@gmail.com`); formal policy still requires product and security | Students see their class/unit aggregate; school coordinators see their school aggregate; IA West Coordinator sees cross-unit portfolio aggregates; raw rows stay restricted. | **RECORDED — GATE INCOMPLETE** | Student exact-unit versus subtree semantics; admin treatment; bare `resource_grant`; named raw-row roles; metric-specific exceptions; formal approval. | Record the hierarchy and keep new raw-row paths fail-closed. No route, policy-matrix, or OpenAPI change yet. |
| **P8 opportunities** | Session approver: Danny Tran (`dt110202@gmail.com`); formal gate still requires the product owner | The programmatic opportunity set includes hackathons, datathons, competitions, guest lecturer events, and school events; out-of-list raw examples are intended for IA West Coordinator review. | **RECORDED — GATE INCOMPLETE** | Whether the examples are exhaustive; canonical eligibility/count definition; owning evidence; T-28 authority; P6 persistence. | Committed category-shape fixtures only. No durable assignment, approval/rejection action, metric, or publication. |
| **P7 D6/D7** | Session approver: Danny Tran (`dt110202@gmail.com`) | Working direction names Danny for D6, places operational control with the IA West Coordinator, and records $5,000 as a placeholder ceiling while the funding model is confirmed; D7 remains tentative. | **RECORDED — GATE INCOMPLETE** | Currency; institutional budget ownership; funded balance; budget lifecycle and effective versions; concurrency; release/refund; overlap rules; item costs/content; earn policy/N; fulfilment; read/redemption roles. | Formal D6 record and verification of already-authorized existing-schema/append-only guarantees only. No new monetary subsystem. |
| **P2 institutional sign-in** | Session approver: Danny Tran (`dt110202@gmail.com`) | In scope; proceed after the Google Cloud IdP tenant exists and the worksheet is complete. | **EXTERNAL DEPENDENCY** | Every field in worksheet Part 1, including approval fields. | No identity implementation until the worksheet is complete; then execute the separately reviewed P2 plan. |
| **P6 Stage 0 scope** | Session approver: Danny Tran (`dt110202@gmail.com`) | iCal and JSON-LD parser work is in scope. | **RECORDED — GATE INCOMPLETE** | The unsigned R3/P6 gate and T-27–T-29 remain open. | Internal parsers, committed synthetic fixtures, and a public contact-free candidate wrapper with no runtime caller, persistence, network, or model call. |
| **P5 D1/G1** | No institutional program owner is named | No factor registry or golden case set is approved. | **CANNOT CLOSE** | Named owner, approved factors/weights, golden cases, unknown semantics, and governance. | Continue fail-closed behavior only. |
| **CP-PII / D9** | Legacy-repository remediation owner is unnamed; Development Lead directed private/archive handling | Keep the archive private and inaccessible; current private-repository engineering may continue. | **CANNOT CLOSE** | Legacy PII remediation owner and outcome; licensing/open-source approval. | No claim of remediation or open-source readiness; non-blocking for work that keeps this repository private. |

## 4. Decision outcomes, restated

- ADR-0015 A1 is ratified and indexed as an amendment — the **only** session
  item promoted to a fully ratified technical implementation gate without
  additional policy input.
- R3 records the Development Lead reviewer fact and T-07, T-13, T-19, and
  T-23 decisions. It remains **unsigned** while its internal T-19 conflict
  and T-27–T-29 remain unresolved.
- P1, P7, P8, and P9 record their explicit decisions while retaining the
  specific unfilled portions of their existing gates.
- P2 is **infrastructure-blocked** (procurement) rather than
  workshop-blocked.
- P6 permits only parser registration/public API, committed synthetic
  fixtures, and pure candidate mapping. The unsigned P6/R3 stop-gate is
  **not** passed.
- CP-PII stays open for D9/licensing/open-source purposes while remaining
  **non-blocking** for current private-repository engineering.

## 5. Linked formal artifacts

| Decision | Formal artifact this record indexes |
|---|---|
| ADR-0015 A1 | [`docs/architecture/decisions/ADR-0015-charge-quota-before-refusal.md`](../architecture/decisions/ADR-0015-charge-quota-before-refusal.md) and its row in [`docs/architecture/decisions/README.md`](../architecture/decisions/README.md) |
| R3 T-07/T-13/T-19/T-23 and reviewer fact | Recorded here only. `docs/security/crawler-threat-model-draft.md` remains an unsigned draft and is **not** edited by this ratification — its signature block is a pinned test boundary (`test_g3_threat_model_remains_unsigned_draft`) that only a human signing pass may flip. |
| P9 Gate B | [`p9-gate-b-contact-fields-worksheet.md`](p9-gate-b-contact-fields-worksheet.md) |
| P9 Gate A | [`p9-gate-a-board-role-decision-draft.md`](p9-gate-a-board-role-decision-draft.md) (new; the direction was previously recorded only in the handoff and `docs/pilot-data/board-role-decision-prep.md`) |
| P1 metrics authorization | [`metrics-authorization-decision-draft.md`](metrics-authorization-decision-draft.md) |
| P8 opportunities | [`p8-opportunities-decision-draft.md`](p8-opportunities-decision-draft.md) (new; no artifact previously existed under `docs/decisions/`) |
| P7 D6/D7 | [`pilot-decisions.md`](pilot-decisions.md) §D6/D7 |
| P2 institutional sign-in | [`a1b-idp-configuration-worksheet.md`](a1b-idp-configuration-worksheet.md) |
| P6 Stage 0 scope | [`g3-crawler-decision.md`](g3-crawler-decision.md) (G3 half, already signed 2026-08-29) plus this record for the Stage 0 scope confirmation; the R3 half remains as above |
| P5 D1/G1 | [`../plans/workshops/g1-factor-registry-workshop-packet.md`](../plans/workshops/g1-factor-registry-workshop-packet.md) and `pilot-decisions.md` D1 |
| CP-PII / D9 | [`../plans/critical-path-legacy-pii.md`](../plans/critical-path-legacy-pii.md) and `pilot-decisions.md` D9 |

## 6. Portfolio synchronization

The same blocker classification and owner recorded above are mirrored, as of
this date, in:

- [`../plans/2026-08-28-plan-portfolio-index.md`](../plans/2026-08-28-plan-portfolio-index.md)
- [`../plans/prep/blocked-work-register-830.md`](../plans/prep/blocked-work-register-830.md)
- [`../plans/status-report-830.md`](../plans/status-report-830.md)
- [`../plans/2026-08-31-ratification-and-implementation-report.md`](../plans/2026-08-31-ratification-and-implementation-report.md)

## 7. Plan supersession recorded here

Before any new P6, P7, or P9 task card executes, the following existing plans
are **explicitly amended/superseded** by
`docs/superpowers/specs/2026-08-31-ratification-and-feature-delivery-design.md`
so the executable plan matches that design. A later agent may not select an
old card merely because its file still exists; each plan's own header now
carries the same notice.

| Plan | Replacement relationship |
|---|---|
| [`../plans/2026-08-28-g3-events-s3-s5-plan.md`](../plans/2026-08-28-g3-events-s3-s5-plan.md) (P6) | Superseded for scope by design §7 (V3): only internal parsers, committed fixtures, and the contact-free `ContactFreeEventCandidate` public wrapper are authorized now. Cards S3–S6 (persistence, identity/upsert, review queue, crawl adapter) remain gated on the unsigned P6/R3 stop-gate exactly as this plan already states, and do not start early. |
| [`../plans/2026-08-28-d6-rewards-s8-s9-plan.md`](../plans/2026-08-28-d6-rewards-s8-s9-plan.md) (P7) | Superseded for scope by design §10 (V6): only the formal D6 record and verification of already-authorized existing-schema/append-only guarantees are authorized now. Cards L1–L4, C1, R3, U1 (ledger fold, listing, redemption) remain gated on D6/D7/role artifacts exactly as this plan already states, and do not start early. |
| [`../plans/2026-08-28-pilot-columns-plan.md`](../plans/2026-08-28-pilot-columns-plan.md) (P9) | Superseded for scope by design §6 (V2): only the four static URL-shape rules are authorized now, and only when no persistence, DNS/network call, or contact-data path is opened. Gate A (`board_role`) and Gate B (contact collection) remain open exactly as this plan already states, and no branch may run past its own gate. |

## 8. What this record does not do

- It does not sign R3, G3 (already signed separately), or any other
  human-only gate artifact.
- It does not name an owner, budget holder, privacy owner, program owner, or
  security reviewer that no source document names.
- It does not authorize a route, policy-matrix, contract, OpenAPI, migration,
  or UI change by itself — each is authorized, if at all, by the boundary
  text in the matrix above and by
  `docs/plans/2026-08-31-ratification-and-implementation-report.md`.
- It does not claim any gate passed or that any feature is production-ready.
