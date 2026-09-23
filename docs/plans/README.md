# Planning navigation authority

**Status:** current navigation authority, updated 2026-09-16.

This index tells contributors where current truth and planning authority live.
It does not make a dated plan active, authorize implementation, or prove that a
target capability exists.

## Start here

| Need | Authority |
|---|---|
| What is implemented, tested, proposed, or absent | Root [README](../../README.md) — the authority required by `CONTRIBUTING.md` |
| Active frontend design and integration contract | [`apps/web/DESIGN.md`](../../apps/web/DESIGN.md); OpenAPI/code still win for current HTTP behavior |
| Accepted architecture decisions | [ADR index](../architecture/decisions/README.md) |
| Tentative development direction | [Pilot decisions](../decisions/pilot-decisions.md); tentative is not organizational ratification |
| Current student-engagement program | [2026-09-14 student-engagement program](2026-09-14-student-engagement-program-plan.md) and its canonical [open-question register](open-questions/student-engagement-deferred.md) |
| Student→event recommender (slice 6, proposed) | [ADR-0024](../architecture/decisions/ADR-0024-staged-student-event-recommender.md) (Accepted 2026-09-16), [decision record](../decisions/student-recommender-decision-record.md) (draft), [contracts](../architecture/student-recommender-contracts.md), [implementation plan](../superpowers/plans/2026-09-14-student-recommender-v1-plan.md) with its [review-fixes plan](../superpowers/plans/2026-09-14-student-recommender-review-fixes.md); gated on OQ-SC-02, OQ-SE-01, OQ-SE-02 |
| Class exercise for Dr. Lin's Spring 2027 course (Ann Wang, second product scope, runs in parallel with the CBA track) | [Requirements](../product/class-exercise-requirements.md), [ADR-0025](../architecture/decisions/ADR-0025-class-exercise-scope-shares-the-matching-mechanism.md), [design spec](../superpowers/specs/2026-09-16-class-exercise-design.md), [scoped register](open-questions/class-exercise-open-questions.md); ADR-0025 D6's engine-level enforcement is recorded in the [2026-09-19 `hide_parameters` plan](../superpowers/plans/2026-09-19-engine-hide-parameters-plan.md) |
| B26 — professionals correct their own availability | DECIDED 2026-09-22 (owner): option B — build self-service availability; plan at [`2026-09-22-b26-self-service-availability-plan.md`](2026-09-22-b26-self-service-availability-plan.md). Planning only; all six follow-ups answered 2026-09-22 (Speaker accounts, D2 centered utilization). Band penalties and the Host+Speaker single login decided the same day. One owner question open: Q8, self-shortlisting on one's own request |
| Ideas logged but not scheduled | [Backlog](backlog.md) |
| Whether any `TODO`/`FIXME` marker is outstanding in code | [TODO disposition register](todo-disposition-register.md) — a 2026-09-18 survey; it recommends only, and authorizes no change |
| Which tests are skipped, why, and whether CI runs them | [Skip-site inventory 2026-09-18](skip-site-inventory-2026-09-18.md) — a dated snapshot of all 72 `skip`/`skipif`/`xfail` call sites; it authorizes no change and will drift |

These links put implementation truth, the active frontend contract, accepted
decisions, tentative direction, and the current student program within two
hops of the repository root.

## Open-question registers

- Student engagement: [canonical OQ-SC/OQ-SE register](open-questions/student-engagement-deferred.md).
- CBA matching: [CBA phase deferred register](open-questions/cba-phase-deferred.md).
- Class exercise: [scoped OQ-CE register](open-questions/class-exercise-open-questions.md); it closes no OQ-SC/OQ-SE/OQ-CBA row.
- Historical attendance/disclosure register: [engagement deferred register](open-questions/engagement-deferred.md),
  preserved as a point-in-time record; current student decisions live in the
  [canonical OQ-SC/OQ-SE register](open-questions/student-engagement-deferred.md).
- Other scoped registers remain in [`open-questions/`](open-questions/); their
  safe defaults stay active until attributed closure evidence lands.
- Workshop framing for gated items: [decision packets](../decision-packets/README.md).
  A packet frames a decision for its named owners; it closes no row, changes no
  status, and is not closure evidence.

For student engagement, the canonical register owns the open decisions. W4 is
**STOPPED** until OQ-SE-04 through OQ-SE-08 close in a way that satisfies
accepted ADR-0011, including one registered definition, one owning query, and
authorized exact-row reconciliation.

## Historical plans and status snapshots

The [2026-08-28 plan portfolio index](2026-08-28-plan-portfolio-index.md) and
[dated status reports](../status-report/README.md) are historical navigation
and evidence. The many other dated files in this directory remain preserved as
point-in-time plans, briefs, implementation records, or superseded proposals;
their presence does not make them current or active.

When a dated plan is superseded or its implementation state changes, preserve
the original evidence and add a dated supersession/current-state note pointing
to the new authority. Do not silently rewrite history, and do not infer current
implementation from a plan: reconcile it against the root README, code, schema,
and contract.

The 2026-09-14 student-engagement plan is documentation-only current planning
authority. Legal review is deferred for its internal CBA development scope but
becomes a future gate for external/public/cross-unit/live-provider/live-data
use. Privacy, records, accessibility, security, and named-owner decisions remain
constraints throughout.
