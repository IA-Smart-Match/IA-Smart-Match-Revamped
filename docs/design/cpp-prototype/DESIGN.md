# Smart Match CPP — presentation mockups: design contract

**Status:** Proposed. Docs and static mockups only; no app code changes with this file.
**Scope:** three static mockups of Dr. Ann Wang's clickable prototype, for the CBACH advisory board on Thursday 2026-10-08.
**Source (never edit):** [`source/SmartMatch_CPP_Prototype_10062026_1.html`](source/SmartMatch_CPP_Prototype_10062026_1.html), [`source/SmartMatch_CPP_Prototype_README_10062026.md`](source/SmartMatch_CPP_Prototype_README_10062026.md), [`source/PROVENANCE.md`](source/PROVENANCE.md).
**Reference screenshots of her prototype:** [`reference/`](reference) (32 PNGs, 1440×900 and 390 wide, captured 2026-10-06 in headless Chromium).
**Shared data and matching logic:** [`shared/data.js`](shared/data.js) (generated from her file; see section 3).
**Related house system:** [`../class-exercise/DESIGN.md`](../class-exercise/DESIGN.md) (the shipped class exercise). This file borrows its spacing scale, inline-confirm and `aria-disabled` conventions. It does **not** inherit its "counts, never scores" rule: Ann's prototype shows "match 6 of 10" and a readiness percentage on purpose (see Appendix B, OQ-3).
**Last updated:** 2026-10-06

How to use this file:

- **Builders:** Part 1 is the same for all three mockups. Build from sections 2 and 3 without opening her HTML. Part 2 has one section per direction; follow only yours.
- **Auditor:** run section 11 against each mockup. Every item is pass or fail.
- **Precedence:** her README's honesty rules (section 1.3), then Part 1, then the direction's section in Part 2. A direction may restyle anything else. It may not change a word in section 2, a number in section 3, re-tone an honesty component (section 7.4), or drop an element from a screen.

---

# Part 1 — Shared contract

## 1. Purpose, audience, setting

### 1.1 What this is

Ann sent a clickable front end of where Smart Match is heading. Her note: "see the mockup of the front end by me for your kind reference. Feel free to use it and modify it from your end." The team answers with three mockups of the **same content** in three visual and interaction directions, so she and the owner can pick what the presenters show.

### 1.2 The room

| Fact | Consequence for design |
|---|---|
| Thursday 2026-10-08, CBACH advisory board, non-technical | Plain words; no jargon in any new string; every screen explains itself in one sentence |
| About 15 minutes of demo on the front end, then Q&A | 9 stops (section 2.1), about 100 seconds each. Nothing may make a presenter wait |
| Two student presenters: Chau and Janice | A presenter guide equal to Ann's (section 2.12) is in every mockup |
| Projected in a lit room, read from the back row | Light theme by default; type and contrast floors in sections 5 and 6 |
| Presenter-driven from a classroom laptop, possibly with a clicker, possibly with no internet | Opens by double-click, no network, PageDown and PageUp move between stops from any control except a text input (section 7.16) |
| Q&A may send a board member's question to any screen | Any screen is reachable in at most two actions from any other; off-script clicks never break state |

### 1.3 Honesty rules (from Ann's README; non-negotiable)

| # | Rule | How every mockup carries it |
|---|---|---|
| H1 | Presented as the design for the next phase, not finished software | The marker "Design for the next phase — made-up data" (N1) is visible on every screen, in every state, at every width. It is never dismissible |
| H2 | Each screen keeps its "working / planned" label | Every screen's status label (section 2.2) is visible without scrolling at 1440×900, with her exact words. The check-in card keeps its own "Planned" label |
| H3 | The profile interview and the CBACH assistant bot are scripted, not live AI | The line "Scripted for this demo. Not a live AI." (N2) is pinned at the top of both transcripts and stays visible while the transcript scrolls. No typing dots, no "thinking" state, no text that streams in character by character (section 8.4) |
| H4 | Only the 300 made-up profiles; never real student data | All people come from `shared/data.js`. No field anywhere accepts a file. Typed text is never stored beyond the page's own demo state |
| H5 | The six readiness markers are a draft | The label "Planned · draft markers" and the closing line "Draft markers for discussion…" stay on the readiness screen |
| H6 | Nothing is saved; no database | No network request of any kind. Buttons that would send something show her sentence about the full version |

## 2. Content inventory

Default is Ann's wording, verbatim. "Verbatim" means the same characters, case and punctuation. Styling may not truncate, re-case, split or re-word a string. Two glyphs in her strings are icon slots, not characters: `→` (render an arrow-right icon, `aria-hidden`) and `✓` (render a check icon, `aria-hidden`). Curly or straight quotes and apostrophes are equivalent.

### 2.1 Portals, screens and demo order

| Stop | ID | Portal | Screen (menu label) | Screen title (`h1` of the screen) | Presenter | Status label | Kind |
|---|---|---|---|---|---|---|---|
| 1 | `entry` | — | Entry: three doors | Smart Match CPP | Chau | none (marker N1 and the demo line carry it) | — |
| 2 | `interview` | Student | Activate my profile | Activate my profile | Chau | Planned · scripted for this demo | planned |
| 3 | `recs` | Student | Events for me | Events picked for Grace | Chau | Matching works in class version | working |
| 4 | `readiness` | Student | My readiness | Grace's career readiness | Janice | Planned · draft markers | planned |
| 5 | `growth` | Student | My growth | Grace's career growth record | Janice | Planned | planned |
| 6 | `overview` | Career Hub | Term overview | Term overview | Janice | Partly built | partly |
| 7 | `records` | Career Hub | Student records | Student records | Janice | Working in class version | working |
| 8 | `match` | Career Hub | Match students to an event | Match students to an event | Chau | Working in class version | working |
| 9 | `talk` | Partner | My talk | Your talk: Northline Analytics | Chau | Partly built | partly |

Presenter split per her README: Chau has Student interview, Events for me, Match students to an event, Partner portal. Janice has My readiness, My growth, Career Hub overview and student records. The entry is Chau's (presenter guide).

### 2.2 Portal chrome (all portal screens)

| Element | Student | Career Hub | Partner |
|---|---|---|---|
| Portal name | Student portal | Career Hub portal | Partner portal |
| Identity line | Signed in as Grace Delgado · Accounting · Junior | CBA Career Hub (CBACH) staff | Dana Whitfield · Senior Data Lead, Northline Analytics · CPP alumna, 2014 |
| Menu items, in order | Activate my profile · Events for me · My readiness · My growth | Term overview · Student records · Match students to an event | My talk |
| Default screen | Activate my profile | Term overview | My talk |
| Nav landmark name | Student portal | Career Hub portal | Partner portal |

Also on every portal screen: the Cal Poly Pomona logo (`SMC.LOGO`, alt text `Cal Poly Pomona`), the button `Switch portal` (returns to the entry), and the floating button `Presenter guide` / `Hide presenter guide`. Page `<title>`: `Smart Match CPP`.

Status label kinds (the label is one component, section 7.4):

| Kind | Her strings that use it | Her colours |
|---|---|---|
| working | "Working in class version", "Matching works in class version" | green on green-soft |
| partly | "Partly built" | blue on blue-soft |
| planned | "Planned", "Planned · scripted for this demo", "Planned · draft markers" | gold-ink on gold-soft |

### 2.3 Entry (`entry`)

| Element | Exact copy |
|---|---|
| Logo | image, alt `Cal Poly Pomona` |
| Title | Smart Match CPP |
| Lede | A student-built app for the CBA Career Hub. Events find the right students, students build a record of their career growth, and industry partners see who they reached. |
| Door 1 eyebrow / title / body / action | For students / Student portal / Activate your profile through a short AI interview, get events picked for you, and see your growth record. / Enter as Grace Delgado → |
| Door 2 eyebrow / title / body / action | For CBACH staff / Career Hub portal / Student records, matching students to an event, and term reports for the college. / Enter as Career Hub staff → |
| Door 3 eyebrow / title / body / action | For industry partners / Partner portal / See who came to your talk, what students asked, and how to stay involved. / Enter as Dana Whitfield → |
| Demo line | Concept prototype. All students, partners, events and numbers are made up; the 300 student records come from the class exercise file. |

Each door is one button; the whole card is the target. Her eyebrows are drawn uppercase by CSS; the strings are sentence case as written above.

### 2.4 Student · Activate my profile (`interview`)

| Element | Exact copy |
|---|---|
| Title | Activate my profile |
| Description | The app already has Grace's college record. A short AI interview fills in the rest of her profile card, so event suggestions fit her, not just her major. |
| Status label | Planned · scripted for this demo |
| Transcript speaker label (assistant turns) | Smart Match assistant |
| Scripted line, pinned (new, N2) | Scripted for this demo. Not a live AI. |
| Free-text field: hidden label / placeholder / button | Type an answer / Or type your own answer… / Send |
| Multi-select confirm button | Done |
| After the interview | Interview finished. + button `Start over` |
| Profile card header | avatar `GD` · Grace Delgado · Profile card |
| Card group 1 label | From college records (already on file) |
| Card group 1 rows | Major: Accounting · Year: Junior · Events: Brand Building at a Streaming Studio; Cybersecurity and Cloud Jobs Q&A (one per line) |
| Card group 2 label | From the interview |
| Card group 2 rows | Interests: chips of short topic names, or `Not yet` · Next step: the goal, or `Not yet` |
| Card footnote | Later: students can answer by voice or by typing. |
| Toast on finishing | Profile card saved. 20 points added. |

**The scripted turns.** Bold spans are bold in her file.

| Turn | Assistant says | Reply options |
|---|---|---|
| 1 | Hi Grace! I can see from your college record that you're an Accounting junior, and you came to **Brand Building at a Streaming Studio** and the **Cybersecurity and Cloud Jobs Q&A**. What made you go to the cloud jobs session? | I'm curious about tech jobs · A friend brought me · My professor offered extra credit · or free text |
| 2 | Thanks. Which industries would you like to hear more about? Pick as many as you like. I've pre-selected ones that fit what you've told me and the events you went to. | 13 toggle chips, in this order: Accounting · Consulting · Entertainment · Entrepreneurship · Finance · Government · Healthcare administration · Hospitality · Marketing · Retail · Sales · Supply chain · Technology. Pre-selected: Technology and Entertainment. Then `Done`. No free text on this turn |
| 3 | Got it. What would you like your next step to be after graduation? | Accounting or audit role (CPA path) · Data, analytics or IT role · Finance or real estate role · Graduate school · Not sure yet · or free text |
| 4a (goal is Undecided) | That's very common for juniors. You picked consulting and technology among your interests. Would you like me to suggest events that help you compare consulting and data roles? | Yes, help me compare · No thanks · or free text |
| 4b (any other goal) | Great, I'll look for events that fit that goal. One last thing: is it OK to suggest events outside the Accounting department? | Yes · Only accounting events · or free text |
| 5 | All set. Your profile card is filled in on the right. You can change it any time, and each event you attend will keep it up to date. Ready to see the events I picked for you? | Show my events · or free text |

Student turns show the chosen option's text. On turn 2 the student turn is the selected short names joined with ", " in the order they were selected (guided path: `Technology, Entertainment`), or `None of these` when nothing is selected.

**Behaviour, exactly** (turn numbers as above):

```js
// Turn 1: any answer advances. If it matches, Technology is added to the picks.
/tech|data|cloud|cyber|curious/i            // -> picks.add("Technology / information systems")
// Turn 2: on arrival, picks gains Technology and Entertainment (in that order, if absent).
//   Chips toggle picks. The profile card's Interests row updates on every toggle.
// Turn 3: goal = the GOALTOPIC key equal to the answer (case-insensitive); otherwise
/data|analytic|it\b/i                       // -> "Data, analytics or IT role"
/account|audit|cpa/i                        // -> "Accounting or audit role (CPA path)"
//   otherwise "Undecided". FIX F2 (section 3.7): the answer "Graduate school" stores "Graduate school".
// Turn 4a: if the answer matches, goal becomes "Exploring consulting or data roles".
/yes|compare/i
// Turn 4b: no effect on data (her code ignores the answer).
// Turn 5: any answer finishes: interests = picks, viaAI = true, 20 points once,
//   toast, then go to "Events for me".
```

- The card's "Next step" row shows `Not yet` until turn 3 is answered. The goal "Exploring consulting or data roles" is displayed as `Undecided · exploring consulting or data roles`. Other goals display as stored.
- `Start over` clears the transcript, picks, interests, goal and `viaAI`, and returns to turn 1. It does not take the 20 points back, and they are not awarded twice.
- **Guided demo path (presenter guide):** I'm curious about tech jobs → Done → Not sure yet → Yes, help me compare → Show my events. It leaves Grace with interests Technology and Entertainment, and the goal "Exploring consulting or data roles". Every test vector in section 3.5 assumes this path.

### 2.5 Student · Events for me (`recs`)

| Element | Exact copy |
|---|---|
| Title | Events picked for Grace |
| Description, first sentence | Events come to the student, each with a plain reason. |
| Description, second sentence (before interview) | Right now the app only knows her major and past events. |
| Description, second sentence (after interview) | These use her profile card. |
| Status label | Matching works in class version |
| Callout (before interview only) | Finish the short interview to get better suggestions. + button `Activate my profile` (goes to the interview) |
| Event row | date tile (day number over month, e.g. `4` / `Mar`) · title · meta line `{host} · {when} · 60 seats` · reason chip `Why you: {reason}` · button `Register` · `match {total} of 10` |
| Reason when total is 0 | open to all students |
| Button after registering | Registered ✓ (gold fill; pressing again does nothing) |
| Toast on registering | Registered. 10 points added. |
| Check-in card (hidden until the first registration) | sample code image, accessible name `Sample check-in code` · label `Check-in code` · `{title} · {when}` of the most recently registered event · Scanned at the door. Attendance goes on her record and points are added. Sample code only. · status label `Planned` |
| Points block (inside the check-in card) | label `Career points` · the number · Points exist in the early version |

Three events are shown: the top three of the five upcoming events by `SMC.rankEvents(grace)`. The reason uses `SMC.whyYou(result)`, which rewrites three phrases for the student's eyes: "said they're" → "you said you're", "career goal fits" → "fits your next step", "same major" → "popular with your major".

Rows on the guided path (must match exactly):

| State | # | Date tile | Title | Meta | Why you | Match line |
|---|---|---|---|---|---|---|
| Before interview | 1 | 19 Nov | Audit Season, Up Close | Ledger & Moss LLP · Thu Nov 19, 2026 · 60 seats | popular with your major | match 3 of 10 |
| Before interview | 2 | 5 Nov | Consulting Case Night | Westbridge Advisory · Thu Nov 5, 2026 · 60 seats | went to 1 similar event | match 1 of 10 |
| Before interview | 3 | 12 Nov | The Business of Streaming | Lumen Studios · Thu Nov 12, 2026 · 60 seats | went to 1 similar event | match 1 of 10 |
| After interview | 1 | 4 Mar | Northline Analytics: Behind the Business | Northline Analytics · Thu Mar 4, 2027 · 60 seats | you said you're interested in technology; fits your next step; went to 1 similar event | match 6 of 10 |
| After interview | 2 | 12 Nov | The Business of Streaming | Lumen Studios · Thu Nov 12, 2026 · 60 seats | you said you're interested in entertainment; went to 1 similar event | match 4 of 10 |
| After interview | 3 | 5 Nov | Consulting Case Night | Westbridge Advisory · Thu Nov 5, 2026 · 60 seats | fits your next step; went to 1 similar event | match 3 of 10 |

### 2.6 Student · My readiness (`readiness`)

| Element | Exact copy |
|---|---|
| Title | Grace's career readiness |
| Description | Points show effort. Readiness shows how many success markers she has reached, and confirmed steps count double so it can't be raised by self-checks alone. |
| Status label | Planned · draft markers |
| Ring | `{pct}%` over `career ready`, with a gold mark at the target for her year |
| Tile 1 | `{pct}%` · readiness now |
| Tile 2 | `60%` · target for a junior (gold mark) |
| Tile 3 | `{points}` · career points |
| Callout, bold lead (gap ≤ 0) | On track for your year. |
| Callout, bold lead (gap 1–20) | A little behind for a junior. |
| Callout, bold lead (gap > 20) | Behind for a junior, and that's fixable. |
| Callout, rest | Next step: {step}. {note} + button `Go` |
| Next step, before interview | Finish your profile interview · Adds about 8% and 20 points · `Go` opens the interview |
| Next step, after interview | Sign up for a resume workshop · The Career Hub can then review your resume · `Go` opens Events for me |
| Next step, third variant (unreachable in her code; keep the string for the port) | Book a practice interview · Interview ready is your lowest marker |
| Help panel avatar / heading | `CB` / Need help with any marker? The CBA Career Hub (CBACH) is here. |
| Help panel body | The assistant bot (AI) answers quick questions any time. CBACH advisors, real people on the Career Hub staff, answer messages and meet with you to review resumes, run practice interviews and help you choose a direction. |
| Help group 1 label / buttons | Help yourself, any time / `Chat with the CBACH assistant bot` · `Career Hub digital resources` |
| Help group 2 label / buttons | Talk to a person / `Message a CBACH advisor` · `Book a 30-minute appointment with a CBACH advisor` |
| Closing line | Draft markers for discussion. If the college has official Career Success Markers, the names here should match them. Readiness is private to the student and her advisor unless she chooses to share it. |
| Toast on ticking a self-check | Self-check saved. 5 points added. |

The four help buttons each toggle one panel below the help panel; pressing the open one closes it; only one is open at a time.

**Panel: assistant bot** (`Chat with the CBACH assistant bot`)

| Element | Exact copy |
|---|---|
| Panel label | CBACH assistant bot (AI) · for quick questions |
| Speaker label (bot turns) | CBACH assistant bot · AI |
| Scripted line, pinned (new, N2) | Scripted for this demo. Not a live AI. |
| First bot turn (always present) | Hi Grace! I'm the CBACH assistant bot, an AI that answers quick questions. For advice on your plans, you can message or book a CBACH advisor. |
| Suggested questions (chips) | Where is the resume template? · How do I get my resume reviewed? · What counts as an employer event? · Talk to a person |
| Field: hidden label / placeholder / button | Ask the assistant bot / Ask a quick question… / Send |
| Footnote | The bot answers quick questions. For advice, it sends you to a CBACH advisor. In the full version these connect to the Career Hub's real booking, messaging and resource pages. Shown here as a demo. |

Bot answers. The first matching rule wins, tested in this order against the question text:

| # | Rule (case-insensitive) | Answer | Then |
|---|---|---|---|
| 1 | contains `template` or `resume guide` | The resume guide and templates are in Career Hub digital resources. Pick the accounting or general business template. | — |
| 2 | contains `review` | A CBACH advisor can review your resume in a 30-minute appointment. Bring your latest version. | booking button |
| 3 | contains `employer event` or `count` | Info sessions, industry panels, career fairs and employer talks all count. You have 2 so far, which meets the networking step. | — |
| 4 | contains `person`, `human`, `advisor` or `talk` | Sure. You can message a CBACH advisor or book a 30-minute appointment. | booking button |
| 5 | anything else | I can help with quick questions about events, resources and your readiness card. For this one, a CBACH advisor is the best person to ask. | booking button |

The booking button inside a bot turn reads `Book a 30-minute appointment with a CBACH advisor` and opens the booking panel. The link `Ask the assistant bot` on a marker card opens the bot panel and appends, with no student turn: You're looking at **{marker name}**. I can point you to resources, or help you book a CBACH advisor.

**Panel: message an advisor** (`Message a CBACH advisor`)

| Element | Exact copy |
|---|---|
| Panel label | Message a CBACH advisor (a person on the Career Hub staff) |
| Field label | Your message |
| Pre-filled text | Hi, could someone review my resume? I'm an accounting junior interested in data and consulting roles. |
| Checkbox (ticked) | Share my readiness card with the advisor so they can see where I am |
| Button | Send message |
| On send | Sent. A CBACH advisor usually replies within one business day. (the panel then closes) |
| Footnote | Messages go to Career Hub staff, not to the bot. In the full version these connect to the Career Hub's real booking, messaging and resource pages. Shown here as a demo. |

**Panel: book an appointment** (`Book a 30-minute appointment with a CBACH advisor`)

| Element | Exact copy |
|---|---|
| Panel label | Book a 30-minute appointment with a CBACH advisor (a person on the Career Hub staff) |
| Slots (three chips) | `Mon Oct 12 · 10:00 am` / `Tue Oct 13 · 2:30 pm` / `Thu Oct 15 · 11:00 am` |
| On choosing a slot | Booked: {slot} with a CBACH advisor. A reminder will be sent. |
| Footnote | In the full version these connect to the Career Hub's real booking, messaging and resource pages. Shown here as a demo. |

**Panel: digital resources** (`Career Hub digital resources`)

| Element | Exact copy |
|---|---|
| Panel label | Career Hub digital resources |
| Chips | Resume guide and templates · Practice interview tool · LinkedIn profile checklist · Workplace ethics scenarios · Career exploration guide · Internship listings on Handshake |
| On choosing a chip | Opens: {resource} |
| Footnote | In the full version these connect to the Career Hub's real booking, messaging and resource pages. Shown here as a demo. |

**The six draft markers.** Each card: marker name, three progress dots (third dot gold when on), three steps each with its level, then two links: the resource name (message: `Opens the Career Hub page: {resource}`) and `Ask the assistant bot`.

| Marker | Step 1 — "I checked myself" | Step 2 — "I did it" | Step 3 — "Someone confirmed it" | Resource link |
|---|---|---|---|---|
| Resume ready | I have a one-page resume for my field | Attended a resume workshop | Resume reviewed by the Career Hub | Resume guide and templates |
| Interview ready | I feel confident answering common interview questions | Completed a practice interview | Rated ready by staff or a speaker | Practice interview tool |
| Networking ready | My LinkedIn profile is complete | Attended 2 or more employer events | Follow-up conversation with a speaker or alum | LinkedIn profile checklist |
| Professional ethics ready | Answered the workplace scenarios check | Attended a professional ethics session | Signed off by an instructor or the Career Hub | Workplace ethics scenarios |
| Career direction | Profile card completed | Career goal stated | Met with a career advisor | Career exploration guide |
| Work experience | Listed relevant experience | Internship, job or project recorded | Confirmed by a supervisor or faculty member | Internship listings on Handshake |

- Step 1 is a checkbox the presenter can tick on five markers. On "Career direction" step 1 is read-only (it is set by the interview).
- Steps 2 and 3 are read-only state marks (a filled check when on, an empty ring when off).
- On: Networking step 2 (Grace attended 2 events) always. Career direction steps 1 and 2 after the interview. Nothing else is on at the start.
- Readiness % = round(earned ÷ 24 × 100), where step 1 and step 2 earn 1 each and step 3 earns 2.

Values on the guided path (must match exactly):

| State | Readiness | Target | Callout lead | Career points |
|---|---|---|---|---|
| Fresh load | 4% | 60% | Behind for a junior, and that's fixable. | 20 |
| After the interview | 13% | 60% | Behind for a junior, and that's fixable. | 40 |
| After the interview and one registration | 13% | 60% | same | 50 |
| …and the LinkedIn self-check ticked | 17% | 60% | same | 55 |

### 2.7 Student · My growth (`growth`)

| Element | Exact copy |
|---|---|
| Title | Grace's career growth record |
| Description | Each event attended adds to a record the student can see. The record stays with the college after she graduates, so the college can study what helps students. |
| Status label | Planned |
| Left block label | Timeline |
| Term 1 | Fall 2025 · Sophomore — Brand Building at a Streaming Studio `attended` |
| Term 2 | Spring 2026 — Cybersecurity and Cloud Jobs Q&A `attended` |
| Term 3 | Fall 2026 · Junior — before interview: Profile card not yet completed · after: Profile card completed through AI interview `+20 points` · then one line per registered event: {title} `registered` |
| Term 4 (future) | Summer 2027 — Internship `recorded later` |
| Term 5 (future) | After graduation — First job and employer `recorded later` |
| Right block label | Topics she has explored |
| Topic bars | one bar per short topic name with its count, sorted by count, largest first. Bar scale maximum is the larger of 3 and the largest count |
| Tile 1 | `{2 + registered}` · events attended or registered |
| Tile 2 | `{points}` · career points |
| Closing line | An Accounting major whose events lean toward media and technology. Her record shows a path her major alone would never reveal. |

Topic counts at fresh load: Marketing 1, Entertainment 1, Technology 1, Consulting 1. After registering for the Northline event: Technology 2, then Marketing 1, Entertainment 1, Consulting 1. Past terms use a filled dot; future terms use an outlined gold dot.

### 2.8 Career Hub · Term overview (`overview`)

| Element | Exact copy |
|---|---|
| Title | Term overview |
| Description | What the college can report each term, drawn from the student records. Shown here for the made-up student body of 300. |
| Status label | Partly built |
| Tiles | `300` student records loaded · `100` students who attended at least one event · `70` students with a profile card (71 after Grace's interview; fix F1) · `200` students never reached by an event |
| Chart 1 label | Event attendance by major |
| Chart 1 rows | Management & HR 46 · IB & Marketing 40 · Accounting 37 · Finance, RE & Law 24 · CIS 13 · Tech & Ops Mgmt 2 (scale maximum 46) |
| Chart 2 label / note | Events that brought in first-time students / Share of each event's attendees for whom it was their first career event. |
| Chart 2 rows (gold bars) | Resume Lab: Getting Past the Screen 100% · Fall Business Career Fair 92% · Brand Building at a Streaming Studio 85% · Moving Goods Across the Pacific 82% · Inside a Big Four Audit Team 56% · Cybersecurity and Cloud Jobs Q&A 38% (scale 0–100) |
| Chart 3 label | Average readiness by year (illustrative) |
| Chart 3 rows | Freshman (34) 22% · Sophomore (35) 33% · Junior (103) 42% · Senior (128) 51% (scale 0–100) |
| Chart 4 label / note | Share on track for their year (illustrative) / Targets: freshman 20%, sophomore 40%, junior 60%, senior 85%. Shows where the Career Hub should focus, for example seniors who are behind. |
| Chart 4 rows (gold bars) | Freshman 56% · Sophomore 20% · Junior 7% · Senior 0% (scale 0–100) |
| Data handling label | How student data is handled (proposed) |
| Data handling bullets | Students activate their own profile; the interview is optional. · The college owns the records, and they stay after students graduate. · Reports show group totals. Partners never see individual student records. |

All numbers come from `SMC.overviewStats()` and `SMC.hubReadiness()`; never type them in.

### 2.9 Career Hub · Student records (`records`)

| Element | Exact copy |
|---|---|
| Title | Student records |
| Description | Every student is on file from day one with major, year and events attended. The profile card fills in when the student activates through the AI interview. |
| Status label | Working in class version |
| Search label / placeholder | Search by name, major or ID / Try Delgado |
| Count | {matches} of 300 records |
| Table columns | ID · Name · Major · Year · Events · Profile card |
| Profile card cell | `AI interview · today` (Grace, after her interview) · `Completed` (a student with interests or a goal on file) · `Not yet` |
| Below the table, when more than 25 match | Showing the first 25. Search to narrow the list. |
| No match (new, N6) | No records match that search. |

Search is a case-insensitive "contains" on `name + " " + major + " " + id`, live on each keystroke, focus and caret kept. The first 25 matches are shown, in file order. Grace's row (P046) is highlighted. Searching `Delgado` gives 14 of 300 records; before the interview Grace's cell reads `Not yet`, after it `AI interview · today`.

### 2.10 Career Hub · Match students to an event (`match`)

| Element | Exact copy |
|---|---|
| Title | Match students to an event |
| Description | Pick an event and the app ranks all 300 students. Staff can adjust how much each factor counts, then invite the top 30 personally. |
| Status label | Working in class version |
| Event picker label | Event |
| Event options, in order | Consulting Case Night · Thu Nov 5, 2026 / The Business of Streaming · Thu Nov 12, 2026 / Audit Season, Up Close · Thu Nov 19, 2026 / Northline Analytics: Behind the Business · Thu Mar 4, 2027 (selected at load) / Harbor Consumer Brands: Behind the Business · Thu Mar 25, 2027 |
| Four weight controls (label, default) | Same major 3 · Said they're interested 3 · Career goal fits 2 · Went to similar events 2. Range 0–10, whole numbers, the value shown beside the label |
| Grace line, when she is in the top 30 | Grace Delgado is #{n} on this list. — after her interview: Grace Delgado is #{n} on this list because of her interview answers. |
| Grace line, not in the top 30, after her interview | Grace Delgado is not in the top 30 for this event. |
| Grace line, not in the top 30, before her interview | Grace has not done her interview yet, so the app knows little about her. |
| Table columns | # · Student · Major · Why on the list · What we know |
| "What we know" cell | Profile card · Major + events · Major only · for Grace after her interview: Profile card (AI interview) |
| Under the table | Showing 15 of the top 30. + button `Send personal invitations to top 30` |
| On pressing the button | In the full version, each student gets a personal invitation and a reminder. |
| No rows (new, N7) | No student matches with these weights. Raise at least one weight above 0. |

Reasons are built by `SMC.score()`: phrases joined with "; " in the order interest, goal, past events, major: `said they're interested in {topic}` · `career goal fits` · `went to {n} similar event(s)` · `same major`. A "Major only" student's reason ends with `; nothing else on file`. The table shows ranks 1–15 of `SMC.rankStudents()`; the list re-ranks on every change of a weight or of the event. Grace's row is highlighted wherever she is.

### 2.11 Partner · My talk (`talk`)

| Element | Exact copy |
|---|---|
| Title | Your talk: Northline Analytics |
| Description | Behind the Business series · Thu Mar 4, 2027 · what an industry partner sees after speaking. Numbers are illustrative. |
| Status label | Partly built |
| Block 1 label / note | Who was invited / Students who said they're interested in technology or data, from every major, not only Computer Information Systems. |
| Block 1 bars (scale maximum 8) | Accounting 8 · Computer Info Systems 7 · Finance, RE & Law 6 · IB & Marketing 5 · Management & HR 4 |
| Block 2 label | How your talk filled |
| Block 2 steps | Invited personally 30 · Signed up 19 · Attended 14 |
| Block 2 note | A mass email to all students for a similar talk brought about 6 people. |
| Block 3 label | What students asked you |
| Block 3 quotes | "What should an accounting student learn first to move into data work?" · "Does Northline hire interns from outside computer science?" |
| Block 3 note | Average rating 4.6 of 5 from 14 students. |
| Block 4 label | Stay involved |
| Block 4 buttons → message | `Offer another talk` → Offer sent to the Career Hub · `Meet interested students` → Students who asked to connect will be notified · `Post an internship` → Internship post sent to the Career Hub for review |
| Block 4 note | You see totals and questions, never individual student records. Your contact stays with the college, not with one staff member. |

These numbers are constants in her file (made up for the demo). They are not derived from the 300.

### 2.12 Presenter guide

A floating button, bottom right: `Presenter guide` when closed, `Hide presenter guide` when open. The panel (landmark name `Presenter guide`) shows, for the current screen: the eyebrow `Presenter guide`, a title, one line of intent, a numbered list, and a `Say:` line. Content, verbatim:

| Screen | Title | Intent | Steps | Say |
|---|---|---|---|---|
| `entry` | Opening (Chau) | Start here. One sentence on the problem, then pick a door. | 1. Problem: events struggle to fill seats, contacts sit with individual staff, and nobody can see a student's growth. 2. Explain the three doors: one app, three kinds of users, each with its own sign-in. 3. Click Student portal. | "Smart Match brings the right events to the right students, and keeps a record of how each student grows." |
| `interview` | Student · AI interview (Chau) | Show that the app already knows the student's record, and the interview fills in the rest. | 1. Point to the right side: major, year and events come from college records. 2. Answer the chat: curious about tech jobs → Done → Not sure yet → Yes, help me compare. 3. Watch the profile card fill in as she answers. 4. Say clearly: this interview is scripted for today; a live AI version is planned. | "Most students never fill in a form. A two-minute conversation does it for them." |
| `recs` | Student · Events for me (Chau) | Show events coming to the student, each with a reason. | 1. Read one 'Why you' line out loud. 2. Mention: before the interview, the app only suggested the audit event because she's an accounting major. 3. Click Register on the top event to show the check-in code and points. | "Every suggestion says why. Staff and students can see it isn't a black box." |
| `readiness` | Student · My readiness (Janice) | Points show effort; readiness shows progress toward being job-ready. | 1. Point to the ring: readiness now versus the gold mark for a junior. 2. Tick one self-check (for example, LinkedIn) and show the % move a little. 3. Explain why: confirmed steps count double, so self-checks alone can't raise it much. 4. Say the markers are a draft and will follow the college's official list. 5. Show the four help options: assistant bot (AI) for quick questions, message an advisor, book an advisor, digital resources. Ask the bot How do I get my resume reviewed? and it hands off to a real advisor. | "Grace can see where she stands for her year and exactly what to do next." |
| `growth` | Student · My growth (Janice) | The record that stays after graduation. | 1. Walk the timeline from sophomore year to after graduation. 2. Point out that her events lean toward media and technology, which her major alone would never show. | "Over four years this becomes the college's best evidence of what helps students." |
| `overview` | Career Hub · Term overview (Janice) | What the college can report each term. | 1. These numbers come from the 300 made-up student records in the class file. 2. Point to 'students never reached by an event' as the opportunity. 3. Readiness charts are illustrative. | "For the first time, the Career Hub can see who it isn't reaching." |
| `records` | Career Hub · Student records (Janice) | Every student is on file from day one. | 1. Type 'Delgado' in search to find Grace; her card shows 'AI interview · today'. | "Students don't sign up from scratch; they activate a record that already exists." |
| `match` | Career Hub · Match students to an event (Chau) | How staff fill an event. | 1. Northline is selected: Grace is #4 because of her interview answers. 2. Move the 'Same major' slider up and show CIS majors take over the list. 3. Close: invite the top 30 personally. | "Students from any major who said they care about the topic get invited, not only the obvious major." |
| `talk` | Partner · My talk (Chau) | Why industry partners would come back. | 1. Show who was invited, from five majors. 2. Show the turnout compared with a mass email. 3. Ask the board: 'Would you use this? What would make you speak again?' | "Your contact stays with the college, and you see the difference your talk made." |

### 2.13 New strings (the only wording the mockups add)

Nothing else may be invented. A mockup that needs a string not listed here uses none.

| ID | Where | Text | Why it exists |
|---|---|---|---|
| N1 | Every screen, persistent | Design for the next phase — made-up data | Honesty rule H1; her demo line is only on the entry |
| N2 | Pinned in both transcripts | Scripted for this demo. Not a live AI. | Honesty rule H3. Her bot panel says "AI" and "demo" but never "scripted" |
| N3 | First focusable element | Skip to main content | Keyboard floor (section 9) |
| N4 | Presenter guide panel (in direction C also on the stop rail) | Stop {n} of 9 · `Back` · `Next` | Presenters and clickers move through the nine stops in order |
| N5 | Presenter guide panel | `Reset demo` → first press: `Press again to reset` | Rehearsals. Inline confirm, 5 seconds, per the class-exercise convention |
| N6 | Student records, no match | No records match that search. | Her table goes blank |
| N7 | Match, no rows | No student matches with these weights. Raise at least one weight above 0. | Her table goes blank when every weight is 0 |
| N8 | Free-text Send while the field is empty | Type an answer first. (interview) · Type a question first. (bot) · Type a message first. (advisor message) | Explains the `aria-disabled` Send button |
| N9 | Theme control, guide panel | `Light` · `Dark` | Dark is opt-in only (section 6.4) |
| N10 | Direction B only: switcher field | Go to a portal or screen… | The command-style switcher needs a field label |

### 2.14 Proposed wording changes (default is hers; apply only if the owner or Ann says so)

| ID | Where | Her wording | Proposed | Reason |
|---|---|---|---|---|
| W1 | Guide, `recs`, step 2 | Mention: before the interview, the app only suggested the audit event because she's an accounting major. | Mention: before the interview, the audit event came first only because she's an accounting major. | Her own screen shows three events before the interview, not one (section 2.5) |
| W2 | Guide, `interview`, step 2 | …→ Not sure yet → Yes, help me compare. | …→ Not sure yet → Yes, help me compare → Show my events. | The path has a fifth click; without it the profile is never saved |
| W3 | Interview turn 4a | You picked consulting and technology among your interests. | You picked technology among your interests. | On the guided path Consulting is never picked; Technology and Entertainment are |
| W4 | Partner, block 1 note | …from every major, not only Computer Information Systems. | …from five majors, not only Computer Information Systems. | The chart and the guide show five of the six majors |
| W5 | Check-in card, under points | Points exist in the early version | Points already work in the class version | Matches the phrasing of her status labels; her line is hard to parse aloud (Appendix C) |

Until a ruling, all three mockups use her wording for W1–W5.

### 2.15 Typos and inconsistencies in her prototype (flagged, not silently fixed)

| # | Where | What |
|---|---|---|
| T1 | README | Names the file `SmartMatch_CPP_Prototype_10062026.html`; the file sent is `…10062026_1.html` |
| T2 | Interview turn 4a | Says "You picked consulting and technology"; the pre-selected picks are technology and entertainment (W3) |
| T3 | Interview turn 3 | "Graduate school" is offered but stored as "Undecided", which then triggers the "That's very common for juniors…" turn (fix F2) |
| T4 | Interview turn 4b | "Only accounting events" changes nothing; events outside Accounting are still suggested |
| T5 | Term overview | "students with a profile card" reads 72 after Grace's interview; the true count is 71. She is counted twice (fix F1) |
| T6 | Career points | Readiness shows points including self-checks; Events for me and My growth show them without. The same student has two totals (fix F3) |
| T7 | Guide, `recs` | "the app only suggested the audit event": three events are shown before the interview (W1) |
| T8 | Guide, `interview` | The click path stops one click short (W2) |
| T9 | Readiness | The third next-step variant ("Book a practice interview") can never appear: its condition is never met |
| T10 | Readiness | "Sign up for a resume workshop" → `Go` opens Events for me, where no resume workshop is listed |
| T11 | Readiness ring | The gold target mark is a 2-unit dash on a 3px stroke; it is all but invisible at 1440 (see `reference/12-student-readiness-1440.png`). Tile 2 refers to it as "(gold mark)" |
| T12 | Partner | "from every major" beside a chart of five majors; the data has six (W4) |
| T13 | Major names | Three spellings of one major: "Computer Information Systems" (tables), "CIS" (overview chart), "Computer Info Systems" (partner chart) |
| T14 | Assistant names | "Smart Match assistant" (interview) and "CBACH assistant bot" (readiness) are two names for scripted helpers; the board may ask if they are one thing |
| T15 | Voice | The student portal mixes first person in the menu ("My readiness"), third person in titles and descriptions ("Grace's career readiness", "her profile card") and second person in reasons ("Why you"). Read as a narrator's voice for the demo; kept |
| T16 | Status labels | Three phrasings for "works": "Working in class version", "Matching works in class version", and for partial "Partly built" |
| T17 | Timeline | The Northline talk is Thu Mar 4, 2027. The Hub screen is about to invite its top 30; the Partner screen reports who attended and what they asked. Both cannot be true on one day |
| T18 | First-time chart | "First career event" is the first event code in the student's list. Codes are in date order, so "Resume Lab" (E01) is 100% by construction |
| T19 | Focus ring | Her focus outline is gold on white: 1.75:1, under the 3:1 needed for a focus indicator (section 6.3) |
| T20 | Dark theme | Her page turns dark when the laptop's OS is dark. Projected in a lit room that is the wrong default (section 6.4) |
| T21 | Topic name | "Supply chain / logistics / operation" (singular). It is the class file's spelling; kept as data |
| T22 | Transcript | The whole chat log is a live region and is rebuilt on every turn, so a screen reader re-reads all of it (section 9.4) |
| T23 | Layout | The floating "Presenter guide" button covers content at the bottom right (the bot's Send button in `reference/13-student-readiness-bot-full.png`); the toast overlaps the check-in card; the check-in card's "Planned" label stretches the full column width; the transcript clips its top line mid-sentence (`reference/06-student-interview-next-step-1440.png`) |
| T24 | Small type | Status labels are 11px, helper lines 13px, the match line 12px. None can be read from the back of a lit room (section 5.3) |
| T25 | Outcomes | Booking, sending and "opens" results appear only as a toast that leaves after 2.3 seconds. A presenter who is talking will miss it (section 7.11) |


## 3. Data contract

### 3.1 The shared file

[`shared/data.js`](shared/data.js) is already written (97 kB). It was generated by copying lines 212–223 of her HTML byte for byte (`LOGO`, `RAW`, `PAST`, `TOPICS`, `GOALTOPIC`, `UPCOMING`) into a wrapper, followed by her `score()`, her ranking sort, her `hubReadiness()` and her check-in pattern, with one change only: global state is passed in as arguments. A check run on 2026-10-06 compared her untouched code with the shared file for all 5 events × 4 weight sets, before and after the interview: identical ids, totals, reasons and "what we know" values in every case.

- **Do not edit it by hand.** If her file changes, regenerate it the same way and re-run `SMC.selfTest()`.
- **Load it as a classic script** (it works from `file://`; ES module imports do not):

```html
<script src="../../shared/data.js"></script>
<script src="../../shared/vendor/gsap/gsap.min.js"></script>
<script src="../../shared/vendor/gsap/Flip.min.js"></script>
<script src="app.js"></script>
```

- It defines one global, `window.SMC`. From Node, `require("./docs/design/cpp-prototype/shared/data.js")` returns the same object.
- No mockup re-implements matching, ranking, overview counts or readiness averages. Call `SMC`.

### 3.2 Shapes

| Name | Shape | Notes |
|---|---|---|
| `SMC.RAW` | 300 rows of `[id, name, major, year, eventsAttended, statedInterests, statedGoal, tiebreak]` | `;`-separated strings for events and interests; empty string when none. Her comment: "profile and record columns only; hidden columns are not included" |
| `SMC.makeStudents()` | `{ id, name, major, year, events: string[], interests: string[], goal: string, tb: number, viaAI: boolean }[]` | Fresh objects each call. Call once per page load, and again on `Reset demo` |
| `SMC.GRACE_ID` | `"P046"` | Grace Delgado · Accounting · Junior · events `E04`, `E08` · no interests, no goal, `tb` 159 |
| `SMC.PAST` | `{ [id]: [title, monthYear, topics[]] }`, `E01`–`E10` | Past events |
| `SMC.UPCOMING` | `{ id, m, d, when, title, host, topics[], major }[]`, 5 items in this order: `U1`, `U2`, `U3`, `E11`, `E12` | `major` may be `"All majors"` (U1), which matches no student |
| `SMC.TOPICS` | 13 strings such as `"Technology / information systems"` | `SMC.short(t)` gives the part before the first `" / "` |
| `SMC.GOALTOPIC` | `{ [goal]: topic[] }`, 14 goals | Goals in the data that are **not** keys: `"Undecided"`, `"Graduate school"` (they never earn the goal factor) |
| `SMC.DEFAULT_WEIGHTS` | `{ major: 3, interest: 3, goal: 2, past: 2 }` | Frozen |
| `SMC.TARGET` | `{ Freshman: 20, Sophomore: 40, Junior: 60, Senior: 85 }` | Readiness targets, % |
| `SMC.LOGO` | PNG data URI | Ann's embedded Cal Poly Pomona logo. Use unaltered, on a white plate, alt `Cal Poly Pomona` |

Population facts (for sanity checks): majors — Management & Human Resources 82, International Business & Marketing 70, Accounting 55, Finance, Real Estate & Law 54, Computer Information Systems 26, Technology & Operations Management 13. Years — Senior 128, Junior 103, Sophomore 35, Freshman 34.

### 3.3 Functions

| Call | Returns | Used by |
|---|---|---|
| `SMC.score(student, event, weights)` | `{ total, reason, info, fInt, fGoal, fPast, fMajor, hit, related }` | everything below |
| `SMC.rankStudents(students, event, weights)` | top 30 of `{ s, ...score }`, total 0 removed | `match` (show the first 15) |
| `SMC.rankEvents(student)` | top 3 upcoming events with their score, always at the default weights | `recs` |
| `SMC.whyYou(result)` | the student-facing reason string | `recs` |
| `SMC.overviewStats(students)` | `{ n, attended, cards, neverReached, attendanceByMajor, firstTimers }` | `overview` |
| `SMC.hubReadiness(students)` | `[year, average %, % on track, count][]` | `overview` charts 3 and 4 |
| `SMC.qrCells(eventId)` | `{ size: 29, cells: [x, y][], finders: [x, y][] }` | check-in card (section 7.12) |
| `SMC.applyGuidedInterview(grace)` | Grace in the guided-path end state | deep link `iv=done`, tests |
| `SMC.selfTest()` | `{ name, got, want, pass }[]` | audit item 15 |

### 3.4 The matching function, exactly

Four factors, each 0 to 1, multiplied by its weight and added:

| Factor | Weight key (default) | Value |
|---|---|---|
| Same major | `major` (3) | 1 when `event.major === student.major`, else 0 |
| Said they're interested | `interest` (3) | 1 when any of the student's interests is one of the event's topics, else 0 |
| Career goal fits | `goal` (2) | 1 when any topic in `GOALTOPIC[student.goal]` is one of the event's topics, else 0 |
| Went to similar events | `past` (2) | Count the student's past events that share a topic with this event: 2 or more → 1, exactly 1 → 0.5, none → 0 |

- `total = major×fMajor + interest×fInt + goal×fGoal + past×fPast`. At the defaults the maximum is 10, which is why the student view says "of 10".
- "What we know": `Profile card` if the student has any interest or a goal; else `Major + events` if any past event; else `Major only`.
- **Hub order:** total, high to low; then "what we know" (Profile card, then Major + events, then Major only); then year (Senior first); then the `tb` number, low to high. Students with total 0 are left out. Top 30 kept, 15 shown.
- **Student order:** total, high to low; ties keep the order of `UPCOMING`. Top 3 shown.

### 3.5 Test vectors

All from her code. "After interview" means the guided path (section 2.4). Factor columns are the 0 / 0.5 / 1 values for major, interest, goal, past.

**TV-A. Northline Analytics (E11), default weights 3/3/2/2, after interview.** Top 8 of 30:

| # | ID | Student | Major | M | I | G | P | Total | Reason | What we know |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 | P108 | Emeka Soto | Computer Information Systems | 1 | 1 | 1 | 0 | 8 | said they're interested in technology; career goal fits; same major | Profile card |
| 2 | P224 | Camila Alcantar | Computer Information Systems | 1 | 1 | 1 | 0 | 8 | said they're interested in technology; career goal fits; same major | Profile card |
| 3 | P028 | Mei Huynh | Computer Information Systems | 1 | 1 | 0 | 0 | 6 | said they're interested in technology; same major | Profile card |
| 4 | **P046** | **Grace Delgado** | Accounting | 0 | 1 | 1 | 0.5 | 6 | said they're interested in technology; career goal fits; went to 1 similar event | Profile card (AI interview) |
| 5 | P286 | Nadia Okafor | Computer Information Systems | 1 | 1 | 0 | 0 | 6 | said they're interested in technology; same major | Profile card |
| 6 | P004 | Brandon Soto | Accounting | 0 | 1 | 1 | 0 | 5 | said they're interested in technology; career goal fits | Profile card |
| 7 | P178 | Lucas Nguyen | Finance, Real Estate & Law | 0 | 1 | 1 | 0 | 5 | said they're interested in technology; career goal fits | Profile card |
| 8 | P131 | Ryan Santos | International Business & Marketing | 0 | 1 | 1 | 0 | 5 | said they're interested in technology; career goal fits | Profile card |

Ties explained: P108 before P224 (Senior before Junior). P028, P046, P286 all total 6 with a profile card: Senior, then Junior, then Sophomore. Line under the sliders: "Grace Delgado is #4 on this list because of her interview answers."

**TV-B. Same event, "Same major" raised to 10 (10/3/2/2), after interview.** Top 8: P108 (15), P224 (15), P028 (13), P286 (13), P220 Samir Navarro (11), P124 Zoe Nguyen (11), P168 Xavier Nguyen (10), P208 Rosa Reyes (10). All fifteen visible rows are Computer Information Systems. Grace is #27, total 6, so she is off the visible table; the line reads "Grace Delgado is #27 on this list because of her interview answers."

**TV-C. Same event, default weights, before interview.** Grace: M 0, I 0, G 0, P 0.5 → total 1, reason "went to 1 similar event", "Major + events". She is not in the top 30. Line: "Grace has not done her interview yet, so the app knows little about her." Top 4: P108 (8), P224 (8), P028 (6), P286 (6).

**TV-D. Audit Season, Up Close (U3), default weights.** Top 5: P049 Valeria Medina (9: M 1, I 1, G 1, P 0.5), P192 Tomas Chen (7), P225 Priya Pham (7), P276 Emily Estrada (6), P072 Maya Truong (6). Grace is not in the top 30 after her interview: "Grace Delgado is not in the top 30 for this event."

**TV-E. Events for Grace.** Before: U3 (3), U1 (1), U2 (1). After: E11 (6), U2 (4), U1 (3). Strings in section 2.5.

**TV-F. Term overview.** 300 / 100 / 70 / 200. Charts as listed in section 2.8.

`SMC.selfTest()` checks the same facts (its rows are named TV0–TV8: counts, events before and after, Grace's rank before, TV-A, TV-B, TV-D, the overview tiles, readiness by year). From the browser console:

```js
console.table(SMC.selfTest());   // every row: pass === true
```

### 3.6 What is real and what is made up (her README)

| Source | What |
|---|---|
| From the class file (300 made-up students) | Grace Delgado (P046), every student record, the matching and its order, the Term overview counts and the two attendance charts, the Student records table |
| Made up for the demo | The three fall events (U1–U3) and their hosts; the partner's talk numbers, quotes and rating; Dana Whitfield; the readiness numbers for the 300 ("illustrative"); the appointment times; the resource names; "60 seats"; career points |
| Scripted, not live AI | The profile interview; the CBACH assistant bot |
| Draft | The six readiness markers and their steps; the year targets 20 / 40 / 60 / 85 |

No name outside `shared/data.js` and section 2 may appear in a mockup, a screenshot or a NOTES file.

### 3.7 Demo state, and three fixes applied by all three mockups

One state object per mockup. Shape (names may differ; the fields may not):

```js
const state = {
  portal: null,                 // null | "student" | "hub" | "partner"
  page: { student: "interview", hub: "overview", partner: "talk" },
  ivStep: 0, ivLog: [], ivDone: false, picks: [], cardPointsGiven: false,
  registered: [], lastRegistered: null,
  selfChecks: {},               // { resume, interview, network, ethics, experience }: boolean
  helpPanel: null,              // null | "chat" | "msg" | "book" | "res"
  bot: [],                      // transcript; first turn is fixed
  hubEvent: "E11", weights: { major: 3, interest: 3, goal: 2, past: 2 }, search: "",
  guideOpen: false, theme: "light"
};
```

| Fix | Her behaviour | Contract behaviour | Why |
|---|---|---|---|
| F1 | "students with a profile card" = count + 1 once Grace is done, although the count already includes her (72) | Show `overviewStats().cards` as is: 70 before, 71 after | The number on screen must be true of the data on screen |
| F2 | "Graduate school" is stored as "Undecided" | Stored as "Graduate school"; turn 4b follows | A board member may click it in Q&A |
| F3 | Two different point totals | One derived number everywhere: `20 + (20 if the interview is finished at least once) + 10 × registered events + 5 × ticked self-checks` | Same student, same number on three screens |

Everything else follows her behaviour, including T4, T9 and T10.

**Persistence.** Her prototype remembers only the open portal and screen. The mockups keep the whole demo state in `localStorage` under `smc.<letter>.v1` (`smc.a.v1`, `smc.b.v1`, `smc.c.v1`; all `file://` pages share one origin in Chrome, so the letter matters), with every read and write in `try/catch`. Reason: stop 8 depends on stop 2, and a stray refresh in front of the board must not lose Grace's interview. `Reset demo` (N5) and `?reset=1` clear it.

**Deep links** (for screenshots and audit; all optional parameters):

```text
?p=student|hub|partner      portal            &s=<screen id from 2.1>
&iv=done                    guided interview  &reg=E11        registered event
&help=chat|msg|book|res     readiness panel   &w=10,3,2,2     weights
&ev=U3                      hub event         &q=Delgado      records search
&guide=1                    guide open        &theme=dark     &rm=1  reduced motion
&reset=1                    clear saved state
```

`theme=dark` turns dark on only in a direction that ships a dark theme (section 6.4). Where none ships, the parameter is ignored without error and the page stays light.

## 4. Wording rules

| Rule | Detail |
|---|---|
| Source | Section 2 is the copy. Section 2.13 is the whole list of additions |
| Voice | Plain, warm, brief; a student explaining their own project to a visitor. No exclamation marks in new strings (hers has "Hi Grace!"; kept) |
| Case | Sentence case for titles, labels, buttons, table heads and status labels. A direction may draw her small labels in uppercase with CSS (A does); the source string stays sentence case, and uppercase text is never under 14px |
| Numerals | Always digits: "30", "2 or more", "#4". Percent with no space: "13%". Ratios as "6 of 10", "4.6 of 5", "15 of the top 30". Tabular figures wherever numbers sit in a column or change in place |
| Dates and times | Events: `Thu Mar 4, 2027`. Past events: `Oct 2025`. Slots: `Mon Oct 12 · 10:00 am` (lowercase am/pm). Date tile: day number over three-letter month. No ISO dates, no relative dates |
| Separator | ` · ` (middle dot with a space each side) between facts in one line. Reasons join with `; ` |
| Status labels | Her six strings only (section 2.2). Never shortened to an icon, never "Beta", "WIP", "Live" |
| Scripted helpers | Named exactly "Smart Match assistant" and "CBACH assistant bot". They "say" and "answer" things. They never "think", "learn", "understand", "decide" or "know you" in any new string. N2 is pinned in both |
| Made-up data | "made-up" (her word), not "fake", "dummy", "synthetic", "sample" (except her own "Sample code only.") |
| Words to avoid in new strings | AI-powered, smart (outside the product name), intelligent, algorithm, real-time, live, predict, insight, optimize, seamless, user, score |
| Button labels | Verb first, say what happens: "Send message", "Offer another talk". In-flight labels are not needed (nothing is sent) |
| Reasons and names | Never truncated, never ellipsed, never hidden in a tooltip. They wrap |
| Line length | A screen description: at most 2 lines at 1440, with a measure of up to 100 characters. Body prose (help body, notes, footnotes, chat turns): 45–70 characters per line at 1440. A reason fits in 2 lines in the match table at 1440 and at 1280; a status label never wraps |
| Outcome messages | Her sentence, as a persistent line next to the control that caused it (section 7.11) |

## 5. Layout and spacing system

### 5.1 Spacing

One 4px-based scale, the same steps as the class exercise so the work ports. Every margin, padding and gap is one of these values; 1px and 2px are allowed only for borders, outlines and rules.

| Token | px | Typical use |
|---|---|---|
| `--sm-space-1` | 4 | Icon to label |
| `--sm-space-2` | 8 | Chip gap, tight groups |
| `--sm-space-3` | 12 | Row inner gap, control padding |
| `--sm-space-4` | 16 | Gutter at 390, card padding at 390, between related controls |
| `--sm-space-5` | 24 | Card padding at 1440, gap between cards |
| `--sm-space-6` | 32 | Between blocks in a screen |
| `--sm-space-7` | 48 | Between sections; page top padding |
| `--sm-space-8` | 64 | Entry and stage breathing room |
| `--sm-space-9` | 96 | Direction C stage only |

More space above a heading than below it.

### 5.2 Grid and breakpoints

| Name | Width | Columns | Gutter | Side margin | Shell |
|---|---|---|---|---|---|
| `xl` (audited) | 1440×900 | 12 | 24 | per direction | Full desktop shell |
| `lg` | 1024–1439 | 12 | 24 | 32 | Desktop shell; must hold at 1280×720 (compact height, below) |
| `md` | 640–1023 | 8 | 16 | 24 | Navigation collapses to a horizontal strip or a sheet |
| `sm` (audited) | 390 | 4 | 16 | 16 | Single column; tables become stacked rows |

- No horizontal page scroll at any width from 360 to 1920. Only a wide table may scroll inside its own box, and at 390 it becomes stacked rows instead.
- At 200% zoom on 1440 the layout reflows to the `md` layout.
- **Above the fold at 1440×900**, without scrolling, every mockup shows:

| Screen | Must be visible |
|---|---|
| every screen | Title, status label, marker N1, the way to switch portal |
| `entry` | All three doors and the demo line. The entry does not scroll: the page is no taller than the viewport |
| `interview` | The latest assistant turn in full, every reply option, and the whole profile card |
| `recs` | All three event rows. After `Register`, the check-in card is brought into view by the smallest scroll that shows the code and the points (a scroll, not a focus move); the pressed button, its event title, the screen title and the status label stay on screen, clear of any sticky bar. A direction that places the card beside the list does not scroll at all |
| `readiness` | The ring, the three tiles, the callout, and the four help buttons |
| `growth` | The timeline, the topic bars and the closing line, whole (the closing line is the stop's point) |
| `overview` | The four tiles and the first row of charts |
| `match` | Event picker, four weight controls, the Grace line, Grace's row #4 whole and at least 5 full ranked rows |
| `talk` | "Who was invited" and "How your talk filled" |

- **Compact height.** The room may give 1280×720 (a 1920×1080 laptop at 150% display scale). Under `@media (max-height: 800px)` every mockup switches to a compact layout built from the same tokens: the screen title and description one step down the type scale (never under the floors of section 5.3), block gaps and card padding one step down the spacing scale, the ring at 150px, match-table cell padding 8 / 12, and any full-height stage sized as `100dvh` minus its fixed bars. Audited at 1280×720:

| Screen | Must hold at 1280×720 |
|---|---|
| every screen | Title, status label, marker N1, the way to switch portal. Nothing interactive and no line of text rests under a fixed bar, under the stop rail or behind the guide button; whatever is below the fold is reached by ordinary scrolling and comes fully clear of them |
| `entry` | All three doors and the demo line, whole, with no scroll |
| `interview` | The latest assistant turn in full (the log is at least 240px tall; the page scrolls, the log does not shrink), every reply option, and the whole profile card down to its "Next step" value |
| `recs` | Every `Register` button and match line on screen is whole; none is under a fixed bar |
| `readiness` | The ring, the three tiles and the callout. The four help buttons are on screen or one scroll away, never under a fixed bar |
| `match` | Event picker, four weight controls, the Grace line, and at least 4 full ranked rows with Grace's row #4 whole |

### 5.3 Type scale

One scale; each direction maps roles onto it (Part 2). Sizes are px at `lg` and up; the 390 column is the size at `sm`.

| Token | Desktop size / line | 390 size / line |
|---|---|---|
| `--sm-text-14` | 14 / 20 | 14 / 20 |
| `--sm-text-16` | 16 / 24 | 15 / 22 |
| `--sm-text-18` | 18 / 28 | 16 / 24 |
| `--sm-text-20` | 20 / 30 | 17 / 26 |
| `--sm-text-24` | 24 / 32 | 20 / 28 |
| `--sm-text-28` | 28 / 36 | 24 / 30 |
| `--sm-text-36` | 36 / 44 | 28 / 34 |
| `--sm-text-48` | 48 / 54 | 34 / 40 |
| `--sm-text-64` | 64 / 68 | 40 / 44 |
| `--sm-text-80` | 80 / 84 (direction C only) | 48 / 52 |

Floors for the back row (at `lg` and up):

| Content | Minimum | Her value |
|---|---|---|
| Any text at all | 14px | 11px |
| Status label, scripted line N2 | 14px, weight 600 (A's mono uppercase status label: 500) | 11px |
| Marker N1 | 16px, weight 600 | 11px |
| Read-aloud body text: names, reasons, table cells, chat turns, bar labels and their numbers | 16px (B) · 18px (A, C) | 12–15px |
| Chip labels (`sm-chip`) and the match line ("match 6 of 10") | 16px in every direction | 12–15px |
| Body and descriptions | 16px (B) · 18px (A, C) | 16px |
| Screen title | 28px | 28px |
| Entry title | 48px | 56px |
| Big figures (tiles, ring, points) | 28px | 30–40px |

- `font-variant-numeric: tabular-nums` on ranks, IDs, counts, weights, percentages and points. It is the computed value that counts: a later `font:` shorthand resets it, so declare it on `td`, `th`, `output`, the weight value and the tile figures after the component rules.
- Weights used: 400, 500, 600, 700. No text under 400. No italic for empty values at small sizes; "Not yet" is muted, not italic.
- Text fits its box at 1440 and 390 with the web fonts **and** with the fallback stack (section 10.4).

### 5.4 Radius, borders, elevation

| Token | Value | Use |
|---|---|---|
| `--sm-radius-xs` | 4px | Bars, progress dots, QR plate |
| `--sm-radius-sm` | 6px | Status label, table corner (B) |
| `--sm-radius-md` | 10px | Buttons, inputs, menu items |
| `--sm-radius-lg` | 14px | Cards, panels, screens |
| `--sm-radius-xl` | 18px | Entry doors, guide panel, sheets |
| `--sm-radius-pill` | 999px | Chips, pills, avatar |

| Token | Value | Use |
|---|---|---|
| `--sm-elev-0` | none | Rows, flat cards |
| `--sm-elev-1` | `0 1px 2px rgba(16,37,27,.06), 0 4px 12px rgba(16,37,27,.06)` | Resting card (directions that use shadow) |
| `--sm-elev-2` | `0 2px 4px rgba(16,37,27,.06), 0 12px 28px rgba(0,80,48,.10)` | Hovered or selected card, popover |
| `--sm-elev-3` | `0 8px 16px rgba(16,37,27,.08), 0 24px 60px rgba(0,80,48,.16)` | Guide panel, toast, sheet |

Rules:

- A surface has a border **or** a shadow, never both. Each direction picks one for cards and keeps it.
- Cards nest one level at most. No card inside a card inside a screen card.
- Decorative lines use `--sm-line` (1px). Anything that outlines a control uses `--sm-line-strong` (at least 3:1).
- No side-stripe borders as accents, no gradient text, no glass blur, no glow.

### 5.5 Icons

- **Set:** Lucide (ISC licence), inlined as SVG, `stroke="currentColor"`, stroke width 2, sizes 16 (inside 14px labels), 20, 24. The React app already uses `lucide-react`, so names port one to one.
- **Allowed, by meaning:** `arrow-right` (door and "next"), `check` (registered, step done), `circle-check` (working label), `circle-dot` (partly label), `circle-dashed` (planned label), `info` (marker N1, scripted line N2), `user-round` (student), `building-2` (Career Hub), `handshake` (partner), `calendar-days` (event), `sliders-horizontal` (weights), `list-ordered` (ranked list), `search`, `send`, `message-square-text`, `bot` (assistant bot label only), `id-card` (profile card), `qr-code` (check-in label), `rotate-ccw` (reset, start over), `presentation` (guide), `chevron-left`, `chevron-right`, `chevrons-up-down` (switcher), `sun`, `moon`, `x`.
- Every icon that stands alone has an accessible name; every icon beside its words is `aria-hidden="true"`.
- No emoji, no icon font, no stock or generated imagery, no illustration other than what a direction's section names. No icon beside a screen title.

### 5.6 Density

| Element | A · Blueprint | B · Workbench | C · Walkthrough |
|---|---|---|---|
| Table row height (a single-line row; a row whose reason takes 2 lines is taller) | 52px | 44px | 60px |
| Table cell padding (block / inline; 8 / 12 at compact height, section 5.2) | 12 / 16 | 8 / 12 | 16 / 16 |
| Table text | 18px | 16px | 18px |
| List row (event) padding | 16 | 12 | 24 |
| Control height, as drawn | 44px | 40px | 52px |

In every direction:

- Sticky table header inside a scrolling table box; numeric columns right-aligned only when they are compared down the column (the `#` and `Events` columns stay left-aligned as in hers); no zebra stripes; row dividers 1px `--sm-line`; Grace's row is the only tinted row.
- **Rows of the match table on screen:** Grace's row #4 whole and at least 5 full rows at 1440×900; at least 4 full rows, Grace's among them, at 1280×720. One number for all three directions. Reasons take 2 lines on this table, so the single-line heights above are not a row count; a denser direction may show more.
- In both tables the student's name and the last column ("What we know", "Profile card") stay on one line at `lg` and up; the reason column takes the slack.
- **Hit area:** at least 44×44px for every control, whatever height is drawn. The drawn box may be 40px tall for chips in any direction and for all controls in B.

## 6. Brand constraints and colour

### 6.1 The two brand colours

Ann's tokens carry Cal Poly Pomona green `#005030` and gold `#fdb71e`. Both stay in all three directions, with fixed jobs:

| Colour | Job (all directions) | Never |
|---|---|---|
| Green `#005030` | Primary action; current navigation item; "working" status; focus ring on light surfaces; data bars; the brand surface in C | Body text colour for long prose (ink is used); a second "decorative" green |
| Gold `#fdb71e` | A highlighter. **Honesty and data marks, the same in every direction:** "planned" status and the scripted line N2 (soft tint + gold-ink text), the gold bars of the two "gold" charts, the third progress dot, the future-term dot on the timeline (a gold ring), the target mark on the ring. **Highlights:** Grace's row (soft tint) and the confirmed state "Registered" in every direction; "new from the interview" pills, the reason chip, the callout and the guide's `Say:` line (soft tint) in A and C | Text on a light surface (1.75:1). A focus ring on a light surface. An outline on a light surface without a dark keyline beside it (the gold bars and the future-term dot carry a 1px `--sm-gold-ink` keyline, the target mark a 1px `--sm-ink` one). A button's resting state. More than one filled gold element per screen region (the bars of one chart, or one marker's dots, count as one) |
| Blue `#2e5f8a` | "Partly built" status only | Links, actions, charts |

How each direction may use them. Part 2 may re-tone a surface; it never re-tones an honesty component (section 7.4) or one of the honesty and data marks above:

| Direction | Green | Gold |
|---|---|---|
| A · Blueprint | As Ann: filled buttons and the current menu item; green-tinted neutrals for page and lines | As Ann: every job in the table above, plus the avatar |
| B · Workbench | One accent on a neutral grey workspace: primary button, current item marker, bars. No green-tinted surfaces except selected rows, the "working" status label and bar tracks; the other surfaces section 7 draws on green-soft may be re-toned to `--b-sunk` (assistant turns are) | The honesty and data marks, Grace's row tint and "Registered". Nothing else: the reason chip, the callout, the `Say:` line and the "new" pills are neutral, on `--b-sunk` |
| C · Walkthrough | Also a full brand surface: the entry stage and the stop rail are solid green with white text | Gold numerals and the active stop on the green surface (5.46:1), plus the same jobs as A |

Note for the port: the app's theme uses `#FFB81C` for gold; Ann's file uses `#fdb71e`. The mockups use hers. Reconcile at build time (Appendix B, OQ-8).

The logo is the university's mark. Use `SMC.LOGO` as she did: unaltered, on a white plate with at least 8px of clear space, never recoloured, redrawn, cropped or animated.

### 6.2 Shared colour tokens (light, default)

Semantic tokens that every mockup defines. A's values are Ann's. B and C change only the neutrals (Part 2); the brand and status rows are identical everywhere.

| Token | A value (Ann's) | Role |
|---|---|---|
| `--sm-page` | `#f2f5f2` | Page background |
| `--sm-surface` | `#ffffff` | Cards, screens, table body |
| `--sm-ink` | `#10251b` | Text |
| `--sm-muted` | `#53655a` | Secondary text |
| `--sm-line` | `#d6dfd8` | Decorative dividers only (1.36:1) |
| `--sm-line-strong` | `#66796e` (new) | Control outlines, slider track, empty step ring |
| `--sm-green` | `#005030` | Brand green |
| `--sm-green-hover` | `#003d24` (new) | Primary button hover and press |
| `--sm-on-green` | `#ffffff` | Text on green |
| `--sm-green-soft` | `#e1ede6` | Assistant turns, date tile, bar track, working label |
| `--sm-gold` | `#fdb71e` | Brand gold |
| `--sm-on-gold` | `#1d1503` | Text on gold |
| `--sm-gold-soft` | `#fff1cc` | Grace's row, planned label, scripted line N2; in A and C also the callout, reason chip, "new" pill and `Say:` line |
| `--sm-gold-ink` | `#7a5600` | Gold-coded text on light |
| `--sm-part` | `#2e5f8a` | Partly-built label text |
| `--sm-part-soft` | `#e3edf7` | Partly-built label fill |
| `--sm-danger` | `#b3261e` (new) | Reserved; no screen uses it at rest |

### 6.3 Contrast (WCAG 2.x, computed 2026-10-06)

Text needs 4.5:1 (3:1 at 24px regular or 19px bold and up). Because the room is lit and projectors wash out, this contract asks for **7:1 on primary text and 5:1 on secondary text**. Non-text parts of controls need 3:1.

Shared and direction A, light:

| Pair | Ratio | Need | Result |
|---|---|---|---|
| ink `#10251b` on page `#f2f5f2` | 14.68 | 7 | pass |
| ink on surface `#ffffff` | 16.12 | 7 | pass |
| ink on green-soft `#e1ede6` (assistant turn) | 13.40 | 7 | pass |
| ink on gold-soft `#fff1cc` (Grace's row, callout) | 14.36 | 7 | pass |
| ink on part-soft `#e3edf7` | 13.61 | 7 | pass |
| muted `#53655a` on surface | 6.22 | 5 | pass |
| muted on page | 5.66 | 5 | pass |
| muted on gold-soft (helper text in the callout and in Grace's row) | 5.54 | 5 | pass |
| muted on green-soft (date tile month, help panel text) | 5.17 | 5 | pass |
| green `#005030` on surface | 9.59 | 7 | pass |
| green on page | 8.73 | 7 | pass |
| green on green-soft (working label, pill) | 7.97 | 5 | pass |
| green on gold-soft | 8.54 | 5 | pass |
| white on green (primary button, current item, student turn) | 9.59 | 7 | pass |
| white on green-hover `#003d24` | 12.40 | 7 | pass |
| part `#2e5f8a` on part-soft (partly label) | 5.68 | 5 | pass |
| gold-ink `#7a5600` on gold-soft (planned label, "new" pill) | 5.92 | 5 | pass |
| gold-ink on surface | 6.65 | 5 | pass |
| gold-ink on page | 6.05 | 5 | pass |
| on-gold `#1d1503` on gold `#fdb71e` (Registered, avatar) | 10.31 | 7 | pass |
| page `#f2f5f2` on ink (toast) | 14.68 | 7 | pass |
| danger `#b3261e` on surface | 6.54 | 5 | pass |
| line-strong `#66796e` on surface / page / green-soft | 4.64 / 4.23 / 3.86 | 3 (non-text) | pass |
| gold on green (C's numerals; focus ring on green) | 5.46 | 4.5 | pass |
| **gold on surface** | **1.75** | — | **fail: decorative only. Never text, never a border or ring that carries meaning on white** |
| **gold on page / on green-soft** | **1.60 / 1.46** | — | **fail: the ring's target mark needs a dark keyline and a text label (section 7.13)** |
| **line `#d6dfd8` on surface** | **1.36** | — | **decorative only** |
| speaker label at 70% opacity on green-soft / on green (her treatment) | 5.48 / 5.58 | 5 | pass, but use `--sm-muted` or solid white instead of opacity |

Focus ring: 3px solid, 2px offset. `--sm-green` on light surfaces (9.59:1 on white, 8.73:1 on page); `--sm-gold` on green surfaces (5.46:1). Her gold ring on white (1.75:1) is not used.

### 6.4 Dark theme (optional)

Light is the default **whatever the operating system says**; the mockups do not follow `prefers-color-scheme`. Dark turns on only from the guide panel's theme control (N9) or `?theme=dark`, as `data-theme="dark"` on `<html>`. A direction may skip dark; if it ships dark it uses these values and passes these pairs.

| Token | Dark value (Ann's) | Pair | Ratio |
|---|---|---|---|
| `--sm-page` | `#0c1611` | ink on page | 15.71 |
| `--sm-surface` | `#14211a` | ink on surface | 14.17 |
| `--sm-ink` | `#e6efe9` | ink on green-soft / gold-soft | 11.68 / 11.33 |
| `--sm-muted` | `#9db0a4` | muted on surface / page | 7.27 / 8.06 |
| `--sm-line` | `#28392f` | decorative | — |
| `--sm-line-strong` | `#7d978a` (new) | on surface / page | 5.28 / 5.85 |
| `--sm-green` | `#5fbf8c` | on surface | 7.38 |
| `--sm-on-green` | `#07150e` | on green | 8.30 |
| `--sm-green-soft` | `#1b3227` | green on it / muted on it | 6.08 / 5.99 |
| `--sm-gold` | `#fdb71e` | on-gold `#1d1503` on it | 10.31 |
| `--sm-gold-soft` | `#3a2e10` | gold-ink on it / muted on it | 9.05 / 5.82 |
| `--sm-gold-ink` | `#fdcf63` | — | — |
| `--sm-part` / `--sm-part-soft` | `#93bce4` / `#1b2a3a` | part on part-soft | 7.33 |

### 6.5 Charts

All four chart kinds in her prototype are single-series. Keep them that plain.

| Chart | Form | Rules |
|---|---|---|
| Horizontal bars (overview ×4, partner ×1, growth ×1) | Label · bar · value | Bars start at zero. The scale maximum is the one in section 2 (46, 100, 8, or max(3, n)); never rescale to make a bar look fuller. Every bar has its number printed beside it, tabular. Bar height 12–16px, track in `--sm-green-soft`, fill green; the "gold" variants use `--sm-gold` fill **with a 1px `--sm-gold-ink` outline** so the bar edge is 3:1 against the track |
| Funnel (partner) | Three bars, widths 70% × value ÷ 30 with a 16% minimum, the number inside the bar, the label after it | Keep her arithmetic. The label is text, not a legend |
| Ring (readiness) | One arc, 0–100% | Starts at 12 o'clock, clockwise. The number is in the centre and again in tile 1. Target mark: section 7.13 |
| Progress dots (markers) | Three dots per marker | `aria-hidden`; the steps below carry the meaning in words. When on, dots one and two are green and the third is gold, in every direction |

No axes, gridlines, legends, 3D, gradients, pie or donut charts for comparison, or animation that overshoots the true value. Charts that are "illustrative" keep that word in their label. Each chart group has a text equivalent: the label and number pairs are real text in DOM order.

## 7. Component inventory

States: **D** default, **H** hover, **F** focus-visible, **P** pressed, **Dis** disabled, **L** loading, **E** empty, **X** error. "n/a" means the state cannot occur in these mockups; the reason is given.

Conventions that apply to every component:

- **Disabled is `aria-disabled="true"`**, never the `disabled` attribute. The control stays focusable, ignores activation, shows 45% opacity with a `not-allowed` cursor, and points at its reason with `aria-describedby` (N8).
- **Loading:** nothing in a mockup is fetched, so no mockup shows a loading state. The L column says what the React port does; it is not audited.
- **Focus-visible:** the ring of section 6.3 on every tab stop. Never removed, never replaced by a colour change alone. The screen title is not a tab stop: `h1[tabindex="-1"]` takes focus by script on a stop change and never draws a ring, whether the change came from the pointer, the keyboard or a clicker (a clicker is a keyboard).
- **Hit area:** at least 44×44px; the drawn height is section 5.6's.
- **Pressed:** scale 0.98 for 100ms on buttons, chips, doors and tiles (`sm-press`); colour change only under reduced motion.
- **Class names:** `sm-<component>`, parts as `sm-<component>__<part>`, variants and states as attributes (`data-variant`, `data-state`, `aria-*`), the way Radix exposes state. Section 10.3 maps them to the app.

### 7.1 App shell and portal switcher (`sm-shell`)

Holds the logo, portal name, identity line, `Switch portal`, the navigation, the main region, marker N1 and the guide button. The shape is per direction (Part 2). The switcher always offers the three portals with their door titles; the entry screen is itself the full-size switcher. `Switch portal` returns to the entry: directly in A and C; in B through its popover, whose first option is the entry (section 13.4).

| State | Treatment |
|---|---|
| D | Per direction |
| H / F / P | On its controls |
| Dis | n/a: every portal is always available |
| L | Port: shell renders at once; the main region shows the screen's skeleton |
| E | n/a |
| X | n/a |

### 7.2 Navigation (`sm-nav`)

A `<nav>` named after the portal, a list of buttons or links, one with `aria-current="page"`.

| State | Treatment |
|---|---|
| D | Label at 16–18px, weight 600 |
| H | `--sm-green-soft` fill |
| F | Ring |
| P | `sm-press` |
| Current | Not colour alone: fill **and** weight or a marker bar, plus `aria-current` |
| Dis / L / E / X | n/a: every screen exists |

### 7.3 Button (`sm-button`)

| Variant | D | H | F | P | Dis |
|---|---|---|---|---|---|
| `primary` | Green fill, white label, 600, radius md, min height per 5.6 | `--sm-green-hover` | Ring | `sm-press` | 45% opacity, reason by `aria-describedby` |
| `secondary` (her "ghost") | Transparent, 1px green outline, green label | `--sm-green-soft` fill | Ring | `sm-press` | as primary |
| `confirmed` (her "done") | Gold fill, `--sm-on-gold` label, check icon; `aria-disabled="true"` once registered | none | Ring | none | — |
| `link` (her "linkbtn") | Green text, underline 1px, offset 3px | Underline 2px | Ring | — | — |
| `inline` (inside a callout or a bot turn) | Primary at the compact size: padding 8 / 12 | as primary | Ring | `sm-press` | — |

- One primary per region. Where her layout puts two filled buttons side by side (the help panel, the partner "Stay involved" row), keep her variants: they are peers in a group, not competing calls to action.
- L: port only; the label changes to the in-progress verb. E / X: n/a.
- Hit area at least 44×44px at every width; the drawn height is section 5.6's (40px in B).

### 7.4 Status label (`sm-status`), marker N1 (`sm-marker`), scripted line N2 (`sm-scripted`)

The three honesty components. They share rules: never interactive, never dismissible, never animated, never truncated, never under 14px (N1 never under 16px), always icon **and** words. Their colours are the ones in this table in every direction; Part 2 does not re-tone them.

| Component | Content | Treatment |
|---|---|---|
| `sm-status[data-kind="working"]` | her string | `circle-check` icon, green on green-soft |
| `sm-status[data-kind="partly"]` | her string | `circle-dot` icon, part on part-soft |
| `sm-status[data-kind="planned"]` | her string | `circle-dashed` icon, gold-ink on gold-soft |
| `sm-marker` | N1 | `info` icon, ink on gold-soft or on the direction's quiet surface, 16px or more; fixed in the shell so it is on screen in every state, including with the guide open |
| `sm-scripted` | N2 | `info` icon, gold-ink on gold-soft in every direction, pinned to the top edge of the transcript, outside the scrolling log. It stays in the viewport, clear of any sticky header, whenever its transcript is in use (section 7.10) |

States: D only. H, F, P, Dis, L, E, X are n/a: they are static text. The status label sits in the screen header, on the title's row at `xl` and directly under the title at `sm`; its width is its content (her check-in "Planned" label stretching full width is a bug).

### 7.5 Card and door (`sm-card`, `sm-door`)

| State | `sm-card` (static container) | `sm-door` (entry button) |
|---|---|---|
| D | Surface, radius lg, border or shadow per direction, padding 24 (16 at `sm`) | Card with eyebrow, title, body, action line with `arrow-right` |
| H | n/a | Border to green or elevation 1→2, translateY(-2px), arrow moves 4px (`sm-lift`) |
| F | n/a | Ring around the whole door |
| P | n/a | `sm-press` |
| Dis / L / E / X | n/a | n/a |

### 7.6 Chip and pill (`sm-chip`, `sm-pill`)

| Kind | Use | States |
|---|---|---|
| `sm-chip[data-kind="option"]` | Interview reply options, bot suggested questions, slots, resources | D outlined (line-strong), H green-soft fill, F ring, P `sm-press`. Not toggles: activating one acts at once |
| `sm-chip[data-kind="toggle"]` | The 13 industries | `aria-pressed`. On: green fill, white label, **and a check icon** (not colour alone). Off: outlined |
| `sm-pill` | Read-only values: interests on the card (`data-tone="new"`: gold-soft / gold-ink in A and C, `--b-sunk` / ink in B), `Completed` (green-soft / green), tags `attended`, `registered`, `recorded later`, `+20 points` | D only |

Drawn min height 40px with a 44×44px hit area; chip label 16px or more in every direction; pills 14px or more.

### 7.7 Table (`sm-table`)

Real `<table>` with `<th scope="col">` at `md` and up. At `sm` each row becomes a stacked block with the same content in the same order (an `<ol>` for the ranked list, a `<ul>` for records), each value prefixed by its column name in muted text.

| State | Treatment |
|---|---|
| D | Section 5.6 |
| H | Row wash `--sm-page` on pointer devices; rows are not interactive |
| F | The scroll box is focusable (`tabindex="0"`, named by the table's caption) when it scrolls |
| Highlight | Grace's row: `--sm-gold-soft` fill **and** an `id-card` icon with visually hidden text "Grace Delgado, the student from the demo" before her name, with a space between the hidden text and the name |
| P / Dis | n/a |
| L | Port: 8 skeleton rows |
| E | N6 or N7 in the table's place, in a quiet card; the header row stays. On `match` the line "Showing 15 of the top 30." is hidden while N7 shows |
| X | n/a |

### 7.8 Weight control (`sm-weight`)

Four of them. A native `<input type="range" min="0" max="10" step="1">` with a visible label and the value beside it (tabular, at least 18px). It maps to the Radix `Slider`.

| State | Treatment |
|---|---|
| D | Track 6px `--sm-green-soft` with a 1px `--sm-line-strong` outline; filled part green; thumb 24px green disc with a 2px white ring; hit area 44px |
| H | Thumb 28px |
| F | Ring on the thumb; the value turns weight 700 |
| P (dragging) | Thumb 28px; the list re-ranks on every `input` event (section 8.3) |
| Dis | n/a: weights are always editable |
| L | Port: the control stays live while a list is rebuilt |
| E | All four at 0 → table empty state N7 |
| X | n/a: the range cannot hold a bad value |

Keyboard: arrows ±1, Home 0, End 10. `PageUp` and `PageDown` are not slider keys here: from inside a slider they change stop, as from any other control, and the weight does not move (section 7.16). The guide's `match` step 2 has the presenter move "Same major" with the pointer, which leaves focus on the slider; the next clicker press still goes to stop 9.

Layout: the value sits clear of the thumb and of its focus ring at every value, 10 included; neighbouring controls are at least `--sm-space-6` apart, so one control's value never reads as part of the next label; a label never wraps onto a track (the four controls fall to two columns when their row is under 900px wide).

### 7.9 Event picker (`sm-event-picker`)

Chooses one of five events on `match`. Label `Event`. Options are her five strings (section 2.10).

| Width | Form, in every direction | Maps to |
|---|---|---|
| 640px and up | A native `<select>`, wide enough to show the longest option whole ("Northline Analytics: Behind the Business · Thu Mar 4, 2027") | Radix `Select` |
| Under 640px | A radio list (`<fieldset>` with the legend `Event`), one option per row, so no option is cut: each row is a 24px control column, a 12px gap and the option text, padding 12 / 16, all five rows aligned alike | Radix `RadioGroup` |

Where the picker sits is per direction (Part 2). B also lists the same five events in its command switcher (section 13.4). `PageDown` and `PageUp` on the focused picker change stop, not the event (section 7.16).

States: D, H, F, P as for the control used. Dis, L, E, X: n/a.

### 7.10 Transcript (`sm-transcript`) and bot panel (`sm-bot`)

One component, two uses: the interview, and the assistant bot panel.

| Part | Rule |
|---|---|
| Container | `sm-scripted` (N2) pinned on top; below it the scrolling log; below that the reply area. The log scrolls so the newest turn is fully visible, starting at the top of a turn, never mid-line; on returning to a finished interview (`PageUp`, a deep link, a reload) it opens at the top of the last assistant turn, not at the end of the log. The log is at least 240px tall: on a short viewport the page scrolls, the log does not shrink. Using the transcript never scrolls N2 or the newest turn out of the viewport or under a sticky header; a focus move made by script uses `focus({ preventScroll: true })` and then scrolls on purpose |
| Assistant turn | Left, green-soft (B: `--b-sunk`), speaker label above the text ("Smart Match assistant" / "CBACH assistant bot · AI") in muted 14px, text 18px (16px in B). May contain bold spans and one `inline` button |
| Student turn | Right, green fill, white text, with visually hidden prefix "Grace:" |
| Reply area | Option chips, then (where section 2.4 allows) the free-text field and `Send`. On turn 2: the 13 toggle chips and `Done`. After a bot suggested question is pressed, focus stays on that chip |
| One press, one answer | A newly rendered turn's controls ignore activation for 350ms, and the second click of a double-click (`event.detail > 1`) is ignored. A rapid double-press therefore answers the current turn once and never activates the control of the next turn that lands under the pointer: it cannot toggle a third industry, answer "No thanks", or press "Show my events". The same guard covers the bot's chips |
| Field | Visible or visually hidden label per section 2; placeholder as hers; `Send` is `aria-disabled` while the field is empty, described by N8; Enter submits |
| Finished | "Interview finished." and `Start over` (secondary) |

| State | Treatment |
|---|---|
| D | As above |
| H / F / P | On chips, field and buttons |
| Dis | `Send` with an empty field |
| L | **None, by rule.** No typing dots, no "thinking…", no streamed text. A scripted turn appears whole (section 8.4) |
| E | The interview starts with turn 1 already present; the bot with its first turn. Never an empty log |
| X | n/a |

Live region: one visually hidden `role="log"` `aria-live="polite"` node per transcript receives **only the newest assistant turn's text**, once. The visible log is not a live region.

### 7.11 Toast (`sm-toast`) and persistent message (`sm-message`)

Her prototype uses one toast for everything. Split it:

| Kind | Used for | Behaviour |
|---|---|---|
| `sm-toast` | Points only: "Profile card saved. 20 points added.", "Registered. 10 points added.", "Self-check saved. 5 points added." | Bottom centre, ink background, page-colour text, 18px. Stays 4 seconds (hers: 2.3), pauses on hover and focus, one at a time, never covers the guide button or marker N1. `role="status"` |
| `sm-message` | Every outcome a presenter may talk over: "Booked: …", "Sent. A CBACH advisor usually replies…", "Opens: …", "Opens the Career Hub page: …", the three partner outcomes, the invitations sentence | A persistent line in a quiet card (`--sm-green-soft`, `circle-check` icon, her sentence) directly under the control that caused it. It stays until that region changes or the screen is left. `role="status"`, announced once |

States for both: D only (plus the toast's enter and exit). No close button is needed on `sm-message`; the toast has none either (it is not the only carrier of its news: the points number also changes).

### 7.12 Check-in card (`sm-checkin`)

Hidden until the first registration. Parts: the sample code, label "Check-in code", `{title} · {when}`, her sentence, `sm-status` "Planned", and the points block.

- Draw the code from `SMC.qrCells(eventId)` as an SVG: white 29×29 plate, a dark 1×1 rect per cell, three 7×7 finder squares (dark, then 5×5 white, then 3×3 dark) at the given origins. Dark is always `#10251b` on `#ffffff`, in both themes, at 116–160px.
- It is a made-up pattern, not a working code. Keep "Sample code only." beside it. Accessible name: "Sample check-in code".
- No "scanning" animation, no pulse, no fake camera frame.

States: D. E: hidden (her behaviour). H, F, P, Dis, L, X: n/a.

### 7.13 Stat tile (`sm-stat`), ring (`sm-ring`), bars (`sm-bars`), funnel (`sm-funnel`)

| Component | Rule |
|---|---|
| `sm-stat` | A big figure (28px or more, tabular, green) over its label (16px or more, muted). The figure and label are one group for screen readers ("300 student records loaded"). D only; a changing figure tweens once (section 8.3) |
| `sm-ring` | 150–200px. Track green-soft, arc green, round caps. **Target mark:** a 4px-wide radial tick across the track in gold with a 1px `--sm-ink` keyline on each side, and the text "60% target" beside the ring or as tile 2 (her tile 2 already says it). The SVG has `role="img"` and the name "13% career ready. Target for a junior: 60%." |
| `sm-bars` | Section 6.5. Label column wide enough for the longest label without truncation ("Brand Building at a Streaming Studio" wraps to two lines; it is never cut) |
| `sm-funnel` | Section 6.5 |

L: port shows a skeleton. E, X, H, F, P, Dis: n/a.

### 7.14 Calendar and event row (`sm-event`), timeline (`sm-timeline`), marker card (`sm-marker-card`), help panel (`sm-help`)

| Component | Parts | States |
|---|---|---|
| `sm-event` | Date tile (day 24px or more over month), title (`h3`), meta line, reason chip ("Why you:" in gold-ink 600, then the reason in ink, on gold-soft; in B on `--b-sunk` with "Why you:" in ink or green), `Register` button, match line (16px or more in every direction, tabular) | D. The button carries H / F / P and the `confirmed` variant. Not a link; the row itself is not clickable |
| `sm-timeline` | An `<ol>` of five terms; past terms have a filled green dot, future terms a gold ring with a 1px `--sm-gold-ink` keyline **and** the tag "recorded later" (not colour alone), in every direction | D only |
| `sm-marker-card` | Name (`h3`), three dots (`aria-hidden`), three steps, two links | Step 1 checkbox: D, H, F, checked, with its level text "I checked myself". Steps 2 and 3: a state mark with visually hidden "done" or "not yet", and the level text |
| `sm-help` | Avatar "CB" (`aria-hidden`), heading, body, two labelled groups of two buttons; each button has `aria-expanded` and `aria-controls` for its panel | D; the open panel's button shows a pressed style and `aria-expanded="true"`. An opening panel is scrolled into view at every viewport, so its label (and, in the bot panel, N2) is on screen and clear of any sticky header |

### 7.15 Fields (`sm-field`)

Search (`records`), free text (`interview`, bot), message textarea, the share checkbox.

| State | Treatment |
|---|---|
| D | Surface fill, 1px `--sm-line-strong` outline, radius md, text 18px (16px in B), label visible above (search, message) or visually hidden (the two chat fields, as hers) |
| H | Outline green |
| F | Ring |
| Dis | n/a |
| E | Placeholder as hers; it is a hint, not the label |
| X | n/a: no field can hold an invalid value. An empty send is handled by the `aria-disabled` Send button and N8 |

Search keeps focus and caret while the table updates, and reports the count line ("14 of 300 records") in a polite status region, debounced 400ms. Enter in the search field releases focus (the typed text and the filtered rows stay), so the next `PageDown` changes stop (section 7.16).

### 7.16 Presenter guide (`sm-guide`)

Equal to Ann's, plus stop controls.

| Part | Rule |
|---|---|
| Button | `Presenter guide` / `Hide presenter guide`, `aria-expanded`, shortcut `G` (when focus is not in a text input or textarea). Its words and behaviour are fixed; its place is per direction. **It never covers a control or a line of text, at 1440×900, 1280×720 or 390×844, at any scroll position;** bottom padding on the main region does not meet this on its own. So on portal screens it is docked in the shell: A in the top bar beside `Switch portal`, B at the foot of the sidebar (in the top strip at `md` and below), C at the right end of the rail. It may float at the bottom right, above the safe area, only where nothing sits behind it (the entry in A and B) |
| Panel | A non-modal `<aside aria-label="Presenter guide">`, width min(400px, 100vw − 32px), max height 70vh, own scroll. Content for the current screen from section 2.12, in this order in every direction: eyebrow, title, intent, numbered steps, the `Say:` line (on gold-soft; in B on `--b-sunk`), then the stop controls, then reset and theme |
| Stop controls (N4) | "Stop {n} of 9", `Back`, `Next`, below the `Say:` line. They move through section 2.1's order and switch portal when needed. `Back` is `aria-disabled` on stop 1, `Next` on stop 9 |
| Keys | `PageDown` / `PageUp` = next / previous stop, always: in every mockup, guide open or closed, from any focused control (a weight slider, the event picker, a radio, a checkbox, a button). The one exception is a text input or a textarea, where the keys keep their native job. The handler calls `preventDefault()`, so the focused control's own value never changes on a Page key. Enter in the records search releases focus (section 7.15), so the clicker works again after the scripted search. `Esc` closes the panel and returns focus to the button |
| Reset (N5) | `Reset demo`: first press changes the label to `Press again to reset` for 5 seconds with a shrinking underline; second press clears the state and goes to the entry; `Esc` or the lapse reverts. A held key never confirms |
| Theme (N9) | A two-button group `Light` / `Dark`, `aria-pressed`, only if the direction ships dark |
| Projection | The panel is for rehearsal. It opens closed on first load and remembers its state. It must not overlap the screen's hero region at 1440×900 (it may overlap secondary content) |

States: D, H / F / P on its controls. Dis on `Back` / `Next` at the ends. L, E, X: n/a.

### 7.17 Dialogs

Her prototype has none, so the mockups have none: no modal, no confirm pop-up, no focus trap. Confirmation is inline (N5). Direction B's switcher is a non-modal popover, not a dialog.

## 8. Motion system

### 8.1 Principles

1. **Motion shows cause and effect.** A weight moves, the list re-sorts. An answer is given, the card fills. Nothing moves that the presenter did not cause.
2. **The presenter never waits.** Every primary action is usable again within 400ms, and any click or key during an animation completes it at once and acts. One guard only: a new transcript turn's controls wait 350ms and drop the second click of a double-click (section 7.10), so one press gives one answer.
3. **Fast in, faster out.** Exits take at most two thirds of the matching entrance. Table rows leaving a ranked list have no exit at all (`sm-rerank`).
4. **Scripted things do not pretend.** No typing indicator, no streamed text, no "analysing" pause (H3).
5. **Once, then rest.** Entrances and count-ups run once per arrival. No loops, no idle or ambient motion, no auto-advance.
6. **Reduced motion keeps the meaning.** The end state is identical; only the travel is removed.

### 8.2 Tokens

CSS custom properties for CSS transitions, and the same values as a JS object for GSAP. Both live in each mockup; the names are fixed.

| Token | Value | Use |
|---|---|---|
| `--sm-dur-instant` | 100ms | Press, colour change |
| `--sm-dur-fast` | 160ms | Hover, exits, popover in |
| `--sm-dur-base` | 220ms | Panel and turn entrances, cross-fades |
| `--sm-dur-move` | 280ms | Things that travel: row re-rank, shared-element moves |
| `--sm-dur-max` | 400ms | Ceiling for anything tied to a primary action: count-ups, ring draw, scene change |
| `--sm-dur-wash` | 900ms | The only longer value: a highlight wash fading out after its row has landed. Never blocks, never moves anything |
| `--sm-stagger` | 30ms per item, 8 items at most | Lists entering |
| `--sm-ease-out` | `cubic-bezier(0.16, 1, 0.3, 1)` · GSAP `expo.out` | Arrivals |
| `--sm-ease-in-out` | `cubic-bezier(0.65, 0, 0.35, 1)` · GSAP `power2.inOut` | Moves between two resting places |
| `--sm-ease-in` | `cubic-bezier(0.7, 0, 0.84, 0)` · GSAP `power2.in` | Departures |

```js
const SM_MOTION = {
  dur:  { instant: 0.10, fast: 0.16, base: 0.22, move: 0.28, max: 0.40, wash: 0.90 },
  ease: { out: "expo.out", inOut: "power2.inOut", in: "power2.in" },
  stagger: 0.03
};
```

No bounce, elastic or back easing. No spring overshoot on data.

### 8.3 What animates

| Name | Trigger | What moves | Duration / ease | Reduced motion |
|---|---|---|---|---|
| `sm-press` | Pointer or key down on a button, chip, door | scale 1 → 0.98 → 1 | instant / out | Colour change only |
| `sm-lift` | Hover on a door or hoverable card | translateY(-2px), elevation or border change | fast / out | Border or shadow change only |
| `sm-screen` | Screen change inside a portal | Outgoing main: opacity → 0 (fast / in). Incoming main: opacity 0 → 1, y 8 → 0 (base / out). Focus moves to the new `h1` at once, not after the tween | fast + base | Opacity only, 150ms |
| `sm-portal` | Entry → portal, portal → entry, portal → portal | Per direction (Part 2), built from these tokens, never over `max` | ≤ max | Opacity only, 150ms |
| `sm-rerank` | A weight or the event changes on `match` | FLIP on transforms (GSAP Flip, `simple: true` allowed, or a hand-written FLIP on GSAP core; section 8.5): rows that stay in the visible 15 travel to their new positions (transform only); rows entering the visible 15 fade in (base); rows that drop out of the visible 15 are removed on the first frame, with no exit animation; rank numerals change at the start, not mid-flight. A new change while rows are moving re-targets from where they are (`overwrite: true`); nothing queues | move / inOut | Rows swap at once; 150ms opacity cross-fade on the table body |
| `sm-wash` | A row lands in a new position; Grace's row always keeps its tint | Rows that entered get a gold-soft wash that fades out | wash / out | No wash |
| `sm-count` | A figure changes because of the presenter's action (points, readiness %, tile counts, slider value) | The number tweens through whole values to the new value; tabular figures so the width holds | ≤ max / out | New value at once |
| `sm-ring-draw` | First view of the ring; a self-check ticked | Arc length tweens via `stroke-dashoffset` (a paint-only property on one element; the one allowed exception to "transform and opacity") | max / out | Final arc at once |
| `sm-bars-grow` | First view of a bar group | `scaleX` from 0, origin left, 30ms stagger; numbers are in place from the first frame | base / out | Final at once |
| `sm-turn` | An interview or bot turn is added | Student turn: opacity + y 6 → 0 (fast). The assistant's reply follows 80ms later: opacity + y 6 → 0 (base), whole, with the reply options appearing in the same beat. Options are visible from the first frame and take activation once the 350ms double-press guard has passed (section 7.10) | fast, then base | Opacity only, 150ms |
| `sm-card-fill` | A profile-card value changes | The "Not yet" text cross-fades to the value; a new interest pill scales 0.9 → 1 with opacity | base / out | Opacity only |
| `sm-register` | `Register` pressed | Button cross-fades to the `confirmed` variant; the check icon draws in (fast). The check-in card enters (opacity + y 8 → 0, base) and the page scrolls only as far as needed to show the code and the points (≤ max), keeping the pressed button and its event title on screen (section 5.2) | ≤ max | Final at once; `scrollIntoView` with `behavior: "auto"` |
| `sm-panel` | A help panel opens or closes | Opacity + y 8 → 0 in (base); out is fast. Layout below jumps to its new place and is FLIP-ed with a transform, not animated by height. An opening panel is scrolled into view (≤ max; `behavior: "auto"` under reduced motion) | base / fast | Opacity only |
| `sm-guide` | Guide opens or closes | Panel: opacity + y 12 → 0 and scale 0.98 → 1 from the button's corner (base / out); out fast. Content swaps on screen change with a 120ms cross-fade | base / fast | Opacity only |
| `sm-toast` | Toast shows or hides | Opacity + y 8 → 0 (base); out fast | base / fast | Opacity only |
| `sm-confirm` | `Reset demo` armed | A 2px underline shrinks from full width to 0 over 5 seconds, linear (`scaleX`) | 5000ms linear | No underline; the label alone carries it |

### 8.4 What never animates

- Status labels, marker N1, scripted line N2, the logo.
- Text arriving character by character or word by word. Typing dots. Any "thinking" or "matching…" interstitial.
- The check-in code (no scan line, no pulse).
- Body copy position on hover; table text; focus rings (they appear at once).
- Anything on scroll: no parallax, no scroll-triggered reveals, no scroll-jacking, no pinned sections.
- Anything on a timer: no auto-advance, no carousel, no looping background, no idle bob.
- Layout properties: `width`, `height`, `top`, `left`, `margin`, `padding`, `grid-template-*`. Use Flip or a transform.
- Blur, `backdrop-filter`, `box-shadow` (cross-fade a pseudo-element's opacity instead), colour of large surfaces during a portal change.

### 8.5 Engine

- **GSAP 3.15.0** (the version on npm on 2026-10-06), core plus the **Flip** plugin. Nothing else: no ScrollTrigger, no SplitText, no Draggable.
- **Vendored**, not linked: `shared/vendor/gsap/gsap.min.js` and `shared/vendor/gsap/Flip.min.js`, copied unmodified from the `gsap@3.15.0` package's `dist/`, plus `shared/vendor/gsap/LICENSE.md`.
- **Licence note:** GSAP is not MIT. It ships under GreenSock's standard "no charge" licence, which since version 3.13 (2025, after Webflow acquired GreenSock) allows free use including commercial use and including the formerly paid plugins such as Flip. Keep the licence file beside the vendored copy and do not edit the library. Confirm the current terms at gsap.com before the real app adopts it; the app already ships `motion`, and the port may use that instead (section 10.3).
- CSS transitions are fine for hover, press and colour. Everything in 8.3 that travels, staggers or can be interrupted uses GSAP so it can be killed, re-targeted or completed. For the table re-rank that means either the Flip plugin (`simple: true` is allowed, and is the cheaper path on table rows) or a hand-written FLIP (read positions, change the DOM, tween the inverse transform to zero) on GSAP core; both meet section 8.7.
- One `gsap.matchMedia()` block per mockup switches every tween to its reduced-motion form.

### 8.6 Reduced motion

`@media (prefers-reduced-motion: reduce)`, or `?rm=1`, or `data-motion="reduced"` on `<html>`: every row in 8.3 uses its last column. No transform travels more than 0px; opacity fades of 150ms are allowed. Count-ups, ring and bars show their final values on the first frame. The 5-second confirm keeps its timing without the underline.

### 8.7 Performance budget

| Budget | Limit |
|---|---|
| Properties animated | `transform` and `opacity` only (exception: the ring's `stroke-dashoffset`) |
| Elements moving at once | 32 (a re-rank moves at most the 15 visible rows, since rows that leave are removed, not animated; the rest is room for chrome and staggered lists) |
| Frame time | Measured on the classroom laptop, in Chrome DevTools with 4× CPU throttle: dragging "Same major" from 3 to 10 produces no frame over 50ms and no long task over 50ms |
| Layout thrash | One read phase, then one write phase per change (Flip's `getState` → DOM change → `Flip.from`, or the same three steps by hand). No forced reflow inside a loop |
| `will-change` | Set by GSAP for the tween's life only; never in the stylesheet at rest |
| Re-rank work | `SMC.rankStudents` on every `input` event is cheap (300 rows); render at most once per animation frame |
| Time to interactive | Under 1 second from double-click to the entry being clickable, from disk |
| Interruptibility | Any pointer or key event during a tween on the same region calls `progress(1)` or re-targets. `PageDown` during a scene change lands on the next stop, not the middle of a transition |

## 9. Accessibility floor (WCAG 2.2 AA)

### 9.1 Structure and landmarks

- One `<header>` (shell), one `<nav aria-label="{portal name}">`, one `<main id="main" tabindex="-1">`, one `<aside aria-label="Presenter guide">`. The entry has no `nav`.
- One `<h1>` per screen (the screen title; on the entry, "Smart Match CPP"). Block labels are `<h2>`; event titles, marker names and card names are `<h3>`. Two screens have no visible block label, so: `recs` carries a visually hidden `<h2>` "Events for me" (its menu label, not a new string) before the event list, and on `interview` the profile card's name "Grace Delgado" is an `<h2>`. No skipped levels.
- `<html lang="en">`, `<title>Smart Match CPP</title>`.

### 9.2 Keyboard order

Tab order follows reading order: skip link (N3) → switch portal → navigation → main content in visual order → guide button → guide panel when open. A guide button docked in the shell (section 7.16) takes its place in the shell's reading order instead, with its panel straight after it. Specifics:

| Screen | Order inside main |
|---|---|
| `entry` | Door 1, door 2, door 3 |
| `interview` | Reply options (or the 13 toggles, then `Done`), free-text field, `Send`; after finishing, `Start over`. The profile card is not focusable |
| `recs` | Callout button (before interview), then each event's `Register` in order |
| `readiness` | `Go`, the four help buttons, the open panel's controls, then each marker's checkbox and two links |
| `records` | Search, then the table scroll box if it scrolls |
| `match` | Event picker, the four weights, the table scroll box, `Send personal invitations to top 30` |
| `talk` | The three "Stay involved" buttons |

- On a screen or portal change, focus goes to the new `<h1>`. It is `tabindex="-1"`: a target for script, not a tab stop, and it never draws a focus ring (section 7).
- Opening a help panel moves focus to the panel's label. `Ask the assistant bot` on a marker card moves focus to the bot field. The booking button inside a bot turn moves focus to the booking panel's label. Pressing a bot suggested question leaves focus on that chip. None of these moves may scroll N2 out of view (section 7.10).
- After `Register`, focus stays on the button (now `confirmed`).
- No keyboard trap anywhere; no positive `tabindex`.
- Shortcuts are single keys (`G`, `PageDown`, `PageUp`, and in B `Ctrl`/`⌘`+`K`). They are off only while focus is in a text input or a textarea; from every other control, sliders and the event picker included, `PageDown` and `PageUp` change stop (section 7.16).

### 9.3 Focus, targets, contrast

- Focus-visible ring per section 6.3 on every tab stop, both themes. The screen title (`h1[tabindex="-1"]`) draws none.
- Hit areas at least 44×44px, the skip link included (WCAG 2.2 asks 24; the room and the clicker ask more). The drawn box may be 40px tall for chips in any direction and for all controls in B (section 5.6).
- Contrast per section 6.3; each direction lists its own neutrals in Part 2 and in its NOTES.

### 9.4 Live regions (announce once)

| Event | Region | Text |
|---|---|---|
| Toast | `role="status"` | The toast sentence |
| Outcome message | `role="status"` on the `sm-message` | Her sentence |
| New assistant or bot turn | One hidden `role="log"` per transcript | The newest turn only |
| Re-rank | One hidden `role="status"` on `match`, debounced 600ms after the last change | The Grace line (for example "Grace Delgado is #4 on this list because of her interview answers.") |
| Search | Hidden `role="status"`, debounced 400ms | "14 of 300 records" |
| Readiness change | Hidden `role="status"` | "Readiness now 17%." is **not** added (no new strings): the toast sentence is enough |

Never `aria-live` on a container that is re-rendered whole. Never `role="alert"`: nothing in these mockups is urgent.

### 9.5 Not by colour alone

| Meaning | Second cue |
|---|---|
| Status kind | Icon + her words |
| Current navigation item | Weight or marker bar + `aria-current` |
| Selected industry | Check icon + `aria-pressed` |
| Grace's row | Icon + hidden text |
| Step done | Check mark + hidden "done" |
| Future term | Ring dot (not filled) + the tag "recorded later" |
| Gold bars against green bars | They are separate charts with their own labels; colour is not the key |
| Registered | Label change + check icon |
| New from the interview | The group label "From the interview" |

### 9.6 Other

- Images: logo alt `Cal Poly Pomona`; check-in code name "Sample check-in code"; ring name per 7.13; decorative marks `aria-hidden`.
- Zoom to 200% and text spacing overrides (WCAG 1.4.12) do not clip or overlap text.
- No content flashes. No motion starts without a user action.
- `overview` and `talk` charts are readable with CSS off: label and number pairs in DOM order.

## 10. Mockup engineering contract

### 10.1 Folders

```text
docs/design/cpp-prototype/
  DESIGN.md                      this file
  source/                        Ann's files (never edit)
  reference/                     screenshots of her prototype
  shared/
    data.js                      generated (section 3)
    vendor/
      gsap/gsap.min.js, Flip.min.js, LICENSE.md
      fonts/<family>/*.woff2, OFL.txt
  mockups/
    a-blueprint/    index.html  styles.css  app.js  NOTES.md  screenshots/
    b-workbench/    index.html  styles.css  app.js  NOTES.md  screenshots/
    c-walkthrough/  index.html  styles.css  app.js  NOTES.md  screenshots/
```

A builder writes only inside its own `mockups/<letter>-<slug>/` folder. `shared/` is read-only for builders; the orchestrator vendors GSAP and the fonts **once, before the builders start** (three builders writing the same vendor files would race).

### 10.2 Rules

| Rule | Detail |
|---|---|
| Opens from disk | Double-click `index.html`; it works under `file://` in Chrome and Edge. No server, no build step, no install |
| No network | Zero requests to any host. No CDN, no Google Fonts link, no analytics, no remote image. Audit with DevTools offline |
| Plain files | Hand-written HTML, CSS and JavaScript (ES2020). Classic `<script>` tags, no `type="module"`, no JSX, no TypeScript, no framework, no bundler, no CSS preprocessor, no Tailwind CDN |
| Libraries | GSAP core and Flip from `shared/vendor/`. Nothing else |
| Data | `shared/data.js` only. No copy of the 300 rows in a mockup folder |
| Rendering | Build DOM with `createElement` and `textContent`, or escape every interpolated value; typed answers are echoed into the transcript, so never put raw input into `innerHTML` |
| Storage | `localStorage` key `smc.<letter>.v1`, guarded; the page renders correctly when storage throws |
| Console | No errors and no warnings on load or on the guided path |
| Honesty | N1 on every screen; her status label on every screen; N2 in both transcripts |
| Guide | Section 7.16, with all nine entries of section 2.12 |
| Review links | The deep links of section 3.7 |

### 10.3 Structure that ports to the React and Radix app

The real app is React with Radix primitives and Tailwind under `apps/web/legacy-frontend`. Write the mockup so each block is a component a developer can lift.

- `app.js` is organised as one function per component (`renderStatus`, `renderEventRow`, `renderWeight`…) taking a props object and returning a DOM node, one function per screen composing them, and one `state` object with a single `setState` that re-renders the affected region. No component reaches into another's DOM.
- State lives in attributes Radix already uses: `data-state="open|closed|on|off|active|inactive"`, `data-disabled`, `aria-pressed`, `aria-expanded`, `aria-current`, `aria-disabled`. Style those, not ad-hoc classes like `.is-open`.
- Tokens are CSS custom properties on `:root` with the `--sm-` prefix; the dark set under `:root[data-theme="dark"]`. Components read tokens only; no raw hex in component rules.

| Mockup class | App component (`apps/web/legacy-frontend/src/app/components/ui/`) | Radix primitive |
|---|---|---|
| `sm-shell`, `sm-nav` | `sidebar.tsx`, `navigation-menu.tsx` | NavigationMenu |
| `sm-button` | `button.tsx` | Slot |
| `sm-status`, `sm-pill` | `badge.tsx` | — |
| `sm-marker` | `DemoModeBadge.tsx` (extend, do not copy) | — |
| `sm-card`, `sm-door`, `sm-stat` | `card.tsx` | — |
| `sm-chip[data-kind="toggle"]` | `toggle-group.tsx` | ToggleGroup |
| `sm-chip[data-kind="option"]` | `button.tsx` (outline, pill) | — |
| `sm-table` | `table.tsx` | — |
| `sm-weight` | `slider.tsx` | Slider |
| `sm-event-picker` | `select.tsx` / `radio-group.tsx` | Select / RadioGroup |
| `sm-field` | `input.tsx`, `textarea.tsx`, `checkbox.tsx`, `label.tsx` | Checkbox, Label |
| `sm-transcript`, `sm-bot` | new; uses `scroll-area.tsx` | ScrollArea |
| `sm-toast` | `sonner.tsx` | — |
| `sm-message` | `alert.tsx` | — |
| `sm-help` panels | `collapsible.tsx` | Collapsible |
| `sm-ring` | `progress.tsx` (new circular variant) | Progress |
| `sm-bars`, `sm-funnel` | `chart.tsx` | — |
| `sm-guide` | `popover.tsx` (non-modal) | Popover |
| B's switcher | `command.tsx` in `popover.tsx` | Popover + cmdk |
| Motion | `motion` (already installed) or GSAP; the tokens of 8.2 either way | — |

Before the port: read `apps/web/AGENTS.md` and `apps/web/DESIGN.md`; the API contract wins over any mockup, and no mockup number, identity or "successful" action may be hard-coded in the app.

### 10.4 Fonts, offline

- Every font file is vendored under `shared/vendor/fonts/` as WOFF2 (Latin subset), loaded with `@font-face` and `font-display: swap`. All chosen families are under the SIL Open Font License 1.1; keep each `OFL.txt`.
- Suggested source: the `@fontsource-variable/<family>` npm packages (`files/<family>-latin-wght-normal.woff2`), copied unmodified.
- Every `font-family` ends in a local fallback stack, and the layout must hold on the fallback alone (Firefox blocks `file://` fonts outside the page's folder; a missing file must not break the room):

| Role | Fallback stack |
|---|---|
| Sans | `"Segoe UI", system-ui, -apple-system, "Helvetica Neue", Arial, sans-serif` |
| Serif (C) | `Georgia, "Times New Roman", serif` |
| Mono | `ui-monospace, "Cascadia Mono", Consolas, Menlo, monospace` |

- At most 2 families plus 1 optional mono per direction; at most 6 font files per direction.
- None of the app's licensed faces (Transducer CPP, Proxima Sera, Usual) and no other company's proprietary typeface may be used or imitated by name.

### 10.5 File-size budget

| File | Limit |
|---|---|
| `index.html` | 40 kB |
| `styles.css` | 70 kB |
| `app.js` | 90 kB, not minified |
| Other files in the mockup folder, excluding `screenshots/` | none (no images; icons are inline SVG) |
| `shared/data.js` | 97 kB (fixed) |
| `shared/vendor/gsap/` | about 110 kB (as shipped) |
| Fonts a direction loads | 400 kB |
| Each screenshot | PNG, 1440×900 or 390×844, 500 kB |

### 10.6 NOTES.md (house format)

Follow `docs/design/class-exercise/mascot-tutorial/redesign/b-friendly-tech/NOTES.md`. Sections, in order:

1. Title (`# Direction A: Blueprint`), then **Open** (the path to double-click), **Status** (mockup for owner review; not app code), **Files**.
2. Concept (one paragraph).
3. Palette: light table, dark list if shipped, and a computed contrast table for every pair the direction adds.
4. Type: families, weights, sizes, file cost.
5. Layout principles (numbered).
6. Motion: the signature moments and how each maps to section 8.
7. Review deep links.
8. Deviations from this DESIGN.md, each with a reason, and any `impeccable detect` findings kept on purpose.
9. Audit self-check: the section 11 item numbers the builder believes pass, and any that do not.
10. 3 things to refine next.

### 10.7 Screenshots

In `screenshots/`, named `<nn>-<screen>-<state>-<width>.png`. Required, at 1440×900 unless noted:

`01-entry` · `02-interview-turn1` · `03-interview-turn2` · `04-interview-finished` · `05-recs-before` · `06-recs-after-registered` · `07-readiness` · `08-readiness-bot` · `09-growth` · `10-overview` · `11-records-delgado` · `12-match-default` · `13-match-major-10` · `14-talk` · `15-guide-open` (on `match`) · `16-entry-390` · `17-interview-390` · `18-match-390` · `19-readiness-390`.

## 11. Audit checklist

Run each item against each mockup. Pass or fail; a fail names the screen and element. "Guided path" is section 2.4's.

**Honesty**

1. Marker N1 "Design for the next phase — made-up data" is visible on all 9 screens at 1440×900 and at 390, with the guide open and closed.
2. Each of the 8 portal screens shows its status label with the exact string of section 2.1, visible without scrolling at 1440×900; the check-in card shows "Planned".
3. N2 "Scripted for this demo. Not a live AI." is visible in the interview transcript and in the bot panel, and stays visible when the log is scrolled.
4. No typing indicator, "thinking" state or character-by-character text appears anywhere.
5. The entry shows her demo line verbatim.
6. The readiness screen shows "Planned · draft markers" and the closing "Draft markers for discussion…" line.
7. Every person named on any screen exists in `shared/data.js` or section 2 (Grace Delgado, Dana Whitfield, the 300). No file input exists.

**Copy**

8. Every string in sections 2.2–2.11 appears verbatim on its screen (case, punctuation, " · " separators), with only `→` and `✓` replaced by icons.
9. All five interview turns, both variants of turn 4, and every reply option match section 2.4.
10. All five bot rules return the answers of section 2.6; rules 2, 4 and 5 show the booking button.
11. All nine presenter-guide entries match section 2.12: title, intent, every step, and the `Say:` line.
12. No user-visible string exists outside section 2 (including N1–N10). W1–W5 are not applied unless ruled.
13. No text is truncated with an ellipsis or clipped by its container on any screen at 1440 or 390.

**Data and logic**

14. `shared/data.js` is loaded by a classic script tag and is byte-identical to the committed file; the mockup folder holds no copy of the student rows.
15. `console.table(SMC.selfTest())` shows `pass: true` on every row.
16. After the guided path, `match` with Northline selected shows the eight rows of TV-A in order, with the same reasons, and the line "Grace Delgado is #4 on this list because of her interview answers."
17. Setting "Same major" to 10 gives TV-B's first eight rows, all visible rows are Computer Information Systems, and the line reads "#27".
18. Before the interview (`?reset=1`), `match` shows "Grace has not done her interview yet, so the app knows little about her." and `recs` shows the three "Before interview" rows of section 2.5.
19. After the guided path, `recs` shows the three "After interview" rows of section 2.5 with "match 6 of 10", "match 4 of 10", "match 3 of 10".
20. Readiness reads 4% on a fresh load, 13% after the interview, 17% after also ticking "My LinkedIn profile is complete"; the target reads 60%.
21. Career points read the same on `recs`, `readiness` and `growth`: 20 fresh, 40 after the interview, 50 after one registration, 55 after one self-check (F3).
22. `overview` tiles read 300 / 100 / 70 / 200 fresh and 300 / 100 / 71 / 200 after the interview (F1); the four charts match section 2.8.
23. `records` shows 25 rows and "300 of 300 records" fresh; typing `Delgado` shows 14 rows, "14 of 300 records", and Grace's cell reads "AI interview · today" after the interview.
24. Choosing "Graduate school" at turn 3 leads to turn 4b and shows "Graduate school" on the card (F2).
25. Reloading the page mid-demo keeps the interview result, registrations and current screen; `Reset demo` (two presses) clears them.

**Layout and type**

26. Every computed `margin`, `padding` and `gap` is 0 or a value in section 5.1 (1px and 2px allowed on borders and outlines only).
27. Every computed `font-size` is a value in section 5.3; none is under 14px at 1440; marker N1 is at least 16px; read-aloud body text meets the floor for the direction; chip labels and the match line are at least 16px.
28. Every `border-radius` is a token of section 5.4; no surface has both a border and a shadow; no card nests more than one level.
29. At 1440×900 each screen shows the "above the fold" content of section 5.2 without scrolling.
30. At 390×844: no horizontal page scroll, tables are stacked rows, every control is reachable, text is at least 14px.
31. At 1280×720 the `match` screen still shows the picker, the four weights, the Grace line and at least 4 full rows, Grace's row #4 whole among them, without scrolling.
32. With web fonts blocked, no text overflows or overlaps at 1440 or 390.

**Colour and contrast**

33. `--sm-green` is `#005030` and `--sm-gold` is `#fdb71e`; the three status kinds use the shared colours of section 6.2.
34. Every text and background pair on screen is in section 6.3 or the direction's NOTES table, with a computed ratio of at least 4.5:1 (5:1 for secondary text, 7:1 for body text).
35. Gold is never text or a focus ring on a light surface, and never an outline there without a dark keyline: the gold bars and the future-term dot have their gold-ink keyline; the ring's target mark has a dark keyline and a text label. In every direction N2 is gold-ink on gold-soft and the third progress dot is gold.
36. Control outlines, slider tracks and empty step rings are at least 3:1 against their background.
37. Dark theme, in two parts:
    - **37a** (all directions). The page is light when the OS is dark.
    - **37b** (only where the direction ships a dark theme: A; B if kept). Dark appears only with `?theme=dark` or the theme control, and then passes section 6.4.
38. No meaning is carried by colour alone: check each row of section 9.5.

**Interaction and accessibility**

39. Tab order on each screen matches section 9.2; a visible focus ring shows on every stop; nothing traps focus.
40. The whole guided path, from the entry to `talk`, can be done with the keyboard only.
41. `PageDown` and `PageUp` move through the nine stops in order from any screen and from any focused control (a weight slider, the event picker, a checkbox, a button), without changing that control's value; they keep their native job only while focus is in a text input or a textarea. `G` toggles the guide.
42. On a screen change, focus is on the new `<h1>`, which draws no focus ring (also after `PageDown`); there is exactly one `<h1>`, one `<main>`, one named `<nav>` (none on the entry); no heading level is skipped (section 9.1).
43. No element uses the `disabled` attribute; disabled controls use `aria-disabled="true"` with a described reason.
44. Each transcript announces only the newest assistant turn, once; toasts and outcome messages are `role="status"`; no `role="alert"`.
45. Every target's hit area is at least 44×44px, the skip link included. The drawn box may be 40px tall for chips in any direction and for all controls in B.
46. Outcomes (booked, sent, opens, partner actions, invitations) appear as persistent messages with her wording, not only as a toast.
47. No modal dialog exists.

**Motion**

48. With `prefers-reduced-motion: reduce` (or `?rm=1`) nothing translates or scales; end states are identical; figures show final values at once.
49. No animation tied to a primary action runs longer than 400ms (only the 900ms wash and the 5-second confirm underline exceed it, and neither blocks input).
50. Clicking or pressing a key during any animation completes it and acts (the double-press guard of item 64 aside); dragging a weight re-targets rows that are still moving; rows that drop out of the visible 15 are gone on the first frame, with no exit animation.
51. Only `transform` and `opacity` are animated (plus the ring's `stroke-dashoffset`); with 4× CPU throttle on the classroom laptop, dragging "Same major" from 3 to 10 shows no frame over 50ms and no long task over 50ms.
52. Nothing animates on scroll, on a timer, or in a loop; status labels, N1, N2 and the logo never animate.

**Engineering**

53. `index.html` opens by double-click under `file://` in Chrome with the network offline; DevTools shows zero network requests other than local files.
54. The console shows no errors and no warnings on load and along the guided path.
55. GSAP and Flip load from `shared/vendor/gsap/` at version 3.15.0 with the licence file present; no other library is loaded; no `type="module"`.
56. Files are within the budget of section 10.5; the folder holds `index.html`, `styles.css`, `app.js`, `NOTES.md` and `screenshots/` only.
57. `NOTES.md` follows section 10.6 and lists computed contrast for every pair the direction adds.
58. The 19 screenshots of section 10.7 exist and show made-up data only.
59. No logo, illustration, typeface or layout signature of another company appears; the Cal Poly Pomona logo is the unaltered `SMC.LOGO`.
60. All deep links of section 3.7 work. Where the direction ships no dark theme, `theme=dark` is ignored without error and the page stays light.

**The room: 1280×720, the clicker, a hurried click**

61. At 1280×720, on all nine screens, nothing interactive and no line of text rests under a fixed bar, under the stop rail or behind the guide button; the content of section 5.2's compact table is on screen without scrolling.
62. The entry does not scroll at 1440×900 or at 1280×720: all three doors and the demo line are whole and no scrollbar shows.
63. The guide button covers no control and no line of text on any screen at 1440×900, 1280×720 or 390×844, at any scroll position.
64. A double-click on each interview reply option, on `Done` and on each bot chip answers one turn only: no control of the next turn is activated. After the guided path made with double-clicks, Grace's interests are Technology and Entertainment, her goal is "Exploring consulting or data roles", and she is #4 on `match`.
65. After dragging "Same major" with the pointer, after choosing an event in the picker, and after typing `Delgado` and pressing Enter in the records search, one `PageDown` goes to the next stop and changes no value.
66. Opening each of the four help panels brings its label into view at 1440×900 and at 1280×720. After a suggested question is pressed, N2 and the bot's answer are on screen, clear of any sticky header, and focus is still on the chip.
67. After `Register`, the pressed button, its event title, the screen title and the status label are still on screen, together with the check-in code and the points.
68. Returning to a finished interview (`PageUp` from stop 3, or a deep link) shows the last assistant turn from its first line.
69. The computed `font-variant-numeric` includes `tabular-nums` on table cells, the weight values, tile figures and the match line.
70. On `match` and `records` at 1440, no student name and no last-column value wraps; reasons take at most 2 lines at 1440 and at 1280; with all four weights at 0, "Showing 15 of the top 30." is hidden. A weight's value never touches the thumb's focus ring, at 10 included.
71. The event picker is a native `<select>` from 640px up and a radio list below; no option is cut at either width.
72. In the guide panel the stop controls sit below the `Say:` line; marker N1 is at least 16px on every screen.


---

# Part 2 — Three directions

Same content, same data, same honesty components, same motion tokens. What differs: the shell, the neutrals, the type, the density, and which moments get the craft. A board member should tell them apart in two seconds:

| | A · Blueprint | B · Workbench | C · Walkthrough |
|---|---|---|---|
| Two-second read | Ann's green-and-white pages with a left menu, made exact | A grey, full-height workspace with a sidebar and dense tables | Warm paper, serif headlines, a green stop rail along the bottom |
| Shell | Centred column, top bar, 224px menu, one screen card | Full-bleed: 264px sidebar, page header, split panes | Full-bleed stage: slim top bar, big content, bottom rail |
| Type | Bricolage Grotesque + Public Sans (hers) | Instrument Sans + JetBrains Mono | Source Serif 4 + Figtree |
| Body size | 18px | 16px | 20px |
| Gold, beyond the shared honesty and data marks (section 6.1) | Reason chip, callout, `Say:` line, "new" pills on gold-soft | None of those: they are neutral, on `--b-sunk` | As A, plus gold numerals on the green rail |
| Match screen | Picker, weights in one row, table below | Weights pane left, table right | Control band over a full-width table |
| Match rows on screen | Grace's row #4 whole and at least 5 full rows at 1440×900; at least 4 at 1280×720 | the same | the same |
| Guide button on portal screens | Docked in the top bar | Docked at the foot of the sidebar | Docked on the rail |
| Dark theme | Ships, opt-in | Optional, opt-in | None; `theme=dark` is ignored |
| Best screen | Student interview | Match students to an event | Entry and the Grace story |
| Risk | Looks like "the same thing" | Looks finished; small from the back row | Most to build by Thursday |

## 12. Direction A — Blueprint (`a-blueprint`)

### 12.1 Concept

Ann's own design, drawn precisely. Her layout, her palette, her three typefaces, her words; with the type raised to projector sizes, every spacing value snapped to the scale, the weak spots fixed (focus ring, target mark, stretched label, clipped transcript, toast-only outcomes), and five moments of motion that explain what the app just did. She should recognise every screen as hers and see that it got sharper, not different. It is the lowest-risk option and the one the presenters can rehearse with her guide unchanged.

### 12.2 Lineage and why it suits the board

University and public-service product design: one brand colour doing the work, bordered cards, generous plain text, nothing that needs explaining (the register of GOV.UK-style service pages and Material 3's "filled button, outlined card" basics). A non-technical board reads it as an institution's own tool, which is what it is meant to become.

### 12.3 Tokens

Shared tokens at Ann's values (section 6.2), nothing changed. Extensions:

| Token | Value | Use |
|---|---|---|
| `--a-font-display` | `"Bricolage Grotesque"` 700 (500 for eyebrows), then the sans fallback | Titles, door titles, big figures, date tile |
| `--a-font-body` | `"Public Sans"` 400 / 500 / 600, then the sans fallback | Everything else |
| `--a-font-mono` | `"JetBrains Mono"` 500, then the mono fallback | IDs, ranks, the match line, bar values |
| Card style | 1px `--sm-line` border, no shadow | As hers. Shadow (`--sm-elev-3`) only on the guide panel and toast |
| Radius | buttons and menu items `md`, cards and the screen `lg`, doors and guide `xl`, status label `sm` | Hers were 9 / 10 / 12 / 14 / 16; snapped |
| Small labels | Uppercase by CSS, 14px, 600, tracking 0.06em, muted | Her `.label` look, raised from 12px |

Type roles: entry title `text-64`; screen title `text-28` (display 700); block label 14 uppercase; `h3` `text-20`; body, table and chat `text-18`; helper `text-16` muted; chip labels and the match line `text-16` or `text-18`; marker N1 `text-16`; status label `text-14` mono 500 uppercase (sentence case at 600 is also allowed, and reads better at distance); tile figure `text-36`; ring figure `text-48`.

Dark theme: ships, with section 6.4's values (they are hers).

### 12.4 Shell and navigation

- Content column max 1200px, centred. Top bar: logo plate, portal name (`text-24` display) over the identity line, then marker N1, then the guide button and `Switch portal` (secondary) at the right. The guide button is docked here on every portal screen, so it covers nothing; the guide panel opens under it.
- Below: a 224px menu (her buttons; the current one filled green with white text and `aria-current`) and one screen card, 24px apart. The menu is sticky.
- At `md` and below the menu becomes a horizontally scrolling strip above the screen (hers), and N1 moves under the top bar at full width.
- Entry: logo at 84px high with marker N1 on the same row at the right, the title, the lede, three doors in a row, the demo line; the guide button floats at the bottom right, where nothing sits behind it. Otherwise as hers.

### 12.5 Signature motion

| # | Moment | Spec |
|---|---|---|
| 1 | A door opens into its portal | `sm-portal`: the pressed door's title Flip-travels to the portal name in the top bar (`move`, `inOut`); the other two doors fade (`fast`, `in`); the menu and screen enter (`base`, `out`). Whole change ≤ 400ms. Reverse on `Switch portal` |
| 2 | The profile card fills | `sm-card-fill`: toggling an industry adds or removes its pill on the card in the same beat; "Not yet" cross-fades to the goal after turn 3 |
| 3 | The list re-ranks | `sm-rerank` + `sm-wash`: Grace's gold row is the eye's anchor as it slides from #4 down and out when "Same major" rises |
| 4 | Readiness moves a little | `sm-ring-draw` + `sm-count`: tick the LinkedIn self-check, the arc extends and 13% counts to 17%, the points tile to its new total, the marker's first dot fills |
| 5 | Register | `sm-register`: the button turns gold with a drawn check; the check-in card rises in under the list |

### 12.6 Hero screens

| Screen | Treatment |
|---|---|
| Student interview | Her two columns (5:4). Transcript left with N2 pinned on top; profile card right on `--sm-page`. The card's two group labels stay, so "already on file" versus "from the interview" is visible at a glance; new values arrive as gold-soft pills |
| Events for me | Her rows: date tile, title, meta, reason chip, button, match line. The reason chip is `text-18`. The check-in card sits under the list with the points block at its right |
| Match students to an event | Picker, then the four weights in one row, the Grace line, the table. Grace's row #4 whole and at least five full rows on screen at 1440×900, at least four at 1280×720 (section 5.6) |
| Career Hub overview | Four tiles in a row, then her 2 × 2 chart grid, then the data-handling card |
| Partner portal | Her 2 × 2 grid: who was invited, how the talk filled, what students asked, stay involved. Outcome messages appear under the three buttons |

### 12.7 What it deliberately does not do

- No new layout ideas: no sidebar restyle, no stage, no command switcher.
- No shadows on cards, no second accent, no illustration.
- No motion beyond the five moments and the shared feedback set.

### 12.8 Main risk

It may read as "the same thing Ann already made". Answer in the room: put her screenshot beside it (`reference/21-hub-match-default-1440.png` against A's `12-match-default`) and name what changed: readable from the back row, keyboard and focus, honest markers on every screen, outcomes that stay on screen, and motion that shows cause and effect.

## 13. Direction B — Workbench (`b-workbench`)

### 13.1 Concept

The staff tool, taken seriously. A calm, dense workspace: a full-height sidebar that always shows where you are, a command-style switcher that jumps between the three portals and their screens, a compact page header carrying the title and its status label, and tables that re-rank smoothly under the weights. Neutral greys do the background work; Cal Poly green appears only where something is active or true; gold is kept for Grace, for "Registered", and for the honesty and data marks every direction shares ("planned", "scripted", the gold bars and dots, the target mark). It shows the board what Career Hub staff would live in every day.

### 13.2 Lineage and why it suits the board

Mature productivity tools: Linear's sidebar and command menu, Stripe's dashboard tables and icon-plus-word status badges, GitHub's and Atlassian's quiet density, Material 3's navigation drawer. Taken as patterns: persistent navigation, keyboard-first switching, hairline separation, tabular figures. Nothing of their look is copied. It suits board members who are employers: many use tools like these at work, so the Career Hub screens will read as a credible operations tool. It is weaker on the student story.

### 13.3 Tokens

Brand and status tokens as shared. Neutrals replaced:

| Token | Value | Pair | Ratio |
|---|---|---|---|
| `--sm-page` | `#f4f5f4` | ink on it | 15.15 |
| `--sm-surface` | `#ffffff` | ink on it | 16.56 |
| `--b-sunk` | `#eceeed` (table header band, wells) | ink / muted on it | 14.21 / 5.55 |
| `--b-sidebar` | `#eef0ee` | ink / muted / green on it | 14.45 / 5.65 / 8.37 |
| `--sm-ink` | `#16211c` | on green-soft / gold-soft | 13.76 / 14.75 |
| `--sm-muted` | `#55615b` | on page / surface / gold-soft / green-soft | 5.92 / 6.47 / 5.76 / 5.38 |
| `--sm-line` | `#e1e5e2` | decorative | — |
| `--sm-line-strong` | `#76837c` | on page / surface / sunk | 3.62 / 3.96 / 3.39 |
| green `#005030` | — | on page / sunk | 8.77 / 8.23 |
| gold-ink `#7a5600` | — | on page | 6.08 |

| Token | Value | Use |
|---|---|---|
| `--b-font-ui` | `"Instrument Sans"` 400 / 500 / 600 / 700, then the sans fallback | Everything |
| `--b-font-mono` | `"JetBrains Mono"` 500, then the mono fallback | IDs, ranks, weights, counts, percentages, the shortcut hint |
| Card style | 1px `--sm-line` hairline, no shadow; panes separated by hairlines, not gaps | Shadow (`--sm-elev-2`) only on the switcher popover and guide |
| Radius | controls `sm` (6px), cards and panes `md` (10px), popover `lg` | Tighter than A |

Type roles: entry title `text-48`; screen title `text-28` 600; block label `text-14` 600 muted, sentence case; `h3` `text-18` 600; body, table and chat `text-16`; helper `text-14` muted (never data); status label `text-14` 600; marker N1 `text-16` 600; tile figure `text-28` mono; ring figure `text-36`.

Controls are drawn 40px tall with a 44×44px hit area (section 5.6).

Dark theme: optional; if shipped, section 6.4's values.

### 13.4 Shell and navigation

- **Sidebar, 264px, full height, `--b-sidebar`.** Top: the switcher button (logo plate, portal name, identity line, `chevrons-up-down`), with marker N1 directly under it at 16px. Middle: the portal's menu items as rows (current row: `--sm-surface` fill, a 3px green bar at the row's inner left edge inside the row's radius, weight 600, `aria-current`). Bottom: the guide button, docked here instead of floating.
- **Switcher.** Pressing the switcher button, `Switch portal`, or `Ctrl`/`⌘`+`K` opens a non-modal popover: a field (N10) and a list. The first option is the entry, labelled with its title, "Smart Match CPP"; choosing it returns to the entry, which is what `Switch portal` does in section 2.2. Then come the groups, one per portal name, each listing its screens by their menu labels, plus the five events under "Match students to an event". Arrow keys move, Enter goes, Esc closes and returns focus. The button's accessible name is `Switch portal`. It is a combobox with a listbox (`aria-activedescendant`), not a dialog.
- **Page header, sticky.** Screen title, status label on the same row, description beneath, in at most 2 lines (section 4).
- **Main.** Split panes where the screen has two subjects: transcript | profile inspector (360px); weights (304px, sticky) | ranked table. Otherwise one column, max 1120px.
- **Entry.** The same three doors, as three wide rows in a centred 720px column (eyebrow, title, body, action), under the title and lede, with the demo line below. No sidebar on the entry: marker N1 sits above the title and the guide button floats at the bottom right, as in A.
- **`md` and below:** the sidebar becomes a top bar with the switcher, marker N1, the guide button and a horizontal menu strip; panes stack.

### 13.5 Signature motion

| # | Moment | Spec |
|---|---|---|
| 1 | Command-style switch | Popover: opacity and scale 0.98 → 1 from the switcher button (`fast`, `out`). On Enter the popover leaves (`instant`), the main pane cross-fades (`fast` out, `base` in) and the sidebar rows cross-fade their labels (120ms). The sidebar itself never moves. ≤ 400ms |
| 2 | Dense re-rank | `sm-rerank` on the densest table of the three; rows that drop out of the visible 15 are removed on the first frame, like everywhere else; the `#` column's numerals update at the first frame while names travel; `sm-wash` on arrivals. The Grace line's number runs `sm-count` (#4 → #27) |
| 3 | Search narrows | Rows that no longer match fade (`fast`); the rest close up with Flip (`move`); the count line updates at once |
| 4 | Inspector fills | `sm-card-fill` in the profile inspector while the transcript advances with `sm-turn` |

### 13.6 Hero screens

| Screen | Treatment |
|---|---|
| Student interview | Transcript pane left, N2 pinned under the page header; profile inspector right as a definition list with two labelled groups. Reply options sit in a docked reply bar at the bottom of the transcript pane |
| Events for me | A three-row list in one bordered pane: date tile, title and meta, reason, match line (mono), `Register`. The check-in card is a second pane to the right at `xl` (QR, sentence, "Planned", points), so nothing is below the fold |
| Match students to an event | **The showpiece.** Weights pane left, sticky, with the event picker on top and the Grace line beneath the four controls; table right, with Grace's row #4 whole and at least five full rows on screen at 1440×900 and at least four at 1280×720 (section 5.6; 44px rows usually show more); the invitations button and its outcome message in a sticky footer of the table pane |
| Career Hub overview | A four-up tile strip with hairline dividers, not four boxes; charts in a 2 × 2 grid of panes; the data-handling list as a full-width pane |
| Partner portal | Two panes on top (who was invited, how the talk filled), two below (questions, stay involved). The sidebar shows one item, "My talk" |

### 13.7 What it deliberately does not do

- No large type, no serif, no illustration, no brand-colour surfaces.
- No floating cards with shadows; no rounded "bubbly" controls.
- No gold except Grace's row, "Registered", and the honesty and data marks every direction keeps: the planned label, the scripted line N2 (gold-soft), the gold bars, the third progress dot, the future-term dot and the target mark. The reason chip, the callout, the `Say:` line and the "new" pills are neutral, on `--b-sunk`.
- No keyboard shortcut beyond `Ctrl`/`⌘`+`K`, `G`, `PageDown`, `PageUp`.

### 13.8 Main risk

Two. It looks the most like finished software, which pulls against rule H1; so N1 sits at the top of the sidebar, under the portal name, at 16px on every screen and the status label is in the sticky header where it cannot scroll away. And 16px tables are at the floor for a lit room; if the projector is weak, the back row loses the reasons. Check it projected before choosing it as the lead.

## 14. Direction C — Walkthrough (`c-walkthrough`)

### 14.1 Concept

Built for the fifteen minutes. The nine stops are the navigation: a green rail along the bottom shows where the presenters are, `Back` and `Next` (or a clicker) move through Ann's order, and each stop opens on one large idea that fills the screen before anything else is asked of the eye. Type is large, on warm paper, with a serif for the sentences the presenters read aloud. Transitions carry the story from Grace's interview to the staff list where she appears at #4. All of Ann's content is still on every screen; the first screenful is simply reserved for the one thing that stop is about.

### 14.2 Lineage and why it suits the board

Presentation-first product storytelling: Apple's large-title, one-message-per-view pages and HIG clarity; Stripe's and Airbnb's editorial product pages, where big type and a single shared-element move explain a feature; one-task-per-view flows. Patterns only: big type, one focal point, a visible "where are we". It suits a board that will watch, not operate: they follow a student's story, and the rail tells them how much is left.

It also sits closest to the team's shipped class-exercise system ("the room reads it first", warm paper, green ink, gold as highlighter), so the board sees one family across the team's work. The type pairing is that system's own mock-up stand-in pair.

### 14.3 Tokens

Brand and status tokens as shared. Neutrals replaced:

| Token | Value | Pair | Ratio |
|---|---|---|---|
| `--sm-page` | `#f8f6f1` (paper) | ink on it | 12.77 |
| `--sm-surface` | `#ffffff` | ink on it | 13.79 |
| `--c-sunk` | `#f2eee8` | ink / muted on it | 11.94 / 5.21 |
| `--sm-ink` | `#163229` | on gold-soft / green-soft | 12.29 / 11.47 |
| `--sm-muted` | `#59665f` | on page / surface / gold-soft / green-soft | 5.57 / 6.02 / 5.36 / 5.00 |
| `--sm-line` | `#d9cbc4` | decorative | — |
| `--sm-line-strong` | `#8f7a70` | on page / surface / sunk | 3.75 / 4.05 / 3.50 |
| `--c-stage` | `#005030` (the brand green as a surface: entry and rail) | white / paper / gold on it | 9.59 / 8.88 / 5.46 |
| `--c-on-stage-soft` | `#cfe3d8` (secondary text on the stage) | on stage | 7.14 |
| green `#005030` | — | on page / sunk | 8.88 / 8.30 |
| gold-ink `#7a5600` | — | on page / sunk | 6.16 / 5.75 |
| part `#2e5f8a` | — | on page | 6.23 |

| Token | Value | Use |
|---|---|---|
| `--c-font-display` | `"Source Serif 4"` 600, then the serif fallback | Screen titles, the `Say`-length sentences on screen (descriptions, reasons), big numerals |
| `--c-font-ui` | `"Figtree"` 400 / 500 / 600 / 700, then the sans fallback | Controls, labels, tables, chat |
| Card style | White card, `--sm-elev-1`, no border; `--sm-elev-2` on hover and on the current event | Controls keep a `--sm-line-strong` outline |
| Radius | controls `md`, cards `lg`, doors and big panels `xl` | — |

Type roles: entry title `text-80`; screen title `text-48`; description `text-24` serif; block label `text-16` 600 sentence case; `h3` `text-24`; body and chat `text-20`; table `text-18`; helper `text-16`; status label `text-16` 600; tile figure `text-48`; ring figure `text-64`; Grace's rank on `match` `text-80`.

Focus ring: green on paper and white; gold on the green stage and rail.

Dark theme: not shipped. A paper direction in a lit room has no use for it. `?theme=dark` is ignored without error, and the guide panel shows no theme control.

### 14.4 Shell and navigation

- **Top bar, 64px, paper:** logo plate, portal name with the identity line beside it, marker N1, `Switch portal`.
- **Stage:** everything between the bars; content max 1200px. The first screenful of each stop is its hero (section 14.6); the rest of Ann's content follows below by ordinary scrolling. No snapping, no pinned sections.
- **Stop rail, 72px, fixed at the bottom, `--c-stage`:** at the left `Back`; in the middle the current portal's menu items as large tabs (her labels; the current one white on green with a gold bar beneath, `aria-current`), which is the portal's `<nav>`; at the right "Stop {n} of 9" in gold numerals and `Next`. The presenter's name for the current stop, taken from the guide title ("Chau" or "Janice"), sits beside the stop count.
- The guide button docks at the rail's right end; the guide panel opens above the rail.
- The rail takes its 72px out of the stage: the stage is sized as `100dvh` minus the top bar and the rail, so nothing rests under the rail, and whatever is below the fold scrolls fully clear of it. Under 800px of viewport height the compact layout of section 5.2 applies: entry title `text-64`, screen title `text-36`, description `text-20`, ring 150px.
- **Entry:** a full-bleed green stage: logo on its white plate, "Smart Match CPP" in white at `text-80`, the lede in `--c-on-stage-soft`, three white doors, the demo line. Marker N1 stays in the top bar. The rail shows "Stop 1 of 9" and `Next` only.
- **`md` and below:** the rail keeps `Back`, the stop count and `Next`; the tabs become a horizontally scrolling strip under the top bar.

### 14.5 Signature motion

| # | Moment | Spec |
|---|---|---|
| 1 | Stop to stop | `sm-portal` as a scene change: outgoing stage content opacity → 0 and x 0 → −24 (`fast`, `in`); incoming x 24 → 0 with opacity (`move`, `out`), overlapping so the whole change is ≤ 400ms; the rail's gold bar glides to the new tab with Flip (`move`, `inOut`). `Back` mirrors the direction. A second `PageDown` mid-change lands on the following stop |
| 2 | The doors arrive | Once per page load: the three doors rise y 16 → 0 with opacity, 30ms apart (`base`, `out`). Any key or click finishes it |
| 3 | An answer is filed on the card | On `Done` and after turn 3: the chosen chips Flip-travel from the reply area to the profile card's row and settle as pills (`move`, `inOut`), then `sm-card-fill`. The card is the hero of this stop, so this is the stop's point made visible |
| 4 | Why you | Arriving on `recs` after the interview: the three reason lines enter 30ms apart (`base`, `out`); `Register` runs `sm-register` |
| 5 | Grace at #4 | On `match`, a `text-80` rank numeral beside the Grace line runs `sm-count` as weights move, while the rows run `sm-rerank`. When she leaves the top 30 the numeral cross-fades to the sentence alone |

### 14.6 Hero screens

| Screen | First screenful | Below |
|---|---|---|
| Student interview | Left: the latest assistant turn large, its reply options beneath as big chips, N2 above. Right: the profile card at hero size, two labelled groups. Earlier turns are in the scrollable log above the latest turn | — |
| Events for me | The top event as a wide feature row (date tile, title `text-36`, reason in serif `text-24`, `Register`, match line), the other two as two half-width rows under it. All three visible | Check-in card (brought into view on `Register`) |
| Match students to an event | A control band across the top: the `Event` picker (a native select; section 7.9), the four weights in one row (two columns when the stage is under 900px wide), Grace's rank numeral and line. Under the band, the table at full width, so reasons fit in 2 lines: Grace's row #4 whole and at least five full rows at 1440×900, at least four at 1280×720 | Rest of the 15 rows, invitations button |
| Career Hub overview | The four tiles at `text-48`, with "students never reached by an event" set apart as the widest tile (the guide's point), then chart row one | Chart row two, data handling |
| Partner portal | "Who was invited" and "How your talk filled" side by side, with the funnel large and its mass-email note in serif | Questions as two large quotes, stay involved |
| Readiness | Ring at 200px (150px at compact height), three tiles, callout, and the four help buttons | The open help panel, then the six markers |

### 14.7 Bree, the team's mascot

Not in this mockup. Reasons:

1. "Bree" is a placeholder name with an open identity question against Cal Poly Pomona's own mascot (`mascot-tutorial/PLAN.md`, open question 1). The board is the wrong place to debut an unresolved character.
2. Two scripted assistants are already on screen. A character beside them would read as an AI persona and blur rule H3.
3. The art is raster, 262–286px, soft on a projector, with one known stray fragment (`redesign/b-friendly-tech/NOTES.md`).
4. Ann's prototype has no mascot; adding one changes her content, which Part 1 forbids.

Bree stays with the class-exercise tutorial, where students are the audience.

### 14.8 What it deliberately does not do

- No sidebar, no command switcher, no dense tables above the fold.
- No mascot, no illustration, no photography, no confetti.
- No scroll effects, no auto-advance, no interstitial title cards between stops.
- No dark theme.
- It does not hide content behind tabs or disclosures: everything of Ann's is on the page, in her order, below the hero.

### 14.9 Main risk

Build time. It has the most bespoke layout (nine hero arrangements, the rail, three Flip moves) for a Thursday deadline, and big type makes long content scroll, so a Q&A question about a detail below the fold costs a scroll. If it slips, cut in this order: moment 3 (chips travelling) → plain `sm-card-fill`; moment 5's big numeral; the feature-row layout on `recs`. Never cut: the rail, N1, N2, the status labels.

## 15. Recommendation

| Role | Direction | Why |
|---|---|---|
| **Lead: present this one** | **A · Blueprint** | It is Ann's design, so she recognises it and the presenters' rehearsal with her guide carries over unchanged. It is the surest to be complete and correct by Thursday. Every fix in this contract (type floors, honesty markers, persistent outcomes, focus, motion) lands on it without changing what she approved |
| Alternate 1 | B · Workbench | Show its `match` and `records` screens if the board asks "what would staff use day to day?". Do not lead with it: it reads as finished software and is the hardest to read from the back row |
| Alternate 2 | C · Walkthrough | The best fit for a projected story and the closest to the team's shipped exercise look, but the riskiest build. If it is finished and rehearsed by Wednesday evening, the owner may promote it to lead for the opening (entry, interview, events) and switch to A or B for the Career Hub screens |

Build order inside every direction, so that a partial build is still presentable: shell with N1 and the guide → `entry` → `interview` → `recs` → `match` → `overview` → `talk` → `readiness` → `growth` → `records` → 390 layouts → compact height (1280×720) → dark (A; B if kept).

Builder notes that save time:

- GSAP Flip on table rows: animate the `<tr>` elements with a transform (Chrome transforms table rows; this is not a layout animation); give each row `data-flip-id` equal to the student id; call `Flip.getState(rows)` before re-rendering and `Flip.from(state, { duration: 0.28, ease: "power2.inOut", simple: true, absolute: false, overwrite: true, onEnter })` after. No `onLeave`: remove the rows that dropped out of the visible 15 before `Flip.from`, so they are gone on the first frame. A hand-written FLIP on GSAP core (one `gsap.fromTo` per row from its old offset to 0) is equally allowed if it holds the frame budget better.
- Re-render the table body by re-ordering existing row nodes, not by replacing `innerHTML`, or Flip has nothing to match and the slider loses focus.
- One `keydown` handler on `document` for `PageDown` / `PageUp`: return early only when the target is a text-entry `<input>` (text or search) or a `<textarea>`; otherwise `preventDefault()` and change stop. Do not give the sliders or the select a Page-key handler of their own.
- Keep the weight inputs out of the re-rendered region so a drag is never interrupted.
- The ring's circumference for a radius-66 circle is 414.69; the arc is that times the percentage.

---

# Appendices

## Appendix A — Sources consulted

**In the repo (read in full):** Ann's HTML and README; `source/PROVENANCE.md`; `docs/design/class-exercise/DESIGN.md`; `docs/design/class-exercise/mascot-tutorial/redesign/b-friendly-tech/NOTES.md` (house format); `apps/web/AGENTS.md`. Skimmed: `mascot-tutorial/PLAN.md` (Bree's open questions), the app's `components/ui/` listing and `package.json` (Radix, lucide, motion).

**Tools:** her prototype was opened in headless Chromium (playwright-cli) and every screen captured into `reference/`; her matching code was run in Node, untouched, to produce and cross-check the test vectors; contrast ratios were computed with the WCAG 2.x relative-luminance formula; the GSAP version was read from the npm registry on 2026-10-06 (`3.15.0`). The `impeccable` skill's context step was run; its guidance on bans (side-stripe accents, gradient text, glass, bounce easing, nested cards) and on verification in bounded passes shaped sections 5, 8 and 11.

**No web reference pass was made.** The lineage notes below are from prior knowledge of public design guidance, not re-read for this document. Patterns and principles only; no asset, logo, illustration, typeface or trade dress of any company is used.

| Reference | What was taken |
|---|---|
| Material Design 3 | Duration and easing as named tokens; "emphasized" arrivals and faster exits; container-transform idea behind the door-to-portal move; navigation drawer and rail model; state layers for hover and press |
| Apple Human Interface Guidelines | Large titles and one focal point per view; 44pt minimum targets; reduce-motion as an equal path; deference of chrome to content |
| Linear | Persistent sidebar, command-menu switching, 100–200ms feedback, dense but calm lists |
| Stripe Dashboard and product pages | Hairline tables with tabular figures; status badges as icon plus word; editorial big-type explanation of one feature at a time |
| Airbnb product UI | Card rows with one clear action; shared-element transitions that keep a thing's identity across views |
| Meta and Netflix app shells | Chrome that stays put while content swaps; no layout shift on navigation |
| GSAP documentation (Flip) | First-Last-Invert-Play for re-ordering without animating layout; `overwrite` for interruptible tweens; `matchMedia` for reduced motion |
| WAI-ARIA Authoring Practices | Slider keys; disclosure and non-modal popover; combobox with listbox for the switcher; log and status regions |
| WCAG 2.2 | Contrast 1.4.3 and 1.4.11, focus appearance, target size, reflow, text spacing, animation from interactions |
| Radix Primitives, lucide | `data-state` and `aria-*` as the styling surface; icon names that port to `lucide-react` |
| Fonts | Bricolage Grotesque, Public Sans, JetBrains Mono, Instrument Sans, Source Serif 4, Figtree: all SIL Open Font License 1.1 |

## Appendix B — Open questions (builders use the default; nothing here blocks the build)

| ID | Question | For | Default |
|---|---|---|---|
| OQ-1 | Which direction do the presenters lead with? | Owner, Ann | A · Blueprint (section 15) |
| OQ-2 | Apply wording changes W1–W5? | Ann | No: her wording stands |
| OQ-3 | The shipped class exercise forbids match scores and percentages for a person (its "counts, never scores" rule). Her prototype shows "match 6 of 10" to the student and a readiness %. Keep both? | Ann | Keep, verbatim, in these mockups. Settle it before the real build |
| OQ-4 | Apply fixes F1–F3 (profile-card count 71, "Graduate school", one points total)? | Owner | Yes, in all three |
| OQ-5 | May team mockups shown to the board carry the Cal Poly Pomona logo? | Owner | Yes, exactly as Ann embedded it, unaltered |
| OQ-6 | Should the presenter guide ever be visible on the projector? | Presenters | Closed by default; rehearsal only; `G` toggles it |
| OQ-7 | T17: the Hub is about to invite students to the Mar 4, 2027 talk while the Partner screen reports its results | Ann | Keep; the presenter says "after the talk, this is what the partner would see" |
| OQ-8 | Gold is `#fdb71e` in her file and `#FFB81C` in the app theme | Owner | Hers in the mockups; reconcile at port time |
| OQ-9 | Dark theme | Owner | A ships it (opt-in); B optional; C none. Never automatic |
| OQ-10 | Keeping demo state across a reload is new behaviour | Owner | On, with `Reset demo` |
| OQ-11 | Feature Bree in C? | Owner | No (section 14.7) |
| OQ-12 | Commit GSAP's minified files and the OFL fonts under `shared/vendor/`? GSAP's licence is free of charge but not open source | Owner | Yes, with the licence files. If refused: CSS transitions and the Web Animations API with the same tokens, and row re-ranking by a hand-written FLIP |
| OQ-13 | Projector resolution and room brightness are unknown | Presenters | Design at 1440×900, hold at 1280×720, test in the room on Wednesday |
| OQ-14 | Outcomes as persistent messages instead of toasts | Ann | Apply (her sentences, unchanged) |
| OQ-15 | "Share my readiness card with the advisor" is ticked by default, while the screen says readiness is private "unless she chooses to share it" | Ann | Keep ticked as hers; flag it to her as a consent question for the real build |
| OQ-16 | Two assistant names: "Smart Match assistant" and "CBACH assistant bot" | Ann | Keep both |
| OQ-17 | Turn 4b's "Only accounting events" has no effect | Ann | Keep her behaviour; the guided path never reaches it |

## Appendix C — Things in her prototype that could not be interpreted

| # | Where | What is unclear | What the mockups do |
|---|---|---|---|
| C1 | Check-in card | "Points exist in the early version": probably "career points already work in the class version", but it could mean an early version of this prototype | Verbatim (W5 proposes a reading) |
| C2 | Data comment | "profile and record columns only; hidden columns are not included": which columns of the class file were left out is not stated | Nothing; the eight columns present are the contract |
| C3 | `tb` column | Used as the last tie-break and, in `hubReadiness`, as a pseudo-random spread (`tb % 17`). Whether it means anything in the class file is not stated | Used exactly as she uses it |
| C4 | Interview card | "Later: students can answer by voice or by typing." Typing already works in the prototype | Verbatim |
| C5 | Events for me | The label "Matching works in class version" on a student-facing screen: the class version has the matching, not this screen | Verbatim |
| C6 | Events | "60 seats" is the same on every event; the series name "Behind the Business" appears only on the partner screen and in two event titles | Verbatim |
| C7 | Readiness | An unused variable counts attended plus registered events; "Attended 2 or more employer events" counts past events only, so registering does not change it | Her behaviour |
| C8 | Guide, `entry` | "each with its own sign-in" while the doors say "Enter as…": the README names CPP login as a later build step | Verbatim; no sign-in screen is added |
| C9 | Term overview | Whether "students with a profile card" was meant to count Grace's interview as +1 on top of the file's 70 (true) or on top of the recount (her code, 72) | 71 (fix F1) |
| C10 | Event ids | `E11` and `E12` continue the past-event numbering and carry the class exercise's two company names; `U1`–`U3` are a separate, made-up set | Ids used as given, never shown on screen |

## Revision history

**2026-10-06 — reconciled after the independent audit ([`audit/AUDIT.md`](audit/AUDIT.md), D-01 to D-14).** Where two sections asked for incompatible things, the document now states one rule. Section 2's copy, the data contract, the test vectors and every colour and contrast number are unchanged.

| ID | Single rule | Sections changed |
|---|---|---|
| D-01 | Match table: Grace's row #4 whole and at least 5 full rows at 1440×900; at least 4 at 1280×720. The per-direction minimums (6 / 10 / 5) and "six or more" are gone | 5.2, 5.6, 12.6, 13.5, 13.6, 14.6, Part 2 table, item 31 |
| D-02 | A screen description is at most 2 lines with a measure up to 100 characters; 45–70 characters is for body prose only | 4, 13.4 |
| D-03 | Part 2 may re-tone a surface, never an honesty component. N2 gold-soft, gold bars, third dot and the future-term gold ring with a gold-ink keyline in every direction; chip, callout, `Say:` line and "new" pills neutral in B only | How to use, 6.1, 6.2, 6.5, 7.4, 7.6, 7.10, 7.14, 7.16, 9.5, 13.1, 13.7, Part 2 table, item 35 |
| D-04 | The 44×44px rule measures the hit area; the drawn box may be 40px for chips and for all controls in B | 5.6, 7, 7.3, 7.6, 9.3, 13.3, item 45 |
| D-05 | Rows leaving the visible 15 are removed on the first frame; no exit animation (was: rows leaving fade out) | 8.1, 8.3, 8.7, 13.5, 15, item 50 |
| D-06 | Frame budget: no frame over 50ms and no long task over 50ms at 4× CPU throttle, on the classroom laptop (was 33ms). Flip with `simple: true` or a hand-written FLIP on GSAP core is allowed | 8.3, 8.5, 8.7, 15, item 51 |
| D-07 | Item 37 split into 37a (light when the OS is dark, all directions) and 37b (only where a dark theme ships). `theme=dark` is ignored without error where none ships | 3.7, 14.3, 15, Part 2 table, items 37 and 60 |
| D-08 | `PageDown` / `PageUp` always change stop, except in a text input or textarea; the slider exception is gone and sliders no longer use Page keys; Enter in the records search releases focus | 1.2, 7.8, 7.9, 7.15, 7.16, 9.2, 15, item 41 |
| D-09 | `h1[tabindex="-1"]` never draws a focus ring | 7, 9.2, 9.3, item 42 |
| D-10 | Event picker: a native select from 640px up, a radio list below, in every direction (the per-direction table is gone) | 7.9, 14.6, item 71 |
| D-11 | C's Match layout is a control band over a full-width table | 14.6, Part 2 table |
| D-12 | `recs` has a visually hidden `h2` "Events for me"; the profile card's name is an `h2` | 9.1, item 42 |
| D-13 | B's `Switch portal` popover lists the entry first, by its title | 7.1, 13.4 |
| D-14 | Chip labels and the match line may be 16px in every direction; the 18px floor (A, C) is for read-aloud body text | 5.3, 7.6, 7.14, 12.3, item 27 |

Also folded in from the audit's findings (A-, B-, C- and X- ids):

| Rule added | From | Sections changed |
|---|---|---|
| Compact layout under 800px of viewport height; nothing interactive under a fixed bar, the rail or the guide button at 1280×720; the entry never scrolls | A-05, A-06, A-13, A-16, B-03, C-02, C-03, C-04, C-12 | 5.2, 5.6, 14.4, 14.6, 15, items 61 and 62 |
| The guide button is docked in the shell on portal screens and covers nothing | A-04, A-18, B-10 | 7.16, 9.2, 12.4, 13.4, item 63 |
| One press, one answer: a double-press never activates the next turn's control | A-07, B-01, C-08 | 7.10, 8.1, 8.3, items 50 and 64 |
| An opening help panel is scrolled into view; N2 stays on screen; focus stays on a pressed bot chip | A-03, B-02, B-08, X-11, X-14 | 7.4, 7.10, 7.14, 8.3, 9.2, item 66 |
| After `Register` the pressed button and its title stay on screen | A-09, C-05, X-06 | 5.2, 8.3, item 67 |
| A finished interview reopens at the top of the last assistant turn; the log is at least 240px tall | A-06, A-08 | 7.10, item 68 |
| `growth` joins the above-the-fold list, with its closing line whole | C-07 | 5.2 |
| `tabular-nums` is checked as a computed value | C-06 | 5.3, item 69 |
| Names and the last table column stay on one line; weight controls are spaced so values and labels cannot collide; "Showing 15 of the top 30." hides with N7; a space follows Grace's hidden text | A-10, A-11, A-12, B-06, B-07, B-09, C-09, C-11, C-14, C-15, X-07 | 5.6, 7.7, 7.8, item 70 |
| Marker N1 is at least 16px (B: under the portal name); guide stop controls sit below the `Say:` line; A's status label may be sentence case | B-05, X-08, X-09, X-10 | 5.3, 7.4, 7.16, 12.3, 13.3, 13.4, 13.8, item 72 |

Checklist numbering: items 1–60 keep their numbers (37 is now 37a and 37b); items 61–72 are new.
