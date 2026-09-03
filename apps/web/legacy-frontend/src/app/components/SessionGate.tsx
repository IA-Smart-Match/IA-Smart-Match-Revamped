/**
 * What a portal shell renders when it has no verified principal.
 *
 * Layouts call this for every session state that is not `signed-in`, so the
 * non-session states have exactly one implementation. It takes no children:
 * it renders *instead of* the shell, never around it, so no portal chrome can
 * leak out before the server has said who the visitor is.
 *
 *  - `loading` — `GET /v1/me` is in flight. A neutral placeholder.
 *  - `unreachable` — the API could not be reached, or did not answer with a
 *    principal. That is an outage, not an answer about this visitor, so it
 *    says so and offers to ask again rather than sending them to `/login`,
 *    which would blame the wrong thing.
 *  - `suspended` — the token resolves, but the account is suspended. Every
 *    authorized route will deny it (`principal_suspended`), so the portal is
 *    not drawn; `/login` would be a misleading destination for an account
 *    that signed in successfully.
 *  - everything else (`no-token`, `rejected`) — `/login`, which states
 *    plainly that institutional sign-in is not connected yet (A1b). Route
 *    guarding is UX only; `/v1` authorization remains the authority.
 */
import type { ReactNode } from "react";
import { Navigate } from "react-router";

import { type SessionState, useRetrySession } from "../hooks/useSession";

function Notice({ title, body, action }: { title: string; body: string; action?: ReactNode }) {
  return (
    <div className="flex min-h-screen items-center justify-center bg-background px-6">
      <div className="max-w-md space-y-3 text-center">
        <h1 className="text-xl font-semibold text-foreground">{title}</h1>
        <p className="text-sm leading-6 text-muted-foreground">{body}</p>
        {action}
      </div>
    </div>
  );
}

export function SessionGate({ state }: { state: Exclude<SessionState, { status: "signed-in" }> }) {
  const retry = useRetrySession();

  if (state.status === "loading") {
    return (
      <div
        className="flex min-h-screen items-center justify-center bg-background"
        role="status"
        aria-live="polite"
      >
        <p className="text-sm text-muted-foreground">Checking your access…</p>
      </div>
    );
  }

  if (state.reason === "unreachable") {
    return (
      <Notice
        title="Can’t confirm your access"
        body="The API did not answer GET /v1/me, so there is no way to tell who you are signed in as. Nothing is shown until it does."
        action={
          <button
            type="button"
            onClick={retry}
            className="inline-flex items-center rounded-xl border border-border bg-card px-4 py-2 text-sm font-semibold text-foreground shadow-sm transition hover:bg-muted"
          >
            Try again
          </button>
        }
      />
    );
  }

  if (state.reason === "suspended") {
    return (
      <Notice
        title="This account is suspended"
        body="Your identity was verified, but an administrator has suspended this account, so every other route will refuse it. Contact your program administrator."
      />
    );
  }

  return <Navigate to="/login" replace />;
}
