"""Monetary spend reservation: pure state machine and receipt types.

ADR-0015 Amendment A1. Counting quota (``rate_limit.py``) and monetary spend are
not the same control — a counter is this system's own bookkeeping and a dollar
paid to a provider is an external, irreversible side effect. A1's rule is:
**reserve the maximum estimated cost atomically before the paid call, then
reconcile the reservation to the actual cost after it.** This module is the
pure half of that rule — the state machine, the receipt the paid-provider
boundary requires, and the transition functions a persistence layer calls under
a real database guard. It imports no ``sqlalchemy``, no ``os``/``pathlib``/
``socket``, and makes no network call; every function here is a deterministic
computation over plain values.

## The four states

``reserved`` is the only non-terminal state. ``reconciled``, ``expired_spent``,
and ``released`` are terminal — no transition leaves them, mirroring
``smartmatch_domain.jobs.TRANSITIONS`` for ``failed_budget``: a state that can
be re-entered is a state whose accounting can be repeated.

## ``released`` has exactly one legal entry path

The live worker holding the reservation may release it, before outbound
dispatch, when its own code path refuses the work for a reason of its own. A
sweeper, a timeout handler, a retry, or a later inference may never release —
ADR-0015 A1, *"The sweep never releases. Any expired reservation is
`expired_spent`, without exception."* This is enforced by construction, not by
convention:

* :func:`release_before_dispatch` is the **only** function in this module that
  can return a :class:`ReleasedOutcome`, and it requires a
  :class:`SpendReservationReceipt` — the value only a successful reservation
  (persistence layer) ever hands out, to the caller that made the reservation,
  in-process.
* :func:`expire_abandoned` (the sweeper's path) takes an
  :class:`AbandonedReservationSnapshot`, a type that has no ``lease_token``
  field at all. There is no legal way, using this module's public API, to
  construct a :class:`SpendReservationReceipt` from what the sweeper reads back
  out of the database — the sweeper's query result type simply does not carry
  the value :func:`release_before_dispatch` requires. That is the enforcement:
  a receipt is minted once, at reservation time, and nothing downstream of a
  sweep or a lease-expiry read can reconstruct one.
* :func:`expire_on_timeout` (the in-worker-timeout path) *does* take a receipt
  — the worker still holds it — but its return type is :class:`ExpiredOutcome`,
  never :class:`ReleasedOutcome`. Holding a valid receipt is necessary to reach
  this function at all; it is not sufficient to reach ``released`` through it.

## Timeouts have no actual cost

ADR-0015 A1: *"an in-worker timeout reconciles to the reserved maximum, held as
spent, and explicitly flagged as estimated rather than actual."* A timeout is
neither a success (which reports a real cost) nor a clean failure (which costs
nothing) — the provider may have completed and billed before the client gave
up waiting. :func:`expire_on_timeout` therefore never returns a
:class:`ReconciledOutcome` (which means an *actual* cost is recorded) and never
records zero, which would be the fail-open answer.

## What this module does not do

It never touches a database, never computes whether a ceiling admits an
estimate (that guard is the guarded SQL write in
``smartmatch_persistence.spend``, per A1's *"a first reservation... for an
estimate larger than the ceiling, is refused"*), and never calls a provider.
:func:`dispatch` is a synthetic seam so the type-level refusal has something to
assert against; it never reaches a network.
"""

from __future__ import annotations

import hashlib
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from types import MappingProxyType
from typing import Final, TypeVar

__all__ = [
    "BUCKET_LOCK_ORDER",
    "TERMINAL_STATES",
    "TRANSITIONS",
    "AbandonedReservationSnapshot",
    "AlreadyReconciledOutcome",
    "BucketType",
    "ExpiredOutcome",
    "InvalidSpendTransitionError",
    "ReconciledOutcome",
    "RefusalReason",
    "Refused",
    "ReleasedOutcome",
    "ReservationSnapshot",
    "ReviewFinding",
    "ReviewFindingCategory",
    "SpendReservationReceipt",
    "SpendReservationState",
    "assert_transition",
    "can_transition",
    "derive_work_key",
    "dispatch",
    "is_terminal",
    "job_bucket_key",
    "tenant_day_bucket_key",
    "tenant_month_bucket_key",
]


class SpendReservationState(StrEnum):
    """Every state a spend reservation row may occupy (ADR-0015 A1)."""

    RESERVED = "reserved"
    RECONCILED = "reconciled"
    EXPIRED_SPENT = "expired_spent"
    RELEASED = "released"


#: Legal transitions. Only ``reserved`` has any — the other three are terminal
#: by construction, the same shape ``smartmatch_domain.jobs.TRANSITIONS`` uses
#: for ``failed_budget``.
TRANSITIONS: Final[MappingProxyType[SpendReservationState, frozenset[SpendReservationState]]] = (
    MappingProxyType(
        {
            SpendReservationState.RESERVED: frozenset(
                {
                    SpendReservationState.RECONCILED,
                    SpendReservationState.EXPIRED_SPENT,
                    SpendReservationState.RELEASED,
                }
            ),
            SpendReservationState.RECONCILED: frozenset(),
            SpendReservationState.EXPIRED_SPENT: frozenset(),
            SpendReservationState.RELEASED: frozenset(),
        }
    )
)

#: States from which no further transition is legal.
TERMINAL_STATES: Final[frozenset[SpendReservationState]] = frozenset(
    state for state, allowed in TRANSITIONS.items() if not allowed
)


class InvalidSpendTransitionError(ValueError):
    """Raised only by :func:`assert_transition`, for a bare state-machine check.

    The higher-level operations below (:func:`reconcile`, :func:`expire_abandoned`,
    :func:`expire_on_timeout`, :func:`release_before_dispatch`) do not raise
    this — they return a typed :class:`Refused` with a stable
    :class:`RefusalReason` instead, because a refusal there is an expected
    outcome (a late worker losing a race, a redelivery finding a terminal row),
    not a programming error.
    """

    def __init__(self, current: SpendReservationState, requested: SpendReservationState) -> None:
        allowed = sorted(s.value for s in TRANSITIONS[current])
        super().__init__(
            f"cannot move spend reservation from {current.value!r} to "
            f"{requested.value!r}; legal transitions are {allowed or ['(terminal)']}"
        )
        self.current = current
        self.requested = requested


def can_transition(current: SpendReservationState, requested: SpendReservationState) -> bool:
    """Return whether ``current -> requested`` is legal."""
    return requested in TRANSITIONS[current]


def assert_transition(current: SpendReservationState, requested: SpendReservationState) -> None:
    """Raise unless ``current -> requested`` is legal.

    Raises:
        InvalidSpendTransitionError: if the transition is not in
            :data:`TRANSITIONS`.
    """
    if not can_transition(current, requested):
        raise InvalidSpendTransitionError(current, requested)


def is_terminal(state: SpendReservationState) -> bool:
    """Return whether ``state`` admits no further transitions."""
    return state in TERMINAL_STATES


class BucketType(StrEnum):
    """The three ceilings A1's obligation 1 debits atomically."""

    JOB = "job"
    TENANT_DAY = "tenant_day"
    TENANT_MONTH = "tenant_month"


#: The fixed lock order A1's *Three ceilings, one debit* requires when the
#: sequential-writes option is chosen: "two workers can take the three rows in
#: different orders [and] it deadlocks unless a fixed row-lock ordering is
#: imposed and documented." The persistence layer iterates this tuple, in this
#: order, on every reservation — never a caller-chosen or key-dependent order —
#: so no two concurrent reservations can ever lock the three ceilings in
#: opposite sequences.
BUCKET_LOCK_ORDER: Final[tuple[BucketType, ...]] = (
    BucketType.JOB,
    BucketType.TENANT_DAY,
    BucketType.TENANT_MONTH,
)


class RefusalReason(StrEnum):
    """Stable reasons a spend operation may be refused.

    Some are produced only by the persistence layer's guarded SQL (the ceiling
    ones — this module never computes a ceiling comparison) and are named here
    anyway so both layers report the same vocabulary to a caller or an
    operator reading a log.
    """

    #: Persistence: the guarded write — first-insert or ``DO UPDATE`` — matched
    #: no row because the estimate would exceed the ceiling.
    CEILING_EXCEEDED = "ceiling_exceeded"
    #: This module: the reservation is already ``reconciled``, ``expired_spent``,
    #: or ``released``, and the requested operation only applies to ``reserved``.
    ALREADY_TERMINAL = "already_terminal"
    #: This module: :func:`expire_abandoned` was called with a lease that has
    #: not actually expired yet.
    NOT_EXPIRED = "not_expired"
    #: This module: the receipt presented does not name the reservation or does
    #: not carry its lease token.
    RECEIPT_MISMATCH = "receipt_mismatch"
    #: Either layer: a redelivery presented a work key whose reservation is
    #: ``expired_spent``. ADR-0015 A1: "the retry does not call... it requires
    #: a new reservation taken under the ceiling as it now stands."
    EXPIRED_NO_RETRY = "expired_no_retry"
    #: Persistence: no reservation row exists for the id presented.
    UNKNOWN_RESERVATION = "unknown_reservation"
    #: Persistence: the guarded ``INSERT`` into ``spend_reservation`` lost a
    #: race on ``uq_spend_reservation_work_key`` — two concurrent
    #: re-reservations after the same ``released`` row computed the same next
    #: attempt number (``smartmatch_persistence.spend``'s ``released``
    #: re-reservation scheme) and only one could commit. See that module's
    #: docstring for the full mechanism; this is expected to be rare, and the
    #: loser is free to call ``reserve`` again.
    WORK_KEY_COLLISION = "work_key_collision"
    #: This module: :func:`release_before_dispatch` was called on a reservation
    #: whose lease has already expired. A1: "an expired, unreconciled
    #: reservation is unconditionally treated as spent at its reserved
    #: maximum... and not released." Once the lease is up, the only remaining
    #: transition is ``expired_spent``, whoever is asking.
    LEASE_EXPIRED = "lease_expired"
    #: This module: a negative actual cost was presented to :func:`reconcile`.
    #: A refund is not a negative call cost, and the database refuses the value
    #: too (``ck_spend_reservation_actual_non_negative``); the domain refuses
    #: first so the caller gets a reason rather than an IntegrityError.
    NEGATIVE_ACTUAL_COST = "negative_actual_cost"


@dataclass(frozen=True, slots=True)
class Refused:
    """A typed, fail-closed refusal. Never a bare exception where this fits."""

    reason: RefusalReason
    detail: str


@dataclass(frozen=True, slots=True)
class SpendReservationReceipt:
    """The value the paid-provider boundary requires before dispatch.

    Minted exactly once, by a successful reservation (a fresh reserve, a
    duplicate-delivery reuse of a live ``reserved`` row, or a renewed
    ``released -> reserved`` row), and handed to the in-process caller that
    made the call. Nothing else in this codebase constructs one from a bare
    database read — see the module docstring's *released has exactly one legal
    entry path* section for why that absence is load-bearing.
    """

    reservation_id: uuid.UUID
    tenant_id: uuid.UUID
    work_key: str
    lease_token: uuid.UUID
    estimate: Decimal


@dataclass(frozen=True, slots=True)
class ReservationSnapshot:
    """A reservation row's state, as read by the worker that holds it.

    Carries ``lease_token`` because the worker-driven operations
    (:func:`expire_on_timeout`, :func:`release_before_dispatch`) verify the
    presented receipt against it. Contrast :class:`AbandonedReservationSnapshot`.
    """

    id: uuid.UUID
    tenant_id: uuid.UUID
    work_key: str
    state: SpendReservationState
    estimate: Decimal
    actual_cost: Decimal | None
    lease_token: uuid.UUID | None
    lease_expires_at: datetime


@dataclass(frozen=True, slots=True)
class AbandonedReservationSnapshot:
    """What a sweep reads back. Deliberately carries no ``lease_token``.

    The absence is the enforcement described in the module docstring: without a
    token in this type, nothing built from a sweep's read can satisfy
    :func:`release_before_dispatch`'s signature.
    """

    id: uuid.UUID
    tenant_id: uuid.UUID
    work_key: str
    state: SpendReservationState
    estimate: Decimal
    lease_expires_at: datetime


class ReviewFindingCategory(StrEnum):
    """Why a spend reservation is being escalated for human review."""

    #: Actual cost exceeded the reserved maximum (ADR-0015 A1: "record the
    #: overage... never silently truncate it").
    OVERAGE = "overage"
    #: A reservation's lease expired unreconciled and was conservatively
    #: reclaimed as spent (T-08).
    ABANDONED_EXPIRY = "abandoned_expiry"


@dataclass(frozen=True, slots=True)
class ReviewFinding:
    """A deduplicated escalation. Never emitted twice for the same reservation.

    Persistence enforces the "never twice" half with a guarded write on the
    reservation's own ``review_flagged_at`` column — see
    ``smartmatch_persistence.spend`` — so this dataclass carries no identity of
    its own beyond the reservation it is about.
    """

    reservation_id: uuid.UUID
    tenant_id: uuid.UUID
    work_key: str
    category: ReviewFindingCategory
    detail: str


@dataclass(frozen=True, slots=True)
class ReconciledOutcome:
    """A fresh reconciliation: an actual cost is now recorded.

    Attributes:
        overage: The amount actual exceeded estimate by, or ``None`` when the
            call cost at or under its reservation. Never negative — a call that
            cost less releases the difference (persistence's concern), it does
            not appear here as a negative overage.
        review_finding: Present exactly when ``overage`` is present. A1
            requires the overage be visible, never absorbed.
    """

    actual_cost: Decimal
    overage: Decimal | None
    review_finding: ReviewFinding | None


@dataclass(frozen=True, slots=True)
class AlreadyReconciledOutcome:
    """Idempotent no-op: this reservation was reconciled by an earlier call.

    ADR-0015 A1: a redelivery against a ``reconciled`` reservation "is a no-op
    returning the recorded outcome, exactly as `dispatcher.py`'s deterministic
    task name makes a duplicate dispatch a no-op rather than a second dispatch."
    Distinguished from :class:`ReconciledOutcome` so a caller can tell "I just
    settled this" from "this was already settled" without inspecting a flag.
    """

    actual_cost: Decimal | None


@dataclass(frozen=True, slots=True)
class ExpiredOutcome:
    """Reached by :func:`expire_abandoned` or :func:`expire_on_timeout` only.

    ``spent_amount`` is always the reservation's original estimate — the
    reserved maximum — per A1's conservative-reclaim rule: "unconditionally
    treated as spent at its reserved maximum." ``is_estimated`` is always
    ``True``: this outcome never represents a confirmed actual.
    """

    spent_amount: Decimal
    is_estimated: bool
    review_finding: ReviewFinding | None


@dataclass(frozen=True, slots=True)
class ReleasedOutcome:
    """Reached by :func:`release_before_dispatch` only. See the module docstring."""

    reason: str


def derive_work_key(
    *, tenant_id: uuid.UUID, job_id: uuid.UUID, provider: str, unit_of_work: str
) -> str:
    """Return the deterministic key one unit of provider work reserves under.

    ADR-0015 A1: "the reservation therefore needs a deterministic key for the
    unit of work it is reserving for... so that re-reserving the same unit is
    recognised rather than added." A hash rather than the raw components
    concatenated, mirroring ``smartmatch_persistence.outbox.derive_task_name``,
    so a re-drive or a retry that presents the identical inputs always derives
    the identical key and a changed input (a different provider, a different
    unit) always derives a different one.

    Args:
        unit_of_work: Whatever identifies *this* piece of work within the job —
            a page URL, a row index, a fetch attempt — the granularity a single
            paid call is reserved for. The caller decides the granularity; this
            function only makes it deterministic.
    """
    # Length-prefixed, not delimiter-joined. A bare "a|b|c|d" join is
    # ambiguous whenever a component may itself contain the delimiter:
    # provider="a|b", unit_of_work="c" and provider="a", unit_of_work="b|c"
    # produce the same string and therefore the same key, which would let two
    # genuinely different paid calls share one reservation. Prefixing each
    # component with its own byte length makes the encoding injective, so
    # distinct inputs always derive distinct keys.
    parts = (str(tenant_id), str(job_id), provider, unit_of_work)
    encoded = b"".join(f"{len(raw := part.encode())}:".encode() + raw for part in parts)
    digest = hashlib.sha256(encoded).hexdigest()[:40]
    return f"spend-{digest}"


def job_bucket_key(job_id: uuid.UUID) -> str:
    """Return the per-job ceiling bucket key (L21's ``$2.00 per job``)."""
    return f"job:{job_id}"


def tenant_day_bucket_key(tenant_id: uuid.UUID, day: date) -> str:
    """Return the per-tenant-per-day ceiling bucket key (G3 §4's ``$25/day``)."""
    return f"tenant-day:{tenant_id}:{day.isoformat()}"


def tenant_month_bucket_key(tenant_id: uuid.UUID, year: int, month: int) -> str:
    """Return the per-tenant-per-month ceiling bucket key (G3 §4's ``$250/month``)."""
    return f"tenant-month:{tenant_id}:{year:04d}-{month:02d}"


def reconcile(
    snapshot: ReservationSnapshot, *, actual_cost: Decimal, now: datetime
) -> ReconciledOutcome | AlreadyReconciledOutcome | Refused:
    """Settle a reservation to its actual cost. Pure; no database write.

    Idempotent: a reservation already ``reconciled`` returns
    :class:`AlreadyReconciledOutcome` rather than re-computing anything, so a
    sweep and a late worker reaching the same row twice cannot double-record.
    Refuses (:data:`RefusalReason.ALREADY_TERMINAL`) against ``expired_spent``
    and ``released`` — the late-worker/sweeper race A1 names explicitly: a
    reconcile that reaches a row the sweep already expired must not reopen or
    double-charge it.

    ``now`` is accepted for signature symmetry with the other operations and
    to let a caller thread a single "as of" instant through a whole settle
    pass; this function does not currently branch on it.
    """
    del now  # symmetry with the other operations; not yet load-bearing here
    if actual_cost < 0:
        return Refused(
            RefusalReason.NEGATIVE_ACTUAL_COST,
            f"actual cost {actual_cost} is negative; a paid call costs zero or more, "
            "and a credit is not a negative call cost",
        )
    if snapshot.state is SpendReservationState.RECONCILED:
        return AlreadyReconciledOutcome(actual_cost=snapshot.actual_cost)
    if snapshot.state is not SpendReservationState.RESERVED:
        return Refused(
            RefusalReason.ALREADY_TERMINAL,
            f"reservation {snapshot.id} is {snapshot.state.value!r}; only a "
            "'reserved' row may be reconciled",
        )

    overage = actual_cost - snapshot.estimate if actual_cost > snapshot.estimate else None
    finding = (
        ReviewFinding(
            reservation_id=snapshot.id,
            tenant_id=snapshot.tenant_id,
            work_key=snapshot.work_key,
            category=ReviewFindingCategory.OVERAGE,
            detail=(
                f"actual cost {actual_cost} exceeded the reserved maximum "
                f"{snapshot.estimate} by {overage}"
            ),
        )
        if overage is not None
        else None
    )
    return ReconciledOutcome(actual_cost=actual_cost, overage=overage, review_finding=finding)


def expire_abandoned(
    snapshot: AbandonedReservationSnapshot, *, now: datetime
) -> ExpiredOutcome | Refused:
    """Conservatively reclaim one abandoned reservation. The sweeper's path.

    Legal only from ``reserved`` with an expired lease. A1: "an expired,
    unreconciled reservation is unconditionally treated as spent at its
    reserved maximum... and not released." This function can never return
    :class:`ReleasedOutcome` — see the module docstring.
    """
    if snapshot.state is not SpendReservationState.RESERVED:
        return Refused(
            RefusalReason.ALREADY_TERMINAL,
            f"reservation {snapshot.id} is {snapshot.state.value!r}; nothing to reclaim",
        )
    if snapshot.lease_expires_at >= now:
        return Refused(
            RefusalReason.NOT_EXPIRED,
            f"reservation {snapshot.id}'s lease does not expire until "
            f"{snapshot.lease_expires_at.isoformat()}",
        )
    return ExpiredOutcome(
        spent_amount=snapshot.estimate,
        is_estimated=True,
        review_finding=ReviewFinding(
            reservation_id=snapshot.id,
            tenant_id=snapshot.tenant_id,
            work_key=snapshot.work_key,
            category=ReviewFindingCategory.ABANDONED_EXPIRY,
            detail=(
                f"lease expired at {snapshot.lease_expires_at.isoformat()} unreconciled; "
                f"reclaimed as spent at the reserved maximum {snapshot.estimate}"
            ),
        ),
    )


def expire_on_timeout(
    snapshot: ReservationSnapshot, receipt: SpendReservationReceipt, *, now: datetime
) -> ExpiredOutcome | Refused:
    """Reconcile an in-worker timeout to the reserved maximum, marked estimated.

    A1: *"the required behavior: an in-worker timeout reconciles to the
    reserved maximum, held as spent, and explicitly flagged as estimated rather
    than actual."* Never returns :class:`ReconciledOutcome` — a timeout has no
    actual cost to record — and never returns :class:`ReleasedOutcome`, even
    though this function (unlike :func:`expire_abandoned`) does take a receipt:
    holding a valid receipt reaches this function, it does not reach
    ``released`` through it. See the module docstring.

    Distinguished from :func:`expire_abandoned` by who calls it and why: this
    is the live worker declaring its own call timed out, not a sweep
    discovering an expired lease later. Both reach ``expired_spent`` because
    A1 requires the identical conservative figure and flag from either path.

    State is checked **before** the receipt, deliberately: a terminal row has
    ``lease_token`` cleared (see the migration and
    ``smartmatch_persistence.spend``), so any receipt would mismatch a
    terminal snapshot's ``None`` token. Checking state first reports the
    caller's real situation — "already settled" — instead of the misleading
    "your receipt is wrong".
    """
    if snapshot.state is not SpendReservationState.RESERVED:
        return Refused(
            RefusalReason.ALREADY_TERMINAL,
            f"reservation {snapshot.id} is {snapshot.state.value!r}; nothing to time out",
        )
    if receipt.reservation_id != snapshot.id or receipt.lease_token != snapshot.lease_token:
        return Refused(
            RefusalReason.RECEIPT_MISMATCH,
            f"receipt for {receipt.reservation_id} does not match reservation {snapshot.id}",
        )
    return ExpiredOutcome(
        spent_amount=snapshot.estimate,
        is_estimated=True,
        review_finding=ReviewFinding(
            reservation_id=snapshot.id,
            tenant_id=snapshot.tenant_id,
            work_key=snapshot.work_key,
            category=ReviewFindingCategory.ABANDONED_EXPIRY,
            detail=(
                f"in-worker timeout at {now.isoformat()}; reconciled to the reserved "
                f"maximum {snapshot.estimate}, flagged estimated rather than actual"
            ),
        ),
    )


def release_before_dispatch(
    snapshot: ReservationSnapshot,
    receipt: SpendReservationReceipt,
    *,
    reason: str,
    now: datetime,
) -> ReleasedOutcome | Refused:
    """Release a reservation in full. The **only** function that can.

    Legal only from ``reserved``, only while the lease is still in force, and
    only when ``receipt`` names this exact reservation and carries its current
    lease token — the proof that the
    caller is the live worker that took the reservation, not an inference
    drawn later from the row's appearance (A1 withdraws exactly that
    inference for the sweep). Must be called before the reserving worker's own
    outbound dispatch; nothing in this module can check that no call has been
    made yet — see the module docstring's *released has exactly one legal
    entry path* section for what does provide that guarantee.
    """
    if snapshot.state is not SpendReservationState.RESERVED:
        return Refused(
            RefusalReason.ALREADY_TERMINAL,
            f"reservation {snapshot.id} is {snapshot.state.value!r}; only a "
            "'reserved' row may be released",
        )
    # A row whose lease has run out is the sweeper's, not the worker's, even in
    # the window before a sweep actually reaches it: A1 admits no exception to
    # "an expired, unreconciled reservation is... not released." Without this
    # check a worker that stalled past its own lease could still hand the
    # reservation back, crediting a ceiling for a call that may well have been
    # paid for.
    if snapshot.lease_expires_at <= now:
        return Refused(
            RefusalReason.LEASE_EXPIRED,
            f"reservation {snapshot.id}'s lease expired at "
            f"{snapshot.lease_expires_at.isoformat()}; an expired reservation is "
            "reclaimed as spent, never released",
        )
    if receipt.reservation_id != snapshot.id or receipt.lease_token != snapshot.lease_token:
        return Refused(
            RefusalReason.RECEIPT_MISMATCH,
            f"receipt for {receipt.reservation_id} does not match reservation {snapshot.id}",
        )
    return ReleasedOutcome(reason=reason)


_T = TypeVar("_T")


def dispatch(
    receipt: SpendReservationReceipt, invoke_provider: Callable[[SpendReservationReceipt], _T]
) -> _T:
    """Synthetic outbound-dispatch seam. Makes no network call.

    Exists so *"a paid call cannot be made by a path that never reserved, and a
    type checker says so at the call site"* (A1, echoing ``QuotaCharge`` at
    ``dependencies.py:187``) has something concrete to assert against in this
    repository's synthetic-provider boundary. ``receipt`` has no default and is
    typed as :class:`SpendReservationReceipt`, not ``SpendReservationReceipt |
    None`` and not ``Any`` — a call site with no reservation cannot satisfy this
    signature, and mypy strict refuses the program before it runs.

    The ``isinstance`` guard below is the runtime half of the same refusal:
    Python does not enforce annotations at call time, so a caller that reaches
    this function through an untyped path (``# type: ignore``, a dict standing
    in for the dataclass, a bare ``None``) is refused here instead of silently
    treated as authorized.

    Args:
        invoke_provider: The caller's synthetic stand-in for the paid call.
            This module never supplies one and never calls a real provider —
            see the module docstring's *What this module does not do*.

    Raises:
        TypeError: if ``receipt`` is not a :class:`SpendReservationReceipt`.
    """
    if not isinstance(receipt, SpendReservationReceipt):
        raise TypeError(
            "dispatch() requires a SpendReservationReceipt from a successful "
            f"reservation; got {type(receipt).__name__}. There is no default "
            "and no Any-typed fallback: a call site that never reserved cannot "
            "reach a paid call through this seam."
        )
    return invoke_provider(receipt)
