"""Source contract for the portal switcher (B26 T6b-5 §6, §8.2).

One login, two roles: the switcher lists portals the server already granted and
grants nothing. These scans hold what a source scan can reach:

- ``PortalSwitcher.tsx`` imports no API adapter and makes no request;
- both two-portal shells (Event Host, Speaker) render it twice — sidebar and
  mobile header — and the sidebar one sits above the profile block, so Sign out
  stays directly beneath the profile (``apps/web/DESIGN.md``, Signed-in shells);
- ``portalChoice.ts`` touches ``localStorage`` only inside ``try`` and stores a
  portal id, never a principal, token or user id;
- sign-out forgets the choice, and ``/`` still navigates to a server-reported
  ``home_path``.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
FRONTEND_SRC = REPO_ROOT / "apps" / "web" / "legacy-frontend" / "src"

SWITCHER = FRONTEND_SRC / "app" / "components" / "PortalSwitcher.tsx"
CHOICE = FRONTEND_SRC / "lib" / "portalChoice.ts"
HOME = FRONTEND_SRC / "app" / "pages" / "Home.tsx"
SESSION_HOOK = FRONTEND_SRC / "app" / "hooks" / "useSession.tsx"

#: Shell file → the portal id it passes as ``current``.
SHELLS = {
    FRONTEND_SRC / "app" / "components" / "VolunteerPortalLayout.tsx": "volunteer",
    FRONTEND_SRC / "app" / "components" / "SpeakerPortalLayout.tsx": "speaker",
}

#: Shells that never hold two portals from this track (Q1: a staff or student
#: login is never merged with a Speaker role).
NO_SWITCHER_SHELLS = (
    FRONTEND_SRC / "app" / "components" / "CoordinatorPortalLayout.tsx",
    FRONTEND_SRC / "app" / "components" / "StudentLayout.tsx",
)

PERSONA_LABELS = ("Student", "Event Host", "Speaker Connector", "Speaker Portal")


def _code_only(source: str) -> str:
    """``source`` without ``/* … */`` blocks and ``//`` line comments."""
    without_blocks = re.sub(r"/\*.*?\*/", "", source, flags=re.DOTALL)
    return re.sub(r"(?m)^\s*//.*$|\s//.*$", "", without_blocks)


def test_the_switcher_makes_no_request() -> None:
    source = _code_only(SWITCHER.read_text(encoding="utf-8"))
    for forbidden in (
        "lib/api",
        "fetch(",
        "requestJson",
        "useQuery",
        "useMutation",
        "XMLHttpRequest",
    ):
        assert forbidden not in source, f"PortalSwitcher.tsx references {forbidden!r}"


def test_the_switcher_names_portals_by_the_server_s_display_name_only() -> None:
    source = _code_only(SWITCHER.read_text(encoding="utf-8"))
    assert ".display_name" in source
    assert ".home_path" in source
    for label in PERSONA_LABELS:
        assert f'"{label}' not in source, f"PortalSwitcher.tsx hardcodes {label!r}"
    assert 'role="menu"' not in source, "a disclosure of links, not a menu"


def test_both_shells_render_the_switcher_above_the_profile_and_in_the_header() -> None:
    for shell, portal in SHELLS.items():
        source = shell.read_text(encoding="utf-8")
        code = _code_only(source)
        assert code.count("<PortalSwitcher") == 2, f"{shell.name}: one switcher per breakpoint"
        sidebar = code.index(f'<PortalSwitcher current="{portal}" placement="sidebar"')
        sign_out = code.rindex("Sign out")
        # The profile block's avatar, the last one before Sign out.
        identity = code.rindex("rounded-full bg-primary", 0, sign_out)
        assert sidebar < identity, f"{shell.name}: the sidebar switcher sits above the profile"
        assert "<PortalSwitcher" not in code[identity:sign_out], (
            f"{shell.name}: nothing may sit between the profile and Sign out"
        )
        assert f'<PortalSwitcher current="{portal}" placement="header"' in code


def test_the_connector_and_student_shells_have_no_switcher() -> None:
    for shell in NO_SWITCHER_SHELLS:
        assert "PortalSwitcher" not in shell.read_text(encoding="utf-8"), shell.name


def test_portal_choice_touches_local_storage_only_inside_try() -> None:
    code = _code_only(CHOICE.read_text(encoding="utf-8"))
    total = code.count("localStorage")
    assert total >= 3, "read, write and forget each reach localStorage"
    inside_try = sum(
        block.count("localStorage") for block in re.findall(r"try\s*\{([^{}]*)\}", code)
    )
    assert inside_try == total, "every localStorage access is inside a try block"
    for forbidden in ("sessionStorage", "user_id", "access_token", "principal", "fetch("):
        assert forbidden not in code, f"portalChoice.ts references {forbidden!r}"


def test_sign_out_forgets_the_remembered_portal() -> None:
    code = _code_only(SESSION_HOOK.read_text(encoding="utf-8"))
    sign_out = code.index("const signOut = useCallback(")
    assert "forgetRememberedPortal()" in code[sign_out : code.index("const retry", sign_out)]


def test_home_reads_the_remembered_portal_and_still_navigates_to_home_path() -> None:
    code = _code_only(HOME.read_text(encoding="utf-8"))
    assert "readRememberedPortal(" in code
    assert "mapping.default_portal" in code
    assert "target.home_path" in code
