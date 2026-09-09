# Migration Roadmap — M0 … M8

**Stage 2 plan.** Commit `c72dced`, 8 September 2026. Increment identifiers
`M0`–`M8` are fixed; other Stage 2 documents cite them by number.

This is a roadmap for a codebase that is **structurally sound and unevenly
enforced**. Nothing here is a rewrite, a service split, an event bus, or a
speculative GCP build. Every increment below is a change to what CI asserts, to
what is wired, or to what is written down — not to how the system works. Two
increments (M1's sweeper wiring, M6's rate limit) change runtime behaviour; both
are additions to mechanisms that already run.

Three rules govern every increment, and each is checkable by a reviewer before
merge:

1. **Independently shippable.** The increment can merge alone, with `make check`
   green, and leave the repository in a coherent state.
2. **Reversible by a named act** — revert one commit, delete one TOML block,
   unset one environment variable. "Reversible in principle" is not a rollback
   strategy; every increment below names the act.
3. **Never weakens a gate.** No increment adds `|| true`, `continue-on-error`,
   an `xfail`, a scanner allowlist entry, or a coverage threshold that could
   later be lowered to pass. Non-negotiable 13.

---

## Ordering argument

The order is not a priority list sorted by risk score. Each increment is placed
where it makes the next one **cheaper or safer to perform**, and the argument is
explicit for the first four because those are the ones a reader is most likely
to want to reorder.

### Why M0 is first

M0 adds `npm test` to the `web` job and `services/*` to `--cov`. It writes no
production code. It is first because **every later increment is verified by CI,
and CI is currently running less than the repository believes it runs**.

- Eight frontend test files exist and no workflow invokes them
  (`apps/web/legacy-frontend/package.json` `"test": "node --test tests/*.test.ts"`;
  `.github/workflows/verify.yml` `web` job runs only *Install locked
  dependencies*, *Typecheck and build*, *Audit dependency vulnerabilities`).
  R-09, P0.
- The `python` job's *Tests* step passes `--cov` for the four `python/`
  packages only, so 28,080 lines of `services/` are exercised and unmeasured
  (R-10).

M3 migrates a frontend page to a generated client. Doing that **before** the
frontend test suite runs means the migration's regressions are invisible on the
one surface that has tests. M2 changes import structure across `services/`;
doing that before `services/` is in `--cov` means a coverage regression caused
by the refactor cannot be seen. M0 is not merely cheap — it is what makes M2 and
M3's evidence readable.

### Why M1 is second

M1 attaches things that were written and never connected, and asserts the one
map a future agent cannot derive by reading:

- the registry-completeness test (R-04, AP-05),
- `SpendReservationSweeper` called from the scheduled dispatch pass (R-08),
- `utils.py` → `clock.py` (R-19),
- `GLOSSARY.md` published (`domain-model.md` §4).

Each is a one-file change with no dependency on anything else in this roadmap.
Two of them are **preconditions for any asynchronous work at all**: until the
registry map is asserted, a new command type can be submitted successfully and
terminally refused with no build-time signal (R-04); until the spend sweeper is
called, every reservation the worker abandons stays `reserved` forever (R-08).
M7 records the worker's delivery contract as an ADR; that ADR is a statement
about a registry whose completeness is, at M1, asserted rather than assumed.

M1 also runs before M2 because M2 moves modules between packages. Moving
`utils.py` to `clock.py` (25 consumers) inside a commit that also promotes authz
helpers and adds two `root_packages` would make a bisect over a broken import
useless. Rename first, cheaply, alone.

### Why M2 is third

M2 declares `smartmatch-persistence` in both service manifests, adds both
services to `[tool.importlinter].root_packages`, promotes the two shared
authorization helpers out of the routers, and forbids router→router and
api↔worker imports (R-05, R-06, AP-01, AP-02).

It is third and not first because the promotion it performs is a **refactor of
authorization code**, which is the category of change one least wants to make
while `services/` coverage is unmeasured (M0) and while a rename of a
25-consumer module is still pending (M1). And it is third and not later because
everything after it adds modules to `services/`: M4 adds a middleware, M6 adds an
ownership module. Adding those before the contract exists means each new module
is written under convention and retrofitted under contract; adding them after
means the contract catches the mistake on the first `lint-imports` run.

R-05 is also a strict prerequisite of R-06 in the mechanical sense: import-linter
with `include_external_packages = true` resolves what the manifests declare, and
a `root_package` whose real dependency is undeclared produces contract results
that describe the pythonpath rather than the package.

### Why M3 is fourth

M3 generates `clients/typescript`, turns on the drift gate already listed as
deferred at the bottom of `verify.yml` (*"generated TypeScript client drift
check (needs clients/)"*), and migrates **one** page as the pattern (R-02,
AP-07).

It follows M0 because the frontend suite must be running before a frontend page
is rewritten. It follows M2 because the generator's input is the OpenAPI
document exported by `tools/export_openapi.py`, which imports
`smartmatch_api.main`; a service package whose dependencies are undeclared is a
service package whose export step works only under the CI pythonpath, and the
client generation step is the second consumer of that import path. It precedes
M4 because M4 changes response *headers and logs*, not the contract, and a
correlation-id middleware landing mid-migration would make a drift-check failure
ambiguous.

### Why M4 … M8 follow in that order

- **M4 before M5** — M5 corrects D1–D3 and adds the gate-claim test. D2's false
  claim (*"the TypeScript client is generated from it and never
  hand-maintained"*, `main.py:214`) stops being false at M3 rather than being
  edited; correcting the docstrings after the code has caught up avoids writing
  a correction that a later increment un-corrects.
- **M5 before M6** — M6 declares table ownership *as documentation that is
  tested*. M5 is where the repository establishes that prose is assertable
  (AP-06) and that a plan carries a status (AP-13). M6's ownership map is the
  largest piece of tested documentation in the plan; it lands into an
  established pattern rather than inventing one.
- **M6 before M7** — M7's retention decisions (R-13) are per-table decisions.
  Naming an owning context for `job_event`, `delivery_event`,
  `contact_channel_transition`, `pilot_login_attempt` and `match_run` is what
  makes "who decides the retention period" answerable.
- **M8 last** — it is the only increment blocked on an owner decision
  (OQ-S2-002), and deletion of dead frontend components is safest once the
  frontend suite runs (M0) and one page has already been migrated (M3), so the
  reference scan is being read against a codebase whose conventions have
  settled.

---

## Re-sequencing versus Stage 1

**Stage 1 §18 sketched:** M0 frontend tests → M1 glossary + clock rename → M2
authz promotion + router contract → M3 client → M4 registry map → M5 sweeper →
M7 indexes.

**Stage 2 re-sequences:** the **registry-map test** and the **sweeper wiring**
move up from M4/M5 into **M1**, and the glossary and clock rename ride along
with them rather than occupying an increment of their own.

Three reasons, in order of weight:

1. **Priority inversion.** R-04 and R-08 are **P1**. The glossary and the
   `utils.py` rename serve R-19, which is **P3**, and the glossary serves no
   risk register entry at all. Stage 1's sketch put a P3 increment ahead of two
   P1 items. Under Stage 1's own ordering principle — *"earlier items make later
   ones cheaper"* — a P3 preventive rename does not make a P1 wiring fix cheaper,
   and §18's own numbered list already places the sweeper (2) and the registry
   map (3) above everything except running the existing tests.
2. **Size.** Both are one-file changes. The registry-map test is a new file
   under `tests/unit/`; the sweeper wiring adds a collaborator to
   `ScheduledPass` and fields to `DispatchPassResponse`
   (`services/worker/smartmatch_worker/main.py:262`). Neither touches a package
   boundary, neither is blocked, and neither has a prerequisite in this roadmap.
   An increment that is cheap, unblocked and P1 has no argument for waiting.
3. **They are preconditions for anything asynchronous.** Every capability still
   to come — live email, discovery, paid extraction — reaches the worker as a
   submitted command. Until the registry map is asserted, adding one of those is
   an act whose failure mode is a silent terminal refusal at runtime rather than
   a red build. And until the spend sweeper runs, any capability that reserves
   spend inherits R-08's stuck rows. Fixing them after those capabilities land
   means fixing them under load.

**What did not move.** Indexes (Stage 1's M7) stay late, in M6, because R-12 is
P2 and — unlike the two items above — the remediation is genuinely large: 33
index declarations mirrored into `schema.py` and a parity comparison extended in
both directions. It also belongs beside the ownership map, since both are
statements about `schema.py` and shipping them together means the file is opened
once.

**Recorded Stage 1 disagreement.** Stage 1 said *"three handlers, eight
submitting routers"* (`wip-analysis.md` §2). Verified in tree on 2026-09-08:
**four routers submit and three command types reach the worker, each with an
executor**. The other counted uses are docstring mentions
(`routers/review.py:40`, `routers/speaker_requests.py:25` — synchronous by
design) and idempotency-scope reservations that never create a job or outbox row
(`routers/cba_contacts.py:302,1097`; `routers/redrive.py:388,527,589`). The map
is complete today. R-04 survives in a sharper form: **nothing asserts it**, and
two of the handlers are composed at the root
(`services/worker/smartmatch_worker/main.py:470,492` via `with_outreach_send` and
`with_paid_extraction`), so they are invisible to a reader of `default_registry()`
at `handlers.py` ~L1349. That invisibility is the M1 test's real target.

---

## Increment summary

| Increment | Risks closed | APs enforced | ADRs | Size (files · agent-hours) | Reversible how |
|---|---|---|---|---|---|
| **M0** Run what already exists | R-09, R-10 | AP-08 | — | 1 file (`verify.yml`) · 1–3 h | Revert one commit; the two edits are additive workflow steps |
| **M1** Attach and assert | R-04, R-08, R-19; part of R-11(b) | AP-05, AP-08 | ADR-0023 (Proposed) | 6–9 files · 6–10 h | Revert one commit; the sweeper is one constructor argument, removable alone |
| **M2** Declare then contract the service layer | R-05, R-06 | AP-01, AP-02 | ADR-0018 | 8–12 files · 8–14 h | Delete the two new `[[tool.importlinter.contracts]]` blocks and the two `root_packages` entries; the promoted module can stay |
| **M3** Close the contract loop | R-02 (+ D2, D5) | AP-07 | ADR-0020 | generated tree + 3–5 files · 10–16 h | Delete the drift-check step from `verify.yml`; revert the one migrated page |
| **M4** Make failure visible | R-03 | AP-09 | — | 3–4 files · 6–10 h | Unset `SMARTMATCH_REQUEST_LOG_ENABLED`; or revert one `add_middleware` line |
| **M5** Make prose assertable | R-15, R-16 | AP-06, AP-13 | — | 3 code files + ~40 docs · 5–9 h | Revert one commit; docs-only plus one new test file |
| **M6** Declare ownership, bring indexes under parity | R-20, R-12, R-07 | AP-03, AP-10, AP-12 | ADR-0019 | 5–7 files · 12–20 h | Revert one commit; no migration, no data change |
| **M7** Record adapter and topology contracts | R-01, R-18, R-13, R-14 | AP-04 (restated) | ADR-0021, ADR-0022 | 4–6 files · 8–12 h | Revert one commit; ADRs are `Proposed`, nothing behavioural changes |
| **M8** Owner-gated cleanups | R-17, R-06b | AP-08 | — | 4–11 files · 3–12 h | Revert one commit; `git` retains the deleted components |

Agent-hours are an estimate for a competent agent working with this repository's
conventions already in context, including writing the tests and getting `make
check` green. They are not a schedule.

---

## Coverage of the risk register

Every P0 and P1 entry — R-09, R-01, R-02, R-03, R-04, R-05, R-06, R-08 — is
closed by an increment. Nothing at P0/P1 is deferred.

| Risk | Priority | Increment | Note |
|---|---|---|---|
| R-09 | P0 | **M0** | Plus the second sentence of its remediation — confirming `queryClient.principal-isolation.test.ts` asserts what its name claims — which is task T-0.5 |
| R-02 | P1 | **M3** | One page migrated, not 49 |
| R-05 | P1 | **M2** | Commit 1 of 2 |
| R-06 | P1 | **M2** | Commit 2 of 2 |
| R-04 | P1 | **M1** | The test *is* the missing map |
| R-08 | P1 | **M1** | Sweeper into the existing scheduled pass |
| R-03 | P1 | **M4** | One middleware, no tracing vendor |
| R-01 | P1 | **M7** | Contract recorded as ADR-0021 before any adapter is built |
| R-07 | P2 | **M6** | `enforce_rate_limit` on metrics drill-down, bounded rows |
| R-10 | P2 | **M0** | Baseline recorded, no threshold in the same change |
| R-11 | P2 | **M1** (b) / **M0** (c) / **(a) resolved in tree** | (a) the `MaxBodySizeMiddleware` chunked / lying-`Content-Length` branch **is** tested — `tests/contract/test_max_body_size.py::test_a_streamed_body_is_rejected_the_moment_the_running_total_crosses_the_cap` — see below |
| R-12 | P2 | **M6** | Indexes declared in `schema.py`, parity both ways |
| R-15 | P2 | **M5** | D1, D3 corrected; D2 falsified by M3 first |
| R-16 | P2 | **M5** | Status header on every `docs/plans` document |
| R-17 | P2 | **M8** | Blocked on **OQ-S2-002** |
| R-06b | P2 | **M8** | The one part of M8 that is *not* blocked |
| R-18 | P2 | **M7** | ADR-0022 |
| R-13 | P3 | **M7** | Recorded as a decision; **OQ-S2-003** supplies the periods |
| R-14 | P3 | **M7** | **OQ-S2-004** decides supported-or-not; M7 records the answer |
| R-19 | P3 | **M1** | `utils.py` → `clock.py` |
| R-20 | P3 | **M6** | Ownership declared; the `schema.py` split remains an optional follow-up |

**R-11(a) — resolved in tree, 2026-09-08.** Stage 1 recorded as UNKNOWN whether
`tests/contract/test_max_body_size.py` covers the buffering branch for a client
that sends chunked or lies about `Content-Length`
(`services/api/smartmatch_api/main.py` ~`:107`, docstring branch 2). **It does.**
`test_a_streamed_body_is_rejected_the_moment_the_running_total_crosses_the_cap`
drives a scope with no `content-length` header through three queued chunks, the
second of which crosses the cap, and asserts exactly two `receive()` calls, that
the downstream application is never invoked, and a 413 `request_body_too_large`.
`test_a_streamed_body_under_the_cap_is_replayed_to_the_downstream_app_unmodified`
covers the accept half, asserting the replay is verbatim. No open question is
required and none is filed; R-11(a) needs no increment.

**Deferrals, with their open question.** Only two items in the register are
not fully closed by M0–M8, and each is deferred to a question engineering cannot
answer alone:

- **R-17** — **deferred: OQ-S2-002** for six of the seven pages. M8 proceeds on
  the deletion of the three dead components regardless.
- **R-13 / R-14** — **deferred: OQ-S2-003** and **OQ-S2-004** respectively. M7
  records whatever answer comes back; it does not implement retention or
  downgrade testing on a guess.

---

## M0 — Run what already exists

### Goal
CI runs the tests the repository already contains, and measures the coverage of
the 40% of production Python it currently does not measure.

### Current problem
- `apps/web/legacy-frontend/package.json` defines
  `"test": "node --test tests/*.test.ts"`; the `web` job in
  `.github/workflows/verify.yml` runs *Install locked dependencies*, *Typecheck
  and build*, and *Audit dependency vulnerabilities* — and nothing else. Eight
  test files under `apps/web/legacy-frontend/tests/` never execute, including
  `queryClient.principal-isolation.test.ts`, whose name claims a
  security-relevant guard. **R-09, P0** — and the impact is not that the guard
  is missing but that *the team believes it is present*.
- The `python` job's *Tests* step passes
  `--cov=smartmatch_domain --cov=smartmatch_authz --cov=smartmatch_providers
  --cov=smartmatch_persistence`. `services/api` (14k L) and `services/worker`
  (7k L) are exercised by the same run and unmeasured. **R-10, P2.**

### Target state
The `web` job runs `npm test` and fails on a failing frontend test. The *Tests*
step's `--cov` list names six packages. A coverage baseline for the two services
is recorded in the PR description. **AP-08** — written code is attached; a test
file no lane runs is not attached.

### Files & modules affected
- `.github/workflows/verify.yml` — `web` job (new step after *Install locked
  dependencies*), `python` job *Tests* step.
- `Makefile` — `test` target, so a developer's `make check` and CI agree.
- No production source file.

### Prerequisites
None. M0 is the entry point.

### Implementation steps
1. In `verify.yml`, add a step to the `web` job between *Install locked
   dependencies* and *Typecheck and build*: `name: Unit tests`, `run: npm test`.
   Placed before the build so a failing assertion is reported before a
   four-minute Vite build.
2. Run it once locally (`cd apps/web/legacy-frontend && npm ci && npm test`) and
   record which of the eight files pass. If any fails, **fix the code or the
   test in the same PR** — do not merge a step that is red, and do not skip the
   file. A test that cannot be made green in this increment blocks M0 and gets
   its own commit with an argument.
3. Add `--cov=smartmatch_api --cov=smartmatch_worker` to the *Tests* step's
   argument list.
4. Mirror both into `Makefile`'s `test` target so `make check` runs what CI
   runs.
5. Record the resulting `term-missing` totals for the two services in the PR
   body. **Set no `fail_under`.** A threshold in the same change turns a
   measurement into a gate before anyone has seen the number.

### Tests required
- Existing, newly executed: all eight files under
  `apps/web/legacy-frontend/tests/`, in particular
  `queryClient.principal-isolation.test.ts`.
- No new Python test. M0's subject *is* the test lanes.

### Migration & data concerns
**None.** No schema, no data, no migration.

### Compatibility concerns
The frontend suite runs under `node --test` against `.test.ts` files; Node 20 is
already pinned in the `web` job's `setup-node`. If `node --test` cannot load
TypeScript directly on Node 20, the fix is a loader flag in the `test` script,
**not** deleting the tests or making the step advisory.

### Rollback strategy
Revert the one commit. Both changes are additive lines; nothing else in the tree
references them.

### Completion criteria
- `verify.yml`'s `web` job contains a step invoking `npm test`, and a
  deliberately broken frontend assertion turns the job red on a scratch branch.
- The *Tests* step's `--cov` list contains six `--cov=` flags.
- The PR body states the two new coverage percentages.
- No `continue-on-error`, `|| true`, or `fail_under` was added.

### Follow-up unlocked
M3 can migrate a page and see a regression. M2 can refactor `services/` and see
its coverage effect. T-0.5 (auditing what the principal-isolation test actually
asserts) becomes meaningful, because the answer now changes a build result.

---

## M1 — Attach and assert

### Goal
Wire the code that was written and never called, and turn the command-type map
from something a reader must reconstruct into something CI asserts.

### Current problem
- **R-04, P1.** `default_registry()`
  (`services/worker/smartmatch_worker/handlers.py` ~L1349) returns three
  handlers: `test.noop`, `import.create`, `MATCH_RUN_COMMAND_TYPE`. Two further
  executors are composed **at the root** and are invisible from that function:
  `with_outreach_send` at `services/worker/smartmatch_worker/main.py:470`
  (unconditional when `registry_is_ours`) and `with_paid_extraction` at
  `main.py:492` (only when spend ceilings are configured). Nothing asserts that
  the set of types routers can submit is covered. The miss path is a documented
  terminal refusal — fail-closed, correct — which is exactly why the gap is
  silent.
- **R-08, P1.** `SpendReservationSweeper`
  (`python/smartmatch_persistence/smartmatch_persistence/spend_sweeper.py:107`)
  has no production caller; `grep -rn SpendReservationSweeper` returns the
  module and two test files. The analogous job-lease sweep *is* wired:
  `sweep_expired_leases` is called at
  `services/worker/smartmatch_worker/execution.py:573` as part of the scheduled
  pass. Abandoned reservations stay `reserved` forever instead of becoming
  `expired_spent` (ADR-0015 Amendment A1).
- **R-19, P3.** `services/api/smartmatch_api/utils.py` is 18 lines, one function
  (`utc_now`), 25 consumers. The content is right; the *name* is an invitation.

### Target state
- A test enumerates every command type any router can submit and asserts each is
  either handled by the registry the worker actually runs — including
  root-composed handlers — or listed on an explicit intentionally-refused list
  with a reason. **AP-05**, ADR-0023.
- The scheduled dispatch pass sweeps abandoned spend reservations, and
  `DispatchPassResponse` reports what it swept.
- `smartmatch_api.clock` replaces `smartmatch_api.utils`.
- `docs/architecture/GLOSSARY.md` exists (`domain-model.md` §4).

### Files & modules affected
- `tests/unit/test_command_registry_map.py` — new.
- `services/worker/smartmatch_worker/main.py` — `DispatchPassResponse`
  (L262–299), `_pass_response` (L818), the `ScheduledPass` construction near
  L810.
- `services/worker/smartmatch_worker/execution.py` — the pass body around L573.
- `python/smartmatch_persistence/smartmatch_persistence/spend_sweeper.py` — no
  change expected; it is called, not modified.
- `services/api/smartmatch_api/clock.py` (from `utils.py`) + 25 importers.
- `docs/architecture/GLOSSARY.md` — new.

### Prerequisites
M0 (so `services/worker` coverage moves visibly when the sweeper is wired, and
so the registry test's own coverage is measured).

### Implementation steps
1. **Registry map test.** Create `tests/unit/test_command_registry_map.py`.
   Derive the *submittable* set statically — parse the router modules under
   `services/api/smartmatch_api/routers/` for the command-type argument passed
   to `smartmatch_api.commands.submit_command`, rather than importing a
   hand-written list that would drift the same way the ADR index would without
   `tests/unit/test_adr_index.py`. Model the file on that test: compare both
   directions, and state in the module docstring what cannot be checked.
2. **Cover the root composition.** The registry under test must be the one the
   worker runs, not `default_registry()`. Build it the way `main.py` does — apply
   `with_outreach_send`, and apply `with_paid_extraction` under a configuration
   with spend ceilings — then assert coverage against that. **This is the U1
   resolution made executable**: a test that only reads `default_registry()`
   would report `outreach.send` as unregistered and would have "confirmed"
   Stage 1's wrong count.
3. **Refusal list.** Add an explicit mapping of intentionally-unhandled types
   with a one-line reason each, and assert every entry names a type some router
   can actually submit — the same shape as
   `test_forbidden_scanner.py::test_every_allowlist_entry_names_a_real_rule`.
   Idempotency-scope-only names (`speaker_contact.create`, `job.redrive`,
   `job.abandon`) must **not** appear on it: they never create a job or an
   outbox row, so the static derivation must exclude `_reserve`-only call sites
   rather than excusing them afterwards.
4. **Sweeper — collaborator.** Give the scheduled pass a
   `SpendReservationSweeper` alongside its `StalledJobSweeper`, constructed from
   the same session factory at `main.py` ~L810.
5. **Sweeper — order.** Run it in the same position and for the same reason the
   job sweep runs first (`main.py:670` docstring — *"why the sweep is first"*),
   and isolate its failure the way `execution.py:567-570` argues: a sweeper that
   reported zero when it had failed would be indistinguishable from a healthy
   one.
6. **Sweeper — reporting.** Add `spend_swept: int` and `spend_sweep_failed: bool`
   to `DispatchPassResponse` and populate them in `_pass_response`. Follow the
   existing convention: a count that could not be taken is reported distinctly
   from a count of zero.
7. **Clock rename.** `git mv utils.py clock.py`, update the 25 importers, keep
   `utc_now`'s docstring and its F-003 rationale verbatim. No shim module — a
   compatibility re-export would recreate the dumping ground the rename exists
   to prevent.
8. **Glossary.** Publish `docs/architecture/GLOSSARY.md` from `domain-model.md`
   §4. It records the terms the tables already use; **no table is renamed** —
   the glossary is the alternative to renaming, per the standing anti-pattern.

### Tests required
- `tests/unit/test_command_registry_map.py` — new, the substance of the
  increment.
- `tests/unit/test_spend_sweeper.py` — existing; extend with the pass-level
  assertion that the sweeper is invoked and its counts reach the response.
- `tests/integration/test_spend_reservation.py` — existing; add a case where an
  abandoned reservation becomes `expired_spent` **through a dispatch pass**
  rather than through a direct sweeper call. This is the R-11(b) item: the
  sweep's production behaviour, previously untestable because there was no
  production path.
- Existing worker dispatch tests must still pass with the two new response
  fields.

### Migration & data concerns
**None.** No schema change, no migration, no backfill. The sweeper transitions
existing `spend_reservation` rows from `reserved` to `expired_spent` — that is
the behaviour ADR-0015 Amendment A1 already specifies and the state machine
already permits, not a data migration. Rows that have been stuck since the
sweeper was written will settle on the first pass after deploy; the PR body
should state the expected count from a production `SELECT count(*) … WHERE
status = 'reserved' AND …` so the first pass's numbers are predicted, not
discovered.

### Compatibility concerns
- `DispatchPassResponse` gains two fields. It is a response model consumed by
  Cloud Scheduler and by operators, and additive fields are compatible; the
  heartbeat log line should gain them too, since the module docstring makes the
  log the durable copy and the response the convenient one.
- The `clock.py` rename is source-incompatible for any out-of-tree importer of
  `smartmatch_api.utils`. There are none in this repository; `mypy python/
  services/` in the `python` job proves the in-tree set is complete.

### Rollback strategy
Revert the one commit. If only the sweeper needs reverting — e.g. the first
production pass settles far more rows than predicted — remove the single
`SpendReservationSweeper(...)` constructor argument at `main.py` ~L810; the two
response fields then report zero and false, which is honest, and the registry
test and the rename are untouched.

### Completion criteria
- Deleting `MATCH_RUN_COMMAND_TYPE` from `default_registry()` turns
  `tests/unit/test_command_registry_map.py` red.
- Removing `with_outreach_send` from `main.py` also turns it red. (This is the
  criterion that proves the U1 resolution was implemented rather than restated.)
- Adding a `submit_command("thing.new", …)` call to any router turns it red.
- `grep -rn SpendReservationSweeper services/` returns a non-test production
  call site.
- An integration test observes a `reserved` row become `expired_spent` via a
  dispatch pass.
- `grep -rn 'smartmatch_api.utils\|from smartmatch_api import utils'` returns
  nothing.
- `docs/architecture/GLOSSARY.md` exists and renames no table.

### Follow-up unlocked
ADR-0023 has an executable referent. M7's ADR-0021 can describe a delivery
contract over a registry whose completeness is asserted. Any future capability —
discovery, live send, paid extraction beyond the ceiling case — gets a red build
instead of a silent terminal refusal.

---

## M2 — Declare, then contract, the service layer

### Goal
Bring `smartmatch_api` and `smartmatch_worker` under the same enforced import
discipline as the four `python/` packages, and give the two shared authorization
helpers an owner.

### Current problem
- **R-05, P1.** `services/api/pyproject.toml` declares `smartmatch-domain`,
  `smartmatch-authz`, `smartmatch-providers` — not `smartmatch-persistence` —
  while 33 files under `services/api` import it, starting at
  `services/api/smartmatch_api/main.py:47`
  (`from smartmatch_persistence.engine import create_session_factory`).
  `services/worker` imports it in 10 files with the same omission. It works
  because the `python` job's *Install pinned dependencies* step runs
  `pip install --no-deps -e` over all four packages and pytest's `pythonpath`
  adds every source root. **The manifests do not describe the real graph.**
- **R-06, P1.** `[tool.importlinter].root_packages` lists four packages;
  `smartmatch_api` and `smartmatch_worker` — 28,080 lines, 40% of production
  Python — are ungoverned. Convention is already broken twice:
  `services/api/smartmatch_api/routers/cba_contact_channels.py:131` imports
  `_authorize_speaker_contacts` from `routers/cba_contacts.py`, and
  `routers/outreach_contacts.py:109` imports `READ_RATE_LIMIT` and
  `_authorize_outreach` from `routers/outreach.py`. Both are documented and both
  are *right about the behaviour and wrong about the location*
  (`dependency-analysis.md` §3b).
- **R-06/3c.** Nothing prevents `smartmatch_api` importing `smartmatch_worker`
  or the reverse. Neither does today; the boundary is convention only.

### Target state
Six `root_packages`. Two new contracts: router→router forbidden, api↔worker
forbidden. The two shared helpers live in an owned module following
`services/api/smartmatch_api/job_authz.py`, whose docstring already argues the
case: *"a second copy of a rule is a rule with two places to drift"*.
**AP-01, AP-02**, ADR-0018.

### Files & modules affected
- `services/api/pyproject.toml`, `services/worker/pyproject.toml` — add
  `smartmatch-persistence`.
- `pyproject.toml` — `[tool.importlinter]` `root_packages` plus two contracts.
- `services/api/smartmatch_api/unit_authz.py` — new; sibling of `job_authz.py`.
- `services/api/smartmatch_api/routers/outreach.py`,
  `routers/outreach_contacts.py`, `routers/cba_contacts.py`,
  `routers/cba_contact_channels.py` — import from the new module.
- `services/api/smartmatch_api/main.py` — the router table comments that argue
  the current lateral imports.

### Prerequisites
M0 (coverage of `services/` is measured before authorization code moves) and M1
(the `clock.py` rename is already done, so this increment's diff contains only
boundary work).

### Implementation steps

**M2 lands as two commits, each independently green.** The contract is declared
before it is enforced, so the enforcement commit is a pure deletion.

**Commit 1 — declare.**
1. Add `smartmatch-persistence` to `dependencies` in both service manifests.
2. Add `"smartmatch_api"` and `"smartmatch_worker"` to
   `[tool.importlinter].root_packages`.
3. Add the two new contracts:
   - *forbidden*: `smartmatch_api.routers.*` must not import
     `smartmatch_api.routers.*` (router→router);
   - *forbidden*: `smartmatch_api` ↮ `smartmatch_worker`.
4. Add `ignore_imports` entries for exactly the two known violations —
   `cba_contact_channels.py` ← `cba_contacts`, `outreach_contacts.py` ←
   `outreach` — each with an inline comment naming the promotion that will
   remove it. **The contract is now live and cannot regress**: a *third* lateral
   import fails the *Architecture import boundaries* step immediately, on the
   day it is written rather than after the promotion lands.
5. `PYTHONPATH="$DOMAIN_PATH" lint-imports --config pyproject.toml` green. Merge.

**Commit 2 — promote and remove the exemptions.**
6. Create `services/api/smartmatch_api/unit_authz.py`. Move
   `_authorize_outreach` and `_authorize_speaker_contacts` there as public
   functions, and `READ_RATE_LIMIT` with them. Follow `job_authz.py`'s module
   docstring shape: name the two ways the previous arrangement was wrong, and
   say what the module makes unrepresentable rather than merely fixed.
7. Update all four routers to import from `unit_authz`.
8. Delete both `ignore_imports` entries.
9. Update the arguing comments in `main.py`'s router table: the reason given
   there — *"one question about a unit's outreach with one answer"* — is still
   correct and now points at the module that holds the answer.
10. `lint-imports` green with no exemptions. Merge.

### Tests required
- Existing authorization tests for the outreach and speaker-contact routes must
  pass **unchanged**. If a test has to change, the promotion changed behaviour,
  and it should not.
- `tests/unit/test_unit_authz.py` — new. Direct tests of the promoted functions,
  which were previously only reachable through two routers.
- The *Architecture import boundaries* step is itself the regression test for
  the contracts; verify it by adding a lateral import on a scratch branch and
  observing red.

### Migration & data concerns
**None.** No schema, no data, no migration.

### Compatibility concerns
- Adding `smartmatch-persistence` to the manifests changes nothing about what CI
  installs (`--no-deps -e` over all four), so the step cannot break; it makes a
  future `uv sync --frozen` or slim-container build correct instead of
  accidentally working.
- `include_external_packages = true` is already set, which is what lets the two
  new forbidden contracts name modules across package roots.
- Two new `root_packages` will surface *existing* violations beyond the two
  known ones. If any appear, they are findings: fix or `ignore_imports` them
  **with a comment naming the increment that will remove the exemption**, in
  commit 1, never silently.

### Rollback strategy
Delete the two new `[[tool.importlinter.contracts]]` blocks and the two
`root_packages` entries from `pyproject.toml` — one TOML edit, no code change.
`unit_authz.py` can stay: it is an improvement independent of the contract, and
the routers importing it is a normal intra-package import under any
configuration.

### Completion criteria
- `[tool.importlinter].root_packages` has six entries.
- `grep -rn 'from smartmatch_api.routers' services/api/smartmatch_api/routers/`
  returns nothing.
- No `ignore_imports` entry remains that names a router.
- A scratch-branch import from `smartmatch_worker` into `smartmatch_api` fails
  the *Architecture import boundaries* step.
- Both service manifests list `smartmatch-persistence`.

### Follow-up unlocked
Every module added later — M4's middleware, M6's `ownership.py` — is born under
contract. ADR-0018 becomes a statement about a configuration that exists. A real
wheel build or slim container becomes attemptable.

---

## M3 — Close the contract loop

### Goal
Make the OpenAPI document a contract the frontend *consumes* rather than one it
transcribes, and prove the pattern on exactly one page.

### Current problem
**R-02, P1.** The API's own published `description` claims *"OpenAPI is the
source of truth; the TypeScript client is generated from it and never
hand-maintained"* (`services/api/smartmatch_api/main.py:214`). `clients/` does
not exist. `apps/web/legacy-frontend/src/lib/api.ts` is 4,238 hand-written
lines, and 49 files call `/v1` paths with inline `fetch` and per-page
transcribed response types. `pyproject.toml`'s ruff `extend-exclude` lists
`clients/typescript` — a fossil of the intent (D5). The contract's freshness
*is* gated (*OpenAPI contract is current*, `tools/export_openapi.py --check`),
so the producing side is honest and only the consuming side is unprotected: a
backend field rename passes every gate in `verify.yml` and reaches a user as a
runtime `undefined`.

The deferred-gate list at the bottom of `verify.yml` already names the missing
gate: *"generated TypeScript client drift check (needs clients/)"*.

### Target state
`clients/typescript/` is generated from `contracts/openapi/smartmatch.json` and
committed. A CI step regenerates and fails on drift, in the same spirit as the
*OpenAPI contract is current* step. **One** page imports its types and its call
functions from the generated client. **AP-07**, ADR-0020.

### Files & modules affected
- `clients/typescript/` — new, generated, committed.
- `Makefile` — a `client` target beside `openapi`, and a `client-check` target
  beside `openapi-check`.
- `.github/workflows/verify.yml` — a step in the `web` job; the deferred list at
  the bottom loses that line and gains it under *"Implemented since this list was
  written"*.
- `apps/web/legacy-frontend/src/pages/<one page>.tsx` — the pattern page.
- `apps/web/legacy-frontend/src/lib/api.ts` — untouched except where the
  migrated page's helpers become unused.

### Prerequisites
M0 (the frontend suite runs, so the migrated page's regressions are visible),
M2 (`smartmatch_api`'s dependencies are declared, so the generation step's
import of the app is not pythonpath-dependent).

### Implementation steps
1. Choose the generator and pin it in the lock the same way every other tool
   here is pinned. Record the choice and the pin in ADR-0020 — this is the one
   new external tool the roadmap adds, and it is a build-time tool, not a
   runtime dependency.
2. Generate into `clients/typescript` from the **committed**
   `contracts/openapi/smartmatch.json`, not from a live app. The committed
   document is already proven current by the existing *OpenAPI contract is
   current* step, so the two gates chain rather than duplicating each other.
3. Add `make client` and `make client-check`, mirroring `openapi` /
   `openapi-check` (`Makefile:193,198`).
4. Add the drift step to the `web` job, after *Install locked dependencies*:
   regenerate, diff, fail with the same "run `make client`" message shape the
   *Dependency locks are current* step uses — that step's comment records that
   `diff -q` cost a wrong guess once, so print the diff.
5. Remove `"generated TypeScript client drift check (needs clients/)"` from the
   deferred list and add it to the implemented block, with the same style the
   other entries use. The list is documentation that is read; leaving it stale
   would re-create R-15 in the file that promises honesty about gates.
6. **Migrate one page.** Choose the smallest page with a real `/v1` call and a
   non-trivial response type. Replace its inline `fetch` and its transcribed
   interface with the generated ones. **Do not touch the other 48 files.** The
   deliverable is a pattern with a diff a reviewer can read, plus a short
   `clients/typescript/README.md` section stating how the next page is migrated.
7. Leave `extend-exclude = ["clients/typescript", …]` in `pyproject.toml` — it
   now excludes a path that exists, which is what it was always for.

### Tests required
- `apps/web/legacy-frontend/tests/` — a test for the migrated page's data path,
  running under the lane M0 created.
- The drift step is the regression test for the client: on a scratch branch,
  add a field to a response model, regenerate the OpenAPI document, and confirm
  the client step goes red.
- `tests/unit/` — no new Python test; the producing side is already gated.

### Migration & data concerns
**None.** No schema, no data. "Migration" here is source migration of one page.

### Compatibility concerns
- The generated client must not become a second hand-maintained artifact.
  Anything added by hand under `clients/typescript` is deleted by the next
  regeneration and must therefore live elsewhere; say so in the generated tree's
  README.
- Committing generated output makes it reviewable and makes the drift check a
  diff. The alternative — generating at build time — would hide contract changes
  from PR review, which is the failure this increment exists to fix.
- 48 pages continue to use `lib/api.ts`. That is the intended end state of M3,
  not a debt introduced by it.

### Rollback strategy
Delete the drift-check step from `verify.yml` (one step) and revert the one
migrated page. The `clients/typescript` tree can remain — unreferenced generated
output that no gate consumes is inert, and keeping it preserves the work while
the gate is off.

### Completion criteria
- `clients/typescript` exists and is committed.
- Changing a response model without regenerating turns the `web` job red.
- Exactly one page imports from the generated client; `grep -rl '/v1/'` over
  `src` returns 48 files, one fewer than today.
- The deferred list at the bottom of `verify.yml` no longer names this gate.
- ADR-0020 records the generator and its pin.

### Follow-up unlocked
D2 in `capability-inventory.md` §4 stops being false, which is why M5 can
correct the remaining stale claims without one of them being un-corrected later.
Each subsequent page migration becomes a mechanical change against a documented
pattern.

---

## M4 — Make failure visible

### Goal
A refusal, a rate-limit rejection, or a 500 outside the job path leaves a
durable, correlatable trace.

### Current problem
**R-03, P1.** Across ~70k lines of `python/` + `services/` there are 20 logging
references in 10 files; 22 of 25 router modules log nothing; there is no structured
logging, no tracing, no metrics export. Diagnosis today means reading `job_event`
rows out of PostgreSQL, and only job work writes those. The synchronous routers
— `review.py`, `speaker_requests.py`, and every read path — write nothing at all.
`services/api/smartmatch_api/errors.py` centralises the refusal shapes
(`ApiError` at L47, eight handlers from L104 to L226, `EXCEPTION_HANDLERS`
consumed at `main.py`) — so there is exactly one place where every refusal
already passes, and it is silent.

### Target state
One ASGI middleware beside `MaxBodySizeMiddleware`
(`services/api/smartmatch_api/main.py:108`, added at `main.py:244`) emits one
structured line per request with a correlation id, method, path template,
status, and duration. Every handler in `errors.py` logs once with its code and
that correlation id. **No tracing vendor, no metrics backend, no new
dependency.** **AP-09.**

### Files & modules affected
- `services/api/smartmatch_api/request_log.py` — new; the middleware and the
  correlation-id contextvar.
- `services/api/smartmatch_api/main.py` — one `add_middleware` call, ordered
  relative to `MaxBodySizeMiddleware`.
- `services/api/smartmatch_api/errors.py` — one log call per handler.
- `services/api/smartmatch_api/config.py` — one setting.

### Prerequisites
M2. The middleware is a new module in `smartmatch_api`; it should be born under
the import contract rather than retrofitted into it.

### Implementation steps
1. Write `request_log.py`: a correlation id read from an inbound header if
   present and generated otherwise, held in a `contextvar`, and echoed on the
   response. Structured output means one JSON object per line to stdout — the
   appliance's log destination — using the standard library. No structlog, no
   OpenTelemetry.
2. Add it to `main.py`. **Order matters and must be argued in a comment.**
   `MaxBodySizeMiddleware` is documented as *"the outermost ASGI layer: it must
   see every request before FastAPI's own routing and dependency resolution
   do"*. A 413 refusal is a refusal that should be logged, so request logging
   goes outside it — and the comment must say so, because the existing comment
   asserts outermost-ness and a future reader needs to know it was
   reconsidered, not overlooked.
3. Log the **path template**, never the raw path. A raw path carries ids;
   templates are what an operator groups by, and this repository does not put
   identifiers in logs it has not decided to put there.
4. In `errors.py`, add exactly one log call to each handler, carrying the error
   code and the correlation id. **Once, not twice** — the middleware logs the
   request, the handler logs the refusal's code, and a refusal must not appear
   as two unrelated events.
5. Add `SMARTMATCH_REQUEST_LOG_ENABLED` to `config.py`, defaulting to on. This
   is the rollback lever and the reason the increment is safe to ship to a live
   pilot.
6. Log **no** request or response body, no `Authorization` header, no
   credential, and no email address. The `secrets` job's gitleaks gate scans the
   tree, not the runtime; the discipline here is the author's.

### Tests required
- `tests/contract/test_request_logging.py` — new. A request produces exactly one
  request line; the correlation id in the response header matches the line; an
  inbound correlation id is honoured.
- `tests/unit/test_errors.py` — existing or new: each handler in
  `EXCEPTION_HANDLERS` logs once with its code. Parametrize over
  `EXCEPTION_HANDLERS` so a ninth handler added later is covered without editing
  the test — the same both-ways discipline `test_adr_index.py` uses.
- A test asserting no `Authorization` header value and no request body reaches
  the log.

### Migration & data concerns
**None.** Logs go to stdout. No table, no retention decision here — retention of
*log output* is an appliance concern and belongs with ADR-0022 in M7, not with
the append-only tables of R-13.

### Compatibility concerns
- Log volume rises from ~nothing to one line per request. At pilot volume this
  is negligible; the appliance's log rotation should be confirmed as part of
  M7's topology statement.
- Middleware ordering interacts with `MaxBodySizeMiddleware`'s documented
  outermost position. The 413 path must be covered by the new contract test, or
  the reordering is unproven.

### Rollback strategy
Unset — or set false — `SMARTMATCH_REQUEST_LOG_ENABLED`. No redeploy of code, no
revert. If the middleware itself is at fault, revert the one `add_middleware`
line at `main.py`; `errors.py`'s log calls are independent and harmless alone.

### Completion criteria
- One structured line per request, with a correlation id, observable in the
  appliance's logs.
- Every handler in `EXCEPTION_HANDLERS` logs once with its code, asserted by a
  parametrized test.
- `grep -rn 'opentelemetry\|structlog\|datadog\|sentry'` over the repository
  returns nothing.
- Setting the flag false silences the middleware and leaves every existing test
  green.

### Follow-up unlocked
An operator can answer *"what happened to that request"* without a database
query. M7's ADR-0021 can specify a delivery contract whose violations are
observable. Any future rate-limit or authz change is diagnosable in production.

---

## M5 — Make prose assertable

### Goal
Correct the three stale claims, then make the class of claim that went stale
CI-checkable; and give every planning document a status.

### Current problem
**R-15, P2.** Three documented contradictions (`capability-inventory.md` §4):
- **D1** — `services/api/smartmatch_api/main.py`'s module docstring says
  *"Match-run, discovery, and send commands — each waits on its gate: G1 for the
  factor registry, G3 for agent controls, G4 for consent-origin policy"*, while
  `match_runs.router`, `outreach.router` and `cba_invitations.router` are all
  mounted in `CAPABILITY_SCOPED_ROUTERS` (`main.py:275`, applied at `main.py:466`)
  and `factor_registry.py:149` reads `"approved"`.
- **D2** — the FastAPI `description` at `main.py:214` claims a generated
  TypeScript client. **M3 makes this true rather than M5 editing it.**
- **D3** — `apps/web/legacy-frontend/src/pages/Calendar.tsx:80-95` says
  `routers/events.py` declares no handlers and the contract exposes no event
  operation; the router is 571 lines and the contract publishes
  `GET /v1/units/{u}/events` and `…/invite.ics`.

D1 and D3 share a shape: a docstring written while a gate was open and not
revisited when it closed. Nothing ties a prose claim to the gate's value.

**R-16, P2.** `docs/plans/` holds 40+ documents with no status field, several
describing resolved conditions. The visible git history begins 2026-09-05 while
plans date from 2026-08-28, so history cannot resolve which landed
(**OQ-S2-005**).

### Target state
D1 and D3 corrected. A test asserts no docstring claims G1 is open while
`factor_registry.REGISTRY_STATUS == "approved"` — **the gate constant already
exists to be asserted against** (AP-06). Every `docs/plans` document declares
`ACTIVE` / `LANDED` / `SUPERSEDED BY …` / `ABANDONED`, and a test asserts that
(AP-13).

### Files & modules affected
- `services/api/smartmatch_api/main.py` — module docstring, fourth bullet.
- `apps/web/legacy-frontend/src/pages/Calendar.tsx` — the retirement reason
  text (`CALENDAR_FEED_RETIRED_REASON`). Note this is *correcting the notice*,
  which is one of the three per-page options in M8; correcting the text does not
  pre-empt M8's port-or-delete decision.
- `tests/unit/test_gate_claims.py` — new.
- `tests/unit/test_plan_status_headers.py` — new.
- `docs/plans/**` — one header line each; `docs/plans/archive/` for the settled
  ones.

### Prerequisites
M3 (so D2 is false-no-longer by code rather than by edit) and M1 (the glossary
landed there, so terminology in the corrected prose has a referent).

### Implementation steps
1. Rewrite D1's bullet to state what is actually true: the three routers are
   mounted, capability-scoped via `CAPABILITY_SCOPED_ROUTERS`, and the registry
   reads `"approved"`. Keep the bullet's argument — *"a route that exists before
   its gate closes is a route someone will call"* — which is a principle
   (AP-11), not a stale fact.
2. Rewrite D3's text in `Calendar.tsx` to say what is true: the events router
   and its two contract paths exist, and this feed is retired for a reason that
   is stated accurately or the page is listed for M8's decision.
3. Write `tests/unit/test_gate_claims.py`. Scan Python docstrings and frontend
   source for claims that a named gate is open, and fail if the corresponding
   constant says otherwise. Start with the one pair that exists —
   `factor_registry.REGISTRY_STATUS` and the G1 phrasings — and make the pairing
   a table, so a second gate constant is added to the table rather than to the
   test's logic. Model the module docstring on `test_adr_index.py`: state what
   cannot be checked. A test that reads prose has a false-negative surface, and
   it should say where.
4. Add a one-line status header to every `docs/plans` document. Where the status
   is genuinely unknowable because it predates the visible history, write
   `ACTIVE` and note the uncertainty — **never invent a `LANDED`**. OQ-S2-005
   covers why the history is short.
5. Move non-`ACTIVE` documents to `docs/plans/archive/`.
6. Write `tests/unit/test_plan_status_headers.py`: every `.md` under
   `docs/plans/` has a status line from the fixed vocabulary; a `SUPERSEDED BY`
   names a file that exists. Same both-directions discipline as
   `test_adr_index.py`, and the same honesty about its silent failure mode — no
   test can tell whether an `ACTIVE` document is *still* active.

### Tests required
- `tests/unit/test_gate_claims.py` — new.
- `tests/unit/test_plan_status_headers.py` — new.
- Both run in the `python` job's *Tests* step and therefore in `make check`,
  which is what makes them gates rather than conventions.

### Migration & data concerns
**None.**

### Compatibility concerns
- The gate-claim test scans prose and will produce false positives on documents
  that *quote* a stale claim while discussing it — including
  `capability-inventory.md` §4 and this roadmap. Exempt by path with a reason,
  the way `tools/scan_forbidden.py` exempts prose
  (`test_forbidden_scanner.py::test_prose_naming_a_forbidden_pattern_is_not_a_violation`),
  and assert every exemption has a reason
  (`::test_every_exclusion_has_a_reason`).
- Moving plan documents changes paths that other documents link to. Fix the
  links in the same commit; a broken link is the failure mode this increment is
  meant to reduce.

### Rollback strategy
Revert the one commit. M5 changes two prose blocks and adds two test files; no
production behaviour is touched, so revert is total and instant.

### Completion criteria
- D1 and D3 no longer appear as contradictions when
  `capability-inventory.md` §4 is re-run against the tree.
- Setting `factor_registry.REGISTRY_STATUS = "draft"` on a scratch branch while
  the corrected docstring stands turns `test_gate_claims.py` red — and so does
  restoring the old docstring text with the status left at `"approved"`.
- Every file under `docs/plans/` carries a status from the fixed vocabulary,
  asserted by a test.
- `make check` green.

### Follow-up unlocked
Documentation becomes a gated artifact, which is the precondition for M6's
ownership map being trustworthy documentation rather than another 43-row table
that drifts. OQ-S2-005's answer, when it arrives, can be applied to a corpus
whose statuses are already declared.

---

## M6 — Declare data ownership, and bring indexes under parity

### Goal
Answer *"who owns this table"* as data, close the index blind spot in the schema
parity guard, and bound the one expensive unbounded read.

### Current problem
- **R-20, P3 (structural).** `python/smartmatch_persistence/smartmatch_persistence/schema.py`
  is 2,691 lines defining 44 tables (Stage 1 reported 43; recounted 2026-09-08 —
  `grep -c "= sa.Table(" schema.py`), from `tenant` at L106 through
  `student_speaker_feedback` at L2593. Nothing states which context or service
  owns which. **The consequence is concrete, and it is the Stage 1 audit's own
  error.** `data-architecture.md` §8, `domain-model.md` §6 and
  `dependency-analysis.md` §4 all record `match_run` as having two writers —
  `routers/match_runs.py` and `worker/handlers.py::handle_match_run_create`.
  Verified against the tree, the router writes nothing:
  `routers/match_runs.py:18-30` says nothing there inserts a `match_run` row and
  nothing there could, `job_id` being a `NOT NULL` FK to `job`; its only
  repository calls are reads (`:1035`, `:1175`). `handle_match_run_create`
  (~`:1109`) is the sole writer, through the insert-only
  `smartmatch_persistence.match_runs`. The audit inferred a second writer because
  the API genuinely writes rows *around* a run — `job`, `outbox_record`,
  `idempotency_record`, and the
  `match_weight_setting`/`match_weight_setting_revision` rows. Inference per
  feature got the per-table writer set wrong; that is what a declared map fixes.
- **R-12, P2.** `schema.py` declares zero indexes; all 33 live in migrations
  `0001`–`0033`. `tests/integration/test_schema_matches_migration.py`'s module
  docstring says so explicitly: *"Index sets are not compared because
  `schema.py` declares no indexes on purpose"*. Dropping `ix_outbox_claimable`
  passes every gate and degrades the dispatcher's `SKIP LOCKED` claim to a
  sequential scan — a silent, progressive production slowdown with green CI.
- **R-07, P2.** `GET /v1/units/{u}/metrics/{name}/drill-down` returns *"the rows
  behind the number"*: authenticated, database-heavy, unbounded, and without
  `enforce_rate_limit`. `services/api/smartmatch_api/units.py:31` already
  establishes the pattern with `MAX_SUBTREE_UNITS: Final[int] = 50`.

### Target state
- `python/smartmatch_persistence/smartmatch_persistence/ownership.py` — a Python
  mapping from table name to `(context, writer)`, with a test asserting every
  table in `schema.METADATA.tables` appears exactly once and every entry names a
  real table. **AP-03**, ADR-0019.
- Indexes declared in `schema.py` beside their tables; the parity test compares
  index names in both directions. **AP-10.**
- Metrics drill-down rate-limited and row-bounded. **AP-12.**

### Chosen form of the ownership map, and why

**A Python module, not a YAML file under `docs/`.** Three reasons:

1. The test that gives it force must compare it against `schema.METADATA.tables`.
   A Python mapping is compared by importing both; a YAML file adds a parser and
   a second source of truth about table names.
2. It lives beside what it describes. `schema.py`'s neighbours are already the
   repository modules that import it (26 of them); a reader who opens the
   package finds the ownership statement without knowing to look in `docs/`.
3. **It is the artifact a future `schema.py` split would be performed along.**
   ADR-0019 records ownership *before* any split; a split follows the map
   mechanically. A YAML file in `docs/` cannot be the thing a module split reads.

Shape: `OWNERSHIP: Final[Mapping[str, TableOwner]]` where `TableOwner` is a
frozen dataclass of `context: str` and `writers: tuple[str, ...]`. `context`
comes from the bounded contexts in `domain-model.md`; `writers` names services.

**`match_run`'s ownership is the pattern the map records, and it is a
single-writer entry.** The confusion Stage 1 recorded was never two writers of
one table — it was two tables written at two lifecycle points, read as one
feature:

- **the API writes the request** — `routers/match_runs.py:947` submits
  `MATCH_RUN_COMMAND_TYPE`, which in one transaction writes the `job` row, the
  `outbox_record` that carries the intent, and the `idempotency_record` that
  makes the submission repeatable. It writes no `match_run` row and could not:
  `match_run.job_id` is a `NOT NULL` FK to `job` (`routers/match_runs.py:18-30`);
- **the worker writes the result** — `handle_match_run_create`
  (~`handlers.py:1109`) solves the portfolio and inserts the `match_run`
  snapshot, which is the only row carrying provenance under ADR-0011 and the only
  thing `scoring_mode` (migration `0032`) describes. Nothing else writes it.

So `match_run`'s entry reads `writers=("smartmatch_worker",)`, with a comment
naming the `job`/`outbox_record`/`idempotency_record` rows the API writes on the
other side of the command path — the reason a per-feature reading of this
capability produces the wrong per-table answer. **Every table gets exactly one
writer, and the test asserts that; there is no two-writer table in the tree
today.** The mechanism for one is kept and unused: a future table with two
writers must add an explicit declaration naming both writers and the reason, in a
diff a reviewer will see, rather than appearing as an ordinary insert. That is
what turns `attendance_record` having one writer today into `attendance_record`
having one writer tomorrow — which is what ADR-0013's invariant depends on.

### Files & modules affected
- `python/smartmatch_persistence/smartmatch_persistence/ownership.py` — new.
- `tests/unit/test_table_ownership.py` — new.
- `python/smartmatch_persistence/smartmatch_persistence/schema.py` — `sa.Index`
  declarations only; **no table definition changes**.
- `tests/integration/test_schema_matches_migration.py` — the index comparison
  and the module docstring paragraph that currently excuses its absence.
- `services/api/smartmatch_api/routers/metrics.py` — rate limit and row bound.

### Prerequisites
M5 (documentation-as-gate is an established pattern) and M2 (the ownership module
is a new module in a contracted package).

### Implementation steps
1. Write `ownership.py` with all 44 entries. Derive each writer by grepping the
   repository modules that write the table, **not by assumption** — the Stage 1
   `match_run` error is what assumption costs. Where the grep finds two, that is
   a finding to investigate and then either refute (as `match_run` was) or
   declare explicitly with its reason.
2. Write `tests/unit/test_table_ownership.py`: every table in
   `schema.METADATA.tables` appears exactly once; every mapped name is a real
   table; every `context` is from the fixed vocabulary; **every table has exactly
   one declared writer**. No table is exempt today; an exemption list exists in
   the test only as the mechanism a future two-writer table would have to be
   added to, alongside its stated reason.
3. Declare the 33 indexes in `schema.py` as `sa.Index(...)` beside their tables,
   copying names verbatim from migrations `0001`–`0033`. Names must match
   exactly — the parity comparison is by name.
4. Extend `test_schema_matches_migration.py` to compare index name sets **both
   directions**, matching the file's stated discipline (*"Every check below
   iterates the schema and reports both directions"*). Rewrite the docstring
   paragraph that says indexes are excluded on purpose — leaving it would be a
   fresh R-15.
5. Note the existing partial exception: `test_ltree_paths_have_gist_indexes`
   already asserts two indexes absolutely. Keep it. The file's own comment
   argues why some things are asserted absolutely as well as symmetrically, and
   that argument still holds for the two `ltree` GiST indexes.
6. Apply `enforce_rate_limit` to `routers/metrics.py`, drill-down at minimum,
   and bound the returned row count with a module-level `Final[int]` following
   `units.MAX_SUBTREE_UNITS`.
7. **Do not split `schema.py`.** The split is an optional follow-up after M6 and
   is not part of it. ADR-0019's whole point is that ownership is the
   prerequisite and the split is the consequence.

### Tests required
- `tests/unit/test_table_ownership.py` — new.
- `tests/integration/test_schema_matches_migration.py` — extended, both
  directions.
- `tests/unit/` or `tests/contract/` — the metrics drill-down refuses past the
  rate limit and returns no more than the bound.

### Migration & data concerns
**No migration.** The indexes already exist in the database — they were created
by migrations `0001`–`0033`. `schema.py` only gains *declarations* of indexes
that are already live. Nothing is created, dropped, or rebuilt, and no new
Alembic revision is written. The parity test proves this: if a declaration were
wrong, the comparison against the migrated database fails in CI, before it
reaches a database anyone cares about. `ownership.py` is a mapping of strings and
touches no data at all.

### Compatibility concerns
- Declaring an index in `schema.py` makes it visible to `METADATA.create_all`.
  Nothing in production calls `create_all` — migrations shape the database
  (ADR-0009, one transaction per migration) — but any test fixture that does
  will now build indexes too. That is correct and should be verified rather than
  assumed.
- Rate-limiting the metrics drill-down changes behaviour for an existing
  authenticated caller. If the pilot is live (**OQ-S2-001**, safe default YES),
  set the limit from the observed call rate in M4's request logs rather than by
  guess. This is a concrete reason M4 precedes M6.

### Rollback strategy
Revert the one commit. There is no migration to unwind and no data to restore,
because the increment creates neither. If only the rate limit needs backing out,
raise its constant — one integer — rather than removing the decorator, so the
guard stays and the bound relaxes.

### Completion criteria
- `ownership.py` covers all 44 tables; adding a table to `schema.py` without
  adding it to the map turns `tests/unit/test_table_ownership.py` red.
- Every entry declares exactly one writer — there is no two-writer table today.
  `match_run`'s writer is `smartmatch_worker`, and its comment names the `job`,
  `outbox_record` and `idempotency_record` rows the API writes on the other side
  of the command path.
- Adding a second writer to any table without also adding its explicit
  declaration and reason turns `tests/unit/test_table_ownership.py` red.
- Dropping `ix_outbox_claimable` from a migration on a scratch branch turns
  `test_schema_matches_migration.py` red.
- `test_schema_matches_migration.py`'s docstring no longer says index sets are
  not compared.
- `routers/metrics.py` calls `enforce_rate_limit` and bounds its returned rows.
- **`schema.py` has not been split.**

### Follow-up unlocked
ADR-0019 is enforceable. R-13's retention decisions in M7 have an owner per
table. A `schema.py` split becomes a mechanical follow-up along a boundary that
means something — and remains optional.

---

## M7 — Record the adapter and topology contracts

### Goal
Write down what each unbuilt adapter must satisfy, and say which deployment
topology is real — before either question is answered by improvisation.

### Current problem
- **R-01, P1.** Every production adapter is unproven. Live Resend, live Routes,
  live Cloud Tasks, and the JWKS-to-real-issuer wiring have never executed;
  `providers/registry.py:196,243,258,303` are four *"not implemented in the
  Foundation scaffold"* refusals, and `main.py`'s docstring records that the
  pilot login *"leaves the JWKS verifier unwired"*. The ports and their
  fixture implementations are well tested; the production side of each seam is
  not. At the moment any one is switched on, retry semantics, deduplication,
  bounce handling, and claim mapping all become live at once.
- **R-18, P2.** Two topologies, one executable. GCP Cloud Run is documented
  across 7 Terraform modules and 4 environments, all deliberately non-applyable
  and asserted so by the *Terraform environments share no identifiers* step. The
  Docker Compose appliance is what CI builds, probes and deploys. The repository
  does not say which is current, so the appliance reads as interim scaffolding
  beneath an architecture that does not exist.
- **R-13 / R-14, P3.** No retention policy for five append-only tables; no
  `downgrade()` ever exercised (the `python` job runs `alembic upgrade head`
  only).

### Target state
Four decisions on paper, `Proposed`, none of them implemented speculatively:
- **ADR-0021** — the worker's task-delivery contract: `200` on duplicate, `503`
  on race, `401`/`403`/`501`/`500` semantics, OIDC verified before the body is
  read. Source: `services/worker/smartmatch_worker/main.py`'s module docstring
  and the `/operations/dispatch` docstring at L664.
- **ADR-0022** — the Compose appliance is the current production topology;
  Terraform is a forward design record.
- Retention recorded per table (**OQ-S2-003**).
- Downgrade supported or not, stated (**OQ-S2-004**).

### Files & modules affected
- `docs/architecture/decisions/ADR-0021-worker-task-delivery-contract.md`,
  `ADR-0022-appliance-is-production-topology.md` — new (writer E).
- `docs/architecture/decisions/README.md` — two index rows, in the exact format
  `tests/unit/test_adr_index.py` parses.
- `tests/contract/test_task_delivery_contract.py` — new; ADR-0021 asserted
  against `FixtureTaskQueue`.
- `docs/architecture/current-system-topology.md` — the ADR-0022 statement.

### Prerequisites
M1 (the registry map is asserted, so a delivery contract is a statement about a
complete map), M4 (contract violations are observable in logs).

### Implementation steps
1. Write ADR-0021 from the worker's existing docstring rather than inventing
   semantics. The docstring is the contract; the ADR promotes it from prose in
   one module to a decision with a number, so the eventual live Cloud Tasks
   adapter is **measured against it rather than improvised**.
2. Add `tests/contract/test_task_delivery_contract.py` exercising the contract
   against the fixture queue: a duplicate task name yields `200`, a lease race
   yields `503`, an unverified caller yields `403` and an absent credential
   `401`, and OIDC verification happens before the body is read. The last is the
   security-relevant ordering and the one an adapter author is most likely to
   invert.
3. Write ADR-0022. State that the Compose appliance is production and Terraform
   is a forward design record; state where logs go, how a rollback is performed,
   and when a migration runs relative to a deploy — the three questions
   `deploy.yml` answers for the appliance and nothing answers for GCP. **Build
   nothing for GCP.** Per the standing anti-pattern, write what an adapter must
   satisfy, not the adapter.
4. Record retention per table for `job_event`, `delivery_event`,
   `contact_channel_transition`, `pilot_login_attempt`, and `match_run`
   snapshots. **Implement nothing.** Each table now has a declared owner from
   M6, which is who the period is asked of. Pending OQ-S2-003, record the
   question and the safe default (retain indefinitely at pilot volume) rather
   than a number nobody chose.
5. Record the downgrade decision. If downgrade is not supported, say so and stop
   writing `downgrade()` bodies that will never work; if it is, the follow-up is
   an upgrade→downgrade→upgrade case in the integration harness — which is
   follow-up work, not M7.
6. Add both index rows to `docs/architecture/decisions/README.md` in the format
   `test_adr_index.py` enforces:
   `| [ADR-NNNN](ADR-NNNN-slug.md) | Title | Status | D Month YYYY | Decides | Amended | Supersedes | Superseded by |`,
   with Title matching the `# ADR-NNNN — Title` heading and Status and Date
   matching the `**Status:**` / `**Date:**` lines. Numbers must stay contiguous
   (`test_adr_numbers_are_contiguous_from_one`).

### Tests required
- `tests/contract/test_task_delivery_contract.py` — new; the substance.
- `tests/unit/test_adr_index.py` — existing; it gates the two new rows and will
  fail on a title, status, or date mismatch, on a non-contiguous number, and on
  a status outside {Accepted, Proposed, Rejected, Superseded, Deprecated}.
- No new test for ADR-0022; it is a statement about deployment, and its check is
  that `deploy.yml` and `docker-compose.vm.yml` still describe what it claims.

### Migration & data concerns
**None.** M7 records decisions and adds a contract test against a fixture queue.
Retention is *recorded*, not implemented — no deletion job, no partitioning, no
data touched. R-14's downgrade question is answered on paper; no `downgrade()`
is run against any database in this increment.

### Compatibility concerns
- ADR-0016 is already recorded in `decisions/README.md`'s "Reserved numbers"
  section as reserved-with-no-file while the file exists (CBA scoring policy) —
  a Stage 1 disagreement, and stale. Correct it in the same PR that adds these
  rows, since the reserved-numbers list and the index are read together.
- The contract test asserts against `FixtureTaskQueue`. That proves the *shape*
  of the contract, not the real queue's semantics. Say so in the ADR: this test
  is what the live adapter will be held to, not evidence that it passes.

### Rollback strategy
Revert the one commit. Both ADRs are `Proposed` and no behaviour changes, so a
revert removes two documents, two index rows, and one test — with no runtime
effect whatsoever.

### Completion criteria
- ADR-0021 and ADR-0022 exist, are `Proposed`, and `tests/unit/test_adr_index.py`
  passes with their rows.
- `tests/contract/test_task_delivery_contract.py` covers duplicate, race, and the
  four status codes, and fails when the fixture queue's duplicate behaviour is
  changed.
- `docs/architecture/current-system-topology.md` states the appliance is
  production.
- Retention and downgrade decisions are recorded, or their OQ is cited with a
  safe default.
- No GCP code was written.
- The "Reserved numbers" ADR-0016 entry is corrected.

### Follow-up unlocked
Any adapter — Resend, Routes, Cloud Tasks, JWKS — is now implemented against a
written contract with a test that already encodes it. R-01's remediation is
*"do not pre-build, do write the contract"*, and after M7 the contract exists.

---

## M8 — Owner-gated cleanups

### Goal
Stop showing users pages that cannot work, and delete code that invites a
prohibited capability.

### Current problem
- **R-17, P2.** Seven routed pages — `Dashboard`, `Opportunities`, `Volunteers`,
  `Pipeline`, `Calendar`, `Outreach`, `AIMatching` — call 24 `/api/*` paths that
  no service serves. The repository asserts this itself in
  `tests/e2e/…::test_16_the_portal_pages_have_no_backend_in_this_repository`.
  `Calendar.tsx` renders an honest retirement notice, which is correct under
  ADR-0011 and DESIGN.md §1.2 — and whose **stated reason is now factually
  wrong** (D3). The notice lies. Doing nothing is the one actively misleading
  option.
- **R-06b, P2.** `OutreachWorkflowModal.tsx`, `AgenticOutreachPanel.tsx`,
  `FeedbackForm.tsx` are referenced by nothing. `AgenticOutreachPanel` names an
  "agentic" capability **ADR-0003 excludes from Foundation** — a live invitation
  for a future agent to wire it up against a standing decision.

### Target state
Three dead components deleted. Each of the seven pages carries a recorded
disposition: port to `/v1`, delete, or keep a corrected notice.

### Files & modules affected
- `apps/web/legacy-frontend/src/components/OutreachWorkflowModal.tsx`,
  `AgenticOutreachPanel.tsx`, `FeedbackForm.tsx` — deleted.
- `apps/web/legacy-frontend/src/pages/{Dashboard,Opportunities,Volunteers,Pipeline,Calendar,Outreach,AIMatching}.tsx`
  — per the decision.
- `apps/web/legacy-frontend/src/lib/api.ts` — the 24 `/api/*` helpers, per the
  decision.
- `tests/e2e/` — `test_16` restated to match whatever is decided.

### Prerequisites
M0 (the frontend suite runs, so a deletion's fallout is caught), M3 (a page has
been migrated, so *"port to /v1"* is a known quantity rather than an estimate),
M5 (the `Calendar.tsx` text has already been corrected, so *"keep the notice"*
is already a defensible state).

**Blocked on OQ-S2-002** for the seven pages. **Not blocked** for the three
deletions.

### Implementation steps
1. **Delete the three components** (unblocked). Confirm zero references with a
   reference scan over `src`, then delete. `git` retains them; ADR-0003 is why
   `AgenticOutreachPanel` in particular should not sit there compiling.
2. **Await OQ-S2-002.** Present the owner with the per-page cost using M3's
   migration as the unit of measure: this is the concrete reason M3 precedes M8.
3. Per page, once decided:
   - *port* — migrate against the generated client using M3's pattern;
   - *delete* — remove the route, the page, and its `lib/api.ts` helpers
     together, so no orphan helper survives;
   - *correct the notice* — the M5 text stands and the page stays routed.
4. Update `test_16` to assert whatever is now true. It currently asserts the
   portal pages have no backend **in this repository**; after a port, that is no
   longer true for the ported page, and the test must say so rather than being
   loosened.

### Tests required
- Existing frontend suite (M0) green after deletion.
- `tests/e2e/…::test_16` — restated, never weakened. If pages are ported, the
  test names which pages remain backend-less; it does not stop asserting.
- Per ported page, a test in `apps/web/legacy-frontend/tests/` following M3's
  pattern page.

### Migration & data concerns
**None.** Frontend only. No schema, no data, no `/v1` endpoint added or removed.

### Compatibility concerns
- Deleting a routed page changes URLs users may have bookmarked. If the pilot is
  live (**OQ-S2-001**, default YES), a deleted route needs a redirect or an
  explicit not-found page rather than a blank screen — deleting the route
  without deciding what replaces it recreates R-17's failure mode in a new form.
- The three component deletions carry no such concern: they are referenced by
  nothing and reachable by no route.

### Rollback strategy
Revert the one commit; `git` retains everything. Because deletion and per-page
work are separate commits, the unblocked deletion can stand while any page
decision is reverted independently.

### Completion criteria
- `grep -rn 'OutreachWorkflowModal\|AgenticOutreachPanel\|FeedbackForm'` over
  `apps/web/legacy-frontend/src` returns nothing.
- Each of the seven pages has a recorded disposition, and no page shows a notice
  whose stated reason is false.
- `test_16` asserts the true current state.
- The frontend suite is green.

### Follow-up unlocked
The frontend surface is what it claims to be. Every remaining `/v1` page
migration is mechanical against M3's pattern, and the `lib/api.ts` line count
becomes a number that only goes down.
