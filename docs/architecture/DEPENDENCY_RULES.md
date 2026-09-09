# Dependency Rules

**Stage 2.** The target import boundaries, written so they can be implemented as
`import-linter` contracts. Commit base `c72dced`, 8 September 2026.
Companion to `ARCHITECTURE_PRINCIPLES.md` (AP-01, AP-02) and
`dependency-analysis.md` §1, §3.

---

## 1. Current state

### 1.1 What is governed (OBSERVED)

`pyproject.toml` `[tool.importlinter]` declares:

```toml
root_packages = [
    "smartmatch_domain",
    "smartmatch_authz",
    "smartmatch_providers",
    "smartmatch_persistence",
]
include_external_packages = true
```

and four contracts:

| # | Name | Type | Effect |
|---|---|---|---|
| 1 | Domain is pure — no frameworks, storage, providers, IO, or env | `forbidden` | `smartmatch_domain` may not import `fastapi`, `starlette`, `sqlalchemy`, `alembic`, `pydantic_settings`, `httpx`, `requests`, `google`, `boto3`, `os`, `pathlib`, `socket`, `subprocess`, `smartmatch_providers` |
| 2 | Authz is pure — policy only, no frameworks or storage | `forbidden` | narrower list, same shape |
| 3 | Layering: outer packages may use domain types, never the reverse | `layers` | persistence → providers → authz → domain, one direction |
| 4 | Persistence is storage only — no network, providers, or frameworks | `forbidden` | no `fastapi`, `starlette`, `httpx`, `requests`, `subprocess`, `smartmatch_providers` |

`include_external_packages = true` is what makes "domain must not import FastAPI"
expressible at all. `os` and `pathlib` in contract 1 make it a genuinely strict
purity contract rather than a nominal one. Run by `Makefile:67-69`
(`make imports`) and by `verify.yml:101-104`, step *"Architecture import
boundaries"*, both as
`PYTHONPATH="$DOMAIN_PATH" lint-imports --config pyproject.toml` where
`DOMAIN_PATH` (`Makefile:11`) names only the four `python/` source roots.

No violation of contracts 1–4 exists today, and no genuine import cycle exists in
any of the six packages (`dependency-analysis.md` §2).

### 1.2 What is ungoverned (the finding)

**R-06.** `smartmatch_api` (14k L) and `smartmatch_worker` (7k L) — 28,080 lines,
40% of production Python — are in no `root_package` and therefore in no contract.
Three consequences, each observed:

- **Router→router coupling, twice.**
  `services/api/smartmatch_api/routers/cba_contact_channels.py:131` imports
  `SPEAKER_CONTACT_READ_RATE_LIMIT` and `_authorize_speaker_contacts` from
  `routers/cba_contacts`;
  `services/api/smartmatch_api/routers/outreach_contacts.py:109` imports
  `READ_RATE_LIMIT` and `_authorize_outreach` from `routers/outreach`. Both are
  documented and argued in `main.py`'s router table; both reach across a sibling
  module for an underscore-prefixed name (AP-02).
- **Nothing prevents api↔worker imports.** Verified 8 September 2026: a grep for
  import statements (`^\s*(from|import)\s+smartmatch_worker` under
  `services/api/`, `tools/`, `python/`, and the mirror for `smartmatch_api` under
  `services/worker/`) returns **zero hits in both directions**. The 7 API files
  and 2 worker files that mention the other service do so only in docstrings and
  comments — e.g. `routers/imports.py:102` and `handlers.py:312`, which
  deliberately describe the other side of the command contract in prose. **The
  boundary holds today entirely by convention**, which is precisely why it is
  cheap to contract now and expensive later.
- **The service layer's public surface is undefinable.** With no contract, any
  module may import any other, so "what is `smartmatch_api`'s API" has no answer
  a tool can give.

**R-05.** Neither service manifest declares `smartmatch-persistence`, which
`services/api` imports in 33 files and `services/worker` in 10.
`services/api/pyproject.toml` lists `smartmatch-domain`, `smartmatch-authz`,
`smartmatch-providers`; `services/worker/pyproject.toml` lists the same three.
`services/api/smartmatch_api/main.py:47` opens with
`from smartmatch_persistence.engine import create_session_factory`. It works only
because CI installs every package with `pip install --no-deps -e` and
`[tool.pytest.ini_options].pythonpath` adds every source root.

### 1.3 The measured graph today (OBSERVED)

| Consumer ↓ / Provider → | domain | authz | providers | persistence | api | worker |
|---|---|---|---|---|---|---|
| `smartmatch_domain` | internal | — | forbidden | forbidden | — | — |
| `smartmatch_authz` | — | internal | forbidden | forbidden | — | — |
| `smartmatch_providers` | 4 | — | internal | forbidden | — | — |
| `smartmatch_persistence` | 14 | 1 | forbidden | internal | — | — |
| `services/api` | 29 | 21 | 5 | 31 | internal | **0** |
| `services/worker` | 8 | — | 6 | 9 | **0** | internal |
| `tools/` | 11 | — | — | 22 | **8** | — |

The `tools/` → `smartmatch_api` column is a Stage 2 correction to the assumption
that `tools/` touches only persistence and domain. Verified: eight scripts import
`smartmatch_api.config.Settings` (`tools/generate_pilot_dataset.py:208`,
`seed_demo_pipeline.py:87`, `seed_pilot.py:17`, `seed_pilot_review.py:39`,
`seed_pilot_principals.py:67`, `seed_pilot_logins.py:66`,
`seed_pilot_rewards.py:71`, and one further), and one reaches into a **router**:
`tools/generate_pilot_dataset.py:209`
`from smartmatch_api.routers.match_runs import MAX_CANDIDATES`. The `Makefile`
targets that run them add `services/api` to `PYTHONPATH` explicitly
(`Makefile:156,166,174,186,194,219`), so this is deliberate, not accidental. It
is nevertheless the same shape as R-06's router coupling, one layer out — see
DR-7.

---

## 2. Target rules

Each rule names the risk it closes and the principle it enforces. Rules are
stated in prose here and rendered as TOML in §3.

**DR-1 — Both services are governed.** `smartmatch_api` and `smartmatch_worker`
join `root_packages`. *Closes R-06 · enforces AP-01.* Consequence to land in the
same change: `Makefile:11`'s `DOMAIN_PATH` and `verify.yml:104` gain
`services/api:services/worker` on `PYTHONPATH`, or `lint-imports` cannot import
the new roots and errors out. This is the one part of M2 that is not a pure
addition.

**DR-2 — The API may import the inner packages; never the worker.**
`smartmatch_api` may import `smartmatch_domain`, `smartmatch_authz`,
`smartmatch_providers`, `smartmatch_persistence`. It may not import
`smartmatch_worker`. *Closes R-06 (§3c) · enforces AP-01.* True today (0 imports);
the contract records it before it stops being true.

**DR-3 — The worker may import the inner packages; never the API.**
`smartmatch_worker` may import `smartmatch_domain`, `smartmatch_providers`,
`smartmatch_persistence` — and `smartmatch_authz`, which it does not import today
(0 files) but which is a policy package and would be a legitimate dependency. It
may not import `smartmatch_api`. *Closes R-06 (§3c) · enforces AP-01.* The two
services communicate through persisted commands and the outbox, never through
Python imports; the prose cross-references at `routers/imports.py:102` and
`handlers.py:312` are the correct form of that coupling.

**DR-4 — No router imports another router.** No module under
`smartmatch_api.routers` may import any other module under
`smartmatch_api.routers`. *Closes R-06 (§3b) · enforces AP-02.*

*Contract type: `independence`, not `forbidden` or `layers`.* Justification —
`layers` is wrong because it imposes an *order*, and 25 router modules have no order;
expressing "mutually independent" as layers would require 26 layer entries and
would assert a hierarchy that does not exist. `forbidden` with
`source_modules = ["smartmatch_api.routers.*"]` and the same glob in
`forbidden_modules` is expressible but self-referential — every router would be
forbidden from importing *itself*, and its own internal submodule imports would
need exclusion. `independence` says exactly the intended thing — these modules
are siblings and none may reach another — in one block, and its violation report
names the importer and the imported symbol, which is what a reviewer needs.

**DR-5 — Routers may import shared API modules.** `smartmatch_api.routers.*` may
import `smartmatch_api.dependencies`, `errors`, `units`, `config`, `commands`,
`job_authz`, `utils` (`clock` after M1), `match_run_evidence`,
`pipeline_provisioning`, `zip_proximity`. This is the intended direction and is
not constrained. *Enforces AP-02* — it is the direction the promoted authz module
travels.

**DR-6 — Shared API modules may not import routers.** No module directly under
`smartmatch_api` may import `smartmatch_api.routers.*`, **except**
`smartmatch_api.main`, which is the composition root and imports every router by
definition. *Closes R-06 · enforces AP-02.* Verified: `main.py` is the only
shared module that imports `routers` today. `pipeline_provisioning.py` mentions
`routers/review.py` and `routers/attendance.py` at lines 12, 47 and 56 — prose
only, no import — so this contract passes on the current tree with no
`ignore_imports`.

**DR-7 — `tools/` imports persistence, domain, and API *configuration* — never a
router.** *Enforces AP-02, extends AP-01.* `tools/` has no `__init__.py` and is
not importable as a package, so it cannot be a `root_package` and **no
import-linter contract can express this rule**. Stated honestly: DR-7 is a review
rule plus a test, not a contract. The one current violation of its second half is
`tools/generate_pilot_dataset.py:209`, which imports `MAX_CANDIDATES` from
`routers/match_runs`. Disposition — the same as AP-02's: the constant is a
published bound, not a router internal, and belongs beside `MAX_SUBTREE_UNITS` in
an owned module. **Disposition: T-1.5 in `IMPLEMENTATION_ROADMAP.md` moves
`MAX_CANDIDATES` into an owned non-router module and re-points
`tools/generate_pilot_dataset.py:209`.** Until that lands it stands as a recorded
exception, not as an accident.

**DR-8 — The domain still imports nothing.** Contracts 1–4 are unchanged, in
their current wording, with their current forbidden lists. *Non-negotiable #1;
ADR-0002.* No rule below weakens them, and no rule below is permitted to.

**DR-9 — Tests are unconstrained.** `tests/` is not a `root_package` and takes no
contract. A test that reaches across every boundary to set up a fixture is doing
its job; constraining test imports would produce indirection whose only purpose
is to satisfy a linter.

---

## 3. Draft TOML — paste-ready

**Version assumption.** `import-linter==2.13`, pinned at
`requirements/dev.txt:573` (`pyproject.toml:30` declares `import-linter>=2.1`).
Under 2.x, `*` wildcards are supported in `forbidden` contracts'
`source_modules` / `forbidden_modules` and in `independence` contracts' `modules`;
`*` matches one module name segment and `**` matches any depth. The routers
package is flat (25 modules plus `__init__.py` directly under
`smartmatch_api/routers/`), so a
single `*` is sufficient. **If `lint-imports` rejects a wildcard on this version,
the fallback is to enumerate the 25 router modules explicitly** — verbose, and
identical in effect; do not silence the contract to avoid the verbosity.

**Contract numbering.** Contracts are numbered by their order in the TOML block
below: 1–4 exist today and are unchanged, 5–9 are added by M2. Every reference
elsewhere in `docs/` uses these numbers.

| # | Name | Type | DR rule | AP |
|---|---|---|---|---|
| 1 | `Domain is pure — no frameworks, storage, providers, IO, or env` | `forbidden` | DR-8 | — (ADR-0002, non-negotiable #1) |
| 2 | `Authz is pure — policy only, no frameworks or storage` | `forbidden` | DR-8 | — (ADR-0002) |
| 3 | `Layering: outer packages may use domain types, never the reverse` | `layers` | DR-8 | — (ADR-0002) |
| 4 | `Persistence is storage only — no network, providers, or frameworks` | `forbidden` | DR-8 | — (ADR-0002) |
| 5 | `The API sits above the inner packages, never beneath them` | `layers` | DR-2 | AP-01 |
| 6 | `The worker sits above the inner packages, never beneath them` | `layers` | DR-3 | AP-01 |
| 7 | `The API and the worker are independent services` | `independence` | DR-2 + DR-3 | AP-01 |
| 8 | `Routers are independent of one another` | `independence` | DR-4 | AP-02 |
| 9 | `Shared API modules must not import routers` | `forbidden` | DR-6 | AP-02 |

`root_packages` gaining `smartmatch_api` and `smartmatch_worker` (DR-1) is not a
contract and takes no number; it is what makes 5–9 expressible.

```toml
[tool.importlinter]
root_packages = [
    "smartmatch_domain",
    "smartmatch_authz",
    "smartmatch_providers",
    "smartmatch_persistence",
    # DR-1 (AP-01, R-06). 28,080 lines that no contract governed until M2.
    # Adding these requires services/api and services/worker on PYTHONPATH for
    # `lint-imports` — see Makefile DOMAIN_PATH and verify.yml.
    "smartmatch_api",
    "smartmatch_worker",
]
# Required so the forbidden contracts below can name third-party and stdlib
# modules. Without it, "domain must not import FastAPI" cannot be expressed.
include_external_packages = true

[[tool.importlinter.contracts]]
name = "Domain is pure — no frameworks, storage, providers, IO, or env"
type = "forbidden"
source_modules = ["smartmatch_domain"]
forbidden_modules = [
    "fastapi",
    "starlette",
    "sqlalchemy",
    "alembic",
    "pydantic_settings",
    "httpx",
    "requests",
    "google",
    "boto3",
    "os",
    "pathlib",
    "socket",
    "subprocess",
    "smartmatch_providers",
]

[[tool.importlinter.contracts]]
name = "Authz is pure — policy only, no frameworks or storage"
type = "forbidden"
source_modules = ["smartmatch_authz"]
forbidden_modules = [
    "fastapi",
    "starlette",
    "sqlalchemy",
    "httpx",
    "requests",
    "os",
    "subprocess",
    "smartmatch_providers",
]

[[tool.importlinter.contracts]]
name = "Layering: outer packages may use domain types, never the reverse"
type = "layers"
layers = [
    "smartmatch_persistence",
    "smartmatch_providers",
    "smartmatch_authz",
    "smartmatch_domain",
]

# Persistence is allowed SQLAlchemy — it is the storage layer — but it must not
# reach the network, spawn processes, or call providers. Storage that quietly
# makes an HTTP call is the coupling this contract exists to prevent.
[[tool.importlinter.contracts]]
name = "Persistence is storage only — no network, providers, or frameworks"
type = "forbidden"
source_modules = ["smartmatch_persistence"]
forbidden_modules = [
    "fastapi",
    "starlette",
    "httpx",
    "requests",
    "subprocess",
    "smartmatch_providers",
]

# --- Added by M2. Everything above is unchanged. ---------------------------

# DR-2 (AP-01, R-06). The API sits above the inner stack and may use all of it.
# A separate contract per service rather than one shared layers list, because
# the two services are siblings with no order between them — that relationship
# is stated by the independence contract below, not by a layer.
# Contract 5 — The API sits above the inner packages, never beneath them
[[tool.importlinter.contracts]]
name = "The API sits above the inner packages, never beneath them"
type = "layers"
layers = [
    "smartmatch_api",
    "smartmatch_persistence",
    "smartmatch_providers",
    "smartmatch_authz",
    "smartmatch_domain",
]

# DR-3 (AP-01, R-06). Same shape for the worker. smartmatch_authz is included
# although the worker imports it in zero files today: it is a policy package and
# a future authorization decision in a handler is a legitimate import, not a
# boundary violation.
# Contract 6 — The worker sits above the inner packages, never beneath them
[[tool.importlinter.contracts]]
name = "The worker sits above the inner packages, never beneath them"
type = "layers"
layers = [
    "smartmatch_worker",
    "smartmatch_persistence",
    "smartmatch_providers",
    "smartmatch_authz",
    "smartmatch_domain",
]

# DR-2 + DR-3 (AP-01, R-06 §3c). Verified 2026-09-08: zero imports in either
# direction. The two services communicate through persisted commands and the
# outbox. The prose cross-references (routers/imports.py:102,
# worker/handlers.py:312) are the correct form of that coupling and are not
# imports. This contract records a property that holds, before it stops holding.
# Contract 7 — The API and the worker are independent services
[[tool.importlinter.contracts]]
name = "The API and the worker are independent services"
type = "independence"
modules = [
    "smartmatch_api",
    "smartmatch_worker",
]

# DR-4 (AP-02, R-06 §3b). No router reaches into a sibling router.
#
# The two ignores below are the two documented, argued cases in main.py's router
# table. They are transitional: M2 promotes _authorize_outreach and
# _authorize_speaker_contacts (plus their rate-limit constants) into an owned
# unit-authorization module on the job_authz.py model, and DELETES these two
# lines in the same commit. Keeping them here lets the contract land BEFORE the
# promotion, so M2 is two independently reversible steps rather than one.
#
# Nothing may be added to this list. A third router with the same question
# promotes the helper; it does not add an ignore.
# Contract 8 — Routers are independent of one another
[[tool.importlinter.contracts]]
name = "Routers are independent of one another"
type = "independence"
modules = [
    "smartmatch_api.routers.*",
]
ignore_imports = [
    "smartmatch_api.routers.cba_contact_channels -> smartmatch_api.routers.cba_contacts",
    "smartmatch_api.routers.outreach_contacts -> smartmatch_api.routers.outreach",
]

# DR-6 (AP-02, R-06). The shared modules are the router layer's dependencies,
# not its consumers. smartmatch_api.main is absent from source_modules because it
# is the composition root: it imports every router and mounts them through
# CAPABILITY_SCOPED_ROUTERS (main.py:275). Verified: main is the only shared
# module that imports routers today, so this contract passes on the current tree
# with no ignores.
# Contract 9 — Shared API modules must not import routers
[[tool.importlinter.contracts]]
name = "Shared API modules must not import routers"
type = "forbidden"
source_modules = [
    "smartmatch_api.dependencies",
    "smartmatch_api.errors",
    "smartmatch_api.units",
    "smartmatch_api.config",
    "smartmatch_api.commands",
    "smartmatch_api.job_authz",
    "smartmatch_api.utils",
    "smartmatch_api.match_run_evidence",
    "smartmatch_api.pipeline_provisioning",
    "smartmatch_api.zip_proximity",
]
forbidden_modules = [
    "smartmatch_api.routers",
]
```

Five new contracts — numbers 5–9 in the table above:

5. `The API sits above the inner packages, never beneath them`
6. `The worker sits above the inner packages, never beneath them`
7. `The API and the worker are independent services`
8. `Routers are independent of one another`
9. `Shared API modules must not import routers`

plus the `root_packages` extension itself, which is not a contract, takes no
number, and is the change that makes contracts 5–9 possible.

**After M1 renames `utils.py` to `clock.py` (R-19),
`smartmatch_api.utils` in the last contract becomes `smartmatch_api.clock`.**
Whichever of M1 and M2 lands second carries that one-line edit.

---

## 4. The manifest rule

**R-05, AP-01.** A contract on imports is worth less if the packaging manifest
disagrees with it. `services/api/pyproject.toml` and
`services/worker/pyproject.toml` must both add `smartmatch-persistence` to
`dependencies` — the API imports it in 33 files, the worker in 10, and neither
declares it.

This is not a lint-imports concern; import-linter reads source, not manifests.
The gate is a test:

> **Test idea — `tests/unit/test_service_manifests_declare_imports.py`.** For each
> of `services/api` and `services/worker`: parse `pyproject.toml`
> (`tomllib.load`), walk every `.py` file under the declared wheel package
> (`[tool.hatch.build.targets.wheel].packages`), collect the top-level
> `smartmatch_*` module names imported via `ast.parse` (`ast.Import` and
> `ast.ImportFrom` at any depth, module-level and nested), map each to its
> distribution name (`smartmatch_persistence` → `smartmatch-persistence`), and
> assert that set is a subset of the manifest's `dependencies`. Assert the
> converse too — a declared dependency nobody imports is also a lie about the
> graph, and it is how `smartmatch-providers` would linger in a manifest after
> the last import went away.

The test is cheap, has no database, and fails loudly the first time someone adds
an import without a declaration — which is the exact event that today produces a
broken wheel months later.

---

## 5. How to verify locally, and how to prove the contract bites

```
make imports          # PYTHONPATH="$(DOMAIN_PATH)" lint-imports --config pyproject.toml
```

After DR-1, `DOMAIN_PATH` (`Makefile:11`) must include `services/api` and
`services/worker`; `verify.yml:104` runs the identical command and needs the same
edit. Run the whole gate set with `make check`
(`format-check lint typecheck imports test scan memory licenses infra-check`) —
a docs-only change must keep it green, and a contract change must be run under
`make imports` before it is committed.

**OBSERVED (2026-09-08) — the block above was executed, not just written.** Run
against the tree with both service packages on the path:

```
PYTHONPATH="python/smartmatch_domain:python/smartmatch_authz:python/smartmatch_providers:python/smartmatch_persistence:services/api:services/worker" \
  lint-imports --config <the block in §3>
```

Result: `Contracts: 9 kept, 0 broken`. Re-run with the two `ignore_imports`
entries deleted, exactly one contract fails —
`Routers are independent of one another BROKEN` — and it names exactly
`outreach_contacts` → `outreach` and `cba_contact_channels` → `cba_contacts`;
every other contract stays KEPT. So §3 is paste-ready in fact rather than in
intent, and the two exceptions are the whole of the debt.

**Proving a contract bites — the ADR-0002 trick.**
`ADR-0002-package-boundaries.md:56` records the method and it is the standard to
meet: *"Verified by deliberately adding `import os` to a domain module: the
contract reported `BROKEN`. Anyone can repeat this in ten seconds."*

A new contract is not landed until the same has been done to it:

| # | Contract | Temporary edit that must report `BROKEN` |
|---|---|---|
| 5 | `The API sits above the inner packages, never beneath them` | add `import smartmatch_api.errors` to `python/smartmatch_persistence/.../jobs.py` |
| 6 | `The worker sits above the inner packages, never beneath them` | add `import smartmatch_worker` to `python/smartmatch_persistence/.../jobs.py` |
| 7 | `The API and the worker are independent services` | add `import smartmatch_worker.handlers` to `services/api/smartmatch_api/main.py` |
| 8 | `Routers are independent of one another` | add `from smartmatch_api.routers import units as _u` to any router not on the ignore list |
| 9 | `Shared API modules must not import routers` | add `from smartmatch_api.routers import jobs` to `services/api/smartmatch_api/errors.py` |

Revert each edit immediately; record the result in the M2 change description.
A contract that has never reported `BROKEN` is an untested assertion, and this
repository's position (`tests/unit/test_forbidden_scanner.py`, its docstring:
*"a gate nobody has verified is worse than no gate"*) already applies that
standard to the scanner. It applies here.

---

## 6. Rollback

Every contract in §3 is one `[[tool.importlinter.contracts]]` block in one file.
**Removing the block is the rollback** — no code moves, no import changes, no
migration. The `root_packages` extension rolls back by deleting two list entries
and the two `PYTHONPATH` segments; because contracts 1–4 name only the four
`python/` packages, they are unaffected either way.

M2 is therefore two independently reversible steps, in this order:

1. **Land the contracts with the two `ignore_imports` lines.** Nothing in
   `services/` changes. If anything is wrong, delete the blocks.
2. **Promote the two authz helpers and delete the two `ignore_imports` lines.**
   Code moves; the contract is already in place to catch the move going wrong.
   If the promotion is wrong, revert the code commit — step 1's contract still
   passes with the ignores restored.

Doing it in the other order — promoting first — leaves the window where the new
owned module exists and nothing prevents a third router from bypassing it.
