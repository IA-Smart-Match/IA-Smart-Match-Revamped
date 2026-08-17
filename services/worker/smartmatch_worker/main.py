"""Worker HTTP boundary.

Foundation scaffold: the health endpoint and the task-authentication skeleton.
Command handlers arrive with their releases.

The task endpoint verifies the caller before doing anything else. In the
scaffold that verification is a stub that **fails closed** — it rejects every
request — so the endpoint cannot be reached before real OIDC verification is
implemented. A permissive stub would be the more dangerous placeholder.
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Header, HTTPException, status

app = FastAPI(
    title="SmartMatch Worker",
    version="0.1.0",
    description=(
        "Private Cloud Tasks target. Not internet-facing: ingress is internal, "
        "and every request must carry a verified OIDC service identity."
    ),
)


@app.get("/health", tags=["operations"])
def health() -> dict[str, str]:
    """Liveness probe for the worker service."""
    return {"status": "ok"}


def _verify_task_identity(authorization: str | None) -> None:
    """Verify the Cloud Tasks OIDC token.

    Not implemented in the Foundation scaffold, and therefore rejects
    everything. Implementing this means verifying the token signature against
    Google's public keys, checking the audience against this service's URL, and
    checking the service account against an allowlist — none of which is
    meaningful until the service actually has a deployed URL and identity.

    Raises:
        HTTPException: always, in the scaffold.
    """
    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="missing task credentials",
        )
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail=(
            "OIDC task-identity verification is not implemented in the Foundation "
            "scaffold; this endpoint fails closed until it is"
        ),
    )


@app.post("/tasks/execute", tags=["tasks"])
def execute_task(authorization: str | None = Header(default=None)) -> dict[str, Any]:
    """Execute one durable command delivered by Cloud Tasks.

    The handler body is intentionally unreachable in the scaffold: identity
    verification runs first and always raises. Command dispatch, the job state
    transition, and the send-time gate rechecks land with R1 and R4.
    """
    _verify_task_identity(authorization)
    raise AssertionError("unreachable: task identity verification always raises")
