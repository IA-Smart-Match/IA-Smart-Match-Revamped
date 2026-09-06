# Ratification and feature-by-feature delivery — design

**Status:** Approved for implementation planning on 31 August 2026  
**Session approver:** Danny Tran (@dangt)  
**Authority boundary:** Human-decision ratification and implementation design;
not blanket approval of production code, deployment, procurement, credentials,
or unresolved organizational policy.  
**Input handoff:**
`docs/plans/prep/human-decisions-handoff-831.md` remains a **HANDOFF ONLY**
source and must not be relabeled as a signed decision artifact. It is untracked
at design-review time and must be committed, unchanged in authority status, as
part of R0 so the ratification record is reproducible from the repository.

## 1. Objective

Turn the explicit decisions from the 31 August 2026 session into an auditable
repository trail, identify exactly which implementation slices those decisions
authorize, and deliver the authorized work feature by feature. A feature is
reported as working only when its approved end-to-end path and evidence ladder
pass. A partial or fail-closed feature keeps that label.

The delivery pattern for each feature is:

```text
decision artifact -> domain -> persistence -> API/authz -> frontend -> verification
```

If a required decision, owner, infrastructure resource, or security value is
missing, that vertical slice stops at the missing input. The executor records
the gap and moves to the next independent slice rather than guessing.

## 2. Scope and non-goals

This design covers:

- the formal ratification trail and portfolio status synchronization;
- ADR-0015 Amendment A1 spend controls;
- P9 pilot columns, P6 offline event ingestion, and P1 metrics authorization;
- the authorized foundations and resumption contracts for P8, P7, P2, and P5;
- a blocker-by-blocker implementation report and ordered continuation plan.

This design does not authorize a push, pull request, merge, deployment, live
provider call, production credential, production-readiness claim, funding
commitment, or a policy value not explicitly approved by a human. CP-PII
remains unresolved and open for D9 licensing and any future open-source
decision. It does not block engineering in the current private repository, and
no work here is represented as remediation of the archived legacy repository.

## 3. Ratification model

The repository uses four statuses so a recorded direction cannot be confused
with a passed implementation gate.

| Status | Meaning |
|---|---|
| **RATIFIED — SESSION POLICY** | Explicitly approved on 31 August 2026 by Danny Tran and available to guide implementation. |
| **RECORDED — GATE INCOMPLETE** | The direction is approved, but a required owner, policy field, or technical value is absent. |
| **EXTERNAL DEPENDENCY** | Policy is sufficient; infrastructure, procurement, credentials, or funding must arrive. |
| **CANNOT CLOSE** | Deliberately unresolved and prohibited from being represented as approved. |

### 3.1 Formal repository outputs

The ratification slice creates or updates:

1. `docs/decisions/2026-08-31-session-ratification.md` as the dated index of
   decisions, approver, status, authority boundary, and linked formal artifacts.
2. The ADR-0015 body and ADR index, together, to mark Amendment A1 ratified.
3. The P1, P2, P6/R3, P7, P8, and P9 decision artifacts only to the strongest
   status supported by their explicit answers.
4. The portfolio index, blocked-work register, and current status report so all
   three use the same blocker classification and owner.
5. `docs/plans/2026-08-31-ratification-and-implementation-report.md` with the
   review-friendly change summary, formal updates, blocker report, continuation
   order, and remaining human-risk items requested by the handoff.

The handoff document remains **HANDOFF ONLY** and links forward to the formal
ratification record. R0 commits that currently untracked handoff as source
evidence, without promoting it, and commits the formal artifacts that carry
authority. The ratification pass is one documentation-only commit, separate
from every behavior change.

### 3.2 Decision outcomes

- ADR-0015 A1 is ratified and indexed as an amendment.
- R3 records the Development Lead reviewer fact and T-07, T-13, T-19, and T-23
  decisions. It remains unsigned while its internal T-19 conflict and
  T-27–T-29 remain unresolved.
- P1, P7, P8, and P9 record their explicit decisions while retaining the
  specific unfilled portions of their existing gates.
- P2 is infrastructure-blocked rather than workshop-blocked.
- P6 permits only parser registration/public API, committed synthetic fixtures,
  and pure candidate mapping. The unsigned P6/R3 stop-gate is not passed.
- CP-PII stays open for D9/licensing/open-source purposes while remaining
  non-blocking for current private-repository engineering.

### 3.3 Per-decision authority matrix

This matrix controls R0. A direction can be explicit and still be
non-implementable when its required gate authority or policy fields are
missing.

| Decision | Approver role/person | Exact explicit decision | Status | Unresolved fields | Permitted implementation boundary |
|---|---|---|---|---|---|
| ADR-0015 A1 | Session approver: Danny Tran (@dangt) | Ratify reserve-before-paid-call monetary spend semantics separately from quota counting. | **RATIFIED — SESSION POLICY** | Live-provider estimate A3, credentials, and production ceilings remain external. | Synthetic-provider reservation implementation and verification only; no paid call. |
| R3 T-07/T-13/T-19/T-23 and reviewer fact | Development Lead / named security reviewer: Danny Tran (@dangt) | OpenRouter and Groq remain viable and all tools are permitted within pilot scope; the project guardrail runs before outbound calls; approver is Danny and proposers are Danny, Chau / Starey Night (Janice), and their relevant agents; choose the cheapest capable model by task/latency; provider-retention terms are recorded as not material to the pilot. | **RECORDED — GATE INCOMPLETE** | R3 signature; T-19 conflict; T-27 observation scope; T-28 reviewer identity/tenant/unit authority; T-29 limits; T-04 compressed-byte cap. | Documentation only. No provider interface, adapter, model call, fetch, persistence, review action, or claim that R3 passed. |
| P9 Gate B | Session approver: Danny Tran (@dangt); formal gate still requires Dr. Wang plus a named privacy owner | Collect Public URL, contact name, and email/phone when available for IA West Coordinator follow-up. | **RECORDED — GATE INCOMPLETE** | Named privacy owner; purpose; minimization; retention; correction/deletion; viewer/exporter roles; per-field decisions; signatures. | Static HTTPS URL-shape validation only; persistence requires an approved host/path projection. Contact data may not be collected, persisted, or quarantined. |
| P9 Gate A | Session approver: Danny Tran (@dangt); formal Gate A decider remains Dr. Wang | `board_role` is relationship-scoped, contextual, and time-dependent rather than intrinsic. | **RECORDED — GATE INCOMPLETE** | Multiplicity, effective dates, source semantics, correction semantics, and formal gate record. | Documentation and schema-shape analysis only; no flat rejection, column enforcement, or relationship migration. |
| P1 metrics authorization | Session approver: Danny Tran (@dangt); formal policy still requires product and security | Students see their class/unit aggregate; school coordinators see their school aggregate; IA West Coordinator sees cross-unit portfolio aggregates; raw rows stay restricted. | **RECORDED — GATE INCOMPLETE** | Student exact-unit versus subtree semantics; admin treatment; bare `resource_grant`; named raw-row roles; metric-specific exceptions; formal approval. | Record the hierarchy and keep new raw-row paths fail-closed. No route, policy-matrix, or OpenAPI change yet. |
| P8 opportunities | Session approver: Danny Tran (@dangt); formal gate still requires the product owner | The programmatic opportunity set includes hackathons, datathons, competitions, guest lecturer events, and school events; out-of-list raw examples are intended for IA West Coordinator review. | **RECORDED — GATE INCOMPLETE** | Whether the examples are exhaustive; canonical eligibility/count definition; owning evidence; T-28 authority; P6 persistence. | Committed category-shape fixtures only. No durable assignment, approval/rejection action, metric, or publication. |
| P7 D6/D7 | Session approver: Danny Tran (@dangt) | Working direction names Danny for D6, places operational control with the IA West Coordinator, and records $5,000 as a placeholder ceiling while the funding model is confirmed; D7 remains tentative. | **RECORDED — GATE INCOMPLETE** | Currency; institutional budget ownership; funded balance; budget lifecycle and effective versions; concurrency; release/refund; overlap rules; item costs/content; earn policy/N; fulfilment; read/redemption roles. | Formal D6 record and verification of already-authorized existing-schema/append-only guarantees only. No new monetary subsystem. |
| P2 institutional sign-in | Session approver: Danny Tran (@dangt) | In scope; proceed after the Google Cloud IdP tenant exists and the worksheet is complete. | **EXTERNAL DEPENDENCY** | Every field in worksheet Part 1, including approval fields. | No identity implementation until the worksheet is complete; then execute the separately reviewed P2 plan. |
| P6 Stage 0 scope | Session approver: Danny Tran (@dangt) | iCal and JSON-LD parser work is in scope. | **RECORDED — GATE INCOMPLETE** | The unsigned R3/P6 gate and T-27–T-29 remain open. | Internal parsers, committed synthetic fixtures, and a public contact-free candidate wrapper with no runtime caller, persistence, network, or model call. |
| P5 D1/G1 | No institutional program owner is named | No factor registry or golden case set is approved. | **CANNOT CLOSE** | Named owner, approved factors/weights, golden cases, unknown semantics, and governance. | Continue fail-closed behavior only. |
| CP-PII / D9 | Legacy-repository remediation owner is unnamed; Development Lead directed private/archive handling | Keep the archive private and inaccessible; current private-repository engineering may continue. | **CANNOT CLOSE** | Legacy PII remediation owner and outcome; licensing/open-source approval. | No claim of remediation or open-source readiness; non-blocking for work that keeps this repository private. |

## 4. Delivery sequence

The selected approach is feature-by-feature vertical delivery.

| Order | Slice | Entry condition and boundary |
|---|---|---|
| R0 | Ratification and blocker report | Documentation only; first commit. |
| V1 | ADR-0015 A1 | Fully ratified; synthetic-provider implementation may proceed. |
| V2 | P9 pilot columns | Static HTTPS URL-shape validation only; persistence and contact/`board_role` behavior remain blocked. |
| V3 | P6 event discovery | Internal parsers, committed fixtures, and a contact-free public wrapper only. |
| V4 | P1 metrics authorization | Record the approved hierarchy; implementation stays blocked on the remaining policy questions. |
| V5 | P8 opportunities | Inclusive category-shape fixtures only; actions and metrics retain separate dependencies. |
| V6 | P7 rewards | Formal D6 recording and existing-schema/append-only verification only. |
| V7 | P2 institutional sign-in | Activates when the Google Cloud IdP worksheet is complete. |
| V8 | P5 matching | Activates when the D1/G1 registry and golden cases are approved. |

The order above is a reporting order, not whole-feature serialization. Tasks
use the narrowest dependency that protects their own boundary:

- P6 parser registration, committed fixtures, and pure candidate mapping do not
  wait for P9; any persistence, network, model, or live-input path remains
  stopped by P6/R3 and its inherited gates.
- P8 category-shape fixtures do not wait for P1 or P6. Durable assignment and
  review actions wait for T-28 identity/tenant authorization and P6
  persistence; P8 metrics additionally wait for P1 and the canonical
  opportunity definition.
- P2 and P5 resume only when their own gate artifacts are complete.

Before any new P6, P7, or P9 task card executes, these existing plans must be
explicitly amended or superseded so the executable plan matches this design:
`docs/plans/2026-08-28-g3-events-s3-s5-plan.md`,
`docs/plans/2026-08-28-d6-rewards-s8-s9-plan.md`, and
`docs/plans/2026-08-28-pilot-columns-plan.md`. R0 records each replacement
relationship; a later agent may not select an old card merely because its file
still exists.

## 5. V1 — ADR-0015 A1 spend control

### 5.1 Components

- `spend_ceiling_bucket`: normalized job, tenant-day, and tenant-month
  reserved/spent totals.
- `spend_reservation`: deterministic work key, estimate, actual cost, lease,
  state, and reconciliation metadata.
- A persistence service that reserves all three ceilings inside one database
  transaction using a fixed lock order. Failure at any ceiling rolls the whole
  reservation back.
- A typed `SpendReservationReceipt` required by the paid-provider boundary.
- A sweeper that moves abandoned reservations conservatively to
  `expired_spent` and creates rate-limited, deduplicated review findings.

### 5.2 Data and state flow

```text
maximum estimate
  -> reserve job/day/month ceilings atomically
  -> typed receipt
  -> outbound dispatch boundary
  -> reconcile actual cost and return the unused difference
```

The four states are `reserved`, `reconciled`, `expired_spent`, and `released`.
The last three are terminal. Duplicate delivery reuses `reserved`, treats
`reconciled` as a completed no-op, and refuses dispatch for `expired_spent`
unless a separate authorized budget decision creates new work.

`released` has one legal entry path: the live worker that holds the reservation
may release it before outbound dispatch when its own code path refuses the
work. A sweeper, timeout handler, retry, or later inference may never release a
reservation. An in-worker timeout reconciles to the reserved maximum as spent
and marks that value as estimated rather than actual.

The reservation commits independently of the caller's work transaction, so a
later rollback cannot erase evidence of capacity already reserved before a
possibly paid side effect. The guarded first-insert path refuses an estimate
larger than its ceiling; it does not rely only on the conflict/update branch.

If actual cost exceeds the estimate, the service records the overage, consumes
remaining capacity where the ratified amendment permits, and emits a
deduplicated review finding. It never hides the overage by rewriting the
estimate.

### 5.3 Boundary and evidence

This slice uses synthetic provider calls. It adds no OpenRouter/Groq credential,
live crawler path, or production configuration. Tests cover the state machine,
concurrent reservations, all-or-nothing rollback, idempotent retry and
reconciliation, conservative expiry, and the type-level refusal to dispatch
without a valid receipt. They also cover a first insert above the ceiling,
reservation durability after caller rollback, timeout-to-estimated-spend, the
single pre-dispatch release path, and late-worker/sweeper races so a late
reconcile cannot reopen or double-charge a terminal reservation.

## 6. V2 — P9 pilot columns

### 6.1 Implementable boundary

Only static validation of a candidate `Public URL` may proceed now. The
mechanically testable rules are:

- the value is an absolute URL with the scheme exactly `https` and a hostname;
- URL userinfo (username or password) is absent;
- query strings and fragments are rejected rather than stored or stripped;
- IPv4 and IPv6 literal hosts are rejected; a DNS hostname is required.

Passing those checks does not establish that the hostname resolves to a public
destination, that redirects remain public, or that the resource is a public
event page. DNS resolution, destination classification, redirect checks, and
public-page/allowlist qualification belong to the future approved fetch seam.
This slice performs no resolution or fetch.

A token may also appear in an otherwise ordinary path, which static validation
cannot classify safely. Raw URL persistence therefore remains blocked unless a
separately approved host/path projection constructs a persistence-safe canonical
URL from explicitly allowlisted host and path components; it does not inspect
or copy arbitrary path segments while guessing whether they are tokens. The
projection output has no query, fragment, or userinfo. If no approved projection
covers the host/path, the URL is not persisted.

Quarantine is collection. Published contact names, email addresses, and phone
numbers therefore may not be collected, persisted, quarantined, copied into a
finding, sent to a model, exported, or rendered until Gate B records all of:

- a named privacy owner and the collection purpose;
- minimization and retention rules;
- correction and deletion paths;
- named viewer and exporter roles;
- completed per-field decisions and required signatures.

The explicit direction to collect those contacts when available for IA West
Coordinator follow-up is preserved as **RECORDED — GATE INCOMPLETE**, not as an
ingestion branch or implementable behavior.

### 6.2 `board_role` boundary

The session records `board_role` as relationship-scoped rather than intrinsic.
Gate A still lacks multiplicity, effective-date, source, and correction
semantics. Until those fields and the formal gate record close, engineering may
not reject the flat column as a discarded interpretation, enforce a new column
shape, or add relationship-schema behavior. R0 records the decision and the
open semantics; it does not select a migration.

Tests in this slice cover the four static rules, prove that passing validation
does not claim destination or page qualification, and prove that no persistence
occurs without an approved host/path projection. They also prove the URL path
performs no DNS/network call and opens no contact-data path. The existing P9
plan must be amended or superseded before any replacement card executes.

## 7. V3 — P6 offline event ingestion

The unsigned P6/R3 stop-gate is not passed. Authorized early work uses a safe
exposed-wrapper design:

```text
committed synthetic fixture
  -> internal iCal or JSON-LD parser
  -> private parsed representation
  -> allowlist projection
  -> ContactFreeEventCandidate public seam
```

Parser modules and their raw parsed representations may remain internal and may
observe organizer/contact fields needed to parse a format. The supported public
seam returns a dedicated `ContactFreeEventCandidate` whose type omits organizer,
contact name, email, phone, and any generic catch-all/raw-properties field that
could carry them. The wrapper constructs that type by allowlisting safe fields,
not by copying a raw object and deleting known contact keys.

Required tests place distinctive synthetic organizer, contact-name, email, and
phone values in committed iCal and JSON-LD fixtures, call the public wrapper,
and prove both that the fields are absent from the candidate type/serialized
shape and that none of the distinctive values cross the wrapper. The committed
synthetic fixtures are the tested evidence. The interface does not recognize or
authenticate fixture provenance, so no runtime caller is wired to it.

No persistence, network access, model dispatch, review assignment, publication,
or UI action lands. No provider interface, fake provider adapter, or arbitrary
caller-supplied document ingestion surface is introduced.

T-29 leaves every post-fetch complexity limit unquantified. The implementation
therefore cannot claim support for unbounded, arbitrary, or even generally
quantified input; it can claim only behavior demonstrated by the bounded
committed synthetic fixtures. Malformed or unsupported fixture cases fail
closed with a pure typed result. Persistence, HTTP fetching, model traffic,
review actions, and publication remain blocked by the unsigned gate and
T-27–T-29. The existing P6 plan must be amended or superseded first.

## 8. V4 — P1 metrics authorization

The session approved an aggregate-visibility hierarchy as direction:

| Actor | Recorded aggregate direction |
|---|---|
| Student | Their own class or unit summary. |
| School coordinator | Their school summary. |
| IA West Coordinator | Cross-unit portfolio metrics. |

That hierarchy does not decide whether a student's scope is the exact unit or a
subtree, whether a school coordinator's “school” is an exact unit or subtree,
how `admin` is treated, whether a bare `resource_grant` can read aggregates, or
which named roles may read raw rows. Engineering must not infer any of those
answers from the existing path model.

Implementation is blocked until product and security record those exact
answers. No route, authorizer, policy-matrix, contract, or OpenAPI change is
authorized yet. Fail-closed raw-row handling governs every **new** path. The
existing intentionally ungated route remains an explicit unresolved exception
until policy is ratified and an implementation change is authorized; it is not
an approved policy and not a pattern new work may copy. When the gate closes,
raw-row refusal must use the standard error envelope rather than an empty row
list, and aggregate/drill-down equality remains required for authorized
callers.

## 9. V5 — P8 opportunities

The recorded opportunity set includes:

- hackathon;
- datathon;
- competition;
- guest lecturer event;
- school event.

These are an inclusive set of examples, not a closed vocabulary unless a later
product-owner artifact explicitly says they are exhaustive. Committed fixtures
may prove an **in-list** category shape and an **out-of-list raw example** shape
without waiting for P1 or P9.

The later session direction intends out-of-list raw examples to go to the IA
West Coordinator for review. “Out-of-list” does not mean invalid or unknown;
the list is non-exhaustive. Executable assignment and approve/reject actions
wait for both T-28 identity/tenant/unit authorization and P6 persistence. Before
those dependencies land, no fixture claims an authenticated assignee, durable
queue, or executable decision; it proves category shape only.

The eventual canonical flow is:

```text
approved event evidence
  -> opportunity eligibility query
  -> registered metric
  -> aggregate and drill-down API
  -> Opportunities, Dashboard, and Pipeline
```

The examples do not decide which lifecycle state counts. Metric registration
waits for an explicit canonical definition, P6 owning persistence, and the
completed P1 authorization rule. No score floor is assumed, so P8 does not
inherit P5 unless a later decision adds one. Until the canonical query exists,
the legacy CSV/crawler merge and fabricated fields are not presented as the
completed replacement.

## 10. V6 — P7 rewards

R0 may formally record the D6 working direction: Danny Tran
(@dangt) was named in the handoff, the IA West Coordinator is the
intended operational administrator, and $5,000 was stated as a placeholder.
That record is **not** proof of institutional budget ownership, currency,
funding, an active ceiling, or authority to spend. D7 remains tentative.

Immediate engineering is limited to the formal D6 record and verification of
already-authorized existing schema and append-only guarantees. If a database
append-only guard is absent, the executor reports that gap rather than adding
it under this session. No new budget envelope, commitment, reservation,
redemption, earning, catalog, route, or UI behavior is authorized here.

The eventual flow is:

```text
verified attendance
  -> active earn-policy version
  -> append-only ledger
  -> server-derived balance
  -> funded catalog
  -> durable redemption
```

New monetary behavior remains blocked until a formal design specifies currency,
funding, envelope lifecycle, effective versions and overlap behavior,
concurrent commitment, release/refund semantics, item names and costs,
fulfilment commitments, earn policy and N, and read/redemption roles. The
$5,000 placeholder and tentative D7 values are not promoted. The existing P7
plan must be amended or superseded before any replacement card executes.

## 11. V7 — P2 institutional sign-in

P2 resumes only when **every field in Part 1** of the Google Cloud worksheet is
complete: IdP product/vendor, environment, tenant/directory identifier; issuer,
audience, JWKS retrieval, JWKS cache/refresh, accepted signing algorithms,
key-rotation policy, and clock-skew tolerance; client ID, public-client/PKCE
decision, token-exchange model, authorization and token endpoints, redirect
URIs, scopes, browser storage, refresh policy, session lifetime, logout
endpoint, and post-logout redirect; approving owner, approval date, and
administration location. A shortened subset does not pass the stop-gate.

```text
Google authorization
  -> PKCE exchange
  -> verified token
  -> server-derived principal
  -> tenant memberships
  -> authorized application
```

The completed slice removes fallback identities, clears principal-scoped query
caches on sign-out, and keeps fixture authentication development-only. Before
the worksheet is complete, this is an external infrastructure dependency rather
than an unanswered product workshop.

## 12. V8 — P5 matching

P5 remains fail-closed until a named IA West program owner approves a D1/G1
artifact containing the factor list and normalized weights; the fate of
`historical_conversion` and `student_interest`; golden cases with expected
outputs; zero-versus-unknown labels; and weight-change governance.

After that approval, delivery follows:

```text
approved registry
  -> independently tested factors
  -> golden-suite join
  -> deterministic portfolio optimizer
  -> immutable match-run snapshots
  -> authorized API
  -> explained UI
```

The legacy scoring engine and its defective 0.90 maximum are not ported or
characterized as the new contract. Matching UI also requires usable identity,
so P2 is an integration dependency even if domain scoring finishes first.

## 13. Error handling and blocker reporting

Every refusal is fail-closed and returns or records a stable reason. Restricted
rows are not represented as empty data, missing evidence is not represented as
zero, malformed imports are not silently dropped, and an unavailable provider
does not produce a synthetic success.

For every blocked feature, the implementation report records:

| Field | Required content |
|---|---|
| Decision | The explicit decision received and its artifact. |
| Implementability | Full, partial, external dependency, or cannot close. |
| Owner | Final approving human or external resource owner. |
| Work now | Exact authorized tasks that may proceed. |
| Resumption | Unresolved field, affected modules, and first concrete next step. |

## 14. Verification and completion

Each task runs the narrowest relevant check first, then expands through:

```text
focused tests
  -> make check
  -> migration and OpenAPI checks where applicable
  -> frontend TypeScript validation and build where applicable
  -> PostgreSQL integration tests
  -> final whole-branch review
```

`vite build` does not replace TypeScript validation. Generated OpenAPI is never
hand-edited. An unavailable database, IdP, provider, credential, or live target
is reported as a verification gap rather than a pass.

A feature is complete only when its authorized workflow works end to end and
the evidence ladder passes. An implemented foundation, unsigned live path, or
fail-closed UI is reported as partial.

## 15. Execution and model routing

Implementation uses subagent-driven development in the same session. Each
implementation task owns one bounded layer and its corresponding files:

| Task layer | Ownership boundary |
|---|---|
| Migration | One numbered migration, schema mirror changes required by it, and migration/constraint tests. |
| Domain | Pure types, state rules, parsers/mappers, and unit tests; no database, HTTP, provider, or UI work. |
| Persistence | Repositories/services, transaction behavior, and persistence tests; no route or UI work. |
| Route/authz/OpenAPI | Router, policy-matrix rows, contract tests, and generated OpenAPI in one task; generated contracts are never hand-edited. |
| Frontend | Named pages/components/hooks and TypeScript tests/build; no backend contract invention. |
| Verification/join | Cross-layer fixtures, integration evidence, and final join verification after owned layers pass. |

Tasks run sequentially with one implementation agent per task:

1. Create an isolated feature worktree and branch.
2. Give one fresh implementation agent the complete task text and one bounded
   layer/file fence.
3. Run a fresh specification-compliance reviewer for that task.
4. After specification compliance passes, run a fresh code-quality reviewer for
   that task.
5. Return findings to the same implementer; start the next implementation task
   only after both reviews pass.

Codex routing uses `gpt-5.6-sol` high reasoning for orchestration and
`gpt-5.6-sol` low reasoning for implementation. When execution moves to the
Claude environment, the portable task prompts support Opus 5.0 orchestration
and Sonnet 5.0 implementation. This Codex harness does not claim it directly
dispatches Claude models.

Policy-matrix edits travel with route changes. Migrations, generated OpenAPI,
and shared frontend files have one owner at a time. The ratification commit and
each feature slice remain independently reviewable. No push, merge, pull
request, deployment, live-provider use, or production credential use is
implicit in design approval.

## 16. Acceptance criteria

- The formal ratification record preserves every explicit session decision and
  never fills an unassigned gate-specific authority; the HANDOFF ONLY input is
  committed in R0 so the record is reproducible.
- The portfolio index, status report, blocker register, decision artifacts, and
  implementation report agree on status and owner.
- ADR-0015 A1 is the only session item promoted to a fully ratified technical
  implementation gate without additional policy input.
- Every partially cleared feature advances only through the boundary documented
  above, and every newly introduced path fails closed beyond that boundary. P1's
  existing intentionally ungated raw-row route remains an explicit unresolved
  exception until policy is ratified and its implementation change is
  authorized.
- V2 performs only the stated static URL checks and persists no URL without an
  approved host/path projection; destination and public-page claims wait for
  the future fetch/allowlist seam.
- V3 exposes only the contact-free candidate wrapper, with tests proving fixture
  organizer/contact fields and values cannot cross it; no runtime caller lands.
- P8 fixtures use `in-list` and `out-of-list raw example`; they do not imply a
  closed vocabulary or an executable review assignment.
- Every implementation task receives spec and code-quality review before the
  next task begins.
- Existing P6, P7, and P9 plans are explicitly amended or superseded before any
  replacement task card executes.
- The final report distinguishes completed behavior, partial foundations,
  external dependencies, security/compliance gaps, and remaining human action,
  including CP-PII as open for D9/open-source purposes but non-blocking for
  current private-repository engineering.
