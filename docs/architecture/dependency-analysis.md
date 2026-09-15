# Dependency Architecture

**Stage 1 §2.** Which module boundaries are real and which are folders. Commit `c72dced`.

---

## 1. What is enforced today

`pyproject.toml` `[tool.importlinter]` declares four contracts, run in CI by
`lint-imports` (`verify.yml`, step *"Architecture import boundaries"*):

| # | Contract | Type | Effect |
|---|---|---|---|
| 1 | Domain is pure — no frameworks, storage, providers, IO, or env | `forbidden` | `smartmatch_domain` may not import `fastapi`, `starlette`, `sqlalchemy`, `alembic`, `pydantic_settings`, `httpx`, `requests`, `google`, `boto3`, `os`, `pathlib`, `socket`, `subprocess`, `smartmatch_providers` |
| 2 | Authz is pure — policy only | `forbidden` | same shape, narrower list |
| 3 | Layering | `layers` | `smartmatch_persistence` → `smartmatch_providers` → `smartmatch_authz` → `smartmatch_domain`, one direction only |
| 4 | Persistence is storage only | `forbidden` | no `httpx`/`requests`/`subprocess`/`smartmatch_providers`/`fastapi` |

**OBSERVED.** `include_external_packages = true` is set, which is what makes
"domain must not import FastAPI" expressible at all. `os` and `pathlib` are in
the forbidden list for the domain package — this is a genuinely strict purity
contract, not a nominal one.

**This is the strongest single architectural asset in the repository.** The
inner four layers are not folders; they are enforced boundaries with a CI gate.

---

## 2. The measured graph

### Cross-package edges (OBSERVED, by `grep -rlE '^(from|import) <pkg>'`)

| Consumer ↓ / Provider → | domain | authz | providers | persistence |
|---|---|---|---|---|
| `smartmatch_domain` | (internal 18+6) | — | **forbidden** | **forbidden** |
| `smartmatch_authz` | — | (internal 1) | **forbidden** | **forbidden** |
| `smartmatch_providers` | 4 | — | (internal 7) | **forbidden** |
| `smartmatch_persistence` | 14 | 1 | **forbidden** | (internal 26) |
| `services/api` | 29 | 21 | 5 | **31** |
| `services/worker` | 8 | — | 6 | 9 |
| `tools/` | 5 | — | — | 7 |

All inner-layer edges point downward. **No violation of contracts 1–4 was found.**

### Import cycles

**OBSERVED.** A full AST-level cycle search over all six Python packages found
**no genuine cycles.** Four apparent cycles were reported and all four are the
same benign shape: `smartmatch_persistence/__init__.py` re-exports
`jobs`/`outbox`/`redrive`, and those modules do
`from smartmatch_persistence import schema` — a submodule import through the
partially-initialised package.

**INFERRED — localized debt, not a defect.** Python resolves this correctly
(`from package import submodule` falls back to importing the submodule), and it
has evidently never broken. It is nevertheless import-order fragility: adding a
new eager import to `__init__.py` above the existing ones can turn it into a
real `ImportError`. Disposition: **acceptable**; note it, do not refactor.

---

## 3. The boundary that is NOT enforced — the finding

**OBSERVED.** `[tool.importlinter].root_packages` lists exactly four packages:

```toml
root_packages = [
    "smartmatch_domain", "smartmatch_authz",
    "smartmatch_providers", "smartmatch_persistence",
]
```

`smartmatch_api` and `smartmatch_worker` are **absent**. Together they are
28,080 lines — 40% of production Python — and **no import contract governs them
at all.**

Three consequences, each independently observed:

### 3a. Undeclared dependency on `smartmatch_persistence`

| Package | `pyproject.toml` declares persistence? | Files importing it |
|---|---|---|
| `services/api` | **No** | **33** |
| `services/worker` | **No** | **10** |

`services/api/pyproject.toml` lists `smartmatch-domain`, `smartmatch-authz`,
`smartmatch-providers` — not `smartmatch-persistence`. Yet
`services/api/smartmatch_api/main.py:47` opens with
`from smartmatch_persistence.engine import create_session_factory`.

It works because CI installs all four `python/` packages with
`pip install --no-deps -e …` regardless of declarations, and because
`[tool.pytest.ini_options].pythonpath` adds every source root. **The manifests
do not describe the real dependency graph.** A future packaging change — a real
wheel build, a slimmer container, a `uv sync --frozen` of one service — breaks
at import time with no earlier warning.

**Severity: P1.** Cheap to fix, and it is the prerequisite for enforcing any
service-layer contract. → `risk-register.md` R-05.

### 3b. Lateral coupling between routers

**OBSERVED.** Two routers import private helpers from sibling routers:

| Importer | Imports | From |
|---|---|---|
| `routers/cba_contact_channels.py:131` | `_authorize_speaker_contacts` (+ others) | `routers/cba_contacts.py` |
| `routers/outreach_contacts.py:109` | `READ_RATE_LIMIT`, `_authorize_outreach` | `routers/outreach.py` |

Both are **deliberate and documented** — `main.py`'s router table argues each
case, and the reason given is sound: *"one question about a unit's outreach with
one answer"*, i.e. avoiding a duplicated authorization rule.

**Disposition: acceptable behaviour, wrong location.** The behaviour (one
authorization rule per subject, not one per router) is right. The mechanism
(reaching across a sibling module for an underscore-prefixed name) makes the
router layer's public surface undefinable and means a rename in `outreach.py`
silently breaks `outreach_contacts.py` with no contract to catch it.

**RECOMMENDATION.** Promote these shared authorization functions out of the
router modules into an explicit unit-authorization module, and add a contract
forbidding router→router imports. → Stage 2 **AP-02**, migration increment M2.

### 3c. Nothing stops a router importing another service

There is no contract preventing `smartmatch_api` from importing
`smartmatch_worker` or vice versa. Today neither does
(`grep`: importers of `smartmatch_worker` = 7, all internal). The boundary
holds by convention only.

---

## 4. Fan-in analysis — which modules are load-bearing

### API shared modules (fan-in across `services/` + `tools/`)

| Module | Fan-in | Lines | Assessment |
|---|---:|---:|---|
| `errors.py` | 26 | 271 | **Healthy.** One error envelope, one set of exception handlers. Deep module: simple interface (`ApiError`, `error_response`) over the whole HTTP error contract. |
| `dependencies.py` | 26 | 296 | **Healthy but load-bearing.** Owns principal resolution, rate limiting, quota charging. Every route depends on it; a change here changes every route. |
| `utils.py` | **25** | **18** | **Smell — see below.** |
| `units.py` | 18 | 150 | **Healthy.** Owns the 404-vs-403 decision once (`load_unit_or_404`), which is exactly the kind of decision that must not be re-made per router. |
| `config.py` | 11 | 176 | Healthy. |
| `commands.py` | 7 | 249 | Healthy — the command-submission seam. |
| `job_authz.py` | 4 | 299 | **Exemplary.** Its docstring records that `jobs.py` and `redrive.py` previously each carried their own `_authorize_job_read` applying *different subsets* of the same policy; this module is the consolidation. This is the pattern §3b should follow. |

#### `utils.py` — a 25-consumer module containing one 7-line function

**OBSERVED.** `services/api/smartmatch_api/utils.py` is 18 lines and exports
exactly one symbol: `utc_now()`. It has the second-highest fan-in in the API.

**Disposition: acceptable, with a caveat.** The *content* is right and the
docstring gives a real defect as its justification (finding F-003: the legacy
ICS generator claiming UTC for local times). One clock, one patch point.

The **name** is the debt. A module called `utils` with 25 consumers is the
textbook seed of a dumping ground: the next helper that has no obvious home
lands here because the import is already everywhere, and in a year it is 400
lines of unrelated behaviour. The repository has been disciplined so far — it
has stayed at 18 lines — but nothing enforces that.

**RECOMMENDATION.** Rename to `clock.py` (or `time.py`) so the module's name
states its single responsibility and a second, unrelated helper has no
plausible reason to be added to it. Low cost, purely preventive.
→ Stage 2 migration increment M1.

### Domain modules by fan-in

| Module | Fan-in | Role |
|---|---:|---|
| `jobs` | 17 | Job lifecycle vocabulary (`JobState` ×12 states). Universal. |
| `factor_registry` | 17 | The approved scoring registry + `assert_registry_approved()`. |
| `events` | 15 | Event entity + temporal model (ADR-0010, ADR-0012). |
| `consent` | 12 | Consent state machine (ADR-0014). |
| `naics_sectors` | 11 | Industry vocabulary. |
| `cba_role_categories` | 10 | CBA role vocabulary. |

**INFERRED.** High fan-in here is *correct*: these are shared vocabularies and
lifecycle rules, exactly what a domain layer should own and what many callers
should agree on. High fan-in on a vocabulary module is cohesion, not coupling.

### Persistence modules by fan-in

| Module | Fan-in | Note |
|---|---:|---|
| `rate_limit` | **21** | Highest in the layer |
| `jobs` | 14 | |
| `pipeline` / `events` / `engine` / `attendance` | 10 each | |
| `schema` | (imported by all 26 repositories) | See §5 |

`rate_limit` at 21 reflects the per-route rate limiting in
`dependencies.enforce_rate_limit` plus 20 routers. Fixed-window in PostgreSQL
by decision (ADR-0006). Healthy.

---

## 5. `schema.py` — 2,691 lines, 44 tables, one module

**OBSERVED.** Every table in the system is defined in a single file. Every one
of the 26 repository modules imports it.

**Assessment: acceptable, verging on compounding debt.**

*Why it is defensible:* the tables are hand-written SQLAlchemy Core `Table`
objects, not ORM models, by explicit decision (ADR-0004,
*"hand-written schema and ltree"*). A single metadata object is the natural
shape for that, cross-table constraints are visible in one place, and the file
is dense with `CheckConstraint`s that are individually tested
(`tests/integration/test_check_constraints.py`, 43 tests;
`test_event_schema_constraints.py`, 54 tests).

*Why it is nevertheless debt:* it is the one file that every persistence
change touches, which makes it a permanent merge-conflict surface in an
agent-parallel workflow, and it defeats the "who owns this data" question —
`schema.py` owns all 44 tables, so nothing else can be said to.

**RECOMMENDATION.** Do **not** split it for aesthetics. Split it only if and
when data ownership is assigned per bounded context (see `domain-model.md` §6),
so the split lines up with a boundary that already means something. Recorded as
a Stage 2 ADR candidate, not a migration increment.

---

## 6. Domain leakage and provider leakage

**OBSERVED — clean.** The audit specifically looked for:

| Leak sought | Found? | Evidence |
|---|---|---|
| Provider SDK semantics in domain code | **No** | Contract 1 forbids `smartmatch_providers` from `smartmatch_domain`; `resend`/`google` appear only under `smartmatch_providers/` |
| Persistence concerns in domain logic | **No** | Contract 1 forbids `sqlalchemy` in domain; domain modules are pure dataclasses + functions |
| Storage layer making network calls | **No** | Contract 4 forbids `httpx`/`requests` in persistence |
| Inline provider IO from an HTTP handler | **No** | `scan_forbidden.py:136` regex-matches route decorators followed within 600 chars by `resend.` / `smtplib` / `sendgrid` / `.send_email(` / `genai.` / `openai.` / `requests.get(http`; CI-gated |
| Caller-selected identity | **No** | `scan_forbidden.py:60`, the caller-selected-identity rule — forbids the archived login-as-anyone route, a caller-chosen role parameter, and reading a role off the request body |
| Tenant/user id taken from a request body | **No** | `scan_forbidden.py:165`, rule `client-supplied-identity` — forbids assigning a tenant, user, student, or professional id from a request payload or body |
| Module-level mutable global state | **No** | `scan_forbidden.py:99` forbids `_?[A-Z_]*(QUEUE\|STATE\|CACHE\|REGISTRY\|STORE\|BUS\|RESULTS?) = {} \| [] \| deque()` |

**This is unusually good.** The classic leakages this audit exists to find are
absent, and their absence is *enforced by a self-tested scanner*
(`tests/unit/test_forbidden_scanner.py`) rather than by review.

---

## 7. Frontend/backend contract coupling

**OBSERVED — this is where the dependency architecture breaks down.**

| Property | Backend | Frontend |
|---|---|---|
| Contract artifact | `contracts/openapi/smartmatch.json` — 57 paths, 120 schemas, CI-gated for staleness | none |
| Client | *documented* as generated (`main.py`: "the TypeScript client is generated from it and never hand-maintained") | **does not exist** — `clients/` is absent from the repository |
| Actual access | — | `lib/api.ts` (4,238 lines, hand-written, legacy) **plus** inline `fetch("/v1/…")` in 49 files |
| Type provenance | Pydantic models → OpenAPI | hand-written TS interfaces, per page |

**INFERRED.** Every response shape the frontend consumes is transcribed by hand
in the consuming page. There are 42 distinct `/v1` endpoints reached this way.
The OpenAPI freshness gate protects the *contract*; nothing protects the
*consumer* from drifting off it. A backend field rename passes every gate in
`verify.yml` and reaches production as a runtime `undefined` in the browser.

This is the highest-value structural gap in the repository.
→ `risk-register.md` R-02, Stage 2 migration increment **M3**.

---

## 8. Summary — real boundaries vs. folders

| Boundary | Real? | Enforced by |
|---|---|---|
| `smartmatch_domain` purity | **Real** | import-linter contract 1 |
| `smartmatch_authz` purity | **Real** | import-linter contract 2 |
| Layer ordering persistence→providers→authz→domain | **Real** | import-linter contract 3 |
| `smartmatch_persistence` = storage only | **Real** | import-linter contract 4 |
| "No provider IO in a request handler" | **Real** | `scan_forbidden.py` rule + CI |
| API ↔ worker separation | **Convention** | nothing |
| Router ↔ router separation | **Folder** | nothing; two documented violations |
| `services/*` → `python/*` declared deps | **Folder** | manifests are wrong (§3a) |
| API contract ↔ frontend consumer | **Folder** | nothing (§7) |
