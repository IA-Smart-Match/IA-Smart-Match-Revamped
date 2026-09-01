"""Source contract for Fix #7A: no caller-chosen login roles in legacy frontend."""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
LOGIN_PAGE = (
    REPO_ROOT / "apps" / "web" / "legacy-frontend" / "src" / "app" / "pages" / "LoginPage.tsx"
)
LANDING_PAGE = (
    REPO_ROOT / "apps" / "web" / "legacy-frontend" / "src" / "app" / "pages" / "LandingPage.tsx"
)

CANNED_LOGIN_EMAILS = (
    "alex.rivera@cal.edu",
    "jordan.lee@cpp.edu",
    "admin@iawest.org",
    "shana.demarinis@testset.com",
)

FORBIDDEN_LOGIN_PATTERNS = (
    "?role=",
    "useSearchParams",
    "selectedRole",
    'sessionStorage.setItem("iaw_session"',
    "handleLogin",
    "const ROLES",
)


def test_login_page_has_no_caller_chosen_role_affordances() -> None:
    source = LOGIN_PAGE.read_text(encoding="utf-8")
    for pattern in FORBIDDEN_LOGIN_PATTERNS:
        assert pattern not in source, f"LoginPage still contains forbidden pattern: {pattern!r}"
    for email in CANNED_LOGIN_EMAILS:
        assert email not in source, f"LoginPage still contains canned login email: {email!r}"


def test_login_page_states_institutional_sign_in_is_not_connected() -> None:
    source = LOGIN_PAGE.read_text(encoding="utf-8")
    assert "Institutional sign-in is not connected yet" in source
    assert "A1b" in source
    assert 'type="submit"' not in source
    assert "<form" not in source


def test_landing_page_has_no_role_bearing_login_links() -> None:
    source = LANDING_PAGE.read_text(encoding="utf-8")
    assert "?role=" not in source
    for label in ("Student Portal", "Event Coordinator"):
        assert label not in source, f"LandingPage still contains role-specific CTA: {label!r}"
