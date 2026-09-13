# Engagement feed research — what to borrow from TikTok, and what to refuse

**Status:** research only. No source file changes. Closes no decision, and closes
none of **D-1..D-11**.

**Question asked:** the student portal should "gamify the scroll" so the platform
is more accessible and builds retention — how do TikTok and Instagram make
infinite scroll work, and what should we copy?

**Short answer:** copy the mechanics, refuse the endlessness. Every property that
makes those feeds *good* is available to a bounded feed; the endlessness itself is
the one property this product cannot have honestly, cannot have legally, and does
not need.

**Parent:** [`../2026-09-13-student-recommendation-program-plan.md`](../2026-09-13-student-recommendation-program-plan.md).

---

## 1. What actually makes those feeds work

It is not the infinity. Five mechanics do the work, and four of them are
independent of feed length.

**A seeded cold start.** TikTok's onboarding opens by asking users to select
interests, and tells them the feed improves with use. Spotify asks for artists and
genres; Pinterest combines onboarding interests with locale and popularity priors
plus content-embedding retrieval for new items. This is the standard answer to the
user cold-start problem, and the standard warning comes with it: ask too much at
signup and people skip or abandon.

**One item per viewport.** Every scroll is a single decision — attend or not —
rather than a comparison across a grid. It removes choice paralysis, and it is why
a feed feels lighter than a listing of the same items.

**The gesture never blocks.** TikTok pre-fetches roughly 10–20 items so the next
card is already there. Latency at the moment of the swipe is what breaks the
rhythm; nothing else about the design matters if that fails.

**Fast in-session adaptation.** The feed visibly changes within the session in
response to what you did, which is what makes the interaction feel like it is
about you.

**Unpredictability of content.** This is the variable-reward schedule, explicitly
compared in the literature to slot machines: the ratio of rewards "need not be
favorable, only unpredictable, because unpredictability sustains the search."

The first four are mechanics. The fifth is the one with an ethical question
attached, and §3 re-sites it.

## 2. Why the endlessness is wrong here — three independent reasons

**It would require fabricating depth.** A chapter runs a handful of events a week.
An endless feed has to pad, which means serving events the ranking already placed
last — presenting low-relevance items as recommendations. `ADR-0011` forbids
exactly this class of dishonesty: an unknown is never rendered as a zero, and an
omission is reported rather than hidden. There is no honest infinite feed over
twelve events.

**Accessibility is a legal mandate here, not a preference.** Cal Poly Pomona is a
CSU campus. CSU's standard is **WCAG 2.1 Level AA**, and the U.S. Department of
Justice's Title II final rule adopts WCAG 2.1 AA as the standard for web content
and mobile applications provided by state and local government entities. Infinite
scroll is a well-documented AA failure mode — an unreachable footer, keyboard
traps, and screen-reader disorientation with no stable end. `apps/web/DESIGN.md`
already sets a *higher* internal bar (WCAG 2.2 AA, keyboard-operable everything,
44×44 px targets, visible focus) and adds a rule that decides this on its own:
**no required information may depend on animation.**

**Bounded designs retain better.** Reported figures put ethical designs at ~75%
retention against ~65% churn for dark-pattern designs, and infinite scroll is named
among the patterns that "make it difficult for users to find a natural stopping
point," with documented anxiety, fatigue and guilt effects. Duolingo is the
standing counter-example that gamification without deception still works.

The Baymard finding is worth adding because it is about utility rather than
ethics: infinite scroll prevents users from finding specific items, comparing
options, bookmarking, sharing a listing URL, and returning to a previous position.
Every one of those is something a student picking events actually wants.

## 3. The borrow / refuse table

| Borrowed | Refused |
|---|---|
| Interest picker to seed the cold start | Endless depth; padding so the feed never ends |
| One event per viewport, CSS scroll-snap | Autoplay, and time-in-feed as a success metric |
| One-thumb actions in the bottom third | Variable-ratio reward scheduling as the engine |
| Pre-fetch so the gesture never blocks | Scroll streaks and login points |
| In-session re-ranking after a skip | Any number that looks like a match score |
| A declared exploration slot | Infinite recycling of already-skipped events |

### The variable reward, re-sited honestly

The unpredictability students respond to becomes **one Wildcard card per session,
visibly labelled as outside their declared interests**.

That is not the Skinner box with a nicer name, and the difference is worth being
precise about. A slot machine's unpredictability exists to sustain searching; the
Wildcard exists to solve a real problem the recommender has. A content-based
ranker over declared interests collapses into a filter bubble — the
over-specialization the recommender-systems literature describes, where a system
"severely limits users' exposure to diverse content and reduces serendipitous
discovery." The standard answers are an explicit explore/exploit trade-off and
diversity re-ranking such as Maximal Marginal Relevance. One exploration slot is
the cheapest version of that, and it also happens to feel good.

Three honesty requirements follow, and they are what separate this from the
pattern it resembles:

1. **It says in the payload that it is a wildcard**, not only in the UI, so a
   client cannot quietly present it as a recommendation.
2. **It is drawn only from scorable events.** Promoting an *unscorable* event as a
   wildcard would launder an unknown into a recommendation.
3. **It is `null` when the pool outside the ranked list is empty**, never a
   duplicate of something already shown.

### Gamification that mints nothing

The obvious move — points for scrolling, a daily streak, a login bonus — is
unavailable, and for a better reason than taste. **`ADR-0013` makes points derive
from recorded attendance and nothing else**: every `point_ledger_entry` names the
`attendance_record` it derives from, there is no discretionary grant, and a
balance is a fold. The existing prototype prompt pack already excludes "points for
logging in / referrals / streaks" by name.

So the gamification is in the *motion and the progress*, not in a second currency:
snap, one-thumb decisions, a progress rail through a finite set, and the
server-authored progress toward the nearest **reachable** reward that
`engagement-model.md` §4 already specifies. Where no reward is reachable, the
honest render is the **absence** of a progress line, not a line toward something
unreachable.

## 4. The success metric, fixed before anything is built

**Registrations per active student, and registration→attendance conversion.**

Not time in feed, not scroll depth, not sessions. This is written down first
because the mechanics in §3 are the mechanics that optimize for attention, and a
team that ships them without naming the target will get attention. The chapter
does not want attention; it wants students in rooms.

`pipeline_record` already measures the second half — Attended cites a real
`attendance_record` or is refused — so the metric is answerable from evidence the
platform keeps rather than from a new counter.

## 5. What this means for the interface

- A **bounded window**, stated in the payload as a real interval rather than
  implied by a label.
- A **real end card**. Reaching the end of the week is a completion, not a dead
  scroll.
- **A number that is never shown.** Relevance is explained in one sentence and
  evidenced by which interests matched; ADR-0016 Proposal 8 forbids the
  percentage, and the strictest reading for a student surface omits the float
  entirely, since a `0.0–1.0` value in a payload is one `Math.round(x*100)` from
  the forbidden thing in a client the backend does not control.
- **`prefers-reduced-motion` removes the motion and none of the information.**
- **The month calendar stays.** Customer §15 asks for it at the bottom of the
  Events page and `OQ-CBA-020` makes its cells deliberately non-interactive. The
  feed is an addition, not a replacement.
- **Do not call it a discovery feed.** `DESIGN.md` bans discovery and crawler
  language on visible paths, and `components/DiscoveryFeed.tsx` and
  `CrawlerFeed.tsx` already exist as exactly what that rule prohibits.

## 6. Sources

- [How TikTok recommends videos #ForYou](https://newsroom.tiktok.com/en-us/how-tiktok-recommends-videos-for-you)
- [How TikTok Keeps You Hooked and Perpetually Scrolling](https://freedom.to/blog/how-tiktok-keeps-you-hooked-and-perpetually-scrolling/)
- [Design TikTok For You Feed — walkthrough](https://systemdr.systemdrd.com/p/design-tiktok-for-you-feed-walkthrough)
- [TikTok's addictive, activation-focused user onboarding](https://goodux.appcues.com/blog/tiktok-user-onboarding)
- [Infinite Scroll UX — Smart Interface Design Patterns](https://smart-interface-design-patterns.com/articles/infinite-scroll/)
- [Choosing the right scrolling design pattern for better UX](https://blog.logrocket.com/ux-design/creative-scrolling-patterns-ux/)
- [What is Infinite Scrolling? — Interaction Design Foundation](https://ixdf.org/literature/topics/infinite-scrolling)
- [Warmer for Less: cost-efficient cold-start recommendations at Pinterest](https://arxiv.org/html/2512.17277)
- [The cold start problem in recommender systems](https://www.freecodecamp.org/news/cold-start-problem-in-recommender-systems/)
- [Exploration vs. exploitation in recommendation systems](https://www.shaped.ai/blog/explore-vs-exploit)
- [Diversity in recommendations — Maximal Marginal Relevance](https://medium.com/data-science-collective/diversity-in-recommendations-maximal-marginal-relevance-mmr-0e7840c9399e)
- [Infinite Scrolling, Finite Satisfaction (arXiv 2408.09601)](https://arxiv.org/html/2408.09601v1)
- [The dark side of gamification: ethical challenges in UX/UI design](https://medium.com/@jgruver/the-dark-side-of-gamification-ethical-challenges-in-ux-ui-design-576965010dba)
- [The impact of dark patterns in app design on users](https://appscrip.com/blog/impact-of-dark-patterns-in-app-design/)
- [CSU Accessibility](https://www.calstate.edu/Pages/accessibility.aspx) and [CSU ATI — 2026 Title II update](https://ati.calstate.edu/policy/2026-title-ii-update)
