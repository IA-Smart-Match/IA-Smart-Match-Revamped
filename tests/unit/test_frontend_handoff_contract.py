"""Shared speaker-event handoff UI contract."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2] / "apps/web/legacy-frontend/src"
BOARD = (ROOT / "app/components/SpeakerEventsBoard.tsx").read_text(encoding="utf-8")


def test_both_roles_use_one_shared_board() -> None:
    assert 'role: "connector" | "host"' in BOARD
    assert "fetchSpeakerEvents" in BOARD
    assert "fetchSpeakerEvent" in BOARD


def test_board_uses_server_versions_and_history() -> None:
    assert "record.version" in BOARD
    assert "detail.data?.history" in BOARD
    assert "detail.data?.notes" in BOARD


def test_board_has_no_send_or_message_action() -> None:
    for forbidden in ("Send Message", "batch invitation", "Approve & Send"):
        assert forbidden not in BOARD
