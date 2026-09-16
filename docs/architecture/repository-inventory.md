# Repository Inventory

**Stage 0 — Repository Discovery.** Produced by the Opus architecture audit,
2026-09-08, against commit `c72dced` on branch
`claude/repository-architecture-audit-y9g2un`.

Classification vocabulary used throughout the audit set: **OBSERVED** (direct
repository evidence), **INFERRED** (conclusion from several observations),
**RISK**, **RECOMMENDATION**, **UNKNOWN**.

---

## 1. Identity

| Fact | Value | Evidence |
|---|---|---|
| Project | SmartMatch platform monorepo | `pyproject.toml` `[project].name = "smartmatch-platform"` |
| Version | `0.1.0` ("Foundation scaffold, architecture v1.1") | `pyproject.toml` |
| Product scope (default) | `CBA` — Cal Poly Pomona College of Business Administration speaker/event matching | `python/smartmatch_domain/smartmatch_domain/product_scope.py:101` |
| Prior scope, retained | `IA_WEST_LEGACY` | `product_scope.py:83-97` |
| Agent-memory ledger id | `f943437b-6a8f-47fe-9c0d-478988b70d9a` | `.agent-memory.yaml` |
| Commits on `main` | 312, all dated 2026-09-05 → 2026-09-08 | `git log` |

**OBSERVED.** Git history spans four calendar days but the documentation set
references planning artifacts dated 2026-08-28 onward
(`docs/plans/2026-08-28-*`). The visible history is therefore **not** the full
development history — it was re-based, squashed, or imported at 2026-09-05.

**Consequence for this audit:** `git log` is usable for *recent* intent
(what changed this week) but **cannot** be used to distinguish "deliberate
architecture" from "unfinished transition" for anything older. Where the audit
needed that distinction it used the documentation set and the code itself.
See `wip-analysis.md` §6.

---

## 2. Languages, runtimes, toolchain

| Concern | Choice | Evidence |
|---|---|---|
| Backend language | Python `>=3.11,<3.13` | `pyproject.toml`, `.python-version` |
| Frontend language | TypeScript 5.6, React 18.3 | `apps/web/legacy-frontend/package.json` |
| Node runtime | `>=20` | `package.json` `engines`, `.nvmrc` |
| Package manager (Python) | `uv` workspace; `pip-tools` for hash-pinned locks | `[tool.uv.workspace]`, `requirements/*.in|.txt`, `Makefile: lock` |
| Package manager (web) | `npm` (`lockfileVersion 3`) | `package-lock.json`, CI `npm ci` |
| Build (web) | Vite 6 + Tailwind 4 | `package.json` `build: tsc --noEmit && vite build` |
| Lint / format | `ruff` (E,F,I,UP,B,SIM,RUF), line length 100 | `[tool.ruff]` |
| Types | `mypy --strict` over `python/` **and** `services/` | `[tool.mypy]`, `verify.yml` |
| Architecture enforcement | `import-linter` ≥2.1, 4 contracts | `[tool.importlinter]` |
| Tests | `pytest` 8.3 + `pytest-cov`; `node --test` for web | `[dependency-groups].dev`, `package.json` |
| Migrations | Alembic, 33 revisions | `db/migrations/versions/` |
| Containers | Docker, two images (`Dockerfile.api`, `Dockerfile.worker`) | repo root |
| IaC | Terraform ≥1.6, GCP-shaped | `infra/terraform/` |

---

## 3. Workspace topology

`pyproject.toml` `[tool.uv.workspace].members` declares six members. The audit
found a seventh source root (`tools/`) that is *not* a workspace member but is
on the pytest path.

```
smartmatch-platform (root, not itself a package)
├── python/smartmatch_domain        pure domain      40k LOC total across python/
├── python/smartmatch_authz         pure policy
├── python/smartmatch_providers     provider ports + fixture adapters
├── python/smartmatch_persistence   PostgreSQL schema + repositories
├── services/api                    FastAPI HTTP boundary
├── services/worker                 private task-execution service
├── tools/                          15 single-file operator scripts (NOT a member)
└── apps/web/legacy-frontend        React SPA (separate npm project)
```

### Code volume (OBSERVED, `find | wc -l`)

| Area | Files | Lines |
|---|---:|---:|
| `tests/` | 204 | 103,956 |
| `python/` (4 packages) | 94 | 40,224 |
| `apps/` (tsx/ts) | 141 | 29,384 |
| `services/` (api + worker) | 52 | 28,080 |
| `db/` (migrations) | 34 | 8,876 |
| `tools/` | 15 | 8,784 |
| `docs/` | 170 `.md` files | — |

**INFERRED.** Test code outnumbers production code roughly 1.5:1 by line count
(104k vs ~70k). Combined with 3,807 discovered test functions, this is a
codebase with an unusually strong verification culture, not a prototype.

### The largest single modules (candidates for cohesion review)

| File | Lines |
|---|---:|
| `python/smartmatch_persistence/.../schema.py` | 2,691 |
| `python/smartmatch_domain/.../zcta_centroids.py` | 1,894 (generated data table) |
| `services/api/.../routers/cba_contacts.py` | 1,416 |
| `services/worker/.../handlers.py` | 1,369 |
| `services/api/.../routers/cba_invitations.py` | 1,313 |
| `services/api/.../routers/match_runs.py` | 1,243 |
| `python/smartmatch_persistence/.../pipeline.py` | 1,224 |
| `services/worker/.../dispatcher.py` | 1,152 |
| `services/api/.../routers/student_events.py` | 1,160 |
| `apps/web/.../src/lib/api.ts` | 4,238 |

---

## 4. Application entrypoints

| Entrypoint | Kind | Evidence |
|---|---|---|
| `smartmatch_api.main:app` | FastAPI ASGI app | `services/api/smartmatch_api/main.py:app` |
| `smartmatch_worker.main:create_app` | FastAPI ASGI app factory (private) | `services/worker/smartmatch_worker/main.py:321` |
| `python -m smartmatch_worker.local_scheduler` | dev-only scheduler sidecar | `docker-compose.yml` `scheduler` service |
| `apps/web/legacy-frontend/src/main.tsx` | Vite SPA | `main.tsx` |
| `tools/*.py` | 15 operator/one-shot scripts | `tools/` |

---

## 5. Deployment targets

**Two distinct topologies exist in this repository, and only one of them is
executable.** This is the single most important fact in the inventory.

| Topology | Status | Evidence |
|---|---|---|
| **Docker Compose appliance** (db, migrate, seed×3, api, worker, scheduler, seed-review, web) | **OPERATIONAL.** Built, started and probed in CI; deployed to a pilot VM over IAP. | `docker-compose.yml` (12 services), `.github/workflows/build.yml` (`compose smoke`, `pilot e2e`), `.github/workflows/deploy.yml`, `docker-compose.vm.yml`, `smartmatch.sh` |
| **GCP Cloud Run + Cloud Tasks + Cloud SQL + Cloud Scheduler** | **SKELETON ONLY, deliberately non-applyable.** | `infra/terraform/envs/dev/main.tf:1` — *"configuration only. NOTHING HERE IS APPLIED… no provider block, no backend block, no resource, module, or data block"*; enforced by `tools/env_isolation_check.py` in the `isolation` CI job |

**OBSERVED.** All four Terraform environments (`dev`, `staging`, `prod`,
`classroom`) contain only `locals` with placeholder identifiers in the reserved
`example` / `.invalid` namespaces, and CI *fails the build* if a real
identifier or an applyable block appears. The GCP topology is a design record,
not a deployment.

**INFERRED.** The production service abstractions (`TaskQueue`,
`TokenVerifier`, Cloud Tasks OIDC audiences, Cloud Scheduler heartbeat) are
built and tested against *fixture* and *local* implementations only. See
`capability-inventory.md` rows `INFRA-*`.

---

## 6. Storage and external systems

| System | Role | Status | Evidence |
|---|---|---|---|
| PostgreSQL 16 | **The** authoritative store *and* the coordination store — job state, outbox, budgets, leases, rate limits | Operational | `smartmatch_persistence/__init__.py` docstring; `docker-compose.yml` `db`; `verify.yml` postgres service |
| Redis / Pub/Sub / BigQuery | Deferred with adoption triggers | **Absent by decision** | `smartmatch_persistence/__init__.py` docstring |
| Object storage (GCS) | Evidence + artifact buckets | Placeholder only | `infra/terraform/modules/storage_buckets/` |
| Cloud Tasks | Command delivery queue | Port defined; only `FixtureTaskQueue` + `local_tasks` implemented | `smartmatch_providers/tasks.py:121`, `smartmatch_worker/local_tasks.py` |
| Resend | Email delivery | Adapter written (`resend.py`, 339 lines); gated off by edition | `smartmatch_providers/registry.py:107-150` |
| Google Routes API | Travel-time matrix | **Not implemented** — `build_route_matrix_provider` raises for live | `smartmatch_providers/registry.py:196` |
| JWKS / institutional IdP | Token verification | Verifier written (`jwks.py`, 469 lines) but **unwired** | `main.py` module docstring: *"leaves the JWKS verifier unwired"* |

---

## 7. Authentication providers

**OBSERVED.** Two mechanisms coexist:

1. **`POST /v1/auth/login`** — password-based, pilot-scoped. Credentials in
   `pilot_credential`, sessions in `pilot_session`, attempts in
   `pilot_login_attempt` (migration `0020`). Roles are read server-side from
   `user_account` + `membership`, never from the request.
   Authorized in `docs/decisions/pilot-login-decision-2026-09-04.md`.
2. **`StaticJwksVerifier` / OIDC** — `smartmatch_providers/jwks.py`, 52 unit
   tests (`tests/unit/test_static_jwks_verifier.py`), **not wired to any live
   issuer.** Gate A1b, deferred: `docs/plans/open-questions/a1b-live-idp-deferred.md`.

Worker-side identity is separate again: Cloud Tasks OIDC and Cloud Scheduler
OIDC with *separate audiences and separate service-account allowlists*
(`smartmatch_worker/identity.py`, 682 lines).

---

## 8. Verification systems

| Gate | Where | What it asserts |
|---|---|---|
| `ruff format --check` / `ruff check` | `verify.yml` python job | Formatting, lint |
| `mypy python/ services/` | same | Strict typing, no untyped defs |
| `lint-imports` | same | 4 architecture contracts (see `dependency-analysis.md`) |
| `alembic upgrade head` | same | Migrations apply from empty |
| `pytest -m "not e2e"` with coverage | same | 3,807 test functions |
| `export_openapi.py --check` | same | Committed OpenAPI is not stale |
| `scan_forbidden.py` | `isolation` job | 11 forbidden legacy patterns |
| `agent_memory_check.py` | same | Agent-memory ledger provenance |
| `env_isolation_check.py` | same | No shared Terraform identifiers; nothing applyable |
| tracked-`.env` / `.db` / archive scan | same | No secrets or binaries committed |
| `pip-audit --strict` | `audit` job | Vulnerabilities in the runtime lock |
| `supply_chain.py licenses` + SBOM | `supply-chain` job | License policy, CycloneDX 1.5 |
| `gitleaks` full history | `secrets` job | Committed secrets |
| `npm ci && npm run build && npm audit` | `web` job | Web typecheck, build, advisories |
| image hardening probes | `build.yml` `images` | Non-root, read-only app dir, no `.env`/history/tests in image, SIGTERM |
| compose smoke + pilot e2e | `build.yml` | 26 numbered end-to-end steps |

**OBSERVED — gap.** The `web` CI job runs `npm ci`, `npm run build` and
`npm audit`. It does **not** run `npm test`, although
`package.json` defines `"test": "node --test tests/*.test.ts"` and eight test
files exist under `apps/web/legacy-frontend/tests/`. Those tests are never
executed by any workflow. See `risk-register.md` R-09.

**OBSERVED — gap.** `pytest --cov` names only the four `python/` packages.
`services/api` (≈14k lines) and `services/worker` (≈7k lines) are exercised by
tests but their coverage is never measured. See `risk-register.md` R-10.

---

## 9. Documentation topology

170 Markdown files. Notable sets:

| Path | Contents |
|---|---|
| `docs/architecture/decisions/` | **17 ADRs**, ADR-0001 → ADR-0017, plus a README index |
| `docs/architecture/` | command path, engagement model, v1.1 pin record, registry supersession record, diagrams, review findings |
| `docs/plans/` | 40+ plan/handoff/brief documents, dated 2026-08-28 → 2026-09-07 |
| `docs/plans/open-questions/` | 7 explicit deferral records (`*-deferred.md`) |
| `docs/decisions/` | owner-level product decisions |
| `docs/agent-memory/` | append-only ledger + approved records |
| `docs/superpowers/{specs,plans}` | specification-before-implementation artifacts |
| `docs/security/`, `docs/operations/`, `docs/testing/`, `docs/ui/`, `docs/product/` | domain-specific guides |
| `.cursor/skills/` | 3 agent skills (`i-have-adhd`, `opus-goal-prompting`, `smartmatch-status-report`) |

**INFERRED.** This repository is developed primarily by AI coding agents under
a heavy written-decision regime: an agent-memory ledger with a CI gate, goal
prompts, handoff documents, and per-decision open-question records. The
documentation is a first-class artifact, not a byproduct — which is why the
audit weights *contradictions* between docs and code as findings rather than
noise (see `wip-analysis.md` §5).

---

## 10. What this inventory does not establish

- **UNKNOWN:** whether the pilot VM deployment is currently live and serving
  real users. `deploy.yml` exists and probes a public URL through Cloudflare
  Access, but no evidence in the repository states current deployment status.
- **UNKNOWN:** actual runtime data volumes. All observed data is synthetic
  (`tools/generate_pilot_dataset.py`, `docs/pilot-data/fixtures/`).
- **UNKNOWN:** whether `docs/plans/*` documents dated before 2026-09-05
  describe work that landed, since the corresponding commits are not in the
  visible history.
