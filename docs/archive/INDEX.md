# docs/archive/ — ID-namespace map

Everything here is **dated or executed** material: plans that shipped,
orchestrator prompts, status snapshots, mock-up rounds, verification
evidence. Paths mirror their original locations (`archive/plans/x.md` was
`docs/plans/x.md`). Nothing here is canonical — check `docs/INDEX.md` first.

This index preserves the **ID namespaces** that archived files defined, so
IDs cited in old commits/PRs stay findable without reading the files.

## ID → file map

| ID family | Meaning | Defining file (archived) |
|---|---|---|
| P1–P9 | 2026-08-28 plan portfolio | `archive/plans/2026-08-28-plan-portfolio-index.md` |
| CP-* | Critical paths (PR1 era) | `archive/plans/critical-path-plans.md` |
| D1–D9, F1–F13, J8–J17, M1–M10 | Pre-CBA backlog numbering | `archive/plans/remaining-foundation-r1-work.md` |
| F-1…F-30 | Port defect findings | `archive/plans/defect-remediation.md` |
| MM-001… / MM-A0x / MM-F0x | Migration manifest rows | `migration/migration-manifest.yaml` (still live — not archived) |
| H01–H21, B-series | Legacy-frontend defect IDs | `plans/frontend-migration.md` (live) |
| B01–B42 | Broken-button ledger | `plans/frontend-broken-buttons.md` (live) |
| B26-T1…T8d | Availability build tracks | `archive/plans/b26-tracks/` |
| CBA-* | CBA pivot track IDs | `archive/plans/cba-goal-catalog.md` |
| R-*, U-*, AP-* | Risks, unknowns, principles | `architecture/risk-register.md`, `ARCHITECTURE_PRINCIPLES.md` (live) |
| T-11…T-15 | R3 crawler review items | `archive/security/r3-technical-review-findings.md` |
| OQ-CBA/CE/SE/SC/A1b/S2/E/F5, OQ-R4/OQ-CAL | Open questions | `plans/open-questions/` (live registers — not archived) |

## What's where

- `archive/plans/` — executed dated plans (Aug–Sep), P1–P9 files, critical-path docs, handoffs, recon
- `archive/plans/b26-tracks/` — all 16 B26 track plans (verified merged into main)
- `archive/plans/prompts/` — orchestrator/worker prompts incl. Sep 19–24 Opus-5.5 handoffs (19 files)
- `archive/plans/prep|workshops|research|open-questions/` — pre-decision packets, answered proposals
- `archive/status-report/` — superseded audit snapshots
- `archive/design/class-exercise/` — mock-up generation corpus: `prompts/` (20), `assets/mockups` (8 PNG), `assets/generated` (24 WebP), `generated.md` catalog
- `archive/architecture/` — Stage-1 leftovers: `engagement-model.md`, `OPUS_AUDIT_HANDOFF.md`, 9-04 diagrams, stakeholder-test-log-audit
- `archive/{operations,migration,security,testing,pilot-data,superpowers,ui,prototypes,misc}` — dated runbooks, run records, evidence, executed specs
