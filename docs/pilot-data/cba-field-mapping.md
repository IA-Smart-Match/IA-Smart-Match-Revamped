# CBA contact import — field-to-schema mapping

**Status:** Released
**Date:** 5 September 2026
**Source:** [`docs/product/cba-smart-match-customer-requirements.md`](../product/cba-smart-match-customer-requirements.md) §§18–19
**Implements:** `docs/plans/2026-09-05-cba-pivot-waves.md` — `CBA-IMPORT-CONTRACT`
**Contract:** [`columns.yaml`](columns.yaml) — the single source of truth for column names
**Schema:** migration `0024_cba_classification_schema` (`CBA-DATA-SCHEMA`), mirrored in
`python/smartmatch_persistence/smartmatch_persistence/schema.py`

## What this document is

One table, answering one question: for each field customer §18 names, which
column does an import declare, and which column will eventually hold it.

It adds no behaviour. `columns.yaml` is the contract; this file explains it
and records the three places where the contract's spelling and the customer's
wording differ on purpose. If the two ever disagree, `columns.yaml` is right
and this file is stale.

## §18 "Expected source columns"

| Customer §18 field | Import column (`professionals`) | Required? | Where a reviewed value lands | Notes |
|---|---|---|---|---|
| Name | `name` | **required** | professional identity (`user_account`, per the synthetic pilot authorization's Choice A) | Ratified 28 Aug 2026 as `name`, not `full_name`. |
| Company Name | `company` | optional | not yet persisted | **Spelling differs on purpose** — see "Three fields keep an earlier spelling". §19 reads company + title to propose a classification; that inference is `CBA-IMPORT-CLASSIFY`'s. |
| Current Position | `title` | optional | not yet persisted | Same. |
| Contact Email | `contact_email` | optional, **withheld** | *nothing — CBA Gate C is open* | Declared so the column is recognized; the value is dropped before any write. See "CBA Gate C". |
| Alumni (Y/N) | `alumni` | optional | not yet persisted | The `(Y/N)` in §18 is the customer describing the value domain, not header text. A header literally spelling `Alumni (Y/N)` normalizes to `alumni_y_n` and would be reported `unexpected_columns`. |
| Graduation Year | `graduation_year` | optional | not yet persisted | Carried as submitted text; nothing parses it. |
| Major | `major` | optional | not yet persisted | |
| Willingness to Partner with CPP (Y/N) | `willingness_to_partner_with_cpp` | optional | not yet persisted | **Not a consent record.** See "Email collection is never consent". |
| Past Engagement (free text) | `past_engagement` | optional | not yet persisted | |

"Not yet persisted" means exactly that: migration `0024` gave the
classification and location fields a home and left the biographical ones for a
later card. Every column reaches a `review_item` regardless — architecture
v1.1 §1.5's quarantine-and-review path is where an import's values live until
a Speaker Connector accepts them — so nothing is lost while those columns do
not exist.

## §18 "Additional fields required by matching"

These take `speaker_profile`'s spellings rather than the customer's prose,
because §18 gives prose here ("city and/or ZIP code") and no header text. An
import column and the column a reviewed record lands in then line up without a
translation table.

| Customer §18 field | Import column (`professionals`) | Required? | `speaker_profile` column | Notes |
|---|---|---|---|---|
| primary Industry sector | `primary_industry_code` | optional | `primary_industry_code` (+ `industry_taxonomy_version`) | One of the 20 NAICS sector groups released by `CBA-TAXONOMY` (`cba-naics-2026-09-04`). **The import does not validate it** — see "What the import deliberately does not do". |
| primary Role category | `primary_role_code` | optional | `primary_role_code` (+ `role_taxonomy_version`) | One of the 10 CBA career role categories (`cba-roles-2026-09-04`). Not the ADR-0012 event-tag vocabulary, which uses the word "role" for an unrelated thing. |
| Topic/interests/expertise text | `expertise_tags` | optional | `topic_text` | **Spelling differs on purpose** — `expertise_tags` was ratified 28 Aug 2026. |
| city | `location_city` | optional | `location_city` | §10 measures proximity in miles from CPP; §18 says city and/or ZIP, so neither is derived from the other and neither is required. |
| ZIP code | `location_postal_code` | optional | `location_postal_code` | The schema says `postal_code`; the import follows the schema rather than §18's "ZIP". |
| optional prior talk information | `prior_talk` | optional | `prior_talk` | |

The two `taxonomy_version` columns have no import column and never will: a
version token records which released table evaluated a code, so it is stamped
by the resolver at classification time, never supplied by a spreadsheet.

## Nothing new is required

`required` stays exactly `("name", "metro_region")`. §18's own first sentence
is the reason — the data "is scattered across multiple people and systems" and
"there is currently no single authoritative export". A contract that made
Graduation Year mandatory would refuse most real submissions for the reason
the customer supplied in advance.

This is not a weakening of the fail-closed posture. What fails closed here is
a contract that cannot be **read**: a missing or malformed `columns.yaml` is a
terminal `column_contract_unavailable` policy failure, and a dataset the
contract does not declare is a terminal `dataset_contract_unknown`. An
*incomplete row* is a different thing, and quarantine-and-review is what
carries it.

Whether `metro_region` should stay required for a CBA-era export is
**OQ-CBA-012(a)**, deliberately unanswered: it was ratified for the IA West
pilot, and §10 now measures proximity from city and/or ZIP. De-ratifying a
required column is a decision, not a refactor.

## Three fields keep an earlier spelling

`company`, `title`, and `expertise_tags` were ratified on 28 August 2026.
Customer §18 later named the same three fields "Company Name", "Current
Position", and "Topic/interests/expertise text".

`smartmatch_domain.ingest.normalize_header` is case-, whitespace-, and
punctuation-insensitive — it is **not** a synonym table. So `Company Name`
normalizes to `company_name`, which is a *different* column from `company`.
Declaring both would put the same customer field in the contract twice, and a
coordinator's export would satisfy whichever spelling they happened to use.
That is the one failure `columns.yaml` exists to prevent, so only one spelling
is declared.

The consequence, stated plainly: an export whose header literally reads
`Company Name` today produces an `unexpected_columns` **warning** for that
column. It is not an error, the import still succeeds, and `_normalize_row`
does not drop unrecognized keys — the value still reaches the review item. The
cost is a warning and a column a reviewer has to place by hand.

Whether to re-ratify these three under the customer's own header text is
**OQ-CBA-012(b)**. Adopting an alias mechanism instead would be a change to
`normalize_header`'s contract, and is out of this card's fence either way.

## CBA Gate C — `contact_email` is withheld

Tracked as **OQ-CBA-011**. `professionals.contact_email` is declared under
`gate_pending` with posture `withhold`:

- **Recognized.** An export carrying `Contact Email` is never refused and
  never reported as `unexpected_columns`. §18 asks for the field; pretending
  not to understand it would be dishonest.
- **Not stored.** The value is dropped by `_normalize_row` before any
  `review_item` is written.
- **Reported.** The drop appears as a `columns_withheld_pending_gate`
  **warning** naming the column, so a coordinator sees exactly what was not
  kept. A warning, never an error: a gate that has not answered cannot make a
  dataset unusable, because refusing would be enforcing an answer too.

**Why P9 Gate B does not cover this.** Gate B closed 2 Sep 2026 over the three
*published* contact fields on the `events` dataset — details an organizer has
already published on a public event page — and §§B2/B3 of its worksheet turn
on exactly that published-ness. A speaker's personal address on a
coordinator's spreadsheet is different data answering a different question,
and Gate B still required a named privacy owner and the full ADR-0014 field
set to answer the easier one. Reading §18's mention of the column as an
authorization to store it would be inventing the harder answer.

**What closing the gate needs:** a program owner and a named privacy owner
recording a collect-or-drop decision with ADR-0014's fields, including
retention, access, and deletion. When it closes, delete the `gate_pending`
entry and its `open_questions` paragraph together — leaving one without the
other is how a contract starts lying.

## Email collection is never consent

`contact_email` and `willingness_to_partner_with_cpp` are contact data. They
say nothing about permission, and this card adds no path by which they could.

`smartmatch_domain.consent` (architecture v1.1 §2.3) admits four approved
consent sources — self-service, authenticated, in-person, and institutional
relationship — and an import is none of them. There is no transition from any
research or import state to an active recipient except through `consented`,
and `consented` requires an approved source, so no spreadsheet can make anyone
send-eligible.

§18's "Willingness to Partner with CPP (Y/N)" is a **stated preference
recorded on a contact record**, not a `ConsentSource`. It tells a Speaker
Connector whether the person is likely to accept an invitation; it does not
authorize an email. Reading it as permission would be exactly the inference
v1.1 §2.3 exists to forbid.

`tests/unit/test_cba_import_columns.py::TestEmailCollectionIsNotConsent` is
where that is asserted rather than merely stated.

## What the import deliberately does not do

- **No classification.** `primary_industry_code` and `primary_role_code` are
  carried as submitted. The import does not check a value against the released
  taxonomies, resolve a display name to a code, or infer either from company
  or title. §19 puts inference and a Speaker Connector's correction downstream
  of the import; an unrecognized value there is a review item, not an import
  failure, and the unmapped text is the input to the next taxonomy version.
  `CBA-IMPORT-CLASSIFY` owns that step.
- **No persistence.** This card wrote no DDL and no write path. Values reach
  `review_item` as they already did.
- **No new Python.** `columns.yaml` gained columns; `column_contract.py`,
  `handlers.py`, and `ingest.py` are unchanged. The gate and withhold
  machinery P9 built for Gate A and Gate B carries the new column as-is, which
  is the point of having built it that way.

## Tests

| File | Holds |
|---|---|
| `tests/unit/test_cba_import_columns.py` | Every §18 field is declared exactly once; nothing new is required; `contact_email` is withheld and reported; no import path implies consent; the CBA fixture validates clean. |
| `tests/unit/test_column_contract.py` | The shipped `professionals.optional` set, pinned; CBA Gate C is the only open gate. |
| `tests/unit/test_import_column_contract_wiring.py` | A full CBA row normalizes with `contact_email` dropped and everything else intact; classification values are carried verbatim. |
| `docs/pilot-data/verify_fixtures.py` | `professionals_cba_contact.json` produces no findings — run by hand, not in CI. |
