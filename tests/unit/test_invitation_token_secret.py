"""#287: the invitation token key fails closed outside dev/classroom."""

from __future__ import annotations

import pytest
from pydantic import SecretStr
from smartmatch_api.config import Settings, check_invitation_startup
from smartmatch_domain.cba_invitations import (
    SYNTHETIC_INVITATION_TOKEN_SECRET,
    resolve_invitation_token_secret,
)

_GOOD = "k" * 40


@pytest.mark.parametrize("edition", ["dev", "classroom"])
@pytest.mark.parametrize("configured", [None, "", "   ", "short"])
def test_dev_and_classroom_fall_back_to_the_synthetic_key(edition: str, configured) -> None:
    assert (
        resolve_invitation_token_secret(configured, edition=edition)
        == SYNTHETIC_INVITATION_TOKEN_SECRET
    )


@pytest.mark.parametrize("edition", ["staging", "production"])
@pytest.mark.parametrize("configured", [None, "", "   ", "short"])
def test_other_editions_have_no_key_without_a_good_secret(edition: str, configured) -> None:
    assert resolve_invitation_token_secret(configured, edition=edition) is None


def test_a_good_secret_is_used_everywhere() -> None:
    for edition in ("dev", "production"):
        assert resolve_invitation_token_secret(_GOOD, edition=edition) == _GOOD


@pytest.mark.parametrize("secret", [None, SecretStr("short")])
def test_startup_rejects_a_missing_or_short_secret_in_production(secret) -> None:
    settings = Settings(edition="production", speaker_portal_token_secret=secret)
    with pytest.raises(ValueError, match="SPEAKER_PORTAL_TOKEN_SECRET"):
        check_invitation_startup(settings)


def test_startup_accepts_dev_without_a_secret_and_production_with_one() -> None:
    check_invitation_startup(Settings(edition="dev"))
    check_invitation_startup(
        Settings(edition="production", speaker_portal_token_secret=SecretStr(_GOOD))
    )
