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
| Deny-by-default authorization policy | `smartmatch_authz.policy` | 29 |
| Provider interfaces + fixture adapters + classroom isolation | `smartmatch_providers` | 16 |
| Tenant-safe schema, enforced by composite keys | `db/migrations` | 11 integration |
| Transactional outbox + dispatcher | `smartmatch_worker.dispatcher` | 17 integration |
| Job/outbox/idempotency repositories | `smartmatch_persistence` | 8 schema-drift |
| Transactional rate limiter | `smartmatch_persistence.rate_limit` | 14 integration |
| Authenticated command path, end to end | `services/api` | 26 integration |
| API health + non-mutating unsubscribe GET | `services/api` | 10 contract |
| Worker boundary, failing closed | `services/worker` | 4 contract |
| Forbidden-legacy-behavior scanner | `tools/scan_forbidden.py` | 25 self-tests |

**287 tests total** (286 pass, 1 skipped by design — see
`test_normalize_weights_honours_overrides_and_renormalizes`, which waits for a
second implemented scoring factor).

### Proposed, scaffolded, or deliberately absent

| Capability | State | Gated on |
|---|---|---|
| Matching / scoring | **Blocked** — registry proposed, scoring fails closed | Gate G1 (see finding F-001) |
| CP-SAT portfolio assignment | Not started | Gate G1, then R1 |
| Route-matrix travel time | Interface only; fixture adapter | Open decision 6 |
| Worker command execution | Dispatcher delivers; no handler consumes yet | R1 |
| Live identity verifier (JWKS) | Fixture only; accepts registered tokens only | R1 |
| Outreach / sending | Consent lifecycle only; **no send path exists** | Gate G4, R4 |
| Calendar API | **Not scaffolded.** ICS is the only artifact | Gate G5 |
| Research agents / crawler | Not scaffolded | Gate G3, R3 |
| `apps/web` frontend | **On hold** — see [`apps/web/DESIGN.md`](apps/web/DESIGN.md) | A DESIGN.md owner |
| Terraform | Skeleton only; **nothing deployed** | Later |
| Redis, Pub/Sub, BigQuery | **Deliberately absent** | Adoption triggers in v1.1 §3.5 |

Nothing here has been deployed, no live provider has been called, and no live
data has been imported.

---

## Quick start

Requires Python 3.11+ and PostgreSQL 16.

```bash
make setup          # virtualenv + dependencies
make db-up          # local PostgreSQL + dev database
make migrate        # apply the Foundation schema
make check          # every gate CI runs
```

`make check` runs formatting, lint, strict typing, architecture import
boundaries, the full test suite, and the forbidden-behavior scan. It is the same
set CI runs, so a green `make check` locally means a green CI.

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
| [Contract review and findings](docs/architecture/review/contract-findings.md) | Consistency checks, six findings, scaffold gate result |
| [Migration manifest](docs/migration/migration-manifest.yaml) | Every legacy component: ported, blocked, or archived, with reasons |
| [Rejected components](docs/migration/rejected-components.md) | What was deliberately not carried forward |
| [Security review](docs/security/scaffold-security-review.md) | Scaffold security posture and residual risk |
| [Verification record](docs/testing/scaffold-verification.md) | Every check run, with its exact result |
| [Remaining work](docs/plans/remaining-foundation-r1-work.md) | Foundation and R1 backlog in dependency order |
| [Frontend design brief](apps/web/DESIGN.md) | Constraints already settled, and the eight decisions the redesign must make |

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
