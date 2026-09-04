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


def test_login_page_offers_a_credential_form_and_nothing_else() -> None:
    """The pilot login exists, and it takes a credential — not a role.

    This replaces an assertion that the page said "Institutional sign-in is not
    connected yet" and carried no ``<form`` at all. That was the right contract
    while there was nothing to sign in with; the owner authorized a
    pilot-scoped login on 2026-09-04
    (``docs/decisions/pilot-login-decision-2026-09-04.md``), so the page now has
    a form and the old assertions would pin a dead screen in place.

    What is asserted instead is the property those assertions were *protecting*.
    A form is not the defect Fix #7 named — a form that lets the visitor choose
    who they are is. So: exactly two credential inputs, no role/tenant/unit
    control, and no canned identities to pick from
    (:data:`FORBIDDEN_LOGIN_PATTERNS` and :data:`CANNED_LOGIN_EMAILS` are
    checked by the test above and are unchanged).
    """
    source = LOGIN_PAGE.read_text(encoding="utf-8")

    # The login is real: it posts a credential and submits.
    assert "postLogin(" in source, "the login page does not call POST /v1/auth/login"
    assert 'type="submit"' in source
    assert "<form" in source

    # ...and the credential is all it sends. One email input, one password
    # input, and no third field of any kind.
    assert source.count('name="email"') == 1
    assert source.count('name="password"') == 1
    for forbidden in ('name="role"', 'name="tenant', 'name="unit', "<select"):
        assert forbidden not in source, (
            f"LoginPage offers {forbidden!r}: the browser must supply a "
            "credential and never a role, tenant, or unit"
        )

    # A1b is still named, because it is still blocked and the page says so
    # rather than implying this is institutional sign-in.
    assert "A1b" in source
    assert "pilot" in source.lower()


def test_login_page_stores_a_credential_and_never_an_identity() -> None:
    """What the page does with the response: store a token, then ask who it is.

    The archived defect wrote an identity into browser storage. This page writes
    the opaque token and then re-resolves through ``GET /v1/me``, so the only
    thing the browser holds is a credential the server interprets.
    """
    source = LOGIN_PAGE.read_text(encoding="utf-8")
    assert "storeSmartmatchBearerToken(issued.access_token)" in source
    # It must not lift any identity field out of the login response.
    for asserted in ("issued.user_id", "issued.role", "issued.tenant_id", "issued.memberships"):
        assert asserted not in source, (
            f"LoginPage reads {asserted!r} from the login response; identity is "
            "GET /v1/me's answer alone"
        )


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

#: The pages that live inside a portal shell and therefore need the mapping
#: seam: ``useAuthenticatedPrincipal()`` for the server's answer to who the
#: caller is, then ``usePortalAccess()`` / ``grantedPortal()`` for the server's
#: answer to which portal they hold, and never a local session reader or a
#: locally derived role-to-portal rule in between.
#:
#: These pages no longer *call* ``/api/portals/*``: that backend is not part of
#: this repository, so each renders an explicit unavailable panel naming the
#: dataset instead of a request that cannot succeed. They still need the seam,
#: because they still render who the caller is and which unit they hold.
#:
#: Membership is decided by whether a page calls such an endpoint, not by which
#: portal it lives in. See :data:`PAGES_WITH_NO_LEGACY_PORTAL_ID` for the pages
#: that need no mapping at all, and
#: :func:`test_no_portal_page_reads_identity_locally` for the assertion that
#: holds over every page either way.
PORTAL_PAGES = (
    "app/pages/student/StudentHome.tsx",
    "app/pages/student/StudentEvents.tsx",
    "app/pages/student/StudentHistory.tsx",
    "app/pages/student/StudentConnect.tsx",
    "app/pages/coordinator/CoordinatorHome.tsx",
    "app/pages/coordinator/CoordinatorEvents.tsx",
    "app/pages/coordinator/CoordinatorOutreach.tsx",
    "app/pages/coordinator/CoordinatorMeetings.tsx",
    "app/pages/volunteer/VolunteerHome.tsx",
    "app/pages/volunteer/VolunteerAssignments.tsx",
    "app/pages/volunteer/VolunteerProfile.tsx",
)

#: Portal pages that need **no** legacy portal id, because every request they
#: make is a ``/v1`` one carrying the bearer token, and the server resolves the
#: subject from that token itself.
#:
#: ``StudentRewards.tsx`` is the first member, and it moved here rather than out
#: of this file: before card P-REWARDS-API it computed points in the browser and
#: fetched ``/api/portals/students/{id}`` to do it, which is why it needed the
#: seam. It now calls ``GET /v1/units/{unit_id}/rewards`` and
#: ``/v1/units/{unit_id}/redemptions``, whose subject is ``principal.user_id``
#: server-side and cannot be named by the client at all. Asserting
#: ``portalSubjectId(principal, ...)`` on it would now require it to derive an
#: identifier it must not send — a weaker position than the one it holds.
#:
#: This tuple is not an exemption from the Fix #7 guard. Every assertion in this
#: file that is really about browser-asserted identity —
#: :func:`test_no_page_reads_the_archived_session_blob`,
#: :func:`test_no_fallback_identity_literal_survives`,
#: :func:`test_no_page_touches_session_storage_directly` and
#: :func:`test_no_portal_page_reads_identity_locally` — runs over both tuples,
#: or over every source file, and none of them is relaxed here.
PAGES_WITH_NO_LEGACY_PORTAL_ID = ("app/pages/student/StudentRewards.tsx",)

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


def _without_block_comments(source: str) -> str:
    """``source`` with every ``/* ... */`` block removed.

    For assertions that a *construct* is absent rather than a string. A file
    that documents what it used to do — which is most of the ones this module
    guards — otherwise fails a check on the very name it is explaining, and the
    usual response to that is to stop explaining, which is the wrong trade.
    Line comments are left alone: they are rare in this codebase and none of
    them has caused a false match.
    """
    return re.sub(r"/\*.*?\*/", "", source, flags=re.DOTALL)


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
    """Each portal page reads both server answers, and derives neither itself.

    The seam used to be ``portalSubjectId(principal, ...)``, which returned
    ``null`` unconditionally because no account-to-portal mapping existed.
    ``GET /v1/me/portals`` is that mapping, so the seam is now the pair:
    ``useAuthenticatedPrincipal()`` for who the caller is and
    ``usePortalAccess()`` / ``grantedPortal()`` for what the server granted
    them. Both are server answers; neither is computed here.
    """
    for relative in PORTAL_PAGES:
        source = (WEB_SRC / relative).read_text(encoding="utf-8")
        assert "useAuthenticatedPrincipal()" in source, (
            f"{relative} does not resolve its principal from GET /v1/me"
        )
        assert "usePortalAccess()" in source, (
            f"{relative} does not read the account-to-portal mapping"
        )
        assert "grantedPortal(portalAccess," in source, (
            f"{relative} bypasses the account-to-portal mapping seam"
        )
        assert "getSession" not in source, f"{relative} still has a local session reader"


def test_no_portal_page_derives_a_portal_from_a_role_it_read() -> None:
    """The browser must not reimplement the role-to-portal rule.

    It would usually agree with the server, which is exactly the danger: two
    copies of one rule drift, and the browser's copy is the one that is wrong
    and the one nobody checks. The rule lives in
    ``services/api/smartmatch_api/routers/portals.py`` and reaches the frontend
    only as data.
    """
    for relative in PORTAL_PAGES + PORTAL_SHELLS:
        source = (WEB_SRC / relative).read_text(encoding="utf-8")
        for derivation in (
            'role === "coordinator"',
            'role === "student"',
            'role === "volunteer"',
            'role === "admin"',
            'includes("coordinator")',
            'includes("student")',
        ):
            assert derivation not in source, (
                f"{relative} decides a portal from a role it read ({derivation!r}). "
                "Ask GET /v1/me/portals instead."
            )


def test_no_portal_page_reads_identity_locally() -> None:
    """The Fix #7 guard itself, over *every* portal page and not only the mapped ones.

    :func:`test_every_portal_page_uses_the_server_mapping_seam` is about a
    narrower thing — that a page needing a *legacy portal id* derives it through
    the seam — and a page that needs no such id has nothing for it to assert.
    That must not become a hole: the property that actually matters is that no
    page reads its own identity, and it is stated here over both tuples so a
    page cannot escape it by moving between them.

    A page in :data:`PAGES_WITH_NO_LEGACY_PORTAL_ID` is held to *more*, not
    less: it must not name a legacy portal id at all, because a page that sends
    only ``/v1`` requests has no honest use for one and reintroducing it would be
    a caller-supplied subject arriving by the back door.
    """
    for relative in PORTAL_PAGES + PAGES_WITH_NO_LEGACY_PORTAL_ID:
        source = (WEB_SRC / relative).read_text(encoding="utf-8")
        assert "getSession" not in source, f"{relative} still has a local session reader"
        assert ARCHIVED_SESSION_KEY not in source, (
            f"{relative} mentions the archived browser session blob"
        )

    for relative in PAGES_WITH_NO_LEGACY_PORTAL_ID:
        source = (WEB_SRC / relative).read_text(encoding="utf-8")
        assert "portalSubjectId(" not in source, (
            f"{relative} derives a legacy portal id from a helper that no longer "
            "exists. Every subject it needs is resolved server-side from the "
            "bearer token."
        )


def test_account_uuid_is_not_reused_as_a_legacy_portal_id() -> None:
    """The mapping is the server's, and it is still not an account UUID.

    ``portalSubjectId`` used to answer ``null`` for everything, because the only
    mapping available was one the browser would have had to invent. That guard
    is kept in substance: the helper that replaced it is a *lookup into the
    server's response* (``portalGrant``), and it still never falls back to
    ``me.user_id``. The legacy ``/api/portals/*`` seam and its error stay in the
    client, unused, so that nothing quietly starts guessing an id.
    """
    principal_source = PRINCIPAL_HELPERS.read_text(encoding="utf-8")
    api_source = API_CLIENT.read_text(encoding="utf-8")

    assert "return me.user_id" not in principal_source
    # The replacement reads the server's answer rather than deriving one.
    assert "export function portalGrant(" in principal_source
    assert "mapping.portals.find(" in principal_source
    # Checked against the code, not the prose. `principal.ts` explains what
    # `portalSubjectId()` was and why it is gone — in `portalGrant`'s own
    # doc comment, not only the module one — and a guard its guarded file
    # cannot describe without failing is a guard nobody keeps. Same intent as
    # `test_the_session_gate_sends_unverified_visitors_to_login`'s split, but
    # over every block comment rather than just the first.
    assert "portalSubjectId(" not in _without_block_comments(principal_source), (
        "the null-returning seam should be gone, replaced by portalGrant()"
    )
    assert "PortalSubjectUnavailableError" in api_source
    assert "portalSubjectPath" in api_source
    # The mapping route is the one the shells consume.
    assert "/v1/me/portals" in api_source


def test_the_portal_mapping_is_fetched_and_never_computed() -> None:
    """One caller of `fetchMyPortals()`, as there is one caller of `fetchMe()`."""
    callers = sorted(
        _web_relative(path)
        for path in _web_sources()
        if re.search(r"(?<!`)fetchMyPortals\(\)(?!`)", path.read_text(encoding="utf-8"))
    )
    assert callers == ["app/hooks/usePortalAccess.tsx", "lib/api.ts"], (
        f"fetchMyPortals() appears in {callers}; the mapping is resolved by "
        "usePortalAccess alone, so every shell sees the same server answer."
    )


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
