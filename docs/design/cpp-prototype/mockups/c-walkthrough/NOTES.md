# Direction C: Walkthrough

**Open:** double-click `docs/design/cpp-prototype/mockups/c-walkthrough/index.html`. No server, no install, no network.
**Status:** mockup for owner review. It is not app code. Nothing in `apps/` changed.
**Files:** `index.html` (shell, 1.4 kB), `styles.css` (tokens and layout, 44 kB), `app.js` (copy, state, components, screens, motion; 81 kB), `screenshots/` (19 PNGs).
**Reads, never copies:** `../../shared/data.js` (`window.SMC`), `../../shared/vendor/gsap/` (core + Flip, 3.15.0), `../../shared/vendor/fonts/` (2 files).
**Contract:** [`../../DESIGN.md`](../../DESIGN.md), Part 1 and section 14.

## Concept

Built for the fifteen minutes. The nine stops are the navigation: a green rail along the bottom says "Stop n of 9" and who is presenting, `Back` and `Next` (or a clicker's PageDown and PageUp) walk Ann's order, and each stop opens on one large idea before anything else is asked of the eye. Sentences the presenters read aloud are set in a serif on warm paper; controls and tables are in a plain sans. Every word, number and screen is Ann's; only the first screenful is rearranged around the one point that stop makes.

## Palette

Light only. Brand and status colours are the shared ones (DESIGN.md 6.2); neutrals are section 14.3's.

| Token | Hex | Use |
|---|---|---|
| `--sm-page` | `#f8f6f1` | Paper: page, top bar |
| `--sm-surface` | `#ffffff` | Cards, fields, table body, logo plate |
| `--c-sunk` | `#f2eee8` | Table head, "recorded later" tag, data-handling block |
| `--sm-ink` | `#163229` | Text |
| `--sm-muted` | `#59665f` | Secondary text, labels |
| `--sm-line` | `#d9cbc4` | Decorative dividers only |
| `--sm-line-strong` | `#8f7a70` | Control outlines, slider track edge, empty step ring |
| `--sm-green` / `--c-stage` | `#005030` | Primary action, bars, figures; the entry stage and the stop rail |
| `--sm-green-hover` | `#003d24` | Primary hover; rail tab hover; rail top rule |
| `--sm-green-soft` | `#e1ede6` | Assistant turns, date tile, bar track, working label, outcome message |
| `--c-on-stage-soft` | `#cfe3d8` | Secondary text and button outline on green |
| `--sm-gold` | `#fdb71e` | Rail numerals and current-stop bar; Registered; avatar; target tick; third dot; gold bars |
| `--sm-gold-soft` | `#fff1cc` | Grace's row, N1, N2, callout, "Why you", planned label |
| `--sm-gold-ink` | `#7a5600` | Gold-coded text; outline of gold bars and dots |
| `--sm-part` / `--sm-part-soft` | `#2e5f8a` / `#e3edf7` | "Partly built" only |

Dark: not shipped (DESIGN.md 14.3). `?theme=dark` is accepted and ignored; there is no theme control.

Contrast, computed with the WCAG 2.x formula from the tokens on 2026-10-06:

| Pair | Where | Ratio | Need |
|---|---|---|---|
| ink on page / surface / sunk | body, cards, data-handling block | 12.77 / 13.79 / 11.94 | 7 |
| ink on gold-soft / green-soft | N1, callout, Grace's row / assistant turn, message | 12.29 / 11.47 | 7 |
| ink on gold `#fdb71e` | not used (on-gold is) | 7.86 | — |
| muted on page / surface / sunk | notes, labels / meta lines / table head, "recorded later" | 5.57 / 6.02 / 5.21 | 5 |
| muted on gold-soft / green-soft | — / speaker label, date-tile month | 5.36 / 5.00 | 5 |
| green on page / surface / sunk | figures, links, secondary buttons | 8.88 / 9.59 / 8.30 | 7 |
| green on green-soft / gold-soft | working label, pills / — | 7.97 / 8.54 | 5 |
| white on green / green-hover | buttons, student turn, funnel, rail / hover | 9.59 / 12.40 | 7 |
| on-stage-soft `#cfe3d8` on green / green-hover | lede, demo line, rail tabs / hovered tab | 7.14 / 9.23 | 5 |
| gold on green / green-hover | rail numerals, current-stop bar, focus ring on green | 5.46 / 7.07 | 4.5 |
| page on ink | toast | 12.77 | 7 |
| on-gold `#1d1503` on gold | Registered, avatar | 10.31 | 7 |
| gold-ink on gold-soft / surface / page | planned label, N2, "Why you:" / pill in Grace's row / — | 5.92 / 6.65 / 6.16 | 5 |
| part on part-soft | partly-built label | 5.68 | 5 |
| line-strong on page / surface / sunk | control outlines (non-text) | 3.75 / 4.05 / 3.50 | 3 |
| line-strong on gold-soft / green-soft | slider track edge beside the fill (non-text) | 3.61 / 3.37 | 3 |
| gold-ink on green-soft | outline of gold bars against the track (non-text) | 5.53 | 3 |
| gold-ink on gold | outline of the gold dot and bar (non-text) | 3.79 | 3 |
| green-hover on green | rail top rule | 1.29 | decorative |

Ratios come from the token values, not from pixels sampled off the screen.

## Type

| Role | Family | Size / line (1440) | Weight |
|---|---|---|---|
| Entry title | Source Serif 4 | 80 / 84 | 600 |
| Screen title | Source Serif 4 | 48 / 54 | 600 |
| Description, feature "Why you", funnel note | Source Serif 4 | 24 / 32 | 400 |
| Tile figures; ring figure; Grace's rank | Source Serif 4 | 48 / 54; 64 / 68; 80 / 84 | 600 |
| Door title, feature event title | Source Serif 4 | 36 / 44 | 600 |
| `h3`, card names, quotes | Source Serif 4 | 24 / 32 (quotes 28 / 36) | 600 / 400 |
| Body, chat turns | Figtree | 20 / 30 | 400 |
| Tables, buttons, chips, fields, bars | Figtree | 18 / 28 | 400–600 |
| Labels, helper lines, status, N1, N2, pills | Figtree | 16 / 24 | 600 (helper 400) |
| Speaker label, presenter name, guide eyebrow | Figtree | 14 / 20 | 600 |

- Fallbacks: `Georgia, "Times New Roman", serif` and `"Segoe UI", system-ui, -apple-system, "Helvetica Neue", Arial, sans-serif`.
- File cost: 2 files, 71 kB (`source-serif-4-latin-wght-normal.woff2` 50.8 kB, `figtree-latin-wght-normal.woff2` 20.2 kB). No italic is used, so neither italic file loads.
- `font-variant-numeric: tabular-nums` on the body, so every figure holds its width while it counts.
- At 390 the scale switches to DESIGN.md 5.3's small column through the same tokens.

## Layout principles

1. **The rail is the map.** `Back`, the portal's own menu as tabs, the presenter's name, "Stop n of 9", `Next`, and the guide button docked at the right end. It is solid brand green; gold marks only the numerals and the current tab.
2. **One hero per stop.** At 1440×900 the first screenful holds what section 5.2 lists for that screen; the rest of Ann's content follows by ordinary scrolling. Nothing is behind a tab or a disclosure.
3. **Paper, white cards, shadow only.** Cards carry `--sm-elev-1` and no border; controls carry a `--sm-line-strong` outline and no shadow.
4. **N1 lives in the top bar**, which is sticky, so it is on screen in every state, scrolled or not, guide open or closed.
5. **Match is a control band over a full-width table** (see Deviations 1): picker and Grace's rank on one row, the four weights on the next, then the list.
6. **The guide never covers the hero.** At 1200 and wider, opening it gives the stage a narrower column instead of laying the panel over it.
7. **Below 1200** the tabs leave the rail and become a strip under the top bar; **at 390** tables become stacked rows, the event picker becomes a radio group, and the rail keeps `Back`, the stop count and `Next`.

## Motion

Tokens are DESIGN.md 8.2's, as CSS custom properties and as `SM_MOTION` in `app.js`. One `gsap.matchMedia()` block sets the reduced-motion switch (`?rm=1` and `data-motion="reduced"` force it).

| 14.5 moment | Shipped | How it maps to section 8 |
|---|---|---|
| 1. Stop to stop | Yes | `sm-portal`: outgoing content opacity → 0, x → −24 (`fast`, `in`); incoming x 24 → 0 with opacity (`move`, `out`) from 100ms; 380ms in all. `Back` mirrors it. The rail's gold bar glides with `Flip` (`move`, `inOut`). Focus is on the new `h1` at once |
| 2. The doors arrive | Yes | Once per page load: y 16 → 0 with opacity, 30ms apart (`base`, `out`) |
| 3. An answer is filed on the card | Yes | On `Done` each chosen industry, and after turn 3 the chosen goal, travels from the reply area to its row on the profile card and settles (`move`, `inOut`); a pill toggled on runs `sm-card-fill` (scale 0.9 → 1). First-last-invert-play done by hand with GSAP on a fixed clone |
| 4. Why you | Yes | On arriving at `recs` after the interview the three reasons enter 30ms apart (`base`, `out`); `Register` runs `sm-register` |
| 5. Grace at #4 | Yes | A `text-80` numeral beside the Grace line runs `sm-count` while the rows run `sm-rerank` with `Flip` (`overwrite: true`, so a new change re-targets rows in flight). When she leaves the top 30 the numeral goes and the sentence stands alone |

Also shipped: `sm-turn`, `sm-count` (points, readiness %, profile-card count), `sm-ring-draw`, `sm-bars-grow`, `sm-wash` (on rows that enter the visible 15), `sm-panel` (enter), `sm-guide`, `sm-toast`, `sm-confirm`, `sm-press`, `sm-lift`.

Cut or simplified: see Deviations 4 and 12.

Interruptibility: every tween that could sit between the presenter and the next action is registered; any `pointerdown` or `keydown` completes them all, then the action runs. A second PageDown during a scene change lands on the following stop.

## Review deep links

All of DESIGN.md 3.7 work (append to `index.html`):

```text
?reset=1                                   fresh entry
?reset=1&s=recs                            Events for me, before the interview
?reset=1&s=interview&iv=done               interview finished, card filled
?reset=1&s=recs&iv=done&reg=E11            registered, check-in card
?reset=1&s=readiness&iv=done&help=chat     readiness with the bot panel (help=msg|book|res)
?reset=1&s=match&iv=done                   TV-A: Grace at #4
?reset=1&s=match&iv=done&w=10,3,2,2        TV-B: Grace at #27
?reset=1&s=match&iv=done&ev=U3             TV-D: not in the top 30
?reset=1&s=match&w=0,0,0,0                 empty state N7
?reset=1&s=records&q=Delgado&iv=done       14 of 300 records
?reset=1&p=hub      ?reset=1&p=partner     a portal's default screen
&guide=1   &rm=1   &theme=dark (ignored)
```

## Deviations from DESIGN.md

1. **Match layout (14.6).** 14.6 asks for controls in the left third and the table in the right two thirds. With 18px table text and 16px cell padding (5.6), a two-thirds table leaves about 290px for "Why on the list", which wraps Grace's reason to three lines and breaks both "a reason fits in 2 lines" (section 4) and "at least 5 ranked rows" (5.2). Built instead as a control band over a full-width table. Measured: 5 whole rows at 1440×900, 3 at 1280×720.
2. **Event picker (7.9 against 14.6).** 7.9 says C uses a row of five radio cards; 14.6 allows "a native select if the cards push the weights below the fold". They do, so it is a native `<select>`, 620px wide so no option is cut. At 390 a select would clip the option text, so it becomes a radio group of five wrapping options.
3. **Rank numeral on short screens.** Under 800px of viewport height the numeral drops from `text-80` to `text-48` so audit item 31 holds.
4. **Re-rank exits.** Rows leaving the visible 15 are removed at once, not faded: a fading table row would need absolute positioning, which breaks the table. Rows entering fade in and get the wash.
5. **Moment 3 uses GSAP, not the Flip plugin.** Same first-last-invert-play, on a fixed clone, because the reply area is re-rendered between "first" and "last". Flip is used for the rows and the rail bar.
6. **No focus ring on the `h1`.** 9.2 moves focus to the new `h1` "with no visible ring unless reached by keyboard". A clicker's PageDown counts as keyboard, so a ring would box every title on the projector. The `h1` has `tabindex="-1"` and cannot be reached by Tab; its outline is removed. Every control keeps its ring.
7. **Description measure.** "Prose 45–70 characters per line" and "a screen description fits in 2 lines at 1440" (section 4) cannot both hold for the 170-character readiness description at `text-24`. The two-line rule wins; descriptions run to about 100 characters per line.
8. **Tab order and the rail.** DOM order is skip link → `Switch portal` → rail (`Back`, tabs, `Next`) → main → guide button → guide panel, which is 9.2's order. The rail is drawn at the bottom, so its controls come before the content in Tab order although they sit below it.
9. **Guide open at 1200 and wider** narrows the stage column instead of overlapping it (7.16 only forbids covering the hero). The hero reflows; `match` then shows 3 rows.
10. **Toast.** It leaves when the stop changes, so it never sits over the next stop's hero. After `Register` the scroll leaves room for it, and the page has 96px of bottom padding so that scroll is possible.
11. **Sticky table head** pins under the top bar while the page scrolls; there is no inner scrolling table box at 1200 and wider. Below 1200 the box scrolls sideways if it must and is then focusable and named.
12. **Simplified motion:** `sm-register`'s check "draws in" as a short fade; a closing help panel is removed at once; the guide closes with opacity only.
13. **Heading order.** `recs` has a visually hidden `h2` "Events for me" (her menu label) so event titles can be `h3` without skipping a level. The profile card name and "Check-in code" are `h2`.
14. **Outlined gold dot (7.14 against 6.1).** Future terms use a 3px gold ring with a 1px `--sm-gold-ink` keyline and the tag "recorded later", so gold is not alone on white.
15. **Page keys in the native select** are left to the select, as in a slider. `G` is ignored there too.
16. **Disabled reasons with no string.** `Next` on stop 9 and the guide's `Back` on stop 1 are described by the "Stop n of 9" text; `Registered` by the check-in card's title. No new string was added.
17. **One file over the house size habit.** `app.js` is 1,134 lines because 10.1 fixes the folder to one script.

No `impeccable detect` run was made (its launcher writes outside this folder); the skill's craft floor was applied by hand.

## Audit self-check (DESIGN.md section 11)

Checked on 2026-10-06 in headless Chromium (playwright-cli) over `http://127.0.0.1:8773`, at 1440×900, 1280×720 and 390×844. P = pass, F = fail, N = not checked.

| # | Result | Note |
|---|---|---|
| 1 | P | Script: N1 inside the viewport, unclipped and on top, on 9 screens × 2 widths × guide open and closed, after scrolling |
| 2 | P | 8 status labels end 122–138px from the top at 1440×900; strings from 2.1; check-in card shows "Planned" |
| 3 | P | N2 sits above the scrolling log in both transcripts |
| 4 | P | No such state exists in the code; turns arrive whole |
| 5 | P | |
| 6 | P | |
| 7 | P | Names on screen: Grace Delgado, Dana Whitfield, rows from `SMC`, and "Chau" / "Janice" from the guide titles. No file input |
| 8 | P | 310 text fragments of section 2 matched literally against `app.js`; the rest are built from `SMC` or split by bold spans and were read on screen |
| 9 | P | Guided path and the Graduate school path clicked through |
| 10 | P | All five rules asked; rules 2, 4, 5 show the booking button |
| 11 | P | Matched literally (part of item 8's check) |
| 12 | P | Extra strings are only those section 7 names ("Grace:", "done", "not yet", "Grace Delgado, the student from the demo", image names). W1–W5 not applied |
| 13 | P | Script found no clipped box at 1440, 1280, 1024, 768, 390, 360, 1920 on 14 states each |
| 14 | P | Classic script tag; `git status` shows `shared/` untouched; no rows in this folder |
| 15 | P | 9 of 9 rows pass in the page |
| 16 | P | Rows 1–8: P108, P224, P028, P046, P286, P004, P178, P131 with TV-A's reasons; line reads "#4 … because of her interview answers." |
| 17 | P | P108, P224, P028, P286, P220, P124, P168, P208; 15 of 15 rows Computer Information Systems; line reads "#27" |
| 18 | P | |
| 19 | P | |
| 20 | P | 4%, 13%, 17%; target 60% |
| 21 | P | 20, 40, 50, 55 read on `readiness`; 40 and 55 on `growth`; 50 on `recs` |
| 22 | P | 300 / 100 / 70 / 200, then 71; all four charts read back |
| 23 | P | |
| 24 | P | |
| 25 | P | |
| 26 | P | Script over every visible element in 14 states × 3 widths: all on the scale. States not in that sample were not measured |
| 27 | P | Same script: sizes on the scale, none under 14px |
| 28 | P | Same script: radii on the tokens; no element with both border and shadow. Nesting read in the code: one level at most |
| 29 | P | Measured bottoms against 828px. Tightest: `recs` before the interview, 825px |
| 30 | P | |
| 31 | P | 3 whole rows at 1280×720 |
| 32 | P | With `.woff2` blocked: no overflow or overlap at 1440 or 390. This box falls back to DejaVu, not Segoe UI or Georgia; with it `match` shows 4 rows above the fold, not 5 |
| 33 | P | |
| 34 | P | Computed from tokens (table above), not sampled from pixels |
| 35 | P | See Deviation 14 for the timeline dot |
| 36 | P | Native checkbox, radio and select use the browser's own outline |
| 37 | P | Light with the OS set to dark. Second half does not apply: no dark theme |
| 38 | P | Each row of 9.5 read in the code and on screen |
| 39 | P | Tab order stepped on `entry`, `interview`, `recs`, `readiness`, `records`, `match`, `talk`. `growth` and `overview` have no control in main |
| 40 | P | Entry → `talk` driven with Tab, Enter and PageDown only |
| 41 | P | Also checked: no stop change from the search field or a slider |
| 42 | P | |
| 43 | P | 0 elements with `disabled` |
| 44 | N | Structure is as specified (two hidden logs, `role="status"` on toast and messages, no `role="alert"`). Not listened to with a screen reader |
| 45 | P | Script: no button, link, field or label under 44×44. Checkboxes and radios are 24px inside a 44px label |
| 46 | P | |
| 47 | P | |
| 48 | P | Sampled with `?rm=1` on a stop change and a re-rank: no inline transform. Not sampled on every animation |
| 49 | P | By the tokens: longest is 400ms (`sm-count`, ring, scroll) |
| 50 | P | Two PageDowns 40ms apart land on stop 3. Re-targeting of rows in flight relies on Flip's `overwrite`; not filmed |
| 51 | P | 4× CPU throttle, "Same major" 3 → 10: longest frame 33ms, no long task. Driven by synthetic `input` events, not a real pointer drag |
| 52 | P | |
| 53 | N | Headless Chromium blocks `file://`. Over http: zero requests to another host, 8 local files |
| 54 | P | 0 errors, 0 warnings on load and along the guided path |
| 55 | P | `gsap.version` and `Flip.version` read "3.15.0" in the page |
| 56 | P | 1.4 / 44 / 81 kB; folder holds the four files and `screenshots/` |
| 57 | P | |
| 58 | P | 19 files, 74–244 kB |
| 59 | P | |
| 60 | P | Each parameter of 3.7 exercised; `theme=dark` is ignored by design |

Tally: 58 pass, 0 fail, 2 not checked (44, 53). Also not checked: 200% zoom and text-spacing overrides (9.6).

## 3 things to refine next

1. Open it by double-click on the classroom laptop and at the projector's real resolution; item 53 and the above-the-fold margins (3px on `recs` before the interview, 17px on `match`) need that room test.
2. Decide the match layout with the owner: the band over a full-width table (built) or 14.6's thirds with a smaller table type.
3. Give `sm-rerank` a proper exit for rows leaving the list, and listen to both transcripts with a screen reader.
