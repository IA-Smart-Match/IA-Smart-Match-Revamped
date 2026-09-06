# Plan — ADR-0015 A1 spend-control persistence (V1)

**Spec:** `docs/architecture/decisions/ADR-0015-charge-quota-before-refusal.md`,
Amendment A1 (from the `# Amendment A1` heading to end of file). A1 is the
binding authority; this plan is its argument. Where this plan and A1 disagree,
A1 wins.

**What already exists (do not rebuild):**
- `db/migrations/versions/0010_spend_reservation.py` — `spend_ceiling_bucket`,
  `spend_reservation`, all constraints.
- `python/smartmatch_persistence/smartmatch_persistence/schema.py:585-678` —
  Core table mirrors for both tables.
- `python/smartmatch_domain/smartmatch_domain/spend.py` — pure state machine,
  receipt/snapshot/outcome dataclasses, `derive_work_key`, bucket key helpers,
  `BUCKET_LOCK_ORDER`, `reconcile`, `expire_abandoned`, `expire_on_timeout`,
  `release_before_dispatch`, `dispatch`.
- `tests/unit/test_spend.py` — 466 lines of domain unit tests.

**What is missing:** every database write. There is no
`smartmatch_persistence/spend.py`, no sweeper, no provider seam, no
integration test.

## Global Constraints

1. **A1 obligation 1 — reserve.** The debit against the three ceilings
   (`job`, `tenant_day`, `tenant_month`) is **all-or-nothing**. The recorded
   schema choice (migration `0010` docstring) is **three normalized rows, three
   sequential guarded writes inside one transaction**, locked in the fixed
   order `smartmatch_domain.spend.BUCKET_LOCK_ORDER` — `job`, then
   `tenant_day`, then `tenant_month` — never a caller-chosen order. Any bucket
   refusing means the whole transaction rolls back and nothing moved.
2. **Every ceiling write is a single guarded statement.** `SELECT`-then-compare
   -then-`UPDATE` is non-conforming, per A1 *"A reservation that is not a single
   conditional write is not a reservation."*
3. **The insert path is guarded too.** A1 is explicit that ADR-0006's shape
   guards only `DO UPDATE` and that copying it verbatim reintroduces the defect:
   a first reservation against a key with **no row**, for an estimate larger
   than the ceiling, **must be refused**. Guard the `INSERT`'s source row.
4. **The reservation commits in its own transaction, before the paid call.**
   No shared transaction that can roll the debit back after money moved.
5. **Money is `Decimal` / `NUMERIC(12,4)`. Never `float`.** No `float()` on a
   dollar figure anywhere in this work.
6. **An estimate is never recorded or reported as an actual.** The
   `actual_is_estimated` column carries that distinction; timeout and sweep
   paths always set it `True`.
7. **The sweep never releases.** Any expired unreconciled reservation becomes
   `expired_spent` at the reserved maximum. No exception.
8. **Redelivery semantics, by state** (A1 *The reservation row's states*):
   `reserved` → recognise and reuse (mint a receipt for the existing row, do
   not add a second debit); `reconciled` → refuse, no-op returning the recorded
   outcome; `expired_spent` → refuse with `RefusalReason.EXPIRED_NO_RETRY`, no
   reuse and no silent fresh debit; `released` → treat as never-charged and
   re-reserve normally.
9. **Reconciliation is idempotent.** The sweep and a late worker can reach the
   same row; neither may double-record.
10. **Review findings are emitted at most once per reservation**, via a guarded
    `UPDATE ... WHERE review_flagged_at IS NULL`.
11. **Layering (import-linter, `pyproject.toml`):** `smartmatch_persistence`
    may import `smartmatch_domain`, never the reverse; persistence may not
    import `fastapi`, `starlette`, `httpx`, `requests`, `subprocess`, or
    `smartmatch_providers`.
12. **Style gates:** `make format-check lint typecheck` must pass. Strict mypy,
    ruff, black. Type annotations on every signature. Google-style docstrings
    matching the density of `rate_limit.py` and `spend.py`.
13. **No live provider.** Synthetic/fixture providers only. No network call, no
    credentials, no OpenRouter/Groq adapter. That is out of scope and blocked.
14. **PostgreSQL is not reachable in the dev sandbox.** Integration tests must
    be written under `tests/integration/` following that package's existing
    skip-when-unreachable conftest pattern, and will execute in CI
    (`.github/workflows/verify.yml` provides `postgres:16`). Do not claim you
    ran them locally if they skipped — report the skip.

## Task 1 — `SpendReservationService.reserve`

Create `python/smartmatch_persistence/smartmatch_persistence/spend.py`.

Model the module on `smartmatch_persistence/rate_limit.py`: module docstring
explaining the rule and what it costs, `__all__`, frozen dataclasses, a service
class taking a `Session`.

Implement:

- `@dataclass(frozen=True, slots=True) class SpendCeilings` — `job`,
  `tenant_day`, `tenant_month`, each `Decimal`. Validate non-negative on
  construction.
- `@dataclass(frozen=True, slots=True) class ReservationRequest` — `tenant_id`,
  `job_id`, `provider`, `unit_of_work`, `estimate: Decimal`, `now: datetime`,
  `lease: timedelta`.
- `class SpendReservationService` with `__init__(self, session: Session)`.
- `reserve(request: ReservationRequest, ceilings: SpendCeilings) ->
  SpendReservationReceipt | Refused`.

`reserve` must:

1. Derive `work_key` via `smartmatch_domain.spend.derive_work_key`, and the
   three bucket keys via `job_bucket_key`, `tenant_day_bucket_key`,
   `tenant_month_bucket_key` (day/month derived from `request.now` in UTC).
2. Look up an existing `spend_reservation` row by `work_key` and apply
   Global Constraint 8's per-state rule **before** touching any bucket.
   Reusing a live `reserved` row mints a receipt from that row's existing
   `lease_token` and debits nothing.
3. Otherwise debit all three buckets in `BUCKET_LOCK_ORDER`, one guarded
   `INSERT ... ON CONFLICT ... DO UPDATE` per bucket, where:
   - the insert's source row is guarded by `WHERE :estimate <= :ceiling`, and
   - the `DO UPDATE` is guarded by
     `WHERE bucket.reserved + bucket.spent + :estimate <= bucket.ceiling`,
   - `RETURNING` yielding no row **is** the refusal
     (`RefusalReason.CEILING_EXCEEDED`, naming which bucket refused).
   On any refusal, roll back the transaction so no bucket moved, and return
   `Refused`.
4. Insert the `spend_reservation` row (`state='reserved'`, fresh
   `lease_token=uuid4()`, `lease_expires_at=request.now + request.lease`, the
   three bucket keys stored on the row).
5. `session.commit()` — the reservation owns its transaction (Constraint 4).
6. Return a `SpendReservationReceipt`.

Handle the `released` → re-reserve case by writing a **new** reservation row
rather than resurrecting the terminal one (`released` is terminal; a row cannot
leave it). Choose a mechanism that satisfies `uq_spend_reservation_work_key`,
and **document the choice and its failure mode in the module docstring** — that
documentation is a deliverable.

Add unit-testable coverage where a database is not required, and note in your
report which behaviors can only be proven in Task 5's integration tests.

## Task 2 — settle paths: reconcile, timeout, release

Extend `smartmatch_persistence/spend.py`. Every method loads the row, builds
the matching domain snapshot, calls the **pure** domain function for the
decision, and only then writes. Do not re-implement any decision the domain
module already makes.

- `reconcile(receipt, *, actual_cost: Decimal, now: datetime) ->
  ReconciledOutcome | AlreadyReconciledOutcome | Refused`
  Guarded `UPDATE ... WHERE id = :id AND state = 'reserved'` setting
  `state='reconciled'`, `actual_cost`, `actual_is_estimated=False`,
  `settled_at=now`, `lease_token=NULL`. Bucket math on all three buckets from
  the row's stored keys: move `reserved -= estimate`, `spent += actual_cost`.
  An overage posts in full past the ceiling — never truncate (A1).
- `expire_on_timeout(receipt, *, now) -> ExpiredOutcome | Refused`
  Writes `state='expired_spent'`, `actual_cost=estimate`,
  `actual_is_estimated=True`. Buckets: `reserved -= estimate`,
  `spent += estimate`.
- `release_before_dispatch(receipt, *, reason: str, now) -> ReleasedOutcome |
  Refused` — `state='released'`, `settled_at`, `lease_token=NULL`, and
  `reserved -= estimate` on all three buckets with **no** `spent` movement.
- `_flag_for_review(finding: ReviewFinding, *, now) -> bool` — guarded
  `UPDATE ... WHERE review_flagged_at IS NULL`; return whether this call is the
  one that flagged. Every path that produces a `ReviewFinding` routes through
  it, so a finding is emitted at most once per reservation (Constraint 10).

A guarded update matching zero rows is a lost race and returns a `Refused`, not
an exception.

## Task 3 — `SpendReservationSweeper`

Extend `smartmatch_persistence/spend.py` (or a sibling module if it exceeds
800 lines — say which you chose and why).

- `class SpendReservationSweeper` taking a `Session`, modelled on
  `execution.StalledJobSweeper` and `RateLimiter.sweep_expired`.
- `sweep(*, now: datetime, limit: int) -> Sequence[ReviewFinding]`.
- Selects `spend_reservation` rows with `state='reserved'` and
  `lease_expires_at < now`, builds an `AbandonedReservationSnapshot` (which
  deliberately carries no `lease_token`), calls
  `smartmatch_domain.spend.expire_abandoned`, and on `ExpiredOutcome` writes
  the same `expired_spent` shape Task 2's timeout path writes.
- **Never releases** (Constraint 7). Fails closed: a sweep that cannot reach
  the database raises rather than reporting a clean sweep.
- Each swept reservation is flagged for review through Task 2's
  `_flag_for_review`, so a re-run of the sweep emits no duplicate finding.
- Bounded by `limit` so one sweep cannot hold a long transaction.

## Task 4 — synthetic paid-provider seam and the A3 estimate constant

1. Create `python/smartmatch_providers/smartmatch_providers/paid.py`:
   - `A3_PRICE_PER_PROSE_PAGE: Final[Decimal]` = `Decimal("0.035")`, with a
     docstring naming it as **assumption A3**, its source
     (`docs/plans/prep/g3-limits-and-policy-options.md:221`), the date it was
     recorded, and that it is **unverified against any provider bill** — A1
     requires the constant carry its provenance in the code that uses it.
   - `estimate_max_cost(pages: int) -> Decimal` — the reserved maximum,
     `Decimal` arithmetic only.
   - `SyntheticPaidProvider` — fixture-backed, **no network**, whose call
     method takes a `SpendReservationReceipt` as a required, non-optional,
     non-`Any` parameter, so a call site that never reserved cannot type-check.
     It returns a synthetic cost and never reads a credential.
   - Registry wiring must refuse any edition other than fixture/synthetic,
     mirroring `registry._assert_fixture_only`.
2. Wire it end to end in the worker: a handler path that reserves, dispatches
   through `smartmatch_domain.spend.dispatch`, and reconciles — including the
   timeout branch. Follow `services/worker/smartmatch_worker/handlers.py`
   conventions and raise `BudgetFailure` on a refused reservation.
3. Unit tests for the estimate arithmetic and for the type-level refusal
   (`dispatch` with a non-receipt raises `TypeError`).

## Task 5 — integration and concurrency tests

Add `tests/integration/test_spend_reservation.py` using
`tests/integration/conftest.py`'s existing fixtures and skip behavior.

Must cover, at minimum:

1. **First reservation over ceiling, against a key with no bucket row, is
   refused** — the named test A1 requires for the guarded-insert hole.
2. All-or-nothing: an estimate the job ceiling admits but the day ceiling
   refuses moves **no** bucket, including the job bucket.
3. Concurrent reservations against one ceiling: N threads/sessions racing a
   ceiling that admits only K, asserting exactly K succeed and
   `reserved + spent <= ceiling` holds.
4. Fixed lock order under concurrency: interleaved reservations across the same
   three buckets complete without deadlock.
5. Redelivery per state: all four states from Constraint 8.
6. Reconcile idempotency: two reconciles record one actual.
7. Sweeper: an expired reservation becomes `expired_spent` at the maximum with
   `actual_is_estimated=True`, is never released, and a second sweep emits no
   second finding.
8. Overage: an actual above the estimate posts in full, `spent` exceeds
   `ceiling`, and the next reservation against that bucket is refused.

Report which tests skipped for lack of a database. Do not claim a passing
integration run that did not happen.
