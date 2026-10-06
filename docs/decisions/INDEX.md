# docs/decisions/INDEX.md — decision spine

Every decision surface in the repo, with status. Update rows when a decision
closes. (`docs/architecture/decisions/` ADRs have their own CI-gated index.)

## Open-question registers (authority = the register file itself)

| Register | Scope | Open |
|---|---|---|
| `plans/open-questions/cba-phase-deferred.md` | CBA boundary, OQ-CBA-001…066 | ~36 open (011, 021, 044, 063–066 block soon) |
| `plans/open-questions/student-engagement-deferred.md` | OQ-SC-01…13 + OQ-SE-01…22 | all 35 open |
| `plans/open-questions/class-exercise-open-questions.md` | OQ-CE-01…16 | only CE-06 rate-limit half open |
| `plans/open-questions/a1b-live-idp-deferred.md` | OQ-A1b-001…006 | all open (JWKS trust anchors) |
| `plans/open-questions/architecture-stage-2-deferred.md` | OQ-S2-003…006 | open (S2-001/002 answered) |
| `plans/open-questions/r4-outreach-deferred.md` | **OQ-R4**-001…009 | 001–008 open; 009 partial |
| `plans/open-questions/calendar-deferred.md` | **OQ-CAL**-001…006 | all open |
| `plans/open-questions/engagement-deferred.md` | OQ-E01…E07 | all open |
| `plans/open-questions/f5-deploy-deferred.md` | OQ-F5-001…004 | all open |
| `plans/open-questions/pipeline-stage-writers-deferred.md` | OQ-101…104 | 101/103/104 open |

> **ID collision note (2026-09-26):** `calendar-deferred` and
> `r4-outreach-deferred` both used bare `OQ-001…009` for different questions.
> Cite them as `OQ-CAL-*` and `OQ-R4-*`.

## Decision records in this directory

| File | Status | Holds |
|---|---|---|
| `2026-08-31-session-ratification.md` | ratified | 8-31 authority matrix; 4-status model |
| `a1b-idp-configuration-worksheet.md` | **OPEN gate** | IdP worksheet; no agent may fill; blocks A1–A4 |
| `a1b-gcp-console-guide.md` | open how-to | console steps for the worksheet |
| `class-exercise-decisions-2026-09-25.md` | current | D1–D16 for CLASS_EXERCISE; amends ADR-0025 |
| `class-exercise-default-weights-2026-10-06.md` | current, not implemented | Default weights 3/3/2/2 on a whole-number 0–10 scale, class module and platform (Dr. Wang; scale: owner); supersedes OQ-CE-02's 0.25 each |
| `d6-rewards-budget-decision-record.md` | closed | owner=Danny Tran; D7 tentative |
| `f5-deploy-target-note-2026-09-03.md` | current | classroom=synthetic; `ALLOW_CLOUD_DEPLOY=false` |
| `g3-crawler-decision.md` | signed | CPP-only scope; fail-closed |
| `manual-events-and-feedback-qr-2026-09-07.md` | implemented | admin events; one feedback QR/event |
| `metrics-authorization-decision-draft.md` | closed, implemented | aggregate hierarchy + drill-down split |
| `owner-roster.md` | closed | who decides what (signer authority) |
| `p8-opportunities-decision-draft.md` | closed | `opportunities` metric |
| `p9-gate-a-board-role-decision-draft.md` | closed, implemented | board_role relationship-scoped |
| `p9-gate-b-contact-fields-worksheet.md` | closed | collect-all-3; no crawler population |
| `pilot-decisions.md` | partial supersession | tentative register; student Qs moved to OQ-SE/SC register |
| `pilot-login-decision-2026-09-04.md` | decided, implemented | DB login substitutes A1b for pilot |
| `r3-signing-decisions-2026-09-03.md` | ratified | T-19/27/28/04/29/C-1/13/23; S6a open |
| `stakeholder-correspondence-2026-09.md` | record | Ann Wang emails verbatim (speaker phase two, Friday check-in, dataset); alignment check 2026-09-28 |
| `student-recommender-decision-record.md` | dispositions recorded 09-16 | OQ-SE/SC product rows; ADR-0024 |
| `synthetic-pilot-development-authorization-2026-09-03.md` | ratified | synthetic-only; deferred-gate map |

## Adjacent decision surfaces

- **ADRs 0001–0027** → `architecture/decisions/` (accepted vs proposed status per row in its README; 0018–0023, 0026, 0027 are Proposed).
- **Exercise visual rulings** → `design/class-exercise/DESIGN.md` §11 (six owner rulings 2026-09-26).
- **B26 per-track rulings/deviations** → `archive/plans/b26-tracks/T*-plan.md` (merged; archived as unit).
- **G1 ratified workshop output** → `plans/workshops/g1-workshop-output-worksheet.md`.
- **Blocked/undecided ADRs** → `architecture/decisions/adr-backlog.md` (B-01…B-09+).
- **Open follow-ups** → `design/coordinator-redemption-queue.md` §9 (F1/F2).

## Open gates (decisions pending that block work)

1. A1b IdP worksheet — all Part-1 fields outstanding (`a1b-idp-configuration-worksheet.md`)
2. Registry 3.0.0 `CURRENT_CBA_REGISTRY` flip — gated on ADR-0027
3. SPEAKER_PORTAL turn-on — T6b-1 C5 rule, pending stakeholder rows
4. MM-A09 legacy PII — CANNOT CLOSE, unassigned sev-1 (`plans/critical-path-legacy-pii.md`)
5. F-28 / CP-V11 vendoring residual (`plans/critical-path-port-rereview.md`)
6. OQ-CE-06 proxy rate-limit rule for `exercise.plated.blog`
