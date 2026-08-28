# Plan portfolio index — 2026-08-28

**Branch baseline:** `friday-deliverable-828` · **Design:**
`2026-08-28-plan-portfolio-design.md`
**Purpose:** execution order, dependency graph, worktree map, and
shared-resource ownership for plans P1–P9. An orchestrator picks up plans from
here; each plan file is self-contained for its executor.

## The portfolio

| Id | Plan file | Gate | Can start |
|---|---|---|---|
| P1 | `2026-08-28-metrics-authz-plan.md` | ratified metrics-authz decision | after workshop |
| P2 | `2026-08-28-a1b-institutional-sign-in-plan.md` | IdP configuration decision | card A0 now; rest after decision |
| P3 | `2026-08-28-adr0011-zero-coercion-cleanup-plan.md` | none | **now** |
| P4 | `2026-08-28-performance-caching-plan.md` | staged (measurement entry conditions) | **now** (Stage 0 + Stage 1) |
| P5 | `2026-08-28-g1-matching-m1-m10-plan.md` | D1/G1 signed artifact | after workshop |
| P6 | `2026-08-28-g3-events-s3-s5-plan.md` | G3 decision + signed R3 threat model | after workshop |
| P7 | `2026-08-28-d6-rewards-s8-s9-plan.md` | D6 + D7 artifacts (+ roles) | after workshop |
| P8 | `2026-08-28-opportunities-s12-plan.md` | written opportunities definition | after definition; may inherit P5/P6 |
| P9 | `2026-08-28-pilot-columns-plan.md` | Dr. Wang gates A and B (independent) | after decisions; W1 after either |

## Dependency graph

```
Workshops (human, parallel):  metrics-authz · IdP · D1/G1 · G3+R3 · D6/D7 · opportunities-def · Dr.Wang columns

Now:            P3 (ADR-0011 cleanup)      P4 Stage 0 + Stage 1        P2 card A0
After decision: P1                          P2 (A1–A4)                  P9 (branches per gate) → W1
After gates:    P5 (M1→M2–M6∥→M7→M8→M9/M10)
                P6 (S3→S4∥S5→S5f→S6)
                P7 (L1→L2∥L3→L4→C1→R3→U1)
                P8 (O1→O2→O3→O4∥)  [BRANCH-SCORE-FLOOR additionally needs P5·M8]
Cross-plan:     P4 Stage 2 consumes P8's S12 read model (P8 owns it)
                P4 Stage 3 (Redis ADR) only after Stage 1–2 measurements miss budget
                P2·A2 provides the sign-out hook P4·F1 requires (queryClient.clear)
                P8·O4a and P9·Branch B both touch Opportunities.tsx → P8 owns the file; P9 records notes only
```

## Worktree map

Create each worktree off `friday-deliverable-828`:

```
git worktree add ../ia-plan-metrics-authz   -b plan/metrics-authz
git worktree add ../ia-plan-a1b-sign-in     -b plan/a1b-sign-in
git worktree add ../ia-plan-adr0011         -b plan/adr0011-cleanup
git worktree add ../ia-plan-perf            -b plan/perf-caching
git worktree add ../ia-plan-g1-matching     -b plan/g1-matching
git worktree add ../ia-plan-g3-events       -b plan/g3-events
git worktree add ../ia-plan-d6-rewards      -b plan/d6-rewards
git worktree add ../ia-plan-s12             -b plan/opportunities-s12
git worktree add ../ia-plan-columns         -b plan/pilot-columns
```

Within one plan, subagents share the plan's worktree; lanes are fence-isolated.
Merging plan branches back into `friday-deliverable-828` is a human-authorized
step, one branch at a time, respecting the serial resources below.

## Serial resources (single ownership; never parallel)

| Resource | Rule | Ownership order |
|---|---|---|
| Migration numbers (`db/migrations/versions/`) | one open migration card portfolio-wide at a time | P6·S3 → P6·S5f → P6·S5m (optional tag/review schema) → P7·L1/L2 → P5·M8a → P8·O2 → P9·A2a (re-sequence at merge time as gates actually close; renumber on rebase) |
| `contracts/openapi/smartmatch.json` regeneration | regenerate + `make openapi-check` in exactly one card per plan; never hand-edit | P1 join card, P4·F3, P5·M8b, P6·S6b, P7·R3, P8·O3 |
| `tests/authz/test_policy_matrix.py` | rows travel with routes in the same commit; merge conflicts resolved by re-running completeness meta-tests | any plan adding routes |
| `tests/unit/test_matching_fail_closed.py` (fail-closed scans) | each deliberate flip happens in the commit that lands the gated capability | P5·M8b, P6·S6b, P7·R3, P4·C1 (extends only) |
| `apps/web/legacy-frontend/src/lib/api.ts` | P3 owns the normalizer layer; P4·F1/F3 own client/cache concerns; P2·A2 owns the auth-header section — coordinate merges in this order: P3 → P4 → P2 | as listed |
| `Opportunities.tsx` | P8·O4a owns it | P9 records notes only |
| `tests/contract/test_metrics.py` | additive per plan; P8·O3 owns the pipeline-unknown flip | P1, P4·F3, P8 |

## Recommended execution order (engineering; workshops run in parallel throughout)

1. **Now:** P3 and P4 (Stage 0 + Stage 1) in parallel worktrees; P2 card A0.
2. **As each decision lands:** P1 (small, high leverage), P2 (A1–A4), P9.
3. **As gates close:** P6 and P7 can run in parallel (disjoint domains,
   coordinated migrations); P5 in parallel with both; P8 last of the gated set
   (it may consume P5·M8 and P6 events, and P4 Stage 2 waits on its read model).
4. **Continuously:** re-run the evidence ladder per plan; CI on push is the
   integration gate (a human must request any push).

## Dr. Wang requirement mapping

| Requirement | Where satisfied |
|---|---|
| Fast loading after sign-in and on metrics surfaces | P4 (budgets R1–R6); P2 removes the fake-session path; P3 keeps honest values |
| No 5–10 s crawler-style lag ever again | P4·C1 executable invariant; P6's worker-only crawl design |
| Honest metrics with drill-down | Wave 3C (done) + P1 (authz decided) + P8 (opportunities canonical) |
| Matching she can trust | P5 (only after her/owner-approved registry + goldens) |
| Pilot data contract | P9 + W1 wiring |
| Rewards that are real | P7 (owned, funded, reachable) |

## Standing constraints (apply to every plan)

No push, no PR, no merge, no deploy, no live providers/data, no production
credentials, no production-readiness claims, no legacy scoring-engine port or
characterization, no caller-chosen identity, unknown never becomes zero, and
gated surfaces stay fail-closed until their written artifacts pass. Workshops
— not engineering capacity — are the limiting factor for P1, P5, P6, P7, P8,
and P9.
