"""The stored Stage A availability verdict (B26 T4).

A match run records, per evaluated Speaker, the availability verdict it was
taken with; the read compares it with today's verdict ("changed since this
run"); compose and dispatch re-check it against the batch's Speaker Request.
This module is the pure half of all three:

* :class:`StoredVerdict` — one subject's verdict, state, reason, the UTC date it
  was taken on, and the pause date when the reason is ``paused``.
* :func:`verdicts_for_pool` — T1's :func:`availability_state_for_event` per
  subject, then the unchanged Stage A gate
  (:func:`~smartmatch_domain.eligibility.apply_availability_filter`) over the
  pool, in pool order. The verdict **annotates**: it removes no one, reorders
  nothing and is never a Stage B input (weight 0, ``factor_registry``).
* :func:`to_payload` / :func:`from_payload` — the ``job.payload["availability"]``
  shape, read back strictly (the ``explanation_from_payload`` discipline): an
  unreadable entry raises ``ValueError`` and is never repaired.
* :func:`changed_since`, :func:`as_of_utc`, :func:`event_time_from_columns`,
  :func:`filed_this_request` (Q8).

Pure domain: no I/O, no clock. Plan ``docs/plans/b26-tracks/T4-plan.md`` §2-§5.
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any, Final

from smartmatch_domain.eligibility import (
    AvailabilityReason,
    AvailabilityState,
    EligibilityOutcome,
    apply_availability_filter,
)
from smartmatch_domain.events import (
    DateOnlyTime,
    EventTime,
    ExactTime,
    TimePrecision,
    UnresolvedTime,
)
from smartmatch_domain.speaker_availability import (
    AvailabilityStatement,
    EventDateSpan,
    availability_state_for_event,
)

__all__ = [
    "PAYLOAD_FIELDS",
    "StoredVerdict",
    "as_of_utc",
    "changed_since",
    "event_time_from_columns",
    "filed_this_request",
    "from_payload",
    "to_payload",
    "verdicts_for_pool",
]

#: The keys of one ``availability`` payload entry, all required.
PAYLOAD_FIELDS: Final[tuple[str, ...]] = (
    "subject_id",
    "verdict",
    "state",
    "reason",
    "as_of",
    "paused_until",
)

#: The Stage A outcome each state produces (``apply_availability_filter``).
_VERDICT_BY_STATE: Final[Mapping[AvailabilityState, EligibilityOutcome]] = {
    AvailabilityState.AVAILABLE: EligibilityOutcome.ELIGIBLE,
    AvailabilityState.BLACKED_OUT: EligibilityOutcome.EXCLUDED,
    AvailabilityState.UNKNOWN: EligibilityOutcome.UNDETERMINED,
}

#: The reasons each state may carry. Unlike ``AvailabilityEvidence``, a stored
#: verdict always names its reason.
_REASONS_BY_STATE: Final[Mapping[AvailabilityState, frozenset[AvailabilityReason]]] = {
    AvailabilityState.AVAILABLE: frozenset({AvailabilityReason.CLEAR}),
    AvailabilityState.BLACKED_OUT: frozenset(
        {AvailabilityReason.PAUSED, AvailabilityReason.WINDOW}
    ),
    AvailabilityState.UNKNOWN: frozenset(
        {AvailabilityReason.NOT_STATED, AvailabilityReason.EVENT_UNRESOLVED}
    ),
}


@dataclass(frozen=True, slots=True)
class StoredVerdict:
    """One subject's Stage A availability verdict, as a run or a batch records it.

    Attributes:
        subject_id: The Speaker (a ``professional_id``, as text). Non-blank.
        verdict: The Stage A outcome; must be the one ``state`` produces.
        state: T1's availability state.
        reason: Why ``state`` was reached; must belong to ``state``.
        as_of: The UTC date the verdict was taken on (C7).
        paused_until: The stored pause date, set exactly when ``reason`` is
            ``paused`` (C6).
    """

    subject_id: str
    verdict: EligibilityOutcome
    state: AvailabilityState
    reason: AvailabilityReason
    as_of: date
    paused_until: date | None

    def __post_init__(self) -> None:
        if not isinstance(self.subject_id, str) or not self.subject_id.strip():
            raise ValueError("subject_id: must not be empty or blank")
        if _VERDICT_BY_STATE[self.state] is not self.verdict:
            raise ValueError(
                f"verdict: {self.verdict.value!r} does not follow from state {self.state.value!r}"
            )
        if self.reason not in _REASONS_BY_STATE[self.state]:
            raise ValueError(
                f"reason: {self.reason.value!r} does not belong to state {self.state.value!r}"
            )
        for name, value in (("as_of", self.as_of), ("paused_until", self.paused_until)):
            if value is not None and (isinstance(value, datetime) or not isinstance(value, date)):
                raise ValueError(f"{name}: must be a date")
        if (self.reason is AvailabilityReason.PAUSED) != (self.paused_until is not None):
            raise ValueError("paused_until: must be set exactly when the reason is 'paused'")


def verdicts_for_pool(
    subject_ids: Sequence[str],
    statements: Mapping[str, AvailabilityStatement],
    event_span: EventDateSpan | None,
    as_of: date,
) -> tuple[StoredVerdict, ...]:
    """One verdict per subject, in ``subject_ids`` order.

    A subject absent from ``statements`` has stated nothing (``not_stated``).
    Statements for subjects outside the pool are ignored.

    Raises:
        ValueError: on a duplicate subject, or a malformed ``event_span``.
    """
    pool = tuple(subject_ids)
    assessments = {
        subject: availability_state_for_event(statements.get(subject), event_span, as_of)
        for subject in pool
    }
    decisions = apply_availability_filter(
        pool,
        {subject: assessment.to_evidence(subject) for subject, assessment in assessments.items()},
    )
    verdicts: list[StoredVerdict] = []
    for decision in decisions:
        assessment = assessments[decision.subject_id]
        statement = statements.get(decision.subject_id)
        paused_until = (
            statement.invitations_paused_until
            if statement is not None and assessment.reason is AvailabilityReason.PAUSED
            else None
        )
        verdicts.append(
            StoredVerdict(
                subject_id=decision.subject_id,
                verdict=decision.outcome,
                state=assessment.state,
                reason=assessment.reason,
                as_of=as_of,
                paused_until=paused_until,
            )
        )
    return tuple(verdicts)


def to_payload(verdicts: Sequence[StoredVerdict]) -> list[dict[str, str | None]]:
    """The ``job.payload["availability"]`` list: one JSON object per verdict."""
    return [
        {
            "subject_id": verdict.subject_id,
            "verdict": verdict.verdict.value,
            "state": verdict.state.value,
            "reason": verdict.reason.value,
            "as_of": verdict.as_of.isoformat(),
            "paused_until": (
                None if verdict.paused_until is None else verdict.paused_until.isoformat()
            ),
        }
        for verdict in verdicts
    ]


def _text(entry: Mapping[str, Any], field: str, index: int) -> str:
    if field not in entry:
        raise ValueError(f"availability[{index}].{field}: missing")
    value = entry[field]
    if not isinstance(value, str):
        raise ValueError(f"availability[{index}].{field}: must be a string")
    return value


def _date(value: str, field: str, index: int) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"availability[{index}].{field}: not an ISO date: {value!r}") from exc


def _member(enum: type[Any], value: str, field: str, index: int) -> Any:
    try:
        return enum(value)
    except ValueError as exc:
        raise ValueError(f"availability[{index}].{field}: unrecognised {value!r}") from exc


def _entry(entry: object, index: int) -> StoredVerdict:
    if not isinstance(entry, Mapping):
        raise ValueError(f"availability[{index}]: must be an object")
    if "paused_until" not in entry:
        raise ValueError(f"availability[{index}].paused_until: missing")
    raw_paused = entry["paused_until"]
    if raw_paused is not None and not isinstance(raw_paused, str):
        raise ValueError(f"availability[{index}].paused_until: must be a string or null")
    try:
        return StoredVerdict(
            subject_id=_text(entry, "subject_id", index),
            verdict=_member(EligibilityOutcome, _text(entry, "verdict", index), "verdict", index),
            state=_member(AvailabilityState, _text(entry, "state", index), "state", index),
            reason=_member(AvailabilityReason, _text(entry, "reason", index), "reason", index),
            as_of=_date(_text(entry, "as_of", index), "as_of", index),
            paused_until=(None if raw_paused is None else _date(raw_paused, "paused_until", index)),
        )
    except ValueError as exc:
        message = str(exc)
        if message.startswith("availability["):
            raise
        raise ValueError(f"availability[{index}]: {message}") from exc


def from_payload(payload: object) -> tuple[StoredVerdict, ...]:
    """Read ``job.payload["availability"]`` back, strictly.

    Raises:
        ValueError: naming the entry and field that could not be read, or the
            invariant it breaks. The caller reports the run's availability as
            unreadable; this function never repairs a row.
    """
    if not isinstance(payload, list):
        raise ValueError("availability: must be a list")
    verdicts = tuple(_entry(entry, index) for index, entry in enumerate(payload))
    seen: set[str] = set()
    for verdict in verdicts:
        if verdict.subject_id in seen:
            raise ValueError(f"availability: duplicate subject_id {verdict.subject_id!r}")
        seen.add(verdict.subject_id)
    return verdicts


def changed_since(stored: StoredVerdict, current: StoredVerdict) -> bool:
    """Whether today's verdict differs from the stored one.

    Compares ``(verdict, reason, paused_until)``: a moved pause date is a change,
    a later ``as_of`` alone is not.
    """
    return (stored.verdict, stored.reason, stored.paused_until) != (
        current.verdict,
        current.reason,
        current.paused_until,
    )


def as_of_utc(now: datetime) -> date:
    """The UTC date of ``now`` (C7). ``now`` must be timezone-aware.

    Raises:
        ValueError: for a naive datetime.
    """
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("now: must be timezone-aware")
    return now.astimezone(UTC).date()


def event_time_from_columns(
    *,
    time_precision: str,
    starts_at: datetime | None,
    ends_at: datetime | None,
    on_date: date | None,
    time_zone: str | None,
) -> EventTime:
    """Rebuild an ``event`` row's :data:`EventTime` from its columns.

    Raises:
        ValueError: for an unknown precision, or a column the precision needs
            that is NULL.
    """
    try:
        precision = TimePrecision(time_precision)
    except ValueError as exc:
        raise ValueError(f"time_precision: unrecognised {time_precision!r}") from exc
    if precision is TimePrecision.UNRESOLVED:
        return UnresolvedTime()
    if time_zone is None:
        raise ValueError("time_zone: required for a resolved event")
    if precision is TimePrecision.EXACT:
        if starts_at is None:
            raise ValueError("starts_at: required for an exact event")
        return ExactTime(starts_at=starts_at, time_zone=time_zone, ends_at=ends_at)
    if on_date is None:
        raise ValueError("on_date: required for a date_only event")
    return DateOnlyTime(on_date=on_date, time_zone=time_zone)


def filed_this_request(
    filed_by_user_id: uuid.UUID | None, account_user_id: uuid.UUID | None
) -> bool:
    """Q8: the Speaker's bound login filed this Speaker Request.

    Both must be known: an unrecorded filer (pre-``0033``) or a Speaker with no
    bound login excludes nobody, and NULL never equals NULL.
    """
    if filed_by_user_id is None or account_user_id is None:
        return False
    return filed_by_user_id == account_user_id
