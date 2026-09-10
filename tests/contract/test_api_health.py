"""API contract tests for the Foundation surface."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from smartmatch_api.main import app


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def test_health_reports_ok(client: TestClient):
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_health_leaks_no_dependency_or_topology_detail():
    """v1.1 §1.11: public health endpoints expose no dependency or topology detail."""
    body = TestClient(app).get("/api/health").json()
    serialized = str(body).lower()

    for leaked in (
        "postgres",
        "database",
        "database_url",
        "localhost",
        "queue",
        "cloud",
        "resend",
        "api_key",
        "secret",
        "password",
        "5432",
    ):
        assert leaked not in serialized, f"health response leaks {leaked!r}"


def test_health_response_keys_are_minimal():
    body = TestClient(app).get("/api/health").json()
    assert set(body) == {"status", "release"}


# ---------------------------------------------------------------------------
# The archived legacy surface must not exist
# ---------------------------------------------------------------------------


def test_mock_login_endpoint_does_not_exist():
    """Caller-selected identity is archived (legacy portals.py:435)."""
    response = TestClient(app).post("/auth/mock-login", json={"role": "admin"})
    assert response.status_code == 404


def test_no_route_advertises_a_mock_or_demo_login():
    """Checked against the published contract, not the route table.

    ``app.routes`` mixes route objects with router wrappers that have no
    ``.path``, and it is the OpenAPI document that clients actually see — so
    asserting on the document is both more robust and more meaningful.
    """
    paths = set(app.openapi()["paths"])
    assert not any("mock" in path or "demo" in path for path in paths)


# ---------------------------------------------------------------------------
# Retired unsubscribe surface
# ---------------------------------------------------------------------------


def test_unsubscribe_page_is_retired(client: TestClient):
    response = client.get("/u/some-opaque-token")
    assert response.status_code == 404


def test_unsubscribe_page_is_not_published_in_openapi():
    assert not any(path.startswith("/u/") for path in app.openapi()["paths"])


# ---------------------------------------------------------------------------
# OpenAPI is the contract source of truth
# ---------------------------------------------------------------------------


def test_openapi_document_is_generated(client: TestClient):
    schema = client.get("/openapi.json").json()
    assert schema["info"]["title"] == "SmartMatch API"
    assert "/api/health" in schema["paths"]


def test_error_envelope_is_declared_in_the_schema(client: TestClient):
    """The stable error envelope is part of the published contract."""
    schema = client.get("/openapi.json").json()
    assert "ErrorEnvelope" in schema["components"]["schemas"]
