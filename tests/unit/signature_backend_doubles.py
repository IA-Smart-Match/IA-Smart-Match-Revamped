"""Test doubles for the worker's signature-backend port, and their limits.

``smartmatch_worker.signature_backend`` declares
:class:`~smartmatch_worker.signature_backend.SignatureVerifier` and implements
none, because the hash-pinned runtime lock carries no asymmetric primitive.
This module supplies the doubles the test suite verifies *around* that hole.

**Nothing here is shipped.** These live under ``tests/`` and are never
importable from the ``smartmatch_worker`` package, which is the whole point: a
double implements the port's shape without implementing RS256, so a deployment
that wired one in would run a verifier that verifies nothing while looking
exactly like one that does. The package therefore contains no implementation of
the port at all, and the only implementations that exist are in this file, in a
directory no image copies.

What a double nonetheless proves, because everything around it is production
code: that :class:`~smartmatch_worker.identity.OidcTaskVerifier` consults the
backend at all, that it does so before trusting any claim, that a token signed
with the wrong key material is rejected, and that the algorithm ban is the
verifier's own rule rather than an accident of which algorithms a backend
happens to support. What no double can prove is that RSA PKCS#1 v1.5
verification is correct — nothing in this repository can.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
from dataclasses import dataclass
from typing import Any

from smartmatch_worker.signature_backend import JsonWebKey, SignatureBackendError

__all__ = [
    "PermissiveSymmetricBackend",
    "StandInSignatureBackend",
    "mint_token",
]


@dataclass(frozen=True, slots=True)
class StandInSignatureBackend:
    """A key-bound signature primitive that needs no third-party library.

    Computes HMAC-SHA256 over the JWT signing input with the key's ``material``
    and compares it with :func:`hmac.compare_digest`. That is **not** RS256 —
    see this module's docstring for exactly what it does and does not prove.

    Attributes:
        algorithms: Declared as ``RS256`` deliberately. The token header must
            agree with the resolved key's declared algorithm *and* with this
            set, and using the real algorithm name keeps the test tokens shaped
            like the ones Cloud Tasks actually mints, so the verifier's own
            agreement checks are exercised rather than sidestepped.
    """

    algorithms: frozenset[str] = frozenset({"RS256"})

    def verify(self, *, signing_input: bytes, signature: bytes, key: JsonWebKey) -> None:
        """Raise unless ``signature`` is this key's MAC over ``signing_input``.

        Raises:
            SignatureBackendError: if it is not — the port's own rejection
                type, so this double depends on the port module alone.
        """
        expected = hmac.new(
            key.material["k"].encode("utf-8"), signing_input, hashlib.sha256
        ).digest()
        if not hmac.compare_digest(expected, signature):
            raise SignatureBackendError("signature does not verify")


@dataclass(frozen=True, slots=True)
class PermissiveSymmetricBackend:
    """A double that *declares* symmetric support, to test the ban structurally.

    The verifier's refusal of ``alg: none`` and the ``HS*`` family must not
    depend on the configured backend happening to support only asymmetric
    algorithms. This one advertises ``HS256`` and accepts every signature, so a
    test can prove the rejection comes from the verifier's own unconditional
    rule: if :meth:`verify` is ever reached, the ban failed.
    """

    algorithms: frozenset[str] = frozenset({"HS256", "RS256"})

    def verify(self, *, signing_input: bytes, signature: bytes, key: JsonWebKey) -> None:
        """Accept anything. Reaching this method is itself the failure."""
        return None


def _segment(raw: bytes) -> str:
    """Base64url-encode one JWS segment, stripping the padding as a JWT does."""
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _json_segment(value: dict[str, Any]) -> str:
    """Encode one JSON segment with no incidental whitespace."""
    return _segment(json.dumps(value, separators=(",", ":")).encode("utf-8"))


def mint_token(
    *,
    header: dict[str, Any],
    claims: dict[str, Any],
    material: str | None,
) -> str:
    """Assemble a compact JWS the way a signer would, for a test to present.

    Args:
        header: The complete JOSE header, written out rather than defaulted —
            a test that pins how the header is treated should be able to read
            the header it presented in the test itself.
        claims: The complete claim set. Keys whose value is ``None`` are
            dropped, so a test can express "this token carries no ``exp``".
        material: The key material to MAC the signing input with, matching
            :class:`StandInSignatureBackend`. ``None`` produces an unsigned
            token — the trailing-dot ``alg: none`` shape.

    Returns:
        The encoded token, without the ``Bearer`` prefix.
    """
    present = {key: value for key, value in claims.items() if value is not None}
    signing_input = f"{_json_segment(header)}.{_json_segment(present)}"
    if material is None:
        return f"{signing_input}."

    signature = hmac.new(
        material.encode("utf-8"), signing_input.encode("ascii"), hashlib.sha256
    ).digest()
    return f"{signing_input}.{_segment(signature)}"
