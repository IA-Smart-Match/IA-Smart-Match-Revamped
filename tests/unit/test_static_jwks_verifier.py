"""Unit tests for the isolated JWKS/JWT verifier core.

Two jobs. First, prove the verifier actually verifies: a token signed by a
synthetic test key is accepted, and every way a token can fail — missing
``kid``, wrong ``alg``, tampered payload, wrong key, absent or past ``exp``,
``nbf`` in the future, mismatched ``iss`` or ``aud`` — is refused. Second,
prove the *isolation* claims that let this land before the A1b stop-gate is
cleared: the module has no network client, cannot be pointed at a live Google
issuer, is not exported from the package, is not reachable from
``smartmatch_api``, and adds no ``/v1`` route to the published contract.

All key material here is generated at import time by :mod:`cryptography` and
lives only in this process. Nothing is committed: no modulus, no exponent, no
PEM block, no pre-baked signed token. A long high-entropy literal in a test
file is indistinguishable — to a secret scanner, and to a reader skimming a
diff — from a credential that leaked, and generating throwaway keys removes the
literal rather than teaching a scanner to ignore one.

No value here is copied from ``docs/decisions/a1b-idp-configuration-worksheet.md``
— the issuer and audience below are obvious test literals, and the worksheet's
fields remain unfilled.
"""

from __future__ import annotations

import ast
import base64
import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from smartmatch_providers import jwks as scaffold
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

#: Test literals, not configuration. Deliberately not identifiers of anything
#: real: ``.invalid`` can never resolve, by RFC 2606.
ISSUER = "https://issuer.invalid/smartmatch-test"
AUDIENCE = "smartmatch-test-audience"

#: A fixed instant, so expiry is a property of the token rather than of when
#: the suite happens to run.
NOW = 1_800_000_000.0

#: Key identifiers for the two synthetic signers. Written out so a test can
#: name a ``kid`` *independently* of the object that signs — which is the whole
#: point of the mismatch test below.
FIRST_KID = "test-kid-1"
SECOND_KID = "test-kid-2"


@dataclass(frozen=True)
class _Signer:
    """A throwaway RSA signer, generated for this process and used nowhere else.

    It holds no ``kid``. An earlier draft bundled one in, and the "signed by a
    different key than it names" test then quietly signed *and* labelled with
    the same signer — it passed while proving nothing. Keeping the label out of
    the signer forces every call site to say which ``kid`` it is claiming.
    """

    private: rsa.RSAPrivateKey

    def sign(self, signing_input: bytes) -> bytes:
        """Sign the JWS signing input the way an RS256 issuer would."""
        return self.private.sign(signing_input, padding.PKCS1v15(), hashes.SHA256())

    def public_jwk(self, kid: str) -> RSAPublicJWK:
        """The public half, as the verifier consumes it, under a chosen ``kid``."""
        numbers = self.private.public_key().public_numbers()
        return RSAPublicJWK(kid=kid, modulus=numbers.n, exponent=numbers.e)


def _new_signer() -> _Signer:
    """Generate one synthetic signer.

    Synthetic in the strict sense: no provider issued it, it authenticates
    nothing, and the module under test never sees its private half. 2048 bits
    is the floor the verifier enforces, and generation is fast enough at that
    size to run at import without anyone noticing.

    The sizes are written as literals rather than as named constants on
    purpose. ``key_size=SOME_NAME`` is the exact shape — a "key" keyword, an
    assignment, and a longish identifier — that a secret scanner's generic
    rule reads as a credential; ``key_size=2048`` cannot be read that way.
    """
    return _Signer(private=rsa.generate_private_key(public_exponent=65537, key_size=2048))


_FIRST_SIGNER = _new_signer()
_SECOND_SIGNER = _new_signer()


def _b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _b64url_json(value: Any) -> str:
    return _b64url(json.dumps(value, separators=(",", ":"), sort_keys=True).encode("utf-8"))


def _b64url_decode(segment: str) -> bytes:
    return base64.urlsafe_b64decode(segment + "=" * (-len(segment) % 4))


def _big_endian(value: int) -> bytes:
    return value.to_bytes((value.bit_length() + 7) // 8, "big")


def make_token(
    *,
    claims: dict[str, Any] | None = None,
    header: dict[str, Any] | None = None,
    signer: _Signer = _FIRST_SIGNER,
    kid: str = FIRST_KID,
) -> str:
    """Build a signed compact JWS, with sensible defaults for these tests.

    ``signer`` and ``kid`` are independent on purpose: a token that names one
    key and is signed by another is exactly the forgery the verifier must
    refuse, and it can only be expressed if the two are separate arguments.

    A ``None`` value in ``claims`` or ``header`` *removes* that member, which is
    how the "missing kid" and "missing exp" cases are expressed.
    """
    full_header: dict[str, Any] = {"alg": "RS256", "typ": "JWT", "kid": kid}
    if header is not None:
        full_header = {**full_header, **header}
        for name, value in header.items():
            if value is None:
                full_header.pop(name, None)
    full_claims: dict[str, Any] = {
        "sub": "subject-abc",
        "iss": ISSUER,
        "aud": AUDIENCE,
        "iat": NOW - 60,
        "exp": NOW + 600,
    }
    if claims is not None:
        full_claims = {**full_claims, **claims}
        for name, value in claims.items():
            if value is None:
                full_claims.pop(name, None)

    header_b64 = _b64url_json(full_header)
    payload_b64 = _b64url_json(full_claims)
    signature = signer.sign(f"{header_b64}.{payload_b64}".encode("ascii"))
    return f"{header_b64}.{payload_b64}.{_b64url(signature)}"


@pytest.fixture
def key_set() -> StaticJWKS:
    """A two-key set, so "wrong key" is distinguishable from "unknown kid"."""
    return StaticJWKS.from_keys(
        [
            _FIRST_SIGNER.public_jwk(FIRST_KID),
            _SECOND_SIGNER.public_jwk(SECOND_KID),
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
    built = StaticJWKSTokenVerifier(keys=key_set, issuer=ISSUER, audience=AUDIENCE)
    now = time.time()
    assert built.verify(make_token(claims={"iat": now, "exp": now + 600})).subject == "subject-abc"
    with pytest.raises(TokenVerificationError):
        built.verify(make_token(claims={"iat": now - 600, "exp": now - 1}))


def test_accepts_a_list_audience_containing_the_configured_one(
    verifier: StaticJWKSTokenVerifier,
) -> None:
    identity = verifier.verify(make_token(claims={"aud": ["other-audience", AUDIENCE]}))
    assert identity.subject == "subject-abc"


def test_accepts_the_second_key_in_the_set(verifier: StaticJWKSTokenVerifier) -> None:
    """Rotation works: a token names its key, and either key in the set is fine."""
    token = make_token(signer=_SECOND_SIGNER, kid=SECOND_KID)
    assert json.loads(_b64url_decode(token.split(".")[0]))["kid"] == SECOND_KID
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
        verifier.verify(make_token(kid="not-in-the-key-set"))


@pytest.mark.parametrize("alg", ["none", "None", "HS256", "RS512", "rs256", "ES256", ""])
def test_refuses_a_token_whose_alg_is_not_rs256(
    verifier: StaticJWKSTokenVerifier, alg: str
) -> None:
    with pytest.raises(TokenVerificationError):
        verifier.verify(make_token(header={"alg": alg}))


def test_refuses_an_unsigned_alg_none_token(verifier: StaticJWKSTokenVerifier) -> None:
    """The classic forgery: valid-looking claims, no signature at all."""
    header_b64 = _b64url_json({"alg": "none", "typ": "JWT", "kid": FIRST_KID})
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
    """Signed by the second signer, but claiming the first key's ``kid``.

    Both halves are asserted, because the failure mode this test guards against
    is passing vacuously: the header really does name ``FIRST_KID`` (so the
    verifier selects the first key, which cannot have made this signature), and
    the *same* signer's token verifies fine once it names its own key. What is
    refused is therefore the mismatch, not the signer.
    """
    forged = make_token(signer=_SECOND_SIGNER, kid=FIRST_KID)
    assert json.loads(_b64url_decode(forged.split(".")[0]))["kid"] == FIRST_KID
    assert verifier.verify(make_token(signer=_SECOND_SIGNER, kid=SECOND_KID)).subject == (
        "subject-abc"
    )

    with pytest.raises(TokenVerificationError):
        verifier.verify(forged)


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


def test_accepts_a_token_whose_nbf_has_passed(verifier: StaticJWKSTokenVerifier) -> None:
    """The ``nbf`` check refuses the future, not every token that carries one."""
    assert verifier.verify(make_token(claims={"nbf": NOW - 60})).subject == "subject-abc"


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
        make_token(claims={"nbf": NOW + 60}),
        make_token(claims={"iss": "https://issuer.invalid/other"}),
        make_token(claims={"aud": "other-audience"}),
        make_token(kid="not-in-the-key-set"),
        make_token(header={"alg": "HS256"}),
        make_token(signer=_SECOND_SIGNER, kid=FIRST_KID),
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
    numbers = _FIRST_SIGNER.private.public_key().public_numbers()
    document = {
        "keys": [
            {
                "kty": "RSA",
                "use": "sig",
                "alg": "RS256",
                "kid": FIRST_KID,
                "n": _b64url(_big_endian(numbers.n)),
                "e": _b64url(_big_endian(numbers.e)),
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
                _FIRST_SIGNER.public_jwk(FIRST_KID),
                _SECOND_SIGNER.public_jwk(FIRST_KID),
            ]
        )


def test_rejects_an_undersized_or_malformed_key() -> None:
    numbers = _FIRST_SIGNER.private.public_key().public_numbers()
    with pytest.raises(ProviderConfigurationError):
        RSAPublicJWK(kid="small", modulus=3233, exponent=17)
    with pytest.raises(ProviderConfigurationError):
        RSAPublicJWK(kid="", modulus=numbers.n, exponent=numbers.e)
    with pytest.raises(ProviderConfigurationError):
        RSAPublicJWK(kid="even-exponent", modulus=numbers.n, exponent=4)


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


def test_the_signature_check_is_delegated_not_hand_rolled() -> None:
    """No custom crypto in an authentication path.

    The predecessor of this module implemented PKCS#1 v1.5 with ``hashlib`` and
    integer arithmetic, because the runtime then carried no crypto dependency.
    It now does, hash-pinned, so the arithmetic is gone and must stay gone.
    """
    source = MODULE_PATH.read_text(encoding="utf-8")
    imported = _imported_modules(MODULE_PATH)

    assert any(module.split(".")[0] == "cryptography" for module in imported)
    for banned in ("hashlib", "hmac"):
        assert banned not in imported
    for arithmetic in ("pow(", "int.from_bytes(signature", "DIGEST_INFO"):
        assert arithmetic not in source, f"hand-rolled crypto reappeared: {arithmetic}"


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
        or "StaticJWKS" in path.read_text(encoding="utf-8")
    ]
    assert offenders == [], f"the unwired scaffold is referenced by: {offenders}"


def test_the_api_still_builds_a_fixture_verifier() -> None:
    """The other half of the wiring test: what main uses has not changed."""
    main_source = (REPO_ROOT / "services" / "api" / "smartmatch_api" / "main.py").read_text(
        encoding="utf-8"
    )
    assert "build_token_verifier" in main_source


def test_the_scaffold_added_no_v1_route() -> None:
    """An unwired verifier cannot have grown an endpoint.

    Generated from the live app as well as read from the committed contract, so
    a route added in code but missing from the contract fails here too.
    """
    from smartmatch_api.main import app

    contract = json.loads(
        (REPO_ROOT / "contracts" / "openapi" / "smartmatch.json").read_text(encoding="utf-8")
    )
    published = {path for path in contract["paths"] if path.startswith("/v1")}
    generated = {path for path in app.openapi()["paths"] if path.startswith("/v1")}

    assert generated == published
    assert not any("jwks" in path.lower() or "auth" in path.lower() for path in published)


def test_the_verifier_is_not_exported_from_the_providers_package() -> None:
    """Not re-exported, so importing the package does not drag the scaffold in.

    ``smartmatch_api.main`` imports from ``smartmatch_providers``, so a
    re-export here would silently load this module into the API process too. An
    unwired module that every importer of the package loads is only nominally
    unwired.
    """
    import smartmatch_providers

    source = (MODULE_PATH.parent / "__init__.py").read_text(encoding="utf-8")
    assert "jwks" not in source
    assert "StaticJWKS" not in source
    for exported in scaffold.__all__:
        assert exported not in smartmatch_providers.__all__
        assert not hasattr(smartmatch_providers, exported)


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
