"""The CBA speaker handoff: an accepted invitation, returned to the Event Host.

Track CBA-HANDOFF-PIPELINE. Two operations:

* ``POST /v1/units/{unit_id}/cba/events/{event_id}/speaker-handoff`` -- bring one
  speaker's funnel journey up to whatever the stored evidence supports. See
  :func:`reconcile_speaker_handoff`.
* ``GET  /v1/units/{unit_id}/cba/confirmed-speakers`` -- the confirmed speakers
  this unit can hand an Event Host, optionally for one event. See
  :func:`list_confirmed_speakers`.

## Why this is not the stage route with a different name

``routers/pipeline.py`` already advances a journey to Confirmed, and it is
explicit about what that means: "Confirmed is a coordinator's claim here and the
route never pretends otherwise". That is the right shape for the pre-CBA
product, where nothing in the system witnesses a speaker agreeing.

Track 20 changed that for CBA. ``cba_invitation.response_status`` records what
the **Speaker** said, in a vocabulary that shares no value with any delivery
disposition, and ``ck_cba_invitation_response_dated`` ties the answer to the
moment it was recorded. So for a CBA speaker there now *is* a stored fact behind
Confirmed, and this route's whole job is to write the stage from that fact
rather than from a claim typed beside it.

That is why the request body has no ``stage`` and no ``reached_at``. There is
nothing here for a browser to toggle: the body names an invitation, and the
stages and their timestamps are read out of the database. Post it twice and the
second call writes nothing.

## What it deliberately does not do

**No member_inquiry, in either direction.** ``Capability.MEMBER_INQUIRY_NARRATIVE``
is ``False`` under ``ProductScope.CBA``, and this module honours it structurally
rather than by filtering at the edge: the writer refuses the stage
(``CbaHandoffRepository.advance_cba_stage``) and the view below has no field for
it (``ConfirmedSpeakerRow`` carries none). The stage, its column and every row
already written are untouched -- ``routers/pipeline.py`` still reads and writes
them for the product that has them.

**No consent is granted, implied, or advanced.** An accepted invitation is
pipeline evidence and nothing else. Consent lives on ``contact_channel`` and is
moved only by the contact-channel surface; nothing in this module reads it,
writes it, or treats an acceptance as a substitute for it.

**No attendance writer.** The Attended stage *cites* an ``attendance_record``;
it never creates one, and the repository checks the cited row belongs to this
speaker and this event before the stage is written.

**No event resolution.** ``cba_invitation_batch`` holds ``event_name`` and
``event_date`` as free text a Connector typed, never an event id, so the Host's
own ``event_id`` comes from the path. It is verified to name a real event in the
tenant before any journey is opened against it --
``pipeline_record.opportunity_event_id`` carries no foreign key, so nothing in
the schema would otherwise stop a journey against an id that names nothing.

## Status codes

``200``, not ``202``: nothing durable starts, the writes land in this request or
they do not. No ``Idempotency-Key`` header either -- the reconciliation is
idempotent in the *data*, because it derives every stage and every timestamp
from stored rows, so a repeat is a ``200`` with an empty ``applied`` rather than
a replay of a stored key.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from typing import Annotated, Final

from fastapi import APIRouter, Path, Query, status
from pydantic import BaseModel, Field
from smartmatch_authz import OrgPath, Resource, assert_allowed
from smartmatch_domain.pipeline import CBA_STAGE_SEQUENCE, CbaStageEvidence, PipelineStage
from smartmatch_persistence.pipeline import (
    CbaAttendanceMismatchError,
    CbaHandoffRepository,
    CbaInvitationNotConfirmedError,
    CbaInvitationNotFoundError,
    ConfirmedSpeakerRow,
    ConflictingOwningUnitError,
    PipelineStageOrderError,
    UnknownAttendanceEvidenceError,
    UnknownOpportunityEventError,
)
from smartmatch_persistence.rate_limit import RateLimit
from sqlalchemy.orm import Session

from smartmatch_api.dependencies import CurrentPrincipal, DbSession, charge_quota
from smartmatch_api.errors import ApiError
from smartmatch_api.units import load_unit_or_404
from smartmatch_api.utils import utc_now

router = APIRouter(prefix="/v1/units", tags=["cba-handoff"])

_repo: Final[CbaHandoffRepository] = CbaHandoffRepository()

#: ``admin`` and ``coordinator``, matching ``pipeline.py::_PIPELINE_ROLES`` and
#: ``outreach.py::_OUTREACH_ROLES``. The same set for the write and the read: a
#: coordinator who may record a handoff may obviously read the one they just
#: recorded, and splitting the two would give a widening two places to happen.
_HANDOFF_ROLES: Final[frozenset[str]] = frozenset({"admin", "coordinator"})

#: The write carries the tighter limit, the relationship ``outreach.py`` draws
#: between its draft and send limits. Reconciling thirty speakers a minute is
#: already faster than invitations can be answered.
HANDOFF_RATE_LIMIT: Final[RateLimit] = RateLimit(
    operation="cba.speaker_handoff", max_requests=30, window=timedelta(minutes=1)
)
CONFIRMED_READ_RATE_LIMIT: Final[RateLimit] = RateLimit(
    operation="cba.confirmed_speakers_read", max_requests=120, window=timedelta(minutes=1)
)


# ---------------------------------------------------------------------------
# Wire shapes
# ---------------------------------------------------------------------------


class SpeakerHandoffRequest(BaseModel):
    """Which invitation to reconcile, and optionally which attendance it cites.

    No ``stage`` field and no ``reached_at`` field, and their absence is the
    design rather than an omission: every stage and every timestamp this request
    can cause to be written is read out of the invitation or the attendance row.
    A request cannot assert that something happened, only name the record that
    already says so.
    """

    invitation_id: uuid.UUID = Field(
        description=(
            "The cba_invitation whose stored answer supplies the Confirmed stage. Must "
            "belong to this unit, and must record an accepted invitation."
        )
    )
    attendance_id: uuid.UUID | None = Field(
        default=None,
        description=(
            "The attendance_record the Attended stage cites. Optional -- a speaker who "
            "has confirmed but not yet presented is the ordinary state. Must belong to "
            "this speaker and to this event."
        ),
    )


class StageEvidenceView(BaseModel):
    """One stage, and the stored fact that makes it true."""

    stage: str
    evidence: str = Field(
        description=(
            "Which kind of stored row supports this stage: invitation_composed, "
            "invitation_dispatched, invitation_accepted, or attendance_record."
        )
    )
    occurred_at: datetime = Field(
        description="The evidencing row's own timestamp, not a server clock reading."
    )


class ConfirmedSpeakerView(BaseModel):
    """One confirmed speaker, as an Event Host is handed them.

    Carries **no** ``member_inquiry_at`` field. Not filtered, not nulled -- the
    field does not exist, so no client rendering this model can show a CBA
    member-inquiry outcome even by accident.

    The three identity fields are ``null`` when this tenant holds no
    ``speaker_profile`` for the id: an honest unknown, never a blank name
    standing in for one. The speaker is identified by ``professional_id``, and
    the name is for display only -- nothing about this record is derived from
    it.
    """

    record_id: uuid.UUID
    professional_id: uuid.UUID
    event_id: uuid.UUID
    full_name: str | None
    company: str | None
    title: str | None
    current_stage: str = Field(
        description="The furthest CBA stage reached, derived from the timestamps below."
    )
    matched_at: datetime
    contacted_at: datetime | None
    confirmed_at: datetime
    attended_at: datetime | None
    attendance_id: uuid.UUID | None = Field(
        description="The attendance_record the Attended stage cites, once it is reached."
    )
    stages: list[StageEvidenceView] = Field(
        default_factory=list,
        description=(
            "The stage-to-evidence map for this journey. Empty on the list surface, "
            "which reads stored rows rather than re-deriving the plan behind them."
        ),
    )


class SpeakerHandoffResponse(BaseModel):
    """What the reconciliation wrote, and the speaker it leaves behind.

    ``applied`` is only the stages *this request's own statements* reached, so a
    replay comes back with an empty list beside an unchanged speaker -- "they are
    confirmed" and "this request confirmed them" stay separable, the distinction
    ``PipelineStageOutcome`` draws between ``transitioned`` and
    ``already_reached``.
    """

    applied: list[str] = Field(
        description=(
            "Stages this request itself wrote. Empty when the evidence was already applied."
        )
    )
    speaker: ConfirmedSpeakerView


class ConfirmedSpeakerListResponse(BaseModel):
    """The confirmed speakers a unit can hand its Event Hosts."""

    unit_id: uuid.UUID
    event_id: uuid.UUID | None = Field(
        description="The event this list was filtered to, or null when it covers the unit."
    )
    speakers: list[ConfirmedSpeakerView]


# ---------------------------------------------------------------------------
# Authorization and views
# ---------------------------------------------------------------------------


def _authorize_handoff(
    session: Session, principal: CurrentPrincipal, unit_id: uuid.UUID
) -> uuid.UUID:
    """Load the unit and authorize a coordinator against *that row's* path.

    Shared by both operations, in the spirit of
    ``pipeline.py::_authorize_pipeline``: they ask the identical question
    against the identical resource, so a widening applies to both or to neither.

    Returns:
        The loaded unit's own id -- the scope every row below is filtered by, so
        it comes from the authorized row and never from a body or a query.
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
        required_roles=_HANDOFF_ROLES,
    )
    return unit.id


def _current_cba_stage(speaker: ConfirmedSpeakerRow) -> str:
    """The furthest **CBA** stage reached, walked in the CBA funnel's own order.

    ``CBA_STAGE_SEQUENCE`` is walked rather than a local tuple, so this cannot
    disagree with the domain about the order -- and cannot report
    ``member_inquiry``, because that stage is not in the sequence it walks.
    """
    reached: dict[PipelineStage, datetime | None] = {
        PipelineStage.MATCHED: speaker.matched_at,
        PipelineStage.CONTACTED: speaker.contacted_at,
        PipelineStage.CONFIRMED: speaker.confirmed_at,
        PipelineStage.ATTENDED: speaker.attended_at,
    }
    furthest = PipelineStage.MATCHED
    for stage in CBA_STAGE_SEQUENCE:
        if reached[stage] is not None:
            furthest = stage
    return furthest.value


def _speaker_view(
    speaker: ConfirmedSpeakerRow, evidence: tuple[CbaStageEvidence, ...] = ()
) -> ConfirmedSpeakerView:
    return ConfirmedSpeakerView(
        record_id=speaker.record_id,
        professional_id=speaker.professional_id,
        event_id=speaker.opportunity_event_id,
        full_name=speaker.full_name,
        company=speaker.company,
        title=speaker.title,
        current_stage=_current_cba_stage(speaker),
        matched_at=speaker.matched_at,
        contacted_at=speaker.contacted_at,
        confirmed_at=speaker.confirmed_at,
        attended_at=speaker.attended_at,
        attendance_id=speaker.attended_attendance_id,
        stages=[
            StageEvidenceView(
                stage=item.stage.value, evidence=item.kind.value, occurred_at=item.occurred_at
            )
            for item in evidence
        ],
    )


def _confirmed_speaker_or_unreachable(
    session: Session,
    principal: CurrentPrincipal,
    *,
    owning_unit_id: uuid.UUID,
    event_id: uuid.UUID,
    professional_id: uuid.UUID,
) -> ConfirmedSpeakerRow:
    """Read back the row the write just produced, through the Host's own query.

    Deliberately the *same* read the Host list uses, rather than a projection of
    the repository's return value: if the two ever disagreed about which
    journeys are confirmed, the write path would report a speaker the Host's own
    list would not show, and this is where that becomes a loud failure instead
    of a quiet inconsistency.
    """
    matches = _repo.list_confirmed_speakers(
        session,
        tenant_id=principal.tenant_id,
        owning_unit_id=owning_unit_id,
        opportunity_event_id=event_id,
    )
    for speaker in matches:
        if speaker.professional_id == professional_id:
            return speaker
    raise RuntimeError(  # pragma: no cover - the write above just confirmed them
        f"pipeline_record for speaker {professional_id} at event {event_id} is confirmed "
        "but absent from the confirmed-speaker query that publishes it"
    )


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.post(
    "/{unit_id}/cba/events/{event_id}/speaker-handoff",
    response_model=SpeakerHandoffResponse,
    summary="Record the funnel stages an invitation and attendance already evidence",
)
def reconcile_speaker_handoff(
    principal: CurrentPrincipal,
    session: DbSession,
    body: SpeakerHandoffRequest,
    unit_id: Annotated[uuid.UUID, Path()],
    event_id: Annotated[uuid.UUID, Path()],
) -> SpeakerHandoffResponse:
    """Bring one speaker's journey up to whatever the stored evidence supports.

    Writes ``matched`` from the invitation's ``created_at``, ``contacted`` from
    its ``dispatched_at``, ``confirmed`` from its ``response_recorded_at`` -- and
    only when the Speaker accepted -- and, when ``attendance_id`` is given,
    ``attended`` from that attendance row's own timestamp. Nothing is inferred
    and nothing is defaulted: a stage whose evidence is absent is not written.

    A repeat is a ``200`` with an empty ``applied``, not a ``409``: a coordinator
    re-running a handoff has asked for nothing illegal, and the speaker they get
    back is the one that was already there.

    Raises:
        ApiError: 404 when the invitation is not in this unit or the event is
            not in this tenant; 409 when the invitation records no acceptance,
            when the cited attendance is not this journey's, or when the stored
            timestamps cannot be ordered into the funnel.
    """
    charge_quota(session, principal, HANDOFF_RATE_LIMIT)

    owning_unit_id = _authorize_handoff(session, principal, unit_id)
    try:
        outcome = _repo.reconcile_invitation(
            session,
            tenant_id=principal.tenant_id,
            owning_unit_id=owning_unit_id,
            opportunity_event_id=event_id,
            invitation_id=body.invitation_id,
            attendance_id=body.attendance_id,
        )
    except CbaInvitationNotFoundError as exc:
        raise ApiError(
            status_code=status.HTTP_404_NOT_FOUND,
            code="cba_invitation_not_found",
            message="No such invitation in this unit.",
        ) from exc
    except UnknownOpportunityEventError as exc:
        raise ApiError(
            status_code=status.HTTP_404_NOT_FOUND,
            code="cba_event_not_found",
            message="No such event in this tenant.",
        ) from exc
    except CbaInvitationNotConfirmedError as exc:
        raise ApiError(
            status_code=status.HTTP_409_CONFLICT,
            code="cba_invitation_not_accepted",
            message=(
                "This invitation does not record an accepted invitation. The Confirmed "
                "stage is supplied by the Speaker's own answer; there is nothing here "
                "to hand an Event Host yet."
            ),
        ) from exc
    except UnknownAttendanceEvidenceError as exc:
        raise ApiError(
            status_code=status.HTTP_409_CONFLICT,
            code="cba_attendance_evidence_not_found",
            message=(
                "The attendance record this Attended claim cites does not exist in this "
                "tenant. The stage cites attendance; it does not create it."
            ),
        ) from exc
    except CbaAttendanceMismatchError as exc:
        raise ApiError(
            status_code=status.HTTP_409_CONFLICT,
            code="cba_attendance_evidence_mismatch",
            message=str(exc),
        ) from exc
    except PipelineStageOrderError as exc:
        raise ApiError(
            status_code=status.HTTP_409_CONFLICT,
            code="pipeline_stage_out_of_order",
            message=str(exc),
        ) from exc
    except ConflictingOwningUnitError as exc:
        raise ApiError(
            status_code=status.HTTP_409_CONFLICT,
            code="pipeline_record_unit_conflict",
            message=str(exc),
        ) from exc

    speaker = _confirmed_speaker_or_unreachable(
        session,
        principal,
        owning_unit_id=owning_unit_id,
        event_id=event_id,
        professional_id=outcome.record.subject_id,
    )
    # The commit `get_session` will not do for us: it rolls back unconditionally,
    # so without this the route returns a cheerful 200 and stores nothing.
    session.commit()
    return SpeakerHandoffResponse(
        applied=[stage.value for stage in outcome.applied],
        speaker=_speaker_view(speaker, outcome.evidence),
    )


@router.get(
    "/{unit_id}/cba/confirmed-speakers",
    response_model=ConfirmedSpeakerListResponse,
    summary="List the confirmed speakers this unit can hand an Event Host",
)
def list_confirmed_speakers(
    principal: CurrentPrincipal,
    session: DbSession,
    unit_id: Annotated[uuid.UUID, Path()],
    event_id: Annotated[uuid.UUID | None, Query()] = None,
) -> ConfirmedSpeakerListResponse:
    """The speakers whose ``confirmed_at`` is set, in this unit.

    With no ``event_id`` this is the *same set* the ``pipeline_confirmed``
    aggregate counts -- the same predicate against the same table, scoped by the
    same tenant and unit. It is not a second count of that metric: it reports no
    total, only which speakers and who they are, which the aggregate cannot say
    and the register does not publish.

    Ordered by ``confirmed_at`` then ``id``, so the Host reads them in the order
    they said yes.
    """
    charge_quota(session, principal, CONFIRMED_READ_RATE_LIMIT)

    owning_unit_id = _authorize_handoff(session, principal, unit_id)
    speakers = _repo.list_confirmed_speakers(
        session,
        tenant_id=principal.tenant_id,
        owning_unit_id=owning_unit_id,
        opportunity_event_id=event_id,
    )
    return ConfirmedSpeakerListResponse(
        unit_id=unit_id,
        event_id=event_id,
        speakers=[_speaker_view(speaker) for speaker in speakers],
    )
