# Transaction-boundary defects: J11, J12, F11

Covers three backlog items that all turn on the same question — **which writes
commit together, and what happens to the ones that should not have** — and that
were left open when Wave C closed.

| Item | Where | One line |
|---|---|---|
| **J11** | `services/api/smartmatch_api/routers/redrive.py` | A 409 commits the idempotency reservation it just inserted, so the retry is answered with a success for work that never happened. |
| **J12** | `services/worker/smartmatch_worker/dispatcher.py`, `smartmatch_persistence/outbox.py` | The last dispatch attempt has no recovery path. A row that does not finish it is `leased`, unclaimable, uncounted, forever. |
| **F11** | `db/migrations/env.py` | One transaction spans every pending revision, so `0003`'s `ACCESS EXCLUSIVE` lock is held for the whole run rather than for its own migration. |

Nothing here is deployed, nothing here makes anything production-ready, and every
severity below is argued against that fact rather than around it.

**Two of the three descriptions handed to this plan needed correcting**, and both
corrections make the item *worse* rather than milder. They are stated in §2.1 and
§3.1 rather than buried: J11's stated symptom names a state that cannot actually
produce it, and J12 is not a defect in `_record_failure_safely` at all — that
function is one of at least two routes into a hole that is structural. A fix
written from the original J12 description would close the testable route and
leave the untestable one open.

A fourth thing was found on the way and is recorded in §6: the suite is **not**
reliably green. One dispatcher test fails roughly one run in ten.

---

## 1. What the three have in common

Every one of them is a decision about a transaction boundary that was made for a
good reason and that has a consequence nobody costed:

* **J11.** `session.commit()` on the 409 path exists to make the rate-limit
  increment durable — security finding S-008, and the comment arguing for it is
  correct. The cost nobody priced is that the same commit persists an
  idempotency reservation for a command that was refused.
* **J12.** The dispatcher's claim commits before the slow provider call, so the
  lease is visible to other dispatchers — ADR-0005, and that is right. The cost
  nobody priced is that the claim also commits the attempt increment, so the
  *last* attempt is durable before anything can record its outcome.
* **F11.** `env.py` wraps the whole run in one transaction, which buys
  all-or-nothing upgrades. The cost nobody priced until `0003` was written is
  that a lock taken by one revision is held by every revision after it.

The pattern is worth naming because it predicts where the next one will be: a
commit whose *timing* was chosen for one property, carrying a second write whose
lifetime nobody asked about.

They are otherwise unrelated. Different files, different services, different
tests, no shared code. §5 says they can and should land as three commits.

---

## 2. J11 — a 409 poisons its idempotency key

### 2.1 The defect, verified

Verified by execution, against a scratch database created with `createdb` +
`alembic upgrade head` and dropped afterwards, driving the real routes through
`TestClient` with the fixture token verifier. Three probes, verbatim outcomes:

**Probe 1 — re-drive.** A job abandoned, then re-driven under key `poison-1`:

```
FIRST  redrive: 409 {"error":{"code":"invalid_state_transition",
        "message":"cannot move job from 'abandoned' to 'redrive_pending' ..."}}
SECOND redrive, same key: 202 {"job_id":"a3b1…","status":"accepted",
        "generation":0,"events_url":"/v1/jobs/a3b1…/events","replayed":true}
job state now: abandoned
outbox rows: 1
idempotency rows: [('job.abandon','k-ab'), ('job.redrive','poison-1')]
rate_limit rows: [('job.redrive', 3)]
```

**Probe 2 — abandon, already-abandoned job.** First 409, same-key retry
`200 {"status":"abandoned"}`.

**Probe 3 — abandon, `running` job.** First 409, same-key retry
`200 {"status":"abandoned"}`, **job state still `running`, zero
`redrive_record` rows.**

So: confirmed, on both routes, through the public HTTP surface, with no fault
injection and no concurrency. The reservation survives the 409 (`_reserve` at
`redrive.py:257`, the commit at `redrive.py:394` and `:474`), and the replay
branch at `:370` / `:455` then answers a refused command as though it had
succeeded.

**Where the description handed to this plan is wrong.** It says `abandon_job`
"returns `200 {"status": "abandoned"}` while the job is still `failed_provider`."
It cannot. `FAILED_PROVIDER -> REDRIVE_PENDING` is a declared transition
(`smartmatch_domain/jobs.py`), so a `failed_provider` job is abandonable and the
first request succeeds — there is no 409 to poison anything. The states that do
produce the symptom are the ones the domain refuses to route into
`redrive_pending`: `succeeded`, `partial`, `cancelled`, `abandoned`,
`failed_budget`, `failed_policy`, `queued`, `dispatched`, and `running`.

That correction sharpens the item rather than softening it. The sharpest form is
probe 3: **a caller is told a job was closed permanently while the worker is
still executing it.** Naming `failed_provider` understated it.

**Three things the description does not mention, all verified:**

1. **The quota is charged and the increment is real** — `rate_limit_counter`
   read `3` after one abandon and two re-drives. That is the property the fix
   must preserve, and `test_a_rejected_redrive_still_consumes_quota`
   (`tests/integration/test_redrive.py:808`) is its guard.
2. **Both routes share one quota bucket.** `abandon_job` uses
   `REDRIVE_RATE_LIMIT`, whose `operation` is `"job.redrive"`. Not a defect —
   they are the same privileged decision at the same tightness — but a reader
   debugging a 429 on `/abandon` will look for a `job.abandon` counter and not
   find one. Worth one sentence in the docstring, not a change.
3. **The poisoning is permanent for that key.** The reservation is scoped
   `(tenant_id, command_type, idempotency_key)`. Nothing expires it. So it is not
   "one wrong response" — an operator who retries the *same* key after the job
   legitimately becomes re-drivable still gets the fake `202`, and the re-drive
   never happens. The harm outlives the condition that caused it.

Also confirmed by reading: `commands.py` never commits a reservation it created —
its only commit before the work is on the `IdempotencyConflictError` path, where
the reservation is *pre-existing* and there is nothing to leave behind. And
`IdempotencyRepository.reserve`'s docstring states the rule the router breaks:
"Must run in the same transaction as the job and outbox inserts, so a reservation
is never left behind by a rolled-back command."

### 2.2 Severity: High. Argued.

The other two items in this document are latent — J12 needs a failure, F11 needs
a `0004`. This one needs neither. It is reachable today, through a supported
route, by a correctly-behaving client doing the single most ordinary thing a
client does with an idempotency key: retrying with it.

Three reasons it is worse than "a wrong status code":

1. **It is a false statement in the direction that stops people looking.** The
   whole reason re-drive returns `202` rather than `200` is spelled out in its
   own docstring: reporting success for work that has not started is the mistake
   the `partial` state exists to correct (v1.1 §3.6 N2). The replay branch does
   exactly that, and worse — the work has not merely *not started*, it was
   *refused*. An operator who reads `202 accepted, replayed: true` stops
   watching. Nothing else in the system will tell them.
2. **The audit trail records the refusal and not the lie.** `redrive_record` gets
   nothing on a 409 (probe 3: zero rows). So the durable evidence says nothing
   happened, and the only artifact saying otherwise is an HTTP response nobody
   keeps. "Why did nobody re-run this?" — the question `abandon`'s docstring says
   is asked months later — has an answer here that is not in any table.
3. **It defeats the guard it is part of.** The idempotency key exists so a retry
   is safe. Here the retry is the *only* thing that is unsafe: the first request
   told the truth, and every retry lies. That inverts the contract, and it is the
   kind of inversion a client library produces automatically, without a human
   in the loop.

**Who is hurt today.** Nothing is deployed, so: nobody, yet. But note what this
does and does not depend on. J12 and F11 both need something that does not exist
(a database blip at exactly the wrong attempt; a `0004`). J11 needs only a
coordinator, a job, and a retry — every one of which exists the day the API
serves its first request. It is the item on this list with the shortest fuse.

### 2.3 The fix: the options, and why only one of them survives

The constraint is exact: **the quota increment and the reservation are in the
same transaction, and the fix must keep the first and drop the second.** Four
candidates.

**(a) Move the reservation to after the transition succeeds.** Reject. The
reservation is not only a record, it is the *replay detector*, and it has to run
before the work or a genuine retry re-executes it. Deferring it means a retry of
a successful re-drive finds the job `queued`, fails `assert_transition`, and
answers 409 instead of replaying — which breaks
`test_a_duplicate_redrive_does_not_double_run` and the whole point of the header.
Splitting `reserve` into "check" then "insert-after-success" reintroduces exactly
the read-then-insert race the repository's docstring rejects by name. Dead end.

**(b) Delete the reservation row before committing.** Workable. Add a `release`
method to `IdempotencyRepository`, call it in the two `except` blocks, then
commit. Two objections, one small and one real:

  * Small: the repository grows a method whose only caller is an error path, and
    whose existence invites someone to call it somewhere it does not belong.
  * Real: it undoes the reservation and nothing else. There is a reachable case
    (§2.4, case iii) where `_open_parking` has already inserted a
    `redrive_record` before the conflict is raised. A targeted delete commits
    that stray record. So (b) fixes the symptom that was reported and leaves a
    smaller one behind — and the next person to add a write inside the `try` has
    to remember to delete that too.

**(c) Commit the quota in its own transaction or on an autonomous connection.**
This is the conceptually cleanest reading — a rate-limit counter is not part of
the command's atomic unit, and "a rejected request still consumed the capacity
used to reject it" is a statement about *every* rejection, not just these two.
Reject it here anyway, for scope: `enforce_rate_limit` is shared with
`commands.py` and every command route, so this changes the transaction shape of
the entire command path to fix a defect in one router. It also costs a second
connection per request, and it silently changes what happens when a route 500s
after the check (quota would then stick, which is arguably right and is
definitely a different decision). **Recorded as the right long-term shape and
explicitly out of scope**; see §9 question 1.

**(d) A SAVEPOINT around everything the command writes. Recommended.**

```
enforce_rate_limit(...)          # outside — a rejection still costs quota
command = session.begin_nested() # SAVEPOINT
    reserve · redrive/abandon    # everything the command writes
on refusal:  command.rollback()  # ROLLBACK TO SAVEPOINT — reservation gone,
             session.commit()    # any parking gone, quota kept
on success:  command.commit(); session.commit()
```

It is right here for four reasons:

1. **It expresses the actual rule** — "the command did not happen; only the
   quota did" — rather than enumerating the rows that must be removed.
2. **It is exhaustive.** It undoes the reservation, the backfilled
   `redrive_record` from case (iii), and anything a future edit adds inside the
   block. (b) has to be updated for each of those; (d) does not.
3. **It adds no persistence API.** Four lines in one router file. No new
   repository method, no change to `commands.py`, no change to any response
   model — so `contracts/openapi/smartmatch.json` does not move and the
   contract gate stays quiet.
4. **`ROLLBACK TO SAVEPOINT` releases the locks taken after the savepoint**, so
   the job row this request touched is released at the same instant the writes
   are undone. A targeted delete leaves the job's row lock held until the outer
   commit.

**Verified, not assumed.** Probe against a scratch database, mimicking the
router: quota outside the savepoint, reservation inside, `InvalidTransitionError`
raised, savepoint rolled back, session committed —

```
reservations after 409: []
rate-limit counters after 409: [('job.redrive', 1)]
job state: cancelled
second attempt is_replay: False   (the key was released)
rate-limit counters after two 409s: [('job.redrive', 2)]
```

Reservation gone, quota kept, quota charged again on the second rejected attempt,
job untouched, and the key usable again.

**One implementation trap, verified.** `Session.commit()` with an open savepoint
**commits everything, including the savepoint's work** — probed directly:

```
commit() with an open SAVEPOINT: allowed
rows after case 1: ['inner', 'outer']
```

So `_reserve`'s internal `session.commit()` at `redrive.py:290` must be **removed**
and the `IdempotencyConflictError` handled in the router alongside the other two.
Leaving it in place would be harmless today (that path inserts nothing new) and a
live landmine the moment anyone writes before it. Do not leave it.

### 2.4 Concurrency, examined

Four reachable paths to a 409, and what (d) does on each.

**(i) `InvalidTransitionError` from `_open_parking`'s `assert_transition`.** The
job is in a state the domain refuses to park. Raised before `redrive()` writes
anything, so the savepoint holds only the reservation. Rolled back; quota kept.
This is the path every existing 409 test takes, and the path all three probes in
§2.1 took.

**(ii) `RedriveConflictError` — the parking compare-and-set lost.** `_open_parking`
reads the job with a non-locking `SELECT`, sees `failed_provider`, then issues
`UPDATE … WHERE status = 'failed_provider'`. Under READ COMMITTED a concurrent
transaction that already moved the row causes this UPDATE to block on its row
lock and then re-evaluate against the committed row, matching zero rows. Nothing
was written. Same outcome as (i).

**(iii) `RedriveConflictError` — the `redrive_pending -> queued` set lost, having
backfilled a record.** Only reachable when `_open_parking` took its third branch
(the job was already `redrive_pending` with no open record) and inserted one via
`_insert_record`, and another actor then moved the job out of `redrive_pending`.
The savepoint rolls that record back too. **This is the case option (b) gets
wrong**, and the reason (d) is recommended rather than merely preferred.

**(iv) `RedriveConflictError` after a successful park, in the same transaction —
impossible, and worth saying so.** If `_open_parking` parked the job itself, our
transaction holds that row's lock; no other transaction can move it out of
`redrive_pending` until we commit, so the subsequent `REDRIVE_PENDING -> QUEUED`
set reads our own uncommitted row and succeeds. The commit at `:394` therefore
cannot be observed committing a half-performed re-drive. Stated because a reader
scanning the code will suspect it can, and will waste time on it.

**`test_two_coordinators_racing_produce_one_run`
(`tests/integration/test_redrive.py:650`), read as asked.** It is **sequential,
not concurrent** — two `TestClient` posts one after the other. When the second
arrives, the first has already committed `redrive_pending -> queued`, so
`_open_parking` sees `queued`, and `QUEUED -> REDRIVE_PENDING` is *not* in
`TRANSITIONS`. The second coordinator therefore gets **`InvalidTransitionError`**,
not `RedriveConflictError` — path (i), not (ii) or (iii). The test asserts
`status_code == 409` without asserting the code, so it passes either way and its
docstring ("the compare-and-set transition arbitrates") describes a mechanism the
test does not actually reach.

Under the fix its assertions are unchanged and still pass: 409, two outbox rows,
two queue entries. What changes is that coordinator B's key `click-b` is released
instead of poisoned — so if B retries after the job legitimately fails again,
they get a real re-drive rather than a fake `202`. That is the behaviour the test
was written to protect, arrived at properly.

**`RedriveConflictError` is untested.** No test in the suite reaches paths
(ii) or (iii); they need genuine concurrency, which this suite does not have for
this route. That is a gap the fix should not pretend to close — see §2.6's second
test and §9 question 2.

### 2.5 What a same-key retry after a 409 should return

**Re-run the attempt and 409 again.** Not "replay the 409".

The argument is `commands.py`'s own, applied consistently: **a reservation exists
if and only if a command was accepted.** That is what makes `is_replay` mean
"your command was already accepted; here is its result", and it is why
`submit_command` commits a reservation only alongside the job and outbox rows. A
refused command was never accepted, so there is nothing for a replay to return —
and the reservation should not exist to be found.

The practical consequences all point the same way:

* **Re-running is free and safe.** The attempt is a `SELECT`, an
  `assert_transition`, and a compare-and-set that fails again. No side effect
  survives it under (d).
* **The answer stays truthful as the world changes.** A `running` job that later
  fails becomes re-drivable; the same key then produces a real re-drive. Under
  "replay the 409" it would produce a stale refusal forever, which is the mirror
  image of today's defect and no better.
* **"Replay the 409" is not implementable without a schema change anyway.**
  `idempotency_record` carries `request_fingerprint` and `job_id` and nothing
  else — no status, no response body. Storing outcomes is a real feature with a
  migration behind it, and it would buy nothing here.

So the contract, stated for the docstring: *a key names accepted work. A refused
command consumes quota and no key.*

### 2.6 The fix, concretely

**File:** `services/api/smartmatch_api/routers/redrive.py`. Nothing else.

1. **`_reserve` (`:257`)** — remove the `try/except IdempotencyConflictError` and
   its `session.commit()` (`:289-290`). It becomes a thin call to
   `_idempotency.reserve` returning `is_replay`. Rewrite its docstring: the
   paragraph beginning "The transaction is committed before that 409 propagates"
   is describing behaviour that has moved.
2. **`redrive_job` (`:314`)** — keep `enforce_rate_limit` (`:351`) where it is,
   **outside** the savepoint. Open `command = session.begin_nested()` immediately
   after. Put the `_reserve` call, the replay branch, and the `_redrive.redrive`
   call inside. Catch `(IdempotencyConflictError, RedriveConflictError,
   InvalidTransitionError)`; on each: `command.rollback()`, `session.commit()`,
   then re-raise or wrap exactly as today. On success: `command.commit()` then
   `session.commit()`.
   * The replay branch must commit normally — `command.commit()` then
     `session.commit()` — because a replay is a legitimate accepted command and
     its reservation must stay.
3. **`abandon_job` (`:417`)** — identical shape. Do not factor the two into a
   shared helper in this commit; they differ in response type and in the replay
   branch, and a premature helper would obscure a diff that needs to be read
   closely.
4. **Module docstring** — the "What guards what" section says `Idempotency-Key`
   guards a retried request. Add the sentence that is now true: a key is
   consumed only by an accepted command, so a refused one leaves the key free.

**Transaction boundaries, named explicitly:**

| Write | Committed | When |
|---|---|---|
| rate-limit increment | always | outer transaction, on every exit path including 409 |
| idempotency reservation | only on acceptance | inside the savepoint |
| job state transition(s) | only on acceptance | inside the savepoint |
| `redrive_record` insert / append | only on acceptance | inside the savepoint |
| outbox row | only on acceptance | inside the savepoint |

### 2.7 Tests that fail before and pass after

Two new cases in `tests/integration/test_redrive.py`, using the existing
`_post_redrive` / `_post_abandon` / `_a_failed_job` helpers. No new fixtures, no
fault injection.

**`test_a_refused_redrive_does_not_consume_its_idempotency_key`**

1. `job_id = _a_failed_job(...)` — a job in `failed_provider`.
2. `_post_abandon(client, job_id, coordinator, key="close")` → assert 200. The
   job is now `abandoned`, which is terminal.
3. `_post_redrive(client, job_id, coordinator, key="K")` → assert 409 and
   `error.code == "invalid_state_transition"`.
4. `_post_redrive(client, job_id, coordinator, key="K")` — **the assertion that
   fails today**: assert 409 again, same code. Today this returns
   `202 {"replayed": true}`.
5. Assert the job is still `abandoned`, that `_outbox_rows(...)` is unchanged
   (one row), and that `idempotency_record` holds **no** row for
   `command_type='job.redrive'` with that key.
6. Assert quota was charged twice, using the `_consumed()` pattern already in
   `test_a_rejected_redrive_still_consumes_quota` — this is the half of the fix
   that must not regress, and it belongs in the same test as the half that
   changes.

**`test_a_refused_abandon_does_not_report_the_job_abandoned`**

The probe-3 shape, because it is the one that produces the worst sentence:

1. Accept a command, `dispatcher.run_once()`, transition the job to `running`
   (`_fail_terminally` takes a `to_state`, but `running` is reached with the
   existing `jobs.transition` calls the helper already makes — a three-line local
   setup, or extend `_fail_terminally`'s docstring rather than its signature).
2. `_post_abandon(..., key="K2")` → 409.
3. `_post_abandon(..., key="K2")` → **assert 409**. Today: `200 {"status":
   "abandoned"}`.
4. Assert the job is still `running` and `redrive_record` is empty for it.

Step 3's failure message should say what the response claimed, not just that the
status differed — `assert response.status_code == 409, response.text` is the
house pattern and reads correctly here.

**What is deliberately not tested:** paths (ii) and (iii). Reaching them needs
two concurrent transactions interleaved at a named point, which this suite has no
harness for, and a test that monkeypatched `JobRepository.transition` to return
`False` would assert that the `except` block runs — not that the race produces
it. Recorded in §9 rather than faked.

### 2.8 What could go wrong

* **A savepoint left open on an unexpected exception.** If something inside the
  block raises anything not in the three-exception tuple, the savepoint is still
  open when `get_session`'s `finally` calls `session.rollback()`. That rolls back
  the outer transaction — quota and all — which is today's behaviour for a 500
  and is correct. Verify by reading, not by hoping: `get_session`
  (`dependencies.py:39`) rolls back unconditionally.
* **The existing quota test.** `test_a_rejected_redrive_still_consumes_quota`
  passes a `queued` job, taking path (i). It must still pass. If it does not, the
  savepoint has been opened before `enforce_rate_limit` — that is the single most
  likely implementation error and the test catches it directly.
* **`test_a_duplicate_redrive_does_not_double_run` and
  `test_a_replayed_redrive_reports_the_generation_it_replays`** cover the replay
  branch, which must keep committing. If the implementer routes the replay
  through the rollback path, both fail immediately. Good coverage already exists;
  nothing new is needed for it.
* **What no test would catch:** whether `_reserve`'s docstring still describes
  what it does. That is a documentation defect of exactly the class
  `defect-remediation.md` §1 argues about, and it is on the reviewer, not on CI.
* **The schema drift test is irrelevant here.** No schema changes, no
  `schema.py` edit, no migration. So is the OpenAPI contract check — no response
  model moves.

---

## 3. J12 — the last dispatch attempt has no recovery path

### 3.1 The defect, verified — and it is wider than described

Verified by execution against a scratch database. First, exactly as described:
five dispatch attempts against a queue that always fails, with `_record_failure`
made to raise on the fifth:

```
attempt 1: failed=1  state=('leased', 1, queued, lag.pending=0)
attempt 2: failed=1  state=('leased', 2, queued, …)
attempt 3: failed=1  state=('leased', 3, queued, …)
attempt 4: failed=1  state=('leased', 4, queued, …)
attempt 5: failed=1  state=('leased', 5, queued, …)   ← failure-write raised

--- after exhaustion ---
outbox status=leased  attempts=5  job=queued  lag.pending=0  lag.oldest_age=None
subsequent pass 0: DispatchOutcome(claimed=0, dispatched=0, already_existed=0, failed=0)
subsequent pass 1: DispatchOutcome(claimed=0, …)
subsequent pass 2: DispatchOutcome(claimed=0, …)
final: ('leased', 5, queued, 0, None)
```

The boundary is confirmed the way the description asked. `MAX_DISPATCH_ATTEMPTS`
is 5 (`outbox.py:57`); `claim_batch` (`:237`) increments and returns the
**post**-increment value, so the fifth claim yields `dispatch_attempts = 5`;
`_claimable_predicate` (`:89`) requires `dispatch_attempts < MAX_DISPATCH_ATTEMPTS`
(`:108`), which `5 < 5` fails. `_record_failure` computes `exhausted = attempts >=
MAX_DISPATCH_ATTEMPTS`, so the write that would have parked it is the one that
did not happen. No off-by-one: the row is claimed exactly five times and stranded
on the fifth.

**Now the correction, and it changes the fix.** The description — and the backlog
entry, and the item's own title — attribute this to `_record_failure_safely`
(`dispatcher.py:291`) swallowing an exception. **That is one route in, not the
defect.** Second probe: no exception anywhere, no fault injection at all. Claim
the row five times and simply abandon it each time — precisely what a killed
dispatcher leaves behind, and exactly the technique
`test_crash_between_commit_and_task_creation_loses_nothing` already uses to
simulate a crash:

```
claim 1: claimed=1 attempts=1
claim 2: claimed=1 attempts=2
claim 3: claimed=1 attempts=3
claim 4: claimed=1 attempts=4
claim 5: claimed=1 attempts=5
after exhaustion: status=leased attempts=5 reclaimable=0 pending_count=0
job state: queued
```

Identical stranding. A pod evicted, a SIGKILL, an OOM, a node drained — anything
that ends the process between the claim's commit and the outcome write — reaches
the same state on the fifth attempt, and **no change to `_record_failure_safely`
closes it**, because `_record_failure_safely` never runs.

So the item is: **`leased` with attempts exhausted is a terminal, invisible
state, and the dispatcher has no way out of it.** The swallowed exception is the
route that is easy to test. Process death is the route that is likely.

**Why this framing matters practically.** A fix written from the original
description — make `_record_failure_safely` re-raise, or retry the write — would
pass a test built from the same description, close the tested route, leave the
untested one open, and produce a commit whose message claims more than it did.
That is the specific failure `defect-remediation.md` §5 is about.

**ADR-0005 already names the shape and misses this instance.** Its "The
invariant" section says: *"A `leased` row must never carry a NULL lease … such a
row is permanently unclaimable — invisible work, silently stuck, with no symptom
except a job that never finishes."* Correct, and incomplete. There is a second
way to be permanently unclaimable while `leased`, and it is the one nothing
guards. The honest statement of the invariant is:

> A `leased` row must always be claimable in the future: it must carry a
> non-NULL lease **and** have attempts remaining. Whichever half fails, the row
> is invisible work.

`mark_failed` upholds both halves for every row it touches. Nothing upholds them
for a row it never reaches.

**Both documents that describe this path are wrong about it and must be corrected
with the fix.** `docs/architecture/command-path.md:100-108` says "the lease
expires, another dispatcher retries the row" without qualification;
`_record_failure_safely`'s own docstring says "Nothing is lost by giving up
here". Neither is true on the last attempt, and both are load-bearing for a
reader deciding whether this path needs attention.

### 3.2 Severity: Medium, and it is the one that gets *worse* with deployment

Lower than J11 for one reason and one only: it requires a failure to reach. J11
requires a retry.

Everything else about it is worse:

* **The failure it needs is the ordinary one.** Not a database blip at an exotic
  moment — a dispatcher process ending. Every deployment restarts it. Every
  autoscale event ends one. The window is one attempt out of five, but it is the
  attempt that arrives precisely when the queue has been broken for a while,
  which is when a dispatcher is most likely to be restarted by an operator
  reacting to the outage. The conditions correlate.
* **It defeats three mechanisms at once.** The row is never reclaimed (claim
  predicate), never counted (`pending_count` and `oldest_pending_age` share the
  predicate, deliberately, so the metric and the behaviour cannot drift — here
  they agree, and both are wrong), and never visible as `failed`. The job stays
  `queued`, which `TRANSITIONS` routes only to `dispatched` and `cancelled` — so
  re-drive answers 409 forever. **This is precisely the state commit `2564d33`
  added the `queued -> failed_provider` parking to eliminate**, reached by a
  route that parking cannot see. The system's own recovery command cannot touch
  it.
* **There is no symptom.** The lag metric — the thing v1.1 §1.6 requires an alert
  on — reads zero. Probed: `lag.pending=0`, `lag.oldest_age=None`, with work
  stuck. An operations view built on `status = 'failed'` shows nothing. The only
  evidence is a job that never finishes, which is an absence.

**Who is hurt today.** Nobody: nothing schedules the dispatcher (backlog J8), so
`run_once` executes only when a test or a person calls it, and no work is waiting
on it. The argument for fixing it now is not urgency, it is that **the fix costs
nothing today and is a data-recovery exercise later.** A stranded row is
unreachable by the API, by the dispatcher, and by re-drive; recovering one after
the fact means hand-written UPDATEs against production, which is the category of
work this system's whole design is arranged to avoid.

### 3.3 J9 — checked, and they should be separate

They are not the same defect and one mechanism does not close both.

| | **J12** | **J9** |
|---|---|---|
| Table | `outbox_record` | `job` |
| Stuck state | `leased`, lease expired, attempts exhausted | `running`, worker gone |
| Detector exists? | **Yes** — `lease_expires_at` and `dispatch_attempts` are already there | **No** — needs `job.lease_expires_at`, an expand-phase migration |
| Recovery write | row → `failed`; job `queued -> failed_provider` | job `running -> failed_provider` (or `timed_out`) |
| Needs a migration | no | **yes** |
| Needs a scheduler | **no** — it can ride `run_once` | yes, or the same host |
| Blocked by | nothing | J7 (done) + a `0004` |

**Do them separately.** The decisive asymmetry is the migration: J12 needs none
and can land this week; J9 needs `0004`, which — see §4 — should not be written
until F11 is settled. Coupling them would make the cheap, complete fix wait on
the expensive, undecided one.

**What they genuinely share is a place, not a mechanism.** Both are "something
that should have finished did not, and an expired lease is how you find out", and
both want to run on a schedule that does not exist (J8). So:

* Land J12's reclaim **inside `OutboxDispatcher.run_once`**, before the claim.
  It then needs no new entrypoint, no new schedule, and no J8 — and a separate
  scheduled sweeper written now would be dead code, since nothing calls anything
  on a timer.
* When J9 lands, put its sweep in the **same scheduled pass**, as a sibling
  method, so an operator has one place to look and one metric surface for "work
  that had to be rescued". Say so in J9's backlog note now, so it is a
  requirement rather than a preference someone rediscovers.

**Do not generalise them into one "expired lease reaper".** The predicates differ,
the recovery writes differ, and the tables have no relationship the code would
share. A generic reaper would be a parameterised abstraction over two callers,
which is the shape that ends up wrong for both.

### 3.4 The fix, concretely

**Files:** `python/smartmatch_persistence/smartmatch_persistence/outbox.py`,
`services/worker/smartmatch_worker/dispatcher.py`. No migration.

**1. `outbox.py` — a predicate and a query for the stranded state.**

Add, next to `_claimable_predicate` so the two are read together:

```
def _stranded_predicate(now) -> ColumnElement[bool]:
    status == LEASED
    AND lease_expires_at < now        # NULL never satisfies this — deliberate,
                                      # and the same reason mark_failed's
                                      # invariant paragraph gives
    AND dispatch_attempts >= MAX_DISPATCH_ATTEMPTS
```

and `OutboxRepository.reclaim_stranded(session, *, now=None, limit=…) ->
list[ClaimedOutboxRecord]`: `UPDATE … WHERE _stranded_predicate` setting
`status='failed'`, `lease_expires_at=NULL`, and a `last_error` that says what
happened, `RETURNING` the rows. Use the same CTE + `FOR UPDATE SKIP LOCKED`
shape as `claim_batch` — ADR-0005 gives the reason and it applies identically.

The `last_error` text matters and should not be an afterthought: the row still
carries the *previous* attempt's error, and an operator reading it would conclude
the queue rejected it when in fact nothing recorded the last attempt at all. Write
something that says so — e.g. *"dispatch attempts exhausted; the final attempt
recorded no outcome and the row was reclaimed"* — truncated to the same 2000
characters `mark_failed` uses.

**2. `dispatcher.py` — call it, and account for it.**

* `OutboxDispatcher.reclaim_stranded()`: in **one transaction**, call the
  repository method and, for each returned row, `transition(job, FAILED_PROVIDER,
  expected_from=QUEUED)`. These are the same two writes `_record_failure`
  performs at exhaustion (`dispatcher.py:331`), and they share a transaction for
  the same reason its docstring gives: *"A parked row beside a `queued` job, or a
  failed job beside a live row, are each a state nothing would reconcile."*
* Call it at the top of `run_once`, before `claim_batch`, in its own transaction.
  Before rather than after, so a pass that reclaims a row also reports it in the
  same `DispatchOutcome` the operator is reading.
* Add `reclaimed: int = 0` to `DispatchOutcome`. **It is outside the
  `claimed == dispatched + already_existed + failed` identity** — a reclaimed row
  was not claimed this pass — and that must be said in the docstring, which
  currently asserts the four fields are exhaustive. A non-zero `reclaimed` is a
  real signal: it means a dispatcher died, or the database refused a write, at
  the worst possible moment. It deserves to be countable.

**3. Leave `_record_failure_safely` swallowing, and correct its docstring.**

Two sub-options were considered and rejected:

* *Re-raise on the final attempt.* Breaks the module's stated rule that one row's
  failure is never the batch's failure — and the rows after it in the batch would
  lose their attempt to a problem that is now recoverable anyway.
* *Retry the failure-write.* Adds a retry policy to a path that already has one,
  and closes nothing: the process-death route has no code running to retry.

The reclaim makes swallowing correct again, which is the point. But the
docstring's claim — *"Nothing is lost by giving up here: an unrecorded failure
leaves the row exactly as the claim left it, so the lease expires and it is
retried"* — is false as written and stays false after the fix (the row is
reclaimed, not retried). Rewrite it to say what is now true: giving up is safe
**because** the reclaim pass finds the row, and on the final attempt that is the
only thing that will.

**4. Correct the two documents that describe the old behaviour.**

* `docs/architecture/command-path.md` §1b — qualify "the lease expires, another
  dispatcher retries the row", and add the reclaim to the description of what
  happens at exhaustion.
* **`ADR-0005` needs an amendment**, exactly as ADR-0004 got one when F7 landed.
  Its "The invariant" section states one invariant where there are two, and its
  Consequences claim *"A command that commits is a command that will eventually
  be attempted"* — which was untrue at the last attempt. Amend both. This is part
  of J12, not a follow-up: an ADR describing a guarantee the code did not provide
  is the same class of defect as everything in `defect-remediation.md` §3.

**Transaction boundaries, named explicitly:**

| Transaction | Contents |
|---|---|
| reclaim | `outbox_record -> failed` **+** `job queued -> failed_provider`, for every stranded row in the pass |
| claim | lease + attempt increment (unchanged) |
| record outcome | `mark_dispatched` + `job queued -> dispatched`, or `mark_failed` + park at exhaustion (unchanged) |

### 3.5 The tests, and the seam question

**No new fault-injection seam is needed, and the primary test needs no injection
at all.**

**`test_a_row_stranded_on_its_last_attempt_is_reclaimed`** — the seam-free one,
and the one that pins the structural property:

1. `_accept_command(...)`.
2. Loop `MAX_DISPATCH_ATTEMPTS` times: `outbox.claim_batch(session, …)`, commit,
   and **do nothing else** — the exact technique
   `test_crash_between_commit_and_task_creation_loses_nothing` already uses for
   "the process died", repeated to exhaustion. Call the existing
   `_expire_all_leases(session_factory, tenant_id)` helper between iterations.
3. Assert the stranded state: row `leased`, `dispatch_attempts == 5`,
   `outbox.pending_count(session) == 0`, job `queued`, and
   `outbox.claim_batch(...) == []`. **These assertions all pass today** — they
   document the hole.
4. `_expire_all_leases(...)`, then `dispatcher.run_once()`.
5. **The assertions that fail today:** the row is `OutboxStatus.FAILED` with
   `lease_expires_at IS NULL`, the job is `JobState.FAILED_PROVIDER`, and
   `can_transition(FAILED_PROVIDER, REDRIVE_PENDING)` — the last one asserted the
   same way `test_a_job_whose_dispatch_is_exhausted_becomes_redrivable` asserts
   it, because "reclaimed" is worth nothing if the operator still cannot act.
   Also assert `outcome.reclaimed == 1`.

Note step 2 exercises the route the original description does not cover, which is
the point of leading with it.

**`test_a_row_whose_failure_is_never_recorded_ends_up_visible`** — the swallowed
route, and the exact sibling of the existing
`test_a_row_whose_dispatch_is_never_recorded_ends_up_visible`
(`test_outbox_dispatcher.py:706`), whose docstring already describes this defect
in full while testing the *other* half of it. Same shape: `queue.fail_next_with =
TaskQueueError(...)` on each pass, `monkeypatch.setattr(dispatcher,
"_record_failure", always_fails)`, loop to exhaustion, expire leases, one more
pass, assert reclaimed.

**On the seam.** The injection point is `dispatcher._record_failure` — a private
method, monkeypatched on the instance, in a test. It is **already** the seam two
existing tests use (`test_a_failure_while_recording_a_failure_does_not_abort_the_batch`
at `:639`, and the `_record_dispatched` equivalent at `:604`). Nothing is added to
production code: no injectable hook, no `if testing:`, no protocol parameter.
That is the whole argument that it is not a testability wart — **the seam is the
method decomposition the module already chose for its own reasons**, and the test
reaches through it rather than the module reaching out. A production-visible seam
would be a wart; monkeypatching a private method is a test taking a liberty it
owns, and the suite has already decided that liberty is acceptable here twice.

**What the tests cannot cover:** a real process death (the second probe simulates
it faithfully but in-process), and concurrent reclaim by two dispatchers — the
`SKIP LOCKED` shape makes that safe by construction and by the same argument
ADR-0005 makes for `claim_batch`, which is an argument, not a test.

### 3.6 What could go wrong

* **The reclaim steals a row a live dispatcher is working on.** It cannot: the
  predicate requires `lease_expires_at < now`, the same guard the existing
  recovery path relies on. But it is the failure that would be worst, so the
  predicate deserves its own assertion —
  `test_a_live_lease_blocks_a_second_claim` (`:199`) has the right shape to copy
  for the reclaim.
* **A `leased` row with a NULL lease.** ADR-0005's stated invariant says this
  cannot happen; the reclaim predicate uses `<`, which NULL never satisfies, so
  such a row would be stranded from the reclaim too. That is the correct
  conservative behaviour (do not touch a row whose state is not understood) but
  it should be *said*, not left as an emergent property of SQL's NULL semantics.
* **The `DispatchOutcome` identity.** Adding `reclaimed` outside
  `claimed == dispatched + already_existed + failed` will look like a bug to the
  next reader unless the docstring says otherwise.
  `test_dispatch_outcome_totals_always_add_up` (`:662`) must keep passing
  unchanged — if it does not, `reclaimed` has been wired into the identity.
* **The schema drift test catches nothing here** — no schema change, no
  `schema.py` edit. Neither does the OpenAPI contract check.
* **What neither would catch:** that `last_error` says something truthful, and
  that ADR-0005's invariant paragraph was amended. Both are on the reviewer.

---

## 4. F11 — one transaction spans every pending migration

### 4.1 Verified

`db/migrations/env.py` calls `context.configure(connection=connection,
target_metadata=target_metadata)` and wraps `context.run_migrations()` in a
single `context.begin_transaction()`. `transaction_per_migration` is not set on
either the online or the offline path.

Confirmed by generating the offline script, which shows the boundaries directly:

```
line   4:  BEGIN;
line  12:  -- Running upgrade  -> 0001_foundation
line 194:  -- Running upgrade 0001_foundation -> 0002_rate_limit
line 212:  -- Running upgrade 0002_rate_limit -> 0003_global_subject
line 214:  LOCK TABLE user_account IN ACCESS EXCLUSIVE MODE;
line 226:  COMMIT;
```

One `BEGIN`, one `COMMIT`, three revisions, and the `LOCK` inside. `0003`'s
docstring is exactly right about all of it, including that it is harmless while
`0003` is head, and it says so at length under *"How long the lock is actually
held — read this before writing `0004`."*

**One thing the backlog entry does not mention: the offline path has it too.**
`0003`'s docstring discusses `env.py` and the runtime lock. But `alembic upgrade
--sql` produces the script above, and a DBA applying a reviewed script by hand
reproduces the same single transaction. Whatever is decided must be applied to
**both** `context.configure` calls, or the reviewed-SQL route keeps the defect
after the live route loses it — and that is the route with a human watching, who
would reasonably assume the script matches what the tool does.

Nothing else in the description is inaccurate.

### 4.2 The trade, argued

`transaction_per_migration=True` buys: each revision commits on its own, so a
lock taken by one revision is released when that revision ends, and a long
upgrade run does not accumulate locks.

It costs: a failed multi-step upgrade leaves earlier revisions committed rather
than rolling the run back as a unit.

**The cost is smaller than it sounds, and it is worth being precise about why.**
The failure state under per-migration transactions is not *inconsistent* — the
`alembic_version` row commits with its own revision, so after a failure at
`0004`, the database is at `0003` and says it is at `0003`. It is a valid,
resumable state: fix the problem, run `alembic upgrade head` again. The
all-or-nothing arrangement gives a different valid state (nothing applied), not a
safer one.

The real question is therefore not "is the failure state consistent?" but **"is
an intermediate revision a state this system can be in?"** And this repository
has already answered that, twice, in writing:

* v1.1 §4.2's expand / migrate / contract discipline, which `0003`'s docstring
  and ADR-0004 both cite, requires every revision to be independently safe under
  a rolling deploy — because during a rollout the old and new releases both run
  against whatever schema is currently applied.
* `0003` itself is written to that rule: it keeps `uq_user_account_tenant_subject`
  specifically so a release rolled back after it ran "must still find the schema
  it was built against" (and F12 exists to drop it later).

**A repository whose migration discipline already requires each revision to be a
valid resting state is a repository whose migrations are already
per-migration-transactional in intent.** The single-transaction run is buying an
atomicity guarantee over a set of changes that are, by construction, individually
atomic and individually deployable. It is paying a lock-duration cost for a
property the discipline says it does not need.

Verified that the change is behaviour-preserving here: a scratch database
migrated to head with `transaction_per_migration=True` passes
`tests/integration/test_schema_matches_migration.py` and
`tests/integration/test_job_states_match_domain.py` — 128 cases, all green — and
the offline script becomes one `BEGIN`/`COMMIT` per revision with the `LOCK`
inside `0003`'s own.

### 4.3 Recommendation, and what would have to be true for the other choice

**Recommend `transaction_per_migration=True`, on both `context.configure` calls,
now, before a `0004` exists.**

The timing argument is the strongest one and it is not urgency. Today there are
three revisions, no deployment, and no production data — so changing the rollback
semantics of "every migration in the repository" means changing it for three
migrations that nobody has ever rolled back and that CI recreates from empty on
every run. The blast radius is developer machines and CI, and it is worth stating
that plainly rather than letting the phrase "changes rollback semantics for every
migration" carry more weight than it does at three revisions. That sentence gets
heavier with every revision added and much heavier the day something is deployed.
The cost of this decision only rises.

**What would have to be true for the other choice to win:**

1. **A change that genuinely cannot be split across revisions is written as two
   revisions.** For example a DDL step plus a data backfill that must be atomic
   with it. Then all-or-nothing saves an operator from a half-applied logical
   change. The answer is that such a change belongs in **one** revision, where it
   is atomic under either setting — so this argues for a review rule, not for the
   global default.
2. **An operator who cannot be trusted to re-run `alembic upgrade head` after a
   failure.** Per-migration transactions make partial progress durable, which is
   only an improvement if someone finishes the job. In a fully automated deploy
   pipeline this is fine; in a hand-run process with no runbook it is a way to
   leave a database at `0003` indefinitely. There is no deploy pipeline yet, so
   this is a real question for whoever builds one — and the answer is a runbook,
   not a transaction setting.
3. **A future revision that must run outside a transaction anyway.** The
   `CREATE INDEX CONCURRENTLY` form `0003`'s docstring recommends for a large
   `user_account` cannot run inside a transaction at all. Note carefully: **`transaction_per_migration=True` does not enable it.** That needs
   `with op.get_context().autocommit_block():` inside the revision. If someone
   assumes otherwise, they will write a `CONCURRENTLY` migration that fails at
   run time. The plan should say this out loud precisely because the two ideas
   sit next to each other in `0003`'s docstring and are easy to conflate.

If (1) or (2) turns out to be decisive, the fallback is the operational one the
backlog already names — run the locking revision on its own — which is weaker
because it depends on an operator remembering, and which does not survive being
forgotten once.

### 4.4 What to check first

1. **Each existing revision is independently valid.** Verified by reading:
   `0001` creates, `0002` creates, `0003` constrains a table nothing writes.
   None depends on a sibling being in the same transaction.
2. **`0003`'s duplicate-refusal test is unaffected.**
   `test_the_migration_refuses_to_run_against_duplicate_subjects`
   (`tests/integration/test_principal_identity.py:253`) upgrades a scratch
   database to `0002_rate_limit`, inserts duplicates, then upgrades to `head` —
   **one pending revision**, so the run has identical boundaries either way. Its
   assertion that `alembic_version` did not move still holds. Confirmed by
   reading `_run_the_refusal`; no change needed.
3. **CI's "Migrations apply from an empty database" step and `make migrate-check`
   are unaffected.** Both recreate from empty; verified green against a scratch
   database with the flag set.
4. **Both `configure` calls, not one.** §4.1.
5. **`0003`'s docstring becomes false and must change in the same commit.** The
   paragraph "How long the lock is actually held — read this before writing
   `0004`" describes the old behaviour and instructs a future author to inherit
   it. Leaving it would leave the repository asserting something untrue about
   itself, which is the class of defect `defect-remediation.md` exists to
   prosecute. Rewrite it to record what was decided and why, and keep the
   `CREATE INDEX CONCURRENTLY` discussion, which stays true.
6. **Write ADR-0009.** ADR-0004 covers the schema and its hand-written mirror,
   not migration mechanics, and this is a decision with a permanent consequence
   for every revision anyone writes. It should be discoverable from the ADR
   directory rather than from a paragraph inside `0003`. (F8's ADR index gets one
   more row; that is not a reason to delay either.)

### 4.5 A test that fails before and passes after

**`tests/unit/test_migration_transactions.py::test_each_revision_is_its_own_transaction`.**

Run `alembic upgrade base:head --sql` from `db/` as a subprocess — the same
`sys.executable -m alembic` pattern `test_principal_identity.py::_alembic` uses —
and assert the emitted script contains one `BEGIN;` and one `COMMIT;` **per
revision**, with `LOCK TABLE user_account` between a `BEGIN` and the next
`COMMIT` rather than spanning them.

Two properties make this the right test:

* **It needs no database.** Verified: offline mode never connects — run against
  `postgresql+psycopg://nobody:nobody@127.0.0.1:1/nope` it emits the script
  normally. So it belongs in the **unit lane**, which means it protects the
  decision even on a machine with no PostgreSQL, unlike everything else in this
  document.
* **It fails before and passes after.** Today: exactly one `BEGIN;`/`COMMIT;`
  pair. After: one per revision, currently three.

Assert on *counts and containment*, not on exact line numbers — the numbers in
§4.1 will move the moment anyone edits a migration.

**Be honest about what it does not cover.** It exercises
`run_migrations_offline`. The online path is the same `configure()` decision but
a different call site, and **with `0003` as head there is no online-observable
difference at all** — the lock is taken in the last revision, so it is released
at the end of the run either way. That is exactly what "harmless while `0003` is
head" means, and it means no online test can fail-before/pass-after today. Do not
invent one: a test that starts an upgrade in a subprocess and races another
connection to observe an intermediate `alembic_version` would be timing-dependent
against migrations that complete in milliseconds, and a flaky test asserting a
transaction boundary is worse than no test. Cover the online call site by review,
and by the fact that both `configure` calls are three lines apart in one small
file.

---

## 5. Ordering and independence

**Three commits. They must not be combined**, and not for ceremony: they touch
disjoint files, they carry different risk, and the project's rule is one coherent
stage per commit with a `code-review` audit at `high` before each. A combined
diff would put a router change, a worker change, and a migration-system decision
in front of one review, and the migration decision is the one that most needs to
be read on its own.

| Order | Item | Files | Depends on | Why here |
|---|---|---|---|---|
| 1 | **J11** | `routers/redrive.py`, `tests/integration/test_redrive.py` | — | Shortest fuse (§2.2): reachable today, no failure required, and it lies to an operator. |
| 2 | **J12** | `dispatcher.py`, `outbox.py`, `test_outbox_dispatcher.py`, ADR-0005 amendment, `command-path.md` | — | Needs no migration and rides the existing `run_once`, so it does not wait on J8 or on F11. |
| 3 | **F11** | `db/migrations/env.py`, `0003`'s docstring, ADR-0009, `tests/unit/test_migration_transactions.py` | — | Independent of both, and **must land before anyone writes `0004`** — which J9 and A5 both need. |

No item blocks another. F11 can be done first, or by someone else, or in
parallel — it shares no file with the other two. The only real sequencing
constraint in the whole document points outward: **F11 before `0004`**, and
therefore F11 before J9 and before A5's expand-phase migration.

If only one is done, do J11.

---

## 6. Found on the way: the suite is not reliably green

This document was handed a repository described as green at 488 passed / 1
skipped. It is, most of the time. Over twenty-plus full and module-scoped runs:

```
488 passed, 1 skipped        (most runs)
1 failed, 487 passed, 1 skipped
FAILED tests/integration/test_outbox_dispatcher.py::
       test_a_failure_while_recording_a_dispatch_does_not_abort_the_batch
```

Roughly one run in eight to fifteen, reproducible with the module alone, never
reproducible with the single test alone (0 failures in 15 isolated runs).

**What fails.** The test breaks the *first* `_record_dispatched` call and then
asserts `second_job` is `DISPATCHED`. On a failing run `second_job` is `LEASED`
and the captured log names the first-enqueued task as the one that failed — i.e.
the dispatcher processed the two claimed rows in the opposite order from the
order they were created.

**Why that is possible.** `claim_batch` selects rows `ORDER BY created_at` inside
a CTE, but returns them from `UPDATE … RETURNING`, and **SQL does not define the
output order of `RETURNING`**. The `ORDER BY` constrains *which* rows are
selected under `LIMIT`, not the order they come back. Nothing in the dispatcher
depends on the order; only this test does.

**What was ruled out.** `created_at` ties: 0 in 200 pairs. Claim order reversal
in isolated probes: 0 in 30, 0 in 60 against a populated table, 0 in 120 against
a delete-churned table. So the trigger is plan- or page-layout-dependent and only
appears with the whole module's churn ahead of it — consistent with an unordered
`RETURNING`, and inconsistent with any timestamp tie.

**What to do.** Two candidate fixes, and they are not equivalent:

* *Make the test not depend on order* — inject the failure by task name or record
  id rather than by call ordinal. Smallest change, and honest: the test is
  asserting something it never meant to.
* *Make `claim_batch` deliver the FIFO order it documents* — sort the returned
  list by `created_at` in Python before returning. One line, and it closes a
  smaller latent gap: with a backlog larger than `batch_size`, the dispatcher
  currently processes an arbitrary permutation of the oldest 20, while ADR-0005
  and the lag metric both talk about the oldest row. No correctness property
  depends on it today.

**Recommend both**, in the J12 commit, since it touches both files and an
implementer will be running this module repeatedly. But do not let it grow: this
is a flaky test and a documentation-versus-behaviour mismatch, not a defect in
dispatch.

This is worth a backlog row of its own — call it **J13** — so it is not carried
only inside this plan.

---

## 7. What is deliberately not fixed, and why

**`enforce_rate_limit` is not moved to its own transaction.** §2.3(c) argues it
is the right long-term shape: a rate-limit counter is not part of a command's
atomic unit, and *every* rejection should cost the capacity used to reject it —
not just the two the savepoint happens to cover. It is out of scope because it
changes the transaction shape of every command route to fix a defect in one, and
because it silently decides a question nobody has asked (does a 500 after the
check cost quota?). Recorded as §9 question 1 rather than done quietly.

**`commands.py` is not changed.** It has the mirror of this problem in a milder
form: if `_jobs.create` or `_outbox.enqueue` raises after the reservation, the
request-scoped session rolls back and the caller pays no quota. That is the
S-008 hole again. It is not fixed here because there is no client-driven route to
it — everything after `reserve` is an unconditional write, so reaching it means a
500, and a caller cannot hammer a 500 for free in any way a limiter would care
about. Fixing it is subsumed by the §2.3(c) change if that is ever made.

**`AbandonedResponse` does not gain a `replayed` field.** `RedriveAcceptedResponse`
has one and this does not, which is an asymmetry a reader will notice. It is not
a defect: once J11 is fixed, a replayed abandon is a *true* statement — the job
is abandoned — so the flag would be informational only. Adding it changes the
OpenAPI contract, which means regenerating `contracts/openapi/smartmatch.json`
and eventually the TypeScript client, for a field with no consumer. Not worth it
now; worth revisiting when W2 generates a client that might want it.

**No test is written for `RedriveConflictError`.** Paths (ii) and (iii) in §2.4
need two transactions interleaved at a named point, and this suite has no harness
for that. A monkeypatched `JobRepository.transition` returning `False` would
assert that the `except` block runs, which is a test of the code's shape rather
than of the race. §9 question 2 names it instead of faking it.

**J12's reclaim is not made a scheduled entrypoint.** It rides `run_once`. A
standalone scheduled sweeper would be dead code until J8 exists, and writing dead
code to a schedule that has not been designed is how the schedule gets designed
around the code instead of the other way round.

**J9 is not folded into J12.** §3.3. Different table, different detector,
different recovery, and a migration this document does not want to force.

**`_record_failure_safely` is not made to re-raise or retry.** §3.4(3). Both
close the route that is easy to test and neither closes the route that is likely,
and the swallow is correct once the reclaim exists.

**No online-mode test is written for F11.** §4.5. With `0003` as head there is
no online-observable difference to assert, and the test that could be written
would be a race against a millisecond-long migration. A flaky test asserting a
transaction boundary is worse than a reviewed three-line diff.

**Nothing is deployed and nothing here changes that.** Every severity in this
document is a statement about what will happen, not about what is happening.

---

## 8. Assumptions

1. **Nothing is deployed and no production data exists.** J12's "fix it now while
   it is free" argument and F11's "the blast radius is developer machines and CI"
   argument both depend on this and both stop being true when it changes.
2. **Nothing writes `user_account`.** Verified by search: `principals.py` reads
   it, `schema.py` declares it, nothing inserts outside tests and fixtures. This
   is what makes F11's lock cost zero today — and note that the lock blocks
   *reads*, and `dependencies.py` reads `user_account` on every authenticated
   request, so the cost is exactly zero until the first deployment and not a
   moment longer.
3. **Nothing calls `run_once` on a timer** (backlog J8). This is why J12 harms
   nobody today and why its reclaim can ride `run_once` instead of needing a
   schedule.
4. **The probes in §2.1, §2.3, §3.1 and §4.1 were run against scratch databases**
   created with `createdb` + `alembic upgrade head` and dropped afterwards, at
   `1315e10` with no working-tree changes. The dev database was not mutated;
   `psql -l` confirms only `smartmatch` remains.
5. **`code-review` at `high` runs on each staged diff before commit**, per the
   process requirements in `docs/plans/orchestrator-handoff.md`, and its findings
   are verified against the code before being acted on.

---

## 9. Open questions

Each needs a named decision, not a default.

| # | Question | Owner |
|---|---|---|
| 1 | Should quota consumption move out of the command transaction entirely (§2.3(c))? It is the coherent version of what the savepoint does locally, it applies to every command route, and it decides whether a 500 after the check costs quota. | Engineering, with whoever owns S-008 |
| 2 | Does this project want a concurrency harness for integration tests? Three things in this document are argued from SQL semantics rather than tested: `RedriveConflictError`'s two paths, the reclaim-versus-live-lease race, and `SKIP LOCKED` disjointness under real contention. Two of them already existed before this plan. | Engineering |
| 3 | Should `DispatchOutcome.reclaimed` be a metric an operator alerts on, or only a counter in the pass summary? A non-zero value means a dispatcher died or the database refused a write at exhaustion — arguably more alert-worthy than lag. | Engineering, with whoever owns the v1.1 §1.6 alert |
| 4 | F11: is there any planned migration that must be atomic with a sibling revision? If yes, the review rule in §4.3(1) needs writing down before `0004`, not after. | Engineering |
| 5 | Once a deploy pipeline exists, what re-runs `alembic upgrade head` after a partial failure (§4.3(2))? Per-migration transactions make partial progress durable, which is an improvement only if something finishes the job. | Whoever builds the pipeline |
| 6 | Should the flaky test in §6 (J13) be fixed by pinning the test or by making `claim_batch` deliver FIFO? Both are recommended here; if only one is done, which. | Engineering |
