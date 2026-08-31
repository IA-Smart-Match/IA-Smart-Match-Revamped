# ADR-0015 — Charge quota before the route can refuse the request

**Status:** Accepted
**Date:** 25 August 2026
**Contract:** Architecture v1.1 §3.4 (layer 2), §3.6 (N4), §1.6
**Backlog:** J16
**Refines:** ADR-0006, which decides *how* the counter counts. This decides
*when* it is incremented.
**Proposed amendment, not yet ratified:** A1 — *Counting quota and monetary
spend are not the same control*, at the end of this file. Required by
`docs/decisions/g3-crawler-decision.md` §4.1 (signed 2026-08-29). It adds a rule
for a class of limit this ADR does not currently cover and **changes nothing
decided above**. The `**Status:**` line stays a bare `Accepted`, with no
amendment note, until a human ratifies A1.

## Context

Every command route in the API charged quota in the same place: after it had
loaded the resource, after it had authorized the caller, and after it had
validated the header and the body. `POST /v1/jobs/{id}/redrive` ran
`_load_job_or_404`, `_authorize_redrive`, `_require_reason` and
`_require_idempotency_key` before `enforce_rate_limit`; `POST
/v1/units/{id}/imports` was one step worse, because its charge lived inside
`submit_command`, which is past the unit load, past `assert_allowed`, and past
the router's own body check.

So a `403`, a `404` and a `400` cost the caller nothing. Measured through the
HTTP surface, 25 consecutive refusals of each kind, on both routers: the
`rate_limit_counter` row for the caller moved by **zero**. That measurement is
now a test rather than a note — `test_a_run_of_forbidden_redrives_is_charged_and_then_limited`
and its five siblings each fail against the old ordering with exactly this
message: *"25 denials moved the counter by 0"*.

Two things made this worse than a rounding error.

**The free refusals were the cheap ones.** Producing a `403` needs a token and a
job id. Producing a `404` needs a token and a random UUID — not even a job. A
`400` needs a token and an omitted header. Producing an *accepted* command, the
only thing that was charged, needs a real parked job in a re-drivable state.
A limiter that bounds the expensive path and leaves the three cheap ones
unmetered has the sign backwards on exactly the traffic v1.1 §3.4 layer 2 exists
to bound. A caller looping on `404`s could probe the job id space at whatever
rate the API would serve, and be told each time, at full speed, that the id did
not exist.

**Reordering alone would not have fixed it.** The increment lived in the
request's own transaction, and `get_session` ends every request with an
unconditional `finally: session.rollback()`. A charge moved to the top of the
handler and left uncommitted is discarded by that rollback on precisely the
paths this ADR is about — every one of them leaves by raising. This is the same
mechanism recorded as backlog **J15** for the `500` case, and as the reason
`submit_command` already committed its quota before letting an idempotency
conflict propagate — the one exception ADR-0006 names to its own "the caller
commits, alongside the request's own work" rule.

The remedy was deliberately not applied when J11 and J15 were fixed, because it
is not a reordering anyone should make silently. Charging before authorizing
decides that an authenticated caller pays for requests they were never allowed
to make; charging before the load decides that they pay for ids that do not
exist. That is a decision about who bears the cost of a rejected request, not a
bug fix, and it belongs in an ADR rather than in a commit message.

## Decision

**A command route charges quota as its first statement, and the charge commits
immediately, in a transaction of its own.**

Concretely, in `services/api/smartmatch_api/dependencies.py`:

```
charge_quota(session, principal, LIMIT)   # consume, then commit
    → QuotaCharge
```

`charge_quota` calls the unchanged `enforce_rate_limit` — the same guarded
`ON CONFLICT` ADR-0006 specifies, failing closed the same way — and then calls
`session.commit()`. Nothing else has run yet, so the commit persists the
increment and nothing else. Both halves are load-bearing: the ordering decides
*that* a refusal is charged, and the commit decides that the charge survives the
refusal it is being charged for.

The receipt exists so the rule is structural where it can be.
`submit_command` no longer takes a `RateLimit` it would apply itself; it takes
the `QuotaCharge` its router produced. A command route therefore cannot accept a
command it never charged for, and `mypy` says so at the call site. What a
signature cannot enforce is that the charge is *first*; that stays the router's
discipline, and it is checked by tests that count the counter after a run of
refusals.

**This applies to every command route, and to every command route added later.**
It is a standing rule, not a fix to two handlers: `/imports` is changed here
alongside `/redrive` and `/abandon` even though the defect was measured on the
latter, and match-run, discovery and send commands inherit it when their gates
open. Quota is now the first thing a mutating route does with the database.

Three kinds of request are deliberately **not** charged, named here so their
absence is a decision rather than an oversight:

* **`401`.** An unauthenticated caller has no subject to charge. This is
  ADR-0006's own boundary — the counter is keyed by `(tenant, subject,
  operation)` — and v1.1 §3.4 gives that traffic to layer 1 and to an IP-keyed
  limiter that does not exist yet.
* **`422`.** FastAPI validates the path parameters and the body before the
  handler is entered, so a malformed body or a `job_id` that is not a UUID is
  answered without any handler statement running. Charging it would mean making
  the charge a route *dependency* rather than a statement. Left open on
  purpose: a `422` is the one refusal here that is genuinely cheap to *serve*
  as well as cheap to produce, since it is answered before the request reaches
  the database at all.
* **Reads.** No read is rate-limited today. When one is, it gets
  `enforce_rate_limit` and a decision of its own; a read that fails has produced
  nothing for the caller to have gained by, so the argument above does not
  simply carry over.

## What this costs

**An authenticated caller pays for requests they were never allowed to make.** A
coordinator whose role was revoked this morning, or a viewer who has never had
the role, spends real quota on every `403`. Their capacity to do the things they
*are* allowed to do is reduced by requests the system refused.

**They pay for ids that do not exist.** A client with a stale job id, a
mistyped UUID, or a bookmark pointing at a job in a tenant they left, is charged
for each `404` — and the tenant-scoped lookup means "another tenant's job" and
"no such job" are the same answer, so this includes being charged for other
people's work being invisible to them.

**They pay for their own client's bugs.** A retry loop on a missing
`Idempotency-Key` header now exhausts the user's window, and the symptom is a
`429` on the *next* legitimate command — a failure that looks unrelated to its
cause. Both routes here share the `job.redrive` bucket, so refused abandons
consume the quota a real re-drive would need.

**Every command request now costs two commits instead of one.** The charge
commits, then the command commits. ADR-0006 already accepts one write on the
request path before the work being limited; this is a second round trip on the
same connection. It is not the second *connection* that
`docs/plans/transaction-boundary-defects.md` §2.3(c) priced when it described an
autonomous-connection variant — the session is reused, and no second pool slot
is taken.

## Why that is the better trade

The costs above are all borne by a caller who has been refused. The cost of the
alternative was borne by everyone else, and it was structural rather than
occasional: **the refusals cheapest to produce in bulk were the ones that cost
nothing**, which is precisely backwards for a limiter whose purpose is to bound
abusive traffic. A limit that binds only on well-formed, authorized, legitimate
commands is a limit on legitimate use.

Charging for refusals also makes the limiter's own answer honest. Before this,
`X-RateLimit-Remaining` described a caller's ability to issue *accepted*
commands, and said nothing about the load they were placing on the API; a caller
sending a thousand refused requests a minute had a full quota throughout.

And the cost is not permanent for anybody. The fixed window hands the quota back
at the next boundary with nobody intervening — there is no ban list, no lockout
row, and nothing an operator has to clear. A caller punished for a stale
bookmark waits out the remainder of one minute. That asymmetry — the harm from
charging is measured in seconds and self-heals, the harm from not charging is an
unmetered request class — is what decides it.

## The window question ADR-0006 did not have to answer

If refusals consume quota, a caller can exhaust a window **without performing a
single successful command**. That was not possible before, and ADR-0006 never
had to consider it. Asserted directly rather than left as an inference:
`test_refusals_alone_exhaust_a_callers_window`.

**Judged acceptable, with no additional bound, for three reasons.**

1. **The blast radius is the caller themselves.** ADR-0006 keys the counter by
   `(tenant, subject, operation)`, so a caller who spends their window on
   refusals denies only their own next request, on that one operation. Nobody
   else's quota moves, and nothing outside that operation is affected — the
   isolation ADR-0006 already ships is what makes self-inflicted exhaustion an
   acceptable outcome rather than a denial of service.
2. **Any bound would be a discount, and the discount is trivially earned.**
   "Refusals cost half", "the first N refusals are free", "only 403s count" — each
   reintroduces a class of request that is cheaper than the others, and a caller
   choosing which requests to send picks the cheap one. That is the defect this
   ADR closes, re-created at a smaller scale and harder to see.
3. **Recovery needs no intervention.** A fixed window is self-clearing. The
   worst case is one window's delay for a caller whose client is misbehaving,
   and the `429` already carries `Retry-After` pointing at the boundary.

**The condition under which this should be revisited, stated so it is not
rediscovered by an incident.** All of the above rests on these windows being
short: `job.redrive` and `import.create` are 10 requests per *minute*. Nothing
structurally holds that — `MAX_RATE_LIMIT_WINDOW` permits 31 days, and a daily
or monthly quota is a plausible thing to add. Under a long window, a client bug
that burns the quota on `400`s locks the user out for the rest of the day, and
the self-healing argument stops carrying the weight it carries here. **A limit
with a window longer than a few minutes should not adopt this rule without
deciding again**, and the honest options at that point are a separate, smaller
allowance for refused requests, or leaving refusals uncharged on that one
operation and accepting the hole with the reasons written down.

**ADR-0006 is not amended.** Its decision — a fixed window counted in
PostgreSQL, with a guarded `ON CONFLICT` and no read-then-write — is unchanged
in every particular. What changes is where a route calls it from and when the
increment commits, which is this ADR's subject. One paragraph of ADR-0006 is
overtaken rather than wrong: the exception it records, that `submit_command`
commits the quota before an idempotency conflict propagates, is no longer an
exception. It is the general rule, moved to the front of the request, and the
special case in `commands.py` is gone because the quota is already durable by
the time a key is looked at.

## Consequences

**Good.** A run of refusals now stops. Whatever a caller sends, the eleventh
request in a minute against `job.redrive` is refused by the limiter rather than
served — which is the property the limiter was documented to have and did not.
The three routers state the rule identically, so a reader comparing them sees
one shape rather than three orderings.

**Good, and slightly unexpected.** The J15 hole in `commands.py` closes as a
side effect. A `500` after the quota check there used to refund the quota,
because the increment shared the transaction that rolled back; it now commits
before `submit_command` is called, so nothing later can take it back. The
savepoint that J11 added to `redrive.py` was the local version of this
guarantee; the general one now sits in front of it.

**Cost, and left in place deliberately.** That makes J11's savepoint and J15's
broad `except` blocks redundant *for the quota's sake* — the increment no longer
needs rescuing, because it is no longer in the transaction being rolled back.
They are kept, because they still say the other half — the command did not
happen, and a refused command leaves no reservation, no parking, no stray
`redrive_record` — and because removing them is a separate change with its own
tests and its own risk. A reader should not conclude from their presence that
the quota depends on them; the module docstring says so in as many words.

**Cost.** `submit_command`'s signature changed, and its module docstring's "one
transaction" list is one item shorter: the reservation, the job with its
payload, and the outbox row commit together, and the quota does not. That list
was a statement about atomicity that no longer holds for quota, and it is better
to shorten it than to let it read as though a failed command refunds.

**Cost.** Two writes on the request path where there was one. See above.

## Alternatives considered

**Leave the ordering alone and accept that cheap refusals are free (the status
quo).** This is what J16 recorded and declined to change silently. It is
defensible only if refusals are cheap for the *server* as well as for the
caller, and they are not: a `404` here is an authenticated request, a principal
lookup with its memberships and grants, and a tenant-scoped job query. It is
the id-space probe that decides it — an unmetered `404` is an oracle you can
call as fast as the API will answer.

**Charge first, but leave the increment in the request's transaction.** The
minimal-looking change, and it fixes nothing: `get_session`'s unconditional
rollback discards the increment on every path that raises, which is every path
this ADR is about. Verified rather than assumed — it is the mechanism J15
measured at quota `0` before and `0` after.

**Wrap each handler in a broad `except` that commits the quota on the way out.**
This keeps the command in one transaction and still charges for refusals. It was
rejected for a specific failure mode: if the exception came from PostgreSQL, the
transaction is already aborted, and `session.commit()` in the handler then
raises `PendingRollbackError` *over* the original error — the caller gets a
confusing 500 and the operator loses the real one. `redrive.py` can do it safely
only because its savepoint gives it a `ROLLBACK TO SAVEPOINT` first; `imports.py`
and `commands.py` have no savepoint, and giving them one to solve a rate-limit
problem is the tail wagging the dog.

**Make the charge a route dependency rather than a statement.** This would also
cover the `422`, since FastAPI solves sub-dependencies before it validates the
request's own parameters. Rejected for now as more machinery than the decision
needs — a per-operation dependency factory, and a second place where the
ordering rule lives — and because it would make the charge invisible at the top
of the handler, which is where a reader looks for it. Named here because if the
`422` gap is ever judged to matter, this is the shape that closes it.

**A separate, smaller allowance for refused requests.** The obvious "fair"
answer: charge refusals against their own bucket, so a client bug cannot spend
the quota a legitimate command needs. Rejected as a discount for the reason
given under the window question — whichever class is cheaper is the class an
abusive caller sends — and as premature: it doubles the counter rows per caller
and needs two numbers tuned instead of one, against limits v1.1 §3.4 already
describes as "still hypotheses to be tuned with recorded evidence". It is the
first thing to reach for if the window question above is ever reopened.

---

# Amendment A1 — Counting quota and monetary spend are not the same control

**Status of this amendment:** **PROPOSED.** Not ratified. Nothing below is in
force, and no code implements it.
**Date drafted:** 30 August 2026
**Mandated by:** `docs/decisions/g3-crawler-decision.md` §4.1 and §10 row 4,
decided 2026-08-29 and signed the same day by the G3 owner of record.
**Approver of this amendment:** ______________________ *(blank — deliberately.
G3 §4.1 authorizes this amendment to be **written**; it does not ratify its
text. An agent drafted this. Ratification is a human act, and the field stays
empty until one performs it.)*
**Changes no code.** No cost ceiling exists in the repository today, no paid
call is made from any code path, and nothing is deployed. Everything in this
amendment is a **requirement on future work** — G3 §4.1 files it as a *new work
item that must land before cost ceilings are implemented* — and is written in
that tense throughout. Where a sentence below describes a mechanism, it
describes one that must be built, not one that runs.
**Deliberately not recorded in the index's `Amended` column.** The ADR's
`**Status:**` line above still reads a bare `Accepted`, which is honest: the
body of the accepted decision has not moved, and an unratified draft must not
make the index claim it has. When A1 is ratified, the ratifying change is the
one that updates both the status line and
`docs/architecture/decisions/README.md`'s row, together, in one commit —
`tests/unit/test_adr_index.py::test_an_amended_adr_is_marked_amended_in_the_index`
ties those two ends and will say so if they are separated.

## What ADR-0015 does not cover

Everything above this line reasons about one kind of resource: a **request
count**. `rate_limit_counter` is a row this system owns, in a database this
system controls, incremented by a statement this system issues. That is what
made the decision above available at all. "Charge as the first statement, commit
immediately, let the refusal be paid for" is a sensible rule only because the
charge is *the system's own bookkeeping*: it can be applied before anything has
been decided, precisely because applying it costs nothing outside the row.

G3 §4 introduces a second kind of limit, and it is not a counter:

> **Cost ceiling L21 = $2.00 per job.** Tenant ceilings: $25/day, $250/month,
> 5,000 fetches/day.

Three of those four bound **money paid to an external LLM provider**. G3 §7.1
decided that tier-3 prose extraction — the paid path — **ships in the first
release**, so those ceilings are load-bearing rather than theoretical; §7.1 says
so in as many words. The crawler threat model draft carries the same control at
row **T-08** of its threat catalog
(`docs/security/crawler-threat-model-draft.md:155`, revision 4 as read on
2026-08-30), whose required-control cell reads — quoted exactly:

> Per-run and per-tenant budget incl. G3's **5,000 fetches/tenant/day**;
> reserve-before-spend with an atomic concurrency contract, idempotent
> reconciliation, defined retry semantics and **conservative**
> abandoned-reservation reclamation per **ADR-0015 Amendment A1** (not yet
> landed): an expired, unreconciled reservation is **unconditionally treated
> as spent at its reserved maximum**, flagged as an estimate, and not
> released (A1 withdrew the "positive evidence the call never happened"
> exception: nothing in the design produces such evidence, and an exception
> no component can establish invites supplying it by inference) — releasing
> by default turns every worker crash into free budget, a control that fails
> open; **escalation** to `discovery_review_item`, rate-limited and
> deduplicated so budget failures cannot flood the queue (see T-17)

**How that file is cited below.** It is an unsigned draft under active revision,
so its line numbers move. Every reference to it names the **row ID**, which is
stable; the line number is a locator for the revision named above and nothing
more. A reader who finds the line wrong should re-read the row by its ID — and
should re-check that the row still says what is attributed to it here, because a
citation that has drifted is indistinguishable from one that was invented, and
this amendment's whole subject is the difference between a recorded figure and a
plausible one.

A dollar paid to a provider is not a row this system owns. It is an **external
side effect the system cannot reverse**. The call goes out, the tokens are
consumed, the invoice line exists, and no `ROLLBACK` reaches it. That single
asymmetry is what this amendment turns on, and it is why the rule above — which
is right for a counter — is structurally wrong for spend.

## The decision recorded here

**Counting quota is unchanged. Monetary spend gets a different rule: reserve the
maximum estimated cost atomically *before* the paid call, then reconcile the
reservation to the actual cost after it.**

Stated as the three obligations a future implementation has to meet:

1. **Reserve.** Before any paid provider call, atomically debit the **maximum
   estimated cost** of that call against every ceiling it is subject to — per
   job, per tenant per day, per tenant per month. The debit is **all-or-nothing
   across all three**: either every ceiling admits it or none of them is moved.
   See *Three ceilings, one debit* below, which is where that requirement stops
   being a slogan.
2. **Refuse at reservation time.** A reservation that cannot be taken **is** the
   refusal. There is no separate "check" whose answer the caller then acts on.
   This is the same structural move ADR-0006 makes for the counter, for the same
   reason, and it is spelled out under *Concurrency* below.
3. **Reconcile.** After the call returns — or fails, or times out — replace the
   reservation with the actual cost: release the difference when the call cost
   less than the maximum, record the overage when it cost more. A reservation
   that is never reconciled must be reclaimable without a human. The three
   outcomes are not symmetric, and *The reservation row's states* below defines
   each of them, including the two that have no actual cost to reconcile to.

Refusal therefore happens *before* money moves, which is the only place a
monetary refusal can mean anything. The counting-quota rule puts the charge
before the refusal; the spend rule puts the **refusal before the spend**. Those
read like opposites and are the same principle applied to two resources with
opposite reversibility: **do the irreversible thing last**. For a counter, the
increment is the reversible half and the request is the expensive half, so the
increment goes first. For spend, the debit is the reversible half and the
provider call is the irreversible one, so the debit goes first there too. The
ordering is identical. It is the vocabulary — "charge", "refuse" — that makes
them look opposed.

## Why a post-hoc check overshoots by exactly one call, every time

This is the mechanism G3 §4.1 names, and it is worth writing out rather than
asserting, because it is the kind of defect that reads as a rounding error and
is not.

A post-hoc check is the obvious implementation:

```
spent = read_spend_so_far(job)      # $1.97 against a $2.00 ceiling
if spent >= CEILING:                # 1.97 >= 2.00 is false
    raise BudgetFailure             # so this does not fire
result = call_the_llm(page)         # $0.035 leaves the building
record_spend(job, result.cost)      # the ledger now reads $2.005
```

Every step is correct in isolation and the composition is wrong. The check reads
a balance that is **under** the ceiling and authorizes a call whose cost lands
*after* the decision was taken. The ceiling is therefore not a ceiling: it is a
threshold above which the *next* call is refused, and the last authorized call
sits on top of it. **The ledger exceeds the ceiling by the full cost of one
call, on every job that reaches its budget** — not occasionally, and not for
some inputs. The overshoot is a property of the ordering, not of the numbers, so
no amount of tuning removes it.

Two things make it worse than that arithmetic suggests.

**The overshoot is bounded by the most expensive call, not the average one.** A
`$2.00` job whose last authorized call happens to be a long prose page is over by
that page's whole cost. Nothing in a post-hoc check bounds *which* call lands
last, so the ceiling's real value is `CEILING + max_call_cost`, and
`max_call_cost` is a property of the provider and the page rather than of
anything this system decided.

**Under concurrency the overshoot is N calls, not one.** G3 §4 sets *concurrency
1 per host, 4 global*. Four workers extracting for the same job — or four jobs
under one tenant's `$25/day` — each read the same under-ceiling balance before
any of them has written its cost back, each concludes there is room, and each
spends. The ceiling is then exceeded by up to `N × max_call_cost`, and `N` is a
tuning parameter someone will raise for throughput without ever connecting that
change to the budget. This is not a new observation: it is exactly the
check-then-act window ADR-0006 rejected under *"Read-then-write against the same
table"*, reappearing in a control where the losing race does not cost a
permitted extra request but **money that has already left**.

That last clause is the whole difference in severity. ADR-0006's races cost a
request. This one cannot be corrected afterwards, because **an LLM call cannot
be un-spent** — G3 §4.1's own phrasing, and the reason it required an amendment
rather than a bug fix.

## Concurrency and failure semantics

An amendment that stopped at "reserve then reconcile" would be a slogan. These
are the parts that decide whether it is implementable, each stated as a
requirement on the future work.

**Reservation atomicity — the same shape ADR-0006 already uses, not
read-then-write.** The reservation must be one guarded write whose failure to
match *is* the denial: the

```
INSERT INTO spend_ledger (key, reserved, spent)
SELECT :key, :estimate, 0
    WHERE :estimate <= :ceiling          -- guards the INSERT path
ON CONFLICT (key) DO UPDATE
    SET reserved = spend_ledger.reserved + :estimate
    WHERE spend_ledger.reserved + spend_ledger.spent + :estimate <= :ceiling
    RETURNING ...
```

shape, where `RETURNING` yielding no row is the refusal. ADR-0006 states the
reasoning for the counter and it transfers — *"there is no separate read, so
there is no window between deciding and recording"*. A reservation written as
`SELECT`, compare, `UPDATE` reinstates the overshoot above one layer down, and
is harder to see there because the code will *look* like it reserves. **A
reservation that is not a single conditional write is not a reservation.**

**Where the sketch departs from ADR-0006's, and why it must.** ADR-0006's
statement guards only the `DO UPDATE` branch, because for a counter that is
sufficient: the first increment against a fresh key is `1`, and `1` is under any
sane limit, so an unguarded insert can never admit an over-limit row. **A dollar
estimate has no such property.** An unguarded insert admits *any* estimate —
however large — whenever the ledger row does not yet exist, and there are three
routine ways for it not to exist: a ceiling lowered since the last write, the
first call in a new day or month bucket, and an unusually expensive first call
on a fresh job. Each of those is a single call that silently exceeds its ceiling
in full, and it is exactly the class of hole this amendment exists to close. So
the insert's source row is guarded too — the `SELECT ... WHERE :estimate <=
:ceiling` above, which yields no row and therefore inserts nothing when the very
first reservation is already over. **ADR-0006's shape is reused; its statement is
not copied verbatim, and an implementer who copies it verbatim reintroduces the
defect.** A test for this is named in *What has to happen before this is in
force*: a first reservation, against a key with no row, for an estimate larger
than the ceiling, must be refused.

## Three ceilings, one debit

Obligation 1 says the debit is all-or-nothing across per-job, per-tenant-per-day
and per-tenant-per-month. **Those are three rows, and one `INSERT … ON CONFLICT`
has one conflict target.** The sketch above is the shape of *a* guarded debit
against *one* ceiling; it is not by itself the debit obligation 1 requires. This
is named here because leaving it implicit would be the same mistake one level
down: a slogan that reads as a design and decides nothing.

The honest options, and what is wrong with each:

* **Three sequential guarded writes, with compensating release on partial
  failure.** The obvious build, and the one an implementer reaches for. It
  reintroduces a **partial-debit state** — the per-job row moved, the per-day row
  refused — so the compensating release becomes a correctness-critical path that
  itself runs after a failure, which is when processes die. And because two
  workers can take the three rows in different orders, it **deadlocks** unless a
  fixed row-lock ordering is imposed and documented. Whichever failure mode is
  not handled shows up as a ceiling that drifts, slowly, in the direction of
  free budget.
* **One composite statement — a CTE that checks and updates all three rows,
  succeeding only if every branch admits the estimate.** Preserves
  all-or-nothing in one round trip and one lock scope, at the cost of a
  statement that is materially harder to read and to test than ADR-0006's, and
  that has to create three missing rows as part of the same all-or-nothing.
* **A single denormalized row carrying all three balances.** The simplest write
  and the worst model: day and month buckets roll over on different clocks and
  the per-job ceiling is scoped to a different entity, so one row means either
  duplicated state or a rollover rewrite, and the per-job row cannot be
  garbage-collected independently.

**This amendment does not choose between them, and says so rather than implying
the choice is made.** It is a schema decision that needs the ledger's shape in
front of it, and the ledger does not exist. What A1 **does** settle:

* **All-or-nothing is the requirement, not an implementation preference.** A
  design in which one ceiling can be debited while another refuses is
  non-conforming, whatever the mechanism.
* **If the sequential option is taken, two things are mandatory rather than
  advisable**: a fixed, documented row-lock ordering across all three ceilings,
  and a release path for a partial debit that is idempotent and reachable by the
  reclaim sweep — because the compensating release will sometimes not run at
  all, and the sweep is then the only thing that recovers the stranded capacity.
  A partial debit left unreleased must fail in the conservative direction: held,
  not released, until the sweep resolves it.
* **The choice must be recorded** in the work item that builds the ledger, with
  the failure mode it accepts written out. Naming which of the three was chosen,
  and why, is the deliverable; leaving it to be settled inside a pull request is
  how the partial-debit state gets built by default.

**The reservation must survive a rollback, the way `charge_quota`'s commit
does — and for a stronger reason.** `charge_quota`
(`services/api/smartmatch_api/dependencies.py:208`) calls `session.commit()` at
line 251 because `get_session`'s unconditional `finally: session.rollback()`
(line 74, in the generator opened at line 61) would otherwise discard the
increment on every path that raises. A reservation faces the same mechanism with
worse stakes: if it shares a transaction that rolls back **after the provider
call was made**, the money is spent and the ledger holds no record of it — the
ceiling silently regains headroom it did not earn, and the next job spends it
again. So the reservation commits in a transaction of its own, before the call,
exactly as the charge does. Noted honestly: this work is worker-side (G3 §9,
*"All network activity is worker-side; API handlers record commands and review
decisions only"*), so `get_session` is not literally the session in play. The
*rule* carries over; the dependency does not.

**Idempotency: a retry must not double-reserve.** This repository retries durable
work by design and says so. `services/worker/smartmatch_worker/execution.py:8`
opens with *"Cloud Tasks delivers **at least once**. A duplicate delivery is not
a fault"*, and `services/worker/smartmatch_worker/dispatcher.py:31-38` records
the claim-then-commit ordering whose stated purpose is that *"the deterministic
task name makes the retry a no-op rather than a double dispatch"*. A reservation
keyed only by `(job, tenant)` and incremented per attempt inherits none of that:
a redelivered task reserves again, and a job retried three times consumes three
times its budget in reservations without making three times the calls. **The
reservation therefore needs a deterministic key for the unit of work it is
reserving for** — the same discipline the dispatcher already applies to task
names — so that re-reserving the same unit is recognised rather than added.
`QuotaCharge` (`dependencies.py:187`) is the API-side precedent for turning a
precondition into a value a later step must be handed; the reservation receipt
should be the same kind of object, and for the reason that docstring gives — so
a paid call cannot be made by a path that never reserved, and a type checker
says so at the call site, the way `submit_command`
(`services/api/smartmatch_api/commands.py:87`, taking `charge: QuotaCharge` at
line 95) already does for quota.

**Abandoned reservations, and how they are reclaimed.** The hard case: the worker
dies between reserving and reconciling. The reservation is then a debit against
the ceiling for a call whose outcome nobody recorded, and left alone it strands
that capacity forever. The system already owns machinery for this shape, and the
amendment should reuse it rather than invent a second one: a job is claimed with
a lease in the same conditional `UPDATE` that takes it `dispatched -> running`
(`execution.py:470`), the lease is renewed on every progress emission
(`execution.py:426`, renewing at line 454), and `StalledJobSweeper`
(`execution.py:502`) takes whatever is left from `running` to `timed_out`. **A
reservation gets a lease or an expiry on the same footing**, and a sweep
reclaims expired ones. Two consequences must be decided by whoever implements
this, and are named here so they are not discovered during an incident:

* **A reclaimed reservation whose call actually succeeded is the dangerous
  case.** The worker died *after* the provider was paid; releasing the
  reservation returns headroom for money that genuinely left. The reclaim must
  therefore be conservative: an expired, unreconciled reservation is
  **unconditionally treated as spent at its reserved maximum**, flagged as an
  estimate, and not released. Releasing by default turns every worker crash into
  free budget, which is a control that fails *open*, and v1.1 §3.6 (N4) — the
  clause ADR-0006 cites for failing closed — does not permit a budget check to
  be skipped under partial infrastructure failure.

  *A draft of this amendment wrote "unless there is positive evidence the call
  never happened". That exception is withdrawn, because **nothing in this design
  produces such evidence.** The reservation is written before the call, so a
  surviving reservation row is equally consistent with "reserved, never
  dispatched" and with "reserved, request in flight, provider paid". There is no
  durable pre-call marker separating the two. An exception whose precondition no
  component can ever establish is not a safety valve — it is an invitation to
  supply the evidence by inference, which is the fabricated-value defect again.*

  **The marker that would earn the exception back, named and not adopted.** A
  second durable write immediately before dispatch — `reserved` → `dispatched`,
  committed — would make "still `reserved` at expiry" positive evidence the
  request never left. It is rejected here for now on cost: it adds a third
  committed write bracketing every paid call, on a path this amendment already
  charges two to, and it narrows rather than closes the window, since the worker
  can still die between that commit and the socket write. It is the right thing
  to reach for if conservative reclaim is later measured to be materially
  over-charging, and it must be adopted *before* any exception to
  spent-at-maximum is written down — not after.
* **Reconciliation itself must be idempotent**, because the sweep and a late
  worker can both reach the same reservation.

### The reservation row's states

The obligations above compose into a case an implementer meets on day one and
would otherwise decide by guessing: conservative reclaim converts an abandoned
reservation to **spent**, while idempotent re-reservation expects a redelivered
task to find its own **reserved** record. A worker dies, the sweeper marks the
reservation spent-at-maximum, Cloud Tasks redelivers, and the retry presents the
same deterministic key against a row that is no longer reserved. Proceeding
double-charges for one call; refusing lets a single crash poison that unit of
work permanently; reusing the spent record silently un-does the conservative
reclaim. **A design that does not say which is a design that will be built all
three ways.** So the row's states are defined here.

A reservation row is in exactly one of four states:

| State | Meaning | Reached from |
|---|---|---|
| `reserved` | Debited against every ceiling; the call may or may not have been made | the guarded write of obligation 1 |
| `reconciled` | The call's actual cost is recorded; the difference from the maximum is released, or the overage recorded | `reserved`, by the worker that made the call |
| `expired_spent` | Lease expired unreconciled; held at the reserved maximum, marked **estimated, not actual** | `reserved`, by the reclaim sweep |
| `released` | The debit was returned in full; the ceiling has the capacity back | `reserved` only, and only under the one condition below |

`reconciled`, `expired_spent` and `released` are **terminal**. There is no
transition out of them and no path back to `reserved` — the same construction
`failed_budget` has in `TRANSITIONS`, and for the same reason: a state that can
be re-entered is a state whose accounting can be repeated.

**What a redelivery does, per state.** The retry presents the deterministic key
of obligation *Idempotency* and finds:

* **`reserved`** — recognise, do not add. The debit already stands for this unit
  of work. The retry proceeds to the call under the existing reservation. This
  is the case the deterministic key exists for, and it is the only one in which
  the retry may make the paid call under a debit it did not itself take.
* **`reconciled`** — **refuse.** This unit of work has a recorded actual cost, so
  the call was made and paid for; a redelivery that calls again spends a second
  time for one unit of work. The redelivery is a no-op returning the recorded
  outcome, exactly as `dispatcher.py`'s deterministic task name makes a duplicate
  dispatch a no-op rather than a second dispatch.
* **`expired_spent`** — **refuse, and require a new reservation to proceed.** The
  ceiling is already debited at maximum for this unit; permitting the retry to
  reuse that debit would let one crash-and-retry pair make two paid calls under
  one debit, and permitting it to take a *fresh* debit silently is how a crash
  loop becomes an unbounded spend. So the retry does not call. Whether that unit
  is ever attempted again is a **budget decision, not a delivery decision**: it
  requires a new reservation taken under the ceiling as it now stands, which
  will fail if the ceiling is exhausted, and that is the correct outcome. The
  cost of this rule is stated plainly: **a crash after reserving permanently
  ends that unit of work under the current budget.** It is chosen because the
  alternative — retrying freely against a debit the system already treated as
  spent — fails open, and the reason `expired_spent` exists at all is that the
  system cannot tell whether the money left.
* **`released`** — recognise as never-charged and re-reserve normally, as though
  no prior attempt existed. Safe only because `released` is reachable under one
  condition alone (below).

**`released` has exactly one entry condition.** A reservation is released in full
only when the reserving worker is **still alive and knows the call was never
dispatched** — the guarded write succeeded and the code path then refused before
the request was issued, for a reason of its own. That is a release taken by the
process that holds the knowledge, in the same lease, not an inference drawn
later from a row's appearance. **The sweep never releases.** Any expired
reservation is `expired_spent`, without exception.

### Timeouts have no actual cost, and must not acquire one

Obligation 3 says reconciliation happens when the call *"returns — or fails, or
times out"*, and the first two are straightforward: a returned call reports its
cost, and a call that fails before the provider accepted it costs nothing that
the provider will bill. **A timeout is neither.** The client stopped waiting; the
provider may well have completed the generation and billed for it. There is no
actual cost available, and *Where the estimate comes from* forbids writing a
number that is not one — "an estimated dollar amount must never be recorded,
displayed, or reported as an actual one".

**The required behavior: an in-worker timeout reconciles to the reserved maximum,
held as spent, and explicitly flagged as estimated rather than actual** — the
same figure and the same flag as `expired_spent`, reached deliberately by a live
worker rather than by a sweep. It stays flagged until a billing audit resolves
it; the lazy reconciliation against the provider's billing API, described under
*Alternatives considered* as an audit rather than an enforcement mechanism, is
what eventually replaces the estimate with an actual or confirms the call was
never billed. A timed-out call therefore does **not** produce a `reconciled` row
— `reconciled` means an actual is recorded — and an implementer must not reach
for zero, for the estimate-as-actual, or for a retry that spends again. Zero is
the fail-open answer; the estimate presented as actual is the fabricated value.

**Progress emission is not optional here either.** G3 §3 records *"Progress
emission ≤60 s. `DEFAULT_JOB_LEASE` bounds silence, not duration"*, and
`execution.py:44-58` explains that a handler working longer than a lease with
nothing to say is swept and its eventual outcome discarded. A long extraction
job holding reservations is exactly such a handler, and the same rule binds it.

## Where the estimate comes from, and what an estimate is

The reservation is of an **estimated maximum**, and G3 §4 is explicit about the
provenance of that estimate:

> Assumptions at §3.2 and §3.2a of `g3-limits-and-policy-options.md`;
> **A3 (LLM price per page) is unverified** and must be confirmed against the
> actual provider.

A3 is `$0.035` per prose page
(`docs/plans/prep/g3-limits-and-policy-options.md:221`), derived from a
token-count assumption and never checked against a bill. It is a **named, dated
assumption**, and this amendment requires it to remain one:

* The price constant must be **named as an assumption in the code that uses
  it** — carrying its identifier (`A3`), its source, and the date it was
  recorded — not left as a bare float in a settings module where the next reader
  takes it for a measured figure.
* **An estimated dollar amount must never be recorded, displayed, or reported as
  an actual one.** A reservation is a reservation until reconciled; the ledger
  must keep "reserved (estimate)" and "spent (actual)" in separate columns, and
  any figure shown to a human must say which it is. This is the same discipline
  the portfolio already enforces as *unknown never becomes a fabricated value*
  (G3 §9), and which G3 §7 makes a must-pass invariant at MP-1: *"No output value
  the fixture does not evidence… a plausible invented value is a hard fail."* A
  plausible invented **dollar figure** is that same defect wearing a currency
  symbol.
* Until A3 is confirmed against the actual provider, **every ceiling computed
  from it is provisional** — L21's `$2.00` included. Confirming A3 is a
  prerequisite of the cost-ceiling work, not a follow-up to it.

**When the actual cost exceeds the reserved maximum.** It can, because a maximum
derived from an unverified assumption is not a bound the provider agreed to. The
required behavior: **record the overage as actual spend, never silently truncate
it to the reservation**, and treat the ceiling as breached from that moment so
the next reservation against it fails. The job that overran is not retroactively
refused — its call already happened, which is the whole argument above — but the
overage must be visible rather than absorbed, because a ledger that clamps
actuals to estimates is a ledger that cannot detect a wrong estimate. A
reconciliation that discovers a material overage is also the single best signal
that A3 is wrong, and is worth emitting as such.

## Relationship to `failed_budget`

Verified in the code rather than carried over from G3 §5 and the R3 findings,
both of which assert it: `TRANSITIONS[JobState.FAILED_BUDGET]` is `frozenset()`
— `python/smartmatch_domain/smartmatch_domain/jobs.py:86`, inside the
`TRANSITIONS` mapping opened at line 53 — and `TERMINAL_STATES` (line 93) is
derived from that mapping by comprehension over the states whose allowed set is
empty, under the comment at line 92: *"States from which no further transition is
legal."* So
`failed_budget` is terminal by construction rather than by a second list someone
has to remember to update. The worker's mapping from a declared failure to a
state, `services/worker/smartmatch_worker/execution.py:117`, sends
`BudgetFailure` to `JobState.FAILED_BUDGET`. It is genuinely terminal: a
budget-failed job cannot be re-driven, cannot return to `queued`, and cannot be
resumed.

**A reservation failure is a `BudgetFailure`, and therefore ends the job as
`failed_budget`.** That follows from the mapping above and is the right outcome:
the ceiling has been reached, and a per-job ceiling gives the job nothing to wait
for. It also means a reservation failure is **not** comparable to a `429`.
ADR-0015's counting-quota refusals are self-healing within one window, and the
argument under *"Why that is the better trade"* leans on that heavily. A
`failed_budget` job heals only when a human raises a ceiling or starts new work.
**The self-clearing argument above does not extend to spend and must not be
quoted as though it did.** This is the same caution ADR-0015 already gives itself
for long windows under *"The window question"*: the shorter the recovery, the
more a rule can be trusted to self-correct, and a monetary ceiling has no window
boundary at which anything is handed back.

**Whether a reservation failure also writes a `discovery_review_item` row is left
open here, deliberately.** T-08's test-expectation cell
(`docs/security/crawler-threat-model-draft.md:155`, revision 4) reads, exactly:
*"Concurrent reserve test (N parallel workers cannot exceed the ceiling); retry
does not double-charge; **an expired unreconciled reservation with no evidence
about the call leaves remaining headroom *reduced by its reserved maximum*,
not restored — a reclaim implemented as a release fails this test** (revision
4: "abandoned reservation reclaimed" was satisfiable by releasing it, which is
the direction A1 forbids); no input releases an expired unreconciled
reservation — a test asserting a release path exists must fail; reconciliation
is idempotent under a sweep and a late worker both reaching the same
reservation; budget exceeded ⇒ `failed_budget`, terminal; escalation row
created **once** per failure class per window, not per failure"*. G3 §5 accepts the new `discovery_review_item` table as
the escalation destination R3 found missing.

**The bound on that escalation is not this amendment's idea, and A1 does not
claim it.** T-08 as it now stands already requires the escalation to be
*"rate-limited and deduplicated so budget failures cannot flood the queue"*, and
already names the bound in its evidence — one row per failure class per window,
not per failure. Row **T-17**
(`docs/security/crawler-threat-model-draft.md:164`) is a review-queue-DoS threat
row in its own right, and names T-08's per-failure escalation rows as one of the
two things that amplify into it. What follows is therefore **agreement with an
existing control, restated so this amendment does not contradict it**, not a
requirement A1 introduces; the implementer's remaining discretion is over which
bound, not whether. The review queue is this system's scarcest resource — G3 §1
records that the binding constraint is *"human review capacity, not fetch
capacity"* — and a row written on **every** budget failure makes an unbounded
queue out of a bounded budget: whoever can cause budget failures can fill a queue
that people have to read. The portfolio already reasons this way about
neighbouring controls: L10's per-page artifact cap exists against *"Unbounded
parse output… flooding the event table and the review queue in a single job"*
(`docs/plans/prep/g3-limits-and-policy-options.md:118`), and R3 caps proposal
volume for T-12 *"so approval cannot be flooded"*
(`docs/security/r3-technical-review-findings.md:131`). The escalation must
therefore be **bounded** — deduplicated per job, rate-limited per tenant, or
aggregated — rather than one row per failure. Naming that bound is the
implementer's decision and belongs in the work item; what this amendment settles
is that "one row per budget failure, unbounded" is not acceptable — which is what
T-08 and T-17 already say, and A1 defers to them rather than restating a second,
possibly divergent bound. *(Stated plainly: this concern is **not** phrased as an
explicit finding in `docs/security/r3-technical-review-findings.md`; the T-12
citation above is the nearest thing there. It **is** phrased explicitly in the
threat model draft, at T-08 and T-17, and that is where it belongs. If those rows
change, they govern and this paragraph follows them.)*

## What this costs

In ADR-0015's own idiom, because a rule whose costs are not written down is a
rule someone will be surprised by.

**A second state transition and a second write per paid call.** ADR-0015 already
accepted that *"every command request now costs two commits instead of one"*.
Spend is worse in kind and not merely in count: a reservation and a
reconciliation are two writes that **bracket a slow network call**, so the
reservation stays durable for the whole latency of the provider round trip, and
the ledger row for a job in flight is always in a third state — neither "not yet
spent" nor "spent" but "reserved". Every consumer of that ledger has to
understand three states where a naive design has two.

**Reservations strand capacity until they are reclaimed.** Between a worker's
death and the sweep, a tenant's ceiling is debited for calls that may never have
happened. The stranding is bounded by the lease, the way `execution.py`'s job
leases bound how long a dead worker's job looks alive — but it is real, and it is
worst exactly when the system is unhealthy, which is when a tenant is least able
to work out why their budget is gone.

**A tenant can hit a ceiling for work that was never done.** The two paragraphs
above combined: reservations for abandoned calls, plus the conservative reclaim
rule that treats an unreconciled reservation as spent, means a crash loop can
consume a tenant's `$25/day` without producing a single extracted event. That is
chosen deliberately over releasing on doubt, which fails open — but it is a real
bill for nothing, and it wants an operator-visible signal rather than silence.

**A crash after reserving ends that unit of work under the current budget.** The
`expired_spent` rule refuses the redelivery rather than letting it reuse or
silently re-take the debit, so a unit whose worker died is not retried until a
fresh reservation is taken and admitted. Named as a cost rather than left to be
discovered: the platform's own idiom is that a redelivery is a routine event and
a retry is a no-op, and this is the one place where a retry is instead a refusal.
It is accepted because the alternative spends twice for one unit, or spends
without bound under a crash loop — but it means budget failures and worker
crashes are not independent, and an operator seeing `failed_budget` on a job that
never completed a call is seeing this rule, not a wrong ceiling.

**The ledger's three balances may not be one write.** *Three ceilings, one debit*
leaves the mechanism undecided, and every option there costs something real: a
harder statement, a partial-debit state with a lock ordering to maintain, or a
denormalized row that models rollover badly. The cost recorded here is that the
work item inherits an open decision — deliberately, because deciding it without
the ledger's schema in front of us would be guessing in an ADR, which is worse
than an open question in one.

**Reserving the *maximum* is deliberately pessimistic, so ceilings bind early.**
If the maximum estimate is `$0.035` and a typical page actually costs `$0.012`, a
`$2.00` job stops after roughly 57 reserved pages while its real spend is nearer
`$0.68`. A tenant hits the ceiling **before their actual spend warrants it**, and
the gap is exactly the estimator's pessimism. This is accepted: erring toward
refusing a call that would have been affordable is recoverable — raise the
ceiling, improve the estimate — while erring toward permitting one that is not is
the overshoot this amendment exists to close. But it means the ceilings in G3 §4
bind tighter in practice than their numbers read, and it is a second reason A3
needs verifying: a bad estimate makes the pessimism arbitrary rather than
calibrated.

**A cost in the document rather than in the system.** ADR-0015 was a single rule,
stated once, applying to every command route. It is now a document with two rules
and a distinction between them, and a reader who takes the headline — *charge
before refusal* — and applies it to spend produces exactly the defect G3 §4.1
rejected. That is why this is a marked section rather than an edit to the
sentences above, and why the section on what does not change exists at all.

## Alternatives considered

**Post-hoc check: read the ledger, then call (the status quo, and what would be
built by default).** Rejected. It is the mechanism spelled out above: a balance
read under the ceiling authorizes a call whose cost lands after the decision, so
the ceiling is exceeded by one full call on every job that reaches it, and by up
to `N` calls under G3 §4's global concurrency of 4. It has the additional
property of *looking* correct in review — there is a check, it precedes the call,
it uses the right constant — which is why G3 §4.1 recorded it as a decision
rather than leaving it to be caught by a reviewer.

**Charge the estimate before the call and never reconcile.** Tempting, because it
is the closest thing to the counting rule above and needs only one write.
Rejected on two grounds. First, it **systematically overcharges**: every call
costing less than its maximum estimate — which, if the estimate is an honest
maximum, is nearly all of them — permanently debits the difference, so a tenant's
`$250/month` buys materially less than `$250` of extraction, and the shortfall
grows with the estimator's caution. Second, and worse, **it makes the ledger a
fiction**. The recorded figure is a sum of estimates presented as spend; it will
not match the provider's invoice, and there is no point at which the system
notices the divergence. G3 §7's MP-1 forbids precisely this shape of output — a
plausible value the evidence does not support — and a budget ledger whose numbers
have never touched an actual cost cannot be used to verify A3, which is the one
thing G3 §4 says must happen.

**A hard provider-side spend cap alone.** Its appeal is that it is the only
control genuinely outside this system's ability to get wrong. It is rejected as a
*substitute*, in the same way ADR-0006 rejects edge-only rate limiting as a
substitute rather than a complement, for three reasons — and the third decides
it. It **does not exist here**: G3 §9 records no live providers and no production
credentials, so there is no account on which to configure a cap. It is **not
per-tenant**: one provider account cannot express `$25/day for this tenant`,
which is the ceiling G3 §4 actually decided, so one tenant's runaway consumes
another's headroom and the cap fires for everybody at once. And it **fails after
the money is gone**: a provider cap stops the *next* call, which is the post-hoc
check again, relocated somewhere this system cannot instrument, cannot attribute,
and cannot show a tenant. Worth having as a backstop against a defect in
everything above. Not the control.

**Treat monetary spend as just another counter and apply the unamended ADR-0015
rule to it.** This is the alternative G3 §4.1 explicitly rejected, and it
deserves more than "disallowed", because it is what a careful reader of this ADR
would do in good faith. The rule above says: charge first, commit immediately,
let the refusal be paid for. Applied to spend, "charge first" means debiting an
estimate before the call — which is the previous alternative, with its
overcharging and its fictional ledger — and "let the refusal be paid for" has no
analogue at all, since no external party charges this system for a call it
declined to make. The deeper error is in the premise. ADR-0015's rule is sound
because the counter is **the system's own record of its own decision**, and the
system is free to decide that a refusal still counts. Money is a record of a
*transaction with someone else*. The system does not get to decide what it cost;
it gets to decide only whether to incur it, and that decision has to be final
before the call rather than recorded after it. Treating the two as one control is
not a shortcut that costs a little precision — it is a category error whose only
two outcomes are the overshoot and the fiction.

**Reconcile lazily from the provider's billing API instead of per call.**
Considered and not adopted, though it is a companion to this design rather than a
rival. Provider billing lags by hours; a ceiling that learns its actuals a day
late cannot refuse anything, so it cannot be the reconciliation step. It is,
however, the right way to **audit** the ledger and to verify A3, and whoever
implements this should expect that comparison to exist even though it is not on
the enforcement path.

## What this amendment does *not* change

Stated plainly, because an amendment attached to a decision is easy to misread as
a reversal, and this one reverses nothing.

* **The counting-quota rule for command routes is untouched in every
  particular.** A command route still charges quota as its first statement, and
  the charge still commits immediately in a transaction of its own.
* **`charge_quota`-first remains the discipline**, at
  `services/api/smartmatch_api/dependencies.py:208`, called as the first
  statement in `services/api/smartmatch_api/routers/redrive.py:372` (re-drive)
  and `:576` (abandon), and in
  `services/api/smartmatch_api/routers/imports.py:228`. `enforce_rate_limit`
  (`dependencies.py:133`) and the guarded `ON CONFLICT` it delegates to are
  unchanged, as is the `QuotaCharge` receipt (`dependencies.py:187`) that
  `submit_command` (`commands.py:87`) requires at line 95.
* **The immediate commit stays** — `dependencies.py:251` — for the reason given
  above: without it, `get_session`'s `finally: session.rollback()`
  (`dependencies.py:74`) discards the increment on exactly the refusal paths this
  ADR exists to charge for.
* **The three deliberately-uncharged classes stay uncharged** — `401`, `422`, and
  reads — with the reasoning above unamended.
* **ADR-0006 is still not amended.** A1 does not touch the counter, its window,
  its key, or its statement. If a spend ledger ends up in PostgreSQL behind a
  guarded conditional write, that is ADR-0006's *shape* being reused, not its
  *decision* being extended.
* **Nothing changes in the running system on ratification.** Ratifying A1 makes it
  binding on unwritten work. It does not make anything true of the system as it
  stands, in which no paid call, no ceiling, and no ledger exists.

## What has to happen before this is in force

1. **A human ratifies A1** — filling the approver field above, changing the ADR's
   `**Status:**` line to record the amendment and its date, and updating the
   `Amended` column of `docs/architecture/decisions/README.md` **in the same
   commit**, which is what
   `tests/unit/test_adr_index.py::test_an_amended_adr_is_marked_amended_in_the_index`
   checks. Until then this section is a draft and the index is correct to show
   none.
2. **A3 is confirmed against the actual provider**, per G3 §4, before any ceiling
   derived from it is enforced.
3. **The reservation ledger, its guarded write, its lease, and its reclaim sweep
   are designed and built** — with tests that reproduce the overshoot against a
   post-hoc implementation *first*, the way ADR-0015's own ordering defect was
   pinned by tests that failed with *"25 denials moved the counter by 0"* before
   the fix existed. A concurrency test with `N` reservers against one ceiling is
   the one that matters most, because it is the case a single-threaded test
   cannot see. Four more that this amendment's own gaps make necessary, each of
   which a plausible implementation fails:
   * **A first reservation against a key with no row, for an estimate larger
     than the ceiling, is refused.** This is the unguarded-insert defect; an
     implementation that copies ADR-0006's statement verbatim admits it.
   * **A reservation that one ceiling admits and another refuses moves no
     ceiling.** The all-or-nothing property of obligation 1, asserted across all
     three rows, including the case where the per-job row does not yet exist.
   * **A redelivery against an `expired_spent` reservation makes no paid call and
     takes no new debit of its own.** The compose-the-two-rules case, and the one
     an implementer otherwise decides by guessing.
   * **A timed-out call leaves the ledger holding the reserved maximum, marked
     estimated.** Not zero, not an actual, and not a second call.
