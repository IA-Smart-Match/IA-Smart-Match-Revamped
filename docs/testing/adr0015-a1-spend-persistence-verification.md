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

Result at the fixed point after adding the approved tests and before production edits: **FAILED — 5 failed, 43 passed**.

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

The first group proves the persistence redelivery path did not receive the request instant and therefore could not distinguish an expired lease or equality. The second group proves the worker treated an already-reconciled outcome as a new receipt instead of completing without dispatch.

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
