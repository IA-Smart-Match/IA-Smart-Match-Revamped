"""The S12 funnel's stage sequence (P8 card O2 app writers) — pure rules, no storage.

Migration ``0011`` (P8 card O2) gave the five Pipeline metrics an evidence
table, ``pipeline_record``, and its two CHECK constraints —
``ck_pipeline_record_stage_prefix`` and ``ck_pipeline_record_stage_order`` —
are the database's own statement of "a funnel that widens is an incoherent
number" (see that migration's docstring). This module is the same rule,
expressed once as data, so a persistence-layer writer can refuse an
out-of-order stage claim *before* issuing a statement the database would
reject anyway — the identical split ``smartmatch_domain.jobs`` already makes
for job-state transitions: ``JobRepository`` calls ``assert_transition``
first, and the database's own CHECK/constraint machinery is what still holds
the line if that call were ever skipped or wrong.

**Nothing in this repository calls the persistence writer this module backs
yet.** Plan `docs/plans/2026-08-28-opportunities-s12-plan.md` states a
standing constraint that applies to this exact table: "No matcher actions
before G1." G1 (plan P5, M1–M10 matching) has not closed
(`docs/status-report/2026-09-02-audit-status-report.md` §5), so nothing in
this codebase originates a genuine "subject X matched to opportunity Y"
event yet — professionals additionally have no persisted identity of their
own to be that subject (`professional_unit_relationship`'s own column
comment, migration `0012`). This module and
``smartmatch_persistence.pipeline.PipelineRepository`` are the write-path
infrastructure card O2's follow-on asked for, ready for the caller that adds
a real match; they intentionally have none yet, because writing one now
would be exactly the fabricated-evidence defect ADR-0011 exists to prevent.
"""

from __future__ import annotations

from collections.abc import Mapping, Set
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from types import MappingProxyType
from typing import Final, Protocol

__all__ = [
    "CBA_EXCLUDED_STAGES",
    "CBA_STAGE_EVIDENCE_KIND",
    "CBA_STAGE_SEQUENCE",
    "PIPELINE_STAGE_SEQUENCE",
    "CbaStageEvidence",
    "CbaStageEvidenceKind",
    "InvalidPipelineStageTransitionError",
    "InvitationEvidence",
    "MemberInquiryExcludedError",
    "PipelineStage",
    "assert_cba_stage_writable",
    "assert_stage_reachable",
    "is_cba_reportable_stage",
    "plan_cba_stages",
    "prerequisite_stage",
]


class PipelineStage(StrEnum):
    """The five funnel stages, in the order ``pipeline_record`` requires them.

    Spelled without the ``_at`` suffix ``pipeline_record``'s own columns
    carry (``matched_at``, ``contacted_at``, ...): this enum names the
    *stage*, a domain concept with no storage shape of its own — the ``_at``
    suffix is how the persistence layer's columns store the moment a stage
    was reached, not part of the stage's identity.
    """

    MATCHED = "matched"
    CONTACTED = "contacted"
    CONFIRMED = "confirmed"
    ATTENDED = "attended"
    MEMBER_INQUIRY = "member_inquiry"


#: The funnel in order — the same order the register's five metrics
#: (`smartmatch_domain.metrics.METRIC_REGISTER`) and migration ``0011``'s
#: ``STAGES`` tuple in `tests/integration/test_pipeline_record_constraints.py`
#: both walk.
PIPELINE_STAGE_SEQUENCE: Final[tuple[PipelineStage, ...]] = (
    PipelineStage.MATCHED,
    PipelineStage.CONTACTED,
    PipelineStage.CONFIRMED,
    PipelineStage.ATTENDED,
    PipelineStage.MEMBER_INQUIRY,
)

#: Each stage's immediate predecessor, or ``None`` for ``MATCHED`` — the
#: entry stage, satisfied by construction (``pipeline_record`` has no row
#: without it; migration ``0011``'s ``matched_at`` is ``NOT NULL``).
#: Transcribed one-for-one from ``ck_pipeline_record_stage_prefix``'s four
#: clauses, so a reader checking this mapping against the constraint is
#: checking it against the same rule rather than a restatement of it.
_PREREQUISITE: Final[Mapping[PipelineStage, PipelineStage | None]] = MappingProxyType(
    {
        PipelineStage.MATCHED: None,
        PipelineStage.CONTACTED: PipelineStage.MATCHED,
        PipelineStage.CONFIRMED: PipelineStage.CONTACTED,
        PipelineStage.ATTENDED: PipelineStage.CONFIRMED,
        PipelineStage.MEMBER_INQUIRY: PipelineStage.ATTENDED,
    }
)


class InvalidPipelineStageTransitionError(ValueError):
    """A stage was claimed reached without its prerequisite.

    A ``ValueError`` subclass, not a bare ``ValueError``: a caller (a future
    matching writer, or this module's own tests) that wants to catch exactly
    this refusal — as opposed to any other invalid argument — has a type to
    catch, the same distinction ``IdempotencyConflictError`` and
    ``RedriveConflictError`` already draw for their own repositories.
    """


def prerequisite_stage(stage: PipelineStage) -> PipelineStage | None:
    """The stage that must already be reached before ``stage`` may be.

    ``None`` only for :attr:`PipelineStage.MATCHED`.
    """
    return _PREREQUISITE[stage]


def assert_stage_reachable(reached: Set[PipelineStage], target: PipelineStage) -> None:
    """Raise unless ``target``'s prerequisite is already in ``reached``.

    Mirrors ``ck_pipeline_record_stage_prefix`` (migration ``0011``): a stage
    is reachable only if the one before it was. ``target`` itself already
    being in ``reached`` is not this function's concern — a caller re-writing
    a stage that was already reached is a different question (whether that is
    a no-op, a conflict, or an error is the writer's call to make, the same
    way ``ReviewRepository.decide`` — not ``smartmatch_domain.jobs`` — decides
    what a repeated decision means) — so this function only ever refuses a
    stage whose prerequisite is missing.

    Args:
        reached: Every stage the journey has already reached.
        target: The stage a caller wants to record next.

    Raises:
        InvalidPipelineStageTransitionError: ``target``'s prerequisite is not
            in ``reached``.
    """
    prerequisite = _PREREQUISITE[target]
    if prerequisite is not None and prerequisite not in reached:
        raise InvalidPipelineStageTransitionError(
            f"{target.value} cannot be reached before {prerequisite.value} "
            f"(reached so far: {sorted(s.value for s in reached)})"
        )


# ---------------------------------------------------------------------------
# The CBA speaker handoff (track CBA-HANDOFF-PIPELINE)
# ---------------------------------------------------------------------------
#
# Everything above this line is the *whole* funnel, exactly as migration
# ``0011`` stores it, and nothing below narrows it: ``PipelineStage`` still has
# five members, ``PIPELINE_STAGE_SEQUENCE`` still walks all five, and
# ``_PREREQUISITE`` still names ``member_inquiry``'s. The stage, its column,
# its CHECK constraints and every row already written stay exactly as they are.
#
# What is added below is the *CBA product's* view of that funnel, which is the
# same sequence with ``member_inquiry`` removed. ``Capability.MEMBER_INQUIRY_NARRATIVE``
# (``smartmatch_domain.product_scope``) already states the policy in as many
# words -- "The stored stage and its history are preserved; CBA has no approved
# equivalent outcome, so the narrative and its tile are not offered and no CBA
# writer may produce one" -- and is ``False`` under ``ProductScope.CBA``. This
# section is the "no CBA writer may produce one" half expressed as code a
# writer can call, so the refusal happens in one place instead of being
# re-derived by every caller that touches a stage.


class MemberInquiryExcludedError(ValueError):
    """A CBA writer tried to produce a ``member_inquiry`` stage.

    A ``ValueError`` subclass for the reason
    :class:`InvalidPipelineStageTransitionError` gives: a caller that wants to
    catch exactly this refusal -- as opposed to any other invalid stage
    argument -- has a type to catch.

    Deliberately **not** raised by :func:`assert_stage_reachable` or by the
    general stage writer. ``member_inquiry`` remains a writable stage of the
    schema and of the pre-CBA product; what this error marks is a *CBA*
    surface attempting it, which the ratified capability policy forbids.
    """


#: The stages the CBA product does not write or display. One member, and the
#: single place the exclusion is stated: everything else derives from it.
CBA_EXCLUDED_STAGES: Final[frozenset[PipelineStage]] = frozenset({PipelineStage.MEMBER_INQUIRY})

#: The funnel the CBA product reports, in order: :data:`PIPELINE_STAGE_SEQUENCE`
#: without :data:`CBA_EXCLUDED_STAGES`. Derived by filtering rather than
#: retyped, so a change to the funnel's order cannot leave the two disagreeing
#: about it -- only about which stages are in scope, which is the one fact
#: :data:`CBA_EXCLUDED_STAGES` states.
CBA_STAGE_SEQUENCE: Final[tuple[PipelineStage, ...]] = tuple(
    stage for stage in PIPELINE_STAGE_SEQUENCE if stage not in CBA_EXCLUDED_STAGES
)


def is_cba_reportable_stage(stage: PipelineStage) -> bool:
    """Whether the CBA product writes and displays ``stage``."""
    return PipelineStage(stage) not in CBA_EXCLUDED_STAGES


def assert_cba_stage_writable(stage: PipelineStage) -> None:
    """Raise unless a CBA writer may produce ``stage``.

    Raises:
        MemberInquiryExcludedError: ``stage`` is
            :attr:`PipelineStage.MEMBER_INQUIRY`.
    """
    coerced = PipelineStage(stage)
    if not is_cba_reportable_stage(coerced):
        raise MemberInquiryExcludedError(
            f"{coerced.value} is not a CBA funnel outcome: the stage, its column and "
            "every row already written are preserved, but no CBA writer may produce "
            "one (Capability.MEMBER_INQUIRY_NARRATIVE is False under ProductScope.CBA)"
        )


class CbaStageEvidenceKind(StrEnum):
    """What kind of stored fact supports one CBA stage claim.

    A closed vocabulary rather than free text, and deliberately sharing no
    value with ``matched_provenance``: provenance says where a **match** came
    from, this says which stored fact makes a **stage** true. Naming them alike
    would invite a writer to put one where the other belongs -- the same
    disjointness track 20 enforces between a Speaker's answer and a provider's
    delivery disposition.
    """

    #: A Speaker Connector composed an invitation naming this speaker for this
    #: event -- ``cba_invitation.created_at``, the pairing act itself.
    INVITATION_COMPOSED = "invitation_composed"
    #: The invitation was submitted for delivery -- ``cba_invitation.dispatched_at``,
    #: which ``ck_cba_invitation_dispatched`` makes inseparable from a real send job.
    INVITATION_DISPATCHED = "invitation_dispatched"
    #: The **Speaker** said yes -- ``response_status = 'accepted_invitation'``.
    #: Never a delivery disposition: a provider taking custody of bytes is not a
    #: person agreeing to speak.
    INVITATION_ACCEPTED = "invitation_accepted"
    #: A real ``attendance_record`` row, which is also what
    #: ``ck_pipeline_record_attendance_evidence`` requires the row to cite.
    ATTENDANCE_RECORD = "attendance_record"


#: The one evidence kind each CBA stage is reached by. One entry per member of
#: :data:`CBA_STAGE_SEQUENCE` and no entry for ``member_inquiry`` -- a stage
#: with no admissible evidence is a stage no evidence-checked writer can reach,
#: which is the exclusion expressed as data rather than as a second rule.
CBA_STAGE_EVIDENCE_KIND: Final[Mapping[PipelineStage, CbaStageEvidenceKind]] = MappingProxyType(
    {
        PipelineStage.MATCHED: CbaStageEvidenceKind.INVITATION_COMPOSED,
        PipelineStage.CONTACTED: CbaStageEvidenceKind.INVITATION_DISPATCHED,
        PipelineStage.CONFIRMED: CbaStageEvidenceKind.INVITATION_ACCEPTED,
        PipelineStage.ATTENDED: CbaStageEvidenceKind.ATTENDANCE_RECORD,
    }
)


@dataclass(frozen=True, slots=True)
class CbaStageEvidence:
    """One stage, the moment it was reached, and the fact that says so.

    Frozen and validated on construction: an instance cannot exist for a stage
    the CBA product does not write, nor pair a stage with an evidence kind that
    does not support it. A caller therefore never has to re-check either.
    """

    stage: PipelineStage
    kind: CbaStageEvidenceKind
    occurred_at: datetime

    def __post_init__(self) -> None:
        assert_cba_stage_writable(self.stage)
        expected = CBA_STAGE_EVIDENCE_KIND[self.stage]
        if self.kind is not expected:
            raise ValueError(
                f"{self.stage.value} is evidenced by {expected.value}, not {self.kind.value}"
            )
        if self.occurred_at.tzinfo is None:
            raise ValueError(
                "occurred_at must be timezone-aware -- a naive datetime can silently "
                "violate ck_pipeline_record_stage_order against a timestamptz column"
            )


class InvitationEvidence(Protocol):
    """The five ``cba_invitation`` fields a stage plan reads.

    A ``Protocol``, not an import of
    ``smartmatch_persistence.cba_invitations.InvitationRow``: the domain
    package may not reach storage (ADR-0002), and this is the same structural
    boundary ``smartmatch_domain.cba_invitations.ChannelFacts`` already draws
    for the same reason.
    """

    @property
    def status(self) -> str: ...

    @property
    def response_status(self) -> str: ...

    @property
    def created_at(self) -> datetime: ...

    @property
    def dispatched_at(self) -> datetime | None: ...

    @property
    def response_recorded_at(self) -> datetime | None: ...


def plan_cba_stages(invitation: InvitationEvidence) -> tuple[CbaStageEvidence, ...]:
    """The stages ``invitation`` currently evidences, in funnel order.

    Pure, total, and a *prefix* of :data:`CBA_STAGE_SEQUENCE` by construction:
    never a later stage without the one before it, because each is appended
    only after its predecessor was. That is the rule
    ``ck_pipeline_record_stage_prefix`` states, applied before a statement is
    issued rather than after one is refused.

    ``attended`` is never planned here. Attendance is a fact of a different
    table -- ``attendance_record``, which the row must also *cite* -- and an
    invitation says nothing about whether anybody turned up. A plan that
    inferred it from an acceptance would be exactly the fabricated evidence
    ADR-0011 exists to prevent.

    A skipped invitation plans **nothing at all**, not even ``matched``:
    ``ck_cba_invitation_addressed`` means a skipped row names no channel and no
    draft, so it records a recipient the Connector was told not to write to
    rather than a speaker paired with an event.

    Returns:
        Zero to three :class:`CbaStageEvidence` values, ordered
        ``matched``, ``contacted``, ``confirmed``.
    """
    if invitation.status == "skipped":
        return ()

    plan: list[CbaStageEvidence] = [
        CbaStageEvidence(
            stage=PipelineStage.MATCHED,
            kind=CbaStageEvidenceKind.INVITATION_COMPOSED,
            occurred_at=invitation.created_at,
        )
    ]

    dispatched_at = invitation.dispatched_at
    if invitation.status != "dispatched" or dispatched_at is None:
        return tuple(plan)
    plan.append(
        CbaStageEvidence(
            stage=PipelineStage.CONTACTED,
            kind=CbaStageEvidenceKind.INVITATION_DISPATCHED,
            occurred_at=dispatched_at,
        )
    )

    accepted_at = invitation.response_recorded_at
    if invitation.response_status != "accepted_invitation" or accepted_at is None:
        return tuple(plan)
    plan.append(
        CbaStageEvidence(
            stage=PipelineStage.CONFIRMED,
            kind=CbaStageEvidenceKind.INVITATION_ACCEPTED,
            occurred_at=accepted_at,
        )
    )
    return tuple(plan)
