# Opus Audit → Architecture Planner Handoff

**Stage 1 complete.** Commit `c72dced`, 2026-09-08.
**To:** the Stage 2 architecture planner (Fable 5.1).
**From:** Claude Opus, Stage 1 audit.

> **Baseline caveat.** This audit is pinned to `c72dced`. `main` has since moved
> to `5fca118` (PRs #126–#139): migration head `0033`→`0034`, tables 44→45,
> routers 26→27, OpenAPI 57/120→59/125. The structural findings were re-checked
> against `5fca118` and hold — **R-09 in particular is unchanged and still P0**.
> See `CURRENT_ARCHITECTURE_AUDIT.md` §0. Verify counts in tree, never from a
> document.

---

## 0. Completion gate — status

| Gate condition | Met | Where |
|---|---|---|
| Major runtime paths traced | ✅ | `current-system-topology.md` §2–4 (request path, command path, three trust boundaries) |
| Major persistence paths traced | ✅ | `data-architecture.md` §§2–6; `CURRENT_ARCHITECTURE_AUDIT.md` §6 |
| Primary domain concepts documented | ✅ | `domain-model.md` §3 (11 concepts, as implemented) |
| Feature status evidence-based | ✅ | `capability-inventory.md` — every row cites entry point, modules, tables, tests |
| WIP separated from finished | ✅ | `wip-analysis.md` — and §0 explains why the usual `TODO` search returns nothing here |
| Architecture risks prioritised | ✅ | `risk-register.md` — 20 risks, P0–P3 |
| Facts separated from recommendations | ✅ | OBSERVED / INFERRED / RISK / RECOMMENDATION / UNKNOWN used throughout |
| Contradictory documentation identified | ✅ | `capability-inventory.md` §4 — five contradictions, D1–D5 |
| Unresolved areas explicitly listed | ✅ | `CURRENT_ARCHITECTURE_AUDIT.md` §19 — eight unknowns, U1–U8 |

---

## 1. Read this first — the three things that will surprise you

**1. This is not a scaffold.** It calls itself "Foundation scaffold" in its own
manifest. It has 21 implemented capabilities, 57 published API paths, 44 tables
with 119 check constraints, 3,807 test functions, 17 ADRs, and a 26-step e2e
walk against a live appliance. **Do not plan as though you are designing a
system. Plan as though you are strengthening a running one.**

**2. There are no `TODO`s — zero, repository-wide — and that is not because
there is no WIP.** Unfinished work here is expressed as *absence*: an unmounted
route, an unregistered handler, a constructor that raises. It is tracked in a
parallel documentation system of named gates (G1–G5, A1b, F5, R2, R4, S12) and
`docs/plans/open-questions/*-deferred.md` records. This is a *better*
discipline than TODO comments and you should preserve it. Its one cost is that
WIP is invisible to code-only reading — which is what `wip-analysis.md` exists
to correct.

**3. The inner layers cannot drift; the outer ones have no guard.** Four
`import-linter` contracts make the domain, authz, providers and persistence
packages genuinely uncrossable — the domain may not import `os`. But
`services/api` and `services/worker`, 28,000 lines between them, appear in **no
contract**, and their manifests do not declare a package they import in 43
files. Almost every P1 risk is downstream of that asymmetry.

---

## 2. The system in one paragraph

A Python `uv` monorepo: four pure/inner packages (`smartmatch_domain` —
functional core, 85 frozen value objects, 5 state machines, no IO;
`smartmatch_authz` — deny-by-default `ltree`-scoped policy;
`smartmatch_providers` — ports plus fixture adapters; `smartmatch_persistence`
— 44 PostgreSQL tables and 26 repositories), two FastAPI services
(`services/api`, 26 routers behind an OpenAPI contract; `services/worker`, a
private OIDC-gated task executor), and a React SPA. Writes that must reach a
provider go through a transactional outbox: the API records intent in one
transaction and returns a job id, a scheduler drives a dispatcher that claims
outbox rows with `SKIP LOCKED` and creates deterministically-named tasks, and
the worker verifies OIDC *before reading the body* and executes. PostgreSQL is
the only store and holds coordination state as well as business data. It runs
as a Docker Compose appliance on a VM; the GCP Terraform is a design record
that CI actively prevents from being applyable.

---

## 3. What is stable — do not touch

These work, are tested, and are load-bearing. Changing them costs more than it
returns.

- The **command path**: outbox, `SKIP LOCKED` CTE claim, deterministic task
  names, lease + generation, 12 job states, idempotency records, redrive.
  44 tests including crash-window cases. (ADR-0005, ADR-0007, ADR-0009)
- **Authorization**: `evaluate`/`assert_allowed`, `ltree` scope, GiST indexes,
  composite tenant-safe keys. Complete coverage across all 26 routers.
- **The four import contracts** and `tools/scan_forbidden.py`. These are the
  reason the codebase is clean; any target architecture must extend them, never
  relax them.
- **Database integrity**: 119 checks, 68 `RESTRICT` FKs, zero `SET NULL`,
  whole-schema parity guard.
- **ADR-0011 accountable numbers**, enforced in three places (scanner, e2e, UI
  components). This is the product's defining commitment.
- **Capability gating by absence.** A gated-off capability owns no router.
  Preserve this — never replace it with `if enabled:`.
- The **test pyramid**, including the fact that the gates themselves are tested.

---

## 4. What is transitional — plan around it

| Area | State | Blocked on |
|---|---|---|
| Live email (Resend) | adapter written + unit-tested; constructor refuses | human decision, OQ-001 |
| Live identity (JWKS/A1b) | verifier written, 52 tests, **unwired**; pilot password login is the interim | the institution |
| Live route matrix | **not implemented**; proximity is great-circle from ZCTA centroids, which is a *different measurement*, not a coarser one | product need |
| Live Cloud Tasks | port + fixture + loopback only | GCP topology |
| GCP Terraform | 7 modules, 4 envs, deliberately non-applyable | F5 |
| The 7 legacy frontend pages | routed, backed by 24 endpoints nothing serves; retirement notice now factually wrong | owner decision |

---

## 5. The findings that should shape the target architecture

Ordered by how much they constrain your design.

1. **The service layer has no contract** (R-05, R-06). `services/*` are absent
   from `root_packages` and mis-declare their dependencies. Two routers already
   import sibling routers' private helpers. Any module-boundary design you write
   is unenforceable until this is fixed — and it is cheap to fix.
2. **The contract loop is open** (R-02). The OpenAPI document *itself* claims a
   generated TypeScript client. `clients/` does not exist. 42 endpoints are
   consumed by hand-transcribed types across 49 files. This is the highest-value
   structural gap.
3. **The command registry is not a map** (R-04, U1). Three registered handlers,
   eight submitting routers, no assertion tying them. A future agent cannot
   answer "what executes my command?" from the code.
4. **No data ownership is declared** (R-20). 44 tables in one 2,691-line
   module; match-run rows have two writers. Ownership is the prerequisite for
   any structural change to `schema.py` — **do not propose splitting the file
   before declaring ownership**.
5. **The system is blind outside the job path** (R-03). 20 logging references
   in 70k lines. Inside a job, `job_event` is excellent. Everywhere else there
   is nothing.
6. **Written-but-unattached code** (R-08, R-09). The spend sweeper and the
   frontend test suite both exist and neither runs. These are wiring, not
   design.
7. **Two deployment topologies, no statement of which is current** (R-18).
8. **Documentation drift in a repository where documentation is load-bearing**
   (R-15, R-16). Three false claims found, one published in the OpenAPI
   document; 40+ plan documents with no status field.

---

## 6. Constraints your target architecture must respect

These are decisions already made, with recorded reasoning. Overturning one
requires an ADR that argues against the existing ADR, not a preference.

| Constraint | Source |
|---|---|
| The domain layer imports no framework, storage, provider, IO, or env — including `os` and `pathlib` | import-linter contract 1, ADR-0002 |
| PostgreSQL is the only store; Redis/Pub/Sub/BigQuery are deferred with objective triggers | `smartmatch_persistence/__init__.py`, v1.1 §2.4 |
| No handler performs provider IO inline | v1.1 §1.6, `scan_forbidden.py:136` |
| Identity is never caller-supplied | `scan_forbidden.py:61,166`, MM-A01 |
| A score carries provenance or is `null`; never a percentage | ADR-0011 |
| Attendance is the only input to points | ADR-0013 |
| Quota is charged before refusal | ADR-0015 |
| Schema is hand-written, not reflected — composite tenant-safe keys are the point | ADR-0004 |
| One transaction per migration | ADR-0009 |
| **No agents in Foundation** | ADR-0003 |
| Terraform environments share no identifier, and nothing is applyable | `env_isolation_check.py`, v1.1 §3.2–3.3 |
| A gated-off capability owns no router | `main.py:CAPABILITY_SCOPED_ROUTERS` |

---

## 7. Explicit anti-goals for Stage 2

Derived from what the audit found, not from general principle:

- **Do not propose a rewrite.** This is a running system with a pilot
  deployment.
- **Do not propose splitting `schema.py` on line count.** Ownership first; the
  split is the optional consequence.
- **Do not propose a service mesh, event bus, CQRS, or microservice split.**
  Nothing in the repository exerts that pressure, and PostgreSQL-as-coordinator
  is a recorded decision with stated adoption triggers.
- **Do not propose building the GCP path speculatively.** Write down what the
  adapters must satisfy; build them when there is a reason.
- **Do not propose a snapshot scheme for the points ledger.** Folding is
  correct at this scale and ADR-0011's reproducibility depends on the ledger
  staying the source of truth.
- **Do not propose renaming database tables** to fix terminology. Write a
  glossary.
- **Do not propose generic abstractions for the foreseeable-but-unrequested**
  (multi-region, public API, ML matching, websockets). ADR-0003 already
  excludes the nearest one.
- **Do not weaken any existing gate** to make a migration easier.

---

## 8. Where the leverage is

If Stage 2 produces only one thing, it should be a **module-boundary and
dependency-rule specification for `services/*` that is enforceable by
`import-linter`**, because:

- it is the largest ungoverned surface (28k lines, 40% of production Python);
- the repository already has the enforcement mechanism, configured and running
  in CI, with four working contracts as the pattern;
- two violations already exist, both documented and both well-motivated, which
  means the *rule* needs writing, not the discipline;
- and every subsequent structural change — the client, the registry map,
  ownership, the observability layer — lands inside boundaries that either do
  or do not hold.

The second-highest leverage is the **generated client plus drift check**,
because it is already listed as a deferred gate at the bottom of `verify.yml`
and closes the one loop where a passing CI can still ship a broken page.

---

## 9. Document map

| Document | Answers |
|---|---|
| `CURRENT_ARCHITECTURE_AUDIT.md` | The authoritative report. Start here |
| `repository-inventory.md` | What is in the repository, and what the git history can and cannot tell you |
| `current-system-topology.md` | What runs, and the two topologies |
| `dependency-analysis.md` | Which boundaries are real; the fan-in and cycle analysis |
| `domain-model.md` | The domain as implemented; bounded contexts; terminology collisions |
| `capability-inventory.md` | Per-capability status with evidence; the five doc/code contradictions |
| `wip-analysis.md` | Unfinished work, how to find it here, and the safest next step for each item |
| `data-architecture.md` | Tables, constraints, ownership ambiguity, indexes, migrations |
| `risk-register.md` | 20 prioritised risks, and what the audit looked for and did **not** find |

---

## 10. Unknowns you inherit

U1–U8 in `CURRENT_ARCHITECTURE_AUDIT.md` §19. The two that most affect
planning:

- **U1 — the command-type → handler map.** Resolve it with the R-04 test before
  designing anything asynchronous.
- **U6 — is the pilot live with real users? ANSWERED, at `793678b`.** A VM does
  serve `https://pilot.plated.blog`, and `docs/operations/vm-deploy.md` states it
  is synthetic: dev edition, fixture providers, seeded data, no identity
  provider, no real user and no production data. Plan the P1 items as
  **pre-go-live hardening, not live incident response** — and do not soften them
  on that basis. The same document reports its own runbook was never bootstrapped
  onto the serving machine. **That gap is now closed** (PR #153, `13ebaf2`):
  the VM was bootstrapped and a promotion produces a real deployment.

- **A limit on this audit you should not inherit.** Deployment configuration was
  outside its evidence base, and a live authentication bypass sat there — public
  fixture bearer tokens on an internet-reachable appliance with no Access wall
  (`ee277ba`, now fixed). Recorded as **R-21**. When you write the target
  architecture's trust boundaries, put `docker-compose.yml`, the compose
  environment, and the tunnel/Access posture *inside* them.
