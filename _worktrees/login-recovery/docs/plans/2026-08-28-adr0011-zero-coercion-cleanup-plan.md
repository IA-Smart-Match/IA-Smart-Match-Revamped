# Implementation plan — residual ADR-0011 zero-coercion cleanup

**Date:** 2026-08-28 · **Plan id:** P3 · **Worktree branch:** `plan/adr0011-cleanup`
**Executor:** frontier orchestrator agent (high reasoning) delegating fenced task
cards to subagents. Self-contained; no chat history required.
**Gate style:** none — this is implement-now engineering debt named in
`docs/plans/orchestrator-handoff.md` §Remaining blockers.

## Standing constraints (restated)

- ADR-0011: never turn missing evidence into a zero, a count, a rank, or a
  progress bar. Unknown stays unknown, with a reason where the surface shows it.
- No push, no PR, no fabricated metrics, no production-readiness claims.
- Wave 3C behavior is correct and must not regress: pipeline funnel metrics
  render unknown (`value: null` + `unknown_reason`); dashboard supplementary
  metrics render unknown on failed fetches (`db0eb09`).

## Problem statement (verified facts)

`apps/web/legacy-frontend/src/lib/api.ts` contains a request-seam normalizer
layer that predates the review fixes and coerces absent values to numbers:

- `parseNumber(value, fallback = 0)` (~line 470) — used throughout the
  normalizers with the default fallback.
- `normalizeRankedMatch` (~line 719): `Number(payload.score ?? ... ?? 0) || 0`.
- `normalizeCalendarEvent` / `normalizeCalendarAssignment` /
  `normalizeVolunteerRecovery`: coverage ratios, fatigue, assignment counts,
  travel burden, and cadence all default to `0` when the payload omits them.
- `normalizeQrCodeAsset` / `normalizeQrStats` / `normalizeFeedbackStats`:
  scan counts, conversion counts/rates, acceptance rates default to `0`.
- `emptyQrStatsSummary()` / `emptyFeedbackStatsSummary()` return all-zero
  objects used as fallbacks.

Not every zero is a violation. A zero is forbidden when the **evidence is
absent** and the surface presents the value as a measurement (metric tile,
rate, count, progress bar, score). A zero is acceptable when it is a true
measured zero, or a pure layout default with no evidentiary claim.

## Task cards

### Card Z1 — audit and classification (sequential, first)

- **Fence:** new file `docs/plans/adr0011-frontend-coercion-inventory.md`.
- **Work:** enumerate every numeric coercion on a metric-bearing path:
  ripgrep `apps/web/legacy-frontend/src` for `\?\? 0`, `\|\| 0`,
  `parseNumber\(`, `Number\(`, `normalizeFatigue`, `clamp(`. For each hit
  record: file, line, the value's meaning, the consuming UI surface, and a
  classification — `violation` (missing evidence shown as measurement),
  `measured-zero-ok`, or `layout-ok`. The consuming-surface column is
  mandatory; a coercion is classified by where it renders, not by its shape.
- **Output:** the committed inventory. Every later card fences to files this
  inventory lists as containing violations.

### Card Z2 — type seam: nullable numerics (after Z1)

- **Fence:** `apps/web/legacy-frontend/src/lib/api.ts` only.
- **Work:** for each violation in `api.ts`: change the field type to
  `number | null`, replace the zero fallback with `null`, and where the API
  provides one, carry the `unknown_reason`. Add
  `parseNumberOrNull(value): number | null` beside `parseNumber` and migrate
  violation call sites to it; leave `layout-ok` call sites on `parseNumber`.
  Do not delete `parseNumber` while any legitimate caller remains.
- **Tests:** `npm run typecheck` — the compiler now forces every consumer to
  handle `null`, which is the point: consumers surface in card Z3's fence.

### Card Z3 — consumer surfaces (parallel lanes after Z2 typecheck output)

Split by page into parallel lanes with disjoint fences, guided by the
typecheck errors and the Z1 inventory. Expected lanes:

- **Z3a** `Dashboard.tsx` + `MetricCard.tsx`
- **Z3b** `Pipeline.tsx` + `PipelineFunnelTiles.tsx`
- **Z3c** calendar/volunteer pages consuming coverage/fatigue summaries
- **Z3d** QR/feedback stat pages consuming `QrStatsSummary` /
  `FeedbackStatsSummary`

Each lane renders `null` as an explicit unknown state (an em-dash or
"unknown" label consistent with the Wave 3C pattern in
`PipelineFunnelTiles.tsx`), never as `0`, and never fabricates a reason string
the API did not send. Progress bars bound to unknown values render an
indeterminate/absent state, not 0%.

### Card Z4 — guard test (after Z3)

- **Fence:** new `tests/unit/test_frontend_zero_coercion_contract.py`.
- **Work:** narrow source-contract test in the style of
  `tests/unit/test_frontend_auth_contract.py`: assert `api.ts` contains no
  `?? 0` / `|| 0` on the field names classified as violations in Z1 (list them
  explicitly in the test), and assert `parseNumberOrNull` exists. Keep it
  narrow; it is not a substitute for Vitest.
- **Tests:** `python -m pytest tests/unit/test_frontend_zero_coercion_contract.py -q`.

## Out of scope

- The legacy `/api/*` endpoints themselves (matching, crawler, outreach
  normalizers feed pages that are G1/G3-gated or slated for removal; fix their
  coercions only where the Z1 inventory shows they render today).
- Backend metric behavior (already ADR-0011-conformant).
- Removing `emptyQrStatsSummary`/`emptyFeedbackStatsSummary` callers' pages —
  convert the summaries' fields to nullable like the rest.

## Evidence ladder

1. `npm run typecheck` in `apps/web/legacy-frontend` (required after Z2, Z3)
2. `python -m pytest tests/unit/test_frontend_zero_coercion_contract.py tests/unit/test_metrics_openapi_contract.py -q`
3. `make check` if available
4. **CI-only proof:** web job locked install, typecheck, Vite build, audit.
5. Manual acceptance: with the API stopped, Dashboard/Pipeline show unknown
   states everywhere — no tile, rate, or progress bar shows `0`.

## Done means

- Every Z1 violation is either fixed (null + unknown rendering) or re-classified
  with a written reason in the inventory.
- Typecheck and the new guard test pass.
- Wave 3C unknown-rendering behavior is unchanged.
