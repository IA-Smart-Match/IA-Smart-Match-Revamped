# ADR-0005 — The transactional outbox, and claiming with a CTE

**Status:** Accepted — amended 20 August 2026, see [Amendment](#amendment--20-august-2026-the-invariant-had-two-halves-and-only-one-was-guarded) below
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

## Amendment — 20 August 2026: the invariant had two halves, and only one was guarded

Landed with J12 (`smartmatch_persistence/outbox.py`,
`smartmatch_worker/dispatcher.py`). The decision above is unchanged: the outbox
is still the seam, claiming is still a CTE with `FOR UPDATE SKIP LOCKED`, the
lease is still the only timer, and the lag metric still shares the claim
predicate. What changes is the statement of the invariant, which was true and
incomplete, and one sentence in Consequences, which was simply wrong.

**"The invariant" above states one invariant where there are two.** It says a
`leased` row must never carry a NULL lease, because such a row satisfies no
`lease_expires_at < now` comparison and is therefore permanently unclaimable —
"invisible work, silently stuck, with no symptom except a job that never
finishes". That is correct. It is also not the only way to reach that state.

`_claimable_predicate` requires **two** things of a leased row: a lease in the
past, *and* `dispatch_attempts < MAX_DISPATCH_ATTEMPTS`. A row can fail the
second half just as permanently as the first. `claim_batch` returns the
post-increment attempt count, so the fifth claim leaves the row at exactly
`MAX_DISPATCH_ATTEMPTS`, and `5 < 5` is false. If the dispatcher then stops
before recording an outcome — a killed process, an evicted pod, an OOM, a drained
node, or a failure-write that itself failed — the row stays `leased` with a lease
that expires and is never looked at again. Identical symptom, different half of
the same predicate. The honest statement is:

> **A `leased` row must always be claimable in the future:** it must carry a
> non-NULL lease **and** have attempts remaining. Whichever half fails, the row
> is invisible work.

`mark_failed` upholds both halves for every row it touches — it is the writer
that moves a row to terminal `failed` when attempts run out. The gap was never in
`mark_failed`; it was that nothing upheld the invariant for a row `mark_failed`
was never reached for.

**Consequences said "a command that commits is a command that will eventually be
attempted".** Read strictly that remained true — a stranded row *had* been
attempted, five times. Read as the guarantee anyone actually relies on, that a
committed command eventually reaches a terminal state an operator can see and act
on, it was false on the last attempt: the row stayed `leased` and invisible, the
job stayed `queued`, and `TRANSITIONS[QUEUED]` — `{dispatched, cancelled,
failed_provider}` — has no route to `redrive_pending`, so
even the re-drive command answered 409 on it forever. The state that commit
`2564d33` added the `queued -> failed_provider` parking to eliminate was
reachable by a route that parking could not see.

**What closes it.** `_stranded_predicate` — placed immediately beside
`_claimable_predicate`, because the two are only correct read together, and the
gap between them is where work went missing — and `reclaim_stranded`, which
writes such rows off as `failed` with the lease cleared, using the same CTE and
`SKIP LOCKED` shape and for the same reasons. `OutboxDispatcher.reclaim_stranded`
pairs that with the job's `queued -> failed_provider` transition in one
transaction, exactly as `_record_failure` does at exhaustion, so a parked row
never sits beside a `queued` job. It runs at the top of every `run_once`.

Two properties of the predicate are deliberate and are asserted rather than
assumed. It requires an **expired** lease, so a live dispatcher's row is never
written out from under it. And a `leased` row carrying *no* lease is skipped,
because NULL satisfies no comparison — the first invariant above says such a row
cannot exist, and if one ever does, its state is not understood, and writing off
work nothing can explain is worse than leaving it to be found.

**Where the reclaim runs, and the constraint that leaves.** It rides `run_once`
rather than living in a scheduled sweeper, because nothing in this system runs on
a timer yet (backlog J8) and a standalone sweeper would have been dead code the
day it was written. The coupling this creates is real and is recorded against J8
rather than buried here: **a dispatcher that is not running is precisely the
condition that strands rows, and is then also the condition under which nothing
reclaims them.** Whatever schedules the dispatcher must therefore also be what
makes the reclaim run, and J9's sweep for jobs stuck in `running` belongs in the
same pass — one place to look, one metric surface for work that had to be
rescued.

**An expired lease is not proof the holder is dead, and the reclaim needed a
guard for that.** The predicate's expired-lease requirement bounds how long a
dispatcher may *hold* a row; it says nothing about how long Cloud Tasks may take
to answer. So with two instances and a slow batch, dispatcher A can still be
mid-enqueue on a row dispatcher B has just written off, and A's evidence write
would land on a terminal row — back to `dispatched` while the job stays
`failed_provider`, because A's conditional `queued -> dispatched` transition
no-ops against a job B has already parked. A `dispatched` row beside a parked
job is the same "nothing would reconcile" state the reclaim shares a transaction
to avoid, produced by the mechanism added to avoid it.

The answer is compare-and-set on the late writer, not a longer lease — a longer
lease shrinks the window without closing it, and lengthening it also lengthens
how long genuinely dead work stays invisible. `mark_dispatched` and `mark_failed`
now move a row **only while it is still `leased`**, the same discipline
`JobRepository.claim` and every conditional job transition already use. A
zero-row result is not an error: it is a dispatcher discovering its work was
written off. It is logged at `warning`, and the row is counted `failed` for that
pass, because that is what the database now says.

**Losing the compare-and-set is two situations, not one, and they call for
opposite responses.** The row may have been reclaimed — the job is parked, no
worker will touch it, and a human must re-drive it. Or a peer dispatcher may have
claimed it once this one's lease expired and finalised it correctly, which is the
ordinary recovery path the deterministic name exists to make safe. The zero-row
result looks identical in both. So the row's status is read before anything is
reported: `failed` is the reclaim, `dispatched` is a peer that won. A peer's win
is counted `already_existed` — the bucket that exists so "a healthy recovery does
not look like an incident" — and logged at `info` with no advice to act, because
telling an operator to re-drive a job that is already running duplicates live
work, the one outcome ADR-0007 is built to prevent. Anything else is logged
without a diagnosis rather than guessed at.

**Both** writers make that distinction, not just the dispatch one. `mark_failed`
loses its compare-and-set to a healthy peer as readily as to the sweep, so
`_record_failure` reads the status too. Having the three-way split in one writer
and not its twin would be worse than not having it, because the next reader would
reasonably assume both paths had been considered.

What each guard protects differs, and the asymmetry is worth stating. For
`mark_dispatched` it is the **status** — without it the terminal row is
resurrected. For `mark_failed` the status was never at risk: a late failure-write
on a reclaimed row necessarily carries exhausted attempts, so it writes `failed`
with a cleared lease, which is what is already there. What it protects is the
**explanation**, since `last_error` would otherwise be replaced by that attempt's
queue error — exactly the misleading text the reclaim exists to remove.

**The guard is a liveness test, not an ownership test, and the difference is
recorded rather than glossed.** `status = 'leased'` proves someone holds the row,
not that the caller does. That closes the race against the reclaim, whose rows
are `failed`. It does not close the race against a peer that re-claimed the row,
whose own claim satisfies `leased` — a stale failure-write still lands there,
truncating the peer's lease to an older attempt's backoff and burning an extra
attempt. Closing that needs the row to carry who claimed it, which is a schema
change; tracked as **J17**. The gap pre-dates these guards.

**Exactly-once was never at risk in this race, and the fix does not claim
otherwise.** The task may genuinely exist in the queue. It executes nothing: the
job is `failed_provider`, and `JobRepository.claim` moves only a `dispatched`
job, so the delivery is acknowledged and does no work. The defect was the
inconsistent state and the work made invisible by it. Note also that a re-drive
is safe here for the same reason and *not* because of the deterministic task
name — ADR-0007 has a re-drive derive a **new** generation name precisely so it
does not dedupe against a possibly-live original.

**The sweep cannot stop dispatch.** `run_once` guards the reclaim call: the sweep
is janitorial, it takes job-row locks other paths also take, and a deadlock or
lock timeout in it must not cost a healthy row its dispatch. `run_once`'s
contract is that only a failed *claim* aborts a pass, and the reclaim is not the
claim. On failure it is logged and `reclaimed` stays zero, so a pass never
credits itself with work it did not do.

**Two rules about reporting it, both learned the hard way.** A reclaim is logged
only *after* its transaction commits, and only about what the commit did: the
per-row lines were being written inside the loop, so a deadlock or a failed
commit part-way through a batch left up to `batch_size` WARNINGs announcing rows
as reclaimed while every one of them stayed `leased` and the pass reported zero.
The line also reports what the job transition actually returned rather than
assuming it — a job that has moved on, cancelled or already advanced, is not
parked by this sweep, and saying so would describe a write that did not happen.

And a reclaim that has committed survives whatever follows it. If `claim_batch`
then raises, `run_once` still propagates that — a batch that could not be claimed
must reach the poll loop — but the committed count is logged and attached to the
exception as a note, so it travels with the traceback. Dropping it would lose the
signal exactly when it matters most: a database under enough strain to fail a
claim is the same database that strands rows.

**The count is reported, not silent.** `DispatchOutcome.reclaimed` sits
deliberately outside the `claimed == dispatched + already_existed + failed`
identity: a reclaimed row was not claimed on this pass, and it reached none of
the three outcomes — its whole problem is that it reached none. It should
normally be zero, and a rising count is a statement about the dispatcher's own
health rather than about the queue's.
