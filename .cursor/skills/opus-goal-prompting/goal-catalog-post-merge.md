# `/goal` catalog — post PR #36 + #37 (2026-09-04)

**Merged on `main`:**
- **#36** — setup/health/deploy: `smartmatch.sh`, `compose_health.sh`, VM deploy, e2e clickthrough, pilot login (0020), portals, `deploy.yml`
- **#37** — R4 outreach: domain, schema 0021, API, worker `outreach.send`, legacy Coordinator Send wired, OQ doc

**Verify before launch:** `git fetch origin && git log -1 --oneline origin/main`

**Superseded — do not re-run:** P-OUTREACH-DRYRUN-DOMAIN, P-OUTREACH full slice, P-AUTH-DEV, P-E2E-PILOT, P-CALENDAR-ICS-SCAFFOLD (see `calendar_invite.py` + wiring tests).

**Superseded (2026-09-04 audit, already on main before this catalog was drafted):**
- **G3** P-WORKER-OIDC-BACKEND — fully merged in PR #17 (`signature_backend.py`, `test_worker_signature_backend.py`). Do not re-run.
- **G2** P-JWKS-VERIFIER-CORE — core merged in PR #27 (`jwks.py`, `test_static_jwks_verifier.py`). Residual OQ doc merged in PR #38. Fully superseded.
- **G4** P-F5-TERRAFORM — modules merged in PR #25. Classroom root module + check update merged in PR #39. Fully superseded.
**Open PRs (2026-09-04 wave 1+2, unmerged):** G6 → #40 · G1 → #41 · G5 → #42 · G8 → #43 (migration 0022 `event.ends_at`) · G10 → #44 · G7+G9 combined → #45 (migration 0022 `contact_channel_transition`; renumber whichever of #43/#45 merges second). Crawler work deferred: coordinators add events manually.

---

## G1 — Pipeline stage writers (P-PIPE-CALLER)

```
/goal Implement pipeline stage writers beyond `record_matched`: wire `PipelineRepository.advance_stage` callers for confirmed, attended, and member_inquiry transitions with integration tests. Branch `feat/pipeline-stage-writers` from origin/main. PR to main.

<role>Lead agent for S12 pipeline production writers.</role>
<mission>Make funnel metrics non-zero for coordinator-driven stage advances without inventing outreach/calendar data.</mission>

Read first: python/smartmatch_persistence/smartmatch_persistence/pipeline.py; services/worker/smartmatch_worker/outreach.py (`_advance_pipeline`); tests/integration/test_pipeline_record_writers.py if present; docs/plans/frontend-migration.md §7.2; README pipeline row.

Assumptions: G4 closed; outreach may advance `contacted` only when `pipeline_record_id` supplied (already shipped). This goal adds **explicit API or command hooks** for later stages (coordinator confirm attendance, inquiry) with authz + idempotency.

Non-negotiables: tenant-scoped; provenance CHECK constraints; no fake UI success; one Alembic revision only if schema change required (prefer none); ADR-0011 unknown-not-zero.

Deliverables: plan card in docs/plans/2026-09-05-pipeline-stage-writers-plan.md; persistence methods if missing; minimal API routes OR worker commands (pick one pattern, match rewards/outreach); contract tests; README funnel row update.

Defer: live calendar confirmation (G5) → stage advance requires explicit coordinator action with timestamp evidence.

Success: integration tests prove matched→contacted→confirmed path on synthetic rows; metrics API returns non-zero for seeded journey; make check green.

Fence: no frontend unless one coordinator button wired to real API (optional). No terraform.
```

---

## G2 — JWKS verifier core (P-JWKS-VERIFIER-CORE)

```
/goal Land isolated JWT/JWKS verifier core with in-process test keys only. Do not wire to API main. Branch `feat/scaffold-jwks-core` from origin/main. PR to main.

<role>Auth infrastructure agent — P2 scaffold only.</role>
<mission>TokenVerifier-compatible module that verifies RS256 test tokens and refuses live Google issuers.</mission>

Read first: python/smartmatch_providers/smartmatch_providers/identity.py; tests/unit/test_static_jwks_verifier.py; docs/decisions/a1b-idp-configuration-worksheet.md (UNFILLED — do not copy values); services/api/smartmatch_api/routers/auth.py (pilot login — do not replace).

Done when: constructor takes static JWKS/keys from tests; rejects wrong alg/kid/exp/iss/aud; FixtureTokenVerifier + pilot session remain production path in main; wiring test asserts main does not import new live verifier; unit tests only.

Defer: A1b worksheet Part 1 → docs/plans/open-questions/a1b-live-idp-deferred.md.

Fence: smartmatch_providers + tests/unit. No SMARTMATCH_JWKS_* in get_settings().
```

---

## G3 — Worker OIDC signature backend (P-WORKER-OIDC-BACKEND)

```
/goal Add worker OIDC signature-backend Protocol + test double; shipped build stays fail-closed without JWKS. Branch `feat/scaffold-worker-oidc-backend` from origin/main. PR to main.

<role>Worker identity agent for S-001 scaffold.</role>
<mission>Pluggable signature verification port without enabling Cloud Tasks delivery.</mission>

Read first: services/worker/smartmatch_worker/identity.py; services/worker/smartmatch_worker/main.py; tests/unit/test_outreach_wiring.py (registry exhaustiveness pattern); docs/security/scaffold-security-review.md S-001.

Done when: Protocol module exists; test double verifies locally signed JWT; production composition still has no backend → deliveries refused; LocalBearerTaskVerifier unchanged; no compose audience env defaults.

Defer: real Google-minted tokens, terraform, Cloud Scheduler jobs.

Fence: worker identity module + unit tests. Avoid docker-compose.yml unless test-only comment.
```

---

## G4 — F5 classroom Terraform root (P-F5-TERRAFORM)

```
/goal Add classroom root Terraform module composing infra/terraform/modules/platform — plan-only, no apply, ALLOW_CLOUD_DEPLOY stays false. Branch `feat/f5-classroom-root-module` from origin/main. PR to main.

<role>Infrastructure scaffold agent.</role>
<mission>Make `terraform validate` + `make infra-check` pass with a classroom root that still cannot apply without human credentials.</mission>

Read first: infra/terraform/README.md; infra/terraform/modules/platform/*; infra/terraform/envs/classroom/main.tf; docs/operations/deploy-runbook.md; docs/decisions/f5-deploy-target-note-2026-09-03.md; tools/env_isolation_check.py.

Done when: infra/terraform/envs/classroom/root.tf (or equivalent) wires platform module with example.invalid placeholders; README documents plan-only; CI infra-check updated if rules change; no provider credentials committed; no state backend with real bucket.

Defer: Artifact Registry image URIs, worker URL, scheduler audience → open-questions/f5-deploy-deferred.md with placeholder variables.

Fence: infra/terraform + docs + CI check scripts only. No gcloud, no apply.
```

---

## G5 — Engagement API scaffold (attendance read + QR domain shell)

```
/goal Scaffold engagement router: attendance aggregate read API and QR check-in domain types (no live student PII). Branch `feat/scaffold-engagement-api` from origin/main. PR to main.

<role>R2 engagement scaffold agent.</role>
<mission>Replace empty engagement.py shell with read-only attendance summary + check-in token domain; synthetic data only.</mission>

Read first: services/api/smartmatch_api/routers/engagement.py; db/migrations/versions/0009_engagement_schema.py; docs/architecture/engagement-model.md; docs/plans/frontend-broken-buttons.md B07–B08; python/smartmatch_domain/smartmatch_domain/consent.py.

Done when: GET unit-scoped attendance summary reads real attendance_record rows; QR token issue/verify domain module (no HTTP to external); OpenAPI updated; contract tests; authz denies cross-unit; no browser-side point math.

Defer: D8 live student data, S10 disclosure consent → open-questions/engagement-deferred.md.

Fence: migration only if unavoidable; prefer using 0009 tables. No rewards changes.
```

---

## G6 — Live Resend adapter (unwired)

```
/goal Implement Resend EmailProvider adapter behind build_email_provider; default remains FixtureEmailProvider; classroom edition refuses live client. Branch `feat/scaffold-resend-adapter-unwired` from origin/main. PR to main.

<role>Provider adapter agent — OQ-002 scaffold.</role>
<mission>Live email transport exists in code but is unreachable without explicit credential + edition + non-synthetic template approval.</mission>

Read first: python/smartmatch_providers/smartmatch_providers/registry.py; python/smartmatch_providers/smartmatch_providers/base.py; services/worker/smartmatch_worker/outreach.py; docs/plans/open-questions/r4-outreach-deferred.md OQ-002/OQ-003.

Done when: Resend adapter module + unit tests with mocked HTTP; registry selects it only when api_key set and edition not classroom; synthetic templates still refused in live mode; no new env vars in compose without docs.

Defer: institutional Resend tenant, verified domain → OQ-002.

Fence: smartmatch_providers + tests. No worker behavior change beyond provider selection.
```

---

## G7 — Outreach coordinator queue + contact channel API

```
/goal Add coordinator list sends API and contact_channel CRUD with consent lifecycle transitions (synthetic .invalid only). Branch `feat/outreach-contact-admin-api` from origin/main. PR to main.

<role>Outreach completion agent building on merged R4.</role>
<mission>Close OQ-004 operational gap: coordinators can register consented contacts and list outreach sends without fake thread UI.</mission>

Read first: services/api/smartmatch_api/routers/outreach.py; python/smartmatch_persistence/smartmatch_persistence/outreach.py; python/smartmatch_domain/smartmatch_domain/consent.py; docs/plans/open-questions/r4-outreach-deferred.md; apps/web/legacy-frontend CoordinatorOutreach.tsx.

Done when: GET /v1/units/{id}/outreach/sends list; POST/PATCH contact_channel with state machine guards; no invite-to-consent template; contract + authz tests; optional legacy list UI (no fake threads).

Defer: production contact CSV import → OQ-004.

Fence: outreach router + persistence + tests. One migration only if contact table needs columns.
```

---

## G8 — Calendar ICS command (wire calendar_invite)

```
/goal Wire calendar_invite facade to a unit-scoped ICS download command (202 + job or sync GET bytes). Fix student B07 honestly. Branch `feat/calendar-ics-command` from origin/main. PR to main.

<role>Calendar artifact agent — G5 scaffold, no Google API.</role>
<mission>Students/coordinators download ICS only for resolved event datetimes; refuse unresolved (F-003).</mission>

Read first: python/smartmatch_domain/smartmatch_domain/calendar_invite.py; tests/golden/test_calendar_invite_golden.py; tests/unit/test_calendar_invite_wiring.py; smartmatch_persistence events read path; frontend-broken-buttons B07.

Done when: API command or GET returns ICS bytes from DB event rows with resolved times; wiring test updated from absence to presence; legacy StudentEvents stops toast-fake calendar add.

Defer: Google Calendar API (G5), OAuth.

Fence: no google-api-python-client. OpenAPI addition allowed.
```

---

## G9 — Contact lifecycle HTTP API (R2 slice)

```
/goal Expose contact-confidence lifecycle transitions via unit-scoped API matching consent.py state machine. Branch `feat/contact-lifecycle-api` from origin/main. PR to main.

<role>R2 consent API agent.</role>
<mission>Persist and transition contact_channel states with audit trail; no send without ACTIVE_CANDIDATE + approved source.</mission>

Read first: python/smartmatch_domain/smartmatch_domain/consent.py; tests/unit/test_consent.py; outreach schema 0021; ADR-0014 if touching disclosure.

Done when: POST transition endpoint with role gate; suppression flag; integration tests for illegal transitions; links to outreach send eligibility.

Defer: self-service opt-in forms (frontend) → document in open-questions.

Fence: API + persistence + tests. No outreach template changes.
```

---

## G10 — E2E extend post-outreach

```
/goal Extend tests/e2e/test_pilot_clickthrough.py to cover outreach draft→send→job terminal state on fixture provider. Branch `feat/e2e-outreach-clickthrough` from origin/main. PR to main.

<role>CI/e2e agent.</role>
<mission>Prove synthetic pilot path includes consent-gated outreach without fake success.</mission>

Read first: tests/e2e/test_pilot_clickthrough.py; tests/e2e/conftest.py; tests/contract/test_outreach.py; Makefile e2e targets.

Done when: e2e creates synthetic contact, draft, send, polls job to terminal; asserts delivery_event row; skips clearly if compose unavailable.

Fence: tests/e2e + Makefile/CI only.
```

---

## Orchestrator meta-goal (parallel launch)

```
/goal Launch up to 3 non-conflicting scaffold goals from .cursor/skills/opus-goal-prompting/goal-catalog-post-merge.md (pick G2, G3, G4). One branch per goal, one PR each. Use opus-goal-prompting skill for prompt shape.

Read catalog superseded list first. Do not duplicate merged outreach/login/e2e work. Report PR URLs and any new OQ files.
```

---

## Maintenance

When a catalog goal merges:
1. Move it to a **Superseded** section with PR number.
2. Update post-merge baseline (migration head, OpenAPI count) at top.
3. Refresh `docs/architecture/diagrams/` status captions if behavior changed.
