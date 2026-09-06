# Parallel `/goal` prompts — synthetic pilot product (2026-09-03)

Copy one prompt per agent. Each agent **must** branch from `origin/main` only,
use the workflow below, stay inside its fence, and open a PR targeting `main`.

**Pilot meaning (authoritative):** end-to-end **synthetic** click-through
(import → review → pipeline → metrics → matching shortlist → coordinator UI),
per `docs/decisions/synthetic-pilot-development-authorization-2026-09-03.md`.
Not production. Not live student data. Not G4 send. Not G5 Calendar API. Not
live crawl (S6a).

**Already done — do not re-implement:** P1/V4 metrics authz; P8 O1–O3 metric
binding; P9 W1 `columns.yaml` worker contract; J8/J9 dispatcher code + compose
scheduler; review decision API; G1/D1 registry approval + M1; pipeline
**repository** (uncalled); compose db/api/worker/scheduler; R3 threat model
signed.

**Human / external (do not invent values):** A1b worksheet Part 1 issuer /
audience / JWKS / client ID; G2/D8 live data; G3 eval set for live crawl; G4;
G5; D9 license.

---

## Shared workflow (paste into every prompt)

Use these models in Cursor (labels as of 2026-09-03):

| Role | Model | Thinking |
|------|--------|----------|
| Orchestrator | **Opus 5.0** | **medium** |
| Planning pass (read plans, write a short plan in the PR body; no code) | **Opus 5.0** | **high** |
| Implementation | **Sonnet 5.0** | default |
| Code review | **Opus 5.0** | **medium** |
| Then | Open a PR with `gh`; **watch the CLI** until you have a URL or a hard error |

CLI watch (do not ignore):

1. `git fetch origin` then `git checkout -b <branch> origin/main` (or
   `git switch -c <branch> --track origin/main`).
2. After implementation + review: `git status`, `git diff`, `git log -5 --oneline`.
3. `git push -u origin HEAD` — read stdout/stderr. If auth fails, **stop**.
4. `gh pr create --base main ...` — wait for the printed PR URL. If `gh`
   prompts or exits non-zero, **stop and report the exact CLI output**.
5. Optional: `gh pr checks --watch` until GitHub reports, or paste the URL.
6. Never `--force`, never `--no-verify`, never skip hooks, never merge.

Standing constraints (every agent):

- Synthetic data / fixtures / seed only. `ALLOW_CLOUD_DEPLOY=false`,
  `ALLOW_LIVE_PROVIDERS=false`, `ALLOW_LIVE_DATA=false`.
- Unknown ≠ zero (ADR-0011). No legacy scoring-engine port or characterization.
- Deny-by-default authz; no caller-chosen identity; no browser-asserted roles.
- One Alembic revision per PR if you touch migrations; next number is
  `head + 1` **on origin/main at start time** — rebase if main moved.
- Regenerated OpenAPI only; `make openapi-check`. Policy matrix rows in the
  same commit as new operations.
- Do not declare production readiness.

---

## Launch waves (merge order)

Serial resources: `db/migrations/versions/`, `contracts/openapi/smartmatch.json`,
`tests/authz/test_policy_matrix.py`, `tests/unit/test_matching_fail_closed.py`,
`apps/web/legacy-frontend/src/lib/api.ts`.

```
Wave S (launch with Wave 1; scaffold only — no migrations, no OpenAPI, not wired)
  P-OUTREACH-DRYRUN-DOMAIN  P-CALENDAR-ICS-SCAFFOLD
  P-CRAWL-FIXTURE-ENGINE    P-JWKS-VERIFIER-CORE    P-WORKER-OIDC-BACKEND

Wave 1 (launch together; no new migrations; no new OpenAPI routes)
  P-MATCH-ENGINE     P-PIPE-CALLER     P-UI-COORD     P-AUTH-DEV
                         │
Wave 2 (one at a time after Wave 1 PRs merge, or rebase onto the prior)
  P-EVENTS-SCHEMA  →  P-MATCH-PERSIST  →  P-REWARDS-LEDGER
                         │
Wave 3 (OpenAPI: one PR at a time)
  P-MATCH-API  →  P-EVENTS-API  →  P-REWARDS-API  →  P-COMPOSE-PILOT
                         │
Wave 4
  P-E2E-PILOT     P-F5-TERRAFORM (config only; do not apply)

Do not launch: P-A1B-LIVE until worksheet Part 1 is filled by a human.
Do not launch: P-CRAWL-LIVE, P-OUTREACH, P-CALENDAR (live/send/API gates).
Wave S names are not those agents.
```

---

## Wave S — scaffold, unwired (launch with Wave 1)

Side lane for G4/G5/S6a/A1b **substitutes**. Same standing constraints as every
agent. Pattern: paid extraction (`smartmatch_worker.paid_extraction`) — code
and tests exist; **shipped worker/API registries do not route to it**.

**Shared fence (every Wave S prompt includes this):**

- Branch from `origin/main`. PR title prefix `[scaffold][unwired]`.
- **No** files under `db/migrations/versions/`. **No** OpenAPI regen. **No**
  `tests/authz/test_policy_matrix.py`. **No** `apps/web/legacy-frontend/src/lib/api.ts`.
- Do not import the new modules from `services/api/smartmatch_api/main.py` or
  from `smartmatch_worker.handlers.default_registry` / `main.py` composition.
- Add a wiring test (see `tests/unit/test_paid_extraction_wiring.py`) that
  fails if the command/type appears on the shipped registry or a new `/v1`
  route appears in `contracts/openapi/smartmatch.json`.
- Invent no IdP issuer, audience, JWKS URI, or OAuth client ID.
- `ALLOW_LIVE_PROVIDERS=false`. No HTTP client to the public internet.
- Do not spawn extra verification subagents. One PR per agent below.

The **human / file orchestrator** pastes these `/goal`s. Do not nest them
inside a Wave 1 agent's Opus orchestrator.

---

### P-OUTREACH-DRYRUN-DOMAIN

**Branch:** `pilot/scaffold-outreach-dryrun`  
**Fence:** new domain (+ optional persistence helpers that do not need a
migration). Consent already lives in `smartmatch_domain.consent`.

```
/goal [scaffold][unwired] Implement a synthetic outreach dry-run domain: compose a message, assert send eligibility via consent.py, record "would send" without leaving the process. Branch: pilot/scaffold-outreach-dryrun from origin/main.

Workflow: Opus 5.0 medium orchestrator; Opus 5.0 high planning (read, do not code); Sonnet 5.0 implement; Opus 5.0 medium code-review; git push -u origin HEAD; gh pr create --base main. Watch CLI. Stop on auth or non-zero. No force push, no skipped hooks.

Read first: python/smartmatch_domain/smartmatch_domain/consent.py, docs/decisions/synthetic-pilot-development-authorization-2026-09-03.md §3 G4 row, docs/plans/frontend-broken-buttons.md B17/B35, services/worker/smartmatch_worker/paid_extraction.py (unwired registry pattern), tests/unit/test_paid_extraction_wiring.py.

Done when:
- Dry-run function refuses research-discovered addresses (assert_send_eligible / no invite-to-consent path).
- Success result is structured (recipient subject, template id, body, eligibility evidence) and is never a provider SMTP/HTTP call.
- No Resend/SendGrid/Gmail adapter. SMARTMATCH_EMAIL_API_KEY unused.
- Shipped CommandRegistry and OpenAPI unchanged. Wiring test proves absence of any outreach command type on default_registry().
- Unit tests only (no integration DB unless 000x already has a table you can write without DDL — prefer no DB).

Out of scope: routers, compose, legacy CoordinatorOutreach Send button (leave fake-success dark or untouched), G4 live send, Jarvis/agentic stream.

Fence: new python/smartmatch_domain (and tests/unit) modules only. Stop.
```

---

### P-CALENDAR-ICS-SCAFFOLD

**Branch:** `pilot/scaffold-calendar-ics`  
**Fence:** wrap existing `ics.py`; no Google client.

```
/goal [scaffold][unwired] Scaffold calendar invites as RFC 5545 ICS from explicit start/end datetimes only — no Google Calendar API. Branch: pilot/scaffold-calendar-ics from origin/main.

Workflow: Opus 5.0 medium orchestrator; Opus 5.0 high planning; Sonnet 5.0 implement; Opus 5.0 medium code-review; push; gh pr create --base main; watch CLI. No force push.

Read first: python/smartmatch_domain/smartmatch_domain/ics.py, tests/golden/test_ics_golden.py, docs/decisions/synthetic-pilot-development-authorization-2026-09-03.md §3 G5 row, ADR-0010 if you touch precision.

Done when:
- A small facade builds ICS bytes from caller-supplied aware datetimes + title (reuse generate_ics; do not duplicate folding/timezone rules).
- Unresolved / naive datetimes still refuse; never fabricate a slot (F-003).
- No google-api-python-client, no Calendar scope, no G5 env vars.
- No HTTP route. OpenAPI unchanged. API/worker main unchanged.
- Golden or unit tests for the facade.

Out of scope: month UI (P-UI-COORD), event list API (P-EVENTS-API), Workspace OAuth, writing to a user's Google calendar.

Fence: domain + tests only. Stop.
```

---

### P-CRAWL-FIXTURE-ENGINE

**Branch:** `pilot/scaffold-crawl-fixtures`  
**Fence:** in-repo bytes → domain event *candidates*. No fetch. No event tables
(those are P-EVENTS-SCHEMA).

```
/goal [scaffold][unwired] Scaffold a fixture-only crawl/ingest engine: read committed iCal/JSON-LD (or golden files) from the repo, run existing Stage 0 parsers, emit unpublished event candidates. No live HTTP. Branch: pilot/scaffold-crawl-fixtures from origin/main.

Workflow: Opus 5.0 medium orchestrator; Opus 5.0 high planning; Sonnet 5.0 implement; Opus 5.0 medium code-review; push; gh pr create --base main; watch CLI. No force push.

Read first: python/smartmatch_domain/smartmatch_domain/events.py, tests/unit/test_event_candidate.py, docs/plans/2026-08-28-g3-events-s3-s5-plan.md S6 fixture sources, docs/decisions/r3-signing-decisions-2026-09-03.md, docs/security/crawler-threat-model-draft.md (no egress).

Done when:
- Loader accepts only filesystem paths under the checkout (or a tests/fixtures tree). Rejects http(s) URLs.
- Unresolved dates stay unkeyed; unmapped tags quarantined in the returned structure (in-memory), not dropped silently.
- No urllib/httpx/requests to the public internet on the ingest path. Test that a URL input is refused.
- Not registered on the worker. No POST /api/crawler/start. OpenAPI unchanged.
- Do not add Alembic. Do not write event persistence (P-EVENTS-SCHEMA).

Out of scope: SSRF allowlist for live hosts, G3 eval set, Jarvis, CrawlerFeed UI, S6a.

Fence: domain/providers + tests + fixture files. Stop.
```

---

### P-JWKS-VERIFIER-CORE

**Branch:** `pilot/scaffold-jwks-core`  
**Fence:** isolated verifier core with **fixture keys only**. No worksheet values.

```
/goal [scaffold][unwired] Land an isolated JWT/JWKS verifier core that can verify tokens signed by test keys in-process, and that cannot be configured with a live Google issuer. Do not wire it to the API. Branch: pilot/scaffold-jwks-core from origin/main.

Workflow: Opus 5.0 medium orchestrator; Opus 5.0 high planning; Sonnet 5.0 implement; Opus 5.0 medium code-review; push; gh pr create --base main; watch CLI. No force push.

Read first: python/smartmatch_providers/smartmatch_providers/identity.py, docs/plans/2026-08-28-a1b-institutional-sign-in-plan.md (A0 stop-gate; A1 blocked), docs/decisions/a1b-idp-configuration-worksheet.md (UNFILLED — do not invent URLs), docs/decisions/a1b-gcp-console-guide.md (future env names only), services/api/smartmatch_api/config.py (do not add SMARTMATCH_JWKS_* until A1 is authorized).

Done when:
- TokenVerifier-compatible type: subject (+ email if present). No tenant, no role, no permission in the token.
- Constructor takes an explicit static JWKS or key set supplied by tests — not a discovery URL, not securetoken.google.com.
- Refuses tokens if kid missing, alg not RS256, exp invalid, or iss/aud do not match the constructor arguments (those arguments are test literals, not copied from the worksheet).
- FixtureTokenVerifier remains what API main uses. get_settings() gains no JWKS fields.
- Wiring test: smartmatch_api.main does not import the new module.

Out of scope: P-A1B-LIVE, frontend OIDC redirect, filling the worksheet, SMARTMATCH_DEV_PRINCIPALS changes (P-AUTH-DEV).

Fence: new provider/domain module + unit tests. Stop.
```

---

### P-WORKER-OIDC-BACKEND

**Branch:** `pilot/scaffold-worker-oidc-backend`  
**Fence:** signature-backend **port** only. Existing fail-closed OIDC path stays
fail-closed. Do not fight P-AUTH-DEV on frontend files.

```
/goal [scaffold][unwired] Add a worker OIDC signature-backend Protocol and a test double; do not pass a live JWKS source into build_task_verifier. Branch: pilot/scaffold-worker-oidc-backend from origin/main.

Workflow: Opus 5.0 medium orchestrator; Opus 5.0 high planning; Sonnet 5.0 implement; Opus 5.0 medium code-review; push; gh pr create --base main; watch CLI. No force push.

Read first: services/worker/smartmatch_worker/identity.py, services/worker/smartmatch_worker/config.py (no default audience), services/worker/smartmatch_worker/main.py (how verifier is built), docs/security/scaffold-security-review.md S-001, tests/unit/test_paid_extraction_wiring.py (absence pattern).

Done when:
- Protocol for "verify this JWT signature against keys" lives in a dedicated module or clearly marked section.
- Production composition still constructs the OIDC verifier with no JWKS source and no signature backend, so deliveries stay 401/501.
- LocalBearerTaskVerifier unchanged: SMARTMATCH_EDITION=dev only.
- Unit tests: backend test double can accept a locally signed token; the shipped build path still reports missing JWKS/backend.
- Do not set SMARTMATCH_TASK_AUDIENCE or service-account allowlists in compose or .env.example.

Out of scope: Cloud Tasks, Cloud Scheduler jobs, terraform apply, real Google-minted tokens, P-AUTH-DEV iaw_session work.

Fence: worker identity/backend module + unit tests. Avoid editing docker-compose.yml. Stop.
```

---

## Wave 1 — launch now (4 agents)

### P-MATCH-ENGINE

**Branch:** `pilot/match-engine-m2-m7`  
**Fence:** `python/smartmatch_domain/smartmatch_domain/factors/` (new),
`factor_registry.py` (implemented flags + wiring only), golden fixtures,
`tests/unit/test_factor_*.py`, M7 optimizer module + tests. **No** migrations,
**no** OpenAPI, **no** routers, **no** frontend.

```
/goal Implement G1-approved matching engine M2, M4, M6, M6j, and M7 on a new branch from origin/main named pilot/match-engine-m2-m7.

Workflow: Opus 5.0 medium orchestrator; Opus 5.0 high planning (read, do not code); Sonnet 5.0 implement; Opus 5.0 medium code-review; then git push -u origin HEAD and gh pr create --base main. Watch gh/git CLI output; stop on auth or non-zero exit. No force push, no skipped hooks.

Read first: docs/plans/workshops/g1-workshop-output-worksheet.md (RATIFIED), docs/plans/2026-08-28-g1-matching-m1-m10-plan.md cards M2–M7, python/smartmatch_domain/smartmatch_domain/factor_registry.py, tests/golden (or create tests/golden/matching/), docs/decisions/synthetic-pilot-development-authorization-2026-09-03.md (F-25 normalize-on-apply).

Done when:
- topic_relevance (weight 0.70) and travel_burden (weight 0.30) are real scorers. Missing evidence returns unknown (None), never 0.
- travel_burden uses straight-line / synthetic coordinates labeled coarse estimate (D3 deferred). Never fabricate mileage or call a live route-matrix provider.
- availability is Stage A after shortlist, weight 0, not in Stage B. Dropped factors stay unimplemented: role_fit, engagement_load, repeat_penalty, credential_check, contact_status, declared_cap.
- M6j: implemented scoring set equals approved set; weights sum to 1.0 on apply; golden cases G1-GC-002/005/006/003/007/008 classify measured_zero vs unknown; tie-break lexicographic ascending subject_id (G1-GC-004).
- M7: CP-SAT portfolio assignment (OR-Tools), never an LLM; deterministic given inputs+seed; solver version recorded. Presentation rule is not this PR: return 2–3 speakers is M10.
- assert_registry_approved() still required on every scoring path. Do not add match HTTP routes (M8b is another agent).
- Tests: focused pytest for new modules; do not invert OpenAPI fail-closed scan.

Out of scope: match_run table, API, UI, pipeline writers, crawler.
```

### P-PIPE-CALLER

**Branch:** `pilot/pipeline-synthetic-caller`  
**Fence:** import/review handlers, persistence pipeline caller wiring,
professional `user_account` link on import, synthetic `attendance_record`
writer, tests. Prefer **no new migration** if `0011`/`0012`/`0009` suffice.
If a migration is required, it is the **only** Wave 1 PR allowed to add one —
coordinate in the PR title `[migration]` and rebase if another lands first.

```
/goal Wire the synthetic production caller for PipelineRepository so coordinator review can populate pipeline_record and funnel metrics leave measured-zero-only, on branch pilot/pipeline-synthetic-caller from origin/main.

Workflow: Opus 5.0 medium orchestrator; Opus 5.0 high planning; Sonnet 5.0 implement; Opus 5.0 medium code-review; push and gh pr create --base main. Watch CLI; stop on failure. No force push.

Read first: docs/decisions/synthetic-pilot-development-authorization-2026-09-03.md §4, python/smartmatch_persistence/smartmatch_persistence/pipeline.py, services/worker import/review path, migration 0011_pipeline_record, 0012_professional_unit_relationship, services/api/smartmatch_api/routers/review.py, tests/integration/test_pipeline_record_writers.py.

Authorized for synthetic pilot:
1. G1 is closed — matched_at may represent heuristic match only after P-MATCH-ENGINE exists; until then, record_matched may be called from review-accept of in-list professionals with provenance "synthetic / coordinator-accepted", not a fake score.
2. Choice A: import creates or links user_account per professional (no orphan subject_id).
3. Minimal synthetic attendance_record writer so Attended-stage CHECK can be satisfied in seed/demo flow — not QR, not live events.

Done when:
- A deployed-in-compose path (import and/or review decision) writes pipeline_record; opportunities_rows_v1 / pipeline_funnel_rows_v1 can be non-zero from that path in integration tests.
- No live data. No weakening of 0011 CHECKs. No calling PipelineRepository from unauthenticated routes.
- Authz unchanged except new operations if strictly required (prefer existing import/review commands).
- If you must add a migration: one revision, schema.py + behavioural tests, rebase onto latest origin/main.

Out of scope: matching scores, OpenAPI match routes, rewards catalog listing, crawler, Terraform.
```

### P-UI-COORD

**Branch:** `pilot/legacy-ui-coordinator-pilot`  
**Fence:** `apps/web/legacy-frontend/` except do not rewrite `api.ts` auth
header contract (P-AUTH-DEV owns remaining session identity). You **may** add
typed client functions for **existing** OpenAPI operations only.

```
/goal Make the authorized legacy frontend a truthful synthetic-pilot coordinator surface: discovery feed, events calendar, opportunities vs funnel agreement, no caller-chosen identity UX leftovers, on branch pilot/legacy-ui-coordinator-pilot from origin/main.

Workflow: Opus 5.0 medium orchestrator; Opus 5.0 high planning; Sonnet 5.0 implement; Opus 5.0 medium code-review; push and gh pr create --base main. Watch CLI. No force push.

Read first: apps/web/DESIGN.md (legacy-only scope), docs/plans/frontend-migration.md Fix #5 #7 #12, g1 worksheet presentation (2–3 speakers, no percentage — keep matching UI gated or labeled unavailable until match API exists), README synthetic banner rules.

Done when:
- Single standard login entry (no portal picker, no role cards, no ?role=). Sign-in may remain "not connected" if A1b worksheet is empty — do not fake success.
- Dashboard discovery feed uses real /v1/metrics (and drill-down) with ADR-0011 provenance; unknown is not drawn as 0. Red/yellow/green is presentation of accountable metrics, not invented scores.
- Opportunities page and pipeline/dashboard do not show two different "opportunities" totals; subscribe to registered opportunities_rows_v1 / pipeline metrics. Remove fabricated crawler dates/roles (H21).
- Month calendar on events page is presentation over honest event records if an API exists; otherwise empty/unavailable state, not mock ICS.
- SyntheticDataBanner remains. Purple theme stays on hold.
- Frontend tests/typecheck/build as in CI web job. Browser-verify changed flows if tools exist.

Out of scope: new apps/web product UI (D-1..D-11 still open), matching shortlist API, live OIDC, adding OpenAPI operations.
```

### P-AUTH-DEV

**Branch:** `pilot/auth-dev-identity`  
**Fence:** leftover `iaw_session` / fallback identities in legacy layouts;
compose/dev bearer documentation; **fixture** JWKS seam only. **Forbidden:**
filling A1b worksheet issuer/audience/client ID.

```
/goal Close remaining Fix #7 identity leftovers for synthetic compose pilot: every authenticated UI principal comes from GET /v1/me or the existing fixture bearer, never sessionStorage role blobs or stu-001 fallbacks. Branch: pilot/auth-dev-identity from origin/main.

Workflow: Opus 5.0 medium orchestrator; Opus 5.0 high planning; Sonnet 5.0 implement; Opus 5.0 medium code-review; push and gh pr create --base main. Watch CLI. No force push.

Read first: docs/plans/2026-08-28-a1b-institutional-sign-in-plan.md (A0 vs A1 stop-gate), docs/decisions/a1b-idp-configuration-worksheet.md (UNFILLED — do not invent IdP URLs), tests/unit/test_frontend_auth_contract.py, tests/contract/test_me.py, docker-compose.yml.

Done when:
- Inventory of iaw_session / fallback identity readers is current; those reads are removed or replaced with fetchMe() + fixture bearer (VITE_SMARTMATCH_BEARER_TOKEN / documented compose tokens).
- Unauthenticated users cannot appear signed-in. No mockLogin, no role-in-body.
- Worker/API keep refusing live OIDC without a signature backend. LocalBearerTaskVerifier stays SMARTMATCH_EDITION=dev only.
- Document in PR how a coordinator clicks through compose with a fixture token.
- If worksheet Part 1 is still outstanding, do not implement live JWKS. Report remaining A1b fields.

Out of scope: production SSO, Terraform, matching, rewards.
```

---

## Opus 5.0 operating rules (paste into every remaining-wave prompt)

Anthropic Opus 5: give the full spec, then run. Keep chat short. Scope stays
the fence. Do not add a verification subagent. Do not pad docs.

```
Start every session by loading and following the user skill "I have ADHD".
Use it for all user-facing messages: one next action, short chunks, outcome
first, no walls of text. If the skill file is missing, keep that cadence anyway.

Keep responses focused and brief. Before the first tool call, say one sentence
of what you will do. While working, update only when you change direction.
When you finish, first sentence is the outcome.

Deliver this task at the intended scope. Make routine judgment calls. If the
request looks mistaken, say so in one sentence and continue as asked. Finish
the whole task. Stop at the fence.

Do not add a separate verification or double-check pass. Do not spawn a
subagent to re-check your work. Delegate only for large independent tracks;
prefer doing the work yourself. Keep spawn counts low.

Match written files to the task. No filler sections.

Only correct an earlier statement if it would change code or the PR. State
the correction once, then continue.

git fetch origin. Branch from origin/main (or latest origin/main if a
predecessor already merged). Push with git push -u origin HEAD. Open a PR
with gh pr create --base main. Watch CLI stdout/stderr. Stop on auth failure
or non-zero exit. No force push. No skipped hooks. No merge.

Orchestrator: Opus 5.0 effort medium. Planning: Opus 5.0 effort high (read
plans; no code in that pass). Implementation: Sonnet 5.0. Code review:
Opus 5.0 effort medium — report every finding; do not filter to
"high-severity only." Then open the PR.

Synthetic fixtures only. ALLOW_CLOUD_DEPLOY=false. ALLOW_LIVE_PROVIDERS=false.
ALLOW_LIVE_DATA=false. Unknown is not zero. No legacy scoring-engine port.
No production-readiness claim.
```

Launch remaining waves **serially** on migrations and OpenAPI:
`P-EVENTS-SCHEMA` → `P-MATCH-PERSIST` → `P-REWARDS-LEDGER` → `P-MATCH-API` →
`P-EVENTS-API` → `P-REWARDS-API` → `P-COMPOSE-PILOT` → `P-E2E-PILOT`.
`P-F5-TERRAFORM` may run beside E2E (no OpenAPI, no migration).

---

## Wave 2 — one migration owner at a time

### P-EVENTS-SCHEMA — `pilot/events-s3-s5-schema`

Start after Wave 1 is on `origin/main`. This PR owns the next Alembic revision.

```
/goal Persist the synthetic-pilot event model (S3–S5f). One migration. No HTTP routes. No live fetch.

Use skill "I have ADHD" every session. Opus 5.0 medium orchestrate; Opus 5.0 high plan then stop coding; Sonnet 5.0 implement; Opus 5.0 medium review (report all findings); push and gh pr create --base main; watch CLI.

Branch: git fetch origin && git switch -c pilot/events-s3-s5-schema origin/main

Read: docs/plans/2026-08-28-g3-events-s3-s5-plan.md S3–S5f; ADR-0010; ADR-0012; docs/decisions/r3-signing-decisions-2026-09-03.md; python/smartmatch_domain/smartmatch_domain/events.py.

Direction: land event storage that coordinators can later list. Unresolved dates stay unkeyed. Unmapped tags go to quarantine. Then attach attendance_record.event_id as an FK.

Done:
- One Alembic revision + schema.py + integration CHECKs.
- Precision enum on wire/storage (ADR-0010).
- Deterministic identity key: host org unit + normalized title + resolved window; upsert tests.
- Closed tag vocabulary; quarantine path for unmapped tags (new table or review_item — pick one and state it in the PR).
- attendance_record.event_id FK after identity exists.
- Unpublished: unresolved dates, quarantined tags.

Fence: db/migrations/versions (this revision only), schema.py, domain events, persistence for events/tags, tests for those. Stop.

Leave for later agents: OpenAPI event list, live crawl, CrawlerFeed, POST /api/crawler/start.
```

### P-MATCH-PERSIST — `pilot/match-run-m8a`

Start after `P-MATCH-ENGINE` and `P-EVENTS-SCHEMA` (or latest migration head) are on `origin/main`.

```
/goal Persist immutable match_run snapshots (M8a) on the durable command path. One migration. No match HTTP routes.

Use skill "I have ADHD" every session. Opus 5.0 medium orchestrate; Opus 5.0 high plan; Sonnet 5.0 implement; Opus 5.0 medium review (all findings); push; gh pr create --base main; watch CLI.

Branch: git fetch origin && git switch -c pilot/match-run-m8a origin/main

Read: docs/plans/2026-08-28-g1-matching-m1-m10-plan.md M8a; docs/plans/workshops/g1-workshop-output-worksheet.md (version pin + MM-005 shadow for weight changes); ADR-0005.

Direction: every run stores inputs hash, registry version hash, weights, optimizer pin, route-estimate pin, tenant/unit, created_at. Rows do not update after insert.

Done:
- One migration + schema.py + PostgreSQL integration tests.
- Writes go through existing job/outbox command pattern.
- tests/unit/test_matching_fail_closed.py OpenAPI scan unchanged.

Fence: match_run schema/persistence/command enqueue only. Stop.

Leave: M8b routes, M9 explanations, M10 UI.
```

### P-REWARDS-LEDGER — `pilot/rewards-l1-l3-domain`

Start after latest `origin/main` (event FK helps attendance). Prefer no new migration if `0009` already has the tables.

```
/goal Build the synthetic rewards domain: attendance-derived ledger fold, catalog listing that refuses unfunded/unowned items, redemption state machine. No HTTP.

Use skill "I have ADHD" every session. Opus 5.0 medium orchestrate; Opus 5.0 high plan; Sonnet 5.0 implement; Opus 5.0 medium review (all findings); push; gh pr create --base main; watch CLI.

Branch: git fetch origin && git switch -c pilot/rewards-l1-l3-domain origin/main

Read: docs/plans/2026-08-28-d6-rewards-s8-s9-plan.md L1–L4; ADR-0013; docs/architecture/engagement-model.md; db/migrations/versions/0009_engagement_schema.py; docs/decisions/pilot-decisions.md D6/D7.

Direction: points come from verified attendance at 100 pts/event (D7). Budget owner is Danny Tran (@dangt) (D6). N=3 is tentative — assert or document, do not invent a new economy. Balance is a fold of an append-only ledger.

Done:
- Domain + persistence services + unit tests (integration if you write DB).
- Listable items always have budget_owner_id and funded=true.
- Redemption: requested → approved → fulfilled | denied | expired.
- If 0009 is insufficient: exactly one migration, else none.

Fence: engagement/rewards domain+persistence+tests. Stop.

Leave: OpenAPI, studentRewardsCatalog.ts deletion (P-REWARDS-API).
```

---

## Wave 3 — one OpenAPI PR at a time

### P-MATCH-API — `pilot/match-api-m8b-m10`

Start after `P-MATCH-PERSIST` is on `origin/main`.

```
/goal Expose match-run command+read (M8b), per-factor explanations (M9), and coordinator shortlist UI (M10): 2–3 speakers, no percentage, label "heuristic score", registry version on every score.

Use skill "I have ADHD" every session. Opus 5.0 medium orchestrate; Opus 5.0 high plan; Sonnet 5.0 implement; Opus 5.0 medium review (all findings); push; gh pr create --base main; watch CLI.

Branch: git fetch origin && git switch -c pilot/match-api-m8b-m10 origin/main

Read: docs/plans/2026-08-28-g1-matching-m1-m10-plan.md M8b/M9/M10; G1 worksheet presentation rules; tests/unit/test_matching_fail_closed.py; tests/authz/test_policy_matrix.py.

Direction: coordinators run a match and see an honest shortlist. Flip the OpenAPI fail-closed scan in the same commit the routes land. Regenerate OpenAPI; do not hand-edit. Roles: admin and coordinator only unless a committed artifact names others.

Done:
- Authenticated unit-scoped match-run write+read.
- Unknown vs measured zero in explanations.
- Legacy AIMatching / Run matcher uses the API or an unavailable state — no mock ranks.
- make openapi-check; policy matrix rows for new operations.

Fence: match routers, OpenAPI regen, policy matrix, fail-closed scan, legacy matching pages + typed client for these ops only. Stop.

Leave: apps/web new product UI; live IdP.
```

### P-EVENTS-API — `pilot/events-api-fixture`

Start after `P-EVENTS-SCHEMA` and `P-MATCH-API` are on `origin/main` (OpenAPI serial).

```
/goal Ship coordinator event-list and tag-quarantine review APIs fed by in-repo iCal/JSON-LD fixtures. No live HTTP fetch.

Use skill "I have ADHD" every session. Opus 5.0 medium orchestrate; Opus 5.0 high plan; Sonnet 5.0 implement; Opus 5.0 medium review (all findings); push; gh pr create --base main; watch CLI.

Branch: git fetch origin && git switch -c pilot/events-api-fixture origin/main

Read: docs/plans/2026-08-28-g3-events-s3-s5-plan.md S6 (fixture sources); tests/unit/test_event_candidate.py; ADR-0012.

Direction: list only resolved, non-quarantined events. Provenance is a field. Contact-free wrapper stays contact-free. ALLOW_LIVE_PROVIDERS stays false.

Done:
- List + quarantine-review routes; policy matrix; regenerated OpenAPI; fail-closed scan updated only for these ops.
- Worker ingest from existing Stage 0 parsers into event persistence.

Fence: event routers, worker ingest of fixtures, OpenAPI, tests. Stop.

Leave: public-internet crawler, SSRF egress, Jarvis.
```

### P-REWARDS-API — `pilot/rewards-api-u1`

Start after `P-REWARDS-LEDGER` and `P-EVENTS-API` are on `origin/main`.

```
/goal Ship S8 listing and S9 redemption HTTP APIs. Delete client-side studentRewardsCatalog.ts / studentPoints.ts formulas. Progress only toward reachable funded items.

Use skill "I have ADHD" every session. Opus 5.0 medium orchestrate; Opus 5.0 high plan; Sonnet 5.0 implement; Opus 5.0 medium review (all findings); push; gh pr create --base main; watch CLI.

Branch: git fetch origin && git switch -c pilot/rewards-api-u1 origin/main

Read: docs/plans/2026-08-28-d6-rewards-s8-s9-plan.md R3 U1; ADR-0013; tests/integration/test_engagement_schema_constraints.py.

Direction: students see a server catalog and request redemption. Identity from GET /v1/me. Synthetic seed items only.

Done:
- Routes + policy matrix + regenerated OpenAPI.
- Legacy catalog constants removed.
- Unfunded/unowned items stay unlistable.

Fence: rewards routers, OpenAPI, legacy rewards pages, tests. Stop.

Leave: real money, procurement, live D8 disclosure.
```

### P-COMPOSE-PILOT — `pilot/compose-pilot-appliance`

Start after the Wave 3 APIs you document as required, or ship with named gaps.

```
/goal Make docker compose the stakeholder click-through: Postgres, migrate, seed, API, worker, scheduler, legacy Vite frontend on documented ports.

Use skill "I have ADHD" every session. Opus 5.0 medium orchestrate; Opus 5.0 high plan; Sonnet 5.0 implement; Opus 5.0 medium review (all findings); push; gh pr create --base main; watch CLI.

Branch: git fetch origin && git switch -c pilot/compose-pilot-appliance origin/main

Read: docker-compose.yml; docs/operations/containers.md; docs/decisions/f5-deploy-target-note-2026-09-03.md; INSTALL.md.

Direction: one documented `docker compose up` path. Seed creates a pending review item. Funnel is non-zero if pipeline caller merged, otherwise an honest zero. SMARTMATCH_EDITION=dev still required for seed/loopback/fixed tokens. Optional IdP sidecar only with documented fixture users — invent no Google issuer URLs.

Done:
- Compose + docs + compose-smoke CI if you add services.

Fence: compose, seed, CI smoke, INSTALL/containers docs. Stop.

Leave: terraform apply, ALLOW_CLOUD_DEPLOY, production IdP.
```

---

## Wave 4

### P-E2E-PILOT — `pilot/e2e-synthetic-clickthrough`

Start after `P-COMPOSE-PILOT` is on `origin/main` (or skip missing steps by name).

```
/goal Add a CI make target that click-throughs the synthetic pilot: fixture auth, columns.yaml import, review accept/reject, metrics read, then match/events/rewards if those routes exist.

Use skill "I have ADHD" every session. Opus 5.0 medium orchestrate; Opus 5.0 high plan; Sonnet 5.0 implement; Opus 5.0 medium review (all findings); push; gh pr create --base main; watch CLI.

Branch: git fetch origin && git switch -c pilot/e2e-synthetic-clickthrough origin/main

Direction: the job fails on mock ranks, unknown-drawn-as-zero, or caller-chosen role. Missing merges use pytest.skip/xfail with the missing PR name. Never assert fake success.

Done: documented make target or CI job covering the path above.

Fence: tests/e2e or equivalent + CI wiring. Stop.

Leave: live SSO, live crawl, outreach send.
```

### P-F5-TERRAFORM — `pilot/f5-classroom-terraform`

May run in parallel with E2E.

```
/goal Complete classroom-project Terraform modules for a hosted synthetic demo. Do not terraform apply. Do not set ALLOW_CLOUD_DEPLOY=true.

Use skill "I have ADHD" every session. Opus 5.0 medium orchestrate; Opus 5.0 high plan; Sonnet 5.0 implement; Opus 5.0 medium review (all findings); push; gh pr create --base main; watch CLI.

Branch: git fetch origin && git switch -c pilot/f5-classroom-terraform origin/main

Read: infra/terraform/README.md; docs/operations/deploy-runbook.md; docs/decisions/f5-deploy-target-note-2026-09-03.md.

Direction: Cloud Run API+worker, Cloud SQL Postgres 16, Cloud Tasks, Cloud Scheduler, Secret Manager placeholders. Environments share no identifiers. No live API keys. README states apply is still gated.

Done: modules + isolation assertions + README.

Fence: infra/terraform and related docs/CI. Stop.

Leave: registry push, real OIDC keys, prod project, apply.
```

---

## Still not a remaining-wave launch (live gates)

Wave S is the synthetic substitute. Do **not** start these names until a human
commits the missing values or a new decision reopens the gate:

- **P-A1B-LIVE** — worksheet Part 1 still empty (issuer/aud/JWKS/client ID).
  Not P-JWKS-VERIFIER-CORE.
- **P-CRAWL-LIVE** — R3 signed; G3 eval set not started; no live fetch.
  Not P-CRAWL-FIXTURE-ENGINE.
- **P-OUTREACH** (G4 send) / **P-CALENDAR** (G5 Calendar API) / G2 live student
  data — deferred in the synthetic authorization (2026-09-03). Not the Wave S
  dry-run / ICS agents.

Wiring Wave S into routers, compose, or OpenAPI is a **later named PR**, after
the matching Wave 2/3 serial owners, not a silent follow-up on the scaffold
branch.

---

## Human checklist

- Launch Wave S **with** Wave 1 (five extra PRs, unwired). Merge them whenever
  green; they must not take the Alembic or OpenAPI lock.
- Merge Wave 1, then Wave 2 one PR at a time, then Wave 3 one OpenAPI PR at a time.
- Fill A1b Part 1 before **P-A1B-LIVE** (not before P-JWKS-VERIFIER-CORE).
- G2/D8 before any real student CSV.
