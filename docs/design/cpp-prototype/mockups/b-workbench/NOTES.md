# Direction B: Workbench

**Open:** double-click `docs/design/cpp-prototype/mockups/b-workbench/index.html` (Chrome or Edge). No server, no build, no network.
**Status:** mockup for owner review. It is not app code. Nothing in `apps/` changed.
**Files:** `index.html` (shell and icon sprite, 8.4 kB), `styles.css` (tokens and layout, 53.7 kB), `app.js` (state, components, screens, 85.6 kB), `screenshots/` (19 PNGs).
**Shared, read-only:** `../../shared/data.js` (`window.SMC`), `../../shared/vendor/gsap/` (GSAP 3.15.0 core and Flip), `../../shared/vendor/fonts/` (2 files, 70.5 kB).

## Concept

The staff tool, taken seriously. A full-height sidebar always shows where you are; a command-style switcher (`Ctrl`/`⌘`+`K`) jumps between the three portals, their screens and the five events; a compact sticky header carries the title and its status label; and the tools (interview, records, match) fill the window as hairline-separated panes. Neutral greys do the background work. Green appears where something is active or true. Gold appears on Grace, on "planned", on the ring's target mark and on "Registered". The best screen is Match students to an event: weights on the left, a 10-row ranked table on the right that re-sorts under the sliders.

## Palette

Brand and status tokens are the shared ones (DESIGN.md 6.2). Neutrals are section 13.3's.

### Light (default, whatever the operating system says)

| Token | Hex | Use |
|---|---|---|
| `--sm-page` | `#f4f5f4` | Page, row hover wash |
| `--sm-surface` | `#ffffff` | Panes, cards, header, table body |
| `--b-sunk` | `#eceeed` | Table head band, wells, assistant turns, date tile, hover on white, reason chip, callout, `Say:` line, "new" pills |
| `--b-sidebar` | `#eef0ee` | Sidebar |
| `--sm-ink` | `#16211c` | Text |
| `--sm-muted` | `#55615b` | Secondary text, labels |
| `--sm-line` | `#e1e5e2` | Hairlines (decorative) |
| `--sm-line-strong` | `#76837c` | Control outlines, slider track, empty step ring |
| `--sm-green` / `-hover` / `-soft` | `#005030` / `#003d24` / `#e1ede6` | Primary action, current item, bars; working label, tracks, outcome message |
| `--sm-gold` / `-soft` / `-ink` | `#fdb71e` / `#fff1cc` / `#7a5600` | Registered, target mark; Grace's row, planned label, N2 |
| `--sm-part` / `-soft` | `#2e5f8a` / `#e3edf7` | "Partly built" only |
| `--sm-plate`, `--sm-qr-ink` | `#ffffff`, `#10251b` | Logo plate and check-in code; the same in both themes |

### Dark (opt-in only: guide control or `?theme=dark`)

Section 6.4's values, plus `--b-sunk #1b2a22`, `--b-sidebar #101c16`, `--sm-green-hover #7fd0a4`.

### Contrast (WCAG 2.x, computed 2026-10-06)

| Pair | Light | Dark | Needs |
|---|---|---|---|
| ink on page / surface | 15.15 / 16.56 | 15.71 / 14.17 | 7 |
| ink on sunk / sidebar | 14.21 / 14.45 | 12.77 / 14.91 | 7 |
| ink on green-soft / gold-soft | 13.76 / 14.75 | 11.68 / 11.33 | 7 |
| muted on page / surface | 5.92 / 6.47 | 8.06 / 7.27 | 5 |
| muted on sunk / sidebar / gold-soft | 5.55 / 5.65 / 5.76 | 6.55 / 7.65 / 5.82 | 5 |
| green on surface / page / sunk / sidebar | 9.59 / 8.77 / 8.23 / 8.37 | 7.38 / 8.18 / 6.65 / 7.77 | 5 |
| green on green-soft / gold-soft | 7.97 / 8.54 | 6.08 / 5.90 | 5 |
| on-green on green / green-hover | 9.59 / 12.40 | 8.30 / 10.21 | 7 |
| gold-ink on gold-soft / surface / green-soft (bar edge) | 5.92 / 6.65 / 5.53 | 9.05 / 11.31 / 9.32 | 5 (3 for the edge) |
| on-gold on gold (Registered) | 10.31 | 10.31 | 7 |
| part on part-soft | 5.68 | 7.33 | 5 |
| page on ink (toast) | 15.15 | 15.71 | 7 |
| line-strong on surface / page / sunk / sidebar | 3.96 / 3.62 / 3.39 / 3.45 | 5.28 / 5.85 / 4.76 / 5.56 | 3 (non-text) |
| gold on surface | 1.75 | — | decorative only; never text, border or ring |

## Type

- **Instrument Sans** (variable, 400 / 500 / 600 / 700) for everything; **JetBrains Mono** 500 for IDs, ranks, weights, counts, percentages, the match line and the shortcut hint. Fallbacks as section 10.4. Two font files, 70.5 kB.
- Entry title 48 / 700. Screen title 28 / 600. `h2` and `h3` 18 / 600. Body, table, chat and helper text 16. N1 16 / 600. Block labels, table heads, speaker labels, pills, status label and N2: 14 / 600. Tile figure 28 mono, ring figure 36 mono, weight value 18 mono, date tile day 24 mono.
- Nothing under 14px. Everything that carries data or is read aloud is 16px or more. At 390 the scale steps down as in section 5.3.
- `word-spacing: 0.06em` on the body, so the ` · ` separator stays readable from the back row (Instrument Sans has a narrow space).

## Layout principles

1. The sidebar never moves. Portal changes swap its labels; screen changes swap only the main pane.
2. The title, its status label and the description sit in a sticky header, so the status label cannot scroll away. N1 sits in the sidebar directly under the portal name on every screen, at 16px.
3. Tools fill the window: `interview`, `records` and `match` are fixed-height panes with their own scroll (sticky table head, docked reply bar, sticky table footer). Reading screens (`recs`, `readiness`, `growth`, `overview`, `talk`) scroll as a page, max 1120px.
4. Hairlines, not gaps: panes and tiles share 1px `--sm-line` dividers inside one bordered group. No shadows on cards.
5. One 4px spacing scale; controls 40px tall with a 44px hit area; table rows 44px minimum, cells 8 / 12.
6. Layout answers to the width of the work area, not the window (container queries), so the guide can dock beside the content. On `match` the weights pane (256px) sits beside the table when the work area is 1160px or wider (a 1440 window); below that the four weights sit in one row above a full-width table, so a reason stays on two lines and names never wrap.
7. At 1023px and below the sidebar becomes a top bar with a wrapping menu, N1 becomes a fixed top strip, the guide button docks in the top bar above the switcher, panes stack, tables become labelled stacked rows (below 640px), and the event picker becomes a radio list (below 640px).

## Motion

All values are the section 8.2 tokens (`SM_MOTION` in `app.js`, `--sm-dur-*` and `--sm-ease-*` in CSS).

| Moment | What happens | Maps to |
|---|---|---|
| Dense re-rank (showpiece) | A hand-written FLIP on one GSAP core tween (audit D-06): read row tops → reorder → read once → tween `y` to 0, 280ms `power2.inOut`, transform only. Rank numerals change at the first frame. Arrivals fade in (220ms) over a gold-soft wash (900ms). Rows that leave the visible 15 are removed on the first frame (audit D-05). A change mid-flight reads positions first, kills the flight and starts from where rows are. The Grace line's number counts (#4 → #27). One render per animation frame. | `sm-rerank`, `sm-wash`, `sm-count` |
| Command-style switch | Popover: opacity and scale 0.98 → 1 from the switcher (160ms). On Enter it leaves at once; the old pane fades out as a clone (160ms), the new one rises in (220ms); sidebar labels cross-fade (120ms). Focus is on the new `h1` at once. | `sm-portal`, `sm-screen` |
| Search narrows | Rows that no longer match fade as clones (160ms); the rest close up with GSAP Flip, `simple: true` (280ms); the count updates at once. | `sm-rerank` |
| Inspector fills | New interest pills scale 0.9 → 1; "Not yet" cross-fades to the goal; turns enter with `sm-turn`. | `sm-card-fill`, `sm-turn` |
| Also | `sm-press`, `sm-lift` (doors), `sm-count`, `sm-ring-draw`, `sm-bars-grow`, `sm-register`, `sm-panel`, `sm-guide`, `sm-toast`, `sm-confirm`. | section 8.3 |

Status labels, N1, N2 and the logo never animate: every entrance skips the subtrees that hold them. Reduced motion (`prefers-reduced-motion`, `?rm=1`, or `data-motion="reduced"`): rows swap at once with a 150ms fade, figures and the ring show final values, no transform runs.

## Review deep links

Append to `index.html`. State persists in `localStorage` under `smc.b.v1`.

```text
?reset=1                                  fresh demo
?reset=1&iv=done&s=match                  Grace at #4
?reset=1&iv=done&s=match&w=10,3,2,2       Grace at #27, all CIS
?reset=1&s=match                          before the interview
?reset=1&iv=done&s=match&ev=U3            Audit Season, Grace not in the top 30
?reset=1&iv=done&s=recs&reg=E11           registered, check-in card
?reset=1&iv=done&s=readiness&help=chat    bot panel (also msg, book, res)
?reset=1&s=records&q=Delgado              14 of 300 records
?reset=1&iv=done&s=match&guide=1          guide open
?p=student | hub | partner   &theme=dark   &rm=1
```

## Deviations from DESIGN.md, each with a reason

| # | What | Reason |
|---|---|---|
| 1 | The open guide is a 400px panel at the bottom right. From 1440px wide the shell reserves a 424px column for it and the content reflows; below 1440px it overlays. | 7.16 says it must not overlap a hero region. No fixed spot is clear on every screen (`readiness` and `overview` fill the fold), so it covers nothing at the audited size. On `match` the weights then sit above the table. |
| 2 | The event picker is a native select in the page header (7.9 allows it), not on top of the weights pane (13.6). At 390 it is a radio list. | In a 256px pane a native select cuts "Northline Analytics: Behind the Business · Thu Mar 4, 2027". Names are never truncated (section 4). |
| 3 | Descriptions wrap at 760px (about 95 characters); the `match` description has no cap. | "Max 70 characters per line" (13.4) and "fits in 2 lines" (4) cannot both hold for a 174-character description. Two lines won; on `match` one line keeps 10 rows on screen. |
| 4 | Gold is held to B's list. The reason chip, callouts, the `Say:` line and the "new" pills (interests on the card, "AI interview · today") are neutral on `--b-sunk`, not gold-soft. Kept gold: N2 and the planned label (gold-ink on gold-soft, as 7.4), the gold bars of charts 2 and 4 with their gold-ink outline, the third progress dot, and the future dot on the timeline (a gold ring with a 1px gold-ink keyline). | Audit D-03: a direction may re-tone a surface, never an honesty component. "Completed" pills stay green-soft (7.6). |
| 5 | Assistant turns, the date tile and hovers use `--b-sunk`, not green-soft. Green-soft stays on the working label, bar, ring and slider tracks, the outcome message and "Completed" pills. | 6.1: "no green-tinted surfaces except selected rows" in B. |
| 6 | Menu items are weight 600 at rest and current (7.2). Current is shown by fill, the 3px bar, green text and `aria-current`. | 13.4 lists weight as a cue; 7.2 already sets 600 at rest. |
| 7 | The switcher's first option is "Smart Match CPP" and returns to the entry. | No longer a deviation: audit D-13 adds this to 13.4 ("the first option is the entry, labelled with its title"). |
| 8 | The switcher button shows the words `Switch portal` and the hint `Ctrl` `K` (`⌘` on a Mac). | Her string stays visible (audit 8); 13.3 names the shortcut hint. |
| 9 | At 1023px and below N1 is a fixed strip at the top of the window. | It must be on screen in every state at 390 (H1). |
| 10 | Helper lines are 16px, not 14px. | Several carry data ("4.6 of 5 from 14 students"); the 16px floor applies to anything read aloud. |
| 11 | On `match`, rows leaving the visible 15 are removed on the first frame (audit D-05). On `records`, rows that stop matching the search fade as clones in an overlay (13.5 row 3). The wash is a span inside the row. | A removed `<tr>` cannot hold its place in a table. Only opacity is animated. |
| 12 | Closing a help panel is instant; opening animates. The content below is FLIP-ed either way. | Kept the code small; the open is the moment the presenter talks over. |
| 13 | On `Register` the check icon scales in (0.5 → 1) instead of drawing its stroke. | 8.7 allows only transform and opacity (the ring is the one exception). |
| 14 | `Reset demo` keeps the guide open and the theme. | It is pressed from the guide during rehearsal. |
| 15 | Grace's goal reaches the matching as soon as turn 3 is answered; her interests when the interview finishes. | Her script sets the goal at turn 3 (2.4); `viaAI` and interests are set at turn 5. |
| 16 | The N8 hint is visually hidden until an empty send is tried; it is always the button's description. | A permanent "Type an answer first." reads as an error. |
| 17 | `Back` and `Next` at the ends are described by the "Stop n of 9" line. | A disabled control needs a described reason (7), and no new string is allowed (2.13). |
| 18 | `recs` has a visually hidden `h2` "Events for me" above the list. | Event titles are `h3` (7.14); this avoids a skipped level. |
| 19 | `index.html` has `<link rel="icon" href="data:,">`. | Stops a favicon 404 when the folder is served for review. No request is made. |
| 20 | Dark theme ships (optional for B) with two extra tokens. | `?theme=dark` is a listed deep link. |
| 21 | N1 sits under the portal name at 16px, not at the foot of the sidebar at 14px (13.4). | Audit B-05 and X-08: at the foot it was the least visible marker of the three. |
| 22 | The weights pane is 256px, not 304px (13.4), and under a 1160px work area the weights sit in one row above the table. The table has fixed columns: `#` 56, Student 160, Major 196 (264 when the weights are above), What we know 136, the reason takes the rest. | Audit B-06 and B-07, and section 4 (a reason fits in 2 lines; names are never broken). At 1280×720 a side pane leaves the reason 3 lines. |
| 23 | PageDown and PageUp change stop from every control except a text input or textarea, a slider included. Sliders keep arrows, Home and End. Enter in the records search moves focus to the title. | Audit D-08: 7.8 and 7.16 made the clicker stall after the scripted slider move (B-04). |
| 24 | Activation inside `main` is ignored for 350ms after an interview turn or a screen renders; the second click of a double-click on a reply does nothing; a held Enter or Space activates once. | Audit B-01: a double-click answered the next turn and moved Grace from #4 to #8. |
| 25 | After a bot suggested question, focus stays on the pressed chip (it used to move to the field). A help panel that is not fully in view scrolls to just under the sticky header. | Audit B-02, B-08, X-11, X-14. |
| 26 | At 1023px and below the guide button is in the top bar (not floating bottom right). | Audit B-10: it covered a reply chip, a tile and a weight value at 390. |

`impeccable detect` was not run. Kept on purpose against its defaults: the entry's small labels above door titles and the 3px current-item bar, because DESIGN.md sections 2.3 and 13.4 require them.

## Audit fixes (2026-10-06)

Source: `../../audit/AUDIT.md`. Verified in headless Chromium through playwright-cli at `http://127.0.0.1:8792/`, by real mouse and key input, at 1440×900, 1280×720 and 390×844. After the fixes: `SMC.selfTest()` 9 of 9; Northline top 8 = Emeka Soto, Camila Alcantar, Mei Huynh, Grace Delgado (#4), Nadia Okafor, Brandon Soto, Lucas Nguyen, Ryan Santos; 0 console errors or warnings; 0 requests to another host; no visible string changed.

| ID | Sev | Result | What changed | How verified |
|---|---|---|---|---|
| B-01 | HIGH | fixed | Activation in `main` is ignored for 350ms after a turn or screen renders; a click with `detail > 1` on a reply does nothing; a repeating Enter or Space is cancelled | Before: double-click on "Not sure yet" stored "No thanks", goal "Undecided", Grace #8, "match 4 of 10". After: real double-clicks on all five answers at 1440 and at 390 give the log "I'm curious about tech jobs / Technology, Entertainment / Not sure yet / Yes, help me compare / Show my events", Grace #4, "match 6 of 10". Enter held for 25 repeats, and Space, on the first chip: one answer, 2 interests |
| B-02 | HIGH | fixed | Focus stays on the pressed chip; the panel scrolls to 12px under the sticky header only when part of it is out of view | 1440×900 after "How do I get my resume reviewed?": N2 at y=174–212 (was 44–82, under the header at 113), student turn 224–272 inside the log 212–492, page scroll unchanged at 524. Same at 1280×720. 390: N2 at 113–151 under the N1 strip. Screenshot 08 |
| B-03 | HIGH | fixed | Entry bottom padding 96 → 48, lede full width; under 800px high: tighter top, logo 40px, door padding 8 / 16, 8px gaps | 1280×720: page 720 high (was 882), doors end at 322 / 446 / 570 (were 426 / 570 / 714), demo line ends at 634 (was 786). 1440×900: page 900 high. With text forced wider (lede and door 1 on 3 lines) both still fit: demo line at 686 and 810. Screenshot 01 |
| B-04 | HIGH | fixed | The slider's own Page-key handler is removed; the global handler skips text fields only; Enter in the search focuses the title | Mouse drag of "Same major" to 10, then PageDown: "Your talk: Northline Analytics", weight still 10 (was: weight 8, same screen). PageUp returns. PageDown from the select: next stop, event unchanged. Search "Delgado": PageDown ignored in the field, Enter, PageDown → match. Arrows, Home, End still move the weight |
| B-05 | MEDIUM | fixed | N1 is 16px and sits under the portal name | Computed 16px / 24px; top y=218, between the switcher (bottom 202) and the menu (top 298); on screen on 9 of 9 stops at all three widths |
| B-06 | MEDIUM | fixed, by another route | Under a 1160px work area the weights sit four across above a full-width table. The proposed 256px side pane still left the reason on 3 lines at 1280 | 1280×720: columns 56 / 160 / 264 / 400 / 136, rows 44–65px (were 89), reasons 2 lines at most on all 5 events, 5–6 whole rows, Grace #4 whole. 1366×768: 5–7 whole rows |
| B-07 | MEDIUM | fixed | Fixed columns; Student and What we know do not wrap; "Profile card (AI interview)" may break only before the bracket; pane 256px | 1440×900: columns 56 / 160 / 196 / 372 / 136; every name on 1 line; reasons 2 lines on all 5 events and at major = 10; 10 whole rows. Screenshots 12, 13 |
| B-08 | MEDIUM | fixed | As B-02, for all four panels | 1280×720: bot panel at y=125–594, N2 174–212 (was N2 top 722, below the fold); message, booking and resources panels open at y=125. 1440×900: bot and message panels at y=125; booking and resources already fit (y=649–843) and do not scroll |
| B-09 | LOW | fixed | "Showing 15 of the top 30." is hidden while the list is empty | Weights 0,0,0,0: line hidden, N7 shown; one ArrowRight: 15 rows, line back |
| B-10 | LOW | fixed | At 1023px and below the guide button is in the top bar above the switcher | 390: button at x=200, y=44 (y=56 on the entry) on 9 of 9 screens, covers no control or tile. Screenshots 16–19 |
| B-11 | LOW | left | Toast over a marker step for 4 seconds | Accepted by the audit |
| B-12 | LOW | left | Guide panel over the table at 1280×720 | Accepted by the audit (rehearsal only). From 1440px the guide has its own column |

| ID | Result for B | Note |
|---|---|---|
| X-07 | fixed | = B-09 |
| X-08 | fixed | = B-05 |
| X-10 | left | Stop controls stay below `Say:`; the audit names no single place |
| X-11, X-14 | fixed | = B-02, B-08 |
| D-01 | met | 10 whole rows at 1440×900, 5 or 6 at 1280×720, Grace's row whole in both |
| D-02 | met | Descriptions 2 lines at 1440, about 95 characters (deviation 3) |
| D-03 | applied | "New" pills moved from green-soft to `--b-sunk`; future dot is a gold ring with a 1px gold-ink keyline. N2, the planned label and the gold bars already kept gold-soft / gold |
| D-04 | no change | 40px drawn controls with a 44px hit area stay |
| D-05 | applied | `match`: leaving rows removed on the first frame. `records` search keeps its fade (13.5) |
| D-06 | applied | Hand-written FLIP on the drag; see item 51 |
| D-07 | no change | Dark ships, by opt-in only; OS dark emulated: page stays `#f4f5f4` |
| D-08 | applied | = B-04 |
| D-09 | no change | `h1` outline-style `none` after PageDown |
| D-10 | no change | Select from 640px, radio list below |
| D-12 | no change | Hidden `h2` "Events for me"; profile card name is `h2` |
| D-13 | no change | The switcher already lists "Smart Match CPP" first |
| D-11, D-14 | not B | |

Not verified after the fixes: `file://` (blocked in the test browser), Windows Chrome and Edge, a real double-click on real hardware, the frame budget on the classroom laptop, a screen reader, dark-theme contrast of the changed pills and dot.

## Audit self-check (DESIGN.md section 11)

Checked on 2026-10-06 in headless Chromium at `http://127.0.0.1:8772/` (file:// is blocked in the headless browser), 1440×900 and 390×844, by script and by looking at every screenshot. Rows 3, 29, 31, 41, 49, 50, 51, 53, 56 and 58 were corrected after the audit fixes above.

| # | Result | Note |
|---|---|---|
| 1 | pass | N1 on screen on all 9 screens at both widths, and with the guide open on `match` |
| 2 | pass | 8 status labels verbatim, bottom edge at y=44–48; check-in card shows "Planned" |
| 3 | pass | N2 is outside both scrolling logs; stays at the same y when the log scrolls. The audit failed this (B-02: N2 went under the header after a bot question); fixed, N2 at y=174–212 before and after the question at 1440×900 and 1280×720 |
| 4 | pass | No typing dots, thinking state or streamed text exists in the code |
| 5 | pass | Demo line verbatim |
| 6 | pass | "Planned · draft markers" and the closing line present |
| 7 | pass | All names from `SMC` or section 2; no file input |
| 8 | pass | Every string literal of 9+ characters in `app.js` was matched verbatim against DESIGN.md; short ones checked in the DOM dumps |
| 9 | pass | Turns 1–5, 4a and 4b, all options, by click path |
| 10 | pass | 5 rules, 5 answers; booking button on rules 2, 4, 5 |
| 11 | pass | 9 entries typed from 2.12 and matched verbatim by the string check; `match` entry also read in the DOM |
| 12 | pass | Only additions: N1–N10, the `Ctrl` `K` hint (13.3), hidden cues named in section 7. W1–W5 not applied |
| 13 | pass | No element clips its text at either width; the select is replaced by radios at 390 |
| 14 | pass | Classic script tag; `git status` shows `shared/data.js` unchanged; no copy of the rows here |
| 15 | pass | 9 of 9 rows `pass: true` in the page |
| 16 | pass | P108, P224, P028, P046, P286, P004, P178, P131 with TV-A's reasons; "#4" line |
| 17 | pass | P108, P224, P028, P286, P220, P124, P168, P208; all visible rows CIS; "#27" line |
| 18 | pass | "Grace has not done her interview yet…"; three "before" rows at 3, 1, 1 of 10 |
| 19 | pass | 6, 4, 3 of 10 with the listed reasons |
| 20 | pass | 4% → 13% → 17%; target 60% |
| 21 | pass | 20 fresh, 40 after the interview, 50 after one registration, 55 after one self-check; same on `recs`, `readiness`, `growth` |
| 22 | pass | 300 / 100 / 70 / 200 fresh, 71 after; four charts match 2.8 |
| 23 | pass | 25 rows and "300 of 300 records"; Delgado: 14 rows, "AI interview · today" |
| 24 | pass | "Graduate school" → turn 4b, card shows "Graduate school" |
| 25 | pass | Reload on `talk` kept the interview, registration, self-check and screen; two presses of `Reset demo` cleared them |
| 26 | pass | Script scan of every visible element on 14 states × 2 widths: all margins, paddings and gaps on the scale. Pseudo-elements and the open switcher were not scanned (on the scale by construction) |
| 27 | pass | Same scan: sizes 14, 16, 18, 20, 24, 28, 36, 48 only (390: 14, 15, 16, 17, 20, 24, 28, 34) |
| 28 | pass | Radii 4, 6, 10, 14, 999 only; no element has both a border and a shadow; cards nest one level |
| 29 | pass | Checked on screenshots 01–14; `match` shows 10 whole rows, Grace's #4 among them. The entry is 900px high at 1440×900 (no scroll) |
| 30 | pass | scrollWidth = 390 on all screens; `ol`/`ul` stacked rows; text 14px or more |
| 31 | pass | At 1280×720: picker, 4 weights in one row, Grace line and 5 whole rows of 2 lines (was 5 rows of 3 lines); Grace's row #4 whole. The entry fits (720px high, demo line bottom at y=634) |
| 32 | pass | Fonts blocked: no overflow or clipping on 9 screens × 2 widths. Tested with Linux fallback fonts, not Segoe UI; `match` then shows 9 rows |
| 33 | pass | Token values as shared |
| 34 | pass | Every pair used is in the table above, computed; not pixel-sampled |
| 35 | pass | Gold is fill only; bar edges and the timeline ring are gold-ink; target mark has ink keylines and tile 2's label |
| 36 | pass | line-strong 3.39–3.96 on its backgrounds |
| 37 | pass | OS dark emulated: page stays light. `?theme=dark` and the guide control switch it |
| 38 | pass | Each row of 9.5 has its second cue |
| 39 | pass | Tab order recorded on 7 screens and matches 9.2; a ring on every stop; no trap |
| 40 | pass | Entry → `talk` done with Tab, Enter, Space, End, PageDown only |
| 41 | pass | PageDown / PageUp through all stops, also straight after a mouse drag of a slider and from the select (audit D-08); ignored only in a text field; Enter in the search releases focus; `G` toggles the guide, not while typing |
| 42 | pass | Focus on the new `h1`; one `h1`, one `main`, one named `nav` (none on the entry) |
| 43 | pass | No `disabled` attribute anywhere; Send, Back and Next use `aria-disabled` with `aria-describedby`. The gold "Registered" button is `aria-disabled` with no description (its label is the reason) |
| 44 | pass | Hidden `role="log"` gets the newest assistant turn only; toast and messages are `role="status"`; no `role="alert"`. Checked in the DOM, not with a screen reader |
| 45 | pass, with note | Buttons and chips draw 40px tall with a 44px hit area (5.6, 9.3). A check of the drawn box alone reads 40px |
| 46 | pass | Booked, Sent, Opens, Opens the Career Hub page, 3 partner outcomes, invitations: all persistent `sm-message` lines |
| 47 | pass | No dialog; the switcher and guide are non-modal |
| 48 | pass | `?rm=1` on `match`: 0 transformed rows over 500ms, same end state; ring and figures final at once |
| 49 | pass | Longest action-tied motion: screen change 160 + 220ms; re-rank 280ms. The scroll that brings a help panel under the header is the browser's smooth scroll (instant under reduced motion); its length was not measured |
| 50 | pass | A second weight change mid-flight starts from the rows' current positions (read before the old tween is killed); after a 20-step mouse drag no row keeps a transform. Any key or click completes pane transitions. The 414.5 → 405.6px sample was taken on the Flip version and not repeated on the hand-written FLIP |
| 51 | pass, against the audit's D-06 budget | Only transform and opacity animate (ring excepted). At 4× CPU throttle (CDP; a test loop ran 41ms → 175ms), dragging "Same major" 3 → 10 with the mouse, 12 runs: worst frame 16.8ms in all 12, no long task. The same harness on GSAP Flip `simple: true`: a 33.3ms frame in 6 of 12 runs, so the drag uses the hand-written FLIP. Headless Chromium, frame gaps read from `requestAnimationFrame`; not measured on the classroom laptop |
| 52 | pass | Nothing runs on scroll, in a loop or unprompted; honesty components are skipped by every entrance |
| 53 | **not checked** | Not opened under `file://` by the builder (blocked in playwright-cli, before and after the audit fixes). The independent audit opened it under `file://` and passed it before the fixes; the fixes add no file, request or path. Served over http: the only requests were the page's own 8 local files |
| 54 | pass | 0 errors, 0 warnings on load and on the whole guided path |
| 55 | pass | `gsap.version` and `Flip.version` are 3.15.0; LICENSE.md is beside them; 4 classic scripts, no `type="module"` |
| 56 | pass | 8.4 / 53.7 / 85.6 kB against 40 / 70 / 90; folder holds the 4 files and `screenshots/` |
| 57 | pass | This file |
| 58 | pass | 19 PNGs, re-captured 2026-10-06 after the audit fixes at the same names, made-up data only |
| 59 | pass | Logo is `SMC.LOGO` unaltered on a white plate; no other mark or licensed face |
| 60 | pass | `p`, `s`, `iv`, `reg`, `help`, `w`, `ev`, `q`, `guide`, `theme`, `rm`, `reset` each exercised |

Tally: 59 pass (2 with a note: 45, 51), 0 not passed, 1 not checked (53).

Also not checked: 200% zoom reflow, text-spacing overrides, Edge, Firefox, a real screen reader, a real projector.

## 3 things to refine next

1. Re-measure item 51 on the classroom laptop in Windows Chrome (the 16.8ms figure is headless Chromium on Linux), and try a real double-click there on each interview answer.
2. Open it by double-click on the presenters' laptop in Chrome and Edge, and check the 16px table from the back of the room with the real projector (section 13.8).
3. Give the event picker a listbox popover so it can live on top of the weights pane as 13.6 draws it, with wrapping option text.
