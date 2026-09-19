"""The four shared student factors (ADR-0025 D3, design spec §4.2).

Two things this file pins that nothing else can: that an **empty card is not
the same fact as no card** all the way through the three-state rule, and that
the package holds the four functions and nothing that belongs to a deferred
row (OQ-SE-01/02).
"""

from __future__ import annotations

import ast
import dataclasses
import pathlib

import pytest
from smartmatch_domain.factor_registry import PROHIBITED_INPUTS
from smartmatch_domain.factors import FactorState, ZeroClassification
from smartmatch_domain.student_factors import (
    STUDENT_FACTOR_KEYS,
    EventEvidence,
    ProfileCard,
    ProfileEvidence,
    career_goal_fit,
    jaccard,
    normalized_term,
    normalized_terms,
    past_event_topic_overlap,
    same_major,
    stated_interest_overlap,
)

EVENT = EventEvidence(
    event_key="northline",
    topic_tags=("Analytics", "Careers"),
    target_majors=("Marketing", "Business Analytics"),
)


# ---------------------------------------------------------------------------
# same_major — never unknown
# ---------------------------------------------------------------------------


def test_same_major_scores_one_for_a_target_major() -> None:
    score = same_major(ProfileEvidence("p1", "Marketing"), EVENT)
    assert score.value == 1.0
    assert score.state is FactorState.MEASURED


def test_same_major_scores_a_measured_zero_for_another_major() -> None:
    score = same_major(ProfileEvidence("p1", "History"), EVENT)
    assert score.value == 0.0
    assert score.zero_classification is ZeroClassification.MEASURED_ZERO


def test_same_major_is_never_unknown_even_with_no_target_majors() -> None:
    bare = EventEvidence(event_key="northline")
    score = same_major(ProfileEvidence("p1", "History"), bare)
    assert score.value == 0.0
    assert not score.is_unknown


def test_same_major_compares_terms_case_and_space_insensitively() -> None:
    assert same_major(ProfileEvidence("p1", "  marketing "), EVENT).value == 1.0


# ---------------------------------------------------------------------------
# stated_interest_overlap — unknown with no card, measured with an empty one
# ---------------------------------------------------------------------------


def test_stated_interest_overlap_is_unknown_with_no_card() -> None:
    score = stated_interest_overlap(ProfileEvidence("p1", "Marketing"), EVENT)
    assert score.value is None
    assert score.is_unknown
    assert score.zero_classification is ZeroClassification.UNKNOWN


def test_an_empty_card_is_not_no_card() -> None:
    """The distinction ADR-0011 exists for, at the exact boundary it lives on."""
    empty = ProfileEvidence("p1", "Marketing", card=ProfileCard())
    absent = ProfileEvidence("p1", "Marketing", card=None)
    assert stated_interest_overlap(empty, EVENT).value == 0.0
    assert stated_interest_overlap(empty, EVENT).state is FactorState.MEASURED
    assert stated_interest_overlap(absent, EVENT).value is None


def test_stated_interest_overlap_is_the_jaccard_index() -> None:
    card = ProfileCard(("analytics", "sports"))
    score = stated_interest_overlap(ProfileEvidence("p1", "Marketing", card=card), EVENT)
    # {analytics, sports} vs {analytics, careers}: one shared of three distinct.
    assert score.value == pytest.approx(1 / 3, abs=1e-4)


# ---------------------------------------------------------------------------
# career_goal_fit
# ---------------------------------------------------------------------------


def test_career_goal_fit_is_unknown_with_no_card() -> None:
    assert career_goal_fit(ProfileEvidence("p1", "Marketing"), EVENT).value is None


def test_career_goal_fit_matches_a_topic_tag() -> None:
    card = ProfileCard(career_goal="Analytics")
    assert career_goal_fit(ProfileEvidence("p1", "Marketing", card=card), EVENT).value == 1.0


def test_career_goal_fit_is_a_measured_zero_when_the_goal_misses() -> None:
    card = ProfileCard(career_goal="Law")
    score = career_goal_fit(ProfileEvidence("p1", "Marketing", card=card), EVENT)
    assert score.value == 0.0
    assert score.zero_classification is ZeroClassification.MEASURED_ZERO


def test_a_card_with_a_blank_career_goal_is_measured_not_unknown() -> None:
    card = ProfileCard(("analytics",), career_goal=None)
    score = career_goal_fit(ProfileEvidence("p1", "Marketing", card=card), EVENT)
    assert score.value == 0.0
    assert not score.is_unknown


def test_a_blank_string_career_goal_is_refused_rather_than_read_as_absent() -> None:
    with pytest.raises(ValueError, match="career_goal"):
        ProfileCard(career_goal="   ")


# ---------------------------------------------------------------------------
# past_event_topic_overlap
# ---------------------------------------------------------------------------


def test_past_event_topic_overlap_is_unknown_with_no_attendance_record() -> None:
    profile = ProfileEvidence("p1", "Marketing", attended_event_topics=None)
    assert past_event_topic_overlap(profile, EVENT).value is None


def test_past_event_topic_overlap_is_unknown_with_a_record_naming_no_event() -> None:
    profile = ProfileEvidence("p1", "Marketing", attended_event_topics=())
    score = past_event_topic_overlap(profile, EVENT)
    assert score.value is None
    assert "no past events attended" in score.basis


def test_the_two_kinds_of_absence_stay_distinguishable_on_the_evidence() -> None:
    no_record = ProfileEvidence("p1", "Marketing", attended_event_topics=None)
    empty_record = ProfileEvidence("p1", "Marketing", attended_event_topics=())
    assert no_record.has_attendance_record is False
    assert empty_record.has_attendance_record is True
    assert no_record.attended_event_count is None
    assert empty_record.attended_event_count == 0


def test_past_event_topic_overlap_unions_the_attended_events_topics() -> None:
    profile = ProfileEvidence(
        "p1",
        "Marketing",
        attended_event_topics=(("Analytics",), ("Sports", "Analytics")),
    )
    # union {analytics, sports} vs {analytics, careers}: one of three.
    assert past_event_topic_overlap(profile, EVENT).value == pytest.approx(1 / 3, abs=1e-4)


def test_attending_events_that_miss_every_topic_is_a_measured_zero() -> None:
    profile = ProfileEvidence("p1", "Marketing", attended_event_topics=(("Sports",),))
    score = past_event_topic_overlap(profile, EVENT)
    assert score.value == 0.0
    assert score.zero_classification is ZeroClassification.MEASURED_ZERO


# ---------------------------------------------------------------------------
# Terms
# ---------------------------------------------------------------------------


def test_terms_are_compared_as_exact_normalized_strings() -> None:
    assert normalized_term("  Analytics ") == "analytics"
    assert normalized_terms((" A ", "a", "")) == frozenset({"a"})
    assert jaccard(frozenset(), frozenset()) == 0.0


# ---------------------------------------------------------------------------
# What the package must not contain
# ---------------------------------------------------------------------------


def test_no_evidence_dataclass_carries_hidden_true_interests() -> None:
    """ADR-0025 D6: no factor reads the withheld column, so no type holds it."""
    for cls in (ProfileEvidence, ProfileCard, EventEvidence):
        names = {field.name for field in dataclasses.fields(cls)}
        assert "hidden_true_interests" not in names
        assert not any("hidden" in name for name in names)


def _package_sources() -> list[pathlib.Path]:
    import smartmatch_domain.student_factors as package

    root = pathlib.Path(next(iter(package.__path__)))
    return sorted(root.glob("*.py"))


def _code_names(source: pathlib.Path) -> set[str]:
    """Every identifier and non-docstring literal in one module.

    Parsed rather than grepped, so that *documenting* a rule ("no factor reads
    ``hidden_true_interests``") is not mistaken for breaking it. What matters
    is whether the code can reach the name, and a docstring cannot.
    """
    tree = ast.parse(source.read_text())
    docstrings = {
        ast.get_docstring(node, clean=False)
        for node in ast.walk(tree)
        if isinstance(node, ast.Module | ast.ClassDef | ast.FunctionDef)
    }
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            names.add(node.id)
        elif isinstance(node, ast.Attribute):
            names.add(node.attr)
        elif isinstance(node, ast.arg):
            names.add(node.arg)
        elif isinstance(node, ast.keyword) and node.arg is not None:
            names.add(node.arg)
        elif isinstance(node, ast.FunctionDef | ast.ClassDef):
            names.add(node.name)
        elif isinstance(node, ast.alias):
            names.add(node.asname or node.name)
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            if node.value not in docstrings:
                names.add(node.value)
    return names


def test_the_package_never_references_the_withheld_column_name() -> None:
    for source in _package_sources():
        assert "hidden_true_interests" not in _code_names(source), source


def test_the_package_declares_no_registry_and_no_student_ranker() -> None:
    """OQ-SE-01/02 are deferred; a shared module must not ship them early."""
    for source in _package_sources():
        names = _code_names(source)
        assert "STUDENT_REGISTRY" not in names, source
        assert "rank_events_for_student" not in names, source
        assert "FactorRegistry" not in names, source


def test_prohibited_inputs_is_imported_not_redefined() -> None:
    import smartmatch_domain.student_factors.factors as factors_module

    assert factors_module.PROHIBITED_INPUTS is PROHIBITED_INPUTS
    assert not frozenset(STUDENT_FACTOR_KEYS) & PROHIBITED_INPUTS
    for source in _package_sources():
        tree = ast.parse(source.read_text())
        for node in ast.walk(tree):
            targets: list[ast.expr] = []
            if isinstance(node, ast.Assign):
                targets = list(node.targets)
            elif isinstance(node, ast.AnnAssign):
                targets = [node.target]
            for target in targets:
                assert not (
                    isinstance(target, ast.Name) and target.id == "PROHIBITED_INPUTS"
                ), f"{source}: PROHIBITED_INPUTS is imported, never redefined"
