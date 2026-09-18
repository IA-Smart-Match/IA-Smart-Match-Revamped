# G1 — matching factor registry: factors, weights, golden cases, program owner

> **Decision packet — docs only. Authorizes no implementation. The register
> row(s) named here remain OPEN.**

## Decision needed

Whether the D1/G1 matching registry item is confirmed closed by the 2026-09-03
ratification, or reopened for a named ongoing weight-governance decision — the
two authorities in this repository disagree about its state.

## Owner(s) of the decision

- **Program owner (P5 / D1 / G1 matching): Danny Tran (@BrooklynD23)**, named
  2026-09-02 in [`../decisions/owner-roster.md`](../decisions/owner-roster.md)
  row 2.
- [`../plans/2026-08-28-g1-matching-m1-m10-plan.md`](../plans/2026-08-28-g1-matching-m1-m10-plan.md)
  requires the decision artifact be "ratified or signed by a **named IA West
  program owner** (the repository's self-assigned interim owner does not
  qualify)". Whether the named owner above satisfies that phrase is part of
  what this packet asks, and this packet does not decide it.
- [`../plans/remaining-engineering-implementation-plan.md`](../plans/remaining-engineering-implementation-plan.md)
  §5.1 additionally requires recording "who may change approved weights"; no
  separate weight-governance owner is named apart from the program owner above.

## Current safe default in force

**Two sources conflict. Both are quoted; this packet resolves neither.**

Source A —
[`../plans/remaining-engineering-implementation-plan.md`](../plans/remaining-engineering-implementation-plan.md)
§2, row 1, classifies matching/scoring (G1) as **blocked-on-stakeholder**:

> D1/G1 requires a named program owner to approve factors, weights, and golden
> cases.

and §1 states the standing rule:

> Matching remains fail-closed while `factor_registry.REGISTRY_STATUS ==
> "proposed"`. Never port or characterize against the legacy scoring engine,
> whose maximum attainable score is 0.90.

Source B —
[`../plans/workshops/g1-workshop-output-worksheet.md`](../plans/workshops/g1-workshop-output-worksheet.md):

> **Status: RATIFIED — 2026-09-03.** Gate G1 / D1 closed. M1 complete in code.

with a sign-off block recording surviving factor keys and final weights
(Stage B sum = 1.0), Q6 answered for `historical_conversion` and
`student_interest`, `zero_classification` for every symptom zero, a tie-break
rule, and "Named program owner for ongoing weight governance recorded."
[`../decisions/owner-roster.md`](../decisions/owner-roster.md) row 2 agrees:
"**G1 closed 2026-09-03**".

**Conflict flagged.** The plan's fail-closed condition keys on
`REGISTRY_STATUS == "proposed"`; at this commit
`python/smartmatch_domain/smartmatch_domain/factor_registry.py` line 149 reads
`REGISTRY_STATUS: Final[str] = "approved"`, so that condition no longer selects
the fail-closed branch. The plan text has not been amended to record this. A
reader of the plan alone would conclude matching is still gated; a reader of the
worksheet and the code would conclude it is not.

## Options

Neutral; each has consequences. This packet selects none.

1. **Confirm closure as recorded.** Ratify that the 2026-09-03 worksheet is the
   G1/D1 decision artifact of record and that no further factor or weight
   approval is outstanding. *Consequence:* the §2 row-1 and §5.1 "blocked" text
   in the remaining-engineering plan becomes stale and needs a dated
   supersession note under the rule in
   [`../plans/README.md`](../plans/README.md) ("add a dated supersession/
   current-state note pointing to the new authority"); nothing about the
   approved weights changes.
2. **Confirm closure but name a separate weight-governance owner.** Accept the
   ratified factors and weights, and separately record who may change an
   approved weight and how a change is recorded, per §5.1's fourth requirement.
   *Consequence:* adds a governance artifact; does not reopen the approved
   values.
3. **Reopen the item.** Rule that the 2026-09-03 ratification does not meet the
   G1 plan's "named IA West program owner" bar. *Consequence:* the approved
   weights and golden cases carry an unratified status; the plan's do-not-build
   list in §5.1 would govern again, against code whose `REGISTRY_STATUS` is
   already `"approved"` — the owner would have to say what happens to that code,
   which this packet does not propose.

## Evidence needed to close

From
[`../plans/2026-08-28-g1-matching-m1-m10-plan.md`](../plans/2026-08-28-g1-matching-m1-m10-plan.md)
(stop-gate) and
[`../plans/remaining-engineering-implementation-plan.md`](../plans/remaining-engineering-implementation-plan.md)
§5.1, a closing artifact contains, non-blank:

1. the named program owner;
2. the approved factor list and weights, including the explicit fate of
   `historical_conversion` and `student_interest` (Q6);
3. approved golden cases with expected outputs, classifying the three
   stakeholder symptoms — the 43% tie, "Topic Relevance 0%", "Match Depth 0" —
   each zero labeled measured-zero or unknown per
   [ADR-0011](../architecture/decisions/ADR-0011-accountable-numbers.md);
4. weight governance: who may change approved weights, and how changes are
   recorded.

The G1 plan also states: "`docs/plans/workshops/g1-factor-registry-workshop-packet.md`
is preparation, not approval" and "`tests/unit/test_gate_decision_artifacts.py`
checks packet completeness — passing it does not signify approval."

For this packet's question, one further item is needed and is not in either
list: a dated statement reconciling the plan's "blocked-on-stakeholder"
classification with the worksheet's "RATIFIED" status.

## What stays blocked until closure

Under option 3 only, the §5.1 do-not-build list would apply:

> do not flip `REGISTRY_STATUS`, port the legacy engine, implement
> optimizer-backed match runs, or expose any score/rank until G1 closes.

Under options 1 and 2, nothing in this packet blocks; the outstanding
matching work is sequenced by §5.1's "After written approval" list (M1 through
M9/M10) and by
[`../plans/2026-08-28-g1-matching-m1-m10-plan.md`](../plans/2026-08-28-g1-matching-m1-m10-plan.md)'s
task cards, neither of which this packet authorizes.

Separately and regardless of the option chosen: the **student** registry is a
different registry with its own gate — see
[`oq-se-01-02-student-ranking.md`](oq-se-01-02-student-ranking.md) and
[ADR-0024](../architecture/decisions/ADR-0024-staged-student-event-recommender.md)
D2, which states `PROHIBITED_INPUTS` "is **imported** by the student registry,
never copied."

## Source links

- [`../plans/remaining-engineering-implementation-plan.md`](../plans/remaining-engineering-implementation-plan.md) — §1 standing rules, §2 row 1, §5.1
- [`../plans/2026-08-28-g1-matching-m1-m10-plan.md`](../plans/2026-08-28-g1-matching-m1-m10-plan.md) — stop-gate, current state, card M1
- [`../plans/workshops/g1-workshop-output-worksheet.md`](../plans/workshops/g1-workshop-output-worksheet.md) — RATIFIED status and sign-off block
- [`../plans/workshops/g1-factor-registry-workshop-packet.md`](../plans/workshops/g1-factor-registry-workshop-packet.md) — preparation, not approval
- [`../decisions/owner-roster.md`](../decisions/owner-roster.md) — row 2, program owner
- [`../architecture/decisions/ADR-0011-accountable-numbers.md`](../architecture/decisions/ADR-0011-accountable-numbers.md) — unknown is not zero; one canonical name; one owning query
- [`../architecture/decisions/ADR-0016-cba-scoring-policy.md`](../architecture/decisions/ADR-0016-cba-scoring-policy.md) — neutral Topic score, proximity bands, `REGISTRY_VERSION` pin policy
- [`../plans/README.md`](../plans/README.md) — supersession discipline for dated plans
