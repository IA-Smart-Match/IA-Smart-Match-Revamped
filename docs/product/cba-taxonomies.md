# CBA classification taxonomies — industry sector and career role category

**Status:** Released
**Date:** 5 September 2026
**Source:** `docs/product/cba-smart-match-customer-requirements.md` §§7–8
**Implements:** `docs/plans/2026-09-05-cba-pivot-waves.md` — CBA-TAXONOMY
**Code:** `python/smartmatch_domain/smartmatch_domain/naics_sectors.py`,
`python/smartmatch_domain/smartmatch_domain/cba_role_categories.py`

## What this is

Two closed, versioned classification vocabularies, transcribed from the
customer's own tables:

| Taxonomy | Count | Version token | Module |
|---|---|---|---|
| NAICS industry sector groups | 20 | `cba-naics-2026-09-04` | `naics_sectors` |
| CBA career role categories | 10 | `cba-roles-2026-09-04` | `cba_role_categories` |

Both are closed lists. Growing either one is a new version token and a
reviewed code diff, never an edit under the existing token.

## These are not the ADR-0012 event tag vocabulary

`ADR-0012` releases a third closed vocabulary
(`smartmatch_domain.event_vocabulary`, version `g3-2026-08-29`) describing
**events**: what kind of event it is (`hackathon`, `career panel`) and what
function a speaker performs at one (`panelist`, `judge`, `keynote`).

The taxonomies here describe **a speaker's professional identity**: the
industry they work in and the career discipline they work within. The word
"role" appears in both and means unrelated things — an ADR-0012 `role` term is
an event function, a CBA role category is a career discipline.

The three stay separate, as the wave plan requires. Separation is held by
construction rather than by convention:

- three distinct version tokens, so a stored value names which vocabulary
  evaluated it;
- three structurally unrelated resolution types, so a career classification
  cannot reach `matchable_tags()` and an event tag cannot be written into a
  career-role column;
- no import between the modules in either direction.

`tests/unit/test_event_vocabulary.py` holds the tests that prove all three.

## The domain module is the only copy

Neither list may be duplicated in a frontend enum, a migration literal, a
matcher constant, or a fixture. The frontend reads these values from the API;
persistence stores the **code** string and leaves the meaning here. A second
copy is where a twenty-first sector or an eleventh role category appears in
one place and not the other.

Both live as Python modules rather than data files because
`smartmatch_domain`'s import-linter contract forbids `os` and `pathlib` — a
taxonomy loaded from disk cannot exist in this layer. The consequence is
intended: every version is a reviewed diff.

## Unknown values: refuse, or quarantine

Each taxonomy exposes two entry points with deliberately different behaviour.

**Refuse** — `sector_for_code()`, `role_category_for_code()` raise
`UnknownNaicsSector` / `UnknownCbaRoleCategory` (both `LookupError`). The
caller holds a code a Speaker Connector already approved and a column already
stores; a code outside the table is a caller bug, and a nearest match would
hide it. Matching is exact: `" 11"`, `"3133"` and `"Finance"` are not stored
codes.

**Quarantine** — `resolve_sector()`, `resolve_role_category()` accept a code
or a display name in any casing and with any whitespace, and return either a
`Classified…` value or a `Quarantined…` value carrying the reviewer's original
text unchanged. The caller holds a spreadsheet cell or an inferred guess, and
ADR-0012's reasoning transfers directly: "Dropping loses the signal that the
vocabulary is wrong. The unmapped values are the input to the next vocabulary
revision, and discarding them is how a closed vocabulary ossifies into a wrong
one."

A blank value is refused by both arms rather than quarantined. An empty cell is
missing data, not a value awaiting a human decision, and filing it into a
review queue only gives a person something to empty.

## Deferred here, on purpose

- **Aliases and inference.** Customer §§7–8 allow a speaker's sector to be
  inferred from company name or title and a role from their title. The
  inference rules are learned from real pilot data and are a later versioned
  decision, so this release adds none of them: `Tech` does not become
  `Information`, `Banking` does not become `Finance and Insurance`, `HR` does
  not become `Human Resources`. All quarantine, visibly.
  A punctuation difference does fold away (`Management  &  Strategy` resolves);
  substituting a word for a symbol does not (`Management and Strategy`
  quarantines), because that is an alias and not a spelling.
- **Cardinality.** §7 and §8 give the speaker side one primary value and the
  Speaker Request side many. Nothing here blocks either, and nothing here
  enforces either — the constraint is `CBA-DATA-SCHEMA`'s column work.
- **Persistence, API, UI, and matching arithmetic** are separate tracks.

## Codes

The **sector codes and names are the customer's**, verbatim, including the
hyphenated ranges `31-33`, `44-45`, `48-49` and the parenthetical in
`Other Services (except Public Administration)`.

The **role-category display names are the customer's**, verbatim, including
`Management & Strategy` and `Entrepreneurship / Founder`. §8 supplies no
codes, so this taxonomy assigns each entry a lowercase underscored storage key
(`management_strategy`, `entrepreneurship_founder`, …) that survives a display
rename. Those codes are fixed by `tests/unit/test_cba_role_categories.py` so a
later revision cannot renumber stored rows unnoticed.
