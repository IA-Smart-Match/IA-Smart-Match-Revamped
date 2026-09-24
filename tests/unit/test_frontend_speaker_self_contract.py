"""Source contract for the Speaker's own ``api.ts`` adapters (B26 T6b-2 plan §6).

No adapter may take a subject: the server finds the Speaker from the session
(MM-A01). A parameter named for a professional, unit or user would be the first
step towards a client choosing whose rows it reads.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
API_LIB = REPO_ROOT / "apps" / "web" / "legacy-frontend" / "src" / "lib" / "api.ts"

ADAPTERS = {
    "fetchMyAvailability": "/v1/me/availability",
    "updateMyAvailability": "/v1/me/availability",
    "fetchMyInvitations": "/v1/me/invitations",
    "answerMyInvitation": "/v1/me/invitations/",
    "fetchMyEngagements": "/v1/me/engagements",
}


def _code_only(source: str) -> str:
    """Strip JSDoc blocks and line comments before scanning."""
    without_blocks = re.sub(r"/\*.*?\*/", "", source, flags=re.DOTALL)
    return "\n".join(
        line for line in without_blocks.splitlines() if not line.lstrip().startswith("//")
    )


def _source() -> str:
    return _code_only(API_LIB.read_text(encoding="utf-8"))


def _declaration(source: str, name: str) -> str:
    head = f"export async function {name}("
    parts = source.split(head, 1)
    assert len(parts) == 2, f"api.ts is missing {head!r}"
    return parts[1].split("\n}", 1)[0]


def _parameters(source: str, name: str) -> str:
    return _declaration(source, name).split(")", 1)[0]


def test_the_five_functions_and_urls_exist() -> None:
    source = _source()
    for name, url in ADAPTERS.items():
        assert url in _declaration(source, name), name


def test_no_adapter_takes_a_subject() -> None:
    source = _source()
    for name in ADAPTERS:
        parameters = _parameters(source, name)
        for forbidden in ("professionalId", "unitId", "userId", "professional_id", "unit_id"):
            assert forbidden not in parameters, f"{name} takes {forbidden}"


def test_fetch_my_engagements_takes_engagement_when() -> None:
    assert "when: EngagementWhen" in _parameters(_source(), "fetchMyEngagements")


def test_invitation_id_is_encoded() -> None:
    assert "encodeURIComponent(invitationId)" in _declaration(_source(), "answerMyInvitation")
