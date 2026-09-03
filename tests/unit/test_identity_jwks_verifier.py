"""Unit tests for the flag-gated JWKS bearer-token verifier.

The verifier under test is
``python/smartmatch_providers/smartmatch_providers/identity_jwks.py``, added by
plan P2 card A1 while the IdP worksheet's Part 1 is still outstanding. Two
properties matter most and both are asserted here rather than assumed:

1. **With the flag off, nothing changes.** ``build_jwks_token_verifier``
   returns the very object it was handed — asserted with ``is``, not equality.
2. **Nothing reaches a live endpoint.** Every token below is minted in-process
   against keys this file generates, and the key source is
   :class:`StaticJwksSource`. No issuer URL, audience, or JWKS URI in this file
   is a real one — they are ``.invalid`` placeholders, deliberately, because
   the committed worksheet records no real values and a test fixture that
   looked like one would be the first thing a future reader mistook for a
   decision.

The signature primitive is a stand-in HMAC backend, the same device
``tests/integration/test_worker_execution.py`` uses for the worker's OIDC
verifier and for the same reason: the hash-pinned dependency lock carries no
asymmetric primitive. What it nonetheless proves — because everything around it
is production code — is that a wrong key, an edited payload, an unknown ``kid``,
a banned algorithm, and every claim check are all rejections, and that the
signature is checked before any claim is trusted.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from smartmatch_providers.base import ProviderConfigurationError
from smartmatch_providers.identity import (
    FixtureTokenVerifier,
    TokenVerificationError,
    VerifiedIdentity,
)
from smartmatch_providers.identity_jwks import (
    ALGORITHMS_ENV_VAR,
    AUDIENCE_ENV_VAR,
    ENABLED_ENV_VAR,
    ISSUER_ENV_VAR,
    JWKS_URI_ENV_VAR,
    LEEWAY_ENV_VAR,
    JsonWebKey,
    JwksTokenVerifier,
    JwksVerifierSettings,
    StaticJwksSource,
    build_jwks_token_verifier,
)

# Placeholders, not configuration. See the module docstring.
ISSUER = "https://issuer.test.invalid/"
AUDIENCE = "smartmatch-api-under-test"
JWKS_URI = "https://issuer.test.invalid/jwks"
KID = "key-1"
KEY_MATERIAL = "hmac-stand-in-key-one"

NOW = datetime(2026, 9, 3, 12, 0, tzinfo=UTC)


@dataclass(frozen=True)
class StandInSignatureVerifier:
    """A key-bound signature primitive that needs no third-party library.

    HMAC-SHA256 over the JWT signing input with the key's material. That is
    *not* RS256, and this class must never be wired into a deployment — it
    lives in the test suite for that reason, and declares ``RS256`` only so the
    tokens below are shaped like the ones an issuer actually mints.
    """

    algorithms: frozenset[str] = frozenset({"RS256"})

    def verify(self, *, signing_input: bytes, signature: bytes, key: JsonWebKey) -> None:
        """Raise unless ``signature`` is this key's MAC over ``signing_input``."""
        expected = hmac.new(
            key.material["k"].encode("utf-8"), signing_input, hashlib.sha256
        ).digest()
        if not hmac.compare_digest(expected, signature):
            raise TokenVerificationError("signature does not verify")


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _mint(
    *,
    key_material: str = KEY_MATERIAL,
    kid: str = KID,
    alg: str = "RS256",
    claims: Mapping[str, Any] | None = None,
) -> str:
    """Mint a token signed with the stand-in primitive."""
    header = {"alg": alg, "kid": kid, "typ": "JWT"}
    body: dict[str, Any] = {
        "iss": ISSUER,
        "aud": AUDIENCE,
        "sub": "subject-abc",
        "iat": int((NOW - timedelta(minutes=1)).timestamp()),
        "exp": int((NOW + timedelta(minutes=30)).timestamp()),
    }
    if claims:
        body.update(claims)
        for key, value in claims.items():
            if value is None:
                body.pop(key, None)

    signing_input = (
        f"{_b64(json.dumps(header).encode())}.{_b64(json.dumps(body).encode())}"
    ).encode("ascii")
    signature = hmac.new(key_material.encode("utf-8"), signing_input, hashlib.sha256).digest()
    return f"{signing_input.decode('ascii')}.{_b64(signature)}"


@pytest.fixture
def verifier() -> JwksTokenVerifier:
    """A verifier holding one published key, with a frozen clock."""
    return JwksTokenVerifier(
        issuer=ISSUER,
        audience=AUDIENCE,
        jwks=StaticJwksSource(
            {KID: JsonWebKey(kid=KID, alg="RS256", material={"k": KEY_MATERIAL})}
        ),
        signature_verifier=StandInSignatureVerifier(),
        clock=lambda: NOW,
    )


def _live_env(**overrides: str) -> dict[str, str]:
    env = {
        ENABLED_ENV_VAR: "true",
        ISSUER_ENV_VAR: ISSUER,
        AUDIENCE_ENV_VAR: AUDIENCE,
        JWKS_URI_ENV_VAR: JWKS_URI,
    }
    env.update(overrides)
    return env


# ---------------------------------------------------------------------------
# 1. The flag is off by default, and off means byte-identical behaviour
# ---------------------------------------------------------------------------


def test_flag_absent_returns_the_existing_verifier_unchanged():
    """The passthrough is identity, not an equivalent object."""
    fixture = FixtureTokenVerifier()
    assert build_jwks_token_verifier(fixture, env={}) is fixture


@pytest.mark.parametrize("value", ["", "false", "0", "no", "off", "  ", "treu", "True-ish"])
def test_only_recognised_true_values_turn_the_flag_on(value: str):
    """Anything unrecognised — a typo included — leaves the flag off."""
    fixture = FixtureTokenVerifier()
    assert build_jwks_token_verifier(fixture, env={ENABLED_ENV_VAR: value}) is fixture


@pytest.mark.parametrize("value", ["1", "true", "TRUE", " yes ", "on"])
def test_recognised_true_values_turn_the_flag_on(value: str):
    settings = JwksVerifierSettings.from_env(_live_env(**{ENABLED_ENV_VAR: value}))
    assert settings.enabled is True


def test_flag_off_ignores_every_other_setting():
    """A half-configured environment with the flag off is not an error."""
    settings = JwksVerifierSettings.from_env({ISSUER_ENV_VAR: ISSUER})
    assert settings.enabled is False
    assert settings.issuer == ""


def test_the_fixture_path_still_verifies_its_own_tokens_with_the_flag_off():
    """The seam that ``tests/contract/test_me.py`` exercises is untouched."""
    fixture = FixtureTokenVerifier()
    fixture.register("tok", "sub-1", "person@example.edu")
    passthrough = build_jwks_token_verifier(fixture, env={})
    expected = VerifiedIdentity(subject="sub-1", email="person@example.edu")
    assert passthrough.verify("tok") == expected
    with pytest.raises(TokenVerificationError):
        passthrough.verify("not-registered")


# ---------------------------------------------------------------------------
# 2. Flag on, configuration missing: refuse to boot, never fall back
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("absent", [ISSUER_ENV_VAR, AUDIENCE_ENV_VAR, JWKS_URI_ENV_VAR])
def test_flag_on_without_required_configuration_is_a_startup_error(absent: str):
    env = _live_env()
    del env[absent]
    with pytest.raises(ProviderConfigurationError) as caught:
        JwksVerifierSettings.from_env(env)
    assert absent in str(caught.value)


def test_a_blank_required_value_counts_as_missing():
    with pytest.raises(ProviderConfigurationError):
        JwksVerifierSettings.from_env(_live_env(**{AUDIENCE_ENV_VAR: "   "}))


def test_the_error_names_every_missing_setting_at_once():
    with pytest.raises(ProviderConfigurationError) as caught:
        JwksVerifierSettings.from_env({ENABLED_ENV_VAR: "true"})
    message = str(caught.value)
    assert all(name in message for name in (ISSUER_ENV_VAR, AUDIENCE_ENV_VAR, JWKS_URI_ENV_VAR))


def test_no_endpoint_is_defaulted_anywhere():
    """The disabled settings carry empty strings, not a plausible placeholder."""
    settings = JwksVerifierSettings.from_env({})
    assert (settings.issuer, settings.audience, settings.jwks_uri) == ("", "", "")


def test_flag_on_without_a_signature_backend_refuses_rather_than_falling_back():
    fixture = FixtureTokenVerifier()
    with pytest.raises(ProviderConfigurationError) as caught:
        build_jwks_token_verifier(fixture, env=_live_env(), jwks=StaticJwksSource({}))
    assert "signature backend" in str(caught.value)


def test_flag_on_without_a_key_source_refuses():
    with pytest.raises(ProviderConfigurationError) as caught:
        build_jwks_token_verifier(
            FixtureTokenVerifier(),
            env=_live_env(),
            signature_verifier=StandInSignatureVerifier(),
        )
    assert "JWKS source" in str(caught.value)


def test_flag_on_with_everything_supplied_builds_the_live_verifier():
    built = build_jwks_token_verifier(
        FixtureTokenVerifier(),
        env=_live_env(**{LEEWAY_ENV_VAR: "5"}),
        jwks=StaticJwksSource(
            {KID: JsonWebKey(kid=KID, alg="RS256", material={"k": KEY_MATERIAL})}
        ),
        signature_verifier=StandInSignatureVerifier(),
        clock=lambda: NOW,
    )
    assert isinstance(built, JwksTokenVerifier)
    assert built.issuer == ISSUER
    assert built.audience == AUDIENCE
    assert built.leeway == timedelta(seconds=5)
    assert built.verify(_mint()).subject == "subject-abc"


@pytest.mark.parametrize("value", ["nonsense", "-1", "1.5"])
def test_an_unusable_leeway_is_a_startup_error(value: str):
    with pytest.raises(ProviderConfigurationError):
        JwksVerifierSettings.from_env(_live_env(**{LEEWAY_ENV_VAR: value}))


@pytest.mark.parametrize("value", ["none", "HS256", "RS256,none"])
def test_configuring_a_banned_algorithm_is_a_startup_error(value: str):
    with pytest.raises(ProviderConfigurationError) as caught:
        JwksVerifierSettings.from_env(_live_env(**{ALGORITHMS_ENV_VAR: value}))
    assert "never accepted" in str(caught.value)


# ---------------------------------------------------------------------------
# 3. A valid token verifies, and proves only subject and verified email
# ---------------------------------------------------------------------------


def test_a_valid_token_verifies(verifier: JwksTokenVerifier):
    assert verifier.verify(_mint()) == VerifiedIdentity(subject="subject-abc", email=None)


def test_a_verified_email_is_returned(verifier: JwksTokenVerifier):
    token = _mint(claims={"email": "person@example.edu", "email_verified": True})
    assert verifier.verify(token).email == "person@example.edu"


def test_an_unverified_email_is_dropped(verifier: JwksTokenVerifier):
    token = _mint(claims={"email": "person@example.edu", "email_verified": False})
    assert verifier.verify(token).email is None


def test_the_token_cannot_name_its_own_tenant_or_role(verifier: JwksTokenVerifier):
    """MM-A01 in JWT clothing: extra claims are not read and grant nothing."""
    identity = verifier.verify(
        _mint(claims={"tenant_id": "some-other-tenant", "role": "admin", "memberships": ["admin"]})
    )
    assert identity == VerifiedIdentity(subject="subject-abc", email=None)
    assert not hasattr(identity, "role")


def test_an_audience_array_containing_this_service_is_accepted(verifier: JwksTokenVerifier):
    assert verifier.verify(_mint(claims={"aud": ["other-service", AUDIENCE]})).subject


# ---------------------------------------------------------------------------
# 4. Every rejection path
# ---------------------------------------------------------------------------


def test_a_token_signed_with_the_wrong_key_is_rejected(verifier: JwksTokenVerifier):
    with pytest.raises(TokenVerificationError):
        verifier.verify(_mint(key_material="hmac-stand-in-key-wrong"))


def test_a_payload_edited_after_signing_is_rejected(verifier: JwksTokenVerifier):
    header, claims, signature = _mint().split(".")
    tampered = json.loads(base64.urlsafe_b64decode(claims + "=" * (-len(claims) % 4)))
    tampered["sub"] = "somebody-else"
    with pytest.raises(TokenVerificationError):
        verifier.verify(f"{header}.{_b64(json.dumps(tampered).encode())}.{signature}")


def test_an_expired_token_is_rejected(verifier: JwksTokenVerifier):
    expired = _mint(claims={"exp": int((NOW - timedelta(hours=1)).timestamp())})
    with pytest.raises(TokenVerificationError, match="expired"):
        verifier.verify(expired)


def test_expiry_is_tolerated_only_within_the_leeway(verifier: JwksTokenVerifier):
    just_inside = _mint(claims={"exp": int((NOW - timedelta(seconds=30)).timestamp())})
    assert verifier.verify(just_inside).subject == "subject-abc"
    just_outside = _mint(claims={"exp": int((NOW - timedelta(seconds=90)).timestamp())})
    with pytest.raises(TokenVerificationError, match="expired"):
        verifier.verify(just_outside)


def test_a_token_with_no_expiry_is_rejected(verifier: JwksTokenVerifier):
    with pytest.raises(TokenVerificationError, match="no expiry"):
        verifier.verify(_mint(claims={"exp": None}))


def test_a_token_issued_in_the_future_is_rejected(verifier: JwksTokenVerifier):
    with pytest.raises(TokenVerificationError):
        verifier.verify(_mint(claims={"iat": int((NOW + timedelta(hours=1)).timestamp())}))


def test_a_token_not_yet_valid_is_rejected(verifier: JwksTokenVerifier):
    with pytest.raises(TokenVerificationError, match="not valid yet"):
        verifier.verify(_mint(claims={"nbf": int((NOW + timedelta(hours=1)).timestamp())}))


def test_a_non_numeric_date_claim_is_rejected_rather_than_skipped(verifier: JwksTokenVerifier):
    with pytest.raises(TokenVerificationError, match="not a number"):
        verifier.verify(_mint(claims={"exp": "soon"}))


def test_a_token_from_another_issuer_is_rejected(verifier: JwksTokenVerifier):
    with pytest.raises(TokenVerificationError, match="issuer"):
        verifier.verify(_mint(claims={"iss": "https://other-issuer.test.invalid/"}))


def test_a_token_with_no_issuer_is_rejected(verifier: JwksTokenVerifier):
    with pytest.raises(TokenVerificationError, match="issuer"):
        verifier.verify(_mint(claims={"iss": None}))


def test_a_token_for_another_audience_is_rejected(verifier: JwksTokenVerifier):
    with pytest.raises(TokenVerificationError, match="audience"):
        verifier.verify(_mint(claims={"aud": "some-other-service"}))


def test_an_audience_array_without_this_service_is_rejected(verifier: JwksTokenVerifier):
    with pytest.raises(TokenVerificationError, match="audience"):
        verifier.verify(_mint(claims={"aud": ["a", "b"]}))


def test_a_token_signed_with_an_unknown_key_id_is_rejected(verifier: JwksTokenVerifier):
    """Rotation: a key this process has not published is not a trusted key."""
    with pytest.raises(TokenVerificationError, match="no published key"):
        verifier.verify(_mint(kid="key-2"))


def test_a_rotated_key_verifies_once_the_source_publishes_it():
    """The same token that was rejected verifies against a refreshed source."""
    rotated = JwksTokenVerifier(
        issuer=ISSUER,
        audience=AUDIENCE,
        jwks=StaticJwksSource(
            {
                KID: JsonWebKey(kid=KID, alg="RS256", material={"k": KEY_MATERIAL}),
                "key-2": JsonWebKey(
                    kid="key-2", alg="RS256", material={"k": "hmac-stand-in-key-two"}
                ),
            }
        ),
        signature_verifier=StandInSignatureVerifier(),
        clock=lambda: NOW,
    )
    assert (
        rotated.verify(_mint(kid="key-2", key_material="hmac-stand-in-key-two")).subject
        == "subject-abc"
    )


def test_a_token_with_no_key_id_is_rejected(verifier: JwksTokenVerifier):
    with pytest.raises(TokenVerificationError, match="key id"):
        verifier.verify(_mint(kid=""))


@pytest.mark.parametrize("algorithm", ["none", "HS256", "hs256", "dir"])
def test_a_banned_algorithm_is_rejected(verifier: JwksTokenVerifier, algorithm: str):
    with pytest.raises(TokenVerificationError, match="never accepted"):
        verifier.verify(_mint(alg=algorithm))


def test_an_algorithm_the_key_was_not_published_for_is_rejected():
    """The key decides which algorithm verifies it, not the token header."""
    mismatched = JwksTokenVerifier(
        issuer=ISSUER,
        audience=AUDIENCE,
        jwks=StaticJwksSource(
            {KID: JsonWebKey(kid=KID, alg="RS512", material={"k": KEY_MATERIAL})}
        ),
        signature_verifier=StandInSignatureVerifier(),
        clock=lambda: NOW,
    )
    with pytest.raises(TokenVerificationError, match="disagrees"):
        mismatched.verify(_mint())


def test_an_unconfigured_algorithm_is_rejected(verifier: JwksTokenVerifier):
    with pytest.raises(TokenVerificationError, match="not configured"):
        verifier.verify(_mint(alg="RS512"))


def test_a_token_with_no_subject_is_rejected(verifier: JwksTokenVerifier):
    with pytest.raises(TokenVerificationError, match="no subject"):
        verifier.verify(_mint(claims={"sub": "   "}))


@pytest.mark.parametrize(
    "token",
    ["", "   ", "not-a-jwt", "only.two", "a.b.c.d", "!!!.@@@.###", "x" * 9000],
    ids=["empty", "blank", "single", "two-parts", "four-parts", "not-base64", "oversized"],
)
def test_a_malformed_token_is_rejected(verifier: JwksTokenVerifier, token: str):
    with pytest.raises(TokenVerificationError):
        verifier.verify(token)


def test_a_json_array_body_is_rejected(verifier: JwksTokenVerifier):
    header = _b64(json.dumps({"alg": "RS256", "kid": KID}).encode())
    body = _b64(json.dumps(["not", "an", "object"]).encode())
    with pytest.raises(TokenVerificationError, match="JSON object"):
        verifier.verify(f"{header}.{body}.{_b64(b'sig')}")


def test_a_backend_raising_something_of_its_own_is_still_a_rejection():
    """Never a 500 a caller could use to tell tokens apart."""

    @dataclass(frozen=True)
    class ExplodingBackend:
        algorithms: frozenset[str] = frozenset({"RS256"})

        def verify(self, *, signing_input: bytes, signature: bytes, key: JsonWebKey) -> None:
            raise RuntimeError("the backend exploded")

    exploding = JwksTokenVerifier(
        issuer=ISSUER,
        audience=AUDIENCE,
        jwks=StaticJwksSource(
            {KID: JsonWebKey(kid=KID, alg="RS256", material={"k": KEY_MATERIAL})}
        ),
        signature_verifier=ExplodingBackend(),
        clock=lambda: NOW,
    )
    with pytest.raises(TokenVerificationError):
        exploding.verify(_mint())


def test_an_empty_key_source_rejects_every_token():
    empty = JwksTokenVerifier(
        issuer=ISSUER,
        audience=AUDIENCE,
        jwks=StaticJwksSource(),
        signature_verifier=StandInSignatureVerifier(),
        clock=lambda: NOW,
    )
    with pytest.raises(TokenVerificationError):
        empty.verify(_mint())
