/**
 * What a server-assigned role is *called* — the frontend half of one map.
 *
 * The whole map — the personas, the labels, and the reasoning behind each one
 * — lives in `python/smartmatch_domain/smartmatch_domain/role_presentation.py`.
 * This file is a **mirror of that module**, not a second opinion about who
 * anyone is. `tests/unit/test_role_presentation.py` parses the
 * `ROLE_PRESENTATION` literal below and asserts it matches the Python map role
 * for role, which is what keeps "one map, read in two places" true rather than
 * aspirational.
 *
 * ## A label is not a power, and never a portal
 *
 * Nothing here decides access. Every `/v1` request is authorized server-side,
 * per route, deny-by-default and tenant-scoped (`smartmatch_authz`), against
 * the *stored* `membership.role` — never against a label. Renaming a persona
 * in this file changes what a screen says and nothing else.
 *
 * It also decides no routing. Which portal an account may open is
 * `GET /v1/me/portals`'s answer alone (`lib/principal.ts`'s `portalGrant()`
 * explains why the browser must not re-derive it), and each portal's own name
 * arrives on that response as `display_name`. Use *that* for a portal header;
 * use this file for naming a **person's role** where only `GET /v1/me`'s
 * membership rows are in hand.
 *
 * ## Stored strings are unchanged
 *
 * The keys below are the stored role strings: `student`, `coordinator`,
 * `volunteer`, `admin`. The CBA pivot renamed nothing in the database — a
 * permanent rename is a separate, deferred decision — so this is a translation
 * over stable storage, which is how a screen says "Speaker Connector" while
 * the row still says `coordinator`.
 *
 * Sources: `docs/product/cba-smart-match-customer-requirements.md` §§2–4;
 * `docs/product/cba-role-presentation.md`.
 */

/**
 * The CBA personas, as customer §2 names them.
 *
 * `speaker` is deliberately present and deliberately unreachable from any
 * stored role: speakers are contact records, not login accounts. Naming the
 * persona without inventing a role for it keeps the vocabulary honest.
 */
export type Persona = "student" | "event_host" | "speaker_connector" | "speaker";

/**
 * Every stored `membership.role`, and everything visible it decides.
 *
 * Mirrors `_PRESENTATION` in `role_presentation.py`. Exhaustive over the roles
 * the pilot seeds: a role absent from this table is *unmapped*, and unmapped
 * is reported as such rather than rounded to the nearest persona.
 */
export const ROLE_PRESENTATION = {
  student: {
    persona: "student",
    roleLabel: "Student",
    portalDisplayName: "Student Portal",
  },
  /** Customer §4: Volunteer → Event Host, for the event-requesting role. */
  volunteer: {
    persona: "event_host",
    roleLabel: "Event Host",
    portalDisplayName: "Event Host Portal",
  },
  coordinator: {
    persona: "speaker_connector",
    roleLabel: "Speaker Connector",
    portalDisplayName: "Speaker Connector Portal",
  },
  /**
   * Same persona as `coordinator`, distinguishable label. The two stored roles
   * keep genuinely different reach in `smartmatch_authz`; the qualifier lets a
   * reader see which row they hold without implying a power the label cannot
   * grant. See `docs/product/cba-role-presentation.md`.
   */
  admin: {
    persona: "speaker_connector",
    roleLabel: "Speaker Connector (administrator)",
    portalDisplayName: "CBA Administration",
  },
} as const;

/** A stored `membership.role` this map names. Derived, so the two cannot drift. */
export type KnownRole = keyof typeof ROLE_PRESENTATION;

/** Every stored role the map names, in declaration order. */
export const KNOWN_ROLES = Object.keys(ROLE_PRESENTATION) as readonly KnownRole[];

function presentation(role: string) {
  // `Object.prototype.hasOwnProperty.call`, not `Object.hasOwn`: this project
  // targets ES2020 (`tsconfig.json`), where `Object.hasOwn` does not exist.
  if (!Object.prototype.hasOwnProperty.call(ROLE_PRESENTATION, role)) {
    return null;
  }
  return ROLE_PRESENTATION[role as KnownRole];
}

/**
 * The persona a stored role presents as, or `null` when it maps to none.
 *
 * Matched exactly — `"Student"` and `"coordinator "` are not the stored
 * strings and answer `null`, because normalising them silently would make a
 * malformed row read as a correct one.
 */
export function personaForRole(role: string): Persona | null {
  return presentation(role)?.persona ?? null;
}

/**
 * What to call the holder of a stored role, or `null` for an unmapped one.
 *
 * `null` is a real answer and callers must render it as one. Substituting a
 * default persona here would be the browser inventing an identity the server
 * never assigned, which is the archived pattern `lib/principal.ts` exists to
 * keep out.
 */
export function visibleRoleLabel(role: string): string | null {
  return presentation(role)?.roleLabel ?? null;
}

/**
 * What to call the shell a stored role opens, or `null` when it opens none.
 *
 * Prefer the `display_name` on a `GET /v1/me/portals` descriptor when one is
 * in hand: that is the server's own answer for the portal actually granted.
 * This exists for the case where only a role string is available.
 */
export function portalDisplayNameForRole(role: string): string | null {
  return presentation(role)?.portalDisplayName ?? null;
}
