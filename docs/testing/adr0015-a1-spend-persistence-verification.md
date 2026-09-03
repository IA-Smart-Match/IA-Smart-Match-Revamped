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

## Independent V1 integration audit — 2026-09-02

**Fixed point:** commit `93a93f8cc1a52101053266171d35cb296c42d087` on
`friday-deliverable-828`.

**Environment correction.** This session was initially told PostgreSQL was
unavailable, matching every earlier section of this document. That was
incorrect for this session: `postgresql+psycopg://smartmatch:smartmatch@localhost:5432/smartmatch`
— the exact URL `tests/integration/conftest.py` defaults to — was live
throughout, PostgreSQL 16.15, migrated to `alembic_version=0011_pipeline_record`
(which includes `0010_spend_reservation`). Every claim below marked "live" ran
against that instance for real. Nothing here is inferred from static reading
alone where a live run is cited.

Scope: the seven checks in this slice's verification brief — reserve-before-dispatch
ordering, durability, the redelivery rule, `AlreadyReconciledOutcome`'s shape,
fail-closed behavior on a missing actual cost, the sweeper's inability to
resurrect or double-charge, and whether the service is wired into a real
request path. No source change was made — no defect was found in any of the
seven.

### 1. Reserve-before-dispatch ordering

`services/worker/smartmatch_worker/paid_extraction.py:12` states the order in
its own docstring: *"reserve (commit) -> dispatch -> settle (commit)."* Traced
directly: `handle_paid_extraction` (line 260) calls `_reserve_or_fail` (line
292) first, which returns only after `SpendReservationService.reserve` has run
and, on success, committed (`_insert_reservation`'s `self._session.commit()`,
`python/smartmatch_persistence/smartmatch_persistence/spend.py:805`). The paid
call happens only inside `_dispatch_and_settle` (line 317), through
`smartmatch_domain.spend.dispatch` (line 481) — after a receipt exists. There
is no path from the handler to `dispatch()` that does not first pass through a
successful `reserve()`.

### 2. Durability across process restart

Architecturally: `reserve()`'s bucket debits and the reservation insert commit
together in one transaction, independent of the worker's own executor
transaction (Global Constraint 4).

Verified live, not only read, now that PostgreSQL is reachable — three
genuinely separate OS processes (`.venv/bin/python`, fresh interpreter, no
shared state) against the live `smartmatch` database:

1. Process 1 took a reservation (estimate `0.5000`) and exited (`exit 0`). A
   *fourth*, independent `psql` connection confirmed the row:
   `id=53d07893-... state=reserved estimate=0.5000`.
2. Process 2, started after process 1 had fully exited, reconciled the
   reservation to `actual_cost=0.1200` using only the reservation id, tenant
   id, work key, lease token, and estimate read back from the database — no
   in-memory state from process 1. `psql` confirmed:
   `state=reconciled actual_cost=0.1200 actual_is_estimated=f lease_token=NULL`.
3. Process 3, a third fresh process, redelivered the identical command (same
   tenant/job/provider/unit_of_work) and received
   `AlreadyReconciledOutcome(actual_cost=Decimal('0.1200'))` with zero new
   debit: `bucket reserved=0.0000 spent=0.1200`, `row_count=1`.

This is the strongest durability evidence available without bouncing the
shared PostgreSQL server itself, which would affect other concurrent work in
this environment. **What remains unverified:** an actual `pg_ctl restart` /
container recycle of PostgreSQL was not performed; durability past that point
rests on PostgreSQL's own WAL/commit guarantees, which this pass does not
re-examine.

### 3. Redelivery rule correctness

Pure/unit level: `tests/unit/test_spend_persistence.py:194-225`
(`TestRedeliveryRule`) pins `SpendReservationService._apply_redelivery_rule`
(`spend.py:814-864`) directly — an expired `reserved` row refuses with
`EXPIRED_NO_RETRY`; a row expiring at exactly `now` reuses the original receipt
(`spend.py:828` uses strict `<`, so equality falls through to the
receipt-minting branch); a `reconciled` row returns
`AlreadyReconciledOutcome(actual_cost=...)`.

Live, against real PostgreSQL — all 14 of `tests/integration/test_spend_reservation.py`
passed (full list below), including
`test_redelivery_of_a_reserved_row_reuses_it_and_debits_nothing_twice`,
`test_redelivery_of_a_reconciled_row_returns_the_recorded_actual`,
`test_redelivery_of_an_expired_row_is_refused_with_expired_no_retry`,
`test_redelivery_of_an_expired_but_unswept_row_refuses_without_writing`, and
`test_redelivery_after_release_re_reserves_under_the_next_attempt_key`.

Independently reproduced outside the test suite, with a raw SQL `UPDATE` from
*outside* any application process pushing `lease_expires_at` into the past
(simulating a worker that is truly gone, not merely a fixture): a fourth fresh
process then redelivered the identical command and got
`Refused(EXPIRED_NO_RETRY)`; the row's `state` stayed `reserved` (not
resurrected, not silently swept); the bucket's `reserved` balance was
untouched (`1.0000`); `row_count=1` (no second row).

### 4. `AlreadyReconciledOutcome` carries only what its call sites read

`python/smartmatch_domain/smartmatch_domain/spend.py:365-377`: the dataclass
has exactly one field, `actual_cost: Decimal | None`.
`grep -rn "AlreadyReconciledOutcome" python/ services/ tests/` shows every
consumer either does an `isinstance` check or reads `.actual_cost` and nothing
else. The one production consumer,
`services/worker/smartmatch_worker/paid_extraction.py:302-316`, reads
`.actual_cost`, guards it against `None`, and otherwise uses it verbatim.

### 5. Fail-closed on a reconciled redelivery missing its actual cost

`paid_extraction.py:302-307`: `if reservation.actual_cost is None: raise
RuntimeError(...)` — before any summary is built, before `SUCCEEDED` is
returned, before the provider is ever considered. Tested directly:
`tests/unit/test_paid_extraction_handler.py::test_a_reconciled_redelivery_missing_its_actual_cost_fails_closed`
(line 315) constructs exactly that state and asserts the `RuntimeError`,
`provider.calls == []`, `service.calls == ["reserve"]`.

The same invariant is defended a second time, independently, in
`SpendReservationService._apply_redelivery_rule` (`spend.py:850-855`), which
raises `RuntimeError` rather than propagate a `None` if it ever reads a
`reconciled` row with a `NULL actual_cost`.

**Non-blocking observation, not fixed.** `SpendReservationService.reconcile()`'s
own already-reconciled branch (`spend.py:472-473`, reached only when a caller
presents a receipt directly to `.reconcile()` rather than through `.reserve()`'s
redelivery path) returns `AlreadyReconciledOutcome(actual_cost=snapshot.actual_cost)`
without the same defensive `None` check. Not reachable through any call path in
this repository today — every write that sets `state='reconciled'` sets
`actual_cost` in the same guarded `UPDATE` (`spend.py:943-958`), and migration
`0010` has no database `CHECK` enforcing that pairing. Left as an observation
rather than a fix: adding a guard against a state no current caller can produce
would be line noise without a reachable defect behind it. A future caller of
`.reconcile()` outside `paid_extraction.py` should not assume this protection
exists at that specific call site.

### 6. The sweeper cannot resurrect or double-charge an expired reservation

Structural: `AbandonedReservationSnapshot` (domain `spend.py:302-317`) has no
`lease_token` field, and `spend_sweeper._snapshot_from_row`
(`spend_sweeper.py:228-244`) never selects that column — nothing the sweeper
reads can satisfy `release_before_dispatch`'s signature (pinned by
`tests/unit/test_spend_sweeper.py::TestSnapshotFromRow::test_carries_no_lease_token`).
`_select_abandoned` (`spend_sweeper.py:184-202`) only selects
`state='reserved' AND lease_expires_at < now`. `_settle_expired` routes through
`SpendReservationService._settle`'s guarded
`UPDATE ... WHERE id=:id AND state='reserved'` (`spend.py:943-958`) — a lost
race matches zero rows and writes nothing. `_flag_for_review`'s guarded
`UPDATE ... WHERE review_flagged_at IS NULL` (`spend.py:1021-1041`) bounds a
reservation to at most one finding.

Verified live, twice: (a) the integration suite's
`test_the_sweep_expires_an_abandoned_reservation_at_the_reserved_maximum`
(asserts a second sweep pass over the same instant reports no second finding)
and `test_the_sweep_leaves_a_live_reservation_alone`, both passing against real
PostgreSQL; (b) an independent probe against the manually-expired row from
check 3 — first sweep produced exactly one finding and moved the bucket
`reserved 1.0000 -> 0.0000`, `spent 0.0000 -> 1.0000`; a second sweep over the
same row and the same `now` produced zero findings and left the row and bucket
unchanged (`state=expired_spent`, `actual_cost=1.0000`,
`actual_is_estimated=True`, `review_flagged_at` set once, not twice). No
release, no second finding, no double-charge.

### 7. End-to-end integration — the "verify integration" heart of this slice

The service is wired into a genuine worker command handler, not merely
exercised by unit tests. `build_paid_extraction_handler`
(`services/worker/smartmatch_worker/paid_extraction.py:218`) returns a
`CommandHandler` with the exact `CommandContext -> HandlerResult` shape every
production handler in `handlers.py` uses — the shape `TaskExecutor`
(`execution.py`) drives from `POST /tasks/execute`, the real Cloud Tasks
delivery endpoint (`main.py`).

It is **not**, however, reachable from that endpoint today.
`services/worker/smartmatch_worker/handlers.py:819-830`'s `default_registry()`
registers exactly `"test.noop"` and `"import.create"`. `"extraction.paid_pages"`
(`paid_extraction.py:123`) is absent. `main.py:324`:
`registry = registry or default_registry()` — the shipped worker app boots
with exactly that registry. `with_paid_extraction` (`paid_extraction.py:329`),
the only function that would add the paid-extraction route, is never called
from `main.py`, `handlers.py`, or any other non-test module
(`grep -rn "with_paid_extraction" services/ | grep -v tests` returns one hit —
its own definition). `python/smartmatch_providers/smartmatch_providers/registry.py:247-312`,
`build_paid_extraction_provider`, only ever returns a `SyntheticPaidProvider`
and explicitly refuses a live adapter under every edition.

`README.md:40-41,77` already states this accurately — "deliberately absent
from the shipped registry" / "`main.py` does not register them in the shipped
worker" — and this pass confirms the claim rather than merely trusting it.

**Verdict:** a library-and-composable-handler, one
`with_paid_extraction(default_registry(), handler)` call away from being live,
deliberately not made in this repository. No HTTP request today can reach
`SpendReservationService` through the running worker or API. This matches A1's
ratification limits exactly ("authorizes only a synthetic-provider reservation
implementation and its verification... no paid call... is authorized") — a
documented gate, not an oversight.

### Runs

Spend-scoped unit tests:

```text
.venv/bin/pytest tests/unit/test_spend_persistence.py tests/unit/test_paid_extraction_handler.py \
  tests/unit/test_spend.py tests/unit/test_spend_sweeper.py -q
```
**PASSED.**

Spend-scoped integration tests, against live PostgreSQL 16.15:

```text
SMARTMATCH_DATABASE_URL="postgresql+psycopg://smartmatch:smartmatch@localhost:5432/smartmatch" \
  .venv/bin/pytest tests/integration/test_spend_reservation.py -v
```
**14 passed**, exit 0: `test_first_reservation_over_ceiling_with_no_bucket_row_is_refused`,
`test_first_reservation_at_exactly_the_ceiling_is_admitted`,
`test_a_day_ceiling_refusal_leaves_the_job_bucket_untouched`,
`test_concurrent_reservations_admit_exactly_the_ceiling_and_no_more`,
`test_interleaved_reservations_over_shared_buckets_do_not_deadlock`,
`test_redelivery_of_a_reserved_row_reuses_it_and_debits_nothing_twice`,
`test_redelivery_of_a_reconciled_row_returns_the_recorded_actual`,
`test_redelivery_of_an_expired_row_is_refused_with_expired_no_retry`,
`test_redelivery_of_an_expired_but_unswept_row_refuses_without_writing`,
`test_redelivery_after_release_re_reserves_under_the_next_attempt_key`,
`test_two_reconciles_record_one_actual`,
`test_the_sweep_expires_an_abandoned_reservation_at_the_reserved_maximum`,
`test_the_sweep_leaves_a_live_reservation_alone`,
`test_an_overage_posts_in_full_and_the_next_reservation_is_refused`.

Full no-database suite:

```text
.venv/bin/pytest tests/ -m "not integration" -q --tb=no -rf
```
1,372 tests collected. **1 failed:**
`tests/unit/test_gate_decision_artifacts.py::test_g1_packet_remains_unapproved_prep`
— the one pre-existing failure named in this task's brief. The brief also named
three pre-existing failures in `tests/unit/test_agent_memory_check.py`; that
file ran clean in this session (`.venv/bin/pytest tests/unit/test_agent_memory_check.py
tests/unit/test_gate_decision_artifacts.py -v` → `86 items, 1 failed, 85
passed`, the one failure being the gate-decision test above). Recorded as
observed, not corrected: this pass made no edits to any file that could affect
that suite, and the brief's instruction was not to fix or grow pre-existing
failures, not to reconcile this document's inherited list with what a given
session actually observes.

**Repository stability during this pass.** This working tree had concurrent,
unrelated work landing throughout this session — visible in `git status`
(modified/untracked files under `docs/decisions/`, `docs/pilot-data/`,
`db/migrations/versions/0012_professional_unit_relationship.py`,
`tests/unit/test_column_contract.py`, `tests/unit/test_import_column_contract_wiring.py`,
none of it touched by this verification). Two consecutive full-suite runs
produced different transient failure sets in `test_column_contract.py` /
`test_import_column_contract_wiring.py` mid-session; a third, later run showed
neither. That is concurrent P9 Gate A work landing mid-run, not spend-module
instability — those files were not read, touched, or investigated further,
being outside this task's scope.

Full integration suite, for completeness, since PostgreSQL is reachable (not
spend-scoped):

```text
SMARTMATCH_DATABASE_URL="postgresql+psycopg://smartmatch:smartmatch@localhost:5432/smartmatch" \
  .venv/bin/pytest tests/ -m integration -q --tb=short -rf
```
**13 failed**, all outside the spend module. Every failure traces to
`db/migrations/versions/0012_professional_unit_relationship.py` (untracked,
unrelated, concurrent P9 Gate A work): its revision id
`'0012_professional_unit_relationship'` is 36 characters against
`alembic_version.version_num`'s `VARCHAR(32)`, raising
`psycopg.errors.StringDataRightTruncation` on every scratch-database migration
test, cascading into nine schema-parity tests for that one new table. Zero of
the thirteen mention `spend_reservation` or `spend_ceiling_bucket`. Reported
for completeness and left alone: out of this task's scope, not caused by
anything reviewed here. The shared dev database's own `alembic_version`
(`0011_pipeline_record`) was confirmed unchanged before and after this run.

Ruff / mypy / import-linter, spend-scoped (the seven source files under review
plus their four test files):

```text
.venv/bin/ruff format --check <11 files>   # 11 files already formatted
.venv/bin/ruff check <11 files>            # All checks passed!
.venv/bin/mypy <6 source files>            # Success: no issues found in 6 source files
PYTHONPATH="python/smartmatch_domain" .venv/bin/lint-imports --config pyproject.toml --no-cache
                                            # Contracts: 4 kept, 0 broken.
```

Full-repo `ruff format --check .` (for completeness): 3 files would be
reformatted, none in scope — the then-untracked duplicate
`tests/integration/test_j8_j9_dispatcher_scheduling.py`,
`tests/integration/test_job_lease_lifecycle.py`, and
`tests/unit/test_import_column_contract_wiring.py` (the latter two mid-flight
per `git status`). Full-repo `ruff check .` found one `I001` import-order error
in that duplicate untracked J8/J9 module. The duplicate was later discarded in
favor of the existing focused suites; no spend-slice file was changed.

### Defects found

None, across all seven checks. One non-blocking observation recorded under
check 5 and deliberately left unfixed, for the reason given there.

### Cleanup note

This pass created a small number of throwaway rows in the shared local
PostgreSQL instance while probing checks 2, 3, and 6 from independent OS
processes (tenant slugs `restart-probe-*` and `expiry-probe-*`, and their
`spend_reservation`/`spend_ceiling_bucket` rows). They were left in place
rather than deleted under a destructive-command safety gate for a cleanup
nobody asked for; they are inert, clearly labeled as probe data, and harmless
to leave or remove later.
