"""Isolated JWT/JWKS verifier core — offline, static keys only.

**Scaffold, unwired, not production-ready.** Nothing in the API imports this
module: :class:`smartmatch_providers.identity.FixtureTokenVerifier` remains what
``smartmatch_api.main`` builds. This module exists so the shape of a real
signature-verifying :class:`~smartmatch_providers.identity.TokenVerifier` can be
designed and tested in-process, *before* the institutional sign-in stop-gate
(plan P2 card A0) is cleared. Cards A1-A4 stay blocked until
``docs/decisions/a1b-idp-configuration-worksheet.md`` is filled in and approved
by a named owner, so this module invents no issuer, audience, JWKS URI, client
ID, key-rotation policy, or clock-skew tolerance: every one of those is supplied
by the caller, and the only callers are tests supplying test literals.

Three properties make that guarantee structural rather than a promise in a
docstring:

* **No discovery, no network.** The constructor accepts a
  :class:`StaticJWKS` — a decoded, in-memory key set. There is no JWKS URI
  parameter, no discovery-document parameter, and no HTTP client anywhere in
  the module. A JWKS that is not already in memory cannot be reached.
* **Live issuers are refused at construction.** :data:`BLOCKED_ISSUER_HOSTS`
  names the hosted identity services this scaffold must not be pointed at. A
  verifier configured with one raises
  :class:`~smartmatch_providers.base.ProviderConfigurationError` before it can
  verify anything. Wiring a live issuer is therefore a deliberate edit to this
  file under a cleared gate, not a configuration slip.
* **The token proves identity and nothing else.** Only ``sub`` and, when
  present, ``email`` are read. Tenant, role, and permission claims are not read
  even if a token carries them — the rule stated in
  :mod:`smartmatch_providers.identity`, enforced here by simply having no code
  that looks at them.

The RS256 check is RSASSA-PKCS1-v1_5 over SHA-256, implemented against the
public key with :mod:`hashlib` and integer arithmetic (RFC 8017 §8.2.2). That
avoids adding a dependency to a hash-locked runtime for a module that is not
wired to anything. It handles no secret material: the private half of every key
used against it lives only in the test fixtures. A verifier that is ever
actually wired to an institutional IdP should be reviewed against a vetted JOSE
library rather than inheriting this implementation unexamined.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
import time
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from typing import Any, Final
from urllib.parse import urlsplit

from smartmatch_providers.base import ProviderConfigurationError
from smartmatch_providers.identity import TokenVerificationError, VerifiedIdentity

__all__ = [
    "BLOCKED_ISSUER_HOSTS",
    "RSAPublicJWK",
    "StaticJWKS",
    "StaticJWKSTokenVerifier",
]

#: The only signature algorithm this verifier accepts. Not configurable: an
#: algorithm the caller can widen is an algorithm an attacker can narrow, and
#: ``{"alg": "none"}`` is the canonical way that goes wrong.
_ALGORITHM: Final[str] = "RS256"

#: ASN.1 DigestInfo prefix for SHA-256 (RFC 8017 §9.2 note 1).
_SHA256_DIGEST_INFO: Final[bytes] = bytes.fromhex("3031300d060960864801650304020105000420")

#: Smallest RSA modulus accepted, in bits. Well below anything an institutional
#: IdP issues; present so a fixture key that is too small to be a meaningful
#: test of the padding check is rejected rather than quietly accepted.
_MIN_MODULUS_BITS: Final[int] = 2048

#: Hosted identity services this scaffold must never be configured against.
#: Matched on the issuer's host, including subdomains. This is a fence, not a
#: vendor judgement: the pilot's standing constraints include
#: ``ALLOW_LIVE_PROVIDERS=false``, and the A1b worksheet's issuer field is
#: unfilled, so *any* live issuer here would be an invented value.
BLOCKED_ISSUER_HOSTS: Final[frozenset[str]] = frozenset(
    {
        "securetoken.google.com",
        "accounts.google.com",
        "identitytoolkit.googleapis.com",
        "googleapis.com",
        "oauth2.googleapis.com",
        "login.microsoftonline.com",
        "sts.windows.net",
        "okta.com",
        "auth0.com",
    }
)


def _b64url_decode(segment: str) -> bytes:
    """Decode one base64url JWS segment.

    Raises:
        TokenVerificationError: if the segment is not strict, unpadded
            base64url. Accepting sloppy encodings means two parties can disagree
            about what bytes were signed.
    """
    if not segment or "=" in segment:
        raise TokenVerificationError("token is not valid")
    padding = "=" * (-len(segment) % 4)
    try:
        return base64.urlsafe_b64decode(segment + padding)
    except (binascii.Error, ValueError) as exc:
        raise TokenVerificationError("token is not valid") from exc


def _decode_json_object(raw: bytes) -> Mapping[str, Any]:
    """Decode a JWS segment's JSON object.

    Raises:
        TokenVerificationError: if the segment is not a JSON object.
    """
    try:
        value = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise TokenVerificationError("token is not valid") from exc
    if not isinstance(value, dict):
        raise TokenVerificationError("token is not valid")
    return value


def _numeric_claim(claims: Mapping[str, Any], name: str) -> float | None:
    """Read a NumericDate claim.

    Returns:
        The value as a float, or ``None`` when the claim is absent.

    Raises:
        TokenVerificationError: if the claim is present but not a number.
            ``bool`` is rejected explicitly — it is an ``int`` subclass, and
            ``exp: true`` must not read as ``exp: 1``.
    """
    if name not in claims:
        return None
    value = claims[name]
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise TokenVerificationError("token is not valid")
    return float(value)


def _int_from_b64url(value: str) -> int:
    """Decode a base64url big-endian integer from a JWK.

    Raises:
        ProviderConfigurationError: if the value is empty or not decodable.
    """
    try:
        raw = base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
    except (binascii.Error, ValueError) as exc:
        raise ProviderConfigurationError("a JWKS key value is not valid base64url") from exc
    if not raw:
        raise ProviderConfigurationError("a JWKS key value is empty")
    return int.from_bytes(raw, "big")


@dataclass(frozen=True, slots=True)
class RSAPublicJWK:
    """One RSA public key from a decoded JWKS.

    Attributes:
        kid: Key identifier. Tokens name the key they were signed with, so a
            key set can be rotated without a flag day.
        modulus: RSA modulus ``n`` as an integer.
        exponent: RSA public exponent ``e`` as an integer.
    """

    kid: str
    modulus: int
    exponent: int

    def __post_init__(self) -> None:
        """Reject keys that cannot support a meaningful RS256 check.

        Raises:
            ProviderConfigurationError: if the key is unusable or too small.
        """
        if not self.kid:
            raise ProviderConfigurationError("a JWKS key must have a non-empty kid")
        if self.modulus.bit_length() < _MIN_MODULUS_BITS:
            raise ProviderConfigurationError(
                f"JWKS key {self.kid!r} has a {self.modulus.bit_length()}-bit modulus; "
                f"at least {_MIN_MODULUS_BITS} bits are required"
            )
        if self.exponent < 3 or self.exponent % 2 == 0:
            raise ProviderConfigurationError(
                f"JWKS key {self.kid!r} has an invalid public exponent"
            )

    @classmethod
    def from_jwk(cls, jwk: Mapping[str, Any]) -> RSAPublicJWK:
        """Build a key from a JWK mapping (``kty``/``kid``/``n``/``e``).

        Args:
            jwk: A single JWK, already parsed from JSON. Supplied in-process by
                the caller — never fetched.

        Raises:
            ProviderConfigurationError: if the JWK is not an RS256-capable RSA
                public signing key.
        """
        if jwk.get("kty") != "RSA":
            raise ProviderConfigurationError("only RSA JWKS keys are supported")
        alg = jwk.get("alg")
        if alg is not None and alg != _ALGORITHM:
            raise ProviderConfigurationError(f"only {_ALGORITHM} JWKS keys are supported")
        use = jwk.get("use")
        if use is not None and use != "sig":
            raise ProviderConfigurationError("only signing JWKS keys are supported")
        kid, modulus, exponent = jwk.get("kid"), jwk.get("n"), jwk.get("e")
        if not (isinstance(kid, str) and isinstance(modulus, str) and isinstance(exponent, str)):
            raise ProviderConfigurationError("a JWKS key needs string kid, n, and e values")
        return cls(
            kid=kid,
            modulus=_int_from_b64url(modulus),
            exponent=_int_from_b64url(exponent),
        )


@dataclass(frozen=True, slots=True)
class StaticJWKS:
    """An in-memory key set, indexed by ``kid``.

    There is deliberately no constructor that takes a URI. The whole point of
    this type is that the key material is already present: a verifier holding a
    :class:`StaticJWKS` has nothing to fetch and no cache to go stale.
    """

    keys: Mapping[str, RSAPublicJWK]

    @classmethod
    def from_keys(cls, keys: Iterable[RSAPublicJWK]) -> StaticJWKS:
        """Build a key set from decoded keys.

        Raises:
            ProviderConfigurationError: if the set is empty or has a duplicate
                ``kid`` — a duplicate makes key selection ambiguous, and an
                ambiguous selection is a verification result nobody can reason
                about.
        """
        indexed: dict[str, RSAPublicJWK] = {}
        for key in keys:
            if key.kid in indexed:
                raise ProviderConfigurationError(f"duplicate kid {key.kid!r} in the key set")
            indexed[key.kid] = key
        if not indexed:
            raise ProviderConfigurationError("a key set must contain at least one key")
        return cls(keys=indexed)

    @classmethod
    def from_jwks_document(cls, document: Mapping[str, Any]) -> StaticJWKS:
        """Build a key set from a parsed JWKS document (``{"keys": [...]}``).

        Args:
            document: An already-parsed JWKS. This method does no IO: the
                caller decides where the bytes came from, and in this scaffold
                the caller is always a test with a synthetic key.

        Raises:
            ProviderConfigurationError: if the document has no ``keys`` list.
        """
        raw_keys = document.get("keys")
        if not isinstance(raw_keys, list):
            raise ProviderConfigurationError("a JWKS document needs a 'keys' list")
        return cls.from_keys(RSAPublicJWK.from_jwk(key) for key in raw_keys)

    def get(self, kid: str) -> RSAPublicJWK | None:
        """Return the key with this ``kid``, or ``None``."""
        return self.keys.get(kid)


def _assert_issuer_is_not_live(issuer: str) -> None:
    """Refuse an issuer that names a hosted identity service.

    Raises:
        ProviderConfigurationError: if ``issuer``'s host is, or is a subdomain
            of, a host in :data:`BLOCKED_ISSUER_HOSTS`.
    """
    if not issuer:
        raise ProviderConfigurationError("an issuer is required")
    host = (urlsplit(issuer).hostname or issuer).lower().rstrip(".")
    for blocked in BLOCKED_ISSUER_HOSTS:
        if host == blocked or host.endswith(f".{blocked}"):
            raise ProviderConfigurationError(
                f"issuer {issuer!r} names a live identity provider ({blocked}). "
                "This verifier is an offline scaffold: the A1b stop-gate "
                "(docs/decisions/a1b-idp-configuration-worksheet.md) is not "
                "cleared, and no live issuer, audience, or JWKS URI is committed."
            )


def _split(token: str) -> tuple[str, str, str]:
    """Split a compact JWS into its three segments.

    Raises:
        TokenVerificationError: if the token is not three dot-separated parts.
    """
    if not isinstance(token, str):
        raise TokenVerificationError("token is not valid")
    parts = token.split(".")
    if len(parts) != 3:
        raise TokenVerificationError("token is not valid")
    return parts[0], parts[1], parts[2]


def _rs256_signature_is_valid(key: RSAPublicJWK, signing_input: bytes, signature: bytes) -> bool:
    """Check an RSASSA-PKCS1-v1_5 SHA-256 signature (RFC 8017 §8.2.2).

    Verification re-encodes the expected padded message and compares it to the
    recovered one, rather than parsing the recovered bytes. Parsing invites the
    lenient-padding family of forgeries; an equality check against a fully
    constructed encoding has nothing to be lenient about.

    Returns:
        True if the signature is valid under ``key``.
    """
    modulus_bytes = (key.modulus.bit_length() + 7) // 8
    if len(signature) != modulus_bytes:
        return False
    signature_int = int.from_bytes(signature, "big")
    if signature_int >= key.modulus:
        return False
    recovered = pow(signature_int, key.exponent, key.modulus).to_bytes(modulus_bytes, "big")

    digest_info = _SHA256_DIGEST_INFO + hashlib.sha256(signing_input).digest()
    padding_length = modulus_bytes - len(digest_info) - 3
    if padding_length < 8:
        return False
    expected = b"\x00\x01" + b"\xff" * padding_length + b"\x00" + digest_info
    return hmac.compare_digest(recovered, expected)


@dataclass(frozen=True)
class StaticJWKSTokenVerifier:
    """Verifies RS256 tokens against a caller-supplied static key set.

    Satisfies :class:`~smartmatch_providers.identity.TokenVerifier`. Every trust
    anchor is a constructor argument, so a test can state exactly what it
    trusts and this module can state that it knows nothing on its own.

    Args:
        keys: The decoded key set. In-memory; never fetched.
        issuer: The exact ``iss`` a token must carry. Rejected at construction
            if it names a live identity provider.
        audience: The exact ``aud`` a token must carry (or contain, when
            ``aud`` is a list).
        leeway_seconds: Clock-skew tolerance applied to ``exp`` and ``nbf``.
            The real tolerance is an unfilled worksheet field; this default of
            zero is a test convenience and asserts nothing about any tenant.
        now: Clock, injected so expiry tests need no sleeping.
        name: Verifier name, for logs.
    """

    keys: StaticJWKS
    issuer: str
    audience: str
    leeway_seconds: float = 0.0
    now: Callable[[], float] = time.time
    name: str = "static-jwks-identity"

    def __post_init__(self) -> None:
        """Validate the configuration.

        Raises:
            ProviderConfigurationError: for a live issuer, an empty audience, or
                a negative skew tolerance.
        """
        _assert_issuer_is_not_live(self.issuer)
        if not self.audience:
            raise ProviderConfigurationError("an audience is required")
        if self.leeway_seconds < 0:
            raise ProviderConfigurationError("leeway_seconds must not be negative")

    def verify(self, token: str) -> VerifiedIdentity:
        """Verify a token and return only what it proves.

        Checks, in order: the JWS structure; a ``kid`` in the header; ``alg ==
        RS256``; the RSASSA-PKCS1-v1_5 signature over the signing input; then
        ``exp``, ``nbf``, ``iss``, and ``aud`` against this verifier's
        arguments. Claims are read only after the signature holds, so an
        unsigned token's claims never influence anything.

        Returns:
            The subject and, when the token carries one, the email. No tenant,
            role, or permission is read.

        Raises:
            TokenVerificationError: if the token is not valid and trusted. The
                reason is deliberately not distinguished to the caller.
        """
        header_b64, payload_b64, signature_b64 = _split(token)
        header = _decode_json_object(_b64url_decode(header_b64))

        kid = header.get("kid")
        if not isinstance(kid, str) or not kid:
            raise TokenVerificationError("token is not valid")
        if header.get("alg") != _ALGORITHM:
            raise TokenVerificationError("token is not valid")
        typ = header.get("typ")
        if typ is not None and (not isinstance(typ, str) or typ.upper() not in {"JWT", "AT+JWT"}):
            raise TokenVerificationError("token is not valid")
        if header.get("crit") is not None:
            raise TokenVerificationError("token is not valid")

        key = self.keys.get(kid)
        if key is None:
            raise TokenVerificationError("token is not valid")

        signing_input = f"{header_b64}.{payload_b64}".encode("ascii")
        if not _rs256_signature_is_valid(key, signing_input, _b64url_decode(signature_b64)):
            raise TokenVerificationError("token is not valid")

        claims = _decode_json_object(_b64url_decode(payload_b64))
        self._assert_claims_are_acceptable(claims)

        subject = claims.get("sub")
        if not isinstance(subject, str) or not subject:
            raise TokenVerificationError("token is not valid")
        email = claims.get("email")
        if email is not None and (not isinstance(email, str) or not email):
            raise TokenVerificationError("token is not valid")
        return VerifiedIdentity(subject=subject, email=email)

    def _assert_claims_are_acceptable(self, claims: Mapping[str, Any]) -> None:
        """Check the time, issuer, and audience claims.

        Raises:
            TokenVerificationError: if any check fails.
        """
        expiry = _numeric_claim(claims, "exp")
        if expiry is None:
            raise TokenVerificationError("token is not valid")
        now = self.now()
        if now >= expiry + self.leeway_seconds:
            raise TokenVerificationError("token is not valid")

        not_before = _numeric_claim(claims, "nbf")
        if not_before is not None and now < not_before - self.leeway_seconds:
            raise TokenVerificationError("token is not valid")
        _numeric_claim(claims, "iat")  # Present only to reject a non-numeric iat.

        if claims.get("iss") != self.issuer:
            raise TokenVerificationError("token is not valid")

        audience = claims.get("aud")
        if isinstance(audience, str):
            audiences = [audience]
        elif isinstance(audience, list) and all(isinstance(item, str) for item in audience):
            audiences = audience
        else:
            raise TokenVerificationError("token is not valid")
        if self.audience not in audiences:
            raise TokenVerificationError("token is not valid")
