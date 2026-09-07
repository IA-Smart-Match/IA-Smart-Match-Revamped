"""A stored ZIP resolves to a measured distance, or to nothing (OQ-CBA-024).

Four inputs, and the interesting thing about them is that three produce the
same return value for three different reasons: a ZIP outside California, a
blank column, and an unreadable string are all ``None``. The resolver is
allowed to collapse them because it answers only "is there a distance"; the
*reasons* stay distinguishable in ``score_proximity``'s basis strings, where a
person reads them.

What these tests are really guarding is the fourth outcome's honesty. A
resolver that quietly returned the nearest ZCTA, a county centroid, or the
campus itself for an unrecognised ZIP would pass any test that only checked
"a number came back" — and it would put a fabricated distance into a band the
customer approved, where nothing downstream could tell it from a measured one.
So the miss cases here assert ``None`` specifically, not falsiness.
"""

from __future__ import annotations

import pytest
from smartmatch_api.zip_proximity import (
    ResolvedDistance,
    normalize_zcta,
    resolve_distance_from_campus,
)
from smartmatch_domain.factors.proximity import (
    MID_BAND_MAX_MILES,
    NEAR_BAND_MAX_MILES,
    ProximityBand,
    band_for_miles,
)
from smartmatch_domain.zcta_centroids import ZCTA_CENTROID_PROVENANCE

#: The CPP campus's own ZIP. Its centroid is a few miles from the origin, so it
#: is the one input whose *band* can be asserted without restating a Census
#: number in the test.
CAMPUS_ZIP = "91768"

#: Sacramento — unambiguously Californian, unambiguously more than 75 miles
#: from Pomona. The Far band's job is to hold real, measured distance, and this
#: is the input that proves an unknown and a Far are not the same code path.
SACRAMENTO_ZIP = "95814"


# ---------------------------------------------------------------------------
# Hit
# ---------------------------------------------------------------------------


def test_a_california_zip_resolves_to_a_distance_with_its_provenance():
    resolved = resolve_distance_from_campus(CAMPUS_ZIP)

    assert isinstance(resolved, ResolvedDistance)
    assert resolved.zcta == CAMPUS_ZIP
    assert resolved.provenance == ZCTA_CENTROID_PROVENANCE
    assert resolved.miles >= 0.0


def test_the_campus_own_zip_lands_in_the_near_band():
    """Not a coordinate assertion — a sanity check that the arithmetic points at
    Pomona rather than, say, at the antimeridian after a sign error."""
    resolved = resolve_distance_from_campus(CAMPUS_ZIP)
    assert resolved is not None
    assert resolved.miles < NEAR_BAND_MAX_MILES
    assert band_for_miles(resolved.miles) is ProximityBand.NEAR


def test_a_distant_california_zip_lands_in_the_far_band():
    """A measured Far, which is a different thing from an unknown.

    ADR-0016 Proposal 4 turns on that distinction, so the suite needs at least
    one input that genuinely earns the Far band rather than falling into it.
    """
    resolved = resolve_distance_from_campus(SACRAMENTO_ZIP)
    assert resolved is not None
    assert resolved.miles >= MID_BAND_MAX_MILES
    assert band_for_miles(resolved.miles) is ProximityBand.FAR


def test_the_distance_is_not_rounded_before_it_is_returned():
    """``band_for_miles`` decides against the raw float and ``proximity``'s
    docstring forbids rounding before comparing, so a resolver that pre-rounded
    to one decimal could move a candidate across a band edge for display's
    sake."""
    resolved = resolve_distance_from_campus(SACRAMENTO_ZIP)
    assert resolved is not None
    assert resolved.miles != round(resolved.miles, 1)


@pytest.mark.parametrize(
    ("stored", "expected_key"),
    [
        (CAMPUS_ZIP, CAMPUS_ZIP),
        (f"  {CAMPUS_ZIP}  ", CAMPUS_ZIP),
        (f"{CAMPUS_ZIP}-1234", CAMPUS_ZIP),
        (f"{CAMPUS_ZIP}1234", CAMPUS_ZIP),
    ],
)
def test_the_stored_forms_of_one_zip_all_resolve_under_the_same_zcta(
    stored: str, expected_key: str
):
    """ZIP+4 resolves under its five-digit prefix, because that is what a ZCTA
    is: the extra four digits name a delivery segment inside it and there is no
    finer centroid to find."""
    resolved = resolve_distance_from_campus(stored)
    assert resolved is not None
    assert resolved.zcta == expected_key


def test_every_stored_form_of_one_zip_yields_the_identical_distance():
    """Normalization must not amount to a second, subtly different measurement."""
    distances = {
        resolve_distance_from_campus(form).miles  # type: ignore[union-attr]
        for form in (CAMPUS_ZIP, f" {CAMPUS_ZIP} ", f"{CAMPUS_ZIP}-1234", f"{CAMPUS_ZIP}1234")
    }
    assert len(distances) == 1


# ---------------------------------------------------------------------------
# Miss — a well-formed ZIP the table does not name
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "stored",
    [
        "10001",  # New York, NY
        "97201",  # Portland, OR
        "85001",  # Phoenix, AZ
        "00601",  # Adjuntas, PR
    ],
)
def test_a_zip_outside_california_resolves_to_nothing(stored: str):
    """The scope decision, enforced at the resolver.

    ``None`` and not a nearest neighbour, a state centroid, or a large number
    standing in for "far away". Every one of those would enter the band table
    as though somebody had measured it.
    """
    assert resolve_distance_from_campus(stored) is None


def test_a_well_formed_zip_that_is_simply_not_a_zcta_resolves_to_nothing():
    """``99999`` is five digits and is nothing. Shape is not membership."""
    assert normalize_zcta("99999") == "99999"
    assert resolve_distance_from_campus("99999") is None


# ---------------------------------------------------------------------------
# Blank
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("stored", [None, "", "   ", "\t\n"])
def test_a_missing_or_blank_postal_code_resolves_to_nothing(stored: str | None):
    """``location_postal_code`` is nullable and the import path can write an
    empty cell. Both mean the same thing — nobody recorded a ZIP — and neither
    is an error to raise at a caller that is assembling a whole pool."""
    assert normalize_zcta(stored) is None
    assert resolve_distance_from_campus(stored) is None


# ---------------------------------------------------------------------------
# Malformed
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "stored",
    [
        "9176",  # four digits — truncated on import
        "917",  # a prefix, not a ZIP
        "917680",  # six digits
        "ABCDE",  # letters
        "91768x",  # trailing junk
        "9 1768",  # embedded space
        "91768-",  # a hyphen with nothing after it
        "91768-abc",  # a hyphen with non-digits after it
        "SW1A 1AA",  # a UK postcode
        "-91768",  # a leading hyphen
    ],
)
def test_an_unreadable_postal_code_resolves_to_nothing(stored: str):
    """Unreadable is unknown, never approximated.

    In particular ``"917"`` is not widened to "somewhere in 91xxx" and
    ``"91768x"`` is not salvaged down to its digits: reading a value the writer
    did not enter is how a typo becomes a measurement.
    """
    assert normalize_zcta(stored) is None
    assert resolve_distance_from_campus(stored) is None


def test_a_zip_that_only_looks_numeric_is_refused_rather_than_coerced():
    """A leading ``+``, a float-shaped string, and a full-width digit all read
    as "numeric" under one Python predicate or another. These pin that the
    resolver's predicate is not one of the weak ones."""
    for stored in ("+9176", "91768.0", "9\uff11768"):
        assert normalize_zcta(stored) is None
        assert resolve_distance_from_campus(stored) is None
