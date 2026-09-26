# Prompt pack — class exercise visual refresh

Run these prompts in **Google Stitch** or **Claude Design** to produce
screens for the refresh described in [`../DESIGN.md`](../DESIGN.md). Each file
has one prompt per tool.

> These prompts make mock-ups, not code. Nothing generated is merged into
> `apps/web`. A generated screen is evidence for a design review. It is not
> proof that a feature exists. The implementing track reads `DESIGN.md`, not
> the mock-up.

## 1. Files and run order

Run the components first, so the page prompts can reuse what they produce.

| Order | File | Covers |
|---|---|---|
| 1 | [`components/weight-slider.md`](components/weight-slider.md) | The four weight sliders |
| 2 | [`components/ranked-row.md`](components/ranked-row.md) | Ranked row with reason line and marker chip |
| 3 | [`components/saved-setting-card.md`](components/saved-setting-card.md) | Saved-setting card and empty slot |
| 4 | [`components/compare-view.md`](components/compare-view.md) | Two lists side by side with the overlap marked |
| 5 | [`components/results-reveal.md`](components/results-reveal.md) | Seating chart, seat sentences, seat figures |
| 6 | [`components/asking-choice-cards.md`](components/asking-choice-cards.md) | The three ways of asking |
| 7 | [`components/instructor-unlock-panel.md`](components/instructor-unlock-panel.md) | Open results per event |
| 8 | [`components/empty-and-loading-states.md`](components/empty-and-loading-states.md) | Skeletons, empty states, refusals |
| 9 | [`pages/01-opening.md`](pages/01-opening.md) | Opening screen and license line |
| 10 | [`pages/02-team-entry.md`](pages/02-team-entry.md) | Team number |
| 11 | [`pages/03-event-picker.md`](pages/03-event-picker.md) | Choose an event |
| 12 | [`pages/04-ranked-list-and-sliders.md`](pages/04-ranked-list-and-sliders.md) | Ranked top 30 and four sliders |
| 13 | [`pages/05-save-and-compare.md`](pages/05-save-and-compare.md) | Save up to 3 settings; compare 2 |
| 14 | [`pages/06-profile-card-mockup.md`](pages/06-profile-card-mockup.md) | Profile-card mock-up |
| 15 | [`pages/07-points-counter.md`](pages/07-points-counter.md) | Points counter — **deferred this round; do not run** |
| 16 | [`pages/08-final-setting-and-results.md`](pages/08-final-setting-and-results.md) | Final setting, locked and unlocked results |
| 17 | [`pages/09-asking-for-more.md`](pages/09-asking-for-more.md) | Asking for more |
| 18 | [`pages/10-round-two-comparison.md`](pages/10-round-two-comparison.md) | Round-two results |
| 19 | [`pages/11-instructor.md`](pages/11-instructor.md) | Passcode, data file, teams, unlock |

## 2. How to run them

### Google Stitch

1. Open a new Stitch project. Choose **Web** for 1280 prompts and **Mobile**
   for 390 prompts.
2. Paste the **Stitch style preamble** (section 4) as the first message of
   the project. Stitch carries it as project context.
3. Paste one screen's Stitch prompt. One screen per prompt.
4. When the screen lands, paste the prompt's **"390 follow-up"** line as an
   edit on a duplicated screen to get the phone layout.
5. Attach the listed reference PNG from `../assets/mockups/` when the prompt
   names one. Stitch uses images as style references.
6. Export as PNG and HTML. Save them under a date-named folder outside this
   repo (see section 6).

### Claude Design

1. Start a new Claude Design project named "SmartMatch class exercise refresh".
2. Paste the **Claude Design style preamble** (section 5) first. It includes
   the CSS variables, so every screen uses the same tokens.
3. Attach `../DESIGN.md`, the SVGs in `../assets/svg/`, and the reference
   PNGs each prompt lists.
4. Paste one screen's Claude Design prompt. Each asks for an interactive
   prototype with a **state switcher**, so every required state can be
   reviewed in one artefact.
5. Ask for 1280 and 390 in the same artefact (each prompt says so).

## 3. Keep outputs consistent

- Always paste the preamble first. Never edit tokens inside a single prompt.
- Use only the fictional data in section 7. Two screens that disagree on a
  name, a count or a weight will confuse the review.
- Font stand-ins in both tools: **Archivo** (SemiExpanded width, 600–700) for
  Transducer CPP, **Source Serif 4** for Proxima Sera, **Figtree** for Usual.
  Production keeps the licensed faces.
- Check each output against [`../DESIGN.md` section 10](../DESIGN.md#10-do-and-dont)
  before keeping it. Reject any output that shows a percentage, a score, a
  confidence, a bar next to a person, a new colour, an eyebrow label above the
  page title, or copy that describes the data other than as "fictional
  profiles shaped by overall survey percentages".
- Keep the reference mock-ups in mind but not their palette: the Fable
  mock-ups use teal and Fraunces. This system uses CPP Green and the CPP font
  roles. Borrow layout, not colour.

## 4. Stitch style preamble

Paste this once per Stitch project.

```text
Design system for every screen in this project.

Product: "Smart Match class exercise", a no-login classroom game for a
university business course, AI in Marketing, at Cal Poly Pomona's College of
Business Administration. Teams of students act as the person promoting a
campus career event with 60 seats and choose whom to invite from 300
fictional profiles shaped by overall survey percentages. Screens are
projected in a lit classroom and also used on laptops and phones.

Mood: warm, crafted, calm and credible. Stationery of a campus event:
white card stock on warm eggwhite paper, green ink, a gold highlighter.
Not a dashboard, not a kids' game, not a newspaper costume.

Colours (use only these):
- Page background #F8F6F1. Cards #FFFFFF. Wells and table header band #F2EEE8.
- Text #163229. Secondary text #59665F.
- Primary (buttons, links, focus, rank numerals) CPP Green #005030, text on it #FFFFFF.
- Selected tint #D9EADF with text #003D24.
- Highlighter CPP Gold #FFB81C (fills only, never text on white); gold wash #FFF1CC; gold text #7A5200.
- Support tint #E8F2D8. Seats already taken #8C6D62. Control outlines #8F7A70.
- Error #BA1A1A (only for connection errors).
No other hues. No gradients. No dark mode unless asked.

Type: headings in Archivo SemiExpanded 600 (page title 48px), section heads
in Source Serif 4 600 (32px), UI and body in Figtree 400 at 20px, labels
Figtree 600 at 18px. Numbers use tabular figures. Sentence case everywhere.
No uppercase labels, no eyebrow text above the page title.

Shape: cards 14px radius with a soft two-layer shadow and no border.
Inputs and buttons 10px radius. Pills only for small chips. 4px spacing grid;
24px card padding; 48px between sections. Primary button 56px tall.

Icons: Lucide, 2px stroke. No emoji. No photos. No illustrations of people.

Always show a slim gold-wash ribbon at the top: an info icon, the bold prefix "Fictional data —" and the text
"All student profiles are fictional, shaped by overall survey percentages."

Never show a percentage, a score, a match strength, a confidence, a star
rating or a progress bar next to a person.
```

## 5. Claude Design style preamble

Paste this once per Claude Design project, then attach `../DESIGN.md`.

```text
You are designing screens for the Smart Match class exercise refresh. The
attached DESIGN.md is the system; follow it exactly. Build every screen as
an interactive HTML/CSS prototype (React is fine) that uses these CSS custom
properties and nothing else for colour, type, space, radius and shadow.

:root {
  --ce-page:#F8F6F1; --ce-surface:#FFFFFF; --ce-surface-sunk:#F2EEE8;
  --ce-ink:#163229; --ce-ink-muted:#59665F;
  --ce-primary:#005030; --ce-on-primary:#FFFFFF; --ce-primary-tint:#D9EADF;
  --ce-gold:#FFB81C; --ce-gold-tint:#FFF1CC; --ce-gold-ink:#7A5200;
  --ce-avocado:#A4D65E; --ce-avocado-tint:#E8F2D8; --ce-bay:#CFBAB0;
  --ce-seat-taken:#8C6D62; --ce-line:#D9CBC4; --ce-line-strong:#8F7A70;
  --ce-danger:#BA1A1A;
  --ce-font-display:"Archivo", "Arial Narrow", sans-serif; /* stands in for Transducer CPP */
  --ce-font-serif:"Source Serif 4", Georgia, serif;          /* stands in for Proxima Sera */
  --ce-font-body:"Figtree", Inter, system-ui, sans-serif;   /* stands in for Usual */
  --ce-radius-control:10px; --ce-radius-card:14px; --ce-radius-pill:999px;
  --ce-elev-1:0 1px 2px rgba(22,50,41,.06),0 4px 12px rgba(22,50,41,.06);
  --ce-elev-2:0 2px 4px rgba(22,50,41,.06),0 12px 28px rgba(0,80,48,.10);
  --ce-elev-3:0 8px 16px rgba(22,50,41,.08),0 24px 60px rgba(0,80,48,.16);
  --ce-ease-out:cubic-bezier(0.16,1,0.3,1);
  --ce-ease-in-out:cubic-bezier(0.65,0,0.35,1);
}
.dark {
  --ce-page:#10251D; --ce-surface:#173228; --ce-surface-sunk:#244237;
  --ce-ink:#F2EEE8; --ce-ink-muted:#CFC5BE; --ce-primary:#A4D65E;
  --ce-on-primary:#10251D; --ce-primary-tint:#315343; --ce-gold-tint:#3A3420;
  --ce-gold-ink:#FFD37A; --ce-seat-taken:#B89A8E; --ce-line:#496257;
  --ce-line-strong:#8FA89C; --ce-danger:#FFB4AB;
}

Load Archivo (wdth 110, 600-700), Source Serif 4 (400, 600) and Figtree
(400, 600, 700) from Google Fonts. Type sizes: page title 48/56 display 600;
section head 32/40 serif 600; card title 24/32 serif 600; body 20/30; reason
line 18/28 serif; labels 18/24 body 600; at 390px wide use 32, 26, 21, 17, 16, 16.

Rules that override anything you would do by habit:
- Light mode by default; include a dark toggle only when asked.
- One h1 per screen. No eyebrow or kicker text above it. No icon beside it.
- Cards have a shadow or a border, never both. No card inside a card.
- No left-border accent stripes. No gradient fills or gradient text.
- No percentages, scores, confidences or bars attached to a person. Rank is a
  position. Weights are the team's own numbers and may be shown.
- Show server sentences verbatim, including their full stop.
- Every screen has a state switcher (a small fixed toolbar, bottom-right,
  outside the design) listing the states the prompt asks for.
- Every motion honours prefers-reduced-motion with the fallback DESIGN.md names.
- Focus ring: 3px solid var(--ce-primary), offset 3px, on every focusable element.
- Touch targets at least 44x44px.
- Top of every screen: a slim ribbon in --ce-gold-tint with a Lucide Info
  icon in --ce-gold-ink, a bold "Fictional data —" prefix, and "All student profiles are fictional, shaped by
  overall survey percentages."
- Show both a 1280px frame and a 390px frame, side by side, unless the prompt
  says otherwise.
```

## 6. Where outputs go

Generated files stay outside the repo, per the precedent in
[`../../../ui/pilot-prototype-prompts.md`](../../../ui/pilot-prototype-prompts.md).
Bring back only: the prompt used (if changed), selected PNG screenshots
(≤ 400 KB each), and review notes. Add a screenshot to `../assets/mockups/`
only when the review picks it.

## 7. Shared fictional data

Every prompt draws from this set. Names are fictional.

**Events** (from the data file; names are Ann's):

| Round | Event | Topics (illustrative) | Aimed at |
|---|---|---|---|
| 1 | Northline Analytics | Technology / information systems; Marketing / advertising / public relations | Computer Information Systems; International Business & Marketing |
| 2 | Harbor Consumer Brands | Retail / consumer goods; Marketing / advertising / public relations | International Business & Marketing; Management & Human Resources |

Ten past events, for attendance history: Fall Career Fair; Resume Lab
Workshop; Consulting Industry Panel; Accounting Firms Night; Startup Pitch
Night; Supply Chain Info Session; Data Analytics Workshop; Nonprofit
Networking Mixer; Retail Leadership Panel; Case Competition Kickoff.

**Factor labels** (verbatim, from the server): "same major"; "said they are
interested in this topic"; "career goal fits this event"; "went to similar
events before".

**Weights:** default 0.25 each. Team 4's current weights: same major 0.40;
interested 0.25; career goal 0.25; similar events 0.10.

**Saved settings (Team 4, Northline):** "Major first" (0.60, 0.15, 0.15,
0.10); "Interests first" (0.15, 0.45, 0.25, 0.15); "Balanced" (0.25 each).
Comparing "Major first" with "Interests first": 12 names on both lists.

**Majors:** Accounting; Computer Information Systems; Finance, Real Estate &
Law; International Business & Marketing; Management & Human Resources;
Technology & Operations Management. **Years:** Freshman, Sophomore, Junior,
Senior. **Markers:** "major only"; "major plus events attended";
"completed card".

**Ranked list, Northline, first 10 of 30 (Team 4's weights):**

| Rank | Name | Major | Year | Marker | Reason line (verbatim style) |
|---|---|---|---|---|---|
| 1 | Maya Tran | Computer Information Systems | Senior | completed card | What counted: same major; said they are interested in this topic; career goal fits this event. |
| 2 | Daniel Okafor | International Business & Marketing | Senior | completed card | What counted: same major; career goal fits this event. |
| 3 | Priya Patel | Computer Information Systems | Junior | major plus events attended | What counted: same major; went to similar events before. |
| 4 | Jordan Kim | Computer Information Systems | Senior | major only | Same major; nothing else on file. |
| 5 | Alexis Rivera | Computer Information Systems | Junior | major only | Tied on major; ordered by year. |
| 6 | Ethan Nguyen | International Business & Marketing | Senior | major plus events attended | What counted: same major; went to similar events before. |
| 7 | Sofia Morales | Technology & Operations Management | Senior | completed card | What counted: said they are interested in this topic; career goal fits this event. |
| 8 | Marcus Chen | International Business & Marketing | Junior | major only | Tied on major; ordered by year. |
| 9 | Hannah Lee | International Business & Marketing | Sophomore | major only | Tied on major; ordered by year. |
| 10 | Diego Garcia | Accounting | Senior | major plus events attended | What counted: went to similar events before. |

Ranks 11–30: Chloe Brooks, Ravi Shah, Grace Park, Tyler Reyes, Leila Haddad,
Brandon Cole, Nina Vasquez, Kevin Yu, Aisha Bello, Lucas Ortiz, Emily Wang,
Omar Farah, Jade Lim, Noah Adams, Isabel Cruz, Andre Mensah, Mei Zhou, Caleb
Foster, Rosa Delgado, Victor Huang. Mix the six majors and four years; most
reason lines are "Tied on major; ordered by year." or "Same major; nothing
else on file.".

**Coverage notice:** "Nobody on this list is a Freshman or a Finance, Real
Estate & Law major."

**Round one results (Northline, final setting "Major first"):** seats 60;
already coming 8; your invitations added 6; still open 46. Team's list:
invited 30, signed up 6, attended 4. If you emailed everyone: invited 300,
signed up 41, attended 27. Signed up: Daniel Okafor, Alexis Rivera, Marcus
Chen, Grace Park, Brandon Cole, Emily Wang. Attended: Daniel Okafor, Marcus
Chen, Grace Park, Emily Wang.

**Asking for more (Team 4 chose "A small reward."):** cards filled in 9;
stopped opening messages 0; topics added from the first event 34.

**Round two results (Harbor, final setting "Interests first"):** seats 60;
already coming 8; your invitations added 11; still open 41. Team's list:
invited 30, signed up 11, attended 8. If you emailed everyone: invited 300,
signed up 44, attended 29. Your team, round one: invited 30, signed up 6,
attended 4 (46 seats empty).

**Instructor:** data file "Ann's file, 25 September" from
`smartmatch_exercise_300.xlsx`, 300 profiles, 12 events, 2 events in the
exercise, 70 profiles with a completed card; invite limit 30. Teams:

| Team | Saved settings | Result runs | Asking | Asked |
|---|---|---|---|---|
| 1 | 3 | 1 | A small reward. | yes |
| 2 | 2 | 1 | Required. | no |
| 3 | 3 | 0 | not picked | no |
| 4 | 3 | 2 | A small reward. | yes |
| 5 | 1 | 0 | not picked | no |
| 6 | 0 | 0 | not picked | no |

**License line (verbatim):** "For California State Polytechnic University,
Pomona — College of Business Administration instructional use only. All
student profiles are fictional."

## 8. Reference material

| Kind | Path |
|---|---|
| Spot SVGs | `../assets/svg/` (7 files, see DESIGN.md section 4) |
| Fable "The Room" mock-ups | `../assets/mockups/room/` |
| Fable "The Ledger" mock-ups | `../assets/mockups/ledger/` |
| Library picks | DESIGN.md section 5 (motion) and [`../experiments.md`](../experiments.md#library-picks) |
| Generated mock-ups (2026-09-26) | [`../generated.md`](../generated.md), images in `../assets/generated/` |
