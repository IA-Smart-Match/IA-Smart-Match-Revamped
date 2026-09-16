# Class exercise — requirements for the Spring 2027 AI in Marketing module

**Last updated:** 2026-09-16
**Source:** Ann Wang, "Smart Match — Marketing Class Exercise and Minimum Build
Requirements", 15 September 2026, and her email of the same date to the team.
**Authority:** this document is the authority for the **class-exercise product
scope** (`ProductScope.CLASS_EXERCISE`, ADR-0019). It amends nothing in
[`cba-smart-match-customer-requirements.md`](cba-smart-match-customer-requirements.md),
which remains the authority for the CBA platform scope. The two scopes share
the domain matching mechanism and share no data, route, role, or table.
**Parallel tracks:** Ann's document defers the "CBACH project" (real students
matched to real events) to a 20 November 2026 decision for *her* deliverable.
The CBA platform track (student engagement, retention, speaker-to-event
matching) is a separate stakeholder commitment and continues on its own plan.
This document does not pause it.

## Vocabulary

Ann's document avoids the bare word "students". This document keeps her terms:

- **The team** — Chau, Danny, Janice, Justin.
- **Class participants** — students in Dr. Lin's AI in Marketing course who use
  the app in Spring 2027.
- **The 300 profiles** — the made-up records inside the app. Every row is
  fictional; no real student appears.
- **Exercise events** — "Northline Analytics" (round one) and "Harbor Consumer
  Brands" (round two), a few weeks apart in the story.

## What class participants must be able to do

Act as the person promoting a campus career event with 60 seats, 8 sign-ups,
and time to personally invite only 30 people. Choose whom to invite with the
tool, see what happened, ask the profiles for more information, refresh, and
run a second event. Leave remembering one thing: AI helps a marketer use
customer information to decide whom to reach, but the marketer still decides
what information matters, what message fits, and who is being overlooked.

## Ann's stated keeps

From her email: "The matching engine, the saved settings, the dashboard, and
the back end you are rewriting are exactly what we build on. What changes is
who gets matched to what, not how." Keep: the matching engine with adjustable
weights, the ranked list with a reason next to each name, and the results
screen.

## Minimum build (transcribed from Ann's build table)

"Required" must work for the exercise to run. "If time allows" makes it better.
"Not now" is out of scope for this deliverable so nobody spends time on it.

| Area | Required | If time allows | Not now |
|---|---|---|---|
| Getting in | No login. A public web address. Each browser tab keeps its own work; a team enters its team number (1–6) so its saved runs are labeled. An instructor page behind a simple passcode can open any team's saved runs, unlock results, and set the invite limit. | — | Accounts and roles; the four user types; invitation-only speaker accounts. |
| Data | Load the made-up student body Ann provides as a spreadsheet, and let the instructor replace it from the instructor page. About 300 profiles and 12 events (10 past events for attendance history plus the 2 exercise events). Every profile has a made-up name, a major, and a year; about a third have attended one or more past events; about 70 have a completed profile card (stated interests and career goals), and of those a good share have interests that do not match Northline. Every profile also carries a hidden "true" set of interests that the app never shows and never uses for matching; only the results rule uses it. | — | Any connection to university records, Handshake, or real sign-ups; any real student data, even with names changed. |
| How much we know | Next to every profile, a simple marker: major only; major plus events attended; completed card. The "who is on the list" table also counts the list by these three groups. | — | — |
| Matching | Match profiles to one chosen event using four adjustable factors, labeled in plain words: same major; said they are interested in this topic; career goal fits this event; went to similar events before (topics of past events attended overlap this event's topics). Major is always available. The other three count only for profiles that have that information; for everyone else the reason line says so ("same major; nothing else on file"). Ties are broken in a fixed order: more information on file first, then year (seniors first), then a fixed random order that never changes; the reason line says "tied on major; ordered by year." Ranked list capped at the invite limit (30 by default). A team can save up to three named settings per event and view any two side by side with shared names highlighted. | — | Machine-learning matching; speaker-to-event matching; checking calendars. |
| Who is on the list | For the current list, a small table: count by major, by year, and by "how much we know" group, next to the same counts for all 300. | A one-line notice when a major or year that exists among the 300 has nobody on the list. | — |
| Download | Download the current list with reasons as a spreadsheet file. | — | Writing messages in the app; AI writing in the app; sending email. |
| Results lock | Results cannot be run until the instructor unlocks them for that event. Each team gets one results run per event. | — | — |
| Comparison | The results screen always shows the "email everyone" result (all 300 contacted) next to the team's result, and in round two the team's own round-one result as well, plus seats still empty. | — | — |
| Simulated results | A hidden rule that turns a list into results (invited, signed up, attended). It uses each profile's hidden true interests, not what the app has on file. (1) A profile is more likely to sign up when its true interests and career goal match the event. (2) Profiles that attended many past events are only a little more likely to sign up. (3) Same major alone gives only a small lift. (4) A small element of chance, fixed for each team so a repeated run gives the same result. (5) A reset per team that does not touch other teams. The rule is written in plain words in the code and shared with Ann and Dr. Lin before the practice run. | Results as a simple bar chart readable from the projector. | Real notifications or reminders; message quality changing results. |
| Asking for more | Before the refresh, a team picks one of three ways to ask the profiles it invited to complete a card. Each has a set outcome, written in the code and shared with Ann: promise better recommendations (about 30 percent of invited profiles without a card complete one); small reward (about 55 percent); required (about 80 percent, but about 15 percent of those without a card stop opening messages and never sign up in round two). Numbers are illustrative; Ann confirms them before the practice run. | A one-screen mock-up of the "five quick questions" card for the instructor to show. | Real profile cards for real people. |
| Profile refresh | A per-team button, available after the team has chosen how to ask: everyone who attended Northline picks up its topics as "went to similar events"; the chosen share of invited profiles complete a card copied from their hidden true interests; markers update. An instructor button runs every team's refresh at once. Each team's refresh changes only that team's copy of the 300 profiles. | — | Refresh from real behavior. |
| Points | Not required. | A points counter per profile that rises with attendance and card completion. | Reward catalog, redeeming points, faculty extra credit. |
| Hosting and backup | A stable web address that loads in under 5 seconds in Chrome on classroom computers. A spreadsheet backup for Session 1 (Ann builds it). Session 2 depends on the site; there is no backup for the simulation. | — | Mobile app; more CPP colors and styling than already exist. |

## Who does what

- **Ann** — confirms the spring plan with Dr. Lin by Oct 2; writes the case and
  the background note; provides the data file (20-row sample with final column
  names on **Sept 18**, full 300-row file on **Sept 25**); provides the four
  participant forms; sets the three "asking for more" percentages; attaches the
  open license (the app's opening screen shows the same license line once she
  provides it); builds the Session 1 backup spreadsheet.
- **Chau** — the four matching factors; the tie-break; the invite limit and
  saved settings; the results rule (written in plain words, shared with Ann and
  Dr. Lin before the November practice run); the "asking for more" outcomes.
- **Danny** — no-login per-team workspaces that survive reload; the instructor
  page (open any team's runs, unlock results, change the invite limit, replace
  the data file, refresh all); data-file loading with a plain error when a
  column is missing; the results lock and one-run rule; the refresh; download
  and per-team reset; hosting at a stable address.
- **Janice** — the "how much we know" marker; the "who is on the list" table;
  the side-by-side view; the "asking for more" choice screen (and, if time,
  the five-questions mock-up); the results screen. Everything readable from the
  projector at classroom distance.
- **Justin** — testing against the build table row by row (two teams at once
  do not see each other's lists; reload keeps saved settings; the lock blocks a
  second run; reset clears one team only; test profiles with known right
  answers); a short list of what was tested and what failed before Oct 16; the
  one-page plain-words write-up of the results rule, the three "asking for
  more" choices, and the refresh.
- **Dr. Lin** — names the spring week, one or two sessions, class size; joins
  one practice run in November.

## Timeline (Ann's planning markers; she will say which ones matter)

| Date | Milestone |
|---|---|
| Fri Sept 18 | Team confirms scope. Ann sends the 20-row sample with final column names. |
| Fri Sept 25 | Ann sends the full 300-row file. |
| Fri Oct 2 | Matching with the four factors, tie-break, cap, saved settings, markers, and the list table working on the site with the full data. |
| Fri Oct 16 | Results with lock, "email everyone" comparison, repeatable runs, reset, "asking for more", per-team refresh, round two, and download working. Ann runs both sessions and sends a problem list. |
| Fri Oct 30 | Problems fixed. |
| Week of Nov 9 | Practice run with Ann, Dr. Lin, and five or six volunteers. Hidden rule and the three percentages reviewed. |
| Fri Nov 20 | Fixes done. Team review. This version becomes the fall deliverable. Ann's decision on her CBACH follow-on. |
| Spring 2027 | Exercise runs. Small fixes only; no new features. |

## Phase two (logged, not built)

The team's proposed speaker workflow (Speaker Connector curates speakers;
speakers create accounts by invitation only; Event Host creates events and runs
matching over the speaker database) is, in Ann's words, "cleaner than what we
have" and "phase two". It is logged in [`../plans/backlog.md`](../plans/backlog.md).

## Where the rest lives

- Architecture: [ADR-0019](../architecture/decisions/ADR-0019-class-exercise-scope-shares-the-matching-mechanism.md).
- Design spec: [`../superpowers/specs/2026-09-16-class-exercise-design.md`](../superpowers/specs/2026-09-16-class-exercise-design.md).
- Open questions for this scope: [`../plans/open-questions/class-exercise-open-questions.md`](../plans/open-questions/class-exercise-open-questions.md).
