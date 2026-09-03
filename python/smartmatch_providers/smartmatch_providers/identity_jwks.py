"""JWKS bearer-token verification for user requests, behind a feature flag.

Plan P2 (`docs/plans/2026-08-28-a1b-institutional-sign-in-plan.md`) card A1:
the API's identity seam is a fixture verifier
(:class:`smartmatch_providers.identity.FixtureTokenVerifier`) that accepts only
explicitly registered tokens. This module adds the real shape of the live path —
signature, issuer, audience, expiry, key rotation — without turning it on.

## Why this ships switched off, and stays off

The stop-gate in that plan requires a committed configuration artifact naming
the issuer, the audience, the JWKS retrieval approach, and the key-rotation
policy. As of this module's authorship
``docs/decisions/a1b-idp-configuration-worksheet.md`` Part 1 is still blank:
a Google Cloud IdP development tenant exists, and none of its values have been
recorded. So this module invents none of them. There is no default issuer, no
default audience, and no default JWKS URI anywhere below — a plausible-looking
endpoint compiled into the tree would be indistinguishable from a real decision,
and would be the one failure mode nobody catches by reading tests.

The consequence is that the flag is the whole safety story:

* ``SMARTMATCH_JWKS_VERIFIER_ENABLED`` is unset or false — the default — and
  :func:`build_jwks_token_verifier` returns the verifier it was handed,
  unchanged. Nothing in this module is constructed and no behaviour anywhere
  differs.
* The flag is true and any required value is missing — startup raises
  :class:`~smartmatch_providers.base.ProviderConfigurationError` naming the
  absent settings. A deployment that asked for live verification and did not
  configure it must fail to boot, not fall back to something weaker.

## The signature primitive, and an honest gap

:class:`SignatureVerifier` is a port, and this repository ships no production
implementation of it, for exactly the reason
``services/worker/smartmatch_worker/identity.py`` gives at length: the
hash-pinned lock (``requirements/runtime.txt``) contains no asymmetric
primitive — no ``cryptography``, no ``pyjwt``, no ``google-auth`` — and
regenerating that lock is a separate, deliberate act coordinated with any other
lock-touching change (``docs/plans/critical-path-plans.md``, CP-A1B). The
response is not to hand-roll RSA. So the gap is named: with the flag on and no
backend supplied, construction fails closed.

## What this module deliberately does not do

* It does not fetch anything. :class:`JwksSource` is a port; the only
  implementation here is :class:`StaticJwksSource`. Fetching, caching, and the
  refresh-on-unknown-``kid`` behaviour belong to an implementation written once
  the worksheet records a JWKS URI and a cache TTL, and keeping them out of the
  verifier is what lets every path below be tested offline.
* It does not run any browser flow. Authorization-code/PKCE is card A2 and is
  blocked on worksheet §1.3, which is untouched.
* It does not read a tenant, a role, or any permission from the token. It
  returns :class:`~smartmatch_providers.identity.VerifiedIdentity` — a subject
  and, at most, a verified email — on the same reasoning
  :mod:`smartmatch_providers.identity` gives: a token that could name its own
  tenant is caller-selected identity wearing a JWT (MM-A01).
"""

from __future__ import annotations

import base64
import binascii
import json
import logging
import os
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any, Final, Protocol, runtime_checkable

from smartmatch_providers.base import ProviderConfigurationError
from smartmatch_providers.identity import (
    TokenVerificationError,
    TokenVerifier,
    VerifiedIdentity,
)

__all__ = [
    "ALGORITHMS_ENV_VAR",
    "AUDIENCE_ENV_VAR",
    "DEFAULT_ACCEPTED_ALGORITHMS",
    "DEFAULT_LEEWAY",
    "ENABLED_ENV_VAR",
    "ISSUER_ENV_VAR",
    "JWKS_URI_ENV_VAR",
    "LEEWAY_ENV_VAR",
    "JsonWebKey",
    "JwksSource",
    "JwksTokenVerifier",
    "JwksVerifierSettings",
    "SignatureVerifier",
    "StaticJwksSource",
    "build_jwks_token_verifier",
]

logger = logging.getLogger(__name__)

#: The feature flag. Absent means off; see the module docstring.
ENABLED_ENV_VAR: Final[str] = "SMARTMATCH_JWKS_VERIFIER_ENABLED"

#: Required when the flag is on. No value is defaulted: every one of these is a
#: blank field in ``docs/decisions/a1b-idp-configuration-worksheet.md`` Part 1.
ISSUER_ENV_VAR: Final[str] = "SMARTMATCH_JWKS_ISSUER"
AUDIENCE_ENV_VAR: Final[str] = "SMARTMATCH_JWKS_AUDIENCE"
JWKS_URI_ENV_VAR: Final[str] = "SMARTMATCH_JWKS_URI"

#: Optional, with defaults that narrow rather than widen what is accepted.
ALGORITHMS_ENV_VAR: Final[str] = "SMARTMATCH_JWKS_ALGORITHMS"
LEEWAY_ENV_VAR: Final[str] = "SMARTMATCH_JWKS_LEEWAY_SECONDS"

#: Values read as true. Anything else — including an empty string, a typo, and
#: an unset variable — is false, because the failure direction of an
#: unrecognised flag value must be "stay off".
_TRUE_VALUES: Final[frozenset[str]] = frozenset({"1", "true", "yes", "on"})

#: Never acceptable, whatever a configured backend claims to support. ``none``
#: is the unsigned-token bypass; the ``HS*`` family is the algorithm-confusion
#: attack, where a token signed with the *public* key as an HMAC secret verifies
#: against a naive implementation. Checked before the backend is consulted, so
#: the ban cannot be weakened by wiring in a permissive backend.
_FORBIDDEN_ALGORITHMS: Final[frozenset[str]] = frozenset(
    {"none", "hs1", "hs256", "hs384", "hs512", "dir"}
)

#: What an OIDC identity token is signed with in practice. Configurable, but the
#: default is one algorithm rather than a family: accepting more than the issuer
#: actually uses is matching surface bought for nothing.
DEFAULT_ACCEPTED_ALGORITHMS: Final[frozenset[str]] = frozenset({"RS256"})

#: Tolerance for clock disagreement between the issuer and this process. Small
#: on purpose: it is the window in which an expired token still works. The
#: worksheet's own clock-skew field, once recorded, overrides it by
#: configuration rather than by editing this line.
DEFAULT_LEEWAY: Final[timedelta] = timedelta(seconds=60)

#: Refuse to decode anything larger. A legitimate identity token is well under a
#: kilobyte, and an unbounded input is free work for an attacker.
_MAX_TOKEN_BYTES: Final[int] = 8192


@dataclass(frozen=True, slots=True)
class JsonWebKey:
    """One public key from a JWKS document.

    Attributes:
        kid: Key id, matched against the token header's ``kid``.
        alg: The algorithm this key is *for*. The token header must agree with
            it — the key decides which algorithm verifies it, not the token.
            Reversing that relationship is the algorithm-confusion attack.
        material: The remaining JWK members (``n`` and ``e`` for RSA), passed to
            the signature backend uninterpreted. This module does no
            cryptography and makes no assumption about their shape.
    """

    kid: str
    alg: str
    material: Mapping[str, str]


@runtime_checkable
class JwksSource(Protocol):
    """Supplies the issuer's current public keys.

    Fetching, caching, and rotation live behind this interface rather than in
    the verifier, so every path in :class:`JwksTokenVerifier` is exercisable
    without a network. See the module docstring: no fetching implementation
    ships here, because the worksheet records no JWKS URI or cache TTL yet.
    """

    def key_for(self, kid: str) -> JsonWebKey | None:
        """Return the key with this id, or ``None`` when it is not known."""
        ...


@runtime_checkable
class SignatureVerifier(Protocol):
    """Checks a JWT signature against a key.

    Attributes:
        algorithms: The ``alg`` values this backend implements. The token's
            algorithm must be in this set, in the verifier's configured set,
            *and* absent from the ban — so a backend can narrow what is
            accepted and never widen it.
    """

    algorithms: frozenset[str]

    def verify(self, *, signing_input: bytes, signature: bytes, key: JsonWebKey) -> None:
        """Return normally if the signature is valid.

        Raises:
            TokenVerificationError: if it is not.
        """
        ...


@dataclass(frozen=True, slots=True)
class StaticJwksSource:
    """A fixed set of keys, with no refresh.

    Safe to ship because it grants nothing on its own: an empty source rejects
    every token, and a populated one trusts exactly the keys an operator put in
    it. It is what tests use, and what a deployment that pins keys deliberately
    would use until a fetching source exists.
    """

    keys: Mapping[str, JsonWebKey] = field(default_factory=dict)

    def key_for(self, kid: str) -> JsonWebKey | None:
        """Return the key with this id, or ``None``."""
        return self.keys.get(kid)


@dataclass(frozen=True, slots=True)
class JwksVerifierSettings:
    """The environment's answer to "should live verification run, and how".

    Attributes:
        enabled: The feature flag. False unless the environment says otherwise.
        issuer: Expected ``iss``. Empty only when disabled.
        audience: Expected ``aud``. Empty only when disabled.
        jwks_uri: Where a fetching :class:`JwksSource` would read keys from.
            Carried but never dereferenced here — recorded so a misconfigured
            deployment fails at boot rather than at the first request, and so
            the value an operator set is visible in one place.
        algorithms: Accepted ``alg`` values, already intersected with nothing —
            the ban is applied at verification time, not here, so a settings
            object can never be the thing that authorises ``none``.
        leeway: Tolerated clock skew.
    """

    enabled: bool
    issuer: str
    audience: str
    jwks_uri: str
    algorithms: frozenset[str] = DEFAULT_ACCEPTED_ALGORITHMS
    leeway: timedelta = DEFAULT_LEEWAY

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> JwksVerifierSettings:
        """Read the flag and, when it is on, the configuration it requires.

        Args:
            env: The environment to read. Defaults to the process environment;
                injectable so a test never mutates it.

        Raises:
            ProviderConfigurationError: if the flag is on and any required
                value is absent or blank, or a supplied value is unusable. The
                message names every missing setting at once, because an
                operator fixing a boot failure should not have to discover them
                one restart at a time.
        """
        source = os.environ if env is None else env

        if source.get(ENABLED_ENV_VAR, "").strip().lower() not in _TRUE_VALUES:
            return cls(enabled=False, issuer="", audience="", jwks_uri="")

        issuer = source.get(ISSUER_ENV_VAR, "").strip()
        audience = source.get(AUDIENCE_ENV_VAR, "").strip()
        jwks_uri = source.get(JWKS_URI_ENV_VAR, "").strip()

        missing = [
            name
            for name, value in (
                (ISSUER_ENV_VAR, issuer),
                (AUDIENCE_ENV_VAR, audience),
                (JWKS_URI_ENV_VAR, jwks_uri),
            )
            if not value
        ]
        if missing:
            raise ProviderConfigurationError(
                f"{ENABLED_ENV_VAR} is set, but "
                + ", ".join(sorted(missing))
                + " is not configured. These values come from "
                "docs/decisions/a1b-idp-configuration-worksheet.md Part 1; this "
                "repository defaults none of them, and refuses to guess."
            )

        raw_algorithms = source.get(ALGORITHMS_ENV_VAR, "").strip()
        if raw_algorithms:
            algorithms = frozenset(
                part.strip() for part in raw_algorithms.split(",") if part.strip()
            )
            if not algorithms:
                raise ProviderConfigurationError(
                    f"{ALGORITHMS_ENV_VAR} is set but names no algorithm."
                )
        else:
            algorithms = DEFAULT_ACCEPTED_ALGORITHMS

        banned = sorted(alg for alg in algorithms if alg.lower() in _FORBIDDEN_ALGORITHMS)
        if banned:
            raise ProviderConfigurationError(
                f"{ALGORITHMS_ENV_VAR} names algorithms that are never accepted: "
                + ", ".join(banned)
                + ". Unsigned and symmetric algorithms are the token-forgery paths "
                "this verifier exists to close."
            )

        raw_leeway = source.get(LEEWAY_ENV_VAR, "").strip()
        if raw_leeway:
            try:
                seconds = int(raw_leeway)
            except ValueError as exc:
                raise ProviderConfigurationError(
                    f"{LEEWAY_ENV_VAR} must be a whole number of seconds; got {raw_leeway!r}."
                ) from exc
            if seconds < 0:
                raise ProviderConfigurationError(f"{LEEWAY_ENV_VAR} must not be negative.")
            leeway = timedelta(seconds=seconds)
        else:
            leeway = DEFAULT_LEEWAY

        return cls(
            enabled=True,
            issuer=issuer,
            audience=audience,
            jwks_uri=jwks_uri,
            algorithms=algorithms,
            leeway=leeway,
        )


def _now() -> datetime:
    """The current instant, as an aware UTC value.

    A named function rather than a lambda default so the verifier's ``clock``
    field has a type mypy can check, and so a stack trace names it.
    """
    return datetime.now(UTC)


@dataclass
class JwksTokenVerifier:
    """Verifies a bearer token against an issuer's published keys.

    Satisfies :class:`smartmatch_providers.identity.TokenVerifier`, so the API's
    existing seam takes one of these in place of the fixture with no other
    change.

    Args:
        issuer: The only trusted ``iss``.
        audience: The only accepted ``aud``. Audience is what stops a token
            minted for a sibling service — commonly sharing an issuer and a
            project — from opening this one.
        jwks: Where the issuer's public keys come from.
        signature_verifier: The signature primitive. See the module docstring
            for why this repository ships none and why that is left visible.
        algorithms: Accepted ``alg`` values, further narrowed by the backend's
            own set and by the unconditional ban.
        leeway: Tolerated clock skew.
        clock: Reads the current instant. Injected so expiry is testable without
            sleeping, and so no path here reaches a naive ``datetime.now()``.
        name: Identifies this adapter in logs, matching the ``name`` attribute
            the verifier protocol declares.

    Not frozen, for one reason only: ``TokenVerifier`` declares ``name`` as a
    settable attribute, and a frozen dataclass does not satisfy that protocol.
    Nothing here mutates any field, and nothing outside should.
    """

    issuer: str
    audience: str
    jwks: JwksSource
    signature_verifier: SignatureVerifier
    algorithms: frozenset[str] = DEFAULT_ACCEPTED_ALGORITHMS
    leeway: timedelta = DEFAULT_LEEWAY
    clock: Callable[[], datetime] = _now
    name: str = "jwks-identity"

    def verify(self, token: str) -> VerifiedIdentity:
        """Verify a token and return what it proves.

        The order is not incidental: the signature is checked before any claim
        is read, so no decision is ever made on unauthenticated text.

        Raises:
            TokenVerificationError: if the token is absent, malformed, signed by
                a key this issuer does not publish, minted for another audience
                or by another issuer, outside its validity window, or carrying
                no usable subject. Undifferentiated on purpose — see that
                exception's own docstring.
        """
        header, claims, signing_input, signature = _split_token(token)
        key = self._resolve_key(header)

        try:
            self.signature_verifier.verify(
                signing_input=signing_input, signature=signature, key=key
            )
        except TokenVerificationError:
            raise
        except Exception as exc:
            # A backend raising something of its own must still be a rejection,
            # never a 500 a caller could use to tell tokens apart. Logged with a
            # traceback because an unexpected failure in the signature primitive
            # is an operator's problem, not a caller's.
            logger.exception("bearer token: signature backend raised")
            raise TokenVerificationError("signature could not be verified") from exc

        return self._verify_claims(claims)

    # -- internals ---------------------------------------------------------

    def _resolve_key(self, header: Mapping[str, Any]) -> JsonWebKey:
        """Pick the key that must verify this token, or reject.

        The ban runs first and unconditionally. Then the key is looked up by
        ``kid``, and the header's algorithm must equal the key's own — so a
        token cannot nominate an algorithm the key was not published for.
        """
        algorithm = header.get("alg")
        if not isinstance(algorithm, str) or not algorithm:
            raise TokenVerificationError("token header declares no algorithm")
        if algorithm.lower() in _FORBIDDEN_ALGORITHMS:
            raise TokenVerificationError(f"algorithm {algorithm!r} is never accepted")
        if algorithm not in self.algorithms:
            raise TokenVerificationError(f"algorithm {algorithm!r} is not configured here")
        if algorithm not in self.signature_verifier.algorithms:
            raise TokenVerificationError(f"algorithm {algorithm!r} is not supported here")

        kid = header.get("kid")
        if not isinstance(kid, str) or not kid:
            raise TokenVerificationError("token header declares no key id")

        key = self.jwks.key_for(kid)
        if key is None:
            # Rotation lands here: a token signed with a key this process has
            # not seen is rejected, and a refreshing JwksSource is what makes
            # the next attempt succeed. Refusing is the correct answer either
            # way — an unknown key is not a trusted key.
            raise TokenVerificationError(f"no published key with id {kid!r}")
        if key.alg != algorithm:
            raise TokenVerificationError(
                f"token algorithm {algorithm!r} disagrees with key algorithm {key.alg!r}"
            )
        return key

    def _verify_claims(self, claims: Mapping[str, Any]) -> VerifiedIdentity:
        """Check every claim the trust decision rests on.

        Reached only after the signature verified, so these values are attested
        by the issuer rather than asserted by the caller.
        """
        issuer = claims.get("iss")
        if not isinstance(issuer, str) or issuer != self.issuer:
            raise TokenVerificationError("token issuer is not trusted")

        if not _audience_matches(claims.get("aud"), self.audience):
            raise TokenVerificationError("token audience is not this service")

        now = self.clock()

        expires_at = _timestamp(claims, "exp")
        if expires_at is None:
            raise TokenVerificationError("token carries no expiry")
        if now > expires_at + self.leeway:
            raise TokenVerificationError("token has expired")

        not_before = _timestamp(claims, "nbf")
        if not_before is not None and now < not_before - self.leeway:
            raise TokenVerificationError("token is not valid yet")

        issued_at = _timestamp(claims, "iat")
        if issued_at is not None and now < issued_at - self.leeway:
            raise TokenVerificationError("token was issued in the future")

        subject = claims.get("sub")
        if not isinstance(subject, str) or not subject.strip():
            raise TokenVerificationError("token carries no subject")

        return VerifiedIdentity(subject=subject, email=_verified_email(claims))


def build_jwks_token_verifier(
    fallback: TokenVerifier,
    *,
    env: Mapping[str, str] | None = None,
    jwks: JwksSource | None = None,
    signature_verifier: SignatureVerifier | None = None,
    clock: Callable[[], datetime] | None = None,
) -> TokenVerifier:
    """Return the live verifier when the flag is on, or ``fallback`` unchanged.

    This is the only entry point a bootstrap should use. With the flag off it
    performs no construction and returns the object it was given, so wiring it
    in is behaviour-preserving by inspection rather than by test.

    Args:
        fallback: The verifier already in use — today the fixture. Returned
            as-is when the flag is off.
        env: Environment to read. Defaults to the process environment.
        jwks: The key source. Required when the flag is on.
        signature_verifier: The signature primitive. Required when the flag is
            on; this repository ships none (see the module docstring).
        clock: Injected time source, for tests.

    Raises:
        ProviderConfigurationError: if the flag is on and the configuration,
            key source, or signature backend is missing. A deployment that
            asked for live verification and cannot perform it must fail to
            boot; silently keeping the fixture would be a deployment that
            believes it checks signatures and does not.
    """
    settings = JwksVerifierSettings.from_env(env)
    if not settings.enabled:
        return fallback

    missing = []
    if jwks is None:
        missing.append("no JWKS source was supplied")
    if signature_verifier is None:
        missing.append(
            "no signature backend is available (the pinned dependency set "
            "contains no asymmetric primitive)"
        )
    if missing:
        raise ProviderConfigurationError(
            f"{ENABLED_ENV_VAR} is set, but live verification cannot run: "
            + "; ".join(missing)
            + ". Refusing to fall back to the fixture verifier."
        )
    assert jwks is not None and signature_verifier is not None  # narrowed above

    return JwksTokenVerifier(
        issuer=settings.issuer,
        audience=settings.audience,
        jwks=jwks,
        signature_verifier=signature_verifier,
        algorithms=settings.algorithms,
        leeway=settings.leeway,
        clock=clock if clock is not None else _now,
    )


# ---------------------------------------------------------------------------
# Token decoding — no trust decisions here, only shape
# ---------------------------------------------------------------------------


def _split_token(token: str) -> tuple[Mapping[str, Any], Mapping[str, Any], bytes, bytes]:
    """Split a compact JWS into header, claims, signing input, and signature.

    Every failure is the same rejection. Nothing decoded here is trusted; the
    header is read only to choose a key, and the claims are returned so the
    caller can check them *after* the signature verifies.

    Raises:
        TokenVerificationError: if the token is empty, oversized, not three
            segments, not valid base64url, or not two JSON objects.
    """
    if not token or not token.strip():
        raise TokenVerificationError("no token presented")
    if len(token.encode("utf-8")) > _MAX_TOKEN_BYTES:
        raise TokenVerificationError("token is implausibly large")

    parts = token.split(".")
    if len(parts) != 3:
        raise TokenVerificationError("token is not a three-part JWS")

    encoded_header, encoded_claims, encoded_signature = parts
    header = _decode_json_segment(encoded_header, "header")
    claims = _decode_json_segment(encoded_claims, "claims")
    signature = _decode_segment(encoded_signature, "signature")
    signing_input = f"{encoded_header}.{encoded_claims}".encode("ascii")
    return header, claims, signing_input, signature


def _decode_segment(segment: str, what: str) -> bytes:
    """Base64url-decode one segment, restoring the stripped padding."""
    try:
        padding = "=" * (-len(segment) % 4)
        return base64.urlsafe_b64decode(segment + padding)
    except (binascii.Error, ValueError) as exc:
        raise TokenVerificationError(f"token {what} is not valid base64url") from exc


def _decode_json_segment(segment: str, what: str) -> Mapping[str, Any]:
    """Decode one segment and require it to be a JSON object."""
    try:
        decoded = json.loads(_decode_segment(segment, what))
    except (ValueError, UnicodeDecodeError) as exc:
        raise TokenVerificationError(f"token {what} is not valid JSON") from exc
    if not isinstance(decoded, dict):
        raise TokenVerificationError(f"token {what} is not a JSON object")
    return decoded


def _audience_matches(audience: Any, expected: str) -> bool:
    """Whether ``aud`` names this service.

    A JWT ``aud`` is a string or an array of strings. Both are accepted, and a
    single-element array is not treated as special: membership is the rule.
    """
    if isinstance(audience, str):
        return audience == expected
    if isinstance(audience, list):
        return any(isinstance(entry, str) and entry == expected for entry in audience)
    return False


def _timestamp(claims: Mapping[str, Any], name: str) -> datetime | None:
    """Read a numeric date claim as an aware UTC instant, or ``None``.

    Raises:
        TokenVerificationError: if the claim is present but not a number, or is
            out of range. A malformed timestamp is a malformed token, never a
            reason to skip the check it would have driven.
    """
    raw = claims.get(name)
    if raw is None:
        return None
    if isinstance(raw, bool) or not isinstance(raw, (int, float)):
        raise TokenVerificationError(f"token claim {name!r} is not a number")
    try:
        return datetime.fromtimestamp(float(raw), tz=UTC)
    except (OverflowError, OSError, ValueError) as exc:
        raise TokenVerificationError(f"token claim {name!r} is out of range") from exc


def _verified_email(claims: Mapping[str, Any]) -> str | None:
    """Return the email only when the issuer says it verified it.

    An unverified email is a string the account holder typed, and this repository
    never looks an account up by email anyway (ADR-0008: ``external_subject`` is
    the identity). Returning it only when ``email_verified`` is true keeps a
    self-asserted address out of logs and out of any future caller's reach.
    """
    email = claims.get("email")
    if not isinstance(email, str) or not email.strip():
        return None
    if claims.get("email_verified") is not True:
        return None
    return email
