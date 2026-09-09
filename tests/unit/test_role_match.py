"""Tests for the role_match scoring factor.

Customer §8: a speaker "should normally have **one primary** role category";
a Speaker Request may target **several** and "must not be restricted to one".
So this factor, like ``industry_match``, is a membership test of one value
against a set — not a set-overlap ratio, because on the speaker side there is
nothing to take a ratio of.

The role taxonomy is a **career discipline**, not an ADR-0012 event-function
tag. ``test_role_match_never_reaches_the_event_tag_vocabulary`` holds that
line here so a future edit cannot quietly reuse `panelist` or `keynote` as a
role category.

ADR-0016's evidence states bind these tests exactly as they bind
``test_industry_match.py``: a role that was read and does not match is a
**measured** ``0.0``; a role that could not be evaluated is **unknown**.

Registry wiring is a separate track, so nothing here asserts membership in
``factor_keys()``.
"""

from __future__ import annotations

import pytest
from smartmatch_domain.cba_role_categories import (
    CBA_ROLE_TAXONOMY_VERSION,
    CbaRoleCategory,
    ClassifiedRoleCategory,
    QuarantinedRoleCategory,
    resolve_role_category,
)
from smartmatch_domain.factors import FactorScore, ZeroClassification
from smartmatch_domain.factors.role_match import (
    ROLE_MATCH_FACTOR_KEY,
    ROLE_MATCH_FORMULA_VERSION,
    RoleMatchInputs,
    score_role_match,
)


def _classified(raw: str) -> ClassifiedRoleCategory:
    resolution = resolve_role_category(raw)
    assert isinstance(resolution, ClassifiedRoleCategory), raw
    return resolution


def _quarantined(raw: str) -> QuarantinedRoleCategory:
    resolution = resolve_role_category(raw)
    assert isinstance(resolution, QuarantinedRoleCategory), raw
    return resolution


# --------------------------------------------------------------------------
# Exact match
# --------------------------------------------------------------------------


def test_speaker_role_among_requested_roles_scores_one():
    result = score_role_match(
        RoleMatchInputs(
            speaker_role=_classified("finance"),
            requested_roles=(_classified("accounting"), _classified("finance")),
        )
    )
    assert isinstance(result, FactorScore)
    assert result.factor_key == ROLE_MATCH_FACTOR_KEY
    assert result.value == pytest.approx(1.0)
    assert result.zero_classification is None
    assert "Finance" in result.basis


def test_a_role_matches_by_stored_code_or_by_display_name():
    by_code = score_role_match(
        RoleMatchInputs(
            speaker_role=_classified("management_strategy"),
            requested_roles=(_classified("management_strategy"),),
        )
    )
    by_name = score_role_match(
        RoleMatchInputs(
            speaker_role=_classified("Management & Strategy"),
            requested_roles=(_classified("management & strategy"),),
        )
    )
    assert by_code.value == by_name.value == pytest.approx(1.0)


def test_duplicate_requested_roles_do_not_change_the_score():
    once = score_role_match(
        RoleMatchInputs(
            speaker_role=_classified("marketing"),
            requested_roles=(_classified("marketing"),),
        )
    )
    twice = score_role_match(
        RoleMatchInputs(
            speaker_role=_classified("marketing"),
            requested_roles=(_classified("marketing"), _classified("Marketing")),
        )
    )
    assert once.value == twice.value == pytest.approx(1.0)


# --------------------------------------------------------------------------
# Non-match — measured zero, never unknown
# --------------------------------------------------------------------------


def test_speaker_role_outside_the_requested_set_is_a_measured_zero():
    result = score_role_match(
        RoleMatchInputs(
            speaker_role=_classified("human_resources"),
            requested_roles=(_classified("finance"), _classified("accounting")),
        )
    )
    assert result.value == pytest.approx(0.0)
    assert result.is_unknown is False
    assert result.zero_classification is ZeroClassification.MEASURED_ZERO
    assert "not among" in result.basis


def test_measured_zero_and_unknown_are_distinguishable_on_the_returned_score():
    measured = score_role_match(
        RoleMatchInputs(
            speaker_role=_classified("human_resources"),
            requested_roles=(_classified("finance"),),
        )
    )
    unknown = score_role_match(
        RoleMatchInputs(
            speaker_role=None,
            requested_roles=(_classified("finance"),),
        )
    )
    assert measured.value == pytest.approx(0.0)
    assert unknown.value is None
    assert measured.zero_classification is not unknown.zero_classification


# --------------------------------------------------------------------------
# Missing speaker evidence — unknown
# --------------------------------------------------------------------------


def test_speaker_with_no_role_classification_is_unknown():
    result = score_role_match(
        RoleMatchInputs(
            speaker_role=None,
            requested_roles=(_classified("finance"),),
        )
    )
    assert result.value is None
    assert result.is_unknown is True
    assert result.zero_classification is ZeroClassification.UNKNOWN


def test_quarantined_speaker_role_is_unknown_not_a_non_match():
    result = score_role_match(
        RoleMatchInputs(
            speaker_role=_quarantined("HR"),
            requested_roles=(_classified("human_resources"),),
        )
    )
    assert result.value is None
    assert result.zero_classification is ZeroClassification.UNKNOWN
    assert "HR" in result.basis


# --------------------------------------------------------------------------
# Empty / unevaluable request side — unknown
# --------------------------------------------------------------------------


def test_request_naming_no_roles_is_unknown():
    result = score_role_match(
        RoleMatchInputs(
            speaker_role=_classified("finance"),
            requested_roles=(),
        )
    )
    assert result.value is None
    assert result.zero_classification is ZeroClassification.UNKNOWN


def test_request_whose_roles_all_quarantined_is_unknown():
    result = score_role_match(
        RoleMatchInputs(
            speaker_role=_classified("finance"),
            requested_roles=(_quarantined("HR"), _quarantined("Ops")),
        )
    )
    assert result.value is None
    assert result.zero_classification is ZeroClassification.UNKNOWN


def test_a_request_with_one_classified_role_among_quarantined_ones_is_measurable():
    matched = score_role_match(
        RoleMatchInputs(
            speaker_role=_classified("finance"),
            requested_roles=(_quarantined("Ops"), _classified("finance")),
        )
    )
    missed = score_role_match(
        RoleMatchInputs(
            speaker_role=_classified("marketing"),
            requested_roles=(_quarantined("Ops"), _classified("finance")),
        )
    )
    assert matched.value == pytest.approx(1.0)
    assert missed.value == pytest.approx(0.0)
    assert missed.zero_classification is ZeroClassification.MEASURED_ZERO


# --------------------------------------------------------------------------
# Invalid input — refused, never scored
# --------------------------------------------------------------------------


def test_a_fabricated_role_row_is_refused():
    fabricated = ClassifiedRoleCategory(
        category=CbaRoleCategory("chief_vibes", "Chief Vibes Officer"),
        taxonomy_version=CBA_ROLE_TAXONOMY_VERSION,
    )
    with pytest.raises(ValueError, match="not a row of"):
        score_role_match(
            RoleMatchInputs(
                speaker_role=fabricated,
                requested_roles=(_classified("finance"),),
            )
        )


def test_a_speaker_classified_under_another_taxonomy_version_is_refused():
    stale = ClassifiedRoleCategory(
        category=_classified("finance").category,
        taxonomy_version="cba-roles-1999-01-01",
    )
    with pytest.raises(ValueError, match="taxonomy version"):
        score_role_match(
            RoleMatchInputs(
                speaker_role=stale,
                requested_roles=(_classified("finance"),),
            )
        )


def test_a_requested_role_from_another_taxonomy_version_is_refused():
    stale = QuarantinedRoleCategory(raw_value="HR", taxonomy_version="cba-roles-1999-01-01")
    with pytest.raises(ValueError, match="taxonomy version"):
        score_role_match(
            RoleMatchInputs(
                speaker_role=_classified("finance"),
                requested_roles=(stale,),
            )
        )


def test_role_match_never_reaches_the_event_tag_vocabulary():
    """ADR-0012 event functions are not CBA career roles and cannot be scored here."""
    for event_function in ("panelist", "keynote", "judge", "mentor"):
        assert isinstance(resolve_role_category(event_function), QuarantinedRoleCategory)
        result = score_role_match(
            RoleMatchInputs(
                speaker_role=_quarantined(event_function),
                requested_roles=(_classified("finance"),),
            )
        )
        assert result.value is None
        assert result.zero_classification is ZeroClassification.UNKNOWN


# --------------------------------------------------------------------------
# Provenance
# --------------------------------------------------------------------------


def test_every_basis_names_the_taxonomy_version_it_was_evaluated_against():
    scored = (
        score_role_match(
            RoleMatchInputs(
                speaker_role=_classified("finance"),
                requested_roles=(_classified("finance"),),
            )
        ),
        score_role_match(
            RoleMatchInputs(
                speaker_role=_classified("marketing"),
                requested_roles=(_classified("finance"),),
            )
        ),
        score_role_match(
            RoleMatchInputs(
                speaker_role=_quarantined("HR"),
                requested_roles=(_classified("finance"),),
            )
        ),
        score_role_match(
            RoleMatchInputs(
                speaker_role=_classified("finance"),
                requested_roles=(),
            )
        ),
    )
    for result in scored:
        assert CBA_ROLE_TAXONOMY_VERSION in result.basis
        assert result.basis.strip()


def test_scoring_is_deterministic_and_carries_no_estimate_label():
    inputs = RoleMatchInputs(
        speaker_role=_classified("finance"),
        requested_roles=(_classified("accounting"), _classified("finance")),
    )
    assert score_role_match(inputs) == score_role_match(inputs)
    assert score_role_match(inputs).estimate_label is None


def test_the_formula_version_is_declared():
    assert ROLE_MATCH_FORMULA_VERSION
    assert ROLE_MATCH_FACTOR_KEY == "role_match"
