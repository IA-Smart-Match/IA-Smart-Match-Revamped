# SmartMatch Platform

IA West SmartMatch — production platform, built to
[Architecture v1.1](docs/architecture/review/contract-findings.md).

> **Status: Foundation scaffold.** This repository is *not* production-ready and
> does not claim to be. What is implemented and what is merely proposed are
> listed explicitly below, because the single most damaging habit in the demo
> this replaces was presenting proposed things as working ones.

This is a ground-up rebuild around the accepted v1.1 contracts, not a
reorganization of the hackathon demo. Behavior from the legacy repository
(`BrooklynD23/Nebiux-Team-IA-West-SmartMatch` @ `bdce024`) is ported only where
it survives evidence, security, architecture, and test review — every port has a
[migration manifest](docs/migration/migration-manifest.yaml) entry recording what
was kept, what was rejected, and why.

---

## What is implemented, and what is not

### Implemented and tested

| Capability | Where | Tests |
|---|---|---|
| Engagement Load Index — hard cap + soft penalty | `smartmatch_domain.eli` | 18 |
| RFC 5545 ICS generation, folded and timezone-correct | `smartmatch_domain.ics` | 15 golden |
| Contact-confidence lifecycle and send eligibility | `smartmatch_domain.consent` | 20 |
| Durable job state machine | `smartmatch_domain.jobs` | 14 |
| Import validation and normalization | `smartmatch_domain.ingest` | 13 |
| Shadow-mode feedback → weight proposals | `smartmatch_domain.feedback` | 16 |
| Factor registry (proposal; scoring fails closed) | `smartmatch_domain.factor_registry` | 17 |
| Deny-by-default authorization policy | `smartmatch_authz.policy` | 32 |
| Provider interfaces + fixture adapters + classroom isolation | `smartmatch_providers` | 16 |
| Tenant-safe schema, enforced by composite keys | `db/migrations` | 11 integration |
| Schema matches migration — foreign keys, nullability, types, PK/UQ/CHECK constraint names, per table (ADR-0004 amendment) | `smartmatch_persistence.schema`, `db/migrations` | 115 integration |
| `job.status` CHECK constraint matches `smartmatch_domain.jobs.JobState` | `db/migrations`, `smartmatch_domain.jobs` | 13 integration |
| Transactional outbox + dispatcher, parking a job at attempt exhaustion | `smartmatch_worker.dispatcher` | 41 integration |
| Transactional rate limiter | `smartmatch_persistence.rate_limit` | 18 integration + 4 unit |
| Spend reservation state machine, guarded reservation service, and conservative abandoned-reservation sweeper (ADR-0015 A1) | `smartmatch_domain.spend`, `smartmatch_persistence.spend`, `smartmatch_persistence.spend_sweeper` | 100 unit + 14 PostgreSQL integration collected; integration unexecuted locally |
| Synthetic paid-extraction seam and opt-in worker handler; deliberately absent from the shipped registry | `smartmatch_providers.paid`, `smartmatch_worker.paid_extraction` | 55 unit |
| Authenticated command path, end to end | `services/api` | 29 integration |
| Identity lookup — `external_subject` globally unique (ADR-0008) | `smartmatch_persistence.principals` | 6 integration |
| API health + non-mutating unsubscribe GET | `services/api` | 10 contract |
| Standard error envelope across the API | `services/api` | 13 contract |
| Worker command execution — claim, run to a terminal state, job events | `smartmatch_worker.execution` | 31 integration |
| OIDC task-identity verification, ships with no signature backend | `smartmatch_worker.identity` | included above + 4 contract |
| Re-drive and abandon commands for parked work | `services/api/.../routers/redrive.py` | 30 integration |
| Forbidden-legacy-behavior scanner | `tools/scan_forbidden.py` | 25 self-tests |
| ADR index checked against the ADR files | `docs/architecture/decisions`, `tests/unit/test_adr_index.py` | 145 |
| Agent-memory ledger validation | `tools/agent_memory_check.py` | 80 |
| CHECK constraints exercised behaviourally — the forbidden write *and* the permitted one | `db/migrations` | 50 integration |
| One transaction per Alembic revision (ADR-0009) | `db/migrations/env.py` | 3 |

**1,817 tests collected: 1,266 in the no-database lane and 551 marked for the
integration lane.** These are fresh collection measurements from
`pytest tests/ --collect-only -q` and `pytest tests/ -m integration`. They are
not a passing-test claim: PostgreSQL was unavailable in the latest local run,
so all 551 integration tests skipped, including the 14 spend-reservation tests.
The no-database run also did not complete in that environment because
`tests/contract/test_api_health.py::test_health_reports_ok` blocked; see the
[A1 verification record](docs/testing/adr0015-a1-spend-persistence-verification.md).

### Proposed, scaffolded, or deliberately absent

| Capability | State | Gated on |
|---|---|---|
| Matching / scoring | **Blocked** — registry proposed, scoring fails closed | Gate G1 (see finding F-001) |
| CP-SAT portfolio assignment | Not started | Gate G1, then R1 |
| Route-matrix travel time | Interface only; fixture adapter | Open decision 6 |
| Command payload persistence | **Done (J10).** `job.payload` (migration `0005`); `import.create` executes with persisted parameters | — |
| Live worker task-identity verifier | Verification logic is real; ships with no signature backend, so it refuses every task delivery | R1 (before worker deploy) |
| Live identity verifier for user requests (JWKS) | Fixture only; accepts registered tokens only | R1 |
| Outreach / sending | Consent lifecycle only; **no send path exists** | Gate G4, R4 |
| Calendar API | **Not scaffolded.** ICS is the only artifact | Gate G5 |
| Research agents / crawler | Not scaffolded | Gate G3, R3 |
| Live paid extraction | **Absent/gated.** Only a synthetic provider and opt-in handler exist; `main.py` does not register them in the shipped worker | Live-provider/A3 confirmation, edition/config gate, credentials, and production ceilings |
| `apps/web` frontend | **On hold** — see [`apps/web/DESIGN.md`](apps/web/DESIGN.md) | A DESIGN.md owner |
| Terraform | Skeleton only; **nothing deployed** | Later |
| Student engagement — attendance, points ledger, rewards, disclosure consent | **Designed, not built** — see [`docs/architecture/engagement-model.md`](docs/architecture/engagement-model.md), ADR-0013, ADR-0014 | R2, with attendance/QR; a shipped catalog also needs D6 and D7, and S10 needs D8 |
| Pipeline funnel — Matched → Contacted → Confirmed → Attended → Member Inquiry | **Not started.** Five registered metrics with one owning query, per ADR-0011 | S12, behind the metric register (S1) |
| Redis, Pub/Sub, BigQuery | **Deliberately absent** | Adoption triggers in v1.1 §3.5 |

Nothing here has been deployed, no live provider has been called, and no live
data has been imported.

---

## Quick start

**Python 3.11 or 3.12** — `pyproject.toml` requires `>=3.11,<3.13`, so **3.13
does not work**. CI runs 3.11 and both images are `python:3.11-slim-bookworm`,
which makes 3.11 the version everything is actually verified against. Plus
**PostgreSQL 16**, needed only for the integration lane and for running the app.

On Debian and Ubuntu, install `python3-venv` first — it is a separate package
there, and without it `make setup` fails on its first line with exit code 1.

```bash
sudo apt install -y python3-venv     # Debian/Ubuntu only
make setup          # virtualenv + hash-verified dependencies (slow; do not interrupt)
make db-up          # local PostgreSQL + dev database — REQUIRES ROOT
make migrate        # apply the Foundation schema
make check          # the nine gates that run without infrastructure
```

`make check` runs nine gates: formatting, lint, strict typing, architecture
import boundaries, the no-database test lane, the forbidden-behavior scan, the
agent-memory ledger check, the dependency-license policy, and the Terraform
environment-isolation check.

Two things bite newcomers. `make setup` is slow — the hash-verified install
takes minutes on a native Linux filesystem and can exceed fifteen on a
Windows-mounted path under WSL (`/mnt/c/...`); a run that looks hung is usually
still working. And `make db-up` **requires root**: it runs `service postgresql
start` and `su postgres`, so it fails on WSL without systemd, on macOS, and
anywhere you cannot become `postgres`. [`CONTRIBUTING.md`](CONTRIBUTING.md)
gives the manual database steps and a troubleshooting section keyed to the exact
error text.

**It is a subset of CI, not the whole of it, so a green `make check` does not
mean a green CI.** Two differences matter. `make test` is
`pytest tests/ -m "not integration"` — the no-database lane, not the full suite;
the integration tests need PostgreSQL and *skip themselves* when none is
reachable, so a clean local run proves nothing about them unless you actually
had a database. And CI additionally runs the migration from an empty database,
the full suite including the integration lane, the OpenAPI drift check, the
dependency-lock recompilation, `pip-audit --strict`, gitleaks over full history,
the tracked-artifact checks, and the container image build. `make test-all` and
`make migrate-check` close part of that gap locally; the rest needs CI.

The precise list, with the local counterpart of each CI step, is in
[`CONTRIBUTING.md`](CONTRIBUTING.md).

```bash
make run-api        # http://localhost:8000  (fixtures only)
make run-worker     # http://localhost:8001
```

The API runs against fixture providers by default and cannot be configured into
a live provider without credentials that do not exist in this repository.

---

## Layout

```
python/smartmatch_domain/      Pure domain logic. Zero dependencies.
python/smartmatch_authz/       Deny-by-default policy. Pure.
python/smartmatch_providers/   Provider interfaces + fixture adapters.
python/smartmatch_persistence/ PostgreSQL schema and repositories.
services/api/                  FastAPI HTTP boundary.
services/worker/               Private Cloud Tasks target + outbox dispatcher.
apps/web/                      Frontend. ON HOLD — see apps/web/DESIGN.md.
contracts/openapi/             Generated contract — source of truth for clients.
db/migrations/                 Alembic, expand → migrate → contract.
requirements/                  Hash-pinned dependency locks.
infra/terraform/               Environment skeletons. Nothing deployed.
tools/                         Verification scripts.
tests/                         unit · golden · authz · contract · integration
docs/                          architecture · migration · security · testing
```

### The boundary that matters

`smartmatch_domain` and `smartmatch_authz` import **no** framework, database
driver, provider SDK, filesystem module, or network library — not even `os`.
This is enforced by import-linter contracts in `pyproject.toml` and checked in
CI, not left to convention. It is what makes the domain rules testable without
infrastructure, and it is why the test suite runs in under two seconds.

Verify the gate is real rather than decorative:

```bash
echo "import os" >> python/smartmatch_domain/smartmatch_domain/jobs.py
make imports        # fails
git checkout python/smartmatch_domain/
```

---

## Working on this

Every change goes through the gates in `make check`. Three of them exist
specifically to stop the demo's habits returning:

- **`make imports`** — the domain cannot acquire a framework dependency by accident.
- **`make scan`** — [`tools/scan_forbidden.py`](tools/scan_forbidden.py) fails the
  build on caller-selected identity, fabricated scores or meeting URLs, business
  writes to local files, module-level authoritative state, demo-mode fallbacks,
  mutating GETs, inline provider calls, and hard-coded credentials. It has its own
  self-tests, because a gate nobody has verified is worse than no gate.
- **`make test-integration`** — tenant isolation is proven against real
  PostgreSQL, not asserted in a comment.

### Adding a port from the legacy repository

The legacy repository is read-only evidence. Do not copy files. Per §9 of the
migration orchestrator contract:

1. Create the migration-manifest entry **before** writing code.
2. Write characterization tests capturing the behavior worth keeping.
3. Port the smallest useful unit against target interfaces.
4. Strip framework, storage, provider, and demo coupling.
5. Run `make check`.
6. Commit separately, with provenance trailers:

```
Legacy-Source: BrooklynD23/Nebiux-Team-IA-West-SmartMatch@bdce024:<path-or-symbol>
Migration-Manifest: MM-0NN
Contract-Refs: v1.1 §N.N
```

---

## Documentation

| Document | Contents |
|---|---|
| [Command path](docs/architecture/command-path.md) | Diagrams: the durable command path end to end, the job state machine, the re-drive cycle |
| [Contract review and findings](docs/architecture/review/contract-findings.md) | Consistency checks, six findings, scaffold gate result |
| [Migration manifest](docs/migration/migration-manifest.yaml) | Every legacy component: ported, blocked, or archived, with reasons |
| [Rejected components](docs/migration/rejected-components.md) | What was deliberately not carried forward |
| [Security review](docs/security/scaffold-security-review.md) | Scaffold security posture and residual risk |
| [Verification record](docs/testing/scaffold-verification.md) | Every check run, with its exact result |
| [Remaining work](docs/plans/remaining-foundation-r1-work.md) | Foundation and R1 backlog in dependency order |
| [Frontend design brief](apps/web/DESIGN.md) | Constraints already settled, and the eleven decisions the redesign must make |

---

## Release train

Capability releases with institutional gates (v1.1 §4.3). Dates follow evidence,
not the reverse.

```
Foundation ──▶ R1 ──▶ R2 ──▶ R3 ──▶ R4 ──▶ R5
   (here)      │       │      │      │
               G1      G2     G3    G4,G5
```

| Gate | Blocks | Owner |
|---|---|---|
| G1 — factor registry + golden cases approved | R1 | Program owner |
| G2 — privacy, records, data-owner approval for live records | R2 | Privacy / legal / records |
| G3 — agent eval set, tool allowlist, cost controls | R3 | Engineering ADR + program owner |
| G4 — consent-origin policy, recipient policy, deliverability | R4 | Program owner + privacy/legal |
| G5 — Calendar authorization model | R4 direct Calendar | Workspace admin + security |

Gate owners sit outside engineering and are never inferred from technical
readiness.

---

## Notice — private pilot, not open-source licensed

> **This repository is a private pilot for IA West SmartMatch. It is not
> open-source licensed, and it carries no `LICENSE` file deliberately.**
>
> The absence of a `LICENSE` is a decision, not an oversight. No license is
> granted to anyone by this repository being visible.
>
> This is a plain statement of intent, not legal language, and nobody qualified
> to write licensing terms has reviewed it.

The decision behind it is **D9**, recorded as a **tentative, not organizationally
ratified** position in
[`docs/decisions/pilot-decisions.md`](docs/decisions/pilot-decisions.md). It
stays gated on the unremediated finding **MM-A09**: the archived legacy
repository's git history still contains paths naming real people, and publishing
that history would broaden the exposure. `CONTRIBUTING.md` carries the same
position from the engineering side.
