# Crawl-ingest scaffold fixtures

Synthetic source documents for `smartmatch_providers.fixture_ingest`, exercised
by `tests/unit/test_fixture_ingest.py`. Every value here is invented:
`example.edu` is IANA-reserved for documentation and resolves to nothing.
Nothing in this tree was fetched, and the module that reads it has no way to
fetch anything — see that module's docstring and
`docs/security/crawler-threat-model-draft.md`.

| File | What it pins |
|---|---|
| `campus_calendar.ics` | A dated event carrying one mappable and one unmappable tag, plus a second event with no `DTSTART` — unresolved time, therefore no identity key, and still returned rather than dropped. |
| `department/seminar_series.jsonld` | A `@graph`-wrapped, date-only event with one mappable and one unmappable keyword. |
| `department/unterminated.ics` | A truncated feed. Must produce a typed refusal, never an empty result that would read as "the source published nothing today". |
| `README.md` | Present on purpose: a non-source file in the tree must be skipped by the directory walk, not refused. |

## MP-1..5 evaluation corpus

The offline eval set from `docs/decisions/g3-crawler-decision.md` section 7
lives in the sibling tree `tests/fixtures/crawl_eval/` (not under this
directory: `test_fixture_ingest.py` pins the exact recursive file list here).

- Layout: one subfolder per category (`flyer_unknown`, `ambiguous_date`,
  `out_of_scope`, `injection`, `contact`, `allowlist`, `capped`) of synthetic
  `.ics` / `.jsonld` files on `example.edu` / `example.invalid`. The 200-record
  subdivision case is generated inside the test, not committed.
- `manifest.json`: per case `id`, `file`, `category`, `mp` (rules exercised),
  `expect` (`kind` plus parameters) and optional `xfail` (reason, for a seam
  that is not built; live crawl stays gated on T-07/T-13).
- Run: `.venv/bin/python -m pytest tests/unit/test_crawl_eval_corpus.py -q`.
  Floors: 100% per floored category, at least 90% whole set (xfail cases
  excluded until their seam exists). Network guard (narrow):
  `socket.socket` raises only while the harness fixture ingests, and an AST
  check bans network imports in the harness and four seam modules (direct
  imports only, not transitive).
