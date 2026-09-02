# ADR-0015 A1 spend persistence verification

## Fixed point and environment

- Branch: `friday-deliverable-828`
- Starting commit: `fb8787abc3f0d484f8a1d013a0ead7fdf9e2d55e`
- Environment: WSL, repository `.venv`; PostgreSQL availability is recorded with the integration run below.

## Fail-before evidence

Command:

```text
.venv/bin/pytest tests/unit/test_spend_persistence.py tests/unit/test_paid_extraction_handler.py -q
```

Result at the fixed point after adding the approved new-interface tests and
before production edits: **FAILED — 5 failed, 43 passed**.

Exact failures:

```text
TestRedeliveryRule.test_an_expired_reserved_row_is_refused_without_becoming_reusable
TestRedeliveryRule.test_a_reserved_row_expiring_exactly_now_reuses_the_original_receipt
TestRedeliveryRule.test_a_reconciled_row_returns_its_durable_actual_cost
TypeError: SpendReservationService._apply_redelivery_rule() got an unexpected keyword argument 'now'

test_a_reconciled_redelivery_succeeds_without_calling_or_settling
test_a_reconciled_redelivery_missing_its_actual_cost_fails_closed
AttributeError: 'AlreadyReconciledOutcome' object has no attribute 'reservation_id'
```

This run proves only that the fixed-point interfaces did not yet accept the new
`now` argument or the new `AlreadyReconciledOutcome` result. Those interface
errors occur before the old behavioral outcomes are observed, so no behavioral
claim is derived from this run.

### Fixed-point behavioral probe adapted to the old interfaces

I exported exactly
`fb8787abc3f0d484f8a1d013a0ead7fdf9e2d55e` to an isolated directory under
`/tmp`, added a temporary three-test probe there, and called the fixed-point
interfaces with their old signatures. No working-tree source was replaced or
mutated.

Command:

```text
/mnt/c/users/dangt/documents/github/ia-smart-match-revamped/.venv/bin/pytest \
  tests/unit/test_adr0015_remediation_fail_before_probe.py -q
```

Result: **PASSED — 3 tests, exit 0**. Each passing assertion records the
undesired fixed-point behavior the remediation changes:

```text
test_fixed_point_reuses_an_expired_reserved_receipt
  -> SpendReservationService._apply_redelivery_rule returned SpendReservationReceipt
     even though lease_expires_at was one second before now.

test_fixed_point_refuses_a_reconciled_redelivery
  -> SpendReservationService._apply_redelivery_rule returned
     Refused(ALREADY_TERMINAL) for a reconciled row carrying actual_cost=0.1200.

test_fixed_point_worker_maps_reconciled_refusal_to_budget_failure
  -> the fixed-point worker raised BudgetFailure(reason="already_terminal") and
     made zero provider calls when reserve returned that reconciled-row refusal.
```

## Green verification

- `.venv/bin/pytest tests/unit/test_spend_persistence.py tests/unit/test_paid_extraction_handler.py tests/unit/test_spend.py -q`: **PASSED**, 113 tests, exit 0.
- `make format-check lint typecheck imports`: **PASSED**, 243 files formatted, Ruff clean, mypy 61 files clean, 4 import contracts kept.
- `.venv/bin/pytest tests/ --collect-only -q`: **PASSED collection**, 1,817 tests (1,266 no-database; 551 integration-marked), exit 0. Collection is not execution.
- `make test-integration`: **SKIPPED / NOT VERIFIED**, 551 skipped and 1,266 deselected, exit 0; PostgreSQL unavailable. Skips are not passes.
- `make test`: **DID NOT COMPLETE**, terminated with Ctrl-C after it remained at 17% for approximately seven minutes. Exact last progress was two tests after the 17% marker. A bounded diagnostic then collected `tests/contract/test_api_health.py` and timed out after 60 seconds (exit 124) at `tests/contract/test_api_health.py::test_health_reports_ok`. No passing no-database-suite claim is made.

## PostgreSQL mutation probes

- Guarded insert source predicate: **NOT RUN — PostgreSQL unavailable**.
- `DO UPDATE` ceiling predicate: **NOT RUN — PostgreSQL unavailable**.
- `_settle` `state='reserved'` predicate: **NOT RUN — PostgreSQL unavailable**.

No mutants were applied because their required focused integration nodes could
not execute. Mocks and static inspection were not substituted for PostgreSQL.

## Restoration checks

- `git diff --check`: **PASSED**, exit 0 after the mutation-probe decision.
- `git diff`: **INSPECTED**; no temporary SQL mutants are present. The untracked approved-plan companion
  `docs/superpowers/plans/2026-09-01-adr0015-a1-spend-persistence.md` is unrelated,
  preserved, and excluded from commits.

## Code-quality remediation verification — 2026-09-02

- Focused unit command from the Green section: **PASSED**, 113 tests, exit 0.
  Pytest also warned that its cache could not write to the case-resolved
  read-only workspace path; test execution itself completed.
- `.venv/bin/pytest tests/integration/test_spend_reservation.py --collect-only -q`:
  **PASSED collection**, 14 nodes, exit 0. PostgreSQL execution was not retried.
- `make format-check lint typecheck imports` with Ruff and mypy caches under
  `/tmp`: format-check **PASSED** (248 files), Ruff **PASSED**, and mypy
  **PASSED** (62 files). The combined command exited 2 only when import-linter
  attempted to create its cache on the case-resolved read-only workspace path.
- The equivalent import-boundary command with `--no-cache`: **PASSED**, 4
  contracts kept and 0 broken, exit 0.
