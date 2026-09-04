import { Link } from "react-router";
import { motion, useReducedMotion } from "motion/react";
import { ArrowRight, CalendarCheck2, HeartHandshake, SearchCheck } from "lucide-react";

const introReveal = {
  initial: { opacity: 0, y: 22 },
  whileInView: { opacity: 1, y: 0 },
  transition: { duration: 0.65, ease: [0.16, 1, 0.3, 1] as const },
  viewport: { once: true, amount: 0.25 },
} as const;

const steps = [
  {
    icon: SearchCheck,
    number: "01",
    title: "Find events",
    description: "Bring university opportunities into one place instead of searching site by site.",
  },
  {
    icon: HeartHandshake,
    number: "02",
    title: "Choose the right volunteer",
    description: "Compare experience, interests, availability, and workload before making an assignment.",
  },
  {
    icon: CalendarCheck2,
    number: "03",
    title: "Keep assignments on track",
    description: "See what needs attention from the first conversation through the day of the event.",
  },
];

export function LandingPage() {
  const reduceMotion = useReducedMotion();
  const currentYear = new Date().getFullYear();

  return (
    <div className="public-shell flex min-h-screen flex-col">
      <header className="sticky top-0 z-50 border-b border-border/70 bg-[#f8f6f1]/90 backdrop-blur-xl">
        <nav className="mx-auto flex w-full max-w-7xl items-center justify-between px-5 py-3 sm:px-6 lg:px-8">
          <Link to="/" className="block w-[210px] sm:w-[260px]" aria-label="Cal Poly Pomona Smart Match home">
            <img
              src="/brand/cpp-horizontal-green.png"
              alt="Cal Poly Pomona"
              className="brand-logo"
            />
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
        <section className="relative overflow-hidden">
          <div className="pointer-events-none absolute -right-24 top-12 h-72 w-72 rounded-full bg-[#A4D65E]/20 blur-3xl" />
          <div className="mx-auto grid max-w-7xl items-center gap-12 px-6 py-16 lg:grid-cols-[1.08fr_0.92fr] lg:px-8 lg:py-24">
            <motion.div {...introReveal} className="relative z-10 space-y-7">
              <div className="space-y-6">
                <h1 className="max-w-4xl text-4xl font-bold leading-[1.05] tracking-[-0.03em] text-primary sm:text-5xl lg:text-6xl">
                  Match volunteers with events where they can help most.
                </h1>
                <p className="max-w-2xl text-lg leading-8 text-muted-foreground sm:text-xl">
                  Smart Match helps coordinators find opportunities, compare volunteer experience
                  and availability, and keep assignments organized in one place.
                </p>
              </div>
              <Link to="/login" className="public-button-primary group gap-2">
                Sign in to Smart Match
                <ArrowRight className="h-4 w-4 transition-transform group-hover:translate-x-1" aria-hidden="true" />
              </Link>
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
                  <span className="rounded-full bg-[#A4D65E]/25 px-3 py-1.5 text-xs font-semibold text-primary">
                    Ready to assign
                  </span>
                </div>
                <div className="space-y-4">
                  {[
                    ["What the event needs", "Product design and career mentoring"],
                    ["Volunteer availability", "Available on the event date"],
                    ["Break need", "Low — available for another event"],
                  ].map(([label, value], index) => (
                    <div key={label} className="flex gap-4 rounded-2xl bg-muted/70 p-4">
                      <span className="brand-accent flex h-8 w-8 shrink-0 items-center justify-center rounded-full text-sm font-bold text-[#17352a]">
                        {index + 1}
                      </span>
                      <div>
                        <p className="text-xs font-semibold uppercase tracking-[0.12em] text-muted-foreground">{label}</p>
                        <p className="mt-1 font-medium text-foreground">{value}</p>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            </motion.div>
          </div>
        </section>

        <motion.section {...introReveal} className="mx-auto max-w-7xl px-6 py-14 lg:px-8 lg:py-20" aria-labelledby="how-it-works">
          <div className="max-w-2xl">
            <h2 id="how-it-works" className="text-3xl font-semibold text-foreground sm:text-4xl">
              How Smart Match works
            </h2>
            <p className="mt-3 text-lg leading-8 text-muted-foreground">
              Give coordinators the information they need to make thoughtful assignments without adding more busywork.
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
                    <span className="font-[var(--font-headline)] text-sm font-bold text-[#8C6D62]">{step.number}</span>
                  </div>
                  <h3 className="mt-6 text-xl font-semibold text-foreground">{step.title}</h3>
                  <p className="mt-2 leading-7 text-muted-foreground">{step.description}</p>
                </motion.article>
              );
            })}
          </div>
        </motion.section>

        <section className="mx-auto max-w-7xl px-6 pb-16 lg:px-8 lg:pb-24" aria-labelledby="workload-care">
          <div className="overflow-hidden rounded-[2rem] bg-primary text-white shadow-[0_24px_70px_rgba(0,80,48,0.2)]">
            <div className="grid items-center gap-8 p-8 md:grid-cols-[0.8fr_1.2fr] md:p-12">
              <div className="brand-accent flex aspect-square max-w-[220px] items-center justify-center rounded-[2rem] p-7 text-primary shadow-lg">
                <HeartHandshake className="h-24 w-24" aria-hidden="true" />
              </div>
              <div>
                <p className="text-sm font-semibold uppercase tracking-[0.16em] text-[#A4D65E]">Support volunteers</p>
                <h2 id="workload-care" className="mt-3 text-3xl font-semibold text-white sm:text-4xl">
                  Make room for the right break.
                </h2>
                <p className="mt-4 max-w-2xl text-lg leading-8 text-white/80">
                  Workload information helps coordinators see when someone has been assigned often and may need time to rest before another event.
                </p>
              </div>
            </div>
          </div>
        </section>
      </main>

      <footer className="border-t border-border/80 bg-[#F2EEE8]">
        <div className="mx-auto flex max-w-7xl flex-col gap-3 px-6 py-7 text-sm text-muted-foreground sm:flex-row sm:items-center sm:justify-between lg:px-8">
          <p>© {currentYear} Cal Poly Pomona. All rights reserved.</p>
          <p className="font-medium text-primary">Smart Match</p>
        </div>
      </footer>
    </div>
  );
}
