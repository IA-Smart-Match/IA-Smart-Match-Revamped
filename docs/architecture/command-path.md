# The durable command path

**As of:** 19 August 2026, Wave B (`2cdc5a8`, `2564d33`, `b0a6a48`).

The repository had no architecture diagrams before this page. Everything below
is transcribed from the code cited beside it, not from the architecture
contract's prose — where the two disagree, the code is what runs.

One thing the diagrams cannot carry, so it is stated once here instead: **the
system's crash-recovery properties come from two specific mechanisms — the
deterministic Cloud Tasks task name (ADR-0007) and the lease/claim pattern on
the outbox and job rows — not from any arrow below.** An arrow says a
transition is *legal*; it says nothing about what happens if the process
executing it dies halfway through. Every section names, separately, what
survives a crash at that point and why.

---

## 1. The durable command path, end to end

A command's life has three phases, each with its own transaction boundary, and
splitting the diagram along those boundaries is not a layout choice — it is
the actual unit of atomicity at each stage.

### 1a. Submission — one transaction, nothing dispatched yet

```mermaid
sequenceDiagram
    participant C as Client
    participant Auth as Auth (bearer token)
    participant R as Route handler
    participant AuthZ as Authz (assert_allowed)
    participant DB as PostgreSQL (one transaction)

    C->>Auth: POST /v1/units/{id}/imports<br/>Authorization: Bearer …
    Auth-->>C: 401 if the token does not verify<br/>or resolves to no local account
    Auth->>R: ResolvedPrincipal (tenant_id, user_id)
    R->>DB: load the org unit (404 if missing)
    R->>AuthZ: assert_allowed(principal, unit, required_roles)
    AuthZ-->>C: 403 on denial (suspended first, then deny,<br/>then role/grant)
    R->>DB: begin transaction
    R->>DB: enforce_rate_limit (429 if exhausted, costs nothing)
    R->>DB: idempotency reserve (409 if key reused with a different body)
    R->>DB: INSERT job (status=queued)
    R->>DB: INSERT outbox_record (status=pending, deterministic task_name)
    R->>DB: COMMIT
    DB-->>C: 202 Accepted {job_id, events_url}
```

Code: `services/api/smartmatch_api/dependencies.py` (auth, rate limit),
`services/api/smartmatch_api/routers/imports.py` (authz),
`services/api/smartmatch_api/commands.py::submit_command` (the transaction).

**What survives, and why.** Rate-limit consumption, the idempotency
reservation, the job row, and the outbox row commit **together, once**. A crash
before that commit means none of it happened — the client got no `job_id` and
has nothing to reconcile. A crash after it means the job and its outbox row
both exist; nothing here can leave one without the other, because there is no
commit boundary between them. This is also why a rejected idempotency conflict
still commits *before* re-raising: the quota it consumed must survive the
rollback that follows, or an attacker gets free retries against the limiter
(security finding S-008).

**What this phase deliberately never does:** call a provider, call Cloud Tasks,
or perform the command's actual work. `submit_command`'s docstring calls this
out explicitly — the request path records intent only.

### 1b. Dispatch — a lease around one network call

```mermaid
sequenceDiagram
    participant D as OutboxDispatcher.run_once
    participant DB as PostgreSQL
    participant CT as Cloud Tasks

    D->>DB: claim_batch (FOR UPDATE SKIP LOCKED,<br/>status -> leased, lease_expires_at set)
    D->>DB: COMMIT (lease now visible to other dispatchers)
    loop each claimed row
        D->>CT: enqueue(task_name, {tenant_id, job_id})
        alt task created
            CT-->>D: created
            D->>DB: job queued -> dispatched<br/>+ outbox row -> dispatched (one transaction)
            D->>DB: COMMIT
        else TaskAlreadyExists
            CT-->>D: already exists (a crashed prior attempt succeeded)
            D->>DB: same transaction as "created" — converge, not retry
        else TaskQueueError / unexpected exception
            CT-->>D: failed
            D->>DB: mark_failed (backoff; job stays queued)
            D->>DB: on the Nth failure (MAX_DISPATCH_ATTEMPTS = 5):<br/>also job queued -> failed_provider, same transaction
        end
    end
```

Code: `services/worker/smartmatch_worker/dispatcher.py`,
`python/smartmatch_persistence/smartmatch_persistence/outbox.py`.

**What survives, and why.** The claim commits *before* the slow call to Cloud
Tasks, or two dispatcher instances could both dispatch the same row. The
enqueue call itself is deliberately outside any transaction — holding a
database transaction open across a network round trip would pin a connection
for its whole duration. If the process dies between the enqueue succeeding and
the "mark dispatched" transaction committing, the lease expires, another
dispatcher retries the row, and **the deterministic task name is what makes
that retry safe**: Cloud Tasks rejects the duplicate name (`TaskAlreadyExists`),
the dispatcher treats that as convergence rather than failure, and the job
advances exactly once. No arrow in this diagram enforces that — it is a
property of how the name is computed (ADR-0007), not of the sequence above.

**What changed in Wave B (`2564d33`):** exhausting `MAX_DISPATCH_ATTEMPTS` used
to leave the outbox row `failed` and the job `queued` — a state nothing would
ever revisit, since no dispatcher looks at a `failed` row again and `queued`
had no route to a terminal state or to `redrive_pending`. The job now moves to
`failed_provider` in the same transaction as the outbox row's final `failed`
write, which is what makes it reachable by the re-drive command (§3).

### 1c. Delivery, claim, and execution

```mermaid
sequenceDiagram
    participant CT as Cloud Tasks
    participant W as Worker: POST /tasks/execute
    participant ID as identity.verify
    participant DB as PostgreSQL
    participant H as Handler

    CT->>W: deliver {tenant_id, job_id}, OIDC bearer token
    W->>ID: verify(Authorization)
    ID-->>W: 401 no credential / 403 rejected / 501 unconfigured
    ID-->>W: TaskIdentity (subject, email, audience)
    W->>DB: read job by (tenant_id, job_id) — 200 "unknown" if none
    W->>DB: claim: dispatched -> running (conditional UPDATE), COMMIT
    alt claim matched (this delivery owns the job)
        W->>DB: emit job.started (own transaction, commits at once)
        W->>H: handler(context)
        H-->>W: HandlerResult(succeeded|partial) or raises HandlerFailure
        W->>DB: terminal transition (running -> …) + terminal event,<br/>ONE transaction, COMMIT
        W-->>CT: 200 {status: executed, state}
    else claim did not match, job still queued
        Note over W,DB: this delivery raced the dispatcher's own<br/>queued -> dispatched commit (§1b) — a one-<br/>transaction-wide window, not a duplicate
        W-->>CT: 503 Retry-After: 1  (status: "early")
    else claim did not match, job already moved on
        Note over W,DB: another delivery already won, or the job<br/>was cancelled — Cloud Tasks delivers at least once
        W-->>CT: 200 {status: duplicate} — executes nothing
    end
```

Code: `services/worker/smartmatch_worker/main.py`,
`services/worker/smartmatch_worker/execution.py`,
`services/worker/smartmatch_worker/identity.py`,
`python/smartmatch_persistence/smartmatch_persistence/jobs.py::JobRepository.claim`.

**What survives, and why.** Cloud Tasks delivers **at least once** — a
duplicate delivery is routine, not exceptional. `JobRepository.claim` is a
conditional `dispatched -> running` UPDATE, committed on its own before any
handler runs, so exactly one delivery can ever match it; every other delivery
of the same task is acknowledged (`200`, `duplicate`) and executes nothing.
Progress events commit as they happen (`emit`), so a client following the SSE
stream sees work in progress rather than only a final summary. The terminal
transition and the event that explains it commit **together** — a job cannot
become terminal with no event saying why, and no event can describe an outcome
the job never reached.

**The `early` outcome, added in `2cdc5a8`.** The dispatcher's `queued ->
dispatched` commit (§1b) happens in a transaction *separate from*, and after,
the Cloud Tasks enqueue call. A delivery can therefore arrive while the job
still reads `queued` — the claim then fails for a reason that has nothing to
do with duplication. Before this change that case was acknowledged like any
other failed claim, which deleted the Cloud Tasks entry with nothing left to
redeliver it and no route from `queued` to `redrive_pending` — the job was
lost silently. It now answers `503` with `Retry-After`, so Cloud Tasks retries
into a window that is at most one transaction wide.

**What does not survive, named rather than hidden.** A worker that dies
*after* `claim` commits and *before* the terminal transition commits leaves the
job `running` with no worker behind it. Nothing in this diagram recovers that
job: the SSE stream shows progress that will never arrive, and there is no
operations view listing it as stuck. Recovering it needs a lease on the job row
(`job.lease_expires_at`) and a sweeper that reclaims an expired one — an
expand-phase migration and a scheduled job, and neither exists yet
(backlog item J9). This is the one gap `execution.py`'s own module docstring
names explicitly rather than leaving implicit.

**Following the result:** `GET /v1/jobs/{id}/events` streams `job_event` rows
in order, resumable via `Last-Event-ID` against `job_event.sequence` — a
database column, not an in-memory position, so any API instance can serve a
reconnect for a stream another instance started (`services/api/smartmatch_api/routers/jobs.py`).

---

## 2. The job state machine

Transcribed directly from `TRANSITIONS` in
`python/smartmatch_domain/smartmatch_domain/jobs.py` — every arrow below is one
entry in that mapping, and nothing here is inferred from the prose elsewhere in
this document.

```mermaid
stateDiagram-v2
    [*] --> queued

    queued --> dispatched
    queued --> cancelled
    queued --> failed_provider

    dispatched --> running
    dispatched --> cancelled

    running --> succeeded
    running --> partial
    running --> failed_provider
    running --> failed_budget
    running --> failed_policy
    running --> cancelled
    running --> timed_out

    failed_provider --> queued
    failed_provider --> redrive_pending

    timed_out --> queued
    timed_out --> redrive_pending

    redrive_pending --> queued
    redrive_pending --> abandoned

    succeeded --> [*]
    partial --> [*]
    cancelled --> [*]
    failed_budget --> [*]
    failed_policy --> [*]
    abandoned --> [*]
```

**Terminal states** (no outgoing transition in `TRANSITIONS`): `succeeded`,
`partial`, `cancelled`, `failed_budget`, `failed_policy`, `abandoned`. Six of
twelve states are terminal, and only two of the six failure-shaped states
(`failed_provider`, `timed_out`) have any way back — that split is the whole
point of the state machine: a handler chooses `PolicyFailure` or
`BudgetFailure` precisely to say "do not re-drive this", and chooses
`ProviderFailure` to say "this might work next time"
(`services/worker/smartmatch_worker/handlers.py`).

**`queued -> failed_provider`, added in `2564d33` (this wave).** Not a job
that ran and failed — a job the dispatcher could never hand over, after
`MAX_DISPATCH_ATTEMPTS` enqueue attempts to Cloud Tasks all failed. Without
this transition a job in that situation stayed `queued` forever: nothing
revisits a `failed` outbox row, and `queued` had no route to any terminal
state or to `redrive_pending`, so the job that most needed re-driving was the
one job the re-drive command could not reach. The state's name is deliberate —
the queue is the provider that failed here, not the handler.

**Two paths worth naming as *not yet exercised* by any code, so this diagram
is not mistaken for a claim that they are:**

* `running -> timed_out` is declared and legal, but nothing in
  `smartmatch_worker.execution` currently raises it — `HandlerResult` accepts
  only `succeeded`/`partial`, and no handler failure maps to `timed_out`. It
  exists in the domain ahead of whatever will produce it.
* `failed_provider -> redrive_pending` and `timed_out -> redrive_pending` are
  driven by exactly one caller today: the re-drive command's own parking step
  (§3), not by any automatic timeout or retry-exhaustion logic watching a
  `running` or `queued` job.

---

## 3. The re-drive cycle

Cloud Tasks has no dead-letter queue. A job that reaches `failed_provider` or
`timed_out` does not requeue itself — a human decides, and the decision is
recorded.

```mermaid
sequenceDiagram
    participant Op as Operator
    participant API as POST /v1/jobs/{id}/redrive or /abandon
    participant DB as PostgreSQL (one transaction)
    participant Out as Outbox

    Note over DB: job is failed_provider or timed_out<br/>(or already redrive_pending from an earlier parking)

    Op->>API: redrive {reason} · Idempotency-Key required
    API->>DB: authorize (suspension, tenant, explicit deny, role — no owning_unit_path exists for this resource)
    API->>DB: begin transaction
    API->>DB: park, if not already: failed_provider/timed_out -> redrive_pending<br/>(open or reuse a redrive_record; attempt history rebuilt from the outbox)
    API->>DB: compare-and-set: redrive_pending -> queued
    alt CAS won
        API->>DB: generation = count of this job's existing outbox rows
        API->>Out: enqueue with redrive_generation=generation<br/>(new, distinct task_name — see ADR-0007 amendment)
        API->>DB: append "redriven" to attempt_history (actor, reason, generation)
        API->>DB: COMMIT
        API-->>Op: 202 {generation, events_url}
        Note over Out: job re-enters §1b dispatch exactly as any<br/>other queued job — same dispatcher, same claim
    else CAS lost (another actor got there first)
        API->>DB: COMMIT anyway (quota already consumed must survive)
        API-->>Op: 409 redrive_conflict
    end
```

```mermaid
sequenceDiagram
    participant Op as Operator
    participant API as POST /v1/jobs/{id}/abandon
    participant DB as PostgreSQL

    Note over DB: job is redrive_pending (or a terminal failure, parked as part of this call)
    Op->>API: abandon {reason} · Idempotency-Key required
    API->>DB: authorize, then compare-and-set: redrive_pending -> abandoned
    API->>DB: append "abandoned" to attempt_history — never written to<br/>redriven_at/redriven_by, so it cannot be mistaken for a re-run
    API->>DB: COMMIT
    API-->>Op: 200 — abandoned is terminal, nothing follows
```

Code: `python/smartmatch_persistence/smartmatch_persistence/redrive.py`,
`services/api/smartmatch_api/routers/redrive.py`.

**Where the cycle re-enters.** A re-driven job does not take a shortcut back
into execution — it becomes an ordinary `queued` row with a fresh outbox
entry, and rejoins §1b exactly where any newly-submitted job would. This is
deliberate: the dispatcher, the claim, and the terminal-transition logic do
not need to know a re-drive happened. The only thing that has to differ is the
task name, because the job's original attempt already used the name a pure
`(job_id, command_type)` hash would derive again — see the ADR-0007 amendment
for why `redrive_generation` fixes that without weakening the guarantee the
dispatcher's own retries depend on.

**Where the cycle ends.** `abandoned` has no outgoing transition in
`TRANSITIONS` — an abandoned job cannot later be re-driven. That is a state
machine fact, not merely a UI convention: the domain layer itself refuses the
transition (`InvalidTransitionError`) if anything tries.

**Three different races, three different guards — worth naming because using
one guard for all three would leave the other two open:**

| Race | Guard |
|---|---|
| The caller's own request retried (network hiccup, client library retry) | `Idempotency-Key` — same key, same body, replays the original response |
| Two operators pressing re-drive on the same job | The job's own state — `redrive_pending -> queued` is a compare-and-set; the loser gets `409` |
| A job that should never be re-driven at all (succeeded, cancelled, still running) | The domain state machine — `assert_transition` rejects any state `TRANSITIONS` does not route through `redrive_pending` |

**What this command does not guard, named rather than papered over.**
Authorization here cannot call `smartmatch_authz.assert_allowed`, because a
`job` row has no owning org unit for the inherited-grant path to match against
— the same gap `docs/security/scaffold-security-review.md` records against
job *reads* (S-006) now also applies to re-driving and abandoning them: a
coordinator in one department can re-run, or permanently close, another
department's failed work. Closing it needs `job.owning_unit_id` (backlog item
A5).
