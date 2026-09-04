"""Source contract for Fix #7A: no caller-chosen login roles in legacy frontend."""

from __future__ import annotations

import re
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


# ---------------------------------------------------------------------------
# Fix #7 residue: no browser-asserted identity anywhere in the frontend
#
# Plan P2 card A3 (`docs/plans/2026-08-28-a1b-institutional-sign-in-plan.md`).
# The portal shells used to read a session blob out of `sessionStorage` and,
# because nothing ever wrote it, fall back to a hard-coded id per portal — so
# any visitor at all was rendered as a fixture person. These assertions are
# the guard that the reads and the fallbacks stay gone, and that what replaced
# them is the server's own answer to `GET /v1/me`.
# ---------------------------------------------------------------------------

WEB_SRC = REPO_ROOT / "apps" / "web" / "legacy-frontend" / "src"

#: The browser-written session blob. No reader, no writer, no mention.
ARCHIVED_SESSION_KEY = "iaw_session"

#: The per-portal identities the archived reads fell back to.
FALLBACK_IDENTITY_LITERALS = ("stu-001", "coord-001", "shana-demarinis")

PORTAL_SHELLS = (
    "app/components/StudentLayout.tsx",
    "app/components/CoordinatorPortalLayout.tsx",
    "app/components/VolunteerPortalLayout.tsx",
    "app/components/Layout.tsx",
)

PORTAL_PAGES = (
    "app/pages/student/StudentHome.tsx",
    "app/pages/student/StudentEvents.tsx",
    "app/pages/student/StudentHistory.tsx",
    "app/pages/student/StudentConnect.tsx",
    "app/pages/student/StudentRewards.tsx",
    "app/pages/coordinator/CoordinatorHome.tsx",
    "app/pages/coordinator/CoordinatorEvents.tsx",
    "app/pages/coordinator/CoordinatorOutreach.tsx",
    "app/pages/coordinator/CoordinatorMeetings.tsx",
    "app/pages/volunteer/VolunteerHome.tsx",
    "app/pages/volunteer/VolunteerAssignments.tsx",
    "app/pages/volunteer/VolunteerProfile.tsx",
)

#: `sessionStorage` is legitimate for exactly one thing: holding the bearer
#: token `/v1` requests are sent with. One module touches it, for that key and
#: nothing else — no identity, no role, no tenant.
BEARER_TOKEN_MODULE = "lib/api.ts"
PRINCIPAL_HELPERS = WEB_SRC / "lib" / "principal.ts"
API_CLIENT = WEB_SRC / "lib" / "api.ts"

#: A real read/write, as opposed to a mention of the API in prose.
STORAGE_ACCESS = re.compile(r"sessionStorage\.(?:get|set|remove)Item\(")

#: A real call, as opposed to a docstring reference (which is backticked).
FETCH_ME_CALL = re.compile(r"(?<!`)fetchMe\(\)(?!`)")


def _web_sources() -> list[Path]:
    return sorted(
        path for path in WEB_SRC.rglob("*") if path.is_file() and path.suffix in {".ts", ".tsx"}
    )


def _web_relative(path: Path) -> str:
    """Return one stable path spelling on Windows and POSIX runners."""
    return path.relative_to(WEB_SRC).as_posix()


def test_the_archived_session_blob_is_read_and_written_nowhere() -> None:
    offenders = [
        _web_relative(path)
        for path in _web_sources()
        if ARCHIVED_SESSION_KEY in path.read_text(encoding="utf-8")
    ]
    assert not offenders, (
        f"{ARCHIVED_SESSION_KEY!r} still appears in: {offenders}. "
        "Identity comes from GET /v1/me, never from browser storage."
    )


def test_no_fallback_identity_literal_remains() -> None:
    offenders: list[str] = []
    for path in _web_sources():
        source = path.read_text(encoding="utf-8")
        for literal in FALLBACK_IDENTITY_LITERALS:
            if literal in source:
                offenders.append(f"{path.relative_to(WEB_SRC)}: {literal}")
    assert not offenders, (
        f"fallback identities still present: {offenders}. A portal that cannot "
        "name its principal must say so, not substitute a canned one."
    )


def test_sessionstorage_is_only_used_for_the_bearer_token() -> None:
    """Storage may hold a credential. It may never hold an identity."""
    offenders = [
        _web_relative(path)
        for path in _web_sources()
        if STORAGE_ACCESS.search(path.read_text(encoding="utf-8"))
        and _web_relative(path) != BEARER_TOKEN_MODULE
    ]
    assert not offenders, (
        f"unexpected sessionStorage access in: {offenders}. Only "
        f"{BEARER_TOKEN_MODULE} may touch it, and only for the bearer token."
    )


def test_only_the_session_module_resolves_identity() -> None:
    """`fetchMe()` has one caller, so there is one place identity can come from."""
    callers = sorted(
        _web_relative(path)
        for path in _web_sources()
        if FETCH_ME_CALL.search(path.read_text(encoding="utf-8"))
    )
    # lib/api.ts is the declaration; lib/session.ts is the only call site.
    assert callers == ["lib/api.ts", "lib/session.ts"], (
        f"fetchMe() appears in {callers}; identity resolution belongs to "
        "lib/session.ts alone, so every consumer sees the same server answer."
    )


def test_every_portal_shell_gates_on_the_server_session() -> None:
    for relative in PORTAL_SHELLS:
        source = (WEB_SRC / relative).read_text(encoding="utf-8")
        assert "useSession()" in source, f"{relative} does not read the session"
        assert "SessionGate" in source, (
            f"{relative} does not render the signed-out/loading gate; an "
            "unverified visitor must never be shown portal chrome"
        )
        assert 'session.status !== "signed-in"' in source, (
            f"{relative} renders its shell without first requiring a signed-in session"
        )


def test_the_session_gate_sends_unverified_visitors_to_login() -> None:
    source = (WEB_SRC / "app" / "components" / "SessionGate.tsx").read_text(encoding="utf-8")
    assert '<Navigate to="/login" replace />' in source
    # The gate renders instead of the shell, never around it: it accepts no
    # children, so a loading or signed-out state cannot leak portal chrome.
    # Checked against the code below the module docstring, which discusses it.
    code = source.split("*/", 1)[1]
    assert "children" not in code
    # An outage and a suspension are not "sign-in is not connected"; sending
    # either to /login would blame the wrong thing.
    assert 'state.reason === "unreachable"' in source
    assert 'state.reason === "suspended"' in source


def test_every_portal_page_uses_the_server_mapping_seam() -> None:
    for relative in PORTAL_PAGES:
        source = (WEB_SRC / relative).read_text(encoding="utf-8")
        assert "useAuthenticatedPrincipal()" in source, (
            f"{relative} does not resolve its principal from GET /v1/me"
        )
        assert "portalSubjectId(principal," in source, (
            f"{relative} bypasses the account-to-portal mapping seam"
        )
        assert "getSession" not in source, f"{relative} still has a local session reader"


def test_account_uuid_is_not_reused_as_a_legacy_portal_id() -> None:
    """No mapping is safer than crossing two unrelated identifier namespaces."""
    principal_source = PRINCIPAL_HELPERS.read_text(encoding="utf-8")
    api_source = API_CLIENT.read_text(encoding="utf-8")

    assert "return me.user_id" not in principal_source
    assert "portalSubjectId(_me: MeResponse, _portal: PortalKind)" in principal_source
    assert "return null;" in principal_source
    assert "PortalSubjectUnavailableError" in api_source
    assert "portalSubjectPath" in api_source


def test_the_session_module_admits_only_a_verified_active_principal() -> None:
    """Every non-answer is signed out. There is no partial state."""
    source = (WEB_SRC / "lib" / "session.ts").read_text(encoding="utf-8")
    for reason in ('"no-token"', '"rejected"', '"suspended"', '"unreachable"'):
        assert reason in source, f"session.ts does not account for {reason}"
    assert "hasSmartmatchAuth()" in source
    # A suspended account is verified but withdrawn: /v1/me admits it so it can
    # learn that, and every other route denies it. It is not a portal session.
    assert "if (me.suspended) {" in source
    # A 200 body that is not a principal must not reach the layouts as one.
    assert "isPrincipal(me)" in source
    for forbidden in ("mockLogin", "role:", "tenant_id:"):
        assert forbidden not in source, f"session.ts asserts {forbidden!r} client-side"


def test_the_archived_browser_login_shim_is_absent() -> None:
    """The archived `mockLogin` helper, named in camelCase so
    `tools/scan_forbidden.py`'s rule matches the code it guards, not this
    guard.
    """
    offenders = [
        _web_relative(path)
        for path in _web_sources()
        if "mockLogin" in path.read_text(encoding="utf-8")
    ]
    assert not offenders, f"mockLogin resurfaced in: {offenders}"
