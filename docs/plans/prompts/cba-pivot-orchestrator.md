# CBA pivot orchestrator prompt

Copy the XML body below into a **GPT 5.6 Extra High** planning session. It is a documentation orchestrator, not an implementation card.

```xml
<role>
Lead CBA pivot orchestrator for IA SmartMatch Revamped. Operate as a repository-grounded product/architecture planner. This session produces and repairs planning documentation only; it does not implement a wave, create branches, commit, push, open PRs, deploy, enable providers, or mutate external state.
</role>

<mission>
Treat the consolidated CPP College of Business Administration customer requirements as product authority. Reconcile them against the current repository, delegate six bounded read-only reconnaissance tracks when subagent routing is available, synthesize one evidence-backed gap analysis, refine a Wave 0–5 implementation train, and produce one copy-paste /goal XML card per implementation track. Preserve working architecture while replacing superseded IA-West terminology, classifications, matching policy, and workflows. Gate only out-of-scope or demonstrably false/incomplete CBA surfaces; never delete historical code or disable a working capability merely because its current naming needs refinement.
</mission>

<context>
Repository: C:\Users\DangT\Documents\GitHub\IA-Smart-Match-Revamped
Customer source outside repository: C:\Users\DangT\curseforge\Downloads\cba_smart_match_customer_requirements.md
In-repository authoritative copy: docs/product/cba-smart-match-customer-requirements.md
Planning source that seeded this prompt: C:\Users\DangT\.cursor\plans\cba_pivot_orchestrator_2b48f1a1.plan.md

Expected planning artifacts:
- docs/product/cba-smart-match-customer-requirements.md
- docs/plans/open-questions/cba-phase-deferred.md
- docs/plans/2026-09-05-cba-pivot-recon.md
- docs/plans/2026-09-05-cba-pivot-waves.md
- docs/plans/cba-goal-catalog.md
- docs/plans/prompts/cba-recon-R-MATCH.md
- docs/plans/prompts/cba-recon-R-ROLES.md
- docs/plans/prompts/cba-recon-R-EVENTS.md
- docs/plans/prompts/cba-recon-R-CONTACTS.md
- docs/plans/prompts/cba-recon-R-OUTREACH.md
- docs/plans/prompts/cba-recon-R-GATES.md

Observed baseline at prompt authoring:
- Working-tree migration head: db/migrations/versions/0021_outreach_schema.py.
- Checked-in OpenAPI: 25 paths / 27 operations.
- Local branch was main, observed 4 commits behind origin/main.
- make was unavailable in the observed PowerShell environment.

These values are evidence to re-check, not eternal facts. Inspect the current tree before relying on them. Do not claim checks passed merely because a prior run recorded a count.
</context>

<assumptions treat_as_true>
- The CBA change is a product pivot, not a greenfield rebuild.
- The in-repository requirements copy must remain text-equivalent to the customer source after line-ending normalization.
- Existing architecture, event browse direction, registration intent, calendar, role-based authz, consented invitation path, R/Y/G discovery feed, and immutable match-run architecture are assets to preserve.
- Stable stored role strings may remain while visible persona labels change. Storage roles, presentation labels, and authorization powers are three separate things.
- Fixture/synthetic providers are the safe default. Live providers, live data, institutional identity, and cloud deploy remain fail-closed.
- Existing planning/recon files may contain good prior work. Inspect and improve them in place; do not duplicate them.
- The wave proposal below is a strong starting hypothesis. It is not a mandate to copy blindly; repository evidence may justify a split, merge, reorder, or narrower fence if the rationale is documented.
</assumptions>

<model_routing>
Conceptual routing:
- Orchestrator, synthesis, wave refinement, and catalog authoring: GPT 5.6, extra-high reasoning.
- R-MATCH, R-ROLES, R-EVENTS, R-CONTACTS, R-OUTREACH, and R-GATES: GPT 5.6 Sol, low reasoning, read-only and parallel.
- Future implementation cards: a capable implementation model selected by the user/tooling.
- Future PR review: GPT 5.6 medium or repository-approved reviewer.

The recon model label describes desired routing. Do not claim that the current agent or environment can route to Sol 5.6 Low unless the tool actually exposes that model. If exact routing is unavailable, perform the same bounded reads directly or use the closest user-approved route and record the limitation.
</model_routing>

<non_negotiables>
1. Customer authority
   - Final default matching weights: Industry 30%, Role 25%, Topic 15%, Proximity 30%.
   - 20 exact NAICS sector groups and 10 exact CBA role categories.
   - Speaker/contact: one primary Industry and one primary Role.
   - Speaker Request: multiple Industries and multiple Roles.
   - Topic: semantic comparison, fit score, one-sentence reasoning, and a customer-directed neutral/middle treatment when evidence is thin.
   - Proximity: miles from CPP campus, 0–25 / 25–75 / 75+ bands.
   - Virtual: exclude Proximity and redistribute its 30%, formula unresolved.
   - Shortlist: approximately 2–3 candidates; do not emphasize an overall percentage.
   - Student Events page: preserve browse/agenda content and place the month calendar at the bottom.
   - Rewards/points stay. Refinements and career-readiness wording are P2.

2. Explicit CBA scope boundary
   - No external speaker discovery, LinkedIn scraping, other scraping, automatic external event discovery, cold outreach to unknown contacts, full external CRM acquisition, chapter membership/dues, or branding-only redesign.
   - Manual records already in the system are the match pool.
   - Preserve fixture ingest for deterministic tests; do not expose it as live CBA discovery.

3. Architecture invariants
   - One standard login; no role/portal chooser.
   - Identity, tenant, unit, and roles come from verified backend state, never request-body/browser assertions.
   - Deny-by-default authorization remains server-side; route visibility is UX only.
   - Request paths record intent and workers perform consequential/provider work where the existing command architecture requires it.
   - Domain purity/import-linter boundaries remain.
   - Unknown is not zero under ADR-0011 unless an accepted CBA ADR defines a distinct neutral policy value and its provenance.
   - Match runs pin registry/formula/optimizer/provider inputs and remain reproducible.
   - One Alembic revision per PR; migration numbering is head+1 at branch time, never assumed from this prompt.
   - OpenAPI is regenerated, never hand-edited; API/authz serial resources merge one at a time.

4. Decisions before behavior
   - An accepted ADR must resolve neutral Topic scoring and virtual redistribution before the Wave 3 CBA registry merges.
   - The same decision must define exact proximity sub-scores/boundaries or explicitly version a configurable approved policy.
   - Student feedback schema is an OQ gate; do not invent a permanent scale, anonymity rule, edit policy, or aggregate.

5. Rewards correction
   - Do not prescribe disabling every rewards route/page. Preserve truthful server-backed rewards and points.
   - Gate only a named chapter-specific, unfunded, incomplete, or fake-success surface, with evidence.
   - Defer optional CBA wording/refinements rather than treating the capability itself as out of scope.

6. Operational safety
   - ALLOW_LIVE_PROVIDERS=false, ALLOW_LIVE_DATA=false, and ALLOW_CLOUD_DEPLOY=false unless the user explicitly authorizes otherwise in a future implementation session.
   - This planning session performs no commit, push, PR, deployment, branch switch, pull, merge, rebase, or reset.
</non_negotiables>

<read_first order="strict">
Read all of these before dispatching recon or editing synthesis/waves:
1. docs/product/cba-smart-match-customer-requirements.md
   Why: product authority; map every §25 P0/P1/P2 item and every §26 unresolved decision.
2. docs/architecture/decisions/ADR-0011-accountable-numbers.md
   Why: unknown-versus-zero, canonical metric, and exact drill-down requirements conflict with an unlabeled neutral score or silent weight re-spread.
3. docs/architecture/decisions/ADR-0012-event-identity-and-tag-vocabulary.md
   Why: manual event entry must keep deterministic identity and quarantine; its event tags are not CBA career roles.
4. python/smartmatch_domain/smartmatch_domain/factor_registry.py
   Why: current approved, implemented 70/30 registry and normalize_weights seam.
5. services/api/smartmatch_api/main.py
   Why: actual mounted routers and composition boundary.
6. services/api/smartmatch_api/config.py
   Why: Edition/provider defaults; product phase must not be confused with deployment environment.
7. .cursor/skills/opus-goal-prompting/SKILL.md
   Why: required XML card shape and objective verification discipline.
8. .cursor/skills/opus-goal-prompting/goal-catalog-post-merge.md
   Why: identify merged/superseded goals and reusable G7–G9/G1 partial architecture.
9. docs/plans/2026-09-03-pilot-parallel-goal-prompts.md
   Why: branch/PR fences, serial resources, and test-first prompt patterns.
10. docs/plans/frontend-broken-buttons.md
    Why: concrete false-success and missing-contract inventory; some entries may be outdated, so verify in code.
11. apps/web/DESIGN.md
    Why: truthful UI/provenance constraints and unresolved design work; customer’s newer month-calendar placement controls CBA student Events.
12. docs/decisions/g3-crawler-decision.md
    Why: fixture/live discovery boundaries, rejected LinkedIn, and no live authorization.
13. docs/architecture/diagrams/2026-09-04-system-process-architecture-diagrams.md
    Why: broad shipped/planned topology, but verify captions against current code because the document records drift.
14. docs/plans/open-questions/cba-phase-deferred.md
    Why: decision register and gate semantics; repair any rewards contradiction.
15. all six docs/plans/prompts/cba-recon-R-*.md
    Why: reuse and validate existing recon scopes instead of recreating prompts.
</read_first>

<file_map purpose="Authoritative implementation map and why each location matters">
  <matching customer_sections="5-11, 25">
    - python/smartmatch_domain/smartmatch_domain/factor_registry.py
      Current registry/version/status, active keys, centralized normalization seam.
    - python/smartmatch_domain/smartmatch_domain/scoring.py
      Current two-factor composition and no-respread behavior.
    - python/smartmatch_domain/smartmatch_domain/factors/topic_relevance.py
      Lexical set-overlap Topic behavior and None-on-missing evidence.
    - python/smartmatch_domain/smartmatch_domain/factors/travel_burden.py
      Haversine kilometers between synthetic points, not CPP mile bands.
    - python/smartmatch_domain/smartmatch_domain/factors/__init__.py
      FactorScore/zero classification contract.
    - python/smartmatch_domain/smartmatch_domain/optimizer.py
      Deterministic CP-SAT selection; explicit portfolio size.
    - python/smartmatch_domain/smartmatch_domain/explanation.py
      2–3 presentation constants, no-percentage policy, registry/provenance/state.
    - python/smartmatch_domain/smartmatch_domain/match_run.py
      Pins/fingerprints for reproducibility.
    - services/api/smartmatch_api/routers/match_runs.py
      Existing unit-scoped create/read contract.
    - services/worker/smartmatch_worker/handlers.py
      Current match-run execution and persisted result.
    - python/smartmatch_persistence/smartmatch_persistence/match_runs.py
      Immutable snapshot storage.
    - apps/web/legacy-frontend/src/app/pages/AIMatching.tsx
      Existing presentation/legacy workflow surface; verify no fake ranks or percentages.
    - tests/unit/test_factor_registry.py
    - tests/unit/test_scoring.py
    - tests/unit/test_topic_relevance.py
    - tests/unit/test_travel_burden.py
    - tests/unit/test_optimizer.py
    - tests/unit/test_explanation.py
    - tests/unit/test_matching_approved_golden.py
    - tests/golden/matching/approved/
    - tests/contract/test_match_runs_api.py
      Existing executable coverage to extend, never evidence that CBA requirements already pass.
  </matching>

  <roles_auth_terminology customer_sections="2-4, 25">
    - services/api/smartmatch_api/routers/auth.py
      Pilot login takes email/password only and returns opaque session.
    - services/api/smartmatch_api/routers/me.py
      Backend identity/membership source.
    - services/api/smartmatch_api/routers/portals.py
      Stored-role-to-shell mapping and current IA-West labels.
    - python/smartmatch_authz/smartmatch_authz/policy.py
      Authorization powers; must not be inferred from labels.
    - tools/seed_pilot_logins.py
      Stored pilot role fixtures and naming.
    - apps/web/legacy-frontend/src/app/pages/LoginPage.tsx
      One login, no role chooser, but stale IA-West copy.
    - apps/web/legacy-frontend/src/lib/principal.ts
    - apps/web/legacy-frontend/src/app/hooks/useSession.tsx
    - apps/web/legacy-frontend/src/app/hooks/usePortalAccess.tsx
    - apps/web/legacy-frontend/src/app/components/PortalGate.tsx
      Server-derived identity and UX-only shell gating.
    - apps/web/legacy-frontend/src/app/routes.tsx
    - apps/web/legacy-frontend/src/app/components/Layout.tsx
    - portal layout components
      Visible IA-West/admin/coordinator/volunteer surfaces.
    - tests/unit/test_frontend_auth_contract.py
    - tests/authz/test_route_roles.py
      Regression boundaries for one login/backend roles and server powers.
  </roles_auth_terminology>

  <events_calendar_registration customer_sections="12, 15, 25">
    - services/api/smartmatch_api/routers/events.py
      Read-only admin/coordinator event catalog and quarantine; no Event Host create.
    - db/migrations/versions/0017_event_persistence.py
    - python/smartmatch_persistence/smartmatch_persistence/events.py
      Existing event identity/tag/provenance storage.
    - python/smartmatch_domain/smartmatch_domain/events.py
    - python/smartmatch_domain/smartmatch_domain/event_vocabulary.py
      ADR-0010/0012 constraints and the separate event tag vocabulary.
    - services/worker/smartmatch_worker/event_ingest.py
      Fixture ingest only; not the Host write path.
    - python/smartmatch_domain/smartmatch_domain/calendar_invite.py
    - python/smartmatch_domain/smartmatch_domain/ics.py
      Existing truthful ICS generation seam.
    - apps/web/legacy-frontend/src/app/pages/student/StudentEvents.tsx
      Current unavailable registrations view; target must add browse/agenda plus bottom calendar.
    - apps/web/legacy-frontend/src/app/pages/Calendar.tsx
      Existing admin/coordinator month-grid implementation and provenance treatment.
    - apps/web/legacy-frontend/src/app/pages/coordinator/CoordinatorEvents.tsx
    - apps/web/legacy-frontend/src/app/pages/Opportunities.tsx
      Existing stubs/naming around event/request/matching.
    - tests/contract/test_events_api.py
    - tests/unit/test_calendar_invite_wiring.py
    - tests/golden/test_calendar_invite_golden.py
      Existing read/calendar coverage to extend.
  </events_calendar_registration>

  <contacts_import_classification customer_sections="13, 18-19, 25">
    - services/api/smartmatch_api/routers/imports.py
      Existing durable admin/coordinator inline import command.
    - services/worker/smartmatch_worker/handlers.py
      Column validation and review-item creation.
    - docs/pilot-data/columns.yaml
      Current SSOT for import columns; lacks CBA fields.
    - services/worker/smartmatch_worker/column_contract.py
      Fail-closed file adapter; never duplicate column names in Python.
    - services/api/smartmatch_api/pipeline_provisioning.py
      Current review-accept identity/journey provisioning.
    - db/migrations/versions/0012_professional_unit_relationship.py
    - python/smartmatch_persistence/smartmatch_persistence/professionals.py
      Existing professional-to-unit relationship, not CBA classifications.
    - db/migrations/versions/0021_outreach_schema.py
      Current contact_channel/outreach base.
    - python/smartmatch_domain/smartmatch_domain/consent.py
      Contact state and send-eligibility boundary.
    - docs/plans/open-questions/r4-outreach-deferred.md
      Existing production-contact/live deferrals.
  </contacts_import_classification>

  <outreach_invitations customer_sections="6, 13-14, 25 P1">
    - services/api/smartmatch_api/routers/outreach.py
      Existing consented draft/list/send/read/unsubscribe contract.
    - services/worker/smartmatch_worker/outreach.py
      Delivery-time consent recheck and fixture/live provider behavior.
    - python/smartmatch_persistence/smartmatch_persistence/outreach.py
      Durable drafts/sends/delivery events/contact channels.
    - apps/web/legacy-frontend/src/app/pages/coordinator/CoordinatorOutreach.tsx
      Current wired coordinator path; verify actual behavior.
    - apps/web/legacy-frontend/src/app/pages/Outreach.tsx
    - apps/web/legacy-frontend/src/components/AgenticOutreachPanel.tsx
    - apps/web/legacy-frontend/src/lib/api.ts legacy /api/data helpers
      Legacy cold/specialist/agentic trust model; CBA gate, never merge with /v1.
    - .cursor/skills/opus-goal-prompting/goal-catalog-post-merge.md G7-G10
      Reusable architecture and superseded work.
  </outreach_invitations>

  <feedback_pipeline_metrics_rewards customer_sections="15-17, 25">
    - python/smartmatch_domain/smartmatch_domain/feedback.py
      Coordinator match-outcome feedback, not student speaker ratings.
    - python/smartmatch_domain/smartmatch_domain/pipeline.py
    - python/smartmatch_persistence/smartmatch_persistence/pipeline.py
    - db/migrations/versions/0011_pipeline_record.py
      Existing historical stages; preserve confirmed/attended, gate CBA member_inquiry writer/narrative.
    - python/smartmatch_domain/smartmatch_domain/metrics.py
    - services/api/smartmatch_api/routers/metrics.py
      Registered owning-query/drill-down model.
    - apps/web/legacy-frontend/src/app/components/DiscoveryFeed.tsx
    - apps/web/legacy-frontend/src/app/components/PipelineFunnelTiles.tsx
    - apps/web/legacy-frontend/src/app/pages/Dashboard.tsx
      Preserve R/Y/G; remove only unsupported CBA narratives.
    - services/api/smartmatch_api/routers/rewards.py
    - python/smartmatch_domain/smartmatch_domain/rewards.py
    - python/smartmatch_persistence/smartmatch_persistence/rewards.py
    - apps/web/legacy-frontend/src/app/pages/student/StudentRewards.tsx
      Working rewards capability to preserve; P2 copy/refinement, not blanket gate.
  </feedback_pipeline_metrics_rewards>

  <scope_and_operations customer_sections="20-22, 25 P2">
    - docs/decisions/g3-crawler-decision.md
    - python/smartmatch_providers/smartmatch_providers/fixture_ingest.py
    - services/worker/smartmatch_worker/paid_extraction.py
    - apps/web/legacy-frontend/src/components/CrawlerFeed.tsx
      Fixture versus forbidden live discovery boundary.
    - apps/web/legacy-frontend/src/app/pages/LandingPage.tsx
      Scraping/CRM/IA-West claims that are false for CBA.
    - services/api/smartmatch_api/config.py
    - services/worker/smartmatch_worker/config.py
    - tools/env_isolation_check.py
      Fixture/live and deployment isolation.
    - apps/web/DESIGN.md
      Branding/design remains secondary and partly unresolved.
  </scope_and_operations>

  <serial_resources>
    - db/migrations/versions/*.py
    - python/smartmatch_persistence/smartmatch_persistence/schema.py
    - contracts/openapi/smartmatch.json
    - tests/authz/test_policy_matrix.py
    - tests/authz/test_route_roles.py
    - python/smartmatch_domain/smartmatch_domain/factor_registry.py
    - tests/golden/matching/**
    - apps/web/legacy-frontend/src/lib/api.ts
  </serial_resources>
</file_map>

<deferral_policy>
Maintain docs/plans/open-questions/cba-phase-deferred.md as the authoritative planning gate.

Required unresolved decisions:
- OQ-CBA-001: virtual-event 30% redistribution formula.
- OQ-CBA-002: exact proximity band values and exact 25/75 boundary ownership.
- OQ-CBA-003: student feedback scale, fields, eligibility, edit/anonymity/retention/aggregation.
- OQ-CBA-004: ADR-0011 interaction with neutral Topic and virtual conditional normalization.
- OQ-CBA-005: optional future overall-score presentation; safe default is no prominent percentage.

Required safe defaults:
- No CBA registry merge before an accepted scoring ADR resolves OQ-CBA-001/002/004.
- No student feedback storage/UI before OQ-CBA-003 is approved.
- No prominent overall percentage.
- No live provider/data/deploy.
- No external discovery or cold unknown-contact outreach.
- No CBA member_inquiry writer or narrative unless an approved outcome decision renames/redefines it.

Gate, preserve, and defer are distinct:
- Gate: retain code/data, remove CBA reachability/claims.
- Preserve: retain working capability and regression-test it.
- Defer-OQ: block only behavior dependent on the unresolved decision.
- Rewards are preserve + P2 refinement, not a globally gated capability.
</deferral_policy>

<suggested_waves purpose="Starting hypothesis to test against recon; preserve strengths, correct weak assumptions">
Strengths to preserve:
- Wave 0 scope policy first.
- Wave 1 parallel and migration-free.
- Wave 2 taxonomy/schema before matching/workflows.
- Wave 3 accepted scoring ADR plus one serial registry/golden integration owner.
- Wave 4 durable CBA workflows.
- Wave 5 reuse G7-G9/G1 partial for consent, invitations, calendar, and pipeline.

Starting track hypothesis:

Wave 0 — serial foundation
- CBA-SCOPE-POLICY: one product-phase/capability policy distinct from deployment Edition.

Wave 1 — parallel, no migrations
- CBA-TERMINOLOGY: CBA/Student/Connector/Speaker Request visible copy.
- CBA-ROLE-PRESENTATION: visible persona aliases over stable stored roles; one login/backend roles preserved.
- CBA-SCOPE-COMPOSITION: apply Wave 0 policy to navigation/composition; gate external discovery, cold legacy outreach, membership/dues, and member_inquiry narrative; preserve discovery and truthful rewards.

Wave 2 — taxonomy/schema
- CBA-TAXONOMY: exact 20 NAICS + 10 CBA roles, separate from event tags.
- CBA-DATA-SCHEMA: speaker one-primary, request multi-select, Topic/location/virtual fields; one migration.
- CBA-IMPORT-CONTRACT: CBA source columns in columns.yaml and fail-closed validation.

Wave 3 — decisions then matching
- CBA-SCORING-ADR: accepted neutral/proximity/virtual policy.
- CBA-MATCH-INDUSTRY-ROLE: fenced factor implementations, no registry edit.
- CBA-MATCH-PROXIMITY: CPP miles/bands under ADR, no registry edit.
- CBA-MATCH-TOPIC: semantic fixture provider, score and one-sentence rationale, no registry edit.
- CBA-MATCH-REGISTRY: sole serial owner of registry, scoring wiring, pins, and approved CBA golden cases.
- CBA-MATCH-WEIGHTS: unit-scoped Connector settings, snapshots, API.

Wave 4 — workflows, parallel development but serial merges on migration/OpenAPI/authz
- CBA-EVENT-REQUEST: Event Host durable Speaker Request create.
- CBA-CONTACT-MANAGEMENT: Connector manual add and classification corrections.
- CBA-IMPORT-CLASSIFY: company/title proposal, human review/correction.
- CBA-STUDENT-FEEDBACK: only after OQ-CBA-003.

Wave 5 — preserve/complete path
- CBA-STUDENT-EVENTS: browse/register/ICS; month calendar last on Events page (G8 reuse).
- CBA-CONTACT-LIFECYCLE: approved-source contact transitions (G9 reuse).
- CBA-INVITATIONS: shortlist batch, response tracking, fixture delivery (G7 reuse).
- CBA-HANDOFF-PIPELINE: confirmed/attended and Host handoff; no member_inquiry writer (G1 partial).
- CBA-REWARDS-REFINEMENT: P2 wording/narrow fixes while preserving working rewards.

For every changed track grouping, explain:
- which repository evidence forced the change;
- whether P0/P1/P2 ownership stays unique;
- which serial resource and predecessor now govern merge order.
</suggested_waves>

<phase_0_recon>
If subagents are available, dispatch exactly six read-only recon tasks in parallel using the existing prompt files. Desired conceptual model is GPT 5.6 Sol Low; record honestly if unavailable. Do not rely on inaccessible reports from prior interrupted runs.

R-MATCH:
- Prompt: docs/plans/prompts/cba-recon-R-MATCH.md
- Customer §§5–11 and §25 matching.
- Return current behavior, conflicts, missing tests, and one disposition per finding.

R-ROLES:
- Prompt: docs/plans/prompts/cba-recon-R-ROLES.md
- Customer §§2–4 and §25 terminology/auth.
- Separate stored role, visible label, and permission.

R-EVENTS:
- Prompt: docs/plans/prompts/cba-recon-R-EVENTS.md
- Customer §§12, 15 and §25 event/calendar.
- Preserve browse/agenda and require bottom month calendar.

R-CONTACTS:
- Prompt: docs/plans/prompts/cba-recon-R-CONTACTS.md
- Customer §§18–19 and §25 contacts/classification.
- Preserve consent and quarantine.

R-OUTREACH:
- Prompt: docs/plans/prompts/cba-recon-R-OUTREACH.md
- Customer §§6, 13–14 and §25 P1.
- Contrast consented /v1 with legacy cold paths.

R-GATES:
- Prompt: docs/plans/prompts/cba-recon-R-GATES.md
- Customer §§17, 20–22 and §25 gate/P2.
- Preserve rewards; gate only wrong/incomplete surfaces.

If subagents are unavailable, perform the same six scopes sequentially/directly. In either case, merge into docs/plans/2026-09-05-cba-pivot-recon.md with:
- sections for matching; roles/auth/terminology; events/calendar/registration; contacts/import/classification; outreach/invitations; feedback; pipeline/metrics/discovery; gated scope;
- path-and-line evidence;
- one preserve | gate | build new | defer-OQ disposition per finding;
- baseline and evidence limitations;
- a unified §25 list where every P0 requirement appears exactly once as sole track owner or explicit OQ→track dependency.
</phase_0_recon>

<phase_1_self_counsel>
Before finalizing docs/plans/2026-09-05-cba-pivot-waves.md:
1. Compare recon to suggested_waves; do not copy the hypothesis without review.
2. Preserve Wave 0–5 strengths unless evidence supplies a written reason to change them.
3. For each track include:
   - track ID and branch name;
   - dependencies and merge order;
   - precise file fence;
   - strict read_first;
   - deliverables;
   - first 1–3 failing tests, including at least one exact test path;
   - objective success criteria;
   - serial resources;
   - demo-critical status;
   - deferred overlaps.
4. Assign unique ownership for every §25 P0 item and identify P1/P2 owners.
5. Keep migration, OpenAPI, authz matrix, registry, approved golden cases, and legacy client serial.
6. Explicitly require an accepted scoring ADR before CBA registry merge.
7. Correct stale assumptions:
   - current matcher exists but is superseded;
   - current events are readable but not Host-writable;
   - current /v1 outreach exists and is consented;
   - current rewards exist and must not be blanket-disabled;
   - student Events lacks registration/calendar composition;
   - member_inquiry is historical, not a CBA narrative.
</phase_1_self_counsel>

<phase_2_goal_catalog>
Write docs/plans/cba-goal-catalog.md.

For every implementation track in the final wave plan, write one copy-paste card beginning with `/goal` and containing:
- <role>
- <mission>
- <context> with repository, exact branch, PR base main, dependencies, and serial locks
- <read_first order="strict">
- <non_negotiables>
- <deliverables>
- <test_first>
- <deferral_policy>
- <anti_patterns>
- <success_criteria>
- <output_format>

Catalog rules:
- One branch and one PR per card; cards are plans and are not executed in this orchestration session.
- Mark launch/merge ordering and serial resources before cards.
- Every card has at least one exact test path.
- Commands are truthful: targeted `python -m pytest ...`; `make check` required in an environment where make exists; report unavailable locally without substitution claims.
- Every API card regenerates OpenAPI and updates policy tests in the same PR.
- Every migration card uses one head+1 revision determined from current main.
- Every matching card forbids weight literals outside registry/settings, prominent percentages, and live semantic providers by default.
- Every workflow card forbids legacy `/api/data/*`, `fetchSpecialists`, fake local success, and CBA member_inquiry writes.
- Every card preserves fail-closed live gates.
</phase_2_goal_catalog>

<deliverables>
Create or repair exactly these planning artifacts:
1. docs/product/cba-smart-match-customer-requirements.md
   Exact customer copy after line-ending normalization; do not editorialize it.
2. docs/plans/open-questions/cba-phase-deferred.md
   OQs and gates; rewards preserved with only P2/narrow defect gates.
3. docs/plans/2026-09-05-cba-pivot-recon.md
   Evidence-backed current-state synthesis and unique §25 ownership.
4. docs/plans/2026-09-05-cba-pivot-waves.md
   Refined Wave 0–5 implementation train.
5. docs/plans/cba-goal-catalog.md
   One /goal XML card per final implementation track.
6. docs/plans/prompts/cba-recon-R-MATCH.md
7. docs/plans/prompts/cba-recon-R-ROLES.md
8. docs/plans/prompts/cba-recon-R-EVENTS.md
9. docs/plans/prompts/cba-recon-R-CONTACTS.md
10. docs/plans/prompts/cba-recon-R-OUTREACH.md
11. docs/plans/prompts/cba-recon-R-GATES.md
12. docs/plans/prompts/cba-pivot-orchestrator.md

Inspect and repair existing artifacts in place. Do not create alternate copies with suffixes.
</deliverables>

<anti_patterns>
- Do not implement Wave 0, Wave 1, or any product code in this session.
- Do not create migrations, flags, tests, branches, commits, pushes, PRs, or deployments.
- Do not clean/revert unrelated untracked or modified content.
- Do not pull/rebase/reset a branch that is behind.
- Do not rely on prior inaccessible subagent reports.
- Do not port the legacy Nebiux multi-factor matcher.
- Do not present the old 70/30 matcher as CBA-complete.
- Do not call labels security or grant powers by renaming them.
- Do not make a calendar-only Student Events page; month calendar belongs at the bottom under browse/agenda.
- Do not hide all rewards; customer says keep rewards/points.
- Do not merge legacy cold outreach with consented /v1 outreach.
- Do not invent external discovery, live provider, deployment, feedback schema, virtual formula, proximity values, or neutral-score semantics.
- Do not hand-edit OpenAPI or assign duplicate §25 P0 ownership.
- Do not cite a planned future path as if it exists; label it “planned.”
- Do not claim `make check` passed where make is unavailable.
</anti_patterns>

<success_criteria>
The orchestration package is complete only when current evidence proves all of the following:
- The external customer source and in-repo copy are text-equivalent after line-ending normalization.
- All twelve deliverable paths above exist.
- All Markdown links/backticked repository paths in newly created artifacts resolve, except future paths explicitly labeled “planned.”
- The six recon prompts reference existing paths or explicitly tell the reader to locate a renamed equivalent.
- Recon covers matching, roles/auth/terminology, events/calendar/registration, contacts/import/classification, outreach/invitations, feedback, pipeline/metrics/discovery, and gated scope.
- Recon records migration 0021/OpenAPI 25/27/make-unavailable/branch-behind only if re-verification still supports each fact.
- Every customer §25 P0 checklist item appears exactly once as an owning track or explicit OQ dependency.
- Wave plan contains branch, dependencies, fence, read_first, deliverables, first failing tests, success criteria, serial resources, demo-critical status, and deferred overlaps for every track.
- Wave 3 registry merge is blocked on an accepted ADR covering neutral Topic and virtual redistribution.
- Goal catalog contains exactly one card per wave-plan implementation track.
- Every card has <test_first> and at least one exact test path.
- Documentation-focused checks available without make pass, and unavailable tooling is reported honestly.
- No product code/config/migration/test/commit/push/PR/deploy change was made by this session.
</success_criteria>

<output_format>
End with:
1. Status: DONE | DONE_WITH_CONCERNS | BLOCKED.
2. Files created and files modified.
3. Verification performed, including requirements parity, baseline counts, path/link validation, §25 unique ownership, and card/test-first coverage.
4. Remaining concerns limited to real evidence gaps, unavailable tooling, unresolved OQs, or branch drift.
5. Explicit statement that no implementation, commit, push, PR, or deployment occurred.
</output_format>
```

