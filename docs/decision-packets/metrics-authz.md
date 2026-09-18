# Metrics role-gating under ADR-0014 — aggregate versus drill-down roles

> **Decision packet — docs only. Authorizes no implementation. The register
> row(s) named here remain OPEN.**

## Decision needed

Which roles may read aggregates and which may read exact rows for the metrics
surfaces that are still ungoverned — principally the W4 engagement metric
(OQ-SE-08) and aggregate student demand (OQ-SC-13) — now that the original
§5.4 metrics-authorization question is recorded closed and implemented.

## Owner(s) of the decision

- **OQ-SE-08: Program owner + records/privacy + security owners; consider
  OQ-CBA-042 and OQ-SC-13** —
  [`../plans/open-questions/student-engagement-deferred.md`](../plans/open-questions/student-engagement-deferred.md).
- **OQ-SC-13: Program owner + records/privacy owner; consider OQ-CBA-042** —
  same register.
- **OQ-CBA-042: CBA product owner with the privacy owner** —
  [`../plans/open-questions/cba-phase-deferred.md`](../plans/open-questions/cba-phase-deferred.md).
- For the already-closed §5.4 decision, the named owners were **Product owner:
  Danny Tran (@BrooklynD23)** and **Security/privacy owner: Danny Tran
  (@BrooklynD23)** —
  [`../decisions/metrics-authorization-decision-draft.md`](../decisions/metrics-authorization-decision-draft.md)
  §1, corroborated by [`../decisions/owner-roster.md`](../decisions/owner-roster.md) row 4.
- The registers name owners by role, not by person, for the rows above. The
  individuals filling "records/privacy owner", "security owner", and "metrics
  owner" for the student program are not named in either register.

## Current safe default in force

For the rows still open —
[`../plans/open-questions/student-engagement-deferred.md`](../plans/open-questions/student-engagement-deferred.md),
both **OPEN — tentative-development**:

- **OQ-SE-08** safe default: "`{admin, coordinator}` only for any read; no Host
  access."
- **OQ-SC-13** safe default: "Connectors only; no Event Host access."
- **OQ-SE-05** safe default, which binds the same surface: "W4 STOPPED; do not
  choose counts-only or expose rows."

[`../plans/README.md`](../plans/README.md) restates the stop:

> W4 is **STOPPED** until OQ-SE-04 through OQ-SE-08 close in a way that
> satisfies accepted ADR-0011, including one registered definition, one owning
> query, and authorized exact-row reconciliation.

[`../plans/open-questions/cba-phase-deferred.md`](../plans/open-questions/cba-phase-deferred.md),
OQ-CBA-042, holds the adjacent line: "The narrow reading, deliberately. An Event
Host learning that three named professionals declined them is a fact about those
people's availability and willingness that nobody agreed to share".

The governing standing rule is
[ADR-0014](../architecture/decisions/ADR-0014-disclosure-consent.md), restated in
[`../plans/remaining-engineering-implementation-plan.md`](../plans/remaining-engineering-implementation-plan.md)
§1:

> ADR-0014 minimum disclosure applies to underlying rows and contact data.
> Aggregate access does not automatically authorize row-level payload access.

**Conflict flagged.** [`../plans/remaining-engineering-implementation-plan.md`](../plans/remaining-engineering-implementation-plan.md)
§2 row 4 still classifies "Metrics role-gating vs ungated" as
**human-decision-required**, and §5.4 says "current intentional ungating remains
until the explicit product/security decision". That decision is recorded as
taken: [`../decisions/metrics-authorization-decision-draft.md`](../decisions/metrics-authorization-decision-draft.md)
reads "**Status:** **CLOSED — 2026-09-02.**" and §4 authorizes "Option B" —
`metrics.read` for "Any **active unit membership** with a role (bare
`resource_grant` **denied**)" and `metrics.drill_down` for "`admin`,
`coordinator` only". At this commit the code matches that record:
`services/api/smartmatch_api/routers/metrics.py` defines
`_DRILL_DOWN_ROLES: Final[frozenset[str]] = frozenset({"admin", "coordinator"})`
and passes it as `required_roles` on the drill-down authorizer, while
`tests/authz/test_policy_matrix.py` now declares
`INTENTIONALLY_UNGATED_OPERATIONS: frozenset[str] = frozenset()`. The plan text
has not been amended.

## Options

Neutral; each has consequences. This packet selects none, and proposes no role
list of its own.

1. **Extend the closed §5.4 policy to the new surfaces unchanged.** Apply the
   same aggregate/drill-down split to W4 and to demand aggregates.
   *Consequence:* one policy to reason about; but OQ-SE-05 and OQ-SE-07
   (suppression thresholds) are not answered by a role list, so W4 would remain
   stopped on those rows regardless.
2. **Decide the new surfaces separately and more narrowly.** Treat engagement
   and demand aggregates as their own policy. *Consequence:* honours each
   register's "Do not close a student row by implication from an OQ-CBA or OQ-E
   row"; costs a second policy matrix and a second set of allow/deny tests.
3. **Widen any of the new surfaces to a further role** (for example Event Host /
   `volunteer`, the actor OQ-SC-13 and OQ-CBA-042 both currently exclude).
   *Consequence:* this is the case OQ-CBA-042 already refused for invitation
   state; the deciding owners would have to say why demand or engagement
   aggregates differ, and §5.4's acceptance rule still applies — "No option
   becomes 'any authenticated user'; unit scope always remains."
4. **Leave the new surfaces at their safe defaults.** *Consequence:* W4 and
   wider demand visibility stay blocked; no disclosure risk is taken.

## Evidence needed to close

From [`../plans/open-questions/student-engagement-deferred.md`](../plans/open-questions/student-engagement-deferred.md):

- **OQ-SE-08** — "Approved role matrix and allow/deny tests for aggregate and
  exact-row routes".
- **OQ-SC-13** — "Role matrix, privacy decision, allow/deny tests".
- Closure discipline for both: "Closure requires an attributed, dated decision
  artifact plus the evidence named in the row" and "Safe defaults remain active
  until closure evidence lands. A plan, prototype, feature flag, or unwired
  implementation is not closure evidence."

From [`../plans/remaining-engineering-implementation-plan.md`](../plans/remaining-engineering-implementation-plan.md)
§5.4, the four questions any metrics-authorization decision record must answer:

> 1. May any active unit membership read aggregates?
> 2. May a bare unit resource grant read aggregates?
> 3. Which roles may read underlying rows such as `review_item.row_data`?
> 4. Must particular metrics have a stricter drill-down policy than others?

and its acceptance criteria, including "Wrong-role, sibling-unit, suspended,
cross-tenant, expired-membership, and explicit-deny cases are tested" and
"Authorized drill-down count still equals the aggregate."

One further item, needed for this packet's question and in neither list: a dated
statement reconciling §2 row 4's "human-decision-required" classification with
the closed 2026-09-02 record and the code that implements it.

## What stays blocked until closure

- **W4 and engagement reporting** — the "Blocked slices" column for OQ-SE-04
  through OQ-SE-08.
- **Wider demand visibility** — OQ-SC-13's blocked slice.
- Per [`../plans/remaining-engineering-implementation-plan.md`](../plans/remaining-engineering-implementation-plan.md)
  §5.4: "Do not silently mirror imports or silently bless the status quo."
- Per OQ-CBA-042: "An Event Host-facing view of their request's outcome; and any
  status on a Speaker Request that reflects invitation responses."

## Source links

- [`../plans/open-questions/student-engagement-deferred.md`](../plans/open-questions/student-engagement-deferred.md) — OQ-SE-04 to OQ-SE-08, OQ-SC-13, closure discipline
- [`../plans/open-questions/cba-phase-deferred.md`](../plans/open-questions/cba-phase-deferred.md) — OQ-CBA-042
- [`../plans/remaining-engineering-implementation-plan.md`](../plans/remaining-engineering-implementation-plan.md) — §1, §2 row 4, §5.4
- [`../plans/2026-08-28-metrics-authz-plan.md`](../plans/2026-08-28-metrics-authz-plan.md) — stop-gate, current state, branch selection
- [`../plans/workshops/p1-metrics-authorization-workshop-packet.md`](../plans/workshops/p1-metrics-authorization-workshop-packet.md) — preparation input
- [`../decisions/metrics-authorization-decision-draft.md`](../decisions/metrics-authorization-decision-draft.md) — closed 2026-09-02, Option B
- [`../architecture/decisions/ADR-0014-disclosure-consent.md`](../architecture/decisions/ADR-0014-disclosure-consent.md) — disclosure consent, audience scope
- [`../architecture/decisions/ADR-0011-accountable-numbers.md`](../architecture/decisions/ADR-0011-accountable-numbers.md) — one owning query, drill-down equals aggregate
- [`../plans/README.md`](../plans/README.md) — W4 STOPPED
