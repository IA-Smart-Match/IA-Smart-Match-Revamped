# Architecture implementation guide — for the agent doing the work

**Audience:** an AI coding agent about to implement one of the Stage 2
increments (M0–M8) or a new product feature in this repository.
**Status:** ACTIVE · **Date:** 8 September 2026

This is not a style guide. It is the set of things about *this* repository that
will cost you a red lane, a reverted PR, or a real-world harm if you assume the
usual defaults instead.

---

## 1. Read this first — five facts

1. **There is a running pilot.** The appliance is deployed and `POST
   /v1/auth/login` is a real, owner-authorized login against `pilot_credential`
   (`services/api/smartmatch_api/main.py` module docstring;
   `docs/decisions/pilot-login-decision-2026-09-04.md`). Whether real users are
   on it *today* was OQ-S2-001, **answered 2026-09-08: NO — synthetic data only,
   no real users.** So there is no notice period and no deprecation window on a
   removal, and Phases 1–3 may batch. Reversibility is unchanged: every increment
   is still independently reversible, because that is a Stage 2 rule about
   reviewability, not a consequence of who is logged in.

2. **Work in progress is marked by ABSENCE, not by comments.** A repository-wide
   search of `python/`, `services/`, `apps/`, `tools/`, `db/`, `infra/` finds
   zero `TODO`, zero `FIXME`, zero `HACK`, zero `XXX`, zero
   `NotImplementedError` (`docs/architecture/wip-analysis.md` §0). Unfinished
   capability is expressed as a route that is not mounted, a handler that is not
   registered, or a constructor that refuses. You will not find the WIP by
   grepping for markers; you find it by looking for unmounted routers,
   unregistered command types, and constructors that raise.

3. **The inner layers are contracted; the outer ones are not yet.** Four
   `python/` packages sit in import-linter `root_packages` with four contracts,
   numbered 1–4 (`pyproject.toml [tool.importlinter]`; `DEPENDENCY_RULES.md` §3
   carries the number → name → type → DR → AP table, including contracts 5–9
   that M2 adds). `smartmatch_api` and
   `smartmatch_worker` are **not** in `root_packages` — nothing today stops a
   router importing another router, and two already do
   (`routers/cba_contact_channels.py:131`, `routers/outreach_contacts.py:109`).
   M2/AP-01/AP-02 close that. Until then, the boundary you must respect in the
   service layer is a convention you are enforcing by hand.

4. **Documentation is load-bearing and some of it is tested.** The ADR index is
   asserted row-by-row by `tests/unit/test_adr_index.py`; the agent-memory
   ledger is asserted by `tools/agent_memory_check.py` on every `make check`;
   published copy is asserted by `tools/scan_cba_terminology.py`. A stale
   docstring here is a defect, not a nit — `docs/architecture/capability-inventory.md`
   §4 lists five places where prose already contradicts code (D1–D5) and each
   one would mislead the next agent.

5. **Every gate is itself tested, and none of them may be weakened.** `make
   check` = `format-check lint typecheck imports test scan memory licenses
   infra-check`. If your change makes a gate fail, the change is wrong until
   proven otherwise. Loosening a scanner rule, adding an exclusion, or marking a
   test `skip` is a decision that needs an ADR arguing against the decision that
   created the gate.

---

## 2. Before implementing — the checklist, in this order

1. **Read the four architecture documents.** `docs/architecture/TARGET_ARCHITECTURE.md`
   (what we are building toward and where Stage 2 disagrees with Stage 1),
   `docs/architecture/MODULE_BOUNDARIES.md` (which module owns what),
   `docs/architecture/DEPENDENCY_RULES.md` (what may import what),
   `docs/architecture/ARCHITECTURE_PRINCIPLES.md` (AP-01…AP-13). Cite the AP
   number in your PR description; if none applies, say so explicitly.

2. **Identify the owning module.** One bounded context (domain-model §2: Identity
   & Access · Work Substrate · Event Catalog · Matching · Speaker Relationship ·
   Engagement & Outreach) and one owning module from MODULE_BOUNDARIES. If your
   change spans two, you have two changes — split them or argue why not.

3. **Trace the existing behaviour before you add any.** The three entry points
   that answer "what happens today":
   - **HTTP surface** — the router table in `services/api/smartmatch_api/main.py`
     (`CAPABILITY_SCOPED_ROUTERS`, `main.py:275`, mounted at `main.py:466-468`
     only when the capability is enabled). If a route is not there, it does not
     exist for anyone.
   - **Command submission** — `smartmatch_api.commands.submit_command`. One
     transaction: idempotency reservation · job row with its payload · outbox row.
     Quota is deliberately *outside* it (ADR-0015).
   - **Command execution** — `smartmatch_worker.handlers.default_registry()`
     (`handlers.py` ~L1349) **plus the root composition in
     `services/worker/smartmatch_worker/main.py:468-489`**, which is where
     `outreach.send` and `extraction.paid_pages` are actually attached. A reader
     of `default_registry()` alone will conclude those handlers do not exist.
     They do. This is R-04's sharp form.

4. **Locate the existing tests.** `tests/` has seven tiers and each answers a
   different question:
   | Tier | Answers |
   |---|---|
   | `tests/unit` | Does this function/module behave? Also where the *meta* tests live (`test_adr_index.py`). |
   | `tests/integration` | Does it behave against real PostgreSQL? Marked `integration`, excluded from `make test`. |
   | `tests/contract` | Does the published interface still say what it said — OpenAPI shape, adapter contract? |
   | `tests/authz` | Does the policy deny what it must deny, per resource and role? |
   | `tests/golden` | Does the computed output match a recorded, reviewed artifact (scoring, explanations)? |
   | `tests/e2e` | Does the whole path — submit, dispatch, execute — run? Marked `e2e`. |
   | `tests/fixtures` | Shared data. Not a tier. |
   Your change belongs in the tier that would have caught the bug you are
   preventing. A test in the wrong tier does not run in the lane you think.

5. **Justify any new abstraction — the one-implementation-port rule.** Several
   ports here have exactly one production-shaped implementation and one fixture
   (`EmailProvider`, `TaskQueue`, `RouteMatrixProvider`;
   `docs/architecture/wip-analysis.md` §1). That is a *deliberate* debt with a
   named blocker, not a precedent. Do **not** add a port, a strategy, or a
   factory for a second implementation that does not exist. ADR-0003 (no agent
   framework in Foundation) is the recorded form of this rule.

6. **Confirm the dependency rules.** Run `make imports` before you write and
   after. It runs `lint-imports` against the contracts in `pyproject.toml` — four today, nine after M2 (ADR-0018).
   If your change requires a new contract or a new `root_package`, that is an
   M2-shaped change and needs to be argued, not slipped in.

7. **Write or update the tests first.** Red, then green. For anything on the
   command path, the registry-map test (M1/AP-05) is the test that must know
   about your new command type.

8. **Make the minimum coherent change.** Independently shippable *and*
   independently reversible. "Coherent" means the increment leaves no half-state:
   a mounted route with no handler, a registered handler with no gate, or a
   migration with no code that reads the column are all incoherent.

9. **Validate the constraints — `make check`, and what each sub-target catches.**
   | Target | Catches |
   |---|---|
   | `format-check` | `ruff format --check .` — formatting drift. |
   | `lint` | `ruff check .` |
   | `typecheck` | `mypy python/ services/` in strict mode. |
   | `imports` | `lint-imports` — a layer violation (domain importing IO, etc.). |
   | `test` | `pytest tests/ -m "not integration and not e2e"` — includes unit, contract, authz, golden **and `test_adr_index.py`**. |
   | `scan` | `tools/scan_forbidden.py` (the twelve legacy anti-behaviours) and `tools/scan_cba_terminology.py` (retired IA-West vocabulary in CBA-visible copy). |
   | `memory` | `tools/agent_memory_check.py` — the agent-memory ledger's front matter and the git blob hashes its records cite. |
   | `licenses` | `tools/supply_chain.py licenses` — a dependency outside policy. |
   | `infra-check` | `tools/env_isolation_check.py` — Terraform environments share no identifier and nothing is applyable. |
   CI adds, in `.github/workflows/verify.yml`: "Migrations apply from an empty
   database", "OpenAPI contract is current", "No committed environment files",
   "Dependency locks are current", "No local databases or archives committed",
   "Audit pinned dependencies", the `web` job (install, typecheck, build, audit),
   "Dependency license policy", the SBOM step, and "Gitleaks".

10. **Update the docs, and remember two of them are tested.**
    - The architecture doc your change contradicts (do not leave a D1-shaped
      stale claim behind).
    - An ADR if you made a decision, **and its row in
      `docs/architecture/decisions/README.md`** — `tests/unit/test_adr_index.py`
      asserts the row format
      `| [ADR-NNNN](ADR-NNNN-slug.md) | Title | Status | D Month YYYY | Decides | Amended | Supersedes | Superseded by |`,
      that Title equals the ADR's `# ADR-NNNN — Title` heading, that Status and
      Date equal the `**Status:**` / `**Date:**` lines above the first `## `, and
      that numbers are contiguous. Status vocabulary: Accepted, Proposed,
      Rejected, Superseded, Deprecated.
    - The **agent-memory ledger** if you are recording a durable claim a future
      agent should trust. `tools/agent_memory_check.py` requires every field in
      its `REQUIRED_FIELDS` set — including `sources`, `produced_by_commit`,
      `reviewed_by`, `approved_at`, `expires_at`, and `content_hash` — and it
      re-verifies that the git blobs a record cites still hash to what the record
      was approved against. A record whose cited file changed **fails the lane**.
      So: if you edit a file an approved memory record cites, you must
      re-approve the record in the same change.
    - The status header on any `docs/plans` document you touch (AP-13:
      ACTIVE / LANDED / SUPERSEDED BY / ABANDONED).

---

## 3. Rules adapted to this repository

Each rule: **Rule** · Why here · How you would violate it by accident · How to check.

### 3.1 WIP is marked by absence — never add a `TODO`

**Rule.** No `TODO`, `FIXME`, `HACK`, `XXX`, or `NotImplementedError` in
`python/`, `services/`, `apps/`, `tools/`, `db/`, `infra/`. Unfinished work is
either not present, or present and refusing with a named blocker.

**Why here.** `docs/architecture/wip-analysis.md` §0: all five counts are zero
today, and one skipped test exists (a platform `skipif`). The discipline is
better than comments because an unmounted route cannot be called by accident.

**How you would violate it by accident.** Scaffolding a handler "to fill in
next", or leaving a marker where you paused. Either one turns a refusal into a
stub that reports success.

**How to check.** `grep -rn "TODO\|FIXME\|HACK\|NotImplementedError" python/
services/ apps/ tools/ db/ infra/` must stay empty. **Note:** a repository grep
gate for these markers does not exist yet and would be a cheap addition
consistent with §0. It is a *new* gate, not a weakened one — propose it, never
propose an exclusion list for an existing gate.

### 3.2 Never register a command handler ahead of its gate

**Rule.** A command type appears in the registry only once something can
genuinely execute it *or* genuinely refuse it.

**Why here.** `handlers.py::default_registry` docstring: *"a handler added ahead
of its gate is a handler someone will trigger."* `MATCH_RUN_COMMAND_TYPE` is
registered before its submitting route existed precisely because it could both
execute and terminally refuse (`registry_not_ready`).

**How you would violate it by accident.** Registering the handler in the same PR
as the port, before the policy decision that gates it lands.

**How to check.** For each new registry entry, name the gate and the terminal
refusal path. The M1 registry-map test (AP-05) asserts every submittable type is
registered **or** explicitly listed as intentionally refused.

### 3.3 Never mount a route for a gated-off capability — never `if enabled:`

**Rule.** A capability that is off owns **no router**. There is no feature flag
inside a handler.

**Why here.** `main.py:275` `CAPABILITY_SCOPED_ROUTERS` pairs each router with a
`Capability`, and `main.py:466-468` includes it only when
`settings.capability_enabled(...)`. A route that exists before its gate closes is
a route someone will call. Non-negotiable #12.

**How you would violate it by accident.** Adding `if get_settings().x_enabled:`
inside the handler and returning 404 — which publishes the operation in the
OpenAPI document, tells an attacker the surface exists, and leaves the disabled
build's contract wrong.

**How to check.** Your router appears in the `CAPABILITY_SCOPED_ROUTERS` tuple
with an argued comment (read the existing comments for `calendar` and
`cba_*` — they argue *why* a router shares a capability rather than taking one).
Regenerate OpenAPI with the capability off and confirm the paths are absent.

### 3.4 Never introduce a parallel service abstraction without justification

**Rule.** One submission path, one registry, one authorization evaluator, one
schema module. A second one is a fork of a rule.

**Why here.** `commands.py` exists precisely so submission is not copied into
each router; `job_authz.py` exists because it *was* copied. Anti-goals: no
service split, no event bus, no CQRS, no broker.

**How you would violate it by accident.** Writing a "lightweight" helper that
does what `submit_command` does minus the outbox row, because your case "does not
need dispatch".

**How to check.** Ask which existing module already owns this responsibility.
If the answer is "one exists but it does not quite fit", extend it or argue in
an ADR — do not clone it.

### 3.5 Never bypass the owning domain module or duplicate a business rule

**Rule.** A rule lives in exactly one place and is called, never restated.

**Why here — the cautionary tale is in tree.**
`services/api/smartmatch_api/job_authz.py`'s own docstring records what happened
last time: `routers/jobs.py::_authorize_job_read` consulted no `resource_grant`
at all, so an administrator's explicit deny stopped `/redrive` and `/abandon`
and was **ignored** by the status and event routes that read the same job's
payloads; and `routers/redrive.py::_authorize_redrive` restated the policy's four
rules in Python — *"it got them right, and a second copy of a rule is a rule with
two places to drift."* Steps 1, 2, 3, 5 and 6 of the evaluation order are
`smartmatch_authz.evaluate`'s, **called rather than copied**.

**How you would violate it by accident.** Writing "just this one check" inline in
a router because importing the helper feels heavy.

**How to check.** Any authorization decision in a router body that is not a call
into an owned authz module is a violation. Note the two router→router imports
that exist today (`cba_contact_channels.py:131`, `outreach_contacts.py:109`) are
the *symptom* M2/AP-02 fixes — do not add a third.

### 3.6 Never leak provider semantics into the domain

**Rule.** `smartmatch_domain` imports no framework, no storage, no provider, no
IO, no environment — including `os` and `pathlib`.

**Why here.** Contract 1 in `pyproject.toml [tool.importlinter]`, ADR-0002,
non-negotiable #1. It is what makes the adapters swappable and the golden tests
deterministic.

**How you would violate it by accident.** Reading a threshold from an env var
inside a factor; putting a provider's error class into a domain exception
hierarchy; typing a domain function against an SDK's response object.

**How to check.** `make imports`. If it passes but you passed a provider object
into the domain, the contract did not catch it — check the signature by eye.

### 3.7 Never create generic abstractions for hypothetical needs

**Rule.** Build for the callers that exist.

**Why here.** ADR-0003 records that Foundation ships **no** agent orchestration,
adapter, or tool layer — the framework choice is deferred rather than inherited.
AP-08: written code is attached or deleted; there is no production-shaped module
without a production caller.

**How you would violate it by accident.** Adding a second implementation slot to
a port that has one fixture and one unwired adapter, "for when we add the other
vendor".

**How to check.** Name the production caller of every new module in the PR
description. If you cannot, delete it.

### 3.8 Never silently change persisted-state semantics

**Rule.** If the meaning of a stored value changes, the change is versioned and
recorded, and old rows stay readable and are never compared across the boundary.

**Why here — three concrete carriers.**
- **The 12 job states** (`python/smartmatch_domain/smartmatch_domain/jobs.py:35`:
  `queued`, `dispatched`, `running`, `succeeded`, `partial`, `failed_provider`,
  `failed_budget`, `failed_policy`, `cancelled`, `timed_out`, `redrive_pending`,
  `abandoned`). `failed_provider` and `timed_out` are the only failure states
  with a transition back to `queued`; relabelling a budget stop as a provider
  failure produces a job retried against a ceiling that will never move.
- **`scoring_mode`** (migration `0032_match_run_scoring_mode.py`) exists so a run
  records *which measurement* produced it — for example the pinned
  `cba-physical-1` / `cba-virtual-1` modes of ADR-0016. When the live route
  matrix lands, proximity stops being great-circle distance and becomes travel
  time: a *different measurement*, not a better one
  (`wip-analysis.md` §1.2). Record it in `scoring_mode`; do not add a column.
- **`REGISTRY_VERSION`** — ADR-0016 moved it to `2.0.0-approved-oq-cba-004`
  (`factor_registry.py:137`) with `SUPERSEDED_REGISTRY_VERSION =
  "1.1.1-approved-g1-m6j"` (`:143`) kept so 1.x runs stay readable but are never
  compared across the bump. That is the precedent to follow.

**How you would violate it by accident.** "Fixing" a factor's formula in place,
or adding a state to the enum without touching the transition table.

**How to check.** Does any stored row computed before your change still mean what
it said? If not, bump the version constant and keep the superseded one.

### 3.9 Never remove a compatibility path before proving it unused

**Rule.** A path that exists for the *other* product or the *previous* rulebook
is deleted only with evidence that nothing reads it.

**Why here.** `ProductScope.IA_WEST_LEGACY`
(`python/smartmatch_domain/smartmatch_domain/product_scope.py:96`, classified at
`:240`) exists precisely because CBA is the other product — and
`tools/scan_cba_terminology.py`'s header says so explicitly, which is why the
terminology scan is scoped rather than a global grep. `SUPERSEDED_G1_MODEL`,
`SUPERSEDED_REGISTRY_VERSION` and `SUPERSEDED_SCORING_KEYS`
(`factor_registry.py:110-112, 143, 394`) exist to reproduce, not re-derive, prior
runs.

**How you would violate it by accident.** A rename sweep that "cleans up" a
legacy identifier, or deleting a superseded constant because nothing imports it
in `services/`.

**How to check.** `grep -rn` across `python/`, `services/`, `apps/`, `db/`,
`tests/` **and** the golden fixtures. Then ask whether stored rows reference it.

### 3.10 Never infer a contract from type annotations alone

**Rule.** Where runtime validation exists, the runtime validation *is* the
contract. Annotations are a convenience.

**Why here.** The API's contract is the Pydantic models and the exported OpenAPI
document (`tools/export_openapi.py`; CI step "OpenAPI contract is current"), not
the Python types. In the database, the **check constraints** are the contract —
`schema.py` is hand-written for exactly this reason (ADR-0004), and the parity
test compares schema and migrations both ways.

**How you would violate it by accident.** Widening a field's annotation and
assuming callers now accept it; adding a column with a Python default and no
check constraint, so the invariant holds only for writes that go through your
code path.

**How to check.** Read the Pydantic validators and the `CheckConstraint` list,
not the type hints. Regenerate OpenAPI and diff.

### 3.11 Preserve the transactional and concurrency invariants

**Rule.** Do not move a statement across a transaction boundary, and do not
touch a leased row you do not own.

**Why here — the invariants, each with its file.**
- **One transaction on submission** — idempotency reservation · job row *with its
  payload* · outbox row (`commands.py` docstring). A rolled-back command must not
  burn an idempotency key; a committed job must never exist without its outbox
  row. J10 is the recorded failure: the payload used to be hashed and dropped, and
  every import failed because nothing recorded what to import.
- **Quota is charged before refusal, in its own transaction** (ADR-0015). The
  router charges first, and `submit_command` takes the resulting `QuotaCharge` as
  *evidence*. A `403`/`404`/`400` costs the caller. Do not "helpfully" refund.
- **Lease + generation + `SKIP LOCKED`** — the outbox claim is a single CTE using
  `FOR UPDATE SKIP LOCKED` (ADR-0005; `outbox.py:20`, and the claim's own comment
  at `outbox.py:410-412` explains that without `SKIP LOCKED` a second dispatcher
  serializes behind the first). Ownership is `status = 'leased' AND lease_token =
  :token` together (`_held_by`, `outbox.py:211-267`): `leased` alone is a
  *liveness* test and lets a dispatcher whose lease expired mid-enqueue overwrite
  a peer's fresh lease. **`NULL` is not "expired"** (`outbox.py:196-206`) — a
  leased row carrying no token is left alone. `redrive_generation` in
  `derive_task_name` (`outbox.py:283`) is what separates a retry from a re-drive
  without costing determinism (ADR-0007).
- **One transaction per migration** (ADR-0009) — a lock a revision takes is
  released when that revision ends.
- **The savepoint pattern in `routers/redrive.py`** (`:46-84`) — a refusal rolls
  the savepoint back so the command did not happen, *while the quota increment,
  which committed earlier in its own transaction, stands*. The broad `except`
  that rolls it back and still commits is deliberate; J15/J16/S-008 are the
  recorded holes it closes.

**How you would violate it by accident.** Adding a `session.commit()` inside a
helper; refunding quota on a 4xx; filtering claimed rows by `status = 'leased'`
alone; adding `OR lease_token IS NULL`.

**How to check.** Integration tests under `tests/integration`, plus reading the
docstrings above — they name the exact tests that hold each property (e.g.
`test_a_leased_row_with_no_lease_is_left_alone`).

### 3.12 Never weaken a CI gate

**Rule.** Gates are added, never relaxed. An exclusion, a `skip`, a widened
regex, or a removed step needs an ADR arguing against the decision that created it.

**Why here.** Non-negotiable #13. The gates, by name: `format-check`, `lint`,
`typecheck`, `imports`, `test`, `scan` (forbidden-behaviour + CBA terminology),
`memory`, `licenses`, `infra-check` — plus CI's "Migrations apply from an empty
database", "OpenAPI contract is current", "No committed environment files",
"Dependency locks are current", "No local databases or archives committed",
"Audit pinned dependencies", "Dependency license policy", the SBOM step,
"Gitleaks", and the `web` job.

**How you would violate it by accident.** Adding your file to
`scan_forbidden.py`'s exclusion list because a rule fired on a docstring, instead
of rewording the docstring.

**How to check.** `git diff` on `tools/`, `Makefile`, `.github/workflows/`,
`pyproject.toml`. Any change there is a gate change and must be argued in the PR.

### 3.13 Identity is never caller-supplied (MM-A01)

**Rule.** Tenant, actor, and role are derived server-side from a verified token.
No route takes an identity parameter.

**Why here.** `scan_forbidden.py:61` (the rule that forbids the archived
caller-selected-identity login route) and `:166` (`client-supplied-identity`) are
both executable. The legacy baseline
(`bdce024:src/api/routers/portals.py:435`) let a caller *choose* who they were.
`GET /v1/me/portals` is the corrected shape — it takes no parameter at all,
"a portal follows from who you are, not from an id you send" (`main.py`
docstring). `dependencies.get_current_principal` / `_subject_for_token`
(`dependencies.py:86,119`) is the single seam where both authentication
mechanisms converge, and both resolve a subject then load the principal
server-side.

**How you would violate it by accident.** Accepting a tenant id in a request
model "for the operator tools"; reading a role out of the parsed request body.

**How to check.** `make scan`. Then read your request models: no field names an
identity.

### 3.14 A score carries provenance or is null; null never renders as 0

**Rule.** A number with no evidence is `unknown`, never `0`. No percentages
invented for presentation. A hard-coded score literal is a build failure.

**Why here.** ADR-0011 (four rules for user-visible numbers) and
`scan_forbidden.py`'s `fabricated-score` rule, which fails the build on a
score/confidence assignment to a numeric literal. ADR-0016 adds a *third*
evidence state, `policy_neutral`, at the versioned constant
`CBA_NEUTRAL_TOPIC_VALUE` — precisely so a deliberate neutral is not confused
with a genuine `unknown`, and so weights are never re-spread per candidate.

**How you would violate it by accident.** A frontend `?? 0`, a `|| 0`, or a
`toFixed` on a nullable score; a default value in a Pydantic response model.

**How to check.** `make scan`, plus
`docs/plans/adr0011-frontend-coercion-inventory.md` for the shapes already found.

### 3.15 The terminology scan will reject retired vocabulary in CBA-visible copy

**Rule.** Copy a CBA user can read must not say *IA West*, *Insights
Association*, *chapter*, *Chapter Admin*, *Member Portal*, *volunteer
opportunity*, or *membership / dues* as a product concept.

**Why here.** `tools/scan_cba_terminology.py` — customer requirements §4 and §25
P0. Its scope is deliberately narrow: `SCANNED_ROOTS` (the legacy frontend source
tree minus tests) plus `SCANNED_FILES` (named backend files whose string literals
are rendered verbatim, such as a registered metric's definition). It strips
TypeScript comments before matching, because *"a comment explaining why the
authorization `membership` row is untouched is not copy, and a gate that cannot
tell the difference forces engineers to delete their own explanations."*

**How you would violate it by accident.** Adding a user-facing string that says
"membership"; or, in the other direction, renaming the backend `membership`
record to satisfy a grep the scanner deliberately does not run.

**How to check.** `python tools/scan_cba_terminology.py` (or `--json`).

### 3.16 The ADR index and the agent-memory ledger are tested — update both

**Rule.** An ADR without a conforming index row fails `make test`. An approved
memory record whose cited git blob changed fails `make check`.

**Why here.** `tests/unit/test_adr_index.py` (row format, title match, status and
date match, contiguous numbering) and `tools/agent_memory_check.py` (required
front-matter fields; blob hashes re-verified against approval). The index carried one known staleness
until this Stage 2 change corrected it — `decisions/README.md`'s "Reserved
numbers" said ADR-0016 was reserved with no file while `ADR-0016-cba-scoring-policy.md`
had existed since 5 September 2026. Keep it in mind as the failure mode, not as
an open defect: the tested half stayed green while the untested prose beside it
went stale.

**How you would violate it by accident.** Adding the ADR file and forgetting the
row; editing a file that an approved memory record cites, in an unrelated change.

**How to check.** `make test` and `make memory`.

---

### 3.17 Cite a Proposed ADR as Proposed, and flip it in the PR that implements it

**Rule.** ADRs 0018–0023 are `Proposed`. If your change implements one, say so as
**"implementing Proposed ADR-00xx"** in the PR body, and in that same PR:

1. change the ADR's `**Status:**` line from `Proposed` to `Accepted`, and
2. change the Status column of that ADR's row in `decisions/README.md`.

Both edits or neither — `tests/unit/test_adr_index.py` asserts the two agree, so
half the flip fails `make test`. A **partially** implemented ADR stays `Proposed`:
status is binary and the increment is the unit. Do not flip an ADR you did not
implement, and do not describe an ADR as Accepted in a PR body while it reads
`Proposed` in tree — that is a claim about a repository that does not exist. The
process is recorded in `decisions/adr-backlog.md` § *Process*.

**How you would violate it by accident.** Writing "per ADR-0020" in a PR body
when ADR-0020 is still Proposed; flipping the `**Status:**` line and forgetting
the README row; flipping an ADR because your change touched the same area.

**How to check.** `make test` (the index test), and `grep -n '\*\*Status:\*\*'`
against the ADR you cited.

---

## 4. How to add X

### 4.1 A new router

1. Decide the **owning module** and put the file under
   `services/api/smartmatch_api/routers/`.
2. **Authorize by calling, never restating.** Job-scoped operations go through
   `job_authz.py`. Unit/subject-scoped operations use the shared helpers — which
   today still live inside `routers/outreach.py` and `routers/cba_contacts.py`
   and are imported router-to-router (`outreach_contacts.py:109`,
   `cba_contact_channels.py:131`). **Do not add a third such import.** If you need
   one of those helpers, that is the trigger for M2/AP-02: promote it into an
   owned module in the same change.
3. **Charge quota first** (ADR-0015) — the charge is the route's first statement,
   ahead of the resource load and the authorization, and commits in its own
   transaction. Apply the read rate limit (see `READ_RATE_LIMIT` for the pattern).
   Bound every list read (AP-12; `units.MAX_SUBTREE_UNITS` is the pattern).
4. **Mount it in `CAPABILITY_SCOPED_ROUTERS`** (`main.py:275`) with a comment that
   *argues* the capability choice — whether it takes its own `Capability` or
   shares one, and why a deployment offering one without the other would or would
   not be a coherent product. The existing `calendar` and `cba_*` comments are the
   model.
5. **Write a contract test** under `tests/contract`, and an authz test per denial
   reason under `tests/authz`.
6. **Regenerate the OpenAPI document** with `python tools/export_openapi.py`; CI's
   "OpenAPI contract is current" step fails otherwise. After M3, regenerate the
   TypeScript client too and let the drift gate check it (ADR-0020).

### 4.2 A new command type

1. Define the type as a **constant in the domain module that owns it** — the
   pattern is `MATCH_RUN_COMMAND_TYPE` (`domain/match_run.py:75`) and
   `OUTREACH_SEND_COMMAND_TYPE` (`domain/outreach.py:126`). Never a bare string
   literal at the call site.
2. Submit it through `commands.submit_command` — nothing else writes a job row.
3. Attach an executor: either in `default_registry()`
   (`handlers.py` ~L1349) or, if it needs configuration the registry must not
   own, at the **root composition** in `worker/main.py:468-489` — which is how
   `outreach.send` (`with_outreach_send`, unconditional when `registry_is_ours`)
   and `extraction.paid_pages` (only when spend ceilings are configured) are
   attached. If you compose at the root, say so in `default_registry()`'s
   docstring: today a reader of that function cannot see those two.
4. **Add the entry to the registry-map test** (M1/AP-05): every type a router can
   submit is registered or explicitly listed as intentionally refused. Types that
   are *idempotency-scope names only* — `speaker_contact.create`
   (`routers/cba_contacts.py:302,1097`), `job.redrive` and `job.abandon`
   (`routers/redrive.py:388,527,589`) — reserve a key and create no job or outbox
   row, and belong in the refusal list, not the handler map.
5. **Declare the `job_event` vocabulary** your handler emits, and pick the failure
   exception deliberately: `PolicyFailure` → `failed_policy` (terminal),
   `BudgetFailure` → `failed_budget` (terminal), `ProviderFailure` →
   `failed_provider` (re-drivable). Read parameters from `context.job.payload`,
   never from the delivery.

### 4.3 A new table

1. Add it to `python/smartmatch_persistence/smartmatch_persistence/schema.py`
   by hand (ADR-0004), with the composite `(tenant_id, id)` unique key if it is
   tenant-owned, and composite foreign keys to tenant-owned parents (a foreign key
   straight to `tenant` stays single-column).
2. Write the migration as `db/migrations/versions/0034_<slug>.py` — **current head
   is `0033_event_filed_by.py`**, so the next number is `0034`. One transaction per
   revision (ADR-0009).
3. Add the **ownership entry**: one owning bounded context, one owning
   repository module in `smartmatch_persistence`, and the declared
   writing-service set — one service, unless you declare more *and* give the
   reason (AP-03 / ADR-0019, from M6). Ownership is declared as data and checked
   by a test — do not leave it inferable. Do not type the writers in from memory:
   run `tools/derive_table_writers.py`. It makes two passes — over
   `python/smartmatch_persistence`, to find the one module issuing `insert()` /
   `update()` / `delete()` against your `schema.<table>` and to collect that
   module's mutating method names; then over `services/api` and `services/worker`,
   to find which service packages call them — and prints
   table → repository module → {services}. Its output seeds the entry and the
   ownership test re-runs it, so a half the tool cannot confirm, or a caller the
   tool finds and the map does not declare, fails the lane. Two services is a
   legitimate answer for a table on the command path — `job`, `job_event`,
   `outbox_record`, `idempotency_record` and `spend_reservation` all declare both,
   with the reason "API records intent / worker transitions state (ADR-0005,
   ADR-0015 A1)" — but it is never a silent answer.
4. The **parity test** compares `schema.py` and the migrations both ways.
   Post-M6 that includes indexes (AP-10/R-12), so declare indexes in `schema.py`.
5. Write a **check-constraint test**: the constraint is the contract (§3.10).
6. Do not add a snapshot or counter table. Points are a fold over the append-only
   `point_ledger_entry`, never a stored counter (ADR-0013).

### 4.4 A new provider adapter

1. Define or reuse the **port** in `smartmatch_providers`, typed only in domain
   and stdlib terms. The adapter takes its transport as a constructor argument and
   imports no HTTP client — `smartmatch_providers.jwks` and
   `smartmatch_providers.resend` are the two worked examples, and a test asserts
   the absent import while another walks every call site under `services/` and
   `python/` asserting nothing passes a transport.
2. Ship the **fixture implementation** as the default from the builder.
3. **Refuse in `registry.py` until the gate opens**, with the blocker named in the
   refusal message and recorded in a `docs/plans/open-questions/*-deferred.md`
   file (`registry.py:142-150`, `:196`, `:243` are the three existing refusals).
4. Write a **contract test** that runs the adapter against a recorded-response
   transport, so its behaviour is pinned before anyone debugs it live. ADR-0021
   is the pattern for the task-delivery contract: 200 on duplicate, 503 on race,
   and OIDC verified before the body is read (`worker/main.py` docstring).

---

## 5. Definition of done

- [ ] `make check` is green — all nine sub-targets.
- [ ] `make imports` passes and no new import-linter contract was weakened.
- [ ] Tests exist in the tier that would have caught the failure, and they failed
      before the implementation existed.
- [ ] Every new command type is in the registry map test — registered or
      explicitly refused — and its executor's composition point is documented.
- [ ] Every new route is in `CAPABILITY_SCOPED_ROUTERS` with an argued comment,
      is quota-charged first, rate-limited, and bounded.
- [ ] OpenAPI regenerated; CI's "OpenAPI contract is current" passes.
- [ ] No `TODO`/`FIXME`/`HACK`/`NotImplementedError` added; no `if enabled:` inside
      a handler; no new port with a single implementation.
- [ ] No stale prose left behind: every docstring and architecture document your
      change contradicted is corrected in the same change.
- [ ] ADR written if a decision was made, **and** its index row added in the
      tested format.
- [ ] If the change implements a `Proposed` ADR (0018–0023): the PR body says
      "implementing Proposed ADR-00xx", the ADR's `**Status:**` line reads
      `Accepted`, and its `decisions/README.md` row's Status column matches
      (§3.17). A partial implementation leaves the ADR `Proposed` and the PR body
      still cites it as Proposed.
- [ ] Agent-memory ledger re-approved if your change touched a file an approved
      record cites.
- [ ] `docs/plans` documents you touched carry a status header.
- [ ] The change is independently shippable **and** independently reversible on a
      live pilot (OQ-S2-001).
