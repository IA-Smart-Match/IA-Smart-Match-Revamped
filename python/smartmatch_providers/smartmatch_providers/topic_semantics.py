"""Topic-comparison adapters, and the reason none of them is live.

Customer §9 asks for an "AI/semantic comparison" between an event description
and a speaker's recorded topic evidence. This module is the seam that request
goes through. Today exactly one adapter exists behind it, and it is a fixture.

## Why there is no live adapter

Choosing a model is not an implementation detail that can be settled at a
keyboard. It commits the project to a vendor, a set of terms, a per-run cost,
and — because the input is a named person's professional profile — a decision
about sending CBA contact data to a third party. None of those has an owner's
answer, which is **OQ-CBA-024**. So :func:`build_semantic_topic_provider`
refuses a live client under *every* edition rather than only the classroom one,
on the pattern ``registry.build_paid_extraction_provider`` established: the
refusal is a property of what has been approved, not of where the code happens
to be running, and expressing it as a deployment property would leave a
production boot silently able to construct something nobody ratified.

``ALLOW_LIVE_PROVIDERS=false`` is the standing environment default and is
necessary but not sufficient here — flipping it reaches an adapter that still
does not exist.

## Why the fixture is a *playback*, and says so

The obvious way to make a deterministic "semantic" fixture is to compute token
overlap between the two strings. That is not done here, and the reason is worth
stating plainly: token overlap is a **lexical** comparison, and shipping one
under a name like "semantic topic provider" would make every stored match carry
a claim about how it was produced that is not true. A misleading name here
becomes a permanent lie in the data — long after anyone remembers that the
"semantic" scorer was three lines of set intersection.

So :class:`FixtureSemanticTopicProvider` computes nothing. It replays
comparisons a caller recorded, refuses any pair it was not given, and reports
:attr:`~FixtureSemanticTopicProvider.is_semantic_model` as ``False``. A test
that wants a particular score states that score, which is also what makes the
fixture deterministic in the strongest sense: there is no algorithm to drift.

Refusing an unrecorded pair rather than returning a default is the same rule in
its other direction — a provider that answered "0.5, probably" would be storing
an assumption as a fact, and the factor above it would have no way to tell that
from a measurement.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from smartmatch_domain.one_sentence import assert_one_sentence
from smartmatch_providers.base import Edition, ProviderConfigurationError

__all__ = [
    "FIXTURE_TOPIC_PROVIDER_NAME",
    "FixtureSemanticTopicProvider",
    "TopicComparisonUnavailable",
    "TopicSimilarity",
    "build_semantic_topic_provider",
]

#: Prefixed ``fixture-`` for the reason ``FixtureEmailProvider``'s message ids
#: are: a synthetic result must never be mistakable for a real one in a log, in
#: the database, or on a screen.
FIXTURE_TOPIC_PROVIDER_NAME: Final[str] = "fixture-topic-semantics"


class TopicComparisonUnavailable(RuntimeError):
    """Raised when an adapter cannot produce a comparison for a pair.

    The factor above turns this into an ``unknown`` — never a zero, and never
    the §9 neutral, which belongs to an absence the system *observed* rather
    than a comparison it could not make.
    """


@dataclass(frozen=True, slots=True)
class TopicSimilarity:
    """One comparison's result. Satisfies the domain's ``TopicComparison``.

    Attributes:
        score: Fit in ``[0.0, 1.0]``.
        rationale: Exactly one sentence (customer §9), validated on the way in
            rather than on the way out, so a malformed rationale cannot reach a
            stored score at all.
        provider: The adapter's name.
        model_id: The model that produced this, or ``None`` when no model did.
        is_semantic_model: Whether this came from a semantic model. ``False``
            for the fixture, and it must stay ``False`` for any lexical
            implementation that is ever added.
    """

    score: float
    rationale: str
    provider: str
    model_id: str | None = None
    is_semantic_model: bool = False

    def __post_init__(self) -> None:
        if not 0.0 <= self.score <= 1.0:
            raise ValueError(f"score must be in [0.0, 1.0], got {self.score!r}")
        assert_one_sentence(self.rationale, field="rationale")
        if not self.provider.strip():
            raise ValueError("provider must be a non-blank name")
        if self.is_semantic_model and self.model_id is None:
            raise ValueError(
                "a comparison claiming to come from a semantic model must name the model; "
                "an unnamed model is an unauditable provenance claim"
            )


def _canonical(text: str) -> str:
    """Fold a string to its lookup form.

    Case- and whitespace-insensitive so that a recorded comparison is found
    regardless of how the same text was typed. This is a *key* normalization,
    not a similarity computation — it decides which recording to replay and
    never what a score should be.
    """
    return " ".join(text.split()).casefold()


class FixtureSemanticTopicProvider:
    """Replays topic comparisons a caller recorded. Computes nothing.

    Not a weaker version of a model, and not a demo-data source. It answers
    exactly the pairs it was given and refuses everything else, so it cannot be
    mistaken for "topic matching that happens to be approximate".

    Example:
        >>> provider = FixtureSemanticTopicProvider()
        >>> provider.record(
        ...     "An event on supply chains.",
        ...     "supply chain analytics",
        ...     score=0.7,
        ...     rationale="Their recorded analytics work addresses the request.",
        ... )
        >>> provider.compare("An event on supply chains.", "supply chain analytics").score
        0.7
    """

    name = FIXTURE_TOPIC_PROVIDER_NAME

    #: A playback fixture is not a semantic model, and says so on every result.
    is_semantic_model = False

    def __init__(self) -> None:
        self._recordings: dict[tuple[str, str], TopicSimilarity] = {}
        #: Every pair this provider was asked about, in order. Lets a test
        #: assert that a branch which must not consult a provider did not.
        self.calls: list[tuple[str, str]] = []

    def record(
        self,
        request_description: str,
        speaker_evidence: str,
        *,
        score: float,
        rationale: str,
    ) -> None:
        """Register the comparison to return for one pair.

        Validation happens here rather than at :meth:`compare` so that a
        malformed recording fails in the test that wrote it, naming the value,
        instead of surfacing later as an unexplained ``unknown``.

        Raises:
            ValueError: ``score`` is outside ``[0.0, 1.0]``.
            smartmatch_domain.one_sentence.OneSentenceRationaleError:
                ``rationale`` is not exactly one sentence.
        """
        similarity = TopicSimilarity(
            score=score,
            rationale=rationale,
            provider=self.name,
            model_id=None,
            is_semantic_model=False,
        )
        key = (_canonical(request_description), _canonical(speaker_evidence))
        self._recordings[key] = similarity

    def compare(self, request_description: str, speaker_evidence: str) -> TopicSimilarity:
        """Return the recorded comparison for this pair.

        Raises:
            TopicComparisonUnavailable: no comparison was recorded for the
                pair. Deliberately not a default value — see the module
                docstring on storing an assumption as a fact.
        """
        key = (_canonical(request_description), _canonical(speaker_evidence))
        self.calls.append(key)

        recorded = self._recordings.get(key)
        if recorded is None:
            raise TopicComparisonUnavailable(
                f"{self.name}: no comparison was recorded for this request and speaker "
                "evidence. The fixture replays recorded comparisons and does not compute "
                "one, so an unrecorded pair is an unknown rather than a guess."
            )
        return recorded


def build_semantic_topic_provider(
    edition: Edition,
    *,
    api_key: str | None = None,
    use_fixture: bool = True,
    allow_live_providers: bool = False,
) -> FixtureSemanticTopicProvider:
    """Construct the topic-comparison provider. Only the fixture exists.

    Mirrors ``registry.build_paid_extraction_provider`` and tightens
    ``registry.build_email_provider``'s rule the same way: the refusal applies
    to **every** edition, not only the fixture-only ones, because no edition
    has an approved model to reach.

    ``use_fixture`` defaults to ``True`` for the reason the paid builder gives:
    the safe outcome must be what a caller gets by writing nothing, and the only
    way to ask for anything else is to say so explicitly and be refused for it.

    Args:
        edition: The running edition. Recorded in the refusal messages so an
            operator can see which deployment asked, and otherwise not
            consulted — every edition gets the same answer.
        api_key: Present only so a misconfigured deployment fails loudly. No
            model credential should exist in any environment of this
            repository; finding one is a deployment defect worth failing on.
        use_fixture: Force the fixture. Passing ``False`` is the only way to
            request a live model, and it is always refused.
        allow_live_providers: Mirrors the ``ALLOW_LIVE_PROVIDERS`` environment
            gate. Accepted so a caller can pass the real value rather than
            assume it, and deliberately **not** sufficient: the gate being open
            does not conjure an adapter or answer OQ-CBA-024.

    Returns:
        A :class:`FixtureSemanticTopicProvider`, which makes no network call
        and reads no credential.

    Raises:
        ProviderConfigurationError: if a model credential is present under any
            edition, or if a live adapter is requested at all.
    """
    if api_key:
        raise ProviderConfigurationError(
            f"a topic-model credential is present under edition {edition.value!r}. "
            "No environment in this repository should hold one: the model, the vendor "
            "terms, and whether a speaker's profile text may be sent to a third party "
            "at all are unanswered (OQ-CBA-024). Failing closed; check the environment "
            "configuration and secret bindings, and rotate anything actually bound."
        )

    if not use_fixture:
        raise ProviderConfigurationError(
            f"no live semantic topic model may be constructed under edition "
            f"{edition.value!r} — or any other. Which model, on whose credentials, "
            "under which terms, and with what per-run cost is OQ-CBA-024, and it is "
            "open. ALLOW_LIVE_PROVIDERS is a necessary gate, not a sufficient one: "
            f"it was passed as {allow_live_providers!r} here and there is still no "
            "adapter behind it. Customer §9's semantic comparison ships when the "
            "question is answered, not when the flag is flipped."
        )

    return FixtureSemanticTopicProvider()
