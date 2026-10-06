# Direction B: Workbench

**Open:** double-click `docs/design/cpp-prototype/mockups/b-workbench/index.html` (Chrome or Edge). No server, no build, no network.
**Status:** mockup for owner review. It is not app code. Nothing in `apps/` changed.
**Files:** `index.html` (shell and icon sprite, 8.4 kB), `styles.css` (tokens and layout, 51.2 kB), `app.js` (state, components, screens, 83.4 kB), `screenshots/` (19 PNGs).
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
| `--b-sunk` | `#eceeed` | Table head band, wells, assistant turns, date tile, hover on white |
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
- Entry title 48 / 700. Screen title 28 / 600. `h2` and `h3` 18 / 600. Body, table, chat and helper text 16. Block labels, table heads, speaker labels, pills, status label, N1 and N2: 14 / 600. Tile figure 28 mono, ring figure 36 mono, weight value 18 mono, date tile day 24 mono.
- Nothing under 14px. Everything that carries data or is read aloud is 16px or more. At 390 the scale steps down as in section 5.3.
- `word-spacing: 0.06em` on the body, so the ` · ` separator stays readable from the back row (Instrument Sans has a narrow space).

## Layout principles

1. The sidebar never moves. Portal changes swap its labels; screen changes swap only the main pane.
2. The title, its status label and the description sit in a sticky header, so the status label cannot scroll away. N1 sits at the foot of the sidebar on every screen.
3. Tools fill the window: `interview`, `records` and `match` are fixed-height panes with their own scroll (sticky table head, docked reply bar, sticky table footer). Reading screens (`recs`, `readiness`, `growth`, `overview`, `talk`) scroll as a page, max 1120px.
4. Hairlines, not gaps: panes and tiles share 1px `--sm-line` dividers inside one bordered group. No shadows on cards.
5. One 4px spacing scale; controls 40px tall with a 44px hit area; table rows 44px minimum, cells 8 / 12.
6. Layout answers to the width of the work area, not the window (container queries), so the guide can dock beside the content.
7. At 1023px and below the sidebar becomes a top bar with a wrapping menu, N1 becomes a fixed top strip, panes stack, tables become labelled stacked rows, and the event picker becomes a radio list.

## Motion

All values are the section 8.2 tokens (`SM_MOTION` in `app.js`, `--sm-dur-*` and `--sm-ease-*` in CSS).

| Moment | What happens | Maps to |
|---|---|---|
| Dense re-rank (showpiece) | `Flip.getState` → reorder → `Flip.from`, 280ms `power2.inOut`, transform only. Rank numerals change at the first frame. Arrivals fade in (220ms) over a gold-soft wash (900ms). Leavers fade out as clones (160ms). A change mid-flight reads positions first, kills the flight and starts from where rows are. The Grace line's number counts (#4 → #27). One render per animation frame. | `sm-rerank`, `sm-wash`, `sm-count` |
| Command-style switch | Popover: opacity and scale 0.98 → 1 from the switcher (160ms). On Enter it leaves at once; the old pane fades out as a clone (160ms), the new one rises in (220ms); sidebar labels cross-fade (120ms). Focus is on the new `h1` at once. | `sm-portal`, `sm-screen` |
| Search narrows | Rows that no longer match fade (160ms); the rest close up with Flip (280ms); the count updates at once. | `sm-rerank` |
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
| 4 | Gold is held to B's list. The reason chip, callouts, the `Say:` line and the interest pills are neutral or green, not gold-soft. Kept gold: N2 (it is a "planned" marker), the gold bars of charts 2 and 4 (section 2.8), the third progress dot, the future dot on the timeline. | 6.1 and 13.7 restrict gold in B; 7.14, 7.16 and 7.6 ask for gold-soft. The direction's limit was applied where the content inventory did not require gold. |
| 5 | Assistant turns, the date tile and hovers use `--b-sunk`, not green-soft. Green-soft stays on the working label, bar, ring and slider tracks, the outcome message and "Completed" pills. | 6.1: "no green-tinted surfaces except selected rows" in B. |
| 6 | Menu items are weight 600 at rest and current (7.2). Current is shown by fill, the 3px bar, green text and `aria-current`. | 13.4 lists weight as a cue; 7.2 already sets 600 at rest. |
| 7 | The switcher's first option is "Smart Match CPP" and returns to the entry. | In B `Switch portal` opens the popover (13.4) and no longer returns to the entry (2.2). The entry must stay within two actions. The string is the entry's own title. |
| 8 | The switcher button shows the words `Switch portal` and the hint `Ctrl` `K` (`⌘` on a Mac). | Her string stays visible (audit 8); 13.3 names the shortcut hint. |
| 9 | At 1023px and below N1 is a fixed strip at the top of the window. | It must be on screen in every state at 390 (H1). |
| 10 | Helper lines are 16px, not 14px. | Several carry data ("4.6 of 5 from 14 students"); the 16px floor applies to anything read aloud. |
| 11 | Leaving rows fade as clones in an overlay; the wash is a span inside the row. | A removed `<tr>` cannot hold its place in a table. Only opacity is animated. |
| 12 | Closing a help panel is instant; opening animates. The content below is FLIP-ed either way. | Kept the code small; the open is the moment the presenter talks over. |
| 13 | On `Register` the check icon scales in (0.5 → 1) instead of drawing its stroke. | 8.7 allows only transform and opacity (the ring is the one exception). |
| 14 | `Reset demo` keeps the guide open and the theme. | It is pressed from the guide during rehearsal. |
| 15 | Grace's goal reaches the matching as soon as turn 3 is answered; her interests when the interview finishes. | Her script sets the goal at turn 3 (2.4); `viaAI` and interests are set at turn 5. |
| 16 | The N8 hint is visually hidden until an empty send is tried; it is always the button's description. | A permanent "Type an answer first." reads as an error. |
| 17 | `Back` and `Next` at the ends are described by the "Stop n of 9" line. | A disabled control needs a described reason (7), and no new string is allowed (2.13). |
| 18 | `recs` has a visually hidden `h2` "Events for me" above the list. | Event titles are `h3` (7.14); this avoids a skipped level. |
| 19 | `index.html` has `<link rel="icon" href="data:,">`. | Stops a favicon 404 when the folder is served for review. No request is made. |
| 20 | Dark theme ships (optional for B) with two extra tokens. | `?theme=dark` is a listed deep link. |

`impeccable detect` was not run. Kept on purpose against its defaults: the entry's small labels above door titles and the 3px current-item bar, because DESIGN.md sections 2.3 and 13.4 require them.

## Audit self-check (DESIGN.md section 11)

Checked on 2026-10-06 in headless Chromium at `http://127.0.0.1:8772/` (file:// is blocked in the headless browser), 1440×900 and 390×844, by script and by looking at every screenshot.

| # | Result | Note |
|---|---|---|
| 1 | pass | N1 on screen on all 9 screens at both widths, and with the guide open on `match` |
| 2 | pass | 8 status labels verbatim, bottom edge at y=44–48; check-in card shows "Planned" |
| 3 | pass | N2 is outside both scrolling logs; stays at the same y when the log scrolls |
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
| 29 | pass | Checked on screenshots 01–14; `match` shows 10 whole rows |
| 30 | pass | scrollWidth = 390 on all screens; `ol`/`ul` stacked rows; text 14px or more |
| 31 | pass | At 1280×720: picker, 4 weights, Grace line and 5 whole rows |
| 32 | pass | Fonts blocked: no overflow or clipping on 9 screens × 2 widths. Tested with Linux fallback fonts, not Segoe UI; `match` then shows 9 rows |
| 33 | pass | Token values as shared |
| 34 | pass | Every pair used is in the table above, computed; not pixel-sampled |
| 35 | pass | Gold is fill only; bar edges and the timeline ring are gold-ink; target mark has ink keylines and tile 2's label |
| 36 | pass | line-strong 3.39–3.96 on its backgrounds |
| 37 | pass | OS dark emulated: page stays light. `?theme=dark` and the guide control switch it |
| 38 | pass | Each row of 9.5 has its second cue |
| 39 | pass | Tab order recorded on 7 screens and matches 9.2; a ring on every stop; no trap |
| 40 | pass | Entry → `talk` done with Tab, Enter, Space, End, PageDown only |
| 41 | pass | PageDown / PageUp through all stops; ignored in the search field and in a slider (there they move the weight by 2); `G` toggles the guide, not while typing |
| 42 | pass | Focus on the new `h1`; one `h1`, one `main`, one named `nav` (none on the entry) |
| 43 | pass | No `disabled` attribute anywhere; Send, Back and Next use `aria-disabled` with `aria-describedby`. The gold "Registered" button is `aria-disabled` with no description (its label is the reason) |
| 44 | pass | Hidden `role="log"` gets the newest assistant turn only; toast and messages are `role="status"`; no `role="alert"`. Checked in the DOM, not with a screen reader |
| 45 | pass, with note | Buttons and chips draw 40px tall with a 44px hit area (5.6, 9.3). A check of the drawn box alone reads 40px |
| 46 | pass | Booked, Sent, Opens, Opens the Career Hub page, 3 partner outcomes, invitations: all persistent `sm-message` lines |
| 47 | pass | No dialog; the switcher and guide are non-modal |
| 48 | pass | `?rm=1` on `match`: 0 transformed rows over 500ms, same end state; ring and figures final at once |
| 49 | pass | Longest action-tied motion: screen change 160 + 220ms; re-rank settled in 291ms |
| 50 | pass | A second weight change 90ms into a flight continued from the row's position (414.5 → 405.6px, no jump); any key or click completes pane transitions |
| 51 | **not passed** | Only transform and opacity animate (ring excepted): pass. Frame budget: at 4× CPU throttle, 15 measured drags gave frames of 16.7 or 33.3ms at the four order changes, with a 50–67ms frame and a 50–80ms task in 4 of the 15 (machine load average 2–3, other builds running). 33.3ms is two refreshes, so it is over "33ms" to the letter |
| 52 | pass | Nothing runs on scroll, in a loop or unprompted; honesty components are skipped by every entrance |
| 53 | **not checked** | Not opened under `file://` (blocked in the headless browser). Served over http: the only requests were the page's own 8 local files. No `fetch`, XHR, module or absolute URL in the code |
| 54 | pass | 0 errors, 0 warnings on load and on the whole guided path |
| 55 | pass | `gsap.version` and `Flip.version` are 3.15.0; LICENSE.md is beside them; 4 classic scripts, no `type="module"` |
| 56 | pass | 8.4 / 51.2 / 83.4 kB against 40 / 70 / 90; folder holds the 4 files and `screenshots/` |
| 57 | pass | This file |
| 58 | pass | 19 PNGs, 62–204 kB, made-up data only |
| 59 | pass | Logo is `SMC.LOGO` unaltered on a white plate; no other mark or licensed face |
| 60 | pass | `p`, `s`, `iv`, `reg`, `help`, `w`, `ev`, `q`, `guide`, `theme`, `rm`, `reset` each exercised |

Tally: 58 pass (1 with a note), 1 not passed (51), 1 not checked (53).

Also not checked: 200% zoom reflow, text-spacing overrides, Edge, Firefox, a real screen reader, a real projector.

## 3 things to refine next

1. Re-measure item 51 on a quiet machine and on the classroom laptop. If frames still double at the order changes, move the weight drag to a hand-written FLIP on GSAP core tweens (measured at about half the script cost per change in a trial) and keep the Flip plugin for search.
2. Open it by double-click on the presenters' laptop in Chrome and Edge, and check the 16px table from the back of the room with the real projector (section 13.8).
3. Give the event picker a listbox popover so it can live on top of the weights pane as 13.6 draws it, with wrapping option text.
