"""What a Speaker Connector reads for a Topic factor, and nothing they don't.

Customer §9 asks Topic matching for two things: a fit score and "one sentence
explaining the reasoning". This module is the second thing, plus the words the
first thing is allowed to travel under.

## Why the labels are constants and not formatting

ADR-0016 Proposal 8 does not describe a rendering style; it fixes exact
strings, and the ADR says why: "each names the exact wording a Speaker
Connector reads, because '0%' on an AI event is the literal symptom (Fix #8)
that produced ADR-0011." A label assembled at a call site is a label that
drifts, and the drift is invisible until somebody reads a screen and draws the
wrong conclusion from it. So the three approved strings are named here, and
:func:`explain_cba_topic` selects between them rather than composing them.

The one label that *is* composed is a measured non-zero value, which renders as
the bare number followed by :data:`MEASURED_LABEL_SUFFIX`. That composition is
deliberate rather than a shortcut: it makes the approved string
``"0 — measured"`` fall out of the same rule that renders every other measured
value, so a measured zero cannot drift away from its siblings by being
special-cased. Nothing here multiplies a value by 100, and no label carries a
percent sign.

## Why this is a separate module from ``explanation.py``

``smartmatch_domain.explanation`` carries the two-state ``ScoreState`` that
ADR-0011 established, the payload round trip, and the composite's presentation
rules. ADR-0016 Proposal 7 widens all of that to three states — a change to
``FactorExplanation``'s invariant, to the payload, and to
``CandidateExplanation`` — and that widening belongs with the registry work
that also moves ``REGISTRY_VERSION``. This module is the Topic factor's own
account, which the CBA factor can produce and a surface can render before the
shared serialization catches up, and it leaves ``explanation.py`` untouched.

## The one-sentence rule is enforced here too

:func:`assert_one_sentence` is re-exported from
:mod:`smartmatch_domain.one_sentence` so that a surface importing this module
gets the checker with it, and :class:`CbaTopicExplanation` applies it in
``__post_init__``. That is the last boundary before the sentence reaches a
person, and it is checked there for the same reason the factor checks it at
construction: a rule enforced only where it is convenient is a rule that is
eventually skipped.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from smartmatch_domain.factors.cba_semantic_topic import (
    CbaTopicFactorScore,
    TopicEvidenceState,
)
from smartmatch_domain.one_sentence import OneSentenceRationaleError, assert_one_sentence

__all__ = [
    "FACTOR_UNKNOWN_UI_LABEL",
    "MEASURED_LABEL_SUFFIX",
    "TOPIC_MEASURED_ZERO_UI_LABEL",
    "TOPIC_NEUTRAL_UI_LABEL",
    "CbaTopicExplanation",
    "OneSentenceRationaleError",
    "assert_one_sentence",
    "explain_cba_topic",
]

#: ADR-0016 Proposal 8, verbatim. Never "0", never "0%", never a blank cell,
#: and never a bar drawn from the origin: a neutral is a stated policy value,
#: and every one of those renderings would report it as a measurement of
#: nothing.
TOPIC_NEUTRAL_UI_LABEL: Final[str] = "Neutral — no topic information on file"

#: ADR-0016 Proposal 8, verbatim. A measured zero is a real claim about a
#: speaker whose recorded topics were read and do not match, and it must never
#: render as "Unknown" — nor as an unqualified "0%".
TOPIC_MEASURED_ZERO_UI_LABEL: Final[str] = "0 — measured"

#: ADR-0016 Proposal 8, verbatim. An unknown carries no numeral at all.
FACTOR_UNKNOWN_UI_LABEL: Final[str] = "Unknown"

#: What follows a measured value in its label. Applying it to ``0.0`` is what
#: produces :data:`TOPIC_MEASURED_ZERO_UI_LABEL`, so the approved string and
#: every other measured label come from one rule rather than two.
MEASURED_LABEL_SUFFIX: Final[str] = " — measured"


@dataclass(frozen=True, slots=True)
class CbaTopicExplanation:
    """One candidate's Topic factor, as a surface should render it.

    Attributes:
        factor_key: The factor this explains.
        state: ADR-0016's discriminator, carried beside the value rather than
            inferred from its nullness, so a renderer cannot read an absence as
            a measurement.
        value: The number, or ``None`` for an unknown. A bare number in
            ``[0.0, 1.0]`` — never a percentage.
        ui_label: The exact words to show. One of the three approved constants,
            or a measured value with :data:`MEASURED_LABEL_SUFFIX`.
        rationale: Customer §9's one sentence.
        basis: The factor's own account of where its number came from, for a
            detail row or a hover.
        policy_id: The §9 policy, present exactly when the state is
            ``policy_neutral``. Its presence is what lets a consumer tell a
            neutral 0.5 from a measured one.
        policy_version: That policy's version, under the same condition.
        zero_classification: ``"measured_zero"``, ``"unknown"``, or ``None``,
            carried through from the score unchanged so a surface does not
            re-derive it from ``value == 0.0`` and get a neutral wrong.
    """

    factor_key: str
    state: TopicEvidenceState
    value: float | None
    ui_label: str
    rationale: str
    basis: str
    policy_id: str | None
    policy_version: str | None
    zero_classification: str | None

    def __post_init__(self) -> None:
        """Check what a renderer would otherwise have to be trusted about."""
        assert_one_sentence(self.rationale, field=f"{self.factor_key}.rationale")

        if not self.ui_label.strip():
            raise ValueError(f"{self.factor_key}: ui_label must not be blank")

        if "%" in self.ui_label:
            raise ValueError(
                f"{self.factor_key}: ui_label must not carry a percent sign; got "
                f"{self.ui_label!r}. A percentage on a factor score is the legacy "
                "surface ADR-0011 was written to remove."
            )

        if (self.state is TopicEvidenceState.POLICY_NEUTRAL) != (self.policy_id is not None):
            raise ValueError(
                f"{self.factor_key}: policy_id and state {self.state.value!r} disagree. "
                "Only a policy_neutral factor carries a policy, and it always carries one — "
                "a measured value is the system's own claim, not the customer's."
            )

        if (self.policy_id is None) != (self.policy_version is None):
            raise ValueError(
                f"{self.factor_key}: a policy_id and a policy_version travel together; "
                "a policy with no version cannot be read back under the right rules."
            )

        if (self.state is TopicEvidenceState.UNKNOWN) != (self.value is None):
            raise ValueError(
                f"{self.factor_key}: state {self.state.value!r} and value {self.value!r} "
                "disagree (ADR-0011: an unknown has no value, and a measured value is "
                "never absent)."
            )

    @property
    def is_policy_value(self) -> bool:
        """Whether this number came from the customer's policy, not a measurement.

        The question a surface actually needs to ask before drawing a bar or
        writing a caption, answerable without comparing floats.
        """
        return self.state is TopicEvidenceState.POLICY_NEUTRAL


def _ui_label(score: CbaTopicFactorScore) -> str:
    """Choose the approved words for one score's state."""
    if score.state is TopicEvidenceState.UNKNOWN:
        return FACTOR_UNKNOWN_UI_LABEL
    if score.state is TopicEvidenceState.POLICY_NEUTRAL:
        return TOPIC_NEUTRAL_UI_LABEL
    # ``:g`` renders 0.0 as "0" and 0.82 as "0.82", so the approved
    # "0 — measured" is produced by the same rule as every other measured
    # label rather than by a branch that could drift away from it.
    return f"{score.value:g}{MEASURED_LABEL_SUFFIX}"


def explain_cba_topic(score: CbaTopicFactorScore) -> CbaTopicExplanation:
    """Render one Topic score as the account a Speaker Connector reads.

    A faithful restatement, not a second opinion: the state, the value, the
    basis, the rationale and the policy provenance all come from the score
    unchanged. The only thing added is the choice of approved words, and the
    only thing checked is that the sentence is still one sentence.

    Args:
        score: The result of
            :func:`~smartmatch_domain.factors.cba_semantic_topic.score_cba_semantic_topic`.

    Returns:
        A :class:`CbaTopicExplanation`.

    Raises:
        OneSentenceRationaleError: if the score's rationale is not exactly one
            sentence. Raised rather than trimmed — a rationale that grew a
            second sentence between the factor and the screen is a defect
            somewhere upstream, and silently truncating it would hide that.
    """
    return CbaTopicExplanation(
        factor_key=score.factor_key,
        state=score.state,
        value=score.value,
        ui_label=_ui_label(score),
        rationale=score.rationale,
        basis=score.basis,
        policy_id=score.policy_id,
        policy_version=score.policy_version,
        zero_classification=score.zero_classification,
    )
