"""Request-scoped dependencies.

Where the token becomes a principal, and where quota is consumed. Every
consequential route depends on both.

The ordering is deliberate and mirrors architecture v1.1 §3.4: authenticate
first, then apply the limit. An unauthenticated caller cannot be attributed to a
tenant, so limiting before authenticating would either share one bucket across
every anonymous caller (trivially exhausted by one bad actor, denying everyone)
or require a separate IP-keyed scheme. Endpoints that genuinely precede
authentication — login, QR scan — get the IP-keyed limiter explicitly, and edge
throttling (Cloud Armor, layer 1) covers the rest.

## Where the limit sits *after* authentication (ADR-0015)

Authenticate, then charge, then do the work. A command route calls
:func:`charge_quota` as its **first** statement — before it loads the resource,
before it authorizes, before it validates a header or a body — and that call
commits the increment in a transaction of its own, so the quota is durable
whatever the request does next.

Both halves are load-bearing and neither works alone. Charging late made a
``403``, ``404`` or ``400`` free, which is backwards for a limiter whose purpose
is to bound abusive traffic: those are the refusals cheapest to produce in bulk.
Charging early without committing early would have left the increment in the
request's own transaction, where ``get_session``'s unconditional
``finally: session.rollback()`` discards it on exactly those paths.

The cost is charged deliberately and is stated in ADR-0015: an authenticated
caller pays for requests they were never allowed to make, and for ids that do
not exist.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Annotated

from fastapi import Depends, Header, Request, status
from smartmatch_domain.pilot_credentials import hash_session_token
from smartmatch_persistence.pilot_auth import PilotSessionRepository
from smartmatch_persistence.principals import PrincipalRepository, ResolvedPrincipal
from smartmatch_persistence.rate_limit import RateLimit, RateLimiter
from smartmatch_providers import TokenVerificationError, TokenVerifier
from sqlalchemy.orm import Session

from smartmatch_api.errors import ApiError

__all__ = [
    "CurrentPrincipal",
    "DbSession",
    "QuotaCharge",
    "charge_quota",
    "enforce_rate_limit",
    "get_current_principal",
    "get_session",
    "get_token_verifier",
]


def get_session(request: Request) -> Iterator[Session]:
    """Yield a request-scoped database session.

    Rolled back rather than committed on exit. A route that changes state
    commits explicitly; anything that reached here without committing either
    failed or only read, and in both cases rolling back is correct. Committing
    by default would turn a half-finished request into a persisted one.
    """
    session_factory = request.app.state.session_factory
    session = session_factory()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


def get_token_verifier(request: Request) -> TokenVerifier:
    """Return the configured token verifier."""
    verifier: TokenVerifier = request.app.state.token_verifier
    return verifier


def _subject_for_token(session: Session, verifier: TokenVerifier, token: str) -> str | None:
    """The verified subject behind a bearer token, or ``None`` if there is none.

    Two credential kinds reach this API, and both resolve to the *same* kind of
    answer — a bare ``external_subject``:

    1. A **pilot session token** (``POST /v1/auth/login``). Looked up
       server-side by hash in ``pilot_session``, which is what makes it
       unforgeable: the browser holds 32 random bytes that mean nothing except
       that a row names them, and the row names an account rather than a role.
       Checked first because it is the credential a person signing in actually
       holds, and because the fixture verifier below would reject it anyway.
    2. A **token the configured verifier accepts** — today the dev fixture
       mapping (``config.py``'s ``dev_principals``), and eventually a real
       identity provider's. Unchanged by this function's existence.

    That both paths end at a subject is the load-bearing part. Neither returns
    a tenant, a unit, or a role; :meth:`PrincipalRepository.load_by_subject`
    reads those from ``user_account`` and ``membership`` afterwards, so a pilot
    session can no more assert a role than a JWT could.
    """
    subject = PilotSessionRepository().resolve_subject(
        session, token_hash=hash_session_token(token)
    )
    if subject is not None:
        return subject

    try:
        return verifier.verify(token).subject
    except TokenVerificationError:
        return None


def get_current_principal(
    session: Annotated[Session, Depends(get_session)],
    verifier: Annotated[TokenVerifier, Depends(get_token_verifier)],
    authorization: Annotated[str | None, Header()] = None,
) -> ResolvedPrincipal:
    """Resolve the caller from their bearer token.

    Four failure modes, all answered with the same 401 and the same message: no
    token, a token no credential path recognises (an expired or revoked pilot
    session included), and a recognised token with no local account. The
    distinction matters in the log, not in the response — telling a caller that
    their token was fine but they have no account reveals which subjects exist,
    and telling them their session merely *expired* would confirm it had once
    been real.

    A suspended account is *not* rejected here. It resolves normally, carrying
    ``suspended=True``, and policy denies it with a specific reason so the denial
    is auditable as a suspension rather than as a generic absence of permission.

    Raises:
        ApiError: 401 when the caller cannot be identified.
    """
    unauthenticated = ApiError(
        status_code=status.HTTP_401_UNAUTHORIZED,
        code="unauthenticated",
        message="Valid credentials are required.",
        headers={"WWW-Authenticate": "Bearer"},
    )

    if not authorization or not authorization.lower().startswith("bearer "):
        raise unauthenticated

    token = authorization[len("bearer ") :].strip()
    if not token:
        raise unauthenticated

    subject = _subject_for_token(session, verifier, token)
    if subject is None:
        raise unauthenticated

    resolved = PrincipalRepository().load_by_subject(session, external_subject=subject)
    if resolved is None:
        raise unauthenticated

    return resolved


CurrentPrincipal = Annotated[ResolvedPrincipal, Depends(get_current_principal)]
DbSession = Annotated[Session, Depends(get_session)]


def enforce_rate_limit(
    session: Session,
    resolved: ResolvedPrincipal,
    limit: RateLimit,
    *,
    now: datetime | None = None,
) -> None:
    """Consume one unit of quota, or raise 429. **Does not commit.**

    Called from route handlers rather than declared as a dependency, because the
    limit differs per operation and because where the increment commits is a
    decision each route has to make rather than inherit.

    Command routes do not call this directly — they call :func:`charge_quota`,
    which wraps it in a commit (ADR-0015). This one is the raw consumption, kept
    separate because the two rules genuinely differ: a *command* is charged
    before anything else and keeps the charge however the request ends, while a
    limited **read** may still want its increment to share the request's
    transaction, since a read that fails has produced nothing for the caller to
    have gained by. No read is limited today; when one is, it gets this function
    and its own paragraph, not the command rule by default.

    Fails closed by construction: any database error propagates rather than being
    swallowed into an allow. v1.1 §3.6 (N4) prohibits skipping rate checks under
    partial infrastructure failure.

    Raises:
        ApiError: 429 with ``Retry-After`` and the standard rate headers.
    """
    decision = RateLimiter().check(
        session,
        limit=limit,
        tenant_id=resolved.tenant_id,
        subject=str(resolved.user_id),
        now=now or datetime.now(UTC),
    )

    if decision.allowed:
        return

    retry_seconds = max(1, int(decision.retry_after.total_seconds()))
    raise ApiError(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        code="rate_limited",
        message=(f"Rate limit exceeded for {limit.operation!r}. Retry in {retry_seconds} seconds."),
        headers={
            "Retry-After": str(retry_seconds),
            "X-RateLimit-Limit": str(limit.max_requests),
            "X-RateLimit-Remaining": "0",
        },
    )


@dataclass(frozen=True, slots=True)
class QuotaCharge:
    """Proof that a caller was charged for this request before it did anything.

    Returned by :func:`charge_quota` and required by
    :func:`smartmatch_api.commands.submit_command`, so a command cannot be
    accepted by a route that never charged for it. That is the half of ADR-0015
    a type checker can enforce; the other half — that the charge is the route's
    *first* statement, ahead of the load, the authorization and the validators —
    is the router's own discipline, checked by tests that count the counter after
    a run of refusals rather than by a signature.

    Attributes:
        operation: The limited operation the charge was made against, matching
            :attr:`~smartmatch_persistence.rate_limit.RateLimit.operation`. Carried
            so a receipt names the bucket it came out of; two routes sharing one
            bucket (re-drive and abandon) are meant to be visible as such.
    """

    operation: str


def charge_quota(
    session: Session,
    resolved: ResolvedPrincipal,
    limit: RateLimit,
    *,
    now: datetime | None = None,
) -> QuotaCharge:
    """Charge one unit of quota **durably**, before the route does anything else.

    The first statement of every command route, ahead of loading the resource,
    authorizing it, and validating the header and the body. ADR-0015 records the
    decision and what it costs: an authenticated caller pays for requests they
    were never allowed to make, and for ids that do not exist.

    The commit is not an implementation detail of "charge first" — it is the
    other half of it. An increment left in the request's own transaction is
    discarded by ``get_session``'s unconditional ``finally: session.rollback()``
    on every path that raises, which is precisely the ``403``/``404``/``400``
    set this ordering exists to charge for. So the increment gets a transaction
    of its own, which is the shape ``docs/plans/transaction-boundary-defects.md``
    §2.3(c) records as the right long-term one: a rate-limit counter is not part
    of a command's atomic unit, and a command that never happens must not take
    the caller's charge back down with it.

    A denial writes nothing — ``RateLimiter.check``'s guarded ``ON CONFLICT``
    matches no row once the window is spent — so the 429 path has nothing to
    commit and correctly commits nothing.

    Args:
        session: The request session. Committed here, and only here, before the
            handler's own work begins.
        resolved: The authenticated caller. Quota is keyed by their tenant and
            user id, never by anything the request supplied.
        limit: The limit for this operation.
        now: Injected for tests so window rollover is exercised directly.

    Returns:
        A :class:`QuotaCharge` receipt to hand to ``submit_command``.

    Raises:
        ApiError: 429 with ``Retry-After`` and the standard rate headers.
    """
    enforce_rate_limit(session, resolved, limit, now=now)
    session.commit()
    return QuotaCharge(operation=limit.operation)


# Resource-level authorization is deliberately *not* a dependency. It is applied
# inside handlers with `smartmatch_authz.assert_allowed`, because the resource
# being accessed is usually loaded by the handler itself, and a dependency cannot
# authorize a resource it has not fetched. A generic "authorized" dependency
# would let a route look protected without ever naming a resource.
