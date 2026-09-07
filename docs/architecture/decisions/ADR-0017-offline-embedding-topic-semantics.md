# ADR-0017 — An offline, in-process embedding model is approved for §9 Topic

**Status:** Accepted
**Date:** 7 September 2026
**Contract:** `docs/product/cba-smart-match-customer-requirements.md` §9; ADR-0011; ADR-0016
**Backlog:** CBA-MATCH-TOPIC
**Findings:** Pilot dataset generator (PR #112) — of 100 named candidates, only 5
were scorable, 3 shortlisted, 56 dropped as `cba_semantic_topic: unknown`, 39
excluded with honest §19 reasons. All 56 dropouts have real topic text the
playback fixture holds no recording for.

## Context

`docs/plans/open-questions/cba-phase-deferred.md` records two open questions
about customer §9's Topic comparison:

- **OQ-CBA-026** asks which semantic model performs the comparison, on whose
  credentials, under which vendor terms, at what per-run cost — and, because
  the input is a named person's professional profile text, whether a speaker's
  `topic_text` and `prior_talk` may be sent to a third party at all.
  `smartmatch_providers.topic_semantics.build_semantic_topic_provider` answers
  that question today by shipping no live adapter at all: it returns a
  deterministic playback fixture by default and refuses a live client under
  every edition, on the pattern `build_paid_extraction_provider` established.
  A model credential found in any environment fails closed. The fixture
  reports `is_semantic_model = False`, honestly, because it computes nothing.
- **OQ-CBA-061** is the consequence of leaving OQ-CBA-026 open through a pilot:
  a speaker *with* topic text on file scores worse than one with none, because
  the one with none gets §9's stated neutral policy value while the one with
  topic text hits the fixture's refusal and comes back `unknown` — which the
  matching gate correctly treats as unscorable. The pilot generator's numbers
  make this concrete: 56 of 100 candidates, all with real topic text, were
  dropped as unknown. The best-documented speakers are exactly the ones the
  system could not evaluate.

Two answers were considered and rejected before this one:

1. **Drop topic text from the pilot seed** so every speaker becomes
   `policy_neutral 0.50`. Rejected: it does not answer OQ-CBA-026, it hides
   OQ-CBA-061 by removing the evidence that exposes it, and it would apply
   §9's neutral — a stated policy for an *observed absence* — to data that
   was never absent. `cba_semantic_topic.py`'s own docstring says this
   distinction is the reason the module exists.
2. **Ratify a lexical (token-overlap) comparator** under the semantic
   provider's name and factor key. Rejected explicitly by both the module
   docstring and the OQ register: a lexical comparison shipped as "semantic"
   puts an untrue provenance claim into every stored match permanently, long
   after anyone remembers the scorer was three lines of set intersection.

## Decision

**An offline, in-process sentence-embedding model is approved for customer
§9's Topic comparison.** Specifically: averaged GloVe word vectors (Wikipedia
2014 + Gigaword 5, 50-dimensional, trained by the Stanford NLP Group),
vendored as a trimmed 20,000-word subset inside `smartmatch_providers`, with
cosine similarity between the request description's embedding and the
speaker's topic-evidence embedding as the score.

This is a genuine semantic comparison, not a lexical one: two texts that share
no tokens but express the same meaning (e.g. "supply chain analytics" and
"logistics optimization") score above chance, because GloVe vectors are
trained on the distributional structure of a large corpus, not on the two
input strings. `LocalEmbeddingSemanticTopicProvider.is_semantic_model` is
`True` because that is true, not because the name says so.

**Why an approval suffices, and a contract does not.** The model runs
in-process, on CPU, from a file already inside this repository. There is no
API call, no network egress at match time, and therefore:

- **No vendor.** Nobody is contracted with, and nobody's terms of service
  govern this comparison.
- **No per-run cost.** The model is loaded once and reused; there is no
  metered call.
- **No external retention.** A speaker's `topic_text` and `prior_talk` are
  read into this process's memory to build a vector and are never sent
  anywhere. No third party ever sees them, holds them, or logs them.

OQ-CBA-026 asked three questions that only have answers when a vendor is
involved — whose credentials, under whose terms, at what per-run cost — and a
fourth that is a privacy question independent of vendor status. This decision
answers the vendor questions by removing the vendor, and answers the privacy
question directly: **no**, this comparison never leaves the process, so there
is nothing to approve at the level of a data-sharing contract.

**OQ-CBA-061 dissolves by mechanism, not by fiat.** It existed because two
things were both true: §9's neutral is a genuine policy for an *observed
absence*, and every candidate *with* topic text hit a refusal that produced
`unknown`. This decision does not touch the neutral policy and does not touch
the `unknown` branch's meaning — it removes the refusal for the offline path,
so a candidate with real topic text now reaches a `measured` score instead of
an `unknown`. The perverse ordering (`unknown` sorting below `policy_neutral`
in every consumer that treats unscorable as worst) had nothing left to act on
once measurement is possible; there is no separate policy change for
OQ-CBA-061 to record.

**The fixture stays the default, everywhere, for everyone who does not opt
in.** `build_semantic_topic_provider(edition)` — called with no keyword
arguments — returns `FixtureSemanticTopicProvider` exactly as before. Existing
golden pins, contract tests, and CI stay reproducible without a model file on
the runner and without a behavior change nobody asked for. The offline
embedding path is reached only by the new `use_local_embedding=True` keyword,
which is off by default.

**The refusal for a live, external vendor client is untouched.** This
decision approves an in-process model with no vendor; it does not approve a
hosted or API-backed one. `use_fixture=False` (with `use_local_embedding` left
at its default of `False`) still raises `ProviderConfigurationError` under
every edition, and a model credential (`api_key`) found in any environment
still fails closed. Nothing here reaches an adapter that calls out to a
service — that remains unapproved, and remains OQ-CBA-026's original,
narrower question if it is ever asked again about a specific vendor.

## Rationale

**Why GloVe 50d, specifically.** Three properties, each disqualifying to give
up:

- **License.** Stanford's pretrained GloVe vectors are released under the
  Public Domain Dedication and License v1.0 (PDDL) — the data, not merely the
  training code, which is Apache-2.0. PDDL is unconditional: no attribution
  requirement, no share-alike, no field-of-use restriction. A vendored subset
  of the data carries the same dedication.
- **Size.** The full `glove.6B.50d` vector set (400,000 words) is ~163 MB as
  plain text. This decision vendors only the 20,000 most frequent words —
  everyday and business vocabulary overwhelmingly falls inside the 20k most
  frequent English words — as a NumPy `float32` array (`4.0 MB`) plus a
  newline-delimited vocabulary file (`173 KB`). Total: **~4.2 MB**, small
  enough to commit as a plain repository asset with no LFS, no build step, and
  no fetch at any point after `git clone`.
- **No new runtime dependency.** `numpy` is already a locked runtime
  dependency (a transitive pin from `ortools`, promoted here to a direct one).
  No `torch`, `onnxruntime`, or `sentence-transformers` is added — each would
  add tens to hundreds of megabytes, a materially larger CVE surface, and a
  license to re-audit. Averaging pretrained word vectors and taking cosine
  similarity needs nothing beyond array arithmetic.

**Why word-vector averaging is "genuinely semantic" and not the rejected
lexical comparator.** The rejected option compares which *tokens* two strings
share. This compares *trained vector representations* of those tokens — GloVe
vectors place semantically similar words near each other in the vector space
because they were fit to word co-occurrence statistics across a 6-billion-token
corpus, not because they share characters. "Logistics" and "supply chain" have
no token overlap and a high cosine similarity; that is the property a lexical
comparator cannot have and an embedding-based one does. The comparison is
approximate — averaging discards word order — but approximate semantic
information is still semantic information, and the class of thing "is this
provider allowed to call itself semantic" cares about the mechanism (trained
distributional vectors and geometric similarity), not the sophistication tier.

**Why cosine similarity is mapped from `[-1, 1]` to `[0, 1]`.** `TopicSimilarity.score`
and `CbaTopicFactorScore.value` are both constrained to `[0.0, 1.0]`
(`smartmatch_domain.factors.cba_semantic_topic`). Cosine similarity's natural
range is `[-1, 1]`; the affine map `(cosine + 1) / 2` is the standard,
information-preserving rescaling and is applied once, at the provider
boundary, so nothing downstream needs to know the raw range existed.

**Determinism and its tolerance.** Given the same two input strings, the same
vendored vector file, and the same NumPy version, this provider is
bit-reproducible: averaging and cosine similarity are fixed-order floating
point operations over a fixed input, with no randomness, no batching, and no
GPU non-determinism anywhere in the path. The one caveat worth stating rather
than assuming away: floating-point summation order can differ across NumPy
versions or CPU architectures by less than `1e-6` absolute on inputs of this
size. `tests/unit/test_cba_semantic_topic_local_embedding.py` therefore
compares scores with `abs_tol=1e-6`, not `==`, and the vendored model file's
identity is pinned by committing it as a versioned repository asset rather
than fetching it — there is no "latest" to drift to.

**Why this is an approval and not a contract, restated plainly.** A contract
exists to bind an external party to terms — data handling, cost, availability,
liability. There is no external party here: the model is a file this
repository already owns, running in a process this repository already
controls. What remained to decide was purely internal — is this technique
good enough, and does the product owner accept its approximate, non-vendor
nature — which is exactly what an approval, rather than a procurement
instrument, is for.

## Consequences

- `smartmatch_providers.topic_semantics` gains
  `LocalEmbeddingSemanticTopicProvider` and vendors
  `smartmatch_providers/data/glove_vectors.npy` and
  `smartmatch_providers/data/glove_vocab.txt` (~4.2 MB total).
- `build_semantic_topic_provider` gains `use_local_embedding: bool = False`.
  Every existing call site and every existing test is unaffected: the fixture
  remains what a caller gets by writing nothing.
- `requirements/runtime.in` promotes `numpy` from a transitive pin to a direct
  dependency of `smartmatch-providers`. The pinned version in the lock is
  unchanged (`ortools` already forced it to the version now declared
  directly); regenerating the lock changes only the `# via` provenance
  comment, not a version.
- OQ-CBA-026 and OQ-CBA-061 are both closed in
  `docs/plans/open-questions/cba-phase-deferred.md`, referencing this ADR.
- A live, vendor-backed Topic model remains unapproved. Any future proposal to
  call an external semantic API for §9 is a new, narrower question — this ADR
  does not pre-clear it, and the existing refusal for `use_fixture=False`
  without `use_local_embedding=True` stays in force to make that concrete.

## Alternatives considered

**A hosted embedding API (OpenAI, Cohere, Vertex AI, etc.).** Rejected for
this decision: it reintroduces every element that made OQ-CBA-026 an approval
question rather than an engineering one — a vendor, terms, per-run cost, and
sending a named person's profile text to a third party. Nothing about a
hosted API is disqualified in principle; it is simply a different, larger
question than the one this ADR answers, and answering the small question
first is what actually unblocks the pilot today.

**A larger local transformer model (e.g. a distilled sentence-transformer via
ONNX).** Considered and set aside for this PR specifically, not rejected in
principle. Such a model would likely score better on nuanced phrasing, but it
requires a new runtime dependency (`onnxruntime` or `torch`) with its own
license and vulnerability review, and a model artifact one to two orders of
magnitude larger than the 4.2 MB vendored here. That is a legitimate future
upgrade to `LocalEmbeddingSemanticTopicProvider`'s implementation — the
factor-level contract (`SemanticTopicProvider`, `TopicComparison`,
`is_semantic_model`) does not change if the vector source underneath it does.

**TF-IDF or another purely corpus-relative weighting scheme.** Rejected as a
disguised version of the option this ADR explicitly is not: a comparator whose
notion of similarity is exact-token matching, reweighted by frequency, is
still lexical. It would fit the letter of "not `token overlap`" while failing
the actual test the OQ register states — whether the comparison can recognize
that two differently-worded topics mean the same thing.
