"""Source contract: matching UI must stay G1 fail-closed until registry approval."""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
AI_MATCHING_PAGE = (
    REPO_ROOT / "apps" / "web" / "legacy-frontend" / "src" / "app" / "pages" / "AIMatching.tsx"
)
DASHBOARD_PAGE = (
    REPO_ROOT / "apps" / "web" / "legacy-frontend" / "src" / "app" / "pages" / "Dashboard.tsx"
)
METRICS_LIB = REPO_ROOT / "apps" / "web" / "legacy-frontend" / "src" / "lib" / "metrics.ts"

MATCHING_FORBIDDEN_PATTERNS = (
    "rankSpeakers",
    "rankSpeakersForCourse",
    "/api/matching",
    "fetchFeedbackStats",
    "fetchPipeline",
    "fetchEvents",
    "Match Score",
    "match.score",
)

DASHBOARD_MATCHING_FORBIDDEN_PATTERNS = (
    "rankSpeakers",
    "/api/matching",
    "topMatches",
    "Match Score",
    "match.score",
)


def test_ai_matching_page_does_not_invoke_legacy_matching_api() -> None:
    source = AI_MATCHING_PAGE.read_text(encoding="utf-8")
    for pattern in MATCHING_FORBIDDEN_PATTERNS:
        assert pattern not in source, (
            f"AIMatching still contains forbidden matching pattern: {pattern!r}"
        )


def test_ai_matching_page_shows_g1_unavailable_state() -> None:
    source = AI_MATCHING_PAGE.read_text(encoding="utf-8")
    assert "MATCHING_UNAVAILABLE_REASON" in source
    assert "unavailableMatchingMetric" in source
    assert "gate G1" in source
    assert "REGISTRY_STATUS" in source


def test_metrics_lib_exports_matching_unavailable_reason() -> None:
    source = METRICS_LIB.read_text(encoding="utf-8")
    assert "MATCHING_UNAVAILABLE_REASON" in source
    assert 'REGISTRY_STATUS == "proposed"' in source
    assert "unavailableMatchingMetric" in source


def test_dashboard_does_not_invoke_legacy_matching_api() -> None:
    source = DASHBOARD_PAGE.read_text(encoding="utf-8")
    for pattern in DASHBOARD_MATCHING_FORBIDDEN_PATTERNS:
        assert pattern not in source, (
            f"Dashboard still contains forbidden matching pattern: {pattern!r}"
        )
    assert "MATCHING_UNAVAILABLE_REASON" in source
