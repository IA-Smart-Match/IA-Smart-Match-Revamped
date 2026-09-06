"""The abandoned-reservation sweep (ADR-0015 Amendment A1, T-08).

``smartmatch_persistence.spend`` settles a reservation whose worker is still
alive to settle it: it reconciled, it timed out and said so, or it released
before dispatching. This module settles the reservations nobody came back
for. A worker that died between committing its debit and reporting its cost
leaves a ``reserved`` row whose lease quietly expires, and nothing else in the
system finds it — the paid call may well have happened, so the money is gone
whether or not anything records it.

A sibling module rather than more of ``spend.py`` because that file is already
past this repository's 800-line ceiling for a single module. The split is
along a real seam, not an arbitrary line count: the settle paths there are
driven by a caller holding a :class:`~smartmatch_domain.spend.
SpendReservationReceipt`, and this one is driven by the *absence* of any such
caller — see *Why the snapshot carries no lease token* below.

## The sweep never releases

A1: *"an expired, unreconciled reservation is unconditionally treated as
spent at its reserved maximum... and not released."* The reasoning is that a
reservation covers a call that may already have cost real money; releasing it
because nobody reported back would hand the tenant back budget a provider has
already billed for, and would do so precisely in the case — a crashed worker —
where the system knows least about what happened. So every reservation this
module touches lands in ``expired_spent`` at the full estimate, with
``actual_is_estimated=True`` because that figure is a reserved maximum and
never a reported cost (Global Constraint 6). There is no code path here that
reaches ``released``, and :func:`~smartmatch_domain.spend.expire_abandoned`
has no return type that could express one.

## Why the snapshot carries no lease token

:class:`~smartmatch_domain.spend.AbandonedReservationSnapshot` deliberately
omits ``lease_token``, and :meth:`SpendReservationSweeper._snapshot_from_row`
never selects the column. That absence is load-bearing: it makes it
impossible to build, from anything this sweep reads, a value satisfying
:func:`~smartmatch_domain.spend.release_before_dispatch`'s signature. The
"never releases" rule above is therefore enforced by the type system on the
way in, not only by this module's discipline on the way out.

## The write is Task 2's write

A swept reservation and an in-worker timeout reach ``expired_spent`` by
different discoveries but must leave identical rows behind — A1 requires the
same conservative figure and the same estimated flag from either path. Rather
than write that shape twice and let the copies drift, this module composes a
:class:`~smartmatch_persistence.spend.SpendReservationService` and settles
through the same ``_settle`` it uses, which takes the guarded ``UPDATE ...
WHERE state = 'reserved'``, credits all three buckets named on the row, flags
the row for review, and commits — one transaction per reservation.

## Concurrency: the guard, not a lock

Two sweeps running at once are safe because each reservation's transition is
a single guarded write, exactly as Global Constraint 2 requires everywhere
else: the loser's ``UPDATE`` matches no row and it moves on having written
nothing. This module deliberately does *not* take ``FOR UPDATE SKIP LOCKED``
over the batch the way ``JobRepository.sweep_expired_leases`` does, because it
cannot benefit from it — settling commits per reservation, which would drop
the batch's remaining locks at the first commit anyway. Taking locks that are
released before they are used would buy nothing and would misrepresent, to
the next reader, where this module's safety actually comes from.

The same guard is what makes a re-run emit no duplicate finding. A settled row
is no longer ``reserved``, so the next sweep's predicate does not select it;
the ``review_flagged_at`` guard inside ``_flag_for_review`` (Global Constraint
10) is the second line of that defence rather than the first.

## Failing closed

A sweep that cannot reach the database raises. It does not return an empty
sequence, because a caller cannot tell a clean sweep from a broken one if
both look like zero findings — and "no abandoned reservations" is the normal,
expected result, so the failure would hide in the ordinary case forever. This
is the rule ``StalledJobSweeper.sweep`` states for the same reason.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime

import sqlalchemy as sa
from smartmatch_domain.spend import (
    AbandonedReservationSnapshot,
    ExpiredOutcome,
    ReviewFinding,
    SpendReservationState,
)
from smartmatch_domain.spend import expire_abandoned as domain_expire_abandoned
from sqlalchemy.orm import Session

from smartmatch_persistence import schema
from smartmatch_persistence.spend import SpendReservationService, _bucket_deltas_for_settle

__all__ = ["DEFAULT_SWEEP_LIMIT", "SpendReservationSweeper"]

#: Most reservations one sweep settles. A bound rather than a throttle, for
#: the reason ``StalledJobSweeper`` gives: a sweep finding ten thousand
#: abandoned reservations has found an incident, and taking them a hundred at
#: a time keeps each pass short instead of walking the whole table while
#: whatever scheduled it waits behind.
DEFAULT_SWEEP_LIMIT = 100


class SpendReservationSweeper:
    """Reclaims reservations whose lease expired with nobody reconciling them.

    Args:
        session: The session every sweep runs in. Taken rather than a
            ``sessionmaker`` because settling is
            :class:`~smartmatch_persistence.spend.SpendReservationService`'s
            job and that class owns a session the same way — the two must
            share one, since a sweep's read and the settle it decides on are
            the same unit of work.
    """

    def __init__(self, session: Session) -> None:
        self._session = session
        self._service = SpendReservationService(session)

    def sweep(self, *, now: datetime, limit: int = DEFAULT_SWEEP_LIMIT) -> Sequence[ReviewFinding]:
        """Reclaim up to ``limit`` abandoned reservations as ``expired_spent``.

        Args:
            now: The instant expiry is judged against. Injected rather than
                read from the clock so a test exercises an expired lease
                without waiting one out.
            limit: Most reservations to settle in this pass. See
                :data:`DEFAULT_SWEEP_LIMIT`.

        Returns:
            One :class:`~smartmatch_domain.spend.ReviewFinding` per
            reservation **this call actually settled**, oldest lease first.
            Normally empty. A non-empty result is not a queue depth to be
            averaged away: every entry is a worker that died holding a paid
            call, and the tenant has been charged for it at the reserved
            maximum on a guess.

        Raises:
            Exception: whatever the database raised, unswallowed. See the
                module docstring's *Failing closed* section.
        """
        findings: list[ReviewFinding] = []
        for row in self._select_abandoned(now=now, limit=limit):
            outcome = domain_expire_abandoned(_snapshot_from_row(row), now=now)
            if not isinstance(outcome, ExpiredOutcome):
                # Refused: another settle path reached this row between the
                # select above and here. Its decision stands; ours is stale.
                continue
            if not self._settle_expired(row, outcome, now=now):
                continue
            # `ExpiredOutcome.review_finding` is optional because
            # `expire_on_timeout` may omit it; `expire_abandoned` never does,
            # so this is always taken. It is written as a narrowing rather
            # than an assertion deliberately: the settle above has already
            # committed, and raising here would report a failure for a
            # reclaim that succeeded.
            if outcome.review_finding is not None:
                findings.append(outcome.review_finding)
        return findings

    def _select_abandoned(
        self, *, now: datetime, limit: int
    ) -> Sequence[sa.Row[tuple[object, ...]]]:
        """Read the expired, still-``reserved`` rows this pass will settle.

        ``lease_expires_at < now`` is written before the state comparison for
        the reason ``JobRepository.sweep_expired_leases`` documents: a range
        condition on a timestamp is what an index can drive, whereas a status
        bound as a parameter is not something the planner can prove constant.
        No index covers this predicate on ``spend_reservation`` yet — migration
        ``0010`` created none — so today this is a sequential scan, bounded by
        ``limit``; the ordering is written to be correct when one is added.

        Oldest lease first, so a pass that hits ``limit`` reclaims what has
        been abandoned longest rather than an arbitrary subset.

        ``lease_token`` is **not** selected. See the module docstring's *Why
        the snapshot carries no lease token*.
        """
        reservation = schema.spend_reservation
        return self._session.execute(
            sa.select(
                reservation.c.id,
                reservation.c.tenant_id,
                reservation.c.work_key,
                reservation.c.job_bucket_key,
                reservation.c.tenant_day_bucket_key,
                reservation.c.tenant_month_bucket_key,
                reservation.c.state,
                reservation.c.estimate,
                reservation.c.lease_expires_at,
            )
            .where(
                reservation.c.lease_expires_at < now,
                reservation.c.state == SpendReservationState.RESERVED.value,
            )
            .order_by(reservation.c.lease_expires_at)
            .limit(limit)
        ).all()

    def _settle_expired(
        self, row: sa.Row[tuple[object, ...]], outcome: ExpiredOutcome, *, now: datetime
    ) -> bool:
        """Write one reclaim through the service's shared settle path.

        Returns whether this call won the guarded write. ``False`` means a
        concurrent settle — another sweep, or a worker that came back after
        all — took the row first, in which case nothing was written here and
        no finding is reported for it: the reservation was somebody else's to
        account for.
        """
        reserved_delta, spent_delta = _bucket_deltas_for_settle(outcome, estimate=row.estimate)
        return self._service._settle(
            row,
            target_state=SpendReservationState.EXPIRED_SPENT,
            now=now,
            actual_cost=outcome.spent_amount,
            actual_is_estimated=outcome.is_estimated,
            reserved_delta=reserved_delta,
            spent_delta=spent_delta,
            review_finding=outcome.review_finding,
        )


def _snapshot_from_row(row: sa.Row[tuple[object, ...]]) -> AbandonedReservationSnapshot:
    """Build the sweep's lease-token-free snapshot from a selected row.

    The counterpart to ``spend._snapshot_from_row``, and separate from it
    because the two build deliberately different types: that one carries the
    ``lease_token`` a receipt-holding caller must match, and this one cannot,
    for the reason the module docstring gives. Pure — no database access — so
    it is unit-testable against a fake row without PostgreSQL.
    """
    return AbandonedReservationSnapshot(
        id=row.id,
        tenant_id=row.tenant_id,
        work_key=row.work_key,
        state=SpendReservationState(row.state),
        estimate=row.estimate,
        lease_expires_at=row.lease_expires_at,
    )
