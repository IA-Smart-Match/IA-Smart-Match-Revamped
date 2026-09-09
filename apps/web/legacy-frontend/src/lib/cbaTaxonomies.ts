/**
 * The two closed CBA vocabularies a Speaker Request form offers.
 *
 * The whole taxonomy — the codes, the names, the resolution rules and the
 * versioning — lives in
 * `python/smartmatch_domain/smartmatch_domain/naics_sectors.py` and
 * `python/smartmatch_domain/smartmatch_domain/cba_role_categories.py`. This file
 * is a **mirror of those modules**, not a second opinion about what an industry
 * is, and it exists for the same reason `productScope.ts` and `roleLabels.ts`
 * exist: a form has to render the options before any request is made, and there
 * is no route that hands them over.
 *
 * `tests/unit/test_frontend_taxonomy_mirror.py` parses the two literals below
 * and asserts they match the Python tables code for code, name for name, in
 * order, versions included. That is the arrangement migration `0024` uses for
 * its transcribed `CHECK` lists, and for the reason it states: a transcription
 * is acceptable exactly when the divergence it risks is caught behaviourally
 * rather than left to discipline.
 *
 * ## Rendering an option is not filing a request
 *
 * Nothing here validates anything. `POST /v1/units/{unit_id}/speaker-requests`
 * resolves every submitted code through the released taxonomy server-side and
 * refuses an unreleased one with a 400, so a stale copy of this file produces a
 * refusal a person can read — never a stored classification the vocabulary does
 * not contain. Do not add a code here to "make the form accept it": growing a
 * closed vocabulary is a reviewed change to the Python module, and this file
 * follows it rather than leading it.
 *
 * Sources: `docs/product/cba-smart-match-customer-requirements.md` §§7-8;
 * `docs/product/cba-taxonomies.md`.
 */

/** One option in a closed vocabulary: the stored key, and the name a person reads. */
export interface TaxonomyOption {
  /** What a row holds and what the matcher compares. */
  code: string;
  /** Customer §7's or §8's own wording. */
  name: string;
}

/**
 * The released NAICS taxonomy this mirror was transcribed from.
 *
 * Sent nowhere and compared to nothing at runtime — the server stamps the
 * version it actually resolved against onto every stored classification and
 * reports it back on the response. This constant is here so the parity test can
 * fail when the taxonomy is revised without this file being revisited.
 */
export const CBA_NAICS_TAXONOMY_VERSION = "cba-naics-2026-09-04";

/** The released CBA career-role taxonomy this mirror was transcribed from. */
export const CBA_ROLE_TAXONOMY_VERSION = "cba-roles-2026-09-04";

/**
 * Customer §7's twenty NAICS sector groups, in the customer's own order.
 *
 * A Speaker Request may target more than one (§7: "Do not restrict an event
 * request to one"), which is why the form renders these as a multi-select and
 * the request body carries an array.
 */
export const CBA_INDUSTRY_SECTORS: readonly TaxonomyOption[] = [
  { code: "11", name: "Agriculture, Forestry, Fishing and Hunting" },
  { code: "21", name: "Mining, Quarrying, and Oil and Gas Extraction" },
  { code: "22", name: "Utilities" },
  { code: "23", name: "Construction" },
  { code: "31-33", name: "Manufacturing" },
  { code: "42", name: "Wholesale Trade" },
  { code: "44-45", name: "Retail Trade" },
  { code: "48-49", name: "Transportation and Warehousing" },
  { code: "51", name: "Information" },
  { code: "52", name: "Finance and Insurance" },
  { code: "53", name: "Real Estate and Rental and Leasing" },
  { code: "54", name: "Professional, Scientific, and Technical Services" },
  { code: "55", name: "Management of Companies and Enterprises" },
  {
    code: "56",
    name: "Administrative and Support and Waste Management and Remediation Services",
  },
  { code: "61", name: "Educational Services" },
  { code: "62", name: "Health Care and Social Assistance" },
  { code: "71", name: "Arts, Entertainment, and Recreation" },
  { code: "72", name: "Accommodation and Food Services" },
  { code: "81", name: "Other Services (except Public Administration)" },
  { code: "92", name: "Public Administration" },
] as const;

/**
 * Customer §8's ten CBA career role categories, in the customer's own order.
 *
 * Multi-select for the same reason as the sectors above (§8: "Do not restrict
 * an event request to one"). The codes are storage keys, not the display names:
 * `Management & Strategy` is what a person reads and `management_strategy` is
 * what a row holds, so a display rename does not renumber stored rows.
 */
export const CBA_ROLE_CATEGORIES: readonly TaxonomyOption[] = [
  { code: "accounting", name: "Accounting" },
  { code: "finance", name: "Finance" },
  { code: "marketing", name: "Marketing" },
  { code: "management_strategy", name: "Management & Strategy" },
  { code: "human_resources", name: "Human Resources" },
  { code: "operations_supply_chain", name: "Operations & Supply Chain" },
  { code: "information_systems_analytics", name: "Information Systems & Analytics" },
  { code: "international_business", name: "International Business" },
  { code: "entrepreneurship_founder", name: "Entrepreneurship / Founder" },
  { code: "sales_business_development", name: "Sales & Business Development" },
] as const;
