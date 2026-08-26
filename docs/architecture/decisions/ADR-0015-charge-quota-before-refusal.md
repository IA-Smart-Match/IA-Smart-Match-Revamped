# ADR-0015 — Charge quota before the route can refuse the request

**Status:** Accepted
**Date:** 25 August 2026
**Contract:** Architecture v1.1 §3.4 (layer 2), §3.6 (N4), §1.6
**Backlog:** J16
**Refines:** ADR-0006, which decides *how* the counter counts. This decides
*when* it is incremented.

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
