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
| 1 | **R3 security reviewer** | `docs/security/crawler-threat-model-draft.md` signature block; `r3-technical-review-findings.md` header reads `Reviewer: (unfilled — see §6)` | Blank | All of P6 past the R3 gate |
| 2 | **R3 reviewer *authority*** | same | Unresolved question, not merely blank | See §1 |
| 3 | **Privacy owner** | P9 Gate B (`2026-08-28-pilot-columns-plan.md` §Stop-gates) | **Role is named as a requirement in five documents and filled in none** | P9 Gate B, R3 T-14, MP-4 |
| 4 | **Program owner (D1/G1)** | `g1-factor-registry-workshop-packet.md`: `Blocking owner: program owner (name TBD)` | Blank | P5 entirely; P8 if score-floor |
| 5 | **Rewards budget owner (D6)** | `pilot-decisions.md` D6: "does **not** name a budget holder, and no budget exists" | Blank | P7; `budget_owner_id NOT NULL` is already enforced by `test_reward_item_rejects_a_null_budget_owner` |
| 6 | **Allowlist entry approver** | `r3-technical-review-findings.md` §5 | **Resolved 2026-08-29** by signed G3 §10 row 1 (Danny Tran). R3's §5 text is now stale. | — |
| 7 | **Product owner (opportunities definition)** | P8 stop-gate | No artifact exists under `docs/decisions/` at all | P8 |
| 8 | **Interim project owner** | `pilot-decisions.md`: "Interim owner: DangT … This is a **self-assignment**" | Filled, but **explicitly unratified** and pending IA West confirmation | Nothing directly; noted so it is not mistaken for institutional authority |
| 9 | **`DESIGN.md` owner (D-0)** | `pilot-decisions.md` §197 | "deferred, not decided" | Nothing directly |

**The pattern worth naming:** items 3, 4, 5, and 7 are all the same failure —
a role that documents reference as though it exists. Each was written as a
dependency by someone who assumed someone else had named it. None is expensive
to fill; all four are cheap sentences a human can write in a single sitting.

## 1. The R3 reviewer-authority question — surfaced, not resolved

The R3 stop-gate requires a **named security reviewer**. Danny Tran is
documented as **Development Lead** and as the G3 owner of record. The repository
does not establish that those are the same role.

This is recorded here as an **open question for the human**, not a finding
against anyone. Two honest resolutions exist:

- **1a.** The Development Lead *is* the security-reviewing authority for this
  project, and the artifact should say so explicitly in the signature block.
- **1b.** A separate reviewer is required, and the field stays blank until one
  is named.

An agent cannot choose between these, because the answer is a fact about the
organization and not about the repository. It matters because signing under the
wrong role produces an artifact that *looks* like it cleared the gate.

## 2. Per-plan status

### P1 — metrics authorization · blocked on a workshop

- **Waiting on:** ratification of `docs/decisions/metrics-authorization-decision-draft.md`, which poses four questions and answers none.
- **Who:** product + security, together.
- **Cost of waiting:** low and *honest*. Current behaviour is intentionally ungated, documented, and pinned by `tests/authz/test_policy_matrix.py::INTENTIONALLY_UNGATED_OPERATIONS`. Nothing is silently wrong; it is knowingly open.
- **Leverage:** the portfolio index calls P1 "small, high leverage". That still reads correctly — four questions, and the work behind them is bounded.
- **Coupling:** if P9 Gate B collects any contact field, P1 acquires a new dependent (minimum-disclosure roles for contact data). **Deciding Gate B as "drop" keeps P1 uncoupled.**

### P2 — institutional sign-in · blocked on a thing that does not exist

- **Waiting on:** `docs/decisions/a1b-idp-configuration-worksheet.md`, in which **every field is `_(blank)_`**.
- **Who:** whoever can provision an identity provider.
- **The honest blocker:** **no IdP tenant exists.** This is not a decision awaiting a decider; it is infrastructure awaiting procurement. Cards A1–A4 cannot be planned around a workshop, because a workshop cannot produce an issuer URL.
- **Recommendation:** stop describing P2 A1–A4 as workshop-blocked. Re-file it as **procurement-blocked** so it is not repeatedly queued behind a meeting that cannot resolve it. Card A0 remains startable per the portfolio index.

### P5 — G1 matching · blocked on the longest pole

- **Waiting on:** a ratified factor registry and golden case set (gate G1), with a named program owner for ongoing weight governance.
- **Who:** the program owner — **currently unnamed** (register item 4).
- **Cost of waiting:** scoring continues to fail closed, which is the correct behaviour. `pilot-decisions.md` D1 calls this "the longest pole, and all matching work waits on it."
- **Note:** the workshop packet exists and is complete. **The gap is a name, not a document.** Naming the owner is a prerequisite to running the workshop, not an output of it.

### P7 — D6/D7 rewards · blocked on a budget that does not exist

- **Waiting on:** a named human budget owner (D6) and calibration N (D7).
- **Who:** whoever controls reward funding.
- **The honest blocker:** `pilot-decisions.md` D6 states plainly that no budget exists and no budget holder is named. `rewards-catalog-worksheet.md` is marked "human completion required — **do not seed listable catalog rows**", and the schema already enforces `budget_owner_id NOT NULL`.
- **Why this is well-designed:** the database refuses to hold a reward with no owner. There is no way to fake progress here, which is why nothing has drifted. Leave it.

### P8 — opportunities · blocked, and likely to inherit P6

- **Waiting on:** a written canonical definition of "opportunities", ratified by the product owner. **No such artifact exists under `docs/decisions/`.**
- **Inheritance, stated carefully:** the plan's stop-gate says P8 inherits P6 if the definition depends on crawler-fed events, and inherits P5 if it includes a score floor. `docs/plans/opportunities-metric-inventory.md:13` records that the Opportunities page **as built today** merges "CSV + crawler rows" with "fabricated crawler dates/roles". So the *current surface* is crawler-fed.
  **That is evidence about the existing page, not a statement of the owner's intended definition** — which does not exist in writing yet. The safe planning assumption is that P8 inherits P6 **unless the definition explicitly excludes crawler rows**; the executor must record which branch actually applies once the artifact lands, exactly as the plan requires.
- **Note the trap the plan already names:** do not resolve the two-pages disagreement (Fix #5) by pointing both pages at the same fabricated client-side merge. The fabricated dates and roles at line 13 are the defect, not the baseline.

### P9 — pilot columns · two independent gates, one of them cheap

- **Gate A (`board_role`):** blocked on Dr. Wang. Two questions (intrinsic vs. relationship-scoped; and if relationship-scoped, multiplicity + effective dates). The holding position in `columns.yaml` is documented as a holding position, which is correct.
- **Gate B (contact fields):** **the cheapest open gate in the portfolio.** Full worksheet prepared at `docs/decisions/p9-gate-b-contact-fields-worksheet.md`.
- Gates pass independently; only the branch whose gate passed may run.

## 3. Recommended workshop order — by leverage, not by number

1. **P9 Gate B.** Three collect/drop choices. Unblocks R3 T-14, makes MP-4's scope final, and completes the Stage 0 §4 schema review. A "drop" outcome needs no privacy owner and adds no dependencies. *Worksheet ready.*
2. **Name the four missing owners** (register items 1, 3, 4, 7). This is not a workshop; it is four sentences. Three other plans are waiting on names rather than on decisions.
3. **P1 metrics authz.** Four bounded questions; the portfolio index already flags it as high leverage per unit of decision.
4. **P5 G1 registry.** The longest pole — start it as soon as item 2 names a program owner, since the packet is already complete.
5. **P9 Gate A**, **P8 definition**, **P7 D6/D7** as their owners become available.
6. **P2 A1–A4** — not a workshop item. Re-file as procurement.

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
