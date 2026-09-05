"""Tests for the travel_burden scoring factor."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest
from smartmatch_domain.factor_registry import factor_keys
from smartmatch_domain.factors import FACTOR_SCORE_PRECISION, ZeroClassification
from smartmatch_domain.factors.proximity import (
    CBA_PROXIMITY_FACTOR_KEY,
    CBA_PROXIMITY_FORMULA_VERSION,
    ProximityInputs,
    SpeakerLocation,
    score_proximity,
)
from smartmatch_domain.factors.travel_burden import (
    FREE_RADIUS_KM,
    MAX_BURDEN_KM,
    TRAVEL_BURDEN_FORMULA_VERSION,
    TRAVEL_ESTIMATE_LABEL,
    GeoPoint,
    TravelInputs,
    haversine_km,
    score_travel_burden,
)

_MODULE_PATH = (
    Path(__file__).resolve().parents[2]
    / "python"
    / "smartmatch_domain"
    / "smartmatch_domain"
    / "factors"
    / "travel_burden.py"
)

LOS_ANGELES = GeoPoint(34.0522, -118.2437)


def _north_of(point: GeoPoint, degrees_latitude: float) -> GeoPoint:
    """Offset a point north by ``degrees_latitude`` (~111.19 km per degree)."""
    return GeoPoint(point.latitude + degrees_latitude, point.longitude)


def test_absent_origin_is_unknown_not_zero():
    result = score_travel_burden(TravelInputs(origin=None, destination=LOS_ANGELES))
    assert result.value is None
    assert result.is_unknown is True
    assert result.zero_classification is ZeroClassification.UNKNOWN
    assert result.factor_key == "travel_burden"
    assert result.basis == "professional or event_need coordinates are absent"


def test_absent_destination_is_unknown_not_zero():
    result = score_travel_burden(TravelInputs(origin=LOS_ANGELES, destination=None))
    assert result.value is None
    assert result.is_unknown is True
    assert result.zero_classification is ZeroClassification.UNKNOWN


def test_identical_coordinates_are_measured_zero_burden():
    result = score_travel_burden(TravelInputs(origin=LOS_ANGELES, destination=LOS_ANGELES))
    assert result.value == pytest.approx(0.0)
    assert result.zero_classification is ZeroClassification.MEASURED_ZERO


def test_inside_the_free_radius_is_zero_burden():
    nearby = _north_of(LOS_ANGELES, 0.1)  # approx 11.1 km
    result = score_travel_burden(TravelInputs(origin=LOS_ANGELES, destination=nearby))
    assert result.value == pytest.approx(0.0)


def test_haversine_matches_a_known_separation():
    distance = haversine_km(GeoPoint(0.0, 0.0), GeoPoint(1.0, 0.0))
    assert distance == pytest.approx(111.19, abs=0.05)


def test_haversine_is_symmetric():
    a = GeoPoint(40.7128, -74.0060)
    b = GeoPoint(51.5074, -0.1278)
    assert haversine_km(a, b) == pytest.approx(haversine_km(b, a))


def test_haversine_of_a_point_with_itself_is_zero():
    assert haversine_km(LOS_ANGELES, LOS_ANGELES) == pytest.approx(0.0)


def test_burden_saturates_at_one_beyond_the_maximum():
    far = _north_of(LOS_ANGELES, 2.0)  # approx 222 km, well beyond MAX_BURDEN_KM
    farther = _north_of(LOS_ANGELES, 10.0)  # approx 1112 km
    far_result = score_travel_burden(TravelInputs(origin=LOS_ANGELES, destination=far))
    farther_result = score_travel_burden(TravelInputs(origin=LOS_ANGELES, destination=farther))
    assert far_result.value == pytest.approx(1.0)
    assert farther_result.value == pytest.approx(1.0)


def test_burden_is_monotonic_in_distance():
    offsets = (0.0, 0.1, 0.3, 0.7912, 1.5, 2.0, 5.0)
    values = [
        score_travel_burden(
            TravelInputs(origin=LOS_ANGELES, destination=_north_of(LOS_ANGELES, offset))
        ).value
        for offset in offsets
    ]
    assert all(value is not None for value in values)
    assert values == sorted(values)


def test_midpoint_of_the_band_is_half_burden():
    midpoint = _north_of(LOS_ANGELES, 0.7912)  # approx 88 km
    result = score_travel_burden(TravelInputs(origin=LOS_ANGELES, destination=midpoint))
    assert result.value == pytest.approx(0.5, abs=0.01)
    assert result.factor_key == "travel_burden"
    expected_distance = haversine_km(LOS_ANGELES, midpoint)
    assert result.basis == f"{expected_distance:.1f} km straight-line between synthetic coordinates"


def test_value_is_rounded_to_the_factor_score_precision():
    # An offset picked so the raw (unrounded) burden has more decimal digits
    # than FACTOR_SCORE_PRECISION -- if the round() in score_travel_burden
    # were dropped, this test would catch it.
    destination = _north_of(LOS_ANGELES, 0.31)
    distance = haversine_km(LOS_ANGELES, destination)
    raw_burden = (distance - FREE_RADIUS_KM) / (MAX_BURDEN_KM - FREE_RADIUS_KM)
    result = score_travel_burden(TravelInputs(origin=LOS_ANGELES, destination=destination))
    assert raw_burden != round(raw_burden, FACTOR_SCORE_PRECISION)
    assert result.value == round(raw_burden, FACTOR_SCORE_PRECISION)


def test_value_is_always_within_bounds():
    offsets = (None, 0.0, 0.05, 0.1, 0.5, 0.7912, 1.0, 2.0, 20.0)
    for offset in offsets:
        destination = None if offset is None else _north_of(LOS_ANGELES, offset)
        result = score_travel_burden(TravelInputs(origin=LOS_ANGELES, destination=destination))
        assert result.value is None or 0.0 <= result.value <= 1.0


def test_every_known_value_carries_the_coarse_estimate_label_and_unknown_carries_none():
    """estimate_label is "set when the value is an explicitly coarse estimate".

    An unknown result (``value=None``) has no value to estimate, so it must
    not carry the label; every known (measured) value must.
    """
    unknown_result = score_travel_burden(TravelInputs(origin=None, destination=LOS_ANGELES))
    known_result = score_travel_burden(
        TravelInputs(origin=LOS_ANGELES, destination=_north_of(LOS_ANGELES, 1.0))
    )
    assert unknown_result.estimate_label is None
    assert known_result.estimate_label == TRAVEL_ESTIMATE_LABEL


def test_out_of_range_latitude_is_rejected():
    with pytest.raises(ValueError):
        GeoPoint(90.1, 0.0)


def test_out_of_range_longitude_is_rejected():
    with pytest.raises(ValueError):
        GeoPoint(0.0, 180.1)


def test_module_imports_no_network_or_io():
    tree = ast.parse(_MODULE_PATH.read_text(), filename=str(_MODULE_PATH))
    allowed_roots = {"__future__", "math", "dataclasses", "typing", "smartmatch_domain"}
    imported_roots: set[str] = set()
    # ast.walk (not iter_child_nodes) so a function-local `import httpx`
    # buried inside a nested scope cannot slip past this guard.
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imported_roots.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            imported_roots.add(node.module.split(".")[0])
    assert imported_roots <= allowed_roots


def test_factor_key_is_declared_in_the_registry():
    assert "travel_burden" in factor_keys()


def test_formula_version_is_pinned():
    assert TRAVEL_BURDEN_FORMULA_VERSION == "1.0.0-straight-line"


def test_near_antipodal_points_saturate_rather_than_raise():
    # Confirmed reproducer: floating-point error pushes the haversine
    # intermediate `a` an ulp above 1.0 for this near-antipodal pair, which
    # made math.asin raise ValueError: math domain error before the fix.
    origin = GeoPoint(59.27902362555744, -62.10239505627078)
    destination = GeoPoint(-59.27902362555729, 117.89760494372922)
    distance = haversine_km(origin, destination)  # must not raise
    assert distance > MAX_BURDEN_KM
    result = score_travel_burden(TravelInputs(origin=origin, destination=destination))
    assert result.value == pytest.approx(1.0)


# --------------------------------------------------------------------------
# Coexistence with the CBA proximity factor (ADR-0016)
#
# `travel_burden` is the pre-CBA proximity notion: a continuous haversine
# penalty in kilometers under REGISTRY_VERSION 1.1.1-approved-g1-m6j.
# `factors.proximity` is the CBA notion: a mile step function from the CPP
# campus under the version ADR-0016 Proposal 9 bumps to. Both exist, and the
# tests below exist so a later reader cannot mistake one for a refactor of the
# other, and so a change to one arithmetic cannot silently move the other.
#
# Retiring `travel_burden` is a separate decision about stored runs and the
# registry -- recorded as OQ-CBA-025, not taken here.
# --------------------------------------------------------------------------


def test_the_two_factors_are_versioned_apart():
    """A shared version would make one bump look like the other's."""
    assert TRAVEL_BURDEN_FORMULA_VERSION != CBA_PROXIMITY_FORMULA_VERSION
    assert TRAVEL_BURDEN_FORMULA_VERSION == "1.0.0-straight-line"
    assert CBA_PROXIMITY_FORMULA_VERSION == "1.0.0-cba-bands"


def test_the_two_factors_carry_different_factor_keys():
    unknown = score_travel_burden(TravelInputs(origin=None, destination=LOS_ANGELES))
    assert unknown.factor_key == "travel_burden"
    assert CBA_PROXIMITY_FACTOR_KEY == "proximity"
    assert unknown.factor_key != CBA_PROXIMITY_FACTOR_KEY


def test_travel_burden_is_a_penalty_and_cba_proximity_is_a_suitability():
    """Opposite polarity: the old value rises with distance, the new one falls.

    Reading a `travel_burden` number as a proximity sub-score (or the reverse)
    would invert a candidate's ranking, which is why they are not
    interchangeable even where their scales overlap.
    """
    near = GeoPoint(LOS_ANGELES.latitude + 0.05, LOS_ANGELES.longitude)
    far = GeoPoint(LOS_ANGELES.latitude + 3.0, LOS_ANGELES.longitude)
    assert score_travel_burden(TravelInputs(LOS_ANGELES, near)).value == pytest.approx(0.0)
    assert score_travel_burden(TravelInputs(LOS_ANGELES, far)).value == pytest.approx(1.0)

    near_proximity = score_proximity(
        ProximityInputs(location=SpeakerLocation("Pomona", "91768"), distance_miles=3.0)
    )
    far_proximity = score_proximity(
        ProximityInputs(location=SpeakerLocation("Pomona", "91768"), distance_miles=300.0)
    )
    assert near_proximity.score.value > far_proximity.score.value


def test_travel_burden_interpolates_where_cba_proximity_steps():
    """The load-bearing difference: continuous versus banded.

    Two distances inside one CBA band score identically under the new factor
    and differently under the old one. If a later refactor made `proximity`
    interpolate, or made `travel_burden` band, this test fails.
    """
    thirty_miles_km = 30.0 * 1.609344
    sixty_miles_km = 60.0 * 1.609344
    # Both are inside the CBA Mid band (25 <= d < 75).
    location = SpeakerLocation("Pomona", "91768")
    assert (
        score_proximity(ProximityInputs(location=location, distance_miles=30.0)).score.value
        == score_proximity(ProximityInputs(location=location, distance_miles=60.0)).score.value
    )

    # The old factor separates the same two distances continuously.
    def _burden_at_km(km: float) -> float:
        degrees = km / 111.19
        result = score_travel_burden(
            TravelInputs(origin=LOS_ANGELES, destination=_north_of(LOS_ANGELES, degrees))
        )
        assert result.value is not None
        return result.value

    assert _burden_at_km(thirty_miles_km) < _burden_at_km(sixty_miles_km)


def test_travel_burden_reports_kilometers_and_cba_proximity_reports_miles():
    """§10 says miles; the pre-CBA factor was never asked to."""
    old = score_travel_burden(
        TravelInputs(origin=LOS_ANGELES, destination=_north_of(LOS_ANGELES, 1.0))
    )
    assert "km" in old.basis

    new = score_proximity(
        ProximityInputs(location=SpeakerLocation("Pomona", "91768"), distance_miles=40.0)
    )
    assert "miles" in new.score.basis
    assert "km" not in new.score.basis.lower()


def test_the_two_factors_disagree_about_a_far_speaker_on_purpose():
    """`travel_burden` saturates at 1.0 (max penalty); CBA Far is 0.20, not 0.00.

    Converted to the same scale the disagreement is real: the old factor says
    a 200-mile speaker is maximally burdened, the new one deliberately keeps
    them rankable. This is why a stored 1.x run must not be re-read under the
    2.x rulebook (ADR-0016 Proposal 9).
    """
    far_km_degrees = 320.0 / 111.19  # ~200 miles north
    old = score_travel_burden(
        TravelInputs(origin=LOS_ANGELES, destination=_north_of(LOS_ANGELES, far_km_degrees))
    )
    new = score_proximity(
        ProximityInputs(location=SpeakerLocation("Pomona", "91768"), distance_miles=200.0)
    )
    assert old.value == pytest.approx(1.0)  # old: maximum burden
    assert new.travel_burden_value == pytest.approx(0.80)  # new: Far, still rankable
    assert old.value != new.travel_burden_value


def test_both_factors_agree_that_a_missing_location_is_unknown_and_not_zero():
    """The one thing that must never diverge: ADR-0011 rule 1."""
    old = score_travel_burden(TravelInputs(origin=None, destination=LOS_ANGELES))
    new = score_proximity(
        ProximityInputs(location=SpeakerLocation(None, None), distance_miles=None)
    )
    assert old.value is None
    assert new.score.value is None
    assert old.zero_classification is ZeroClassification.UNKNOWN
    assert new.score.zero_classification is ZeroClassification.UNKNOWN


def test_the_cba_factor_is_not_registered_and_travel_burden_still_is():
    """Registry wiring is the registry track's deliverable, not this one.

    When that track lands, this test is the one that should be updated
    deliberately rather than the one that quietly starts passing differently.
    """
    assert "travel_burden" in factor_keys()
    assert CBA_PROXIMITY_FACTOR_KEY not in factor_keys()
