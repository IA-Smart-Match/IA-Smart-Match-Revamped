"""B-07 seam: no credential branch returns a principal without the server-side load.

Both credential kinds (pilot session, verifier-accepted token) resolve only to a
bare subject. ``PrincipalRepository.load_by_subject`` is the single place tenant,
unit and role are read, so a principal must be exactly what it returned, and
``None`` from it must be a 401.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest
from fastapi import APIRouter, FastAPI
from fastapi.testclient import TestClient
from smartmatch_api.dependencies import CurrentPrincipal
from smartmatch_api.errors import EXCEPTION_HANDLERS


class _Session:
    def rollback(self) -> None: ...

    def close(self) -> None: ...


class _AcceptingVerifier:
    def verify(self, token: str) -> Any:
        return SimpleNamespace(subject="subject-from-verifier")


class _RejectingVerifier:
    def verify(self, token: str) -> Any:
        from smartmatch_providers import TokenVerificationError

        raise TokenVerificationError("no")


def _client() -> tuple[TestClient, dict[str, Any]]:
    app = FastAPI()
    for exception_type, handler in EXCEPTION_HANDLERS.items():
        app.add_exception_handler(exception_type, handler)
    router = APIRouter()

    @router.get("/probe")
    def probe(principal: CurrentPrincipal) -> dict[str, str]:
        return {"user_id": str(principal.user_id)}

    app.include_router(router)
    app.state.session_factory = _Session
    return TestClient(app), {"app": app}


# (pilot subject or None, verifier, expected subject passed to the load)
KINDS = [
    pytest.param("subject-from-pilot", _RejectingVerifier(), "subject-from-pilot", id="pilot"),
    pytest.param(None, _AcceptingVerifier(), "subject-from-verifier", id="verifier"),
]


def _stub(monkeypatch: pytest.MonkeyPatch, pilot: str | None, loaded: Any) -> list[str]:
    from smartmatch_persistence.pilot_auth import PilotSessionRepository

    from smartmatch_api.dependencies import PrincipalRepository

    loads: list[str] = []

    def _resolve(self: Any, session: Any, *, token_hash: str) -> str | None:
        return pilot

    def _load(self: Any, session: Any, *, external_subject: str) -> Any:
        loads.append(external_subject)
        return loaded

    monkeypatch.setattr(PilotSessionRepository, "resolve_subject", _resolve)
    monkeypatch.setattr(PrincipalRepository, "load_by_subject", _load)
    return loads


@pytest.mark.parametrize(("pilot", "verifier", "subject"), KINDS)
def test_principal_is_what_the_server_side_load_returned(
    monkeypatch: pytest.MonkeyPatch, pilot: str | None, verifier: Any, subject: str
) -> None:
    loads = _stub(monkeypatch, pilot, SimpleNamespace(user_id="loaded-user"))
    client, handles = _client()
    handles["app"].state.token_verifier = verifier
    with client:
        response = client.get("/probe", headers={"Authorization": "Bearer t"})

    assert response.status_code == 200
    assert response.json() == {"user_id": "loaded-user"}
    assert loads == [subject]


@pytest.mark.parametrize(("pilot", "verifier", "subject"), KINDS)
def test_no_loaded_account_is_a_401_for_both_credential_kinds(
    monkeypatch: pytest.MonkeyPatch, pilot: str | None, verifier: Any, subject: str
) -> None:
    loads = _stub(monkeypatch, pilot, None)
    client, handles = _client()
    handles["app"].state.token_verifier = verifier
    with client:
        response = client.get("/probe", headers={"Authorization": "Bearer t"})

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthenticated"
    assert loads == [subject], "the load must run, and be what denies"
