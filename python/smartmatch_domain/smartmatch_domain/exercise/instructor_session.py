"""The instructor passcode and its session token (design spec §14).

Arithmetic over bytes, for :mod:`smartmatch_api.exercise_dependencies` and
``routers/exercise_instructor.py`` to compose. Nothing here reads the
environment, touches a database, or knows what a request is — the same bound
:mod:`smartmatch_domain.exercise.workspace_token` keeps, and for the same
reason: a module that could read the passcode out of the environment is a
module a test cannot pin without one.

What this is, and what it deliberately is not
=============================================

Design spec §14 asks for **one passcode from the environment**, verified with
the PBKDF2-HMAC-SHA256 primitive, and an opaque session minted with
:func:`smartmatch_domain.pilot_credentials.new_session_token`. It explicitly
rules out ``routers/auth.py``'s login, which resolves a ``user_account`` and
mints a principal — ADR-0025 D1/D2 forbid the exercise process either.

So there is no account here, no role, no tenant, and nothing a session can
carry beyond "this browser presented the passcode, and it was still this
deployment's passcode when it did". The instructor is not a *who*; the
passcode is a *door*, and this module is the lock.

PLACEHOLDER (OQ-CE-07) — one environment variable per deployment
================================================================

The register's safe default: ``SMARTMATCH_EXERCISE_INSTRUCTOR_PASSCODE``, one
per deployment, shared out of band, rotated after the spring run. Nothing here
closes that row. If the answer turns out to be per-person passcodes or a
rotation schedule, this module and the settings field are what change.

Why the session is *signed* rather than stored
==============================================

The pilot login stores a row per session and looks a presented token up by its
hash. That is the better design and it is not available here: a session table
is a migration, this track ships none (its whole surface is routes over the
``0037`` tables), and a route mounted against a table that does not exist is
worse than a stateless token that does.

So the cookie is self-describing and signed:

    payload = "<expiry as a whole number of seconds>.<opaque nonce>"
    cookie  = payload + "." + HMAC-SHA256(session key, payload)

The nonce is :func:`~smartmatch_domain.pilot_credentials.new_session_token`,
so two sessions minted in the same second are still different values and a
cookie is never a function of the clock alone. The expiry is *in* the token
because there is no row to carry it; it is covered by the signature, so
editing it invalidates the cookie rather than extending it.

**What the stateless form costs, said plainly.** There is no server-side
revocation: a minted session stays usable until it expires, and "log out"
clears the browser's cookie rather than a row. The two levers that do work are
its short lifetime (:data:`INSTRUCTOR_SESSION_TTL`) and rotating the exercise
secret, which invalidates every live instructor session and every workspace
cookie at once. A server-side store, with the migration it needs, is the
upgrade; it is recorded on this track's pull request rather than smuggled in.

Two keys from one secret, and why they cannot be swapped
========================================================

The deployment has one exercise secret (``SMARTMATCH_EXERCISE_WORKSPACE_SECRET``).
Both the team workspace token and this session are derived from it, so the
derivations are **labelled**: a workspace token is
``HMAC(secret, workspace id)`` and a session signature is
``HMAC(HMAC(secret, "…session-key/v1"), payload)``. Different keys, so a value
minted for one purpose can never verify as the other — which matters here more
than usual, because a team's workspace cookie is handed to every class
participant and the instructor's is the one that must not be.
"""

from __future__ import annotations

import hashlib
import hmac
from datetime import datetime, timedelta
from typing import Final

from smartmatch_domain.pilot_credentials import (
    MINIMUM_PASSWORD_LENGTH,
    derive_password_hash,
    new_session_token,
    verify_password,
)

__all__ = [
    "INSTRUCTOR_SESSION_TTL",
    "MINIMUM_INSTRUCTOR_PASSCODE_LENGTH",
    "instructor_session_is_live",
    "mint_instructor_session",
    "passcode_is_usable",
    "verify_instructor_passcode",
]

#: How long an instructor session stays usable. Twelve hours is
#: :data:`~smartmatch_domain.pilot_credentials.SESSION_TTL`, restated rather
#: than imported so that shortening the *exercise's* session never shortens the
#: pilot login's by accident. It is short because it cannot be revoked: see the
#: module docstring.
INSTRUCTOR_SESSION_TTL: Final[timedelta] = timedelta(hours=12)

#: The shortest passcode this will accept from a deployment. Not a strength
#: policy — the owner supplies the value (OQ-CE-07) — but a floor that refuses
#: an empty or one-character environment variable, which is far more likely to
#: be a misconfiguration than an intention. A deployment below it serves a
#: *closed* door, never an open one.
MINIMUM_INSTRUCTOR_PASSCODE_LENGTH: Final[int] = MINIMUM_PASSWORD_LENGTH

#: Labels that separate the two keys derived from the one exercise secret. See
#: the module docstring. Versioned so a later change to either derivation is a
#: new label rather than a silent reinterpretation of old cookies.
_PASSCODE_SALT_LABEL: Final[bytes] = b"exercise-instructor-passcode-salt/v1"
_SESSION_KEY_LABEL: Final[bytes] = b"exercise-instructor-session-key/v1"

#: What separates the session token's three fields. A full stop, because
#: :func:`~smartmatch_domain.pilot_credentials.new_session_token` is
#: ``secrets.token_urlsafe`` — base64url, whose alphabet is letters, digits,
#: ``-`` and ``_`` — so the nonce cannot contain one and the split is
#: unambiguous without any escaping.
_FIELD_SEPARATOR: Final[str] = "."

#: How many fields a session token has. Named so the parse below reads as a
#: shape check rather than a magic number.
_TOKEN_FIELDS: Final[int] = 3


def _derived_key(*, secret: str, label: bytes) -> bytes:
    """One purpose-separated key from the deployment's exercise secret."""
    return hmac.new(secret.encode("utf-8"), label, hashlib.sha256).digest()


def passcode_is_usable(passcode: str | None) -> bool:
    """Whether a deployment has configured a passcode this module will honour.

    ``False`` for ``None``, for blank, and for anything shorter than
    :data:`MINIMUM_INSTRUCTOR_PASSCODE_LENGTH`. The caller's job on ``False``
    is to *refuse the login* — design spec §14 has one door and an unconfigured
    door is a shut one, never an open one. A deployment that meant to have an
    instructor page and typed the variable wrong finds out by not getting in.
    """
    return passcode is not None and len(passcode.strip()) >= MINIMUM_INSTRUCTOR_PASSCODE_LENGTH


def verify_instructor_passcode(presented: str, *, configured: str, secret: str) -> bool:
    """Whether ``presented`` is this deployment's instructor passcode.

    Design spec §14's "verify with the PBKDF2-HMAC-SHA256 primitive". The
    configured value arrives as plaintext from the environment (OQ-CE-07), so
    there is no stored digest to compare against and one is derived on the spot
    — both sides through
    :func:`~smartmatch_domain.pilot_credentials.derive_password_hash` under the
    *same* salt, which is what makes the comparison meaningful.

    The salt is derived from the deployment secret rather than drawn at random,
    because a random salt per call would make the two digests incomparable and
    a constant salt would be a constant. It is not a per-user salt and does not
    pretend to be one: there is one passcode and one deployment, so what the
    salt buys is that a digest computed here is worthless against any other
    deployment, not protection from a precomputed table over one credential.

    Both derivations run at
    :data:`~smartmatch_domain.pilot_credentials.DEFAULT_ITERATIONS`, which
    costs a fraction of a second per attempt. That is the point on a login
    route, and it is why the rate limiter in front of this one is a second
    bound rather than the only one.

    The comparison is :func:`hmac.compare_digest`, inside
    :func:`~smartmatch_domain.pilot_credentials.verify_password`: an ordinary
    ``==`` returns as soon as it finds a mismatch, which leaks the length of
    the matching prefix to anyone who can time the response.

    Args:
        presented: What the browser sent. Never logged and never echoed.
        configured: The deployment's passcode. Caller has already established
            it is usable with :func:`passcode_is_usable`.
        secret: The deployment's exercise secret, used only as key material.
    """
    stored = derive_password_hash(
        configured, salt=_derived_key(secret=secret, label=_PASSCODE_SALT_LABEL)
    )
    return verify_password(presented, stored)


def _sign(payload: str, *, secret: str) -> str:
    """The signature over a session token's payload."""
    return hmac.new(
        _derived_key(secret=secret, label=_SESSION_KEY_LABEL),
        payload.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def mint_instructor_session(
    *, secret: str, now: datetime, ttl: timedelta = INSTRUCTOR_SESSION_TTL
) -> str:
    """The cookie value for a browser that just presented the passcode.

    Args:
        secret: The deployment's exercise secret.
        now: The caller's clock, passed in rather than read, so a test can mint
            an expired session without sleeping.
        ttl: How long the session lasts.

    Returns:
        ``"<expiry>.<nonce>.<signature>"``. It carries no account, no role and
        no team — there is nothing in it to read but the moment it dies, and
        that is covered by the signature.
    """
    expires_at = int((now + ttl).timestamp())
    payload = f"{expires_at}{_FIELD_SEPARATOR}{new_session_token()}"
    return f"{payload}{_FIELD_SEPARATOR}{_sign(payload, secret=secret)}"


def instructor_session_is_live(token: str, *, secret: str, now: datetime) -> bool:
    """Whether ``token`` is a signature this deployment made and has not outlived.

    Every way of being "no" answers the same way — wrong shape, a nonce with a
    separator smuggled into it, an edited expiry, a signature from another
    deployment, a signature from the *workspace* derivation, or an honest
    session that has run out — so the route in front of this cannot be used to
    tell one from another.

    The signature is checked **before** the expiry is believed, because the
    expiry is a field in an attacker-supplied string until it is.
    """
    fields = token.split(_FIELD_SEPARATOR)
    if len(fields) != _TOKEN_FIELDS:
        return False
    expiry_text, nonce, signature = fields
    payload = f"{expiry_text}{_FIELD_SEPARATOR}{nonce}"
    if not hmac.compare_digest(signature, _sign(payload, secret=secret)):
        return False
    try:
        expires_at = int(expiry_text)
    except ValueError:  # pragma: no cover - a signed payload always parses
        return False
    return now.timestamp() < expires_at
