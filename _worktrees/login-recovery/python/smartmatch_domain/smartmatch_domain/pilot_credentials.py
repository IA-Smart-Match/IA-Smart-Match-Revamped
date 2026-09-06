"""Password and session-token primitives for the **pilot** login.

Scope, stated first because it bounds everything below: this module exists to
support an owner-authorized, pilot-scoped substitute for institutional
sign-in (``docs/decisions/pilot-login-decision-2026-09-04.md``). It is not
production authentication, it does not implement or unblock A1b, and the JWKS
verifier core in :mod:`smartmatch_providers.jwks` stays unwired by it.

## What this module is, and what it deliberately is not

It is arithmetic over bytes: derive a key from a password and a salt, compare
two digests without leaking where they first differ, and mint an opaque
random token. Nothing here reads the environment, touches a database, or
knows what a role is — which is what lets the policy statements the rest of
the system depends on stay true:

* **A credential proves *who*, never *what*.** No function here accepts,
  returns, or stores a role, tenant, or unit. Authentication resolves an
  account; authorization still reads ``membership`` rows through
  :mod:`smartmatch_persistence.principals` and
  :mod:`smartmatch_authz.policy`. A login that could carry a role would undo
  the removal of caller-selected identity (MM-A01, stakeholder Fix #7).
* **A session token carries no claims.** :func:`new_session_token` returns
  random bytes rendered as text and nothing else — it is a *lookup key* for a
  server-side row, not a bearer of assertions. There is nothing in it to
  forge, because there is nothing in it to read.

## Why PBKDF2-HMAC-SHA256 and not something else

It is a standard password-based KDF, it is in the standard library
(:func:`hashlib.pbkdf2_hmac`), and it therefore adds no dependency and forces
no regeneration of the hash-pinned requirement locks. A memory-hard KDF
(scrypt, Argon2) would be a better choice for a production credential store
and is named as such in the decision record; adopting one is part of standing
up real authentication, not part of a pilot substitute that is meant to be
switched off.

Nothing here is a hand-rolled construction. The one composition this module
performs is "run the library's KDF with a per-user random salt and a recorded
iteration count", and both the salt and the count are stored beside the
digest so a stored credential can always be re-derived and so the count can
be raised later without invalidating anything.

## Unknown is never a default (ADR-0011)

:func:`verify_password` takes the *stored* parameters rather than assuming
them. A credential row whose algorithm this module does not recognise is
refused by :func:`verify_password` returning ``False`` — never re-derived
under today's defaults and compared anyway, which would silently accept a row
written by a scheme nobody has read.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
from dataclasses import dataclass
from datetime import timedelta
from typing import Final

__all__ = [
    "DEFAULT_ITERATIONS",
    "MINIMUM_ITERATIONS",
    "MINIMUM_PASSWORD_LENGTH",
    "PBKDF2_SHA256",
    "SALT_BYTES",
    "SESSION_TOKEN_BYTES",
    "SESSION_TTL",
    "StoredPassword",
    "derive_password_hash",
    "hash_session_token",
    "new_salt",
    "new_session_token",
    "verify_password",
]

#: The one algorithm identifier this module writes. Stored as a column on
#: every credential row rather than assumed, so a future scheme can be added
#: beside it and an unrecognised row can be refused rather than misread.
PBKDF2_SHA256: Final[str] = "pbkdf2_hmac_sha256"

#: Iterations used for credentials written today. Recorded per row, so raising
#: this number does not invalidate existing rows — they keep verifying under
#: the count they were written with, and are rewritten with the new one the
#: next time the seed runs.
DEFAULT_ITERATIONS: Final[int] = 600_000

#: The lowest iteration count a stored row may claim and still be used. A row
#: carrying a trivially small count is not a weak credential to be accepted
#: with a shrug; it is a row nobody should have been able to write, and
#: verifying against it would make the count decorative.
MINIMUM_ITERATIONS: Final[int] = 100_000

#: Per-user random salt width. 16 bytes is the width the stored CHECK
#: constraint enforces (migration ``0020``), so the two cannot drift.
SALT_BYTES: Final[int] = 16

#: Opaque session-token width. 32 bytes of ``secrets`` randomness; the token is
#: a lookup key with no structure, so its only security property is that it
#: cannot be guessed.
SESSION_TOKEN_BYTES: Final[int] = 32

#: How long a pilot session stays usable. Short enough that an abandoned
#: browser stops being a way in, long enough for a demonstration session.
#: Expiry is stored on the row and checked server-side; the token itself says
#: nothing about when it dies.
SESSION_TTL: Final[timedelta] = timedelta(hours=12)

#: The shortest password the seed will store. Not a strength policy — the
#: owner supplies the values — but a floor that refuses an empty or one-
#: character environment variable, which is far more likely to be a
#: misconfiguration than an intention.
MINIMUM_PASSWORD_LENGTH: Final[int] = 12


@dataclass(frozen=True, slots=True)
class StoredPassword:
    """A stored credential, exactly as the ``pilot_credential`` row holds it.

    Attributes:
        algorithm: The KDF identifier the digest was produced with. Compared,
            not assumed — see the module docstring.
        iterations: The iteration count that row was written with.
        salt: The per-user random salt.
        digest: The derived key.
    """

    algorithm: str
    iterations: int
    salt: bytes
    digest: bytes


def new_salt() -> bytes:
    """Return a fresh per-user salt.

    Generated at call time from :mod:`secrets`. No salt is ever a constant, a
    literal, or derived from the account — a salt that can be predicted from
    the email is a salt that does not stop a precomputed table.
    """
    return secrets.token_bytes(SALT_BYTES)


def derive_password_hash(
    password: str, *, salt: bytes, iterations: int = DEFAULT_ITERATIONS
) -> StoredPassword:
    """Derive the stored form of ``password``.

    Args:
        password: The plaintext, held only for the duration of this call. It
            is never stored, logged, or returned.
        salt: A per-user salt, normally from :func:`new_salt`.
        iterations: The count to record on the row.

    Returns:
        The :class:`StoredPassword` to persist, carrying the parameters needed
        to re-derive it.

    Raises:
        ValueError: on a salt narrower than :data:`SALT_BYTES` or an iteration
            count below :data:`MINIMUM_ITERATIONS`. Both are refusals to write
            a row that would later have to be verified under parameters this
            module considers unusable.
    """
    if len(salt) < SALT_BYTES:
        raise ValueError(f"salt must be at least {SALT_BYTES} bytes")
    if iterations < MINIMUM_ITERATIONS:
        raise ValueError(f"iterations must be at least {MINIMUM_ITERATIONS}")

    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return StoredPassword(algorithm=PBKDF2_SHA256, iterations=iterations, salt=salt, digest=digest)


def verify_password(password: str, stored: StoredPassword) -> bool:
    """Whether ``password`` re-derives ``stored``'s digest.

    The comparison is :func:`hmac.compare_digest`, which takes the same time
    whichever byte first differs. An ordinary ``==`` on bytes returns as soon
    as it finds a mismatch, which leaks the length of the matching prefix to
    anyone who can time the response.

    An unrecognised algorithm or an iteration count below
    :data:`MINIMUM_ITERATIONS` returns ``False`` rather than raising: a caller
    on the login path must not be able to tell a malformed row from a wrong
    password, and the two outcomes are the same denial.
    """
    if stored.algorithm != PBKDF2_SHA256:
        return False
    if stored.iterations < MINIMUM_ITERATIONS:
        return False
    if len(stored.salt) < SALT_BYTES:
        return False

    candidate = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), stored.salt, stored.iterations
    )
    return hmac.compare_digest(candidate, stored.digest)


def new_session_token() -> str:
    """Mint an opaque session token.

    URL-safe text over :data:`SESSION_TOKEN_BYTES` bytes of ``secrets``
    randomness. It encodes nothing: not the account, not the tenant, and
    above all not a role. The server stores only :func:`hash_session_token`
    of it, so the value handed to the browser exists in exactly one place a
    database dump does not reach.
    """
    return secrets.token_urlsafe(SESSION_TOKEN_BYTES)


def hash_session_token(token: str) -> bytes:
    """The stored form of a session token.

    A plain SHA-256, deliberately *not* a slow KDF. The input is 32 bytes of
    uniform randomness rather than a human-chosen password, so there is no
    guessing attack for iteration count to slow down, and the lookup happens
    on every authenticated request. What the hash buys is that a leaked
    database does not hand over live sessions.
    """
    return hashlib.sha256(token.encode("utf-8")).digest()
