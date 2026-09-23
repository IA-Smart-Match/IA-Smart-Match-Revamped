"""``SMARTMATCH_SPEAKER_PORTAL_TOKEN_SECRET``: fail fast when on, unread when off (R10).

Secret-shaped values are built at runtime.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import SecretStr
from smartmatch_api.config import Settings, check_speaker_portal_startup
from smartmatch_domain.product_scope import Capability

REPO_ROOT = Path(__file__).resolve().parents[2]
_VAR = "SMARTMATCH_SPEAKER_PORTAL_TOKEN_SECRET"


class _Stub(Settings):
    """Settings whose SPEAKER_PORTAL answer is forced, the rest from the policy."""

    portal_on: bool = False

    def capability_enabled(self, capability: Capability) -> bool:  # type: ignore[override]
        if capability is Capability.SPEAKER_PORTAL:
            return self.portal_on
        return super().capability_enabled(capability)


def _value(length: int) -> str:
    return "k" * length


@pytest.mark.parametrize(
    "stored", [None, "", " " * 40, _value(31)], ids=["unset", "empty", "whitespace", "31"]
)
def test_check_speaker_portal_startup_refuses_on_without_secret(stored: str | None) -> None:
    settings = _Stub(
        portal_on=True,
        speaker_portal_token_secret=None if stored is None else SecretStr(stored),
    )
    with pytest.raises(ValueError) as raised:
        check_speaker_portal_startup(settings)
    message = str(raised.value)
    assert _VAR in message and "32" in message
    if stored and stored.strip():
        assert stored not in message


def test_check_speaker_portal_startup_returns_secret_when_on() -> None:
    value = _value(32)
    settings = _Stub(portal_on=True, speaker_portal_token_secret=SecretStr(value))
    assert check_speaker_portal_startup(settings) == value


def test_check_speaker_portal_startup_is_none_when_off() -> None:
    assert check_speaker_portal_startup(_Stub(portal_on=False)) is None
    short = _Stub(portal_on=False, speaker_portal_token_secret=SecretStr("x"))
    assert check_speaker_portal_startup(short) is None
    assert check_speaker_portal_startup(Settings()) is None
