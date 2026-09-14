# Future Feature Integration

**Stage 2.** Where the next ten things go, and — more often — which existing
seam already holds them. Written against commit `c72dced`, 2026-09-08.

This document exists because the repository's dominant failure mode for a
future agent is not *"where do I put this"* but *"I could not tell that a seam
already existed, so I built a second one."* Every section below therefore
answers the same question in the same order, and the **"what new abstraction is
justified"** row answers **none** ten times out of ten. That is the finding, not
a stylistic preference: the audit found ports for email, route matrix, task
queue, identity and paid extraction; a command registry; a factor registry; a
capability gate; and a published contract. The extension points are built. What
is missing is proof that they hold, which is why every section's real content is
in **testing requirements**.

**The governing anti-goal (handoff §7).** Do not build the GCP path
speculatively, do not add generic abstractions for the foreseeable-but-
unrequested, and do not propose a rewrite. Write down what an adapter must
**satisfy**, so that when it is built it is *measured* rather than improvised.

---

## 0. Preamble table

| Capability | Owning module | Interface it extends (the seam) | New abstraction justified? | Migration? | Gate / OQ |
|---|---|---|---|---|---|
| Live email (Resend) | `providers/resend.py` + `worker/outreach.py` | `EmailProvider`, via `registry.build_email_provider` | **None** | No | G4; OQ-001 (sender identity), OQ-002 (tenant/domain/DPA) |
| Live identity (A1b) | `providers/jwks.py` + `api/dependencies.py` | `TokenVerifier`, via `registry.build_token_verifier` → `dependencies.get_token_verifier` | **None** — and a third auth path is forbidden | No | A1b; `a1b-live-idp-deferred.md`; the institution |
| Live route matrix | `providers/` (adapter absent) + `domain/factors/proximity.py` | `RouteMatrixProvider`, via `registry.build_route_matrix_provider` | **None** | **`scoring_mode` already exists — migration `0032`** | R1, open decision 6; **OQ-S2-006** |
| Live Cloud Tasks | `providers/tasks.py` + `worker/dispatcher.py` | `TaskQueue`, via `registry.build_task_queue` | **None** | No | F5; depends on GCP topology existing |
| GCP deployment (F5) | `infra/terraform/` | Nothing in the application. ADR-0022 names the appliance as current | **None** | No | F5; `f5-deploy-deferred.md`; ADR-0022 |
| Calendar API (G5) | `domain/calendar_invite.py` + `routers/calendar.py` | The `.ics` download **is** the shipped substitute | **None** | Unknown until scoped | G5; `calendar-deferred.md` OQ-001 |
| Additional scoring factors | `domain/factor_registry.py` + `domain/factors/` | The factor registry + `REGISTRY_VERSION` supersession record | **None** | No | G1 closed; registry approval by the named approver |
| Additional command types | router + `worker/handlers.py` or the worker root | `submit_command` → `CommandRegistry` | **None** | No | AP-05 test must pass; the capability's own gate |
| Retention / archival | `db/migrations` + a dispatch-pass sweep | The scheduled dispatch pass (`sweep_expired_leases` precedent) | **None** | Yes, per table | **OQ-S2-003**; R-13 |
| A second client (mobile / other SPA) | `clients/typescript` (pinned `openapi-typescript`) | The generated client + the OpenAPI contract | **None** | No | Blocked on M3 existing at all |

---

## 1. Live email (Resend)

**Where it belongs.** Nowhere new. `providers/resend.py` is 339 lines,
unit-tested with 37 tests, and `worker/outreach.py` is 607 lines of send
execution that already runs — e2e 20 proves the worker sends through the fixture
provider. The live path is the same path with a different object injected.

**Owning module.** `smartmatch_providers/resend.py` owns the transport;
`smartmatch_worker/outreach.py` owns the send decision, the consent re-check and
`delivery_event` recording; `worker/main.py` owns the composition.

**Interface it extends.** `EmailProvider`, constructed by
`registry.build_email_provider`. Today that constructor refuses three ways, each
naming its decision: no transport wired (OQ-002 — *"which Resend tenant, on
which verified sending domain, under whose data-processing contract"*), no From
address (OQ-001 — *"the institutional sender is an identity claim… a live
adapter must not guess one"*), no credential. It fails **at boot** rather than
at send time, "so a deployment that acquired a credential cannot discover this
one message at a time."

**What new abstraction is justified: none.** A "mail service" layer between
`worker/outreach.py` and the port would put a second place between the consent
check and the send, and the module's single most valuable property is that *to
answer "under what conditions does this system email a person", a reader has to
read one function*. Bounce and webhook handling do not need an abstraction
either — `delivery_event` and `suppression_record` already exist and
`DeliveryEventType` is a closed vocabulary; a Resend webhook is an ingest route
that maps a provider event onto that vocabulary.

**Boundary that must not be crossed.** `scan_forbidden.py:136` — no `resend.`
call within 600 characters of a route decorator. A webhook route **receives**
delivery signals; it never sends. AP-04 restated: provider-touching work is a
submitted command with a registered executor. And `_FIXTURE_ONLY_EDITIONS`
(registry.py:40) must keep refusing a live client under the classroom edition
even when a credential is present — classroom isolation is enforced in code,
not by configuration convention (v1.1 §3.3).

**Migration requirements.** None. `outreach_send`, `delivery_event`,
`suppression_record` and `contact_channel` all exist.

**Testing requirements.** A **contract test against a recorded transport**
(`wip-analysis.md` §1.1): run `ResendEmailProvider` against recorded responses —
success, hard bounce, soft bounce, rate limit, 5xx — and pin the mapping from
each onto `SendDisposition` and `DeliveryEventType`, plus which failure type the
handler raises (`ProviderFailure` is re-drivable; `PolicyFailure` and
`BudgetFailure` are not, and mislabeling a budget stop as a provider failure
produces a job retried against a ceiling that was never going to move). Pin the
behaviour **before** anyone has to debug it live. Existing consent guarantees
stay asserted end-to-end (e2e 18, 21).

**Gating / OQ.** G4 (consent-origin policy, supervised recipient policy,
deliverability review), OQ-001, OQ-002 — all recorded in
`docs/plans/open-questions/r4-outreach-deferred.md`, whose stated policy is that
every deferral fails toward *not sending*. Preserve that asymmetry: a deferral
that fails toward action costs a real person an email they never agreed to
receive, and no later decision undoes it.

---

## 2. Live identity (A1b)

**Where it belongs.** `providers/jwks.py` (469 L, 52 unit tests) becomes
reachable. Nothing else moves.

**Owning module.** `smartmatch_providers/jwks.py` + `identity.py` own
verification; `api/dependencies.py` owns the conversion of a verified subject
into a `Principal`; `api/config.py` owns the issuer/audience settings.

**Interface it extends.** `TokenVerifier`, injected via
`registry.build_token_verifier` → `dependencies.get_token_verifier`
(dependencies.py:80) → `_subject_for_token` (:86) → `get_current_principal`
(:119).

**What new abstraction is justified: none — and this is the section where
building one would do real harm.** Two authentication mechanisms already exist:
the pilot password login against `pilot_credential`, owner-authorized
2026-09-04 and in use, and the dormant JWKS verifier. `main.py`'s own docstring
says the pilot login *"is not A1b, does not unblock it, and leaves the JWKS
verifier unwired."*

> **The no-third-path rule (wip-analysis §1.4).** Whichever mechanism lands
> second **must not become a third path.** `dependencies.get_current_principal`
> / `_subject_for_token` is the seam where they converge, and the property that
> makes A1b a swap rather than a rewrite is that *both* paths are
> "resolve a subject, then load the principal server-side" — with **no branch
> that skips the server-side load**. An "auth strategy" abstraction, a second
> dependency, or a parallel `get_current_principal_sso` would each create the
> third path by construction. Verify the existing shape first; then change only
> which verifier is injected.

**Boundary that must not be crossed.** Identity is never caller-supplied —
`scan_forbidden.py:61` (`mock[-_]login`, `caller[-_]selected[-_]role`,
a role assigned from the request body) and `:166` (`tenant_id`/`user_id`/`student_id`/
`professional_id` read from a payload), both CI-gated, MM-A01. A verified token
yields a *subject string* and nothing more; roles and tenancy come from
`user_account` + `membership` server-side (`domain-model.md` §3.2). Suspension
must stay evaluated locally and first, so an administratively suspended account
is denied without waiting for the IdP to revoke (`job_authz.py` docstring,
step 1). And the worker's OIDC task identity (`worker/identity.py`) is a
**different trust boundary** — do not unify the two verifiers.

**Migration requirements.** None. `user_account`, `membership`,
`resource_grant`, `pilot_credential`, `pilot_session` all exist. Whether pilot
login is retired after A1b lands is a product decision, not a schema one.

**Testing requirements.** A **parity test**: the same principal, authenticated
through each mechanism, must produce the same `Principal` and the same
`AccessDecision` on a fixed set of resources. That test is what proves the
convergence claim rather than asserting it. Plus the 52 existing JWKS unit
tests, plus a contract test against recorded JWKS responses covering key
rotation, wrong issuer, wrong audience and expiry — the four things that cannot
be exercised meaningfully before a real project exists (registry.py:265-270).

**Gating / OQ.** A1b. Issuer URL, audience, claim mapping and tenant mapping are
all *OUTSTANDING — EXTERNAL DEPENDENCY* in
`docs/decisions/a1b-idp-configuration-worksheet.md`; the blocker is the
institution (`docs/plans/open-questions/a1b-live-idp-deferred.md`). Engineering
cannot close it and should not simulate it.

---

## 3. Live route matrix

**Where it belongs.** A new `providers/routes.py` satisfying
`RouteMatrixProvider` — the one section here that adds a *file*, because the
adapter genuinely does not exist (`registry.py:196`: *"the live Routes adapter
is not implemented in the Foundation scaffold"*). It adds no new *seam*.

**Owning module.** `smartmatch_providers` owns the adapter;
`domain/factors/proximity.py` (697 L) owns what a distance means;
`domain/zcta_centroids.py` (1,894 L, regenerable via `make zcta-centroids`) owns
the current input.

**Interface it extends.** `RouteMatrixProvider`, via
`registry.build_route_matrix_provider`. `FixtureRouteMatrixProvider` already
satisfies it.

**What new abstraction is justified: none.** The port exists and the interim
carries a visible `"estimate quality: coarse"` label, never presented as a real
route time.

> **This one changes the measurement, not the fidelity.** Proximity today is
> **great-circle distance from ZCTA centroids**. Travel time is a *different
> measurement*, not a lower-resolution version of the same one
> (`wip-analysis.md` §1.2, handoff §4). The factor's meaning changes on the day
> the adapter lands, and **every `match_run` snapshot computed before that is
> not comparable to one computed after.** Runs across the change must not be
> compared, aggregated, trended, or shown side by side.

**Boundary that must not be crossed.** ADR-0011: a score carries provenance or
it is `null`; `null` never renders as `0`; no percentages
(`scan_forbidden.py:69`). A route lookup is provider IO and therefore may not
happen in a request handler (AP-04) — it belongs inside the `match-run.create`
execution, where a per-run call budget can be enforced. And the domain may not
import an HTTP client (contract 1): the adapter hands *values* to
`domain/factors/proximity.py`.

**Migration requirements — the one section with a real answer.** **None
needed: `scoring_mode` already exists (migration `0032`).** Before implementing,
decide that `scoring_mode` is where a run records *which measurement produced
it*, and use the existing column rather than adding one
(`wip-analysis.md` §1.2). The precedent for how to carry the discontinuity is
already in the tree: `factor_registry.py` keeps `REGISTRY_VERSION`
(`2.0.0-approved-oq-cba-004`), `SUPERSEDED_REGISTRY_VERSION`
(`1.1.1-approved-g1-m6j`), `SUPERSEDED_G1_MODEL` and `SUPERSEDED_SCORING_KEYS`,
so a superseded model is *retained and reproducible* rather than deleted, and
`docs/architecture/registry-supersession-record.md` records why (ADR-0016).
A measurement change is at least as consequential as a rulebook change and
should be recorded the same way: a new registry version, the old model retained,
and the mode on the row saying which produced it.

**Testing requirements.** A **contract test against a recorded transport** for
the Routes adapter (quota exhaustion, partial matrix, unroutable pair, timeout —
each mapping onto a declared factor outcome, and an unavailable route producing
`null` with provenance rather than a fabricated number). A **parity test**
asserting that a run pinned to the superseded mode still reproduces its stored
snapshot after the adapter lands — `SUPERSEDED_G1_MODEL` *reproduces rather than
re-derives*, and that property is what makes an old run explainable.

**Gating / OQ.** R1, open decision 6 (provider terms and per-run call budget).
**OQ-S2-006** asks the prior question: does the product need travel-time
proximity at all, given that it changes the measurement rather than the
fidelity? Answer that before building the adapter.

---

## 4. Live Cloud Tasks

**Where it belongs.** A GCP client behind the existing `TaskQueue` port. The
dispatcher does not change.

**Owning module.** `smartmatch_providers/tasks.py` owns the port;
`worker/dispatcher.py` (1,152 L) owns claiming and task creation and is
*deliberately the only component that creates tasks*; `worker/main.py` owns the
delivery boundary.

**Interface it extends.** `TaskQueue`, via `registry.build_task_queue`
(refusing today at `registry.py:243`: the live adapter *"requires a deployed
worker URL and service identity to target, neither of which exists yet"*).

**What new abstraction is justified: none.** Deterministic task names
(ADR-0007), lease + generation, the `SKIP LOCKED` CTE claim, 12 job states,
idempotency records and redrive are all built and covered by 44 tests including
crash windows. Handoff §3 lists the command path under "do not touch".

**Boundary that must not be crossed.** The delivery contract in
`worker/main.py`'s docstring, which is **the** thing to preserve:

- verify OIDC **before the body is read** — the body arrives as a raw `Request`
  precisely so an unauthenticated caller cannot be answered `422`;
- the delivery carries **identifiers only**; parameters come from `job.payload`,
  re-read from PostgreSQL (a payload the worker trusts is a payload anyone who
  reaches the queue can dictate);
- `200` on a duplicate delivery — at-least-once makes it the normal case;
- `503` on the dispatcher race — one transaction wide; acknowledging instead
  strands the job, because nothing else re-delivers it and `queued` has no route
  to `redrive_pending`;
- `401` / `403` (undifferentiated on purpose) / `501` when task identity is
  unconfigured / `500` only for PostgreSQL.

Also: the two callers stay apart — separate audiences, separate allowlists,
separate verifiers. Cloud Tasks may deliver and may not dispatch; Cloud
Scheduler the reverse. The scheduler verifier must never fall back to the task
audience.

**Migration requirements.** None.

**Testing requirements.** A **fixture-queue delivery contract test per
ADR-0021**: the contract above expressed as executable assertions against
`FixtureTaskQueue` and `worker/main.py`, so the docstring becomes a gate. Run
the same suite against the live adapter when it exists — the point of writing it
first is that the adapter is *measured* rather than improvised (R-01). Add a
**registry-map test** dependency check too: a live queue changes nothing about
which command types exist, and AP-05 must still pass unchanged.

**Gating / OQ.** F5, and the fact that the live client needs a deployed worker
URL and service identity. `local_tasks.py` is not a lesser version of this — it
is the appliance's queue and stays (ADR-0022).

---

## 5. GCP deployment (F5)

**Where it belongs.** `infra/terraform/` — 7 modules, 4 environments, and
**nothing in the application changes**.

**Owning module.** Terraform only. No Python module gains a branch for GCP.

**Interface it extends.** None. This is the one capability with no application
seam, which is exactly why it must not acquire one.

**What new abstraction is justified: none.** There is no "cloud provider
abstraction" to write. The application's environmental variability is already
expressed as: `Edition`, injected providers, and configuration that refuses to
boot half-set. That is the abstraction.

**Boundary that must not be crossed.** `tools/env_isolation_check.py` — Terraform
environments share no identifier and **nothing is applyable** (v1.1 §3.2–3.3).
One root module exists (`envs/classroom/root.tf`) so `terraform validate` can run
over a whole environment; that is the ceiling. Non-negotiable 11. And ADR-0022
records the topology honestly: the Docker Compose appliance on a VM is what CI
builds, probes and deploys (`deploy.yml`, `docker-compose.vm.yml`,
`smartmatch.sh`) and is therefore the **current production topology**; the
Terraform is a forward design record. Without that statement the appliance reads
as interim scaffolding beneath an architecture that does not exist (R-18).

**Migration requirements.** None. Deploy-time migration behaviour is answered
for the appliance and unanswered for GCP; ADR-0022 should say so rather than
imply parity.

**Testing requirements.** `env_isolation_check.py` and `terraform validate`
continue to run; neither is weakened (non-negotiable 13). When GCP becomes real,
rollback, log destination and deploy-time migration each need a recorded answer
*before* an apply, because those are the three the appliance answers and the
Terraform does not.

**Gating / OQ.** F5, `docs/plans/open-questions/f5-deploy-deferred.md`. Blocked
on a decision to deploy, not on engineering. Do not build it speculatively
(handoff §7).

---

## 6. Calendar API (G5)

**Where it belongs.** Not yet anywhere, and the absence is enforced.

**Owning module.** Today: `domain/calendar_invite.py` and `domain/ics.py` (pure,
standard-library only) plus `routers/calendar.py` (a database read and a
`Response`). A future Google Calendar write would need a provider port and a
worker handler — not a router.

**Interface it extends.** If it is ever built: a new port in
`smartmatch_providers` alongside `EmailProvider`, plus a command type executed
in the worker. Never a synchronous route.

**What new abstraction is justified: none today, and the substitute is complete
rather than degraded.** An `.ics` file is what a person imports into *whichever*
calendar they use, and it needs authorization from nobody because the person
performs the import. That is not a fallback; for many users it is the better
answer.

**Boundary that must not be crossed.** `tests/unit/test_calendar_invite_wiring.py`
asserts the **absence** of `googleapiclient`, `google_auth_oauthlib`,
`auth/calendar`, `calendar.events`, `GOOGLE_CALENDAR` and `CALENDAR_CREDENTIALS`
**by name**, so acquiring the capability fails a test that cites the gate rather
than passing as a diff. This is the model implementation of "capability by
absence" (AP-11) and must be extended, never deleted, when G5 opens. The
second boundary is F-003's lesson: the legacy generator turned an unparsed
"Every Tuesday" into a confident invite thirty days out. Where a fact is
missing, the route returns a `409` naming which fact and issues no bytes. *A
refusal costs somebody a download. A fabrication costs somebody a Tuesday.*

**Migration requirements.** Unknown until the capability is scoped. Recorded as
UNKNOWN, not as none.

**Testing requirements.** Extend the absence test rather than remove it — when
G5 opens, it should assert that the calendar client appears **only** under
`smartmatch_providers/` and never under `services/api/`. Plus a contract test
against recorded Google responses for consent revocation and token expiry, which
are the two states that decide what happens to entries already written.

**Gating / OQ.** G5 stays deferred to public-release planning.
`docs/plans/open-questions/calendar-deferred.md` OQ-001 is the blocker: under
whose OAuth client, on which scopes, with whose consent screen does SmartMatch
write into a person's calendar — and what happens to existing entries when a
student leaves the institution. Those are institutional commitments, not
implementation choices.

---

## 7. Additional scoring factors

**Where it belongs.** `domain/factors/` for the computation,
`domain/factor_registry.py` for the declaration.

**Owning module.** `smartmatch_domain`. A factor is a pure function of values;
if it needs IO, the IO belongs to a provider and the *result* is passed in — as
proximity does today with ZCTA centroids and would do tomorrow with a route
matrix.

**Interface it extends.** The **factor registry** — `ScoringModel`,
`registry_version`, `scoring_keys`, `_keys_in_registry_order`, and the
`assert_registry_approved()` gate that **fails closed** unless
`REGISTRY_STATUS == "approved"` (factor_registry.py:149, 553).

**What new abstraction is justified: none.** A "plugin" or "factor provider"
mechanism would defeat the registry's whole purpose, which is that the set of
factors is *closed, versioned and approved by a named person*
(`REGISTRY_APPROVER`, :154). A factor that can be added dynamically is a factor
nobody approved.

**Boundary that must not be crossed.** ADR-0011 — provenance or `null`, never a
percentage, never a fabricated literal (`scan_forbidden.py:69`, e2e 11 and 12,
plus the frontend rendering rule). Contract 1 — the factor may not import a
framework, storage, provider or `os`. And the supersession discipline: retiring
or reweighting a factor bumps `REGISTRY_VERSION`, moves the old model to a
`SUPERSEDED_*` constant so it still *reproduces* rather than re-derives, and is
recorded in `registry-supersession-record.md` (ADR-0016). `SUPERSEDED_SCORING_KEYS`
currently holds `topic_relevance` and `travel_burden` — that is what the pattern
looks like in practice.

**Migration requirements.** None. `match_run` snapshots carry the version; new
factors do not add columns.

**Testing requirements.** A **registry-map test** in the same spirit as AP-05:
every key in a `ScoringModel` has a factor implementation, and every factor
implementation is named by some model — current or superseded. Plus a **parity
test** that a stored snapshot from a superseded version still reproduces
identically after the new factor lands. Plus the ADR-0011 assertions, unchanged.

**Gating / OQ.** G1 is **closed** (`REGISTRY_STATUS = "approved"`, approver
named). New factors need the same approval route, not a new one.

---

## 8. Additional command types

**Where it belongs.** A router submits; the worker executes. Both halves already
have their place, and the choice between them is the only real decision.

**Owning module.** The submitting router calls
`smartmatch_api.commands.submit_command`. The executor goes in
`worker/handlers.py::default_registry()` **if it takes no collaborators**, or is
composed at `worker/main.py`'s root **if it does** — the rule is stated in the
tree: *"a registry function that takes no arguments cannot supply them"*, and
`handlers` importing `outreach`/`paid_extraction` to reach them *"would make a
cycle out of a dependency that is genuinely one-way"* (worker/main.py:451-459).

**Interface it extends.** `submit_command` → `CommandRegistry`.

**What new abstraction is justified: none.** The registry is a dictionary and
that is the design — *"A command type either has a handler or it does not, and
the difference is visible in one dictionary rather than scattered across `if`
branches."* A miss is a **terminal refusal**, and the docstring names the
alternative (log a warning, return success) as "the single worst outcome
available here", because the job would report `succeeded` while nothing had been
done.

**Boundary that must not be crossed.** AP-04 / `scan_forbidden.py:136` — the
router records intent and returns a job id; it performs no provider IO. AP-11 —
a gated-off capability registers **no handler**; *"a handler added ahead of its
gate is a handler someone will trigger."* And a handler reads its parameters
from `job.payload`, never from the delivery, and never commits the executor's
session.

**Migration requirements.** None. `job`, `outbox_record`, `idempotency_record`,
`job_event`, `redrive_record` are generic.

**Testing requirements.** The **registry-map test** (AP-05, ADR-0023) must be
extended by the same change that adds the command type — that is the point of
making it a build failure. Note the two things it must model correctly or it
will report false gaps:

- **Root-composed handlers count as registered.** `outreach.send` reaches the
  worker via `with_outreach_send` at `worker/main.py:468-489`, unconditionally
  when `registry_is_ours` (the guard at `:468`, the call at `:470`);
  `extraction.paid_pages` via `with_paid_extraction` at `:491-492`, only when spend ceilings are configured. Neither appears in
  `default_registry()`.
- **Idempotency-scope names are not command types.** `speaker_contact.create`
  (`routers/cba_contacts.py:302,1097`), `job.redrive` and `job.abandon`
  (`routers/redrive.py:388,527,589`) reserve an idempotency key and create no
  job and no outbox row, so **no handler is expected**. Likewise `routers/review.py:40`
  and `routers/speaker_requests.py:25` mention `submit_command` in prose and are
  synchronous by design.

**U1, resolved in tree (OBSERVED, 2026-09-08).** Four routers submit; three
command types reach the worker; every one has an executor. Stage 1's "eight
submitting routers" counted docstring mentions and idempotency-only uses — this
is a recorded Stage 1 disagreement. R-04 stands in a sharper form: **the map is
complete today, nothing asserts it, and the root-composed handlers are invisible
to a reader of `default_registry()`.**

| Command type | Submitting router(s) | Executor | Registered where |
|---|---|---|---|
| `import.create` | `routers/imports.py:293` | `handle_import_create` | `default_registry()` |
| `match-run.create` | `routers/match_runs.py:947` | `handle_match_run_create` | `default_registry()` |
| `outreach.send` | `routers/outreach.py:679`, `routers/cba_invitations.py:1112` | `build_outreach_send_handler` | **root**, `worker/main.py:468-489` |
| `test.noop` | none over HTTP | `handle_noop` | `default_registry()` |
| `extraction.paid_pages` | none over HTTP | `build_paid_extraction_handler` | **root**, conditionally, `worker/main.py:491` |

**Gating / OQ.** Whatever gate the capability itself waits on. The registry does
not become the gate.

---

## 9. Retention / archival

**Where it belongs.** A sweep in the scheduled dispatch pass, plus per-table
retention recorded as a decision.

**Owning module.** `smartmatch_persistence` for the delete/archive query,
`worker/dispatcher.py`'s pass for the schedule. The precedent is exact:
`sweep_expired_leases` is already called from the pass, and `DispatchPassResponse`
already reports counters (`sweep_failed`, `timed_out`).

**Interface it extends.** The **scheduled dispatch pass**. Not a new scheduler,
not a cron container, not a separate job type.

**What new abstraction is justified: none.** A retention framework for five
tables would be more machinery than the thing it manages.

**Boundary that must not be crossed.** ADR-0011's reproducibility: a `match_run`
snapshot is *"an immutable snapshot of a decision"* and the point of retaining
`SUPERSEDED_G1_MODEL` is that an old run can still be explained. A retention
policy that deletes snapshots deletes the ability to answer "why did this
system say that", which is the product's defining commitment. `point_ledger_entry`
is likewise **not** on this list — balance is `fold_balance(entries)`, derived
and never stored, and the handoff's anti-goals explicitly forbid a snapshot
scheme for the ledger. `contact_channel_transition` is the *log* of consent
changes and is evidence of a privacy decision. Treat `job_event`,
`delivery_event` and `pilot_login_attempt` as the ones where a period is
plausibly short.

**Migration requirements. Yes — the only capability here that needs schema
work.** An archive table or a partition per retained table, one transaction per
migration (ADR-0009), and the parity test updated. Do not implement before the
period is decided; a retention job with a guessed period is worse than none.

**Testing requirements.** An integration test per table asserting that rows
inside the window survive and rows outside it are archived (not silently
dropped), plus a **contract test** that `DispatchPassResponse` reports what was
swept — same shape as the M1 spend-sweeper reporting, so the pass stays
self-describing.

**Gating / OQ.** **OQ-S2-003** — the retention period per append-only table:
`job_event`, `delivery_event`, `contact_channel_transition`,
`pilot_login_attempt`, `match_run` snapshots. R-13's own remediation is
*"Record the intended retention per table as a decision. Implement nothing
yet."* At pilot volume the risk is P3; the decision is still the prerequisite.

---

## 10. A second client (mobile, or another SPA)

**Where it belongs.** `clients/typescript` — which does not exist yet, and that
is the whole story.

**Owning module.** The generated client, produced from
`contracts/openapi/smartmatch.json` (57 paths, 120 schemas, already CI-gated for
freshness) by **`openapi-typescript`, pinned by exact version** — types only, no
runtime shipped to the browser (ADR-0020, owner decision 8 September 2026). A
second client importing the same declarations is the point; a second *generator*
would recreate the drift at the tool layer.

**Interface it extends.** The **generated client** and the OpenAPI contract.
Nothing on the server changes for a second consumer: the contract is the
interface, and it is already published.

**What new abstraction is justified: none — and a BFF is the specific thing to
refuse.** A backend-for-frontend layer would create a second contract to keep
fresh and a second place for types to drift, which is the exact failure R-02
describes at n=1. The correct move is the opposite: reduce to *one* generated
client that both consumers import.

**Boundary that must not be crossed.** AP-07 — *the contract is consumed, never
transcribed.* No hand-written type for a `/v1` response in any client. No new
`/api/*` path: the 24 that exist are served by nothing
(`test_16_the_portal_pages_have_no_backend_in_this_repository`) and a second
client must not learn them. And the OpenAPI `description` must stop claiming a
generated client before a second consumer reads it — D2 is currently a false
statement published *inside the contract itself*.

**Migration requirements.** None.

**Testing requirements.** The **drift gate** — already listed as deferred at the
bottom of `verify.yml` as *"generated TypeScript client drift check (needs
clients/)"*. Regenerate in CI and run `git diff --exit-code clients/typescript`,
so a backend field rename fails the build instead of reaching a user as a runtime
`undefined`. Plus the first migrated page as the executable pattern —
`src/lib/session.ts` with `src/app/hooks/useSession.tsx`, the `GET /v1/me` path
(ADR-0020); **do not migrate 48 files in one change** (Stage 1 reported 49; recounted 2026-09-08) (R-02's remediation,
`wip-analysis.md` §3.1). A second client inherits that pattern: it resolves
identity through the generated principal types rather than transcribing them.

**Gating / OQ.** Blocked entirely on M3. Until `clients/typescript` exists,
a second client would be a second hand-written transcription — the failure the
first one already demonstrates at 4,238 lines.

---

## 11. What this document refuses

Recorded so that a future agent does not have to re-derive the refusals, and so
that proposing one requires arguing against a citation rather than against a
preference.

| Proposal | Refused because |
|---|---|
| An "auth strategy" abstraction for A1b | Creates the third auth path by construction (wip-analysis §1.4) |
| A mail-service layer above `EmailProvider` | Breaks "one function answers when this system emails a person" (worker/outreach.py) |
| A cloud-provider abstraction for F5 | `Edition` + injected providers + boot-refusing config already is one |
| A dynamic factor-plugin mechanism | A factor that can be added dynamically is a factor nobody approved (factor_registry `REGISTRY_APPROVER`) |
| A retention framework | More machinery than five tables warrant (R-13 is P3) |
| A backend-for-frontend for a second client | A second contract to keep fresh, which is R-02 again |
| Splitting `schema.py` to make room for new tables | Ownership first (R-20, AP-03, ADR-0019) |
| An event bus / CQRS / broker / service split for any of the above | Nothing in the repository exerts that pressure; PostgreSQL-as-coordinator is recorded with adoption triggers (ADR-0005, handoff §7) |
| Comparing match runs across the route-matrix change | The measurement changed, not the fidelity (§3; ADR-0016's `REGISTRY_VERSION` precedent) |
