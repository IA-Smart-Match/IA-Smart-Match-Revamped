"""Source checks for the Event Host home and its canonical data reads."""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
HOME = REPO_ROOT / "apps" / "web" / "legacy-frontend" / "src" / "app" / "pages" / "coordinator" / "CoordinatorHome.tsx"


def test_event_host_home_uses_authorized_unit_and_canonical_reads() -> None:
    source = HOME.read_text(encoding="utf-8")
    assert 'useAuthorizedUnitId("coordinator")' in source
    for adapter in ("fetchManualEvents", "fetchSpeakerEvents", "fetchSpeakers"):
        assert adapter in source
    assert "Promise.all" not in source
    assert "/api/" not in source


def test_event_host_home_exposes_the_combined_workflow() -> None:
    source = HOME.read_text(encoding="utf-8")
    assert "Create an event" in source
    assert "Run Smart Match" in source
    assert "Review handoffs" in source
    assert "/coordinator-portal/events" in source
    assert "/coordinator-portal/outreach" in source


def test_event_host_home_has_truthful_loading_empty_and_error_states() -> None:
    source = HOME.read_text(encoding="utf-8")
    assert "isLoading" in source
    assert "No events yet" in source
    assert "No speaker handoffs" in source
    assert "ErrorPanel" in source
    assert "has not published a roster" in source
