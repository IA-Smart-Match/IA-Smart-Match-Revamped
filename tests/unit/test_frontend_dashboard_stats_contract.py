"""The Connector dashboard keeps accountable server-backed data."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2] / "apps/web/legacy-frontend/src"
DASHBOARD = (ROOT / "app/pages/Dashboard.tsx").read_text(encoding="utf-8")


def test_dashboard_uses_the_server_authorized_unit() -> None:
    assert 'useAuthorizedUnitId("admin")' in DASHBOARD
    assert "getConfiguredUnitId" not in DASHBOARD


def test_dashboard_reads_backed_data_sources() -> None:
    for helper in (
        "fetchCalendarEvents",
        "fetchCalendarAssignments",
        "fetchFeedbackStats",
        "fetchManualEvents",
    ):
        assert helper in DASHBOARD


def test_dashboard_keeps_a_visible_source_disclosure() -> None:
    assert "Synthetic data" in DASHBOARD or "fixture" in DASHBOARD.casefold()
    assert "loadFailed" in DASHBOARD
