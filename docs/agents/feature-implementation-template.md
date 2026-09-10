# Feature implementation template

**Status:** ACTIVE · **Date:** 8 September 2026

Copy this file, fill every field, and put the result in the PR description or in
`docs/plans/`. A field you cannot fill is a decision that has not been made —
say so as UNKNOWN and name who decides, rather than picking a default silently.
Read `docs/agents/architecture-implementation-guide.md` first; this template is
its worksheet.

**Do not, while filling this in:**

- Do not write a `TODO`, `FIXME`, `HACK`, or `NotImplementedError` anywhere in
  the change. WIP here is marked by absence (`wip-analysis.md` §0).
- Do not add `if <capability>_enabled:` inside a handler. A gated-off capability
  owns **no router** (`main.py:275`).
- Do not add a port, strategy, or factory with one implementation for a second
  implementation that does not exist yet (ADR-0003, AP-08).
- Do not add a snapshot, cache, or counter table for something that is a fold
  over an append-only ledger (ADR-0013).
- Do not weaken a gate, add a scanner exclusion, or `skip` a test to go green.

---

## Feature

- **Name:**
- **One sentence, in product terms:**
- **Gate / card / risk ID it closes (G-n, R-nn, OQ-…):**
- **Which Stage 2 increment does it sit in or after (M0–M8, T-x.y)?**

## User / business requirement

- **Which committed artifact requires this** — customer requirements §, a plan in
  `docs/plans/`, an ADR, or an owner decision record? Cite it.
- **Who is the user, and which role/portal do they hold?**
- **What is the harm if this is wrong** — a coordinator sees a stale number, or a
  real person receives something they never consented to? (This determines which
  way the safe default must fail.)
- **What is explicitly out of scope in this change?**

## Existing system context

- **What happens today** for this user, traced through the three entry points:
  the router table in `main.py`, `commands.submit_command`, and
  `default_registry()` + the root composition in `worker/main.py`?
- **Which of this already exists but is unreachable** — an unmounted router, an
  unregistered command type, a provider refusing in `registry.py`?
- **Which docstrings or architecture documents describe the current behaviour,
  and are any of them stale** (see `capability-inventory.md` §4 D1–D5)?

## Owning domain (bounded context)

- **One of the six** (domain-model §2): Identity & Access · Work Substrate ·
  Event Catalog · Matching · Speaker Relationship · Engagement & Outreach.
- **The glossary terms this feature uses**, spelled as the GLOSSARY spells them.
  If the term is new, define it there rather than inventing a synonym.
- **If it spans two contexts:** why is that not two changes?

## Owning module

- **Module from `MODULE_BOUNDARIES.md`** that owns the new behaviour:
- **Which layer** — domain / persistence / providers / authz / api / worker /
  web?
- **What must it import, and does `make imports` permit that today?** If a new
  import-linter contract or `root_package` is needed, that is M2-shaped work —
  say so.

## Existing interfaces it extends

- **Ports** it uses (and their current implementations — fixture, live, or
  refusing):
- **Routers** it extends or sits beside:
- **Command types** it submits or executes:
- **Authorization evaluator / policy rules** it calls (never restates):

## Data changes

- **Table(s)** added or altered, and the columns:
- **Ownership entry** — owning bounded context, owning repository module in
  `smartmatch_persistence`, and the declared writing-service set (AP-03 /
  ADR-0019). One service unless you declare more and give the reason, as the five
  command-path tables do. If both API and worker would write it, say so here and
  say why; seed the entry from `tools/derive_table_writers.py` rather than from
  memory.
- **Migration number** = current head + 1. Head is `0033_event_filed_by.py`, so
  the next is `0034_<slug>.py`. One transaction per revision (ADR-0009).
- **Check constraints** — the constraint is the contract, not the annotation.
  List each and the invariant it holds.
- **Parity** — declared in `schema.py` by hand (ADR-0004), including indexes
  (AP-10), with the composite `(tenant_id, id)` key if tenant-owned.
- **Does any stored value change meaning?** If so, name the version constant that
  is bumped and the superseded constant that is kept (the `REGISTRY_VERSION` /
  `SUPERSEDED_REGISTRY_VERSION` precedent, ADR-0016).

## API changes

- **Router and paths:**
- **Capability it is mounted under** in `CAPABILITY_SCOPED_ROUTERS`, and the
  argument for that choice (own capability vs shared — is a deployment offering
  one without the other a coherent product?).
- **OpenAPI regenerated** with `python tools/export_openapi.py`? CI's "OpenAPI
  contract is current" must pass.
- **Generated client** regenerated, and the drift gate green (post-M3 /
  ADR-0020)? Until then, name the hand-written call site in `lib/api.ts` you had
  to touch and why that is unavoidable.

## Security and authorization

- **Which authz helper decides** — `job_authz.py` for job-scoped operations; the
  owned unit/subject-scoped module otherwise. Never a rule restated in a router,
  never a router→router import.
- **Identity is never from the body** — confirm no request model carries a
  tenant, actor, user, or role field (MM-A01; `scan_forbidden.py:61,166`).
- **Rate limit** applied, and the read bound (AP-12; `units.MAX_SUBTREE_UNITS`).
- **Quota charged before refusal** — as the route's first statement, in its own
  transaction, with the `QuotaCharge` passed as evidence (ADR-0015).
- **Denial reasons** each covered by a `tests/authz` case.

## Consent and privacy

- **Does this disclose one person's activity to another?** If yes, it needs a
  *disclosure consent* record — subject, audience scope, purpose,
  granted/revoked — which is **not** `smartmatch_domain.consent` widened
  (ADR-0014).
- **Does this contact anyone?** Then the consent lifecycle, suppression records,
  and unsubscribe path apply, and nothing may send until the R4 open questions
  are answered (`docs/plans/open-questions/r4-outreach-deferred.md`).
- **Which suppression / revocation check runs, and where?**
- **What PII does the new table or log line hold, and for how long** (see
  OQ-S2-003 on retention)?

## Command-path vs synchronous decision

**The rule:** if the work performs provider IO, needs more than one transaction,
or has retry semantics, it is a **submitted command**, not a request handler.
`commands.py`'s docstring states what is deliberately absent from the request
path: *"no provider call, no Cloud Tasks call, no work. The request path only
records intent."* `scan_forbidden.py:136` enforces the provider half.

- **Decision:** command / synchronous.
- **Which of the three triggers applies** (provider IO · >1 transaction · retry
  semantics)?
- **If command:** the type constant and its owning domain module; where the
  executor is composed (`default_registry()` or the root in `worker/main.py`);
  the registry-map test entry (registered, or explicitly refused —
  idempotency-scope-only names go in the refusal list).
- **If synchronous:** state positively that it touches no provider and commits
  once. `routers/review.py:40` and `routers/speaker_requests.py:25` are the two
  routers that mention `submit_command` in prose and deliberately do not use it —
  match that clarity.

## Observability

- **If command:** which `job_event` rows are written, at which transitions, and
  which failure exception maps to which terminal state (`PolicyFailure` →
  `failed_policy`, `BudgetFailure` → `failed_budget`, `ProviderFailure` →
  `failed_provider` — the only re-drivable one alongside `timed_out`).
- **If synchronous (from M4 on):** the structured request log line with its
  correlation id, and the `ApiError` code that is logged exactly once (AP-09).
- **What can an operator see when this fails**, without reading the database?
- **No tracing vendor.** Do not add one.

## Tests required

| Tier | What this feature needs there |
|---|---|
| `tests/unit` | |
| `tests/contract` | |
| `tests/authz` | |
| `tests/golden` | |
| `tests/integration` | |
| `tests/e2e` | |

- **Which test fails today, before the implementation?** Name it.
- **Which existing test would have caught this bug if it had existed?**

## Migration and rollback

- **Deploy order** — migration first, or code first? Say which, and why the other
  order breaks.
- **Is this reversible?** OQ-S2-001 is answered NO — the pilot carries synthetic
  data only — so no user-facing notice period is required. State the rollback
  window and the exact rollback action anyway: every increment is independently
  reversible by rule.
- **Is a downgrade required?** Note that whether migration downgrade is a
  supported operation at all is OQ-S2-004 — do not assume it.
- **What happens to rows written by the new code if the code is rolled back?**

## Documentation to update

- [ ] The architecture document(s) this change contradicts.
- [ ] Every docstring whose claim your change makes stale (D1/D3 are what that
      looks like when it is skipped).
- [ ] ADR written? Number, slug, Status (`Proposed` unless the owner accepted it),
      Date in house format (e.g. `8 September 2026`).
- [ ] **ADR index row** in `docs/architecture/decisions/README.md`, in the format
      `tests/unit/test_adr_index.py` asserts — title equal to the `# ADR-NNNN —
      Title` heading, Status and Date equal to the `**Status:**` / `**Date:**`
      lines, numbers contiguous.
- [ ] **Agent-memory ledger** — a new record if this establishes a durable claim,
      and **re-approval of any existing record whose cited file you edited**
      (`tools/agent_memory_check.py` re-verifies blob hashes; a stale record fails
      `make check`).
- [ ] `docs/plans/` status header on any plan you touched: ACTIVE / LANDED /
      SUPERSEDED BY / ABANDONED (AP-13).
- [ ] GLOSSARY entry if the feature introduces a term.

## Completion criteria

- [ ] `make check` green (format-check · lint · typecheck · imports · test ·
      scan · memory · licenses · infra-check).
- [ ] CI green, including "Migrations apply from an empty database", "OpenAPI
      contract is current", the `web` job, and the secret scan.
- [ ] Every field above is filled or explicitly UNKNOWN with a named decider.
- [ ] No gate was weakened, excluded, or skipped.
- [ ] The change is independently shippable **and** independently reversible.
