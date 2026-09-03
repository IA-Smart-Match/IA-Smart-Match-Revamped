"""`match_depth` derived display quantity.

Architecture v1.1 §1.2 / ADR-0011. **`match_depth` is a derived display
quantity computed from engagement history. It is NOT a registry factor,
carries no weight, and must never be added to
``smartmatch_domain.factor_registry.PROPOSED_FACTORS``.** It exists solely so
a coordinator-facing explanation can state how many times a professional has
already engaged with a unit, distinguishing "no engagement history record
exists for this subject and unit" (unknown) from "a history record exists
and it is empty" (measured zero) — the ADR-0011 distinction the legacy UI
destroyed by rendering both facts as the same "0".

``G1-GC-003``, ``G1-GC-007`` and ``G1-GC-008`` exercise this module as a
derived quantity, not as a scorer: they assert what :func:`derive_match_depth`
returns for absent, empty, and populated engagement history, never that it
contributes to a Stage B score.
"""

from __future__ import annotations

from dataclasses import dataclass

from smartmatch_domain.factors import ZeroClassification

__all__ = [
    "EngagementHistoryEvidence",
    "MatchDepth",
    "derive_match_depth",
]


@dataclass(frozen=True, slots=True)
class EngagementHistoryEvidence:
    """Raw engagement history for one (professional, unit) pair.

    Attributes:
        subject_id: Stable identifier for the professional. Non-empty.
        unit_id: Stable identifier for the unit (event/organization) the
            professional has or has not engaged with. Non-empty.
        engagement_ids: The recorded engagement ids, or ``None`` when no
            engagement history record exists for this subject and unit at
            all. ``None`` and ``()`` are deliberately different: ``None``
            means the record is absent (unknown), ``()`` means the record
            exists and is empty (measured, and measurably zero).
    """

    subject_id: str
    unit_id: str
    engagement_ids: tuple[str, ...] | None

    def __post_init__(self) -> None:
        if not self.subject_id.strip():
            raise ValueError("subject_id: must not be empty or blank")
        if not self.unit_id.strip():
            raise ValueError("unit_id: must not be empty or blank")


@dataclass(frozen=True, slots=True)
class MatchDepth:
    """A derived display quantity: how many times a subject has engaged a unit.

    Never a registry factor — see the module docstring. Constructed only by
    :func:`derive_match_depth`.

    Attributes:
        subject_id: Stable identifier for the professional. Non-empty.
        unit_id: Stable identifier for the unit. Non-empty.
        count: Number of recorded engagements, or ``None`` when no engagement
            history record exists (unknown). ``None`` is never coerced to
            ``0``.
        basis: Human-readable provenance for ``count``. Non-empty.
    """

    subject_id: str
    unit_id: str
    count: int | None
    basis: str

    def __post_init__(self) -> None:
        if not self.subject_id.strip():
            raise ValueError("subject_id: must not be empty or blank")
        if not self.unit_id.strip():
            raise ValueError("unit_id: must not be empty or blank")
        if self.count is not None and self.count < 0:
            raise ValueError(f"count: must be non-negative or None, got {self.count!r}")
        if not self.basis.strip():
            raise ValueError("basis: must not be empty or blank")

    @property
    def is_unknown(self) -> bool:
        """Whether no engagement history record exists for this pair."""
        return self.count is None

    @property
    def zero_classification(self) -> ZeroClassification | None:
        """``UNKNOWN`` for ``None``, ``MEASURED_ZERO`` for ``0``, else ``None``."""
        if self.count is None:
            return ZeroClassification.UNKNOWN
        if self.count == 0:
            return ZeroClassification.MEASURED_ZERO
        return None


def derive_match_depth(evidence: EngagementHistoryEvidence) -> MatchDepth:
    """Derive the `match_depth` display quantity from engagement history.

    Args:
        evidence: The raw engagement history for one (professional, unit)
            pair.

    Returns:
        A :class:`MatchDepth`. ``count`` is ``None`` when
        ``evidence.engagement_ids`` is ``None`` (no history record exists —
        unknown, per ADR-0011); ``0`` when it is an empty tuple (a history
        record exists and is empty — measured zero); otherwise the number of
        recorded engagement ids.

    Raises:
        ValueError: if ``evidence.engagement_ids`` contains a duplicate
            engagement id.
    """
    if evidence.engagement_ids is None:
        return MatchDepth(
            evidence.subject_id,
            evidence.unit_id,
            None,
            basis="no engagement history record for this subject and unit",
        )

    if evidence.engagement_ids == ():
        return MatchDepth(
            evidence.subject_id,
            evidence.unit_id,
            0,
            basis="engagement history recorded and empty for this unit",
        )

    engagement_ids = evidence.engagement_ids
    if len(set(engagement_ids)) != len(engagement_ids):
        raise ValueError(
            f"engagement_ids: duplicate engagement id in history for "
            f"subject={evidence.subject_id!r} unit={evidence.unit_id!r}"
        )

    count = len(engagement_ids)
    return MatchDepth(
        evidence.subject_id,
        evidence.unit_id,
        count,
        basis=f"{count} recorded engagements with this unit",
    )
