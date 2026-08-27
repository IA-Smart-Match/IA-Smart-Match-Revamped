"""Authorization for every operation over a job, in one place.

Four routes act on a job — ``GET /v1/jobs/{id}``, ``GET /v1/jobs/{id}/events``,
``POST /v1/jobs/{id}/redrive`` and ``POST /v1/jobs/{id}/abandon`` — and until A5
they were authorized by two different hand-written functions in two different
routers, each applying a *different subset* of the same policy to the same
resource. The two ways that was wrong are worth naming, because this module
exists to make both unrepresentable rather than merely fixed:

* ``routers/jobs.py::_authorize_job_read`` consulted no ``resource_grant`` at
  all. An administrator who carved one job out of a broad grant was obeyed by
  ``/redrive`` and ``/abandon`` and **ignored** by the status and event routes —
  so the deny stopped the privileged operations and not the read of the same
  job's payloads.
* ``routers/redrive.py::_authorize_redrive`` restated the policy's four rules in
  Python. It got them right, and a second copy of a rule is a rule with two
  places to drift.

Neither could scope to an org unit, because ``job`` had no owning unit to scope
to. That is backlog **A5**, and it is a column rather than a rule: migration
``0006`` adds ``job.owning_unit_id``, ``JobRepository.get`` joins the unit's
``ltree`` path in, and the policy's existing inherited-grant path then does the
work the routers were reimplementing badly.

## The evaluation order, and why it is this order

1. **Suspension.** An administratively suspended account is denied locally and
   immediately, without waiting for the identity provider to revoke a token
   (v1.1 Appendix A, diagram 23).
2. **Tenant mismatch.** Structural, and asserted rather than assumed: the job
   load is tenant-scoped in its query, so this is unreachable today, and the
   check costs one comparison against a failure mode that is cross-tenant
   disclosure.
3. **An explicit deny on this job.** Rule 3 of v1.1 §2.1 — a deny beats
   inheritance, because carving an exception out of a broad grant is what a deny
   is for.
4. **The actor exception**, and only on the two read routes. Whoever submitted
   the work may follow it without being handed oversight of everyone else's.
5. **An inherited unit grant** carrying an oversight role, tested against the
   job's owning unit.
6. **A bare resource allow is not enough** for a role-gated operation (S-007).

Steps 1, 2, 3, 5 and 6 are :func:`smartmatch_authz.evaluate`'s, called rather
than copied — which is what puts them in that order for free and what makes the
five denial reasons the same stable strings the rest of the API already emits.
The actor exception is this module's own, and its position is the load-bearing
detail: it is applied **only** after ``evaluate`` has returned a denial that is
*not* one of the three structural ones. An actor exception evaluated first would
let a suspended account, a cross-tenant caller, or the subject of an explicit
deny read their own job — and the last of those is precisely the hole this
module closes.

## What re-authorization means here

Every request re-runs this. A bounded SSE response closes after
``_MAX_EVENTS_PER_RESPONSE`` events and the client reconnects, and the reconnect
is an ordinary request that loads the job and authorizes it again — so a
membership revoked between two reconnects is honoured on the next one.

**Mid-response revalidation is deliberately not attempted.** A stream that
re-checked permissions while rendering would need the principal reloaded on a
timer inside the generator, which means database work in a response body, a
second transaction whose failure has no way to reach the client as an error, and
a truncated ``text/event-stream`` that a browser treats as a network blip and
retries. The bound on the response is the control: the window is one response
long, and it is closed by the connection ending rather than by watching it.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Final, Protocol
from uuid import UUID

from smartmatch_authz import (
    AccessDecision,
    AuthorizationError,
    OrgPath,
    Resource,
    evaluate,
)
from smartmatch_persistence.principals import ResolvedPrincipal

__all__ = [
    "JOB_OVERSIGHT_ROLES",
    "JOB_RESOURCE_TYPE",
    "AuthorizableJob",
    "authorize_job_command",
    "authorize_job_read",
]

logger = logging.getLogger(__name__)

#: The ``resource_grant.resource_type`` an explicit grant on a job carries. One
#: constant, because an allow written against ``"job"`` and a denial evaluated
#: against ``"jobs"`` would silently never match.
JOB_RESOURCE_TYPE: Final[str] = "job"

#: Roles that may act on a job they did not themselves submit. An explicit set
#: rather than "any active membership": a job's command type and event payloads
#: carry operational detail, re-running failed work can repeat effects that
#: already reached people outside the system, and abandoning removes an item from
#: everyone else's view.
#:
#: One set for all four operations, and that is a decision rather than a
#: convenience. The two constants this replaces — ``_JOB_OVERSIGHT_ROLES`` and
#: ``_REDRIVE_ROLES`` — held equal values in two files, which is the arrangement
#: in which they quietly stop being equal.
JOB_OVERSIGHT_ROLES: Final[frozenset[str]] = frozenset({"admin", "coordinator"})

#: Denials that outrank the actor exception. Each is a statement about the
#: *caller* or the *request* rather than about which grants they hold, so no
#: relationship to the job can answer them: a suspended account is suspended for
#: its own job too, a cross-tenant request is never a policy question, and an
#: explicit deny on this job is aimed at exactly this job.
_STRUCTURAL_DENIALS: Final[frozenset[str]] = frozenset(
    {"principal_suspended", "tenant_mismatch", "explicit_resource_deny"}
)


class AuthorizableJob(Protocol):
    """What authorizing an operation needs off a job row.

    A structural type rather than
    :class:`~smartmatch_persistence.jobs.JobRecord`, so that this module states
    its four inputs instead of depending on the whole record — and so a test can
    build the one shape the routes cannot produce (an absent owning unit path)
    without constructing a record that claims to have been read from the
    database.
    """

    @property
    def id(self) -> UUID: ...

    @property
    def tenant_id(self) -> UUID: ...

    @property
    def actor_id(self) -> UUID | None: ...

    @property
    def owning_unit_path(self) -> str | None: ...


def authorize_job_read(
    principal: ResolvedPrincipal, job: AuthorizableJob, *, at: datetime
) -> AccessDecision:
    """Authorize reading a job's status or its event stream.

    The actor exception applies: the person who submitted the work may follow it
    without holding a role in :data:`JOB_OVERSIGHT_ROLES`. It is still ranked
    below suspension, tenant isolation and an explicit deny — see the module
    docstring for why that ordering is the whole point.

    Both read routes call this one function, which is what stops the stream from
    becoming a way around the status endpoint: there is no second decision for
    the two to disagree about.

    Returns:
        The allowing decision, so a caller can record which path granted access.

    Raises:
        AuthorizationError: on any denial, carrying the policy's own stable
            reason code. Rendered as ``403`` with ``details.reason`` by
            :func:`smartmatch_api.errors.authorization_error_handler`.
    """
    return _decide(
        principal,
        job,
        at=at,
        required_roles=JOB_OVERSIGHT_ROLES,
        actor_may_act=True,
    )


def authorize_job_command(
    principal: ResolvedPrincipal, job: AuthorizableJob, *, at: datetime
) -> AccessDecision:
    """Authorize re-driving or abandoning a job.

    **No actor exception**, and that is the negative that matters most on these
    two routes: having submitted a job is not authority to re-run it or to close
    it permanently. Re-drive and abandon are oversight, not ownership, so they
    require a role in :data:`JOB_OVERSIGHT_ROLES` covering the job's owning unit
    — or an explicit allow, which S-007 says conveys reach and not authority, and
    is therefore refused with its own reason code.

    Returns:
        The allowing decision.

    Raises:
        AuthorizationError: on any denial, with the policy's stable reason code.
    """
    return _decide(
        principal,
        job,
        at=at,
        required_roles=JOB_OVERSIGHT_ROLES,
        actor_may_act=False,
    )


def _decide(
    principal: ResolvedPrincipal,
    job: AuthorizableJob,
    *,
    at: datetime,
    required_roles: frozenset[str],
    actor_may_act: bool,
) -> AccessDecision:
    """Apply the policy, then the actor exception, in that order.

    The ordering is expressed as a *filter on the denial reason* rather than as a
    sequence of ``if`` statements restating the policy's own checks. That is
    deliberate: a re-implementation of "is this principal suspended" here would
    be the second copy this module exists to delete, and it would drift the first
    time the policy gained a rule. Asking ``evaluate`` and then deciding which of
    its denials the actor exception is allowed to override keeps exactly one
    statement of each rule.

    The unusable-path refusal is taken **before** the policy is consulted rather
    than folded into its result, and that position was found by a test rather
    than reasoned to. Returning ``no_grant`` for such a row and letting it flow
    through the ordinary ordering put it on the *overridable* side of the actor
    exception, so a job with no owning unit path was readable by its own actor —
    fail-open on exactly the row that carries no authorization data at all.
    """
    owning_unit_path = _owning_unit_path(job)
    if owning_unit_path is None:
        # Unconditional, and ahead of everything: a row this module cannot ask
        # the policy about is a row nothing may be granted over — no membership,
        # no grant, and no relationship to the job.
        raise AuthorizationError(AccessDecision(allowed=False, reason="no_grant"))

    decision = evaluate(
        principal.principal,
        Resource(
            resource_type=JOB_RESOURCE_TYPE,
            resource_id=str(job.id),
            # The job's own tenant, read off the row, rather than the request's.
            # They agree — the load is tenant-scoped — and taking it from the row
            # is what makes the comparison a check rather than a tautology.
            tenant_id=str(job.tenant_id),
            owning_unit_path=owning_unit_path,
        ),
        at=at,
        required_roles=required_roles,
    )
    if decision.allowed:
        return decision

    if decision.reason in _STRUCTURAL_DENIALS:
        # Nothing about the caller's relationship to this job can answer these.
        raise AuthorizationError(decision)

    if actor_may_act and job.actor_id is not None and job.actor_id == principal.user_id:
        # `is not None` first, and not merely for style: `actor_id` is nullable
        # because system-initiated work records none, and `None == None` would
        # make every such job readable by any authenticated member of the tenant.
        return AccessDecision(allowed=True, reason="job_actor")

    raise AuthorizationError(decision)


def _owning_unit_path(job: AuthorizableJob) -> OrgPath | None:
    """The job's owning unit as a tree path, or ``None`` if the row has no usable one.

    ``owning_unit_path`` is populated by
    :meth:`~smartmatch_persistence.jobs.JobRepository.get`'s tenant-safe join and
    the column behind it is ``NOT NULL``, so neither ``None`` below is reachable
    from the four routes. They exist because the alternative to a denial is an
    exception on an authorization path — a 500 where a 403 belongs — and because
    the fail-*open* version of either is a one-line mistake that no route-level
    test could see.

    Logged at ``error`` rather than ``warning``: reaching here means a record was
    authorized that did not come from a tenant-scoped read, or that a unit path
    in the database is not a path. Both are defects in the system rather than in
    the request, and neither is something the caller can act on.
    """
    raw_path = job.owning_unit_path
    if raw_path is None:
        logger.error(
            "job %s was authorized without an owning unit path; the record did not "
            "come from a tenant-scoped read. Denying.",
            job.id,
        )
        return None

    try:
        return OrgPath.parse(raw_path)
    except ValueError:
        logger.error(
            "job %s carries an owning unit path the org tree cannot parse (%r). Denying.",
            job.id,
            raw_path,
        )
        return None
