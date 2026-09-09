"""Composition contract for the superseding CPP speaker workflow."""

from pathlib import Path

from smartmatch_api.main import app
from smartmatch_domain.product_scope import DEFAULT_PRODUCT_SCOPE, Capability, is_capability_enabled

ROOT = Path(__file__).resolve().parents[2]
ROUTES = (ROOT / "apps/web/legacy-frontend/src/app/routes.tsx").read_text(encoding="utf-8")


def test_email_capability_is_disabled() -> None:
    assert not is_capability_enabled(DEFAULT_PRODUCT_SCOPE, Capability.CONSENTED_OUTREACH)


def test_email_and_batch_routes_are_not_composed() -> None:
    paths = set(app.openapi()["paths"])
    assert not any("outreach" in path or "speaker-invitations" in path for path in paths)
    assert not any(path.startswith("/u/") or path.startswith("/i/") for path in paths)


def test_shared_tracking_surfaces_remain_reachable() -> None:
    paths = set(app.openapi()["paths"])
    assert "/v1/units/{unit_id}/speaker-events" in paths
    assert "/v1/units/{unit_id}/events/{event_id}/match-runs" in paths
    assert 'path: "outreach"' in ROUTES
