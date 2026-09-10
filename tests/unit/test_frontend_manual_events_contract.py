"""Source contract for the Speaker Connector's manual-events frontend surface.

Asserts the shape Track C added on top of Track B's backend
(``services/api/smartmatch_api/routers/manual_events.py``): six additive
adapters in ``api.ts``, an ``Events.tsx`` page with no raw ``fetch`` and no
third-party QR endpoint, and a ``routes.tsx``/``Layout.tsx`` that still carry
every route main already had — this port must not remove or redirect an
existing surface.
"""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
FRONTEND_SRC = REPO_ROOT / "apps" / "web" / "legacy-frontend" / "src"
API_LIB = FRONTEND_SRC / "lib" / "api.ts"
EVENTS_PAGE = FRONTEND_SRC / "app" / "pages" / "Events.tsx"
QR_CARD = FRONTEND_SRC / "components" / "QRCodeCard.tsx"
ROUTES = FRONTEND_SRC / "app" / "routes.tsx"
LAYOUT = FRONTEND_SRC / "app" / "components" / "Layout.tsx"

MAIN_ROUTE_LITERALS = (
    "opportunities",
    "ai-matching",
    "pipeline",
    "calendar",
    "review-queue",
    "matching-weights",
    "invitations",
    "match-runs",
    "speaker-contacts",
    "speaker-feedback",
    "meetings",
    "speaker-request",
    "confirmed-speaker",
    "my-requests",
)


def test_api_ts_has_manual_event_adapters_and_paths() -> None:
    text = API_LIB.read_text(encoding="utf-8")
    for name in (
        "createManualEvent",
        "fetchManualEvent",
        "updateManualEvent",
        "publishManualEvent",
        "fetchFeedbackQr",
        "saveFeedbackQr",
    ):
        assert f"export async function {name}" in text, f"api.ts is missing {name}"
    assert "/events" in text
    assert "/feedback-qr" in text
    assert "Idempotency-Key" in text


def test_events_page_has_no_fetch_no_legacy_qr_endpoint_and_qr_opens_wording() -> None:
    text = EVENTS_PAGE.read_text(encoding="utf-8")
    assert "fetch(" not in text
    assert "/api/qr" not in text
    combined = text + QR_CARD.read_text(encoding="utf-8")
    assert "QR opens" in combined


def test_routes_tsx_keeps_every_main_route_and_adds_events_under_admin_layout() -> None:
    text = ROUTES.read_text(encoding="utf-8")
    for literal in MAIN_ROUTE_LITERALS:
        assert f'"{literal}"' in text, f"routes.tsx lost the {literal!r} route"
    assert '"events"' in text
    # The admin (pathless-layout) block is the one containing "opportunities";
    # confirm "events" sits in that same block rather than some other shell.
    admin_block_start = text.index('{ path: "opportunities"')
    admin_block = text[admin_block_start:]
    assert '{ path: "events"' in admin_block


def test_layout_nav_gained_one_events_entry_without_disturbing_pinned_structure() -> None:
    text = LAYOUT.read_text(encoding="utf-8")
    assert "offeredSections.map(" in text
    assert "requires:" in text
    for href in (
        "/dashboard",
        "/volunteers",
        "/pipeline",
        "/calendar",
        "/opportunities",
        "/ai-matching",
    ):
        assert f'href: "{href}"' in text
    assert '{ name: "Events", href: "/events"' in text
