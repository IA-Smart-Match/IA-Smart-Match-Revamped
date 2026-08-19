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
| F7 | Widen the schema drift test beyond column names | — | It compares column *name sets*, composite FKs, and three named constraints. Types, nullability, server defaults, indexes, and FK actions are unchecked — `schema.py` declares `org_unit.tenant_id` without the `ondelete="RESTRICT"` the migration specifies, and CI cannot see it. The database is correct; the hand-written mirror is not. |
| F8 | Add an ADR index | — | ADR-0004..0007 are discoverable only by directory listing. |

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
| ~~A1a~~ | ~~Token verification adapter and principal resolution~~ | — | **Done.** Interface, fixture, and database-backed principal lookup. |
| A1b | Live Google Identity Platform verifier (JWKS, audience, rotation) | — | The fixture accepts only registered tokens, so it cannot be mistaken for permissive auth. |
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
