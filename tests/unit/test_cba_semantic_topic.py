"""CBA semantic Topic factor: the three evidence states ADR-0016 ratified.

ADR-0016 Proposals 1 and 2 (accepted 5 September 2026) turn on one distinction
the pre-CBA code does not make: *there are two different reasons a Topic score
can be absent, and only one of them is an unknown.*

- A speaker profile that **was read** and carries no usable topic evidence is an
  **observed absence**. Customer §9 states a policy for it, so it scores
  ``CBA_NEUTRAL_TOPIC_VALUE`` in state ``policy_neutral`` and **participates in
  scoring**.
- A speaker whose evidence **could not be evaluated** is a genuine ``unknown``.
  ADR-0011 rule 1 applies unchanged: ``None``, never ``0.0``, and the composite
  is unscorable.
- A comparison that ran and genuinely found no fit is a **measured zero** — a
  real claim, and distinguishable from both of the above.

The assertion this file exists to make, above all the others: a neutral value
is **never a bare, unlabelled 0.5**. Every neutral score carries the policy id
and the policy version, because a neutral with no provenance is indistinguish-
able from a measured 0.5, which would be ADR-0011's defect in a new costume.
"""

from __future__ import annotations

import pytest
from smartmatch_domain.factors.cba_semantic_topic import (
    CBA_NEUTRAL_TOPIC_POLICY_VERSION,
    CBA_NEUTRAL_TOPIC_VALUE,
    CBA_SEMANTIC_TOPIC_FACTOR_KEY,
    CBA_SEMANTIC_TOPIC_FACTOR_VERSION,
    NEUTRAL_TOPIC_BASIS,
    NEUTRAL_TOPIC_POLICY_ID,
    CbaTopicFactorScore,
    SpeakerTopicEvidence,
    TopicEvidenceState,
    score_cba_semantic_topic,
)
from smartmatch_providers.topic_semantics import (
    FixtureSemanticTopicProvider,
    TopicComparisonUnavailable,
    TopicSimilarity,
)

REQUEST = "We need a speaker on applied machine learning for supply chains."


def _provider(**recordings: tuple[float, str]) -> FixtureSemanticTopicProvider:
    """A fixture provider holding pre-recorded comparisons for this request."""
    provider = FixtureSemanticTopicProvider()
    for evidence, (score, rationale) in recordings.items():
        provider.record(REQUEST, evidence.replace("_", " "), score=score, rationale=rationale)
    return provider


# ---------------------------------------------------------------------------
# The three constants, and their versions
# ---------------------------------------------------------------------------


def test_the_neutral_value_is_the_named_versioned_constant():
    """ADR-0016 Proposal 2, verbatim: 0.50, ``cba-neutral-topic``, ``1.0.0``."""
    assert CBA_NEUTRAL_TOPIC_VALUE == 0.50
    assert NEUTRAL_TOPIC_POLICY_ID == "cba-neutral-topic"
    assert CBA_NEUTRAL_TOPIC_POLICY_VERSION == "1.0.0"


def test_the_approved_basis_string_is_carried_verbatim():
    """The wording a Speaker Connector reads is approved text, not paraphrase."""
    assert NEUTRAL_TOPIC_BASIS == (
        "No usable topic evidence on file; customer §9 neutral policy applied "
        "(cba-neutral-topic 1.0.0)."
    )


def test_the_factor_carries_its_own_version():
    assert CBA_SEMANTIC_TOPIC_FACTOR_VERSION == "1.0.0"


def test_no_weight_literal_appears_in_this_factor():
    """Redistribution is a later track's job; this module writes no weights."""
    import inspect

    from smartmatch_domain.factors import cba_semantic_topic

    source = inspect.getsource(cba_semantic_topic)
    for weight in ("0.30", "0.25", "0.15", "0.428571", "0.357143", "0.214286"):
        assert weight not in source, f"{weight!r} is a registry weight, not this factor's business"


# ---------------------------------------------------------------------------
# policy_neutral — the observed absence
# ---------------------------------------------------------------------------


def test_a_read_profile_with_no_topic_evidence_is_policy_neutral():
    """Customer §9: a thin record is not scored zero, it is scored neutral."""
    score = score_cba_semantic_topic(
        request_description=REQUEST,
        evidence=SpeakerTopicEvidence.from_profile(topic_text=None, prior_talk=None),
        provider=_provider(),
    )

    assert score.state is TopicEvidenceState.POLICY_NEUTRAL
    assert score.value == CBA_NEUTRAL_TOPIC_VALUE
    assert score.is_scorable is True


def test_a_policy_neutral_score_is_always_labelled_with_its_policy():
    """The anti-pattern: no unlabelled neutral 0.5, ever."""
    score = score_cba_semantic_topic(
        request_description=REQUEST,
        evidence=SpeakerTopicEvidence.from_profile(topic_text=None, prior_talk=None),
        provider=_provider(),
    )

    assert score.policy_id == NEUTRAL_TOPIC_POLICY_ID
    assert score.policy_version == CBA_NEUTRAL_TOPIC_POLICY_VERSION
    assert score.basis == NEUTRAL_TOPIC_BASIS
    assert score.rationale == NEUTRAL_TOPIC_BASIS


def test_blank_topic_evidence_is_the_same_observed_absence_as_null():
    """``ck_speaker_profile_text_present`` forbids a blank, so treat one as absent."""
    score = score_cba_semantic_topic(
        request_description=REQUEST,
        evidence=SpeakerTopicEvidence.from_profile(topic_text="   ", prior_talk=""),
        provider=_provider(),
    )

    assert score.state is TopicEvidenceState.POLICY_NEUTRAL
    assert score.policy_id == NEUTRAL_TOPIC_POLICY_ID


def test_a_policy_neutral_score_never_calls_the_provider():
    """There is nothing to compare; calling a provider would invent evidence."""
    provider = _provider()
    score_cba_semantic_topic(
        request_description=REQUEST,
        evidence=SpeakerTopicEvidence.from_profile(topic_text=None, prior_talk=None),
        provider=provider,
    )

    assert provider.calls == []


def test_an_unlabelled_neutral_value_is_refused_at_construction():
    """A 0.5 that claims to be a policy value must carry the policy."""
    with pytest.raises(ValueError, match="policy_id"):
        CbaTopicFactorScore(
            factor_key=CBA_SEMANTIC_TOPIC_FACTOR_KEY,
            state=TopicEvidenceState.POLICY_NEUTRAL,
            value=CBA_NEUTRAL_TOPIC_VALUE,
            basis=NEUTRAL_TOPIC_BASIS,
            rationale=NEUTRAL_TOPIC_BASIS,
            policy_id=None,
            policy_version=None,
        )


def test_a_policy_neutral_score_may_not_carry_some_other_number():
    """``policy_neutral`` means the policy value, not "roughly neutral"."""
    with pytest.raises(ValueError, match="CBA_NEUTRAL_TOPIC_VALUE"):
        CbaTopicFactorScore(
            factor_key=CBA_SEMANTIC_TOPIC_FACTOR_KEY,
            state=TopicEvidenceState.POLICY_NEUTRAL,
            value=0.45,
            basis=NEUTRAL_TOPIC_BASIS,
            rationale=NEUTRAL_TOPIC_BASIS,
            policy_id=NEUTRAL_TOPIC_POLICY_ID,
            policy_version=CBA_NEUTRAL_TOPIC_POLICY_VERSION,
        )


# ---------------------------------------------------------------------------
# unknown — the evidence that could not be evaluated
# ---------------------------------------------------------------------------


def test_no_speaker_profile_row_at_all_is_unknown_not_neutral():
    """ADR-0016: no row is a genuine unknown; ADR-0011 rule 1 is untouched."""
    score = score_cba_semantic_topic(
        request_description=REQUEST,
        evidence=SpeakerTopicEvidence.no_profile_record(),
        provider=_provider(),
    )

    assert score.state is TopicEvidenceState.UNKNOWN
    assert score.value is None
    assert score.policy_id is None
    assert score.is_scorable is False


def test_a_comparison_that_could_not_run_is_unknown():
    """A provider that has no recording for this pair must not be guessed past."""
    score = score_cba_semantic_topic(
        request_description=REQUEST,
        evidence=SpeakerTopicEvidence.from_profile(topic_text="quantum optics", prior_talk=None),
        provider=_provider(),
    )

    assert score.state is TopicEvidenceState.UNKNOWN
    assert score.value is None


def test_a_request_with_no_description_is_unknown():
    """There is nothing to compare a speaker against, which is not an absence
    on the speaker's side and must not be charged to them as a neutral."""
    score = score_cba_semantic_topic(
        request_description="   ",
        evidence=SpeakerTopicEvidence.from_profile(topic_text="machine learning", prior_talk=None),
        provider=_provider(machine_learning=(0.9, "Their recorded work is a direct match.")),
    )

    assert score.state is TopicEvidenceState.UNKNOWN
    assert score.value is None


def test_an_unknown_still_carries_a_non_blank_basis():
    """ADR-0011: an unknown carries a reason, never a blank."""
    score = score_cba_semantic_topic(
        request_description=REQUEST,
        evidence=SpeakerTopicEvidence.no_profile_record(),
        provider=_provider(),
    )

    assert score.basis.strip()
    assert score.rationale.strip()


def test_an_unknown_may_not_carry_a_value():
    with pytest.raises(ValueError, match="unknown"):
        CbaTopicFactorScore(
            factor_key=CBA_SEMANTIC_TOPIC_FACTOR_KEY,
            state=TopicEvidenceState.UNKNOWN,
            value=0.0,
            basis="could not evaluate",
            rationale="The topic comparison could not be evaluated for this speaker.",
        )


# ---------------------------------------------------------------------------
# measured — including a measured zero, which is a real claim
# ---------------------------------------------------------------------------


def test_a_real_comparison_produces_a_measured_score():
    score = score_cba_semantic_topic(
        request_description=REQUEST,
        evidence=SpeakerTopicEvidence.from_profile(topic_text="machine learning", prior_talk=None),
        provider=_provider(
            machine_learning=(0.82, "Their recorded machine-learning work matches the request.")
        ),
    )

    assert score.state is TopicEvidenceState.MEASURED
    assert score.value == 0.82
    assert score.policy_id is None
    assert score.is_scorable is True


def test_a_measured_zero_is_not_a_neutral_and_not_an_unknown():
    """ADR-0016 G-CBA-03: a read record that genuinely does not match is 0.0."""
    score = score_cba_semantic_topic(
        request_description=REQUEST,
        evidence=SpeakerTopicEvidence.from_profile(topic_text="medieval poetry", prior_talk=None),
        provider=_provider(
            medieval_poetry=(0.0, "Their recorded topic does not address the request at all.")
        ),
    )

    assert score.state is TopicEvidenceState.MEASURED
    assert score.value == 0.0
    assert score.zero_classification == "measured_zero"
    assert score.policy_id is None
    assert score.value != CBA_NEUTRAL_TOPIC_VALUE


def test_prior_talk_alone_is_usable_topic_evidence():
    """§9 names prior talks as topic information in its own right."""
    score = score_cba_semantic_topic(
        request_description=REQUEST,
        evidence=SpeakerTopicEvidence.from_profile(
            topic_text=None, prior_talk="Forecasting logistics demand"
        ),
        provider=_provider(),
    )

    # Not recorded, so unknown — but crucially *not* policy_neutral: the record
    # carried evidence, so the absence is not an observed one.
    assert score.state is not TopicEvidenceState.POLICY_NEUTRAL


def test_measured_values_are_rounded_deterministically():
    score = score_cba_semantic_topic(
        request_description=REQUEST,
        evidence=SpeakerTopicEvidence.from_profile(topic_text="logistics", prior_talk=None),
        provider=_provider(logistics=(0.123456789, "Their logistics background partly fits.")),
    )

    assert score.value == 0.1235


def test_a_provider_value_outside_the_unit_interval_is_refused():
    provider = FixtureSemanticTopicProvider()
    with pytest.raises(ValueError, match=r"\[0.0, 1.0\]"):
        provider.record(REQUEST, "logistics", score=1.4, rationale="Too high.")


# ---------------------------------------------------------------------------
# Determinism, and no network
# ---------------------------------------------------------------------------


def test_the_same_inputs_produce_the_identical_score_every_time():
    provider = _provider(logistics=(0.4, "Their logistics work partly addresses the request."))
    evidence = SpeakerTopicEvidence.from_profile(topic_text="logistics", prior_talk=None)

    first = score_cba_semantic_topic(REQUEST, evidence, provider)
    second = score_cba_semantic_topic(REQUEST, evidence, provider)

    assert first == second


def test_the_fixture_provider_is_insensitive_to_case_and_whitespace():
    """Determinism must not depend on how a coordinator typed the text."""
    provider = FixtureSemanticTopicProvider()
    provider.record(REQUEST, "Machine Learning", score=0.7, rationale="A close match here.")

    similarity = provider.compare(REQUEST.upper(), "  machine   learning ")

    assert isinstance(similarity, TopicSimilarity)
    assert similarity.score == 0.7


def test_the_fixture_provider_refuses_rather_than_guessing_an_unrecorded_pair():
    provider = FixtureSemanticTopicProvider()
    with pytest.raises(TopicComparisonUnavailable):
        provider.compare(REQUEST, "nothing was recorded for this")


def test_the_fixture_provider_names_itself_synthetically():
    """A fixture comparison must never be mistakable for a model's output."""
    provider = FixtureSemanticTopicProvider()
    provider.record(REQUEST, "logistics", score=0.4, rationale="A partial match here.")

    similarity = provider.compare(REQUEST, "logistics")

    assert similarity.provider.startswith("fixture-")
    assert similarity.model_id is None


def test_the_fixture_provider_does_not_claim_to_be_a_semantic_model():
    """No lexical or playback implementation may be relabelled as semantic.

    The fixture is a *playback* of comparisons recorded by the caller. It says
    so, because a name is the only thing a later reader has to go on when
    asking how a stored match was actually produced.
    """
    provider = FixtureSemanticTopicProvider()
    provider.record(REQUEST, "logistics", score=0.4, rationale="A partial match here.")

    assert provider.is_semantic_model is False
    assert provider.compare(REQUEST, "logistics").is_semantic_model is False
