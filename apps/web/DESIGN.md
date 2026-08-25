# SmartMatch Design Standard

**Status: NOT STARTED — this document is a brief, not a design.**
**Owner: unassigned. Blocks all frontend work.**

The frontend is deliberately on hold pending a redesign and a standardized
design system. This document exists so that when that work begins it starts from
the constraints already decided, rather than rediscovering them — and so nobody
builds a screen in the meantime.

Everything below in **Part 1** is settled: it follows from architecture v1.1 and
from the specific failures of the demo this replaces. Everything in **Part 2** is
open and is what the redesign must decide.

---

## Why the frontend is blocked

Three reasons, in order of how much trouble each would cause if ignored.

**1. There is no design standard yet.** The legacy accumulated four portal
experiences, two landing pages, a Streamlit UI, and 44 imported components with
no shared decisions behind them. Rebuilding without a standard reproduces that.

**2. The generated client does not exist yet.** Architecture v1.1 §5.1 requires
the frontend consume a **generated** TypeScript client, never a hand-maintained
one. The client is generated from `contracts/openapi/smartmatch.json`, which
currently describes five endpoints. Building screens now means hand-writing API
calls and rewriting them later — recreating exactly the coupling the contract
forbids.

**3. Most screens have nothing truthful to show.** The control center's thirteen
views (v1.1 §5.2) depend on match runs, which are blocked on gate G1. A screen
built before its data exists gets populated with placeholder content, and
placeholder content that looks real is the single habit this whole revamp exists
to end.

---

# Part 1 — Constraints the design must satisfy

Not stylistic preferences. Each traces to a contract clause or to a specific
legacy defect, and a design that violates one is wrong regardless of how it
looks.

## 1.1 Provenance is visible on every data element

Architecture v1.1 §5.5. Every value on screen carries a visible source label:

| Label | Meaning |
|---|---|
| Observed | A recorded fact — someone entered it, or a system captured it |
| Inferred | Derived from other data by a deterministic rule |
| Heuristic score | A computed score from the factor registry |
| Model output | Produced by a language or embedding model |
| Synthetic / demo | Fixture data. Must be unmistakable. |

**This is the component family that replaces the legacy's demo-mode ambiguity.**
The legacy served seed content unlabeled so screens stayed populated
(MM-A03, archived). The design must make an unlabeled value impossible to render
— which means provenance belongs in the primitive that displays a value, not in
a decoration someone remembers to add.

Design question this raises, and the redesign must answer: how does a label stay
legible on a dense table where every cell needs one, without the labels becoming
the loudest thing on the page?

## 1.2 Failure states render truthfully

Architecture v1.1 §3.6 and §5.5. Each of these is a state the design must have a
treatment for — not an error toast, a *designed state*:

- "Travel estimate unavailable" — never a fabricated distance (N1)
- "Estimate quality: coarse" — the straight-line interim, visibly marked
- "Partial discovery: 3 of 5 sources" — partial results labeled partial
- "Draft is a deterministic template (AI unavailable)" — not silently different
- "Calendar unsynchronized" — never a silent ICS fallback shown as success
- "Rate limited — retry in 45s" — with the actual retry window
- "No data yet" versus "zero" — an empty feedback set is *unknown*, not 0%

That last one is subtle and the design has to hold the line on it. The domain
already returns `None` rather than `0.0` for an acceptance rate with no
feedback; a component that renders `None` as `0%` throws that away.

## 1.3 Route guards are user experience only

Architecture v1.1 §5.1. The API is authoritative. A guard exists so people do not
see doors they cannot open — never as a security control. Any design that implies
otherwise (a "secure area" affordance, a client-side permission check presented
as enforcement) is wrong.

## 1.4 No hard-coded identity, roles, or records

The legacy let a caller pick their role (`mock-login`, archived MM-A01) and
shipped `mockData.ts` and `mockProfilePhotos.ts`. None of that comes forward.
Role comes from the session; every record comes from the API.

## 1.5 Accessibility is WCAG 2.2 AA, verified

Keyboard, screen reader, contrast, focus. Not a review checklist at the end — an
automated a11y smoke test in CI (`.github/workflows/verify.yml` lists it under
before-live gates). A design that cannot pass it is not finished.

## 1.6 Four audiences, genuinely different needs

Administrator, coordinator, professional, student. The professional portal has an
obligation the others do not: architecture v1.1 §5.1 requires professionals be
able to **see and correct the availability and workload data used about them**.
The Engagement Load Index affects whether they get assigned, so a design that
shows them a score without a way to correct its inputs is not acceptable.

## 1.7 Jarvis is an accelerator, not a parallel system

Architecture v1.1 §5.4, when it arrives in R5. The conversational surface shows
the typed intent it derived (visible and editable before execution) and the
autonomy tier of each proposed action. Draft artifacts open in their **normal
editors**. Nothing executes from ambient conversation — every consequential
action shows the same confirmation UI the conventional screens use.

## 1.8 Times render in the event's own zone, with the zone named

ADR-0010. An event carries a UTC instant, an IANA zone, and a precision
(`exact` / `date_only` / `unresolved`).

- Render in the **event's** zone, never the viewer's and never the server's, and
  name the zone beside the time. A time without a named zone is a number that
  happens to have a colon in it.
- An event at `date_only` renders as a **date**. Collapsing it to midnight and
  rendering that is how a list comes to show events at 3 AM — which is what the
  19–20 August 2026 test log found (Fix #6).
- An event at `unresolved` cannot be matched or published, so it should not
  reach a list at all; if one does, it renders as unresolved, not as a guess.

## 1.9 Unknown is not zero, enforced by the value primitive

ADR-0011. A value with no evidence renders as `unknown` — never `0`, never `0%`,
never an em-dash styled to look like a measurement.

This is a **component**, not a habit. The test log found "Topic Relevance 0%" on
an event about AI, "Match Depth 0", and "Rest recommended: 0" beside a volunteer
the same screen had flagged as overloaded (Fix #8). Every one of those is a
missing value wearing a measurement's clothes, and no amount of reviewer
attention catches the next one. `smartmatch_domain.feedback.acceptance_rate`
already returns `None` rather than `0.0` for an empty set; the primitive is what
stops that distinction being thrown away at the last step.

This is **S2**, and it is held behind D-0 with the rest of the frontend.

## 1.10 Every aggregate has a drill-down

ADR-0011. Clicking a number returns exactly the rows it was computed from — the
same rows, from the same query, not a re-query with similar-looking filters. The
count of the result equals the number clicked.

The test log found a count of 15 that opened to 31 rows (Fix #12). This is the
one rule in ADR-0011 a test can check without a human reading a definition, so
it is the one the design must not make impossible: an aggregate rendered with no
affordance to open it cannot be checked by anyone, reviewer or test.

## 1.11 Action queue before statistics

On the coordinator and administrator home, what needs doing comes before how
things are going. Statistics are the second screenful.

**When n is small, name the people.** "3 volunteers over their load ceiling" is
a worse rendering than the three names, and an average over four data points is
a summary of nothing. This is Fix #13, and it is a constraint on the redesign
rather than the redesign itself.

---

# Part 2 — Open, and to be decided by the redesign

Engineering has no standing to decide these. They are recorded so the redesign
has a defined scope.

| # | Decision | Notes |
|---|---|---|
| D-1 | Design system: adopt, adapt, or build | The legacy used shadcn/ui. Upstream licensing must be confirmed before any component is reused (MM-F01). |
| D-2 | Visual language | Typography, color, spacing, density. Institutional brand constraints unknown — needs an owner at IA West. |
| D-3 | Provenance label treatment | See §1.1. The hardest visual problem here, because it touches every value. |
| D-4 | Information density | The control center has 13 views; a coordinator triaging exceptions and an administrator reviewing scenarios want very different densities. |
| D-5 | Portal navigation model | One shell with role-conditional navigation, or four distinct experiences. |
| D-6 | Empty, loading, partial, denied, stale, failed | Six states, every view. Currently undesigned. |
| D-7 | Responsive and device targets | **Partly settled.** Students check in from phones; coordinators work on desktops. Not the same problem. QR check-in (MM-F02) is the mechanism that produces attendance, and it is phone-first — so **mobile is a primary target for the student surface, not a responsive afterthought**. What remains open is the coordinator and administrator side. |
| D-8 | Charting approach | The legacy used Recharts. Needs revisiting against §1.1 — a chart of heuristic scores must say so. |
| D-9 | Rewards and points presentation | Depends on D6/D7 being answered at all. A progress line toward an unreachable reward is worse than no progress line — see [`docs/architecture/engagement-model.md`](../../docs/architecture/engagement-model.md) §4. |
| D-10 | Disclosure and peer visibility on the student surface | ADR-0014 fixes the *record*; how consent is asked for, and how a limited list explains itself, are undesigned. Policy is D8. |
| D-11 | The agenda view | `engagement-model.md` §5 rules out a month grid and specifies a time-ordered agenda. Its density, grouping, and region badges are open. |

## What "done" looks like for this document

This document is ready when it can answer, for someone building a new screen:

1. Which components do I use, and where do they live?
2. How do I render a value with its provenance?
3. What do the six non-happy states look like here?
4. How do I know this passes accessibility before I open a PR?

Until it answers those, `apps/web` stays empty.

---

## Sequencing once this is settled

From `docs/plans/remaining-foundation-r1-work.md`:

1. **W1** — scaffold React 18 + TypeScript + Vite
2. **W2** — generate the TypeScript client; add a drift check to CI
3. **W4** — build the provenance and truthful-state components **first**, before
   any screen that needs them. Built after, they get retrofitted, and retrofits
   get skipped.
4. **W3** — port presentational components (MM-F01), confirming licensing, and
   leaving the legacy's mock data behind
5. **W6** — accessibility tests in CI
6. **W5** — matching control center, once match runs exist (gate G1)

Note the ordering of W4 before W3 and W5. That is deliberate: the provenance
components are the ones enforcing §1.1, and everything built before them will
have to be revisited.
