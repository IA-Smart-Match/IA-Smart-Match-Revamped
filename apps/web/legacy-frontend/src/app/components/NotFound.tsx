/**
 * What the app renders for an address it does not have, and for a route that
 * threw on the way in.
 *
 * Before this existed, react-router's built-in error boundary handled both:
 * an unknown path rendered the framework's stock "Unexpected Application
 * Error!" screen with a stack trace, and so did a lazy chunk that failed to
 * download. Two different facts — "there is no such page" and "the page is
 * here but could not be loaded" — arrived looking identical, and neither
 * offered a way back.
 *
 * ## The two states, kept apart
 *
 * `useRouteError()` is the discriminator, and it is deliberately not flattened
 * into one apologetic paragraph:
 *
 *  - **No error object** (the `path: "*"` catch-all) — the address does not
 *    exist. Said plainly, with the address quoted back so the reader can see a
 *    typo or a stale bookmark for what it is.
 *  - **A 404 `ErrorResponse`** — same statement, reached through the boundary.
 *  - **Anything else** — the route exists and something went wrong reaching
 *    it. That is an outage, not a statement about the address, and saying "no
 *    such page" here would send the reader off to fix a URL that was correct.
 *    Reloading is the honest offer, because a failed chunk fetch usually
 *    succeeds on the second try.
 *
 * ## Why the links are the server's answer and not a guess
 *
 * The way out is whichever portals `GET /v1/me/portals` granted this account,
 * read from the provider `App.tsx` mounts above the router. This page never
 * derives a home from a role, never assumes `/coordinator-portal`, and never
 * links somewhere the reader would only be refused — `lib/principal.ts`'s
 * `portalGrant()` explains why the browser must not re-derive that mapping.
 *
 * While the mapping is in flight, or when it could not be fetched, no portal
 * links are drawn at all and only the public home remains. An unanswered
 * question is not a denial and it is not a grant either; inventing a
 * destination to fill the space is the failure this whole file exists to
 * avoid.
 *
 * No error text from the server, no stack trace, and no status code is put on
 * screen: `DESIGN.md`'s error rule is that a reader is told how to recover,
 * not shown the internals. The detail still reaches the console for whoever is
 * debugging.
 */
import { Link, isRouteErrorResponse, useLocation, useRouteError } from "react-router";

import { usePortalAccess } from "../hooks/usePortalAccess";

/** The portal home links the server granted, or nothing when it has not answered. */
function PortalHomeLinks() {
  const access = usePortalAccess();

  if (access.status !== "ready" || access.mapping.portals.length === 0) {
    return null;
  }

  return (
    <div className="space-y-2">
      <p className="text-sm font-medium text-foreground">Go to a portal you can open:</p>
      <div className="flex flex-wrap justify-center gap-2">
        {access.mapping.portals.map((portal) => (
          <Link
            key={portal.portal}
            to={portal.home_path}
            className="inline-flex min-h-[40px] items-center rounded-xl border border-border bg-card px-4 py-2 text-sm font-semibold text-foreground shadow-sm transition-colors hover:bg-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
          >
            {portal.display_name}
          </Link>
        ))}
      </div>
    </div>
  );
}

export function NotFound() {
  const error = useRouteError();
  const location = useLocation();

  // A missing address and a broken route are different facts and get
  // different sentences. `undefined` is the catch-all route, which
  // react-router renders as an element rather than through the boundary.
  const isMissingAddress =
    error === undefined || error === null || (isRouteErrorResponse(error) && error.status === 404);

  if (!isMissingAddress) {
    // Kept out of the visible copy, kept available to whoever is debugging.
    console.error("Route failed to render", error);
  }

  return (
    <main className="flex min-h-screen items-center justify-center bg-background px-6 py-16">
      <div className="max-w-md space-y-6 text-center">
        {isMissingAddress ? (
          <>
            <h1 className="text-xl font-semibold text-foreground">This page doesn’t exist</h1>
            <p className="text-sm leading-6 text-muted-foreground">
              Smart Match has no page at{" "}
              <code className="break-all rounded bg-muted px-1.5 py-0.5 text-xs text-foreground">
                {location.pathname}
              </code>
              . It may have been renamed, or the link may be out of date.
            </p>
          </>
        ) : (
          <>
            <h1 className="text-xl font-semibold text-foreground">This page didn’t load</h1>
            <p className="text-sm leading-6 text-muted-foreground">
              The page exists, but something went wrong opening it. Nothing you did caused this,
              and nothing was saved or changed. Reloading usually clears it.
            </p>
            <button
              type="button"
              onClick={() => window.location.reload()}
              className="inline-flex min-h-[40px] items-center rounded-xl border border-border bg-card px-4 py-2 text-sm font-semibold text-foreground shadow-sm transition-colors hover:bg-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
            >
              Reload the page
            </button>
          </>
        )}

        <PortalHomeLinks />

        <p className="text-sm">
          <Link
            to="/"
            className="font-medium text-primary underline underline-offset-4 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
          >
            Back to the Smart Match home page
          </Link>
        </p>
      </div>
    </main>
  );
}
