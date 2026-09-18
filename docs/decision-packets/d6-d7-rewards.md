# D6 / D7 — rewards: budget owners, funding confirmation, and calibration N

> **Decision packet — docs only. Authorizes no implementation. The register
> row(s) named here remain OPEN.**

## Decision needed

Whether to ratify the tentative D7 points economy (earn rate, reward bands, and
calibration N) and confirm the institutional funding that D6 closed only as a
placeholder, so that a catalog item may be listed.

## Owner(s) of the decision

- **Rewards budget owner (P7 / D6): Danny Tran (@BrooklynD23)**, named
  2026-09-02 — [`../decisions/owner-roster.md`](../decisions/owner-roster.md)
  row 3 and [`../decisions/d6-rewards-budget-decision-record.md`](../decisions/d6-rewards-budget-decision-record.md) §1.
- **IA West Coordinator** — "remains operational administrator" per the same
  record's header. No individual is named for that office in that record.
- **OQ-SC-01 owners: Ann + Yuka; Danny as D6 budget owner** —
  [`../plans/open-questions/student-engagement-deferred.md`](../plans/open-questions/student-engagement-deferred.md),
  OQ-SC-01.
- D7 ratification is assigned to the "program-owner" by
  [`../plans/2026-08-28-d6-rewards-s8-s9-plan.md`](../plans/2026-08-28-d6-rewards-s8-s9-plan.md)
  stop-gate item 2; the program owner of record is Danny Tran (@BrooklynD23)
  ([`../decisions/owner-roster.md`](../decisions/owner-roster.md) row 2).
- Reward read and redemption **roles**: stop-gate item 3 records these as "TBD".
  No owner named.

## Current safe default in force

[`../plans/open-questions/student-engagement-deferred.md`](../plans/open-questions/student-engagement-deferred.md),
OQ-SC-01, status **OPEN — tentative-development**, safe default:

> Catalog remains empty; only funded items are listable.

[`../architecture/decisions/ADR-0013-attendance-derived-engagement.md`](../architecture/decisions/ADR-0013-attendance-derived-engagement.md)
fixes the structural rule:

> `reward_item` carries `fulfilment_cost`, `budget_owner_id`, and `funded`. An
> item whose fulfilment costs the program money **cannot be listed** without
> both.

and on N:

> **The cheapest reward is reachable within N events**, where N is a parameter
> set by the program owner. Proposed default: **3**. … N itself is **not decided
> here** — it is D7, and the recommendation is a recommendation.

[`../decisions/d6-rewards-budget-decision-record.md`](../decisions/d6-rewards-budget-decision-record.md)
header:

> **Status:** **CLOSED — 2026-09-02 (pilot scope).** Danny Tran (@BrooklynD23)
> named institutional budget owner. **$5,000** placeholder ceiling ratified
> pending institutional funding confirmation — **not** a ratified figure. IA
> West Coordinator remains operational administrator. D7 remains tentative and
> is **not** promoted by this record.

[`../decisions/pilot-decisions.md`](../decisions/pilot-decisions.md) §"D7 —
points and rewards (tentative)" records the tentative numbers:

| | Tentative value |
|---|---|
| Earning rate | **100 points per verified attendance** |
| Initial reward bands | **300 / 600 / 1,000 points** |
| Calibration N | **3** — the cheapest reward is reachable in three events |

with the property `min(points_cost over listed items) ≤ N × points_per_event`
holding "by construction: **3 × 100 = 300**, which is the cheapest band exactly."

**Conflict flagged.** [`../plans/remaining-engineering-implementation-plan.md`](../plans/remaining-engineering-implementation-plan.md)
§2 row 3 still classifies rewards as blocked because "D6 must name budget owners
and D7 must choose calibration N"; D6 is recorded closed for pilot scope, while
D7 remains explicitly tentative. The plan has not been amended to distinguish
the two.

## Options

Neutral; each has consequences. This packet selects none. **No values are
proposed here** — the numbers above are quotations of an existing tentative
record, not recommendations.

1. **Ratify D7 as it stands and confirm funding.** Promote the tentative earn
   rate, bands, and N to ratified, and replace the $5,000 placeholder with a
   confirmed institutional figure. *Consequence:* the stop-gate's items 2 and 1
   are both satisfied; a catalog may be populated subject to the roles decision
   and to S6/S7; the calibration test has a number to assert against.
2. **Ratify D7 with different values.** Same as option 1, with the earn rate,
   bands, or N changed by the deciding owner. *Consequence:* identical to
   option 1 in structure; the calibration property must be restated and
   re-checked, and per ADR-0013 "The legacy catalog's seven items carry forward
   as content to re-price, not as values."
3. **Confirm funding but leave D7 tentative.** *Consequence:* the budget owner
   and funded balance exist, but no item can be priced, so OQ-SC-01's safe
   default ("catalog remains empty") continues to bind.
4. **Leave both open.** *Consequence:* the status quo; the rewards surface
   remains unshippable and OQ-SC-01 stays OPEN — tentative-development.

Each of options 1–3 also requires the separate, currently-TBD decision on
**reward read and redemption roles** (stop-gate item 3), which no option
above supplies.

## Evidence needed to close

From
[`../plans/2026-08-28-d6-rewards-s8-s9-plan.md`](../plans/2026-08-28-d6-rewards-s8-s9-plan.md)
(stop-gate):

1. **D6** — "every proposed listable item has a **named human budget owner**
   represented by a real same-tenant `user_account`, with written confirmation
   of funded balance and fulfilment commitment. A blank worksheet is the honest
   pre-workshop state and selects nothing."
2. **D7** — "program-owner ratification of: points per verified attendance,
   calibration N ('cheapest reward reachable within N events' — ADR-0013's 3 is
   a proposal, not approval), item point costs, and catalog content."
3. "Reward read and redemption **roles** decided (the prep contract labels these
   TBD)."

From [`../plans/open-questions/student-engagement-deferred.md`](../plans/open-questions/student-engagement-deferred.md),
OQ-SC-01 closure evidence:

> Dated owner decision; funded catalog and calibration evidence

The plan also records the prerequisite engineering, which is not a decision:
"**S6** attendance-derived point evidence and **S7** server-side ledger fold
must exist before S8/S9."

## What stays blocked until closure

Per [`../plans/remaining-engineering-implementation-plan.md`](../plans/remaining-engineering-implementation-plan.md)
§5.3:

> **Do not build yet:** no listable catalog content, redemption UI, or repriced
> legacy catalog before D6/D7 and S6/S7.

Per OQ-SC-01's "Blocked slices" column: **Rewards activation**.

Per [`../plans/2026-08-28-d6-rewards-s8-s9-plan.md`](../plans/2026-08-28-d6-rewards-s8-s9-plan.md)'s
31 August amendment header: cards "L1–L4, C1, R3, U1 … (ledger fold, listing,
redemption) remain gated on D6/D7/role artifacts … No new budget envelope,
commitment, reservation, redemption, earning, catalog, route, or UI behavior is
authorized."

## Source links

- [`../plans/open-questions/student-engagement-deferred.md`](../plans/open-questions/student-engagement-deferred.md) — OQ-SC-01, closure discipline
- [`../plans/remaining-engineering-implementation-plan.md`](../plans/remaining-engineering-implementation-plan.md) — §2 row 3, §5.3
- [`../plans/2026-08-28-d6-rewards-s8-s9-plan.md`](../plans/2026-08-28-d6-rewards-s8-s9-plan.md) — standing constraints, stop-gate, 31 August amendment
- [`../architecture/decisions/ADR-0013-attendance-derived-engagement.md`](../architecture/decisions/ADR-0013-attendance-derived-engagement.md) — ledger, budget owner, calibration property
- [`../decisions/d6-rewards-budget-decision-record.md`](../decisions/d6-rewards-budget-decision-record.md) — D6 closure for pilot scope
- [`../decisions/pilot-decisions.md`](../decisions/pilot-decisions.md) — §D6, §D7 (tentative)
- [`../decisions/owner-roster.md`](../decisions/owner-roster.md) — rows 2 and 3
- [`../architecture/engagement-model.md`](../architecture/engagement-model.md) — calibration arithmetic
