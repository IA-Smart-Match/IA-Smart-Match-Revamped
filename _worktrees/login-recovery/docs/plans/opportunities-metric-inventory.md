# Opportunities metric inventory (Fix #5 prep)

**Status:** inventory and draft register entries — **no metric implementation**.  
**Classification:** blocked-on-stakeholder (plan §5.7).  
**Rule:** ADR-0011 — one canonical name, one owning query; unknown ≠ fabricated count.

## Problem

Two surfaces label "opportunities" but use different evidence:

| Surface | Route / component | What it shows | Evidence source |
|---|---|---|---|
| Opportunities page | `/opportunities` — `Opportunities.tsx` | Merged CSV + crawler rows; fabricated crawler dates/roles | Client `fetchEvents` + legacy `/api/data/*` |
| Dashboard | `Dashboard.tsx` | Prose "active opportunities"; links to `/opportunities` | Not a registered metric |
| Pipeline funnel | `Pipeline.tsx` + `PipelineFunnelTiles.tsx` | Five funnel stages | Registered `pipeline_*` metrics — **unknown** until S12 |
| Metric register | `METRIC_REGISTER` | No `opportunities` entry | — |

Wave 3C wired Dashboard/Pipeline to accountable metrics with honest `null` +
`PIPELINE_UNKNOWN_REASON` — do not "fix" disagreement by fabricating counts.

## String inventory (legacy-frontend)

| File | Usage |
|---|---|
| `Opportunities.tsx` | Page title, list merge, "Run matcher" → `/ai-matching` (G1 blocked) |
| `Dashboard.tsx` | Copy + link to `/opportunities` (~617, 677) |
| `LandingPage.tsx` | Marketing copy (not a metric) |
| `Layout.tsx` | Nav label |
| `routes.tsx` | Route registration |
| `metrics.ts` | Maps `pipeline_*` only — no opportunities key |
| `AIMatching.tsx` | Mock ranks (H10 — G1 blocked) |
| `Outreach.tsx` | Opportunity wording in workflow copy |

Backend:

| File | Usage |
|---|---|
| `smartmatch_domain/metrics.py` | `pipeline_*`, `pending_review_items` only |
| `routers/metrics.py` | `_pipeline_funnel_rows_v1` returns unknown; no opportunities query |

## Draft register entries (definitions TBD — workshop)

Do **not** add to `METRIC_REGISTER` until written definition approved.

```python
# PLACEHOLDER — not committed to METRIC_REGISTER until S1/S12 + definition close

# MetricDefinition(
#     canonical_name="opportunities_eligible",  # name TBD
#     display_name="Opportunities",
#     definition="WORKSHOP: e.g. events eligible for publication excluding unresolved dates",
#     owning_query="opportunities_rows_v1",  # S12 persistence required
#     drill_down="Same rows as aggregate.",
#     unknown_reason=None,  # only when evidence exists
# )
```

Workshop must decide whether "opportunities" means:

- events eligible for publication,
- events in a match pool, or
- events above a score floor (**inherits G1** if score included).

Distinct UI filters need **distinct registered names** (ADR-0011 rule 2).

## S12 read model (design prep)

One persistence model should return both:

- aggregate `count(rows)` for dashboard tiles, and
- exact `rows` for drill-down (Fix #12 / S1).

Lifecycle stages (stakeholder #3): Matched → Contacted → Confirmed → Attended →
Member Inquiry — currently five separate `pipeline_*` metrics sharing
`pipeline_funnel_rows_v1` unknown stub.

## Tests to add after definition

- `tests/contract/test_metrics.py` — clicked N returns exactly N rows
- Unit isolation, authorization, zero and non-zero cases
- Unresolved dates and quarantined tags never appear in rows

## Explicit non-build

- No client-side CSV/crawler merge as canonical source.
- No `opportunities` total on Dashboard until register entry exists.
- No matcher actions until G1.

## References

- `docs/plans/remaining-engineering-brief.md` §8
- `docs/architecture/decisions/ADR-0011-accountable-numbers.md`
- `docs/plans/frontend-migration.md` Fix #5
- `python/smartmatch_domain/smartmatch_domain/metrics.py`
- `tests/contract/test_metrics.py::test_pipeline_unknown_is_null_with_an_empty_drill_down`
