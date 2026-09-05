"""Industry Match scoring factor.

Customer §7 gives each speaker **one primary** NAICS sector and lets a Speaker
Request target **several** ("Do not restrict an event request to one
industry"). So this factor is a membership test — is the speaker's one sector
among the sectors the request named? — and not a set-overlap ratio. There is
nothing on the speaker side to take a ratio of, and inventing a graded score
where the data supports only a yes/no would be a precision the evidence does
not carry.

Weights live elsewhere
======================

This module contains no weight literal and no reference to one. Customer §5's
Industry weight belongs to :mod:`smartmatch_domain.factor_registry`, which is
a different track's file; ADR-0016 reaffirms that weights are never re-spread
per candidate, and a factor that cannot see a weight cannot re-spread one.
``1.0`` and ``0.0`` below are the endpoints of the ``FactorScore`` scale
itself, not weights.

Evidence states, and where this factor sits in them
===================================================

ADR-0016 (accepted 5 September 2026) names three states: ``measured``,
``policy_neutral`` and ``unknown``. Only two of them can arise here. The
``policy_neutral`` state exists because customer §9 states a policy for a
speaker with no *topic* information; §7 states no such policy for a speaker
with no industry classification, and ADR-0016 is explicit that a value may not
be invented where the customer has not chosen one. So an industry factor is
either measured or unknown, and this module deliberately does not reach for
the neutral machinery.

The boundary between the two, stated once so every branch below can be read
against it: **a classification that was read and does not match is a measured
zero; a classification that could not be evaluated is unknown.**

* Speaker's sector resolved and is one of the requested sectors — measured
  ``1.0``; the comparison ran.
* Speaker's sector resolved and is not one of them — measured ``0.0``. The
  comparison ran and the answer was no. That is a real claim about a real
  classification, and ADR-0016 requires it stay distinguishable from an
  unknown.
* No sector on file for the speaker (``None``) — unknown; nothing was read.
* Speaker's sector quarantined — unknown. A value was read but the taxonomy
  could not evaluate it. Scoring it ``0.0`` would assert "this speaker does
  not work in any requested sector", which nobody established: a later
  taxonomy version may well classify ``"Tech"`` into ``Information``.
* Request names no sectors at all — unknown. Nothing to measure against, the
  same reading ``topic_relevance`` gives an ``event_need`` that declares no
  topics.
* Request names sectors but none resolved — unknown, for the same reason: a
  speaker cannot be said to miss a target set that was never established.

Deferred: alias and fuzzy matching
==================================

`Tech` does not become `Information` and `Banking` does not become `Finance
and Insurance` here, for the reason :mod:`smartmatch_domain.naics_sectors`
gives at length: those are inference rules learned from pilot data and a later
versioned decision. This factor consumes that module's resolutions and adds no
matching of its own — there is no normalization, no substring test and no
similarity measure anywhere below, so a future alias rule has exactly one
place to land.

Not wired into the registry
===========================

Registration of ``industry_match`` in
:mod:`smartmatch_domain.factor_registry` is a separate track's work.
:data:`INDUSTRY_MATCH_FACTOR_KEY` is exported so that track references one
string rather than retyping it.

Sources
=======

* ``docs/product/cba-smart-match-customer-requirements.md`` §§5, 7
* ``docs/architecture/decisions/ADR-0016-cba-scoring-policy.md`` (Proposal 1)
* ADR-0011 (measured zero versus unknown)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from smartmatch_domain.factors import FACTOR_SCORE_PRECISION, FactorScore
from smartmatch_domain.naics_sectors import (
    NAICS_SECTORS,
    NAICS_TAXONOMY_VERSION,
    ClassifiedSector,
    QuarantinedSector,
    SectorResolution,
)

__all__ = [
    "INDUSTRY_MATCH_FACTOR_KEY",
    "INDUSTRY_MATCH_FORMULA_VERSION",
    "IndustryMatchInputs",
    "score_industry_match",
]

#: The registry key this factor's scores carry. Exported so the registry track
#: references one string instead of retyping it, and so a rename is one edit.
INDUSTRY_MATCH_FACTOR_KEY: Final[str] = "industry_match"

#: Versioned independently of the registry and of the taxonomy: any change to
#: the comparison rules above is a new formula version, even when neither the
#: weights nor the sector table moved.
INDUSTRY_MATCH_FORMULA_VERSION: Final[str] = "1.0.0"

_KNOWN_SECTORS: Final[frozenset[tuple[str, str]]] = frozenset(
    (sector.code, sector.name) for sector in NAICS_SECTORS
)


@dataclass(frozen=True, slots=True)
class IndustryMatchInputs:
    """Everything :func:`score_industry_match` is permitted to see.

    Both sides arrive already resolved against
    :mod:`smartmatch_domain.naics_sectors`. That is the point: resolution is
    the taxonomy's job and scoring is this module's, so a raw string never
    reaches the comparison and no second resolution rule can drift from the
    first.

    Attributes:
        speaker_sector: The speaker's **one primary** sector classification,
            or ``None`` when no industry value is on file. ``None`` and a
            :class:`~smartmatch_domain.naics_sectors.QuarantinedSector` are
            both unknown but for different reasons, and the ``basis`` string
            distinguishes them for the Speaker Connector who has to act.
            Cardinality is enforced by the type: §7 says one primary sector,
            so this is one value and not a tuple, and no caller can pass two.
        requested_sectors: The sectors the Speaker Request targets, in the
            order the request named them. May hold several (§7: "Do not
            restrict an event request to one industry"), may be empty, and may
            mix classified and quarantined entries. Duplicates are permitted
            and cannot change the score — the comparison is over a set.
    """

    speaker_sector: SectorResolution | None
    requested_sectors: tuple[SectorResolution, ...]

    def __post_init__(self) -> None:
        if self.speaker_sector is not None:
            _validate("speaker_sector", self.speaker_sector)
        for resolution in self.requested_sectors:
            _validate("requested_sectors", resolution)


def _validate(label: str, resolution: SectorResolution) -> None:
    """Refuse a resolution this factor cannot honestly compare.

    Two refusals, both :class:`ValueError` because both are caller bugs rather
    than missing evidence — and both must raise rather than return an unknown,
    or a construction error would be silently filed as "we could not tell",
    which is the same information loss ADR-0011 forbids in the other
    direction.
    """
    if resolution.taxonomy_version != NAICS_TAXONOMY_VERSION:
        raise ValueError(
            f"{label}: was resolved against taxonomy version "
            f"{resolution.taxonomy_version!r}, but this factor scores against "
            f"{NAICS_TAXONOMY_VERSION!r}; a classification from another "
            "version must be resolved again before it is scored, never "
            "compared across versions"
        )
    if (
        isinstance(resolution, ClassifiedSector)
        and (
            resolution.sector.code,
            resolution.sector.name,
        )
        not in _KNOWN_SECTORS
    ):
        raise ValueError(
            f"{label}: {resolution.sector!r} is not a row of the NAICS "
            f"taxonomy customer §7 supplies ({NAICS_TAXONOMY_VERSION}); a "
            "classified sector the released table does not contain was "
            "assembled by hand and is not scorable"
        )


def _requested_codes(inputs: IndustryMatchInputs) -> frozenset[str]:
    """The codes of the requested sectors that actually resolved.

    Quarantined request entries are dropped from the comparison rather than
    counted against the speaker: an unresolvable target is not a target the
    speaker failed to hit. They are not lost — the raw values stay on the
    request for a Speaker Connector to reclassify — and the "none of them
    resolved" case becomes its own unknown branch below rather than a silent
    empty set.
    """
    return frozenset(
        r.sector.code for r in inputs.requested_sectors if isinstance(r, ClassifiedSector)
    )


def score_industry_match(inputs: IndustryMatchInputs) -> FactorScore:
    """Score a speaker's primary industry sector against a request's targets.

    Args:
        inputs: The speaker's resolved primary sector and the request's
            resolved target sectors.

    Returns:
        A :class:`~smartmatch_domain.factors.FactorScore` keyed
        :data:`INDUSTRY_MATCH_FACTOR_KEY`. ``value`` is ``1.0`` when the
        speaker's sector is among the requested ones, a measured ``0.0`` when
        it was read and is not, and ``None`` when either side could not be
        evaluated. Every ``basis`` names
        :data:`~smartmatch_domain.naics_sectors.NAICS_TAXONOMY_VERSION`, so a
        stored score states which table produced it.

    Raises:
        ValueError: if either side carries a classification from another
            taxonomy version, or a sector row the released table does not
            contain. (Raised from :class:`IndustryMatchInputs` construction.)
    """
    speaker = inputs.speaker_sector

    if speaker is None:
        return FactorScore(
            INDUSTRY_MATCH_FACTOR_KEY,
            None,
            basis=(
                f"no industry classification on file for this speaker ({NAICS_TAXONOMY_VERSION})"
            ),
        )

    if isinstance(speaker, QuarantinedSector):
        return FactorScore(
            INDUSTRY_MATCH_FACTOR_KEY,
            None,
            basis=(
                f"speaker industry value {speaker.raw_value!r} is not classified "
                f"under {NAICS_TAXONOMY_VERSION} and awaits review; not evaluable"
            ),
        )

    if not inputs.requested_sectors:
        return FactorScore(
            INDUSTRY_MATCH_FACTOR_KEY,
            None,
            basis=f"speaker request names no industry sectors ({NAICS_TAXONOMY_VERSION})",
        )

    requested = _requested_codes(inputs)
    if not requested:
        return FactorScore(
            INDUSTRY_MATCH_FACTOR_KEY,
            None,
            basis=(
                f"none of the {len(inputs.requested_sectors)} industry sectors the "
                f"request names is classified under {NAICS_TAXONOMY_VERSION}; "
                "not evaluable"
            ),
        )

    matched = speaker.sector.code in requested
    speaker_label = f"{speaker.sector.code} ({speaker.sector.name})"
    relation = "is one of" if matched else "is not among"
    return FactorScore(
        INDUSTRY_MATCH_FACTOR_KEY,
        round(1.0 if matched else 0.0, FACTOR_SCORE_PRECISION),
        basis=(
            f"speaker sector {speaker_label} {relation} the {len(requested)} "
            f"requested sector(s) ({NAICS_TAXONOMY_VERSION})"
        ),
    )
