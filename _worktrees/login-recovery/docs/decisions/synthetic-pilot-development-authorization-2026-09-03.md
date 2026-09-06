# Synthetic pilot — development authorization

**Status:** **RATIFIED — SESSION POLICY** (engineering authorization only).
**Ratifier:** Danny Tran (@dangt), program owner.
**Date:** 2026-09-03

---

## 1. Scope boundary

### This authorizes

- End-to-end **click-through** stakeholder demos on **synthetic data only**, persisted in PostgreSQL (not client-side mocks).
- Implementation of product paths (import → review → pipeline → metrics → matching shortlist → coordinator flows) using dev fixtures, seed data, and compose appliance.
- Engineering to proceed on deferred institutional gates **under synthetic constraint** without waiting for privacy/legal procurement for **development** milestones (e.g. Fri 2026-09-04 functional app target per program direction).

### This does NOT waive

- Legal FERPA, records, or privacy obligations for **live** student data (G2, D8).
- G4 outreach send, G5 Calendar API, or production provider credentials without separate gates.
- Institutional licensing / open source (D9) or MM-A09 archive exposure.
- Claims of production readiness, public release, or institutional adoption.

**Posture:** Development-only synthetic pilot until a separate public-release planning gate reopens G2–G5 and D3–D5.

---

## 2. D5 — retention periods (synthetic development environment)

Conservative defaults for **synthetic-dev** only. Production retention requires privacy/legal ratification (D5 institutional row).

| Evidence class | Synthetic-dev retention | Purge trigger |
|---|---|---|
| Import quarantine / review items | 90 days | Classroom reset or manual purge job |
| Pipeline / attendance / engagement ledger | 1 year | Synthetic re-seed |
| Match runs and explanations | 1 year | Synthetic re-seed |
| Crawler provenance / observations (when implemented) | 90 days | No live fetch in dev |
| Audit / authz decision logs | 180 days | Ops rotation |
| Spend reservation receipts (ADR-0015 A1) | 90 days | Sweeper + reset |

---

## 3. Deferred external gates (engineering continues on synthetic)

| Gate | Deferred until | Engineering permitted now |
|---|---|---|
| G2 live data | Public release planning | Synthetic imports, fixture users |
| G4 outreach | Public release planning | Consent lifecycle, dry-run only |
| G5 Calendar API | Public release planning | ICS artifacts, month calendar UI |
| D3 route matrix | Procurement | Straight-line / synthetic travel_burden |
| D4 DNS | Institutional IT | Localhost / compose URLs |
| D8 FERPA position | Institutional privacy review | Minimum-disclosure policy (recorded) |
| ADR-0015 A3 | Procurement | Synthetic reservation (V1 complete) |

---

## 4. Pipeline production caller (item 6)

**Authorized:** Wire **synthetic** import and review-decision paths to call `PipelineRepository` for stakeholder demo, subject to:

1. G1 registry approval (D1 sign-off) before `matched_at` semantics represent real matching.
2. Professional identity: import creates or links `user_account` per professional (Choice A).
3. `attendance_record` write path: minimal synthetic writer for Attended-stage CHECK constraints in demo seed flow.

Production live-data callers remain blocked until G2 closes.

---

## 5. F-25 — weight semantics

**Normalize on apply** — weights normalized when applied to Stage B scoring (program owner decision 2026-09-03).

---

## 6. F5 — deploy target guidance (stakeholder pilot)

See `docs/decisions/f5-deploy-target-note-2026-09-03.md` for classroom vs dev comparison.

**Interim direction:** Local compose + optional **classroom** GCP project for hosted stakeholder demo; both use **synthetic fixtures only**.

---

## 7. Related decisions (same session)

- R3 signed: `docs/decisions/r3-signing-decisions-2026-09-03.md`
- G1 workshop prep: `docs/plans/workshops/g1-workshop-output-worksheet.md`
- D6: $5k placeholder stands
- D7: 100 points per verified attendance
- IA West ratification: engineering on tentative; pursuit in parallel
