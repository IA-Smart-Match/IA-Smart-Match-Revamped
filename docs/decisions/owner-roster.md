# Owner roster — the roles nobody has been named to

**Status:** **CLOSED** — rows 1–7 named through 3 September 2026.
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
| 2 | **Program owner** (P5 / D1 / G1 matching) | **Danny Tran (@dangt)** — named 2026-09-02; **G1 closed 2026-09-03** | M2 factor implementation (`topic_relevance`, `travel_burden`) | `docs/plans/workshops/g1-workshop-output-worksheet.md` |
| 3 | **Rewards budget owner** (P7 / D6) | **Danny Tran (@dangt)** — named 2026-09-02; $5,000 placeholder ceiling ratified pending institutional funding confirmation | Rewards catalog path; formal D6 gate **closed** for pilot scope | `docs/plans/2026-08-28-d6-rewards-s8-s9-plan.md` |
| 4 | **Product owner** (P8 opportunities, and P1 metrics) | **Danny Tran (@dangt)** — same as program owner; named 2026-09-02 | P8 and P1 gates **closed** 2026-09-02 | `docs/decisions/metrics-authorization-decision-draft.md`; `docs/decisions/p8-opportunities-decision-draft.md` |
| 5 | **R3 signature authority** | **Resolved 1a** — Danny Tran (@dangt), Development Lead; threat model **signed 2026-09-03** | S6a implementation evidence (live fetch still gated) | `docs/security/crawler-threat-model-draft.md`; `docs/decisions/r3-signing-decisions-2026-09-03.md` |

## Second tier — named later, blocking less

| # | Role | Named | Note |
|---|---|---|---|
| 6 | **Google Cloud IdP provisioner** (P2) | **Danny Tran (@dangt)** — named 2026-09-03 | Worksheet Part 1 fields still required; see `docs/decisions/a1b-gcp-console-guide.md`. |
| 7 | **Legacy-PII remediation owner** (CP-PII / D9) | **Danny Tran (@dangt)** — named 2026-09-03 | `MM-A09.blocking_owner`. Strategy: read-only archive (Q1). **Non-blocking** for Revamped private-repo engineering; gates D9/LICENSE only. |

## Next actions (post-naming)

1. **M2 factor implementation** — `topic_relevance` then `travel_burden` per G1 closure.
2. **S6a implementation evidence** — R3 design signed; live fetch remains gated.
3. **Complete A1b worksheet Part 1** — IdP tenant exists; see `docs/decisions/a1b-gcp-console-guide.md`.
4. **CP-V11 vendoring** — full v1.1 copy + `test_contract_refs.py` per pin record.

## References

- `docs/plans/2026-08-31-ratification-and-implementation-report.md` §3, §5
- `docs/plans/prep/blocked-work-register-830.md` §3, §6
- `docs/decisions/pilot-decisions.md`
