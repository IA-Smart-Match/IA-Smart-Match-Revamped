/**
 * The pilot sign-in screen.
 *
 * This page used to say "Institutional sign-in is not connected yet" and
 * accept no input at all, because A1b's identity provider is unconfigured. It
 * still is. What changed is that the project owner authorized, on 2026-09-04,
 * a **pilot-scoped** login backed by credentials they supply — see
 * `docs/decisions/pilot-login-decision-2026-09-04.md` — so the screen now
 * takes a credential and exchanges it for a session instead of standing there
 * declaring itself useless.
 *
 * ## What this form sends, and what it structurally cannot send
 *
 * Two fields: an email and a password. There is no role selector, no tenant
 * picker, no unit input, and no `?role=` link that could seed one — the
 * archived defect (Fix #7 / MM-A01) was a login page where the *visitor* chose
 * who they were, and the absence of those controls is the visible half of not
 * reopening it.
 *
 * The invisible half is stronger than the absence of a widget: the server's
 * `LoginRequest` forbids extra fields outright, so a body carrying `role` is
 * rejected with a 422 rather than quietly ignored. A future edit to this file
 * cannot re-introduce caller-chosen roles by adding an input, because the
 * request would stop being accepted.
 *
 * ## What happens after a successful sign-in
 *
 * The response carries an opaque token and nothing else — no user id, no
 * tenant, no role. It is stored as a credential, and then the app asks `GET
 * /v1/me` who that credential belongs to. Identity is the server's answer,
 * exactly as it was before this page could sign anyone in; this screen is a
 * way to obtain a credential, never a place where a session's contents are
 * decided.
 *
 * ## What is deliberately not on this page
 *
 * No password reset, no sign-up, no "remember me". Pilot credentials are
 * issued out of band by the owner and rotated by re-running the seed; a
 * self-service password surface is part of standing up real authentication,
 * not part of a stand-in for it. And no list of demo accounts: canned login
 * emails on a login screen are how the archived version invited people to pick
 * an identity.
 */
import { useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router";
import { motion } from "motion/react";
import { LockKeyhole } from "lucide-react";

import { ApiRequestError, postLogin, storeSmartmatchBearerToken } from "@/lib/api";
import { useRetrySession, useSession } from "../hooks/useSession";

const panelReveal = {
  initial: { opacity: 0, y: 24 },
  animate: { opacity: 1, y: 0 },
  transition: { duration: 0.65, ease: [0.16, 1, 0.3, 1] as const },
} as const;

/**
 * What to show the person for a failed attempt.
 *
 * The server answers every credential failure with one code and one message on
 * purpose, so that a login cannot be used to discover which addresses exist.
 * This function does not undo that: it passes the server's own message
 * through, and only supplies wording where the server said nothing a person
 * could read (a network failure, a body the browser never got).
 */
function signInFailureMessage(error: unknown): string {
  if (error instanceof ApiRequestError) {
    if (error.status === 422) {
      return "Enter an email address and a password.";
    }
    return error.message;
  }
  return "The sign-in service could not be reached. Check your connection and try again.";
}

export function LoginPage() {
  const navigate = useNavigate();
  const session = useSession();
  const retrySession = useRetrySession();

  const [email, setEmail] = useState("");
  const [secret, setSecret] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submitCredentials(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (submitting) {
      return;
    }

    setSubmitting(true);
    setError(null);

    try {
      const issued = await postLogin(email.trim(), secret);
      // A credential, not an identity. Who this is remains GET /v1/me's answer.
      storeSmartmatchBearerToken(issued.access_token);
      // Drop the memoized signed-out answer so the next resolution asks the
      // server with the new credential rather than replaying the old refusal.
      retrySession();
      // Home, not a portal: which portal this account opens is
      // `GET /v1/me/portals`' answer, and guessing one here from an email
      // would be the browser deciding an access question again.
      navigate("/");
    } catch (caught) {
      setError(signInFailureMessage(caught));
    } finally {
      setSubmitting(false);
    }
  }

  const alreadySignedIn = session.status === "signed-in";

  return (
    <div className="public-shell">
      <header className="border-b border-border/70 bg-background/85 backdrop-blur-xl">
        <nav className="mx-auto flex max-w-7xl items-center justify-between px-6 py-4 lg:px-8">
          <Link to="/" className="flex items-center gap-3">
            <span className="flex h-11 w-11 items-center justify-center rounded-2xl bg-primary text-sm font-bold text-primary-foreground shadow-lg shadow-primary/20">
              IW
            </span>
            <div className="leading-tight">
              <p className="font-semibold text-foreground">IA West Smart Match</p>
              <p className="text-xs uppercase tracking-[0.28em] text-muted-foreground">
                Portal login
              </p>
            </div>
          </Link>
          <Link
            to="/"
            className="text-sm font-medium text-muted-foreground transition hover:text-primary"
          >
            Back to home
          </Link>
        </nav>
      </header>

      <main className="mx-auto max-w-2xl px-6 py-12 lg:px-8 lg:py-16">
        <motion.div {...panelReveal} className="mb-10 space-y-3 text-center">
          <span className="public-pill">Sign in</span>
          <h1 className="font-[Inter_Tight] text-4xl font-semibold tracking-tight text-foreground md:text-5xl">
            Pilot sign-in
          </h1>
          <p className="mx-auto max-w-xl text-base leading-7 text-muted-foreground">
            Access is assigned by the server after your credentials are verified. Roles are not
            chosen in the browser.
          </p>
        </motion.div>

        <motion.section
          {...panelReveal}
          transition={{ ...panelReveal.transition, delay: 0.06 }}
          className="public-panel overflow-hidden"
          aria-labelledby="sign-in-heading"
        >
          <div className="border-b border-border/70 px-6 py-5">
            <div className="flex items-center gap-3">
              <div className="flex h-11 w-11 items-center justify-center rounded-xl bg-primary/10 text-primary">
                <LockKeyhole className="h-5 w-5" aria-hidden="true" />
              </div>
              <div>
                <p className="public-pill">Pilot access</p>
                <h2
                  id="sign-in-heading"
                  className="mt-2 font-[Inter_Tight] text-2xl font-semibold text-foreground"
                >
                  Sign in with your pilot credentials
                </h2>
              </div>
            </div>
          </div>

          <div className="space-y-6 px-6 py-6">
            {alreadySignedIn && (
              <p
                className="rounded-xl border border-border/70 bg-muted/40 px-4 py-3 text-sm leading-6 text-muted-foreground"
                role="status"
              >
                You are already signed in as{" "}
                <span className="font-medium text-foreground">{session.me.email}</span>. Signing in
                again replaces that session.
              </p>
            )}

            <form className="space-y-5" onSubmit={submitCredentials} noValidate>
              <div className="space-y-2">
                <label htmlFor="pilot-email" className="block text-sm font-medium text-foreground">
                  Email
                </label>
                <input
                  id="pilot-email"
                  name="email"
                  type="email"
                  autoComplete="username"
                  required
                  value={email}
                  onChange={(event) => setEmail(event.target.value)}
                  placeholder="you@example.edu"
                  className="w-full rounded-xl border border-border bg-background px-4 py-2.5 text-sm text-foreground shadow-sm outline-none transition focus:border-primary focus:ring-2 focus:ring-primary/30"
                />
              </div>

              <div className="space-y-2">
                <label
                  htmlFor="pilot-password"
                  className="block text-sm font-medium text-foreground"
                >
                  Password
                </label>
                <input
                  id="pilot-password"
                  name="password"
                  type="password"
                  autoComplete="current-password"
                  required
                  value={secret}
                  onChange={(event) => setSecret(event.target.value)}
                  className="w-full rounded-xl border border-border bg-background px-4 py-2.5 text-sm text-foreground shadow-sm outline-none transition focus:border-primary focus:ring-2 focus:ring-primary/30"
                />
              </div>

              {error && (
                <p
                  className="rounded-xl border border-destructive/30 bg-destructive/5 px-4 py-3 text-sm leading-6 text-destructive"
                  role="alert"
                >
                  {error}
                </p>
              )}

              <button
                type="submit"
                disabled={submitting}
                className="w-full rounded-xl bg-primary px-4 py-2.5 text-sm font-semibold text-primary-foreground shadow-sm transition hover:bg-primary/90 disabled:cursor-not-allowed disabled:opacity-60"
              >
                {submitting ? "Signing in…" : "Sign in"}
              </button>
            </form>

            <div className="space-y-3 border-t border-border/70 pt-5 text-sm leading-6 text-muted-foreground">
              <p>
                Your account and your role come from the server. After sign-in,{" "}
                <code className="rounded bg-muted px-1.5 py-0.5 text-xs">GET /v1/me</code> reports
                who you are and{" "}
                <code className="rounded bg-muted px-1.5 py-0.5 text-xs">GET /v1/me/portals</code>{" "}
                reports which portals your roles open. This screen sends a credential and nothing
                else — no role, tenant, or unit.
              </p>
              <p>
                This is a <span className="font-medium text-foreground">pilot</span> sign-in using
                credentials issued by the project owner. It is not your institution&apos;s
                identity provider: institutional single sign-on (A1b) is still unconfigured, and
                this path is scheduled to be withdrawn when it is connected. Contact the pilot
                owner for credentials or to have a password reset — there is no self-service reset
                here.
              </p>
            </div>
          </div>
        </motion.section>
      </main>
    </div>
  );
}
