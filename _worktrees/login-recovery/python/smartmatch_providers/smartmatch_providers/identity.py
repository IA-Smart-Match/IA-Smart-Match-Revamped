"""Identity token verification.

Architecture v1.1: Google Identity Platform is the identity provider, and
``POST /auth/mock-login`` is archived (MM-A01). The single rule this module
exists to enforce is that **identity comes from a verified token, never from the
request**.

A verifier returns only what the token proves: the issuer's subject identifier
and, when present, an email. It deliberately does **not** return a tenant, a
role, or any permission. Those are looked up server-side from the subject. A
token that could name its own tenant would be caller-selected identity wearing a
JWT, which is the legacy pattern in a better disguise.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

__all__ = [
    "FixtureTokenVerifier",
    "TokenVerificationError",
    "TokenVerifier",
    "VerifiedIdentity",
]


class TokenVerificationError(Exception):
    """The token is absent, malformed, expired, or not trusted.

    Deliberately carries no detail about *which*. Distinguishing "expired" from
    "bad signature" in a response tells an attacker which tokens are worth
    forging; the specifics belong in the server log.
    """


@dataclass(frozen=True, slots=True)
class VerifiedIdentity:
    """What a verified token proves.

    Attributes:
        subject: The identity provider's stable subject identifier. Matched
            against ``user_account.external_subject`` to find the local account.
        email: The verified email, when the token carries one. Never used for
            lookup — emails change, and a mutable identifier is not an identity.
    """

    subject: str
    email: str | None = None


@runtime_checkable
class TokenVerifier(Protocol):
    """Verifies a bearer token."""

    name: str

    def verify(self, token: str) -> VerifiedIdentity:
        """Verify a token and return what it proves.

        Raises:
            TokenVerificationError: if the token is not valid and trusted.
        """
        ...


@dataclass
class FixtureTokenVerifier:
    """Accepts only tokens explicitly registered with it.

    For local development, CI, and the classroom. Registration is explicit
    because a fixture that accepts *any* token is indistinguishable from no
    authentication at all — and if such a fixture were ever wired into a
    deployed environment by misconfiguration, nothing would fail visibly.

    Instance state, never module state (the legacy's module-level state is
    archived, MM-A02): each test owns its own verifier.
    """

    name: str = "fixture-identity"
    #: Token string to the identity it proves.
    subjects: dict[str, VerifiedIdentity] = field(default_factory=dict)

    def register(self, token: str, subject: str, email: str | None = None) -> None:
        """Make ``token`` verify as ``subject``."""
        self.subjects[token] = VerifiedIdentity(subject=subject, email=email)

    def verify(self, token: str) -> VerifiedIdentity:
        """Verify a registered token.

        Raises:
            TokenVerificationError: for any token not explicitly registered.
        """
        identity = self.subjects.get(token)
        if identity is None:
            raise TokenVerificationError("token is not valid")
        return identity
