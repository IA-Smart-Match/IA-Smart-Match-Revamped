"""Tests for the industry_match scoring factor.

Customer §7: a speaker has **one primary** NAICS sector; a Speaker Request may
target **several**. The factor is therefore a membership test, and the cases
that matter are the ones where the answer is *not* a number: an unclassified
speaker, an unclassified request, and a request that names nothing at all.

ADR-0016's evidence states bind these tests. A speaker whose sector was read
and is not among the requested sectors scores a **measured** ``0.0`` — a real
claim about a real classification. A speaker whose sector could not be
evaluated is **unknown**. The two must never collapse into each other, so
every unknown case below asserts ``ZeroClassification.UNKNOWN`` and every
non-match asserts ``ZeroClassification.MEASURED_ZERO``.

This factor is deliberately *not* wired into
:mod:`smartmatch_domain.factor_registry` yet — registry wiring is a separate
track — so nothing here asserts membership in ``factor_keys()``.
"""

from __future__ import annotations

import pytest
from smartmatch_domain.factors import FactorScore, ZeroClassification
from smartmatch_domain.factors.industry_match import (
    INDUSTRY_MATCH_FACTOR_KEY,
    INDUSTRY_MATCH_FORMULA_VERSION,
    IndustryMatchInputs,
    score_industry_match,
)
from smartmatch_domain.naics_sectors import (
    NAICS_TAXONOMY_VERSION,
    ClassifiedSector,
    NaicsSector,
    QuarantinedSector,
    resolve_sector,
)


def _classified(raw: str) -> ClassifiedSector:
    resolution = resolve_sector(raw)
    assert isinstance(resolution, ClassifiedSector), raw
    return resolution


def _quarantined(raw: str) -> QuarantinedSector:
    resolution = resolve_sector(raw)
    assert isinstance(resolution, QuarantinedSector), raw
    return resolution


# --------------------------------------------------------------------------
# Exact match
# --------------------------------------------------------------------------


def test_speaker_sector_among_requested_sectors_scores_one():
    result = score_industry_match(
        IndustryMatchInputs(
            speaker_sector=_classified("52"),
            requested_sectors=(_classified("51"), _classified("52")),
        )
    )
    assert isinstance(result, FactorScore)
    assert result.factor_key == INDUSTRY_MATCH_FACTOR_KEY
    assert result.value == pytest.approx(1.0)
    assert result.zero_classification is None
    assert "Finance and Insurance" in result.basis


def test_a_request_naming_one_sector_matches_by_name_or_by_code():
    by_code = score_industry_match(
        IndustryMatchInputs(
            speaker_sector=_classified("31-33"),
            requested_sectors=(_classified("31-33"),),
        )
    )
    by_name = score_industry_match(
        IndustryMatchInputs(
            speaker_sector=_classified("Manufacturing"),
            requested_sectors=(_classified("manufacturing"),),
        )
    )
    assert by_code.value == by_name.value == pytest.approx(1.0)


def test_duplicate_requested_sectors_do_not_change_the_score():
    once = score_industry_match(
        IndustryMatchInputs(
            speaker_sector=_classified("61"),
            requested_sectors=(_classified("61"),),
        )
    )
    thrice = score_industry_match(
        IndustryMatchInputs(
            speaker_sector=_classified("61"),
            requested_sectors=(_classified("61"), _classified("61"), _classified("61")),
        )
    )
    assert once.value == thrice.value == pytest.approx(1.0)


# --------------------------------------------------------------------------
# Non-match — measured zero, never unknown
# --------------------------------------------------------------------------


def test_speaker_sector_outside_the_requested_set_is_a_measured_zero():
    result = score_industry_match(
        IndustryMatchInputs(
            speaker_sector=_classified("51"),
            requested_sectors=(_classified("52"), _classified("62")),
        )
    )
    assert result.value == pytest.approx(0.0)
    assert result.is_unknown is False
    assert result.zero_classification is ZeroClassification.MEASURED_ZERO
    assert "not among" in result.basis


def test_measured_zero_and_unknown_are_distinguishable_on_the_returned_score():
    measured = score_industry_match(
        IndustryMatchInputs(
            speaker_sector=_classified("51"),
            requested_sectors=(_classified("52"),),
        )
    )
    unknown = score_industry_match(
        IndustryMatchInputs(
            speaker_sector=None,
            requested_sectors=(_classified("52"),),
        )
    )
    assert measured.value == pytest.approx(0.0)
    assert unknown.value is None
    assert measured.zero_classification is not unknown.zero_classification


# --------------------------------------------------------------------------
# Missing speaker evidence — unknown
# --------------------------------------------------------------------------


def test_speaker_with_no_industry_classification_is_unknown():
    result = score_industry_match(
        IndustryMatchInputs(
            speaker_sector=None,
            requested_sectors=(_classified("52"),),
        )
    )
    assert result.value is None
    assert result.is_unknown is True
    assert result.zero_classification is ZeroClassification.UNKNOWN


def test_quarantined_speaker_sector_is_unknown_not_a_non_match():
    result = score_industry_match(
        IndustryMatchInputs(
            speaker_sector=_quarantined("Tech"),
            requested_sectors=(_classified("51"),),
        )
    )
    assert result.value is None
    assert result.zero_classification is ZeroClassification.UNKNOWN
    assert "Tech" in result.basis


# --------------------------------------------------------------------------
# Empty / unevaluable request side — unknown
# --------------------------------------------------------------------------


def test_request_naming_no_sectors_is_unknown():
    result = score_industry_match(
        IndustryMatchInputs(
            speaker_sector=_classified("52"),
            requested_sectors=(),
        )
    )
    assert result.value is None
    assert result.zero_classification is ZeroClassification.UNKNOWN


def test_request_whose_sectors_all_quarantined_is_unknown():
    result = score_industry_match(
        IndustryMatchInputs(
            speaker_sector=_classified("52"),
            requested_sectors=(_quarantined("Tech"), _quarantined("Banking")),
        )
    )
    assert result.value is None
    assert result.zero_classification is ZeroClassification.UNKNOWN


def test_a_request_with_one_classified_sector_among_quarantined_ones_is_measurable():
    matched = score_industry_match(
        IndustryMatchInputs(
            speaker_sector=_classified("52"),
            requested_sectors=(_quarantined("Banking"), _classified("52")),
        )
    )
    missed = score_industry_match(
        IndustryMatchInputs(
            speaker_sector=_classified("51"),
            requested_sectors=(_quarantined("Banking"), _classified("52")),
        )
    )
    assert matched.value == pytest.approx(1.0)
    assert missed.value == pytest.approx(0.0)
    assert missed.zero_classification is ZeroClassification.MEASURED_ZERO


# --------------------------------------------------------------------------
# Invalid input — refused, never scored
# --------------------------------------------------------------------------


def test_a_fabricated_sector_row_is_refused():
    fabricated = ClassifiedSector(
        sector=NaicsSector("99", "Speculative Ventures"),
        taxonomy_version=NAICS_TAXONOMY_VERSION,
    )
    with pytest.raises(ValueError, match="not a row of"):
        score_industry_match(
            IndustryMatchInputs(
                speaker_sector=fabricated,
                requested_sectors=(_classified("52"),),
            )
        )


def test_a_speaker_classified_under_another_taxonomy_version_is_refused():
    stale = ClassifiedSector(
        sector=_classified("52").sector,
        taxonomy_version="cba-naics-1999-01-01",
    )
    with pytest.raises(ValueError, match="taxonomy version"):
        score_industry_match(
            IndustryMatchInputs(
                speaker_sector=stale,
                requested_sectors=(_classified("52"),),
            )
        )


def test_a_requested_sector_from_another_taxonomy_version_is_refused():
    stale = QuarantinedSector(raw_value="Tech", taxonomy_version="cba-naics-1999-01-01")
    with pytest.raises(ValueError, match="taxonomy version"):
        score_industry_match(
            IndustryMatchInputs(
                speaker_sector=_classified("52"),
                requested_sectors=(stale,),
            )
        )


# --------------------------------------------------------------------------
# Provenance
# --------------------------------------------------------------------------


def test_every_basis_names_the_taxonomy_version_it_was_evaluated_against():
    scored = (
        score_industry_match(
            IndustryMatchInputs(
                speaker_sector=_classified("52"),
                requested_sectors=(_classified("52"),),
            )
        ),
        score_industry_match(
            IndustryMatchInputs(
                speaker_sector=_classified("51"),
                requested_sectors=(_classified("52"),),
            )
        ),
        score_industry_match(
            IndustryMatchInputs(
                speaker_sector=_quarantined("Tech"),
                requested_sectors=(_classified("52"),),
            )
        ),
        score_industry_match(
            IndustryMatchInputs(
                speaker_sector=_classified("52"),
                requested_sectors=(),
            )
        ),
    )
    for result in scored:
        assert NAICS_TAXONOMY_VERSION in result.basis
        assert result.basis.strip()


def test_scoring_is_deterministic_and_carries_no_estimate_label():
    inputs = IndustryMatchInputs(
        speaker_sector=_classified("52"),
        requested_sectors=(_classified("51"), _classified("52")),
    )
    assert score_industry_match(inputs) == score_industry_match(inputs)
    assert score_industry_match(inputs).estimate_label is None


def test_the_formula_version_is_declared():
    assert INDUSTRY_MATCH_FORMULA_VERSION
    assert INDUSTRY_MATCH_FACTOR_KEY == "industry_match"
