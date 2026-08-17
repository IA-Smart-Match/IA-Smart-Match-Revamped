"""Worker boundary contract tests.

The worker is private and consequential. These tests assert it fails closed
before it does anything, which is the property that matters most while the
command handlers are unimplemented.
"""

from __future__ import annotations

from fastapi.testclient import TestClient
from smartmatch_worker.main import app

client = TestClient(app)


def test_health_is_available():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_task_execution_rejects_an_unauthenticated_caller():
    """No credentials means 401, before any work is attempted."""
    response = client.post("/tasks/execute", json={"command_type": "noop"})
    assert response.status_code == 401


def test_task_execution_fails_closed_even_with_a_bearer_token():
    """The scaffold's identity verification is a stub that rejects everything.

    A permissive stub would let unverified callers reach command dispatch the
    moment a handler is added. 501 makes the missing control explicit rather
    than silently absent.
    """
    response = client.post(
        "/tasks/execute",
        json={"command_type": "noop"},
        headers={"Authorization": "Bearer anything"},
    )
    assert response.status_code == 501
    assert "not implemented" in response.json()["detail"].lower()


def test_worker_exposes_no_command_routes_yet():
    """Command handlers arrive with their releases and their gates."""
    paths = {route.path for route in app.routes}  # type: ignore[attr-defined]
    business_paths = {
        p for p in paths if not p.startswith(("/health", "/openapi", "/docs", "/redoc"))
    }
    assert business_paths == {"/tasks/execute"}
