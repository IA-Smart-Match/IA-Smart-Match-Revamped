"""Travel Burden scoring factor.

Architecture v1.1 §1.2. Registered in
:mod:`smartmatch_domain.factor_registry` as ``travel_burden``
(``FactorKind.PENALTY``, Stage B weight 0.30 per gate G1 approval,
2026-09-03). Measures how burdensome the physical distance between a
professional and an ``event_need`` is, as a penalty in ``[0.0, 1.0]``.

**This value is a coarse straight-line (haversine) estimate, nothing more.**
The D3 route-matrix provider — which would supply real driving distance and
travel time — is deferred pending procurement
(``docs/decisions/synthetic-pilot-development-authorization-2026-09-03.md``
§3). This module never calls a network, a provider, or a route-matrix API,
and never fabricates mileage or travel time: absent coordinates yield an
unknown (``value=None``) result, never a guessed distance and never
``0.0``. Every produced value — including a genuine, measured ``0.0`` for
coincident points — carries :data:`TRAVEL_ESTIMATE_LABEL` so downstream
consumers cannot mistake this for a real-world route estimate. Coordinates
scored by this module are synthetic pilot data.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Final

from smartmatch_domain.factors import FACTOR_SCORE_PRECISION, FactorScore

__all__ = [
    "EARTH_RADIUS_KM",
    "FREE_RADIUS_KM",
    "MAX_BURDEN_KM",
    "TRAVEL_BURDEN_FORMULA_VERSION",
    "TRAVEL_ESTIMATE_LABEL",
    "GeoPoint",
    "TravelInputs",
    "haversine_km",
    "score_travel_burden",
]

#: Versioned independently of the registry: any change to this arithmetic is a
#: new formula version. The "-straight-line" suffix records that this is a
#: haversine estimate, not a route-matrix result.
TRAVEL_BURDEN_FORMULA_VERSION: Final[str] = "1.0.0-straight-line"

#: Attached to every produced FactorScore so no downstream consumer mistakes
#: this haversine estimate for a real driving distance or travel time.
TRAVEL_ESTIMATE_LABEL: Final[str] = "coarse straight-line estimate; D3 route matrix deferred"

#: IUGG mean Earth radius in kilometers, used by the haversine formula.
EARTH_RADIUS_KM: Final[float] = 6371.0088

#: Distance, in kilometers, within which travel is considered local and
#: carries no burden (~10 miles).
FREE_RADIUS_KM: Final[float] = 16.0

#: Distance, in kilometers, at and beyond which burden saturates at 1.0
#: (~100 miles).
MAX_BURDEN_KM: Final[float] = 160.0


@dataclass(frozen=True, slots=True)
class GeoPoint:
    """A synthetic pilot coordinate.

    Attributes:
        latitude: Degrees, must be in ``[-90.0, 90.0]``.
        longitude: Degrees, must be in ``[-180.0, 180.0]``.
    """

    latitude: float
    longitude: float

    def __post_init__(self) -> None:
        if not -90.0 <= self.latitude <= 90.0:
            raise ValueError(f"latitude: must be in [-90.0, 90.0], got {self.latitude!r}")
        if not -180.0 <= self.longitude <= 180.0:
            raise ValueError(f"longitude: must be in [-180.0, 180.0], got {self.longitude!r}")


@dataclass(frozen=True, slots=True)
class TravelInputs:
    """Everything :func:`score_travel_burden` is permitted to see.

    Attributes:
        origin: The professional's synthetic coordinates, or ``None`` when no
            coordinates are on file (unknown).
        destination: The ``event_need``'s synthetic coordinates, or ``None``
            when no coordinates are on file (unknown).
    """

    origin: GeoPoint | None
    destination: GeoPoint | None


def haversine_km(origin: GeoPoint, destination: GeoPoint) -> float:
    """Great-circle distance between two points, in kilometers.

    Standard haversine formula over a sphere of radius
    :data:`EARTH_RADIUS_KM`. Pure :mod:`math`; no third-party library, no
    network.

    Args:
        origin: The first point.
        destination: The second point.

    Returns:
        The great-circle distance in kilometers. Symmetric in its two
        arguments; ``0.0`` when the two points coincide.
    """
    lat1 = math.radians(origin.latitude)
    lat2 = math.radians(destination.latitude)
    delta_lat = math.radians(destination.latitude - origin.latitude)
    delta_lon = math.radians(destination.longitude - origin.longitude)

    a = (
        math.sin(delta_lat / 2) ** 2
        + math.cos(lat1) * math.cos(lat2) * math.sin(delta_lon / 2) ** 2
    )
    # Clamp: floating-point error can push `a` an ulp above 1.0 for
    # near-antipodal points, which would make math.asin raise a domain
    # error instead of returning the (correctly saturating) distance.
    c = 2 * math.asin(math.sqrt(min(1.0, a)))
    return EARTH_RADIUS_KM * c


def score_travel_burden(inputs: TravelInputs) -> FactorScore:
    """Score the travel burden between a professional and an event_need.

    Args:
        inputs: The professional's and event_need's synthetic coordinates.

    Returns:
        A :class:`~smartmatch_domain.factors.FactorScore` with
        ``factor_key="travel_burden"``. ``value`` is ``None`` when either
        coordinate is absent (unknown, per ADR-0011 — never a guessed
        distance); otherwise it is the straight-line burden magnitude in
        ``[0.0, 1.0]``, rounded to
        :data:`~smartmatch_domain.factors.FACTOR_SCORE_PRECISION` places,
        where ``0.0`` is no burden and ``1.0`` is maximum burden. Every
        produced value carries :data:`TRAVEL_ESTIMATE_LABEL`.
    """
    if inputs.origin is None or inputs.destination is None:
        # No estimate_label here: FactorScore.estimate_label is "set when the
        # value is an explicitly coarse estimate" — an unknown result has no
        # value to estimate, so leave it at its FactorScore default of None
        # rather than attaching a label that describes a value this result
        # does not carry.
        return FactorScore(
            "travel_burden",
            None,
            basis="professional or event_need coordinates are absent",
        )

    distance = haversine_km(inputs.origin, inputs.destination)

    if distance <= FREE_RADIUS_KM:
        burden = 0.0
    elif distance >= MAX_BURDEN_KM:
        burden = 1.0
    else:
        burden = (distance - FREE_RADIUS_KM) / (MAX_BURDEN_KM - FREE_RADIUS_KM)

    return FactorScore(
        "travel_burden",
        round(burden, FACTOR_SCORE_PRECISION),
        basis=f"{distance:.1f} km straight-line between synthetic coordinates",
        estimate_label=TRAVEL_ESTIMATE_LABEL,
    )
