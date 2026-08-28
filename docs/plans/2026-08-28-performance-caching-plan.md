# Implementation plan — portal performance and caching (fast loading)

**Date:** 2026-08-28 · **Plan id:** P4 · **Worktree branch:** `plan/perf-caching`
**Executor:** frontier orchestrator agent (high reasoning) delegating fenced task
cards to subagents. Self-contained; no chat history required.
**Origin:** stakeholder requirement (Dr. Wang) — slowness observed after
sign-in; portal and metrics lag in demos; the legacy repository's
Tavily/web-crawler API calls took 5–10 seconds.

## Standing constraints (restated)

- No live providers, live data, production credentials, or deploys.
- ADR-0011: a cached number is still an accountable number. Staleness must be
  visible (computed-at provenance); never present a silently stale value as
  live, and never turn a cache miss into a zero.
- Authorization: cache behavior must not widen access. Cache keys always
  include principal + unit. The metrics-authorization decision (plan P1) is
  pending — nothing here may bake in the assumption that metrics stay ungated.
- No push, no PR, no production-readiness claims.

## Requirements (the spec)

| Id | Requirement | Verification |
|---|---|---|
| R1 | Post-sign-in to interactive dashboard ≤ 1.5 s on demo hardware (dev build ≤ 3 s) | Stage 0 baseline vs. exit measurement |
| R2 | Metric panels never block first paint; every pending panel shows an honest loading state; every unknown shows unknown | Manual + component review |
| R3 | **No crawl, LLM, or external network call on any API request path.** The legacy 5–10 s Tavily lag must be structurally impossible, not just absent | Executable scan, card C1 |
| R4 | Repeat navigation within a session re-renders previously loaded views without refetch-blocking (stale-while-revalidate) | Stage 1 cards |
| R5 | Repeat visits skip unchanged payload transfer (HTTP revalidation) | Stage 1 API card |
| R6 | Any server-side cached aggregate carries computed-at provenance | Stage 2/3 cards |

## Verified current-state facts

- `apps/web/legacy-frontend` uses **raw `fetch` in `useState`/`useEffect`
  hooks** (`src/app/hooks/useUnitMetrics.ts`); there is no query-cache library
  (no TanStack Query/SWR in `package.json`). Every mount refetches.
- The dependency list is heavy (MUI 7 + full Radix set + recharts + motion +
  react-slick + embla + masonry + react-dnd); bundle size is a first-paint
  risk. Build is Vite 6.
- `src/lib/api.ts` still exposes legacy `/api/*` clients (matching, crawler,
  outreach). The new API (`contracts/openapi/smartmatch.json`) has no such
  routes — R3's scan locks that in.
- No `Cache-Control`/`ETag` handling exists in the frontend client.

## Stage 0 — measure (sequential; blocks all optimization cards)

### Card M1 — baseline document

- **Fence:** new `docs/plans/perf-baseline-828.md`.
- **Work:** with the dev stack running, measure and record: (1) cold and warm
  load of `/`, `/dashboard`, `/pipeline` — TTFB, first contentful paint,
  interactive (browser devtools or Lighthouse); (2) wall time of each
  `/v1/units/{unit_id}/metrics` and drill-down call (server logs or devtools);
  (3) `vite build` output sizes per chunk; (4) count of fetches fired on
  dashboard mount and whether any are sequential waterfalls (network tab).
  Record hardware/context. If the environment cannot run the stack, record
  exactly what could not be measured — do not invent numbers.
- **Rule:** every Stage 1–3 card cites the baseline number it targets. No
  optimization without a number behind it.

### Card C1 — R3 guard (parallel with M1)

- **Fence:** extend `tests/unit/test_matching_fail_closed.py` or add
  `tests/unit/test_no_external_calls_on_request_path.py`.
- **Work:** assert committed OpenAPI contains no crawl/discovery/LLM/outreach
  route families (path-segment checks, consistent with the existing scan), and
  assert no module under `services/api/` imports an HTTP-client library
  (httpx/requests/aiohttp) at request-handling scope except through the
  existing verified seams (worker-side code is out of scope; the A1b JWKS
  fetch, if added by plan P2, is an allowed named exception with a comment).
- **Tests:** `python -m pytest <the test file> -q`.

## Stage 1 — existing stack (parallel lanes after M1)

### Lane F1 — frontend query cache

- **Fence:** `apps/web/legacy-frontend/package.json`,
  `src/app/hooks/useUnitMetrics.ts`, new `src/lib/queryClient.ts`, app root
  provider file.
- **Work:** add TanStack Query (latest v5). Wrap the app in a provider;
  convert `useUnitMetrics` to `useQuery` with stale-while-revalidate defaults
  (`staleTime` ~30 s for metrics; refetch on window focus off for demo
  stability). Cache keys: `["metrics", unitId]`,
  `["drilldown", unitId, metricName]` — the principal is implicit while the
  bearer is process-global, but sign-out (plan P2 card A2) must call
  `queryClient.clear()`; add that hook point now.
- **Hard rule:** an unknown metric (`value: null`) is cached like any value —
  do not retry-hammer unknowns; do not transform them.

### Lane F2 — fetch waterfall and code splitting

- **Fence:** `src/app/` router/entry files, page-level lazy imports,
  `vite.config.ts`.
- **Work:** (1) convert routes to `React.lazy`/dynamic imports so heavy chart
  and portal pages are separate chunks; (2) from M1's fetch census, start
  independent page fetches concurrently (`Promise.all` or parallel queries)
  instead of sequentially; (3) `vite build` chunk report before/after in the
  baseline doc.
- **Guard:** typecheck + build; no route behavior change.

### Lane F3 — HTTP revalidation on metrics API

- **Fence:** `services/api/smartmatch_api/routers/metrics.py` (response-header
  layer only), `tests/contract/test_metrics.py` additions.
- **Work:** add `Cache-Control: private, max-age=0, must-revalidate` and a
  weak `ETag` derived from the response payload hash to the metrics and
  drill-down responses; honor `If-None-Match` with `304`. `private` is
  mandatory (per-principal responses must never be shared-cache eligible).
  OpenAPI: regenerate only if the contract representation changes; one card
  owns regeneration.
- **Tests:** contract tests for `304` on unchanged payload and fresh `200`
  after data changes.

## Stage 2 — PostgreSQL read models (only if M1 shows API query cost)

- **Entry condition:** baseline shows metrics endpoint wall time is dominated
  by query execution (not network/render). Otherwise skip — record the skip in
  the baseline doc.
- **Card D1:** for each slow owning query, add a precomputed read model or
  index — coordinate with plan P8 (S12 read model) via the portfolio index;
  S12's owning query must not be duplicated here. Any migration goes through
  the portfolio's single migration-number owner.
- **Rule:** a precomputed aggregate row stores `computed_at`; the API includes
  it in the response so the UI can show "as of \<time\>" (R6).

## Stage 3 — Redis (only if Stages 1–2 miss R1; requires a new ADR)

- **Entry condition:** post-Stage-1/2 measurement still misses R1, and the gap
  is attributable to repeated server-side computation a process cache cannot
  hold.
- **Card R1a:** write `docs/architecture/decisions/ADR-0016-server-side-cache.md`
  proposing Redis in `docker-compose` (dev-only; no cloud service): key schema
  `{tenant}:{principal}:{unit}:{resource}:{version}`, TTLs, invalidation on
  import/write events via the existing outbox, and the ADR-0011 provenance
  rule (cached values carry `computed_at`; the API surfaces it). The ADR is a
  proposal for human review — **stop after writing it**; implementation
  proceeds only after it is accepted.
- Session-scoped warm caching ("previous login session") lives here and in
  Lane F1: it requires A1b (plan P2) so a session actually exists, and
  sign-out must clear both query cache and any server-side session keys.

## Evidence ladder

1. `python -m pytest` for C1 + F3 contract additions; `make check` if available
2. `npm run typecheck` and `npm run build` (chunk report) in the web app
3. Re-run M1 measurements; append before/after table to the baseline doc
4. **CI-only proof:** web job clean install/build; PostgreSQL contract tests
5. R1 is judged against the baseline doc's exit measurement, honestly recorded

## Done means

- R1–R6 each verified or explicitly recorded as unmet with the measured gap.
- No stage skipped silently; skips are recorded with their entry-condition
  evaluation.
- No cache serves one principal's data to another; no stale value is
  presented as live; unknown values remain unknown through every cache layer.
