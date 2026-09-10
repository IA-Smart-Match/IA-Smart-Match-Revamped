# WIP Archaeology

**Stage 1 §5.** Unfinished work, separated from finished work, with evidence.
Commit `c72dced`.

---

## 0. Method note — why the usual search returned nothing

**OBSERVED.** A repository-wide search of all `.py`, `.ts`, `.tsx` and `.tf`
files under `python/`, `services/`, `apps/`, `tools/`, `db/`, `infra/` found:

| Marker | Occurrences |
|---|---:|
| `TODO` | **0** |
| `FIXME` | **0** |
| `HACK` | **0** |
| `XXX` | **0** |
| `NotImplementedError` | **0** |
| skipped/xfail tests | **1** (`test_vm_deploy_script.py:38`, a platform `skipif`) |

**INFERRED.** WIP in this repository is not marked in code. It is tracked in a
parallel documentation system — named gates (G1–G5, A1b, F5, R2, R4, S12),
`docs/plans/open-questions/*-deferred.md` records, and an agent-memory ledger
with a CI gate. Code either does the thing or **refuses to exist**: the
dominant pattern is a route that is not mounted and a handler that is not
registered, rather than a stub that returns `None`.

This is a genuinely better discipline than TODO comments, because an unmounted
route cannot be called by accident. It has one cost, which this section exists
to pay: **the WIP is invisible to anyone reading only the code.** The searches
that find it are: unmounted capabilities, unregistered command types,
constructors that raise, modules with no production caller, and stale
docstrings.

---

## 1. Provider adapters — written, deliberately unreachable

`smartmatch_providers/registry.py` is the single place a live client can be
constructed, and it refuses in four cases. Each refusal is a WIP item with a
named blocker.

### 1.1 Live email (Resend)

| | |
|---|---|
| **Intended** | Send consented outreach and speaker invitations to real inboxes |
| **Exists** | `providers/resend.py` (339 L), fully unit-tested (`tests/unit/test_resend_email_adapter.py`, 37 tests); the whole compose/send/suppress pipeline (C6) |
| **Missing** | Approved transport; institutional-sender identity decision (OQ-001); recipient policy; deliverability review |
| **Blocker** | Human decision, not engineering. `registry.py:142-150`: *"institutional sender is an identity claim — see OQ-001"*. Recorded in `docs/plans/open-questions/r4-outreach-deferred.md` |
| **Architectural consequence** | The `EmailProvider` port has exactly one production-shaped implementation that has never run. Retry semantics, bounce handling, and `delivery_event` ingestion from a real webhook are **unproven**, not absent-by-design |
| **Safest next step** | Do not wire it. Add a *contract test* that runs `ResendEmailProvider` against a recorded-response transport, so the adapter's behaviour is pinned before anyone has to debug it live |

### 1.2 Live route matrix (Google Routes)

| | |
|---|---|
| **Intended** | Real travel times for the `proximity` and `travel_burden` scoring factors |
| **Exists** | `FixtureRouteMatrixProvider`; `domain/factors/proximity.py` (697 L); `zcta_centroids.py` (1,894 L of CA ZCTA centroid data, regenerable via `make zcta-centroids`); `api/zip_proximity.py` |
| **Missing** | The adapter itself. `registry.py:196`: *"the live Routes adapter is **not implemented** in the Foundation scaffold"* |
| **Blocker** | Not started |
| **Architectural consequence** | Proximity scoring today is **great-circle distance from ZCTA centroids**, not travel time. This is a *different measurement*, not a lower-fidelity one — the factor's meaning changes when the adapter lands, and every stored `match_run` snapshot computed before that will not be comparable to one after |
| **Safest next step** | Before implementing, decide whether `scoring_mode` (migration `0032`) is the right place to record which measurement produced a run. The column exists; use it rather than adding a new one |

### 1.3 Live Cloud Tasks

| | |
|---|---|
| **Intended** | Durable, retrying command delivery in GCP |
| **Exists** | `TaskQueue` port (`providers/tasks.py`), `FixtureTaskQueue`, `worker/local_tasks.py` (507 L, HTTP loopback for compose), deterministic task names (ADR-0007), the whole dispatcher (I2) |
| **Missing** | The GCP client. `registry.py:243` |
| **Blocker** | Depends on the GCP topology existing at all (§5) |
| **Architectural consequence** | The dispatcher's crash-safety properties are proven against a queue that lives in the same process. At-least-once delivery, task deduplication by name, and the `503` retry contract are **modelled and tested but not validated against the real queue's semantics** |
| **Safest next step** | The `503`/`200`-on-duplicate contract in `worker/main.py`'s docstring is the thing to preserve. Write it down as an ADR before implementing, so the adapter is measured against it |

### 1.4 Live identity verifier (A1b)

| | |
|---|---|
| **Intended** | Institutional SSO — the real login |
| **Exists** | `providers/jwks.py` (469 L) with 52 unit tests; `providers/identity.py`; the entire `Principal`/`Membership` model |
| **Missing** | Issuer URL, audience, claim mapping, tenant mapping — all marked *OUTSTANDING — EXTERNAL DEPENDENCY* in `docs/decisions/a1b-idp-configuration-worksheet.md` |
| **Blocker** | The institution. `docs/plans/open-questions/a1b-live-idp-deferred.md` |
| **Interim** | `POST /v1/auth/login` — password login against `pilot_credential`, owner-authorized 2026-09-04. `main.py`'s docstring is explicit that this *"is not A1b, does not unblock it, and leaves the JWKS verifier unwired"* |
| **Architectural consequence** | Two authentication mechanisms now exist. The pilot one is real and in use; the intended one is dormant. Whichever lands second must not become a *third* path — `dependencies.get_current_principal` / `_subject_for_token` is the seam where they must converge |
| **Safest next step** | Verify that `get_current_principal` treats both as "resolve a subject, then load the principal server-side", with no branch that skips the server-side load. It appears to (`dependencies.py:86,119`), and that property is what makes A1b a swap rather than a rewrite |

---

## 2. The command registry — three handlers, eight submitting routers

**OBSERVED.** `worker/handlers.py:default_registry()` registers three command
types: `test.noop`, `import.create`, `match_run.create`.

**OBSERVED.** Eight routers reference `submit_command` / `commands.`:
`imports`, `match_runs`, `redrive`, `review`, `outreach`, `speaker_requests`,
`cba_contacts`, `cba_invitations`.

**OBSERVED.** `handlers.py:11` states the miss behaviour is what matters: an
unregistered command type is a **terminal refusal**, not a crash — and
`default_registry`'s docstring says *"a handler added ahead of its gate is a
handler someone will trigger."*

**OBSERVED — countervailing evidence.** `tests/e2e/…::test_20_the_worker_sends_through_the_fixture_provider`
passes, and `worker/outreach.py` is 607 lines of send execution. So the outreach
send path *does* execute in the worker.

**INFERRED.** The command-type → handler mapping is therefore richer than
`default_registry()` alone shows — either the additional types are constructed
elsewhere, or several routers reuse one of the three registered types. The audit
did not resolve which.

**UNKNOWN — and this is the single most important unknown in the audit.** A
future agent adding an asynchronous capability cannot answer "which command
type does my router submit, and what executes it?" by reading the registry.

**Safest next step (do this first, it is cheap):** add a test that asserts every
command type any router can submit is present in `default_registry()`, or is
explicitly listed as intentionally-refused. That test is the missing map, and it
turns a research question into a build failure.
→ `risk-register.md` R-04, Stage 2 increment **M4**.

---

## 3. The frontend — the largest single WIP surface

### 3.1 The generated client that does not exist

| | |
|---|---|
| **Intended** | `contracts/openapi/smartmatch.json` → generated TypeScript client → consumed by every page |
| **Exists** | The contract (57 paths, 120 schemas), a CI staleness gate (`export_openapi.py --check`), a ruff exclusion for `clients/typescript`, and a claim in the published OpenAPI `description` that the client *is* generated |
| **Missing** | `clients/`. The directory does not exist |
| **Actual state** | Two uncoordinated access styles: `lib/api.ts` (4,238 hand-written lines) and inline `fetch("/v1/…")` across 49 files reaching 42 distinct endpoints |
| **Architectural consequence** | The OpenAPI freshness gate protects the contract but **nothing protects the consumer**. A backend field rename passes every gate in `verify.yml` and surfaces as a runtime `undefined` in a user's browser |
| **Blocker** | None identified. This appears to be unfinished, not deferred — no `*-deferred.md` record covers it |
| **Safest next step** | Generate the client into `clients/typescript`, add a drift check to CI (it is already listed as a deferred gate at the bottom of `verify.yml`), and migrate **one** page to it as the pattern. Do not migrate all 49 files in one change |

→ `risk-register.md` R-02, Stage 2 increment **M3**.

### 3.2 Legacy pages with no backend

`Dashboard`, `Opportunities`, `Volunteers`, `Pipeline`, `Calendar`, `Outreach`,
`AIMatching` are routed and reachable. Between them `lib/api.ts` calls 24
`/api/*` paths — crawler, matching, QR, feedback, agentic-workflow streaming,
`/api/data/*` — and **none** is served by `smartmatch_api`. The repository
asserts this itself in
`tests/e2e/…::test_16_the_portal_pages_have_no_backend_in_this_repository`.

**OBSERVED — handled honestly, not hidden.** `Calendar.tsx` renders an explicit
"this feed is retired" state rather than an empty grid, with a documented reason
(`CALENDAR_FEED_RETIRED_REASON`) and an `isRetiredRoute` predicate. That is the
correct behaviour under ADR-0011 and DESIGN.md §1.2 (*no silent fallback shown
as success*).

**But:** `Calendar.tsx`'s stated reason is now **factually wrong** — it claims
`routers/events.py` declares no handlers and the contract exposes no event
operation. Both are false as of this commit. The page is showing a retirement
notice for a feed whose replacement now exists.

**Safest next step:** these seven pages need a per-page decision — *port to
`/v1`*, *delete*, or *keep the retirement notice and correct its text*. Doing
nothing is the one option that is actively misleading, because the notice now
lies. → Stage 2 increment **M6**.

### 3.3 Dead components

`OutreachWorkflowModal.tsx`, `AgenticOutreachPanel.tsx`, `FeedbackForm.tsx` are
referenced by nothing in `src/`. `AgenticOutreachPanel` additionally names an
"agentic" capability that **ADR-0003 (`no-agents-in-foundation`) excludes**.

**Safest next step:** delete. They are `git`-recoverable, they compile, and
`AgenticOutreachPanel` in particular is a live invitation for a future agent to
"just wire this up" against a decision that says not to.

### 3.4 Frontend tests written but never run

Eight test files under `apps/web/legacy-frontend/tests/` — including
`queryClient.principal-isolation.test.ts`, which by its name guards a
**security-relevant** property (one principal's cached data not leaking to
another). `package.json` defines `"test": "node --test tests/*.test.ts"`.
**No workflow invokes it.**

**Safest next step:** add `npm test` to the `web` job in `verify.yml`. One line.
→ `risk-register.md` R-09, Stage 2 increment **M0**.

---

## 4. `SpendReservationSweeper` — implemented, tested, never scheduled

| | |
|---|---|
| **Intended** | Reclaim reservations whose worker died between committing the debit and reporting the cost (ADR-0015 Amendment A1, T-08) |
| **Exists** | `persistence/spend_sweeper.py` (244 L), `domain/spend.expire_abandoned`, `AbandonedReservationSnapshot` deliberately built without a `lease_token` so nothing from a sweep can satisfy the settle path. Tested: `tests/integration/test_spend_reservation.py` (3 call sites), `tests/unit/test_spend_sweeper.py` |
| **Missing** | **Any production caller.** `grep -rn SpendReservationSweeper` outside the module returns only test files |
| **Contrast** | The *job-lease* sweep is wired: `sweep_expired_leases` is called from `worker/main.py` and `worker/execution.py` as part of the scheduled dispatch pass (`worker/main.py:670` — *"why the sweep is first"*). The spend sweep is the one that was not attached |
| **Architectural consequence** | An abandoned reservation stays `reserved` forever. Per A1 it must become `expired_spent` at its reserved maximum — so the tenant's budget is **not** being charged for spend that may genuinely have occurred. The failure mode is *under*-charging and a slowly-growing set of stuck rows, not data loss |
| **Blocker** | None identified — this looks like a missed wiring step, not a deferral. No `*-deferred.md` covers it |
| **Safest next step** | Call it from the same scheduled dispatch pass that already runs `sweep_expired_leases`, and extend `DispatchPassResponse` to report what it swept. The pass already has the shape (`sweep_failed`, `timed_out` counters); this is an addition to a working mechanism, not a new one |

→ `risk-register.md` R-08, Stage 2 increment **M5**.

---

## 5. GCP topology — configuration with nothing behind it

Covered in `current-system-topology.md` §1. As a WIP item:

| | |
|---|---|
| **Intended** | Cloud Run (api + private worker), Cloud Tasks, Cloud Scheduler, Cloud SQL, GCS, Secret Manager, across `dev`/`staging`/`prod`/`classroom` |
| **Exists** | 7 Terraform modules, 4 environment configurations, `env_isolation_check.py` asserting the environments share no identifier, one root module (`envs/classroom/root.tf`) so `terraform validate` can run over a whole environment |
| **Missing** | Every provider block, backend, resource, and real identifier — **by design and by CI gate** |
| **Blocker** | `docs/plans/open-questions/f5-deploy-deferred.md` |
| **Actual deployment** | The Docker Compose appliance on a pilot VM (`deploy.yml`, `docker-compose.vm.yml`, `smartmatch.sh`) |
| **Architectural consequence** | The system has a *real* deployment target (a VM appliance) and a *documented* one (Cloud Run) and they are not the same. Operational decisions — how to roll back, where logs go, how migrations run at deploy — are answered for the appliance and unanswered for GCP |
| **Safest next step** | Do not build the GCP path speculatively. **Do** write down that the appliance is the current production topology, so it stops reading as an interim scaffold beneath a "real" architecture that does not exist |

---

## 6. Contradictions between plans and implementation

`docs/plans/` holds 40+ documents dated 2026-08-28 → 2026-09-07. The visible
`git` history starts 2026-09-05.

**UNKNOWN.** For any plan dated before 2026-09-05, the audit **cannot** tell
from history whether the work landed, was superseded, or was abandoned. Files
such as `remaining-foundation-r1-work.md`, `defect-remediation.md`,
`frontend-broken-buttons.md`, `transaction-boundary-defects.md` and
`g1-g3-d6-remedy-plan.md` read as open work items; several describe conditions
this audit found already resolved (G1 is closed; `frontend-broken-buttons.md`
B06 is cited in `main.py` as *fixed*).

**Assessment: compounding documentation debt.** 40 plan documents with no
status field is a corpus that a future agent must read in full to know what is
current, and the cost grows with every added plan.

**RECOMMENDATION.** Give every document in `docs/plans/` a one-line status
header (`ACTIVE` / `LANDED` / `SUPERSEDED BY …` / `ABANDONED`) and archive the
non-active ones under `docs/plans/archive/`. This is the cheapest single
improvement to future-agent comprehension in the repository.
→ Stage 2 increment **M1**.

---

## 7. Summary — WIP by disposition

| Item | Kind | Blocked on | Priority |
|---|---|---|---|
| Frontend tests never run in CI (§3.4) | Missed wiring | nothing | **P0** — one line, guards a security property |
| Spend sweeper never scheduled (§4) | Missed wiring | nothing | **P1** |
| Command-registry map unverified (§2) | Unknown | nothing | **P1** |
| No generated API client (§3.1) | Unfinished | nothing | **P1** |
| Undeclared service→persistence dependency (`dependency-analysis.md` §3a) | Manifest error | nothing | **P1** |
| Stale docstrings D1/D3 (`capability-inventory.md` §4) | Documentation | nothing | **P2** |
| Legacy pages with no backend (§3.2) | Product decision | owner | **P2** |
| Dead components (§3.3) | Cleanup | nothing | **P2** |
| `docs/plans/` has no status fields (§6) | Documentation | nothing | **P2** |
| Live email adapter (§1.1) | Deferred | human decision (OQ-001) | **P3** |
| Live identity / A1b (§1.4) | Deferred | the institution | **P3** |
| Live route matrix (§1.2) | Not started | product need | **P3** |
| Live Cloud Tasks (§1.3) | Deferred | GCP topology | **P3** |
| GCP Terraform (§5) | Deferred | F5 | **P3** |
