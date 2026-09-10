/**
 * The `/` route's decision: public landing page, or straight into a portal.
 *
 * `LoginPage` deliberately sends a freshly signed-in visitor to `/` rather
 * than guessing a portal from their email (see that file's header) — the
 * portal is `GET /v1/me/portals`' answer, not the browser's. Before this
 * component existed, `/` always rendered {@link LandingPage} regardless of
 * session state, so a successful sign-in landed back on the marketing page
 * instead of the portal the server had just granted. This is the piece that
 * closes that gap: an anonymous or still-loading visitor sees the landing
 * page exactly as before, and a signed-in one is forwarded to their portal's
 * server-reported `home_path`.
 *
 * Route guarding is UX only here, as everywhere else in this app: a visitor
 * who lands on the wrong page reaches nothing without `/v1` authorizing the
 * request behind it.
 */
import { Navigate } from "react-router";

import { useSession } from "../hooks/useSession";
import { usePortalAccess, useRetryPortalAccess } from "../hooks/usePortalAccess";
import { LandingPage } from "./LandingPage";

function CheckingAccessNotice() {
  return (
    <div
      className="flex min-h-screen items-center justify-center bg-background"
      role="status"
      aria-live="polite"
    >
      <p className="text-sm text-muted-foreground">Checking which portal to open…</p>
    </div>
  );
}

function PortalUnavailableNotice({ onRetry }: { onRetry: () => void }) {
  return (
    <div className="flex min-h-screen items-center justify-center bg-background px-6">
      <div className="max-w-md space-y-4 text-center">
        <h1 className="text-xl font-semibold text-foreground">Can’t confirm your portal</h1>
        <p className="text-sm leading-6 text-muted-foreground">
          The API did not answer GET /v1/me/portals, so there is no way to tell which portal to
          open. Nothing is shown until it does.
        </p>
        <button
          type="button"
          onClick={onRetry}
          className="inline-flex items-center rounded-xl border border-border bg-card px-4 py-2 text-sm font-semibold text-foreground shadow-sm transition hover:bg-muted"
        >
          Try again
        </button>
      </div>
    </div>
  );
}

export function Home() {
  const session = useSession();
  const portalAccess = usePortalAccess();
  const retryPortalAccess = useRetryPortalAccess();

  // Not signed in (or `/v1/me` is still resolving): this is the first page an
  // anonymous visitor needs, unchanged from before this component existed.
  if (session.status !== "signed-in") {
    return <LandingPage />;
  }

  if (portalAccess.status === "loading") {
    return <CheckingAccessNotice />;
  }

  if (portalAccess.status === "unavailable") {
    // `signed-out` here means the credential lapsed between `/v1/me` and
    // `/v1/me/portals` resolving — `useSession()` will pick that up on its
    // own next check. Either way there is nothing this page can decide yet,
    // so offer the same retry rather than guessing.
    return <PortalUnavailableNotice onRetry={retryPortalAccess} />;
  }

  const { mapping } = portalAccess;
  const target =
    mapping.portals.find((entry) => entry.portal === mapping.default_portal) ??
    mapping.portals[0];

  // A verified account the server granted no portal to. Not an error — an
  // administrator has not assigned this account a role yet — so this is
  // informational, not a dead end.
  if (!target) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-background px-6">
        <div className="max-w-md space-y-3 text-center">
          <h1 className="text-xl font-semibold text-foreground">No portal assigned yet</h1>
          <p className="text-sm leading-6 text-muted-foreground">
            You're signed in as {session.me.email}, but your account holds no active membership
            that opens a portal. Ask your program administrator to grant one.
          </p>
        </div>
      </div>
    );
  }

  return <Navigate to={target.home_path} replace />;
}
