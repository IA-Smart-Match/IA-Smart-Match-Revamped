"""The generated California ZCTA centroid table is real Census data (OQ-CBA-024).

A coordinate table is the one artifact in this repository where a plausible
wrong value is invisible. A misspelled sector name is caught by a reader; a
centroid half a degree out looks exactly like a centroid that is right, and it
silently moves a speaker across the 25- or 75-mile band edges customer §10
approved. So these tests are not about the table being *nice* — they are about
it being **traceable**, which is the only property that distinguishes a
measurement from a guess (ADR-0011).

The load-bearing test is
:func:`test_the_committed_module_is_exactly_what_the_generator_emits`. Because
the generator renders its own header from digest-pinned source constants, a
byte-identical round-trip means every row in the committed module came out of
the pinned Census files and nothing was pasted in afterwards. A hand-edited
coordinate — even one — breaks it.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from smartmatch_domain.factors.proximity import (
    CPP_CAMPUS_ORIGIN,
    NEAR_BAND_MAX_MILES,
    Coordinate,
    distance_miles_from_campus,
)
from smartmatch_domain.zcta_centroids import (
    CA_ZCTA_CENTROIDS,
    CALIFORNIA_STATE_FIPS,
    ZCTA_CENTROID_PROVENANCE,
    ZCTA_CENTROID_VINTAGE,
    ZCTA_GAZETTEER_SHA256,
    ZCTA_GAZETTEER_URL,
    ZCTA_STATE_RELATIONSHIP_SHA256,
    ZCTA_STATE_RELATIONSHIP_URL,
)

from tools import generate_zcta_centroids as generator

MODULE_PATH = (
    Path(__file__).resolve().parents[2]
    / "python"
    / "smartmatch_domain"
    / "smartmatch_domain"
    / "zcta_centroids.py"
)

#: The number of ZCTAs with land in a California county in the pinned sources.
#: Pinned as a literal so a regeneration that silently loses (or gains) rows —
#: a truncated download, a changed membership rule — fails here rather than
#: quietly shrinking the set of speakers who can be measured at all.
EXPECTED_ROW_COUNT = 1808

#: California's extent, generously rounded outward. Not a precision check — a
#: wrong-but-Californian centroid passes it — but it catches the failure that
#: matters most: a latitude/longitude swap, a dropped minus sign, or rows from
#: another state leaking into a table the resolver treats as Californian.
CA_LATITUDE_RANGE = (32.0, 42.5)
CA_LONGITUDE_RANGE = (-125.0, -114.0)


# ---------------------------------------------------------------------------
# Traceability — every row came from the pinned sources
# ---------------------------------------------------------------------------


def test_the_committed_module_is_exactly_what_the_generator_emits():
    """Re-rendering the committed table reproduces the committed file byte for byte.

    The generator writes its own docstring, its vintage and both source digests
    from module constants, so this equality covers the *whole* file, not just
    the rows. A coordinate added, edited, or reordered by hand cannot survive
    it, and neither can a header claiming a vintage the generator does not
    declare.
    """
    rendered = generator.render_module(
        [(zcta, latitude, longitude) for zcta, (latitude, longitude) in CA_ZCTA_CENTROIDS.items()]
    )
    assert rendered == MODULE_PATH.read_text(encoding="utf-8")


def test_the_module_docstring_records_the_gazetteer_vintage_and_both_digests():
    """The vintage and digests are readable in the file itself, not only in the tool.

    Somebody auditing a stored score reads the module, not the generator. If the
    provenance lived only in ``tools/`` the table would be a pile of numbers
    with its story told somewhere else.
    """
    header = MODULE_PATH.read_text(encoding="utf-8").split('"""')[1]

    assert ZCTA_CENTROID_VINTAGE in header
    assert ZCTA_GAZETTEER_SHA256 in header
    assert ZCTA_STATE_RELATIONSHIP_SHA256 in header
    assert "GENERATED FILE" in header
    assert "tools/generate_zcta_centroids.py" in header


def test_the_module_and_the_generator_agree_on_vintage_and_provenance():
    """One vintage, declared once.

    A table saying 2023 built by a tool pinned to another year is a provenance
    string that lies.
    """
    assert ZCTA_CENTROID_VINTAGE == generator.VINTAGE
    assert ZCTA_CENTROID_PROVENANCE == generator.PROVENANCE
    assert CALIFORNIA_STATE_FIPS == generator.CALIFORNIA_STATE_FIPS


def test_the_pinned_source_urls_are_the_census_bureau_and_nothing_else():
    """Public-domain government data, over https, and no provider anywhere.

    OQ-CBA-024's whole shape is "static offline table instead of a geocoder". A
    source URL that drifted to a commercial ZIP-database vendor would change
    what the table *is* — its licensing, its accuracy claims, its ADR-0011
    story — without changing a single coordinate.
    """
    for url in (ZCTA_GAZETTEER_URL, ZCTA_STATE_RELATIONSHIP_URL):
        assert url.startswith("https://www2.census.gov/")


# ---------------------------------------------------------------------------
# Shape
# ---------------------------------------------------------------------------


def test_the_table_holds_every_california_zcta_in_the_pinned_sources():
    assert len(CA_ZCTA_CENTROIDS) == EXPECTED_ROW_COUNT


def test_every_key_is_a_five_digit_zcta():
    """The resolver looks up a normalized 5-character key, so a 4- or
    9-character key here would be a row no lookup could ever reach."""
    bad = [zcta for zcta in CA_ZCTA_CENTROIDS if len(zcta) != 5 or not zcta.isdigit()]
    assert bad == []


def test_every_coordinate_lies_within_californias_extent():
    minimum_latitude, maximum_latitude = CA_LATITUDE_RANGE
    minimum_longitude, maximum_longitude = CA_LONGITUDE_RANGE

    outside = [
        (zcta, latitude, longitude)
        for zcta, (latitude, longitude) in CA_ZCTA_CENTROIDS.items()
        if not (minimum_latitude <= latitude <= maximum_latitude)
        or not (minimum_longitude <= longitude <= maximum_longitude)
    ]
    assert outside == []


def test_the_table_cannot_be_edited_at_runtime():
    """A module-level dict is a dict any caller can write to, and a coordinate
    injected at runtime would be untraceable by construction — it would appear
    in no diff and under no digest."""
    with pytest.raises(TypeError):
        CA_ZCTA_CENTROIDS["91768"] = (0.0, 0.0)  # type: ignore[index]


# ---------------------------------------------------------------------------
# Boundaries — what is in, and what is deliberately out
# ---------------------------------------------------------------------------


def test_the_campus_own_zcta_is_present_and_lands_in_the_near_band():
    """91768 is the CPP campus's own ZIP, so its centroid must sit within a few
    miles of the campus origin.

    Asserted as a *band* rather than as a coordinate on purpose: a test that
    restated the Census number would become a second, hand-written copy of the
    very datum it is checking, and the two would then have to be kept in step
    by hand.
    """
    latitude, longitude = CA_ZCTA_CENTROIDS["91768"]
    miles = distance_miles_from_campus(Coordinate(latitude, longitude), CPP_CAMPUS_ORIGIN)
    assert miles < NEAR_BAND_MAX_MILES


@pytest.mark.parametrize(
    "zcta",
    [
        "10001",  # New York, NY
        "97201",  # Portland, OR
        "85001",  # Phoenix, AZ
        "00601",  # Adjuntas, PR — the first row of the national Gazetteer
    ],
)
def test_zctas_outside_california_are_absent(zcta: str):
    """The scope decision, pinned. California only was the owner's call, and a
    national table arriving by accident would widen it without a decision."""
    assert zcta not in CA_ZCTA_CENTROIDS


def test_california_zctas_that_straddle_a_state_line_are_kept():
    """A membership rule of "any part in a California county" is not the same
    as a ZIP prefix, and here is the difference: 89010 (Dyer, NV) and 97635
    (New Pine Creek, OR) reach into California and carry real Census centroids,
    so a speaker living in one is measurable. A prefix rule would drop them and
    say nothing about having done so."""
    assert "89010" in CA_ZCTA_CENTROIDS
    assert "97635" in CA_ZCTA_CENTROIDS
