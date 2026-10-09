# Smart Match CPP presentation mockups: independent audit

**Audited:** 2026-10-06, branch `demo/cbach-advisory-2026-10-08`, against `../DESIGN.md`.
**Method:** each mockup served on `127.0.0.1:8780` and driven in headless Chromium (Playwright 1.64, the engine behind playwright-cli) at 1440×900, 1280×720 and 390×844; also opened once each under `file://`. 29 states × 3 widths × 3 mockups measured by computed-style script; the guided path walked live at 1440 and 1280; every 1440 screen looked at.
**Evidence:** `screenshots/` (321 PNG). Names: `<a|b|c>-<state>-<width>.png` (deep-link states), `<a|b|c>-walk-<nn>-<step>-<width>.png` (live guided path), `<a|b|c>-t2-…` (targeted tests).
**Nothing in `mockups/`, `shared/`, `source/` or `DESIGN.md` was changed.**

## 1. Verdict

| Mockup | Verdict | BLOCKER | HIGH | MEDIUM | LOW | The single most important fix |
|---|---|---|---|---|---|---|
| A · Blueprint | READY AFTER FIXES | 0 | 6 | 7 | 5 | A-01: let the clicker's PageDown leave the weight slider; then A-02 (green box round every title) |
| B · Workbench | READY AFTER FIXES | 0 | 4 | 4 | 4 | B-01: a double-click on "Not sure yet" silently answers "No thanks" and moves Grace from #4 to #8 |
| C · Walkthrough | READY AFTER FIXES at 1440×900 or larger. NOT READY at 1280×720 | 0 | 4 | 8 | 4 | C-02 to C-04: at 1280×720 the rail hides the doors' bottoms, the profile card's "Next step" and the help buttons |

What holds in all three (measured, not taken from NOTES):

- Data: `SMC.selfTest()` 9 of 9 pass; TV-A, TV-B, TV-C, TV-D rows identical in all three; F1 (70 → 71), F3 (20 / 40 / 50 / 55) correct.
- Wording: no visible string differs from section 2. No string is missing on the states crawled.
- Honesty: N1 in the viewport and on top in all 29 states × 3 widths; all 8 status labels verbatim and above the fold; N2 in both transcripts (one exception: B-02).
- Scale scan: 0 spacing, font-size, radius, border-plus-shadow or target offenders at 1440 and 1280 (pseudo-elements not scanned).
- Contrast: lowest text pair 5.17 (A), 5.55 (B), 5.00 (C). The only pairs below are `aria-disabled` controls at 45% opacity (2.37, 3.22).
- Console: 0 errors, 0 warnings. Network: 0 requests to another host.
- `file://`: all three rendered with data (300 students), fonts and GSAP 3.15.0 from disk.

The weak point common to all three is the room, not the build: at 1280×720 each one hides part of a hero screen (section 6).

## 2. Findings: A · Blueprint

Severity: BLOCKER breaks the demo or misleads the audience · HIGH visibly wrong from the back row, wrong wording, or stalls the presenter · MEDIUM a careful viewer notices · LOW.

| ID | Sev | Screen | Viewport | What is wrong (measured) | Evidence | Exact fix |
|---|---|---|---|---|---|---|
| A-01 | HIGH | match | all | After dragging "Same major" with the mouse the slider keeps focus. The clicker's PageDown then does not go to stop 9; it lowers the weight 10 → 9. Same after typing in the records search field. Contract-conformant (7.16); see D-08 | `a-mouse-drag-major10-1440.png`; script: before `value=10, activeElement=range`, after PageDown `h1="Match students to an event", value=9` | `app.js` line 1320: remove `inSlider` from `if (inText \|\| inSlider) return;`. Search field: `blur()` on Enter |
| A-02 | HIGH | all 8 portal screens | all | Every PageDown or PageUp draws a 3px green box round the screen title. `h1:focus-visible` computes `outline: solid 3px rgb(0,80,48)`. B and C draw none | `a-walk-30-pgdn-match-1440.png`, `a-walk-25-pgdn-growth-1440.png`, `a-walk-26-pgdn-overview-1440.png` | `styles.css` after line 102: `h1[tabindex="-1"]:focus-visible { outline: none; }` |
| A-03 | HIGH | readiness | 1440×900 | "Chat with the CBACH assistant bot" opens its panel below the fold. N2 top is at y=908, page scroll stays 0, so nothing visible changes. At 1280×720 the page does scroll (N2 at y=430) | `a-walk-17-open-bot-1440.png` | `app.js` `setHelp()` (line 893): after the panel renders call the existing `scrollIntoView(panel)` helper (line 731) for all four panels |
| A-04 | HIGH | interview, recs, overview, match | 1280×720 (match also 1440) | The floating "Presenter guide" button covers content. 1280: the profile card's "Undecided · exploring consulting or data roles", "match 3 of 10", a `Register` button, "82%". 1440: "Profile card" in row 6. T23 is not fixed | `a-t2-interview-turn5-1280.png`, `a-recs-after-1280.png`, `a-walk-30-pgdn-match-1440.png` | `styles.css` `.sm-guide-button`: dock it in the top bar beside `Switch portal` at `min-width: 1024px` instead of `position: fixed` bottom right |
| A-05 | HIGH | match | 1280×720 | 3 full rows only (rows are 81px, table body starts at y=462). Grace's row #4 is cut by the fold. Item 31 passes (3 rows) but the row the presenter points at is hidden | `a-match-after-1280.png` | `styles.css`: put the Grace line on the picker's row; under `@media (max-height: 800px)` use cell padding 8 / 12. Or run the room at 90% zoom (4 rows) |
| A-06 | HIGH | interview | 1280×720 | The transcript log is 177px (turn 1) and 131px (turn 2) tall. The assistant's question is cut mid-line: "Jobs Q&A. What made you go to the cloud…" is hidden | `a-walk-02-door-student-1280.png`, `a-walk-05-iv-1-curious-1280.png` | `styles.css` transcript log: `min-height: 240px`; let the page scroll instead of shrinking the log |
| A-07 | MEDIUM | interview | all | A double-click bleeds into the next turn. On "I'm curious about tech jobs" it also toggles Entrepreneurship (third pill; turn reads "Technology, Entertainment, Entrepreneurship"). On "Not sure yet" it also presses "Yes, help me compare". On "Yes, help me compare" it also presses "Show my events" and leaves the screen. Grace stays #4 | script `t3` DBL: picks `[Technology, Entertainment, Entrepreneurship]` | `app.js` `answer()` (line 594): ignore activation for 350ms after a turn renders, or `if (e.detail > 1) return;` |
| A-08 | MEDIUM | interview | 1440 | Returning to a finished interview (PageUp from stop 3, or a deep link) opens the log mid-turn: "and data roles?" is cut under N2. Section 7.10 says a turn starts at its top | `a-interview-done-1440.png` | `app.js` interview render: set `log.scrollTop` to the last assistant turn's `offsetTop`, not `scrollHeight` |
| A-09 | MEDIUM | recs | 1440 | After `Register` the page scrolls 163px. The title, the status label and the registered event's title go under the sticky bar | `a-walk-12-register-settled-1440.png` | `styles.css` `.sm-checkin`: QR at 116px and padding 16 so the scroll is under 100px; or place the card beside the list at 1440 as B does |
| A-10 | MEDIUM | match, records | 1440 | Names wrap to two lines ("Emeka / Soto", icon + "Grace / Delgado") while "Why on the list" is 360px wide. Column widths 52 / 118 / 214 / 360 / 156. "Profile card (AI / interview)" also wraps | `a-walk-30-pgdn-match-1440.png`, `a-walk-28-search-delgado-1440.png` | `styles.css`: `td:nth-child(2), td:last-child { white-space: nowrap; }` on both tables |
| A-11 | MEDIUM | match | 1440 | The four weight controls sit 16px apart. One control's value is 14–16px from the next label: "3 Said they're interested 3 Career goal fits" reads as one line | `a-walk-30-pgdn-match-1440.png` | `styles.css` line 484 `.sm-weights`: column gap `--sm-space-4` → `--sm-space-6` |
| A-12 | MEDIUM | match | keyboard | At 10 the value "10" collides with the thumb's focus ring | `a-walk-31-major-10-1440.png` | `styles.css` line 486 `.sm-weight`: first grid row `minmax(32px, auto)` |
| A-13 | MEDIUM | readiness, overview, recs | 1280×720 | More below the fold than at 1440: help group 2 (bottom 798), chart row 1 (851), third event before the interview (783) | fold script; `a-readiness-after-1280.png`, `a-overview-after-1280.png` | Room: 90% zoom or a viewport at least 800px high |
| A-14 | LOW | match | keyboard | Page keys move a weight by 1. Section 7.8 says 2; B and C do 2 | script: 10 → 9 | `app.js`: handle PageUp / PageDown on the range as ±2 (only if D-08 keeps Page keys in sliders) |
| A-15 | LOW | readiness | 1440 | The toast sits over reading content for 4 seconds (bot footnote, marker titles) | `a-walk-16-readiness-top-after-tick-1440.png`, `a-walk-18-bot-ask-review-1440.png` | Accept, or shorten to 3 seconds |
| A-16 | LOW | entry | 1280×720 | The entry scrolls 24px (page 744 high) | scan `scrollHeight=744` | `.sm-entry` bottom padding 48 → 24 under `max-height: 800px` |
| A-17 | LOW | all | 390 | Skip link is 186×40, under 44 | scan `a.sm-skip drawn 186x40` | `.sm-skip { min-height: 44px; }` |
| A-18 | LOW | interview, match | 390 | The floating guide button covers a reply chip and a weight value | `a-interview-t1-390.png`, `a-match-after-390.png` | As A-04 |

## 3. Findings: B · Workbench

| ID | Sev | Screen | Viewport | What is wrong (measured) | Evidence | Exact fix |
|---|---|---|---|---|---|---|
| B-01 | HIGH | interview → recs → match | all | A double-click on "Not sure yet" also presses "No thanks", which lands under the pointer. Goal is stored as "Undecided". Result: Grace is #8 with total 4 (not #4, 6); Events for me opens with "The Business of Streaming · match 4 of 10" and "match 6 of 10" never appears. Nothing on screen says why. Also: double-click on turn 1 adds Supply chain; on "Yes, help me compare" it skips turn 5 | script `t3` DBL: `goal:"Undecided"`; `SMC.rankStudents` with that state: Grace #8, total 4 | `app.js` `ivAnswer()` (line 460): ignore activation for 350ms after a turn renders, or `if (e.detail > 1) return;` |
| B-02 | HIGH | readiness, bot | 1440×900 | After a suggested question is pressed, focus moves to the bot field and the pane scrolls. N2 "Scripted for this demo. Not a live AI." ends at y=44, under the sticky header; the student's turn is cut in half; the first bot turn is gone. H3 fails at the moment the bot answers. At 1280×720 N2 stays visible (y=144) | `b-t2-bot-after-ask-1440.png`; script `n2Visible:false` | `app.js` line 922: `target.focus({ preventScroll: true })`, then scroll the panel so its label sits under the header (`scroll-margin-top` = header height) |
| B-03 | HIGH | entry | 1280×720 | Door bottoms 450 / 594 / 738: the third door is cut at 720 and the demo line (bottom 810) is off screen. The entry also scrolls 6px at 1440×900 (page 906 high), so a scrollbar shows on the first screen | `b-entry-1280.png`; fold script | `styles.css` `.b-entry` (line 437): title offset 120 → 64, door padding 24 → 16 under `max-height: 800px`; remove the 6px overflow |
| B-04 | HIGH | match | all | As A-01. After a mouse drag of "Same major", PageDown lowers the weight 10 → 8 and does not change stop | `b-mouse-drag-major10-1440.png`; script | `app.js` line 782: drop the slider's own Page-key handler; let line 1087 handle it |
| B-05 | MEDIUM | all portal screens | 1440 | N1 is the least visible of the three: 14px, two lines, bottom left of the sidebar at y=780. Body and table text are 16px. Contract-conformant; it is the back-row risk section 13.8 names | scan `marker=12,780 14px`; `b-walk-30-pgdn-match-1440.png` | `styles.css` `.sm-marker` in the sidebar: 16px, and move it under the portal name |
| B-06 | MEDIUM | match | 1280×720 | Rows grow to 89px: reasons wrap to 3 lines (section 4 allows 2). "What we / know" and "Profile / card" wrap. Columns 68 / 109 / 155 / 277 / 103. 5 rows visible | `b-match-after-1280.png` | Weights pane 304 → 256px under 1366px wide; `td:last-child { white-space: nowrap; }` |
| B-07 | MEDIUM | match | 1440 | Uneven wraps: "Camila / Alcantar", "Grace / Delgado", "Major + / events" | `b-walk-30-pgdn-match-1440.png`, `b-walk-31-major-10-1440.png` | `td:nth-child(2), td:last-child { white-space: nowrap; }` |
| B-08 | MEDIUM | readiness | 1280×720 | The bot panel opens below the fold (N2 top y=722) | script `afterOpen y=722 onTop=false` | `openHelp()` (line 572): scroll the panel into view |
| B-09 | LOW | match | all | With all weights 0 the footer still says "Showing 15 of the top 30." above N7 (A hides it) | `b-walk-37-all-zero-1440.png` | Hide the line when the list is empty |
| B-10 | LOW | interview, readiness, match | 390 | The guide button covers a reply chip, a tile and a weight value | `b-interview-t1-390.png`, `b-match-after-390.png` | Dock the button in the top strip at 390 |
| B-11 | LOW | readiness | 1440 | The toast covers a marker step for 4 seconds | `b-walk-16-readiness-top-after-tick-1440.png` | Accept |
| B-12 | LOW | match, guide open | 1280×720 | The guide panel overlays the table and the invitations button (rehearsal only) | `b-match-guide-1280.png` | Accept; presenters keep the guide closed on the projector |

## 4. Findings: C · Walkthrough

| ID | Sev | Screen | Viewport | What is wrong (measured) | Evidence | Exact fix |
|---|---|---|---|---|---|---|
| C-01 | HIGH | match | all | Clicker stalls twice. After a slider drag PageDown lowers the weight 10 → 8. After picking an event the `<select>` keeps focus and PageDown jumps the event to "Harbor Consumer Brands" (value `E12`) instead of changing stop. A and B change stop from the select | `c-mouse-drag-major10-1440.png`; script `pgdnInSelect: sel=E12` | `app.js` line 1077: `const adjusting = false;` (Page keys always change stop), and remove the slider Page handler at line 788 |
| C-02 | HIGH | entry | 1280×720 | The rail's top is at y=648. Door bottoms are at 673: the doors run under the rail, and the demo line (713) is hidden. At 1440×900 the entry scrolls 37px (page 937 high) | `c-entry-1280.png`; fold script | `styles.css` line 169 `.c-entry`: under `max-height: 800px` title `text-64`, padding 16; size the stage as `100dvh − bar − rail` |
| C-03 | HIGH | interview | 1280×720 | The profile card ends at y=747; the "Next step" value ends at 715, under the rail. The card filling in, the point of the stop, cannot be seen without scrolling. Turn 2's assistant text is cut at its third line (log 120px) | `c-t2-interview-turn5-1280.png`, `c-walk-05-iv-1-curious-1280.png` | `styles.css`: under `max-height: 800px` screen title `text-36`, description `text-20`, card row gap 8 |
| C-04 | HIGH | recs, readiness | 1280×720 | recs: rows 2 and 3 end at 697; row 2's `Register` is under the rail. readiness: all four help buttons (687 / 749) are under the rail | `c-recs-after-1280.png`, `c-readiness-after-1280.png` | Same compact rule as C-03; ring 200 → 150px under `max-height: 800px` |
| C-05 | MEDIUM | recs | 1440 | After `Register` the page scrolls 237px. The gold "Registered" button and the event title leave the screen; "match 6 of 10" is cut mid-line at the top bar | `c-walk-12-register-settled-1440.png` | Scroll only until the code and the points are visible; or `scroll-margin-top` so the feature row's button stays |
| C-06 | MEDIUM | match, records, tiles | all | Figures are proportional. Computed `font-variant-numeric: normal` on table cells and the weight value (20px). "1111" is 28px wide, "0000" 48px. Ranks, counts and count-ups change width. `body` sets `tabular-nums` (line 56) but each later `font:` shorthand resets it (cause inferred from the stylesheet; widths measured) | script `digits: 1111=28, 0000=48` | `styles.css`: add after the component rules `td, th, output, .sm-num, .sm-stat, .sm-weight__value { font-variant-numeric: tabular-nums; }` |
| C-07 | MEDIUM | growth | 1440×900 | The closing line is cut by the rail after its first line: "…Her record shows a path her" (page 1023 high). It is the stop's punchline | `c-walk-25-pgdn-growth-1440.png` | Move the closing line above the two tiles, or tighten the timeline's gaps by 24px |
| C-08 | MEDIUM | interview | all | Double-click bleed: turn 1 also toggles Government; "Yes, help me compare" also presses "Show my events". Grace stays #4 | script `t3` DBL | `app.js` `answer()` (line 569): 350ms guard as A-07 |
| C-09 | MEDIUM | match, guide open | 1280×720 | Weight labels wrap onto the track: "Said they're / interested" and "Went to similar / events" overlap the thumbs; the title wraps to 2 lines | `c-match-guide-1280.png` | `.sm-weights`: 2 columns when the stage is under 900px wide |
| C-10 | MEDIUM | match | 390 | The five event radio options are misaligned: text runs to the card edge and the first card is indented differently from the rest | `c-match-after-390.png` | Radio label: `display: grid; grid-template-columns: 24px 1fr; gap: 12px; padding: 12px 16px;` |
| C-11 | MEDIUM | match | keyboard | "10" collides with the thumb's focus ring | `c-walk-31-major-10-1440.png` | As A-12 |
| C-12 | MEDIUM | entry | 1440×900 | The first screen scrolls 37px, so a scrollbar shows on the projector | scan `scrollHeight=937` | As C-02 |
| C-13 | LOW | readiness | 1440 | The toast covers two help buttons for 4 seconds | `c-walk-16-readiness-top-after-tick-1440.png` | Accept |
| C-14 | LOW | match | all | "Showing 15 of the top 30." stays with zero rows | `c-walk-37-all-zero-1440.png` | Hide when empty |
| C-15 | LOW | match, records | all | Hidden text has no space: "Grace Delgado, the student from the demoGrace Delgado" | DOM text of Grace's row | Add a space after the hidden span |
| C-16 | LOW | interview, bot | all | Speaker label: muted `#59665f` on green-soft is 5.00:1 at 14px, exactly at the floor | scan contrast table | Use `--sm-ink` for the speaker label |

## 5. Section 11 checklist

P pass · F fail · N not checked · P* pass with a note. "Builder" marks where my result differs from NOTES.md.

| # | Item | A | B | C | Note |
|---|---|---|---|---|---|
| 1 | N1 on all screens, 1440 and 390, guide open and closed | P | P | P | Guide-open checked on 4 screens at 1440 and 1280, not at 390 |
| 2 | Status labels verbatim, above the fold; check-in "Planned" | P | P | P | |
| 3 | N2 in both transcripts, stays when the log scrolls | P | **F** | P | B-02. Builder B: pass |
| 4 | No typing indicator or streamed text | P | P | P | |
| 5 | Demo line verbatim | P | P | P | |
| 6 | "Planned · draft markers" and closing line | P | P | P | |
| 7 | Only made-up people; no file input | P | P | P | C shows "Chau" / "Janice" on the rail (14.4) |
| 8 | Section 2.2–2.11 strings verbatim | P | P | P | Unreachable strings confirmed in code only |
| 9 | Interview turns and options | P | P | P | Walked 1, 2, 3, 4a, 4b, 5 and "None of these" |
| 10 | Five bot rules; booking button on 2, 4, 5 | P | P | P | |
| 11 | Nine guide entries | P | P | P | |
| 12 | No string outside section 2; W1–W5 not applied | P | P* | P | B adds `Ctrl` `K` (13.3) |
| 13 | Nothing truncated or clipped, 1440 and 390 | P* | P | **F** | A-08 (log opens mid-turn). C-10. Builder C: pass |
| 14 | `shared/data.js` classic script, unchanged, no copy | P | P | P | `git status` shows `shared/` untouched |
| 15 | `SMC.selfTest()` all pass | P | P | P | 9 of 9 |
| 16 | TV-A and "#4" line | P | P | P | |
| 17 | TV-B, all CIS, "#27" | P | P | P | |
| 18 | Before-interview line and rows | P | P | P | |
| 19 | After-interview rows 6 / 4 / 3 | P | P | P | |
| 20 | 4% / 13% / 17%, target 60% | P | P | P | |
| 21 | Points 20 / 40 / 50 / 55 on three screens | P | P | P | |
| 22 | Overview 300 / 100 / 70 → 71 / 200 and charts | P | P | P | |
| 23 | Records 25 rows, 300 of 300; Delgado 14 | P | P | P | |
| 24 | "Graduate school" → turn 4b, card value | P* | P* | P | Turn 4b seen in all; card value read only in C |
| 25 | Reload keeps state; Reset clears | P | P | P | |
| 26 | Spacing on the scale | P | P | P | Pseudo-elements not scanned |
| 27 | Font sizes on the scale, none under 14px | P | P | P | |
| 28 | Radii; border or shadow; nesting | P* | P* | P* | Nesting not measured |
| 29 | Above the fold at 1440×900 | P | P | P* | C-07 (growth is not in 5.2's list) |
| 30 | 390: no horizontal scroll, stacked rows, 14px | P | P | P* | C-10 |
| 31 | 1280×720 match: picker, weights, line, 3 rows | P | P | P | A and C show exactly 3; Grace's row is cut (A-05) |
| 32 | Fonts blocked: no overflow | P* | P* | P* | 1440 only, Linux fallback font. A shows 3 match rows, not 5 |
| 33 | Green and gold token values | P | P | P | |
| 34 | Every pair at least 4.5 / 5 / 7 | P | P | P | Computed from the rendered DOM |
| 35 | Gold never text, border or ring on light; target mark | P* | P* | P* | Keyline looked at, not measured |
| 36 | Control outlines at least 3:1 | N | N | N | |
| 37 | Light when the OS is dark; dark by opt-in | P* | P* | P* | First half pass in all. Dark values (6.4) not checked. C has no dark (D-07) |
| 38 | Not by colour alone | P | P | P | |
| 39 | Tab order and visible ring | P | P | P* | C: rail before main (its deviation 8) |
| 40 | Whole path by keyboard | N | N | N | Every control reached by Tab; full run not repeated |
| 41 | PageDown / PageUp / G | P | P | P* | X-01. See A-01, B-04, C-01 for what the rule does in the room |
| 42 | Focus on the new `h1`; one `h1`, `main`, `nav` | P | P | P | |
| 43 | No `disabled`; `aria-disabled` with a reason | P | P | P | |
| 44 | Transcripts announce the newest turn once | P* | P* | P* | Structure only; no screen reader |
| 45 | Targets 44×44 | **F** | P | P | A-17 (skip link 40px at 390). Builder A: pass |
| 46 | Outcomes persistent | P | P | P | |
| 47 | No modal | P | P | P | |
| 48 | Reduced motion: no travel | P | P | P | Emulated; 9 actions sampled each; 0 transforms |
| 49 | Nothing over 400ms | P | P | P | Longest measured: A 335ms, B 303ms, C 311ms |
| 50 | Input during animation completes it | P* | P* | P* | 12 fast PageDowns land on stop 9; row re-target not measured |
| 51 | Transform and opacity only; 33ms at 4× throttle | N | N | N | Indicative only: A worst frame 50ms, B 33ms, C 50ms (headless, key steps) |
| 52 | Nothing on scroll, timer or loop | P | P | P | 3 seconds idle: 0 moving elements |
| 53 | Opens under `file://`, no network | P | P | P | Builders B and C: not checked. Playwright Chromium on Linux, not Windows Chrome |
| 54 | Console clean | P | P | P | |
| 55 | GSAP and Flip 3.15.0, licence, no module | P | P | P | |
| 56 | File budget and folder contents | P | P | P | |
| 57 | NOTES.md format | P* | P* | P* | Skimmed, not line-checked |
| 58 | 19 screenshots | P* | P* | P* | Count only (19 each) |
| 59 | No other company's marks; logo unaltered | P | P | P | |
| 60 | Deep links | P | P | P* | C ignores `theme=dark` by design |

## 6. Cross-mockup consistency

Two-second test: pass. A is white cards on green-tinted grey with a left menu; B is a grey full-height sidebar with dense rows; C is paper, serif titles and a green rail. A and B share filled green buttons and a left navigation; density and the sidebar card keep them apart.

| ID | What differs | A | B | C | Recommendation |
|---|---|---|---|---|---|
| X-01 | PageDown while the event `<select>` has focus | next stop | next stop | changes the event to E12 | One rule (D-08) |
| X-02 | Page keys inside a slider | ±1 | ±2 | ±2 | D-08 |
| X-03 | `h1` ring after a stop change by key | drawn | none | none | D-09 |
| X-04 | "New from the interview" pills, reason chip, callout, `Say:` line | gold-soft | green or neutral | gold-soft | D-03 |
| X-05 | Rows leaving the visible 15 | removed at once | fade as clones | removed at once | D-05 |
| X-06 | After `Register` | page scrolls 163px, button stays | no scroll, card beside the list | page scrolls 237px, button leaves | Keep the pressed button on screen in all three |
| X-07 | "Showing 15 of the top 30." with zero rows | hidden | shown | shown | Hide in all |
| X-08 | N1 | top bar, 14px | sidebar bottom, 14px, 2 lines | top bar, 16px | 16px in all three |
| X-09 | Status label | 14px mono uppercase, tracked | 14px sentence case | 16px sentence case | A's is the hardest to read at distance; allow A sentence case |
| X-10 | Stop controls in the guide panel | above the steps | below `Say:` | below `Say:`, and on the rail | Same place in all three |
| X-11 | Focus after a bot suggested question | stays on the chip | moves to the field and scrolls | stays on the chip | B follows A and C (fixes B-02) |
| X-12 | Dark theme | ships | ships | none | D-07 |
| X-13 | "Registered" described reason | none | none | check-in card title | Cosmetic |
| X-14 | Bot panel on opening at 1440×900 | below the fold | in view | scrolled into view | A and B follow C |

Same in all three (checked): every string, all numbers, the three honesty components, the nine guide entries, toast wording and 4-second life, outcome messages, the 5-second reset confirm, state kept on reload.

## 7. DESIGN.md contradictions and one resolution each

| ID | Sections in conflict (quoted) | What each mockup did | Recommended single rule |
|---|---|---|---|
| D-01 | 5.6 "Rows of the match table visible at 1440×900: at least 6 / at least 10 / at least 5", "Table text 18px / 16px / 18px", "Table cell padding 12 / 16"; 12.6 "Six or more rows on screen"; 5.2 "at least 5 ranked rows (so #4 is on screen)"; 4 "a reason fits in 2 lines in the match table"; 12.4 "Content column max 1200px" | A 5 rows (81px rows). B 11. C 5 | One number: "Grace's row #4 whole and at least 5 full rows at 1440×900; at least 4 full rows at 1280×720". Delete 12.6's "six". 5.6's row heights are for single-line rows; reasons take 2 lines. Change item 31 from 3 rows to 4 |
| D-02 | 4 "Prose 45–70 characters per line at 1440. A screen description fits in 2 lines at 1440"; 13.4 "description beneath (max 70 characters per line)" | All three: 2 lines, about 95–100 characters | "A screen description: at most 2 lines at 1440, measure up to 100 characters. 45–70 applies to body prose (help body, notes, chat turns)". Delete 13.4's figure |
| D-03 | 6.1 B "No green-tinted surfaces except selected rows", gold "Only Grace's row tint, the planned label, the ring's target mark, and 'Registered'"; 13.7 the same list. Against 7.4 `sm-scripted` "gold-ink on gold-soft"; 7.14 reason chip "on gold-soft"; 7.6 `data-tone="new"` gold-soft; 7.16 "`Say:` line on gold-soft"; 7.10 assistant turn "green-soft"; 6.5 gold bars; 7.14 "outlined gold dot" against 6.1 "Never … a border … on a light surface" | A and C follow section 7. B keeps gold on N2, the gold bars, the third dot and the future dot; makes the chip, callout, `Say:` and pills neutral or green; assistant turns use `--b-sunk` | Part 2 may re-tone a surface, never an honesty component. All directions: N2 gold-soft, gold bars with the gold-ink outline, third dot gold, future dot = gold ring with a 1px gold-ink keyline (C's form). B only: reason chip, callout, `Say:` and "new" pills on `--b-sunk`; add these to 13.7 |
| D-04 | 5.6 B "Control height 40px (hit area 44px)"; 7.3 "Target at least 44×44px at every width"; 9.3 "Chips may draw 40px tall with a 44px hit area"; item 45 "Every target is at least 44×44px" | B draws 40px with a 44px hit area; A 44; C 52 | Item 45: "the hit area is at least 44×44; the drawn box may be 40px tall for chips, and for all controls in B" |
| D-05 | 8.3 `sm-rerank` "rows leaving fade out (fast)"; 8.4 never animate layout; 15 "animate the `<tr>` elements" | A and C remove at once; B fades clones in an overlay | "Rows leaving the visible 15 are removed on the first frame. No exit animation." Rank numerals already change at the start |
| D-06 | 8.5 "Everything in 8.3 that travels … uses GSAP"; 8.3 "GSAP Flip"; 8.7 "no frame over 33ms and no long task over 50ms" at 4× throttle; item 51 | A Flip with `simple: true`, self-reported borderline. B self-reported not passed. C passed on synthetic input. My run: A 50ms, B 33ms, C 50ms worst frame | Budget: "no frame over 50ms and no long task over 50ms at 4× throttle, measured on the classroom laptop". 33.3ms is two 60Hz refreshes and fails "33ms" to the letter. Allow Flip with `simple: true` or a hand-written FLIP |
| D-07 | Item 37 "dark appears only with `?theme=dark` or the theme control, and then passes section 6.4"; 6.4 "A direction may skip dark"; 14.3 "Dark theme: not shipped"; 3.7 lists `&theme=dark`; item 60 "All deep links of section 3.7 work" | A ships dark. B ships it (optional). C ignores the parameter | Split item 37: 37a "light when the OS is dark" (all); 37b "if the direction ships dark, it appears only by opt-in and passes 6.4" (A; B if kept). Item 60: "`theme=dark` is ignored without error where no dark theme ships" |
| D-08 | 1.2 "PageDown and PageUp move between stops"; 7.16 "unless focus is in a text field or a slider"; 7.8 "Page keys inside a slider do not change stop"; 2.12 `match` step 2 "Move the 'Same major' slider" | All three follow 7.16, so the clicker stalls after the scripted slider move (A-01, B-04, C-01). A and B change stop from the `<select>`; C does not | "PageDown and PageUp always change stop, from any control except a text input or textarea. Sliders keep arrows, Home and End." Add: Enter in the records search field releases focus |
| D-09 | 9.2 "focus goes to the new `<h1>` (programmatic, no visible ring unless reached by keyboard)"; 7 "Focus-visible: the ring … on every focusable element. Never removed" | A draws a ring after every PageDown (a clicker is a keyboard). B and C remove it | "`h1[tabindex="-1"]` is not a tab stop and never draws a ring" |
| D-10 | 7.9 C "A row of five radio cards"; 14.6 "a native select if the cards push the weights below the fold"; section 4 names never truncated | A select (wraps at 390). B select in the header, radios at 390. C select, radios at 390 | "A native `<select>` from 640px up, wide enough for the longest option; a radio list below 640px." Remove 7.9's per-direction table |
| D-11 | 14.6 match "Left third … Right two thirds: the table"; 5.2 "at least 5 ranked rows"; 4 reason in 2 lines | C built a control band over a full-width table | Adopt C's band in 14.6 |
| D-12 | 9.1 "Block labels are `<h2>`; event titles, marker names and card names are `<h3>`. No skipped levels"; `recs` has no block label | All three add a visually hidden `h2` "Events for me"; the profile card name is `h2` | Write both into 9.1 |
| D-13 | 2.2 "`Switch portal` (returns to the entry)"; 13.4 B "`Switch portal` … opens a non-modal popover" | B's popover lists "Smart Match CPP" first, which returns to the entry | Add to 13.4: "the first option is the entry, labelled with its title" |
| D-14 | 5.3 floor "Anything … a presenter reads aloud … 18px (A, C)"; 7.6 chips "label 16px or more"; 7.14 match line "16px or more" | A: toggle chips and the match line at 16px | "Chips and the match line may be 16px in every direction" |

## 8. Wording diff

Compared: every visible text fragment, hidden helper text, `aria-label`, `placeholder` and `alt` across 58 states per mockup, against DESIGN.md section 2 and `shared/data.js`.

| Check | Result |
|---|---|
| Strings that differ from section 2 | None in A, B or C |
| Strings missing | None on the reachable states. Present in code only (unreachable in the demo): "On track for your year.", "A little behind for a junior.", "Book a practice interview", "Interview ready is your lowest marker". "open to all students" comes from `shared/data.js` |
| Strings duplicated | None visible. B repeats the records count and the Grace line in a hidden status region (9.4) |
| New strings outside N1–N10 | B: `Ctrl` `K` beside "Switch portal" (13.3 names the hint). C: "Chau" / "Janice" on the rail (14.4). All: hidden "Grace:", "done", "not yet", "Grace Delgado, the student from the demo", ring name (section 7) |
| Typos | None visible. C-15: a missing space in hidden text |
| Capitalisation | Source strings are sentence case in all three. A draws labels, table heads, status labels and month names uppercase by CSS, at 14px or more. B shows "Nov"; A and C "NOV" |
| Terms across the three | Identical |
| Widows or orphans in titles at 1440 | None; every `h1` is one line (A 36px high at 28px; B 36; C 54 at 48px) |
| Numbers and dates (section 4) | Conform: "Thu Mar 4, 2027", "Mon Oct 12 · 10:00 am", "13%", "6 of 10", "4.6 of 5", "#4" |
| W1–W5 | Not applied in any: "You picked consulting and technology…", "from every major…", "Points exist in the early version", guide `recs` step 2 and `interview` step 2 are hers |
| N1 on every screen | Yes, 9 of 9, all three, three widths |
| Status label on every portal screen | Yes, 8 of 8, verbatim, above the fold |
| Scripted disclosure in both transcripts | Yes. Exception: B-02 |

## 9. Presenter readiness

### 9.1 Which one goes on the projector

**A · Blueprint**, once A-01 and A-02 are fixed, and if the browser window is at least 1440×800 CSS pixels.

1. It is Ann's layout, so her guide and the rehearsal carry over.
2. Its body text is 18px against B's 16px.
3. At 1440×900 it has one HIGH that survives the two fixes (A-03, one scroll on readiness).
4. Its other three HIGH findings (A-04, A-05, A-06) bite at 1280×720. At 1440×900 A-04 covers one table cell only.

If the room turns out to be 1280×720:

| Option | Result |
|---|---|
| A at 90% browser zoom (1422×800) | 4 match rows with Grace's row whole; profile card whole; help buttons in view. Text 16.2 device pixels. Preferred |
| B at 100% | Hub screens hold (5 match rows, charts in view). The entry's third door is cut (B-03); fix first |
| C at 100% | Do not use: C-02, C-03, C-04 |

Keep B open in a second tab for "what would staff use day to day?" (section 15), after B-01 and B-02.

### 9.2 Rehearsal risks

| Presenter | Stop | Risk | What to do |
|---|---|---|---|
| Chau | 2 interview | A double-click skips or changes an answer (A-07, B-01, C-08). In B it changes Grace's rank | Single clicks only. If the card shows a third interest or "Undecided" alone: `Start over` |
| Chau | 2 interview | W2: the guide's click path stops at "Yes, help me compare". Without "Show my events" the profile is not saved and stop 8 reads "Grace has not done her interview yet" | Always press "Show my events" |
| Chau | 3 events | After `Register` the page scrolls (A 163px, C 237px); the title leaves the screen | Say "the check-in code appears below" before clicking |
| Chau | 8 match | After moving the slider the clicker does nothing visible; it changes the weight (A-01, B-04, C-01). In C the same happens after picking an event | Until fixed: click the screen title once, then press Next |
| Chau | 8 match | Guide step 2 says "CIS majors take over the list". True at 10: all 15 rows are Computer Information Systems and Grace is #27, off the table | Drag fully to the right; read the line, not the table |
| Chau | 9 talk | T17: stop 8 invites students to the Mar 4, 2027 talk; stop 9 reports its results | Say "after the talk, this is what the partner would see" |
| Janice | 4 readiness | The LinkedIn checkbox is below the fold in A and C at 1440×900 (in view in B). After ticking, the ring (17%) is above the fold | Scroll down, tick, scroll back up |
| Janice | 4 readiness | A at 1440×900: the bot panel opens below the fold (A-03). B: the "Scripted" line scrolls away after a question (B-02) | A: scroll after clicking. B: say "this bot is scripted" aloud |
| Janice | 4 readiness | T10: `Go` opens Events for me, where no resume workshop is listed | Do not press `Go` |
| Janice | 6 overview | "students with a profile card" reads 71 after the interview, 70 before | Say "seventy-one, including Grace" only if stop 2 was done |
| Janice | 7 records | After typing "Delgado" the clicker does nothing: focus is in the search field | Click the title, then Next |
| Both | all | A draws a green box round each title after a clicker press (A-02) | Fix before Thursday |
| Both | all | `G` opens the presenter guide on the projector | Keep hands off the keyboard except the clicker |

### 9.3 Pre-flight checklist for the room

1. Open by double-click in Chrome on the classroom laptop. Check the entry shows the logo, three doors and the demo line.
2. Press F11 (full screen). Browser chrome costs about 120px of height.
3. Open DevTools once and read `innerWidth` × `innerHeight`. Target: at least 1440×800. If it reads 1280×720, set zoom to 90% (Ctrl and minus, once).
4. Windows display scale: a 1920×1080 laptop at 150% gives 1280×720. Set the scale to 100% or 125%, or use step 3.
5. Mirror the display; do not extend. The projector must show the same resolution as the laptop.
6. OS dark mode: no action needed; all three stay light (tested). Do not press `Dark` in the guide.
7. Offline: turn Wi-Fi off and reload once. All three load with no network (tested under `file://`).
8. Clicker: confirm it sends PageDown and PageUp, not arrow keys. Arrows move a focused slider.
9. Press `Reset demo` twice, or open `index.html?reset=1`, before the board enters. State survives a reload on purpose.
10. Close the presenter guide (`G`) before mirroring.
11. Walk all nine stops once with the clicker in the room. Watch stops 7 and 8.
12. From the back row, read the "Why on the list" column on stop 8 and the N1 marker.

## 10. Not checked, and why

| What | Why |
|---|---|
| A real double-click in Windows Chrome and Edge | Linux headless Chromium only. `file://` loading passed there |
| Segoe UI and Georgia fallbacks | The test box falls back to DejaVu |
| A real projector, room light, back-row legibility | No room |
| Item 51 frame budget | Headless software rendering and key steps, not a pointer drag. Numbers are indicative |
| Screen reader output (item 44) | No screen reader; DOM structure only |
| Item 36 (control outline contrast), the ring keyline width | Not measured |
| Dark theme contrast in A and B (6.4) | One screenshot taken, not examined |
| Item 40 as one unbroken keyboard-only run | Tab reachability checked per screen instead |
| 200% zoom and text-spacing overrides beyond one screen | 720×450 on `match` only: no horizontal scroll |
| Spacing of pseudo-elements; hover styles; card nesting depth | Outside the script |
| The builders' own 19 screenshots | Counted, not opened |
| The guided path at 390 | States at 390 scanned and five per mockup looked at; no live walk |
| `impeccable` detector | Its launcher writes project files; this audit is read-only. Its audit dimensions and the Web Interface Guidelines were applied by hand. No `transition: all`, no `will-change`, no `user-scalable=no`, no raw `innerHTML` of typed text, no raw hex outside `:root` |
