"""The signed-in Speaker's own channel consent (B26 T6b-3 plan §5.3, §6, §7).

The work behind ``routers/me_contact_channels.py``. The routes charge the quota
and call T6b-2's ``_authorize_speaker_self``; everything after that is here, in
one transaction per request, and the route commits.

## Lock order (plan §7)

``speaker_profile`` (``FOR SHARE``) → ``contact_channel`` (``FOR UPDATE``, its own
statement) → ``suppression_record`` (``FOR UPDATE``) → inserts. Every other
writer takes a subsequence of it, so no wait cycle exists.

## ``now``

Read once, after the channel and suppression locks are held:
``max(utc_now(), suppressed_at)`` when a row exists. That keeps ``lifted_at >=
suppressed_at`` (``ck_suppression_record_lifted``) true even when an unsubscribe
re-opened the row while this request waited, or another process's clock runs
ahead (S2).

## What a Speaker may lift (owner rulings, OQ-3)

Their own ``speaker_portal`` opt-out on any of their channels; an
``unsubscribe_link`` or ``one_click`` suppression only on the address they sign
in with (the one the invitation proved). Never a bounce, complaint or
coordinator suppression. ``smartmatch_domain.suppression.speaker_lift_verdict``
decides; ``SuppressionRepository.lift`` touches only the sources it allowed.

## What the Speaker sees

No consent evidence or source, no actor id, no unit id, no ``origin_send_id``
(parent plan §2).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Final, Literal

from fastapi import status
from pydantic import BaseModel, Field
from smartmatch_domain.consent import (
    ConsentSource,
    ConsentViolationError,
    ContactState,
    assert_transition,
    is_send_eligible,
)
from smartmatch_domain.speaker_channel_consent import (
    OPT_IN_START_STATES,
    SELF_SERVICE_EVIDENCE,
    SELF_SERVICE_REASON,
    SpeakerChoice,
    opt_in_path,
)
from smartmatch_domain.suppression import (
    LiftOutcome,
    MergeAction,
    SpeakerFacingReason,
    SuppressionSource,
    SuppressionState,
    merge_suppression,
    speaker_facing_reason,
    speaker_lift_verdict,
)
from smartmatch_persistence.contacts import ContactChannelRepository, ContactChannelRow
from smartmatch_persistence.speaker_channel_choice import (
    SpeakerChoiceRepository,
    SpeakerChoiceRow,
)
from smartmatch_persistence.speaker_portal import BoundSpeakerProfile, SpeakerPortalRepository
from smartmatch_persistence.suppression import SuppressionRepository
from sqlalchemy.orm import Session

from smartmatch_api.errors import ApiError
from smartmatch_api.utils import utc_now

__all__ = [
    "MAX_CHANNELS",
    "MyContactChannel",
    "MyContactChannelList",
    "MyContactChannelResult",
    "list_channels",
    "opt_in",
    "opt_out",
    "read_channel",
]

#: A Speaker holds a handful of addresses; the cap keeps the read bounded.
MAX_CHANNELS: Final[int] = 50

_contacts: Final[ContactChannelRepository] = ContactChannelRepository()
_suppressions: Final[SuppressionRepository] = SuppressionRepository()
_choices: Final[SpeakerChoiceRepository] = SpeakerChoiceRepository()
_portal: Final[SpeakerPortalRepository] = SpeakerPortalRepository()


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class MyContactChannel(BaseModel):
    """One of the Speaker's own channels. Never evidence, source, actor or unit."""

    contact_channel_id: uuid.UUID
    channel_kind: str
    address: str
    contact_state: str
    send_eligible: bool
    suppressed: bool
    suppression_reason: SpeakerFacingReason | None = Field(
        description=(
            "Why messages to this address are stopped: 'your_opt_out', "
            "'unsubscribed', 'connector' or 'delivery'; null when they are not."
        )
    )
    speaker_choice: Literal["opt_in", "opt_out"] | None
    last_set_by: Literal["speaker", "connector"]
    can_opt_in: bool
    can_opt_out: bool
    updated_at: datetime


class MyContactChannelList(BaseModel):
    channels: list[MyContactChannel]
    #: More than :data:`MAX_CHANNELS` exist; the page is not the whole list.
    truncated: bool


class MyContactChannelResult(BaseModel):
    channel: MyContactChannel
    #: ``false`` when nothing needed to change; nothing was written.
    changed: bool


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


def _not_linked() -> ApiError:
    return ApiError(
        status_code=status.HTTP_404_NOT_FOUND,
        code="speaker_profile_not_linked",
        message="No Speaker profile is linked to this account.",
    )


def _not_found() -> ApiError:
    return ApiError(
        status_code=status.HTTP_404_NOT_FOUND,
        code="speaker_contact_channel_not_found",
        message="No such contact channel.",
    )


_NOT_LIFTABLE_MESSAGES: Final[dict[str, str]] = {
    "connector": (
        "Your Speaker Connector stopped messages to this address. Ask them if you want it back."
    ),
    "delivery": (
        "Messages to this address bounced or were reported, so they stay stopped. Ask your "
        "Speaker Connector."
    ),
}


# ---------------------------------------------------------------------------
# Reads
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class _ChannelFacts:
    row: ContactChannelRow
    suppression: SuppressionState | None
    choice: SpeakerChoiceRow | None
    last_transition_at: datetime | None


def _same_address(a: str, b: str | None) -> bool:
    return b is not None and a.strip().lower() == b.strip().lower()


def _view(facts: _ChannelFacts, *, login_address: str | None) -> MyContactChannel:
    row = facts.row
    state = ContactState(row.contact_state)
    source = ConsentSource(row.consent_source) if row.consent_source is not None else None
    latest = None if facts.choice is None else facts.choice.choice
    verdict = speaker_lift_verdict(
        facts.suppression, address_is_login=_same_address(row.address, login_address)
    )
    path = opt_in_path(state)
    nothing_to_do = path == () and not row.suppressed and latest is SpeakerChoice.OPT_IN
    speaker_last = facts.choice is not None and (
        facts.last_transition_at is None or facts.choice.decided_at >= facts.last_transition_at
    )
    return MyContactChannel(
        contact_channel_id=row.id,
        channel_kind=row.channel_kind,
        address=row.address,
        contact_state=row.contact_state,
        send_eligible=is_send_eligible(state, consent_source=source, suppressed=row.suppressed),
        suppressed=row.suppressed,
        suppression_reason=speaker_facing_reason(facts.suppression) if row.suppressed else None,
        speaker_choice=None if latest is None else latest.value,
        last_set_by="speaker" if speaker_last else "connector",
        can_opt_in=(
            verdict.outcome is not LiftOutcome.REFUSED
            and state in OPT_IN_START_STATES
            and not nothing_to_do
        ),
        can_opt_out=not (latest is SpeakerChoice.OPT_OUT and row.suppressed),
        updated_at=row.updated_at,
    )


def _facts(
    session: Session, *, tenant_id: uuid.UUID, rows: list[ContactChannelRow]
) -> list[_ChannelFacts]:
    """The suppression rows, latest choices and last Connector moves, batched."""
    ids = [row.id for row in rows]
    suppressions = _suppressions.states_for_addresses(
        session, tenant_id=tenant_id, addresses=[row.address for row in rows]
    )
    choices = _choices.latest_for_channels(session, tenant_id=tenant_id, contact_channel_ids=ids)
    moved = _choices.last_transition_at_for_channels(
        session, tenant_id=tenant_id, contact_channel_ids=ids
    )
    return [
        _ChannelFacts(
            row=row,
            suppression=suppressions.get(row.address),
            choice=choices.get(row.id),
            last_transition_at=moved.get(row.id),
        )
        for row in rows
    ]


def list_channels(
    session: Session,
    *,
    tenant_id: uuid.UUID,
    professional_id: uuid.UUID,
    account_user_id: uuid.UUID,
) -> MyContactChannelList:
    """Every channel of this professional in the tenant, across units (OQ-7)."""
    rows = _contacts.list_for_speaker(
        session, tenant_id=tenant_id, professional_id=professional_id, limit=MAX_CHANNELS + 1
    )
    login = _portal.login_address(session, tenant_id=tenant_id, account_user_id=account_user_id)
    facts = _facts(session, tenant_id=tenant_id, rows=rows[:MAX_CHANNELS])
    return MyContactChannelList(
        channels=[_view(f, login_address=login) for f in facts],
        truncated=len(rows) > MAX_CHANNELS,
    )


def read_channel(
    session: Session,
    *,
    tenant_id: uuid.UUID,
    professional_id: uuid.UUID,
    account_user_id: uuid.UUID,
    contact_channel_id: uuid.UUID,
) -> MyContactChannel:
    """One own channel, read back after a write."""
    row = _contacts.get(session, tenant_id=tenant_id, contact_channel_id=contact_channel_id)
    if row is None or row.professional_id != professional_id:
        raise _not_found()
    login = _portal.login_address(session, tenant_id=tenant_id, account_user_id=account_user_id)
    [facts] = _facts(session, tenant_id=tenant_id, rows=[row])
    return _view(facts, login_address=login)


# ---------------------------------------------------------------------------
# Writes
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class _Locked:
    row: ContactChannelRow
    suppression: SuppressionState | None
    now: datetime


def _locked_channel(
    session: Session,
    *,
    tenant_id: uuid.UUID,
    bound: BoundSpeakerProfile,
    actor_user_id: uuid.UUID,
    contact_channel_id: uuid.UUID,
) -> _Locked:
    """Take the §7 locks in order and read everything the write decides on.

    1. The profile ``FOR SHARE``, re-checking the binding the authorizer read
       (an unbind that committed in between is ``404 speaker_profile_not_linked``).
    2. The channel ``FOR UPDATE``, then a re-read; not this professional's is 404.
    3. The address's suppression row ``FOR UPDATE`` (may be none).
    4. ``now``, after both locks (S2).
    """
    if not _portal.lock_bound_profile_share(
        session,
        tenant_id=tenant_id,
        professional_id=bound.professional_id,
        account_user_id=actor_user_id,
    ):
        raise _not_linked()
    _contacts.lock(session, tenant_id=tenant_id, contact_channel_id=contact_channel_id)
    row = _contacts.get(session, tenant_id=tenant_id, contact_channel_id=contact_channel_id)
    if row is None or row.professional_id != bound.professional_id:
        raise _not_found()
    suppression = _suppressions.lock_for_address(session, tenant_id=tenant_id, address=row.address)
    now = utc_now()
    if suppression is not None and suppression.suppressed_at > now:
        now = suppression.suppressed_at
    return _Locked(row=row, suppression=suppression, now=now)


def opt_in(
    session: Session,
    *,
    tenant_id: uuid.UUID,
    bound: BoundSpeakerProfile,
    actor_user_id: uuid.UUID,
    contact_channel_id: uuid.UUID,
) -> bool:
    """The Speaker opts in on one of their channels. Does not commit.

    Returns:
        Whether anything was written (``False``: already opted in and sendable).

    Raises:
        ApiError: 404 ``speaker_profile_not_linked`` / ``speaker_contact_channel_not_found``;
            409 ``speaker_contact_channel_address_unverified``,
            ``speaker_contact_channel_suppression_not_liftable`` (``details.reason``),
            ``speaker_contact_channel_opt_in_unavailable`` (``details.contact_state``),
            ``speaker_contact_channel_transition_conflict``.
    """
    locked = _locked_channel(
        session,
        tenant_id=tenant_id,
        bound=bound,
        actor_user_id=actor_user_id,
        contact_channel_id=contact_channel_id,
    )
    row, now = locked.row, locked.now
    login = _portal.login_address(session, tenant_id=tenant_id, account_user_id=actor_user_id)

    # Suppression before legality, the order `assert_transition` uses.
    verdict = speaker_lift_verdict(
        locked.suppression, address_is_login=_same_address(row.address, login)
    )
    if verdict.outcome is LiftOutcome.REFUSED:
        if verdict.reason == "unverified_address":
            raise ApiError(
                status_code=status.HTTP_409_CONFLICT,
                code="speaker_contact_channel_address_unverified",
                message=(
                    "This address was unsubscribed and is not the one you sign in with. "
                    "Ask your Speaker Connector."
                ),
            )
        reason = verdict.reason or "delivery"
        raise ApiError(
            status_code=status.HTTP_409_CONFLICT,
            code="speaker_contact_channel_suppression_not_liftable",
            message=_NOT_LIFTABLE_MESSAGES[reason],
            details={"reason": reason},
        )

    current = ContactState(row.contact_state)
    path = opt_in_path(current)
    if path is None:
        raise ApiError(
            status_code=status.HTTP_409_CONFLICT,
            code="speaker_contact_channel_opt_in_unavailable",
            message=(
                "This address is not ready for you to opt in yet. Ask your Speaker Connector."
            ),
            details={"contact_state": current.value},
        )

    latest = _choices.latest_for_channel(
        session, tenant_id=tenant_id, contact_channel_id=contact_channel_id
    )
    if (
        not path
        and verdict.outcome is LiftOutcome.NOTHING_TO_LIFT
        and latest is not None
        and latest.choice is SpeakerChoice.OPT_IN
    ):
        return False

    lifted = locked.suppression if verdict.outcome is LiftOutcome.LIFT else None
    if lifted is not None:
        _suppressions.lift(
            session,
            tenant_id=tenant_id,
            address=row.address,
            allowed_sources=verdict.allowed_sources,
            lifted_at=now,
            lifted_by_user_id=actor_user_id,
        )

    for previous, following in path:
        try:
            assert_transition(
                previous,
                following,
                consent_source=ConsentSource.SELF_SERVICE,
                suppressed=False,
            )
        except ConsentViolationError as exc:  # pragma: no cover - the path is legal
            raise _transition_conflict() from exc
        moved = _contacts.apply_transition(
            session,
            tenant_id=tenant_id,
            contact_channel_id=contact_channel_id,
            expected_state=previous.value,
            to_state=following.value,
            consent_source=ConsentSource.SELF_SERVICE.value,
            consent_evidence=SELF_SERVICE_EVIDENCE,
            reason=SELF_SERVICE_REASON,
            actor_user_id=actor_user_id,
            occurred_at=now,
        )
        if moved is None:  # pragma: no cover - unreachable under the channel lock
            raise _transition_conflict()

    _choices.append(
        session,
        tenant_id=tenant_id,
        contact_channel_id=contact_channel_id,
        choice=SpeakerChoice.OPT_IN,
        decided_at=now,
        actor_user_id=actor_user_id,
        lifted_source=None if lifted is None else lifted.source.value,
        lifted_suppressed_at=None if lifted is None else lifted.suppressed_at,
    )
    return True


def _transition_conflict() -> ApiError:
    return ApiError(
        status_code=status.HTTP_409_CONFLICT,
        code="speaker_contact_channel_transition_conflict",
        message="This address changed while you were opting in. Read it again.",
    )


def opt_out(
    session: Session,
    *,
    tenant_id: uuid.UUID,
    bound: BoundSpeakerProfile,
    actor_user_id: uuid.UUID,
    contact_channel_id: uuid.UUID,
) -> bool:
    """The Speaker opts out on one of their channels: immediate and prospective.

    Writes a ``speaker_portal`` suppression (merged by rank, so a bounce stays a
    bounce) and a choice row. The lifecycle is not touched, so a later opt-in
    restores sending without research moves. Does not commit.

    Returns:
        Whether anything was written (``False``: already opted out and suppressed).
    """
    locked = _locked_channel(
        session,
        tenant_id=tenant_id,
        bound=bound,
        actor_user_id=actor_user_id,
        contact_channel_id=contact_channel_id,
    )
    latest = _choices.latest_for_channel(
        session, tenant_id=tenant_id, contact_channel_id=contact_channel_id
    )
    merge = merge_suppression(
        locked.suppression, SuppressionSource.SPEAKER_PORTAL, at=locked.now, origin_send_id=None
    )
    if (
        merge.action is MergeAction.NOOP
        and latest is not None
        and latest.choice is SpeakerChoice.OPT_OUT
    ):
        return False
    _suppressions.record(
        session,
        tenant_id=tenant_id,
        address=locked.row.address,
        source=SuppressionSource.SPEAKER_PORTAL,
        at=locked.now,
    )
    _choices.append(
        session,
        tenant_id=tenant_id,
        contact_channel_id=contact_channel_id,
        choice=SpeakerChoice.OPT_OUT,
        decided_at=locked.now,
        actor_user_id=actor_user_id,
    )
    return True
