# Plan — ADR-0015 A1 critical remediation

**Fixed point:** `main...e4d808e` on `friday-deliverable-828`

**Authority:** ADR-0015 Amendment A1, the approved Approach A in this plan, and
`CONTRIBUTING.md`

**Goal:** close the six final-review findings without broadening the paid-provider
slice or overstating PostgreSQL evidence.

## Approved design

`SpendReservationService.reserve()` returns one of three typed results:
`SpendReservationReceipt`, `AlreadyReconciledOutcome`, or `Refused`.
`AlreadyReconciledOutcome` is reused because the domain already defines it as
A1's idempotent *"no-op returning the recorded outcome"*; introducing a second
type for the same state would duplicate vocabulary.

Work-key resolution receives the request's normalized UTC `now`, selects
`lease_expires_at` and `actual_cost`, and applies this table to the latest family
row:

| Persisted state | Condition | Reservation result | Permitted side effects |
|---|---|---|---|
| `reserved` | `lease_expires_at >= now` | Existing receipt | None; reuse the existing debit |
| `reserved` | `lease_expires_at < now` | `Refused(EXPIRED_NO_RETRY)` | None; the sweeper remains the only abandoned-expiry writer |
| `reconciled` | Recorded actual present | `AlreadyReconciledOutcome(actual_cost=...)` | None |
| `expired_spent` | Any | `Refused(EXPIRED_NO_RETRY)` | None |
| `released` | Any | Continue under the next family key | A fresh guarded reservation may be taken |

Equality remains live deliberately: the domain reclaim decision and sweeper
predicate both define expiry as `lease_expires_at < now`. An expired-but-unswept
row remains `reserved` until the sweeper settles it, but its existing debit still
reduces headroom and no paid call may reuse it. This fails closed without moving
the sweeper's write responsibility into the reservation path.

The worker handles `AlreadyReconciledOutcome` before dispatch. It returns
`HandlerResult(state=JobState.SUCCEEDED)` with `already_reconciled=True`, the
recorded `actual_cost`, and `actual_is_estimated=False`; it does not call the
provider or any settle method. A `reconciled` row with `actual_cost=None` violates
the state's meaning. Fail closed with `RuntimeError`; do not report success,
invent a figure, or call the provider.

## Scope fence

Included files:

- `python/smartmatch_persistence/smartmatch_persistence/spend.py`
- `services/worker/smartmatch_worker/paid_extraction.py`
- `tests/unit/test_spend_persistence.py`
- `tests/unit/test_paid_extraction_handler.py`
- `tests/integration/test_spend_reservation.py`
- `README.md` and a focused verification record under `docs/testing/`

Excluded: migrations, the missing sweep index, integration-conftest cleanup,
`main.py` or edition/config wiring, live providers, credentials, production
ceilings, network calls, unrelated refactors, generated contracts, deployment,
merge, and push.

## Task 1 — pin the two production failures before changing source

**Tests first**

1. In `tests/unit/test_spend_persistence.py`, extend the redelivery-row helper
   with `lease_expires_at` and `actual_cost`. Add cases proving an expired
   `reserved` row returns `EXPIRED_NO_RETRY`, equality at `now` still returns the
   original receipt, and `reconciled` returns `AlreadyReconciledOutcome` carrying
   the stored actual.
2. In `tests/unit/test_paid_extraction_handler.py`, widen the recording service's
   reserve result type. Add a reconciled-redelivery test asserting `SUCCEEDED`,
   the recorded actual, `already_reconciled=True`, and no provider, reconcile, or
   timeout call. Add the missing-actual fail-closed case.
3. Run the focused tests against `e4d808e` before editing production code and
   record their exact failures in
   `docs/testing/adr0015-a1-spend-persistence-verification.md`.

```bash
.venv/bin/pytest \
  tests/unit/test_spend_persistence.py \
  tests/unit/test_paid_extraction_handler.py -q
```

**Green implementation**

1. In persistence, widen the public and internal result unions, pass normalized
   `now` into work-key resolution, select both missing columns, and implement the
   approved state table. Update docstrings that currently say every refusal is a
   budget failure.
2. In the worker, pass `AlreadyReconciledOutcome` through the reservation helper
   and branch before `_dispatch_and_settle`. Build the replay summary only from
   durable command fields and the recorded actual; do not label the newly
   recomputed estimate as the historical estimate.

```bash
.venv/bin/pytest \
  tests/unit/test_spend_persistence.py \
  tests/unit/test_paid_extraction_handler.py \
  tests/unit/test_spend.py -q
make format-check lint typecheck imports
```

## Task 2 — correct and strengthen PostgreSQL coverage

Edit only `tests/integration/test_spend_reservation.py`.

1. In the all-or-nothing case, create the tenant-day bucket with its immutable
   ceiling already set to `Decimal("1.5000")`. The second estimate must fit the
   job ceiling and exceed the stored day headroom. Assert the refusal names
   `tenant_day`, the job bucket retains only the first debit, and the reservation
   count remains one.
2. Add expired-but-unswept redelivery: reserve with a lease ending before the
   redelivery request's `now`, do not run the sweep, then assert
   `EXPIRED_NO_RETRY`, unchanged buckets, unchanged row count, and the original
   row still `reserved` for the sweep.
3. Change reconciled redelivery to expect `AlreadyReconciledOutcome` with the
   recorded actual, one row, and no new bucket movement.
4. Replace the sequential reconcile test with two sessions racing the same
   receipt. Use a test-scoped barrier immediately before the real `_settle` call
   so both services have read `reserved`; do not replace the SQL with a fake.
   Assert exactly one `ReconciledOutcome`, one
   `Refused(ALREADY_TERMINAL)`, and one actual posting across all three buckets.

```bash
make test-integration
```

Collection or thirteen skips is not a passing result. PostgreSQL 16 must execute
the assertions before this task is reported green.

## Task 3 — establish fail-before evidence

Create `docs/testing/adr0015-a1-spend-persistence-verification.md`. Record the
commit, environment, command, exact result, and restoration check for each probe:

| Probe | Required failing evidence |
|---|---|
| Pre-fix expired redelivery | New unit test receives a receipt instead of `EXPIRED_NO_RETRY` |
| Pre-fix reconciled replay | Persistence returns `Refused`; worker raises `BudgetFailure` |
| Remove guarded insert source predicate temporarily | Fresh over-ceiling integration test admits the reservation |
| Remove `DO UPDATE` ceiling predicate temporarily | N/K concurrency test admits too many reservations or exceeds the ceiling |
| Remove `_settle`'s `state='reserved'` predicate temporarily | Concurrent reconcile test double-posts or fails a bucket invariant |

Use `apply_patch` for each temporary mutation and its reversal. Never stage or
commit a mutant. After every probe, run `git diff --check` and inspect
`git diff` to prove only the intended implementation remains. If PostgreSQL is
unavailable, mark the three SQL probes `NOT RUN — PostgreSQL unavailable`; do not
replace them with mocks or claim them from static inspection.

## Task 4 — restore README authority and run final gates

Update `README.md` from fresh measurements after the tests settle:

1. Add the spend state machine, reservation service, conservative sweeper, and
   their unit/integration coverage. Add the synthetic paid-provider seam and
   opt-in worker handler without implying `main.py` registers them.
2. Keep live paid extraction in the proposed/absent table: synthetic only,
   unwired in the shipped registry, still gated on live-provider/A3 confirmation,
   an edition/config gate, credentials, and production ceilings.
3. Recompute every aggregate and lane count used in README. Do not copy the old
   `789`, the pre-remediation `1811` collection snapshot, or an earlier
   `1260 passed` report.
4. Describe PostgreSQL-backed spend tests as executed only if PostgreSQL 16 ran
   them. Otherwise state that they are collected but unexecuted and keep merge
   blocked.

```bash
.venv/bin/pytest tests/ --collect-only -q
make test
make test-integration
make format-check lint typecheck imports
git diff --check
git status --short
```

## Acceptance criteria

- Expired-but-unswept redelivery makes zero paid calls, takes zero new debit,
  creates zero rows, and returns `EXPIRED_NO_RETRY`; equality at expiry remains
  reusable.
- Reconciled redelivery returns the stored actual as successful idempotent
  completion and makes zero provider or settle calls.
- The all-or-nothing test refuses against the persisted day ceiling and leaves
  the earlier job debit unchanged.
- Two concurrent reconciles post the actual exactly once across all three
  buckets, with one winner and one typed lost-race refusal.
- README capability claims and counts match fresh commands, and the verification
  record distinguishes pass, fail, skip, and not-run evidence.

## Validation truth table

| Environment | What may be reported | Completion status |
|---|---|---|
| PostgreSQL 16 available; focused mutations fail; integration and local gates pass | Exact pass/fail counts and mutation evidence | Remediation locally verified; still no merge/push/deploy authority |
| PostgreSQL unavailable; unit/static/local gates pass; integration skips or is unrun | Unit/static gates pass; PostgreSQL and SQL mutations `NOT RUN` | Code may be implemented, but remediation remains blocked from merge |
| PostgreSQL runs and any assertion fails | Exact failing node and output | Not complete; fix within this scope and rerun |
| Test collection fails | Collection failure only | Not complete; no test-count or integration claim |

No step in this plan authorizes pushing, merging, deploying, enabling a paid
command in the shipped worker, configuring production, or calling a live
provider.
