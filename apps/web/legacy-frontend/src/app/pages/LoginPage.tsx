import { Link } from "react-router";
import { motion } from "motion/react";
import { ArrowLeft, Building2, LockKeyhole } from "lucide-react";

const panelReveal = {
  initial: { opacity: 0, y: 24 },
  animate: { opacity: 1, y: 0 },
  transition: { duration: 0.65, ease: [0.16, 1, 0.3, 1] as const },
} as const;

export function LoginPage() {
  const currentYear = new Date().getFullYear();

  return (
    <div className="public-shell flex min-h-screen flex-col">
      <header className="border-b border-border/70 bg-[#f8f6f1]/90 backdrop-blur-xl">
        <nav className="mx-auto flex max-w-7xl items-center justify-between px-6 py-4 lg:px-8">
          <Link to="/" className="block w-[210px] sm:w-[260px]" aria-label="Cal Poly Pomona Smart Match home">
            <img src="/brand/cpp-horizontal-green.png" alt="Cal Poly Pomona" className="brand-logo" />
          </Link>
          <Link to="/" className="inline-flex items-center gap-2 text-sm font-semibold text-primary transition hover:text-primary/75">
            <ArrowLeft className="h-4 w-4" aria-hidden="true" />
            Back to home
          </Link>
        </nav>
      </header>

      <main className="mx-auto flex w-full max-w-5xl flex-1 items-center px-6 py-12 lg:px-8 lg:py-16">
        <div className="grid w-full items-center gap-10 lg:grid-cols-[0.85fr_1.15fr]">
        <motion.div {...panelReveal} className="mb-10 space-y-3 text-center">
          <span className="public-pill">Sign in</span>
          <h1 className="text-4xl font-bold leading-tight tracking-[-0.02em] text-primary md:text-5xl">
            Welcome to Smart Match
          </h1>
          <p className="mx-auto max-w-xl text-base leading-7 text-muted-foreground lg:text-left">
            Your school or organization will provide access when institutional sign-in is ready.
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
              <div className="brand-accent flex h-12 w-12 items-center justify-center rounded-2xl text-primary">
                <LockKeyhole className="h-5 w-5" aria-hidden="true" />
              </div>
              <div>
                <p className="text-sm font-semibold text-primary">Access update</p>
                <h2
                  id="sign-in-unavailable-heading"
                  className="mt-1 text-2xl font-semibold text-foreground"
                >
                  Institutional sign-in is not connected yet
                </h2>
              </div>
            </div>
          </div>
          <div className="space-y-5 px-6 py-6 text-sm leading-7 text-muted-foreground">
            <p>
              Smart Match will use the account provided by your institution. Until that connection is ready,
              this page cannot open a portal session.
            </p>
            <div className="flex gap-3 rounded-2xl bg-muted/80 p-4">
              <Building2 className="mt-0.5 h-5 w-5 shrink-0 text-primary" aria-hidden="true" />
              <p>
                When access is enabled, Smart Match will recognize your account and open the correct workspace automatically.
              </p>
            </div>
            <p className="text-xs text-muted-foreground/80">Connection reference: A1b</p>
          </div>
        </motion.section>
        </div>
      </main>

      <footer className="border-t border-border/80 bg-[#F2EEE8] px-6 py-6 text-center text-sm text-muted-foreground">
        © {currentYear} Cal Poly Pomona. All rights reserved.
      </footer>
    </div>
  );
}
