# Module Boundaries — Target Specification

**Stage 2.** The module map of the system as it should be after the Stage 2
increments, with a **disposition** for every module. Written against commit
`c72dced`, 2026-09-08.

This document is the answer to the handoff's §8 leverage claim: *"if Stage 2
produces only one thing, it should be a module-boundary and dependency-rule
specification for `services/*` that is enforceable by `import-linter`."* It is
therefore written so that the **Allowed deps** and **Forbidden deps** rows are
directly translatable into `[tool.importlinter]` contracts (AP-01, ADR-0018),
not as prose about layering.

---

## 0. How to read this

Every module carries eleven fields. Nine describe it as it is; the tenth
(**Tests**) says what asserts it; the eleventh is the **Disposition** — exactly
one of:

| Disposition | Means |
|---|---|
| **remain** | Correct shape, correct place, correct name. Change nothing structural. |
| **deepen** | Stays where it is; gains an assertion, a caller, or a field it should already have had. Written as `remain, deepen` where the module is otherwise untouched. |
| **split** | One module becomes two along a named seam. |
| **merge** | Two or more become one. |
| **move** | Same content, different name or location. |
| **disappear** | Deleted. Git retains it. |
| **become an adapter** | Keeps its callers but stops being the implementation; it forwards to something generated or injected. |

**No cosmetic reorganisation.** The overwhelming majority of dispositions below
are **remain**, and each says *why* it is right rather than merely leaving it
alone. The audit found no anemic domain model, no leaked provider semantics, no
missing authorization and no genuine import cycle
(`dependency-analysis.md` §6, `risk-register.md` "What is explicitly NOT on this
register"). A boundary specification for a codebase in that condition is mostly
a record of what must not be disturbed.

**Counting note (OBSERVED, refines Stage 1).** Stage 1 says "26 routers".
`services/api/smartmatch_api/routers/` contains **25** router modules plus
`__init__.py`; those 25 modules export **28** `APIRouter` objects, because
`outreach`, `cba_invitations` and `student_speaker_feedback` each export two
(`main.py:275-465`). 24 router objects are capability-scoped; four —
`jobs`, `redrive`, `engagement`, `review` — are mounted unconditionally
(`main.py:251-254`). The "26" figure is close enough for risk prose and wrong
for a contract, so the contract below is written against 25 modules.

---

## 1. Inner packages — `python/`

These four are the only modules in the system whose boundaries are already
real. `[tool.importlinter].root_packages` names exactly them, four contracts
govern them, and `include_external_packages = true` is what makes
"the domain may not import `os`" expressible (`dependency-analysis.md` §1).

### 1.1 `smartmatch_domain`

| Field | Value |
|---|---|
| **Purpose** | The functional core. 54 modules, 85 `@dataclass(frozen=True)` value objects, 40+ `StrEnum` vocabularies, 5 explicit state machines, pure decision functions. |
| **Owns** | Every business rule that can be stated without IO: eligibility filtering, consent transitions, ledger folding, scoring and the factor registry, spend refusal, job-state legality, the event temporal model. |
| **Does not own** | Identity of a row (that is `schema.py`), transport, configuration, time-of-day (callers pass instants in), or any decision that needs a network. |
| **Public API** | Module-level frozen dataclasses, `StrEnum`s, and functions. `factor_registry.REGISTRY_STATUS` / `REGISTRY_VERSION` / `assert_registry_approved()` (factor_registry.py:137,149,553) are the load-bearing constants; `jobs.JobState` (fan-in 17) is the load-bearing vocabulary. |
| **Allowed deps** | `smartmatch_domain` only, plus the standard library minus `os`/`pathlib`/`socket`/`subprocess`. |
| **Forbidden deps** | `fastapi`, `starlette`, `sqlalchemy`, `alembic`, `pydantic_settings`, `httpx`, `requests`, `google`, `boto3`, `os`, `pathlib`, `socket`, `subprocess`, `smartmatch_providers`, `smartmatch_persistence`, `smartmatch_api`, `smartmatch_worker` — import-linter contract 1, ADR-0002. |
| **Persistence** | None, by contract. |
| **Domain concepts** | All eleven of `domain-model.md` §3. |
| **Tests** | Unit tests per module; `tests/unit/test_calendar_invite_wiring.py` asserts the *absence* of Google Calendar symbols by name — the pattern for gating a capability by absence rather than by flag. |
| **Operational concerns** | None. It cannot fail at runtime for an environmental reason, which is the point of the purity contract. |
| **Disposition** | **remain.** The strictest boundary in the repository and the reason the codebase is clean (handoff §3). `column_contract.py` living in the *worker* rather than here — because reading a YAML file needs `pathlib` and `yaml` — is the contract working as designed, not a workaround. Nothing in the risk register argues against it. |

### 1.2 `smartmatch_authz`

| Field | Value |
|---|---|
| **Purpose** | Deny-by-default `ltree`-scoped access policy. One module, `policy.py`. |
| **Owns** | `Principal`, `Membership`, `ResourceGrant`, `OrgPath`, `AccessDecision`, `evaluate()`, `assert_allowed()`. |
| **Does not own** | Where a principal comes from (`api/dependencies.py`), what a job's owning unit is (`schema.py` + `job_authz.py`), or any HTTP status. |
| **Public API** | `evaluate` returns a decision; `assert_allowed` raises `AuthorizationError`. Two functions, one rule set. |
| **Allowed deps** | `smartmatch_domain`, standard library. |
| **Forbidden deps** | Same shape as contract 1, narrower list — import-linter contract 2. |
| **Persistence** | None. Rows are loaded by `smartmatch_persistence.principals` and handed in. |
| **Domain concepts** | Org unit, Principal, Membership, Resource grant (`domain-model.md` §3.1–3.2). |
| **Tests** | Full coverage across all 25 router modules by usage; six routers authorize by documented delegation (`capability-inventory.md` §5). |
| **Operational concerns** | Suspension is evaluated locally and first (`job_authz.py` docstring, step 1), so an administratively suspended account is denied without waiting for an IdP revocation. That property must survive A1b. |
| **Disposition** | **remain.** The audit looked specifically for a route without authorization and found none. A boundary with complete coverage and a CI-enforced purity contract has nothing to gain from being moved. |

### 1.3 `smartmatch_providers`

| Field | Value |
|---|---|
| **Purpose** | Ports, plus the fixture adapters that satisfy them, plus `registry.py` — the single place a live client can be constructed. |
| **Owns** | `EmailProvider`, `RouteMatrixProvider`, `TaskQueue`, `TokenVerifier`, `PaidExtractionProvider`; `FixtureTaskQueue`, `FixtureRouteMatrixProvider`, `FixtureTokenVerifier`; `ResendEmailProvider`; the JWKS verifier core. |
| **Does not own** | Composition. Nothing here decides *which* provider a deployment gets at runtime — `worker/main.py` and `api/main.py` do, at their composition roots. |
| **Public API** | The five `build_*` functions in `registry.py:30-36` and the port protocols. |
| **Allowed deps** | `smartmatch_domain`, standard library, provider SDKs and HTTP clients. |
| **Forbidden deps** | `smartmatch_persistence`, `fastapi` — import-linter contract 3 (layering) fixes the direction persistence → providers → authz → domain. |
| **Persistence** | None. |
| **Domain concepts** | None of its own; it carries domain values across the boundary. |
| **Tests** | `tests/unit/test_resend_email_adapter.py` (37 tests); 52 unit tests over `jwks.py`. |
| **Operational concerns** | **Four terminal refusals** (`registry.py`, live Resend transport / live Routes / live Cloud Tasks / live Google Identity). Each refuses *at boot*, naming the decision it waits on, "so a deployment that acquired a credential cannot discover this one message at a time". `_FIXTURE_ONLY_EDITIONS` makes classroom isolation a code property, not a configuration convention (v1.1 §3.3). |
| **Disposition** | **remain.** This is the seam every future live capability arrives through; see `FUTURE_FEATURE_INTEGRATION.md`. The refusals are the design, not a gap — R-01's remediation is explicitly *"do not pre-build"*. |

#### 1.3a `providers/jwks.py` + `providers/identity.py`

| Field | Value |
|---|---|
| **Purpose** | JWT/JWKS verification core (469 L, 52 tests) and the `TokenVerifier` port. |
| **Owns** | Signature, issuer, audience and expiry validation; key-rotation handling. |
| **Does not own** | Issuer URL, audience, claim mapping, tenant mapping — all *OUTSTANDING — EXTERNAL DEPENDENCY* (`docs/decisions/a1b-idp-configuration-worksheet.md`). |
| **Public API** | `TokenVerifier.verify(token) -> subject`. That signature is the whole of the seam. |
| **Allowed deps** | `smartmatch_domain`, standard library, crypto. |
| **Forbidden deps** | As §1.3. |
| **Persistence** | None. The *subject* is verified here; the *principal* is loaded server-side by `PrincipalRepository`. |
| **Domain concepts** | Principal (indirectly — this produces only a subject string). |
| **Tests** | 52 unit tests. Unwired: `main.py`'s own docstring says the pilot login *"leaves the JWKS verifier unwired"*. |
| **Operational concerns** | Two authentication mechanisms exist today (pilot password login, dormant JWKS). Whichever lands second **must not become a third path** — `wip-analysis.md` §1.4. |
| **Disposition** | **become an adapter.** It stops being a tested-but-dormant module and becomes the production implementation behind `dependencies.get_token_verifier`, converging with pilot login at `dependencies._subject_for_token` (dependencies.py:86) → `get_current_principal` (dependencies.py:119). Both paths must remain "resolve a subject, then load the principal server-side"; that shared shape is what makes A1b a swap rather than a rewrite. Cited: R-01, wip-analysis §1.4. |

#### 1.3b `providers/fixtures.py` and the fixture adapters

| Field | Value |
|---|---|
| **Purpose** | Working implementations of every port, for tests, local development and the classroom edition. |
| **Owns** | `FixtureTaskQueue`, `FixtureRouteMatrixProvider`, `FixtureTokenVerifier`, the fixture email path, `fixture_ingest`. |
| **Does not own** | Any claim to production semantics. `FixtureTokenVerifier` "accepts only tokens explicitly registered with it, so it cannot be mistaken for authentication that happens to be permissive" (registry.py:279-283). |
| **Public API** | The same ports as the live adapters. |
| **Allowed / Forbidden deps** | As §1.3. |
| **Persistence** | None. |
| **Domain concepts** | None. |
| **Tests** | Every integration and e2e test in the repository runs against these; e2e 20 proves the worker sends through the fixture provider. |
| **Operational concerns** | The pilot appliance runs in fixture email mode by design — "a worker with no email credential is in *fixture* mode, which is a perfectly good thing for it to be and the mode the pilot runs in" (worker/main.py:462-467). |
| **Disposition** | **remain.** These are not scaffolding to be replaced; they are the permanent classroom-edition implementation and the permanent test substrate. They also become the *contract surface* for the live adapters — ADR-0021's delivery-contract test runs against `FixtureTaskQueue`. |

### 1.4 `smartmatch_persistence`

| Field | Value |
|---|---|
| **Purpose** | 43 PostgreSQL tables and 26 repositories. The only module that speaks SQL. |
| **Owns** | `schema.py`, the repositories, `engine.create_session_factory`, `rate_limit` (fan-in 21), `outbox`, `jobs`, `idempotency`, `redrive`, `spend`, `spend_sweeper`. |
| **Does not own** | Business rules — it calls into `smartmatch_domain` for them (14 edges). Transaction *boundaries* on the request path belong to `api/dependencies.get_session`; on the command path to `worker/execution`. |
| **Public API** | Repository classes; `schema.py`'s `Table` objects. |
| **Allowed deps** | `smartmatch_domain` (14 files), `smartmatch_authz` (1 file), SQLAlchemy Core, Alembic. |
| **Forbidden deps** | `httpx`, `requests`, `subprocess`, `smartmatch_providers`, `fastapi` — import-linter contract 4. The storage layer makes no network calls of its own. |
| **Persistence** | All of it. PostgreSQL is the only store (ADR-0005, v1.1 §2.4). |
| **Domain concepts** | Identity and row shape for all eleven. |
| **Tests** | `tests/integration/test_check_constraints.py` (43), `test_event_schema_constraints.py` (54), `test_schema_matches_migration.py` (whole-schema parity). |
| **Operational concerns** | 119 check constraints, 68 `RESTRICT` FKs, zero `SET NULL`. Four benign apparent import cycles from `__init__.py` re-exports — **do not refactor**, but do not add a new eager import above the existing ones either (`dependency-analysis.md` §2). |
| **Disposition** | **remain.** PostgreSQL-as-only-store is a recorded decision with stated adoption triggers; no measured pressure argues against it. |

#### 1.4a `persistence/schema.py`

| Field | Value |
|---|---|
| **Purpose** | All 44 tables (Stage 1 reported 43; recounted 2026-09-08), hand-written SQLAlchemy Core, in one 2,691-line module. |
| **Owns** | Table definitions, check constraints, foreign keys, composite tenant-safe keys (ADR-0004). |
| **Does not own** | Indexes — **all 33 live in migrations and `schema.py` declares zero** (R-12). That is the actual defect in this module, and it is not a size problem. |
| **Public API** | One `MetaData` object; imported by all 26 repository modules. |
| **Allowed deps** | SQLAlchemy Core. |
| **Forbidden deps** | As §1.4. |
| **Persistence** | It *is* the persistence declaration. |
| **Domain concepts** | Every entity's identity. |
| **Tests** | The parity guard compares tables and columns both ways and explicitly *"does not compare index sets"*. |
| **Operational concerns** | The one file every persistence change touches — a permanent merge-conflict surface in an agent-parallel workflow (R-20). |
| **Disposition** | **remain now; split OPTIONAL after M6.** The argument against splitting today is not conservatism, it is ordering: `schema.py` currently owns all 44 tables, *so nothing else can be said to own any of them* (`domain-model.md` §6). A split before ownership is declared invents boundaries by file size and then freezes them. M6 declares table → context → writing service as data with a test (AP-03, ADR-0019); only after that does a split follow a line that already means something. R-20's own remediation reads *"Do not split for aesthetics."* The index gap (R-12, AP-10) is fixed **in place at M6** and is independent of any split. |

#### 1.4b `persistence/spend_sweeper.py`

| Field | Value |
|---|---|
| **Purpose** | Reclaim reservations whose worker died between committing the debit and reporting the cost (ADR-0015 Amendment A1, T-08). 244 lines. |
| **Owns** | The abandoned-reservation sweep. Every reservation it touches lands in `expired_spent` at the reserved maximum with `actual_is_estimated=True`; **there is no path here that reaches `released`**. |
| **Does not own** | Settlement by a live caller — that is `persistence/spend.py`, driven by a `SpendReservationReceipt`. This module is driven by the *absence* of such a caller, which is why `AbandonedReservationSnapshot` deliberately carries no lease token. |
| **Public API** | `SpendReservationSweeper`. |
| **Allowed deps** | `smartmatch_domain.spend.expire_abandoned`, SQLAlchemy. |
| **Forbidden deps** | As §1.4. |
| **Persistence** | `spend_reservation`, `tenant_budget`, `spend_ceiling_bucket`. |
| **Domain concepts** | Spend / budget (`domain-model.md` §3.9). |
| **Tests** | `tests/integration/test_spend_reservation.py`, `tests/unit/test_spend_sweeper.py`. |
| **Operational concerns** | **It has no production caller.** `grep -rn SpendReservationSweeper` outside the module returns only test files. The analogous `sweep_expired_leases` *is* wired into the scheduled dispatch pass. |
| **Disposition** | **remain, attach.** The module is right — its docstring argues its own seam correctly, including why it is a sibling of `spend.py` rather than more of it. What is wrong is that nothing calls it. M1 calls it from the same scheduled dispatch pass that already runs `sweep_expired_leases` and extends `DispatchPassResponse` to report what it swept. This is an addition to a working mechanism, not a new one. Cited: R-08, AP-08, wip-analysis §4. |

---

## 2. `services/api` — `smartmatch_api`

**The governing fact for this whole section:** `smartmatch_api` appears in **no
import contract** and its manifest omits `smartmatch-persistence`, which it
imports in 33 files (R-05, R-06, `dependency-analysis.md` §3a). Every
**Allowed deps** / **Forbidden deps** row below is therefore a *target* to be
made enforceable at M2 (AP-01, ADR-0018), not a description of an existing gate.

The service-wide rules, stated once:

| Rule | Enforced by, after M2 |
|---|---|
| `smartmatch_api` may import all four `python/` packages | manifest declares them; layering contract extended |
| `smartmatch_api` may **not** import `smartmatch_worker`, and vice versa | new `forbidden` contract (AP-01) — today held by convention only (`dependency-analysis.md` §3c) |
| A router may **not** import another router | new `forbidden` contract (AP-02) — today violated twice |
| No router performs provider IO inline | `scan_forbidden.py:136`, already CI-gated (AP-04) |
| No router reads identity from a request body | `scan_forbidden.py:61,166`, already CI-gated |
| A gated-off capability owns no router | `main.py:CAPABILITY_SCOPED_ROUTERS` (AP-11) — never `if enabled:` |

### 2.1 `main.py` (562 L)

| Field | Value |
|---|---|
| **Purpose** | The API composition root and the capability gate. |
| **Owns** | App construction, exception-handler registration, `MaxBodySizeMiddleware`, `CAPABILITY_SCOPED_ROUTERS` (main.py:275), the four unconditional mounts (main.py:251-254), the FastAPI `description` that *is* the published contract's preamble, `/api/health`. |
| **Does not own** | Any route logic, any authorization rule, any provider construction beyond wiring what `registry.py` returns. |
| **Public API** | `app`. |
| **Allowed deps** | Every `smartmatch_api` module, all four `python/` packages, FastAPI. |
| **Forbidden deps** | `smartmatch_worker`. |
| **Persistence** | Creates the session factory (`main.py:47`, `create_session_factory`) — the import that R-05 is about. |
| **Domain concepts** | `Capability` (`smartmatch_domain.product_scope`). |
| **Tests** | Contract tests per router; the capability gate is exercised by scope tests. |
| **Operational concerns** | Its module docstring is **stale in two published places**: D1 (claims match-run/discovery/send "wait on" G1/G3/G4 while mounting all three, with `REGISTRY_STATUS == "approved"`) and D2 (the OpenAPI `description` advertises a generated TypeScript client that does not exist). D4 promises a readiness endpoint the audit could not find. |
| **Disposition** | **remain, deepen.** The composition-root shape is exactly right — capability by absence, not by `if enabled:`, is a stated non-negotiable and one of the repository's best properties (AP-11). What it gains: the M4 request-logging middleware **beside** `MaxBodySizeMiddleware` (R-03, AP-09); the M5 corrections to D1/D2/D4 plus the AP-06 test that makes a prose gate-claim assertable against `factor_registry.REGISTRY_STATUS` (R-15). No structural change. |

### 2.2 `dependencies.py` (296 L, fan-in 26)

| Field | Value |
|---|---|
| **Purpose** | Request-scoped dependencies: where the token becomes a principal, and where quota is consumed. |
| **Owns** | `get_session` (with the unconditional `finally: session.rollback()`), `get_token_verifier`, `_subject_for_token` (:86), `get_current_principal` (:119), `enforce_rate_limit` (:170), `QuotaCharge` (:224), `charge_quota` (:245). |
| **Does not own** | The policy itself (`smartmatch_authz`), or per-resource authorization (`job_authz.py`, and after M2 `unit_authz.py`). |
| **Public API** | `CurrentPrincipal`, `DbSession`, `QuotaCharge`, `charge_quota`, `enforce_rate_limit`, `get_current_principal`, `get_session`, `get_token_verifier`. |
| **Allowed deps** | `smartmatch_domain`, `smartmatch_persistence`, `smartmatch_providers`, `smartmatch_api.errors`, FastAPI. |
| **Forbidden deps** | Any router; `smartmatch_worker`. |
| **Persistence** | `PilotSessionRepository`, `PrincipalRepository`, `RateLimiter`. |
| **Domain concepts** | Principal, Membership, rate limit, spend quota. |
| **Tests** | Exercised by every contract test; ADR-0015's charge-before-refusal is e2e-visible. |
| **Operational concerns** | Load-bearing: a change here changes every route. The ordering — authenticate, then charge (committed in its own transaction), then do the work — is deliberate and both halves are required; charging inside the request transaction would be discarded by `get_session`'s rollback. |
| **Disposition** | **remain, deepen.** This is the A1b convergence seam. Both authentication mechanisms must resolve to *"a subject, then a server-side principal load"* with no branch that skips the load; `_subject_for_token`/`get_current_principal` appear to have that shape already and the A1b work is to keep it. Nothing moves here — the *point* is that A1b changes `get_token_verifier`'s injected object and nothing else (R-01, wip-analysis §1.4). |

### 2.3 `errors.py` (271 L, fan-in 26)

| Field | Value |
|---|---|
| **Purpose** | One error envelope and one set of exception handlers for the whole HTTP surface. |
| **Owns** | `ApiError`, `ErrorBody`, `ErrorEnvelope`, `error_response`, and seven handlers — authorization, consent violation, invalid transition, `ApiError`, idempotency conflict, request validation, `HTTPException`. |
| **Does not own** | Which status a given rule produces; that is the raising module's decision. |
| **Public API** | `ApiError`, `error_response`, the handler functions registered in `main.py`. |
| **Allowed deps** | `smartmatch_domain` exception types, `smartmatch_authz.AuthorizationError`, pydantic, FastAPI. |
| **Forbidden deps** | Any router; `smartmatch_persistence`; `smartmatch_worker`. |
| **Persistence** | None. |
| **Domain concepts** | Consent violation, invalid transition, idempotency conflict — the domain's refusals, surfaced. |
| **Tests** | Contract tests assert the envelope shape per route family. |
| **Operational concerns** | **A refusal here currently leaves no trace.** 22 of 25 router modules log nothing; an authz refusal, a rate-limit rejection or a 500 in a synchronous router is invisible outside PostgreSQL, and only job work writes `job_event` rows (R-03). |
| **Disposition** | **remain, deepen.** A deep module — simple interface over the whole HTTP error contract — and exactly the right shape. It gains one property at M4: **every `ApiError` path logs once, with its code** (AP-09). One log line per refusal, in the module that already owns every refusal. No tracing vendor. |

### 2.4 `units.py` (150 L, fan-in 18)

| Field | Value |
|---|---|
| **Purpose** | The org-unit read primitives shared by the 46-of-57 unit-scoped paths. |
| **Owns** | `load_unit_or_404` (:44) — the 404-vs-403 decision, made **once**; `units_in_subtree` (:82); `MAX_SUBTREE_UNITS`; `OrgUnitRow`. |
| **Does not own** | Authorization. It loads and scopes; `smartmatch_authz` decides. |
| **Public API** | `MAX_SUBTREE_UNITS`, `OrgUnitRow`, `load_unit_or_404`, `units_in_subtree`. |
| **Allowed deps** | `smartmatch_persistence`, `smartmatch_authz`, `smartmatch_api.errors`. |
| **Forbidden deps** | Any router; `smartmatch_worker`. |
| **Persistence** | `org_unit`, via `ltree`. |
| **Domain concepts** | Org unit — the universal scope (`domain-model.md` §3.1). |
| **Tests** | Exercised by every unit-scoped contract test. |
| **Operational concerns** | `MAX_SUBTREE_UNITS` is the repository's existing pattern for bounding an unbounded read, and it is the pattern AP-12 generalises to the metrics drill-down (R-07). |
| **Disposition** | **remain.** A module that makes one cross-cutting decision once, with a bound already in it. It is the *model* for the M6 work, not a subject of it. |

### 2.5 `utils.py` (18 L, fan-in 25)

| Field | Value |
|---|---|
| **Purpose** | One function: `utc_now()`. |
| **Owns** | The clock, as read from the request path. One place to patch in tests; one place a naive `datetime.now()` cannot hide. |
| **Does not own** | Anything else — and that is the entire issue. |
| **Public API** | `utc_now`. |
| **Allowed deps** | `datetime`. |
| **Forbidden deps** | Everything else. |
| **Persistence** | None. |
| **Domain concepts** | None. |
| **Tests** | Implicit in every time-sensitive test. |
| **Operational concerns** | Its docstring cites a real defect as justification — F-003, the legacy ICS generator claiming UTC for local times. The content and the rationale are correct. |
| **Disposition** | **move → `smartmatch_api/clock.py`.** The argument is not tidiness, it is gravity. A module named `utils` with the second-highest fan-in in the API is the textbook seed of a dumping ground: the next helper with no obvious home lands here *because the import is already everywhere*, and nothing enforces the current 18 lines. Renaming it to `clock.py` makes "does this belong here?" answerable — a second, unrelated helper has no plausible reason to be added to a module called `clock`. 25 import sites change mechanically; no behaviour changes. Cited: R-19, `dependency-analysis.md` §4. This is the cheapest preventive change in the plan and it lands at M1. |

### 2.6 `config.py` (176 L, fan-in 11)

| Field | Value |
|---|---|
| **Purpose** | `Settings` (pydantic-settings) and `get_settings()`. |
| **Owns** | Environment reading and validation for the API, including the product scope that drives `capability_enabled`. |
| **Does not own** | Worker configuration — `smartmatch_worker/config.py` is separate and must stay so; the two services have different secrets and different failure modes. |
| **Public API** | `Settings`, `get_settings`. |
| **Allowed deps** | `smartmatch_domain.product_scope`, pydantic-settings. |
| **Forbidden deps** | Any router; `smartmatch_worker`. |
| **Persistence** | None (holds the DSN; does not connect). |
| **Domain concepts** | `Capability`, `ProductScope`. |
| **Tests** | Settings validation tests. |
| **Disposition** | **remain.** Composition asks the domain policy rather than restating it (`main.py:259-263`) — "which product is this" answered in one place and read in two. Correct as is. |

### 2.7 `commands.py` (249 L, fan-in 7)

| Field | Value |
|---|---|
| **Purpose** | The command-submission seam: the one function that turns a request into durable intent. |
| **Owns** | `submit_command` (:87) and `CommandAccepted` (:71) — the job row, the outbox row and the idempotency record written in one transaction. |
| **Does not own** | Execution. Nothing in the API request path talks to a queue; the dispatcher is *deliberately the only component that creates tasks* (`worker/dispatcher.py` docstring). |
| **Public API** | `CommandAccepted`, `submit_command`. |
| **Allowed deps** | `smartmatch_persistence` (jobs, outbox, idempotency), `smartmatch_domain.jobs`. |
| **Forbidden deps** | `smartmatch_providers` task clients; `smartmatch_worker`; any router. |
| **Persistence** | `job`, `outbox_record`, `idempotency_record`, `job_event`. |
| **Domain concepts** | Job (`domain-model.md` §3.3). |
| **Tests** | 44 tests across the command path, including crash-window cases. |
| **Operational concerns** | Four routers submit; three command types reach the worker (U1, resolved). `speaker_contact.create`, `job.redrive` and `job.abandon` reserve an idempotency key **only** — they create no job and no outbox row, so no handler is expected for them. That distinction is currently invisible to a reader. |
| **Disposition** | **remain.** The seam is correct and AP-04's "provider-touching work is a submitted command" depends on it staying the single entry. It is a *subject* of the M1 registry-map test rather than a target of change: the test reads what any router can submit and asserts each type is registered or explicitly refused (AP-05, ADR-0023). |

### 2.8 `job_authz.py` (299 L, fan-in 4)

| Field | Value |
|---|---|
| **Purpose** | Authorization for every operation over a job, in one place. |
| **Owns** | `authorize_job_read`, `authorize_job_command`, and the documented five-step evaluation order (suspension → tenant mismatch → explicit deny → actor exception → inherited unit grant). |
| **Does not own** | Unit-scoped authorization for non-job resources — which is precisely the gap `unit_authz.py` fills at M2. |
| **Public API** | The two authorize functions, consumed by `routers/jobs.py` and `routers/redrive.py`. |
| **Allowed deps** | `smartmatch_authz`, `smartmatch_persistence.jobs`, `smartmatch_api.errors`. |
| **Forbidden deps** | Any router. |
| **Persistence** | `job` (with `owning_unit_id`, migration `0006`), `resource_grant`. |
| **Domain concepts** | Job, Principal, Resource grant. |
| **Tests** | Job authorization tests across all four job routes. |
| **Operational concerns** | Its docstring records the *defect it fixed*: two routers each carrying a `_authorize_job_read` applying **different subsets of the same policy to the same resource**, so a per-job deny was obeyed by `/redrive` and ignored by the status read. |
| **Disposition** | **remain — and it is the precedent.** This module is why AP-02 is written the way it is. It demonstrates the whole pattern: name the resource, put its authorization in an owned module, record in the docstring what drifted before. `dependency-analysis.md` §4 calls it *exemplary*; §3b says the router→router imports "should follow" it. Nothing to change; everything to copy. |

### 2.9 `match_run_evidence.py` (531 L), `pipeline_provisioning.py` (763 L), `zip_proximity.py` (195 L)

| Field | Value |
|---|---|
| **Purpose** | Three API-layer modules that assemble a response or provision a record from several repositories and domain functions: match-run evidence and explanation assembly; pipeline record provisioning; ZCTA-centroid proximity lookup for the API surface. |
| **Owns** | Assembly and orchestration that is genuinely HTTP-shaped — which rows a response needs, in what order — and which therefore cannot live in the pure domain. |
| **Does not own** | Any scoring rule (`domain/scoring.py`, `domain/explanation.py`), any distance model (`domain/factors/proximity.py`, `domain/zcta_centroids.py`), any pipeline stage legality (`domain/pipeline.py`). |
| **Public API** | Called by `routers/match_runs.py`, `routers/pipeline.py`, `routers/events.py` and their neighbours. |
| **Allowed deps** | `smartmatch_domain`, `smartmatch_persistence`, `smartmatch_api.{errors,units,clock}`. |
| **Forbidden deps** | Any router (the dependency runs router → these, never back); `smartmatch_worker`. |
| **Persistence** | Read-mostly across `match_run`, `pipeline_record`, `event`. |
| **Domain concepts** | Match run, Pipeline record, proximity factor. |
| **Tests** | Contract tests over the routes that consume them; e2e 08c, 11, 12. |
| **Operational concerns** | `pipeline_provisioning.py` at 763 lines is within the repository's stated 800-line module ceiling (cited in `spend_sweeper.py`'s docstring) but has no headroom. |
| **Disposition** | **remain.** These are already the correct answer to "a router got too big": behaviour extracted to a named module with a single subject, called by one or two routers. They are not shared authorization helpers and AP-02 does not touch them. Splitting `pipeline_provisioning.py` on line count would repeat the mistake the handoff's anti-goals forbid for `schema.py`; if it grows past the ceiling, split it along a named seam, as `spend_sweeper.py` was split from `spend.py`. |

### 2.10 `routers/` — 25 modules, 28 `APIRouter` objects

| Field | Value |
|---|---|
| **Purpose** | The HTTP surface: 57 published paths, 46 of them under `/v1/units/{unit_id}/…`. |
| **Owns** | Request/response models, route-level orchestration, per-route rate limits, and the *submission* of commands. |
| **Does not own** | Provider IO (AP-04, `scan_forbidden.py:136`); identity from a body (`scan_forbidden.py:61,166`); another router's helpers (AP-02, violated twice today); mounting themselves (`main.py` owns the capability gate). |
| **Public API** | `router` (and, for three modules, a second `public_router` / `connector_router` — the unauthenticated or differently-scoped half, split deliberately so that "this route takes no principal" is visible at the mount site rather than inside the handler). |
| **Allowed deps** | `smartmatch_api.{dependencies,errors,units,clock,commands,config,job_authz,unit_authz,match_run_evidence,pipeline_provisioning,zip_proximity}`; all four `python/` packages. |
| **Forbidden deps** | **Any other `smartmatch_api.routers.*` module** (new contract, M2); `smartmatch_worker`; any provider client constructed inline. |
| **Persistence** | Via repositories only. |
| **Domain concepts** | All eleven, distributed by capability. |
| **Tests** | `tests/contract/` per router family; 26-step e2e walk against a live appliance. |
| **Operational concerns** | Rate limiting is applied in 20 of 25 modules; `metrics` is the one indefensible omission — `GET /v1/units/{u}/metrics/{name}/drill-down` is unbounded, authenticated, database-heavy work (R-07). 22 of 25 log nothing (R-03). |
| **Disposition** | **split.** Exactly two symbols move, and only these two: `cba_contacts.SPEAKER_CONTACT_READ_RATE_LIMIT` + `cba_contacts._authorize_speaker_contacts` (imported at `routers/cba_contact_channels.py:131`) and `outreach.READ_RATE_LIMIT` + `outreach._authorize_outreach` (imported at `routers/outreach_contacts.py:109`) become the public surface of a new **`services/api/smartmatch_api/unit_authz.py`**, following `job_authz.py` exactly — including a docstring that records what it is preventing. The *behaviour* those imports encode is right and `main.py`'s router table argues it correctly: *"one question about a unit's outreach with one answer"*. What is wrong is the mechanism. Reaching across a sibling module for an underscore-prefixed name makes the router layer's public surface undefinable, and a rename in `outreach.py` silently breaks `outreach_contacts.py` with no contract to catch it. With the two helpers relocated, the router→router `forbidden` contract has zero exceptions and can be added the same day. Cited: R-06, AP-02, `dependency-analysis.md` §3b, `job_authz.py` precedent. Everything else in `routers/` **remains**; the M6 additions to `metrics` (rate limit + bounded rows) are behaviour inside an unchanged module. |

---

## 3. `services/worker` — `smartmatch_worker`

Service-wide rules, stated once and enforced from M2 (AP-01):

| Rule | Enforced by |
|---|---|
| `smartmatch_worker` may import all four `python/` packages | manifest declares `smartmatch-persistence` (10 files import it today, undeclared) |
| `smartmatch_worker` may **not** import `smartmatch_api` | new `forbidden` contract |
| Only the worker executes a command's work | v1.1 §1.6; enforced on the API side by `scan_forbidden.py:136` |
| A gated-off capability has no registered handler | `handlers.default_registry` docstring (AP-11) |

### 3.1 `worker/main.py` (923 L)

| Field | Value |
|---|---|
| **Purpose** | The worker HTTP boundary **and** the composition root. Four endpoints: health, `/tasks/execute`, `/operations/dispatch`, and the pass heartbeat. |
| **Owns** | The order of operations that *is* the security property — verify OIDC **before the body is read**, then parse identifiers only, then execute against the job re-read from PostgreSQL. The status-code contract with the queue. The separation of the two callers (separate audiences, separate allowlists, separate verifiers: Cloud Tasks may deliver and may not dispatch; Cloud Scheduler the reverse). Root composition of `with_outreach_send` (:451-489, unconditional when `registry_is_ours`) and `with_paid_extraction` (:491, only when all three spend ceilings are named). |
| **Does not own** | Handler bodies; claim semantics (`execution.py`); task creation (`dispatcher.py`). |
| **Public API** | `app`; the four routes. |
| **Allowed deps** | Every `smartmatch_worker` module, all four `python/` packages, FastAPI. |
| **Forbidden deps** | `smartmatch_api`. |
| **Persistence** | Session factory; the dispatch pass writes leases and outbox state. |
| **Domain concepts** | Job, Spend, Outreach send. |
| **Tests** | Delivery and dispatch tests; e2e 20 sends through the fixture provider. |
| **Operational concerns** | The docstring states the delivery contract precisely — `200` on a duplicate (at-least-once makes it the normal case), `503` on the dispatcher race (a single transaction wide; acknowledging would strand the job, since `queued` has no route to `redrive_pending`), `401`/`403`/`501`/`500` with reasons. **That docstring is the source text for ADR-0021.** |
| **Disposition** | **remain, deepen.** The root-composition design is argued, not accidental: a registry function that takes no arguments cannot supply a provider, a From address, an HMAC key and a session factory, and `handlers` importing `outreach`/`paid_extraction` to reach them would make a cycle out of a genuinely one-way dependency. The asymmetry between the two — outreach composed unconditionally because *absence means fixture mode*, paid extraction withheld because *absence must mean cannot spend money* — is exactly right and must be preserved verbatim. What it gains: the M1 spend-sweeper call in the dispatch pass beside `sweep_expired_leases` (R-08), and the M7 ADR-0021 delivery-contract test run against `FixtureTaskQueue` so the docstring becomes assertable (R-01). |

### 3.2 `worker/handlers.py` (1,369 L) and `default_registry()`

| Field | Value |
|---|---|
| **Purpose** | Command handlers and the registry that routes to them — the only place a durable command's actual work is allowed to happen. |
| **Owns** | `CommandRegistry`, `CommandContext`, `default_registry()` (:1349), `handle_noop`, `handle_import_create`, `handle_match_run_create`; the three failure types (`PolicyFailure`→`failed_policy`, `BudgetFailure`→`failed_budget`, `ProviderFailure`→`failed_provider`, the only re-drivable one). |
| **Does not own** | The two root-composed handlers (`outreach.send`, `extraction.paid_pages`) — deliberately, see §3.1. |
| **Public API** | `default_registry()`, the failure types, `CommandContext`. |
| **Allowed deps** | All four `python/` packages; `smartmatch_worker.column_contract`. |
| **Forbidden deps** | `smartmatch_api`; `smartmatch_worker.outreach` and `.paid_extraction` (the one-way dependency runs the other way, and reversing it makes a cycle). |
| **Persistence** | Reads the authoritative payload from `job.payload` (migration `0005`), **never from the delivery** — "a payload the worker trusts is a payload anyone who reaches the queue can dictate". Writes into the executor-owned session; never commits or rolls back. |
| **Domain concepts** | Job, Import batch, Match run. |
| **Tests** | Handler tests per type; e2e 20. |
| **Operational concerns** | **A miss is a terminal refusal, not a crash** — the docstring names the alternative (log a warning, return success) as "the single worst outcome available here". Fail-closed is correct. But nothing asserts the map, and the two root-composed handlers are invisible to a reader of `default_registry()` (R-04, U1). |
| **Disposition** | **remain, deepen — with the AP-05 test.** The registry's shape is right and the refusal policy is right; the design rule *"a handler added ahead of its gate is a handler someone will trigger"* is a genuine safety property and must not be relaxed to make the map easier to read. What is missing is an assertion, and the assertion **is** the map: a test that collects every command type any router can submit and requires each to be registered in `default_registry()`, composed at the root, or on an explicit intentionally-refused list — with the idempotency-scope-only names (`speaker_contact.create`, `job.redrive`, `job.abandon`) recorded as expecting no handler. That test turns the hardest research question in the codebase into a build failure. Cited: R-04, AP-05, ADR-0023, U1. |

### 3.3 `worker/dispatcher.py` (1,152 L)

| Field | Value |
|---|---|
| **Purpose** | Move durable intents from the outbox into the queue, and record the evidence that it did. |
| **Owns** | The outbox claim (`SKIP LOCKED` CTE, ADR-0005), deterministic task naming (ADR-0007), dispatch evidence. |
| **Does not own** | Execution; the queue implementation (injected `TaskQueue`). |
| **Public API** | The dispatch pass entry point and `DispatchPassResponse`. |
| **Allowed deps** | `smartmatch_persistence.outbox/jobs`, `smartmatch_providers.tasks`, `smartmatch_domain.jobs`. |
| **Forbidden deps** | `smartmatch_api`. |
| **Persistence** | `outbox_record`, `job`, `job_event`, `concurrency_lease`. |
| **Domain concepts** | Job. |
| **Tests** | Part of the 44-test command-path suite, including crash windows. |
| **Operational concerns** | **The only component that creates tasks** — so a browser request can never enqueue work not first committed to PostgreSQL. `DispatchPassResponse` already carries `sweep_failed` / `timed_out` counters, which is the shape the M1 spend-sweep report extends. |
| **Disposition** | **remain.** Explicitly listed under handoff §3 "what is stable — do not touch". Its crash-safety is proven against `FixtureTaskQueue`; validating it against a live queue is an adapter question (`FUTURE_FEATURE_INTEGRATION.md` §4), not a dispatcher question. |

### 3.4 `worker/execution.py` (628 L)

| Field | Value |
|---|---|
| **Purpose** | Execute one delivered command. |
| **Owns** | The claim — the whole safety argument against at-least-once delivery — lease + generation, the outcome transaction, `job.outcome_discarded` when cancellation or the J9 stalled-job sweep wins first, and the call to `sweep_expired_leases`. |
| **Does not own** | What the work is (handlers); who may deliver (`identity.py`). |
| **Public API** | The execute entry point. |
| **Allowed deps** | `smartmatch_worker.handlers`, `smartmatch_persistence.jobs`, `smartmatch_domain.jobs`. |
| **Forbidden deps** | `smartmatch_api`. |
| **Persistence** | `job`, `job_event`, `concurrency_lease`. |
| **Domain concepts** | Job, its 12 states. |
| **Tests** | Duplicate-delivery and crash-window tests. |
| **Operational concerns** | It owns the transaction a handler stages into. A handler that committed would make work durable that the executor may need to discard. |
| **Disposition** | **remain.** Stable, tested, load-bearing. |

### 3.5 `worker/identity.py` (682 L) + `worker/signature_backend.py` (114 L)

| Field | Value |
|---|---|
| **Purpose** | OIDC task-identity verification at the worker boundary — the control that makes "only the queue may invoke the worker" true rather than intended. Resolves security finding S-001. |
| **Owns** | Verification of the caller's OIDC token; the `SignatureVerifier` / `JsonWebKey` seam, deliberately holding *no implementations*. |
| **Does not own** | End-user identity — that is `providers/jwks.py` on the API side. Two different trust boundaries; conflating them would be a serious error. |
| **Public API** | `build_task_verifier(expected_audience, allowed_service_accounts)`. |
| **Allowed deps** | `smartmatch_providers`, crypto. |
| **Forbidden deps** | `smartmatch_api`; `smartmatch_persistence`. |
| **Persistence** | None. |
| **Domain concepts** | None. |
| **Tests** | Verifier tests; the `501`-when-unconfigured path. |
| **Operational concerns** | `config.py` supplies **no default audience and no default allowlist**, so a deployment that forgets task identity gets a worker that refuses everything rather than one that accepts anything. The scheduler verifier is built from the scheduler's own settings and never falls back to the task audience — otherwise a queue-minted token could drive dispatch. |
| **Disposition** | **remain.** A boundary whose failure mode on misconfiguration is total refusal needs no restructuring. `signature_backend.py` being empty of implementations is the point, not an omission. |

### 3.6 `worker/local_tasks.py` (507 L) and `worker/local_scheduler.py` (231 L)

| Field | Value |
|---|---|
| **Purpose** | A PostgreSQL-backed loopback queue and a scheduler sidecar, for `docker compose up`. |
| **Owns** | Local delivery and local periodic dispatch, opt-in and refusing to boot without both a task token and a validated loopback target. |
| **Does not own** | Any claim to be Cloud Tasks or Cloud Scheduler. Both docstrings say so in bold and say that S-001/F5 deployment work stays open. |
| **Public API** | Composed at the root only when no queue was injected *and* the deployment explicitly enabled it. |
| **Allowed deps** | `smartmatch_persistence`, `smartmatch_providers.tasks`, httpx (loopback). |
| **Forbidden deps** | `smartmatch_api`. |
| **Persistence** | A local queue table. |
| **Domain concepts** | None. |
| **Tests** | Compose-path tests; the 26-step e2e walk runs against this appliance. |
| **Operational concerns** | This is what the pilot actually runs on (R-18). Calling it "local development only" understates its role; ADR-0022 records that the appliance **is** the production topology. |
| **Disposition** | **remain.** Two modules that state precisely what they are not, and are gated so they cannot be mistaken for what they emulate. Under ADR-0022 they stop reading as interim scaffolding and start reading as the current topology's queue. |

### 3.7 `worker/outreach.py` (607 L)

| Field | Value |
|---|---|
| **Purpose** | Execute `outreach.send` — the only place in the platform where a message actually leaves. |
| **Owns** | Send execution, consent re-check at send time, suppression, `delivery_event` recording, unsubscribe token signing. |
| **Does not own** | Composition of a draft (API side), the template registry (`domain/outreach.py`, closed — bodies cannot be caller-supplied), or its own construction (root-composed with provider, From address, HMAC key and session factory). |
| **Public API** | `build_outreach_send_handler`, `with_outreach_send`, `OUTREACH_SEND_COMMAND_TYPE`. |
| **Allowed deps** | `smartmatch_worker.handlers` (for `CommandContext` and the failure types — the one-way edge), `smartmatch_providers`, `smartmatch_persistence`, `smartmatch_domain`. |
| **Forbidden deps** | `smartmatch_api`. |
| **Persistence** | `outreach_send`, `delivery_event`, `suppression_record`, `contact_channel`. |
| **Domain concepts** | Outreach draft → send → delivery, Consent (`domain-model.md` §3.6, §3.10). |
| **Tests** | e2e 18, 19, 20, 21 — including that a recipient who unsubscribes after approval is not written to. |
| **Operational concerns** | *"To answer 'under what conditions does this system email a person', a reader has to read one function."* That property is worth more than any refactor could add. |
| **Disposition** | **remain.** Its command type is one of the three that reach the worker and is composed at the root — the AP-05 test must recognise root composition, not just `default_registry()`, or it will report a false gap here. |

### 3.8 `worker/paid_extraction.py` (617 L)

| Field | Value |
|---|---|
| **Purpose** | The one handler path that reserves money before spending it (ADR-0015 A1). |
| **Owns** | Reserve-max → call → reconcile-to-actual ordering. |
| **Does not own** | The sweep of reservations nobody came back for (`persistence/spend_sweeper.py`, §1.4b) — the two halves of A1, and only one of them is attached. |
| **Public API** | `build_paid_extraction_handler`, `with_paid_extraction`, the `extraction.paid_pages` command type (:123). |
| **Allowed deps** | `smartmatch_worker.handlers`, `smartmatch_providers.paid`, `smartmatch_persistence.spend`. |
| **Forbidden deps** | `smartmatch_api`. |
| **Persistence** | `spend_reservation`, `tenant_budget`, `spend_ceiling_bucket`. |
| **Domain concepts** | Spend (`domain-model.md` §3.9). |
| **Tests** | Reservation and reconciliation tests. |
| **Operational concerns** | Composed **only** when all three ceilings are configured; otherwise a delivery of this type meets the registry's existing terminal refusal. No router submits it over HTTP today. |
| **Disposition** | **remain.** Withholding the handler when ceilings are absent is the correct reading of "capability by absence" for a money-spending path (AP-11). The AP-05 test records `extraction.paid_pages` as *conditionally composed, no HTTP submitter* rather than as a gap. |

### 3.9 `worker/event_ingest.py` (326 L) and `worker/column_contract.py` (292 L)

| Field | Value |
|---|---|
| **Purpose** | Two adapters that carry file-shaped inputs into the worker: fixture ingest → event persistence (via the pure Stage 0 parsers and ADR-0012 identity resolution), and the ratified pilot column contract (`docs/pilot-data/columns.yaml`) → import validation. |
| **Owns** | The IO that the domain may not do. |
| **Does not own** | Parsing rules (`domain/event_candidate`, `domain/ingest.validate_columns`) or identity resolution rules (ADR-0012). |
| **Public API** | Called from handlers. |
| **Allowed deps** | `smartmatch_domain`, `smartmatch_providers.fixture_ingest`, `smartmatch_persistence.events`, `pathlib`, `yaml`. |
| **Forbidden deps** | `smartmatch_api`. |
| **Persistence** | `event`, `event_tag`, `import_batch`, `review_item`. |
| **Domain concepts** | Event identity and provenance; Import batch. |
| **Tests** | Ingest integration tests. |
| **Operational concerns** | `column_contract.py` closed a real gap — the ratified contract had sat unread while `handlers.py` called `validate_columns(required=(), optional=())`. |
| **Disposition** | **remain.** These are the canonical example of the purity contract producing a correct placement: the rule stays in the domain, the file read lives in the service that may read files. Exactly what AP-01 should keep true. |

### 3.10 `worker/config.py` (557 L)

| Field | Value |
|---|---|
| **Purpose** | Worker configuration, validated once at boot. |
| **Owns** | Audiences, service-account allowlists, spend ceilings, outreach live-mode and secrets, the local-task-queue opt-in and its refusal to boot half-configured. |
| **Does not own** | API settings — separate module, separate service, different secrets. |
| **Public API** | The resolved settings object read at the composition root. |
| **Allowed deps** | pydantic-settings, `smartmatch_domain` vocabularies. |
| **Forbidden deps** | `smartmatch_api`. |
| **Persistence** | None. |
| **Domain concepts** | `Edition`, spend ceilings. |
| **Tests** | Boot-refusal tests. |
| **Operational concerns** | **No default that would make the worker easier to reach.** That principle is the reason a misconfigured worker is unreachable rather than open. |
| **Disposition** | **remain.** |

---

## 4. Repository-level modules

### 4.1 `tools/`

| Field | Value |
|---|---|
| **Purpose** | The CI gates, plus seeding and generation scripts. 16 modules. |
| **Owns** | `scan_forbidden.py` (provider IO in handlers :136; caller-supplied identity :61,166; fabricated scores :69; module-level mutable state :99; mutating GET :121), `scan_cba_terminology.py`, `env_isolation_check.py`, `export_openapi.py --check`, `agent_memory_check.py`, `supply_chain.py`, the `seed_pilot_*` and `generate_*` scripts. |
| **Does not own** | Anything at runtime. Nothing in `services/` imports `tools/`. |
| **Public API** | `make check` = format-check, lint, typecheck, imports, test, scan, memory, licenses, infra-check. |
| **Allowed deps** | `smartmatch_domain` (5 files), `smartmatch_persistence` (7 files), standard library. |
| **Forbidden deps** | `smartmatch_api`, `smartmatch_worker` (a gate that imports the thing it gates can be disabled by the thing it gates). |
| **Persistence** | The seed scripts write; the scanners do not. |
| **Domain concepts** | Terminology (`scan_cba_terminology.py` scoped so it does not demand renaming the authz `membership` row). |
| **Tests** | **The gates are themselves tested** — `tests/unit/test_forbidden_scanner.py`, `tests/unit/test_adr_index.py`. |
| **Operational concerns** | Non-negotiable 13: never weaken an existing gate. Every Stage 2 increment adds gates and relaxes none. |
| **Disposition** | **remain, deepen.** This directory is why the audit's leakage search came back empty. It gains, across the plan: the AP-05 registry-map test, the AP-06 gate-claim test, the AP-03 table-ownership test, the AP-10 both-ways index parity, the AP-13 plan-status check, and the deferred TypeScript drift gate already named at the bottom of `verify.yml`. New gates, same mechanism. |

### 4.2 `db/migrations` (34 revisions)

| Field | Value |
|---|---|
| **Purpose** | The forward history of the schema. Alembic, one transaction per migration (ADR-0009). |
| **Owns** | Every structural change, and — today, wrongly — **all 33 indexes**. |
| **Does not own** | The declarative schema (`schema.py`); the two are kept honest by the parity test. |
| **Public API** | `alembic upgrade head`. |
| **Allowed deps** | `smartmatch_persistence.schema`, Alembic, SQLAlchemy. |
| **Forbidden deps** | `smartmatch_api`, `smartmatch_worker`, `smartmatch_providers`. |
| **Persistence** | All of it. |
| **Domain concepts** | Reading migrations in sequence records decisions: `0014` added a ledger reversal target, `0015` removed unauthorized reversal; `0032` added `scoring_mode`. |
| **Tests** | Forward-tested from empty on every PR; whole-schema parity. |
| **Operational concerns** | **`downgrade()` bodies are never exercised** (R-14, OQ-S2-004). Either they are supported and tested upgrade→downgrade→upgrade, or they are not and the repository says so and stops writing them. |
| **Disposition** | **remain.** Migrations stay the sole mechanism for applying change; ADR-0004's hand-written schema and ADR-0009's one-transaction rule are untouched. Indexes move *into* `schema.py` alongside their tables at M6 and continue to be **applied** by migrations — that is a change to where an index is declared, not to how it is deployed. |

### 4.3 `contracts/openapi/smartmatch.json`

| Field | Value |
|---|---|
| **Purpose** | The published contract: 57 paths, 120 schemas, CI-gated for freshness. |
| **Owns** | The wire shape of every `/v1` path. |
| **Does not own** | Any consumer. |
| **Public API** | The document itself; `tools/export_openapi.py --check` is the freshness gate. |
| **Allowed deps** | Generated from `smartmatch_api`. |
| **Forbidden deps** | Nothing hand-edits it. |
| **Persistence** | None. |
| **Domain concepts** | All of them, in wire form. |
| **Tests** | The staleness gate in `verify.yml`. |
| **Operational concerns** | Its own `description` claims *"the TypeScript client is generated from it and never hand-maintained"* (D2) — a **false statement published in the contract**. The freshness gate protects the contract and nothing protects the consumer: a backend field rename passes every gate in `verify.yml` and reaches a user as a runtime `undefined`. |
| **Disposition** | **remain, deepen.** The contract-first design is correct; what is missing is the second half of the loop. M3 generates `clients/typescript` from this document and adds the drift gate already listed as deferred at the bottom of `verify.yml` (R-02, AP-07, ADR-0020). The `ruff` `extend-exclude = ["clients/typescript"]` fossil (D5) stops being a fossil the day the directory exists. |

---

## 5. `apps/web/legacy-frontend`

The largest single WIP surface, and the only place where the target disposition
is genuinely mixed.

### 5.1 `src/lib/api.ts` (4,238 L)

| Field | Value |
|---|---|
| **Purpose** | The hand-written legacy client. |
| **Owns** | 24 `/api/*` calls that **no service serves** — crawler, matching, QR, feedback, agentic-workflow streaming, `/api/data/*` — plus transcribed types including `Specialist`, `CppEvent`, `CrawlerEvent`. |
| **Does not own** | The `/v1` surface, which is reached by inline `fetch` across 49 files (42 distinct endpoints). |
| **Public API** | Whatever each of the seven legacy pages imports. |
| **Allowed deps** | (target) `clients/typescript` only. |
| **Forbidden deps** | (target) a hand-written type for any `/v1` response. |
| **Persistence** | None. |
| **Domain concepts** | It is the largest surviving carrier of retired IA-West vocabulary — `Specialist` is a *type*, not copy, so `scan_cba_terminology.py` cannot see it, and the next agent will read it as current (`domain-model.md` §3.5). |
| **Tests** | `tests/e2e/…::test_16_the_portal_pages_have_no_backend_in_this_repository` asserts the `/api/*` situation from the backend side. |
| **Operational concerns** | Deleting it wholesale breaks seven routed pages that users can reach. |
| **Disposition** | **become an adapter, then shrink.** Its `/v1` surface is re-expressed as thin forwarders over the generated client so that no `/v1` response type is transcribed anywhere in this file; each migrated page then imports the generated client directly and its forwarder goes. The `/api/*` half does not become an adapter over anything, because nothing serves it — it shrinks to zero as OQ-S2-002 resolves each page. M3 migrates **one** page as the pattern; migrating 49 files in one change is the failure mode R-02's remediation explicitly warns against. Cited: R-02, AP-07, ADR-0020. |

### 5.2 `OutreachWorkflowModal.tsx`, `AgenticOutreachPanel.tsx`, `FeedbackForm.tsx`

| Field | Value |
|---|---|
| **Purpose** | None. Referenced by nothing in `src/`. |
| **Owns** | Nothing. |
| **Does not own** | Nothing. |
| **Public API** | None reachable. |
| **Allowed / Forbidden deps** | n/a. |
| **Persistence** | None. |
| **Domain concepts** | `AgenticOutreachPanel` names an "agentic" capability that **ADR-0003 excludes from Foundation**. |
| **Tests** | None. |
| **Operational concerns** | They compile, so every build carries them, and a future agent may read `AgenticOutreachPanel` as an invitation to "just wire this up" against a standing decision. |
| **Disposition** | **disappear.** Delete all three at M8. Git retains them. This is the one M8 item not blocked on OQ-S2-002, because deletion of an unreferenced component requires no product decision. Cited: R-06b, AP-08. |

### 5.3 The seven legacy pages — `Dashboard`, `Opportunities`, `Volunteers`, `Pipeline`, `Calendar`, `Outreach`, `AIMatching`

| Field | Value |
|---|---|
| **Purpose** | Routed, reachable pages backed by 24 endpoints nothing serves. |
| **Owns** | The user-visible consequence of §5.1. |
| **Does not own** | Any working data path. |
| **Public API** | Routes in `src/app/routes.tsx`. |
| **Allowed deps** | (target) the generated client. |
| **Forbidden deps** | New `/api/*` calls. |
| **Persistence** | None. |
| **Domain concepts** | `Calendar.tsx` renders an explicit "feed retired" state with `CALENDAR_FEED_RETIRED_REASON` and an `isRetiredRoute` predicate — correct behaviour under ADR-0011 and DESIGN.md §1.2 (no silent fallback shown as success). |
| **Tests** | e2e 16. |
| **Operational concerns** | **The notice is now factually wrong** (D3): it claims `routers/events.py` declares no handlers and the contract exposes no event operation. `routers/events.py` is 571 lines with handlers and the contract publishes two event paths. The page shows a retirement notice for a feed whose replacement exists. |
| **Disposition** | **remain — with the notice corrected at M5 — pending OQ-S2-002.** Port / delete / correct-the-notice is an owner's decision, not engineering's, so the engineering default is the option that is honest today and forecloses nothing tomorrow. Doing nothing is the one actively misleading option, because the notice currently lies; correcting the text is cheap, reversible, and independent of the eventual per-page verdict. Cited: R-17, D3, OQ-S2-002. |

### 5.4 `src/lib/*` (other modules), `src/app/`, `src/components/`

| Field | Value |
|---|---|
| **Purpose** | The working SPA: `queryClient.ts`, `principal.ts`, `principalKey.ts`, `session.ts`, `productScope.ts`, `roleLabels.ts`, `metrics.ts`, `calendarCoverage.ts`, `calendarProvenance.ts`, `cbaTaxonomies.ts`, `eventDates.ts`, `signals.ts`, plus pages, components and hooks. |
| **Owns** | Principal-scoped cache keying (`principalKey.ts` + `queryClient.ts`) — a security-relevant invariant; the frontend half of the product-scope policy (`productScope.ts`, mirroring `smartmatch_domain.product_scope`); the ADR-0011 rendering rule that a `null` score is never a `0`. |
| **Does not own** | Any `/v1` response type, after M3. |
| **Allowed deps** | (target) `clients/typescript`. |
| **Forbidden deps** | Hand-transcribed contract types; `/api/*`. |
| **Persistence** | Browser cache only. |
| **Domain concepts** | Product scope, Principal, score presentation. |
| **Tests** | See §5.5. |
| **Operational concerns** | The `/v1` inline `fetch` calls live here, spread across 49 files. |
| **Disposition** | **remain.** The SPA's structure is not a finding anywhere in the audit; what is missing is a generated client beneath it and an executed test suite beside it. Both are additions. |

### 5.5 `apps/web/legacy-frontend/tests/` (8 files)

| Field | Value |
|---|---|
| **Purpose** | The frontend test suite, including `queryClient.principal-isolation.test.ts` — by its name, a guard against one principal's cached data reaching another. |
| **Owns** | The frontend half of the ADR-0011 rendering invariant and the cache-isolation invariant. |
| **Does not own** | Anything the backend already asserts. |
| **Public API** | `npm test` → `node --test tests/*.test.ts`. |
| **Allowed / Forbidden deps** | n/a. |
| **Persistence** | None. |
| **Domain concepts** | Principal isolation; accountable numbers. |
| **Tests** | It *is* the tests — and **no workflow invokes it.** The `web` job in `verify.yml` runs `npm ci`, `npm run build`, `npm audit` and nothing else. |
| **Operational concerns** | The team believes a security-relevant invariant is guarded. It is not. This is the register's only P0. |
| **Disposition** | **remain, attach.** One line in the `web` job at M0, then confirm the isolation test asserts what its name claims. Written code that no lane runs is not attached code (AP-08). Cited: R-09. |

---

## 6. Disposition ledger

| # | Module | Disposition | Because |
|---|---|---|---|
| 1 | `smartmatch_domain` | remain | Strictest contract in the repo; no finding against it (contracts 1, ADR-0002) |
| 2 | `smartmatch_authz` | remain | Complete authorization coverage; no unauthorized route found (`capability-inventory.md` §5) |
| 3 | `smartmatch_providers` | remain | The seam every live capability arrives through; R-01 says do not pre-build |
| 4 | `providers/jwks.py` + `identity.py` | become an adapter | A1b is a swap at `dependencies.get_token_verifier`, not a rewrite (R-01, wip-analysis §1.4) |
| 5 | fixture adapters | remain | Permanent classroom implementation and the ADR-0021 contract-test substrate |
| 6 | `smartmatch_persistence` | remain | PostgreSQL-only is a recorded decision with stated triggers (ADR-0005) |
| 7 | `persistence/schema.py` | remain (split optional after M6) | Ownership before structure (R-20, AP-03, ADR-0019) |
| 8 | `persistence/spend_sweeper.py` | remain, attach | Right module, no production caller (R-08, AP-08) |
| 9 | `api/main.py` | remain, deepen | Capability-by-absence is correct; gains M4 logging + M5 doc corrections (R-03, R-15) |
| 10 | `api/dependencies.py` | remain, deepen | The A1b convergence seam; no third auth path (wip-analysis §1.4) |
| 11 | `api/errors.py` | remain, deepen | Deep module; gains log-once-per-`ApiError` (R-03, AP-09) |
| 12 | `api/units.py` | remain | Makes the 404-vs-403 decision once; `MAX_SUBTREE_UNITS` is AP-12's model |
| 13 | `api/utils.py` | **move** → `clock.py` | A 25-consumer module named `utils` is a dumping ground waiting to happen (R-19) |
| 14 | `api/config.py` | remain | Asks the domain policy rather than restating it |
| 15 | `api/commands.py` | remain | The single submission seam AP-04 depends on |
| 16 | `api/job_authz.py` | remain | The precedent AP-02 generalises |
| 17 | `api/match_run_evidence.py` | remain | HTTP-shaped assembly, correctly outside the pure domain |
| 18 | `api/pipeline_provisioning.py` | remain | Same; split only along a named seam if it passes the 800-line ceiling |
| 19 | `api/zip_proximity.py` | remain | Same |
| 20 | `api/routers/` (25 modules) | **split** | Two authz helpers → `smartmatch_api/unit_authz.py` (R-06, AP-02, `job_authz.py` precedent) |
| 21 | `worker/main.py` | remain, deepen | Root composition is argued and correct; gains the sweeper call and ADR-0021's test |
| 22 | `worker/handlers.py` | remain, deepen | Fail-closed registry is right; gains the AP-05 map test (R-04, ADR-0023) |
| 23 | `worker/dispatcher.py` | remain | Handoff §3 "do not touch" |
| 24 | `worker/execution.py` | remain | Same |
| 25 | `worker/identity.py` + `signature_backend.py` | remain | Misconfiguration produces total refusal; S-001 resolved |
| 26 | `worker/local_tasks.py` + `local_scheduler.py` | remain | ADR-0022 makes them the current topology's queue, not scaffolding |
| 27 | `worker/outreach.py` | remain | One function answers "when does this system email a person" |
| 28 | `worker/paid_extraction.py` | remain | Absence-withholds-the-handler is correct for a spending path (AP-11) |
| 29 | `worker/event_ingest.py` + `column_contract.py` | remain | Canonical result of the purity contract |
| 30 | `worker/config.py` | remain | No default that makes the worker easier to reach |
| 31 | `tools/` | remain, deepen | Six new gates, none relaxed (non-negotiable 13) |
| 32 | `db/migrations` | remain | ADR-0004 + ADR-0009 untouched; indexes change *where declared*, not how applied |
| 33 | `contracts/openapi` | remain, deepen | Contract-first is right; the consumer half is missing (R-02, ADR-0020) |
| 34 | `apps/web` `lib/api.ts` | **become an adapter**, then shrink | Forward over the generated client, one page at a time (R-02, AP-07) |
| 35 | 3 dead components | **disappear** | Unreferenced; one invites a capability ADR-0003 excludes (R-06b) |
| 36 | 7 legacy pages | remain (notice corrected) | Port/delete is the owner's call (OQ-S2-002); a false notice is not (R-17, D3) |
| 37 | `apps/web` `src/lib/*`, `app/`, `components/` | remain | No structural finding; needs a client beneath and tests beside |
| 38 | `apps/web/tests/` | remain, attach | One line in the `web` job (R-09) — the register's only P0 |

### Counts

| Disposition | Count | Entries |
|---|---:|---|
| **remain** | 33 | 1, 2, 3, 5, 6, 7, 8, 9, 10, 11, 12, 14, 15, 16, 17, 18, 19, 21, 22, 23, 24, 25, 26, 27, 28, 29, 30, 31, 32, 33, 36, 37, 38 |
| — of which also **deepen** (7) or **attach** (2) | 9 | deepen: 9, 10, 11, 21, 22, 31, 33 · attach: 8, 38 |
| **move** | 1 | 13 |
| **split** | 1 | 20 |
| **become an adapter** | 2 | 4, 34 |
| **disappear** | 1 | 35 |
| **merge** | 0 | — |
| **Total modules** | **38** | |

**Read the shape of that table before reading anything else in it.** Thirty-three
of thirty-eight modules stay exactly where they are, and five change: one rename,
one two-symbol extraction, two adapter conversions and three file deletions.
That is the correct output for a system with 21 implemented capabilities, 3,807
test functions, four working import contracts and a live pilot. A boundary
specification that proposed more movement than this would be proposing a rewrite
under another name, which handoff §7 forbids.
