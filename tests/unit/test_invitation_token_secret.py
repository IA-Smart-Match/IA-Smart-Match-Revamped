"""#287: the invitation token key is required in every edition."""

from __future__ import annotations

import pytest
from pydantic import SecretStr
from smartmatch_api.config import Settings, check_invitation_startup
from smartmatch_domain.cba_invitations import (
    resolve_invitation_token_secret,
)

_GOOD = "k" * 40


@pytest.mark.parametrize("configured", [None, "", "   ", "short"])
def test_no_key_without_a_good_secret(configured) -> None:
    assert resolve_invitation_token_secret(configured) is None


def test_a_good_secret_is_used() -> None:
    assert resolve_invitation_token_secret(_GOOD) == _GOOD


@pytest.mark.parametrize("secret", [None, SecretStr("short")])
def test_startup_rejects_a_missing_or_short_secret_in_production(secret) -> None:
    settings = Settings(edition="production", speaker_portal_token_secret=secret)
    with pytest.raises(ValueError, match="SPEAKER_PORTAL_TOKEN_SECRET"):
        check_invitation_startup(settings)


def test_startup_refuses_dev_without_a_secret_when_outreach_is_on(monkeypatch) -> None:
    import smartmatch_api.config as cfg

    settings = Settings(edition="dev", speaker_portal_token_secret=None)
    monkeypatch.setattr(Settings, "capability_enabled", lambda self, cap: True)
    with pytest.raises(ValueError, match="SPEAKER_PORTAL_TOKEN_SECRET"):
        cfg.check_invitation_startup(settings)


def test_startup_accepts_a_good_secret_in_any_edition() -> None:
    for edition in ("dev", "production"):
        check_invitation_startup(
            Settings(edition=edition, speaker_portal_token_secret=SecretStr(_GOOD))
        )


def test_app_startup_refuses_without_a_secret_but_import_does_not(monkeypatch) -> None:
    from fastapi.testclient import TestClient
    from smartmatch_api import main

    monkeypatch.delenv("SMARTMATCH_SPEAKER_PORTAL_TOKEN_SECRET", raising=False)
    main.get_settings.cache_clear()
    try:
        with pytest.raises(ValueError, match="SPEAKER_PORTAL_TOKEN_SECRET"), TestClient(main.app):
            pass
    finally:
        main.get_settings.cache_clear()
