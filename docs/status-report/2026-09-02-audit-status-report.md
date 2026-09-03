# Audit-status report — 2026-09-02

**Repository:** IA SmartMatch Revamped (`IA-Smart-Match-Revamped`)  
**Report type:** Pilot readiness audit (self-hosted vs cloud)  
**Prepared:** 2026-09-02 (revised same day — see **Revision** below)  
**Posture (authoritative):** Foundation scaffold — **not production-ready, not deployed, synthetic data only**

**Authoritative blocker index:** `docs/decisions/2026-08-31-session-ratification.md`  
**Continuation order:** `docs/plans/2026-08-31-ratification-and-implementation-report.md` (V1–V8)

This report decides nothing and fills no owner field. It summarizes implemented
state, gaps, and deployment posture as of the report date.

**Revision (2026-09-02, third pass):** Records engineering slices landed after the
second pass: migration `0013_review_decision` (head **13** revisions); review
accept/reject API (`POST /v1/review-items/{id}/decision`, **11** OpenAPI
operations); S12/P8 **O3** binding — `pipeline_funnel_rows_v1` and
`opportunities_rows_v1` return measured zeros from storage (not honest-unknown);
worker **local-mode** loopback queue + compose **scheduler** sidecar; `build.yml`
**compose-smoke** job. Pipeline **writers** and live OIDC remain open.

**Current-status note:** J8/J9 dispatcher lease code is closed in-repository;
external Cloud Scheduler job and OIDC/signature provisioning remain open. CI on
Ubuntu + PostgreSQL 16 with Python 3.11–3.12 is the authoritative green gate.

---

## Executive summary

| Dimension | Status | Notes |
|-----------|--------|-------|
| **Backend foundation** | Strong (~80–88% of R1 scaffold) | Domain, authz, jobs/outbox, imports + column contract, metrics API (incl. O3 binding), review API, spend controls, **13 migrations**, compose appliance + CI smoke |
| **Pilot product surface** | Weak (~25–35%) | Matching, live auth, rewards behavior, crawler, pipeline **writers**, truthful frontend largely blocked |
| **Local dev self-host** | **Available** | `make setup` + PostgreSQL 16 + `make migrate` + `make run-api` / `make run-worker`; or `docker compose up` for db + migrate + seed + api + worker + scheduler |
| **Self-hosted “pilot in a box”** | **Partial / not ready** | Compose covers db + migrate + seed + api + worker + scheduler; still no bundled IdP or product frontend |
| **Cloud pilot** | **Not started** | Terraform skeleton; images build in CI but are not pushed; `ALLOW_CLOUD_DEPLOY=false` |

**Bottom line:** Credible **engineering platform** for private development, with
post-ratification slices (V4, V5 O1–O3, W1, review API, compose appliance) now
landed in code. **Not** a self-service institutional pilot — locally or in cloud
— without human gates (G1–G5), pipeline writers, matching, and deploy packaging.

---

## 1. Product intent and release train

**Intended product (Architecture v1.1):** Match students and professionals to
speaking opportunities; pipeline funnel (Matched → Contacted → Confirmed →
Attended → Member Inquiry); coordinator imports/review; attendance-derived
points and rewards; accountable metrics with drill-down; constrained event
discovery.

```
Foundation → R1 → R2 → R3 → R4 → R5
   (here)      G1    G2    G3   G4,G5
```

| Gate | Blocks | Owner |
|------|--------|-------|
| G1 | Factor registry + golden cases (matching) | **Danny Tran (@dangt)** — named 2026-09-02; workshop pending |
| G2 | Privacy/records for live data | Privacy / legal / records |
| G3 | Agent eval, allowlist, cost controls (crawler) | Engineering ADR + program owner |
| G4 | Consent-origin, deliverability (outreach) | Program owner + privacy/legal |
| G5 | Calendar authorization | Workspace admin + security |

---

## 2. What is implemented

### Backend and data plane

| Area | Status |
|------|--------|
| Domain primitives (ELI, ICS, consent lifecycle, jobs, ingest, feedback) | Implemented + tested |
| Deny-by-default authz | Implemented |
| PostgreSQL schema | **13 migrations** (`0001`–`0013`); head `0013_review_decision` |
| Transactional outbox + dispatcher | Implemented |
| Command path + `job.payload` (J10) | **Closed** — migration `0005`; `import.create` executes with persisted payload |
| API surface (OpenAPI) | **11 operations** — health, `/v1/me`, imports, jobs/SSE, redrive/abandon, metrics list + drill-down, **review decision** |
| Metrics authz (P1 / V4) | **Implemented** — Option B: `require_membership` in policy; `MEMBERSHIP_ONLY_OPERATIONS` for `metrics.read`; `metrics.drill_down` role-gated; `INTENTIONALLY_UNGATED_OPERATIONS` empty |
| Opportunities metric (P8 / V5) | **O3 bound** — `opportunities_rows_v1` reads accepted in-list `review_item` rows; measured zero when empty |
| Pipeline schema (S12 O2) | Migration `0011_pipeline_record` — table + constraints; funnel metrics **O3 bound** to `pipeline_record`; **no app writer** yet |
| Professional–unit relationship (P9) | Migration `0012_professional_unit_relationship` |
| Spend reservation (ADR-0015 A1) | Domain + persistence + sweeper; migration `0010` |
| Engagement schema (ADR-0013) | Tables in `0009`; **no APIs/ledger behavior** |
| Import review quarantine | Migration `0008` + `0013`; import creates pending `review_item`; **accept/reject API** (`POST /v1/review-items/{id}/decision`) |
| Container images (API + worker) | Build + CI health/SIGTERM verification |
| CI | `verify.yml` + `build.yml` — lint, types, boundaries, full pytest, OpenAPI drift, containers, **compose-smoke** |

**Tests (collected):** ~1,817 total (~1,266 no-database lane, ~551 integration) per
`README.md` and CI. Local collection on Python 3.13 failed (unsupported; repo
requires 3.11–3.12). CI on Ubuntu + Postgres 16 is authoritative.

### Partially complete

| Area | State |
|------|-------|
| Metrics API | `pending_review_items`, pipeline funnel, and opportunities **backed by DB** (O3); pipeline **writers** still open |
| Legacy frontend Wave 3C | Dashboard/Pipeline wired to `/v1/metrics`; synthetic banner |
| P3 ADR-0011 zero-coercion cleanup | Complete |
| P4 performance Stage 0+1 | Complete |
| P6 Stage 0 | iCal + JSON-LD parsers **and** `event_candidate.py` contact-free wrapper with tests (`tests/unit/test_event_candidate.py`) — fixture-only, not exported to API |
| Pilot data contract (P9 W1) | `docs/pilot-data/columns.yaml` ratified; **wired** — `smartmatch_worker/column_contract.py`; handlers enforce via `get_column_contract()` |
| J8/J9 dispatcher | **Code closed** — `ScheduledPass`, lease claim/renew/sweep; compose **scheduler sidecar** for local J8; external Cloud Scheduler wiring still open |
| `docker-compose.yml` | db + migrate + seed + api + worker + **scheduler**; **no** IdP or frontend |

### Blocked or absent

| Area | Blocker |
|------|---------|
| Matching / scoring | G1/D1 — `REGISTRY_STATUS = "proposed"`; fails closed |
| Live OIDC (API + worker) | P2 — IdP tenant exists; A1b worksheet Part 1 unfilled |
| Review accept/reject API | **Implemented** — `POST /v1/review-items/{id}/decision` |
| Outreach send | G4 |
| Calendar API | G5 |
| Crawler / live fetch | G3 + **unsigned** R3 threat model (reviewer authority resolved 1a) |
| Pipeline funnel metrics (S12 O3+) | **O3 binding done**; `pipeline_record` **app writers** not done |
| Rewards catalog / ledger / redemption | D6/D7; schema only |
| New frontend (`apps/web`) | D-0 — `DESIGN.md` owner unassigned |
| Terraform / deploy | F5; nothing applied |
| Live providers / live data | Standing constraints forbid |

---

## 3. Self-hosted: local dev vs pilot appliance

### Local developer self-host (today)

```bash
make setup && make db-up && make migrate
make run-api    # :8000, fixtures
make run-worker # :8001
```

**Alternative (Docker):**

```bash
docker compose up -d db          # database only, for pytest
docker compose up --build        # db + migrate + seed + api + worker + scheduler
```

- Python **3.11–3.12**; PostgreSQL **16**
- `make check` ≠ full CI (integration needs Postgres; image build in CI only)
- Legacy Vite frontend (`apps/web/legacy-frontend`) on :5173 — **development-only**

**Suitable for:** backend engineering verification, not institutional pilot.

### Self-hosted pilot (not ready)

| Gap | Impact |
|-----|--------|
| Compose stack incomplete for pilot | `docker-compose.yml` has scheduler sidecar but **no IdP**, **no frontend** |
| No institutional IdP | Login is fixture / broken legacy role cards |
| No deployed dispatcher scheduler (J8) | Compose scheduler covers local dev; external Cloud Scheduler job still open |
| No product frontend | Legacy UI uses mock/legacy API paths |
| Core pilot features missing | Matching, rewards, events list, outreach; pipeline writers |

---

## 4. Cloud deployment

### Intended (Architecture v1.1)

GCP: **Cloud Run** (API + worker), **Cloud SQL** (Postgres 16), **Cloud Tasks**,
**Cloud Scheduler**, **Secret Manager**. Four isolated projects: dev, staging,
classroom, prod (`infra/terraform/README.md`).

### Reality (2026-09-02)

| Item | Status |
|------|--------|
| `Dockerfile.api` / `Dockerfile.worker` | Built and probed in CI |
| `docker-compose.yml` | Local dev spike only — not a deployment claim |
| Registry push / CD | **Absent** — `build.yml` explicitly no push |
| Terraform | Placeholder `locals` only — F5 open |
| `ALLOW_CLOUD_DEPLOY=false` | Deploy blocked by contract |
| Worker OIDC | Logic exists; no signature backend → refuses live delivery |
| Monitoring / on-call | Not applicable — nothing running |

**Minimum path to classroom cloud pilot:** F5 Terraform → registry + signing gates → Cloud SQL/Run/Tasks/Scheduler → migrations per deploy runbook → IdP (P2) → product scope decision.

---

## 5. Plan portfolio (P1–P9) gate status

Index: `docs/plans/2026-08-28-plan-portfolio-index.md`

| Plan | Topic | Status (post–2 Sep decision batch + code) |
|------|-------|---------------------------------------------|
| P1 | Metrics authz | **CLOSED 2026-09-02** — Option B; **V4 implemented** in metrics router + policy matrix |
| P2 | Institutional sign-in | EXTERNAL DEPENDENCY — tenant exists; worksheet unfilled |
| P3 | ADR-0011 coercion cleanup | **Complete** |
| P4 | Performance/caching | Stage 0+1 **complete** |
| P5 | G1 matching M1–M10 | **Workshop ready** — program owner named; registry not approved |
| P6 | G3 events S3–S5 | G3 signed; R3 **unsigned** (authority resolved); Stage 0 parsers + contact-free wrapper |
| P7 | D6/D7 rewards | D6 **closed** (pilot scope); D7 tentative |
| P8 | Opportunities S12 | **CLOSED 2026-09-02** — category-list definition; **O1–O3 implemented** (register + storage binding) |
| P9 | Pilot columns | Gate A **CLOSED**; Gate B **CLOSED**; **W1 column contract wired** |

### Post-ratification engineering slices (V1–V8)

| Order | Slice | Status |
|-------|-------|--------|
| R0 | Ratification | **Complete** |
| V1 | ADR-0015 A1 spend | **Complete** (synthetic) |
| V2 | P9 pilot columns | **Largely complete** — static URL validation + W1 worker wiring |
| V3 | P6 event discovery | Parsers + contact-free wrapper (fixture-only) |
| V4 | P1 metrics authz | **Complete** — Option B implemented |
| V5 | P8 opportunities | **Complete** — O1 register, O2 schema (`0011`), **O3 storage binding** |
| V6 | P7 rewards | D6 closed — schema checks + formal record |
| V7 | P2 sign-in | Tenant exists — worksheet Part 1 |
| V8 | P5 matching | G1 workshop (owner named) |

---

## 6. Pilot readiness checklist

| Criterion | Ready? |
|-----------|--------|
| Deployable to real users | **No** |
| Real institutional sign-in | **No** — fixture tokens |
| Trustworthy matching scores | **No** — G1 blocked; UI mocks |
| Honest coordinator metrics | **Mostly** — review queue, pipeline funnel, and opportunities measured from storage |
| Import pilot CSV (`columns.yaml`) | **Yes (enforcement)** — worker reads and enforces contract; dry-run path available |
| Coordinator review decisions via API | **Yes** — `POST /v1/review-items/{id}/decision` |
| Rewards students can redeem | **No** |
| Event discovery | **No** — parsers + wrapper only |
| Outreach | **No** — consent domain only |
| Live student data (D8) | **No** — synthetic only |
| Engineering quality bar | **High** |

---

## 7. Feature completeness (approximate)

```
Auth (A1b)              ████░░░░░░  ~40%
Import/quarantine       █████████░  ~85%  (contract wired; review API shipped)
Metrics/dashboard       ████████░░  ~75%  (authz + all three metrics bound; writers open)
Matching (G1)           █░░░░░░░░░  ~10%
Opportunities (P8)      ██████░░░░  ~55%  (register + O3 binding; no pipeline writers)
Events/crawler (G3)     ███░░░░░░░  ~20%  (Stage 0 wrapper)
Rewards (D6/D7)         ██░░░░░░░░  ~15%  (schema; no behavior)
Outreach (G4)           ░░░░░░░░░░   0%
Frontend product        █░░░░░░░░░  ~10%
Deploy packaging        ██████░░░░  ~55%  (compose appliance + CI smoke; no IdP)
```

---

## 8. Highest-leverage blockers (human + engineering)

### Human / institutional (parallel)

1. **P5 G1 workshop** — program owner named; factor registry is longest product pole
2. **R3 signing pass** — reviewer authority resolved (1a); threat model unsigned
3. **P2 A1b worksheet** — IdP tenant exists; Part 1 fields pending
4. **D-0** — assign `apps/web/DESIGN.md` owner

### Engineering (when unblocked or no gate)

| ID | Item | Notes |
|----|------|-------|
| J8 | Dispatcher scheduling | **Code closed** — compose scheduler sidecar for local dev; **external Cloud Scheduler wiring open** |
| J9 | Job lease write/renew/sweep | **Code closed** — claim, renewal, terminal clear, expired-lease sweep |
| Review API | Accept/reject `review_item` | **Closed** — `POST /v1/review-items/{id}/decision` |
| S12 O3 | Pipeline owning-query binding | **Closed** — `pipeline_funnel_rows_v1` bound in metrics router |
| S12 writers | `pipeline_record` app paths | No application writer yet |
| P8 O3 | Opportunities evidence | **Closed** — `opportunities_rows_v1` bound to accepted `review_item` rows |
| Compose scheduler | Local J8 timer | **Closed** — scheduler sidecar in `docker-compose.yml` |
| A1b | Live JWKS verifier | Fixture only today |
| A4/A5 | Full authz matrix; `job.owning_unit_id` | **Closed in code**; live identity gates still open |
| M1–M10 | Matching | After G1 |
| F5 | Terraform modules | After deploy target chosen |
| W2–W5 | New frontend | After D-0 |

### Doc-sync note (CP-DOCSYNC)

| Doc | Drift |
|-----|-------|
| `README.md` pipeline funnel row | **Resolved 2026-09-02.** Was "**Not started**"; now "schema and read path only" — `pipeline_record` (migration `0011`) plus the `pipeline_funnel_rows_v1` binding, with **no application writer**, so every stage measures a real zero |
| `README.md` review decision API | **Resolved 2026-09-02.** `POST /v1/review-items/{id}/decision` and migration `0013` were absent from the capability table; a row now cites the route, the repository, and the migration |
| `README.md` metric register | **Resolved 2026-09-02.** All three owning queries read storage; the table said nothing about metrics at all |
| `README.md` compose appliance | **Resolved 2026-09-02.** Added to *Proposed, scaffolded, or deliberately absent* as **dev-only, local compose only** — the seed, loopback queue, dev bearer tokens, and scheduler sidecar all refuse to start outside `SMARTMATCH_EDITION=dev` and deploy nothing |
| `README.md` task-identity rows | **Resolved 2026-09-02.** Both rows now name the dev-only `LocalBearerTaskVerifier` alongside the unconfigured OIDC path, so "refuses every delivery" is not read as "nothing can accept a task in compose" |
| `README.md` ADR-index test count | **Resolved 2026-09-02.** Said 145; `pytest tests/unit/test_adr_index.py` collects and passes **155** |
| `README.md` suite totals | **Open, bounded.** The 1,817 / 1,266 / 551 figures predate the 2026-09-02 slices and are now labelled a floor, not a current measurement. Re-collecting needs a working local environment (the checked-in `.venv` interpreter and its `site-packages` are on different Python versions) |
| `README.md` J10 | **Accurate** — marked Done; first-draft report stale claim removed |
| First-draft report | Incorrectly stated no `docker-compose` and column contract not wired — corrected in this revision |

---

## 9. Local vs cloud comparison

| Concern | Local dev | Local pilot | Cloud pilot (GCP) |
|---------|-----------|-------------|-------------------|
| Setup | Makefile + Postgres or `docker compose` | Medium (compose + scheduler + IdP) | High (Terraform + GCP) |
| Auth | Fixture tokens | Needs IdP | Identity Platform |
| Worker/dispatcher | Manual run or compose worker + scheduler | Compose scheduler sidecar | Cloud Tasks + Scheduler |
| Product features | Same gaps | Same gaps | Same gaps |
| Ops | Engineer | Institution IT | GCP + team |
| **Readiness** | **Today** | **Months** | **Months** |

Cloud vs local is primarily an **ops choice** once the same product slices exist; both are equally unprepared for end-user pilot today.

---

## 10. Key reference paths

| Topic | Path |
|-------|------|
| Honest capability table | `README.md` |
| Session ratification | `docs/decisions/2026-08-31-session-ratification.md` |
| Plan portfolio | `docs/plans/2026-08-28-plan-portfolio-index.md` |
| Pilot decisions D1–D9 | `docs/decisions/pilot-decisions.md` |
| Blocked-work register | `docs/plans/prep/blocked-work-register-830.md` |
| Owner roster | `docs/decisions/owner-roster.md` |
| Deploy runbook | `docs/operations/deploy-runbook.md` |
| Containers / compose | `docs/operations/containers.md`, `docker-compose.yml` |
| OpenAPI contract | `contracts/openapi/smartmatch.json` |
| Pilot columns | `docs/pilot-data/columns.yaml` |
| Column contract (W1) | `services/worker/smartmatch_worker/column_contract.py` |
| Metrics router (V4/V5) | `services/api/smartmatch_api/routers/metrics.py` |
| Frontend hold | `apps/web/DESIGN.md` |

---

## 11. Post-report sync — 2 September 2026 (decision batch + implementation)

Human decisions recorded in `docs/decisions/owner-roster.md` and synced to
`docs/plans/prep/blocked-work-register-830.md` §6–§7:

| Decision | Outcome |
|----------|---------|
| Program / product owner | Danny Tran (@dangt) |
| P1 metrics authz | Closed — Option B; **implemented (V4)** |
| P8 opportunities | Closed — category-list + coordinator review; **O1 implemented** |
| P9 Gate A / Gate B | Closed (pilot scope) |
| P9 W1 column contract | **Wired** in worker |
| P7 D6 | Closed (pilot) — Danny budget owner; $5k placeholder |
| R3 authority | 1a — Development Lead is security reviewer; signature outstanding |
| P2 IdP | Tenant procured; worksheet fields pending |
| S12 O2/O3 | `0011_pipeline_record` + O3 binding landed |

**Workshop may schedule:** G1. **Next engineering without human gate:** §12 items.

---

## 12. E2E pilot slices available now (no human gate)

These slices can be completed in-repository without closing G1–G5 or filling
owner worksheets. They do **not** constitute pilot readiness.

| Slice | What works today | What remains |
|-------|------------------|--------------|
| **Import + column contract** | Inline-rows import enforces `columns.yaml`; quarantine + **review decision API** | Pipeline writers for full funnel |
| **Metrics (authorized)** | All three metrics measured from storage (O3) | Pipeline record writers for non-zero funnel |
| **Compose dev stack** | `docker compose up` — db, migrate, seed, api, worker, scheduler on :8080/:8081 | IdP, frontend |
| **Dispatcher code path** | `ScheduledPass`, lease lifecycle, compose scheduler, CI smoke | External Scheduler + OIDC provisioning |
| **S12 schema + O3** | `pipeline_record` table + metrics binding | App writers to populate `pipeline_record` |
| **P6 Stage 0** | Parsers + `ContactFreeEventCandidate` wrapper + unit tests | API export; G3/R3 for live fetch |

**Suggested next E2E engineering sequence (ordered):**

1. `pipeline_record` app writers (populate funnel stages beyond measured zero)
2. A1b live JWKS verifier (replace fixture tokens)
3. M1–M10 matching (after G1 workshop)
4. Compose IdP sidecar or documented institutional auth path

---

*End of audit-status report. Third pass revised in place on 2026-09-02; supersede by adding a new dated file under `docs/status-report/` and updating `docs/status-report/README.md`.*
