"""The engagement-load multiplier in the CBA composition (B26 T8c, plan §6).

Registry 3.0.0 is ``proposed``. Every 3.x score here is produced with the
registry passed explicitly and its approval gate evaluated through
``tests/unit/registry_evaluation.py``; nothing makes 3.0.0 current.

Every candidate uses G-CBA-09's evidence (sector 52, role finance, topic 0.8,
10.0 mi, physical), whose 2.x composite is 0.97.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import date, timedelta
from decimal import Decimal

import pytest
from smartmatch_domain import scoring
from smartmatch_domain.cba_role_categories import resolve_role_category
from smartmatch_domain.eli import (
    Engagement,
    LoadBand,
    LoadInputs,
    LoadReason,
    compute_eli,
)
from smartmatch_domain.factor_registry import CBA_REGISTRY, CBA_REGISTRY_3
from smartmatch_domain.factors.cba_semantic_topic import SpeakerTopicEvidence
from smartmatch_domain.factors.industry_match import IndustryMatchInputs
from smartmatch_domain.factors.proximity import CBA_PHYSICAL_SCORING_MODE, SpeakerLocation
from smartmatch_domain.factors.role_match import RoleMatchInputs
from smartmatch_domain.load_bands import AssessedLoad
from smartmatch_domain.naics_sectors import resolve_sector
from smartmatch_domain.scoring import (
    CBA_LOAD_STAGE_B_FORMULA_VERSION,
    CBA_STAGE_B_FORMULA_VERSION,
    CbaCandidateEvidence,
    rank_cba_candidates,
    score_cba_candidate,
)
from smartmatch_providers.topic_semantics import FixtureSemanticTopicProvider

from tests.unit.registry_evaluation import evaluate_registry_3

AS_OF = date(2026, 10, 6)
DESCRIPTION = "A panel on financial planning for small businesses."
TOPIC_TEXT = "corporate treasury and financial planning"


def _provider() -> FixtureSemanticTopicProvider:
    provider = FixtureSemanticTopicProvider()
    provider.record(DESCRIPTION, TOPIC_TEXT, score=0.8, rationale="Treasury work fits.")
    return provider


def _evidence(
    subject: str, *, load: AssessedLoad | None = None, profile: bool = True
) -> CbaCandidateEvidence:
    return CbaCandidateEvidence(
        subject_id=subject,
        industry=IndustryMatchInputs(
            speaker_sector=resolve_sector("52"), requested_sectors=(resolve_sector("52"),)
        ),
        role=RoleMatchInputs(
            speaker_role=resolve_role_category("finance"),
            requested_roles=(resolve_role_category("finance"),),
        ),
        topic_evidence=(
            SpeakerTopicEvidence.from_profile(topic_text=TOPIC_TEXT, prior_talk=None)
            if profile
            else SpeakerTopicEvidence.no_profile_record()
        ),
        location=SpeakerLocation(city="Pomona", postal_code="91768"),
        distance_miles=10.0,
        load=load,
    )


def _load(hours: int | None, *, capacity: str | None = "100.0") -> AssessedLoad:
    engagements = (
        ()
        if hours is None
        else (
            Engagement(
                ref="r-1",
                event_date=AS_OF - timedelta(days=10),
                duration=timedelta(hours=hours),
                confirmed=True,
                attended=True,
                cancelled=False,
            ),
        )
    )
    assessment = compute_eli(
        LoadInputs(
            as_of=AS_OF,
            engagements=engagements,
            declared_capacity_hours=None if capacity is None else Decimal(capacity),
        )
    )
    return AssessedLoad(as_of=AS_OF, assessment=assessment)


LIGHT = _load(None)
MODERATE = _load(50)
HEAVY = _load(80)
FULL = _load(101)
UNKNOWN = _load(30, capacity=None)


def _score3(evidence: CbaCandidateEvidence):
    return score_cba_candidate(
        evidence,
        request_description=DESCRIPTION,
        topic_provider=_provider(),
        scoring_mode=CBA_PHYSICAL_SCORING_MODE,
        registry=CBA_REGISTRY_3,
    )


def _score2(evidence: CbaCandidateEvidence):
    return score_cba_candidate(
        evidence,
        request_description=DESCRIPTION,
        topic_provider=_provider(),
        scoring_mode=CBA_PHYSICAL_SCORING_MODE,
    )


@pytest.fixture
def registry_3(monkeypatch):
    evaluate_registry_3(monkeypatch)


def test_the_loads_are_the_bands_they_claim():
    assert LIGHT.assessment.band is LoadBand.LIGHT
    assert MODERATE.assessment.band is LoadBand.MODERATE
    assert HEAVY.assessment.band is LoadBand.HEAVY
    assert FULL.assessment.band is LoadBand.FULL
    assert UNKNOWN.assessment.band is LoadBand.UNKNOWN
    assert UNKNOWN.assessment.reason is LoadReason.CAPACITY_NOT_STATED


def test_3_x_scoring_is_refused_by_the_real_gate():
    """No helper: the proposed registry fails closed."""
    from smartmatch_domain.factor_registry import RegistryNotApprovedError

    with pytest.raises(RegistryNotApprovedError):
        _score3(_evidence("SYNTH-LOAD-GATE", load=LIGHT))


# 18
def test_2_x_scoring_refuses_a_load():
    with pytest.raises(ValueError, match="load"):
        _score2(_evidence("SYNTH-LOAD-2X", load=LIGHT))


def test_3_x_scoring_requires_a_load(registry_3):
    with pytest.raises(ValueError, match="load"):
        _score3(_evidence("SYNTH-LOAD-MISSING"))


# 19
def test_full_cannot_reach_stage_b(registry_3):
    with pytest.raises(ValueError, match="Stage A"):
        rank_cba_candidates(
            [_evidence("SYNTH-LOAD-FULL", load=FULL)],
            request_description=DESCRIPTION,
            topic_provider=_provider(),
            scoring_mode=CBA_PHYSICAL_SCORING_MODE,
            registry=CBA_REGISTRY_3,
        )


# 20
def test_multiplier_applies_to_the_unrounded_composite(registry_3):
    moderate = _score3(_evidence("SYNTH-LOAD-MODERATE", load=MODERATE))
    heavy = _score3(_evidence("SYNTH-LOAD-HEAVY", load=HEAVY))
    assert moderate.value == 0.873
    assert heavy.value == 0.679
    assert repr(moderate.composite_before_load) == "0.97"
    assert repr(heavy.composite_before_load) == "0.97"
    assert moderate.load is MODERATE
    assert heavy.load is HEAVY
    assert heavy.value == round(0.97 * 0.7, 6)


# 21
def test_light_and_unknown_equal_the_2_x_value_bit_for_bit(registry_3):
    baseline = _score2(_evidence("SYNTH-LOAD-BASE")).value
    assert baseline == 0.97
    for load in (LIGHT, UNKNOWN):
        score = _score3(_evidence("SYNTH-LOAD-BASE", load=load))
        assert score.value == baseline
        assert score.value.hex() == baseline.hex()


def test_ranking_under_3_x_follows_the_multiplied_values(registry_3):
    ranked = rank_cba_candidates(
        [
            _evidence("SYNTH-LOAD-C-HEAVY", load=HEAVY),
            _evidence("SYNTH-LOAD-A-LIGHT", load=LIGHT),
            _evidence("SYNTH-LOAD-B-MODERATE", load=MODERATE),
        ],
        request_description=DESCRIPTION,
        topic_provider=_provider(),
        scoring_mode=CBA_PHYSICAL_SCORING_MODE,
        registry=CBA_REGISTRY_3,
    )
    assert [score.subject_id for score in ranked] == [
        "SYNTH-LOAD-A-LIGHT",
        "SYNTH-LOAD-B-MODERATE",
        "SYNTH-LOAD-C-HEAVY",
    ]
    assert {score.registry_version for score in ranked} == {CBA_REGISTRY_3.version}


# 22
def test_unknown_factor_keeps_none_and_still_records_the_load(registry_3):
    score = _score3(_evidence("SYNTH-LOAD-NO-PROFILE", load=HEAVY, profile=False))
    assert score.value is None
    assert score.composite_before_load is None
    assert score.load is HEAVY
    assert "cba_semantic_topic" in score.unknown_factor_keys


# 23
def test_formula_version_moves_only_under_3_x(registry_3):
    assert _score2(_evidence("SYNTH-LOAD-V2")).formula_version == CBA_STAGE_B_FORMULA_VERSION
    assert CBA_STAGE_B_FORMULA_VERSION == "2.0.0-cba"
    three = _score3(_evidence("SYNTH-LOAD-V3", load=LIGHT))
    assert three.formula_version == CBA_LOAD_STAGE_B_FORMULA_VERSION == "3.0.0-cba-load"
    two = _score2(_evidence("SYNTH-LOAD-V2"))
    assert two.load is None
    assert two.composite_before_load is None


# 24
def test_eli_formula_mismatch_is_refused(registry_3):
    stale = AssessedLoad(as_of=AS_OF, assessment=replace(LIGHT.assessment, formula_version="1.0.0"))
    with pytest.raises(ValueError, match="formula"):
        _score3(_evidence("SYNTH-LOAD-STALE", load=stale))


# 25
def test_score_cba_candidate_calls_zero_argument_gates_on_the_cba_path(monkeypatch):
    calls: list[tuple[str, dict[str, object]]] = []

    def approved() -> None:
        calls.append(("approved", {}))

    def ready() -> None:
        calls.append(("ready", {}))

    monkeypatch.setattr(scoring, "assert_registry_approved", approved)
    monkeypatch.setattr(scoring, "assert_scoring_ready", ready)
    _score2(_evidence("SYNTH-LOAD-SEAM"))
    assert calls == [("approved", {}), ("ready", {})]

    calls.clear()

    def approved_kw(**kwargs: object) -> None:
        calls.append(("approved", kwargs))

    def ready_kw(**kwargs: object) -> None:
        calls.append(("ready", kwargs))

    monkeypatch.setattr(scoring, "assert_registry_approved", approved_kw)
    monkeypatch.setattr(scoring, "assert_scoring_ready", ready_kw)
    _score3(_evidence("SYNTH-LOAD-SEAM-3", load=LIGHT))
    assert calls == [
        ("approved", {"registry": CBA_REGISTRY_3}),
        ("ready", {"registry": CBA_REGISTRY_3}),
    ]
    assert CBA_REGISTRY.load_bands is None


def test_applied_weights_takes_a_registry_and_defaults_to_2_0_0():
    from smartmatch_domain.factor_registry import CBA_3_PHYSICAL_MODEL, CBA_PHYSICAL_MODEL
    from smartmatch_domain.weight_settings import applied_weights

    two = applied_weights(None, model=CBA_PHYSICAL_MODEL)
    three = applied_weights(None, model=CBA_3_PHYSICAL_MODEL, registry=CBA_REGISTRY_3)
    assert dict(two) == dict(three)
    assert "engagement_load" not in three
    overridden = applied_weights(
        {"engagement_load": 0.5, "proximity": 0.0},
        model=CBA_3_PHYSICAL_MODEL,
        registry=CBA_REGISTRY_3,
    )
    assert "engagement_load" not in overridden
    assert overridden["proximity"] == 0.0
