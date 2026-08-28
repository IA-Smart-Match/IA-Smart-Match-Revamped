# SmartMatch pilot data

Synthetic test dataset for the SmartMatch pilot, built so `POST
/v1/units/{unit_id}/imports`'s live import path (rows travel already-parsed in
the request body; a live import writes an `import_batch` plus one quarantined
`review_item` per row) has something real to run against, and so the column
contract that import path is missing has a concrete proposal a human can
ratify or amend.

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
- **The column contract in `columns.yaml` is a proposal, not a decision.** See
  that file's header and its `open_questions` section. Nothing in
  `python/`, `services/`, or the frontend reads it.

## Why this exists

`smartmatch_domain.ingest.validate_columns` is real and already does real
work -- it catches empty datasets, ragged rows, and colliding headers -- but
`services/worker/smartmatch_worker/handlers.py` currently calls it with
`required=(), optional=()` because **no dataset anywhere in this repository
declares its required and optional columns**. The migration manifest's own
**F-28** finding records that architecture v1.1 Section 1.5 -- the spec
section that would define the real contract -- "has not been read into this
repository." `columns.yaml` fills that gap as a proposal; it does not resolve
F-28, since it cannot cite a section that isn't present, but it gives a human
something concrete to ratify or correct in its place.

## Layout

```
docs/pilot-data/
  README.md              this file
  columns.yaml            proposed required/optional columns + blank_sentinels, per dataset
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
| `professionals_literal_null_value.json` | professionals | `full_name` is literally `"Null"`, and one row's `metro_region` is literally `"None"` -- real surnames/place-name text, not blanks | *(none)*, validated with `blank_sentinels=()` -- deliberately kept isolated from any contract that declares `"NULL"` as a sentinel; see `columns.yaml`'s `open_questions` for why running it *against* the proposed contract's sentinels would be a false positive |
| `professionals_duplicates.json` | professionals | plausible duplicate people (same person, spacing/abbreviation/title variants; e.g. "Anaya Ferreira" / "Anaya  Ferreira" / "A. Ferreira") | *(none)* -- every row is column-valid; `validate_columns` does not deduplicate. These rows exist to exercise a downstream entity-resolution step this repository does not yet have, not `validate_columns` itself. |
| `events_clean.json` | events | none -- 20 rows, every declared column present and consistent | *(none)* |
| `events_missing_required.json` | events | `Category` never appears as a key in any row | `missing_required_columns` (error) |
| `events_ragged.json` | events | `Host / Unit` (optional) present in some rows, absent in others; `Event / Program` (required) present in some rows, absent in others | `ragged_rows` (warning, for `Host / Unit`) **and** `ragged_rows` (error, for `Event / Program`) |
| `events_colliding_headers.json` | events | two rows carry both `Category` and `category`, which collapse to the same column | `colliding_headers` (error, since the collision is on a required column) |
| `empty_dataset.json` | either | zero rows | `empty_dataset` (error) -- shared fixture, validated once against each dataset's contract in `verify_fixtures.py` |

## The column contract, briefly

See `columns.yaml` for the full proposal and its rationale. In short:

- **professionals**: required `full_name`, `metro_region`; optional `company`,
  `title`, `expertise_tags`, `board_role`, `initials`, `pronouns`.
- **events**: required `"Event / Program"`, `"Category"`; optional
  `"Recurrence (typical)"`, `"Host / Unit"`, `"Volunteer Roles (fit)"`,
  `"Primary Audience"`, `"Public URL"`, `"Point(s) of Contact (published)"`,
  `"Contact Email / Phone (published)"`.
- **blank_sentinels** (both datasets, proposed): `"NULL"`, `"nan"`, `"N/A"`.

Column names were derived from two places already in this repository, not
invented:

1. `tests/unit/test_ingest.py` already uses `full_name` and `metro_region` as
   its `REQUIRED` example for a `"professionals"` dataset, and `pronouns` as
   its example optional column -- the only place in the repo that names
   professionals columns before this drop.
2. `apps/web/legacy-frontend/src/lib/mockData.ts` (orphaned -- nothing
   imports it; used here for shape and vocabulary only) supplies the
   remaining professionals fields (`board_role`, `company`, `title`,
   `expertise_tags`, `initials`) and the entire `events` column set, taken
   verbatim from its `CppEvent` type including punctuation (`"Event /
   Program"`, `"Host / Unit"`, ...).

## Running the verification script

```bash
PYTHONPATH="python/smartmatch_domain" .venv/bin/python docs/pilot-data/verify_fixtures.py
```

It loads every fixture above, validates it against `columns.yaml`'s proposed
contract, and raises `AssertionError` if the finding codes don't match this
README's table. A clean run prints one `OK` line per fixture (some fixtures
get more than one line, for the sentinel-declared/not-declared contrast) and
exits `0`.

## Open questions for a human (see `columns.yaml`'s `open_questions` for the full text)

- **`full_name` vs. `name`.** The test fixture already in the repo says
  `full_name`; `mockData.ts`'s `Specialist` type says `name`. This proposal
  picked `full_name` because it's the spelling already codified in a
  committed test, not because it's obviously correct.
- **`blank_sentinels` are global to a `validate_columns()` call, not
  per-column.** Declaring `"NULL"` to catch a blank `metro_region` also
  blanks a professional literally named `"Null"` in *every* column on their
  row, not just `metro_region`. `professionals_literal_null_value.json`
  demonstrates the value this would clobber; it's kept out of any run that
  declares `"NULL"` as a sentinel for exactly that reason.
- **Whether `board_role` belongs on a professional at all**, versus being a
  property of their relationship to a specific unit/chapter, is a modeling
  question `mockData.ts` doesn't answer and this proposal doesn't resolve.
- **Two events fields** (`"Public URL"`, and the two `"(published)"` contact
  fields) are declared optional because `mockData.ts`'s `CppEvent` type has
  them, but no fixture here exercises them -- worth deciding whether the
  pilot actually collects them.
