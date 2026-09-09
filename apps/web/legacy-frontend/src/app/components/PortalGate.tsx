/**
 * What a portal shell renders when the server has not granted it that portal.
 *
 * `SessionGate` answers "is anybody signed in". This answers the next
 * question — "did the server grant *this* portal to the person who is" — from
 * `GET /v1/me/portals` and never from a role the browser read for itself.
 *
 * The states it handles, and why each says what it says:
 *
 *  - `loading` — the mapping request is in flight. A neutral placeholder, for
 *    `SessionGate`'s reason: an unanswered question is not a denial.
 *  - `unavailable` / `unreachable` — the API could not be asked. That is an
 *    outage, not a statement about this account, so it offers to ask again.
 *    Rendering "you do not have access" here would be the browser inventing a
 *    denial the server never made, which is the mirror image of inventing an
 *    access it never granted.
 *  - granted-nothing — the server *did* answer, and the answer is that no
 *    active, role-bearing membership opens this portal. Stated plainly,
 *    naming the roles the account actually holds so the reader can see why,
 *    and offering the portals it *was* granted rather than a dead end.
 *
 * Like `SessionGate`, this renders **instead of** the shell rather than around
 * it, so no portal chrome is drawn for a portal the server did not list.
 * Route guarding is UX only — `/v1` authorization remains the authority, and
 * a shell drawn in error would be one whose every request is refused.
 */
import type { ReactNode } from "react";
import { Link } from "react-router";

import type { MeResponse } from "@/lib/api";
import { portalGrant, principalRoleLabel, type PortalKind } from "@/lib/principal";

import { useRetryPortalAccess, type PortalAccessState } from "../hooks/usePortalAccess";

function Notice({
  title,
  body,
  children,
}: {
  title: string;
  body: string;
  children?: ReactNode;
}) {
  return (
    <div className="flex min-h-screen items-center justify-center bg-background px-6">
      <div className="max-w-md space-y-4 text-center">
        <h1 className="text-xl font-semibold text-foreground">{title}</h1>
        <p className="text-sm leading-6 text-muted-foreground">{body}</p>
        {children}
      </div>
    </div>
  );
}

export function PortalGate({ state, me }: { state: PortalAccessState; me: MeResponse }) {
  const retry = useRetryPortalAccess();

  if (state.status === "loading") {
    return (
      <div
        className="flex min-h-screen items-center justify-center bg-background"
        role="status"
        aria-live="polite"
      >
        <p className="text-sm text-muted-foreground">Checking which portals you can open…</p>
      </div>
    );
  }

  if (state.status === "unavailable") {
    if (state.problem === "signed-out") {
      // The shell's own `SessionGate` handles this and runs first, so reaching
      // here means the credential lapsed between the two calls. Say that,
      // rather than claiming the account lacks a portal it may well hold.
      return (
        <Notice
          title="Your session ended"
          body="The server no longer recognises this session, so it cannot say which portals you can open. Sign in again."
        >
          <Link
            to="/login"
            className="inline-flex items-center rounded-xl border border-border bg-card px-4 py-2 text-sm font-semibold text-foreground shadow-sm transition hover:bg-muted"
          >
            Go to sign-in
          </Link>
        </Notice>
      );
    }

    return (
      <Notice
        title="Can’t confirm your portal access"
        body="The API did not answer GET /v1/me/portals, so there is no way to tell which portals you were granted. Nothing is shown until it does."
      >
        <button
          type="button"
          onClick={retry}
          className="inline-flex items-center rounded-xl border border-border bg-card px-4 py-2 text-sm font-semibold text-foreground shadow-sm transition hover:bg-muted"
        >
          Try again
        </button>
      </Notice>
    );
  }

  const granted = state.mapping.portals;

  return (
    <Notice
      title="This portal isn’t assigned to your account"
      body={`The server assigned you: ${principalRoleLabel(me)}. None of those roles opens this portal, and roles are assigned by an administrator — they are not chosen here.`}
    >
      {granted.length > 0 ? (
        <div className="space-y-2">
          <p className="text-sm font-medium text-foreground">Portals you can open:</p>
          <div className="flex flex-wrap justify-center gap-2">
            {granted.map((entry) => (
              <Link
                key={entry.portal}
                to={entry.home_path}
                className="inline-flex items-center rounded-xl border border-border bg-card px-4 py-2 text-sm font-semibold text-foreground shadow-sm transition hover:bg-muted"
              >
                {entry.display_name}
              </Link>
            ))}
          </div>
        </div>
      ) : (
        <p className="text-sm leading-6 text-muted-foreground">
          Your account holds no active membership that opens any portal. Ask your program
          administrator to grant one.
        </p>
      )}
    </Notice>
  );
}

/**
 * The granted descriptor for a portal, or `null` when the shell should render
 * {@link PortalGate} instead.
 *
 * A small helper so each shell states the same condition once rather than
 * three times slightly differently.
 */
export function grantedPortal(state: PortalAccessState, portal: PortalKind) {
  if (state.status !== "ready") {
    return null;
  }
  return portalGrant(state.mapping, portal);
}
