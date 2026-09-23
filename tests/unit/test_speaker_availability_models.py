"""Unit tests for the speaker-availability request/response models (B26 T3).

No database. Covers the body shape, the float -> ``Decimal`` conversion, the
expired-pause drop rule, the error mapping, the response for "not stated", and
``write_statement``'s validate-then-upsert order (plan-gate addition 2).
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any

import pytest
from pydantic import ValidationError
from smartmatch_api.errors import ApiError
from smartmatch_api.routers import speaker_availability_models as models
from smartmatch_api.routers.speaker_availability_models import (
    SpeakerAvailabilityUpdateRequest,
    availability_error,
    availability_response,
    stale_error,
    statement_from_request,
    write_statement,
)
from smartmatch_domain.speaker_availability import (
    MAX_WINDOWS,
    AvailabilityErrorCode,
    AvailabilityStatement,
    AvailabilityStatementInvalid,
    UnavailableWindow,
)
from smartmatch_persistence.speaker_availability import (
    AvailabilitySource,
    StaleSpeakerAvailabilityError,
    StoredSpeakerAvailability,
    StoredWindow,
)

TODAY = date(2026, 10, 6)
NOW = datetime(2026, 10, 6, 12, 0, tzinfo=UTC)

_FULL_BODY: dict[str, Any] = {
    "expected_version": None,
    "invitations_paused_until": None,
    "declared_capacity_hours_per_90_days": None,
    "unavailable": [],
}


def _body(**overrides: Any) -> SpeakerAvailabilityUpdateRequest:
    return SpeakerAvailabilityUpdateRequest.model_validate({**_FULL_BODY, **overrides})


def _stored(
    *,
    paused_until: date | None = None,
    capacity: Decimal | None = None,
    windows: tuple[StoredWindow, ...] = (),
    version: int = 1,
) -> StoredSpeakerAvailability:
    return StoredSpeakerAvailability(
        tenant_id=uuid.uuid4(),
        professional_id=uuid.uuid4(),
        statement=AvailabilityStatement(
            invitations_paused_until=paused_until,
            declared_capacity_hours_per_90_days=capacity,
            unavailable=tuple(UnavailableWindow(w.starts_on, w.ends_on) for w in windows),
        ),
        windows=windows,
        version=version,
        updated_source=AvailabilitySource.CONNECTOR,
        updated_by_user_id=uuid.uuid4(),
        created_at=NOW - timedelta(days=3),
        updated_at=NOW,
    )


# ---------------------------------------------------------------------------
# 1. Body shape
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("missing", sorted(_FULL_BODY))
def test_request_requires_all_four_keys(missing: str) -> None:
    payload = {key: value for key, value in _FULL_BODY.items() if key != missing}
    with pytest.raises(ValidationError):
        SpeakerAvailabilityUpdateRequest.model_validate(payload)


@pytest.mark.parametrize("extra", ["professional_id", "updated_source", "version"])
def test_request_forbids_extra_keys(extra: str) -> None:
    with pytest.raises(ValidationError):
        SpeakerAvailabilityUpdateRequest.model_validate({**_FULL_BODY, extra: "x"})


# ---------------------------------------------------------------------------
# 2. Number handling
# ---------------------------------------------------------------------------


def test_capacity_float_parses_via_str() -> None:
    statement = statement_from_request(
        _body(declared_capacity_hours_per_90_days=24.05), None, TODAY
    )
    assert statement.declared_capacity_hours_per_90_days == Decimal("24.05")


def test_capacity_int_becomes_decimal() -> None:
    statement = statement_from_request(_body(declared_capacity_hours_per_90_days=24), None, TODAY)
    assert statement.declared_capacity_hours_per_90_days == Decimal("24")
    assert isinstance(statement.declared_capacity_hours_per_90_days, Decimal)


@pytest.mark.parametrize("value", [True, "24"])
def test_capacity_bool_and_string_rejected(value: object) -> None:
    with pytest.raises(ValidationError):
        _body(declared_capacity_hours_per_90_days=value)


@pytest.mark.parametrize("value", [True, "3"])
def test_expected_version_bool_and_string_rejected(value: object) -> None:
    with pytest.raises(ValidationError):
        _body(expected_version=value)


# ---------------------------------------------------------------------------
# 3. Expired-pause drop rule
# ---------------------------------------------------------------------------


def test_expired_pause_equal_to_stored_is_dropped() -> None:
    past = TODAY - timedelta(days=2)
    statement = statement_from_request(
        _body(invitations_paused_until=past.isoformat()), _stored(paused_until=past), TODAY
    )
    assert statement.invitations_paused_until is None


def test_expired_pause_different_from_stored_is_kept() -> None:
    past = TODAY - timedelta(days=2)
    statement = statement_from_request(
        _body(invitations_paused_until=past.isoformat()),
        _stored(paused_until=past - timedelta(days=1)),
        TODAY,
    )
    assert statement.invitations_paused_until == past


def test_expired_pause_without_row_is_kept() -> None:
    past = TODAY - timedelta(days=2)
    statement = statement_from_request(
        _body(invitations_paused_until=past.isoformat()), None, TODAY
    )
    assert statement.invitations_paused_until == past


@pytest.mark.parametrize("offset", [0, 1, 30])
def test_today_and_future_pause_never_dropped(offset: int) -> None:
    when = TODAY + timedelta(days=offset)
    statement = statement_from_request(
        _body(invitations_paused_until=when.isoformat()), _stored(paused_until=when), TODAY
    )
    assert statement.invitations_paused_until == when


# ---------------------------------------------------------------------------
# 4. Windows
# ---------------------------------------------------------------------------


def test_windows_keep_request_order() -> None:
    later = {"starts_on": "2026-12-01", "ends_on": "2026-12-03"}
    earlier = {"starts_on": "2026-11-01", "ends_on": "2026-11-02"}
    statement = statement_from_request(_body(unavailable=[later, earlier]), None, TODAY)
    assert statement.unavailable == (
        UnavailableWindow(date(2026, 12, 1), date(2026, 12, 3)),
        UnavailableWindow(date(2026, 11, 1), date(2026, 11, 2)),
    )


# ---------------------------------------------------------------------------
# 5. Error mapping
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("exc", "details"),
    [
        (
            AvailabilityStatementInvalid(
                AvailabilityErrorCode.CAPACITY_INVALID, "declared_capacity_hours_per_90_days"
            ),
            {"field": "declared_capacity_hours_per_90_days"},
        ),
        (
            AvailabilityStatementInvalid(
                AvailabilityErrorCode.PAUSE_INVALID, "invitations_paused_until"
            ),
            {"field": "invitations_paused_until"},
        ),
        (
            AvailabilityStatementInvalid(AvailabilityErrorCode.TOO_MANY_WINDOWS, "unavailable"),
            {"field": "unavailable", "limit": MAX_WINDOWS},
        ),
        (
            AvailabilityStatementInvalid(AvailabilityErrorCode.WINDOW_INVALID, "unavailable", 3),
            {"field": "unavailable", "index": 3},
        ),
    ],
)
def test_availability_error_maps_each_code(
    exc: AvailabilityStatementInvalid, details: dict[str, Any]
) -> None:
    error = availability_error(exc)
    assert error.status_code == 422
    assert error.code == exc.code.value
    assert error.details == details


@pytest.mark.parametrize("code", list(AvailabilityErrorCode))
def test_error_message_never_contains_the_value(code: AvailabilityErrorCode) -> None:
    exc = AvailabilityStatementInvalid(code, "unavailable", 7)
    error = availability_error(exc)
    assert str(exc) not in error.message
    assert "7" not in error.message
    assert code.value not in error.message


def test_stale_error_is_409_without_details() -> None:
    error = stale_error()
    assert error.status_code == 409
    assert error.code == "speaker_availability_stale"
    assert error.details is None


# ---------------------------------------------------------------------------
# 6. Response
# ---------------------------------------------------------------------------


def test_response_for_no_row_is_not_stated() -> None:
    professional_id = uuid.uuid4()
    response = availability_response(professional_id, None)
    assert response.model_dump() == {
        "professional_id": professional_id,
        "stated": False,
        "version": None,
        "invitations_paused_until": None,
        "declared_capacity_hours_per_90_days": None,
        "unavailable": [],
        "updated_source": None,
        "updated_at": None,
    }


def test_response_maps_sources_and_capacity_as_float() -> None:
    windows = (
        StoredWindow(
            starts_on=date(2026, 11, 1),
            ends_on=date(2026, 11, 2),
            created_source=AvailabilitySource.SPEAKER,
            created_by_user_id=uuid.uuid4(),
            created_at=NOW,
        ),
        StoredWindow(
            starts_on=date(2026, 12, 1),
            ends_on=date(2026, 12, 3),
            created_source=AvailabilitySource.CONNECTOR,
            created_by_user_id=uuid.uuid4(),
            created_at=NOW,
        ),
    )
    stored = _stored(
        paused_until=date(2026, 10, 20), capacity=Decimal("24.5"), windows=windows, version=4
    )
    response = availability_response(stored.professional_id, stored)
    assert response.stated is True
    assert response.version == 4
    assert response.invitations_paused_until == date(2026, 10, 20)
    assert response.declared_capacity_hours_per_90_days == 24.5
    assert isinstance(response.declared_capacity_hours_per_90_days, float)
    assert [(w.starts_on, w.ends_on, w.source) for w in response.unavailable] == [
        (date(2026, 11, 1), date(2026, 11, 2), "speaker"),
        (date(2026, 12, 1), date(2026, 12, 3), "connector"),
    ]
    assert response.updated_source == "connector"
    assert response.updated_at == NOW
    dumped = response.model_dump()
    assert "updated_by_user_id" not in dumped
    assert all("created_by_user_id" not in w for w in dumped["unavailable"])


# ---------------------------------------------------------------------------
# write_statement: validate, then upsert (plan-gate addition 2)
# ---------------------------------------------------------------------------


class _RecordingRepository:
    """Stands in for ``SpeakerAvailabilityRepository``; records every upsert."""

    def __init__(self, *, raises: Exception | None = None) -> None:
        self.calls: list[dict[str, Any]] = []
        self._raises = raises

    def upsert(self, session: object, **kwargs: Any) -> StoredSpeakerAvailability:
        self.calls.append(kwargs)
        if self._raises is not None:
            raise self._raises
        return _stored(version=(kwargs["expected_version"] or 0) + 1)


def _write(repository: _RecordingRepository, statement: AvailabilityStatement) -> Any:
    return write_statement(
        object(),
        repository,  # type: ignore[arg-type]
        tenant_id=uuid.uuid4(),
        professional_id=uuid.uuid4(),
        statement=statement,
        today=TODAY,
        source=AvailabilitySource.CONNECTOR,
        actor_user_id=uuid.uuid4(),
        expected_version=None,
        now=NOW,
    )


_VALID = AvailabilityStatement(None, Decimal("10"), ())


def test_write_statement_never_upserts_when_the_validator_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _refuse(statement: AvailabilityStatement, today: date) -> None:
        raise AvailabilityStatementInvalid(
            AvailabilityErrorCode.CAPACITY_INVALID, "declared_capacity_hours_per_90_days"
        )

    monkeypatch.setattr(models, "validate_availability_statement", _refuse)
    repository = _RecordingRepository()
    with pytest.raises(ApiError) as raised:
        _write(repository, _VALID)
    assert raised.value.code == "speaker_availability_capacity_invalid"
    assert repository.calls == []


def test_write_statement_validates_then_upserts() -> None:
    repository = _RecordingRepository()
    result = _write(repository, _VALID)
    assert result.version == 1
    assert len(repository.calls) == 1
    call = repository.calls[0]
    assert call["statement"] == _VALID
    assert call["source"] is AvailabilitySource.CONNECTOR
    assert call["expected_version"] is None
    assert call["now"] == NOW


def test_write_statement_rejects_a_domain_invalid_statement() -> None:
    repository = _RecordingRepository()
    with pytest.raises(ApiError) as raised:
        _write(repository, AvailabilityStatement(None, Decimal("0"), ()))
    assert raised.value.status_code == 422
    assert repository.calls == []


def test_write_statement_maps_stale_to_409() -> None:
    repository = _RecordingRepository(raises=StaleSpeakerAvailabilityError("lost the race"))
    with pytest.raises(ApiError) as raised:
        _write(repository, _VALID)
    assert raised.value.status_code == 409
    assert raised.value.code == "speaker_availability_stale"
