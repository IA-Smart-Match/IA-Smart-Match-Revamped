# Engine-wide `hide_parameters` Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Date:** 2026-09-19
**Owner decision (Danny Tran, Development Lead, 2026-09-19, verbatim):**

> "yes, env-switchable. Have the subagent record it all applicable docs & create
> an implementation plans to then fix all tests/modules affected by the changes"

**Goal:** Turn on SQLAlchemy `hide_parameters=True` for every engine the shared
factory builds, default ON, switchable OFF by one environment variable
(`SMARTMATCH_DB_HIDE_PARAMETERS`), so a failed write's exception text can never
carry bound values.

**Architecture:** One reader in
`python/smartmatch_persistence/smartmatch_persistence/engine.py`, beside the
existing `SMARTMATCH_DB_POOL_*` readers, passed into `create_engine`. No
service settings object learns about it — this package is shared by the API,
the worker and `tools/`, and each has its own (or no) settings object. The
Alembic environment reads the same helper so an operator-run migration is
covered by the same switch.

**Tech Stack:** Python 3.12, SQLAlchemy 2.0.52, Alembic, pytest, PostgreSQL 16.

---

## Why

A failed write raises `sqlalchemy.exc.DBAPIError`, whose `str()` is the
statement **plus** `[parameters: {...}]` — every bound value of every row.

- **Class exercise (ADR-0025 D6).** That text carries the withheld column
  `hidden_true_interests`. Found on PR #179; found again on PR #184, where
  three deletes in `instructor_repository.reset_team_rows` had bypassed the
  per-repository scrubber. Per-repository scrubbing is correct but is a
  discipline: it is one `session.execute` away from being wrong again.
- **CBA.** The same text carries real emails, names and invitation tokens into
  the server log.

The engine flag closes the door once, for every repository, including the ones
nobody has written a scrubber for (`workspace_repository`, and every CBA
repository). The per-repository scrubbers **stay** as a second layer: they also
null the exception's `__context__`, which the flag does not do.

## Scope

**In scope.** `engine.py` (one env-read + one `create_engine` keyword),
`db/migrations/env.py` (the same keyword on `engine_from_config`), the two
scrubber modules' comments that promised this as a follow-up, the env-var
reference, the operations docs, a dated non-amending note on ADR-0025 D6, and
tests for the flag.

**Out of scope, explicitly.** Pool settings, session settings, any query, any
migration, any contract. `services/api/smartmatch_api/config.py`, `main.py`,
`exercise_dependencies.py`, `pyproject.toml` import contracts,
`tests/authz/test_policy_matrix.py`, `routes.tsx`, and everything under
`routers/exercise_*` and `smartmatch_persistence/exercise/` except
comment/docstring updates in the scrubber modules — all owned by in-flight
tracks. `factor_registry.py` and its tests. Every gated item.

## What the flag changes, verified against SQLAlchemy 2.0.52

Read from the installed source rather than assumed:

| Site | Effect with `hide_parameters=True` |
|---|---|
| `sqlalchemy/exc.py:525` | `StatementError.__str__` prints `[SQL parameters hidden due to hide_parameters=True]` in place of `[parameters: …]`. The statement and the error class are unchanged. |
| `sqlalchemy/engine/base.py:1905,2100` | The `echo=True` / `sqlalchemy.engine` logger prints `[SQL parameters hidden due to hide_parameters=True]` instead of the parameter tuple. **So `echo=True` is covered too** — it is not a way around the flag. |
| `sqlalchemy/engine/base.py:2405` | The flag is carried from the engine onto every `DBAPIError` the engine raises. |

Not changed: the SQL text, `exc.orig` (the driver's own exception, and thus
`exc.orig.diag.constraint_name`), the exception class, or `exc.params`, which
remains reachable in a debugger. This is an error/log **text** change only.

## Recon inventory

### Engines: which inherit the flag

| File:line | Builder | Covered? | Action |
|---|---|---|---|
| `python/smartmatch_persistence/smartmatch_persistence/engine.py:109` | `create_engine` inside `create_db_engine` | **yes — the change** | Pass `hide_parameters=`. |
| `python/smartmatch_persistence/smartmatch_persistence/engine.py:126` | `create_session_factory` → `create_db_engine` | yes, transitively | None. |
| `services/api/smartmatch_api/main.py:227` | `create_session_factory` | yes | None. API request path is covered. |
| `services/worker/smartmatch_worker/main.py:392` | `create_session_factory` | yes | None. Worker path is covered. |
| `tools/seed_pilot.py:307`, `seed_pilot_review.py:213`, `seed_pilot_principals.py:192`, `seed_pilot_rewards.py:262`, `seed_pilot_logins.py:342` | `create_db_engine` | yes | None. |
| `tools/seed_demo_pipeline.py:347`, `generate_pilot_dataset.py:2944`, `seed_pilot_engagement.py:1075`, `seed_pilot_student_feedback.py:1074`, `verify_pilot_dataset.py:1626` | `create_session_factory` | yes | None. |
| `db/migrations/env.py:69` | `engine_from_config` | **no** | Pass the same resolved value. Migrations run data backfills with bound values; an operator-run migrate container logging them is the same leak. |
| `tests/integration/conftest.py:231` and ~30 sibling `create_engine(DATABASE_URL, future=True)` fixtures in `tests/contract/**` and `tests/integration/**` | bare `create_engine` | **no** | Leave as they are. A test engine is a developer's debugging surface, and an integration test that asserts on constraint text should keep seeing everything. This is the main reason the blast radius on the suite is nil. |
| `tests/integration/migration_harness.py:86,184` | bare `create_engine` (admin / scratch) | no | Leave. |
| `tests/integration/test_job_lease_lifecycle.py:73`, `test_principal_identity.py:274,381,414` | bare `create_engine` | no | Leave. |
| `tests/**` sites calling `create_session_factory(...)` to bind `app.state.session_factory` (~40) | shared factory | **yes** | No change needed — none of them asserts on parameter text (see below). |

### Text the flag could break

| File:line | What it is | Impact | Action |
|---|---|---|---|
| `python/smartmatch_persistence/smartmatch_persistence/spend.py:350` | `getattr(exc.orig, "diag", None)` → `constraint_name` | none — `exc.orig` is untouched | None. |
| `python/smartmatch_persistence/smartmatch_persistence/spend.py:354` | `_WORK_KEY_UNIQUE_CONSTRAINT in str(exc.orig)` | none — `str(exc.orig)` is the **driver's** text, not SQLAlchemy's wrapper | None. Documented in the plan so a future reader does not "fix" it. |
| `tests/integration/migration_harness.py:93,97,134` | `exc.orig.sqlstate` / `{exc.orig}` | none, same reason; and the harness builds its own engine | None. |
| `services/api/.../routers/host_organizations.py:541`, `manual_events.py:346,451` | `except IntegrityError` → worded `ApiError` | none — the driver text is never rendered into the response | None. |
| `tests/unit/test_seed_pilot.py:152` | `statement.compile().params["role"]` | none — a Core compile, no engine involved | None. |
| Every `caplog` assertion found in `tests/integration/**` | asserts on the repository's own worded log lines | none — no test asserts that a bound value **appears** in error text | None. |

No test in the repository asserts that a parameter value is present in a
`DBAPIError`'s rendering. Consequently **no existing assertion is weakened or
rewritten by this change.** The inventory above is the evidence for that claim.

### Comments and docs that record this as a follow-up

| File:line | Action |
|---|---|
| `python/.../exercise/dataset_repository.py:125` — "A related follow-up is recorded on this pull request rather than done here: setting `hide_parameters=True` on the engine would close the same door…" | Rewrite to say the engine flag now exists, names the env var, and that this scrubber stays as the second layer (it also nulls `__context__`, which the flag does not). |
| `python/.../exercise/dataset_repository.py:344` (comment) | Add half a sentence: the engine flag is the first layer. |
| `python/.../exercise/instructor_repository.py:100,518,691` | Same note; the `[parameters: …]` wording stays because it is what the flag suppresses. |
| `python/.../exercise/workspace_repository.py` (`reset_team`) | Note that this module deliberately lets the driver exception reach its caller, and that the engine flag now means that exception carries no values. |

### Environment plumbing

| File | Today | Action |
|---|---|---|
| `.env.example:60-77` | A "Connection pool" block listing `SMARTMATCH_DB_POOL_SIZE` / `_MAX_OVERFLOW` / `_POOL_TIMEOUT` | Add a new block for `SMARTMATCH_DB_HIDE_PARAMETERS` with the default and the "never on a shared deployment" warning. |
| `docker-compose.yml:438-440,509-511` | Passes the three pool vars through to `api` and `worker` | Add `SMARTMATCH_DB_HIDE_PARAMETERS: ${SMARTMATCH_DB_HIDE_PARAMETERS:-}` to both. Empty = unset = default (hidden). |
| `docs/operations/vm-deploy.md` | VM operating instructions | Add the var to the operating notes: never set it false on the VM. |
| `docs/operations/deploy-runbook.md` | "When a revision fails part-way" | Add a note: a migration failure no longer prints bound values; how to get them back for a local reproduction. |
| `docs/operations/local-dev-walkthrough.md` | Local loop | Add the one-line local-debugging escape hatch. |
| `docs/architecture/decisions/ADR-0025-…md` §D6 | Decision text | **Dated note only**, in the blockquote style D5 already uses for a factual note. No decision text, status or date changes. |
| `docs/plans/README.md` | Navigation authority | Add this plan to the class-exercise row, since it is the record of a decision taken for D6. |
| `docs/architecture/decisions/adr-backlog.md` | Ideas not yet ADRs | Record "error text never carries bound values" as a candidate ADR. It is a repository-wide invariant, wider than the one owner decision quoted above, so it is **recorded, not decided**. |

## Tasks

### Task 1: Write the plan (this file) and commit it before any code change

- [ ] **Step 1:** `git add docs/superpowers/plans/2026-09-19-engine-hide-parameters-plan.md` and commit.

### Task 2: RED — unit tests for the flag

**Files:** Modify `tests/unit/test_db_engine_pool.py`.

- [ ] **Step 1:** Add `SMARTMATCH_DB_HIDE_PARAMETERS` to `_ENV_VARS` so the
      autouse fixture clears it.
- [ ] **Step 2:** Add four cases:
      - default (unset) → `resolve_hide_parameters() is True` and
        `create_db_engine(_URL).hide_parameters is True`;
      - `"false"` / `"0"` / `"no"` / `"off"` → `False`, and the engine agrees;
      - `"true"` / `"1"` / `"yes"` / `"on"` → `True`;
      - garbage (`"maybe"`) → `True` **and** a `WARNING` on the module logger
        (fail closed, never silently expose).
- [ ] **Step 3:** Run them; expect FAIL (`ImportError` / `AttributeError`).

```bash
.venv/bin/pytest tests/unit/test_db_engine_pool.py -q
```

### Task 3: GREEN — `engine.py`

**Files:** Modify `python/smartmatch_persistence/smartmatch_persistence/engine.py`.

- [ ] **Step 1:** Add `DEFAULT_HIDE_PARAMETERS: bool = True` with a docstring
      stating the privacy reason and the ADR-0025 D6 / CBA motivations.
- [ ] **Step 2:** Add `_bool_from_env(name, default)`. There is **no existing
      bool-env helper in the repository** (verified by grep), so this is the
      first, not a second parser. Spellings: `1/true/yes/on` and
      `0/false/no/off`, case-insensitive, whitespace-stripped.
      **It does not raise** — unlike `_int_from_env`, which raises because a
      mistyped pool size must stop the boot. Here the two failure modes are not
      symmetric: refusing to boot over a typo is worse than the typo, and
      falling back to the *permissive* value would publish data. So it logs a
      `WARNING` naming the variable and the bad value and returns the default,
      which for this variable is "hidden".
- [ ] **Step 3:** Add `resolve_hide_parameters() -> bool`, exported in
      `__all__`, next to `resolve_pool_settings`.
- [ ] **Step 4:** Pass `hide_parameters=resolve_hide_parameters()` in
      `create_db_engine`, and document in its docstring that this also covers
      `echo=True` output (base.py:1905/2100, verified above).
- [ ] **Step 5:** Re-run Task 2's command; expect PASS.

### Task 4: RED→GREEN — an integration test that proves the switch is real

**Files:** Create
`tests/integration/test_engine_hide_parameters.py`.

- [ ] **Step 1:** Against the standing PostgreSQL, build an engine with
      `create_db_engine` and force a failing `INSERT` that binds a distinctive
      sentinel value into a table with a CHECK or NOT NULL it violates. Use a
      scratch table created and dropped by the test, so the test owns its
      schema and asserts nothing about the product schema.
- [ ] **Step 2:** Assert, with the flag on (default):
      - `str(exc)` contains the constraint name;
      - `str(exc)` does **not** contain the sentinel;
      - `str(exc)` contains `hide_parameters=True`;
      - the captured `sqlalchemy.engine` log does not contain the sentinel;
      - `type(exc)` is still `IntegrityError` — the class did not change.
- [ ] **Step 3:** Assert, with `SMARTMATCH_DB_HIDE_PARAMETERS=false`, that the
      sentinel **does** appear. Without this the first assertion could pass for
      the wrong reason (a sentinel the statement never bound).
- [ ] **Step 4:** The sentinel is a neutral string. **`hidden_true_interests`
      is not named in this file**, in any log line it produces, or in any test
      output it can print.

```bash
.venv/bin/pytest tests/integration/test_engine_hide_parameters.py -q
```

### Task 5: Alembic

**Files:** Modify `db/migrations/env.py`.

- [ ] **Step 1:** Import `resolve_hide_parameters` from
      `smartmatch_persistence.engine` (the package is installed in the venv the
      `alembic` entry point runs from, and in the migrate container image) and
      pass it to `engine_from_config`.
- [ ] **Step 2:** Verify with a scratch database: `alembic upgrade head` still
      reaches `0037`.

### Task 6: Scrubber comments

- [ ] Update the four comment sites in the inventory. Comments and docstrings
      only — no code, no signature, no behaviour, in modules owned by other
      in-flight tracks.

### Task 7: Docs

- [ ] `.env.example`, `docker-compose.yml`, `docs/operations/vm-deploy.md`,
      `docs/operations/deploy-runbook.md`,
      `docs/operations/local-dev-walkthrough.md`,
      ADR-0025 D6 dated note, `docs/plans/README.md`,
      `docs/architecture/decisions/adr-backlog.md`.

### Task 8: Gates

```bash
make scan VENV=<parent>/.venv
make imports VENV=<parent>/.venv
make openapi-check VENV=<parent>/.venv   # must still report 83 ops
<parent>/.venv/bin/ruff check <changed paths>
<parent>/.venv/bin/mypy --cache-dir ~/.cache/mypy-engine-hide python/smartmatch_persistence
```

## Risks

1. **Harder CBA debugging.** An operator reading a 500 in the API log sees the
   statement and the constraint but not the values. Mitigated by: the
   constraint name is what identifies the fault; `exc.orig.diag` still carries
   the server's own detail; the database's log has the statement; and the env
   var turns it off for a local reproduction. Accepted deliberately — the
   values are exactly what must not be in a shared log.
2. **Self-built engines are not covered.** Every `create_engine(...)` outside
   `create_db_engine` keeps rendering parameters. Today those are all test
   fixtures and the migration harness, which is the intended outcome, but a
   future production module that builds its own engine would silently opt out.
   Recorded in `adr-backlog.md` as the reason the invariant may deserve an ADR
   and an import/lint gate.
3. **Someone turns it off on a shared deployment.** The var is documented with
   an explicit "never on a shared/VM deployment" line in three places, and
   compose passes it through empty by default.
4. **A future test asserts on parameter text.** It would fail loudly against
   the shared factory, and the failure names `hide_parameters=True`, which is a
   self-explaining message.

## Rollback

Set `SMARTMATCH_DB_HIDE_PARAMETERS=false` in the deployment's environment and
restart. No migration, no schema change, no contract change, so there is
nothing to revert in the database. Reverting the commit is equally safe.

## Verification

```bash
.venv/bin/pytest tests/unit/test_db_engine_pool.py -q
.venv/bin/pytest tests/integration/test_engine_hide_parameters.py -q
.venv/bin/pytest tests/integration/test_exercise_dataset_repository.py \
                tests/integration/test_exercise_instructor_persistence.py -q
make scan && make imports && make openapi-check   # 83 ops, migration head 0037
```

---

## Execution addendum, 19 September 2026

Written after the tasks above ran. The plan is preserved as it was written;
this records where reality differed from it.

### The flag is narrower than this plan assumed

Task 4 was written expecting a CHECK-violating insert to prove the sentinel
absent. It did not, and the failure is the most useful thing this change
produced:

```
(psycopg.errors.CheckViolation) new row for relation "…" violates check constraint "…"
DETAIL:  Failing row contains (1, sentinel-value-b027cc…).
[SQL: INSERT INTO … VALUES (%(id)s::INTEGER, %(label)s::VARCHAR)]
[SQL parameters hidden due to hide_parameters=True]
```

SQLAlchemy's rendering is suppressed exactly as intended. **PostgreSQL's own
`DETAIL:` line is not**, because it arrives composed inside `exc.orig`, below
the layer the flag operates on. For a CHECK or NOT NULL refusal that line is
the whole failing row. For a unique or foreign-key refusal it is the key only.

Consequences, all carried into the change rather than left here:

1. The probe was rebuilt around a primary-key refusal, where `DETAIL` names
   only the key, so the sentinel's absence is attributable to the flag.
2. `test_the_servers_own_detail_line_is_not_covered` asserts the limitation, so
   it is discovered by a test rather than in a log, and fails loudly if a future
   driver or server setting ever makes it suppressible.
3. Every docstring this change touched says "floor, not ceiling" explicitly.
   The per-repository scrubbers are not redundant and must not be removed on
   the strength of this flag.
4. `adr-backlog.md` **B-11** records the wider invariant, unresolved, with the
   survey it would need. It is not decided here: the owner decision quoted at
   the top of this plan is about the switch, not about a repository-wide gate.

### Other differences

- **No assertion was weakened or rewritten.** The inventory's prediction held:
  no test in the repository asserts that a bound value appears in a
  `DBAPIError`'s rendering, and the integration fixtures build their own
  engines, so the shared-factory change does not reach them.
- **Alembic was covered**, as planned. `db/migrations/env.py` imports the
  resolver; `alembic upgrade head` against a scratch database still reaches
  `0037_exercise_tables`. Note for anyone running the suite from a **git
  worktree**: `migration_harness.py` shells out to `alembic`, which resolves
  `smartmatch_persistence` through the venv's editable install — i.e. the
  *parent* checkout. Run those tests with the worktree's package directory on
  `PYTHONPATH`, or the import fails for reasons that have nothing to do with the
  change.
- **`_bool_from_env` is genuinely the first** of its kind here. A grep for an
  existing boolean environment reader across `python/`, `services/`, `tools/`
  and `db/` found none; the only prior art is `_int_from_env` in the same
  module, which raises, and the addendum in that function's docstring explains
  why this one deliberately does not.
