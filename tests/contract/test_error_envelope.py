"""One error shape, for every non-2xx response.

Architecture v1.1 §1.11 requires a stable error envelope across the whole
contract, and the TypeScript client is generated from that contract rather than
hand-maintained. A second shape is not a cosmetic inconsistency: it is a branch
every generated client has to grow by hand, at the exact boundary generation
exists to keep honest.

FastAPI supplies two of its own — ``{"detail": [...]}`` for request validation
and ``{"detail": "Not Found"}`` for an unrouted path — so both are asserted
against here.

The validation handler is exercised on a small application wired from the same
:data:`~smartmatch_api.errors.EXCEPTION_HANDLERS` mapping the real app uses,
because every route on the real app resolves a database-backed principal before
a body is ever validated, and this suite runs without a database. What the real
app is asked for instead is that it wires the same handlers and publishes the
same shape.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.testclient import TestClient
from pydantic import BaseModel, Field, field_validator
from smartmatch_api.errors import (
    EXCEPTION_HANDLERS,
    http_exception_handler,
    request_validation_handler,
)
from smartmatch_api.main import app as real_app
from starlette.exceptions import HTTPException as StarletteHTTPException


class _Credentials(BaseModel):
    """A body with a field whose value must never come back out."""

    api_key: str = Field(min_length=8)
    attempts: int = 1

    @field_validator("api_key")
    @classmethod
    def _reject_placeholders(cls, value: str) -> str:
        # Interpolating the value is exactly the mistake this suite guards
        # against, and pydantic stores the raised exception itself under
        # ``ctx``, which is not JSON-serializable.
        if value.startswith("test-"):
            raise ValueError(f"placeholder credential rejected: {value}")
        return value


@pytest.fixture
def client() -> TestClient:
    """A client for an app wired exactly as the real one is."""
    application = FastAPI()
    for exception_type, handler in EXCEPTION_HANDLERS.items():
        application.add_exception_handler(exception_type, handler)

    @application.post("/probe")
    def probe(body: _Credentials) -> dict[str, str]:
        return {"status": "ok"}

    # A collection route, so a single request can produce one error *per entry*
    # rather than one per field. Reaching the truncation cap needs more than 20
    # distinct errors, and a scalar body cannot produce them: a malformed list
    # under one field is one error, not one per element.
    @application.post("/probe-many")
    def probe_many(body: list[_Credentials]) -> dict[str, str]:
        return {"status": "ok"}

    return TestClient(application)


# ---------------------------------------------------------------------------
# Malformed requests use the envelope, not FastAPI's own shape
# ---------------------------------------------------------------------------


def test_a_malformed_body_returns_the_standard_envelope(client: TestClient):
    response = client.post("/probe", json={"attempts": "many"})
    body = response.json()

    assert response.status_code == 422
    assert "detail" not in body, "the second error shape must be gone, not merely joined"
    assert set(body) == {"error"}
    assert body["error"]["code"] == "invalid_request"
    assert body["error"]["message"]


def test_the_envelope_names_the_offending_fields(client: TestClient):
    """A 422 a developer cannot act on just costs them a debugging session."""
    response = client.post("/probe", json={"attempts": "many"})
    fields = response.json()["error"]["details"]["fields"]

    located = {entry["field"] for entry in fields}
    assert located == {"body.api_key", "body.attempts"}
    assert {entry["type"] for entry in fields} == {"missing", "int_parsing"}


def test_the_envelope_does_not_echo_the_submitted_value(client: TestClient):
    """A rejected field may be a credential or a piece of personal data.

    Reflecting it puts it in the response body, and from there into every log,
    proxy, and error tracker that records one — a leak created by the error
    path, for data the caller only ever sent once.
    """
    submitted = "reflect-me-not"
    response = client.post("/probe", json={"api_key": submitted, "attempts": submitted})

    assert response.status_code == 422
    assert submitted not in response.text


def test_a_validator_authored_message_is_not_reflected_either(client: TestClient):
    """The riskiest message text is the text a validator wrote itself.

    Pydantic's own messages describe the rule ("Field required"). A message from
    a ``ValueError`` raised in a validator is arbitrary application text that may
    well interpolate the value it rejected, so it is replaced rather than
    forwarded.
    """
    response = client.post("/probe", json={"api_key": "test-abcdefgh"})
    fields = response.json()["error"]["details"]["fields"]

    assert response.status_code == 422
    assert "test-abcdefgh" not in response.text
    assert [entry["type"] for entry in fields] == ["value_error"]


def test_a_ctx_carrying_error_still_renders(client: TestClient):
    """Pydantic v2 puts the raised exception object itself under ``ctx``.

    Forwarding ``errors()`` verbatim therefore hands ``JSONResponse`` something
    it cannot serialize, and the failure lands at render time — turning a 422
    into a 500, which is the API reporting its own fault for the caller's
    mistake.
    """
    response = client.post("/probe", json={"api_key": "test-abcdefgh"})

    assert response.status_code == 422
    assert response.headers["content-type"].startswith("application/json")
    assert response.json()["error"]["code"] == "invalid_request"


def test_malformed_json_is_reported_as_a_request_error_not_a_crash(client: TestClient):
    """A body that is not JSON at all takes the same path."""
    response = client.post(
        "/probe",
        content="{not json",
        headers={"Content-Type": "application/json"},
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_request"


def test_the_reported_field_list_is_bounded(client: TestClient):
    """One malformed request must not buy an unbounded response body.

    A body with thousands of invalid entries produces an error per entry;
    echoing all of them makes the error response larger than the request that
    caused it.

    ``field_count`` reports the true total alongside the truncated list, so a
    caller can tell a truncated response from a complete one. Asserting it is
    what makes this test non-vacuous: an earlier version posted a scalar body
    that produced only two errors, so the cap was never reached and deleting
    the truncation entirely would have kept the test green.
    """
    entries = 30
    response = client.post("/probe-many", json=[{"api_key": 1} for _ in range(entries)])
    details = response.json()["error"]["details"]

    assert details["field_count"] > 20, "the request must actually exceed the cap"
    assert details["field_count"] == entries
    assert len(details["fields"]) == 20


# ---------------------------------------------------------------------------
# The real application
# ---------------------------------------------------------------------------


def test_the_api_wires_the_validation_handler():
    """Asserted on the app, because no route reaches validation without a database.

    Identity, not membership: FastAPI installs its own handler for this
    exception by default, so ``RequestValidationError in exception_handlers`` is
    true even when nothing has been overridden.
    """
    assert real_app.exception_handlers[RequestValidationError] is request_validation_handler


def test_an_unrouted_path_also_uses_the_envelope():
    """FastAPI's own 404 is ``{"detail": "Not Found"}`` — the second shape again."""
    response = TestClient(real_app).get("/no-such-path")
    body = response.json()

    assert response.status_code == 404
    assert "detail" not in body
    assert body["error"]["code"] == "not_found"


def test_a_wrong_method_keeps_its_allow_header():
    """The envelope must not cost a response its protocol headers.

    A 405 without ``Allow`` is a worse answer than a bare ``detail`` body.
    """
    response = TestClient(real_app).post("/api/health")

    assert response.status_code == 405
    assert response.headers.get("allow")
    assert response.json()["error"]["code"] == "method_not_allowed"


def test_the_contract_documents_the_validation_response():
    """The generated client should never meet a shape the contract omits."""
    schema = TestClient(real_app).get("/openapi.json").json()
    responses = schema["paths"]["/v1/units/{unit_id}/imports"]["post"]["responses"]

    assert (
        responses["422"]["content"]["application/json"]["schema"]["$ref"]
        == "#/components/schemas/ErrorEnvelope"
    )


def test_the_contract_publishes_no_second_error_schema():
    """``HTTPValidationError`` is FastAPI's shape; publishing it re-introduces it."""
    schema = TestClient(real_app).get("/openapi.json").json()

    assert "HTTPValidationError" not in schema["components"]["schemas"]


def test_the_starlette_http_exception_handler_is_wired():
    """Also by identity — Starlette installs a default for this one too."""
    assert real_app.exception_handlers[StarletteHTTPException] is http_exception_handler
