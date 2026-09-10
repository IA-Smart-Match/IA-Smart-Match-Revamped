"""Source contract: each principal lands in its own portal, not the coordinator's.

The pilot appliance builds the frontend bundle with a fixture credential
(``VITE_SMARTMATCH_BEARER_TOKEN``) so the stack can be opened without signing
in, and ``docker-compose.yml`` sets that fixture to the token the API maps to
the seeded **coordinator**. A person who then signs in as a student, an event
host, or an administrator gets a real session token in ``sessionStorage`` — and
if the fixture outranks it, every ``/v1`` request still authenticates as the
coordinator. Nothing downstream is wrong in that state and nothing reports an
error: ``GET /v1/me/portals`` truthfully answers "coordinator" and
``pages/Home.tsx`` truthfully forwards to ``/coordinator-portal``. The sign-in
appears to succeed and changes nothing, which is the fake-success shape applied
to identity.

So the rule pinned here is the ordering itself: **a credential this browser was
asked to use outranks the fixture it was merely built with.** The behavioural
proof lives next to the code it guards
(``apps/web/legacy-frontend/tests/bearerToken.test.ts``, a plain-Node test over
the pure resolver); this file is the static half — it holds ``api.ts`` to
delegating that decision rather than re-inlining a second, drifting copy of it,
which is how the reversed order got there in the first place.

Read as text rather than executed, for ``test_frontend_auth_contract.py``'s
reason: what has to be true is that the literal in the shipped file says this,
and no Python-side import of a TypeScript module could say otherwise.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
FRONTEND_LIB = REPO_ROOT / "apps" / "web" / "legacy-frontend" / "src" / "lib"
API_MODULE = FRONTEND_LIB / "api.ts"
BEARER_TOKEN_MODULE = FRONTEND_LIB / "bearerToken.ts"
HOME_PAGE = (
    REPO_ROOT / "apps" / "web" / "legacy-frontend" / "src" / "app" / "pages" / "Home.tsx"
)

# See `test_compose_dev_principals.py` for why `tools/` goes on the path rather
# than the repository root.
sys.path.insert(0, str(REPO_ROOT / "tools"))

from seed_pilot_principals import COMPOSE_DEV_PRINCIPALS  # noqa: E402
from smartmatch_api.routers.portals import _PORTAL_FOR_ROLE  # noqa: E402


def test_the_signed_in_credential_outranks_the_build_time_fixture() -> None:
    """The stored token is consulted first, and the fixture is the fallback.

    Asserted as an exact expression because the ordering *is* the contract: the
    two candidate spellings differ only in which operand comes first, and a
    looser assertion (both names appear) would pass against the reversed one.
    """
    source = BEARER_TOKEN_MODULE.read_text(encoding="utf-8")

    assert "return usableCredential(sessionToken) ?? usableCredential(envToken);" in source, (
        "resolveBearerToken() no longer prefers the signed-in credential: with the "
        "fixture first, every principal signing in to the pilot appliance "
        "authenticates as the seeded coordinator and lands in /coordinator-portal"
    )


def test_api_delegates_the_credential_choice_rather_than_re_inlining_it() -> None:
    """One decision, in one place, that the test above can actually hold.

    ``readSmartmatchBearerToken()`` reads the two sources — ``import.meta.env``
    and ``sessionStorage``, neither of which exists in a plain-Node test — and
    hands them to the resolver. A future edit that folds the choice back into
    this function would put it out of reach of both guards, so the delegation
    is pinned too.
    """
    source = API_MODULE.read_text(encoding="utf-8")

    assert 'from "./bearerToken.ts"' in source
    assert "return resolveBearerToken(envToken, sessionToken);" in source, (
        "readSmartmatchBearerToken() no longer delegates to resolveBearerToken(): "
        "the credential precedence must stay in one testable place"
    )


def test_home_navigates_to_the_server_reported_path_and_composes_none() -> None:
    """`/`'s decision stays the server's answer, not a browser-side guess.

    The landing bug is only visible because ``Home`` is honest: it forwards to
    the ``home_path`` the server reported. If it ever hard-coded a portal, the
    credential fix above would be invisible and the symptom identical.
    """
    source = HOME_PAGE.read_text(encoding="utf-8")

    assert "target.home_path" in source, "Home no longer navigates to the reported home_path"
    for invented in ('"/coordinator-portal"', "'/coordinator-portal'", '"/student-portal"'):
        assert invented not in source, (
            f"Home.tsx names {invented}: the portal path is GET /v1/me/portals' answer "
            "and is never composed in the browser"
        )


def test_each_compose_dev_principal_opens_a_distinct_portal_path() -> None:
    """The server side is not the fault, and this is what says so.

    Four seeded principals, four stored roles, four different shells. If this
    ever collapses, the symptom is identical to the credential bug above and
    the fix is somewhere else entirely — so the two are separated here rather
    than left to be told apart by clicking.
    """
    home_paths = {
        principal.token: _PORTAL_FOR_ROLE[principal.role][1]
        for principal in COMPOSE_DEV_PRINCIPALS
    }

    assert len(set(home_paths.values())) == len(home_paths), (
        f"two compose dev principals share a portal path: {home_paths}"
    )
    coordinator_paths = [
        token for token, path in home_paths.items() if path == "/coordinator-portal"
    ]
    assert coordinator_paths == ["compose-api"], (
        "only the seeded coordinator token may resolve to /coordinator-portal, "
        f"but these do: {coordinator_paths}"
    )
