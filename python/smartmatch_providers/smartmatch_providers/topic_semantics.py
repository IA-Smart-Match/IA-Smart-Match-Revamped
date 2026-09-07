"""Topic-comparison adapters, and the reason none of them is a live vendor.

Customer §9 asks for an "AI/semantic comparison" between an event description
and a speaker's recorded topic evidence. This module is the seam that request
goes through. Two adapters exist behind it: a deterministic playback fixture,
and — as of ADR-0017 — an offline, in-process embedding provider.

## Why there is no *live vendor* adapter

Choosing a hosted model is not an implementation detail that can be settled at
a keyboard. It commits the project to a vendor, a set of terms, a per-run
cost, and — because the input is a named person's professional profile — a
decision about sending CBA contact data to a third party. None of those has an
owner's answer, and none of them is answered by ADR-0017 either: ADR-0017
approves an *offline* model with no vendor, not a hosted one. So
:func:`build_semantic_topic_provider` still refuses a live, external client
under *every* edition, on the pattern ``registry.build_paid_extraction_provider``
established: the refusal is a property of what has been approved, not of where
the code happens to be running, and expressing it as a deployment property
would leave a production boot silently able to construct something nobody
ratified.

``ALLOW_LIVE_PROVIDERS=false`` is the standing environment default and is
necessary but not sufficient here — flipping it reaches no live-vendor
adapter, because none exists.

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

This fixture **remains the default** for every caller that does not opt in
otherwise, so existing golden pins and CI stay reproducible with no model file
on the runner.

## Why :class:`LocalEmbeddingSemanticTopicProvider` may honestly say ``True``

ADR-0017 approves an offline, in-process embedding model — averaged GloVe word
vectors, vendored inside this package — for §9's Topic comparison. Its
comparison is *not* token overlap: it compares trained distributional vector
representations of the words involved, so two texts that share no tokens but
mean similar things (e.g. "supply chain analytics" and "logistics
optimization") score above chance. That is the actual test a "semantic"
label makes, which is why this provider's
:attr:`~LocalEmbeddingSemanticTopicProvider.is_semantic_model` is ``True`` —
not because ADR-0017 says the word "semantic" in its title, but because the
mechanism genuinely is one. See ADR-0017 for the license, size, and
determinism evidence behind the vendored vector file.

The model runs entirely in this process, from a file already inside this
repository: no network call, no vendor, no per-run cost, and no speaker
profile text ever reaches a third party. That is precisely why ADR-0017 is an
*approval* and not a *contract* — there is no counterparty to bind.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Final

import numpy as np
from smartmatch_domain.one_sentence import assert_one_sentence

from smartmatch_providers.base import Edition, ProviderConfigurationError

__all__ = [
    "FIXTURE_TOPIC_PROVIDER_NAME",
    "LOCAL_EMBEDDING_MODEL_ID",
    "LOCAL_EMBEDDING_TOPIC_PROVIDER_NAME",
    "FixtureSemanticTopicProvider",
    "LocalEmbeddingSemanticTopicProvider",
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


#: Prefixed ``local-`` for the same reason the fixture is prefixed
#: ``fixture-``: the name on a stored score must say what actually produced
#: it, and this is neither a vendor nor a replay.
LOCAL_EMBEDDING_TOPIC_PROVIDER_NAME: Final[str] = "local-embedding-topic-semantics"

#: The vendored model, named and versioned so a stored score's provenance is
#: reproducible: which vector table produced it, pinned rather than "latest".
#: ADR-0017 records the license, size, and determinism evidence behind this
#: specific file.
LOCAL_EMBEDDING_MODEL_ID: Final[str] = "glove-wiki-gigaword-50-20k-v1"

#: The vendored vector table and its vocabulary, committed as plain repository
#: assets (~4.2 MB total) so no network call is ever made to reach them —
#: see ADR-0017.
_DATA_DIR: Final[Path] = Path(__file__).resolve().parent / "data"
_VECTORS_PATH: Final[Path] = _DATA_DIR / "glove_vectors.npy"
_VOCAB_PATH: Final[Path] = _DATA_DIR / "glove_vocab.txt"

#: A run of one-or-more letters or digits. Case folding happens before this
#: runs, so no character class for uppercase is needed. Punctuation and
#: whitespace are treated purely as separators; there is no attempt to keep
#: contractions or hyphenated compounds as single tokens, because the
#: vendored vocabulary indexes on the simple word forms GloVe was trained on.
_TOKEN_PATTERN: Final[re.Pattern[str]] = re.compile(r"[a-z0-9]+")


def _tokenize(text: str) -> list[str]:
    """Fold to lowercase and split into word/digit runs."""
    return _TOKEN_PATTERN.findall(text.casefold())


@lru_cache(maxsize=1)
def _load_vectors() -> tuple[dict[str, int], np.ndarray]:
    """Load the vendored vector table once per process.

    Cached because the table is read-only for the process's lifetime and
    re-parsing a 4 MB array on every comparison would be pure waste. A single
    cache entry is deliberate: there is exactly one vendored model, not a
    family selected at runtime.

    Raises:
        ProviderConfigurationError: the vendored data files are missing. This
            is a packaging defect, not a normal "no comparison" outcome, so it
            is distinguished from :class:`TopicComparisonUnavailable`.
    """
    if not _VECTORS_PATH.exists() or not _VOCAB_PATH.exists():
        raise ProviderConfigurationError(
            f"the vendored local-embedding model is missing from {_DATA_DIR}. "
            f"Expected {_VECTORS_PATH.name} and {_VOCAB_PATH.name}, committed as "
            "repository assets per ADR-0017. This is a packaging defect: the local "
            "embedding path makes no network call and cannot fetch them at runtime."
        )
    vectors = np.load(_VECTORS_PATH)
    words = _VOCAB_PATH.read_text(encoding="utf-8").splitlines()
    if len(words) != vectors.shape[0]:
        raise ProviderConfigurationError(
            f"the vendored local-embedding model is inconsistent: {len(words)} "
            f"vocabulary entries but {vectors.shape[0]} vectors. Regenerate both "
            "files together; a mismatch here means every lookup index is wrong."
        )
    return {word: index for index, word in enumerate(words)}, vectors


class LocalEmbeddingSemanticTopicProvider:
    """Compares topic text by averaged word-embedding cosine similarity.

    ADR-0017's approved adapter: an offline, in-process model with no vendor,
    no per-run cost, and no network call. See the module docstring for why
    :attr:`is_semantic_model` is honestly ``True`` here and not on the
    fixture.

    The comparison is deliberately simple — mean-pool the vendored GloVe
    vectors for each recognized word, then take the cosine similarity of the
    two pooled vectors — documented in ADR-0017 alongside why that is enough
    to be genuinely semantic without being a claim of state-of-the-art
    accuracy. Word order is discarded; a caller after phrase-level nuance
    needs a different, larger model, which ADR-0017's "Alternatives
    considered" section discusses.
    """

    name = LOCAL_EMBEDDING_TOPIC_PROVIDER_NAME

    #: Genuinely true: this compares trained distributional vectors, not
    #: tokens. See the module docstring.
    is_semantic_model = True

    def __init__(self) -> None:
        self._vocab, self._vectors = _load_vectors()
        #: Every pair this provider was asked about, in order — the same
        #: audit hook the fixture exposes, so a test can assert whether a
        #: branch that must not consult a provider did.
        self.calls: list[tuple[str, str]] = []

    def _embed(self, text: str) -> np.ndarray | None:
        """Mean-pool the vendored vectors for ``text``'s recognized words.

        Returns ``None`` when no word in ``text`` is in the vendored 20,000-word
        vocabulary — deliberately not a zero vector, which would silently
        compare "nothing recognized" against real content as if it were a
        real, if unusual, topic.
        """
        indices = [self._vocab[token] for token in _tokenize(text) if token in self._vocab]
        if not indices:
            return None
        pooled: np.ndarray = self._vectors[indices].mean(axis=0)
        return pooled

    def compare(self, request_description: str, speaker_evidence: str) -> TopicSimilarity:
        """Return the cosine-similarity fit between the two texts.

        Raises:
            TopicComparisonUnavailable: neither text yielded a recognized
                word, so no embedding could be built for one or both sides.
                Never a default value — see the module docstring on storing
                an assumption as a fact.
        """
        self.calls.append((request_description, speaker_evidence))

        request_vector = self._embed(request_description)
        speaker_vector = self._embed(speaker_evidence)
        if request_vector is None or speaker_vector is None:
            raise TopicComparisonUnavailable(
                f"{self.name}: no word in the request description and/or the speaker's "
                "topic evidence is in the vendored 20,000-word vocabulary, so no "
                "embedding could be built for one or both sides of this comparison."
            )

        request_norm = float(np.linalg.norm(request_vector))
        speaker_norm = float(np.linalg.norm(speaker_vector))
        if request_norm == 0.0 or speaker_norm == 0.0:
            # A recognized word with an all-zero vector is not a real
            # possibility in this vendored table, but a provider must never
            # divide by zero silently to produce a plausible-looking score.
            raise TopicComparisonUnavailable(
                f"{self.name}: an embedding for this comparison had zero magnitude, "
                "so a cosine similarity could not be computed."
            )

        # Cosine similarity is [-1, 1] by construction; the clamp only guards
        # against floating-point drift pushing a near-1.0 result a fraction
        # past the boundary.
        cosine = float(np.dot(request_vector, speaker_vector) / (request_norm * speaker_norm))
        cosine = max(-1.0, min(1.0, cosine))

        # TopicSimilarity.score (and CbaTopicFactorScore.value above it) is
        # constrained to [0.0, 1.0]; this affine rescale is the standard,
        # information-preserving map from cosine similarity's natural range.
        score = (cosine + 1.0) / 2.0
        percent = round(score * 100, 1)

        return TopicSimilarity(
            score=score,
            rationale=(
                "Offline embedding cosine similarity between the request description "
                f"and the speaker's recorded topic evidence was {percent} percent."
            ),
            provider=self.name,
            model_id=LOCAL_EMBEDDING_MODEL_ID,
            is_semantic_model=True,
        )


def build_semantic_topic_provider(
    edition: Edition,
    *,
    api_key: str | None = None,
    use_fixture: bool = True,
    allow_live_providers: bool = False,
    use_local_embedding: bool = False,
) -> FixtureSemanticTopicProvider | LocalEmbeddingSemanticTopicProvider:
    """Construct the topic-comparison provider.

    Two adapters exist: the deterministic playback fixture (the default for
    every caller who writes nothing extra), and — since ADR-0017 —
    :class:`LocalEmbeddingSemanticTopicProvider`, reached only by passing
    ``use_local_embedding=True``. No live, external vendor adapter exists
    under any edition; mirrors ``registry.build_paid_extraction_provider``.

    ``use_fixture`` defaults to ``True`` and ``use_local_embedding`` defaults
    to ``False`` for the same reason the paid builder gives: the safe outcome
    must be what a caller gets by writing nothing, and the only way to ask for
    anything else is to say so explicitly.

    Args:
        edition: The running edition. Recorded in the refusal messages so an
            operator can see which deployment asked, and otherwise not
            consulted — every edition gets the same answer.
        api_key: Present only so a misconfigured deployment fails loudly. No
            model credential should exist in any environment of this
            repository — the offline embedding path needs none — so finding
            one is a deployment defect worth failing on, regardless of
            ``use_local_embedding``.
        use_fixture: Force the fixture. Ignored when ``use_local_embedding``
            is ``True``; otherwise, passing ``False`` is the only way to
            request a live, external vendor model, and it is always refused.
        allow_live_providers: Mirrors the ``ALLOW_LIVE_PROVIDERS`` environment
            gate. Accepted so a caller can pass the real value rather than
            assume it, and deliberately **not** sufficient on its own: the
            gate being open does not, by itself, reach the offline embedding
            path or conjure a live vendor adapter — see
            ``use_local_embedding``.
        use_local_embedding: Opt into ADR-0017's offline, in-process embedding
            provider. Off by default so no existing caller's behavior, golden
            pin, or CI run changes by upgrading this package.

    Returns:
        A :class:`FixtureSemanticTopicProvider` by default, or a
        :class:`LocalEmbeddingSemanticTopicProvider` when
        ``use_local_embedding=True``. Neither makes a network call; neither
        reads a credential.

    Raises:
        ProviderConfigurationError: if a model credential is present under any
            edition, if a live vendor adapter is requested
            (``use_fixture=False`` without ``use_local_embedding=True``), or
            if the vendored local-embedding data files are missing.
    """
    if api_key:
        raise ProviderConfigurationError(
            f"a topic-model credential is present under edition {edition.value!r}. "
            "No environment in this repository should hold one: ADR-0017 approves "
            "only the offline, in-process embedding path, which reads no credential "
            "at all, and a live external vendor remains unapproved (OQ-CBA-026 closed "
            "by removing the vendor, not by approving one). Failing closed; check the "
            "environment configuration and secret bindings, and rotate anything "
            "actually bound."
        )

    if use_local_embedding:
        return LocalEmbeddingSemanticTopicProvider()

    if not use_fixture:
        raise ProviderConfigurationError(
            f"no live, external vendor semantic topic model may be constructed under "
            f"edition {edition.value!r} — or any other. OQ-CBA-026 is closed by "
            "ADR-0017, which approves an offline, in-process embedding model with no "
            "vendor (pass use_local_embedding=True to reach it) — it does not approve "
            "a hosted or API-backed one, which remains a separate, unanswered question. "
            "ALLOW_LIVE_PROVIDERS is a necessary gate, not a sufficient one: it was "
            f"passed as {allow_live_providers!r} here and there is still no live-vendor "
            "adapter behind it."
        )

    return FixtureSemanticTopicProvider()
