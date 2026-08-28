"""Tests for the deliberately bounded local-pilot identity fixture."""

from __future__ import annotations

import pytest
from pydantic import ValidationError
from smartmatch_api.config import Settings
from smartmatch_providers import (
    Edition,
    FixtureTokenVerifier,
    ProviderConfigurationError,
    TokenVerificationError,
    build_token_verifier,
)


def test_configured_development_token_verifies_as_its_configured_subject():
    verifier = build_token_verifier(
        Edition.DEV,
        use_fixture=True,
        fixture_principals={"pilot-token": "pilot-subject"},
    )

    assert isinstance(verifier, FixtureTokenVerifier)
    assert verifier.verify("pilot-token").subject == "pilot-subject"


def test_unknown_token_is_rejected_even_when_a_development_token_is_configured():
    verifier = build_token_verifier(
        Edition.DEV,
        use_fixture=True,
        fixture_principals={"pilot-token": "pilot-subject"},
    )

    with pytest.raises(TokenVerificationError):
        verifier.verify("not-configured")


def test_empty_development_principal_config_keeps_the_fixture_all_401():
    verifier = build_token_verifier(Edition.DEV, use_fixture=True, fixture_principals={})

    with pytest.raises(TokenVerificationError):
        verifier.verify("any-token")


@pytest.mark.parametrize("edition", [Edition.STAGING, Edition.CLASSROOM, Edition.PRODUCTION])
def test_direct_factory_rejects_fixture_principals_outside_dev(edition: Edition):
    with pytest.raises(ProviderConfigurationError, match="fixture principals"):
        build_token_verifier(
            edition,
            use_fixture=True,
            fixture_principals={"pilot-token": "pilot-subject"},
        )


def test_direct_factory_rejects_fixture_principals_without_fixture_mode():
    with pytest.raises(ProviderConfigurationError, match="use_fixture=true"):
        build_token_verifier(
            Edition.DEV,
            use_fixture=False,
            fixture_principals={"pilot-token": "pilot-subject"},
        )


@pytest.mark.parametrize(
    ("token", "subject"),
    [
        ("", "pilot-subject"),
        ("   ", "pilot-subject"),
        ("pilot-token", ""),
        ("pilot-token", "\t"),
        (1, "pilot-subject"),
        ("pilot-token", 1),
    ],
)
def test_direct_factory_rejects_blank_or_non_string_principals(token: object, subject: object):
    with pytest.raises(ProviderConfigurationError, match="non-blank strings"):
        build_token_verifier(
            Edition.DEV,
            use_fixture=True,
            fixture_principals={token: subject},  # type: ignore[arg-type]
        )


@pytest.mark.parametrize("edition", ["staging", "classroom", "production"])
def test_development_principals_are_rejected_outside_dev(edition: str):
    with pytest.raises(ValidationError, match="dev_principals"):
        Settings(edition=edition, dev_principals={"pilot-token": "pilot-subject"})


def test_development_principals_require_fixture_providers():
    with pytest.raises(ValidationError, match="fixture providers"):
        Settings(
            edition="dev",
            use_fixture_providers=False,
            dev_principals={"pilot-token": "pilot-subject"},
        )
