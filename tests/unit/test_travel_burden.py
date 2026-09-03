"""Tests for the travel_burden scoring factor."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest
from smartmatch_domain.factor_registry import factor_keys
from smartmatch_domain.factors import FACTOR_SCORE_PRECISION, ZeroClassification
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
