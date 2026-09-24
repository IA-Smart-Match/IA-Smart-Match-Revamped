"""Source contract for the coordinator Bookings page (B26 T8a).

``/coordinator-portal/bookings`` lists the unit's confirmed Speaker bookings and
cancels one. This scan pins the four registrations the ``ce2701ff`` pattern needs
(route, nav entry, prefetch, API helper) and the one dialog rule that is easy to
lose in a refactor: the confirm button is a plain button, not an
``AlertDialogAction``, because an Action closes the dialog on click and the
dialog must stay open while the write is in flight and when it is refused.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
FRONTEND_SRC = REPO_ROOT / "apps" / "web" / "legacy-frontend" / "src"

API_LIB = FRONTEND_SRC / "lib" / "api.ts"
ROUTES = FRONTEND_SRC / "app" / "routes.tsx"
LAYOUT = FRONTEND_SRC / "app" / "components" / "CoordinatorPortalLayout.tsx"
PREFETCH = FRONTEND_SRC / "app" / "navPrefetch.ts"
PAGE = FRONTEND_SRC / "app" / "pages" / "coordinator" / "CoordinatorBookings.tsx"


def _code_only(source: str) -> str:
    """Strip block and line comments, so prose about a rule does not satisfy it."""
    without_blocks = re.sub(r"/\*.*?\*/", "", source, flags=re.DOTALL)
    return "\n".join(
        line for line in without_blocks.splitlines() if not line.lstrip().startswith("//")
    )


def _helper_body(source: str, name: str) -> str:
    marker = f"export async function {name}"
    assert marker in source, f"api.ts is missing {name}"
    return source.split(marker, 1)[1].split("\n}", 1)[0]


def test_the_route_is_registered() -> None:
    code = _code_only(ROUTES.read_text(encoding="utf-8"))
    assert 'path: "bookings"' in code
    assert "CoordinatorBookings" in code


def test_the_nav_entry_is_in_the_coordinate_group() -> None:
    code = _code_only(LAYOUT.read_text(encoding="utf-8"))
    assert "/coordinator-portal/bookings" in code
    assert "CalendarCheck" in code
    coordinate = code.split('label: "Coordinate"', 1)[1].split("label:", 1)[0]
    assert '"/coordinator-portal/bookings"' in coordinate, "Bookings belongs in Coordinate"


def test_the_route_is_prefetched_with_the_page_key() -> None:
    code = _code_only(PREFETCH.read_text(encoding="utf-8"))
    assert '"/coordinator-portal/bookings"' in code
    assert 'spec("confirmed-speakers"' in code


def test_the_api_helper_posts_to_the_cancellation_route() -> None:
    helper = _helper_body(API_LIB.read_text(encoding="utf-8"), "cancelBooking")
    assert "/cancellation" in helper
    assert 'method: "POST"' in helper
    assert "authenticated: true" in helper
    assert "encodeURIComponent(unitId)" in helper
    assert "encodeURIComponent(recordId)" in helper


def test_the_page_uses_a_controlled_dialog_not_an_auto_closing_action() -> None:
    code = _code_only(PAGE.read_text(encoding="utf-8"))
    assert "AlertDialogAction" not in code
    assert "onEscapeKeyDown" in code
    assert "onCloseAutoFocus" in code
