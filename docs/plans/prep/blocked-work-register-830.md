# Blocked-work register — 2026-08-30

**Status:** **PREPARATION ONLY.** This document approves nothing, ratifies
nothing, and fills no owner field. **Changes no code.**
**Ratification status (31 August 2026):** synchronized with
`docs/decisions/2026-08-31-session-ratification.md` — that record is now the
authoritative blocker classification (RATIFIED — SESSION POLICY / RECORDED —
GATE INCOMPLETE / EXTERNAL DEPENDENCY / CANNOT CLOSE) and owner for every
item below. Session-recorded working directions now exist for several blank
owners named below (R3 T-07/T-13/T-19/T-23, P1's hierarchy, P6 Stage 0
scope, P7's D6, P8's category set, P9 Gate A's `board_role` shape, P9 Gate
B's collect direction) — **none of those directions fills the blank owner
fields this register tracks.** Read this register's per-item detail
alongside the ratification record's matrix, not as superseded by it.
**Baseline:** branch `friday-deliverable-828` at `fc40a06`.
**Purpose:** for each plan that engineering cannot start, record precisely *what*
is missing, *who* must supply it, and what it costs to keep waiting — so the
workshop queue can be ordered by leverage rather than by plan number.

> Companion to `docs/plans/2026-08-28-plan-portfolio-index.md`, which orders
> plans by dependency. This orders the same plans by **decision cost**.

---

## 0. The blank-owner register

Every owner field in the portfolio that is currently blank. **An agent filled
none of these and may fill none of them.**

| # | Field | Where | State | Blocks |
|---|---|---|---|---|
| 1 | **R3 security reviewer** | `docs/security/crawler-threat-model-draft.md` signature block; `r3-technical-review-findings.md` header | **Resolved 1a — 2026-09-02:** Danny Tran (@dangt), Development Lead, is the designated R3 security reviewer. Threat model **unsigned** until signing pass. | R3 signature pass (not authority) |
| 2 | **R3 reviewer *authority*** | same | **Closed 2026-09-02** — option **1a** (Development Lead is security reviewer) | — |
| 3 | **Privacy owner** | P9 Gate B (`2026-08-28-pilot-columns-plan.md` §Stop-gates) | **Closed 2026-09-02** — Danny Tran (@dangt); see `p9-gate-b-contact-fields-worksheet.md` §8 | — |
| 4 | **Program owner (D1/G1)** | `g1-factor-registry-workshop-packet.md` | **Named 2026-09-02** — Danny Tran (@dangt). G1 workshop may run. | Registry approval (workshop output) |
| 5 | **Rewards budget owner (D6)** | `pilot-decisions.md` D6 | **Named 2026-09-02** — Danny Tran (@dangt); $5k placeholder. D6 **closed** for pilot scope. | P7 behavior cards |
| 6 | **Allowlist entry approver** | `r3-technical-review-findings.md` §5 | **Resolved 2026-08-29** by signed G3 §10 row 1 (Danny Tran). R3's §5 text is now stale. | — |
| 7 | **Product owner (opportunities definition)** | P8 + P1 stop-gates | **Named 2026-09-02** — Danny Tran (@dangt). P8 and P1 **closed**. | — |
| 8 | **Interim project owner** | `pilot-decisions.md`: "Interim owner: DangT … This is a **self-assignment**" | Filled, but **explicitly unratified** and pending IA West confirmation | Nothing directly; noted so it is not mistaken for institutional authority |
| 9 | **`DESIGN.md` owner (D-0)** | `pilot-decisions.md` §197 | "deferred, not decided" | Nothing directly |

**Owner naming (2 September 2026):** rows 4, 5, and 7 are now filled. Row 1
authority is resolved (1a); signature remains outstanding. Row 6 (IdP
provisioner) and row 9 (D-0) remain open.

## 1. The R3 reviewer-authority question — **closed 2026-09-02**

**Resolution (1a):** Danny Tran (@dangt), Development Lead, **is** the
designated R3 security reviewer for this project. The signature block should
name Danny Tran with role **Development Lead / Security Reviewer**.

The threat model remains **unsigned** until a human signing pass. T-27–T-29 and
other open items in the threat model's outstanding-dependencies list remain
as recorded there — authority resolution does not close those items.

## 2. Per-plan status

### P1 — metrics authorization · **closed 2026-09-02**

- **Status:** **CLOSED** — `docs/decisions/metrics-authorization-decision-draft.md`
- **Policy:** Option B (split aggregates/drill-down); subtree scopes; admin
  unrestricted within tenant; bare `resource_grant` denied; no metric exceptions.
- **Owners:** Danny Tran (@dangt) as product owner and security/privacy owner.
- **Implementation:** V4 authorized; retire `INTENTIONALLY_UNGATED_OPERATIONS`
  for metrics in the implementation change set.

### P2 — institutional sign-in · tenant procured; worksheet unfilled

- **Waiting on:** `docs/decisions/a1b-idp-configuration-worksheet.md` Part 1
  fields. **Google Cloud IdP dev/test tenant exists** (procurement resolved
  2026-09-02); configuration values not yet committed.
- **Who:** IdP provisioner (unnamed on roster row 6).
- **Status:** remains **EXTERNAL DEPENDENCY** until worksheet complete.

### P5 — G1 matching · workshop ready

- **Program owner:** **Danny Tran (@dangt)** — named 2026-09-02.
- **Waiting on:** G1 factor-registry workshop execution and committed approval
  outputs (factors, weights, golden cases).
- **Cost of waiting:** scoring continues to fail closed — correct behaviour.
- **Next action:** schedule and run
  `docs/plans/workshops/g1-factor-registry-workshop-packet.md`.

### P7 — D6/D7 rewards · D6 closed for pilot scope

- **Budget owner:** **Danny Tran (@dangt)** — named 2026-09-02; $5,000 placeholder
  ceiling ratified pending institutional funding confirmation.
- **Waiting on:** D7 calibration review; cards L1–L4+ remain gated per plan.
- **Permitted now:** formal D6 record + schema verification per ratification boundary.

### P8 — opportunities · **closed 2026-09-02**

- **Definition:** category-list with coordinator review; import + crawler evidence
  (P6 persistence for crawler rows). **BRANCH-ELIGIBILITY** — no score floor.
- **Artifact:** `docs/decisions/p8-opportunities-decision-draft.md`
- **Product owner:** Danny Tran (@dangt).
- **Next:** card O1 (register definition); O2+ blocked on S12 / P6 as plan states.

### P9 — pilot columns · two independent gates, one of them cheap

- **Gate A (`board_role`):** **CLOSED 2026-09-02 (pilot scope)** — relationship-scoped;
  multiple concurrent roles; no effective dates for pilot. Artifact:
  `docs/decisions/p9-gate-a-board-role-decision-draft.md`. Decider: Danny Tran
  (@dangt), program owner. Schema migration follows plan Wave C.
- **Gate B (contact fields):** **CLOSED 2026-09-02.** Artifact:
  `docs/decisions/p9-gate-b-contact-fields-worksheet.md` §8. Collect all three;
  ADR-0014 fields recorded. Unblocks T-14 (subject to R3 sign-off), narrows
  MP-4, completes Stage 0 §4 schema review. Adds P1 coupling (minimum-disclosure
  for contact data).
- Gates pass independently; only the branch whose gate passed may run.

## 3. Recommended workshop order — by leverage, not by number

1. **P5 G1 registry workshop** — program owner named; packet complete. **Longest remaining product pole.**
2. **R3 signing pass** — reviewer authority resolved (1a); threat model still unsigned.
3. **P2 A1–A4** — complete A1b worksheet Part 1 (tenant exists; fields pending).
4. **Implement V4 (P1)** — gate closed; engineering backlog item.
5. **P8 O1+** — definition closed; persistence cards when ready.
6. **P9 Gate A migration** — gate closed; `columns.yaml` + schema card per plan.

## 4. What an agent must never do with this register

- Fill any owner field, here or in any artifact it references.
- Treat a prepared worksheet as a passed gate.
- Treat the *absence* of an owner as permission to proceed under a default.
- Sign, or edit the status line of, any gate artifact.

## 5. Sources

All claims above were read directly from the working tree at `fc40a06` on
2026-08-30, not carried forward from a prior session's summary:

- `docs/plans/2026-08-28-plan-portfolio-index.md`
- `docs/plans/2026-08-28-{metrics-authz,a1b-institutional-sign-in,g1-matching-m1-m10,d6-rewards-s8-s9,opportunities-s12,pilot-columns}-plan.md`
- `docs/decisions/{a1b-idp-configuration-worksheet,metrics-authorization-decision-draft,pilot-decisions,g3-crawler-decision}.md`
- `docs/plans/workshops/g1-factor-registry-workshop-packet.md`
- `docs/pilot-data/{rewards-catalog-worksheet,board-role-decision-prep,event-contact-fields-decision-prep}.md`
- `docs/plans/opportunities-metric-inventory.md`
- `docs/security/{r3-technical-review-findings,crawler-threat-model-draft,prompt-injection-assessment}.md`

## 6. Synchronization — 2 September 2026

| Item | Prior state | Current state |
|---|---|---|
| **P9 Gate B** | RECORDED — GATE INCOMPLETE | **CLOSED** — `p9-gate-b-contact-fields-worksheet.md` §8 complete |
| **Privacy owner** (register §0 item 3) | Blank | **Named and closed** — Danny Tran (@dangt) |
| **events `gate_pending`** in `columns.yaml` | All three fields `withhold` | **Removed** — gate closed per worksheet comment |
| **MP-4** (G3 §7) | Provisional while Gate B open | **Narrowed** — human/import per §8; extractors forbidden |
| **T-14** (R3) | Blocked on Gate B | **Unblocked for closure** — pending R3 signature pass |
| **Next recommended action** | P9 Gate B signature | **G1 workshop** (program owner named) or **R3 signing pass** |

## 7. Synchronization — 2 September 2026 (decision batch)

| Item | Prior state | Current state |
|---|---|---|
| **Program owner** (P5/D1) | Blank | **Named** — Danny Tran (@dangt) |
| **Product owner** (P8/P1) | Blank | **Named** — Danny Tran (@dangt) |
| **P1 metrics authz** | RECORDED — GATE INCOMPLETE | **CLOSED** — Option B; see decision draft |
| **P8 opportunities** | RECORDED — GATE INCOMPLETE | **CLOSED** — category-list + coordinator review |
| **P9 Gate A** | RECORDED — GATE INCOMPLETE | **CLOSED (pilot scope)** — relationship-scoped; multiple concurrent; no dates |
| **P7 D6 budget owner** | Blank | **Named** — Danny Tran (@dangt); $5k placeholder |
| **R3 reviewer authority** | Open (1a vs 1b) | **Closed — 1a** (Development Lead is reviewer); signature still outstanding |
| **P2 IdP** | No tenant | **Tenant exists** — worksheet Part 1 still unfilled |
| **Next recommended action** | Name program owner or P1 workshop | **G1 workshop** or **R3 signing pass** |
