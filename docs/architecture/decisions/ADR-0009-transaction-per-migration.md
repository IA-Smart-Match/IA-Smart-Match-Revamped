# ADR-0009 — One transaction per Alembic revision

**Status:** Accepted
**Date:** 24 August 2026
**Contract:** Architecture v1.1 §4.2 (expand / migrate / contract)
**Backlog:** F11

## Context

`db/migrations/env.py` wrapped `context.run_migrations()` in a single
`context.begin_transaction()` and did not set `transaction_per_migration`. One
transaction therefore spanned every pending revision in a run.

The visible consequence is a lock. Migration `0003` takes `ACCESS EXCLUSIVE` on
`user_account` before adding a unique constraint. Under a single run-wide
transaction that lock is held from the moment it is taken until the entire
`alembic upgrade` commits — not until `0003` finishes.

While `0003` is head these are the same instant, which is why the arrangement
was harmless when it was written and was documented rather than changed. It
stops being harmless the moment a `0004` exists: upgrading a live database from
`0002` would hold `user_account` locked across `0003`, `0004`, and every
revision after them in the same run, blocking every authenticated request for
the duration of the whole upgrade rather than for one index build.

The same boundary appears on the offline path. `alembic upgrade --sql` produced
one `BEGIN`/`COMMIT` pair around all three revisions, so a DBA applying a
reviewed script by hand reproduced the defect — on the route with a human
watching, who would reasonably assume the script matches what the tool does.

## Decision

Set `transaction_per_migration=True` on **both** `context.configure` calls in
`db/migrations/env.py`, online and offline.

Each revision is applied in its own transaction and commits with its own
`alembic_version` row.

## Rationale

The cost of this setting is that a failed multi-step upgrade leaves earlier
revisions committed instead of rolling the run back as a unit. That cost is
smaller than it sounds, and being precise about why is the substance of this
decision.

The failure state under per-revision transactions is not inconsistent. The
`alembic_version` row commits with its revision, so a failure at `0004` leaves
the database at `0003` and saying it is at `0003` — a valid, resumable state.
Fix the problem and run `alembic upgrade head` again. The all-or-nothing
arrangement produces a different valid state, not a safer one.

So the real question is not whether the failure state is consistent, but whether
an intermediate revision is a state this system can be in. This repository has
already answered that, in writing and twice: v1.1 §4.2's expand / migrate /
contract discipline requires every revision to be independently safe under a
rolling deploy, because during a rollout the old and new releases both run
against whatever schema is currently applied. A repository whose revisions must
each be independently safe is a repository that can sit at any revision.
All-or-nothing was protecting a property the contract already forbids relying
on.

The argument also gets weaker with time and never stronger. "One lock held
across every pending migration" costs more with every revision added, and much
more the day something is deployed.

**What would have to be true for the other choice to win**, recorded so the
decision can be revisited on evidence rather than reopened on instinct:

1. *A change that genuinely cannot be split across revisions is written as two
   revisions* — a DDL step plus a backfill that must be atomic with it. Such a
   change belongs in **one** revision, where it is atomic under either setting.
   This argues for a review rule, not for the global default.
2. *An operator who cannot be relied on to re-run `alembic upgrade head` after a
   failure.* Per-revision transactions make partial progress durable, which only
   helps if someone finishes the job. The answer is a runbook, not a transaction
   setting — and it is a real question for whoever builds the deploy pipeline,
   which does not exist yet.

The fallback the backlog named — running the locking revision on its own — is
weaker than either, because it depends on an operator remembering, and it does
not survive being forgotten once.

## Consequences

**Good.** A lock is released when its revision ends. A long upgrade does not
accumulate locks. A failed upgrade is resumable from where it stopped, and the
recorded version matches reality. The offline script now shows the same
boundaries the online path uses, so a reviewed script is an honest preview.

**Bad.** A multi-step upgrade that fails partway leaves earlier revisions
applied. Operators must re-run `alembic upgrade head` rather than assume a
failed run left nothing behind. This belongs in the deploy runbook when one is
written.

**Applying a generated script requires `ON_ERROR_STOP`.** This is the sharpest
edge the decision introduces, and it is on the offline path rather than the
online one.

`psql` continues after an error by default when reading a file. Under one
run-wide transaction that was survivable: the first failure poisoned the
transaction, every later statement was refused, and the final `COMMIT` acted as
a rollback, so nothing applied. Per-revision transactions remove that safety
net. A failed revision now rolls back alone, and the *next* revision's
transaction runs normally — its
`UPDATE alembic_version SET version_num = 'N' WHERE version_num = 'N-1'` matches
zero rows, which PostgreSQL does not treat as an error, so its DDL commits while
the recorded version stays behind.

The result is a database whose schema is ahead of its `alembic_version`, with no
failure reported to the operator. Reproduced against PostgreSQL 16: after an
induced failure in the second of three revisions, the third revision's table
existed and `alembic_version` still read the first.

Therefore:

```
psql -v ON_ERROR_STOP=1 -f upgrade.sql
```

This obligation belongs in the deploy runbook alongside "re-run
`alembic upgrade head` after a failure." Note that the alternative — keeping the
run-wide transaction for offline only — was rejected: it would make the reviewed
script stop matching what the tool does, on the one route with a human watching,
which is the defect this ADR set out to close.

**`CREATE INDEX CONCURRENTLY` still requires `autocommit_block()`.** This is the
conflation most likely to cause a run-time failure, so it is stated here rather
than left implicit. `transaction_per_migration=True` gives each revision *its
own* transaction. It does not give any revision *no* transaction.
`CREATE INDEX CONCURRENTLY` cannot run inside a transaction at all, and still
needs:

```python
with op.get_context().autocommit_block():
    op.create_index(..., postgresql_concurrently=True)
```

The two ideas sit next to each other in `0003`'s docstring. Anyone who assumes
this setting enables `CONCURRENTLY` will write a migration that fails when it
runs. `tests/unit/test_migration_transactions.py` asserts the property that
makes the assumption wrong.

**Every revision must be independently safe.** This was already required by
v1.1 §4.2; it is now also enforced by the migration mechanics rather than only
by review.

## Verification

`tests/unit/test_migration_transactions.py` generates the offline script and
asserts one `BEGIN`/`COMMIT` pair per revision, that the `user_account` lock is
held by exactly one revision, and that no revision emits `CONCURRENTLY` inside a
transaction. It needs no database: offline mode never connects, and the test
points at an unreachable URL to keep it that way.

The test covers `run_migrations_offline`. The online path is the same decision
at a call site three lines away, and while `0003` is head there is no
online-observable difference to assert — the lock is taken in the last revision,
so it is released at the end of the run either way. That is precisely what
"harmless while `0003` is head" means. Covering it would require racing an
upgrade against a second connection to observe an intermediate
`alembic_version`, which would be timing-dependent against migrations that
complete in milliseconds; a flaky test asserting a transaction boundary is worse
than no test. The online call site is covered by review.

## References

- `docs/plans/transaction-boundary-defects.md` §4 — the full analysis, including
  what was checked before changing the setting.
- `docs/plans/remaining-foundation-r1-work.md` — F11.
- `db/migrations/versions/0003_global_external_subject.py` — the lock, and the
  `CONCURRENTLY` guidance this ADR qualifies.
- ADR-0004 — hand-written schema; migration mechanics were out of its scope.
