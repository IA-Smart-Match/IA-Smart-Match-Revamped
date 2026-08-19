# ADR-0007 — Deterministic Cloud Tasks names as the deduplication mechanism

**Status:** Accepted — amended 19 August 2026, see [Amendment](#amendment--19-august-2026-the-re-drive-collision-is-resolved) below
**Date:** 18 August 2026
**Contract:** Architecture v1.1 §1.6, §3.1

## Context

ADR-0005 leaves one crash window open by design. The dispatcher enqueues a task,
then records that it did so in a separate transaction — necessarily separate,
because holding a database transaction open across a network call to Cloud Tasks
would pin a connection for the whole round trip. If the process dies between
those two steps, or if the enqueue call times out with no answer, the outbox row
still says the task was never created.

The recovery path is a retry. The question this ADR answers is what a retry does
when the first attempt actually *succeeded* and nobody recorded it.

With a randomly named task, the retry enqueues the work a second time. That is
the worst possible behavior: the duplicate is produced precisely in the ambiguous
case that retries exist to handle, so the mechanism meant to make crashes safe
becomes the mechanism that doubles the work. For a command that sends mail or
spends provider budget, "ran twice" is not a degraded outcome; it is a wrong one
that reaches people outside the system.

## Decision

The task name is a deterministic function of the job:

```python
digest = hashlib.sha256(f"{job_id}|{command_type}".encode()).hexdigest()[:40]
return f"sm-{digest}"
```

`derive_task_name` is called once by `OutboxRepository.enqueue`, which stores the
result in `outbox_record.task_name`, and the same inputs always produce the same
name. Cloud Tasks refuses to create a task whose name already exists, so a
retried dispatch after an ambiguous failure cannot enqueue the work twice — the
queue rejects it. `test_crash_after_task_creation_does_not_dispatch_twice`
reproduces exactly that state: it dispatches, forces the outbox row back to
`pending` as a crash would have left it, dispatches again, and asserts the queue
holds one task.

**`TaskAlreadyExists` is modeled as a success outcome, and deliberately not a
subclass of `TaskQueueError`.** This is a small piece of type design carrying a
real invariant. `TaskQueueError` means "transient, worth retrying". A rejected
duplicate is neither: retrying it will be rejected again, forever, and the work
is already enqueued. If `TaskAlreadyExists` inherited from `TaskQueueError`, any
caller catching retryable failures would swallow it by accident and retry a
condition that can never clear — burning the row's attempts and eventually
parking work that was in fact dispatched successfully. The dispatcher counts it
separately as `already_existed` for the same reason: it is the *expected*
recovery path, and folding it into failures would make a healthy recovery look
like an incident on the dashboard.

**The name is a hash rather than the raw job id.** Queue metadata is visible in
Cloud Console to anyone with queue-viewer access — a broader audience than those
authorized to see a tenant's jobs. A raw name would put a job id, and via
`command_type` a description of what is being done, in front of that audience.
The hash carries the same uniqueness with no readable content;
`test_task_name_does_not_leak_identifiers` asserts that neither the job id nor
the command's words appear in the derived name.

The name is also constrained at the database, before the queue ever sees it:
`outbox_record` carries `uq_outbox_task_name`, a global unique constraint. A
second attempt to write an outbox row for the same `(job_id, command_type)` is
refused by PostgreSQL rather than being discovered later by Cloud Tasks.

## Determinism at the queue is not sufficient

It is worth being explicit, because the deduplication is easy to over-trust.
Cloud Tasks delivers **at-least-once**. The same task — one task, correctly
enqueued exactly once — may be delivered to the worker more than once. No naming
scheme addresses that; the duplicate is a duplicate *delivery*, not a duplicate
task.

The guard against double execution is therefore elsewhere: `JobRepository.claim`
moves the job `dispatched -> running` with a conditional UPDATE that requires the
row still to be in `dispatched`. The first delivery matches and returns `True`.
The second matches nothing, returns `False`, and the worker acknowledges it
without re-running anything.

The two mechanisms defend different failure modes and neither substitutes for the
other:

| Failure | Defence |
|---|---|
| A dispatch retried after an ambiguous enqueue | Deterministic task name — the queue refuses the duplicate |
| One task delivered twice by the queue | Conditional `dispatched -> running` claim — only one delivery wins |

`test_duplicate_task_delivery_does_not_double_execute` covers the second row
directly: two `claim` calls against the same job, and only the first succeeds.

## Consequences

**Good.** The dispatcher can retry freely. Every crash point in ADR-0005 has a
recovery path that is either a no-op or the intended work, and the code that
takes those paths does not have to know which case it is in.

**Good.** `FixtureTaskQueue` models the dedupe faithfully — enqueuing a name
twice raises `TaskAlreadyExists` exactly as Cloud Tasks would — so the property
the design rests on is exercised in CI without a queue.

### The consequence that bites

Because the name is a pure function of `(job_id, command_type)`, **a job
re-driven under its original identifiers derives the same task name as its own
earlier attempt.** The queue treats the re-drive as a duplicate and discards it.
The job does not run, and nothing reports an error: from the dispatcher's point
of view a rejected duplicate is a success, so the row is marked `dispatched`, the
job advances, and the work never happens.

This is not hypothetical for the re-drive design. The domain state machine in
`smartmatch_domain.jobs` routes `REDRIVE_PENDING -> QUEUED` — back to the same
job id, which is the point of re-drive: attempt history is preserved and the job
keeps its identity. And `uq_outbox_task_name` means the attempt fails even
earlier, at the database, when a second outbox row for the same job and command
is written.

So determinism, which makes retries safe, makes re-drive unsafe under exactly the
identifiers re-drive wants to use. **This was a constraint on backlog item J4, not
a solved problem, when this ADR was written.** Whoever implements re-drive has to
make the task name differ across deliberate re-attempts while still being
identical across accidental retries of one attempt — and must not weaken the
property in the first table above while doing it. No design for that was
recorded here, and none should have been inferred from this ADR at the time.

**Resolved by `redrive_generation` — see the amendment below.**

Also worth stating: Cloud Tasks' name-based deduplication is a property of a live
queue, not a permanent registry, and this ADR does not assert how long a
completed name is retained. The dispatcher does not depend on unbounded retention
— its retries happen within a lease — but a re-drive arriving much later is
depending on behavior nobody here has verified. Verify it before relying on it in
either direction.

## Alternatives considered

**Random task names.** Rejected: it produces a duplicate in precisely the
ambiguous case the retry exists for. It would make re-drive trivial, which is the
trade the section above describes from the other side.

**Deduplicate in the worker only, with no naming scheme.** Rejected as
insufficient rather than wrong. The conditional claim does catch the duplicate,
so the work would not run twice — but the queue would then carry two live tasks
per affected job, both delivered, both authenticated, both consuming worker
capacity to discover there is nothing to do. Defending the same failure twice at
different costs is worth it when the cheaper defence is a hash.

**Include a timestamp or attempt counter in the name.** Rejected for the
dispatcher's own retries: any input that varies between attempts of the same
dispatch destroys the property this ADR exists to provide. It is a plausible
ingredient for J4's *deliberate* re-attempts, where varying the name is the goal
— which is a different decision, to be recorded when it is made.

## Amendment — 19 August 2026: the re-drive collision is resolved

Landed in `b0a6a48` (J4), alongside the re-drive command itself
(`python/smartmatch_persistence/smartmatch_persistence/redrive.py`,
`services/api/smartmatch_api/routers/redrive.py`). The decision above — a
deterministic name as the dedupe mechanism, and the conditional `claim` as the
separate defence against duplicate delivery — is unchanged and still holds. What
changes is `derive_task_name`'s signature:

```python
def derive_task_name(job_id, command_type, *, redrive_generation: int = 0) -> str:
    suffix = "" if redrive_generation == 0 else f"|r{redrive_generation}"
    digest = hashlib.sha256(f"{job_id}|{command_type}{suffix}".encode()).hexdigest()[:40]
    return f"sm-{digest}"
```

**Why a generation number, and not one of the alternatives this ADR already
rejected.** A timestamp or an always-incrementing attempt counter was rejected
above because it would vary the name *within* one dispatch attempt, which is
exactly the property this ADR depends on: the dispatcher must retry an ambiguous
enqueue under the identical name, or the deduplication guarantee is gone.
`redrive_generation` is different in kind, not degree — it varies only *between*
dispatches a human explicitly authorized, never within one:

* The dispatcher's own retries — `run_once` re-processing a row still `pending`
  or `leased`-with-an-expired-lease after a crash — never call
  `derive_task_name` at all. The name is computed once, in
  `OutboxRepository.enqueue`, and *stored* on `outbox_record.task_name`; every
  retry of that same row reads the stored value back. So "accidental repeat
  keeps the identical name" is not re-verified by the generation number, it is
  structurally untouched by it.
* `RedriveRepository.redrive` computes the next generation by counting the
  job's existing outbox rows (`_next_generation`) and passes it to `enqueue`,
  which derives a name that has never been used for this job before, and which
  `uq_outbox_task_name` will accept.

**Why generation `0` hashing byte-identically matters.** The suffix is empty
exactly when `redrive_generation == 0`, so the derived name for every job's
first, ordinary dispatch — which is the entire fleet of names any queue or
outbox row carries today — is bit-for-bit what the pre-amendment formula
produced. The change is additive rather than a migration: no existing
`outbox_record.task_name` value, and no task already live in Cloud Tasks, means
anything different under the new code. `test_task_names_differ_across_generations_but_are_stable_within_one`
(`tests/integration/test_redrive.py`) asserts both halves of this: generation 0
is unchanged, and generation 1 differs from it.

**What this does not change.** The two-defence table above — deterministic name
for an ambiguous *dispatch*, conditional claim for an ambiguous *delivery* — is
exactly as it was. Re-drive adds a third case to think about, not a third
defence: a *deliberate* repeat, authorized by a human, which now gets a
genuinely new name because it is genuinely new work, while an *accidental*
repeat of any single dispatch — original or re-driven — still resolves to one
name and one task, exactly as designed here.
