"""Job status and event streaming.

Architecture v1.1 §1.6 and §1.11. One shared contract serves every command
resource: submit a command, get ``202`` plus a job id, then follow the job.

The event stream is backed by ``job_event.sequence`` and reconnects from
``Last-Event-ID``. That is why Redis is not required for correctness (v1.1 §3.5):
the reconnect cursor is a column, not an ephemeral in-memory position, so any
API instance can serve a reconnect for a stream another instance started.

Polling reads the same rows through the same repository, so the two views cannot
disagree — a client that falls back to polling after an SSE failure sees exactly
what the stream would have shown.

Both routes authorize through :func:`smartmatch_api.job_authz.authorize_job_read`,
which is also where ``/redrive`` and ``/abandon`` go. That is not tidiness: this
module used to carry its own ``_authorize_job_read`` applying a *different subset*
of the policy from the one the command routes applied to the same resource — it
consulted no ``resource_grant`` at all, so an administrator's explicit deny on a
job stopped the re-drive and not the read. One function serves all four
operations now, and the difference between a read and a command is a single
argument rather than a second implementation.

Because the reconnect is an ordinary request, authorization runs again on every
one of them: the job is re-loaded and re-authorized before any event is
rendered. A membership revoked between two reconnects is honoured on the next.
Revalidation *during* a response is deliberately not attempted — see
``job_authz``'s module docstring for why the bounded response is the control.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Iterator
from typing import Annotated, Any

from fastapi import APIRouter, Header, Path, Query, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from smartmatch_domain.jobs import JobState
from smartmatch_persistence.jobs import JobRecord, JobRepository
from sqlalchemy.orm import Session

from smartmatch_api.dependencies import CurrentPrincipal, DbSession
from smartmatch_api.errors import ApiError
from smartmatch_api.job_authz import authorize_job_read
from smartmatch_api.utils import utc_now

router = APIRouter(prefix="/v1/jobs", tags=["jobs"])

_jobs = JobRepository()

#: Events returned in a single stream response before it closes and the client
#: reconnects. Bounded so one very long-running job cannot hold a connection and
#: a database cursor open indefinitely.
_MAX_EVENTS_PER_RESPONSE = 500


class JobStatusResponse(BaseModel):
    """A job's current state."""

    id: uuid.UUID
    command_type: str
    status: JobState
    created_at: str
    updated_at: str
    #: Highest event sequence emitted so far. A client can pass this as
    #: ``Last-Event-ID`` to resume without replaying what it already has.
    latest_sequence: int = Field(default=0, description="Highest job_event sequence emitted so far")


class JobEventResponse(BaseModel):
    """One event in a job's stream."""

    sequence: int
    payload: dict[str, Any]
    occurred_at: str


def _load_job_or_404(session: Session, tenant_id: uuid.UUID, job_id: uuid.UUID) -> JobRecord:
    """Fetch a job within the caller's tenant, or raise 404.

    A job in another tenant produces the same 404 as a job that does not exist.
    Distinguishing them would turn this endpoint into an existence oracle for
    other tenants' work.

    The record carries the owning unit's ``ltree`` path, joined in by
    ``JobRepository.get`` on both ``tenant_id`` and ``id``. That is what
    :func:`~smartmatch_api.job_authz.authorize_job_read` scopes against, and it
    is why authorization happens in the handler rather than in a dependency: a
    dependency cannot authorize a resource it has not fetched.
    """
    job = _jobs.get(session, tenant_id=tenant_id, job_id=job_id)
    if job is None:
        raise ApiError(
            status_code=status.HTTP_404_NOT_FOUND,
            code="job_not_found",
            message="No such job.",
        )
    return job


@router.get(
    "/{job_id}",
    response_model=JobStatusResponse,
    summary="Get a job's status",
)
def get_job(
    principal: CurrentPrincipal,
    session: DbSession,
    job_id: Annotated[uuid.UUID, Path()],
) -> JobStatusResponse:
    """Return one job's current state.

    Tenant-scoped by the caller's own tenant, which is derived server-side from
    their token and never read from the request, and then scoped again to the
    org unit the job belongs to — so a coordinator in one department no longer
    reads another department's work (A5).
    """
    job = _load_job_or_404(session, principal.tenant_id, job_id)
    authorize_job_read(principal, job, at=utc_now())

    return JobStatusResponse(
        id=job.id,
        command_type=job.command_type,
        status=job.status,
        created_at=job.created_at.isoformat(),
        updated_at=job.updated_at.isoformat(),
        latest_sequence=_jobs.latest_sequence(
            session, tenant_id=principal.tenant_id, job_id=job_id
        ),
    )


@router.get(
    "/{job_id}/events",
    summary="Stream a job's events (SSE)",
    response_class=StreamingResponse,
    responses={200: {"content": {"text/event-stream": {}}}},
)
def stream_job_events(
    principal: CurrentPrincipal,
    session: DbSession,
    job_id: Annotated[uuid.UUID, Path()],
    last_event_id: Annotated[
        int | None,
        Header(
            alias="Last-Event-ID",
            description="Resume from this sequence. Standard SSE reconnect header.",
        ),
    ] = None,
    after: Annotated[
        int | None,
        Query(description="Resume cursor for polling clients that cannot send headers"),
    ] = None,
) -> StreamingResponse:
    """Stream a job's events as Server-Sent Events.

    Reconnect is the interesting case. A browser that loses the connection
    reissues the request with ``Last-Event-ID`` set to the last sequence it saw,
    and the stream resumes from there — no duplicates, no gap. Because the cursor
    is a database column rather than in-memory state, the reconnect can land on
    any API instance.

    ``after`` exists for clients that cannot set headers (EventSource
    polyfills, simple polling loops) and means the same thing. When both are
    present ``Last-Event-ID`` wins, since it is the standard.

    Every reconnect re-authorizes. The response is bounded at
    ``_MAX_EVENTS_PER_RESPONSE`` and then closes, and the request the client
    makes to resume runs the same load and the same authorization the first one
    did — so this route cannot become a long-lived hole through which a
    membership revoked ten minutes ago keeps delivering events.

    Browser disconnect does not cancel the underlying work. Cancellation is an
    explicit, persisted, authorized command (v1.1 §1.6) — closing a tab must
    never stop a running job.
    """
    job = _load_job_or_404(session, principal.tenant_id, job_id)
    authorize_job_read(principal, job, at=utc_now())

    cursor = last_event_id if last_event_id is not None else (after or 0)
    if cursor < 0:
        raise ApiError(
            status_code=status.HTTP_400_BAD_REQUEST,
            code="invalid_cursor",
            message="Resume cursor must not be negative.",
        )

    events = _jobs.events_since(
        session,
        tenant_id=principal.tenant_id,
        job_id=job_id,
        after_sequence=cursor,
        limit=_MAX_EVENTS_PER_RESPONSE,
    )

    def render() -> Iterator[str]:
        """Render events in SSE wire format.

        ``id:`` carries the sequence, which is what the browser echoes back as
        ``Last-Event-ID`` on reconnect. Emitting it is what makes resumption
        work at all.
        """
        for event in events:
            body = json.dumps(
                {
                    "sequence": event.sequence,
                    "payload": event.payload,
                    "occurred_at": event.created_at.isoformat(),
                },
                sort_keys=True,
            )
            yield f"id: {event.sequence}\nevent: job_event\ndata: {body}\n\n"

    return StreamingResponse(
        render(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-store",
            # Proxies that buffer defeat streaming entirely; this is the
            # conventional opt-out.
            "X-Accel-Buffering": "no",
        },
    )
