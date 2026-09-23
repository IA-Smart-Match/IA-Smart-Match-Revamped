"""``SPEAKER_PORTAL`` is off everywhere, and what turning it on requires (B26 T6b-1).

Turning it on is a reviewed edit to the policy rows (plan C2 = a). Its turn-on
rule (C5): T6b-5 merged **and** parent §10 rows 1, 2 and 4 cleared.
"""

from __future__ import annotations

import re
from pathlib import Path

from smartmatch_domain.product_scope import (
    Capability,
    ProductScope,
    is_capability_enabled,
)

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_speaker_portal_is_off_in_every_scope() -> None:
    for scope in ProductScope:
        assert not is_capability_enabled(scope, Capability.SPEAKER_PORTAL), (
            f"SPEAKER_PORTAL must stay off in {scope}; turning it on is a reviewed "
            "edit gated on T6b-5 and parent §10 rows 1, 2 and 4"
        )


def test_no_config_seed_or_compose_file_turns_it_on() -> None:
    """No env var, compose file or seed names the capability as a switch."""
    pattern = re.compile(r"SPEAKER_PORTAL\s*[:=]\s*[\"']?(1|true|on|yes)", re.IGNORECASE)
    for relative in ("docker-compose.yml", ".env.example"):
        path = REPO_ROOT / relative
        if path.is_file():
            assert not pattern.search(path.read_text(encoding="utf-8")), relative


def test_capability_requires_login_outreach_and_contacts() -> None:
    """The docstring's turn-on rule and the import-time dependency both exist."""
    source = (
        REPO_ROOT / "python" / "smartmatch_domain" / "smartmatch_domain" / "product_scope.py"
    ).read_text(encoding="utf-8")
    assert "T6b-5" in source
    for scope in ProductScope:
        if is_capability_enabled(scope, Capability.SPEAKER_PORTAL):  # pragma: no cover
            for required in (
                Capability.AUTHENTICATED_LOGIN,
                Capability.CONSENTED_OUTREACH,
                Capability.SPEAKER_CONTACT_MANAGEMENT,
            ):
                assert is_capability_enabled(scope, required)

    from smartmatch_domain import product_scope

    assert product_scope.SPEAKER_PORTAL_REQUIRES == frozenset(
        {
            Capability.AUTHENTICATED_LOGIN,
            Capability.CONSENTED_OUTREACH,
            Capability.SPEAKER_CONTACT_MANAGEMENT,
        }
    )
