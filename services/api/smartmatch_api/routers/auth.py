"""The pilot login: exchange a credential for a session, and end that session.

``POST /v1/auth/login`` and ``POST /v1/auth/logout``. Both exist because the
project owner authorized, on 2026-09-04, a **pilot-scoped** login backed by
credentials they supply, as a stand-in for institutional sign-in while A1b
stays blocked. ``docs/decisions/pilot-login-decision-2026-09-04.md`` is the
record; it also states what must happen before any of this may be used for
anything real, and this module makes no production-readiness claim.

What this is **not**:

* It is not A1b, and it does not unblock it. The JWKS verifier core stays
  unwired, ``docs/decisions/a1b-idp-configuration-worksheet.md`` stays
  unfilled, and no issuer, audience, JWKS URI, or client id is invented here
  or anywhere else in this change.
* It is not ``POST /auth/mock-login``, archived as MM-A01 and named in
  :mod:`smartmatch_api.main` as "the single most dangerous pattern in the
  legacy baseline". That route let the caller *choose an identity*. This one
  requires a secret only the account holder has, and still resolves who that
  account is — and every role it holds — from the database.

## The property this module exists to preserve

    **The request supplies a credential. It never supplies a role, a tenant,
    or a unit.**

:class:`LoginRequest` has exactly two fields and forbids every other one, so a
body carrying ``role``, ``tenant_id``, or ``unit_path`` is **rejected** with a
422 rather than accepted-and-ignored. Rejecting is the stronger of the two
readings the requirement allows, and it is the one that stays true under
future edits: an ignored field is one careless ``model_config`` change away
from being an honoured one, whereas a forbidden field has to be deliberately
permitted before it can mean anything.

Nothing downstream could use such a field anyway.
:func:`login` resolves an account, mints an opaque token, and stores a row
naming the account. The token carries no claims at all — it is 32 bytes of
randomness — and :func:`~smartmatch_api.dependencies.get_current_principal`
turns it back into a principal by looking the *subject* up and reading
``membership``, which is the same path a verified identity-provider token
would take. There is no representation of a role anywhere between the form
and the policy.

## Why every failure looks the same

A wrong password, an unknown address, an address held by two accounts, and an
account with no pilot credential all produce one 401 with one message and one
code. Telling them apart would make this route an account-existence oracle:
"no such user" is exactly the answer a list of harvested addresses is being
checked against.

A **suspended** account is the one deliberate exception, and it is not an
exception to the rule above — a suspended caller has already proved they hold
the credential, so naming their suspension reveals nothing they did not
already know, and refusing them with the generic message would send them
hunting for a typo in a password that is correct. This is the same reasoning
``GET /v1/me`` gives for admitting a suspended caller so it can learn that it
is suspended.

## Quota, and where it is charged (ADR-0015)

:func:`login` charges :data:`LOGIN_RATE_LIMIT` as its **first statement**, and
commits that charge in a transaction of its own, before it looks at the email
at all. That ordering is what stops this route being a free brute-force
oracle: a caller pays for the attempt whether the address exists, whether the
password is right, and whether the account is suspended.

The charge is keyed on the client address rather than on ``(tenant,
subject)``, because a caller who has not authenticated has neither — see
:class:`~smartmatch_persistence.pilot_auth.LoginAttemptLimiter` and migration
``0020`` for why that needs its own counter rather than a relaxation of the
shared one. ``dependencies.py``'s own docstring anticipated exactly this
("endpoints that genuinely precede authentication — login, QR scan — get the
IP-keyed limiter explicitly").

One honest gap, stated rather than glossed: a body that fails
:class:`LoginRequest`'s own validation is answered with a 422 by FastAPI
before this handler runs, so it is **not** charged. That is acceptable
precisely because such a request cannot be a credential guess — it did not
carry a well-formed email and password to guess with — and closing it would
mean parsing the body by hand and giving up the generated contract for it.

``POST /v1/auth/logout`` is not charged. It requires a live session to do
anything at all, so it cannot be used to probe for one, and a caller who is
already authenticated is bounded by the credential they hold rather than by a
counter.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Annotated, Final

from fastapi import APIRouter, Header, Request, status
from pydantic import BaseModel, ConfigDict, Field
from smartmatch_domain.pilot_credentials import (
    SESSION_TTL,
    hash_session_token,
    new_session_token,
    verify_password,
)
from smartmatch_persistence.pilot_auth import (
    LoginAttemptLimiter,
    PilotCredentialRepository,
    PilotSessionRepository,
)
from smartmatch_persistence.rate_limit import RateLimit
from sqlalchemy.orm import Session

from smartmatch_api.dependencies import CurrentPrincipal, DbSession
from smartmatch_api.errors import ApiError
from smartmatch_api.utils import utc_now

router = APIRouter(prefix="/v1/auth", tags=["identity"])

#: v1.1 §3.4's pilot limits are hypotheses to tune with recorded evidence, and
#: this is one of them. Tighter than any authenticated command route because
#: the population it bounds is different: an unauthenticated caller repeating
#: this route is, by construction, either a person who mistyped a password or
#: somebody guessing one.
LOGIN_RATE_LIMIT: Final[RateLimit] = RateLimit(
    operation="auth.login",
    max_requests=10,
    window=timedelta(minutes=5),
)

#: The bucket a request with no resolvable client address is charged against.
#: Such callers share one counter, which is the conservative direction: it can
#: refuse more than strictly necessary, never less. A per-request unique key
#: would be the opposite — every attempt its own fresh quota, which is no
#: limit at all.
_UNRESOLVED_CALLER_KEY: Final[str] = "client-address-unavailable"

#: One message for every way a login can fail that is not a suspension. See
#: the module docstring: the differences are real and are deliberately not
#: reported.
_REJECTED_MESSAGE: Final[str] = "Those sign-in details were not accepted."


class LoginRequest(BaseModel):
    """A pilot sign-in attempt: an address and a password, and nothing else.

    ``extra="forbid"`` is the load-bearing line. A body carrying ``role``,
    ``tenant_id``, ``unit_path``, or any other field is refused with a 422 —
    not silently dropped — so the browser cannot even *attempt* to assert what
    it is allowed to do. Roles come from ``membership`` rows an administrator
    wrote; see the module docstring and ``routers/me.py``.
    """

    model_config = ConfigDict(extra="forbid")

    email: str = Field(
        min_length=3,
        max_length=320,
        description="The address the pilot account was created with. Matched case-insensitively.",
    )
    #: Bounded above because a password is hashed with a deliberately slow KDF:
    #: an unbounded string would let one request buy an arbitrary amount of
    #: server work. Bounded below at 1 only — the *storage* floor lives in the
    #: seed (``MINIMUM_PASSWORD_LENGTH``), because a login must not tell a
    #: caller that their guess was too short to be anybody's password.
    password: str = Field(
        min_length=1,
        max_length=1024,
        description="The password the owner supplied for this pilot account.",
    )


class LoginResponse(BaseModel):
    """An issued pilot session.

    Carries a token and when it dies. It deliberately carries **no** identity:
    not the user id, not the tenant, not a role. A client that wants to know
    who it is calls ``GET /v1/me``, which is the single source of the
    principal — duplicating any of it here would create a second answer to
    "who am I" that could disagree with the first.
    """

    access_token: str = Field(
        description=(
            "An opaque session token. It encodes nothing and is not a JWT — the "
            "server stores only a hash of it and resolves the account by lookup. "
            "Send it as `Authorization: Bearer <token>`."
        )
    )
    token_type: str = Field(description="Always `bearer`.")
    expires_at: str = Field(description="ISO-8601 instant after which this session is refused.")


class LogoutResponse(BaseModel):
    """The outcome of ending a session."""

    ended: bool = Field(
        description=(
            "Whether this request is what withdrew the session. `false` means the "
            "token named nothing live — already ended, already expired, or never a "
            "session — which is not an error: the requested end state holds either way."
        )
    )


def _caller_key(request: Request) -> str:
    """The address a pre-authentication attempt is charged against."""
    client = request.client
    if client is None or not client.host:
        return _UNRESOLVED_CALLER_KEY
    return client.host


def _bearer_token(authorization: str | None) -> str | None:
    """The token out of an ``Authorization`` header, or ``None``.

    Shares its parsing rules with
    :func:`~smartmatch_api.dependencies.get_current_principal` rather than
    inventing looser ones: the header this route revokes is the same header
    that route authenticated with, and two different readings of it would mean
    a token could authenticate a log-out and then not be the token that got
    revoked.
    """
    if not authorization or not authorization.lower().startswith("bearer "):
        return None
    token = authorization[len("bearer ") :].strip()
    return token or None


def _charge_login_attempt(request: Request, session: Session) -> None:
    """Charge one login attempt to the caller's address, durably.

    Committed here, and only here, before the handler's own work begins —
    ADR-0015's shape, for the reason that docstring gives: an increment left in
    the request's own transaction is discarded by ``get_session``'s
    unconditional ``finally: session.rollback()`` on exactly the paths this
    ordering exists to charge for, which here is *every* failed sign-in.

    A denial writes nothing — the guarded ``ON CONFLICT`` matches no row once
    the window is spent — so the 429 path correctly commits nothing.

    Raises:
        ApiError: 429 with ``Retry-After`` and the standard rate headers.
    """
    decision = LoginAttemptLimiter().check(
        session,
        limit=LOGIN_RATE_LIMIT,
        caller_key=_caller_key(request),
        now=utc_now(),
    )

    if not decision.allowed:
        retry_seconds = max(1, int(decision.retry_after.total_seconds()))
        raise ApiError(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            code="rate_limited",
            message=f"Too many sign-in attempts. Retry in {retry_seconds} seconds.",
            headers={
                "Retry-After": str(retry_seconds),
                "X-RateLimit-Limit": str(LOGIN_RATE_LIMIT.max_requests),
                "X-RateLimit-Remaining": "0",
            },
        )

    session.commit()


@router.post(
    "/login",
    response_model=LoginResponse,
    status_code=status.HTTP_200_OK,
    summary="Exchange pilot credentials for a session",
)
def login(request: Request, session: DbSession, payload: LoginRequest) -> LoginResponse:
    """Verify a pilot credential and issue an opaque server-side session.

    The first statement charges quota and commits it, before the address is
    read (ADR-0015, and the module docstring for why this route needs the
    ordering more than most). Everything after that is: find the one
    credentialed account for the address, re-derive the password against the
    parameters that account's row was written with, and — only then — mint a
    token whose hash is stored beside the account id.

    Raises:
        ApiError: 429 when the caller's login quota is spent; 401 for every
            failure that is not a suspension; 403 for a suspended account.
    """
    _charge_login_attempt(request, session)

    account = PilotCredentialRepository().load_by_email(session, email=payload.email)

    # A denial is a denial whether the row was missing, ambiguous, or simply
    # did not match. `verify_password` is still run against a real stored
    # password when one exists, and skipped when none does; that difference is
    # a timing signal this pilot accepts and the decision record names, because
    # removing it means deriving a key against a manufactured credential, and a
    # fabricated row is a worse thing to have in the code than a measurable
    # difference in how fast a 401 comes back.
    if account is None or not verify_password(payload.password, account.password):
        raise ApiError(
            status_code=status.HTTP_401_UNAUTHORIZED,
            code="invalid_credentials",
            message=_REJECTED_MESSAGE,
            headers={"WWW-Authenticate": "Bearer"},
        )

    if account.suspended:
        # Named, unlike every other failure. The caller has already proved they
        # hold this credential, so this tells them nothing they did not know,
        # and the generic message would send them looking for a typo in a
        # password that is correct.
        raise ApiError(
            status_code=status.HTTP_403_FORBIDDEN,
            code="principal_suspended",
            message=(
                "This account is suspended. Its credentials are correct; an "
                "administrator has withdrawn its access."
            ),
        )

    issued_at = utc_now()
    expires_at = issued_at + SESSION_TTL
    token = new_session_token()

    PilotSessionRepository().issue(
        session,
        tenant_id=account.tenant_id,
        user_id=account.user_id,
        token_hash=hash_session_token(token),
        issued_at=issued_at,
        expires_at=expires_at,
    )
    session.commit()

    return LoginResponse(access_token=token, token_type="bearer", expires_at=expires_at.isoformat())


@router.post(
    "/logout",
    response_model=LogoutResponse,
    status_code=status.HTTP_200_OK,
    summary="End the caller's own pilot session",
)
def logout(
    principal: CurrentPrincipal,
    session: DbSession,
    authorization: Annotated[str | None, Header()] = None,
) -> LogoutResponse:
    """Revoke the session this request authenticated with.

    ``principal`` is required rather than decorative: it is what makes this
    route able to revoke *only the caller's own* session. The token is looked
    up by hash and withdrawn, so there is no path here to end somebody else's
    session — a caller cannot name one, because the only token they can send
    is the one that authenticated them.

    A caller authenticated by the dev fixture verifier rather than by a pilot
    session reaches this route successfully and is told ``ended: false``, which
    is the truth: that credential is a configured mapping with no expiry and no
    revocation (``config.py``'s ``dev_principals``), and nothing here can
    withdraw it. Reporting success would be the fake-success shape (v1.1 §3.6
    N2); reporting an error would be wrong too, since the caller did nothing
    invalid.
    """
    # `principal` is deliberately unread beyond the dependency's own
    # resolution: its job is to make this route authenticated, and the
    # revocation is keyed by the presented token rather than by the account, so
    # that one session is ended and not *all* of an account's sessions.
    del principal

    token = _bearer_token(authorization)
    if token is None:
        # Unreachable through `get_current_principal`, which raises 401 without
        # a bearer header — stated rather than assumed, so a future change to
        # that dependency cannot silently turn this into an unrevoked logout
        # that still answers `ended: true`.
        return LogoutResponse(ended=False)

    ended = PilotSessionRepository().revoke(session, token_hash=hash_session_token(token))
    session.commit()

    return LogoutResponse(ended=ended)
