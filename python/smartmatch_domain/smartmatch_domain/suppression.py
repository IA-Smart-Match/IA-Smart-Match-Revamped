"""Suppression sources, their rank, and the Speaker's lift rule (B26 T6b-3).

``suppression_record`` keeps **one row per address** (``uq_suppression_record_address``).
A row is *active* while ``lifted_at IS NULL``; an active row blocks every send to
the address. This module decides, without IO, what one row should hold after a
new suppression arrives (:func:`merge_suppression`) and whether the signed-in
Speaker may lift it (:func:`speaker_lift_verdict`).

## Rank

| Source | Rank | Speaker may lift |
|---|---|---|
| ``bounce``, ``complaint`` | 3 | never |
| ``coordinator`` | 2 | never |
| ``unsubscribe_link``, ``one_click`` | 1 | only on the Speaker's login address |
| ``speaker_portal`` | 0 | yes, on any of the Speaker's channels |

The row holds the highest-ranked source still standing. For either kind of
address the sources the Speaker may lift are exactly those at or below a rank
threshold, and a merge only moves the rank up, so the row's source is
non-liftable exactly when some non-liftable fact stands. A lift is therefore
all-or-nothing and one row loses no lift decision.
``tests/unit/test_suppression_rules.py`` proves it against a per-source model.

``speaker_portal`` ranks **below** the unsubscribe sources on purpose: with the
opposite order, a Speaker opt-out on top of an unsubscribe made at another
address would hide that unsubscribe, and a later opt-in would lift it.
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from types import MappingProxyType
from typing import Final, Literal

__all__ = [
    "LIFTABLE_BY_SPEAKER",
    "LOGIN_ADDRESS_ONLY",
    "NEVER_LIFTED",
    "SOURCE_RANK",
    "LiftOutcome",
    "LiftVerdict",
    "MergeAction",
    "SpeakerFacingReason",
    "SuppressionSource",
    "SuppressionState",
    "SuppressionWrite",
    "address_is_login",
    "liftable_sources",
    "merge_suppression",
    "speaker_facing_reason",
    "speaker_lift_verdict",
]


class SuppressionSource(StrEnum):
    """Who or what said stop. The six values of ``ck_suppression_record_source``."""

    UNSUBSCRIBE_LINK = "unsubscribe_link"
    ONE_CLICK = "one_click"
    COORDINATOR = "coordinator"
    BOUNCE = "bounce"
    COMPLAINT = "complaint"
    SPEAKER_PORTAL = "speaker_portal"


SOURCE_RANK: Final[Mapping[SuppressionSource, int]] = MappingProxyType(
    {
        SuppressionSource.SPEAKER_PORTAL: 0,
        SuppressionSource.UNSUBSCRIBE_LINK: 1,
        SuppressionSource.ONE_CLICK: 1,
        SuppressionSource.COORDINATOR: 2,
        SuppressionSource.BOUNCE: 3,
        SuppressionSource.COMPLAINT: 3,
    }
)

#: The widest set a Speaker lift may ever touch; ``ck_suppression_record_lift_source``.
LIFTABLE_BY_SPEAKER: Final[frozenset[SuppressionSource]] = frozenset(
    {
        SuppressionSource.SPEAKER_PORTAL,
        SuppressionSource.UNSUBSCRIBE_LINK,
        SuppressionSource.ONE_CLICK,
    }
)

#: Liftable by the Speaker only on the address the invitation proved (OQ-3).
LOGIN_ADDRESS_ONLY: Final[frozenset[SuppressionSource]] = frozenset(
    {SuppressionSource.UNSUBSCRIBE_LINK, SuppressionSource.ONE_CLICK}
)

#: Delivery facts and a Connector's decision: never lifted by either side.
NEVER_LIFTED: Final[frozenset[SuppressionSource]] = frozenset(
    {SuppressionSource.BOUNCE, SuppressionSource.COMPLAINT, SuppressionSource.COORDINATOR}
)

SpeakerFacingReason = Literal["your_opt_out", "unsubscribed", "connector", "delivery"]

_SPEAKER_FACING: Final[Mapping[SuppressionSource, SpeakerFacingReason]] = MappingProxyType(
    {
        SuppressionSource.SPEAKER_PORTAL: "your_opt_out",
        SuppressionSource.UNSUBSCRIBE_LINK: "unsubscribed",
        SuppressionSource.ONE_CLICK: "unsubscribed",
        SuppressionSource.COORDINATOR: "connector",
        SuppressionSource.BOUNCE: "delivery",
        SuppressionSource.COMPLAINT: "delivery",
    }
)


@dataclass(frozen=True, slots=True)
class SuppressionState:
    """The one ``suppression_record`` row for an address, as the rules need it."""

    source: SuppressionSource
    suppressed_at: datetime
    lifted_at: datetime | None
    origin_send_id: uuid.UUID | None

    @property
    def active(self) -> bool:
        """Whether the row blocks sending (``lifted_at IS NULL``)."""
        return self.lifted_at is None


class MergeAction(StrEnum):
    """What the one row becomes when a new suppression arrives."""

    INSERT = "insert"
    REOPEN = "reopen"
    ESCALATE = "escalate"
    NOOP = "noop"


@dataclass(frozen=True, slots=True)
class SuppressionWrite:
    """The row's values after the merge. ``NOOP`` repeats the existing values."""

    action: MergeAction
    source: SuppressionSource
    suppressed_at: datetime
    origin_send_id: uuid.UUID | None


def merge_suppression(
    existing: SuppressionState | None,
    incoming_source: SuppressionSource,
    *,
    at: datetime,
    origin_send_id: uuid.UUID | None,
) -> SuppressionWrite:
    """Merge a new suppression into the address's one row.

    * No row → ``INSERT``.
    * A lifted row → ``REOPEN`` with the incoming values; the lift is cleared.
    * An active row and a higher-ranked source → ``ESCALATE``: the source and
      ``origin_send_id`` change, ``suppressed_at`` is kept ("when did they
      first ask us to stop").
    * An active row and an equal or lower rank → ``NOOP``.
    """
    if existing is None:
        return SuppressionWrite(MergeAction.INSERT, incoming_source, at, origin_send_id)
    if not existing.active:
        return SuppressionWrite(MergeAction.REOPEN, incoming_source, at, origin_send_id)
    if SOURCE_RANK[incoming_source] > SOURCE_RANK[existing.source]:
        return SuppressionWrite(
            MergeAction.ESCALATE, incoming_source, existing.suppressed_at, origin_send_id
        )
    return SuppressionWrite(
        MergeAction.NOOP, existing.source, existing.suppressed_at, existing.origin_send_id
    )


def address_is_login(address: str, login_email: str | None) -> bool:
    """Whether ``address`` is the Speaker's login address: trimmed, ASCII case fold.

    ASCII only: Python's Unicode ``lower()`` maps look-alikes (U+212A KELVIN
    SIGN to ``k``), which would let a different mailbox count as the one the
    invitation proved.
    """
    if login_email is None:
        return False
    a, b = address.strip(), login_email.strip()
    return a.isascii() and b.isascii() and a.lower() == b.lower()


def liftable_sources(*, address_is_login: bool) -> frozenset[SuppressionSource]:
    """The sources a Speaker may lift on this address (OQ-3 ruling)."""
    if address_is_login:
        return LIFTABLE_BY_SPEAKER
    return frozenset({SuppressionSource.SPEAKER_PORTAL})


class LiftOutcome(StrEnum):
    """The answer to "may the Speaker lift this address's suppression"."""

    LIFT = "lift"
    NOTHING_TO_LIFT = "nothing_to_lift"
    REFUSED = "refused"


LiftRefusal = Literal["unverified_address", "connector", "delivery"]


@dataclass(frozen=True, slots=True)
class LiftVerdict:
    """The verdict, and for ``LIFT`` the sources the ``UPDATE`` may touch (S6)."""

    outcome: LiftOutcome
    reason: LiftRefusal | None
    allowed_sources: frozenset[SuppressionSource]


_NOTHING: Final[LiftVerdict] = LiftVerdict(LiftOutcome.NOTHING_TO_LIFT, None, frozenset())


def speaker_lift_verdict(
    existing: SuppressionState | None, *, address_is_login: bool
) -> LiftVerdict:
    """Whether the signed-in Speaker's opt-in may lift the address's suppression.

    ``address_is_login`` is true only for the address the Speaker signs in with,
    the one the invitation proved. An unsubscribe made at any other address may
    have come from whoever holds it now.
    """
    if existing is None or not existing.active:
        return _NOTHING
    allowed = liftable_sources(address_is_login=address_is_login)
    if existing.source in allowed:
        return LiftVerdict(LiftOutcome.LIFT, None, allowed)
    if existing.source in LOGIN_ADDRESS_ONLY:
        return LiftVerdict(LiftOutcome.REFUSED, "unverified_address", frozenset())
    if existing.source is SuppressionSource.COORDINATOR:
        return LiftVerdict(LiftOutcome.REFUSED, "connector", frozenset())
    return LiftVerdict(LiftOutcome.REFUSED, "delivery", frozenset())


def speaker_facing_reason(existing: SuppressionState | None) -> SpeakerFacingReason | None:
    """Why the address is suppressed, in words the Speaker may see; ``None`` when not."""
    if existing is None or not existing.active:
        return None
    return _SPEAKER_FACING[existing.source]
