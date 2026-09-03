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
    """

    factor_key: str
    value: float | None
    basis: str
    estimate_label: str | None = None

    def __post_init__(self) -> None:
        if self.value is not None and not 0.0 <= self.value <= 1.0:
            raise ValueError(
                f"{self.factor_key}: value must be in [0.0, 1.0] or None, got {self.value!r}"
            )
        if not self.basis.strip():
            raise ValueError(f"{self.factor_key}: basis must be a non-empty, non-blank string")

    @property
    def is_unknown(self) -> bool:
        """Whether the evidence behind this factor is absent."""
        return self.value is None

    @property
    def zero_classification(self) -> ZeroClassification | None:
        """``UNKNOWN`` for ``None``, ``MEASURED_ZERO`` for ``0.0``, else ``None``."""
        if self.value is None:
            return ZeroClassification.UNKNOWN
        if self.value == 0.0:
            return ZeroClassification.MEASURED_ZERO
        return None
