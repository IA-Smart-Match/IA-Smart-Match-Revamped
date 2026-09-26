"""The instructor's door: present the passcode, clear the cookie.

The two routes that must answer **before** there is a session, as a module of
its own rather than as the first section of ``routers/exercise_instructor.py``.
That file was past this repository's 800-line ceiling, and this is the cut it
already had: everything left there is about the data file and the teams in it
and runs *inside* a session; these two are about getting one and giving it
back. Nothing about either route changed in the move — same paths, same status
codes, same response model, same cookie, same limiter, same sentences.

The precedent is ``routers/exercise_instructor_refresh.py``, which took the
same cut for the same reason (design spec §14, ADR-0025 D1/D2/D6/D8).

Why the gate is *absent* here, and why that is structural
=========================================================

:data:`router` is a **bare** ``APIRouter`` with no router-level dependency,
because a login that required a session could never be reached and a logout
that required one would refuse the person pressing "sign out" with an expired
cookie. Every *other* instructor router — ``exercise_instructor.router`` and
``exercise_instructor_refresh.router`` — takes
:func:`~smartmatch_api.exercise_dependencies.require_instructor_session` as a
router-level dependency.

Splitting the ungated pair into a file of their own makes that arrangement
harder to undo by accident than the two-routers-in-one-module version was: a
route added to any instructor module is gated unless it is added *here*, and
adding it here is a deliberate act in a file whose whole subject is the
unauthenticated door. ``tests/unit/test_exercise_instructor_router.py`` walks
the mounted route table and asserts that these two paths, and only these two,
answer without a session.

Both routers are bare module-level assignments, for ``exercise_public.router``'s
reason: the route ledger in ``tests/authz/test_policy_matrix.py`` reads router
prefixes out of the AST and matches ``name = APIRouter(...)``. The prefix is
written out as a literal rather than hoisted into a shared constant for the same
reason — the ledger only sees ``prefix="…"``.

What a response may carry
=========================

Nothing here reads the withheld column, reports a score (ADR-0025 D6/D8), or
puts a workspace id, token, hash or seed on the wire: the only response is
:class:`~smartmatch_api.routers.exercise_instructor_models.InstructorSessionView`,
which is one boolean. The session token leaves only as a cookie.

Rate limiting and CSRF
======================

The login route is bounded by :mod:`smartmatch_api.exercise_rate_limit` — a
**PLACEHOLDER (OQ-CE-06)**, in-process and per worker, because the repository's
real limiter needs a principal or ``smartmatch_persistence`` and an exercise
router may import neither. There is one limiter instance and it is this
module's, so the counters are this process's — which is the whole of what the
limiter claims to be. Both routes require ``X-Exercise-Request``, as the team
routes do: they are cookie-addressed POSTs with no login behind them, which is
exactly the shape a cross-site form forges.
"""

from __future__ import annotations

import logging
from typing import Final

from fastapi import APIRouter, Depends, Request, Response, status
from smartmatch_domain.exercise.instructor_session import (
    mint_instructor_session,
    spend_a_verification,
    verify_instructor_passcode,
)

from smartmatch_api.exercise_dependencies import (
    InstructorCookiePolicy,
    InstructorPasscode,
    WorkspaceSecret,
    require_exercise_request_header,
)
from smartmatch_api.exercise_errors import ExerciseError
from smartmatch_api.exercise_rate_limit import (
    INSTRUCTOR_LOGIN_ATTEMPTS_PER_CLIENT,
    INSTRUCTOR_LOGIN_ATTEMPTS_TOTAL,
    INSTRUCTOR_LOGIN_WINDOW,
    UNRESOLVED_CALLER_KEY,
    FixedWindowLimiter,
)
from smartmatch_api.routers.exercise_instructor_models import (
    InstructorLoginRequest,
    InstructorSessionView,
)
from smartmatch_api.utils import utc_now

_LOGGER = logging.getLogger(__name__)

#: Applied to both routes here, and declared once so they cannot drift.
_STATE_CHANGING = [Depends(require_exercise_request_header)]

#: The two routes that must answer before there is a session, and therefore the
#: one instructor router with no ``require_instructor_session`` on it.
router = APIRouter(prefix="/v1/exercise/instructor", tags=["class-exercise"])

#: PLACEHOLDER (OQ-CE-06, owner Danny). Module-level because the counters are
#: this process's, which is the whole of what this limiter claims to be. See
#: :mod:`smartmatch_api.exercise_rate_limit`.
_LOGIN_LIMITER: Final[FixedWindowLimiter] = FixedWindowLimiter(
    per_key=INSTRUCTOR_LOGIN_ATTEMPTS_PER_CLIENT,
    total=INSTRUCTOR_LOGIN_ATTEMPTS_TOTAL,
    window=INSTRUCTOR_LOGIN_WINDOW,
)

#: One message for every way a login can fail that is not a rate limit. The
#: differences are real — an unconfigured passcode, a blank one, a wrong one —
#: and are deliberately not reported, so the response cannot be used to learn
#: whether this deployment has an instructor page at all.
_LOGIN_REFUSED: Final[str] = "That passcode was not recognised."


def _client_key(request: Request) -> str:
    """The rate-limit bucket this request is charged against."""
    client = request.client
    return client.host if client and client.host else UNRESOLVED_CALLER_KEY


@router.post(
    "/login",
    response_model=InstructorSessionView,
    status_code=status.HTTP_200_OK,
    dependencies=_STATE_CHANGING,
    summary="Present the instructor passcode",
)
def instructor_login(
    payload: InstructorLoginRequest,
    request: Request,
    response: Response,
    passcode: InstructorPasscode,
    secret: WorkspaceSecret,
    policy: InstructorCookiePolicy,
) -> InstructorSessionView:
    """Design spec §14's one door.

    **The two bounds are not the same bound** (see
    :class:`~smartmatch_api.exercise_rate_limit.Allowance`).

    * The **per-key** bound is the caller's own budget and is charged first. If
      it is spent, this refuses without looking at the passcode at all: no key
      derivation, no global budget consumed. The earlier version charged the
      global window first, so fifty attempts a caller's own key had already
      refused still spent fifty units of everybody else's allowance — one
      script could lock the real instructor out for a lesson.
    * The **global** bound is the one an attacker can exhaust on somebody
      else's behalf, so it may not be the reason a *correct* passcode is
      refused. When it is spent the passcode is still checked and a correct one
      is let in and **refunds the unit it spent** — none, if the window was
      already full. The window is left holding only the wrong attempts.

    **Fail closed, and at the same cost.** A deployment with no usable passcode
    reaches the same refusal as a wrong one *and pays the same key derivation*
    to get there — see
    :func:`~smartmatch_domain.exercise.instructor_session.spend_a_verification`.
    Returning early would have answered "is there an instructor page on this
    host?" to anyone with a stopwatch. The response cannot tell the cases apart;
    the server log records which, because an operator who mistyped the variable
    has to be able to find out.

    Raises:
        ExerciseError: 429 when this caller's attempts are spent or a wrong
            passcode arrives on a spent global window, 401 when the passcode is
            not this deployment's, 403 when the request carries no
            ``X-Exercise-Request`` header.
    """
    allowance = _LOGIN_LIMITER.charge(_client_key(request), now=utc_now())
    if not allowance.key_allows:
        _LOGGER.warning("exercise instructor login rate limited: this caller's attempts are spent")
        raise _too_many_attempts()

    if passcode.value is None:
        # The same work a real verification costs, discarded. Not an early
        # return: that is the timing oracle this branch used to be.
        spend_a_verification(payload.passcode, secret=secret)
        _LOGGER.error(
            "exercise instructor login refused: no usable "
            "SMARTMATCH_EXERCISE_INSTRUCTOR_PASSCODE is configured (OQ-CE-07)"
        )
        raise _passcode_refused()

    if not verify_instructor_passcode(payload.passcode, configured=passcode.value, secret=secret):
        _LOGGER.warning("exercise instructor login refused: passcode did not match")
        if not allowance.global_allows:
            raise _too_many_attempts()
        raise _passcode_refused()

    # Correct. The global window never holds a unit for an attempt that was
    # right, so a flood from many addresses cannot lock the passcode holder out.
    #
    # Guarded on this attempt having actually spent a global unit (F3, PR
    # #184): a false ``global_allows`` means ``charge`` spent nothing, so an
    # unconditional refund minted budget out of somebody else's wrong attempt.
    if allowance.global_allows:
        _LOGIN_LIMITER.refund_global()
    _set_instructor_cookie(
        response, policy=policy, token=mint_instructor_session(secret=secret, now=utc_now())
    )
    _LOGGER.info("exercise instructor signed in")
    return InstructorSessionView(signed_in=True)


def _too_many_attempts() -> ExerciseError:
    """One sentence for both ways of running out of attempts."""
    return ExerciseError(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        code="exercise_instructor_login_rate_limited",
        message="Too many passcode attempts. Please wait a few minutes and try again.",
    )


def _passcode_refused() -> ExerciseError:
    """One sentence for every way a passcode can be wrong. See :data:`_LOGIN_REFUSED`."""
    return ExerciseError(
        status_code=status.HTTP_401_UNAUTHORIZED,
        code="exercise_instructor_passcode_refused",
        message=_LOGIN_REFUSED,
    )


@router.post(
    "/logout",
    response_model=InstructorSessionView,
    status_code=status.HTTP_200_OK,
    dependencies=_STATE_CHANGING,
    summary="Clear the instructor session cookie",
)
def instructor_logout(
    response: Response,
    policy: InstructorCookiePolicy,
) -> InstructorSessionView:
    """Drop this browser's session cookie.

    Takes no session of its own — a request with an expired or absent cookie
    still gets its cookie cleared, which is what a person pressing "sign out"
    means, and refusing them would be a refusal with nothing behind it.

    **What this does not do, said plainly:** the session is a signed value with
    no server-side row (see
    :mod:`smartmatch_domain.exercise.instructor_session`), so this clears the
    *browser's* copy and does not revoke anything. A token already captured
    stays usable until it expires. The levers that do revoke are the twelve-hour
    lifetime and rotating the exercise secret; a server-side store, with the
    migration it needs, is recorded on this track's pull request.
    """
    response.delete_cookie(
        key=policy.name,
        path=policy.path,
        httponly=policy.http_only,
        samesite=policy.same_site,
        secure=policy.secure,
    )
    return InstructorSessionView(signed_in=False)


def _set_instructor_cookie(
    response: Response, *, policy: InstructorCookiePolicy, token: str
) -> None:
    """Point this browser at a live session.

    A session cookie — no ``max_age`` and no ``expires`` — so it dies with the
    browser as well as with its own signed expiry. The two are independent and
    both are short on purpose.
    """
    response.set_cookie(
        key=policy.name,
        value=token,
        path=policy.path,
        httponly=policy.http_only,
        samesite=policy.same_site,
        secure=policy.secure,
    )
