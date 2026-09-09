"""The worker's signature-backend port, and the hole where its implementation isn't.

Two claims are pinned here, and they only mean something together.

The first is that the port *works*: given a backend, the production
:class:`~smartmatch_worker.identity.OidcTaskVerifier` consults it, checks the
signature before it trusts any claim, and rejects a token signed with the wrong
key. That is exercised with the stand-in doubles in ``signature_backend_doubles``
— HMAC, not RS256 — so what is proven is the verifier around the primitive, never
the primitive. Read that module's docstring for the exact limit.

The second is that the *shipped* path still has no backend and no JWKS source,
and therefore refuses everything. This is the absence pattern
``test_paid_extraction_wiring`` uses: the interesting assertion is about what a
booting worker does **not** acquire. Nothing in this PR wires a key source into
:func:`~smartmatch_worker.identity.build_task_verifier`, and these tests fail if
something later does so without saying why.

No network, no database, no Google. Every key, token, issuer, audience, and
service account below is a synthetic ``.invalid`` value written in this file.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from signature_backend_doubles import (
    PermissiveSymmetricBackend,
    StandInSignatureBackend,
    mint_token,
)
from smartmatch_worker.config import WorkerSettings
from smartmatch_worker.identity import (
    OidcTaskVerifier,
    StaticJwksSource,
    TaskIdentityError,
    TaskIdentityUnconfigured,
    UnconfiguredTaskVerifier,
    build_task_verifier,
)
from smartmatch_worker.main import create_app
from smartmatch_worker.signature_backend import (
    JsonWebKey,
    SignatureBackendError,
    SignatureVerifier,
)

# --- Synthetic constants ---------------------------------------------------
#
# All fabricated, all ``.invalid``: no real issuer, no real audience, no real
# service account, and no JWKS URI anywhere in this file or the module under
# test. Nothing here is reachable and nothing here is a credential.

ISSUER = "https://issuer.smartmatch.invalid"
AUDIENCE = "https://worker.smartmatch.invalid/tasks/execute"
DISPATCHER = "tasks-dispatcher@smartmatch-test.invalid"
KID = "synthetic-signing-key"
MATERIAL = "only-the-legitimate-signer-holds-this"
WRONG_MATERIAL = "a-key-nobody-published"

#: A DSN that is never connected to. ``create_app``'s lifespan builds a session
#: factory from it, which opens no connection, and no test here runs a command.
_UNUSED_DSN = "postgresql+psycopg://smartmatch:smartmatch@localhost:5432/smartmatch"


def _claims(**overrides: object) -> dict[str, object]:
    """A claim set that verifies, before any override is applied."""
    now = int(datetime.now(UTC).timestamp())
    claims: dict[str, object] = {
        "iss": ISSUER,
        "aud": AUDIENCE,
        "sub": "114857392847362718293",
        "email": DISPATCHER,
        "email_verified": True,
        "iat": now,
        "exp": now + 600,
    }
    claims.update(overrides)
    return claims


@pytest.fixture
def jwks() -> StaticJwksSource:
    """One published key, held in memory. No fetch, no URI, no network."""
    return StaticJwksSource(keys={KID: JsonWebKey(kid=KID, alg="RS256", material={"k": MATERIAL})})


@pytest.fixture
def verifier(jwks: StaticJwksSource) -> OidcTaskVerifier:
    """The production verifier, with a stand-in backend supplied by the test."""
    return OidcTaskVerifier(
        expected_audience=AUDIENCE,
        allowed_service_accounts=frozenset({DISPATCHER}),
        jwks=jwks,
        signature_verifier=StandInSignatureBackend(),
        accepted_issuers=frozenset({ISSUER}),
    )


class TestThePort:
    """The Protocol itself: shape only, and no implementation in the package."""

    def test_the_stand_in_double_satisfies_the_protocol(self):
        assert isinstance(StandInSignatureBackend(), SignatureVerifier)

    def test_the_package_ships_no_implementation_of_the_port(self):
        """`signature_backend` declares the port and implements nothing.

        The check is deliberately structural rather than a comment: if someone
        adds a class to that module with an ``algorithms`` attribute and a
        ``verify`` method, this fails and they have to argue for it in review.
        Adding a *real* vetted backend is a legitimate change — it just is not
        one that should be able to land silently, because it is exactly the
        change that turns a closed door into an open one.
        """
        from smartmatch_worker import signature_backend

        implementations = [
            name
            for name, value in vars(signature_backend).items()
            if isinstance(value, type)
            and not name.startswith("_")
            and value is not signature_backend.SignatureVerifier
            and hasattr(value, "algorithms")
        ]
        assert implementations == []


class TestABackendIsConsulted:
    """With a backend supplied, the production verifier actually uses it."""

    def test_a_locally_signed_token_is_accepted(self, verifier: OidcTaskVerifier):
        token = mint_token(
            header={"alg": "RS256", "kid": KID, "typ": "JWT"},
            claims=_claims(),
            material=MATERIAL,
        )

        identity = verifier.verify(f"Bearer {token}")

        assert identity.subject == "114857392847362718293"
        assert identity.email == DISPATCHER
        assert identity.audience == AUDIENCE

    def test_a_token_signed_with_the_wrong_key_is_rejected(self, verifier: OidcTaskVerifier):
        token = mint_token(
            header={"alg": "RS256", "kid": KID, "typ": "JWT"},
            claims=_claims(),
            material=WRONG_MATERIAL,
        )

        with pytest.raises(TaskIdentityError):
            verifier.verify(f"Bearer {token}")

    def test_a_backend_rejection_never_escapes_as_its_own_exception_type(
        self, verifier: OidcTaskVerifier
    ):
        """`SignatureBackendError` becomes the undifferentiated `TaskIdentityError`.

        A backend's own exception type reaching the boundary would be a ``500``
        rather than a ``401``, and a distinguishable one at that — telling a
        caller which forgery is worth refining.
        """
        token = mint_token(
            header={"alg": "RS256", "kid": KID, "typ": "JWT"},
            claims=_claims(),
            material=WRONG_MATERIAL,
        )

        with pytest.raises(TaskIdentityError) as raised:
            verifier.verify(f"Bearer {token}")
        assert not isinstance(raised.value, SignatureBackendError)

    def test_the_signature_is_checked_before_any_claim_is_trusted(self, verifier: OidcTaskVerifier):
        """A token with an expired claim set *and* a bad signature fails on the signature.

        Asserted through the backend rather than the message: the claim set here
        would be rejected on its own, so a verifier that read claims first would
        still raise — and would still pass a test that only checked that it
        raised.
        """
        seen: list[bytes] = []

        class RecordingBackend:
            algorithms = frozenset({"RS256"})

            def verify(self, *, signing_input: bytes, signature: bytes, key: JsonWebKey) -> None:
                seen.append(signing_input)
                raise SignatureBackendError("no")

        recording = OidcTaskVerifier(
            expected_audience=AUDIENCE,
            allowed_service_accounts=frozenset({DISPATCHER}),
            jwks=verifier.jwks,
            signature_verifier=RecordingBackend(),
            accepted_issuers=frozenset({ISSUER}),
        )
        expired = int((datetime.now(UTC) - timedelta(days=1)).timestamp())
        token = mint_token(
            header={"alg": "RS256", "kid": KID, "typ": "JWT"},
            claims=_claims(exp=expired, iat=expired - 600),
            material=MATERIAL,
        )

        with pytest.raises(TaskIdentityError):
            recording.verify(f"Bearer {token}")
        assert seen, "the backend was never consulted"

    def test_the_algorithm_ban_does_not_depend_on_the_backend(self):
        """`HS256` is refused even by a verifier whose backend advertises it."""
        permissive = OidcTaskVerifier(
            expected_audience=AUDIENCE,
            allowed_service_accounts=frozenset({DISPATCHER}),
            jwks=StaticJwksSource(
                keys={KID: JsonWebKey(kid=KID, alg="HS256", material={"k": MATERIAL})}
            ),
            signature_verifier=PermissiveSymmetricBackend(),
            accepted_issuers=frozenset({ISSUER}),
        )
        token = mint_token(
            header={"alg": "HS256", "kid": KID, "typ": "JWT"},
            claims=_claims(),
            material=MATERIAL,
        )

        with pytest.raises(TaskIdentityError):
            permissive.verify(f"Bearer {token}")

    def test_an_unsigned_token_is_refused_by_a_permissive_backend_too(self, jwks: StaticJwksSource):
        permissive = OidcTaskVerifier(
            expected_audience=AUDIENCE,
            allowed_service_accounts=frozenset({DISPATCHER}),
            jwks=jwks,
            signature_verifier=PermissiveSymmetricBackend(),
            accepted_issuers=frozenset({ISSUER}),
        )
        token = mint_token(
            header={"alg": "none", "kid": KID, "typ": "JWT"},
            claims=_claims(),
            material=None,
        )

        with pytest.raises(TaskIdentityError):
            permissive.verify(f"Bearer {token}")


class TestTheShippedBuildPathStaysClosed:
    """What this repository actually ships: no backend, no key source, no entry.

    The absence is the control, exactly as in ``test_paid_extraction_wiring``.
    """

    def test_build_reports_both_missing_pieces_even_when_everything_else_is_set(self):
        built = build_task_verifier(
            expected_audience=AUDIENCE,
            allowed_service_accounts=frozenset({DISPATCHER}),
        )

        assert isinstance(built, UnconfiguredTaskVerifier)
        assert "no signature backend" in built.reason
        assert "no JWKS source" in built.reason

    def test_a_jwks_source_alone_is_still_not_enough(self, jwks: StaticJwksSource):
        built = build_task_verifier(
            expected_audience=AUDIENCE,
            allowed_service_accounts=frozenset({DISPATCHER}),
            jwks=jwks,
        )

        assert isinstance(built, UnconfiguredTaskVerifier)
        assert "no signature backend" in built.reason

    def test_the_unconfigured_verifier_answers_401_shaped_and_501_shaped_refusals(self):
        built = build_task_verifier(
            expected_audience=AUDIENCE,
            allowed_service_accounts=frozenset({DISPATCHER}),
        )

        with pytest.raises(TaskIdentityError) as missing:
            built.verify(None)
        assert not isinstance(missing.value, TaskIdentityUnconfigured)

        with pytest.raises(TaskIdentityUnconfigured):
            built.verify("Bearer anything-at-all")

    def test_a_booting_worker_acquires_no_backend_and_no_key_source(self):
        """The composition root, run for real, still ends up refusing everything.

        This is the assertion that would break if someone wired a live JWKS
        source or a signature backend into ``main``'s lifespan. Both endpoints
        are checked: the scheduler verifier is built from its own settings and
        must not inherit anything from the task path.
        """
        app = create_app(settings=WorkerSettings(database_url=_UNUSED_DSN))

        with TestClient(app):
            assert isinstance(app.state.task_verifier, UnconfiguredTaskVerifier)
            assert isinstance(app.state.scheduler_verifier, UnconfiguredTaskVerifier)
            assert "no signature backend" in app.state.task_verifier.reason
            assert "no JWKS source" in app.state.task_verifier.reason
            assert "no signature backend" in app.state.scheduler_verifier.reason
