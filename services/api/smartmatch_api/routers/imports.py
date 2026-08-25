"""Import command resource.

Architecture v1.1 §1.11 lists ``/imports`` among the explicit command resources
that replace the v1.0 generic job endpoint. It ships first among them because it
is the only one whose downstream work is already gated correctly: imports feed
the quarantine-and-review path (v1.1 §1.5), producing review items rather than
verified records, so accepting one commits no policy the open decisions have not
settled.

Match-run, discovery, and send commands follow the *same* shape via
:func:`~smartmatch_api.commands.submit_command`, but each waits on its gate —
match-runs on G1 (factor registry), discovery on G3 (agent controls), sends on
G4 (consent-origin policy).
"""

from __future__ import annotations

import uuid
from datetime import timedelta
from typing import Annotated

from fastapi import APIRouter, Header, Path, status
from pydantic import BaseModel, Field
from smartmatch_authz import OrgPath, Resource, assert_allowed
from smartmatch_persistence.rate_limit import RateLimit

from smartmatch_api.commands import submit_command
from smartmatch_api.dependencies import CurrentPrincipal, DbSession
from smartmatch_api.errors import ApiError
from smartmatch_api.units import load_unit_or_404
from smartmatch_api.utils import utc_now

router = APIRouter(prefix="/v1/units", tags=["imports"])

#: v1.1 §3.4 gives pilot defaults as hypotheses to tune with recorded evidence.
#: Imports are deliberately tighter than reads: each one queues durable work.
IMPORT_RATE_LIMIT = RateLimit(
    operation="import.create",
    max_requests=10,
    window=timedelta(minutes=1),
)

#: Roles permitted to submit an import. An explicit set rather than "any
#: membership": importing records into a unit is a consequential act.
_IMPORT_ROLES = frozenset({"admin", "coordinator"})


class ImportRequest(BaseModel):
    """An import submission.

    Deliberately carries no tenant, actor, or timestamp. All three are derived
    server-side; accepting them from the body is the caller-supplied-identity
    pattern archived as MM-A01.
    """

    source_reference: str = Field(
        min_length=1,
        max_length=500,
        description="Opaque reference to previously uploaded content in Cloud Storage",
    )
    dataset: str = Field(
        min_length=1,
        max_length=100,
        description="Logical dataset name, e.g. 'professionals'",
    )
    dry_run: bool = Field(
        default=True,
        description=(
            "When true the import validates and reports without creating review "
            "items. Defaults to true: the safe outcome should be the one you get "
            "by not thinking about it."
        ),
    )


class CommandAcceptedResponse(BaseModel):
    """Standard acknowledgement for every command resource."""

    job_id: uuid.UUID
    status: str = Field(default="accepted")
    #: Where to follow the work.
    events_url: str
    #: True when an identical request under the same key was already accepted.
    replayed: bool = False


@router.post(
    "/{unit_id}/imports",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=CommandAcceptedResponse,
    summary="Submit an import command",
)
def create_import(
    principal: CurrentPrincipal,
    session: DbSession,
    body: ImportRequest,
    unit_id: Annotated[uuid.UUID, Path()],
    idempotency_key: Annotated[
        str | None,
        Header(
            alias="Idempotency-Key",
            description="Required. Makes retries safe.",
        ),
    ] = None,
) -> CommandAcceptedResponse:
    """Accept an import command.

    Returns ``202``, not ``200``: nothing has been imported when this returns.
    The command is recorded and will be dispatched; the job is where the outcome
    lives. Saying ``200`` here would be reporting success for work that has not
    started (v1.1 §3.6 N2).

    Authorization runs against the *owning unit*, after loading it — which is
    why it happens here rather than in a dependency. A dependency cannot
    authorize a resource it has not fetched.
    """
    unit = load_unit_or_404(session, tenant_id=principal.tenant_id, unit_id=unit_id)

    assert_allowed(
        principal.principal,
        Resource(
            resource_type="org_unit",
            resource_id=str(unit_id),
            tenant_id=str(principal.tenant_id),
            owning_unit_path=OrgPath.parse(unit.path),
        ),
        at=utc_now(),
        required_roles=_IMPORT_ROLES,
    )

    if not body.source_reference.strip():
        raise ApiError(
            status_code=status.HTTP_400_BAD_REQUEST,
            code="invalid_source_reference",
            message="source_reference must not be blank.",
        )

    # This dictionary is the command's durable contract, not a scratch value for
    # the idempotency hash: `submit_command` writes it to `job.payload` in the
    # same INSERT as the job row, and `smartmatch_worker.handlers` reads these
    # four keys back and refuses the job if any is missing or unusable. Renaming
    # a key here changes what the worker is given, so the two ends move together.
    # `unit_id` comes from the authorized path parameter rather than the body —
    # the caller may not name the unit their import lands in (MM-A01).
    accepted = submit_command(
        session,
        principal,
        command_type="import.create",
        payload={
            "unit_id": str(unit_id),
            "source_reference": body.source_reference,
            "dataset": body.dataset,
            "dry_run": body.dry_run,
        },
        idempotency_key=idempotency_key,
        rate_limit=IMPORT_RATE_LIMIT,
    )

    return CommandAcceptedResponse(
        job_id=accepted.job_id,
        events_url=f"/v1/jobs/{accepted.job_id}/events",
        replayed=accepted.is_replay,
    )
