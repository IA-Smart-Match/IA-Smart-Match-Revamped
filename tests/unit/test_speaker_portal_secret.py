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


# ---------------------------------------------------------------------------
# The worker's half (plan §4.2, R10)
# ---------------------------------------------------------------------------


def _worker_settings(**kwargs: object):
    from smartmatch_worker.config import WorkerSettings

    return WorkerSettings(**kwargs)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "stored", [None, "", " " * 40, _value(31)], ids=["unset", "empty", "whitespace", "31"]
)
def test_check_worker_speaker_portal_startup_refuses_on_without_secret(
    stored: str | None, monkeypatch: pytest.MonkeyPatch
) -> None:
    from smartmatch_worker import config as worker_config

    monkeypatch.setattr(worker_config, "is_capability_enabled", lambda scope, capability: True)
    settings = _worker_settings(
        speaker_portal_token_secret=None if stored is None else SecretStr(stored)
    )
    with pytest.raises(ValueError) as raised:
        worker_config.check_worker_speaker_portal_startup(settings)
    assert _VAR in str(raised.value) and "32" in str(raised.value)
    if stored and stored.strip():
        assert stored not in str(raised.value)


def test_check_worker_speaker_portal_startup_returns_secret_when_on(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from smartmatch_worker import config as worker_config

    monkeypatch.setattr(worker_config, "is_capability_enabled", lambda scope, capability: True)
    value = _value(40)
    settings = _worker_settings(speaker_portal_token_secret=SecretStr(value))
    assert worker_config.check_worker_speaker_portal_startup(settings) == value


def test_check_worker_speaker_portal_startup_is_none_when_off() -> None:
    from smartmatch_worker.config import check_worker_speaker_portal_startup

    assert check_worker_speaker_portal_startup(_worker_settings()) is None
    short = _worker_settings(speaker_portal_token_secret=SecretStr("x"))
    assert check_worker_speaker_portal_startup(short) is None


def test_worker_settings_default_to_the_api_product_scope() -> None:
    from smartmatch_domain.product_scope import DEFAULT_PRODUCT_SCOPE

    assert _worker_settings().product_scope is DEFAULT_PRODUCT_SCOPE


def test_env_example_documents_the_secret() -> None:
    text = (REPO_ROOT / ".env.example").read_text(encoding="utf-8")
    assert f"{_VAR}=" in text
    assert "32" in text and "worker" in text


def test_compose_passes_the_secret_to_api_and_worker() -> None:
    import yaml

    compose = yaml.safe_load((REPO_ROOT / "docker-compose.yml").read_text(encoding="utf-8"))
    for service in ("api", "worker"):
        environment = compose["services"][service]["environment"]
        assert environment[_VAR] == "${SMARTMATCH_SPEAKER_PORTAL_TOKEN_SECRET:-}", service
