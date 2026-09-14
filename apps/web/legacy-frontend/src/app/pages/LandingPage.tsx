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
 * So the copy below describes exactly that. It previously advertised an
 * external-acquisition pipeline monitoring named universities in real time, a
 * terminal widget issuing a request to a real third-party host, a platforms-
 * monitored count, and three headline figures that no measurement produced.
 * Every one of them was a claim a visitor would act on.
 *
 * The rule for editing this file: a number here must come from a registered
 * metric or not appear (ADR-0011 rule 1), and a capability described here must
 * be one `src/lib/productScope.ts` says this product offers.
 */
import { Link } from "react-router";
import { motion, useReducedMotion } from "motion/react";
import { ArrowRight, CalendarCheck2, HeartHandshake, SearchCheck } from "lucide-react";

const introReveal = {
  initial: { opacity: 0, y: 22 },
  whileInView: { opacity: 1, y: 0 },
  transition: { duration: 0.65, ease: [0.16, 1, 0.3, 1] as const },
  viewport: { once: true, amount: 0.25 },
} as const;

/**
 * The in-scope workflow, in the order it actually happens.
 *
 * Each step names something the system does today: an operator import through
 * the quarantine/review path, an immutable versioned match run over records
 * already stored, and the funnel stages a coordinator moves a record through.
 * Nothing here describes a capability `src/lib/productScope.ts` gates.
 */
const steps = [
  {
    icon: SearchCheck,
    number: "01",
    title: "Create and organize events",
    description:
      "Event Hosts add event details, staffing needs, and schedules in one shared place. Nothing is collected from outside it.",
  },
  {
    icon: HeartHandshake,
    number: "02",
    title: "Intelligent Matching finds the right speaker",
    description:
      "Each match run scores the speakers already on file against an event, and records the factors and version it used so a ranking can be re-read later.",
  },
  {
    icon: CalendarCheck2,
    number: "03",
    title: "Keep assignments on track",
    description:
      "Follow an assignment from matched through contacted, confirmed, and attended. Every figure shown is a registered metric, or says why it is unknown.",
  },
];

export function LandingPage() {
  const reduceMotion = useReducedMotion();
  const currentYear = new Date().getFullYear();

  return (
    <div className="public-shell flex min-h-screen flex-col">
      <header className="sticky top-0 z-50 border-b border-border/70 bg-background/90 backdrop-blur-xl">
        <nav className="mx-auto flex w-full max-w-7xl items-center justify-between px-5 py-3 sm:px-6 lg:px-8">
          <Link to="/" className="block w-[210px] sm:w-[260px]" aria-label="CBA Smart Match home">
            <img src="/brand/cpp-horizontal-green.png" alt="Cal Poly Pomona" className="brand-logo" />
          </Link>
          <Link
            to="/login"
            className="rounded-md px-2 py-2 text-sm font-semibold text-primary transition hover:text-primary/70 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary"
          >
            Sign in
          </Link>
        </nav>
      </header>

      <main className="flex-1">
        {/* ── HERO ──────────────────────────────────────────── */}
        <section className="relative overflow-hidden">
          <div className="pointer-events-none absolute -right-24 top-12 h-72 w-72 rounded-full bg-accent blur-3xl" />
          <div className="mx-auto grid max-w-7xl items-center gap-12 px-6 py-16 lg:grid-cols-[1.08fr_0.92fr] lg:px-8 lg:py-24">
            <motion.div {...introReveal} className="relative z-10 space-y-7">
              <span className="public-pill">Intelligent Matching for Event Hosts</span>

              <div className="space-y-6">
                <h1 className="max-w-4xl text-4xl font-bold leading-[1.05] tracking-[-0.03em] text-primary sm:text-5xl lg:text-6xl">
                  Match speakers with events where they can help most.
                </h1>
                <p className="max-w-2xl text-lg leading-8 text-muted-foreground sm:text-xl">
                  Smart Match helps Event Hosts create and organize events, compare speaker
                  experience and availability, and keep staffing assignments in one place.
                </p>
              </div>

              <div className="flex flex-wrap items-center gap-3">
                <Link to="/login" className="public-button-primary group gap-2">
                  Sign in to Smart Match
                  <ArrowRight className="h-4 w-4 transition-transform group-hover:translate-x-1" aria-hidden="true" />
                </Link>
              </div>

              {/* No headline figures. The three that used to sit here were
                  decoration: no registered metric produced them, and this page
                  cannot read a unit's metrics anyway — it is unauthenticated,
                  and every real number in this product is unit-scoped and
                  behind `GET /v1/units/{unit_id}/metrics`. A visitor's first
                  impression is exactly the wrong place to start inventing
                  measurements (ADR-0011 rule 1). The signed-in dashboard shows
                  the real ones, with their provenance and their drill-downs. */}
            </motion.div>

            <motion.div
              initial={reduceMotion ? false : { opacity: 0, x: 28 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ duration: 0.75, delay: 0.12, ease: [0.16, 1, 0.3, 1] }}
              className="relative"
              aria-label="A simple event assignment workflow"
            >
              <div className="brand-accent absolute -inset-3 rounded-[2rem] opacity-35 blur-xl" />
              <div className="public-panel relative overflow-hidden p-6 sm:p-8">
                <div className="mb-7 flex items-center justify-between border-b border-border/70 pb-5">
                  <div>
                    <p className="text-sm font-semibold text-primary">Upcoming event</p>
                    <h2 className="mt-1 text-2xl font-semibold text-foreground">Career panel</h2>
                  </div>
                  <span className="rounded-full bg-accent px-3 py-1.5 text-xs font-semibold text-primary">
                    Ready to assign
                  </span>
                </div>
                <div className="space-y-4">
                  {[
                    ["What the event needs", "Product design and career mentoring"],
                    ["Speaker availability", "Available on the event date"],
                    ["Break need", "Low — available for another event"],
                  ].map(([label, value], index) => (
                    <div key={label} className="flex gap-4 rounded-2xl bg-muted/70 p-4">
                      <span className="brand-accent flex h-8 w-8 shrink-0 items-center justify-center rounded-full text-sm font-bold text-primary-foreground">
                        {index + 1}
                      </span>
                      <div>
                        <p className="text-xs font-semibold uppercase tracking-[0.12em] text-muted-foreground">
                          {label}
                        </p>
                        <p className="mt-1 font-medium text-foreground">{value}</p>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            </motion.div>
          </div>
        </section>

        {/* ── HOW IT WORKS ─────────────────────────────────────
            Replaces the "Discovery Automation" terminal widget, which showed
            a GET to a live third-party host, a parsing animation, a
            fabricated "Match Found", and "+42 Platforms Monitored". None of
            it happened, and all of it depicted work customer §20 puts out of
            scope for this phase.
        ──────────────────────────────────────────────────────── */}
        <motion.section
          {...introReveal}
          className="mx-auto max-w-7xl px-6 py-14 lg:px-8 lg:py-20"
          aria-labelledby="how-it-works"
        >
          <div className="max-w-2xl">
            <h2 id="how-it-works" className="text-3xl font-semibold text-foreground sm:text-4xl">
              How Smart Match works
            </h2>
            <p className="mt-3 text-lg leading-8 text-muted-foreground">
              Give Event Hosts the information they need to make thoughtful assignments without
              adding more busywork.
            </p>
          </div>

          <div className="mt-10 grid gap-5 md:grid-cols-3">
            {steps.map((step, index) => {
              const Icon = step.icon;
              return (
                <motion.article
                  key={step.title}
                  initial={reduceMotion ? false : { opacity: 0, y: 18 }}
                  whileInView={{ opacity: 1, y: 0 }}
                  transition={{ duration: 0.5, delay: index * 0.08 }}
                  viewport={{ once: true, amount: 0.35 }}
                  className="public-panel flex h-full flex-col p-6"
                >
                  <div className="flex items-center justify-between">
                    <span className="flex h-11 w-11 items-center justify-center rounded-2xl bg-primary text-primary-foreground">
                      <Icon className="h-5 w-5" aria-hidden="true" />
                    </span>
                    <span className="text-sm font-bold text-muted-foreground">{step.number}</span>
                  </div>
                  <h3 className="mt-6 text-xl font-semibold text-foreground">{step.title}</h3>
                  <p className="mt-2 leading-7 text-muted-foreground">{step.description}</p>
                </motion.article>
              );
            })}
          </div>
        </motion.section>

        {/* ── WHAT IT WILL NOT DO ──────────────────────────────── */}
        <motion.section {...introReveal} className="mx-auto max-w-7xl px-6 pb-16 lg:px-8 lg:pb-24">
          <div className="public-panel overflow-hidden">
            <div className="grid md:grid-cols-2">
              <div className="border-b border-border/60 p-6 md:border-b-0 md:border-r md:p-10">
                <h3 className="text-2xl font-bold text-foreground md:text-3xl">What it will not do</h3>
                <p className="mt-4 leading-relaxed text-muted-foreground">
                  This phase does not search the internet for speakers, read outside profile
                  sources, pull events in from external systems, or contact anyone who has not
                  agreed to be contacted. Records enter through a person, and a person reviews
                  them.
                </p>
                <p className="mt-4 leading-relaxed text-muted-foreground">
                  Where a number cannot be measured, the application says so rather than showing a
                  zero.
                </p>
              </div>
              <div className="flex flex-col justify-center gap-4 p-6 md:p-10">
                <p className="text-sm font-semibold uppercase tracking-[0.16em] text-primary">
                  Support speakers
                </p>
                <h3 className="text-2xl font-bold text-foreground md:text-3xl">
                  Make room for the right break.
                </h3>
                <p className="leading-relaxed text-muted-foreground">
                  Workload information helps Event Hosts see when a speaker has been assigned often
                  and may need time to rest before another event.
                </p>
                <Link to="/login" className="public-button-primary self-start">
                  Sign in
                </Link>
              </div>
            </div>
          </div>
        </motion.section>
      </main>

      <footer className="border-t border-border/80 bg-muted/60">
        <div className="mx-auto flex max-w-7xl flex-col gap-3 px-6 py-7 text-sm text-muted-foreground sm:flex-row sm:items-center sm:justify-between lg:px-8">
          <p>© {currentYear} Cal Poly Pomona. All rights reserved.</p>
          <p className="font-medium text-primary">Smart Match</p>
        </div>
      </footer>
    </div>
  );
}
