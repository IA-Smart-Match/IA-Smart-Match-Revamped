# docs/INDEX.md — read this first

**Rules for agents:** start here, follow one pointer, stop. Do not bulk-read
`docs/plans/` or `docs/archive/`. Cite decision IDs (ADR-0005, OQ-CE-06), not
file contents. Dated material lives in `docs/archive/` — see
`archive/INDEX.md` for the ID-namespace map.

## Orientation — "how does this system work?"
- What runs today → `architecture/current-system-topology.md`
- The async mechanism everything depends on → `architecture/command-path.md`
- Bounded contexts & term collisions → `architecture/domain-model.md`, `architecture/GLOSSARY.md`
- What hurts → `architecture/risk-register.md` (R-09 is the standing P0)
- How stale the Stage-1 docs are → `architecture/CURRENT_ARCHITECTURE_AUDIT.md` §0
- Target design → `architecture/TARGET_ARCHITECTURE.md` · principles → `ARCHITECTURE_PRINCIPLES.md` (AP-01…13)

## Decisions — "what was decided?"
- ADR index (CI-checked, `test_adr_index.py`) → `architecture/decisions/README.md`
- Feature/gate decision spine → `decisions/INDEX.md`
- Open-question registers → `plans/open-questions/` (one file per area; the
  register IS the authority — `cba-phase-deferred`, `student-engagement-deferred`,
  `class-exercise-open-questions`, `a1b-live-idp-deferred`, `architecture-stage-2-deferred`,
  `calendar-deferred`, `engagement-deferred`, `f5-deploy-deferred`,
  `pipeline-stage-writers-deferred`, `r4-outreach-deferred`)

## Build — "how do I add code here?"
- `agents/architecture-implementation-guide.md` (M0–M8 increments, gates, hazards)
- `architecture/MODULE_BOUNDARIES.md` + `architecture/DEPENDENCY_RULES.md`
  (inventory is stale — verify contract set in `pyproject.toml`)
- `agents/feature-implementation-template.md` (worksheet)

## Operate — "how do I run/deploy it?"
- Deploy → `operations/vm-deploy.md` · migrations/rollback → `operations/deploy-runbook.md`
- Compose appliance → `operations/containers.md` · dev loop → `operations/local-dev-walkthrough.md`
- Exercise hosting (`exercise.plated.blog`) → `operations/exercise-hosting.md`
- Tunnel rebuild (sole record) → `operations/classroom-vm-cloudflare-tunnel.md`
- Dataset rebuild → `operations/pilot-dataset-rebuild.md` · contract → `pilot-data/columns.yaml`

## Product — "what are we building?"
- CBA scope authority → `product/cba-smart-match-customer-requirements.md`
- Class exercise authority → `product/class-exercise-requirements.md`
- Capability/role/taxonomy maps → `product/cba-capability-policy.md`, `cba-role-presentation.md`, `cba-taxonomies.md`, `cba-terminology.md`
- Exercise visual system → `design/class-exercise/DESIGN.md` (§11 = owner rulings)
- Exercise Stitch mock-ups (contact sheet) → `design/class-exercise/stitch.md`
- Redemption queue → `design/coordinator-redemption-queue.md`

## In flight
- B26 self-service availability → `plans/2026-09-22-b26-self-service-availability-plan.md` (per-track plans: `archive/plans/b26-tracks/`)
- Registry 3.0.0 flip — gated on ADR-0027 (Proposed) → `architecture/decisions/`
- Open PR #239 → branch `fix/ce-wave3-ui`
- MM-A09 legacy PII — CANNOT CLOSE → `plans/critical-path-legacy-pii.md`
- Live ledgers → `plans/backlog.md`, `plans/frontend-broken-buttons.md` (B01–B42), `plans/todo-disposition-register.md`

## Status
- Latest audit snapshot → `status-report/` (README points at newest)

Historical/executed work (plans, prompts, mock-ups, evidence) is archived
under `docs/archive/` mirroring the original paths.
