import { Link } from "react-router";
import { motion } from "motion/react";
import { LockKeyhole } from "lucide-react";

const panelReveal = {
  initial: { opacity: 0, y: 24 },
  animate: { opacity: 1, y: 0 },
  transition: { duration: 0.65, ease: [0.16, 1, 0.3, 1] as const },
} as const;

export function LoginPage() {
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
              <p className="text-xs uppercase tracking-[0.28em] text-muted-foreground">Portal login</p>
            </div>
          </Link>
          <Link to="/" className="text-sm font-medium text-muted-foreground transition hover:text-primary">
            Back to home
          </Link>
        </nav>
      </header>

      <main className="mx-auto max-w-2xl px-6 py-12 lg:px-8 lg:py-16">
        <motion.div {...panelReveal} className="mb-10 space-y-3 text-center">
          <span className="public-pill">Sign in</span>
          <h1 className="font-[Inter_Tight] text-4xl font-semibold tracking-tight text-foreground md:text-5xl">
            Institutional sign-in
          </h1>
          <p className="mx-auto max-w-xl text-base leading-7 text-muted-foreground">
            Access is assigned by the server after verified identity. Roles are not chosen in the browser.
          </p>
        </motion.div>

        <motion.section
          {...panelReveal}
          transition={{ ...panelReveal.transition, delay: 0.06 }}
          className="public-panel overflow-hidden"
          aria-labelledby="sign-in-unavailable-heading"
        >
          <div className="border-b border-border/70 px-6 py-5">
            <div className="flex items-center gap-3">
              <div className="flex h-11 w-11 items-center justify-center rounded-xl bg-muted text-muted-foreground">
                <LockKeyhole className="h-5 w-5" aria-hidden="true" />
              </div>
              <div>
                <p className="public-pill">Not connected</p>
                <h2
                  id="sign-in-unavailable-heading"
                  className="mt-2 font-[Inter_Tight] text-2xl font-semibold text-foreground"
                >
                  Institutional sign-in is not connected yet
                </h2>
              </div>
            </div>
          </div>
          <div className="space-y-4 px-6 py-6 text-sm leading-7 text-muted-foreground">
            <p>
              IA West Smart Match will use your institution&apos;s identity provider once A1b is
              configured. Until then, this page does not accept email, role, tenant, or user input,
              and it cannot open a portal session.
            </p>
            <p>
              When sign-in is available, your account and server-assigned roles will come from a
              verified token and <code className="rounded bg-muted px-1.5 py-0.5 text-xs">GET /v1/me</code>
              — not from choices made on this screen.
            </p>
          </div>
        </motion.section>
      </main>
    </div>
  );
}
