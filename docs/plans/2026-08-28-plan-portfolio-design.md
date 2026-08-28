# Plan-portfolio design — agent-executable implementation plans

**Date:** 2026-08-28
**Branch:** `friday-deliverable-828` (design written at HEAD `266c1e6`)
**Status:** validated design for the planning deliverable; this document does not
authorize implementation, deployment, a pull request, or a push.
**Validated with:** the user, in the 2026-08-28 planning session, section by
section.

## Purpose

Convert the diagnosis and sequencing documents already on this branch
(`remaining-engineering-brief.md`, `remaining-engineering-implementation-plan.md`,
`g1-g3-d6-remedy-plan.md`, `orchestrator-handoff.md`) into **self-contained,
agent-executable implementation plans** — one per remaining backlog item — plus
one new plan for a stakeholder requirement raised in this session: Dr. Wang
requires fast loading of the web portal ("performance & caching").

Each plan is written for a frontier orchestrator agent running in high
reasoning that delegates fenced task cards to low-level subagents in parallel.

## Deliverable: the plan portfolio

Ten files under `docs/plans/`:

| # | File | Covers | Gate style |
|---|---|---|---|
| 0 | `2026-08-28-plan-portfolio-index.md` | Dependency graph, execution order, worktree/branch map, shared-resource ownership | n/a |
| 1 | `2026-08-28-metrics-authz-plan.md` | Metrics read/drill-down authorization | conditional branches |
| 2 | `2026-08-28-a1b-institutional-sign-in-plan.md` | Real IdP sign-in; fallback-identity removal | stop-gated on identity decision |
| 3 | `2026-08-28-adr0011-zero-coercion-cleanup-plan.md` | Residual `?? 0` coercion in the legacy-frontend request seam | none (implement-now) |
| 4 | `2026-08-28-performance-caching-plan.md` | Fast-loading requirement; staged caching | staged, measurement-gated |
| 5 | `2026-08-28-g1-matching-m1-m10-plan.md` | Matching M1–M10 | stop-gated on D1/G1 artifact |
| 6 | `2026-08-28-g3-events-s3-s5-plan.md` | Event persistence S3–S5, review queue, constrained crawler | stop-gated on G3 + R3 sign-off |
| 7 | `2026-08-28-d6-rewards-s8-s9-plan.md` | Ledger fold, S8 listing, S9 redemption | stop-gated on D6/D7 + S6/S7 |
| 8 | `2026-08-28-opportunities-s12-plan.md` | Canonical opportunities metric + S12 persistence | stop-gated on written definition; conditional on score-floor (G1 inheritance) |
| 9 | `2026-08-28-pilot-columns-plan.md` | `board_role` model; public URL / contact fields | conditional branches per Dr. Wang decision |

Self-containment rule: an executing agent needs only its plan file plus the
repository — no chat history. Every plan restates the standing constraints
(no push, no PR, no live providers/data, no production-readiness claims, no
legacy scoring-engine port) so an excerpt cannot be misread as authorization.

## Execution model inside each plan

- **Task cards.** Numbered units of work sized for a cheap subagent: goal,
  exact file fence (files to touch and files that must not be touched), tests
  that prove the card, dependencies on other cards.
- **Parallel lanes.** Cards grouped into lanes with disjoint fences that can
  run concurrently; sequential join cards wire lanes together. Where two plans
  need the same file, the index assigns single ownership and ordering.
- **Worktrees.** Independent plans each get a git worktree off
  `friday-deliverable-828` (`plan/<topic>` branches, mapped in the index).
  Within one plan, subagents share the plan's worktree; lanes are
  fence-isolated. Migration numbering and OpenAPI regeneration are serial
  resources owned by exactly one card at a time, portfolio-wide.
- **Evidence ladder.** Every plan ends with: focused pytest → `make check` →
  `make openapi-check` when contracts change → web typecheck/build → an
  explicit list of what only CI can prove (PostgreSQL integration, clean
  `npm ci`). Plans never claim green for gates they cannot run locally; the
  Windows environment limits from `orchestrator-handoff.md` carry forward.

## Stop-gates and conditional branches

- **Stop-gate block.** Each gated plan opens with a literal checklist: the
  decision-artifact path, the fields that must be non-blank (named owner,
  approved values, sign-off), and the rule that a missing or ambiguous
  artifact means stop and report — never infer approval.
  `tests/unit/test_gate_decision_artifacts.py` is the ground truth for packet
  completeness.
- **Branch selection.** Conditional plans enumerate each decision outcome as a
  named branch with a complete task-card set. The agent selects the branch
  matching the committed artifact's content; a decision that leaves
  alternatives open selects nothing.
- **Deliberate test flips.** Guard tests designed to change on approval
  (`test_registry_is_not_yet_approved`, fail-closed OpenAPI scans) are
  inverted only as the first post-gate card, in the same commit as the
  approval landing.
- **Policy rows travel with routes.** Any card adding a route updates
  `tests/authz/test_policy_matrix.py` in the same card.

## Performance & caching design (new requirement)

Reported symptoms: slowness after sign-in; web portal and metrics lag in
demos; the old repository's Tavily/web-crawler API calls took 5–10 seconds.

- **Requirements before mechanism.** Budgets: post-sign-in to interactive
  dashboard under ~1.5 s on demo hardware; metric panels never block page
  render and always show honest loading states. Hard invariant carried from
  the legacy lag: **no crawl, LLM, or external network call on any request
  path** — enforced by an executable router/OpenAPI scan, not prose.
- **Stage 0 — measure.** Profile the post-login path and metrics endpoints;
  commit a baseline document. No optimization lands without a number.
- **Stage 1 — existing stack.** Parallelize independent metric fetches,
  route-level code splitting, frontend query cache with
  stale-while-revalidate, `ETag` / `Cache-Control: private` on metrics
  responses.
- **Stage 2 — PostgreSQL read models.** Precomputed aggregates where
  measurement shows query cost; converges with S12 rather than duplicating it.
- **Stage 3 — Redis, gated by a new ADR.** Only if Stages 1–2 miss budget:
  ADR proposing Redis in docker-compose for server-side caching.
- **Non-negotiable constraints at every stage:** cache keys always include
  principal + unit (never serve one principal's numbers to another; do not
  bake the undecided metrics-authz outcome into cache behavior). ADR-0011
  applies to staleness: cached aggregates carry computed-at provenance; the UI
  may show "as of \<time\>" but never a silently stale number presented as
  live. Session-scoped warm caching depends on A1b and is cleared on
  sign-out.

## Decisions taken in this session

1. Scope: all eight backlog items plus the performance/caching spec.
2. Caching infrastructure: staged — existing stack first; Redis only by ADR
   after measurement.
3. Gated items: full conditional plans with hard stop-gates, not prep-only
   plans.
4. Exploration model: cheap subagents (`composer-2.5-fast`) for documentation
   and code reconnaissance; plan authorship stays with the orchestrator.
