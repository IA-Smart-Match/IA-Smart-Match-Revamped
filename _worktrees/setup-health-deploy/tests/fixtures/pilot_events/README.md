# Pilot event-ingest fixtures

Synthetic source documents for `smartmatch_worker.event_ingest`, exercised by
`tests/integration/test_event_fixture_ingest.py` and
`tests/contract/test_events_api.py`. Every value here is invented:
`example.edu` is IANA-reserved for documentation and resolves to nothing.
Nothing in this tree was fetched, and the reader beneath it
(`smartmatch_providers.fixture_ingest`) has no way to fetch anything — see that
module's docstring and `docs/security/crawler-threat-model-draft.md`.

## Why this tree and not `crawl_sources/`

`tests/fixtures/crawl_sources/` belongs to the ingest scaffold's own unit
tests, which pin its directory walk to exactly three documents
(`tests/unit/test_fixture_ingest.py`). Adding a fourth there would fail a
merged test for a reason unrelated to what that test is about. This tree is
separate so the two can change independently.

It also carries something `crawl_sources/` deliberately does not: tags that
actually resolve against `smartmatch_domain.event_vocabulary.G3_VOCABULARY`,
the twelve terms G3 §6.2 approved. The scaffold's fixtures were written against
a two-term scratch vocabulary, so under the real one every tag in that tree
quarantines — which makes it excellent evidence for the quarantine path and
useless as evidence that a clean event can reach a coordinator's list.

## What each file pins

| File | What it pins |
|---|---|
| `engineering_calendar.ics` | A dated event whose two tags (`Hackathon`, `Keynote`) both map — the one event that survives to `GET /v1/units/{unit_id}/events` — plus a second with no `DTSTART`: unresolved time, no identity key, written but never listed. |
| `seminars.jsonld` | A `@graph`-wrapped, date-only event with one mappable keyword (`Career Panel`) and one that is not (`Underwater Basket Weaving`). Its quarantined value is what the tag-quarantine queue shows, and the reason the event itself is withheld from the listing. |
| `README.md` | Present on purpose: a non-source file in the tree must be skipped by the directory walk, not refused, and must not count toward `documents_read`. |
