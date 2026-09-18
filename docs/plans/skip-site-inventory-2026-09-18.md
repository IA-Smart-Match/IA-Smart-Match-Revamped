# Skip / skipif / xfail site inventory — 2026-09-18

**Inventory — dated snapshot, docs only. Authorizes no code change. Not
machine-checked; will drift.**

**Base:** `origin/main`. **Survey date:** 2026-09-18.

This answers the `skip-inventory-audit` track proposed in
[`todo-disposition-register.md`](todo-disposition-register.md) §6. That register
sampled the skip sites and said so; this file reads every one of them. It
recommends nothing, changes no test, opens and closes no register row, and makes
no production-readiness claim.

---

## 1. The survey command and its raw count

```
git grep -nE "pytest\.(mark\.)?(skip|skipif|xfail)" -- .   →  83
```

Per top-level directory: `tests/` **75**, `docs/` **7**, `Makefile` **1**.
Within `tests/`: `tests/e2e` **35**, `tests/contract` **30**,
`tests/integration` **6**, `tests/unit` **4**.

The `docs/` (7) and `Makefile` (1) hits are prose *about* skips, not skip sites.
Three of the 75 `tests/` hits are likewise prose — two module docstrings and one
comment. All eleven are listed in §6, so that **83 = 72 call sites + 11 prose
lines** is checkable rather than asserted. **Real call sites: 72.**

A count of call sites is **not** a count of tests skipped in a CI run. One site
can skip many parametrised cases; one `skipif` can skip none; a site inside a
session- or module-scoped fixture takes the whole module with it. `pytest -ra`
would report a different number again.

## 2. What the classes mean

| Class | Meaning |
|---|---|
| **environment-conditional** | The guard asks the machine a question — is PostgreSQL reachable, is it migrated far enough, is a compose appliance up, does this platform have `git`/`flock`/symlinks. |
| **predecessor-conditional** | An `e2e` step whose earlier step in the chain did not produce the state it needs. The guard reports the missing predecessor by name rather than asserting a fake success. |
| **unconditional skip** | Fires on every run, or on a condition internal to the repository rather than to the machine. |
| **xfail** | A `pytest.mark.xfail` marker. |

## 3. What CI does, and therefore what "runs in CI" means here

Read from `.github/workflows/verify.yml` and `.github/workflows/build.yml`:

- **PostgreSQL** is provided by the `python` job in `verify.yml` — a
  `postgres:16` service on `localhost:5432` with
  `SMARTMATCH_DATABASE_URL=postgresql+psycopg://smartmatch:smartmatch@localhost:5432/smartmatch`.
  That job runs `cd db && alembic upgrade head` **before** the test step, so the
  database is migrated to head, not merely reachable.
- That job's test step is `pytest tests/ -m "not e2e"`, so `tests/e2e` is
  **excluded** from `verify.yml` by design (its own comment explains why).
- **e2e** is run by the `pilot-e2e` job in `build.yml`, which does
  `docker compose up --build -d` and then `make e2e PYTEST=pytest`. The
  `Makefile` target passes `-ra`, so every skip is printed in the summary.
- Both runners are `ubuntu-24.04`, which provides `git`, `flock` and symlink
  creation. `greenlet==3.5.5` is pinned in `requirements/dev.txt`, which CI
  installs with `--require-hashes`.

So "**yes**" in the last column means: a CI job runs this test and the
environment that job provides satisfies the guard, so the body executes. For a
predecessor-conditional e2e guard, "yes" means the `pilot-e2e` job runs the step
and the guard fires only if the named earlier step failed to produce its state —
i.e. it is a failure-propagation guard, not a standing skip.

---

## 4. Inventory

### 4.1 `tests/contract` — 30 sites

Every one is the same shape: a module- or session-scoped `engine` fixture that
probes the database and skips the whole module if the probe fails. The `python`
job provides a migrated PostgreSQL, so all thirty **run** in CI.

| file:line | kind | condition / reason (verbatim) | class | runs in CI |
|---|---|---|---|---|
| `tests/contract/test_attendance_api.py:72` | `skip` | `f"no migrated PostgreSQL available at {DATABASE_URL}: {exc}"` (probe: `SELECT 1 FROM attendance_record LIMIT 1`) | environment-conditional | yes |
| `tests/contract/test_calendar_ics.py:76` | `skip` | `f"no migrated PostgreSQL available at {DATABASE_URL}: {exc}"` (probe: `SELECT ends_at FROM event LIMIT 1`) | environment-conditional | yes |
| `tests/contract/test_cba_contact_create_idempotency.py:106` | `skip` | `f"database at {DATABASE_URL} is not migrated to 0030"` (index `ix_speaker_profile_unit_folded_name` absent) | environment-conditional | yes |
| `tests/contract/test_cba_contact_create_idempotency.py:108` | `skip` | `f"no PostgreSQL migrated to 0030 at {DATABASE_URL}: {exc}"` | environment-conditional | yes |
| `tests/contract/test_cba_contact_duplicate_hint.py:85` | `skip` | `f"database at {DATABASE_URL} is not migrated to 0030"` | environment-conditional | yes |
| `tests/contract/test_cba_contact_duplicate_hint.py:87` | `skip` | `f"no PostgreSQL migrated to 0030 at {DATABASE_URL}: {exc}"` | environment-conditional | yes |
| `tests/contract/test_cba_contact_rename_hint.py:94` | `skip` | `f"database at {DATABASE_URL} is not migrated to 0030"` | environment-conditional | yes |
| `tests/contract/test_cba_contact_rename_hint.py:96` | `skip` | `f"no PostgreSQL migrated to 0030 at {DATABASE_URL}: {exc}"` | environment-conditional | yes |
| `tests/contract/test_cba_contacts_api.py:99` | `skip` | `f"no PostgreSQL migrated to 0025 at {DATABASE_URL}: {exc}"` (probe: `SELECT full_name FROM speaker_profile LIMIT 1`) | environment-conditional | yes |
| `tests/contract/test_cba_invitations_api.py:258` | `skip` | `f"no migrated PostgreSQL available at {DATABASE_URL}: {exc}"` (probe: `cba_invitation`) | environment-conditional | yes |
| `tests/contract/test_contact_lifecycle_api.py:221` | `skip` | `f"no migrated PostgreSQL available at {DATABASE_URL}: {exc}"` (probes `speaker_profile.full_name` **and** `contact_channel_transition`) | environment-conditional | yes |
| `tests/contract/test_engagement_api.py:77` | `skip` | `f"no migrated PostgreSQL available at {DATABASE_URL}: {exc}"` (probe: `attendance_record`) | environment-conditional | yes |
| `tests/contract/test_events_api.py:72` | `skip` | `f"no migrated PostgreSQL available at {DATABASE_URL}: {exc}"` (probe: `event`) | environment-conditional | yes |
| `tests/contract/test_host_organizations_api.py:88` | `skip` | `f"no migrated PostgreSQL available at {DATABASE_URL}: {exc}"` (probe: `host_organization`) | environment-conditional | yes |
| `tests/contract/test_manual_events_api.py:52` | `skip` | `f"no migrated PostgreSQL available at {DATABASE_URL}: {exc}"` (probe: `event_manual_detail`) | environment-conditional | yes |
| `tests/contract/test_match_runs_api.py:118` | `skip` | `f"no migrated PostgreSQL available at {DATABASE_URL}: {exc}"` (probes `match_run` and `speaker_profile`) | environment-conditional | yes |
| `tests/contract/test_matching_weights_api.py:70` | `skip` | `f"no migrated PostgreSQL available at {DATABASE_URL}: {exc}"` (probe: `match_weight_setting`) | environment-conditional | yes |
| `tests/contract/test_me.py:54` | `skip` | `f"no PostgreSQL available at {DATABASE_URL}: {exc}"` (probe: `SELECT 1`) | environment-conditional | yes |
| `tests/contract/test_me_suspended.py:51` | `skip` | `f"no PostgreSQL available at {DATABASE_URL}: {exc}"` (probe: `SELECT 1`) | environment-conditional | yes |
| `tests/contract/test_meetings_api.py:84` | `skip` | `f"no migrated PostgreSQL available at {DATABASE_URL}: {exc}"` (probe: `cba_meeting`) | environment-conditional | yes |
| `tests/contract/test_metrics.py:44` | `skip` | `f"no migrated PostgreSQL available at {DATABASE_URL}: {exc}"` (probe: `review_item`) | environment-conditional | yes |
| `tests/contract/test_outreach.py:197` | `skip` | `f"no migrated PostgreSQL available at {DATABASE_URL}: {exc}"` (probe: `outreach_draft`) | environment-conditional | yes |
| `tests/contract/test_outreach_contacts.py:127` | `skip` | `f"no migrated PostgreSQL available at {DATABASE_URL}: {exc}"` (probe: `contact_channel_transition`) | environment-conditional | yes |
| `tests/contract/test_pipeline_stages.py:136` | `skip` | `f"no migrated PostgreSQL available at {DATABASE_URL}: {exc}"` (probe: `pipeline_record`) | environment-conditional | yes |
| `tests/contract/test_portals_api.py:68` | `skip` | `f"no PostgreSQL available at {DATABASE_URL}: {exc}"` (probe: `SELECT 1`) | environment-conditional | yes |
| `tests/contract/test_review_decision.py:73` | `skip` | `f"no migrated PostgreSQL available at {DATABASE_URL}: {exc}"` (probe: `review_item`) | environment-conditional | yes |
| `tests/contract/test_review_item_list.py:84` | `skip` | `f"no migrated PostgreSQL available at {DATABASE_URL}: {exc}"` (probe: `review_item`) | environment-conditional | yes |
| `tests/contract/test_speaker_pipeline_api.py:189` | `skip` | `f"no migrated PostgreSQL available at {DATABASE_URL}: {exc}"` (probe: `pipeline_record`) | environment-conditional | yes |
| `tests/contract/test_speaker_requests_api.py:84` | `skip` | `f"no migrated PostgreSQL available at {DATABASE_URL}: {exc}"` (probe: `speaker_request_classification`) | environment-conditional | yes |
| `tests/contract/test_student_events_api.py:90` | `skip` | `f"no migrated PostgreSQL available at {DATABASE_URL}: {exc}"` (probe: `SELECT ends_at FROM event LIMIT 1`) | environment-conditional | yes |

### 4.2 `tests/integration` — 5 sites (6 grep hits; one is a comment)

| file:line | kind | condition / reason (verbatim) | class | runs in CI |
|---|---|---|---|---|
| `tests/integration/conftest.py:203` | `skip` | `f"no PostgreSQL available at {DATABASE_URL}: {exc}"` — session-scoped `engine` fixture, so this takes every test that depends on it | environment-conditional | yes |
| `tests/integration/migration_harness.py:95` | `skip` | `f"{engine.url.username} lacks the privilege to create a database, so this migration cannot be exercised here: {exc.orig}"` — fires only on SQLSTATE `INSUFFICIENT_PRIVILEGE` from `CREATE DATABASE` | environment-conditional | yes — the service's `POSTGRES_USER: smartmatch` is the database's own superuser-equivalent owner created by the `postgres:16` image, so `CREATE DATABASE` is permitted. Not machine-checked here |
| `tests/integration/test_contact_lifecycle.py:204` | `skip` | `f"no migrated PostgreSQL available at {DATABASE_URL}: {exc}"` (probes `speaker_profile.full_name` and `contact_channel_transition`) | environment-conditional | yes |
| `tests/integration/test_rewards_api.py:202` | `skip` | `f"no migrated PostgreSQL available at {DATABASE_URL}: {exc}"` (probe: `redemption`) | environment-conditional | yes |
| `tests/integration/test_tenant_isolation.py:44` | `skip` | `f"no PostgreSQL available at {DATABASE_URL}: {exc}"` (probe: `SELECT 1`) | environment-conditional | yes |

### 4.3 `tests/unit` — 4 sites

| file:line | kind | condition / reason (verbatim) | class | runs in CI |
|---|---|---|---|---|
| `tests/unit/test_env_isolation_check.py:132` | `skip` | `f"{key} is null in the environment used for this comparison"` — inside a `@pytest.mark.parametrize` over `IDENTIFIER_KEYS`, guarded by `if value is None` where `value = _env("prod").values[key]` | unconditional skip (repository-data-conditional, not environment-conditional) | **cannot tell from the repo** — see §5 |
| `tests/unit/test_fixture_ingest.py:232` | `skip` | `"symlink creation is not permitted in this environment"` — on `OSError`/`NotImplementedError` from `link.symlink_to(secret)` | environment-conditional | yes — `ubuntu-24.04` permits symlinks |
| `tests/unit/test_supply_chain.py:413` | `skip` | `"greenlet is not installed here"` — when the built SBOM component carries no `licenses` key | environment-conditional | yes — `greenlet==3.5.5` is pinned in `requirements/dev.txt`, which CI installs |
| `tests/unit/test_vm_deploy_script.py:38` | `skipif` (module-level `pytestmark`) | `shutil.which("git") is None or shutil.which("flock") is None`, reason `"the deployment script needs git and flock, which this platform lacks"` | environment-conditional | yes — `ubuntu-24.04` provides both |

### 4.4 `tests/e2e` — 33 sites (35 grep hits; two are prose)

`tests/e2e` is excluded from `verify.yml` (`pytest -m "not e2e"`) and is run by
`build.yml`'s `pilot-e2e` job behind `docker compose up --build -d`.

| file:line | kind | condition / reason (verbatim) | class | runs in CI |
|---|---|---|---|---|
| `tests/e2e/conftest.py:209` | `skip(allow_module_level=True)` | `f"no compose appliance answering at {API_BASE}/api/health after {READY_ATTEMPTS} attempts; run 'docker compose up --build -d' first (see INSTALL.md §4)"` | environment-conditional | yes — `pilot-e2e` brings the stack up first |
| `tests/e2e/conftest.py:226` | `skip(allow_module_level=True)` | `"the seed-review one-shot is '{state}' and never finished; 'docker compose logs seed-review' shows what it is waiting on"` | environment-conditional | yes |
| `tests/e2e/test_pilot_clickthrough.py:450` | `skip` | `"match scoring is unavailable: the API answered 503 registry_not_ready, so the factor registry is not approved or not fully implemented on this appliance — …"` | environment-conditional (appliance state) | yes — `factor_registry.REGISTRY_STATUS == "approved"`, so the guard is not expected to fire; whether the appliance answers 503 is a runtime fact this file does not check |
| `tests/e2e/test_pilot_clickthrough.py:552` | `skip` | `"step 02 did not resolve a unit id from GET /v1/me"` | predecessor-conditional | yes (guard fires only if step 02 failed) |
| `tests/e2e/test_pilot_clickthrough.py:664` | `skip` | `"step 02 did not resolve a unit id from GET /v1/me"` | predecessor-conditional | yes |
| `tests/e2e/test_pilot_clickthrough.py:712` | `skip` | `"step 02 did not resolve a unit id from GET /v1/me"` | predecessor-conditional | yes |
| `tests/e2e/test_pilot_clickthrough.py:754` | `skip` | `"step 05 did not produce a pending review item to accept"` | predecessor-conditional | yes |
| `tests/e2e/test_pilot_clickthrough.py:777` | `skip` | `"step 05 did not produce a pending review item to reject"` | predecessor-conditional | yes |
| `tests/e2e/test_pilot_clickthrough.py:814` | `skip` | `"step 05 did not establish a pending_review_items baseline"` | predecessor-conditional | yes |
| `tests/e2e/test_pilot_clickthrough.py:839` | `skip` | `"step 02 did not resolve a unit id from GET /v1/me"` | predecessor-conditional | yes |
| `tests/e2e/test_pilot_clickthrough.py:880` | `skip` | `"step 02 did not resolve a unit id from GET /v1/me"` | predecessor-conditional | yes |
| `tests/e2e/test_pilot_clickthrough.py:920` | `skip` | `"step 02 did not resolve a unit id from GET /v1/me"` | predecessor-conditional | yes |
| `tests/e2e/test_pilot_clickthrough.py:1016` | `skip` | `"step 02 did not resolve a unit id from GET /v1/me"` | predecessor-conditional | yes |
| `tests/e2e/test_pilot_clickthrough.py:1090` | `skip` | `"step 09 did not produce a match run to compare against"` | predecessor-conditional | yes |
| `tests/e2e/test_pilot_clickthrough.py:1129` | `skip` | `"step 09 did not produce a match run to inspect"` | predecessor-conditional | yes |
| `tests/e2e/test_pilot_clickthrough.py:1175` | `skip` | `"step 09 did not produce a match run to inspect"` | predecessor-conditional | yes |
| `tests/e2e/test_pilot_clickthrough.py:1254` | `skip` | `"step 02 did not resolve a unit id from GET /v1/me"` | predecessor-conditional | yes |
| `tests/e2e/test_pilot_clickthrough.py:1310` | `skip` | `"step 02 did not resolve a unit id from GET /v1/me"` | predecessor-conditional | yes |
| `tests/e2e/test_pilot_clickthrough.py:1410` | `skip` | `"step 02 did not resolve a unit id from GET /v1/me"` | predecessor-conditional | yes |
| `tests/e2e/test_pilot_clickthrough.py:1426` | `skip` | `"no funded reward item exists on this appliance: nothing seeds a rewards catalog automatically and no /v1 route creates one. Run \`make seed-pilot-rewards\` with owner-supplied values (see docs/pilot-data/rewards-catalog-worksheet.md) to walk the request/decide path this step exercises when one exists."` | environment-conditional (appliance content) | **no** — the reason states that nothing seeds a rewards catalog and `pilot-e2e` runs no `make seed-pilot-rewards`, so this guard is expected to fire on every CI run |
| `tests/e2e/test_pilot_clickthrough.py:1444` | `skip` | `f"a funded reward item exists, but the student's balance does not cover it yet (server code {code!r}); Gap 3's attendance route credits the balance this step needs — verify one has run"` | environment-conditional (appliance content) | **no** — unreachable while `:1426` fires first in the same test |
| `tests/e2e/test_pilot_clickthrough.py:1489` | `skip` | `"the portal pages fetch /api/portals/*, a backend that does not exist in this repository, so they render a load-failure state; nothing here stands in for it. The web service's real behaviour is covered by scripts/compose_smoke.sh stage 16"` | **unconditional skip** | **no** — first statement in the test body; skips on every run, everywhere |
| `tests/e2e/test_pilot_clickthrough.py:1585` | `skip` | `"step 02 did not resolve a unit id from GET /v1/me"` | predecessor-conditional | yes |
| `tests/e2e/test_pilot_clickthrough.py:1640` | `skip` | `"step 02 did not resolve a unit id from GET /v1/me"` | predecessor-conditional | yes |
| `tests/e2e/test_pilot_clickthrough.py:1672` | `skip` | `"step 17 did not compose an approved outreach draft to send"` | predecessor-conditional | yes |
| `tests/e2e/test_pilot_clickthrough.py:1710` | `skip` | `"step 19 did not submit an outreach send command"` | predecessor-conditional | yes |
| `tests/e2e/test_pilot_clickthrough.py:1773` | `skip` | `"step 17 did not create a synthetic contact to compose for"` | predecessor-conditional | yes |
| `tests/e2e/test_pilot_clickthrough.py:1949` | `skip` | `"step 09 did not produce a match run to invite the shortlist of"` | predecessor-conditional | yes |
| `tests/e2e/test_pilot_clickthrough.py:2123` | `skip` | `"step 22 did not compose an invitation batch to dispatch"` | predecessor-conditional | yes |
| `tests/e2e/test_pilot_clickthrough.py:2346` | `skip` | `"step 23 did not record an accepted invitation to hand off"` | predecessor-conditional | yes |
| `tests/e2e/test_pilot_clickthrough.py:2574` | `skip` | `"step 02 did not resolve a unit id from GET /v1/me"` | predecessor-conditional | yes |
| `tests/e2e/test_pilot_clickthrough.py:2576` | `skip` | `"step 23 did not confirm a speaker to read a feedback summary for"` | predecessor-conditional | yes |
| `tests/e2e/test_pilot_clickthrough.py:2884` | `skip` | `"step 02 did not resolve a unit id from GET /v1/me"` | predecessor-conditional | yes |

---

## 5. Counts and the short list a human should look at

| Class | Sites |
|---|---:|
| environment-conditional | **43** (30 contract, 5 integration, 3 unit, 5 e2e) |
| predecessor-conditional | **27** (all `tests/e2e/test_pilot_clickthrough.py`) |
| unconditional skip | **2** |
| xfail | **0** |
| **Total real call sites** | **72** |

### 5.1 Unconditional skips — 2

- `tests/e2e/test_pilot_clickthrough.py:1489` — the portal step. The first
  statement in the test body is the skip; nothing in it can ever execute. Its
  reason is explicit that `/api/portals/*` is served by no service in this
  repository and that `scripts/compose_smoke.sh` stage 16 covers what is true of
  the `web` service.
- `tests/unit/test_env_isolation_check.py:132` — not a machine condition. It is
  a `None` guard over a parametrised identifier key, so whether it ever fires
  depends on the committed Terraform fixture tree, not on where the suite runs.

### 5.2 xfail — 0

There is **no** `pytest.mark.xfail` anywhere in the tree. The only two `xfail`
matches in `.py` files are prose in the module docstring of
`tests/unit/test_cba_scoring_decision_artifact.py` (lines 14 and 21), describing
markers that document a policy rather than markers that exist. `wip-analysis.md`
§0's "skipped/xfail" row therefore has an xfail half whose current value is zero.

### 5.3 "no" or "cannot tell from the repo" — 4

| Site | Verdict | Why it deserves a human |
|---|---|---|
| `tests/e2e/test_pilot_clickthrough.py:1489` | **no** | Runs nowhere. The step number is occupied by a test that cannot assert anything. |
| `tests/e2e/test_pilot_clickthrough.py:1426` | **no** | Its own reason says nothing seeds a rewards catalog and no `/v1` route creates one; `pilot-e2e` runs no seeding step. The request/decide path this step exists to exercise is therefore not exercised in CI. |
| `tests/e2e/test_pilot_clickthrough.py:1444` | **no** | Unreachable while `:1426` fires earlier in the same test. If `:1426` is ever resolved, this one becomes the next thing to check. |
| `tests/unit/test_env_isolation_check.py:132` | **cannot tell from the repo** | The in-line comment says *"provider_secret_id is null in classroom by policy"*, but the guarded value is read from `_env("prod")`, and `tools/env_isolation_check.py:148` declares `IdentifierKey("provider_secret_id", null_in=("classroom",))` — i.e. null in *classroom*, not in *prod*. On that reading the guard fires for no key and the comment is stale. **This was not executed to confirm.** |

`tests/integration/migration_harness.py:95` is marked "yes" on the reasoning in
§4.2 rather than on an observed run, and is flagged here for the same reason:
nothing in the repository asserts that the CI database user may `CREATE
DATABASE`.

### 5.4 One observed `pilot-e2e` run, 2026-09-18

The `pilot-e2e` job on the pull request carrying this file reported:

```
31 passed, 2 skipped in 23.90s
SKIPPED [1] tests/e2e/test_pilot_clickthrough.py:1426: no funded reward item exists on this appliance…
SKIPPED [1] tests/e2e/test_pilot_clickthrough.py:1489: the portal pages fetch /api/portals/*…
```

That is one run, not a guarantee, and it is recorded rather than generalized.
It does agree with §4.4 on every count: the two sites this inventory marks
**no** are exactly the two that skipped; `:1444` did not report, consistent with
being unreachable behind `:1426`; and none of the 27 predecessor-conditional
guards fired, which is what "yes (guard fires only if the named earlier step
failed)" predicts of a healthy run. The e2e half of the last column is
therefore observed for this run. **The `verify.yml` half — the 35
database-conditional sites in §4.1 and §4.2 — is still read from the workflow
file only.**

---

## 6. The eleven non-site grep hits, for reconciliation

Prose, not skip sites. Listed so that 83 = 72 sites + 11 prose lines is
checkable rather than asserted.

| file:line | What it is |
|---|---|
| `Makefile:97` | Comment: each e2e skip names its reason and `-ra` prints every one |
| `docs/architecture/IMPLEMENTATION_ROADMAP.md:1489` | Rule text: never `pytest.skip`, never an `xfail` |
| `docs/architecture/MIGRATION_ROADMAP.md:1684` | Same rule text |
| `docs/plans/2026-09-03-m2-m7-implementation-plan.md:888` | Plan prose |
| `docs/plans/2026-09-03-pilot-parallel-goal-prompts.md:606` | Plan prose |
| `docs/plans/2026-09-07-remaining-pilot-gaps-plan.md:769` | Plan prose |
| `docs/superpowers/plans/2026-09-14-student-recommender-v1-plan.md:888` | Code sample inside a plan |
| `docs/superpowers/plans/2026-09-14-student-recommender-v1-plan.md:2804` | Code sample inside a plan |
| `tests/e2e/conftest.py:16` | Module docstring |
| `tests/e2e/test_pilot_clickthrough.py:62` | Module docstring |
| `tests/integration/migration_harness.py:107` | Comment explaining that `pytest.skip` raises a `BaseException` |

---

## 7. Limits of this document

- It is a **snapshot**. Line numbers move with the next edit to any of these
  files; re-run the command in §1 rather than trusting the table.
- The "runs in CI" column is read from **workflow files**, with one exception:
  the single observed `pilot-e2e` run quoted in §5.4, which covers the `e2e`
  rows only. No `verify.yml` `-ra` summary was collected, so every yes/no on the
  35 database-conditional rows is a reading of the workflow, not of a run.
- It **authorizes nothing**. It proposes no test change, no workflow change and
  no status change, and it is not a production-readiness claim.

## References

- [`todo-disposition-register.md`](todo-disposition-register.md) — the 2026-09-18
  TODO survey; §2.1 is where the 83/75/35/30 figures first appear and §6 is
  where this audit was proposed
- [`../architecture/wip-analysis.md`](../architecture/wip-analysis.md) §0 — the
  `c72dced` snapshot this sits beside
- `.github/workflows/verify.yml` — the `python` job (PostgreSQL, migrations,
  `pytest -m "not e2e"`)
- `.github/workflows/build.yml` — the `pilot-e2e` job (`docker compose up`,
  `make e2e`)
