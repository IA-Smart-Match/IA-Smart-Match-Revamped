"""CBA semantic Topic factor — three evidence states, one of them a policy.

Customer §9 and ADR-0016 (accepted 5 September 2026, Danny Tran, program owner
of record). This module implements ADR-0016's most subtle decision, so the
reasoning is written out rather than left to be re-derived.

## The distinction this module exists to make

Read naively, §9 asks for what ADR-0011 forbids: a number where there is no
evidence. The contradiction dissolves on one observation — *there are two
different reasons a Topic score can be absent, and only one of them is an
unknown.*

===================  ==========================================================
State                What it means
===================  ==========================================================
``measured``         The comparison ran against real topic evidence and
                     produced a number. A ``0.0`` here is a **measured zero**:
                     a real claim that this speaker's recorded topics do not
                     address the request, and it must stay distinguishable
                     from both of the states below.
``policy_neutral``   The speaker profile **was read** and carries no usable
                     topic evidence. That is an *observed absence* — we looked,
                     and there was nothing — and §9 states a policy for it.
                     Scores :data:`CBA_NEUTRAL_TOPIC_VALUE` and
                     **participates in scoring**.
``unknown``          The evidence **could not be evaluated**: no profile row,
                     or a comparison that could not run. ADR-0011 rule 1 in
                     full — ``None``, never ``0.0``, and the composite is
                     unscorable.
===================  ==========================================================

Only ``unknown`` makes a composite unscorable. This *refines* ADR-0011 by
naming a case rule 1 never covered; it does not amend or weaken it.

## The rule is decided here, at the evidence-gathering step

ADR-0016 Proposal 1 is explicit that the choice between ``policy_neutral`` and
``unknown`` is a property of the evidence-gathering step rather than of the
score. :class:`SpeakerTopicEvidence` is that step made into a type: a profile
row that exists with no topic text and no prior talk is an observed absence, no
profile row at all is an unknown, and a caller cannot express "absent" without
saying which of the two it means.

## No unlabelled neutral

A ``0.5`` with no policy attached is indistinguishable from a measured ``0.5``,
which would be ADR-0011's defect in a new costume. So
:class:`CbaTopicFactorScore` refuses to hold a ``policy_neutral`` state without
:data:`NEUTRAL_TOPIC_POLICY_ID` and :data:`CBA_NEUTRAL_TOPIC_POLICY_VERSION`
on it, and refuses to hold a ``policy_neutral`` state carrying any value other
than the policy's own.

## What this module does not do

It writes **no registry weights** and performs no composition. Which weight
Topic carries, and how weight is redistributed for a virtual event, are
decisions ADR-0016 Proposals 5 and 6 assign to the registry track; a factor
that also knew its own weight would be two decisions in one file. The registry
key this factor binds to is likewise not settled here — see
:data:`CBA_SEMANTIC_TOPIC_FACTOR_KEY`.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Final, Protocol, runtime_checkable

from smartmatch_domain.one_sentence import assert_one_sentence

__all__ = [
    "CBA_NEUTRAL_TOPIC_POLICY_VERSION",
    "CBA_NEUTRAL_TOPIC_VALUE",
    "CBA_SEMANTIC_TOPIC_FACTOR_KEY",
    "CBA_SEMANTIC_TOPIC_FACTOR_VERSION",
    "NEUTRAL_TOPIC_BASIS",
    "NEUTRAL_TOPIC_POLICY_ID",
    "TOPIC_SCORE_PRECISION",
    "CbaTopicFactorScore",
    "SemanticTopicProvider",
    "SpeakerTopicEvidence",
    "TopicComparison",
    "TopicEvidenceState",
    "score_cba_semantic_topic",
]

# ---------------------------------------------------------------------------
# The ratified policy constants (ADR-0016 Proposal 2)
# ---------------------------------------------------------------------------

#: The score a ``policy_neutral`` Topic factor contributes. The midpoint of the
#: ``[0.0, 1.0]`` factor scale, which is the plainest reading of §9's
#: "neutral/middle score". Its one operational property, stated so it is never
#: a surprise: a speaker with no topic evidence ranks **above** a speaker
#: measured below this and **below** one measured above it, on Topic alone.
CBA_NEUTRAL_TOPIC_VALUE: Final[float] = 0.50

#: The stable identifier of the policy, recorded on every score that used it.
NEUTRAL_TOPIC_POLICY_ID: Final[str] = "cba-neutral-topic"

#: Bumped whenever the value **or** the ``policy_neutral``/``unknown`` boundary
#: rule changes, so an older stored run is never re-read under a newer policy.
CBA_NEUTRAL_TOPIC_POLICY_VERSION: Final[str] = "1.0.0"

#: The approved wording a Speaker Connector reads, verbatim from ADR-0016
#: Proposal 2. Not paraphrasable: it names the policy and its version inline so
#: the provenance survives being copied into a surface that drops other fields.
NEUTRAL_TOPIC_BASIS: Final[str] = (
    "No usable topic evidence on file; customer §9 neutral policy applied "
    "(cba-neutral-topic 1.0.0)."
)

#: Versioned independently of the registry and of the neutral policy: a change
#: to *how this factor decides* is a new factor version even when the policy
#: value is untouched.
CBA_SEMANTIC_TOPIC_FACTOR_VERSION: Final[str] = "1.0.0"

#: This factor's own key. Deliberately **not** ``topic_relevance``: that key
#: belongs to the pre-CBA lexical set-overlap factor, which still exists and
#: still means what it meant. Which of the two the CBA registry binds to its
#: Topic slot is a registry decision (OQ-CBA-027), and taking the existing key
#: here would have made that decision silently by collision.
CBA_SEMANTIC_TOPIC_FACTOR_KEY: Final[str] = "cba_semantic_topic"

#: Decimal places a measured value is rounded to before it leaves this factor,
#: matching ``smartmatch_domain.factors.FACTOR_SCORE_PRECISION``. Named locally
#: so a provider returning full float precision cannot make two runs of the
#: same comparison differ in their last digit.
TOPIC_SCORE_PRECISION: Final[int] = 4


class TopicEvidenceState(StrEnum):
    """ADR-0016 Proposal 1's three states, as a discriminator beside the value.

    A discriminator rather than a nullness convention, for the reason
    ``smartmatch_domain.explanation`` gives about its own ``ScoreState``: a
    consumer that only looked at the value would have to infer the difference
    from a null, and that is the inference every surface in the legacy system
    got wrong.
    """

    MEASURED = "measured"
    POLICY_NEUTRAL = "policy_neutral"
    UNKNOWN = "unknown"


# ---------------------------------------------------------------------------
# The provider seam
# ---------------------------------------------------------------------------


@runtime_checkable
class TopicComparison(Protocol):
    """One provider's account of how well a speaker's topics fit a request.

    Structural rather than a concrete class because the domain may not import
    :mod:`smartmatch_providers` (``pyproject.toml``'s layering contract), and
    the concrete result type belongs with the adapter that produces it.

    Attributes:
        score: Fit in ``[0.0, 1.0]``.
        rationale: Exactly one sentence, per customer §9.
        provider: The adapter's name, carried onto the score so a stored match
            can still answer "what produced this" a year later.
        model_id: The specific model, when one was actually used. ``None`` for
            any provider that is not a live model.
        is_semantic_model: Whether the comparison came from a semantic model.
            ``False`` for a fixture or any lexical implementation — a name is
            the only thing a later reader has to go on, and a lexical or
            replayed comparison labelled "semantic" is a permanent lie about
            how a match was produced.
    """

    score: float
    rationale: str
    provider: str
    model_id: str | None
    is_semantic_model: bool


@runtime_checkable
class SemanticTopicProvider(Protocol):
    """Compares an event description against a speaker's topic evidence.

    Narrow on purpose: an adapter can do exactly this and nothing else, which
    is what makes the classroom-isolation assertions in
    ``tests/unit/test_provider_isolation.py`` meaningful.

    Implementations raise their own "unavailable" error when they cannot
    produce a comparison, and this factor turns that into an ``unknown``. An
    implementation must never return a plausible number in place of a
    comparison it could not make: no model-generated assumption may be stored
    as fact.
    """

    name: str
    is_semantic_model: bool

    def compare(self, request_description: str, speaker_evidence: str) -> TopicComparison:
        """Return the fit between a request and a speaker's topic evidence."""
        ...


# ---------------------------------------------------------------------------
# The evidence-gathering step, where the state is actually decided
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class SpeakerTopicEvidence:
    """What was found when the speaker's profile was looked for.

    Constructed through :meth:`from_profile` or :meth:`no_profile_record`
    rather than directly, because the two carry different meanings and the
    difference is the whole of ADR-0016 Proposal 1. A caller cannot say
    "absent" without saying which absence it means.

    Attributes:
        profile_present: Whether a speaker profile record was actually read.
            ``False`` is a genuine unknown; ``True`` with no usable text is an
            observed absence.
        topic_text: Migration ``0024``'s ``speaker_profile.topic_text`` —
            customer §18's "Topic/interests/expertise text".
        prior_talk: Migration ``0024``'s ``speaker_profile.prior_talk``.
    """

    profile_present: bool
    topic_text: str | None = None
    prior_talk: str | None = None

    def __post_init__(self) -> None:
        if not self.profile_present and (self.topic_text or self.prior_talk):
            raise ValueError(
                "SpeakerTopicEvidence: topic text was supplied with profile_present=False. "
                "Evidence that was read implies a record that was reached; use from_profile()."
            )

    @classmethod
    def from_profile(
        cls, *, topic_text: str | None = None, prior_talk: str | None = None
    ) -> SpeakerTopicEvidence:
        """A speaker profile row **was** read. Its contents may still be empty.

        An empty result here is an *observed absence* and scores under the §9
        policy. Blank and whitespace-only strings are treated exactly as
        ``None``: ``ck_speaker_profile_text_present`` (migration ``0024``)
        already forbids a blank in the column, so a blank arriving here is a
        value that lost its content on the way, not evidence.
        """
        return cls(profile_present=True, topic_text=topic_text, prior_talk=prior_talk)

    @classmethod
    def no_profile_record(cls) -> SpeakerTopicEvidence:
        """No speaker profile row exists for this candidate — a true unknown.

        Not "probably has nothing to say". The record was never reached, so
        there is nothing to have a policy about, and ADR-0011 rule 1 applies
        unchanged.
        """
        return cls(profile_present=False)

    @property
    def usable_text(self) -> str | None:
        """The topic evidence to compare, or ``None`` when there is none.

        ``topic_text`` and ``prior_talk`` are joined rather than ranked: §9
        names prior talks as topic information in their own right, so a
        speaker with only a prior talk on file has usable evidence and is not
        an observed absence.
        """
        parts = [
            part.strip()
            for part in (self.topic_text, self.prior_talk)
            if part is not None and part.strip()
        ]
        return " ".join(parts) if parts else None

    @property
    def is_observed_absence(self) -> bool:
        """A record that was read and carries no usable topic evidence."""
        return self.profile_present and self.usable_text is None


# ---------------------------------------------------------------------------
# The score
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class CbaTopicFactorScore:
    """One candidate's Topic result, with its state and provenance attached.

    Attributes:
        factor_key: :data:`CBA_SEMANTIC_TOPIC_FACTOR_KEY`.
        state: Which of ADR-0016's three states this is.
        value: The number, or ``None`` when :attr:`state` is ``unknown``.
        basis: Machine-and-human readable provenance for the number, non-empty
            on every branch including the unknown one — an unknown carries a
            reason, never a blank.
        rationale: Customer §9's one sentence, checked rather than trusted.
        policy_id: :data:`NEUTRAL_TOPIC_POLICY_ID` when, and only when, the
            state is ``policy_neutral``.
        policy_version: :data:`CBA_NEUTRAL_TOPIC_POLICY_VERSION` under the same
            condition.
        provider_name: Which adapter produced a measured comparison, or
            ``None``. Carried so a stored match can answer how it was made.
        model_id: The model behind a measured comparison, when there was one.
        is_semantic_model: Whether the comparison came from a semantic model.
            ``False`` for a fixture. Reported exactly as the provider stated
            it, never asserted on this side.
    """

    factor_key: str
    state: TopicEvidenceState
    value: float | None
    basis: str
    rationale: str
    policy_id: str | None = None
    policy_version: str | None = None
    provider_name: str | None = None
    model_id: str | None = None
    is_semantic_model: bool = False

    def __post_init__(self) -> None:
        """Refuse a score whose state, value, and provenance disagree."""
        if not self.basis.strip():
            raise ValueError(f"{self.factor_key}: basis must be a non-empty, non-blank string")

        assert_one_sentence(self.rationale, field=f"{self.factor_key}.rationale")

        if self.value is not None and not 0.0 <= self.value <= 1.0:
            raise ValueError(
                f"{self.factor_key}: value must be in [0.0, 1.0] or None, got {self.value!r}"
            )

        if self.state is TopicEvidenceState.POLICY_NEUTRAL:
            if self.policy_id is None or self.policy_version is None:
                raise ValueError(
                    f"{self.factor_key}: a policy_neutral score must carry policy_id and "
                    "policy_version. An unlabelled neutral is indistinguishable from a "
                    "measured 0.5, which is the ADR-0011 defect this state exists to avoid."
                )
            if self.value != CBA_NEUTRAL_TOPIC_VALUE:
                raise ValueError(
                    f"{self.factor_key}: a policy_neutral score must carry "
                    f"CBA_NEUTRAL_TOPIC_VALUE ({CBA_NEUTRAL_TOPIC_VALUE}), got {self.value!r}. "
                    "'policy_neutral' names the customer's stated value, not 'roughly neutral'."
                )
            return

        if self.policy_id is not None or self.policy_version is not None:
            raise ValueError(
                f"{self.factor_key}: only a policy_neutral score may carry a policy_id; "
                f"state is {self.state.value!r}. A measured value is the system's own claim."
            )

        if self.state is TopicEvidenceState.UNKNOWN and self.value is not None:
            raise ValueError(
                f"{self.factor_key}: an unknown has no value, got {self.value!r} "
                "(ADR-0011 rule 1: unknown is still not zero)."
            )

        if self.state is TopicEvidenceState.MEASURED and self.value is None:
            raise ValueError(
                f"{self.factor_key}: a measured score must carry a value; got None. "
                "A measurement that renders as blank is one some consumer will fill with zero."
            )

    @property
    def is_scorable(self) -> bool:
        """Whether this factor can take part in a composite.

        ``True`` for ``measured`` and for ``policy_neutral`` — ADR-0016's
        central consequence is that a policy value participates in scoring.
        ``False`` only for ``unknown``, which keeps today's behaviour exactly:
        the composite becomes ``None`` and weights are never re-spread.
        """
        return self.state is not TopicEvidenceState.UNKNOWN

    @property
    def zero_classification(self) -> str | None:
        """``"measured_zero"``, ``"unknown"``, or ``None``.

        A ``policy_neutral`` score is none of these: it is not zero, so it has
        no zero to classify.
        """
        if self.state is TopicEvidenceState.UNKNOWN:
            return "unknown"
        if self.state is TopicEvidenceState.MEASURED and self.value == 0.0:
            return "measured_zero"
        return None


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------


def _unknown(reason_basis: str, rationale: str) -> CbaTopicFactorScore:
    return CbaTopicFactorScore(
        factor_key=CBA_SEMANTIC_TOPIC_FACTOR_KEY,
        state=TopicEvidenceState.UNKNOWN,
        value=None,
        basis=reason_basis,
        rationale=rationale,
    )


def score_cba_semantic_topic(
    request_description: str,
    evidence: SpeakerTopicEvidence,
    provider: SemanticTopicProvider,
) -> CbaTopicFactorScore:
    """Score one candidate's Topic fit, in one of ADR-0016's three states.

    The order of the branches is the decision procedure, and it is deliberate:
    the two states that need no comparison are settled *before* the provider is
    consulted, so a thin record and a description-less request never reach an
    adapter at all. Calling a model to ask about evidence that does not exist
    is how a system ends up storing an assumption as a fact.

    Args:
        request_description: The event description from the Speaker Request.
        evidence: What was found when the speaker's profile was looked for.
        provider: The comparison adapter. Under ``ALLOW_LIVE_PROVIDERS=false``
            this is always the deterministic fixture.

    Returns:
        A :class:`CbaTopicFactorScore`. ``policy_neutral`` carries
        :data:`CBA_NEUTRAL_TOPIC_VALUE` and its policy provenance;
        ``unknown`` carries ``None``; ``measured`` carries the provider's value
        rounded to :data:`TOPIC_SCORE_PRECISION` places, which may legitimately
        be ``0.0``.
    """
    if not evidence.profile_present:
        return _unknown(
            "no speaker profile record was reached for this candidate",
            "No speaker profile record was reached, so their topic fit could not be evaluated.",
        )

    if evidence.is_observed_absence:
        return CbaTopicFactorScore(
            factor_key=CBA_SEMANTIC_TOPIC_FACTOR_KEY,
            state=TopicEvidenceState.POLICY_NEUTRAL,
            value=CBA_NEUTRAL_TOPIC_VALUE,
            basis=NEUTRAL_TOPIC_BASIS,
            rationale=NEUTRAL_TOPIC_BASIS,
            policy_id=NEUTRAL_TOPIC_POLICY_ID,
            policy_version=CBA_NEUTRAL_TOPIC_POLICY_VERSION,
        )

    if not request_description.strip():
        # Not the speaker's absence, so not the speaker's neutral. Reading a
        # coordinator's blank description as an observed absence on the
        # speaker's side would apply a policy to the wrong party.
        return _unknown(
            "the speaker request carries no description to compare against",
            "The request carries no description, so their topic fit could not be evaluated.",
        )

    speaker_evidence = evidence.usable_text
    if speaker_evidence is None:  # pragma: no cover - the observed-absence branch returned
        raise AssertionError(
            "unreachable: a present profile with no usable text is an observed absence "
            "and was already returned as policy_neutral"
        )

    try:
        comparison = provider.compare(request_description, speaker_evidence)
    except Exception:
        # Any failure to evaluate is an unknown, never a zero and never the §9
        # neutral: the customer stated a policy for an absence we observed, not
        # for a comparison we could not make. Broad on purpose — an adapter's
        # failure modes are its own, and every one of them means the same thing
        # here. The failure is not swallowed: it becomes a stated unknown that
        # a Connector can read and act on.
        return _unknown(
            "the topic comparison could not be evaluated for this candidate",
            "Their topic evidence could not be evaluated, so no fit was measured.",
        )

    return CbaTopicFactorScore(
        factor_key=CBA_SEMANTIC_TOPIC_FACTOR_KEY,
        state=TopicEvidenceState.MEASURED,
        value=round(comparison.score, TOPIC_SCORE_PRECISION),
        basis=(
            f"semantic topic comparison against recorded topic evidence ({comparison.provider})"
        ),
        rationale=comparison.rationale,
        provider_name=comparison.provider,
        model_id=comparison.model_id,
        is_semantic_model=comparison.is_semantic_model,
    )
