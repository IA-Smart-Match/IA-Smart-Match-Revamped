"""Worker boundary contract tests.

The worker is private and consequential. These tests assert that the shipped
application — the one uvicorn serves, built from whatever environment it finds —
fails closed before it does anything.

They deliberately exercise the *default* worker rather than a configured one.
Verification being correct when configured is proved in
``tests/integration/test_worker_execution.py``, with real tokens and real keys;
what is proved here is the property that survives someone forgetting to
configure it.
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


def test_task_execution_fails_closed_when_verification_is_not_configured():
    """An unconfigured deployment refuses everything, exactly as the stub did.

    **Changed in J6, deliberately.** Real OIDC verification now exists, so 501 no
    longer means "the control is missing from the codebase"; it means this
    process has no audience, no service-account allowlist, and no signature
    backend, so there is nothing to verify against. The wording moved from "not
    implemented" to "not configured" to say that accurately.

    The status code and the property it guards are unchanged, and that is the
    point of keeping this test: the module-level ``app`` is built from an
    environment that configures none of it, and it must still be a closed door.
    A verifier that treated missing configuration as nothing to check would be
    the one regression that turns this endpoint into an open one.
    """
    response = client.post(
        "/tasks/execute",
        json={"command_type": "noop"},
        headers={"Authorization": "Bearer anything"},
    )
    assert response.status_code == 501
    assert "not configured" in response.json()["detail"].lower()


def test_worker_exposes_no_command_routes_beyond_the_task_target():
    """Commands are executed through the one task endpoint, never as routes.

    Handlers were added in J7, and none of them brought a route with it: the
    worker is reachable only by Cloud Tasks, and a per-command HTTP route would
    be a second way in that nothing verifies.

    ``/operations/dispatch`` was added by J8 and is listed here deliberately
    rather than excluded by prefix. It is not a command route — it carries no
    body, names no job, and executes nothing; it runs one dispatcher pass for
    Cloud Scheduler. It is a second door, though, and it is verified by its own
    OIDC identity against its own allowlist, which is what this file exists to
    keep true. Its fail-closed behaviour is asserted in
    ``tests/integration/test_scheduled_dispatch.py``.
    """
    paths = {route.path for route in app.routes}  # type: ignore[attr-defined]
    business_paths = {
        p for p in paths if not p.startswith(("/health", "/openapi", "/docs", "/redoc"))
    }
    assert business_paths == {"/tasks/execute", "/operations/dispatch"}
