"""Source contract for the Speaker Connector's manual-events frontend surface.

Asserts the shape Track C added on top of Track B's backend
(``services/api/smartmatch_api/routers/manual_events.py``): six additive
adapters in ``api.ts``, an events page with no raw ``fetch`` and no
third-party QR endpoint, and a router that still carries every route main
already had — this port must not remove or silently drop an existing surface.

Addendum 10 September 2026 — the Connector Dashboard consolidation
=================================================================

``admin`` and ``coordinator`` are one persona (``role_presentation.py``), so
the two Speaker Connector shells became one and the two events pages became
one with them. Three things this file asserted moved rather than went away,
and each assertion moved with its subject rather than being deleted:

* the events page is ``app/pages/coordinator/CoordinatorEvents.tsx``. The
  retired ``app/pages/Events.tsx`` held create/edit/publish and the feedback
  QR; the coordinator page held the listing. Every route behind both is
  ``admin``/``coordinator`` server-side, so the split was by shell rather than
  by authority, and merging the shells merged the pages.
* ``app/components/Layout.tsx`` is deleted. The nav assertion is made against
  ``CoordinatorPortalLayout.tsx``, the shell that survived.
* the eight addresses that shell owned are not gone — they redirect. The
  "no route lost" assertion is now made against the redirect table
  (``app/legacyRedirects.ts``) as well as the router, which is a stronger
  check than the original: it verifies the old URL still resolves rather than
  merely that some route with a similar name exists.

The invariant is unchanged: no surface main had may be removed, and nothing
about the manual-event write path may be weakened.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
FRONTEND_SRC = REPO_ROOT / "apps" / "web" / "legacy-frontend" / "src"
API_LIB = FRONTEND_SRC / "lib" / "api.ts"
EVENTS_PAGE = FRONTEND_SRC / "app" / "pages" / "coordinator" / "CoordinatorEvents.tsx"
QR_CARD = FRONTEND_SRC / "components" / "QRCodeCard.tsx"
ROUTES = FRONTEND_SRC / "app" / "routes.tsx"
CONNECTOR_SHELL = FRONTEND_SRC / "app" / "components" / "CoordinatorPortalLayout.tsx"
REDIRECTS = FRONTEND_SRC / "app" / "legacyRedirects.ts"

#: Route segments main carried that are still mounted as routes today.
MAIN_ROUTE_LITERALS = (
    "review-queue",
    "matching-weights",
    "invitations",
    "match-runs",
    "speaker-contacts",
    "speaker-feedback",
    "meetings",
    "speaker-request",
    "my-requests",
)

#: Addresses main carried that are now redirects, and where each one lands.
#:
#: Written out here rather than imported from the frontend so that this file
#: is an independent statement of what must keep working, not an echo of the
#: table under test.
RETIRED_MAIN_ROUTES = {
    "/opportunities": "/coordinator-portal/speaker-requests",
    "/ai-matching": "/coordinator-portal/match-runs",
    "/pipeline": "/coordinator-portal/speaker-requests",
    "/calendar": "/coordinator-portal/events",
    "/dashboard": "/coordinator-portal",
    "/volunteers": "/coordinator-portal/speaker-contacts",
    "/outreach": "/coordinator-portal/outreach",
    "/events": "/coordinator-portal/events",
    "/volunteer-portal/confirmed-speaker": "/volunteer-portal/my-requests",
    "/volunteer-portal/assignments": "/volunteer-portal",
}


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


def test_the_one_events_page_carries_both_halves_of_the_merge() -> None:
    """The merged page lists, writes, publishes, and configures the QR.

    The check that matters after a merge is that nothing was dropped on the
    way. The listing half contributes the withheld counts and the truncation
    notice — the figures that say whether a short list is a quiet unit or an
    unfinished pipeline — and the editor half contributes the write path.
    """
    text = EVENTS_PAGE.read_text(encoding="utf-8")

    for adapter in (
        "fetchUnitEvents",
        "createManualEvent",
        "updateManualEvent",
        "publishManualEvent",
        "fetchFeedbackQr",
        "saveFeedbackQr",
    ):
        assert adapter in text, f"the merged events page lost {adapter}"

    for withheld in ("withheld_unresolved_date", "withheld_quarantined_tags", "truncated"):
        assert withheld in text, (
            f"the merged events page lost {withheld}; without it an empty list cannot be "
            "told apart from a list the server could not complete"
        )

    # ADR-0012: provenance is its own field, never folded into a title.
    assert "provenance.origin" in text

    # No fake success: every notice is set after the server answered.
    assert "onSuccess" in text
    assert "isPending" in text, "duplicate submits must be blocked while a write is in flight"

    # The unit is the granted one, and there is no "admin" portal to ask for.
    assert 'grantedPortal(portalAccess, "coordinator")' in text
    assert 'grantedPortal(portalAccess, "admin")' not in text
    assert "getConfiguredUnitId" not in text, (
        "the events page must scope itself by the granted unit, never the build variable"
    )


def test_the_publish_refusal_is_rendered_rather_than_swallowed() -> None:
    """A 422 naming missing fields is the only actionable part of a refusal."""
    text = EVENTS_PAGE.read_text(encoding="utf-8")
    assert "details?.fields" in text
    assert "Complete these fields before publishing" in text


def test_routes_tsx_keeps_every_main_route() -> None:
    text = ROUTES.read_text(encoding="utf-8")
    for literal in MAIN_ROUTE_LITERALS:
        assert f'"{literal}"' in text, f"routes.tsx lost the {literal!r} route"
    assert '"events"' in text
    # The events route now sits in the one Connector shell rather than a
    # separate admin block. Confirm it is a child of `coordinator-portal`.
    shell_start = text.index('path: "coordinator-portal"')
    shell_block = text[shell_start : text.index('path: "volunteer-portal"')]
    assert '{ path: "events"' in shell_block, (
        "the events route must be a child of the Connector Dashboard shell"
    )
    assert '{ path: "speaker-requests"' in shell_block


def test_no_address_main_served_stops_resolving() -> None:
    """Every retired URL redirects to a route this router actually serves."""
    redirects = REDIRECTS.read_text(encoding="utf-8")
    routes = ROUTES.read_text(encoding="utf-8")

    for retired, successor in RETIRED_MAIN_ROUTES.items():
        assert re.search(
            rf'from: "{re.escape(retired)}", to: "{re.escape(successor)}"', redirects
        ), f"{retired} no longer resolves; it must redirect to {successor}"
        segment = successor.rsplit("/", 1)[-1]
        assert f'path: "{segment}"' in routes, (
            f"{retired} redirects to {successor}, which routes.tsx does not register"
        )

    # The table is only a promise until the router is built from it.
    assert "LEGACY_ROUTE_REDIRECTS.map" in routes
    # And an address that never existed gets an honest 404 rather than
    # react-router's stock error screen.
    assert 'path: "*"' in routes
    assert "errorElement: <NotFound />" in routes


def test_connector_shell_nav_carries_one_events_entry() -> None:
    """The Events nav entry survived the shell merge, at the portal address.

    The deleted admin shell's capability-gated section structure
    (``offeredSections``/``requires``) went with it: the one capability pair it
    gated — cold unknown-contact outreach and external speaker acquisition —
    belonged to the retired ``/outreach`` page, which is not restored. The
    Connector shell offers no out-of-scope capability for a gate to remove, so
    asserting a gating mechanism it does not need would pin scaffolding rather
    than behaviour. ``tests/productScope.test.ts`` and
    ``tests/unit/test_cba_scope_policy.py`` still pin the policy itself.
    """
    text = CONNECTOR_SHELL.read_text(encoding="utf-8")
    assert '{ name: "Events", href: "/coordinator-portal/events"' in text

    # The four Option A groups, and one entry per retired admin-shell surface
    # that still has a home.
    for group in ("Inbox", "Coordinate", "People", "Administration"):
        assert f'label: "{group}"' in text, f"the Connector shell lost the {group!r} nav group"
    for href in (
        "/coordinator-portal",
        "/coordinator-portal/speaker-requests",
        "/coordinator-portal/review-queue",
        "/coordinator-portal/match-runs",
        "/coordinator-portal/speaker-contacts",
        "/coordinator-portal/outreach",
        "/coordinator-portal/matching-weights",
    ):
        assert f'href: "{href}"' in text, f"the Connector shell has no nav entry for {href}"

    # The Administration group is a visibility decision over the stored role,
    # never a second portal lookup.
    assert 'hasActiveRole(session.me, "admin")' in text
