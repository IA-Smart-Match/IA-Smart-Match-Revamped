# Handoff: the PR #1 blockers and TODOs

**Branch:** `claude/pr1-blockers-todos-er5heu`, 13 commits ahead of `main`
(`c4ae716`, the PR #1 merge).
**State:** working tree clean, pushed. Every gate green at the tip —
`ruff format --check`, `ruff check`, `mypy --strict` (44 files), 4 import
contracts kept / 0 broken, forbidden-behavior scan clean (160 files),
agent-memory ledger clean (3 records), OpenAPI document current, and
**1078 test outcomes, exit 0** (576 in the no-database lane, 377 requiring
PostgreSQL, plus the authz and contract lanes).

Baseline at the start of this work was 789 outcomes. Nothing was skipped or
disabled to reach green.

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

**Four of these items carry an evidence gap, and it is the same gap in each.**

The agents implementing **J9+J8**, **J16**, **F9 (docs)** and **F2b+F5** were
each terminated by a usage limit at their final verification step. Their code
landed; their reports did not. So for those four:

- Every gate was re-run by the orchestrator and passes. The suite is green.
- **But the per-test revert-check evidence was never delivered.** This
  repository's standing rule is that a test must be shown to fail against the
  behaviour it fixes, and for these four items nobody has confirmed that.

A test that passes both before and after a change is worthless, and this
project has already been bitten by exactly that (F-2, F-24 — both were tests
that asserted a tautology and passed against an empty implementation). **The
first task for whoever picks this up is to run the revert-check on the tests
added by those four commits**, not to add more work on top.

The items whose evidence *was* delivered and reviewed — J10, J17, J15, A4,
F9 (code), F13 — do not carry this caveat. Their revert-checks are described in
their commit messages, including two cases where a mutant was needed because
the defect was in the evidence rather than the code.

Two further specifics:

- **No `terraform validate` has been run against the F5 files.** Terraform is
  not installed in the environment this was built in. The Python-side isolation
  assertion runs and passes; the HCL itself is unvalidated.
- **The J17 commit records a correction to its own backlog row** — the row
  called `mark_dispatched` "affected in form but not in substance", which is
  true of the outcome and not of the reporting. A benign lease race now
  produces a `DispatchOutcome.failed` increment. J8's alerting design was
  handed that question; confirm it was answered.

---

## 3. What is still open

### 3.1 Engineering work not started

| # | Item | Why it matters |
|---|---|---|
| **A5 / S-006** | `job.owning_unit_id` and unit-scoped job reads | A coordinator in one department can read, re-drive or abandon another department's job. The A4 matrix pins this hole as an equality across all four `job.*` operations, so closing A5 will break those cells and point at itself. A4 also measured that this is *missing data, not a missing rule* — the same principal against a resource that does carry an owning unit is correctly denied. Migration `0006`; `payload.unit_id` now exists to backfill from, which it did not before J10. |
| **JOB-READ-IGNORES-GRANTS** | `_authorize_job_read` consults no `resource_grant` at all | **Found by A4 and not yet fixed.** Policy rule 3, "an explicit deny beats inheritance", is not applied on the job-read path: an admin holding an explicit DENY on a job is refused by `/redrive` and `/abandon` and **permitted** by `GET /v1/jobs/{id}` and its event stream. An administrator carving one job out of a broad grant is silently ignored for reads. Current behaviour is pinned in two matrix cells, so the fix will break them visibly. This is the one I would do first. |
| **F12** | Drop `uq_user_account_tenant_subject` | Contract-phase. `uq_user_account_external_subject` (migration `0003`) makes it strictly redundant. |
| **F-25** | The weight-proposal aggregate bound | **Deliberately left open**, per `defect-remediation.md` §4.5 — the real finding is that the number a human approves is not the number applied, and choosing between normalize-on-apply and bound-at-proposal belongs with the M1/M8 consumer behind gate G1. Pinned by `test_aggregate_movement_is_deliberately_unbounded`. An earlier agent bounded it and was reverted; do not re-add a bound without settling the semantics. |
| **A1b / S-001** | Live identity verification, and the worker's signature backend | Ruled **out of scope** for this branch by the repository owner: closing it needs an asymmetric-crypto runtime dependency and a lock recompile, and PR #2 is already touching the lock files. The worker still refuses every task delivery. |

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
