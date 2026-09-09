"""Published speaker rosters, deterministic matching, and shared handoffs."""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timedelta
from typing import Annotated, Any, Literal

import sqlalchemy as sa
from fastapi import APIRouter, Header, Path, Query
from pydantic import BaseModel, Field, field_validator
from smartmatch_authz import OrgPath, Resource, assert_allowed
from smartmatch_domain.speaker_invitations import TERMINAL_STATUSES, can_correct, can_transition
from smartmatch_domain.speaker_matching import suggest_speakers
from smartmatch_persistence import schema
from smartmatch_persistence.rate_limit import RateLimit
from smartmatch_persistence.speaker_workflow import SpeakerWorkflowRepository

from smartmatch_api.dependencies import CurrentPrincipal, DbSession, charge_quota
from smartmatch_api.errors import ApiError
from smartmatch_api.units import load_unit_or_404
from smartmatch_api.utils import utc_now

router = APIRouter(prefix="/v1/units", tags=["speakers"])
_repo = SpeakerWorkflowRepository()
_ADMIN = frozenset({"admin"})
_SHARED = frozenset({"admin", "coordinator"})
SPEAKER_WRITE_RATE_LIMIT = RateLimit(
    operation="speaker-workflow.write", max_requests=90, window=timedelta(minutes=1)
)

SpeakerEventStatus = Literal[
    "not_emailed_yet",
    "awaiting_response",
    "declined",
    "ready_for_handoff",
    "handed_off",
    "awaiting_final_confirmation",
    "confirmed",
    "withdrawn",
    "attended",
    "did_not_attend",
    "event_cancelled",
]


def _authorize(session: Any, principal: Any, unit_id: uuid.UUID, roles: frozenset[str]) -> None:
    unit = load_unit_or_404(session, tenant_id=principal.tenant_id, unit_id=unit_id)
    assert_allowed(
        principal.principal,
        Resource(
            resource_type="org_unit",
            resource_id=str(unit.id),
            tenant_id=str(principal.tenant_id),
            owning_unit_path=OrgPath.parse(unit.path),
        ),
        at=utc_now(),
        required_roles=roles,
        require_membership=True,
    )


class SpeakerInput(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    title: str | None = Field(default=None, max_length=200)
    company: str | None = Field(default=None, max_length=200)
    board_role: str | None = Field(default=None, max_length=200)
    expertise_topics: list[str] = Field(default_factory=list, max_length=30)
    home_region: str | None = Field(default=None, max_length=200)
    service_regions: list[str] = Field(default_factory=list, max_length=30)
    contact_email: str | None = Field(default=None, max_length=320)
    contact_phone: str | None = Field(default=None, max_length=60)
    available: bool = True
    active: bool = True

    @field_validator("name")
    @classmethod
    def name_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("name must not be blank")
        return value.strip()

    @field_validator("expertise_topics", "service_regions")
    @classmethod
    def normalize_list(cls, values: list[str]) -> list[str]:
        normalized = list(dict.fromkeys(value.strip() for value in values if value.strip()))
        if any(len(value) > 100 for value in normalized):
            raise ValueError("entries must be at most 100 characters")
        return normalized


class SpeakerPatch(BaseModel):
    version: int = Field(ge=1)
    name: str | None = Field(default=None, min_length=1, max_length=200)
    title: str | None = Field(default=None, max_length=200)
    company: str | None = Field(default=None, max_length=200)
    board_role: str | None = Field(default=None, max_length=200)
    expertise_topics: list[str] | None = Field(default=None, max_length=30)
    home_region: str | None = Field(default=None, max_length=200)
    service_regions: list[str] | None = Field(default=None, max_length=30)
    contact_email: str | None = Field(default=None, max_length=320)
    contact_phone: str | None = Field(default=None, max_length=60)
    available: bool | None = None
    active: bool | None = None

    @field_validator("name")
    @classmethod
    def optional_name_not_blank(cls, value: str | None) -> str | None:
        return SpeakerInput.name_not_blank(value) if value is not None else None

    @field_validator("expertise_topics", "service_regions")
    @classmethod
    def normalize_optional_list(cls, values: list[str] | None) -> list[str] | None:
        return SpeakerInput.normalize_list(values) if values is not None else None


class SpeakerResponse(SpeakerInput):
    id: uuid.UUID
    version: int
    created_at: datetime
    updated_at: datetime


class PublicSpeakerResponse(BaseModel):
    id: uuid.UUID
    name: str
    title: str | None
    company: str | None
    board_role: str | None
    expertise_topics: list[str]
    home_region: str | None
    service_regions: list[str]


class SpeakerListResponse(BaseModel):
    data: list[SpeakerResponse | PublicSpeakerResponse]
    total: int
    roster_version: int | None = None
    published_at: datetime | None = None


def _speaker(row: Any, *, private: bool) -> SpeakerResponse | PublicSpeakerResponse:
    payload = dict(row)
    if "speaker_id" in payload:
        payload["id"] = payload.pop("speaker_id")
    return (SpeakerResponse if private else PublicSpeakerResponse).model_validate(payload)


@router.post("/{unit_id}/speakers", response_model=SpeakerResponse, status_code=201)
def create_speaker(
    principal: CurrentPrincipal,
    session: DbSession,
    body: SpeakerInput,
    unit_id: Annotated[uuid.UUID, Path()],
) -> SpeakerResponse:
    charge_quota(session, principal, SPEAKER_WRITE_RATE_LIMIT)
    _authorize(session, principal, unit_id, _ADMIN)
    row = _repo.create_speaker(
        session,
        tenant_id=principal.tenant_id,
        unit_id=unit_id,
        actor_id=principal.user_id,
        values=body.model_dump(),
    )
    session.commit()
    return SpeakerResponse.model_validate(row)


@router.get("/{unit_id}/speakers", response_model=SpeakerListResponse)
def list_speakers(
    principal: CurrentPrincipal, session: DbSession, unit_id: Annotated[uuid.UUID, Path()]
) -> SpeakerListResponse:
    _authorize(session, principal, unit_id, _SHARED)
    unit = load_unit_or_404(session, tenant_id=principal.tenant_id, unit_id=unit_id)
    unit_path = OrgPath.parse(unit.path)
    private = any(
        m.role == "admin" and m.is_active_at(utc_now()) and m.granted_path.contains(unit_path)
        for m in principal.principal.memberships
    )
    rows = _repo.list_speakers(
        session, tenant_id=principal.tenant_id, unit_id=unit_id, published=not private
    )
    roster = (
        session.execute(
            sa.select(schema.speaker_roster).where(
                schema.speaker_roster.c.tenant_id == principal.tenant_id,
                schema.speaker_roster.c.owning_unit_id == unit_id,
            )
        )
        .mappings()
        .one_or_none()
    )
    return SpeakerListResponse(
        data=[_speaker(row, private=private) for row in rows],
        total=len(rows),
        roster_version=roster["version"] if roster else None,
        published_at=roster["published_at"] if roster else None,
    )


@router.get("/{unit_id}/speakers/{speaker_id}", response_model=SpeakerResponse)
def get_speaker(
    principal: CurrentPrincipal,
    session: DbSession,
    unit_id: Annotated[uuid.UUID, Path()],
    speaker_id: Annotated[uuid.UUID, Path()],
) -> SpeakerResponse:
    _authorize(session, principal, unit_id, _ADMIN)
    row = _repo.get_speaker(
        session, tenant_id=principal.tenant_id, unit_id=unit_id, speaker_id=speaker_id
    )
    if not row:
        raise ApiError(status_code=404, code="speaker_not_found", message="No such speaker.")
    return SpeakerResponse.model_validate(row)


@router.patch("/{unit_id}/speakers/{speaker_id}", response_model=SpeakerResponse)
def update_speaker(
    principal: CurrentPrincipal,
    session: DbSession,
    body: SpeakerPatch,
    unit_id: Annotated[uuid.UUID, Path()],
    speaker_id: Annotated[uuid.UUID, Path()],
) -> SpeakerResponse:
    charge_quota(session, principal, SPEAKER_WRITE_RATE_LIMIT)
    _authorize(session, principal, unit_id, _ADMIN)
    values = body.model_dump(exclude={"version"}, exclude_unset=True)
    row = _repo.update_speaker(
        session,
        tenant_id=principal.tenant_id,
        unit_id=unit_id,
        speaker_id=speaker_id,
        version=body.version,
        values=values,
    )
    if not row:
        raise ApiError(
            status_code=409,
            code="stale_speaker",
            message="This speaker changed. Refresh and try again.",
        )
    session.commit()
    return SpeakerResponse.model_validate(row)


class PublishRosterResponse(BaseModel):
    version: int
    published_at: datetime


@router.post("/{unit_id}/speaker-roster/publish", response_model=PublishRosterResponse)
def publish_roster(
    principal: CurrentPrincipal, session: DbSession, unit_id: Annotated[uuid.UUID, Path()]
) -> PublishRosterResponse:
    charge_quota(session, principal, SPEAKER_WRITE_RATE_LIMIT)
    _authorize(session, principal, unit_id, _ADMIN)
    version, published_at = _repo.publish_roster(
        session, tenant_id=principal.tenant_id, unit_id=unit_id, actor_id=principal.user_id
    )
    session.commit()
    return PublishRosterResponse(version=version, published_at=published_at)


class MatchSuggestion(BaseModel):
    speaker_id: uuid.UUID
    name: str
    title: str | None
    company: str | None
    board_role: str | None
    expertise_topics: list[str]
    home_region: str | None
    service_regions: list[str]
    explanations: list[str]


class MatchRunResponse(BaseModel):
    id: uuid.UUID
    event_id: uuid.UUID
    suggestions: list[MatchSuggestion]
    created_at: datetime


def _match_response(session: Any, principal: Any, unit_id: uuid.UUID, run: Any) -> MatchRunResponse:
    rows = _repo.match_results(
        session, tenant_id=principal.tenant_id, unit_id=unit_id, run_id=run["id"]
    )
    return MatchRunResponse(
        id=run["id"],
        event_id=run["event_id"],
        created_at=run["created_at"],
        suggestions=[MatchSuggestion.model_validate(row) for row in rows],
    )


@router.post(
    "/{unit_id}/events/{event_id}/match-runs", response_model=MatchRunResponse, status_code=201
)
def run_match(
    principal: CurrentPrincipal,
    session: DbSession,
    unit_id: Annotated[uuid.UUID, Path()],
    event_id: Annotated[uuid.UUID, Path()],
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=1, max_length=200)],
) -> MatchRunResponse:
    charge_quota(session, principal, SPEAKER_WRITE_RATE_LIMIT)
    _authorize(session, principal, unit_id, frozenset({"coordinator"}))
    event = _repo_event(session, principal.tenant_id, unit_id, event_id)
    if not event or event["status"] != "published":
        raise ApiError(
            status_code=404, code="event_not_found", message="No published event was found."
        )
    profiles = _repo.list_speakers(
        session, tenant_id=principal.tenant_id, unit_id=unit_id, published=True
    )
    results = suggest_speakers(event["speaker_topics"], event["region"], profiles)
    fingerprint = hashlib.sha256(
        json.dumps(
            {"event_id": str(event_id), "version": event["version"]}, sort_keys=True
        ).encode()
    ).hexdigest()
    try:
        run, _ = _repo.create_match_run(
            session,
            tenant_id=principal.tenant_id,
            unit_id=unit_id,
            event_id=event_id,
            actor_id=principal.user_id,
            idempotency_key=idempotency_key,
            fingerprint=fingerprint,
            results=results,
        )
    except ValueError as exc:
        raise ApiError(
            status_code=409,
            code=str(exc),
            message="Publish the speaker roster before running Smart Match."
            if str(exc) == "roster_not_published"
            else "That request key was already used.",
        ) from exc
    session.commit()
    return _match_response(session, principal, unit_id, run)


class ShortlistInput(BaseModel):
    speaker_ids: list[uuid.UUID] = Field(min_length=1, max_length=3)


class SpeakerEventSummary(BaseModel):
    id: uuid.UUID
    event_id: uuid.UUID
    speaker_id: uuid.UUID
    assigned_host_id: uuid.UUID
    status: SpeakerEventStatus
    version: int
    speaker_name: str
    speaker_title: str | None
    speaker_company: str | None
    event_title: str
    created_at: datetime
    updated_at: datetime


@router.post(
    "/{unit_id}/match-runs/{match_run_id}/shortlist",
    response_model=list[SpeakerEventSummary],
)
def submit_shortlist(
    principal: CurrentPrincipal,
    session: DbSession,
    body: ShortlistInput,
    unit_id: Annotated[uuid.UUID, Path()],
    match_run_id: Annotated[uuid.UUID, Path()],
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=1, max_length=200)],
) -> list[SpeakerEventSummary]:
    charge_quota(session, principal, SPEAKER_WRITE_RATE_LIMIT)
    _authorize(session, principal, unit_id, frozenset({"coordinator"}))
    run = _repo.get_run(
        session, tenant_id=principal.tenant_id, unit_id=unit_id, run_id=match_run_id
    )
    if not run:
        raise ApiError(status_code=404, code="match_run_not_found", message="No such match run.")
    try:
        rows = _repo.submit_shortlist(
            session,
            tenant_id=principal.tenant_id,
            unit_id=unit_id,
            run=run,
            speaker_ids=list(dict.fromkeys(body.speaker_ids)),
            actor_id=principal.user_id,
            idempotency_key=idempotency_key,
        )
    except ValueError as exc:
        conflict = str(exc) == "idempotency_conflict"
        raise ApiError(
            status_code=409,
            code="idempotency_conflict" if conflict else "invalid_shortlist",
            message=(
                "That request key was already used for another shortlist."
                if conflict
                else "Choose speakers from this match run."
            ),
        ) from exc
    session.commit()
    return [SpeakerEventSummary.model_validate(row) for row in rows]


class HistoryItem(BaseModel):
    id: uuid.UUID
    from_status: str | None
    to_status: str
    action_kind: str
    actor_id: uuid.UUID
    note: str | None
    correction_reason: str | None
    created_at: datetime


class NoteItem(BaseModel):
    id: uuid.UUID
    actor_id: uuid.UUID
    body: str
    created_at: datetime


class SpeakerEventResponse(SpeakerEventSummary):
    history: list[HistoryItem] = Field(default_factory=list)
    notes: list[NoteItem] = Field(default_factory=list)


def _record_response(
    session: Any, principal: Any, unit_id: uuid.UUID, row: Any, detail: bool = False
) -> SpeakerEventResponse:
    payload = dict(row)
    if detail:
        payload["history"] = _repo.history(
            session, tenant_id=principal.tenant_id, unit_id=unit_id, record_id=row["id"]
        )
        payload["notes"] = _repo.notes(
            session, tenant_id=principal.tenant_id, unit_id=unit_id, record_id=row["id"]
        )
    return SpeakerEventResponse.model_validate(payload)


@router.get("/{unit_id}/speaker-events", response_model=list[SpeakerEventResponse])
def list_speaker_events(
    principal: CurrentPrincipal,
    session: DbSession,
    unit_id: Annotated[uuid.UUID, Path()],
    event_id: Annotated[uuid.UUID | None, Query()] = None,
) -> list[SpeakerEventResponse]:
    _authorize(session, principal, unit_id, _SHARED)
    return [
        _record_response(session, principal, unit_id, row)
        for row in _repo.list_records(
            session, tenant_id=principal.tenant_id, unit_id=unit_id, event_id=event_id
        )
    ]


@router.get("/{unit_id}/speaker-events/{record_id}", response_model=SpeakerEventResponse)
def get_speaker_event(
    principal: CurrentPrincipal,
    session: DbSession,
    unit_id: Annotated[uuid.UUID, Path()],
    record_id: Annotated[uuid.UUID, Path()],
) -> SpeakerEventResponse:
    _authorize(session, principal, unit_id, _SHARED)
    row = _repo.get_record(
        session, tenant_id=principal.tenant_id, unit_id=unit_id, record_id=record_id
    )
    if not row:
        raise ApiError(
            status_code=404, code="speaker_event_not_found", message="No such speaker handoff."
        )
    return _record_response(session, principal, unit_id, row, True)


class TransitionInput(BaseModel):
    to_status: SpeakerEventStatus
    expected_version: int = Field(ge=1)
    note: str | None = Field(default=None, max_length=2000)


def _is_admin_for_unit(session: Any, principal: Any, unit_id: uuid.UUID) -> bool:
    unit = load_unit_or_404(session, tenant_id=principal.tenant_id, unit_id=unit_id)
    unit_path = OrgPath.parse(unit.path)
    return any(
        m.role == "admin" and m.is_active_at(utc_now()) and m.granted_path.contains(unit_path)
        for m in principal.principal.memberships
    )


@router.post(
    "/{unit_id}/speaker-events/{record_id}/transitions", response_model=SpeakerEventResponse
)
def transition(
    principal: CurrentPrincipal,
    session: DbSession,
    body: TransitionInput,
    unit_id: Annotated[uuid.UUID, Path()],
    record_id: Annotated[uuid.UUID, Path()],
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=1, max_length=200)],
) -> SpeakerEventResponse:
    charge_quota(session, principal, SPEAKER_WRITE_RATE_LIMIT)
    _authorize(session, principal, unit_id, _SHARED)
    current = _repo.get_record(
        session, tenant_id=principal.tenant_id, unit_id=unit_id, record_id=record_id
    )
    if not current:
        raise ApiError(
            status_code=404, code="speaker_event_not_found", message="No such speaker handoff."
        )
    replay_record_id = session.scalar(
        sa.select(schema.speaker_event_history.c.speaker_event_id).where(
            schema.speaker_event_history.c.tenant_id == principal.tenant_id,
            schema.speaker_event_history.c.owning_unit_id == unit_id,
            schema.speaker_event_history.c.idempotency_key == idempotency_key,
        )
    )
    if replay_record_id is not None:
        if replay_record_id != record_id:
            raise ApiError(
                status_code=409,
                code="idempotency_conflict",
                message="That request key was already used for another handoff.",
            )
        return _record_response(session, principal, unit_id, current, True)
    is_admin = _is_admin_for_unit(session, principal, unit_id)
    role = "admin" if is_admin else "coordinator"
    if not is_admin and current["assigned_host_id"] != principal.user_id:
        raise ApiError(
            status_code=404, code="speaker_event_not_found", message="No such speaker handoff."
        )
    if not can_transition(role, current["status"], body.to_status):
        raise ApiError(
            status_code=409,
            code="invalid_transition",
            message="That status change is not available at this stage.",
        )
    try:
        row = _repo.change_status(
            session,
            tenant_id=principal.tenant_id,
            unit_id=unit_id,
            record_id=record_id,
            expected_version=body.expected_version,
            to_status=body.to_status,
            actor_id=principal.user_id,
            action_kind="transition",
            idempotency_key=idempotency_key,
            note=body.note,
        )
    except RuntimeError as exc:
        raise ApiError(
            status_code=409,
            code="stale_record",
            message="This handoff changed. Refresh and try again.",
        ) from exc
    session.commit()
    assert row
    return _record_response(session, principal, unit_id, row, True)


class NoteInput(BaseModel):
    body: str = Field(min_length=1, max_length=2000)


@router.post(
    "/{unit_id}/speaker-events/{record_id}/notes", response_model=NoteItem, status_code=201
)
def add_note(
    principal: CurrentPrincipal,
    session: DbSession,
    body: NoteInput,
    unit_id: Annotated[uuid.UUID, Path()],
    record_id: Annotated[uuid.UUID, Path()],
) -> NoteItem:
    charge_quota(session, principal, SPEAKER_WRITE_RATE_LIMIT)
    _authorize(session, principal, unit_id, _SHARED)
    if not _repo.get_record(
        session, tenant_id=principal.tenant_id, unit_id=unit_id, record_id=record_id
    ):
        raise ApiError(
            status_code=404, code="speaker_event_not_found", message="No such speaker handoff."
        )
    row = _repo.add_note(
        session,
        tenant_id=principal.tenant_id,
        unit_id=unit_id,
        record_id=record_id,
        actor_id=principal.user_id,
        body=body.body.strip(),
    )
    session.commit()
    return NoteItem.model_validate(row)


class CorrectionInput(BaseModel):
    to_status: SpeakerEventStatus
    expected_version: int = Field(ge=1)
    reason: str = Field(min_length=1, max_length=1000)


@router.post(
    "/{unit_id}/speaker-events/{record_id}/corrections", response_model=SpeakerEventResponse
)
def correct_status(
    principal: CurrentPrincipal,
    session: DbSession,
    body: CorrectionInput,
    unit_id: Annotated[uuid.UUID, Path()],
    record_id: Annotated[uuid.UUID, Path()],
) -> SpeakerEventResponse:
    charge_quota(session, principal, SPEAKER_WRITE_RATE_LIMIT)
    _authorize(session, principal, unit_id, _ADMIN)
    current = _repo.get_record(
        session, tenant_id=principal.tenant_id, unit_id=unit_id, record_id=record_id
    )
    if not current:
        raise ApiError(
            status_code=404, code="speaker_event_not_found", message="No such speaker handoff."
        )
    if not can_correct(current["status"], body.to_status):
        raise ApiError(
            status_code=409,
            code="unsafe_correction",
            message="Corrections cannot create attendance or override a cancelled event.",
        )
    try:
        row = _repo.change_status(
            session,
            tenant_id=principal.tenant_id,
            unit_id=unit_id,
            record_id=record_id,
            expected_version=body.expected_version,
            to_status=body.to_status,
            actor_id=principal.user_id,
            action_kind="correction",
            idempotency_key=None,
            correction_reason=body.reason.strip(),
        )
    except RuntimeError as exc:
        raise ApiError(
            status_code=409,
            code="stale_record",
            message="This handoff changed. Refresh and try again.",
        ) from exc
    session.commit()
    assert row
    return _record_response(session, principal, unit_id, row, True)


class EventActionInput(BaseModel):
    expected_version: int = Field(ge=1)
    reason: str | None = Field(default=None, max_length=1000)


def _repo_event(session: Any, tenant_id: uuid.UUID, unit_id: uuid.UUID, event_id: uuid.UUID):
    return (
        session.execute(
            sa.select(schema.event).where(
                schema.event.c.tenant_id == tenant_id,
                schema.event.c.owning_unit_id == unit_id,
                schema.event.c.id == event_id,
            )
        )
        .mappings()
        .one_or_none()
    )


@router.post(
    "/{unit_id}/events/{event_id}/close-attendance", response_model=list[SpeakerEventResponse]
)
def close_attendance(
    principal: CurrentPrincipal,
    session: DbSession,
    body: EventActionInput,
    unit_id: Annotated[uuid.UUID, Path()],
    event_id: Annotated[uuid.UUID, Path()],
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=1, max_length=200)],
) -> list[SpeakerEventResponse]:
    charge_quota(session, principal, SPEAKER_WRITE_RATE_LIMIT)
    _authorize(session, principal, unit_id, frozenset({"coordinator"}))
    event = _repo_event(session, principal.tenant_id, unit_id, event_id)
    if not event or event["status"] == "cancelled":
        raise ApiError(
            status_code=404, code="event_not_found", message="No active event was found."
        )
    if event["attendance_closed_at"] is None:
        changed = session.execute(
            sa.update(schema.event)
            .where(
                schema.event.c.id == event_id,
                schema.event.c.tenant_id == principal.tenant_id,
                schema.event.c.owning_unit_id == unit_id,
                schema.event.c.version == body.expected_version,
            )
            .values(
                attendance_closed_at=sa.func.now(),
                attendance_closed_by=principal.user_id,
                version=body.expected_version + 1,
            )
        ).rowcount
        if not changed:
            raise ApiError(
                status_code=409,
                code="stale_event",
                message="This event changed. Refresh and try again.",
            )
        records = _repo.list_records(
            session, tenant_id=principal.tenant_id, unit_id=unit_id, event_id=event_id
        )
        for record in records:
            if record["status"] == "confirmed":
                _repo.change_status(
                    session,
                    tenant_id=principal.tenant_id,
                    unit_id=unit_id,
                    record_id=record["id"],
                    expected_version=record["version"],
                    to_status="did_not_attend",
                    actor_id=principal.user_id,
                    action_kind="attendance_close",
                    idempotency_key=f"{idempotency_key}:{record['id']}",
                )
    session.commit()
    return [
        _record_response(session, principal, unit_id, row)
        for row in _repo.list_records(
            session, tenant_id=principal.tenant_id, unit_id=unit_id, event_id=event_id
        )
    ]


@router.post("/{unit_id}/events/{event_id}/cancel", response_model=list[SpeakerEventResponse])
def cancel_event(
    principal: CurrentPrincipal,
    session: DbSession,
    body: EventActionInput,
    unit_id: Annotated[uuid.UUID, Path()],
    event_id: Annotated[uuid.UUID, Path()],
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=1, max_length=200)],
) -> list[SpeakerEventResponse]:
    charge_quota(session, principal, SPEAKER_WRITE_RATE_LIMIT)
    _authorize(session, principal, unit_id, _ADMIN)
    event = _repo_event(session, principal.tenant_id, unit_id, event_id)
    if not event:
        raise ApiError(status_code=404, code="event_not_found", message="No such event.")
    if event["attendance_closed_at"] is not None:
        raise ApiError(
            status_code=409,
            code="attendance_closed",
            message="An event cannot be cancelled after attendance is closed.",
        )
    if event["status"] != "cancelled":
        changed = session.execute(
            sa.update(schema.event)
            .where(
                schema.event.c.id == event_id,
                schema.event.c.tenant_id == principal.tenant_id,
                schema.event.c.owning_unit_id == unit_id,
                schema.event.c.version == body.expected_version,
            )
            .values(
                status="cancelled",
                cancelled_at=sa.func.now(),
                cancelled_by=principal.user_id,
                cancellation_reason=body.reason,
                version=body.expected_version + 1,
            )
        ).rowcount
        if not changed:
            raise ApiError(
                status_code=409,
                code="stale_event",
                message="This event changed. Refresh and try again.",
            )
        for record in _repo.list_records(
            session, tenant_id=principal.tenant_id, unit_id=unit_id, event_id=event_id
        ):
            if record["status"] not in TERMINAL_STATUSES:
                _repo.change_status(
                    session,
                    tenant_id=principal.tenant_id,
                    unit_id=unit_id,
                    record_id=record["id"],
                    expected_version=record["version"],
                    to_status="event_cancelled",
                    actor_id=principal.user_id,
                    action_kind="event_cancelled",
                    idempotency_key=f"{idempotency_key}:{record['id']}",
                    note=body.reason,
                )
    session.commit()
    return [
        _record_response(session, principal, unit_id, row)
        for row in _repo.list_records(
            session, tenant_id=principal.tenant_id, unit_id=unit_id, event_id=event_id
        )
    ]
