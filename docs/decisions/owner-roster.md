# Owner roster — the roles nobody has been named to

**Status:** **MOSTLY CLOSED** — rows 1–5 named 2 September 2026. Rows 6–7
remain open (procurement / legacy-repo scope).
**Decision date:** 2 September 2026
**Approver:** Danny Tran (@dangt)

**Prepared:** 2 September 2026, from
`docs/plans/2026-08-31-ratification-and-implementation-report.md` §5 item 2.

**How to use this file:** fill a row's *Named* cell with a person, commit, and
open the artifact in that row's *Closes* cell. Naming a person here does not
close their gate — it makes the gate runnable.

## The blanks

| # | Role | Named | What it blocks today | Closes via |
|---|---|---|---|---|
| 1 | **Privacy owner** (P9 Gate B) | Danny Tran (@dangt) — named 2026-09-02; **gate closed** same date | — | `docs/decisions/p9-gate-b-contact-fields-worksheet.md` §8 |
| 2 | **Program owner** (P5 / D1 / G1 matching) | **Danny Tran (@dangt)** — named 2026-09-02 | G1 workshop may run; `assert_registry_approved()` stays fail-closed until registry is approved in workshop | `docs/plans/workshops/g1-factor-registry-workshop-packet.md` |
| 3 | **Rewards budget owner** (P7 / D6) | **Danny Tran (@dangt)** — named 2026-09-02; $5,000 placeholder ceiling ratified pending institutional funding confirmation | Rewards catalog path; formal D6 gate **closed** for pilot scope | `docs/plans/2026-08-28-d6-rewards-s8-s9-plan.md` |
| 4 | **Product owner** (P8 opportunities, and P1 metrics) | **Danny Tran (@dangt)** — same as program owner; named 2026-09-02 | P8 and P1 gates **closed** 2026-09-02 | `docs/decisions/metrics-authorization-decision-draft.md`; `docs/decisions/p8-opportunities-decision-draft.md` |
| 5 | **R3 signature authority** | **Resolved 1a** — Danny Tran (@dangt), Development Lead, **is** the designated R3 security reviewer. Threat model remains **unsigned** until the signing pass. | R3 signature pass; T-27–T-29 remain open per threat-model text | `docs/security/crawler-threat-model-draft.md` |

## Second tier — named later, blocking less

| # | Role | Named | Note |
|---|---|---|---|
| 6 | **Google Cloud IdP provisioner** (P2) | _(blank)_ | **Tenant exists** (procurement resolved 2026-09-02). Worksheet Part 1 fields still required from provisioner before P2 A1–A4. |
| 7 | **Legacy-PII remediation owner** (CP-PII / D9) | _(blank)_ | `MM-A09.blocking_owner`. Explicitly **non-blocking** for current private-repository engineering; still gates D9 and `LICENSE`. Concerns a different repository. |

## Next actions (post-naming)

1. **Schedule G1 factor-registry workshop** — packet complete; program owner named.
2. **R3 signing pass** — reviewer authority resolved (1a); threat model still unsigned.
3. **Complete A1b worksheet Part 1** — IdP tenant exists; configuration fields pending.
4. **Implement V4 (P1 metrics authz)** — gate closed; Option B policy authorized.

## References

- `docs/plans/2026-08-31-ratification-and-implementation-report.md` §3, §5
- `docs/plans/prep/blocked-work-register-830.md` §3, §6
- `docs/decisions/pilot-decisions.md`
