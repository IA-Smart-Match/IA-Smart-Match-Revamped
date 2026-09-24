"""The one module that reads or writes ``suppression_record`` (B26 T6b-3 plan §5.1).

A suppression row is **active** while ``lifted_at IS NULL``. Only an active row
stops a send. Every send-eligibility read in the codebase asks the same
question through :func:`active_suppression_exists` or
:meth:`SuppressionRepository.is_active`; nothing else names the table
(``tests/unit/test_suppression_single_reader.py`` pins that).

## Why ``EXISTS`` and not a ``LEFT JOIN``

With a ``LEFT JOIN``, ``lifted_at IS NULL`` in the ``WHERE`` would drop a
channel whose only suppression is lifted: the reader would answer "no such
contact", and the worker would fail ``outreach_contact_not_found``. In the
``ON`` clause it is correct but easy to regress. A correlated ``EXISTS`` has
neither failure mode.

## Writes

* :meth:`SuppressionRepository.record` merges a new suppression into the
  address's one row by rank (``smartmatch_domain.suppression.merge_suppression``):
  insert, no-op, escalate, or re-open a lifted row.
* :meth:`SuppressionRepository.lift` is the only writer of ``lifted_at``. It
  touches only the sources the Speaker's verdict allowed for *this* address,
  and ``ck_suppression_record_lift_source`` backs the widest set.

Nothing here commits: the caller owns the transaction.
"""

from __future__ import annotations

import uuid
from collections.abc import Collection, Iterable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import sqlalchemy as sa
from smartmatch_domain.suppression import (
    MergeAction,
    SuppressionSource,
    SuppressionState,
    SuppressionWrite,
    merge_suppression,
)
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Session

from smartmatch_persistence import schema

__all__ = [
    "RecordOutcome",
    "SuppressionLiftError",
    "SuppressionRepository",
    "active_suppression_exists",
]

_TABLE = schema.suppression_record


def active_suppression_exists(channel: sa.FromClause) -> sa.ColumnElement[bool]:
    """``EXISTS`` an active suppression for ``channel``'s ``(tenant_id, address)``.

    ``channel`` is ``schema.contact_channel`` or an alias of it. By address, not
    by channel id: a suppression is a statement about a person, not a row.
    """
    return sa.exists(
        sa.select(sa.literal(1))
        .select_from(_TABLE)
        .where(
            _TABLE.c.tenant_id == channel.c.tenant_id,
            _TABLE.c.address == channel.c.address,
            _TABLE.c.lifted_at.is_(None),
        )
    )


class SuppressionLiftError(RuntimeError):
    """A lift changed no row: nothing active, or a source the verdict did not allow.

    Raised so the caller's transaction rolls back rather than recording an
    opt-in that lifted nothing.
    """


@dataclass(frozen=True, slots=True)
class RecordOutcome:
    """What :meth:`SuppressionRepository.record` did.

    Attributes:
        write: The merge the row went through.
        was_already_suppressed: An active row existed before the call.
    """

    write: SuppressionWrite
    was_already_suppressed: bool


def _state(row: sa.Row[Any]) -> SuppressionState:
    return SuppressionState(
        source=SuppressionSource(row.source),
        suppressed_at=row.suppressed_at,
        lifted_at=row.lifted_at,
        origin_send_id=row.origin_send_id,
    )


_COLUMNS = (
    _TABLE.c.address,
    _TABLE.c.source,
    _TABLE.c.suppressed_at,
    _TABLE.c.lifted_at,
    _TABLE.c.origin_send_id,
)


class SuppressionRepository:
    """Reads and writes ``suppression_record``. Stateless; never commits."""

    def is_active(self, session: Session, *, tenant_id: uuid.UUID, address: str) -> bool:
        """Whether an active suppression covers this address in this tenant."""
        return (
            session.execute(
                sa.select(sa.literal(1)).where(
                    _TABLE.c.tenant_id == tenant_id,
                    _TABLE.c.address == address,
                    _TABLE.c.lifted_at.is_(None),
                )
            ).first()
            is not None
        )

    def lock_for_address(
        self, session: Session, *, tenant_id: uuid.UUID, address: str
    ) -> SuppressionState | None:
        """The address's row, ``FOR UPDATE``, lifted or not; ``None`` when there is none."""
        row = session.execute(
            sa.select(*_COLUMNS)
            .where(_TABLE.c.tenant_id == tenant_id, _TABLE.c.address == address)
            .with_for_update()
        ).one_or_none()
        return None if row is None else _state(row)

    def states_for_addresses(
        self, session: Session, *, tenant_id: uuid.UUID, addresses: Iterable[str]
    ) -> dict[str, SuppressionState]:
        """Each address's row, lifted or not, without a lock. One query."""
        wanted = sorted(set(addresses))
        if not wanted:
            return {}
        rows = session.execute(
            sa.select(*_COLUMNS).where(
                _TABLE.c.tenant_id == tenant_id, _TABLE.c.address.in_(wanted)
            )
        ).all()
        return {row.address: _state(row) for row in rows}

    def record(
        self,
        session: Session,
        *,
        tenant_id: uuid.UUID,
        address: str,
        source: SuppressionSource,
        at: datetime,
        origin_send_id: uuid.UUID | None = None,
        record_id: uuid.UUID | None = None,
    ) -> RecordOutcome:
        """Record that an address must not be written to, merged by rank.

        ``INSERT ... ON CONFLICT ON CONSTRAINT uq_suppression_record_address DO
        NOTHING RETURNING id``. When a row already exists: ``SELECT ... FOR
        UPDATE``, :func:`~smartmatch_domain.suppression.merge_suppression`, then
        one ``UPDATE`` or none. Two first suppressions for one address serialize
        on the surviving row (T6b-3 §7 race 9).
        """
        inserted = session.execute(
            postgresql.insert(_TABLE)
            .values(
                id=record_id or uuid.uuid4(),
                tenant_id=tenant_id,
                address=address,
                source=source.value,
                suppressed_at=at,
                origin_send_id=origin_send_id,
            )
            .on_conflict_do_nothing(constraint="uq_suppression_record_address")
            .returning(_TABLE.c.id)
        ).one_or_none()
        if inserted is not None:
            write = SuppressionWrite(MergeAction.INSERT, source, at, origin_send_id)
            return RecordOutcome(write=write, was_already_suppressed=False)

        existing = self.lock_for_address(session, tenant_id=tenant_id, address=address)
        if existing is None:  # pragma: no cover - the conflict proves a row exists
            raise RuntimeError("suppression_record conflict without a row")
        write = merge_suppression(existing, source, at=at, origin_send_id=origin_send_id)
        if write.action is not MergeAction.NOOP:
            values: dict[str, Any] = {
                "source": write.source.value,
                "suppressed_at": write.suppressed_at,
                "origin_send_id": write.origin_send_id,
            }
            if write.action is MergeAction.REOPEN:
                values["lifted_at"] = None
                values["lifted_by_user_id"] = None
            session.execute(
                sa.update(_TABLE)
                .where(_TABLE.c.tenant_id == tenant_id, _TABLE.c.address == address)
                .values(**values)
            )
        return RecordOutcome(write=write, was_already_suppressed=existing.active)

    def lift(
        self,
        session: Session,
        *,
        tenant_id: uuid.UUID,
        address: str,
        allowed_sources: Collection[SuppressionSource],
        lifted_at: datetime,
        lifted_by_user_id: uuid.UUID,
    ) -> None:
        """Lift the address's active suppression, if its source is in ``allowed_sources``.

        ``allowed_sources`` is the set the Speaker's verdict allowed for **this**
        address (S6), never the fixed liftable list.

        Raises:
            SuppressionLiftError: unless exactly one row changed.
        """
        sources = sorted(s.value for s in allowed_sources)
        if not sources:
            raise SuppressionLiftError("no source may be lifted on this address")
        result = session.execute(
            sa.update(_TABLE)
            .where(
                _TABLE.c.tenant_id == tenant_id,
                _TABLE.c.address == address,
                _TABLE.c.lifted_at.is_(None),
                _TABLE.c.source.in_(sources),
            )
            .values(lifted_at=lifted_at, lifted_by_user_id=lifted_by_user_id)
        )
        changed = result.rowcount  # type: ignore[attr-defined]
        if changed != 1:
            raise SuppressionLiftError(f"lift changed {changed} rows, expected 1")
