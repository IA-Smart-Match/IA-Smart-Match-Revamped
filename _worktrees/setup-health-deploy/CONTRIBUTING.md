# Contributing

**Scope:** how to get this repository running, exactly what a change has to pass
before it can merge, and the conventions that are not negotiable here.

Read [`README.md`](README.md) first. Its two tables — what is implemented and
tested, and what is proposed, scaffolded, or deliberately absent — are the
authority on what exists. Nothing in this repository is deployed, no live
provider has been called, and no live data has been imported; a change that
would alter any of those three facts is not an ordinary change.

---

## Setup

### Prerequisites

| Requirement | Version | Why this range |
|---|---|---|
| **Python** | **3.11 or 3.12** | `.python-version` says 3.11; `pyproject.toml` requires `>=3.11,<3.13` for all five workspace packages. **3.13 is not supported.** CI runs 3.11 and both images are `python:3.11-slim-bookworm`, so 3.11 is what everything is verified against. |
| **PostgreSQL** | **16** | Only for the integration lane and for running the app. `make check` needs no database. |
| **make**, **git** | any recent | — |

No compiler is needed — `psycopg[binary]` ships wheels.

Check first: `python3 --version` must report 3.11.x or 3.12.x.

### System packages

Debian and Ubuntu ship the standard library's virtualenv support as a separate
package. Without it, `make setup` fails on its first line.

```bash
# Debian / Ubuntu
sudo apt update && sudo apt install -y python3-venv postgresql-16

# Fedora / RHEL
sudo dnf install -y python3-devel postgresql16-server

# macOS (Homebrew)
brew install python@3.12 postgresql@16
```

### The four steps

```bash
make setup          # virtualenv + hash-verified dependencies + editable workspace packages
make db-up          # local PostgreSQL role and database
make migrate        # apply migrations to head
make check          # the local gate set
```

**`make setup` is slow, and interrupting it leaves a half-built virtualenv.**
The hash-verified install is the slow step: minutes on a native Linux
filesystem, and it can exceed fifteen on a Windows-mounted path under WSL
(`/mnt/c/...`). If it looks frozen, `ls .venv/lib/*/site-packages | wc -l` shows
the count still climbing. Working from the native Linux filesystem
(`~/src/...`) is a large speedup.

### Troubleshooting

Keyed to the error text you will actually see.

**`ensurepip is not available`, or `The virtual environment was not created successfully`**
→ `python3-venv` is missing. `sudo apt install python3-venv`. The most common
first-run failure on Debian and Ubuntu; it exits 1 on the first line of
`make setup`.

**`ERROR: Package 'smartmatch-domain' requires a different Python: 3.13.x not in '<3.13,>=3.11'`**
→ Python 3.13 or newer. Build the virtualenv with a supported interpreter
explicitly, then re-run: `python3.12 -m venv .venv && make setup`. This one
surfaces at the *last* step of `make setup`, after the dependency install has
already succeeded, so everything before it looks healthy.

**`su: Authentication failure` or `service: command not found` from `make db-up`**
→ See the note on `make db-up` below; provide the database yourself.

**`THESE PACKAGES DO NOT MATCH THE HASHES FROM THE REQUIREMENTS FILE`**
→ The lock and your index disagree. Do not work around it with `--no-deps`.
Re-run `make lock` and review the diff. `make lock` pins `pip-tools==7.6.1`
deliberately and that pin must match `.github/workflows/verify.yml` — the two
move together, because the step compares pip-compile's *output* against a
committed file, which makes the tool's version part of the comparison.

**`make format-check` fails right after a fresh clone on Windows**
→ Line endings. `git add --renormalize . && git checkout -- .` resets the
working copy.

**Still stuck?** Open an issue with `python3 --version`, your OS, and the last
twenty lines of `make setup`. The step it dies on identifies it.

`make setup` installs from `requirements/dev.txt` with `--require-hashes`, so a
compromised or newly broken upstream release cannot be picked up silently
(security finding S-003). Add a dependency by editing `requirements/*.in` and
running `make lock` — never by editing a lock file, and never by installing into
the virtualenv by hand. CI recompiles the locks and fails if the committed bytes
differ.

`make db-up` is written for a local Debian-style PostgreSQL service (`service
postgresql start`, then `su postgres`). On any other setup, provide the database
yourself and point `SMARTMATCH_DATABASE_URL` at it; `.env.example` documents
that variable and every other setting, and no value in it is a real credential.

The API and worker run against fixture providers and cannot be configured into a
live provider, because no live adapter is implemented and no credentials exist
here:

```bash
make run-api        # http://localhost:8000
make run-worker     # http://localhost:8001
```

---

## The gates

`make check` runs nine targets, in this order:

| Target | Command | What it protects |
|---|---|---|
| `format-check` | `ruff format --check .` | Formatting is not a review topic |
| `lint` | `ruff check .` | — |
| `typecheck` | `mypy python/ services/` | Strict typing across the packages and both services |
| `imports` | `lint-imports --config pyproject.toml` | The domain and authz packages import no framework, driver, provider SDK, filesystem module, or network library. See ADR-0002 |
| `test` | `pytest tests/ -m "not integration"` | The lane that needs no database |
| `scan` | `python tools/scan_forbidden.py` | The legacy anti-patterns cannot return. See §15 of the migration orchestrator contract |
| `memory` | `python tools/agent_memory_check.py` | The agent-memory ledger in `docs/agent-memory/` |
| `licenses` | `python tools/supply_chain.py licenses` | No dependency enters under a license outside the policy |
| `infra-check` | `python tools/env_isolation_check.py` | The Terraform environments share no identifier, so one environment cannot reach another's resources. Applies nothing |

**`make check` is a subset of CI, not the whole of it.** A green `make check` is
necessary and not sufficient. `.github/workflows/verify.yml` additionally runs,
on every pull request:

| CI step | Closest local command |
|---|---|
| Migrations apply from an empty database | `make migrate-check` |
| The **whole** test suite, integration lane included, with coverage | `make test-integration`, or `make test-all` |
| The committed OpenAPI document is current | `make openapi-check` |
| No tracked `.env` file | — |
| The dependency locks recompile to the committed bytes | `make lock`, then check the diff is empty |
| No tracked `.db`, `.sqlite`, `.zip`, `.tar.gz`, or `.jsonl` | — |
| `pip-audit --strict` against `requirements/runtime.txt` | — |
| gitleaks over the full history | — |

Run the integration lane before pushing anything that touches the schema, the
persistence package, or an API or worker route. Those four CI steps with no
local equivalent are cheap to satisfy and expensive to discover in review.

If you add a step to a workflow, pin the action to an immutable commit SHA with
the readable tag in a trailing comment, the way every action in `verify.yml`
already is. A tag can be moved, and a moved tag in a workflow with repository
write access is a supply-chain compromise.

---

## Tests

Two lanes, split by the `integration` marker declared in `pyproject.toml`:

```bash
make test               # pytest tests/ -m "not integration"    — no database
make test-integration   # pytest tests/ -m integration          — requires PostgreSQL 16
make test-all           # everything
```

The integration tests need a real PostgreSQL instance. They **skip themselves**
when none is reachable (`tests/integration/conftest.py`), which is what keeps
the other lane runnable anywhere — and is also why a passing local run proves
nothing about them unless you actually had a database. Check the skip count.

They are measured against PostgreSQL 16: `tests/integration/test_check_constraints.py`
pins constraint expressions against PostgreSQL 16's rendering of them, so a
major-version change is expected to fail that file and to be reviewed
deliberately rather than papered over.

### A test must fail against the behaviour it fixes

This is the standing rule, and it is not satisfied by a test that merely passes
after the fix. Demonstrate the fail-before, and say in the commit message how
you demonstrated it. The repository already does this by habit and records the
method each time — J14 in the backlog says "Both new tests fail against the
previous behaviour, confirmed by reverting the branch"; F10 records dropping
each CHECK constraint in turn and widening or relaxing eight of them, and names
which tests failed for each mutation. `make imports` has the same treatment in
the README, as a two-line recipe you can run to watch the gate fail.

A test whose failure mode you have never seen is a test you do not know the
meaning of. Where no honest failing test is possible, say so and say why, rather
than writing a weaker one that always passes: ADR-0009 does this for the online
migration call site, and `tests/unit/test_migration_transactions.py` repeats the
reasoning in its module docstring.

---

## Documentation is not a control

**A sentence in a document that the code does not enforce is a defect, not a
safeguard.** This is the single most important convention in this repository,
and every mechanism here exists because of it:

- The layer boundaries are an executable import-linter contract, not a diagram
  (ADR-0002). Architecture v1.1 §3.3's phrase — a diagram label is not a control
  — is quoted in `python/smartmatch_providers/smartmatch_providers/base.py` and
  in `tests/unit/test_provider_isolation.py`, at the two places that turn it
  into code.
- Tenant isolation is composite foreign keys that PostgreSQL rejects writes
  against, proven by integration tests, rather than a rule stated in a comment.
- The forbidden-behaviour scanner has its own self-tests, "because a gate nobody
  has verified is worse than no gate."
- The ADR index is checked against the ADR files by `tests/unit/test_adr_index.py`.
- The agent-memory ledger's own rule is that memory never outranks the
  repository: a record that conflicts with the code is a defect in the record.

Two consequences for you. First, if you write a rule, ask what fails when
someone breaks it; if the answer is "nothing", either build the check or write
the sentence as an acknowledged gap rather than as a safeguard. Second, when you
change behaviour, the prose that described the old behaviour is now false and
fixing it is part of the change — ADR-0009 rewrote migration `0003`'s docstring
for exactly this reason, because the paragraph telling a future author to
inherit the old transaction behaviour "would otherwise have left the repository
asserting something untrue about itself."

Claims about counts, results, and versions are held to the same standard. State
the command you ran and its output; do not carry a number forward because it was
true once. The README records what that costs when it slips.

---

## Commits

`git log` uses Conventional Commit subjects — `docs:`, `feat(api):`,
`fix(dispatcher):`, `build:`, `test(schema):` — in lower case and in the
imperative. The subject is one line; the body is where the work is justified,
and bodies here are long on purpose. A good body states what was checked, how,
and what the check returned, including the gates run and anything deliberately
not run ("Integration tests NOT run; there is no PostgreSQL in this
environment" is a real and correct line from this history).

Trailers:

```
Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
```

and, for a port from the legacy repository, the provenance trailers the README's
"Adding a port" section specifies — `Legacy-Source:`, `Migration-Manifest:`,
`Contract-Refs:`. The legacy repository is read-only evidence; do not copy files
from it, and create the migration-manifest entry before writing code.

## Architecture decisions

An ADR is immutable once accepted. A decision that stops being true is replaced
by a new ADR that supersedes it; a decision that is refined carries an
amendment. Both go in the index in `docs/architecture/decisions/README.md`,
which a test verifies against the files — including that ADR numbers are
contiguous from one, so a reserved-but-unwritten number cannot be left as a gap.
ADR-0015 is reserved; do not take it.

---

## What is not decided here

**There is deliberately no `LICENSE` file, and adding one is not an engineering
task.** Backlog item F13 blocks it on decision D9 — whether this repository may
be open-sourced — which is owned by the program owner and is itself gated by the
unremediated severity-1 finding recorded as MM-A09 in
`docs/migration/migration-manifest.yaml`: real-identity datasets tracked in the
*legacy* repository's git history, which archiving at HEAD does not remove.
Publishing history that includes those paths would broaden that exposure. Leave
the file absent until D9 is recorded.

The same applies more generally: the release gates G1–G5 in the README have
owners outside engineering, and they are never inferred from technical
readiness.
