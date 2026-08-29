# Performance baseline — plan P4, card M1

**Date:** 2026-08-28 · **Plan:** P4 (`docs/plans/2026-08-28-performance-caching-plan.md`)
**Branch:** `plan/perf-caching` · **Base commit:** `2357251`

## Reading rule for this document

Card M1 says: *"If the environment cannot run the stack, record exactly what
could not be measured — do not invent numbers."*

Every row below is one of exactly two things:

- a **measured** value, with the exact command or method that produced it, or
- **`NOT MEASURABLE IN THIS ENVIRONMENT`**, with the reason.

There are no estimates, no extrapolations, and no illustrative figures in this
document. A row with no number has no number. Optimization cards cite rows from
this document; a card that cannot cite a measured row must say so.

---

## 1. Measurement environment

| Property | Value | How known |
|---|---|---|
| Host | WSL2 on Windows, kernel `6.6.87.2-microsoft-standard-WSL2` | `uname -r` |
| CPU | Intel Core Ultra 7 258V, 5 cores visible to WSL | `/proc/cpuinfo`, `nproc` |
| Memory | 12 GiB visible to WSL | `free -g` |
| Repo location | `/mnt/c/...` — a **9p/DrvFs mount**, not native ext4 | path |
| Python | 3.12.3 (`.venv/bin/python`) | `--version` |
| Node / npm | v22.21.0 / 11.6.3 | `--version` |
| PostgreSQL | 16.2, reachable at `localhost:5432` | `SELECT version()` |
| Browser | **none installed** | `which google-chrome chromium` → not found |
| Lighthouse | **not installed** | `which lighthouse` → not found |
| Docker daemon | **not running** | `docker info` → failure |

Two environment facts shape everything below and must be carried forward:

1. **There is no browser and no Lighthouse on this machine.** Anything defined
   in terms of a rendered page — first contentful paint, time to interactive,
   cold vs. warm browser page load, network-tab waterfall observation — cannot
   be produced here at all. It is recorded as not measurable, not estimated.
2. **The repository lives on `/mnt/c`.** Filesystem-bound work (npm install,
   Vite build, TypeScript) is materially slower here than on native Linux
   storage, so any *build-time* figure recorded in this document is a figure for
   this machine and must not be read as a property of the code.

### Measurement stack actually stood up

To avoid disturbing the shared `smartmatch` development database (other plan
worktrees are using it concurrently), all API measurement ran against a
dedicated, freshly migrated database:

```
createdb smartmatch_p4perf   (via psycopg; no psql client on PATH)
cd db && SMARTMATCH_DATABASE_URL="postgresql+psycopg://smartmatch:smartmatch@localhost:5432/smartmatch_p4perf" \
  ../.venv/bin/alembic upgrade head        # → head 0009_engagement_schema
tools/seed_pilot.py --subject p4-perf-subject --email p4perf@example.invalid --role admin
```

API process under measurement:

```
SMARTMATCH_DATABASE_URL=postgresql+psycopg://smartmatch:smartmatch@localhost:5432/smartmatch_p4perf \
SMARTMATCH_EDITION=dev SMARTMATCH_USE_FIXTURE_PROVIDERS=true \
SMARTMATCH_DEV_PRINCIPALS='{"p4-perf-token":"p4-perf-subject"}' \
uvicorn smartmatch_api.main:app --host 127.0.0.1 --port 8321
```

Timing method, for every API row below:

```
curl -s -o /dev/null -H 'Authorization: Bearer p4-perf-token' -w '%{time_total}' <url>
```

repeated 25 times per endpoint, sorted, reported as min / p50 / p95 / max in
seconds. `time_total` is loopback wall time including connect, so it is an upper
bound on server time, not a server-internal timer.

---

## 2. Browser-side page load — NOT MEASURABLE IN THIS ENVIRONMENT

Card M1 item (1): cold and warm load of `/`, `/dashboard`, `/pipeline` —
TTFB, first contentful paint, interactive.

| Metric | Value |
|---|---|
| `/` cold TTFB / FCP / interactive | **NOT MEASURABLE IN THIS ENVIRONMENT** — no browser and no Lighthouse are installed on this host; there is no way to render the page or observe paint or interactivity timings. |
| `/` warm TTFB / FCP / interactive | **NOT MEASURABLE IN THIS ENVIRONMENT** — same reason. |
| `/dashboard` cold and warm | **NOT MEASURABLE IN THIS ENVIRONMENT** — same reason. |
| `/pipeline` cold and warm | **NOT MEASURABLE IN THIS ENVIRONMENT** — same reason. |

**Consequence for R1 (post-sign-in to interactive dashboard ≤ 1.5 s):**
R1 is defined in terms of time-to-interactive in a browser. With no browser on
this machine, **R1 is not verifiable here — neither met nor unmet.** This
document does not claim R1 is satisfied and does not claim it is missed. It
records that the evidence required to judge it cannot be produced in this
environment. Judging R1 requires a run on demo hardware with a real browser.

---

## 3. API endpoint wall time — MEASURED

Card M1 item (2). All figures in **seconds**, loopback, 25 samples each.

### 3a. Baseline dataset: 0 pending review items (freshly seeded database)

| Endpoint | min | p50 | p95 | max |
|---|---|---|---|---|
| `GET /api/health` (no auth, no DB) | 0.0028 | 0.0036 | 0.0053 | 0.0111 |
| `GET /v1/me` | 0.0082 | 0.0118 | 0.0163 | 0.0243 |
| `GET /v1/units/{unit}/metrics` (all 6 registered metrics) | 0.0097 | 0.0169 | 0.0248 | 0.0390 |
| `GET .../metrics/pending_review_items/drill-down` | 0.0085 | 0.0181 | 0.0387 | 0.1182 |
| `GET .../metrics/pipeline_matched/drill-down` (an *unknown* metric, no DB work) | 0.0082 | 0.0137 | 0.0280 | 0.0652 |

Metrics collection response size: **2,085 bytes**.

### 3b. Loaded dataset: 5,000 synthetic pending review items

5,000 `review_item` rows with `status='pending'` were inserted under one
synthetic `import_batch` owned by the seeded unit, purely to make the one real
owning query do real work. The rows are synthetic and local-only.

| Endpoint | min | p50 | p95 | max |
|---|---|---|---|---|
| `GET /v1/units/{unit}/metrics` | 0.0368 | 0.0430 | 0.0911 | 0.1070 |
| `GET .../metrics/pending_review_items/drill-down` | 0.0409 | 0.0778 | 0.1208 | 0.1256 |

Response sizes at 5,000 rows: metrics collection **2,088 bytes**; drill-down
**1,686,898 bytes** (~1.6 MB — the drill-down returns every constituent row by
design, and its cost is transfer-dominated, not query-dominated).

### 3c. Cost attribution inside the metrics endpoint (5,000 rows)

| Layer | Measured | Method |
|---|---|---|
| PostgreSQL execution of the one real owning query | **12.2 ms** execution, 1.9 ms planning | `EXPLAIN (ANALYZE)` on the `pending_review_item_rows_v1` query |
| Same query round-tripped through psycopg incl. row transfer | min 0.0158 / p50 0.0203 s | 15 timed `execute().fetchall()` calls |
| Whole `GET .../metrics` HTTP request | p50 0.0430 s | curl, above |

So at 5,000 rows the metrics endpoint costs ~43 ms p50 end to end, of which
~12 ms is PostgreSQL execution. The remainder is psycopg row materialisation,
authorization, Pydantic serialization and HTTP framing.

---

## 4. Legacy `/api/*` mount fetches against the revamp API — MEASURED

The recon fact restated: the revamp API implements only `/v1/*`, `/api/health`
and `/u/{token}`. Every legacy endpoint that `Dashboard`, `Pipeline` and the
crawler surfaces call on mount is absent from it. M1 is required to attribute
observed lag between *failing legacy fetches* and *real endpoint latency*.
Measured against the running revamp API, 10 samples each:

| Path (caller) | HTTP | p50 | max |
|---|---|---|---|
| `/api/data/specialists` (`fetchSpecialists`) | 404 | 0.0033 | 0.0113 |
| `/api/data/events` (`fetchEvents`) | 404 | 0.0027 | 0.0283 |
| `/api/data/pipeline` (`fetchPipeline`) | 404 | 0.0036 | 0.0135 |
| `/api/calendar/events` (`fetchCalendarEvents`) | 404 | 0.0030 | 0.0119 |
| `/api/calendar/assignments` (`fetchCalendarAssignments`) | 404 | 0.0022 | 0.0035 |
| `/api/feedback/stats` (`fetchFeedbackStats`) | 404 | 0.0031 | 0.0066 |
| `/api/qr/stats` (`fetchQrStats`) | 404 | 0.0025 | 0.0083 |
| `/api/crawler/status` (`CrawlerContext` 3 s poll) | 404 | 0.0024 | 0.0062 |
| `/api/crawler/results` (`CrawlerFeed`) | 404 | 0.0020 | 0.0034 |

**Attribution finding.** Against the revamp API these fetches fail in about
3 ms each. They are therefore **not** a latency source on this stack; they are a
correctness and honesty problem (a mount that renders from failed calls, and a
recurring failed poll). The stakeholder-reported 5–10 s lag came from the
*legacy* backend's Tavily/crawler calls, which the revamp API does not implement
at all — card C1 now pins that structurally (R3).

This number is what plan P8 inherits: removing these calls buys correctness, not
milliseconds, on the revamp API. Any card claiming a latency win from removing
them would be citing a number that does not exist.

---

## 5. Fetches fired on mount — MEASURED BY SOURCE READING

Card M1 item (4). Counted by reading the source, since no network tab exists.
(The plan's recon already established there are no A-then-B waterfalls; this
confirms the counts rather than re-deriving the waterfall analysis.)

**`/dashboard` (`src/app/pages/Dashboard.tsx`)** — 8 requests on mount:

| # | Call | Batch |
|---|---|---|
| 1–6 | `fetchSpecialists`, `fetchEvents`, `fetchPipeline`, `fetchCalendarEvents`, `fetchCalendarAssignments`, `fetchFeedbackStats` | one `Promise.allSettled` batch, `Dashboard.tsx:313–320` — **parallel** |
| 7 | `useUnitMetrics(reloadToken)` → `GET /v1/units/{unit}/metrics` | independent effect, `Dashboard.tsx:442` |
| 8 | `CrawlerFeed` → `fetchCrawlerResults` plus an `EventSource("/api/crawler/feed")` | `CrawlerFeed.tsx:55, 108` |

Plus, on **every** IA-admin page (the `Layout` route), `CrawlerProvider` fires
`GET /api/crawler/status` immediately and then **every 3 seconds forever**
(`CrawlerContext.tsx:25–30`), and `CrawlerFeed` starts its own `setInterval`
poll of `/api/crawler/results` (`CrawlerFeed.tsx:75`).

**`/pipeline` (`src/app/pages/Pipeline.tsx`)** — 4 requests on mount in one
`Promise.allSettled` batch (`Pipeline.tsx:190–194`): `fetchPipeline`,
`fetchEvents`, `fetchQrStats`, `fetchFeedbackStats` — **parallel**.

**Sequential waterfalls found: none.** Confirmed by reading; consistent with the
plan's recon. No card in this plan does waterfall work.

---

## 6. `vite build` chunk report

Card M1 item (3). MEASURED. Command, run from
`apps/web/legacy-frontend`:

```
npm run typecheck   # tsc --noEmit
npm run build       # npm run typecheck && vite build
```

Note on where the modules live: `/mnt/c`'s drvfs mount corrupted two npm
installs outright, so `node_modules` is a symlink to an ext4 tree at
`/home/danny/nm-perf/node_modules`. That affects install and build *duration*
only — the emitted chunk bytes below are a property of the code and the Vite
config, not of the filesystem.

### 6a. Before Lane F2 — MEASURED

`tsc --noEmit` exit 0; `vite build` exit 0, `✓ 2751 modules transformed`,
`✓ built in 7.26s`.

| Artifact | Raw | gzip |
|---|---|---|
| `dist/index.html` | 0.69 kB | 0.35 kB |
| `dist/assets/index-*.css` | 135.22 kB | 21.44 kB |
| `dist/assets/vendor-ui-*.js` | 50.31 kB | 16.71 kB |
| `dist/assets/vendor-react-*.js` | 276.46 kB | 92.28 kB |
| `dist/assets/vendor-charts-*.js` | 412.19 kB | 114.51 kB |
| **`dist/assets/index-*.js`** (the single application chunk) | **448.39 kB** | **112.40 kB** |
| **Total JS** | **1187.35 kB** | **335.90 kB** |

The number Lane F2 targets is the **448.39 kB / 112.40 kB gzip single
application chunk**: `routes.tsx` imports all 21 page components statically, so
every route's code — student portal, coordinator portal, volunteer portal,
admin pages — is in the one chunk downloaded before any route renders.

Note that the `vendor-emotion` chunk configured in `vite.config.ts` does not
appear in the output; Emotion is currently landing inside another chunk. That
is an observation about today's `manualChunks` behaviour, not a Lane F2 target.

### 6b. After Lane F2 — MEASURED

Same command, same machine, after route-level code splitting. `tsc --noEmit`
exit 0; `vite build` exit 0, `✓ 2752 modules transformed`, `✓ built in 14.05s`.
The output is now ~35 route chunks; the entries that changed or matter:

| Artifact | Before | After |
|---|---|---|
| `dist/assets/index-*.js` (application chunk) | 448.39 kB / 112.40 kB gzip | **197.49 kB / 59.88 kB gzip** |
| `dist/assets/vendor-react-*.js` | 276.46 kB / 92.28 kB | 276.46 kB / 92.28 kB (identical) |
| `dist/assets/vendor-charts-*.js` | 412.19 kB / 114.51 kB | 412.19 kB / 114.51 kB (identical) |
| `dist/assets/vendor-ui-*.js` | 50.31 kB / 16.71 kB | 50.31 kB / 16.71 kB (identical) |
| `dist/assets/index-*.css` | 135.22 kB / 21.44 kB | 134.48 kB / 21.29 kB |
| per-route chunks | none | ~35, e.g. `Dashboard` 32.22 kB / 8.29 kB, `Calendar` 23.06 kB / 5.29 kB, `Volunteers` 22.26 kB / 5.64 kB, `Pipeline` 19.63 kB / 5.18 kB |

**Delta on the eagerly-loaded application chunk: −250.90 kB raw, −52.52 kB
gzip (−46.7%).** The three vendor chunks are byte-identical, which confirms the
existing `manualChunks` configuration was neither changed nor disturbed.

What this figure does and does not say, stated plainly: it is a **measured
reduction in bytes downloaded before the first route can render**. It is *not*
a time-to-interactive measurement, and this document does not convert it into
one — see §2. Whether it moves R1 can only be judged on hardware with a browser.

### 6d. After Lane F1 — MEASURED (the honest net figure)

Lane F1 adds TanStack Query, which lands in the eagerly loaded chunk. The
final `npm run build` on this branch, with F1, F2 and F4 all in:
`✓ 2800 modules transformed`, `✓ built in 27.70s`.

| Artifact | Before P4 (§6a) | After F2 (§6b) | After F1 (final) |
|---|---|---|---|
| `dist/assets/index-*.js` | 448.39 kB / 112.40 kB gzip | 197.49 kB / 59.88 kB gzip | **243.50 kB / 73.31 kB gzip** |
| `vendor-react-*.js` | 276.46 / 92.28 | 276.46 / 92.28 | 276.46 / 92.28 |
| `vendor-charts-*.js` | 412.19 / 114.51 | 412.19 / 114.51 | 412.19 / 114.51 |
| `vendor-ui-*.js` | 50.31 / 16.71 | 50.31 / 16.71 | 50.31 / 16.71 |

Stated plainly, both directions: route splitting removed 250.90 kB raw /
52.52 kB gzip from the eager chunk, and **the query cache added 46.01 kB raw /
13.43 kB gzip back**. The net across this plan is **−204.89 kB raw /
−39.09 kB gzip (−34.8% gzip)** on the bytes downloaded before the first route
can render. F1's cost is recorded rather than netted away silently — it buys
R4, and R4 has a byte price.

The build also emits a pre-existing circular-dependency warning about
`Dashboard.tsx` importing `MetricDrilldownSheet` through the `provenance`
barrel. It is a warning, not a failure, it predates this lane, and both files
belong to another plan's fence. Recorded, not fixed.

---

## 6c. Lane F3 — HTTP revalidation, verified live

Measured against a running API carrying the Lane F3 change (same database,
same host, same method as §3).

Response headers on a 200, verbatim from `curl -D -`:

```
HTTP/1.1 200 OK
cache-control: private, max-age=0, must-revalidate
etag: W/"b85e2c83bc31ecbf220d41a3bad8ea5afa31cf2adf36b83b390c5f6cf10111a1"
```

Replaying that ETag as `If-None-Match`:

```
HTTP/1.1 304 Not Modified
cache-control: private, max-age=0, must-revalidate
etag: W/"b85e2c83bc31ecbf220d41a3bad8ea5afa31cf2adf36b83b390c5f6cf10111a1"
```

**R5 — payload transfer skipped on an unchanged repeat visit (measured):**

| Request | Bytes downloaded | p50 wall time (n=25) |
|---|---|---|
| Drill-down `200` (5,000 rows) | **1,686,898** | 0.0591 s |
| Drill-down `304` (same data) | **0** | 0.0467 s |
| Metrics `200` | 2,088 | 0.0362 s |
| Metrics `304` | 0 | 0.0347 s |

Read this honestly: the **transfer** saving is total and real (1.69 MB → 0 B).
The **wall-time** saving is modest (0.0591 s → 0.0467 s p50 on loopback, where
transfer is nearly free) because the server still executes the owning query and
serializes the payload in order to compute the ETag — a 304 skips sending the
body, not producing it. On a real network the transfer saving dominates; on
this loopback it does not, and this document does not pretend otherwise.
Eliminating the server-side recomputation is what Stage 2/3 would address, and
§7 records why neither is entered.

ADR-0011 through the new layer, verified on the live endpoint: an unknown
metric still returns `"aggregate_value": null` with its `unknown_reason`
intact. The cache layer does not coerce unknown to zero.

---

## 7. Stage 2 entry-condition evaluation (PostgreSQL read models)

**Entry condition (from the plan):** *"baseline shows metrics endpoint wall time
is dominated by query execution (not network/render). Otherwise skip — record
the skip in the baseline doc."*

**Evaluation against §3:**

- The metrics collection endpoint executes exactly **one** real PostgreSQL
  query (`pending_review_item_rows_v1`). The other five registered metrics are
  `pipeline_*` and are honest unknowns with no database access at all until S12.
- On an empty dataset the whole endpoint is 16.9 ms p50, and the *unknown-only*
  drill-down — which touches no database — is 13.7 ms p50. Almost all of the
  endpoint's cost is therefore framework and transport, not query execution.
- On a deliberately loaded 5,000-row dataset the endpoint is 43.0 ms p50, of
  which PostgreSQL execution is 12.2 ms — about **28%**. Query execution does
  not dominate even when the one real query is doing 5,000 rows of work.

**Decision: Stage 2 is SKIPPED.** The entry condition is not met. This matches
the plan's own recon expectation that the stage stays skipped until plan P8
lands real owning queries. There is no slow owning query to build a read model
for; building one now would add a migration and a `computed_at` provenance
surface for a query that costs 12 ms.

Re-evaluate when P8/S12 lands real Pipeline persistence and the five `pipeline_*`
metrics stop being no-DB unknowns.

---

## 7b. Stage 3 entry-condition evaluation (Redis; ADR-0016)

**Entry condition (from the plan):** *"post-Stage-1/2 measurement still misses
R1, and the gap is attributable to repeated server-side computation a process
cache cannot hold."*

**Evaluation.** The condition has two conjuncts and the first cannot be
established here. §2 records that R1 is a time-to-interactive requirement and
that no browser or Lighthouse exists on this host, so the post-Stage-1
measurement does not miss R1 — it **cannot judge R1 at all**. "Not verifiable"
is not "missed", and treating it as a miss would be exactly the kind of
invented conclusion this document exists to prevent.

The second conjunct also has no supporting evidence. §3c and §6c measure the
server-side computation directly: the whole metrics endpoint is 43 ms p50 at
5,000 rows, of which 12 ms is PostgreSQL. There is no repeated server-side
computation of a size that would justify a new infrastructure dependency.

**Decision: Stage 3 is NOT entered, and ADR-0016 is NOT written.** Writing a
Redis proposal now would mean proposing infrastructure on the strength of a
number this environment cannot produce. If a run on demo hardware with a real
browser shows R1 missed, this evaluation should be revisited **with that
measurement in hand** — and even then only if the gap is attributable to
server-side recomputation rather than to page weight or render.

---

## 8. What was not measured, and why

| Item | Status |
|---|---|
| FCP / TTI / cold-vs-warm page load for `/`, `/dashboard`, `/pipeline` | **NOT MEASURABLE IN THIS ENVIRONMENT** — no browser, no Lighthouse installed. |
| R1 (≤ 1.5 s to interactive; dev build ≤ 3 s) | **NOT VERIFIABLE IN THIS ENVIRONMENT** — it is a time-to-interactive requirement and §2 explains why no such number can be produced here. Not claimed met; not claimed unmet. |
| Network-tab observation of mount fetches | **NOT MEASURABLE IN THIS ENVIRONMENT** — no browser. Substituted with source reading in §5, which is labelled as such. |
| Real production/demo data volumes | **NOT AVAILABLE** — §3b uses 5,000 *synthetic* local rows, chosen to exercise the one real query. It is not a claim about real volumes. |

---

## 9. Before/after table

Appended as Stage 1 lanes land. Every row cites the section above that it
targets, and any row that cannot be measured on this machine says so.

| Requirement | Target | Before | After | Method |
|---|---|---|---|---|
| R1 | ≤ 1.5 s interactive | not verifiable here (§2) | not verifiable here (§2) | needs a browser on demo hardware; no browser or Lighthouse on this host |
| R2 | panels never block first paint; pending shows loading; unknown shows unknown | metrics fetched in an independent effect, not blocking the mount batch (§5) | unchanged for first paint; route suspense fallback is a plain spinner with no fabricated values | source review + typecheck |
| R3 | no crawl/LLM/external call on any request path | no executable guard existed | two structural guards, both passing (card C1) | `pytest tests/unit/test_no_external_calls_on_request_path.py` |
| R4 | repeat navigation re-renders without refetch-blocking | every mount refetched; raw `fetch` in `useEffect`, no query cache (plan recon, confirmed in §5) | TanStack Query, `staleTime` 30 s, `refetchOnWindowFocus` off; principal-scoped keys with clear-on-identity-change | `npm test` — 8/8 pass, including the account-switch isolation test; `npm run typecheck` clean |
| R5 | skip unchanged payload transfer | no `Cache-Control` and no `ETag` on any `/v1` metrics response (confirmed by reading `services/api/smartmatch_api/routers/metrics.py`: the only `Cache-Control` anywhere in `services/api/` was `no-store` on the jobs SSE stream) | drill-down repeat visit transfers **0 bytes** instead of **1,686,898** (§6c) | live `curl` with `If-None-Match`, plus contract tests |
| R6 | server-side cached aggregates carry computed-at provenance | no server-side cached aggregate exists | still none — Stage 2 skipped (§7), Stage 3 not entered | entry-condition evaluation, §7 |
| eager JS bytes | reduce pre-route download | 448.39 kB / 112.40 kB gzip (§6a) | 243.50 kB / 73.31 kB gzip (§6d — F2 removed 52.52 kB gzip, F1 added 13.43 kB back) | `npm run build` |
