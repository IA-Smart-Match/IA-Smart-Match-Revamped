"""Resolve a stored postal code to a distance from the CPP campus (OQ-CBA-024).

The seam ``factors/proximity.py`` names and refuses to fill itself. That module
scores an **already-resolved** ``distance_miles`` and says *unknown* when it has
none; ADR-0016 puts the resolution at the caller, and this is that caller. It
lives here, at the API/evidence layer, and not in the domain — the domain must
never resolve a coordinate, so that no future edit to a factor module can
quietly acquire the ability to invent a place.

What it is allowed to use
=========================

One thing: :data:`~smartmatch_domain.zcta_centroids.CA_ZCTA_CENTROIDS`, the
static table generated at build time from the US Census ZCTA Gazetteer. No
network, no geocoding provider, no cache, no clock. ``ALLOW_LIVE_PROVIDERS``
does not gate this module because there is no live path here to gate — the
lookup is a dict access and a haversine, and it would behave identically with
every socket on the machine closed.

The four outcomes, and why three of them are the same answer
===========================================================

===============================  ============================================
Stored ``location_postal_code``  Result
===============================  ============================================
``"91768"`` (in the table)       A distance, ``zcta-centroid-2023``.
``"10001"`` (not in it)          ``None`` — outside California.
``""`` / ``NULL``                ``None`` — nothing to resolve.
``"9176"`` / ``"ABCDE"``         ``None`` — unreadable.
===============================  ============================================

The last three are all ``None`` here on purpose, and that is **not** a claim
that they are the same fact. This module's job is narrow: it answers "is there
a distance, and what is it". The *distinction* between the absences is
preserved where a reader can see it — ``score_proximity`` renders "no city and
no postal code on file" and "a place is on file but was not resolved" as two
different basis strings, and neither is the Far band. Re-deriving that
three-way distinction here would put the wording of an ADR-0016 decision in two
places.

What it deliberately does not do
================================

* **It does not resolve a city.** ``speaker_profile`` has no state column, so
  "Pomona" is ambiguous across states and the disambiguation rule is an unmade
  product decision — registered as **OQ-CBA-063**. A table keyed on city name
  alone would resolve Pomona, New York to a point in California, and the
  resulting distance would look exactly as trustworthy as a correct one.
* **It does not fall back.** A ZIP outside the table is unknown: never the
  nearest ZCTA, never a county or state centroid, never the campus itself.
  Each of those is a guess that renders as a measurement, and the band edges
  customer §10 approved are precisely where such a guess does its damage.
* **It does not widen a prefix.** ``"917"`` is not read as "somewhere in the
  91xxx area". A partial ZIP is unreadable, and unreadable is unknown.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from smartmatch_domain.factors.proximity import (
    CPP_CAMPUS_ORIGIN,
    Coordinate,
    distance_miles_from_campus,
)
from smartmatch_domain.zcta_centroids import CA_ZCTA_CENTROIDS, ZCTA_CENTROID_PROVENANCE

__all__ = [
    "ZCTA_LENGTH",
    "ZIP_PLUS_FOUR_LENGTH",
    "ResolvedDistance",
    "normalize_zcta",
    "resolve_distance_from_campus",
]

#: A ZCTA key is five digits. Anything else is unreadable, not approximated.
ZCTA_LENGTH: Final[int] = 5

#: ZIP+4 without its hyphen, as some import sources store it.
ZIP_PLUS_FOUR_LENGTH: Final[int] = 9


def _is_ascii_digits(value: str) -> bool:
    """Whether ``value`` is one or more ASCII ``0``-``9`` characters.

    ``str.isdigit`` alone is **not** this test: it is true of the full-width
    forms a spreadsheet paste can carry (a ZIP whose "1" is U+FF11 passes it),
    and those five characters are not the five a table key is written in.
    Such a value would sail past a looser check, miss the table, and resolve to
    unknown — the safe outcome, but reached by accident rather than by a rule.
    """
    return value.isascii() and value.isdigit()


@dataclass(frozen=True, slots=True)
class ResolvedDistance:
    """A distance that was actually looked up, with the receipt for it.

    Only ever constructed from a table hit, so its existence *is* the claim
    that a real Census centroid was read. There is no "unresolved"
    :class:`ResolvedDistance`: an absence is ``None``, so a caller cannot
    accidentally pass an empty one along as though it carried a measurement.

    Attributes:
        zcta: The five-digit ZCTA the coordinate was read under, after
            normalization. Recorded because the stored postal code and the key
            that resolved it can differ (``"91768-1234"`` resolves under
            ``"91768"``), and a reader checking the number should be able to
            see which row was used.
        miles: Straight-line miles from :data:`CPP_CAMPUS_ORIGIN`, unrounded.
            The band is decided against this raw value; rounding here would let
            a display convention move a candidate between bands.
        provenance: :data:`ZCTA_CENTROID_PROVENANCE` — the table and vintage the
            coordinate came from, carried into the score's basis so a stored
            number can be traced to the data that produced it.
    """

    zcta: str
    miles: float
    provenance: str


def normalize_zcta(postal_code: str | None) -> str | None:
    """The five-digit ZCTA key a stored postal code names, or ``None``.

    Accepts the three forms ``speaker_profile.location_postal_code`` actually
    holds — ``"91768"``, ``"91768-1234"`` and ``"917681234"`` — plus surrounding
    whitespace, and nothing else. A ZIP+4 resolves under its five-digit prefix
    because that is what a ZCTA *is*: the extra four digits name a delivery
    segment inside it, and there is no finer centroid to find.

    Args:
        postal_code: The stored column value, which may be ``None`` or blank.

    Returns:
        A five-digit string, or ``None`` when there is nothing readable. A
        well-formed ZIP is still only a *key*; whether the table holds it is
        :func:`resolve_distance_from_campus`'s question.
    """
    if postal_code is None:
        return None

    trimmed = postal_code.strip()
    if not trimmed:
        return None

    if "-" in trimmed:
        head, _, tail = trimmed.partition("-")
        # A hyphen that is not ZIP+4 punctuation means this is not a ZIP at
        # all. Salvaging the part before it would be reading a value the writer
        # never entered.
        if not _is_ascii_digits(tail):
            return None
        trimmed = head

    if not _is_ascii_digits(trimmed):
        return None
    if len(trimmed) == ZIP_PLUS_FOUR_LENGTH:
        trimmed = trimmed[:ZCTA_LENGTH]
    if len(trimmed) != ZCTA_LENGTH:
        return None
    return trimmed


def resolve_distance_from_campus(postal_code: str | None) -> ResolvedDistance | None:
    """Miles from the CPP campus for a stored postal code, or ``None``.

    A dict lookup and a haversine. No network, no provider, no fallback: a ZIP
    the California table does not name resolves to ``None``, which
    ``score_proximity`` renders as *unknown* rather than as the Far band, so a
    speaker outside the table is never scored as though somebody had measured
    them and found them distant.

    Args:
        postal_code: ``speaker_profile.location_postal_code`` as read.

    Returns:
        A :class:`ResolvedDistance` when the normalized ZIP is in the table;
        ``None`` when it is absent, blank, malformed, or outside California.
    """
    zcta = normalize_zcta(postal_code)
    if zcta is None:
        return None

    centroid = CA_ZCTA_CENTROIDS.get(zcta)
    if centroid is None:
        return None

    latitude, longitude = centroid
    return ResolvedDistance(
        zcta=zcta,
        miles=distance_miles_from_campus(Coordinate(latitude, longitude), CPP_CAMPUS_ORIGIN),
        provenance=ZCTA_CENTROID_PROVENANCE,
    )
