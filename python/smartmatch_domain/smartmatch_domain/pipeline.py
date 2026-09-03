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
from enum import StrEnum
from types import MappingProxyType
from typing import Final

__all__ = [
    "PIPELINE_STAGE_SEQUENCE",
    "InvalidPipelineStageTransitionError",
    "PipelineStage",
    "assert_stage_reachable",
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
