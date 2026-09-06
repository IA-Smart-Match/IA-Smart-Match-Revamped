"""The stable API error envelope.

Architecture v1.1 §1.11 requires a stable error envelope across the whole
contract. One shape, one set of codes, and no leakage of dependency or topology
detail — an error body must never tell a caller which database, queue, or
provider was involved.

"Across the whole contract" includes the responses this application does not
write itself. FastAPI answers a malformed body with ``{"detail": [...]}`` and an
unrouted path with ``{"detail": "Not Found"}``; left alone, those make the
contract carry three shapes where it promises one, and the TypeScript client
generated from it has to branch on all three by hand — at precisely the boundary
generation exists to keep honest. Both are re-rendered here.
"""

from __future__ import annotations

import http
from typing import Any, Final

from fastapi import Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from smartmatch_authz import AuthorizationError
from smartmatch_domain.consent import ConsentViolationError
from smartmatch_domain.jobs import InvalidTransitionError
from smartmatch_persistence.idempotency import IdempotencyConflictError
from starlette.exceptions import HTTPException as StarletteHTTPException

#: Field-level problems reported in a single 422. A request with a thousand bad
#: entries produces a thousand errors, and echoing them all makes the error
#: larger than the request that caused it. The full count is reported alongside,
#: so a caller can tell a truncated list from a complete one.
_MAX_REPORTED_FIELDS: Final[int] = 20

#: Error types whose ``msg`` was written by a validator rather than by pydantic.
#: Pydantic's own messages describe the rule ("Field required", "Input should be
#: a valid integer"). These two carry the text of an exception the application
#: raised, which may well interpolate the value it rejected — so the message is
#: replaced rather than forwarded.
_AUTHOR_SUPPLIED_MESSAGE_TYPES: Final[frozenset[str]] = frozenset(
    {"value_error", "assertion_error"}
)


class ApiError(Exception):
    """An error to render in the standard envelope.

    Raised by dependencies and handlers instead of ``HTTPException``, so every
    non-2xx response carries the same shape and a stable ``code`` clients can
    branch on. ``HTTPException`` produces ``{"detail": ...}``, which would give
    the contract two error shapes and force clients to handle both.
    """

    def __init__(
        self,
        *,
        status_code: int,
        code: str,
        message: str,
        details: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.details = details
        self.headers = headers


class ErrorBody(BaseModel):
    """The inner error object."""

    code: str = Field(description="Stable machine-readable code; safe to branch on")
    message: str = Field(description="Human-readable summary; not for branching")
    details: dict[str, Any] | None = Field(default=None, description="Optional structured context")


class ErrorEnvelope(BaseModel):
    """The response body for every non-2xx API response."""

    error: ErrorBody


def error_response(
    status_code: int,
    code: str,
    message: str,
    *,
    details: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    """Build an error response in the standard envelope."""
    envelope = ErrorEnvelope(error=ErrorBody(code=code, message=message, details=details))
    return JSONResponse(
        status_code=status_code,
        content=envelope.model_dump(exclude_none=True),
        headers=headers,
    )


async def authorization_error_handler(_request: Request, exc: Exception) -> JSONResponse:
    """Map an authorization denial to 403.

    The stable reason code is returned, but nothing about *why* the resource
    exists or does not — a denial must not become an existence oracle.
    """
    assert isinstance(exc, AuthorizationError)
    return error_response(
        status.HTTP_403_FORBIDDEN,
        code="forbidden",
        message="You do not have access to this resource.",
        details={"reason": exc.decision.reason},
    )


async def consent_error_handler(_request: Request, exc: Exception) -> JSONResponse:
    """Map a consent violation to 409.

    Not 403: the caller may be perfectly authorized, but the *recipient* has not
    consented. Conflating the two hides a policy failure behind a permissions
    error.
    """
    assert isinstance(exc, ConsentViolationError)
    return error_response(
        status.HTTP_409_CONFLICT,
        code="consent_required",
        message=str(exc),
    )


async def invalid_transition_handler(_request: Request, exc: Exception) -> JSONResponse:
    """Map an illegal job state transition to 409."""
    assert isinstance(exc, InvalidTransitionError)
    return error_response(
        status.HTTP_409_CONFLICT,
        code="invalid_state_transition",
        message=str(exc),
        details={"current": exc.current.value, "requested": exc.requested.value},
    )


async def api_error_handler(_request: Request, exc: Exception) -> JSONResponse:
    """Render an :class:`ApiError` in the standard envelope."""
    assert isinstance(exc, ApiError)
    return error_response(
        exc.status_code,
        code=exc.code,
        message=exc.message,
        details=exc.details,
        headers=exc.headers,
    )


async def idempotency_conflict_handler(_request: Request, exc: Exception) -> JSONResponse:
    """Map an idempotency-key conflict to 409.

    Never 200 with the original job: the caller reused a key for a *different*
    request, and answering with the earlier result would silently discard what
    they actually asked for.
    """
    assert isinstance(exc, IdempotencyConflictError)
    return error_response(
        status.HTTP_409_CONFLICT,
        code="idempotency_key_reused",
        message=str(exc),
    )


def _describe_validation_error(error: Any) -> dict[str, str]:
    """Reduce one pydantic error to what a caller needs and nothing more.

    Three keys, chosen for what they leave out as much as for what they carry:

    * ``field`` — the dotted location, e.g. ``body.dataset``. Names the thing to
      fix.
    * ``type`` — pydantic's stable machine code, e.g. ``missing``. Safe to
      branch on, and the only part of the entry a client should.
    * ``message`` — the rule that was broken.

    ``input`` is dropped, and this is the point of the whole function. A
    validation failure on a field carrying an API key, a password, or a date of
    birth would otherwise reflect that value into the response body and from
    there into every log, proxy, and error tracker that records one — a leak
    manufactured by the error path, for data the caller sent exactly once.

    ``ctx`` is dropped for a second reason on top of that one: pydantic v2 puts
    the raised exception *object* there for validator-authored failures, which
    ``JSONResponse`` cannot serialize. Forwarding ``errors()`` unfiltered fails
    at render time and turns the caller's 422 into the API's 500.
    """
    location = ".".join(str(part) for part in error.get("loc", ()))
    error_type = str(error.get("type", "invalid"))

    if error_type in _AUTHOR_SUPPLIED_MESSAGE_TYPES:
        message = "The submitted value was rejected by a validation rule."
    else:
        message = str(error.get("msg", "Invalid value."))

    return {"field": location or "body", "type": error_type, "message": message}


async def request_validation_handler(_request: Request, exc: Exception) -> JSONResponse:
    """Render a malformed request in the standard envelope, as 422.

    The code is ``invalid_request`` and it is stable: clients branch on it, so it
    outlives any change to how the details are assembled.

    422 rather than 400, matching what FastAPI already answered and what the
    contract has always documented for these routes. The status is the part
    existing clients may already depend on; only the body changes.
    """
    errors = exc.errors() if isinstance(exc, RequestValidationError) else []
    fields = [_describe_validation_error(error) for error in errors[:_MAX_REPORTED_FIELDS]]

    return error_response(
        status.HTTP_422_UNPROCESSABLE_ENTITY,
        code="invalid_request",
        message="The request could not be processed as submitted.",
        details={"fields": fields, "field_count": len(errors)},
    )


async def http_exception_handler(_request: Request, exc: Exception) -> JSONResponse:
    """Render Starlette's own HTTP errors in the envelope too.

    These are the responses no handler in this application produced: the 404 for
    an unrouted path, the 405 for a wrong method. They are the last place the
    old ``{"detail": ...}`` shape survives, and an unrouted path is a very
    ordinary thing for a client to hit.

    The code is derived from the status rather than kept in a table, so a status
    this application has never returned before still arrives with a sensible,
    stable code instead of an unhandled shape. Anything raised deliberately by a
    route uses :class:`ApiError`, which names its own code.

    ``exc.headers`` are preserved. A 405 without its ``Allow`` header is a worse
    answer than one with the wrong body shape, and ``WWW-Authenticate`` on a 401
    is load-bearing for a client that intends to retry.
    """
    assert isinstance(exc, StarletteHTTPException)
    try:
        code = http.HTTPStatus(exc.status_code).name.lower()
    except ValueError:  # pragma: no cover - a non-standard status code
        code = "http_error"

    return error_response(
        exc.status_code,
        code=code,
        # ``detail`` is Starlette's own text ("Not Found"), never a caller's
        # input, so it is safe to pass through. It is stringified because
        # ``HTTPException`` accepts any object there.
        message=str(exc.detail),
        # Copied into a plain dict: ``HTTPException`` types its headers as a
        # read-only mapping, and the envelope builder owns what it is handed.
        headers=dict(exc.headers) if exc.headers else None,
    )


#: Wired into the app in :mod:`smartmatch_api.main`.
EXCEPTION_HANDLERS = {
    ApiError: api_error_handler,
    AuthorizationError: authorization_error_handler,
    ConsentViolationError: consent_error_handler,
    InvalidTransitionError: invalid_transition_handler,
    IdempotencyConflictError: idempotency_conflict_handler,
    RequestValidationError: request_validation_handler,
    StarletteHTTPException: http_exception_handler,
}
