# Vendored embedding model — ADR-0017

`glove_vectors.npy` and `glove_vocab.txt` are a trimmed subset of the
Stanford NLP Group's pretrained GloVe word vectors (Wikipedia 2014 +
Gigaword 5, 50-dimensional), used by
`smartmatch_providers.topic_semantics.LocalEmbeddingSemanticTopicProvider`.
See `docs/architecture/decisions/ADR-0017-offline-embedding-topic-semantics.md`
for the full approval, license, and determinism record.

- **Source:** `glove-wiki-gigaword-50`, the Stanford GloVe `glove.6B.50d`
  vectors as redistributed by the `gensim-data` project.
- **License:** Public Domain Dedication and License v1.0 (PDDL) —
  <https://www.opendatacommons.org/licenses/pddl/1.0/>. Unconditional: no
  attribution or share-alike requirement. This trimmed subset carries the
  same dedication as the source data.
- **Trim:** the 20,000 most frequent words of the original 400,000-word
  vocabulary (GloVe's files are frequency-ordered), kept at the original
  50 dimensions.
- **Files:**
  - `glove_vectors.npy` — a `float32` NumPy array, shape `(20000, 50)`
    (~4.0 MB).
  - `glove_vocab.txt` — the 20,000 words, one per line, in the same order
    as the array's rows (~173 KB).
- **No network call at match time.** Both files are ordinary repository
  assets, loaded from disk by `smartmatch_providers.topic_semantics`. There
  is no fetch step, no build step, and no external service involved in
  producing a comparison.

## Regenerating this asset

Not part of any build or CI step — this is a one-time vendoring, pinned by
committing the result rather than by a fetch that could return something
different later. To reproduce it:

1. Download `glove-wiki-gigaword-50.gz` from the `gensim-data` project's
   GitHub releases (a gensim `KeyedVectors` text-format re-publication of
   Stanford's `glove.6B.50d`, under the same PDDL license).
2. Decompress it to `word2vec`-format text: a header line `400000 50`,
   then one line per word — the word, then 50 space-separated floats,
   ordered most-frequent-first.
3. Keep the first 20,000 word lines, write their vectors to
   `glove_vectors.npy` as a `(20000, 50)` `float32` NumPy array, and write
   their words, in the same order, one per line, to `glove_vocab.txt`.
