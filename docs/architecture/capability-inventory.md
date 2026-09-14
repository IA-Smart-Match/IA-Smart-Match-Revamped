# Capability Inventory

**Stage 1 §4.** Evidence-based status for every capability. Commit `c72dced`.

Status derived from code, routes, the published contract, and tests — **not**
from README claims or checklists. Where the two disagree, the disagreement is
itself recorded (§4).

**Statuses:** `COMPLETE` · `FUNCTIONAL / NEEDS HARDENING` · `PARTIAL` · `WIP` ·
`SCAFFOLDED` · `BLOCKED` · `PLANNED` · `DEPRECATED` · `DEAD / UNUSED` · `UNKNOWN`

---

## 1. Product capabilities (the `Capability` gate)

`smartmatch_domain.product_scope.Capability` is the system's own capability
declaration, and `main.py:CAPABILITY_SCOPED_ROUTERS` binds each router to one.
Under the default `CBA` scope, every capability with a router is enabled.

| # | Capability | Status | Entry point(s) | Core modules | Data model | Tests | Prod-integrated | Known issues |
|---|---|---|---|---|---|---|---|---|
| C1 | `AUTHENTICATED_LOGIN` | **FUNCTIONAL / NEEDS HARDENING** | `POST /v1/auth/login`, `/logout`, `GET /v1/me`, `/v1/me/portals` | `routers/auth.py`, `me.py`, `portals.py`, `dependencies.py` | `pilot_credential`, `pilot_session`, `pilot_login_attempt`, `user_account`, `membership` | `tests/contract/test_me.py`, `test_me_suspended.py`, `test_portals_api.py`; e2e 01–03b | Yes (pilot) | **Pilot-scoped password login, not institutional SSO.** JWKS verifier written and unit-tested (52 tests) but **unwired** — see I3 below |
| C2 | `EVENT_READS` | **COMPLETE** | `GET /v1/units/{u}/events`, `…/invite.ics`, `…/tag-quarantine`, `…/student/events`, `…/student/agenda`, `…/student/events/{e}/registration` (POST/DELETE) | `routers/events.py`, `calendar.py`, `student_events.py`, `domain/events.py`, `ical_parser.py`, `jsonld_parser.py`, `ics.py` | `event`, `event_tag`, `event_registration`, `discovery_review_item` | `contract/test_events_api.py`, `test_calendar_ics.py`, `test_student_events_api.py`; `integration/test_event_*` (6 files); e2e 13 | Yes | Rate limiting absent on `events`/`calendar` (§5) |
| C3 | `SPEAKER_REQUEST_INTAKE` | **COMPLETE** | `GET,POST /v1/units/{u}/speaker-requests`, `GET …/host/speaker-requests` | `routers/speaker_requests.py`, `domain/speaker_requests.py` | `speaker_request_classification` | `contract/test_speaker_requests_api.py`, `integration/test_speaker_request_persistence.py`; e2e 26 | Yes | — |
| C4 | `SPEAKER_CONTACT_MANAGEMENT` | **COMPLETE** | `GET,POST /v1/units/{u}/speaker-contacts`, `GET,PATCH …/{pid}`, `POST …/classification`, `GET …/speakers/{sid}/feedback-summary` | `routers/cba_contacts.py` (1,416 L), `domain/cba_contacts.py`, `cba_classification.py`, `cba_role_categories.py` | `speaker_profile`, `professional_unit_relationship`, `speaker_request_classification` | 4 contract files, 6 integration files; e2e 25 | Yes | Largest router in the codebase; two sibling routers import its private helpers (`dependency-analysis.md` §3b) |
| C5 | `MATCH_RUNS` | **COMPLETE** | `POST,GET /v1/units/{u}/match-runs[/{id}]`, `GET,PATCH …/matching-weights` | `routers/match_runs.py`, `matching_weights.py`, `worker/handlers.py:1109`, `domain/scoring.py`, `optimizer.py`, `factor_registry.py`, `explanation.py`, `factors/*` (6) | `match_run`, `match_weight_setting`, `match_weight_setting_revision` | `contract/test_match_runs_api.py`, `test_matching_weights_api.py`, `integration/test_match_run_*` (4); e2e 09–12 | Yes | **G1 gate is CLOSED** — `REGISTRY_STATUS = "approved"` with a named approver (`factor_registry.py:149,154`). `main.py`'s own module docstring still says match-run commands "wait on G1" — stale, see §4 |
| C6 | `CONSENTED_OUTREACH` | **FUNCTIONAL / NEEDS HARDENING** | 14 paths: `…/outreach/contacts*`, `…/outreach/drafts*`, `…/outreach/sends*`, `POST /v1/unsubscribe`, `…/speaker-invitations/*`, `POST /v1/speaker-invitations/respond`, `…/cba/speaker-handoff`, `GET …/cba/confirmed-speakers` | `routers/outreach.py`, `outreach_contacts.py`, `cba_contact_channels.py`, `cba_invitations.py`, `cba_handoff.py`; `worker/outreach.py`; `domain/outreach.py`, `consent.py`, `cba_invitations.py` | `contact_channel`, `contact_channel_transition`, `outreach_draft`, `outreach_send`, `delivery_event`, `suppression_record`, `cba_invitation_batch`, `cba_invitation` | 5 contract files, 5 integration files; e2e 17–24 | Yes — **through the fixture email provider only** | **No live email has ever been sent.** `ResendEmailProvider` (339 L) exists; `registry.py:107-150` refuses to construct it under fixture-only editions and requires an approved transport + institutional-sender decision (OQ-001). e2e 20 asserts the *fixture* path |
| C7 | `DISCOVERY_METRICS` | **COMPLETE** | `GET …/metrics`, `…/metrics/{name}/drill-down`, `GET …/pipeline-records/{id}`, `POST …/stages`, `POST …/events/{e}/attendance` | `routers/metrics.py` (702 L), `pipeline.py`, `attendance.py`, `domain/metrics.py`, `pipeline.py`, `attendance.py` | `pipeline_record`, `attendance_record`, `import_batch`, `review_item` | `contract/test_metrics.py`, `test_pipeline_stages.py`, `test_attendance_api.py`; `integration/test_pipeline_*` (6); e2e 08–08c | Yes | Drill-down is unbounded read work with **no rate limit** (§5) |
| C8 | `REWARDS_LEDGER` | **COMPLETE** | `GET …/rewards`, `GET,POST …/redemptions`, `POST …/redemptions/{id}/decision` | `routers/rewards.py` (861 L), `domain/rewards.py` (627 L) | `point_ledger_entry`, `reward_item`, `redemption` | `contract` via e2e 14–15; `integration/test_rewards_api.py`, `test_rewards_repository.py`, `test_redemption_durability.py`; `unit/test_rewards_domain.py` (51) | Yes | Requires a *funded* item to exercise the decision path (e2e 15 is conditional) |
| C9 | `OPERATOR_RECORD_IMPORT` | **COMPLETE** | `POST /v1/units/{u}/imports` | `routers/imports.py`, `worker/handlers.py:433`, `worker/column_contract.py`, `domain/ingest.py` | `import_batch`, `review_item` | `integration/test_import_rows.py`, `test_import_review_constraints.py`, `test_command_path.py`; e2e 04–07 | Yes | The reference implementation of the command path |

### Capabilities gated OFF under CBA scope

| Capability | Status | Evidence |
|---|---|---|
| `EXTERNAL_SPEAKER_ACQUISITION` | **PLANNED (out of scope by decision)** | Owns no router at all. `main.py` states this explicitly: *"the capabilities CBA does gate own no router — they were never mounted"* |
| Cold unknown-contact outreach | **PLANNED (out of scope)** | same |
| Chapter dues | **DEPRECATED** — belongs to `IA_WEST_LEGACY` | `product_scope.py:83-97`; `scan_cba_terminology.py` fails the build if "dues" reaches CBA copy |
| `member_inquiry` narrative | **DEPRECATED** | same |

**OBSERVED — this is a good pattern.** A gated-off capability here is *absent*,
not `if enabled:`-wrapped. There is no dead branch to accidentally enable.

---

## 2. Infrastructure capabilities (mounted unconditionally)

| # | Capability | Status | Entry point | Core modules | Data model | Tests | Known issues |
|---|---|---|---|---|---|---|---|
| I1 | **Job lifecycle / command substrate** | **COMPLETE** | `GET /v1/jobs/{id}`, `/events` | `commands.py`, `job_authz.py`, `worker/execution.py`, `domain/jobs.py` | `job`, `job_event`, `idempotency_record` | `integration/test_command_path.py`, `test_job_lease_lifecycle.py`, `test_job_states_match_domain.py`, `test_job_owning_unit.py`, `test_worker_execution.py` | — |
| I2 | **Transactional outbox + dispatcher** | **COMPLETE** | `POST /operations/dispatch` (worker) | `worker/dispatcher.py` (1,152 L), `persistence/outbox.py` (884 L) | `outbox_record` | `integration/test_outbox_dispatcher.py` (**44 tests** — incl. crash between commit and task creation, duplicate delivery), `test_scheduled_dispatch_pass.py` | Only exercised against `FixtureTaskQueue` / `local_tasks` |
| I3 | **Task-identity verification (OIDC)** | **SCAFFOLDED — fails closed** | `POST /tasks/execute` | `worker/identity.py` (682 L), `providers/jwks.py` (469 L) | — | `unit/test_static_jwks_verifier.py` (52), `contract/test_worker_boundary.py` | **Never verified against a real issuer.** Unconfigured → `501`, refuses everything (resolves S-001) |
| I4 | **Redrive / parked jobs** | **COMPLETE** | `POST /v1/jobs/{id}/redrive`, `/abandon` | `routers/redrive.py` (637 L), `persistence/redrive.py` (561 L) | `redrive_record` | `integration/test_redrive.py` (37) | — |
| I5 | **Import review queue** | **COMPLETE** | `POST /v1/review-items/{id}/decision` | `routers/review.py`, `persistence/review.py` | `review_item` | `contract/test_review_decision.py`, `integration/test_review_accept_opens_pipeline.py`; e2e 06–07 | — |
| I6 | **Engagement summary** | **COMPLETE** | `GET …/engagement/attendance-summary` | `routers/engagement.py`, `persistence/engagement.py` | `attendance_record` | `contract/test_engagement_api.py`, `integration/test_engagement_schema_constraints.py` | No rate limit (§5) |
| I7 | **Rate limiting** | **COMPLETE** | — (dependency) | `dependencies.enforce_rate_limit`, `persistence/rate_limit.py` | `rate_limit_counter` | `integration/test_rate_limit.py` | Fixed-window by decision (ADR-0006); applied to 20 of 26 routers (§5) |
| I8 | **Spend / quota** | **FUNCTIONAL / NEEDS HARDENING** | — (dependency) | `dependencies.charge_quota`, `domain/spend.py`, `persistence/spend.py` | `tenant_budget`, `spend_ceiling_bucket`, `spend_reservation` | `integration/test_spend_reservation.py`, `unit/test_spend.py` (40) | **`spend_sweeper.py` (244 L) has no scheduled caller** — see `wip-analysis.md` §4 |
| I9 | **Tenant isolation** | **COMPLETE** | — | `authz/policy.py`, `units.py` | all unit-scoped tables | `integration/test_tenant_isolation.py`, `authz/test_policy_matrix.py` (41) | — |
| I10 | **OpenAPI contract publication** | **COMPLETE** | `tools/export_openapi.py` | — | 57 paths, 120 schemas | CI staleness gate | **No consumer generated from it** — see §3 |
| I11 | **Request-body bound** | **COMPLETE** | ASGI middleware | `main.py:MaxBodySizeMiddleware` | — | `contract/test_max_body_size.py` | Chunked/lying-`Content-Length` branch coverage UNKNOWN |
| I12 | **Error envelope** | **COMPLETE** | app-wide | `errors.py` | — | `contract/test_error_envelope.py` | 422 deliberately overrides FastAPI's default so one shape is published |

---

## 3. Frontend capabilities

| # | Surface | Status | Evidence |
|---|---|---|---|
| F1 | **Coordinator portal** (8 pages: Home, Events, Outreach, Meetings, MatchRuns, Invitations, MatchingWeights, SpeakerContacts, SpeakerFeedback) | **FUNCTIONAL / NEEDS HARDENING** | All call `/v1` inline; lazy-loaded in `routes.tsx`; gated by `PortalGate` + `productScope.ts` |
| F2 | **Student portal** (6 pages) | **FUNCTIONAL / NEEDS HARDENING** | same |
| F3 | **Volunteer portal** (6 pages) | **FUNCTIONAL / NEEDS HARDENING** | same |
| F4 | **Landing + Login** | **FUNCTIONAL** | Eager-loaded (not lazy) — deliberate, they carry the entry flow |
| F5 | **Legacy pages** — `Dashboard`, `Opportunities`, `Volunteers`, `Pipeline`, `Calendar`, `Outreach`, `AIMatching` | **BLOCKED / partially DEAD** | Routed and reachable, but backed by `lib/api.ts` calling 24 `/api/*` paths **no service in this repository serves**. Asserted by `tests/e2e/…::test_16_the_portal_pages_have_no_backend_in_this_repository`. Some (`Pipeline`, `Dashboard`, `Opportunities`, `AIMatching`) also call `/v1` and so partly work |
| F6 | `components/OutreachWorkflowModal.tsx` | **DEAD / UNUSED** | Referenced by no other file in `src/` |
| F7 | `components/AgenticOutreachPanel.tsx` | **DEAD / UNUSED** | same. Also names an "agentic" capability ADR-0003 explicitly excludes from Foundation |
| F8 | `components/FeedbackForm.tsx` | **DEAD / UNUSED** | same |
| F9 | **Provenance / accountable-number components** (`AccountableValue`, `MetricValueDisplay`, `MetricDrilldownSheet`, `ProvenanceDisclosure`, `SyntheticDataMarker`) | **COMPLETE** | The ADR-0011 contract rendered in the UI: a number carries its provenance or is not shown as a number |
| F10 | **Frontend test suite** (8 files) | **PARTIAL — written, never run** | `package.json` defines `test`; **no workflow invokes it** |

---

## 4. Documentation-vs-code contradictions found

Each of these is a place where a future agent reading the repository would be
misled. They are findings, not nitpicks — this repository's documentation is
load-bearing.

| # | Claim | Location | Reality |
|---|---|---|---|
| D1 | *"Match-run, discovery, and send commands — each waits on its gate: G1 for the factor registry, G3 for agent controls, G4 for consent-origin policy."* | `services/api/smartmatch_api/main.py` module docstring | **Stale.** `match_runs.router`, `outreach.router` and `cba_invitations.router` are all mounted in the table 200 lines below, and `factor_registry.py:149` reads `"approved"` |
| D2 | *"the TypeScript client is generated from it and never hand-maintained"* | `main.py` FastAPI `description=` — **published in the OpenAPI document itself** | **False.** `clients/` does not exist. `lib/api.ts` is 4,238 hand-written lines and the `/v1` calls are inline `fetch` in 49 files |
| D3 | *"`services/api/.../routers/events.py` declares no handlers… The OpenAPI contract exposes no event operation either."* | `apps/web/.../pages/Calendar.tsx:80-95` | **Stale.** `routers/events.py` is 571 lines with handlers; the contract publishes `GET /v1/units/{u}/events` and `…/invite.ics` |
| D4 | *"Readiness, which does check dependencies, is a separate private endpoint"* | `main.py:health` docstring | **UNKNOWN / likely absent.** No readiness endpoint was found on the API app |
| D5 | `ruff` `extend-exclude = ["clients/typescript", …]` | `pyproject.toml` | Excludes a path that does not exist — harmless, but it is the fossil of D2 |

**INFERRED.** D1 and D3 share a shape: a docstring written when a gate was open,
not revisited when the gate closed. The repository has no mechanism that ties a
prose claim about a gate to the gate's actual value. `factor_registry.py`
already exposes `REGISTRY_STATUS` as a constant — a test could assert that no
docstring claims G1 is open while that constant reads `"approved"`.
→ Stage 2 **AP-06**.

---

## 5. Cross-cutting coverage gaps (OBSERVED)

### Rate limiting

Applied in 20 of 26 routers. **Absent** in: `calendar`, `engagement`, `events`,
`jobs`, `me`, `metrics`, `portals`.

**Assessment.** Six of the seven are cheap authenticated reads and their absence
is defensible. **`metrics` is not**: `GET …/metrics/{name}/drill-down` returns
"the rows behind the number" (e2e 08c) — unbounded, authenticated,
database-heavy read work with no per-caller bound.
→ `risk-register.md` R-07.

### Authorization

**Complete.** Six routers do not import `smartmatch_authz` directly and all six
were verified to authorize by delegation:

| Router | Authorizes via |
|---|---|
| `cba_contact_channels` | `cba_contacts._authorize_speaker_contacts` (line 487) |
| `outreach_contacts` | `outreach._authorize_outreach` (lines 459, 494, 544) |
| `jobs` | `job_authz.authorize_job_read` |
| `redrive` | `job_authz.authorize_job_command` |
| `auth` | pre-authentication by definition; rate-limited via `_charge_login_attempt` |
| `__init__` | empty |

**No unauthorized route was found.**

### Test coverage measurement

`pytest --cov` names only the four `python/` packages. `services/api` (14k L)
and `services/worker` (7k L) are **exercised but unmeasured**.
→ `risk-register.md` R-10.
