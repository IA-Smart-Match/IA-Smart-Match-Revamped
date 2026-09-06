"""Shared scoring-factor types.

Architecture v1.1 §1.2 / §3.6 R4 and ADR-0011: a matching factor's evidence is
either **absent** (no record exists — the honest answer is "unknown") or
**recorded** (a record exists, and the measured value may legitimately be
``0.0``). These two facts must never collapse into each other. Coercing an
absent record to ``0.0`` is exactly the "N/A becomes zero" defect ADR-0011
exists to forbid: a professional with no expertise record on file is not the
same as one whose recorded expertise verifiably does not overlap the event's
topics, and reporting both as ``0.0`` erases that distinction from every
downstream consumer — the optimizer, the coordinator-facing explanation, and
the professional who might otherwise correct their own record.

Every scoring factor in :mod:`smartmatch_domain.factors` returns a
:class:`FactorScore`: ``value=None`` for absent evidence, a rounded value in
``[0.0, 1.0]`` for a measured one. :attr:`FactorScore.zero_classification`
makes the distinction machine-checkable rather than a convention every caller
must remember.

This package holds only the shared vocabulary. Individual factors (for
example ``topic_relevance``) live in their own modules and import from here;
they do not redefine these types.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Final

__all__ = [
    "FACTOR_SCORE_PRECISION",
    "EvidenceState",
    "FactorScore",
    "FactorState",
    "ZeroClassification",
]

#: Decimal places every factor value is rounded to before it leaves a factor.
FACTOR_SCORE_PRECISION: Final[int] = 4


class ZeroClassification(StrEnum):
    """ADR-0011: an unknown and a measured zero are different facts."""

    MEASURED_ZERO = "measured_zero"
    UNKNOWN = "unknown"


class EvidenceState(StrEnum):
    """Whether the underlying record exists at all."""

    ABSENT = "absent"
    RECORDED = "recorded"


class FactorState(StrEnum):
    """ADR-0016 Proposal 1's three evidence states, as a discriminator.

    The two-state world above — a value, or a null meaning unknown — could not
    say what customer §9 needed said. There are two different reasons a factor
    can have no measurement, and only one of them is an unknown:

    ``MEASURED``
        The comparison ran against real evidence and produced a number. A
        ``0.0`` here is a **measured zero**: a real claim, and it must stay
        distinguishable from both states below.
    ``POLICY_NEUTRAL``
        The record **was read** and carries no usable evidence. That is an
        *observed absence*, and the customer has a stated policy for what one
        is worth. It carries a value, it carries the policy's identifier, and
        it **participates in scoring**.
    ``UNKNOWN``
        The evidence **could not be evaluated**. ADR-0011 rule 1 in full:
        ``None``, never ``0.0``, and the composite is unscorable.

    Only ``UNKNOWN`` makes a composite unscorable, and unknown dominates: a
    candidate with both an unknown factor and a policy-neutral one is unknown.
    This *refines* ADR-0011 by naming a case rule 1 never covered; it does not
    amend, weaken, or supersede it.

    The member values are identical to
    :class:`smartmatch_domain.factors.cba_semantic_topic.TopicEvidenceState`'s
    and to :class:`smartmatch_domain.explanation.ScoreState`'s, and
    ``tests/unit/test_scoring.py`` asserts that rather than trusting it: three
    enums that must serialize alike are three chances for one of them to drift.
    """

    MEASURED = "measured"
    POLICY_NEUTRAL = "policy_neutral"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class FactorScore:
    """One factor's contribution, or its explicit absence.

    Attributes:
        factor_key: Registry key. Must match a key in ``factor_keys()``.
        value: Score in ``[0.0, 1.0]``, or ``None`` when the evidence is
            absent. ``None`` is unknown and is never coerced to ``0.0``.
        basis: Human-readable provenance for the number, non-empty.
        estimate_label: Set when the value is an explicitly coarse estimate,
            otherwise ``None``.
        policy_id: The stable identifier of the customer policy that supplied
            this value, set when and only when the score is
            :attr:`FactorState.POLICY_NEUTRAL`. A neutral value with no policy
            attached is indistinguishable in storage from a measured one, which
            would be ADR-0011's defect in a new costume — so this field is what
            *makes* a score policy-neutral rather than a flag beside it.
        policy_version: That policy's version, required alongside
            :attr:`policy_id` so an older stored run is never re-read under a
            newer policy.
    """

    factor_key: str
    value: float | None
    basis: str
    estimate_label: str | None = None
    policy_id: str | None = None
    policy_version: str | None = None

    def __post_init__(self) -> None:
        if self.value is not None and not 0.0 <= self.value <= 1.0:
            raise ValueError(
                f"{self.factor_key}: value must be in [0.0, 1.0] or None, got {self.value!r}"
            )
        if not self.basis.strip():
            raise ValueError(f"{self.factor_key}: basis must be a non-empty, non-blank string")
        if (self.policy_id is None) != (self.policy_version is None):
            raise ValueError(
                f"{self.factor_key}: policy_id and policy_version must be set or unset "
                f"together; got {self.policy_id!r} and {self.policy_version!r}. A policy "
                "value whose version is unrecoverable cannot be re-read under the policy "
                "that produced it."
            )
        if self.policy_id is not None and self.value is None:
            raise ValueError(
                f"{self.factor_key}: a policy value must carry a value; got None. A policy "
                "the system could not apply is an unknown, and an unknown has no policy."
            )

    @property
    def state(self) -> FactorState:
        """Which of ADR-0016's three states this score is in.

        Derived rather than stored, so the discriminator and the fields it
        describes cannot disagree: ``policy_id`` is what a policy value has and
        nothing else does, and ``value is None`` is what an unknown has. A
        stored fourth field could contradict both.
        """
        if self.value is None:
            return FactorState.UNKNOWN
        if self.policy_id is not None:
            return FactorState.POLICY_NEUTRAL
        return FactorState.MEASURED

    @property
    def is_unknown(self) -> bool:
        """Whether the evidence behind this factor could not be evaluated.

        Unchanged in meaning by ADR-0016: a policy-neutral score is **not**
        unknown, because the absence it describes was observed rather than
        merely encountered. Every existing caller that branches on this keeps
        the behaviour it had.
        """
        return self.value is None

    @property
    def is_scorable(self) -> bool:
        """Whether this factor can take part in a composite.

        ``True`` for ``MEASURED`` and for ``POLICY_NEUTRAL`` — ADR-0016's
        central consequence is that a policy value participates in scoring.
        ``False`` only for ``UNKNOWN``, which keeps today's behaviour exactly:
        the composite becomes ``None`` and weights are never re-spread.
        """
        return self.value is not None

    @property
    def zero_classification(self) -> ZeroClassification | None:
        """``UNKNOWN`` for ``None``, ``MEASURED_ZERO`` for a measured ``0.0``.

        A policy-neutral score is neither: it is not zero, so it has no zero to
        classify, and it was not measured, so calling its value a measured
        anything would be the mislabelling this whole type exists to prevent.
        """
        if self.value is None:
            return ZeroClassification.UNKNOWN
        if self.policy_id is not None:
            return None
        if self.value == 0.0:
            return ZeroClassification.MEASURED_ZERO
        return None
