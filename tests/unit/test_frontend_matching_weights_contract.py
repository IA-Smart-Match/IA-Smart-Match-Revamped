"""The superseded configurable-weight UI cannot return."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2] / "apps/web/legacy-frontend/src/app"
ROUTES = (ROOT / "routes.tsx").read_text(encoding="utf-8")


def test_no_weight_settings_page_is_mounted() -> None:
    assert "CoordinatorMatchingWeights" not in ROUTES
    assert "matching-weights" not in ROUTES
