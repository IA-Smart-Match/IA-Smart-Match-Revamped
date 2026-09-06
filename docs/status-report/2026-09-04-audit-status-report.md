# Audit-status report — 2026-09-04

**Repository:** IA SmartMatch Revamped (`IA-Smart-Match-Revamped`)  
**Report type:** Pilot readiness audit (self-hosted vs cloud)  
**Prepared:** 2026-09-04  
**Posture:** Foundation scaffold — **not production-ready, not deployed, synthetic data only**

**Authoritative blocker index:** `docs/decisions/2026-08-31-session-ratification.md`  
**Continuation order:** `docs/plans/2026-08-31-ratification-and-implementation-report.md` (V1–V8)  
**Session closures since prior report (2026-09-02):** G1/D1 closed, R3 signed, synthetic pilot authorization — see `docs/decisions/pilot-decisions.md` §2026-09-03 decision records.

This report decides nothing and fills no owner field.

**Verification note:** Two Composer 2.5 explore subagents audited deploy/infra and features/gates against the tree on 2026-09-04. Local `pytest --collect-only` was **not** re-run: no `.venv` on this host and system Python 3.13 errors in `tests/authz/test_policy_matrix.py` (repo requires 3.11–3.12). Static tree count: **~1,394** test functions across **83** files (below README's ~1,817 floor). OpenAPI verified: **11 paths / 11 operations**. CI on Ubuntu + PostgreSQL 16 remains authoritative.

---

## Executive summary

| Dimension | Status | Notes |
|-----------|--------|-------|
| **Backend foundation** | **Strong** (~82–90% of R1 scaffold) | Domain, authz, jobs/outbox, imports + column contract, metrics API (O3 binding), review API, spend controls, **15 migrations** (head `0015_remove_ledger_reversal`), compose appliance + CI smoke |
| **Pilot product surface** | **Weak** (~30–40%) | G1 registry approved but **no scoring engine**; live auth, rewards behavior, crawler runtime, pipeline **production writers**, truthful new frontend largely blocked |
| **Local dev self-host** | **Available** | `make setup` + PostgreSQL 16 + `make migrate` + `make run-api` / `make run-worker`; or `docker compose up` for db + migrate + seed + api + worker + scheduler |
| **Self-hosted “pilot in a box”** | **Partial** | Compose backend appliance CI-verified; **no bundled IdP or frontend**; stakeholder path documented via manual Vite + tunnel/VM ops guides |
| **Cloud pilot** | **Not started** | Terraform skeleton only; images build in CI but are not pushed; `ALLOW_CLOUD_DEPLOY=false` |

**Bottom line:** The **09-03 decision batch** (G1/D1 closure, R3 signing, synthetic pilot authorization, hosted-demo ops guides) materially advances **policy and operator documentation**, but does not change the product verdict: this remains a credible **private engineering platform** with a **compose-verified import → review → metrics** smoke path. It is **not** a self-service institutional pilot — locally or in cloud — without M2–M3 matching implementation, pipeline production writers, P2 live OIDC, and F5 deploy packaging.

---

## 1. Product intent and release train

**Intended product (Architecture v1.1):** Match students and professionals to speaking opportunities; pipeline funnel (Matched → Contacted → Confirmed → Attended → Member Inquiry); coordinator imports/review; attendance-derived points and rewards; accountable metrics with drill-down; constrained event discovery.

```
Foundation → R1 → R2 → R3 → R4 → R5
   (here)      G1✓   G2    G3†   G4,G5
```

| Gate | Blocks | Status (2026-09-04) |
|------|--------|----------------------|
| **G1** | Factor registry + golden cases (matching) | **CLOSED 2026-09-03** — `REGISTRY_STATUS = "approved"`; `topic_relevance` 0.70, `travel_burden` 0.30. **M2–M3 scoring still unimplemented.** |
| **G2** | Privacy/records for live data | Open — D8 tentative; synthetic-only posture |
| **G3** | Agent eval, allowlist, cost controls (crawler) | G3 decision signed 2026-08-29; **R3 signed 2026-09-03** (`r3-signing-decisions-2026-09-03.md`). **No crawl runtime scaffolded.** |
| **G4** | Consent-origin, deliverability (outreach) | Open — consent lifecycle only |
| **G5** | Calendar authorization | Open — ICS artifact only |

† G3 policy signed; implementation (S6a live fetch) still gated.

---

## 2. What is implemented

### Backend and data plane

| Area | Status |
|------|--------|
| Domain primitives (ELI, ICS, consent lifecycle, jobs, ingest, feedback) | Implemented + tested |
| Deny-by-default authz | Implemented |
| PostgreSQL schema | **15 migrations** (`0001`–`0015`); head `0015_remove_ledger_reversal` (compensates dev-only `0014` prototype) |
| Factor registry (G1) | **Approved** — `REGISTRY_STATUS = "approved"`, `REGISTRY_VERSION = "1.1.0-approved-g1"`; **3 factors registered, 0/3 `implemented=True`** (`topic_relevance`, `travel_burden`, `availability`) |
| Transactional outbox + dispatcher | Implemented |
| Command path + `job.payload` (J10) | **Closed** — migration `0005`; `import.create` reads persisted payload via `ImportCommand` in `services/worker/smartmatch_worker/handlers.py` |
| API surface (OpenAPI) | **11 operations** — health, `/v1/me`, imports, jobs/SSE, redrive/abandon, metrics list + drill-down, review decision |
| Metrics authz (P1 / V4) | **Implemented** — Option B |
| Opportunities metric (P8 / V5) | **O3 bound** — `opportunities_rows_v1` reads accepted in-list `review_item` rows |
| Pipeline schema + repository (S12) | Migration `0011`; `PipelineRepository` in `smartmatch_persistence/pipeline.py` + integration tests — **no production route calls it yet** |
| Professional–unit relationship (P9) | Migration `0012` |
| Spend reservation (ADR-0015 A1) | Domain + persistence + sweeper; migration `0010` |
| Engagement schema (ADR-0013) | Tables in `0009`; router is empty shell (`services/api/smartmatch_api/routers/engagement.py`) |
| Import review quarantine | Migration `0008` + `0013`; accept/reject API shipped |
| Container images (API + worker) | Build + CI health/SIGTERM verification |
| CI | `verify.yml` + `build.yml` — lint, types, boundaries, full pytest, OpenAPI drift, containers, **compose-smoke** |

**Tests (collected):** README cites ~1,817 total (~1,266 no-database, ~551 integration) as a **floor** predating 2026-09-02 slices; not re-collected here. Key dirs: `tests/unit/`, `tests/integration/`, `tests/contract/`, `tests/authz/`, `tests/golden/matching/`.

### Partially complete

| Area | State |
|------|-------|
| Matching / scoring | G1 **approval gate closed**; product scoring still fail-closed — all three factors `implemented=False`, no match-run domain/API; OpenAPI forbids match/score path segments (`tests/unit/test_matching_fail_closed.py`); golden fixtures input-only (no expected scores) |
| Metrics API | All three owning queries bound (O3); pipeline **production writers** still open |
| Legacy frontend | Authorized for synthetic pilot (2026-09-03); owner Danny Tran for legacy scope; many screens still fixture/mock |
| P6 Stage 0 | iCal + JSON-LD parsers + contact-free wrapper — fixture-only |
| Pilot data contract (P9 W1) | `columns.yaml` ratified; worker enforces via `column_contract.py` |
| J8/J9 dispatcher | **Code closed** — compose scheduler sidecar; external Cloud Scheduler wiring open |
| Hosted synthetic demo ops | New guides: `docs/operations/hosted-synthetic-pilot-guide.md`, `docs/operations/classroom-vm-cloudflare-tunnel.md` (compose + Vite + tunnel/VM; not F5) |
| `docker-compose.yml` | db + migrate + seed + api + worker + scheduler; **no IdP or frontend** |

### Blocked or absent

| Area | Blocker |
|------|---------|
| Match scoring API/UI | M2–M3 — registry approved; implementations pending |
| Live OIDC (API + worker) | P2 — IdP tenant exists; A1b worksheet Part 1 unfilled; `FixtureTokenVerifier` only |
| Outreach send | G4 |
| Calendar API | G5 |
| Crawler / live fetch | Implementation (S6a); parsers exist, no runtime caller |
| Rewards catalog / ledger / redemption | D6 closed (pilot scope); D7 tentative; no routes |
| New frontend (`apps/web`) | Part 2 design open; legacy path authorized only |
| Terraform / cloud deploy | F5; nothing applied |
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
docker compose up --build -d   # db + migrate + seed + api + worker + scheduler
scripts/compose_smoke.sh       # import → dispatch → review → metrics
```

- Python **3.11–3.12**; PostgreSQL **16**
- `make check` ≠ full CI
- Legacy Vite frontend on `:5173` — **not in compose**; proxy defaults to `:8000` (compose API is `:8080` — documented fix in hosted guide)

**Suitable for:** backend engineering and stakeholder synthetic demos (with manual UI + tunnel setup), not institutional pilot.

### Self-hosted pilot (not ready)

| Gap | Impact |
|-----|--------|
| Compose stack incomplete | No IdP, no frontend service (`P-COMPOSE-PILOT` not merged) |
| No institutional IdP | Login is fixture bearer / legacy fallback identities |
| No deployed dispatcher scheduler (J8) | Compose scheduler covers local dev only |
| Core pilot features missing | Matching scores, rewards redemption, events list, outreach; pipeline production writers |
| Product UI | Legacy authorized for synthetic click-through; new product UI on hold |

---

## 4. Cloud deployment

### Intended (Architecture v1.1)

GCP: **Cloud Run** (API + worker), **Cloud SQL** (Postgres 16), **Cloud Tasks**, **Cloud Scheduler**, **Secret Manager**. Four isolated projects: dev, staging, classroom, prod. First cloud target when F5 lands: **classroom** (`docs/decisions/f5-deploy-target-note-2026-09-03.md`).

### Reality (2026-09-04)

| Item | Status |
|------|--------|
| `Dockerfile.api` / `Dockerfile.worker` | Built and probed in CI; **no registry push** |
| `docker-compose.yml` | Local dev / CI smoke only |
| Terraform | Placeholder `locals` only in four env skeletons — **no provider, backend, resource, or module** |
| `ALLOW_CLOUD_DEPLOY=false` | Orchestrator contract gate (`docs/migration/orchestrator-run.md`); not an env toggle |
| Worker OIDC (S-001) | Verifier logic exists; no signature backend → refuses live delivery outside dev bearers |
| Cloud Tasks adapter | Not implemented — `FixtureTaskQueue` + local loopback queue only |
| Monitoring / on-call | Design only — nothing running |

**Documented workaround (not F5):** GCE VM + `docker compose` + Cloudflare Tunnel + Access (`classroom-vm-cloudflare-tunnel.md`); still `SMARTMATCH_EDITION=dev`, still `ALLOW_CLOUD_DEPLOY=false`.

**Minimum path to classroom cloud pilot:** F5 Terraform → Artifact Registry + CI push → Cloud SQL/Run/Tasks/Scheduler → S-001 OIDC → migrations per deploy runbook → IdP (P2) → product scope decision.

---

## 5. Plan portfolio (P1–P9) gate status

Index: `docs/plans/2026-08-28-plan-portfolio-index.md`

| Plan | Topic | Status (2026-09-04) |
|------|-------|---------------------|
| P1 | Metrics authz | **CLOSED 2026-09-02** — **V4 implemented** |
| P2 | Institutional sign-in | EXTERNAL DEPENDENCY — tenant exists; worksheet Part 1 unfilled |
| P3 | ADR-0011 coercion cleanup | **Complete** |
| P4 | Performance/caching | Stage 0+1 **complete** |
| P5 | G1 matching M1–M10 | **G1 CLOSED 2026-09-03** — registry approved; **M2–M10 not started** |
| P6 | G3 events S3–S5 | G3 signed; **R3 signed 2026-09-03**; Stage 0 parsers + wrapper only |
| P7 | D6/D7 rewards | D6 **closed** (pilot scope); D7 tentative; schema only |
| P8 | Opportunities S12 | **CLOSED 2026-09-02** — **O1–O3 implemented**; production writers open |
| P9 | Pilot columns | Gate A **CLOSED**; Gate B **CLOSED**; **W1 column contract wired** |

### Post-ratification engineering slices (V1–V8)

| Order | Slice | Status |
|-------|-------|--------|
| R0 | Ratification | **Complete** |
| V1 | ADR-0015 A1 spend | **Complete** (synthetic) |
| V2 | P9 pilot columns | **Largely complete** |
| V3 | P6 event discovery | Parsers + contact-free wrapper (fixture-only) |
| V4 | P1 metrics authz | **Complete** |
| V5 | P8 opportunities | **Complete** — O1–O3 |
| V6 | P7 rewards | D6 closed — schema checks + formal record |
| V7 | P2 sign-in | Tenant exists — worksheet Part 1 |
| V8 | P5 matching | **G1 closed** — M2+ authorized |

### Pilot decisions D1–D9 (summary)

| # | Status |
|---|--------|
| D1 | **CLOSED 2026-09-03** (G1 registry) |
| D2 | Tentative — ELI params stand; committed-future-engagements sub-question open |
| D3 | Deferred — no route-matrix provider |
| D4 | Deferred — DNS/domain out of pilot scope |
| D5 | Dev retention in synthetic authorization; production periods open |
| D6 | **CLOSED 2026-09-02** (pilot scope) — $5k placeholder |
| D7 | Tentative — earn rates/bands recorded |
| D8 | Tentative — minimum-disclosure; no FERPA compliance claim |
| D9 | **CANNOT CLOSE** — private pilot; non-blocking for private engineering |

---

## 6. Pilot readiness checklist

| Criterion | Ready? |
|-----------|--------|
| Deployable to real users | **No** |
| Real institutional sign-in | **No** — fixture tokens |
| Trustworthy matching scores | **No** — registry approved; **no scorer** |
| Honest coordinator metrics | **Mostly** — review queue, pipeline funnel, opportunities measured from storage (zeros until writers) |
| Import pilot CSV (`columns.yaml`) | **Yes** — worker enforces contract |
| Coordinator review decisions via API | **Yes** |
| Rewards students can redeem | **No** |
| Event discovery | **No** — parsers + wrapper only |
| Outreach | **No** |
| Live student data (D8) | **No** — synthetic only |
| Stakeholder synthetic click-through | **Partial** — compose + manual Vite + tunnel docs |
| Engineering quality bar | **High** |

---

## 7. Feature completeness (approximate)

```
Auth (A1b)              ████░░░░░░  ~40%
Import/quarantine       █████████░  ~85%
Metrics/dashboard       ████████░░  ~75%  (O3 bound; production writers open)
Matching (G1 registry)  ███░░░░░░░  ~25%  (approved registry; no scorer)
Matching (scores)       █░░░░░░░░░  ~10%  (M2–M3)
Opportunities (P8)      ██████░░░░  ~55%
Events/crawler (G3)     ████░░░░░░  ~30%  (policy signed; no runtime)
Rewards (D6/D7)         ██░░░░░░░░  ~15%
Outreach (G4)           ░░░░░░░░░░   0%
Frontend (legacy synth) ███░░░░░░░  ~25%
Frontend (new product)  █░░░░░░░░░  ~10%
Deploy packaging        ██████░░░░  ~55%  (compose + CI smoke; F5 open)
```

---

## 8. Highest-leverage blockers

### Human / institutional (parallel)

1. **P2 A1b worksheet Part 1** — IdP tenant exists; issuer/JWKS/client fields pending
2. **D8 institutional privacy review** — before any live student data
3. **D9 licensing** — CANNOT CLOSE; archive-history exposure (Q1)
4. **Institutional funding confirmation** — D6 $5k placeholder

### Engineering (ordered by leverage)

| ID | Item | Notes |
|----|------|-------|
| **M2–M3** | Factor implementations + scoring engine | G1 unblocks this; longest product pole |
| **S12 writers** | Wire `PipelineRepository` to production paths | Repository + tests exist; no route/handler calls it |
| **F5** | Terraform modules (classroom first) | Skeleton only; blocks cloud pilot |
| **S-001** | Worker OIDC signature backend | Cloud Tasks/Scheduler cannot authenticate without dev bearers |
| **A1b** | Live JWKS verifier for API | Fixture only today |
| **P-COMPOSE-PILOT** | Frontend in compose | Stakeholder demo friction |
| **J8 external** | Cloud Scheduler job provisioning | Compose sidecar covers local only |
| **S6a** | Crawler runtime | R3 signed; implementation card open |

---

## 9. Local vs cloud comparison

| Concern | Local dev | Local pilot (appliance) | Cloud pilot (GCP) |
|---------|-----------|---------------------------|-------------------|
| Setup | Makefile + Postgres or compose | Medium (compose + manual Vite + tunnel) | High (F5 + GCP) |
| Auth | Fixture tokens | Needs IdP (P2) | Identity Platform |
| Worker/dispatcher | Manual or compose + scheduler | Compose scheduler | Cloud Tasks + Scheduler + OIDC |
| Product features | Same gaps | Same gaps | Same gaps |
| Ops | Engineer | Engineer + tunnel/VM ops | GCP + team |
| **Readiness** | **Today** | **Weeks** (ops docs exist) | **Months** |

Cloud vs local is primarily an **ops choice** once the same product slices exist; both are equally unprepared for end-user pilot with live student data today.

---

## 10. Doc-sync drift (CP-DOCSYNC)

| Doc | Drift |
|-----|-------|
| `docs/decisions/2026-08-31-session-ratification.md` | **Stale vs 09-03 closures.** Matrix still lists P5 G1 as RECORDED — GATE INCOMPLETE and R3 as unsigned; superseded by `pilot-decisions.md` and `r3-signing-decisions-2026-09-03.md` |
| `docs/decisions/pilot-decisions.md` L357 | Says OpenAPI has **seven** operations; verified **11** |
| `docs/decisions/pilot-decisions.md` D7 § | Says "no points ledger" in code; migration `0009` + `point_ledger_entry` table exist (behavior/routes still absent) |
| `apps/web/DESIGN.md` | Says OpenAPI describes "**seven** endpoints"; verified **11** |
| `apps/web/legacy-frontend/` | UI copy still cites `REGISTRY_STATUS` as `"proposed"` (`AIMatching.tsx`, `Volunteers.tsx`, `api.ts`, etc.) |
| `docs/plans/prep/blocked-work-register-830.md` | P5 row still workshop-pending; superseded by G1 closure 2026-09-03 |
| `docs/plans/orchestrator-handoff.md` | Still references `REGISTRY_STATUS == "proposed"` |
| `tests/unit/test_gate_decision_artifacts.py` | Expects G1 packet "unapproved prep" text; worksheet ratified 2026-09-03 |
| `tests/golden/matching/symptoms/G1-GC-*.json` | Descriptions still say "NOT RATIFIED"; no expected scores in fixtures |
| `docs/status-report/README.md` | Index pointed at 2026-09-02 report; updated by this report |
| `README.md` suite totals | Still a labelled floor (~1,817); static count ~1,394; not re-collected locally 2026-09-04 |
| `README.md` G1 / matching rows | **Accurate** — registry approved; scoring unimplemented (M2–M3) |
| `README.md` migration count | **Drift** — capability table does not mention head `0015` or compensating `0014`/`0015` ledger reversal sequence |
| Prior report (2026-09-02) | Stated head `0013`, G1 blocked, R3 unsigned — superseded by this report |

---

## 11. Key reference paths

| Topic | Path |
|-------|------|
| Honest capability table | `README.md` |
| Session ratification | `docs/decisions/2026-08-31-session-ratification.md` |
| Pilot decisions D1–D9 | `docs/decisions/pilot-decisions.md` |
| G1 closure worksheet | `docs/plans/workshops/g1-workshop-output-worksheet.md` |
| R3 signing record | `docs/decisions/r3-signing-decisions-2026-09-03.md` |
| Synthetic pilot authorization | `docs/decisions/synthetic-pilot-development-authorization-2026-09-03.md` |
| Hosted demo guide | `docs/operations/hosted-synthetic-pilot-guide.md` |
| Classroom VM + tunnel | `docs/operations/classroom-vm-cloudflare-tunnel.md` |
| F5 deploy target | `docs/decisions/f5-deploy-target-note-2026-09-03.md` |
| Plan portfolio | `docs/plans/2026-08-28-plan-portfolio-index.md` |
| Blocked-work register | `docs/plans/prep/blocked-work-register-830.md` |
| Deploy runbook | `docs/operations/deploy-runbook.md` |
| Containers / compose | `docs/operations/containers.md`, `docker-compose.yml` |
| Factor registry | `python/smartmatch_domain/smartmatch_domain/factor_registry.py` |
| Fail-closed contracts | `tests/unit/test_matching_fail_closed.py` |
| Migration head | `db/migrations/versions/0015_remove_unauthorized_ledger_reversal.py` |
| OpenAPI contract | `contracts/openapi/smartmatch.json` (11 paths / 11 operations) |
| Prior report | `docs/status-report/2026-09-02-audit-status-report.md` |

---

*End of audit-status report.*
