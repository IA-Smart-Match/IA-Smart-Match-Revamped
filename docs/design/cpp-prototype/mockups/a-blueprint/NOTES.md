# Direction A: Blueprint

**Open:** double-click `docs/design/cpp-prototype/mockups/a-blueprint/index.html` (works under `file://`, no server, no network).
**Status:** mockup for owner review. It is not app code. Nothing in `apps/` changed.
**Files:** `index.html` (1.1 kB, shell markup), `styles.css` (41 kB, tokens and layout), `app.js` (83 kB, behaviour), `NOTES.md`, `screenshots/` (19 PNG).
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

1. One column, 1200px, centred. Sticky top bar (logo, portal name, identity, N1, `Switch portal`), sticky 224px menu, one screen card.
2. Borders, never shadows, on cards. Shadow only on the guide panel and toast.
3. Cards nest one level. The bot transcript sits straight in its panel.
4. The hero of each screen is above the fold at 1440×900; chrome is kept to 88px to pay for it.
5. Tables are real tables from 640px, stacked rows below. Reasons and names wrap; nothing is cut.
6. Below 1024px the menu is a scrolling strip and N1 becomes its own sticky bar under the top bar.
7. With the guide open at 1400px and wider, the page gives the guide its own column, so it overlaps nothing.

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
| D1 | 5.6, 12.6 | The match table shows 5 full rows and part of a 6th at 1440×900, not 6 | An 18px table (5.3) in a 904px card (12.4) with 12/16 cell padding (5.6) cannot hold a reason on one line; rows are 2 lines, 81px. 5.2's "at least 5 rows, #4 on screen" holds. 1280×720 shows 3 rows |
| D2 | 8.3 `sm-rerank` | Rows leaving the visible 15 are removed at once; they do not fade out | A removed `<tr>` cannot fade without taking layout space or being cloned. Arrivals fade and wash as specified |
| D3 | 8.5 | `sm-wash` is a CSS opacity animation on a pseudo-element, not a GSAP tween | It never blocks or moves anything, and it removed per-frame style work from the drag (8.7 budget) |
| D4 | 8.3 `sm-rerank` | Flip runs with `simple: true` | Without it a re-rank cost 86–124ms per change under 4× CPU throttle |
| D5 | 4 | Screen descriptions run to about 95 characters per line | "Fits in 2 lines at 1440" and "45–70 characters" cannot both hold for the 173-character readiness description; 2 lines won |
| D6 | 9.1 | "Grace Delgado" on the profile card is an `h2`; its two group labels are `h3`. `recs` has a visually hidden `h2` "Events for me" (her menu label) | "Card names are h3" would skip a level on both screens |
| D7 | 7.16 | PageDown / PageUp also work while the event `<select>` has focus | A clicker must not die after the presenter picks an event. Text fields and sliders are excluded as specified |
| D8 | 2.11 | Her quotes had a 3px gold left border; here they sit in a quiet page-colour block | 5.4 bans side-stripe accents and gold borders on light |
| D9 | 7.5 | Doors are outlined in `--sm-line-strong`, not `--sm-line` | A door is a control; 5.4 asks 3:1 for control outlines |
| D10 | 7.6 | Industry toggle chips are 16px; reply option chips are 18px | 7.6 allows 16px; 13 toggles at 18px push `Done` below the fold |
| D11 | 12.4 | The top bar is sticky from 1024px; below that N1 is its own sticky bar | H1: the marker must be visible in every state, including after scrolling |
| D12 | 7.7 | Table boxes scroll inside themselves (max height: viewport minus the top bar) | Gives the sticky table header; the weights stay in view while the list scrolls |

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
| 13 | pass | No clipped box at 1440 or 390 in Chromium. The 390 select wraps with `field-sizing: content`; Firefox not checked |
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
| 29 | pass | Measured: interview `Done` at y=852, card at 757; recs rows end 717; readiness help buttons 798; overview chart row 851; match 5 full rows; talk row one 525; entry demo line 638 |
| 30 | pass | No horizontal scroll, stacked `ol` / `ul`, text 14px or more |
| 31 | pass | 1280×720: picker, 4 weights, Grace line (y=405), 3 full rows |
| 32 | pass | Fonts blocked: no overflow at 1440 or 390; match rows grow to 3 lines, weight labels wrap, nothing overlaps (headless fallback font, not Segoe UI) |
| 33 | pass | Token values as specified |
| 34 | pass | 58 pairs, minimum 5.17:1; body ink pairs 11.3:1 or more |
| 35 | pass | Ring mark has an ink keyline and tile 2's label. Note: future timeline dots are the "outlined gold dot" of 7.14, drawn with a 1px gold-ink outline and the tag "recorded later" |
| 36 | pass | Fields, chips, checkbox, step ring, slider track, doors use `--sm-line-strong` or green |
| 37 | pass | OS dark emulated: page stays light. `?theme=dark` and the control switch it |
| 38 | pass | Each 9.5 row has its second cue |
| 39 | pass | Tab order walked on entry, interview, recs, readiness, records, match, talk; every stop shows the ring |
| 40 | pass | Door, five answers, Register, slider, and all nine stops done by keyboard |
| 41 | pass | Nine stops in order; ignored in the search field and the slider; `G` toggles, types "g" in a field |
| 42 | pass | Focus on `H1` after each change; one `h1`, one `main`, one named `nav`, none on entry |
| 43 | pass | No `disabled` attribute. Send, `Back` and `Next` are `aria-disabled` with `aria-describedby`. "Registered" is `aria-disabled` with no described reason: its label is the reason |
| 44 | pass | Hidden `role="log"` holds only the newest turn's text; toast and messages are `role="status"`; no `role="alert"` |
| 45 | pass | All focusable targets 44×44 or more (checkbox counted with its label) |
| 46 | pass | Booked, sent, opens (×2), three partner outcomes, invitations: persistent `sm-message` |
| 47 | pass | No dialog |
| 48 | pass | Under reduced motion no element carried a transform during a portal change; the rest read from code, not each measured |
| 49 | pass | Read from code: screen change 380ms, portal 320ms, count and ring 400ms, bars 400ms. Not timed in the browser |
| 50 | pass | Two fast PageUp landed two stops back with no ghost left; `End` then `Home` on a weight re-targeted moving rows |
| 51 | **fail (borderline)** | Only transform, opacity and the ring's dashoffset animate. 4× throttle, drag 3→10, 6 runs after the fixes: no long task; 5 runs peaked at 33.3ms (two vsync ticks), 1 run had one 100ms frame. Headless software rendering; re-measure on the classroom laptop |
| 52 | pass | No scroll, timer or loop motion. Note: a status label and N2 fade with their screen during `sm-screen`; N1 and the logo never do |
| 53 | pass | Raw headless Chromium opened `file://…/index.html?s=match&iv=done`: 15 rows, Grace line, web fonts. Served run made 9 requests, all local files. Edge and a real double-click not checked |
| 54 | pass | 0 errors, 0 warnings on load and along the guided path |
| 55 | pass | `gsap.version` and `Flip.version` 3.15.0; `LICENSE.md` present; no `type="module"` |
| 56 | pass | 1.1 / 41 / 83 kB; folder holds the five required entries only |
| 57 | pass | This file |
| 58 | pass | 19 PNG, largest 214 kB |
| 59 | pass | Logo is `SMC.LOGO`, unaltered, on a white plate |
| 60 | pass | `p`, `s`, `iv`, `reg`, `help`, `w`, `ev`, `q`, `guide`, `theme`, `rm`, `reset` each exercised |

Tally: 59 pass, 1 fail (item 51, borderline), 0 not checked. Outside the numbered list: D1 (6 rows) is not met.

## 3 things to refine next

1. Decide D1 with the owner: 6 rows needs either a 16px table (B's floor) or the Grace line moved beside the event picker.
2. Run item 51 and the whole guided path on the real classroom laptop and projector, in Chrome and Edge, from a double-click.
3. Fade leaving rows in the re-rank (D2) with a fixed-layout clone, if the board lead wants the full `sm-rerank` spec.
