# Oct. 2 stakeholder revisions execution plan

**Prepared:** 2026-10-04  
**Source baseline:** `main` at `ec471ba222bbad91c16b6875e41d250592041e37`  
**Delivery milestone:** `#1 — Oct-14 stakeholder board`, due 2026-10-14  
**Stakeholder run-through:** 2026-10-16  
**Later remediation checkpoint:** 2026-10-30  
**Status:** active planning and delegation authority; policy-gated implementation remains blocked until named owners decide it

## Purpose

Audit and document the Oct. 2, 2026 class-exercise revisions, turn each confirmed gap into an implementation-ready specification and GitHub task, and organize those tasks for the named collaborators. Do not confuse stakeholder observations from a deployed site with evidence from the repository. Every scoped GitHub issue must use milestone #1 and, when the repository Project exposes a date field, a target date of 2026-10-14.

This is a planning, specification, documentation, and issue-tracking effort only. It does not authorize product-code changes, deployment, live-data access, destructive cleanup, or execution of the Oct. 16 reset. Those actions belong to collaborators working their assigned issues and remain subject to the gates documented here.

## Ownership

| Role | GitHub assignee | Scope from stakeholder documents |
|---|---|---|
| Danny | `BrooklynD23` | instructor detail, lock/refresh behavior, upload/repoint operation, deployment-safe run-through preparation |
| Chau | `Chau-Nguyen-Developer` | matching formulas, factor semantics, simulation policy, golden-result approval |
| Janice | `starey6789` | team/instructor screens, event descriptions, reason presentation, status and action feedback |
| Justin | Not provided | acceptance testing only; do not assign until a GitHub username is confirmed |

Supporting collaborators are additional assignees only where the stakeholder documents name them. Unknown ownership remains unassigned rather than guessed.

## Non-negotiable constraints

1. Preserve `hidden_true_interests` and `hidden_true_career_goal` as results-only fields; never expose them through ranking, public/instructor APIs, logs, pages, or downloads.
2. Keep server refusals authoritative. Disabled controls are presentation, not enforcement.
3. Keep class-year display order separate from ranking tie-break order.
4. Do not hard-code workbook-owned event descriptions in the frontend.
5. Do not silently supersede OQ-CE-14/D2 or implement unresolved OQ-CE-17 semantics.
6. Use test-first development: each behavior change must have a focused test observed failing for the expected reason before production code changes.
7. Do not reset any environment until the specific destructive operation receives separate confirmation.

## GitHub issue policy

- Search open and closed issues before creating anything.
- Reuse #267, #268, #269, #271, #273, #289, #293, #295, and #299 where their scope matches.
- Put every scoped issue on milestone #1 with due date 2026-10-14.
- Set the repository Project target-date field to 2026-10-14 when that field exists.
- Each issue must include acceptance criteria, dependencies, assignees, tests, source-document references, and any policy gate.

## Collaborator work packages and dependency order

The sections below specify the work collaborators will implement through their assigned GitHub issues. This planning effort documents the required sequence and exit criteria; it does not execute these packages.

### Package 0 — Evidence and control setup

1. Verify current `main`, issue history, collaborators, milestone #1, Project fields, labels, and deployment documentation.
2. Build a requirement matrix: request → current source behavior → evidence → status → blast radius → issue → owner → gate.
3. Record source/deployment discrepancies without claiming either is the other.

**Exit gate:** evidence matrix reviewed; no duplicate issues; target milestone and date mechanisms confirmed.

### Package 1 — Policy decisions

1. Resolve OQ-CE-17: any-match stated-interest credit and related-event counting. Owner: Chau.
2. Resolve whether Oct. 2 supersedes D2/OQ-CE-14 for Northline only or more broadly. Owner: Chau with stakeholder confirmation.
3. Resolve #295 email-everyone seed scope if still open.
4. Define whether `event_description` is required for all new uploads and how older datasets behave.

**Exit gate:** decision evidence is recorded before changing formulas, simulation, golden fixtures, or public contracts.

### Package 2 — Event descriptions

**Assignees:** `starey6789`, `BrooklynD23`

1. Add failing ingest tests for the new column, blank past-event values, and missing-column rollback.
2. Carry the value through domain types, persistence/schema and migration if required, repositories, API models, OpenAPI, and fixture builders.
3. Display descriptions above team sliders and beside instructor events.
4. Keep instructor-only “why someone would come” commentary out of participant responses.
5. Verify replacing the active file changes rendered descriptions without client copy changes.

**Exit gate:** unit, integration, API-contract, frontend, migration, and hidden-field negative tests pass.

### Package 3 — Matching and explanations

**Assignees:** `Chau-Nguyen-Developer`, `starey6789`

1. Implement #289 only after OQ-CE-17 closes; review shared-module impact and golden rankings.
2. Implement the approved undecided-goal rule consistently in matching, reason projection, and simulation.
3. Render exactly one concise reason line per profile.
4. Apply the approved major-only and deterministic tie wording.
5. Keep Freshman → Senior display order independent from the senior-first tie-break.

**Exit gate:** focused factor, simulation, reason, ranking, golden, desktop, and mobile tests pass; no hidden score or withheld value enters responses.

### Package 4 — Instructor observability

**Assignees:** `BrooklynD23`, `starey6789`

1. Add invited names for every saved list/event/round to instructor team detail.
2. Preserve setting context after deletion in coordination with #271.
3. Include saved weights, result counts, asking choice, refresh state, and unambiguous event/round labels.
4. Scope all reads by workspace and dataset and exclude scores, seeds, tokens, internal IDs, and hidden fields.

**Exit gate:** multiple-team, both-round, reload, and deleted-setting tests pass.

### Package 5 — Persistent status and action feedback

**Assignees:** `starey6789`, `BrooklynD23`

1. Reuse #268 for team identity rather than duplicating it.
2. Add an always-visible server-backed summary for team, event/round, result-run state, asking choice, and refresh state.
3. Keep success and refusal feedback adjacent to controls until the next action.
4. Explain no-ops and reflect one-use controls in accessible disabled/reused states.
5. Confirm destructive/reset/repoint/refresh-all scope before execution.
6. Test reload, second tab, keyboard focus, live announcements, projector layout, and cross-team isolation.

**Exit gate:** server-state persistence and accessibility tests pass; controls cannot mutate another team.

### Package 6 — Acceptance and operations readiness

**Assignees:** issue-specific owners; Justin remains test support without assignment

1. Attach acceptance evidence to #299 rather than duplicating the checklist.
2. Test concurrent teams, reload/re-entry, second-tab duplicate runs, upload rollback, hidden-column download exclusion, refresh isolation, clear-team isolation, browser title, projector readability, and measured load time.
3. Record deployed SHA, environment, URL, dataset label/checksum, event locks, and rollback procedure.
4. Prepare—but do not execute—the Teams 1–4 reset and Northline/Harbor closure runbook.

**Exit gate:** exact deployment is verified and a separate destructive-operation confirmation is obtained before reset.

## Requirement-to-repository evidence matrix

| # | Requirement | Stakeholder evidence | Current source behavior | Evidence | Status | Blast radius | Issue | Owner | Gate |
|---|---|---|---|---|---|---|---|---|---|
| 1 | Interest partial credit → any-match + related-event count | Oct 2 checklist; audit doc §Evidence row 1 | Jaccard stated-interest overlap in `student_factors/factors.py`; no related-event count | `factors.py`, `exercise/reasons.py`, matching tests | Partial / planned | Matching, reasons, golden rankings | #289 | Chau | OQ-CE-17 owner decision |
| 2 | Northline undecided goal no 0.5 credit | Oct 2 review says Northline is not broad | D2/OQ-CE-14 implemented: both Northline and Harbor are exploratory; undecided gets 0.5 in matching and simulation | `vocabulary.py:37-48`, `factors.py:74-82`, `simulation.py:71-79` | Conflicts with prior decision | Matching, simulation, reason text, golden results | #322 | Chau | Scope: Northline-only or broader |
| 3 | Exactly one reason line per profile | Oct 2 copy; issue draft 3 | Backend emits one phrase; `RankedList.tsx` adds a second `FactorNames` line | `RankedList.tsx:253-270`, `reasons.py` | Absent / conflicts | Frontend renderer, tests | #320 | Janice | Wording matches OQ-CE-12/D2 |
| 4 | Event descriptions end-to-end | New `Events.event_description` column in workbook | No `event_description` field anywhere in ingest / schema / API / UI | `layout.py:134-144`, `ingest.py`, `schema.py:189-223`, `exercise_matching_models.py:351-362` | Absent | Layout, ingest, schema/migration, persistence, API, OpenAPI, frontend | #318 | Janice | Required-vs-optional; old datasets |
| 5 | Instructor invited names per list/run | Full-class view for Ann | Summary shows counts/settings; no invited profile names | `InstructorTeams.tsx:330-364`, `exercise_instructor_models.py` | Partial | Instructor API/read, frontend detail | #319 | Danny | Coordinate with #271 |
| 6 | Persistent team status + action feedback | Every button must respond; always-visible status | No persistent status region; some notices exist; refresh-all lacks confirmation | `ExerciseScreen.tsx:83-116`, `ExerciseMatching.tsx`, `ExerciseResults.tsx`, `InstructorUnlock.tsx` | Partial | `ExerciseScreen`, every exercise page, `readCurrentWorkspace`, accessibility tests | #321 | Janice | Reuse #268 |
| 7 | Results locked / one run per team/event | Checklist rows | Server refuses second POST; reload and second-tab covered | `exercise_results_rules.py`, `test_exercise_results_rules.py:208` | Implemented in source | — | (covered by tests) | — | Verify deployed build |
| 8 | Email-everyone baseline | Checklist row | Response model supports `email_everyone`; UI panel exists | `exercise_results_models.py`, `ExerciseResults.tsx` | Implemented (contract) | Seed scope | #295 | — | Owner decision on seed |
| 9 | Refresh status/summary + refresh-all | Checklist rows | Refresh isolates per team; refresh-all reports skipped/refresh; no UI confirmation | `test_exercise_results_refresh.py:102,338-424` | Mostly implemented | UI confirmation | #321 / #295 | Janice / Danny | Verify checklist copy |
| 10 | Class-year display order Freshman→Senior | Checklist row | `EXERCISE_CLASS_YEARS` tuple defines order | `vocabulary.py:96-103` | Implemented in source | UI table map | — | Janice | Verify rendered order |
| 11 | Hidden pink columns excluded everywhere | Participant download must exclude hidden columns | `EXERCISE_WITHHELD_FIELDS` allowlist; CSV fixed six columns; models built field-by-field | `exercise/__init__.py:41-43`, `schema.py`, `exercise_matching_csv.py:47-54` | Implemented | Negative CSV test | — | — | Add negative test |
| 12 | Browser tab title | Title still generic | `index.html:7` static title; no per-page `document.title` | `apps/web/legacy-frontend/index.html:7` | Absent | Existing issue #267 | #267 | Janice | — |
| 13 | License line | Checklist "once Ann provides it" | D13 already records Ann's wording; constant on opening screen; nullable `license_line` unused | `ExerciseEntry.tsx`, `schema.py:133` | Partial / decision mismatch | #273 | — | Reconcile #273 |
| 14 | Oct 16 reset runbook | Checklist + issue draft 6 | Per-team reset endpoint documented; no Oct 16 runbook | `exercise-hosting.md`, `InstructorTeams.tsx:1-41` | Blocked on owner/deployment | Ops, runbook | #323 | Danny | Verify environment |
| 15 | E2E / acceptance mapped to checklist | Checklist row-by-row; #299 | Unit/integration cover server rows; browser/projection/load-time checks manual | Multiple test files | Partial | E2E harness or manual acceptance | #299 | Justin | No GitHub username; unassigned |
| 16 | Deployment/source reconciliation | Ann tested live GCP site; repo says no deployment | Deployed SHA / env unknown | `exercise-hosting.md`, runbook | Needs verification | All "implemented" rows | #323 | Danny | Identify live build |
| 17 | Date plan: Oct 14 / Oct 16 / Oct 30 | Audit doc exec summary | Milestone #1 exists with 2026-10-14 due date; scoped issues added to Project | GitHub milestone + Project | Implemented | Plan communication | — | — | Confirm dates with Ann |

### Source/deployment note

Stakeholder observations came from a deployed site whose commit SHA has not been verified. Source evidence is from `main` at `ec471ba222bbad91c16b6875e41d250592041e37`. Do not attribute live behavior to this commit until the deployed SHA is recorded.

## Checklist-to-tests-and-operations mapping

| Checklist concern | Automated tests | Manual acceptance / gap |
|---|---|---|
| Two concurrent teams | `test_exercise_workspace_router.py:312`, `test_exercise_results_refresh.py:114`, `test_exercise_workspace_persistence.py:186,405,770`, `test_exercise_results_persistence.py:417,738` | — |
| Reload / re-entry / second tab | `test_exercise_workspace_router.py:266,285,333`, `test_exercise_results_persistence.py` | Browser-level double-click / two-tab race |
| Upload: `event_description` + removed-column refusal, old dataset kept | `test_exercise_ingest.py:327,336`, `test_exercise_dataset_repository.py:243,310` | Refused upload leaves *active* dataset unchanged (add test); `event_description` not yet implemented |
| Hidden-column download exclusion | `test_exercise_matching_router.py:732` and model-walk tests | Add negative CSV-byte test |
| Refresh isolation + refresh-all | `test_exercise_results_refresh.py:102,338-424`, `test_exercise_results_persistence.py:738,773` | Refresh-all UI confirmation |
| Clear-team isolation | `test_exercise_workspace_persistence.py:489,537,554`, `test_exercise_results_persistence.py:795,838` | — |
| Result locks / one run | `test_exercise_results_rules.py:178,208`, `test_exercise_results_persistence.py:248,306,362,1003,1185,1210` | Verify on deployed build |
| Browser title | None (static HTML) | Add per-page titles (#267) |
| Projector / load time < 5 s | Static layout-contract tests only | Classroom-machine measurement |
| Reset runbook | None | Prepare runbook; do not execute without separate confirmation |

## SWE-2 Max planning protocol

1. Use up to five parallel read-only audit sessions with no nested delegation: stakeholder requirements, backend/data contracts, frontend/accessibility, tests/operations, and adversarial issue/decision review.
2. The orchestrator verifies material claims and retains documentation edits, issue mutations, Kanban configuration, and final synthesis.
3. Agents produce specifications, task decomposition, acceptance criteria, dependencies, and test plans only; they do not modify product code or operate deployments.
4. Each issue specification receives an evidence and completeness review before it is marked ready for its collaborator.
5. A final adversarial review checks duplicate issues, unsupported claims, hidden-field leakage, missing requirements, date sequencing, and unsafe operational instructions.

## Verification specified for collaborators

Each issue must name its focused red/green test commands and the applicable repository gates:

- `make check`
- `make test-integration` for schema, persistence, or API changes with PostgreSQL 16 available
- `make migrate-check` for migrations
- `make openapi-check` for response-contract changes
- frontend tests and build commands required by `apps/web/DESIGN.md`
- manual classroom-machine checks only when the actual environment is available

A skipped integration or live check must be reported as skipped, never passed. This planning effort validates documentation links and evidence but does not claim that unimplemented product acceptance tests pass.

## Definition of done for this planning effort

- Every stakeholder requirement is represented in an evidence-backed audit matrix.
- Every confirmed gap maps to a deduplicated, implementation-ready issue with acceptance criteria, dependencies, test expectations, and source references.
- Every scoped issue is assigned where ownership is evidenced and dated 2026-10-14 through milestone and Project field where available.
- Policy-gated work identifies its decision owner and remains explicitly blocked.
- Hidden-field safeguards, source/deployment distinctions, and destructive-operation boundaries are explicit in every affected specification.
- The documentation-only PR is reviewed but not merged automatically.
- No product code, deployment, or live exercise state is changed by this effort.
