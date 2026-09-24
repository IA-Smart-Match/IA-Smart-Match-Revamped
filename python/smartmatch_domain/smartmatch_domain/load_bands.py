"""The registry-side wrapper around ELI 2.0.0's band table (B26 T8c).

:mod:`smartmatch_domain.eli` owns the arithmetic: the window, the band edges
and :data:`~smartmatch_domain.eli.Q7_LOAD_BAND_TABLE`. This module owns what the
*registry* needs to say about that table and never edits T8b's types:

* **Ownership.** :class:`LoadBandOwnership` records who decided the bands, when,
  under which decision, and whether IA West has reviewed them. It is not hashed:
  approval must not move a ``registry_hash``.
* **Hash coverage.** :func:`canonical_load_bands` renders the cut points, the
  multipliers and the ELI formula version so a 3.x ``registry_hash`` covers them
  (ADR-0027). Every ``Decimal`` is normalised, so ``0.5`` and ``0.50`` hash alike.
* **One run, one date.** :func:`assess_pool_loads` runs ``compute_eli`` once per
  subject against one ``as_of``, and never invents a capacity (Q6).
* **Stage A.** :func:`stage_a_load_excluded` is true for Full only: a Full pair is
  removed before the solve and never scored.

Nothing here makes registry 3.0.0 current. It is declared ``proposed`` in
:mod:`smartmatch_domain.factor_registry`.
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from types import MappingProxyType
from typing import Any, Final

from smartmatch_domain.eli import (
    ELI_FORMULA_VERSION,
    Q7_LOAD_BAND_TABLE,
    Engagement,
    LoadAssessment,
    LoadBand,
    LoadBandTable,
    LoadInputs,
    compute_eli,
)

__all__ = [
    "ENGAGEMENT_LOAD_FACTOR_KEY",
    "Q7_REGISTERED_LOAD_BANDS",
    "AssessedLoad",
    "LoadBandOwnership",
    "LoadReviewStatus",
    "RegisteredLoadBands",
    "assess_pool_loads",
    "assessed_load_payload",
    "canonical_decimal",
    "canonical_load_bands",
    "stage_a_load_excluded",
]

#: The registry key of the load penalty. Declared only by registry 3.0.0.
ENGAGEMENT_LOAD_FACTOR_KEY: Final[str] = "engagement_load"


class LoadReviewStatus(StrEnum):
    """Whether IA West has reviewed the band table (parent plan §10 row 3)."""

    PENDING_IA_WEST_REVIEW = "pending_ia_west_review"
    REVIEWED = "reviewed"


def _require_text(value: object, name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-blank string")


@dataclass(frozen=True, slots=True)
class LoadBandOwnership:
    """Who decided a band table, when, and under which decision.

    Attributes:
        decided_by: The accountable person and role.
        decided_on: The decision date, as an ISO ``YYYY-MM-DD`` string.
        decision: The decision's name, e.g. ``"B26 Q7 = A (parent plan §9)"``.
        review_status: Whether IA West has reviewed the table.
    """

    decided_by: str
    decided_on: str
    decision: str
    review_status: LoadReviewStatus

    def __post_init__(self) -> None:
        _require_text(self.decided_by, "decided_by")
        _require_text(self.decided_on, "decided_on")
        _require_text(self.decision, "decision")
        try:
            parsed = date.fromisoformat(self.decided_on)
        except ValueError as error:
            raise ValueError(f"decided_on must be an ISO date, got {self.decided_on!r}") from error
        if parsed.isoformat() != self.decided_on:
            raise ValueError(f"decided_on must be written YYYY-MM-DD, got {self.decided_on!r}")
        if not isinstance(self.review_status, LoadReviewStatus):
            raise TypeError(
                f"review_status must be a LoadReviewStatus, got {type(self.review_status).__name__}"
            )


@dataclass(frozen=True, slots=True)
class RegisteredLoadBands:
    """T8b's band table as a registry holds it.

    Attributes:
        table: T8b's :class:`~smartmatch_domain.eli.LoadBandTable`, used as-is.
        eli_formula_version: The ELI formula the table was declared against. The
            same numbers under another formula are another rule, so it is hashed.
        ownership: Who decided the table. Not hashed (see the module docstring).
    """

    table: LoadBandTable
    eli_formula_version: str
    ownership: LoadBandOwnership

    def __post_init__(self) -> None:
        if not isinstance(self.table, LoadBandTable):
            raise TypeError(f"table must be a LoadBandTable, got {type(self.table).__name__}")
        _require_text(self.eli_formula_version, "eli_formula_version")
        if not isinstance(self.ownership, LoadBandOwnership):
            raise TypeError(
                f"ownership must be a LoadBandOwnership, got {type(self.ownership).__name__}"
            )


#: The Q7 = A table, owned by the program owner of record, pending IA West review.
Q7_REGISTERED_LOAD_BANDS: Final[RegisteredLoadBands] = RegisteredLoadBands(
    table=Q7_LOAD_BAND_TABLE,
    eli_formula_version=ELI_FORMULA_VERSION,
    ownership=LoadBandOwnership(
        decided_by="Danny Tran, Development Lead / program owner of record",
        decided_on="2026-09-22",
        decision="B26 Q7 = A (parent plan §9)",
        review_status=LoadReviewStatus.PENDING_IA_WEST_REVIEW,
    ),
)


def canonical_decimal(value: Decimal) -> str:
    """Render a ``Decimal`` without trailing zeros or an exponent.

    ``Decimal("0.50")`` and ``Decimal("0.5")`` are equal and both render
    ``"0.5"``; ``Decimal("1.00")`` renders ``"1"``.
    """
    return format(value.normalize(), "f")


def canonical_load_bands(bands: RegisteredLoadBands) -> dict[str, object]:
    """The part of a band table a 3.x ``registry_hash`` covers.

    In: cut points, multipliers, ELI formula version. Out: ownership and review
    status, so approving the table never moves a hash.
    """
    table = bands.table
    return {
        "eli_formula_version": bands.eli_formula_version,
        "full_above": canonical_decimal(table.full_above),
        "heavy_from": canonical_decimal(table.heavy_from),
        "moderate_from": canonical_decimal(table.moderate_from),
        "multipliers": {
            str(band.value): canonical_decimal(multiplier)
            for band, multiplier in sorted(table.multipliers.items(), key=lambda item: item[0])
        },
    }


@dataclass(frozen=True, slots=True)
class AssessedLoad:
    """One subject's load, as a run assessed it.

    Attributes:
        as_of: The run's UTC date. One value per run.
        assessment: T8b's output, unmodified.
    """

    as_of: date
    assessment: LoadAssessment

    def __post_init__(self) -> None:
        if not isinstance(self.as_of, date) or isinstance(self.as_of, datetime):
            raise TypeError(f"as_of must be a date (not a datetime), got {type(self.as_of)}")
        if not isinstance(self.assessment, LoadAssessment):
            raise TypeError(
                f"assessment must be a LoadAssessment, got {type(self.assessment).__name__}"
            )


def assess_pool_loads(
    subject_ids: Sequence[uuid.UUID],
    *,
    capacities: Mapping[uuid.UUID, Decimal | None],
    engagements: Mapping[uuid.UUID, tuple[Engagement, ...]],
    as_of: date,
    bands: RegisteredLoadBands,
) -> Mapping[uuid.UUID, AssessedLoad]:
    """Assess every named subject's load against one ``as_of``.

    Args:
        subject_ids: The subjects to assess, each once.
        capacities: Declared capacity per 90 days. An absent key or ``None`` is
            an unstated capacity, so the band is Unknown; never a default (Q6).
        engagements: Each subject's engagements. An absent key is none.
        as_of: The run's UTC date, shared by every subject.
        bands: The registry's band table.

    Returns:
        A read-only mapping of subject to :class:`AssessedLoad`.

    Raises:
        ValueError: when a subject is named twice.
    """
    if len(set(subject_ids)) != len(subject_ids):
        raise ValueError("subject_ids: duplicate subject in assess_pool_loads")
    loads: dict[uuid.UUID, AssessedLoad] = {}
    for subject in subject_ids:
        inputs = LoadInputs(
            as_of=as_of,
            engagements=tuple(engagements.get(subject, ())),
            declared_capacity_hours=capacities.get(subject),
        )
        loads[subject] = AssessedLoad(as_of=as_of, assessment=compute_eli(inputs, bands.table))
    return MappingProxyType(loads)


def stage_a_load_excluded(load: AssessedLoad | None) -> bool:
    """Whether Stage A removes the pair: Full only, and never without a load."""
    return load is not None and load.assessment.band is LoadBand.FULL


def _decimal_text(value: Decimal | None) -> str | None:
    return None if value is None else str(value)


def assessed_load_payload(load: AssessedLoad) -> dict[str, Any]:
    """Render a load as the JSON block a run payload stores.

    Decimals are strings so nothing rounds on the way to JSON. This is the
    ``excluded[].load`` block, and the explanation ``load`` block less its
    ``multiplier`` and ``composite_before_load``. ``unknown_hours_refs`` stays in
    the stored payload; the API view drops it.
    """
    assessment = load.assessment
    return {
        "band": assessment.band.value,
        "reason": assessment.reason.value,
        "measurable": assessment.measurable,
        "completed_hours": str(assessment.completed_hours),
        "confirmed_hours": str(assessment.confirmed_hours),
        "capacity_hours": _decimal_text(assessment.capacity_hours),
        "utilization": _decimal_text(assessment.utilization),
        "unknown_hours_refs": list(assessment.unknown_hours_refs),
        "as_of": load.as_of.isoformat(),
        "eli_formula_version": assessment.formula_version,
    }
