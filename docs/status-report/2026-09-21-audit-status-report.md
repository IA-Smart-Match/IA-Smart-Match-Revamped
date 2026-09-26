# Audit-status report — 2026-09-21

**Repository:** IA SmartMatch Revamped (`IA-Smart-Match-Revamped`)
**Report type:** Pilot readiness audit (self-hosted vs cloud) + class-exercise track
**Prepared:** 2026-09-21
**Posture:** Foundation scaffold — **not production-ready**; one synthetic pilot VM runs; class exercise approaching Oct 2026 milestones; synthetic data only for CBA

**Authoritative blocker index:** `docs/decisions/2026-08-31-session-ratification.md`
**Continuation order:** `docs/archive/plans/2026-08-31-ratification-and-implementation-report.md` (V1–V8)
**Planning navigation:** `docs/plans/README.md`
**Owner decision queue:** `docs/archive/plans/owner-open-decisions-2026-09-19.md` (21 open, 8 decided)

This report decides nothing and fills no owner field.

**Verification note:** Facts below were checked against the tree on 2026-09-21. **Merged authority is `origin/main` at `468ba755`** (includes PRs through #190: exercise results API, crawl-route guard, matching API). The checked-out local `main` is **71 commits behind** that tip (stops at PR #179 ingest merge). Many local feature branches exist; most track already-merged work (`origin/…: gone`) while a handful still carry unpushed commits (e.g. `docs/exercise-hosting`, `feat/exercise-mount-components`, `refactor/exercise-instructor-session`). Local `pytest --collect-only` was **not** completed: collection aborted on `test_adr_index.py` (adr-backlog drift on this checkout). OpenAPI and migration counts were verified statically. CI on Ubuntu + PostgreSQL 16 remains authoritative for pass/fail.

**Doc-sync drift (critical):** Root `README.md` on `origin/main` is still the capability truth table but records **36 migrations / head `0036_host_organization`**; the tree now has **37 revisions**, head **`0037_exercise_tables`**. Locally, `README.md` is **modified and overwritten with unrelated Gitleaks content** — do not treat the working copy as authority; use `git show origin/main:README.md` until restored.

---

## Executive summary

| Dimension | Status | Notes |
|-----------|--------|-------|
| **Backend foundation** | **Strong** (~90% R1 scaffold) | 37 migrations; 66 OpenAPI paths / 83 operations; CBA matching live over HTTP; pipeline stage writers; rewards/attendance/student-events surfaces; deny-by-default authz; compose + CI smoke |
| **CBA pilot product** | **Moderate** (~55–65%) | Match runs, coordinator surfaces, fixture outreach, metrics bound — but live OIDC, live send, crawler runtime, CP-SAT, new frontend, and several student-program slices remain gated |
| **Class exercise product** | **Substantial code, decision-blocked deploy** | Second `ProductScope` (`class_exercise`); 8 `exercise_*` tables; ingest, matching, simulation, workspace, results APIs and legacy-frontend pages largely merged through #190 — **21 owner decisions open**, Oct 2 / Oct 16 milestones at risk |
| **Local dev self-host** | **Available** | `make setup` + PostgreSQL 16 + migrate + run-api/worker; or `docker compose` dev appliance |
| **Self-hosted pilot appliance** | **Partial — CBA VM exists** | GCE VM + Cloudflare tunnel at `pilot.plated.blog`; deploy script takes `pg_dump` before migrate; **no bundled IdP**; exercise host proposed at `exercise.plated.blog` (docs branch, not confirmed deployed) |
| **Cloud pilot** | **Not started** | Terraform skeleton; images build in CI, not pushed; `ALLOW_CLOUD_DEPLOY=false`; Supabase ticket drafted, **not executed** |

**Bottom line:** Since the 2026-09-04 report, the repository crossed a major product pivot: **CBA matching is implemented and HTTP-reachable** (registry `2.0.0-approved-oq-cba-004`, four factors, `POST …/match-runs`), and a **parallel class-exercise module system** now shares the matching mechanism without sharing data (ADR-0025). Foundation remains a credible private engineering platform with a **compose-verified synthetic pilot on a VM**. It is still **not** an institutional self-service pilot: live OIDC (P2/A1b), F5 cloud packaging, student-program W-series work, and most OQ-CE owner inputs are unresolved. **Supabase** exists only as a planning ticket — managed Postgres backups are not wired. Local branch topology shows heavy parallel exercise development with **most work merged on GitHub** but **this workstation's `main` lagging 71 commits**; treat `origin/main` as the audit baseline.

---

## 0. Repository and branch posture (2026-09-21)

| Signal | Value |
|--------|-------|
| Merged tip | `origin/main` → `468ba755` (PR #190 exercise-results-api) |
| Local `main` | `38f3e4be`, **behind 71** |
| OpenAPI | **66 paths / 83 operations** (all carry `operationId`) |
| Migration head | **`0037_exercise_tables`** (37 revisions) |
| Factor registry | `REGISTRY_STATUS = "approved"`; version **`2.0.0-approved-oq-cba-004`** |
| Untracked / local-only docs | `docs/archive/plans/owner-open-decisions-2026-09-19.md`, fable orchestrator handoffs, `LICENSE` |

**Branch landscape:** Dozens of local `feat/exercise-*`, `docs/*`, and `fix/*` branches exist. Pattern: feature branches merged to GitHub show `[origin/…: gone]`; remaining remotes with ahead commits suggest **unpushed follow-up** (mount components, instructor-session refactor, exercise hosting doc). This is consistent with "leading most local branches" — local tips ahead of stale or deleted remotes — while **canonical merged history lives on `origin/main`**, not on the lagging local `main`.

---

## 1. Product intent and release train

**Two parallel products** share infrastructure but not data:

1. **CBA** (`ProductScope.CBA`) — Cal Poly Pomona speaker/event matching (current pilot).
2. **Class exercise** (`ProductScope.CLASS_EXERCISE`) — Spring 2027 classroom simulation (Ann Wang); no-login, synthetic profiles, separate `exercise_*` schema (ADR-0025 D2).

```
Foundation → R1 → R2 → R3 → R4 → R5
              G1✓   G2    G3†   G4,G5

Parallel: Class exercise (CE-*) → Oct 2 site / Oct 16 results / Nov 20 deliverable
```

| Gate | Blocks | Status (2026-09-21) |
|------|--------|---------------------|
| **G1** | Factor registry + golden cases | **CLOSED** (2026-09-03 G1; superseded by CBA registry 2026-09-05 ADR-0016) |
| **G2** | Privacy/records for live data | Open — D8 tentative; synthetic-only posture |
| **G3** | Agent eval, allowlist, cost controls | R3 signed 2026-09-03; **no crawl runtime** |
| **G4** | Consent-origin, deliverability | Fixture outreach shipped; **live send blocked** (OQ-001–003) |
| **G5** | Calendar authorization | ICS download only; no live Calendar API |

**Class exercise milestones (owner doc):** Oct 2 matching on public site; Oct 16 results with lock/compare; Nov 9 practice run; Nov 20 deliverable. Blocked by OQ-CE-01–07 and VM secrets (see §8).

---

## 2. What is implemented

### Backend and data plane (CBA + shared)

| Area | Status |
|------|--------|
| Domain primitives (ELI, ICS, consent, jobs, ingest, feedback) | Implemented + tested |
| CBA factor registry | **Approved** — four implemented factors; G1 pair retired-in-version but reproducible at `1.1.1-approved-g1-m6j` |
| CBA scoring | **`POST /v1/units/{unit_id}/match-runs`** via `rank_cba_candidates`; modes `cba-virtual-1` / `cba-physical-1`; ZIP-centroid proximity (CA only) |
| Deny-by-default authz | Implemented |
| PostgreSQL schema | **37 migrations** (`0001`–`0037`); ~49+ tables in persistence mirror |
| Pipeline funnel writers | Matched (review accept), Contacted (outreach), Confirmed/Attended/Member Inquiry (coordinator route) |
| Metrics (P1) | All three owning queries bound to storage |
| Student events + registration + calendar ICS | Implemented |
| Attendance + rewards ledger + redemption | Implemented (synthetic catalog content) |
| Outreach | End-to-end **fixture** provider; live send refused |
| Manual events + feedback QR | Implemented |
| Command path + `job.payload` (J10) | Closed |
| Container images + CI | Build, health, SIGTERM; compose-smoke |
| Pilot VM | GCE + tunnel; `scripts/vm/deploy.sh` backs up before migrate |

### Class exercise module system (new since 09-04)

| Layer | Status | Notes |
|-------|--------|-------|
| **Product scope** | Implemented | `ProductScope.CLASS_EXERCISE`, `Capability.CLASS_EXERCISE`; API + `productScope.ts` read shared policy |
| **Schema** | Migration `0037` | Eight `exercise_*` tables; **no `tenant_id`**; FKs stay inside exercise family (ADR-0025 D2) |
| **Domain** | Implemented | `smartmatch_domain/exercise/`: ingest, layout (PLACEHOLDER OQ-CE-01), matching, reasons, simulation (`require_coefficients()` fail-closed), workspace tokens, asking, markers, determinism |
| **Persistence** | Implemented | `smartmatch_persistence/exercise/`: schema mirror, dataset + workspace repositories |
| **API** | Largely merged through #190 | `/v1/exercise` public + workspace routers; instructor passcode routes; matching + results APIs on `origin/main` |
| **Frontend** | Partial | Legacy-frontend exercise pages: profile card mock-up, results chart, points counter, list-coverage notice; mount/routing tracks still landing |
| **Tests** | Extensive | 20+ exercise test modules (unit, golden, integration); results-router suite on `origin/main` |

**Isolation guarantees:** Exercise paths gated by capability; CBA tables not read from exercise code; `/u/` and `/i/` token routes excluded from exercise scope (#176).

### Partially complete

| Area | State |
|------|-------|
| CP-SAT / Stage A eligibility | Not started (M6–M7) |
| Live OIDC | Fixture tokens only; A1b worksheet Part 1 open |
| Crawler | Signed threat model; no runtime |
| New `apps/web` frontend | On hold; legacy authorized for synthetic pilot + CBA coordinator/volunteer surfaces |
| Student engagement program (W1–W4) | Plans + ADR-0024/0026; **W4 STOPPED** pending OQ-SE-04–08 |
| Class exercise deploy | Code path exists; **VM secrets, hostname, coefficients, column layout** open |
| Supabase managed Postgres | Ticket only (`docs/plans/2026-09-14-supabase-migration-ticket.md`); no `docs/operations/supabase-setup.md` |

### Blocked or absent

| Area | Blocker |
|------|---------|
| Live email send | OQ-001–003, provider tenant |
| Live Calendar sync | G5 |
| Production cloud deploy | F5, `ALLOW_CLOUD_DEPLOY=false` |
| Real student data | D8, G2, institutional sign-off |
| Speaker invitation accounts (backlog) | Phase two; OQ-SE-09/10 |

---

## 3. Self-hosted: local dev vs pilot appliance

### Local developer self-host (today)

```bash
make setup && make db-up && make migrate
make run-api    # :8000
make run-worker # :8001
```

Docker alternative: `docker compose up --build -d` (db, migrate, seed, api, worker, scheduler) — **dev edition only** (`SMARTMATCH_EDITION=dev`).

For **class exercise** locally: set `SMARTMATCH_PRODUCT_SCOPE=class_exercise` plus exercise secrets (`SMARTMATCH_EXERCISE_WORKSPACE_SECRET`, instructor passcode, cookie Secure flag) per `.env.example`.

### Pilot appliance gaps

| Have | Missing for full pilot |
|------|------------------------|
| Compose backend on VM | Institutional IdP (P2) |
| Synthetic seed + pilot logins | Live OIDC worker verifier |
| Cloudflare tunnel to VM | Bundled frontend in compose |
| Pre-migrate `pg_dump` on deploy | Supabase/off-site backup automation (ticket drafted) |
| CBA surfaces on legacy frontend | New frontend (D-0) |

**Exercise appliance:** Recommended pattern is **separate process/scope** on pilot VM (`exercise.plated.blog` per `docs/exercise-hosting` branch) with **only** `CLASS_EXERCISE` routers — not confirmed production-deployed in this audit.

---

## 4. Cloud deployment

| Item | Intended | Actual (2026-09-21) |
|------|----------|---------------------|
| GCP / Terraform F5 | Environment skeletons | **Not applied** |
| Container registry | CI builds images | **No push** |
| Cloud SQL / managed Postgres | Supabase or Cloud SQL | **Local Docker + VM Postgres only**; Supabase SOP **not committed** |
| Cloud Scheduler + Tasks | Worker OIDC delivery | **Local scheduler sidecar in dev compose only** |
| `ALLOW_CLOUD_DEPLOY` | false | **false** — standing constraint |

**Supabase migration ticket status:** Scope is managed Postgres only (no PostgREST/Auth/RLS). Acceptance: `alembic upgrade head`, drift test, integration suite against Supabase URL, committed runbooks. **None of the acceptance artifacts exist yet** — engineering backlog item, not a blocker for class-exercise VM path.

---

## 5. Plan portfolio (P1–P9) and continuation (V1–V8)

| Id | Summary | Gate status (2026-09-21) |
|----|---------|--------------------------|
| **P1** Metrics authz | **Implemented** (O3 binding, Option B drill-down) |
| **P2** Institutional sign-in | **Blocked** — fixture auth; A1b IdP worksheet Part 1 |
| **P3** ADR-0011 zero coercion | In progress / partial per frontend inventory |
| **P4** Performance caching | Stage 0–1 available; Redis absent |
| **P5** G1 matching M1–M10 | **M1 closed**; CBA factors shipped; **M7–M10 (CP-SAT, explanations) not started** |
| **P6** Events / crawler | Parsers + schema; **no live crawl** |
| **P7** Rewards | Routes + ledger; **live catalog content gated** |
| **P8** Opportunities metric | **O3 bound** |
| **P9** Pilot columns | Gates A/B closed 2026-09-02; `columns.yaml` enforced |

**V-series (ratification continuation):** V1–V3 largely delivered in foundation; V4 metrics done; V5 opportunities bound; V6–V8 (pipeline honesty, outreach, calendar) partially advanced — pipeline writers landed; outreach fixture-complete; calendar remains ICS-only.

---

## 6. Pilot readiness checklist

| Requirement | Self-hosted CBA pilot | Class exercise (Spring 2027) | Cloud pilot |
|-------------|----------------------|------------------------------|-------------|
| Institutional sign-in | **No** (fixtures) | N/A (no-login) | **No** |
| Pilot import + `columns.yaml` | **Yes** (synthetic) | **Partial** (PLACEHOLDER layout) | N/A |
| Trustworthy matching | **Yes** (CBA HTTP) | **Yes** (domain); **coefficients block results** | Same as self-hosted |
| Opportunities metric | **Yes** (bound) | N/A | N/A |
| Honest coordinator metrics | **Yes** | N/A | N/A |
| Rewards (**mandatory** pilot) | **Yes** (synthetic; see §6a) | N/A | N/A |
| Crawler (optional) | **No** | N/A | **No** |
| D8 before real student data | **Not met** | N/A (no real students) | **Not met** |
| Frontend | Legacy synthetic | Legacy exercise pages | N/A |
| Managed DB backups | VM deploy dump only | Same | **No** (Supabase not wired) |
| Deployed & reachable | **VM yes** (CBA) | **Blocked** (hosting decisions) | **No** |

### 6a. Pilot-readiness run, 2026-09-21 evening — row status after PRs #196–#204

The table above is the audit as written. This one is the same rows after the
pilot-readiness orchestrator run. `origin/main` = `012080f1` (#205 merged), migration head
`0037_exercise_tables` (unchanged), OpenAPI 84 operations (was 83).

| Requirement | Status now | Evidence | What is still open |
|-------------|-----------|----------|--------------------|
| Institutional sign-in | **DEFERRED** (owner) | No P2/A1b file in any PR of this run | Pilot has no IdP; fixture auth stays |
| Pilot import + `columns.yaml` | **Yes** (CBA, synthetic) · **Partial** (exercise) | `pilot e2e` CI job generates the dataset and walks the columns-contract step on every PR (#198, #202) | `make verify-pilot-dataset` was not run by hand this run — no seeded database on the dev machine. Exercise layout stays PLACEHOLDER until OQ-CE-01 |
| Trustworthy matching | **Yes** | 41 passed: `tests/contract/test_match_runs_api.py` + `test_metrics.py`; 160 passed: exercise matching + router + opportunities contract (run on `73836b3c`) | Exercise coefficients are placeholders (OQ-CE-03/04, Ann/Chau) |
| Opportunities metric | **Yes** | Included in the 160 above (`test_frontend_opportunities_contract.py`, `test_opportunity_category_shape.py`) | — |
| Honest coordinator metrics | **Yes** | `tests/contract/test_metrics.py` in the 41 above; policy matrix green in CI | — |
| Rewards (**mandatory** this pilot) | **Yes** (synthetic) | #198 seed wired into `pilot-e2e` + docs; #202 `SMARTMATCH_E2E_REQUIRE_REWARDS=true` makes a reward skip fail CI — job log: `requested and decided redemption … (300 pts) -> approved`; #200 coordinator queue `GET /v1/units/{unit_id}/redemptions/queue`, rows scoped to the unit's `student` memberships | Catalog values are `TENTATIVE (pilot-decisions.md)`; D6/D7 registers not closed. Coordinator queue page shipped in #205 (`/coordinator-portal/redemptions`). `decide_redemption` by id stays tenant-scoped (owner-acknowledged) |
| Crawler | **DEFERRED** (owner) | No crawl handler/router PR in this run | G3 signed; no runtime |
| D8 before real student data | **Not met** — PARTIAL by design | Synthetic pilot only | No real student data goes in anywhere, including Supabase staging |
| Frontend | **Yes** (CBA synthetic + exercise screens) | CE-MOUNT #194; review fixes #196 + #201 (refused weight commit no longer becomes the next base; serialized commits; StrictMode reload fix); #199 copied-card goal | 2 LOW follow-ups on `WeightsControls` (queued edit dropped on unmount is undocumented; one avoidable no-op request). Original G4 named 5 vacuous tests — 1 was identifiable, re-review found no others |
| Managed DB backups | **Partial** | #197 `docs/operations/supabase-setup.md`, `supabase-maintenance.md`, `.env.example` — 3 of 6 ticket criteria met | The other 3 criteria need a real Supabase project: `alembic upgrade head`, the schema-drift test and `make test-integration` against it. None exists |
| Deployed & reachable | **VM yes** (CBA) · **Ready, operator run pending** (exercise) | #203 deploy-and-verify checklist (`docs/operations/exercise-hosting.md` §9); #204 `docker-compose.exercise.yml` (`api-exercise`, `127.0.0.1:8090`, profile `exercise`) — parsed by the real Compose CLI in the `compose-smoke` job | #204 merged. Nobody has run the checklist on the VM; Cloudflare hostname + WAF rate-limit rule are dashboard-side |

---

## 7. Feature completeness (approximate)

| Surface | ~Complete | Notes |
|---------|-----------|-------|
| R1 foundation scaffold | **90%** | F2b SBOM, F5 Terraform, F12/F13 governance gaps |
| CBA coordinator workflow | **60%** | Match runs, imports, review, metrics, pipeline |
| CBA student workflow | **45%** | Events/agenda/registration; no recommender/digest |
| Class exercise | **70% code / 30% deploy-ready** | Owner inputs + VM config gate |
| Student engagement program | **15%** | Documentation authority; W4 stopped |
| Cloud operations | **5%** | VM only |

**Tests:** README floor **1,817** collected (predates Sep slices); exercise suite adds **~350+** functions in local tree; `origin/main` adds further results-router tests. Treat counts as **floor**, not current green run.

---

## 8. Highest-leverage blockers

### Human / owner (ordered)

1. **OQ-CE-01 / Ann sample** — column layout; blocks ingest on real file (owner-open-decisions #8).
2. **VM exercise secrets + hostname** — workspace secret, cookie Secure, DB role on `exercise_*` only, stable URL (#1–2, #15–17 in owner-open-decisions).
3. **OQ-CE-03 simulation coefficients** — eight values; `require_coefficients()` raises until set (#5; Chau + Ann).
4. **P2 / A1b live IdP** — blocks real institutional CBA pilot login.
5. **D8 disclosure consent** — blocks real student attendance visibility.
6. **F5 + Supabase decision** — plan tier, dev-vs-staging DB story (ticket open questions).
7. **Student program OQ-SE-04–08** — unblocks W4 recommender track.

**Consolidated queue:** `docs/archive/plans/owner-open-decisions-2026-09-19.md` — **5 "do now"** for Danny, **Ann message** unblocks six rows, **Chau message** unblocks coefficients/weights/points.

### Engineering backlog (selected)

| Item | Notes |
|------|-------|
| **J8/J9** | Dispatcher code done; external Cloud Scheduler wiring open |
| **A1b** | Live JWKS verifier |
| **S12 production callers** | Pipeline repo now has writers; creation path + RSVP source open (OQ-101/102) |
| **M7–M10** | CP-SAT, explanations, scenario compare |
| **F5** | Terraform environments |
| **W-series** | Student recommender gated on registers |
| **Supabase ticket** | Setup + maintenance SOPs |
| **CE-MOUNT / frontend** | Exercise UI mount on public host |
| **Doc sync** | README migration count; restore corrupted local README |

### Backlog parking lot (`docs/plans/backlog.md`)

Not scheduled: invitation-only speaker accounts, exercise "nice-to-have" UI (projector chart, list notice, points counter as product polish), AMP governance adapter, Handshake source, native mobile.

---

## 9. Local vs cloud comparison

| Concern | Local dev | VM self-hosted | Cloud (intended) |
|---------|-----------|----------------|------------------|
| Postgres | Docker 16 | Container on GCE | Supabase / Cloud SQL (planned) |
| Migrations | `make migrate` | `deploy.sh` + alembic | Same; forward-only (ADR-0009) |
| Auth | Fixture tokens | Fixture / pilot logins | OIDC + workload identity (not wired) |
| Product scope | Env switch | Per-deployment env | Per-service env |
| Backups | Manual | Pre-deploy `pg_dump` | Supabase tier + off-site dump (planned) |
| CI truth | `verify.yml` + compose-smoke | Promote workflow | N/A |
| Cost / ops | Developer machine | Single VM + tunnel | F5 blocked |

---

## 10. Key reference paths

| Purpose | Path |
|---------|------|
| Capability truth table | `README.md` on **`origin/main`** (not corrupted local copy) |
| Planning index | `docs/plans/README.md` |
| Class exercise requirements | `docs/product/class-exercise-requirements.md` |
| Class exercise design | `docs/superpowers/specs/2026-09-16-class-exercise-design.md` |
| ADR-0025 scope isolation | `docs/architecture/decisions/ADR-0025-class-exercise-scope-shares-the-matching-mechanism.md` |
| OQ-CE register | `docs/plans/open-questions/class-exercise-open-questions.md` |
| Owner decisions (21) | `docs/archive/plans/owner-open-decisions-2026-09-19.md` |
| CBA deferred register | `docs/plans/open-questions/cba-phase-deferred.md` |
| Student engagement register | `docs/plans/open-questions/student-engagement-deferred.md` |
| Supabase ticket | `docs/plans/2026-09-14-supabase-migration-ticket.md` |
| Backlog parking lot | `docs/plans/backlog.md` |
| Deploy runbook | `docs/operations/deploy-runbook.md` |
| VM deploy | `docs/operations/vm-deploy.md` |
| Product scope policy | `python/smartmatch_domain/smartmatch_domain/product_scope.py` |
| Exercise domain | `python/smartmatch_domain/smartmatch_domain/exercise/` |
| OpenAPI contract | `contracts/openapi/smartmatch.json` |
| Prior audit | `docs/status-report/2026-09-04-audit-status-report.md` |

---

*End of audit-status report.*
