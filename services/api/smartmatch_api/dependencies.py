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
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Annotated

from fastapi import Depends, Header, Request, status
from smartmatch_persistence.principals import PrincipalRepository, ResolvedPrincipal
from smartmatch_persistence.rate_limit import RateLimit, RateLimiter
from smartmatch_providers import TokenVerificationError, TokenVerifier
from sqlalchemy.orm import Session

from smartmatch_api.errors import ApiError

__all__ = [
    "CurrentPrincipal",
    "DbSession",
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


def get_current_principal(
    session: Annotated[Session, Depends(get_session)],
    verifier: Annotated[TokenVerifier, Depends(get_token_verifier)],
    authorization: Annotated[str | None, Header()] = None,
) -> ResolvedPrincipal:
    """Resolve the caller from their bearer token.

    Three failure modes, all answered with the same 401 and the same message:
    no token, an invalid token, and a valid token with no local account. The
    distinction matters in the log, not in the response — telling a caller that
    their token was fine but they have no account reveals which subjects exist.

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

    try:
        identity = verifier.verify(token)
    except TokenVerificationError as exc:
        raise unauthenticated from exc

    resolved = PrincipalRepository().load_by_subject(session, external_subject=identity.subject)
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
    """Consume one unit of quota, or raise 429.

    Called from route handlers rather than declared as a dependency, because the
    limit differs per operation and the consumption must join the handler's
    transaction — quota spent by a request that then rolls back should not count.

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


# Resource-level authorization is deliberately *not* a dependency. It is applied
# inside handlers with `smartmatch_authz.assert_allowed`, because the resource
# being accessed is usually loaded by the handler itself, and a dependency cannot
# authorize a resource it has not fetched. A generic "authorized" dependency
# would let a route look protected without ever naming a resource.
