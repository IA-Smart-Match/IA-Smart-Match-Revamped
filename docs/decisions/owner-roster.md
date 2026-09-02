# Owner roster — the roles nobody has been named to

**Status:** OPEN — every row below is blank. This file is the single place
those blanks live; it records no decision and names nobody.

**Prepared:** 2 September 2026, from
`docs/plans/2026-08-31-ratification-and-implementation-report.md` §5 item 2,
which states the naming is "a short, cheap act; none was named by this
session, and none may be named by an agent."

**How to use this file:** fill a row's *Named* cell with a person, commit, and
open the artifact in that row's *Closes* cell. Naming a person here does not
close their gate — it makes the gate runnable.

## The blanks

| # | Role | Named | What it blocks today | Closes via |
|---|---|---|---|---|
| 1 | **Privacy owner** (P9 Gate B) | _(blank)_ | Collect-or-drop for `Public URL`, `Point(s) of Contact (published)`, `Contact Email / Phone (published)`; T-14 incidental-PII in the crawler threat model; one of the stated reasons R3 is unsigned | `docs/decisions/p9-gate-b-contact-fields-worksheet.md` §8 |
| 2 | **Program owner** (P5 / D1 / G1 matching) | _(blank)_ | Factor registry, weights, golden cases, `unknown`-vs-zero semantics, weight-change governance. `assert_registry_approved()` stays fail-closed until this is named. **The longest pole in the portfolio.** | `docs/plans/workshops/g1-factor-registry-workshop-packet.md` (packet already complete — runs the day this is named) |
| 3 | **Rewards budget owner** (P7 / D6) | _(blank)_ | Institutional budget for the rewards path; formal D6 recording exists, budget authority does not | `docs/plans/2026-08-28-d6-rewards-s8-s9-plan.md` |
| 4 | **Product owner** (P8 opportunities, and P1 metrics) | _(blank)_ | Whether imported `row_data` is visible to every unit role (P1 Item 3); P8 opportunity actions and metrics | `docs/plans/workshops/p1-metrics-authorization-workshop-packet.md` §6; `docs/decisions/p8-opportunities-decision-draft.md` |
| 5 | **R3 signature authority** (if not the Development Lead) | _(blank)_ | R3 remains unsigned; T-27–T-29 remain CANNOT CLOSE by their own labelling | R3 signing pass — see `docs/security/` |

## Second tier — named later, blocking less

| # | Role | Named | Note |
|---|---|---|---|
| 6 | **Google Cloud IdP provisioner** (P2) | _(blank)_ | Procurement, not a workshop. Blocks every field of `docs/decisions/a1b-idp-configuration-worksheet.md` Part 1, and through it the 16 fallback-identity files in the legacy frontend. A shortened subset of Part 1 does not pass the stop-gate. |
| 7 | **Legacy-PII remediation owner** (CP-PII / D9) | _(blank)_ | `MM-A09.blocking_owner`. Explicitly **non-blocking** for current private-repository engineering; still gates D9 and `LICENSE`. Concerns a different repository. |

## The cheapest thing on this page

Row 1 is the cheapest open gate in the portfolio, and it may not need a person
at all: `p9-gate-b-contact-fields-worksheet.md` §6 records that **if all three
contact fields are dropped, no privacy owner is needed to close Gate B** —
there is nothing to be privacy owner *of*. A "drop all three" outcome closes
Gate B with Dr. Wang's signature alone.

The session's recorded working direction is "collect", which is why a privacy
owner is on this list. That direction is not a decision.

## Rows 2 and 4 are the ones with waiting packets

Both have complete meeting material sitting ready:

- Row 2 → `docs/plans/workshops/g1-factor-registry-workshop-packet.md`
- Row 4 → `docs/plans/workshops/p1-metrics-authorization-workshop-packet.md`

Neither meeting can be scheduled until its row is filled.

## References

- `docs/plans/2026-08-31-ratification-and-implementation-report.md` §3, §5
- `docs/plans/prep/blocked-work-register-830.md` §3
- `docs/decisions/pilot-decisions.md`
