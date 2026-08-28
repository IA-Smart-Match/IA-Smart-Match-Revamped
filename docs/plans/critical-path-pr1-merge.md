# Critical path: merge and evidence-check the PR1 blockers branch

**ID:** CP-PR1
**Parent:** [critical-path-plans.md](critical-path-plans.md)
**Branch:** `claude/pr1-blockers-todos-er5heu` (remote of the same name)
**Handoff (on that branch only):** `docs/plans/pr1-blockers-handoff.md`

Planning only. Do not merge from this document; execute the checklist when the
team is ready.

---

## (a) What this is

`main` still has an end-to-end command path that cannot execute work:
`import.create` fails as `failed_policy` / `command_not_executable` because
there is no `job.payload` (backlog **J10**). The dispatcher has no timer
(**J8**). A worker that dies after `claim` leaves the job `running` forever
(**J9**). Quota is refunded on a 500 (**J15**) and not charged on 403/404/400
(**J16**). Outbox writers prove *someone* holds a lease, not that *this*
dispatcher does (**J17**). The authorization matrix is one operation, not a
matrix (**A4**). Port-verification findings are unfixed (**F9**). Governance
files and supply-chain gates are incomplete (**F13**, **F2b**, **F5**).

All of that is implemented on the PR1 branch, in 13 commits ahead of `main`
(`c4ae716`). The handoff lists them:

| Item | Commit | Notes |
|---|---|---|
| J15 | `c023fb3` | 500 keeps quota. Evidence delivered. |
| F13 | `0c5ede6` | `CONTRIBUTING.md`, `SECURITY.md`, `CODEOWNERS`, `docs/operations/deploy-runbook.md`. No `LICENSE` (D9). Evidence delivered. |
| F9 code | `654e89f`, `8c47c2e` | ics/eli then ingest/feedback. Evidence delivered. F-25 left open. |
| J10 | `180a9c3` | Migration `0005` `job.payload`. Evidence delivered. |
| J17 | `6c5ba21` | Lease token. Evidence delivered. Ledger 0001 re-pointed in `691367a`. |
| A4 | `b4450ab` | `tests/authz/test_policy_matrix.py`; 32 → 134 authz tests. Evidence delivered. |
| README | `6a2f0ec` | Stops claiming `make check` ⇒ green CI. |
| **J9 + J8** | `3243e00` | **No revert-check evidence.** |
| **J16** | `41d47da` | ADR-0015. **No revert-check evidence.** |
| **F9 docs** | `3cf3284` | Manifest + F-30. **No revert-check evidence.** |
| **F2b + F5** | `80a07ea` | License gate, CycloneDX SBOM, env isolation. **No revert-check evidence.** `terraform validate` never run. |
| Handoff | `fab0614` | This file. |
| F-4 docstring | `a48408a` | Partial leftover-copy fix after the handoff. |

Sources on `main` that still describe the pre-PR1 world:
`docs/plans/remaining-foundation-r1-work.md` (J8–J10, J15–J17, A4, F9, F5, F2b,
F13, "Suggested next three"), `docs/architecture/command-path.md` (J8/J9/J17
still open), `docs/security/scaffold-security-review.md` (S-008 residual as of
Wave B).

---

## (b) Current status

- Working tree on the feature branch was reported clean and pushed.
- Gates at the tip: ruff, mypy `--strict` (44 files), import-linter, forbidden
  scan (160 files), agent-memory (3 records), OpenAPI current, **1078 tests**.
- **Not merged.** `main` does not contain `0005`, ADR-0015, or the handoff file.
- `origin/main` is four commits ahead of local `main` (gitleaks workflow, lock
  regen). Rebase or merge that CI line as part of landing; it is not a third
  product branch.
- ADR-0015 on this branch **takes the number** `docs/superpowers/specs/2026-08-24-agent-memory-design.md`
  still reserves for Slice 1. The ADR index on the branch moves the reservation
  to **ADR-0016**. The spec was not updated.

---

## (c) Execution plan

### 1. Rebase onto current `origin/main`

PR #2 (`claude/fix-lock-drift-and-gitleaks-gate`) touches `requirements/runtime.txt`
and `.github/workflows/verify.yml`. PR1 also touches both. Resolve lock and
workflow conflicts once, in this merge, not twice.

File-level conflict likely:

- `.github/workflows/verify.yml` — gitleaks-as-tool vs PR1's extra gates
  (license, SBOM, env isolation).
- `requirements/runtime.txt` — PR #2 regen vs PR1 adding no crypto (A1b still
  deferred). Keep PR #2's regen flags; do not add a crypto library in this merge.

### 2. Revert-checks (do this before treating the four thin commits as done)

Rule: a test added to pin a defect must fail against the behaviour it fixes.
This repository has already shipped tautological tests (F-2, F-24).

For each of `3243e00`, `41d47da`, `3cf3284`, `80a07ea`:

1. List new tests from the commit (`git show --stat`, then `git show -- tests/`).
2. Soft-revert the **production** side onto a worktree (not the tests).
3. Run those tests; they must fail.
4. Restore; they must pass.
5. Record the command and the failure message in the merge PR or in
   `pr1-blockers-handoff.md` §2.

If a test passes both before and after, it is not coverage. Fix or delete it
before merge.

**J8/J9 specifics.** Confirm `job.lease_expires_at` is written at
`dispatched -> running`, renewed, cleared on terminal, and that the sweep
emits `running -> timed_out`. Confirm something actually **schedules**
`run_once` (HTTP endpoint, documented operator command, or test-only hook —
read `dispatcher.py` / `main.py` on the branch; do not assume Cloud Scheduler
exists). Confirm J8 alerting: scheduler-not-firing (not only lag), plus
`DispatchOutcome.reclaimed`, plus whether a benign J17 race incrementing
`failed` was answered in the alerting design (handoff §2).

**J16 specifics.** Confirm 25 consecutive 403/404/400 each move
`rate_limit_counter`, that 401 is uncharged, and that the charge commits in
its own transaction (`charge_quota` in `dependencies.py`). ADR-0015 is the
spec.

**F9 docs specifics.** Confirm MM-003/004/005 YAML no longer contains the
false retained-vocabulary / nonexistent-characterization-tests / substring-match
claims. Status fields must still be `ported_unverified`. Confirm F-30 exists
in `port-verification.md`.

**F2b+F5 specifics.** Run `terraform validate` in each of
`infra/terraform/envs/{dev,staging,prod,classroom}` — **this has never been
run**. Run the Python env-isolation tool (`tools/env_isolation_check.py`) and
the supply-chain tool (`tools/supply_chain.py`) and confirm CI wires them.

### 3. Do not merge with known product holes unlabelled

The merge PR description must name, as still open:

- CP-GRANT, CP-A5, CP-REREVIEW, F-25, leftover docstrings, A1b, D9/`LICENSE`.

Otherwise the merge reads as "Foundation complete".

### 4. Land as one merge to `main`, then CP-DOCSYNC

Do not squash-merge if the 13 commits are the audit trail the handoff cites by
SHA. Prefer a merge commit. After land, immediately update
`remaining-foundation-r1-work.md` (see master CP-DOCSYNC) so the next agent
does not re-implement J10.

### 5. Agent-memory

Record `0001` was already re-pointed at the post-J17 `outbox.py` blob. Any
further `outbox.py` edit in the rebase will go `stale-source` until re-pointed
again (`docs/agent-memory/README.md`: re-verify the claim, do not update the
SHA alone).

---

## (d) Dependencies

**Blocked by.** Nothing except agreeing to merge.

**Blocks.** Every later critical path that assumes `job.payload`, the A4
matrix, ADR-0015, or F9 code fixes.

**Collides with.** PR #2 lock/gitleaks. A1b (lock). Do not start A1b inside
this merge.

---

## (e) Acceptance

- [ ] `main` contains `db/migrations/versions/0005_job_command_payload.py`.
- [ ] `docs/architecture/decisions/ADR-0015-charge-quota-before-refusal.md` exists
      and the ADR index row + reservation-to-0016 match `test_adr_index.py`.
- [ ] `tests/authz/test_policy_matrix.py` is on `main`.
- [ ] Revert-checks for the four thin commits recorded with failing-then-passing
      output.
- [ ] `terraform validate` run in all four env dirs, or explicitly waived with
      why.
- [ ] Full `pytest tests/` green on the merge commit (expect on the order of
      1078 outcomes; re-measure, do not copy the number).
- [ ] `remaining-foundation-r1-work.md` no longer lists J8–J10 / J15–J17 / A4
      as open.
- [ ] Superpowers spec ADR number updated to 0016, or Slice 1 explicitly still
      claiming 0015 with a failing index test — pick one; do not leave both.

---

## (f) Priority

**First.** On `main`, J10 is still the functional blocker; on the PR1 branch it
is already done. The cost of ignoring this path is duplicating 10k+ lines.

---

## What this path is not

- Not a substitute for CP-REREVIEW. F9 *fixes* are here; F9 *approval* is not.
- Not A5, not the job-read grant hole, not A1b.
- Not production readiness. Nothing is deployed; `ALLOW_CLOUD_DEPLOY` remains
  false unless the user changes it.
