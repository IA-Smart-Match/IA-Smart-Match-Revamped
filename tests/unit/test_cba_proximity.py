"""Tests for the CBA CPP-campus proximity factor (ADR-0016 Proposals 3, 4, 5).

Every assertion in this file traces to an *accepted* value in
``docs/architecture/decisions/ADR-0016-cba-scoring-policy.md``. Nothing here
asserts a number this test file chose: the band edges, the three sub-scores,
the boundary ownership at exactly 25 and exactly 75 miles, the refusal to file
a missing address in the Far band, and the two scoring-mode names are all
owner-approved policy. A change to any of them amends the ADR first and this
file second.

The golden-case IDs named in the docstrings below (``G-CBA-04`` … ``G-CBA-08``)
are the ADR's own. The golden *set* is another track's deliverable; these are
the unit-level equivalents, asserted here so the band arithmetic is pinned
before any registry wiring exists.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest
from smartmatch_domain.factors import FACTOR_SCORE_PRECISION, ZeroClassification
from smartmatch_domain.factors.proximity import (
    CBA_PHYSICAL_SCORING_MODE,
    CBA_PROXIMITY_FACTOR_KEY,
    CBA_PROXIMITY_FORMULA_VERSION,
    CBA_PROXIMITY_POLICY_ID,
    CBA_VIRTUAL_SCORING_MODE,
    CPP_CAMPUS_ORIGIN,
    CPP_CAMPUS_ORIGIN_VERSION,
    FAR_BAND_SCORE,
    MID_BAND_SCORE,
    NEAR_BAND_SCORE,
    PROXIMITY_ESTIMATE_LABEL,
    CampusOrigin,
    Coordinate,
    ProximityBand,
    ProximityInputs,
    SpeakerLocation,
    UnknownScoringModeError,
    VirtualEventProximityError,
    band_for_miles,
    distance_miles_from_campus,
    proximity_is_scored,
    score_proximity,
)

_MODULE_PATH = (
    Path(__file__).resolve().parents[2]
    / "python"
    / "smartmatch_domain"
    / "smartmatch_domain"
    / "factors"
    / "proximity.py"
)

POMONA = SpeakerLocation(city="Pomona", postal_code="91768")
ZIP_ONLY = SpeakerLocation(city=None, postal_code="91768")
CITY_ONLY = SpeakerLocation(city="Pomona", postal_code=None)
NO_LOCATION = SpeakerLocation(city=None, postal_code=None)


def _at(miles: float, location: SpeakerLocation = POMONA) -> ProximityInputs:
    """A physical-mode input resolved to exactly ``miles`` from the campus."""
    return ProximityInputs(location=location, distance_miles=miles)


# --------------------------------------------------------------------------
# Proposal 3 -- the band table, exactly as accepted
# --------------------------------------------------------------------------


def test_the_three_band_scores_are_the_accepted_values():
    assert NEAR_BAND_SCORE == 1.00
    assert MID_BAND_SCORE == 0.60
    assert FAR_BAND_SCORE == 0.20


def test_the_far_band_is_not_zero():
    """ADR-0016 Proposal 3: `0.00` stays reserved for a real measured zero."""
    assert FAR_BAND_SCORE != 0.0
    assert score_proximity(_at(3000.0)).score.zero_classification is None


@pytest.mark.parametrize("miles", [0.0, 0.5, 10.0, 24.0, 24.9, 24.999999])
def test_near_band_covers_zero_up_to_but_not_including_twenty_five(miles: float):
    """G-CBA-04: `d = 24.9` is Near, proximity `1.00`."""
    result = score_proximity(_at(miles))
    assert result.band is ProximityBand.NEAR
    assert result.score.value == NEAR_BAND_SCORE


@pytest.mark.parametrize("miles", [25.0, 25.000001, 40.0, 74.0, 74.9, 74.999999])
def test_mid_band_covers_twenty_five_up_to_but_not_including_seventy_five(miles: float):
    result = score_proximity(_at(miles))
    assert result.band is ProximityBand.MID
    assert result.score.value == MID_BAND_SCORE


@pytest.mark.parametrize("miles", [75.0, 75.000001, 100.0, 3000.0])
def test_far_band_covers_seventy_five_and_beyond(miles: float):
    result = score_proximity(_at(miles))
    assert result.band is ProximityBand.FAR
    assert result.score.value == FAR_BAND_SCORE


def test_exactly_twenty_five_miles_is_mid_not_near():
    """G-CBA-05, the boundary ruling stated in words in Proposal 3."""
    assert band_for_miles(25.0) is ProximityBand.MID
    assert score_proximity(_at(25.0)).score.value == MID_BAND_SCORE


def test_exactly_seventy_five_miles_is_far_not_mid():
    """G-CBA-06, second half."""
    assert band_for_miles(75.0) is ProximityBand.FAR
    assert score_proximity(_at(75.0)).score.value == FAR_BAND_SCORE


def test_seventy_four_point_nine_is_mid_and_seventy_five_is_far():
    """G-CBA-06 as the ADR states it, in one assertion pair."""
    assert score_proximity(_at(74.9)).score.value == MID_BAND_SCORE
    assert score_proximity(_at(75.0)).score.value == FAR_BAND_SCORE


def test_boundaries_are_lower_inclusive_upper_exclusive():
    """Every distance falls in exactly one band and none falls in two."""
    for miles in (0.0, 24.9999, 25.0, 74.9999, 75.0, 1e6):
        assert isinstance(band_for_miles(miles), ProximityBand)


def test_a_display_rounding_never_moves_a_candidate_between_bands():
    """Proposal 3: comparison is against the raw float, with no pre-rounding.

    ``24.9996`` renders as ``25.0`` at one decimal place. If the comparison
    were made against the rounded value the candidate would silently become
    Mid, which is a display convention deciding a score.
    """
    result = score_proximity(_at(24.9996))
    assert result.band is ProximityBand.NEAR
    assert result.score.value == NEAR_BAND_SCORE
    assert "25.0 miles" in result.score.basis  # the display *does* round
    assert round(24.9996, 1) == 25.0  # and rounding really would have moved it


def test_the_band_is_a_step_function_with_no_interpolation_inside_it():
    """§10 specifies bands; a band that secretly interpolates is not that."""
    near_values = {score_proximity(_at(m)).score.value for m in (0.0, 12.0, 24.9)}
    mid_values = {score_proximity(_at(m)).score.value for m in (25.0, 50.0, 74.9)}
    far_values = {score_proximity(_at(m)).score.value for m in (75.0, 500.0, 9000.0)}
    assert near_values == {NEAR_BAND_SCORE}
    assert mid_values == {MID_BAND_SCORE}
    assert far_values == {FAR_BAND_SCORE}


def test_the_score_is_monotonically_non_increasing_in_distance():
    values = [score_proximity(_at(m)).score.value for m in (0.0, 24.9, 25.0, 74.9, 75.0, 400.0)]
    assert values == sorted(values, reverse=True)


def test_band_travel_burden_values_match_the_adr_penalty_column():
    """Proposal 3's right-hand column: the penalty scale, ``1 - proximity``."""
    assert score_proximity(_at(10.0)).travel_burden_value == pytest.approx(0.00)
    assert score_proximity(_at(50.0)).travel_burden_value == pytest.approx(0.40)
    assert score_proximity(_at(500.0)).travel_burden_value == pytest.approx(0.80)


def test_band_labels_are_the_proposal_eight_ui_strings():
    assert ProximityBand.NEAR.label == "Near"
    assert ProximityBand.MID.label == "Mid"
    assert ProximityBand.FAR.label == "Far"


def test_a_negative_distance_is_refused_rather_than_clamped():
    with pytest.raises(ValueError):
        ProximityInputs(location=POMONA, distance_miles=-0.1)


def test_a_non_finite_distance_is_refused():
    with pytest.raises(ValueError):
        ProximityInputs(location=POMONA, distance_miles=float("inf"))
    with pytest.raises(ValueError):
        ProximityInputs(location=POMONA, distance_miles=float("nan"))


def test_band_for_miles_refuses_a_negative_distance():
    with pytest.raises(ValueError):
        band_for_miles(-1.0)


# --------------------------------------------------------------------------
# Proposal 4 -- an unknown distance is unknown, and is not the Far band
# --------------------------------------------------------------------------


def test_no_city_and_no_zip_is_unknown_not_the_far_band():
    """G-CBA-07. The tempting shortcut is "probably far"; it is a guess."""
    result = score_proximity(ProximityInputs(location=NO_LOCATION, distance_miles=None))
    assert result.score.value is None
    assert result.score.is_unknown is True
    assert result.score.zero_classification is ZeroClassification.UNKNOWN
    assert result.band is None
    assert result.score.value != FAR_BAND_SCORE
    assert result.distance_miles is None


def test_a_null_location_object_is_also_unknown():
    result = score_proximity(ProximityInputs(location=None, distance_miles=None))
    assert result.score.value is None
    assert result.band is None


def test_a_blank_city_and_blank_zip_are_absent_not_present():
    """A whitespace-only city is a writer that forgot, not a place on file."""
    blank = SpeakerLocation(city="   ", postal_code="\t")
    assert blank.is_absent is True
    assert score_proximity(ProximityInputs(location=blank, distance_miles=None)).band is None


def test_either_a_city_or_a_zip_alone_counts_as_a_location_on_file():
    """§10: "City or ZIP code is sufficient for this phase."."""
    assert ZIP_ONLY.is_absent is False
    assert CITY_ONLY.is_absent is False
    assert NO_LOCATION.is_absent is True


def test_an_unresolved_address_is_unknown_and_says_why():
    """Deferral policy: no geocoder runs here, so a place on file with no
    resolved coordinate is honestly unknown rather than guessed."""
    result = score_proximity(ProximityInputs(location=POMONA, distance_miles=None))
    assert result.score.value is None
    assert result.band is None
    assert "not resolved" in result.score.basis


def test_the_two_unknown_reasons_are_distinguishable_in_the_basis():
    no_place = score_proximity(ProximityInputs(location=NO_LOCATION, distance_miles=None))
    unresolved = score_proximity(ProximityInputs(location=POMONA, distance_miles=None))
    assert no_place.score.basis != unresolved.score.basis
    assert "no postal code" in no_place.score.basis


def test_an_unknown_result_carries_no_estimate_label():
    """As in travel_burden: an unknown has no value to label as an estimate."""
    result = score_proximity(ProximityInputs(location=NO_LOCATION, distance_miles=None))
    assert result.score.estimate_label is None


def test_a_distance_without_a_location_on_file_is_a_contradiction():
    with pytest.raises(ValueError):
        ProximityInputs(location=NO_LOCATION, distance_miles=10.0)


def test_the_unknown_ui_label_is_never_the_word_far():
    result = score_proximity(ProximityInputs(location=NO_LOCATION, distance_miles=None))
    assert result.ui_label == "Unknown — no location on file"
    assert "Far" not in result.ui_label


def test_the_scored_ui_label_is_the_band_name():
    assert score_proximity(_at(10.0)).ui_label == "Near"
    assert score_proximity(_at(50.0)).ui_label == "Mid"
    assert score_proximity(_at(500.0)).ui_label == "Far"


# --------------------------------------------------------------------------
# Proposal 5 -- virtual events: proximity is not scored at all
# --------------------------------------------------------------------------


def test_the_two_scoring_mode_names_are_the_accepted_ones():
    assert CBA_PHYSICAL_SCORING_MODE == "cba-physical-1"
    assert CBA_VIRTUAL_SCORING_MODE == "cba-virtual-1"


def test_proximity_is_scored_under_the_physical_mode_and_not_the_virtual_one():
    assert proximity_is_scored(CBA_PHYSICAL_SCORING_MODE) is True
    assert proximity_is_scored(CBA_VIRTUAL_SCORING_MODE) is False


def test_scoring_a_virtual_run_refuses_rather_than_returning_a_number():
    """G-CBA-08: under ``cba-virtual-1`` there is no proximity factor at all.

    Not ``0.0`` (a measured claim nobody measured) and not ``unknown`` (a
    factor that failed to evaluate). The factor is absent from the model by an
    approved rule, so asking it for a score is a caller error.
    """
    with pytest.raises(VirtualEventProximityError):
        score_proximity(
            ProximityInputs(
                location=POMONA,
                distance_miles=10.0,
                scoring_mode=CBA_VIRTUAL_SCORING_MODE,
            )
        )


def test_an_unrecognised_scoring_mode_is_refused_not_defaulted():
    with pytest.raises(UnknownScoringModeError):
        ProximityInputs(location=POMONA, distance_miles=10.0, scoring_mode="cba-hybrid-1")


def test_the_default_scoring_mode_is_physical():
    assert ProximityInputs(location=POMONA, distance_miles=1.0).scoring_mode == (
        CBA_PHYSICAL_SCORING_MODE
    )


def test_the_assessment_records_the_mode_it_was_scored_under():
    assert score_proximity(_at(10.0)).scoring_mode == CBA_PHYSICAL_SCORING_MODE


def test_this_module_declares_no_weight_at_all():
    """Weight redistribution is another track's deliverable (Proposal 6).

    This factor must not carry ``0.428571``, ``0.357143`` or ``0.214286`` in
    any form: a weight literal here would be a second, unpinned copy of the
    registry's arithmetic.
    """
    source = _MODULE_PATH.read_text()
    for forbidden in ("0.428571", "0.357143", "0.214286", "normalize_weights"):
        assert forbidden not in source


# --------------------------------------------------------------------------
# Provenance: origin seam, formula version, factor identity
# --------------------------------------------------------------------------


def test_the_formula_version_is_pinned():
    assert CBA_PROXIMITY_FORMULA_VERSION == "1.0.0-cba-bands"
    assert score_proximity(_at(10.0)).formula_version == CBA_PROXIMITY_FORMULA_VERSION


def test_the_policy_id_is_pinned_and_named_in_every_scored_basis():
    assert CBA_PROXIMITY_POLICY_ID == "cba-proximity-bands"
    assert CBA_PROXIMITY_POLICY_ID in score_proximity(_at(10.0)).score.basis


def test_the_factor_key_is_stable():
    assert CBA_PROXIMITY_FACTOR_KEY == "proximity"
    assert score_proximity(_at(10.0)).score.factor_key == CBA_PROXIMITY_FACTOR_KEY


def test_the_campus_origin_is_a_versioned_config_value_with_a_stated_source():
    assert CPP_CAMPUS_ORIGIN.identifier == "cpp-main-campus"
    assert CPP_CAMPUS_ORIGIN.version == CPP_CAMPUS_ORIGIN_VERSION
    assert CPP_CAMPUS_ORIGIN.source.strip() != ""
    assert "OQ-CBA-023" in CPP_CAMPUS_ORIGIN.source


def test_the_origin_version_is_marked_provisional_until_the_owner_confirms_it():
    assert CPP_CAMPUS_ORIGIN_VERSION == "0.1.0-provisional"


def test_the_assessment_records_the_origin_it_measured_from():
    assert score_proximity(_at(10.0)).origin is CPP_CAMPUS_ORIGIN


def test_the_origin_version_is_independent_of_the_formula_version():
    """Moving the campus pin is not the same event as changing the bands."""
    assert CPP_CAMPUS_ORIGIN_VERSION != CBA_PROXIMITY_FORMULA_VERSION


def test_a_campus_origin_with_out_of_range_coordinates_is_refused():
    with pytest.raises(ValueError):
        CampusOrigin("x", "X", 91.0, 0.0, "test", "1.0.0")
    with pytest.raises(ValueError):
        CampusOrigin("x", "X", 0.0, 181.0, "test", "1.0.0")


def test_a_campus_origin_with_a_blank_source_is_refused():
    with pytest.raises(ValueError):
        CampusOrigin("x", "X", 0.0, 0.0, "   ", "1.0.0")


def test_an_alternate_origin_can_be_supplied_through_the_seam():
    """The origin is config, not a hard-coded literal inside the arithmetic."""
    elsewhere = CampusOrigin("test-origin", "Test", 0.0, 0.0, "test fixture", "0.0.0-test")
    near_equator = Coordinate(0.1, 0.0)
    miles = distance_miles_from_campus(near_equator, origin=elsewhere)
    assert miles == pytest.approx(6.9, abs=0.2)


# --------------------------------------------------------------------------
# The distance seam itself: miles only, no network, no geocoding
# --------------------------------------------------------------------------


def test_distance_is_reported_in_miles_not_kilometers():
    """One degree of latitude is ~69.09 statute miles (and ~111.19 km)."""
    origin = CampusOrigin("o", "O", 0.0, 0.0, "test fixture", "0.0.0-test")
    miles = distance_miles_from_campus(Coordinate(1.0, 0.0), origin=origin)
    assert miles == pytest.approx(69.09, abs=0.05)
    assert abs(miles - 111.19) > 1.0


def test_no_output_string_mentions_kilometers():
    scored = score_proximity(_at(50.0))
    unknown = score_proximity(ProximityInputs(location=NO_LOCATION, distance_miles=None))
    for text in (scored.score.basis, scored.ui_label, unknown.score.basis, unknown.ui_label):
        assert "km" not in text.lower()
        assert "kilomet" not in text.lower()


def test_distance_from_the_origin_to_itself_is_zero():
    at_campus = Coordinate(CPP_CAMPUS_ORIGIN.latitude, CPP_CAMPUS_ORIGIN.longitude)
    assert distance_miles_from_campus(at_campus) == pytest.approx(0.0)


def test_distance_is_symmetric_about_the_origin():
    north = Coordinate(CPP_CAMPUS_ORIGIN.latitude + 0.5, CPP_CAMPUS_ORIGIN.longitude)
    south = Coordinate(CPP_CAMPUS_ORIGIN.latitude - 0.5, CPP_CAMPUS_ORIGIN.longitude)
    assert distance_miles_from_campus(north) == pytest.approx(distance_miles_from_campus(south))


def test_near_antipodal_points_saturate_rather_than_raise():
    origin = CampusOrigin("o", "O", 59.27902362555744, -62.10239505627078, "fixture", "0.0.0-test")
    antipode = Coordinate(-59.27902362555729, 117.89760494372922)
    assert distance_miles_from_campus(antipode, origin=origin) > 12000.0


def test_an_out_of_range_coordinate_is_refused():
    with pytest.raises(ValueError):
        Coordinate(90.1, 0.0)
    with pytest.raises(ValueError):
        Coordinate(0.0, -180.1)


def test_a_full_pipeline_from_a_coordinate_lands_in_the_expected_band():
    """Resolution is a seam the caller drives; this module only measures."""
    ten_miles_north = Coordinate(CPP_CAMPUS_ORIGIN.latitude + 0.1448, CPP_CAMPUS_ORIGIN.longitude)
    miles = distance_miles_from_campus(ten_miles_north)
    assert miles == pytest.approx(10.0, abs=0.2)
    assert score_proximity(_at(miles)).band is ProximityBand.NEAR


def test_scored_values_carry_the_coarse_estimate_label():
    result = score_proximity(_at(50.0))
    assert result.score.estimate_label == PROXIMITY_ESTIMATE_LABEL
    assert "deferred" in PROXIMITY_ESTIMATE_LABEL


def test_values_are_rounded_to_the_factor_score_precision():
    for miles in (0.0, 25.0, 75.0):
        value = score_proximity(_at(miles)).score.value
        assert value == round(value, FACTOR_SCORE_PRECISION)


def test_module_imports_no_network_or_io():
    tree = ast.parse(_MODULE_PATH.read_text(), filename=str(_MODULE_PATH))
    allowed_roots = {"__future__", "math", "dataclasses", "enum", "typing", "smartmatch_domain"}
    imported_roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imported_roots.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            imported_roots.add(node.module.split(".")[0])
    assert imported_roots <= allowed_roots


def test_module_does_not_geocode_or_call_a_route_provider():
    source = _MODULE_PATH.read_text().lower()
    for forbidden in ("requests.", "httpx", "urllib", "socket."):
        assert forbidden not in source


def test_the_module_does_not_import_the_superseded_travel_burden_factor():
    """Coexistence: the two formulas are versioned apart on purpose, so a
    change to one cannot silently move the other."""
    source = _MODULE_PATH.read_text()
    assert "from smartmatch_domain.factors.travel_burden import" not in source
