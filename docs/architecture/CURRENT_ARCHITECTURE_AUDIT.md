# Current Architecture Audit

**The authoritative Stage 1 report.** Commit `c72dced`, branch
`claude/repository-architecture-audit-y9g2un`, 2026-09-08.
Auditor: Claude Opus, evidence-first architecture investigation.

Classifications: **OBSERVED** · **INFERRED** · **RISK** · **RECOMMENDATION** · **UNKNOWN**.

Companion documents (evidence lives there; this report summarises and links):
`repository-inventory.md` · `current-system-topology.md` ·
`dependency-analysis.md` · `domain-model.md` · `capability-inventory.md` ·
`wip-analysis.md` · `data-architecture.md` · `risk-register.md`

---

## 1. Executive summary

**What we actually have.** SmartMatch is a **mature, deliberately-layered
Python monorepo** implementing a speaker/event matching platform for Cal Poly
Pomona's College of Business Administration. It is not a prototype and not a
scaffold, despite calling itself "Foundation scaffold" in its own manifest:
9 product capabilities and 12 infrastructure capabilities are implemented,
57 API paths are published under a CI-gated OpenAPI contract, 43 tables carry
119 check constraints, and 3,807 test functions run against it — including a
26-step end-to-end walk of the real product journey against a live appliance.

**The architecture's central asset is that its inner boundaries are real.**
Four `import-linter` contracts enforce a pure domain layer (no `fastapi`, no
`sqlalchemy`, no `httpx`, and no `os` or `pathlib`), a pure policy layer, a
storage layer that cannot reach the network, and a strict one-directional
layering. A self-tested scanner (`tools/scan_forbidden.py`) makes eleven
specific legacy defects — caller-selected identity, fabricated scores, inline
provider IO in a handler, mutating GETs, module-level mutable global state —
build failures rather than review items. The audit searched for every classic
architectural leak these controls target and **found none**.

**The architecture's central weakness is that its outer boundaries are not.**
The 28,000 lines of `services/api` and `services/worker` — 40% of production
Python — are governed by **no import contract at all**, and their manifests do
not declare a dependency they use in 43 files. Beyond the API, the frontend
consumes 42 endpoints with hand-transcribed types while the repository's own
published contract asserts that a generated client exists; it does not. The
result is a system whose *core* cannot drift and whose *edges* have no guard.

**The most consequential single finding** is not architectural at all: the
frontend's eight test files — including one whose name says it guards
cross-principal cache isolation — are **never executed by any workflow**.
That is a one-line fix and it is P0 (R-09).

**What is transitional.** Every production adapter is unproven. Live Cloud
Tasks, live Google Routes, live Resend email, and JWKS-against-a-real-issuer
each exist as a well-tested *port* with a fixture implementation and a
constructor that refuses. The GCP topology is described across seven Terraform
modules and four environments, all of which CI actively prevents from being
applyable. **The system that runs is a Docker Compose appliance on a VM**, and
the repository nowhere says so.

**The pattern worth naming.** This codebase does not mark WIP with `TODO`.
There are zero `TODO`, `FIXME`, `HACK`, `XXX` markers and zero
`NotImplementedError`s. Unfinished work is expressed as *absence* — an
unmounted route, an unregistered handler, a constructor that raises — tracked
in a parallel documentation system of named gates and deferral records. This is
a better discipline than comments, because an unmounted route cannot be called
by accident. Its one cost is that WIP is invisible to anyone reading only the
code, which is why §12 exists.

---

## 2. Repository topology

`uv` workspace, six declared members plus a seventh un-declared source root.

```
python/smartmatch_domain       pure domain            54 modules
python/smartmatch_authz        pure policy             2 modules
python/smartmatch_providers    ports + fixtures       12 modules
python/smartmatch_persistence  PostgreSQL             26 modules, 43 tables
services/api                   FastAPI                26 routers, 14k lines
services/worker                private task service    7k lines
tools/                         15 operator scripts    NOT a workspace member
apps/web/legacy-frontend       React 18 SPA           141 ts/tsx files
db/migrations                  Alembic                33 revisions
contracts/openapi              57 paths, 120 schemas  CI-gated for staleness
infra/terraform                7 modules, 4 envs      deliberately non-applyable
docs/                          170 markdown files     17 ADRs
```

Test code (104k lines) exceeds production code (~70k) by roughly 1.5:1.
Full detail: `repository-inventory.md`.

---

## 3. Runtime architecture

**OBSERVED — two topologies, one executable.**

| | Executable | Design record |
|---|---|---|
| **What** | `docker compose` appliance: db · migrate · 4 seeders · api · worker · scheduler · web | GCP: Cloud Run ×2 · Cloud Tasks · Cloud Scheduler · Cloud SQL · GCS · Secret Manager |
| **Proof** | Built, started, probed and smoke-tested in `build.yml`; deployed over IAP to a pilot VM by `deploy.yml`; probed through Cloudflare Access | `infra/terraform/envs/dev/main.tf:1` — *"NOTHING HERE IS APPLIED"*; `env_isolation_check.py` fails the build on any applyable block or non-placeholder identifier |

**The request path.** Cloudflare Access → SPA → `MaxBodySizeMiddleware` (ASGI,
ahead of routing, so an oversized body is refused before Pydantic parses it) →
exception handlers → `get_current_principal` → `assert_allowed` →
`enforce_rate_limit` → `charge_quota` → router.

**The command path** (ADR-0005, the architecture's spine). A write that must
reach a provider is recorded, never performed, in the request:

1. API opens one transaction: `job(queued)` + `outbox_record` +
   `idempotency_record`. Returns `202` and a job id — **never a result**.
2. Cloud Scheduler (locally, a sidecar) drives `POST /operations/dispatch`.
3. The dispatcher claims outbox rows with a CTE and `SKIP LOCKED`, creates
   tasks under deterministic names (ADR-0007), marks them dispatched.
4. Cloud Tasks delivers to `POST /tasks/execute`. The worker **verifies the
   caller's OIDC identity before reading the body** — the body arrives as a raw
   `Request` precisely so FastAPI cannot answer `422` to an unauthenticated
   caller.
5. The handler executes, writes the result, moves the job to one of twelve
   states.

**Three trust boundaries**, each with its own verifier and allowlist: internet →
API; Cloud Tasks → worker (audience `tasks`); Cloud Scheduler → worker
(audience `scheduler`). *"Cloud Tasks may deliver work and may not drive
dispatch; Cloud Scheduler may drive dispatch and may not deliver work."*
Unconfigured, every one of them refuses (`501`), so the default posture is
closed.

Diagrams: `current-system-topology.md`.

---

## 4. Domain architecture

`smartmatch_domain` is a **functional core**: 85 frozen dataclasses, 40+
`StrEnum` vocabularies, five explicit state machines (`consent`, `jobs`,
`outreach`, `rewards`, `spend`), pure decision functions, zero IO. The audit
specifically tested for an anemic domain model and did not find one — the
rules live in the domain layer and the outer layers call into them.

Six bounded contexts are identifiable from converging evidence (module
clustering, table clustering, and the `Capability` gate table): Identity &
Access · Work Substrate · Event Catalog · Matching · Speaker Relationship ·
Engagement & Outreach.

**Three concepts are modelled unusually well:**

- **Event time is a sum type.** `ExactTime | DateOnlyTime | UnresolvedTime`
  with `TimePrecision`. Uncertainty is a *type*, not a nullable column with a
  convention, so a caller cannot read a time without deciding what to do about
  not knowing it (ADR-0010).
- **Job failure is three states, not one.** `failed_provider`, `failed_budget`,
  `failed_policy` are distinct, and `partial` is a first-class terminal state.
  "Why did this fail" is queryable rather than greppable.
- **Accountable numbers (ADR-0011).** A score carries its provenance or it is
  `null`; `null` is never rendered as `0`; no score is presented as a
  percentage. Enforced three ways — a scanner rule against literal score
  assignment, e2e tests 11 and 12, and dedicated UI components
  (`AccountableValue`, `MetricValueDisplay`, `ProvenanceDisclosure`).

**Terminology is the domain's weak point.** Four names overlap for one referent
(`speaker_profile` / `professional_unit_relationship` / `contact_channel` /
"Specialist"), "event" means four unrelated things across the schema, and
"review" means two. The repository actively manages the *product-visible* half
of this with a scoped terminology scanner; the *internal* half is unmanaged.

Full detail: `domain-model.md`.

---

## 5. Dependency architecture

**Enforced (and clean):**

| Contract | Effect |
|---|---|
| Domain is pure | no `fastapi`, `starlette`, `sqlalchemy`, `httpx`, `google`, `boto3`, `os`, `pathlib`, `socket`, `subprocess`, `smartmatch_providers` |
| Authz is pure | same shape, narrower |
| Layering | persistence → providers → authz → domain, one direction |
| Persistence is storage only | no network, no providers, no frameworks |

A full AST cycle search found **no genuine import cycles**. All cross-package
edges point downward. Every classic leak the audit looked for was absent.

**Not enforced (the finding):**

- `smartmatch_api` and `smartmatch_worker` are **absent from
  `root_packages`** — 28k lines with no contract.
- Both services import `smartmatch_persistence` (43 files) without declaring
  it. The manifests do not describe the real graph.
- Two routers reach into sibling routers for underscore-prefixed helpers. Both
  are *documented and well-motivated* — the motive is "one authorization
  question, one answer" — but the mechanism makes the router layer's public
  surface undefinable.
- Nothing prevents `smartmatch_api` importing `smartmatch_worker`.

**Fan-in is healthy** where it should be (vocabularies: `jobs` 17,
`factor_registry` 17, `events` 15) and reveals one smell: `utils.py` — 18
lines, one function, **25 consumers**. The content is right; the *name* is the
seed of a dumping ground.

`job_authz.py` is the model to follow: its docstring records that `jobs.py`
and `redrive.py` each previously carried their own `_authorize_job_read`
applying *different subsets of the same policy*, and this module is the
consolidation.

Full detail: `dependency-analysis.md`.

---

## 6. Data architecture

PostgreSQL is the only store, holding business data **and** coordination state
(jobs, outbox, idempotency, leases, rate limits, budgets). Redis, Pub/Sub and
BigQuery are deferred with stated adoption triggers. This is what makes the
transactional outbox sound — one transaction spans "record the intent" and
"enqueue the work" — and it is also the decision that most constrains scale.

**Integrity posture is the strongest in the system:** 119 check constraints,
283 non-null columns, 68 of 81 foreign keys `RESTRICT`, **zero** `SET NULL`,
composite tenant-safe keys, two GiST `ltree` indexes for subtree authorization,
and a whole-schema symmetric parity test between `schema.py` and the migrated
database.

**Derived data has explicit source-of-truth rules.** Point balances are folded
from an append-only ledger, never stored. Match scores are reproducible from
fingerprinted weights and inputs. Attendance is the *only* input to points
(ADR-0013), and registration deliberately never writes an attendance row.

**Two gaps:**

- **Indexes are outside the guard.** `schema.py` declares zero indexes; all 33
  live in migrations; the parity test explicitly does not compare them.
  Dropping `ix_outbox_claimable` would pass every CI gate and silently degrade
  the dispatcher to a sequential scan.
- **No table has a declared owner.** All 43 are in one 2,691-line module, and
  the consequence is already visible: match-run rows are written by both the
  API router and the worker handler, with nothing saying which should.

Full detail: `data-architecture.md`.

---

## 7. API architecture

57 paths, 120 schemas, OpenAPI 3.1, regenerated by `tools/export_openapi.py`
and **CI-gated for staleness**. One error envelope (`ErrorEnvelope`) declared
application-wide, deliberately overriding FastAPI's automatic `422` so the
contract advertises exactly one error shape. Media types declared per response
rather than per route, so an HTML page's inherited JSON error bodies are not
mis-documented.

46 of 57 paths sit under `/v1/units/{unit_id}/…` — the org-unit tree is
simultaneously the tenancy model, the authorization scope, and the URL
structure.

**The contract is deliberate. The consumption of it is accidental.** There is
no generated client, no client at all: 42 endpoints are reached by inline
`fetch` across 49 files with response types transcribed by hand, alongside a
4,238-line hand-written `api.ts` that targets 24 routes **no service serves**.
The freshness gate protects the contract and nothing protects the consumer.

**Two write styles coexist** without a stated rule: eight routers submit
commands, eight write synchronously, two do both. The *actual* invariant —
readable in one module docstring and one scanner regex — is narrower than "all
writes are async": a router may write its own rows, it may not perform provider
IO. That rule is real and enforced; it is not written down as a principle.

---

## 8. Security architecture

**Strong, and enforced rather than reviewed.**

| Property | Mechanism |
|---|---|
| Deny by default | `authz.evaluate` returns `Effect`; `assert_allowed` raises |
| Identity is never caller-supplied | `Principal` assembled server-side from `user_account` + `membership`; scanner forbids `role = request.json` and `tenant_id = payload[...]` |
| Tenant isolation | composite tenant-safe keys + `ltree` scope, GiST-indexed; `test_tenant_isolation.py`, `test_policy_matrix.py` (41) |
| Authorization coverage | **all 26 routers**; six authorize by documented delegation. No unauthorized route found |
| Consent | explicit state machine with an escalation predicate and a full transition log; checked at composition *and* at send; e2e 18 and 21 |
| Quota before refusal | ADR-0015 — a refused caller still consumes quota, so refusal is not a free probe |
| Request-body bound | ASGI middleware ahead of routing; refuses an honest oversized `Content-Length` without reading, and bounds a lying one by buffering |
| Worker boundaries | two callers, two audiences, two allowlists, verify-before-parse; `501` when unconfigured |
| No mutating GET | scanner rule; the unsubscribe/invitation GETs render, the POSTs mutate — because link scanners and mail prefetchers fetch GETs |
| No token echo | invitation and unsubscribe pages deliberately do not reflect the token into HTML |
| Anti-oracle | the invitation POST answers identically for every token |
| Supply chain | hash-pinned locks, `pip-audit --strict`, license policy, CycloneDX SBOM, actions pinned to commit SHAs, full-history `gitleaks`, non-root images with read-only app dirs |

**Weaknesses:**

- **Observability is the security gap.** 20 logging references across 70k
  lines. An authorization refusal, a rate-limit rejection, or a 500 leaves no
  structured trace. A system that fails closed but cannot say *that* it failed
  closed is hard to operate and harder to investigate.
- The most expensive read (`metrics/{name}/drill-down`) has no rate limit.
- The frontend's cross-principal cache-isolation test never runs.

---

## 9. Operational architecture

| Concern | State |
|---|---|
| Logging | 20 references, unstructured, 10 files. 22 of 26 routers silent |
| Metrics / tracing | **None** |
| Health | `GET /api/health` — liveness only, exposes no topology (deliberate, v1.1 §1.11). The readiness endpoint its docstring promises was **not found** |
| Job visibility | **Good.** `job_event` + `GET /v1/jobs/{id}/events` is a durable per-job stream; `DispatchPassResponse` reports sweep/claim outcomes with `sweep_failed` distinguished from "nothing to sweep" |
| Migrations | Applied from empty on every PR; one transaction per migration (ADR-0009); parity-guarded |
| Rollback | **UNKNOWN.** No `downgrade()` is exercised anywhere |
| Deployment | `deploy.yml` → IAP → pilot VM → probe public URL; records the deployed revision; prints a diagnosis section on failure |
| Environment parity | Compose appliance is what CI tests *and* what deploys — genuinely high parity, and better than the GCP design record would give |

**INFERRED — would a production failure be diagnosable?** Inside the job path,
yes: `job_event` records it. Everywhere else, no. That asymmetry is the single
biggest operational gap.

---

## 10. Testing architecture

| Layer | Count | Character |
|---|---:|---|
| `tests/unit` | 111 files | Pure domain, scanners, parsers, providers. `test_env_isolation_check.py` (73), `test_agent_memory_check.py` (72), `test_jsonld_parser.py` (64) |
| `tests/integration` | 57 files | Real PostgreSQL. Constraints, migrations, command path, outbox (44 tests incl. crash-between-commit-and-task-creation and duplicate delivery), leases, redrive, tenant isolation |
| `tests/contract` | 27 files | HTTP surface per router, error envelope, body bound, worker boundary |
| `tests/authz` | 5 files | Policy matrix (41) |
| `tests/golden` | 2 files + fixtures | Characterization tests pinning ported legacy behaviour |
| `tests/e2e` | 2 files, 26 numbered steps | Full product walk against a live `docker compose` appliance |
| **Total** | 3,807 test functions | |

**The pyramid is real and correctly shaped**: broad pure-unit base, a
substantial integration tier where the invariants actually live (constraints
and concurrency are tested against PostgreSQL, not mocks), a thin contract
tier, and a single narrative e2e walk. Markers (`golden`, `integration`,
`e2e`) are strict, and `e2e` is excluded **by marker rather than by path** so a
file added under `tests/e2e/` cannot accidentally put a stack-dependent suite
into the no-database gate.

Even the *gates* are tested: `test_forbidden_scanner.py`,
`test_env_isolation_check.py`, `test_supply_chain.py`,
`test_agent_memory_check.py`. A green gate here means something.

**Three gaps:** API/worker coverage is unmeasured; the frontend suite never
runs; downgrades are never exercised.

---

## 11. Feature inventory

9 product capabilities and 12 infrastructure capabilities, each with entry
points, modules, tables, tests and status, in `capability-inventory.md`.
Summary:

- **COMPLETE (12):** event reads, speaker-request intake, speaker contact
  management, match runs, discovery metrics, rewards ledger, operator import,
  job lifecycle, outbox/dispatcher, redrive, review queue, engagement summary,
  rate limiting, tenant isolation, OpenAPI publication, body bound, error
  envelope.
- **FUNCTIONAL / NEEDS HARDENING (4):** authenticated login (pilot password,
  not SSO); consented outreach (fixture email only — **no live email has ever
  been sent**); spend/quota (sweeper unattached); the three portal front-ends.
- **SCAFFOLDED (1):** task-identity verification — fails closed, never verified
  against a real issuer.
- **BLOCKED / partly DEAD (1):** seven legacy frontend pages.
- **DEAD (3):** three unreferenced components.
- **PLANNED, out of scope by decision (4):** external speaker acquisition, cold
  outreach, chapter dues, member-inquiry narrative — these own **no router at
  all**, which is the right way to gate a capability off.

---

## 12. WIP inventory

Zero `TODO`/`FIXME`/`HACK`/`XXX`/`NotImplementedError` in the codebase. WIP is
expressed as absence and tracked in documentation. Found by other means:

| Item | Kind | Blocked on |
|---|---|---|
| Frontend tests never run in CI | **Missed wiring** | nothing |
| `SpendReservationSweeper` never scheduled | **Missed wiring** | nothing |
| Command-type → handler map unverifiable | **Unknown** | nothing |
| Generated API client absent | **Unfinished** | nothing |
| Undeclared service→persistence dependency | **Manifest error** | nothing |
| Stale docstrings (G1, Calendar, generated client) | **Documentation** | nothing |
| Seven legacy pages with a now-false retirement notice | **Product decision** | owner |
| Live email adapter | **Deferred** | human decision, OQ-001 |
| Live identity (A1b) | **Deferred** | the institution |
| Live route matrix | **Not started** | product need |
| Live Cloud Tasks | **Deferred** | GCP topology |
| GCP Terraform | **Deferred** | F5 |

The first five are unblocked and cheap. Detail and safest-next-step for each:
`wip-analysis.md`.

---

## 13. Architectural strengths

1. **Enforced inner boundaries.** Four import contracts including `os` and
   `pathlib` in the domain's forbidden list. Not nominal.
2. **Defects encoded as gates.** `scan_forbidden.py` turns eleven specific
   legacy failures into build failures, and is itself tested.
3. **A sound command path.** Transactional outbox, `SKIP LOCKED` CTE claim,
   deterministic task names, lease + generation, twelve job states, idempotency
   records, a redrive path, and 44 tests including crash-window cases.
4. **Deny-by-default authorization with complete coverage**, `ltree`-scoped,
   GiST-indexed, matrix-tested.
5. **Database-level integrity.** 119 checks, `RESTRICT` everywhere, zero
   `SET NULL`, whole-schema parity guard.
6. **Accountable numbers (ADR-0011).** Enforced in the scanner, the e2e suite,
   *and* the UI components. Rare, and the right commitment for a system that
   ranks people.
7. **Capabilities gated by absence, not by branches.** A disabled capability
   owns no router. No dead branch to enable by accident.
8. **A real test pyramid**, with the invariants tested where they live and the
   gates themselves under test.
9. **Reasoning is recorded where it is needed.** 17 ADRs, and docstrings that
   argue the decision rather than restate the code — `main.py`'s router table
   argues each capability assignment on its merits.
10. **Supply-chain discipline** most production systems lack: hash-pinned
    locks, SBOM, license policy, SHA-pinned actions, full-history secret scan,
    hardened images.

---

## 14. Architectural weaknesses

1. **40% of production Python is uncontracted** — `services/*` are absent from
   `root_packages`, and their manifests understate their dependencies.
2. **No frontend/backend contract enforcement.** A published claim of a
   generated client that does not exist; 42 endpoints consumed by hand.
3. **Near-zero observability outside the job path.**
4. **The command registry is not a map.** Three registered handlers, eight
   submitting routers, and no assertion tying them together.
5. **Written-but-unattached code.** The spend sweeper and the frontend test
   suite both exist, both are tested or testable, and neither runs.
6. **No declared data ownership.** 43 tables, one module, no owner statement —
   which is why match-run rows have two writers.
7. **Indexes sit outside the parity guard.**
8. **Documentation drift in a repository where documentation is load-bearing.**
   Three stale claims found, one of them published in the OpenAPI document.
9. **Two deployment topologies and no statement of which is current.**
10. **40+ plan documents with no status field**, against a git history too short
    to resolve them.

---

## 15. Critical architecture risks

Full register with evidence, probability, impact and remediation:
`risk-register.md`.

- **P0 — R-09.** Frontend tests, including a cross-principal cache-isolation
  guard, are never executed.
- **P1 — R-02** no client/contract enforcement · **R-03** observability ·
  **R-04** command-registry map · **R-05** undeclared dependency · **R-06**
  uncontracted service layer · **R-08** unscheduled spend sweeper · **R-01**
  every production adapter unproven.
- **P2 — R-07, R-10, R-11, R-12, R-15, R-16, R-17, R-06b, R-18.**
- **P3 — R-13, R-14, R-19, R-20.**

---

## 16. Technical debt

| Debt | Disposition |
|---|---|
| `services/*` uncontracted and mis-declared | **Compounding.** Every new router widens it. Fix now — it is cheap and it unlocks enforcement |
| Hand-written frontend API access | **Compounding.** Every new endpoint adds a hand-transcribed type |
| `schema.py` at 2,691 lines | **Localized.** Do **not** split for aesthetics; split only after ownership is declared |
| `utils.py` name | **Localized, preventive.** Rename to `clock.py` |
| Router→router private imports | **Localized.** The behaviour is right, the location is wrong — promote to an owned module |
| `docs/plans` without status fields | **Compounding.** Every added plan raises the reading cost |
| Benign `__init__` re-export import shape | **Acceptable.** Note it, do not refactor |
| Fixed-window rate limiting in PostgreSQL | **Acceptable** — a recorded trade (ADR-0006), not an oversight |
| Balance folded from the full ledger on read | **Acceptable.** Correct now; do **not** pre-build a snapshot scheme |
| Terminology overloading (`event` ×4, `review` ×2, speaker ×4) | **Localized.** Write a glossary; do not rename tables |
| Three dead frontend components | **Localized.** Delete |

---

## 17. Expansion pressure

**Explicitly planned** (documentation supports it):
institutional SSO (A1b, blocked on the institution) · live email delivery
(blocked on OQ-001) · GCP deployment (F5) · Calendar API (G5, deferred to
public-release planning) · the deferred CI gates listed at the bottom of
`verify.yml` (generated-client drift, Playwright, CodeQL, Trivy, IaC scan,
image signing).

**Architecturally implied** (the abstractions already anticipate it):
- `ProductScope` with a second, retained value (`IA_WEST_LEGACY`) says
  multi-product is a live concern, not a hypothetical.
- `TaskQueue`, `EmailProvider`, `RouteMatrixProvider`, `TokenVerifier` are
  ports with exactly one fixture implementation each — they exist to be
  swapped.
- `match_weight_setting_revision` and `scoring_mode` (migration `0032`) say
  scoring policy is expected to change *and* to remain reproducible across the
  change.
- `SUPERSEDED_G1_MODEL` / `SUPERSEDED_SCORING_KEYS` say registry supersession
  is a designed-for event.
- Twelve job states with three distinct failure kinds anticipate more command
  types than the three registered.
- `factors/` with six modules and a registry anticipates more factors.

**Reasonably foreseeable** (architecture should not block it): more scoring
factors · more command types · additional org-unit depth · retention/archival
for the append-only tables · a second frontend or a mobile client consuming the
same contract.

**Speculative — do NOT design for it now:** multi-region · event sourcing
beyond the points ledger · a public API for third parties · real-time
websockets · ML-based matching. None of these is implied by anything in the
repository, and ADR-0003 explicitly excludes agents from Foundation.

**RECOMMENDATION.** The single most valuable thing expansion pressure argues
for is **not** a new abstraction. It is finishing the seams that already exist:
the client, the registry map, the service contracts. Every one of them is a
place where the *next* feature will otherwise be added ad hoc.

---

## 18. Recommended architecture priorities

In order. Earlier items make later ones cheaper.

1. **Run the tests that exist.** Add `npm test` to the `web` job; add
   `services/*` to `--cov`. (R-09, R-10)
2. **Attach the code that was written and not wired.** Call the spend sweeper
   from the scheduled dispatch pass. (R-08)
3. **Make the command registry a map.** Assert every submittable command type
   is registered or explicitly refused. (R-04)
4. **Declare and then enforce the service layer.** Add
   `smartmatch-persistence` to both manifests; add both services to
   `root_packages`; promote the two shared authorization helpers out of the
   routers; forbid router→router imports. (R-05, R-06)
5. **Close the contract loop.** Generate the TypeScript client, add the drift
   check, migrate one page as the pattern. (R-02)
6. **Make failure visible.** Structured request logging with a correlation id
   at the API boundary; log every `ApiError` once with its code. Do not adopt a
   tracing vendor yet. (R-03)
7. **Correct the three stale claims, then guard the gate one.** (R-15)
8. **Declare table ownership**, then decide whether `schema.py` splits.
   (R-20, and the prerequisite for it)
9. **Bring indexes under the parity guard.** (R-12)
10. **Give `docs/plans` status headers and archive the settled ones.** (R-16)

---

## 19. Unknowns requiring investigation

| # | Unknown | Why it matters | How to resolve |
|---|---|---|---|
| U1 | Which command type does each of the eight submitting routers use, and what executes it? | Blocks any new async capability | The R-04 test answers it by construction |
| U2 | Is `MaxBodySizeMiddleware`'s buffering branch (lying `Content-Length`, chunked body) tested? | It is the security-relevant branch and the subtle one | Read `tests/contract/test_max_body_size.py` |
| U3 | Does a readiness endpoint exist anywhere? `main.py`'s docstring says one does | Deployment health checks may be probing liveness and calling it readiness | Search the worker app and the compose healthchecks |
| U4 | Are migration `downgrade()` bodies functional? | Determines whether rollback is a real option | Run upgrade→downgrade→upgrade in the integration harness |
| U5 | Which `docs/plans/*` documents describe landed work? | 40+ documents, git history too short to say | Ask the owner, or mark each on next touch |
| U6 | Is the pilot VM currently live and serving real users? | Changes the risk weighting of every P1 item | Ask the owner |
| U7 | What are the real data volumes? All observed data is synthetic | Determines when ADR-0006's fixed-window trade expires | Query the pilot instance |
| U8 | Why was the git history rewritten at 2026-09-05? | Determines whether pre-2026-09-05 archaeology is recoverable at all | Ask the owner |

---

## 20. Evidence index

Every claim above traces to one of these.

**Manifests & configuration** — `pyproject.toml` (`[tool.uv.workspace]`,
`[tool.ruff]`, `[tool.mypy]`, `[tool.pytest.ini_options]`,
`[tool.importlinter]`) · `python/*/pyproject.toml` ·
`services/*/pyproject.toml` · `apps/web/legacy-frontend/package.json` ·
`requirements/*.in|.txt` · `Makefile` · `.agent-memory.yaml` · `.gitleaks.toml`

**Entrypoints & composition** — `services/api/smartmatch_api/main.py`
(module docstring; `MaxBodySizeMiddleware`; `CAPABILITY_SCOPED_ROUTERS`;
`health`; `unsubscribe_page`; `invitation_response_page`) ·
`services/worker/smartmatch_worker/main.py` (docstring §"Order of operations,
which is the security property"; `create_app`) ·
`apps/web/legacy-frontend/src/{main.tsx,app/routes.tsx}`

**Domain** — `product_scope.py:74-135` · `factor_registry.py:106-156,543-556` ·
`jobs.py:38-49` · `events.py:169-463` · `consent.py:40-281` ·
`scoring.py:114-630` · `rewards.py:129-497` · `spend.py:109-331` ·
`outreach.py:152-622` · `match_run.py:113-199` · `eligibility.py:50-110`

**Authz** — `policy.py:110-405` · `services/api/smartmatch_api/job_authz.py` ·
`dependencies.py:63-245` · `units.py`

**Persistence** — `schema.py` (43 `sa.Table` definitions at lines 106–2593) ·
`spend_sweeper.py:1-40,97,107` · `outbox.py` · `jobs.py:22-65` ·
`smartmatch_persistence/__init__.py`

**Providers** — `registry.py:38-303` (four live-client refusals) ·
`jwks.py` · `identity.py` · `tasks.py` · `resend.py`

**Worker** — `handlers.py:11,287,433,1109,1330-1369` · `dispatcher.py` ·
`execution.py` · `identity.py` · `local_tasks.py` · `local_scheduler.py`

**Contract** — `contracts/openapi/smartmatch.json` (57 paths, 120 schemas) ·
`tools/export_openapi.py`

**Frontend** — `src/lib/api.ts` (4,238 lines; 24 `/api/*` targets) ·
`src/app/pages/Calendar.tsx:80-100` · `src/lib/productScope.ts` ·
`src/app/components/provenance/*` · `tests/*.test.ts` (8 files)

**Database** — `db/migrations/versions/0001…0033` · `db/migrations/env.py`

**Infrastructure** — `infra/terraform/envs/{dev,staging,prod,classroom}/*.tf`
(`dev/main.tf:1`) · `infra/terraform/modules/*` · `docker-compose.yml`
(12 services) · `docker-compose.vm.yml` · `Dockerfile.{api,worker}` ·
`smartmatch.sh`

**CI/CD** — `.github/workflows/verify.yml` (jobs `python`, `isolation`,
`audit`, `web`, `supply-chain`, `secrets`; deferred-gate list at end) ·
`build.yml` (`images`, `compose smoke`, `pilot e2e`) · `deploy.yml`

**Gates** — `tools/scan_forbidden.py:58-183` (11 rules) ·
`tools/scan_cba_terminology.py:1-40` · `tools/env_isolation_check.py` ·
`tools/agent_memory_check.py` · `tools/supply_chain.py`

**Tests** — `tests/e2e` (26 numbered steps) ·
`tests/integration/test_outbox_dispatcher.py` (44) ·
`test_schema_matches_migration.py:1-30` · `test_check_constraints.py` (43) ·
`test_event_schema_constraints.py` (54) · `test_tenant_isolation.py` ·
`tests/authz/test_policy_matrix.py` (41) ·
`tests/unit/test_static_jwks_verifier.py` (52) · `test_spend_sweeper.py`

**Decisions** — ADR-0001 … ADR-0017 under
`docs/architecture/decisions/` · `docs/plans/open-questions/*.md` (7 deferral
records) · `docs/decisions/pilot-login-decision-2026-09-04.md` ·
`docs/architecture/{command-path,engagement-model,v1.1-pin-record,registry-supersession-record}.md`
