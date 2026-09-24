"""Source contract for the speaker-availability ``api.ts`` adapter (B26 T3).

The adapter is a thin pass-through: it must send ``expected_version`` every
time (the server treats ``null`` as "I read no row", never as a blind write),
and it must never invent a capacity — "not stated" is ``null``, not a number.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
API_LIB = REPO_ROOT / "apps" / "web" / "legacy-frontend" / "src" / "lib" / "api.ts"


def _code_only(source: str) -> str:
    """Strip JSDoc blocks and line comments before scanning."""
    without_blocks = re.sub(r"/\*.*?\*/", "", source, flags=re.DOTALL)
    return "\n".join(
        line for line in without_blocks.splitlines() if not line.lstrip().startswith("//")
    )


def _declaration(source: str, head: str) -> str:
    parts = source.split(head, 1)
    assert len(parts) == 2, f"api.ts is missing {head!r}"
    return parts[1].split("\n}", 1)[0]


def test_both_functions_and_the_url_exist() -> None:
    source = _code_only(API_LIB.read_text(encoding="utf-8"))
    assert "export async function fetchSpeakerAvailability(" in source
    assert "export async function updateSpeakerAvailability(" in source
    assert "/availability`" in source
    assert "/speaker-contacts/" in _declaration(
        source, "export async function fetchSpeakerAvailability("
    )


def test_expected_version_is_required_not_optional() -> None:
    source = _code_only(API_LIB.read_text(encoding="utf-8"))
    payload = _declaration(source, "export interface SpeakerAvailabilityUpdatePayload")
    assert "expected_version: number | null;" in payload
    assert "expected_version?" not in payload


def test_no_capacity_is_invented() -> None:
    source = _code_only(API_LIB.read_text(encoding="utf-8"))
    for head in (
        "export async function fetchSpeakerAvailability(",
        "export async function updateSpeakerAvailability(",
    ):
        body = _declaration(source, head)
        assert not re.search(r"declared_capacity_hours_per_90_days\s*[:=?|]+\s*\d", body), (
            f"{head} invents a capacity number"
        )
    assert not re.search(r"declared_capacity_hours_per_90_days\??:\s*\d", source)
