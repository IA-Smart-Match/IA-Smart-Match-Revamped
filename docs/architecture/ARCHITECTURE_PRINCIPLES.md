# Architecture Principles

**Stage 2.** Thirteen principles, AP-01…AP-13. Commit base `c72dced`, 8 September 2026.

---

## How to read these — and how they differ from generic principles

These are not "prefer composition over inheritance". **Every principle below was
derived backwards from a finding in this repository**: an audit observation with
a `file:line`, carrying a risk ID from `risk-register.md`. If the finding did not
exist, the principle would not be here. Three consequences:

1. **Each AP names the evidence that produced it.** *Problem observed* cites at
   least one verified `file:line` plus a risk ID or audit section. A principle
   with no observation is not a principle here; it is advice, and this repository
   already has enough prose.
2. **Each AP names a mechanism.** *Enforcement* names an import-linter contract
   from `DEPENDENCY_RULES.md`, a `tools/scan_forbidden.py` rule code, a test
   file, or — where nothing mechanical exists yet — an explicit review rule,
   stated as such. Where the mechanism arrives with a migration increment, the
   AP says what enforces it **today** and what enforces it **after** the
   increment. This is the honest form: several of these are review rules for now.
3. **Each AP is already scheduled.** The increment column is writer D's M-n
   sequence; nothing here is aspirational without a landing slot.

The repository's existing strength is that its inner boundaries are *contracts*,
not conventions (`dependency-analysis.md` §1; ADR-0002's `import os` verification
at `ADR-0002-package-boundaries.md:56`). These principles extend that stance to
the 40% of production Python and the documentation surface that currently rest on
convention alone.

**Never weaken an existing gate to satisfy a principle here.** If an AP appears
to conflict with a landed gate, the AP is wrong until an ADR argues otherwise.

### Index

| AP | Principle (short) | Risk IDs | Increment | Enforcing mechanism (after) |
|---|---|---|---|---|
| AP-01 | Service packages are contracted | R-05, R-06 | M2 | import-linter contracts 5–7 + manifest-declaration test |
| AP-02 | Shared authorization has one owner | R-06 | M2 | import-linter contract 8 (`Routers are independent of one another`) |
| AP-03 | Table ownership is declared as data | R-20 | M6 | `tests/unit/test_table_ownership.py` (new) |
| AP-04 | No provider IO in a request handler | R-01 | landed; M7 records adapter contracts | `scan_forbidden.py` rule `provider-call-in-request-path` (`tools/scan_forbidden.py:135`) |
| AP-05 | Every command type has an executor or a refusal | R-04 | M1 | `tests/unit/test_command_registry_map.py` (new); ADR-0023 |
| AP-06 | A gate's prose claim is assertable | R-15 | M5 | `tests/unit/test_gate_claims.py` (new) against `factor_registry.REGISTRY_STATUS` |
| AP-07 | The contract is consumed, never transcribed | R-02 | M3 | generated-client drift check in `verify.yml`; ADR-0020 |
| AP-08 | Written code is attached or deleted | R-08, R-09, R-06b | M0, M1, M8 | `npm test` in the `web` job; `DispatchPassResponse` assertion; reference scan |
| AP-09 | Every refusal leaves a trace | R-03 | M4 | request-logging middleware + `tests/contract/test_request_logging.py` (new) |
| AP-10 | Parity covers what performance depends on | R-12 | M6 | `tests/integration/test_schema_matches_migration.py` extended both ways |
| AP-11 | Capability by absence | — (invariant 12) | landed; asserted M5 | `main.py` `CAPABILITY_SCOPED_ROUTERS:275`; contract test on the mounted set |
| AP-12 | Unbounded reads are bounded and rate-limited | R-07 | M6 | `enforce_rate_limit` + a `MAX_*` constant per unbounded read; contract test |
| AP-13 | A plan carries a status | R-16 | M5 | `tests/unit/test_plan_status_headers.py` (new) |

---

## AP-01 — Service packages are contracted

**Problem observed.** `pyproject.toml` `[tool.importlinter].root_packages` lists
exactly four `python/` packages; `smartmatch_api` (14k L) and `smartmatch_worker`
(7k L) — 40% of production Python — appear in no contract
(`dependency-analysis.md` §3; **R-06**). Their manifests are also wrong about
what they import: `services/api/pyproject.toml` declares `smartmatch-domain`,
`smartmatch-authz`, `smartmatch-providers` and **not** `smartmatch-persistence`,
while `services/api/smartmatch_api/main.py:47` imports
`smartmatch_persistence.engine` and 32 further API files import the package
(**R-05**; `CURRENT_ARCHITECTURE_AUDIT.md` §5).

**Rule.** A production Python package is governed or it is not production. Both
services sit in `root_packages`, and each service manifest declares every
`smartmatch_*` package its own source imports.

**Why.** The inner four layers are strong *because* they are contracted, not
because their authors were more careful. The service layer has the same authors
and no contract, and its convention is already broken twice (AP-02). Separately,
the manifests work only by accident of the CI install (`pip install --no-deps -e`
over all packages) and `pytest` `pythonpath`; the first real wheel, slim
container, or `uv sync --frozen` fails at import time with no earlier signal.

**Exceptions.** `tools/` is not a package (no `tools/__init__.py`) and cannot be
a `root_package`; it is governed by DR-7 as a review rule plus a manifest test,
not by a contract. Test packages are unconstrained (DR-9).

**Enforcement.** *Today:* nothing — this is the finding. *After M2:*
import-linter contracts 5, 6 and 7 in `DEPENDENCY_RULES.md` §3, plus the
manifest-declaration test of §4. Note that `Makefile:69` and `verify.yml:104`
must gain `services/api:services/worker` on `PYTHONPATH` in the same change, or
the new roots are unimportable and `lint-imports` errors rather than passes.

---

## AP-02 — Shared authorization has one owner

**Problem observed.** Two routers reach into a sibling router for
underscore-prefixed names:
`services/api/smartmatch_api/routers/cba_contact_channels.py:131` imports
`SPEAKER_CONTACT_READ_RATE_LIMIT` and `_authorize_speaker_contacts` from
`routers/cba_contacts`, and
`services/api/smartmatch_api/routers/outreach_contacts.py:109` imports
`READ_RATE_LIMIT` and `_authorize_outreach` from `routers/outreach`
(`dependency-analysis.md` §3b; **R-06**). The correct pattern already exists in
the same package: `services/api/smartmatch_api/job_authz.py:1-23` records that
`routers/jobs.py::_authorize_job_read` and `routers/redrive.py::_authorize_redrive`
applied *different subsets of the same policy to the same resource*, and exists
to make that unrepresentable.

**Rule.** A unit- or subject-scoped authorization rule lives in one owned module
outside `routers/`, on the `job_authz.py` model. No router imports another
router.

**Why.** The *behaviour* is right — one question about a unit's outreach with one
answer — and the *location* is wrong. Importing `_authorize_outreach` across
modules makes the router layer's public surface undefinable and means a rename in
`outreach.py` breaks `outreach_contacts.py` with no contract to catch it. Left
alone this grows: the third router with the same question copies the rule instead,
and R-06's failure mode becomes `job_authz.py`'s — two copies of a policy, one of
them stale.

**Exceptions.** The two imports named above are the **transitional exception**:
they are documented and argued in `main.py`'s router table, and they stand until
M2 promotes the helpers. They are carried in the contract as explicit
`ignore_imports` entries (DR-3, `DEPENDENCY_RULES.md` §3) so the contract can
land *before* the promotion. No third such import is acceptable — the contract
refuses it. `main.py` importing every router is not an exception; it is the
composition root and is excluded by construction.

**Enforcement.** *Today:* review rule only, and it has failed twice. *After M2:*
import-linter contract 8, `Routers are independent of one another`; the two
`ignore_imports` lines are deleted in the same commit that promotes the helpers,
which is what makes M2 reversible in two independent steps.

---

## AP-03 — Table ownership is declared as data

**Problem observed.** All 44 tables (Stage 1 reported 43; recounted 2026-09-08)
live in one 2,691-line
`python/smartmatch_persistence/smartmatch_persistence/schema.py`; nothing states
which context or service owns which table (`data-architecture.md` §8; **R-20**).

**The sharpest evidence is the audit's own mistake.** Stage 1
(`data-architecture.md` §8, `domain-model.md` §6, `dependency-analysis.md` §4)
records `match_run` as having two writers — `routers/match_runs.py` and
`smartmatch_worker.handlers.handle_match_run_create`. Verified against the tree
on 2026-09-08, that is wrong: `routers/match_runs.py:18-30` states that nothing
there inserts a `match_run` row and nothing there could, `job_id` being a
`NOT NULL` FK to `job`; its only repository calls are reads (`:1035`, `:1175`).
`handle_match_run_create` (~`handlers.py:1109`) is the sole writer, through the
insert-only `smartmatch_persistence.match_runs`. No table has two writers today.

The error was not careless. The API genuinely writes rows *related to* a match
run — the `job`, `outbox_record` and `idempotency_record` rows `submit_command`
creates in one transaction, plus the
`match_weight_setting`/`match_weight_setting_revision` rows a run reads — so a
reader reasoning **per feature** concludes the API writes match-run data, and a
careful audit did. That is the problem this principle names: ownership is
**undeclared**, so it must be inferred, and inference over a feature's write
footprint gets the per-table writer set wrong. ADR-0013's invariant (attendance
is the only input to points) depends on `attendance_record` having one writer,
and nothing asserts that it does either — the same gap, one table over.

**Rule.** Every table names one owning bounded context and exactly one writing
service, declared as data in the repository and checked by a test. Ownership is declared
**before** any structural change to `schema.py`.

**Why.** "Who owns this data" currently has no answer, which is why the
merge-conflict complaint about `schema.py` cannot be acted on: a split along no
boundary produces four files with the same problem. Ownership is the prerequisite;
the split is the optional consequence, and `risk-register.md` R-20 says so
explicitly — *do not split for aesthetics*.

**Exceptions.** No table has two writers today, so the map declares one writer
per table and the test asserts exactly that. A future table with two legitimate
writers may declare both — provided the declaration names each writer *and* the
reason, in the diff that introduces it. The rule forbids *undeclared* second
writers, not co-writing. Reference/vocabulary tables written only by migrations declare the
migration as writer.

**Enforcement.** *Today:* none. *After M6:* `tests/unit/test_table_ownership.py`
asserting every `sa.Table` in `schema.py` appears in the ownership map and every
map entry names a real table; ADR-0019 records the decision.

---

## AP-04 — No provider IO in a request handler

**Problem observed.** The rule is landed and gated —
`tools/scan_forbidden.py:135` `provider-call-in-request-path` fails CI on a
handler that calls `resend.`, `smtplib`, `sendgrid`, `.send_email(`, `genai.`,
`openai.` or `requests.get(http` inline (v1.1 §1.6). What is *not* proven is the
other end of the seam: `providers/registry.py:196,243,258,303` are four
"not implemented in the Foundation scaffold" refusals, so every production
adapter — Cloud Tasks, Routes, Resend, JWKS-to-real-issuer — has never executed
(**R-01**; `CURRENT_ARCHITECTURE_AUDIT.md` §15).

**Rule.** A browser request handler performs no provider IO. Provider-touching
work is persisted as a command and dispatched through the outbox to a registered
executor. The contract each adapter must satisfy is written **before** the
adapter.

**Why.** This is non-negotiable #3 and the scanner already enforces the near
side. The far side is where the risk sits: switching on any one adapter makes
retry semantics, deduplication, bounce handling and claim mapping live
simultaneously. A written contract makes the adapter measurable rather than
improvised; pre-building it speculatively is ruled out.

**Exceptions.** The public unsubscribe and invitation pages —
`main.py:507 unsubscribe_page` and the invitation surfaces — are unauthenticated
render endpoints reached by mail clients and link scanners. They are exceptions
to *authentication*, not to this rule: they render from GET and mutate only from
a signed POST (`scan_forbidden.py` `mutating-get`, v1.1 §1.10), and they call no
provider inline.

**Enforcement.** *Today:* `scan_forbidden.py:135`, self-tested in
`tests/unit/test_forbidden_scanner.py`. *After M7:* ADR-0021 states the worker's
delivery contract (200 on duplicate, 503 on race) and a contract test runs it
against the fixture queue.

---

## AP-05 — Every submittable command type has an executor or an explicit refusal

**Problem observed.** `smartmatch_worker/handlers.py:1350 default_registry()`
registers a small set of types; the map from *what a router can submit* to *what
the worker can execute* exists nowhere and is asserted by nothing (**R-04**).
Worse for a reader: `outreach.send` is composed at the root in
`worker/main.py` ~L451-489 via `with_outreach_send` and is therefore **invisible**
to anyone reading `default_registry()`, and `extraction.paid_pages` is composed
only when spend ceilings are configured. The Stage 2 resolution of U1 establishes
the map today — 4 submitting routers, 3 command types over HTTP, every one with
an executor — which is a **disagreement with Stage 1's "eight submitting
routers"**: that count included docstring mentions
(`routers/review.py:40`, `routers/speaker_requests.py:25`) and idempotency-scope
reservations (`routers/cba_contacts.py:302,1097`; `routers/redrive.py:388,527,589`).

**Rule.** Every command type any router can submit is registered in the worker,
or appears on an explicit intentionally-refused list. The assertion is the map.

**Why.** The miss path is a documented terminal refusal — fail-closed, and good —
which is exactly why the gap is dangerous: a new async capability submits
successfully, is terminally refused, and CI is green. This is the hardest
question in the codebase for a future agent to answer, and the answer is
currently "read five files and the root composition".

**Exceptions.** `test.noop` (`handlers.py:287`, registered at `handlers.py:1359`)
has no HTTP submitter by design and is a registered *path check*, not an
exception to registration. Idempotency-scope names that create no job and no
outbox row (`speaker_contact.create`, `job.redrive`, `job.abandon`) are not
command types and belong on the refused list with that reason.

**Enforcement.** *Today:* nothing; the terminal refusal is a runtime behaviour,
not a gate. *After M1:* `tests/unit/test_command_registry_map.py` asserting the
submittable set equals registered ∪ refused, including root-composed handlers;
ADR-0023 records it.

---

## AP-06 — A gate's prose claim must be assertable against its constant

**Problem observed.** `main.py`'s module docstring says match-run, discovery and
send commands "each wait on its gate: G1 for the factor registry, G3 for agent
controls, G4 for consent-origin policy", while the router table 200 lines below
mounts all three and
`python/smartmatch_domain/smartmatch_domain/factor_registry.py:149` reads
`REGISTRY_STATUS: Final[str] = "approved"` (`capability-inventory.md` §4 **D1**;
**R-15**). `Calendar.tsx:80-95` says `routers/events.py` declares no handlers and
the contract exposes no event operation; the router is 571 lines and the contract
publishes two event paths (**D3**).

**Rule.** A prose claim about a gate's state must be mechanically comparable to
the constant that holds that state. If it cannot be compared, do not write it.

**Why.** In this repository docstrings are the primary architecture record — a
false one is worse here than in a normal codebase, because agents act on it. D1
and D3 share a shape: written when a gate was open, not revisited when it closed.
The constant already exists to be asserted against; only the assertion is missing.

**Exceptions.** Historical narrative that names its own tense — "until A5 these
were authorized by two functions" (`job_authz.py:4`) — is a record, not a claim
about current state, and is not in scope.

**Enforcement.** *Today:* none; three stale claims are live. *After M5:*
`tests/unit/test_gate_claims.py` asserting no docstring claims G1 is open while
`factor_registry.REGISTRY_STATUS == "approved"`, plus correction of D1–D3.

---

## AP-07 — The contract is consumed, never transcribed

**Problem observed.** The OpenAPI document — CI-gated for freshness — advertises
in its own `description` that "the TypeScript client is generated from it and
never hand-maintained" (`main.py` FastAPI `description=`). `clients/` does not
exist; `pyproject.toml` `ruff` still carries
`extend-exclude = ["clients/typescript"]`, the fossil of the claim. 42 `/v1`
endpoints are consumed by hand-written `fetch` across 49 files
(**R-02**; `capability-inventory.md` §4 D2/D5).

**Rule.** The frontend consumes a client generated from the committed contract,
and CI fails on drift between the two.

**Why.** Today a backend field rename passes every gate in `verify.yml` and
reaches users as a runtime `undefined`. The contract is gated at the producer and
unguarded at the consumer, which is the half of the loop that users experience.
`verify.yml` already names "generated TypeScript client drift check (needs
`clients/`)" on its deferred list — the decision was made and never executed.

**Exceptions.** The seven legacy portal pages calling `/api/*` paths no service
serves are outside the `/v1` contract entirely; their disposition is OQ-S2-002,
not a client-generation exception. Migration is one page at a time — migrating 49
files at once is ruled out.

**Enforcement.** *Today:* producer-side freshness gate only. *After M3:* the
drift check promoted off `verify.yml`'s deferred list; ADR-0020.

---

## AP-08 — Written code is attached or deleted

**Problem observed.** Three independent instances. (a)
`python/smartmatch_persistence/smartmatch_persistence/spend_sweeper.py:107
SpendReservationSweeper` is implemented and tested, and its only non-test
references are its own module and its two tests — while the analogous
`sweep_expired_leases` *is* called from the scheduled dispatch pass (**R-08**).
(b) Eight frontend test files exist, including
`queryClient.principal-isolation.test.ts`, and no workflow runs `npm test`
(**R-09**, P0). (c) `OutreachWorkflowModal`, `AgenticOutreachPanel` and
`FeedbackForm` are referenced by nothing, and `AgenticOutreachPanel` names a
capability ADR-0003 excludes from Foundation (**R-06b**).

**Rule.** No production-shaped module without a production caller; no test file
that no lane runs. Code is attached in the increment that writes it, or deleted.

**Why.** Unattached code is worse than absent code because the team believes it
runs. A named principal-isolation guard that never executes is a security
invariant everyone thinks is held. An unwired sweeper leaves reservations
`reserved` forever instead of `expired_spent` — under-charging and stuck rows.
An unreferenced "agentic" panel invites a future agent to wire up a prohibited
capability.

**Exceptions.** None identified. Deliberate scaffolding is acceptable only when
the refusal is explicit and reachable — the four `providers/registry.py` "not
implemented in the Foundation scaffold" refusals are attached: they are called
and they refuse.

**Enforcement.** *Today:* none mechanical. *After M0:* `npm test` in the `web`
job and `services/*` in `--cov`. *After M1:* the sweeper called from the dispatch
pass and reported in `DispatchPassResponse` — the report is the assertion. *After
M8:* the three components deleted; git retains them.

---

## AP-09 — Every refusal leaves a trace

**Problem observed.** Across ~70k lines of `python/` + `services/` there are 20
logging references in 10 files, no structured logging, no tracing, no metrics
export; 22 of 25 router modules log nothing (**R-03**; Stage 1 reported 26 routers, recounted 2026-09-08). `GET /api/health`
(`main.py:471`) is liveness only, and the readiness endpoint its docstring
promises at `main.py:477` was not found (`capability-inventory.md` §4 D4).

**Rule.** One structured request log line with a correlation id at the API
boundary, and every `ApiError` path logs exactly once with its code.

**Why.** An authz refusal, a rate-limit rejection or a 500 in a synchronous
router currently leaves no trace at all. Diagnosis means reading `job_event` rows
out of PostgreSQL, and only job work writes those — so precisely the paths with
no diagnostic story are the ones users hit. One middleware beside
`MaxBodySizeMiddleware` (`main.py:108`) is the whole change.

**Exceptions.** No secret, token, or principal identifier beyond an opaque id in
a log line — the health endpoint's rule (`main.py:475`, expose no dependency or
topology detail) applies to logs as it does to responses. No tracing vendor is
adopted at this stage.

**Enforcement.** *Today:* none. *After M4:* the middleware plus
`tests/contract/test_request_logging.py` asserting a correlation id on a refusal
and exactly one log record per `ApiError`.

---

## AP-10 — Parity covers what performance depends on

**Problem observed.** `schema.py` declares zero indexes; all 33 live in
migrations; `tests/integration/test_schema_matches_migration.py:25` states
outright that *"Index sets are not compared because `schema.py` declares no
indexes on purpose"* (**R-12**). Dropping `ix_outbox_claimable` therefore passes
every CI gate and degrades the dispatcher's `SKIP LOCKED` claim to a sequential
scan.

**Rule.** Indexes are declared in `schema.py` beside their tables, and the parity
test compares index names in **both** directions — schema→migrations and
migrations→schema.

**Why.** The parity guard exists to make schema drift impossible, and it has a
hole exactly where the failure is silent and progressive: a slow production with
green CI. One-directional comparison is not parity.

**Exceptions.** An index created concurrently or as a temporary operational
measure must still be declared; if it is genuinely transient it is recorded with
its removal migration rather than exempted.

**Enforcement.** *Today:* parity on tables and columns only, with the gap
documented in the test's own docstring — which is the good version of the
problem. *After M6:* the same test, both directions.

---

## AP-11 — Capability by absence

**Problem observed.** The mechanism is landed and is the repository's sharpest
idea: `services/api/smartmatch_api/main.py:275 CAPABILITY_SCOPED_ROUTERS` pairs
each router with a `Capability`, and `main.py:466-468` includes the router only
when `get_settings().capability_enabled(...)`. A disabled capability therefore
has **no route to reach**, rather than a route that checks a flag. The risk is
that nothing asserts the pairing stays exhaustive as routers are added — the same
shape as R-04 for handlers.

**Rule.** A gated-off capability owns no router and no registered handler. Never
`if enabled:` inside a handler.

**Why.** This is non-negotiable #12. A flag checked inside a handler leaves the
route mounted, in the OpenAPI document, and in the client's reachable surface; a
flag checked at mount time removes all three. Absence is the only form of "off"
that cannot be partially true.

**Exceptions.** `test.noop` (`handlers.py:287,1359`) is registered
unconditionally and belongs to no capability — it is the path check, and its
whole purpose is to be reachable when everything else is off.
`extraction.paid_pages`, composed at the root only when spend ceilings are
configured (`worker/main.py` ~L491), is the handler-side expression of this same
principle, not an exception to it.

**Enforcement.** *Today:* the construction itself — there is no flag to check
inside a handler because there is no handler mounted. *After M5:* a contract test
asserting every router module in `routers/` appears either in
`CAPABILITY_SCOPED_ROUTERS` or in the unconditional list, so a new router cannot
be mounted ungated by omission.

---

## AP-12 — Unbounded reads are bounded and rate-limited

**Problem observed.** `GET /v1/units/{u}/metrics/{name}/drill-down` returns "the
rows behind the number": authenticated, database-heavy, unbounded, and
`services/api/smartmatch_api/routers/metrics.py` (702 lines) contains no
`enforce_rate_limit` call at all — one of seven routers of 26 without one
(**R-07**). The pattern to copy already exists:
`services/api/smartmatch_api/units.py:31 MAX_SUBTREE_UNITS: Final[int] = 50`,
applied as the default `limit` at `units.py:83`.

**Rule.** Every authenticated read whose cost scales with data carries both a
rate limit and a declared maximum row count, the maximum expressed as a named
constant.

**Why.** The alternative is an authenticated denial-of-service against the shared
database, from a legitimate token. The constant matters as much as the limit: a
named `MAX_*` is a decision a reviewer can see and a test can assert, where an
inline `LIMIT 500` is a number nobody owns.

**Exceptions.** Reads bounded by the resource itself — a single row by primary
key — need no `MAX_*`. Export endpoints that are legitimately large must say so
and be rate-limited harder, not exempted.

**Enforcement.** *Today:* `enforce_rate_limit` applied by convention in 20 of 26
routers; `metrics` is the counter-example. *After M6:* `enforce_rate_limit` on
`metrics` drill-down plus a bounding constant, and a contract test asserting every
router exposing a collection read declares one.

---

## AP-13 — A plan carries a status

**Problem observed.** `docs/plans/` holds 50 entries with no status field.
Several describe conditions already resolved — G1 open, and
`frontend-broken-buttons.md` B06 which `main.py` cites as fixed. The visible git
history begins 2026-09-05 while plans date from 2026-08-28, so history cannot
resolve which landed (**R-16**; U8 / OQ-S2-005).

**Rule.** Every document under `docs/plans/` declares exactly one of `ACTIVE`,
`LANDED`, `SUPERSEDED BY <path>`, `ABANDONED` in a one-line header.
Non-`ACTIVE` documents move to `docs/plans/archive/`.

**Why.** Every future agent currently pays the cost of reading 50 documents to
find what is current, and some of what they read is false. The ADR corpus already
solves this — `tests/unit/test_adr_index.py` asserts each ADR's `**Status:**`
against the index row — and the plans corpus, which is larger and changes faster,
has nothing.

**Exceptions.** `docs/plans/open-questions/` documents carry the question's
disposition instead; the deferred-question shape
(`open-questions/r4-outreach-deferred.md`) is the record, and a question is not a
plan.

**Enforcement.** *Today:* none; `test_adr_index.py` covers decisions only.
*After M5:* `tests/unit/test_plan_status_headers.py` on the same model as
`test_adr_index.py`, with the four-value vocabulary above.
