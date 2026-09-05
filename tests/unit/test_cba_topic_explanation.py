"""The one-sentence Topic rationale contract, and ADR-0016's approved labels.

Customer §9 asks for two things from Topic matching: "a simple Topic fit score"
and "**one sentence** explaining the reasoning". One sentence is a contract,
not a style note — it is the difference between a Speaker Connector reading a
reason and a Speaker Connector reading a paragraph of model output nobody
approved. So it is checked rather than hoped for: not two sentences, not a
fragment, and never blank.

ADR-0016 Proposal 8 fixes the exact words each state renders under. They are
approved strings, so this file asserts them verbatim rather than approximately.
Nothing here multiplies a value by 100: "0%" on an AI event is the literal
symptom (Fix #8) that produced ADR-0011.
"""

from __future__ import annotations

import pytest
from smartmatch_domain.cba_topic_explanation import (
    FACTOR_UNKNOWN_UI_LABEL,
    MEASURED_LABEL_SUFFIX,
    TOPIC_MEASURED_ZERO_UI_LABEL,
    TOPIC_NEUTRAL_UI_LABEL,
    CbaTopicExplanation,
    OneSentenceRationaleError,
    assert_one_sentence,
    explain_cba_topic,
)
from smartmatch_domain.factors.cba_semantic_topic import (
    CBA_NEUTRAL_TOPIC_POLICY_VERSION,
    CBA_NEUTRAL_TOPIC_VALUE,
    CBA_SEMANTIC_TOPIC_FACTOR_KEY,
    NEUTRAL_TOPIC_BASIS,
    NEUTRAL_TOPIC_POLICY_ID,
    CbaTopicFactorScore,
    SpeakerTopicEvidence,
    TopicEvidenceState,
    score_cba_semantic_topic,
)
from smartmatch_providers.topic_semantics import FixtureSemanticTopicProvider

REQUEST = "We need a speaker on applied machine learning for supply chains."


def _measured(value: float, rationale: str) -> CbaTopicFactorScore:
    provider = FixtureSemanticTopicProvider()
    provider.record(REQUEST, "machine learning", score=value, rationale=rationale)
    return score_cba_semantic_topic(
        request_description=REQUEST,
        evidence=SpeakerTopicEvidence.from_profile(topic_text="machine learning", prior_talk=None),
        provider=provider,
    )


def _neutral() -> CbaTopicFactorScore:
    return score_cba_semantic_topic(
        request_description=REQUEST,
        evidence=SpeakerTopicEvidence.from_profile(topic_text=None, prior_talk=None),
        provider=FixtureSemanticTopicProvider(),
    )


def _unknown() -> CbaTopicFactorScore:
    return score_cba_semantic_topic(
        request_description=REQUEST,
        evidence=SpeakerTopicEvidence.no_profile_record(),
        provider=FixtureSemanticTopicProvider(),
    )


# ---------------------------------------------------------------------------
# Exactly one sentence
# ---------------------------------------------------------------------------


def test_one_plain_sentence_is_accepted():
    text = "Their recorded machine-learning work matches the request."
    assert assert_one_sentence(text, field="rationale") == text


def test_two_sentences_are_refused():
    with pytest.raises(OneSentenceRationaleError, match="exactly one sentence"):
        assert_one_sentence(
            "Their work matches the request. They have also spoken on it before.",
            field="rationale",
        )


def test_a_fragment_with_no_terminal_punctuation_is_refused():
    with pytest.raises(OneSentenceRationaleError, match="exactly one sentence"):
        assert_one_sentence("matches the request", field="rationale")


def test_a_blank_rationale_is_refused():
    with pytest.raises(OneSentenceRationaleError):
        assert_one_sentence("   ", field="rationale")


def test_a_single_word_with_a_full_stop_is_still_a_fragment():
    with pytest.raises(OneSentenceRationaleError):
        assert_one_sentence("Matches.", field="rationale")


def test_a_question_or_exclamation_is_not_a_rationale():
    """A reason is a statement about the evidence, not an interjection."""
    for text in ("Does their work match the request?", "Their work matches the request!"):
        with pytest.raises(OneSentenceRationaleError):
            assert_one_sentence(text, field="rationale")


def test_a_version_number_inside_a_sentence_is_not_a_sentence_boundary():
    """The approved neutral basis contains ``1.0.0``; it is still one sentence."""
    assert assert_one_sentence(NEUTRAL_TOPIC_BASIS, field="rationale") == NEUTRAL_TOPIC_BASIS


def test_the_contract_is_enforced_on_every_explanation():
    """Not a helper somebody may forget to call — the type refuses a bad one."""
    with pytest.raises(OneSentenceRationaleError):
        CbaTopicExplanation(
            factor_key=CBA_SEMANTIC_TOPIC_FACTOR_KEY,
            state=TopicEvidenceState.MEASURED,
            value=0.8,
            ui_label="0.8" + MEASURED_LABEL_SUFFIX,
            rationale="First sentence here. Second sentence here.",
            basis="recorded comparison",
            policy_id=None,
            policy_version=None,
            zero_classification=None,
        )


def test_the_provider_rationale_is_validated_at_recording_time():
    """A two-sentence rationale must not reach a score at all."""
    provider = FixtureSemanticTopicProvider()
    with pytest.raises(OneSentenceRationaleError):
        provider.record(
            REQUEST, "machine learning", score=0.8, rationale="One thing. And another thing."
        )


# ---------------------------------------------------------------------------
# ADR-0016 Proposal 8: the approved labels, verbatim
# ---------------------------------------------------------------------------


def test_the_three_approved_label_strings_are_exact():
    assert TOPIC_NEUTRAL_UI_LABEL == "Neutral — no topic information on file"
    assert TOPIC_MEASURED_ZERO_UI_LABEL == "0 — measured"
    assert FACTOR_UNKNOWN_UI_LABEL == "Unknown"


def test_a_policy_neutral_topic_renders_the_approved_neutral_label():
    explanation = explain_cba_topic(_neutral())

    assert explanation.ui_label == TOPIC_NEUTRAL_UI_LABEL
    assert explanation.value == CBA_NEUTRAL_TOPIC_VALUE
    assert explanation.policy_id == NEUTRAL_TOPIC_POLICY_ID
    assert explanation.policy_version == CBA_NEUTRAL_TOPIC_POLICY_VERSION
    assert explanation.rationale == NEUTRAL_TOPIC_BASIS


def test_a_measured_zero_renders_the_approved_measured_zero_label():
    """Never "Unknown", never a blank cell, never a bar drawn from the origin."""
    explanation = explain_cba_topic(
        _measured(0.0, "Their recorded topic does not address the request at all.")
    )

    assert explanation.ui_label == TOPIC_MEASURED_ZERO_UI_LABEL
    assert explanation.zero_classification == "measured_zero"
    assert explanation.ui_label != TOPIC_NEUTRAL_UI_LABEL
    assert explanation.ui_label != FACTOR_UNKNOWN_UI_LABEL


def test_an_unknown_topic_renders_the_approved_unknown_label_and_no_numeral():
    explanation = explain_cba_topic(_unknown())

    assert explanation.ui_label == FACTOR_UNKNOWN_UI_LABEL
    assert explanation.value is None
    assert not any(character.isdigit() for character in explanation.ui_label)


def test_a_measured_value_renders_as_a_bare_number_not_a_percentage():
    explanation = explain_cba_topic(
        _measured(0.82, "Their recorded machine-learning work matches the request.")
    )

    assert explanation.ui_label == "0.82 — measured"
    assert "%" not in explanation.ui_label
    assert explanation.ui_label != "82"


def test_no_label_this_module_produces_carries_a_percent_sign():
    """ADR-0011's originating symptom was a percentage. None is rendered here."""
    for score in (
        _neutral(),
        _unknown(),
        _measured(0.0, "Their recorded topic does not address the request at all."),
        _measured(0.5, "Their recorded work partly addresses the request."),
    ):
        assert "%" not in explain_cba_topic(score).ui_label


def test_a_measured_half_is_not_confusable_with_the_neutral_policy_value():
    """The whole point: a measured 0.5 and a policy neutral 0.5 differ visibly."""
    measured = explain_cba_topic(_measured(0.5, "Their recorded work partly fits the request."))
    neutral = explain_cba_topic(_neutral())

    assert measured.value == neutral.value == 0.5
    assert measured.ui_label != neutral.ui_label
    assert measured.policy_id is None
    assert neutral.policy_id == NEUTRAL_TOPIC_POLICY_ID
    assert measured.state is TopicEvidenceState.MEASURED
    assert neutral.state is TopicEvidenceState.POLICY_NEUTRAL


# ---------------------------------------------------------------------------
# The explanation is a faithful account of the score, not a second opinion
# ---------------------------------------------------------------------------


def test_the_explanation_carries_the_score_state_and_value_unchanged():
    score = _measured(0.82, "Their recorded machine-learning work matches the request.")
    explanation = explain_cba_topic(score)

    assert explanation.state is score.state
    assert explanation.value == score.value
    assert explanation.basis == score.basis
    assert explanation.rationale == score.rationale
    assert explanation.factor_key == score.factor_key


def test_an_explanation_may_not_invent_a_policy_id_for_a_measured_score():
    with pytest.raises(ValueError, match="policy_id"):
        CbaTopicExplanation(
            factor_key=CBA_SEMANTIC_TOPIC_FACTOR_KEY,
            state=TopicEvidenceState.MEASURED,
            value=0.5,
            ui_label="0.5" + MEASURED_LABEL_SUFFIX,
            rationale="Their recorded work partly addresses the request.",
            basis="recorded comparison",
            policy_id=NEUTRAL_TOPIC_POLICY_ID,
            policy_version=CBA_NEUTRAL_TOPIC_POLICY_VERSION,
            zero_classification=None,
        )


def test_explaining_the_same_score_twice_gives_the_identical_explanation():
    score = _measured(0.82, "Their recorded machine-learning work matches the request.")

    assert explain_cba_topic(score) == explain_cba_topic(score)
