"""ADR-0011 held at the explanation boundary (card M9).

``tests/unit/test_matching_approved_golden.py`` proves the *scorers* keep an
unknown and a measured zero apart. This file proves the layer between a scorer
and a screen keeps them apart too — which is where the legacy system lost the
distinction, not in the arithmetic.

Three properties, each asserted rather than assumed:

1. A factor with no evidence explains as ``state="unknown"`` with ``value=None``
   and ``zero_classification="unknown"``. A factor measured at zero explains as
   ``state="measured"``, ``value=0.0``, ``zero_classification="measured_zero"``.
   The two are distinguishable from the explanation alone, without consulting
   the evidence that produced it.
2. Those facts survive the round trip through a durable ``job.payload``, and a
   payload in which they have been made to disagree is **refused** rather than
   repaired.
3. Every explanation carries the ratified presentation contract: the label
   "heuristic score", the registry version, and no percentage anywhere.
"""

from __future__ import annotations

import copy
from decimal import Decimal

import pytest
from smartmatch_domain.explanation import (
    MAX_SHORTLIST_SIZE,
    MIN_SHORTLIST_SIZE,
    SCORE_PROVENANCE_LABEL,
    CandidateExplanation,
    FactorExplanation,
    ScoreState,
    explain_candidate,
    explain_candidates,
    explanation_from_payload,
    explanation_to_payload,
)
from smartmatch_domain.factor_registry import REGISTRY_VERSION, SUPERSEDED_REGISTRY_VERSION
from smartmatch_domain.factors.topic_relevance import TopicRelevanceInputs
from smartmatch_domain.factors.travel_burden import GeoPoint, TravelInputs
from smartmatch_domain.scoring import CandidateEvidence, rank_candidates, score_candidate

from tests.unit.registry_evaluation import evaluate_registry_3
from tests.unit.test_scoring_load import (
    HEAVY,
    LIGHT,
    MODERATE,
    UNKNOWN,
    _score2,
    _score3,
)
from tests.unit.test_scoring_load import _evidence as _cba_evidence

#: Two synthetic coordinates a short distance apart, so travel burden is
#: measured rather than saturated. Ordinary decimals, written here rather than
#: copied from anywhere real.
_HERE = GeoPoint(latitude=34.05, longitude=-118.25)
_NEARBY = GeoPoint(latitude=34.06, longitude=-118.26)

_REQUIRED = ("analytics", "ethics")


def _evidence(
    subject: str,
    *,
    expertise: tuple[str, ...] | None,
    origin: GeoPoint | None,
    destination: GeoPoint | None = _HERE,
) -> CandidateEvidence:
    return CandidateEvidence(
        subject_id=subject,
        topic=TopicRelevanceInputs(expertise_topics=expertise, required_topics=_REQUIRED),
        travel=TravelInputs(origin=origin, destination=destination),
    )


def _factor(explanation: CandidateExplanation, factor_key: str) -> FactorExplanation:
    return next(item for item in explanation.factors if item.factor_key == factor_key)


# ---------------------------------------------------------------------------
# 1 — unknown and measured zero are two different facts
# ---------------------------------------------------------------------------


def test_a_factor_with_no_evidence_explains_as_unknown_and_carries_no_value() -> None:
    """No expertise record on file is unknown, and unknown has no number.

    This is the case the G1 worksheet classifies as ``G1-GC-005`` ("Topics
    absent" -> "Unknown", not 0%). If this ever produced ``value=0.0`` the
    legacy "Topic Relevance 0%" surface would be back, under a registry that
    was supposed to have made it impossible.
    """
    explanation = explain_candidate(
        score_candidate(_evidence("subj-unknown", expertise=None, origin=_NEARBY))
    )

    topic = _factor(explanation, "topic_relevance")
    assert topic.state is ScoreState.UNKNOWN
    assert topic.value is None
    assert topic.zero_classification == "unknown"
    assert topic.basis.strip(), "an unknown carries a reason, never a blank"


def test_a_factor_measured_at_zero_explains_as_a_measured_zero_with_its_value() -> None:
    """Recorded expertise that does not overlap is a genuine, showable zero.

    ``G1-GC-006`` ("Topics disjoint" -> measured_zero -> "Show 0% with
    source"). The distinguishing evidence is a *recorded* expertise tuple: the
    record exists and demonstrably covers none of the required topics.
    """
    explanation = explain_candidate(
        score_candidate(_evidence("subj-disjoint", expertise=("basket weaving",), origin=_NEARBY))
    )

    topic = _factor(explanation, "topic_relevance")
    assert topic.state is ScoreState.MEASURED
    assert topic.value == 0.0
    assert topic.zero_classification == "measured_zero"


def test_an_empty_expertise_record_is_a_measured_zero_not_an_unknown() -> None:
    """``()`` and ``None`` are different submissions and stay different.

    The record exists and is empty, which is measurable — and measurably zero
    against any declared topic. Collapsing this into the unknown branch would
    lose a fact the professional could act on.
    """
    explanation = explain_candidate(
        score_candidate(_evidence("subj-empty", expertise=(), origin=_NEARBY))
    )

    topic = _factor(explanation, "topic_relevance")
    assert topic.state is ScoreState.MEASURED
    assert topic.value == 0.0
    assert topic.zero_classification == "measured_zero"


def test_one_unknown_factor_makes_the_composite_unknown_and_says_which() -> None:
    """ADR-0011's aggregate rule, reported rather than silently applied.

    The remaining weight is never re-spread over the known subset — that would
    let an evidence-free candidate outrank an evidenced one — so a candidate
    with no coordinates has no heuristic score at all, and
    ``unknown_factor_keys`` names the reason.
    """
    explanation = explain_candidate(
        score_candidate(_evidence("subj-no-coords", expertise=_REQUIRED, origin=None))
    )

    assert explanation.state is ScoreState.UNKNOWN
    assert explanation.heuristic_score is None
    assert explanation.unknown_factor_keys == ("travel_burden",)
    assert not explanation.is_shortlistable

    # The *measured* factor is still reported with its value. An unknown
    # composite does not erase the evidence that was present.
    topic = _factor(explanation, "topic_relevance")
    assert topic.state is ScoreState.MEASURED
    assert topic.value == 1.0


def test_an_unknown_factor_is_listed_rather_than_dropped() -> None:
    """ "No evidence for travel" must not look like "travel was not scored"."""
    explanation = explain_candidate(
        score_candidate(_evidence("subj-no-coords", expertise=_REQUIRED, origin=None))
    )

    assert [item.factor_key for item in explanation.factors] == [
        "topic_relevance",
        "travel_burden",
    ]
    travel = _factor(explanation, "travel_burden")
    assert travel.state is ScoreState.UNKNOWN
    assert travel.value is None
    assert travel.weight > 0.0, "an unknown factor still reports the weight it would have carried"


# ---------------------------------------------------------------------------
# 2 — the distinction survives storage, and a corrupted payload is refused
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("subject", "expertise", "origin"),
    [
        ("subj-measured", _REQUIRED, _NEARBY),
        ("subj-measured-zero", (), _NEARBY),
        ("subj-unknown-topic", None, _NEARBY),
        ("subj-unknown-travel", _REQUIRED, None),
    ],
)
def test_an_explanation_round_trips_through_a_durable_payload_unchanged(
    subject: str, expertise: tuple[str, ...] | None, origin: GeoPoint | None
) -> None:
    """What is stored on ``job.payload`` reads back as the same facts.

    Parametrized over all four shapes — measured, measured zero, unknown for
    each factor — because a serializer that lost the distinction would very
    likely still round-trip the ordinary case.
    """
    original = explain_candidate(
        score_candidate(_evidence(subject, expertise=expertise, origin=origin))
    )

    restored = explanation_from_payload(explanation_to_payload(original))

    assert restored == original


def test_a_payload_whose_state_and_value_disagree_is_refused_not_repaired() -> None:
    """An edited row cannot resurrect the unknown-as-zero collapse.

    A reader that "helpfully" filled a missing value with ``0.0``, or inferred
    ``measured`` from the presence of one, would make the read path the place
    the defect came back. The refusal names the field.
    """
    payload = explanation_to_payload(
        explain_candidate(score_candidate(_evidence("subj-x", expertise=None, origin=_NEARBY)))
    )
    payload["factors"][0]["value"] = 0.0  # unknown, now wearing a measurement

    with pytest.raises(ValueError, match="disagree"):
        explanation_from_payload(payload)


def test_a_payload_missing_its_state_discriminator_is_refused() -> None:
    """Absent ``state`` is not "probably measured"; it is unreadable."""
    payload = explanation_to_payload(
        explain_candidate(score_candidate(_evidence("subj-y", expertise=_REQUIRED, origin=_NEARBY)))
    )
    del payload["state"]

    with pytest.raises(ValueError, match="state"):
        explanation_from_payload(payload)


def test_a_boolean_is_not_read_as_a_number() -> None:
    """``true`` must not become ``1.0`` — ``bool`` subclasses ``int``.

    The same trap ``PortfolioCandidate`` names. Here it would manufacture a
    heuristic score out of a flag.
    """
    payload = explanation_to_payload(
        explain_candidate(score_candidate(_evidence("subj-z", expertise=_REQUIRED, origin=_NEARBY)))
    )
    payload["heuristic_score"] = True

    with pytest.raises(ValueError, match="must be a number"):
        explanation_from_payload(payload)


# ---------------------------------------------------------------------------
# 3 — the ratified presentation contract
# ---------------------------------------------------------------------------


def test_every_explanation_carries_the_heuristic_score_label_and_the_registry_version() -> None:
    """The two facts the G1 worksheet requires on every displayed score."""
    explanations = explain_candidates(
        rank_candidates(
            [
                _evidence("subj-a", expertise=_REQUIRED, origin=_NEARBY),
                _evidence("subj-b", expertise=("analytics",), origin=_NEARBY),
                _evidence("subj-c", expertise=None, origin=_NEARBY),
            ]
        )
    )

    assert len(explanations) == 3
    for explanation in explanations:
        assert explanation.score_label == SCORE_PROVENANCE_LABEL == "heuristic score"
        # These explanations come from ``score_candidate``, the superseded
        # two-factor composition, so they carry the pin of the rulebook that
        # declares those two factors — never today's REGISTRY_VERSION.
        assert explanation.registry_version == SUPERSEDED_REGISTRY_VERSION
        assert explanation.registry_version != REGISTRY_VERSION
        assert explanation.registry_version.strip()


def test_the_shortlist_bounds_are_the_ratified_two_to_three() -> None:
    """The presentation rule is a constant, not a number typed into a router."""
    assert (MIN_SHORTLIST_SIZE, MAX_SHORTLIST_SIZE) == (2, 3)


def test_no_score_is_expressed_as_a_percentage() -> None:
    """Values stay in the unit interval, and no field formats one.

    The worksheet forbids a ranked percentage display, and the way to make that
    hold is for no percentage to exist to display: every number that leaves
    here is in ``[0.0, 1.0]`` and no string in the payload carries a percent
    sign.
    """
    payload = explanation_to_payload(
        explain_candidate(score_candidate(_evidence("subj-p", expertise=_REQUIRED, origin=_NEARBY)))
    )

    assert payload["heuristic_score"] is not None
    assert 0.0 <= payload["heuristic_score"] <= 1.0
    for factor in payload["factors"]:
        assert factor["value"] is None or 0.0 <= factor["value"] <= 1.0
        assert "%" not in factor["basis"]
    assert "%" not in payload["score_label"]


def test_a_construction_that_disagrees_with_itself_is_rejected_at_the_type() -> None:
    """The invariant is on the type, so no caller can assemble a violation."""
    with pytest.raises(ValueError, match="disagree"):
        FactorExplanation(
            factor_key="topic_relevance",
            display_label="Topic Relevance",
            kind="suitability",
            weight=0.7,
            state=ScoreState.UNKNOWN,
            value=0.0,
            zero_classification="measured_zero",
            basis="a value that claims to be absent",
        )


# ---------------------------------------------------------------------------
# B26 T8c: the explanation ``load`` block (plan §7)
# ---------------------------------------------------------------------------

_PRE_T8C_PAYLOAD_KEYS = {
    "subject_id",
    "heuristic_score",
    "state",
    "score_label",
    "registry_version",
    "formula_version",
    "scoring_mode",
    "scoring_mode_version",
    "unknown_factor_keys",
    "policy_neutral_factor_keys",
    "factors",
}


@pytest.fixture
def registry_3(monkeypatch):
    evaluate_registry_3(monkeypatch)


# 26
def test_2_x_payload_has_no_load_key_and_reads_back_none():
    explanation = explain_candidate(_score2(_cba_evidence("SYNTH-EXPLAIN-2X")))
    assert explanation.load is None
    payload = explanation_to_payload(explanation)
    assert "load" not in payload
    assert set(payload) == _PRE_T8C_PAYLOAD_KEYS
    restored = explanation_from_payload(payload)
    assert restored.load is None
    assert restored == explanation


# 27
def test_3_x_load_block_round_trips_exactly(registry_3):
    explanation = explain_candidate(_score3(_cba_evidence("SYNTH-EXPLAIN-3X", load=MODERATE)))
    load = explanation.load
    assert load is not None
    assert load.band.value == "moderate"
    assert load.multiplier == Decimal("0.90")
    assert load.composite_before_load == 0.97
    assert load.as_of.isoformat() == "2026-10-06"
    assert explanation.heuristic_score == 0.873

    payload = explanation_to_payload(explanation)
    assert payload["load"] == {
        "band": "moderate",
        "reason": "measured",
        "measurable": True,
        "completed_hours": "50",
        "confirmed_hours": "0",
        "capacity_hours": "100.0",
        "utilization": "0.5",
        "unknown_hours_refs": [],
        "multiplier": "0.90",
        "composite_before_load": 0.97,
        "as_of": "2026-10-06",
        "eli_formula_version": "2.0.0",
    }
    assert set(payload) == _PRE_T8C_PAYLOAD_KEYS | {"load"}
    restored = explanation_from_payload(payload)
    assert restored == explanation
    assert restored.load == load


def test_unknown_load_block_is_labelled_and_neutral(registry_3):
    explanation = explain_candidate(_score3(_cba_evidence("SYNTH-EXPLAIN-UNK", load=UNKNOWN)))
    payload = explanation_to_payload(explanation)
    assert payload["load"]["band"] == "unknown"
    assert payload["load"]["reason"] == "capacity_not_stated"
    assert payload["load"]["measurable"] is False
    assert payload["load"]["capacity_hours"] is None
    assert payload["load"]["utilization"] is None
    assert Decimal(payload["load"]["multiplier"]) == 1
    assert payload["heuristic_score"] == 0.97
    assert explanation_from_payload(payload) == explanation


def test_explain_candidate_refuses_a_mismatched_load(registry_3):
    three = _score3(_cba_evidence("SYNTH-EXPLAIN-MIS", load=LIGHT))
    from dataclasses import replace

    with pytest.raises(ValueError, match="load"):
        explain_candidate(replace(three, load=None, composite_before_load=None))
    two = _score2(_cba_evidence("SYNTH-EXPLAIN-MIS"))
    with pytest.raises(ValueError, match="load"):
        explain_candidate(replace(two, load=LIGHT))


def test_a_3_x_explanation_is_gated_without_the_helper(monkeypatch):
    from smartmatch_domain.factor_registry import RegistryNotApprovedError

    evaluate_registry_3(monkeypatch)
    three = _score3(_cba_evidence("SYNTH-EXPLAIN-GATE", load=HEAVY))
    monkeypatch.undo()
    with pytest.raises(RegistryNotApprovedError):
        explain_candidate(three)


def _payload_3x(load=MODERATE):
    return explanation_to_payload(
        explain_candidate(_score3(_cba_evidence("SYNTH-EXPLAIN-R", load=load)))
    )


def _mutate(path, value):
    def apply(payload):
        target = payload
        for key in path[:-1]:
            target = target[key]
        if value is _DELETE:
            del target[path[-1]]
        else:
            target[path[-1]] = value
        return payload

    return apply


_DELETE = object()


# 28
@pytest.mark.parametrize(
    ("mutate", "match"),
    [
        pytest.param(_mutate(("load", "completed_hours"), 50), "completed_hours", id="number"),
        pytest.param(_mutate(("load", "utilization"), 0.5), "utilization", id="number-util"),
        pytest.param(_mutate(("load", "band"), "overloaded"), "band", id="bad-band"),
        pytest.param(_mutate(("load", "reason"), "guessed"), "reason", id="bad-reason"),
        pytest.param(_mutate(("load", "measurable"), False), "measurable", id="measurable"),
        pytest.param(_mutate(("load", "multiplier"), "0.95"), "multiplier", id="multiplier"),
        pytest.param(_mutate(("heuristic_score",), 0.9), "heuristic_score", id="heuristic"),
        pytest.param(_mutate(("load", "band"), "full"), "full", id="full-band"),
        pytest.param(_mutate(("load", "as_of"), "6 Oct 2026"), "as_of", id="bad-date"),
        pytest.param(
            _mutate(("load", "unknown_hours_refs"), "r-1"), "unknown_hours_refs", id="refs"
        ),
        pytest.param(_mutate(("load", "as_of"), _DELETE), "as_of", id="missing-field"),
        pytest.param(_mutate(("load",), None), "load", id="null-on-3x"),
        pytest.param(_mutate(("load",), _DELETE), "load", id="missing-on-3x"),
        pytest.param(
            _mutate(("registry_version",), "9.9.9-nobody"), "registry_version", id="unknown-pin"
        ),
    ],
)
def test_load_block_is_refused_not_repaired(registry_3, mutate, match):
    payload = mutate(copy.deepcopy(_payload_3x()))
    with pytest.raises(ValueError, match=match):
        explanation_from_payload(payload)


@pytest.mark.parametrize("value", [None, {"band": "light"}])
def test_a_load_key_on_a_2_x_payload_is_refused(value):
    payload = explanation_to_payload(explain_candidate(_score2(_cba_evidence("SYNTH-EXPLAIN-2L"))))
    payload["load"] = value
    with pytest.raises(ValueError, match="load"):
        explanation_from_payload(payload)
