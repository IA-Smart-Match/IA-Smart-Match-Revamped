"""Topic Relevance scoring factor.

Architecture v1.1 §1.2. Registered in
:mod:`smartmatch_domain.factor_registry` as ``topic_relevance``
(``FactorKind.SUITABILITY``, Stage B weight 0.70 per gate G1 approval,
2026-09-03). Measures how well a professional's recorded expertise topics
cover the topics an ``event_need`` declares.

ADR-0011 governs both branches that return ``value=None``: a professional with
no expertise record at all is **unknown**, not zero, and an ``event_need``
that declares no topics has nothing to measure a professional against, which
is also unknown, not zero. Only a *recorded* expertise tuple — even an empty
one — compared against at least one declared topic yields a **measured**
value, and that value is legitimately ``0.0`` when there is no overlap.

**Justification for the 0.75 / 0.25 required/preferred sub-weights:** the
``event_need`` distinguishes required from preferred topics, so this factor
must too, or a candidate who covers only nice-to-haves would score as well as
one who covers the must-haves. A 3:1 split makes full required coverage alone
(0.75) dominate any amount of preferred coverage alone (0.25), while still
letting preferred coverage separate two candidates who both fully cover the
requirements. These are **intra-factor sub-weights**, scoped entirely inside
this module's own arithmetic — they are not registry weights. F-25
normalize-on-apply governs the Stage B factor weights (topic_relevance 0.70 /
travel_burden 0.30) in :mod:`smartmatch_domain.factor_registry`, and this
factor never sees those numbers.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from smartmatch_domain.factors import FACTOR_SCORE_PRECISION, FactorScore

__all__ = [
    "PREFERRED_TOPIC_SUBWEIGHT",
    "REQUIRED_TOPIC_SUBWEIGHT",
    "TOPIC_RELEVANCE_FORMULA_VERSION",
    "TopicRelevanceInputs",
    "score_topic_relevance",
]

#: Versioned independently of the registry: any change to this arithmetic is a
#: new formula version.
TOPIC_RELEVANCE_FORMULA_VERSION: Final[str] = "1.0.0"

#: Weight given to required-topic coverage when both required and preferred
#: coverage are defined. See the module docstring for the 3:1 justification.
REQUIRED_TOPIC_SUBWEIGHT: Final[float] = 0.75

#: Weight given to preferred-topic coverage when both required and preferred
#: coverage are defined. See the module docstring for the 3:1 justification.
PREFERRED_TOPIC_SUBWEIGHT: Final[float] = 0.25


@dataclass(frozen=True, slots=True)
class TopicRelevanceInputs:
    """Everything :func:`score_topic_relevance` is permitted to see.

    Attributes:
        expertise_topics: The professional's recorded expertise topics, or
            ``None`` when no expertise record exists for this professional.
            ``None`` and ``()`` are deliberately different: ``None`` means the
            record is absent (unknown), ``()`` means the record exists and is
            empty (measurable, and measurably zero against any declared
            topic).
        required_topics: Topics the ``event_need`` declares as required.
        preferred_topics: Topics the ``event_need`` declares as preferred.
    """

    expertise_topics: tuple[str, ...] | None
    required_topics: tuple[str, ...]
    preferred_topics: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        for label, topics in (
            ("expertise_topics", self.expertise_topics),
            ("required_topics", self.required_topics),
            ("preferred_topics", self.preferred_topics),
        ):
            if topics is None:
                continue
            for topic in topics:
                if not topic.strip():
                    raise ValueError(f"{label}: topic strings must not be empty or whitespace")


def _canonical(topic: str) -> str:
    """Fold a topic string to its comparison form.

    Comparison is over the ``frozenset`` of canonical forms produced by this
    function, so duplicate entries and case/whitespace differences in either
    the recorded expertise or the declared topics can never change the score.
    """
    return topic.strip().lower()


def _canonical_set(topics: tuple[str, ...]) -> frozenset[str]:
    return frozenset(_canonical(topic) for topic in topics)


def score_topic_relevance(inputs: TopicRelevanceInputs) -> FactorScore:
    """Score how well recorded expertise covers an event_need's topics.

    Args:
        inputs: The professional's recorded expertise and the event_need's
            required/preferred topics.

    Returns:
        A :class:`~smartmatch_domain.factors.FactorScore` with
        ``factor_key="topic_relevance"``. ``value`` is ``None`` when there is
        no expertise record or the event_need declares no topics at all
        (both unknown, per ADR-0011); otherwise it is the weighted required/
        preferred coverage, rounded to
        :data:`~smartmatch_domain.factors.FACTOR_SCORE_PRECISION` places.
    """
    if inputs.expertise_topics is None:
        return FactorScore(
            "topic_relevance",
            None,
            basis="no expertise record for this professional",
        )

    if inputs.required_topics == () and inputs.preferred_topics == ():
        return FactorScore(
            "topic_relevance",
            None,
            basis="event_need declares no topics",
        )

    expertise = _canonical_set(inputs.expertise_topics)
    required = _canonical_set(inputs.required_topics)
    preferred = _canonical_set(inputs.preferred_topics)

    required_matched = expertise & required
    preferred_matched = expertise & preferred

    required_coverage = len(required_matched) / len(required) if required else None
    preferred_coverage = len(preferred_matched) / len(preferred) if preferred else None

    value: float
    if required_coverage is not None and preferred_coverage is not None:
        value = (
            REQUIRED_TOPIC_SUBWEIGHT * required_coverage
            + PREFERRED_TOPIC_SUBWEIGHT * preferred_coverage
        )
    elif required_coverage is not None:
        value = required_coverage
    elif preferred_coverage is not None:
        value = preferred_coverage
    else:
        # Unreachable: the "no topics at all" branch above already returned
        # when both required_topics and preferred_topics are empty, so at
        # least one of required/preferred is non-empty here, which means at
        # least one of required_coverage/preferred_coverage is not None.
        raise AssertionError(
            "unreachable: score_topic_relevance had no required or preferred "
            "topics to measure after the empty-topics guard"
        )

    basis_parts = []
    if required:
        basis_parts.append(f"{len(required_matched)}/{len(required)} required")
    if preferred:
        basis_parts.append(f"{len(preferred_matched)}/{len(preferred)} preferred")
    basis = ", ".join(basis_parts) + " topics matched"

    return FactorScore(
        "topic_relevance",
        round(value, FACTOR_SCORE_PRECISION),
        basis=basis,
    )
