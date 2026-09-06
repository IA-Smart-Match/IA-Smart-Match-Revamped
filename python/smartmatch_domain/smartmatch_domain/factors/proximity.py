"""CBA Proximity scoring factor — mile bands from the CPP campus.

Customer §10 and **ADR-0016 Proposals 3, 4 and 5**, accepted 5 September 2026.
Every number in this module is an approved policy value, not an engineering
choice: the band edges (25 and 75 miles), the three sub-scores
(``1.00`` / ``0.60`` / ``0.20``), the lower-inclusive/upper-exclusive boundary
rule, the ruling that a missing address is *unknown* rather than Far, and the
two scoring-mode names. Changing any of them amends ADR-0016 and needs its own
approval; it does not follow from finding an old value inconvenient.

**The three things this module refuses to do**

1. **It does not interpolate.** §10 specifies *bands*, and a band that
   secretly interpolates is not the thing the customer approved. Every
   distance inside a band scores identically.
2. **It does not round before comparing.** The band is decided against the raw
   float. ``24.9996`` is Near even though its own basis string renders
   ``25.0 miles``, because a display convention must never move a candidate
   between bands.
3. **It does not guess a distance.** No network, no geocoder, no route-matrix
   provider — the D3/D4 providers stay deferred. A speaker with a place on
   file but no resolved coordinate is *unknown*, and a speaker with neither a
   city nor a postal code is *unknown*. Neither is filed in the Far band on
   the grounds that they are "probably far": that is a guess rendered as a
   measurement, which is precisely the defect ADR-0011 exists to forbid.

**Miles, never kilometers.** §10 measures proximity "in miles from the CPP
campus", so miles are the unit on every CBA output this module produces. The
pre-CBA :mod:`~smartmatch_domain.factors.travel_burden` factor works in
kilometers; see "Coexistence with travel_burden" below for why both still
exist.

**Virtual events.** Under ``cba-virtual-1`` proximity is not scored *at all*
(ADR-0016 Proposal 5). :func:`score_proximity` therefore **raises** in that
mode rather than returning a number: not ``0.0``, which would be a measured
claim nobody measured, and not ``unknown``, which would say the factor tried
to evaluate and failed. The factor is absent from the model by an approved
rule known before any candidate is read. The redistribution of its weight
across Industry, Role and Topic (Proposal 6) is the registry track's work and
appears nowhere here — this module contains no weight literal of any kind.

**What this module deliberately does not decide**

* **Registry wiring.** :mod:`smartmatch_domain.factor_registry`,
  :mod:`~smartmatch_domain.scoring`, :mod:`~smartmatch_domain.explanation` and
  :mod:`~smartmatch_domain.match_run` are untouched by this module. Whether the
  registry key is ``proximity`` (the sub-score scale) or ``travel_burden`` (the
  penalty scale, ``1 - proximity``, which is the column ADR-0016 Proposal 3
  actually tabulates) is the registry track's call.
  :attr:`ProximityAssessment.travel_burden_value` exposes the penalty form so
  that track need not re-derive the arithmetic.
* **``scoring_mode_version``.** Proposal 9 puts it on ``MatchRunPins``; this
  module names the two *modes* (a closed, ADR-approved vocabulary) and nothing
  about how a run records them.
* **How a city or ZIP becomes a coordinate.** That is a provider seam and it
  is gated (OQ-CBA-024). The caller resolves it or does not; this module
  measures and bands, and says "unknown" honestly when it cannot.

**Coexistence with travel_burden — this module does not supersede it yet.**
:mod:`smartmatch_domain.factors.travel_burden` is the pre-CBA, G1-approved
proximity notion: a *continuous* haversine penalty in kilometers, with a free
radius at ~16 km and saturation at ~160 km, registered under
``REGISTRY_VERSION`` ``1.1.1-approved-g1-m6j``. This module is the CBA notion:
a *step function* in miles from a single fixed campus origin, under the
registry version ADR-0016 Proposal 9 bumps to. They are not two
implementations of one idea and one is not a refactor of the other — they
answer different questions under different rulebooks, and runs stored under
the old pin stay readable at that pin and are never re-scored under this one.

They are therefore kept deliberately apart: this module does **not** import
``travel_burden``, does not reuse its haversine (the few lines are duplicated
on purpose, so a change to one arithmetic cannot silently move the other), and
does not delete or edit it. Retiring ``travel_burden`` is a separate decision
about stored runs and the registry, recorded as **OQ-CBA-025**, and it is not
taken here.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import StrEnum
from typing import Final

from smartmatch_domain.factors import FACTOR_SCORE_PRECISION, FactorScore

__all__ = [
    "CBA_PHYSICAL_SCORING_MODE",
    "CBA_PROXIMITY_FACTOR_KEY",
    "CBA_PROXIMITY_FORMULA_VERSION",
    "CBA_PROXIMITY_POLICY_ID",
    "CBA_SCORING_MODES",
    "CBA_VIRTUAL_SCORING_MODE",
    "CPP_CAMPUS_ORIGIN",
    "CPP_CAMPUS_ORIGIN_VERSION",
    "EARTH_RADIUS_MILES",
    "FAR_BAND_SCORE",
    "MID_BAND_MAX_MILES",
    "MID_BAND_SCORE",
    "NEAR_BAND_MAX_MILES",
    "NEAR_BAND_SCORE",
    "PROXIMITY_ESTIMATE_LABEL",
    "UNKNOWN_LOCATION_UI_LABEL",
    "CampusOrigin",
    "Coordinate",
    "ProximityAssessment",
    "ProximityBand",
    "ProximityInputs",
    "SpeakerLocation",
    "UnknownScoringModeError",
    "VirtualEventProximityError",
    "band_for_miles",
    "distance_miles_from_campus",
    "proximity_is_scored",
    "score_proximity",
]

# ---------------------------------------------------------------------------
# Pins
# ---------------------------------------------------------------------------

#: Versioned independently of the registry and of the campus origin: any change
#: to the band edges, the sub-scores, or the boundary rule is a new formula
#: version. The ``-cba-bands`` suffix records that this is the customer §10
#: step function and not the pre-CBA continuous penalty.
CBA_PROXIMITY_FORMULA_VERSION: Final[str] = "1.0.0-cba-bands"

#: The stable identifier of the band policy, named in every scored basis so a
#: stored score can be traced back to the decision that produced it.
CBA_PROXIMITY_POLICY_ID: Final[str] = "cba-proximity-bands"

#: The key this factor's :class:`~smartmatch_domain.factors.FactorScore`
#: carries. Registry declaration is the registry track's deliverable; this
#: constant exists so the key is written down once rather than typed at each
#: call site.
CBA_PROXIMITY_FACTOR_KEY: Final[str] = "proximity"

#: Attached to every produced value: the band is derived from a straight-line
#: distance, not a driving route. Never attached to an unknown, which has no
#: value to describe as an estimate.
PROXIMITY_ESTIMATE_LABEL: Final[str] = (
    "band from straight-line miles to the CPP campus; D3 route matrix deferred"
)

#: ADR-0016 Proposal 8: an unknown distance renders as this, and never as
#: "Far", "0", "0%", or a blank cell.
UNKNOWN_LOCATION_UI_LABEL: Final[str] = "Unknown — no location on file"

# ---------------------------------------------------------------------------
# The accepted band table (ADR-0016 Proposal 3)
# ---------------------------------------------------------------------------

#: Upper edge of the Near band, **exclusive**: exactly 25 miles is Mid.
NEAR_BAND_MAX_MILES: Final[float] = 25.0

#: Upper edge of the Mid band, **exclusive**: exactly 75 miles is Far.
MID_BAND_MAX_MILES: Final[float] = 75.0

#: Sub-score for ``0 <= d < 25``.
NEAR_BAND_SCORE: Final[float] = 1.00

#: Sub-score for ``25 <= d < 75``.
MID_BAND_SCORE: Final[float] = 0.60

#: Sub-score for ``75 <= d``. Deliberately ``0.20`` and not ``0.00``: under
#: ADR-0011 a measured zero is a real claim ("maximally distant"), and a
#: speaker 80 miles away is not the same fact as one 3,000 miles away. Zero
#: stays reserved for a band that means it.
FAR_BAND_SCORE: Final[float] = 0.20

# ---------------------------------------------------------------------------
# Scoring modes (ADR-0016 Proposal 5) -- a closed vocabulary, never inferred
# ---------------------------------------------------------------------------

#: ``is_virtual = false``: Industry, Role, Topic, Proximity.
CBA_PHYSICAL_SCORING_MODE: Final[str] = "cba-physical-1"

#: ``is_virtual = true``: Industry, Role, Topic. Proximity is excluded from
#: the factor set entirely.
CBA_VIRTUAL_SCORING_MODE: Final[str] = "cba-virtual-1"

#: The whole vocabulary. A mode outside it is refused, never defaulted.
CBA_SCORING_MODES: Final[frozenset[str]] = frozenset(
    {CBA_PHYSICAL_SCORING_MODE, CBA_VIRTUAL_SCORING_MODE}
)

# ---------------------------------------------------------------------------
# Geometry
# ---------------------------------------------------------------------------

#: IUGG mean Earth radius in statute miles (6371.0088 km / 1.609344).
EARTH_RADIUS_MILES: Final[float] = 3958.7613


class UnknownScoringModeError(ValueError):
    """A scoring mode outside the ADR-0016 vocabulary was supplied."""


class VirtualEventProximityError(ValueError):
    """Proximity was asked for under ``cba-virtual-1``.

    Under that mode the factor does not participate at all, so this is a
    caller error rather than a score. Returning ``0.0`` would be a measured
    claim nobody measured, and returning ``unknown`` would say the factor
    tried to evaluate and could not.
    """


class ProximityBand(StrEnum):
    """The three §10 distance bands."""

    NEAR = "near"
    MID = "mid"
    FAR = "far"

    @property
    def label(self) -> str:
        """The ADR-0016 Proposal 8 UI label for this band."""
        return _BAND_LABELS[self]

    @property
    def score(self) -> float:
        """The accepted proximity sub-score for this band."""
        return _BAND_SCORES[self]

    @property
    def travel_burden_value(self) -> float:
        """The penalty-scale form of this band's score, ``1 - proximity``.

        Proposal 3's right-hand column: ``0.00`` / ``0.40`` / ``0.80``.
        Exposed so a registry that declares this factor on the penalty scale
        does not re-derive the subtraction at its own call site.
        """
        return round(1.0 - self.score, FACTOR_SCORE_PRECISION)


_BAND_LABELS: Final[dict[ProximityBand, str]] = {
    ProximityBand.NEAR: "Near",
    ProximityBand.MID: "Mid",
    ProximityBand.FAR: "Far",
}

_BAND_SCORES: Final[dict[ProximityBand, float]] = {
    ProximityBand.NEAR: NEAR_BAND_SCORE,
    ProximityBand.MID: MID_BAND_SCORE,
    ProximityBand.FAR: FAR_BAND_SCORE,
}


@dataclass(frozen=True, slots=True)
class Coordinate:
    """A point on the globe, in degrees.

    Named separately from
    :class:`smartmatch_domain.factors.travel_burden.GeoPoint` rather than
    reused: the two factors are versioned apart on purpose, and a shared type
    is the seam through which one module's change reaches the other.
    """

    latitude: float
    longitude: float

    def __post_init__(self) -> None:
        if not -90.0 <= self.latitude <= 90.0:
            raise ValueError(f"latitude: must be in [-90.0, 90.0], got {self.latitude!r}")
        if not -180.0 <= self.longitude <= 180.0:
            raise ValueError(f"longitude: must be in [-180.0, 180.0], got {self.longitude!r}")


@dataclass(frozen=True, slots=True)
class CampusOrigin:
    """The versioned point every CBA distance is measured from.

    A config seam, not a literal buried in the arithmetic: the campus pin can
    move (a different building, a corrected coordinate) without that being a
    change to the band formula, which is why it carries its own ``version``
    separate from :data:`CBA_PROXIMITY_FORMULA_VERSION`.

    Attributes:
        identifier: Stable machine key, recorded on scores measured from it.
        label: Human-readable name for an explanation row.
        latitude: Degrees, in ``[-90.0, 90.0]``.
        longitude: Degrees, in ``[-180.0, 180.0]``.
        source: Where the coordinate came from, non-blank. A coordinate with
            no stated provenance is a number nobody can check.
        version: Bumped whenever the coordinate moves, so a stored run is
            never re-read against an origin it was not measured from.
    """

    identifier: str
    label: str
    latitude: float
    longitude: float
    source: str
    version: str

    def __post_init__(self) -> None:
        if not -90.0 <= self.latitude <= 90.0:
            raise ValueError(f"latitude: must be in [-90.0, 90.0], got {self.latitude!r}")
        if not -180.0 <= self.longitude <= 180.0:
            raise ValueError(f"longitude: must be in [-180.0, 180.0], got {self.longitude!r}")
        for name, value in (
            ("identifier", self.identifier),
            ("label", self.label),
            ("source", self.source),
            ("version", self.version),
        ):
            if not value.strip():
                raise ValueError(f"CampusOrigin.{name}: must be a non-empty, non-blank string")


#: ``0.1.0-provisional``, not ``1.0.0``: the coordinate below is derived from
#: the campus street address and has **not** been confirmed by the program
#: owner. Recorded as OQ-CBA-023 rather than adopted as settled, because a
#: number nobody approved that never gets questioned is exactly how an
#: unapproved default becomes permanent. The band formula is not provisional;
#: only the point it measures from is.
CPP_CAMPUS_ORIGIN_VERSION: Final[str] = "0.1.0-provisional"

#: The CBA proximity origin of record.
CPP_CAMPUS_ORIGIN: Final[CampusOrigin] = CampusOrigin(
    identifier="cpp-main-campus",
    label="Cal Poly Pomona main campus",
    latitude=34.0575,
    longitude=-117.8210,
    source=(
        "Approximate centroid of the campus at 3801 W. Temple Ave, Pomona, CA 91768. "
        "PROVISIONAL: not confirmed by the program owner -- see OQ-CBA-023. No geocoding "
        "provider was called to obtain it and none is called to use it."
    ),
    version=CPP_CAMPUS_ORIGIN_VERSION,
)


@dataclass(frozen=True, slots=True)
class SpeakerLocation:
    """The place on file for a speaker (migration ``0024``).

    §10: "City or ZIP code is sufficient for this phase", so either alone
    counts as a location. A blank or whitespace-only value is treated as
    absent rather than present-but-empty — the same reading migration
    ``0024``'s check constraints take, and the same reading ADR-0011 takes of
    a writer who forgot.
    """

    city: str | None
    postal_code: str | None

    @property
    def is_absent(self) -> bool:
        """Whether neither a city nor a postal code is on file."""
        return not (self.city or "").strip() and not (self.postal_code or "").strip()


@dataclass(frozen=True, slots=True)
class ProximityInputs:
    """Everything :func:`score_proximity` is permitted to see.

    Attributes:
        location: The speaker's city/postal code, or ``None`` when no location
            record exists at all.
        distance_miles: The distance from :data:`CPP_CAMPUS_ORIGIN`, already
            resolved by the caller, or ``None`` when the place on file has not
            been resolved to a coordinate. This module never resolves one
            itself — see OQ-CBA-024.
        scoring_mode: One of :data:`CBA_SCORING_MODES`, resolved from the event
            before scoring and never inferred here.
    """

    location: SpeakerLocation | None
    distance_miles: float | None = None
    scoring_mode: str = CBA_PHYSICAL_SCORING_MODE

    def __post_init__(self) -> None:
        if self.scoring_mode not in CBA_SCORING_MODES:
            raise UnknownScoringModeError(
                f"scoring_mode: must be one of {sorted(CBA_SCORING_MODES)}, got "
                f"{self.scoring_mode!r}. The mode vocabulary is closed (ADR-0016 "
                "Proposal 5); an unrecognised mode is refused rather than defaulted."
            )
        if self.distance_miles is None:
            return
        if not math.isfinite(self.distance_miles):
            raise ValueError(f"distance_miles: must be finite, got {self.distance_miles!r}")
        if self.distance_miles < 0.0:
            raise ValueError(
                f"distance_miles: must be non-negative, got {self.distance_miles!r}. A "
                "negative distance is a caller bug, and clamping it to 0.0 would file a "
                "bug in the Near band."
            )
        if self.location is None or self.location.is_absent:
            raise ValueError(
                "distance_miles was supplied with no city and no postal code on file. A "
                "distance from a place that is not recorded is a guess wearing a "
                "measurement's clothes (ADR-0016 Proposal 4)."
            )


@dataclass(frozen=True, slots=True)
class ProximityAssessment:
    """One proximity outcome, with everything needed to account for it.

    Attributes:
        score: The factor score. ``value`` is ``None`` for an unknown distance
            — never the Far band's ``0.20``, and never ``0.0``.
        band: The band that produced the value, or ``None`` when unknown.
        distance_miles: The raw distance the band was decided from, or
            ``None``. Reported for provenance; the band was decided from this
            unrounded value.
        origin: The campus origin the distance was measured from.
        formula_version: :data:`CBA_PROXIMITY_FORMULA_VERSION`.
        scoring_mode: The mode this assessment was produced under.
    """

    score: FactorScore
    band: ProximityBand | None
    distance_miles: float | None
    origin: CampusOrigin
    formula_version: str
    scoring_mode: str

    @property
    def travel_burden_value(self) -> float | None:
        """The penalty-scale form, ``1 - proximity``, or ``None`` if unknown."""
        return None if self.band is None else self.band.travel_burden_value

    @property
    def ui_label(self) -> str:
        """ADR-0016 Proposal 8's label: the band name, or the unknown wording."""
        return UNKNOWN_LOCATION_UI_LABEL if self.band is None else self.band.label


def proximity_is_scored(scoring_mode: str) -> bool:
    """Whether proximity participates at all under ``scoring_mode``.

    Args:
        scoring_mode: A member of :data:`CBA_SCORING_MODES`.

    Returns:
        ``True`` under ``cba-physical-1``, ``False`` under ``cba-virtual-1``.

    Raises:
        UnknownScoringModeError: If the mode is outside the vocabulary.
    """
    if scoring_mode not in CBA_SCORING_MODES:
        raise UnknownScoringModeError(
            f"scoring_mode: must be one of {sorted(CBA_SCORING_MODES)}, got {scoring_mode!r}"
        )
    return scoring_mode == CBA_PHYSICAL_SCORING_MODE


def band_for_miles(miles: float) -> ProximityBand:
    """The §10 band a raw distance falls in.

    Boundaries are lower-inclusive and upper-exclusive throughout, so every
    distance falls in exactly one band and none falls in two: **exactly 25**
    miles is Mid, **exactly 75** miles is Far. The comparison is against the
    value as passed — this function never rounds, and a caller must not round
    before calling it.

    Args:
        miles: A finite, non-negative distance in statute miles.

    Returns:
        The :class:`ProximityBand` containing ``miles``.

    Raises:
        ValueError: If ``miles`` is negative or not finite.
    """
    if not math.isfinite(miles):
        raise ValueError(f"miles: must be finite, got {miles!r}")
    if miles < 0.0:
        raise ValueError(f"miles: must be non-negative, got {miles!r}")
    if miles < NEAR_BAND_MAX_MILES:
        return ProximityBand.NEAR
    if miles < MID_BAND_MAX_MILES:
        return ProximityBand.MID
    return ProximityBand.FAR


def distance_miles_from_campus(
    point: Coordinate,
    origin: CampusOrigin = CPP_CAMPUS_ORIGIN,
) -> float:
    """Great-circle distance from ``origin`` to ``point``, in statute miles.

    Standard haversine over a sphere of radius :data:`EARTH_RADIUS_MILES`.
    Pure :mod:`math`: no third-party library, no network, no address lookup.
    The result is a straight-line estimate and is labelled as one wherever it
    reaches a score.

    Args:
        point: The speaker's resolved coordinate. Resolving a city or ZIP into
            one is the caller's job and is gated (OQ-CBA-024).
        origin: The campus origin to measure from; defaults to
            :data:`CPP_CAMPUS_ORIGIN`.

    Returns:
        The distance in miles. ``0.0`` when the point coincides with the
        origin, and symmetric about it.
    """
    lat1 = math.radians(origin.latitude)
    lat2 = math.radians(point.latitude)
    delta_lat = math.radians(point.latitude - origin.latitude)
    delta_lon = math.radians(point.longitude - origin.longitude)

    a = (
        math.sin(delta_lat / 2) ** 2
        + math.cos(lat1) * math.cos(lat2) * math.sin(delta_lon / 2) ** 2
    )
    # Clamp: floating-point error can push `a` an ulp above 1.0 for
    # near-antipodal points, which would make math.asin raise a domain error
    # instead of returning the (correct) distance.
    c = 2 * math.asin(math.sqrt(min(1.0, a)))
    return EARTH_RADIUS_MILES * c


def _unknown(inputs: ProximityInputs, basis: str) -> ProximityAssessment:
    """An honest non-answer: ``value=None``, no band, no estimate label."""
    return ProximityAssessment(
        # No estimate_label: FactorScore.estimate_label is "set when the value
        # is an explicitly coarse estimate", and an unknown has no value to
        # describe.
        score=FactorScore(CBA_PROXIMITY_FACTOR_KEY, None, basis=basis),
        band=None,
        distance_miles=None,
        origin=CPP_CAMPUS_ORIGIN,
        formula_version=CBA_PROXIMITY_FORMULA_VERSION,
        scoring_mode=inputs.scoring_mode,
    )


def score_proximity(inputs: ProximityInputs) -> ProximityAssessment:
    """Score CBA proximity for one speaker against one physical request.

    Args:
        inputs: The speaker's place on file and its resolved distance, plus
            the run's scoring mode.

    Returns:
        A :class:`ProximityAssessment`. Its ``score.value`` is the band's
        accepted sub-score, or ``None`` when the distance is unknown — an
        unknown distance is **not** the Far band (ADR-0016 Proposal 4), so a
        speaker who later supplies an address does not see their score move
        for no visible reason.

    Raises:
        VirtualEventProximityError: If ``inputs.scoring_mode`` is
            ``cba-virtual-1``. Proximity is excluded from the factor set for a
            virtual run, so there is no number to return.
    """
    if not proximity_is_scored(inputs.scoring_mode):
        raise VirtualEventProximityError(
            f"proximity is not scored under {inputs.scoring_mode!r} (ADR-0016 Proposal 5: "
            "customer §11 says to ignore proximity entirely for a virtual event). The "
            "factor is absent from the model by an approved rule, so there is no score, "
            "no 0.0, and no unknown to return. Call proximity_is_scored() before scoring."
        )

    if inputs.location is None or inputs.location.is_absent:
        return _unknown(
            inputs,
            "No city and no postal code on file, so the distance from the CPP campus is "
            "unknown. An unknown distance is not the Far band (ADR-0016 Proposal 4).",
        )

    if inputs.distance_miles is None:
        return _unknown(
            inputs,
            "A city or postal code is on file but was not resolved to a coordinate, so "
            "the distance from the CPP campus is unknown. No address-lookup provider is "
            "called here (OQ-CBA-024), and an unresolved address is not the Far band.",
        )

    # Decided against the raw float, before any display rounding below.
    band = band_for_miles(inputs.distance_miles)

    return ProximityAssessment(
        score=FactorScore(
            CBA_PROXIMITY_FACTOR_KEY,
            round(band.score, FACTOR_SCORE_PRECISION),
            basis=(
                f"{inputs.distance_miles:.1f} miles straight-line from "
                f"{CPP_CAMPUS_ORIGIN.label} ({CPP_CAMPUS_ORIGIN.identifier} "
                f"{CPP_CAMPUS_ORIGIN_VERSION}); {band.label} band "
                f"({CBA_PROXIMITY_POLICY_ID} {CBA_PROXIMITY_FORMULA_VERSION})."
            ),
            estimate_label=PROXIMITY_ESTIMATE_LABEL,
        ),
        band=band,
        distance_miles=inputs.distance_miles,
        origin=CPP_CAMPUS_ORIGIN,
        formula_version=CBA_PROXIMITY_FORMULA_VERSION,
        scoring_mode=inputs.scoring_mode,
    )
