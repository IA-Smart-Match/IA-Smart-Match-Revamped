# ADR-0021 — The worker task-delivery contract is the acceptance test for any queue adapter

**Status:** Proposed
**Date:** 8 September 2026
**Contract:** Architecture v1.1 §1.6, §3.1; ADR-0005; ADR-0007
**Backlog:** Stage 2 AP-04; migration increment M7
**Findings:** `docs/architecture/risk-register.md` R-01;
`services/worker/smartmatch_worker/main.py` module docstring (lines 14–63);
`docs/architecture/current-system-topology.md` §1

## Context

Every production adapter in this system is unproven. Live Cloud Tasks, live
Routes, live Resend and the JWKS-to-real-issuer wiring have never executed;
`providers/registry.py:196,243,258,303` are four "not implemented in the
Foundation scaffold" refusals (R-01). The ports and their fixture and local
implementations are well tested. The production side of each seam is not.

R-01's remediation is unusual and correct: *do not pre-build; do write down what
the adapter must satisfy, so it is measured rather than improvised.* This ADR
does that for the task queue, which is the seam with the most already written
down and the most to lose.

What is already written down is `services/worker/smartmatch_worker/main.py`'s
module docstring. It is not a description of the implementation; it is a
specification, and it argues each clause:

- **Order of operations is the security property** (lines 14–27). `/tasks/execute`
  verifies the caller's OIDC task identity *before the body is read*. That is why
  the body arrives as a raw `Request` rather than a declared model: FastAPI
  resolves a declared body before the handler runs, so an unauthenticated caller
  sending malformed JSON would be answered `422` — telling them something about
  a service they were never allowed to reach.
- **`200` on a duplicate delivery** (line 33). At-least-once delivery makes a
  duplicate the normal case; answering anything else asks the queue to retry a
  task that is already running.
- **`503` on the pre-dispatch race** (lines 37–42). The delivery arrived before
  the dispatcher recorded the job as dispatched, so the job still reads `queued`
  and the claim cannot match. Retrying genuinely helps — the window is one
  transaction wide. Acknowledging would delete the task and strand the job,
  because nothing else re-delivers it and `queued` has no route to
  `redrive_pending`.
- **`401` / `403` / `501` / `500`** (lines 45–52), with `403` deliberately
  undifferentiated and `501` reserved for "verification is not configured here",
  because an operator seeing `501` should look at the deployment rather than the
  queue.
- **`/operations/dispatch` answers `501` when no task queue is configured**
  (lines 53–62), rather than defaulting to `FixtureTaskQueue` — which would
  answer `200` while every dispatched task went into a dictionary in process
  memory and vanished with the container.

This contract does not stand alone. ADR-0005 establishes that a job and its
dispatch intent share one transaction, which does not make the job and the task
atomic — nothing can — and leaves a crash window. ADR-0007 closes that window by
deriving the task name from the job, so a re-enqueue collides instead of
duplicating. The `200`-on-duplicate rule is the receiving half of ADR-0007's
sending half.

And it is not hypothetical. `smartmatch_worker.local_tasks.LocalPostgresHttpTaskQueue`
already implements the sending side against durable PostgreSQL rows and delivers
over an HTTP loopback to the same `/tasks/execute` endpoint (topology §1). One
non-fixture adapter exists, exercised end to end, today.

The risk is what happens when the second one lands. R-01's impact line: retry
semantics, deduplication, bounce handling and claim mapping all become live at
once. If the contract is only a docstring at that moment, the adapter will be
measured against whatever it happens to do.

## Decision

**The docstring's contract is promoted to an executable acceptance test that any
`TaskQueue` adapter must pass — the loopback and fixture implementations today,
a live Cloud Tasks client whenever one is written. No live adapter is built
here.**

The properties, enumerated so a test can name them one at a time:

1. **At-least-once is tolerated, not avoided.** The adapter may deliver a task
   more than once; the system must be correct when it does. An adapter offering
   exactly-once is not required and its guarantee is not relied on.
2. **A duplicate delivery answers `200` and executes nothing a second time.**
   Both halves. A `200` with a second execution is worse than a `500`.
3. **A delivery that arrives before dispatch is recorded answers `503`**, and the
   task remains for redelivery. Not `200`, which strands the job; not `500`,
   which misreports a race as a database failure.
4. **The task name is derived deterministically from the job** (ADR-0007), so a
   re-enqueue of the same job collides in the queue rather than creating a second
   task. The test asserts the collision, not merely the name's shape.
5. **Identity is verified before the body is read.** Asserted behaviourally: an
   unauthenticated request with a malformed body answers `401`, never `422`.
   `422` on that request is the regression this clause exists to catch, and it is
   the one a framework upgrade can reintroduce silently.
6. **An unconfigured deployment refuses rather than pretends.** No task queue
   configured means `501` from `/operations/dispatch`, never a silent
   `FixtureTaskQueue`.
7. **Nothing about the caller's mistake is disclosed beyond the status.** `403`
   stays undifferentiated; which check failed belongs in the log.

**The suite runs today** against `FixtureTaskQueue` and against
`LocalPostgresHttpTaskQueue`'s loopback, parameterized over the adapter. That is
what makes it a contract rather than a wish: it is green before any live adapter
exists, so a live adapter is measured against a standard that already passes for
two implementations, and **must pass unchanged**. A live adapter that requires
editing this suite has failed it.

**Explicitly out of scope.** No Cloud Tasks client is written. No GCP credential,
queue, or project is introduced. `OPUS_AUDIT_HANDOFF.md` §7 rules out speculative
GCP building, and ADR-0022 records why the appliance is the topology of record.

## Consequences

**Good.** The hardest-to-recover failure mode in the system — a live queue whose
duplicate or race semantics differ from what the dispatcher assumes, discovered
in production — becomes a failing test on the day the adapter is written. The
docstring, currently load-bearing prose in a repository that has already shipped
three false docstrings (D1–D3, R-15), acquires a guard. And the local loopback
adapter stops being "the dev path" and becomes the first passing implementation
of a stated contract, which is a much stronger thing to have.

**Cost.** Parameterizing the existing worker tests over an adapter is real work
against a well-tested area that is not currently broken, and it buys nothing
observable until a second adapter exists. That is the trade R-01 recommends
taking deliberately. There is also a limit worth stating: the suite tests the
*worker's* obligations and the adapter's observable behaviour through the port.
It cannot test Cloud Tasks' own retry scheduling, its backoff, or its dead-letter
policy, because those are the vendor's and are not reachable from a test in this
repository. What it can do is ensure the worker survives any of them.

**Enforcement.** The contract suite in the integration lane, beside
`tests/integration/test_outbox_dispatcher.py`, which `verify.yml`'s deferred list
already records as implemented for the crash-window and duplicate-delivery cases.
This extends that work from one implementation to a contract over all of them.

## Alternatives considered

**Implement the live adapter first, then characterise what it does.** Rejected —
this is the improvisation R-01 names. The adapter would define the contract
rather than satisfy one, and the four semantics that go live simultaneously would
have no prior statement to be checked against.

**Accept queue-specific semantics and branch on the adapter.** Rejected: it makes
the dispatcher's correctness depend on which queue is configured, so every later
reasoning about the command path acquires a case split. The current design's
strength is that ADR-0005's outbox plus ADR-0007's deterministic names make the
worker's obligations independent of the queue; a per-adapter branch spends that.

**Write the contract as prose in `docs/architecture/` and rely on the docstring.**
Rejected: that is the present state. The docstring is excellent and unguarded,
and this repository's own contradiction inventory (D1–D3) is the argument against
trusting a prose invariant nothing asserts.

**Defer until GCP is chosen.** Rejected: the contract is worth having against the
loopback adapter alone, and writing it *before* the topology decision is what
keeps ADR-0022's "any GCP work satisfies this first" clause meaningful.
