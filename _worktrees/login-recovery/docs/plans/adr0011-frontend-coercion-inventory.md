# ADR-0011 frontend zero-coercion inventory (Card Z1)

**Plan:** `2026-08-28-adr0011-zero-coercion-cleanup-plan.md` · **Card:** Z1
**Method:** `rg '\?\? 0|\|\| 0|parseNumber\(|Number\(|normalizeFatigue|clamp\('
apps/web/legacy-frontend/src`, then every hit was traced to its actual
consuming UI surface by reading the rendering component (not guessed from the
coercion's shape). Classification is per the plan's rubric:

- **violation** — evidence is absent and the surface presents the value as a
  measurement (metric tile, rate, count, progress bar, score).
- **measured-zero-ok** — a genuine measured zero (the backend always computes
  the aggregate; 0 is a true state, not absent evidence).
- **layout-ok** — a pure layout/sort/accumulator default that makes no
  evidentiary claim to the user, or a field with no current consumer.
- **out-of-scope** — feeds a matching/crawler/outreach endpoint explicitly
  excluded by the plan's "Out of scope" section.

Counts: **7 violations found and fixed** · **~14 measured-zero-ok** ·
**~30 layout-ok / unconsumed** · **8 out-of-scope (matching/outreach)**.
(Counts are approximate where one line covers a small cluster of near-identical
sibling fields in the same object literal; every distinct field is listed
below.)

## Violations (fixed in Z2/Z3)

| # | File:Line (pre-fix) | Coercion | Value meaning | Consuming surface | Fix |
|---|---|---|---|---|---|
| V1 | `lib/api.ts:682` `normalizeFatigue(...)` in `normalizeCalendarAssignment` | `CalendarAssignmentSummary.volunteer_fatigue` | Volunteer fatigue score for a calendar assignment | `Calendar.tsx` "Fatigue" tile (`formatPercent`), `Calendar.tsx` "Average fatigue" KPI card, `Volunteers.tsx` fatigue % + progress bar (via `CalendarAssignmentSummary` rows) | Field is now `number \| null`; added `normalizeFatigueOrNull`; consumers render "Unknown" text and an indeterminate striped bar instead of 0%. |
| V2 | `lib/api.ts:705` `parseNumber(..., 0)` in `normalizeCalendarAssignment` | `CalendarAssignmentSummary.recent_assignment_count` | Recent-assignment count shown unconditionally in a metric-tile-shaped card | `Calendar.tsx` "Recent" tile, rendered with no guard | Field is now `number \| null` via `parseNumberOrNull`; `Calendar.tsx` renders via new `formatCount()` helper → "Unknown" when null. |
| V3 | `lib/api.ts:809-829` (`normalizeQrCodeAsset`) | `QrCodeAsset.scan_count`, `.conversion_count`, `.conversion_rate` | Per-referral-code scan/conversion counts and rate | `Volunteers.tsx` QR history list + ROI bar, `Pipeline.tsx` QR entries list, `QRCodeCard.tsx` (Scans/Conversions/ROI tiles + progress bar) | All three fields are now `number \| null`. A rate with no scan-count evidence is `null`, never a fabricated `0`. Consumers render "Unknown" text and an indeterminate striped bar in place of a 0%-width bar. |
| V4 | `lib/api.ts:866-908` (`normalizeQrStats`) | `QrStatsSummary.total_generated/total_scans/total_conversions/conversion_rate` | Aggregate QR summary tiles | `Pipeline.tsx` QR summary metrics (`qrCodesGenerated`, etc., already null-gated by `qrAvailable` at the top level) and the `qrStats.total_generated > 0` / `total_scans > 0` badge/gating logic | Fields now `number \| null`; explicit plan directive ("convert the summaries' fields to nullable like the rest") followed even though the top-level aggregate is often a real computed sum — see note below. Entries-derived fallback sums are only used when every entry actually reports a value; otherwise `null`. |
| V5 | `lib/api.ts:974-1008` (`normalizeFeedbackStats`) | `FeedbackStatsSummary.total_feedback/accepted/declined/acceptance_rate/attended_count/membership_interest_count/membership_interest_rate/average_match_score_accepted/average_match_score_declined/pain_score` | Feedback-optimizer summary tiles + trend narration | `Dashboard.tsx` and `Pipeline.tsx` metric tiles (already null-gated by `feedbackAvailable`) and the `${feedbackStats.accepted} accepted / ${feedbackStats.declined} declined` / `${feedbackStats.membership_interest_count} attributed...` narration strings, which previously had **no** per-field null guard and would have literally rendered the string `"null accepted / null declined"` once these fields could be `null` | Fields now `number \| null`; `emptyQrStatsSummary`/`emptyFeedbackStatsSummary` now return `null` for every numeric field (previously all-zero placeholders — the exact ADR-0011 anti-pattern of using a fabricated zero object as a "no data yet" placeholder). Dashboard/Pipeline narration strings now check each field for `null` before interpolating. |
| V6 | `app/pages/Volunteers.tsx:176-185` (pre-fix) `clamp((12 + weightedLoad*11 + ...)/100, 0, 1)` | `fallbackFatigue` — a **fabricated** fatigue estimate synthesized from unrelated pipeline-stage weighting whenever a volunteer had zero calendar-assignment overlays | Volunteer card "Recovery / load" %, progress bar, and the volunteer-detail "Fatigue index" %, progress bar, and caption text ("Fatigue is derived locally from the current pipeline footprint.") | This is the most serious finding: not just a zero standing in for missing evidence, but a plausible-looking *non-zero* number computed from unrelated data and presented as if it were a measurement. The formula and its use have been **deleted**. `volunteerFatigue`/`fatigueScore` are now `number \| null`, computed only from real `CalendarAssignmentSummary.volunteer_fatigue` values; the UI renders "Unknown" text, an indeterminate striped bar, and a corrected caption ("Fatigue is averaged from this volunteer's calendar assignment overlays.") when no overlay exists for that volunteer. |
| V7 | `app/pages/Volunteers.tsx:187-196` (pre-fix) `recoveryState(volunteerFatigue)` fallback | Recovery status label/tone derived from the fabricated fatigue in V6 when no `recoveryRows` exist | Volunteer card recovery badge | Now renders an explicit `{ label: "Recovery unknown", tone: slate }` state when `volunteerFatigue` is `null`, matching the "Unknown" pattern `normalizeRecoveryStatus` already uses in `lib/api.ts`. |

**Note on V4/V5 (QR/feedback summary aggregates):** by the plan's own rubric
("not every zero is a violation... a zero is acceptable when it is a true
measured zero"), a strict reading would classify most of these top-level
*counts* as `measured-zero-ok` — they are backend-computed aggregates (sums
over real event logs), and 0 rows / 0 scans is a legitimate state, not
withheld evidence. However, the plan's "Out of scope" section explicitly
instructs: *"Removing `emptyQrStatsSummary`/`emptyFeedbackStatsSummary`
callers' pages — convert the summaries' fields to nullable like the rest."*
That is a direct instruction from the plan authors, not left to this card's
judgment call, so it is implemented as a violation-and-fix regardless of the
narrower measured-zero-ok reading. The practical benefit is real even under
the narrower reading: it eliminates `emptyQrStatsSummary()` /
`emptyFeedbackStatsSummary()` as fabricated all-zero placeholder objects, and
it closes the accepted/declined narration gap described in V5.

## measured-zero-ok (left in place, with reason)

| File:Line | Coercion | Reason |
|---|---|---|
| `lib/api.ts:617` `assignment_count` in `normalizeCalendarEvent` | `Math.max(parseNumber(... ?? assignedVolunteers.length), assignedVolunteers.length)` | Fallback is the *parsed* `assigned_volunteers` array length (real evidence already extracted from the payload), not a bare zero. Rendered as "N assigned" in `Calendar.tsx`/`CoordinatorEvents.tsx`. Calendar's core fetch already fails the whole page (not silently zeros) on a fetch error, so within a successful fetch a 0-length array is a genuine "no volunteers assigned yet." |
| `lib/api.ts:774-849` per-entry `QrCodeAsset` and `QrStatsSummary` — see V3/V4 above for the *converted* fields; the *entries-derived-sum* fallback path inside `normalizeQrStats` | When the raw total is absent but every entry reports a real (non-null) count, summing them is a legitimate derived measurement, not a guess. Only degrades to `null` when entries themselves are absent/incomplete. |
| `Dashboard.tsx`/`Pipeline.tsx` reduce accumulators (`(current?.count ?? 0) + 1`, `(acc[region] ?? 0) + 1`, etc. — originally at old `Dashboard.tsx:144,160,212,232`, `Pipeline.tsx:118`, `CrawlerFeed.tsx:242`, `coordinator/CoordinatorHome.tsx:106`, `Calendar.tsx:575,577`) | Standard `Map`/accumulator initialization pattern over a dataset that is already fully fetched (or the whole page fails first). `?? 0` here means "we haven't seen this key yet in the loop," not "the API omitted this count." |
| `Volunteers.tsx` (pre-fix line 199) `Number(row.match_score \|\| 0)` | `PipelineRecord.match_score` is a core field of an already-fetched pipeline row (not a supplementary/optional aggregate); a malformed/absent value here would indicate a corrupt record, not withheld evidence in the ADR-0011 sense. Left as-is; flagged for a follow-up if `match_score` is ever made explicitly optional by the backend contract. |
| `Dashboard.tsx` (pre-fix line 544) `funnelData.find(...)?.value ?? 0` (`memberInquiryDemoCount`) | `funnelData` is derived from the fully-fetched pipeline dataset; a stage with zero matching records is a real zero. |
| `Dashboard.tsx` (pre-fix line 967) `region.eventCount \|\| 0` | `regionalPulse` is computed entirely from already-validated `calendarEvents`/`calendarAssignments`; not a network-boundary coercion. |
| `lib/api.ts` `normalizeFeedbackTrend`, `normalizeFeedbackAdjustment`, `normalizeFeedbackWeightSnapshot`, `decline_reasons`/`event_outcomes` entries | Not named in the plan's problem statement (only `normalizeQrCodeAsset`/`normalizeQrStats`/`normalizeFeedbackStats` top-level fields were named). These are nested per-row chart/list data where "record exists but field is missing" cannot currently be distinguished from "record doesn't exist" without backend contract changes. Left as `parseNumber(..., 0)`; recorded here as a known gap for a follow-up plan rather than silently unclassified. |

## layout-ok (no evidentiary claim, or unconsumed)

| File:Line | Coercion | Reason |
|---|---|---|
| `lib/api.ts:470` `parseNumber` definition | The utility itself; still used by every `layout-ok`/`measured-zero-ok` call site above. Not deleted per the card's explicit instruction. |
| `lib/api.ts:490` `parseNumberMap` (`parseNumber(raw, NaN)`) | Already drops unparsable entries from the weights map instead of zero-filling them — this is the *correct* pre-existing pattern, not a violation. |
| `lib/api.ts:607` `coverage_ratio` in `normalizeCalendarEvent` | Computed but **never rendered anywhere** in the current app (`rg coverage_ratio` outside `api.ts` returns nothing). No evidentiary claim is made because there is no consuming surface. |
| `lib/api.ts:621` `open_slots` in `normalizeCalendarEvent` | Rendered only behind `event.open_slots > 0 &&` in `CoordinatorEvents.tsx`. Whether the value is a real 0 or a coerced-missing 0, the UI renders nothing in both cases — no measurement claim is ever displayed either way, so there is no distinguishable violation to fix at this call site. |
| `lib/api.ts:677/750` `event_cadence` (calendar assignment + volunteer recovery) | Rendered as `assignment.event_cadence \|\| "n/a"` in `Calendar.tsx` — the page already treats `0`/missing identically as "n/a," so no false "0" measurement is ever shown. |
| `lib/api.ts:672-675/711-714` `days_since_last_assignment` | Already null-safe in the existing code (`record.x == null && record.y == null ? null : parseNumber(...)`) — this is the pattern the rest of the file is being brought up to. Not rendered by any current page. |
| `lib/api.ts:676/715` `travel_burden` | `rg travel_burden` outside `api.ts` returns nothing — unconsumed. |
| `lib/api.ts:694/710/716-717,726-751` `VolunteerRecoverySummary` fields, `RankedMatch`/`MatchScore` fields (`score`, `rank`, `volunteer_fatigue`) | `VolunteerRecoverySummary`/`fetchVolunteerRecovery` are exported but have zero consumers anywhere in `app/`. `RankedMatch`/`MatchScore` feed `/api/matching/*` endpoints, explicitly out-of-scope (see below) — also unconsumed numerically (`OutreachWorkflowModal.tsx` only uses `RankedMatch` for name/title/company display, never its scores). Fixed the arithmetic in `normalizeVolunteerRecovery` to be null-safe (filters out assignments with unknown fatigue before averaging) purely so the file continues to typecheck now that `CalendarAssignmentSummary.volunteer_fatigue` is nullable — this is a type-safety necessity, not a behavior change to a rendered surface. |
| `Dashboard.tsx`/`Pipeline.tsx` `Number(record.stage_order) \|\| 0` (sort key) | Used only as an internal sort key when grouping funnel stages, never displayed. |
| `AgenticOutreachPanel.tsx:112` `step ?? 0` | Outreach workflow step tracker — outreach is explicitly out-of-scope. |
| `components/ui/progress.tsx:25` `${100 - (value \|\| 0)}%` | Generic shadcn-style `Progress` primitive; makes no evidentiary claim itself — any claim belongs to the (single, unrelated `StudentRewards.tsx`) caller, which was not a Z1 grep hit and is outside the fenced pages for this plan. |
| `components/FeedbackForm.tsx:107` `Number(coordinatorRating)` | Parses a live form input value, not API evidence. |
| `app/components/provenance/MetricValueDisplay.tsx` `formatNumber(value.value)` | Part of the ADR-0011 "Unknown" rendering solution itself (only ever called for `known`/`at_least` variants); not part of the problem. |
| `Volunteers.tsx:103-109` `stageWeights` constant | Left in place though now otherwise unused after V6's fix removed its only caller (`weightedLoad`). Harmless dead code; removing it was judged out of the Z3c fence (not a coercion, no behavior change) and left to avoid unrelated churn. |

## out-of-scope (matching / crawler / outreach)

Per the plan: *"The legacy `/api/*` endpoints themselves (matching, crawler,
outreach normalizers feed pages that are G1/G3-gated or slated for removal;
fix their coercions only where the Z1 inventory shows they render today)."*
None of the following render their numeric fields on any page found by this
audit, so none are fixed:

| File:Line | Coercion | Endpoint |
|---|---|---|
| `lib/api.ts:757` `normalizeRankedMatch` `rawScoreValue = Number(... ?? 0) \|\| 0` | `/api/matching/rank`, `/api/matching/rank-for-course` |
| `lib/api.ts:761` `normalizeRankedMatch` `volunteer_fatigue: ... ?? 0` | same |
| `lib/api.ts:772` `normalizeRankedMatch` `rank: Number(payload.rank ?? 0) \|\| 0` | same |
| `lib/api.ts:1195` `scoreSpeaker` `normalizeFatigue(... ?? 0)` | `/api/matching/score` |
| `CrawlerFeed.tsx:242` `(acc[v.source] ?? 0) + 1` | crawler feed accumulator |
| `CrawlerContext.tsx` (crawler state, not a Z1 grep hit but same endpoint family) | crawler |

Incidental observation (not a grep hit, out of Z1's fence, recorded for
completeness): `lib/api.ts` `fetchVolunteerProfile`/`fetchVolunteerAssignments`
(`VolunteerProfile.volunteer_fatigue`, `VolunteerAssignment.volunteer_fatigue`)
pass the raw JSON payload straight through with a TypeScript type assertion
and **no normalizer at all** — no `?? 0`/`parseNumber`/`clamp`, so this audit's
grep does not surface it, but it means a missing field would be `undefined`
at runtime despite the `number` type claiming otherwise. This is a type-safety
gap, not a zero-coercion violation, and touches `VolunteerHome.tsx`/
`VolunteerProfile.tsx` (volunteer self-service portal, not in this plan's
fenced pages). Left untouched; flagged for a separate plan.

## New seams added in Z2 (`lib/api.ts` only)

- `parseNumberOrNull(value): number | null` — returns `null` (never a
  fabricated zero) when the value is absent or unparsable. Sits beside
  `parseNumber`, which is retained for every `layout-ok`/`measured-zero-ok`
  call site above.
- `normalizeFatigueOrNull(value): number | null` — the null-aware counterpart
  to `normalizeFatigue`, used only for `CalendarAssignmentSummary.volunteer_fatigue`.

## Done-means check

- Every violation found (V1–V7) is fixed: null + explicit "Unknown"
  rendering, no fabricated `unknown_reason` strings, no 0%-width progress
  bars standing in for missing evidence.
- Every other coercion found by the mandated grep is classified above with a
  written reason (measured-zero-ok / layout-ok / out-of-scope) rather than
  silently left unclassified.
- Wave 3C behavior (`PipelineFunnelTiles.tsx`, pipeline funnel metrics,
  dashboard supplementary-metric fetch-failure handling) is untouched — this
  audit traced it for pattern reference but made no changes to it.
