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


def test_dispatch_fails_closed_when_verification_is_not_configured():
    """An arbitrary bearer token does not open the dispatch route either.

    **Added when the local development path was.** The worker now knows how
    to accept a plain bearer credential — ``LocalBearerTaskVerifier``, built
    only when ``SMARTMATCH_DEV_SCHEDULER_BEARER_TOKEN`` is configured under
    ``edition=dev`` — and that is precisely the kind of addition that can turn
    a closed door into an open one without anybody noticing, because the
    mechanism is correct and only its *gating* is load-bearing.

    So this asserts the property at the layer that matters: the module-level
    ``app``, built from whatever environment the suite happens to run in,
    which configures none of it. A caller presenting a guessed token must be
    refused, and refused with ``501`` — "nothing here is configured to verify
    you" — rather than ``200``.

    ``tests/unit/test_worker_local_mode.py`` proves the settings-level half
    of the same statement (no token, no queue, and ``build_task_verifier``
    still returning the unconfigured verifier). This is the half that
    exercises the running application, so the two are not redundant: one
    could pass while the other failed if composition ever consulted something
    other than those settings.
    """
    response = client.post(
        "/operations/dispatch",
        headers={"Authorization": "Bearer guessed-local-token"},
    )
    assert response.status_code == 501
    assert "not configured" in response.json()["detail"].lower()


def test_dispatch_rejects_an_unauthenticated_caller():
    """No credential is refused before the 501, and separately from it.

    Kept distinct from the test above because the two failures mean different
    things to an operator — ``401`` is a caller who brought nothing, ``501``
    is a deployment that can verify nothing — and a verifier that collapsed
    them would be hiding one of the two.
    """
    response = client.post("/operations/dispatch")
    assert response.status_code == 401
