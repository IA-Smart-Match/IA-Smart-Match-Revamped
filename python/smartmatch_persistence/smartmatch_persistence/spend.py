"""Monetary spend reservation persistence (ADR-0015 Amendment A1).

``smartmatch_domain.spend`` is the pure state machine; this module is the
guarded database half A1 requires: *"reserve the maximum estimated cost
atomically before the paid call, then reconcile the reservation to the actual
cost after it."* :class:`SpendReservationService` implements the first half —
the reservation. Reconciliation, timeout, release, the sweep, and review
escalation are separate, later work items; this module does not touch any of
them.

## Three ceilings, one debit, one guarded write each

A1's obligation 1 debits the ``job``, ``tenant_day``, and ``tenant_month``
ceilings **atomically, all-or-nothing**, inside one transaction, in the fixed
order ``smartmatch_domain.spend.BUCKET_LOCK_ORDER`` — never a caller-chosen
order — so two concurrent reservations taking the same three rows can never
deadlock by locking them in opposite sequences.

Each of the three writes is a *single* guarded statement, never a separate
read followed by a write: *"A reservation that is not a single conditional
write is not a reservation."* ADR-0006's shape — a guarded
``ON CONFLICT ... DO UPDATE`` — covers the case where a bucket row already
exists, but copying it verbatim reintroduces exactly the defect A1 calls out:
ADR-0006 only guards the ``DO UPDATE``, so a *first* reservation against a key
with no row yet — for an estimate already larger than the ceiling — sails
through unguarded. :func:`SpendReservationService._debit_bucket` closes that
gap by guarding the insert's own source row too: the row is built by a
``SELECT ... WHERE :estimate <= :ceiling`` rather than a bare ``VALUES``
clause, so when the estimate alone already exceeds the ceiling, the ``SELECT``
produces no candidate row, there is nothing for ``ON CONFLICT`` to act on, and
the statement's ``RETURNING`` clause returns nothing — which *is* the refusal,
not a separate check. If any of the three bucket writes returns no row, the
whole transaction is rolled back before any of the others can be observed as
committed, and :meth:`SpendReservationService.reserve` returns
:class:`~smartmatch_domain.spend.Refused` with
:attr:`~smartmatch_domain.spend.RefusalReason.CEILING_EXCEEDED`, naming which
bucket refused.

## Redelivery, by the existing row's state

Before any bucket is touched, :meth:`SpendReservationService.reserve` looks up
the reservation this exact ``(tenant, job, provider, unit_of_work)`` would
derive, via :func:`~smartmatch_domain.spend.derive_work_key`, and applies A1's
per-state redelivery rule:

* ``reserved`` — a live reservation already covers this unit of work. A
  receipt is minted straight from the existing row's ``lease_token``; nothing
  is debited a second time.
* ``reconciled`` — refused
  (:attr:`~smartmatch_domain.spend.RefusalReason.ALREADY_TERMINAL`), a no-op.
  The call already happened and was paid for; redelivering it must not reserve
  again.
* ``expired_spent`` — refused
  (:attr:`~smartmatch_domain.spend.RefusalReason.EXPIRED_NO_RETRY`). A1: *"the
  retry does not call... it requires a new reservation taken under the
  ceiling as it now stands"* — but that new reservation is not this call; the
  caller must derive a genuinely new unit of work (a new ``unit_of_work``,
  which changes the work key) to try again.
* ``released`` — terminal, but treated as *never charged*: A1's caller
  released it before any outbound dispatch, of its own accord, for a reason
  that has nothing to do with the ceilings. This case re-reserves normally —
  see the next section for how, since ``released`` being terminal is exactly
  what makes it not simply reusable.

## The ``released`` re-reservation scheme, and its failure mode

``work_key`` carries ``uq_spend_reservation_work_key``, a *global* unique
constraint, and :func:`~smartmatch_domain.spend.derive_work_key` is
deterministic — the same four inputs always derive the same key. Once a row
occupies that key and lands in ``released`` (terminal: nothing may leave it,
per ``smartmatch_domain.spend.TRANSITIONS``), a later re-reservation for the
identical unit of work cannot reuse that row, and cannot reuse its key either
— the constraint would refuse a second row at the same key even though the
first is terminal. No migration in this work item adds a retry-attempt
counter column, so the persistence layer manufactures the numbering itself,
entirely from what is already on the row:

The base key is ``derive_work_key(...)``'s output, unchanged. A reservation's
**attempt number** is 1 for a row whose stored ``work_key`` equals the base
key exactly, and ``n`` for a row stored as ``f"{base}#{n}"``
(:func:`family_attempt_number`). A re-reservation after ``released`` is given
the *next* attempt's key: ``f"{base}#{n}"`` where ``n`` is one more than the
number of existing rows whose stored ``work_key`` is the base key or starts
with ``f"{base}#"`` (:func:`next_family_work_key`) — so the very first
release-then-retry becomes ``base#2`` (the original, unsuffixed row already
occupies attempt 1), the next becomes ``base#3``, and so on. The redelivery
lookup above therefore does not look up the base key alone: it fetches every
row in the family (base key or ``base#...``) and applies the per-state rule to
whichever one has the *highest* attempt number — the most recent attempt is
the one that speaks for this unit of work now.

**Failure mode.** The attempt number is computed by reading the family, then
writing a new row with the computed key — not itself a single guarded
statement, unlike the bucket debits, because there is no ``ON CONFLICT`` target
that could express "the next available attempt number" atomically. Two workers
concurrently re-reserving the *same* released unit of work (a genuine
double-release, or two redeliveries racing each other) can therefore both read
the same family, both compute the same ``n``, and both attempt to insert
``f"{base}#{n}"``. ``uq_spend_reservation_work_key`` lets exactly one of those
inserts through; the loser's ``INSERT`` raises an ``IntegrityError`` at
execute time (PostgreSQL checks a plain ``UNIQUE`` constraint immediately, not
at commit). :meth:`SpendReservationService.reserve` catches exactly that
constraint's violation, rolls back the loser's transaction — crediting back
whatever it had just debited from the three buckets, so the loser leaves no
partial trace — and returns :class:`~smartmatch_domain.spend.Refused` with
:attr:`~smartmatch_domain.spend.RefusalReason.WORK_KEY_COLLISION` rather than
letting the raw ``IntegrityError`` escape. This is deliberately *not* retried
internally: the race is expected to be rare, and the loser calling
``reserve`` again re-reads the family (now including the winner's row) and
computes a fresh, uncontested ``n``. Any other ``IntegrityError`` — a
genuinely broken caller, such as a ``tenant_id`` with no ``tenant`` row — is
re-raised rather than folded into this refusal, so a real bug is not
mistaken for a benign, self-resolving race.

## Money

``estimate`` and the ceiling columns are ``NUMERIC(12,4)``. Every value this
module writes or compares is a :class:`~decimal.Decimal`; none is ever coerced
through :class:`float`, which cannot represent a currency amount exactly.

## What this module does not do

It never records or reports an estimate as an actual cost — that distinction
belongs to reconciliation, not reservation, and this module writes no
``actual_cost`` at all. It never releases a reservation itself, and it never
sweeps or expires one; A1's *"the sweep never releases, without exception"*
is a rule this module cannot violate simply by never implementing a release or
sweep path.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import sqlalchemy as sa
from smartmatch_domain.spend import (
    BUCKET_LOCK_ORDER,
    BucketType,
    RefusalReason,
    Refused,
    SpendReservationReceipt,
    SpendReservationState,
    derive_work_key,
    job_bucket_key,
    tenant_day_bucket_key,
    tenant_month_bucket_key,
)
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from smartmatch_persistence import schema

__all__ = [
    "ReservationRequest",
    "SpendCeilings",
    "SpendReservationService",
    "family_attempt_number",
    "next_family_work_key",
]

#: The unique constraint the `released` re-reservation race can violate. See
#: the module docstring's *failure mode* section.
_WORK_KEY_UNIQUE_CONSTRAINT = "uq_spend_reservation_work_key"

#: The named primary key the bucket debit's ON CONFLICT targets — mirrors how
#: rate_limit.py names pk_rate_limit_counter.
_BUCKET_PRIMARY_KEY = "pk_spend_ceiling_bucket"


@dataclass(frozen=True, slots=True)
class SpendCeilings:
    """The three ceilings one reservation is checked against (ADR-0015 A1).

    Attributes:
        job: Per-job ceiling (L21's example, ``$2.00`` per job).
        tenant_day: Per-tenant-per-day ceiling (G3 §4, ``$25``/day).
        tenant_month: Per-tenant-per-month ceiling (G3 §4, ``$250``/month).
    """

    job: Decimal
    tenant_day: Decimal
    tenant_month: Decimal

    def __post_init__(self) -> None:
        for name, value in (
            ("job", self.job),
            ("tenant_day", self.tenant_day),
            ("tenant_month", self.tenant_month),
        ):
            if value < 0:
                raise ValueError(f"{name} ceiling must be non-negative, got {value}")


@dataclass(frozen=True, slots=True)
class ReservationRequest:
    """One caller's request to reserve estimated spend for a unit of work.

    Attributes:
        tenant_id: The tenant the spend is charged against.
        job_id: The job the per-job ceiling is scoped to.
        provider: Which paid provider the call will go to.
        unit_of_work: Whatever identifies this piece of work within the job —
            see :func:`~smartmatch_domain.spend.derive_work_key`. The caller
            decides the granularity.
        estimate: The maximum this unit of work may cost, reserved up front.
            Never negative.
        now: The instant the reservation is taken, injected rather than read
            from the clock so tests are deterministic — the same discipline
            as ``RateLimiter.check``'s ``now``. Must be timezone-aware; the
            day and month bucket keys are derived from it in UTC.
        lease: How long the reservation is held before a sweep may reclaim it
            as ``expired_spent``. Must be positive.
    """

    tenant_id: uuid.UUID
    job_id: uuid.UUID
    provider: str
    unit_of_work: str
    estimate: Decimal
    now: datetime
    lease: timedelta

    def __post_init__(self) -> None:
        if self.estimate < 0:
            raise ValueError(f"estimate must be non-negative, got {self.estimate}")
        if self.now.tzinfo is None:
            raise ValueError("now must be timezone-aware")
        if self.lease <= timedelta(0):
            raise ValueError("lease must be positive")


def family_attempt_number(base_key: str, work_key: str) -> int:
    """Return ``work_key``'s attempt number within the ``base_key`` family.

    The unsuffixed base key itself is attempt 1; ``f"{base_key}#{n}"`` is
    attempt ``n``. See the module docstring's *released re-reservation scheme*
    for why the numbering starts this way.

    Raises:
        ValueError: if ``work_key`` is neither the base key nor a
            ``base_key#<int>`` suffix of it — it does not belong to this
            family at all, which means a caller mismatched its inputs.
    """
    if work_key == base_key:
        return 1
    prefix = f"{base_key}#"
    if not work_key.startswith(prefix):
        raise ValueError(f"{work_key!r} does not belong to the {base_key!r} family")
    suffix = work_key[len(prefix) :]
    try:
        return int(suffix)
    except ValueError as exc:
        raise ValueError(f"{work_key!r} has a non-numeric attempt suffix") from exc


def next_family_work_key(base_key: str, existing_work_keys: Iterable[str]) -> str:
    """Return the ``work_key`` a re-reservation after ``released`` should use.

    Counts every key in ``existing_work_keys`` that belongs to the
    ``base_key`` family (the base key itself, or a ``base_key#<int>`` suffix
    of it — anything else is ignored, so this is safe to call with an
    unfiltered set of keys) and returns the next attempt's key. The result is
    unique against every *previously observed* key in the family, but not
    against a concurrent caller computing the same count at the same time —
    see the module docstring's *failure mode* section, which
    :class:`SpendReservationService` handles at the point of insertion.
    """
    prefix = f"{base_key}#"
    family_size = sum(1 for key in existing_work_keys if key == base_key or key.startswith(prefix))
    return f"{base_key}#{family_size + 1}"


def _is_work_key_collision(exc: IntegrityError) -> bool:
    """Return whether ``exc`` is the ``released`` re-reservation race.

    Checked narrowly, not by treating every ``IntegrityError`` as this race: a
    caller error (an unknown ``tenant_id``, say) must still surface as itself
    rather than being silently reinterpreted as a benign, self-resolving
    collision. Prefers the driver's structured constraint name (``psycopg``'s
    ``exc.orig.diag.constraint_name``) and falls back to matching the
    constraint name in the rendered error text for a driver that does not
    expose it structurally.
    """
    diag = getattr(exc.orig, "diag", None)
    constraint_name = getattr(diag, "constraint_name", None)
    if constraint_name is not None:
        return bool(constraint_name == _WORK_KEY_UNIQUE_CONSTRAINT)
    return _WORK_KEY_UNIQUE_CONSTRAINT in str(exc.orig)


class SpendReservationService:
    """Reserves monetary spend against the three ADR-0015 A1 ceilings.

    Takes its :class:`~sqlalchemy.orm.Session` at construction, unlike
    :class:`~smartmatch_persistence.rate_limit.RateLimiter`, which takes one
    per call. A reservation is not meant to share a caller's transaction the
    way a counter increment or an outbox enqueue does — Global Constraint 4
    requires it to "commit in its own transaction, before any paid call" — so
    there is no reason for the session to vary between the calls one instance
    makes.
    """

    def __init__(self, session: Session) -> None:
        self._session = session

    def reserve(
        self, request: ReservationRequest, ceilings: SpendCeilings
    ) -> SpendReservationReceipt | Refused:
        """Reserve ``request.estimate`` against the three ceilings, or refuse.

        See the module docstring for the full redelivery rule, the bucket
        debit's guard shape, and the ``released`` re-reservation scheme this
        method implements.

        Commits on success. On any refusal after a bucket has been debited,
        rolls back so the whole transaction — all three buckets — leaves no
        trace. A refusal reached before any bucket is touched (the redelivery
        checks) neither commits nor rolls back, since nothing was written.
        """
        now = request.now
        now_utc = now.astimezone(UTC)
        base_key = derive_work_key(
            tenant_id=request.tenant_id,
            job_id=request.job_id,
            provider=request.provider,
            unit_of_work=request.unit_of_work,
        )
        job_key = job_bucket_key(request.job_id)
        # Day and month roll over on UTC's clock, not whatever offset `now`
        # happened to be expressed in — two callers passing the same instant
        # in different offsets must land in the same bucket.
        tenant_day_key = tenant_day_bucket_key(request.tenant_id, now_utc.date())
        tenant_month_key = tenant_month_bucket_key(request.tenant_id, now_utc.year, now_utc.month)

        family = self._session.execute(
            sa.select(
                schema.spend_reservation.c.id,
                schema.spend_reservation.c.tenant_id,
                schema.spend_reservation.c.work_key,
                schema.spend_reservation.c.state,
                schema.spend_reservation.c.estimate,
                schema.spend_reservation.c.lease_token,
            ).where(
                sa.or_(
                    schema.spend_reservation.c.work_key == base_key,
                    schema.spend_reservation.c.work_key.like(f"{base_key}#%"),
                )
            )
        ).all()

        work_key = base_key
        if family:
            latest = max(family, key=lambda row: family_attempt_number(base_key, row.work_key))
            redelivery = self._apply_redelivery_rule(latest)
            if redelivery is not None:
                return redelivery
            # `released`: fall through and re-reserve under the next attempt's
            # key. `_apply_redelivery_rule` returns None only for `released`.
            work_key = next_family_work_key(base_key, (row.work_key for row in family))

        bucket_ceilings = {
            BucketType.JOB: (job_key, ceilings.job),
            BucketType.TENANT_DAY: (tenant_day_key, ceilings.tenant_day),
            BucketType.TENANT_MONTH: (tenant_month_key, ceilings.tenant_month),
        }
        for bucket_type in BUCKET_LOCK_ORDER:
            bucket_key, ceiling = bucket_ceilings[bucket_type]
            debited = self._debit_bucket(
                tenant_id=request.tenant_id,
                bucket_type=bucket_type,
                bucket_key=bucket_key,
                ceiling=ceiling,
                estimate=request.estimate,
            )
            if not debited:
                self._session.rollback()
                return Refused(
                    RefusalReason.CEILING_EXCEEDED,
                    f"{bucket_type.value} ceiling ({ceiling}) refused estimate "
                    f"{request.estimate} for bucket {bucket_key!r}",
                )

        reservation_id = uuid.uuid4()
        lease_token = uuid.uuid4()
        try:
            self._session.execute(
                sa.insert(schema.spend_reservation).values(
                    id=reservation_id,
                    tenant_id=request.tenant_id,
                    work_key=work_key,
                    job_bucket_key=job_key,
                    tenant_day_bucket_key=tenant_day_key,
                    tenant_month_bucket_key=tenant_month_key,
                    estimate=request.estimate,
                    state=SpendReservationState.RESERVED.value,
                    lease_token=lease_token,
                    lease_expires_at=now + request.lease,
                )
            )
        except IntegrityError as exc:
            self._session.rollback()
            if _is_work_key_collision(exc):
                return Refused(
                    RefusalReason.WORK_KEY_COLLISION,
                    f"work key {work_key!r} was claimed by a concurrent "
                    "re-reservation of the same released unit of work; see "
                    "smartmatch_persistence.spend's module docstring",
                )
            raise

        self._session.commit()
        return SpendReservationReceipt(
            reservation_id=reservation_id,
            tenant_id=request.tenant_id,
            work_key=work_key,
            lease_token=lease_token,
            estimate=request.estimate,
        )

    @staticmethod
    def _apply_redelivery_rule(
        latest: sa.Row[tuple[object, ...]],
    ) -> SpendReservationReceipt | Refused | None:
        """Apply Global Constraint 8 to the family's most recent row.

        Returns a receipt or refusal for every state except ``released``, for
        which it returns ``None`` — the caller's signal to fall through and
        re-reserve under a fresh, family-scoped key.
        """
        state = SpendReservationState(latest.state)
        if state is SpendReservationState.RESERVED:
            if latest.lease_token is None:
                # ck_spend_reservation_lease_token_iff_reserved guarantees a
                # `reserved` row always carries a token; reaching this means
                # the database's own invariant was violated, not a refusal.
                raise RuntimeError(
                    f"reservation {latest.id} is 'reserved' with no lease_token, "
                    "violating ck_spend_reservation_lease_token_iff_reserved"
                )
            return SpendReservationReceipt(
                reservation_id=latest.id,
                tenant_id=latest.tenant_id,
                work_key=latest.work_key,
                lease_token=latest.lease_token,
                estimate=latest.estimate,
            )
        if state is SpendReservationState.RECONCILED:
            return Refused(
                RefusalReason.ALREADY_TERMINAL,
                f"reservation {latest.id} for work key {latest.work_key!r} is "
                "already reconciled; a redelivery is a no-op",
            )
        if state is SpendReservationState.EXPIRED_SPENT:
            return Refused(
                RefusalReason.EXPIRED_NO_RETRY,
                f"reservation {latest.id} for work key {latest.work_key!r} expired "
                "unreconciled; a retry requires a new reservation for a new unit "
                "of work, taken under the ceiling as it now stands",
            )
        return None  # released: re-reserve normally.

    def _debit_bucket(
        self,
        *,
        tenant_id: uuid.UUID,
        bucket_type: BucketType,
        bucket_key: str,
        ceiling: Decimal,
        estimate: Decimal,
    ) -> bool:
        """Guarded single-statement debit of one ceiling bucket.

        Returns whether the debit succeeded. Failure — the guarded write
        matched no row — is not an error here; it is Global Constraint 3's
        refusal signal, and the caller turns it into a
        :class:`~smartmatch_domain.spend.Refused`.

        The insert's source row is a ``SELECT`` guarded by
        ``WHERE :estimate <= :ceiling`` rather than a bare ``VALUES`` clause,
        so a first reservation against a key with no existing row, for an
        estimate already larger than the ceiling, produces no candidate row
        and therefore no insert — see the module docstring's *three ceilings*
        section for why copying ADR-0006's shape verbatim would miss exactly
        this case. When a row already exists, the ``ON CONFLICT ... DO
        UPDATE`` is separately guarded by the arithmetic check against that
        row's own stored ``ceiling`` (fixed at first creation, never
        rewritten here). Either guard failing means ``RETURNING`` yields no
        row, which is this method's ``False``.
        """
        bucket = schema.spend_ceiling_bucket
        # Each literal is typed from the destination column it fills, rather
        # than a type this module maintains separately — `.from_select`,
        # unlike `.values()`, does not infer bind types from the INSERT's
        # target table, so an untyped literal here would bind by Python-value
        # guesswork instead of the schema's own NUMERIC(12,4)/UUID/Text.
        source = sa.select(
            sa.literal(tenant_id, type_=bucket.c.tenant_id.type).label("tenant_id"),
            sa.literal(bucket_type.value, type_=bucket.c.bucket_type.type).label("bucket_type"),
            sa.literal(bucket_key, type_=bucket.c.bucket_key.type).label("bucket_key"),
            sa.literal(ceiling, type_=bucket.c.ceiling.type).label("ceiling"),
            sa.literal(estimate, type_=bucket.c.reserved.type).label("reserved"),
        ).where(
            sa.literal(estimate, type_=bucket.c.reserved.type)
            <= sa.literal(ceiling, type_=bucket.c.ceiling.type)
        )

        statement = (
            pg_insert(bucket)
            .from_select(["tenant_id", "bucket_type", "bucket_key", "ceiling", "reserved"], source)
            .on_conflict_do_update(
                constraint=_BUCKET_PRIMARY_KEY,
                set_={"reserved": bucket.c.reserved + estimate},
                where=(bucket.c.reserved + bucket.c.spent + estimate <= bucket.c.ceiling),
            )
            .returning(bucket.c.reserved)
        )
        return self._session.execute(statement).one_or_none() is not None
