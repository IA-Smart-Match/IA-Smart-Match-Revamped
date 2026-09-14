/**
 * Every URL the retired admin shell owned, and where it goes now.
 *
 * ## Why this is a table and not ten `<Navigate>` elements
 *
 * The Connector Dashboard replaces a second, parallel shell: `Layout.tsx` held
 * `/dashboard`, `/opportunities`, `/events`, `/volunteers`, `/ai-matching`,
 * `/pipeline`, `/calendar` and `/outreach`, and two volunteer-portal pages were
 * folded into their siblings at the same time. Those addresses are in people's
 * bookmarks, in the pilot walkthrough, in the e2e test, and in links pasted
 * into chat. Deleting the routes would turn every one of them into a 404 for a
 * page whose *successor exists* — which is the one failure mode this
 * consolidation was not allowed to introduce.
 *
 * Keeping the mapping in a single exported constant, rather than scattering
 * `<Navigate>` calls through `routes.tsx`, is what makes that promise
 * checkable. `tests/legacyRedirects.test.ts` asserts the table is complete
 * against the recorded inventory of retired paths and that every destination
 * is a path this router actually serves. A redirect that is only a JSX element
 * buried in a route tree can be dropped in a merge and nothing notices until a
 * user does.
 *
 * ## What a destination means here
 *
 * Each `to` is the surface that now does the retired page's job — not the
 * nearest-looking page. `/pipeline` and `/opportunities` both land on speaker
 * requests because both were views of the same filed requests. `/calendar` and
 * `/events` both land on the merged events page. `/volunteers` lands on the
 * speaker roster, which is what that page listed once the legacy `/api/data`
 * feeds behind it were retired.
 *
 * These are `replace` navigations in `routes.tsx`: the retired address should
 * not sit in the history stack, because pressing Back onto it would only
 * redirect forward again and trap the reader.
 */

/** One retired address and its successor. Both are absolute, router-relative paths. */
export interface LegacyRedirect {
  /** The path that used to work. Must stay exactly as it was spelled. */
  readonly from: string;
  /** The surface that now does its job. */
  readonly to: string;
  /**
   * Query parameters that were part of the old address's contract, forwarded
   * verbatim onto the destination.
   *
   * `/ai-matching?run={id}` was the shortlist's whole address — the parameter
   * is not decoration, it names the run. Dropping it at the redirect would
   * land the reader on the submission form with the shortlist orphaned, so
   * `run` is listed here and `routes.tsx` carries it through. Everything not
   * named is still dropped: forwarding every parameter wholesale would hand
   * the successor inputs it never agreed to read.
   */
  readonly forwardParams?: readonly string[];
}

/**
 * The complete retirement table.
 *
 * Ordered by the shell they came from — the eight admin-shell pages first,
 * then the two volunteer-portal pages folded into their siblings — so that a
 * reader can check it against the shells rather than against an alphabet.
 */
export const LEGACY_ROUTE_REDIRECTS: readonly LegacyRedirect[] = [
  // The retired admin shell (`components/Layout.tsx`, deleted in this change).
  { from: "/dashboard", to: "/coordinator-portal" },
  { from: "/opportunities", to: "/coordinator-portal/speaker-requests" },
  { from: "/events", to: "/coordinator-portal/events" },
  { from: "/ai-matching", to: "/coordinator-portal/match-runs", forwardParams: ["run"] },
  { from: "/pipeline", to: "/coordinator-portal/speaker-requests" },
  { from: "/calendar", to: "/coordinator-portal/events" },
  { from: "/volunteers", to: "/coordinator-portal/speaker-contacts" },
  { from: "/outreach", to: "/coordinator-portal/outreach" },
  // Volunteer-portal pages folded into a sibling rather than retired outright.
  { from: "/volunteer-portal/assignments", to: "/volunteer-portal" },
  { from: "/volunteer-portal/confirmed-speaker", to: "/volunteer-portal/my-requests" },
] as const;
