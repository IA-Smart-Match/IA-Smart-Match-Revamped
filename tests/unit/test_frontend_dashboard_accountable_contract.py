"""Source contract: dashboard supplementary metrics must not show zero on fetch failure."""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DASHBOARD_PAGE = (
    REPO_ROOT / "apps" / "web" / "legacy-frontend" / "src" / "app" / "pages" / "Dashboard.tsx"
)

DASHBOARD_ACCOUNTABLE_REQUIRED = (
    "feedbackAvailable",
    "assignmentsAvailable",
    "accountableDemoMetric",
    "feedbackAcceptanceMetric",
    "averageFatigueMetric",
    "restRecommendedMetric",
    "AccountableValue",
)

DASHBOARD_FORBIDDEN_ZERO_FALLBACKS = (
    "Math.round(feedbackStats.acceptance_rate * 100)",
    "Math.round(feedbackStats.pain_score)",
    "Math.round(feedbackStats.membership_interest_rate * 100)",
    "{averageFatigue}%",
    "{cooldownCount}",
)


def test_dashboard_tracks_supplementary_metric_availability() -> None:
    source = DASHBOARD_PAGE.read_text(encoding="utf-8")
    for pattern in DASHBOARD_ACCOUNTABLE_REQUIRED:
        assert pattern in source, f"Dashboard missing accountable metric wiring: {pattern!r}"


def test_dashboard_does_not_render_failed_requests_as_zero() -> None:
    source = DASHBOARD_PAGE.read_text(encoding="utf-8")
    for pattern in DASHBOARD_FORBIDDEN_ZERO_FALLBACKS:
        assert pattern not in source, (
            f"Dashboard still renders unavailable metrics as zero: {pattern!r}"
        )
