"""Principal resolution refuses, and refuses *first*, where there is no login.

ADR-0025 D1 makes ``get_current_principal`` unreachable in the class-exercise
scope by not mounting any router that resolves one, and the lifespan builds no
token verifier there. That is composition, and composition is the right place
for the rule — but it is only half a guarantee. ``app.state.token_verifier`` is
``None`` in that process, and two things followed from it that this file pins:

1. ``get_token_verifier`` was annotated ``-> TokenVerifier``. A type annotation
   that is false in a running process is worse than none: every caller
   downstream inherits the lie, and a type checker signs it off. It is now
   ``TokenVerifier | None``, and this file asserts the annotation itself, not
   only the behaviour, because the behaviour could be right while the contract
   a reader relies on is wrong.

2. ``get_current_principal`` consulted ``PilotSessionRepository`` **before** the
   verifier was used, so a pilot session token would have resolved to a subject
   in a process that has no login at all — a second credential path that needs
   no verifier, quietly working. The refusal is now the function's first
   statement, ahead of the header checks and ahead of any repository call, and
   the test below proves the ordering by spying on the repository rather than
   by reading the source.

The refusal is a **503** ``authentication_unavailable``, following the taxonomy
``routers/match_runs.py`` already uses for ``registry_not_ready``: 503 rather
than 500 because nothing is broken, and rather than 401 because no credential
the caller could produce would help — authentication is a capability this
deployment does not offer.

The route below is mounted *only in this test*. No exercise-scope process mounts
a principal-bearing route, and this file does not ask for one to be added; it
asks what would happen if one ever were, which is the only way to test a guard
whose whole purpose is to be unreachable.
"""

from __future__ import annotations

import inspect
from typing import Any

import pytest
from fastapi import APIRouter, FastAPI
from fastapi.testclient import TestClient
from smartmatch_api.dependencies import CurrentPrincipal, get_token_verifier
from smartmatch_api.errors import EXCEPTION_HANDLERS
from smartmatch_providers import TokenVerifier


class _SessionThatIsNeverQueried:
    """Stands in for a request session, and records that nothing asked it anything.

    ``get_session`` resolves before ``get_current_principal`` runs — FastAPI
    builds a dependency's arguments before calling it — so a session *object*
    is created on this path whatever happens. That is not the thing at issue.
    What must not happen is a *query*, and the repository spy below is what
    proves none was made.
    """

    def __init__(self) -> None:
        self.rolled_back = False
        self.closed = False

    def rollback(self) -> None:
        self.rolled_back = True

    def close(self) -> None:
        self.closed = True


@pytest.fixture
def repository_spy(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Replace ``PilotSessionRepository.resolve_subject`` with a recorder.

    Recording rather than raising: a raise would be answered by the 500 handler
    and the test would pass for the wrong reason if the refusal were removed.
    An empty list at the end is the assertion.
    """
    from smartmatch_persistence.pilot_auth import PilotSessionRepository

    calls: list[str] = []

    def _record(self: Any, session: Any, *, token_hash: str) -> str | None:
        calls.append(token_hash)
        return "somebody"

    monkeypatch.setattr(PilotSessionRepository, "resolve_subject", _record)
    return calls


def _app_with_a_principal_bearing_route(*, verifier: TokenVerifier | None) -> FastAPI:
    app = FastAPI()
    for exception_type, handler in EXCEPTION_HANDLERS.items():
        app.add_exception_handler(exception_type, handler)

    router = APIRouter()

    @router.get("/probe")
    def probe(principal: CurrentPrincipal) -> dict[str, str]:
        return {"subject": str(principal.user_id)}

    app.include_router(router)
    app.state.token_verifier = verifier
    app.state.session_factory = _SessionThatIsNeverQueried
    return app


# ---------------------------------------------------------------------------
# The annotation
# ---------------------------------------------------------------------------


def test_the_verifier_dependency_admits_that_it_may_return_none() -> None:
    """The state boundary is typed for what the state actually holds."""
    annotation = inspect.signature(get_token_verifier).return_annotation
    assert annotation == "TokenVerifier | None"


# ---------------------------------------------------------------------------
# The refusal, and its order
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "headers",
    [
        pytest.param({}, id="no-credential"),
        pytest.param({"Authorization": "Bearer a-pilot-session-token"}, id="pilot-session-token"),
        pytest.param({"Authorization": "not-a-bearer-scheme"}, id="malformed-header"),
    ],
)
def test_principal_resolution_refuses_when_there_is_no_login(
    repository_spy: list[str], headers: dict[str, str]
) -> None:
    """503 whatever the caller sent, and the session repository is never consulted.

    The ``pilot-session-token`` case is the load-bearing one. The spy is rigged
    to *succeed* — it returns a subject for any token hash — so if the refusal
    were ordered after ``_subject_for_token`` this request would get past
    authentication in a process with no login. It answers 503 instead, and the
    spy records nothing.
    """
    app = _app_with_a_principal_bearing_route(verifier=None)
    with TestClient(app) as client:
        response = client.get("/probe", headers=headers)

    assert response.status_code == 503
    assert response.json() == {
        "error": {
            "code": "authentication_unavailable",
            "message": "This deployment does not offer authentication.",
        }
    }
    assert repository_spy == [], "the pilot-session repository was consulted before the refusal"


def test_the_refusal_does_not_invite_a_retry_with_a_better_token() -> None:
    """No ``WWW-Authenticate``: there is no scheme that would work here."""
    app = _app_with_a_principal_bearing_route(verifier=None)
    with TestClient(app) as client:
        response = client.get("/probe")
    assert "WWW-Authenticate" not in response.headers


def test_a_process_that_has_a_verifier_still_answers_401(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The guard is about an absent login, not about an unrecognised caller.

    With a verifier present the function behaves exactly as before: the
    credential is examined, the pilot-session path *is* consulted, and an
    unidentifiable caller gets the 401 with its ``WWW-Authenticate`` header.
    Without this, "refuses everything" would pass the test above.
    """
    from smartmatch_persistence.pilot_auth import PilotSessionRepository

    consulted: list[str] = []

    def _no_such_session(self: Any, session: Any, *, token_hash: str) -> str | None:
        consulted.append(token_hash)
        return None

    monkeypatch.setattr(PilotSessionRepository, "resolve_subject", _no_such_session)

    class _RejectingVerifier:
        def verify(self, token: str) -> Any:
            from smartmatch_providers import TokenVerificationError

            raise TokenVerificationError("no")

    app = _app_with_a_principal_bearing_route(verifier=_RejectingVerifier())  # type: ignore[arg-type]
    with TestClient(app) as client:
        response = client.get("/probe", headers={"Authorization": "Bearer something"})

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthenticated"
    assert response.headers["WWW-Authenticate"] == "Bearer"
    assert consulted != [], "the pilot-session path must still run where there is a login"
