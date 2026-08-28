"""Source contract: opportunities UI must not fabricate counts or lists until S12."""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
OPPORTUNITIES_PAGE = (
    REPO_ROOT / "apps" / "web" / "legacy-frontend" / "src" / "app" / "pages" / "Opportunities.tsx"
)
DASHBOARD_PAGE = (
    REPO_ROOT / "apps" / "web" / "legacy-frontend" / "src" / "app" / "pages" / "Dashboard.tsx"
)
METRICS_LIB = REPO_ROOT / "apps" / "web" / "legacy-frontend" / "src" / "lib" / "metrics.ts"

OPPORTUNITIES_FORBIDDEN_PATTERNS = (
    "fetchCrawlerResults",
    "fetchEvents",
    "mapCrawlerToOpportunity",
    "mapEventToOpportunity",
    'date: "See link for details"',
    'role: "Guest speaker"',
    "/ai-matching",
    "live dataset",
    "Showing ",
    "of {opportunities.length}",
)

DASHBOARD_OPPORTUNITIES_FORBIDDEN_PATTERNS = (
    "Loaded from CPP events",
    "Active Opportunities",
    "value={eventCount}",
)


def test_opportunities_page_does_not_fabricate_legacy_merge() -> None:
    source = OPPORTUNITIES_PAGE.read_text(encoding="utf-8")
    for pattern in OPPORTUNITIES_FORBIDDEN_PATTERNS:
        assert pattern not in source, (
            f"Opportunities page still contains fabricated-list pattern: {pattern!r}"
        )


def test_opportunities_page_shows_unknown_until_s12() -> None:
    source = OPPORTUNITIES_PAGE.read_text(encoding="utf-8")
    assert "OPPORTUNITIES_UNKNOWN_REASON" in source
    assert "unavailableOpportunitiesMetric" in source
    assert "S12" in source
    assert "gate G1" in source


def test_metrics_lib_exports_opportunities_unknown_reason() -> None:
    source = METRICS_LIB.read_text(encoding="utf-8")
    assert "OPPORTUNITIES_UNKNOWN_REASON" in source
    assert "S12 Pipeline persistence is not started" in source
    assert "canonical opportunities metric is not registered" in source


def test_dashboard_does_not_fabricate_opportunities_count() -> None:
    source = DASHBOARD_PAGE.read_text(encoding="utf-8")
    for pattern in DASHBOARD_OPPORTUNITIES_FORBIDDEN_PATTERNS:
        assert pattern not in source, (
            f"Dashboard still contains fabricated opportunities pattern: {pattern!r}"
        )
    assert "unavailableOpportunitiesMetric" in source
    assert "OPPORTUNITIES_UNKNOWN_REASON" in source
