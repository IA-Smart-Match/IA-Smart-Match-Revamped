# Audit-status report — 2026-09-02

**Repository:** IA SmartMatch Revamped (`IA-Smart-Match-Revamped`)  
**Report type:** Pilot readiness audit (self-hosted vs cloud)  
**Prepared:** 2026-09-02 (consolidated from repository exploration session)  
**Posture (authoritative):** Foundation scaffold — **not production-ready, not deployed, synthetic data only**

**Authoritative blocker index:** `docs/decisions/2026-08-31-session-ratification.md`  
**Continuation order:** `docs/plans/2026-08-31-ratification-and-implementation-report.md` (V1–V8)

This report decides nothing and fills no owner field. It summarizes implemented
state, gaps, and deployment posture as of the report date.

**Current-status correction (2026-09-02):** J8/J9, A4, A5, J4, and J17 are
implemented in this checkout. J8's external Cloud Scheduler job and OIDC/
signature provisioning remain open; the two focused J8/J9 suites have 22 cases,
but the controller's local run collected and skipped all 22 because PostgreSQL
at `localhost:5432` was unavailable.

---

## Executive summary

| Dimension | Status | Notes |
|-----------|--------|-------|
| **Backend foundation** | Strong (~70–80% of R1 scaffold) | Domain, authz, jobs/outbox, imports, metrics API, spend controls (ADR-0015 A1), 1,800+ tests |
| **Pilot product surface** | Weak (~15–25%) | Matching, live auth, rewards behavior, crawler, pipeline persistence, truthful frontend largely blocked |
| **Local dev self-host** | **Available** | `make setup` + PostgreSQL 16 + `make migrate` + `make run-api` / `make run-worker` |
| **Self-hosted “pilot in a box”** | **Not ready** | No docker-compose, no bundled IdP, no dispatcher scheduler, no product frontend |
| **Cloud pilot** | **Not started** | Terraform skeleton; images build in CI but are not pushed; `ALLOW_CLOUD_DEPLOY=false` |

**Bottom line:** Credible **engineering platform** for private development. **Not** a self-service institutional pilot — locally or in cloud — without human gates (G1–G5, P1–P9), feature work, and deploy packaging.

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
| PostgreSQL schema | 10 migrations (`0001`–`0010`) |
| Transactional outbox + dispatcher | Implemented |
| Command path + `job.payload` (J10) | **Closed** — migration `0005`; `import.create` executes with persisted payload |
| API surface (OpenAPI) | 10 operations — health, `/v1/me`, imports, jobs/SSE, redrive/abandon, metrics |
| Spend reservation (ADR-0015 A1) | Domain + persistence + sweeper; migration `0010` |
| Engagement schema (ADR-0013) | Tables in `0009`; **no APIs/ledger behavior** |
| Container images (API + worker) | Build + CI health/SIGTERM verification |
| CI | `verify.yml` + `build.yml` — lint, types, boundaries, full pytest, OpenAPI drift, containers |

**Tests (collected):** ~1,817 total (~1,266 no-database lane, ~551 integration).
CI on Ubuntu + Postgres 16 is the authoritative green gate.

### Partially complete

| Area | State |
|------|-------|
| Metrics API | `pending_review_items` backed by DB; pipeline metrics honest-unknown (S12 not started) |
| Legacy frontend Wave 3C | Dashboard/Pipeline wired to `/v1/metrics`; synthetic banner |
| P3 ADR-0011 zero-coercion cleanup | Complete |
| P4 performance Stage 0+1 | Complete |
| P6 Stage 0 | iCal + JSON-LD parsers (fixture-only, not exported to API) |
| Pilot data contract | `docs/pilot-data/columns.yaml` ratified; **not wired** to worker `validate_columns` |

### Blocked or absent

| Area | Blocker |
|------|---------|
| Matching / scoring | G1/D1 — `REGISTRY_STATUS = "proposed"`; fails closed |
| Live OIDC (API + worker) | P2 — IdP tenant exists; A1b worksheet Part 1 unfilled |
| Outreach send | G4 |
| Calendar API | G5 |
| Crawler / live fetch | G3 + **unsigned** R3 threat model (reviewer authority resolved 1a) |
| Pipeline funnel persistence (S12) | Blocks real funnel + unified opportunities |
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

- Python **3.11–3.12**; PostgreSQL **16**
- `make check` ≠ full CI (integration needs Postgres; image build in CI only)
- Legacy Vite frontend (`apps/web/legacy-frontend`) on :5173 — **development-only**

**Suitable for:** backend engineering verification, not institutional pilot.

### Self-hosted pilot (not ready)

| Gap | Impact |
|-----|--------|
| No `docker-compose` | No single-command stack |
| No institutional IdP | Login is fixture / broken legacy role cards |
| No deployed dispatcher scheduler (J8) | The pass and endpoint exist, but no external Cloud Scheduler job is provisioned; outbox is not on a deployed timer |
| No product frontend | Legacy UI uses mock/legacy API paths |
| Core pilot features missing | Matching, rewards, events list, outreach |

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
| Registry push / CD | **Absent** — `build.yml` explicitly no push |
| Terraform | Placeholder `locals` only — F5 open |
| `ALLOW_CLOUD_DEPLOY=false` | Deploy blocked by contract |
| Worker OIDC | Logic exists; no signature backend → refuses live delivery |
| Monitoring / on-call | Not applicable — nothing running |

**Minimum path to classroom cloud pilot:** F5 Terraform → registry + signing gates → Cloud SQL/Run/Tasks/Scheduler → migrations per deploy runbook → IdP (P2) → product scope decision.

---

## 5. Plan portfolio (P1–P9) gate status

Index: `docs/plans/2026-08-28-plan-portfolio-index.md`

| Plan | Topic | Status (post–2 Sep decision batch) |
|------|-------|-----------------------------------|
| P1 | Metrics authz | **CLOSED 2026-09-02** — Option B; V4 authorized |
| P2 | Institutional sign-in | EXTERNAL DEPENDENCY — tenant exists; worksheet unfilled |
| P3 | ADR-0011 coercion cleanup | **Complete** |
| P4 | Performance/caching | Stage 0+1 **complete** |
| P5 | G1 matching M1–M10 | **Workshop ready** — program owner named; registry not approved |
| P6 | G3 events S3–S5 | G3 signed; R3 **unsigned** (authority resolved); parsers only in scope |
| P7 | D6/D7 rewards | D6 **closed** (pilot scope); D7 tentative |
| P8 | Opportunities S12 | **CLOSED 2026-09-02** — category-list definition |
| P9 | Pilot columns | Gate A **CLOSED 2026-09-02** (pilot scope); Gate B **CLOSED 2026-09-02** |

### Post-ratification engineering slices (V1–V8)

| Order | Slice | Entry |
|-------|-------|-------|
| R0 | Ratification | **Complete** |
| V1 | ADR-0015 A1 spend | Ratified — may proceed (synthetic) |
| V2 | P9 pilot columns | Static HTTPS URL validation only |
| V3 | P6 event discovery | Parsers/fixtures/wrapper only |
| V4 | P1 metrics authz | **Gate closed** — implement Option B |
| V5 | P8 opportunities | **Definition closed** — O1+ when persistence ready |
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
| Honest coordinator metrics | **Partial** — review queue yes; pipeline/opportunities no |
| Import pilot CSV (`columns.yaml`) | **Partial** — API path works; column contract not enforced in worker |
| Rewards students can redeem | **No** |
| Event discovery | **No** — parsers only |
| Outreach | **No** — consent domain only |
| Live student data (D8) | **No** — synthetic only |
| Engineering quality bar | **High** |

---

## 7. Feature completeness (approximate)

```
Auth (A1b)              ████░░░░░░  ~40%
Import/quarantine       ██████░░░░  ~60%
Metrics/dashboard       █████░░░░░  ~50%
Matching (G1)           █░░░░░░░░░  ~10%
Opportunities (P8)      ██░░░░░░░░  ~20%
Events/crawler (G3)     ██░░░░░░░░  ~15%
Rewards (D6/D7)         ██░░░░░░░░  ~15%  (schema; no behavior)
Outreach (G4)           ░░░░░░░░░░   0%
Frontend product        █░░░░░░░░░  ~10%
Deploy packaging        ███░░░░░░░  ~30%
```

---

## 8. Highest-leverage blockers (human + engineering)

### Human / institutional (parallel)

1. **P5 G1 workshop** — program owner named; factor registry is longest product pole
2. **R3 signing pass** — reviewer authority resolved (1a); threat model unsigned
3. **P2 A1b worksheet** — IdP tenant exists; Part 1 fields pending
4. **D-0** — assign `apps/web/DESIGN.md` owner

### Engineering (when unblocked)

| ID | Item | Notes |
|----|------|-------|
| J8 | Dispatcher scheduling | **Code closed** — `ScheduledPass`, scheduler-authenticated endpoint, heartbeat, and alert design exist; external Cloud Scheduler wiring remains open |
| J9 | Job lease write/renew/sweep | **Code closed** — claim, renewal, terminal clear, and expired-lease sweep are implemented; focused integration execution awaits PostgreSQL |
| A1b | Live JWKS verifier | Fixture only today |
| A4/A5 | Full authz matrix; `job.owning_unit_id` | **Closed in code**; shared job authorization now enforces unit scope, with external/live identity gates still open |
| S12 | Pipeline persistence | Unblocks funnel metrics |
| M1–M10 | Matching | After G1 |
| F5 | Terraform modules | After deploy target chosen |
| W1–W5 | New frontend | After D-0 |

### Doc-sync note (CP-DOCSYNC)

As of this report date, `README.md` still lists J10 (command payload) as open.
**Code and migration `0005` show J10 closed.** Treat README line 71 as stale
until updated.

---

## 9. Local vs cloud comparison

| Concern | Local dev | Local pilot | Cloud pilot (GCP) |
|---------|-----------|-------------|-------------------|
| Setup | Makefile + Postgres | High (compose + IdP) | High (Terraform + GCP) |
| Auth | Fixture tokens | Needs IdP | Identity Platform |
| Worker/dispatcher | Manual run | Needs scheduler | Cloud Tasks + Scheduler |
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
| Deploy runbook | `docs/operations/deploy-runbook.md` |
| Containers | `docs/operations/containers.md` |
| OpenAPI contract | `contracts/openapi/smartmatch.json` |
| Pilot columns | `docs/pilot-data/columns.yaml` |
| Frontend hold | `apps/web/DESIGN.md` |

---

## 11. Post-report sync — 2 September 2026 (decision batch)

Human decisions recorded in `docs/decisions/owner-roster.md` and synced to
`docs/plans/prep/blocked-work-register-830.md` §7:

| Decision | Outcome |
|----------|---------|
| Program / product owner | Danny Tran (@dangt) |
| P1 metrics authz | Closed — Option B, subtree scopes, admin unrestricted |
| P8 opportunities | Closed — category-list + coordinator review; import + crawler |
| P9 Gate A | Closed (pilot) — relationship-scoped; multiple concurrent; no dates |
| P7 D6 | Closed (pilot) — Danny budget owner; $5k placeholder |
| R3 authority | 1a — Development Lead is security reviewer; signature outstanding |
| P2 IdP | Tenant procured; worksheet fields pending |

**Implementation may begin:** V4 (P1 metrics authz). **Workshop may schedule:** G1.

---

*End of audit-status report. Supersede by adding a new dated file under `docs/status-report/` and updating `docs/status-report/README.md`.*
