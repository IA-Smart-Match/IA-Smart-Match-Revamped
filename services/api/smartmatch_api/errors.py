"""The stable API error envelope.

Architecture v1.1 §1.11 requires a stable error envelope across the whole
contract. One shape, one set of codes, and no leakage of dependency or topology
detail — an error body must never tell a caller which database, queue, or
provider was involved.
"""

from __future__ import annotations

from typing import Any

from fastapi import Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from smartmatch_authz import AuthorizationError
from smartmatch_domain.consent import ConsentViolationError
from smartmatch_domain.jobs import InvalidTransitionError
from smartmatch_persistence.idempotency import IdempotencyConflictError


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


#: Wired into the app in :mod:`smartmatch_api.main`.
EXCEPTION_HANDLERS = {
    ApiError: api_error_handler,
    AuthorizationError: authorization_error_handler,
    ConsentViolationError: consent_error_handler,
    InvalidTransitionError: invalid_transition_handler,
    IdempotencyConflictError: idempotency_conflict_handler,
}
