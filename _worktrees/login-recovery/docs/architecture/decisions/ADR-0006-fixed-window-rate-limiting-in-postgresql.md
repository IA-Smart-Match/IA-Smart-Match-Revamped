# ADR-0006 — Fixed-window rate limiting in PostgreSQL

**Status:** Accepted
**Date:** 18 August 2026
**Contract:** Architecture v1.1 §3.4 (layer 2), §3.5, §3.6 (N4)

## Context

v1.1 §3.4 specifies three layers of protection. Layer 1 is at the edge and layer
3 is budget reservation; layer 2 is a per-caller request limit, and it is the one
the application has to implement itself.

The naive implementation is a dictionary in the process. It is also wrong here,
and wrong in a way that does not announce itself: **the API runs on Cloud Run,
which autoscales.** Each instance would hold its own counter and independently
permit the whole quota, so a limit documented as 30/min becomes 30/min *per
instance* — a number that changes with traffic, is never written down anywhere,
and rises exactly when load is heaviest and the limit matters most. Nothing in
the system would report this. The dashboards would show the limiter working.

The second trap is subtler. Even with a shared store, a limiter written as "read
the count, compare it, write the new count" has a window between the read and the
write in which two requests both observe room and both proceed. Two instances
hitting that window is not an edge case at the point where a limit binds; it is
the normal condition, because that is when requests are arriving fastest.

## Decision

The counter is a **row in PostgreSQL**: `rate_limit_counter`, keyed
`(tenant_id, subject, operation, window_start)` — the whole key is the primary
key, `pk_rate_limit_counter`.

`RateLimiter.check` consumes quota with one statement:

```
INSERT ... VALUES (..., count=1)
ON CONFLICT (pk_rate_limit_counter) DO UPDATE
    SET count = count + 1
    WHERE count < max_requests
RETURNING count
```

The `WHERE` on the `SET` clause is the whole design. When the counter has already
reached the limit, the update matches nothing, `RETURNING` yields no row, and
`row is None` *is* the denial. There is no separate read, so there is no window
between deciding and recording — PostgreSQL serializes the conflicting inserts on
the primary key index and the losing one is denied by the same statement that
would have incremented it.

`check` does not commit. The caller does, usually alongside whatever the request
itself did, so a request that rolls back does not consume quota
(`test_rolled_back_requests_do_not_consume_quota`). The one place this needed
care is worth noting because it inverts the rule: in `submit_command`, a request
rejected for an idempotency conflict commits the quota consumption before the 409
propagates. Otherwise an unbounded stream of conflicting requests would be free —
which is precisely the traffic a limiter exists to bound.

`window_start` is computed from the Unix epoch rather than from first use, so
every instance agrees where a window begins without exchanging a message.

The limiter fails closed. `enforce_rate_limit` lets a database error propagate
rather than catching it into an allow; v1.1 §3.6 (N4) prohibits skipping rate or
budget checks under partial infrastructure failure, and an unavailable limiter
must not become an open door.

## Fixed windows, and what that costs

Each `(tenant, subject, operation)` gets one counter per fixed window. The
imprecision is **boundary bursting**: a caller who spends a full quota at the end
of one window and another at the start of the next briefly achieves twice the
nominal rate. A limit of 30/min permits 60 requests across one particular
straddling minute.

This is accepted knowingly, not overlooked. A sliding window needs a row per
request rather than a row per window, and the storage and vacuum cost of that is
paid continuously to buy precision that nothing here has asked for. v1.1 §3.4
states plainly that the limits themselves are "still hypotheses to be tuned with
recorded evidence" — tuning a hypothesis to sliding-window precision is false
rigor. A doubled burst across a boundary is survivable for every operation
currently limited; a wrong limit value is not made right by measuring it more
finely.

**The adoption trigger for something better — a sliding window, or Redis — is the
same one v1.1 §3.5 gives for Redis generally: measured contention, or throughput
that cannot meet SLO after tuning.** Nothing has been measured. The system is not
deployed, no load test exists, and the expectation that a counter row per
`(subject, operation, window)` is cheap enough at pilot volume is an
*expectation* about scale, not a measurement. If it turns out to be wrong, the
trigger above is what should decide the replacement, not the argument in this
paragraph.

## Consequences

**Good.** The limit means what it says regardless of how many instances are
running — `test_the_counter_is_shared_across_sessions` asserts exactly this,
using two sessions as stand-ins for two instances. Quota is isolated by tenant,
by subject, and by operation, so one noisy caller cannot deny everyone else and
exhausting imports cannot block reads. No Redis, so no second datastore to
provision, secure, and reason about during an incident.

**Cost.** Every limited request performs a database write, on the request path,
before the work it is limiting. That is one more round trip and one more row lock
per request. It is the price of the counter being shared, and the alternative is
the per-instance counter this ADR exists to reject.

**Cost.** Boundary bursting, as above.

**Cost.** `subject` is `TEXT`, not `UUID`, because for unauthenticated endpoints
it holds an IP address and for authenticated ones a user id. Forcing both into a
UUID column would mean encoding an address as a fake identifier, which is worse
than a wide column. The consequence is that the column's contents are only
meaningful in combination with the operation that wrote them.

**Cost, and a growth path that is not yet closed.** The table gains a row per
distinct `(tenant, subject, operation, window)`, and for IP-keyed limits the
subject space is unbounded. A periodic sweep of elapsed windows exists for this,
intended to run from the worker rather than on the request path — a request that
occasionally pays for a bulk delete is a latency outlier nobody can explain. Its
window-awareness has since been corrected; treat the module as the current
description rather than this paragraph. Nothing schedules the sweep yet, so the
retention story is designed but not yet running.

## Alternatives considered

**In-process counters.** Rejected: the autoscaling failure described above, which
is silent and worsens under load.

**Redis.** Deferred, per v1.1 §3.5. It would be a better fit for a sliding window
and for very high request rates, and it buys nothing at all until one of those
applies. Adding it now means a second datastore in the availability path of every
limited request, with its own failure modes, its own secrets, and its own
capacity story — and the limiter fails closed, so a Redis outage becomes an API
outage. PostgreSQL is already in that path and already has to be available for
the request to do anything.

**Read-then-write against the same table.** Rejected: it reintroduces the
check-then-act window that the guarded `ON CONFLICT` closes, and it does so in
the one condition where the limiter is load-bearing.

**Rejecting at the edge only (layer 1).** Rejected as a substitute rather than as
a complement. Cloud Armor cannot see tenant, subject, or operation, so it cannot
express "this user, this command, this many per minute" — which is the limit v1.1
§3.4 layer 2 actually calls for.
