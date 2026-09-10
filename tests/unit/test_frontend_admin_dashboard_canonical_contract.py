from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
FRONTEND = ROOT / "apps" / "web" / "legacy-frontend" / "src"
DASHBOARD = (FRONTEND / "app" / "pages" / "Dashboard.tsx").read_text(encoding="utf-8")
STUDENT_EVENTS = (FRONTEND / "app" / "pages" / "student" / "StudentEvents.tsx").read_text(
    encoding="utf-8"
)


def test_admin_dashboard_uses_canonical_unit_scoped_reads() -> None:
    for adapter in (
        "fetchManualEvents",
        "fetchReviewItems",
        "fetchSpeakers",
        "fetchSpeakerEvents",
        "fetchUnitSpeakerFeedbackSummary",
        "fetchAttendanceSummary",
        "useAuthorizedUnitId(\"admin\")",
    ):
        assert adapter in DASHBOARD
    assert "getConfiguredUnitId" not in DASHBOARD
    assert "VITE_SMARTMATCH_UNIT_ID" not in DASHBOARD
    for call in (
        "fetchManualEvents(unitId",
        "fetchReviewItems(unitId",
        "fetchSpeakers(unitId",
        "fetchSpeakerEvents(unitId",
        "fetchUnitSpeakerFeedbackSummary(unitId",
        "fetchAttendanceSummary(unitId",
        "useUnitMetrics(reloadToken, unitId)",
    ):
        assert call in DASHBOARD


def test_admin_dashboard_has_no_legacy_fixture_or_calendar_reads() -> None:
    for forbidden in (
        "/api/calendar/",
        "/api/feedback/stats",
        "/api/data/",
        "/api/crawler/",
        "fetchCalendarEvents",
        "fetchCalendarAssignments",
        "fetchFeedbackStats",
    ):
        assert forbidden not in DASHBOARD


def test_student_calendar_keeps_its_canonical_routes() -> None:
    assert "fetchStudentEvents" in STUDENT_EVENTS
    assert "fetchStudentAgenda" in STUDENT_EVENTS
