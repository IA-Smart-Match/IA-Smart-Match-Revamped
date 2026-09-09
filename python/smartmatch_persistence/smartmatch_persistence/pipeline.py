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
    CbaStageEvidence,
    CbaStageEvidenceKind,
    PipelineStage,
    assert_cba_stage_writable,
    assert_stage_reachable,
    plan_cba_stages,
    prerequisite_stage,
)
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Session

from smartmatch_persistence import schema
from smartmatch_persistence.cba_invitations import InvitationRepository

__all__ = [
    "MATCH_PROVENANCE_MATCH_ENGINE",
    "MATCH_PROVENANCE_SYNTHETIC_COORDINATOR",
    "MATCH_PROVENANCE_VALUES",
    "CbaAttendanceMismatchError",
    "CbaHandoffOutcome",
    "CbaHandoffRepository",
    "CbaInvitationNotConfirmedError",
    "CbaInvitationNotFoundError",
    "ConfirmedSpeakerRow",
    "ConflictingOwningUnitError",
    "PipelineRecordRow",
    "PipelineRepository",
    "PipelineStageOrderError",
    "PipelineStageOutcome",
    "UnknownAttendanceEvidenceError",
    "UnknownOpportunityEventError",
]

#: A coordinator accepted a synthetic, in-list opportunity row in the pilot
#: appliance — no matching engine ran. This is the exact string the program
#: owner directed, and the one string this module, the database column, and
#: the provisioning service's log line all share; see migration ``0016``'s
#: module docstring for why a tidier ``snake_case`` spelling would be a second
#: source of truth for the same fact.
MATCH_PROVENANCE_SYNTHETIC_COORDINATOR: Final[str] = "synthetic / coordinator-accepted"

#: The row was produced by the real matching engine (G1 / M1-M10, landing on
#: ``pilot/match-engine-m2-m7``). A reserved slot: **nothing in this
#: repository writes this value.** Reserving it is not depending on that
#: branch.
MATCH_PROVENANCE_MATCH_ENGINE: Final[str] = "match-engine"

#: The closed vocabulary ``ck_pipeline_record_matched_provenance`` admits.
#: :meth:`PipelineRepository.record_matched` checks a caller's argument
#: against this set in application code before any statement reaches the
#: database — the CHECK constraint remains the backstop.
MATCH_PROVENANCE_VALUES: Final[frozenset[str]] = frozenset(
    {MATCH_PROVENANCE_SYNTHETIC_COORDINATOR, MATCH_PROVENANCE_MATCH_ENGINE}
)


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
    matched_provenance: str
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
        matched_provenance: str,
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

        ``matched_provenance`` is a required argument with **no default**, for
        the same reason ``matched_at`` is required rather than assumed: a
        default would let a caller write a row that asserts a match happened
        without saying where it came from, which is exactly the fabricated-
        field shape this column exists to make unstorable (migration
        ``0016``'s own module docstring). It is checked against
        :data:`MATCH_PROVENANCE_VALUES` before any statement is issued, so a
        caller gets a catchable ``ValueError`` naming the constraint rather
        than an ``IntegrityError`` naming a column it may not recognize — the
        database's own CHECK remains the backstop.

        **Provenance under idempotency.** This method conflicts ``DO
        NOTHING`` against ``uq_pipeline_record_subject_opportunity``, so
        ``matched_provenance`` is written exactly once, by whichever call
        first creates the row for a given ``(tenant_id, subject_id,
        opportunity_event_id)``. A later call naming a *different*
        provenance for that same journey does **not** overwrite it — the
        read-back below returns the row as the first call left it, silently
        for provenance the same way it already does for ``matched_at``. This
        method deliberately has no ``ON CONFLICT DO UPDATE`` path: one would
        let a synthetic re-accept relabel a row the matching engine produced,
        or the reverse, and if a row's provenance ever genuinely needs to
        change that is a separate, deliberate operation this method does not
        provide.

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
            matched_provenance: Where this match came from. Must be one of
                :data:`MATCH_PROVENANCE_VALUES`. Not overwritten by a later
                call for the same journey — see "Provenance under
                idempotency" above.

        Returns:
            The row as it now stands — freshly inserted, or the one an
            earlier call already wrote for this exact journey.

        Raises:
            ValueError: ``matched_at`` is a naive ``datetime``, or
                ``matched_provenance`` is not one of
                :data:`MATCH_PROVENANCE_VALUES`.
            ConflictingOwningUnitError: this journey already exists under a
                different ``owning_unit_id``.
        """
        if matched_provenance not in MATCH_PROVENANCE_VALUES:
            raise ValueError(
                f"matched_provenance must be one of {sorted(MATCH_PROVENANCE_VALUES)}, "
                f"not {matched_provenance!r} (ck_pipeline_record_matched_provenance)"
            )
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
                matched_provenance=matched_provenance,
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
        matched_provenance=row.matched_provenance,
        contacted_at=row.contacted_at,
        confirmed_at=row.confirmed_at,
        attended_at=row.attended_at,
        member_inquiry_at=row.member_inquiry_at,
        attended_attendance_id=row.attended_attendance_id,
    )


# ===========================================================================
# The CBA speaker handoff (track CBA-HANDOFF-PIPELINE)
# ===========================================================================
#
# Everything above is the general funnel writer, unchanged: it still writes all
# five stages, ``member_inquiry`` included, because the pre-CBA product and
# every row already in ``pipeline_record`` depend on it.
#
# What follows is the CBA product's own writer, and its whole difference is
# where the stages come from. :class:`PipelineRepository.advance_stage` takes a
# caller's word for *when* a stage was reached; :class:`CbaHandoffRepository`
# takes nobody's word. Each stage it writes is derived from a row that is
# already in the database and is stamped with **that row's own timestamp**:
#
#   matched    <- cba_invitation.created_at        (a Connector composed it)
#   contacted  <- cba_invitation.dispatched_at     (ck_..._dispatched ties this
#                                                   to a real send job)
#   confirmed  <- cba_invitation.response_recorded_at, and only when
#                 response_status = 'accepted_invitation' -- the Speaker's own
#                 answer, never a provider's delivery disposition
#   attended   <- attendance_record.created_at, for a row whose subject and
#                 event both match this journey
#
# There is no argument by which a caller can name a stage or a moment. That is
# what makes this not a stage toggle with a nicer name: re-running it against
# unchanged evidence writes nothing, and running it against evidence that does
# not support Confirmed refuses rather than writing a weaker claim.


class UnknownOpportunityEventError(ValueError):
    """``opportunity_event_id`` does not name a real event in this tenant.

    ``pipeline_record.opportunity_event_id`` carries **no foreign key** -- the
    column predates the ``event`` table and migration ``0017`` added the
    constraint to ``attendance_record.event_id`` only. So nothing in the schema
    stops a journey being opened against an id that names nothing, and a funnel
    row whose opportunity does not exist is a count no Event Host can act on.
    Checked here, with a ``SELECT``, because the database will not.
    """


class CbaInvitationNotFoundError(ValueError):
    """No such ``cba_invitation`` in this tenant and this unit.

    One error for both, deliberately. A caller that may act in the unit it named
    and is handed an invitation id belonging to a *different* unit has named
    something it is not entitled to distinguish from a typo; a route turns this
    into a 404 rather than a 403 for the same reason ``compose_draft`` does.
    """


class CbaInvitationNotConfirmedError(ValueError):
    """The invitation exists but does not evidence a confirmed speaker.

    Raised **before anything is written**, so an unanswered, declined or skipped
    invitation leaves no journey behind at all -- not even one stopped at
    Contacted. That is the deliberate choice: this repository's purpose is the
    Event Host handoff, and a half-opened journey for a speaker who never said
    yes would put a row into the Matched and Contacted aggregates as a side
    effect of somebody checking whether the handoff was possible yet.
    """


class CbaAttendanceMismatchError(ValueError):
    """The cited attendance is real, but it is not this journey's.

    ``ck_pipeline_record_attendance_evidence`` makes the citation biconditional
    -- an Attended row names an attendance, and a row naming one is Attended --
    but the schema never checks *whose* attendance, or *which event's*. Both
    gaps are closed here: an Attended stage evidenced by somebody else's
    attendance, or by attendance at a different event, is a number the
    drill-down would report faithfully and a reader could not reconcile.
    """


@dataclass(frozen=True, slots=True)
class ConfirmedSpeakerRow:
    """One confirmed speaker, as the Event Host is handed them.

    Carries **no** ``member_inquiry_at``. Not filtered out at the edge and not
    set to ``None`` -- the field does not exist on this record, so no CBA
    surface built on it can render one even by accident. The stage's column,
    its history and :class:`PipelineRecordRow`'s own field are all untouched.

    The three identity fields come from ``speaker_profile`` and are ``None``
    when this tenant holds no profile for the ``professional_id`` -- an honest
    unknown rather than a blank string, the same distinction
    ``speaker_profile.company``'s own column comment draws.
    """

    record_id: uuid.UUID
    owning_unit_id: uuid.UUID
    professional_id: uuid.UUID
    opportunity_event_id: uuid.UUID
    full_name: str | None
    company: str | None
    title: str | None
    matched_at: datetime
    contacted_at: datetime | None
    confirmed_at: datetime
    attended_at: datetime | None
    attended_attendance_id: uuid.UUID | None


@dataclass(frozen=True, slots=True)
class CbaHandoffOutcome:
    """What one reconciliation found, and what it wrote.

    :attr:`evidence` is the whole stage-to-evidence map the stored rows support
    right now, whoever wrote it; :attr:`applied` is only the stages *this call's
    own statements* reached. The two are separate for the reason
    :class:`PipelineStageOutcome` keeps ``transitioned`` and ``already_reached``
    apart: "the speaker is confirmed" and "this request confirmed them" are
    different facts, and a replay must be able to say the first without
    claiming the second.
    """

    record: PipelineRecordRow
    evidence: tuple[CbaStageEvidence, ...]
    applied: tuple[PipelineStage, ...]


class CbaHandoffRepository:
    """Derives CBA funnel stages from invitation and attendance evidence.

    Stateless; one instance serves all. Takes a session per call and **commits
    nothing** -- transaction boundaries belong to the caller, exactly as they do
    for :class:`PipelineRepository` and every other repository in this package.
    A route calling this must issue its own ``session.commit()``: ``get_session``
    rolls back unconditionally, so a route that forgets returns a clean 2xx and
    stores nothing.
    """

    def __init__(self) -> None:
        self._pipeline = PipelineRepository()
        self._invitations = InvitationRepository()

    # -- writes ----------------------------------------------------------

    def reconcile_invitation(
        self,
        session: Session,
        *,
        tenant_id: uuid.UUID,
        owning_unit_id: uuid.UUID,
        opportunity_event_id: uuid.UUID,
        invitation_id: uuid.UUID,
        attendance_id: uuid.UUID | None = None,
    ) -> CbaHandoffOutcome:
        """Bring one speaker's journey up to whatever the evidence supports.

        Idempotent, and idempotent in the strong sense: the stages and their
        timestamps are read out of the invitation and the attendance row rather
        than passed in, so calling this twice with the same stored evidence
        cannot produce a second row, a moved timestamp, or a different answer.
        The second call reports the same :attr:`~CbaHandoffOutcome.evidence` and
        an empty :attr:`~CbaHandoffOutcome.applied`.

        Ordered, and the order is not this method's to skip: the plan is a
        prefix of the CBA funnel by construction
        (``smartmatch_domain.pipeline.plan_cba_stages``), and each stage is
        still written through :meth:`PipelineRepository.advance_stage`, which
        re-checks the prerequisite against the row and lets
        ``ck_pipeline_record_stage_prefix`` remain the backstop.

        **Provenance.** The journey is opened with
        :data:`MATCH_PROVENANCE_SYNTHETIC_COORDINATOR`, never
        :data:`MATCH_PROVENANCE_MATCH_ENGINE`, even when the invitation's batch
        names a ``match_run_id``. A shortlist may suggest a speaker, but what
        pairs *this* speaker with *this* event is a Speaker Connector composing
        an invitation for them -- a coordinator-accepted pairing, which is what
        that value says. ``match-engine`` stays the reserved slot its own
        docstring describes.

        Args:
            owning_unit_id: The unit the caller is authorized in. The invitation
                must belong to it; a journey is never opened under a unit the
                invitation does not name.
            opportunity_event_id: The Event Host's own event. Supplied by the
                caller because ``cba_invitation_batch`` holds only
                ``event_name``/``event_date`` free text and no event id, so
                there is nothing in the invitation to derive it from -- but it
                is verified to name a real event in this tenant before any
                journey is opened against it.
            attendance_id: The ``attendance_record`` this Attended claim cites.
                Optional: a speaker who has confirmed but not yet presented is
                the ordinary state, and omitting it records exactly that.

        Returns:
            A :class:`CbaHandoffOutcome` carrying the row as it now stands, the
            evidence map, and the stages this call itself wrote.

        Raises:
            CbaInvitationNotFoundError: no such invitation in this tenant/unit.
            UnknownOpportunityEventError: ``opportunity_event_id`` names no
                event in this tenant.
            CbaInvitationNotConfirmedError: the invitation does not evidence a
                confirmed speaker. Nothing is written.
            UnknownAttendanceEvidenceError: ``attendance_id`` names no
                attendance record in this tenant.
            CbaAttendanceMismatchError: it names one belonging to another
                subject or another event.
        """
        invitation = self._invitations.get_invitation(
            session, tenant_id=tenant_id, invitation_id=invitation_id
        )
        if invitation is None or invitation.owning_unit_id != owning_unit_id:
            raise CbaInvitationNotFoundError(
                f"no cba_invitation {invitation_id} in tenant {tenant_id} under unit "
                f"{owning_unit_id}"
            )

        self._assert_event_exists(
            session, tenant_id=tenant_id, opportunity_event_id=opportunity_event_id
        )

        # Everything below reads or refuses before the first write, so a refused
        # handoff leaves no partial journey behind.
        evidence = plan_cba_stages(invitation)
        if not any(item.stage is PipelineStage.CONFIRMED for item in evidence):
            raise CbaInvitationNotConfirmedError(
                f"cba_invitation {invitation_id} does not evidence a confirmed speaker "
                f"(status={invitation.status!r}, response_status={invitation.response_status!r}); "
                "an accepted invitation is what supplies the Confirmed stage"
            )

        if attendance_id is not None:
            evidence = (
                *evidence,
                self._attendance_evidence(
                    session,
                    tenant_id=tenant_id,
                    attendance_id=attendance_id,
                    subject_id=invitation.professional_id,
                    opportunity_event_id=opportunity_event_id,
                ),
            )

        record, applied = self._apply(
            session,
            tenant_id=tenant_id,
            owning_unit_id=owning_unit_id,
            subject_id=invitation.professional_id,
            opportunity_event_id=opportunity_event_id,
            evidence=evidence,
            attendance_id=attendance_id,
        )
        return CbaHandoffOutcome(record=record, evidence=evidence, applied=applied)

    def advance_cba_stage(
        self,
        session: Session,
        *,
        tenant_id: uuid.UUID,
        record_id: uuid.UUID,
        stage: PipelineStage,
        reached_at: datetime,
        attended_attendance_id: uuid.UUID | None = None,
    ) -> PipelineStageOutcome:
        """:meth:`PipelineRepository.advance_stage`, refusing ``member_inquiry``.

        The one behavioural difference, and the reason this wrapper exists
        rather than a comment asking callers to remember:
        ``assert_cba_stage_writable`` runs first, so every CBA write path --
        including any future one that does not go through
        :meth:`reconcile_invitation` -- refuses the excluded stage in one place.

        Raises:
            MemberInquiryExcludedError: ``stage`` is ``member_inquiry``. The
                stage remains writable through :class:`PipelineRepository` for
                the pre-CBA product and for the rows that already have one.
        """
        assert_cba_stage_writable(stage)
        return self._pipeline.advance_stage(
            session,
            tenant_id=tenant_id,
            record_id=record_id,
            stage=stage,
            reached_at=reached_at,
            attended_attendance_id=attended_attendance_id,
        )

    # -- reads -----------------------------------------------------------

    def list_confirmed_speakers(
        self,
        session: Session,
        *,
        tenant_id: uuid.UUID,
        owning_unit_id: uuid.UUID,
        opportunity_event_id: uuid.UUID | None = None,
    ) -> tuple[ConfirmedSpeakerRow, ...]:
        """The confirmed speakers this unit can hand an Event Host.

        The ``WHERE`` clause is deliberately the *same predicate* the
        ``pipeline_confirmed`` metric uses -- ``confirmed_at IS NOT NULL``,
        scoped by ``tenant_id`` and ``owning_unit_id`` and nothing else -- so
        with no ``opportunity_event_id`` filter this list and that aggregate are
        the same set by construction rather than by coincidence. That is ADR-0011
        rule 3 held at the query, and
        ``tests/integration/test_cba_confirmed_handoff.py`` compares the two
        numbers rather than trusting this paragraph.

        This is not a second count of the metric. It answers a different
        question -- *which speakers*, with the names an Event Host needs, and
        optionally for one event -- and it never reports a total of its own; the
        aggregate stays the register's to publish through its one owning query.

        The join to ``speaker_profile`` is a ``LEFT`` join and cannot multiply
        rows: that table's primary key is ``(tenant_id, professional_id)``, so
        it contributes at most one row per journey. A speaker with no profile in
        this tenant comes back with ``None`` names rather than being dropped --
        a confirmed speaker the roster has lost track of is exactly the row a
        Host most needs to see.
        """
        profile = schema.speaker_profile
        record = schema.pipeline_record
        where = [
            record.c.tenant_id == tenant_id,
            record.c.owning_unit_id == owning_unit_id,
            record.c.confirmed_at.is_not(None),
        ]
        if opportunity_event_id is not None:
            where.append(record.c.opportunity_event_id == opportunity_event_id)

        rows = session.execute(
            sa.select(
                record.c.id,
                record.c.owning_unit_id,
                record.c.subject_id,
                record.c.opportunity_event_id,
                profile.c.full_name,
                profile.c.company,
                profile.c.title,
                record.c.matched_at,
                record.c.contacted_at,
                record.c.confirmed_at,
                record.c.attended_at,
                record.c.attended_attendance_id,
            )
            .select_from(
                record.outerjoin(
                    profile,
                    sa.and_(
                        profile.c.tenant_id == record.c.tenant_id,
                        profile.c.professional_id == record.c.subject_id,
                    ),
                )
            )
            .where(*where)
            .order_by(record.c.confirmed_at, record.c.id)
        )
        return tuple(
            ConfirmedSpeakerRow(
                record_id=row.id,
                owning_unit_id=row.owning_unit_id,
                professional_id=row.subject_id,
                opportunity_event_id=row.opportunity_event_id,
                full_name=row.full_name,
                company=row.company,
                title=row.title,
                matched_at=row.matched_at,
                contacted_at=row.contacted_at,
                confirmed_at=row.confirmed_at,
                attended_at=row.attended_at,
                attended_attendance_id=row.attended_attendance_id,
            )
            for row in rows
        )

    def evidence_for_invitation(
        self, session: Session, *, tenant_id: uuid.UUID, invitation_id: uuid.UUID
    ) -> tuple[CbaStageEvidence, ...]:
        """The stages one invitation currently evidences, without writing any.

        A read of the same plan :meth:`reconcile_invitation` acts on, so a
        surface can show a Connector why a handoff is not yet possible without
        attempting one and catching the refusal.
        """
        invitation = self._invitations.get_invitation(
            session, tenant_id=tenant_id, invitation_id=invitation_id
        )
        if invitation is None:
            raise CbaInvitationNotFoundError(
                f"no cba_invitation {invitation_id} in tenant {tenant_id}"
            )
        return plan_cba_stages(invitation)

    # -- internals -------------------------------------------------------

    def _assert_event_exists(
        self, session: Session, *, tenant_id: uuid.UUID, opportunity_event_id: uuid.UUID
    ) -> None:
        exists = session.execute(
            sa.select(schema.event.c.id).where(
                schema.event.c.tenant_id == tenant_id,
                schema.event.c.id == opportunity_event_id,
            )
        ).one_or_none()
        if exists is None:
            raise UnknownOpportunityEventError(
                f"event {opportunity_event_id} does not exist in tenant {tenant_id}; "
                "pipeline_record.opportunity_event_id carries no foreign key, so a journey "
                "against an id that names nothing would otherwise be storable"
            )

    def _attendance_evidence(
        self,
        session: Session,
        *,
        tenant_id: uuid.UUID,
        attendance_id: uuid.UUID,
        subject_id: uuid.UUID,
        opportunity_event_id: uuid.UUID,
    ) -> CbaStageEvidence:
        """Read the attendance row and check it is *this* journey's.

        Returns the Attended evidence stamped with the attendance row's own
        ``created_at`` -- when the attendance was recorded, which is the only
        moment this table stores. ``attendance_record`` has no separate
        "attended at", so a caller-supplied one would be an invention.
        """
        row = session.execute(
            sa.select(
                schema.attendance_record.c.subject_id,
                schema.attendance_record.c.event_id,
                schema.attendance_record.c.created_at,
            ).where(
                schema.attendance_record.c.tenant_id == tenant_id,
                schema.attendance_record.c.id == attendance_id,
            )
        ).one_or_none()
        if row is None:
            raise UnknownAttendanceEvidenceError(
                f"attendance_record {attendance_id} does not exist in tenant {tenant_id} — "
                "ck_pipeline_record_attendance_evidence requires real evidence"
            )
        if row.subject_id != subject_id:
            raise CbaAttendanceMismatchError(
                f"attendance_record {attendance_id} belongs to subject {row.subject_id}, "
                f"not to this journey's speaker {subject_id}"
            )
        if row.event_id != opportunity_event_id:
            raise CbaAttendanceMismatchError(
                f"attendance_record {attendance_id} is at event {row.event_id}, not at this "
                f"journey's opportunity {opportunity_event_id}"
            )
        return CbaStageEvidence(
            stage=PipelineStage.ATTENDED,
            kind=CbaStageEvidenceKind.ATTENDANCE_RECORD,
            occurred_at=row.created_at,
        )

    def _apply(
        self,
        session: Session,
        *,
        tenant_id: uuid.UUID,
        owning_unit_id: uuid.UUID,
        subject_id: uuid.UUID,
        opportunity_event_id: uuid.UUID,
        evidence: tuple[CbaStageEvidence, ...],
        attendance_id: uuid.UUID | None,
    ) -> tuple[PipelineRecordRow, tuple[PipelineStage, ...]]:
        """Open the journey, then walk the plan. Writes nothing this call is not sure of."""
        opening, *rest = evidence

        # record_matched conflicts DO NOTHING and returns the resulting row
        # either way, so the row it hands back cannot say whether this call is
        # the one that opened the journey. Asked here instead, before the
        # insert. Under READ COMMITTED a concurrent opener between this read and
        # that insert would make both calls report MATCHED as applied; that is
        # the same window record_matched's own docstring already describes, and
        # it cannot produce a second row -- uq_pipeline_record_subject_opportunity
        # is what guarantees the count, not this flag.
        existed_before = (
            session.execute(
                sa.select(schema.pipeline_record.c.id).where(
                    schema.pipeline_record.c.tenant_id == tenant_id,
                    schema.pipeline_record.c.subject_id == subject_id,
                    schema.pipeline_record.c.opportunity_event_id == opportunity_event_id,
                )
            ).one_or_none()
            is not None
        )

        record = self._pipeline.record_matched(
            session,
            tenant_id=tenant_id,
            owning_unit_id=owning_unit_id,
            subject_id=subject_id,
            opportunity_event_id=opportunity_event_id,
            matched_at=opening.occurred_at,
            matched_provenance=MATCH_PROVENANCE_SYNTHETIC_COORDINATOR,
        )
        applied: list[PipelineStage] = [] if existed_before else [PipelineStage.MATCHED]

        for item in rest:
            outcome = self.advance_cba_stage(
                session,
                tenant_id=tenant_id,
                record_id=record.id,
                stage=item.stage,
                reached_at=item.occurred_at,
                attended_attendance_id=(
                    attendance_id if item.stage is PipelineStage.ATTENDED else None
                ),
            )
            if outcome.record is not None:
                record = outcome.record
            if outcome.transitioned:
                applied.append(item.stage)
        return record, tuple(applied)
