import { Link } from "react-router";
import { motion, useReducedMotion } from "motion/react";
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
    title: "Discover Opportunities",
    description:
      "Automated scraping of university career centers across the West Coast to find the perfect speaking slots.",
  },
  {
    icon: "matching" as const,
    title: "Intelligent Matching",
    description:
      "Advanced algorithms analyze volunteer bios and event descriptions to ensure high-impact connections.",
  },
  {
    icon: "pipeline" as const,
    title: "Pipeline Tracking",
    description:
      "Manage the flow from initial lead to confirmed engagement with detailed CRM-style reporting.",
  },
];

export function LandingPage() {
  const reduceMotion = useReducedMotion();

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
              <Link to="/login?role=ia_admin" className="public-button-primary">
                Start Matching
              </Link>
              <a href="#proof" className="public-button-secondary">
                View Demo
              </a>
            </div>

            <div className="grid gap-4 sm:grid-cols-3">
              <div className="public-panel p-5">
                <p className="text-3xl font-semibold text-primary">2,481</p>
                <p className="mt-1 text-sm text-muted-foreground">opportunities surfaced</p>
              </div>
              <div className="public-panel p-5">
                <p className="text-3xl font-semibold text-primary">842</p>
                <p className="mt-1 text-sm text-muted-foreground">high-fit matches</p>
              </div>
              <div className="public-panel p-5">
                <p className="text-3xl font-semibold text-primary">94%</p>
                <p className="mt-1 text-sm text-muted-foreground">signal confidence</p>
              </div>
            </div>
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

        {/* ── PROOF ────────────────────────────────────────────
            Reference: "Discovery Automation" terminal widget
        ──────────────────────────────────────────────────────── */}
        <motion.section
          id="proof"
          {...introReveal}
          className="mx-auto max-w-7xl px-6 py-8 lg:px-8 lg:py-16"
        >
          {/* Discovery Automation row */}
          <div className="public-panel overflow-hidden">
            <div className="grid md:grid-cols-2">
              {/* Terminal widget */}
              <div className="border-b border-border/60 bg-slate-950 p-6 md:border-b-0 md:border-r md:p-8">
                {/* GET request line */}
                <div className="flex items-center gap-3 rounded-xl border border-white/10 bg-white/5 px-4 py-3">
                  <span className="shrink-0 rounded-md bg-emerald-500/20 px-2 py-0.5 text-[10px] font-bold text-emerald-400">
                    GET
                  </span>
                  <code className="truncate text-xs text-slate-300">
                    https://career.ucla.edu/api/events
                  </code>
                </div>

                {/* Parsing line */}
                <div className="mt-4 flex items-center gap-3 px-1">
                  <motion.span
                    className="h-2 w-2 shrink-0 rounded-full bg-emerald-400"
                    animate={reduceMotion ? undefined : { opacity: [1, 0.3, 1] }}
                    transition={{ duration: 1.4, repeat: Infinity, ease: "easeInOut" }}
                  />
                  <span className="text-xs font-mono font-medium text-slate-400">
                    PARSING UCLA DATA...
                  </span>
                </div>

                {/* Match found */}
                <div className="mt-4 flex items-center justify-between gap-3 rounded-xl bg-primary px-4 py-3">
                  <div className="flex items-center gap-3">
                    <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-white/20 text-[10px] font-bold text-white">
                      ✓
                    </span>
                    <span className="text-xs font-semibold text-white">
                      Match Found: UCLA Career Fair 2026
                    </span>
                  </div>
                  <span className="text-white/60">›</span>
                </div>

                {/* Platform badges */}
                <div className="mt-6 flex flex-wrap items-center gap-2">
                  {["UCLA", "USC", "SDSU"].map((tag) => (
                    <span
                      key={tag}
                      className="rounded-full border border-white/15 bg-white/10 px-3 py-1 text-[10px] font-bold text-slate-300"
                    >
                      {tag}
                    </span>
                  ))}
                  <span className="text-[11px] text-slate-500">+42 Platforms Monitored</span>
                </div>
              </div>

              {/* Copy */}
              <div className="flex flex-col justify-center gap-4 p-6 md:p-10">
                <h3 className="font-[Inter_Tight] text-2xl font-bold text-foreground md:text-3xl">
                  Discovery Automation
                </h3>
                <p className="leading-relaxed text-muted-foreground">
                  Our proprietary web scraping pipeline monitors UCLA, USC, and dozens of other
                  university sites in real-time. No more manual searching; opportunities are
                  delivered directly to your dashboard.
                </p>
                <Link to="/login?role=ia_admin" className="public-button-primary self-start">
                  Start Matching
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
                  Pick your portal and jump straight in.
                </h2>
                <p className="max-w-2xl text-muted-foreground">
                  Students track events and earn points. Event coordinators manage outreach and
                  meetings with IA West. Both portals use pre-loaded demo data.
                </p>
              </div>
              <div className="flex flex-col gap-3 justify-self-start lg:justify-self-end">
                <Link to="/login?role=student" className="public-button-primary">
                  Student Portal
                </Link>
                <Link to="/login?role=event_coordinator" className="public-button-secondary">
                  Event Coordinator
                </Link>
                <Link
                  to="/login"
                  className="text-center text-sm text-muted-foreground transition hover:text-primary"
                >
                  Sign in with email →
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
