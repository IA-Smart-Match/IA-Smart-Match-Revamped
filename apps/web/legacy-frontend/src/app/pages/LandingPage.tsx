/**
 * The public landing page.
 *
 * ## What this page may claim
 *
 * A landing page is the product's first factual statement about itself, and it
 * is read by people who cannot check it. Customer §20 puts finding speakers on
 * the internet, scraping LinkedIn or other external sources, automatic external
 * event discovery, and a contact-acquisition CRM out of scope for this phase;
 * the lists of events and speakers grow **manually inside the system**, and
 * matching occurs only between records already in it.
 *
 * So the copy below describes exactly that. It previously advertised a
 * "proprietary web scraping pipeline" monitoring named universities in real
 * time, a terminal widget issuing a GET to a real third-party host, "+42
 * Platforms Monitored", and three headline figures (2,481 / 842 / 94%) that no
 * measurement produced. Every one of them is a claim a visitor would act on.
 *
 * The rule for editing this file: a number here must come from a registered
 * metric or not appear (ADR-0011 rule 1), and a capability described here must
 * be one `src/lib/productScope.ts` says this product offers.
 */
import { Link } from "react-router";
import { motion } from "motion/react";
import { AppIcon } from "../../components/AppIcon";

const introReveal = {
  initial: { opacity: 0, y: 24 },
  whileInView: { opacity: 1, y: 0 },
  transition: { duration: 0.7, ease: [0.16, 1, 0.3, 1] as const },
  viewport: { once: true, amount: 0.35 },
} as const;

const pipelineFeatures = [
  {
    icon: "discover" as const,
    title: "Records You Already Have",
    description:
      "Coordinators enter events and speaker records inside the system, and review every import before it becomes matchable. Nothing is collected from outside it.",
  },
  {
    icon: "matching" as const,
    title: "Intelligent Matching",
    description:
      "Each match run scores the speakers already on file against an event, and records the factors and version it used so a ranking can be re-read later.",
  },
  {
    icon: "pipeline" as const,
    title: "Pipeline Tracking",
    description:
      "Follow an invitation from matched through contacted, confirmed, and attended. Every figure shown is a registered metric, or says why it is unknown.",
  },
];

/**
 * The in-scope workflow, in the order it actually happens.
 *
 * Each step names something the system does today: an operator import through
 * the quarantine/review path, an immutable versioned match run over records
 * already stored, an approved draft sent to a contact whose consent is on
 * record and re-checked at delivery, and the funnel stages a coordinator moves
 * a record through. Nothing here describes a capability
 * `src/lib/productScope.ts` gates.
 */
const matchSteps = [
  {
    title: "A coordinator adds the records",
    description:
      "Events and speaker details are entered or imported by staff, then reviewed and corrected before anything becomes matchable.",
  },
  {
    title: "A match run ranks the candidates",
    description:
      "The run scores stored speakers against a stored event and is kept immutable, so the same ranking can be re-read with the factors it used.",
  },
  {
    title: "An approved draft goes out",
    description:
      "Outreach is sent only to a contact whose consent is already on record, and consent is checked again at the moment of delivery.",
  },
  {
    title: "The pipeline records what happened",
    description:
      "Matched, contacted, confirmed, attended — each stage is a stored record, and the dashboard reports the registered metric behind it.",
  },
];

export function LandingPage() {
  return (
    <div className="public-shell">
      {/* ── Header ──────────────────────────────────────────── */}
      <header className="sticky top-0 z-50 border-b border-border/70 bg-background/85 backdrop-blur-xl">
        <nav className="mx-auto flex max-w-7xl items-center justify-between px-6 py-4 lg:px-8">
          <Link to="/" className="flex items-center gap-3">
            <span className="flex h-11 w-11 items-center justify-center rounded-2xl bg-primary text-sm font-bold text-primary-foreground shadow-lg shadow-primary/20">
              IW
            </span>
            <div className="leading-tight">
              <p className="font-semibold text-foreground">IA West Smart Match</p>
              <p className="text-xs uppercase tracking-[0.28em] text-muted-foreground">Coordinator Platform</p>
            </div>
          </Link>
          <Link to="/login" className="public-button-primary">Sign In</Link>
        </nav>
      </header>

      <main>
        {/* ── HERO ──────────────────────────────────────────── */}
        <section
          id="hero"
          className="mx-auto max-w-5xl px-6 py-16 text-center lg:px-8 lg:py-24"
        >
          <motion.div {...introReveal} className="space-y-8">
            <span className="public-pill">AI-Driven Volunteer Coordination for IA West</span>

            <div className="space-y-6">
              <h1 className="font-[Inter_Tight] text-5xl font-bold leading-[1.08] tracking-tight text-foreground md:text-6xl lg:text-7xl">
                Connect the right speakers with the right university opportunities
              </h1>

              <p className="mx-auto max-w-2xl text-lg leading-relaxed text-muted-foreground md:text-xl">
                Intelligent matching system that bridges the gap between industry expertise and
                academic needs through high-fidelity data signals.
              </p>
            </div>

            <div className="flex flex-wrap items-center justify-center gap-3">
              <Link to="/login" className="public-button-primary">
                Sign in
              </Link>
              <a href="#proof" className="public-button-secondary">
                View Demo
              </a>
            </div>

            {/* No headline figures. The three that used to sit here were
                decoration: no registered metric produced them, and this page
                cannot read a unit's metrics anyway — it is unauthenticated, and
                every real number in this product is unit-scoped and behind
                `GET /v1/units/{unit_id}/metrics`. A visitor's first impression
                is exactly the wrong place to start inventing measurements
                (ADR-0011 rule 1). The signed-in dashboard shows the real ones,
                with their provenance and their drill-downs. */}
          </motion.div>
        </section>

        {/* ── STORY ────────────────────────────────────────────
            Reference: "Complete Volunteer Engagement Pipeline"
        ──────────────────────────────────────────────────────── */}
        <motion.section
          id="story"
          {...introReveal}
          className="mx-auto max-w-7xl px-6 py-8 lg:px-8 lg:py-16"
        >
          <div className="mb-12 space-y-2">
            <h2 className="font-[Inter_Tight] text-3xl font-bold tracking-tight text-foreground md:text-4xl">
              Complete Volunteer Engagement Pipeline
            </h2>
            <p className="text-base text-muted-foreground">
              A unified platform to manage the entire lifecycle of university partnerships.
            </p>
          </div>

          <div className="grid gap-8 border-t border-border/60 pt-10 md:grid-cols-3">
            {pipelineFeatures.map((feature, i) => (
              <motion.div
                key={feature.title}
                initial={{ opacity: 0, y: 16 }}
                whileInView={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.5, delay: i * 0.1, ease: [0.16, 1, 0.3, 1] }}
                viewport={{ once: true, amount: 0.4 }}
                className="flex flex-col gap-4"
              >
                <div className="flex h-11 w-11 items-center justify-center rounded-2xl bg-primary/10">
                  <AppIcon name={feature.icon} className="h-5 w-5 text-primary" />
                </div>
                <div>
                  <h3 className="font-[Inter_Tight] text-lg font-bold text-foreground">
                    {feature.title}
                  </h3>
                  <p className="mt-2 text-sm leading-relaxed text-muted-foreground">
                    {feature.description}
                  </p>
                </div>
              </motion.div>
            ))}
          </div>
        </motion.section>

        {/* ── HOW IT WORKS ─────────────────────────────────────
            Replaces the "Discovery Automation" terminal widget, which showed
            a GET to a live third-party host, a parsing animation, a
            fabricated "Match Found", and "+42 Platforms Monitored". None of
            it happened, and all of it depicted work customer §20 puts out of
            scope for this phase.
        ──────────────────────────────────────────────────────── */}
        <motion.section
          id="proof"
          {...introReveal}
          className="mx-auto max-w-7xl px-6 py-8 lg:px-8 lg:py-16"
        >
          <div className="public-panel overflow-hidden">
            <div className="grid md:grid-cols-2">
              <div className="border-b border-border/60 p-6 md:border-b-0 md:border-r md:p-10">
                <h3 className="font-[Inter_Tight] text-2xl font-bold text-foreground md:text-3xl">
                  How a match happens
                </h3>
                <ol className="mt-6 space-y-5">
                  {matchSteps.map((step, index) => (
                    <li key={step.title} className="flex gap-4">
                      <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-primary/10 text-xs font-bold text-primary">
                        {index + 1}
                      </span>
                      <div>
                        <p className="font-semibold text-foreground">{step.title}</p>
                        <p className="mt-1 text-sm leading-relaxed text-muted-foreground">
                          {step.description}
                        </p>
                      </div>
                    </li>
                  ))}
                </ol>
              </div>

              <div className="flex flex-col justify-center gap-4 p-6 md:p-10">
                <h3 className="font-[Inter_Tight] text-2xl font-bold text-foreground md:text-3xl">
                  What it will not do
                </h3>
                <p className="leading-relaxed text-muted-foreground">
                  This phase does not search the internet for speakers, read
                  outside profile sources, pull events in from external systems,
                  or contact anyone who has not agreed to be contacted. Records
                  enter through a person, and a person reviews them.
                </p>
                <p className="leading-relaxed text-muted-foreground">
                  Where a number cannot be measured, the application says so
                  rather than showing a zero.
                </p>
                <Link to="/login" className="public-button-primary self-start">
                  Sign in
                </Link>
              </div>
            </div>
          </div>
        </motion.section>

        {/* ── LOGIN CTA ────────────────────────────────────────── */}
        <motion.section
          id="login"
          {...introReveal}
          className="mx-auto max-w-5xl px-6 py-8 pb-20 lg:px-8 lg:py-16"
        >
          <div className="public-panel overflow-hidden p-8 md:p-10">
            <div className="grid gap-8 lg:grid-cols-[1fr_auto] lg:items-center">
              <div className="space-y-4">
                <p className="public-pill">Ready to explore?</p>
                <h2 className="font-[Inter_Tight] text-3xl font-semibold tracking-tight text-foreground md:text-4xl">
                  Sign in when institutional access is connected.
                </h2>
                <p className="max-w-2xl text-muted-foreground">
                  Portal access and roles are assigned by the server after verified identity. Until
                  institutional sign-in is connected, the login page explains what is not available yet.
                </p>
              </div>
              <div className="flex flex-col gap-3 justify-self-start lg:justify-self-end">
                <Link to="/login" className="public-button-primary">
                  Sign in
                </Link>
              </div>
            </div>
          </div>
        </motion.section>
      </main>

      <footer className="border-t border-border/70 bg-background/80">
        <div className="mx-auto flex max-w-7xl flex-col gap-3 px-6 py-8 text-sm text-muted-foreground md:flex-row md:items-center md:justify-between lg:px-8">
          <p className="font-medium text-foreground">IA West Smart Match</p>
        </div>
      </footer>
    </div>
  );
}
