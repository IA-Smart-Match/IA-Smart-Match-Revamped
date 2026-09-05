/**
 * Which product this build is, and which named capabilities it offers.
 *
 * This is the frontend half of the single CBA product-scope capability policy.
 * The whole policy — the vocabulary, the decisions, and the reasoning behind
 * each one — lives in `python/smartmatch_domain/smartmatch_domain/product_scope.py`.
 * This file is a **mirror of that module**, not a second opinion about scope.
 *
 * `tests/unit/test_cba_scope_policy.py` parses the `CBA_CAPABILITY_POLICY`
 * literal below and asserts it matches the Python policy capability for
 * capability. Editing one without the other fails that test, which is what
 * keeps "one policy, read in two places" true rather than aspirational.
 *
 * ## A UI gate is not authorization
 *
 * Hiding a link removes a *claim*, not an access path. Anyone can type a URL,
 * open a devtools console, or call the API directly, and nothing in this file
 * stops them — nor is it meant to. Authorization is enforced server-side, per
 * route, deny-by-default and tenant-scoped (`smartmatch_authz`). What this
 * policy does is stop the product from *advertising* something it does not do
 * this phase: navigation to a scraping console the customer put out of scope
 * is a false claim about the product long before it is a security question.
 *
 * Never derive a capability from a role label, and never treat a `false` here
 * as a substitute for a server-side check.
 *
 * ## Product scope is not deployment edition
 *
 * The API's `edition` (dev / staging / classroom / production) decides which
 * deployment this is and whether it may hold a provider credential. Product
 * scope decides which product this is. They are two values on purpose; neither
 * derives from the other.
 *
 * Sources: `docs/product/cba-smart-match-customer-requirements.md` §§1, 4, 20,
 * 22; `docs/plans/open-questions/cba-phase-deferred.md`;
 * `docs/product/cba-capability-policy.md`.
 */

/**
 * The capability decisions for the CBA product scope.
 *
 * Mirrors `ProductScope.CBA` in
 * `python/smartmatch_domain/smartmatch_domain/product_scope.py`. Every
 * capability carries an explicit boolean: a missing entry is not "disabled by
 * default", it is an unclassified capability, and the parity test treats it as
 * a failure rather than a safe omission.
 */
export const CBA_CAPABILITY_POLICY = {
  /** One standard, backend-derived login. No portal chooser (customer §3). */
  authenticated_login: true,
  /** Reading the event catalog already in the system (customer §22). */
  event_reads: true,
  /** Match runs over records already entered in the system (customer §1). */
  match_runs: true,
  /** The red/yellow/green discovery feed and its funnel metrics (customer §17). */
  discovery_metrics: true,
  /** Sending an approved draft to a contact whose consent is on record. */
  consented_outreach: true,
  /** Server-backed rewards/points. Customer §4: "Rewards / points — Keep". */
  rewards_ledger: true,
  /** An operator importing records the institution already holds (customer §20). */
  operator_record_import: true,
  /** Scraping, LinkedIn, external speaker/event discovery. Out of scope (§20). */
  external_speaker_acquisition: false,
  /** Contacting someone who never consented. Out of scope (§20). */
  cold_unknown_contact_outreach: false,
  /** Chapter membership and dues as a product concept. Removed (§4, §20). */
  chapter_membership_dues: false,
  /** Presenting `member_inquiry` as a CBA funnel outcome. No CBA equivalent. */
  member_inquiry_narrative: false,
} as const;

/** A named product capability. Derived from the policy so the two cannot drift. */
export type Capability = keyof typeof CBA_CAPABILITY_POLICY;

/** Every capability name, for exhaustive rendering and tests. */
export const CAPABILITIES = Object.keys(CBA_CAPABILITY_POLICY) as readonly Capability[];

/**
 * Thrown for an unrecognised capability name.
 *
 * Deliberately not "return false". An unknown name is a typo or a stale
 * reference, and answering it with "disabled" would let the mistake read as a
 * correctly closed gate for as long as nobody looked. This mirrors
 * `CapabilityScopeError` in the Python policy.
 */
export class CapabilityScopeError extends Error {
  constructor(name: string) {
    super(`unknown capability: ${name}`);
    this.name = "CapabilityScopeError";
  }
}

/**
 * Whether this product offers `capability`.
 *
 * Fails closed *loudly*: an unknown name throws rather than reading as
 * disabled. Remember that a `false` here hides a claim; it does not protect a
 * route. See the module docstring.
 *
 * @throws {CapabilityScopeError} if `capability` is not a known capability.
 */
export function isCapabilityEnabled(capability: Capability): boolean {
  // `Object.prototype.hasOwnProperty.call`, not `Object.hasOwn`: this project
  // targets ES2020 (`tsconfig.json`), where `Object.hasOwn` does not exist.
  if (!Object.prototype.hasOwnProperty.call(CBA_CAPABILITY_POLICY, capability)) {
    throw new CapabilityScopeError(String(capability));
  }
  return CBA_CAPABILITY_POLICY[capability];
}

/** Every capability this product offers, in declaration order. */
export function enabledCapabilities(): readonly Capability[] {
  return CAPABILITIES.filter((capability) => CBA_CAPABILITY_POLICY[capability]);
}
