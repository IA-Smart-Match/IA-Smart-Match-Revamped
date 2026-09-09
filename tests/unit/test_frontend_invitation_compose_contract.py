"""Email composition and batch invitation stay outside the frontend."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2] / "apps/web/legacy-frontend/src"
API = (ROOT / "lib/api.ts").read_text(encoding="utf-8")


def test_email_and_batch_adapters_are_absent() -> None:
    for symbol in (
        "createOutreachDraft",
        "submitOutreachSend",
        "createSpeakerInvitationBatch",
        "dispatchSpeakerInvitationBatch",
        "/speaker-invitations/batches",
    ):
        assert symbol not in API


def test_shortlist_creates_tracking_records_instead() -> None:
    assert "submitSpeakerShortlist" in API
    assert "/shortlist" in API
