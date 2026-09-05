"""Coordinator-driven pipeline stage advances (S12 funnel write path).

``docs/plans/2026-09-05-pipeline-stage-writers-plan.md`` is this module's plan
card. Two operations:

* ``GET  /v1/units/{unit_id}/pipeline-records/{record_id}`` — one journey and
  every stage it has reached. See :func:`read_pipeline_record`.
* ``POST /v1/units/{unit_id}/pipeline-records/{record_id}/stages`` — advance it
  to Confirmed, Attended, or Member Inquiry. See :func:`advance_pipeline_stage`.

## Why this module exists at all

``pipeline_record`` has had a schema since migration ``0011`` and a read path
since the metric register was bound to storage, but until now its only
*application* writers were the review-accept path and the synthetic seed (both
opening a journey at Matched) and the outreach worker's ``_advance_pipeline``
(Contacted, and only when a send command named an existing journey). The last
three funnel metrics therefore measured a genuine, honest zero: no code could
reach those stages, so no row had.

Zero because nothing happened and zero because nothing *could* happen look the
same to a coordinator reading a dashboard, and only one of them is a fact about
their program. This module closes that gap the only way ADR-0011 permits — by
giving a real person a route that records a real claim with a real timestamp,
not by inferring a stage from something adjacent to it.

## The request cannot name Matched or Contacted, and that is the point

:class:`StageAdvanceRequest`'s ``stage`` admits exactly three values.

``matched`` is excluded because it is not an advance: a ``pipeline_record`` has
no row without ``matched_at`` (``NOT NULL`` since ``0011``), so the stage is
opened by :meth:`~smartmatch_persistence.pipeline.PipelineRepository.record_matched`
and every row this route can find has already reached it.
:meth:`~smartmatch_persistence.pipeline.PipelineRepository.advance_stage` refuses
it with a ``ValueError``; keeping it out of the enum means a caller is told by
the schema instead.

``contacted`` is excluded for a different and more important reason: it is the
one stage in this funnel that a machine witnesses. The outreach worker writes it
after a provider has accepted custody of a message, which is evidence. A
coordinator typing "contacted" into this route would be an assertion wearing that
evidence's name, and the metric could no longer distinguish the two. If a message
was sent outside this appliance, the honest record is that the journey has not
reached Contacted here — not a hand-written timestamp that says it did.

## Everything else this module deliberately does not do

**No list route.** ``GET`` reads exactly one record by an id the caller was given
out of band. A queue over other students' journeys needs the same unresolved
read-role decision ``docs/decisions/d6-rewards-budget-decision-record.md`` §5
still lists as open for redemptions, and ``rewards.py`` declines to ship one for
the same reason. See OQ-104 in
``docs/plans/open-questions/pipeline-stage-writers-deferred.md``.

**No journey creator.** Nothing here writes new ``pipeline_record`` rows.
Advancing a journey that exists is a different act from deciding one should
exist, and the second is the matching engine's (G1) or the coordinator-accept
path's.

**No attendance writer.** The Attended stage *cites* an ``attendance_record``; it
does not create one. ``ck_pipeline_record_attendance_evidence`` makes the citation
biconditional and ``advance_stage`` checks the row exists in this tenant before
the ``UPDATE``, so a journey cannot reach Attended on evidence that is not there.
OQ-102 carries who eventually writes those rows.

**No calendar integration.** Confirmed is a coordinator's claim here and the
route never pretends otherwise — there is no poller and no webhook. OQ-101 carries
the question and what lands when it is answered.

## Status codes

``200``, not ``202``. Nothing durable starts: the ``UPDATE`` lands in this request
or it does not, which is ``rewards.py::decide_redemption``'s shape rather than
``outreach.py::send_draft``'s. There is likewise no ``Idempotency-Key`` header —
the advance is idempotent in the data (``advance_stage``'s ``UPDATE`` carries
``target_column IS NULL``), so a repeat returns ``200`` with ``transitioned:
false`` and ``already_reached: true``. A stored key would be weaker: it covers a
retry of one request, and would misreport a second coordinator asserting the same
fact as a replay of the first.

``charge_quota`` runs first on both routes — ADR-0015's ordering, ahead of the
load, the authorization and the validation, so a caller producing 404s against
invented ids spends exactly what a caller advancing real journeys spends.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from typing import Annotated, Final, Literal

from fastapi import APIRouter, Path, status
from pydantic import AwareDatetime, BaseModel, Field, model_validator
from smartmatch_authz import OrgPath, Resource, assert_allowed
from smartmatch_domain.pipeline import (
    PIPELINE_STAGE_SEQUENCE,
    InvalidPipelineStageTransitionError,
    PipelineStage,
)
from smartmatch_persistence.pipeline import (
    PipelineRecordRow,
    PipelineRepository,
    PipelineStageOrderError,
    UnknownAttendanceEvidenceError,
)
from smartmatch_persistence.rate_limit import RateLimit
from sqlalchemy.orm import Session

from smartmatch_api.dependencies import CurrentPrincipal, DbSession, charge_quota
from smartmatch_api.errors import ApiError
from smartmatch_api.units import load_unit_or_404
from smartmatch_api.utils import utc_now

router = APIRouter(prefix="/v1/units", tags=["pipeline"])

_repo: Final[PipelineRepository] = PipelineRepository()

#: ``admin`` and ``coordinator``, matching ``outreach.py::_OUTREACH_ROLES``,
#: ``review.py::_REVIEW_ROLES`` and ``rewards.py::_REDEMPTION_DECISION_ROLES``.
#: The same set for the read and the write: a coordinator who may advance a
#: journey may obviously read the one they just advanced, and splitting the two
#: would give a widening two places to happen instead of one.
_PIPELINE_ROLES: Final[frozenset[str]] = frozenset({"admin", "coordinator"})

#: The write is the consequential one and carries the tighter limit, the same
#: relationship ``outreach.py`` draws between ``DRAFT_RATE_LIMIT`` and
#: ``SEND_RATE_LIMIT``. A coordinator advancing thirty journeys a minute is
#: already working faster than the events behind them can happen.
STAGE_ADVANCE_RATE_LIMIT: Final[RateLimit] = RateLimit(
    operation="pipeline.stage_advance", max_requests=30, window=timedelta(minutes=1)
)
PIPELINE_READ_RATE_LIMIT: Final[RateLimit] = RateLimit(
    operation="pipeline.read", max_requests=120, window=timedelta(minutes=1)
)

#: The stages this route may write. See the module docstring for why ``matched``
#: and ``contacted`` are absent — the exclusion is a rule about evidence, not an
#: oversight, and the ``Literal`` is where a client finds out.
AdvanceableStage = Literal["confirmed", "attended", "member_inquiry"]


# ---------------------------------------------------------------------------
# Wire shapes
# ---------------------------------------------------------------------------


class StageAdvanceRequest(BaseModel):
    """One coordinator's claim that a journey reached a stage, and when."""

    stage: AdvanceableStage = Field(
        description=(
            "The stage reached. 'matched' is opened when the journey is created and "
            "'contacted' is written by the outreach send, so neither is accepted here."
        )
    )
    reached_at: AwareDatetime = Field(
        description=(
            "When the stage was reached. Required and timezone-aware — this records "
            "when something happened, which a server clock reading is not, and a naive "
            "value can silently violate ck_pipeline_record_stage_order against a "
            "timestamptz column. Must not precede the previous stage's own timestamp."
        )
    )
    attendance_id: uuid.UUID | None = Field(
        default=None,
        description=(
            "The attendance_record this claim cites. Required for 'attended' and "
            "rejected for every other stage (ck_pipeline_record_attendance_evidence)."
        ),
    )

    @model_validator(mode="after")
    def _evidence_matches_stage(self) -> StageAdvanceRequest:
        """Enforce ``ck_pipeline_record_attendance_evidence``'s biconditional here.

        ``advance_stage`` refuses both halves too, and its refusal is the one that
        actually protects the table. Restating it in the schema is not redundancy
        for its own sake: it turns a ``ValueError`` naming a repository keyword
        into a ``422`` naming the request field the caller can see, which is the
        difference between a client being able to fix a request and being able to
        guess at one.
        """
        if self.stage == PipelineStage.ATTENDED.value and self.attendance_id is None:
            raise ValueError(
                "attendance_id is required for the 'attended' stage: the Attended "
                "claim cites a real attendance_record rather than asserting one."
            )
        if self.stage != PipelineStage.ATTENDED.value and self.attendance_id is not None:
            raise ValueError(
                f"attendance_id is only accepted for the 'attended' stage, not {self.stage!r}."
            )
        return self


class PipelineRecordResponse(BaseModel):
    """One journey, with every stage timestamp it actually has.

    The four optional ``*_at`` fields are ``null`` when the stage has not been
    reached — never ``0``, never an epoch, and never the row's ``created_at``
    standing in for a moment nobody recorded. ``current_stage`` is derived from
    those same timestamps rather than stored, so it cannot drift from them.
    """

    id: uuid.UUID
    owning_unit_id: uuid.UUID
    subject_id: uuid.UUID
    opportunity_event_id: uuid.UUID
    matched_provenance: str
    current_stage: str = Field(
        description="The furthest stage reached, derived from the timestamps below."
    )
    matched_at: datetime
    contacted_at: datetime | None
    confirmed_at: datetime | None
    attended_at: datetime | None
    member_inquiry_at: datetime | None
    attendance_id: uuid.UUID | None = Field(
        description="The attendance_record the Attended stage cites, when it has been reached."
    )


class StageAdvanceResponse(BaseModel):
    """What the advance did, and the row it left behind.

    ``transitioned`` and ``already_reached`` are two fields rather than one
    negated boolean for the reason
    :class:`~smartmatch_persistence.pipeline.PipelineStageOutcome` keeps them
    apart: "this request's own statement wrote the stage" and "the stage was
    already recorded before this request" are different facts, and a client
    showing a coordinator "recorded" versus "already recorded" needs both.
    """

    transitioned: bool = Field(
        description="True only when this request's own UPDATE is the one that wrote the stage."
    )
    already_reached: bool = Field(
        description="True when the stage was already recorded before this request arrived."
    )
    record: PipelineRecordResponse


# ---------------------------------------------------------------------------
# Authorization and views
# ---------------------------------------------------------------------------


def _authorize_pipeline(
    session: Session, principal: CurrentPrincipal, unit_id: uuid.UUID
) -> uuid.UUID:
    """Load the unit and authorize a coordinator against *that row's* path.

    Shared by both operations, in the spirit of ``_authorize_outreach``: they ask
    the identical question against the identical resource, so a widening applies
    to both or to neither.

    ``load_unit_or_404`` scopes the lookup by the caller's own tenant, so a unit
    in another tenant is a 404 rather than a 403 that would confirm the id names
    something real.

    Returns:
        The loaded unit's own id — the value every record below is checked
        against, so the scope comes from the authorized row and never from a
        body or a query parameter.
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
        required_roles=_PIPELINE_ROLES,
    )
    return unit.id


def _load_record_or_404(
    session: Session,
    principal: CurrentPrincipal,
    *,
    record_id: uuid.UUID,
    owning_unit_id: uuid.UUID,
) -> PipelineRecordRow:
    """Read one record, refusing anything outside the authorized unit.

    A record in another unit is a **404**, not a 403 — the caller is permitted to
    act in the unit they named, and the record simply is not in it. Saying
    "forbidden" would confirm that an id the caller may not read names a real
    journey, which is ``compose_draft``'s reasoning for a contact channel in
    another unit and the same reasoning here.
    """
    record = _repo.get(session, tenant_id=principal.tenant_id, record_id=record_id)
    if record is None or record.owning_unit_id != owning_unit_id:
        raise ApiError(
            status_code=status.HTTP_404_NOT_FOUND,
            code="pipeline_record_not_found",
            message="No such pipeline record in this unit.",
        )
    return record


def _current_stage(record: PipelineRecordRow) -> str:
    """The furthest stage reached, walked in the funnel's own declared order.

    ``PIPELINE_STAGE_SEQUENCE`` is walked rather than a local tuple, so a stage
    added to the funnel appears here without this module being edited — and, more
    to the point, cannot appear here in a *different* order than the domain's.
    ``MATCHED`` is the floor: ``matched_at`` is ``NOT NULL``, so every row this
    function can be handed has reached it.
    """
    reached = record.reached()
    furthest = PipelineStage.MATCHED
    for stage in PIPELINE_STAGE_SEQUENCE:
        if stage in reached:
            furthest = stage
    return furthest.value


def _record_view(record: PipelineRecordRow) -> PipelineRecordResponse:
    return PipelineRecordResponse(
        id=record.id,
        owning_unit_id=record.owning_unit_id,
        subject_id=record.subject_id,
        opportunity_event_id=record.opportunity_event_id,
        matched_provenance=record.matched_provenance,
        current_stage=_current_stage(record),
        matched_at=record.matched_at,
        contacted_at=record.contacted_at,
        confirmed_at=record.confirmed_at,
        attended_at=record.attended_at,
        member_inquiry_at=record.member_inquiry_at,
        attendance_id=record.attended_attendance_id,
    )


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.get(
    "/{unit_id}/pipeline-records/{record_id}",
    response_model=PipelineRecordResponse,
    summary="Read one pipeline journey and the stages it has reached",
)
def read_pipeline_record(
    principal: CurrentPrincipal,
    session: DbSession,
    unit_id: Annotated[uuid.UUID, Path()],
    record_id: Annotated[uuid.UUID, Path()],
) -> PipelineRecordResponse:
    """Read one journey by id, scoped to this tenant and this unit.

    A read, and only a read: no stage is inferred, defaulted, or filled in. An
    unreached stage comes back ``null``, which is what the column holds.

    Raises:
        ApiError: 404 when this tenant has no such record, or it is not under
            the unit the request was authorized for.
    """
    charge_quota(session, principal, PIPELINE_READ_RATE_LIMIT)

    owning_unit_id = _authorize_pipeline(session, principal, unit_id)
    record = _load_record_or_404(
        session, principal, record_id=record_id, owning_unit_id=owning_unit_id
    )
    return _record_view(record)


@router.post(
    "/{unit_id}/pipeline-records/{record_id}/stages",
    response_model=StageAdvanceResponse,
    summary="Record that a pipeline journey reached a stage",
)
def advance_pipeline_stage(
    principal: CurrentPrincipal,
    session: DbSession,
    body: StageAdvanceRequest,
    unit_id: Annotated[uuid.UUID, Path()],
    record_id: Annotated[uuid.UUID, Path()],
) -> StageAdvanceResponse:
    """Advance one journey to Confirmed, Attended, or Member Inquiry.

    The legality of the move is decided by
    :meth:`~smartmatch_persistence.pipeline.PipelineRepository.advance_stage`,
    and this handler restates none of it: Attended is reachable only from
    Confirmed because ``assert_stage_reachable`` says so and because
    ``ck_pipeline_record_stage_prefix`` refuses the row otherwise, not because of
    a check written here. The one rule this module adds is *which* stages a human
    may claim at all, which is a question about evidence rather than about
    ordering — see the module docstring.

    Repeating a request that already landed is a ``200`` with ``transitioned:
    false`` and ``already_reached: true``, not a ``409``: a coordinator asserting
    a fact that is already recorded has not asked for anything illegal, and the
    row they get back is the one that was already there.

    Raises:
        ApiError: 404 when this tenant has no such record or it is not in this
            unit; 409 when the previous stage has not been reached, when
            ``reached_at`` precedes that stage's own timestamp, or when
            ``attendance_id`` names no attendance record in this tenant.
    """
    charge_quota(session, principal, STAGE_ADVANCE_RATE_LIMIT)

    owning_unit_id = _authorize_pipeline(session, principal, unit_id)
    # Loaded — and its unit checked — before the write, so a record in another
    # unit is a 404 rather than an advance the repository would have been happy
    # to perform on a tenant-scoped id the caller had no business naming.
    _load_record_or_404(session, principal, record_id=record_id, owning_unit_id=owning_unit_id)

    stage = PipelineStage(body.stage)
    try:
        outcome = _repo.advance_stage(
            session,
            tenant_id=principal.tenant_id,
            record_id=record_id,
            stage=stage,
            reached_at=body.reached_at,
            attended_attendance_id=body.attendance_id,
        )
    except UnknownAttendanceEvidenceError as exc:
        raise ApiError(
            status_code=status.HTTP_409_CONFLICT,
            code="pipeline_attendance_evidence_not_found",
            message=(
                "The attendance record this Attended claim cites does not exist in "
                "this tenant. The stage cites attendance; it does not create it."
            ),
        ) from exc
    except PipelineStageOrderError as exc:
        raise ApiError(
            status_code=status.HTTP_409_CONFLICT,
            code="pipeline_stage_out_of_order",
            message=str(exc),
        ) from exc
    except InvalidPipelineStageTransitionError as exc:
        raise ApiError(
            status_code=status.HTTP_409_CONFLICT,
            code="pipeline_stage_prerequisite_unmet",
            message=str(exc),
        ) from exc

    if not outcome.exists or outcome.record is None:
        # The load above found the row, so reaching here means a concurrent
        # DELETE between that read and the UPDATE. A 404 is still the honest
        # answer: the record the caller named is gone.
        raise ApiError(
            status_code=status.HTTP_404_NOT_FOUND,
            code="pipeline_record_not_found",
            message="No such pipeline record in this unit.",
        )

    session.commit()
    return StageAdvanceResponse(
        transitioned=outcome.transitioned,
        already_reached=outcome.already_reached,
        record=_record_view(outcome.record),
    )
