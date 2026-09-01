# Implementation plan — canonical opportunities metric and S12 persistence

**Date:** 2026-08-28 · **Plan id:** P8 · **Worktree branch:** `plan/opportunities-s12`
**Executor:** frontier orchestrator agent (high reasoning) delegating fenced task
cards to subagents. Self-contained; no chat history required.

## Standing constraints (restated)

- ADR-0011: "opportunities" without a written definition is an invalid metric
  name; one canonical name maps to one owning query; drill-down count equals
  aggregate; unknown stays unknown until evidence exists.
- Do not "fix" the two-pages disagreement (Fix #5) by pointing both pages at
  the same fabricated client-side merge.
- No unresolved event date or quarantined tag reaches a publishable list
  (ADR-0010/0012). No matcher actions before G1.
- No push, no PR, no production-readiness claims.

## Stop-gate (verify before any card)

Required committed artifact: a written canonical definition of
"opportunities" (expected under `docs/decisions/`, building on
`docs/plans/opportunities-metric-inventory.md`), ratified by the product
owner, containing non-blank:

1. the definition — which of: events eligible for publication, events in a
   match pool, events with a candidate above a score floor, or another
   precisely stated rule;
2. which variants deserve **distinct registered names** versus UI filters;
3. the owning evidence source for each registered name.

**Conditional inheritance:** if the definition includes a score floor, this
plan inherits plan P5's stop-gate (G1) and cannot proceed past card O1 until
G1's artifact passes. If the definition depends on crawler-fed events, it
inherits plan P6's gate for those rows. The executor evaluates and records
which branch applies:

| Definition | Branch |
|---|---|
| Publication-eligibility based (no scores) | `BRANCH-ELIGIBILITY` — proceed after this gate alone |
| Score-floor based | `BRANCH-SCORE-FLOOR` — also requires P5 M8 landed |

## Current state (verifiable)

- `python/smartmatch_domain/smartmatch_domain/metrics.py`: `METRIC_REGISTER`
  has pipeline funnel metrics returning unknown with
  `PIPELINE_UNKNOWN_REASON` ("S12 Pipeline persistence is not started"); no
  `opportunities` metric exists.
- `services/api/smartmatch_api/routers/metrics.py`:
  `_pipeline_funnel_rows_v1` honestly returns no rows;
  `tests/contract/test_metrics.py::test_pipeline_unknown_is_null_with_an_empty_drill_down`
  locks that behavior.
- `Opportunities.tsx` still merges legacy CSV + crawler client-side with
  fabricated fields (`date: "See link for details"`, `role: "Guest speaker"` —
  H21); Dashboard prose says "active opportunities"; Pipeline uses registered
  funnel metrics (Wave 3C). This is the Fix #5 disagreement.
- Drill-down template exists: `MetricDrilldownSheet.tsx`, `useUnitMetrics.ts`.

## Task cards

### Card O1 — register the definition (sequential first)

- **Fence:** `python/smartmatch_domain/smartmatch_domain/metrics.py` + unit
  tests.
- **Work:** add register entries copying the ratified definition text exactly
  — the canonical `opportunities` metric and any decided variant names, each
  with one owning-query identifier. Until card O3 binds storage, the entries
  resolve unknown with an honest reason (mirroring the pipeline pattern).

### Card O2 — S12 persistence (serial migration resource; after O1)

- **Fence:** new migration (number from the portfolio migration owner),
  `smartmatch_persistence/schema.py`, integration tests.
- **Work:** funnel/lifecycle persistence per the definition: one lifecycle
  `Matched → Contacted → Confirmed → Attended → Member Inquiry` with
  tenant/unit scoping and evidence linkage (event identity from P6's `event`
  table where applicable; if P6 has not landed and the definition needs event
  rows, record the dependency and stop this card). Design the read model to
  return both the aggregate and the exact constituent rows.
- **Coordination:** shares the funnel domain with plan P4 Stage 2 — the
  portfolio index gives P8 ownership of the S12 read model; P4 must consume,
  not duplicate.

### Card O3 — bind owning query (after O2)

- **Fence:** `services/api/smartmatch_api/routers/metrics.py` + contract tests.
- **Work:** bind the registered identifier(s) to the storage-backed row query;
  derive the aggregate from those same rows (rule 3/rule 4 of ADR-0011); the
  pipeline funnel metrics move from unknown to real values only where S12
  evidence actually exists — stages without evidence remain unknown.
- **Tests:** `tests/contract/test_metrics.py` — clicked N returns exactly N
  rows for zero and non-zero cases; unit isolation; authorization consistent
  with the P1 outcome (whatever the committed policy is at execution time).
  The deliberate flip of
  `test_pipeline_unknown_is_null_with_an_empty_drill_down` happens here, in
  the same commit, and only for stages with real evidence.

### Card O4 — frontend subscribers (parallel lanes after O3)

- **O4a fence:** `Opportunities.tsx` (+ its data helpers): remove the
  client-side CSV/crawler merge and every fabricated field; subscribe to the
  registered metric(s) via `useUnitMetrics`/`fetchMetricDrillDown`; hide
  unresolved events; remove the "Run matcher" pathway (stays G1-gated).
- **O4b fence:** `Dashboard.tsx`: replace "active opportunities" prose and any
  link with the registered metric name and its drill-down; no `href`-only
  navigation where a same-query drill-down is required (B30).
- **O4c fence:** `Pipeline.tsx` + `PipelineFunnelTiles.tsx`: consume the same
  registered names; label any decided variant by its registered display name.
- **Rule for all lanes:** the number on every surface comes from the same
  registered metric API; two surfaces showing different numbers must be
  showing differently *named* registered metrics.

## Evidence ladder

1. Per-card focused pytest; `make check`
2. `make openapi-check` if response contracts change
3. Web typecheck/build after O4
4. **CI-only proof:** S12 migration + contract tests on PostgreSQL; web build.
5. Manual acceptance: `/opportunities`, Dashboard, and Pipeline show the same
   value for the same metric name; clicking an aggregate N lists exactly N
   rows; stages without evidence still say unknown.

## Done means

- One written definition ↔ one owning query ↔ all surfaces subscribed.
- Drill-down equals aggregate, unit-scoped, authorization-consistent.
- No fabricated dates/roles; unresolved events and quarantined tags never
  render; unknown remains unknown where evidence is missing.
