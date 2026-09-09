# CBA cloud agent dispatch queue

**Updated:** 2026-09-05  
**Base branch:** `origin/main` (fetch before every dispatch)  
**Orchestrator doc:** [`cba-fable-wave-orchestrator.md`](cba-fable-wave-orchestrator.md)  
**Goal cards source:** [`../cba-goal-catalog.md`](../cba-goal-catalog.md)

## Status

| Track | Status | Action |
|-------|--------|--------|
| CBA-SCOPE-POLICY … CBA-SCOPE-COMPOSITION | Merged (#47–#50) | Do not re-dispatch |
| CBA-TAXONOMY | Merged (#51, `c3ba9a5`) | Do not re-dispatch |
| **CBA-DATA-SCHEMA** | **PR #52 open**, 10/10 CI green | Review + merge, then dispatch SCORING-ADR |
| CBA-SCORING-ADR | Queued | Dispatch **solo** after DATA-SCHEMA merges |
| CBA-MATCH-INDUSTRY-ROLE / PROXIMITY / TOPIC | Queued | Dispatch **3 in parallel** after SCORING-ADR merges |

Standing env for every cloud agent: `ALLOW_LIVE_PROVIDERS=false`, `ALLOW_LIVE_DATA=false`, `ALLOW_CLOUD_DEPLOY=false`.

---

## Shared preamble (prepend to every dispatch below)

```text
You are an implementation agent for ONE CBA track only.

Repository: IA-Smart-Match-Revamped
Remote: fetch origin/main and branch from current origin/main only
PR target: main
Standing env: ALLOW_LIVE_PROVIDERS=false, ALLOW_LIVE_DATA=false, ALLOW_CLOUD_DEPLOY=false

Workflow (mandatory):
1. git fetch origin && git switch -c <branch-from-card> origin/main
2. Read the card <read_first> files in order before coding
3. Write failing tests first (<test_first> section)
4. Implement within the card fence only
5. Run targeted pytest from <success_criteria>; run make check where make exists
6. git push -u origin HEAD && gh pr create --base main with Summary, Test plan, OQ table
7. Return: PR URL | migration head | new OpenAPI ops | tests run | concerns | DONE | DONE_WITH_CONCERNS | BLOCKED

Do not merge. Do not force-push. Do not skip hooks. Do not declare production readiness.

Execute the /goal card below exactly:
```

---

## 1. CBA-DATA-SCHEMA — RETURNED 2026-09-05 (solo) → PR #52

Gate cleared: `feat/cba-taxonomy` merged as #51 (`c3ba9a5`), CI green.

**Result:** [PR #52](https://github.com/IA-Smart-Match/IA-Smart-Match-Revamped/pull/52),
`feat/cba-data-schema`, MERGEABLE, 10/10 checks SUCCESS. One migration,
`0023_contact_transition` → `0024_cba_classification`, downgrade present.
Fence held: no `factor_registry.py`, `scoring.py`, `tests/golden/**`, API, or UI edits.
Opened OQ-CBA-008 (classification provenance), OQ-CBA-009 (`professional_id` FK
retrofit on 0012/0021), OQ-CBA-010 (quarantined classifications).

**Reviewer must decide two things the agent chose on its own:**
1. `speaker_profile.professional_id` gets a tenant-scoped FK to `user_account`,
   which the older `professional_unit_relationship` and `contact_channel` columns
   still lack — a deliberate inconsistency, tracked as OQ-CBA-009.
2. Taxonomy codes are transcribed into CHECK constraints, which
   `docs/product/cba-taxonomies.md` warns against; drift is caught by tests
   parametrized over the domain modules rather than by the database.

**Verified against `origin/main` @ `c3ba9a5` before dispatch:**

- Migration chain is linear with a single head, `0023_contact_transition`
  (file `db/migrations/versions/0023_contact_channel_transition.py`).
  The new revision is `0024_*`, **not** `0022_*` — the card's original
  read-first list predated `0022_event_end_instant` and `0023`.
- Taxonomy modules released by #51:
  `smartmatch_domain/naics_sectors.py`, `smartmatch_domain/cba_role_categories.py`,
  `smartmatch_domain/role_presentation.py`.

The card below is the dispatched text, amended with those two facts.

```text
/goal Persist CBA speaker and Speaker Request classifications/location fields with enforced cardinality in one migration. Branch feat/cba-data-schema from current origin/main; one PR to main.

<role>Lead implementation agent for CBA-DATA-SCHEMA.</role>
<mission>Store speaker one-primary classifications and request multi-select classifications without weakening event identity or tenant boundaries.</mission>
<context>Branch: feat/cba-data-schema. PR base: main. Depends on CBA-TAXONOMY (merged as PR #51, commit c3ba9a5 — taxonomy modules are smartmatch_domain/naics_sectors.py and smartmatch_domain/cba_role_categories.py). Own exactly one head+1 Alembic revision. As of origin/main c3ba9a5 the single migration head is 0023_contact_transition (file db/migrations/versions/0023_contact_channel_transition.py); re-verify with `alembic heads` after fetching and chain your new revision from the actual head. Serial: migration queue and schema.py.</context>
<read_first order="strict">
1. docs/product/cba-smart-match-customer-requirements.md §§7-8,10-12,18-19
2. docs/product/cba-taxonomies.md
3. python/smartmatch_domain/smartmatch_domain/naics_sectors.py
4. python/smartmatch_domain/smartmatch_domain/cba_role_categories.py
5. db/migrations/versions/0012_professional_unit_relationship.py
6. db/migrations/versions/0017_event_persistence.py
7. db/migrations/versions/0021_outreach_schema.py
8. db/migrations/versions/0023_contact_channel_transition.py
9. python/smartmatch_persistence/smartmatch_persistence/schema.py
10. python/smartmatch_persistence/smartmatch_persistence/professionals.py
11. python/smartmatch_persistence/smartmatch_persistence/events.py
12. docs/architecture/decisions/ADR-0012-event-identity-and-tag-vocabulary.md
</read_first>
<non_negotiables>One migration, chained from the verified current head. Speaker has exactly zero-or-one primary Industry and zero-or-one primary Role as approved; Speaker Request allows multiple of each. Classification values must be constrained to the merged taxonomy modules, not free text. CBA roles are not event tags. Tenant-scoped FKs, a working downgrade, and schema.py parity are required.</non_negotiables>
<deliverables>Classification/location/Topic/prior-talk/virtual storage; persistence models; constraints; migration; behavioral tests.</deliverables>
<test_first>Create tests/integration/test_cba_classification_schema.py; extend tests/integration/test_event_schema_constraints.py and tests/integration/test_schema_matches_migration.py before writing migration code.</test_first>
<deferral_policy>Feedback schema and classifier inference are later tracks. Missing audit requirements become an OQ before DDL.</deferral_policy>
<anti_patterns>No hard-coded 0022 assumption — the head has advanced past it. No API/UI/matcher changes. No arrays without constraints and tenant model review. No event-tag reuse. Do not edit factor_registry.py, scoring.py, or tests/golden/**.</anti_patterns>
<success_criteria>python -m pytest tests/integration/test_cba_classification_schema.py tests/integration/test_event_schema_constraints.py tests/integration/test_schema_matches_migration.py passes against PostgreSQL; alembic upgrade head and downgrade -1 both work; make check where supported.</success_criteria>
<output_format>PR URL | previous/new migration head | schema cardinalities | tests | OQs</output_format>
```

---

## 2. CBA-SCORING-ADR — dispatch SOLO after CBA-DATA-SCHEMA merges

**Hard gate** before any Wave 3 factor or registry work. Documentation/tests only — no runtime scoring code.

```text
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

---

## 3–5. Three parallel cloud agents — after CBA-SCORING-ADR merges

Launch **all three at once** on separate cloud agents. Each must **not** edit `factor_registry.py`, `scoring.py`, or `tests/golden/matching/cba/**`.

### Agent A — CBA-MATCH-INDUSTRY-ROLE

```text
/goal Implement isolated CBA Industry and Role factor functions without registry wiring. Branch feat/cba-match-industry-role from current origin/main; one PR to main.

<role>Matching factor agent for CBA-MATCH-INDUSTRY-ROLE.</role>
<mission>Score one-primary speaker classifications against multi-select Speaker Requests with accountable evidence.</mission>
<context>Branch: feat/cba-match-industry-role. PR base: main. Depends on CBA-TAXONOMY, CBA-DATA-SCHEMA, accepted CBA-SCORING-ADR. Parallel factor lane; factor_registry.py and approved goldens are forbidden.</context>
<read_first order="strict">
1. docs/product/cba-smart-match-customer-requirements.md §§5,7-8
2. python/smartmatch_domain/smartmatch_domain/naics_sectors.py and cba_role_categories.py (locate merged taxonomy module names on main)
3. python/smartmatch_domain/smartmatch_domain/factors/__init__.py
4. python/smartmatch_domain/smartmatch_domain/factors/topic_relevance.py
5. python/smartmatch_domain/smartmatch_domain/scoring.py
</read_first>
<non_negotiables>No weight literals. Preserve measured-zero versus unknown. Validate taxonomy/cardinality. Deterministic pure domain functions.</non_negotiables>
<deliverables>factors/industry_match.py and factors/role_match.py; exports; unit tests; basis/provenance strings.</deliverables>
<test_first>Create tests/unit/test_industry_match.py and tests/unit/test_role_match.py before factor code.</test_first>
<deferral_policy>Ambiguous alias/fuzzy matching is deferred unless the taxonomy decision defines it.</deferral_policy>
<anti_patterns>No registry/scoring/worker/API/UI/golden edits. No event-tag role reuse. No unknown-to-zero coercion.</anti_patterns>
<success_criteria>python -m pytest tests/unit/test_industry_match.py tests/unit/test_role_match.py passes; exact/nonmatch/missing/invalid/empty cases explicit; make check where supported.</success_criteria>
<output_format>PR URL | factor keys | input/output rules | tests | deferred aliases</output_format>
```

### Agent B — CBA-MATCH-PROXIMITY

```text
/goal Implement the isolated CBA CPP-campus proximity factor under the accepted scoring ADR, without registry wiring. Branch feat/cba-match-proximity from current origin/main; one PR to main.

<role>Matching factor agent for CBA-MATCH-PROXIMITY.</role>
<mission>Produce accountable mile-band proximity outcomes for physical and virtual requests.</mission>
<context>Branch: feat/cba-match-proximity. PR base: main. Depends on CBA-DATA-SCHEMA and accepted CBA-SCORING-ADR. Parallel factor lane; registry/goldens forbidden.</context>
<read_first order="strict">
1. docs/product/cba-smart-match-customer-requirements.md §§10-11
2. Accepted CBA scoring ADR path recorded in docs/plans/open-questions/cba-phase-deferred.md
3. python/smartmatch_domain/smartmatch_domain/factors/travel_burden.py
4. docs/architecture/decisions/ADR-0011-accountable-numbers.md
5. python/smartmatch_domain/smartmatch_domain/match_run.py
</read_first>
<non_negotiables>Miles from versioned CPP origin. Exact bands/boundaries from ADR. Missing location is honest. Virtual behavior follows ADR. No network/live routing/geocoding. Version formula and provenance.</non_negotiables>
<deliverables>factors/proximity.py or versioned replacement; CPP origin/config seam; tests; coexistence/supersession note.</deliverables>
<test_first>Create tests/unit/test_cba_proximity.py; extend tests/unit/test_travel_burden.py for old/new distinction.</test_first>
<deferral_policy>Live geocoding/routes remain gated; unresolved address returns approved unknown/refusal behavior.</deferral_policy>
<anti_patterns>No kilometers on CBA output. No invented boundary or proportional formula. No registry/scoring/golden/API edit.</anti_patterns>
<success_criteria>python -m pytest tests/unit/test_cba_proximity.py tests/unit/test_travel_burden.py passes, including exact 25/75 and virtual cases; make check where supported.</success_criteria>
<output_format>PR URL | formula version | campus origin source | boundary behavior | tests | deferred providers</output_format>
```

### Agent C — CBA-MATCH-TOPIC

```text
/goal Implement fixture-backed semantic CBA Topic scoring and one-sentence reasoning under the accepted ADR, without registry wiring. Branch feat/cba-match-topic from current origin/main; one PR to main.

<role>Matching factor/provider agent for CBA-MATCH-TOPIC.</role>
<mission>Compare request description with speaker Topic/profile/prior-talk evidence semantically and explain one sentence.</mission>
<context>Branch: feat/cba-match-topic. PR base: main. Depends on CBA-DATA-SCHEMA and accepted CBA-SCORING-ADR. Parallel factor lane; registry/goldens forbidden.</context>
<read_first order="strict">
1. docs/product/cba-smart-match-customer-requirements.md §9
2. Accepted CBA scoring ADR path recorded in docs/plans/open-questions/cba-phase-deferred.md
3. python/smartmatch_domain/smartmatch_domain/factors/topic_relevance.py
4. python/smartmatch_domain/smartmatch_domain/explanation.py
5. python/smartmatch_providers/smartmatch_providers/registry.py
6. services/api/smartmatch_api/config.py
7. tests/unit/test_provider_isolation.py
</read_first>
<non_negotiables>Deterministic fixture provider. Live provider unreachable by default/classroom. Score plus exactly one-sentence rationale. Thin-data behavior/provenance follows ADR. No LLM-generated assumptions stored as fact.</non_negotiables>
<deliverables>Semantic Topic protocol/factor; fixture provider; one-sentence explanation contract; provider isolation and unit tests.</deliverables>
<test_first>Create tests/unit/test_cba_semantic_topic.py and tests/unit/test_cba_topic_explanation.py; extend tests/unit/test_provider_isolation.py.</test_first>
<deferral_policy>Live model credentials/selection remain OQ and fail closed.</deferral_policy>
<anti_patterns>No lexical-overlap relabel as semantic. No live HTTP in tests. No registry/scoring/golden/API edit. No unlabeled neutral 0.5.</anti_patterns>
<success_criteria>python -m pytest tests/unit/test_cba_semantic_topic.py tests/unit/test_cba_topic_explanation.py tests/unit/test_provider_isolation.py passes; make check where supported.</success_criteria>
<output_format>PR URL | provider/factor versions | thin-data behavior | rationale contract | tests | live deferral</output_format>
```

---

## After the three factor PRs merge

Dispatch **one** agent for **CBA-MATCH-REGISTRY** (`feat/cba-match-registry-v2`) — serial owner of `factor_registry.py` and golden cases. Card in `cba-goal-catalog.md` § CBA-MATCH-REGISTRY.

---

## Orchestrator ledger template

| Track | Branch | PR | Status |
|-------|--------|-----|--------|
| CBA-TAXONOMY | feat/cba-taxonomy | #51 (`c3ba9a5`) | MERGED |
| CBA-DATA-SCHEMA | feat/cba-data-schema | #52 | RETURNED — open, CI green |
| CBA-SCORING-ADR | docs/cba-scoring-decisions | | PENDING |
| CBA-MATCH-INDUSTRY-ROLE | feat/cba-match-industry-role | | PENDING |
| CBA-MATCH-PROXIMITY | feat/cba-match-proximity | | PENDING |
| CBA-MATCH-TOPIC | feat/cba-match-topic | | PENDING |
