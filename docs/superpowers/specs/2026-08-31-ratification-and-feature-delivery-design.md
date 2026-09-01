# Ratification and feature-by-feature delivery — design

**Status:** Approved for implementation planning on 31 August 2026  
**Session approver:** Danny Tran (`dt110202@gmail.com`)  
**Authority boundary:** Human-decision ratification and implementation design;
not blanket approval of production code, deployment, procurement, credentials,
or unresolved organizational policy.  
**Input handoff:**
`docs/plans/prep/human-decisions-handoff-831.md` remains a handoff-only source
and must not be relabeled as the signed decision artifact.

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
commitment, or a policy value not explicitly approved by a human. CP-PII is
recorded as out of scope and non-blocking; no work in the active repository is
proposed for the archived legacy repository.

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
ratification record. The ratification pass is one documentation-only commit,
separate from every behavior change.

### 3.2 Decision outcomes

- ADR-0015 A1 is ratified and indexed as an amendment.
- R3 records the Development Lead reviewer fact and T-07, T-13, T-19, and T-23
  decisions. It remains unsigned while its internal T-19 conflict and
  T-27–T-29 remain unresolved.
- P1, P7, P8, and P9 record their explicit decisions while retaining the
  specific unfilled portions of their existing gates.
- P2 is infrastructure-blocked rather than workshop-blocked.
- P6 Stage 0 is authorized to advance beyond fixture-only parser tests without
  opening live fetching, persistence, publication, or model traffic.
- CP-PII is out of scope and cannot block active delivery in this repository.

## 4. Delivery sequence

The selected approach is feature-by-feature vertical delivery.

| Order | Slice | Entry condition and boundary |
|---|---|---|
| R0 | Ratification and blocker report | Documentation only; first commit. |
| V1 | ADR-0015 A1 | Fully ratified; synthetic-provider implementation may proceed. |
| V2 | P9 pilot columns | Safe import validation may proceed; relationship/contact persistence retains explicit gaps. |
| V3 | P6 event discovery | Offline parser integration and guarded interfaces only. |
| V4 | P1 metrics authorization | Aggregate hierarchy may proceed; raw drill-down remains denied. |
| V5 | P8 opportunities | Closed category vocabulary may proceed; canonical count waits for eligibility and event persistence. |
| V6 | P7 rewards | Budget envelope and ledger hardening may proceed; rewards stay unlisted. |
| V7 | P2 institutional sign-in | Activates when the Google Cloud IdP worksheet is complete. |
| V8 | P5 matching | Activates when the D1/G1 registry and golden cases are approved. |

P9 precedes P6 because its contact-field decision feeds R3 T-14. P6 precedes
P8 because crawler-derived opportunities need durable reviewed event evidence.
P1 precedes the P8 metric surface so opportunity aggregates inherit an explicit
authorization rule. P2 and P5 resume immediately when their external gate
artifacts become complete.

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
  -> reconcile actual cost
  -> release unused reserved capacity
```

The four states are `reserved`, `reconciled`, `expired_spent`, and `released`.
The last three are terminal. Duplicate delivery reuses `reserved`, treats
`reconciled` as a completed no-op, and refuses dispatch for `expired_spent`
unless a separate authorized budget decision creates new work.

If actual cost exceeds the estimate, the service records the overage, consumes
remaining capacity where the ratified amendment permits, and emits a
deduplicated review finding. It never hides the overage by rewriting the
estimate.

### 5.3 Boundary and evidence

This slice uses synthetic provider calls. It adds no OpenRouter/Groq credential,
live crawler path, or production configuration. Tests cover the state machine,
concurrent reservations, all-or-nothing rollback, idempotent retry and
reconciliation, conservative expiry, and the type-level refusal to dispatch
without a valid receipt.

## 6. V2 — P9 pilot columns

### 6.1 Ratified behavior

`board_role` is relationship-scoped rather than an intrinsic professional
attribute. Public URL is collected. Published contact name and contact details,
when available, exist for IA West Coordinator follow-up.

The import pipeline loads `docs/pilot-data/columns.yaml` as its single contract:

```text
import
  -> load contract
  -> validate headers and values
  -> accept ratified safe fields
  -> quarantine policy-incomplete fields
  -> emit named findings
```

Public URL accepts validated public HTTP/HTTPS values and refuses executable or
internal schemes. Published contact name and email/phone are quarantined for
review until their privacy rules are complete. They never reach titles, tags,
metrics rows, model input, exports, or public payloads. A flat `board_role` is
rejected or quarantined as the discarded interpretation; no relationship-table
migration lands until its remaining semantics are decided.

### 6.2 Remaining gate fields

Gate A still needs multiplicity, effective-date, source, and correction
semantics. Gate B still needs a named privacy owner, retention period,
view/export roles, and correction/deletion path. These are recorded as gaps,
not filled by engineering.

Tests use synthetic fixtures to prove URL validation, contact quarantine, no
contact leakage, flat-role refusal, and worker enforcement from the YAML source
of truth.

## 7. V3 — P6 offline event ingestion

Stage 0 becomes a supported provider-neutral domain pipeline:

```text
supplied document
  -> media-type parser registry
  -> ParsedSourceEvent
  -> guarded candidate adapter
  -> quarantine-ready result
```

The iCal and JSON-LD parsers become supported domain APIs. A common registry
selects the parser, and a candidate adapter carries structured provenance while
keeping raw tags quarantined, contacts redacted, unresolved time
unpublishable, and provenance out of titles.

A provider-neutral model-dispatch interface lands with fake adapters. It
requires both runtime guardrail approval and the A1 spend receipt. No real
OpenRouter or Groq call is introduced.

Event persistence, live HTTP fetching, review approval actions, publication,
and UI remain blocked by the unsigned R3 gate, T-19/T-28 authority gaps,
T-27–T-29, independent network-egress controls, credentials, and endpoint
configuration. Equivalent iCal/JSON-LD fixtures must produce equivalent
candidate shapes, and every malformed or unsupported document fails closed
with a named finding.

## 8. V4 — P1 metrics authorization

Aggregate access requires an active qualifying membership and uses the existing
organizational path to define breadth.

| Actor | Aggregate scope |
|---|---|
| Student | Their active class/unit membership only. |
| School coordinator | Their school subtree. |
| IA West Coordinator | The IA West root subtree. |
| Viewer or unrelated role | Denied. |
| Bare resource grant without membership | Denied. |

The aggregate and drill-down authorizers become separate paths. Aggregate roles
are `student` and `coordinator`; path containment distinguishes local, school,
and IA West scope. Explicit deny, suspension, tenant isolation, and membership
validity remain mandatory.

Raw drill-down is denied to every role until a later decision names permitted
row-level roles. Refusal uses the standard error envelope rather than an empty
row list. Aggregate values continue to derive from owning queries without
returning their raw rows. Policy-matrix and contract tests cover every role,
path, expiry, suspension, tenant, explicit-deny, bare-grant, and raw-row case.

## 9. V5 — P8 opportunities

The approved closed opportunity-category vocabulary is:

- hackathon;
- datathon;
- competition;
- guest lecturer event;
- school event.

Unknown-category events produce a `review_required` result assigned to the IA
West Coordinator. Once P6 persistence is authorized, that result enters the
durable auditable review queue. The coordinator may map the event to an approved
category or reject it; the original category and decision provenance remain
recorded. Before persistence lands, fixtures prove the assignment and decision
shape without claiming that a durable queue exists.

The eventual canonical flow is:

```text
approved event evidence
  -> opportunity eligibility query
  -> registered metric
  -> aggregate and drill-down API
  -> Opportunities, Dashboard, and Pipeline
```

The category list does not decide which lifecycle state counts. Metric
registration therefore waits for an explicit choice among discovered,
reviewed/publishable, match-pool, or another precise eligibility rule. No score
floor is assumed, so P8 does not inherit P5 unless a later decision adds one.
Until the canonical query exists, the legacy CSV/crawler merge and fabricated
fields are not presented as the completed replacement.

## 10. V6 — P7 rewards

The budget owner is Danny Tran (`dt110202@gmail.com`), the IA West Coordinator
is the operational administrator, and the placeholder pilot ceiling is $5,000.
This is a maximum, not proof of funded balance.

The authorized foundation adds a versioned reward-budget envelope with owner,
ceiling, effective dates, and audit reason; prevents committed reward cost from
exceeding the active ceiling; and adds the database-level append-only guard for
point-ledger entries. It seeds no budget, owner account, catalog item, or points
balance. The catalog and all reward routes remain fail-closed.

The eventual flow is:

```text
verified attendance
  -> active earn-policy version
  -> append-only ledger
  -> server-derived balance
  -> funded catalog
  -> durable redemption
```

Point earning, calibration, listing, routes, and UI wait for ratified
points-per-attendance, N, reward bands, item names/costs, funded balances,
fulfilment commitments, and read/redemption roles. The existing tentative
values are not silently promoted.

## 11. V7 — P2 institutional sign-in

P2 resumes when the Google Cloud worksheet records issuer, audience, JWKS,
algorithms, rotation, PKCE client settings, redirects, scopes, storage, refresh,
session, logout, owner, and approval date.

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

Implementation uses subagent-driven development in the same session:

1. Create an isolated feature worktree and branch.
2. Give one fresh implementation agent the complete task text and bounded file
   ownership; implementation agents run sequentially.
3. Run a fresh specification-compliance reviewer.
4. After specification compliance passes, run a fresh code-quality reviewer.
5. Return every finding to the implementer and repeat the relevant review until
   no required issue remains.

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
  never fills an unassigned gate-specific authority.
- The portfolio index, status report, blocker register, decision artifacts, and
  implementation report agree on status and owner.
- ADR-0015 A1 is the only session item promoted to a fully ratified technical
  implementation gate without additional policy input.
- Every partially cleared feature advances only through the boundary documented
  above and retains executable fail-closed behavior beyond it.
- Every implementation task receives spec and code-quality review before the
  next task begins.
- The final report distinguishes completed behavior, partial foundations,
  external dependencies, security/compliance gaps, and remaining human action.
