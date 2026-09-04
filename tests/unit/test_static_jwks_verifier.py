"""Unit tests for the isolated JWKS/JWT verifier core.

Two jobs. First, prove the verifier actually verifies: a token signed by a
synthetic test key is accepted, and every way a token can fail — missing
``kid``, wrong ``alg``, tampered payload, wrong key, absent or past ``exp``,
mismatched ``iss`` or ``aud`` — is refused. Second, prove the *isolation*
claims that let this land before the A1b stop-gate is cleared: the module has
no network client, cannot be pointed at a live Google issuer, is not exported
from the package, and is not reachable from ``smartmatch_api``.

All key material here is synthetic, generated for this test file and used
nowhere else. The private halves exist only so a test can produce a signature;
the module under test never sees them. No value in this file is copied from
``docs/decisions/a1b-idp-configuration-worksheet.md`` — the issuer and audience
below are obvious test literals, and the worksheet's fields remain unfilled.
"""

from __future__ import annotations

import ast
import base64
import hashlib
import json
import time
from pathlib import Path
from typing import Any

import pytest
from smartmatch_providers.base import ProviderConfigurationError
from smartmatch_providers.identity import TokenVerificationError, TokenVerifier, VerifiedIdentity
from smartmatch_providers.jwks import (
    BLOCKED_ISSUER_HOSTS,
    RSAPublicJWK,
    StaticJWKS,
    StaticJWKSTokenVerifier,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = REPO_ROOT / "python" / "smartmatch_providers" / "smartmatch_providers" / "jwks.py"

# ---------------------------------------------------------------------------
# Synthetic test keys. Generated for this file; not a credential of any system.
# ---------------------------------------------------------------------------


def _hex_int(*chunks: str) -> int:
    """Reassemble a hex literal split across lines to stay within the line limit."""
    return int("".join(chunks), 16)


_TEST_KEY_N = _hex_int(
    "c88ecd252af500a32738aad7f7b7f5aae2a5b2d8748e6e84abf38d2d72153060"
    "334d4773c31243345b62552599d766183a3ec3881d9dd9838c6c94f52c086d6e"
    "ee4e80a3cd9390784b19f3a177878367080a4e39dc76980293e7a5fa33656af8"
    "10064e5e2e43bb386f2455e5c6fbc49b3d816dd5b367c98f65c44ffbb65de79b"
    "0d3df65936e2bd23c50184be0b523e4df1ff149c3a9049df321d8694ba3324df"
    "a386f4f70e6b42eadc515a2470d357f9fe93adc8f3c7f62439d2d06720aa1dce"
    "8aa0eec0a6d62e00324aadab42ba083f5889a027eb185e93ca9b21bf48919833"
    "483397ae45d83013ee75ca6b64ee014efe5a723500056f5cd9ac550989460d93"
)
_TEST_KEY_D = _hex_int(
    "2a61268f528ef80601dd3318b4d34e19c08fe4056247d0a9bf4e154883a15f9a"
    "0c6d298a982f6d3d0c8c7052a43a046c5d2e7311f9b427c8e8eceee309dd7406"
    "6b5bf249eac062585102585d87ccfe62d0aba0d110398d308a417a6caedca0e8"
    "6f366debefd9c71f8b38c1dfee96b7fa57da5833be97d15b38556dd3523b709b"
    "8e567959db48e1c338f362b9b53292336c276f25ae29bd81e313ccf4f8883bb9"
    "72155cc085fd179dd5b7a51e43dccb8725162315bfc841f83be623855dcfb4a3"
    "9e7f6df1766c590187c03ad35c28ecf3fd3a07f44630d0e1e5d94d1bead1f65b"
    "bf5481e060648a5e9683e6b9f632a7eabd020e0d44e2e615564f1072a66dc9e5"
)

_OTHER_KEY_N = _hex_int(
    "d3461881523b6414a3b5f0aaa0d927bb9d57ef1af919753813febfe12417bb87"
    "ad4f3aebe5d273675856f444e9db0859b4664cb80433f046971d04c6954f70d2"
    "d493ecce3b4250194b8629b9b25c07838a611d46e3a4292c356dcf8a00203949"
    "4b887baceaf599e1373336600216fb353525c5d7d4e128122a038d2e84c2eb1b"
    "cd99b0a75be92071d4e2d5d3bec7b0207e5cc097f55dcc9b9ef4b78e213e9ea6"
    "176f9c5e8b9b038007370aee62953ae76dbf29165a933a06b93b2a09fc269b5b"
    "2bf368ff70b45d7db9b2a67aa39362e07143b57747d1f2a934e2fbf9a6500d39"
    "7cb7376161e5004f834fbf993b293bf692450d6b009a9e5679d4f9e0410bddaf"
)
_OTHER_KEY_D = _hex_int(
    "51f7df9908e0eef6ccff5134b9fc165cc57270db8baa935e62ef92dd5425fb05"
    "6c399198254dcda55a523e2a207af0d5f0d641cca120cf876ba8800a55b28108"
    "e31dd321be3eff9998c2201d22346f5bdb0bcb928dce4a8512e39c4223c35cc6"
    "718e2dc18c552653091a0eee17d177bc10772bb78da99f64d0b51908e3cc45ef"
    "8a92b5af9ee678c97840afc1f4e937bbf082479304b0c6283c8118326e6e6823"
    "d1f8665b3da354c561821d54d0512118508b9eb65adecc2ac972f1c49037e8a3"
    "57ce9befc8457d44c53327c9d7058b7c29e66a7a7e9c387f6909fed03c6ed349"
    "7ce40517983cb28e06ec773b8f079a98d0aaa7b0f315f44a214b2eb8751e4abd"
)

_TEST_KEY_E = 65537
_TEST_KID = "test-key-1"
_OTHER_KID = "test-key-2"

#: Test literals, not configuration. Deliberately not URLs of anything real.
ISSUER = "https://issuer.invalid/smartmatch-test"
AUDIENCE = "smartmatch-test-audience"

#: A fixed instant, so expiry is a property of the token rather than of when
#: the suite happens to run.
NOW = 1_800_000_000.0

_SHA256_DIGEST_INFO = bytes.fromhex("3031300d060960864801650304020105000420")


def _b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _b64url_json(value: Any) -> str:
    return _b64url(json.dumps(value, separators=(",", ":"), sort_keys=True).encode("utf-8"))


def _sign(signing_input: bytes, modulus: int, private_exponent: int) -> bytes:
    """Produce an RSASSA-PKCS1-v1_5 SHA-256 signature with a synthetic key.

    Test-side only: the module under test holds no private material. Written
    out here rather than pulled from a library because the hash-locked runtime
    carries no JOSE or crypto dependency, and this scaffold must not add one.
    """
    modulus_bytes = (modulus.bit_length() + 7) // 8
    digest_info = _SHA256_DIGEST_INFO + hashlib.sha256(signing_input).digest()
    padding = b"\xff" * (modulus_bytes - len(digest_info) - 3)
    encoded = b"\x00\x01" + padding + b"\x00" + digest_info
    signature = pow(int.from_bytes(encoded, "big"), private_exponent, modulus)
    return signature.to_bytes(modulus_bytes, "big")


def make_token(
    *,
    claims: dict[str, Any] | None = None,
    header: dict[str, Any] | None = None,
    modulus: int = _TEST_KEY_N,
    private_exponent: int = _TEST_KEY_D,
) -> str:
    """Build a signed compact JWS, with sensible defaults for these tests.

    A ``None`` value in ``claims`` or ``header`` *removes* that member, which is
    how the "missing kid" and "missing exp" cases are expressed.
    """
    full_header: dict[str, Any] = {"alg": "RS256", "typ": "JWT", "kid": _TEST_KID}
    if header is not None:
        full_header = {**full_header, **header}
        for key, value in header.items():
            if value is None:
                full_header.pop(key, None)
    full_claims: dict[str, Any] = {
        "sub": "subject-abc",
        "iss": ISSUER,
        "aud": AUDIENCE,
        "iat": NOW - 60,
        "exp": NOW + 600,
    }
    if claims is not None:
        full_claims = {**full_claims, **claims}
        for key, value in claims.items():
            if value is None:
                full_claims.pop(key, None)

    header_b64 = _b64url_json(full_header)
    payload_b64 = _b64url_json(full_claims)
    signing_input = f"{header_b64}.{payload_b64}".encode("ascii")
    signature = _sign(signing_input, modulus, private_exponent)
    return f"{header_b64}.{payload_b64}.{_b64url(signature)}"


@pytest.fixture
def key_set() -> StaticJWKS:
    """A two-key set, so "wrong key" is distinguishable from "unknown kid"."""
    return StaticJWKS.from_keys(
        [
            RSAPublicJWK(kid=_TEST_KID, modulus=_TEST_KEY_N, exponent=_TEST_KEY_E),
            RSAPublicJWK(kid=_OTHER_KID, modulus=_OTHER_KEY_N, exponent=_TEST_KEY_E),
        ]
    )


@pytest.fixture
def verifier(key_set: StaticJWKS) -> StaticJWKSTokenVerifier:
    return StaticJWKSTokenVerifier(
        keys=key_set,
        issuer=ISSUER,
        audience=AUDIENCE,
        now=lambda: NOW,
    )


# ---------------------------------------------------------------------------
# Acceptance: a correctly signed token verifies, and proves only identity.
# ---------------------------------------------------------------------------


def test_verifies_a_token_signed_by_a_known_key(verifier: StaticJWKSTokenVerifier) -> None:
    identity = verifier.verify(make_token())
    assert identity == VerifiedIdentity(subject="subject-abc", email=None)


def test_returns_email_when_the_token_carries_one(verifier: StaticJWKSTokenVerifier) -> None:
    identity = verifier.verify(make_token(claims={"email": "someone@example.invalid"}))
    assert identity.subject == "subject-abc"
    assert identity.email == "someone@example.invalid"


def test_satisfies_the_token_verifier_protocol(verifier: StaticJWKSTokenVerifier) -> None:
    assert isinstance(verifier, TokenVerifier)


def test_ignores_tenant_role_and_permission_claims(verifier: StaticJWKSTokenVerifier) -> None:
    """A token cannot name its own tenant, role, or permissions.

    The rule from :mod:`smartmatch_providers.identity`: identity comes from the
    token, authorization comes from the server. A token asserting
    ``role: admin`` must verify as nothing more than its subject.
    """
    token = make_token(
        claims={
            "tenant_id": "tenant-attacker",
            "org": "tenant-attacker",
            "role": "admin",
            "roles": ["admin", "owner"],
            "permissions": ["*"],
            "scope": "admin",
        }
    )
    identity = verifier.verify(token)
    assert identity == VerifiedIdentity(subject="subject-abc", email=None)
    assert VerifiedIdentity.__slots__ == ("subject", "email")


def test_the_default_clock_is_the_wall_clock(key_set: StaticJWKS) -> None:
    """Every other test injects a clock; this one exercises the default path.

    Worth its own test because the default is a dataclass class attribute: a
    plain Python function there would bind as a method and be called with
    ``self``. ``time.time`` is a builtin and does not, but that is a property of
    the default rather than of the code, so it is pinned here.
    """
    verifier = StaticJWKSTokenVerifier(keys=key_set, issuer=ISSUER, audience=AUDIENCE)
    now = time.time()
    assert verifier.verify(make_token(claims={"iat": now, "exp": now + 600})).subject == (
        "subject-abc"
    )
    with pytest.raises(TokenVerificationError):
        verifier.verify(make_token(claims={"iat": now - 600, "exp": now - 1}))


def test_accepts_a_list_audience_containing_the_configured_one(
    verifier: StaticJWKSTokenVerifier,
) -> None:
    identity = verifier.verify(make_token(claims={"aud": ["other-audience", AUDIENCE]}))
    assert identity.subject == "subject-abc"


def test_accepts_the_second_key_in_the_set(key_set: StaticJWKS) -> None:
    """Rotation works: a token names its key, and either key in the set is fine."""
    verifier = StaticJWKSTokenVerifier(
        keys=key_set, issuer=ISSUER, audience=AUDIENCE, now=lambda: NOW
    )
    token = make_token(
        header={"kid": _OTHER_KID}, modulus=_OTHER_KEY_N, private_exponent=_OTHER_KEY_D
    )
    assert verifier.verify(token).subject == "subject-abc"


# ---------------------------------------------------------------------------
# Refusal: header and signature.
# ---------------------------------------------------------------------------


def test_refuses_a_token_with_no_kid(verifier: StaticJWKSTokenVerifier) -> None:
    with pytest.raises(TokenVerificationError):
        verifier.verify(make_token(header={"kid": None}))


def test_refuses_a_token_with_an_empty_kid(verifier: StaticJWKSTokenVerifier) -> None:
    with pytest.raises(TokenVerificationError):
        verifier.verify(make_token(header={"kid": ""}))


def test_refuses_a_token_naming_an_unknown_kid(verifier: StaticJWKSTokenVerifier) -> None:
    with pytest.raises(TokenVerificationError):
        verifier.verify(make_token(header={"kid": "not-in-the-key-set"}))


@pytest.mark.parametrize("alg", ["none", "None", "HS256", "RS512", "rs256", "ES256", ""])
def test_refuses_a_token_whose_alg_is_not_rs256(
    verifier: StaticJWKSTokenVerifier, alg: str
) -> None:
    with pytest.raises(TokenVerificationError):
        verifier.verify(make_token(header={"alg": alg}))


def test_refuses_an_unsigned_alg_none_token(verifier: StaticJWKSTokenVerifier) -> None:
    """The classic forgery: valid-looking claims, no signature at all."""
    header_b64 = _b64url_json({"alg": "none", "typ": "JWT", "kid": _TEST_KID})
    payload_b64 = _b64url_json(
        {"sub": "subject-abc", "iss": ISSUER, "aud": AUDIENCE, "exp": NOW + 600}
    )
    with pytest.raises(TokenVerificationError):
        verifier.verify(f"{header_b64}.{payload_b64}.")


def test_refuses_a_token_with_a_missing_alg(verifier: StaticJWKSTokenVerifier) -> None:
    with pytest.raises(TokenVerificationError):
        verifier.verify(make_token(header={"alg": None}))


def test_refuses_a_token_signed_by_a_key_not_matching_its_kid(
    verifier: StaticJWKSTokenVerifier,
) -> None:
    """Signed with key two, but claiming key one. The signature must not check out."""
    token = make_token(modulus=_OTHER_KEY_N, private_exponent=_OTHER_KEY_D)
    with pytest.raises(TokenVerificationError):
        verifier.verify(token)


def test_refuses_a_token_whose_payload_was_swapped_after_signing(
    verifier: StaticJWKSTokenVerifier,
) -> None:
    header_b64, _, signature_b64 = make_token().split(".")
    forged_payload = _b64url_json(
        {"sub": "someone-else", "iss": ISSUER, "aud": AUDIENCE, "exp": NOW + 600}
    )
    with pytest.raises(TokenVerificationError):
        verifier.verify(f"{header_b64}.{forged_payload}.{signature_b64}")


def test_refuses_a_token_with_a_truncated_signature(verifier: StaticJWKSTokenVerifier) -> None:
    header_b64, payload_b64, signature_b64 = make_token().split(".")
    with pytest.raises(TokenVerificationError):
        verifier.verify(f"{header_b64}.{payload_b64}.{signature_b64[:-4]}")


@pytest.mark.parametrize("token", ["", "not-a-token", "a.b", "a.b.c.d", "....", "a..c", ".b.c"])
def test_refuses_a_malformed_token(verifier: StaticJWKSTokenVerifier, token: str) -> None:
    with pytest.raises(TokenVerificationError):
        verifier.verify(token)


def test_refuses_a_token_with_an_unrecognised_typ(verifier: StaticJWKSTokenVerifier) -> None:
    with pytest.raises(TokenVerificationError):
        verifier.verify(make_token(header={"typ": "not-a-jwt"}))


def test_refuses_a_token_with_a_crit_header(verifier: StaticJWKSTokenVerifier) -> None:
    """``crit`` names extensions that must be understood. This verifier understands none."""
    with pytest.raises(TokenVerificationError):
        verifier.verify(make_token(header={"crit": ["exp"]}))


# ---------------------------------------------------------------------------
# Refusal: claims.
# ---------------------------------------------------------------------------


def test_refuses_a_token_with_no_exp(verifier: StaticJWKSTokenVerifier) -> None:
    with pytest.raises(TokenVerificationError):
        verifier.verify(make_token(claims={"exp": None}))


@pytest.mark.parametrize("exp", ["1800000600", True, [], {}, "soon"])
def test_refuses_a_token_with_a_non_numeric_exp(
    verifier: StaticJWKSTokenVerifier, exp: Any
) -> None:
    with pytest.raises(TokenVerificationError):
        verifier.verify(make_token(claims={"exp": exp}))


def test_refuses_an_expired_token(verifier: StaticJWKSTokenVerifier) -> None:
    with pytest.raises(TokenVerificationError):
        verifier.verify(make_token(claims={"exp": NOW - 1}))


def test_refuses_a_token_expiring_exactly_now(verifier: StaticJWKSTokenVerifier) -> None:
    """The boundary belongs to the past: ``exp`` is the first instant of invalidity."""
    with pytest.raises(TokenVerificationError):
        verifier.verify(make_token(claims={"exp": NOW}))


def test_accepts_a_recently_expired_token_within_the_configured_leeway(
    key_set: StaticJWKS,
) -> None:
    """Skew tolerance is a constructor argument, never a default that drifts in."""
    lenient = StaticJWKSTokenVerifier(
        keys=key_set, issuer=ISSUER, audience=AUDIENCE, leeway_seconds=120, now=lambda: NOW
    )
    assert lenient.verify(make_token(claims={"exp": NOW - 30})).subject == "subject-abc"
    with pytest.raises(TokenVerificationError):
        lenient.verify(make_token(claims={"exp": NOW - 300}))


def test_refuses_a_token_that_is_not_yet_valid(verifier: StaticJWKSTokenVerifier) -> None:
    with pytest.raises(TokenVerificationError):
        verifier.verify(make_token(claims={"nbf": NOW + 60}))


def test_refuses_a_token_with_a_non_numeric_iat(verifier: StaticJWKSTokenVerifier) -> None:
    with pytest.raises(TokenVerificationError):
        verifier.verify(make_token(claims={"iat": "yesterday"}))


@pytest.mark.parametrize(
    "issuer",
    [
        "https://issuer.invalid/other",
        "https://issuer.invalid/smartmatch-test/",
        "issuer.invalid/smartmatch-test",
        "",
    ],
)
def test_refuses_a_token_from_a_different_issuer(
    verifier: StaticJWKSTokenVerifier, issuer: str
) -> None:
    with pytest.raises(TokenVerificationError):
        verifier.verify(make_token(claims={"iss": issuer}))


def test_refuses_a_token_with_no_issuer(verifier: StaticJWKSTokenVerifier) -> None:
    with pytest.raises(TokenVerificationError):
        verifier.verify(make_token(claims={"iss": None}))


@pytest.mark.parametrize("audience", ["other-audience", ["other-audience"], [], 7, [AUDIENCE, 7]])
def test_refuses_a_token_for_a_different_audience(
    verifier: StaticJWKSTokenVerifier, audience: Any
) -> None:
    with pytest.raises(TokenVerificationError):
        verifier.verify(make_token(claims={"aud": audience}))


def test_refuses_a_token_with_no_audience(verifier: StaticJWKSTokenVerifier) -> None:
    with pytest.raises(TokenVerificationError):
        verifier.verify(make_token(claims={"aud": None}))


@pytest.mark.parametrize("subject", ["", 42, ["subject-abc"]])
def test_refuses_a_token_without_a_usable_subject(
    verifier: StaticJWKSTokenVerifier, subject: Any
) -> None:
    with pytest.raises(TokenVerificationError):
        verifier.verify(make_token(claims={"sub": subject}))


def test_refuses_a_token_with_no_subject(verifier: StaticJWKSTokenVerifier) -> None:
    with pytest.raises(TokenVerificationError):
        verifier.verify(make_token(claims={"sub": None}))


def test_refuses_a_token_whose_email_is_not_a_string(verifier: StaticJWKSTokenVerifier) -> None:
    with pytest.raises(TokenVerificationError):
        verifier.verify(make_token(claims={"email": 1234}))


def test_the_failure_message_does_not_say_which_check_failed(
    verifier: StaticJWKSTokenVerifier,
) -> None:
    """Telling an attacker a token merely expired says which forgeries are worth trying."""
    messages = set()
    for token in (
        make_token(claims={"exp": NOW - 1}),
        make_token(claims={"iss": "https://issuer.invalid/other"}),
        make_token(modulus=_OTHER_KEY_N, private_exponent=_OTHER_KEY_D),
    ):
        with pytest.raises(TokenVerificationError) as caught:
            verifier.verify(token)
        messages.add(str(caught.value))
    assert messages == {"token is not valid"}


# ---------------------------------------------------------------------------
# Configuration: static key sets only, and never a live issuer.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "issuer",
    [
        "https://securetoken.google.com/some-project",
        "https://accounts.google.com",
        "https://identitytoolkit.googleapis.com/v1",
        "https://oauth2.googleapis.com",
        "https://SecureToken.Google.com/some-project",
        "securetoken.google.com",
        "https://securetoken.google.com.",
        "https://sub.domain.securetoken.google.com/x",
        "https://login.microsoftonline.com/common/v2.0",
    ],
)
def test_refuses_to_be_constructed_with_a_live_issuer(key_set: StaticJWKS, issuer: str) -> None:
    """The scaffold cannot be pointed at a hosted IdP, in any casing or subdomain."""
    with pytest.raises(ProviderConfigurationError):
        StaticJWKSTokenVerifier(keys=key_set, issuer=issuer, audience=AUDIENCE)


def test_blocked_issuer_hosts_covers_google_identity_platform() -> None:
    assert "securetoken.google.com" in BLOCKED_ISSUER_HOSTS
    assert "accounts.google.com" in BLOCKED_ISSUER_HOSTS


def test_refuses_an_empty_issuer_or_audience(key_set: StaticJWKS) -> None:
    with pytest.raises(ProviderConfigurationError):
        StaticJWKSTokenVerifier(keys=key_set, issuer="", audience=AUDIENCE)
    with pytest.raises(ProviderConfigurationError):
        StaticJWKSTokenVerifier(keys=key_set, issuer=ISSUER, audience="")


def test_refuses_a_negative_leeway(key_set: StaticJWKS) -> None:
    with pytest.raises(ProviderConfigurationError):
        StaticJWKSTokenVerifier(keys=key_set, issuer=ISSUER, audience=AUDIENCE, leeway_seconds=-1)


def test_the_constructor_takes_a_key_set_not_a_url() -> None:
    """No discovery URL, no JWKS URI, no cache TTL — the keys are already here.

    Those are exactly the fields the A1b worksheet leaves outstanding. A
    constructor that accepted them would need values this repository does not
    have, and inventing one is the failure the worksheet exists to prevent.
    """
    fields = set(StaticJWKSTokenVerifier.__dataclass_fields__)
    assert fields == {"keys", "issuer", "audience", "leeway_seconds", "now", "name"}
    for forbidden in ("url", "uri", "endpoint", "discovery", "http", "client"):
        assert not any(forbidden in field for field in fields)


def test_builds_a_key_set_from_a_parsed_jwks_document() -> None:
    """The JWKS shape is supported — as an already-parsed mapping, never a fetch."""
    document = {
        "keys": [
            {
                "kty": "RSA",
                "use": "sig",
                "alg": "RS256",
                "kid": _TEST_KID,
                "n": _b64url(_TEST_KEY_N.to_bytes(256, "big")),
                "e": _b64url(_TEST_KEY_E.to_bytes(3, "big")),
            }
        ]
    }
    keys = StaticJWKS.from_jwks_document(document)
    built = StaticJWKSTokenVerifier(keys=keys, issuer=ISSUER, audience=AUDIENCE, now=lambda: NOW)
    assert built.verify(make_token()).subject == "subject-abc"


@pytest.mark.parametrize(
    "jwk",
    [
        {"kty": "oct", "kid": "k", "n": "AQ", "e": "AQAB"},
        {"kty": "RSA", "alg": "HS256", "kid": "k", "n": "AQ", "e": "AQAB"},
        {"kty": "RSA", "use": "enc", "kid": "k", "n": "AQ", "e": "AQAB"},
        {"kty": "RSA", "kid": 5, "n": "AQ", "e": "AQAB"},
        {"kty": "RSA", "kid": "k", "n": "", "e": "AQAB"},
    ],
)
def test_rejects_a_jwks_key_that_is_not_an_rs256_rsa_public_key(jwk: dict[str, Any]) -> None:
    with pytest.raises(ProviderConfigurationError):
        StaticJWKS.from_jwks_document({"keys": [jwk]})


def test_rejects_an_empty_or_malformed_key_set() -> None:
    with pytest.raises(ProviderConfigurationError):
        StaticJWKS.from_keys([])
    with pytest.raises(ProviderConfigurationError):
        StaticJWKS.from_jwks_document({})
    with pytest.raises(ProviderConfigurationError):
        StaticJWKS.from_keys(
            [
                RSAPublicJWK(kid=_TEST_KID, modulus=_TEST_KEY_N, exponent=_TEST_KEY_E),
                RSAPublicJWK(kid=_TEST_KID, modulus=_OTHER_KEY_N, exponent=_TEST_KEY_E),
            ]
        )


def test_rejects_an_undersized_or_malformed_key() -> None:
    with pytest.raises(ProviderConfigurationError):
        RSAPublicJWK(kid="small", modulus=3233, exponent=17)
    with pytest.raises(ProviderConfigurationError):
        RSAPublicJWK(kid="", modulus=_TEST_KEY_N, exponent=_TEST_KEY_E)
    with pytest.raises(ProviderConfigurationError):
        RSAPublicJWK(kid="even-exponent", modulus=_TEST_KEY_N, exponent=4)


# ---------------------------------------------------------------------------
# Isolation guards — structural, so the scaffold cannot quietly become wired.
# ---------------------------------------------------------------------------

_NETWORK_MODULE_ROOTS = frozenset(
    {
        "httpx",
        "requests",
        "urllib",
        "http",
        "socket",
        "ssl",
        "aiohttp",
        "google",
        "firebase_admin",
        "smartmatch_api",
        "smartmatch_worker",
    }
)


def _imported_modules(path: Path) -> set[str]:
    """Every module name imported by one source file, from its AST."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            names.add(node.module)
    return names


def test_the_verifier_module_imports_no_network_client() -> None:
    """It cannot fetch a JWKS because it has nothing to fetch with.

    ``urllib.parse`` is allowed — it splits a string to check a hostname and
    opens nothing. ``urllib.request`` is not.
    """
    for module in _imported_modules(MODULE_PATH):
        if module == "urllib.parse":
            continue
        root = module.split(".")[0]
        assert root not in _NETWORK_MODULE_ROOTS, f"{module} must not be imported here"


def test_smartmatch_api_does_not_import_the_verifier_module() -> None:
    """The wiring test. ``FixtureTokenVerifier`` stays what the API uses.

    Checked statically over every module under ``services/api`` rather than via
    ``sys.modules``, because this very test file imports the module.
    """
    api_root = REPO_ROOT / "services" / "api"
    offenders = [
        str(path.relative_to(REPO_ROOT))
        for path in sorted(api_root.rglob("*.py"))
        if "smartmatch_providers.jwks" in path.read_text(encoding="utf-8")
        or "StaticJWKSTokenVerifier" in path.read_text(encoding="utf-8")
    ]
    assert offenders == [], f"the unwired scaffold is referenced by: {offenders}"


def test_the_api_still_builds_a_fixture_verifier() -> None:
    """The other half of the wiring test: what main uses has not changed."""
    main_source = (REPO_ROOT / "services" / "api" / "smartmatch_api" / "main.py").read_text(
        encoding="utf-8"
    )
    assert "build_token_verifier" in main_source


def test_the_verifier_is_not_exported_from_the_providers_package() -> None:
    """Not re-exported, so importing the package does not drag the scaffold in.

    An unwired module that every importer of ``smartmatch_providers`` loads is
    only nominally unwired.
    """
    source = (MODULE_PATH.parent / "__init__.py").read_text(encoding="utf-8")
    assert "jwks" not in source
    assert "StaticJWKS" not in source


def test_api_settings_have_no_jwks_or_issuer_fields() -> None:
    """A1 is blocked, so ``SMARTMATCH_JWKS_*`` and friends must not exist yet."""
    from smartmatch_api.config import Settings

    for field in Settings.model_fields:
        lowered = field.lower()
        assert "jwks" not in lowered
        assert "issuer" not in lowered
        assert "audience" not in lowered


def test_no_live_issuer_is_baked_into_the_module_as_a_value() -> None:
    """The scaffold names no real issuer, audience, JWKS URI, or client ID.

    The blocklist does mention live hostnames — that is what a blocklist is —
    so this guard checks none of them appears as a URL or a default instead.
    """
    source = MODULE_PATH.read_text(encoding="utf-8")
    for host in BLOCKED_ISSUER_HOSTS:
        assert f"https://{host}" not in source
        assert f'= "{host}"' not in source
