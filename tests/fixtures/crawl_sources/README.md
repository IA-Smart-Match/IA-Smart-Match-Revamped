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
