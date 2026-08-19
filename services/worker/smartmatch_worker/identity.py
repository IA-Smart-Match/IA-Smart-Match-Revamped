"""OIDC task-identity verification for the worker boundary.

Architecture v1.1 §3.1: the worker is a private Cloud Run service whose only
caller is Cloud Tasks, presenting an OIDC identity token minted for the
dispatcher's service account. This module is the control that makes "only Cloud
Tasks may invoke the worker" true rather than merely intended, and it resolves
security finding S-001.

## What verification actually means here

Five things, all of them required, none of them sufficient alone:

1. The token's **signature** verifies against the issuer's published key. Without
   this the rest is decoration — every other claim is attacker-controlled text.
2. The **issuer** is Google.
3. The **audience** is *this* service's URL. Cloud Run services in one project
   commonly share a service account; audience is the only thing that stops a
   token minted for another service from opening this one.
4. The token is **currently valid** — not expired, not issued in the future
   beyond a small clock skew.
5. The **service account** in ``email`` is on an explicit allowlist. A valid
   Google token proves only that *some* Google identity asked; the allowlist is
   what narrows that to the dispatcher.

## Everything is injected, because everything must be testable offline

The JWKS source, the signature primitive, and the clock are all constructor
arguments. A test can therefore supply its own keys and its own notion of "now"
and exercise the real code path. That is deliberate: a test that monkeypatches
the verifier away proves nothing about the verifier, and this is precisely the
control where "we believe it works" is not good enough.

## The signature primitive, and an honest gap

:class:`SignatureVerifier` is a port, and **this repository ships no production
implementation of it**. Verifying RS256 requires an asymmetric primitive, and
the hash-pinned dependency lock (``requirements/runtime.txt``) contains none —
no ``cryptography``, no ``pyjwt``, no ``google-auth``. Regenerating that lock is
a separate, deliberate act.

The response to that is *not* to hand-roll RSA. PKCS#1 v1.5 signature
verification is exactly the kind of code whose bugs are silent and total —
Bleichenbacher's low-exponent forgery is the canonical example — and a
hand-rolled version would be a verification step that looks right and admits
forgeries. So the gap is left open and named: :func:`build_task_verifier`
returns an :class:`UnconfiguredTaskVerifier` when no backend is supplied, and
the worker refuses every request, exactly as the scaffold's stub did. Supplying
a vetted backend is a one-argument change; pretending to have one is not
recoverable.

## Fail closed at every ambiguity

Missing audience, empty allowlist, absent signature backend, unparseable token,
``alg: none``, a symmetric algorithm, an unknown key id, a claim that does not
check out — every one of them is a rejection. An unconfigured deployment must be
a closed door, not an open one: the most dangerous version of this module is the
one that treats "nothing is configured" as "nothing to check".
"""

from __future__ import annotations

import base64
import binascii
import json
import logging
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any, Final, Protocol, runtime_checkable

__all__ = [
    "JsonWebKey",
    "JwksSource",
    "OidcTaskVerifier",
    "SignatureVerifier",
    "StaticJwksSource",
    "TaskIdentity",
    "TaskIdentityError",
    "TaskIdentityUnconfigured",
    "TaskIdentityVerifier",
    "UnconfiguredTaskVerifier",
    "build_task_verifier",
]

logger = logging.getLogger(__name__)

#: Algorithms that are never acceptable, whatever the configured backend claims
#: to support. ``none`` is the unsigned-token bypass; the ``HS*`` family is the
#: algorithm-confusion attack, where a token signed with the *public* key as an
#: HMAC secret verifies against a naive implementation. Checked before the
#: backend is consulted, so the ban cannot be weakened by wiring in a permissive
#: backend.
_FORBIDDEN_ALGORITHMS: Final[frozenset[str]] = frozenset(
    {"none", "hs1", "hs256", "hs384", "hs512", "dir"}
)

#: Issuers Google uses for identity tokens. Both spellings are current, and a
#: deployment that accepted only one would reject valid tokens at an arbitrary
#: future moment.
DEFAULT_ACCEPTED_ISSUERS: Final[frozenset[str]] = frozenset(
    {"https://accounts.google.com", "accounts.google.com"}
)

#: Tolerance for clock disagreement between the token's issuer and this process.
#: Small on purpose: it is the window in which an expired token still works.
DEFAULT_LEEWAY: Final[timedelta] = timedelta(seconds=60)

#: Refuse to decode anything larger. A legitimate Cloud Tasks OIDC token is well
#: under a kilobyte, and an unbounded input is free work for an attacker.
_MAX_TOKEN_BYTES: Final[int] = 8192


class TaskIdentityError(Exception):
    """The caller's task credential is absent, malformed, or not trusted.

    Deliberately undifferentiated, in the same spirit as
    :class:`smartmatch_providers.identity.TokenVerificationError`: telling a
    caller *which* check failed tells an attacker which forgery is worth
    refining. The specifics go to the log, where an operator can see them and a
    caller cannot.
    """


class TaskIdentityUnconfigured(TaskIdentityError):
    """Verification cannot run because this deployment has not configured it.

    Distinguished from an ordinary rejection only so the boundary can answer
    ``501`` rather than ``403``. The distinction is about *whose* problem it is —
    a caller cannot fix a missing audience by presenting a better token — and
    never about whether the request proceeds. It does not.
    """


@dataclass(frozen=True, slots=True)
class TaskIdentity:
    """What a verified task token proves.

    Attributes:
        subject: The issuer's stable subject identifier for the calling service
            account.
        email: The service-account address, already checked against the
            allowlist. Recorded so a log line can name the caller.
        audience: The audience the token was minted for, which has already been
            checked to equal this service's expected audience.

    Carries no tenant and no authority. The task payload names the tenant, and
    the worker re-reads that tenant's job from PostgreSQL; a token that could
    name its own tenant would be caller-selected identity in a better disguise
    (MM-A01).
    """

    subject: str
    email: str
    audience: str


@dataclass(frozen=True, slots=True)
class JsonWebKey:
    """One public key from a JWKS document.

    Attributes:
        kid: Key id, matched against the token header's ``kid``.
        alg: The algorithm this key is *for*. The token header must agree with
            it — the key decides which algorithm verifies it, not the token.
            Reversing that relationship is the algorithm-confusion attack.
        material: The remaining JWK members (``n`` and ``e`` for RSA), passed
            through to the signature backend uninterpreted. This module does no
            cryptography and therefore makes no assumptions about their shape.
    """

    kid: str
    alg: str
    material: Mapping[str, str]


@runtime_checkable
class JwksSource(Protocol):
    """Supplies the issuer's current public keys.

    Fetching, caching, and rotation live behind this interface rather than in
    the verifier. Google rotates its signing keys regularly, so a production
    implementation refreshes on an unknown ``kid`` and caches by
    ``Cache-Control`` — but a verifier that owned that logic could not be tested
    without a network, which is the whole reason this is a port.

    One constraint on any implementation: :meth:`key_for` is called on the
    worker's event loop, so it must answer from cache and refresh out of band. A
    source that fetched over HTTP inline would stall every other in-flight
    delivery on the instance while it waited.
    """

    def key_for(self, kid: str) -> JsonWebKey | None:
        """Return the key with this id, or ``None`` when it is not known."""
        ...


@runtime_checkable
class SignatureVerifier(Protocol):
    """Checks a JWT signature against a key.

    Attributes:
        algorithms: The ``alg`` values this backend implements. The verifier
            requires the token's algorithm to be in this set *and* absent from
            :data:`_FORBIDDEN_ALGORITHMS`, so a backend can narrow the accepted
            algorithms but never widen them past the ban.
    """

    algorithms: frozenset[str]

    def verify(self, *, signing_input: bytes, signature: bytes, key: JsonWebKey) -> None:
        """Return normally if the signature is valid.

        Raises:
            TaskIdentityError: if it is not.
        """
        ...


@runtime_checkable
class TaskIdentityVerifier(Protocol):
    """Verifies the ``Authorization`` header of a Cloud Tasks delivery."""

    def verify(self, authorization: str | None) -> TaskIdentity:
        """Verify the header and return the identity it proves.

        Raises:
            TaskIdentityError: if the caller is not a trusted task dispatcher.
        """
        ...


@dataclass(frozen=True, slots=True)
class StaticJwksSource:
    """A fixed set of keys, with no refresh.

    Suitable for tests and for a deployment that pins keys deliberately. It is
    safe to ship because it grants nothing on its own: an empty source rejects
    every token, and a populated one trusts exactly the keys an operator put in
    it.
    """

    keys: Mapping[str, JsonWebKey] = field(default_factory=dict)

    def key_for(self, kid: str) -> JsonWebKey | None:
        """Return the key with this id, or ``None``."""
        return self.keys.get(kid)


@dataclass(frozen=True, slots=True)
class UnconfiguredTaskVerifier:
    """Rejects everything, and says why.

    This is what the worker runs with until an audience, an allowlist, and a
    signature backend are all present. It is not a placeholder in the weak sense
    — it is the correct behavior for a deployment that cannot verify its
    callers, and it is what makes "forgot to configure it" fail visibly instead
    of silently opening the endpoint.

    Attributes:
        reason: Logged and returned to the caller as a configuration message. It
            names the missing control, not a secret: an operator reading a
            worker's 501 needs to know which setting is absent.
    """

    reason: str

    def verify(self, authorization: str | None) -> TaskIdentity:
        """Always raise.

        Raises:
            TaskIdentityError: if no credential was presented at all, so a
                caller that simply forgot one still gets ``401``.
            TaskIdentityUnconfigured: otherwise.
        """
        if not authorization:
            raise TaskIdentityError("missing task credentials")
        raise TaskIdentityUnconfigured(self.reason)


@dataclass(frozen=True)
class OidcTaskVerifier:
    """Verifies a Google-issued OIDC identity token minted for this service.

    Args:
        expected_audience: This service's URL, as configured on the Cloud Tasks
            queue. ``None`` means unconfigured, and every request is refused.
        allowed_service_accounts: Service-account addresses permitted to invoke
            the worker. An empty set means unconfigured, and every request is
            refused — an allowlist that permits everyone is not an allowlist.
        jwks: Where the issuer's public keys come from.
        signature_verifier: The signature primitive. ``None`` means the
            deployment has no backend, and every request is refused. See the
            module docstring for why that case is real and left open.
        accepted_issuers: Issuers to trust.
        leeway: Tolerated clock skew.
        clock: Reads the current instant. Injected so expiry can be tested
            without sleeping, and so no code path here can reach a naive
            ``datetime.now()``.

    Every constructor argument that can be missing is checked at ``verify``
    time rather than at construction, so a misconfigured worker still starts,
    still serves ``/health``, and still refuses work. Refusing to start would
    take the health endpoint with it and make a misconfiguration look like an
    outage.
    """

    expected_audience: str | None
    allowed_service_accounts: frozenset[str]
    jwks: JwksSource
    signature_verifier: SignatureVerifier | None
    accepted_issuers: frozenset[str] = DEFAULT_ACCEPTED_ISSUERS
    leeway: timedelta = DEFAULT_LEEWAY
    clock: Callable[[], datetime] = field(default=lambda: datetime.now(UTC))

    def verify(self, authorization: str | None) -> TaskIdentity:
        """Verify an ``Authorization`` header and return the caller's identity.

        The order is not incidental. Configuration is checked before the token
        is even looked at, so an unconfigured deployment cannot be probed for
        which tokens it likes; the signature is checked before any claim is
        read, so no decision is ever made on unauthenticated text.

        Raises:
            TaskIdentityUnconfigured: if verification is not configured here.
            TaskIdentityError: if the token is absent, malformed, unsigned by a
                trusted key, minted for another audience, outside its validity
                window, or presented by a service account that is not allowed.
        """
        self._assert_configured()

        token = _extract_bearer_token(authorization)
        header, claims, signing_input, signature = _split_token(token)

        key = self._resolve_key(header)
        assert self.signature_verifier is not None  # narrowed by _assert_configured
        try:
            self.signature_verifier.verify(
                signing_input=signing_input, signature=signature, key=key
            )
        except TaskIdentityError:
            raise
        except Exception as exc:
            # A backend that raises something of its own must still be a
            # rejection, never a 500 that a caller could use to distinguish
            # tokens. Logged with a traceback because an unexpected failure in
            # the signature primitive is an operator's problem.
            logger.exception("task token: signature backend raised")
            raise TaskIdentityError("signature could not be verified") from exc

        return self._verify_claims(claims)

    # -- internals ---------------------------------------------------------

    def _assert_configured(self) -> None:
        """Raise unless every control this verifier depends on is present."""
        missing = []
        if self.signature_verifier is None:
            missing.append(
                "no signature backend is available (the pinned dependency set "
                "contains no asymmetric primitive)"
            )
        if not self.expected_audience:
            missing.append("no expected audience is configured")
        if not self.allowed_service_accounts:
            missing.append("no dispatcher service-account allowlist is configured")

        if missing:
            raise TaskIdentityUnconfigured(
                "OIDC task-identity verification is not configured: "
                + "; ".join(missing)
                + ". This endpoint refuses every request until it is."
            )

    def _resolve_key(self, header: Mapping[str, Any]) -> JsonWebKey:
        """Pick the key that must verify this token, or reject.

        The algorithm ban runs first and unconditionally. Then the key is looked
        up by ``kid``, and the header's algorithm must equal the key's own — so
        the token cannot nominate an algorithm the key was not published for.
        """
        algorithm = header.get("alg")
        if not isinstance(algorithm, str) or not algorithm:
            raise TaskIdentityError("token header declares no algorithm")
        if algorithm.lower() in _FORBIDDEN_ALGORITHMS:
            raise TaskIdentityError(f"algorithm {algorithm!r} is never accepted")

        kid = header.get("kid")
        if not isinstance(kid, str) or not kid:
            raise TaskIdentityError("token header declares no key id")

        key = self.jwks.key_for(kid)
        if key is None:
            raise TaskIdentityError(f"no published key with id {kid!r}")
        if key.alg != algorithm:
            raise TaskIdentityError(
                f"token algorithm {algorithm!r} disagrees with key algorithm {key.alg!r}"
            )

        assert self.signature_verifier is not None  # narrowed by _assert_configured
        if algorithm not in self.signature_verifier.algorithms:
            raise TaskIdentityError(f"algorithm {algorithm!r} is not supported here")

        return key

    def _verify_claims(self, claims: Mapping[str, Any]) -> TaskIdentity:
        """Check every claim the trust decision rests on.

        Reached only after the signature verified, so the values here are
        attested by the issuer rather than asserted by the caller.
        """
        issuer = claims.get("iss")
        if not isinstance(issuer, str) or issuer not in self.accepted_issuers:
            raise TaskIdentityError(f"issuer {issuer!r} is not trusted")

        audience = claims.get("aud")
        if not isinstance(audience, str) or audience != self.expected_audience:
            # A string, not a list: Cloud Tasks mints a single-audience token,
            # and accepting an array would add matching surface for no gain.
            raise TaskIdentityError("token audience is not this service")

        now = self.clock()
        expires_at = _timestamp(claims, "exp")
        if expires_at is None:
            raise TaskIdentityError("token carries no expiry")
        if now > expires_at + self.leeway:
            raise TaskIdentityError("token has expired")

        issued_at = _timestamp(claims, "iat")
        if issued_at is None:
            raise TaskIdentityError("token carries no issue time")
        if issued_at > now + self.leeway:
            raise TaskIdentityError("token was issued in the future")

        not_before = _timestamp(claims, "nbf")
        if not_before is not None and now + self.leeway < not_before:
            raise TaskIdentityError("token is not yet valid")

        subject = claims.get("sub")
        if not isinstance(subject, str) or not subject:
            raise TaskIdentityError("token carries no subject")

        email = claims.get("email")
        if not isinstance(email, str) or not email:
            raise TaskIdentityError("token names no service account")
        if claims.get("email_verified") is not True:
            # Google marks service-account tokens verified. An unverified email
            # is not an identity, and matching an allowlist against one would
            # make the allowlist meaningless.
            raise TaskIdentityError("token's service account is not verified")
        if email not in self.allowed_service_accounts:
            raise TaskIdentityError(f"service account {email!r} is not permitted here")

        return TaskIdentity(subject=subject, email=email, audience=audience)


def build_task_verifier(
    *,
    expected_audience: str | None,
    allowed_service_accounts: frozenset[str],
    jwks: JwksSource | None = None,
    signature_verifier: SignatureVerifier | None = None,
    accepted_issuers: frozenset[str] = DEFAULT_ACCEPTED_ISSUERS,
) -> TaskIdentityVerifier:
    """Construct the worker's task-identity verifier, failing closed.

    Returns an :class:`UnconfiguredTaskVerifier` — which refuses everything —
    whenever a control is missing, and an :class:`OidcTaskVerifier` only when
    all of them are present. The two are interchangeable at the boundary, so
    there is no code path that "skips" verification; there is only a verifier
    that rejects for a different reason.

    Args:
        expected_audience: This service's URL. Absent by default.
        allowed_service_accounts: Dispatcher accounts permitted to invoke the
            worker. Empty by default.
        jwks: The issuer's key source. Absent by default; without it there is
            nothing to verify against.
        signature_verifier: The signature backend. Absent by default — see the
            module docstring. This is the one gap that cannot be closed by
            configuration alone.
        accepted_issuers: Issuers to trust.

    Returns:
        A :class:`TaskIdentityVerifier`.
    """
    missing: list[str] = []
    if signature_verifier is None:
        missing.append("no signature backend")
    if jwks is None:
        missing.append("no JWKS source")
    if not expected_audience:
        missing.append("no expected audience (SMARTMATCH_TASK_AUDIENCE)")
    if not allowed_service_accounts:
        missing.append("no service-account allowlist (SMARTMATCH_TASK_SERVICE_ACCOUNTS)")

    if missing or jwks is None:
        reason = (
            "OIDC task-identity verification is not configured in this deployment: "
            + ", ".join(missing)
            + ". The worker refuses every task delivery until it is."
        )
        logger.warning("worker task identity unconfigured: %s", reason)
        return UnconfiguredTaskVerifier(reason=reason)

    return OidcTaskVerifier(
        expected_audience=expected_audience,
        allowed_service_accounts=allowed_service_accounts,
        jwks=jwks,
        signature_verifier=signature_verifier,
        accepted_issuers=accepted_issuers,
    )


# ---------------------------------------------------------------------------
# Token parsing
# ---------------------------------------------------------------------------


def _extract_bearer_token(authorization: str | None) -> str:
    """Pull the token out of an ``Authorization`` header.

    Raises:
        TaskIdentityError: if the header is absent or is not a bearer credential.
    """
    if not authorization:
        raise TaskIdentityError("missing task credentials")
    if len(authorization) > _MAX_TOKEN_BYTES:
        raise TaskIdentityError("credential is implausibly large")

    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        raise TaskIdentityError("credential is not a bearer token")
    return token.strip()


def _split_token(token: str) -> tuple[dict[str, Any], dict[str, Any], bytes, bytes]:
    """Split a compact JWS into header, claims, signing input, and signature.

    The signing input is returned as the exact bytes that were signed — the
    original encoded segments, not a re-encoding of the decoded values. A
    re-encoding would not reproduce the signer's byte sequence, and a verifier
    built on one would either reject everything or, worse, be tempted into
    comparing decoded structures instead of signed bytes.

    Raises:
        TaskIdentityError: if the token is not three base64url segments carrying
            JSON objects.
    """
    parts = token.split(".")
    if len(parts) != 3:
        raise TaskIdentityError("token is not a three-part JWS")

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
        raise TaskIdentityError(f"token {what} is not valid base64url") from exc


def _decode_json_segment(segment: str, what: str) -> dict[str, Any]:
    """Decode one segment and parse it as a JSON object."""
    try:
        decoded = json.loads(_decode_segment(segment, what))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise TaskIdentityError(f"token {what} is not JSON") from exc

    if not isinstance(decoded, dict):
        raise TaskIdentityError(f"token {what} is not a JSON object")
    return decoded


def _timestamp(claims: Mapping[str, Any], name: str) -> datetime | None:
    """Read a NumericDate claim, or ``None`` when it is absent.

    A present-but-unusable value is a rejection rather than a ``None``: a token
    whose ``exp`` is the string ``"never"`` must not be treated as one carrying
    no expiry, because the caller of this function treats absence as its own
    explicit failure and a lenient parse here would blur the two.
    """
    raw = claims.get(name)
    if raw is None:
        return None
    if isinstance(raw, bool) or not isinstance(raw, int | float):
        raise TaskIdentityError(f"token {name} is not a numeric date")
    try:
        return datetime.fromtimestamp(raw, tz=UTC)
    except (OverflowError, OSError, ValueError) as exc:
        raise TaskIdentityError(f"token {name} is not a representable instant") from exc
