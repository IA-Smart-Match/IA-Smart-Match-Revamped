"""``pipeline_record`` write path — the S12 funnel's evidence (P8 card O2 app writers).

Migration ``0011`` gave the five Pipeline metrics a real table
(``services/api/smartmatch_api/routers/metrics.py::_pipeline_funnel_rows_v1``,
card O3, already reads it); this module is the write half card O2's own
docstring named as the next dependency: "Whichever migration first needs to
point at a pipeline record adds it then." No migration has, so this is that
write path's first caller-facing home, built now so a real match has
somewhere correct to land the moment one exists.

## No production caller wires this module yet, and that is deliberate

`docs/plans/2026-08-28-opportunities-s12-plan.md` states a standing
constraint that governs this exact table: **"No matcher actions before G1."**
G1 (plan P5, M1–M10 matching) has not closed
(`docs/status-report/2026-09-02-audit-status-report.md` §5: "M1–M10 matching
(after G1 workshop)" is still future work), so no code path in this
repository originates a genuine "subject X was matched to opportunity Y"
event today. Two further gaps compound that: professionals — the funnel's
actual subject, per the frontend's own "Deterministic referral assets
created for speaker–event pairs" (`Pipeline.tsx`) — have no persisted
identity of their own to be ``pipeline_record.subject_id`` yet
(``professional_unit_relationship``'s own column comment, migration
``0012``: "no professional table exists yet in this schema"); and
``attendance_record`` — what ``ck_pipeline_record_attendance_evidence``
requires the Attended stage to cite — has no write path either
(``routers/engagement.py`` is a declared-empty stub). Wiring this repository
to ``POST /v1/review-items/{id}/decision`` (raised as a candidate wiring
point when this module was commissioned) would write a real timestamp and a
real ``decided_by`` id, but under a claim the data does not support — a
coordinator accepting a submitted event or professional roster row is not a
person being matched to an opportunity — which is exactly the fabricated
"audits as correct but is wrong" number ADR-0011 and this migration's own
docstring exist to refuse. So this module is written, tested against every
`0011` CHECK constraint, and left uncalled by production code, the same
posture ``attendance_record`` itself has held since migration ``0009``.

## The write shape mirrors two existing repositories, not a new one

:meth:`PipelineRepository.record_matched` is
:meth:`~smartmatch_persistence.review.ReviewRepository.create_batch_with_items`'s
own idempotent-insert idiom — ``INSERT ... ON CONFLICT DO NOTHING`` against
the row's own natural key (here, ``uq_pipeline_record_subject_opportunity``)
— so calling it twice for the same journey is a no-op, not a
``UniqueViolation`` a caller has to catch.

:meth:`PipelineRepository.advance_stage` is
:meth:`~smartmatch_persistence.review.ReviewRepository.decide`'s conditional-
``UPDATE`` idiom, plus two things that method does not need:
``smartmatch_domain.pipeline.assert_stage_reachable`` is called first, the
same split ``smartmatch_persistence.jobs.JobRepository.transition`` already
makes against ``smartmatch_domain.jobs.assert_transition`` — a pure domain
rule refuses an impossible stage claim before any statement reaches the
database — and, because that domain rule only knows about *which* stages are
reached and not *when*, this module additionally compares ``reached_at``
against the prerequisite stage's own timestamp on the row already in hand and
raises :class:`PipelineStageOrderError` before issuing the ``UPDATE``.
``ck_pipeline_record_stage_prefix`` and ``ck_pipeline_record_stage_order`` are
both guarded in application code this way; the database's own CHECK
constraints are what still hold the line if either guard were ever skipped,
wrong, or raced by a concurrent write — which is why the ``UPDATE`` below also
carries the prerequisite's ordering in its own ``WHERE`` clause, not just the
application-side check.
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from types import MappingProxyType
from typing import Any, Final

import sqlalchemy as sa
from smartmatch_domain.pipeline import (
    PipelineStage,
    assert_stage_reachable,
    prerequisite_stage,
)
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Session

from smartmatch_persistence import schema

__all__ = [
    "ConflictingOwningUnitError",
    "PipelineRecordRow",
    "PipelineRepository",
    "PipelineStageOrderError",
    "PipelineStageOutcome",
    "UnknownAttendanceEvidenceError",
]


#: ``pipeline_record``'s five stage columns, keyed by the domain stage each
#: one stores the timestamp for — the names, for building ``UPDATE ...
#: SET <name> = ...`` kwargs and for reading :class:`PipelineRecordRow`'s own
#: matching attribute back via ``getattr``. A read-only view
#: (``MappingProxyType``), the same idiom
#: ``smartmatch_domain.pipeline._PREREQUISITE`` already uses, so nothing can
#: mutate what every call site treats as a fixed table.
_STAGE_COLUMN_NAMES: Final[Mapping[PipelineStage, str]] = MappingProxyType(
    {
        PipelineStage.MATCHED: "matched_at",
        PipelineStage.CONTACTED: "contacted_at",
        PipelineStage.CONFIRMED: "confirmed_at",
        PipelineStage.ATTENDED: "attended_at",
        PipelineStage.MEMBER_INQUIRY: "member_inquiry_at",
    }
)

#: The same five stages, as the actual schema columns — spelled out
#: explicitly rather than looked up off :data:`_STAGE_COLUMN_NAMES` via
#: ``getattr``, mirroring ``routers/metrics.py::_PIPELINE_STAGE_COLUMNS``'s
#: own explicit mapping and for the identical reason that dict's own
#: docstring gives: a shortcut that derived the column from the name would
#: happen to work for all five stages that exist today, which is exactly
#: what makes it dangerous the day a sixth one does not agree.
_STAGE_COLUMNS: Final[Mapping[PipelineStage, sa.ColumnElement[Any]]] = MappingProxyType(
    {
        PipelineStage.MATCHED: schema.pipeline_record.c.matched_at,
        PipelineStage.CONTACTED: schema.pipeline_record.c.contacted_at,
        PipelineStage.CONFIRMED: schema.pipeline_record.c.confirmed_at,
        PipelineStage.ATTENDED: schema.pipeline_record.c.attended_at,
        PipelineStage.MEMBER_INQUIRY: schema.pipeline_record.c.member_inquiry_at,
    }
)


class PipelineStageOrderError(ValueError):
    """``reached_at`` precedes the prerequisite stage's own timestamp.

    ``ck_pipeline_record_stage_order`` (migration ``0011``) refuses this at
    the database too; this is the identical refusal, raised in application
    code — against the row already read for :meth:`PipelineRepository.advance_stage`'s
    other preconditions — before any statement reaches the database, the same
    ``ValueError`` subclass idiom ``InvalidPipelineStageTransitionError``
    documents itself with: a caller that wants to catch exactly this refusal
    has a type to catch.
    """


class UnknownAttendanceEvidenceError(ValueError):
    """``attended_attendance_id`` does not name a real row in this tenant.

    Checked with a ``SELECT`` before :meth:`PipelineRepository.advance_stage`
    issues its ``UPDATE``, rather than left to the composite foreign key
    (``pipeline_record_tenant_id_attended_attendance_id_fkey``): a bogus or
    cross-tenant id would otherwise abort the whole transaction with an
    ``IntegrityError`` the caller may not be prepared to catch, for the same
    reason the Attended stage's other precondition
    (``ck_pipeline_record_attendance_evidence``) is checked here rather than
    left to its own constraint.
    """


class ConflictingOwningUnitError(ValueError):
    """A journey already exists under a different ``owning_unit_id``.

    ``uq_pipeline_record_subject_opportunity`` —
    :meth:`PipelineRepository.record_matched`'s idempotency key — is
    ``(tenant_id, subject_id, opportunity_event_id)`` and deliberately
    excludes ``owning_unit_id`` (A5 scoping is written once, at the row's
    first insert; migration ``0011``'s docstring). A second call naming a
    different unit for the same journey would otherwise be silently absorbed
    by ``ON CONFLICT DO NOTHING``: the journey stays counted under the first
    unit's funnel and never the second's, an inconsistency a caller cannot see
    from the returned row alone. Refused rather than accepted silently.
    """


@dataclass(frozen=True, slots=True)
class PipelineRecordRow:
    """One ``pipeline_record`` row, as it stands after a write."""

    id: uuid.UUID
    tenant_id: uuid.UUID
    owning_unit_id: uuid.UUID
    subject_id: uuid.UUID
    opportunity_event_id: uuid.UUID
    matched_at: datetime
    contacted_at: datetime | None
    confirmed_at: datetime | None
    attended_at: datetime | None
    member_inquiry_at: datetime | None
    attended_attendance_id: uuid.UUID | None

    def reached(self) -> frozenset[PipelineStage]:
        """Every stage this row has reached, derived from which timestamps are set.

        The same predicate the register and ``_pipeline_funnel_rows_v1`` both
        use — "reached stage X" is ``<stage>_at IS NOT NULL`` and nothing
        else — read back off this row rather than tracked separately, so it
        cannot drift from what the row actually stores.
        """
        return frozenset(
            stage for stage, name in _STAGE_COLUMN_NAMES.items() if getattr(self, name) is not None
        )


@dataclass(frozen=True, slots=True)
class PipelineStageOutcome:
    """What happened when :meth:`PipelineRepository.advance_stage` was called.

    Mirrors :class:`~smartmatch_persistence.review.ReviewDecisionOutcome`'s
    shape, with one addition. :attr:`exists` is ``False`` when no row matches
    ``record_id`` in this tenant. :attr:`transitioned` is the ``UPDATE``'s own
    ``RETURNING`` result and nothing else — it is ``True`` only when *this
    call's* statement is the one that wrote ``stage``'s timestamp, never
    inferred from a re-read, so two concurrent callers under READ COMMITTED
    can never both observe ``True`` for the same transition (see
    :attr:`~ReviewDecisionOutcome.transitioned`'s own docstring for why a
    blind zero-row match cannot be trusted to mean the same thing every time).

    :attr:`already_reached` answers a different question — "is ``stage``
    reached now, whoever's write did it" — and exists precisely so a caller
    cannot confuse it with :attr:`transitioned`. It is ``True`` in two
    situations that are otherwise indistinguishable from a bare
    ``transitioned=False``: the row had already reached ``stage`` when this
    call's own read happened (a genuine no-op — the standing answer
    :meth:`~smartmatch_persistence.review.ReviewRepository.decide` gives a
    repeated decision), or a concurrent writer reached it in the window
    between this call's read and its ``UPDATE`` (this call lost the race).
    Both leave :attr:`transitioned` ``False`` and :attr:`already_reached`
    ``True``; :attr:`record` carries the row's resulting state either way.
    """

    exists: bool
    transitioned: bool
    already_reached: bool = False
    record: PipelineRecordRow | None = None


class PipelineRepository:
    """Writes ``pipeline_record`` rows — the S12 funnel's evidence.

    Takes a session per call, like every other repository in this package
    (``jobs.py``, ``review.py``, ``redrive.py``): transaction boundaries
    belong to the caller, and neither method here commits.
    """

    def get(
        self, session: Session, *, tenant_id: uuid.UUID, record_id: uuid.UUID
    ) -> PipelineRecordRow | None:
        """Read one journey back by id, scoped by tenant — or ``None``.

        Public, unlike :meth:`_read_by_journey` below: a caller (a router, a
        future matching writer, or this module's own tests) that already
        holds ``record_id`` — the common case once :meth:`record_matched` or
        :meth:`advance_stage` has returned one — has no journey key left to
        look it up by, so this is the read-by-id path
        :meth:`~smartmatch_persistence.jobs.JobRepository.get` already
        establishes the shape of, for jobs.
        """
        return self._read_by_id(session, tenant_id=tenant_id, record_id=record_id)

    def record_matched(
        self,
        session: Session,
        *,
        tenant_id: uuid.UUID,
        owning_unit_id: uuid.UUID,
        subject_id: uuid.UUID,
        opportunity_event_id: uuid.UUID,
        matched_at: datetime,
    ) -> PipelineRecordRow:
        """Open one journey: ``subject_id`` matched to ``opportunity_event_id``.

        Idempotent under ``uq_pipeline_record_subject_opportunity``: a second
        call naming the same ``(tenant_id, subject_id, opportunity_event_id)``
        is a no-op — the ``ON CONFLICT DO NOTHING`` below matches
        :meth:`~smartmatch_persistence.review.ReviewRepository.create_batch_with_items`'s
        own idiom for the identical reason — and this method returns the row
        as it already stood, not an error a caller has to catch.

        ``matched_at`` is a required argument, not defaulted to
        ``utc_now()`` internally: the schema's own ``server_default`` already
        covers "no caller has an opinion", so a repository default here would
        only ever be a second, competing source for the same value. A caller
        with a real match names the moment it happened, the same discipline
        :meth:`~smartmatch_persistence.review.ReviewRepository.decide` applies
        to ``decided_at``. It must be timezone-aware: ``pipeline_record``'s
        stage columns are ``timestamptz``, and a naive ``datetime`` compares
        against them using the session's local offset rather than UTC, which
        can silently satisfy or violate ``ck_pipeline_record_stage_order``
        depending on what that offset happens to be — refused here rather than
        left to that accident.

        **Assumes READ COMMITTED** (PostgreSQL's default, and what this
        codebase runs under). The insert below and the read-back that follows
        it are two statements, not one: under READ COMMITTED a concurrent
        commit between them is visible to the read, which is exactly what
        makes the read-back the correct way to learn whether *this* call or an
        earlier one won the ``ON CONFLICT``. A stricter isolation level
        (``REPEATABLE READ`` or ``SERIALIZABLE``) would make the read-back
        Isolation-anomaly-prone instead — it could still see the pre-insert
        snapshot — so this method is not safe to call under one without
        re-examining that assumption.

        Args:
            owning_unit_id: The unit this journey is scoped against (A5) —
                supplied by the caller, not derived here, mirroring
                ``ReviewRepository.create_batch_with_items``'s
                ``owning_unit_id`` argument. Must agree with the unit an
                earlier call already wrote for this exact journey — see
                :class:`ConflictingOwningUnitError`.

        Returns:
            The row as it now stands — freshly inserted, or the one an
            earlier call already wrote for this exact journey.

        Raises:
            ValueError: ``matched_at`` is a naive ``datetime``.
            ConflictingOwningUnitError: this journey already exists under a
                different ``owning_unit_id``.
        """
        if matched_at.tzinfo is None:
            raise ValueError(
                "matched_at must be timezone-aware — a naive datetime can silently "
                "violate ck_pipeline_record_stage_order against a timestamptz column"
            )

        record_id = uuid.uuid4()
        session.execute(
            postgresql.insert(schema.pipeline_record)
            .values(
                id=record_id,
                tenant_id=tenant_id,
                owning_unit_id=owning_unit_id,
                subject_id=subject_id,
                opportunity_event_id=opportunity_event_id,
                matched_at=matched_at,
            )
            .on_conflict_do_nothing(constraint="uq_pipeline_record_subject_opportunity")
        )
        row = self._read_by_journey(
            session,
            tenant_id=tenant_id,
            subject_id=subject_id,
            opportunity_event_id=opportunity_event_id,
        )
        if row is None:
            # The insert above is either the row that now exists or lost an
            # ON CONFLICT to one that does — either way a row must be there.
            # Not asserted: an assert is compiled out under python -O, which
            # would return None from a method typed to return
            # PipelineRecordRow.
            raise RuntimeError(
                f"no pipeline_record found for tenant {tenant_id}, subject {subject_id}, "
                f"opportunity {opportunity_event_id} immediately after an insert "
                "targeting that exact key — this should be unreachable"
            )
        if row.owning_unit_id != owning_unit_id:
            raise ConflictingOwningUnitError(
                f"pipeline_record {row.id} already exists for this journey under owning "
                f"unit {row.owning_unit_id}, not the {owning_unit_id} this call named"
            )
        return row

    def advance_stage(
        self,
        session: Session,
        *,
        tenant_id: uuid.UUID,
        record_id: uuid.UUID,
        stage: PipelineStage,
        reached_at: datetime,
        attended_attendance_id: uuid.UUID | None = None,
    ) -> PipelineStageOutcome:
        """Advance one journey to ``stage``, refusing an unreachable one.

        ``stage`` is coerced with ``PipelineStage(stage)`` at the top of this
        method — the same "the caller may hand back a plain string, or a
        ``StrEnum`` member imported through a different module path" boundary
        discipline ``JobRepository`` applies via ``JobState(row.status)`` —
        so every comparison below is against the canonical member rather than
        an identity check (``is``) that only happens to hold for the literal
        object a caller passed in.

        ``stage`` must not be :attr:`~smartmatch_domain.pipeline.PipelineStage.MATCHED`
        — that stage is opened by :meth:`record_matched`, not advanced to;
        every row this method can find already has it.
        ``smartmatch_domain.pipeline.assert_stage_reachable`` runs against the
        row's own current stages before any statement is issued (mirroring
        ``JobRepository.transition``'s call to ``assert_transition``), so a
        caller that tries to record Confirmed before Contacted gets
        ``InvalidPipelineStageTransitionError`` rather than a database
        round-trip that would only end in ``IntegrityError``. This method then
        separately compares ``reached_at`` against the prerequisite stage's
        own timestamp on that same row — ``assert_stage_reachable`` only knows
        *which* stages are reached, not *when*, so it cannot catch a
        ``reached_at`` that names a moment before its prerequisite — and
        raises :class:`PipelineStageOrderError` before any statement is
        issued if it precedes it.

        The Attended stage additionally requires ``attended_attendance_id`` —
        ``ck_pipeline_record_attendance_evidence``'s biconditional, enforced
        here as a precondition for the same reason: a caller that omits it is
        told immediately, in a caller-catchable ``ValueError``, rather than
        via a constraint violation naming a column it may not recognize. When
        supplied, it is also checked against a real, tenant-scoped
        ``attendance_record`` row before the ``UPDATE`` — see
        :class:`UnknownAttendanceEvidenceError`.

        Args:
            reached_at: When this stage was reached. Required, not derived —
                see :meth:`record_matched`'s docstring for why, including the
                same timezone-aware requirement (checked here too). Must be
                greater than or equal to the prerequisite stage's own
                timestamp (``ck_pipeline_record_stage_order``); an ``at`` that
                violates that ordering is refused in application code, against
                the row already read for the other preconditions above, before
                any statement reaches the database — the ``UPDATE`` below
                additionally repeats the ordering test in its own ``WHERE``
                clause, which is that constraint's own backstop role against
                a concurrent write racing this one between the read and the
                write.
            attended_attendance_id: The real ``attendance_record`` row this
                claim cites. Required when ``stage`` is
                :attr:`~smartmatch_domain.pipeline.PipelineStage.ATTENDED`, and
                rejected for every other stage — a claim citing evidence for a
                stage that is not Attended has nowhere valid to put it. Must
                name a row that actually exists in this tenant.

        Returns:
            A :class:`PipelineStageOutcome` reporting whether the row exists,
            whether *this call's own statement* is the one that reached
            ``stage``, and the row's resulting state. See that class's
            docstring for why ``transitioned`` and ``already_reached`` are
            two different fields rather than one overloaded boolean.

        Raises:
            ValueError: ``stage`` is ``MATCHED``, ``attended_attendance_id``
                is present/absent for the wrong stage, or either datetime
                argument is naive.
            InvalidPipelineStageTransitionError: the row exists but has not
                yet reached ``stage``'s prerequisite.
            PipelineStageOrderError: ``reached_at`` precedes the prerequisite
                stage's own timestamp.
            UnknownAttendanceEvidenceError: ``attended_attendance_id`` does
                not name a row in ``attendance_record`` in this tenant.
        """
        stage = PipelineStage(stage)

        if stage == PipelineStage.MATCHED:
            raise ValueError("MATCHED is the entry stage; call record_matched, not advance_stage")
        if stage == PipelineStage.ATTENDED and attended_attendance_id is None:
            raise ValueError(
                "the Attended stage requires attended_attendance_id "
                "(ck_pipeline_record_attendance_evidence)"
            )
        if stage != PipelineStage.ATTENDED and attended_attendance_id is not None:
            raise ValueError(
                f"attended_attendance_id is only accepted for the Attended stage, not {stage.value}"
            )
        if reached_at.tzinfo is None:
            raise ValueError(
                "reached_at must be timezone-aware — a naive datetime can silently "
                "violate ck_pipeline_record_stage_order against a timestamptz column"
            )

        if attended_attendance_id is not None:
            evidence_row = session.execute(
                sa.select(schema.attendance_record.c.id).where(
                    schema.attendance_record.c.tenant_id == tenant_id,
                    schema.attendance_record.c.id == attended_attendance_id,
                )
            ).one_or_none()
            if evidence_row is None:
                raise UnknownAttendanceEvidenceError(
                    f"attendance_record {attended_attendance_id} does not exist in tenant "
                    f"{tenant_id} — ck_pipeline_record_attendance_evidence requires real evidence"
                )

        row = self._read_by_id(session, tenant_id=tenant_id, record_id=record_id)
        if row is None:
            return PipelineStageOutcome(exists=False, transitioned=False)

        reached = row.reached()
        if stage in reached:
            # Already reached as of this call's own read — not this call's
            # transition, and not an error: see PipelineStageOutcome's
            # docstring for why this is the same answer
            # ReviewRepository.decide gives a repeated decision.
            return PipelineStageOutcome(
                exists=True, transitioned=False, already_reached=True, record=row
            )

        assert_stage_reachable(reached, stage)  # raises InvalidPipelineStageTransitionError

        prerequisite = prerequisite_stage(stage)
        if prerequisite is None:
            # Unreachable: every stage but MATCHED has a prerequisite, and
            # MATCHED was already refused above. Not asserted — see
            # record_matched's own RuntimeError for why an invariant this
            # method's return type depends on is raised explicitly rather
            # than compiled out under python -O.
            raise RuntimeError(f"{stage.value} has no prerequisite stage — unreachable")
        prerequisite_column = _STAGE_COLUMNS[prerequisite]
        target_column = _STAGE_COLUMNS[stage]

        prerequisite_at = getattr(row, _STAGE_COLUMN_NAMES[prerequisite])
        if prerequisite_at is None:
            # Unreachable: assert_stage_reachable above already confirmed
            # prerequisite is in `reached`, which is defined as "its column is
            # not None". Raised, not asserted, for the same reason as above.
            raise RuntimeError(
                f"{prerequisite.value} is reported reached but its timestamp is None — unreachable"
            )
        if reached_at < prerequisite_at:
            raise PipelineStageOrderError(
                f"{stage.value} reached_at ({reached_at!r}) precedes its prerequisite "
                f"{prerequisite.value}'s own timestamp ({prerequisite_at!r}) "
                "(ck_pipeline_record_stage_order)"
            )

        update_values: dict[str, object] = {
            _STAGE_COLUMN_NAMES[stage]: reached_at,
            "updated_at": datetime.now(UTC),
        }
        if stage == PipelineStage.ATTENDED:
            update_values["attended_attendance_id"] = attended_attendance_id

        transitioned_id = session.execute(
            sa.update(schema.pipeline_record)
            .where(
                schema.pipeline_record.c.tenant_id == tenant_id,
                schema.pipeline_record.c.id == record_id,
                target_column.is_(None),
                prerequisite_column.is_not(None),
                # Closes the race CRITICAL 1 names: even if the prerequisite
                # was reached again with a later timestamp between this
                # method's read above and this UPDATE, the ordering this call
                # was told to enforce is re-checked against the row this
                # statement actually touches, not just the one this method
                # happened to read earlier.
                prerequisite_column <= reached_at,
            )
            .values(**update_values)
            .returning(schema.pipeline_record.c.id)
        ).one_or_none()

        # transitioned is this UPDATE's own RETURNING result and nothing
        # else — never inferred from a re-read — per CRITICAL 2.
        if transitioned_id is not None:
            # The common case: this call's own UPDATE is the transition, so
            # the row already in hand plus what this call just wrote is the
            # row's resulting state — no re-read needed, mirroring
            # ReviewRepository.decide's fast path. Spelled out per stage with
            # literal keyword arguments, not built from a dynamic dict keyed
            # off _STAGE_COLUMN_NAMES: dataclasses.replace's own typing (and
            # this module's stated preference — see _STAGE_COLUMNS's
            # docstring) both want the field being written named explicitly,
            # not derived.
            if stage == PipelineStage.CONTACTED:
                updated_row = replace(row, contacted_at=reached_at)
            elif stage == PipelineStage.CONFIRMED:
                updated_row = replace(row, confirmed_at=reached_at)
            elif stage == PipelineStage.ATTENDED:
                updated_row = replace(
                    row, attended_at=reached_at, attended_attendance_id=attended_attendance_id
                )
            else:
                updated_row = replace(row, member_inquiry_at=reached_at)
            return PipelineStageOutcome(exists=True, transitioned=True, record=updated_row)

        # The UPDATE matched nothing. The precondition checks above already
        # ruled out "does not exist", "already reached", "prerequisite
        # unmet", and "reached_at out of order" as of this method's own read;
        # reaching here means a concurrent write changed the row between that
        # read and this UPDATE. Re-read once, honestly, only to classify which
        # zero-match case this is — never to decide `transitioned`.
        row = self._read_by_id(session, tenant_id=tenant_id, record_id=record_id)
        if row is None:
            # A concurrent DELETE FROM pipeline_record — nothing in this
            # schema's outward-pointing RESTRICT foreign keys prevents that
            # (they protect org_unit/user_account/attendance_record from
            # deletion while a pipeline_record cites them, not the reverse).
            return PipelineStageOutcome(exists=False, transitioned=False)
        return PipelineStageOutcome(
            exists=True,
            transitioned=False,
            already_reached=stage in row.reached(),
            record=row,
        )

    # -- internals -------------------------------------------------------

    def _read_by_id(
        self, session: Session, *, tenant_id: uuid.UUID, record_id: uuid.UUID
    ) -> PipelineRecordRow | None:
        row = session.execute(
            sa.select(schema.pipeline_record).where(
                schema.pipeline_record.c.tenant_id == tenant_id,
                schema.pipeline_record.c.id == record_id,
            )
        ).one_or_none()
        return None if row is None else _to_row(row)

    def _read_by_journey(
        self,
        session: Session,
        *,
        tenant_id: uuid.UUID,
        subject_id: uuid.UUID,
        opportunity_event_id: uuid.UUID,
    ) -> PipelineRecordRow | None:
        row = session.execute(
            sa.select(schema.pipeline_record).where(
                schema.pipeline_record.c.tenant_id == tenant_id,
                schema.pipeline_record.c.subject_id == subject_id,
                schema.pipeline_record.c.opportunity_event_id == opportunity_event_id,
            )
        ).one_or_none()
        return None if row is None else _to_row(row)


def _to_row(row: sa.Row[Any]) -> PipelineRecordRow:
    return PipelineRecordRow(
        id=row.id,
        tenant_id=row.tenant_id,
        owning_unit_id=row.owning_unit_id,
        subject_id=row.subject_id,
        opportunity_event_id=row.opportunity_event_id,
        matched_at=row.matched_at,
        contacted_at=row.contacted_at,
        confirmed_at=row.confirmed_at,
        attended_at=row.attended_at,
        member_inquiry_at=row.member_inquiry_at,
        attended_attendance_id=row.attended_attendance_id,
    )
