"""The visible matching UI uses the speaker roster workflow."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2] / "apps/web/legacy-frontend/src"
EVENTS = (ROOT / "app/pages/coordinator/CoordinatorEvents.tsx").read_text(encoding="utf-8")


def test_matching_lives_on_event_host_events() -> None:
    assert "Run Smart Match" in EVENTS
    assert "Submit selected speakers" in EVENTS
    assert "explanations" in EVENTS


def test_matching_shows_no_internal_score_or_confidence() -> None:
    for forbidden in ("total_score", "topic_score", "proximity_score", "confidence"):
        assert forbidden not in EVENTS
