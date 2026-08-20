# Remaining Foundation and R1 work

In dependency order. Each item names what blocks it and who owns the block, so
sequencing is visible rather than rediscovered.

---

## Blocked on decisions outside engineering

These cannot be started by engineering alone. They are listed first because
several downstream items wait on them, and the calendar cost of a late decision
is larger than the work itself.

| # | Item | Blocked on | Owner | Blocks |
|---|---|---|---|---|
| D1 | Approve the factor registry contents and golden case set | Gate G1 | Program owner | All matching work (R1) |
| D2 | Confirm ELI formula parameters (decay half-life, window, caps) | Open decision 2 | Program owner | R1 tuning; not R1 delivery |
| D3 | Route-matrix provider terms and per-run call budget | Open decision 6 | Procurement + engineering | `travel_burden` factor |
| D4 | Domain registration and DNS control | Open decision 8 | Institutional IT | All mail work (R4) |
| D5 | Retention periods per evidence table | Open decision 5 | Privacy / legal / records | R2 evidence tables |

**D1 is the critical path.** Everything in "Matching" below waits on it, and
matching is the product's reason for existing.

---

## Foundation completion

Work that finishes the scaffold itself. None is blocked on a decision.

| # | Item | Depends on | Notes |
|---|---|---|---|
| ~~F1~~ | ~~Pin dependencies to a lock file with hashes~~ | — | **Done.** `requirements/*.txt`, hash-verified, with a CI drift gate. Resolves S-003. |
| ~~F2a~~ | ~~Dependency vulnerability scanning~~ | F1 | **Done.** `pip-audit --strict` against the lock. Resolves S-004. |
| F2b | License-policy check and SBOM generation | F1 | The remainder of F2. Not blocking. |
| ~~F3~~ | ~~Independent review of the four `ported_unverified` manifest entries~~ | — | **Done, and it did not approve most of them.** MM-001 → `verified` with findings. MM-003, MM-004, MM-005 remain `ported_unverified`: the review found the manifest's own descriptions inaccurate. See `docs/migration/port-verification.md` and F9 below. |
| F9 | Act on the port-verification findings (F-1..F-27) | F3 | **The review's real output.** Three entries were rejected not because the ported code is bad — it is better than the legacy in every case — but because the manifest describes it wrongly: MM-005 claims a decline vocabulary was *retained* when it was replaced, and claims a legacy substring-matching defect that does not reproduce; MM-004 cites characterization tests that do not exist. Remedy is a manifest correction plus a small number of code fixes, then re-review. One genuine code defect: MM-003's Stage A cap boundary is set by 4-decimal-place rounding. |
| ~~F4~~ | ~~Containerize API and worker; add image build to CI~~ | F1 | **Done.** `Dockerfile.api`, `Dockerfile.worker`, `.dockerignore`, `.github/workflows/build.yml`, `docs/operations/containers.md`. Images build, run non-root, serve health, and stop on SIGTERM; CI asserts each on the built artifact. Still no deployment and no registry. |
| F5 | Flesh out Terraform environment skeletons | F4 | Still no deployment — configuration only, with the CI assertion that environments share no identifiers |
| ~~F6~~ | ~~Add ADRs for decisions made during scaffolding~~ | — | **Done.** ADR-0004 (hand-written schema + `LTree`), 0005 (outbox CTE claim), 0006 (fixed-window limiter), 0007 (deterministic task names). |
| ~~F7~~ | ~~Widen the schema drift test beyond column names~~ | — | **Done.** `tests/integration/test_schema_matches_migration.py` now compares, per table and in both directions: foreign key constrained columns, referred table/columns, and delete action (`None` normalized to `NO ACTION`); nullability; column types compiled against the PostgreSQL dialect, with the two `ltree` columns (`org_unit.path`, `membership.granted_path`) handled by a documented `information_schema` exception rather than swallowed; and primary key, unique, and CHECK constraint **names** as sets, with unique constraints additionally compared by columns. Because a symmetric comparison can't catch a constraint deleted from both sides in the same change, four load-bearing constraints are also asserted absolutely against the database: `uq_job_event_sequence`, `uq_outbox_task_name`, `uq_idempotency_scope`, `pk_rate_limit_counter`. The tenant-anchoring check (`test_every_tenant_scoped_table_is_anchored_by_a_composite_key`) now enumerates tables from the live database rather than from `schema.py` — an earlier draft derived the list from the mirror, which let a simplified composite key silently shrink the very list meant to catch it — and requires a composite key's `tenant_id` to correspond *positionally* to the parent's `tenant_id`, not merely appear somewhere in the same key. `schema.py` gained the seven `ondelete` values, the named primary keys, and the CHECK constraint names; ADR-0004 has an amendment recording the widened coverage. New `tests/integration/test_job_states_match_domain.py` holds `ck_job_status`'s expression to `smartmatch_domain.jobs.JobState`, the one CHECK constraint whose text is actually read rather than only named. **What it still does not cover:** six of the eight CHECK constraints — `ck_membership_valid_window`, `ck_resource_grant_effect`, `ck_outbox_status`, `ck_redrive_authorship_complete`, `ck_budget_non_negative`, `ck_rate_limit_count_non_negative` — are asserted by name only, with no test attempting the forbidden write (see F10). Server default *expressions* and index *sets* remain deliberately unchecked (presence-only, and two named GiST indexes respectively), per the design recorded in `docs/plans/defect-remediation.md` §6.3. |
| F8 | Add an ADR index | — | ADR-0004..0008 are discoverable only by directory listing. |
| F10 | Add behavioural tests for the six name-only CHECK constraints | F7 | `ck_membership_valid_window`, `ck_resource_grant_effect`, `ck_outbox_status`, `ck_redrive_authorship_complete`, `ck_budget_non_negative`, `ck_rate_limit_count_non_negative` are asserted by name only. Only `ck_job_status` (`test_tenant_isolation.py::test_job_status_check_rejects_an_unknown_state`) and `ck_budget_ceiling_non_negative` (`::test_budget_ceiling_cannot_go_negative`) are exercised by a test that attempts the forbidden write. A constraint re-added under the same name with an inverted expression, or as `NOT VALID`, keeps its name and stays green today. |
| F11 | Decide `transaction_per_migration` before a `0004` exists | — | `db/migrations/env.py` wraps every pending revision in one transaction and does not set `transaction_per_migration=True`, so a lock taken by one migration (`0003`'s `ACCESS EXCLUSIVE` on `user_account`) is held until the whole `alembic upgrade` run commits, not until that migration finishes. Harmless while `0003` is head; stops being harmless the moment a `0004` exists. Setting `transaction_per_migration=True` changes rollback semantics for every migration in the repository — a failed multi-step upgrade would then leave earlier revisions committed instead of rolling the run back as a unit — so `0003`'s own docstring flags this as a decision to make deliberately, not a drive-by fix. |
| F12 | Contract-phase: drop `uq_user_account_tenant_subject` | Release fully promoted | `uq_user_account_external_subject` (migration `0003`) makes it strictly redundant — a globally unique subject is unique per tenant too — but dropping it is contract-phase work under v1.1 §4.2's expand/migrate/contract discipline, and every migration in this repository is expand-phase only. See ADR-0008 and `0003`'s docstring. |

---

## R1 — Matching foundation

### Blocked on D1

| # | Item | Depends on | Notes |
|---|---|---|---|
| M1 | Flip `REGISTRY_STATUS` to `approved` in a reviewed commit | D1 | Also lands the golden case set; `test_registry_is_not_yet_approved` changes here, deliberately |
| M2 | Implement `topic_relevance` | M1 | Embedding models may contribute feature inputs only with provenance and golden/shadow tests |
| M3 | Implement `role_fit` | M1 | The legacy's alias/fuzzy approach is a reasonable starting point; it needs golden cases, not a port |
| M4 | Implement `travel_burden` over the route matrix | M1, D3 | Interim: straight-line distance labeled "estimate quality: coarse". Never fabricate mileage. |
| M5 | Implement `repeat_penalty` | M1 | Feeds control-center view V6 (repeatedly selected vs underutilized) |
| M6 | Stage A eligibility filter | M1 | The four eligibility factors are declared in the registry and unimplemented |
| M7 | Stage B CP-SAT portfolio optimization | M2–M6 | OR-Tools. The LLM never solves the schedule. |
| M8 | Immutable `match_run` persistence with full version pinning | M7 | Input snapshot, eligibility policy, registry, weight set, optimizer version, route-estimate timestamp |
| M9 | Per-factor and per-penalty explanations | M7, M8 | Must separately show the ELI hard cap and soft penalty (v1.1 §1.3) |
| M10 | Scenario comparison | M8 | Six objectives per v1.1 §5.3 |

### Not blocked on D1

| # | Item | Depends on | Notes |
|---|---|---|---|
| ~~J1~~ | ~~Outbox dispatcher~~ | — | **Done.** Lease/claim with `FOR UPDATE SKIP LOCKED`, deterministic task names, dispatch evidence, lag metric, crash recovery via lease expiry. |
| ~~J2~~ | ~~Command resource pattern with idempotency and 202 + job id~~ | J1 | **Done.** `submit_command` commits reservation, quota, job, and outbox in one transaction. `/imports` is the first resource. |
| ~~J3~~ | ~~SSE with `Last-Event-ID`~~ | J1 | **Done.** Backed by `job_event.sequence`; polling reads the same rows. |
| ~~J5~~ | ~~The two named integration scenarios~~ | J1 | **Done.** `tests/integration/test_outbox_dispatcher.py`. |
| ~~J4~~ | ~~Re-drive command with authorization and audit~~ | J1 | **Done.** `POST /v1/jobs/{id}/redrive` and `/abandon` (`services/api/smartmatch_api/routers/redrive.py`), role-gated (`admin`/`coordinator`), idempotent, and audited with actor + reason in `redrive_record`. The task-name collision ADR-0007 recorded as an unsolved constraint is closed by `redrive_generation` — see the ADR's amendment. Authorization shares the same gap as job reads (S-006/A5): the `job` table has no owning unit, so a coordinator in one department can re-drive another department's job. |
| ~~J6~~ | ~~Real OIDC task-identity verification in the worker~~ | J1 | **Done, with an honest, named gap.** `services/worker/smartmatch_worker/identity.py` checks signature, issuer, audience, expiry, and a service-account allowlist. The signature primitive is an injected `SignatureVerifier` port; `requirements/runtime.txt` carries no asymmetric-crypto library, so the shipped default backend is `None` and the worker refuses every request until one is supplied — the same closed door the 501 stub gave. See S-001. |
| ~~J7~~ | ~~Worker command handlers, and the `running -> succeeded/partial/failed` transitions~~ | J1, J6 | **Done.** `services/worker/smartmatch_worker/{execution,handlers}.py`. `JobRepository.claim` (`dispatched -> running`, conditional) guards against Cloud Tasks' at-least-once delivery; a losing delivery is acknowledged and executes nothing, and a delivery that races the dispatcher's own `queued -> dispatched` commit gets `503` so the queue retries instead of the job being silently stranded. Two handlers ship: `test.noop` (a path check, not reachable from the API) and `import.create`, which **always fails** as `failed_policy` — see J10. |
| J8 | Dispatcher scheduling (Cloud Scheduler → dispatcher endpoint) and its alert | J1, F4 | `run_once` and `lag` exist; nothing calls them on a timer. |
| J9 | Lease + sweeper for a job stuck in `running` | J7 | Named but not closed in `execution.py`: a worker that dies after `claim` succeeds and before the terminal transition commits leaves the job `running` with no worker behind it. Recovering it needs `job.lease_expires_at` (an expand-phase migration) and a scheduled sweep — neither exists. Today such a job stays `running` until someone notices. |
| J10 | Durable command payload (`job.payload`) | J7 | `import.create` is the only real command wired end-to-end, and it cannot execute: `submit_command` uses the request body only for the idempotency fingerprint, and neither `job` nor `outbox_record` has a payload column. Every import that reaches the worker fails immediately with `failed_policy` and the reason `command_not_executable`. Needs a `job.payload` column written inside the same transaction as the job and outbox rows. |
| ~~J11~~ | ~~A 409 from re-drive or abandon poisons its idempotency key~~ | J4 | **Done.** Both handlers wrap everything the command writes in a `SAVEPOINT` (`session.begin_nested()` in `routers/redrive.py`), with `enforce_rate_limit` deliberately *outside* it. A refusal rolls the savepoint back — reservation, parking, state change, audit record, outbox row — and commits the outer transaction, so the quota still sticks (S-008) and no key is consumed. `_reserve`'s internal `session.commit()` is removed: `Session.commit()` with an open savepoint commits the savepoint's work too, so leaving it would have made permanent the very reservation the fix exists to discard. The contract is now stated in the module docstring — **a key names accepted work; a refused command consumes quota and no key** — so a retry after a 409 re-runs the attempt and is refused again, rather than replaying either the refusal or a success that never happened. That matters because the refused states are not permanent: a `running` job later fails and becomes re-drivable, and the same key must then produce a real re-drive. The symptom, recorded because this row first described it wrongly: **`running`** has no declared path to `ABANDONED`, so a first abandon is correctly refused and the retry answered `200 {"status": "abandoned"}` while the worker was still executing the job, with no `redrive_record` — a caller told a job was closed permanently while it was in fact running. `failed_provider`, which this row originally named, cannot produce it: `FAILED_PROVIDER -> REDRIVE_PENDING` is declared, so the first abandon succeeds and there is no 409 to poison. Covered by `test_a_refused_redrive_does_not_consume_its_idempotency_key`, `test_a_refused_abandon_does_not_report_the_job_abandoned`, and `test_a_redrive_that_loses_the_parking_race_leaves_no_stray_audit_record` — the last reaching `RedriveConflictError` with two genuinely concurrent transactions, and the reason this is a savepoint rather than a targeted delete of the reservation: the parking step backfills a `redrive_record` before the compare-and-set can lose, and a delete aimed at the reservation would have committed that stray record. Plan: `docs/plans/transaction-boundary-defects.md` §2. |
| J12 | A failed failure-write strands an outbox row at the last attempt | J1 | **Found by the Wave C audit, in Wave B code; verified against `_claimable_predicate`.** `_record_failure_safely` (`worker/dispatcher.py`) swallows an exception from writing the failure evidence, on the reasoning that the row is left as the claim left it and "the lease expires and it is retried". That holds on every attempt but the last. At `dispatch_attempts == MAX_DISPATCH_ATTEMPTS` the row stays `leased` with no attempts remaining, and `_claimable_predicate` requires attempts remaining — so it is never reclaimed, never marked `failed`, and never counted by the lag metric, and its job stays `queued` indefinitely. This is the same stranding the `queued -> failed_provider` parking added in `2564d33` exists to prevent, reachable by a different route. |
| ~~J13~~ | ~~Make the dispatcher's claim order the FIFO its contract promises~~ | — | **Done** (`bfb1a0e`). A dispatcher test failed about one run in thirty, and only at module scope. The cause was not the test: `claim_batch` picks the oldest rows in a CTE ordered by `created_at`, then returns them from `UPDATE ... RETURNING`, whose output order SQL does not define. `EXPLAIN` shows the CTE's sort feeding a hash join whose outer side is a sequential scan, so rows arrived in *heap* order — indistinguishable from creation order until an update rewrites an older row's tuple behind a newer one, which is what a busy outbox does. So the FIFO order named in the method's docstring, measured against by `oldest_pending_age`, and assumed by ADR-0005 was never guaranteed. The claimed rows are now sorted by `(created_at, id)` in Python, `id` breaking ties so the order is total. Correctness never depended on it — rows dispatch independently, so a wrong order cost latency on the oldest row, not safety — but three artifacts already documented the guarantee, and relaxing the test to match the code would have left all three quietly false. The test had its own defect: it injected failure on the second *call* rather than on a named job, silently turning a test about a database blip into an assertion about claim order. `_claimable_predicate` is untouched, so the claim query and the lag metric still share one definition (ADR-0005). Verified across 132 module runs with no failures, against three failures in 75 before. |
| J14 | A replayed re-drive reports the wrong generation | J11 | **Found by the J11 audit; reproduced through the HTTP surface, and it pre-dates the J11 fix (identical at `bfb1a0e`).** The replay branch answers with `_redrive.current_generation(...)`, which returns the job's *latest* dispatch rather than the one the replayed key created. Verbatim: K1 re-drives → `generation: 1`; the job is dispatched and fails again; K2 re-drives → `generation: 2`; a retry of **K1** answers `{"replayed": true, "generation": 2}`. **Severity: Medium.** Three reasons, and the third is why it is not Low. (1) It is wrong in the one field that exists to disambiguate dispatches, and it is wrong silently — a client reconciling generations against the event stream reads the replay as belonging to a dispatch that key never created, and nothing else in the response contradicts it. (2) The sequence is ordinary, not adversarial: two re-drives of the same job under different keys and a client library retrying the first. (3) **The comment directly above the call claims this class of error was already fixed.** It fixed a neighbouring one — the generation defaulting to `0` — and now reads as though the field is trustworthy, so the next reader is actively steered away. It is not Higher because the work genuinely was accepted and did run: unlike J11 nothing false is claimed about *whether* the command happened, only about *which dispatch* it names. **Not a one-liner: `idempotency_record` stores no generation.** Answering correctly means persisting one at reserve time, which is a schema change and a migration — the same constraint that made "replay the 409" unimplementable in `transaction-boundary-defects.md` §2.5. Either do that, or drop the field from the replay response and say why; do not start it expecting to fix the call site. |
| J15 | An unexpected exception refunds the rate-limit quota | J11 | **Found by the J11 audit; reproduced, and it pre-dates the J11 fix (identical at `bfb1a0e`).** For any exception outside the three-type `except` tuple in `redrive_job` — reproduced by making `_redrive.redrive` raise `RuntimeError` — the savepoint stays open, `session.commit()` never runs, and `get_session`'s unconditional `finally: session.rollback()` discards the rate-limit increment along with everything else. Measured: quota `0` before, `0` after. `abandon_job` has the identical shape. **This reopens S-008 through a repeatable 500**: a caller who can reliably provoke an unhandled error on this route pays no quota for it, which is exactly the traffic the limiter exists to bound, and re-drive is rate-limited tightly precisely because it is a privileged decision. **Severity: Medium on merit, Low exposure today.** Nothing is deployed, so the only caller who can reach it is a test — this is a test-environment concern now and a live one the day the API serves traffic, which is the argument for closing it before first deploy rather than after. It is Medium and not High because it needs an unhandled 500, which is itself a defect that would be fixed on its own terms; the quota refund is a second-order consequence, not the primary failure. **Newly cheap to fix, and that is the point of filing it now.** Before J11 the exit path could not simply commit: the command's writes shared the transaction, so committing on the way out risked persisting a half-written re-drive — the hole was real and the obvious fix was unsafe. The savepoint now isolates everything the command wrote, so a `command.rollback()` plus `session.commit()` in a broad `except`/re-raise persists the quota and nothing else. What needs deciding is scope, not mechanism: `enforce_rate_limit` is shared by every command route, and only these two are savepointed, so fixing it here leaves the same hole open in `commands.py` — see `transaction-boundary-defects.md` §2.3(c) and §9 question 1, which record moving quota to its own transaction as the right long-term shape. |
| J16 | Cheap refusals bypass the rate limiter | A3 | **Found by the J11 audit; pre-existing ordering, measured through the HTTP surface.** `enforce_rate_limit` runs after `_load_job_or_404`, `_authorize_redrive`, and the header and body validators, so a `403`, `404` or `400` moves `rate_limit_counter` by zero — 25 consecutive refusals of each kind, no movement. That is the same S-008 shape the J11 savepoint exists to close on the `409` paths, reached by the three refusals that are *cheapest* to produce in bulk. Not fixed with J11 because the remedy is not a reordering anyone should make silently: charging quota before authorizing decides that an authenticated caller pays for requests they were never allowed to make, and charging before the job load decides they pay for ids that do not exist — defensible, and a decision about who bears the cost of a rejected request rather than a bug fix. Whatever is decided applies to every command route, not only these two (see J15). The `redrive.py` module docstring states the narrow, true version of the contract and points here. |
| ~~A1a~~ | ~~Token verification adapter and principal resolution~~ | — | **Done.** Interface, fixture, and database-backed principal lookup. |
| A1b | Live Google Identity Platform verifier (JWKS, audience, rotation) | — | The fixture accepts only registered tokens, so it cannot be mistaken for permissive auth. |
| ~~A1c~~ | ~~Make `external_subject` globally unique~~ | A1a | **Done.** Migration `0003` adds `uq_user_account_external_subject` and refuses to run against duplicate subjects, naming them and their count, rather than deduplicating or picking a winner. Fixes the defect where `PrincipalRepository.load_by_subject` filtered on `external_subject` alone and called `.one_or_none()` against a constraint that was only `(tenant_id, external_subject)` — one identity-provider subject with accounts in two tenants matched two rows, raised `MultipleResultsFound`, and 500'd every authenticated request by that person. `uq_user_account_tenant_subject` is kept, now redundant, as contract-phase work (F12). New `tests/integration/test_principal_identity.py`; integration subjects now route through `conftest.unique_subject` for a per-session token. See ADR-0008. **This item carried no backlog number before now** — it was tracked only in `docs/plans/orchestrator-handoff.md`'s Wave C section. |
| ~~A2~~ | ~~Wire `smartmatch_authz` into request handling~~ | A1a | **Done.** Applied in handlers after the resource is loaded, not as a blanket dependency. |
| ~~A3~~ | ~~PostgreSQL transactional rate limiter~~ | A1a | **Done.** Shipped with the first command endpoint, as S-002 required. |
| A4 | Authorization policy matrix with negative tests per operation | A2 | v1.1 §2.1 names this as a workstream. One operation is covered; the matrix is not. Includes deciding which roles a `resource_grant` conveys — currently a bare grant cannot satisfy a role-gated operation (fail-closed, see S-007). |
| A5 | Add `job.owning_unit_id` so job reads can be unit-scoped | A2 | Expand-phase migration. Until then a coordinator in one department can read (S-006), re-drive, or abandon (added by J4) another department's job. |

---

## R1 — Frontend — **ON HOLD**

**Blocked on `apps/web/DESIGN.md`**, which is a brief, not a design, and has no
owner. Nothing in `apps/web` is built until a standardized design system exists.

This is a deliberate hold, not a backlog item waiting its turn. Three reasons,
set out in full in that document:

1. There is no design standard. The legacy accumulated four portals, two landing
   pages, a Streamlit UI, and 44 imported components with no shared decisions
   behind them; rebuilding without a standard reproduces that.
2. The generated TypeScript client does not exist yet, and building screens
   against a hand-written client recreates the coupling v1.1 §5.1 forbids.
3. Most screens have nothing truthful to show — the control center depends on
   match runs, which are blocked on gate G1. A screen built early gets filled
   with placeholder content, which is the exact habit this revamp exists to end.

`DESIGN.md` already records the constraints that are *settled* (provenance
labelling, truthful failure states, guards-are-UX-only, no hard-coded identity,
WCAG 2.2 AA, the professional's right to correct their own workload data) so the
redesign starts from them rather than rediscovering them.

| # | Item | Depends on | Notes |
|---|---|---|---|
| **D-0** | **Assign a DESIGN.md owner and settle the eight open decisions** | — | **Blocks everything below.** See `apps/web/DESIGN.md` Part 2. |
| W1 | Scaffold `apps/web` — React 18, TypeScript, Vite | D-0 | |
| W2 | Generate the TypeScript client from OpenAPI; add a drift check to CI | W1 | Routes now exist (`/imports`, `/v1/jobs/*`), so this is unblocked once W1 is |
| W4 | Provenance and truthful-state components | W1 | **Before W3 and W5, deliberately.** These enforce the labelling rule; anything built before them needs revisiting. |
| W3 | Port presentational components (MM-F01) | W1, W2, W4 | Confirm upstream shadcn/ui licensing first. Leave `mockData.ts` and `mockProfilePhotos.ts` behind. |
| W6 | Accessibility: WCAG 2.2 AA, plus a11y smoke tests in CI | W1 | |
| W5 | Matching control center — 13 views | M8, W2, W4 | Also blocked on gate G1 via M8 |
| W7 | Add web gates to CI (npm ci, tsc, vitest, bundle budget, Playwright) | W1 | Listed as deferred in `.github/workflows/verify.yml` |

---

## Deferred beyond R1

Recorded so the sequencing is visible, not scheduled here.

- **R2** — self-service professional profiles (required by the ELI design: people
  must be able to see and correct the workload data used about them), coordinator
  intake, accept/decline, ICS delivery, attendance and QR (MM-F02), feedback,
  contact-confidence lifecycle in the API.
- **R3** — read-only Jarvis, research scout, quarantine and provenance,
  extraction, entity resolution, human verification queue, agent eval dataset.
  **Requires the crawler threat model before any crawl code is written.**
- **R4** — consent-origin workflows, suppression, versioned approval, crash-safe
  send, scheduling proposals. Gate G4 and G5.
- **R5** — conversational control center, exception triage, scenario analysis,
  failure explanation, forecasting. No new mutation authority.

---

## Suggested next three

The durable command path is now complete end to end, including execution: a
command is authenticated, authorized, rate-limited, recorded, dispatched,
delivered, claimed, and run to a terminal state a client can follow over SSE.
See `docs/architecture/command-path.md` for the diagrammed version.

1. **J10** — a durable command payload. `/imports` is the only real command
   resource wired end-to-end today, and every import job that reaches the
   worker fails immediately with `failed_policy`, because the parameters the
   caller submitted were never recorded anywhere the worker can read them.
   Without this, the one implemented command cannot do anything.
2. **J8** — dispatcher scheduling. `run_once` and `lag` exist; nothing calls
   them on a timer, so a command commits and then waits for someone to invoke
   the dispatcher by hand or in a test.
3. **D1** — start the factor-registry approval conversation. Still the longest
   pole and still the only thing blocking the product's core.

**D-0** (assign a DESIGN.md owner) and **F3** (independent review of the four
ports) remain cheap, unblocked, and worth doing whenever an owner or a reviewer
is free. **J9** (the lease + sweeper for a job stuck in `running`) is not urgent
at today's traffic but should not be forgotten before anything depends on the
worker recovering from a crash mid-execution.
