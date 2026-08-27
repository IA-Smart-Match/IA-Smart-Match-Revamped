# Handoff: the PR #1 blockers and TODOs

**Branch:** `claude/pr1-blockers-todos-er5heu`, open as **PR #3**.
**Base:** `main` at `c4ae716`, the PR #1 merge.

**State at `2e13032`**, re-verified by the orchestrator against a freshly
migrated database (`0001`…`0007`): `ruff format --check` (134 files),
`ruff check`, `mypy --strict` (45 files), 4 import contracts kept / 0 broken,
forbidden-behavior scan clean (171 files), agent-memory ledger clean (3
records), license policy clean (43 allowed, 4 under a recorded exception, 0
undetermined), environment isolation clean (4 environments, 40 identifiers,
none shared), OpenAPI document current, and **1135 test outcomes, exit 0**.

Baseline at the start of this work was 789 outcomes. Nothing was skipped or
disabled to reach green — but read §2.2 before reading that number as coverage.

**CI on PR #3 is red on two checks, and neither is this branch's.** Both are
pre-existing failures on `main` — the `--strip-extras` lock drift and the
gitleaks organisation-licence failure — and **PR #2 fixes both**. Diagnosed in
a comment on PR #3.

---

## 1. What this branch closed

| Item | Commit | What it was |
|---|---|---|
| **J10** | `180a9c3` | The top functional blocker. `import.create` was the only real command wired end to end and it always failed — no payload column existed, so every import terminated as `failed_policy` / `command_not_executable`. Migration `0005` adds `job.payload`. |
| **J17** | `6c5ba21` | Outbox writers proved *someone* held the row, not that the caller did. Reproduced the measured lease theft — 56 seconds cut off a peer's 60-second lease — then closed it with a lease token. |
| **J15** | `c023fb3` | A 500 refunded the quota that produced it. Now it persists. |
| **J16** | `41d47da` | 403/404/400 refusals cost zero quota. Now charged, per the owner's decision, recorded as **ADR-0015**. |
| **J9 + J8** | `3243e00` | A job stuck `running` had no recovery, and nothing ran the dispatcher on a timer. Lease, sweep, scheduled pass, heartbeat. |
| **A4** | `b4450ab` | The authorization matrix: 5 operations × 11 principal shapes, executed against the real authorizer, completeness enforced executably. `tests/authz` 32 → 134. |
| **F9 (code)** | `654e89f`, `8c47c2e` | 13 of the port review's engineering findings across `ics`, `eli`, `ingest`, `feedback`. |
| **F9 (docs)** | `3cf3284` | The manifest description errors the review actually rejected the ports for, plus **F-30**, a new defect found in the review document itself. |
| **F13** | `0c5ede6` | `CONTRIBUTING.md`, `SECURITY.md`, `CODEOWNERS`, and the deploy runbook carrying ADR-0009's `ON_ERROR_STOP=1` obligation. |
| **F2b + F5** | `80a07ea` | License policy gate, CycloneDX SBOM, and the executable assertion that Terraform environments share no identifiers. |
| **README** | `6a2f0ec` | Removed the false claim that a green `make check` means a green CI. |
| **Ledger** | `691367a` | Re-pointed agent-memory record 0001 at the `outbox.py` blob J17 produced. |

---

## 2. Read this before trusting section 1

**Four items carried an evidence gap. Two have since been resolved, and one of
them turned out to be worse than a missing report.**

The agents implementing **J9+J8**, **J16**, **F9 (docs)** and **F2b+F5** were
each terminated by a usage limit at their final verification step. Their code
landed; their reports did not — so nobody had confirmed their tests fail
against the behaviour they fix, which is this repository's standing rule.

A test that passes both before and after a change is worthless, and this
project has already been bitten by exactly that (F-2, F-24 — both were tests
that asserted a tautology and passed against an empty implementation).

### 2.1 J16 — revert-check run, evidence good

Reverting J16's four source files to `41d47da~1`, keeping the tests, fails
exactly the six tests J16 added and no others:

```
FAILED test_command_path.py::test_a_run_of_forbidden_imports_is_charged_and_then_limited
FAILED test_command_path.py::test_a_run_of_imports_into_a_unit_that_does_not_exist_is_charged_and_then_limited
FAILED test_command_path.py::test_a_run_of_imports_with_no_idempotency_key_is_charged_and_then_limited
FAILED test_redrive.py::test_a_run_of_forbidden_redrives_is_charged_and_then_limited
FAILED test_redrive.py::test_a_run_of_redrives_against_ids_that_do_not_exist_is_charged_and_then_limited
FAILED test_redrive.py::test_a_run_of_redrives_with_no_idempotency_key_is_charged_and_then_limited
```

Restored, and all six pass again. **J16's evidence gap is closed.**

### 2.2 J9 and J8 — the tests do not exist

This one was not a missing report. It was missing tests.

Commit `3243e00` changed 22 lines of test across two files, and **none of them
test J9 or J8.** Measured:

| Location | `timed_out\|sweep\|heartbeat\|lease_expires` |
|---|---|
| `tests/integration/test_worker_execution.py` | **0** |
| `tests/contract/test_worker_boundary.py` | **0** |
| `tests/integration/test_outbox_dispatcher.py` | 27 — but **every one is `outbox_record.lease_expires_at`**, the *outbox* lease, which predates J9 |
| `services/worker/smartmatch_worker/main.py` | 28 |
| `services/worker/smartmatch_worker/execution.py` | 19 |
| `python/smartmatch_persistence/.../jobs.py` | 34 |

So the job lease, the sweep to `timed_out`, and the heartbeat have **no test
coverage whatsoever**. The suite is green because nothing exercises them.

Confirmed by revert-check: reverting the four worker source files to
`3243e00~1` (leaving `jobs.py` at HEAD — see the trap below) fails only three
tests, and two of those are J17's, adapted by `3243e00` rather than written for
it. The third is a route-surface contract assertion.

**Trap for whoever runs this again:** do not revert
`smartmatch_persistence/jobs.py` to `3243e00~1`. A later commit (A5, `7e27268`)
added `owning_unit_id` to `JobRepository.create()`, so reverting that far
produces 40 `TypeError` failures that are an API mismatch, not evidence.
Reverting only the worker files reproduces the true pre-J9 condition the
backlog describes — the column exists and nothing reads or writes it.

### 2.3 Still unverified

- **F9 (docs)** — documentation only, so there is no behavioural revert-check
  to run. What it needs instead is the re-review in §3.2, and its re-measured
  test counts re-counted by someone else.
- **F2b+F5** — the two new tools have self-tests that pass, but nobody has
  confirmed those self-tests fail against a broken tool. The mutation check is
  the one that matters for a gate.
- **No `terraform validate`** has been run against the F5 files; terraform is
  not installed here. The Python-side isolation assertion runs and passes; the
  HCL itself is unvalidated.
- **The J17 commit records a correction to its own backlog row** — the row
  called `mark_dispatched` "affected in form but not in substance", which is
  true of the outcome and not of the reporting. A benign lease race now
  produces a `DispatchOutcome.failed` increment. J8's alerting design was
  handed that question; confirm it was answered.

The items whose evidence *was* delivered and reviewed — J10, J17, J15, A4,
F9 (code), F13 — do not carry this caveat. Their revert-checks are described in
their commit messages, including two cases where a mutant was needed because
the defect was in the evidence rather than the code.

---

## 3. What is still open

### 3.1 Engineering work

**Closed since this document was first written** (commits `7e27268`, `5f02423`,
`2e13032`):

- **A5 / S-006** — `job.owning_unit_id` (migration `0006`). A coordinator can no
  longer reach another department's job.
- **JOB-READ-IGNORES-GRANTS** — closed with A5, and closed properly: rather than
  patching the read path, `routers/jobs.py` and `routers/redrive.py` now both
  call one `job_authz.authorize_job_read`, so all four job operations apply the
  same policy to the same resource. The old defect is named in that module's
  docstring so the reason the two implementations were merged is not lost.
- **F12** — `uq_user_account_tenant_subject` dropped (migration `0007`).

**Still open:**

| # | Item | Why it matters |
|---|---|---|
| **J9 / J8 tests** | The lease, the sweep and the heartbeat are untested | See §2.2. This is the top item: the code is in and nothing exercises it. |
| **F-25** | The weight-proposal aggregate bound | **Deliberately left open**, per `defect-remediation.md` §4.5 — the real finding is that the number a human approves is not the number applied, and choosing between normalize-on-apply and bound-at-proposal belongs with the M1/M8 consumer behind gate G1. Pinned by `test_aggregate_movement_is_deliberately_unbounded`. An earlier agent bounded it and was reverted; do not re-add a bound without settling the semantics. |
| **A1b / S-001** | Live identity verification, and the worker's signature backend | Ruled **out of scope** for this branch by the repository owner: closing it needs an asymmetric-crypto runtime dependency and a lock recompile, and PR #2 is already touching the lock files. The worker still refuses every task delivery. |
| **CI** | Two checks red on PR #3 | Neither is this branch's: the `--strip-extras` lock drift and the gitleaks org-licence failure, both pre-existing on `main` and both fixed by **PR #2**. Diagnosed in a comment on PR #3. Merging #2 resolves them. |

### 3.2 The re-review F9 requires

F9's remedy is "a manifest correction plus a small number of code fixes, then
**re-review**". The corrections and the fixes are done; the re-review is not.
§6 of the orchestrator contract forbids an agent approving its own port, so
**MM-003, MM-004 and MM-005 remain `ported_unverified`** and must be re-reviewed
by someone who did not write the fixes. What a re-reviewer needs to check is
stated in the manifest.

Note the review document now contains **F-30**, a defect in its own F-24 probe
table: the table claims coverage of the `frozen=True` guarantee that its probes
do not actually provide. Worth reading before trusting other probe tables in
that document.

### 3.3 Blocked on a named human — no engineering path

None of these can be closed from a checkout, and several block work that can.

**Interim positions on all of them are now recorded in
[`../decisions/pilot-decisions.md`](../decisions/pilot-decisions.md).** Those
positions are **tentative, interim-owned, and not organizationally ratified** —
they exist so development has something written down to build against. They do
not close any of the items below, which still need IA West.

- **D1** — approve the factor registry and golden case set (gate G1). **The
  longest pole.** All matching work waits on it, and matching is the product's
  reason for existing. *Tentative position recorded; no registry is approved.*
- **D2** — ELI formula parameters. Now blocking one decided question: whether
  committed future engagements should count toward load (F-9 made the current
  behaviour explicit and refuses them rather than silently dropping them).
  *Tentative position recorded; that sub-question stays open.*
- **D3–D8** — route-matrix terms, DNS, retention periods, rewards budget owner,
  points calibration, disclosure-consent policy. *Tentative positions recorded.
  D7 (100 points per verified attendance; 300/600/1,000 bands; N = 3) and D8
  (minimum disclosure, and explicitly **no** FERPA-compliance claim) are decided
  in full there; D3–D5 are deferred; D6 names an operational administrator, not
  a budget holder.*
- **D9** — licensing. Blocks `LICENSE`, which is why F13 shipped the other three
  governance files and deliberately not that one. *Tentative position recorded:
  private pilot, no open-source license, and deliberately still no `LICENSE`
  file. `README.md` now carries that notice.*
- **Q1** — remediation owner for the six legacy paths carrying named real
  people. **A *handling* decision is now recorded as CLOSED: the archived legacy
  repository stays read-only reference material — not modified, not deleted,
  history not rewritten.** That is a decision about handling and **not an
  erasure**. The six paths remain in that archive's history, so the exposure
  behind MM-A09 is unchanged and still gates D9.
- **D-0** — a `DESIGN.md` owner, which blocks the entire W-series frontend.
  *Deferred, not decided. `apps/web/DESIGN.md` stays unresolved pending the UI
  team. See also [`../ui/pilot-prototype-prompts.md`](../ui/pilot-prototype-prompts.md),
  which is non-authoritative and closes nothing.*

### 3.4 Deliberately not started

The **S-series** (S1–S12, the stakeholder test-log items) is R2/R3 work behind
ADRs 0010–0014 and several of the D-decisions above. The backlog is explicit
that these are **not** ordered ahead of the existing work.

---

## 4. Environment notes for the next session

The container is ephemeral; everything worth keeping is pushed.

```bash
make setup                       # venv + hash-pinned dev deps
make db-up                       # local PostgreSQL 16 (already installed)
make migrate                     # applies 0001..0005
.venv/bin/pytest tests/ -q       # expect 1078 outcomes, exit 0
```

Two things that cost time here and need not cost it again:

- **Integration tests share one database and an autouse fixture deletes every
  `job` row.** Two concurrent test runs destroy each other. If you parallelise
  agents, give each its own database (`createdb`, then `alembic upgrade head`
  against it) and pass `SMARTMATCH_DATABASE_URL`.
- **The agent-memory ledger pins source blobs**, so any uncommitted change to a
  cited file (today: `outbox.py`) fails `test_the_real_ledger_validates_clean`
  with `dirty-source`. That is expected while work is in flight and clears on
  commit — but committing then flips it to `stale-source`, and the record must
  be re-pointed at the new blob. See `691367a` for the shape of that fix.

Docker is not available in this environment; PostgreSQL runs natively.

---

## 5. Suggested order

1. **The job-read grant defect** — a real authorization hole, small, and A4 has
   already pinned the current behaviour so the fix announces itself.
2. **The revert-checks in §2** — cheap, and they either confirm four items or
   find that one of them is not actually tested. Do this before building on them.
3. **A5** — closes S-006, and the matrix will tell you when it is done.
4. **D1** — start the conversation. It is not engineering work and it is the
   longest pole in the project.
