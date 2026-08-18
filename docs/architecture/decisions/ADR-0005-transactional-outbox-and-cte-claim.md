# ADR-0005 — The transactional outbox, and claiming with a CTE

**Status:** Accepted
**Date:** 18 August 2026
**Contract:** Architecture v1.1 §1.6, §4.1

## Context

Accepting a command means two writes to two systems: a job row in PostgreSQL and
a task in Cloud Tasks. **They cannot be made atomic.** Whichever order they are
attempted in, there is a point at which the process can die and leave the two
disagreeing:

* Job first, then task — a crash in between leaves a job that nothing will ever
  execute. The work is lost, and lost *silently*: the client received its job id
  and will poll a job that never moves.
* Task first, then job — a crash in between leaves a task referencing a job that
  does not exist. The worker picks it up and finds nothing.

Neither is a rare window. Cloud Run terminates instances routinely, and the
provider call is the slow part of the request, so the window is exactly where the
process is most likely to be interrupted.

The failure to avoid is the first one. A duplicate task can be defended against
downstream; work that no longer exists anywhere cannot be recovered by anything,
because nothing knows it is missing.

## Decision

The intent to dispatch is written to `outbox_record` in the **same transaction**
as the job. `OutboxRepository.enqueue` takes the caller's session and does not
commit, precisely so that it cannot commit separately. A separate dispatcher then
moves durable intents into Cloud Tasks.

This does not make the two systems atomic — nothing can. It converts the problem
into one PostgreSQL commit plus a retryable follow-up, so every crash point has a
recovery path:

* before commit — nothing happened, and the command was never accepted;
* after commit, before dispatch — the row is `pending` and the next poll finds
  it;
* mid-dispatch — the lease expires, another dispatcher retries, and the
  deterministic task name (ADR-0007) makes the retry a no-op if the task was in
  fact created before the crash.

Both v1.1 §4.1 scenarios are exercised directly, in
`tests/integration/test_outbox_dispatcher.py`.

## Claiming: `FOR UPDATE SKIP LOCKED`

`claim_batch` selects claimable rows `FOR UPDATE SKIP LOCKED` and stamps a lease
on them. A row is claimable when it is `pending`, or `leased` with a lease
already in the past, and has attempts remaining — one predicate,
`_claimable_predicate`, shared by the claim query and by the lag metric so a row
can never be claimable but uncounted, or counted but unclaimable.

`SKIP LOCKED` is what lets more than one dispatcher run. Without it a second
dispatcher blocks on the rows the first has locked and contributes no throughput
— it waits, then claims rows already dispatched. With it, each instance takes a
disjoint batch and needs no coordination, no leader election, and no lock
service. `test_concurrent_dispatchers_claim_disjoint_batches` holds two real
overlapping transactions open and asserts the batches do not intersect.

Recovery uses the same mechanism rather than a new one. Nothing detects that a
dispatcher died; its lease simply elapses and the row becomes claimable again.
There is no liveness protocol to get wrong, and no state that is correct only
while some monitor is running.

## Why the claim is a CTE

The claim materializes its selection in a **common table expression** and updates
by joining against it. It is not written as:

```sql
UPDATE outbox_record SET ... WHERE id IN (
    SELECT id FROM outbox_record WHERE ... LIMIT n FOR UPDATE SKIP LOCKED
)
```

That form is the one most references reach for, and it is wrong here. PostgreSQL
cannot hash a subplan that contains `FOR UPDATE`, so the subquery is not
evaluated once into a set — it may be re-executed while the `IN` is being
evaluated, and each execution takes a *fresh* batch of up to `n` currently
claimable rows. The `UPDATE` then touches far more rows than `n`.

**This was observed here, not read about.** With five pending rows and a claim of
`limit=2`, the subquery form claimed all five. The bound was not merely
approximate; it was absent. `test_batch_size_is_respected` is the regression
guard: it accepts five commands, claims with `batch_size=2`, and asserts exactly
two are claimed and three remain.

The consequence of an unbounded claim is not cosmetic. `batch_size` is what keeps
one dispatcher pass from taking a whole backlog, and every claimed row has a
lease running while its slow provider call waits its turn — so a claim that
ignores its limit is also a claim whose later rows may have their leases expire
before they are ever attempted, handing them to another dispatcher while this one
still intends to dispatch them.

## The lease as the backoff timer

When a dispatch fails with attempts remaining, `mark_failed` re-arms the row as
`leased` with `lease_expires_at` set into the future by `backoff_for(attempts)` —
exponential, `2 ** attempts` seconds, capped at 300.

No `next_attempt_at` column was added. The claim predicate already treats a live
lease as "not claimable yet", which is exactly what a backoff timer needs to
mean. Reusing the lease gives backoff for free; a second column would give the
same behavior plus a second thing that can disagree with the first — and the lag
metric would then have to know about both to avoid reporting a row as stuck when
it is merely waiting.

Backoff is correctness here, not polish. Re-arming immediately meant a dispatcher
polling every couple of seconds consumed all five attempts inside about ten
seconds and parked the work permanently, for an outage that might have cleared a
minute later. A survivable blip became lost work requiring a manual re-drive.
`test_dispatch_failure_backs_off_before_retrying` asserts the row is not
claimable immediately after a failure.

### The invariant

**A `leased` row must never carry a NULL lease.** The predicate matches a leased
row only when `lease_expires_at < now`, and NULL satisfies no comparison, so such
a row is permanently unclaimable — invisible work, silently stuck, with no
symptom except a job that never finishes. Both writers uphold it from opposite
directions: `mark_failed` sets a future lease when re-arming and clears the lease
only when moving the row to the terminal `failed` status, and `mark_dispatched`
clears the lease at the same moment it sets `dispatched`, so a completed row
cannot look claimable again the instant its old timer elapses.

The `failed` and `dispatched` statuses hold the mirror-image rule: terminal, and
therefore no lease at all. `test_exhausted_row_is_parked_without_a_lease` and
`test_dispatch_records_the_job_transition_and_evidence` assert
`lease_expires_at IS NULL` for each.

## Consequences

**Good.** A command that commits is a command that will eventually be attempted,
without an inbox, a broker, or a distributed transaction. Concurrency needs no
coordination beyond what PostgreSQL already provides. Crash recovery needs no
liveness detection. Dispatch lag is measurable from the same predicate that
governs claiming, so the metric and the behavior cannot drift apart.

**Cost.** Dispatch is now polled rather than immediate, so every command carries
the poll interval as added latency before its work begins. Nothing schedules the
dispatcher yet — `run_once` and `lag` exist and nothing calls them on a timer
(backlog J8) — so at present dispatch happens only when something invokes it.

**Cost.** `MAX_DISPATCH_ATTEMPTS` rows accumulate as `failed` and require a human.
That is deliberate: dispatch failures are usually systemic — a misconfigured
queue, denied credentials — and retrying such a row forever fills the logs
without ever succeeding. It does mean the outbox has a terminal state that only
an operator can clear, and the re-drive command that would clear it is not built
yet (backlog J4).

**Cost.** `outbox_record` grows without bound; `dispatched` rows are never
removed. The partial index `ix_outbox_claimable` keeps the dispatcher's own
queries proportional to claimable rows rather than to history, so the *poll* does
not degrade as the table grows. Retention for the table itself is unaddressed.

## Alternatives considered

**Create the Cloud Tasks task inside the request handler.** Rejected: it is the
non-atomic ordering above, and it also puts a provider call in the browser
request path, which v1.1 §1.6 forbids and which ADR-0003 records as one of the
legacy's architectural defects rather than a performance problem.

**Advisory locks instead of row locks.** Rejected. It requires a lock key
convention, correct release on every path including the crash path, and gives no
better concurrency than `SKIP LOCKED` — which is already the row-level version of
the same idea, with release handled by transaction end.

**A dedicated `next_attempt_at` column.** Rejected, per the section above: a
second timer with the same meaning as the one already present.

**A message broker with its own delivery guarantees.** Not evaluated in depth.
The problem is not delivery — Cloud Tasks delivers — it is the seam between the
database commit and the enqueue, which a broker does not remove. It would have to
be replaced by a broker-side transaction the application still cannot join.
