# Direction A: Blueprint

**Open:** double-click `docs/design/cpp-prototype/mockups/a-blueprint/index.html` (works under `file://`, no server, no network).
**Status:** mockup for owner review. It is not app code. Nothing in `apps/` changed.
**Files:** `index.html` (1.1 kB, shell markup), `styles.css` (44 kB, tokens and layout), `app.js` (86 kB, behaviour), `NOTES.md`, `screenshots/` (19 PNG, re-captured 2026-10-06 after the audit fixes).
**Reads, never copies:** `../../shared/data.js` (`window.SMC`), `../../shared/vendor/gsap/` (core + Flip 3.15.0), `../../shared/vendor/fonts/` (3 files, 109 kB).

## Concept

Ann's own design, drawn exactly. Her layout (top bar, 224px menu, one screen card), her palette, her three typefaces, her words. What changed is craft: type raised to projector sizes (18px body, 14px floor), every spacing value on the 4px scale, a green focus ring that can be seen, a ring target mark with a dark keyline, outcomes that stay on screen next to the button that caused them, the marker "Design for the next phase — made-up data" pinned on every screen, and five moments of motion that show cause and effect. She should recognise every screen as hers.

## Palette

Colour strategy: Ann's tokens, unchanged (DESIGN.md 6.2). Green does the work, gold highlights, blue only says "Partly built".

### Light (default, whatever the OS says)

All 17 shared tokens at Ann's values. Two constants this direction adds:

| Token | Hex | Use |
|---|---|---|
| `--sm-plate` | `#ffffff` | Logo plate and check-in code plate; the same in both themes |
| `--sm-code-ink` | `#10251b` | Check-in code cells; the same in both themes |

### Dark (opt-in: guide panel `Light` / `Dark`, or `?theme=dark`)

DESIGN.md 6.4 values. Added: `--sm-green-hover #86d3a9` (the spec gives no dark hover), `--sm-danger #ffb4ab` (reserved, unused), darker `--sm-elev-3`.

### Contrast (WCAG 2.x, computed)

Every text and background pair on screen was read from the browser (58 distinct pairs across all screens, both themes). The lowest is 5.17:1; all light pairs are rows of DESIGN.md 6.3. Pairs this direction adds:

| Pair | Ratio | Needs |
|---|---|---|
| dark: on-green `#07150e` on green-hover `#86d3a9` (primary button hover) | 10.60 | 7 |
| dark: green-hover on surface `#14211a` | 9.43 | 3 (non-text) |
| dark: danger `#ffb4ab` on surface (reserved) | 9.80 | 5 |
| code ink `#10251b` on plate `#ffffff` | 16.12 | 3 (non-text) |
| line-strong `#66796e` on page (door outline) | 4.23 | 3 (non-text) |
| dark: page `#0c1611` on ink `#e6efe9` (toast) | 15.71 | 7 |

Lowest pairs measured on screen: muted on green-soft 5.17 (labels in assistant turns), muted on gold-soft 5.54, muted on page 5.66, part on part-soft 5.68, dark muted on gold-soft 5.82, gold-ink on gold-soft 5.92.

## Type

| Family | Weights | Roles | File |
|---|---|---|---|
| Bricolage Grotesque | 700 (500 door eyebrows) | Titles, door titles, big figures, date tile, avatar | 41 kB |
| Public Sans | 400 / 600 | Everything else | 27 kB |
| JetBrains Mono | 500 | Status labels, IDs, ranks, match line, bar and weight values | 40 kB |

Sizes: entry title 64, screen title 28, portal name and door title 24, `h3` 20, body / table / chat 18, helper 16, labels and status 14 uppercase with 0.06em tracking, tile figure 36, ring and points figure 48. Fallback stacks per DESIGN.md 10.4; the layout was checked with the web fonts blocked.

## Layout principles

1. One column, 1200px, centred. Sticky top bar (logo, portal name, identity, N1, `Switch portal`), sticky 224px menu with the `Presenter guide` button docked under it, one screen card. Nothing floats over the screen.
2. Borders, never shadows, on cards. Shadow only on the guide panel and toast.
3. Cards nest one level. The bot transcript sits straight in its panel.
4. The hero of each screen is above the fold at 1440×900; chrome is kept to 88px to pay for it.
5. Tables are real tables from 640px, stacked rows below. Reasons and names wrap; nothing is cut.
6. Below 1024px the menu is a scrolling strip, N1 becomes its own sticky bar under the top bar, and the `Presenter guide` button sits in the top bar beside `Switch portal`. Below 640px the event picker is a radio list.
7. With the guide open at 1400px and wider, the page gives the guide its own column, so it overlaps nothing.
8. Short rooms (1024px and wider, 800px high or less, so 1280×720): tighter card padding, gaps and table rows, so each hero stays above the fold.

## Motion

| # | Moment | Maps to (DESIGN.md 8.3) | How |
|---|---|---|---|
| 1 | A door opens into its portal | `sm-portal` | Flip carries the door's title to the portal name (280ms, `power2.inOut`); the old screen leaves as a ghost (160ms); menu and screen enter (220ms). Reverse on `Switch portal` |
| 2 | The profile card fills | `sm-card-fill`, `sm-turn` | Toggling an industry adds or removes its pill in the same beat; "Not yet" cross-fades to the goal after turn 3 |
| 3 | The list re-ranks | `sm-rerank`, `sm-wash` | Flip on the 15 `<tr>` nodes, `overwrite: true`, re-ordered not rebuilt; arrivals fade in and carry a 900ms gold wash; Grace's row keeps its tint |
| 4 | Readiness moves a little | `sm-ring-draw`, `sm-count` | Arc tweens by `stroke-dashoffset` (400ms); 13% counts to 17% in the ring and tile; points count; the marker's dot fills |
| 5 | Register | `sm-register` | Button turns gold with a check; check-in card rises in; the page scrolls it into view (400ms) |

Shared feedback: `sm-press`, `sm-lift`, `sm-screen`, `sm-panel` (Flip on the markers below), `sm-guide`, `sm-toast`, `sm-confirm`, `sm-bars-grow`. Any pointer or key press completes running tweens first (`fx.finishAll`). `prefers-reduced-motion`, `?rm=1` or `data-motion="reduced"`: opacity only, 150ms, figures final at once.

## Review deep links

Append to `index.html`:

| Link | Shows |
|---|---|
| `?reset=1` | Fresh entry |
| `?reset=1&s=interview` | Interview, turn 1 |
| `?iv=done&s=recs` | Events after the guided interview |
| `?iv=done&reg=E11&s=readiness&help=chat` | Readiness with the bot panel |
| `?iv=done&s=records&q=Delgado` | Records search |
| `?iv=done&s=match` | Match, Grace #4 |
| `?iv=done&s=match&w=10,3,2,2` | Match, Same major 10, Grace #27 |
| `?iv=done&s=match&ev=U3` | Audit Season, Grace not in the top 30 |
| `?s=match&w=0,0,0,0` | Empty state N7 |
| `?p=partner` | Partner portal |
| `?s=match&guide=1` | Guide open |
| `&theme=dark`, `&rm=1` | Dark theme, reduced motion |

## Deviations from DESIGN.md

| # | Section | What | Why |
|---|---|---|---|
| D1 | 5.6, 12.6 | The match table shows 5 full rows and most of a 6th at 1440×900, not 6; 4 full rows at 1280×720 | Audit resolution D-01: "Grace's row #4 whole and at least 5 full rows at 1440×900; at least 4 at 1280×720". Rows are 2 lines: 81px, and 73px in a short room |
| D2 | 8.3 `sm-rerank` | Rows leaving the visible 15 are removed at once; they do not fade out | A removed `<tr>` cannot fade without taking layout space or being cloned. Arrivals fade and wash as specified |
| D3 | 8.5 | `sm-wash` is a CSS opacity animation on a pseudo-element, not a GSAP tween | It never blocks or moves anything, and it removed per-frame style work from the drag (8.7 budget) |
| D4 | 8.3 `sm-rerank` | Flip runs with `simple: true` | Without it a re-rank cost 86–124ms per change under 4× CPU throttle |
| D5 | 4 | Screen descriptions run to about 95 characters per line | "Fits in 2 lines at 1440" and "45–70 characters" cannot both hold for the 173-character readiness description; 2 lines won |
| D6 | 9.1 | "Grace Delgado" on the profile card is an `h2`; its two group labels are `h3`. `recs` has a visually hidden `h2` "Events for me" (her menu label) | "Card names are h3" would skip a level on both screens |
| D7 | 7.8, 7.16 | PageDown / PageUp change stop from every control except a text input or textarea, sliders included. Enter in the records search releases focus | Audit resolution D-08: the clicker must not stall after the scripted slider move. Sliders keep arrows, Home and End |
| D8 | 2.11 | Her quotes had a 3px gold left border; here they sit in a quiet page-colour block | 5.4 bans side-stripe accents and gold borders on light |
| D9 | 7.5 | Doors are outlined in `--sm-line-strong`, not `--sm-line` | A door is a control; 5.4 asks 3:1 for control outlines |
| D10 | 7.6 | Industry toggle chips are 16px; reply option chips are 18px | 7.6 allows 16px; 13 toggles at 18px push `Done` below the fold |
| D11 | 12.4 | The top bar is sticky from 1024px; below that N1 is its own sticky bar | H1: the marker must be visible in every state, including after scrolling |
| D12 | 7.7 | Table boxes scroll inside themselves (max height: viewport minus the top bar) | Gives the sticky table header; the weights stay in view while the list scrolls |
| D13 | 7.16, 9.2 | The `Presenter guide` button is docked, not fixed bottom right: under the menu from 1024px, in the top bar below that and on the entry. Tab order: skip link, `Switch portal`, menu, guide button, main | Audit A-04 and A-18: the floating button covered content. The 224px menu column has the room; the top bar at 1280 does not (the identity line would wrap) |
| D14 | 12.6 | On `match` the Grace line sits on the picker's row (right of the select) from 1200px, not between the weights and the table | Audit A-05: it starts the table 40px higher, which is what puts row #4 on screen at 1280×720 |
| D15 | 5.6 | The match table's cells have 12px inline padding (first and last column 4px on the right), not 16 | Audit A-10: it pays for a 170px name column, so names hold on one line while every Northline reason still holds in two |
| D16 | 7.8 | A weight's value sits past the right end of its track, not beside the label | Audit A-11 and A-12: clear of the next control's label (32px) and of the thumb's focus ring at 10 (7px) |
| D17 | 7.9 | The event picker is a radio list below 640px | Audit resolution D-10 |
| D18 | 7.12 | The check-in card's "Planned" label sits on the "Check-in code" label's row; the code is 116px | Audit A-09: the card is short enough to appear after `Register` with a 7px scroll at 1440×900 |
| D19 | 7.16 | In the guide panel the stop controls sit below the `Say:` line | Audit X-10: the same place as B and C |

`impeccable detect` was not run (no `.impeccable/` files are written for this folder by instruction).

## Audit self-check (DESIGN.md section 11)

Checked in headless Chromium (playwright-cli) on 2026-10-06, served on `127.0.0.1:8771`, plus one raw headless run from `file://`.

| # | Result | Note |
|---|---|---|
| 1 | pass | N1 in viewport on 9 screens × 1440 and 390 × guide open and closed; also after scrolling 900px at 1440, 800 and 390 |
| 2 | pass | 8 status labels at y=145 at 1440×900; check-in card shows "Planned" |
| 3 | pass | N2 sits outside both scrolling logs |
| 4 | pass | No typing dots or streamed text in code; turns append whole |
| 5 | pass | Demo line on entry |
| 6 | pass | Label and closing line present |
| 7 | pass | All names come from `SMC`; no `input[type=file]` |
| 8 | pass | Every UI string literal in `app.js` was matched against DESIGN.md text; the six guided-path event rows matched in the browser. Not diffed character by character against Ann's HTML |
| 9 | pass | Turns 1–5, 4a and 4b walked in the browser |
| 10 | pass | 5 rules asked; rules 2, 4, 5 show the booking button |
| 11 | pass | Nine entries are literals matched against 2.12; `→` drawn as an icon |
| 12 | pass | Only hidden helper strings named in section 7: "Grace:", "done", "not yet", "Grace Delgado, the student from the demo", the ring's name. W1–W5 not applied |
| 13 | pass | No clipped box at 1440 or 390 in Chromium. A finished interview opens at the top of a turn (A-08 fixed). At 390 the picker is a radio list; Firefox not checked |
| 14 | pass | Classic script tag; `git status` shows `shared/` unchanged; no student rows in this folder |
| 15 | pass | 9 of 9 rows `pass: true` |
| 16 | pass | P108, P224, P028, P046, P286, P004, P178, P131; line reads "#4 … because of her interview answers." |
| 17 | pass | P108, P224, P028, P286, P220, P124, P168, P208; 15 of 15 visible rows are Computer Information Systems; line reads "#27" |
| 18 | pass | Line and the three "Before interview" rows match |
| 19 | pass | match 6, 4, 3 of 10 with the listed reasons |
| 20 | pass | 4% fresh, 13% after interview, 17% with LinkedIn ticked, target 60% |
| 21 | pass | 20 fresh, 40 after interview, 50 after one registration, 55 after one self-check; same on readiness and growth; recs shows it in the check-in card (30 fresh + one registration, 50 after interview + one) |
| 22 | pass | 300 / 100 / 70 / 200 fresh, 71 after the interview; four charts match 2.8 |
| 23 | pass | 25 rows, "300 of 300 records"; `Delgado` gives 14; Grace reads "Not yet" before, "AI interview · today" after |
| 24 | pass | "Graduate school" leads to turn 4b; card shows "Graduate school" |
| 25 | pass | Reload kept screen, interview and registration; two presses of `Reset demo` cleared them |
| 26 | pass | Computed margin, padding and gap on every element in 42 states: all on the scale |
| 27 | pass | Computed font sizes all on the scale, none under 14px. Toggle chips and the match line are 16px (7.6, 7.14) |
| 28 | pass | Radii are tokens; no element has both border and shadow; nesting is one level |
| 29 | pass | Re-measured after the fixes: interview reply area ends y=868, card 757; recs rows end 681; readiness help buttons 798; overview chart row 851; match 5 full rows (Grace's row 666 to 747); talk row one 525; entry demo line 638 |
| 30 | pass | No horizontal scroll, stacked `ol` / `ul`, text 14px or more |
| 31 | pass | 1280×720: picker, 4 weights, Grace line (ends y=281), 4 full rows, Grace's row whole (614 to 687). Was 3 rows with row #4 cut |
| 32 | pass with a note | Re-checked after the fixes, fonts blocked (DejaVu fallback, wider than Segoe UI): no horizontal scroll at 1440, 1280 or 390, nothing overlaps; match rows grow to 3 lines (4 full rows at 1440, 2 at 1280) and the last table head "What we know" is cut by 8px at the box edge |
| 33 | pass | Token values as specified |
| 34 | pass | 58 pairs, minimum 5.17:1; body ink pairs 11.3:1 or more |
| 35 | pass | Ring mark has an ink keyline and tile 2's label. Note: future timeline dots are the "outlined gold dot" of 7.14, drawn with a 1px gold-ink outline and the tag "recorded later" |
| 36 | pass | Fields, chips, checkbox, step ring, slider track, doors use `--sm-line-strong` or green |
| 37 | pass | OS dark emulated: page stays light. `?theme=dark` and the control switch it |
| 38 | pass | Each 9.5 row has its second cue |
| 39 | pass | Tab order walked on entry, interview, recs, readiness, records, match, talk; every stop shows the ring. Since the fixes the guide button comes after the menu, before main (D13) |
| 40 | pass | Door, five answers, Register, slider, and all nine stops done by keyboard |
| 41 | pass | Nine stops in order at 1440 and 1280, forward and back. Page keys now change stop from the slider, the select and the radios; ignored only in a text input or textarea (D-08). `G` toggles, types "g" in a field |
| 42 | pass | Focus on `H1` after each change, with no ring (D-09); one `h1`, one `main`, one named `nav`, none on entry |
| 43 | pass | No `disabled` attribute. Send, `Back` and `Next` are `aria-disabled` with `aria-describedby`. "Registered" is `aria-disabled` with no described reason: its label is the reason |
| 44 | pass | Hidden `role="log"` holds only the newest turn's text; toast and messages are `role="status"`; no `role="alert"` |
| 45 | pass | All focusable targets 44×44 or more (checkbox and radio counted with their labels). The skip link is now 187×44 at 390 (was 186×40, A-17) |
| 46 | pass | Booked, sent, opens (×2), three partner outcomes, invitations: persistent `sm-message` |
| 47 | pass | No dialog |
| 48 | pass | Under reduced motion no element carried a transform during a portal change; the rest read from code, not each measured |
| 49 | pass | Read from code: screen change 380ms, portal 320ms, count and ring 400ms, bars 400ms. Not timed in the browser |
| 50 | pass | Two fast PageUp landed two stops back with no ghost left; `End` then `Home` on a weight re-targeted moving rows |
| 51 | **fail (borderline)** | Not re-measured after the audit fixes (no animation code changed). Only transform, opacity and the ring's dashoffset animate. 4× throttle, drag 3→10, 6 runs after the fixes: no long task; 5 runs peaked at 33.3ms (two vsync ticks), 1 run had one 100ms frame. Headless software rendering; re-measure on the classroom laptop |
| 52 | pass | No scroll, timer or loop motion. Note: a status label and N2 fade with their screen during `sm-screen`; N1 and the logo never do |
| 53 | pass | Raw headless Chromium opened `file://…/index.html?s=match&iv=done`: 15 rows, Grace line, web fonts. Served run made 9 requests, all local files. Edge and a real double-click not checked |
| 54 | pass | 0 errors, 0 warnings on load and along the guided path |
| 55 | pass | `gsap.version` and `Flip.version` 3.15.0; `LICENSE.md` present; no `type="module"` |
| 56 | pass | 1.1 / 44.3 / 86.4 kB (budget 40 / 70 / 90); folder holds the five required entries only |
| 57 | pass | This file |
| 58 | pass | 19 PNG, same names, re-captured after the fixes, each one looked at; largest 211 kB |
| 59 | pass | Logo is `SMC.LOGO`, unaltered, on a white plate |
| 60 | pass | `p`, `s`, `iv`, `reg`, `help`, `w`, `ev`, `q`, `guide`, `theme`, `rm`, `reset` each exercised |

Tally: 59 pass, 1 fail (item 51, borderline), 0 not checked. Rows 13, 29, 31, 32, 39, 41, 42, 45, 51, 56 and 58 were corrected on 2026-10-06 after the independent audit; the audit had marked 45 as a fail (skip link), now fixed.

## Audit fixes (2026-10-06)

Source: `../../audit/AUDIT.md`. Every row was re-run in headless Chromium (playwright-cli, `--browser=chromium`), served on `127.0.0.1:8791`, cache off, by reproducing the auditor's failing condition. After the fixes: `SMC.selfTest()` 9 of 9; Northline top 8 `P108 P224 P028 P046 P286 P004 P178 P131` (Grace #4); Same major 10 gives `P108 P224 P028 P286 P220 P124 P168 P208`, 15 of 15 CIS, "#27"; N1 and the status label in view on 9 screens × 1440, 1280 and 390, guide open and closed; 0 console errors; 0 requests to another host; `file://` opens with data and fonts; no transform under reduced motion during a portal change.

| ID | Sev | Result | What changed | How verified (measured) |
|---|---|---|---|---|
| A-01 | HIGH | fixed | Page keys change stop from any control except a text input or textarea; Enter in the records search blurs it | Mouse-dragged "Same major" to 10 (focus on the range), PageDown: title "Your talk: Northline Analytics", weight still 10 (was: same title, weight 9). PageUp returns. Arrows, Home, End still move the weight. In search: PageDown while typing stays; Enter moves focus to `body`; PageDown then goes to stop 8 |
| A-02 | HIGH | fixed | `h1[tabindex="-1"]` never draws an outline | After PageDown the title has focus, matches `:focus-visible`, computed `outline-style: none`, on all 8 portal titles at 1440 and 1280 |
| A-03 | HIGH | fixed | Opening a help panel scrolls it into view (focus no longer scrolls); after a bot question the panel is kept in view | 1440×900: N2 at y=440 to 476, on top, panel 379 to 888 (was N2 at 908, scroll 0). 1280×720: N2 at 268 to 304. After "How do I get my resume reviewed?": N2 at 268, answer turn whole. `Ask the assistant bot` from the page bottom: panel top at 104, focus in the field |
| A-04 | HIGH | fixed | Guide button docked: under the menu from 1024px, in the top bar below that and on the entry (D13) | `position: relative`; its box intersects `main` on 0 of 6 screens at 1280×720, 1440×900 and 390×844; no horizontal scroll |
| A-05 | HIGH | fixed | Grace line on the picker's row (D14); short-room rule: 8px cell block padding, 8px gaps | 1280×720: 4 full rows (73px), Grace's row #4 at y=614 to 687, whole. 1440×900: 5 full rows (81px), Grace's row 666 to 747. Was 3 rows with row #4 cut at 1280 |
| A-06 | HIGH | fixed | The transcript grows to hold the newest turn (`--need`); the page scrolls if it must | 1280×720, all five turns: newest assistant turn inside the log and the viewport (`whole: true`). Turn 1: reply area ends y=685, card 693. Turn 2: `Done` ends 709. Was a 177px and 131px log with the question cut |
| A-07 | MEDIUM | fixed | Clicks inside `main` are ignored for 350ms after an interview answer | Double-click on each answer: picks stay `[Technology, Entertainment]`; "Not sure yet" leaves goal "Undecided" at turn 4; "Yes, help me compare" stays on the interview at turn 5; "Show my events" lands on Events with nothing registered. A click 600ms later registers |
| A-08 | MEDIUM | fixed | The log is re-fitted when the web fonts land and on resize (cause inferred: fitted before the font swap) | Deep link and PageUp from stop 3, 1440 and 1280: 0 turns cut at the log's top or bottom edge |
| A-09 | MEDIUM | fixed | Check-in card shorter (D18), reason chip padding 4 / 12, scroll margin 12px, the pressed button is kept below the top bar | 1440×900 after the interview: scroll 7px (was 163); title y=106, status label 110, pressed button 241, card ends 880. 1280×720: scroll 116, pressed button at y=116, event title 90; the screen title is off screen there |
| A-10 | MEDIUM | fixed in part | Match columns 38 / 170 / 206 / rest / 140 with 12px inline padding (D15); records: name and profile-card cells `nowrap` | Match, Northline default: 0 names wrap, 0 rows over 2 lines. Left: "Profile card (AI interview)" wraps in Grace's row only. A `nowrap` there needs 242px and pushes Northline reasons to 3 lines (measured), which would undo A-05. Names that wrap, over 5 events × 7 weight sets (525 rows): 3 (was 486). Rows over 2 lines on the same sample: 63, the same as before the fix; none on Northline |
| A-11 | MEDIUM | fixed | Weights gap 32px; the value sits at the track's end (D16) | Value to the next label: 32px on all three gaps (was 14 to 16) |
| A-12 | MEDIUM | fixed | As A-11 | At 10 with keyboard focus: ring ends x=566, value starts x=573; no overlap |
| A-13 | MEDIUM | left (improved) | Short-room rule tightens padding and gaps | 1280×720 now: readiness help buttons end 774 (was 798; the bot button's group ends 688, in view), overview chart row 827 (was 851), third event before the interview 715 (was 783, now in view). Readiness group 2 and the chart row still need the auditor's room fix: 90% zoom or a window 800px high |
| A-14 | LOW | closed by D-08 | Page keys no longer act inside a slider | See A-01 |
| A-15 | LOW | left | Toast stays 4 seconds (the same in all three, section 7.11) | After `Register` at 1440×900 it covers the check-in card's helper line for 4 seconds |
| A-16 | LOW | fixed | `main` bottom padding 64 to 24 (no floating button to clear) | Entry at 1280×720: `scrollHeight` 720, no scroll (was 744) |
| A-17 | LOW | fixed | Skip link `min-height: 44px` | 187×44 at 390 |
| A-18 | LOW | fixed | As A-04 | 390: button in the top bar beside `Switch portal`; over `main` on 0 of 6 screens. With the guide open the panel stops at least 8px under N1 (checked on 9 screens) |

Cross-mockup and DESIGN.md resolutions:

| ID | Result | Note |
|---|---|---|
| X-01, X-02, D-08 | applied | A-01 |
| X-03, D-09 | applied | A-02 |
| X-06 | applied | The pressed `Register` button stays on screen at 1440×900 and 1280×720 |
| X-08 | applied | N1 is 16px (15px at 390, the small-screen step of the 16px token) |
| X-09 | left | The status label stays 14px mono uppercase: sections 5.3 and 12.6 specify it and the audit only "allows" sentence case. One rule to change (`.sm-status`) if the owner wants it |
| X-10 | applied | Stop controls below the `Say:` line (D19) |
| X-14 | applied | A-03 |
| D-01 | applied | A-05; D1 above |
| D-02, D-03, D-04, D-05, D-06, D-07, D-11, D-12, D-14 | no change needed | A already did what each resolution says |
| D-10 | applied | Radio list below 640px (D17). From 1200px the select is 600px wide and holds the longest option on one line (44px high for all five) |
| D-13 | n/a | B only |

Not verified: Windows Chrome and Edge, a real double-click, a real clicker, the projector; item 51 was not re-measured; the dark theme was only opened once after the fixes (it renders, not examined).

## 3 things to refine next

1. Rehearse at the room's real window size. At 1280×720 `readiness` and `overview` still keep part of their hero below the fold (A-13); 90% browser zoom or a window 800px high fixes both.
2. Run item 51 and the whole guided path on the real classroom laptop and projector, in Chrome and Edge, from a double-click.
3. Fade leaving rows in the re-rank (D2) with a fixed-layout clone, if the board lead wants the full `sm-rerank` spec.
