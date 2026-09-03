# SmartMatch pilot data

Synthetic test dataset for the SmartMatch pilot, built so `POST
/v1/units/{unit_id}/imports`'s live import path (rows travel already-parsed in
the request body; a live import writes an `import_batch` plus one quarantined
`review_item` per row) has something real to run against, and so the column
contract the pilot import path is held to — ratified 28 Aug 2026 in
`columns.yaml`. Both column questions the ratification left open (P9 Gate A,
`board_role`; P9 Gate B, the three published contact fields) closed
2 Sep 2026 — see "Resolved gates" below.

## What this is, and is not

- **Every person, and every organization that is not a real public
  institution, is fabricated.** Names, companies, consulting groups, "labs",
  and "ventures" in these fixtures do not refer to real people or businesses.
  Any resemblance to a real individual is coincidental.
- **Geography is real and deliberate.** The pilot's focus is **Los Angeles and
  Orange County, California**, centered on **Cal Poly Pomona** (California
  State Polytechnic University, Pomona -- Pomona, LA County, 91768) as the
  primary campus. City names (Pomona, Walnut, Diamond Bar, Anaheim, Irvine,
  Fullerton, Long Beach, Santa Ana, Tustin, Costa Mesa, Whittier, Rowland
  Heights, San Gabriel Valley, San Fernando Valley, ...) are real. Event host
  institutions (Cal Poly Pomona, UC Irvine, UCLA, Cal State Fullerton, Cal
  State Long Beach, Mt. San Antonio College, Citrus College, Rio Hondo
  College, Fullerton College, Santa Ana College, Orange Coast College, Cypress
  College, Golden West College) are real *public* institutions, used only as
  the "Host / Unit" of a fabricated event/program name -- no fixture claims
  any of these institutions actually ran the fabricated program named
  alongside it.
- **This is not a demo-data fallback.** These files are not read by any
  application code and are not served to a live pilot in place of real data
  (that pattern is explicitly forbidden -- see `tools/scan_forbidden.py`'s
  `demo-mode-fallback` rule). They exist so a human can exercise the import
  path and its validation locally, deliberately, one file at a time.
- **The column contract in `columns.yaml` is ratified for the pilot** (28 Aug
  2026). Both column questions the ratification left open closed 2 Sep 2026
  (P9 Gate A, Gate B) — see that file's `open_questions` section and "Resolved
  gates" below. As of P9 card W1, `services/worker/smartmatch_worker` reads
  it and holds live imports to it (see "Why this exists" below); ratification
  is also what the fixtures and ``verify_fixtures.py`` are held to.

## Why this exists

`smartmatch_domain.ingest.validate_columns` is real and already did real
work before any contract existed -- it catches empty datasets, ragged rows,
and colliding headers without knowing a single column name. What it lacked was
a schema to hold an import to.

**As of 2 September 2026 (P9 card W1) it has one.**
`services/worker/smartmatch_worker/column_contract.py` reads `columns.yaml`
and `handlers.py` hands its declarations to `validate_columns`, so an
inline-rows import is now validated against the ratified contract instead of
`required=(), optional=()`. The YAML is the single source of truth: no column
name is repeated in Python, a contract that cannot be read is a terminal
`column_contract_unavailable` refusal rather than a quiet fall back to
validating nothing, and a dataset the contract does not declare is refused as
`dataset_contract_unknown`.

Enforcement is **section-level**. A column still behind an open question
would be declared under its dataset's `gate_pending` map and never treated as
ratified. No column is gate-pending today: P9 Gate A (`board_role`, a
modelling question) and P9 Gate B (the three published contact fields, a
privacy question) were the only entries, and both gates closed 2 Sep 2026.
`board_role` is no longer a `professionals` column at all -- it is
relationship-scoped, on the `professional_unit_relationship` table
(`python/smartmatch_persistence/smartmatch_persistence/schema.py`, migration
`db/migrations/versions/0012_professional_unit_relationship.py`), with no
effective-date columns for the pilot. The three contact fields are collected
and stored per Gate B's decision. See the `GATE-PENDING COLUMNS` section in
`columns.yaml`.

The migration manifest's own **F-28** finding records that architecture v1.1
Section 1.5 -- the spec section that would define the real contract -- "has
not been read into this repository." ``columns.yaml`` fills that gap for the
pilot; it does not resolve F-28, since it cannot cite a section that isn't
present.

## Layout

```
docs/pilot-data/
  README.md              this file
  columns.yaml            ratified required/optional columns + per-column blank_sentinels
  verify_fixtures.py       loads every fixture and asserts the finding codes below
  fixtures/
    professionals_*.json   the people who speak or mentor
    events_*.json           the sessions they are matched to
    empty_dataset.json      zero rows, shared by both datasets
```

Every fixture is a JSON array of row objects -- the exact shape
`ImportRequest.rows` takes in `services/api/smartmatch_api/routers/imports.py`
(`list[dict[str, Any]]`), not CSV.

## Fixture-to-finding-code table

Every code below is produced by `docs/pilot-data/verify_fixtures.py` running
against the proposed contract in `columns.yaml`; run the script yourself (see
below) to reproduce this table's right-hand column.

| Fixture | Dataset | Defect | `validate_columns` finding code(s) |
|---|---|---|---|
| `professionals_clean.json` | professionals | none -- 30 rows, every declared column present and consistent | *(none)* |
| `professionals_missing_required.json` | professionals | `metro_region` never appears as a key in any row | `missing_required_columns` (error) |
| `professionals_ragged.json` | professionals | `company` (optional) present in some rows, absent in others; `metro_region` (required) present in some rows, absent in others | `ragged_rows` (warning, for `company`) **and** `ragged_rows` (error, for `metro_region`) -- two separate findings |
| `professionals_colliding_headers.json` | professionals | two rows carry both `metro_region` and `Metro Region`, which collapse to the same column after `normalize_header` | `colliding_headers` (error, since the collision is on a required column) |
| `professionals_blank_required_column.json` | professionals | `metro_region` key present in every row, but empty or whitespace-only every time | `required_column_entirely_blank` (error) |
| `professionals_null_sentinels.json` | professionals | `metro_region` filled only with `"NULL"`, `"nan"`, `"N/A"` -- source-specific null markers, not truly blank | **With** the proposed contract's declared `blank_sentinels` (`NULL`, `nan`, `N/A`): `required_column_entirely_blank`. **Without** any declared sentinels: *(none)* -- the same rows validate differently depending on the caller's declaration. `verify_fixtures.py` runs both variants explicitly. |
| `professionals_literal_null_value.json` | professionals | `name` is literally `"Null"`, and one row's `metro_region` is literally `"None"` -- real surnames/place-name text, not blanks | *(none)*, validated with `blank_sentinels=()` -- deliberately kept isolated from any contract that declares `"NULL"` as a sentinel; see `columns.yaml`'s `open_questions` for why running it *against* the ratified per-column sentinels would be a false positive |
| `professionals_duplicates.json` | professionals | plausible duplicate people (same person, spacing/abbreviation/title variants; e.g. "Anaya Ferreira" / "Anaya  Ferreira" / "A. Ferreira") | *(none)* -- every row is column-valid; `validate_columns` does not deduplicate. These rows exist to exercise a downstream entity-resolution step this repository does not yet have, not `validate_columns` itself. |
| `events_clean.json` | events | none -- 20 rows, every declared column present and consistent | *(none)* |
| `events_missing_required.json` | events | `Category` never appears as a key in any row | `missing_required_columns` (error) |
| `events_ragged.json` | events | `Host / Unit` (optional) present in some rows, absent in others; `Event / Program` (required) present in some rows, absent in others | `ragged_rows` (warning, for `Host / Unit`) **and** `ragged_rows` (error, for `Event / Program`) |
| `events_colliding_headers.json` | events | two rows carry both `Category` and `category`, which collapse to the same column | `colliding_headers` (error, since the collision is on a required column) |
| `empty_dataset.json` | either | zero rows | `empty_dataset` (error) -- shared fixture, validated once against each dataset's contract in `verify_fixtures.py` |

## The column contract, briefly

See `columns.yaml` for the ratified contract and its rationale. In short:

- **professionals**: required `name`, `metro_region`; optional `company`,
  `title`, `expertise_tags`, `initials`, `pronouns`. (`board_role` is no
  longer here — P9 Gate A closed it relationship-scoped; see below.)
- **events**: required `"Event / Program"`, `"Category"`; optional
  `"Recurrence (typical)"`, `"Host / Unit"`, `"Volunteer Roles (fit)"`,
  `"Primary Audience"`, `"Public URL"`, `"Point(s) of Contact (published)"`,
  `"Contact Email / Phone (published)"`.
- **blank_sentinels_by_column** (per-column, not global): `metro_region` and
  the events required columns declare `NULL`, `nan`, `N/A`; `name` explicitly
  declares none so a surname like `"Null"` is never blanked.

Column names were derived from two places already in this repository, not
invented:

1. `tests/unit/test_ingest.py` uses `full_name` in its illustrative examples
   (ratification chose `name` instead — see `columns.yaml` header) and supplies
   `metro_region` as the second required column and `pronouns` as optional.
2. `apps/web/legacy-frontend/src/lib/mockData.ts` (retired in Wave 3D; used
   here for historical shape and vocabulary only) supplied the remaining
   professionals fields and the entire `events` column set.

## Running the verification script

```bash
PYTHONPATH="python/smartmatch_domain" .venv/bin/python docs/pilot-data/verify_fixtures.py
```

It loads every fixture above, validates it against `columns.yaml`'s ratified
contract, and raises `AssertionError` if the finding codes don't match this
README's table. A clean run prints one `OK` line per fixture (some fixtures
get more than one line, for the sentinel-declared/not-declared contrast) and
exits `0`.

## Resolved gates (see `columns.yaml`'s `open_questions`)

Both questions this contract originally left open are now closed, 2 Sep 2026:

- **P9 Gate A — `board_role`.** Relationship-scoped, not intrinsic to a
  professional: it varies by `(professional, unit)`, multiple concurrent
  roles per person across different units are representable at once, and
  the pilot carries no effective-date columns (current-state only). See
  `docs/decisions/p9-gate-a-board-role-decision-draft.md`. The column is
  removed from `professionals.optional` and now lives on the
  `professional_unit_relationship` table.
- **P9 Gate B — the three events contact fields** (`"Public URL"`,
  `"Point(s) of Contact (published)"`, `"Contact Email / Phone
  (published)"`). All three: **collect**, human/import origin only. See
  `docs/decisions/p9-gate-b-contact-fields-worksheet.md` §8.
