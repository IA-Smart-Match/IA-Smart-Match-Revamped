# CBA pivot `/goal` catalog

**Date:** 2026-09-05  
**Source plan:** [`2026-09-05-cba-pivot-waves.md`](2026-09-05-cba-pivot-waves.md)  
**Use:** Copy one card into a new implementation session. Do not execute cards from this documentation session.

## Launch and merge discipline

- Every card creates exactly one branch from then-current `origin/main` and one PR to `main`.
- Launch order: Wave 0 → Wave 1 in parallel → Wave 2 taxonomy, then schema/import contract → Wave 3 scoring ADR, three factor lanes in parallel, serial registry integration, then weight settings → Wave 4 dependency-ready tracks → Wave 5 completion tracks.
- Merge one at a time when touching migrations, `schema.py`, OpenAPI, authz matrices, `factor_registry.py`, approved matching golden files, or legacy `api.ts`.
- A card may use `make check` only where `make` exists. It must always run its targeted `python -m pytest ...` commands and report unavailable tooling truthfully.
- Planned paths below are intentionally marked **(planned)** on first declaration. Repeated references to the same path inside that card’s success command retain that planned status; creating those paths is part of the named card.

## Wave 0

### CBA-SCOPE-POLICY

```xml
/goal Establish one fail-closed CBA product-scope capability policy without implementing any CBA feature. Branch feat/cba-scope-policy from current origin/main; one PR to main.

<role>Lead implementation agent for CBA-SCOPE-POLICY.</role>
<mission>Give API composition and frontend navigation one explicit policy for CBA scope, distinct from deployment Edition.</mission>
<context>Repository: IA-Smart-Match-Revamped. Branch: feat/cba-scope-policy. PR base: main. Wave 0 and predecessor to all CBA tracks. Serial owner: capability-policy representation and any main.py composition edit.</context>
<read_first order="strict">
1. docs/product/cba-smart-match-customer-requirements.md §§1,3-4,17,20-22
2. docs/plans/open-questions/cba-phase-deferred.md
3. services/api/smartmatch_api/config.py
4. services/api/smartmatch_api/main.py
5. apps/web/legacy-frontend/src/app/routes.tsx
6. tools/env_isolation_check.py
</read_first>
<non_negotiables>Product phase is not deployment Edition. Preserve login, event reads, match runs, metrics/discovery, consented outreach, and truthful rewards. Disable external acquisition, cold unknown-contact outreach, chapter dues, and CBA member_inquiry narrative. Live provider/data/deploy defaults stay false. UI gates are not security.</non_negotiables>
<deliverables>One documented capability policy; API/frontend adapters to query it; safe defaults; no feature implementation; no migration or OpenAPI change unless the policy changes mounted routes and the contract is regenerated.</deliverables>
<test_first>First add failing tests at tests/unit/test_cba_scope_policy.py (planned). Extend tests/unit/test_provider_isolation.py and tests/unit/test_no_external_calls_on_request_path.py before implementation.</test_first>
<deferral_policy>Unclear capability ownership goes to docs/plans/open-questions/cba-phase-deferred.md. Default to preserving working in-scope behavior and refusing live/out-of-scope behavior.</deferral_policy>
<anti_patterns>No blanket rewards disable. No label-based authz. No feature code, deployment edits, or separate frontend-only scope truth.</anti_patterns>
<success_criteria>Targeted pytest passes: python -m pytest tests/unit/test_cba_scope_policy.py tests/unit/test_provider_isolation.py tests/unit/test_no_external_calls_on_request_path.py. make check passes where available. Policy behavior is identical in API/frontend tests. One branch/PR only.</success_criteria>
<output_format>PR URL | policy location | enabled preserved capabilities | disabled CBA capabilities | tests | OQs</output_format>
```

## Wave 1 — launch in parallel after Wave 0

### CBA-TERMINOLOGY

```xml
/goal Replace CBA-visible IA-West terminology with the customer-approved CBA vocabulary, with no behavior or schema change. Branch feat/cba-terminology from current origin/main; one PR to main.

<role>Lead implementation agent for CBA-TERMINOLOGY.</role>
<mission>Make visible copy consistently say CBA, Student, Connector Dashboard, Student Portal, and Speaker Request.</mission>
<context>Branch: feat/cba-terminology. PR base: main. Depends on CBA-SCOPE-POLICY. Wave 1 migration-free parallel lane.</context>
<read_first order="strict">
1. docs/product/cba-smart-match-customer-requirements.md §4 and §25
2. apps/web/legacy-frontend/src/app/components/Layout.tsx
3. apps/web/legacy-frontend/src/app/pages/LandingPage.tsx
4. apps/web/legacy-frontend/src/app/pages/LoginPage.tsx
5. apps/web/legacy-frontend/src/app/pages/Opportunities.tsx
6. docs/plans/frontend-broken-buttons.md
</read_first>
<non_negotiables>Speaker remains Speaker. Do not rename backend authorization membership records. Historical docs may retain historical names. No role power, route, matcher, rewards economy, or theme change.</non_negotiables>
<deliverables>CBA-visible copy sweep; scoped forbidden-term scanner; fixture/seed/demo label updates where user-visible; documentation of intentional historical/backend exclusions.</deliverables>
<test_first>Add tests/unit/test_cba_terminology_strings.py (planned), then extend tests/unit/test_frontend_opportunities_contract.py and tests/unit/test_frontend_auth_contract.py.</test_first>
<deferral_policy>CPP green/gold and ambiguous institutional wording are P2; record rather than redesign.</deferral_policy>
<anti_patterns>No blind global replace. No changing identifiers/API fields. No branding project. No hiding rewards.</anti_patterns>
<success_criteria>python -m pytest tests/unit/test_cba_terminology_strings.py tests/unit/test_frontend_opportunities_contract.py tests/unit/test_frontend_auth_contract.py passes; make check where supported; scanner has explicit exclusions.</success_criteria>
<output_format>PR URL | changed surfaces | intentional exclusions | tests | deferred branding</output_format>
```

### CBA-ROLE-PRESENTATION

```xml
/goal Add CBA persona presentation over stable backend roles while preserving one login and deny-by-default permissions. Branch feat/cba-role-presentation from current origin/main; one PR to main.

<role>Lead implementation agent for CBA-ROLE-PRESENTATION.</role>
<mission>Present Student, Event Host, Speaker Connector, and Speaker without treating labels as authorization.</mission>
<context>Branch: feat/cba-role-presentation. PR base: main. Depends on CBA-SCOPE-POLICY. Wave 1, no migrations. Portal response/OpenAPI is serial if its schema changes.</context>
<read_first order="strict">
1. docs/product/cba-smart-match-customer-requirements.md §§2-3
2. services/api/smartmatch_api/routers/auth.py
3. services/api/smartmatch_api/routers/me.py
4. services/api/smartmatch_api/routers/portals.py
5. python/smartmatch_authz/smartmatch_authz/policy.py
6. apps/web/legacy-frontend/src/lib/principal.ts
7. apps/web/legacy-frontend/src/app/components/PortalGate.tsx
8. tests/unit/test_frontend_auth_contract.py
</read_first>
<non_negotiables>Login sends email/password only. Roles come from backend memberships. Keep stored role strings initially. A display alias grants no power; every API route remains server-authorized.</non_negotiables>
<deliverables>Central visible-label mapping; CBA portal labels; documented mapping ambiguity for coordinator/admin; regression coverage for one login/backend roles.</deliverables>
<test_first>Add tests/contract/test_portals_api.py (planned); extend tests/unit/test_frontend_auth_contract.py and tests/authz/test_route_roles.py before changing labels.</test_first>
<deferral_policy>Permanent database-role rename and institutional SSO remain separate decisions.</deferral_policy>
<anti_patterns>No role chooser. No request-body role. No authz widening to make a label convenient. No role logic duplicated in multiple frontend files.</anti_patterns>
<success_criteria>python -m pytest tests/contract/test_portals_api.py tests/unit/test_frontend_auth_contract.py tests/authz/test_route_roles.py passes; OpenAPI regenerated if response changes; make check where supported.</success_criteria>
<output_format>PR URL | stored-to-visible map | authz unchanged evidence | OpenAPI impact | tests</output_format>
```

### CBA-SCOPE-COMPOSITION

```xml
/goal Apply the Wave 0 policy to CBA routes, navigation, and claims while preserving consented outreach, discovery, and truthful rewards. Branch feat/cba-scope-composition from current origin/main; one PR to main.

<role>Lead implementation agent for CBA-SCOPE-COMPOSITION.</role>
<mission>Remove CBA reachability for out-of-scope/false surfaces without deleting historical implementation.</mission>
<context>Branch: feat/cba-scope-composition. PR base: main. Depends on CBA-SCOPE-POLICY. Wave 1 migration-free. routes.tsx and main.py are serial resources if touched.</context>
<read_first order="strict">
1. docs/product/cba-smart-match-customer-requirements.md §§17,20-22
2. docs/plans/open-questions/cba-phase-deferred.md
3. apps/web/legacy-frontend/src/app/routes.tsx
4. apps/web/legacy-frontend/src/app/pages/LandingPage.tsx
5. apps/web/legacy-frontend/src/app/pages/Outreach.tsx
6. apps/web/legacy-frontend/src/app/pages/coordinator/CoordinatorOutreach.tsx
7. apps/web/legacy-frontend/src/app/components/DiscoveryFeed.tsx
8. apps/web/legacy-frontend/src/app/pages/student/StudentRewards.tsx
9. docs/decisions/g3-crawler-decision.md
</read_first>
<non_negotiables>Gate external discovery, LinkedIn/scraping, cold unknown-contact outreach, chapter membership/dues, and CBA member_inquiry narrative. Preserve R/Y/G, /v1 consented outreach, fixture test seams, and server-backed rewards.</non_negotiables>
<deliverables>Policy-driven route/nav composition; truthful landing copy; member_inquiry CBA suppression; no legacy cold path on CBA navigation; narrow evidence-based handling of any rewards defect.</deliverables>
<test_first>Add tests/unit/test_cba_surface_composition.py (planned); extend tests/unit/test_frontend_no_fake_success_contract.py and tests/unit/test_fixture_ingest_wiring.py.</test_first>
<deferral_policy>Branding and rewards wording are P2. Live discovery/provider work remains prohibited.</deferral_policy>
<anti_patterns>No deletion cleanup. No blanket rewards disable. No reuse of fetchSpecialists or /api/data/*. No frontend-only security claim.</anti_patterns>
<success_criteria>python -m pytest tests/unit/test_cba_surface_composition.py tests/unit/test_frontend_no_fake_success_contract.py tests/unit/test_fixture_ingest_wiring.py passes; preserved capabilities have explicit regression assertions; make check where supported.</success_criteria>
<output_format>PR URL | gated surfaces | preserved surfaces | rewards evidence | tests | OQs</output_format>
```

## Wave 2

### CBA-TAXONOMY

```xml
/goal Add versioned domain taxonomies for the exact 20 NAICS sectors and 10 CBA role categories. Branch feat/cba-taxonomy from current origin/main; one PR to main.

<role>Lead implementation agent for CBA-TAXONOMY.</role>
<mission>Create canonical classification sources without conflating them with event tags.</mission>
<context>Branch: feat/cba-taxonomy. PR base: main. Depends on all Wave 1 tracks. Migration-free Wave 2 lane.</context>
<read_first order="strict">
1. docs/product/cba-smart-match-customer-requirements.md §§7-8
2. python/smartmatch_domain/smartmatch_domain/event_vocabulary.py
3. docs/architecture/decisions/ADR-0012-event-identity-and-tag-vocabulary.md
4. pyproject.toml import-linter contracts
</read_first>
<non_negotiables>Names/codes match customer exactly. Career roles are not event role/type tags. Domain module is the sole source; no frontend enum copy. Unknown values follow an explicit refuse/quarantine contract.</non_negotiables>
<deliverables>python/smartmatch_domain/smartmatch_domain/naics_sectors.py (planned); cba_role_categories.py (planned); exports; versions; validation/lookups; tests.</deliverables>
<test_first>Create tests/unit/test_naics_taxonomy.py and tests/unit/test_cba_role_categories.py (planned); extend tests/unit/test_event_vocabulary.py to prove separation.</test_first>
<deferral_policy>Aliases/inference learned from real data are later versioned decisions, not silently added here.</deferral_policy>
<anti_patterns>No migration/API/UI. No free-form taxonomy growth. No changing ADR-0012 terms.</anti_patterns>
<success_criteria>python -m pytest tests/unit/test_naics_taxonomy.py tests/unit/test_cba_role_categories.py tests/unit/test_event_vocabulary.py passes; exact counts are 20 and 10; make check where supported.</success_criteria>
<output_format>PR URL | taxonomy versions | exact counts | validation behavior | tests</output_format>
```

### CBA-DATA-SCHEMA

```xml
/goal Persist CBA speaker and Speaker Request classifications/location fields with enforced cardinality in one migration. Branch feat/cba-data-schema from current origin/main; one PR to main.

<role>Lead implementation agent for CBA-DATA-SCHEMA.</role>
<mission>Store speaker one-primary classifications and request multi-select classifications without weakening event identity or tenant boundaries.</mission>
<context>Branch: feat/cba-data-schema. PR base: main. Depends on CBA-TAXONOMY. Own exactly one head+1 Alembic revision chosen after fetching current main. Serial: migration queue and schema.py.</context>
<read_first order="strict">
1. docs/product/cba-smart-match-customer-requirements.md §§7-8,10-12,18-19
2. db/migrations/versions/0012_professional_unit_relationship.py
3. db/migrations/versions/0017_event_persistence.py
4. db/migrations/versions/0021_outreach_schema.py
5. python/smartmatch_persistence/smartmatch_persistence/schema.py
6. python/smartmatch_persistence/smartmatch_persistence/professionals.py
7. python/smartmatch_persistence/smartmatch_persistence/events.py
8. docs/architecture/decisions/ADR-0012-event-identity-and-tag-vocabulary.md
</read_first>
<non_negotiables>One migration. Speaker exactly zero/one primary Industry and Role as approved; request allows multiple. CBA roles are not event tags. Tenant-scoped FKs, downgrade, and schema.py parity required.</non_negotiables>
<deliverables>Classification/location/Topic/prior-talk/virtual storage; persistence models; constraints; migration; behavioral tests.</deliverables>
<test_first>Create tests/integration/test_cba_classification_schema.py (planned); extend tests/integration/test_event_schema_constraints.py and tests/integration/test_schema_matches_migration.py before migration code.</test_first>
<deferral_policy>Feedback schema and classifier inference are later tracks. Missing audit requirements become an OQ before DDL.</deferral_policy>
<anti_patterns>No hard-coded 0022 assumption. No API/UI/matcher. No arrays without constraints/tenant model review. No event-tag reuse.</anti_patterns>
<success_criteria>python -m pytest tests/integration/test_cba_classification_schema.py tests/integration/test_event_schema_constraints.py tests/integration/test_schema_matches_migration.py passes with PostgreSQL; alembic upgrade/downgrade works; make check where supported.</success_criteria>
<output_format>PR URL | previous/new migration head | schema cardinalities | tests | OQs</output_format>
```

### CBA-IMPORT-CONTRACT

```xml
/goal Extend the ratified import column contract for CBA contact data without adding persistence or inference. Branch feat/cba-import-contract from current origin/main; one PR to main.

<role>Lead implementation agent for CBA-IMPORT-CONTRACT.</role>
<mission>Represent every customer source/matching field once in columns.yaml and keep worker validation fail-closed.</mission>
<context>Branch: feat/cba-import-contract. PR base: main. Depends on CBA-TAXONOMY; coordinate with CBA-DATA-SCHEMA. No migration.</context>
<read_first order="strict">
1. docs/product/cba-smart-match-customer-requirements.md §§18-19
2. docs/pilot-data/columns.yaml
3. services/worker/smartmatch_worker/column_contract.py
4. services/worker/smartmatch_worker/handlers.py import sections
5. python/smartmatch_domain/smartmatch_domain/ingest.py
6. python/smartmatch_domain/smartmatch_domain/consent.py
</read_first>
<non_negotiables>YAML is column-name SSOT. Include customer fields and matching fields. Email collection never means consent. Missing contract refuses import. Keep privacy gate mechanism.</non_negotiables>
<deliverables>Required/optional CBA columns, aliases only through existing normalization, fixture updates, worker validation tests, documentation of field-to-schema mapping.</deliverables>
<test_first>Extend tests/unit/test_column_contract.py and tests/unit/test_import_column_contract_wiring.py; add tests/unit/test_cba_import_columns.py (planned).</test_first>
<deferral_policy>Unapproved sensitive fields use gate_pending/withhold rather than guessed collection policy.</deferral_policy>
<anti_patterns>No duplicated Python column list. No DDL/classifier/API. No consent inference.</anti_patterns>
<success_criteria>python -m pytest tests/unit/test_column_contract.py tests/unit/test_import_column_contract_wiring.py tests/unit/test_cba_import_columns.py passes; all §18 fields appear once; make check where supported.</success_criteria>
<output_format>PR URL | required columns | optional columns | withheld fields | tests | schema dependencies</output_format>
```

## Wave 3

### CBA-SCORING-ADR

```xml
/goal Resolve CBA neutral Topic, proximity bands, and virtual redistribution in an accepted scoring ADR before registry implementation. Branch docs/cba-scoring-decisions from current origin/main; one PR to main.

<role>Decision-record agent for CBA-SCORING-ADR.</role>
<mission>Produce an owner-approved rulebook that reconciles customer scoring with ADR-0011 and reproducible match runs.</mission>
<context>Branch: docs/cba-scoring-decisions. PR base: main. Depends on CBA-DATA-SCHEMA. Hard predecessor to all CBA matching factor/registry merges. Documentation/tests only.</context>
<read_first order="strict">
1. docs/product/cba-smart-match-customer-requirements.md §§5,9-11,26
2. docs/architecture/decisions/ADR-0011-accountable-numbers.md
3. docs/plans/open-questions/cba-phase-deferred.md
4. python/smartmatch_domain/smartmatch_domain/factor_registry.py
5. python/smartmatch_domain/smartmatch_domain/scoring.py
6. python/smartmatch_domain/smartmatch_domain/explanation.py
7. python/smartmatch_domain/smartmatch_domain/match_run.py
</read_first>
<non_negotiables>No implementation. Separate missing-Topic neutral policy from unknown evidence. Decide exact 25/75 boundaries/sub-scores and virtual formula. Define provenance, serialization, UI labels, pins, and golden cases. Named owner approval required.</non_negotiables>
<deliverables>Accepted new ADR or accepted ADR-0011 amendment; closed OQ-CBA-001/002/004 entries; decision-artifact tests.</deliverables>
<test_first>Add tests/unit/test_cba_scoring_decision_artifact.py (planned); extend tests/unit/test_gate_decision_artifacts.py to fail while status/fields/owner are missing.</test_first>
<deferral_policy>If the owner does not decide, keep OQs open and stop; do not mark the goal complete.</deferral_policy>
<anti_patterns>No “temporary” 0.5, proportional formula, or boundary assumption. No code/migration/golden implementation.</anti_patterns>
<success_criteria>python -m pytest tests/unit/test_cba_scoring_decision_artifact.py tests/unit/test_gate_decision_artifacts.py passes; ADR status Accepted and owner/date present; make check where supported.</success_criteria>
<output_format>PR URL | ADR path/status | decisions | closed OQs | still-open OQs | tests</output_format>
```

### CBA-MATCH-INDUSTRY-ROLE

```xml
/goal Implement isolated CBA Industry and Role factor functions without registry wiring. Branch feat/cba-match-industry-role from current origin/main; one PR to main.

<role>Matching factor agent for CBA-MATCH-INDUSTRY-ROLE.</role>
<mission>Score one-primary speaker classifications against multi-select Speaker Requests with accountable evidence.</mission>
<context>Branch: feat/cba-match-industry-role. PR base: main. Depends on CBA-TAXONOMY, CBA-DATA-SCHEMA, accepted CBA-SCORING-ADR. Parallel factor lane; factor_registry.py and approved goldens are forbidden.</context>
<read_first order="strict">
1. docs/product/cba-smart-match-customer-requirements.md §§5,7-8
2. python/smartmatch_domain/smartmatch_domain/naics_sectors.py and cba_role_categories.py (planned predecessor outputs; locate renamed equivalents if the merged taxonomy track chose different names)
3. python/smartmatch_domain/smartmatch_domain/factors/__init__.py
4. python/smartmatch_domain/smartmatch_domain/factors/topic_relevance.py
5. python/smartmatch_domain/smartmatch_domain/scoring.py
</read_first>
<non_negotiables>No weight literals. Preserve measured-zero versus unknown. Validate taxonomy/cardinality. Deterministic pure domain functions.</non_negotiables>
<deliverables>factors/industry_match.py and factors/role_match.py (planned); exports; unit tests; basis/provenance strings.</deliverables>
<test_first>Create tests/unit/test_industry_match.py and tests/unit/test_role_match.py (planned) before factor code.</test_first>
<deferral_policy>Ambiguous alias/fuzzy matching is deferred unless the taxonomy decision defines it.</deferral_policy>
<anti_patterns>No registry/scoring/worker/API/UI/golden edits. No event-tag role reuse. No unknown-to-zero coercion.</anti_patterns>
<success_criteria>python -m pytest tests/unit/test_industry_match.py tests/unit/test_role_match.py passes; exact/nonmatch/missing/invalid/empty cases explicit; make check where supported.</success_criteria>
<output_format>PR URL | factor keys | input/output rules | tests | deferred aliases</output_format>
```

### CBA-MATCH-PROXIMITY

```xml
/goal Implement the isolated CBA CPP-campus proximity factor under the accepted scoring ADR, without registry wiring. Branch feat/cba-match-proximity from current origin/main; one PR to main.

<role>Matching factor agent for CBA-MATCH-PROXIMITY.</role>
<mission>Produce accountable mile-band proximity outcomes for physical and virtual requests.</mission>
<context>Branch: feat/cba-match-proximity. PR base: main. Depends on CBA-DATA-SCHEMA and accepted CBA-SCORING-ADR. Parallel factor lane; registry/goldens forbidden.</context>
<read_first order="strict">
1. docs/product/cba-smart-match-customer-requirements.md §§10-11
2. Accepted CBA scoring ADR linked from docs/plans/open-questions/cba-phase-deferred.md (planned predecessor output; locate the approved path recorded there)
3. python/smartmatch_domain/smartmatch_domain/factors/travel_burden.py
4. docs/architecture/decisions/ADR-0011-accountable-numbers.md
5. python/smartmatch_domain/smartmatch_domain/match_run.py
</read_first>
<non_negotiables>Miles from versioned CPP origin. Exact bands/boundaries from ADR. Missing location is honest. Virtual behavior follows ADR. No network/live routing/geocoding. Version formula and provenance.</non_negotiables>
<deliverables>factors/proximity.py (planned) or versioned replacement; CPP origin/config seam; tests; coexistence/supersession note.</deliverables>
<test_first>Create tests/unit/test_cba_proximity.py (planned); extend tests/unit/test_travel_burden.py for old/new distinction.</test_first>
<deferral_policy>Live geocoding/routes remain gated; unresolved address returns approved unknown/refusal behavior.</deferral_policy>
<anti_patterns>No kilometers on CBA output. No invented boundary or proportional formula. No registry/scoring/golden/API edit.</anti_patterns>
<success_criteria>python -m pytest tests/unit/test_cba_proximity.py tests/unit/test_travel_burden.py passes, including exact 25/75 and virtual cases; make check where supported.</success_criteria>
<output_format>PR URL | formula version | campus origin source | boundary behavior | tests | deferred providers</output_format>
```

### CBA-MATCH-TOPIC

```xml
/goal Implement fixture-backed semantic CBA Topic scoring and one-sentence reasoning under the accepted ADR, without registry wiring. Branch feat/cba-match-topic from current origin/main; one PR to main.

<role>Matching factor/provider agent for CBA-MATCH-TOPIC.</role>
<mission>Compare request description with speaker Topic/profile/prior-talk evidence semantically and explain one sentence.</mission>
<context>Branch: feat/cba-match-topic. PR base: main. Depends on CBA-DATA-SCHEMA and accepted CBA-SCORING-ADR. Parallel factor lane; registry/goldens forbidden.</context>
<read_first order="strict">
1. docs/product/cba-smart-match-customer-requirements.md §9
2. Accepted CBA scoring ADR linked from docs/plans/open-questions/cba-phase-deferred.md (planned predecessor output; locate the approved path recorded there)
3. python/smartmatch_domain/smartmatch_domain/factors/topic_relevance.py
4. python/smartmatch_domain/smartmatch_domain/explanation.py
5. python/smartmatch_providers/smartmatch_providers/registry.py
6. services/api/smartmatch_api/config.py
7. tests/unit/test_provider_isolation.py
</read_first>
<non_negotiables>Deterministic fixture provider. Live provider unreachable by default/classroom. Score plus exactly one-sentence rationale. Thin-data behavior/provenance follows ADR. No LLM-generated assumptions stored as fact.</non_negotiables>
<deliverables>Semantic Topic protocol/factor; fixture provider; one-sentence explanation contract; provider isolation and unit tests.</deliverables>
<test_first>Create tests/unit/test_cba_semantic_topic.py and tests/unit/test_cba_topic_explanation.py (planned); extend tests/unit/test_provider_isolation.py.</test_first>
<deferral_policy>Live model credentials/selection remain OQ and fail closed.</deferral_policy>
<anti_patterns>No lexical-overlap relabel as semantic. No live HTTP in tests. No registry/scoring/golden/API edit. No unlabeled neutral 0.5.</anti_patterns>
<success_criteria>python -m pytest tests/unit/test_cba_semantic_topic.py tests/unit/test_cba_topic_explanation.py tests/unit/test_provider_isolation.py passes; make check where supported.</success_criteria>
<output_format>PR URL | provider/factor versions | thin-data behavior | rationale contract | tests | live deferral</output_format>
```

### CBA-MATCH-REGISTRY

```xml
/goal Integrate the approved four-factor CBA matcher into a new versioned registry and golden set. Branch feat/cba-match-registry-v2 from current origin/main; one PR to main.

<role>Matching integration owner for CBA-MATCH-REGISTRY.</role>
<mission>Supersede the approved 70/30 runtime with Industry 30, Role 25, Topic 15, Proximity 30 while preserving reproducibility.</mission>
<context>Branch: feat/cba-match-registry-v2. PR base: main. Depends on accepted scoring ADR and all three factor PRs. Exclusive Wave 3 owner of factor_registry.py and tests/golden/matching/cba (planned). OpenAPI serial if changed.</context>
<read_first order="strict">
1. docs/product/cba-smart-match-customer-requirements.md §§5-11
2. Accepted CBA scoring ADR linked from docs/plans/open-questions/cba-phase-deferred.md (planned predecessor output; locate the approved path recorded there)
3. python/smartmatch_domain/smartmatch_domain/factor_registry.py
4. python/smartmatch_domain/smartmatch_domain/scoring.py
5. new Industry/Role/Topic/Proximity factors
6. python/smartmatch_domain/smartmatch_domain/explanation.py
7. python/smartmatch_domain/smartmatch_domain/match_run.py
8. services/worker/smartmatch_worker/handlers.py match-run section
9. tests/unit/test_matching_approved_golden.py
10. tests/contract/test_match_runs_api.py
</read_first>
<non_negotiables>One registry source for defaults. Four implemented keys exactly. Accepted physical/virtual policy only. Old runs remain distinguishable. 2–3 shortlist. No prominent percentage. All scores/pins/provenance versioned.</non_negotiables>
<deliverables>New registry version/status; scoring/worker/pin/explanation integration; approved CBA golden set; API contract update only if necessary; supersession docs.</deliverables>
<test_first>Extend tests/unit/test_factor_registry.py and tests/unit/test_matching_approved_golden.py; add CBA fixtures under tests/golden/matching/cba (planned); extend tests/integration/test_match_run_snapshot.py and tests/contract/test_match_runs_api.py.</test_first>
<deferral_policy>Do not merge if scoring ADR or named golden approval is absent. Live semantic provider remains gated.</deferral_policy>
<anti_patterns>No legacy Nebiux port. No scattered weights. No demo heuristic substitution. No unknown-to-zero. No hand-edited OpenAPI.</anti_patterns>
<success_criteria>python -m pytest tests/unit/test_factor_registry.py tests/unit/test_matching_approved_golden.py tests/integration/test_match_run_snapshot.py tests/contract/test_match_runs_api.py passes; approved key set/weights/pins/goldens proven; make check where supported.</success_criteria>
<output_format>PR URL | registry version/status/approver | factor weights | golden cases | OpenAPI impact | tests</output_format>
```

### CBA-MATCH-WEIGHTS

```xml
/goal Add unit-scoped Speaker Connector matching-weight settings and snapshot applied values. Branch feat/cba-match-weight-settings from current origin/main; one PR to main.

<role>Settings/API agent for CBA-MATCH-WEIGHTS.</role>
<mission>Let authorized Connectors adjust centralized weights without changing immutable historical match runs.</mission>
<context>Branch: feat/cba-match-weight-settings. PR base: main. Depends on CBA-MATCH-REGISTRY. Serial resources: next migration if needed, OpenAPI, policy matrix.</context>
<read_first order="strict">
1. docs/product/cba-smart-match-customer-requirements.md §§5,13,25 P1
2. python/smartmatch_domain/smartmatch_domain/factor_registry.py normalize_weights
3. python/smartmatch_domain/smartmatch_domain/match_run.py
4. python/smartmatch_persistence/smartmatch_persistence/match_runs.py
5. services/api/smartmatch_api/routers/match_runs.py
6. tests/authz/test_policy_matrix.py
</read_first>
<non_negotiables>Registry defaults remain sole default literals. Tenant/unit scoped. Audit/version settings. Snapshot applied weights per run. Invalid/negative/zero-total values refuse. UI labels grant no power.</non_negotiables>
<deliverables>Domain/settings persistence; one migration only if needed; Connector GET/PATCH API; authz/OpenAPI; minimal approved UI or explicit deferral.</deliverables>
<test_first>Create tests/unit/test_cba_weight_settings.py, tests/integration/test_cba_weight_settings.py, and tests/contract/test_matching_weights_api.py (planned); add policy-matrix rows first.</test_first>
<deferral_policy>Complex admin UI and autonomous feedback tuning are deferred.</deferral_policy>
<anti_patterns>No duplicated defaults. No update of old match runs. No client-only setting. No hand-edited OpenAPI.</anti_patterns>
<success_criteria>python -m pytest tests/unit/test_cba_weight_settings.py tests/integration/test_cba_weight_settings.py tests/contract/test_matching_weights_api.py tests/authz/test_policy_matrix.py passes; make openapi-check/check where supported.</success_criteria>
<output_format>PR URL | migration head | operations | authz roles | snapshot proof | tests</output_format>
```

## Wave 4

### CBA-EVENT-REQUEST

```xml
/goal Ship an Event Host-authorized durable Speaker Request create path using the CBA schema. Branch feat/cba-event-speaker-request from current origin/main; one PR to main.

<role>Workflow agent for CBA-EVENT-REQUEST.</role>
<mission>Allow an Event Host to manually create a physical or virtual request that can feed matching.</mission>
<context>Branch: feat/cba-event-speaker-request. PR base: main. Depends on taxonomy, data schema, scope policy, and role presentation. OpenAPI/authz serial; migration only if Wave 2 is insufficient.</context>
<read_first order="strict">
1. docs/product/cba-smart-match-customer-requirements.md §§12,22-23
2. docs/architecture/decisions/ADR-0010-event-temporal-model.md
3. docs/architecture/decisions/ADR-0012-event-identity-and-tag-vocabulary.md
4. services/api/smartmatch_api/routers/events.py
5. python/smartmatch_persistence/smartmatch_persistence/events.py
6. services/api/smartmatch_api/commands.py
7. apps/web/legacy-frontend/src/app/pages/coordinator/CoordinatorEvents.tsx
8. apps/web/legacy-frontend/src/app/pages/Opportunities.tsx
</read_first>
<non_negotiables>Host power is server-side. Multi-select Industry/Role. Manual origin/provenance. Idempotency. No external URL/fetch/crawl. No fake UI success. Preserve deterministic identity/time precision.</non_negotiables>
<deliverables>Domain/persistence create; API command or justified transactional create; Connector read; Host UI; regenerated OpenAPI; policy rows; tests.</deliverables>
<test_first>Create tests/contract/test_speaker_requests_api.py and tests/integration/test_speaker_request_persistence.py (planned); add tests/authz/test_policy_matrix.py rows before route.</test_first>
<deferral_policy>Live external calendars/discovery and unresolved fields fail closed or become review items.</deferral_policy>
<anti_patterns>No fetchSpecialists, /api/data/*, local-only event, label-based authz, or provider inline request path.</anti_patterns>
<success_criteria>python -m pytest tests/contract/test_speaker_requests_api.py tests/integration/test_speaker_request_persistence.py tests/authz/test_policy_matrix.py passes; OpenAPI regenerated; make check where supported.</success_criteria>
<output_format>PR URL | operations | authz | persistence/idempotency | tests | OQs</output_format>
```

### CBA-CONTACT-MANAGEMENT

```xml
/goal Ship Speaker Connector manual contact create/read/update and primary classification correction. Branch feat/cba-contact-management from current origin/main; one PR to main.

<role>Workflow agent for CBA-CONTACT-MANAGEMENT.</role>
<mission>Let Connectors maintain in-system contacts and correct Industry/Role with provenance without granting consent.</mission>
<context>Branch: feat/cba-contact-management. PR base: main. Depends on CBA-DATA-SCHEMA and CBA-TAXONOMY. OpenAPI/authz serial; migration only if an audited field is missing.</context>
<read_first order="strict">
1. docs/product/cba-smart-match-customer-requirements.md §§13,18-19
2. python/smartmatch_persistence/smartmatch_persistence/professionals.py
3. services/api/smartmatch_api/routers/imports.py
4. python/smartmatch_domain/smartmatch_domain/consent.py
5. db/migrations/versions/0021_outreach_schema.py
6. python/smartmatch_persistence/smartmatch_persistence/outreach.py
7. tests/authz/test_policy_matrix.py
</read_first>
<non_negotiables>One-primary classifications. Tenant-scoped/audited corrections. New contact email is not sendable by creation. Connector label is not permission. Manual records only.</non_negotiables>
<deliverables>Contact domain/persistence/API; classification correction audit/provenance; Connector UI; generated OpenAPI/authz tests.</deliverables>
<test_first>Create tests/contract/test_cba_contacts_api.py and tests/integration/test_cba_contact_corrections.py (planned); add policy rows first.</test_first>
<deferral_policy>Inference belongs to CBA-IMPORT-CLASSIFY; self-service opt-in belongs to contact lifecycle OQ.</deferral_policy>
<anti_patterns>No cold outreach, scrape, consent auto-activation, free-form taxonomy, fake UI, or hand-edited OpenAPI.</anti_patterns>
<success_criteria>python -m pytest tests/contract/test_cba_contacts_api.py tests/integration/test_cba_contact_corrections.py tests/authz/test_policy_matrix.py passes; make openapi-check/check where supported.</success_criteria>
<output_format>PR URL | operations | audit/provenance | consent state | tests | migration head if any</output_format>
```

### CBA-IMPORT-CLASSIFY

```xml
/goal Add deterministic fixture classification proposals to the reviewed CBA contact import flow. Branch feat/cba-import-classification from current origin/main; one PR to main.

<role>Worker/classification agent for CBA-IMPORT-CLASSIFY.</role>
<mission>Infer proposed Industry/Role from company/title, require human review, and persist accountable accepted classifications.</mission>
<context>Branch: feat/cba-import-classification. PR base: main. Depends on import contract, data schema, taxonomy, and contact correction shape. Worker lane; no live provider.</context>
<read_first order="strict">
1. docs/product/cba-smart-match-customer-requirements.md §19
2. services/api/smartmatch_api/routers/imports.py
3. services/worker/smartmatch_worker/handlers.py import sections
4. services/worker/smartmatch_worker/column_contract.py
5. services/api/smartmatch_api/routers/review.py
6. services/api/smartmatch_api/pipeline_provisioning.py
7. tests/integration/test_import_rows.py
8. tests/unit/test_provider_isolation.py
</read_first>
<non_negotiables>Proposal is inferred provenance, not fact. Ambiguous/unknown is reviewable. Connector correction wins. No public network/live model. Contact email does not imply consent.</non_negotiables>
<deliverables>Classifier protocol; deterministic fixture classifier; import/review/persistence wiring; match-eligibility gate after required review; tests.</deliverables>
<test_first>Create tests/unit/test_cba_contact_classifier.py and tests/integration/test_cba_import_classification.py (planned); extend tests/integration/test_import_rows.py.</test_first>
<deferral_policy>Live AI classifier/provider stays fail-closed and documented as OQ.</deferral_policy>
<anti_patterns>No guessed confident value, internet lookup, direct bypass of review, legacy /api/data/*, or consent mutation.</anti_patterns>
<success_criteria>python -m pytest tests/unit/test_cba_contact_classifier.py tests/integration/test_cba_import_classification.py tests/integration/test_import_rows.py passes; make check where supported.</success_criteria>
<output_format>PR URL | classifier version | review behavior | unknown behavior | tests | live deferral</output_format>
```

### CBA-STUDENT-FEEDBACK

```xml
/goal Implement minimal student-to-speaker feedback only after OQ-CBA-003 is explicitly approved. Branch feat/cba-student-speaker-feedback from current origin/main; one PR to main.

<role>Engagement workflow agent for CBA-STUDENT-FEEDBACK.</role>
<mission>Let eligible students submit approved speaker feedback and Connectors read it without over-design.</mission>
<context>Branch: feat/cba-student-speaker-feedback. PR base: main. Depends on OQ-CBA-003, data schema, event/student identities. Serial: migration, OpenAPI, authz. If OQ is open, write/seek decision and stop.</context>
<read_first order="strict">
1. docs/product/cba-smart-match-customer-requirements.md §§15-16,26
2. docs/plans/open-questions/cba-phase-deferred.md OQ-CBA-003
3. python/smartmatch_domain/smartmatch_domain/feedback.py
4. python/smartmatch_persistence/smartmatch_persistence/schema.py attendance/event tables
5. docs/architecture/decisions/ADR-0011-accountable-numbers.md
6. tests/authz/test_policy_matrix.py
</read_first>
<non_negotiables>Do not reuse coordinator match feedback. Implement only approved scale/fields/edit/anonymity/retention/aggregation. Tie submission to eligible student/event/speaker evidence. Empty aggregate is unknown.</non_negotiables>
<deliverables>Approved decision reference; one migration; domain/persistence/API; student form; Connector read; OpenAPI/authz/tests.</deliverables>
<test_first>Create tests/unit/test_student_speaker_feedback.py, tests/integration/test_student_speaker_feedback.py, and tests/contract/test_student_feedback_api.py (planned) before production code.</test_first>
<deferral_policy>If OQ-CBA-003 is unresolved, do not implement or mark complete. Record exact missing decisions.</deferral_policy>
<anti_patterns>No invented 1–5 default, local-state success, public aggregate with no privacy decision, or zero for empty feedback.</anti_patterns>
<success_criteria>python -m pytest tests/unit/test_student_speaker_feedback.py tests/integration/test_student_speaker_feedback.py tests/contract/test_student_feedback_api.py tests/authz/test_policy_matrix.py passes; OpenAPI regenerated; make check where supported.</success_criteria>
<output_format>PR URL | OQ/decision | migration head | operations/authz | tests | privacy behavior</output_format>
```

## Wave 5

### CBA-STUDENT-EVENTS

```xml
/goal Complete student event browse, registration, ICS, and bottom-of-page month calendar using existing event architecture. Branch feat/cba-student-events-calendar from current origin/main; one PR to main.

<role>Student workflow agent for CBA-STUDENT-EVENTS.</role>
<mission>Preserve browse/agenda, add real registration/calendar actions, and render the month calendar last on Events.</mission>
<context>Branch: feat/cba-student-events-calendar. PR base: main. Depends on CBA-EVENT-REQUEST; coordinate feedback action. Reuses G8. Serial: OpenAPI/authz/client.</context>
<read_first order="strict">
1. docs/product/cba-smart-match-customer-requirements.md §15
2. apps/web/legacy-frontend/src/app/pages/student/StudentEvents.tsx
3. apps/web/legacy-frontend/src/app/pages/Calendar.tsx
4. python/smartmatch_domain/smartmatch_domain/calendar_invite.py
5. tests/unit/test_calendar_invite_wiring.py
6. tests/golden/test_calendar_invite_golden.py
7. services/api/smartmatch_api/routers/events.py
8. docs/plans/frontend-broken-buttons.md B06-B09
</read_first>
<non_negotiables>Month calendar is below browse/agenda, not a replacement. Registration idempotent. ICS only for resolved times. No toast-only success. Student data tenant/self scoped. No Google Calendar API.</non_negotiables>
<deliverables>Student event read; registration command/read; ICS operation; Events UI ordered browse/agenda then month calendar; OpenAPI/authz/tests.</deliverables>
<test_first>Create tests/contract/test_student_events_api.py, tests/integration/test_event_registration.py, and tests/unit/test_student_events_layout_contract.py (planned); extend tests/unit/test_calendar_invite_wiring.py.</test_first>
<deferral_policy>Direct calendar provider/OAuth and QR check-in remain deferred.</deferral_policy>
<anti_patterns>No mock events, local registration Set, fake calendar toast, unresolved datetime fabrication, or calendar-first page.</anti_patterns>
<success_criteria>python -m pytest tests/contract/test_student_events_api.py tests/integration/test_event_registration.py tests/unit/test_student_events_layout_contract.py tests/unit/test_calendar_invite_wiring.py passes; OpenAPI regenerated; make check where supported.</success_criteria>
<output_format>PR URL | operations | registration/ICS behavior | calendar order proof | tests | deferrals</output_format>
```

### CBA-CONTACT-LIFECYCLE

```xml
/goal Expose the existing consent/contact-channel lifecycle for CBA Connector-managed contacts. Branch feat/cba-contact-lifecycle from current origin/main; one PR to main.

<role>Consent API agent for CBA-CONTACT-LIFECYCLE.</role>
<mission>Make approved-source contacts transitionable and auditable without an invite-to-consent loophole.</mission>
<context>Branch: feat/cba-contact-lifecycle. PR base: main. Depends on CBA-CONTACT-MANAGEMENT. Reuses G9. Serial: OpenAPI/authz; migration only if current 0021 schema proves insufficient.</context>
<read_first order="strict">
1. python/smartmatch_domain/smartmatch_domain/consent.py
2. db/migrations/versions/0021_outreach_schema.py
3. python/smartmatch_persistence/smartmatch_persistence/outreach.py
4. services/api/smartmatch_api/routers/outreach.py
5. docs/plans/open-questions/r4-outreach-deferred.md
6. tests/unit/test_consent.py
</read_first>
<non_negotiables>No send without ACTIVE_CANDIDATE plus approved source. Suppression wins. Tenant scoped. `.invalid` fixtures. Contact creation alone grants no consent.</non_negotiables>
<deliverables>Unit-scoped contact-channel create/transition/read; audit; OpenAPI/authz; integration/unit tests.</deliverables>
<test_first>Extend tests/unit/test_consent.py; create tests/contract/test_contact_lifecycle_api.py and tests/integration/test_contact_lifecycle.py (planned).</test_first>
<deferral_policy>Production roster import and self-service opt-in remain OQs.</deferral_policy>
<anti_patterns>No cold outreach, invite-to-consent, scraped contact activation, client-only state, or template changes.</anti_patterns>
<success_criteria>python -m pytest tests/unit/test_consent.py tests/contract/test_contact_lifecycle_api.py tests/integration/test_contact_lifecycle.py tests/authz/test_policy_matrix.py passes; OpenAPI regenerated; make check where supported.</success_criteria>
<output_format>PR URL | operations | transition table | audit/suppression proof | tests | OQs</output_format>
```

### CBA-INVITATIONS

```xml
/goal Extend consented /v1 outreach into CBA shortlist batch invitations, Speaker responses, and response tracking. Branch feat/cba-speaker-invitations from current origin/main; one PR to main.

<role>Invitation workflow agent for CBA-INVITATIONS.</role>
<mission>Batch-invite stored eligible candidates and distinguish delivery from Speaker accept/decline.</mission>
<context>Branch: feat/cba-speaker-invitations. PR base: main. Depends on match registry/weights, Event Request, Contact Lifecycle. Reuses G7. Serial: migration if needed, OpenAPI/authz/client.</context>
<read_first order="strict">
1. docs/product/cba-smart-match-customer-requirements.md §§6,13-14
2. services/api/smartmatch_api/routers/outreach.py
3. services/worker/smartmatch_worker/outreach.py
4. python/smartmatch_domain/smartmatch_domain/consent.py
5. python/smartmatch_persistence/smartmatch_persistence/outreach.py
6. services/api/smartmatch_api/routers/match_runs.py
7. apps/web/legacy-frontend/src/app/pages/coordinator/CoordinatorOutreach.tsx
8. tests/integration/test_outreach_handler.py
</read_first>
<non_negotiables>Use consented /v1 path only. Recheck consent at delivery. Batch idempotent with explicit partial outcomes. Provider accepted/delivered is not Speaker accepted. Fixture provider default.</non_negotiables>
<deliverables>Invitation/batch domain and persistence; Connector send/track; Speaker accept/decline; generated OpenAPI/authz/UI/tests.</deliverables>
<test_first>Create tests/contract/test_cba_invitations_api.py and tests/integration/test_cba_invitation_batch.py (planned); extend tests/integration/test_outreach_handler.py.</test_first>
<deferral_policy>Live email and external contact acquisition remain gated.</deferral_policy>
<anti_patterns>No Outreach.tsx cold path, AgenticOutreachPanel, fetchSpecialists, /api/data/*, fake thread, or member_inquiry write.</anti_patterns>
<success_criteria>python -m pytest tests/contract/test_cba_invitations_api.py tests/integration/test_cba_invitation_batch.py tests/integration/test_outreach_handler.py tests/authz/test_policy_matrix.py passes; OpenAPI regenerated; make check where supported.</success_criteria>
<output_format>PR URL | migration head if any | operations | batch/response semantics | tests | live deferral</output_format>
```

### CBA-HANDOFF-PIPELINE

```xml
/goal Connect accepted invitations to evidence-backed confirmed/attended stages and Event Host handoff, excluding member_inquiry. Branch feat/cba-confirmed-speaker-handoff from current origin/main; one PR to main.

<role>Pipeline workflow agent for CBA-HANDOFF-PIPELINE.</role>
<mission>Return the confirmed speaker to the Host and preserve accountable funnel progression.</mission>
<context>Branch: feat/cba-confirmed-speaker-handoff. PR base: main. Depends on CBA-INVITATIONS and CBA-STUDENT-EVENTS. Reuses G1 partial. Serial: metric register/OpenAPI if changed.</context>
<read_first order="strict">
1. docs/product/cba-smart-match-customer-requirements.md §§6,23
2. python/smartmatch_domain/smartmatch_domain/pipeline.py
3. python/smartmatch_persistence/smartmatch_persistence/pipeline.py
4. python/smartmatch_domain/smartmatch_domain/metrics.py
5. services/api/smartmatch_api/routers/metrics.py
6. tests/integration/test_pipeline_record_writers.py
7. tests/contract/test_metrics.py
</read_first>
<non_negotiables>Accepted invitation supplies confirmed evidence; attendance supplies attended evidence. Idempotent ordered stages. Aggregate equals drill-down. Preserve schema/history but write/display no CBA member_inquiry.</non_negotiables>
<deliverables>Stage caller wiring; Host confirmed-speaker read/UI; CBA metric labels/filter; provenance and tests.</deliverables>
<test_first>Create tests/integration/test_cba_confirmed_handoff.py (planned); extend tests/integration/test_pipeline_record_writers.py and tests/contract/test_metrics.py.</test_first>
<deferral_policy>A future post-event CBA outcome requires an approved decision before replacing member_inquiry.</deferral_policy>
<anti_patterns>No stage without evidence, browser stage toggle, duplicate metric query, member_inquiry writer/narrative, or fake handoff.</anti_patterns>
<success_criteria>python -m pytest tests/integration/test_cba_confirmed_handoff.py tests/integration/test_pipeline_record_writers.py tests/contract/test_metrics.py passes; drill-down equality proven; make check where supported.</success_criteria>
<output_format>PR URL | stage evidence map | Host operation/UI | member_inquiry exclusion | tests | OQs</output_format>
```

### CBA-REWARDS-REFINEMENT

```xml
/goal Preserve working rewards/points and make only approved CBA P2 wording or narrow truthfulness refinements. Branch feat/cba-rewards-refinement from current origin/main; one PR to main.

<role>P2 refinement agent for CBA-REWARDS-REFINEMENT.</role>
<mission>Remove chapter-specific reward framing without disabling the server-backed capability or inventing a new economy.</mission>
<context>Branch: feat/cba-rewards-refinement. PR base: main. Depends on CBA-SCOPE-COMPOSITION and should wait behind P0/P1 demo-critical work. No migration/API change without explicit approved need.</context>
<read_first order="strict">
1. docs/product/cba-smart-match-customer-requirements.md §§4,21,25 P2
2. services/api/smartmatch_api/routers/rewards.py
3. python/smartmatch_domain/smartmatch_domain/rewards.py
4. python/smartmatch_persistence/smartmatch_persistence/rewards.py
5. apps/web/legacy-frontend/src/app/pages/student/StudentRewards.tsx
6. docs/decisions/d6-rewards-budget-decision-record.md
7. apps/web/DESIGN.md
8. tests/integration/test_rewards_api.py
</read_first>
<non_negotiables>Rewards/points remain. Preserve server catalog/balance/redemption. No client point math. Gate only a named false/unfunded/incomplete control with evidence. Branding cannot delay function.</non_negotiables>
<deliverables>CBA wording; optional approved career-readiness copy; narrow truthfulness fixes; regression tests proving capability remains.</deliverables>
<test_first>Create tests/unit/test_cba_rewards_copy.py (planned); extend tests/integration/test_rewards_api.py and tests/unit/test_rewards_domain.py before copy/behavior edits.</test_first>
<deferral_policy>New economy, budget calibration, procurement, and CPP green/gold redesign are separate P2/OQ work.</deferral_policy>
<anti_patterns>No blanket route/page disable. No new point values, unreachable rewards, frontend ledger, or branding rewrite.</anti_patterns>
<success_criteria>python -m pytest tests/unit/test_cba_rewards_copy.py tests/integration/test_rewards_api.py tests/unit/test_rewards_domain.py passes; existing capability remains reachable under CBA policy; make check where supported.</success_criteria>
<output_format>PR URL | preserved reward paths | wording/refinements | gated defects with evidence | tests | deferrals</output_format>
```

## Catalog completeness

This catalog contains one card for each of the 22 tracks in the wave plan:

- Wave 0: 1
- Wave 1: 3
- Wave 2: 3
- Wave 3: 6
- Wave 4: 4
- Wave 5: 5

