"""The signature-backend port: "verify this JWT signature against this key".

This module is the seam named in security finding S-001 and argued at length in
:mod:`smartmatch_worker.identity`. It holds two things and deliberately nothing
else: the shape of a published key (:class:`JsonWebKey`) and the shape of the
primitive that checks a signature against one (:class:`SignatureVerifier`).

## Why it is its own module, and why it is empty of implementations

**This repository ships no production implementation of the port, and this
module is where that absence is visible.** Verifying RS256 needs an asymmetric
primitive, and the hash-pinned dependency lock (``requirements/runtime.txt``)
contains none — no ``cryptography``, no ``pyjwt``, no ``google-auth``.
Regenerating that lock is a separate, deliberate act, and hand-rolling PKCS#1
v1.5 verification is precisely the kind of code whose bugs are silent and total.

So the gap stays open and named. A file that declares a port and contains no
implementation of it is a legible statement that the primitive is missing;
scattering the declaration through the verifier that consumes it is not.
:func:`smartmatch_worker.identity.build_task_verifier` is passed no backend and
no JWKS source by the worker's composition root, and therefore returns a
verifier that refuses every delivery — see that module and
:mod:`smartmatch_worker.main`.

**Nothing here is a substitute for that missing primitive.** A test double
implementing this Protocol lives in the test suite (``tests/unit`` — see
``signature_backend_doubles``) and is never imported by this package: a double
proves that the *surrounding* verifier consults a backend, checks the signature
before any claim is trusted, and rejects a token signed with the wrong key. It
proves nothing about RSA, and a deployment that wired one in would have a
verifier that verifies nothing while looking exactly like one that does.

## The direction of the dependency

:mod:`smartmatch_worker.identity` imports from here, never the reverse. That
keeps this module free of the JWT parsing, claim checking, and configuration
logic it would otherwise be tangled with, and it means a future real backend
can be written against this file alone.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

__all__ = ["JsonWebKey", "SignatureBackendError", "SignatureVerifier"]


class SignatureBackendError(Exception):
    """A backend could not verify a signature, for any reason.

    The port's own rejection type, so a backend written against this module
    alone need not import the verifier that consumes it.

    A backend is equally free to raise
    :class:`smartmatch_worker.identity.TaskIdentityError` directly, and the
    stand-ins in the test suite do. Either is a rejection: the consuming
    verifier converts whatever is raised here into an undifferentiated
    ``TaskIdentityError`` before it reaches a caller, so no backend can turn a
    failed signature check into a distinguishable response — or into a ``500``.
    """


@dataclass(frozen=True, slots=True)
class JsonWebKey:
    """One public key from a JWKS document.

    Attributes:
        kid: Key id, matched against the token header's ``kid``.
        alg: The algorithm this key is *for*. The token header must agree with
            it — the key decides which algorithm verifies it, not the token.
            Reversing that relationship is the algorithm-confusion attack.
        material: The remaining JWK members (``n`` and ``e`` for RSA), passed
            through to the signature backend uninterpreted. Neither this module
            nor the verifier does any cryptography, so neither makes any
            assumption about their shape.
    """

    kid: str
    alg: str
    material: Mapping[str, str]


@runtime_checkable
class SignatureVerifier(Protocol):
    """Checks a JWT signature against a key.

    Attributes:
        algorithms: The ``alg`` values this backend implements. The consuming
            verifier requires the token's algorithm to be in this set *and*
            absent from its own unconditional ban (``none``, the ``HS*``
            family, ``dir``), so a backend can narrow the accepted algorithms
            but never widen them past that ban. Declaring an algorithm here
            grants nothing on its own.
    """

    algorithms: frozenset[str]

    def verify(self, *, signing_input: bytes, signature: bytes, key: JsonWebKey) -> None:
        """Return normally if, and only if, the signature is valid.

        Args:
            signing_input: The exact bytes that were signed — the token's
                encoded header and claims segments joined by a ``.``, never a
                re-encoding of the decoded values.
            signature: The decoded signature bytes.
            key: The key the signature must verify against, already resolved by
                ``kid`` and already checked to declare the token's algorithm.

        Raises:
            SignatureBackendError: if the signature does not verify.
        """
        ...
